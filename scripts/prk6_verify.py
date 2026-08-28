""" verification gates - run BEFORE and AFTER the swap and diff the output.

The gates are the ones the roadshift / stub-connect patches used, plus the two
this particular swap is supposed to move:

  1. land-use counts EXACTLY conserved (a swap must not create or destroy a use)
  2. households total unchanged
  3. road cells 628 in ONE component
  4. solar estate: zero built cells on any of its 8 neighbours
  5. every HARD constraint green (parking_road_frontage should IMPROVE - the whole
     point of the swap is that the lot gains a real ROAD edge)
  6. lanes rebuild with every parking lot still served
  7. the two swapped cells report the expected new state

Run from district_v3:
    PYTHONPATH=. python -u scripts/prk6_verify.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

GEOJSON = os.path.join(ROOT, "outputs", "geojson3d", "optimised_sa.geojson")
LOT, KOTHI = (12, 28), (12, 26)


def main() -> int:
    from collections import Counter, deque
    from core.building import building_from_cell
    from core.config import load_config
    from core.land_use import LandUse
    from energy.network import grid_from_geojson
    from layout.constraints import check_hard_constraints

    cfg = load_config()
    grid, _ = grid_from_geojson()
    with open(GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)

    parcels = [ft["properties"] for ft in gj["features"]
               if ft["properties"].get("role") == "parcel"]
    counts = Counter(p.get("land_use") for p in parcels)
    print("1. LAND-USE COUNTS")
    for lu, n in sorted(counts.items(), key=lambda kv: str(kv[0])):
        print(f"     {str(lu):26s} {n}")

    hh = sum(int(getattr(building_from_cell(c, cfg), "households", 0) or 0)
             for c in grid.all_cells() if building_from_cell(c, cfg))
    print(f"\n2. HOUSEHOLDS  {hh:,}")

    roads = {(c.row, c.col) for c in grid.all_cells()
             if c.land_use == LandUse.ROAD}
    seen, comps = set(), 0
    for s in roads:
        if s in seen:
            continue
        comps += 1
        q = deque([s])
        seen.add(s)
        while q:
            r, c = q.popleft()
            for n in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if n in roads and n not in seen:
                    seen.add(n)
                    q.append(n)
    print(f"\n3. ROAD CELLS  {len(roads)}  in {comps} component(s)"
          f"   {'OK' if len(roads) == 628 and comps == 1 else '*** CHECK ***'}")

    solar = {(c.row, c.col) for c in grid.all_cells()
             if c.land_use == LandUse.SOLAR_FARM}
    built = {(c.row, c.col) for c in grid.all_cells() if c.has_building}
    bad = [s for s in solar
           if any((s[0] + dr, s[1] + dc) in built
                  for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0))]
    print(f"\n4. SOLAR ESTATE built-8-neighbour adjacency  {len(bad)}"
          f"   {'OK' if not bad else '*** ' + str(bad[:5]) + ' ***'}")

    print("\n5. HARD CONSTRAINTS")
    fails = 0
    for r in check_hard_constraints(grid, cfg):
        if not r.passes:
            fails += 1
        print(f"     {'PASS' if r.passes else 'FAIL'}  {r.name:32s} "
              f"gap={r.gap:.4f}  {r.message[:70]}")
    print(f"     -> {fails} failing")

    lane_cells = set()
    for e in grid.street_edges:
        if e.kind == "local_street":
            lane_cells.add(e.a)
            lane_cells.add(e.b)
    lots = [(c.row, c.col) for c in grid.all_cells()
            if c.land_use == LandUse.PARKING_LOT]
    unserved = []
    for k in lots:
        r, c = k
        road_adj = any((r + dr, c + dc) in roads
                       for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))
        if not road_adj and k not in lane_cells:
            unserved.append(k)
    road_fronted = sum(
        1 for (r, c) in lots
        if any((r + dr, c + dc) in roads
               for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))))
    print(f"\n6. PARKING  {len(lots)} lots | {road_fronted} with a real ROAD edge "
          f"| {len(lots) - road_fronted} lane-only | {len(unserved)} unserved "
          f"{unserved if unserved else ''}")

    print("\n7. THE SWAPPED CELLS")
    for rc in (LOT, KOTHI):
        cell = grid.at(*rc)
        r, c = rc
        radj = [(r + dr, c + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                if (r + dr, c + dc) in roads]
        b = building_from_cell(cell, cfg)
        print(f"     {rc}  {cell.land_use.value:18s} tier={cell.height_tier}"
              f"  hh={getattr(b, 'households', 0) if b else 0}"
              f"  axis={cell.building_axis_deg:.0f}"
              f"  entrances={cell.entrance_sides}"
              f"  road_nbrs={radj}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
