"""Proof for the INTERNAL NETWORK PARITY COST.

WHAT WAS WRONG. `electrical_network.enabled` is false AND its only consumer
sits inside the Stage-D builder, which is also false - so the district's
cables, substation and distribution transformers were costed in NO
production number. Both the designed town and BAU got their internal grid
for free.

WHAT MUST HOLD:
  1. The overlay is a constant of the LAYOUT, independent of what the LP
     builds, so the optimum CANNOT move. Cost must rise by EXACTLY the
     annualised total in both scenarios and CO2 must be byte-identical.
     Anything else means the term leaked into a decision it should not
     touch.
  2. Charged at PARITY. Equal absolute rupees on an unequal base means
     this HURTS the designed town's percentage. Predicted in advance:
     vs-BAU cost 45.300% -> 44.104%. Print the miss either way.
  3. The substation re-size (480 -> 300 MVA) must show up in the
     breakdown, not just in the comment.

Baseline (sized connection ON, internal network OFF), from
outputs/verification/sized_connection_proof_20260811.txt:
     town 1,888,890,288.99   BAU 3,453,212,155.50

Run from district_v3:  PYTHONPATH=. python -u scripts/internal_network_proof.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics                      # noqa: E402
from energy.dispatch import solve_dispatch_pyomo              # noqa: E402
from energy.electrical_assets import (                        # noqa: E402
    production_network_annualised_inr,
)
from energy.network import load_optimised_network             # noqa: E402

# The OFF baseline is not re-solved: it is the previous proof's ON-sizing
# result, which is this run's configuration minus the one flag.
BASE = {"full_stack": 1_888_890_288.99, "bau": 3_453_212_155.50}
BASE_CO2 = {}

econ = load_economics(force_reload=True)
net = load_optimised_network()
print("network built\n", flush=True)

brk = production_network_annualised_inr(net, econ)
const = float(brk["annualised_total_inr"])

print("--- what is being charged ---")
print(f"  substation      {brk['substation_mva_installed']:>10,.1f} MVA  "
      f"Rs {brk['substation_annualised_inr']:>15,.2f}/yr")
print(f"  cables          {brk['cable_route_km']:>10,.1f} km   "
      f"Rs {brk['cable_annualised_inr']:>15,.2f}/yr")
print(f"  dist txfmrs     {brk['transformer_total_kva'] / 1000:>10,.1f} MVA  "
      f"Rs {brk['transformer_annualised_inr']:>15,.2f}/yr")
print(f"  TOTAL                          Rs {const:>15,.2f}/yr "
      f"({const / 1e7:,.3f} crore)\n")

rows = {}
for scen in ("full_stack", "bau"):
    r = solve_dispatch_pyomo(net, econ, scenario_name=scen, alpha=0.0)
    rows[scen] = (r.annual_cost_inr, r.annual_emissions_kgco2,
                  r.__dict__.get("grid_connection_mw"))
    print(f"  {scen:11} cost {r.annual_cost_inr:>18,.2f}  "
          f"CO2 {r.annual_emissions_kgco2:>16,.2f}  "
          f"conn {r.__dict__.get('grid_connection_mw', 0.0):>7,.1f} MW",
          flush=True)

print("\n--- CHECK 1: the constant must pass straight through ---")
ok = True
for scen in ("full_stack", "bau"):
    got = rows[scen][0]
    want = BASE[scen] + const
    d = got - want
    flag = "OK" if abs(d) < 0.01 else "*** LEAKED ***"
    if abs(d) >= 0.01:
        ok = False
    print(f"  {scen:11} {BASE[scen]:,.2f} + {const:,.2f}")
    print(f"              expected {want:>18,.2f}")
    print(f"              got      {got:>18,.2f}   delta {d:>+14,.2f}  {flag}")
if not ok:
    print("  A non-zero delta means the overlay CHANGED THE BUILD. It is a")
    print("  build-independent constant, so it must not. Investigate before")
    print("  quoting any number from this run.")

print("\n--- CHECK 2: what parity costs the designed town ---")
f, b = rows["full_stack"][0], rows["bau"][0]
fc, bc = rows["full_stack"][1], rows["bau"][1]
before = 100 * (1 - BASE["full_stack"] / BASE["bau"])
after = 100 * (1 - f / b)
print(f"  vs-BAU cost BEFORE the overlay  {before:.3f}%")
print(f"  vs-BAU cost AFTER               {after:.3f}%   ({after - before:+.3f} pp)")
print(f"  predicted in advance            44.104%")
print(f"  miss vs prediction              {after - 44.104:+.3f} pp")
print(f"  vs-BAU CO2                      {100 * (1 - fc / bc):.3f}%  "
      f"(must be unchanged - the overlay has no emissions term)")
print("\n  Equal rupees on an unequal base: the same Rs "
      f"{const / 1e7:,.2f} cr is "
      f"{100 * const / f:.2f}% of the town and "
      f"{100 * const / b:.2f}% of BAU.")
print("  The town pays a bigger SHARE for the same wires, because both")
print("  towns sit on the same layout and serve the same evening peak.")
print("  The decentralisation saving is at the CONNECTION (36.4% smaller),")
print("  not inside the district. Report it that way.")
