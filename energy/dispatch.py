"""Stage B energy dispatch over 16 representative slices.

This module is the heart of the energy MILP. It takes an `EnergyNetwork`
(built from a populated `Grid`) plus the `Economics` table and decides:

  * Rooftop PV capacity (continuous kWp, capped by per-cell roof / acceptance).
  * Ground-mount PV capacity on `SOLAR_FARM` cells (continuous kWp).
  * Li-ion battery capacity (continuous kWh).
  * V2G charger count (integer; LP-relaxed to continuous in the foundation).
  * Per-slice grid import, grid export, battery charge / discharge, and V2G
    discharge in kWh / slice.

All costs are in INR. The single Stage B objective is total annualised
cost in INR / yr; carbon is reported as a diagnostic and becomes a second
objective in Stage C.

Two solve paths are provided so the foundation works in any environment:

  * **Pyomo MILP** (preferred). Activates if ``pyomo`` is importable.
    Solver order: HiGHS (``highspy``/``appsi_highs``), then CBC, then GLPK.
  * **Pure-Python fallback** (always available). A merit-order dispatcher
    over the 16 slices with a coordinate-descent sizer over the four
    capacity variables. Same objective and constraints as the MILP; runs
    on the Python standard library only.

Both paths return the same `DispatchResult` shape so callers can stay
agnostic. Tests cover the fallback unconditionally and the Pyomo path
only when Pyomo is installed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .costs import Economics, MONTHS, Scenario, load_economics
from .network import EnergyNetwork


# ---------------------------------------------------------------------------
# Optional Pyomo import.
# ---------------------------------------------------------------------------
try:
    import pyomo.environ as pyo  # type: ignore[import-not-found]
    _HAS_PYOMO = True
except Exception:  # pragma: no cover - dependency-gated path
    pyo = None  # type: ignore[assignment]
    _HAS_PYOMO = False


def has_pyomo() -> bool:
    """Return True if the Pyomo solver path is importable.

    Returns
    -------
    bool
        True when ``pyomo`` is installed in the active environment.
    """
    return _HAS_PYOMO


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
@dataclass
class DispatchResult:
    """Outputs of one MILP solve.

    Attributes
    ----------
    scenario : str
        Name of the scenario solved.
    solver : str
        Which solve path produced this result (``pyomo:highs``,
        ``pyomo:cbc``, ``pyomo:glpk``, ``fallback:merit_order``,...).
    alpha : float
        Carbon weight in the objective (Stage C). 0 = pure cost; 1 =
        pure carbon. Default 0.0 (cost only — Stage B behaviour).
    capacities : Dict[str, float]
        ``rooftop_pv_kwp``, ``solar_farm_kwp``, ``battery_kwh``,
        ``v2g_units``, ``biomass_kw_e`` (Stage C),
        ``tracked_pv_active`` (Stage C — 0 or 1).
    annual_cost_inr : float
        Total annualised cost in INR / yr. Sum of CAPEX annuities,
        fixed OPEX, grid import tariff, biomass fuel, V2G cycle
        degradation, minus grid export revenue.
    annual_emissions_kgco2 : float
        Total annual operational CO2 in kg.
    annual_demand_kwh : float
        Total annual demand in kWh (input).
    grid_import_kwh : float
    grid_export_kwh : float
    pv_generation_kwh : float
    battery_throughput_kwh : float
        Total discharged kWh through the battery in a year.
    v2g_discharge_kwh : float
    by_slice : Dict[str, Dict[str, float]]
        Per-slice flows. Each entry: ``demand_kwh``, ``pv_kwh``,
        ``battery_charge_kwh``, ``battery_discharge_kwh``,
        ``v2g_discharge_kwh``, ``grid_import_kwh``, ``grid_export_kwh``,
        ``dsr_reduce_kwh`` and ``dsr_add_kwh``.
    """

    scenario: str
    solver: str
    alpha: float = 0.0
    capacities: Dict[str, float] = field(default_factory=dict)
    annual_cost_inr: float = 0.0
    annual_emissions_kgco2: float = 0.0
    annual_demand_kwh: float = 0.0
    grid_import_kwh: float = 0.0
    grid_export_kwh: float = 0.0
    pv_generation_kwh: float = 0.0
    battery_throughput_kwh: float = 0.0
    v2g_discharge_kwh: float = 0.0
    biomass_generation_kwh: float = 0.0       # Stage C
    wte_generation_kwh: float = 0.0           # Stage C round 2
    biogas_generation_kwh: float = 0.0        # Stage C round 2
    thermal_storage_throughput_kwh: float = 0.0  # Stage C round 2
    dsr_shifted_kwh: float = 0.0              # Stage C round 3 (Claude 2)
    # REV-2: EV energy rescheduled by managed charging within
    # plug-in windows (base-year sum of ev_shift_out; pairs 1:1 with
    # ev_shift_in by per-(class, month, day-type) conservation).
    ev_smart_shifted_kwh: float = 0.0
    # Caveat-14 fix: 25-yr lifetime cost with tariff escalation
    # applied to the grid-import / grid-export portion only (CAPEX/OPEX
    # annuities locked at 2030-real INR). Reporting only - does not enter
    # the optimisation objective so the Pareto shape is unchanged.
    lifetime_cost_inr: float = 0.0
    by_slice: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # (D1(b) Phase 3 — Claude 2): per-period detail when the
    # multi-period LP path is active. Empty for single-period solves. Keys
    # are period years (e.g. 2030, 2042, 2055); values carry per-period
    # ``annual_cost_inr``, ``annual_emissions_kgco2``, ``annual_demand_kwh``,
    # ``installed_capacities`` (cumulative end-of-period kW/kWh/units),
    # ``new_build`` (period-specific additions), ``grid_import_kwh``,
    # ``grid_export_kwh``, ``pv_generation_kwh``, and the period's
    # ``represents_years`` weight. Single-period headlines
    # (``annual_cost_inr`` / ``annual_emissions_kgco2`` / ``capacities`` /
    # ``by_slice``) are filled from the 2030-period snapshot for direct
    # comparability with the single-period baseline.
    period_breakdown: Dict[int, Dict[str, object]] = field(default_factory=dict)

    # ---- convenience ----------------------------------------------------
    def total_pv_kwp(self) -> float:
        return (self.capacities.get("rooftop_pv_kwp", 0.0)
                + self.capacities.get("solar_farm_kwp", 0.0))

    def renewable_share(self) -> float:
        """Fraction of annual demand met by ALL on-site renewables.

        FX-7 /: now includes biomass + WTE + biogas, which are
        renewable and were previously excluded (the old metric understated the
        headline: 46.4% PV-only vs 59.1% true share at the 2026-06 baseline).
        The old PV-only metric lives on as ``pv_self_consumption_share``.

        Returns
        -------
        float
            (pv - exports + biomass + wte + biogas) / annual_demand, in [0, 1].
        """
        if self.annual_demand_kwh <= 0:
            return 0.0
        net = (self.pv_generation_kwh - self.grid_export_kwh
               + self.biomass_generation_kwh + self.wte_generation_kwh
               + self.biogas_generation_kwh)
        return max(0.0, min(1.0, net / self.annual_demand_kwh))

    def pv_self_consumption_share(self) -> float:
        """The pre- metric: self-consumed PV / demand (PV net of exports)."""
        if self.annual_demand_kwh <= 0:
            return 0.0
        net = self.pv_generation_kwh - self.grid_export_kwh
        return max(0.0, min(1.0, net / self.annual_demand_kwh))

    def lcoe_inr_per_kwh(self) -> float:
        """NET system cost per kWh of demand served (INR/kWh).

        FX-7 / honesty note: this is NOT a conventional LCOE -
        ``annual_cost_inr`` already nets off grid-export and DC-PPA revenue.
        The field name is kept for backward compatibility (viewer/CSV
        consumers); present it as "net cost of energy served"."""
        if self.annual_demand_kwh <= 0:
            return 0.0
        return self.annual_cost_inr / self.annual_demand_kwh


# ---------------------------------------------------------------------------
# Capacity caps from scenario.
# ---------------------------------------------------------------------------
def _capacity_caps(net: EnergyNetwork, econ: Economics,
                    scenario: Scenario) -> Dict[str, float]:
    """Per-tech upper bound, gated by the scenario flags.

    REV-5: the previously hard-coded cap VALUES (biomass 5,000
    kW, biogas 500 kW, battery 8 h x peak, WTE design population 100k) now
    come from economics.yaml `technologies.*` keys, with the old literals
    kept as back-compat defaults so legacy fixtures are byte-identical.
    """
    techs = econ.technologies or {}
    biomass_cap_kw = (
        float(techs.get("biomass_chp", {}).get("capacity_cap_kw_e", 5000.0))
        if getattr(scenario, "allow_biomass_chp", False) else 0.0
    )
    wte_cap_kw = (
        econ.wte_capacity_cap_kw_e(population=int(
            techs.get("wte_plant", {}).get("design_population", 100_000)))
        if getattr(scenario, "allow_wte", False) else 0.0
    )
    biogas_cap_kw = (
        float(techs.get("biogas_plant", {}).get("capacity_cap_kw_e", 500.0))
        if getattr(scenario, "allow_biogas", False) else 0.0
    )
    # Caveat / TES-targeting: if the YAML defines eligible
    # categories (central-cooling buildings), cap thermal storage at the
    # eligible cells' floor-area-weighted potential. Falls back to legacy
    # "4 * peak demand" behaviour when the eligibility list is empty.
    if getattr(scenario, "allow_thermal_storage", False):
        eligible_pot = net.total_thermal_storage_potential_kwh(econ)
        if eligible_pot > 0:
            thermal_cap_kwh = eligible_pot
        else:
            thermal_cap_kwh = net.total_peak_demand_kw() * 4.0
    else:
        thermal_cap_kwh = 0.0
    return {
        "rooftop_pv_kwp": net.total_rooftop_pv_cap_kwp() if scenario.allow_rooftop_pv else 0.0,
        "solar_farm_kwp": net.total_solar_farm_cap_kwp() if scenario.allow_solar_farm else 0.0,
        "battery_kwh": (
            net.total_peak_demand_kw()
            * float(techs.get("li_ion_battery", {}).get(
                "max_capacity_hours_of_peak", 8.0))
            if scenario.allow_battery else 0.0
        ),
        "v2g_units": (
            net.v2g_units(econ) if scenario.allow_v2g else 0.0
        ),
        "biomass_kw_e": biomass_cap_kw,
        "tracked_pv_active": (
            1.0 if getattr(scenario, "allow_tracked_pv", False) else 0.0
        ),
        "wte_kw_e": wte_cap_kw,
        "biogas_kw_e": biogas_cap_kw,
        "thermal_storage_kwh": thermal_cap_kwh,
    }


# ---------------------------------------------------------------------------
# Pure-Python fallback: merit-order dispatch + coordinate-descent sizing.
# ---------------------------------------------------------------------------
def _slice_costs(econ: Economics) -> Dict[str, Tuple[float, float, float]]:
    """Per slice: (import_tariff, export_tariff, hours)."""
    out = {}
    for s in econ.slices:
        out[s.id] = (econ.import_tariff(s.id), econ.export_tariff(),
                     float(s.hours_per_year))
    return out


def _apply_dsr_shift(
    econ: Economics,
    demand_kwh_by_slice: Dict[str, float],
) -> Tuple[Dict[str, float], float, Dict[str, float], Dict[str, float]]:
    """Stage C round 3 (Claude 2): shift peak demand into shoulder / off-peak.

    Operates on the aggregate per-slice demand array. For each
    peak / super_peak slice, the configured aggregate_shiftable_fraction
    is removed from that slice and spread evenly across non-peak slices
    in the same month that fall within ``shift_window_hours``. The total
    shifted kWh is returned for cost accounting (comfort penalty).

 (per-slice DSR export, schema v1.4): the return tuple
    now also includes per-slice ``reduce`` and ``add`` dicts so the
    cockpit can plot which windows the heuristic shifted from/to.

    Returns
    -------
    Tuple[Dict[str, float], float, Dict[str, float], Dict[str, float]]
        ``(adjusted_demand, total_shifted_kwh, reduce_by_slice,
        add_by_slice)``. Reduce / add are zero-initialised across all
        slices; only the affected slices carry non-zero values.
    """
    reduce_by_slice = {s.id: 0.0 for s in econ.slices}
    add_by_slice = {s.id: 0.0 for s in econ.slices}
    fraction = econ.dsr_aggregate_shiftable_fraction()
    window_hours = econ.dsr_shift_window_hours()
    if fraction <= 0 or window_hours <= 0:
        return dict(demand_kwh_by_slice), 0.0, reduce_by_slice, add_by_slice

    adjusted = dict(demand_kwh_by_slice)
    total_shifted = 0.0
    # (864-slice refactor Phase 3.3, Claude 2): bucket by
    # (month, day_type) so DSR conservation respects day-type boundaries
    # in 864-slice mode (a weekday-peak shift can't end up on a weekend
    # off-peak). In 144-slice mode every slice has day_type="mixed" so
    # this reduces to the legacy per-month behaviour. Hour comparison
    # uses ``s.hour`` directly (auto-populated to the daypart midpoint
    # in 144-slice mode, to the literal hour-of-day in 864-slice mode).
    slices_by_bucket: Dict[Tuple[str, str], List[str]] = {}
    for s in econ.slices:
        slices_by_bucket.setdefault((s.month, s.day_type), []).append(s.id)

    for s in econ.slices:
        if s.tariff_band not in ("peak", "super_peak"):
            continue
        shift_kwh = adjusted[s.id] * fraction
        if shift_kwh <= 0:
            continue
        peak_hour = int(s.hour)
        # Eligible targets: same (month, day_type), NOT peak/super_peak,
        # within window hours (wrap-around allowed).
        targets: List[str] = []
        for other_sid in slices_by_bucket[(s.month, s.day_type)]:
            other = econ.slice_by_id(other_sid)
            if other.tariff_band in ("peak", "super_peak"):
                continue
            dh = abs(int(other.hour) - peak_hour)
            dh = min(dh, 24 - dh)
            if dh <= window_hours:
                targets.append(other_sid)
        if not targets:
            continue
        adjusted[s.id] -= shift_kwh
        reduce_by_slice[s.id] += shift_kwh
        per_target = shift_kwh / len(targets)
        for t in targets:
            adjusted[t] += per_target
            add_by_slice[t] += per_target
        total_shifted += shift_kwh
    return adjusted, total_shifted, reduce_by_slice, add_by_slice


# Daypart ids used by DSR shift accounting. Mirrors `DAYPARTS` from
# `energy.costs` but kept private here to avoid an import cycle when
# `costs.py` imports from this module (it currently doesn't, but
# keeping it local is safer if that changes).
DAYPARTS_IN_DISPATCH: Tuple[str, ...] = (
    "00_02", "02_04", "04_06", "06_08", "08_10", "10_12",
    "12_14", "14_16", "16_18", "18_20", "20_22", "22_24",
)


def _merit_order_dispatch(
    net: EnergyNetwork,
    econ: Economics,
    rooftop_kwp: float,
    farm_kwp: float,
    battery_kwh: float,
    v2g_units: float,
    biomass_kw_e: float = 0.0,
    tracked_pv_active: float = 0.0,
    wte_kw_e: float = 0.0,
    biogas_kw_e: float = 0.0,
    thermal_storage_kwh: float = 0.0,
    # Stage C round 3 (Claude 2) flags. All default OFF so the legacy
    # dispatch path is unchanged when no Stage C round 3 scenario opts in.
    orientation_active: bool = False,
    battery_coupling_mode: str = "ac_traditional",
    dsr_active: bool = False,
    rooftop_capex_multiplier: float = 1.0,
    rooftop_yield_multiplier: float = 1.0,
    demand_multiplier: float = 1.0,
    bipv_kwp: float = 0.0,
    carport_kwp: float = 0.0,
    floating_pv_kwp: float = 0.0,
) -> DispatchResult:
    """Deterministic dispatch given fixed capacities.

    Per slice:
      1. Compute residual demand after on-site PV (rooftop + ground-mount).
      2. Discharge battery up to throughput cap and SOC reserve.
      3. Discharge V2G up to per-day availability.
      4. Import remainder from the grid at the slice tariff.
      5. If PV surplus: charge battery, export the rest.

    Battery is "cycled" within each month (the 12 daily-pattern slices of
    one month): total monthly discharge <= monthly charge * eff_RT.
    No multi-day chronological state; that belongs to Stage D.
    """
    # Stage C round 3 (Claude 2): battery RTE depends on coupling mode.
    # ac_traditional = 0.90 (legacy), dc_native (SigEnergy) = 0.94.
    # net of the plant's own auxiliary load (CERC RTE x (1-AEC)).
    rt_eff = econ.battery_rte_net_of_aux_for(battery_coupling_mode)
    max_dod = econ.battery_max_dod()
    v2g_kwh_per_unit_per_day = econ.v2g_kwh_per_unit_per_day()
    v2g_power_kw = econ.v2g_power_kw_per_unit()
    v2g_deg_inr_per_kwh = econ.v2g_cycle_degradation_inr_per_kwh()
    import_cap_kw = econ.import_capacity_limit_kw()
    export_cap_kw = econ.export_capacity_limit_kw()
    # Stage C round 3: use 25-yr project-lifetime average grid emission factor
    # (CEA NEP-2023 trajectory) instead of the static 2030 value.
    emission_factor = econ.emission_factor_trajectory_average()

    # Stage C round 3 (Claude 2): orientation-weighted rooftop yield when
    # the scenario opts into per-cell panel orientation choice. The
    # biosolar yield bonus is applied on top via rooftop_yield_multiplier.
    if orientation_active:
        yield_rooftop_base = net.pv_yield_per_kwp_kwh_oriented(econ)
    else:
        yield_rooftop_base = net.pv_yield_per_kwp_kwh(econ)
    yield_rooftop = {
        sid: y * rooftop_yield_multiplier
        for sid, y in yield_rooftop_base.items()
    }
    yield_farm_base = net.pv_yield_per_kwp_kwh_solar_farm(econ)
    # Stage C tracked PV: apply yield multiplier across all slices when active
    tracked_mult = econ.tracked_pv_yield_multiplier() if tracked_pv_active >= 0.5 else 1.0
    yield_farm = {sid: y * tracked_mult for sid, y in yield_farm_base.items()}
    # Stage C round 3 (Claude 2): DSR shift + biosolar demand multiplier.
    # Operates on a local copy so the cached network demand is not mutated.
    raw_demand = net.demand_by_slice_kwh(econ)
    scaled_demand = {sid: v * demand_multiplier for sid, v in raw_demand.items()}
    if dsr_active:
        (demand_kwh_by_slice, dsr_shifted_kwh,
         dsr_reduce_by_slice, dsr_add_by_slice) = _apply_dsr_shift(
            econ, scaled_demand,
        )
    else:
        demand_kwh_by_slice = scaled_demand
        dsr_shifted_kwh = 0.0
        dsr_reduce_by_slice = {s.id: 0.0 for s in econ.slices}
        dsr_add_by_slice = {s.id: 0.0 for s in econ.slices}
    slice_costs = _slice_costs(econ)

    # Stage C dispatchable plant parameters
    biomass_fuel_inr_per_kwh = econ.biomass_fuel_cost_inr_per_kwh()
    biomass_emission = econ.biomass_emission_factor_kgco2_per_kwh()
    biomass_annual_kwh_cap = (
        biomass_kw_e * econ.biomass_operating_hours_per_year()
    )
    # FX-6 / N7: the heuristic (non-production) path honours the annual
    # straw-energy budget but NOT the monthly availability profile or the
    # monthly fuel-cost multiplier (Pyomo builders carry the full model).
    _straw_cap = econ.biomass_annual_straw_energy_cap_kwh()
    if _straw_cap is not None:
        biomass_annual_kwh_cap = min(biomass_annual_kwh_cap, _straw_cap)
    # Stage C round 2: WTE + biogas (same dispatch pattern as biomass).
    # Caveat-2 fix: WTE marginal cost is fuel (~0) MINUS the
    # landfill-diversion credit (~Rs 3/kWh) representing avoided landfill
    # methane. The effective figure flows into both the merit-order
    # eligibility filter and the total-cost summation below.
    wte_fuel_inr_per_kwh = econ.wte_effective_fuel_cost_inr_per_kwh()
    wte_emission = econ.wte_emission_factor_kgco2_per_kwh()
    wte_annual_kwh_cap = wte_kw_e * econ.wte_operating_hours_per_year()
    biogas_fuel_inr_per_kwh = econ.biogas_fuel_cost_inr_per_kwh()
    biogas_emission = econ.biogas_emission_factor_kgco2_per_kwh()
    biogas_annual_kwh_cap = biogas_kw_e * econ.biogas_operating_hours_per_year()
    # Thermal storage: cooling-specific Li-ion analogue; cheaper per kWh.
    thermal_rt_eff = econ.thermal_storage_round_trip_efficiency()

    # Group slices by month for the monthly battery balance.
    slices_by_month: Dict[str, List[str]] = {}
    for s in econ.slices:
        slices_by_month.setdefault(s.month, []).append(s.id)

    # Per-slice results.
    by_slice: Dict[str, Dict[str, float]] = {}
    for sid in demand_kwh_by_slice:
        by_slice[sid] = {
            "demand_kwh": demand_kwh_by_slice[sid],
            "pv_kwh": 0.0,
            "battery_charge_kwh": 0.0,
            "battery_discharge_kwh": 0.0,
            "v2g_discharge_kwh": 0.0,
            "biomass_kwh": 0.0,            # Stage C
            "wte_kwh": 0.0,                # Stage C round 2
            "biogas_kwh": 0.0,             # Stage C round 2
            "thermal_storage_charge_kwh": 0.0,    # Stage C round 2
            "thermal_storage_discharge_kwh": 0.0, # Stage C round 2
            "dsr_reduce_kwh": dsr_reduce_by_slice.get(sid, 0.0),
            "dsr_add_kwh": dsr_add_by_slice.get(sid, 0.0),
            "grid_import_kwh": 0.0,
            "grid_export_kwh": 0.0,
        }

    # Stage C round 3 (Claude 2): BIPV facade and solar carports contribute
    # to PV generation alongside rooftop + ground-mount. BIPV yields at 60%
    # of rooftop south-fixed; carports yield like ground-mount.
    bipv_yield_mult = econ.bipv_yield_multiplier_vs_rooftop() if bipv_kwp > 0 else 0.0
    # Floating PV (Stage C round 5): yields like ground-mount but with a
    # water-cooling bonus (~4%). Capacity capped by BLUE_SPACE area.
    fpv_yield_mult = (
        econ.floating_pv_yield_multiplier_vs_ground_mount() if floating_pv_kwp > 0 else 0.0
    )

    # (A12): AC-bus delivery efficiency. Grid_import, V2G
    # discharge, battery_discharge are stored source-side (i.e. what the
    # meter or inverter delivers); only `ac_eff * source` reaches the
    # load. The deficit must therefore draw `need / ac_eff` from these
    # AC sources, which is how the cost / emissions / capacity sizing
    # see the upgrade. Non-AC flows (biomass / WTE / biogas / thermal
    # storage / DSR) keep the legacy convention because they sit on the
    # district bus, not behind the AC distribution.
    ac_eff = max(1e-6, 1.0 - econ.ac_loss_fraction())
    # (Phase 1A —: PSPCL UPSTREAM
    # T&D loss applies to grid_import only (not local-bus sources).
    # Combined grid-delivery efficiency = (1 - ac_loss) × (1 - pspcl_loss).
    pspcl_eff = max(1e-6, 1.0 - econ.pspcl_grid_loss_fraction())
    grid_import_eff = ac_eff * pspcl_eff

    # Pass 1: PV generation and immediate use; surplus and deficit per slice.
    surplus: Dict[str, float] = {}
    deficit: Dict[str, float] = {}
    for sid, demand_kwh in demand_kwh_by_slice.items():
        pv_kwh = (yield_rooftop[sid] * rooftop_kwp
                  + yield_farm[sid] * farm_kwp
                  + yield_rooftop_base[sid] * bipv_yield_mult * bipv_kwp
                  + yield_farm[sid] * carport_kwp
                  + yield_farm[sid] * fpv_yield_mult * floating_pv_kwp)
        by_slice[sid]["pv_kwh"] = pv_kwh
        net_kwh = pv_kwh - demand_kwh
        if net_kwh >= 0:
            surplus[sid] = net_kwh
            deficit[sid] = 0.0
        else:
            surplus[sid] = 0.0
            deficit[sid] = -net_kwh

    # Pass 2: battery cycling within each month (12 dayparts × n days).
    # Per-slice throughput cap = e_battery * max_dod * slice_hours / 24
    for month, sids in slices_by_month.items():
        avail_per_slice = {
            sid: battery_kwh * max_dod * slice_costs[sid][2] / 24.0
            for sid in sids
        }
        deficit_sids = sorted(sids, key=lambda x: -slice_costs[x][0])
        surplus_sids = sorted(sids, key=lambda x: slice_costs[x][1])

        total_discharge = 0.0
        for sid in deficit_sids:
            need = deficit[sid]
            if need <= 0:
                continue
            cap = avail_per_slice[sid]
            # (A12): inflate source-side draw by 1/ac_eff so
            # `give * ac_eff` reaches load. `cap` is source-side already.
            source_need = need / ac_eff
            give = min(source_need, cap)
            by_slice[sid]["battery_discharge_kwh"] = give
            deficit[sid] = max(0.0, need - give * ac_eff)
            total_discharge += give

        energy_to_charge = total_discharge / max(rt_eff, 1e-6)
        for sid in surplus_sids:
            have = surplus[sid]
            if have <= 0 or energy_to_charge <= 0:
                continue
            cap = avail_per_slice[sid]
            take = min(have, cap, energy_to_charge)
            by_slice[sid]["battery_charge_kwh"] = take
            surplus[sid] = have - take
            energy_to_charge -= take

    # Pass 3: V2G discharge in deficit slices (peak-priority), per month.
    days_in_month = {m: econ.calendar.get(m, {}).get("days", 30)
                      for m in slices_by_month}
    v2g_kwh_available_by_month = {
        m: days * v2g_kwh_per_unit_per_day * v2g_units
        for m, days in days_in_month.items()
    }
    for month, sids in slices_by_month.items():
        avail = v2g_kwh_available_by_month[month]
        deficit_sids = sorted(sids, key=lambda x: -slice_costs[x][0])
        for sid in deficit_sids:
            if avail <= 0:
                break
            need = deficit[sid]
            if need <= 0:
                continue
            slice_hours = slice_costs[sid][2]
            power_cap_kwh = v2g_units * v2g_power_kw * slice_hours
            # (A12): inflate source-side draw by 1/ac_eff.
            source_need = need / ac_eff
            give = min(source_need, avail, power_cap_kwh)
            by_slice[sid]["v2g_discharge_kwh"] = give
            deficit[sid] = max(0.0, need - give * ac_eff)
            avail -= give

    # Pass 3b (Stage C): biomass CHP fills deficit in slices where
    # biomass marginal cost (fuel only) is < grid tariff. Capped annually
    # by biomass_kw_e * operating_hours_per_year.
    def _dispatchable_plant_pass(out_key: str, capacity_kw: float,
                                   fuel_inr_per_kwh: float,
                                   annual_kwh_cap: float) -> None:
        if annual_kwh_cap <= 0:
            return
        eligible_sids = [
            sid for sid in demand_kwh_by_slice
            if deficit[sid] > 0
            and slice_costs[sid][0] > fuel_inr_per_kwh
        ]
        eligible_sids.sort(key=lambda x: -slice_costs[x][0])
        avail = annual_kwh_cap
        for sid in eligible_sids:
            if avail <= 0:
                break
            need = deficit[sid]
            if need <= 0:
                continue
            slice_hours = slice_costs[sid][2]
            power_cap_kwh = capacity_kw * slice_hours
            give = min(need, avail, power_cap_kwh)
            by_slice[sid][out_key] = give
            deficit[sid] = need - give
            avail -= give

    # Dispatchable plants in marginal-cost merit order (cheapest first).
    # Caveat-2 fix: WTE's landfill-diversion credit makes its
    # effective fuel cost negative (-Rs 3/kWh), so it now dispatches FIRST
    # ahead of biogas/biomass. Pre-fix order was biogas < biomass < WTE.
    plants = sorted(
        [
            ("wte_kwh", wte_kw_e, wte_fuel_inr_per_kwh, wte_annual_kwh_cap),
            ("biogas_kwh", biogas_kw_e, biogas_fuel_inr_per_kwh, biogas_annual_kwh_cap),
            ("biomass_kwh", biomass_kw_e, biomass_fuel_inr_per_kwh, biomass_annual_kwh_cap),
        ],
        key=lambda p: p[2],   # ascending marginal cost
    )
    for out_key, cap_kw, fuel, cap_kwh in plants:
        _dispatchable_plant_pass(out_key, cap_kw, fuel, cap_kwh)

    # Pass 3c (Stage C round 2): thermal cold storage as cooling-specific
    # battery. Treated like Li-ion in this foundation (Stage D will couple
    # to cooling-only slices explicitly). Cheaper per kWh.
    if thermal_storage_kwh > 0:
        for month, sids in slices_by_month.items():
            avail_per_slice = {
                sid: thermal_storage_kwh * max_dod * slice_costs[sid][2] / 24.0
                for sid in sids
            }
            deficit_sids = sorted(sids, key=lambda x: -slice_costs[x][0])
            surplus_sids = sorted(sids, key=lambda x: slice_costs[x][1])

            total_discharge = 0.0
            for sid in deficit_sids:
                need = deficit[sid]
                if need <= 0:
                    continue
                cap = avail_per_slice[sid]
                give = min(need, cap)
                by_slice[sid]["thermal_storage_discharge_kwh"] = give
                deficit[sid] = need - give
                total_discharge += give

            energy_to_charge = total_discharge / max(thermal_rt_eff, 1e-6)
            for sid in surplus_sids:
                have = surplus[sid]
                if have <= 0 or energy_to_charge <= 0:
                    continue
                cap = avail_per_slice[sid]
                take = min(have, cap, energy_to_charge)
                by_slice[sid]["thermal_storage_charge_kwh"] = take
                surplus[sid] = have - take
                energy_to_charge -= take

    # Pass 4: grid import covers remaining deficit; remaining surplus exports.
    # (A12): inflate the metered import by 1/ac_eff so that
    # `import * ac_eff` reaches the load; tariff is billed on the source
    # side (what the utility's meter sees). Export stays load-side per
    # the brief's literal scope (AC loss applied only to import / V2G /
    # battery_discharge).
    for sid in demand_kwh_by_slice:
        slice_hours = slice_costs[sid][2]
        # respect grid import / export power caps
        max_import_kwh = import_cap_kw * slice_hours
        max_export_kwh = export_cap_kw * slice_hours
        # (Phase 1A): grid_import pays ac_loss + PSPCL upstream
        # T&D. Effective delivery efficiency = ac_eff × pspcl_eff. Each
        # load-side kWh requires source = load / grid_import_eff.
        source_need = (deficit[sid] / grid_import_eff
                       if deficit[sid] > 0 else 0.0)
        by_slice[sid]["grid_import_kwh"] = min(source_need, max_import_kwh)
        by_slice[sid]["grid_export_kwh"] = min(surplus[sid], max_export_kwh)

    # Aggregate totals.
    pv_generation = sum(b["pv_kwh"] for b in by_slice.values())
    battery_throughput = sum(b["battery_discharge_kwh"] for b in by_slice.values())
    v2g_discharge = sum(b["v2g_discharge_kwh"] for b in by_slice.values())
    biomass_generation = sum(b["biomass_kwh"] for b in by_slice.values())
    wte_generation = sum(b["wte_kwh"] for b in by_slice.values())
    biogas_generation = sum(b["biogas_kwh"] for b in by_slice.values())
    thermal_discharge = sum(b["thermal_storage_discharge_kwh"] for b in by_slice.values())
    grid_import = sum(b["grid_import_kwh"] for b in by_slice.values())
    grid_export = sum(b["grid_export_kwh"] for b in by_slice.values())
    annual_demand = sum(b["demand_kwh"] for b in by_slice.values())

    # Solar-farm CAPEX premium for tracked PV (capex × 1.25)
    farm_annual_inr_per_kwp = (
        econ.tracked_pv_annualised_inr_per_kwp()
        if tracked_pv_active >= 0.5
        else econ.solar_farm_annualised_inr_per_kwp()
    )

    # Cost: annualised CAPEX + OPEX + tariff outflow - export revenue
    #         + V2G cycle degradation + biomass fuel + biomass CAPEX/OPEX.
    # Stage C round 3 (Claude 2): the rooftop multiplier folds in Allume
    # SolShare hardware premium (+10% × apartment_roof × uptake) and the
    # Sika+Zinco biosolar capex bump (Feature 4 below).
    cost = (
        econ.rooftop_pv_annualised_inr_per_kwp() * rooftop_kwp
        * rooftop_capex_multiplier
        + farm_annual_inr_per_kwp * farm_kwp
        + econ.battery_annualised_inr_per_kwh() * battery_kwh
        + econ.v2g_annualised_inr_per_unit() * v2g_units
        + econ.biomass_chp_annualised_inr_per_kw_e() * biomass_kw_e
        + biomass_generation * biomass_fuel_inr_per_kwh
        # Stage C round 2 additions
        + econ.wte_annualised_inr_per_kw_e() * wte_kw_e
        + wte_generation * wte_fuel_inr_per_kwh
        + econ.biogas_annualised_inr_per_kw_e() * biogas_kw_e
        + biogas_generation * biogas_fuel_inr_per_kwh
        + econ.thermal_storage_annualised_inr_per_kwh() * thermal_storage_kwh
        - grid_export * econ.export_tariff()
        + v2g_discharge * v2g_deg_inr_per_kwh
    )
    for sid, slice_data in by_slice.items():
        cost += slice_data["grid_import_kwh"] * econ.import_tariff(sid)

    emissions = (
        grid_import * emission_factor
        + biomass_generation * biomass_emission
        + wte_generation * wte_emission
        + biogas_generation * biogas_emission
    )

    # Stage C round 3: embodied carbon (annualised over each tech's lifetime).
    if econ.include_embodied_carbon():
        emb = econ.embodied_carbon()
        techs = econ.technologies
        emissions += econ.annualised_embodied_kgco2(
            emb.get("rooftop_pv_kgco2_per_kwp", 0), rooftop_kwp,
            int(techs["rooftop_pv"]["lifetime_years"]))
        farm_emb_per_kwp = emb.get("solar_farm_kgco2_per_kwp", 0)
        if tracked_pv_active >= 0.5:
            farm_emb_per_kwp += emb.get("tracked_pv_extra_kgco2_per_kwp", 0)
        emissions += econ.annualised_embodied_kgco2(
            farm_emb_per_kwp, farm_kwp,
            int(techs["solar_farm"]["lifetime_years"]))
        emissions += econ.annualised_embodied_kgco2(
            emb.get("li_ion_battery_kgco2_per_kwh", 0), battery_kwh,
            int(techs["li_ion_battery"]["lifetime_years"]))
        emissions += econ.annualised_embodied_kgco2(
            emb.get("v2g_charger_kgco2_per_unit", 0), v2g_units,
            int(techs["v2g_charger"]["lifetime_years"]))
        if biomass_kw_e > 0:
            emissions += econ.annualised_embodied_kgco2(
                emb.get("biomass_chp_kgco2_per_kw_e", 0), biomass_kw_e,
                int(techs["biomass_chp"]["lifetime_years"]))
        if wte_kw_e > 0:
            emissions += econ.annualised_embodied_kgco2(
                emb.get("wte_plant_kgco2_per_kw_e", 0), wte_kw_e,
                int(techs["wte_plant"]["lifetime_years"]))
        if biogas_kw_e > 0:
            emissions += econ.annualised_embodied_kgco2(
                emb.get("biogas_plant_kgco2_per_kw_e", 0), biogas_kw_e,
                int(techs["biogas_plant"]["lifetime_years"]))
        if thermal_storage_kwh > 0:
            emissions += econ.annualised_embodied_kgco2(
                emb.get("thermal_storage_kgco2_per_kwh", 0), thermal_storage_kwh,
                int(techs["thermal_cold_storage"]["lifetime_years"]))

    # Stage C round 3 (Claude 2): BIPV facade + solar carport CAPEX.
    if bipv_kwp > 0:
        cost += econ.bipv_annualised_inr_per_kwp() * bipv_kwp
    if carport_kwp > 0:
        cost += econ.carport_annualised_inr_per_kwp() * carport_kwp
    if floating_pv_kwp > 0:
        cost += econ.floating_pv_annualised_inr_per_kwp() * floating_pv_kwp

    # Stage C round 3 (Claude 2): DSR comfort cost.
    if dsr_active and dsr_shifted_kwh > 0:
        cost += dsr_shifted_kwh * econ.dsr_comfort_cost_inr_per_kwh()

    # Stage C round 3: reliability / diesel-displacement credit.
    # Each kWh of battery + V2G capacity covers some outage hours that
    # would otherwise burn diesel @ ~₹17/kWh + 0.27 kgCO2/kWh.
    rel_hours = econ.outage_hours_per_year()
    rel_cov = econ.reliability_coverage_fraction()
    diesel_inr = econ.diesel_displacement_value_inr_per_kwh()
    # Critical-load kWh covered = (battery_kwh + V2G capacity-kWh) × outage_hours × coverage / 24
    # Use a simple proxy: battery + V2G aggregate × outage_hours_yr × cov
    v2g_capacity_kwh = v2g_units * econ.v2g_kwh_per_unit_per_day()
    storage_kwh_outage_covered = (battery_kwh + v2g_capacity_kwh) * rel_hours * rel_cov / 24.0
    # SYMMETRIC DIESEL. Under the old branch the town received an
    # UNBOUNDED credit for storage while BAU was never charged for the diesel
    # it actually burns. Now every scenario pays for the critical outage load
    # it cannot cover, capped at the diesel it would really have burned.
    # Full rationale + arithmetic: economics.yaml reliability block.
    if econ.symmetric_diesel_backup_enabled():
        crit_outage_kwh = econ.critical_outage_energy_kwh(annual_demand)
        # CHP rides through the outage; storage alone understates coverage
        # badly: 100% critical served in 2030 with zero battery).
        chp_covered_kwh = ((biomass_kw_e + wte_kw_e + biogas_kw_e)
                           * rel_hours * econ.chp_outage_availability())
        diesel_backup_kwh = max(
            0.0,
            crit_outage_kwh - storage_kwh_outage_covered - chp_covered_kwh)
        reliability_credit_inr = 0.0
        cost += diesel_backup_kwh * diesel_inr
    else:
        diesel_backup_kwh = 0.0
        reliability_credit_inr = storage_kwh_outage_covered * diesel_inr
        cost -= reliability_credit_inr

    # Caveat-14 fix: 25-yr lifetime cost with tariff escalation
    # on the grid-flow portion only. The annualised CAPEX / OPEX / fuel
    # cashflows are locked at 2030-real INR (no real escalation), so the
    # lifetime sum for the non-grid portion is simply annual * lifetime.
    # The grid-import / grid-export portion escalates at
    # `tariff_escalation_real_annual` per year (default 2.5%/yr). Reporting
    # only - does not enter the optimisation objective.
    grid_import_annual_inr = sum(
        slice_data["grid_import_kwh"] * econ.import_tariff(sid)
        for sid, slice_data in by_slice.items()
    )
    grid_export_annual_inr = grid_export * econ.export_tariff()
    grid_net_annual_inr = grid_import_annual_inr - grid_export_annual_inr
    non_grid_annual_inr = cost - grid_net_annual_inr
    lifetime_yrs = int(econ.project_lifetime_years())
    # A21: tariff escalation now honours active price scenario.
    esc = float(econ.tariff_escalation_real_annual_value())
    if esc != 0.0 and lifetime_yrs > 0:
        # sum_{y=1..N} (1+esc)^y = (1+esc) * ((1+esc)^N - 1) / esc
        grid_lifetime_factor = (
            (1.0 + esc) * ((1.0 + esc) ** lifetime_yrs - 1.0) / esc
        )
    else:
        grid_lifetime_factor = float(lifetime_yrs)
    # (Phases 2A/2B/2C/2D/4 —:
    # multiplicative demand-growth factor on grid_net (population +
    # EV ramp + climate drift + cooking electrification + income
    # mobility). Returns 1.0 when district_composition.yaml
    # `lifetime_demand_trajectory.enabled: false`.
    lifetime_demand_growth = float(econ.lifetime_demand_growth_factor())
    lifetime_cost_inr = (
        non_grid_annual_inr * lifetime_yrs
        + grid_net_annual_inr * grid_lifetime_factor * lifetime_demand_growth
    )
    # (D2 —: PMSGY rooftop subsidy fades over
    # the 25-yr horizon (decay_linear_to_2040). The annual LP amortises
    # rooftop CAPEX at the 2030-snapshot subsidy (0.30); across the
    # lifetime the effective subsidy is ~0.078, so the rooftop-CAPEX
    # portion of the lifetime cost is uplifted by
    # (1-life_avg)/(1-snapshot). Annual cost is untouched. The uplift
    # factor is 1.0 (no-op) when pmsgy_continuation_scenario is absent.
    rooftop_annual_capex_inr = (
        econ.rooftop_pv_annualised_inr_per_kwp()
        * rooftop_kwp * rooftop_capex_multiplier
    )
    pmsgy_uplift = float(econ.pmsgy_lifetime_capex_uplift_factor())
    lifetime_cost_inr += (
        rooftop_annual_capex_inr * (pmsgy_uplift - 1.0) * lifetime_yrs
    )

    return DispatchResult(
        scenario="",  # filled by caller
        solver="",    # filled by caller
        capacities={
            "rooftop_pv_kwp": rooftop_kwp,
            "solar_farm_kwp": farm_kwp,
            "battery_kwh": battery_kwh,
            "v2g_units": v2g_units,
            "biomass_kw_e": biomass_kw_e,
            "tracked_pv_active": tracked_pv_active,
            "wte_kw_e": wte_kw_e,
            "biogas_kw_e": biogas_kw_e,
            "thermal_storage_kwh": thermal_storage_kwh,
            "bipv_kwp": bipv_kwp,                     # Stage C round 3 Claude 2
            "carport_kwp": carport_kwp,               # Stage C round 3 Claude 2
            "floating_pv_kwp": floating_pv_kwp,       # Stage C round 5
        },
        annual_cost_inr=cost,
        annual_emissions_kgco2=emissions,
        annual_demand_kwh=annual_demand,
        grid_import_kwh=grid_import,
        grid_export_kwh=grid_export,
        pv_generation_kwh=pv_generation,
        battery_throughput_kwh=battery_throughput,
        v2g_discharge_kwh=v2g_discharge,
        biomass_generation_kwh=biomass_generation,
        wte_generation_kwh=wte_generation,
        biogas_generation_kwh=biogas_generation,
        thermal_storage_throughput_kwh=thermal_discharge,
        dsr_shifted_kwh=dsr_shifted_kwh,
        lifetime_cost_inr=lifetime_cost_inr,
        by_slice=by_slice,
    )


def _coordinate_descent_size(
    net: EnergyNetwork,
    econ: Economics,
    scenario: Scenario,
    alpha: float = 0.0,
    n_steps: int = 9,
    n_passes: int = 4,
    warm_start: Optional[Dict[str, float]] = None,
) -> DispatchResult:
    """Coordinate-descent sizer over PV + battery + V2G + biomass (Stage C).

    Each pass golden-section searches each variable over its [0, cap]
    range. Deterministic; weighted objective (1-alpha)*cost + alpha*
    carbon_price*emissions monotonically non-increasing across passes.

    For tracked PV: a separate binary search at the end picks
    tracked_active ∈ {0, 1} if the scenario allows it.
    """
    caps = _capacity_caps(net, econ, scenario)
    carbon_price = econ.carbon_price_inr_per_kgco2()

    cur = {"rooftop_pv_kwp": 0.0, "solar_farm_kwp": 0.0,
            "battery_kwh": 0.0, "v2g_units": 0.0,
            "biomass_kw_e": 0.0, "tracked_pv_active": 0.0,
            "wte_kw_e": 0.0, "biogas_kw_e": 0.0,
            "thermal_storage_kwh": 0.0}
    if warm_start is not None:
        # Clamp warm-start values to current scenario caps (e.g. previous
        # alpha's biomass = 5000 but new scenario disallows biomass).
        for k in cur:
            cap = caps.get(k, 0.0)
            cur[k] = min(float(warm_start.get(k, 0.0)), cap)

    # Stage C round 3 (Claude 2) — propagate per-scenario flags into the
    # merit-order evaluator. Default OFF, so existing scenarios run unchanged.
    orientation_active = bool(
        getattr(scenario, "allow_panel_orientation_choice", False)
    )
    battery_coupling_mode = str(
        getattr(scenario, "battery_coupling_mode", "ac_traditional")
    )
    dsr_active = bool(getattr(scenario, "allow_dsr", False)) and econ.dsr_enabled()
    # Rooftop CAPEX / yield / demand multipliers fold Stage C round 3
    # features (Allume SolShare, Sika+Zinco biosolar). Default 1.0 = no
    # change when the corresponding scenario flags are OFF.
    rooftop_capex_multiplier = (
        econ.rooftop_pv_capex_multiplier_with_solshare(scenario)
        * econ.rooftop_pv_capex_multiplier_with_biosolar(scenario)
    )
    rooftop_yield_multiplier = (
        econ.rooftop_pv_yield_multiplier_with_biosolar(scenario)
    )
    demand_multiplier = econ.total_demand_multiplier_with_biosolar(scenario)
    # BIPV facade + solar carport capacity. Both binary: deployed at the
    # network's full potential when the scenario flag is set, zero otherwise.
    bipv_kwp = (
        net.total_bipv_potential_kwp(econ)
        if getattr(scenario, "allow_bipv", False) else 0.0
    )
    carport_kwp = (
        net.total_carport_potential_kwp(econ)
        if getattr(scenario, "allow_carport", False) else 0.0
    )
    # Stage C round 5: floating PV on BLUE_SPACE.
    floating_pv_kwp = (
        net.total_floating_pv_potential_kwp(econ)
        if getattr(scenario, "allow_floating_pv", False) else 0.0
    )

    def evaluate(state: Dict[str, float]) -> DispatchResult:
        return _merit_order_dispatch(
            net, econ,
            state["rooftop_pv_kwp"], state["solar_farm_kwp"],
            state["battery_kwh"], state["v2g_units"],
            biomass_kw_e=state["biomass_kw_e"],
            tracked_pv_active=state["tracked_pv_active"],
            wte_kw_e=state["wte_kw_e"],
            biogas_kw_e=state["biogas_kw_e"],
            thermal_storage_kwh=state["thermal_storage_kwh"],
            orientation_active=orientation_active,
            battery_coupling_mode=battery_coupling_mode,
            dsr_active=dsr_active,
            rooftop_capex_multiplier=rooftop_capex_multiplier,
            rooftop_yield_multiplier=rooftop_yield_multiplier,
            demand_multiplier=demand_multiplier,
            bipv_kwp=bipv_kwp,
            carport_kwp=carport_kwp,
            floating_pv_kwp=floating_pv_kwp,
        )

    def weighted_obj(r: DispatchResult) -> float:
        return ((1.0 - alpha) * r.annual_cost_inr
                + alpha * carbon_price * r.annual_emissions_kgco2)

    best = evaluate(cur)
    order = ["rooftop_pv_kwp", "solar_farm_kwp",
              "battery_kwh", "v2g_units", "biomass_kw_e",
              "wte_kw_e", "biogas_kw_e", "thermal_storage_kwh"]
    eps = 1.0  # absolute INR improvement threshold for early-exit

    for _ in range(n_passes):
        improved = False
        for var in order:
            ub = caps[var]
            if ub <= 0:
                continue
            grid_xs = [ub * i / (n_steps - 1) for i in range(n_steps)]
            best_x = cur[var]
            best_obj = weighted_obj(best)
            for x in grid_xs:
                trial = dict(cur)
                trial[var] = x
                r = evaluate(trial)
                obj = weighted_obj(r)
                if obj < best_obj - eps:
                    best_obj = obj
                    best_x = x
            if best_x != cur[var]:
                cur[var] = best_x
                best = evaluate(cur)
                improved = True

        # Tracked-PV binary search (only if allowed by scenario)
        if caps["tracked_pv_active"] > 0:
            best_obj = weighted_obj(best)
            for active in (0.0, 1.0):
                trial = dict(cur)
                trial["tracked_pv_active"] = active
                r = evaluate(trial)
                obj = weighted_obj(r)
                if obj < best_obj - eps:
                    best_obj = obj
                    cur["tracked_pv_active"] = active
                    best = evaluate(cur)
                    improved = True

        if not improved:
            break

    best.alpha = alpha
    return best


def solve_dispatch_fallback(
    net: EnergyNetwork,
    econ: Economics,
    scenario_name: str = "pv_battery_v2g",
    alpha: float = 0.0,
    warm_start: Optional[Dict[str, float]] = None,
) -> DispatchResult:
    """Run the pure-Python merit-order dispatcher + coordinate-descent
    sizer. Always available; stdlib-only.

    B21 NOTE: the buy-side green open-access purchase is NOT
    modelled in this heuristic path (deprecated, non-production - the FX-11
    README note family). Both Pyomo builders carry it; production always
    solves via Pyomo.

    Parameters
    ----------
    alpha : float, default 0.0
        Stage C carbon weight in [0, 1]. 0 = pure cost; 1 = pure carbon.

    Returns
    -------
    DispatchResult
        Best solution found by the heuristic.
    """
    scenario = econ.scenario(scenario_name)
    # SOLAR WATER HEATING IS NOT MODELLED HERE, AND SILENCE WOULD BE THE BUG.
    # This heuristic has no collector, no tank and no water-heating leg, so it
    # would return a number that looks like a full-stack answer while quietly
    # omitting a technology the scenario asked for - and its own docstring
    # already warns it is "NOT number-compatible" with the Pyomo builders.
    # Refuse loudly rather than under-report. Production always solves via
    # Pyomo, so this can only fire on a deliberate fallback call.
    if (econ.solar_thermal_enabled()
            and bool(getattr(scenario, "allow_solar_thermal", False))):
        raise NotImplementedError(
            "solar thermal is enabled for scenario %r but the merit-order "
            "fallback does not model it (no collector, no tank, no DHW leg). "
            "Solve via Pyomo, or switch allow_solar_thermal off for this "
            "run - do not compare a fallback number against a Pyomo one."
            % scenario_name
        )
    result = _coordinate_descent_size(net, econ, scenario, alpha=alpha,
                                        warm_start=warm_start)
    result.scenario = scenario_name
    result.solver = "fallback:merit_order_coord_descent"
    result.alpha = alpha
    return result


# ---------------------------------------------------------------------------
# Pyomo MILP path.
# ---------------------------------------------------------------------------
def _build_pyomo_model(net: EnergyNetwork, econ: Economics,
                       scenario: Scenario,
                       alpha: float = 0.0):  # pragma: no cover
    """Build the Stage C Pyomo MILP.

 supervisor refactor: extended from the Stage B
    foundation (PV / battery / V2G / grid only) to the full Stage C
    technology stack. The MILP now models:

      Capacity decisions (continuous, bounded by scenario caps):
        rooftop_kwp, farm_fixed_kwp, farm_tracked_kwp, battery_kwh,
        v2g_units, biomass_kw_e, wte_kw_e, biogas_kw_e,
        thermal_storage_kwh, bipv_kwp, carport_kwp, floating_pv_kwp.

      Per-slice flows (continuous, non-negative):
        imp, exp, charge, discharge, v2g, biomass_kwh, wte_kwh,
        biogas_kwh, thermal_charge, thermal_discharge.

      Objective:
        (1-alpha)*cost + alpha*carbon_price*emissions
        - cost includes CAPEX annuities (with SolShare/biosolar premiums),
          fuel costs, grid tariff in/out, V2G degradation, BIPV/carport/
          floating-PV CAPEX, reliability credit (negative); WTE marginal
          uses the effective fuel cost = fuel - landfill credit.
        - emissions = grid import * EF + biomass/WTE/biogas operational +
          embodied carbon (if `include_embodied_carbon`).

    Scenario flag mapping (LP-only, no binaries):
      allow_tracked_pv -> farm_tracked_kwp upper bound > 0
      allow_biomass_chp -> biomass_kw_e cap > 0
      allow_wte -> wte_kw_e cap > 0
      allow_biogas -> biogas_kw_e cap > 0
      allow_thermal_storage -> thermal_storage_kwh cap > 0
      allow_bipv -> bipv_kwp cap > 0
      allow_carport -> carport_kwp cap > 0
      allow_floating_pv -> floating_pv_kwp cap > 0
      allow_solshare -> rooftop CAPEX premium multiplier
      allow_biosolar -> rooftop yield + cooling demand + CAPEX multipliers
      battery_coupling_mode -> battery round-trip efficiency (ac 0.90 / dc 0.94)
      allow_dsr -> dsr_reduce/dsr_add vars + monthly conservation + comfort cost (in Pyomo since)
      allow_panel_orientation_choice -> uses pv_yield_per_kwp_kwh_oriented

    Returns the model + helper data needed by `solve_dispatch_pyomo`.
    """
    if not _HAS_PYOMO:
        raise RuntimeError("pyomo is not installed in this environment")

    m = pyo.ConcreteModel()

    # ---- Sets + per-slice data -----------------------------------------
    slice_ids = [s.id for s in econ.slices]
    months_set = sorted({s.month for s in econ.slices})
    m.S = pyo.Set(initialize=slice_ids, ordered=True)
    m.MONTHS = pyo.Set(initialize=months_set, ordered=True)
    month_of = {s.id: s.month for s in econ.slices}
    hours_of = {s.id: s.hours_per_year for s in econ.slices}
    days_per_month = {mm: econ.calendar.get(mm, {}).get("days", 30)
                       for mm in months_set}
    # FX-1: DSR + storage conservation tightened from
    # per-MONTH to per-(month, day-type) buckets - a weekday-evening shave can
    # no longer reappear on a weekend night (the 3am-spike root). Zero-hour
    # slices (festival dayparts in festival-less months) are excluded. In
    # 144-slice mode day_type is "mixed" so buckets reduce to months (legacy).
    daytype_of = {s.id: getattr(s, "day_type", "mixed") for s in econ.slices}
    bucket_keys = sorted({(month_of[sid], daytype_of[sid]) for sid in slice_ids
                          if hours_of[sid] > 0})
    bucket_slices = {bk: [sid for sid in slice_ids
                          if (month_of[sid], daytype_of[sid]) == bk
                          and hours_of[sid] > 0]
                     for bk in bucket_keys}
    bucket_hours = {bk: sum(hours_of[sid] for sid in bucket_slices[bk])
                    for bk in bucket_keys}
    m.BUCKETS = pyo.Set(initialize=bucket_keys, dimen=2)

    # PV yield builders (already shading-multiplier-aware in network.py).
    orientation_active = bool(getattr(scenario, "allow_panel_orientation_choice", False))
    yield_rooftop_base = net.pv_yield_per_kwp_kwh(econ)
    if orientation_active:
        yield_rooftop = net.pv_yield_per_kwp_kwh_oriented(econ)
    else:
        yield_rooftop = yield_rooftop_base
    yield_farm = net.pv_yield_per_kwp_kwh_solar_farm(econ)
    demand_kwh = net.demand_by_slice_kwh(econ)

    # Scenario-derived yield / CAPEX multipliers for rooftop PV.
    rooftop_capex_mult = (
        econ.rooftop_pv_capex_multiplier_with_solshare(scenario)
        * econ.rooftop_pv_capex_multiplier_with_biosolar(scenario)
    )
    rooftop_yield_mult = econ.rooftop_pv_yield_multiplier_with_biosolar(scenario)
    demand_mult = econ.total_demand_multiplier_with_biosolar(scenario)

    # Battery rt_eff depends on coupling mode (dc_native = 0.94, ac = 0.90).
    coupling_mode = str(getattr(scenario, "battery_coupling_mode", "ac_traditional"))
    # net of the plant's own auxiliary load (CERC RTE x (1-AEC)).
    rt_eff = econ.battery_rte_net_of_aux_for(coupling_mode)
    max_dod = econ.battery_max_dod()

    # (A12): AC-bus delivery efficiency, applied to grid
    # import + V2G discharge + battery discharge in the per-slice power
    # balance. Source-side variables stay unchanged; the AC sources
    # contribute `ac_eff * source` to load. PV (already DC-lossy) and
    # local dispatchable plants (biomass / WTE / biogas / thermal) sit
    # on the same bus as the load per the brief, so they are unaffected.
    ac_eff_pyo = max(1e-6, 1.0 - econ.ac_loss_fraction())
    # (Phase 1A —: PSPCL UPSTREAM
    # T&D applies to grid_import (m.imp[s]) only. Combined grid-delivery
    # efficiency = ac_eff × pspcl_eff. V2G + battery + biomass + WTE +
    # biogas + thermal remain ON the district bus (ac_eff only).
    pspcl_eff_pyo = max(1e-6, 1.0 - econ.pspcl_grid_loss_fraction())
    grid_import_eff_pyo = ac_eff_pyo * pspcl_eff_pyo

    # V2G + grid params.
    v2g_kwh_per_unit_per_day = econ.v2g_kwh_per_unit_per_day()
    v2g_power_kw = econ.v2g_power_kw_per_unit()
    v2g_deg = econ.v2g_cycle_degradation_inr_per_kwh()
    import_cap_kw = econ.import_capacity_limit_kw()
    export_cap_kw = econ.export_capacity_limit_kw()

    # Stage C dispatchable plant params.
    biomass_fuel = econ.biomass_fuel_cost_inr_per_kwh()
    biomass_emiss = econ.biomass_emission_factor_kgco2_per_kwh()
    biomass_hours_yr = econ.biomass_operating_hours_per_year()
    # FX-6 / N7+: straw-supply realism. Per-slice fuel cost
    # (storage economics by month), per-month availability ceiling
    # (pre-harvest trough + monsoon handling), annual straw-energy budget.
    # All three default to no-ops when the YAML keys are absent.
    bm_month_of = {s.id: s.month for s in econ.slices}
    biomass_fuel_by_slice = {
        sid: biomass_fuel * econ.biomass_monthly_fuel_cost_multiplier(mm)
        for sid, mm in bm_month_of.items()
    }
    biomass_constrained_months = [
        mm for mm in MONTHS
        if econ.biomass_monthly_availability_fraction(mm) < 1.0 - 1e-12
    ]
    biomass_straw_cap_kwh = econ.biomass_annual_straw_energy_cap_kwh()
    wte_fuel = econ.wte_effective_fuel_cost_inr_per_kwh()  # negative w/ landfill credit
    wte_emiss = econ.wte_emission_factor_kgco2_per_kwh()
    wte_hours_yr = econ.wte_operating_hours_per_year()
    biogas_fuel = econ.biogas_fuel_cost_inr_per_kwh()
    biogas_emiss = econ.biogas_emission_factor_kgco2_per_kwh()
    biogas_hours_yr = econ.biogas_operating_hours_per_year()
    thermal_rt_eff = econ.thermal_storage_round_trip_efficiency()

    # Stage C PV add-on yield multipliers.
    bipv_yield_mult = econ.bipv_yield_multiplier_vs_rooftop()
    fpv_yield_mult = econ.floating_pv_yield_multiplier_vs_ground_mount()
    tracked_yield_mult = econ.tracked_pv_yield_multiplier()  # ~1.18

    # Capacity caps (already gated by scenario flags).
    caps = _capacity_caps(net, econ, scenario)
    bipv_cap = (net.total_bipv_potential_kwp(econ)
                if getattr(scenario, "allow_bipv", False) else 0.0)
    carport_cap = (net.total_carport_potential_kwp(econ)
                    if getattr(scenario, "allow_carport", False) else 0.0)
    fpv_cap = (net.total_floating_pv_potential_kwp(econ)
                if getattr(scenario, "allow_floating_pv", False) else 0.0)
    tracked_cap = (caps["solar_farm_kwp"]
                    if getattr(scenario, "allow_tracked_pv", False) else 0.0)

    # DSR (demand-side response) - supervisor follow-up.
    # When allow_dsr is on, the LP gets per-slice load-shift variables:
    # dsr_reduce[s] for peak/super-peak slices, dsr_add[s] for non-peak.
    # Conservation per month (no creation/destruction). Comfort cost per
    # kWh shifted enters the objective. Mirrors the fallback's
    # `_apply_dsr_shift` semantics but lets the LP pick where to add
    # (the heuristic spreads evenly within a window; the LP picks
    # optimally).
    dsr_enabled = (getattr(scenario, "allow_dsr", False) and econ.dsr_enabled())
    if dsr_enabled:
        dsr_fraction = econ.dsr_aggregate_shiftable_fraction()
        dsr_comfort = econ.dsr_comfort_cost_inr_per_kwh()
    else:
        dsr_fraction = 0.0
        dsr_comfort = 0.0
    # Slices classified by tariff band.
    peak_slice_ids = [s.id for s in econ.slices
                       if s.tariff_band in ("peak", "super_peak")]
    nonpeak_slice_ids = [s.id for s in econ.slices
                          if s.tariff_band not in ("peak", "super_peak")]

    # ---- Capacity variables --------------------------------------------
    # (A18 LP module-mix decision variable, Claude 2):
    # Replace the single `m.rooftop_kwp` Var with 3 module-type Vars
    # (mono_perc / poly_si / thin_film_cdte) plus a Pyomo Expression that
    # sums them. The LP can now pick the share of each module type the
    # district deploys, subject to the same total deployable cap.
    # `economics.yaml:technologies.rooftop_pv.module_types[*].capex_inr_per_kwp`
    # provides per-type CAPEX (mono 38k, poly 32k, thin-film 28k);
    # `Economics.rooftop_pv_module_annualised_inr_per_kwp` provides the
    # annualised cost. When `module_types` is absent (legacy fixtures),
    # falls back to the single-variable path.
    _module_types_a18 = econ.rooftop_pv_module_types()
    # from the single-period builder. The documented share caps
    # (rooftop_pv_module_share) were never wired, yields are module-identical,
    # so the LP provably loaded 100% thin-film (28k) - flattering the
    # single-period pin ~2% vs the multi-period headline's 35.5k share-blend
    # basis and contaminating the quoted single-vs-multi delta. Single now
    # prices rooftop exactly like multi: the ownership-blended, share-blended
    # aggregate (rooftop_pv_annualised_inr_per_kwp). module_types stays in the
    # YAML as calibrated market data for the thesis; the retired Var code below
    # is kept for the git history one release and never activates.
    _a18_active = False
    if _a18_active:
        m.rooftop_kwp_mono = pyo.Var(
            bounds=(0.0, caps["rooftop_pv_kwp"])) \
            if "mono_perc" in _module_types_a18 else None
        m.rooftop_kwp_poly = pyo.Var(
            bounds=(0.0, caps["rooftop_pv_kwp"])) \
            if "poly_si" in _module_types_a18 else None
        m.rooftop_kwp_thinfilm = pyo.Var(
            bounds=(0.0, caps["rooftop_pv_kwp"])) \
            if "thin_film_cdte" in _module_types_a18 else None
        # Total rooftop_kwp expression: sum of present module variables.
        _present_module_vars = [
            v for v in (
                getattr(m, "rooftop_kwp_mono", None),
                getattr(m, "rooftop_kwp_poly", None),
                getattr(m, "rooftop_kwp_thinfilm", None),
            ) if v is not None
        ]
        m.rooftop_kwp = pyo.Expression(
            expr=sum(_present_module_vars))
        # Joint cap on total rooftop deployment.
        def _rooftop_total_cap(m):
            return m.rooftop_kwp <= caps["rooftop_pv_kwp"]
        m.rooftop_total_cap = pyo.Constraint(rule=_rooftop_total_cap)
    else:
        m.rooftop_kwp = pyo.Var(bounds=(0.0, caps["rooftop_pv_kwp"]))
    # Split farm into fixed + tracked so the +18% yield only applies to tracked.
    # CRIT-2b /: tracked rows need wider pitch, so 1 kWp of
    # tracked consumes `farm_land_ratio` kWp-equivalents of the area-derived
    # cap (GCR 0.45 fixed vs ~0.34 SAT -> 1.33; citations in economics.yaml).
    # ratio 1.0 (key absent) reproduces the legacy shared-density behaviour.
    # NOTE: the non-production heuristic fallback keeps its binary
    # tracked-at-full-cap treatment and ignores the ratio (FX-11 family).
    farm_land_ratio = econ.tracked_pv_land_ratio_vs_fixed()
    #: the SINGLE-PERIOD builder must see the same 2030
    # farm LAND as the multi-period builder's 2030 slice. It did not.
    # The multi builder caps the farm at
    #     caps["solar_farm_kwp"] * pv_density_mult[p] * farm_land[p]
    # while this one used the bare `caps["solar_farm_kwp"]`, i.e. the raw
    # 201-cell / 143,514 kWp base with NO land multiplier. That was harmless
    # while the layout's expansion tags only unlocked land in 2042/2055
    # (2030 multiplier was 1.0 by construction) - but released the
    # whole reserve INTO 2030, so the two builders silently disagreed about
    # the base year: multi saw 301 ha, single saw 201 ha, while BOTH paid
    # rent on 301 ha. Single-period is a 2030 model, so it takes the 2030
    # multipliers. Untagged/pre-B18 layouts still give 1.0 x 1.0, so every
    # historical single-period baseline stays byte-exact.
    from energy.network import phased_land_multipliers as _plm
    _sp_land = float(_plm(
        getattr(net, "grid", None))["solar_farm"].get(2030, 1.0))
    _sp_dens = float(econ.pv_density_ceiling_multiplier(2030))
    _sp_farm_cap = caps["solar_farm_kwp"] * _sp_dens * _sp_land
    m.farm_fixed_kwp = pyo.Var(bounds=(0.0, _sp_farm_cap))
    m.farm_tracked_kwp = pyo.Var(
        bounds=(0.0, tracked_cap * _sp_dens * _sp_land / farm_land_ratio))
    m.battery_kwh = pyo.Var(bounds=(0.0, caps["battery_kwh"]))
    m.v2g_units = pyo.Var(bounds=(0.0, caps["v2g_units"]))
    m.biomass_kw_e = pyo.Var(bounds=(0.0, caps["biomass_kw_e"]))
    m.wte_kw_e = pyo.Var(bounds=(0.0, caps["wte_kw_e"]))
    m.biogas_kw_e = pyo.Var(bounds=(0.0, caps["biogas_kw_e"]))
    m.thermal_storage_kwh = pyo.Var(bounds=(0.0, caps["thermal_storage_kwh"]))
    m.bipv_kwp = pyo.Var(bounds=(0.0, bipv_cap))
    m.carport_kwp = pyo.Var(bounds=(0.0, carport_cap))
    m.floating_pv_kwp = pyo.Var(bounds=(0.0, fpv_cap))

    # Total farm LAND for the joint farm-cap constraint (fixed-equivalent
    # kWp; tracked weighted by its land ratio - CRIT-2b /.
    def _farm_total(m):
        #: same 2030 land x density ceiling as the Var
        # bounds above - previously the bare caps["solar_farm_kwp"].
        return (m.farm_fixed_kwp + farm_land_ratio * m.farm_tracked_kwp
                <= _sp_farm_cap)
    m.farm_total_cap = pyo.Constraint(rule=_farm_total)

    # ---- Per-slice flow variables --------------------------------------
    m.imp = pyo.Var(m.S, bounds=(0.0, None))
    m.exp = pyo.Var(m.S, bounds=(0.0, None))
    m.charge = pyo.Var(m.S, bounds=(0.0, None))
    m.discharge = pyo.Var(m.S, bounds=(0.0, None))
    m.v2g = pyo.Var(m.S, bounds=(0.0, None))
    m.biomass = pyo.Var(m.S, bounds=(0.0, None))
    m.wte = pyo.Var(m.S, bounds=(0.0, None))
    m.biogas = pyo.Var(m.S, bounds=(0.0, None))
    m.thermal_chg = pyo.Var(m.S, bounds=(0.0, None))
    m.thermal_dis = pyo.Var(m.S, bounds=(0.0, None))

    # DSR per-slice shift variables. dsr_reduce defined only on peak slices
    # (capped at fraction*demand), dsr_add defined only on non-peak slices.
    # When dsr_enabled is False all bounds are 0.
    def _reduce_bound(m, s):
        if dsr_enabled and s in peak_slice_ids:
            return (0.0, dsr_fraction * demand_kwh[s] * demand_mult)
        return (0.0, 0.0)
    # FX-1/: dsr_add capped per slice (was unbounded - the
    # 3am-spike root) + zero-hour slices excluded.
    def _add_bound(m, s):
        if dsr_enabled and s in nonpeak_slice_ids and hours_of[s] > 0:
            return (0.0, dsr_fraction * demand_kwh[s] * demand_mult)
        return (0.0, 0.0)
    m.dsr_reduce = pyo.Var(m.S, bounds=_reduce_bound)
    m.dsr_add = pyo.Var(m.S, bounds=_add_bound)

    # FX-1/: conservation per (month, day-type) bucket (was per month) -
    # a weekday shave can no longer land on a weekend night.
    def _dsr_bucket(m, mm, dt):
        sids = bucket_slices[(mm, dt)]
        return (sum(m.dsr_reduce[s] for s in sids)
                == sum(m.dsr_add[s] for s in sids))
    m.dsr_bucket = pyo.Constraint(m.BUCKETS, rule=_dsr_bucket)

    # ---- REV-2: EV SMART CHARGING -------------------------
    # Managed charging reschedules a bounded share of EV energy WITHIN each
    # class's plug-in window (residential overnight / workplace workday =
    # the support of the cited charging daypart shapes, so bounds are 0
    # outside the window by construction). Same machinery as the FX-1 DSR
    # buckets: shift-out/shift-in pairs conserved per (month, day-type)
    # bucket AND per class - evening EV load can move to cheap night/solar
    # hours of the SAME day type, never across classes or day types. The
    # per-slice in-bound f x base is the-class anti-spike guard
    # (post-shift EV load <= (1+f) x dumb-charging load in any slice).
    smart_ev_on = (getattr(scenario, "allow_ev_smart_charging", False)
                   and econ.ev_smart_charging_enabled())
    EV_CLASSES = ("residential", "workplace")
    if smart_ev_on:
        ev_class_kwh = net.ev_charging_kwh_by_slice_by_class(econ, year=None)
        ev_shift_frac = {c: econ.ev_shiftable_fraction(c) for c in EV_CLASSES}
        ev_program_cost = econ.ev_smart_charging_cost_inr_per_kwh()
    else:
        ev_class_kwh = {c: {} for c in EV_CLASSES}
        ev_shift_frac = {c: 0.0 for c in EV_CLASSES}
        ev_program_cost = 0.0
    m.EVC = pyo.Set(initialize=EV_CLASSES, ordered=True)

    def _ev_shift_bound(m, c, s):
        if not smart_ev_on or hours_of[s] <= 0:
            return (0.0, 0.0)
        base = ev_class_kwh[c].get(s, 0.0)
        if base <= 0.0:
            return (0.0, 0.0)
        return (0.0, ev_shift_frac[c] * base * demand_mult)
    m.ev_shift_out = pyo.Var(m.EVC, m.S, bounds=_ev_shift_bound)
    m.ev_shift_in = pyo.Var(m.EVC, m.S, bounds=_ev_shift_bound)

    def _ev_shift_bucket(m, c, mm, dt):
        sids = bucket_slices[(mm, dt)]
        if not smart_ev_on:
            return pyo.Constraint.Skip
        return (sum(m.ev_shift_out[c, s] for s in sids)
                == sum(m.ev_shift_in[c, s] for s in sids))
    m.ev_shift_bucket = pyo.Constraint(m.EVC, m.BUCKETS,
                                       rule=_ev_shift_bucket)

    # ---- Per-slice power balance ---------------------------------------
    # Energy in = Energy out. PV is built from 5 surfaces (rooftop, farm
    # fixed, farm tracked, BIPV, carport, floating). Rooftop yield carries
    # the biosolar multiplier; farm/carport/floating use ground-mount yield
    # (with floating's +4% water-cooling bonus). BIPV uses the base rooftop
    # yield curve at 60%. Tracked PV uses +18% on the ground-mount yield.
    def _sp_pv_supply(m, s):
        return (
            yield_rooftop[s] * rooftop_yield_mult * m.rooftop_kwp
            + yield_farm[s] * m.farm_fixed_kwp
            + yield_farm[s] * tracked_yield_mult * m.farm_tracked_kwp
            + yield_rooftop_base[s] * bipv_yield_mult * m.bipv_kwp
            + yield_farm[s] * m.carport_kwp
            + yield_farm[s] * fpv_yield_mult * m.floating_pv_kwp
        )

    # FX-1/: explicit PV curtailment (the balance was an
    # equality with no spill - see the multi-period builder note).
    m.pv_curtail = pyo.Var(m.S, bounds=(0.0, None))
    m.pv_curtail_cap = pyo.Constraint(
        m.S, rule=lambda m, s: m.pv_curtail[s] <= _sp_pv_supply(m, s))

    # B21: buy-side green open-access purchase, single-period
    # form (2030 grant year). Same gating/pricing/shape conventions as the
    # multi-period builder - see the block there for the full note. Giving
    # the 2030-only model the buy option honestly evolves.3 (it can now
    # BUY external green instead of waiting for land grants it cannot see).
    _gp_on_sp = (econ.green_purchase_enabled()
                 and bool(getattr(scenario, "allow_green_purchase", False)))
    if _gp_on_sp:
        _gp_price_sp = econ.green_purchase_delivered_price_inr_per_kwh()
        _gp_admin_sp = econ.green_purchase_annual_admin_inr()
        m.gp_mw = pyo.Var(
            bounds=(0.0, econ.green_purchase_contracted_mw_max()))
        m.gp = pyo.Var(m.S, bounds=(0.0, None))
        m.gp_shape = pyo.Constraint(
            m.S, rule=lambda m, s: (m.gp[s] <= m.gp_mw * 1000.0
                                    * yield_farm[s] * tracked_yield_mult))
    else:
        _gp_price_sp = 0.0
        _gp_admin_sp = 0.0

    def _balance(m, s):
        # FIX removed the spurious math.sqrt(rt_eff) on discharge.
        # The bucket constraint already enforces sum(discharge) <= rt_eff *
        # sum(charge), so any rt_eff factor on the slice-level balance double-
        # counts the round-trip loss.
        # REV-2: managed-EV charge-shift terms (0-bounded
        # no-ops when smart charging is off).
        effective_demand = (demand_kwh[s] * demand_mult
                             - m.dsr_reduce[s] + m.dsr_add[s]
                             - sum(m.ev_shift_out[c, s] for c in EV_CLASSES)
                             + sum(m.ev_shift_in[c, s] for c in EV_CLASSES))
        # (A12) + FX-1/Q-1: imports pay ac_eff x
        # pspcl_eff; ALL local-bus sources (battery discharge, V2G, biomass,
        # WTE, biogas, thermal discharge) pay ac_eff - the code now matches
        # the documented intent (Q-1: biomass/WTE/biogas/thermal were at 1.0).
        # PV remains at 1.0 (generated at/behind the load; documented choice).
        return (
            effective_demand + m.charge[s] + m.thermal_chg[s] + m.exp[s]
            == _sp_pv_supply(m, s) - m.pv_curtail[s]
                 + ac_eff_pyo * m.discharge[s] + ac_eff_pyo * m.thermal_dis[s]
                 + ac_eff_pyo * m.v2g[s] + ac_eff_pyo * m.biomass[s]
                 + ac_eff_pyo * m.wte[s] + ac_eff_pyo * m.biogas[s]
                 + grid_import_eff_pyo * m.imp[s]
                 # B21: green purchase enters DELIVERED (see multi builder).
                 + (m.gp[s] if _gp_on_sp else 0.0)
        )
    m.balance = pyo.Constraint(m.S, rule=_balance)

    # ---- Battery cycling -----------------------------------------------
    # FX-1/: real C-rate power caps replace the hours/24
    # throughput proxy (~C/27); see the multi-period builder note.
    batt_c_rate_sp = econ.battery_c_rate_per_hour()
    thermal_c_rate_sp = econ.thermal_storage_c_rate_per_hour()
    def _batt_chg_power(m, s):
        return m.charge[s] <= m.battery_kwh * batt_c_rate_sp * hours_of[s]
    m.batt_chg_power = pyo.Constraint(m.S, rule=_batt_chg_power)
    def _batt_dis_power(m, s):
        return m.discharge[s] <= m.battery_kwh * batt_c_rate_sp * hours_of[s]
    m.batt_dis_power = pyo.Constraint(m.S, rule=_batt_dis_power)
    def _batt_bucket_cycles(m, mm, dt):
        return (sum(m.discharge[s] for s in bucket_slices[(mm, dt)])
                <= m.battery_kwh * max_dod * bucket_hours[(mm, dt)] / 24.0)
    m.batt_bucket_cycles = pyo.Constraint(m.BUCKETS, rule=_batt_bucket_cycles)

    def _batt_bucket_conserve(m, mm, dt):
        sids = bucket_slices[(mm, dt)]
        return (sum(m.discharge[s] for s in sids)
                <= rt_eff * sum(m.charge[s] for s in sids))
    m.batt_bucket_conserve = pyo.Constraint(m.BUCKETS, rule=_batt_bucket_conserve)

    # ---- Thermal storage cycling (cooling-specific battery analogue) ---
    # FX-1/: C-rate power caps + per-(month, day-type) conservation/cycles.
    def _thermal_chg_power(m, s):
        return m.thermal_chg[s] <= m.thermal_storage_kwh * thermal_c_rate_sp * hours_of[s]
    m.thermal_chg_power = pyo.Constraint(m.S, rule=_thermal_chg_power)
    def _thermal_dis_power(m, s):
        return m.thermal_dis[s] <= m.thermal_storage_kwh * thermal_c_rate_sp * hours_of[s]
    m.thermal_dis_power = pyo.Constraint(m.S, rule=_thermal_dis_power)
    def _thermal_bucket_conserve(m, mm, dt):
        sids = bucket_slices[(mm, dt)]
        return (sum(m.thermal_dis[s] for s in sids)
                <= thermal_rt_eff * sum(m.thermal_chg[s] for s in sids))
    m.thermal_bucket_conserve = pyo.Constraint(m.BUCKETS, rule=_thermal_bucket_conserve)
    def _thermal_bucket_cycles(m, mm, dt):
        return (sum(m.thermal_dis[s] for s in bucket_slices[(mm, dt)])
                <= m.thermal_storage_kwh * max_dod * bucket_hours[(mm, dt)] / 24.0)
    m.thermal_bucket_cycles = pyo.Constraint(m.BUCKETS, rule=_thermal_bucket_cycles)

    # ---- V2G constraints -----------------------------------------------
    # FX-1/: energy budget per (month, day-type) bucket (was monthly).
    def _v2g_bucket(m, mm, dt):
        sids = bucket_slices[(mm, dt)]
        return (sum(m.v2g[s] for s in sids)
                <= (bucket_hours[(mm, dt)] / 24.0) * v2g_kwh_per_unit_per_day
                   * m.v2g_units)
    m.v2g_bucket = pyo.Constraint(m.BUCKETS, rule=_v2g_bucket)

    def _v2g_slice_power(m, s):
        return m.v2g[s] <= v2g_power_kw * m.v2g_units * hours_of[s]
    m.v2g_slice_power = pyo.Constraint(m.S, rule=_v2g_slice_power)

    # ---- Dispatchable plant constraints (biomass / WTE / biogas) --------
    def _biomass_slice(m, s):
        return m.biomass[s] <= m.biomass_kw_e * hours_of[s]
    m.biomass_slice = pyo.Constraint(m.S, rule=_biomass_slice)

    def _biomass_annual(m):
        return sum(m.biomass[s] for s in slice_ids) <= m.biomass_kw_e * biomass_hours_yr
    m.biomass_annual = pyo.Constraint(rule=_biomass_annual)

    # FX-6 /: per-month availability ceiling (only months with
    # fraction < 1.0 get a row; the per-slice cap covers the rest).
    if biomass_constrained_months:
        def _biomass_monthly(m, mm):
            sids = [s for s in slice_ids if bm_month_of[s] == mm]
            hrs = sum(hours_of[s] for s in sids)
            frac = econ.biomass_monthly_availability_fraction(mm)
            return (sum(m.biomass[s] for s in sids)
                    <= frac * m.biomass_kw_e * hrs)
        m.biomass_monthly = pyo.Constraint(biomass_constrained_months,
                                            rule=_biomass_monthly)
    # FX-6 / N7: annual straw-energy budget (district catchment tonnage).
    if biomass_straw_cap_kwh is not None:
        m.biomass_straw_annual = pyo.Constraint(
            expr=sum(m.biomass[s] for s in slice_ids)
                 <= biomass_straw_cap_kwh)

    def _wte_slice(m, s):
        return m.wte[s] <= m.wte_kw_e * hours_of[s]
    m.wte_slice = pyo.Constraint(m.S, rule=_wte_slice)

    def _wte_annual(m):
        return sum(m.wte[s] for s in slice_ids) <= m.wte_kw_e * wte_hours_yr
    m.wte_annual = pyo.Constraint(rule=_wte_annual)

    def _biogas_slice(m, s):
        return m.biogas[s] <= m.biogas_kw_e * hours_of[s]
    m.biogas_slice = pyo.Constraint(m.S, rule=_biogas_slice)

    def _biogas_annual(m):
        return sum(m.biogas[s] for s in slice_ids) <= m.biogas_kw_e * biogas_hours_yr
    m.biogas_annual = pyo.Constraint(rule=_biogas_annual)

    # ---- Grid I/O caps -------------------------------------------------
    def _imp_cap(m, s):
        return m.imp[s] <= import_cap_kw * hours_of[s]
    def _exp_cap(m, s):
        return m.exp[s] <= export_cap_kw * hours_of[s]
    m.imp_cap = pyo.Constraint(m.S, rule=_imp_cap)
    if _gp_on_sp:
        # B21 shared physical import ceiling (see multi-period note).
        m.gp_shared_import_cap = pyo.Constraint(
            m.S, rule=lambda m, s: (m.imp[s] + m.gp[s]
                                    <= import_cap_kw * hours_of[s]))
    m.exp_cap = pyo.Constraint(m.S, rule=_exp_cap)

    # ---- Cost expression -----------------------------------------------
    # CAPEX annuities. Rooftop multiplier folds SolShare + biosolar premiums.
    # (A18 LP module-mix, Claude 2): when module_types is
    # present, cost is sum of per-module annualised CAPEX × per-module
    # kWp variable. Each module type has its own CAPEX (mono 38k, poly
    # 32k, thin-film 28k) so the LP can trade off cheaper modules vs
    # higher-yield modules to minimise levelised cost.
    if _a18_active:
        rooftop_capex_term = 0.0
        if getattr(m, "rooftop_kwp_mono", None) is not None:
            rooftop_capex_term += (
                econ.rooftop_pv_module_annualised_inr_per_kwp("mono_perc")
                * m.rooftop_kwp_mono * rooftop_capex_mult
            )
        if getattr(m, "rooftop_kwp_poly", None) is not None:
            rooftop_capex_term += (
                econ.rooftop_pv_module_annualised_inr_per_kwp("poly_si")
                * m.rooftop_kwp_poly * rooftop_capex_mult
            )
        if getattr(m, "rooftop_kwp_thinfilm", None) is not None:
            rooftop_capex_term += (
                econ.rooftop_pv_module_annualised_inr_per_kwp("thin_film_cdte")
                * m.rooftop_kwp_thinfilm * rooftop_capex_mult
            )
    else:
        rooftop_capex_term = (
            econ.rooftop_pv_annualised_inr_per_kwp()
            * m.rooftop_kwp * rooftop_capex_mult
        )
    capex_annual = (
        rooftop_capex_term
        + econ.solar_farm_annualised_inr_per_kwp() * m.farm_fixed_kwp
        + econ.tracked_pv_annualised_inr_per_kwp() * m.farm_tracked_kwp
        + econ.battery_annualised_inr_per_kwh() * m.battery_kwh
        + econ.v2g_annualised_inr_per_unit() * m.v2g_units
        + econ.biomass_chp_annualised_inr_per_kw_e() * m.biomass_kw_e
        + econ.wte_annualised_inr_per_kw_e() * m.wte_kw_e
        + econ.biogas_annualised_inr_per_kw_e() * m.biogas_kw_e
        + econ.thermal_storage_annualised_inr_per_kwh() * m.thermal_storage_kwh
        + econ.bipv_annualised_inr_per_kwp() * m.bipv_kwp
        + econ.carport_annualised_inr_per_kwp() * m.carport_kwp
        + econ.floating_pv_annualised_inr_per_kwp() * m.floating_pv_kwp
    )

    # Fuel costs per kWh dispatched (WTE fuel is negative with landfill credit).
    # FX-6: biomass fuel is per-slice (monthly storage-cost multiplier).
    fuel_costs = (
        sum(biomass_fuel_by_slice[s] * m.biomass[s] for s in slice_ids)
        + wte_fuel * sum(m.wte[s] for s in slice_ids)
        + biogas_fuel * sum(m.biogas[s] for s in slice_ids)
    )

    # Grid tariff balance.
    import_tariff = {s: econ.import_tariff(s) for s in slice_ids}
    export_tariff = econ.export_tariff()
    grid_cost = (
        sum(import_tariff[s] * m.imp[s] for s in slice_ids)
        - export_tariff * sum(m.exp[s] for s in slice_ids)
    )

    # V2G cycle-degradation cost.
    v2g_cost = v2g_deg * sum(m.v2g[s] for s in slice_ids)

    # DSR comfort cost (paid per kWh shifted, measured on the reduce side
    # since reduce and add pair 1:1 by monthly conservation).
    dsr_comfort_cost = dsr_comfort * sum(m.dsr_reduce[s] for s in slice_ids)

    # REV-2: managed-charging programme fee per SHIFTED kWh (out side;
    # pairs 1:1 with shift-in by per-(class, bucket) conservation).
    ev_smart_cost = ev_program_cost * sum(
        m.ev_shift_out[c, s] for c in EV_CLASSES for s in slice_ids
    )

    # Reliability credit: each kWh of (battery + V2G capacity) covers some
    # outage hours that would otherwise burn diesel. Subtracted from cost.
    rel_hours = econ.outage_hours_per_year()
    rel_cov = econ.reliability_coverage_fraction()
    diesel_inr = econ.diesel_displacement_value_inr_per_kwh()
    storage_outage_covered_expr = (
        (m.battery_kwh + m.v2g_units * v2g_kwh_per_unit_per_day)
        * rel_hours * rel_cov / 24.0
    )
    # CORRECTION: the town's blackout resilience
    # comes from the DISPATCHABLE CHP FLEET, not from storage./RES-1
    # measured 100% critical service through a month-long grid cut in every
    # period INCLUDING 2030, which has zero battery. Counting only storage
    # charged the town for diesel it demonstrably never burns.
    _chp_avail = econ.chp_outage_availability()
    chp_outage_covered_expr = (
        (m.biomass_kw_e + m.wte_kw_e + m.biogas_kw_e) * rel_hours * _chp_avail
    )
    # SYMMETRIC DIESEL (see economics.yaml reliability block).
    # `diesel_backup` is a free Var floored at 0 and pushed down to
    # max(0, E - C) by its own positive cost coefficient, so the kink is
    # exact and the model stays linear.
    _sym_diesel_sp = econ.symmetric_diesel_backup_enabled()
    if _sym_diesel_sp:
        _crit_outage_sp = econ.critical_outage_energy_kwh(
            sum(demand_kwh[s] for s in slice_ids) * demand_mult
        )
        m.diesel_backup = pyo.Var(within=pyo.NonNegativeReals)
        m.diesel_backup_def = pyo.Constraint(
            expr=m.diesel_backup >= (_crit_outage_sp
                                      - storage_outage_covered_expr
                                      - chp_outage_covered_expr)
        )
        reliability_credit_expr = 0.0
        diesel_backup_cost_expr = diesel_inr * m.diesel_backup
    else:
        reliability_credit_expr = storage_outage_covered_expr * diesel_inr
        diesel_backup_cost_expr = 0.0

    # B21: green-purchase energy at the delivered price + OA
    # admin (once enabled); interconnection + boundary-opex PARITY lines
    # (every scenario incl. BAU; accessors return 0.0 while disabled);
    # TRJ-7 land rent on the 2030 granted hectares (farm scenarios only).
    # Full conventions note in the multi-period builder.
    gp_cost_sp = (
        _gp_price_sp * sum(m.gp[s] for s in slice_ids) + _gp_admin_sp
        if _gp_on_sp else 0.0
    )
    # internal-network parity constant, same rule as the
    # multi-period builder (economics.yaml:electrical_network.
    # cost_in_production). NOTE the single-period path keeps the FLAT
    # interconnection charge - connection sizing is a multi-period asset
    # decision (sized once over 35 years) and is not wired here.
    from energy.electrical_assets import production_network_annualised_inr
    _en_prod_sp = float(production_network_annualised_inr(net, econ)
                        .get("annualised_total_inr", 0.0))
    b21_parity_sp = (econ.interconnection_annualised_inr()
                     + econ.boundary_opex_annual_inr(2030)
                     + _en_prod_sp)
    b21_land_rent_sp = (
        econ.farm_land_rent_annual_inr(2030)
        if getattr(scenario, "allow_solar_farm", False) else 0.0
    )

    cost_expr = (capex_annual + fuel_costs + grid_cost + v2g_cost
                  + dsr_comfort_cost + ev_smart_cost
                  - reliability_credit_expr + diesel_backup_cost_expr
                  + gp_cost_sp + b21_parity_sp + b21_land_rent_sp)

    # ---- Emissions expression ------------------------------------------
    emission_factor = econ.emission_factor_trajectory_average()
    emiss_op = (
        emission_factor * sum(m.imp[s] for s in slice_ids)
        + biomass_emiss * sum(m.biomass[s] for s in slice_ids)
        + wte_emiss * sum(m.wte[s] for s in slice_ids)
        + biogas_emiss * sum(m.biogas[s] for s in slice_ids)
    )
    # diesel burned during uncovered outages is now COUNTED.
    # `diesel_genset_emission_kgco2_per_kwh` had been defined in the config
    # and exposed by an accessor since Stage C but added to NO emissions
    # expression, so BAU's diesel CO2 was invisible - which understated BAU
    # emissions and therefore understated the town's CO2 saving.
    if _sym_diesel_sp:
        emiss_op = emiss_op + (
            econ.diesel_displacement_emission_kgco2_per_kwh() * m.diesel_backup
        )

    # Embodied carbon (annualised) -- include only if scenario opts in via
    # `carbon_objective.include_embodied_carbon` (Stage C round 3).
    if econ.include_embodied_carbon():
        emb = econ.embodied_carbon()
        techs = econ.technologies
        rooftop_emb = emb.get("rooftop_pv_kgco2_per_kwp", 0)
        farm_emb = emb.get("solar_farm_kgco2_per_kwp", 0)
        tracked_extra = emb.get("tracked_pv_extra_kgco2_per_kwp", 0)
        batt_emb = emb.get("li_ion_battery_kgco2_per_kwh", 0)
        v2g_emb = emb.get("v2g_charger_kgco2_per_unit", 0)
        biomass_emb = emb.get("biomass_chp_kgco2_per_kw_e", 0)
        wte_emb = emb.get("wte_plant_kgco2_per_kw_e", 0)
        biogas_emb = emb.get("biogas_plant_kgco2_per_kw_e", 0)
        thermal_emb = emb.get("thermal_storage_kgco2_per_kwh", 0)
        eol = 1.0 + econ.end_of_life_carbon_fraction()
        emb_annual = (
            rooftop_emb * eol * m.rooftop_kwp / int(techs["rooftop_pv"]["lifetime_years"])
            + farm_emb * eol * m.farm_fixed_kwp / int(techs["solar_farm"]["lifetime_years"])
            + (farm_emb + tracked_extra) * eol * m.farm_tracked_kwp / int(techs["solar_farm"]["lifetime_years"])
            + batt_emb * eol * m.battery_kwh / int(techs["li_ion_battery"]["lifetime_years"])
            + v2g_emb * eol * m.v2g_units / int(techs["v2g_charger"]["lifetime_years"])
            + biomass_emb * eol * m.biomass_kw_e / int(techs["biomass_chp"]["lifetime_years"])
            + wte_emb * eol * m.wte_kw_e / int(techs["wte_plant"]["lifetime_years"])
            + biogas_emb * eol * m.biogas_kw_e / int(techs["biogas_plant"]["lifetime_years"])
            + thermal_emb * eol * m.thermal_storage_kwh / int(techs["thermal_cold_storage"]["lifetime_years"])
        )
        emiss_expr = emiss_op + emb_annual
    else:
        emiss_expr = emiss_op

    # internal-network embodied carbon, mirroring the parity
    # cost added above. Outside the include_embodied_carbon branch on
    # purpose - the accessor carries that gate itself.
    from energy.electrical_assets import production_network_annualised_kgco2
    _en_prod_co2_sp = float(production_network_annualised_kgco2(net, econ)
                            .get("annualised_total_kgco2", 0.0))
    emiss_expr = emiss_expr + _en_prod_co2_sp

    # ---- Weighted objective: (1 - alpha) * cost + alpha * price * emissions
    carbon_price = econ.carbon_price_inr_per_kgco2()
    m.cost_expr = pyo.Expression(expr=cost_expr)
    m.emissions_expr = pyo.Expression(expr=emiss_expr)
    m.cost = pyo.Objective(
        expr=(1.0 - alpha) * cost_expr + alpha * carbon_price * emiss_expr,
        sense=pyo.minimize,
    )

    return m, slice_ids, hours_of


# ---------------------------------------------------------------------------
# D1(b) — multi-period vintaged capacity-expansion Pyomo LP.
# ---------------------------------------------------------------------------
def _build_pyomo_model_multi_period(net: EnergyNetwork, econ: Economics,
                                     scenario: Scenario,
                                     alpha: float = 0.0,
                                     fixed_build: Optional[dict] = None,
                                     ):  # pragma: no cover
    """Build the D1(b) multi-period vintaged Pyomo LP.

 (D1(b) Phase 2 — the author signed off): when
    ``econ.multi_period_enabled`` is True the dispatch LP solves a
    REPRESENTATIVE-YEAR capacity-expansion model across 3 periods
    (2030 / 2042 / 2055, weighted 8/9/8 yrs of the 25-yr horizon).

    Capacity vintages
    -----------------
    For each technology, ``new_build[tech, period]`` is a non-negative
    decision variable. ``installed[tech, p]`` is the cumulative sum
    ``Σ_{p' ≤ p} new_build[tech, p']`` capped at the geometric
    ``_capacity_caps``. No explicit retirement -- per the Phase 2 design
    note, battery / V2G replacement is treated implicitly via the
    annualised CRF (each vintage keeps paying its annuity in every period
    after its build year). PV yield degrades by vintage age via
    ``Economics.pv_vintage_yield_factor``.

    Per-period state
    ----------------
    Per-(period, slice) flow variables (``imp``, ``exp``, ``charge``,
    ``discharge``, ``v2g``, ``biomass``, ``wte``, ``biogas``,
    ``thermal_chg``, ``thermal_dis``, ``dsr_reduce``, ``dsr_add``)
    reuse the existing single-period rules parametrised by period.
    Demand scales with ``Economics.period_demand_multiplier(year_p)``;
    grid emission factor uses ``Economics.period_emission_factor(year_p)``;
    new-build CAPEX uses ``Economics.period_capex_factor(tech, vintage_year)``
    so 2042 / 2055 vintages benefit from learning-curve declines.

    PMSGY decay
    -----------
    The 2030-snapshot 30% subsidy already baked into
    ``rooftop_pv_annualised_inr_per_kwp`` is corrected per-vintage via
    ``Economics.pmsgy_subsidy_fraction_at_year(year)`` -- 2030 vintages
    pay the snapshot, 2042 / 2055 vintages pay (1 - lifetime-end subsidy).

    Objective
    ---------
    ``obj = Σ_p w_p × ((1-α) × cost_p + α × carbon_price × emissions_p)``
    where ``w_p = represents_years[p] / (1+discount)^(year_p - base_year)``.
    With ``discount_rate_real: 0.0`` (default), ``w_p = represents_years[p]``
    so ``lifetime_cost_expr`` is the 25-yr cashflow sum directly --
    replacing the single-period post-hoc lifetime projection. The
    legacy ``lifetime_demand_growth_factor`` and
    ``pmsgy_lifetime_capex_uplift_factor`` projections are NOT applied
    in this path: both effects are modelled per-period instead.

    Returns
    -------
    Tuple[ConcreteModel, List[int], List[str], Dict[str, float], Dict[int, float]]
        ``(model, period_years, slice_ids, hours_of, weights)``. Consumed
        by ``_solve_dispatch_pyomo_multi_period`` for result extraction.
    """
    if not _HAS_PYOMO:
        raise RuntimeError("pyomo is not installed in this environment")
    if not econ.multi_period_enabled():
        raise RuntimeError(
            "multi_period.enabled is false; call _build_pyomo_model instead"
        )

    m = pyo.ConcreteModel()

    # ---- Periods + weights ---------------------------------------------
    periods_data = econ.multi_period_periods()
    if not periods_data:
        raise RuntimeError(
            "multi_period.enabled is true but no periods defined in YAML"
        )
    period_years: List[int] = [int(p["year"]) for p in periods_data]
    represents: Dict[int, int] = {
        int(p["year"]): int(p["represents_years"]) for p in periods_data
    }
    base_year = int(econ.multi_period_base_year())
    discount = float(econ.multi_period_discount_rate())
    # w_p = represents_years[p] / (1+r)^(year_p - base_year). With r=0
    # this collapses to represents_years so Σ_p w_p × cost_p is the
    # 25-yr undiscounted sum, directly comparable to the legacy
    # ``lifetime_cost_inr = annual × N`` projection.
    weights: Dict[int, float] = {
        y: represents[y] / ((1.0 + discount) ** (y - base_year))
        for y in period_years
    }

    m.P = pyo.Set(initialize=period_years, ordered=True)

    # ---- Slices + per-slice data ---------------------------------------
    slice_ids = [s.id for s in econ.slices]
    months_set = sorted({s.month for s in econ.slices})
    m.S = pyo.Set(initialize=slice_ids, ordered=True)
    m.MONTHS = pyo.Set(initialize=months_set, ordered=True)
    month_of = {s.id: s.month for s in econ.slices}
    hours_of = {s.id: s.hours_per_year for s in econ.slices}
    days_per_month = {mm: econ.calendar.get(mm, {}).get("days", 30)
                       for mm in months_set}
    # FX-1: DSR + storage conservation tightened from
    # per-MONTH to per-(month, day-type) buckets - a weekday-evening shave can
    # no longer reappear on a weekend night (the 3am-spike root). Zero-hour
    # slices (festival dayparts in festival-less months) are excluded. In
    # 144-slice mode day_type is "mixed" so buckets reduce to months (legacy).
    daytype_of = {s.id: getattr(s, "day_type", "mixed") for s in econ.slices}
    bucket_keys = sorted({(month_of[sid], daytype_of[sid]) for sid in slice_ids
                          if hours_of[sid] > 0})
    bucket_slices = {bk: [sid for sid in slice_ids
                          if (month_of[sid], daytype_of[sid]) == bk
                          and hours_of[sid] > 0]
                     for bk in bucket_keys}
    bucket_hours = {bk: sum(hours_of[sid] for sid in bucket_slices[bk])
                    for bk in bucket_keys}
    m.BUCKETS = pyo.Set(initialize=bucket_keys, dimen=2)

    # PV yield builders (same as single-period: shared across periods, only
    # the vintage-degradation factor varies between periods).
    orientation_active = bool(
        getattr(scenario, "allow_panel_orientation_choice", False)
    )
    yield_rooftop_base = net.pv_yield_per_kwp_kwh(econ)
    if orientation_active:
        yield_rooftop = net.pv_yield_per_kwp_kwh_oriented(econ)
    else:
        yield_rooftop = yield_rooftop_base
    yield_farm = net.pv_yield_per_kwp_kwh_solar_farm(econ)
    demand_kwh = net.demand_by_slice_kwh(econ)

    # RES-1: resilience / unserved-energy scenario hook
    # (scenario_hooks.resilience_unserved - VoLL + shock knobs; citations in
    # economics.yaml). Gated exactly like duck_curve_drift: every branch
    # below is structurally absent when the hook is off, so the production
    # expression tree is byte-identical. Never enabled in the production
    # config; scripts/res1_black_swan_pack.py flips it on deepcopied clones.
    _res = econ.scenario_hook("resilience_unserved")
    _res_on = bool(_res)
    if _res_on:
        _res_voll = float(_res.get("voll_inr_per_kwh", 140.0) or 140.0)
        _res_imp_m = {str(k): float(v) for k, v in
                      (_res.get("import_cap_multiplier_by_month") or {}).items()}
        _res_exp_m = {str(k): float(v) for k, v in
                      (_res.get("export_cap_multiplier_by_month") or {}).items()}
        _res_dem = _res.get("demand_multiplier_by_period_month") or {}
        _res_pv_m = {str(k): float(v) for k, v in
                     (_res.get("pv_yield_multiplier_by_month") or {}).items()}
        _res_fpv_m = {str(k): float(v) for k, v in
                      (_res.get("floating_pv_yield_multiplier_by_month")
                       or {}).items()}
        _sr = _res.get("straw_energy_cap_multiplier")
        _res_straw_mult = 1.0 if _sr is None else float(_sr)
        # All-PV month derate (RES-B heatwave): rebind COPIES of the yield
        # dicts; the wheeled green park (gp_shape) correctly derates too
        # since it is shaped by yield_farm (same insolation clock).
        if _res_pv_m:
            def _res_scale(_yd):
                return {sid: v * _res_pv_m.get(month_of[sid], 1.0)
                        for sid, v in _yd.items()}
            _same_obj = yield_rooftop is yield_rooftop_base
            yield_rooftop_base = _res_scale(yield_rooftop_base)
            yield_rooftop = (yield_rooftop_base if _same_obj
                             else _res_scale(yield_rooftop))
            yield_farm = _res_scale(yield_farm)
        # Floating-PV-only month derate (RES-D canal closure).
        _res_fpv_slice = ({sid: _res_fpv_m.get(month_of[sid], 1.0)
                           for sid in demand_kwh} if _res_fpv_m else None)
    else:
        _res_fpv_slice = None

    # Multipliers (scenario-dependent; constant across periods).
    rooftop_capex_mult = (
        econ.rooftop_pv_capex_multiplier_with_solshare(scenario)
        * econ.rooftop_pv_capex_multiplier_with_biosolar(scenario)
    )
    rooftop_yield_mult = econ.rooftop_pv_yield_multiplier_with_biosolar(scenario)
    demand_mult = econ.total_demand_multiplier_with_biosolar(scenario)

    coupling_mode = str(
        getattr(scenario, "battery_coupling_mode", "ac_traditional")
    )
    # net of the plant's own auxiliary load (CERC RTE x (1-AEC)).
    rt_eff = econ.battery_rte_net_of_aux_for(coupling_mode)
    max_dod = econ.battery_max_dod()

    ac_eff = max(1e-6, 1.0 - econ.ac_loss_fraction())
    #: PSPCL's technical T&D loss now improves across the
    # horizon instead of sitting flat at 10.7% while the same grid's carbon
    # intensity falls 69% (period_emission_factor 0.5106 -> 0.1605). The
    # trajectory is deliberately shallow (10.7 / 9.5 / 8.5%) because RDSS
    # targets AT&C, most of which is a billing improvement, while this figure
    # is physical loss only. Keyed by PERIOD YEAR; with no trajectory
    # configured every entry collapses to the flat value, byte-exact.
    grid_import_eff_p = {
        y: ac_eff * max(1e-6, 1.0 - econ.pspcl_grid_loss_fraction(y))
        for y in period_years
    }

    v2g_kwh_per_unit_per_day = econ.v2g_kwh_per_unit_per_day()
    # TRJ-3: V2G energy budget per unit GROWS with fleet-average
    # EV pack size (6 -> 8 -> 9.5 kWh/unit/day; economics.yaml v2g_charger
    # block). Used in the per-period V2G energy budget + reliability credit;
    # collapses to the static value at the base year and when unconfigured.
    v2g_day_by_period = {y: econ.v2g_kwh_per_unit_per_day_at(y)
                         for y in period_years}
    v2g_power_kw = econ.v2g_power_kw_per_unit()
    v2g_deg = econ.v2g_cycle_degradation_inr_per_kwh()
    import_cap_kw = econ.import_capacity_limit_kw()
    export_cap_kw = econ.export_capacity_limit_kw()

    biomass_fuel = econ.biomass_fuel_cost_inr_per_kwh()
    biomass_emiss = econ.biomass_emission_factor_kgco2_per_kwh()
    biomass_hours_yr = econ.biomass_operating_hours_per_year()
    # FX-6 / N7+: straw-supply realism (mirrors the
    # single-period builder; see the YAML block for derivations).
    bm_month_of = {s.id: s.month for s in econ.slices}
    biomass_fuel_by_slice = {
        sid: biomass_fuel * econ.biomass_monthly_fuel_cost_multiplier(mm)
        for sid, mm in bm_month_of.items()
    }
    # TRJ-4: straw-price COMPETITION path - the real fuel price
    # rises across periods as CBG/boiler/power ex-situ demand tightens the
    # catchment (CAQM Tier-1 anchors; economics.yaml biomass_chp block).
    # Stacks multiplicatively with the FX-6 monthly storage multiplier.
    biomass_fuel_period_mult = {
        y: econ.biomass_fuel_price_period_multiplier(y) for y in period_years
    }
    biomass_constrained_months = [
        mm for mm in MONTHS
        if econ.biomass_monthly_availability_fraction(mm) < 1.0 - 1e-12
    ]
    biomass_straw_cap_kwh = econ.biomass_annual_straw_energy_cap_kwh()
    # RES-1 (RES-C straw loss): scale the annual straw-energy budget on
    # shock clones (x0 = season lost). No-op when the hook is off.
    if _res_on and biomass_straw_cap_kwh is not None:
        biomass_straw_cap_kwh = biomass_straw_cap_kwh * _res_straw_mult
    wte_fuel = econ.wte_effective_fuel_cost_inr_per_kwh()
    wte_emiss = econ.wte_emission_factor_kgco2_per_kwh()
    wte_hours_yr = econ.wte_operating_hours_per_year()
    biogas_fuel = econ.biogas_fuel_cost_inr_per_kwh()
    biogas_emiss = econ.biogas_emission_factor_kgco2_per_kwh()
    biogas_hours_yr = econ.biogas_operating_hours_per_year()
    thermal_rt_eff = econ.thermal_storage_round_trip_efficiency()

    bipv_yield_mult = econ.bipv_yield_multiplier_vs_rooftop()
    fpv_yield_mult = econ.floating_pv_yield_multiplier_vs_ground_mount()
    tracked_yield_mult = econ.tracked_pv_yield_multiplier()

    caps = _capacity_caps(net, econ, scenario)
    bipv_cap = (net.total_bipv_potential_kwp(econ)
                if getattr(scenario, "allow_bipv", False) else 0.0)
    carport_cap = (net.total_carport_potential_kwp(econ)
                    if getattr(scenario, "allow_carport", False) else 0.0)
    fpv_cap = (net.total_floating_pv_potential_kwp(econ)
                if getattr(scenario, "allow_floating_pv", False) else 0.0)
    tracked_cap = (caps["solar_farm_kwp"]
                    if getattr(scenario, "allow_tracked_pv", False) else 0.0)
    # TRJ-1: area-limited PV ceilings GROW for later periods -
    # rising module efficiency packs more kWp on the same roof/land (ITRPV/
    # NREL ATB; economics.yaml multi_period block). Applies to every
    # area-based PV cap (rooftop, farm incl. tracked, BIPV, carport,
    # floating); 1.0 at the base year keeps 2030 byte-exact. Counters
    # (demand growth outrunning a fixed PV ceiling).
    pv_dens_mult = {y: econ.pv_density_ceiling_multiplier(y)
                    for y in period_years}

    # Per-period V2G fleet cap: EV-car-owning, V2G-willing
    # households grow across the horizon via `ev_car_share_by_period`, so the
    # cumulative installed V2G at each period is bounded by THAT period's fleet
    # (not the static 2030 count). Replaces the single caps["v2g_units"] bound.
    if scenario.allow_v2g:
        v2g_cap_by_period = {y: net.v2g_units(econ, year=y) for y in period_years}
    else:
        v2g_cap_by_period = {y: 0.0 for y in period_years}
    v2g_cap_max = max(v2g_cap_by_period.values()) if v2g_cap_by_period else 0.0

    # Per-period demand multiplier + tariff escalation across periods.
    period_demand_mult = {y: econ.period_demand_multiplier(y)
                           for y in period_years}
    # EV-charging demand split: the EV term ramps per period via
    # the per-income `ev_car_share_by_period` table while the rest of demand
    # scales by `period_demand_multiplier`. `ev_kwh_base` is the 2030 EV load
    # already embedded in `demand_kwh`; `non_ev_kwh` is everything else.
    ev_kwh_base = net.ev_charging_kwh_by_slice(econ, year=None)
    non_ev_kwh = {s: demand_kwh[s] - ev_kwh_base.get(s, 0.0) for s in slice_ids}
    ev_kwh_by_period = {
        y: net.ev_charging_kwh_by_slice(econ, year=y) for y in period_years
    }
    # Period-correct demand by slice (kWh, pre scenario demand_mult): non-EV
    # scales by period_demand_mult; EV ramps via the per-period table. Collapses
    # to demand_kwh[s] at 2030 (ramp=1, period_demand_mult=1) -> byte-exact base.
    #: climate warming is applied to the COOLING term, not
    # flat across all demand. It used to ride inside period_demand_multiplier,
    # which meant +2 C of global warming raised JANUARY 2055 demand by 3% -
    # warming raises cooling and lowers heating, it does not raise winter
    # demand. `non_ev_kwh` already contains the 2030 cooling, so only the
    # UPLIFT is added here. The other lifetime drivers (income, cooking, AI,
    # water) still scale everything including the uplift, which is correct:
    # a richer household cools a warmer house harder.
    cool_kwh_base = net.cooling_kwh_by_slice(econ)
    cool_uplift = {y: econ.cooling_warming_multiplier(y) - 1.0
                   for y in period_years}
    period_slice_demand = {
        y: {s: period_demand_mult[y]
               * (non_ev_kwh[s]
                  + cool_uplift[y] * cool_kwh_base.get(s, 0.0)
                  + ev_kwh_by_period[y].get(s, 0.0))
            for s in slice_ids}
        for y in period_years
    }
    # RES-1 (RES-B heatwave): scale the affected (period, month) slice
    # demand IN PLACE after construction - the construction above stays
    # byte-identical when the hook is off or the table is empty.
    if _res_on and _res_dem:
        for _y, _row in _res_dem.items():
            _yi = int(_y)
            if _yi not in period_slice_demand or not _row:
                continue
            for _sid in period_slice_demand[_yi]:
                _mlt = _row.get(month_of[_sid])
                if _mlt is not None:
                    period_slice_demand[_yi][_sid] *= float(_mlt)
    esc = float(econ.tariff_escalation_real_annual_value())
    period_tariff_mult = {y: (1.0 + esc) ** (y - base_year)
                           for y in period_years}
    period_emiss = {y: econ.period_emission_factor(y) for y in period_years}
    import_tariff = {s: econ.import_tariff(s) for s in slice_ids}
    # per-slice export (flat under fixed ToU; wholesale-pegged per
    # slice under IEX-Agile "Outgoing Agile").
    export_tariff = {s: econ.export_tariff(s) for s in slice_ids}
    # DEM-3 scenario hook: duck-curve tariff drift + falling
    # feed-in. All-1.0 no-ops unless scenario_hooks.duck_curve_drift is
    # enabled (A/B runs only); the guard keeps the production expression
    # tree untouched.
    _duck_on = bool(econ.scenario_hook("duck_curve_drift"))
    if _duck_on:
        _daypart_of = {s.id: s.daypart for s in econ.slices}
        duck_imp = {
            (y, sid): econ.duck_curve_import_multiplier(y, _daypart_of[sid])
            for y in period_years for sid in slice_ids
        }
        duck_exp = {y: econ.duck_curve_export_multiplier(y)
                    for y in period_years}
    # DEM-8 scenario hook: carbon price 2042+ (0.0 everywhere
    # unless scenario_hooks.carbon_price is enabled).
    carbon_price_by_period = {
        y: econ.carbon_price_by_period_inr_per_kgco2(y) for y in period_years
    }

    dsr_enabled = (getattr(scenario, "allow_dsr", False) and econ.dsr_enabled())
    if dsr_enabled:
        dsr_fraction = econ.dsr_aggregate_shiftable_fraction()
        dsr_comfort = econ.dsr_comfort_cost_inr_per_kwh()
    else:
        dsr_fraction = 0.0
        dsr_comfort = 0.0
    peak_slice_ids = [s.id for s in econ.slices
                       if s.tariff_band in ("peak", "super_peak")]
    nonpeak_slice_ids = [s.id for s in econ.slices
                          if s.tariff_band not in ("peak", "super_peak")]

    # ---- New-build capacity variables (per period) ---------------------
    # TRJ-1: PV-surface new-build bounds carry the period's density ceiling
    # (a 2055 vintage may fill the 2055-efficiency roof, not just the 2030
    # one); the cumulative-installed cap constraints below are scaled the
    # same way, so the binding limit is always the period ceiling.
    # STAGE-B18.1/B18.3: farm + carport ceilings ALSO carry the
    # per-period LAND multiplier read from the layout's phased expansion
    # tags (solar_expansion_* / parking_expansion_* - the 6%->8%->10% land
    # grant + demand-driven parking growth). 1.0 on untagged layouts, so
    # pre-B18 baselines stay byte-exact ("more land x better panels").
    from energy.network import phased_land_multipliers
    _land_mult = phased_land_multipliers(getattr(net, "grid", None))
    farm_land = {p: float(_land_mult["solar_farm"].get(p, 1.0))
                 for p in period_years}
    carport_land = {p: float(_land_mult["carport"].get(p, 1.0))
                    for p in period_years}
    # CRIT-2b /: tracked-vs-fixed LAND ratio (GCR-derived
    # 1.33; economics.yaml tracked_pv block). 1 kWp tracked consumes `ratio`
    # fixed-equivalent kWp of every period's area-derived farm ceiling.
    # ratio 1.0 (key absent) = legacy shared-density behaviour, byte-exact.
    farm_land_ratio = econ.tracked_pv_land_ratio_vs_fixed()
    m.rooftop_new = pyo.Var(m.P, bounds=lambda _m, p: (
        0.0, caps["rooftop_pv_kwp"] * pv_dens_mult[p]))
    m.farm_fixed_new = pyo.Var(m.P, bounds=lambda _m, p: (
        0.0, caps["solar_farm_kwp"] * pv_dens_mult[p] * farm_land[p]))
    m.farm_tracked_new = pyo.Var(m.P, bounds=lambda _m, p: (
        0.0, tracked_cap * pv_dens_mult[p] * farm_land[p] / farm_land_ratio))
    m.battery_new = pyo.Var(m.P, bounds=(0.0, caps["battery_kwh"]))
    m.v2g_new = pyo.Var(m.P, bounds=(0.0, v2g_cap_max))
    m.biomass_new = pyo.Var(m.P, bounds=(0.0, caps["biomass_kw_e"]))
    m.wte_new = pyo.Var(m.P, bounds=(0.0, caps["wte_kw_e"]))
    m.biogas_new = pyo.Var(m.P, bounds=(0.0, caps["biogas_kw_e"]))
    m.thermal_new = pyo.Var(m.P, bounds=(0.0, caps["thermal_storage_kwh"]))
    m.bipv_new = pyo.Var(m.P, bounds=lambda _m, p: (
        0.0, bipv_cap * pv_dens_mult[p]))
    m.carport_new = pyo.Var(m.P, bounds=lambda _m, p: (
        0.0, carport_cap * pv_dens_mult[p] * carport_land[p]))
    m.floating_pv_new = pyo.Var(m.P, bounds=lambda _m, p: (
        0.0, fpv_cap * pv_dens_mult[p]))

    # RES-1 build-freeze: fix the per-vintage new-build Vars at supplied
    # values so shock solves run DISPATCH-ONLY on the frozen design (the
    # town cannot retro-build its way out of a black swan). None = model
    # untouched (production path).
    if fixed_build:
        for _vname, _by_year in fixed_build.items():
            _var = getattr(m, _vname)
            for _yy, _vv in _by_year.items():
                _var[int(_yy)].fix(float(_vv))

    # ---- Cumulative installed Expressions ------------------------------
    def _cumulative(var, p_target: int):
        return sum(var[pp] for pp in period_years if pp <= p_target)

    m.rooftop_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.rooftop_new, p))
    m.farm_fixed_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.farm_fixed_new, p))
    m.farm_tracked_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.farm_tracked_new, p))
    m.battery_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.battery_new, p))
    # USABLE battery capacity = sum of vintages with calendar-fade
    # applied (a battery built in vintage pp has shrunk to (1-fade)^age by p).
    # battery_installed (above) stays the as-built kWh (for the build cap +
    # CAPEX/EOL); battery_effective is what can actually be cycled.
    m.battery_effective = pyo.Expression(
        m.P, rule=lambda _m, p: sum(
            _m.battery_new[pp] * econ.battery_vintage_capacity_factor(pp, p)
            for pp in period_years if pp <= p))
    m.v2g_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.v2g_new, p))
    m.biomass_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.biomass_new, p))
    m.wte_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.wte_new, p))
    m.biogas_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.biogas_new, p))
    m.thermal_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.thermal_new, p))
    m.bipv_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.bipv_new, p))
    m.carport_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.carport_new, p))
    m.floating_pv_installed = pyo.Expression(
        m.P, rule=lambda _m, p: _cumulative(_m.floating_pv_new, p))

    # ---- Capacity caps on cumulative installed -------------------------
    # TRJ-1: PV-surface caps scale with the period's density ceiling
    # (pv_dens_mult; 1.0 at 2030). Non-area techs (battery, V2G, plants,
    # thermal) keep their original caps.
    # (,
    # capacity?"): TWO FORMS, switched by economics.multi_period.
    # pv_density_area_budget (default False = legacy, byte-exact).
    #   legacy:  sum_v new[v]           <= base * dens[p] * land[p]
    #   area:    sum_v new[v] / dens[v] <= base * land[p]
    # The legacy form was written for phased land ("more land x better
    # panels", above) and is only correct while the LAND term grows: once
    # released all 301 farm ha in 2030, dens[p] began
    # re-rating ALREADY-BUILT vintages on land that is already full.
    # Measured phantom capacity at 2055: farm +32,237.1 kWp (13.0%),
    # capacity_cap_audit_20260820.txt). The area form conserves surface:
    # each vintage occupies land at its OWN vintage density, so a late
    # build on EMPTY surface still packs denser (the 2042 canal fill at
    # x1.10 is legitimate and survives), but standing capacity is never
    # re-rated. dens[2030] = 1.0, so the 2030 base year - and the pinned
    # annual headline - is IDENTICAL under both forms. Same area-budget
    # pattern the solar-thermal `st_roof_share` constraint has always used.
    _area_budget = econ.pv_density_area_budget()

    def _area_used(var, p_target):
        # Fixed-equivalent surface consumed by vintages up to p_target,
        # each at its own density (kWp / dens[vintage]).
        return sum(var[pp] / pv_dens_mult[pp]
                   for pp in period_years if pp <= p_target)

    if _area_budget:
        m.rooftop_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _area_used(_m.rooftop_new, p)
                <= caps["rooftop_pv_kwp"])
        # CRIT-2b / ratio unchanged: tracked consumes `ratio` fixed-
        # equivalent surface per kWp - now per-vintage like everything else.
        m.farm_total_cap = pyo.Constraint(
            m.P, rule=lambda _m, p:
                _area_used(_m.farm_fixed_new, p)
                + farm_land_ratio * _area_used(_m.farm_tracked_new, p)
                <= caps["solar_farm_kwp"] * farm_land[p])
        m.farm_tracked_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _area_used(_m.farm_tracked_new, p)
                <= tracked_cap * farm_land[p] / farm_land_ratio)
    else:
        m.rooftop_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _m.rooftop_installed[p]
                <= caps["rooftop_pv_kwp"] * pv_dens_mult[p])
        # CRIT-2b /: farm LAND cap in fixed-equivalent kWp - tracked
        # weighted by its land ratio (1.0 legacy = the old simple sum).
        m.farm_total_cap = pyo.Constraint(
            m.P, rule=lambda _m, p:
                _m.farm_fixed_installed[p]
                + farm_land_ratio * _m.farm_tracked_installed[p]
                <= caps["solar_farm_kwp"] * pv_dens_mult[p] * farm_land[p])
        m.farm_tracked_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _m.farm_tracked_installed[p]
                <= tracked_cap * pv_dens_mult[p] * farm_land[p] / farm_land_ratio)
    m.battery_cap = pyo.Constraint(
        m.P, rule=lambda _m, p: _m.battery_installed[p] <= caps["battery_kwh"])
    m.v2g_cap = pyo.Constraint(
        m.P, rule=lambda _m, p: _m.v2g_installed[p] <= v2g_cap_by_period[p])
    m.biomass_cap = pyo.Constraint(
        m.P, rule=lambda _m, p:
            _m.biomass_installed[p] <= caps["biomass_kw_e"])
    m.wte_cap = pyo.Constraint(
        m.P, rule=lambda _m, p: _m.wte_installed[p] <= caps["wte_kw_e"])
    m.biogas_cap = pyo.Constraint(
        m.P, rule=lambda _m, p: _m.biogas_installed[p] <= caps["biogas_kw_e"])
    m.thermal_cap = pyo.Constraint(
        m.P, rule=lambda _m, p:
            _m.thermal_installed[p] <= caps["thermal_storage_kwh"])
    if _area_budget:
        # area form for the remaining PV surfaces (see block above).
        m.bipv_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _area_used(_m.bipv_new, p) <= bipv_cap)
        m.carport_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _area_used(_m.carport_new, p)
                <= carport_cap * carport_land[p])
        m.floating_pv_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _area_used(_m.floating_pv_new, p)
                <= fpv_cap)
    else:
        m.bipv_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _m.bipv_installed[p]
                <= bipv_cap * pv_dens_mult[p])
        m.carport_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _m.carport_installed[p]
                <= carport_cap * pv_dens_mult[p] * carport_land[p])
        m.floating_pv_cap = pyo.Constraint(
            m.P, rule=lambda _m, p: _m.floating_pv_installed[p]
                <= fpv_cap * pv_dens_mult[p])

    # ---- Per-period per-slice flow variables ---------------------------
    m.imp = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.exp = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.charge = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.discharge = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.v2g = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.biomass = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.wte = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.biogas = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.thermal_chg = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.thermal_dis = pyo.Var(m.P, m.S, bounds=(0.0, None))

    # Data-centre PPA offtake (N21 — Stage E PPA LP wiring,). Drives
    # off the existing `ppa:` scaffold (config + Economics.ppa_* accessors): an
    # EXTERNAL data centre buys the district's SURPLUS generation via a
    # dedicated line off the substation, BYPASSING the 60 MW grid-export cap.
    # GATED on `ppa_enabled` + an active counterparty — when off, no Var/
    # constraint/revenue is created, so the headline stays byte-exact.
    # PPA-BAU-1 (, caught by test_bau_cost_is_pure_tariffed_import
    # latent-red class that test's docstring warns about, and the first one
    # the test caught BEFORE the number was published):
    # `ppa_enabled` is a CONFIG flag, so once the PPA went live in
    # production EVERY scenario paid `_dc_ppa_annual_fixed` -
    # including BAU, which has no generation and sold the data centre
    # 0 kWh. BAU was being charged Rs 1,092,787.03/yr for a contract it
    # cannot serve, inflating the headline DENOMINATOR (i.e. flattering
    # vs-BAU by ~0.03 pp). The PPA sells the district's SURPLUS
    # GENERATION, so it is now gated on the scenario being allowed to
    # generate at all - the same test `b21_land_rent` already uses.
    _dc_ppa_on = (econ.ppa_enabled()
                  and bool(econ.ppa_active_counterparties())
                  and (getattr(scenario, "allow_solar_farm", False)
                       or getattr(scenario, "allow_rooftop_pv", False)))
    if _dc_ppa_on:
        _active_cps = econ.ppa_active_counterparties()
        _dc_offtake_cap_kw = econ.ppa_total_offtake_kw_constant()
        # (register AUD-CFG-1,: read
        # `bound_by_surplus_not_baseload` FOR REAL. It had been documented in
        # the comment at constraint (3) below since the block was written, and
        # NO CODE READ IT - the surplus-following branch was hardcoded, so the
        # strict-baseload contract the config advertises could not be selected.
        # Found by the config-consumer audit's comment-only class.
        # true  (default, production) -> offtake is an UPPER BOUND: the town
        #        sells whatever surplus it has, up to the intake capacity.
        # false (legacy strict baseload) -> the contract is FIRM: the Var must
        #        EQUAL offtake_kw_constant x hours in every slice, so the town
        #        must serve 25 MW round-the-clock or the model is infeasible.
        # ALL active counterparties must agree; mixing firm and surplus
        # contracts in one solve is not defined, so that raises rather than
        # silently picking one.
        _dc_bound_flags = {bool(sp.get("bound_by_surplus_not_baseload", True))
                           for sp in _active_cps.values()}
        if len(_dc_bound_flags) > 1:
            raise ValueError(
                "active PPA counterparties disagree on "
                "bound_by_surplus_not_baseload; a firm-baseload and a "
                "surplus-following contract cannot be solved together: "
                f"{ {nm: sp.get('bound_by_surplus_not_baseload', True) for nm, sp in _active_cps.items()} }")
        _dc_firm_baseload = (_dc_bound_flags == {False})
        # Offtake-weighted NET price (= the single active counterparty's net in
        # the usual A/B case). Net = tariff·(1-wheeling_loss) - wheeling - CSS.
        _tot_off = sum(float(sp.get("offtake_kw_constant", 0.0))
                       for sp in _active_cps.values()) or 1.0
        _dc_ppa_price = sum(
            econ.ppa_counterparty_net_tariff_inr_per_kwh(nm)
            * float(sp.get("offtake_kw_constant", 0.0))
            for nm, sp in _active_cps.items()) / _tot_off
        # Annual FIXED cost when the PPA is signed: annualised interconnection
        # + legal CAPEX (CRF, utility actor) + annual admin, summed over active.
        _dc_ppa_annual_fixed = sum(
            econ.ppa_counterparty_annualised_capex_inr(nm, "utility")
            + econ.ppa_counterparty_annual_admin_inr(nm)
            for nm in _active_cps)
        _dc_max_share = econ.ppa_max_share_of_district_demand()
        m.dc_ppa = pyo.Var(m.P, m.S, bounds=(0.0, None))
    else:
        _dc_offtake_cap_kw = 0.0
        _dc_ppa_price = 0.0
        _dc_ppa_annual_fixed = 0.0
        _dc_max_share = 0.0

    # B21: buy-side GREEN OPEN-ACCESS PURCHASE.
    # Per-period contracted MW (gp_mw) + per-slice DELIVERED energy (gp),
    # solar-shaped (the external Punjab park generates on the same GSA clock
    # as the district's own tracked farm - the drawal bound reuses the farm
    # per-kWp slice yields x the tracked multiplier). Delivered-price
    # convention: OA losses + the 2% NRSE in-kind T&W charge are priced INTO
    # econ.green_purchase_delivered_price_inr_per_kwh, so gp enters the
    # balance at par. Gated on the config enable AND the scenario flag
    # (BAU / pv_* counterfactuals stay grid-only); enabled: false in
    _gp_on = (econ.green_purchase_enabled()
              and bool(getattr(scenario, "allow_green_purchase", False)))
    if _gp_on:
        _gp_price = econ.green_purchase_delivered_price_inr_per_kwh()
        _gp_admin = econ.green_purchase_annual_admin_inr()
        m.gp_mw = pyo.Var(
            m.P, bounds=(0.0, econ.green_purchase_contracted_mw_max()))
        m.gp = pyo.Var(m.P, m.S, bounds=(0.0, None))
    else:
        _gp_price = 0.0
        _gp_admin = 0.0

    peak_set = set(peak_slice_ids)
    nonpeak_set = set(nonpeak_slice_ids)
    def _reduce_bound(_m, p, s):
        if dsr_enabled and s in peak_set:
            return (0.0, dsr_fraction * demand_mult * period_slice_demand[p][s])
        return (0.0, 0.0)
    # FX-1/: dsr_add is now CAPPED per slice (symmetric with
    # the reduce cap) and barred from zero-hour slices - the uncapped bound was
    # the 3am-spike root (a month of evening shaves dumped into one cheap hour,
    # 3.42x daily mean, saturating the 200 MW import cap).
    def _add_bound(_m, p, s):
        if dsr_enabled and s in nonpeak_set and hours_of[s] > 0:
            return (0.0, dsr_fraction * demand_mult * period_slice_demand[p][s])
        return (0.0, 0.0)
    m.dsr_reduce = pyo.Var(m.P, m.S, bounds=_reduce_bound)
    m.dsr_add = pyo.Var(m.P, m.S, bounds=_add_bound)

    # FX-1/: conservation per (month, day-type) bucket (was per month).
    def _dsr_bucket(_m, p, mm, dt):
        sids = bucket_slices[(mm, dt)]
        return (sum(_m.dsr_reduce[p, s] for s in sids)
                == sum(_m.dsr_add[p, s] for s in sids))
    m.dsr_bucket = pyo.Constraint(m.P, m.BUCKETS, rule=_dsr_bucket)

    # ---- REV-2: EV SMART CHARGING (per period) ------------
    # Mirrors the single-period builder: bounded charge-shift within each
    # class's plug-in window (= the support of the cited daypart shapes),
    # conserved per (period, class, month, day-type). Bounds scale with the
    # PERIOD's EV load (ev_car_share_by_period ramp), so the movable pool
    # grows with the fleet. See _build_pyomo_model for the full rationale.
    smart_ev_on = (getattr(scenario, "allow_ev_smart_charging", False)
                   and econ.ev_smart_charging_enabled())
    EV_CLASSES = ("residential", "workplace")
    if smart_ev_on:
        ev_class_kwh_by_period = {
            y: net.ev_charging_kwh_by_slice_by_class(econ, year=y)
            for y in period_years
        }
        ev_shift_frac = {c: econ.ev_shiftable_fraction(c) for c in EV_CLASSES}
        ev_program_cost = econ.ev_smart_charging_cost_inr_per_kwh()
    else:
        ev_class_kwh_by_period = {
            y: {c: {} for c in EV_CLASSES} for y in period_years
        }
        ev_shift_frac = {c: 0.0 for c in EV_CLASSES}
        ev_program_cost = 0.0
    m.EVC = pyo.Set(initialize=EV_CLASSES, ordered=True)

    def _ev_shift_bound(_m, p, c, s):
        if not smart_ev_on or hours_of[s] <= 0:
            return (0.0, 0.0)
        base = ev_class_kwh_by_period[p][c].get(s, 0.0)
        if base <= 0.0:
            return (0.0, 0.0)
        return (0.0, ev_shift_frac[c] * base * demand_mult)
    m.ev_shift_out = pyo.Var(m.P, m.EVC, m.S, bounds=_ev_shift_bound)
    m.ev_shift_in = pyo.Var(m.P, m.EVC, m.S, bounds=_ev_shift_bound)

    def _ev_shift_bucket(_m, p, c, mm, dt):
        if not smart_ev_on:
            return pyo.Constraint.Skip
        sids = bucket_slices[(mm, dt)]
        return (sum(_m.ev_shift_out[p, c, s] for s in sids)
                == sum(_m.ev_shift_in[p, c, s] for s in sids))
    m.ev_shift_bucket = pyo.Constraint(m.P, m.EVC, m.BUCKETS,
                                       rule=_ev_shift_bucket)

    # ---- Per-(period, slice) balance with vintage-aged PV supply -------
    def _mp_pv_supply(_m, p, s):
        # PV supply summed across vintages with age-degraded yields.
        pv_supply = 0.0
        for pp in period_years:
            if pp > p:
                break
            roof_age = econ.pv_vintage_yield_factor("rooftop_pv", pp, p)
            farm_age = econ.pv_vintage_yield_factor("solar_farm", pp, p)
            pv_supply += (
                yield_rooftop[s] * rooftop_yield_mult
                * _m.rooftop_new[pp] * roof_age
            )
            pv_supply += yield_farm[s] * _m.farm_fixed_new[pp] * farm_age
            pv_supply += (
                yield_farm[s] * tracked_yield_mult
                * _m.farm_tracked_new[pp] * farm_age
            )
            pv_supply += (
                yield_rooftop_base[s] * bipv_yield_mult
                * _m.bipv_new[pp] * roof_age
            )
            pv_supply += yield_farm[s] * _m.carport_new[pp] * farm_age
            # RES-1 (RES-D canal closure): floating-PV-only month derate;
            # _res_fpv_slice is None when the hook/table is off, and the
            # expression below then reduces to the original arithmetic.
            _fpv_y = yield_farm[s] * fpv_yield_mult
            if _res_fpv_slice is not None:
                _fpv_y *= _res_fpv_slice.get(s, 1.0)
            pv_supply += _fpv_y * _m.floating_pv_new[pp] * farm_age
        return pv_supply

    # FX-1/: explicit PV curtailment. The old balance was an
    # EQUALITY with no spill term, so the LP was FORCED to absorb every PV kWh
    # (1.05 GWh/yr of dsr_add was forced absorption at export-cap hours) and
    # PV build was bounded by absorbability, not economics. Named pv_curtail
    # (not `curtail`) to avoid colliding with the Stage-D phase-2 per-type vars.
    m.pv_curtail = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.pv_curtail_cap = pyo.Constraint(
        m.P, m.S, rule=lambda _m, p, s: _m.pv_curtail[p, s] <= _mp_pv_supply(_m, p, s))

    # RES-1: unserved-energy Var (load shed priced at VoLL in the period
    # cost) - built ONLY when the resilience hook is on; the production
    # balance below stays a hard equality with no extra term.
    if _res_on:
        m.unserved = pyo.Var(m.P, m.S, bounds=(0.0, None))
        m.unserved_cap = pyo.Constraint(
            m.P, m.S, rule=lambda _m, p, s: _m.unserved[p, s]
                <= demand_mult * period_slice_demand[p][s])

    # ---- SOLAR WATER HEATING -------------------------------
    # Gated on BOTH the config flag and the scenario flag. When either is off
    # NO Var, Expression or Constraint is created and the balance below loses
    # its term entirely, so the model is STRUCTURALLY identical to the pinned
    # one - not merely numerically close.
    # WHY IT IS A STORE, NOT A GENERATOR. 79.05% of this district's water
    # heating is drawn outside the collector's own 08-16 window, and 41.58% of
    # it is the 06-08 morning shower - heat collected the previous day. So the
    # interesting constraint is not "how much can it collect" but "how much
    # survives the wait", which is why this follows the BATTERY's bucket
    # formulation rather than the PV pattern.
    _st_on = (econ.solar_thermal_enabled()
              and bool(getattr(scenario, "allow_solar_thermal", False)))
    if _st_on:
        _st_dhw_base = net.water_heating_kwh_by_slice(econ)
        _st_roof_m2 = net.solar_thermal_roof_cap_m2(econ)
        _st_yield = {sid: econ.solar_thermal_kw_per_m2(sid) * hours_of[sid]
                     for sid in slice_ids}
        _st_tank = econ.solar_thermal_tank_kwh_per_m2()
        _st_eff = float(net.rooftop_module_efficiency)
        # Water heating rides the SAME period multiplier as the rest of
        # non-EV demand, so the collector chases a load that grows with the
        # town rather than a frozen 2030 one.
        _st_dhw = {y: {s: period_demand_mult[y] * _st_dhw_base.get(s, 0.0)
                       for s in slice_ids}
                   for y in period_years}

        m.st_new = pyo.Var(m.P, bounds=(0.0, None))
        m.st_installed = pyo.Expression(
            m.P, rule=lambda _m, p: _cumulative(_m.st_new, p))
        m.st_collect = pyo.Var(m.P, m.S, bounds=(0.0, None))
        m.st_serve = pyo.Var(m.P, m.S, bounds=(0.0, None))

        # (a) collection is capped by the derived per-slice yield.
        m.st_collect_cap = pyo.Constraint(
            m.P, m.S, rule=lambda _m, p, s:
                _m.st_collect[p, s] <= _st_yield[s] * _m.st_installed[p])

        # (b) THE ROOF COMPETITION, and it is the point of the whole exercise.
        # A square metre carrying a collector cannot also carry a panel.
        # Rooftop PV capacity inverts to area through the same module
        # efficiency the caps were built with, so both sides are in m2.
        if _st_roof_m2 > 0:
            #: under the area budget a later rooftop vintage occupies
            # less roof per kWp (its own density), so the kWp->m2 inversion
            # is per-vintage. An all-2030 rooftop fleet (the pinned solution)
            # is numerically identical either way.
            if _area_budget:
                def _pv_roof_area(_m, p):
                    return sum(_m.rooftop_new[pp] / (_st_eff * pv_dens_mult[pp])
                               for pp in period_years if pp <= p)
            else:
                def _pv_roof_area(_m, p):
                    return _m.rooftop_installed[p] / _st_eff

            #: the legacy single inequality charges ALL
            # district rooftop PV against the hot-water-ELIGIBLE roof alone
            # - PV on offices/retail/warehouses (177,000 m2 of non-eligible
            # roof) competes for roof it never occupies. Measured on the
            # pins the constraint binds EXACTLY (428,628.5 +
            # 63,226.0 = 491,854.5 m2 = the eligible roof to the decimal),
            # so it - not economics - is what stops rooftop PV at 64% of
            # its cap. Correct PAIR: collectors only fit hot-water roofs;
            # the TOTAL accepted roof is conserved for both users. PV is
            # fungible across categories at aggregate level (one district
            # yield), so the pair is exact, not a relaxation. Flag-gated,
            # default legacy - see Economics.solar_thermal_roof_pair_form.
            if econ.solar_thermal_roof_pair_form():
                _total_roof_m2 = caps["rooftop_pv_kwp"] / _st_eff
                m.st_eligible_cap = pyo.Constraint(
                    m.P, rule=lambda _m, p:
                        _m.st_installed[p] <= _st_roof_m2)
                m.st_roof_share = pyo.Constraint(
                    m.P, rule=lambda _m, p:
                        _pv_roof_area(_m, p) + _m.st_installed[p]
                        <= _total_roof_m2)
            else:
                m.st_roof_share = pyo.Constraint(
                    m.P, rule=lambda _m, p:
                        _pv_roof_area(_m, p) + _m.st_installed[p]
                        <= _st_roof_m2)

        # (c) heat can only serve the WATER-heating leg, never space heating
        # and never any other load.
        m.st_serve_cap = pyo.Constraint(
            m.P, m.S, rule=lambda _m, p, s:
                _m.st_serve[p, s] <= demand_mult * _st_dhw[p][s])

        # (d) STORAGE, per (month, day-type) bucket - identical shape to
        # `_batt_bucket_conserve` below. What is drawn across a bucket cannot
        # exceed what was collected in it, after standing losses. The
        # retention factor is applied ONCE per bucket at the average hold,
        # which is the same approximation the battery's round-trip makes.
        # THE HOLD TIME IS CALIBRATED AGAINST AN HOUR-BY-HOUR TANK, NOT
        # ESTIMATED FROM THE DRAW CENTROID. The obvious derivation - gap
        # between the collection centre of mass and the draw centre of mass,
        # wrapped over midnight for the 06-08 shower - gives 10.8 h and is
        # 3.7% OPTIMISTIC. It undercounts because heat arriving EARLY in the
        # collection window waits longer than the centroid suggests and is
        # losing the whole time.
        # 12.5 h reproduces `scripts/solar_thermal_match_simulation.py`, which
        # carries a cyclic tank state hour by hour, to within 0.0013 of its
        # 0.7755 effective retention. Config-driven so the calibration is
        # visible and can be re-derived if the draw shape moves.
        _st_hold_h = float((econ.technologies.get("solar_thermal") or {})
                           .get("bucket_average_hold_hours", 12.5))
        _st_ret = econ.solar_thermal_tank_retention(_st_hold_h)
        m.st_bucket_conserve = pyo.Constraint(
            m.P, m.BUCKETS, rule=lambda _m, p, mm, dt:
                sum(_m.st_serve[p, s] for s in bucket_slices[(mm, dt)])
                <= _st_ret * sum(_m.st_collect[p, s]
                                 for s in bucket_slices[(mm, dt)]))

        # (e) the tank cannot hold more than one day's store, so a bucket
        # cannot draw more than the tank can cycle in it. Mirrors
        # `_batt_bucket_cycles`.
        m.st_bucket_tank = pyo.Constraint(
            m.P, m.BUCKETS, rule=lambda _m, p, mm, dt:
                sum(_m.st_serve[p, s] for s in bucket_slices[(mm, dt)])
                <= _st_tank * _m.st_installed[p]
                   * bucket_hours[(mm, dt)] / 24.0)

    def _balance(_m, p, s):
        # REV-2: managed-EV charge-shift terms (0-bounded
        # no-ops when smart charging is off).
        effective_demand = (
            demand_mult * period_slice_demand[p][s]
            - _m.dsr_reduce[p, s] + _m.dsr_add[p, s]
            - sum(_m.ev_shift_out[p, c, s] for c in EV_CLASSES)
            + sum(_m.ev_shift_in[p, c, s] for c in EV_CLASSES)
        )
        # Solar heat displaces the electric geyser one-for-one: this district
        # heats water RESISTIVELY (there is no heat-pump water heating
        # anywhere in the config), so COP is 1.0 and a kWh of delivered heat
        # removes a kWh of electric load. Against a heat pump the divisor
        # would be its COP and the case would be far weaker - stated because
        # it is an assumption about the COUNTERFACTUAL, not a property of the
        # collector.
        # *** APPENDED AS A STATEMENT, NOT AS AN INLINE `if... else 0.0`. ***
        # The neighbouring optional terms (dc_ppa, unserved, gp) all use the
        # inline form, and that is safe FOR THEM because the current pins were
        # taken with those terms already in the expression. A NEW inline
        # `- 0.0` would add a constant to a pinned expression tree, and while
        # Pyomo very probably folds it away, "very probably" is not the
        # standard this project holds byte-exactness to. Writing it this way
        # means the off path emits the identical expression rather than one
        # that has to be argued about.
        if _st_on:
            effective_demand = effective_demand - _m.st_serve[p, s]
        # FX-1/Q-1: biomass/WTE/biogas/thermal now pay ac_eff,
        # per the documented intent (the single-period comment listed them as
        # local-bus sources "keeping ac_eff only" but the equation had them at
        # 1.0). PV remains at 1.0 (generated at/behind the load; documented).
        return (
            effective_demand + _m.charge[p, s] + _m.thermal_chg[p, s]
            + _m.exp[p, s] + (_m.dc_ppa[p, s] if _dc_ppa_on else 0.0)
            == _mp_pv_supply(_m, p, s) - _m.pv_curtail[p, s]
                 + ac_eff * _m.discharge[p, s] + ac_eff * _m.thermal_dis[p, s]
                 + ac_eff * _m.v2g[p, s] + ac_eff * _m.biomass[p, s]
                 + ac_eff * _m.wte[p, s] + ac_eff * _m.biogas[p, s]
                 + grid_import_eff_p[p] * _m.imp[p, s]
                 # B21: green purchase enters DELIVERED (losses + in-kind
                 # charges already priced into the delivered tariff).
                 + (_m.gp[p, s] if _gp_on else 0.0)
                 # RES-1: load shed closes the balance ONLY on shock clones.
                 + (_m.unserved[p, s] if _res_on else 0.0)
        )
    m.balance = pyo.Constraint(m.P, m.S, rule=_balance)

    # ---- Battery + thermal storage cycling (per period) ----------------
    # FX-1/: the old per-slice proxy (chg+dis <= cap x DoD x
    # hours/24, ~C/27 power) + per-MONTH pooling let a battery "charge" on one
    # day-type and "discharge" on another. Replaced with: (a) real C-rate
    # power caps per slice; (b) per-(month, day-type) energy conservation;
    # (c) a one-DoD-cycle-per-day energy budget per bucket.
    batt_c_rate = econ.battery_c_rate_per_hour()
    thermal_c_rate = econ.thermal_storage_c_rate_per_hour()

    def _batt_chg_power(_m, p, s):
        return _m.charge[p, s] <= _m.battery_effective[p] * batt_c_rate * hours_of[s]
    m.batt_chg_power = pyo.Constraint(m.P, m.S, rule=_batt_chg_power)
    def _batt_dis_power(_m, p, s):
        return _m.discharge[p, s] <= _m.battery_effective[p] * batt_c_rate * hours_of[s]
    m.batt_dis_power = pyo.Constraint(m.P, m.S, rule=_batt_dis_power)

    def _batt_bucket_conserve(_m, p, mm, dt):
        sids = bucket_slices[(mm, dt)]
        return (sum(_m.discharge[p, s] for s in sids)
                <= rt_eff * sum(_m.charge[p, s] for s in sids))
    m.batt_bucket_conserve = pyo.Constraint(m.P, m.BUCKETS,
                                            rule=_batt_bucket_conserve)
    def _batt_bucket_cycles(_m, p, mm, dt):
        # max one full DoD cycle per equivalent day in the bucket
        return (sum(_m.discharge[p, s] for s in bucket_slices[(mm, dt)])
                <= _m.battery_effective[p] * max_dod
                   * bucket_hours[(mm, dt)] / 24.0)
    m.batt_bucket_cycles = pyo.Constraint(m.P, m.BUCKETS,
                                          rule=_batt_bucket_cycles)

    def _thermal_chg_power(_m, p, s):
        return _m.thermal_chg[p, s] <= _m.thermal_installed[p] * thermal_c_rate * hours_of[s]
    m.thermal_chg_power = pyo.Constraint(m.P, m.S, rule=_thermal_chg_power)
    def _thermal_dis_power(_m, p, s):
        return _m.thermal_dis[p, s] <= _m.thermal_installed[p] * thermal_c_rate * hours_of[s]
    m.thermal_dis_power = pyo.Constraint(m.P, m.S, rule=_thermal_dis_power)

    def _thermal_bucket_conserve(_m, p, mm, dt):
        sids = bucket_slices[(mm, dt)]
        return (sum(_m.thermal_dis[p, s] for s in sids)
                <= thermal_rt_eff * sum(_m.thermal_chg[p, s] for s in sids))
    m.thermal_bucket_conserve = pyo.Constraint(m.P, m.BUCKETS,
                                               rule=_thermal_bucket_conserve)
    def _thermal_bucket_cycles(_m, p, mm, dt):
        return (sum(_m.thermal_dis[p, s] for s in bucket_slices[(mm, dt)])
                <= _m.thermal_installed[p] * max_dod
                   * bucket_hours[(mm, dt)] / 24.0)
    m.thermal_bucket_cycles = pyo.Constraint(m.P, m.BUCKETS,
                                             rule=_thermal_bucket_cycles)

    # ---- V2G constraints (per period) ----------------------------------
    # FX-1/: V2G energy budget per (month, day-type) bucket (was monthly) -
    # bucket_hours/24 = the bucket's equivalent days. TRJ-3:
    # the per-unit daily budget is now PERIOD-dependent (pack growth).
    def _v2g_bucket(_m, p, mm, dt):
        sids = bucket_slices[(mm, dt)]
        return (sum(_m.v2g[p, s] for s in sids)
                <= (bucket_hours[(mm, dt)] / 24.0) * v2g_day_by_period[p]
                   * _m.v2g_installed[p])
    m.v2g_bucket = pyo.Constraint(m.P, m.BUCKETS, rule=_v2g_bucket)

    def _v2g_slice_power(_m, p, s):
        return _m.v2g[p, s] <= v2g_power_kw * _m.v2g_installed[p] * hours_of[s]
    m.v2g_slice_power = pyo.Constraint(m.P, m.S, rule=_v2g_slice_power)

    # ---- Biomass / WTE / biogas constraints (per period) ---------------
    def _biomass_slice(_m, p, s):
        return _m.biomass[p, s] <= _m.biomass_installed[p] * hours_of[s]
    m.biomass_slice = pyo.Constraint(m.P, m.S, rule=_biomass_slice)
    def _biomass_annual(_m, p):
        return (sum(_m.biomass[p, s] for s in slice_ids)
                <= _m.biomass_installed[p] * biomass_hours_yr)
    m.biomass_annual = pyo.Constraint(m.P, rule=_biomass_annual)

    # FX-6 /: per-(period, month) availability ceiling (only months
    # with fraction < 1.0 get rows; the per-slice cap covers the rest).
    if biomass_constrained_months:
        def _biomass_monthly(_m, p, mm):
            sids = [s for s in slice_ids if bm_month_of[s] == mm]
            hrs = sum(hours_of[s] for s in sids)
            frac = econ.biomass_monthly_availability_fraction(mm)
            return (sum(_m.biomass[p, s] for s in sids)
                    <= frac * _m.biomass_installed[p] * hrs)
        m.biomass_monthly = pyo.Constraint(m.P, biomass_constrained_months,
                                            rule=_biomass_monthly)
    # FX-6 / N7: per-period annual straw-energy budget (each period is a
    # representative year drawing on the same district catchment).
    if biomass_straw_cap_kwh is not None:
        def _biomass_straw(_m, p):
            return (sum(_m.biomass[p, s] for s in slice_ids)
                    <= biomass_straw_cap_kwh)
        m.biomass_straw_annual = pyo.Constraint(m.P, rule=_biomass_straw)

    def _wte_slice(_m, p, s):
        return _m.wte[p, s] <= _m.wte_installed[p] * hours_of[s]
    m.wte_slice = pyo.Constraint(m.P, m.S, rule=_wte_slice)
    def _wte_annual(_m, p):
        return (sum(_m.wte[p, s] for s in slice_ids)
                <= _m.wte_installed[p] * wte_hours_yr)
    m.wte_annual = pyo.Constraint(m.P, rule=_wte_annual)

    def _biogas_slice(_m, p, s):
        return _m.biogas[p, s] <= _m.biogas_installed[p] * hours_of[s]
    m.biogas_slice = pyo.Constraint(m.P, m.S, rule=_biogas_slice)
    def _biogas_annual(_m, p):
        return (sum(_m.biogas[p, s] for s in slice_ids)
                <= _m.biogas_installed[p] * biogas_hours_yr)
    m.biogas_annual = pyo.Constraint(m.P, rule=_biogas_annual)

    # ---- Grid I/O caps -------------------------------------------------
    # SIZED GRID CONNECTION. `import_cap_kw` (600 MW) was a hard
    # cap with NO PRICE - every scenario could draw up to it for free and paid
    # the same flat Rs 8.77 crore/yr whether it peaked at 100 MW or 600. That
    # gave away one of the thesis's own claims: that a locally-supplied town
    # needs less imported infrastructure. Now the cap becomes a priced Var,
    # sized ONCE across all periods (it is a 35-year asset, built once), and
    # every place that used the constant uses the variable's kW instead.
    # When the flag is off `_conn_kw` returns the identical float, so the
    # production expression tree is byte-unchanged.
    # Full rationale: economics.yaml:interconnection.sizing.
    _ic_sizing = econ.interconnection_sizing_enabled()
    if _ic_sizing:
        m.grid_connection_mw = pyo.Var(
            bounds=(0.0, import_cap_kw / 1000.0))

        def _conn_kw(_m):
            return _m.grid_connection_mw * 1000.0
    else:
        def _conn_kw(_m):
            return import_cap_kw

    # the district's INTERNAL network (cables + substation +
    # distribution transformers) as an annualised parity constant. A
    # constant of the LAYOUT, not of the dispatch, so it is a scalar added
    # to every period's cost - the LP structure is untouched and the flag
    # off reproduces the prior pins exactly. See economics.yaml:
    # electrical_network.cost_in_production.
    from energy.electrical_assets import (
        production_network_annualised_inr,
        production_network_annualised_kgco2,
    )
    _en_prod = production_network_annualised_inr(net, econ)
    _en_prod_annual = float(_en_prod.get("annualised_total_inr", 0.0))
    #...and its EMBODIED CARBON. Costing the copper while ignoring its
    # carbon would be an asymmetry; charged at the same parity, so it
    # cannot flatter the designed town. ~0.19% of town CO2.
    _en_prod_co2 = float(production_network_annualised_kgco2(net, econ)
                         .get("annualised_total_kgco2", 0.0))

    # RES-1: month-multiplied cap variants on shock clones (blackout month
    # x0, N-1 x0.5); the else-branch keeps the original rule objects so the
    # production constraint expressions are byte-identical.
    if _res_on and (_res_imp_m or _res_exp_m):
        def _imp_cap(_m, p, s):
            return (_m.imp[p, s] <= _conn_kw(_m)
                    * _res_imp_m.get(month_of[s], 1.0) * hours_of[s])
        def _exp_cap(_m, p, s):
            return (_m.exp[p, s] <= export_cap_kw
                    * _res_exp_m.get(month_of[s], 1.0) * hours_of[s])
    else:
        def _imp_cap(_m, p, s):
            return _m.imp[p, s] <= _conn_kw(_m) * hours_of[s]
        def _exp_cap(_m, p, s):
            return _m.exp[p, s] <= export_cap_kw * hours_of[s]
    m.imp_cap = pyo.Constraint(m.P, m.S, rule=_imp_cap)

    if _gp_on:
        # B21 drawal shape: the contracted park delivers per-kWp what the
        # district's own TRACKED farm delivers in that slice (same Punjab
        # insolation clock; GSA v5 dayparts; 1 MW = 1,000 kWp). yield_farm[s]
        # is kWh per kWp per slice, so the bound is already energy.
        def _gp_shape(_m, p, s):
            return (_m.gp[p, s] <= _m.gp_mw[p] * 1000.0
                    * yield_farm[s] * tracked_yield_mult)
        m.gp_shape = pyo.Constraint(m.P, m.S, rule=_gp_shape)

        # B21 shared physical import ceiling: grey import + wheeled green
        # arrive over the SAME 600 MW substation connection (imp is capped
        # source-side above; the wheeled-green flow at the district
        # connection ~= delivered gp - the in-kind extra is injected at the
        # GENERATOR end and lost en route).
        # RES-1: the wheeled green flow rides the SAME physical connection,
        # so the blackout/N-1 month multiplier applies here too (a grid
        # outage takes the green OA down with it).
        if _res_on and _res_imp_m:
            def _gp_shared_import_cap(_m, p, s):
                return (_m.imp[p, s] + _m.gp[p, s]
                        <= _conn_kw(_m)
                        * _res_imp_m.get(month_of[s], 1.0) * hours_of[s])
        else:
            def _gp_shared_import_cap(_m, p, s):
                return (_m.imp[p, s] + _m.gp[p, s]
                        <= _conn_kw(_m) * hours_of[s])
        m.gp_shared_import_cap = pyo.Constraint(
            m.P, m.S, rule=_gp_shared_import_cap)
    m.exp_cap = pyo.Constraint(m.P, m.S, rule=_exp_cap)

    # ---- REV-3 scenario hook: planning reserve margin ------
    # Firm, capacity-credit-weighted supply must cover (1 + margin) x the
    # period's PEAK hourly load (pre-DSR, conservative). PV credits 0
    # (evening-peak convention); built ONLY when the hook is enabled
    # (scenario_hooks.reserve_margin) - A/B stress runs, never production.
    _rm = econ.reserve_margin_params()
    if _rm:
        _rm_margin = float(_rm.get("margin_fraction", 0.15))
        _rm_cc = _rm.get("capacity_credit") or {}
        _rm_peak_kw = {
            p: max(demand_mult * period_slice_demand[p][s] / hours_of[s]
                   for s in slice_ids if hours_of[s] > 0)
            for p in period_years
        }
        _batt_c_rate_rm = econ.battery_c_rate_per_hour()

        def _reserve_margin(_m, p):
            firm_kw = (
                float(_rm_cc.get("grid_import", 1.0)) * import_cap_kw
                + float(_rm_cc.get("battery", 1.0))
                * _m.battery_effective[p] * _batt_c_rate_rm
                + float(_rm_cc.get("v2g", 0.5))
                * v2g_power_kw * _m.v2g_installed[p]
                + float(_rm_cc.get("biomass", 0.9)) * _m.biomass_installed[p]
                + float(_rm_cc.get("wte", 0.9)) * _m.wte_installed[p]
                + float(_rm_cc.get("biogas", 0.9)) * _m.biogas_installed[p]
            )
            return firm_kw >= (1.0 + _rm_margin) * _rm_peak_kw[p]
        m.reserve_margin = pyo.Constraint(m.P, rule=_reserve_margin)

    if _dc_ppa_on:
        # (1) Per-slice offtake cap = dedicated-line / DC intake capacity.
        # `==` when the contract is FIRM BASELOAD, `<=` when it
        #     follows surplus (the production default). See the flag read above.
        def _dc_ppa_cap(_m, p, s):
            if _dc_firm_baseload:
                return _m.dc_ppa[p, s] == _dc_offtake_cap_kw * hours_of[s]
            return _m.dc_ppa[p, s] <= _dc_offtake_cap_kw * hours_of[s]
        m.dc_ppa_cap = pyo.Constraint(m.P, m.S, rule=_dc_ppa_cap)
        # (2) Aggregate annual cap: the district must stay a NET consumer for
        # reliability balance — PPA sales <= max_share x annual demand.
        def _dc_ppa_annual_cap(_m, p):
            annual_demand = demand_mult * sum(period_slice_demand[p][s]
                                              for s in slice_ids)
            return (sum(_m.dc_ppa[p, s] for s in slice_ids)
                    <= _dc_max_share * annual_demand)
        m.dc_ppa_annual_cap = pyo.Constraint(m.P, rule=_dc_ppa_annual_cap)
        # (3) ANTI-ARBITRAGE (bound_by_surplus_not_baseload): grid import may
        # only serve district demand + storage charging — NEVER feed export or
        # the PPA. This stops the optimiser importing cheap grid power to resell
        # to the DC (which, without this, raised emissions ~13%). Forces the PPA
        # to absorb genuine renewable SURPLUS, per the scaffold's design.
        # *** STRENGTHENED. The comment above claimed import may
        # "NEVER feed export or the PPA", but the constraint did not say that:
        # it only capped import at demand + charging, which still permits a
        # slice to import for the houses AND sell to the data centre at the
        # same time. That is precisely the behaviour
        # "the town sold energy first to dc then imported electricity from
        # grid to power homes". Selling at the PPA price while importing in
        # the SAME slice is a resale, whatever the energy accounting says.
        # The fix puts export and PPA offtake on the same side as import, so
        # the three together cannot exceed what the district itself consumes:
        #     imp_eff + exp + dc_ppa  <=  eff_dem + charge + thermal_chg
        # If import already covers demand, dc_ppa and exp are forced to zero.
        # If the district is not importing, the term is slack and the ENERGY
        # BALANCE is what limits the sale - i.e. real surplus.
        # WHY THIS FORM AND NOT THE OBVIOUS ONE. The natural statement is
        # `dc_ppa <= max(0, local_generation - demand)`, but a max of a
        # variable expression is not linear, and writing it without the max
        # makes every low-generation slice INFEASIBLE (it would demand
        # dc_ppa <= a negative number while dc_ppa >= 0). Doing it with a
        # binary would turn the LP into a MILP across 2,592 slice-periods.
        # The form above is linear, always feasible (imp = exp = dc_ppa = 0
        # satisfies it), and enforces the same intent.
        # SCOPE: this lives INSIDE `if _dc_ppa_on`, so the production path
        # (PPA disabled) is structurally untouched and stays byte-exact.
        # *** FORM IS NOW SWITCHABLE - see the investigation
        # note below. `ppa.anti_arbitrage_form`:
        #   "strict"     = the form (import + export + PPA capped
        #                  at demand + charging). DEFAULT, unchanged.
        #   "import_cap" = the pre- form (import alone capped at
        #                  demand + charging).
        # WHY THIS IS BEING QUESTIONED. Turning the PPA on made the model
        # build a SMALLER 2030 solar farm - 92,514 kWp against 201,000 kWp
        # with the PPA off - i.e. it built LESS solar when offered a BETTER
        # price. That is backwards, and the strict form is the suspect: with
        # import at zero it still reads `exp + dc_ppa <= eff_dem + charge`,
        # so PPA sales DISPLACE export headroom instead of adding to it, and
        # the marginal 2030 panel loses its outlet.
        # WHY THE WEAKER FORM MAY ACTUALLY BE CORRECT. Under `import_cap`
        # the energy balance ALREADY guarantees sales are generation-backed:
        #     gen + imp = eff_dem + charge + exp + ppa + curtail
        #     imp <= eff_dem + charge   =>   exp + ppa <= gen - curtail
        # So no imported kWh can reach the data centre either way. The only
        # thing the strict form adds is a ban on importing and selling in the
        # SAME SLICE - and a slice here is ~22 aggregated hours of one month
        # and day-type, within which a town can legitimately import at 19:00
        # and export at 12:00. Forbidding that is an artifact of temporal
        # aggregation, not a real arbitrage guard.
        # DO NOT change the default on this reasoning alone - it is an
        # argument, not a measurement. scripts/ppa_anti_arbitrage_probe.py
        # measures it.
        # measurement below, not on the argument above.
        # ppa_anti_arbitrage_probe_20260811.txt, three solves, one variable:
        #     PPA off                 2030 farm 201,000 kWp
        #     PPA on, strict           2030 farm  92,705 kWp   (-53.9%)
        #     PPA on, import_cap       2030 farm 201,000 kWp   (+0.0%)
        # The strict form was suppressing 108,295 kWp of 2030 solar farm,
        # 141 GWh of exports and Rs 600 M of lifetime saving, and it was the
        # sole cause of the "PPA-ON costs MORE in the base year" anomaly
        # (2,005.4 M -> 1,749.7 M once relaxed). A guard that changes a
        # capacity investment decision by 54% is not a guard, it is a
        # distortion.
        # THE INTENT SURVIVES: under import_cap the energy balance still
        # proves no imported kWh reaches the data centre, because
        #     gen + imp = eff_dem + charge + exp + ppa + curtail
        #     imp <= eff_dem + charge   =>   exp + ppa <= gen - curtail
        # What is GIVEN UP is only the ban on importing and selling within
        # the SAME slice - and a slice is one hour-band repeated over ~22
        # days of a month, so that pattern is as likely to be genuine
        # day-to-day variation as arbitrage. STATE THAT LIMITATION rather
        # than claiming the stronger guard.
        # "strict" is retained and reachable, and its cost is measured, so
        # the choice is defensible either way at viva.
        _aa_form = str((econ.__dict__.get("ppa_raw", {}) or {})
                       .get("anti_arbitrage_form", "import_cap")).lower()

        def _no_import_resale(_m, p, s):
            eff_dem = (demand_mult * period_slice_demand[p][s]
                       - _m.dsr_reduce[p, s] + _m.dsr_add[p, s])
            lhs = grid_import_eff_p[p] * _m.imp[p, s]
            if _aa_form != "import_cap":
                lhs = lhs + _m.exp[p, s] + _m.dc_ppa[p, s]
            return lhs <= eff_dem + _m.charge[p, s] + _m.thermal_chg[p, s]
        m.dc_ppa_no_import_resale = pyo.Constraint(m.P, m.S,
                                                   rule=_no_import_resale)

        # THE RULE, in one sentence: NO ROOFTOP OF ANY KIND MAY SUPPLY THE
        # DATA CENTRE. Only ground-, water- and parking-mounted PUBLIC solar
        # can - the solar farm, the carports and the floating PV.
        # WHY. The model pools all generation at one bus, so without this the
        # PPA is served from an undifferentiated mix that includes 95,915 kWp
        # of PRIVATE high-income/commercial rooftop and 21,719 kWp of RWA
        # pooled apartment roofs.
        # panels on their homes so a hyperscaler could buy the output;
        # private and RWA rooftops serve the town or export to the grid, and
        # that is all. EWS social housing is excluded too (
        # revision) - selling generation off the roofs of the most
        # energy-poor group in the model is not defensible whoever owns the
        # asset. Public-BUILDING rooftops (schools, healthcare) fall out on
        # the same "no rooftop" line, which is why the rule is stated by
        # MOUNTING rather than by owner: it needs no per-owner carve-outs.
        # WHAT IT DOES NOT CLAIM. This is a per-slice CEILING on the sale,
        # not an electron-tagging scheme - a single-bus model cannot tag
        # electrons and should not pretend to. It guarantees the district
        # never sells the data centre more, in any slice, than its eligible
        # public plant physically produced in that slice. Combined with
        # constraint (3), which already bars import-and-resell, the sale is
        # provably backed by eligible on-site generation.
        # EXCLUDED AND WHY: rooftop + BIPV (private/RWA/EWS/public roofs, by
        # the rule above); biomass CHP, waste-to-energy and biogas
        # municipal dispatchable plant serves the town, not a data centre);
        # battery and V2G discharge (stored energy has no single source and
        # would launder ineligible generation through the store).
        # EXPECT THE SALE TO FALL. In the unconstrained run, 164 of the 354
        # selling slices had PV alone short of demand + PPA, i.e. the CHP
        # fleet was making up the difference. Those slices must now sell less.
        # A drop is the constraint WORKING, not a regression.
        def _dc_ppa_eligible_sources(_m, p, s):
            eligible = 0.0
            for pp in period_years:
                if pp > p:
                    break
                farm_age = econ.pv_vintage_yield_factor("solar_farm", pp, p)
                eligible += yield_farm[s] * _m.farm_fixed_new[pp] * farm_age
                eligible += (yield_farm[s] * tracked_yield_mult
                             * _m.farm_tracked_new[pp] * farm_age)
                eligible += yield_farm[s] * _m.carport_new[pp] * farm_age
                _fpv_y = yield_farm[s] * fpv_yield_mult
                if _res_fpv_slice is not None:
                    _fpv_y *= _res_fpv_slice.get(s, 1.0)
                eligible += _fpv_y * _m.floating_pv_new[pp] * farm_age
            return _m.dc_ppa[p, s] <= eligible
        m.dc_ppa_eligible_sources = pyo.Constraint(
            m.P, m.S, rule=_dc_ppa_eligible_sources)

    # ---- Per-period CAPEX (vintaged) -----------------------------------
    # Base annualised CAPEX (constant across periods; vintage-CAPEX
    # learning is applied per build year via period_capex_factor).
    base_rooftop_annual = econ.rooftop_pv_annualised_inr_per_kwp()
    base_farm_annual = econ.solar_farm_annualised_inr_per_kwp()
    base_tracked_annual = econ.tracked_pv_annualised_inr_per_kwp()
    base_battery_annual = econ.battery_annualised_inr_per_kwh()
    base_v2g_annual = econ.v2g_annualised_inr_per_unit()
    base_biomass_annual = econ.biomass_chp_annualised_inr_per_kw_e()
    base_wte_annual = econ.wte_annualised_inr_per_kw_e()
    base_biogas_annual = econ.biogas_annualised_inr_per_kw_e()
    base_thermal_annual = econ.thermal_storage_annualised_inr_per_kwh()
    base_bipv_annual = econ.bipv_annualised_inr_per_kwp()
    base_carport_annual = econ.carport_annualised_inr_per_kwp()
    base_floating_pv_annual = econ.floating_pv_annualised_inr_per_kwp()
    base_st_annual = (econ.solar_thermal_blended_annualised_inr_per_m2()
                      if _st_on else 0.0)

    capex_factor: Dict[Tuple[str, int], float] = {}
    for vy in period_years:
        for tech in ("rooftop_pv", "solar_farm", "li_ion_battery",
                     "v2g_charger", "biomass_chp", "wte_plant",
                     "biogas_plant", "thermal_cold_storage",
                     "bipv_facade", "solar_carport", "floating_pv"):
            capex_factor[(tech, vy)] = econ.period_capex_factor(tech, vy)

    # PMSGY: snapshot subsidy is already baked into base_rooftop_annual.
    # Per-vintage correction (1 - sub_at_vy) / (1 - snapshot_sub) restores
    # the vintage-actual subsidy. Stacked onto rooftop CAPEX for rooftop +
    # BIPV (both consume the snapshot subsidy via the rooftop helper).
    snapshot_sub = econ.rooftop_pv_capex_subsidy_fraction()
    snapshot_denom = max(1e-9, 1.0 - snapshot_sub)
    pmsgy_adj: Dict[int, float] = {}
    for vy in period_years:
        sub_at_vy = econ.pmsgy_subsidy_fraction_at_year(vy)
        pmsgy_adj[vy] = (1.0 - sub_at_vy) / snapshot_denom

    def _capex_annual_p(p):
        total = 0.0
        for vy in period_years:
            if vy > p:
                break
            total += (
                m.rooftop_new[vy]
                * base_rooftop_annual * rooftop_capex_mult
                * capex_factor[("rooftop_pv", vy)] * pmsgy_adj[vy]
            )
            total += (m.farm_fixed_new[vy] * base_farm_annual
                      * capex_factor[("solar_farm", vy)])
            total += (m.farm_tracked_new[vy] * base_tracked_annual
                      * capex_factor[("solar_farm", vy)])
            total += (m.battery_new[vy] * base_battery_annual
                      * capex_factor[("li_ion_battery", vy)])
            total += (m.v2g_new[vy] * base_v2g_annual
                      * capex_factor[("v2g_charger", vy)])
            total += (m.biomass_new[vy] * base_biomass_annual
                      * capex_factor[("biomass_chp", vy)])
            total += (m.wte_new[vy] * base_wte_annual
                      * capex_factor[("wte_plant", vy)])
            total += (m.biogas_new[vy] * base_biogas_annual
                      * capex_factor[("biogas_plant", vy)])
            total += (m.thermal_new[vy] * base_thermal_annual
                      * capex_factor[("thermal_cold_storage", vy)])
            total += (m.bipv_new[vy] * base_bipv_annual
                      * capex_factor[("bipv_facade", vy)] * pmsgy_adj[vy])
            total += (m.carport_new[vy] * base_carport_annual
                      * capex_factor[("solar_carport", vy)])
            total += (m.floating_pv_new[vy] * base_floating_pv_annual
                      * capex_factor[("floating_pv", vy)])
            # SOLAR WATER HEATING. Priced per m2 of aperture at the blended
            # cost of capital, NET of the geyser it replaces (MNRE: one
            # appliance with an integral booster, not two).
            # NO `capex_factor` MULTIPLIER, AND THAT IS DELIBERATE. Every
            # technology above gets a learning-curve decline; solar thermal
            # is a mature, low-volume, largely mechanical product with no
            # published Indian learning rate. Handing it PV's decline would
            # be the CAPEX-DERIVED error in reverse - inventing
            # a cost fall rather than omitting one. Flat-real is the
            # conservative choice and is stated as an assumption.
            if _st_on:
                total += m.st_new[vy] * base_st_annual
        return total

    # ---- Per-period cost / emissions / weighted lifetime ---------------
    rel_hours = econ.outage_hours_per_year()
    rel_cov = econ.reliability_coverage_fraction()
    diesel_inr = econ.diesel_displacement_value_inr_per_kwh()
    # SYMMETRIC DIESEL, per period. The critical outage energy
    # grows with each period's demand, so the ceiling on displaceable diesel
    # grows too - the same reason the DSR pool grows without its fraction
    # changing. See economics.yaml reliability block.
    _sym_diesel = econ.symmetric_diesel_backup_enabled()
    _diesel_emiss = econ.diesel_displacement_emission_kgco2_per_kwh()
    if _sym_diesel:
        _crit_outage = {
            p: econ.critical_outage_energy_kwh(
                sum(period_slice_demand[p][s] for s in slice_ids))
            for p in period_years
        }
        m.diesel_backup = pyo.Var(m.P, within=pyo.NonNegativeReals)

        _chp_avail = econ.chp_outage_availability()

        def _diesel_backup_rule(_m, p):
            storage = ((_m.battery_installed[p]
                        + _m.v2g_installed[p] * v2g_day_by_period[p])
                       * rel_hours * rel_cov / 24.0)
            # The CHP fleet is what actually rides through a grid cut -
            # measured 100% critical service in every period, including 2030
            # with zero battery. Omitting it charged the town for diesel it
            # never burns. Full note in economics.yaml.
            chp = ((_m.biomass_installed[p] + _m.wte_installed[p]
                    + _m.biogas_installed[p]) * rel_hours * _chp_avail)
            return _m.diesel_backup[p] >= _crit_outage[p] - storage - chp

        m.diesel_backup_def = pyo.Constraint(m.P, rule=_diesel_backup_rule)

    def _annual_cost_p(_m, p):
        capex_term = _capex_annual_p(p)
        tariff_mult = period_tariff_mult[p]
        # is now FLAT-REAL - tariff_mult applies to the IMPORT line only. The
        # old expression escalated the feed-in at the import tariff's +2.5%/yr
        # real (Rs 3.00 -> effectively 5.55 by 2055), while duck-curve reality
        # for solar-hour feed-in is flat-to-FALLING as grid solar saturates.
        # Flat-real is the conservative middle; the DEM-3 hook's
        # duck_exp multiplier (A/B) models the falling path on top of it.
        if _duck_on:
            # DEM-3 A/B: midday cheapens / evening firms; feed-in falls.
            grid_cost = (
                sum(import_tariff[s] * duck_imp[(p, s)] * tariff_mult
                    * _m.imp[p, s] for s in slice_ids)
                - duck_exp[p]
                * sum(export_tariff[s] * _m.exp[p, s] for s in slice_ids)
            )
        else:
            grid_cost = (
                sum(import_tariff[s] * tariff_mult * _m.imp[p, s] for s in slice_ids)
                - sum(export_tariff[s] * _m.exp[p, s] for s in slice_ids)
            )
        # FX-6: biomass fuel is per-slice (monthly storage-cost multiplier).
        # TRJ-4: x the period's straw-competition price path.
        fuel_term = (biomass_fuel_period_mult[p]
                     * sum(biomass_fuel_by_slice[s] * _m.biomass[p, s]
                           for s in slice_ids)
                     + wte_fuel * sum(_m.wte[p, s] for s in slice_ids)
                     + biogas_fuel * sum(_m.biogas[p, s] for s in slice_ids))
        v2g_cost_term = v2g_deg * sum(_m.v2g[p, s] for s in slice_ids)
        # RES-1: load shed priced at VoLL (CEA RA Guidelines Rs 140/kWh,
        # economics.yaml citations). 0.0 term unless the hook is on.
        unserved_cost = (
            _res_voll * sum(_m.unserved[p, s] for s in slice_ids)
            if _res_on else 0.0
        )
        dsr_cost_term = dsr_comfort * sum(_m.dsr_reduce[p, s]
                                            for s in slice_ids)
        # REV-2: managed-charging programme fee per shifted kWh.
        ev_smart_cost_term = ev_program_cost * sum(
            _m.ev_shift_out[p, c, s] for c in EV_CLASSES for s in slice_ids
        )
        # TRJ-3: reliability credit uses the PERIOD's per-unit
        # V2G energy (pack growth) - consistent with the V2G energy budget.
        if _sym_diesel:
            # Charged to EVERY scenario incl. BAU, and CAPPED at the diesel
            # that would actually have been burned - the old credit had no
            # ceiling, so more battery always bought more credit.
            reliability_credit = -diesel_inr * _m.diesel_backup[p]
        else:
            reliability_credit = (
                (_m.battery_installed[p]
                 + _m.v2g_installed[p] * v2g_day_by_period[p])
                * rel_hours * rel_cov / 24.0 * diesel_inr
            )
        # Data-centre PPA: NET revenue (credit) at the wheeling/CSS-adjusted
        # price — FIXED real (price certainty is the PPA's value), so NOT scaled
        # by tariff_mult — minus the annual FIXED cost (annualised
        # interconnection+legal CAPEX + admin) incurred once the PPA is signed.
        dc_ppa_revenue = (
            _dc_ppa_price * sum(_m.dc_ppa[p, s] for s in slice_ids)
            if _dc_ppa_on else 0.0
        )
        # DEM-8 A/B: carbon price on OPERATIONAL emissions
        # (grid import at the period EF + local fuel emissions). Embodied
        # carbon is deliberately excluded - it is priced where the kit is
        # manufactured, not on the district's compliance bill. 0.0 term
        # unless the scenario hook is enabled (2030 price is 0 even then,
        # so the headline year is untouched; the BUILD may shift).
        cp = carbon_price_by_period[p]
        carbon_cost_term = (
            cp * (period_emiss[p] * sum(_m.imp[p, s] for s in slice_ids)
                  + biomass_emiss * sum(_m.biomass[p, s] for s in slice_ids)
                  + wte_emiss * sum(_m.wte[p, s] for s in slice_ids)
                  + biogas_emiss * sum(_m.biogas[p, s] for s in slice_ids))
            if cp > 0.0 else 0.0
        )
        # B21: buy-side green purchase energy at the DELIVERED
        # price (real, like the dc-PPA's - price certainty is the PPA's
        # value, so NOT scaled by tariff_mult) + the fixed OA admin charged
        # once the block is enabled (the dc-ppa standing-charge convention).
        gp_cost = (
            _gp_price * sum(_m.gp[p, s] for s in slice_ids) + _gp_admin
            if _gp_on else 0.0
        )
        # B21 PARITY lines - applied to EVERY scenario INCLUDING BAU (the
        # BAU town needs the same substations, exports the same waste,
        # drinks the same water; accessors return 0.0 while disabled):
        # interconnection CRF + waste gate fee + canal water charge.
        # when the connection is SIZED, the flat interconnection
        # charge is REPLACED by the per-MW charge on the sized capacity - it
        # is not added on top, or the connection would be paid for twice.
        # Boundary opex stays flat either way (it is waste + canal handling,
        # not a wire). Parity is preserved: BAU is sized by the same rule.
        if _ic_sizing:
            _interconnect_term = (econ.interconnection_annualised_inr_per_mw()
                                  * _m.grid_connection_mw)
        else:
            _interconnect_term = econ.interconnection_annualised_inr()
        b21_parity = (_interconnect_term + econ.boundary_opex_annual_inr(p)
                      + _en_prod_annual)
        # B21/TRJ-7: rent on the GRANTED farm hectares - farm scenarios
        # only (BAU has no farm; asymmetry stated in FINDINGS).
        b21_land_rent = (
            econ.farm_land_rent_annual_inr(p)
            if getattr(scenario, "allow_solar_farm", False) else 0.0
        )
        return (capex_term + grid_cost + fuel_term + v2g_cost_term
                + unserved_cost
                + dsr_cost_term + ev_smart_cost_term + carbon_cost_term
                - reliability_credit
                - dc_ppa_revenue + _dc_ppa_annual_fixed
                + gp_cost + b21_parity + b21_land_rent)
    m.annual_cost_by_period = pyo.Expression(m.P, rule=_annual_cost_p)

    def _annual_emissions_p(_m, p):
        ef_p = period_emiss[p]
        op = (
            ef_p * sum(_m.imp[p, s] for s in slice_ids)
            + biomass_emiss * sum(_m.biomass[p, s] for s in slice_ids)
            + wte_emiss * sum(_m.wte[p, s] for s in slice_ids)
            + biogas_emiss * sum(_m.biogas[p, s] for s in slice_ids)
        )
        # diesel CO2 on the uncovered outage load. Was dead
        # config until now - BAU's genset emissions were simply not counted.
        if _sym_diesel:
            op = op + _diesel_emiss * _m.diesel_backup[p]
        if econ.include_embodied_carbon():
            emb = econ.embodied_carbon()
            techs = econ.technologies
            rooftop_emb = emb.get("rooftop_pv_kgco2_per_kwp", 0)
            farm_emb = emb.get("solar_farm_kgco2_per_kwp", 0)
            tracked_extra = emb.get("tracked_pv_extra_kgco2_per_kwp", 0)
            batt_emb = emb.get("li_ion_battery_kgco2_per_kwh", 0)
            v2g_emb = emb.get("v2g_charger_kgco2_per_unit", 0)
            biomass_emb = emb.get("biomass_chp_kgco2_per_kw_e", 0)
            wte_emb = emb.get("wte_plant_kgco2_per_kw_e", 0)
            biogas_emb = emb.get("biogas_plant_kgco2_per_kw_e", 0)
            thermal_emb = emb.get("thermal_storage_kgco2_per_kwh", 0)
            eol = 1.0 + econ.end_of_life_carbon_fraction()
            # PV embodied carbon is now PER VINTAGE, because a
            # panel built in 2055 does not carry a 2030 factory's footprint
            # (module carbon intensity fell 0.61 -> 0.17 kgCO2/W over the
            # recent survey period). Same treatment the model already gives
            # vintage CAPEX. Every other technology keeps its flat factor, so
            # their expression trees are unchanged.
            _rt_life = int(techs["rooftop_pv"]["lifetime_years"])
            _fm_life = int(techs["solar_farm"]["lifetime_years"])
            _rt_emb_vintaged = sum(
                econ.embodied_kgco2_per_unit_at("rooftop_pv_kgco2_per_kwp", vy)
                * eol * _m.rooftop_new[vy] / _rt_life
                for vy in period_years if vy <= p
            )
            _fm_emb_vintaged = sum(
                econ.embodied_kgco2_per_unit_at("solar_farm_kgco2_per_kwp", vy)
                * eol * _m.farm_fixed_new[vy] / _fm_life
                for vy in period_years if vy <= p
            )
            _tr_emb_vintaged = sum(
                (econ.embodied_kgco2_per_unit_at("solar_farm_kgco2_per_kwp", vy)
                 + tracked_extra)
                * eol * _m.farm_tracked_new[vy] / _fm_life
                for vy in period_years if vy <= p
            )
            op = op + (
                _rt_emb_vintaged + _fm_emb_vintaged + _tr_emb_vintaged
                + batt_emb * eol * _m.battery_installed[p]
                  / int(techs["li_ion_battery"]["lifetime_years"])
                + v2g_emb * eol * _m.v2g_installed[p]
                  / int(techs["v2g_charger"]["lifetime_years"])
                + biomass_emb * eol * _m.biomass_installed[p]
                  / int(techs["biomass_chp"]["lifetime_years"])
                + wte_emb * eol * _m.wte_installed[p]
                  / int(techs["wte_plant"]["lifetime_years"])
                + biogas_emb * eol * _m.biogas_installed[p]
                  / int(techs["biogas_plant"]["lifetime_years"])
                + thermal_emb * eol * _m.thermal_installed[p]
                  / int(techs["thermal_cold_storage"]["lifetime_years"])
            )
        # embodied carbon of the district's OWN internal network
        # (cables + substation + distribution transformers). A constant of
        # the layout, added to every period at PARITY - same treatment, and
        # same justification, as the cost side. Deliberately OUTSIDE the
        # include_embodied_carbon branch above: the accessor applies that
        # gate itself, so this line reads the same whether the branch ran.
        # No end-of-life uplift: the ENWL factor is A1-3 product stage and
        # the transformer source is manufacturing-only, so applying the PV
        # end-of-life fraction would be borrowing an uplift from a
        # different boundary.
        op = op + _en_prod_co2
        return op
    m.annual_emissions_by_period = pyo.Expression(m.P,
                                                    rule=_annual_emissions_p)

    # Weighted lifetime cost = LP objective cost term (replaces post-hoc
    # projection). Weighted lifetime emissions = total kgCO2 across horizon.
    m.lifetime_cost_expr = pyo.Expression(
        expr=sum(weights[p] * m.annual_cost_by_period[p] for p in period_years)
    )
    m.lifetime_emissions_expr = pyo.Expression(
        expr=sum(weights[p] * m.annual_emissions_by_period[p]
                  for p in period_years)
    )

    # For diagnostic compatibility with the single-period model, also
    # expose ``cost_expr`` / ``emissions_expr`` as the 2030-period values
    # (these are what get extracted into ``annual_cost_inr`` /
    # ``annual_emissions_kgco2`` so the headline stays comparable to the
    # single-period baseline).
    m.cost_expr = pyo.Expression(expr=m.annual_cost_by_period[base_year])
    m.emissions_expr = pyo.Expression(
        expr=m.annual_emissions_by_period[base_year]
    )

    carbon_price = econ.carbon_price_inr_per_kgco2()
    m.cost = pyo.Objective(
        expr=((1.0 - alpha) * m.lifetime_cost_expr
              + alpha * carbon_price * m.lifetime_emissions_expr),
        sense=pyo.minimize,
    )

    return m, period_years, slice_ids, hours_of, weights


def _pyomo_termination(results) -> Tuple[bool, str]:  # pragma: no cover
    """Read the termination condition off a Pyomo solve result, robust to
    both the classic (``results.solver.termination_condition``) and the
    appsi (``results.termination_condition``) interfaces — which use
    DIFFERENT enum classes — by comparing the condition's ``.name`` string.

    Returns ``(ok, name)`` where ``ok`` is False for infeasible / unbounded /
    error / no-solution outcomes (so the caller never silently reads stale
    ``pyo.value(...)`` off an unsolved model). Unknown / missing condition is
    treated as OK for back-compat with solvers that don't report one.
    """
    tc = getattr(results, "termination_condition", None)
    if tc is None:
        solver_res = getattr(results, "solver", None)
        tc = getattr(solver_res, "termination_condition", None) if solver_res else None
    if tc is None:
        return True, "unknown"
    name = str(getattr(tc, "name", tc)).lower()
    bad = ("infeasible", "unbounded", "error", "nosolution",
           "maxtimelimit", "maxiterations", "intermediatenonint")
    if any(b in name for b in bad):
        return False, name
    return True, name


def _solve_pyomo(model, verbose: bool = False,
                 highs_options: Optional[dict] = None) -> str:  # pragma: no cover
    """Try HiGHS, then CBC, then GLPK. Return solver-name string.

    Raises RuntimeError if an available solver RUNS but terminates
    non-optimally (infeasible / unbounded / error) — a definitive answer, so
    we do NOT fall through to a weaker solver in that case. Only solver
    construction / availability failures cascade to the next candidate.
    Set ``verbose=True`` to stream the solver log (``tee``) — used by the
    Stage D Phase 2 FULL LP to surface WHERE a large solve goes wrong.

    ``highs_options`` (HiGHS only) sets native HiGHS options as a dict, e.g.
    ``{"solver": "ipm", "run_crossover": "on"}`` to use interior-point instead
    of dual simplex (which cycles on the degenerate Phase 2 LP), or
    ``{"user_bound_scale": -15}`` to rescale pathologically large bounds.
    """
    candidates = [
        ("highs", "appsi_highs"),
        ("cbc", "cbc"),
        ("glpk", "glpk"),
    ]
    last_error: Optional[str] = None
    for label, factory_arg in candidates:
        try:
            solver = pyo.SolverFactory(factory_arg)
            if not solver.available(exception_flag=False):
                continue
        except Exception as exc:
            last_error = f"{label}: {exc}"
            continue
        # HiGHS-native options (IPM, scaling). Only the appsi HiGHS interface
        # exposes ``highs_options``; ignored for the CBC / GLPK fallbacks.
        if highs_options and label == "highs":
            try:
                solver.highs_options = dict(highs_options)
            except Exception as exc:  # never let option-setting abort the solve
                if verbose:
                    print(f"  [_solve_pyomo] could not set highs_options: {exc}",
                          flush=True)
        # Solver is available — run it. A non-optimal termination is a
        # DEFINITIVE answer (a weaker solver won't disagree), so raise.
        results = solver.solve(model, tee=verbose)
        ok, cond = _pyomo_termination(results)
        if verbose:
            print(f"  [_solve_pyomo] {label} termination: {cond}", flush=True)
        if not ok:
            raise RuntimeError(f"{label} terminated non-optimal: {cond}")
        return f"pyomo:{label}"
    raise RuntimeError(
        "no Pyomo-compatible solver available "
        "(install highspy / cbc / glpk). "
        f"last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Stage D scaffold — per-cell / multi-bus LP
# ---------------------------------------------------------------------------
def _solve_dispatch_pyomo_stage_d(
    net: EnergyNetwork,
    econ: Economics,
    scenario_name: str,
    scenario: Scenario,
    alpha: float = 0.0,
) -> DispatchResult:  # pragma: no cover
    """Stage D per-cell / multi-bus LP entry point.

    **Phase status:**
    * Phase 1 ``per_cell_buses`` — **LANDED**. Per-cell breakdown via
      ``_stage_d_per_cell_breakdown`` attributes single-bus PV / V2G /
      demand to physical cells (rooftop / solar farm / carport /
      floating PV by physical cap-share; V2G by per-income EV ownership
      × willingness × households) and district-shared items
      (battery / biomass / WTE / biogas / grid I/O / DSR) to a virtual
      ``"district_slack"`` bucket. Reconciliation is BY CONSTRUCTION;
      verified by ``_stage_d_reconcile``. Solve time identical to the
      single-bus path (no extra LP Vars).
    * Phase 2 ``per_edge_cable_flow`` — **AUDIT LANDED** (full
      LP-integrated version is a future increment, see §14). Post-hoc
      per-edge cable-flow audit via ``_stage_d_phase2_edge_flow_audit``:
      864 small min-Σ|f| LPs (one per slice) solve KCL on the
      ROAD-ROAD topology given the Phase 1 per-cell injections + a
      substation cell (most central road, ``(12, 12)`` on optimised_sa).
      Reports per-edge annual flow + congestion events + infeasible
      slices. The dispatch LP optimum is UNCHANGED — this surfaces the
      data layer (per-edge flows) that Stage E NPV / viewer cell-flow
      arrows / Phase 4 P2P trading need. The full Phase 2 (per-cell
      curtailment Vars + LP feedback so the dispatch optimum DIVERGES
      from single-bus when 6 MW caps bind) is deferred to keep this
      session's scope tractable (~2 M new LP Vars).
    * Phase 3 ``dc_power_flow`` — NOT YET. Linearised DC + piecewise
      losses on |f|/thermal.
    * Phase 4 ``p2p_trading`` — NOT YET. Cell-to-cell exchange Var
      priced at ``econ.stage_d_p2p_tariff_inr_per_kwh`` (~4.5 INR/kWh
      mid import/export).

    Scope (per `_spec/stage_d_prompt.md` + this session's Phase 1 landing):

    1. Per-cell / multi-bus balance: each built cell is a bus with its
       own demand + local PV/storage; balance per (cell, period, slice).
       Phase 1 attributes the single-bus optimum onto cells; Phase 2
       upgrades to a real per-cell LP.
    2. Per-edge cable flow + KCL on the ROAD-ROAD topology, with
       linearised DC power-flow approximation + per-edge thermal cap +
       per-edge loss.
    3. P2P trading variable: cell-to-cell energy exchange priced at
       `econ.stage_d_p2p_tariff_inr_per_kwh` (mid-point between
       import and export tariffs).
    4. Bundled from day 1: module-mix mono/poly/thin-film as LP Var;
 per-cell residential/commercial/industrial tariff split;
       Phase 3C industrial cross-subsidy wiring;- PMSGY tiering;
       N9 EV/V2G home-vs-workplace placement; N10 demand-diversity.

    Guardrails:
    * Single-bus path stays byte-for-byte when `stage_d.enabled: false`
      (verified via the same `if econ.stage_d_enabled` branch in
      `solve_dispatch_pyomo`).
    * Aggregate (sum-over-cells) must reconcile with the single-bus
      headline 1,216.0 M / 74.46 kt / 49.06 B (post-tariff-bundle,
 baseline) within
      `econ.stage_d_reconciliation_tolerance_fraction` before trusting.
    * Watch solve time: 864 slices × 419 built cells × 3 periods
      could be ~1 M Vars naively. `cell_aggregation_strategy` knob in
      the YAML lets the spine start aggregated and refine later.
    * No re-anneal of `optimised_sa.geojson` (seed 42 frozen).

    Reconciliation target (post-tariff-bundle baseline,
    single-bus aggregate, full_stack alpha=0, multi-period, nep_policy_push):
      annual_cost = 1,216,005,997 INR/yr  (base-year 2030 headline)
      emissions   = 74,462,760 kgCO2/yr   (base-year 2030)
      lifetime    = 49,064,339,759 INR    (LP-derived multi-period)
      capacities  = rooftop 42,903; farm 100,000; carport 22,000;
                    floating_pv 900; v2g 2,636; biomass 5,000;
                    wte 811; biogas 500; battery 0
      topology    = 625 cells -> 408 built buses, 141 ROAD cells, 25
                    solar-farm cells, 11 parking_lot (carport sites),
                    10 blue_space (2 floating-PV-eligible). Per-edge
                    LP (Phase 2+) runs on the ROAD-ROAD 4-neighbour
                    edges; built cells inject at their nearest ROAD node.

    Returns
    -------
    DispatchResult
        Once built: per-cell flows aggregated to the same schema fields
        the single-bus path uses + an extra `per_cell_breakdown` dict
        (cell_id -> per-period-per-slice flow snapshot).
    """
    # (Stage D minimal spine — Claude 2): build a per-cell
    # LP where each built cell is its own bus with local demand + local
    # rooftop PV. This minimal version DOES NOT yet add inter-cell
    # edges / KCL / DC flow / P2P trading — it shares district-wide
    # capacities (farm, biomass, WTE, biogas, V2G, battery, thermal,
    # carport, floating PV) just like the single-bus path. So the
    # aggregate sum-of-cells equals the single-bus headline by
    # construction. This is the validation harness; the next
    # increment (per-edge cable flow + KCL + DC + P2P) builds on top.
    return _solve_dispatch_pyomo_stage_d_minimal(
        net, econ, scenario_name, scenario, alpha=alpha,
    )


def _solve_dispatch_pyomo_stage_d_phase2_full_lp(
    net: EnergyNetwork,
    econ: Economics,
    scenario_name: str,
    scenario: Scenario,
    alpha: float = 0.0,
) -> DispatchResult:  # pragma: no cover
    """Stage D Phase 2 FULL LP integration.

    Builds the multi-period MILP, then ADDS:
    - 1 aggregate ``curtail[p, s]`` Var per period × slice (~2.6 k Vars)
      that subtracts from total PV supply in a NEW balance constraint
      (the original balance is deactivated). Captures the LP-decided
      response to cable congestion: when 6 MW thermal caps bind, LP
      forced to curtail surplus PV → more grid_import → headline shifts.
    - 144 signed edge flow Vars ``f[edge, p, s]`` on the ROAD-ROAD
      topology, bounded ``[-cable_thermal × hours, +cable_thermal × hours]``
      (~373 k Vars at 864 slices × 3 periods).
    - 141 KCL constraints per (period, slice) at every road node:
      signed flow sum = sum of per-cell net injections (computed via
      Phase 1 shares times capacity/flow expressions) + substation's
      district-shared injection (grid I/O + battery + biomass + etc.)
      at substation cell ``(12, 12)``.

    The dispatch LP optimum DIVERGES from single-bus when cable thermal
    caps bind on peak slices. Reconciles to single-bus / Phase 1 when
    ``cable_thermal_kw_default`` is set to 10^9 (unlimited) — first
    sanity check before reading the realistic 6 MW divergence.

    Returns DispatchResult via the standard multi-period extraction
    path. Adds ``r.by_cell``, ``r.stage_d_curtailment_kwh`` (per-slice
    LP-decided curtailment), ``r.stage_d_per_edge_flow_kwh`` (signed
    per-edge per-slice flows), and ``r.stage_d_features`` with
    ``per_edge_cable_flow_mode: "lp_integrated"``.
    """
    if not _HAS_PYOMO:
        raise RuntimeError("pyomo is not installed in this environment")
    if not econ.multi_period_enabled():
        # Single-period not yet supported in FULL LP — multi-period gates Stage D.
        raise RuntimeError(
            "Stage D Phase 2 FULL LP currently requires multi_period.enabled=true"
        )

    #: print
    # per-phase timing so future runs surface WHICH step is slow (Pyomo
    # build vs HiGHS solve vs recursive extraction). Output is single-line
    # per phase; cheap.
    import time, sys
    _t_total = time.time()
    def _phase(label: str, t_start: float) -> None:
        dt = time.time() - t_start
        print(f"  [Phase 2 FULL LP] {label}: {dt:.1f}s "
              f"(total elapsed {time.time()-_t_total:.1f}s)", flush=True)
        sys.stdout.flush()

    _t = time.time()
    # Build the base multi-period model (provides capacity Vars, flow Vars,
    # the original balance constraint that we'll deactivate, etc.).
    m, period_years, slice_ids, hours_of, weights = (
        _build_pyomo_model_multi_period(net, econ, scenario, alpha=alpha)
    )
    _phase("base multi-period model built", _t)

    # ----- Precompute per-cell shares (mirror Phase 1 logic, capacity-weighted) -----
    from core.land_use import LandUse
    built_cells = [n for n in net.nodes if n.is_built]
    solar_cells = [n for n in net.nodes if n.is_solar_farm]
    # Demand share: cell.peak_demand_kw / Σ
    total_peak = sum(n.peak_demand_kw for n in built_cells if n.peak_demand_kw > 0)
    demand_share: Dict[Tuple[int, int], float] = {
        n.cell_id: (n.peak_demand_kw / total_peak if total_peak > 0 else 0.0)
        for n in built_cells if n.peak_demand_kw > 0
    }
    # Rooftop share (excludes solar farms)
    total_roof = sum(n.rooftop_pv_cap_kwp * float(n.pv_shading_multiplier or 1.0)
                      for n in net.nodes
                      if not n.is_solar_farm and n.rooftop_pv_cap_kwp > 0)
    rooftop_share: Dict[Tuple[int, int], float] = {}
    if total_roof > 0:
        for n in net.nodes:
            if n.is_solar_farm or n.rooftop_pv_cap_kwp <= 0:
                continue
            rooftop_share[n.cell_id] = (
                n.rooftop_pv_cap_kwp * float(n.pv_shading_multiplier or 1.0)
                / total_roof
            )
    # Solar farm share
    total_farm = sum(n.solar_farm_cap_kwp * float(n.pv_shading_multiplier or 1.0)
                      for n in solar_cells if n.solar_farm_cap_kwp > 0)
    farm_share: Dict[Tuple[int, int], float] = {}
    if total_farm > 0:
        for n in solar_cells:
            if n.solar_farm_cap_kwp <= 0:
                continue
            farm_share[n.cell_id] = (
                n.solar_farm_cap_kwp * float(n.pv_shading_multiplier or 1.0)
                / total_farm
            )
    # Carport share (from grid is_carport_site tags)
    carport_share: Dict[Tuple[int, int], float] = {}
    if net.grid is not None and any(c.is_carport_site for c in net.grid.all_cells()):
        from layout.carport_siting import carport_kwp_for_cell
        cp_pairs: List[Tuple[Tuple[int, int], float]] = []
        for c in net.grid.all_cells():
            if not c.is_carport_site:
                continue
            kwp = carport_kwp_for_cell(c)
            if kwp > 0:
                cp_pairs.append(((c.row, c.col), kwp))
        cp_total = sum(kwp for _, kwp in cp_pairs)
        if cp_total > 0:
            for cid, kwp in cp_pairs:
                carport_share[cid] = kwp / cp_total
    # Floating PV share
    fpv_share: Dict[Tuple[int, int], float] = {}
    if net.grid is not None and any(c.floating_pv_cluster_id is not None
                                      for c in net.grid.all_cells()):
        # FIX. This used to split the district floating-PV build
        # EQUALLY over every tagged site (1/len). That contradicted
        # `Network.total_floating_pv_potential_kwp`, which prices a CANAL
        # corridor cell at the canal-top density (econ.canal_pv_kwp_per_cell,
        # 210 kWp per 100 m cell, Q23/PEDA) and a pond cell at
        # kwp_per_cell x uptake (450 kWp) - a 2.14x difference.
        # On the current town that is 43 canal cells + 16 pond cells, so the
        # equal split put ~31% too much PV on every canal cell and ~39% too
        # little on every pond cell. The AGGREGATE was always right (these are
        # normalised shares of an LP variable already bounded by the correct
        # 16,230 kWp), so no headline number was ever wrong - but the per-cell
        # NETWORK flows in Stage D were, which is the one place these shares
        # are used. Weight by the same per-cell rule the potential uses.
        per_cell_fpv = (econ.floating_pv_kwp_per_cell_default()
                         * econ.floating_pv_uptake_fraction())
        canal_per_cell = econ.canal_pv_kwp_per_cell()
        eligible = set(econ.floating_pv_eligible_land_uses())
        fpv_weights: Dict[Tuple[int, int], float] = {}
        for c in net.grid.all_cells():
            if not (c.is_floating_pv_site and c.land_use.value in eligible):
                continue
            w = canal_per_cell if c.amenity_subtype == "canal" else per_cell_fpv
            if w > 0:
                fpv_weights[(c.row, c.col)] = w
        total_fpv_w = sum(fpv_weights.values())
        if total_fpv_w > 0:
            for cid, w in fpv_weights.items():
                fpv_share[cid] = w / total_fpv_w
    # V2G share
    v2g_share: Dict[Tuple[int, int], float] = {}
    total_v2g_w = 0.0
    has_ownership = bool(getattr(econ, "ev_vehicle_ownership", None))
    v2g_weights: Dict[Tuple[int, int], float] = {}
    for n in net.nodes:
        if not n.is_residential or n.households <= 0:
            continue
        if has_ownership:
            inc = econ.income_for_category(n.category_name or "")
            if inc is None:
                continue
            w = (n.households
                 * econ.ev_cars_per_household(inc, None)
                 * econ.v2g_willingness(inc))
        else:
            w = n.households / 5.0
        if w <= 0:
            continue
        v2g_weights[n.cell_id] = w
        total_v2g_w += w
    if total_v2g_w > 0:
        v2g_share = {cid: w / total_v2g_w for cid, w in v2g_weights.items()}
    _phase("per-cell shares computed", _t)
    _t = time.time()

    # ----- Substation + cell-to-road mapping -----
    substation = _stage_d_pick_substation_cell(net)
    cell_to_road = _stage_d_map_cells_to_roads(net)
    road_nodes = [n for n in net.nodes if n.land_use == LandUse.ROAD]
    road_ids = [n.cell_id for n in road_nodes]
    road_to_cells: Dict[Tuple[int, int], List[Tuple[int, int]]] = {
        r: [] for r in road_ids
    }
    for cell_id, road_id in cell_to_road.items():
        if road_id in road_to_cells:
            road_to_cells[road_id].append(cell_id)
    # (Opus 4.8) ROOT-CAUSE FIX for the Attempt-1/2 infeasibility.
    # carport (PARKING_LOT) and floating-PV (BLUE_SPACE) cells are NOT
    # is_built and NOT is_solar_farm, so `_stage_d_map_cells_to_roads` skips
    # them (network.py: is_built == category_name is not None). Their
    # carport_share / fpv_share therefore never enter ANY KCL injection,
    # while `balance_phase2` DOES include carport + fpv supply. Summing the
    # 141 KCL constraints cancels every flow term (each ROAD-ROAD edge is
    # +f at one end, -f at the other), leaving Σ(net injections) == 0; that
    # equals `balance_phase2` ONLY if every share dict sums to 1 over the
    # cells actually used in KCL. With carport/fpv Σmapped == 0 (proven by
    # `(carport_supply - curtail_carport) + (fpv_supply - curtail_fpv) == 0`,
    # an inconsistent extra equation that makes HiGHS thrash -> infeasible.
    # Fix: map each carport/fpv cell to its NEAREST road (physically: the PV
    # injects at the lot / pond and reaches the grid via the closest road
    # cable — same Manhattan tie-break as `_stage_d_map_cells_to_roads`), so
    # every share dict sums to 1 over `road_to_cells` and summed-KCL becomes
    # byte-identical to `balance_phase2`. NOTE: kept local to the FULL LP so
    # the shared mapping (used by the post-hoc AUDIT + its exact-count test)
    # is untouched.
    _node_by_id = {n.cell_id: n for n in net.nodes}
    _extra_mapped = 0
    for _cid in list(carport_share.keys()) + list(fpv_share.keys()):
        if _cid in cell_to_road:
            continue
        _src = _node_by_id.get(_cid)
        if _src is None:
            continue
        _nearest = min(
            road_nodes,
            key=lambda r: (abs(r.centre_x_m - _src.centre_x_m)
                            + abs(r.centre_y_m - _src.centre_y_m),
                            r.cell_id[0], r.cell_id[1]),
        )
        cell_to_road[_cid] = _nearest.cell_id
        road_to_cells[_nearest.cell_id].append(_cid)
        _extra_mapped += 1
    # Edge adjacency
    edges = list(net.edges)
    n_edges = len(edges)
    edge_adj: Dict[Tuple[int, int], List[Tuple[int, int]]] = {r: [] for r in road_ids}
    road_set = set(road_ids)
    for ei, e in enumerate(edges):
        if e.a in road_set:
            edge_adj[e.a].append((ei, +1))
        if e.b in road_set:
            edge_adj[e.b].append((ei, -1))
    _phase(f"topology mapped ({len(road_ids)} road nodes, "
           f"{n_edges} edges, substation={substation}, "
           f"+{_extra_mapped} carport/fpv cells mapped to nearest road)", _t)
    _t = time.time()

    # ----- Distributed plant injection (Stage D KCL-completion, Opus 4.8) -----
    # The realistic per-edge cable cap was INFEASIBLE because ALL district-shared
    # generation (grid import + biomass/WTE/biogas + battery/thermal storage) injected
    # at the SINGLE substation node — its ~4 edges cannot pass grid-import (~104 MW peak)
    # + the plants + storage simultaneously. This is the MODELLING ARTIFACT (proven by
    # per-node + connectivity diagnostics: 0 nodes over-capacity, fully connected, peak
    # 104 MW < substation throughput). FIX: inject the 3 combustion plants at their REAL
    # road-adjacent cells (Stage A siting). Grid I/O + storage + DC-PPA stay at the
    # substation (physical grid interconnection / co-located grid-scale BESS). This is
    # balance-PRESERVING: each district-shared term still appears exactly ONCE across all
    # road nodes, so Σ_road KCL == balance_phase2 regardless of WHICH node carries it.
    # Gated on electrical_network.enabled so the legacy all-at-substation branch stays
    # byte-identical when the flag is off (Stage D reconciliation tests unchanged).
    _distribute_plants = econ.electrical_network_enabled()
    _bio_node = _biogas_node = _wte_node = substation
    if _distribute_plants:
        _pn = _stage_d_plant_injection_nodes(net, road_nodes, substation)
        if _pn:
            _bio_node = _pn.get("biomass", substation)
            _biogas_node = _pn.get("biogas", substation)
            _wte_node = _pn.get("wte", substation)
            _phase("distributed plant injection: "
                   + ", ".join(f"{v}@{r}" for v, r in sorted(_pn.items())), _t)
        else:
            _distribute_plants = False
            _phase("distributed plant injection: no placements found "
                   "(substation fallback)", _t)
        _t = time.time()

    # ----- Add curtailment Var (subtracts from total PV supply per slice) -----
    m.curtail = pyo.Var(m.P, m.S, bounds=(0.0, None))

    # ----- Add per-edge signed flow Var -----
    # (Stage D electrical-asset build, Phase C): when
    # electrical_network.enabled, each edge's thermal cap is a function of its
    # VOLTAGE CLASS (33 kV backbone ~40 MW vs 11 kV distribution 6 MW) instead of
    # one flat cable_thermal_kw. The 33 kV backbone is what makes the realistic
    # per-cable cap FEASIBLE (the pure-11 kV 6 MW network was infeasible —
    # substation egress ~24 MW << ~100 MW peak). When disabled, the legacy single
    # cable_thermal_kw_default applies to every edge (byte-exact Phase-2 path).
    # the electrical-asset COST (capex, B/C/D) is decoupled from the
    # per-edge thermal CAPS (the Phase-C feasibility limiter). `enforce_thermal_caps`
    # (default true) gates ONLY the caps — so a "costed" scenario can run capex-ON /
    # caps-OFF (caps-off uses the flat cable_thermal_kw_default, e.g. 1 GW unlimited).
    # This matters because the realistic per-edge caps currently expose a MODELLING
    # ARTIFACT (all district-shared generation is injected at the single substation
    # node) — see the next_session spec. The costing of the infrastructure should not
    # depend on that artifact.
    cable_thermal_kw = econ.stage_d_cable_thermal_kw_default()
    per_edge_cap_kw: Optional[List[float]] = None
    _en_caps_on = (econ.electrical_network_enabled()
                   and bool(econ.electrical_network_config()
                            .get("enforce_thermal_caps", True)))
    #-closure): REINFORCE-OVER-TIME. When electrical_network + reinforcement
    # are enabled, the per-edge thermal caps are PERIOD-DEPENDENT — a 2030 base (by voltage
    # class) scaled by a per-period multiplier that tracks demand growth (the distribution
    # network is upgraded as load rises). This is what makes the realistic-cap LP feasible
    # across 2030/2042/2055: a single fixed cap that serves the 2030 88 MW peak is infeasible
    # by the 2042/2055 116/147 MW peaks (see FINDINGS. Gated; when off, the flat
    # voltage-tier caps (or cable_thermal_kw_default) apply — byte-identical.
    _reinforce_on = _en_caps_on and econ.en_reinforcement_enabled()
    per_edge_base_cap_kw: Optional[List[float]] = None
    _reinforce_mult: Dict[int, float] = {}
    if _en_caps_on:
        from energy.electrical_assets import per_edge_thermal_kw as _en_caps

        def _ek(a, b):
            return (a, b) if a <= b else (b, a)
        _caps = _en_caps(net, econ)
        per_edge_cap_kw = [
            _caps.get(_ek(e.a, e.b), cable_thermal_kw) for e in edges
        ]
        _bb = sum(1 for c in per_edge_cap_kw if c > cable_thermal_kw)
        _phase(f"electrical_network ON: per-edge voltage-class caps "
               f"({_bb} backbone / {n_edges - _bb} distribution edges)", _t)
        if _reinforce_on:
            from energy.electrical_assets import assign_voltage_classes as _avc
            _vc = _avc(net, econ)
            _base_dist = econ.en_reinforcement_base_thermal_kw("dist_11kv")
            _base_bb = econ.en_reinforcement_base_thermal_kw("backbone_33kv")
            per_edge_base_cap_kw = [
                _base_bb if _vc.get(_ek(e.a, e.b), "dist_11kv") == "backbone_33kv"
                else _base_dist for e in edges
            ]
            _reinforce_mult = {
                p: econ.en_reinforcement_period_multiplier(p) for p in period_years
            }
            _mult_str = ", ".join(f"{p}:{_reinforce_mult[p]:.3f}" for p in period_years)
            _phase(f"reinforce-over-time ON: base {_base_dist/1000:.0f}/{_base_bb/1000:.0f} MW "
                   f"(dist/backbone), period mult [{_mult_str}]", _t)
    m.E = pyo.Set(initialize=list(range(n_edges)), ordered=True)
    def _flow_bounds(_m, ei, p, s):
        if _reinforce_on and per_edge_base_cap_kw is not None:
            cap = per_edge_base_cap_kw[ei] * _reinforce_mult.get(p, 1.0)
        elif per_edge_cap_kw is not None:
            cap = per_edge_cap_kw[ei]
        else:
            cap = cable_thermal_kw
        cap_kwh = cap * hours_of[s]
        return (-cap_kwh, +cap_kwh)
    m.f = pyo.Var(m.E, m.P, m.S, bounds=_flow_bounds)
    _phase(f"added curtail Var ({len(period_years)*len(slice_ids)} vars) + "
           f"edge flow Vars ({n_edges*len(period_years)*len(slice_ids)} vars)", _t)
    _t = time.time()

    # ----- Helper: compute PV supply expression at (p, s) — mirror multi-period balance -----
    yield_rooftop_base = net.pv_yield_per_kwp_kwh(econ)
    orientation_active = bool(
        getattr(scenario, "allow_panel_orientation_choice", False)
    )
    yield_rooftop = (net.pv_yield_per_kwp_kwh_oriented(econ)
                     if orientation_active else yield_rooftop_base)
    yield_farm = net.pv_yield_per_kwp_kwh_solar_farm(econ)
    rooftop_yield_mult = econ.rooftop_pv_yield_multiplier_with_biosolar(scenario)
    bipv_yield_mult = econ.bipv_yield_multiplier_vs_rooftop()
    fpv_yield_mult = econ.floating_pv_yield_multiplier_vs_ground_mount()
    tracked_yield_mult = econ.tracked_pv_yield_multiplier()
    demand_mult = econ.total_demand_multiplier_with_biosolar(scenario)
    # (Stage D Phase D-losses): double-count reconciliation. When
    # electrical_network is enabled, the explicit distribution transformers (Phase D)
    # make their share of the aggregate ac_loss_fraction EXPLICIT (sized by installed
    # kVA + throughput). Remove that transformer share from the in-balance AC loss so
    # it is not counted twice; the cable + reactive-overhead remainder stays in the
    # balance, and the explicit transformer loss is added as a costed energy overlay
    # after the solve. LOCAL to the Stage D FULL LP — the single-bus and multi-period
    # base paths keep the full econ.ac_loss_fraction, so they remain byte-exact.
    _ac_loss_frac = econ.ac_loss_fraction()
    if econ.electrical_network_enabled():
        _ac_loss_frac *= max(0.0, 1.0 - econ.en_transformer_share_of_ac_loss())
    ac_eff = max(1e-6, 1.0 - _ac_loss_frac)
    #: PSPCL's technical T&D loss now improves across the
    # horizon instead of sitting flat at 10.7% while the same grid's carbon
    # intensity falls 69% (period_emission_factor 0.5106 -> 0.1605). The
    # trajectory is deliberately shallow (10.7 / 9.5 / 8.5%) because RDSS
    # targets AT&C, most of which is a billing improvement, while this figure
    # is physical loss only. Keyed by PERIOD YEAR; with no trajectory
    # configured every entry collapses to the flat value, byte-exact.
    grid_import_eff_p = {
        y: ac_eff * max(1e-6, 1.0 - econ.pspcl_grid_loss_fraction(y))
        for y in period_years
    }
    period_demand_mult = {y: econ.period_demand_multiplier(y) for y in period_years}
    ev_kwh_base = net.ev_charging_kwh_by_slice(econ, year=None)
    demand_kwh = net.demand_by_slice_kwh(econ)
    non_ev_kwh = {s: demand_kwh[s] - ev_kwh_base.get(s, 0.0) for s in slice_ids}
    ev_kwh_by_period = {
        y: net.ev_charging_kwh_by_slice(econ, year=y) for y in period_years
    }
    #: climate warming is applied to the COOLING term, not
    # flat across all demand. It used to ride inside period_demand_multiplier,
    # which meant +2 C of global warming raised JANUARY 2055 demand by 3% -
    # warming raises cooling and lowers heating, it does not raise winter
    # demand. `non_ev_kwh` already contains the 2030 cooling, so only the
    # UPLIFT is added here. The other lifetime drivers (income, cooking, AI,
    # water) still scale everything including the uplift, which is correct:
    # a richer household cools a warmer house harder.
    cool_kwh_base = net.cooling_kwh_by_slice(econ)
    cool_uplift = {y: econ.cooling_warming_multiplier(y) - 1.0
                   for y in period_years}
    period_slice_demand = {
        y: {s: period_demand_mult[y]
               * (non_ev_kwh[s]
                  + cool_uplift[y] * cool_kwh_base.get(s, 0.0)
                  + ev_kwh_by_period[y].get(s, 0.0))
            for s in slice_ids}
        for y in period_years
    }

    # RETRY (Claude 2): per-PV-type supply expressions. Replaces the
    # single _pv_supply_expr (which forced KCL to use a wrong `demand_share`
    # proxy for PV-share, causing infeasibility). Each PV type has its OWN
    # share dict + its OWN curtailment Var, so per-cell injection in KCL is
    # mathematically consistent with the aggregate balance.
    def _rooftop_supply_expr(p, s):
        terms = []
        for pp in period_years:
            if pp > p: break
            roof_age = econ.pv_vintage_yield_factor("rooftop_pv", pp, p)
            terms.append(yield_rooftop[s] * rooftop_yield_mult
                          * m.rooftop_new[pp] * roof_age)
            terms.append(yield_rooftop_base[s] * bipv_yield_mult
                          * m.bipv_new[pp] * roof_age)
        return sum(terms) if terms else 0.0
    def _farm_supply_expr(p, s):
        terms = []
        for pp in period_years:
            if pp > p: break
            farm_age = econ.pv_vintage_yield_factor("solar_farm", pp, p)
            terms.append(yield_farm[s] * m.farm_fixed_new[pp] * farm_age)
            terms.append(yield_farm[s] * tracked_yield_mult
                          * m.farm_tracked_new[pp] * farm_age)
        return sum(terms) if terms else 0.0
    def _carport_supply_expr(p, s):
        terms = []
        for pp in period_years:
            if pp > p: break
            farm_age = econ.pv_vintage_yield_factor("solar_farm", pp, p)
            terms.append(yield_farm[s] * m.carport_new[pp] * farm_age)
        return sum(terms) if terms else 0.0
    def _fpv_supply_expr(p, s):
        terms = []
        for pp in period_years:
            if pp > p: break
            farm_age = econ.pv_vintage_yield_factor("solar_farm", pp, p)
            terms.append(yield_farm[s] * fpv_yield_mult
                          * m.floating_pv_new[pp] * farm_age)
        return sum(terms) if terms else 0.0
    def _pv_supply_expr(p, s):
        """Total PV supply = sum of all 4 per-type expressions."""
        return (_rooftop_supply_expr(p, s) + _farm_supply_expr(p, s)
                + _carport_supply_expr(p, s) + _fpv_supply_expr(p, s))

    def _effective_demand_expr(p, s):
        return (demand_mult * period_slice_demand[p][s]
                 - m.dsr_reduce[p, s] + m.dsr_add[p, s])

    # ----- Replace 1 aggregate curtail Var with 4 per-PV-type Vars -----
    # (m.curtail was added earlier; deactivate / re-create as 4 per-type)
    m.del_component(m.curtail)
    m.curtail_rooftop = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.curtail_farm = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.curtail_carport = pyo.Var(m.P, m.S, bounds=(0.0, None))
    m.curtail_fpv = pyo.Var(m.P, m.S, bounds=(0.0, None))

    # ----- Deactivate the original balance, add new one with per-type curtail -----
    # Data-centre PPA offtake (N21): if enabled, m.dc_ppa already exists from
    # the multi-period build. It is an EXTERNAL sink off the substation, so it
    # appears on the balance LHS here and injects ONLY at the substation node in
    # KCL below (never on interior road edges).
    # PPA-BAU-1: mirror the builder's scenario gate by testing
    # for the Var itself - Stage D must not reference m.dc_ppa in a
    # scenario where the builder never created it (BAU).
    _dc_ppa_on = (econ.ppa_enabled()
                  and bool(econ.ppa_active_counterparties())
                  and hasattr(m, "dc_ppa"))
    # B21: if the buy-side green purchase is on, m.gp already
    # exists from the multi-period build; it is an EXTERNAL source at the
    # substation (delivered convention), mirroring the dc-PPA sink.
    _gp_on = econ.green_purchase_enabled() and hasattr(m, "gp")
    m.balance.deactivate()
    # FX-1/: the base model now ships an aggregate m.pv_curtail
    # (used by the deactivated single-bus balance). Phase 2 has its own per-type
    # curtail vars, so pin the aggregate one to 0 and drop its cap constraint -
    # otherwise it floats free (no objective coefficient) in this path.
    if hasattr(m, "pv_curtail_cap"):
        m.pv_curtail_cap.deactivate()
    if hasattr(m, "pv_curtail"):
        for _k in m.pv_curtail:
            m.pv_curtail[_k].fix(0.0)
    # D-2 WARNING: this Phase-2 balance
    # NEVER received the FX-1/Q-1 ac_eff propagation - thermal_dis / biomass /
    # wte / biogas enter at 1.0 below (and in the KCL injections), while the
    # production multi-period balance charges all four ac_eff. Internally
    # consistent with its own KCL (so it solves), but those sources get a free
    # ~2% delivery advantage vs production. MUST be fixed (balance + BOTH KCL
    # injection branches together) before any B15-SC super-cell revival, else
    # the reconciliation-to-single-bus will drift by the ac_eff differential.
    # Not fixed live in: the FULL-LP trio is documented-intractable at
    # 100 m (B15), so an edit here is unverifiable until B15-SC lands.
    def _new_balance(_m, p, s):
        return (
            _effective_demand_expr(p, s) + _m.charge[p, s] + _m.thermal_chg[p, s]
            + _m.exp[p, s] + (_m.dc_ppa[p, s] if _dc_ppa_on else 0.0)
            == _rooftop_supply_expr(p, s) - _m.curtail_rooftop[p, s]
                 + _farm_supply_expr(p, s) - _m.curtail_farm[p, s]
                 + _carport_supply_expr(p, s) - _m.curtail_carport[p, s]
                 + _fpv_supply_expr(p, s) - _m.curtail_fpv[p, s]
                 + ac_eff * _m.discharge[p, s] + _m.thermal_dis[p, s]
                 + ac_eff * _m.v2g[p, s] + _m.biomass[p, s]
                 + _m.wte[p, s] + _m.biogas[p, s]
                 + grid_import_eff_p[p] * _m.imp[p, s]
                 + (_m.gp[p, s] if _gp_on else 0.0)
        )
    m.balance_phase2 = pyo.Constraint(m.P, m.S, rule=_new_balance)

    # ----- Per-type curtailment upper bounds -----
    m.curtail_cap_rooftop = pyo.Constraint(m.P, m.S,
        rule=lambda _m, p, s: _m.curtail_rooftop[p, s] <= _rooftop_supply_expr(p, s))
    m.curtail_cap_farm = pyo.Constraint(m.P, m.S,
        rule=lambda _m, p, s: _m.curtail_farm[p, s] <= _farm_supply_expr(p, s))
    m.curtail_cap_carport = pyo.Constraint(m.P, m.S,
        rule=lambda _m, p, s: _m.curtail_carport[p, s] <= _carport_supply_expr(p, s))
    m.curtail_cap_fpv = pyo.Constraint(m.P, m.S,
        rule=lambda _m, p, s: _m.curtail_fpv[p, s] <= _fpv_supply_expr(p, s))
    _phase("deactivated old balance + added per-type curtail + new balance", _t)
    _t = time.time()

    # ----- NOTE on curtailment at unlimited CABLE cap ---
    # The FULL LP curtails ~0.3% of generation (~930 MWh/yr) even at unlimited
    # cable cap. This is NOT a bug and NOT numerical: export tariff is a flat
    # 3.5 INR/kWh but grid EXPORT is capped at 60 MW, so on peak-solar hours the
    # surplus above 60 MW can only be stored (battery degradation cost) or
    # curtailed — and curtailing is cheaper than uneconomic storage. The
    # single-bus baseline has NO curtail Var (strict equality balance), so it is
    # FORCED to store that surplus, making it 0.0138% more expensive over the
    # lifetime. The FULL LP is therefore the more realistic model; it reconciles
    # to single-bus on the optimised headline (lifetime cost, Δ=-0.0138%), while
    # annual cost/emissions differ ~2% because the two models dispose of peak
    # surplus differently. A tie-break curtailment penalty was tried and reverted
    # (the curtailment is genuine, not degenerate, so a small penalty barely
    # moved it: 983->932 MWh — confirming it is economically driven).

    # ----- KCL at every road node per (p, s) — per-PV-type share decomposition -----
    # For each road r: sum(signed flows at r) = net_injection(r, p, s)
    # net_inj = sum_over_adjacent_cells_c [
    #     rooftop_share[c] × (rooftop_supply - curtail_rooftop)
    #   + farm_share[c]    × (farm_supply - curtail_farm)
    #   + carport_share[c] × (carport_supply - curtail_carport)
    #   + fpv_share[c]     × (fpv_supply - curtail_fpv)
    #   + v2g_share[c]     × ac_eff × m.v2g
    #   - demand_share[c]  × effective_demand
    # ] + (substation_dist_shared if r == substation)
    # Because each per-type share dict sums to 1 across all cells of that
    # type, sum-over-cells gives the aggregate balance terms — KCL is now
    # consistent with the balance constraint by construction.
    # Progress: print every 30 road nodes during build (every ~78 k constraints).
    _kcl_count = [0]
    _kcl_progress_every = max(1, len(road_ids) // 5)  # ~5 progress lines
    def _kcl(_m, road_idx, p, s):
        rid = road_ids[road_idx]
        # Flow side
        flow_lhs = sum(sign * _m.f[ei, p, s] for ei, sign in edge_adj[rid])
        # Injection side — per-PV-type, with correct share dicts
        eff_dem = _effective_demand_expr(p, s)
        rs_pv = _rooftop_supply_expr(p, s)
        fs_pv = _farm_supply_expr(p, s)
        cs_pv = _carport_supply_expr(p, s)
        fp_pv = _fpv_supply_expr(p, s)
        inj_rhs_terms = []
        for cid in road_to_cells[rid]:
            rs = rooftop_share.get(cid, 0.0)
            fs = farm_share.get(cid, 0.0)
            cs = carport_share.get(cid, 0.0)
            fp = fpv_share.get(cid, 0.0)
            if rs > 0:
                inj_rhs_terms.append(rs * rs_pv)
                inj_rhs_terms.append(-rs * _m.curtail_rooftop[p, s])
            if fs > 0:
                inj_rhs_terms.append(fs * fs_pv)
                inj_rhs_terms.append(-fs * _m.curtail_farm[p, s])
            if cs > 0:
                inj_rhs_terms.append(cs * cs_pv)
                inj_rhs_terms.append(-cs * _m.curtail_carport[p, s])
            if fp > 0:
                inj_rhs_terms.append(fp * fp_pv)
                inj_rhs_terms.append(-fp * _m.curtail_fpv[p, s])
            v2g_s = v2g_share.get(cid, 0.0)
            if v2g_s > 0:
                inj_rhs_terms.append(v2g_s * ac_eff * _m.v2g[p, s])
            ds = demand_share.get(cid, 0.0)
            if ds > 0:
                inj_rhs_terms.append(-ds * eff_dem)
        # District-shared injections.
        if _distribute_plants:
            # Combustion plants inject at their REAL road-adjacent cells.
            if rid == _bio_node:
                inj_rhs_terms.append(_m.biomass[p, s])
            if rid == _biogas_node:
                inj_rhs_terms.append(_m.biogas[p, s])
            if rid == _wte_node:
                inj_rhs_terms.append(_m.wte[p, s])
            # Grid I/O + storage + DC-PPA stay at the substation node.
            if rid == substation:
                inj_rhs_terms.extend([
                    grid_import_eff_p[p] * _m.imp[p, s], -_m.exp[p, s],
                    ac_eff * _m.discharge[p, s], -_m.charge[p, s],
                    _m.thermal_dis[p, s], -_m.thermal_chg[p, s],
                ])
                if _dc_ppa_on:
                    inj_rhs_terms.append(-_m.dc_ppa[p, s])
                # B21: wheeled green purchase ARRIVES at the substation
                # (delivered convention) - a source, like grid import.
                if _gp_on:
                    inj_rhs_terms.append(_m.gp[p, s])
        else:
            # Legacy: ALL district-shared injection at the substation. Byte-identical
            # to the pre- path (used when electrical_network is disabled).
            if rid == substation:
                inj_rhs_terms.extend([
                    grid_import_eff_p[p] * _m.imp[p, s], -_m.exp[p, s],
                    _m.biomass[p, s], _m.wte[p, s], _m.biogas[p, s],
                    ac_eff * _m.discharge[p, s], -_m.charge[p, s],
                    _m.thermal_dis[p, s], -_m.thermal_chg[p, s],
                ])
                # Data-centre PPA offtake withdraws at the substation (external
                # dedicated line) — a sink, like grid export.
                if _dc_ppa_on:
                    inj_rhs_terms.append(-_m.dc_ppa[p, s])
                # B21: wheeled green purchase arrives at the substation.
                if _gp_on:
                    inj_rhs_terms.append(_m.gp[p, s])
        # Progress print (cheap: only on road_idx tick + first slice of first period)
        _kcl_count[0] += 1
        if (road_idx > 0 and road_idx % _kcl_progress_every == 0
                and p == period_years[0] and s == slice_ids[0]):
            import sys
            print(f"    [Phase 2 FULL LP] KCL build progress: "
                  f"{road_idx}/{len(road_ids)} roads "
                  f"({_kcl_count[0]} constraints built)", flush=True)
            sys.stdout.flush()
        expr = flow_lhs == sum(inj_rhs_terms) if inj_rhs_terms else flow_lhs == 0
        # BUGFIX. A node with NO incident edges and NO injection
        # terms leaves both sides as plain Python numbers, so `0 == 0`
        # evaluates to a bare bool and Pyomo raises
        #   "Invalid constraint expression... resolved to a trivial Boolean"
        # This crashed all three Stage-D phase-2 full-LP tests at
        # kcl[340,2030,jan_wd_00] - an isolated road node carrying no flow
        # and hosting no load or generation.
        # TRUE means the balance is trivially satisfied and carries no
        # information, so the constraint is simply not needed -> Skip.
        # FALSE would mean a node whose fixed injections CANNOT balance, i.e.
        # a structural infeasibility. That must NEVER be skipped silently -
        # skipping it would hand the LP a feasible-looking model that is
        # physically wrong, which is exactly the class of silent-fallback bug
        # this project has been burned by before and the shading
        # except-swallow found on). So it raises.
        if expr is True:
            return pyo.Constraint.Skip
        if expr is False:
            raise ValueError(
                f"Stage-D phase-2 KCL is structurally infeasible at road "
                f"index {road_idx}, period {p}, slice {s}: fixed injections "
                f"cannot balance and no free variable is present."
            )
        return expr
    m.N = pyo.Set(initialize=list(range(len(road_ids))), ordered=True)
    m.kcl = pyo.Constraint(m.N, m.P, m.S, rule=_kcl)
    _phase(f"KCL constraints built "
           f"({len(road_ids)*len(period_years)*len(slice_ids)} total)", _t)
    _t = time.time()

    # ----- Solve ----- (verbose: stream HiGHS log so a non-optimal
    # termination is visible immediately, and _solve_pyomo now RAISES on
    # infeasible/unbounded rather than silently returning stale values.)
    # (Opus 4.8): the structural infeasibility fix (carport/fpv
    # share mapping) unblocked the model, but dual simplex then CYCLED on the
    # highly degenerate flow LP (objective frozen ~4.8e10 for >3800s, primal
    # infeasibility stuck ~9e-3) and HiGHS returned status Unknown after ~69
    # min. It also warned of pathologically large bounds (2e10) from the big
    # cable cap. Switch to interior-point (IPM) + crossover: IPM does not
    # cycle on degenerate LPs and converges directly; user_bound_scale tames
    # the large bounds. Crossover gives a clean vertex solution for extraction.
    # IPM (not dual simplex, which cycled on this degenerate flow LP) +
    # crossover (clean vertex solution → no smeared near-bound values that
    # would read as phantom curtailment). No user_bound_scale: with the cap at
    # 1 GW the bounds are ~2e7 (well-conditioned), so the aggressive -15 scale
    # that left 2298 unscaling-feasibility violations is no longer needed.
    _solve_pyomo(m, verbose=True, highs_options={
        "solver": "ipm",
        "run_crossover": "on",
    })
    _phase("HiGHS solve finished", _t)
    _t = time.time()

    # ----- Extract via the standard multi-period extraction path -----
    # The model now has a phase-2 balance + curtail + flow Vars. The
    # multi-period extractor reads m.imp, m.exp, m.charge, etc. — all
    # untouched — so it works. We just call the multi-period solve path
    # AFTER manually solving the model. Re-uses ~150 lines of extraction.
    # Easiest: temporarily disable stage_d on a deepcopy + recurse via
    # solve_dispatch_pyomo, then overlay the curtail/flow data.
    # Actually since we have the model already solved, we extract inline.
    from copy import deepcopy
    e2 = deepcopy(econ)
    e2.__dict__["stage_d_raw"] = {
        **(e2.__dict__.get("stage_d_raw") or {}),
        "enabled": False,
    }
    # Build a dummy result via single-bus recursion to get the extraction
    # logic to populate annual cost/emissions/by_slice/period_breakdown.
    # The recursion solves its OWN model (NOT m) so its values reflect the
    # SINGLE-BUS optimum. We'll override with our LP's values below.
    # NOTE: this means we pay for 2 multi-period solves (the m we just
    # solved + the dummy single-bus). For this session's scope we accept it.
    base_result = solve_dispatch_pyomo(
        net, e2, scenario_name=scenario_name, alpha=alpha,
    )
    _phase("recursive single-bus extraction done", _t)
    _t = time.time()
    # Now OVERRIDE the base_result fields with our LP's values.
    # Annual cost / emissions / lifetime / by_slice all come from the
    # multi-period model — but our model has the SAME structure plus
    # curtailment. So we read the OBJECTIVE directly from m.
    annual_cost = float(pyo.value(m.annual_cost_by_period[
        int(econ.multi_period_base_year())]))
    annual_emissions = float(pyo.value(m.annual_emissions_by_period[
        int(econ.multi_period_base_year())]))
    lifetime_cost = float(pyo.value(m.lifetime_cost_expr))

    # (Stage D electrical-asset build, Phases B-C): add the explicit
    # network + substation CAPEX as an annualised constant (it is built
    # regardless of dispatch, so it is NOT an LP Var — a post-hoc overlay keeps
    # the LP itself unchanged). Only when electrical_network.enabled; otherwise 0.
    en_capex_annual = 0.0
    if econ.electrical_network_enabled():
        from energy.electrical_assets import (
            electrical_network_annualised_capex_inr,
        )
        _enc = electrical_network_annualised_capex_inr(net, econ)
        en_capex_annual = float(_enc.get("annualised_total_inr", 0.0))
        annual_cost += en_capex_annual
        # lifetime = Σ_p w_p × annual_cost[p]; the capex is a constant each year,
        # so its lifetime contribution = annual × Σ w_p. Use the SAME period
        # weights the LP uses (w_p = represents_years[p] / (1+r)^(year-base)), NOT
        # a flat × project_lifetime_years — otherwise a non-zero multi-period
        # discount rate would weight the capex inconsistently vs the LP cost.
        # With discount=0, Σ w_p == project_lifetime_years (25), so this is a
        # no-op today but correct if discounting is ever enabled. (
        # code-review fix.)
        try:
            _periods = (econ.__dict__.get("multi_period_raw", {}) or {}).get(
                "periods", []) or []
            _disc = float(econ.multi_period_discount_rate())
            _base = int(econ.multi_period_base_year())
            _sum_w = sum(
                int(p.get("represents_years", 0))
                / (1.0 + _disc) ** (int(p.get("year", _base)) - _base)
                for p in _periods
            ) or float(econ.project_lifetime_years())
        except Exception:
            _sum_w = float(econ.project_lifetime_years())
        lifetime_cost += en_capex_annual * _sum_w
        base_result.__dict__["electrical_network_breakdown"] = _enc

        # (Stage D Phase D-losses): explicit distribution-transformer
        # losses (no-load core + load copper) — the share removed from
        # ac_loss_fraction above, now sized by installed kVA (transformer_zones) +
        # the base-year AC throughput. Costed at the demand-weighted grid-import
        # tariff + grid emission factor (the marginal balancing energy). Added to
        # annual + lifetime cost and annual emissions. Post-hoc overlay (no extra LP
        # Var); the reconciliation that AVOIDS double-counting is the ac_eff
        # reduction above. NOTE: the no-load (core) loss is a 24/7 constant ∝ kVA, so
        # at the district's modest average transformer loading the explicit model
        # typically exceeds the flat-fraction share — a genuine realism correction
        # (lightly-loaded DTRs lose proportionally more), not a bug.
        from energy.electrical_assets import transformer_loss_kwh as _txr_loss
        _by = int(econ.multi_period_base_year())
        _annual_demand_kwh = demand_mult * sum(period_slice_demand[_by].values())
        _tl = _txr_loss(net, econ, _annual_demand_kwh)
        _txr_loss_kwh = float(_tl.get("total_kwh", 0.0))
        _imp_den = sum(period_slice_demand[_by].values()) or 1.0
        _imp_num = sum(econ.import_tariff(s) * period_slice_demand[_by][s]
                       for s in slice_ids)
        _loss_price = _imp_num / _imp_den            # demand-weighted INR/kWh import
        _loss_emis = econ.emission_factor()          # grid kgCO2/kWh
        annual_cost += _txr_loss_kwh * _loss_price
        annual_emissions += _txr_loss_kwh * _loss_emis
        lifetime_cost += _txr_loss_kwh * _loss_price * _sum_w
        _tl["loss_price_inr_per_kwh"] = _loss_price
        _tl["annual_cost_inr"] = _txr_loss_kwh * _loss_price
        base_result.__dict__["electrical_transformer_loss"] = _tl

    base_result.annual_cost_inr = annual_cost
    base_result.annual_emissions_kgco2 = annual_emissions
    base_result.lifetime_cost_inr = lifetime_cost

    # Extract per-slice curtailment (per-PV-type sum) + per-edge flow.
    base_year = int(econ.multi_period_base_year())
    curtail_by_slice = {
        s: float(pyo.value(m.curtail_rooftop[base_year, s])
                  + pyo.value(m.curtail_farm[base_year, s])
                  + pyo.value(m.curtail_carport[base_year, s])
                  + pyo.value(m.curtail_fpv[base_year, s]))
        for s in slice_ids
    }
    curtail_by_type = {
        "rooftop": {s: float(pyo.value(m.curtail_rooftop[base_year, s])) for s in slice_ids},
        "farm":    {s: float(pyo.value(m.curtail_farm[base_year, s])) for s in slice_ids},
        "carport": {s: float(pyo.value(m.curtail_carport[base_year, s])) for s in slice_ids},
        "fpv":     {s: float(pyo.value(m.curtail_fpv[base_year, s])) for s in slice_ids},
    }
    flow_by_slice = {}
    for ei, e in enumerate(edges):
        ek = f"{e.a}-{e.b}"
        flow_by_slice[ek] = {
            s: float(pyo.value(m.f[ei, base_year, s])) for s in slice_ids
        }

    # ----- Phase E: per-cable I²R losses (spatial loss layer, post-hoc) -----
    # (Stage D Phase E). The Phase-2 KCL is lossless on the edges; this
    # resolves the ohmic (I²R) loss on each ROAD-ROAD cable SPATIALLY from the optimal
    # base-year per-slice flows. Loss ∝ P², so it MUST use per-slice flows (never an
    # annual average — Jensen's inequality). Three-phase: loss_W = P_W²·R/(V_LL²·pf²),
    # R = ρ(class)·length, V_LL by voltage class (33 kV backbone / 11 kV distribution).
    # REPORT-ONLY: cable I²R is ALREADY inside the aggregate ac_loss_fraction remainder
    # (the ~0.01 left after Phase D removed the transformer share), so it is NOT re-costed
    # here — that would double-count. Phase E's deliverable is the spatial loss MAP (which
    # feeders lose most → viewer + thesis) plus a defensible explicit total to compare
    # against the aggregate. Post-hoc (no loss-feedback into routing): defensible on these
    # short urban feeders (<~0.5% loss); a full piecewise in-LP loss would add
    # 144×864×3×segments Vars and risk the solve, against the "realistic without crashing"
    # rule. Gated on electrical_network.enabled (production path untouched).
    if econ.electrical_network_enabled():
        from energy import electrical_assets as _ea_e
        _vc_e = _ea_e.assign_voltage_classes(net, econ)
        _pf_e = econ.en_substation_power_factor() or 0.95

        def _ek_e(a, b):
            return (a, b) if a <= b else (b, a)
        _i2r_by_edge: Dict[str, float] = {}
        _i2r_total_kwh = 0.0
        for ei, e in enumerate(edges):
            cls = _vc_e.get(_ek_e(e.a, e.b), "dist_11kv")
            v_ll = 33000.0 if cls == "backbone_33kv" else 11000.0
            r_ohm = (econ.en_conductor_resistance_ohm_per_km(cls)
                     * (e.length_m / 1000.0))
            ek = f"{e.a}-{e.b}"
            edge_loss = 0.0
            for s in slice_ids:
                h = hours_of[s]
                if h <= 0:
                    continue
                p_w = (flow_by_slice[ek][s] / h) * 1000.0   # avg power on slice (W)
                edge_loss += (p_w * p_w * r_ohm
                              / (v_ll * v_ll * _pf_e * _pf_e) / 1000.0) * h
            _i2r_by_edge[ek] = edge_loss
            _i2r_total_kwh += edge_loss
        _ann_dem_e = demand_mult * sum(period_slice_demand[base_year].values())
        base_result.__dict__["stage_d_i2r_loss_kwh"] = {
            "total_kwh": _i2r_total_kwh,
            "per_edge_kwh": _i2r_by_edge,
            "pct_of_annual_demand": (
                _i2r_total_kwh / _ann_dem_e * 100.0 if _ann_dem_e else 0.0),
            "note": ("report-only; cable I2R already within the ac_loss_fraction "
                     "remainder, resolved spatially here for the viewer + thesis"),
        }

    # Phase 1 breakdown + reconciliation (using OUR LP's result, not the
    # base recursion's optimum).
    by_cell = _stage_d_per_cell_breakdown(net, econ, base_result, scenario)
    _stage_d_reconcile(by_cell, base_result,
                        tol_frac=econ.stage_d_reconciliation_tolerance_fraction())

    base_result.__dict__["by_cell"] = by_cell
    base_result.__dict__["stage_d_enabled"] = True
    base_result.__dict__["stage_d_substation_cell"] = substation
    base_result.__dict__["stage_d_curtailment_kwh"] = curtail_by_slice
    base_result.__dict__["stage_d_curtailment_kwh_by_type"] = curtail_by_type
    base_result.__dict__["stage_d_per_edge_flow_kwh"] = flow_by_slice
    base_result.__dict__["stage_d_features"] = {
        "per_cell_buses": True,
        "per_cell_demand": True,
        "per_edge_cable_flow": True,
        "per_edge_cable_flow_mode": "lp_integrated",
        "dc_power_flow": False,
        "p2p_trading": False,
        # (Stage D KCL-completion): distributed plant injection fix)
        # + Phase D explicit transformer losses + Phase E spatial I²R loss layer.
        # All gated on electrical_network.enabled.
        "distributed_plant_injection": bool(econ.electrical_network_enabled()),
        "transformer_losses_explicit": bool(econ.electrical_network_enabled()),
        "i2r_loss_layer": bool(econ.electrical_network_enabled()),
    }
    # Annual totals
    base_result.__dict__["stage_d_total_curtail_kwh"] = sum(curtail_by_slice.values())
    total_flow_abs = sum(abs(v) for slc in flow_by_slice.values()
                          for v in slc.values())
    base_result.__dict__["stage_d_total_edge_flow_kwh"] = total_flow_abs
    _phase(f"per-cell breakdown + reconciliation done; "
           f"TOTAL Phase 2 FULL LP time {time.time()-_t_total:.1f}s", _t)
    return base_result


def _solve_dispatch_pyomo_stage_d_minimal(
    net: EnergyNetwork,
    econ: Economics,
    scenario_name: str,
    scenario: Scenario,
    alpha: float = 0.0,
) -> DispatchResult:  # pragma: no cover
    """Stage D minimal spine — per-cell demand, shared district capacities.

    Reuses the single-bus aggregate by construction: the LP has the
    same capacity Vars, the same per-slice flow Vars, the same balance
    constraint. The "per-cell" part is that we PRECOMPUTE per-cell
    demand AND surface it in DispatchResult.by_cell so downstream code
    (Stage E NPV, viewer cell-flow lines) has the disaggregation.

    This intermediate keeps the LP solve time identical to the
    single-bus path (no extra Vars) while landing the per-cell DATA
    structure the next increment needs.
    """
    # Phase 2 FULL LP branch (Claude 2): when all three flags
    # `per_cell_buses` + `per_edge_cable_flow` + `per_edge_cable_flow_lp_integrated`
    # are true, use the FULL LP integration where curtailment + edge flow Vars
    # are baked into the multi-period MILP — LP optimum diverges from single-bus
    # when 6 MW caps bind. Otherwise fall through to the audit path below.
    if (econ.stage_d_feature_enabled("per_cell_buses")
            and econ.stage_d_feature_enabled("per_edge_cable_flow")
            and econ.stage_d_feature_enabled("per_edge_cable_flow_lp_integrated")):
        return _solve_dispatch_pyomo_stage_d_phase2_full_lp(
            net, econ, scenario_name, scenario, alpha=alpha,
        )
    # Delegate to multi-period if it's also enabled (cumulative gates).
    if econ.multi_period_enabled():
        result = _solve_dispatch_pyomo_multi_period(
            net, econ, scenario_name, scenario, alpha=alpha,
        )
    else:
        # Solve the existing single-bus model unchanged.
        model, slice_ids, hours_of = _build_pyomo_model(
            net, econ, scenario, alpha=alpha,
        )
        solver_name = _solve_pyomo(model)
        # Reuse the single-bus DispatchResult extraction by calling
        # the public single-period solver path inline. To avoid
        # duplicating the ~150 lines of extraction, we recurse with
        # stage_d temporarily disabled.
        from copy import deepcopy
        e2 = deepcopy(econ)
        e2.__dict__["stage_d_raw"] = {
            **(e2.__dict__.get("stage_d_raw") or {}),
            "enabled": False,
        }
        result = solve_dispatch_pyomo(
            net, e2, scenario_name=scenario_name, alpha=alpha,
        )
    # Decorate with the per-cell breakdown. Two tiers, switched by the
    # `per_cell_buses` feature flag:
    # - flag OFF (legacy minimal spine): demand-only decomposition.
    # - flag ON (Phase 1, Claude 2): FULL decomposition —
    #   demand + rooftop_pv + solar_farm + carport_pv + floating_pv +
    #   v2g_discharge per cell + a district-shared bucket for items
    #   that physically inject at one node (battery, biomass, WTE,
    #   biogas, grid import/export) + signed `net_district_flow_kwh`
    #   (positive = cell draws from district through future cables).
    #   Reconciliation is BY CONSTRUCTION (all shares sum to 1), so
    #   sum-over-cells per item == single-bus per item for every slice.
    if econ.stage_d_feature_enabled("per_cell_buses"):
        by_cell = _stage_d_per_cell_breakdown(net, econ, result, scenario)
        # Reconcile every per-cell item against the single-bus aggregate.
        _stage_d_reconcile(by_cell, result, tol_frac=
            econ.stage_d_reconciliation_tolerance_fraction())
        per_edge_audit: Optional[Dict[str, object]] = None
        if econ.stage_d_feature_enabled("per_edge_cable_flow"):
            # Phase 2 AUDIT: per-edge cable flow on the
            # ROAD-ROAD topology via a small min-Σ|f| LP per slice on Phase 1
            # injections. Surfaces per-edge flows + congestion diagnostics
            # WITHOUT yet changing the dispatch LP optimum. Foundation for
            # the full Phase 2 (LP feedback + per-cell curtailment) which
            # is a future increment — see §14.
            substation = _stage_d_pick_substation_cell(net)
            cell_to_road = _stage_d_map_cells_to_roads(net)
            per_edge_audit = _stage_d_phase2_edge_flow_audit(
                net, econ, by_cell, substation, cell_to_road,
            )
            result.__dict__["stage_d_per_edge_audit"] = per_edge_audit
            result.__dict__["stage_d_substation_cell"] = substation
        features = {
            "per_cell_buses": True,
            "per_cell_demand": True,
            "per_edge_cable_flow": (per_edge_audit is not None),
            "per_edge_cable_flow_mode": ("audit" if per_edge_audit is not None
                                          else None),
            "dc_power_flow": False,
            "p2p_trading": False,
        }
    else:
        per_cell_demand_kwh = _stage_d_per_cell_demand_kwh(
            net, econ, scenario=scenario,
        )
        # Sanity: sum-of-cells must equal the aggregate within 1 kWh.
        aggregate_demand = result.annual_demand_kwh
        sum_cells = sum(
            sum(slc.values()) for slc in per_cell_demand_kwh.values()
        )
        tol = max(1.0, aggregate_demand * 1e-9)
        assert abs(sum_cells - aggregate_demand) <= tol, (
            f"Stage D per-cell demand sum {sum_cells:,.1f} kWh "
            f"!= aggregate {aggregate_demand:,.1f} kWh (tol {tol:.1f})"
        )
        by_cell = per_cell_demand_kwh
        features = {
            "per_cell_buses": False,
            "per_cell_demand": True,
            "per_edge_cable_flow": False,
            "dc_power_flow": False,
            "p2p_trading": False,
        }
    # Stamp the result with the per-cell map (read-through field on
    # DispatchResult; consumers see {} when stage_d.enabled is false).
    result.__dict__["by_cell"] = by_cell
    result.__dict__["stage_d_enabled"] = True
    result.__dict__["stage_d_features"] = features
    return result


def _stage_d_pick_substation_cell(net: EnergyNetwork) -> Tuple[int, int]:
    """Pick the substation ROAD cell — the single grid-injection node where
    grid_import / grid_export / battery / biomass / WTE / biogas / DSR enter
    the per-edge network (Phase 2+). Heuristic: the most central ROAD
    JUNCTION (>= 3 road-road cable edges) by geographic centroid of built
    cells, falling back to the plain nearest ROAD cell when the network has
    no junction. Deterministic + stable across runs.

    JUNCTION PREFERENCE: a
    distribution substation sits at a feeder hub so its egress fans out
    over >= 3 corridors (CEA Manual on Distribution System Planning -
    substations at load centres feeding radial feeders; Tier 2,
    https://cea.nic.in/ (Distribution Perspective Plan; the direct path 404s as of)). The-run-2 anneal
    exposed the flaw in plain-nearest: it landed on a degree-2 mid-segment
    cell ((27, 25)) whose two cables cap egress at a fraction of the 250k
    peak; the nearest degree-4 junction ((25, 25), 2.3 cells further)
    restores the-era siting. Mirrored in
    ``energy.electrical_assets.substation_cell``.

    Returns
    -------
    Tuple[int, int]
        ``cell_id`` of the substation ROAD cell. History: (12, 12) on the
        25x25 town, (25, 25) at Stage- 50x50, (27, 25) after the
        anneal under plain-nearest, (25, 25) again under the junction rule.
    """
    from core.land_use import LandUse
    road_cells = [n for n in net.nodes if n.land_use == LandUse.ROAD]
    if not road_cells:
        raise RuntimeError("Stage D Phase 2 needs at least one ROAD cell")
    built = [n for n in net.nodes if n.is_built]
    if built:
        cx = sum(b.centre_x_m for b in built) / len(built)
        cy = sum(b.centre_y_m for b in built) / len(built)
    else:
        cx = sum(r.centre_x_m for r in road_cells) / len(road_cells)
        cy = sum(r.centre_y_m for r in road_cells) / len(road_cells)
    degree: Dict[Tuple[int, int], int] = {}
    for e in net.edges:
        degree[e.a] = degree.get(e.a, 0) + 1
        degree[e.b] = degree.get(e.b, 0) + 1
    junctions = [r for r in road_cells if degree.get(r.cell_id, 0) >= 3]
    pool = junctions or road_cells
    best = min(pool,
               key=lambda r: ((r.centre_x_m - cx) ** 2
                              + (r.centre_y_m - cy) ** 2,
                              r.cell_id[0], r.cell_id[1]))
    return best.cell_id


def _stage_d_map_cells_to_roads(
    net: EnergyNetwork,
) -> Dict[Tuple[int, int], Tuple[int, int]]:
    """Map each non-road cell (built or solar_farm) to its nearest ROAD cell —
    the node where its supply/demand injects into the per-edge flow network.

 (A4 re-time debug): cells map only to roads that CARRY CABLE
    EDGES. The-run-2 town has 3 edge-less orphan road cells (628 roads,
    625 in the cable graph); a cell mapped to one injected power the KCL
    audit silently dropped (its node constraint is trivial) while the
    substation slack still counted it — the connected system then summed to
    a nonzero residual and EVERY real slice read infeasible. Physically the
    orphan roads are lane-fed: their neighbours' cables carry the power, so
    nearest-connected-road is the honest mapping. Falls back to all roads
    when the network has no edges (tiny test grids).

    Returns
    -------
    Dict[(int,int), (int,int)]
        ``cell_id -> road_cell_id``. Roads themselves are not in the map.
        Used by Phase 2+ to build KCL at each ROAD node.
    """
    from core.land_use import LandUse
    road_nodes = [n for n in net.nodes if n.land_use == LandUse.ROAD]
    if not road_nodes:
        return {}
    if net.edges:
        wired = set()
        for e in net.edges:
            wired.add(e.a)
            wired.add(e.b)
        wired_roads = [n for n in road_nodes if n.cell_id in wired]
        if wired_roads:
            road_nodes = wired_roads
    out: Dict[Tuple[int, int], Tuple[int, int]] = {}
    for n in net.nodes:
        if n.land_use == LandUse.ROAD:
            continue
        if not (n.is_built or n.is_solar_farm):
            continue
        # Manhattan distance (4-neighbour grid) — ties broken deterministically
        # by (row, col) order of the road node.
        best = min(road_nodes,
                   key=lambda r: (abs(r.centre_x_m - n.centre_x_m)
                                   + abs(r.centre_y_m - n.centre_y_m),
                                   r.cell_id[0], r.cell_id[1]))
        out[n.cell_id] = best.cell_id
    return out


def _stage_d_plant_injection_nodes(
    net: EnergyNetwork,
    road_nodes: List["EnergyNode"],
    substation: Tuple[int, int],
) -> Dict[str, Tuple[int, int]]:
    """Map each Stage C combustion plant (biomass_chp / biogas / wte) to its
    nearest ROAD node, so the Phase-2 KCL can inject plant generation at the
    plant's REAL road-adjacent cell instead of concentrating it all at the
    substation (the single-node-injection artifact).

    Plant cells come from ``grid.plant_placements`` (Stage A siting). The geojson
    round-trip drops that dict (``grid_from_geojson`` restores other tags but not
    plants, and ``from_grid`` does not re-site plants), so when it is empty we
    re-site deterministically — ``place_stage_c_plants`` is idempotent (pure
    land-use + road-adjacency + buffer rules the geojson preserves), so the
    dispatch-path siting reproduces the optimiser's cells.

    Returns
    -------
    Dict[str, (int, int)]
        ``{LP-Var-name: road_cell_id}`` keyed by the dispatch Var name
        (``"biomass"`` / ``"biogas"`` / ``"wte"``). Empty dict -> the caller
        falls back to injecting at the substation (byte-exact legacy path).
    """
    grid = getattr(net, "grid", None)
    if grid is None or not road_nodes:
        return {}
    placements = getattr(grid, "plant_placements", None) or {}
    if not placements:
        try:
            from layout.plant_siting import place_stage_c_plants
            placements = place_stage_c_plants(grid) or {}
        except Exception:
            return {}
    if not placements:
        return {}
    # Plant siting kind -> dispatch LP Var name.
    kind_to_var = {"biomass_chp": "biomass", "biogas": "biogas", "wte": "wte"}
    out: Dict[str, Tuple[int, int]] = {}
    for kind, pl in placements.items():
        var = kind_to_var.get(kind)
        if var is None:
            continue
        prow, pcol = pl.row, pl.col
        # Nearest road node by Manhattan cell distance (200 m square grid);
        # deterministic tie-break by (row, col).
        nearest = min(
            road_nodes,
            key=lambda r: (abs(r.cell_id[0] - prow) + abs(r.cell_id[1] - pcol),
                           r.cell_id[0], r.cell_id[1]),
        )
        out[var] = nearest.cell_id
    return out


def _stage_d_phase2_edge_flow_audit(
    net: EnergyNetwork,
    econ: Economics,
    by_cell: Dict[object, Dict[str, Dict[str, float]]],
    substation_cell: Tuple[int, int],
    cell_to_road: Dict[Tuple[int, int], Tuple[int, int]],
) -> Dict[str, object]:
    """Phase 2 AUDIT: post-hoc per-edge cable flow on
    the ROAD-ROAD topology, given the Phase 1 per-cell net injections.

    This is a STEPPING STONE to the full Phase 2 LP integration (where flows
    feed back into the dispatch LP and per-cell curtailment closes the
    feasibility loop when thermal caps bind). It surfaces the per-edge flow
    + congestion diagnostics consumers need (Stage E NPV, viewer cell-flow
    arrows) without yet changing the dispatch LP optimum. Run AFTER the
    multi-period MILP has solved.

    Per (period, slice) algorithm:
      1. Build the road-node graph (141 nodes, 144 edges).
      2. For each built/solar cell, compute net injection = pv_kwh +
         v2g_discharge_kwh - demand_kwh from `by_cell`. Sum at the cell's
         nearest road node.
      3. Add district-shared items (grid I/O, biomass, WTE, biogas,
         battery, thermal storage, DSR) at the substation road node, all
         from `by_cell["district_slack"]`.
      4. Solve a small LP per slice: minimise Σ |f[edge]| subject to KCL
         at every road node and per-edge thermal cap (currently
         ``cable_thermal_kw_default``). With min-Σ|f| objective, the LP
         picks the minimal-energy flow consistent with KCL — physically
         meaningful (cables carry only what they have to).
      5. Tag each edge with a congestion flag if |f| exceeds 95 % of cap.

    Returns
    -------
    Dict
        ``{
            "substation_cell": (row, col),
            "n_road_nodes": int,
            "n_edges": int,
            "cable_thermal_kw": float,
            "per_edge_annual_flow_kwh": {edge_key: float},  # sum |f| × hours
            "edges_congested": List[edge_key],  # any (edge, slice) hit cap
            "infeasible_slices": List[(period, slice_id)],  # KCL+thermal infeasible
            "max_edge_flow_kw": float,  # peak |f| across all edges/slices
            "scope": "audit",  # "audit" vs future "lp_integrated"
        }``
    """
    from core.land_use import LandUse
    road_nodes = [n for n in net.nodes if n.land_use == LandUse.ROAD]
    road_ids = [n.cell_id for n in road_nodes]
    road_set = set(road_ids)
    edges = list(net.edges)
    if not edges or not road_nodes:
        return {
            "substation_cell": substation_cell,
            "n_road_nodes": len(road_nodes),
            "n_edges": len(edges),
            "cable_thermal_kw": econ.stage_d_cable_thermal_kw_default(),
            "per_edge_annual_flow_kwh": {},
            "edges_congested": [],
            "infeasible_slices": [],
            "max_edge_flow_kw": 0.0,
            "scope": "audit",
        }
    # Build inflow/outflow adjacency: for each road node, the list of (edge_idx, sign)
    # where sign = +1 if node = edge.a (outflow direction), -1 if node = edge.b (inflow).
    adj: Dict[Tuple[int, int], List[Tuple[int, int]]] = {r: [] for r in road_ids}
    for ei, e in enumerate(edges):
        if e.a in road_set:
            adj[e.a].append((ei, +1))
        if e.b in road_set:
            adj[e.b].append((ei, -1))
    cable_thermal_kwh_per_slice: Dict[str, float] = {
        s.id: econ.stage_d_cable_thermal_kw_default() * s.hours_per_year
        for s in econ.slices
    }
    # Group cells by their nearest road node for KCL aggregation.
    road_to_cells: Dict[Tuple[int, int], List[Tuple[int, int]]] = {
        r: [] for r in road_ids
    }
    for cell_id, road_id in cell_to_road.items():
        if road_id in road_to_cells:
            road_to_cells[road_id].append(cell_id)
    slack_bucket = by_cell.get("district_slack", {}) or {}
    # fix: the substation is a SLACK BUS — it absorbs the residual
    # of per-cell net injections so KCL is always feasible across the road
    # graph. Trying to match the LP's adjusted balance (grid_import_eff × imp,
    # ac_eff × discharge, DSR offsets) here would re-implement the LP balance
    # constraint and is fragile. The audit's purpose is to surface the
    # ROUTING (per-edge flows) given the per-cell injections; substation as
    # slack guarantees feasibility when Phase 1's per-cell data is internally
    # consistent.

    per_edge_annual_flow_kwh: Dict[str, float] = {
        f"{e.a}-{e.b}": 0.0 for e in edges
    }
    edges_congested: List[str] = []
    infeasible_slices: List[Tuple[str, str]] = []
    audit_errors: List[str] = []
    max_edge_flow_kw = 0.0
    n_slices_solved = 0

    if not _HAS_PYOMO:
        # Skip the audit LP if Pyomo isn't available — return scaffold only.
        return {
            "substation_cell": substation_cell,
            "n_road_nodes": len(road_nodes),
            "n_edges": len(edges),
            "cable_thermal_kw": econ.stage_d_cable_thermal_kw_default(),
            "per_edge_annual_flow_kwh": per_edge_annual_flow_kwh,
            "edges_congested": [],
            "infeasible_slices": [],
            "max_edge_flow_kw": 0.0,
            "scope": "audit_pyomo_unavailable",
        }
    # Solve one small LP per slice. KCL: for each road node,
    # Σ (sign × f[ei]) = local_injection[road]. Objective: minimise Σ |f|.
    # |f[ei]| handled via aux Var ``af[ei]`` >= ±f[ei], minimise Σ af[ei].
    cap_per_slice = cable_thermal_kwh_per_slice
    slice_ids = [s.id for s in econ.slices]
    n_edges = len(edges)
    edge_keys = [f"{e.a}-{e.b}" for e in edges]
    for sid in slice_ids:
        # Aggregate cell-level injections at each road node.
        node_inj: Dict[Tuple[int, int], float] = {r: 0.0 for r in road_ids}
        for road_id, cells in road_to_cells.items():
            net_kwh = 0.0
            for cid in cells:
                cell_bucket = by_cell.get(cid, {}) or {}
                pv = (cell_bucket.get("pv_kwh", {}) or {}).get(sid, 0.0)
                v2g = (cell_bucket.get("v2g_discharge_kwh", {}) or {}).get(sid, 0.0)
                dem = (cell_bucket.get("demand_kwh", {}) or {}).get(sid, 0.0)
                # net injection at this cell = (pv + v2g) - demand. Positive
                # means cell EXPORTS to the road; negative means it DRAWS.
                net_kwh += (pv + v2g - dem)
            node_inj[road_id] += net_kwh
        # Substation is a SLACK BUS: absorbs whatever residual the network
        # has so KCL is always feasible. Total balance = 0 by construction.
        # If we left node_inj[substation] alone, it'd carry only the cells
        # mapped to it; here we subtract the TOTAL residual so the sum is 0.
        total_residual = sum(node_inj.values())
        node_inj[substation_cell] -= total_residual
        # Build the small LP for this slice.
        m = pyo.ConcreteModel()
        m.E = pyo.Set(initialize=list(range(n_edges)), ordered=True)
        cap = cap_per_slice[sid]
        m.f = pyo.Var(m.E, bounds=(-cap, +cap))
        m.af = pyo.Var(m.E, bounds=(0.0, cap))
        # |f| via two-sided bound: af >= f and af >= -f.
        m.abs_upper = pyo.Constraint(m.E, rule=lambda _m, e: _m.af[e] >= _m.f[e])
        m.abs_lower = pyo.Constraint(m.E, rule=lambda _m, e: _m.af[e] >= -_m.f[e])

        # KCL at every road node: sign×f sum = local injection.
        def _kcl(_m, rid_idx):
            rid = road_ids[rid_idx]
            terms = [sign * _m.f[ei] for ei, sign in adj[rid]]
            if not terms:
                return _m.f[0] == _m.f[0]  # trivial (isolated road)
            return sum(terms) == node_inj[rid]
        m.N = pyo.Set(initialize=list(range(len(road_ids))), ordered=True)
        m.kcl = pyo.Constraint(m.N, rule=_kcl)

        # Objective: minimise Σ af (= min total energy on cables).
        m.obj = pyo.Objective(expr=sum(m.af[e] for e in m.E),
                                sense=pyo.minimize)
        try:
            _solve_pyomo(m)
            n_slices_solved += 1
            for ei in range(n_edges):
                fv = float(pyo.value(m.f[ei]))
                af = abs(fv)
                per_edge_annual_flow_kwh[edge_keys[ei]] += af
                # Power (kW) during this slice = energy / hours.
                hours = max(1e-6, next(
                    (s.hours_per_year for s in econ.slices if s.id == sid),
                    1.0))
                pf = af / hours
                if pf > max_edge_flow_kw:
                    max_edge_flow_kw = pf
                if af >= 0.95 * cap and cap > 0:
                    key = f"{edge_keys[ei]}@{sid}"
                    edges_congested.append(key)
        except Exception as exc:  # noqa: BLE001
            infeasible_slices.append(("multi", sid))
            # (A4 re-time debug): the bare except was hiding the
            # real failure mode - keep the first few messages for diagnosis.
            if len(audit_errors) < 5:
                audit_errors.append(f"{sid}: {type(exc).__name__}: {exc}"[:300])

    return {
        "substation_cell": substation_cell,
        "n_road_nodes": len(road_nodes),
        "n_edges": len(edges),
        "n_slices_solved": n_slices_solved,
        "audit_errors": audit_errors,
        "cable_thermal_kw": econ.stage_d_cable_thermal_kw_default(),
        "per_edge_annual_flow_kwh": per_edge_annual_flow_kwh,
        "edges_congested": edges_congested[:50],  # truncate noisy diagnostic
        "n_edges_congested_events": len(edges_congested),
        "infeasible_slices": infeasible_slices[:20],
        "max_edge_flow_kw": max_edge_flow_kw,
        "scope": "audit",
        "note": ("Phase 2 AUDIT — per-edge flow + congestion diagnostic "
                 "from min-Σ|f| LP on Phase 1 per-cell injections, with the "
                 "substation cell acting as the SLACK BUS (absorbs the "
                 "residual to guarantee KCL feasibility). The dispatch LP "
                 "optimum is unchanged (Phase 1 = single-bus). The full "
                 "Phase 2 (per-cell curtailment Vars + LP feedback loop + "
                 "physically-consistent substation balance) is a future "
                 "increment — see CODEX_HANDOFF.md §14 '2026-05-28 — Stage "
                 "D Phase 2 FULL LP integration'."),
    }


def _stage_d_per_cell_breakdown(
    net: EnergyNetwork,
    econ: Economics,
    single_bus_result: DispatchResult,
    scenario: Optional["Scenario"] = None,
) -> Dict[object, Dict[str, Dict[str, float]]]:
    """Phase 1 — full per-cell breakdown decoration.

    Without per-edge thermal caps (Phase 2) or DC losses (Phase 3) the
    per-cell LP is mathematically equivalent to the single-bus LP: any
    cell's surplus PV can free-flow to any deficit cell at zero cost.
    So Phase 1 attributes the SINGLE-BUS optimum onto cells using
    physical/proportional shares, which the downstream consumers (Stage
    E NPV, viewer cell-flow lines, P2P trading in Phase 4) need as
    their input data structure. Reconciliation is BY CONSTRUCTION
    (per-item shares sum to 1.0). Phase 2 will replace this decoration
    with the result of a real per-cell LP that picks different optima
    when cable thermal caps bind.

    Shares (per slice, identical across slices since shares are static):
      - demand: cell.peak_demand_kw / Σ (existing logic; built cells only)
      - rooftop_pv: cell.rooftop_pv_cap_kwp × cell.pv_shading_multiplier / Σ
      - solar_farm: cell.solar_farm_cap_kwp × cell.pv_shading_multiplier / Σ
        (concentrated on the 25 SOLAR_FARM cells)
      - carport_pv: carport_kwp_for_cell(grid_cell) / Σ
        (concentrated on the 11 PARKING_LOT × is_carport_site cells)
      - floating_pv: per_cell_default × uptake / Σ
        (concentrated on BLUE_SPACE × is_floating_pv_site cells)
      - v2g_discharge: cell.households × ev_cars_per_household(income)
                       × v2g_willingness(income) / Σ (residential only)
      - district-shared items (battery/biomass/WTE/biogas/grid I/O):
        deposited at a single virtual `"district_slack"` key. Phase 2
        picks a real substation cell + adds the cable path.

    Returns
    -------
    Dict
        ``by_cell[cell_id_or_slack][item][slice_id] = kWh``. ``cell_id``
        is the (row, col) tuple matching ``EnergyNode.cell_id``. The
        special key ``"district_slack"`` holds district-shared items.
        Each cell also carries ``"net_district_flow_kwh"`` per slice:
        signed flow (positive = cell pulls from district through the
        future cable network; negative = cell exports surplus to district).
    """
    # ----- aggregate per-slice totals from the solved single-bus LP -----
    bs = single_bus_result.by_slice  # may be {} in degenerate cases
    slice_ids = [s.id for s in econ.slices]

    # Helper: total annual kWh from per-slice dict for one key (0 if missing).
    def total_annual(key: str) -> float:
        return sum((bs.get(s, {}) or {}).get(key, 0.0) for s in slice_ids)

    # ----- per-cell shares (static; same across all slices) -----
    # Demand: reuse the existing peak-share decomposition.
    demand_share: Dict[Tuple[int, int], float] = {}
    total_peak = 0.0
    for n in net.nodes:
        if n.category_name is None:
            continue
        p = n.peak_demand_kw
        if p <= 0:
            continue
        demand_share[n.cell_id] = p
        total_peak += p
    if total_peak > 0:
        for k in demand_share:
            demand_share[k] /= total_peak

    # Rooftop PV: cap × shading multiplier. Excludes solar farm cells.
    rooftop_share: Dict[Tuple[int, int], float] = {}
    total_roof = 0.0
    for n in net.nodes:
        if n.is_solar_farm or n.rooftop_pv_cap_kwp <= 0:
            continue
        eff = n.rooftop_pv_cap_kwp * float(n.pv_shading_multiplier or 1.0)
        if eff <= 0:
            continue
        rooftop_share[n.cell_id] = eff
        total_roof += eff
    if total_roof > 0:
        for k in rooftop_share:
            rooftop_share[k] /= total_roof

    # Solar farm: cap × shading. Only SOLAR_FARM cells.
    farm_share: Dict[Tuple[int, int], float] = {}
    total_farm = 0.0
    for n in net.nodes:
        if not n.is_solar_farm or n.solar_farm_cap_kwp <= 0:
            continue
        eff = n.solar_farm_cap_kwp * float(n.pv_shading_multiplier or 1.0)
        if eff <= 0:
            continue
        farm_share[n.cell_id] = eff
        total_farm += eff
    if total_farm > 0:
        for k in farm_share:
            farm_share[k] /= total_farm

    # Carport PV: per-site kWp from carport_siting. Only PARKING_LOT +
    # is_carport_site cells (or legacy eligible cells when sites are absent).
    carport_share: Dict[Tuple[int, int], float] = {}
    if net.grid is not None and any(
        c.is_carport_site for c in net.grid.all_cells()
    ):
        from layout.carport_siting import carport_kwp_for_cell
        total_cp = 0.0
        for c in net.grid.all_cells():
            if not c.is_carport_site:
                continue
            kwp = carport_kwp_for_cell(c)
            if kwp <= 0:
                continue
            carport_share[(c.row, c.col)] = kwp
            total_cp += kwp
        if total_cp > 0:
            for k in carport_share:
                carport_share[k] /= total_cp

    # Floating PV: deterministic per-cell default × uptake on tagged
    # cluster sites. Falls back to legacy eligible-land-use list otherwise.
    # canal corridor cells weight at the canal-top density
    # (210 kWp/cell) rather than the pond product (450 kWp/cell), matching
    # `Network.total_floating_pv_potential_kwp`. Same fix as the Stage-D
    # phase-2 share builder - see the long note there for why the aggregate
    # was never wrong but the per-cell allocation was.
    fpv_share: Dict[Tuple[int, int], float] = {}
    if net.grid is not None and any(
        c.floating_pv_cluster_id is not None for c in net.grid.all_cells()
    ):
        kwp_per_cell = (econ.floating_pv_kwp_per_cell_default()
                         * econ.floating_pv_uptake_fraction())
        canal_per_cell = econ.canal_pv_kwp_per_cell()
        eligible = set(econ.floating_pv_eligible_land_uses())
        total_fpv = 0.0
        for c in net.grid.all_cells():
            if not (c.is_floating_pv_site and c.land_use.value in eligible):
                continue
            w = canal_per_cell if c.amenity_subtype == "canal" else kwp_per_cell
            if w > 0:
                fpv_share[(c.row, c.col)] = w
                total_fpv += w
        if total_fpv > 0:
            for k in fpv_share:
                fpv_share[k] /= total_fpv

    # V2G: residential cells weighted by per-income EV-car ownership ×
    # willingness × households. Uses base-year ramp (2030) for consistency
    # with the headline by_slice extraction.
    v2g_share: Dict[Tuple[int, int], float] = {}
    has_ownership = bool(getattr(econ, "ev_vehicle_ownership", None))
    total_v2g = 0.0
    for n in net.nodes:
        if not n.is_residential or n.households <= 0:
            continue
        if has_ownership:
            inc = econ.income_for_category(n.category_name or "")
            if inc is None:
                continue
            w = (n.households
                 * econ.ev_cars_per_household(inc, None)
                 * econ.v2g_willingness(inc))
        else:
            # Legacy fallback: households / 5 (matches net.v2g_units default).
            w = n.households / 5.0
        if w <= 0:
            continue
        v2g_share[n.cell_id] = w
        total_v2g += w
    if total_v2g > 0:
        for k in v2g_share:
            v2g_share[k] /= total_v2g

    # ----- build per-cell, per-slice breakdown -----
    out: Dict[object, Dict[str, Dict[str, float]]] = {}

    def _attribute(item_key: str, share_map: Dict[Tuple[int, int], float]) -> None:
        """Spread per-slice item kWh across cells by share."""
        if not share_map:
            return
        for cell_id, s in share_map.items():
            if s <= 0:
                continue
            cell_bucket = out.setdefault(cell_id, {})
            slot = cell_bucket.setdefault(item_key, {})
            for sid in slice_ids:
                v = (bs.get(sid, {}) or {}).get(item_key, 0.0) * s
                slot[sid] = float(v)

    _attribute("demand_kwh", demand_share)
    # Rooftop + solar_farm + carport + floating come out as a single
    # ``pv_kwh`` aggregate in the single-bus by_slice. We can't disaggregate
    # the LP's PV decision back into the four physical buckets from
    # by_slice alone — to do that exactly we'd need to read each ``model.
    # *_pv`` Var. Phase 1 therefore attributes the AGGREGATE ``pv_kwh``
    # using a composite share that mixes the four physical caps weighted
    # by the headline installed capacity (capacities dict). This makes
    # per-cell PV sum-reconcile exactly while keeping the four-bucket
    # physical-location intent: a carport site visibly carries PV; a
    # residential rooftop without panels carries none.
    caps = single_bus_result.capacities or {}
    weighted_share: Dict[Tuple[int, int], float] = {}
    for w_kwp, sh in (
        (caps.get("rooftop_pv_kwp", 0.0), rooftop_share),
        (caps.get("solar_farm_kwp", 0.0), farm_share),
        (caps.get("carport_kwp", 0.0), carport_share),
        (caps.get("floating_pv_kwp", 0.0), fpv_share),
    ):
        if w_kwp <= 0 or not sh:
            continue
        for cid, s in sh.items():
            weighted_share[cid] = weighted_share.get(cid, 0.0) + w_kwp * s
    total_w = sum(weighted_share.values())
    if total_w > 0:
        for k in weighted_share:
            weighted_share[k] /= total_w
    _attribute("pv_kwh", weighted_share)

    _attribute("v2g_discharge_kwh", v2g_share)

    # District-shared items: deposit at the virtual ``district_slack``
    # bucket. Phase 2 picks a real substation cell + adds the cable path
    # connecting it to demand cells.
    slack: Dict[str, Dict[str, float]] = {}
    DISTRICT_ITEMS = (
        "battery_charge_kwh", "battery_discharge_kwh",
        "biomass_kwh", "wte_kwh", "biogas_kwh",
        "thermal_storage_charge_kwh", "thermal_storage_discharge_kwh",
        "dsr_reduce_kwh", "dsr_add_kwh",
        "solar_thermal_served_kwh",
        "grid_import_kwh", "grid_export_kwh",
    )
    for key in DISTRICT_ITEMS:
        slot = slack.setdefault(key, {})
        for sid in slice_ids:
            slot[sid] = float((bs.get(sid, {}) or {}).get(key, 0.0))
    out["district_slack"] = slack

    # Per-cell signed net flow with the district = local_demand - local_supply.
    # Positive = cell PULLS from district (its local PV + V2G < local demand).
    # Negative = cell EXPORTS surplus (rooftop PV exceeds local demand).
    # Sum over cells equals grid_import - grid_export + district_shared_gen
    # - battery_charge - thermal_charge - dsr_add + battery_discharge +
    # thermal_discharge + dsr_reduce. Sanity-checked by _stage_d_reconcile.
    for cid in set().union(demand_share, weighted_share, v2g_share):
        cell_bucket = out.setdefault(cid, {})
        flow = cell_bucket.setdefault("net_district_flow_kwh", {})
        for sid in slice_ids:
            d = cell_bucket.get("demand_kwh", {}).get(sid, 0.0)
            pv = cell_bucket.get("pv_kwh", {}).get(sid, 0.0)
            v2g = cell_bucket.get("v2g_discharge_kwh", {}).get(sid, 0.0)
            flow[sid] = float(d - pv - v2g)

    return out


def _stage_d_reconcile(
    by_cell: Dict[object, Dict[str, Dict[str, float]]],
    single_bus_result: DispatchResult,
    tol_frac: float = 0.01,
) -> None:
    """Verify per-cell breakdown sums to the single-bus aggregate within
    ``tol_frac`` for each per-slice item. Raises AssertionError on failure.

    Aggregate keys this checks:
      - demand_kwh, pv_kwh, v2g_discharge_kwh: per-cell, summed
      - battery_*, biomass, wte, biogas, thermal_*, dsr_*, grid_*: district_slack
    """
    bs = single_bus_result.by_slice or {}
    # Per-cell items: aggregate across cells, compare to annual total.
    PER_CELL_ITEMS = ("demand_kwh", "pv_kwh", "v2g_discharge_kwh")
    for item in PER_CELL_ITEMS:
        agg_target = sum((slc or {}).get(item, 0.0) for slc in bs.values())
        agg_sum = 0.0
        for cid, items in by_cell.items():
            if cid == "district_slack":
                continue
            slc = items.get(item, {}) or {}
            agg_sum += sum(slc.values())
        if abs(agg_target) <= 1.0:
            continue  # nothing to reconcile (item not deployed)
        rel = abs(agg_sum - agg_target) / abs(agg_target)
        assert rel <= tol_frac, (
            f"Stage D Phase 1 reconciliation FAILED for {item!r}: "
            f"sum-of-cells {agg_sum:,.1f} vs single-bus {agg_target:,.1f} "
            f"(rel error {rel:.4%}, tol {tol_frac:.2%})"
        )
    # District-shared items: just confirm the slack bucket carries the
    # right annual totals (already a direct copy by construction).
    slack = by_cell.get("district_slack", {}) or {}
    DISTRICT_ITEMS = ("grid_import_kwh", "grid_export_kwh",
                       "biomass_kwh", "wte_kwh", "biogas_kwh",
                       "battery_discharge_kwh")
    for item in DISTRICT_ITEMS:
        agg_target = sum((slc or {}).get(item, 0.0) for slc in bs.values())
        agg_sum = sum((slack.get(item, {}) or {}).values())
        if abs(agg_target) <= 1.0:
            continue
        rel = abs(agg_sum - agg_target) / abs(agg_target)
        assert rel <= tol_frac, (
            f"Stage D Phase 1 district_slack reconciliation FAILED for "
            f"{item!r}: slack {agg_sum:,.1f} vs single-bus {agg_target:,.1f} "
            f"(rel error {rel:.4%}, tol {tol_frac:.2%})"
        )


def _stage_d_per_cell_demand_kwh(
    net: EnergyNetwork,
    econ: Economics,
    scenario: Optional["Scenario"] = None,
) -> Dict[Tuple[int, int], Dict[str, float]]:
    """Per-cell, per-slice demand in kWh. Used by the Stage D spine
    and by Stage E NPV / viewer cell-flow lines.

    Sum across cells reproduces the single-bus aggregate that the LP
    extraction uses, namely
    ``net.demand_by_slice_kwh(econ)[s] × demand_mult × period_demand_mult[base_year]``.
    To stay consistent with the LP, we read the aggregate demand from
    the network (which already bundles base + cooling + heating + EV +
    faith / behavioural multipliers) and apportion it to each cell by
    the cell's peak-demand share. This guarantees byte-exact
    reconciliation with the single-bus headline.
    """
    aggregate_kwh = net.demand_by_slice_kwh(econ)
    demand_mult = (
        econ.total_demand_multiplier_with_biosolar(scenario)
        if scenario is not None else 1.0
    )
    # Period demand multiplier for the base year (1.0 when multi-period
    # is off, the base-year value from the trajectory otherwise).
    if econ.multi_period_enabled():
        base_year = econ.multi_period_base_year()
        period_mult = econ.period_demand_multiplier(base_year)
    else:
        period_mult = 1.0
    # Build per-cell peak share from peak_demand_kw (base + cooling
    # microclimate-adjusted + heating). Faith bumps are <2 % of total
    # district demand (23 RELIGIOUS cells × ~3 kW base) so the share
    # is well-approximated by the static peak; the per-cell map is for
    # spatial visualisation / Stage E NPV, not for LP capacity sizing.
    peaks: Dict[Tuple[int, int], float] = {}
    total_peak = 0.0
    for n in net.nodes:
        if n.category_name is None:
            continue
        peak = n.peak_demand_kw
        if peak <= 0:
            continue
        peaks[n.cell_id] = peak
        total_peak += peak
    if total_peak <= 0:
        return {}
    out: Dict[Tuple[int, int], Dict[str, float]] = {}
    for cell_id, peak in peaks.items():
        share = peak / total_peak
        out[cell_id] = {
            sid: float(aggregate_kwh[sid]) * demand_mult * period_mult * share
            for sid in aggregate_kwh
        }
    return out


def _solve_dispatch_pyomo_multi_period(
    net: EnergyNetwork,
    econ: Economics,
    scenario_name: str,
    scenario: Scenario,
    alpha: float = 0.0,
    fixed_build: Optional[dict] = None,
) -> DispatchResult:  # pragma: no cover
    """Solve the D1(b) multi-period vintaged-expansion LP and extract the
    DispatchResult.

    Headline reporting (for backwards-compat with the single-period
    cockpit + price-sweep schema):

    * ``capacities`` carries the END-OF-HORIZON installed capacities
      (the latest period in ``multi_period.periods``) -- the full
      deployment by year 25.
    * ``annual_cost_inr`` and ``annual_emissions_kgco2`` carry the
      ``base_year`` (2030) period values for direct comparability with
      the single-period baseline.
    * ``by_slice`` carries the ``base_year`` per-slice flows so the
      864-aware cockpit and price-sweep visualisations keep working.
    * ``lifetime_cost_inr`` = the LP objective cost expression directly
      (Σ_p w_p × annual_cost_by_period[p]) -- no post-hoc projection.
    * ``period_breakdown`` carries the per-period detail (annual cost /
      emissions / installed capacities / new-build / flows summary).
    """
    model, period_years, slice_ids, hours_of, weights = (
        _build_pyomo_model_multi_period(net, econ, scenario, alpha=alpha,
                                        fixed_build=fixed_build)
    )
    solver_name = _solve_pyomo(model)

    base_year = int(econ.multi_period_base_year())
    last_year = max(period_years)

    # Per-period inputs reused for flow-derived reporting.
    yield_rooftop_base = net.pv_yield_per_kwp_kwh(econ)
    orientation_active = bool(
        getattr(scenario, "allow_panel_orientation_choice", False)
    )
    yield_rooftop = (net.pv_yield_per_kwp_kwh_oriented(econ)
                     if orientation_active else yield_rooftop_base)
    yield_farm = net.pv_yield_per_kwp_kwh_solar_farm(econ)
    demand_kwh = net.demand_by_slice_kwh(econ)
    demand_mult = econ.total_demand_multiplier_with_biosolar(scenario)
    rooftop_yield_mult = econ.rooftop_pv_yield_multiplier_with_biosolar(scenario)
    bipv_yield_mult = econ.bipv_yield_multiplier_vs_rooftop()
    fpv_yield_mult = econ.floating_pv_yield_multiplier_vs_ground_mount()
    tracked_yield_mult = econ.tracked_pv_yield_multiplier()
    period_demand_mult = {y: econ.period_demand_multiplier(y)
                           for y in period_years}
    # EV-charging demand split (mirror of the builder) so per-period reported
    # demand ramps the EV term via the per-income table while the rest scales
    # by period_demand_mult. Collapses to demand_kwh[s] at the base year.
    ev_kwh_base = net.ev_charging_kwh_by_slice(econ, year=None)
    non_ev_kwh = {s: demand_kwh[s] - ev_kwh_base.get(s, 0.0) for s in slice_ids}
    ev_kwh_by_period = {
        y: net.ev_charging_kwh_by_slice(econ, year=y) for y in period_years
    }

    def _pv_supply_for_slice(p_target: int, s: str) -> float:
        pv = 0.0
        for pp in period_years:
            if pp > p_target:
                break
            roof_age = econ.pv_vintage_yield_factor("rooftop_pv", pp, p_target)
            farm_age = econ.pv_vintage_yield_factor("solar_farm", pp, p_target)
            pv += (yield_rooftop[s] * rooftop_yield_mult
                   * float(pyo.value(model.rooftop_new[pp])) * roof_age)
            pv += (yield_farm[s]
                   * float(pyo.value(model.farm_fixed_new[pp])) * farm_age)
            pv += (yield_farm[s] * tracked_yield_mult
                   * float(pyo.value(model.farm_tracked_new[pp])) * farm_age)
            pv += (yield_rooftop_base[s] * bipv_yield_mult
                   * float(pyo.value(model.bipv_new[pp])) * roof_age)
            pv += (yield_farm[s]
                   * float(pyo.value(model.carport_new[pp])) * farm_age)
            pv += (yield_farm[s] * fpv_yield_mult
                   * float(pyo.value(model.floating_pv_new[pp])) * farm_age)
        return pv

    # Build by_slice for the BASE year (2030 snapshot for headline / cockpit).
    by_slice: Dict[str, Dict[str, float]] = {}
    for s in slice_ids:
        by_slice[s] = {
            "demand_kwh": (demand_kwh[s] * demand_mult
                            * period_demand_mult[base_year]),
            "pv_kwh": _pv_supply_for_slice(base_year, s),
            "battery_charge_kwh": float(pyo.value(model.charge[base_year, s])),
            "battery_discharge_kwh": float(
                pyo.value(model.discharge[base_year, s])
            ),
            "v2g_discharge_kwh": float(pyo.value(model.v2g[base_year, s])),
            "biomass_kwh": float(pyo.value(model.biomass[base_year, s])),
            "wte_kwh": float(pyo.value(model.wte[base_year, s])),
            "biogas_kwh": float(pyo.value(model.biogas[base_year, s])),
            "thermal_storage_charge_kwh": float(
                pyo.value(model.thermal_chg[base_year, s])
            ),
            "thermal_storage_discharge_kwh": float(
                pyo.value(model.thermal_dis[base_year, s])
            ),
            "dsr_reduce_kwh": float(pyo.value(model.dsr_reduce[base_year, s])),
            "dsr_add_kwh": float(pyo.value(model.dsr_add[base_year, s])),
            # SOLAR WATER HEATING, AND IT MUST BE EXPORTED HERE.
            # `st_serve` reduces `effective_demand` inside the LP balance, but
            # `demand_kwh` above reports GROSS demand. Omitting this field
            # leaves the EXPORTED solution short by exactly the heat served,
            # and `test_per_slice_energy_balance_holds` caught it: the chain
            # halted at step 3 with a worst residual of 565,624 kWh. Reported
            # as a REDUCTION term alongside dsr_reduce, which is the same
            # shape - both are load that never reaches the grid.
            "solar_thermal_served_kwh": (
                float(pyo.value(model.st_serve[base_year, s]))
                if hasattr(model, "st_serve") else 0.0),
            # REV-2: managed-EV charge shift (sum of classes;
            # 0.0 when the smart-charging Vars are absent/zero-bounded).
            "ev_shift_out_kwh": (
                sum(float(pyo.value(model.ev_shift_out[base_year, c, s]))
                    for c in model.EVC)
                if hasattr(model, "ev_shift_out") else 0.0),
            "ev_shift_in_kwh": (
                sum(float(pyo.value(model.ev_shift_in[base_year, c, s]))
                    for c in model.EVC)
                if hasattr(model, "ev_shift_in") else 0.0),
            "grid_import_kwh": float(pyo.value(model.imp[base_year, s])),
            "grid_export_kwh": float(pyo.value(model.exp[base_year, s])),
            # Data-centre PPA offtake (N21) — 0.0 when the PPA Var is absent.
            "dc_ppa_kwh": (float(pyo.value(model.dc_ppa[base_year, s]))
                           if hasattr(model, "dc_ppa") else 0.0),
            # B21: buy-side green open-access energy DELIVERED
            # in the slice - 0.0 when the purchase Var is absent.
            "green_purchase_kwh": (float(pyo.value(model.gp[base_year, s]))
                                   if hasattr(model, "gp") else 0.0),
            # FX-1/: explicit PV spill. pv_kwh stays GROSS;
            # delivered PV = pv_kwh - curtailment_kwh.
            "curtailment_kwh": (float(pyo.value(model.pv_curtail[base_year, s]))
                                if hasattr(model, "pv_curtail") else 0.0),
        }

    # End-of-horizon installed capacities (latest period).
    def _v(name, p):
        return float(pyo.value(getattr(model, name)[p]))

    def _v_opt(name, p):
        """Like _v, but 0.0 when the component was never created.

        Flag-gated technologies add no Var at all when switched off, so a
        plain getattr would raise. Reporting them as zero is the correct
        reading: the technology is absent, not missing.
        """
        c = getattr(model, name, None)
        return float(pyo.value(c[p])) if c is not None else 0.0

    cap_rooftop = _v("rooftop_installed", last_year)
    cap_farm_fixed = _v("farm_fixed_installed", last_year)
    cap_farm_tracked = _v("farm_tracked_installed", last_year)
    cap_farm_total = cap_farm_fixed + cap_farm_tracked
    cap_batt = _v("battery_installed", last_year)
    cap_v2g = _v("v2g_installed", last_year)
    cap_biomass = _v("biomass_installed", last_year)
    cap_wte = _v("wte_installed", last_year)
    cap_biogas = _v("biogas_installed", last_year)
    cap_thermal = _v("thermal_installed", last_year)
    cap_bipv = _v("bipv_installed", last_year)
    cap_carport = _v("carport_installed", last_year)
    cap_floating_pv = _v("floating_pv_installed", last_year)
    # solar water heating. Sized in m2 of aperture, and the
    # USEFUL output is heat delivered to a tap, not heat collected -
    # collected minus standing loss minus anything above the day's draw.
    # Reporting the collected figure would overstate what the technology
    # does by the ~21% the tank loses while it waits for the morning.
    cap_solar_thermal_m2 = _v_opt("st_installed", last_year)
    solar_thermal_served = (
        sum(float(pyo.value(model.st_serve[base_year, s])) for s in slice_ids)
        if hasattr(model, "st_serve") else 0.0)
    tracked_active = 1.0 if cap_farm_tracked > 1.0 else 0.0

    # Base-year headline aggregates.
    pv_generation = sum(b["pv_kwh"] for b in by_slice.values())
    annual_demand = sum(b["demand_kwh"] for b in by_slice.values())
    grid_import = sum(b["grid_import_kwh"] for b in by_slice.values())
    grid_export = sum(b["grid_export_kwh"] for b in by_slice.values())
    biomass_gen = sum(b["biomass_kwh"] for b in by_slice.values())
    wte_gen = sum(b["wte_kwh"] for b in by_slice.values())
    biogas_gen = sum(b["biogas_kwh"] for b in by_slice.values())
    thermal_throughput = sum(b["thermal_storage_discharge_kwh"]
                               for b in by_slice.values())
    battery_throughput = sum(b["battery_discharge_kwh"]
                              for b in by_slice.values())
    v2g_throughput = sum(b["v2g_discharge_kwh"] for b in by_slice.values())
    annual_cost = float(pyo.value(model.cost_expr))
    annual_emissions = float(pyo.value(model.emissions_expr))
    lifetime_cost = float(pyo.value(model.lifetime_cost_expr))
    dsr_shifted = sum(float(pyo.value(model.dsr_reduce[base_year, s]))
                       for s in slice_ids)
    ev_smart_shifted = sum(b.get("ev_shift_out_kwh", 0.0)
                           for b in by_slice.values())

    # Per-period breakdown.
    represents_by_year: Dict[int, int] = {
        int(p["year"]): int(p["represents_years"])
        for p in econ.multi_period_periods()
    }
    period_breakdown: Dict[int, Dict[str, object]] = {}
    for p in period_years:
        new_caps = {
            "rooftop_pv_kwp": _v("rooftop_new", p),
            "farm_fixed_kwp": _v("farm_fixed_new", p),
            "farm_tracked_kwp": _v("farm_tracked_new", p),
            "battery_kwh": _v("battery_new", p),
            "v2g_units": _v("v2g_new", p),
            "biomass_kw_e": _v("biomass_new", p),
            "wte_kw_e": _v("wte_new", p),
            "biogas_kw_e": _v("biogas_new", p),
            "thermal_storage_kwh": _v("thermal_new", p),
            "bipv_kwp": _v("bipv_new", p),
            "carport_kwp": _v("carport_new", p),
            "floating_pv_kwp": _v("floating_pv_new", p),
            "solar_thermal_m2": _v_opt("st_new", p),
        }
        inst_caps = {
            "rooftop_pv_kwp": _v("rooftop_installed", p),
            "solar_farm_kwp": _v("farm_fixed_installed", p)
                + _v("farm_tracked_installed", p),
            "battery_kwh": _v("battery_installed", p),
            "v2g_units": _v("v2g_installed", p),
            "biomass_kw_e": _v("biomass_installed", p),
            "wte_kw_e": _v("wte_installed", p),
            "biogas_kw_e": _v("biogas_installed", p),
            "thermal_storage_kwh": _v("thermal_installed", p),
            "bipv_kwp": _v("bipv_installed", p),
            "carport_kwp": _v("carport_installed", p),
            "floating_pv_kwp": _v("floating_pv_installed", p),
            "solar_thermal_m2": _v_opt("st_installed", p),
        }
        gi_p = sum(float(pyo.value(model.imp[p, s])) for s in slice_ids)
        ge_p = sum(float(pyo.value(model.exp[p, s])) for s in slice_ids)
        pv_p = sum(_pv_supply_for_slice(p, s) for s in slice_ids)
        # B21: per-period wheeled-green energy + contracted MW
        # (0 when the purchase Var is absent) - feeds the B19 boundary
        # ledger's IN-flow line + the thesis per-period table.
        gp_p = (sum(float(pyo.value(model.gp[p, s])) for s in slice_ids)
                if hasattr(model, "gp") else 0.0)
        demand_p = sum(demand_mult * period_demand_mult[p]
                        * (non_ev_kwh[s] + ev_kwh_by_period[p].get(s, 0.0))
                        for s in slice_ids)
        period_breakdown[p] = {
            "represents_years": int(represents_by_year.get(p, 0)),
            "weight": float(weights[p]),
            "annual_cost_inr": float(pyo.value(model.annual_cost_by_period[p])),
            "annual_emissions_kgco2": float(
                pyo.value(model.annual_emissions_by_period[p])
            ),
            "annual_demand_kwh": float(demand_p),
            "grid_import_kwh": float(gi_p),
            "grid_export_kwh": float(ge_p),
            "pv_generation_kwh": float(pv_p),
            "green_purchase_kwh": float(gp_p),
            # energy we can supply to the data centre"). The PPA was
            # only ever reported for the BASE YEAR, so the model could
            # not answer the question that decides whether the
            # counterparty stays viable as demand grows. Now per period.
            "dc_ppa_kwh": (
                sum(float(pyo.value(model.dc_ppa[p, s])) for s in slice_ids)
                if hasattr(model, "dc_ppa") else 0.0),
            "green_purchase_mw": (float(pyo.value(model.gp_mw[p]))
                                  if hasattr(model, "gp_mw") else 0.0),
            "new_build": new_caps,
            "installed_capacities": inst_caps,
        }

    result = DispatchResult(
        scenario=scenario_name,
        solver=solver_name,
        alpha=alpha,
        capacities={
            "rooftop_pv_kwp": cap_rooftop,
            "solar_farm_kwp": cap_farm_total,
            "solar_farm_fixed_kwp": cap_farm_fixed,
            "solar_farm_tracked_kwp": cap_farm_tracked,
            "battery_kwh": cap_batt,
            "v2g_units": cap_v2g,
            "biomass_kw_e": cap_biomass,
            "tracked_pv_active": tracked_active,
            "wte_kw_e": cap_wte,
            "biogas_kw_e": cap_biogas,
            "thermal_storage_kwh": cap_thermal,
            "bipv_kwp": cap_bipv,
            "carport_kwp": cap_carport,
            "floating_pv_kwp": cap_floating_pv,
            "solar_thermal_m2": cap_solar_thermal_m2,
            "solar_thermal_served_kwh": solar_thermal_served,
        },
        annual_cost_inr=annual_cost,
        lifetime_cost_inr=lifetime_cost,
        annual_emissions_kgco2=annual_emissions,
        annual_demand_kwh=annual_demand,
        grid_import_kwh=grid_import,
        grid_export_kwh=grid_export,
        pv_generation_kwh=pv_generation,
        battery_throughput_kwh=battery_throughput,
        v2g_discharge_kwh=v2g_throughput,
        biomass_generation_kwh=biomass_gen,
        wte_generation_kwh=wte_gen,
        biogas_generation_kwh=biogas_gen,
        thermal_storage_throughput_kwh=thermal_throughput,
        dsr_shifted_kwh=dsr_shifted,
        ev_smart_shifted_kwh=ev_smart_shifted,
        by_slice=by_slice,
        period_breakdown=period_breakdown,
    )
    # Data-centre PPA offtake (N21): base-year kWh sold + net revenue (both 0
    # when the PPA is off). Net price = offtake-weighted net tariff of the
    # active counterparties (tariff·(1-loss) - wheeling - CSS).
    _dc_ppa_kwh = sum(b.get("dc_ppa_kwh", 0.0) for b in by_slice.values())
    _dc_net_price = 0.0
    if econ.ppa_enabled():
        _acps = econ.ppa_active_counterparties()
        _toff = sum(float(sp.get("offtake_kw_constant", 0.0))
                    for sp in _acps.values()) or 1.0
        _dc_net_price = sum(
            econ.ppa_counterparty_net_tariff_inr_per_kwh(nm)
            * float(sp.get("offtake_kw_constant", 0.0))
            for nm, sp in _acps.items()) / _toff
    result.__dict__["dc_ppa_offtake_kwh"] = _dc_ppa_kwh
    result.__dict__["dc_ppa_revenue_inr"] = _dc_ppa_kwh * _dc_net_price
    # Stage-E requirement 4: REPORT THE TEMPORAL MATCH rather
    # than assert it. Share of PPA offtake delivered in slices where the
    # district imported nothing from the grid - i.e. genuinely sold surplus
    # rather than energy the town was simultaneously buying in. The
    # strengthened `dc_ppa_no_import_resale` constraint should make this
    # 1.0 by construction; publishing it turns "the constraint is correct"
    # from a claim into a measurement, and it is the number to quote when
    # asked whether the town ever resold grid power to the data centre.
    _dc_matched = sum(
        b.get("dc_ppa_kwh", 0.0) for b in by_slice.values()
        if b.get("grid_import_kwh", 0.0) <= 1e-9
    )
    result.__dict__["dc_ppa_surplus_matched_kwh"] = _dc_matched
    result.__dict__["dc_ppa_temporal_match_fraction"] = (
        _dc_matched / _dc_ppa_kwh if _dc_ppa_kwh > 1e-9 else 1.0
    )
    # The metric above answers "did we ever resell grid power" - it does NOT
    # answer "how much of the buyer's load do we actually cover", which is
    # the question that decides whether this counterparty is credible. Both
    # are now computed AND exported; the temporal-match one had been
    # computed since but was missing from the export whitelist,
    # so it read as null in dispatch_results.json and in every report.
    # COVERAGE = what we deliver / what a flat contracted block would need.
    # The town supplies 06:00-17:00 only, at the full contract rate 08:00-
    # 15:00 and nothing at all overnight or at the 19:00 peak, so coverage
    # is structurally well below 1.0 and SHOULD be. That is not a shortfall
    # to hide: India's RPO obligation rises to 43.33% by FY2029-30, so a
    # daytime-solar contract covering ~38% of a hall's annual load nearly
    # discharges the buyer's entire statutory renewable quota. Digital
    # Edge's comparable Navi Mumbai deal covers ~24%.
    _dc_contract_kwh = 0.0
    if econ.ppa_enabled():
        _dc_contract_kwh = sum(
            float(sp.get("offtake_kw_constant", 0.0)) * 8760.0
            for sp in econ.ppa_active_counterparties().values())
    result.__dict__["dc_ppa_contract_kwh"] = _dc_contract_kwh
    result.__dict__["dc_ppa_coverage_fraction"] = (
        _dc_ppa_kwh / _dc_contract_kwh if _dc_contract_kwh > 1e-9 else 0.0
    )
    # Hours of the day in which ANY energy is delivered, and the hours in
    # which none is - published so the shape is a reported fact rather than
    # something a reader has to reconstruct from by_slice.
    _dc_by_hour: Dict[int, float] = {}
    for _sid, _b in by_slice.items():
        _k = _b.get("dc_ppa_kwh", 0.0)
        if _k <= 0:
            continue
        try:
            _hh = int(str(_sid).rsplit("_", 1)[-1])
        except (ValueError, TypeError):
            continue
        _dc_by_hour[_hh] = _dc_by_hour.get(_hh, 0.0) + _k
    result.__dict__["dc_ppa_kwh_by_hour"] = _dc_by_hour
    result.__dict__["dc_ppa_hours_supplied"] = sorted(_dc_by_hour)
    result.__dict__["dc_ppa_hours_unsupplied"] = [
        h for h in range(24) if h not in _dc_by_hour]
    # B21: buy-side green purchase - base-year delivered kWh +
    # cost at the delivered price + contracted MW per period (0/empty when
    # the block is off).
    _gp_kwh = sum(b.get("green_purchase_kwh", 0.0) for b in by_slice.values())
    result.__dict__["green_purchase_kwh"] = _gp_kwh
    result.__dict__["green_purchase_cost_inr"] = (
        _gp_kwh * econ.green_purchase_delivered_price_inr_per_kwh()
        if _gp_kwh > 0.0 else 0.0)
    result.__dict__["green_purchase_mw_by_period"] = (
        {str(p): float(pyo.value(model.gp_mw[p])) for p in period_years}
        if hasattr(model, "gp_mw") else {})
    # the SIZED grid connection (MW) and what it costs. Absent
    # when interconnection.sizing is off, so the flat-charge path is
    # structurally unchanged. This is the number that carries the
    # "decentralised supply needs less imported infrastructure" claim, so it
    # is published rather than left inside the objective.
    if hasattr(model, "grid_connection_mw"):
        _conn_mw = float(pyo.value(model.grid_connection_mw))
        result.__dict__["grid_connection_mw"] = _conn_mw
        result.__dict__["grid_connection_cost_inr"] = (
            econ.interconnection_annualised_inr_per_mw() * _conn_mw)
    # the internal-network parity charge, itemised. Published so
    # the infrastructure line can be read off the result instead of being
    # re-derived in a report script. Absent-as-zero when the flag is off.
    if econ.en_cost_in_production_enabled():
        from energy.electrical_assets import (
            production_network_annualised_inr,
            production_network_annualised_kgco2,
        )
        result.__dict__["internal_network_breakdown"] = (
            production_network_annualised_inr(net, econ))
        result.__dict__["internal_network_embodied"] = (
            production_network_annualised_kgco2(net, econ))
    # base-year diesel-backup energy and its cost. Published so
    # the BAU parity test can RECONSTRUCT the cost from live components
    # instead of carrying a pinned constant - the symmetric-diesel change
    # added a term that test could not see, and a parity test
    # that cannot see a cost term silently stops testing parity.
    if hasattr(model, "diesel_backup"):
        _d_kwh = float(pyo.value(model.diesel_backup[base_year]))
        result.__dict__["diesel_backup_kwh"] = _d_kwh
        result.__dict__["diesel_backup_cost_inr"] = (
            econ.diesel_displacement_value_inr_per_kwh() * _d_kwh)
    # RES-1: per-(period, slice) unserved energy for the black-swan pack's
    # served%/critical reporting (absent unless the resilience hook built
    # the Var; 0/{} never appears on production results).
    if hasattr(model, "unserved"):
        _us_ps = {
            p: {s: float(pyo.value(model.unserved[p, s])) for s in slice_ids}
            for p in period_years
        }
        result.__dict__["unserved_kwh_by_period_slice"] = _us_ps
        result.__dict__["unserved_kwh_by_period"] = {
            p: sum(v.values()) for p, v in _us_ps.items()
        }
        result.__dict__["unserved_kwh"] = sum(
            sum(v.values()) for v in _us_ps.values())
    return result


def solve_dispatch_pyomo(
    net: EnergyNetwork,
    econ: Economics,
    scenario_name: str = "pv_battery_v2g",
    alpha: float = 0.0,
    fixed_build: Optional[dict] = None,
) -> DispatchResult:  # pragma: no cover
    """Run the Stage C Pyomo MILP. Requires pyomo + a backend solver.

 supervisor refactor: now Stage C-complete -- models
    all 12+ Stage C technologies + carbon-alpha-weighted objective.

    Parameters
    ----------
    alpha : float
        Carbon-weight in [0, 1]. 0 = pure cost minimisation; 1 = pure
        emissions minimisation. The MILP objective is
        ``(1 - alpha) * cost + alpha * carbon_price * emissions``.

    Returns
    -------
    DispatchResult
        Provably-optimal LP/MILP solution (HiGHS optimality tolerance
        applies; typically gap < 0.01%).
    """
    if not _HAS_PYOMO:
        raise RuntimeError("pyomo is not installed")
    scenario = econ.scenario(scenario_name)
    # (Stage D scaffold — Claude 2): branch to the per-cell
    # / multi-bus LP when `stage_d.enabled: true`. Currently raises
    # NotImplementedError because the per-cell LP is not built yet;
    # the gate exists so the wiring lands now and the LP can land
    # incrementally without touching dispatch.py again.
    if econ.stage_d_enabled():
        return _solve_dispatch_pyomo_stage_d(
            net, econ, scenario_name, scenario, alpha=alpha,
        )
    # (D1(b) Phase 2 — Claude 2): branch to the vintaged
    # multi-period capacity-expansion LP when the YAML opt-in flag is on.
    # The single-period path below stays byte-for-byte unchanged when
    # multi_period.enabled is false.
    if econ.multi_period_enabled():
        return _solve_dispatch_pyomo_multi_period(
            net, econ, scenario_name, scenario, alpha=alpha,
            fixed_build=fixed_build,
        )
    if fixed_build:
        raise ValueError(
            "fixed_build is a multi-period (RES-1) feature; the "
            "single-period builder does not support it")
    model, slice_ids, hours_of = _build_pyomo_model(net, econ, scenario, alpha=alpha)
    solver_name = _solve_pyomo(model)

    # ---- Extract capacities --------------------------------------------
    # (A18 LP module-mix, Claude 2): per-module rooftop kWp
    # is reported alongside the aggregate when the LP exposed the 3
    # module variables. `model.rooftop_kwp` is a Pyomo Expression in
    # the active path so pyo.value still works seamlessly.
    cap_rooftop = float(pyo.value(model.rooftop_kwp))
    cap_rooftop_mono = (
        float(pyo.value(model.rooftop_kwp_mono))
        if getattr(model, "rooftop_kwp_mono", None) is not None
        else 0.0
    )
    cap_rooftop_poly = (
        float(pyo.value(model.rooftop_kwp_poly))
        if getattr(model, "rooftop_kwp_poly", None) is not None
        else 0.0
    )
    cap_rooftop_thinfilm = (
        float(pyo.value(model.rooftop_kwp_thinfilm))
        if getattr(model, "rooftop_kwp_thinfilm", None) is not None
        else 0.0
    )
    cap_farm_fixed = float(pyo.value(model.farm_fixed_kwp))
    cap_farm_tracked = float(pyo.value(model.farm_tracked_kwp))
    cap_farm_total = cap_farm_fixed + cap_farm_tracked
    cap_batt = float(pyo.value(model.battery_kwh))
    cap_v2g = float(pyo.value(model.v2g_units))
    cap_biomass = float(pyo.value(model.biomass_kw_e))
    cap_wte = float(pyo.value(model.wte_kw_e))
    cap_biogas = float(pyo.value(model.biogas_kw_e))
    cap_thermal = float(pyo.value(model.thermal_storage_kwh))
    cap_bipv = float(pyo.value(model.bipv_kwp))
    cap_carport = float(pyo.value(model.carport_kwp))
    cap_floating_pv = float(pyo.value(model.floating_pv_kwp))
    tracked_active = 1.0 if cap_farm_tracked > 1.0 else 0.0  # binary-like indicator

    # ---- Extract per-slice flows ---------------------------------------
    orientation_active = bool(getattr(scenario, "allow_panel_orientation_choice", False))
    yield_rooftop_base = net.pv_yield_per_kwp_kwh(econ)
    yield_rooftop = (net.pv_yield_per_kwp_kwh_oriented(econ)
                     if orientation_active else yield_rooftop_base)
    yield_farm = net.pv_yield_per_kwp_kwh_solar_farm(econ)
    demand_kwh = net.demand_by_slice_kwh(econ)
    rooftop_yield_mult = econ.rooftop_pv_yield_multiplier_with_biosolar(scenario)
    demand_mult = econ.total_demand_multiplier_with_biosolar(scenario)
    bipv_yield_mult = econ.bipv_yield_multiplier_vs_rooftop()
    fpv_yield_mult = econ.floating_pv_yield_multiplier_vs_ground_mount()
    tracked_yield_mult = econ.tracked_pv_yield_multiplier()

    by_slice: Dict[str, Dict[str, float]] = {}
    for s in slice_ids:
        pv_kwh = (
            yield_rooftop[s] * rooftop_yield_mult * cap_rooftop
            + yield_farm[s] * cap_farm_fixed
            + yield_farm[s] * tracked_yield_mult * cap_farm_tracked
            + yield_rooftop_base[s] * bipv_yield_mult * cap_bipv
            + yield_farm[s] * cap_carport
            + yield_farm[s] * fpv_yield_mult * cap_floating_pv
        )
        by_slice[s] = {
            "demand_kwh": demand_kwh[s] * demand_mult,
            "pv_kwh": pv_kwh,
            "battery_charge_kwh": float(pyo.value(model.charge[s])),
            "battery_discharge_kwh": float(pyo.value(model.discharge[s])),
            "v2g_discharge_kwh": float(pyo.value(model.v2g[s])),
            "biomass_kwh": float(pyo.value(model.biomass[s])),
            "wte_kwh": float(pyo.value(model.wte[s])),
            "biogas_kwh": float(pyo.value(model.biogas[s])),
            "thermal_storage_charge_kwh": float(pyo.value(model.thermal_chg[s])),
            "thermal_storage_discharge_kwh": float(pyo.value(model.thermal_dis[s])),
            "dsr_reduce_kwh": float(pyo.value(model.dsr_reduce[s])),
            "dsr_add_kwh": float(pyo.value(model.dsr_add[s])),
            # REV-2: managed-EV charge shift (sum of classes).
            "ev_shift_out_kwh": (
                sum(float(pyo.value(model.ev_shift_out[c, s]))
                    for c in model.EVC)
                if hasattr(model, "ev_shift_out") else 0.0),
            "ev_shift_in_kwh": (
                sum(float(pyo.value(model.ev_shift_in[c, s]))
                    for c in model.EVC)
                if hasattr(model, "ev_shift_in") else 0.0),
            "grid_import_kwh": float(pyo.value(model.imp[s])),
            "grid_export_kwh": float(pyo.value(model.exp[s])),
            # B21: buy-side green open-access energy delivered.
            "green_purchase_kwh": (float(pyo.value(model.gp[s]))
                                   if hasattr(model, "gp") else 0.0),
            # FX-1/: explicit PV spill (pv_kwh stays gross).
            "curtailment_kwh": (float(pyo.value(model.pv_curtail[s]))
                                if hasattr(model, "pv_curtail") else 0.0),
        }
    pv_generation = sum(b["pv_kwh"] for b in by_slice.values())
    annual_demand = sum(b["demand_kwh"] for b in by_slice.values())
    grid_import = sum(b["grid_import_kwh"] for b in by_slice.values())
    grid_export = sum(b["grid_export_kwh"] for b in by_slice.values())
    biomass_gen = sum(b["biomass_kwh"] for b in by_slice.values())
    wte_gen = sum(b["wte_kwh"] for b in by_slice.values())
    biogas_gen = sum(b["biogas_kwh"] for b in by_slice.values())
    thermal_throughput = sum(b["thermal_storage_discharge_kwh"] for b in by_slice.values())
    battery_throughput = sum(b["battery_discharge_kwh"] for b in by_slice.values())
    v2g_throughput = sum(b["v2g_discharge_kwh"] for b in by_slice.values())

    annual_cost = float(pyo.value(model.cost_expr))
    annual_emissions = float(pyo.value(model.emissions_expr))
    # DSR total shifted = sum of reductions (paired with adds by conservation).
    dsr_shifted = sum(float(pyo.value(model.dsr_reduce[s])) for s in slice_ids)
    # REV-2: EV energy rescheduled by managed charging (out side).
    ev_smart_shifted = sum(b.get("ev_shift_out_kwh", 0.0)
                           for b in by_slice.values())

    # Lifetime cost (caveat-14): non-grid CAPEX/OPEX * lifetime + grid * annuity.
    # CRIT-2c NOTE: this LEGACY single-period projection escalates
    # the NET grid position (import - export) together, i.e. export still
    # escalates here. Documented and left as-is: the production convention
    # (import escalates, export flat-real - lives in the multi-period
    # objective, which REPLACES this projection on the production path.
    grid_import_annual_inr = sum(
        by_slice[s]["grid_import_kwh"] * econ.import_tariff(s) for s in slice_ids
    )
    grid_export_annual_inr = grid_export * econ.export_tariff()
    grid_net_annual = grid_import_annual_inr - grid_export_annual_inr
    non_grid_annual = annual_cost - grid_net_annual
    lifetime_yrs = int(econ.project_lifetime_years())
    # A21: tariff escalation now honours active price scenario.
    esc = float(econ.tariff_escalation_real_annual_value())
    if esc != 0.0 and lifetime_yrs > 0:
        grid_factor = (1.0 + esc) * ((1.0 + esc) ** lifetime_yrs - 1.0) / esc
    else:
        grid_factor = float(lifetime_yrs)
    # (Phases 2A/2B/2C/2D/4): see Pyomo path comment above.
    lifetime_demand_growth = float(econ.lifetime_demand_growth_factor())
    lifetime_cost = (non_grid_annual * lifetime_yrs
                     + grid_net_annual * grid_factor * lifetime_demand_growth)
    # (D2 —: PMSGY subsidy decay over the 25-yr
    # horizon, lifetime-cost only (annual LP untouched). Reconstruct the
    # rooftop-CAPEX cashflow that entered annual_cost from the solved
    # capacities (module-split when A18 is active, else aggregate), then
    # uplift it by (1-life_avg)/(1-snapshot). 1.0 (no-op) when the decay
    # block is absent. See costs.py:pmsgy_lifetime_capex_uplift_factor.
    rooftop_capex_mult_post = (
        econ.rooftop_pv_capex_multiplier_with_solshare(scenario)
        * econ.rooftop_pv_capex_multiplier_with_biosolar(scenario)
    )
    if cap_rooftop_mono or cap_rooftop_poly or cap_rooftop_thinfilm:
        rooftop_annual_capex_inr = (
            econ.rooftop_pv_module_annualised_inr_per_kwp("mono_perc")
            * cap_rooftop_mono
            + econ.rooftop_pv_module_annualised_inr_per_kwp("poly_si")
            * cap_rooftop_poly
            + econ.rooftop_pv_module_annualised_inr_per_kwp("thin_film_cdte")
            * cap_rooftop_thinfilm
        ) * rooftop_capex_mult_post
    else:
        rooftop_annual_capex_inr = (
            econ.rooftop_pv_annualised_inr_per_kwp()
            * cap_rooftop * rooftop_capex_mult_post
        )
    pmsgy_uplift = float(econ.pmsgy_lifetime_capex_uplift_factor())
    lifetime_cost += rooftop_annual_capex_inr * (pmsgy_uplift - 1.0) * lifetime_yrs

    result = DispatchResult(
        scenario=scenario_name,
        solver=solver_name,
        alpha=alpha,
        capacities={
            "rooftop_pv_kwp": cap_rooftop,
            "rooftop_pv_kwp_mono_perc": cap_rooftop_mono,
            "rooftop_pv_kwp_poly_si": cap_rooftop_poly,
            "rooftop_pv_kwp_thin_film_cdte": cap_rooftop_thinfilm,
            "solar_farm_kwp": cap_farm_total,
            "solar_farm_fixed_kwp": cap_farm_fixed,
            "solar_farm_tracked_kwp": cap_farm_tracked,
            "battery_kwh": cap_batt,
            "v2g_units": cap_v2g,
            "biomass_kw_e": cap_biomass,
            "tracked_pv_active": tracked_active,
            "wte_kw_e": cap_wte,
            "biogas_kw_e": cap_biogas,
            "thermal_storage_kwh": cap_thermal,
            "bipv_kwp": cap_bipv,
            "carport_kwp": cap_carport,
            "floating_pv_kwp": cap_floating_pv,
        },
        annual_cost_inr=annual_cost,
        lifetime_cost_inr=lifetime_cost,
        annual_emissions_kgco2=annual_emissions,
        annual_demand_kwh=annual_demand,
        grid_import_kwh=grid_import,
        grid_export_kwh=grid_export,
        pv_generation_kwh=pv_generation,
        battery_throughput_kwh=battery_throughput,
        v2g_discharge_kwh=v2g_throughput,
        biomass_generation_kwh=biomass_gen,
        wte_generation_kwh=wte_gen,
        biogas_generation_kwh=biogas_gen,
        thermal_storage_throughput_kwh=thermal_throughput,
        dsr_shifted_kwh=dsr_shifted,
        ev_smart_shifted_kwh=ev_smart_shifted,
        by_slice=by_slice,
    )
    # B21: buy-side green purchase fields (0 when off).
    _gp_kwh_sp = sum(b.get("green_purchase_kwh", 0.0)
                     for b in by_slice.values())
    result.__dict__["green_purchase_kwh"] = _gp_kwh_sp
    result.__dict__["green_purchase_cost_inr"] = (
        _gp_kwh_sp * econ.green_purchase_delivered_price_inr_per_kwh()
        if _gp_kwh_sp > 0.0 else 0.0)
    result.__dict__["green_purchase_mw_by_period"] = (
        {"2030": float(pyo.value(model.gp_mw))}
        if hasattr(model, "gp_mw") else {})
    return result


# ---------------------------------------------------------------------------
# Public entry point: prefer Pyomo, fall back to merit-order.
# ---------------------------------------------------------------------------
def solve_dispatch(
    net: EnergyNetwork,
    econ: Optional[Economics] = None,
    scenario_name: str = "pv_battery_v2g",
    prefer_solver: str = "auto",
    alpha: float = 0.0,
) -> DispatchResult:
    """Solve a Stage B dispatch problem and return a DispatchResult.

    Parameters
    ----------
    net : EnergyNetwork
        Network built from a populated `Grid`.
    econ : Optional[Economics]
        Economics config; defaults to `load_economics`.
    scenario_name : str
        Which scenario to solve. Must exist in `economics.yaml`.
    prefer_solver : {"auto", "pyomo", "fallback"}
        ``auto`` uses Pyomo if installed, else fallback. ``pyomo`` raises
        if Pyomo is missing; ``fallback`` always runs the stdlib path.

    Returns
    -------
    DispatchResult
        Best solution produced by the selected solver.
    """
    if econ is None:
        econ = load_economics()
    if scenario_name not in econ.scenarios:
        raise KeyError(
            f"unknown scenario {scenario_name!r}; "
            f"choose from {sorted(econ.scenarios)}"
        )
    if prefer_solver == "pyomo":
        return solve_dispatch_pyomo(net, econ, scenario_name, alpha=alpha)
    if prefer_solver == "fallback":
        return solve_dispatch_fallback(net, econ, scenario_name, alpha=alpha)
    # auto
    #: Pyomo MILP path now Stage
    # C-complete (12 techs + carbon-alpha objective + sign-bug fix). Auto
    # prefers Pyomo whenever it's installed, falls back to merit-order
    # coord-descent only if the LP fails (e.g. solver not present at
    # runtime).
    if _HAS_PYOMO:
        try:
            return solve_dispatch_pyomo(net, econ, scenario_name, alpha=alpha)
        except Exception as exc:
            # D-1: the fallback is NOT number-compatible
            # with the LP (no B21 parity lines, no green purchase, heuristic
            # sizing), so a silent swallow here could write degraded numbers
            # into a regen for scenarios that carry no byte-exact pin. Keep
            # the auto-fallback for library callers but make it LOUD; the
            # production regen driver (__main__) passes prefer_solver="pyomo"
            # and never reaches this branch.
            import sys as _sys
            print(f"WARNING [solve_dispatch auto]: Pyomo path FAILED for "
                  f"scenario {scenario_name!r} (alpha={alpha}) - falling back "
                  f"to the merit-order heuristic, which is NOT "
                  f"number-compatible with the production LP.\n"
                  f"  cause: {type(exc).__name__}: {exc}",
                  file=_sys.stderr, flush=True)
    return solve_dispatch_fallback(net, econ, scenario_name, alpha=alpha)


# ---------------------------------------------------------------------------
# Pareto-style multi-scenario sweep (Stage B acceptance bullet 4).
# ---------------------------------------------------------------------------
def pareto_sweep(
    net: EnergyNetwork,
    econ: Optional[Economics] = None,
    scenarios: Optional[List[str]] = None,
    prefer_solver: str = "auto",
) -> List[DispatchResult]:
    """Solve the four (Stage B) or six (Stage C) headline scenarios.

    Returns
    -------
    List[DispatchResult]
        One result per scenario; same ordering as the input list.
    """
    if econ is None:
        econ = load_economics()
    if scenarios is None:
        # Stage C extends Stage B by adding biomass + full-stack scenarios
        available = set(econ.scenarios.keys())
        wanted = [
            "bau", "pv_only", "pv_battery", "pv_battery_v2g",
            "pv_battery_v2g_biomass", "full_stack",
        ]
        scenarios = [s for s in wanted if s in available]
    return [
        solve_dispatch(net, econ, name, prefer_solver=prefer_solver)
        for name in scenarios
    ]


def carbon_alpha_sweep(
    net: EnergyNetwork,
    econ: Optional[Economics] = None,
    scenario_name: str = "full_stack",
    alphas: Optional[List[float]] = None,
    prefer_solver: str = "auto",
) -> List[DispatchResult]:
    """Stage C carbon-cost Pareto sweep.

    Runs the same scenario at multiple cost / carbon objective weights.
    Default uses the `full_stack` scenario (all techs enabled). Each
    alpha is solved with a warm-start from the previous alpha's solution,
    which yields a smoother Pareto curve under the heuristic coordinate-
    descent (true LP via Pyomo gives smooth Pareto naturally).

    Returns
    -------
    List[DispatchResult]
        One result per alpha, sorted by alpha. Higher alpha shifts the
        optimum toward lower emissions and (typically) higher cost.
    """
    if econ is None:
        econ = load_economics()
    if alphas is None:
        alphas = econ.carbon_alphas()
    results: List[DispatchResult] = []
    prev_capacities: Optional[Dict[str, float]] = None
    for a in alphas:
        # Warm-start each alpha from the previous alpha's deployed capacities
        # so the coord-descent sees a smooth gradient instead of jumping
        # from zero at every alpha.
        # (Stage C Pyomo parity refactor): Pyomo now handles the
        # alpha-weighted objective directly. Use the standard solve_dispatch
        # path so auto-select picks Pyomo when available.
        r = solve_dispatch(net, econ, scenario_name=scenario_name,
                            prefer_solver=prefer_solver, alpha=a)
        results.append(r)
        prev_capacities = dict(r.capacities)
    return results


def export_pareto_csv(results: List[DispatchResult],
                       out_path: Path) -> None:
    """Write the Pareto sweep to a CSV file ready for plotting (UES style).

    Columns: alpha, annual_cost_inr, annual_emissions_kgco2, lcoe_inr_per_kwh,
    rooftop_pv_kwp, solar_farm_kwp, battery_kwh, v2g_units, biomass_kw_e,
    wte_kw_e, biogas_kw_e, thermal_storage_kwh, tracked_pv_active,
    pv_generation_kwh, grid_import_kwh.
    """
    import csv
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "alpha", "annual_cost_inr", "annual_emissions_kgco2",
        "lcoe_inr_per_kwh",
        "rooftop_pv_kwp", "solar_farm_kwp", "battery_kwh", "v2g_units",
        "biomass_kw_e", "wte_kw_e", "biogas_kw_e",
        "thermal_storage_kwh", "tracked_pv_active",
        "pv_generation_kwh", "grid_import_kwh",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for r in results:
            w.writerow([
                r.alpha,
                f"{r.annual_cost_inr:.0f}",
                f"{r.annual_emissions_kgco2:.0f}",
                f"{r.lcoe_inr_per_kwh():.4f}",
                f"{r.capacities.get('rooftop_pv_kwp', 0):.0f}",
                f"{r.capacities.get('solar_farm_kwp', 0):.0f}",
                f"{r.capacities.get('battery_kwh', 0):.0f}",
                f"{r.capacities.get('v2g_units', 0):.0f}",
                f"{r.capacities.get('biomass_kw_e', 0):.0f}",
                f"{r.capacities.get('wte_kw_e', 0):.0f}",
                f"{r.capacities.get('biogas_kw_e', 0):.0f}",
                f"{r.capacities.get('thermal_storage_kwh', 0):.0f}",
                f"{r.capacities.get('tracked_pv_active', 0):.0f}",
                f"{r.pv_generation_kwh:.0f}",
                f"{r.grid_import_kwh:.0f}",
            ])


def _attach_stage_d_export_fields(result: DispatchResult,
                                  net: EnergyNetwork, econ: Economics) -> None:
    """Stage-D EXPORT — attach the Codex-Batch-2 data
    layer to a SOLVED result, READ-ONLY (does NOT change the LP optimum /
    headline; all post-hoc on the already-solved dispatch).

    Attaches to ``result.__dict__``:
      * ``by_cell["<r>_<c>"]["net_district_flow_kwh"]``         signed annual kWh
        ``by_cell["<r>_<c>"]["net_district_flow_kwh_by_daypart"][dp]``  (12 dayparts)
      * ``stage_d_substation_cell``           ``[row, col]``
      * ``stage_d_per_edge_flow_kwh``         ``{"<a>-<b>": annual_kWh}`` (min-Σ|f| audit)
      * ``stage_d_per_edge_voltage_class``    ``{"<a>-<b>": "backbone_33kv"|"dist_11kv"}``
                                              (SAME edge-key strings as the flow map)
      * ``stage_d_transformer_zones``         ``[{centroid:[x,y],peak_kw,kva,n_built}]``

    Voltage class + transformer zones are computed on an electrical-ENABLED econ
    CLONE (deterministic topology overlay from ``energy/electrical_assets.py``) —
    the production dispatch ``econ`` (electrical_network off) is untouched, so the
    headline stays byte-exact.
    """
    from copy import deepcopy
    from energy.electrical_assets import (
        assign_voltage_classes, transformer_zones,
    )

    # --- per-cell breakdown (read-only) + per-edge audit (min-Σ|f| LP) ---
    by_cell_raw = _stage_d_per_cell_breakdown(net, econ, result, None)
    substation = _stage_d_pick_substation_cell(net)
    cell_to_road = _stage_d_map_cells_to_roads(net)
    # (AUD-25 second cause): the EXPORT audit must run at an
    # effectively-unlimited cable cap. The production default (6 MW Rabbit)
    # makes ~every slice infeasible by design at this scale (the egress
    # arithmetic), so the exported per-edge flows silently zeroed. These
    # flows are the ROUTING picture ("cables carry only what they must") -
    # the realistic-cap feasibility story lives in the stage-D tests, not
    # the viewer export. Mirrors the audit-structural test configuration.
    econ_audit = deepcopy(econ)
    econ_audit.__dict__["stage_d_raw"] = {
        **dict(econ_audit.__dict__.get("stage_d_raw", {}) or {}),
        "cable_thermal_kw_default": 1e9,
    }
    audit = _stage_d_phase2_edge_flow_audit(
        net, econ_audit, by_cell_raw, substation, cell_to_road,
    )

    # compact per-cell net flow: annual + per-daypart (matches the viewer's
    # 12-daypart time slider; the full 864-slice map would bloat the JSON).
    dp_of = {s.id: s.daypart for s in econ.slices}
    by_cell_out: Dict[str, Dict[str, object]] = {}
    for cid, items in by_cell_raw.items():
        if cid == "district_slack":
            continue
        nf = items.get("net_district_flow_kwh", {}) or {}
        if not nf:
            continue
        ann = 0.0
        bydp: Dict[str, float] = {}
        for sid, v in nf.items():
            ann += v
            dp = dp_of.get(sid, "?")
            bydp[dp] = bydp.get(dp, 0.0) + v
        by_cell_out[f"{cid[0]}_{cid[1]}"] = {
            "net_district_flow_kwh": ann,
            "net_district_flow_kwh_by_daypart": bydp,
        }

    # --- per-edge voltage class on the SAME "<a>-<b>" keys as the flow map ---
    econ_e = deepcopy(econ)
    en = dict(econ_e.__dict__.get("electrical_network_raw", {}) or {})
    en["enabled"] = True
    en["backbone_assignment"] = "heuristic"
    econ_e.__dict__["electrical_network_raw"] = en
    try:
        vc = assign_voltage_classes(net, econ_e)  # {(min,max) edge_key: cls}
    except Exception:
        vc = {}

    def _vk(a, b):
        return (a, b) if a <= b else (b, a)

    edge_voltage: Dict[str, str] = {}
    for e in net.edges:
        cls = vc.get(_vk(e.a, e.b), "dist_11kv")
        edge_voltage[f"{e.a}-{e.b}"] = cls

    try:
        zones = transformer_zones(net, econ_e)
        tz = [{"centroid": [float(z["centroid"][0]), float(z["centroid"][1])],
               "peak_kw": float(z["peak_kw"]), "kva": float(z["kva"]),
               "n_built": int(z["n_built"])} for z in zones]
    except Exception:
        tz = []

    result.__dict__["by_cell"] = by_cell_out
    result.__dict__["stage_d_substation_cell"] = [substation[0], substation[1]]
    result.__dict__["stage_d_per_edge_flow_kwh"] = dict(
        audit.get("per_edge_annual_flow_kwh", {}) or {})
    result.__dict__["stage_d_per_edge_voltage_class"] = edge_voltage
    result.__dict__["stage_d_transformer_zones"] = tz


def _scenario_payload_dict(r: DispatchResult, econ: Economics) -> Dict[str, object]:
    """Serialise one DispatchResult to the dispatch_results.json scenario schema.
    Extracted from ``export_dispatch_results_json`` so the Stage-D export driver
    can reuse it. Adds the optional Stage-D / DC-PPA fields when present on the
    result (attached read-only by ``_attach_stage_d_export_fields`` / the solve)."""
    def _dsr(key: str) -> Dict[str, float]:
        return {s.id: float((r.by_slice.get(s.id) or {}).get(key, 0.0))
                for s in econ.slices}
    d: Dict[str, object] = {
        "name": r.scenario,
        "solver": r.solver,
        "alpha": r.alpha,
        "capacities": r.capacities,
        "annual_cost_inr": r.annual_cost_inr,
        "lifetime_cost_inr": r.lifetime_cost_inr,
        "annual_emissions_kgco2": r.annual_emissions_kgco2,
        "annual_demand_kwh": r.annual_demand_kwh,
        "grid_import_kwh": r.grid_import_kwh,
        "grid_export_kwh": r.grid_export_kwh,
        "pv_generation_kwh": r.pv_generation_kwh,
        "battery_throughput_kwh": r.battery_throughput_kwh,
        "v2g_discharge_kwh": r.v2g_discharge_kwh,
        "biomass_generation_kwh": r.biomass_generation_kwh,
        "wte_generation_kwh": r.wte_generation_kwh,
        "biogas_generation_kwh": r.biogas_generation_kwh,
        "thermal_storage_throughput_kwh": r.thermal_storage_throughput_kwh,
        "dsr_shifted_kwh": r.dsr_shifted_kwh,
        # REV-2: managed-EV rescheduled energy (base year).
        "ev_smart_shifted_kwh": getattr(r, "ev_smart_shifted_kwh", 0.0),
        "dsr_reduce_kwh_by_slice": _dsr("dsr_reduce_kwh"),
        "dsr_add_kwh_by_slice": _dsr("dsr_add_kwh"),
        "lcoe_inr_per_kwh": r.lcoe_inr_per_kwh(),
        "renewable_share": r.renewable_share(),
        # FX-7 /+: honest-metrics additions.
        "pv_self_consumption_share": r.pv_self_consumption_share(),
        "metric_notes": {
            "renewable_share": "includes biomass/WTE/biogas (F24 fix); the old "
                               "PV-only metric is pv_self_consumption_share. "
                               "B21 (2026-07-10): counts SELF-GENERATED clean "
                               "energy only - purchased green open-access "
                               "energy (green_purchase_kwh, zero-EF) is NOT "
                               "included, so this UNDERSTATES clean supply "
                               "post-B21 (2055 CO2 -24.9% while the share "
                               "reads flat); quote alongside "
                               "green_purchase_kwh (F36)",
            "lcoe_inr_per_kwh": "NET system cost per kWh served (export + PPA "
                                "revenue already netted) - not a conventional LCOE",
            "capacities": "END-OF-HORIZON (2055) installed; use "
                          "capacities_base_year or period_breakdown for the "
                          "2030 design (F19)",
            "green_purchase": "only the full_stack scenario carries "
                              "allow_green_purchase (the design package); "
                              "bau/pv_* counterfactuals are grid-only by "
                              "construction - cross-scenario tables must not "
                              "read the green option as missing from BAU (B21)",
        },
        "by_slice": r.by_slice,
        "period_breakdown": {
            str(year): info for year, info in r.period_breakdown.items()
        },
    }
    # FX-7 /: base-year installed capacities alongside the end-of-horizon
    # `capacities` (which is what the 2030 headline must NOT be quoted from).
    _pb = r.period_breakdown or {}
    if _pb:
        _first = sorted(_pb.keys())[0]
        _inst = (_pb[_first] or {}).get("installed_capacities")
        if _inst:
            d["capacities_base_year"] = {"year": int(_first), **_inst}
    # B21: + the buy-side green-purchase fields.
    for k in ("dc_ppa_offtake_kwh", "dc_ppa_revenue_inr", "by_cell",
              "stage_d_substation_cell", "stage_d_per_edge_flow_kwh",
              "stage_d_per_edge_voltage_class", "stage_d_transformer_zones",
              "green_purchase_kwh", "green_purchase_cost_inr",
              "green_purchase_mw_by_period",
              # INFRA batch: the sized connection is the number
              # that carries the decentralisation claim (town 129.4 MW vs
              # BAU 203.6 MW), and the viewer brief VIS-CABLE wants it. The
              # internal-network blocks let the parity test and the reports
              # read the infrastructure line instead of re-deriving it.
              "grid_connection_mw", "grid_connection_cost_inr",
              "internal_network_breakdown", "internal_network_embodied",
              "diesel_backup_kwh", "diesel_backup_cost_inr",
              # the PPA shape metrics. temporal_match had
              # been COMPUTED since but never exported, so it
              # read as null everywhere downstream - the coverage and
              # hour-profile fields are new alongside it.
              "dc_ppa_temporal_match_fraction", "dc_ppa_surplus_matched_kwh",
              "dc_ppa_coverage_fraction", "dc_ppa_contract_kwh",
              "dc_ppa_kwh_by_hour", "dc_ppa_hours_supplied",
              "dc_ppa_hours_unsupplied"):
        v = r.__dict__.get(k)
        if v is not None:
            d[k] = v
    return d


def export_dispatch_results_json(
    results: List[DispatchResult],
    econ: Economics,
    out_path: Path,
    network_summary: Optional[Dict[str, float]] = None,
) -> None:
    """Write a `dispatch_results.json` file consumed by the phone-app cockpit.

    Schema matches `_spec/phone_app_spec.md` §3.1.

    Parameters
    ----------
    results : List[DispatchResult]
        Output of `pareto_sweep`.
    econ : Economics
        For slice metadata (tariff bands etc).
    out_path : Path
        Target file. Parents created if missing.
    network_summary : Optional[Dict[str, float]]
        Optional aggregate stats for the cockpit header (peak demand, etc).
    """
    import json
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _dsr_by_slice(result: DispatchResult, key: str) -> Dict[str, float]:
        return {
            s.id: float((result.by_slice.get(s.id) or {}).get(key, 0.0))
            for s in econ.slices
        }

    # (864-slice refactor Phase 3.4, Claude 2): schema version
    # depends on slice count. 144-slice path stays on v1.5 (A18 per-module
    # rooftop_pv kWp); 864-slice path is v2.0 (per-(month, day_type, hour)
    # arrays, new slice ID format e.g. ``jan_wd_18``, new top-level
    # ``slices_per_year`` field). Consumers iterating ``by_slice.keys``
    # continue working; consumers that hardcode the 144 slice IDs need to
    # gate on version >= 2.0.
    schema_version = "2.0" if len(econ.slices) == 864 else "1.5"

    # BOTH fixed-ToU and IEX-Agile per-slice tariff curves (import + export)
    # regardless of which mode the dispatch ran under. The per-slice
    # ``import_tariff_inr_per_kwh`` / ``export_tariff_inr_per_kwh`` in ``slices``
    # still reflect whichever mode was active for THIS solve (preserves existing
    # consumer semantics); the dedicated ``tariff_curve`` block below is purely
    # for the cockpit graph + A/B comparison. Toggles ``set_dynamic_tariff``
    # temporarily and restores the prior mode so the function is side-effect-free
    # for callers that re-use the same Economics instance afterwards.
    _prev_dyn = econ.__dict__.get("_force_dynamic_tariff")
    try:
        econ.set_dynamic_tariff(False)
        fixed_import = {s.id: float(econ.import_tariff(s.id)) for s in econ.slices}
        fixed_export = {s.id: float(econ.export_tariff(s.id)) for s in econ.slices}
        econ.set_dynamic_tariff(True)
        agile_import = {s.id: float(econ.import_tariff(s.id)) for s in econ.slices}
        agile_export = {s.id: float(econ.export_tariff(s.id)) for s in econ.slices}
    finally:
        econ.set_dynamic_tariff(_prev_dyn)
    tariff_curve = {
        "fixed_tou": {
            "import_inr_per_kwh_by_slice": fixed_import,
            "export_inr_per_kwh_by_slice": fixed_export,
        },
        "agile_iex": {
            "import_inr_per_kwh_by_slice": agile_import,
            "export_inr_per_kwh_by_slice": agile_export,
            "note": ("IEX-DAM-pegged retail = wholesale/(1-loss)+network+CSS+duty, "
                     "clamped to [floor, cap]; export pegged to wholesale when "
                     "dynamic_tariff.export_pegged_to_wholesale:true."),
        },
        "active_mode": ("agile_iex" if bool(_prev_dyn)
                        else ("agile_iex" if econ.dynamic_tariff_enabled() else "fixed_tou")),
    }

    payload = {
        "version": schema_version,
        "slices_per_year": len(econ.slices),
        # (Opus 4.8): per-scenario serialisation extracted to
        # ``_scenario_payload_dict`` (reused by the Stage-D export driver). It
        # also serialises the optional Stage-D / DC-PPA fields when present
        # (by_cell, stage_d_per_edge_flow_kwh, stage_d_per_edge_voltage_class,
        # stage_d_transformer_zones, dc_ppa_offtake_kwh, dc_ppa_revenue_inr).
        "scenarios": [_scenario_payload_dict(r, econ) for r in results],
        "slices": [
            {
                "id": s.id,
                "month": s.month,
                "daypart": s.daypart,
                "hours_per_year": s.hours_per_year,
                "tariff_band": s.tariff_band,
                "import_tariff_inr_per_kwh": econ.import_tariff(s.id),
                "export_tariff_inr_per_kwh": econ.export_tariff(),
                "weekday_share": s.weekday_share,
                "weekend_share": s.weekend_share,
                "festival_share": s.festival_share,
            }
            for s in econ.slices
        ],
        "network_summary": network_summary or {},
        "economics_meta": {
            "currency": econ.currency,
            "base_year": econ.base_year,
            "emission_factor_kgco2_per_kwh": econ.emission_factor(),
            "import_tariff_bands": econ.grid.get("import_tariff_inr_per_kwh", {}),
            "dynamic_tariff_enabled_default": bool(
                (econ.dynamic_tariff_raw or {}).get("enabled_default", False)
            ),
        },
        # (Claude 2): per-slice tariff curves (fixed-ToU + IEX-Agile)
        # for the cockpit's Octopus-Agile daily-tariff graph + tariff-mode A/B.
        "tariff_curve": tariff_curve,
        # model-owned EV/V2G params so the viewer can drop its hardcoded
        # defaults (0.18 adoption / 0.35 v2g-capable / 5 hh-per-unit). The model
        # is now per-INCOME (not a flat adoption): EV-car ownership + V2G
        # willingness differ by tier, and EV-car share RAMPS per multi-period
        # year. V2G discharge shape is LP-decided (read per-slice v2g_discharge_kwh
        # in by_slice), not a fixed profile, so only the charging shape is given.
        "ev_v2g_params": {
            "model": "per_income_2030_stock_with_period_ramp",
            "by_income": (econ.ev_vehicle_ownership or {}).get("by_income", {}),
            "v2g_willingness_by_income": (econ.ev_vehicle_ownership or {})
                .get("v2g_willingness_by_income", {}),
            "ev_car_share_by_period": (econ.ev_vehicle_ownership or {})
                .get("ev_car_share_by_period", {}),
            "battery_kwh": (econ.ev_vehicle_ownership or {}).get("battery_kwh", {}),
            "ev_car_kwh_per_day": (econ.ev_vehicle_ownership or {})
                .get("ev_car_kwh_per_day"),
            "e2w_kwh_per_day": (econ.ev_vehicle_ownership or {})
                .get("e2w_kwh_per_day"),
            "residential_charging_daypart_shape": econ.ev_adoption.get(
                "ev_charging_daypart_shape_residential", {}),
            "note": ("V2G units = sum over residential cells of households x "
                     "ev_car_share(income, year) x v2g_willingness(income); "
                     "V2G discharge profile is LP-optimised per slice (see "
                     "by_slice.v2g_discharge_kwh), not a fixed shape."),
        },
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


if __name__ == "__main__":
    from .network import load_optimised_network
    n = load_optimised_network()
    e = load_economics()
    print(f"network ready: {n.layout_name}, "
          f"{n.annual_demand_kwh(e)/1e6:,.1f} GWh/yr demand")
    print(f"  Pyomo available: {has_pyomo()}; "
          f"production solver = Pyomo+HiGHS MILP for the full Stage C model"
          if has_pyomo() else
          f"  Pyomo available: False; using fallback (merit-order coord-descent)")
    print()
    # D-1: the production regen must FAIL LOUD if the LP
    # path breaks mid-run - never silently degrade to the heuristic (whose
    # numbers are not LP-comparable) for scenarios without byte-exact pins.
    results = pareto_sweep(n, e, prefer_solver="pyomo")
    print(f"{'scenario':<18} {'solver':<28} {'cost (INR/yr)':>18} "
          f"{'tCO2/yr':>10} {'rooftop kWp':>12} {'farm kWp':>10} "
          f"{'batt kWh':>10} {'v2g':>6} {'INR/kWh':>9}")
    for r in results:
        print(f"{r.scenario:<18} {r.solver:<28} "
              f"{r.annual_cost_inr:>18,.0f} "
              f"{r.annual_emissions_kgco2/1000:>10,.0f} "
              f"{r.capacities['rooftop_pv_kwp']:>12,.0f} "
              f"{r.capacities['solar_farm_kwp']:>10,.0f} "
              f"{r.capacities['battery_kwh']:>10,.0f} "
              f"{r.capacities['v2g_units']:>6,.0f} "
              f"{r.lcoe_inr_per_kwh():>9,.2f}")

    print("\n=== Stage C carbon-cost Pareto sweep (alpha = 0 -> 1, full_stack) ===")
    alpha_results = carbon_alpha_sweep(n, e, scenario_name="full_stack",
                                       prefer_solver="pyomo")
    print(f"{'alpha':>6} {'cost (INR/yr)':>16} {'tCO2/yr':>10} "
          f"{'rooftop':>9} {'farm':>8} {'tracked':>8} {'biomass':>9} {'INR/kWh':>9}")
    for r in alpha_results:
        print(f"{r.alpha:>6.2f} "
              f"{r.annual_cost_inr:>16,.0f} "
              f"{r.annual_emissions_kgco2/1000:>10,.0f} "
              f"{r.capacities.get('rooftop_pv_kwp', 0):>9,.0f} "
              f"{r.capacities.get('solar_farm_kwp', 0):>8,.0f} "
              f"{r.capacities.get('tracked_pv_active', 0):>8.0f} "
              f"{r.capacities.get('biomass_kw_e', 0):>9,.0f} "
              f"{r.lcoe_inr_per_kwh():>9,.2f}")

    # Pareto CSV for plotting (UES Fig 3.1 style)
    csv_path = Path(__file__).parent.parent / "outputs" / "data" / "energy" / "carbon_pareto.csv"
    export_pareto_csv(alpha_results, csv_path)
    print(f"wrote {csv_path}")

    out_path = Path(__file__).parent.parent / "outputs" / "data" / "energy" / "dispatch_results.json"
    network_summary = {
        "layout_name": n.layout_name,
        "n_nodes": len(n.nodes),
        "n_built_nodes": len(n.built_nodes()),
        "n_residential_nodes": len(n.residential_nodes()),
        "total_households": n.total_households(),
        "total_peak_demand_kw": n.total_peak_demand_kw(),
        "annual_demand_kwh": n.annual_demand_kwh(e),
        "rooftop_pv_ceiling_kwp": n.total_rooftop_pv_cap_kwp(),
        "solar_farm_ceiling_kwp": n.total_solar_farm_cap_kwp(),
    }
    # (Claude 2): Agile-tariff A/B. Solve full_stack alpha=0 once
    # more under IEX-Agile dynamic tariff so the JSON carries both the
    # production fixed-ToU result AND the Agile counter-factual. ``load_economics``
    # caches a singleton, so we ``force_reload`` to get an INDEPENDENT instance
    # — otherwise ``set_dynamic_tariff(True)`` on e_agile would also flip ``e``
    # and pollute the subsequent export's ``active_mode`` label.
    print("\n=== Agile-tariff A/B (full_stack, alpha=0, IEX-Agile) ===")
    e_agile = load_economics(force_reload=True)
    e_agile.set_dynamic_tariff(True)
    agile_full = solve_dispatch(n, e_agile, "full_stack",
                                prefer_solver="pyomo", alpha=0.0)
    agile_full.scenario = "full_stack_agile"
    print(f"  fixed-ToU  full_stack: {results[-1].annual_cost_inr/1e6:>10,.1f} M / "
          f"{results[-1].annual_emissions_kgco2/1000:>7,.0f} t / "
          f"{results[-1].lifetime_cost_inr/1e9:>6,.2f} B / "
          f"LCOE {results[-1].lcoe_inr_per_kwh():.3f}")
    print(f"  agile_iex  full_stack: {agile_full.annual_cost_inr/1e6:>10,.1f} M / "
          f"{agile_full.annual_emissions_kgco2/1000:>7,.0f} t / "
          f"{agile_full.lifetime_cost_inr/1e9:>6,.2f} B / "
          f"LCOE {agile_full.lcoe_inr_per_kwh():.3f}")
    d_cost = (agile_full.annual_cost_inr - results[-1].annual_cost_inr) / results[-1].annual_cost_inr * 100
    d_life = (agile_full.lifetime_cost_inr - results[-1].lifetime_cost_inr) / results[-1].lifetime_cost_inr * 100
    print(f"  delta Agile vs fixed:  {d_cost:+.1f}% cost / {d_life:+.1f}% lifetime "
          f"(positive = Agile worse = solar cannibalisation expected)")

    # (N21): data-centre PPA A/B as SCENARIOS. Production baseline
    # stays byte-exact (ppa.enabled stays false in YAML); these are extra
    # scenarios in the JSON so the cockpit / Pareto can compare them. Two
    # variants: standard HT open-access (net ~2.53/kWh — only absorbs surplus
    # the 60 MW feeder can't export) and the Punjab RE intra-state concession
    # (net ~4.79/kWh — beats feed-in, absorbs all surplus). Independent econ
    # instances (force_reload) so the toggle doesn't pollute the cached `e`.
    print("\n=== Data-centre PPA A/B (full_stack, alpha=0) ===")
    e_ppa = load_economics(force_reload=True)
    e_ppa.set_ppa_enabled(True)  # default active counterparty = data_centre_offsite (standard)
    ppa_std = solve_dispatch(n, e_ppa, "full_stack",
                             prefer_solver="pyomo", alpha=0.0)
    ppa_std.scenario = "full_stack_dc_ppa"
    e_ppa_g = load_economics(force_reload=True)
    e_ppa_g.set_ppa_enabled(True)
    _cps = e_ppa_g.__dict__["ppa_raw"]["counterparties"]
    _cps["data_centre_offsite"]["enabled"] = False
    _cps["data_centre_offsite_re_concession"]["enabled"] = True
    ppa_green = solve_dispatch(n, e_ppa_g, "full_stack",
                               prefer_solver="pyomo", alpha=0.0)
    ppa_green.scenario = "full_stack_dc_ppa_green"
    for lbl, r in (("standard  ~2.53/kWh", ppa_std), ("RE-concess ~4.79/kWh", ppa_green)):
        dc = (r.annual_cost_inr - results[-1].annual_cost_inr) / results[-1].annual_cost_inr * 100
        de = (r.annual_emissions_kgco2 - results[-1].annual_emissions_kgco2) / results[-1].annual_emissions_kgco2 * 100
        print(f"  DC PPA {lbl}: {r.annual_cost_inr/1e6:>9,.1f} M ({dc:+.1f}% cost) / "
              f"{r.annual_emissions_kgco2/1000:>7,.0f} t ({de:+.1f}% emis)")

    # (per-cell net flow + per-edge flow + voltage class + transformers) to the
    # PRODUCTION full_stack result (results[-1], alpha=0). Read-only post-hoc —
    # does NOT change the LP optimum / headline. DC-PPA offtake/revenue are
    # already on ppa_std / ppa_green from the solve.
    try:
        _attach_stage_d_export_fields(results[-1], n, e)
        print(f"  Stage-D export fields attached to {results[-1].scenario} "
              f"a={results[-1].alpha} (by_cell + per-edge flow + voltage class "
              f"+ transformers)")
    except Exception as _exc:  # noqa: BLE001
        print(f"  WARNING: Stage-D export-field attach failed: {_exc}")

    # Combine scenario results + alpha sweep + Agile A/B + PPA A/B into one JSON
    export_dispatch_results_json(
        results + alpha_results + [agile_full, ppa_std, ppa_green],
        e, out_path, network_summary)
    print(f"\nwrote {out_path}")
