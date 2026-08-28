"""Re-discover the B21 forced-off anchor on the-run-2 layout.

The provenance anchor (tests/test_b21_regional.test_off_is_byte_exact) proves
the B21 blocks alone separate the baseline from its pre-B21 counterfactual.
The anneal re-baselined the LAYOUT (+ streetlight class weights), so the
forced-off value moves too - one solve pins it fresh.
"""
from __future__ import annotations
import sys, time
from copy import deepcopy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from energy import load_optimised_network
from energy.costs import load_economics
from energy.dispatch import solve_dispatch_pyomo
from tests.test_b21_regional import _force_b21_off

t0 = time.time()
e = deepcopy(load_economics(force_reload=True))
e.set_ppa_enabled(False)
_force_b21_off(e)
net = load_optimised_network()
r = solve_dispatch_pyomo(net, e, scenario_name="full_stack", alpha=0.0)
print(f"[{time.time()-t0:.0f}s] FORCED-OFF multi anchor (F6 run 2 layout + streetlight weights):")
print(f"  annual_cost_inr     : {r.annual_cost_inr:,.2f}")
print(f"  annual_emissions_kg : {r.annual_emissions_kgco2:,.2f}")
print(f"  green_purchase_kwh  : {r.__dict__.get('green_purchase_kwh', 0.0)}")
