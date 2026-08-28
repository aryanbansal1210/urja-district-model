"""Proof for INTERNAL-NETWORK EMBODIED CARBON.

The same batch started CHARGING the district's cables, substation and
distribution transformers. Costing the copper while ignoring its carbon is
an asymmetry, so the carbon is added here at the same parity.

WHAT MUST HOLD:
  1. COST MUST NOT MOVE. The carbon price is levied on OPERATIONAL
     emissions only (dispatch.py ~2944: "Embodied carbon is deliberately
     excluded"), so this term must be invisible to the cost. If cost moves,
     the term leaked into the carbon price and the exclusion is broken.
  2. CO2 rises by EXACTLY the annualised constant in BOTH scenarios, and
     no capacity changes - a constant cannot move an argmin.
  3. Predicted in advance: vs-BAU CO2 61.430% -> 61.381%.

Baseline (internal network costed, carbon NOT yet added), from
outputs/verification/internal_network_proof_20260811.txt:
     town 1,982,474,680.20 / 117,163,413.04
     bau  3,546,796,546.71 / 303,765,424.09

Run from district_v3:
    PYTHONPATH=. python -u scripts/internal_network_carbon_proof.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics                       # noqa: E402
from energy.dispatch import solve_dispatch_pyomo               # noqa: E402
from energy.electrical_assets import (                         # noqa: E402
    production_network_annualised_kgco2,
)
from energy.network import load_optimised_network              # noqa: E402

BASE_COST = {"full_stack": 1_982_474_680.20, "bau": 3_546_796_546.71}
BASE_CO2 = {"full_stack": 117_163_413.04, "bau": 303_765_424.09}

econ = load_economics(force_reload=True)
net = load_optimised_network()
print("network built\n", flush=True)

emb = production_network_annualised_kgco2(net, econ)
const = float(emb["annualised_total_kgco2"])
print("--- embodied carbon being added ---")
print(f"  cables        {emb['cable_kgco2_total'] / 1000:>10,.1f} tCO2 over 40 y"
      f"  -> {emb['cable_kgco2_annual']:>12,.2f} kg/yr")
print(f"  substation    {emb['substation_kgco2_total'] / 1000:>10,.1f} tCO2 over 35 y"
      f"  -> {emb['substation_kgco2_annual']:>12,.2f} kg/yr")
print(f"  dist txfmrs   {emb['transformer_kgco2_total'] / 1000:>10,.1f} tCO2 over 25 y"
      f"  -> {emb['transformer_kgco2_annual']:>12,.2f} kg/yr")
print(f"  TOTAL                                     "
      f"     {const:>12,.2f} kg/yr\n")

rows = {}
for scen in ("full_stack", "bau"):
    r = solve_dispatch_pyomo(net, econ, scenario_name=scen, alpha=0.0)
    rows[scen] = (r.annual_cost_inr, r.annual_emissions_kgco2, r.capacities)
    print(f"  {scen:11} cost {r.annual_cost_inr:>18,.2f}  "
          f"CO2 {r.annual_emissions_kgco2:>16,.2f}", flush=True)

print("\n--- CHECK 1: cost must NOT move ---")
for scen in ("full_stack", "bau"):
    d = rows[scen][0] - BASE_COST[scen]
    flag = "OK" if abs(d) < 0.01 else "*** COST MOVED - the carbon price is picking up embodied carbon ***"
    print(f"  {scen:11} {BASE_COST[scen]:>18,.2f} -> {rows[scen][0]:>18,.2f}"
          f"   delta {d:>+12,.2f}  {flag}")

print("\n--- CHECK 2: CO2 rises by exactly the constant ---")
for scen in ("full_stack", "bau"):
    want = BASE_CO2[scen] + const
    got = rows[scen][1]
    d = got - want
    flag = "OK" if abs(d) < 0.01 else "*** LEAKED - it changed the build ***"
    print(f"  {scen:11} {BASE_CO2[scen]:,.2f} + {const:,.2f}")
    print(f"              expected {want:>18,.2f}")
    print(f"              got      {got:>18,.2f}   delta {d:>+12,.2f}  {flag}")

print("\n--- CHECK 3: the headline ---")
f, b = rows["full_stack"][0], rows["bau"][0]
fc, bc = rows["full_stack"][1], rows["bau"][1]
co2_before = 100 * (1 - BASE_CO2["full_stack"] / BASE_CO2["bau"])
co2_after = 100 * (1 - fc / bc)
print(f"  vs-BAU cost  {100 * (1 - f / b):.3f}%  (must be 44.105%, unchanged)")
print(f"  vs-BAU CO2   {co2_before:.3f}% -> {co2_after:.3f}%  "
      f"({co2_after - co2_before:+.3f} pp)")
print(f"  predicted in advance   61.381%")
print(f"  miss vs prediction     {co2_after - 61.381:+.3f} pp")
print(f"\n  {const / 1000:,.1f} tCO2/yr is "
      f"{100 * const / fc:.3f}% of the town and {100 * const / bc:.3f}% of BAU.")
print("  Added for COMPLETENESS. That it does not change the answer is the")
print("  defensible result - the exclusion would have been safe, and now it")
print("  does not have to be argued.")
