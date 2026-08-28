"""Building CAMPUS footprints - the LIGHT model (Stage-.

the author ask: buildings should look like real buildings - a hospital is a big
campus, a school spans its playfield, not every cell a uniform box. The LIGHT
model delivers this WITHOUT touching demand:

  * the BUILDING cell keeps its per-cell floor + demand (unchanged),
  * a campus is the building cell PLUS (footprint - 1) GROUNDS cells claimed
    from adjacent OPEN_SPACE and tagged `amenity_subtype = "campus_grounds"`
    (land_use STAYS open_space -> zero demand, zero re-pin),
  * export/rendering merges the building + its grounds into one campus polygon.

Campus size comes from `core.land_use.TYPICAL_FOOTPRINT_CELLS` (+ the sub-type
overrides for secondary school = 2 and UCHC hospital = 4). Only facilities with
a footprint > 1 (mall 4, UCHC 4, secondary 2, warehouse 2) claim grounds; the
rest are single-cell buildings.

Runs POST-anneal, AFTER assign_amenity_subtypes (needs the school/health
sub-types) and BEFORE tag_open_space_structure (so grounds are claimed before
the remaining open space is tagged as parks/belt). Deterministic (BFS from each
facility, facilities processed largest-first then by (row, col); no RNG).
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid
from core.land_use import (
    LandUse, TYPICAL_FOOTPRINT_CELLS, TYPICAL_FOOTPRINT_CELLS_BY_SUBTYPE,
)

CellId = Tuple[int, int]
CAMPUS_GROUNDS = "campus_grounds"


def footprint_cells_for(cell: Cell) -> int:
    """Campus size in cells for a built cell (sub-type override wins)."""
    if cell.amenity_subtype in TYPICAL_FOOTPRINT_CELLS_BY_SUBTYPE:
        return TYPICAL_FOOTPRINT_CELLS_BY_SUBTYPE[cell.amenity_subtype]
    return TYPICAL_FOOTPRINT_CELLS.get(cell.land_use, 1)


def apply_campus_grounds(grid: Grid,
                         cfg: Optional[DistrictConfig] = None
                         ) -> Dict[str, object]:
    """Ring each grounds-wanting building UNIT with GROUNDS cells claimed from
    adjacent OPEN_SPACE (tagged `campus_grounds`; land_use unchanged, so demand
    is untouched). Mutates grid. Operates on UNITS (grouped contiguous same-use
    cells), not individual cells, so a clustered mall/hospital is ONE campus:
    a unit whose footprint target F exceeds its current cell-count U gets
    (F - U) grounds. Deterministic. Returns a summary for the register/logbook.
    """
    if cfg is None:
        cfg = load_config()

    # group built cells into units (grounds not yet placed -> pure built groups)
    unit_of = building_units(grid)
    cells_by_unit: Dict[int, List[Cell]] = {}
    by_id = {(c.row, c.col): c for c in grid.all_cells()}
    for cid, uid in unit_of.items():
        cell = by_id[cid]
        if cell.has_building:
            cells_by_unit.setdefault(uid, []).append(cell)

    # target footprint per unit = max campus size over its cells (sub-type wins)
    units = []
    for uid, cells in cells_by_unit.items():
        target = max(footprint_cells_for(c) for c in cells)
        deficit = max(0, target - len(cells))
        if deficit > 0:
            units.append((deficit, cells))
    units.sort(key=lambda t: (-t[0], t[1][0].row, t[1][0].col))

    claimed: set = set()
    grounds_added = 0
    fully = 0
    for deficit, cells in units:
        got = 0
        cell_ids = {(c.row, c.col) for c in cells}
        frontier = deque(sorted(cell_ids))
        seen = set(cell_ids)
        while frontier and got < deficit:
            r, c = frontier.popleft()
            for nb in grid.neighbours_4(r, c):
                key = (nb.row, nb.col)
                if key in seen:
                    continue
                seen.add(key)
                free_open = (nb.land_use == LandUse.OPEN_SPACE
                             and not nb.locked
                             and nb.amenity_subtype != CAMPUS_GROUNDS
                             and key not in claimed)
                if got < deficit and free_open:
                    nb.amenity_subtype = CAMPUS_GROUNDS
                    claimed.add(key)
                    got += 1
                    grounds_added += 1
                    frontier.append(key)
                elif nb.land_use == LandUse.OPEN_SPACE and key not in claimed:
                    frontier.append(key)  # spread through open to reach grounds
        if got == deficit:
            fully += 1
    return {
        "grounds_wanting_units": len(units),
        "fully_ringed": fully,
        "grounds_added": grounds_added,
    }


def building_units(grid: Grid) -> Dict[CellId, int]:
    """Group cells into building UNITS for merged export/rendering: each unit is
    a 4-connected run of same-land-use BUILT cells, extended to include any
    `campus_grounds` open cells 4-adjacent to it. Returns cell_id -> unit_id.
    Non-built, non-grounds cells are absent. (Rendering/report helper; the
    viewer merges one polygon per unit - deferred to the Codex re-sync.)
    """
    built_by_use: Dict[CellId, LandUse] = {
        (c.row, c.col): c.land_use for c in grid.all_cells() if c.has_building
    }
    grounds: set = {(c.row, c.col) for c in grid.all_cells()
                    if c.land_use == LandUse.OPEN_SPACE
                    and c.amenity_subtype == CAMPUS_GROUNDS}
    out: Dict[CellId, int] = {}
    uid = 0
    seen: set = set()
    for start, use in sorted(built_by_use.items()):
        if start in seen:
            continue
        # grow a same-use built component
        comp: List[CellId] = []
        dq = deque([start])
        seen.add(start)
        while dq:
            cur = dq.popleft()
            comp.append(cur)
            r, c = cur
            for d in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nb = (r + d[0], c + d[1])
                if nb in seen:
                    continue
                if built_by_use.get(nb) == use:
                    seen.add(nb)
                    dq.append(nb)
        # attach adjacent campus grounds
        for (r, c) in list(comp):
            for d in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nb = (r + d[0], c + d[1])
                if nb in grounds and nb not in out:
                    out[nb] = uid
        for cid in comp:
            out[cid] = uid
        uid += 1
    return out


if __name__ == "__main__":
    from energy.network import grid_from_geojson
    g, name = grid_from_geojson()
    summary = apply_campus_grounds(g)
    units = building_units(g)
    print(f"{name}: campus grounds {summary}")
    print(f"building units: {len(set(units.values()))} units over "
          f"{len(units)} cells (built + grounds)")
