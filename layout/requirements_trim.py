"""Post-anneal REQUIREMENTS TRIM (Stage-.

Why this exists (register 0f follow-up): the SA's `area_targets` hard
constraint tolerates +/-3 percentage points ABSOLUTE per class - calibrated
at 200 m where every built class held 1-4% of 625 cells. At the 100 m
re-grid the sub-1% classes (hotel 0.04%, restaurant 0.08%, office 0.24%...)
gained enormous RELATIVE slack, and the catchment/frontage soft metrics
happily converted ~113 surplus cells into demand-heavy commercial uses
(restaurants 27 vs 2 required, hotels 20 vs 1, malls 34 vs 17...) plus 117
scattered non-arterial ROAD fragments (65 disconnected components). That
inflates demand +25% above the FX-3 reconciliation and households +5.4% -
both Stage- acceptance failures.

The remedy follows the locked-zones philosophy: counts that
are DEMAND-DERIVED (URDPFI/IPHS norms x population) are not the SA's to
grow - the SA decides WHERE, the norms decide HOW MANY. This deterministic
post-anneal pass:

  1. trims every over-supplied BUILT class back to its required cell count,
     KEEPING the best-placed cells (road-fronted first, then nearest the
     residential centre of mass, then (row, col) for determinism) and
     converting the surplus to OPEN_SPACE;
  2. converts non-locked ROAD cells (SA-grown fragments) to OPEN_SPACE -
     at the road network IS the locked arterial skeleton; collectors/
     locals arrive at Stage by design. Fragments that are the ONLY road
     within the 600 m access radius of some built cell are KEPT (guard set)
     so `road_proximity` cannot regress;
  3. leaves under-supplied or exactly-supplied classes untouched, and never
     touches locked cells, SOLAR_FARM, OPEN_SPACE, BLUE_SPACE or PARKING_LOT
     (parking is demand-sized and road-frontage-constrained; blue/open are
     area-fillers).

Floor accounting: trimmed cells lose their buildings entirely, so the
bottom-up household/demand totals return to the requirement-pinned values
the FX-3 reconciliation certified. Trim of RESIDENTIAL classes prefers
MEDIUM-tier cells (never the spine-gradient TALL/SHORT cells) so the
floor-conserving gradient bookkeeping stays intact.

Deterministic: no RNG; stable sort keys throughout.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid, HeightTier
from core.land_use import LandUse
from core.requirements import Requirements

CellId = Tuple[int, int]

# Classes the trim may touch (built, demand-derived counts). Open/blue/road/
# solar are handled specially or never trimmed.
# STAGE-B18.3: PARKING_LOT joined the trimmable set - it is now
# FLEET-CONSTRAINED demand-derived (17 cells at 2030, core/parking_demand.py),
# so SA over-supply must trim like any demand-derived class. The keep-rule
# prefers road-fronted cells first, which IS
# street" requirement (parking_road_frontage stays a hard constraint too).
_TRIMMABLE = (
    LandUse.RESIDENTIAL_LOW, LandUse.RESIDENTIAL_MID, LandUse.RESIDENTIAL_HIGH,
    LandUse.SCHOOL, LandUse.OFFICE, LandUse.SHOPPING_CENTRE,
    LandUse.RETAIL_HIGHSTREET, LandUse.RESTAURANT_FOOD,
    LandUse.HOTEL_GUESTHOUSE, LandUse.HEALTHCARE, LandUse.LIGHT_INDUSTRY,
    LandUse.WAREHOUSE, LandUse.PUBLIC_SERVICES, LandUse.RELIGIOUS,
    LandUse.PARKING_LOT,
)


def _to_open(cell: Cell) -> None:
    """Convert a cell to OPEN_SPACE with the generator's defaults."""
    cell.land_use = LandUse.OPEN_SPACE
    cell.height_m = 0.0
    cell.height_tier = None
    cell.albedo = 0.25
    cell.vegetation_fraction = 0.85
    cell.entrance_sides = []
    cell.amenity_subtype = None
    cell.faith = None
    cell.is_carport_site = False
    cell.building_axis_deg = 0.0


def apply_requirements_trim(grid: Grid,
                            requirements: Requirements,
                            cfg: Optional[DistrictConfig] = None
                            ) -> Dict[str, object]:
    """Trim SA over-supply back to required counts. Mutates ``grid``.

    Returns a summary dict for the register/logbook.
    """
    if cfg is None:
        cfg = load_config()

    # Review fix: frontage must be ranked
    # against the STABLE road network, not the full pre-trim road set -
    # otherwise the keep-rule prefers cells fronted by SA fragments that
    # step 2 then deletes, silently un-fronting kept amenities.
    # STAGE-: the stable network is now arterials + the locked
    # sector COLLECTOR grid, identified GEOMETRICALLY via
    # layout.road_network.structural_road_lines (locked flags do not survive
    # the geojson round-trip - known trap).
    from .road_network import structural_road_lines
    art_rows_f, art_cols_f = structural_road_lines(grid, cfg)
    stable_road_set = {(c.row, c.col) for c in grid.all_cells()
                       if c.land_use == LandUse.ROAD
                       and (c.locked or c.row in art_rows_f
                            or c.col in art_cols_f)}

    def _road_fronted(cell: Cell) -> bool:
        return any((n.row, n.col) in stable_road_set
                   for n in grid.neighbours_4(cell.row, cell.col))

    # Residential centre of mass = the demand the amenities should serve.
    res_cells = [c for c in grid.all_cells() if c.land_use.is_residential]
    if res_cells:
        com_r = sum(c.row for c in res_cells) / len(res_cells)
        com_c = sum(c.col for c in res_cells) / len(res_cells)
    else:
        com_r = grid.n_rows / 2.0
        com_c = grid.n_cols / 2.0

    counts = defaultdict(int)
    for c in grid.all_cells():
        counts[c.land_use] += 1

    summary_trims: Dict[str, int] = {}

    # Catchment-serving classes keep by GREEDY MAXIMUM COVERAGE, not
    # centre-of-mass proximity (trim v5, the v4 COM rule kept
    # 6 central clinics and un-served a far quadrant - caught by the
    # catchment self-check below; review finding 4 made concrete). Radii
    # come from the same YAML the hard constraints read.
    catchment_radius_m = {
        LandUse.HEALTHCARE: float(
            cfg.constraint_catchments_m.get("healthcare", 2500.0)),
        LandUse.SCHOOL: float(
            cfg.constraint_catchments_m.get("school", 1000.0)),
        LandUse.RELIGIOUS: float(
            cfg.constraint_catchments_m.get("religious", 800.0)),
    }

    def _coverage_keep(pool: List[Cell], required: int,
                       radius_m: float) -> List[Cell]:
        """Greedy set-cover: pick `required` cells maximising residential
        coverage within radius (Manhattan, metres); ties broken by
        road-fronted first, then (row, col). Deterministic."""
        radius_cells_c = radius_m / max(1.0, grid.cell_size_m)
        uncovered = {(c.row, c.col) for c in res_cells}
        chosen: List[Cell] = []
        remaining = list(pool)
        while remaining and len(chosen) < required:
            best = None
            best_key = None
            for cand in remaining:
                gain = sum(1 for (r, cc) in uncovered
                           if abs(cand.row - r) + abs(cand.col - cc)
                           <= radius_cells_c)
                key = (-gain, 0 if _road_fronted(cand) else 1,
                       cand.row, cand.col)
                if best_key is None or key < best_key:
                    best, best_key = cand, key
            chosen.append(best)
            remaining.remove(best)
            uncovered = {(r, cc) for (r, cc) in uncovered
                         if abs(best.row - r) + abs(best.col - cc)
                         > radius_cells_c}
        return chosen

    # ---- 1. trim over-supplied built classes --------------------------
    for lu in _TRIMMABLE:
        required = int(requirements.required_cells_by_landuse.get(lu, 0))
        have = counts[lu]
        if have <= required or required <= 0:
            continue
        pool = [c for c in grid.all_cells()
                if c.land_use == lu and not c.locked]
        #: LOCKED cells
        # (the highstreet chain, the hospital campus - layout/f6_locks.py)
        # already satisfy their share of the requirement, so only the
        # REMAINDER may be kept from the unlocked pool. The old
        # pool[:required] arithmetic ignored them and would have shipped
        # locked + required = over-supplied classes at the production run
        # (e.g. 7 locked + 7 kept = 14 highstreet vs the required 7).
        n_locked = have - len(pool)
        required_unlocked = max(0, required - n_locked)
        if lu in catchment_radius_m:
            keep = _coverage_keep(pool, required_unlocked,
                                  catchment_radius_m[lu])
            keep_ids = {(c.row, c.col) for c in keep}
            drop = [c for c in pool if (c.row, c.col) not in keep_ids]
        else:
            # Keep-preference: road-fronted first, then closest to the
            # residential centre of mass, then stable (row, col).
            pool.sort(key=lambda c: (
                0 if _road_fronted(c) else 1,
                abs(c.row - com_r) + abs(c.col - com_c),
                c.row, c.col,
            ))
            keep = pool[:required_unlocked]
            drop = pool[required_unlocked:]
        # Residential guard: never drop spine-gradient TALL/SHORT cells
        # (floor-conserving bookkeeping); swap such cells back into keep.
        if lu in (LandUse.RESIDENTIAL_LOW, LandUse.RESIDENTIAL_MID):
            protected = [c for c in drop if c.height_tier in
                         (HeightTier.TALL, HeightTier.SHORT)]
            if protected:
                swappable = [c for c in keep
                             if c.height_tier == HeightTier.MEDIUM]
                for p in protected:
                    if not swappable:
                        break
                    s = swappable.pop()
                    keep.remove(s)
                    keep.append(p)
                    drop.remove(p)
                    drop.append(s)
        for c in drop:
            _to_open(c)
        summary_trims[lu.value] = len(drop)

    # ---- 1b. PARKING_LOT under-supply TOP-UP (B18.3 fix,) ----
    # The B18 rehearsal caught the gap: parking is now demand-derived (17
    # cells at 2030) but the trim only CUTS over-supply - an SA run that
    # lands short shipped an under-parked town. Mirror rule (same
    # locked-zones philosophy): top up to the required count by converting
    # the best-placed OPEN_SPACE cells - ROAD-FRONTED (the hard
    # parking_road_frontage semantic + and
    # nearest the JOB-heavy cells (where the day-peak demand lives).
    # Deterministic; never touches locked/tagged green structure.
    required_park = int(requirements.required_cells_by_landuse.get(
        LandUse.PARKING_LOT, 0))
    have_park = sum(1 for c in grid.all_cells()
                    if c.land_use == LandUse.PARKING_LOT)
    if required_park > have_park:
        job_ids = {(c.row, c.col) for c in grid.all_cells()
                   if c.land_use in (LandUse.OFFICE, LandUse.LIGHT_INDUSTRY,
                                     LandUse.WAREHOUSE,
                                     LandUse.SHOPPING_CENTRE,
                                     LandUse.HEALTHCARE,
                                     LandUse.PUBLIC_SERVICES)}

        def _job_dist(c: Cell) -> int:
            if not job_ids:
                return 0
            return min(abs(c.row - r) + abs(c.col - cc)
                       for (r, cc) in job_ids)

        # Convertible pool: UNTAGGED open space (the pre-tagging pipeline
        # state) OR reserve-class tags (robust if a tagged grid is
        # re-trimmed) - never parks/greenways/campus grounds/expansion
        # parcels (same philosophy as layout/phased_expansion._RETAGGABLE).
        # TWO TIERS: (1) cells already touching ANY road; (2) job-near
        # cells with no road neighbour - legitimate because the lane
        # overlay (assign_local_streets, runs later) serves every
        # PARKING_LOT cell with a local street, and
        # frontage on "a road OR STREET" (parking_road_frontage accepts
        # lanes accordingly).
        _convertible = {"", "expansion_reserve_2042", "expansion_reserve_2055",
                        "greenbelt", "agri_belt"}

        def _any_road(c: Cell) -> bool:
            return any(n.land_use == LandUse.ROAD
                       for n in grid.neighbours_4(c.row, c.col))

        base = [c for c in grid.all_cells()
                if c.land_use == LandUse.OPEN_SPACE and not c.locked
                and (c.amenity_subtype or "") in _convertible]
        tier1 = [c for c in base if _any_road(c)]
        tier2 = [c for c in base if not _any_road(c)]
        tier1.sort(key=lambda c: (_job_dist(c), c.row, c.col))
        tier2.sort(key=lambda c: (_job_dist(c), c.row, c.col))
        pool = tier1 + tier2
        topped = 0
        for c in pool[:required_park - have_park]:
            c.land_use = LandUse.PARKING_LOT
            c.height_m = 0.0
            c.height_tier = None
            c.albedo = 0.18                     # asphalt lot (generator default)
            c.vegetation_fraction = 0.05
            c.amenity_subtype = None
            topped += 1
        summary_trims["parking_topped_up"] = topped

    # ---- 2. non-structural ROAD fragments -> open (guard road_proximity) --
    # The structural network (arterial skeleton + STAGE- sector collector
    # grid) is identified GEOMETRICALLY, not by cell.locked: the geojson
    # round-trip does not persist locked flags, and the skeleton is
    # infrastructure regardless of building proximity (same convention as
    # spine_gradient). Anything off the structural lines is an SA-grown
    # fragment; survivors of the guards below become LOCAL access cells
    # (tag_road_classes classes them "local").
    art_rows, art_cols = art_rows_f, art_cols_f
    frag_roads = [c for c in grid.all_cells()
                  if c.land_use == LandUse.ROAD
                  and c.row not in art_rows and c.col not in art_cols
                  and not c.locked]
    locked_roads = {(c.row, c.col) for c in grid.all_cells()
                    if c.land_use == LandUse.ROAD
                    and (c.locked or c.row in art_rows or c.col in art_cols)}
    max_cells = max(1, round(600.0 / max(1.0, grid.cell_size_m)))

    def _served_by_locked(cell: Cell) -> bool:
        return any(abs(cell.row - r) + abs(cell.col - c) <= max_cells
                   for (r, c) in locked_roads)

    # Built cells whose 600 m road access depends on SA fragments:
    needy = [c for c in grid.all_cells()
             if c.has_building and not _served_by_locked(c)]
    guard: set = set()
    for nc in needy:
        # keep the nearest fragment road (deterministic tie-break)
        best = None
        best_key = None
        for fr in frag_roads:
            d = abs(nc.row - fr.row) + abs(nc.col - fr.col)
            if d <= max_cells:
                key = (d, fr.row, fr.col)
                if best_key is None or key < best_key:
                    best, best_key = fr, key
        if best is not None:
            guard.add((best.row, best.col))

    # FRONTAGE guard (trim v3,): three categories carry a HARD
    # adjacency semantic that must survive the fragment trim - HEALTHCARE
    # (ambulance access, `hospital_near_road`), PARKING_LOT (vehicles,
    # `parking_road_frontage`; hard-won at the re-anneal) and
    # RETAIL_HIGHSTREET (a bazaar IS on a road, `highstreet_road_frontage`).
    # For any such cell whose ONLY 4-neighbour road(s) are fragments, keep
    # the deterministic first fragment. The softer frontage families
    # (schools/shops/offices - `amenities_road_frontage`, the corridor
    # contiguity) are DOCUMENTED residuals, same family as at 200 m.
    frag_set = {(c.row, c.col) for c in frag_roads}
    frontage_kept = 0
    for cell in grid.all_cells():
        if cell.land_use not in (LandUse.HEALTHCARE, LandUse.PARKING_LOT,
                                 LandUse.RETAIL_HIGHSTREET):
            continue
        nbrs = grid.neighbours_4(cell.row, cell.col)
        road_nbrs = [(n.row, n.col) for n in nbrs
                     if n.land_use == LandUse.ROAD]
        if not road_nbrs:
            continue
        if any(rc in locked_roads or
               (rc in guard) for rc in road_nbrs):
            continue  # already fronted by skeleton or an access-kept fragment
        frag_nbrs = sorted(rc for rc in road_nbrs if rc in frag_set)
        if frag_nbrs:
            guard.add(frag_nbrs[0])
            frontage_kept += 1

    dropped_roads = 0
    for c in frag_roads:
        if (c.row, c.col) not in guard:
            _to_open(c)
            dropped_roads += 1
    summary_trims["road_fragments"] = dropped_roads
    summary_trims["road_fragments_kept_for_access"] = len(guard) - frontage_kept
    summary_trims["road_fragments_kept_for_frontage"] = frontage_kept

    converted = sum(v for k, v in summary_trims.items()
                    if k not in ("road_fragments_kept_for_access",
                                 "road_fragments_kept_for_frontage"))

    # Review fix: the trim can touch
    # catchment-serving classes (healthcare, school, religious), so verify
    # the catchment constraints POST-trim and surface any regression loudly
    # in the summary instead of relying on someone re-running the panel.
    catchment_regressions = []
    try:
        from .constraints import (
            check_amenity_equity, check_park_quadrant_coverage,
            check_religious_catchment, check_school_catchment,
        )
        for res in (check_school_catchment(grid),
                    check_religious_catchment(grid),
                    check_amenity_equity(grid),
                    check_park_quadrant_coverage(grid)):
            if not res.passes:
                catchment_regressions.append(f"{res.name} gap={res.gap:.3f}")
    except Exception as exc:  # pragma: no cover - diagnostic only
        catchment_regressions.append(f"catchment re-check failed: {exc}")

    return {
        "trimmed": summary_trims,
        "total_cells_converted": int(converted),
        "catchment_regressions": catchment_regressions or "none",
    }


if __name__ == "__main__":
    from core.demographics import load_demand_norms, load_demographics
    from core.requirements import derive_requirements
    from energy.network import grid_from_geojson

    grid, name = grid_from_geojson()
    req = derive_requirements(load_demographics(), load_demand_norms(),
                              load_config())
    out = apply_requirements_trim(grid, req)
    print(f"trim summary for {name}: {out}")
