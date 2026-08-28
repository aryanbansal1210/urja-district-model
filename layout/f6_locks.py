""" ANNEAL pre-anneal LOCKS (register the author ballot).

Four structures the author's visual review proved the SA cannot deliver
emergently.1/.3/.4/.8) become PLANNED, locked pre-anneal - the
same philosophy as the arterial skeleton, the farm block, the canal and
the big parks (layout/locked_zones.py + park_structure.py): the SA
arranges the town AROUND fixed infrastructure decisions.

  1. HIGHSTREET CHAIN.1): one contiguous run of RETAIL_HIGHSTREET
     cells on the spine - the row immediately SOUTH of the central E-W
     arterial (the greenway holds the north side, park_structure), centred
     on the town core crossing. Chandigarh's shopping streets are planned
     corridors, not emergent singletons (Chandigarh Master Plan 2031,
     Tier 1, https://chandigarh.gov.in/departments/chandigarh-master-plan-2031).
  2. HOSPITAL CAMPUS.8): a 2x2 HEALTHCARE block whose west or east
     face sits ON an arterial/collector (ambulance access - IPHS 2022
     facility siting + IRC access norms, Tier 1/2); nearest valid block to
     the town centre, deterministic spiral search (the park-anchor
     pattern). Subtype "hospital_campus" (protected through the amenity
     passes like canal/campus_grounds).
  3. SOLAR EXPANSION RING.3): the +50/+50 B18 growth parcels stamped
     CONTIGUOUSLY around the locked farm fence by BFS over claimable open
     space, pre-anneal (post-anneal the claimable pool fragments into ~90
     pieces - proven impossible, patch-A diagnostic). Tags
     solar_expansion_2042 / solar_expansion_2055 on locked OPEN_SPACE.
  4. AGRI PERIMETER BAND.4): one bridged run of agri_belt cells along
     the north edge rows just inside the canal corridor (GMADA land-pool
     periphery stays productive until development reaches it; feeds the
     B19 local-food line).

All four are deterministic, compose with existing locks (never overwrite
locked cells), and are wired into core/export_3d.py's seed-grid sequence
AFTER locked zones + sectors + canal + parks (wiring lands with the
anneal batch - this module alone changes nothing).
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from core.grid import Grid
from core.land_use import LandUse

from .locked_zones import arterial_rows_cols

CellId = Tuple[int, int]

HOSPITAL_SUBTYPE = "hospital_campus"
_RING_TAGS = ("solar_expansion_2042", "solar_expansion_2055")


def _free(grid: Grid, r: int, c: int) -> bool:
    if not (0 <= r < grid.n_rows and 0 <= c < grid.n_cols):
        return False
    cell = grid.at(r, c)
    return (not cell.locked) and cell.land_use != LandUse.ROAD


def apply_highstreet_chain_lock(grid: Grid, n_cells: int = 6
                                ) -> Dict[str, object]:
    """Lock ONE contiguous highstreet run on the spine row (south side of
    the central E-W arterial), centred on the core crossing. Slides east
    then west around collisions; a road crossing splits nothing because
    ROAD cells are simply skipped over (the chain is contiguous in the
    retail sense - continuous frontage along the same arterial)."""
    mid = grid.n_rows // 2
    row = mid - 1                       # south of the arterial; greenway is north
    centre = grid.n_cols // 2
    # candidate columns ordered by distance from the core crossing
    order = sorted(range(1, grid.n_cols - 1), key=lambda c: abs(c - centre))
    placed: List[CellId] = []
    for c in order:
        if len(placed) >= n_cells:
            break
        if _free(grid, row, c):
            placed.append((row, c))
    for (r, c) in placed:
        cell = grid.at(r, c)
        cell.land_use = LandUse.RETAIL_HIGHSTREET
        cell.locked = True
    cols = sorted(c for _, c in placed)
    span = (cols[-1] - cols[0] + 1) if cols else 0
    return {"highstreet_locked": len(placed), "row": row,
            "col_span": span, "cols": cols}


def apply_hospital_campus_lock(grid: Grid) -> Dict[str, object]:
    """Lock a 2x2 HEALTHCARE campus with at least one face column/row ON
    the arterial skeleton (ambulance access; lanes are insufficient -
    the.6 lesson). Deterministic spiral from the town centre."""
    art_rows, art_cols = arterial_rows_cols(grid)
    mid_r, mid_c = grid.n_rows // 2, grid.n_cols // 2

    def _block_ok(r0: int, c0: int) -> bool:
        if r0 < 1 or c0 < 1:
            return False
        if r0 + 2 >= grid.n_rows - 1 or c0 + 2 >= grid.n_cols - 1:
            return False
        for r in range(r0, r0 + 2):
            for c in range(c0, c0 + 2):
                if not _free(grid, r, c):
                    return False
        # a face must touch the skeleton: block adjacent to an arterial
        touches = ((r0 - 1) in art_rows or (r0 + 2) in art_rows
                   or (c0 - 1) in art_cols or (c0 + 2) in art_cols)
        return touches

    found: Optional[CellId] = None
    for radius in range(0, max(grid.n_rows, grid.n_cols)):
        ring = sorted(
            (mid_r + dr, mid_c + dc)
            for dr in range(-radius, radius + 1)
            for dc in range(-radius, radius + 1)
            if abs(dr) == radius or abs(dc) == radius
        )
        for (r0, c0) in ring:
            if _block_ok(r0, c0):
                found = (r0, c0)
                break
        if found:
            break
    if not found:
        return {"hospital_campus": 0}
    (r0, c0) = found
    for r in range(r0, r0 + 2):
        for c in range(c0, c0 + 2):
            cell = grid.at(r, c)
            cell.land_use = LandUse.HEALTHCARE
            cell.amenity_subtype = HOSPITAL_SUBTYPE
            cell.locked = True
    return {"hospital_campus": 4, "anchor": found}


def apply_solar_ring_lock(grid: Grid, per_period: int = 50
                          ) -> Dict[str, object]:
    """Stamp the +50/+50 B18 growth parcels as a CONTIGUOUS-BRIDGED ring
    grown by BFS from the locked farm boundary over free open-space cells.
    BRIDGED = the ring may jump ONE road cell (the farm block is boxed by
    the sector collector grid - row/col 16 on the 50x50 seed - so a pure
    ring is impossible; same convention as the agri band, patch A
). Bridge nodes are stepped over, never claimed, and never
    chain (one-cell jumps only). First `per_period` claims ->
    solar_expansion_2042 (locked), next -> solar_expansion_2055 (locked).
    Cells stay OPEN_SPACE (dual-use green until the grant year unlocks -
.16)."""
    farm = [(c.row, c.col) for c in grid.all_cells()
            if c.land_use == LandUse.SOLAR_FARM]
    if not farm:
        return {"ring_2042": 0, "ring_2055": 0}
    seen: Set[CellId] = set(farm)
    # queue entries: (row, col, is_bridge)
    q: deque = deque((r, c, False) for (r, c) in sorted(farm))
    ring: List[CellId] = []
    want = 2 * per_period
    n_bridges = 0
    while q and len(ring) < want:
        (r, c, is_bridge) = q.popleft()
        for (nr, nc) in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if (nr, nc) in seen:
                continue
            if not (0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols):
                continue
            seen.add((nr, nc))
            cell = grid.at(nr, nc)
            claimable = (not cell.locked
                         and cell.land_use == LandUse.OPEN_SPACE)
            if claimable:
                ring.append((nr, nc))
                q.append((nr, nc, False))
                if len(ring) >= want:
                    break
            elif (not is_bridge) and cell.land_use == LandUse.ROAD:
                # step over ONE road cell (collector crossing); bridges
                # do not chain - their neighbours must be claimable.
                q.append((nr, nc, True))
                n_bridges += 1
    for i, (r, c) in enumerate(ring):
        cell = grid.at(r, c)
        cell.amenity_subtype = _RING_TAGS[0] if i < per_period else _RING_TAGS[1]
        cell.locked = True
    n42 = min(per_period, len(ring))
    return {"ring_2042": n42, "ring_2055": max(0, len(ring) - n42),
            "ring_bridges_crossed": n_bridges}


def apply_agri_band_lock(grid: Grid, n_cells: int = 14) -> Dict[str, object]:
    """Lock ONE bridged agri_belt run along the north edge just inside the
    canal corridor (canal row = n-2; band row = n-3, falling back inward).
    'Bridged' = the run may jump ROAD cells (the perimeter fabric)."""
    row = grid.n_rows - 3
    centre = grid.n_cols // 2
    placed: List[CellId] = []
    # walk outward from the centre column so the band sits mid-edge
    order = sorted(range(1, grid.n_cols - 1), key=lambda c: abs(c - centre))
    for c in order:
        if len(placed) >= n_cells:
            break
        r = row
        # fall inward up to 2 rows if the band row is blocked here
        for rr in (row, row - 1, row - 2):
            if _free(grid, rr, c) and grid.at(rr, c).land_use == LandUse.OPEN_SPACE:
                r = rr
                break
        else:
            continue
        cell = grid.at(r, c)
        cell.amenity_subtype = "agri_belt"
        cell.locked = True
        placed.append((r, c))
    return {"agri_band_locked": len(placed),
            "rows": sorted({r for r, _ in placed})}


def apply_f6_locks(grid: Grid, highstreet_cells: int = 6) -> Dict[str, object]:
    """All four locks in the ratified order (chain -> campus -> ring ->
    band). Call AFTER locked zones + sector grid + canal + parks in the
    seed-grid sequence."""
    out: Dict[str, object] = {}
    out.update(apply_highstreet_chain_lock(grid, highstreet_cells))
    out.update(apply_hospital_campus_lock(grid))
    out.update(apply_solar_ring_lock(grid))
    out.update(apply_agri_band_lock(grid))
    return out
