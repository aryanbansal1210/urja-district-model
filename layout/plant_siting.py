"""Spatial siting of Stage C utility plants (biomass CHP, biogas, WTE).

: the dispatch already has plant
capacities (kw_e) but the MILP is single-bus -- there is no physical
location for biomass / biogas / WTE on the district grid. This module
adds a deterministic post-SA placement step that:

  * picks ONE cell each for biomass_chp, biogas, and wte;
  * prefers LIGHT_INDUSTRY or WAREHOUSE_COLD_STORAGE land-use (existing
    industrial / service-yard zones); falls back to PUBLIC_SERVICES if
    no industrial cell qualifies;
  * requires each chosen cell be ROAD-adjacent (4-neighbour);
  * requires each chosen cell be at least N cells away from any
    RESIDENTIAL_* or SCHOOL cell (Manhattan distance);
  * the three plants must not share a cell.

The placement is *not* an SA decision variable -- it is a deterministic
greedy assignment over the SA-final grid. This keeps Stage A's SA
problem unchanged and adds Stage C spatial information for the viewer
and downstream Stage D peer-to-peer flows.

Buffers default to:
  * residential buffer = 3 cells (600 m at 200 m grid);
  * school buffer     = 2 cells (400 m).

The exact buffer can be tuned in ``district_composition.yaml`` later;
for now the defaults are baked into the module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from core.grid import Cell, Grid
from core.land_use import LandUse


# ---------------------------------------------------------------------------
# Constants -- buffers in cells (Manhattan distance).
# ---------------------------------------------------------------------------
PLANT_KINDS: Tuple[str, ...] = ("biomass_chp", "biogas", "wte")

RESIDENTIAL_BUFFER_CELLS: int = 3       # 600 m at 200 m grid
SCHOOL_BUFFER_CELLS: int = 2            # 400 m

# Cells preferred as plant sites, in priority order.
PREFERRED_HOSTS_BY_KIND: Dict[str, Tuple[LandUse, ...]] = {
    "biomass_chp": (LandUse.LIGHT_INDUSTRY, LandUse.WAREHOUSE,
                     LandUse.PUBLIC_SERVICES),
    "biogas":      (LandUse.PUBLIC_SERVICES, LandUse.LIGHT_INDUSTRY,
                     LandUse.WAREHOUSE),  # near water-treatment / waste
    "wte":         (LandUse.LIGHT_INDUSTRY, LandUse.WAREHOUSE,
                     LandUse.PUBLIC_SERVICES),
}

# Residential 4-cluster recognised as "sensitive receptor" for buffers.
SENSITIVE_LAND_USES: Tuple[LandUse, ...] = (
    LandUse.RESIDENTIAL_LOW,
    LandUse.RESIDENTIAL_MID,
    LandUse.RESIDENTIAL_HIGH,
    LandUse.SCHOOL,
    LandUse.HEALTHCARE,
)


@dataclass(frozen=True)
class PlantPlacement:
    """Where a Stage C utility plant is sited on the district grid."""

    kind: str           # "biomass_chp" / "biogas" / "wte"
    row: int
    col: int
    host_land_use: str  # land_use of the host cell (str, value of LandUse)
    min_residential_distance_cells: int
    min_school_distance_cells: int
    reason: str

    def cell_id(self) -> str:
        return f"{self.row:02d}_{self.col:02d}"


# ---------------------------------------------------------------------------
# Distance helpers.
# ---------------------------------------------------------------------------
def _manhattan(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _is_road_adjacent(grid: Grid, row: int, col: int) -> bool:
    return any(nb.land_use == LandUse.ROAD
               for nb in grid.neighbours_4(row, col))


def _min_distance_to(grid: Grid, row: int, col: int,
                      land_uses: Iterable[LandUse]) -> int:
    """Manhattan distance (in cells) from (row, col) to nearest cell in
    ``land_uses``. Returns ``grid.n_rows + grid.n_cols`` if no such cell exists.
    """
    target_uses = set(land_uses)
    best = grid.n_rows + grid.n_cols
    for c in grid.all_cells():
        if c.land_use in target_uses:
            d = _manhattan((row, col), (c.row, c.col))
            if d < best:
                best = d
    return best


# ---------------------------------------------------------------------------
# Plant siting core.
# ---------------------------------------------------------------------------
def _candidate_cells_for_kind(grid: Grid, kind: str,
                                 already_placed: Iterable[Tuple[int, int]],
                                 ) -> List[Cell]:
    """Filter cells eligible as a plant site for ``kind``.

    A candidate must:
      * have land_use in the kind's PREFERRED_HOSTS_BY_KIND list;
      * be ROAD-adjacent (4-neighbour);
      * not already host another placed plant.
    """
    placed_set = set(already_placed)
    hosts = set(PREFERRED_HOSTS_BY_KIND.get(kind, ()))
    out: List[Cell] = []
    for c in grid.all_cells():
        if (c.row, c.col) in placed_set:
            continue
        if c.land_use not in hosts:
            continue
        if not _is_road_adjacent(grid, c.row, c.col):
            continue
        out.append(c)
    return out


def _distance_to_district_edge(grid: Grid, row: int, col: int) -> int:
    """Minimum Manhattan distance from (row, col) to any grid edge.

    Proxy for truck-access cost: cells nearer the edge are cheaper to
    reach for agri-waste collection (biomass) without crossing the
    residential interior.
    """
    return min(row, col, grid.n_rows - 1 - row, grid.n_cols - 1 - col)


def _min_distance_to_other_same_kind_host(grid: Grid, row: int, col: int,
                                            land_use: LandUse) -> int:
    """Manhattan distance to the nearest OTHER cell of ``land_use``.

    Self-exclusive (the (row, col) cell itself is skipped). Returns
    ``grid.n_rows + grid.n_cols`` if no other such cell exists -- treated
    as "no clustering bonus available" by the caller.
    """
    best = grid.n_rows + grid.n_cols
    for c in grid.all_cells():
        if c.land_use != land_use:
            continue
        if c.row == row and c.col == col:
            continue
        d = _manhattan((row, col), (c.row, c.col))
        if d < best:
            best = d
    return best


def _score_candidate(grid: Grid, cell: Cell,
                       kind: str = "biomass_chp",
                       ) -> Tuple[float, int, int]:
    """Return a tuple suitable for ``max`` -- higher first values are
    preferred.

    ** (A15 logistics-aware siting)**: the scoring now varies by
    plant kind to reflect real-world feedstock / receptor logistics, not
    just "max sum of buffer distances" across the board.

    * ``biomass_chp`` -- biomass feedstock (paddy straw / agri waste)
      arrives by truck from outside the district. Prefer cells **close
      to the grid edge** (truck access) and **clustered with other
      LIGHT_INDUSTRY** cells (shared logistics yard). Residential /
      school distance is the secondary tiebreaker so the placement
      still favours setback within the eligible set.
    * ``biogas`` -- digester feedstock is sewage / wet organics from
      PUBLIC_SERVICES (waste / water-services). Prefer cells **close
      to PUBLIC_SERVICES** so the digester can be co-located with the
      treatment plant (avoiding sewage-collection truck movements).
    * ``wte`` -- waste-to-energy stack produces NOx + particulates and
      requires the largest setback from sensitive receptors. Pure
      max-distance objective: sum of distances to RESIDENTIAL + SCHOOL
      + HEALTHCARE.

    Items in the returned tuple are (composite_score, d_residential,
    d_school) so the secondary fields keep the legacy reporting contract
    (used by `PlantPlacement.min_residential_distance_cells` and
    `min_school_distance_cells`).
    """
    d_res = _min_distance_to(grid, cell.row, cell.col,
                              (LandUse.RESIDENTIAL_LOW,
                               LandUse.RESIDENTIAL_MID,
                               LandUse.RESIDENTIAL_HIGH))
    d_school = _min_distance_to(grid, cell.row, cell.col, (LandUse.SCHOOL,))
    d_health = _min_distance_to(grid, cell.row, cell.col,
                                  (LandUse.HEALTHCARE,))

    if kind == "biomass_chp":
        d_edge = _distance_to_district_edge(grid, cell.row, cell.col)
        d_cluster = _min_distance_to_other_same_kind_host(
            grid, cell.row, cell.col, LandUse.LIGHT_INDUSTRY,
        )
        # Closer to edge + closer to clustered industry both increase score.
        # Residential/school distances are secondary tie-breakers (scaled
        # so a single residential cell of buffer doesn't dominate the
        # logistics signal).
        score = (
            -2.0 * d_edge
            - 1.0 * d_cluster
            + 0.25 * (d_res + d_school + d_health)
        )
    elif kind == "biogas":
        d_pubsvc = _min_distance_to(
            grid, cell.row, cell.col, (LandUse.PUBLIC_SERVICES,),
        )
        # Co-locate with waste / water-services; receptor distance is
        # only the tiebreaker.
        score = (
            -3.0 * d_pubsvc
            + 0.25 * (d_res + d_school + d_health)
        )
    elif kind == "wte":
        # WTE is the most-polluting plant: pure max-receptor-distance.
        score = float(d_res + d_school + d_health)
    else:
        # Unknown kind -- fall back to the legacy sum-of-buffers.
        score = float(d_res + d_school + d_health)

    return score, d_res, d_school


def find_plant_site(grid: Grid, kind: str,
                     residential_buffer_cells: int = RESIDENTIAL_BUFFER_CELLS,
                     school_buffer_cells: int = SCHOOL_BUFFER_CELLS,
                     already_placed: Optional[Iterable[Tuple[int, int]]] = None,
                     ) -> Optional[PlantPlacement]:
    """Pick the best cell for a plant of the given kind.

    Strategy: among candidates that meet both buffers, pick the one with
    the maximum (residential + school + healthcare) summed Manhattan
    distance. If no candidate meets the buffers, relax the constraints
    and pick the candidate with the maximum minimum distance (best of
    worst -- documented as a buffer violation in the placement reason).

    Returns
    -------
    Optional[PlantPlacement]
        ``None`` if no candidate cells exist at all (no industrial or
        public-services cell on the grid).
    """
    placed = list(already_placed) if already_placed else []
    candidates = _candidate_cells_for_kind(grid, kind, placed)
    if not candidates:
        return None

    # First pass: only those meeting both buffers.
    compliant: List[Tuple[Cell, Tuple[float, int, int]]] = []
    for c in candidates:
        d_res = _min_distance_to(grid, c.row, c.col,
                                  (LandUse.RESIDENTIAL_LOW,
                                   LandUse.RESIDENTIAL_MID,
                                   LandUse.RESIDENTIAL_HIGH))
        d_school = _min_distance_to(grid, c.row, c.col, (LandUse.SCHOOL,))
        if d_res >= residential_buffer_cells and d_school >= school_buffer_cells:
            compliant.append((c, _score_candidate(grid, c, kind)))

    if compliant:
        best, score = max(compliant, key=lambda t: t[1])
        return PlantPlacement(
            kind=kind, row=best.row, col=best.col,
            host_land_use=best.land_use.value,
            min_residential_distance_cells=score[1],
            min_school_distance_cells=score[2],
            reason=f"compliant ({best.land_use.value}, road-adjacent)",
        )

    # Fallback: relax buffers, pick best-of-worst.
    scored = [(c, _score_candidate(grid, c, kind)) for c in candidates]
    best, score = max(scored, key=lambda t: t[1])
    return PlantPlacement(
        kind=kind, row=best.row, col=best.col,
        host_land_use=best.land_use.value,
        min_residential_distance_cells=score[1],
        min_school_distance_cells=score[2],
        reason=(f"buffer-violated fallback ({best.land_use.value}, "
                f"residential {score[1]} cells, school {score[2]} cells; "
                f"required {residential_buffer_cells} / {school_buffer_cells})"),
    )


# ---------------------------------------------------------------------------
#: deterministic per-cell axis alignment for RETAIL_HIGHSTREET.
# The SA's soft `building_axis_coherence_score` (weight 0.04) is not strong
# enough to fully align a 10-cell chain: regenerated layouts still show
# mixed axes within a single chain (0 / 90 / 180 / 270 jumbled). Fix: post-
# SA, set each high-street cell's `building_axis_deg` to FACE the ROAD it
# fronts, preferring the road perpendicular to the chain's primary axis so
# the long facade lies along the chain and fronts the road.
# ---------------------------------------------------------------------------
def align_highstreet_axes(grid: Grid) -> int:
    """Deterministically set ``building_axis_deg`` for RETAIL_HIGHSTREET cells.

    Each high-street cell's "facing" is set to the cardinal direction of
    its adjacent ROAD. If the chain runs along a row, prefer the ROAD on
    the N or S side of the cell (so the long facade lies E-W along the
    chain and fronts the road perpendicular to it). Same for vertical
    chains. Bent / branched chains fall back to "any ROAD neighbour".

    Returns
    -------
    int
        Number of cells whose axis was set.
    """
    hs_cells = [c for c in grid.all_cells()
                if c.land_use == LandUse.RETAIL_HIGHSTREET]
    if not hs_cells:
        return 0
    hs_set = {(c.row, c.col) for c in hs_cells}
    visited: set = set()
    aligned = 0
    for start in hs_cells:
        if (start.row, start.col) in visited:
            continue
        # 4-connected BFS to find the chain component.
        component: List[Tuple[int, int]] = []
        frontier = [(start.row, start.col)]
        while frontier:
            r, c = frontier.pop()
            if (r, c) in visited:
                continue
            visited.add((r, c))
            component.append((r, c))
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nb = (r + dr, c + dc)
                if nb in hs_set and nb not in visited:
                    frontier.append(nb)
        rows = {r for r, _ in component}
        cols = {c for _, c in component}
        chain_horizontal = len(rows) == 1
        chain_vertical = len(cols) == 1

        # Map: (dr, dc) -> facing axis in degrees ("face this direction").
        DIR_TO_AXIS = {
            (-1, 0): 0.0,    # N neighbour -> face N
            (0, 1):  90.0,   # E neighbour -> face E
            (1, 0):  180.0,  # S neighbour -> face S
            (0, -1): 270.0,  # W neighbour -> face W
        }

        for r, c in component:
            cell = grid.at(r, c)
            road_dirs: List[Tuple[Tuple[int, int], float]] = []
            for (dr, dc), axis in DIR_TO_AXIS.items():
                nr, nc = r + dr, c + dc
                if 0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols:
                    if grid.at(nr, nc).land_use == LandUse.ROAD:
                        road_dirs.append(((dr, dc), axis))
            if not road_dirs:
                continue   # constraint violation; leave the SA-chosen axis

            chosen: float
            if chain_horizontal:
                # Prefer N or S road (perpendicular to E-W chain).
                perp = [(d, a) for d, a in road_dirs if d[0] != 0]
                chosen = perp[0][1] if perp else road_dirs[0][1]
            elif chain_vertical:
                perp = [(d, a) for d, a in road_dirs if d[1] != 0]
                chosen = perp[0][1] if perp else road_dirs[0][1]
            else:
                chosen = road_dirs[0][1]   # bent chain
            cell.building_axis_deg = chosen
            aligned += 1
    return aligned


# ---------------------------------------------------------------------------
#: the SA picks `building_axis_deg` per cell using only
# wind alignment + neighbour coherence + PV/BIPV scoring -- it does NOT
# know that a hospital / school / shopping_centre / etc. should "face the
# road it accesses". Result: arrows sometimes point sideways (away from
# the road) in the viewer. This deterministic post-SA step generalises
# `align_highstreet_axes` to ALL built categories with road access: each
# cell's `building_axis_deg` is overridden to face the nearest 4-neighbour
# ROAD, preserving the soft-metric chosen value only when no road is
# adjacent.
# ---------------------------------------------------------------------------
ROAD_FACING_CATEGORIES = frozenset({
    LandUse.SCHOOL,
    LandUse.HEALTHCARE,
    LandUse.SHOPPING_CENTRE,
    LandUse.RETAIL_HIGHSTREET,    # already handled by align_highstreet_axes
    LandUse.RESTAURANT_FOOD,
    LandUse.HOTEL_GUESTHOUSE,
    LandUse.PUBLIC_SERVICES,
    LandUse.OFFICE,
    LandUse.RELIGIOUS,
    LandUse.RESIDENTIAL_LOW,
    LandUse.RESIDENTIAL_MID,
    LandUse.RESIDENTIAL_HIGH,
})

# Industrial categories: front door faces road, but the long facade should
# typically lie along the road. Same rule applies.
ROAD_FACING_CATEGORIES = ROAD_FACING_CATEGORIES | frozenset({
    LandUse.LIGHT_INDUSTRY,
    LandUse.WAREHOUSE,
})


def align_road_facing_axes(grid: Grid) -> int:
    """Set ``building_axis_deg`` for every built cell to face its nearest ROAD.

    For cells with multiple ROAD 4-neighbours, prefer the road on the same
    cardinal as the cell's SA-chosen axis (so the SA's wind / coherence
    decision is respected when it's road-consistent). For cells with no
    ROAD 4-neighbour, leave the SA-chosen axis intact.

    Returns
    -------
    int
        Number of cells overridden.
    """
    DIR_TO_AXIS = {
        (-1, 0): 0.0,    # N neighbour -> face N
        (0, 1):  90.0,   # E neighbour -> face E
        (1, 0):  180.0,  # S neighbour -> face S
        (0, -1): 270.0,  # W neighbour -> face W
    }
    aligned = 0
    for c in grid.all_cells():
        if c.land_use not in ROAD_FACING_CATEGORIES:
            continue
        if not c.has_building:
            continue
        road_options: List[float] = []
        for (dr, dc), axis in DIR_TO_AXIS.items():
            nr, nc = c.row + dr, c.col + dc
            if 0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols:
                if grid.at(nr, nc).land_use == LandUse.ROAD:
                    road_options.append(axis)
        if not road_options:
            continue
        # Honour the SA's chosen axis if it points at a road; else pick first.
        current = float(c.building_axis_deg)
        if current in road_options:
            chosen = current
        else:
            chosen = road_options[0]
        if abs(chosen - current) > 1e-6:
            c.building_axis_deg = chosen
            aligned += 1
    return aligned


def place_stage_c_plants(grid: Grid) -> Dict[str, PlantPlacement]:
    """Site all three Stage C plants on the grid in priority order
    (biomass_chp, biogas, wte). Mutates ``grid.plant_placements`` and
    returns the populated dict for convenience.
    """
    placed: Dict[str, PlantPlacement] = {}
    already_taken: List[Tuple[int, int]] = []
    for kind in PLANT_KINDS:
        place = find_plant_site(grid, kind, already_placed=already_taken)
        if place is not None:
            placed[kind] = place
            already_taken.append((place.row, place.col))
    grid.plant_placements = placed
    return placed
