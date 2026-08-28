"""Layout scoring metrics for the Pareto-front comparison.

Each metric is a pure function over a Grid (and config / requirements where
relevant). Returns are normalised to [0, 1] where **higher = better** so
they combine straightforwardly into a weighted sum.

----------------------------------------------------------------------------
IMPLEMENTATION STATUS  (single source of truth: _spec/IMPLEMENTATION_STATUS.md)
----------------------------------------------------------------------------
This file currently implements 9 of ~80 metrics in the design spec. Pending
items are tracked in `_spec/IMPLEMENTATION_STATUS.md` with a priority queue.

Tier 1 (implement BEFORE the energy MILP, all layout-stage):
  - albedo / cool-roof fraction (B.1)
  - composite heat-island index (B.1)
  - anthropogenic heat clustering penalty (B.1)
  - street alignment to prevailing wind (B.2)
  - tree shading along pedestrian routes (B.3)
  - cool walking-route shadability EWS->amenity (B.3)
  - distance to nearest cool refuge (B.5)
  - mixed-use ratio within 400 m (C)
  - land-use Shannon diversity (C)
  - walkable destinations count per cell (C)
  - connected vegetation corridor index (B.5)
  - block-permeability index (D)
  - service-equity variance (D)
  - building orientation E-W axis (A)
  - sky-view factor per residential cell (A / B.4)
  - roof-use split: PV / greenery / unused per cell (H.1)
  - street-tree density as a decision per ROAD cell (H.3)
  - bus-stop placement per ROAD cell (H.2)
  - solar streetlight density per ROAD cell (H.2)
  - EV-charging-hub placement (H.2)

Tier 2 (during energy MILP build, energy-data-dependent):
  - energy cost as % of EWS income (F)
  - diurnal generation-vs-demand match (A)
  - curtailment risk (A)
  - daytime/evening load co-location (C)
  - service reliability variance (F)

Tier 3 (polish, after layout + energy end-to-end work):
  - vertical mixed-use, vibrancy, frontage (C)
  - cycling network, trip diversity, severance (D)
  - bifacial / BIPV / soiling / structural (A)
  - air quality, disaster exposure variance (F)

DO NOT remove this header without first updating IMPLEMENTATION_STATUS.md.

Metrics currently implemented (subset of A, D, F from the design-factors spec):

  A. Solar / rooftop generation
     - solar_capacity_score:   total deployable PV vs target
     - solar_access_score:     fewer "shadowed-from-south" cells = better

  D. Transport / accessibility ("15-minute city")
     - access_to_school:       1 - mean residential walk distance / 800 m
     - access_to_commercial:   1 - mean residential walk distance / 600 m
     - access_to_healthcare:   1 - mean residential walk distance / 1200 m
     - 15min_coverage:         fraction of residential cells within 1200 m
                               of all 3 amenities

  F. Equity
     - ews_amenity_access:     EWS mean amenity distance vs all-residential
                               mean (ratio inverted so ~1 = equal access)
     - mid_ews_adjacency:      adjacent (mid OR low)+(low OR mid) pairs
                               normalised by neighbour count
     - ews_heat_shielding:     mean vegetation_fraction near EWS cells

`score_layout` runs all of them and returns a dict; `weighted_score`
collapses to a single number for the simulated annealer's objective.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from core.shading_constants import (
    PV_SHADING_DELTA_M, GROUND_PV_PANEL_TOP_M,
)


from core.config import DistrictConfig, load_config
from core.demographics import DemandNorms, load_demand_norms
from core.grid import Cell, Grid
from core.land_use import LandUse
from core.requirements import Requirements
from core.building import building_from_cell


# Walking distance norms (m). Indian planning practice puts schools at 400-800 m,
# commercial at 400-600 m, hospitals at 1500-2000 m. We score full credit at or
# under these distances.
TARGET_WALK_M = {
    "school": 800.0,
    "commercial": 600.0,
    "healthcare": 1500.0,
}
COVERAGE_RADIUS_M = 1200.0
MIXED_USE_RADIUS_M = 400.0
COOL_REFUGE_TARGET_M = 600.0
WATER_BODY_TARGET_M = 600.0
NEIGHBOURHOOD_RADIUS_M = 400.0
DESTINATION_TYPES_TARGET = 5     # distinct amenity types treated as "complete"
SVF_HEIGHT_NORMALISER_M = 24.0   # tall residential reference height for SVF


# ---------------------------------------------------------------------------
# A. Solar
# ---------------------------------------------------------------------------
def solar_capacity_score(grid: Grid,
                          requirements: Requirements,
                          cfg: Optional[DistrictConfig] = None,
                          norms: Optional[DemandNorms] = None,
                          ) -> float:
    """Total deployable PV (rooftop + ground-mount) divided by target.

    Capped at 1.0. Higher is better.

    Returns
    -------
    float
        Normalised PV-capacity score in [0, 1].
    """
    cfg = cfg or load_config()
    norms = norms or load_demand_norms()

    rooftop_kwp = 0.0
    for cell in grid.all_cells():
        b = building_from_cell(cell, cfg)
        if b is not None:
            rooftop_kwp += b.deployable_pv_kwp

    # ground-mount: SOLAR_FARM cells * area * kWp/m^2
    cell_area_m2 = grid.cell_size_m ** 2
    ground_kwp_per_m2 = norms.solar.get("ground_mount_kwp_per_m2", 0.10)
    ground_kwp = (
        len(grid.cells_of(LandUse.SOLAR_FARM))
        * cell_area_m2 * ground_kwp_per_m2
    )

    total_kwp = rooftop_kwp + ground_kwp
    target = max(1.0, requirements.solar_kwp_total)
    return min(1.0, total_kwp / target)


def solar_access_score(grid: Grid) -> float:
    """Penalise PV-bearing cells (built rooftops AND ground-mount solar farms)
    that are shadowed from the south by tall neighbouring buildings.

    For each PV-bearing cell, check the three southern directions (S, SW, SE)
    and the two adjacent east / west directions. If any of those neighbours
    is significantly taller than this cell, mark the cell as shadowed.
    Ground-mount solar (SOLAR_FARM) is treated as ~1.5 m tall, so any tall
    building neighbour shades it.

    Score = fraction of PV-bearing cells NOT shadowed. 1.0 = no shadowing.

    Returns
    -------
    float
        Fraction of PV-bearing cells not shadowed by nearby taller cells.
    """
    return _solar_access_for(
        grid,
        cells=[c for c in grid.all_cells()
                if c.has_building or c.land_use == LandUse.SOLAR_FARM],
    )


def solar_farm_residential_buffer_score(grid: Grid) -> float:
    """Reward SOLAR_FARM cells that are NOT 4-adjacent to residential cells.

 (Codex placement-audit follow-up, Claude 2): the placement
    audit `outputs/data/placement_audit.md` flagged 21 SOLAR_FARM cells
    4-adjacent to residential cells -- the largest category in the audit
    after the amenity-no-road set. Real ground-mount PV arrays carry
    visual / noise / nighttime-glare nuisances that residents reasonably
    object to; published Indian PV-siting guidance (MNRE, CEA) recommends
    50-100 m buffers. At 200 m grid resolution, "not 4-adjacent" enforces
    a >= 200 m buffer, which is in the upper half of that range.

    Score = fraction of SOLAR_FARM cells with NO RESIDENTIAL_*
    4-neighbour. 1.0 = every SOLAR_FARM cell has a clean buffer; 0.0 =
    every SOLAR_FARM cell butts up against residential. Returns 1.0 if
    no SOLAR_FARM cells exist (no signal to optimise).

    Soft rather than HARD because peri-urban Punjab solar farms DO sit
    close to villages in many real cases; the metric nudges the SA
    toward cleaner separations without forbidding the realistic edge
    case. Weight tuned in DEFAULT_WEIGHTS.
    """
    farms = [c for c in grid.all_cells() if c.land_use == LandUse.SOLAR_FARM]
    if not farms:
        return 1.0
    residential_lus = {LandUse.RESIDENTIAL_LOW, LandUse.RESIDENTIAL_MID,
                        LandUse.RESIDENTIAL_HIGH}
    clean = 0
    for f in farms:
        nbs = grid.neighbours_4(f.row, f.col)
        if not any(n.land_use in residential_lus for n in nbs):
            clean += 1
    return clean / len(farms)


def solar_farm_solar_access(grid: Grid) -> float:
    """SOLAR_FARM-only variant of ``solar_access_score``.

: the mixed metric dilutes
    SOLAR_FARM shading violations (~25 cells) against built-cell PV
    (~1200 cells), letting the SA optimiser place ground-mount arrays
    next to tall buildings (cell (7,8) on the on-disk SA layout has
    S=18m W=18m E=27m neighbours -> heavily shaded). Splitting the
    metric and giving the SOLAR_FARM variant its own DEFAULT_WEIGHTS
    entry lets the optimiser see an undiluted signal.

    Score = fraction of SOLAR_FARM cells NOT shadowed. 1.0 = perfect.
    Returns 1.0 if no SOLAR_FARM cells exist.
    """
    return _solar_access_for(
        grid,
        cells=[c for c in grid.all_cells() if c.land_use == LandUse.SOLAR_FARM],
    )


def _solar_access_for(grid: Grid, cells) -> float:
    """Helper: shared shading-check logic for solar_access_score variants."""
    #: single source of truth, core/shading_constants.py
    SHADOW_DELTA_M = PV_SHADING_DELTA_M       # 6.0 m = 2 storeys
    GROUND_PV_HEIGHT_M = GROUND_PV_PANEL_TOP_M

    if not cells:
        return 1.0

    south_checks = [(-1, -1), (-1, 0), (-1, 1)]
    flank_checks = [(0, -1), (0, 1)]

    shadowed = 0
    for c in cells:
        my_height = (c.height_m if c.has_building else GROUND_PV_HEIGHT_M)
        is_shadowed = False
        for dr, dc in south_checks + flank_checks:
            nr, nc = c.row + dr, c.col + dc
            if 0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols:
                nb = grid.at(nr, nc)
                if nb.height_m - my_height > SHADOW_DELTA_M:
                    is_shadowed = True
                    break
        if is_shadowed:
            shadowed += 1

    return 1.0 - (shadowed / len(cells))


# ---------------------------------------------------------------------------
# A.2 Solar farm clustering (layout-stage proxy for fixed costs and
# economies of scale on ground-mount installations)
# ---------------------------------------------------------------------------
def solar_cluster_score(grid: Grid,
                         min_cluster_size: int = 4,
                         ideal_components: int = 1,
                         ) -> float:
    """Reward compact solar-farm installations; penalise scattered fragments.

    1.0 = all SOLAR_FARM cells in <= ideal_components clusters, all of size
          >= min_cluster_size.
    Heavier penalty for singletons than for slightly-too-small clusters.

 (the author ask "I want the solar-farm cells all bunched up
    together"): default `ideal_components` lowered 2 -> 1 so a layout with
    a single contiguous solar block beats one split into a big block + a
    satellite. Each extra component now costs a flat
    `_EXTRA_COMPONENT_PENALTY` (0.15) rather than the old tiny
    `0.5 * extra / n_cells`, so the SA has a real incentive to merge the
    satellite into the main field.

    Returns
    -------
    float
        Normalised solar-farm clustering score in [0, 1].
    """
    _EXTRA_COMPONENT_PENALTY = 0.15
    from collections import deque
    coords = {(c.row, c.col) for c in grid.all_cells()
              if c.land_use == LandUse.SOLAR_FARM}
    if not coords:
        # No solar farm = neutral score (the capacity metric will penalise this
        # if the requirement is unmet).
        return 0.5

    # 4-connected components
    remaining = set(coords)
    components: List[Set[Tuple[int, int]]] = []
    while remaining:
        start = next(iter(remaining))
        comp = {start}
        q = deque([start])
        remaining.discard(start)
        while q:
            r, c = q.popleft()
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nb = (r + dr, c + dc)
                if nb in remaining:
                    remaining.discard(nb)
                    comp.add(nb)
                    q.append(nb)
        components.append(comp)

    n_components = len(components)
    n_cells = len(coords)
    cells_in_big = sum(len(c) for c in components if len(c) >= min_cluster_size)
    big_share = cells_in_big / n_cells

    # Reward big-cluster share; charge a flat penalty per component beyond
    # the ideal so the SA prefers ONE contiguous field over a field + a
    # satellite. (Old formula divided by n_cells, making the penalty
    # negligible — a 19+5 split scored a near-perfect 0.98.)
    extra_components = max(0, n_components - ideal_components)
    score = big_share - _EXTRA_COMPONENT_PENALTY * extra_components
    return max(0.0, min(1.0, score))


def open_space_cluster_score(grid: Grid,
                              min_cluster_size: int = 4,
                              ) -> float:
    """Reward connected, usable parks; penalise green-confetti singletons.

    1.0 = all OPEN_SPACE cells live in clusters of >= min_cluster_size.

    Returns
    -------
    float
        Share of open-space cells in clusters of at least `min_cluster_size`.
    """
    from collections import deque
    coords = {(c.row, c.col) for c in grid.all_cells()
              if c.land_use == LandUse.OPEN_SPACE}
    if not coords:
        return 0.5  # neutral; area-target check handles "no parks" elsewhere

    remaining = set(coords)
    components: List[Set[Tuple[int, int]]] = []
    while remaining:
        start = next(iter(remaining))
        comp = {start}
        q = deque([start])
        remaining.discard(start)
        while q:
            r, c = q.popleft()
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nb = (r + dr, c + dc)
                if nb in remaining:
                    remaining.discard(nb)
                    comp.add(nb)
                    q.append(nb)
        components.append(comp)

    n_cells = len(coords)
    cells_in_big = sum(len(c) for c in components if len(c) >= min_cluster_size)
    return cells_in_big / n_cells


# ---------------------------------------------------------------------------
# E. Energy-infrastructure proxy (layout-stage; full MILP comes later)
# ---------------------------------------------------------------------------
def infrastructure_distance_score(grid: Grid) -> float:
    """Reward layouts where solar-farm cells are close to roads (HV cable
    grouting along ROAD only) and where high-demand cells cluster together.

    Two sub-components, equally weighted:

      * solar_to_road: 1.0 if every SOLAR_FARM cell touches or is within 2
        cells of a ROAD; 0 if the average distance is >= 5 cells.
      * high_demand_compactness: 1.0 if SHOPPING_CENTRE / OFFICE / WAREHOUSE
        / LIGHT_INDUSTRY cells form connected clusters; lower if they're
        scattered.

    1.0 = perfect; 0.0 = worst.

    Returns
    -------
    float
        Combined road-proximity and demand-compactness proxy score in [0, 1].
    """
    from collections import deque

    # --- solar farm to road distance ---
    solar_coords = [(c.row, c.col) for c in grid.all_cells()
                    if c.land_use == LandUse.SOLAR_FARM]
    road_coords = {(c.row, c.col) for c in grid.all_cells()
                    if c.land_use == LandUse.ROAD}

    if solar_coords and road_coords:
        # multi-source BFS from roads
        INF = 10**9
        dist = [[INF] * grid.n_cols for _ in range(grid.n_rows)]
        q: deque = deque()
        for (r, c) in road_coords:
            dist[r][c] = 0
            q.append((r, c))
        while q:
            r, c = q.popleft()
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols:
                    if dist[nr][nc] > dist[r][c] + 1:
                        dist[nr][nc] = dist[r][c] + 1
                        q.append((nr, nc))
        mean_d = sum(dist[r][c] for r, c in solar_coords) / len(solar_coords)
        # full credit at <=2 cells; zero at >=5
        solar_to_road = max(0.0, min(1.0, (5.0 - mean_d) / 3.0))
    else:
        solar_to_road = 1.0  # nothing to penalise

    # --- high-demand compactness ---
    high_demand_uses = {
        LandUse.SHOPPING_CENTRE, LandUse.OFFICE,
        LandUse.WAREHOUSE, LandUse.LIGHT_INDUSTRY,
    }
    coords = {(c.row, c.col) for c in grid.all_cells()
              if c.land_use in high_demand_uses}
    if coords:
        remaining = set(coords)
        components = 0
        while remaining:
            start = next(iter(remaining))
            comp = {start}
            q = deque([start])
            remaining.discard(start)
            while q:
                r, c = q.popleft()
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nb = (r + dr, c + dc)
                    if nb in remaining:
                        remaining.discard(nb)
                        comp.add(nb)
                        q.append(nb)
            components += 1
        # full credit if components <= ceil(n_cells / 6) -> roughly 6 cells
        # per cluster; zero if every cell is its own component.
        ideal = max(1, len(coords) // 6)
        compactness = max(0.0, min(1.0, 1.0 - (components - ideal) / len(coords)))
    else:
        compactness = 1.0

    return 0.5 * solar_to_road + 0.5 * compactness


# ---------------------------------------------------------------------------
# D. Transport / accessibility
# ---------------------------------------------------------------------------
def _residential_cells(grid: Grid) -> List[Cell]:
    return [c for c in grid.all_cells() if c.is_residential]


def _ews_cells(grid: Grid) -> List[Cell]:
    return [c for c in grid.all_cells()
            if c.land_use == LandUse.RESIDENTIAL_LOW]


def _amenity_cells(grid: Grid, kind: str) -> List[Cell]:
    """kind in {school, commercial, healthcare}."""
    if kind == "school":
        return grid.cells_of(LandUse.SCHOOL)
    if kind == "commercial":
        return [c for c in grid.all_cells() if c.land_use in (
            LandUse.SHOPPING_CENTRE, LandUse.RESTAURANT_FOOD,
        )]
    if kind == "healthcare":
        return grid.cells_of(LandUse.HEALTHCARE)
    raise ValueError(f"unknown amenity kind {kind!r}")


def _mean_walk_to_amenity(residents: List[Cell],
                           amenities: List[Cell]) -> float:
    """Mean Manhattan distance (m) from each resident to the nearest amenity.

    Returns +inf if there are no amenities and >0 residents.
    """
    if not residents:
        return 0.0
    if not amenities:
        return float("inf")
    total = 0.0
    for r in residents:
        d = min(Grid.manhattan_distance(r, a) for a in amenities)
        total += d
    return total / len(residents)


def access_score_for(grid: Grid, kind: str) -> float:
    """Distance score for a given amenity kind.

    score = max(0, 1 - mean_walk / target_walk). 1.0 if everyone is at the
    target distance or closer; 0.0 if mean walk >= 2x target.

    Returns
    -------
    float
        Normalised accessibility score for the requested amenity kind.
    """
    target = TARGET_WALK_M[kind]
    residents = _residential_cells(grid)
    amenities = _amenity_cells(grid, kind)
    mean_d = _mean_walk_to_amenity(residents, amenities)
    if mean_d == float("inf"):
        return 0.0
    return max(0.0, min(1.0, 1.0 - (mean_d - target) / target))


# Per-amenity service radii for the population-catchment metric.
# Derived from URDPFI 2014 Table 2 + IPHS 2022 healthcare norms +
# CPHEEO 2019 public-services manual. Walking radii where the user is
# expected to reach the facility on foot, vehicular for the
# for full parameter-table sourcing.
CATCHMENT_RADIUS_M: Dict[str, float] = {
    "healthcare": 5000.0,            # vehicular (CHC / hospital — URDPFI 1/100k)
    "school": 800.0,                 # walking (URDPFI primary 1/5k)
    "public_services": 2000.0,       # walking (URDPFI admin / RWA 1/50k)
    "shopping_centre": 5000.0,       # vehicular (URDPFI mall 1/100k)
    "shopping_local": 800.0,         # walking (URDPFI convenience 1/10k -- restaurant_food + retail_highstreet)
    "religious": 800.0,              # walking (URDPFI community-hall 1/5k)
}
# Weights inside the population-catchment composite. Sum-to-1 per the
# spec; healthcare + school dominate because they are highest-frequency
# resident needs (school daily, healthcare weekly).
CATCHMENT_WEIGHTS: Dict[str, float] = {
    "healthcare": 0.22,
    "school": 0.22,
    "public_services": 0.15,
    "shopping_centre": 0.13,
    "shopping_local": 0.18,
    "religious": 0.10,
}


def coverage_15_minute(grid: Grid,
                        radius_m: float = COVERAGE_RADIUS_M,
                        ) -> float:
    """Fraction of residential cells within `radius_m` of ALL three amenity
    kinds (school + commercial + healthcare). 1.0 = perfect 15-min city.

    Returns
    -------
    float
        Share of residential cells covered by all required amenity classes.
    """
    residents = _residential_cells(grid)
    if not residents:
        return 0.0
    schools = _amenity_cells(grid, "school")
    commercial = _amenity_cells(grid, "commercial")
    healthcare = _amenity_cells(grid, "healthcare")
    if not (schools and commercial and healthcare):
        return 0.0

    covered = 0
    for r in residents:
        ok = (
            min(Grid.manhattan_distance(r, a) for a in schools) <= radius_m
            and min(Grid.manhattan_distance(r, a) for a in commercial) <= radius_m
            and min(Grid.manhattan_distance(r, a) for a in healthcare) <= radius_m
        )
        if ok:
            covered += 1
    return covered / len(residents)


# ---------------------------------------------------------------------------
#:
# Reward layouts whose hospitals / schools / public services / shopping
# centres / religious cells actually serve the residents that live in
# the district, not just the right COUNT of each. Catchment populations
# are derived from the cell's `building_from_cell(cell).households`.
# Distances are Manhattan (200 m grid proxy for road-network walk-shed).
# ---------------------------------------------------------------------------
# Mapping each catchment kind to the set of LandUse values that count as
# an amenity of that kind. Aligns with CATCHMENT_RADIUS_M / CATCHMENT_WEIGHTS.
_CATCHMENT_AMENITY_LAND_USES: Dict[str, Tuple[LandUse, ...]] = {
    "healthcare": (LandUse.HEALTHCARE,),
    "school": (LandUse.SCHOOL,),
    "public_services": (LandUse.PUBLIC_SERVICES,),
    "shopping_centre": (LandUse.SHOPPING_CENTRE,),
    "shopping_local": (LandUse.RESTAURANT_FOOD, LandUse.RETAIL_HIGHSTREET),
    "religious": (LandUse.RELIGIOUS,),
}


def _amenity_cells_for_catchment(grid: Grid, kind: str) -> List[Cell]:
    """Per catchment-kind amenity cells. Keep aligned with CATCHMENT_RADIUS_M."""
    land_uses = _CATCHMENT_AMENITY_LAND_USES[kind]
    return [c for c in grid.all_cells() if c.land_use in land_uses]


def _household_weighted_coverage(grid: Grid, kind: str,
                                  cfg: Optional[DistrictConfig] = None) -> float:
    """Share of district households within `CATCHMENT_RADIUS_M[kind]` of
    any amenity cell of `kind`. Wraps the optimised path below."""
    return population_catchment_coverage_score(
        grid, cfg, _kinds_only=(kind,),
    )


def population_catchment_coverage_score(
    grid: Grid, cfg: Optional[DistrictConfig] = None,
    *, _kinds_only: Optional[Tuple[str, ...]] = None,
) -> float:
    """Household-weighted catchment-coverage composite across 6 amenity kinds.

    For each amenity kind:
        coverage_kind = (households within radius_kind of any amenity_kind cell)
                        / (district total households)

    Composite = weighted mean of coverage_kind by `CATCHMENT_WEIGHTS`
    (healthcare + school dominate; religious lowest because daily
    interaction is lowest).

    Returns a value in [0, 1]. 1.0 = every district household has every
    amenity kind within the URDPFI / IPHS walk- or vehicle-shed.

    Used by the SA optimiser as a SOFT metric (weight 0.05; see
    DEFAULT_WEIGHTS). Pairs with `_amenity_catchment_swap` in
    `layout/optimiser.py` which biases amenity placement toward
    under-served residential clusters.

    Performance: this is called once per SA iteration (~2,500 times per
    anneal). The implementation walks the grid ONCE to collect
    residential cells + their household counts (via `building_from_cell`),
    then loops over amenity kinds against the cached per-cell list. The
    naive per-kind impl was ~38 ms/call; this one is ~7 ms/call.
    """
    # Single grid walk: collect residential cells with non-zero households
    # AND collect per-kind amenity lists. Replaces the 6 separate grid
    # walks the per-kind helper used to do.
    #: only count amenities that HAVE
    # road frontage (a ROAD 4-neighbour) as "serving" residents. This
    # aligns the catchment metric with the HARD `amenities_road_frontage`
    # constraint so the SA is rewarded for placing amenities that are BOTH
    # near residents AND on roads, instead of trading one for the other.
    # Without this gate the first catchment re-anneal pushed
    # amenities_road_frontage 0.16 -> 0.324 (amenities pulled to road-less
    # cells near population centres). RETAIL_HIGHSTREET is exempt — it has
    # its own `highstreet_road_frontage` HARD constraint and fronts a road
    # by construction, so we don't double-gate it.
    def _has_road_frontage(c: Cell) -> bool:
        if c.land_use == LandUse.RETAIL_HIGHSTREET:
            return True
        return any(nb.land_use == LandUse.ROAD
                   for nb in grid.neighbours_4(c.row, c.col))

    residential: List[Tuple[Cell, int]] = []
    amenity_by_kind: Dict[str, List[Cell]] = {k: [] for k in CATCHMENT_WEIGHTS}
    for cell in grid.all_cells():
        if cell.is_residential:
            b = building_from_cell(cell, cfg)
            hh = b.households if b is not None else 0
            if hh > 0:
                residential.append((cell, hh))
        for kind, lu_tuple in _CATCHMENT_AMENITY_LAND_USES.items():
            if cell.land_use in lu_tuple and _has_road_frontage(cell):
                amenity_by_kind[kind].append(cell)

    total_hh = sum(hh for _, hh in residential)
    if total_hh <= 0:
        return 0.0

    kinds = _kinds_only or tuple(CATCHMENT_WEIGHTS.keys())
    total = 0.0
    total_weight = 0.0
    for kind in kinds:
        amenities = amenity_by_kind.get(kind) or []
        w = CATCHMENT_WEIGHTS[kind] if _kinds_only is None else 1.0
        total_weight += w
        if not amenities:
            continue
        radius = CATCHMENT_RADIUS_M[kind]
        covered = 0
        for cell, hh in residential:
            nearest = min(Grid.manhattan_distance(cell, a) for a in amenities)
            if nearest <= radius:
                covered += hh
        total += w * (covered / total_hh)
    if total_weight <= 0:
        return 0.0
    return total / total_weight


# ---------------------------------------------------------------------------
# F. Equity
# ---------------------------------------------------------------------------
def ews_amenity_access(grid: Grid) -> float:
    """How EWS access compares to all-residential access.

    Score = mean(all_residential_walk_to_amenity)
    / mean(EWS_walk_to_amenity)
    capped to [0, 1]. 1.0 = EWS get equal-or-better access; <1.0 = EWS
    walk further than the average resident.

    Returns
    -------
    float
        Equity score comparing EWS amenity distance with all-resident distance.
    """
    residents = _residential_cells(grid)
    ews = _ews_cells(grid)
    if not (residents and ews):
        return 0.0

    # Use all amenities (school + commercial + healthcare) combined.
    amenities = (
        _amenity_cells(grid, "school")
        + _amenity_cells(grid, "commercial")
        + _amenity_cells(grid, "healthcare")
    )
    if not amenities:
        return 0.0

    all_mean = _mean_walk_to_amenity(residents, amenities)
    ews_mean = _mean_walk_to_amenity(ews, amenities)
    if ews_mean == 0:
        return 1.0
    return max(0.0, min(1.0, all_mean / ews_mean))


def mid_ews_adjacency(grid: Grid) -> float:
    """How often LOW (EWS) cells sit next to MID-income cells.

    Score = (LOW-MID adjacent pairs) / (LOW cell count * 4).
    1.0 means every EWS cell is fully ringed by mid-income neighbours.
    Anti-ghettoisation proxy.

    Returns
    -------
    float
        Share of possible EWS sides adjacent to mid-income cells.
    """
    ews = _ews_cells(grid)
    if not ews:
        return 0.0
    adjacent_pairs = 0
    for c in ews:
        for nb in grid.neighbours_4(c.row, c.col):
            if nb.land_use == LandUse.RESIDENTIAL_MID:
                adjacent_pairs += 1
    max_pairs = len(ews) * 4
    return adjacent_pairs / max(1, max_pairs)


def ews_heat_shielding(grid: Grid, radius_cells: int = 2) -> float:
    """Mean vegetation_fraction across cells within `radius_cells` of EWS.

    Higher = EWS households have more cooling vegetation nearby.

    Returns
    -------
    float
        Mean nearby vegetation fraction around EWS cells.
    """
    ews = _ews_cells(grid)
    if not ews:
        return 0.0
    veg_total = 0.0
    n = 0
    radius_m = radius_cells * grid.cell_size_m * 1.01
    for c in ews:
        for nb in grid.cells_within_radius(c.row, c.col, radius_m):
            veg_total += nb.vegetation_fraction
            n += 1
    if n == 0:
        return 0.0
    return veg_total / n


# ---------------------------------------------------------------------------
# B.1 Surface-energy balance: albedo composite, heat-island index,
#     anthropogenic heat clustering
# ---------------------------------------------------------------------------
def albedo_composite_score(grid: Grid,
                            ideal_mean_albedo: float = 0.50,
                            ) -> float:
    """District-wide mean albedo, normalised so 0.5 (cool surfaces) scores 1.

    Punjab heat-island reduction targets a district-average albedo around
    0.4-0.5 (cool roofs, lighter pavements, etc.). Asphalt + concrete pull
    the baseline toward 0.2. This metric rewards layouts that compose to a
    higher mean.

    Returns
    -------
    float
        Mean cell albedo clamped to [0, 1] against ``ideal_mean_albedo``.
    """
    n = grid.total_cells
    if n == 0:
        return 0.0
    total = sum(c.albedo for c in grid.all_cells())
    return max(0.0, min(1.0, (total / n) / max(1e-6, ideal_mean_albedo)))


def heat_island_index(grid: Grid) -> float:
    """Composite heat-island score: ``1 - mean(heat_load)`` over cells.

    For each cell, ``heat_load = (1 - albedo) - vegetation_fraction``, with
    a small additive penalty for AC-using built cells (proxy for
    anthropogenic waste-heat). The cell-level value is clamped to [0, 1]
    so the district mean is on the same scale. Higher score = cooler.

    Returns
    -------
    float
        Mean inverted heat-load score in [0, 1]. Higher is better.
    """
    cells = list(grid.all_cells())
    if not cells:
        return 0.0
    AC_INTENSE_USES: Set[LandUse] = {
        LandUse.SHOPPING_CENTRE, LandUse.RETAIL_HIGHSTREET,
        LandUse.OFFICE, LandUse.HOTEL_GUESTHOUSE,
        LandUse.HEALTHCARE, LandUse.WAREHOUSE,
        LandUse.LIGHT_INDUSTRY,
    }
    total = 0.0
    for c in cells:
        load = (1.0 - c.albedo) - c.vegetation_fraction
        if c.land_use in AC_INTENSE_USES:
            load += 0.15  # AC waste-heat surcharge
        clamped = max(0.0, min(1.0, load))
        total += 1.0 - clamped
    return total / len(cells)


def anthro_heat_clustering_score(grid: Grid) -> float:
    """Penalise concentrating AC-intensive cells into a single hotspot.

    Computed as the size of the largest 4-connected component of AC-intensive
    cells normalised to the total of such cells. The metric is inverted so
    that dispersed AC load scores high (1.0) and a single mega-cluster
    scores low (1 / n).

    Returns
    -------
    float
        Dispersion score for anthropogenic heat sources in [0, 1].
    """
    AC_INTENSE_USES: Set[LandUse] = {
        LandUse.SHOPPING_CENTRE, LandUse.RETAIL_HIGHSTREET,
        LandUse.OFFICE, LandUse.HOTEL_GUESTHOUSE,
        LandUse.HEALTHCARE, LandUse.WAREHOUSE,
        LandUse.LIGHT_INDUSTRY,
    }
    coords = {(c.row, c.col) for c in grid.all_cells()
              if c.land_use in AC_INTENSE_USES}
    if not coords:
        return 1.0
    components = _components_4(coords)
    largest = max(len(comp) for comp in components)
    n = len(coords)
    # 1 - (largest / n) — fully dispersed scales toward 1.
    return 1.0 - (largest - 1) / max(1, n - 1)


# ---------------------------------------------------------------------------
# Internal: 4-connected components helper (duplicates constraints._components_4
# locally so layout/metrics.py does not import from layout/constraints.py).
# ---------------------------------------------------------------------------
def _components_4(coords: Set[Tuple[int, int]]) -> List[Set[Tuple[int, int]]]:
    """Return the 4-connected components of a coordinate set."""
    remaining = set(coords)
    out: List[Set[Tuple[int, int]]] = []
    while remaining:
        start = next(iter(remaining))
        comp = {start}
        q: deque = deque([start])
        remaining.discard(start)
        while q:
            r, c = q.popleft()
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nb = (r + dr, c + dc)
                if nb in remaining:
                    remaining.discard(nb)
                    comp.add(nb)
                    q.append(nb)
        out.append(comp)
    return out


# ---------------------------------------------------------------------------
# B.2 Wind alignment to prevailing NW-SE corridor
# ---------------------------------------------------------------------------
def wind_alignment_score(grid: Grid) -> float:
    """Reward ROAD cells that run along the NW-SE prevailing-wind axis.

    A ROAD cell is considered "wind-aligned" when at least one of its
    diagonal 8-neighbours (NW or SE) is also a ROAD cell — i.e. the road
    geometry has a NW-SE-running segment passing through this cell. Score
    is the fraction of ROAD cells that satisfy this criterion. Pure E-W
    or N-S grids score 0; a perfectly diagonal corridor scores 1.

    Returns
    -------
    float
        Share of ROAD cells with at least one NW or SE ROAD neighbour.
    """
    road_cells = [c for c in grid.all_cells() if c.land_use == LandUse.ROAD]
    if not road_cells:
        return 0.0
    aligned = 0
    # NW = (+1, -1) in (row, col): row + 1 means north (row 0 is south),
    # col - 1 means west. SE = (-1, +1).
    nw_se = [(1, -1), (-1, 1)]
    for c in road_cells:
        for dr, dc in nw_se:
            nr, nc = c.row + dr, c.col + dc
            if 0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols:
                if grid.at(nr, nc).land_use == LandUse.ROAD:
                    aligned += 1
                    break
    return aligned / len(road_cells)


# ---------------------------------------------------------------------------
# B.2b Building-axis wind alignment
# ---------------------------------------------------------------------------
# v2 cardinal convention:
# `building_axis_deg` is now the principal facade-facing direction in
# {0=N, 90=E, 180=S, 270=W}. Facing N/S means the long axis is E-W and
# the large facades are N/S; facing E/W means the long axis is N-S and
# the large facades are E/W. The current Punjab wind proxy rewards the
# N/S-facing cases because they catch the SW summer wind better for the
# coarse 200 m Stage B/C model.
def building_wind_alignment_score(grid: Grid) -> float:
    """Reward built cells whose long-facade axis catches Punjab SW summer wind.

 v2: cardinal-only facing options {0, 90, 180, 270} replace
    the prior diagonal-inclusive set. SW summer wind hits the long facade
    cleanly when the long axis is E-W (i.e. facing N or S); when the long
    axis is N-S (facing E or W), the wind only hits the short ends and
    cross-ventilation is weaker.

    Returns
    -------
    float
        Mean wind-alignment score across BUILT cells in [0, 1]. Score 1.0
        for facing 0 (N) or 180 (S) -- long axis E-W catches SW wind.
        Score 0.0 for facing 90 (E) or 270 (W) -- long axis N-S misses it.
    """
    built = [c for c in grid.all_cells() if c.has_building]
    if not built:
        return 0.0
    per_axis_score = {0.0: 1.0, 90.0: 0.0, 180.0: 1.0, 270.0: 0.0}
    return sum(per_axis_score.get(round(c.building_axis_deg), 0.0) for c in built) / len(built)


# ---------------------------------------------------------------------------
# (item 2 from supervisor brief): Stage A SA shading-yield
# metric. The full geometric integration in `energy.solar_geometry` is
# the gold standard but too slow for the SA inner loop (~3 s per call x
# ~2500 iterations). This metric uses the SAME geometric ideas (sun-aware
# tall-neighbour shadow projection) but evaluated on a fixed sun-azimuth
# heuristic so the SA can use it on every accept-check.
# Approximation: for each PV-bearing cell, count tall S/SW/SE/E/W
# neighbours weighted by (height_diff_m / cell_size_m) -- the larger
# the height gap, the longer the shadow it casts at low sun angles.
# Each PV-bearing cell's yield-multiplier proxy = 1 - 0.10 * weighted_count,
# floored at 0.60 (matches the legacy heuristic floor for consistency).
# Capacity-weighted by `deployable_pv_kwp`. Returns mean in [0.60, 1.0].
# This is INTENTIONALLY a fast proxy: the SA optimises against the proxy,
# and at export time the GeoJSON ships the full geometric multiplier from
# `energy.solar_geometry`. The two should correlate strongly (same
# tall-S-neighbour intuition) but aren't byte-for-byte identical.
# ---------------------------------------------------------------------------
#: single source of truth, core/shading_constants.py
SHADING_DELTA_M_PROXY = PV_SHADING_DELTA_M
# (Claude 2 critical-review #3): empirical geometric shading
# multipliers across optimised_sa span 0.887 - 1.000 with mean 0.987 and
# 52 % of PV-bearing cells at exactly 1.000. The previous proxy floor of
# 0.60 made the SA optimise over a 0.60 - 1.00 range that never occurs
# in dispatch -- gradient wasted on shading penalties between 0.60 and
# 0.85 that the LP never gets credit for. Narrowing the proxy floor to
# 0.85 aligns the SA's "mental model" with the geometric ground-truth
# while leaving headroom (still below the empirical 0.887 minimum) for
# rare tall-neighbour clusters the empirical sample didn't catch.
SHADING_FLOOR_PROXY = 0.85
SHADING_PER_NEIGHBOUR_PENALTY = 0.10


#: high-street typology in Chandigarh-style master plans
# runs in a single straight line along one road. The HARD `highstreet_corridor`
# constraint already requires a 4-connected chain >=4 cells with <=2 endpoints.
# This soft metric rewards layouts whose RETAIL_HIGHSTREET chains are also
# AXIS-ALIGNED (each component lies on a single row or single column), not
# bent / L-shaped / staircase. A bent chain still passes the corridor
# constraint (<=2 endpoints) but is less Chandigarh-faithful.
def highstreet_axis_alignment_score(grid: Grid) -> float:
    """Mean fraction of RETAIL_HIGHSTREET cells in axis-aligned components.

    Returns
    -------
    float
        In [0, 1]. 1.0 = every component is a pure horizontal or vertical
        line. 0.0 = no RETAIL_HIGHSTREET cells (no signal to optimise).
    """
    cells = [(c.row, c.col) for c in grid.all_cells()
             if c.land_use == LandUse.RETAIL_HIGHSTREET]
    if not cells:
        return 0.0
    cell_set = set(cells)
    visited: Set[Tuple[int, int]] = set()
    aligned_count = 0
    total = len(cells)
    for start in cells:
        if start in visited:
            continue
        component: List[Tuple[int, int]] = []
        frontier = [start]
        while frontier:
            r, c = frontier.pop()
            if (r, c) in visited:
                continue
            visited.add((r, c))
            component.append((r, c))
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nb = (r + dr, c + dc)
                if nb in cell_set and nb not in visited:
                    frontier.append(nb)
        rows = {r for r, _ in component}
        cols = {c for _, c in component}
        if len(rows) == 1 or len(cols) == 1:
            aligned_count += len(component)
    return aligned_count / total


#: visual coherence -- adjacent built cells in a real
# block tend to share orientation (one developer, one plot, one set of
# rules). The SA picks `building_axis_deg` per cell independently which
# can produce a chequerboard of N-facing / E-facing / S-facing cells
# inside what should be a coherent block. This metric rewards layouts
# where adjacent built cells share the SAME `building_axis_deg`.
def building_axis_coherence_score(grid: Grid) -> float:
    """Mean fraction of adjacent BUILT cell pairs that share building_axis_deg.

    Returns
    -------
    float
        In [0, 1]. 1.0 = every adjacent (4-neighbour) built pair has the
        same axis. 0.0 = no built cells (no signal). High values give
        the SA an incentive to keep blocks visually coherent.
    """
    built = [c for c in grid.all_cells() if c.has_building]
    if len(built) < 2:
        return 0.0
    same_axis = 0
    total_pairs = 0
    seen: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
    for c in built:
        for dr, dc in ((0, 1), (1, 0)):  # only east + south to avoid double-count
            nr, nc = c.row + dr, c.col + dc
            if not (0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols):
                continue
            nb = grid.at(nr, nc)
            if not nb.has_building:
                continue
            total_pairs += 1
            if abs(c.building_axis_deg - nb.building_axis_deg) < 1.0:
                same_axis += 1
    return same_axis / total_pairs if total_pairs > 0 else 0.0


def pv_shading_yield_score(grid: Grid) -> float:
    """Capacity-weighted PV-yield shading multiplier proxy across PV cells.

    Higher score = less aggregate shading = more PV energy delivered for
    the same installed kWp ceiling. Computed cheaply enough to run inside
    the SA inner loop.

    Returns
    -------
    float
        Capacity-weighted mean shading multiplier across PV-bearing
        cells, in approximately [0.60, 1.00]. 1.00 when no cell is
        shaded; lower as taller buildings overshadow PV-bearing cells.
        Returns 0.0 when the grid has no PV-bearing cells.
    """
    pv_pairs: List[Tuple[Cell, float]] = []
    for c in grid.all_cells():
        # Reuse the same PV-bearing definition as energy.network.
        if c.has_building:
            # Approx rooftop PV ceiling. Match energy.network.from_grid
            # by using a fraction of cell area; this is a proxy so a
            # rough constant is acceptable.
            cap_kwp = max(0.0, c.height_m) * 8.0  # ~8 kWp / storey-of-height
            if cap_kwp > 0:
                pv_pairs.append((c, cap_kwp))
        elif c.land_use == LandUse.SOLAR_FARM:
            pv_pairs.append((c, float(c.cell_size_m) * float(c.cell_size_m) * 0.10))
    if not pv_pairs:
        return 0.0

    south_checks = ((-1, -1), (-1, 0), (-1, 1))
    flank_checks = ((0, -1), (0, 1))
    total_cap = 0.0
    weighted_sum = 0.0
    for cell, cap in pv_pairs:
        my_h = cell.height_m if cell.has_building else 1.5
        penalty_weight = 0.0
        for dr, dc in south_checks + flank_checks:
            nr, nc = cell.row + dr, cell.col + dc
            if 0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols:
                nb = grid.at(nr, nc)
                delta = nb.height_m - my_h
                if delta > SHADING_DELTA_M_PROXY:
                    # Weight by height-delta-over-cell so a 30 m gap
                    # is heavier than a 7 m one.
                    penalty_weight += min(1.0, delta / cell.cell_size_m)
        multiplier = max(SHADING_FLOOR_PROXY,
                         1.0 - SHADING_PER_NEIGHBOUR_PENALTY * penalty_weight)
        weighted_sum += multiplier * cap
        total_cap += cap
    return weighted_sum / total_cap if total_cap > 0 else 0.0


# ---------------------------------------------------------------------------
# B.3 Tree shading along pedestrian routes (mean vegetation on ROAD cells)
# ---------------------------------------------------------------------------
def tree_shading_score(grid: Grid) -> float:
    """Mean ``vegetation_fraction`` across ROAD cells.

    The pedestrian-route proxy: the more vegetation cover along the road
    network, the more shaded walking is. Returns 0.0 if no roads.

    Returns
    -------
    float
        Mean ROAD-cell vegetation fraction in [0, 1].
    """
    roads = [c for c in grid.all_cells() if c.land_use == LandUse.ROAD]
    if not roads:
        return 0.0
    return sum(c.vegetation_fraction for c in roads) / len(roads)


# ---------------------------------------------------------------------------
# B.5 Cool refuge distance and water-body proximity
# ---------------------------------------------------------------------------
def _mean_residential_distance_to(grid: Grid,
                                    target_uses: Set[LandUse],
                                    cap_m: float,
                                    ) -> Tuple[float, int]:
    """Mean Manhattan distance from each residential cell to its nearest
    cell of any ``target_uses``. Distances above ``cap_m`` are capped at
    ``cap_m`` so a single very-far cell does not dominate. Returns
    ``(mean_distance, n_residents)``.
    """
    residents = [c for c in grid.all_cells() if c.is_residential]
    if not residents:
        return 0.0, 0
    targets = [c for c in grid.all_cells() if c.land_use in target_uses]
    if not targets:
        return cap_m, len(residents)
    total = 0.0
    for r in residents:
        d = min(Grid.manhattan_distance(r, t) for t in targets)
        total += min(d, cap_m)
    return total / len(residents), len(residents)


def cool_refuge_distance_score(grid: Grid,
                                 target_m: float = COOL_REFUGE_TARGET_M,
                                 ) -> float:
    """Score residential proximity to the nearest cool refuge.

    "Cool refuge" = ``OPEN_SPACE`` or ``BLUE_SPACE`` cell. Score is
    ``1 - (mean_residential_distance / target_m)`` clamped to [0, 1].

    Returns
    -------
    float
        Cool-refuge accessibility score in [0, 1]. Higher is better.
    """
    mean_d, n = _mean_residential_distance_to(
        grid, {LandUse.OPEN_SPACE, LandUse.BLUE_SPACE},
        cap_m=target_m * 2.0,
    )
    if n == 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - mean_d / target_m))


# ---------------------------------------------------------------------------
#: BLUE_SPACE green-buffer soft metric.
# Real water bodies (ponds / tanks / canals) sit inside a vegetated setback
# rather than touching roads or buildings directly. Reward layouts where
# each BLUE_SPACE cell has a high share of OPEN_SPACE / BLUE_SPACE 8-
# neighbours (i.e. the water body is embedded in a green envelope), and
# penalise direct adjacency to ROAD or built cells. At 200 m grid this
# is a soft preference -- once we move to 100 m the buffer pattern can
# be encoded explicitly with per-tile sub-cell water rendering.
# ---------------------------------------------------------------------------
BLUE_SPACE_GREEN_NEIGHBOURS: frozenset = frozenset({
    "open_space",
    "blue_space",   # adjacent water bodies count as compatible
})


def blue_space_green_buffer_score(grid: Grid) -> float:
    """Mean share of OPEN_SPACE / BLUE_SPACE 8-neighbours per BLUE_SPACE cell.

    Higher score = water bodies are nestled in green setbacks rather than
    directly touching roads / buildings. Returns 0.5 (neutral) when no
    BLUE_SPACE cells exist on the grid so the metric doesn't penalise
    layouts that omit water.

    Returns
    -------
    float
        In [0, 1]. 1.0 = every BLUE_SPACE cell has only green/water
        8-neighbours; 0.0 = every BLUE_SPACE cell is fully surrounded by
        road or buildings.
    """
    blue_cells = [c for c in grid.all_cells() if c.land_use == LandUse.BLUE_SPACE]
    if not blue_cells:
        return 0.5
    total = 0.0
    for c in blue_cells:
        nbrs = list(grid.neighbours_8(c.row, c.col))
        if not nbrs:
            continue
        green_count = sum(
            1 for n in nbrs
            if n.land_use.value in BLUE_SPACE_GREEN_NEIGHBOURS
        )
        total += green_count / len(nbrs)
    return total / len(blue_cells)


def water_body_proximity_score(grid: Grid,
                                 target_m: float = WATER_BODY_TARGET_M,
                                 ) -> float:
    """Score residential proximity to BLUE_SPACE (evaporative cooling).

    Returns 0.5 (neutral) when no BLUE_SPACE cells exist so this metric
    doesn't punish layouts that have not yet introduced water bodies
    rather than indicating a failure mode.

    Returns
    -------
    float
        Water-body proximity score in [0, 1]. Higher is better.
    """
    if not grid.cells_of(LandUse.BLUE_SPACE):
        return 0.5
    mean_d, n = _mean_residential_distance_to(
        grid, {LandUse.BLUE_SPACE}, cap_m=target_m * 2.0,
    )
    if n == 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - mean_d / target_m))


def high_income_water_body_proximity(grid: Grid,
                                       target_m: float = WATER_BODY_TARGET_M,
                                       ) -> float:
    """Score HIGH_INCOME_RESIDENTIAL proximity to BLUE_SPACE.

 supervisor request: captures the "lakeside premium"
    real-estate reality of Indian peri-urban land-use (e.g. Sukhna Lake's
    surrounds in Chandigarh are dominated by upmarket residential). The
    metric is RIVAL to ``water_body_proximity_score`` which is egalitarian
    across all residents - both run together so the SA optimiser has to
    trade realism (rich pay -> water view) against equity (every resident
    deserves access). The thesis discussion chapter can examine the
    trade-off.

    Returns 0.5 (neutral) when no BLUE_SPACE cells exist.

    Returns
    -------
    float
        High-income blue-space proximity score in [0, 1]. Higher = closer.
    """
    if not grid.cells_of(LandUse.BLUE_SPACE):
        return 0.5
    residents = [c for c in grid.all_cells()
                  if c.land_use == LandUse.RESIDENTIAL_HIGH]
    if not residents:
        return 0.5
    targets = [c for c in grid.all_cells() if c.land_use == LandUse.BLUE_SPACE]
    cap_m = target_m * 2.0
    total = 0.0
    for r in residents:
        d = min(Grid.manhattan_distance(r, t) for t in targets)
        total += min(d, cap_m)
    mean_d = total / len(residents)
    return max(0.0, min(1.0, 1.0 - mean_d / target_m))


# ---------------------------------------------------------------------------
# C. Mixed-use ratio, Shannon diversity, walkable destinations
# ---------------------------------------------------------------------------
def _residential_neighbourhood_cells(grid: Grid,
                                      anchor: Cell,
                                      radius_m: float,
                                      ) -> List[Cell]:
    return grid.cells_within_radius(anchor.row, anchor.col, radius_m)


def mixed_use_ratio_400m(grid: Grid,
                          radius_m: float = MIXED_USE_RADIUS_M,
                          ) -> float:
    """Per residential cell, count distinct land-use classes within
    ``radius_m``, then average across residents and normalise.

    The bar for "complete mix" is 6 distinct uses (residential + school +
    commercial + healthcare + open/blue space + ROAD). Higher scores
    indicate the average resident has a wider variety of activities within
    a 400 m walk.

    Returns
    -------
    float
        Mean distinct-land-use count normalised to [0, 1].
    """
    residents = [c for c in grid.all_cells() if c.is_residential]
    if not residents:
        return 0.0
    ideal_uses = 6
    total = 0.0
    for r in residents:
        seen = {r.land_use}
        for nb in _residential_neighbourhood_cells(grid, r, radius_m):
            seen.add(nb.land_use)
        total += min(1.0, len(seen) / ideal_uses)
    return total / len(residents)


def shannon_diversity_score(grid: Grid,
                              radius_m: float = NEIGHBOURHOOD_RADIUS_M,
                              ) -> float:
    """Mean Shannon entropy of land-uses in each residential cell's
    400 m neighbourhood, normalised by the entropy of an even spread
    over the full LandUse enum.

    Returns
    -------
    float
        Normalised Shannon-diversity score in [0, 1].
    """
    residents = [c for c in grid.all_cells() if c.is_residential]
    if not residents:
        return 0.0
    n_uses = len(LandUse)
    max_entropy = math.log(n_uses)
    if max_entropy <= 0:
        return 0.0
    total = 0.0
    for r in residents:
        counts: Dict[LandUse, int] = {r.land_use: 1}
        for nb in _residential_neighbourhood_cells(grid, r, radius_m):
            counts[nb.land_use] = counts.get(nb.land_use, 0) + 1
        n = sum(counts.values())
        h = 0.0
        for v in counts.values():
            p = v / n
            if p > 0:
                h -= p * math.log(p)
        total += h / max_entropy
    return total / len(residents)


def walkable_destinations_score(grid: Grid,
                                  radius_m: float = NEIGHBOURHOOD_RADIUS_M,
                                  target_count: int = DESTINATION_TYPES_TARGET,
                                  ) -> float:
    """Distinct AMENITY types reachable within `radius_m` of each
    residential cell.

    "Amenity" types: school, commercial (shopping_centre / retail_highstreet
    / restaurant_food_service), healthcare, public_services, religious,
    open_space, blue_space. A residential cell that can reach ``target_count``
    or more of these in 400 m scores 1.0.

    Returns
    -------
    float
        Mean walkable-destination count normalised to [0, 1].
    """
    AMENITY_GROUPS: Dict[str, Set[LandUse]] = {
        "school": {LandUse.SCHOOL},
        "commercial": {
            LandUse.SHOPPING_CENTRE,
            LandUse.RETAIL_HIGHSTREET,
            LandUse.RESTAURANT_FOOD,
        },
        "healthcare": {LandUse.HEALTHCARE},
        "public_services": {LandUse.PUBLIC_SERVICES},
        "religious": {LandUse.RELIGIOUS},
        "open_space": {LandUse.OPEN_SPACE},
        "blue_space": {LandUse.BLUE_SPACE},
    }
    residents = [c for c in grid.all_cells() if c.is_residential]
    if not residents:
        return 0.0
    total = 0.0
    for r in residents:
        nearby_uses = {nb.land_use
                       for nb in _residential_neighbourhood_cells(grid, r, radius_m)}
        nearby_uses.add(r.land_use)
        groups_present = sum(
            1 for group in AMENITY_GROUPS.values() if nearby_uses & group
        )
        total += min(1.0, groups_present / target_count)
    return total / len(residents)


# ---------------------------------------------------------------------------
# E. Commercial cluster compactness — anti-fragmentation for shops
# ---------------------------------------------------------------------------
COMMERCIAL_USES: Set[LandUse] = {
    LandUse.SHOPPING_CENTRE,
    LandUse.RETAIL_HIGHSTREET,
}


def commercial_cluster_score(grid: Grid,
                               min_cluster_size: int = 4,
                               ideal_components: int = 3,
                               ) -> float:
    """Anti-fragmentation score for commercial cells.

    Mirror of :func:`solar_cluster_score` but applied to the union of
    SHOPPING_CENTRE and RETAIL_HIGHSTREET cells. Scattered single-cell
    shops are penalised; compact clusters are rewarded.

    Returns
    -------
    float
        Commercial-cluster compactness score in [0, 1].
    """
    coords = {(c.row, c.col) for c in grid.all_cells()
              if c.land_use in COMMERCIAL_USES}
    if not coords:
        return 0.5  # nothing to score
    components = _components_4(coords)
    n_components = len(components)
    n_cells = len(coords)
    cells_in_big = sum(len(c) for c in components if len(c) >= min_cluster_size)
    big_share = cells_in_big / n_cells
    extra_components_penalty = max(0, n_components - ideal_components) / n_cells
    return max(0.0, min(1.0, big_share - 0.5 * extra_components_penalty))


# ---------------------------------------------------------------------------
# A. Building orientation (long axis E-W)
# ---------------------------------------------------------------------------
def building_orientation_score(grid: Grid) -> float:
    """Reward layouts whose built cells form E-W-running rows.

    At 200 m grid resolution, a single cell is square and has no axis;
    "orientation" emerges from how cells of the same land-use line up.
    For each built cell, compare same-use neighbour counts along the
    E-W axis vs the N-S axis (within 4-neighbourhood). Higher E-W count
    means the building row runs east-west, the orientation that
    maximises south-facing roof PV access. Score is normalised to [0, 1].

    Returns
    -------
    float
        Mean E-W axis preference for built cells in [0, 1].
    """
    built = [c for c in grid.all_cells() if c.has_building]
    if not built:
        return 0.0
    total = 0.0
    for c in built:
        ew = 0
        ns = 0
        for dc in (-1, 1):
            nc = c.col + dc
            if 0 <= nc < grid.n_cols:
                if grid.at(c.row, nc).land_use == c.land_use:
                    ew += 1
        for dr in (-1, 1):
            nr = c.row + dr
            if 0 <= nr < grid.n_rows:
                if grid.at(nr, c.col).land_use == c.land_use:
                    ns += 1
        if ew + ns == 0:
            total += 0.5  # isolated cell — neutral, not penalised
        else:
            total += ew / (ew + ns)
    return total / len(built)


# ---------------------------------------------------------------------------
# A / B.4 Sky-view factor per residential cell
# ---------------------------------------------------------------------------
def sky_view_factor_score(grid: Grid,
                            normaliser_m: float = SVF_HEIGHT_NORMALISER_M,
                            ) -> float:
    """Approximate sky-view factor (SVF) per residential cell.

    For each residential cell, compute the mean of
    ``max(0, neighbour_height - my_height) / normaliser_m`` over its
    4-neighbours, clamped at 1, and subtract from 1 to get a per-cell
    SVF ∈ [0, 1]. Returns the mean SVF across all residential cells.
    Helps both rooftop solar access and night radiative cooling.

    Returns
    -------
    float
        Mean residential SVF in [0, 1]. Higher is better.
    """
    residents = [c for c in grid.all_cells() if c.is_residential]
    if not residents:
        return 0.0
    total = 0.0
    for c in residents:
        nbs = grid.neighbours_4(c.row, c.col)
        if not nbs:
            total += 1.0
            continue
        obstruction = 0.0
        for nb in nbs:
            obstruction += max(0.0, (nb.height_m - c.height_m) / normaliser_m)
        mean_obs = min(1.0, obstruction / len(nbs))
        total += 1.0 - mean_obs
    return total / len(residents)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# compactness. These two reshape the "scattered village with trees" into
# an organised, clustered town (the Chandigarh-sector inspiration; the sector
# ROADS themselves land at per register B16). Both are cheap O(built) local
# metrics, safe for per-move SA evaluation.
# ---------------------------------------------------------------------------
_RES_CLASS_RANK = {
    LandUse.RESIDENTIAL_LOW: 0,
    LandUse.RESIDENTIAL_MID: 1,
    LandUse.RESIDENTIAL_HIGH: 2,
}


def income_block_clustering_score(grid: Grid) -> float:
    """Reward same-income residential cells forming BLOCKS, tolerating
    adjacent-class mixing at block edges and penalising low<->high adjacency
    (the author: "income groups can be in another block if low/mid or mid/high,
    NEVER low/high").

    Score = mean over residential-residential 4-adjacencies of a pair score:
    same class 1.0, adjacent class (|rank diff| = 1) 0.6, distant class
    (low<->high, |rank diff| = 2) 0.0. Returns 1.0 when no residential
    adjacencies exist (nothing to score).
    """
    total = 0
    acc = 0.0
    for cell in grid.all_cells():
        if not cell.land_use.is_residential:
            continue
        r0 = _RES_CLASS_RANK.get(cell.land_use)
        if r0 is None:
            continue
        for nb in grid.neighbours_4(cell.row, cell.col):
            if not nb.land_use.is_residential:
                continue
            r1 = _RES_CLASS_RANK.get(nb.land_use)
            if r1 is None:
                continue
            total += 1
            d = abs(r0 - r1)
            acc += 1.0 if d == 0 else (0.6 if d == 1 else 0.0)
    return 1.0 if total == 0 else acc / total


def town_compactness_score(grid: Grid) -> float:
    """Reward a COMPACT built core over a scattered "village in a field"
    (the author. Score = mean over built cells of the fraction of their
    4-neighbours that are BUILT or ROAD (town fabric, not open space). High =
    the town clusters; low = buildings sprinkled through the green. ROAD counts
    as fabric so a building fronting a street is not penalised. 0.0 with no
    built cells."""
    built = [c for c in grid.all_cells() if c.has_building]
    if not built:
        return 0.0
    acc = 0.0
    for cell in built:
        nbrs = grid.neighbours_4(cell.row, cell.col)
        if not nbrs:
            continue
        fabric = sum(1 for n in nbrs
                     if n.has_building or n.land_use == LandUse.ROAD)
        acc += fabric / len(nbrs)
    return acc / len(built)


def park_shape_score(grid: Grid, min_cluster_size: int = 4,
                     target_fill: float = 0.7) -> float:
    """.9: reward RECTANGULAR-ish
    emergent parks over raggedy sprawl. His "GOOD PARK" example was a
    locked 12-ha block (bbox fill 1.0); the audit found 20 emergent
    clusters >= 4 cells with fill < 0.6.

    Over UNLOCKED OPEN_SPACE cells only (mid-anneal the locked structure -
    big parks / greenway / agri band / solar ring - is excluded by the
    locked flag; post-anneal subtypes do not exist yet while the SA runs),
    for every connected cluster >= `min_cluster_size`: contribution =
    min(1, bbox_fill / target_fill) where bbox_fill = |cluster| / (h x w)
    of its bounding box. Score = mean contribution; 1.0 when no such
    clusters exist (nothing to penalise). Weight tuned at the dress
    rehearsal (default 0.05, the population-catchment band)."""
    from collections import deque
    coords = {(c.row, c.col) for c in grid.all_cells()
              if c.land_use == LandUse.OPEN_SPACE and not c.locked}
    if not coords:
        return 1.0
    remaining = set(coords)
    fills: List[float] = []
    while remaining:
        start = next(iter(remaining))
        comp = {start}
        q = deque([start])
        remaining.discard(start)
        while q:
            r, c = q.popleft()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nb = (r + dr, c + dc)
                if nb in remaining:
                    remaining.discard(nb)
                    comp.add(nb)
                    q.append(nb)
        if len(comp) >= min_cluster_size:
            rows = [r for r, _ in comp]
            cols = [c for _, c in comp]
            bbox = (max(rows) - min(rows) + 1) * (max(cols) - min(cols) + 1)
            fills.append(min(1.0, (len(comp) / bbox) / target_fill))
    return sum(fills) / len(fills) if fills else 1.0


def open_singleton_score(grid: Grid, allowance: int = 40,
                         span: float = 60.0) -> float:
    """.9 companion: consolidate EXCESS 1-cell open-space confetti.

    THE ALLOWANCE MATTERS: the B18.8 sector-green pattern NEEDS a pool of
    1-2-cell greens (~1 per sector, ~36 sectors; the post-anneal tagger
    round-robins park_neighbourhood from exactly this pool) - so the first
    `allowance` singletons are FREE and only the excess is penalised
    (the author's ballot: "consolidate non-sector-green singletons; sector
    greens stay"). Over unlocked OPEN_SPACE: score = max(0, 1 -
    max(0, n_singletons - allowance) / span). The audit's 59 emergent
    singletons -> ~0.68; <= 40 -> 1.0. Weight default 0.03."""
    from collections import deque
    coords = {(c.row, c.col) for c in grid.all_cells()
              if c.land_use == LandUse.OPEN_SPACE and not c.locked}
    if not coords:
        return 1.0
    remaining = set(coords)
    singletons = 0
    while remaining:
        start = next(iter(remaining))
        comp_n = 1
        q = deque([start])
        remaining.discard(start)
        while q:
            r, c = q.popleft()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nb = (r + dr, c + dc)
                if nb in remaining:
                    remaining.discard(nb)
                    comp_n += 1
                    q.append(nb)
        if comp_n == 1:
            singletons += 1
    return max(0.0, 1.0 - max(0, singletons - allowance) / span)


def walkability_permeability_score(grid: Grid) -> float:
    """STAGE- walkability composite (access + permeability + green loop).

    Thin wrapper over `layout.path_network.walkability_report` so the score
    appears alongside the other layout metrics. The street/path EDGES it
    reads are POST-ANNEAL overlays (assign_local_streets +
    assign_path_network) - they do not exist while the SA runs, so this
    metric carries weight 0.0 in DEFAULT_WEIGHTS (report-only; wiring it
    into the objective would score a half-built state) and the empty-edges
    guard keeps the per-move cost at zero during annealing.
    """
    if not grid.street_edges:
        return 0.0
    from .path_network import walkability_report
    return walkability_report(grid)["composite"]


@dataclass
class LayoutScore:
    """Container for all metric scores from one layout."""

    solar_capacity: float
    solar_access: float
    solar_farm_access: float
    solar_cluster: float
    access_school: float
    access_commercial: float
    access_healthcare: float
    coverage_15min: float
    ews_amenity_access: float
    mid_ews_adjacency: float
    ews_heat_shielding: float
    open_space_cluster: float
    infrastructure_distance: float
    # Stage A Tier 1 additions (passive cooling / mixed-use / equity)
    albedo_composite: float
    heat_island_index: float
    anthro_heat_clustering: float
    wind_alignment: float
    tree_shading_routes: float
    cool_refuge_distance: float
    water_body_proximity: float
    high_income_water_proximity: float
    mixed_use_ratio_400m: float
    shannon_diversity: float
    walkable_destinations: float
    commercial_cluster: float
    building_orientation: float
    sky_view_factor: float
    # (Priority 2): per-cell building-axis wind alignment.
    building_wind_alignment: float = 0.0
    # (item 2): SA-fast PV-yield shading metric.
    pv_shading_yield: float = 0.0
    #: high-street axis-alignment soft metric.
    highstreet_axis_alignment: float = 0.0
    #: adjacent-pair building-axis coherence.
    building_axis_coherence: float = 0.0
    #: blue-space green-buffer share.
    blue_space_green_buffer: float = 0.0
    # buffered from residential 4-neighbours.
    solar_farm_residential_buffer: float = 0.0
    #: household-weighted catchment
    # coverage for healthcare / school / public_services / shopping /
    # religious. Pairs with `_amenity_catchment_swap` in
    # `layout/optimiser.py`. Spec at
    population_catchment_coverage: float = 0.0
    # -> STAGE-: income-block clustering + town-core
    # compactness (the "organise the scattered town" objective).
    income_block_clustering: float = 0.0
    town_compactness: float = 0.0
    #.9: park bbox-fill shape term + excess-singleton
    # consolidation (with the sector-green allowance) - the anneal-half of
    park_shape: float = 0.0
    open_singletons: float = 0.0
    # STAGE-: walkability composite over the street/path edge
    # network. Post-anneal overlay -> weight 0.0 in the SA (report-only).
    walkability_permeability: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        """Return metric values keyed by metric name.

        Returns
        -------
        Dict[str, float]
            Flat mapping of score names to numeric score values.
        """
        return {
            "solar_capacity": self.solar_capacity,
            "solar_access": self.solar_access,
            "solar_farm_access": self.solar_farm_access,
            "solar_cluster": self.solar_cluster,
            "access_school": self.access_school,
            "access_commercial": self.access_commercial,
            "access_healthcare": self.access_healthcare,
            "coverage_15min": self.coverage_15min,
            "ews_amenity_access": self.ews_amenity_access,
            "mid_ews_adjacency": self.mid_ews_adjacency,
            "ews_heat_shielding": self.ews_heat_shielding,
            "open_space_cluster": self.open_space_cluster,
            "infrastructure_distance": self.infrastructure_distance,
            "albedo_composite": self.albedo_composite,
            "heat_island_index": self.heat_island_index,
            "anthro_heat_clustering": self.anthro_heat_clustering,
            "wind_alignment": self.wind_alignment,
            "tree_shading_routes": self.tree_shading_routes,
            "cool_refuge_distance": self.cool_refuge_distance,
            "water_body_proximity": self.water_body_proximity,
            "high_income_water_proximity": self.high_income_water_proximity,
            "mixed_use_ratio_400m": self.mixed_use_ratio_400m,
            "shannon_diversity": self.shannon_diversity,
            "walkable_destinations": self.walkable_destinations,
            "commercial_cluster": self.commercial_cluster,
            "building_orientation": self.building_orientation,
            "sky_view_factor": self.sky_view_factor,
            "building_wind_alignment": self.building_wind_alignment,
            "pv_shading_yield": self.pv_shading_yield,
            "highstreet_axis_alignment": self.highstreet_axis_alignment,
            "building_axis_coherence": self.building_axis_coherence,
            "blue_space_green_buffer": self.blue_space_green_buffer,
            "solar_farm_residential_buffer": self.solar_farm_residential_buffer,
            "population_catchment_coverage": self.population_catchment_coverage,
            "income_block_clustering": self.income_block_clustering,
            "town_compactness": self.town_compactness,
            "park_shape": self.park_shape,
            "open_singletons": self.open_singletons,
            "walkability_permeability": self.walkability_permeability,
        }


def score_layout(grid: Grid,
                  requirements: Optional[Requirements] = None,
                  cfg: Optional[DistrictConfig] = None,
                  norms: Optional[DemandNorms] = None,
                  ) -> LayoutScore:
    """Evaluate every implemented layout metric.

    Returns
    -------
    LayoutScore
        Container with all metric values for the grid.
    """
    cfg = cfg or load_config()
    norms = norms or load_demand_norms()

    if requirements is not None:
        sc = solar_capacity_score(grid, requirements, cfg, norms)
    else:
        sc = 0.0

    return LayoutScore(
        solar_capacity=sc,
        solar_access=solar_access_score(grid),
        solar_farm_access=solar_farm_solar_access(grid),
        solar_cluster=solar_cluster_score(grid),
        access_school=access_score_for(grid, "school"),
        access_commercial=access_score_for(grid, "commercial"),
        access_healthcare=access_score_for(grid, "healthcare"),
        coverage_15min=coverage_15_minute(grid),
        ews_amenity_access=ews_amenity_access(grid),
        mid_ews_adjacency=mid_ews_adjacency(grid),
        ews_heat_shielding=ews_heat_shielding(grid),
        open_space_cluster=open_space_cluster_score(grid),
        infrastructure_distance=infrastructure_distance_score(grid),
        albedo_composite=albedo_composite_score(grid),
        heat_island_index=heat_island_index(grid),
        anthro_heat_clustering=anthro_heat_clustering_score(grid),
        wind_alignment=wind_alignment_score(grid),
        tree_shading_routes=tree_shading_score(grid),
        cool_refuge_distance=cool_refuge_distance_score(grid),
        water_body_proximity=water_body_proximity_score(grid),
        high_income_water_proximity=high_income_water_body_proximity(grid),
        mixed_use_ratio_400m=mixed_use_ratio_400m(grid),
        shannon_diversity=shannon_diversity_score(grid),
        walkable_destinations=walkable_destinations_score(grid),
        commercial_cluster=commercial_cluster_score(grid),
        building_orientation=building_orientation_score(grid),
        sky_view_factor=sky_view_factor_score(grid),
        building_wind_alignment=building_wind_alignment_score(grid),
        pv_shading_yield=pv_shading_yield_score(grid),
        highstreet_axis_alignment=highstreet_axis_alignment_score(grid),
        building_axis_coherence=building_axis_coherence_score(grid),
        blue_space_green_buffer=blue_space_green_buffer_score(grid),
        solar_farm_residential_buffer=solar_farm_residential_buffer_score(grid),
        population_catchment_coverage=population_catchment_coverage_score(grid, cfg),
        income_block_clustering=income_block_clustering_score(grid),
        town_compactness=town_compactness_score(grid),
        park_shape=park_shape_score(grid),
        open_singletons=open_singleton_score(grid),
        walkability_permeability=walkability_permeability_score(grid),
    )


# Default weights for the Pareto-style weighted-sum objective.
# Three macro axes from the spec: CARBON (solar + cooling) / LIVEABILITY
# (transport) / EQUITY (EWS-focused). Existing weights were rebalanced
# downward so the new Stage A Tier 1 metrics could be folded in without
# changing the sum. Weights are normalised by ``weighted_score`` so the
# absolute total is not load-bearing — relative magnitudes are.
# =========================================================================
# /: DECLARED, NOT CHANGED.
# Changing any weight means re-annealing, which re-baselines the frozen
# seed-42 layout and every energy pin that depends on it. Out of scope by
# standing instruction. So these two facts are recorded here instead, and
# they belong in the methods chapter.
# - THE THREE AXES ARE NOT CO-EQUAL. Measured across all 39 weights
# (sum 1.67):
#     CARBON      (solar + passive cooling, 18 metrics)   0.740   44.3%
#     LIVEABILITY (mixed-use, transport, infra, form, 18) 0.780   46.7%
#     EQUITY      (3 explicitly EWS-targeted metrics)     0.150    9.0%
# By group: solar 21.6%, passive cooling 22.8%, transport 17.4%, town form
# 16.8%, equity 9.0%, infrastructure 7.8%, mixed-use 4.8%.
# The header above names three axes as co-equal framing. One of them carries
# about a fifth of the weight of the others. That may well be the intended
# preference - but this thesis has an EQUITY CHAPTER, and the frozen layout
# underneath every energy result was annealed with EWS-specific objectives at
# 9% of the objective function. Any claim that the plan was optimised for
# equitable access has to be stated against that 9%. A fairer reading gives
# equity a little more - `water_body_proximity` calls itself
# "equity-flavoured" in its own comment, and the school-access and
# 15-minute-coverage metrics benefit EWS households too - but the three
# metrics that are EXPLICITLY EWS-targeted total 0.150.
# - SOME WEIGHTS WERE TUNED UNTIL THE PICTURE LOOKED RIGHT. Several
# entries below record their own provenance as a visual or behavioural target
# rather than an external source ("bunch the solar-farm cells all together"
# -> 0.04 to 0.07, and similar). That is a legitimate way to build a design
# objective and an illegitimate thing to leave unsaid: it makes the objective
# a preference statement, not a measurement. The individual comments are
# honest; what was missing was the summary.
# CONSEQUENCE FOR THE WRITE-UP: describe the objective as a DESIGNER'S
# WEIGHTED PREFERENCE, calibrated partly against visual judgement, with equity
# at 9%. Do not describe it as three balanced axes.
# See also: no weight sensitivity has ever been run. The cheap version
# re-scores the EXISTING frozen layout under perturbed weights and answers
# "is this layout on a plateau or a peak?" without touching the freeze.
# =========================================================================
DEFAULT_WEIGHTS: Dict[str, float] = {
    # ---- A. Solar ----
    "solar_capacity": 0.08,
    "solar_access": 0.06,
    # dedicated SOLAR_FARM shading metric with its own weight
    # so the SA optimiser is not diluted by ~1200 built rooftops vs ~25
    # SOLAR_FARM cells. Weight chosen ~3x higher per-cell than the mixed
    # solar_access since SOLAR_FARM placement is much more concentrated
    # (clustered land block, not 1 cell per built parcel).
    "solar_farm_access": 0.06,
    #: weight
    # bumped 0.04 -> 0.07 alongside the single-block `solar_cluster_score`
    # change (ideal_components 2->1, flat 0.15 per-extra-component penalty)
    # so the SA actually merges the satellite field into the main block.
    "solar_cluster": 0.07,
    "building_orientation": 0.02,
    "sky_view_factor": 0.03,
    # ---- B. Passive cooling ----
    "albedo_composite": 0.04,
    "heat_island_index": 0.05,
    "anthro_heat_clustering": 0.03,
    "wind_alignment": 0.02,
    # (Priority 2 v2): building-axis wind alignment rewards
    # cardinal N/S-facing cells, whose E-W long axis performs better for
    # this coarse Punjab cross-ventilation proxy. Weight 0.03 -- slightly
    # higher than road-axis wind alignment because building axes can be
    # flipped per cell whereas road axes are baked into the seed.
    "building_wind_alignment": 0.03,
    # (item 2 from supervisor brief): reward layouts whose
    # PV-bearing cells have minimal cap-weighted shading. Weight 0.04 --
    # higher than solar_cluster because it directly couples Stage A
    # geometry into Stage B/C dispatch yield.
    "pv_shading_yield": 0.04,
    #: reward axis-aligned high-street chains over
    # bent / staircase ones. Weight small (0.02) since the HARD corridor
    # constraint already ensures size/endpoint conformity; this just
    # nudges the SA toward the cleaner straight-line typology.
    "highstreet_axis_alignment": 0.02,
    #: nudge SA toward block-coherent building axes
    # so adjacent built cells share orientation (single-developer reality).
    # Weight 0.04 -- intentionally larger than highstreet_axis_alignment
    # because it covers all built cells, not just a small chain.
    "building_axis_coherence": 0.04,
    #: reward green setbacks around water bodies
    # (real ponds / tanks have vegetated edges, not road / building right up
    # to the water).
    #: weight bumped 0.03 -> 0.05 because the original
    # weight produced only ~0.18 mean green-share on optimised_sa (still
    # 7 BLUE_SPACE-ROAD adjacencies). 0.05 is justified as the same band
    # as `albedo_composite` (0.04) and `cool_refuge_distance` (0.04) --
    # both passive-cooling metrics in the same realism family, all of
    # which the supervisor explicitly flagged as priority B audits.
    # warned that high weights risk the SA clustering BLUE_SPACE into
    # one mega-pond instead of distributing the ponds; 0.05 keeps the
    # nudge strong without that pathology.
    "blue_space_green_buffer": 0.05,
    # SOLAR_FARM cells from residential 4-neighbours. Weight 0.03 -- same
    # band as `anthro_heat_clustering` (0.03), `wind_alignment` (0.02),
    # `building_wind_alignment` (0.03) since this is a passive-realism
    # nuisance metric. Soft (not HARD) because peri-urban Punjab realism
    # admits some residential-adjacent ground arrays; SA still nudged.
    # catchment re-anneal): 0.03 -> 0.06 to push residential cells off the
    # farm perimeter (the realism-flag overlay highlights these
    # adjacencies;.
    "solar_farm_residential_buffer": 0.06,
    "tree_shading_routes": 0.03,
    "cool_refuge_distance": 0.04,
    "water_body_proximity": 0.02,
    # rival "lakeside-premium" metric scoring HIGH_INCOME proximity
    # to BLUE_SPACE separately. Weight LOW (0.01) so it doesn't dominate the
    # equity-flavoured water_body_proximity above. The two together let the
    # SA optimiser balance realism (rich-near-water) and equity (all-near-water).
    "high_income_water_proximity": 0.01,
    # ---- C. Mixed-use ----
    "mixed_use_ratio_400m": 0.03,
    "shannon_diversity": 0.02,
    "walkable_destinations": 0.03,
    # ---- D. Transport / accessibility ----
    "access_school": 0.06,
    "access_commercial": 0.05,
    "access_healthcare": 0.05,
    "coverage_15min": 0.08,
    # ---- E. Energy-infrastructure layout proxies ----
    "open_space_cluster": 0.04,
    "infrastructure_distance": 0.06,
    "commercial_cluster": 0.03,
    # ---- F. Equity ----
    "ews_amenity_access": 0.08,
    "mid_ews_adjacency": 0.02,
    "ews_heat_shielding": 0.05,
    #: population-catchment coverage
    # for healthcare / school / public_services / shopping / religious.
    # Weight 0.05 — same band as `blue_space_green_buffer` (0.05) and
    # `ews_heat_shielding` (0.05), strong enough to actually move
    # amenity placement during SA but not so strong it dominates the
    # existing solar / road / buffer metrics. Pairs with the new
    # `_amenity_catchment_swap` SA move in `layout/optimiser.py`.
    "population_catchment_coverage": 0.05,
    # ---- G. STAGE- town form ----
    # Strong weights (0.07/0.07) - these are the objective that reshapes
    # the "village with trees" into clustered income blocks + a compact core.
    # Same band as the top solar/coverage metrics so they actually move the SA.
    "income_block_clustering": 0.07,
    "town_compactness": 0.07,
    # park_shape 0.05 = the population-catchment band (moves placement
    # without dominating solar/roads); open_singletons 0.03 = gentle
    # consolidation with the ~40-singleton sector-green allowance baked
    "park_shape": 0.05,
    "open_singletons": 0.03,
    # ---- H. STAGE- walkability (post-anneal overlay) ----
    # Weight DELIBERATELY 0.0: the street/path edges are stamped AFTER the
    # anneal, so mid-anneal the metric would score a half-built state. It is
    # computed + reported at export/verify only (see the function docstring).
    "walkability_permeability": 0.0,
}


def weighted_score(score: LayoutScore,
                    weights: Optional[Dict[str, float]] = None,
                    ) -> float:
    """Collapse all metrics into a single 0-1 score using a weighted sum.

    Returns
    -------
    float
        Weighted average of metric scores.
    """
    weights = weights or DEFAULT_WEIGHTS
    d = score.as_dict()
    s = sum(d[k] * w for k, w in weights.items())
    return s / sum(weights.values())
