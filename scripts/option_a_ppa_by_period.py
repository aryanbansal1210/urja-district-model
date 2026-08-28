"""OPTION A: how much can the town actually sell the data centre, per period?

the author, "check over the three periods how much energy we can supply
to the data centre with this new option A. we have to account for module
degradation too."

WHAT OPTION A IS. The whole reserved farm land (295 ha, after the 6-cell
100 m buffer) is released in 2030 instead of phased 200/250/300. That
restores the 2030 capacity lost to the land-density correction, but maxes the
farm out immediately - so capacity thereafter grows only by the TRJ-1 density
multiplier (~+15% by 2055) while demand grows +43%.

THE QUESTION THIS ANSWERS: does the PPA survive that squeeze, or does the
data centre starve in 2055?

DEGRADATION IS INCLUDED and is not an afterthought: the LP applies
`pv_vintage_yield_factor` per build vintage, so a panel built in 2030 is
delivering less by 2055 (rooftop/farm degradation 1.2%/yr, Dubey et al. 2017,
n=1,148 India field study). Under Option A almost the ENTIRE farm is a 2030
vintage, so by 2055 it carries ~25 years of degradation - which is exactly why
Option A needs checking rather than assuming.

Run from district_v3:
    PYTHONPATH=. python -u scripts/option_a_ppa_by_period.py
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics                    # noqa: E402
from energy.dispatch import solve_dispatch_pyomo           # noqa: E402
from energy.network import load_optimised_network          # noqa: E402

net = load_optimised_network()
print("network built\n", flush=True)

econ = deepcopy(load_economics(force_reload=True))
econ.set_ppa_enabled(True)
r = solve_dispatch_pyomo(net, econ, scenario_name="full_stack", alpha=0.0)

CAP_MW = sum(float(sp.get("offtake_kw_constant", 0.0))
             for sp in econ.ppa_active_counterparties().values()) / 1000.0
contract = CAP_MW * 1000.0 * 8760.0

print("=" * 74)
print(f"OPTION A - PPA DELIVERY BY PERIOD   (contract {CAP_MW:,.0f} MW flat "
      f"= {contract / 1e6:,.1f} GWh/yr)")
print("=" * 74)
print(f"{'period':>8}{'demand GWh':>13}{'farm kWp':>12}{'PV gen GWh':>13}"
      f"{'PPA GWh':>10}{'cover %':>9}{'export GWh':>12}")

pb = r.period_breakdown or {}
rows = []
for y in sorted(pb):
    d = pb[y]
    ic = d.get("installed_capacities") or {}
    dem = float(d.get("annual_demand_kwh", 0.0)) / 1e6
    farm = float(ic.get("solar_farm_kwp", 0.0))
    pv = float(d.get("pv_generation_kwh", 0.0)) / 1e6
    ppa = float(d.get("dc_ppa_kwh", 0.0)) / 1e6
    exp = float(d.get("grid_export_kwh", 0.0)) / 1e6
    cov = 100.0 * (ppa * 1e6) / contract if contract else 0.0
    rows.append((y, dem, farm, pv, ppa, cov, exp))
    print(f"{y:>8}{dem:>13,.1f}{farm:>12,.0f}{pv:>13,.1f}{ppa:>10,.1f}"
          f"{cov:>9,.1f}{exp:>12,.1f}")

if len(rows) >= 2:
    a, z = rows[0], rows[-1]
    print("\n--- THE SQUEEZE, measured ---")
    print(f"  demand      {a[1]:>8,.1f} -> {z[1]:>8,.1f} GWh   "
          f"({100 * (z[1] / a[1] - 1):+.1f}%)")
    print(f"  farm kWp    {a[2]:>8,.0f} -> {z[2]:>8,.0f}       "
          f"({100 * (z[2] / a[2] - 1):+.1f}%)")
    print(f"  PV gen      {a[3]:>8,.1f} -> {z[3]:>8,.1f} GWh   "
          f"({100 * (z[3] / a[3] - 1):+.1f}%)"
          "   <- capacity x degradation")
    print(f"  PPA sold    {a[4]:>8,.1f} -> {z[4]:>8,.1f} GWh   "
          f"({100 * (z[4] / a[4] - 1) if a[4] else 0:+.1f}%)")
    print(f"  coverage    {a[5]:>8,.1f}% -> {z[5]:>8,.1f}% of a flat "
          f"{CAP_MW:,.0f} MW contract")
    print("\n  NOTE the PV-gen change is capacity AND degradation together.")
    print("  Under Option A nearly the whole farm is a 2030 vintage, so by")
    print("  2055 it is carrying ~25 years of 1.2%/yr degradation. That is")
    print("  the cost of spending the land early, and it is in these numbers.")
    print("\n  For the counterparty story: India's RPO obligation rises to")
    print("  43.33% by FY2029-30. Coverage above that means one contract with")
    print("  this town still discharges the buyer's whole statutory quota.")

print(f"\nbase-year headline  cost {r.annual_cost_inr:,.2f}  "
      f"CO2 {r.annual_emissions_kgco2:,.2f}")
print(f"lifetime            {r.lifetime_cost_inr:,.2f}")
