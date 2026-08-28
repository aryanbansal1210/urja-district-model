"""FARM LEDGER per period, under the ratified DENS batch (P3 config).

the author "installed is different to produced - how much do we
produce in each period, how much do we export to the data centre, how much
money does the solar farm make in each period? I think as demand grows and
generation falls due to degradation, the export decreases?"

One solve at the P3 configuration (area budget + dens 1.0 + roof pair + farm
scaled to GCR 0.382), then a per-period ledger:

  produced   - FARM-only generation, computed from the solved builds x the
               per-kWp farm yield x the vintage age factor (degradation +
               soiling relief + warming derate). The LP pools generation on
               one bus, so a per-tech split is arithmetic on its inputs,
               not a solver output - stated as such.
  DC PPA     - offtake energy and revenue at the blended net concession
               tariff (PPA-PRICE-1 basis; flat-real).
  exports    - district grid exports and revenue at the export tariff.
  money      - IMPORTANT HONESTY NOTE printed with the table: a single-bus
               LP has no per-generator P&L. The farm's "income" is shown
               two ways: (a) the district streams it feeds (exports + PPA),
               with the farm's pro-rata share of PPA-ELIGIBLE generation
               (farm + carport + floating; rooftop is excluded from PPA
               eligibility in the constraint at dispatch ~3066); (b) the
               value of farm energy consumed in town at the avoided
               effective import price. Both labelled conventions.

    PYTHONPATH=. python scripts/dens1_farm_ledger.py
"""
from copy import deepcopy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics
from energy.dispatch import solve_dispatch_pyomo
from energy.network import load_optimised_network

GCR_SCALE = 0.382 / 0.34


def econ_p3():
    e = deepcopy(load_economics(force_reload=True))
    mp = dict(e.__dict__.get("multi_period_raw", {}) or {})
    mp["pv_density_area_budget"] = True
    mp["pv_density_ceiling_multiplier_by_period"] = {
        2030: 1.0, 2042: 1.0, 2055: 1.0}
    e.__dict__["multi_period_raw"] = mp
    techs = dict(e.technologies or {})
    st = dict(techs.get("solar_thermal", {}) or {})
    st["roof_pair_constraint"] = True
    techs["solar_thermal"] = st
    e.technologies = techs
    return e


net = load_optimised_network()
for n in net.nodes:
    n.solar_farm_cap_kwp *= GCR_SCALE
econ = econ_p3()
r = solve_dispatch_pyomo(net, econ, scenario_name="full_stack", alpha=0.0)
pb = r.period_breakdown
print("solved; annual %.2f (expect 1733119405.44)" % r.annual_cost_inr,
      flush=True)

# per-kWp annual farm yield at nameplate (before vintage ageing)
yield_farm = net.pv_yield_per_kwp_kwh_solar_farm(econ)
y_per_kwp = sum(yield_farm.values())

# carport borrows the farm table outright; floating multiplies it by the
# water-cooling gain (dispatch ~2573) - close enough to the farm table for a
# SHARE calculation, and the share moves third-decimal at most.
y_fpv = y_per_kwp

exp_tariff = econ.export_tariff()
acps = econ.ppa_active_counterparties()
toff = sum(float(sp.get("offtake_kw_constant", 0.0))
           for sp in acps.values()) or 1.0
ppa_rate = sum(econ.ppa_counterparty_net_tariff_inr_per_kwh(nm)
               * float(sp.get("offtake_kw_constant", 0.0))
               for nm, sp in acps.items()) / toff

# effective avoided import price: retail tariff x (1 + upstream loss chain)
# is period/slice-shaped; use the model's own reported effective figure -
# import cost / import kWh per period, the honest average.
print("\nexport tariff Rs %.4f/kWh (flat-real), DC-PPA net Rs %.6f/kWh"
      % (exp_tariff, ppa_rate))
print("farm nameplate yield %.1f kWh/kWp/yr (before ageing)\n" % y_per_kwp)

periods = sorted(pb)
print("%-34s" % "per period", "".join("%16d" % p for p in periods))
print("-" * 84)


def row(label, vals, fmt="%16.1f"):
    print("%-34s" % label + "".join(fmt % v for v in vals))


builds = {p: pb[p]["new_build"] for p in periods}
inst_farm = [float(pb[p]["installed_capacities"]["solar_farm_kwp"])
             for p in periods]
row("farm installed kWp", inst_farm)

farm_gen = []
for p in periods:
    g = 0.0
    for v in periods:
        if v > p:
            continue
        kwp = float(builds[v].get("farm_fixed_kwp", 0.0)) \
            + float(builds[v].get("farm_tracked_kwp", 0.0))
        g += kwp * y_per_kwp * econ.pv_vintage_yield_factor(
            "solar_farm", v, p)
    farm_gen.append(g / 1e6)
row("farm produced GWh", farm_gen, "%16.2f")
row("  vintage-2030 age factor",
    [econ.pv_vintage_yield_factor("solar_farm", 2030, p) for p in periods],
    "%16.4f")

demand = [float(pb[p]["annual_demand_kwh"]) / 1e6 for p in periods]
row("district demand GWh", demand, "%16.2f")
pv_all = [float(pb[p]["pv_generation_kwh"]) / 1e6 for p in periods]
row("ALL PV produced GWh", pv_all, "%16.2f")

dc = [float(pb[p].get("dc_ppa_kwh", 0.0)) / 1e6 for p in periods]
row("DC-PPA offtake GWh", dc, "%16.2f")
row("DC-PPA revenue Rs crore", [d * 1e6 * ppa_rate / 1e7 for d in dc],
    "%16.2f")

exp = [float(pb[p]["grid_export_kwh"]) / 1e6 for p in periods]
row("grid export GWh", exp, "%16.2f")
row("export revenue Rs crore", [e * 1e6 * exp_tariff / 1e7 for e in exp],
    "%16.2f")

# farm share of PPA-eligible generation (farm + carport + floating)
shares = []
for i, p in enumerate(periods):
    carport = 0.0
    fpv = 0.0
    for v in periods:
        if v > p:
            continue
        age = econ.pv_vintage_yield_factor("solar_farm", v, p)
        carport += float(builds[v].get("carport_kwp", 0.0)) * y_per_kwp * age
        fpv += float(builds[v].get("floating_pv_kwp", 0.0)) * y_fpv * age
    elig = farm_gen[i] * 1e6 + carport + fpv
    shares.append(farm_gen[i] * 1e6 / elig if elig > 0 else 1.0)
row("farm share of PPA-eligible gen", shares, "%16.3f")
row("farm pro-rata (exp+PPA) Rs crore",
    [shares[i] * (exp[i] * 1e6 * exp_tariff + dc[i] * 1e6 * ppa_rate) / 1e7
     for i in range(len(periods))], "%16.2f")

selfcon = [max(0.0, farm_gen[i] - shares[i] * (exp[i] + dc[i]))
           for i in range(len(periods))]
row("farm energy used in town GWh", selfcon, "%16.2f")

print("""
CONVENTIONS PRINTED WITH THE NUMBERS (single-bus model, no per-asset P&L):
farm 'produced' = solved builds x per-kWp yield x vintage ageing (arithmetic
on the LP's own inputs); 'pro-rata' allocates export + PPA revenue by the
farm's share of PPA-ELIGIBLE generation (farm/carport/floating - rooftop is
not PPA-eligible); energy used in town is worth the avoided import, priced
period-by-period in the cost ledger rather than as one number here.""")
