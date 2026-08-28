"""CAPACITY-CAP AUDIT - which technology caps BIND, and are they conserved?

WHY THIS EXISTS (, the author: "check for all tech properly, i dont know
how we missed this").

The multi-period LP writes every area-limited PV cap as

    SUM_vintages new_kwp[v]  <=  base_cap * density_mult[p] * land_mult[p]

A 2030-vintage kWp and a 2042-vintage kWp count IDENTICALLY on the left while
the right-hand side grows with BOTH multipliers. That is correct when the LAND
term is what grows - a later, denser vintage really does fit more kWp on newly
released land ("more land x better panels", dispatch.py:2200). It is WRONG
when land is flat, because then the density term re-rates capacity that is
already standing on ground that is already full.

 released the entire 301 ha solar reserve in 2030, which
flattened `solar_farm`'s land multiplier to a constant 1.497512 and left the
density multiplier lifting a cap on a field that fills in year one. The
formulation did not change; the thing it was written for did.

The physically correct form budgets AREA, so each vintage consumes land at its
OWN density and installed capacity cannot be re-rated:

    SUM_vintages new_kwp[v] / density_mult[v]  <=  base_cap * land_mult[p]

The `solar thermal` block (dispatch.py ~2586, `st_roof_share`) already does
exactly this - it inverts rooftop kWp back to m2 and budgets roof AREA - so
both patterns sit in one file, one right and one wrong.

This script does NOT solve. It rebuilds every cap the way the LP builds it,
compares against the capacities the pinned run actually built, and then
re-tests each vintage against the AREA budget to show where the wrong form
handed out capacity that no land exists for.

    PYTHONPATH=. python scripts/capacity_cap_audit.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics
from energy.dispatch import _capacity_caps
from energy.network import (load_optimised_network, phased_land_multipliers)

RESULTS = "outputs/data/energy/dispatch_results.json"
SCENARIO = "full_stack"
PERIODS = (2030, 2042, 2055)

econ = load_economics(force_reload=True)
net = load_optimised_network()
scenario = econ.scenario(SCENARIO)
caps = _capacity_caps(net, econ, scenario)

lm = phased_land_multipliers(getattr(net, "grid", None))
farm_land = {p: float(lm["solar_farm"].get(p, 1.0)) for p in PERIODS}
carport_land = {p: float(lm["carport"].get(p, 1.0)) for p in PERIODS}
one = {p: 1.0 for p in PERIODS}
dens = {p: econ.pv_density_ceiling_multiplier(p) for p in PERIODS}

flag = lambda n: bool(getattr(scenario, n, False))
bipv_cap = net.total_bipv_potential_kwp(econ) if flag("allow_bipv") else 0.0
carport_cap = net.total_carport_potential_kwp(econ) if flag("allow_carport") else 0.0
fpv_cap = net.total_floating_pv_potential_kwp(econ) if flag("allow_floating_pv") else 0.0

with open(RESULTS) as fh:
    doc = json.load(fh)
scen = [s for s in doc["scenarios"] if s.get("name") == SCENARIO][0]
pb = scen["period_breakdown"]

inst = lambda p, k: pb[str(p)]["installed_capacities"].get(k, 0.0)
built = lambda p, k: pb[str(p)]["new_build"].get(k, 0.0)

# name, installed key, new_build key, base cap, land mult, density-scaled?
TECHS = [
    ("rooftop_pv",    "rooftop_pv_kwp",   "rooftop_pv_kwp", caps["rooftop_pv_kwp"], one, True),
    ("solar_farm",    "solar_farm_kwp",   "farm_fixed_kwp", caps["solar_farm_kwp"], farm_land, True),
    ("bipv",          "bipv_kwp",         "bipv_kwp",       bipv_cap,   one,          True),
    ("carport",       "carport_kwp",      "carport_kwp",    carport_cap, carport_land, True),
    ("floating_pv",   "floating_pv_kwp",  "floating_pv_kwp", fpv_cap,   one,          True),
    ("battery",       "battery_kwh",      "battery_kwh",    caps["battery_kwh"], one, False),
    ("biomass",       "biomass_kw_e",     "biomass_kw_e",   caps["biomass_kw_e"], one, False),
    ("wte",           "wte_kw_e",         "wte_kw_e",       caps["wte_kw_e"], one, False),
    ("biogas",        "biogas_kw_e",      "biogas_kw_e",    caps["biogas_kw_e"], one, False),
    ("thermal_store", "thermal_storage_kwh", "thermal_storage_kwh", caps["thermal_storage_kwh"], one, False),
]

print("=" * 100)
print("CAPACITY-CAP AUDIT - scenario %s" % SCENARIO)
print("density mult   " + "  ".join("%d=%.2f" % (p, dens[p]) for p in PERIODS))
print("farm land mult " + "  ".join("%d=%.4f" % (p, farm_land[p]) for p in PERIODS))
print("carport land   " + "  ".join("%d=%.4f" % (p, carport_land[p]) for p in PERIODS))
print("=" * 100)
print()
print("%-14s %10s  %-34s %-34s" % ("tech", "base cap", "installed / cap  (BIND = at limit)", ""))
print("-" * 100)

density_binding = []
for name, ikey, nkey, base, land, is_dens in TECHS:
    cells = []
    any_bind = False
    for p in PERIODS:
        eff = base * (dens[p] if is_dens else 1.0) * land[p]
        got = inst(p, ikey)
        if eff <= 0:
            cells.append("   cap=0    ")
            continue
        frac = got / eff
        bind = frac > 0.9995
        any_bind = any_bind or bind
        cells.append("%9.1f%%%s" % (100 * frac, " BIND" if bind else "     "))
    print("%-14s %10.1f  %s" % (name, base, " ".join(cells)))
    if any_bind and is_dens and base > 0:
        density_binding.append((name, ikey, nkey, base, land))

print()
print("=" * 100)
print("AREA-BUDGET RE-TEST - only for caps that BIND *and* are density-scaled")
print("Correct rule: SUM_v new_kwp[v]/density[v] <= base_cap * land_mult[p]")
print("=" * 100)
if not density_binding:
    print("  none")
for name, ikey, nkey, base, land in density_binding:
    print()
    print("  %s (base %.1f)" % (name, base))
    used = 0.0
    for p in PERIODS:
        add = built(p, nkey)
        used += add / dens[p]              # land this vintage consumes
        budget = base * land[p]
        over = used - budget
        tag = "OVER by %10.1f" % over if over > 1e-6 else "ok"
        print("     %d  new %11.1f kWp  land used %11.1f of %11.1f   %s"
              % (p, add, used, budget, tag))
    # what the correct constraint would have allowed, greedily, same order
    used2 = 0.0
    allowed_total = 0.0
    for p in PERIODS:
        budget = base * land[p]
        want = built(p, nkey)
        room = max(0.0, budget - used2) * dens[p]
        take = min(want, room)
        used2 += take / dens[p]
        allowed_total += take
    actual_total = inst(PERIODS[-1], ikey)
    print("     -> 2055 installed  actual %11.1f   area-correct %11.1f   FREE %10.1f (%.1f%%)"
          % (actual_total, allowed_total, actual_total - allowed_total,
             100.0 * (actual_total - allowed_total) / actual_total if actual_total else 0.0))

print()
print("=" * 100)
print("V2G - rising cap, checked separately (fleet genuinely grows)")
print("=" * 100)
for p in PERIODS:
    cap = net.v2g_units(econ, year=p)
    got = inst(p, "v2g_units")
    print("  %d  installed %10.1f of fleet cap %10.1f = %6.1f%%%s"
          % (p, got, cap, 100 * got / cap if cap else 0.0,
             "  BIND" if cap and got / cap > 0.9995 else ""))
