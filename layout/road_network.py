"""STAGE- road HIERARCHY + honest ROW-area accounting.

Register B6/B8/B16 (the author-ratified direction, B6 in the
 gate ballot: target ~20% ROW of the DEVELOPED area, measured in ROW area,
not cells). Three road classes on the 50x50x100 m grid:

  * ARTERIAL  - the locked perimeter ring + central cross (rows/cols
    {0, n//2, n-1}), the primary boulevards. Cell-based (they predate.
  * COLLECTOR - the Chandigarh sector-defining grid between the arterials
    (layout.sector_structure.sector_collector_lines), locked PRE-anneal so
    the SA arranges land use WITHIN sectors. Cell-based, but only their
    ROW width counts as road area.
  * LOCAL     - (a) SA-grown access/frontage road cells kept by the
    requirements-trim guards, and (b) the POST-anneal `assign_local_streets`
    lane overlay on cell EDGES ("little branches connecting buildings").

THE HONEST ACCOUNTING (the fix for the ~30% full-cell over-count, B16): a
road cell only counts its right-of-way strip - width_m x cell_size_m - as
road; the cell remainder is verge, service margin and building frontage.
Local lanes are edges: length one cell side x 12 m. `road_row_report`
returns ROW area by class + the share of SITE and of DEVELOPED area (the
B6 metric).

ROW widths (right-of-way, carriageway + footpath + cycle track + verge):
  * arterial 50 m, collector 25 m, local street 20 m; residential LANES 12 m.
  * Source Tier 1 (RE-ANCHORED to the site's OWN adopted plan,
    the author: "work out which one is a road and which one is a street"):
    GMADA/NF Infratech, Revised Master Plan Zirakpur, road hierarchy at
    Table 6-1's notes (p63 of Zirakpur_rpt_2011.pdf, parsed in full):
    R0/R1 R/W 60 m (NH-21/22/64, PR-7 - outside this site), R2 50 m,
    R3 30 m, R4 25 m, R5 20 m. Mapping: our sector arterials = R2 (50 m),
    collectors = R4 (25 m), local road cells = R5 (20 m). The residential
    LANE overlay = the plan's own minimum: "The lowest hierarchy street
    within residential zone of Master Plan shall be minimum 40 feet wide"
    (Table 7-1 note ii) = 12.2 m, adopted 12 m. Consistent with URDPFI
    2015 Vol I bands (arterial 50-80, collector 20-30, local 10-20).
    https://www.mohua.gov.in/link/urdpfi-guidelines.php
  * Cycle/foot provision per IRC:103-2012 (pedestrian facilities) +
    IRC:11-2015 (cycle tracks): SEPARATE cycle track + footpath on EVERY
    road class including local (the author; feasible at R5's 20 m,
    infeasible inside a 12 m lane where IRC:103 prescribes shared space) -
    register B8.

All identification is GEOMETRIC (arterial rows/cols + collector lines from
the configured sector size): the geojson round-trip does not persist locked
flags (known trap), so no pass may rely on `cell.locked`.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid, StreetEdge
from core.land_use import LandUse

from .locked_zones import arterial_rows_cols
from .sector_structure import sector_collector_lines

CellId = Tuple[int, int]

# ROW widths in metres (see module docstring for Tier-1 sources - the
# adopted Zirakpur plan's own R2/R4/R5 classes as of).
ROAD_CLASS_SPEC: Dict[str, Dict[str, object]] = {
    "arterial": {
        "width_m": 50.0,          # R2 sector road, Revised Master Plan Zirakpur p63
        "has_cycle_track": True,  # dedicated (IRC:11-2015)
        "has_footpath": True,     # both sides (IRC:103-2012)
        "label": "arterial boulevard",
    },
    "collector": {
        "width_m": 25.0,          # R4, Revised Master Plan Zirakpur p63
        "has_cycle_track": True,
        "has_footpath": True,
        "label": "sector collector",
    },
    "local": {
        "width_m": 20.0,          # R5, Revised Master Plan Zirakpur p63
        "has_cycle_track": True,  # separate track fits at 20 m
        "has_footpath": True,
        "label": "local access street",
    },
}

# Residential LANE overlay (sub-cell street_edges): the plan's own minimum
# street - "lowest hierarchy street within residential zone... minimum 40
# feet wide" (Table 7-1 note ii, Revised Master Plan Zirakpur) = 12.2 m,
# adopted 12 m. Deliberately DECOUPLED from the local ROAD class (R5 20 m)
# so lanes stay lane-width - shared space per IRC:103.
LANE_WIDTH_M = 12.0

LOCAL_STREET_WIDTH_M = LANE_WIDTH_M


def configured_sector_size(cfg: Optional[DistrictConfig] = None) -> int:
    """The ratified sector size in cells sweep winner; config-pinned)."""
    cfg = cfg or load_config()
    return int(cfg.optimisation.get("sector_size_cells", 8))


def structural_road_lines(grid: Grid,
                          cfg: Optional[DistrictConfig] = None
                          ) -> Tuple[Set[int], Set[int]]:
    """All STRUCTURAL road rows/cols: arterials + sector collectors.

    The geometric identity used by the requirements trim (which roads are
    infrastructure vs SA-grown fragments) and by the class tagger below.
    """
    art_rows, art_cols = arterial_rows_cols(grid)
    coll_rows, coll_cols = sector_collector_lines(
        grid, configured_sector_size(cfg))
    return art_rows | coll_rows, art_cols | coll_cols


def tag_road_classes(grid: Grid,
                     cfg: Optional[DistrictConfig] = None) -> Dict[str, int]:
    """Tag every ROAD cell with its road_class + ROW width. Mutates grid.

    Geometric and idempotent: arterial lines win over collector lines at
    crossings (the wider ROW governs the junction); any ROAD cell on
    neither line set is a LOCAL access cell (the trim's kept guards).
    Non-ROAD cells get road_class=None / width 0. Returns counts by class.
    """
    art_rows, art_cols = arterial_rows_cols(grid)
    coll_rows, coll_cols = sector_collector_lines(
        grid, configured_sector_size(cfg))
    counts = {"arterial": 0, "collector": 0, "local": 0}
    for cell in grid.all_cells():
        if cell.land_use != LandUse.ROAD:
            cell.road_class = None
            cell.road_width_m = 0.0
            continue
        if cell.row in art_rows or cell.col in art_cols:
            cls = "arterial"
        elif cell.row in coll_rows or cell.col in coll_cols:
            cls = "collector"
        else:
            cls = "local"
        cell.road_class = cls
        cell.road_width_m = float(ROAD_CLASS_SPEC[cls]["width_m"])
        counts[cls] += 1
    return counts


def _cell_row_area_m2(grid: Grid, cell: Cell,
                      art_rows: Set[int], art_cols: Set[int],
                      coll_rows: Set[int], coll_cols: Set[int]) -> float:
    """ROW area of ONE road cell, overlap-honest at crossings.

    A cell may sit on a row-line and/or a col-line. Each line contributes a
    strip width x cell_size; a crossing counts the union of the two strips
    (w1 x L + w2 x L - w1 x w2), never double-counting the junction square.
    A LOCAL road cell (no structural line) counts one local-width strip.
    """
    L = grid.cell_size_m

    def _w(idx: int, art: Set[int], coll: Set[int]) -> float:
        if idx in art:
            return float(ROAD_CLASS_SPEC["arterial"]["width_m"])
        if idx in coll:
            return float(ROAD_CLASS_SPEC["collector"]["width_m"])
        return 0.0

    w_row = _w(cell.row, art_rows, coll_rows)   # a row-line runs E-W through the cell
    w_col = _w(cell.col, art_cols, coll_cols)   # a col-line runs N-S through the cell
    if w_row > 0.0 and w_col > 0.0:
        return w_row * L + w_col * L - w_row * w_col
    if w_row > 0.0 or w_col > 0.0:
        return max(w_row, w_col) * L
    # SA-grown local access cell kept by the trim guards: one local strip
    # (the R5 CLASS width, not the 12 m lane width - it is a road cell).
    return float(ROAD_CLASS_SPEC["local"]["width_m"]) * L


def road_row_area_m2(grid: Grid,
                     cfg: Optional[DistrictConfig] = None
                     ) -> Dict[str, float]:
    """ROW area (m2) by road class, incl. local street EDGES."""
    art_rows, art_cols = arterial_rows_cols(grid)
    coll_rows, coll_cols = sector_collector_lines(
        grid, configured_sector_size(cfg))
    out = {"arterial": 0.0, "collector": 0.0, "local": 0.0}
    for cell in grid.all_cells():
        if cell.land_use != LandUse.ROAD:
            continue
        if cell.row in art_rows or cell.col in art_cols:
            cls = "arterial"
        elif cell.row in coll_rows or cell.col in coll_cols:
            cls = "collector"
        else:
            cls = "local"
        out[cls] += _cell_row_area_m2(grid, cell, art_rows, art_cols,
                                      coll_rows, coll_cols)
    # Local street SEGMENTS: centre-to-centre length = one cell side each,
    # width 12 m. Connector segments (one endpoint a ROAD cell) count HALF -
    # the road-side half already lies inside the road's own ROW.
    road_ids = {(c.row, c.col) for c in grid.all_cells()
                if c.land_use == LandUse.ROAD}
    lane_len = 0.0
    for e in grid.street_edges:
        if e.kind != "local_street":
            continue
        frac = 0.5 if (e.a in road_ids or e.b in road_ids) else 1.0
        lane_len += frac * grid.cell_size_m
    out["local"] += lane_len * LOCAL_STREET_WIDTH_M
    return out


def developed_area_m2(grid: Grid) -> float:
    """DEVELOPED area = built + road + parking cells (full cell areas).

    The denominator of the B6 road-share metric ("roads+paths ~20% of the
    developed area", the author + gate ballot). Open space,
    blue space and the solar reserve are deliberate non-developed land (the
    green-belt structure) and sit outside the denominator.
    """
    cell_area = grid.cell_size_m ** 2
    n = sum(1 for c in grid.all_cells()
            if c.has_building
            or c.land_use in (LandUse.ROAD, LandUse.PARKING_LOT))
    return n * cell_area


def road_row_report(grid: Grid,
                    cfg: Optional[DistrictConfig] = None
                    ) -> Dict[str, object]:
    """The B6 reporting bundle: ROW area by class + shares. Road is reported
    in ROW AREA everywhere (CLAUDE.md deliverable rule for."""
    by_class = road_row_area_m2(grid, cfg)
    total_row = sum(by_class.values())
    site = grid.total_area_m2
    developed = developed_area_m2(grid)
    n_road_cells = sum(1 for c in grid.all_cells()
                       if c.land_use == LandUse.ROAD)
    n_lanes = sum(1 for e in grid.street_edges if e.kind == "local_street")
    return {
        "row_m2_by_class": {k: round(v, 1) for k, v in by_class.items()},
        "row_km2_total": round(total_row / 1e6, 4),
        "row_share_of_site": round(total_row / site, 4),
        "row_share_of_developed": round(total_row / max(1.0, developed), 4),
        "developed_km2": round(developed / 1e6, 4),
        "road_cells": n_road_cells,
        "road_cell_share_of_site": round(n_road_cells / grid.total_cells, 4),
        "local_street_edges": n_lanes,
        "local_street_km": round(n_lanes * grid.cell_size_m / 1e3, 2),
    }


# ---------------------------------------------------------------------------
# local access streets - POST-anneal deterministic overlay
# ---------------------------------------------------------------------------
# Lanes may not run through water, the solar field, or road cells themselves.
_LANE_IMPASSABLE = {LandUse.ROAD, LandUse.BLUE_SPACE, LandUse.SOLAR_FARM}


def _road_adjacent(grid: Grid, cell: Cell) -> bool:
    return any(n.land_use == LandUse.ROAD
               for n in grid.neighbours_4(cell.row, cell.col))


def assign_local_streets(grid: Grid) -> Dict[str, object]:
    """Route LOCAL access lanes (sub-cell centerline streets) so every BUILT
    cell and every PARKING_LOT fronts the street network. Mutates
    grid.street_edges.

    Algorithm (deterministic, no RNG): multi-source BFS over passable cells
    (anything except road/water/solar) seeded at all road-adjacent cells;
    every unserved built cell then walks its BFS parent chain toward the
    road network, stamping a lane SEGMENT (cell centre to cell centre, see
    StreetEdge geometry) per step, plus a final CONNECTOR segment into the
    adjacent ROAD cell (the junction). Cells the chain passes through are
    served too (the lane runs through them), so branches are shared - the
    "little branches connecting buildings" rather
    than a lane per building.

    Serving rule: a cell is SERVED if it 4-touches a ROAD cell or a lane
    segment starts/ends in it. Carport lots must front a road OR street
 - PARKING_LOT is included in the needy set.
    """
    # replace any previous lane pass (idempotent)
    grid.street_edges = [e for e in grid.street_edges
                         if e.kind != "local_street"]

    passable: Dict[CellId, Cell] = {
        (c.row, c.col): c for c in grid.all_cells()
        if c.land_use not in _LANE_IMPASSABLE
    }
    # BFS distance-to-road over passable cells (parents for chain-walking).
    INF = 10 ** 9
    dist: Dict[CellId, int] = {cid: INF for cid in passable}
    parent: Dict[CellId, Optional[CellId]] = {cid: None for cid in passable}
    q: deque = deque()
    for cid in sorted(passable):
        if _road_adjacent(grid, passable[cid]):
            dist[cid] = 0
            q.append(cid)
    while q:
        cur = q.popleft()
        (r, c) = cur
        for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if nb in passable and dist[nb] > dist[cur] + 1:
                dist[nb] = dist[cur] + 1
                parent[nb] = cur
                q.append(nb)

    needs_frontage = [
        c for c in grid.all_cells()
        if (c.has_building or c.land_use == LandUse.PARKING_LOT)
    ]

    lane_edges: Set[Tuple[CellId, CellId]] = set()
    laned_cells: Set[CellId] = set()   # cells with a lane on some boundary

    def _served(cell: Cell) -> bool:
        cid = (cell.row, cell.col)
        return _road_adjacent(grid, cell) or cid in laned_cells

    def _add_edge(a: CellId, b: CellId) -> None:
        key = (a, b) if a <= b else (b, a)
        if key not in lane_edges:
            lane_edges.add(key)
            laned_cells.add(a)
            laned_cells.add(b)

    unreachable: List[CellId] = []
    # farthest-first so long branches are laid once and nearer cells reuse them
    for cell in sorted(needs_frontage,
                       key=lambda c: (-dist.get((c.row, c.col), INF),
                                      c.row, c.col)):
        cid = (cell.row, cell.col)
        if _served(cell):
            continue
        if dist.get(cid, INF) >= INF:
            unreachable.append(cid)
            continue
        # walk the parent chain toward the road, stamping lane segments;
        # stop as soon as the chain joins an EXISTING lane branch (shared
        # dendritic branches) or reaches a road-adjacent cell, where a
        # final CONNECTOR segment ties the lane into the road cell itself
        # (the junction - without it the lane would float unconnected).
        cur = cid
        while True:
            nxt = parent[cur]
            if nxt is None:
                break                      # already road-adjacent (dist 0)
            joins_existing = nxt in laned_cells
            _add_edge(cur, nxt)
            cur = nxt
            if joins_existing:
                break
            if _road_adjacent(grid, passable[cur]):
                (r, c) = cur
                road_nbs = sorted(
                    (n.row, n.col) for n in grid.neighbours_4(r, c)
                    if n.land_use == LandUse.ROAD)
                _add_edge(cur, road_nbs[0])
                break
        # dist-0 needy cells were skipped by _served (road-adjacent), so a
        # chain always has at least one segment before reaching here.

    grid.street_edges.extend(
        StreetEdge(a=a, b=b, kind="local_street",
                   width_m=LOCAL_STREET_WIDTH_M,
                   modes=("motor", "cycle", "foot"))
        for (a, b) in sorted(lane_edges)
    )

    n_unserved = sum(1 for c in needs_frontage if not _served(c))
    return {
        "lane_edges": len(lane_edges),
        "lane_km": round(len(lane_edges) * grid.cell_size_m / 1e3, 2),
        "frontage_cells_needing": len(needs_frontage),
        "frontage_cells_unserved": n_unserved,
        "unreachable_cells": unreachable,
    }


def cells_with_lane_frontage(grid: Grid) -> Set[CellId]:
    """Cell ids that have a local lane or path-street on some boundary."""
    out: Set[CellId] = set()
    for e in grid.street_edges:
        if e.kind == "local_street":
            out.add(e.a)
            out.add(e.b)
    return out


if __name__ == "__main__":
    from energy.network import grid_from_geojson

    g, name = grid_from_geojson()
    counts = tag_road_classes(g)
    lanes = assign_local_streets(g)
    rep = road_row_report(g)
    print(f"{name}: road classes {counts}")
    print(f"lanes: {lanes['lane_edges']} edges / {lanes['lane_km']} km; "
          f"unserved {lanes['frontage_cells_unserved']}")
    print(f"ROW: {rep['row_km2_total']} km2 = {rep['row_share_of_site']:.1%} "
          f"of site / {rep['row_share_of_developed']:.1%} of developed")
