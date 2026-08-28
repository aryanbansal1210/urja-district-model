"""STAGE- pedestrian + cycle NETWORK + walkability scoring.

Register B8: bike + foot KEPT
TOGETHER, on every street; dedicated cycle track on arterials + collectors,
shared space on locals; greenway LOOPS through parks and the belt.

What is geometry vs attribute (the honest split):
  * Footpaths + cycle tracks ALONG STREETS are attributes of the street
    itself - every ROAD cell's ROW already contains them (IRC:103-2012
    footpaths both sides; IRC:11-2015 cycle tracks; see
    layout.road_network.ROAD_CLASS_SPEC) and every local lane is shared
    space (motor+cycle+foot). No extra geometry, no extra ROW.
  * GREENWAY PATHS are new geometry: foot+cycle edges on the boundaries
    between adjacent green cells (park_community / park_neighbourhood /
    greenway / greenbelt open-space subtypes), forming the park loops.
    They live INSIDE park area - no ROW debit (a 3-4 m shared path per
    IRC:11 is landscape, not right-of-way).

This layer carries NO electrons: it never touches the energy LP, so it
cannot move the headline (roadmap: = post-anneal overlay). It runs
POST-anneal after `tag_open_space_structure` (needs the green subtypes)
and after `assign_local_streets` (walkability reads the lanes).

WALKABILITY: `walkability_report` (and the thin
`metrics.walkability_permeability_score` wrapper, weight 0.0 in the SA -
the edges do not exist mid-anneal) scores:
  * access      - share of built+parking cells fronting the walk network
                  (road cell, local lane, or adjacent walkable green);
  * permeability - mean share of each built cell's 4 boundaries that are
                  walkable interfaces (redundancy is GOOD urban design -
                  never minimised, register B8/spec 3d);
  * green_loop  - share of green+path cells in the largest connected
                  walk component (the greenway loop actually connects).
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from core.grid import Cell, Grid, StreetEdge
from core.land_use import LandUse

CellId = Tuple[int, int]

GREEN_PATH_SUBTYPES = {
    "park_community", "park_neighbourhood", "greenway", "greenbelt",
}
PATH_WIDTH_M = 3.5   # shared foot+cycle greenway path, IRC:11-2012 two-way
                     # cycle track 3.0 m + pedestrian margin; inside park area


def _is_walkable_green(cell: Cell) -> bool:
    return (cell.land_use == LandUse.OPEN_SPACE
            and (cell.amenity_subtype or "") in GREEN_PATH_SUBTYPES)


def assign_path_network(grid: Grid) -> Dict[str, object]:
    """Stamp greenway foot+cycle path edges between adjacent green cells.
    Mutates grid.street_edges (kind="greenway_path"). Idempotent.

    Every boundary between two walkable-green cells carries a path: parks
    are freely walkable, and the full 4-neighbour permeability is the point
    (spec 3d: model FULL walk permeability, do not prune to a spanning
    tree - redundancy is good urban design).
    """
    grid.street_edges = [e for e in grid.street_edges
                         if e.kind != "greenway_path"]
    green: Dict[CellId, Cell] = {
        (c.row, c.col): c for c in grid.all_cells() if _is_walkable_green(c)
    }
    edges: List[StreetEdge] = []
    for (r, c) in sorted(green):
        for nb in ((r + 1, c), (r, c + 1)):        # each boundary once
            if nb in green:
                edges.append(StreetEdge(
                    a=(r, c), b=nb, kind="greenway_path",
                    width_m=PATH_WIDTH_M, modes=("cycle", "foot"),
                ))
    grid.street_edges.extend(edges)
    return {
        "path_edges": len(edges),
        "path_km": round(len(edges) * grid.cell_size_m / 1e3, 2),
        "green_cells": len(green),
    }


def walkability_report(grid: Grid) -> Dict[str, float]:
    """Score the walk network (see module docstring). Returns the three
    component scores + the composite in [0, 1]."""
    lane_frontage: Set[CellId] = set()
    path_cells: Set[CellId] = set()
    for e in grid.street_edges:
        if e.kind == "local_street":
            lane_frontage.add(e.a)
            lane_frontage.add(e.b)
        elif e.kind == "greenway_path":
            path_cells.add(e.a)
            path_cells.add(e.b)

    road_ids: Set[CellId] = {(c.row, c.col) for c in grid.all_cells()
                             if c.land_use == LandUse.ROAD}
    green_ids: Set[CellId] = {(c.row, c.col) for c in grid.all_cells()
                              if _is_walkable_green(c)}

    edge_pairs = {frozenset((e.a, e.b)) for e in grid.street_edges}

    def _walkable_interface(cell: Cell) -> Tuple[int, int]:
        """(# walkable boundaries, # boundaries) of a cell: a boundary is
        walkable if the neighbour is a ROAD cell (footpaths both sides), a
        walkable green cell, or the boundary carries a lane/path edge."""
        cid = (cell.row, cell.col)
        nbrs = grid.neighbours_4(cell.row, cell.col)
        walkable = 0
        for n in nbrs:
            nid = (n.row, n.col)
            if (nid in road_ids or nid in green_ids
                    or frozenset((cid, nid)) in edge_pairs):
                walkable += 1
        return walkable, len(nbrs)

    checked = [c for c in grid.all_cells()
               if c.has_building or c.land_use == LandUse.PARKING_LOT]
    if not checked:
        return {"access": 0.0, "permeability": 0.0,
                "green_loop": 0.0, "composite": 0.0}

    served = 0
    perm_acc = 0.0
    for cell in checked:
        cid = (cell.row, cell.col)
        w, n = _walkable_interface(cell)
        perm_acc += w / max(1, n)
        if w > 0 or cid in lane_frontage:
            served += 1
    access = served / len(checked)
    permeability = perm_acc / len(checked)

    # green_loop: largest connected component over the walk graph restricted
    # to green + road cells (park loops must connect to the street net).
    walk_nodes = green_ids | road_ids
    if walk_nodes:
        seen: Set[CellId] = set()
        best = 0
        for start in sorted(walk_nodes):
            if start in seen:
                continue
            comp = 0
            dq = deque([start])
            seen.add(start)
            while dq:
                (r, c) = dq.popleft()
                comp += 1
                for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if nb in walk_nodes and nb not in seen:
                        seen.add(nb)
                        dq.append(nb)
            best = max(best, comp)
        green_loop = best / len(walk_nodes)
    else:
        green_loop = 0.0

    composite = 0.5 * access + 0.3 * permeability + 0.2 * green_loop
    return {
        "access": round(access, 4),
        "permeability": round(permeability, 4),
        "green_loop": round(green_loop, 4),
        "composite": round(composite, 4),
    }


if __name__ == "__main__":
    from energy.network import grid_from_geojson
    from layout.road_network import assign_local_streets

    g, name = grid_from_geojson()
    lanes = assign_local_streets(g)
    paths = assign_path_network(g)
    walk = walkability_report(g)
    print(f"{name}: lanes {lanes['lane_edges']}, paths {paths['path_edges']}")
    print(f"walkability: {walk}")
