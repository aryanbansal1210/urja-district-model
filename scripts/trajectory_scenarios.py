"""Trajectory-batch A/B scenarios (register 0e,): DEM-3 duck-curve
tariff drift + falling feed-in, DEM-8 carbon price 2042+, REV-3 reserve margin.

Each run clones the economics (deepcopy + force_reload - REV-1-safe: the
identity-pinned caches in network.py key on the clone object), flips ONE
scenario_hooks block to enabled, and re-solves full_stack alpha=0 multi-period.
The production baseline is solved once for the comparison row. NO production
files are modified; results go to outputs/data/energy/trajectory_scenarios.{csv,md}.

Run (from district_v3): python scripts/trajectory_scenarios.py
"""
from __future__ import annotations
import csv, os, sys, time
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
from energy.costs import load_economics
from energy.network import load_optimised_network
from energy.dispatch import solve_dispatch

OUT = os.path.join(ROOT, "outputs", "data", "energy")
NET = load_optimised_network()

SCENARIOS = [
    ("base", None),
    ("dem3_duck_curve", "duck_curve_drift"),
    ("dem8_carbon_price", "carbon_price"),
    ("rev3_reserve_margin", "reserve_margin"),
]


def _per_period(r, key):
    pb = getattr(r, "period_breakdown", {}) or {}
    out = {}
    for y, d in pb.items():
        ic = d.get("installed_capacities", {}) or {}
        out[int(y)] = float(ic.get(key, 0.0) or 0.0)
    return out


def _cost_per_period(r):
    pb = getattr(r, "period_breakdown", {}) or {}
    return {int(y): float(d.get("annual_cost_inr", 0.0)) for y, d in pb.items()}


def run():
    rows = []
    for label, hook in SCENARIOS:
        t = time.time()
        e = deepcopy(load_economics(force_reload=True))
        if hook is not None:
            blocks = e.__dict__.get("scenario_hooks_raw") or {}
            if hook not in blocks:
                print(f"  !! scenario_hooks.{hook} missing from economics.yaml - skipped")
                continue
            blocks[hook]["enabled"] = True
        r = solve_dispatch(NET, e, "full_stack", alpha=0.0)
        bat = _per_period(r, "battery_kwh")
        v2g = _per_period(r, "v2g_units")
        farm = _per_period(r, "solar_farm_kwp")
        biom = _per_period(r, "biomass_kw_e")
        costs = _cost_per_period(r)
        rows.append({
            "scenario": label,
            "annual_cost_2030_inr": round(r.annual_cost_inr, 2),
            "annual_emissions_2030_kg": round(r.annual_emissions_kgco2, 2),
            "lifetime_cost_inr": round(r.lifetime_cost_inr, 0),
            "cost_2042_inr": round(costs.get(2042, 0.0), 0),
            "cost_2055_inr": round(costs.get(2055, 0.0), 0),
            "battery_2030_kwh": round(bat.get(2030, 0.0), 1),
            "battery_2042_kwh": round(bat.get(2042, 0.0), 1),
            "battery_2055_kwh": round(bat.get(2055, 0.0), 1),
            "v2g_2055_units": round(v2g.get(2055, 0.0), 0),
            "farm_2055_kwp": round(farm.get(2055, 0.0), 0),
            "biomass_2055_kw": round(biom.get(2055, 0.0), 0),
            "grid_import_2030_kwh": round(r.grid_import_kwh, 0),
            "grid_export_2030_kwh": round(r.grid_export_kwh, 0),
            "renewable_share": round(r.renewable_share(), 4),
            "ev_smart_shifted_2030_kwh": round(
                getattr(r, "ev_smart_shifted_kwh", 0.0), 0),
        })
        print(f"  {label:<20} cost30 {r.annual_cost_inr/1e6:,.1f} M | "
              f"life {r.lifetime_cost_inr/1e9:.2f} B | "
              f"batt 30/42/55 {bat.get(2030,0)/1e3:.0f}/{bat.get(2042,0)/1e3:.0f}/"
              f"{bat.get(2055,0)/1e3:.0f} MWh ({time.time()-t:.0f}s)", flush=True)

    with open(os.path.join(OUT, "trajectory_scenarios.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    base = rows[0]
    lines = [
        "# Trajectory-batch A/B scenarios (DEM-3 / DEM-8 / REV-3)",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M')} on the trajectory-batch "
        "baseline (register 0e). Each row = ONE scenario_hooks block enabled on a "
        "cloned economics; full_stack alpha=0 multi-period; production files untouched.",
        "Hook definitions + sources: config/economics.yaml `scenario_hooks` "
        "(IEX DAM midday troughs Tier 2; CCTS/IEA WEO carbon path Tier 1-3; "
        "CEA Resource Adequacy margin Tier 1).",
        "",
        "| scenario | cost 2030 (M) | life (B) | cost 2042 (M) | cost 2055 (M) | "
        "battery 30/42/55 (MWh) | v2g 2055 | farm 2055 (MWp) | export 2030 (GWh) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['scenario']} | {row['annual_cost_2030_inr']/1e6:,.1f} | "
            f"{row['lifetime_cost_inr']/1e9:.2f} | {row['cost_2042_inr']/1e6:,.1f} | "
            f"{row['cost_2055_inr']/1e6:,.1f} | "
            f"{row['battery_2030_kwh']/1e3:.0f}/{row['battery_2042_kwh']/1e3:.0f}/"
            f"{row['battery_2055_kwh']/1e3:.0f} | {row['v2g_2055_units']:.0f} | "
            f"{row['farm_2055_kwp']/1e3:.1f} | {row['grid_export_2030_kwh']/1e9:.2f} |"
        )
    lines += [
        "",
        "Reading guide: DEM-3 stresses F28 (cheap midday charging makes storage "
        "more valuable, falling feed-in kills export revenue = F5 stress); DEM-8 "
        "prices operational CO2 from 2042 (build shifts, 2030 headline untouched); "
        "REV-3 forces firm capacity >= 1.15x peak (battery/V2G/dispatchables gain "
        "a resilience role beyond energy arbitrage - pairs SUP-5).",
        f"Base row for deltas: cost 2030 {base['annual_cost_2030_inr']/1e6:,.1f} M, "
        f"lifetime {base['lifetime_cost_inr']/1e9:.2f} B.",
    ]
    with open(os.path.join(OUT, "trajectory_scenarios.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {OUT}/trajectory_scenarios.csv + .md")


if __name__ == "__main__":
    run()
