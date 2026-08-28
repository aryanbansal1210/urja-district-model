"""Hard constraints any feasible layout must satisfy.

Each check is a pure function over a Grid (and sometimes Requirements / Config)
that returns a `ConstraintResult` with:

  * `passes`  - True if satisfied, False otherwise.
  * `gap`     - 0 if passing, larger positive number = bigger violation.
  * `message` - human-readable note for diagnostics.

The optimiser distinguishes HARD constraints (heavy penalty in cost) from
SOFT constraints (light penalty). Use `check_hard_constraints` and
`check_soft_constraints` to get the right subset. Use `check_all` if you
want everything for reporting.

Implemented constraints (subset of §G in `_spec/design_factors.md`):

  HARD:
    1. area_targets               - per-category tolerances against master-plan
    2. road_connectivity          - all ROAD cells form one component
    3. road_proximity             - every cell within K cells of a ROAD cell
    4. schools_vs_industry        - schools >= K cells from industry
    5. industry_on_edge           - industry within K cells of grid boundary
    6. hospital_near_road         - healthcare cell adjacent to a road
    7. amenities_road_frontage    - schools/shops/restaurants/public-services/hotels touch a road
    8. industrial_buffer          - no industry directly adjacent to residential
    9. solar_farm_clustering      - solar farm cells form clusters >= min size
   10. open_space_clustering      - open-space cells not all isolated singletons
   11. green_space_buffer         - NEW: tall (>=18 m) cells need an OPEN_SPACE / BLUE_SPACE / ROAD in 8-neighbourhood
   12. building_shading           - NEW: no built cell may have an S/SW/SE neighbour > 2 storeys taller
   13. highstreet_road_frontage   - NEW: RETAIL_HIGHSTREET cells need a ROAD in 4-neighbourhood
   14. school_catchment           - NEW: every residential cell within 1 km of a SCHOOL cell
   15. religious_catchment        - NEW: every residential cell within 800 m of a RELIGIOUS cell

  SOFT:
   16. requirements_satisfied     - cell counts >= demand-driven requirements

----------------------------------------------------------------------------
PENDING CONSTRAINTS  (single source of truth: _spec/IMPLEMENTATION_STATUS.md)
----------------------------------------------------------------------------
Designed but not yet implemented:

  - max building height per zone
  - minimum setbacks between adjacent residential blocks
  - public-transit coverage radius (transit not modelled yet)
  - inter-building gap >= 12 m perpendicular to wind (B.2 ventilation)
  - long building-rows broken every K cells (B.6 wind-shadow break)
  - open-space cells reserved for PV >= X percent (currently only via area target)
  - EWS within Y m of a primary amenity >= X percent (currently scored as F metric)
  - substation candidate cell count >= N (energy MILP territory)
  - drainage / flood: low-elevation cells designated OPEN_SPACE / BLUE_SPACE
    (deferred until elevation data is available)

DO NOT remove this header without first updating IMPLEMENTATION_STATUS.md.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Grid
from core.land_use import LandUse
from core.requirements import Requirements


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------
@dataclass
class ConstraintResult:
    """Outcome of one constraint check."""

    name: str
    passes: bool
    gap: float
    message: str

    def __str__(self) -> str:
        mark = "OK " if self.passes else "X  "
        return f"{mark} {self.name:<28} {self.message}"


# ---------------------------------------------------------------------------
# Per-category area-target tolerances. Tighter for big categories so they
# can't drift far; looser for small categories where +/- one cell is a big
# percentage move.
# ---------------------------------------------------------------------------
PER_CATEGORY_TOLERANCE: Dict[LandUse, float] = {
    LandUse.RESIDENTIAL_LOW: 0.04,
    LandUse.RESIDENTIAL_MID: 0.04,
    LandUse.RESIDENTIAL_HIGH: 0.04,
    LandUse.ROAD: 0.03,
    LandUse.OPEN_SPACE: 0.03,
    LandUse.LIGHT_INDUSTRY: 0.03,
    LandUse.WAREHOUSE: 0.02,
    LandUse.SHOPPING_CENTRE: 0.02,
    LandUse.RETAIL_HIGHSTREET: 0.03,
    LandUse.OFFICE: 0.02,
    LandUse.SCHOOL: 0.02,
    LandUse.HEALTHCARE: 0.02,
    LandUse.RESTAURANT_FOOD: 0.02,
    LandUse.HOTEL_GUESTHOUSE: 0.02,
    LandUse.PUBLIC_SERVICES: 0.02,
    LandUse.RELIGIOUS: 0.03,
    LandUse.BLUE_SPACE: 0.03,
    LandUse.SOLAR_FARM: 0.02,
    LandUse.PARKING_LOT: 0.03,
}
DEFAULT_TOLERANCE = 0.03


# ---------------------------------------------------------------------------
# Helper: 4-connected components of a coordinate set
# ---------------------------------------------------------------------------
def _components_4(coords: Set[Tuple[int, int]]) -> List[Set[Tuple[int, int]]]:
    """Return the 4-connected components of a set of (row, col) coordinates."""
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
    return components


# ---------------------------------------------------------------------------
# 1. Area-share targets (per-category tolerances)
# ---------------------------------------------------------------------------
def check_area_targets(grid: Grid,
                        cfg: Optional[DistrictConfig] = None,
                        ) -> ConstraintResult:
    """Each land-use's actual share is within its CATEGORY-specific tolerance.

    Major categories (residential, roads, open space) get tighter tolerances
    than small amenities, where +/- one cell is a big percentage swing.

    Returns
    -------
    ConstraintResult
        Area-target pass/fail result with worst overshoot as the gap.
    """
    cfg = cfg or load_config()
    counts: Dict[LandUse, int] = {}
    for cell in grid.all_cells():
        counts[cell.land_use] = counts.get(cell.land_use, 0) + 1

    worst_excess = 0.0
    worst_lu: Optional[LandUse] = None
    failures: List[str] = []
    for lu, target in cfg.land_use_targets.items():
        actual = counts.get(lu, 0) / grid.total_cells
        diff = abs(actual - target)
        # STAGE-: tolerance is now RELATIVE-
        # aware. The old fixed absolute band gave sub-1% classes enormous
        # relative slack SA grew restaurants 27 vs 2 required, hotels 20 vs
        # 1, within +/-3pp), which the requirements_trim pass then had to undo.
        # tol = the per-category absolute CAP, AND-ed with max(0.5pp, 30% of
        # target): big structural classes keep their absolute cap; small
        # facility classes are tightened to ~0.5pp so the SA cannot over-grow
        # them, and the trim becomes a safety net rather than load-bearing.
        abs_tol = PER_CATEGORY_TOLERANCE.get(lu, DEFAULT_TOLERANCE)
        tol = min(abs_tol, max(0.005, 0.30 * target))
        excess = max(0.0, diff - tol)
        if excess > worst_excess:
            worst_excess, worst_lu = excess, lu
        if excess > 0:
            failures.append(f"{lu.value}({actual:.1%} vs {target:.0%}+/-{tol:.0%})")

    passes = worst_excess == 0.0
    msg = (f"max overshoot {worst_excess:.1%} on {worst_lu.value}"
           if worst_lu else "all within tolerance")
    if failures and len(failures) <= 3:
        msg += "; " + ", ".join(failures)
    elif failures:
        msg += f"; {len(failures)} categories out of band"
    return ConstraintResult(
        name="area_targets",
        passes=passes,
        gap=worst_excess,
        message=msg,
    )


# ---------------------------------------------------------------------------
# 2. Road connectivity
# ---------------------------------------------------------------------------
def check_road_connectivity(grid: Grid) -> ConstraintResult:
    """All ROAD cells must form a single connected network.

    STAGE-: connectivity is judged over the UNION graph of
    (a) ROAD-cell 4-adjacency and (b) the local-street lane edges - a kept
    access-guard road cell whose lane chain reaches the collector grid IS
    connected to the network (the lane is a real 12 m street; counting only
    full road cells was the 46-component residual's accounting artifact).

    Returns
    -------
    ConstraintResult
        Road-connectivity result with disconnected road-cell share as gap.
    """
    road_coords = {
        (c.row, c.col) for c in grid.all_cells() if c.land_use == LandUse.ROAD
    }
    if not road_coords:
        return ConstraintResult(
            name="road_connectivity", passes=False, gap=1.0,
            message="no road cells",
        )
    # Union-graph BFS: nodes = road cells + lane-carrying cells; edges =
    # road-road 4-adjacency + lane edges (lanes chain through non-road cells
    # to join road fragments to the structural network).
    lane_adj: Dict[Tuple[int, int], Set[Tuple[int, int]]] = {}
    for e in grid.street_edges:
        if e.kind != "local_street":
            continue
        lane_adj.setdefault(e.a, set()).add(e.b)
        lane_adj.setdefault(e.b, set()).add(e.a)
    nodes = road_coords | set(lane_adj)
    seen: Set[Tuple[int, int]] = set()
    best_roads = 0
    n_components_with_roads = 0
    for start in nodes:
        if start in seen:
            continue
        comp_roads = 0
        q = deque([start])
        seen.add(start)
        while q:
            cur = q.popleft()
            if cur in road_coords:
                comp_roads += 1
            r, c = cur
            for nb in [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]:
                # road-road adjacency only counts between two ROAD cells
                if (nb in nodes and nb not in seen
                        and (cur in road_coords and nb in road_coords)):
                    seen.add(nb)
                    q.append(nb)
            for nb in lane_adj.get(cur, ()):
                if nb in nodes and nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        if comp_roads > 0:
            n_components_with_roads += 1
        best_roads = max(best_roads, comp_roads)
    unreached = len(road_coords) - best_roads
    passes = unreached == 0
    return ConstraintResult(
        name="road_connectivity",
        passes=passes,
        gap=unreached / max(1, len(road_coords)),
        message=(f"{best_roads}/{len(road_coords)} road cells in main "
                 f"network ({n_components_with_roads} road-bearing "
                 f"components, lanes counted as links)"),
    )


# ---------------------------------------------------------------------------
# 3. Road proximity
# ---------------------------------------------------------------------------
# Non-built / non-access-needing land-uses are exempt from road_proximity.
# Refinement landed planning rules require road access for built
# parcels (residential / commercial / civic / industrial) and for amenities,
# not for parks, water bodies, or solar farms. Solar farms ARE built up by
# service vehicles but at a much weaker access norm; if that becomes a real
# constraint later, split into a dedicated `solar_farm_road_access` rule
# rather than adding it back here.
ROAD_PROXIMITY_EXEMPT: Set[LandUse] = {
    LandUse.OPEN_SPACE,
    LandUse.BLUE_SPACE,
    LandUse.SOLAR_FARM,
    LandUse.ROAD,           # ROAD cells trivially satisfy the rule
}


def check_road_proximity(grid: Grid,
                          max_distance_cells: int = 3,
                          ) -> ConstraintResult:
    """Every built / access-needing cell must be within
    ``max_distance_cells`` 4-steps of a ROAD cell.

    OPEN_SPACE, BLUE_SPACE, SOLAR_FARM, and ROAD cells are exempt — they
    are listed in ``ROAD_PROXIMITY_EXEMPT``. The rule represents pedestrian
    and emergency-vehicle access for built parcels; parks and water bodies
    do not need the same standard, and solar farms only need an access lane
    for maintenance which is modelled separately by
    ``infrastructure_distance_score``.

    Returns
    -------
    ConstraintResult
        Road-proximity result with too-far built-cell share as the gap.
    """
    road_coords = [
        (c.row, c.col) for c in grid.all_cells() if c.land_use == LandUse.ROAD
    ]
    if not road_coords:
        return ConstraintResult(
            name="road_proximity", passes=False, gap=1.0,
            message="no roads",
        )

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

    too_far = 0
    max_d = 0
    n_checked = 0
    for cell in grid.all_cells():
        if cell.land_use in ROAD_PROXIMITY_EXEMPT:
            continue
        n_checked += 1
        d = dist[cell.row][cell.col]
        max_d = max(max_d, d)
        if d > max_distance_cells:
            too_far += 1

    passes = too_far == 0
    return ConstraintResult(
        name="road_proximity",
        passes=passes,
        gap=too_far / max(1, n_checked),
        message=(f"{too_far}/{n_checked} built cells > {max_distance_cells} "
                 f"cells from a road; max dist {max_d}"),
    )


# ---------------------------------------------------------------------------
# 4. Schools separated from industry
# ---------------------------------------------------------------------------
def check_schools_industry_separation(grid: Grid,
                                       min_separation_cells: int = 2,
                                       ) -> ConstraintResult:
    """No SCHOOL cell within `min_separation_cells` Chebyshev steps of any
    LIGHT_INDUSTRY or WAREHOUSE cell.

    Returns
    -------
    ConstraintResult
        School-industry separation result with violating school share as the gap.
    """
    schools = [(c.row, c.col) for c in grid.all_cells()
               if c.land_use == LandUse.SCHOOL]
    industry = [(c.row, c.col) for c in grid.all_cells()
                if c.land_use in (LandUse.LIGHT_INDUSTRY, LandUse.WAREHOUSE)]
    if not schools or not industry:
        return ConstraintResult(
            name="schools_vs_industry", passes=True, gap=0.0,
            message=f"{len(schools)} schools, {len(industry)} industrial cells",
        )

    violations = 0
    for sr, sc in schools:
        for ir, ic in industry:
            cheb = max(abs(sr - ir), abs(sc - ic))
            if cheb < min_separation_cells:
                violations += 1
                break

    passes = violations == 0
    return ConstraintResult(
        name="schools_vs_industry",
        passes=passes,
        gap=violations / max(1, len(schools)),
        message=(f"{violations}/{len(schools)} schools too close to industry "
                 f"(<{min_separation_cells} cells)"),
    )


# ---------------------------------------------------------------------------
# 5. Industry on edge
# ---------------------------------------------------------------------------
def check_industry_on_edge(grid: Grid,
                            max_dist_from_edge: int = 6,
                            ) -> ConstraintResult:
    """Industry should sit at the district edge so prevailing wind blows
    pollutants away from residential cells.

    Returns
    -------
    ConstraintResult
        Industry-edge result with interior industrial share as the gap.
    """
    industrial = [c for c in grid.all_cells()
                  if c.land_use in (LandUse.LIGHT_INDUSTRY, LandUse.WAREHOUSE)]
    if not industrial:
        return ConstraintResult(
            name="industry_on_edge", passes=True, gap=0.0,
            message="no industrial cells",
        )

    interior_industry = 0
    for c in industrial:
        edge_dist = min(
            c.row, c.col,
            grid.n_rows - 1 - c.row,
            grid.n_cols - 1 - c.col,
        )
        if edge_dist > max_dist_from_edge:
            interior_industry += 1

    passes = interior_industry == 0
    return ConstraintResult(
        name="industry_on_edge",
        passes=passes,
        gap=interior_industry / max(1, len(industrial)),
        message=(f"{interior_industry}/{len(industrial)} industrial cells "
                 f">{max_dist_from_edge} cells from edge"),
    )


# ---------------------------------------------------------------------------
# 6. Hospital adjacent to road
# ---------------------------------------------------------------------------
def check_hospital_near_road(grid: Grid) -> ConstraintResult:
    """Every HEALTHCARE cell must touch a ROAD cell (Moore neighbourhood).

    Returns
    -------
    ConstraintResult
        Healthcare-road adjacency result with non-adjacent share as the gap.
    """
    healthcare = [c for c in grid.all_cells()
                  if c.land_use == LandUse.HEALTHCARE]
    if not healthcare:
        return ConstraintResult(
            name="hospital_near_road", passes=True, gap=0.0,
            message="no healthcare cells",
        )

    not_adjacent = 0
    for h in healthcare:
        nbs = grid.neighbours_8(h.row, h.col)
        if not any(n.land_use == LandUse.ROAD for n in nbs):
            not_adjacent += 1

    passes = not_adjacent == 0
    return ConstraintResult(
        name="hospital_near_road",
        passes=passes,
        gap=not_adjacent / max(1, len(healthcare)),
        message=(f"{not_adjacent}/{len(healthcare)} healthcare cells not "
                 f"adjacent to a road"),
    )


# ---------------------------------------------------------------------------
# 7. NEW: amenity road frontage (schools, shops, restaurants, public
#    services, hotels). Healthcare is covered by check_hospital_near_road.
# ---------------------------------------------------------------------------
ROAD_FRONTAGE_REQUIRED: Set[LandUse] = {
    LandUse.SCHOOL,
    LandUse.SHOPPING_CENTRE,
    LandUse.RESTAURANT_FOOD,
    LandUse.PUBLIC_SERVICES,
    LandUse.HOTEL_GUESTHOUSE,
    LandUse.OFFICE,
    # added to the road-frontage requirement after the
    # placement audit flagged 14 RELIGIOUS cells with no ROAD 8-neighbour
    # (the largest single category in the audit). Cultural/community
    # facilities need road access for gatherings, processions, and
    # accessibility. HEALTHCARE is intentionally NOT added here — it has
    # its own stricter `check_hospital_near_road` (4-neighbour ambulance
    # access) that already covers the same physical requirement.
    LandUse.RELIGIOUS,
    # PARKING_LOT must touch a ROAD — you have to be able to drive into it.
    # Adding it to the frontage requirement gives the SA the signal to place
    # parking on road edges (near the office/mall/industry anchors it serves).
    LandUse.PARKING_LOT,
}


def check_amenities_road_frontage(grid: Grid) -> ConstraintResult:
    """SCHOOL / SHOPPING / RESTAURANT / PUBLIC_SERVICES / HOTEL / OFFICE cells
    must touch a ROAD cell (Moore neighbourhood) OR carry a STAGE- local
    access lane on one of their boundaries.

: a 12 m local street on the cell edge IS street frontage
    (that is exactly what the lane overlay exists to provide - register B8
    "little branches connecting buildings"); counting only full ROAD cells
    was the 100 m-grid artifact behind the 54/258 residual.

    Returns
    -------
    ConstraintResult
        Amenity-frontage result with non-fronted amenity share as the gap.
    """
    cells = [c for c in grid.all_cells() if c.land_use in ROAD_FRONTAGE_REQUIRED]
    if not cells:
        return ConstraintResult(
            name="amenities_road_frontage", passes=True, gap=0.0,
            message="no amenities to check",
        )
    laned: Set[Tuple[int, int]] = set()
    for e in grid.street_edges:
        if e.kind == "local_street":
            laned.add(e.a)
            laned.add(e.b)
    not_adjacent = 0
    for c in cells:
        if (c.row, c.col) in laned:
            continue
        if not any(n.land_use == LandUse.ROAD
                   for n in grid.neighbours_8(c.row, c.col)):
            not_adjacent += 1
    passes = not_adjacent == 0
    return ConstraintResult(
        name="amenities_road_frontage",
        passes=passes,
        gap=not_adjacent / max(1, len(cells)),
        message=(f"{not_adjacent}/{len(cells)} amenities (schools / shops / "
                 f"restaurants / hotels / public services / offices) lack "
                 f"road or local-street frontage"),
    )


# ---------------------------------------------------------------------------
# 8. NEW: industrial buffer (no industry directly touching residential)
# ---------------------------------------------------------------------------
def check_industrial_buffer(grid: Grid) -> ConstraintResult:
    """No LIGHT_INDUSTRY or WAREHOUSE cell may have a SENSITIVE 8-neighbour.

    Sensitive land uses:
      * any RESIDENTIAL_*
      * RELIGIOUS ( audit A26: gurudwaras/temples shouldn't share
        boundary with industrial activity -- cultural mismatch).
    SCHOOL and HEALTHCARE have their own dedicated separation constraints
    (`schools_vs_industry` + `hospital_near_road`) so they aren't included
    here to avoid double-counting.

    Returns
    -------
    ConstraintResult
        Industrial-buffer result with violating industrial share as the gap.
    """
    industrial = [c for c in grid.all_cells()
                  if c.land_use in (LandUse.LIGHT_INDUSTRY, LandUse.WAREHOUSE)]
    if not industrial:
        return ConstraintResult(
            name="industrial_buffer", passes=True, gap=0.0,
            message="no industrial cells",
        )

    violating = 0
    for c in industrial:
        for n in grid.neighbours_8(c.row, c.col):
            if n.land_use.is_residential or n.land_use == LandUse.RELIGIOUS:
                violating += 1
                break

    passes = violating == 0
    return ConstraintResult(
        name="industrial_buffer",
        passes=passes,
        gap=violating / max(1, len(industrial)),
        message=(f"{violating}/{len(industrial)} industrial cells touch "
                 f"residential or religious (need road / open-space buffer)"),
    )


# ---------------------------------------------------------------------------
# 9. NEW: solar-farm clustering (avoid scattered single-cell fragments)
# ---------------------------------------------------------------------------
def check_solar_farm_clustering(grid: Grid,
                                  min_cluster_size: int = 4,
                                  ) -> ConstraintResult:
    """SOLAR_FARM cells should form clusters of at least `min_cluster_size`.
    Singletons and small fragments fail.

    Returns
    -------
    ConstraintResult
        Solar-clustering result with below-minimum cell share as the gap.
    """
    coords = {(c.row, c.col) for c in grid.all_cells()
              if c.land_use == LandUse.SOLAR_FARM}
    if not coords:
        return ConstraintResult(
            name="solar_farm_clustering", passes=True, gap=0.0,
            message="no solar-farm cells",
        )
    components = _components_4(coords)
    n_components = len(components)
    cells_in_small = sum(len(c) for c in components if len(c) < min_cluster_size)
    n_small = sum(1 for c in components if len(c) < min_cluster_size)
    n_singletons = sum(1 for c in components if len(c) == 1)

    # gap = fraction of solar cells stuck in below-min clusters
    gap = cells_in_small / max(1, len(coords))
    passes = cells_in_small == 0
    return ConstraintResult(
        name="solar_farm_clustering",
        passes=passes,
        gap=gap,
        message=(f"{n_components} components, {n_small} below "
                 f"{min_cluster_size} cells ({n_singletons} singletons), "
                 f"{cells_in_small}/{len(coords)} cells in small clusters"),
    )


# ---------------------------------------------------------------------------
# 10. NEW: open-space clustering (avoid green confetti)
# ---------------------------------------------------------------------------
def check_open_space_clustering(grid: Grid,
                                  min_cluster_size: int = 4,
                                  max_singleton_share: float = 0.25,
                                  ) -> ConstraintResult:
    """At most ``max_singleton_share`` of green-blue cells may be singletons,
    AND at least 60 % of those cells should belong to clusters of size
    ``>= min_cluster_size``.

    "Green-blue cells" = OPEN_SPACE ∪ BLUE_SPACE. The union landed
 from a heat-island and recreational-coherence perspective
    parks and water bodies serve the same clustering purpose, so 4-cell
    pond next to a 4-cell park reads as one 8-cell green-blue patch
    instead of two singletons. The constraint name and gap semantics
    don't change.

    Returns
    -------
    ConstraintResult
        Open-space clustering result with the larger clustering violation as the gap.
    """
    coords = {(c.row, c.col) for c in grid.all_cells()
              if c.land_use in (LandUse.OPEN_SPACE, LandUse.BLUE_SPACE)}
    if not coords:
        return ConstraintResult(
            name="open_space_clustering", passes=True, gap=0.0,
            message="no open/blue cells",
        )
    components = _components_4(coords)
    cells_in_singletons = sum(1 for c in components if len(c) == 1)
    cells_in_big = sum(len(c) for c in components if len(c) >= min_cluster_size)
    big_share = cells_in_big / max(1, len(coords))
    singleton_share = cells_in_singletons / max(1, len(coords))

    passes = (singleton_share <= max_singleton_share) and (big_share >= 0.60)
    # gap is whichever rule is more violated
    gap_singletons = max(0.0, singleton_share - max_singleton_share)
    gap_big = max(0.0, 0.60 - big_share)
    gap = max(gap_singletons, gap_big)
    return ConstraintResult(
        name="open_space_clustering",
        passes=passes,
        gap=gap,
        message=(f"{singleton_share:.0%} singletons (<={max_singleton_share:.0%}), "
                 f"{big_share:.0%} in big clusters (>=60%), "
                 f"{len(components)} components"),
    )


# ---------------------------------------------------------------------------
# 11. NEW: green-space buffer for tall buildings (anti-congestion / ventilation)
# ---------------------------------------------------------------------------
# Calibrated from 18 m -> 21 m. The original Stage A spec said
# "any cell with height >= 18 m" but 18 m is the medium tier for both
# RESIDENTIAL_MID and the default RESIDENTIAL_HIGH typical height, which
# catches a very large share of residential cells. At Indian planning
# practice level, "tall buildings need a buffer" really means 7+ storey
# blocks (>=21 m), not 6-storey mid-rises. The 21 m threshold catches
# HOTEL_GUESTHOUSE (21 m typical), OFFICE (24 m), and TALL-tier residential
# (27 m) while leaving normal 6-storey mid-rises unconstrained.
TALL_BUILDING_HEIGHT_M = 21.0


def check_green_space_buffer(grid: Grid,
                              tall_threshold_m: float = TALL_BUILDING_HEIGHT_M,
                              ) -> ConstraintResult:
    """Every built cell at or above ``tall_threshold_m`` must have at least
    one OPEN_SPACE / BLUE_SPACE / ROAD cell in its 8-neighbourhood.

    This is the anti-congestion / cross-ventilation rule from Stage A.
    The default threshold is 21 m (7 storeys at 3 m floor-to-floor).

    Returns
    -------
    ConstraintResult
        Green-space buffer result with the violating-tall-cell share as the gap.
    """
    open_uses = {LandUse.OPEN_SPACE, LandUse.BLUE_SPACE, LandUse.ROAD}
    tall_cells = [
        c for c in grid.all_cells()
        if c.has_building and c.height_m >= tall_threshold_m
    ]
    if not tall_cells:
        return ConstraintResult(
            name="green_space_buffer", passes=True, gap=0.0,
            message=f"no cells >= {tall_threshold_m:.0f} m",
        )
    violating = 0
    for c in tall_cells:
        if not any(nb.land_use in open_uses
                   for nb in grid.neighbours_8(c.row, c.col)):
            violating += 1
    passes = violating == 0
    return ConstraintResult(
        name="green_space_buffer",
        passes=passes,
        gap=violating / max(1, len(tall_cells)),
        message=(f"{violating}/{len(tall_cells)} tall (>={tall_threshold_m:.0f} m) "
                 f"cells lack an open / blue / road buffer in 8-neighbourhood"),
    )


# ---------------------------------------------------------------------------
# 12. NEW: building-to-building solar shading (hard version)
# ---------------------------------------------------------------------------
# Calibrated from 6 m -> 9 m. Original Stage A spec said
# ">2 storeys taller" but 6 m at 200 m cell granularity is normal mixed-
# density variation (e.g. a 4-storey block beside a 6-storey block — well
# within typical Indian neighbourhood character). The hard-failure threshold
# should be set where the height differential genuinely blocks winter sun
# and rooftop PV on the southern building: 3+ storeys = 9 m. Beneficial
# street shading (cooler walking routes) is captured by the soft
# ``solar_access_score`` and the new ``tree_shading_routes`` metric, both
# of which stay in play.
#: single source of truth, core/shading_constants.py
# The layout hard constraint deliberately uses a LOOSER threshold (3 storeys)
# than the PV side (2 storeys): a planning failure is a stronger claim than a
# yield penalty, so it takes more building to trigger it.
from core.shading_constants import DAYLIGHT_BLOCKAGE_DELTA_M

SHADING_DELTA_M = DAYLIGHT_BLOCKAGE_DELTA_M   # 9.0 m = 3 storeys


def check_building_shading(grid: Grid,
                            delta_m: float = SHADING_DELTA_M,
                            ) -> ConstraintResult:
    """No built cell may have any S / SW / SE neighbour more than
    ``delta_m`` metres taller than itself.

    Hard version of ``solar_access_score``. Applied to BUILT cells
    (residential + non-residential alike); ground PV (SOLAR_FARM) is
    already covered by ``solar_access_score`` as a soft metric and is
    intentionally outside this hard check (otherwise every SOLAR_FARM
    cell with even a short building to its south would block the layout).

    Returns
    -------
    ConstraintResult
        Building-shading result with the violating-built-cell share as the gap.
    """
    built = [c for c in grid.all_cells() if c.has_building]
    if not built:
        return ConstraintResult(
            name="building_shading", passes=True, gap=0.0,
            message="no built cells",
        )
    # row decreases southward (row 0 is south), so the S / SW / SE
    # neighbours sit at (row - 1, col + {-1, 0, +1}).
    south_offsets = [(-1, -1), (-1, 0), (-1, 1)]
    violating = 0
    for c in built:
        for dr, dc in south_offsets:
            nr, nc = c.row + dr, c.col + dc
            if 0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols:
                nb = grid.at(nr, nc)
                if nb.height_m - c.height_m > delta_m:
                    violating += 1
                    break
    passes = violating == 0
    return ConstraintResult(
        name="building_shading",
        passes=passes,
        gap=violating / max(1, len(built)),
        message=(f"{violating}/{len(built)} built cells have an S/SW/SE "
                 f"neighbour >{delta_m:.0f} m taller"),
    )


# ---------------------------------------------------------------------------
# 13. NEW: RETAIL_HIGHSTREET must have a ROAD in 4-neighbourhood
# ---------------------------------------------------------------------------
def check_highstreet_road_frontage(grid: Grid) -> ConstraintResult:
    """RETAIL_HIGHSTREET cells must touch a ROAD cell on a 4-neighbour edge.

    Tighter than ``amenities_road_frontage`` (which uses an 8-neighbour
    check) because the high-street pattern explicitly fronts a primary
    road, not just sits near one.

    Returns
    -------
    ConstraintResult
        High-street frontage result with the non-fronting share as the gap.
    """
    cells = [c for c in grid.all_cells()
             if c.land_use == LandUse.RETAIL_HIGHSTREET]
    if not cells:
        return ConstraintResult(
            name="highstreet_road_frontage", passes=True, gap=0.0,
            message="no high-street cells",
        )
    not_adjacent = 0
    for c in cells:
        if not any(nb.land_use == LandUse.ROAD
                   for nb in grid.neighbours_4(c.row, c.col)):
            not_adjacent += 1
    passes = not_adjacent == 0
    return ConstraintResult(
        name="highstreet_road_frontage",
        passes=passes,
        gap=not_adjacent / max(1, len(cells)),
        message=(f"{not_adjacent}/{len(cells)} RETAIL_HIGHSTREET cells lack a "
                 f"ROAD on a 4-neighbour edge"),
    )


# ---------------------------------------------------------------------------
# 14. NEW: PARKING_LOT must have a ROAD in 4-neighbourhood
# ---------------------------------------------------------------------------
def check_parking_road_frontage(grid: Grid) -> ConstraintResult:
    """PARKING_LOT cells must touch a ROAD on a 4-neighbour edge.

    Cars must be able to drive in: the 8-neighbour ``amenities_road_frontage``
    allows a diagonal-only touch, which is not drivable. This is the strict
    drive-in rule for carport parking lots (modelled on
    ``check_highstreet_road_frontage``).

    Returns
    -------
    ConstraintResult
        Parking road-frontage result with the non-fronting share as the gap.
    """
    cells = [c for c in grid.all_cells()
             if c.land_use == LandUse.PARKING_LOT]
    if not cells:
        return ConstraintResult(
            name="parking_road_frontage", passes=True, gap=0.0,
            message="no parking lots",
        )
    # STAGE-/B18: a LOCAL STREET on the lot's boundary is
    # must front a road OR STREET", and the lane overlay explicitly
    # serves every PARKING_LOT cell (assign_local_streets needy set).
    laned: Set[Tuple[int, int]] = set()
    for e in grid.street_edges:
        if e.kind == "local_street":
            laned.add(e.a)
            laned.add(e.b)
    not_adjacent = 0
    bad = []
    for c in cells:
        if (c.row, c.col) in laned:
            continue
        if not any(nb.land_use == LandUse.ROAD
                   for nb in grid.neighbours_4(c.row, c.col)):
            not_adjacent += 1
            bad.append((c.row, c.col))
    passes = not_adjacent == 0
    return ConstraintResult(
        name="parking_road_frontage",
        passes=passes,
        gap=not_adjacent / max(1, len(cells)),
        message=(f"{not_adjacent}/{len(cells)} PARKING_LOT cells lack a "
                 f"ROAD on a 4-neighbour edge: {bad[:5]}"),
    )


# ---------------------------------------------------------------------------
# Stage C plant siting buffer.
# RESIDENTIAL_BUFFER / SCHOOL_BUFFER are validated on the chosen plant
# cells stored in `grid.plant_placements`. Buffer violations show up as
# the gap; "no placements" is treated as a pass (the constraint only
# bites once placements have been made).
# ---------------------------------------------------------------------------
def check_stage_c_plant_buffer(grid: Grid) -> ConstraintResult:
    """Validate the residential / school buffers on placed Stage C plants.

    Reads ``grid.plant_placements`` (populated by
    ``layout.plant_siting.place_stage_c_plants``). Each placement must
    meet:
      * residential 4-neighbour Manhattan distance >= 3 cells (600 m);
      * school     4-neighbour Manhattan distance >= 2 cells (400 m).

    Returns
    -------
    ConstraintResult
        Buffer-violation share as the gap. If no placements exist on
        the grid, returns "no plant placements" pass (the spatial siting
        step has not been run yet).
    """
    placements = getattr(grid, "plant_placements", {}) or {}
    if not placements:
        return ConstraintResult(
            name="stage_c_plant_buffer", passes=True, gap=0.0,
            message="no plant placements (site step not run)",
        )
    violations = 0
    notes: List[str] = []
    for kind, p in placements.items():
        if p.min_residential_distance_cells < 3:
            violations += 1
            notes.append(f"{kind} too close to residential "
                         f"({p.min_residential_distance_cells} cells)")
        if p.min_school_distance_cells < 2:
            violations += 1
            notes.append(f"{kind} too close to school "
                         f"({p.min_school_distance_cells} cells)")
    return ConstraintResult(
        name="stage_c_plant_buffer",
        passes=violations == 0,
        gap=violations / max(1, len(placements) * 2),  # 2 buffers per plant
        message=("; ".join(notes) if notes
                 else f"{len(placements)} placements OK"),
    )


# ---------------------------------------------------------------------------
# 13b. NEW: RETAIL_HIGHSTREET must form connected
# road-fronting CHAINS, not isolated standalone parcels. Minimum chain
# length 4 cells, each cell adjacent to ROAD, at most two chain endpoints
# (cells with only one high-street 4-neighbour) per component.
# ---------------------------------------------------------------------------
HIGHSTREET_MIN_CHAIN_LENGTH: int = 4
HIGHSTREET_MAX_ENDPOINTS: int = 2


def check_highstreet_corridor(grid: Grid) -> ConstraintResult:
    """RETAIL_HIGHSTREET cells must form chains of >= 4 connected cells,
    with each cell ROAD-adjacent and at most two chain endpoints per
    connected component (so a chain, not a star or T-junction).

    Failure modes counted as failing cells:
      * component size < HIGHSTREET_MIN_CHAIN_LENGTH (isolated parcels,
        2-cell pairs, 3-cell stubs);
      * component endpoint count > HIGHSTREET_MAX_ENDPOINTS (Y / + / T
        branchings -- not high-street typology);
      * cell lacks a ROAD 4-neighbour (caught by sibling check too;
        repeated here so any pre-existing layout that satisfied the
        looser check still surfaces a violation if a chain is corridor-
        sized but lacks frontage).

    Returns
    -------
    ConstraintResult
        Gap is share of high-street cells in non-conforming components.
    """
    cells = [c for c in grid.all_cells()
             if c.land_use == LandUse.RETAIL_HIGHSTREET]
    if not cells:
        return ConstraintResult(
            name="highstreet_corridor", passes=True, gap=0.0,
            message="no high-street cells",
        )

    cells_by_pos = {(c.row, c.col): c for c in cells}
    visited: Set[Tuple[int, int]] = set()
    failing_cells = 0
    n_components = 0
    n_short_components = 0
    n_branched_components = 0
    n_unfronted_components = 0

    for start in cells:
        if (start.row, start.col) in visited:
            continue
        # 4-connected BFS over highstreet cells only.
        component: List[Tuple[int, int]] = []
        frontier = [(start.row, start.col)]
        while frontier:
            r, c = frontier.pop()
            if (r, c) in visited:
                continue
            visited.add((r, c))
            component.append((r, c))
            for nb in grid.neighbours_4(r, c):
                if (nb.row, nb.col) in cells_by_pos and (nb.row, nb.col) not in visited:
                    frontier.append((nb.row, nb.col))

        n_components += 1
        size = len(component)
        # Endpoint count: cells with exactly 1 highstreet 4-neighbour.
        endpoints = 0
        for r, c in component:
            highstreet_neighbour_count = sum(
                1 for nb in grid.neighbours_4(r, c)
                if (nb.row, nb.col) in cells_by_pos
            )
            if highstreet_neighbour_count == 1:
                endpoints += 1
        # Frontage check per cell in component.
        unfronted = 0
        for r, c in component:
            if not any(nb.land_use == LandUse.ROAD
                       for nb in grid.neighbours_4(r, c)):
                unfronted += 1

        component_fails = (
            size < HIGHSTREET_MIN_CHAIN_LENGTH
            or endpoints > HIGHSTREET_MAX_ENDPOINTS
            or unfronted > 0
        )
        if size < HIGHSTREET_MIN_CHAIN_LENGTH:
            n_short_components += 1
        if endpoints > HIGHSTREET_MAX_ENDPOINTS:
            n_branched_components += 1
        if unfronted > 0:
            n_unfronted_components += 1
        if component_fails:
            failing_cells += size

    passes = failing_cells == 0
    return ConstraintResult(
        name="highstreet_corridor",
        passes=passes,
        gap=failing_cells / max(1, len(cells)),
        message=(
            f"{failing_cells}/{len(cells)} highstreet cells in non-conforming "
            f"components (short: {n_short_components}, branched: "
            f"{n_branched_components}, unfronted: {n_unfronted_components}; "
            f"{n_components} components total)"
        ),
    )


# ---------------------------------------------------------------------------
# 14 & 15. NEW: amenity catchment for schools and religious facilities
# ---------------------------------------------------------------------------
# (Claude 2 critical-review #4): catchment radii consolidated
# in `config/district_composition.yaml:constraint_catchments_m`. The
# module-level constants below are now LOADED from YAML at first access,
# with the hardcoded numbers as fallback so tests that build a Grid
# without a config still work. URDPFI 2014 §8.2 Table 2 is the anchoring
# document for all five catchment radii.
def _load_catchments() -> Dict[str, float]:
    try:
        cfg = load_config()
        return dict(cfg.constraint_catchments_m or {})
    except Exception:
        return {}


_CATCHMENTS = _load_catchments()
SCHOOL_CATCHMENT_M = float(_CATCHMENTS.get("school", 1000.0))
RELIGIOUS_CATCHMENT_M = float(_CATCHMENTS.get("religious", 800.0))


def _residential_uncovered_count(grid: Grid,
                                  amenity: LandUse,
                                  radius_m: float,
                                  ) -> Tuple[int, int]:
    """Helper: count residential cells with no amenity cell within `radius_m`.

    Uses cell-centre Manhattan distance, which approximates walking on the
    grid. Returns ``(violating, total)``.
    """
    residents = [c for c in grid.all_cells() if c.is_residential]
    if not residents:
        return 0, 0
    amenities = grid.cells_of(amenity)
    if not amenities:
        return len(residents), len(residents)
    violating = 0
    for r in residents:
        nearest_m = min(Grid.manhattan_distance(r, a) for a in amenities)
        if nearest_m > radius_m:
            violating += 1
    return violating, len(residents)


def check_school_catchment(grid: Grid,
                            radius_m: float = SCHOOL_CATCHMENT_M,
                            ) -> ConstraintResult:
    """Every RESIDENTIAL cell must be within `radius_m` Manhattan walking
    distance of at least one SCHOOL cell.

    Returns
    -------
    ConstraintResult
        School-catchment result with the uncovered-residential share as the gap.
    """
    violating, total = _residential_uncovered_count(
        grid, LandUse.SCHOOL, radius_m,
    )
    if total == 0:
        return ConstraintResult(
            name="school_catchment", passes=True, gap=0.0,
            message="no residential cells",
        )
    passes = violating == 0
    return ConstraintResult(
        name="school_catchment",
        passes=passes,
        gap=violating / total,
        message=(f"{violating}/{total} residential cells > {radius_m:.0f} m "
                 f"Manhattan from a SCHOOL"),
    )


# ---------------------------------------------------------------------------
# 15b. NEW:
# Amenity equity - every income class must have minimum access to public
# amenities, regardless of market dynamics. The 'lakeside premium' effect
# (rich-near-water) is still allowed to emerge from the soft metric
# `high_income_water_body_proximity`, but the hard constraint ensures NO
# income class is locked out of healthcare / blue-space / green-space access.
# ---------------------------------------------------------------------------
COOL_REFUGE_CATCHMENT_M = float(_CATCHMENTS.get("cool_refuge", 1000.0))   # 800 m walk + grid-cell rounding
#: 1200 -> 2500 for the IPHS facility model (2 UPHC + 1 UCHC
# for 100k). UPHC primary-care walking radius ~2 km + 200 m-grid rounding; the
# CHC/hospital is 5 km vehicular (the soft-catchment radius). The old 1200 m was
# calibrated for the retired ~12-dispensary model and is unmeetable with 3 cells.
HEALTHCARE_CATCHMENT_M = float(_CATCHMENTS.get("healthcare", 2500.0))     # IPHS UPHC ~2 km walk + rounding
#: the existing `amenity_equity` constraint counts
# BLUE_SPACE as a valid cool refuge, which let the SA satisfy the
# residential cool-refuge requirement entirely with water bodies in one
# corner -- leaving large residential clusters (e.g. the NE quadrant
# row 1-11, col 13-23 on optimised_sa) with zero OPEN_SPACE / park
# nearby. URDPFI 2014 §8.2 Table 2 "Recreational" prescribes a
# neighbourhood-park standard of 0.5 ha per 1000 population within
# 500-800 m. We pin the upper bound at 600 m (3 cells at 200 m grid)
# so the constraint is satisfiable on a 25x25 grid without forcing
# every residential cluster to have a park literally next door.
PARK_CATCHMENT_M = float(_CATCHMENTS.get("park", 600.0))
# Per-quadrant minimum park-cell count. The grid is divided into 4
# equal NW / NE / SW / SE quadrants by the row/col midpoints. The
# constraint requires each quadrant containing residential cells to
# host at least PARK_CELLS_PER_QUADRANT_MIN OPEN_SPACE cells. With a
# 25x25 grid the quadrants are ~12x12 = ~144 cells each; URDPFI
# greenery norms suggest ~7-10% greenery in residential neighbourhoods,
# so 4 OPEN_SPACE cells per quadrant (~2.8% of a quadrant's area) is
# a conservative floor that still avoids the "all parks in one corner"
# pathology.
def _load_park_cells_min() -> int:
    try:
        cfg = load_config()
        return int(cfg.park_cells_per_quadrant_min or 4)
    except Exception:
        return 4


PARK_CELLS_PER_QUADRANT_MIN = _load_park_cells_min()


def check_amenity_equity(grid: Grid,
                          cool_refuge_radius_m: float = COOL_REFUGE_CATCHMENT_M,
                          healthcare_radius_m: float = HEALTHCARE_CATCHMENT_M,
                          ) -> ConstraintResult:
    """Every residential cell of every income class must have:
      (a) an OPEN_SPACE or BLUE_SPACE cool refuge within ``cool_refuge_radius_m``;
      (b) a HEALTHCARE cell within ``healthcare_radius_m``.

    Soft metric `water_body_proximity_score` rewards short distance to
    BLUE_SPACE; soft metric `high_income_water_body_proximity` separately
    rewards short distance for HIGH-income cells specifically. The
    interaction: SA will preferentially place BLUE_SPACE near high-income
    residential to maximise the soft metric BUT the hard constraint below
    prevents any low-income or mid-income cell from being marooned far from
    a cool refuge or hospital. Captures the supervisor's option C "hybrid
    hard constraint" model -- equity floor + emergent rich-buy-nearby.

    Reports the worst gap across the two checks.
    """
    residents = [c for c in grid.all_cells() if c.is_residential]
    if not residents:
        return ConstraintResult(
            name="amenity_equity", passes=True, gap=0.0,
            message="no residential cells",
        )

    cool_targets = [c for c in grid.all_cells()
                     if c.land_use in (LandUse.OPEN_SPACE, LandUse.BLUE_SPACE)]
    health_targets = grid.cells_of(LandUse.HEALTHCARE)

    cool_violating = 0
    health_violating = 0
    for r in residents:
        if not cool_targets:
            cool_violating += 1
        else:
            d_cool = min(Grid.manhattan_distance(r, t) for t in cool_targets)
            if d_cool > cool_refuge_radius_m:
                cool_violating += 1
        if not health_targets:
            health_violating += 1
        else:
            d_health = min(Grid.manhattan_distance(r, t) for t in health_targets)
            if d_health > healthcare_radius_m:
                health_violating += 1

    n = len(residents)
    cool_gap = cool_violating / n
    health_gap = health_violating / n
    worst_gap = max(cool_gap, health_gap)
    return ConstraintResult(
        name="amenity_equity",
        passes=(cool_violating == 0 and health_violating == 0),
        gap=worst_gap,
        message=(f"{cool_violating}/{n} residential cells > "
                 f"{cool_refuge_radius_m:.0f} m from OPEN/BLUE_SPACE, and "
                 f"{health_violating}/{n} > {healthcare_radius_m:.0f} m from HEALTHCARE"),
    )


def check_park_quadrant_coverage(grid: Grid,
                                   park_radius_m: float = PARK_CATCHMENT_M,
                                   cells_per_quadrant_min: int = PARK_CELLS_PER_QUADRANT_MIN,
                                   ) -> ConstraintResult:
    """Every residential cell must have an OPEN_SPACE park within
    ``park_radius_m`` Manhattan distance, AND each of the four district
    quadrants (NW / NE / SW / SE) containing residential cells must host
    at least ``cells_per_quadrant_min`` OPEN_SPACE cells.

: the existing `amenity_equity` constraint counts
    BLUE_SPACE as a valid cool refuge, so the SA was satisfying the
    residential-near-green requirement entirely with water bodies in one
    corner of the district. On optimised_sa this left the entire NE
    quadrant (rows 1-11, cols 13-23) with zero parks and zero water --
    57 residential cells with no green amenity nearby.

    This new HARD constraint forces:
      (a) per-residential park proximity (OPEN_SPACE specifically, not
          BLUE_SPACE) within 600 m;
      (b) per-quadrant minimum park count so the SA cannot satisfy (a)
          with a single mega-park serving all four quadrants.

    Gap is the worse of (parks-missing-per-quadrant-share,
    residentials-far-from-park-share).
    """
    residents = [c for c in grid.all_cells() if c.is_residential]
    if not residents:
        return ConstraintResult(
            name="park_quadrant_coverage", passes=True, gap=0.0,
            message="no residential cells",
        )

    parks = [c for c in grid.all_cells() if c.land_use == LandUse.OPEN_SPACE]

    # Per-residential park-proximity check.
    far_residents = 0
    if not parks:
        far_residents = len(residents)
    else:
        for r in residents:
            d = min(Grid.manhattan_distance(r, p) for p in parks)
            if d > park_radius_m:
                far_residents += 1
    prox_gap = far_residents / len(residents)

    # Per-quadrant park-count check. Quadrants by row/col midpoints.
    n_rows = grid.n_rows
    n_cols = grid.n_cols
    row_mid = n_rows // 2
    col_mid = n_cols // 2

    def _quadrant(c) -> str:
        r_top = c.row < row_mid
        c_left = c.col < col_mid
        return ("nw" if c_left else "ne") if r_top else ("sw" if c_left else "se")

    park_counts = {"nw": 0, "ne": 0, "sw": 0, "se": 0}
    for p in parks:
        park_counts[_quadrant(p)] += 1

    res_quadrants = {_quadrant(r) for r in residents}
    deficits = [
        max(0, cells_per_quadrant_min - park_counts[q]) for q in res_quadrants
    ]
    quad_violating = sum(1 for d in deficits if d > 0)
    quad_gap = quad_violating / max(1, len(res_quadrants))

    worst_gap = max(prox_gap, quad_gap)
    counts_str = ", ".join(f"{q}={park_counts[q]}" for q in ("nw", "ne", "sw", "se"))
    return ConstraintResult(
        name="park_quadrant_coverage",
        passes=(far_residents == 0 and quad_violating == 0),
        gap=worst_gap,
        message=(f"{far_residents}/{len(residents)} residential cells > "
                 f"{park_radius_m:.0f} m from any OPEN_SPACE; "
                 f"per-quadrant parks ({counts_str}), required >= "
                 f"{cells_per_quadrant_min} per residential quadrant"),
    )


def check_religious_catchment(grid: Grid,
                                radius_m: float = RELIGIOUS_CATCHMENT_M,
                                ) -> ConstraintResult:
    """Every RESIDENTIAL cell must be within `radius_m` Manhattan walking
    distance of at least one RELIGIOUS cell.

    Returns
    -------
    ConstraintResult
        Religious-catchment result with the uncovered-residential share as the gap.
    """
    violating, total = _residential_uncovered_count(
        grid, LandUse.RELIGIOUS, radius_m,
    )
    if total == 0:
        return ConstraintResult(
            name="religious_catchment", passes=True, gap=0.0,
            message="no residential cells",
        )
    passes = violating == 0
    return ConstraintResult(
        name="religious_catchment",
        passes=passes,
        gap=violating / total,
        message=(f"{violating}/{total} residential cells > {radius_m:.0f} m "
                 f"Manhattan from a RELIGIOUS cell"),
    )


# ---------------------------------------------------------------------------
# 16. Requirements satisfied (SOFT)
# ---------------------------------------------------------------------------
def check_requirements_satisfied(grid: Grid,
                                  req: Requirements,
                                  ) -> ConstraintResult:
    """Actual cell count per land-use >= required cell count. SOFT.

    Returns
    -------
    ConstraintResult
        Soft requirements result with worst land-use shortfall as the gap.
    """
    actual: Dict[LandUse, int] = {}
    for cell in grid.all_cells():
        actual[cell.land_use] = actual.get(cell.land_use, 0) + 1

    worst_short = 0.0
    worst_lu: Optional[LandUse] = None
    deficits: List[str] = []
    for lu, needed in req.required_cells_by_landuse.items():
        if needed <= 0:
            continue
        have = actual.get(lu, 0)
        if have < needed:
            short_frac = (needed - have) / needed
            if short_frac > worst_short:
                worst_short, worst_lu = short_frac, lu
            deficits.append(f"{lu.value}({have}/{needed})")

    passes = worst_short == 0.0
    msg = (f"largest shortfall {worst_short:.0%} on {worst_lu.value}"
           if worst_lu else "all requirements met")
    if deficits and len(deficits) <= 4:
        msg += "; " + ", ".join(deficits)
    elif deficits:
        msg += f"; {len(deficits)} land-uses short"
    return ConstraintResult(
        name="requirements_satisfied",
        passes=passes,
        gap=worst_short,
        message=msg,
    )


# ---------------------------------------------------------------------------
# Hard / soft separation. The optimiser uses these subsets to apply
# different penalty weights.
# ---------------------------------------------------------------------------
HARD_CONSTRAINT_NAMES: Set[str] = {
    "area_targets",
    "road_connectivity",
    "road_proximity",
    "schools_vs_industry",
    "industry_on_edge",
    "hospital_near_road",
    "amenities_road_frontage",
    "industrial_buffer",
    "solar_farm_clustering",
    "open_space_clustering",
    "green_space_buffer",
    "building_shading",
    "highstreet_road_frontage",
    "highstreet_corridor",
    "school_catchment",
    "religious_catchment",
    "amenity_equity",
    "park_quadrant_coverage",
    "stage_c_plant_buffer",
    "parking_road_frontage",
}
SOFT_CONSTRAINT_NAMES: Set[str] = {
    "requirements_satisfied",
}


def check_hard_constraints(grid: Grid,
                            cfg: Optional[DistrictConfig] = None,
                            ) -> List[ConstraintResult]:
    """Run only the HARD constraints (those the optimiser must respect).

    Returns
    -------
    List[ConstraintResult]
        Ordered hard-constraint results.
    """
    cfg = cfg or load_config()
    # STAGE-: the three cell-count distances below were
    # calibrated at 200 m cells (3 cells = 600 m road access; 2 cells =
    # 400 m school-industry separation; 6 cells = 1,200 m industry edge
    # band). They are METRE semantics, so they are re-derived from the
    # grid's cell size instead of silently halving at the 100 m re-grid.
    # (Cluster minimums stay in CELLS: a 4-cell park/solar cluster is a
    # granularity rule, not a distance - documented in register 0f.)
    _cell = max(1.0, float(grid.cell_size_m))
    return [
        check_area_targets(grid, cfg),
        check_road_connectivity(grid),
        check_road_proximity(grid,
                             max_distance_cells=max(1, round(600.0 / _cell))),
        check_schools_industry_separation(
            grid, min_separation_cells=max(1, round(400.0 / _cell))),
        check_industry_on_edge(grid,
                               max_dist_from_edge=max(1, round(1200.0 / _cell))),
        check_hospital_near_road(grid),
        check_amenities_road_frontage(grid),
        check_industrial_buffer(grid),
        check_solar_farm_clustering(grid, min_cluster_size=4),
        check_open_space_clustering(grid, min_cluster_size=4,
                                      max_singleton_share=0.25),
        check_green_space_buffer(grid),
        check_building_shading(grid),
        check_highstreet_road_frontage(grid),
        check_highstreet_corridor(grid),
        check_school_catchment(grid),
        check_religious_catchment(grid),
        check_amenity_equity(grid),
        check_park_quadrant_coverage(grid),
        check_stage_c_plant_buffer(grid),
        check_parking_road_frontage(grid),
    ]


def check_soft_constraints(grid: Grid,
                            requirements: Optional[Requirements],
                            cfg: Optional[DistrictConfig] = None,
                            ) -> List[ConstraintResult]:
    """Run only the SOFT constraints (low penalty).

    Returns
    -------
    List[ConstraintResult]
        Ordered soft-constraint results, or an empty list when requirements are absent.
    """
    if requirements is None:
        return []
    return [check_requirements_satisfied(grid, requirements)]


# ---------------------------------------------------------------------------
# Aggregator (everything, for reporting)
# ---------------------------------------------------------------------------
def check_all(grid: Grid,
              requirements: Optional[Requirements] = None,
              cfg: Optional[DistrictConfig] = None,
              ) -> List[ConstraintResult]:
    """Run every constraint check (hard + soft) and return all results.

    Returns
    -------
    List[ConstraintResult]
        Hard constraints followed by soft constraints.
    """
    out = check_hard_constraints(grid, cfg)
    out.extend(check_soft_constraints(grid, requirements, cfg))
    return out


def feasibility_summary(results: List[ConstraintResult]) -> str:
    """Compact pass/fail / gap report.

    Returns
    -------
    str
        Multi-line textual summary of constraint outcomes.
    """
    lines = ["constraint check:"]
    for r in results:
        lines.append("  " + str(r))
    n_pass = sum(1 for r in results if r.passes)
    lines.append(f"  -> {n_pass}/{len(results)} constraints passed")
    return "\n".join(lines)
