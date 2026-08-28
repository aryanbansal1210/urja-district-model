"""STAGE- canal corridor + canal-top PV ceiling (register Q23,).

the author's siting decision gate ballot,): a minor irrigation
channel along the NORTHERN greenbelt edge - row n_rows-2, one cell inside
the perimeter arterial. Zirakpur's peri-urban surroundings are crossed by
irrigation channels and seasonal choes (Ghaggar system), so a boundary-
following minor canal is the realistic alignment; it never conflicts with
the SW solar reserve, the sector grid, or the town core.

The corridor is BLUE_SPACE cells tagged `amenity_subtype = "canal"` and
LOCKED pre-anneal. At road crossings (arterial + collector columns) the
canal culverts UNDER the road: the road cell wins, the canal splits into
segments (each still >= the floating-PV min-cluster of 2 cells, so every
segment stays a deployable site).

CANAL-TOP PV: the existing `floating_pv` machinery already models canal-top
fixed-tilt structures (PEDA Sidhwan precedent, see economics.yaml
`floating_pv`). Canal cells join the floating-PV site set via the normal
`assign_floating_pv_sites` pass; `EnergyNetwork.total_floating_pv_potential_
kwp` prices canal cells at the CANAL density (`floating_pv.canal.
kwp_per_cell` = 210 kWp per 100 m cell = 2.1 MW/km, PEDA Sidhwan/Ghaggar,
Tier 1-2) instead of the pond density. The LP's existing floating-PV
decision variable then SIZES the build within that ceiling - "capacity is
a decision variable capped by canal-length x ~2.1 MW/km" (register Q23)
with NO new LP variable.

Identification is GEOMETRIC + subtype-based (row == n_rows-2, BLUE_SPACE,
subtype "canal"): amenity_subtype round-trips through the geojson, locked
flags do not (known trap).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid
from core.land_use import LandUse

CellId = Tuple[int, int]

CANAL_SUBTYPE = "canal"


def canal_row(grid: Grid) -> int:
    """The canal's row: one cell inside the northern perimeter arterial."""
    return grid.n_rows - 2


def apply_canal_corridor(grid: Grid,
                         cfg: Optional[DistrictConfig] = None,
                         lock: bool = True) -> Dict[str, object]:
    """Stamp + lock the northern canal corridor. Mutates grid.

    Runs PRE-anneal, AFTER apply_locked_zones + apply_sector_grid: any cell
    already ROAD (arterial/collector crossing) or locked SOLAR is skipped -
    the canal culverts under roads, and never bisects the solar reserve.
    """
    r = canal_row(grid)
    stamped: List[CellId] = []
    for c in range(1, grid.n_cols - 1):     # perimeter arterials excluded
        cell = grid.at(r, c)
        if cell.land_use == LandUse.ROAD:
            continue                         # culvert under the crossing
        if cell.locked and cell.land_use == LandUse.SOLAR_FARM:
            continue                         # never carve the solar reserve
        cell.land_use = LandUse.BLUE_SPACE
        cell.height_m = 0.0
        cell.height_tier = None
        cell.albedo = 0.08                   # open water
        cell.vegetation_fraction = 0.10      # banks
        cell.amenity_subtype = CANAL_SUBTYPE
        cell.entrance_sides = []
        cell.faith = None
        cell.is_carport_site = False
        if lock:
            cell.locked = True
        stamped.append((r, c))
    return {
        "canal_cells": len(stamped),
        "canal_km": round(len(stamped) * grid.cell_size_m / 1e3, 2),
        "row": r,
    }


def canal_cells(grid: Grid) -> List[Cell]:
    """All canal-corridor cells (geometric + subtype identification)."""
    r = canal_row(grid)
    return [grid.at(r, c) for c in range(grid.n_cols)
            if grid.at(r, c).land_use == LandUse.BLUE_SPACE
            and grid.at(r, c).amenity_subtype == CANAL_SUBTYPE]


def is_canal_cell(cell: Cell) -> bool:
    return (cell.land_use == LandUse.BLUE_SPACE
            and cell.amenity_subtype == CANAL_SUBTYPE)


if __name__ == "__main__":
    from core.grid import make_thesis_grid
    from layout.locked_zones import apply_locked_zones
    from layout.sector_structure import apply_sector_grid

    g = make_thesis_grid()
    apply_locked_zones(g, solar_cells=350)
    apply_sector_grid(g, sector_size_cells=8)
    out = apply_canal_corridor(g)
    print(f"canal: {out}")
    segs = len(canal_cells(g))
    print(f"canal cells identified back: {segs}")
