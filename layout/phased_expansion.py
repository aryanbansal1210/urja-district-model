"""PHASED EXPANSION PARCELS for solar + parking (register B18.1/B18.3,
 - "the town grows across the periods, and so do its farm and
its parking").

Runs POST-anneal, AFTER tag_open_space_structure (it re-tags a subset of
the generic expansion_reserve_* / greenbelt cells with SPECIFIC purposes):

  * solar_expansion_2042 / solar_expansion_2055 - the phased land grant's
    growth parcels, chosen ADJACENT to the locked solar farm (a farm grows
    at its own fence line, not in fragments across town). Counts from
    economics.yaml `multi_period.farm_land_cells_by_period` (the B18.1
    grant schedule): cells(2042) - cells(2030) and cells(2055) - cells(2042).
  * parking_expansion_2042 / parking_expansion_2055 - future lots, chosen
    nearest the JOB-heavy cells (office/industry/mall/healthcare - where
    the day-parking demand lives), road-fronting preferred. Counts from
    requirements.parking_cells_by_period increments.

Tags are amenity_subtype values on OPEN_SPACE cells - land_use unchanged,
demand unchanged, energy byte-identical (same mechanism as the B13 green
structure). The viewer renders them as "Phase 2/3" land; the energy side's
per-period ceilings (farm land + carport growth) tell the SAME story on
the supply side. Deterministic (sorted scans, no RNG).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid
from core.land_use import LandUse

CellId = Tuple[int, int]

# Reserve-class subtypes we may re-tag (never parks/greenways/campus/canal).
_RETAGGABLE = {"expansion_reserve_2042", "expansion_reserve_2055", "greenbelt"}

_JOB_USES = (LandUse.OFFICE, LandUse.LIGHT_INDUSTRY, LandUse.WAREHOUSE,
             LandUse.SHOPPING_CENTRE, LandUse.HEALTHCARE,
             LandUse.PUBLIC_SERVICES)


def _retaggable_cells(grid: Grid) -> List[Cell]:
    pool = [c for c in grid.all_cells()
            if c.land_use == LandUse.OPEN_SPACE
            and (c.amenity_subtype or "") in _RETAGGABLE]
    if pool:
        return pool
    # Fallback (grids where tag_open_space_structure has not run, e.g.
    # fresh pre-anneal seeds in tests/tools): plain UNTAGGED open space.
    # Never parks/greenways/campus/canal - those carry their own subtypes.
    return [c for c in grid.all_cells()
            if c.land_use == LandUse.OPEN_SPACE
            and not (c.amenity_subtype or "")
            and not c.locked]


def _bfs_distance_to(grid: Grid, sources: Set[CellId]) -> Dict[CellId, int]:
    from collections import deque
    INF = 10 ** 9
    dist: Dict[CellId, int] = {}
    dq = deque()
    for cid in sorted(sources):
        dist[cid] = 0
        dq.append(cid)
    while dq:
        r, c = dq.popleft()
        for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= nb[0] < grid.n_rows and 0 <= nb[1] < grid.n_cols \
                    and nb not in dist:
                dist[nb] = dist[(r, c)] + 1
                dq.append(nb)
    return dist


def apply_phased_expansion(grid: Grid,
                           parking_cells_by_period: Dict[str, int],
                           cfg: Optional[DistrictConfig] = None,
                           farm_land_cells_by_period: Optional[Dict[str, int]]
                           = None) -> Dict[str, int]:
    """Re-tag reserve parcels as solar/parking growth land. Mutates grid.

    Parameters
    ----------
    parking_cells_by_period : {"2030": n, "2042": n, "2055": n}
        From requirements (B18.3); increments become parking_expansion_*.
    farm_land_cells_by_period : {"2030": n, "2042": n, "2055": n}
        The B18.1 grant schedule; increments become solar_expansion_*.
        Defaults to economics.yaml multi_period.farm_land_cells_by_period
        (absent -> no solar expansion tagged, e.g. pre-B18 configs).
    """
    cfg = cfg or load_config()
    if farm_land_cells_by_period is None:
        try:
            from energy.costs import load_economics
            mp = load_economics().multi_period_config()
            farm_land_cells_by_period = mp.get("farm_land_cells_by_period")
        except Exception:
            farm_land_cells_by_period = None

    counts: Dict[str, int] = {}

    # ---- solar growth: CONTIGUOUS ring grown from the farm fence ---------
    #.3 fix: the old version sorted
    # the retaggable pool by distance but never required ADJACENCY, so when
    # the fence ring held few retaggable cells it scattered 64 confetti
    # clusters across town (3/100 touching the farm). A farm expansion is a
    # ring at the fence BY CONSTRUCTION now: every taken cell must touch the
    # farm or an already-taken cell (greedy nearest-first flood), with plain
    # untagged open space and the agri belt as fallback tiers when the
    # reserve-tag pool starves (the agri band re-stamps itself afterwards -
    # green today, panels when the grant unlocks =.
    if farm_land_cells_by_period:
        # ANNEAL SKIP-GUARD: when the ring was PRE-LOCKED on
        # contiguity fix), the tags already satisfy the grant schedule and
        # survive the anneal as locked cells - re-stamping here would tear
        # up the planned ring. Count first; skip when satisfied.
        _pre = {"solar_expansion_2042": 0, "solar_expansion_2055": 0}
        for c in grid.all_cells():
            if (c.amenity_subtype or "") in _pre:
                _pre[c.amenity_subtype] += 1
        _f30 = int(farm_land_cells_by_period.get("2030", 0))
        _f42 = int(farm_land_cells_by_period.get("2042", _f30))
        _f55 = int(farm_land_cells_by_period.get("2055", _f42))
        if (_pre["solar_expansion_2042"] >= max(0, _f42 - _f30)
                and _pre["solar_expansion_2055"] >= max(0, _f55 - _f42)):
            counts.update(_pre)
            counts["solar_ring_prelocked"] = 1
            farm_land_cells_by_period = None   # solar section done; parking below

    if farm_land_cells_by_period:
        farm_ids = {(c.row, c.col) for c in grid.all_cells()
                    if c.land_use == LandUse.SOLAR_FARM}
        dist = _bfs_distance_to(grid, farm_ids)

        def _tier(c: Cell) -> int:
            sub = c.amenity_subtype or ""
            if sub in _RETAGGABLE:
                return 0
            if not sub and not c.locked:
                return 1
            if sub == "agri_belt":
                return 2
            #.3: sector greens (park_neighbourhood) MAY be
            # claimed at the farm fence - each claimed green is RE-ISSUED
            # on a claimable cell in the same sector afterwards, so the
            # "every sector has its 2-5 acre green" promise holds. Pure
            # tag swaps between OPEN_SPACE cells: zero energy impact.
            if sub == "park_neighbourhood":
                return 3
            return 99  # community parks / greenway / canal / campus: never

        by_id: Dict[CellId, Cell] = {(c.row, c.col): c for c in grid.all_cells()
                                     if c.land_use == LandUse.OPEN_SPACE
                                     and _tier(c) < 99}
        f30 = int(farm_land_cells_by_period.get("2030", 0))
        f42 = int(farm_land_cells_by_period.get("2042", f30))
        f55 = int(farm_land_cells_by_period.get("2055", f42))
        need = [("solar_expansion_2042", max(0, f42 - f30)),
                ("solar_expansion_2055", max(0, f55 - f42))]
        region: Set[CellId] = set(farm_ids)

        road_ids = {(c.row, c.col) for c in grid.all_cells()
                    if c.land_use == LandUse.ROAD}

        def _adjacent_to_region(cid: CellId) -> bool:
            # direct fence contact, OR a one-cell jump ACROSS a road (the
            # production farm is ringed by the boundary road - a farm
            # expanding across a road is normal peri-urban form)
            r, cc = cid
            for nb in ((r-1, cc), (r+1, cc), (r, cc-1), (r, cc+1)):
                if nb in region:
                    return True
                if nb in road_ids:
                    rr, rc = nb
                    for nb2 in ((rr-1, rc), (rr+1, rc), (rr, rc-1), (rr, rc+1)):
                        if nb2 in region:
                            return True
            return False

        def _frontier() -> List[CellId]:
            out = [cid for cid in by_id
                   if cid not in region and _adjacent_to_region(cid)]
            # nearest fence first, cheapest tier first, deterministic
            out.sort(key=lambda cid: (dist.get(cid, 10 ** 9),
                                      _tier(by_id[cid]), cid))
            return out

        # ATOMIC green claims: a park_neighbourhood cell is claimed ONLY if
        # its same-sector replacement exists RIGHT NOW (found and re-tagged
        # in the same step) - sector-green count is conserved exactly.
        sector = 8
        reserved: Set[CellId] = set()
        claimed = reissued = 0
        for tag, n in need:
            taken = 0
            while taken < n:
                frontier = [cid for cid in _frontier() if cid not in reserved]
                if not frontier:
                    break  # nothing adjacent left - report the shortfall
                cid = frontier[0]
                if (by_id[cid].amenity_subtype or "") == "park_neighbourhood":
                    gr, gc = cid
                    sec = (gr // sector, gc // sector)
                    repl = sorted(
                        (rid for rid, c in by_id.items()
                         if rid not in region and rid not in reserved
                         and rid != cid
                         and (c.amenity_subtype or "") in _RETAGGABLE | {""}
                         and (rid[0] // sector, rid[1] // sector) == sec),
                        key=lambda rid: (abs(rid[0] - gr) + abs(rid[1] - gc),
                                         rid))
                    if not repl:
                        reserved.add(cid)   # unclaimable - skip permanently
                        continue
                    by_id[repl[0]].amenity_subtype = "park_neighbourhood"
                    reserved.add(repl[0])
                    claimed += 1
                    reissued += 1
                by_id[cid].amenity_subtype = tag
                region.add(cid)
                taken += 1
            counts[tag] = taken
        counts["greens_claimed"] = claimed
        counts["greens_reissued"] = reissued

    # ---- parking growth: nearest jobs, ROAD/LANE FRONTAGE REQUIRED -------
    #.5 fix: the old version only PREFERRED road frontage, so
    # 14/16 reserved lots ended up unreachable. A future lot with no access
    # is not a lot: frontage is now a hard filter (road neighbour today, or
    # a local-street lane where the overlay exists).
    p30 = int(parking_cells_by_period.get("2030", 0))
    p42 = int(parking_cells_by_period.get("2042", p30))
    p55 = int(parking_cells_by_period.get("2055", p42))
    job_ids = {(c.row, c.col) for c in grid.all_cells()
               if c.land_use in _JOB_USES}
    if job_ids:
        dist_j = _bfs_distance_to(grid, job_ids)
        try:
            from layout.road_network import cells_with_lane_frontage
            laned = cells_with_lane_frontage(grid)
        except Exception:
            laned = set()

        def _has_frontage(c: Cell) -> bool:
            if any(n.land_use == LandUse.ROAD
                   for n in grid.neighbours_4(c.row, c.col)):
                return True
            return (c.row, c.col) in laned

        pool = sorted(
            (c for c in _retaggable_cells(grid)
             if not (c.amenity_subtype or "").startswith("solar_expansion")
             and _has_frontage(c)),
            key=lambda c: (dist_j.get((c.row, c.col), 10 ** 9),
                           c.row, c.col))
        # shortfall tier: fronted sector greens with ATOMIC in-sector
        # re-issue (the tag counts feed phased_land_multipliers, so the
        # 2042/2055 increments MUST be met exactly to keep the energy
        # ceilings - and pins - unchanged).
        greens = sorted(
            (c for c in grid.all_cells()
             if c.land_use == LandUse.OPEN_SPACE and not c.locked
             and c.amenity_subtype == "park_neighbourhood"
             and _has_frontage(c)),
            key=lambda c: (dist_j.get((c.row, c.col), 10 ** 9),
                           c.row, c.col))
        sector = 8
        used: set = set()
        pk_claimed = pk_reissued = 0
        need = [("parking_expansion_2042", max(0, p42 - p30)),
                ("parking_expansion_2055", max(0, p55 - p42))]
        # tier 3: fronted
        # UNLOCKED greenway cells. The open-space tagger assigns greenway to
        # every arterial/collector-fronting green BY CONSTRUCTION, so when
        # the reserve pool + sector greens starve (both live in sector
        # interiors), the road corridor's own green is the honest place a
        # future lot goes (a parking lot ON the road corridor - standard
        # form). Greenway is abundant (~400 cells); no re-issue needed.
        greenway_pool = sorted(
            (c for c in grid.all_cells()
             if c.land_use == LandUse.OPEN_SPACE and not c.locked
             and c.amenity_subtype == "greenway"
             and _has_frontage(c)),
            key=lambda c: (dist_j.get((c.row, c.col), 10 ** 9),
                           c.row, c.col))
        i = 0
        gi = 0
        wi = 0
        for tag, n in need:
            taken = 0
            while taken < n and i < len(pool):
                pool[i].amenity_subtype = tag
                used.add((pool[i].row, pool[i].col))
                taken += 1
                i += 1
            while taken < n and wi < len(greenway_pool):
                wcell = greenway_pool[wi]
                wi += 1
                if (wcell.row, wcell.col) in used:
                    continue
                wcell.amenity_subtype = tag
                used.add((wcell.row, wcell.col))
                taken += 1
            while taken < n and gi < len(greens):
                gcell = greens[gi]
                gi += 1
                gid = (gcell.row, gcell.col)
                if gid in used or gcell.amenity_subtype != "park_neighbourhood":
                    continue
                sec = (gcell.row // sector, gcell.col // sector)
                repl = sorted(
                    ((c.row, c.col) for c in _retaggable_cells(grid)
                     if (c.row, c.col) not in used
                     and not (c.amenity_subtype or "").startswith("solar_expansion")
                     and ((c.row // sector, c.col // sector) == sec)),
                    key=lambda rid: (abs(rid[0] - gcell.row)
                                     + abs(rid[1] - gcell.col), rid))
                if not repl:
                    continue
                rid = repl[0]
                rcell = next(c for c in grid.all_cells()
                             if (c.row, c.col) == rid)
                rcell.amenity_subtype = "park_neighbourhood"
                used.add(rid)
                gcell.amenity_subtype = tag
                used.add(gid)
                pk_claimed += 1
                pk_reissued += 1
                taken += 1
            counts[tag] = taken
        if pk_claimed:
            counts["parking_greens_claimed"] = pk_claimed
            counts["parking_greens_reissued"] = pk_reissued

    return counts


if __name__ == "__main__":
    from core.demographics import load_demand_norms, load_demographics
    from core.requirements import derive_requirements
    from energy.network import grid_from_geojson

    g, name = grid_from_geojson()
    cfg = load_config()
    req = derive_requirements(load_demographics(), load_demand_norms(), cfg)
    out = apply_phased_expansion(g, req.parking_cells_by_period, cfg,
                                 farm_land_cells_by_period={"2030": 150,
                                                            "2042": 200,
                                                            "2055": 250})
    print(f"{name}: {out}")
