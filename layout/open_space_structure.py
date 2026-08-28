"""Open-space STRUCTURE pass (Stage- green directive, the author).

Two jobs, both deterministic, both register-0f rows:

1. SOLAR EXPANSION BLOCK (B3 superseded: reserve 225 -> 350 cells = 14% of
   site = 350 MWp base ceiling). On the CURRENT layout the extra 125 cells
   form a clean rectangle of OPEN_SPACE cells in the NORTH BELT (rows above
   the central arterial, away from the town core - "land for the solar
   farm, not idle green"). Only OPEN_SPACE cells are consumed; built cells,
   parks near residential, blue space and roads are never touched. Future
   re-anneals derive the full 350 via apply_locked_zones instead.

2. OPEN-SPACE SUBTYPE TAGGING ("structured parks, not random fields - this
   is a town, not a village"). Every remaining OPEN_SPACE cell gets an
   `amenity_subtype` tag (the existing per-cell hover/subtype field - same
   mechanism as SCHOOL primary/secondary, so the geojson schema is
   unchanged and the viewer can render each class distinctly):

     park_community      - the largest contiguous open cluster serving each
                           quadrant's residents (URDPFI community-park tier)
     park_neighbourhood  - open cells within walking reach (<= 300 m) of
                           residential (URDPFI housing/neighbourhood tier)
     greenway            - open cells fronting the arterial skeleton
                           (avenue green; hosts the cycle/foot spine)
     expansion_reserve_2042 / expansion_reserve_2055
                         - the PHASED-DEVELOPMENT LAND BANK (the author: the
                           town must GROW across the periods; reserve sized
                           by proximity to the developed core - nearest
                           parcels develop first)
     greenbelt           - the perimeter/deep-belt residual

   Tag budget: parks capped at the URDPFI 12 m2/cap allowance (300 cells at
   250k); the remainder splits reserve-2042 / reserve-2055 / greenbelt by
   distance to the developed core. Tags are REPORTING/RENDERING structure -
   land_use stays OPEN_SPACE, so the energy model and constraints are
   byte-identical.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid
from core.land_use import LandUse

from .locked_zones import arterial_rows_cols

CellId = Tuple[int, int]

PARK_CELL_BUDGET = 300          # URDPFI 12 m2/cap x 250k / 1 ha
NEIGHBOURHOOD_RADIUS_CELLS = 3  # <= 300 m walk to a doorstep park


def add_solar_expansion_block(grid: Grid, extra_cells: int = 125
                              ) -> Dict[str, object]:
    """Convert a clean north-belt rectangle of OPEN_SPACE to SOLAR_FARM.

    Deterministic scan: widest clean rectangle anchored from the north-west
    interior, skipping arterial rows/cols, only OPEN_SPACE accepted. Falls
    back to row-major fill of open belt cells if no full rectangle exists.
    """
    art_rows, art_cols = arterial_rows_cols(grid)
    n = grid.n_rows
    mid = n // 2

    def _ok(r: int, c: int) -> bool:
        if r in art_rows or c in art_cols:
            return False
        cell = grid.at(r, c)
        return cell.land_use == LandUse.OPEN_SPACE and not cell.locked

    # CONTIGUOUS region-grow (v2, the rectangle scan found no
    # clean 125-cell rectangle in the belt - blue parks + scattered cells
    # break it up - and its row-major fallback produced "solar confetti"
    # (20 components, flagged by solar_farm_clustering). A solar field is
    # a contiguous blob: BFS-grow from the densest corner of the LARGEST
    # open connected component in the north belt; if that component is
    # smaller than the ask, continue in the next-largest (each blob is
    # still >= the 4-cell clustering minimum).
    from collections import deque

    open_ids: Set[CellId] = {(c.row, c.col) for c in grid.all_cells()
                             if c.row > mid and _ok(c.row, c.col)}
    comps: List[List[CellId]] = []
    seen: Set[CellId] = set()
    for cid in sorted(open_ids):
        if cid in seen:
            continue
        comp = []
        dq = deque([cid])
        seen.add(cid)
        while dq:
            (r, c) = dq.popleft()
            comp.append((r, c))
            for nb in ((r-1, c), (r+1, c), (r, c-1), (r, c+1)):
                if nb in open_ids and nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        comps.append(comp)
    comps.sort(key=lambda comp: (-len(comp), comp[0]))

    best: List[CellId] = []
    for comp in comps:
        if len(best) >= extra_cells:
            break
        comp_set = set(comp)
        # seed at the deepest-north, most-central corner of the component
        seed = min(comp, key=lambda rc: (-rc[0], abs(rc[1] - n // 2)))
        grown: List[CellId] = []
        grown_set: Set[CellId] = set()
        dq = deque([seed])
        grown_set.add(seed)
        while dq and len(best) + len(grown) < extra_cells:
            cur = dq.popleft()
            grown.append(cur)
            (r, c) = cur
            for nb in sorted(((r-1, c), (r+1, c), (r, c-1), (r, c+1)),
                             key=lambda rc: (-rc[0], rc[1])):
                if nb in comp_set and nb not in grown_set:
                    grown_set.add(nb)
                    dq.append(nb)
        if len(grown) >= 4:                 # respect the cluster minimum
            best.extend(grown)

    for (r, c) in best:
        cell = grid.at(r, c)
        cell.land_use = LandUse.SOLAR_FARM
        cell.locked = True
        cell.albedo = 0.30
        cell.vegetation_fraction = 0.10
        cell.amenity_subtype = None
    return {"solar_expansion_cells": len(best),
            "anchor": best[0] if best else None}


def tag_open_space_structure(grid: Grid,
                             cfg: Optional[DistrictConfig] = None
                             ) -> Dict[str, int]:
    """Tag every OPEN_SPACE cell with a structure subtype. Mutates grid."""
    if cfg is None:
        cfg = load_config()
    art_rows, art_cols = arterial_rows_cols(grid)

    # STAGE-: exclude campus_grounds cells - they belong to a
    # facility campus (tagged by layout.building_footprints, which runs first)
    # and must keep that tag, not be re-tagged as parks/belt.
    # STAGE-B18.4: also PRESERVE the pre-anneal LOCKED green
    # structure (3 big parks + the greenway spine, layout/park_structure.py)
    # - their subtypes are planned structure, not this tagger's to reassign.
    #: the locked solar ring + agri band join the
    # preserved set - pre-anneal planned structure, not this tagger's to
    # reassign (caught by the dress rehearsal).
    open_cells = [c for c in grid.all_cells()
                  if c.land_use == LandUse.OPEN_SPACE
                  and c.amenity_subtype != "campus_grounds"
                  and not (c.locked and (c.amenity_subtype or "") in
                           ("park_community", "greenway",
                            "solar_expansion_2042", "solar_expansion_2055",
                            "agri_belt"))]
    res_ids = {(c.row, c.col) for c in grid.all_cells()
               if c.land_use.is_residential}
    built_ids = {(c.row, c.col) for c in grid.all_cells()
                 if c.has_building or c.land_use == LandUse.PARKING_LOT}

    def _near(ids: Set[CellId], cell: Cell, k: int) -> bool:
        return any(abs(cell.row - r) + abs(cell.col - c) <= k
                   for (r, c) in ids)

    def _dist(ids: Set[CellId], cell: Cell) -> int:
        return min(abs(cell.row - r) + abs(cell.col - c)
                   for (r, c) in ids) if ids else 10 ** 6

    # --- greenways: open cells fronting the STRUCTURAL road network ------
    # STAGE-: collectors joined the structural network, so
    # avenue green now fronts arterials AND sector collectors (the boulevard
    # planting strip of every structural street, not just the arterial cross).
    from .road_network import structural_road_lines
    struct_rows, struct_cols = structural_road_lines(grid, cfg)
    tags: Dict[CellId, str] = {}
    for c in open_cells:
        if any(nb.land_use == LandUse.ROAD
               and (nb.row in struct_rows or nb.col in struct_cols)
               for nb in grid.neighbours_4(c.row, c.col)):
            tags[(c.row, c.col)] = "greenway"

    # --- community parks: biggest contiguous open cluster per quadrant --
    def _clusters(cells: List[Cell]) -> List[List[Cell]]:
        ids = {(c.row, c.col): c for c in cells}
        seen: Set[CellId] = set()
        out = []
        for cid, cell in ids.items():
            if cid in seen:
                continue
            comp = []
            dq = deque([cid])
            seen.add(cid)
            while dq:
                cur = dq.popleft()
                comp.append(ids[cur])
                (r, c) = cur
                for nb in ((r-1, c), (r+1, c), (r, c-1), (r, c+1)):
                    if nb in ids and nb not in seen:
                        seen.add(nb)
                        dq.append(nb)
            out.append(comp)
        return out

    # B18.4: the locked big parks count against the URDPFI park budget too
    # (they ARE community parks - the budget stays 12 m2/cap honest).
    park_count = sum(1 for c in grid.all_cells()
                     if c.land_use == LandUse.OPEN_SPACE and c.locked
                     and c.amenity_subtype == "park_community")
    untagged = [c for c in open_cells if (c.row, c.col) not in tags]
    mid_r, mid_c = grid.n_rows / 2.0, grid.n_cols / 2.0
    by_quadrant: Dict[int, List[List[Cell]]] = {0: [], 1: [], 2: [], 3: []}
    for comp in _clusters(untagged):
        # only clusters that actually serve residents
        if not any(_near(res_ids, c, 5) for c in comp):
            continue
        head = comp[0]
        q = (2 if head.row >= mid_r else 0) + (1 if head.col >= mid_c else 0)
        by_quadrant[q].append(comp)
    for q, comps in sorted(by_quadrant.items()):
        comps.sort(key=lambda comp: (-len(comp),
                                     comp[0].row, comp[0].col))
        if comps:
            take = comps[0][:40]           # cap one community park ~40 ha
            for c in take:
                tags[(c.row, c.col)] = "park_community"
            park_count += len(take)

    # --- neighbourhood parks: SECTOR GREENS, 2-5 acres each (B18.8) -----
    # Chandigarh" - every sector carries its own small green. On the 1-ha
    # grid that band is EXACTLY 1-2 cells (2.47 / 4.94 acres; URDPFI
    # neighbourhood-park tier ~0.5-2 ha agrees). So: round-robin across
    # the SECTORS, each pass giving one sector its best candidate cell
    # (nearest residents) plus at most ONE adjacent partner (cluster cap
    # = 2 cells), never touching an existing neighbourhood green - until
    # the URDPFI budget runs out. Chandigarh's sector-green pattern,
    # deterministic.
    from .road_network import configured_sector_size
    from .sector_structure import sector_id_of
    sec_size = configured_sector_size(cfg)
    cands = [c for c in open_cells if (c.row, c.col) not in tags
             and _near(res_ids, c, NEIGHBOURHOOD_RADIUS_CELLS)]
    by_sector: Dict[Tuple[int, int], List[Cell]] = {}
    for c in cands:
        by_sector.setdefault(sector_id_of(grid, c.row, c.col, sec_size),
                             []).append(c)
    for pool in by_sector.values():
        pool.sort(key=lambda c: (_dist(res_ids, c), c.row, c.col))

    def _adjacent_to_green(r: int, c: int) -> bool:
        return any(tags.get(nb) == "park_neighbourhood"
                   for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)))

    progressing = True
    while park_count < PARK_CELL_BUDGET and progressing:
        progressing = False
        for sec in sorted(by_sector):
            if park_count >= PARK_CELL_BUDGET:
                break
            pool = by_sector[sec]
            while pool and ((pool[0].row, pool[0].col) in tags
                            or _adjacent_to_green(pool[0].row, pool[0].col)):
                pool.pop(0)
            if not pool:
                continue
            head = pool.pop(0)
            tags[(head.row, head.col)] = "park_neighbourhood"
            park_count += 1
            progressing = True
            # optional partner: the best 4-adjacent candidate (cap 2 cells);
            # the partner may touch the HEAD only - never another green,
            # else two pairs would merge past the 5-acre band
            if park_count < PARK_CELL_BUDGET:
                def _touches_other_green(c: Cell) -> bool:
                    return any(
                        tags.get(nb) == "park_neighbourhood"
                        and nb != (head.row, head.col)
                        for nb in ((c.row - 1, c.col), (c.row + 1, c.col),
                                   (c.row, c.col - 1), (c.row, c.col + 1)))
                partner = next(
                    (c for c in pool
                     if abs(c.row - head.row) + abs(c.col - head.col) == 1
                     and (c.row, c.col) not in tags
                     and not _touches_other_green(c)), None)
                if partner is not None:
                    pool.remove(partner)
                    tags[(partner.row, partner.col)] = "park_neighbourhood"
                    park_count += 1

    # --- phased reserve + belt by distance to the developed core --------
    # STAGE-B18.6: the DEEP belt (farthest from the
    # core - including the land the solar-farm grant no longer takes) is
    # PRODUCTIVE agri/orchard land until phased development consumes it
    # (GMADA land-pooling reality; feeds the B19 food-flow line + marginal
    # local straw for the CHP). The nearest slice of the tail stays
    # greenbelt (the town's visual/climatic buffer).
    rest = [c for c in open_cells if (c.row, c.col) not in tags]
    rest.sort(key=lambda c: (_dist(built_ids, c), c.row, c.col))
    n_rest = len(rest)
    n_2042 = n_rest * 2 // 5
    n_2055 = n_rest * 2 // 5
    tail = n_rest - n_2042 - n_2055
    n_belt = tail * 2 // 5                  # nearest 40% of the tail
    #: when the LOCKED agri perimeter band exists
    # (layout/f6_locks.py - preserved by the open_cells filter above), the
    # deep-tail slice becomes greenbelt instead of a SECOND agri scatter -
    # one band, one meaning (caught by the dress rehearsal: 14 locked +
    # ~20 deep-tail = 34 confetti agri cells otherwise).
    locked_band_exists = any(
        c.locked and c.amenity_subtype == "agri_belt"
        for c in grid.all_cells())
    for i, c in enumerate(rest):
        if i < n_2042:
            tags[(c.row, c.col)] = "expansion_reserve_2042"
        elif i < n_2042 + n_2055:
            tags[(c.row, c.col)] = "expansion_reserve_2055"
        elif i < n_2042 + n_2055 + n_belt:
            tags[(c.row, c.col)] = "greenbelt"
        else:
            tags[(c.row, c.col)] = ("greenbelt" if locked_band_exists
                                    else "agri_belt")

    counts: Dict[str, int] = {}
    for c in open_cells:
        tag = tags.get((c.row, c.col), "greenbelt")
        c.amenity_subtype = tag
        counts[tag] = counts.get(tag, 0) + 1
    return counts


# Subtypes an agri band may claim (never structure: parks/greenway/canal/
# campus/sector greens, never the solar/parking growth parcels).
_BAND_CLAIMABLE = {"", "greenbelt", "agri_belt",
                   "expansion_reserve_2042", "expansion_reserve_2055"}


def apply_agri_perimeter_band(grid: Grid, n_cells: int = 20) -> Dict[str, int]:
    """Re-stamp the agri/orchard belt as a CONTIGUOUS band on the site edge.

.4 fix: the B18.6 rule tagged the
    cells FARTHEST from the developed core, which scattered 20 confetti
    cells with zero on the boundary - not a belt. GMADA-style peri-urban
    agri land wraps the town edge, so the band now lives in the outer two
    rings by construction: largest connected run first, BFS growth keeps
    every added cell touching the band. Existing agri_belt tags elsewhere
    revert to greenbelt. Deterministic; report-only (tags never move
    land use, demand or energy).
    """
    n_rows = len(grid.cells)
    n_cols = len(grid.cells[0])

    # ANNEAL SKIP-GUARD: when the band was PRE-LOCKED on the
    # seed grid (layout/f6_locks.apply_agri_band_lock) the locked cells
    # already form the planned single run - keep them, never re-stamp
    # (re-stamping would tear up the planned band).
    locked_band = sum(1 for c in grid.all_cells()
                      if c.amenity_subtype == "agri_belt" and c.locked)
    if locked_band >= max(1, n_cells - 6):
        return {"agri_band_cells": locked_band, "agri_band_prelocked": 1}

    def _ring(c: Cell) -> int:
        return min(c.row, c.col, n_rows - 1 - c.row, n_cols - 1 - c.col)

    # 1. clear the old scatter
    cleared = 0
    for c in grid.all_cells():
        if c.amenity_subtype == "agri_belt":
            c.amenity_subtype = "greenbelt"
            cleared += 1

    # 2. candidates: open space in the outer SIX rings - the production
    # site's outermost rings are the boundary road + greenway + canal +
    # farm, so the band hugs the edge as tightly as the built form allows.
    # Sector greens (park_neighbourhood) may be claimed - each one is
    # RE-ISSUED on a claimable cell in the same sector afterwards (pure
    # OPEN_SPACE tag swaps; zero energy impact).
    cand = {(c.row, c.col): c for c in grid.all_cells()
            if c.land_use == LandUse.OPEN_SPACE and _ring(c) <= 6
            and ((c.amenity_subtype or "") in _BAND_CLAIMABLE
                 or c.amenity_subtype == "park_neighbourhood")
            and not c.locked}
    roads = {(c.row, c.col) for c in grid.all_cells()
             if c.land_use == LandUse.ROAD}

    def _bridged_nbs(cid: Tuple[int, int]):
        """Direct 4-neighbours plus one-cell jumps across a road (the
        band runs along the boundary road; a field interrupted by a road
        crossing is still one belt)."""
        r, cc = cid
        for nb in ((r - 1, cc), (r + 1, cc), (r, cc - 1), (r, cc + 1)):
            if nb in cand:
                yield nb
            elif nb in roads:
                rr, rc = nb
                for nb2 in ((rr - 1, rc), (rr + 1, rc),
                            (rr, rc - 1), (rr, rc + 1)):
                    if nb2 in cand and nb2 != cid:
                        yield nb2

    # 3. bridged components, biggest first
    seen: Set[Tuple[int, int]] = set()
    comps: List[List[CellId]] = []
    for cid in sorted(cand):
        if cid in seen:
            continue
        comp, stack = [], [cid]
        seen.add(cid)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in _bridged_nbs(cur):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        comps.append(comp)
    comps.sort(key=lambda c: (-len(c),
                              min(_ring(cand[x]) for x in c),
                              min(c)))

    # 4. take bridged-BFS subsets, biggest component first
    taken: List[CellId] = []
    for comp in comps:
        if len(taken) >= n_cells:
            break
        comp_set = set(comp)
        start = min(comp)
        dq, comp_seen = deque([start]), {start}
        while dq and len(taken) < n_cells:
            cur = dq.popleft()
            taken.append(cur)
            for nb in sorted(_bridged_nbs(cur)):
                if nb in comp_set and nb not in comp_seen:
                    comp_seen.add(nb)
                    dq.append(nb)

    # 5. ATOMIC green claims: keep a taken green ONLY if a same-sector
    # replacement exists (re-tagged in the same step); otherwise release
    # it back and take the next candidate. Sector-green count conserved.
    sector = 8
    taken_set = set(taken)
    pool = {(c.row, c.col): c for c in grid.all_cells()
            if c.land_use == LandUse.OPEN_SPACE
            and (c.amenity_subtype or "") in _BAND_CLAIMABLE
            and not c.locked and (c.row, c.col) not in taken_set}
    kept: List[CellId] = []
    claimed = reissued = 0
    for cid in taken:
        if cand[cid].amenity_subtype != "park_neighbourhood":
            kept.append(cid)
            continue
        gr, gc = cid
        sec = (gr // sector, gc // sector)
        cands = sorted(
            (rid for rid in pool
             if (rid[0] // sector, rid[1] // sector) == sec),
            key=lambda rid: (abs(rid[0] - gr) + abs(rid[1] - gc), rid))
        if cands:
            pool.pop(cands[0]).amenity_subtype = "park_neighbourhood"
            kept.append(cid)
            claimed += 1
            reissued += 1
        # else: green stays a green - band is one cell shorter here
    for cid in kept:
        cand[cid].amenity_subtype = "agri_belt"

    return {"cleared_old": cleared, "band_cells": len(kept),
            "band_component_sizes": _component_count(kept),
            "greens_claimed": claimed,
            "greens_reissued": reissued}


def _component_count(cells: List[Tuple[int, int]]) -> List[int]:
    s = set(cells)
    seen: set = set()
    sizes: List[int] = []
    for cid in sorted(s):
        if cid in seen:
            continue
        n, stack = 0, [cid]
        seen.add(cid)
        while stack:
            r, cc = stack.pop()
            n += 1
            for nb in ((r - 1, cc), (r + 1, cc), (r, cc - 1), (r, cc + 1)):
                if nb in s and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        sizes.append(n)
    return sizes


if __name__ == "__main__":
    from core.demographics import load_demand_norms, load_demographics
    from energy.network import grid_from_geojson

    g, name = grid_from_geojson()
    s1 = add_solar_expansion_block(g)
    s2 = tag_open_space_structure(g)
    print(f"{name}: {s1}")
    for k, v in sorted(s2.items()):
        print(f"  {k:<24} {v}")
