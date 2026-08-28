"""Proof for the SIZED GRID CONNECTION.

Solves full_stack and bau with `interconnection.sizing` OFF and ON.

WHAT MUST HOLD:
  1. OFF reproduces the pre-change numbers byte-exactly (the B21 pattern).
  2. ON, the connection sizes to each scenario's own PEAK import, and the
     charge is annualised_inr_per_mw x that size. At the full 600 MW basis
     the two are identical by construction, so any difference IS the
     decentralisation saving.
  3. BAU should size LARGER than the designed town. If it does not, the
     town's peak is as bad as BAU's and the infrastructure claim fails -
     which is a real finding, not a bug. Print it either way.

Run from district_v3:  PYTHONPATH=. python -u scripts/sized_connection_proof.py
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics            # noqa: E402
from energy.dispatch import solve_dispatch_pyomo    # noqa: E402
from energy.network import load_optimised_network   # noqa: E402


def econ_with(sizing: bool):
    e = deepcopy(load_economics(force_reload=True))
    ic = dict(e.__dict__.get("interconnection_raw", {}) or {})
    blk = dict(ic.get("sizing") or {})
    blk["enabled"] = bool(sizing)
    ic["sizing"] = blk
    e.__dict__["interconnection_raw"] = ic
    return e


net = load_optimised_network()
print("network built\n", flush=True)

rows = {}
for sizing in (False, True):
    for scen in ("full_stack", "bau"):
        e = econ_with(sizing)
        r = solve_dispatch_pyomo(net, e, scenario_name=scen, alpha=0.0)
        mw = r.__dict__.get("grid_connection_mw")
        rows[(sizing, scen)] = (r.annual_cost_inr, r.annual_emissions_kgco2, mw)
        print(f"  sizing={sizing!s:5} {scen:11} "
              f"cost {r.annual_cost_inr:>18,.2f}  "
              f"conn {'n/a' if mw is None else f'{mw:>8,.1f} MW'}", flush=True)

e_on = econ_with(True)
per_mw = e_on.interconnection_annualised_inr_per_mw()
flat = e_on.interconnection_annualised_inr()

print("\n--- verification ---")
print(f"flat charge            Rs {flat:,.2f}/yr for {e_on.interconnection_design_basis_mw():.0f} MW")
print(f"per-MW rate            Rs {per_mw:,.2f}/MW/yr")
print(f"equivalence at basis   Rs {per_mw * 600:,.2f}  (must equal the flat charge)")

for scen in ("full_stack", "bau"):
    off = rows[(False, scen)][0]
    on, _, mw = rows[(True, scen)]
    if mw is not None:
        print(f"\n{scen}:")
        print(f"  sized connection     {mw:,.1f} MW  "
              f"({100 * mw / 600:.1f}% of the 600 MW basis)")
        print(f"  connection charge    Rs {per_mw * mw:,.2f}/yr "
              f"(flat was Rs {flat:,.2f})")
        print(f"  saving vs flat       Rs {flat - per_mw * mw:,.2f}/yr")
        print(f"  total cost           {off:,.2f} -> {on:,.2f}")

mw_t = rows[(True, "full_stack")][2]
mw_b = rows[(True, "bau")][2]
if mw_t is not None and mw_b is not None:
    print(f"\n*** THE INFRASTRUCTURE CLAIM ***")
    print(f"  town needs {mw_t:,.1f} MW, BAU needs {mw_b:,.1f} MW")
    if mw_b > mw_t:
        print(f"  town connection is {100 * (1 - mw_t / mw_b):.1f}% SMALLER - "
              f"worth Rs {per_mw * (mw_b - mw_t):,.0f}/yr")
    else:
        print("  *** TOWN IS NOT SMALLER. The evening peak is as bad as "
              "BAU's - the decentralisation benefit is on ENERGY, not "
              "infrastructure. Report this, do not bury it. ***")

for tag, k in (("OFF", False), ("ON ", True)):
    b = rows[(k, "bau")][0]
    f = rows[(k, "full_stack")][0]
    bc = rows[(k, "bau")][1]
    fc = rows[(k, "full_stack")][1]
    print(f"vs-BAU {tag}: cost {100 * (1 - f / b):.3f}%   "
          f"CO2 {100 * (1 - fc / bc):.3f}%")
