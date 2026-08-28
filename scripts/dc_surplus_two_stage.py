"""DC-1: size the town's energy system FIRST, then ask how much is spare.

the author, "if we are supplying this extra energy to dc which is
substantial wouldnt the town just build as much solar/w2e/biomass as possible
to supply the dc, shoudlnt the energy infra be decided first then see how much
we can supply to dc? and over years as energy demand in town grows the dc
energy supply would be less?"

That is a real risk and the plain PPA switch does not answer it. With
`ppa.enabled: true` the data centre is inside the optimisation, so the LP is
free to BUILD FOR IT - the offtake stops being "spare energy" and becomes a
customer the town sizes plant around. The annual cap
(`max_ppa_share_of_district_demand`, currently 0.6) bounds how much is sold,
not how much is built to sell.

This script runs the sequence the author actually asked for:

  STAGE 1  solve with the PPA OFF
           -> the town sized for ITSELF. Record the per-period build.
  STAGE 2  solve with the PPA ON and the build FROZEN at Stage 1
           (`fixed_build`, the RES-1 mechanism)
           -> the data centre can only take genuine surplus off
              infrastructure that was never sized for it.
  STAGE 3  solve with the PPA ON and the build FREE
           -> what the town WOULD build if the data centre were allowed to
              drive investment.

Stage 2 is the honest "how much can we spare" answer. Stage 3 - Stage 2 is the
size of the effect the author was worried about, measured rather than asserted.

It also answers the second half of his question directly: because Stage 2
holds the build fixed while district demand grows 2030 -> 2042 -> 2055, the
surplus available to the data centre SHRINKS period by period, and the script
prints that trajectory.

Run from district_v3 (expect ~10-20 min per solve, 3 solves):
    PYTHONPATH=. python -u scripts/dc_surplus_two_stage.py
"""
from __future__ import annotations

import json
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics          # noqa: E402
from energy.dispatch import solve_dispatch_pyomo  # noqa: E402
from energy.network import load_optimised_network  # noqa: E402

# Installed-capacity key -> the multi-period per-vintage new-build Var.
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


def _econ(ppa_on: bool):
    e = deepcopy(load_economics(force_reload=True))
    raw = dict(e.__dict__.get("ppa_raw", {}) or {})
    raw["enabled"] = bool(ppa_on)
    e.__dict__["ppa_raw"] = raw
    return e


def _fixed_build_from(result) -> dict:
    """Per-period CUMULATIVE installed -> per-vintage additions, per Var."""
    pb = result.period_breakdown or {}
    caps = {int(y): (d.get("installed_capacities") or {})
            for y, d in pb.items()}
    if not caps:
        raise SystemExit("period_breakdown empty - is multi_period enabled?")
    years = sorted(caps)
    out: dict = {}
    for key, var in _CAP_TO_VAR.items():
        prev, adds = 0.0, {}
        for y in years:
            cur = float(caps[y].get(key, prev) or 0.0)
            adds[y] = max(0.0, cur - prev)
            prev = cur
        out[var] = adds
    # The farm: the LP is all-fixed-tilt since the flip. Guard it
    # rather than assume, because a tracked share is not recoverable here.
    tracked = float((result.capacities or {}).get("solar_farm_tracked_kwp", 0.0))
    if tracked > 1e-6:
        raise SystemExit(
            "Stage 1 built a TRACKED farm share; the per-period fixed/tracked "
            "split cannot be reconstructed from installed_capacities. Extend "
            "the exporter before trusting Stage 2.")
    prev, fx, tr = 0.0, {}, {}
    for y in years:
        cur = float(caps[y].get("solar_farm_kwp", prev) or 0.0)
        fx[y] = max(0.0, cur - prev)
        tr[y] = 0.0
        prev = cur
    out["farm_fixed_new"] = fx
    out["farm_tracked_new"] = tr
    return out


def _row(tag, r):
    d = r.__dict__
    return {
        "stage": tag,
        "annual_cost_inr": r.annual_cost_inr,
        "annual_emissions_kgco2": r.annual_emissions_kgco2,
        "dc_ppa_offtake_kwh": d.get("dc_ppa_offtake_kwh", 0.0),
        "dc_ppa_revenue_inr": d.get("dc_ppa_revenue_inr", 0.0),
        "temporal_match": d.get("dc_ppa_temporal_match_fraction", 1.0),
        "capacities": dict(r.capacities or {}),
    }


def main() -> None:
    net = load_optimised_network()
    print("network built", flush=True)

    print("\nSTAGE 1  PPA OFF - the town sized for itself", flush=True)
    s1 = solve_dispatch_pyomo(net, _econ(False),
                              scenario_name="full_stack", alpha=0.0)
    print(f"  cost {s1.annual_cost_inr:,.2f}", flush=True)

    frozen = _fixed_build_from(s1)

    print("\nSTAGE 2  PPA ON, build FROZEN at Stage 1 - genuine surplus only",
          flush=True)
    s2 = solve_dispatch_pyomo(net, _econ(True), scenario_name="full_stack",
                              alpha=0.0, fixed_build=frozen)
    print(f"  cost {s2.annual_cost_inr:,.2f}  "
          f"offtake {s2.__dict__.get('dc_ppa_offtake_kwh', 0.0):,.0f} kWh",
          flush=True)

    print("\nSTAGE 3  PPA ON, build FREE - what the DC would pull into being",
          flush=True)
    s3 = solve_dispatch_pyomo(net, _econ(True),
                              scenario_name="full_stack", alpha=0.0)
    print(f"  cost {s3.annual_cost_inr:,.2f}  "
          f"offtake {s3.__dict__.get('dc_ppa_offtake_kwh', 0.0):,.0f} kWh",
          flush=True)

    rows = [_row("1_no_dc", s1), _row("2_dc_on_frozen_build", s2),
            _row("3_dc_on_free_build", s3)]

    print("\n================ RESULT ================")
    for r in rows:
        print(f"{r['stage']:22} cost {r['annual_cost_inr']:>18,.2f}  "
              f"offtake {r['dc_ppa_offtake_kwh']:>14,.0f} kWh  "
              f"match {r['temporal_match']:.3f}")

    print("\n-- how much extra plant the data centre would pull into being --")
    for k in sorted(set(rows[0]["capacities"]) | set(rows[2]["capacities"])):
        a = rows[0]["capacities"].get(k, 0.0)
        c = rows[2]["capacities"].get(k, 0.0)
        if abs(c - a) > 1e-6:
            print(f"  {k:26} {a:>14,.1f} -> {c:>14,.1f}  ({c - a:+,.1f})")

    print("\n-- surplus available per period on the FROZEN build --")
    print("   (Aryan: 'over years as energy demand in town grows the dc "
          "energy supply would be less')")
    for y, d in sorted((s2.period_breakdown or {}).items()):
        dem = float(d.get("annual_demand_kwh", 0.0))
        print(f"   {y}: district demand {dem:>15,.0f} kWh   "
              f"grid import {float(d.get('grid_import_kwh', 0.0)):>14,.0f}   "
              f"export {float(d.get('grid_export_kwh', 0.0)):>13,.0f}")

    out = os.path.join("outputs", "verification",
                       "dc_surplus_two_stage.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    print(f"\nwritten {out}")


if __name__ == "__main__":
    main()
