"""LOCKED CHANDIGARH GREEN STRUCTURE (register B18.4,).

the author: "parks have to be bigger, 2-3 big parks (~20-30 acres) + smaller
squares scattered, organised like Chandigarh." Chandigarh's greens are
PLANNED structure, not emergent: Leisure Valley is a ~8 km linear park
threading the sector grid (Chandigarh Master Plan 2031, Tier 1,
https://chandigarh.gov.in/departments/chandigarh-master-plan-2031), the
Zakir Hussain Rose Garden is ~30 acres, and nearly every sector carries
its own green strip. The optimiser's emergent clusters cannot GUARANTEE
that form - so, exactly like the arterial skeleton, the solar farm and
the canal, the big green structure is REGISTERED + LOCKED PRE-anneal and
the SA arranges the town around it:

  * THREE community parks of 3 x 4 cells = 12 ha (~30 acres) each -
    one per non-solar quadrant, anchored ADJACENT to a sector collector
    (park visitors arrive by street; URDPFI community-park tier is
    10-25 ha, our 12 ha sits inside it).
  * ONE linear GREENWAY SPINE: the row of cells immediately north of the
    central E-W arterial, running the width of the town (the Leisure
    Valley pattern) - park segments between road crossings, each locked.

Locked cells are OPEN_SPACE with amenity_subtype pre-set (park_community /
greenway); tag_open_space_structure PRESERVES pre-tagged locked green (the
same protected-subtype pattern as canal/campus_grounds). Small sector
greens still EMERGE from the SA + get tagged as before. Deterministic.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid
from core.land_use import LandUse

from .locked_zones import arterial_rows_cols

CellId = Tuple[int, int]

PARK_BLOCK_ROWS = 3
PARK_BLOCK_COLS = 4          # 3 x 4 cells = 12 ha ~= 30 acres
SPINE_SUBTYPE = "greenway"
PARK_SUBTYPE = "park_community"


def _quadrant_anchors(grid: Grid) -> List[CellId]:
    """Deterministic park anchors: NE, NW, SE quadrant centres (the SW
    quadrant hosts the solar farm). Anchor = top-left of the 3x4 block,
    nudged to sit clear of arterials and adjacent to the quadrant's
    collector lines."""
    n = grid.n_rows
    mid = n // 2
    q = n // 4
    # top-left corners for a 3x4 block roughly centred in each quadrant
    return [
        (mid + q - 1, mid + q - 2),   # NE
        (mid + q - 1, q - 2),         # NW
        (q - 1, mid + q - 2),         # SE
    ]


def _block_ok(grid: Grid, r0: int, c0: int) -> bool:
    if r0 < 1 or c0 < 1:
        return False
    if r0 + PARK_BLOCK_ROWS >= grid.n_rows - 1:
        return False
    if c0 + PARK_BLOCK_COLS >= grid.n_cols - 1:
        return False
    for r in range(r0, r0 + PARK_BLOCK_ROWS):
        for c in range(c0, c0 + PARK_BLOCK_COLS):
            cell = grid.at(r, c)
            if cell.locked or cell.land_use == LandUse.ROAD:
                return False
    return True


def apply_locked_parks(grid: Grid,
                       cfg: Optional[DistrictConfig] = None
                       ) -> Dict[str, object]:
    """Stamp + lock the big-park blocks and the greenway spine. Mutates
    grid. Runs PRE-anneal AFTER locked zones + sector grid + canal (locks
    compose; blocks shift deterministically if their anchor collides)."""
    cfg = cfg or load_config()
    placed: List[CellId] = []

    # ---- three 12-ha community parks -----------------------------------
    n_parks = 0
    for (ar, ac) in _quadrant_anchors(grid):
        # deterministic spiral search around the anchor for a clean block
        found = None
        for radius in range(0, 8):
            candidates = sorted(
                (ar + dr, ac + dc)
                for dr in range(-radius, radius + 1)
                for dc in range(-radius, radius + 1)
                if abs(dr) == radius or abs(dc) == radius
            )
            for (r0, c0) in candidates:
                if _block_ok(grid, r0, c0):
                    found = (r0, c0)
                    break
            if found:
                break
        if not found:
            continue
        (r0, c0) = found
        for r in range(r0, r0 + PARK_BLOCK_ROWS):
            for c in range(c0, c0 + PARK_BLOCK_COLS):
                cell = grid.at(r, c)
                cell.land_use = LandUse.OPEN_SPACE
                cell.height_m = 0.0
                cell.height_tier = None
                cell.albedo = 0.22
                cell.vegetation_fraction = 0.95
                cell.amenity_subtype = PARK_SUBTYPE
                cell.locked = True
                placed.append((r, c))
        n_parks += 1

    # ---- the linear greenway spine (Leisure Valley pattern) ------------
    art_rows, _ = arterial_rows_cols(grid)
    spine_row = grid.n_rows // 2 + 1        # immediately north of the cross
    n_spine = 0
    for c in range(1, grid.n_cols - 1):
        cell = grid.at(spine_row, c)
        if cell.locked or cell.land_use == LandUse.ROAD:
            continue                        # road crossings / farm / canal
        cell.land_use = LandUse.OPEN_SPACE
        cell.height_m = 0.0
        cell.height_tier = None
        cell.albedo = 0.22
        cell.vegetation_fraction = 0.95
        cell.amenity_subtype = SPINE_SUBTYPE
        cell.locked = True
        placed.append((spine_row, c))
        n_spine += 1

    return {
        "big_parks": n_parks,
        "park_cells": n_parks * PARK_BLOCK_ROWS * PARK_BLOCK_COLS,
        "spine_cells": n_spine,
        "spine_km": round(n_spine * grid.cell_size_m / 1e3, 1),
        "total_locked_green": len(placed),
    }


def locked_green_cells(grid: Grid) -> Set[CellId]:
    """Geometric-ish identification for post-anneal passes: locked open
    cells already carrying the park/greenway subtype (in-process the
    locked flag survives; across a geojson round-trip the SUBTYPE is the
    persistent marker and re-stamping is deterministic)."""
    return {(c.row, c.col) for c in grid.all_cells()
            if c.land_use == LandUse.OPEN_SPACE
            and (c.amenity_subtype or "") in (PARK_SUBTYPE, SPINE_SUBTYPE)
            and c.locked}


if __name__ == "__main__":
    from core.grid import make_thesis_grid
    from layout.canal_corridor import apply_canal_corridor
    from layout.locked_zones import apply_locked_zones
    from layout.sector_structure import apply_sector_grid

    g = make_thesis_grid()
    apply_locked_zones(g, solar_cells=200)
    apply_sector_grid(g, sector_size_cells=8)
    apply_canal_corridor(g)
    out = apply_locked_parks(g)
    print(out)
