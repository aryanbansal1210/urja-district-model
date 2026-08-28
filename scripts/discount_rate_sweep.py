"""REV-4 / TRJ-6 - inter-period discount-rate sensitivity (the viva-closer).

The production objective uses multi_period.discount_rate_real = 0.0 (a 2055 rupee ==
a 2030 rupee): a documented social-planner stance, but the most examiner-attackable
objective parameter (it favours late-horizon builds, incl. the 2055 battery). This
sweep re-solves full_stack alpha=0 at r in {0.0, 0.03, 0.05, 0.065} real and reports how the
headline + the battery story move. Clone-econ; production files untouched.

Run: python scripts/discount_rate_sweep.py   (~10 min: 3 multi-period solves)
Writes: outputs/data/energy/discount_rate_sweep.md
"""
from __future__ import annotations
import os, sys, time
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
from energy.costs import load_economics
from energy.network import load_optimised_network
from energy.dispatch import solve_dispatch

# (DISC-1 /: 0.065 added = the utility-tier real rate
# (CERC 8.77% nominal deflated), so the sweep brackets the model's own cost
# of capital. The question it must now answer: does 'build all 301 ha in
# 2030' survive discounting, or was it a 0%-rate artifact?
RATES = [0.0, 0.03, 0.05, 0.065]
NET = load_optimised_network()

def batt(r):
    pb = getattr(r, "period_breakdown", {}) or {}
    return {int(y): float((d.get("installed_capacities", {}) or {}).get("battery_kwh", 0) or 0)
            for y, d in pb.items()}

rows = []
for rate in RATES:
    t = time.time()
    e = deepcopy(load_economics(force_reload=True))
    raw = dict(e.__dict__.get("multi_period_raw", {}) or {})
    raw["discount_rate_real"] = float(rate)
    e.__dict__["multi_period_raw"] = raw
    r = solve_dispatch(NET, e, "full_stack", alpha=0.0)
    b = batt(r)
    rows.append((rate, r.annual_cost_inr, r.annual_emissions_kgco2, r.lifetime_cost_inr,
                 b.get(2030, 0), b.get(2042, 0), b.get(2055, 0)))
    print(f"  r={rate:.2f}: cost {r.annual_cost_inr/1e6:,.1f} M | lifetime {r.lifetime_cost_inr/1e9:.2f} B | "
          f"battery {b.get(2030,0)/1e3:.0f}/{b.get(2042,0)/1e3:.0f}/{b.get(2055,0)/1e3:.0f} MWh "
          f"({time.time()-t:.0f}s)", flush=True)

base = rows[0]
with open("outputs/data/energy/discount_rate_sweep.md", "w", encoding="utf-8") as f:
    f.write("# REV-4 / TRJ-6 - inter-period discount-rate sensitivity (full_stack a=0)\n\n")
    f.write("Base case r = 0.0 (documented social-planner stance). Clone-econ sweep; production untouched.\n\n")
    f.write("| r (real) | 2030 annual cost M | lifetime B | battery 2030 MWh | 2042 | 2055 |\n")
    f.write("|---:|---:|---:|---:|---:|---:|\n")
    for rate, c, em, lc, b30, b42, b55 in rows:
        f.write(f"| {rate:.2f} | {c/1e6:,.1f} | {lc/1e9:.2f} | {b30/1e3:.0f} | {b42/1e3:.0f} | {b55/1e3:.0f} |\n")
    f.write("\n**Reading.** The 2030 annual headline is r-invariant by construction (same-year term); the\n")
    f.write("LIFETIME cost and the late-period battery build are what move. If the 2055 battery shrinks or\n")
    f.write("vanishes at r=3-5%, state in the thesis that storage entry is additionally contingent on the\n")
    f.write("social discount stance - which strengthens, not weakens, the switching-point narrative (F28/B1).\n")
print("wrote outputs/data/energy/discount_rate_sweep.md")
