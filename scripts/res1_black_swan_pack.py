"""RES-1 black-swan stress pack: 5 shock cases on the FROZEN build.

Method (_spec/RES_1_RESILIENCE_PACK.md): every solve runs full_stack alpha=0
multi-period with (a) the scenario_hooks.resilience_unserved hook ON (an
unserved-energy Var priced at VoLL Rs 140/kWh, CEA RA Guidelines Tier 1 -
citations in economics.yaml + the pack doc), and (b) the build FROZEN at the
production solution (fixed_build: the 12 per-vintage new-build Vars.fixed
at vintage additions differenced from dispatch_results.json). Operations
respond; the design does not. Pins untouched: the hook is enabled only on
deepcopied econ clones (trajectory_scenarios.py pattern, REV-1-safe).

Cases:
  null          hook on, no shock            -> MUST equal the pin to the paisa
                                                with unserved == 0 (gate)
  a_blackout_jan/jul  import = export = 0 for the month (all periods; the
                shared physical connection also takes green OA down)
  b_heatwave    2055 may+jun demand x 1.175 (cooling ~50% of those months x
                +35% heatwave uplift, Tier 3 derived - pack doc RES-B)
                + all-PV yield x 0.97 those months
  c_straw_lost  straw energy cap x 0.0 (all periods; permanent = upper bound)
  d_canal_dec   floating-PV yield x 0.0 in dec (Sirhind closure precedent)
  e_n1_import   import cap x 0.5, all months (one 220 kV corridor down)
  voll_20       a_blackout_jan re-run at VoLL 20 -> shed/served% must MATCH
                a_blackout_jan (only the damage price moves)

Run (from district_v3, AFTER the hook + fixed_build + components accessor
land and the null gate passes):
  python -u scripts/res1_black_swan_pack.py [--cases null,a_blackout_jan,...]
Progress prints per case; expect ~10-20 min per solve.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics            # noqa: E402
from energy.network import load_optimised_network  # noqa: E402
from energy.dispatch import solve_dispatch_pyomo   # noqa: E402

RESULTS_JSON = os.path.join(ROOT, "outputs", "data", "energy",
                            "dispatch_results.json")
OUT_DIR = os.path.join(ROOT, "outputs", "data", "energy")
VOLL_INR_PER_KWH = 140.0     # CEA Draft RA Guidelines 2022 Annexure C, Tier 1
CRITICAL_CATEGORIES = ("healthcare", "public_services")  # + street_lighting
ALL_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec")

# JSON installed-capacity key -> multi-period new-build Var name.
_CAP_TO_VAR = {
    "rooftop_pv_kwp": "rooftop_new",
    "battery_kwh": "battery_new",
    "v2g_units": "v2g_new",
    "biomass_kw_e": "biomass_new",
    "wte_kw_e": "wte_new",
    "biogas_kw_e": "biogas_new",
    "thermal_storage_kwh": "thermal_new",
    "bipv_kwp": "bipv_new",
    "carport_kwp": "carport_new",
    "floating_pv_kwp": "floating_pv_new",
}


def _load_frozen(path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    fs = next((sc for sc in data.get("scenarios", [])
               if sc.get("name") == "full_stack"), None)
    if fs is None:
        raise SystemExit("full_stack not found in dispatch_results.json")
    pb = fs.get("period_breakdown") or {}
    caps = {int(y): (d.get("installed_capacities") or {}) for y, d in pb.items()}
    if not caps:
        raise SystemExit("period_breakdown empty - run the regen first")
    end = fs.get("capacities") or {}
    if float(end.get("solar_farm_tracked_kwp", 0.0) or 0.0) > 1e-6:
        raise SystemExit(
            "frozen solution has a TRACKED farm share; the per-period "
            "fixed/tracked split is not recoverable from the JSON - extend "
            "the exporter before running the pack")
    return fs, caps


def _fixed_build(caps: dict[int, dict[str, float]]) -> dict[str, dict[int, float]]:
    """Cumulative per-period installed -> per-vintage additions per Var."""
    years = sorted(caps)
    out: dict[str, dict[int, float]] = {}
    for key, var in _CAP_TO_VAR.items():
        prev, adds = 0.0, {}
        for y in years:
            cur = float(caps[y].get(key, prev) or 0.0)
            adds[y] = max(0.0, cur - prev)
            prev = cur
        out[var] = adds
    prev, fx, tr = 0.0, {}, {}
    for y in years:   # all-fixed farm (guarded in _load_frozen)
        cur = float(caps[y].get("solar_farm_kwp", prev) or 0.0)
        fx[y] = max(0.0, cur - prev)
        tr[y] = 0.0
        prev = cur
    out["farm_fixed_new"] = fx
    out["farm_tracked_new"] = tr
    return out


def _hook(e, voll: float, params: dict) -> None:
    blocks = e.__dict__.setdefault("scenario_hooks_raw", {})
    blocks["resilience_unserved"] = {
        "enabled": True, "voll_inr_per_kwh": voll, **params}


def _period_demand_kwh(net, econ, period: int,
                       dem_mult_by_month: dict[str, float]) -> dict[str, float]:
    """Per-slice TOTAL demand kWh for one period, mirroring the dispatch
    formula pmult x (non_ev + ev_by_period), with any RES-B shock month
    multiplier applied (reporting must match the LP's shocked demand)."""
    demand_kwh = net.demand_by_slice_kwh(econ)
    ev_base = net.ev_charging_kwh_by_slice(econ, year=None)
    ev_y = net.ev_charging_kwh_by_slice(econ, year=period)
    pmult = econ.period_demand_multiplier(period)
    month_of = {s.id: s.month for s in econ.slices}
    return {
        sid: (pmult * (demand_kwh[sid] - ev_base.get(sid, 0.0)
                       + ev_y.get(sid, 0.0))
              * float(dem_mult_by_month.get(month_of[sid], 1.0)))
        for sid in demand_kwh
    }


def _critical_kwh(net, econ, period: int,
                  dem_mult_by_month: dict[str, float]) -> dict[str, float]:
    """Per-slice CRITICAL demand kWh (healthcare + public_services incl.
    water + streetlights; no EV in these categories), same scaling."""
    comps = net.demand_components_by_slice_kw(econ)
    pmult = econ.period_demand_multiplier(period)
    month_of = {s.id: s.month for s in econ.slices}
    out: dict[str, float] = {}
    for s in econ.slices:
        kw = sum(comps.get(c, {}).get(s.id, 0.0) for c in CRITICAL_CATEGORIES)
        kw += comps.get("street_lighting", {}).get(s.id, 0.0)
        out[s.id] = (pmult * kw * s.hours_per_year
                     * float(dem_mult_by_month.get(month_of[s.id], 1.0)))
    return out


CASES: dict[str, dict] = {
    "null": {"params": {}},
    "a_blackout_jan": {"params": {
        "import_cap_multiplier_by_month": {"jan": 0.0},
        "export_cap_multiplier_by_month": {"jan": 0.0}},
        "window_months": ("jan",)},
    "a_blackout_jul": {"params": {
        "import_cap_multiplier_by_month": {"jul": 0.0},
        "export_cap_multiplier_by_month": {"jul": 0.0}},
        "window_months": ("jul",)},
    "b_heatwave": {"params": {
        "demand_multiplier_by_period_month": {2055: {"may": 1.175,
                                                     "jun": 1.175}},
        "pv_yield_multiplier_by_month": {"may": 0.97, "jun": 0.97}},
        "window_months": ("may", "jun"), "window_periods": (2055,)},
    "c_straw_lost": {"params": {"straw_energy_cap_multiplier": 0.0}},
    "d_canal_dec": {"params": {
        "floating_pv_yield_multiplier_by_month": {"dec": 0.0}},
        "window_months": ("dec",)},
    "e_n1_import": {"params": {
        "import_cap_multiplier_by_month": {m: 0.5 for m in ALL_MONTHS}}},
    "voll_20": {"params": {
        "import_cap_multiplier_by_month": {"jan": 0.0},
        "export_cap_multiplier_by_month": {"jan": 0.0}},
        "window_months": ("jan",), "voll": 20.0},
}


def _assert_components_sum(net, econ) -> None:
    """Drift guard: the components accessor replicates demand_by_slice_kw's
    arithmetic (pin-safety, see network.py docstring) - prove they agree."""
    total = net.demand_by_slice_kw(econ)
    comps = net.demand_components_by_slice_kw(econ)
    for sid, v in total.items():
        c = sum(d.get(sid, 0.0) for d in comps.values())
        if abs(c - v) > 1e-6 * max(1.0, abs(v)):
            raise SystemExit(
                f"components drift at slice {sid}: {c} vs {v} - "
                "demand_components_by_slice_kw is out of sync with "
                "demand_by_slice_kw")


def run(case_names: list[str]) -> None:
    net = load_optimised_network()
    _assert_components_sum(net, deepcopy(load_economics(force_reload=True)))
    print("  components drift guard: OK", flush=True)
    fs, caps = _load_frozen(RESULTS_JSON)
    fixed = _fixed_build(caps)
    base_cost_by_period = {int(y): float(d.get("annual_cost_inr", 0.0))
                           for y, d in (fs.get("period_breakdown") or {}).items()}
    rows = []
    for name in case_names:
        spec = CASES[name]
        params = spec["params"]
        window_m = spec.get("window_months", ALL_MONTHS)
        window_p = spec.get("window_periods")
        voll = float(spec.get("voll", VOLL_INR_PER_KWH))
        t0 = time.time()
        e = deepcopy(load_economics(force_reload=True))
        _hook(e, voll, params)
        r = solve_dispatch_pyomo(net, e, scenario_name="full_stack",
                                 alpha=0.0, fixed_build=fixed)
        us_ps = getattr(r, "unserved_kwh_by_period_slice", None)
        if us_ps is None:
            raise SystemExit("result has no unserved_kwh_by_period_slice - "
                             "is the resilience_unserved hook wired?")
        month_of = {s.id: s.month for s in e.slices}
        pb = getattr(r, "period_breakdown", {}) or {}
        dm_by_period = (params.get("demand_multiplier_by_period_month") or {})
        case_rows = []
        for y in sorted(int(k) for k in pb):
            if window_p and y not in window_p:
                continue
            us = us_ps.get(y, us_ps.get(str(y), {})) or {}
            dm_m = {str(k): float(v) for k, v in
                    (dm_by_period.get(y) or dm_by_period.get(str(y)) or {}).items()}
            dem = _period_demand_kwh(net, e, y, dm_m)
            crit = _critical_kwh(net, e, y, dm_m)
            in_w = {sid for sid in dem if month_of[sid] in window_m}
            shed_w = sum(us.get(sid, 0.0) for sid in in_w)
            dem_w = sum(dem[sid] for sid in in_w)
            crit_w = sum(crit[sid] for sid in in_w)
            # critical-first ladder: shed eats non-critical before critical
            shed_crit_w = sum(
                max(0.0, us.get(sid, 0.0) - max(0.0, dem[sid] - crit[sid]))
                for sid in in_w)
            shed_y = sum(us.values())
            cost_y = float(pb[y].get("annual_cost_inr", 0.0) or 0.0)
            op_cost_y = cost_y - voll * shed_y   # strip the VoLL penalty
            case_rows.append({
                "case": name, "period": y, "voll_inr_per_kwh": voll,
                "shed_gwh_year": round(shed_y / 1e6, 4),
                "shed_gwh_window": round(shed_w / 1e6, 4),
                "served_pct_window": round(
                    100.0 * (1.0 - shed_w / dem_w) if dem_w else 100.0, 3),
                "crit_served_pct_window": round(
                    100.0 * (1.0 - shed_crit_w / crit_w) if crit_w else 100.0, 3),
                "op_cost_delta_minr": round(
                    (op_cost_y - base_cost_by_period.get(y, 0.0)) / 1e6, 2),
                "voll_cost_minr": round(voll * shed_y / 1e6, 2),
                "window_demand_gwh": round(dem_w / 1e6, 2),
                "window_critical_gwh": round(crit_w / 1e6, 2),
            })
        rows.extend(case_rows)
        summary = ", ".join(
            f"{cr['period']}: served {cr['served_pct_window']:.1f}% / "
            f"crit {cr['crit_served_pct_window']:.1f}%" for cr in case_rows)
        print(f"  {name:<16} {time.time() - t0:6,.0f}s  {summary}", flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_csv = os.path.join(OUT_DIR, "res1_black_swan.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"-> {out_csv} ({len(rows)} rows). The md table + FINDINGS entries "
          "are written from this csv (pack doc section 4).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=",".join(CASES))
    args = ap.parse_args()
    names = [c.strip() for c in args.cases.split(",") if c.strip()]
    unknown = [c for c in names if c not in CASES]
    if unknown:
        raise SystemExit(f"unknown cases: {unknown}; known: {list(CASES)}")
    run(names)
