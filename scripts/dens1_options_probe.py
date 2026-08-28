""" decision probes: what does the corrected (area-budget) model do
under each candidate convention?

The A/B (density_cap_ab.py, dens1_ab_20260820.txt) showed the area form is
right about land but EXPOSES a second issue: with zero inter-period
discounting + capex learning + denser later vintages, the LP DEFERS 44% of
the farm to 2042 to harvest 1.10x density on the same hectares (2030 build
120,154 kWp, exports collapse, 2030 annual +Rs 228.0 M). Physically legal,
economically strange - no developer leaves permitted land empty 12 years for
a 4.4% capacity gain. That deferral is priced at the 0% inter-period rate the
DISC-1 caveat already flags as contentious.

Two probes, both with the area budget ON:

  B - density multipliers forced to 1.0 (kill TRJ-1). A kWp is a kWp;
      deferral buys only cheaper capex, not extra capacity.
  C - discount_rate_real = 0.065 between periods (CERC 8.77% nominal
      deflated - the same real rate the farm's own capex annuity uses).
      Future operational gains are discounted, so the deferral trade is
      priced the way a developer prices it.

Expected: both rebuild the full 214,914 kWp farm in 2030 and reproduce the
pinned 2030 period EXACTLY (the 2030 constraint is identical to legacy in
both; the only question is whether the JOINT optimum still fills the land in
year one). If C's 2030 matches the pins, + DISC-1 close together with
the headline intact.

    PYTHONPATH=. python scripts/dens1_options_probe.py
"""
from copy import deepcopy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics
from energy.dispatch import solve_dispatch_pyomo
from energy.network import load_optimised_network

PIN_2030_COST = 1_841_569_555.79
PIN_2030_CO2 = 116_638_892.44

KEYS = ("rooftop_pv_kwp", "solar_farm_kwp", "carport_kwp", "floating_pv_kwp",
        "battery_kwh", "solar_thermal_m2")


def econ_variant(dens_flat: bool, disc: float):
    e = deepcopy(load_economics(force_reload=True))
    mp = dict(e.__dict__.get("multi_period_raw", {}) or {})
    mp["pv_density_area_budget"] = True
    if dens_flat:
        mp["pv_density_ceiling_multiplier_by_period"] = {
            2030: 1.0, 2042: 1.0, 2055: 1.0}
    if disc:
        mp["discount_rate_real"] = float(disc)
    e.__dict__["multi_period_raw"] = mp
    return e


net = load_optimised_network()
print("network built", flush=True)

runs = {
    "B_dens_flat": econ_variant(dens_flat=True, disc=0.0),
    "C_disc_6.5%": econ_variant(dens_flat=False, disc=0.065),
}

for tag, e in runs.items():
    r = solve_dispatch_pyomo(net, e, scenario_name="full_stack", alpha=0.0)
    pb = r.period_breakdown
    p0 = sorted(pb)[0]
    c0 = float(pb[p0]["annual_cost_inr"])
    e0 = float(pb[p0]["annual_emissions_kgco2"])
    print("\n=== %s ===" % tag, flush=True)
    print("  lifetime %20.2f" % r.lifetime_cost_inr)
    print("  2030 period cost %18.2f  vs pin %18.2f  delta %14.2f  %s"
          % (c0, PIN_2030_COST, c0 - PIN_2030_COST,
             "MATCHES PIN" if abs(c0 - PIN_2030_COST) < 0.01 else "moved"))
    print("  2030 period CO2  %18.2f  vs pin %18.2f  delta %14.2f  %s"
          % (e0, PIN_2030_CO2, e0 - PIN_2030_CO2,
             "MATCHES PIN" if abs(e0 - PIN_2030_CO2) < 0.01 else "moved"))
    for p in sorted(pb):
        row = pb[p]["installed_capacities"]
        print("  %d  " % p + "  ".join(
            "%s %.1f" % (k.replace("_kwp", "").replace("_kwh", "")
                          .replace("_m2", ""), float(row.get(k, 0.0)))
            for k in KEYS))
    print("  exports GWh: " + "  ".join(
        "%d %.1f" % (p, float(pb[p]["grid_export_kwh"]) / 1e6)
        for p in sorted(pb)))

print("\ndone", flush=True)
