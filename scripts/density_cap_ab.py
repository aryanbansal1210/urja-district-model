""" A/B: legacy density-ceiling caps vs the area-budget form.

Two production multi-period solves of full_stack, identical in everything
except `multi_period.pv_density_area_budget`:

  OFF - the legacy form. MUST reproduce the pins to the paisa
        (annual 1,841,569,555.79 / CO2 116,638,892.44 / lifetime
        63,247,015,703.14). This is also the end-to-end proof that the
 shading cache changes nothing downstream: same solve, cache
        in the loop, same bytes out.
  ON  - the area-budget form:  sum_v new[v]/dens[v] <= base * land[p].
        2030 must be IDENTICAL (dens[2030]=1.0); only 2042/2055 builds and
        the lifetime figure may move.

ADVANCE PREDICTION (written before the run, convention):
  farm installed goes 214,914.0 / 236,405.4 / 247,151.1
                   -> 214,914.0 / 214,914.0 / 214,914.0  (flat, land-bound)
  floating goes 0 / 17,853.0 / 18,664.5 -> 0 / 17,853.0 / 17,853.0
  carport 2055 loses its 575-kWp re-rating; 2042 fill unchanged
  2030 row of the period breakdown byte-identical to the pins
  lifetime cost RISES (less free PV late in the horizon); annual 2030 flat.

BAU is not solved: it builds no PV, so the flag cannot touch it - the pinned
BAU stays the comparator.

    PYTHONPATH=. python scripts/density_cap_ab.py
"""
from copy import deepcopy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics
from energy.dispatch import solve_dispatch_pyomo
from energy.network import load_optimised_network

PIN_ANNUAL = 1_841_569_555.79
PIN_CO2 = 116_638_892.44
PIN_LIFETIME = 63_247_015_703.14

# new_build uses farm_fixed/farm_tracked; installed_capacities uses the
# combined solar_farm_kwp - carry all of them, absent keys read as 0.
PV_KEYS = ("rooftop_pv_kwp", "solar_farm_kwp", "farm_fixed_kwp",
           "farm_tracked_kwp", "carport_kwp", "floating_pv_kwp", "bipv_kwp",
           "battery_kwh", "solar_thermal_m2")


def econ_with(area_budget: bool):
    e = deepcopy(load_economics(force_reload=True))
    mp = dict(e.__dict__.get("multi_period_raw", {}) or {})
    mp["pv_density_area_budget"] = bool(area_budget)
    e.__dict__["multi_period_raw"] = mp
    assert e.pv_density_area_budget() == bool(area_budget)
    return e


net = load_optimised_network()
print("network built", flush=True)

out = {}
for flag in (False, True):
    e = econ_with(flag)
    r = solve_dispatch_pyomo(net, e, scenario_name="full_stack", alpha=0.0)
    out[flag] = r
    print("area_budget=%-5s annual %.2f  CO2 %.2f  lifetime %.2f"
          % (flag, r.annual_cost_inr, r.annual_emissions_kgco2,
             r.lifetime_cost_inr), flush=True)

off, on = out[False], out[True]

print("\n--- gate 1: OFF reproduces the 2026-08-19 pins ---")
ok = True
for name, got, want in (("annual", off.annual_cost_inr, PIN_ANNUAL),
                        ("CO2", off.annual_emissions_kgco2, PIN_CO2),
                        ("lifetime", off.lifetime_cost_inr, PIN_LIFETIME)):
    d = got - want
    good = abs(d) < 0.01
    ok &= good
    print("  %-8s got %20.2f  pin %20.2f  delta %12.4f  %s"
          % (name, got, want, d, "OK" if good else "FAIL"))
print("  gate 1:", "PASS - cache + refactor are byte-clean" if ok
      else "FAIL - DO NOT TRUST THE A/B, find the regression first")

print("\n--- gate 2: ON leaves 2030 untouched ---")
pb_off, pb_on = off.period_breakdown, on.period_breakdown
p0 = sorted(pb_off)[0]
g2 = True
for k in ("annual_cost_inr", "annual_emissions_kgco2"):
    a, b = float(pb_off[p0][k]), float(pb_on[p0][k])
    good = abs(a - b) < 0.01
    g2 &= good
    print("  2030 %-24s OFF %20.2f  ON %20.2f  %s"
          % (k, a, b, "OK" if good else "FAIL"))
for k in PV_KEYS:
    a = float(pb_off[p0]["new_build"].get(k, 0.0))
    b = float(pb_on[p0]["new_build"].get(k, 0.0))
    good = abs(a - b) < 1e-6
    g2 &= good
    print("  2030 new %-20s OFF %20.1f  ON %20.1f  %s"
          % (k, a, b, "OK" if good else "FAIL"))
print("  gate 2:", "PASS" if g2 else "FAIL")

print("\n--- the A/B itself ---")
print("  %-10s %22s %22s %16s" % ("", "OFF (legacy)", "ON (area)", "delta"))
for name, a, b in (
    ("annual", off.annual_cost_inr, on.annual_cost_inr),
    ("CO2", off.annual_emissions_kgco2, on.annual_emissions_kgco2),
    ("lifetime", off.lifetime_cost_inr, on.lifetime_cost_inr),
):
    print("  %-10s %22.2f %22.2f %16.2f" % (name, a, b, b - a))

print("\n  per-period installed capacities:")
for p in sorted(pb_off):
    for k in PV_KEYS:
        a = float(pb_off[p]["installed_capacities"].get(k, 0.0))
        b = float(pb_on[p]["installed_capacities"].get(k, 0.0))
        if abs(a - b) > 1e-6 or a or b:
            print("    %d %-20s OFF %14.1f   ON %14.1f   %+12.1f"
                  % (p, k, a, b, b - a))
    for k in ("grid_import_kwh", "grid_export_kwh"):
        a, b = float(pb_off[p][k]), float(pb_on[p][k])
        print("    %d %-20s OFF %14.0f   ON %14.0f   %+12.0f"
              % (p, k, a, b, b - a))

print("\nVERDICT: %s" % ("gates PASS - A/B numbers are trustworthy"
                          if (ok and g2) else "A GATE FAILED - investigate"))
sys.exit(0 if (ok and g2) else 1)
