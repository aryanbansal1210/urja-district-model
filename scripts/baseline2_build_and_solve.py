"""BASELINE 2 - build, audit, export and solve the third town.

the author's definition: "plan as delivered. i want it as close to the modern day
current zirakpur, without any solar.. so we have two baselines." Programme
held CONSTANT per his ballot (same 54,794 households, same built floor
areas) - only the ARRANGEMENT differs.

Pipeline, one run:
  1. generate('zirakpur_ribbon', seed=42) - self-validates the programme.
  2. Calibration table vs the GMADA Revised Master Plan measured shares.
  3. Hard-constraint audit (A20 fairness discipline: a baseline must not be
     a strawman that fails constraints by construction - and where it DOES
     fail, the failure must be the finding, not an accident).
  4. Export outputs/geojson3d/zirakpur_ribbon.geojson (viewer + regen).
  5. EnergyNetwork.from_grid + BAU solve = Baseline 2's cost and CO2.
  6. Internal-network cost on ITS OWN geometry vs the planned layout's.

PREDICTIONS REGISTERED IN THE SPEC, printed against results either way:
  P1 cable-km: the spec predicted MORE than the planned layout. NOTE the
     honest caveat discovered at build time: Baseline 2 has 9.2% road share
     against the town's 25.1% (real unplanned growth under-builds roads -
     the Bertaud point), and the cable model follows ROAD-ROAD edges, so it
     may come out SHORTER, i.e. sprawl "saving" cable by under-building
     roads. If so, that is the finding: under-provision masquerading as
     savings, at 100 m resolution which cannot see colony lanes.
  P2 cooling demand: HIGHER (fewer green neighbours -> less microclimate
     relief) - despite MORE open space in aggregate, because the parks are
     gone and the agri remnant is not adjacent to the ribbon housing.
  P3 sized grid connection ~ BAU's (same demand, no solar).

Run from district_v3:
    PYTHONPATH=. python -u scripts/baseline2_build_and_solve.py
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_config                         # noqa: E402
from core.demographics import (                             # noqa: E402
    load_demand_norms, load_demographics,
)
from core.export_3d import export_layouts                   # noqa: E402
from energy.costs import load_economics                     # noqa: E402
from energy.dispatch import solve_dispatch_pyomo            # noqa: E402
from energy.electrical_assets import (                      # noqa: E402
    network_capex_inr, production_network_annualised_inr,
)
from energy.network import EnergyNetwork, load_optimised_network  # noqa: E402
from layout.constraints import check_hard_constraints       # noqa: E402
from layout.generator import generate                       # noqa: E402

GMADA = {  # measured existing land use, Revised Master Plan (share of LPA)
    "residential": 22.54, "commercial": 5.93, "industrial": 0.89,
    "institutional": 1.01, "parks+recreation": 0.21, "agriculture": 63.4,
}

print("=" * 76)
print("1/6  GENERATE (self-validating programme-constant)")
grid = generate("zirakpur_ribbon", seed=42)
counts = Counter(cell.land_use.value for cell in grid.all_cells())
tot = sum(counts.values())
print(f"  generated OK: {tot} cells, programme-constant check passed inside "
      f"the generator")

print("\n2/6  CALIBRATION vs GMADA measured Zirakpur")
res = sum(counts[k] for k in ("residential_low", "residential_mid",
                              "residential_high"))
com = sum(counts.get(k, 0) for k in ("shopping_centre", "retail_highstreet",
                                     "restaurant_food_service",
                                     "hotel_guesthouse", "warehouse_cold_storage",
                                     "office"))
ind = counts.get("light_industry", 0)
inst = sum(counts.get(k, 0) for k in ("school", "healthcare",
                                      "public_services", "religious"))
print(f"  {'use':<20}{'B2 share':>10}{'GMADA':>9}   note")
print(f"  {'residential':<20}{100*res/tot:>9.1f}%{GMADA['residential']:>8.1f}%"
      f"   B2 is DENSER housing (programme constant at 250k)")
print(f"  {'commercial':<20}{100*com/tot:>9.1f}%{GMADA['commercial']:>8.1f}%")
print(f"  {'industrial':<20}{100*ind/tot:>9.1f}%{GMADA['industrial']:>8.1f}%")
print(f"  {'institutional':<20}{100*inst/tot:>9.1f}%{GMADA['institutional']:>8.1f}%"
      f"   B2 keeps the town's full programme (the ballot)")
print(f"  {'open/agri residual':<20}{100*counts['open_space']/tot:>9.1f}%"
      f"{GMADA['agriculture']:>8.1f}%   ribbons never reach the interior")
print(f"  {'road':<20}{100*counts['road']/tot:>9.1f}%{'~':>9}"
      f"   town 25.1% - unplanned growth under-builds roads")
print(f"  {'solar farm':<20}{counts.get('solar_farm', 0):>10}{'0':>9}"
      f"   NO SOLAR (Aryan definition)")

print("\n3/6  HARD-CONSTRAINT AUDIT (A20 fairness)")
results = check_hard_constraints(grid)
fails = [r for r in results if not r.passes]
for r in results:
    flag = "PASS" if r.passes else "FAIL"
    print(f"  {flag}  {r.name:<38} gap={r.gap:.3f}  {r.message[:60]}")
print(f"  => {len(results) - len(fails)} pass / {len(fails)} fail")
if fails:
    print("  Failures are REPORTED, not fixed: for Baseline 2 a failed")
    print("  planning constraint is the point of the comparison (the plan")
    print("  enforces what unplanned growth does not).")

print("\n4/6  EXPORT geojson (viewer + regen consumption)")
out = export_layouts(layout_names=["zirakpur_ribbon"], svg_dir=None)
print(f"  wrote outputs/geojson3d/zirakpur_ribbon.geojson")

print("\n5/6  ENERGY - BAU solve on the Baseline 2 layout")
cfg = load_config()
econ = load_economics(force_reload=True)
norms = load_demand_norms()
demo = load_demographics()
net2 = EnergyNetwork.from_grid(grid, cfg=cfg, norms=norms, econ=econ,
                               layout_name="zirakpur_ribbon",
                               demographics=demo)
r2 = solve_dispatch_pyomo(net2, econ, scenario_name="bau", alpha=0.0)
print(f"  B2 (sprawl+grid-only)  cost {r2.annual_cost_inr:>18,.2f}  "
      f"CO2 {r2.annual_emissions_kgco2:>16,.2f}")
print(f"  demand {r2.annual_demand_kwh/1e6:,.1f} GWh   "
      f"import {r2.grid_import_kwh/1e6:,.1f} GWh   "
      f"conn {r2.__dict__.get('grid_connection_mw', 0):,.1f} MW")

print("\n6/6  NETWORK GEOMETRY - Baseline 2 vs the planned layout")
netP = load_optimised_network()
cabP = network_capex_inr(netP, econ)
cab2 = network_capex_inr(net2, econ)
encP = production_network_annualised_inr(netP, econ)
enc2 = production_network_annualised_inr(net2, econ)
print(f"  {'':<26}{'planned':>14}{'baseline2':>14}")
print(f"  {'route km':<26}{cabP['total_route_km']:>14,.1f}"
      f"{cab2['total_route_km']:>14,.1f}")
print(f"  {'cable annualised Rs':<26}{cabP['annualised_inr']:>14,.0f}"
      f"{cab2['annualised_inr']:>14,.0f}")
print(f"  {'network total Rs/yr':<26}"
      f"{encP.get('annualised_total_inr', 0):>14,.0f}"
      f"{enc2.get('annualised_total_inr', 0):>14,.0f}")
print("\n  PREDICTION CHECK (spec P1): the spec predicted MORE cable-km for")
print("  sprawl. If baseline2 shows FEWER km, the mechanism is the 9.2% vs")
print("  25.1% road share: at 100 m resolution the model cannot see colony")
print("  lanes, so under-built roads read as an infrastructure SAVING.")
print("  Report whichever way it lands - it is a finding either way.")

print("\nDONE. Compare against BAU-on-planned-layout 3,546,796,546.71 / "
      "304,003,984.89 (the 2026-08-11 pins; demand differences here are the")
print("microclimate + streetlight channels - the programme is identical.")
