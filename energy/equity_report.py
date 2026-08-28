"""Phase 4 — EQUITY + P2P TRADING REPORT (report-only).

WHAT THIS IS
------------
A post-hoc *transfer / settlement* layer that turns the solved single-bus
dispatch into the per-owner / per-tier EQUITY + TRADING story the thesis needs:
**who saves, who trades, and what the EWS resident's bill is.** It consumes the
Phase-1 per-cell breakdown (``_stage_d_per_cell_breakdown``) plus the cited
retail-tariff config (``economics.yaml: equity_report``) and computes bills,
P2P trades and subsidy attribution. It NEVER changes the optimiser.

WHY IT IS BYTE-EXACT-SAFE (the core idea)
-----------------------------------------
A retail tariff or a P2P trade *price* is a **transfer** between two actors, not
a system resource cost. In the social-planner cost-minimisation LP the buyer's
payment and the seller's receipt cancel to zero, so re-pricing the internal
flows cannot change the optimum or the headline. And physically, the single bus
already lets any cell's surplus PV serve any cell's deficit for free, optimally
-- so the cell-to-cell *volume* is read straight off the existing optimum; only
the money is new. This module therefore:
  * does NOT add variables to ``solve_dispatch_pyomo`` (production stays
    byte-exact: 1,402,369,939.69 / 82,573,979 / 57,199,879,508), and
  * is the concrete realisation of FINDINGS ("equity shows in per-owner
    reporting, not the aggregate").

BACKLOG ITEMS BUNDLED (per _spec/QUESTIONS_AND_FIXES_REGISTER.md)
----------------------------------------------------------------
  P2P        peer-to-peer building-to-building rooftop trading settlement
         per-cell / per-tier retail tariff split (res / com / ind)
  D-ews      EWS minimal social tariff (~Rs 3/kWh) + social_ews financing tie-in
  3C         industrial cross-subsidy flow (Rs 1.05/kWh -> residential)
/15/16  PMSGY per-tier subsidy attribution (report-only)
  N9         home/work V2G attribution (documented)
  N10        demand diversity / coincidence factor (documented; implicit in LP)
 (PV module-mix as an LP Var) is DEFERRED to Stage F -- it is a genuine
*system-cost* change (not a transfer), and the calibrated mono-dominant mix is
more realistic than a pure cost-min mix.

P2P market design (defensible, deliberately simple)
---------------------------------------------------
Two complementary equity mechanisms, kept clean:
  1. EWS poorest tier is protected by the Rs 3 SOCIAL tariff (< the Rs 4.5 P2P
     price), so EWS are NOT P2P buyers -- their equity is the social-tariff
     transfer (the gov landlord absorbs the gap).
  2. Every NON-EWS building (mid/high residential, commercial, public,
     industrial) is a P2P prosumer: per slice, rooftop SURPLUS cells sell to
     DEFICIT cells. A trade clears only when it is mutually beneficial,
     ``export_tariff < p2p_price < import_tariff(slice)``, which concentrates
     trading in the midday shoulder (rooftop surplus + favourable spread).
Matched P2P volume per slice = min(Sigma surplus, Sigma deficit), allocated to
sellers / buyers in proportion to their surplus / deficit. The utility-scale
solar farm + carports + biomass/WTE/biogas serve the residual district load --
they are central supply, not peers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Consumer-class taxonomy                                                      #
# --------------------------------------------------------------------------- #
# Residential tiers come from econ.income_for_category; industrial categories
# carry the cross-subsidy; everything else is commercial/public.
_TIER_LABEL = {"low": "ews", "mid": "mid_residential", "high": "high_residential"}
_RESIDENTIAL_CLASSES = ("ews", "mid_residential", "high_residential")


def _consumer_class(econ, node) -> Optional[str]:
    """Map an EnergyNode to its billing consumer-class, or None if it is not a
    demand-carrying building (solar farm / parking / blue-space / road)."""
    cat = getattr(node, "category_name", None)
    if not cat:
        return None
    inc = econ.income_for_category(cat)
    if inc in _TIER_LABEL:
        return _TIER_LABEL[inc]
    industrial = set((econ.grid or {}).get("industrial_categories", []) or [])
    if cat in industrial:
        return "industrial"
    return "commercial_public"


def _new_class_acc() -> Dict[str, float]:
    return {
        "consumption_kwh": 0.0,
        "rooftop_gen_kwh": 0.0,
        "v2g_gen_kwh": 0.0,
        "self_consumed_kwh": 0.0,
        "grid_import_kwh": 0.0,        # residual deficit drawn from district/grid
        "grid_export_kwh": 0.0,        # residual surplus fed to district/grid
        "p2p_bought_kwh": 0.0,
        "p2p_sold_kwh": 0.0,
        # money (INR/yr)
        "grid_import_cost": 0.0,
        "grid_export_revenue": 0.0,
        "p2p_buy_cost": 0.0,
        "p2p_sell_revenue": 0.0,
        "p2p_buyer_saving": 0.0,       # vs buying that energy from the grid
        "p2p_seller_gain": 0.0,        # vs exporting that energy to the grid
        "bau_cross_subsidy": 0.0,      # 3C surcharge on ALL consumption (BAU view)
        "district_cross_subsidy": 0.0, # 3C surcharge on grid-supplied units (district)
        "social_tariff_bill": 0.0,     # EWS: consumption x Rs 3
        "gov_grid_cost": 0.0,          # EWS: gov landlord's net grid cost to serve
        "bau_cost": 0.0,               # all consumption at standard ToU retail, no rooftop/P2P
        "n_cells": 0.0,
        "households": 0.0,
        "rooftop_households": 0.0,     # households in cells that carry rooftop PV
        "rooftop_installed_kwp": 0.0,  # share of installed rooftop on this class's cells
        # solar water heating. Attributed by each class's share
        # of DISTRICT WATER-HEATING DEMAND, not of roof area, because the
        # collector is sized by the hot water drawn beneath it. Zero on
        # every run where the technology is off, which is production.
        "solar_thermal_m2": 0.0,
        "solar_thermal_served_kwh": 0.0,
        "solar_thermal_dhw_kwh": 0.0,   # the water-heating load itself
    }


def _rooftop_capex_per_kwp(econ) -> float:
    techs = getattr(econ, "technologies", {}) or {}
    rt = techs.get("rooftop_pv", {}) or {}
    return float(rt.get("capex_inr_per_kwp", 35000.0))


# --------------------------------------------------------------------------- #
# Main builder                                                                 #
# --------------------------------------------------------------------------- #
def build_equity_report(net, econ, result, scenario=None) -> Dict[str, object]:
    """Compute the equity + P2P trading report for a solved dispatch.

    Parameters
    ----------
    net : EnergyNetwork
    econ : Economics
    result : DispatchResult
        A solved single-bus dispatch (multi-period production fills ``by_slice``
        from the 2030 base-year snapshot, which is what we attribute).
    scenario : optional
        Passed through to the per-cell breakdown for scenario-aware shares.

    Returns
    -------
    dict
        A JSON-serialisable report (see ``write_equity_report_json``).
    """
    # Lazy import to avoid an import-time cycle (dispatch may import us when the
    # report is wired into the export path).
    from energy.dispatch import _stage_d_per_cell_breakdown

    cfg = econ.equity_report_config()
    ews_tariff = float(cfg.get("ews_social_tariff_inr_per_kwh", 3.0))
    first_slab = float(cfg.get("pspcl_domestic_first_slab_inr_per_kwh", 5.40))
    comm_premium = float(cfg.get("commercial_tariff_premium_inr_per_kwh", 0.0))
    exclude_ews = bool(cfg.get("p2p_exclude_ews", True))
    p2p_price = float(econ.stage_d_p2p_tariff_inr_per_kwh())
    cross_sub = float(econ.industrial_cross_subsidy_inr_per_kwh())

    # ----- per-cell breakdown (READ-ONLY attribution of the LP optimum) -----
    by_cell = _stage_d_per_cell_breakdown(net, econ, result, scenario)

    node_by_cell = {n.cell_id: n for n in net.nodes}
    slices = list(econ.slices)

    # Pre-classify cells + cache per-slice arrays we will reuse.
    # cell -> (class, is_p2p_participant)
    cell_class: Dict[Tuple[int, int], str] = {}
    for cid, items in by_cell.items():
        if cid == "district_slack":
            continue
        node = node_by_cell.get(cid)
        if node is None:
            continue
        klass = _consumer_class(econ, node)
        if klass is None:
            continue
        # only demand-carrying cells participate in billing
        if sum((items.get("demand_kwh", {}) or {}).values()) <= 0.0:
            continue
        cell_class[cid] = klass

    acc: Dict[str, Dict[str, float]] = {}

    def cls(k: str) -> Dict[str, float]:
        return acc.setdefault(k, _new_class_acc())

    # Per-cell static attributes (households, rooftop kWp, n_cells).
    total_rooftop_cap = 0.0
    for cid, klass in cell_class.items():
        node = node_by_cell[cid]
        c = cls(klass)
        c["n_cells"] += 1.0
        hh = float(getattr(node, "households", 0) or 0)
        c["households"] += hh
        rk = float(getattr(node, "rooftop_pv_cap_kwp", 0.0) or 0.0)
        if rk > 0:
            c["rooftop_households"] += hh
        total_rooftop_cap += rk
    # installed rooftop attributed to each class in proportion to its rooftop cap.
    # AUD-2 /: use the 2030 period build, not the end-of-horizon
    # result.capacities (2055) - this report is a 2030 snapshot, and the old
    # source overstated the PMSGY capex attribution by the late-period ceiling
    # growth (~15%). Falls back to result.capacities for single-period runs
    # (where the two coincide). Pin-safe: the equity pins cover cost/emissions,
    # and the pmsgy test asserts ordering, which a uniform scale preserves.
    _pb30 = (result.period_breakdown or {}).get(2030) or {}
    _caps30 = _pb30.get("installed_capacities") or {}
    installed_rooftop = float(_caps30.get("rooftop_pv_kwp", 0.0)
                              or (result.capacities or {}).get("rooftop_pv_kwp", 0.0))
    if total_rooftop_cap > 0:
        for cid, klass in cell_class.items():
            rk = float(getattr(node_by_cell[cid], "rooftop_pv_cap_kwp", 0.0) or 0.0)
            cls(klass)["rooftop_installed_kwp"] += installed_rooftop * rk / total_rooftop_cap

    # ----- solar water heating, attributed by water-heating demand -------
    # WITHOUT THIS BLOCK THE TECHNOLOGY WOULD BE BUILT BY THE LP AND BE
    # INVISIBLE HERE, and this report is where the distributional results
    # come from. A technology that lowers bills unevenly and is absent from
    # the equity statement is worse than one that was never modelled.
    _st_m2 = float(_caps30.get("solar_thermal_m2", 0.0)
                   or (result.capacities or {}).get("solar_thermal_m2", 0.0))
    _st_served = float((result.capacities or {})
                       .get("solar_thermal_served_kwh", 0.0))
    if _st_m2 > 0.0 or _st_served > 0.0:
        _hl = getattr(econ, "heating_loads", {}) or {}
        _shares = _hl.get("dhw_share_of_peak_by_category", {}) or {}
        _dhw_by_class: Dict[str, float] = {}
        for cid, klass in cell_class.items():
            n = node_by_cell[cid]
            cat = getattr(n, "category_name", None)
            pk = float(getattr(n, "peak_heating_kw", 0.0) or 0.0)
            if not cat or pk <= 0:
                continue
            # annual water-heating energy for this cell, via the DHW leg
            e = sum(pk * econ.dhw_only_split_factor(cat, s.id)
                    * s.hours_per_year for s in slices)
            if e > 0:
                _dhw_by_class[klass] = _dhw_by_class.get(klass, 0.0) + e
                cls(klass)["solar_thermal_dhw_kwh"] += e
        _dhw_total = sum(_dhw_by_class.values())
        if _dhw_total > 0:
            for klass, e in _dhw_by_class.items():
                share = e / _dhw_total
                cls(klass)["solar_thermal_m2"] += _st_m2 * share
                cls(klass)["solar_thermal_served_kwh"] += _st_served * share

    # ----- per-slice settlement -----
    p2p_volume_kwh = 0.0
    p2p_buyer_saving = 0.0
    p2p_seller_gain = 0.0
    p2p_volume_by_band: Dict[str, float] = {}

    for s in slices:
        sid = s.id
        import_p = float(econ.import_tariff(sid))
        export_p = float(econ.export_tariff(sid))
        clears = export_p < p2p_price < import_p

        # gather participant surplus / deficit at this slice
        surplus: Dict[Tuple[int, int], float] = {}
        deficit: Dict[Tuple[int, int], float] = {}
        S = 0.0
        D = 0.0
        for cid, klass in cell_class.items():
            items = by_cell[cid]
            d = float((items.get("demand_kwh", {}) or {}).get(sid, 0.0))
            pv = float((items.get("pv_kwh", {}) or {}).get(sid, 0.0))
            v2g = float((items.get("v2g_discharge_kwh", {}) or {}).get(sid, 0.0))
            net_c = d - pv - v2g
            local_self = min(d, pv + v2g)
            retail_bau = import_p + (comm_premium if klass == "commercial_public" else 0.0)
            c = cls(klass)
            c["consumption_kwh"] += d
            c["rooftop_gen_kwh"] += pv
            c["v2g_gen_kwh"] += v2g
            c["self_consumed_kwh"] += local_self
            c["bau_cost"] += d * retail_bau
            if klass == "industrial":
                # BAU buys every unit from the grid, so the surcharge is on all of d
                c["bau_cross_subsidy"] += d * cross_sub

            is_participant = not (exclude_ews and klass == "ews")
            if not is_participant:
                # EWS: served at the social tariff; gov landlord bears grid cost
                imp = max(0.0, net_c)
                exp = max(0.0, -net_c)
                c["grid_import_kwh"] += imp
                c["grid_export_kwh"] += exp
                c["social_tariff_bill"] += d * ews_tariff
                c["gov_grid_cost"] += imp * import_p - exp * export_p
                continue

            if net_c > 0:
                deficit[cid] = net_c
                D += net_c
            elif net_c < 0:
                surplus[cid] = -net_c
                S += -net_c

        matched = min(S, D) if clears else 0.0
        if matched > 0:
            p2p_volume_kwh += matched
            p2p_buyer_saving += matched * (import_p - p2p_price)
            p2p_seller_gain += matched * (p2p_price - export_p)
            band = getattr(s, "tariff_band", "?")
            p2p_volume_by_band[band] = p2p_volume_by_band.get(band, 0.0) + matched

        # allocate this slice's flows (P2P + residual grid) into class accumulators
        for cid, klass in cell_class.items():
            if exclude_ews and klass == "ews":
                continue
            c = cls(klass)
            sur = surplus.get(cid, 0.0)
            dfc = deficit.get(cid, 0.0)
            sold = (matched * sur / S) if (matched > 0 and S > 0 and sur > 0) else 0.0
            bought = (matched * dfc / D) if (matched > 0 and D > 0 and dfc > 0) else 0.0
            grid_imp = dfc - bought
            grid_exp = sur - sold
            c["p2p_sold_kwh"] += sold
            c["p2p_bought_kwh"] += bought
            c["grid_import_kwh"] += grid_imp
            c["grid_export_kwh"] += grid_exp
            retail = import_p + (comm_premium if klass == "commercial_public" else 0.0)
            c["grid_import_cost"] += grid_imp * retail
            c["grid_export_revenue"] += grid_exp * export_p
            c["p2p_buy_cost"] += bought * p2p_price
            c["p2p_sell_revenue"] += sold * p2p_price
            c["p2p_buyer_saving"] += bought * (import_p - p2p_price)
            c["p2p_seller_gain"] += sold * (p2p_price - export_p)
            if klass == "industrial":
                # in the district, self-consumed rooftop units do NOT carry the
                # cross-subsidy surcharge (only grid-supplied units do) -> going
                # solar lowers the cross-subsidy the industrial actually pays
                c["district_cross_subsidy"] += grid_imp * cross_sub

    # ----- derive per-class bills + savings -----
    by_class: Dict[str, Dict[str, float]] = {}
    for klass, c in acc.items():
        if klass == "ews":
            district_bill = c["social_tariff_bill"]
            # gov subsidy on the ENERGY bill (rooftop CAPEX accounted separately
            # via social_ews 6% financing + PMSGY attribution below)
            gov_energy_subsidy = c["gov_grid_cost"] - c["social_tariff_bill"]
        else:
            district_bill = (
                c["grid_import_cost"] + c["p2p_buy_cost"]
                - c["grid_export_revenue"] - c["p2p_sell_revenue"]
                + c["district_cross_subsidy"]
            )
            gov_energy_subsidy = 0.0
        bau = c["bau_cost"] + c["bau_cross_subsidy"]  # bau_cross_subsidy is 0 for non-industrial
        savings = bau - district_bill
        by_class[klass] = {
            **c,
            "district_bill_inr": district_bill,
            "bau_bill_inr": bau,
            "savings_vs_bau_inr": savings,
            "savings_pct": (100.0 * savings / bau) if bau > 0 else 0.0,
            "effective_tariff_inr_per_kwh": (
                district_bill / c["consumption_kwh"] if c["consumption_kwh"] > 0 else 0.0
            ),
            "gov_energy_subsidy_inr": gov_energy_subsidy,
        }

    # ----- EWS equity headline (the resident-facing transfer) -----
    ews = by_class.get("ews", {})
    ews_consumption = ews.get("consumption_kwh", 0.0)
    ews_equity = {
        "social_tariff_inr_per_kwh": ews_tariff,
        "pspcl_first_slab_comparator_inr_per_kwh": first_slab,
        "annual_consumption_kwh": ews_consumption,
        "annual_bill_at_social_tariff_inr": ews_consumption * ews_tariff,
        "annual_bill_at_first_slab_inr": ews_consumption * first_slab,
        "annual_discount_vs_first_slab_inr": ews_consumption * (first_slab - ews_tariff),
        "discount_vs_first_slab_pct": (
            100.0 * (first_slab - ews_tariff) / first_slab if first_slab > 0 else 0.0
        ),
        "annual_discount_vs_tou_inr": ews.get("savings_vs_bau_inr", 0.0),
        "gov_energy_subsidy_absorbed_inr": ews.get("gov_energy_subsidy_inr", 0.0),
        "note": (
            "EWS building+roof+PV are GOVERNMENT-owned (council/ARHC/RESCO model, "
            "financed at discount_rates.social_ews=6%); tenants pay the flat Rs "
            f"{ews_tariff}/kWh social tariff on all consumption. Discount = the "
            "resident-facing equity transfer (gov absorbs the gap)."
        ),
    }

    # ----- PMSGY per-tier subsidy attribution// report-only) -----
    pmsgy_tier = dict((cfg.get("pmsgy_effective_subsidy_by_tier", {}) or {}))
    capex_kwp = _rooftop_capex_per_kwp(econ)
    free_kwh_yr = 12.0 * float(cfg.get("pmsgy_free_kwh_per_month", 300))
    rwa_common_rate = float(cfg.get("pmsgy_rwa_common_area_inr_per_kw", 18000))
    pmsgy_attr: Dict[str, Dict[str, float]] = {}
    for tier_key, klass in (("low", "ews"), ("mid", "mid_residential"), ("high", "high_residential")):
        c = by_class.get(klass)
        if not c:
            continue
        frac = float(pmsgy_tier.get(tier_key, 0.0))
        installed = c.get("rooftop_installed_kwp", 0.0)
        capex_subsidy = installed * capex_kwp * frac
        #: 300 kWh/month free for SELF-INSTALLING (owner-occupier) PV
        # households. Gov-owned EWS tenants did NOT self-install -- the gov owns
        # the PV + receives the CAPEX subsidy, and the tenant's benefit is
        # the Rs 3 social tariff -- so does not apply to EWS (counting it
        # there would double-count with the social-tariff transfer).
        if klass == "ews":
            free_energy = 0.0
            free_value = 0.0
        else:
            rooftop_hh = c.get("rooftop_households", 0.0)
            free_energy = min(free_kwh_yr * rooftop_hh, c.get("consumption_kwh", 0.0))
            eff_tariff = c.get("effective_tariff_inr_per_kwh", 0.0)
            free_value = free_energy * max(eff_tariff, 0.0)
        pmsgy_attr[klass] = {
            "effective_capex_subsidy_fraction": frac,
            "rooftop_installed_kwp": installed,
            "capex_subsidy_inr": capex_subsidy,           #: who got the CAPEX rupees
            "f15_free_kwh_per_year": free_energy,
            "f15_free_value_inr": free_value,
        }
    #: RWA / group-housing common-area subsidy applies to the mid (rwa) tier
    # apartment common-area systems (Rs 18k/kW). Reported as the rate + an
    # illustrative attribution on the mid-tier installed rooftop (common-area
    # share not separately modelled at this grid resolution).
    pmsgy_f14 = {
        "rwa_common_area_inr_per_kw": rwa_common_rate,
        "applies_to": "mid_residential (rwa-pooled apartment common areas)",
        "note": "Production LP uses the blended 0.30 PMSGY; this per-tier "
                "attribution is report-only (does not move the headline).",
    }

    # ----- N9: home/work V2G attribution -----
    v2g_total = sum(c.get("v2g_gen_kwh", 0.0) for c in acc.values())
    n9 = {
        "v2g_discharge_kwh_total": v2g_total,
        "by_residential_tier": {
            k: acc.get(k, {}).get("v2g_gen_kwh", 0.0) for k in _RESIDENTIAL_CLASSES
        },
        "placement": "home-dominant (V2G attributed to residential cells via "
                     "per-income EV ownership x willingness). Workplace daytime "
                     "V2G at office/industrial cells is a documented Stage-E/F "
                     "extension (N9 split home/work/fleet).",
    }

    # ----- N10: demand diversity / coincidence -----
    sum_cell_peaks = sum(
        float(getattr(node_by_cell[cid], "peak_demand_kw", 0.0) or 0.0)
        for cid in cell_class
    )
    # district per-slice peak (kW-equivalent) from the aggregate by_slice demand
    bs = result.by_slice or {}
    # demand_kwh per slice is energy over the slice's hours; convert to avg kW
    slice_hours = {s.id: float(getattr(s, "hours_per_year", 0) or 0) for s in slices}
    district_peak_kw = 0.0
    for sid, row in bs.items():
        d_kwh = float((row or {}).get("demand_kwh", 0.0))
        h = slice_hours.get(sid, 0.0)
        # by_slice demand is annual kWh for that representative slice; per-hour
        # average load = annual kWh / hours_per_year (representative-day proxy).
        # NOTE: this is an average-load coincidence proxy, not an instantaneous
        # peak; the per-slice LP is coincident by construction (N10 implicit).
        if h > 0:
            district_peak_kw = max(district_peak_kw, d_kwh / h)
    n10 = {
        "sum_of_cell_peaks_kw": sum_cell_peaks,
        "district_coincident_peak_kw_proxy": district_peak_kw,
        "coincidence_factor_proxy": (
            district_peak_kw / sum_cell_peaks if sum_cell_peaks > 0 else 0.0
        ),
        "note": "The per-slice LP makes inter-cell flows coincident by "
                "construction, so no explicit diversity factor is applied "
                "(N10 implicit). This proxy is report-only.",
    }

    # ----- district totals + reconciliation -----
    total_consumption = sum(c.get("consumption_kwh", 0.0) for c in acc.values())
    total_savings = sum(v.get("savings_vs_bau_inr", 0.0) for v in by_class.values())
    total_bau = sum(v.get("bau_bill_inr", 0.0) for v in by_class.values())
    total_district_bill = sum(v.get("district_bill_inr", 0.0) for v in by_class.values())
    # 3C: the industrial cross-subsidy flow that funds the residential/EWS
    # discount (paid on grid-supplied industrial units in the district).
    total_cross_subsidy_3c = sum(
        v.get("district_cross_subsidy", 0.0) for v in by_class.values()
    )
    ind = by_class.get("industrial", {})
    slack = by_cell.get("district_slack", {}) or {}
    district_grid_import = sum((slack.get("grid_import_kwh", {}) or {}).values())
    district_grid_export = sum((slack.get("grid_export_kwh", {}) or {}).values())
    # 2030 base-year aggregate demand for reconciliation
    agg_demand = sum(float((row or {}).get("demand_kwh", 0.0)) for row in bs.values())

    p2p = {
        "p2p_price_inr_per_kwh": p2p_price,
        "annual_volume_kwh": p2p_volume_kwh,
        "volume_pct_of_demand": (100.0 * p2p_volume_kwh / total_consumption
                                 if total_consumption > 0 else 0.0),
        "annual_buyer_saving_inr": p2p_buyer_saving,
        "annual_seller_gain_inr": p2p_seller_gain,
        "annual_welfare_redistributed_inr": p2p_buyer_saving + p2p_seller_gain,
        "volume_by_tariff_band_kwh": p2p_volume_by_band,
        "participants": ("non-EWS buildings (mid/high residential, commercial, "
                         "public, industrial)") if exclude_ews else "all buildings",
        "clearing_rule": "trade only when export_tariff < p2p_price < import_tariff(slice)",
        "note": "P2P is behind-the-meter BUILDING-to-building rooftop trading; "
                "utility-scale solar farm + carports + biomass/WTE/biogas serve "
                "the residual district load (central supply, not peers).",
    }

    report = {
        "meta": {
            "phase": "Phase 4 — equity + P2P trading report (report-only)",
            "generated_by": "energy/equity_report.py (Opus 4.8, 2026-06-03)",
            "scenario": getattr(result, "scenario", scenario) or "full_stack",
            "alpha": getattr(result, "alpha", 0.0),
            "base_year_snapshot": True,
            "production_headline_inr_per_yr": getattr(result, "annual_cost_inr", 0.0),
            # R-1: the old note hardcoded the May-era pins
            # (1,402,369,939.69 era) - stale by many re-pins. State the
            # contract without freezing a number into a generated artifact.
            "byte_exact_note": (
                "Transfers/prices only; the production LP optimum is unchanged. "
                "The current byte-exact pins live in tests/test_energy_milp.py "
                "+ tests/test_equity_report.py + CLAUDE.md (RF-2 baseline); "
                "production_headline_inr_per_yr above is read from THIS solve."
            ),
        },
        "totals": {
            "consumption_kwh": total_consumption,
            "aggregate_demand_kwh_2030": agg_demand,
            "district_grid_import_kwh": district_grid_import,
            "district_grid_export_kwh": district_grid_export,
            "total_bau_bill_inr": total_bau,
            "total_district_bill_inr": total_district_bill,
            "total_savings_vs_bau_inr": total_savings,
            "total_savings_pct": (100.0 * total_savings / total_bau) if total_bau > 0 else 0.0,
        },
        "p2p": p2p,
        "cross_subsidy_3c": {
            "industrial_surcharge_inr_per_kwh": cross_sub,
            "annual_flow_to_residential_inr": total_cross_subsidy_3c,
            "industrial_grid_import_kwh": ind.get("grid_import_kwh", 0.0),
            "note": "PSPCL embedded industrial cross-subsidy (Rs 1.05/kWh, PSERC "
                    "FY24-25). Paid on grid-supplied industrial units; funds the "
                    "domestic/agri (and here the EWS) discount. Self-consumed "
                    "rooftop is exempt, so district industrial pays less than BAU.",
        },
        "by_class": by_class,
        "ews_equity": ews_equity,
        "pmsgy_attribution": {
            "by_tier_f16": pmsgy_attr,
            "f14_rwa_common_area": pmsgy_f14,
            "rooftop_capex_inr_per_kwp": capex_kwp,
            "production_lp_blended_subsidy_fraction": float(
                econ.rooftop_pv_capex_subsidy_fraction()
            ),
            "note": "F16 per-tier fractions + F14/F15 are REPORT-ONLY "
                    "attribution; the LP keeps the blended 0.30 (byte-exact). "
                    "These are GROSS central-scheme transfers (govt -> owner) and "
                    "are NOT additive to by_class.savings_vs_bau (which already "
                    "reflects the deployed rooftop). F16 = CAPEX subsidy received; "
                    "F15 = a consumption-side benefit for self-installing owners.",
        },
        "n9_v2g_placement": n9,
        "n10_diversity": n10,
        "reconciliation": {
            "consumption_vs_aggregate_demand_rel_err": (
                abs(total_consumption - agg_demand) / agg_demand if agg_demand > 0 else 0.0
            ),
            "note": "Per-class consumption should tie to the 2030 aggregate "
                    "demand (within the Phase-1 attribution tolerance).",
        },
    }
    return report


# --------------------------------------------------------------------------- #
# Output helpers                                                               #
# --------------------------------------------------------------------------- #
def _default_report_path() -> Path:
    return (Path(__file__).parent.parent / "outputs" / "data" / "energy"
            / "equity_report.json")


def write_equity_report_json(report: Dict[str, object],
                             path: Optional[Path] = None) -> Path:
    out = Path(path) if path is not None else _default_report_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return out


def _fmt_inr(x: float) -> str:
    """Indian-style short crore/lakh formatting for the console summary."""
    ax = abs(x)
    if ax >= 1e7:
        return f"Rs {x/1e7:,.2f} cr"
    if ax >= 1e5:
        return f"Rs {x/1e5:,.2f} L"
    return f"Rs {x:,.0f}"


def print_equity_summary(report: Dict[str, object]) -> None:
    t = report["totals"]
    p = report["p2p"]
    e = report["ews_equity"]
    print("\n" + "=" * 70)
    print("PHASE 4 — EQUITY + P2P TRADING REPORT (report-only; headline byte-exact)")
    print("=" * 70)
    print(f"  consumption (2030)        : {t['consumption_kwh']/1e6:,.1f} GWh")
    print(f"  total BAU bill            : {_fmt_inr(t['total_bau_bill_inr'])}/yr")
    print(f"  total district bill       : {_fmt_inr(t['total_district_bill_inr'])}/yr")
    print(f"  total savings vs BAU      : {_fmt_inr(t['total_savings_vs_bau_inr'])}/yr "
          f"({t['total_savings_pct']:.1f}%)")
    print("\n  P2P trading:")
    print(f"    volume                  : {p['annual_volume_kwh']/1e6:,.2f} GWh "
          f"({p['volume_pct_of_demand']:.1f}% of demand)")
    print(f"    buyer saving            : {_fmt_inr(p['annual_buyer_saving_inr'])}/yr")
    print(f"    seller gain             : {_fmt_inr(p['annual_seller_gain_inr'])}/yr")
    print(f"    welfare redistributed   : {_fmt_inr(p['annual_welfare_redistributed_inr'])}/yr")
    print("\n  EWS equity (social tariff):")
    print(f"    consumption             : {e['annual_consumption_kwh']/1e6:,.2f} GWh")
    print(f"    bill @ Rs {e['social_tariff_inr_per_kwh']:.2f}/kWh        : "
          f"{_fmt_inr(e['annual_bill_at_social_tariff_inr'])}/yr")
    print(f"    discount vs first slab  : {_fmt_inr(e['annual_discount_vs_first_slab_inr'])}/yr "
          f"({e['discount_vs_first_slab_pct']:.0f}% off Rs {e['pspcl_first_slab_comparator_inr_per_kwh']})")
    print(f"    gov energy subsidy      : {_fmt_inr(e['gov_energy_subsidy_absorbed_inr'])}/yr")
    print("\n  By class (savings vs BAU):")
    for k, c in report["by_class"].items():
        print(f"    {k:<18} cons {c['consumption_kwh']/1e6:6.2f} GWh  "
              f"eff Rs {c['effective_tariff_inr_per_kwh']:5.2f}/kWh  "
              f"save {_fmt_inr(c['savings_vs_bau_inr'])}/yr ({c['savings_pct']:.0f}%)")
    print("=" * 70)


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main() -> None:
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    sys.path.insert(0, root)
    os.chdir(root)

    from energy.costs import load_economics
    from energy.network import load_optimised_network
    from energy.dispatch import solve_dispatch_pyomo

    print("Solving production dispatch (full_stack, alpha=0) for the equity report...")
    net = load_optimised_network()
    econ = load_economics(force_reload=True)   # production defaults (stage_d off)
    result = solve_dispatch_pyomo(net, econ, scenario_name="full_stack", alpha=0.0)
    # R-1: dropped the hardcoded May-era "(pin...)" tag -
    # the live pins are asserted by the test suite, not this console line.
    print(f"  headline annual cost = {result.annual_cost_inr:,.2f} INR/yr "
          f"(byte-exact pins asserted in tests/test_equity_report.py)")

    report = build_equity_report(net, econ, result)
    out = write_equity_report_json(report)
    print_equity_summary(report)
    print(f"\n  -> wrote {out}")


if __name__ == "__main__":
    main()
