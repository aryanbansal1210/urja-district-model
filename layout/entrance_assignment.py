"""Per-cell entrance-side computation.

the author: "how do we know what the front (entrance) of each building is?
The roadside building entrance is obviously going to be from the road.
Rest you have to critically think how to place them. Also the high
street, as there are two buildings in one cell, if the high-street
cell is adjacent to the road, the building/shop in that cell could
have two doors, one at the road side and one on its back opening
towards the high street. And then the second shop will have the
entrance pointing towards the high street too — this will only be
true if the high-street cell is adjacent to the road, otherwise they
can just have one door each facing the high street (doors facing each
other basically)."

Deterministic rules (cell-by-cell, in order):

1. If cell is RETAIL_HIGHSTREET:
   a. If it has a ROAD 4-neighbour → TWO entrances: one toward the road
      (shop facing the street) + one toward the other RETAIL_HIGHSTREET
      cell in the chain (back-shop opening toward the highstreet alley).
   b. If no ROAD 4-neighbour → one entrance toward the adjacent
      RETAIL_HIGHSTREET cell in the chain ("doors facing each other"
      across the pedestrianised alley).
2. Else if cell has any ROAD 4-neighbour → entrance toward the
   ROAD with the highest "traffic" proxy. Proxy: pick the ROAD with
   the most non-ROAD built-cell 4-neighbours (busier feeder road).
3. Else (no road 4-neighbour, no highstreet) → entrance toward the
   nearest ROAD cell in the 8-neighbour ring (typical Punjab service
   lane pattern). If still no ROAD in the 8-ring, default to south
   (180°) — most cells in Indian urban grids face south for daylight.

Encoded in cardinal degrees clockwise from north:
   0 = north, 90 = east, 180 = south, 270 = west.

Mutates `Cell.entrance_sides: List[int]` in place. None for non-built
cells.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from core.grid import Cell, Grid
from core.land_use import LandUse


# 4-neighbour offsets + the entrance degree they imply (entrance points
# AT the neighbour). row+1 = north (since (0,0) is SW), col+1 = east.
_NEIGHBOUR_DEGREES = {
    (1, 0): 0,    # neighbour north of me → my entrance faces N
    (0, 1): 90,   # east
    (-1, 0): 180, # south
    (0, -1): 270, # west
}
# 8-neighbour offsets for the "nearest road in 8-ring" fallback.
_EIGHT_NEIGHBOURS = [
    (1, 0), (0, 1), (-1, 0), (0, -1),
    (1, 1), (1, -1), (-1, 1), (-1, -1),
]


def _cell_at(grid: Grid, r: int, c: int) -> Optional[Cell]:
    if 0 <= r < grid.n_rows and 0 <= c < grid.n_cols:
        return grid.at(r, c)
    return None


def _road_neighbours_4(grid: Grid, cell: Cell) -> List[Tuple[Tuple[int, int], int]]:
    """List of ((row, col), entrance_deg) for ROAD 4-neighbours."""
    out: List[Tuple[Tuple[int, int], int]] = []
    for (dr, dc), deg in _NEIGHBOUR_DEGREES.items():
        nb = _cell_at(grid, cell.row + dr, cell.col + dc)
        if nb is not None and nb.land_use == LandUse.ROAD:
            out.append(((nb.row, nb.col), deg))
    return out


def _highstreet_neighbours_4(grid: Grid, cell: Cell) -> List[Tuple[Tuple[int, int], int]]:
    out: List[Tuple[Tuple[int, int], int]] = []
    for (dr, dc), deg in _NEIGHBOUR_DEGREES.items():
        nb = _cell_at(grid, cell.row + dr, cell.col + dc)
        if nb is not None and nb.land_use == LandUse.RETAIL_HIGHSTREET:
            out.append(((nb.row, nb.col), deg))
    return out


def _road_traffic_proxy(grid: Grid, road_cell_id: Tuple[int, int]) -> int:
    """Higher = busier. Counts built (non-road) 4-neighbours of this road."""
    r, c = road_cell_id
    count = 0
    for (dr, dc) in _NEIGHBOUR_DEGREES.keys():
        nb = _cell_at(grid, r + dr, c + dc)
        if nb is None:
            continue
        if nb.land_use != LandUse.ROAD and nb.has_building:
            count += 1
    return count


def _nearest_road_8ring(grid: Grid, cell: Cell) -> Optional[int]:
    """Degree toward the nearest ROAD in the 8-neighbour ring."""
    best: Optional[Tuple[int, int]] = None  # (distance², deg)
    for (dr, dc) in _EIGHT_NEIGHBOURS:
        nb = _cell_at(grid, cell.row + dr, cell.col + dc)
        if nb is None or nb.land_use != LandUse.ROAD:
            continue
        d2 = dr * dr + dc * dc
        # Translate dr/dc to a cardinal degree (snap to nearest 4-axis).
        if abs(dr) >= abs(dc):
            deg = 0 if dr > 0 else 180
        else:
            deg = 90 if dc > 0 else 270
        if best is None or d2 < best[0]:
            best = (d2, deg)
    return best[1] if best is not None else None


def entrance_sides_for_cell(grid: Grid, cell: Cell) -> List[int]:
    """Deterministic entrance-side rule for one cell. Returns 0-2 ints
    (cardinal degrees); empty list for non-built cells."""
    if not cell.has_building:
        return []
    # Rule 1: RETAIL_HIGHSTREET special case (2 doors when also road-adjacent).
    if cell.land_use == LandUse.RETAIL_HIGHSTREET:
        road_nbrs = _road_neighbours_4(grid, cell)
        hs_nbrs = _highstreet_neighbours_4(grid, cell)
        if road_nbrs and hs_nbrs:
            # Two entrances: one road-side, one highstreet-internal-side.
            return [road_nbrs[0][1], hs_nbrs[0][1]]
        if road_nbrs:
            return [road_nbrs[0][1]]
        if hs_nbrs:
            return [hs_nbrs[0][1]]
        # Highstreet with no road and no adjacent highstreet: rare; fall through.
    # Rule 2: prefer 4-neighbour ROAD (busiest one).
    road_nbrs = _road_neighbours_4(grid, cell)
    if road_nbrs:
        # Pick the road with the highest traffic proxy; tie-break by deg.
        road_nbrs.sort(key=lambda t: (-_road_traffic_proxy(grid, t[0]), t[1]))
        return [road_nbrs[0][1]]
    # Rule 3: fallback to nearest ROAD in 8-ring; else south.
    deg = _nearest_road_8ring(grid, cell)
    if deg is not None:
        return [deg]
    return [180]


def assign_entrances(grid: Grid) -> int:
    """Compute and write `Cell.entrance_sides` for every built cell.

    Returns the number of cells touched."""
    n = 0
    for cell in grid.all_cells():
        cell.entrance_sides = entrance_sides_for_cell(grid, cell)
        if cell.entrance_sides:
            n += 1
    return n
