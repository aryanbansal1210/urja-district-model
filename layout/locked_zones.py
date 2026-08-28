"""Deterministic locked zones for the SA optimiser.

the author flagged two recurring artifacts that soft SA metrics could not fix:

1. **Amenities blocking roads.** The optimiser kept converting cells on the
   arterial road skeleton (e.g. the central (12,12) intersection, the
   (12,0) edge node) into a temple or hospital, severing the through-road.
   This also shows up as the `road_connectivity` hard-constraint failure.

2. **Buildings embedded inside the solar farm.** The single-block
   `solar_cluster_score` produced one *connected* SOLAR_FARM region, but a
   Swiss-cheese one with ~23 residential / religious / school / hospital
   cells trapped inside its footprint. A solar field with houses inside it
   is not physically sensible.

Both are fixed deterministically here rather than by hoping the optimiser
lands them: we reserve the arterial road skeleton and a clean rectangular
solar zone as **locked** cells. The SA then arranges all other land use
*around* these reserved cells (every move skips locked cells), so roads can
never be broken and the solar field is always a clean block with nothing
inside it.

This mirrors real master-planning: the road network and the solar zone are
fixed infrastructure decisions, not things the layout optimiser should be
free to dissolve.
"""
from __future__ import annotations

import math
from typing import Set, Tuple

from core.grid import Grid
from core.land_use import LandUse

CellId = Tuple[int, int]


def arterial_rows_cols(grid: Grid) -> Tuple[Set[int], Set[int]]:
    """Arterial road rows/cols: south edge, central spine, north edge (and
    the column equivalents). Matches the chandigarh_sector seed skeleton
    (rows/cols 0, n//2, n-1)."""
    art_rows = {0, grid.n_rows // 2, grid.n_rows - 1}
    art_cols = {0, grid.n_cols // 2, grid.n_cols - 1}
    return art_rows, art_cols


def _solar_zone_cells(grid: Grid, solar_cells: int,
                       art_rows: Set[int], art_cols: Set[int]) -> Set[CellId]:
    """Return a clean rectangular block of `solar_cells` cells in the SW
    corner, just inside the perimeter road and clear of any arterial.

    Filled row-major from (1, 1) with width ceil(sqrt(n)); for 25 cells this
    is a 5x5 square. A non-perfect square gives a rectangle with a partial
    final row (e.g. 4,4,4,4,5) which is fine -- the only requirement is a
    contiguous block with no non-solar cells inside it.
    """
    width = max(1, math.ceil(math.sqrt(solar_cells)))
    zone: Set[CellId] = set()
    r = 1
    while len(zone) < solar_cells and r < grid.n_rows - 1:
        if r in art_rows:
            r += 1
            continue
        c = 1
        while c <= width and c < grid.n_cols - 1 and len(zone) < solar_cells:
            if c in art_cols:
                c += 1
                continue
            zone.add((r, c))
            c += 1
        r += 1
    return zone


def apply_locked_zones(grid: Grid, solar_cells: int = 25) -> Set[CellId]:
    """Stamp + lock the arterial road skeleton and a clean solar block.

    Mutates `grid` in place:
      * clears any pre-existing SOLAR_FARM (so solar only ever lives in the
        reserved zone),
      * sets the arterial skeleton to ROAD and locks it,
      * sets the SW-corner rectangle to SOLAR_FARM and locks it,
      * leaves every other cell unlocked for the SA to optimise.

    Returns the set of locked (row, col) ids.
    """
    art_rows, art_cols = arterial_rows_cols(grid)

    # Reset locks + clear existing solar so the only solar is the reserved zone.
    for cell in grid.all_cells():
        cell.locked = False
        if cell.land_use == LandUse.SOLAR_FARM:
            cell.land_use = LandUse.OPEN_SPACE

    locked: Set[CellId] = set()

    # Arterial road skeleton (full perimeter + central cross).
    for c in range(grid.n_cols):
        for r in art_rows:
            cell = grid.at(r, c)
            cell.land_use = LandUse.ROAD
            cell.locked = True
            locked.add((r, c))
    for r in range(grid.n_rows):
        for c in art_cols:
            cell = grid.at(r, c)
            cell.land_use = LandUse.ROAD
            cell.locked = True
            locked.add((r, c))

    # Clean solar block in the SW corner.
    for (r, c) in _solar_zone_cells(grid, solar_cells, art_rows, art_cols):
        cell = grid.at(r, c)
        cell.land_use = LandUse.SOLAR_FARM
        cell.locked = True
        locked.add((r, c))

    return locked


def is_road_corridor_cell(grid: Grid, row: int, col: int) -> bool:
    """True if the cell is flanked by ROAD on opposite sides (N&S or E&W).

    Such a cell sits in a road's through-path; placing a building/amenity
    there visually severs the road link even if the network stays
    connected elsewhere. Used as a secondary guard in the optimiser moves.
    """
    def _road(r: int, c: int) -> bool:
        if 0 <= r < grid.n_rows and 0 <= c < grid.n_cols:
            return grid.at(r, c).land_use == LandUse.ROAD
        return False
    ns = _road(row - 1, col) and _road(row + 1, col)
    ew = _road(row, col - 1) and _road(row, col + 1)
    return ns or ew
