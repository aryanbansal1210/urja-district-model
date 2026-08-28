"""Amenity sub-type tags for SCHOOL and HEALTHCARE cells (batch-A,).

One land-use, a sub-type shown on viewer hover (like the RELIGIOUS faith tag).
Tagged post-anneal; cosmetic only (no energy-model effect):

  * SCHOOL    -> "primary" / "secondary"  (URDPFI 2014: 1/5,000 vs 1/7,500 pop)
  * HEALTHCARE -> "UPHC" / "UCHC"          (IPHS 2022: urban PHC vs urban CHC)

Counts come from `core.requirements.Requirements` (the same URDPFI/IPHS
population-per-facility derivation that sized the cell counts). The split is
proportional to the derived facility mix and deterministic (walk cells in
(row, col) order). For healthcare, the larger UCHC (district hospital) is
assigned to the most CENTRAL healthcare cell(s) — physically it is the
region-serving facility — and UPHCs take the rest.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from core.grid import Cell, Grid
from core.land_use import LandUse
from core.requirements import Requirements


def _assign_schools(grid: Grid, req: Requirements) -> Dict[str, int]:
    cells: List[Cell] = sorted(
        (c for c in grid.all_cells() if c.land_use == LandUse.SCHOOL),
        key=lambda c: (c.row, c.col),
    )
    n = len(cells)
    if n == 0:
        return {"primary": 0, "secondary": 0}
    n_prim_fac = max(0, int(req.primary_schools))
    n_sec_fac = max(0, int(req.secondary_schools))
    total_fac = n_prim_fac + n_sec_fac
    # Proportional split; default to mostly-primary if facility counts absent.
    prim_share = (n_prim_fac / total_fac) if total_fac > 0 else 0.6
    n_primary = int(round(n * prim_share))
    n_primary = max(0, min(n, n_primary))
    for i, c in enumerate(cells):
        c.amenity_subtype = "primary" if i < n_primary else "secondary"
    return {"primary": n_primary, "secondary": n - n_primary}


def _assign_healthcare(grid: Grid, req: Requirements) -> Dict[str, int]:
    cells: List[Cell] = [c for c in grid.all_cells()
                         if c.land_use == LandUse.HEALTHCARE]
    n = len(cells)
    if n == 0:
        return {"UPHC": 0, "UCHC": 0}
    #.8: the LOCKED 2x2
    # hospital campus (layout/f6_locks.py, subtype "hospital_campus") IS
    # the town's general hospital - it keeps its tag and satisfies the
    # UCHC requirement; every other healthcare cell becomes a UPHC clinic.
    # Without this the centrality re-subtyping below overwrote the campus
    # tag (the same wipe class as the canal lesson).
    campus = [c for c in cells if c.amenity_subtype == "hospital_campus"]
    if campus:
        for c in cells:
            if c.amenity_subtype != "hospital_campus":
                c.amenity_subtype = "UPHC"
        return {"UCHC": 0, "UPHC": n - len(campus),
                "hospital_campus": len(campus)}
    n_uchc = max(0, int(req.hospitals))      # IPHS urban CHC (district hospital)
    n_uchc = min(n_uchc, n)
    if n_uchc == 0 and n > 0:
        n_uchc = 1                            # always at least one hospital if any
        n_uchc = min(n_uchc, n)
    # UCHC = the most CENTRAL healthcare cell(s) (region-serving hospital).
    cr = (grid.n_rows - 1) / 2.0
    cc = (grid.n_cols - 1) / 2.0
    by_central = sorted(
        cells, key=lambda c: (abs(c.row - cr) + abs(c.col - cc), c.row, c.col)
    )
    uchc_set = set(id(c) for c in by_central[:n_uchc])
    for c in cells:
        c.amenity_subtype = "UCHC" if id(c) in uchc_set else "UPHC"
    return {"UCHC": n_uchc, "UPHC": n - n_uchc}


def assign_amenity_subtypes(grid: Grid, req: Requirements) -> Dict[str, Dict[str, int]]:
    """Tag SCHOOL + HEALTHCARE cells with a hover sub-type. Mutates in place.

    Returns
    -------
    Dict[str, Dict[str, int]]
        ``{"school": {...}, "healthcare": {...}}`` allocation counts.
    """
    # Clear stale tags on non-school/health cells (defensive) - but PRESERVE
    # protected pre-anneal subtypes that other passes own. STAGE- fix
    #: the canal corridor is
    # tagged amenity_subtype="canal" PRE-anneal (layout.canal_corridor) and
    # the energy model keys the canal-top PV density off that tag, so this
    # defensive wipe must not nuke it. campus_grounds + open-space subtypes
    # are assigned AFTER this pass so they are naturally safe; canal is the
    # one assigned before it. (Same protect-a-subtype pattern as
    # tag_open_space_structure skipping campus_grounds.)
    # B18.4: the locked Chandigarh green structure's tags
    # (park_community blocks + the greenway spine) are pre-anneal planned
    # structure like the canal - never this pass's to wipe. (Emergent
    # open-space tags are re-derived by tag_open_space_structure right
    # after this pass, so protecting the names is harmless for them.)
    # Review fix: protection is LAND-USE-AWARE - a protected
    # tag only survives on the land use it belongs to (canal on water,
    # green tags on open space). A stale park tag on a cell the SA later
    # built on must be wiped, not preserved.
    _PROTECTED = {
        "canal": (LandUse.BLUE_SPACE,),
        "park_community": (LandUse.OPEN_SPACE,),
        "greenway": (LandUse.OPEN_SPACE,),
        # (, caught by the dress rehearsal - the canal
        # lesson repeated): the pre-anneal LOCKED solar expansion ring +
        # agri perimeter band (layout/f6_locks.py) are planned structure;
        # wiping them walled the farm fence with locked-but-untagged cells
        # and the post-anneal stamper could only re-tag 6/100 ring cells.
        "solar_expansion_2042": (LandUse.OPEN_SPACE,),
        "solar_expansion_2055": (LandUse.OPEN_SPACE,),
        "agri_belt": (LandUse.OPEN_SPACE,),
        # VACANT-1: Baseline 2's generator tags its 43
        # Table 6-1 park cells park_neighbourhood so the viewer can draw
        # them as the satellite's green POCKETS while the untagged
        # remainder renders as bare Open/Vacant land. Same canal lesson:
        # a generator-owned tag is not this pass's to wipe. Harmless for
        # the designed town - its emergent park tags are re-derived by
        # tag_open_space_structure right after this pass anyway.
        "park_neighbourhood": (LandUse.OPEN_SPACE,),
    }
    for c in grid.all_cells():
        if c.land_use in (LandUse.SCHOOL, LandUse.HEALTHCARE):
            continue
        allowed = _PROTECTED.get(c.amenity_subtype or "")
        if allowed and c.land_use in allowed:
            continue
        c.amenity_subtype = None
    return {
        "school": _assign_schools(grid, req),
        "healthcare": _assign_healthcare(grid, req),
    }
