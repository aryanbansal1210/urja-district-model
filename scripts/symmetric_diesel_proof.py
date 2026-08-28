"""SYMMETRIC DIESEL provenance check.

Solves the production multi-period LP twice - flag ON and forced OFF - for
both full_stack and BAU, and verifies the arithmetic claimed in
economics.yaml: BOTH scenarios must rise by the SAME constant
diesel_inr x critical_outage_energy, so the absolute saving is unchanged
and only the vs-BAU ratio moves.

Run from the district_v3 root with PYTHONPATH=.
"""
from copy import deepcopy

from energy.costs import load_economics
from energy.dispatch import solve_dispatch_pyomo
from energy.network import load_optimised_network


def econ_with(flag: bool):
    e = deepcopy(load_economics(force_reload=True))
    rel = dict(e.__dict__.get("reliability_raw", {}) or {})
    rel["symmetric_diesel_backup"] = {"enabled": flag}
    e.__dict__["reliability_raw"] = rel
    return e


net = load_optimised_network()
print("network built", flush=True)

out = {}
for flag in (False, True):
    for scen in ("full_stack", "bau"):
        e = econ_with(flag)
        r = solve_dispatch_pyomo(net, e, scenario_name=scen, alpha=0.0)
        out[(flag, scen)] = (r.annual_cost_inr, r.annual_emissions_kgco2)
        print(f"  sym={flag!s:5} {scen:11} cost {r.annual_cost_inr:,.2f} "
              f"CO2 {r.annual_emissions_kgco2:,.2f}", flush=True)

e_on = econ_with(True)
demand = sum(net.demand_by_slice_kwh(e_on).values())
crit = e_on.critical_outage_energy_kwh(demand)
expected = crit * e_on.diesel_displacement_value_inr_per_kwh()

print("\n--- verification ---")
print(f"annual demand              {demand:,.0f} kWh")
print(f"critical outage energy E   {crit:,.0f} kWh")
print(f"expected uplift diesel x E {expected:,.2f} INR")
for scen in ("full_stack", "bau"):
    d = out[(True, scen)][0] - out[(False, scen)][0]
    print(f"actual uplift {scen:11}   {d:,.2f} INR")

off_gap = out[(False, "bau")][0] - out[(False, "full_stack")][0]
on_gap = out[(True, "bau")][0] - out[(True, "full_stack")][0]
print(f"\nabsolute saving OFF        {off_gap:,.2f}")
print(f"absolute saving ON         {on_gap:,.2f}")
print(f"difference (want ~0)       {on_gap - off_gap:,.2f}")

for tag, k in (("OFF", False), ("ON ", True)):
    b = out[(k, "bau")][0]
    f = out[(k, "full_stack")][0]
    print(f"vs-BAU {tag}: {100.0 * (1 - f / b):.3f}%")
