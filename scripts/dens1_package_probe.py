"""THE BATCH PACKAGE, measured before the ballot: + + GCR.

One solve per configuration:

  P0 - pins reproduction (all flags legacy). Regression gate.
  P1 - option B alone      (area budget + density mults 1.0)
  P2 - P1 + pair           (the corrected roof competition)
  P3 - P2 + farm density GCR 0.34 -> 0.382 (4.0 ac/MWac; NREL Ong 2013
       scaled to 21% modules = 3.9; bottom of the Indian 4-5 band; derived
       inter-row loss 0.021% - gcr_interrow_sweep_20260820.txt)

P1 is known from the options probe (2030 byte-exact); it runs again here so
every delta in the table is same-harness, same-machine, no cross-run doubt.
Farm density scales node.solar_farm_cap_kwp AFTER the network build - the
land (301 ha), rent, and phased multipliers are untouched; only kWp-per-m2
moves. BAU is not solved: no PV, no roof, no farm - the pinned comparator
stands for every row.

    PYTHONPATH=. python scripts/dens1_package_probe.py
"""
from copy import deepcopy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics
from energy.dispatch import solve_dispatch_pyomo
from energy.network import load_optimised_network

PIN = (1_841_569_555.79, 116_638_892.44, 63_247_015_703.14)
BAU_ANNUAL, BAU_CO2 = 3_643_546_228.06, 311_116_477.55
GCR_SCALE = 0.382 / 0.34          # density ratio; = (0.21*GCR) ratio exactly

KEYS = ("rooftop_pv_kwp", "solar_farm_kwp", "carport_kwp", "floating_pv_kwp",
        "battery_kwh", "solar_thermal_m2")


def econ_for(dens_b: bool, roof_pair: bool):
    e = deepcopy(load_economics(force_reload=True))
    mp = dict(e.__dict__.get("multi_period_raw", {}) or {})
    if dens_b:
        mp["pv_density_area_budget"] = True
        mp["pv_density_ceiling_multiplier_by_period"] = {
            2030: 1.0, 2042: 1.0, 2055: 1.0}
    e.__dict__["multi_period_raw"] = mp
    if roof_pair:
        techs = dict(e.technologies or {})
        st = dict(techs.get("solar_thermal", {}) or {})
        st["roof_pair_constraint"] = True
        techs["solar_thermal"] = st
        e.technologies = techs
    return e


net = load_optimised_network()
print("network built; farm cap %.1f kWp" % net.total_solar_farm_cap_kwp(),
      flush=True)

CASES = [
    ("P0_pins",      dict(dens_b=False, roof_pair=False), 1.0),
    ("P1_densB",     dict(dens_b=True,  roof_pair=False), 1.0),
    ("P2_+roofpair", dict(dens_b=True,  roof_pair=True),  1.0),
    ("P3_+gcr0.382", dict(dens_b=True,  roof_pair=True),  GCR_SCALE),
]

results = {}
farm_base = {id(n): n.solar_farm_cap_kwp for n in net.nodes}
for tag, kw, scale in CASES:
    for n in net.nodes:
        n.solar_farm_cap_kwp = farm_base[id(n)] * scale
    # the network memoises yields/caps per econ identity; a fresh econ per
    # case keeps every cache honest
    e = econ_for(**kw)
    r = solve_dispatch_pyomo(net, e, scenario_name="full_stack", alpha=0.0)
    results[tag] = r
    print("%-14s annual %.2f  CO2 %.2f  lifetime %.2f"
          % (tag, r.annual_cost_inr, r.annual_emissions_kgco2,
             r.lifetime_cost_inr), flush=True)
for n in net.nodes:
    n.solar_farm_cap_kwp = farm_base[id(n)]

p0 = results["P0_pins"]
print("\n--- gate: P0 reproduces the 2026-08-19 pins ---")
ok = True
for name, got, want in (("annual", p0.annual_cost_inr, PIN[0]),
                        ("CO2", p0.annual_emissions_kgco2, PIN[1]),
                        ("lifetime", p0.lifetime_cost_inr, PIN[2])):
    good = abs(got - want) < 0.01
    ok &= good
    print("  %-8s %20.2f  delta %10.4f  %s"
          % (name, got, got - want, "OK" if good else "FAIL"))

print("\n--- headline ladder (annual = the 2030 period, the thesis number) ---")
print("%-14s %16s %14s %10s %10s" %
      ("case", "annual INR", "CO2 kg", "vs-BAU c", "vs-BAU e"))
for tag, _, _ in CASES:
    r = results[tag]
    print("%-14s %16.2f %14.2f %9.4f%% %9.4f%%"
          % (tag, r.annual_cost_inr, r.annual_emissions_kgco2,
             100 * (1 - r.annual_cost_inr / BAU_ANNUAL),
             100 * (1 - r.annual_emissions_kgco2 / BAU_CO2)))

print("\n--- per-period installed, P0 vs P3 ---")
pb0 = p0.period_breakdown
pb3 = results["P3_+gcr0.382"].period_breakdown
for p in sorted(pb0):
    for k in KEYS:
        a = float(pb0[p]["installed_capacities"].get(k, 0.0))
        b = float(pb3[p]["installed_capacities"].get(k, 0.0))
        if a or b:
            print("  %d %-18s P0 %14.1f   P3 %14.1f   %+12.1f"
                  % (p, k, a, b, b - a))
    print("  %d exports %.1f -> %.1f GWh, imports %.1f -> %.1f GWh"
          % (p, float(pb0[p]["grid_export_kwh"]) / 1e6,
             float(pb3[p]["grid_export_kwh"]) / 1e6,
             float(pb0[p]["grid_import_kwh"]) / 1e6,
             float(pb3[p]["grid_import_kwh"]) / 1e6))

print("\nGATE:", "PASS" if ok else "FAIL - do not trust the ladder")
sys.exit(0 if ok else 1)
