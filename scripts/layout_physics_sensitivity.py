"""What are the LAYOUT-PHYSICS features actually worth?

Replaces two dead scenario switches. `full_stack.allow_street_trees` and
`full_stack.allow_solar_streetlights` both read `true` in economics.yaml and
NO CODE READ EITHER ONE, so flipping them to false changed nothing. That made
them worse than useless: a "town without street trees" run would have returned
an identical answer and invited the conclusion that trees are worth nothing.

Both effects are real. They are just not scenario options - they are computed
when the network is BUILT (tree shading lands in each cell's cooling peak via
`_microclimate_cooling_multiplier`; the streetlight load is summed inside
`EnergyNetwork.from_grid`), and `from_grid` deliberately takes no scenario
argument because ONE network is shared by BAU and the designed town. That
sharing is what makes the vs-BAU ratio a fair comparison.

So the honest way to price a layout feature is to STRIP IT FROM THE LAYOUT and
rebuild. That is what this does.

COST: three network builds, ~200 s each, so about 10 minutes.

Run:  python scripts/layout_physics_sensitivity.py
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from core.land_use import LandUse                              # noqa: E402
from energy.costs import load_economics                        # noqa: E402
from energy.network import (                                   # noqa: E402
    DEFAULT_OPTIMISED_GEOJSON,
    EnergyNetwork,
    grid_from_geojson,
)

OUT = os.path.join(ROOT, "outputs", "verification",
                   "layout_physics_sensitivity.txt")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
log = open(OUT, "w", encoding="utf-8")
T0 = time.time()


def emit(s=""):
    print(str(s), flush=True)
    log.write(str(s) + "\n")
    log.flush()


def build(mutate=None):
    """Fresh grid from the frozen layout, optionally mutated, then a network."""
    grid, layout = grid_from_geojson(DEFAULT_OPTIMISED_GEOJSON)
    if mutate is not None:
        mutate(grid)
    return EnergyNetwork.from_grid(grid, econ=ECON, layout_name=layout), layout


emit("LAYOUT-PHYSICS SENSITIVITY  %s" % time.strftime("%F %H:%M"))
ECON = load_economics(force_reload=True)

net, layout = build()
base_demand = sum(net.demand_by_slice_kwh(ECON).values())
roads = [c for c in grid_from_geojson(DEFAULT_OPTIMISED_GEOJSON)[0].all_cells()
         if c.land_use == LandUse.ROAD]
n_treed = sum(1 for c in roads if getattr(c, "has_street_trees", False))
n_grid = sum(1 for c in roads if c.streetlight_type == "grid")
n_solar = sum(1 for c in roads if c.streetlight_type == "solar")

emit("  layout                 %s" % layout)
emit("  road cells             %d  (treed %d, grid-lit %d, solar-lit %d)"
     % (len(roads), n_treed, n_grid, n_solar))
emit("  district demand AS-IS  %.2f GWh" % (base_demand / 1e6))
emit("  grid streetlight load  %.3f GWh" % (net.grid_streetlight_kwh_yr / 1e6))
emit("[%4.0fs] baseline built" % (time.time() - T0))


# ---- 1. street trees ------------------------------------------------------
def strip_trees(grid):
    for c in grid.all_cells():
        if c.land_use == LandUse.ROAD:
            c.has_street_trees = False


net_nt, _ = build(strip_trees)
no_trees = sum(net_nt.demand_by_slice_kwh(ECON).values())
d_trees = no_trees - base_demand
emit("")
emit("=" * 68)
emit("1. STREET TREES  (avenue-tree shading on adjacent built cells)")
emit("=" * 68)
emit("  demand WITH trees      %.2f GWh" % (base_demand / 1e6))
emit("  demand WITHOUT trees   %.2f GWh" % (no_trees / 1e6))
emit("  TREES SAVE             %.2f GWh/yr = %.3f%% of district demand"
     % (d_trees / 1e6, 100.0 * d_trees / no_trees))
emit("  Mechanism: cooling only. Capped at `microclimate.street_tree_cooling_max`")
emit("  (0.12) per cell, applied where a built cell has a treed-road neighbour.")
emit("[%4.0fs]" % (time.time() - T0))


# ---- 2. solar streetlights -----------------------------------------------
def all_grid_lit(grid):
    for c in grid.all_cells():
        if c.land_use == LandUse.ROAD and c.streetlight_type == "solar":
            c.streetlight_type = "grid"


net_ag, _ = build(all_grid_lit)
d_lights = net_ag.grid_streetlight_kwh_yr - net.grid_streetlight_kwh_yr
emit("")
emit("=" * 68)
emit("2. SOLAR STREETLIGHTS  (off-grid roads draw no night load)")
emit("=" * 68)
emit("  grid streetlight load AS-IS        %.3f GWh" % (net.grid_streetlight_kwh_yr / 1e6))
emit("  if ALL roads were grid-lit         %.3f GWh" % (net_ag.grid_streetlight_kwh_yr / 1e6))
emit("  SOLAR LIGHTS SAVE                  %.3f GWh/yr = %.4f%% of district demand"
     % (d_lights / 1e6, 100.0 * d_lights / base_demand))
emit("  Mechanism: load removal, NOT a PV export. The per-capita street-lighting")
emit("  total is unchanged; only the grid-lit SHARE of roads draws from the grid.")

emit("")
emit("=" * 68)
emit("SUMMARY - what the layout is worth, in demand terms")
emit("=" * 68)
emit("  street trees        %.2f GWh/yr  %.3f%%" % (d_trees / 1e6, 100.0 * d_trees / no_trees))
emit("  solar streetlights  %.2f GWh/yr  %.3f%%" % (d_lights / 1e6, 100.0 * d_lights / base_demand))
emit("")
emit("  NOTE: these are DEMAND-side savings measured on the frozen seed-42")
emit("  layout. They are inherited by BAU as well as the designed town, because")
emit("  both share one network - so they do NOT appear in the vs-BAU ratio.")
emit("  That is the point: the vs-BAU number prices the ENERGY SYSTEM, and these")
emit("  two numbers price part of the MASTER PLAN, which the ratio does not.")
emit("")
emit("  elapsed %.0f s" % (time.time() - T0))
log.close()
