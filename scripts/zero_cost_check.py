"""Switching-point analysis #1 - "would the tech deploy if CAPEX = 0?" (supervisor ask,).

For each tech the model currently does NOT build (battery, thermal storage, BIPV), set its CAPEX -> ~0
and re-solve full_stack alpha=0. If it then DEPLOYS, the absence at real cost is ECONOMIC (validates
 - "battery=0 is economics, not a constraint/bug"), not a modelling artifact. Pure diagnostic: clones
the econ, changes nothing in production. Run: python scripts/zero_cost_check.py
"""
from __future__ import annotations
import json, os, sys, time
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
from energy.costs import load_economics
from energy.network import load_optimised_network
from energy.dispatch import solve_dispatch

net = load_optimised_network()
PIN = 1_402_369_939.69

def solve(mod_fn):
    e = deepcopy(load_economics(force_reload=True))
    mod_fn(e)
    return solve_dispatch(net, e, "full_stack", alpha=0.0)

# (label, capacity key in result.capacities, mutator that zeroes the tech CAPEX)
def _zero_battery(e):  e.technologies["li_ion_battery"]["capex_inr_per_kwh"] = 0.0
def _zero_thermal(e):  e.technologies["thermal_cold_storage"]["capex_inr_per_kwh_thermal"] = 0.0
def _zero_bipv(e):     e.__dict__["bipv_raw"]["capex_multiplier_vs_rooftop"] = 0.0
CHECKS = [
    ("battery",         "battery_kwh",  _zero_battery),
    ("thermal_storage", "thermal_storage_kwh", _zero_thermal),
    ("bipv",            "bipv_kwp",     _zero_bipv),
]

def main():
    print("=== ZERO-COST DEPLOYMENT CHECK (would it deploy if CAPEX=0?) ===", flush=True)
    print("baseline first (production full_stack a=0)...", flush=True)
    t = time.time()
    base = solve(lambda e: None)
    print(f"  baseline cost {base.annual_cost_inr:,.0f} (pin {PIN:,.0f}); "
          f"emis {base.annual_emissions_kgco2/1e6:.1f} kt; battery {base.capacities.get('battery_kwh',0):,.0f} kWh "
          f"({time.time()-t:.0f}s)", flush=True)
    rows = []
    for label, cap_key, mod in CHECKS:
        print(f"solving with {label} CAPEX=0 ...", flush=True)
        t = time.time()
        r = solve(mod)
        base_cap = base.capacities.get(cap_key, 0.0)
        free_cap = r.capacities.get(cap_key, 0.0)
        rows.append({
            "tech": label, "capacity_key": cap_key,
            "baseline_deployed": base_cap, "deployed_at_zero_cost": free_cap,
            "deploys_when_free": free_cap > max(1.0, 0.001 * base_cap + 1.0),
            "cost_at_zero_cost_inr": r.annual_cost_inr,
            "emissions_at_zero_cost_kg": r.annual_emissions_kgco2,
            "cost_delta_vs_baseline_pct": (r.annual_cost_inr - base.annual_cost_inr) / base.annual_cost_inr * 100,
            "emis_delta_vs_baseline_pct": (r.annual_emissions_kgco2 - base.annual_emissions_kgco2) / base.annual_emissions_kgco2 * 100,
            "solve_s": round(time.time() - t, 0),
        })
        print(f"  {label}: baseline {base_cap:,.0f} -> @cost0 {free_cap:,.0f} "
              f"(cost {rows[-1]['cost_delta_vs_baseline_pct']:+.1f}%, "
              f"emis {rows[-1]['emis_delta_vs_baseline_pct']:+.1f}%) [{rows[-1]['solve_s']:.0f}s]", flush=True)
    out = {"baseline": {"cost": base.annual_cost_inr, "emissions_kg": base.annual_emissions_kgco2},
           "checks": rows,
           "note": "If a tech is 0 at baseline AND deploys at CAPEX=0, the absence is economic (not a "
                   "constraint/bug). Battery deploying when free validates F1."}
    p = os.path.join(ROOT, "outputs", "data", "energy", "zero_cost_check.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=2)
    print("\n=== SUMMARY ===")
    for r in rows:
        verdict = "DEPLOYS (absence is economic)" if r["deploys_when_free"] else "STILL 0 (constraint/no-use, not cost)"
        print(f"  {r['tech']:<16} baseline {r['baseline_deployed']:>10,.0f} -> @free {r['deployed_at_zero_cost']:>12,.0f}  => {verdict}")
    print(f"  -> wrote {p}")

if __name__ == "__main__":
    main()
