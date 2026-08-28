""" LIVENESS PROBE.

One question: after the fix batch - and in particular, which added
+64 GWh of PV and so raises the value of storage - does the LP still build
the battery in 2055 only?

If yes, stays latent and the vintage fix costs nothing.
If the battery now enters at 2042, was about to become live and fixing
it was necessary rather than precautionary.

ONE multi-period solve. Also prints the headline, which is an early read on
where the fix batch has landed - NOT a pin. The pins come from the re-pin
chain after the code review.
"""
from __future__ import annotations
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics                    # noqa: E402
from energy.network import load_optimised_network          # noqa: E402
from energy.dispatch import solve_dispatch_pyomo           # noqa: E402

OUT = os.path.join(ROOT, "outputs", "verification",
                   "pae4_battery_vintage_probe_20260807.txt")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
log = open(OUT, "w", encoding="utf-8")


def emit(s):
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


t0 = time.time()
emit("PA-E4 battery-vintage liveness probe  %s" % time.strftime("%F %H:%M"))
emit("branch fix/param-audit-2026-08-06, after Tier 1 complete")
emit("")

net = load_optimised_network()
econ = load_economics(force_reload=True)
emit("district demand   %.2f GWh" % (
    sum(net.demand_by_slice_kwh(econ).values()) / 1e6))
emit("solving multi-period full_stack alpha=0 ...")

r = solve_dispatch_pyomo(net, econ, "full_stack", alpha=0.0)
caps = r.capacities or {}
emit("")
emit("=== HEADLINE (early read, NOT a pin) ===")
emit("  annual_cost_inr        = {:,.2f}".format(r.annual_cost_inr))
emit("  annual_emissions_kgco2 = {:,.2f}".format(r.annual_emissions_kgco2))
emit("  lifetime_cost_inr      = {:,.2f}".format(r.lifetime_cost_inr))
emit("  rooftop_pv_kwp         = {:,.1f}".format(caps.get("rooftop_pv_kwp", 0)))
emit("  solar_farm_kwp         = {:,.1f}".format(caps.get("solar_farm_kwp", 0)))
emit("  battery_kwh            = {:,.1f}".format(caps.get("battery_kwh", 0)))
emit("")
emit("=== THE PA-E4 QUESTION: which period builds the battery? ===")
pb = r.period_breakdown or {}
built_early = False
for y in sorted(pb):
    ic = (pb[y] or {}).get("installed_capacities") or {}
    nb = (pb[y] or {}).get("new_build") or {}
    new_batt = float(nb.get("battery_kwh", 0) or 0)
    emit("  {}: battery installed {:>12,.0f} kWh | NEW this period {:>12,.0f} kWh"
         .format(y, float(ic.get("battery_kwh", 0) or 0), new_batt))
    if new_batt > 1.0 and int(y) < 2055:
        built_early = True
emit("")
if built_early:
    emit("  *** PA-E4 IS LIVE. The battery now enters before 2055, so the")
    emit("  *** vintage-ageing defect would have bitten. Fixing it was")
    emit("  *** NECESSARY, not precautionary.")
else:
    emit("  PA-E4 STAYS LATENT. Battery is still 2055-only, so the sole")
    emit("  vintage is evaluated in its own build year at a factor of exactly")
    emit("  1.0000 and the fix costs nothing. It remains correct, and it")
    emit("  removes the risk permanently.")
emit("")
emit("elapsed %.0f s" % (time.time() - t0))
log.close()
