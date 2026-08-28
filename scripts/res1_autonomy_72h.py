"""RES-1 case A, chronological leg: 72h total-grid-blackout autonomy simulation.

Answers the register's RES-1 metric that the slice LP cannot: hour-by-hour,
during a 72h import = export = 0 event, how much of the town's TOTAL and
CRITICAL load (hospital campus + water treatment + grid streetlights) is
served by the FROZEN build (PV + CHP fleet + battery + thermal store + V2G),
and how long the critical layer holds at 100% ("days of autonomy").

NOT an LP - a deterministic merit-order simulation over 72 hourly steps.
Nothing here touches production files or pins; it reads the frozen solution
from outputs/data/energy/dispatch_results.json and the same econ/network
accessors the Pyomo builder uses (conventions mirrored from
_build_pyomo_model_multi_period,):
  - battery/thermal: discharge budget <= rt_eff x charge (round trip applied
    between charge and discharge), delivery to load x ac_eff, max one DoD
    cycle per day; V2G: per-unit daily kWh budget (period-dependent) +
    power cap, delivery x ac_eff; PV at the load bus (no ac_eff), vintage
    age-derated via econ.pv_vintage_yield_factor.
  - CHP fleet (biomass 15 MW x monthly availability, WTE, biogas) on the
    district bus, delivery x ac_eff.

Conventions (stated in the output md):
  - Event starts 06:00 on a WEEKDAY; the stress month's weekday day-type
    slice profile repeats for 3 days.
  - Storage starts FULL (usable = cap x DoD): overnight ToD charging means
    storage sits full at dawn in normal operation.
  - Critical load is served FIRST within an hour (Indian discom
    essential-services curtailment ladder; reporting convention, Tier 3).
  - No exports (nowhere to send); PV surplus charges battery -> thermal ->
    curtailed.

Requires network.demand_components_by_slice_kw (RES-1 accessor, added with
the unserved-Var hook); fails loudly if absent.

Run (from district_v3):
  python scripts/res1_autonomy_72h.py [--months jan,jul] [--periods 2030,2042,2055]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics          # noqa: E402
from energy.network import load_optimised_network  # noqa: E402

RESULTS_JSON = os.path.join(ROOT, "outputs", "data", "energy",
                            "dispatch_results.json")
OUT_DIR = os.path.join(ROOT, "outputs", "data", "energy")
# Critical set: healthcare cells + public_services cells (the water-treatment
# district baseload is BAKED INTO public-services node base load, network.py
# ~line 346) + the grid-streetlight district term (separate component key).
CRITICAL_CATEGORIES = ("healthcare", "public_services")

# real lifeline loads NOT in the LP demand model (boundary), so they are added
# here to BOTH the sim's hourly demand and the critical requirement as cited
# constant-kW proxies (design pop 250,000, Stage- binding decision):
#   sewage  ~0.57 MW: 108 LPCD sewage (CPHEEO 135 x 0.8) x 0.5 kWh/m3 (MDPI
#           Energies 16:2433 municipal band 0.3-0.8, Tier 3 derived)
#   telecom ~0.66 MW: ~1 tower/1,890 people x ~5 kW (GSMA India towers, Tier 3)
DESIGN_POP = 250_000
SEWAGE_KW = DESIGN_POP * 0.108 * 0.5 / 24.0          # m3/day x kWh/m3 -> kW
TELECOM_KW = (DESIGN_POP / 1_890.0) * 5.0
BOUNDARY_CRITICAL_KW = SEWAGE_KW + TELECOM_KW
EVENT_HOURS = 72
EVENT_START_HOUR = 6                    # 06:00 weekday start convention


def _frozen_capacities(path: str) -> dict[int, dict[str, float]]:
    """full_stack per-period installed capacities from the frozen JSON."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    fs = None
    for sc in data.get("scenarios", []):
        if sc.get("name") == "full_stack":
            fs = sc
            break
    if fs is None:
        raise SystemExit("full_stack scenario not found in dispatch_results.json")
    caps_end = fs.get("capacities", {})
    tracked_end = float(caps_end.get("solar_farm_tracked_kwp", 0.0) or 0.0)
    if tracked_end > 1e-6:
        print("  !! WARNING: frozen solution carries a TRACKED farm share "
              f"({tracked_end:,.0f} kWp). This sim treats the whole farm at "
              "fixed-tilt yield; refine before quoting if the tracked A/B "
              "revives the split.", file=sys.stderr)
    out: dict[int, dict[str, float]] = {}
    for y_str, pd in (fs.get("period_breakdown") or {}).items():
        ic = pd.get("installed_capacities", {}) or {}
        out[int(y_str)] = {k: float(v or 0.0) for k, v in ic.items()}
    if not out:
        raise SystemExit("full_stack period_breakdown empty - regen JSON first")
    return out


def _vintage_adds(fleet_by_period: dict[int, float],
                  years: list[int]) -> dict[int, float]:
    """Cumulative per-period fleet -> per-vintage additions (clamped >= 0)."""
    adds, prev = {}, 0.0
    for y in years:
        cur = float(fleet_by_period.get(y, prev))
        adds[y] = max(0.0, cur - prev)
        prev = cur
    return adds


def _weekday_slices(econ, month: str) -> list:
    sl = [s for s in econ.slices
          if s.month == month and getattr(s, "day_type", "mixed") == "weekday"
          and s.hours_per_year > 0]
    if len(sl) != 24:
        raise SystemExit(f"expected 24 weekday slices for {month}, got {len(sl)}"
                         " (sim requires 864-slice mode)")
    return sorted(sl, key=lambda s: int(getattr(s, "hour")))


def simulate(period: int, month: str, econ, net, caps_by_period,
             period_years: list[int]) -> dict:
    ic = caps_by_period[period]

    # ---- hourly demand template (kW), total + critical -------------------
    slices = _weekday_slices(econ, month)
    hours_of = {s.id: s.hours_per_year for s in slices}

    demand_kwh = net.demand_by_slice_kwh(econ)
    comps = net.demand_components_by_slice_kw(econ)   # RES-1 accessor
    ev_base = net.ev_charging_kwh_by_slice(econ, year=None)
    ev_y = net.ev_charging_kwh_by_slice(econ, year=period)
    pmult = econ.period_demand_multiplier(period)

    total_kw, crit_kw = [], []
    for s in slices:
        non_ev = demand_kwh[s.id] - ev_base.get(s.id, 0.0)
        # verbatim mirror of dispatch.py period_slice_demand:
        # pmult x (non_ev + ev_by_period)
        tot = pmult * (non_ev + ev_y.get(s.id, 0.0))
        total_kw.append(tot / hours_of[s.id])
        c_kw = sum(comps.get(cat, {}).get(s.id, 0.0)
                   for cat in CRITICAL_CATEGORIES)
        c_kw += comps.get("street_lighting", {}).get(s.id, 0.0)
        crit_kw.append(pmult * c_kw)   # non-EV categories scale with the period

    # ---- hourly PV per kWp templates (kW/kWp), vintage-aged fleets -------
    yield_roof = net.pv_yield_per_kwp_kwh(econ)
    yield_farm = net.pv_yield_per_kwp_kwh_solar_farm(econ)
    fpv_mult = econ.floating_pv_yield_multiplier_vs_ground_mount()
    bipv_mult = econ.bipv_yield_multiplier_vs_rooftop()

    roof_adds = _vintage_adds({y: caps_by_period[y].get("rooftop_pv_kwp", 0.0)
                               for y in period_years}, period_years)
    farm_adds = _vintage_adds({y: caps_by_period[y].get("solar_farm_kwp", 0.0)
                               for y in period_years}, period_years)
    carport_adds = _vintage_adds({y: caps_by_period[y].get("carport_kwp", 0.0)
                                  for y in period_years}, period_years)
    fpv_adds = _vintage_adds({y: caps_by_period[y].get("floating_pv_kwp", 0.0)
                              for y in period_years}, period_years)
    bipv_adds = _vintage_adds({y: caps_by_period[y].get("bipv_kwp", 0.0)
                               for y in period_years}, period_years)

    pv_kw = []
    for s in slices:
        r_y = yield_roof[s.id] / hours_of[s.id]
        f_y = yield_farm[s.id] / hours_of[s.id]
        kw = 0.0
        for vy in period_years:
            if vy > period:
                break
            r_age = econ.pv_vintage_yield_factor("rooftop_pv", vy, period)
            f_age = econ.pv_vintage_yield_factor("solar_farm", vy, period)
            kw += r_y * roof_adds[vy] * r_age
            kw += f_y * farm_adds[vy] * f_age          # all-fixed farm (guarded)
            kw += f_y * carport_adds[vy] * f_age
            kw += f_y * fpv_mult * fpv_adds[vy] * f_age
            kw += r_y * bipv_mult * bipv_adds[vy] * r_age
        pv_kw.append(kw)

    # ---- dispatchable + storage parameters (builder conventions) ---------
    ac_eff = max(1e-6, 1.0 - econ.ac_loss_fraction())
    # net of the plant's own auxiliary load (CERC RTE x (1-AEC)).
    rt_eff = econ.battery_rte_net_of_aux_for("ac_traditional")
    max_dod = econ.battery_max_dod()
    batt_c = econ.battery_c_rate_per_hour()
    th_rt = econ.thermal_storage_round_trip_efficiency()
    th_c = econ.thermal_storage_c_rate_per_hour()

    batt_kwh = ic.get("battery_kwh", 0.0)
    th_kwh = ic.get("thermal_storage_kwh", 0.0)
    v2g_units = ic.get("v2g_units", 0.0)
    v2g_p_kw = econ.v2g_power_kw_per_unit() * v2g_units
    try:
        v2g_day_kwh = econ.v2g_kwh_per_unit_per_day(period) * v2g_units
    except TypeError:
        v2g_day_kwh = econ.v2g_kwh_per_unit_per_day() * v2g_units

    bm_kw = ic.get("biomass_kw_e", 0.0) * econ.biomass_monthly_availability_fraction(month)
    wte_kw = ic.get("wte_kw_e", 0.0)
    bg_kw = ic.get("biogas_kw_e", 0.0)
    straw_budget = econ.biomass_annual_straw_energy_cap_kwh() or float("inf")

    # ---- 72h merit-order walk --------------------------------------------
    batt_soc = batt_kwh * max_dod          # start full (usable energy)
    th_soc = th_kwh * max_dod
    batt_dis_day = th_dis_day = v2g_day_used = 0.0
    straw_used = 0.0
    served_tot = served_crit = dem_tot = dem_crit = 0.0
    crit_full_hours = 0
    first_crit_gap_h = None
    rows = []

    for h in range(EVENT_HOURS):
        hod = (EVENT_START_HOUR + h) % 24
        if h > 0 and hod == EVENT_START_HOUR:
            batt_dis_day = th_dis_day = v2g_day_used = 0.0   # daily budgets reset
        dem = total_kw[hod] + BOUNDARY_CRITICAL_KW
        crit = min(crit_kw[hod], total_kw[hod]) + BOUNDARY_CRITICAL_KW
        pv = pv_kw[hod]

        supply = min(pv, dem)                 # PV at the bus, no ac_eff
        surplus = max(0.0, pv - dem)
        need = dem - supply

        # CHP fleet (delivery x ac_eff; straw budget tracked for biomass)
        for cap_kw, is_bm in ((bm_kw, True), (wte_kw, False), (bg_kw, False)):
            if need <= 1e-9 or cap_kw <= 0.0:
                continue
            gen = min(cap_kw, need / ac_eff)
            if is_bm:
                gen = min(gen, max(0.0, straw_budget - straw_used))
                straw_used += gen
            supply += gen * ac_eff
            need = dem - supply

        # battery (power cap, SOC, one-DoD-cycle-per-day budget)
        if need > 1e-9 and batt_kwh > 0.0:
            dis = min(batt_c * batt_kwh, batt_soc,
                      batt_kwh * max_dod - batt_dis_day, need / ac_eff)
            if dis > 0:
                batt_soc -= dis
                batt_dis_day += dis
                supply += dis * ac_eff
                need = dem - supply

        # thermal store (same conventions; electric-equivalent, LP-style)
        if need > 1e-9 and th_kwh > 0.0:
            dis = min(th_c * th_kwh, th_soc,
                      th_kwh * max_dod - th_dis_day, need / ac_eff)
            if dis > 0:
                th_soc -= dis
                th_dis_day += dis
                supply += dis * ac_eff
                need = dem - supply

        # V2G (power cap + per-day energy budget)
        if need > 1e-9 and v2g_units > 0.0:
            dis = min(v2g_p_kw, max(0.0, v2g_day_kwh - v2g_day_used),
                      need / ac_eff)
            if dis > 0:
                v2g_day_used += dis
                supply += dis * ac_eff
                need = dem - supply

        # PV surplus -> battery, then thermal (charge x rt_eff), else curtail
        if surplus > 1e-9 and batt_kwh > 0.0:
            room = batt_kwh * max_dod - batt_soc
            chg = min(surplus, batt_c * batt_kwh, room / rt_eff if rt_eff else 0.0)
            batt_soc += chg * rt_eff
            surplus -= chg
        if surplus > 1e-9 and th_kwh > 0.0:
            room = th_kwh * max_dod - th_soc
            chg = min(surplus, th_c * th_kwh, room / th_rt if th_rt else 0.0)
            th_soc += chg * th_rt
            surplus -= chg

        unserved = max(0.0, dem - supply)
        crit_served = min(crit, supply)       # critical-first ladder
        if crit - crit_served <= 1e-6:
            crit_full_hours += 1
        elif first_crit_gap_h is None:
            first_crit_gap_h = h

        dem_tot += dem
        dem_crit += crit
        served_tot += dem - unserved
        served_crit += crit_served
        rows.append((h, hod, dem, crit, pv, supply, unserved))

    crit_avg_kw = dem_crit / EVENT_HOURS
    straw_days_critical = (straw_budget / (crit_avg_kw * 24.0)
                           if crit_avg_kw > 0 and straw_budget != float("inf")
                           else float("inf"))
    return {
        "period": period, "month": month,
        "demand_mwh": dem_tot / 1e3, "served_mwh": served_tot / 1e3,
        "served_pct": 100.0 * served_tot / dem_tot if dem_tot else 0.0,
        "crit_demand_mwh": dem_crit / 1e3, "crit_served_mwh": served_crit / 1e3,
        "crit_served_pct": 100.0 * served_crit / dem_crit if dem_crit else 0.0,
        "crit_full_hours": crit_full_hours,
        "first_crit_gap_h": first_crit_gap_h,
        "straw_used_mwh_e": straw_used / 1e3,
        "straw_days_critical_only": straw_days_critical,
        "batt_soc_end_mwh": batt_soc / 1e3,
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", default="jan,jul")
    ap.add_argument("--periods", default="2030,2042,2055")
    ap.add_argument("--json", default=RESULTS_JSON)
    args = ap.parse_args()

    econ = deepcopy(load_economics(force_reload=True))
    net = load_optimised_network()
    # Drift guard (see network.demand_components_by_slice_kw docstring).
    _total = net.demand_by_slice_kw(econ)
    _comps = net.demand_components_by_slice_kw(econ)
    for _sid, _v in _total.items():
        _c = sum(d.get(_sid, 0.0) for d in _comps.values())
        if abs(_c - _v) > 1e-6 * max(1.0, abs(_v)):
            raise SystemExit(f"components drift at slice {_sid}: {_c} vs {_v}")
    caps = _frozen_capacities(args.json)
    period_years = sorted(caps)
    months = [m.strip() for m in args.months.split(",") if m.strip()]
    periods = [int(p) for p in args.periods.split(",")]

    results = [simulate(p, m, econ, net, caps, period_years)
               for p in periods for m in months]

    lines = [
        "# RES-1 case A: 72h grid-blackout autonomy (chronological simulation)",
        "",
        "Frozen build, import = export = 0 for 72h from a 06:00 weekday start;",
        "storage starts full (usable = cap x DoD); critical load (hospital",
        "campus + water treatment + grid streetlights) served first; merit",
        "order PV -> CHP (straw/WTE/biogas) -> battery -> thermal -> V2G;",
        "LP conventions mirrored (ac_eff on AC-side delivery, rt_eff between",
        "charge and discharge, one DoD cycle per day). Sewage + telecom",
        f"lifeline proxies (~{BOUNDARY_CRITICAL_KW/1e3:.2f} MW combined, boundary loads outside",
        "the LP demand model) are included in BOTH hourly demand and the",
        "critical requirement (Aryan ballot 2026-07-19). Method + citations:",
        "_spec/RES_1_RESILIENCE_PACK.md. Generated by scripts/res1_autonomy_72h.py.",
        "",
        "| period | month | total served % | critical served % | critical 100% hours (of 72) | first critical gap (h) | straw burned MWh_e | straw budget alone = days of critical-only service |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        gap = "-" if r["first_crit_gap_h"] is None else str(r["first_crit_gap_h"])
        sd = r["straw_days_critical_only"]
        sd_s = "unbounded" if sd == float("inf") else f"{sd:,.0f}"
        lines.append(
            f"| {r['period']} | {r['month']} | {r['served_pct']:.1f} "
            f"| {r['crit_served_pct']:.1f} | {r['crit_full_hours']} | {gap} "
            f"| {r['straw_used_mwh_e']:,.1f} | {sd_s} |")
        print(f"  {r['period']} {r['month']}: total {r['served_pct']:5.1f}% | "
              f"critical {r['crit_served_pct']:5.1f}% "
              f"({r['crit_full_hours']}/72 h at 100%)")

    out_md = os.path.join(OUT_DIR, "res1_autonomy_72h.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"-> {out_md}")


if __name__ == "__main__":
    main()
