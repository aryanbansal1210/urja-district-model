"""Sanity-check the derived-PV capex-learning fix.

Between the two diesel proofs the full_stack 2030 ANNUAL cost rose
1,983,943,783 -> 2,027,619,863 (+2.2%) on the sym=False path, whose diesel
code is unchanged. The only behaviour change in between was giving BIPV /
carport / floating PV their parent's learning rate.

MAKING SOMETHING CHEAPER MUST NOT RAISE THE OPTIMUM. The multi-period
objective is the LIFETIME cost, so the 2030 annual cost is free to move either
way as the LP re-times its build - but lifetime_cost MUST fall (or hold).
If it rises, the fix has a bug and the re-pin must not proceed.
"""
from copy import deepcopy

from energy.costs import Economics, load_economics
from energy.dispatch import solve_dispatch_pyomo
from energy.network import load_optimised_network

net = load_optimised_network()
print("network built", flush=True)

REAL = dict(Economics._DERIVED_CAPEX_PARENT)

out = {}
for tag, mapping in (("OLD (bug: no inheritance)", {}), ("NEW (inherits)", REAL)):
    Economics._DERIVED_CAPEX_PARENT = mapping
    e = deepcopy(load_economics(force_reload=True))
    r = solve_dispatch_pyomo(net, e, scenario_name="full_stack", alpha=0.0)
    life = getattr(r, "lifetime_cost_inr", None)
    out[tag] = (r.annual_cost_inr, life, dict(r.capacities or {}))
    print(f"{tag:28} annual {r.annual_cost_inr:>18,.2f}   "
          f"lifetime {life if life is None else f'{life:,.2f}'}", flush=True)

Economics._DERIVED_CAPEX_PARENT = REAL

(a_old, l_old, c_old) = out["OLD (bug: no inheritance)"]
(a_new, l_new, c_new) = out["NEW (inherits)"]
print("\n--- verdict ---")
print(f"annual   2030 {a_old:,.2f} -> {a_new:,.2f}  ({a_new - a_old:+,.2f})")
if l_old and l_new:
    print(f"lifetime      {l_old:,.2f} -> {l_new:,.2f}  ({l_new - l_old:+,.2f})")
    print("LIFETIME FELL - correct" if l_new <= l_old + 1.0
          else "*** LIFETIME ROSE - BUG, DO NOT RE-PIN ***")

print("\n--- capacity shifts ---")
for k in sorted(set(c_old) | set(c_new)):
    a, b = c_old.get(k, 0.0), c_new.get(k, 0.0)
    if abs(b - a) > 1e-6:
        print(f"  {k:26} {a:>14,.1f} -> {b:>14,.1f}  ({b - a:+,.1f})")
