"""Simulated annealing layout optimiser (Path A — smarter moves).

This is the heart of the layout half of the project. It searches the space
of layouts by repeatedly mutating the grid (swap two cells, OR change a
single cell, OR a targeted swap aimed at a violated constraint) and
accepting / rejecting via the Metropolis criterion.

Path A improvements vs v1:
  * Three move types instead of one.
  * Cell-change move is biased toward UNDER-SUPPLIED land-uses (i.e. those
    where the current grid has fewer cells than the demographic requirements
    demand). This is what lets the optimiser shift land-use COUNTS, not just
    swap positions of existing types.
  * Targeted-swap move addresses constraint violations directly.
  * Cooling schedule slowed slightly; iteration count bumped.
  * Move framework now uses undo-callable returns so any mutation type is
    composable with the same accept/reject loop.

Cost function unchanged:
    cost = -weighted_metric_score + penalty * sum(constraint_gaps)
Lower cost = better.

Tuning knobs all live in `config/district_composition.yaml`.
"""

from __future__ import annotations

import math
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from core.building import building_from_cell
from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid, HeightTier
from core.land_use import LandUse, category_for
from core.requirements import Requirements

from .constraints import check_hard_constraints, check_soft_constraints
from .locked_zones import is_road_corridor_cell
from .metrics import DEFAULT_WEIGHTS, score_layout, weighted_score


# ---------------------------------------------------------------------------
# History container
# ---------------------------------------------------------------------------
@dataclass
class AnnealHistory:
    """One row per iteration of the SA loop."""

    iteration: List[int] = field(default_factory=list)
    temperature: List[float] = field(default_factory=list)
    current_cost: List[float] = field(default_factory=list)
    best_cost: List[float] = field(default_factory=list)
    accepted: List[bool] = field(default_factory=list)
    move_type: List[str] = field(default_factory=list)

    def acceptance_rate(self) -> float:
        """Return the overall move acceptance rate.

        Returns
        -------
        float
            Fraction of proposed moves accepted so far.
        """
        if not self.accepted:
            return 0.0
        return sum(self.accepted) / len(self.accepted)

    def acceptance_by_move(self) -> Dict[str, float]:
        """Return acceptance rates grouped by move type.

        Returns
        -------
        Dict[str, float]
            Acceptance fraction keyed by move type label.
        """
        out: Dict[str, List[bool]] = {}
        for mt, acc in zip(self.move_type, self.accepted):
            out.setdefault(mt, []).append(acc)
        return {k: sum(v) / len(v) for k, v in out.items() if v}


# ---------------------------------------------------------------------------
# Land-use defaults helper
# ---------------------------------------------------------------------------
def _apply_land_use_defaults(cell: Cell, cfg: DistrictConfig,
                              rng: random.Random,
                              n_rows: int = 25) -> None:
    """Set height / albedo / vegetation defaults for a cell after its
    land-use changed. Mirrors `_set_default_height` and
    `_set_default_albedo_and_vegetation` from the generator module.

    STAGE-: tiers are DETERMINISTIC (mirrors the generator).
    low/mid residential anneal at MEDIUM (net FAR 2.0, ratified A2 base);
    the plotted colony (RESIDENTIAL_HIGH) and all non-residential cells
    take the category's fixed typical height (colony = 12 m G+3, net FAR
    1.2). The Bertaud TALL/SHORT spine gradient is applied POST-anneal,
    floor-neutrally, by ``layout.spine_gradient.apply_spine_gradient`` -
    a random tier here would make the floor stock stochastic and break
    the FX-3 household reconciliation. ``rng``/``n_rows`` are kept for
    signature compatibility (no randomness remains).
    """
    cat = category_for(cell.land_use)
    if cat is None:
        cell.height_m = 0.0
        cell.height_tier = None
    else:
        cell.height_tier = HeightTier.MEDIUM
        if (cell.land_use.is_residential
                and cell.land_use != LandUse.RESIDENTIAL_HIGH):
            cell.height_m = cfg.height_for(HeightTier.MEDIUM.value)
        else:
            cell.height_m = cat.typical_height_m

    # albedo / vegetation defaults per land-use (must mirror
    # `_set_default_albedo_and_vegetation` in layout/generator.py)
    if cell.land_use == LandUse.OPEN_SPACE:
        cell.albedo, cell.vegetation_fraction = 0.25, 0.85
    elif cell.land_use == LandUse.BLUE_SPACE:
        cell.albedo, cell.vegetation_fraction = 0.10, 1.00
    elif cell.land_use == LandUse.SOLAR_FARM:
        cell.albedo, cell.vegetation_fraction = 0.30, 0.10
    elif cell.land_use == LandUse.ROAD:
        cell.albedo, cell.vegetation_fraction = 0.18, 0.10
    elif cell.land_use == LandUse.PARKING_LOT:
        cell.albedo, cell.vegetation_fraction = 0.18, 0.05   # asphalt surface lot
    elif cell.land_use.is_residential:
        cell.albedo, cell.vegetation_fraction = 0.30, 0.20
    elif cell.land_use in (LandUse.SHOPPING_CENTRE, LandUse.OFFICE,
                            LandUse.WAREHOUSE, LandUse.LIGHT_INDUSTRY,
                            LandUse.RETAIL_HIGHSTREET):
        cell.albedo, cell.vegetation_fraction = 0.30, 0.10
    elif cell.land_use == LandUse.RELIGIOUS:
        cell.albedo, cell.vegetation_fraction = 0.30, 0.30
    else:
        cell.albedo, cell.vegetation_fraction = 0.25, 0.15


# ---------------------------------------------------------------------------
# Move primitives
# Each move mutates `grid` in place and returns (move_type_label, undo_fn).
# ---------------------------------------------------------------------------
def _swap_cells(grid: Grid, a: Tuple[int, int], b: Tuple[int, int]) -> None:
    c1, c2 = grid.at(*a), grid.at(*b)
    c1.land_use, c2.land_use = c2.land_use, c1.land_use
    c1.height_m, c2.height_m = c2.height_m, c1.height_m
    c1.height_tier, c2.height_tier = c2.height_tier, c1.height_tier
    c1.albedo, c2.albedo = c2.albedo, c1.albedo
    c1.vegetation_fraction, c2.vegetation_fraction = (
        c2.vegetation_fraction, c1.vegetation_fraction,
    )


def _capture_cell(cell: Cell) -> tuple:
    return (cell.land_use, cell.height_m, cell.height_tier,
            cell.albedo, cell.vegetation_fraction, cell.building_axis_deg)


def _restore_cell(cell: Cell, snap: tuple) -> None:
    (cell.land_use, cell.height_m, cell.height_tier,
     cell.albedo, cell.vegetation_fraction, cell.building_axis_deg) = snap


# ---------------------------------------------------------------------------
# Move generators
# ---------------------------------------------------------------------------
def _random_swap_move(grid: Grid,
                       rng: random.Random) -> Tuple[str, Callable[[], None]]:
    """Swap attributes of two random cells. Self-undo.

    Skip pairs where exactly one side is ROAD: such swaps relocate a road
    cell, often into a position with no road neighbours, which fragments
    the road network. ROAD-ROAD swaps are allowed (they're a no-op for the
    network) and non-ROAD-non-ROAD swaps are allowed.
    """
    for _ in range(40):
        r1 = rng.randrange(grid.n_rows)
        c1 = rng.randrange(grid.n_cols)
        r2 = rng.randrange(grid.n_rows)
        c2 = rng.randrange(grid.n_cols)
        if (r1, c1) == (r2, c2):
            continue
        # never touch locked cells (arterial roads + solar zone).
        if grid.at(r1, c1).locked or grid.at(r2, c2).locked:
            continue
        a_is_road = grid.at(r1, c1).land_use == LandUse.ROAD
        b_is_road = grid.at(r2, c2).land_use == LandUse.ROAD
        if a_is_road != b_is_road:
            continue  # one-sided road swap would relocate a road cell
        a, b = (r1, c1), (r2, c2)
        _swap_cells(grid, a, b)
        return "random_swap", lambda: _swap_cells(grid, a, b)
    # extremely unlikely fallback: accept any non-self, non-locked pair
    while True:
        r1 = rng.randrange(grid.n_rows)
        c1 = rng.randrange(grid.n_cols)
        r2 = rng.randrange(grid.n_rows)
        c2 = rng.randrange(grid.n_cols)
        if (r1, c1) == (r2, c2):
            continue
        if grid.at(r1, c1).locked or grid.at(r2, c2).locked:
            continue
        break
    a, b = (r1, c1), (r2, c2)
    _swap_cells(grid, a, b)
    return "random_swap", lambda: _swap_cells(grid, a, b)


def _cell_change_move(grid: Grid,
                       rng: random.Random,
                       requirements: Requirements,
                       cfg: DistrictConfig,
                       ) -> Tuple[str, Callable[[], None]]:
    """Pick one random cell, set its land-use to an under-supplied one.

    "Under-supplied" = required-cells > current-cells. The likelihood of
    picking a given target land-use is proportional to its shortfall.
    Falls back to a uniform random choice if nothing is short.
    """
    counts = Counter(c.land_use for c in grid.all_cells())
    shortfalls: List[Tuple[LandUse, int]] = []
    for lu, needed in requirements.required_cells_by_landuse.items():
        gap = needed - counts.get(lu, 0)
        if gap > 0:
            shortfalls.append((lu, gap))

    if shortfalls:
        target = rng.choices(
            [lu for lu, _ in shortfalls],
            weights=[g for _, g in shortfalls], k=1,
        )[0]
    else:
        target = rng.choice(list(LandUse))

    # pick a cell that is NOT already this target AND that we don't want
    # to preserve. ROAD cells are protected unless ROAD itself is in
    # shortfall (the SA may need to add roads back) OR the candidate ROAD
    # cell has 2+ ROAD neighbours (so removing it doesn't disconnect the
    # network).
    road_in_shortfall = any(lu == LandUse.ROAD for lu, _ in shortfalls)

    def _cell_is_eligible(c: Cell) -> bool:
        if c.locked:  # arterial roads + solar zone are immutable
            return False
        if c.land_use == target:
            return False
        if c.land_use != LandUse.ROAD:
            return True
        if road_in_shortfall:
            return True
        road_nbs = sum(1 for nb in grid.neighbours_4(c.row, c.col)
                       if nb.land_use == LandUse.ROAD)
        # only convert "thick" road cells (3+ road neighbours means the
        # ROAD cell sits inside a road junction or wide corridor) so
        # removing it is unlikely to fragment the network.
        return road_nbs >= 3

    cell = None
    for _ in range(40):
        r = rng.randrange(grid.n_rows)
        c = rng.randrange(grid.n_cols)
        candidate = grid.at(r, c)
        if _cell_is_eligible(candidate):
            cell = candidate
            break
    if cell is None:
        # rare fallback — accept any non-target, non-locked cell
        for _ in range(20):
            r = rng.randrange(grid.n_rows)
            c = rng.randrange(grid.n_cols)
            candidate = grid.at(r, c)
            if candidate.land_use != target and not candidate.locked:
                cell = candidate
                break
        if cell is None:
            # nothing found; no-op move (keeps locked cells safe)
            return "no_op", lambda: None

    snap = _capture_cell(cell)
    cell.land_use = target
    _apply_land_use_defaults(cell, cfg, rng, n_rows=grid.n_rows)
    return "cell_change", lambda: _restore_cell(cell, snap)


def _targeted_swap_move(grid: Grid,
                         rng: random.Random,
                         requirements: Requirements,
                         cfg: DistrictConfig,
                         ) -> Tuple[str, Callable[[], None]]:
    """Swap a cell that is over-supplied with one of an under-supplied type.

    Picks a random "donor" cell whose land-use is over-represented (or
    OPEN_SPACE / RESIDENTIAL_MID acts as a sink) and changes it to an
    under-supplied land-use. Sharper than `_cell_change_move` because the
    donor is biased away from already-rare types.
    """
    counts = Counter(c.land_use for c in grid.all_cells())
    short: List[Tuple[LandUse, int]] = []
    over: List[Tuple[LandUse, int]] = []
    for lu, needed in requirements.required_cells_by_landuse.items():
        have = counts.get(lu, 0)
        if have < needed:
            short.append((lu, needed - have))
        elif have > needed and lu in (
            LandUse.OPEN_SPACE, LandUse.RESIDENTIAL_MID,
            LandUse.RESIDENTIAL_HIGH,
        ):
            # only allow donors from "abundant" non-network types so we
            # don't degrade rare amenities OR the road network. ROAD was
            # in this list pre-Stage A but was the dominant cause of the
            # SA fragmenting the road grid in pursuit of under-supplied
            # new land-uses (RETAIL_HIGHSTREET / BLUE_SPACE / RELIGIOUS).
            over.append((lu, have - needed))

    if not short:
        # nothing short; degrade gracefully to a swap
        return _random_swap_move(grid, rng)
    if not over:
        # nothing surplus to convert; do a cell change instead
        return _cell_change_move(grid, rng, requirements, cfg)

    target = rng.choices([lu for lu, _ in short],
                          weights=[g for _, g in short], k=1)[0]
    donor_use = rng.choices([lu for lu, _ in over],
                             weights=[g for _, g in over], k=1)[0]

    # find a cell of donor_use type (never a locked cell)
    donor_cells = [c for c in grid.all_cells()
                   if c.land_use == donor_use and not c.locked]
    if not donor_cells:
        return _random_swap_move(grid, rng)
    cell = rng.choice(donor_cells)
    snap = _capture_cell(cell)
    cell.land_use = target
    _apply_land_use_defaults(cell, cfg, rng, n_rows=grid.n_rows)
    return "targeted_swap", lambda: _restore_cell(cell, snap)


# ---------------------------------------------------------------------------
# Cluster-aware move: when introducing a new SOLAR_FARM or OPEN_SPACE cell,
# prefer a position adjacent to existing cells of that type. This dramatically
# reduces fragmentation that the v1 cell_change move was creating.
# ---------------------------------------------------------------------------
CLUSTER_ATTRACTED_LANDUSES = (
    LandUse.SOLAR_FARM,
    LandUse.OPEN_SPACE,
    LandUse.LIGHT_INDUSTRY,
    LandUse.WAREHOUSE,
)


def _cluster_grow_move(grid: Grid,
                        rng: random.Random,
                        requirements: Requirements,
                        cfg: DistrictConfig,
                        ) -> Tuple[str, Callable[[], None]]:
    """Pick an under-supplied land-use that benefits from clustering, find an
    existing cluster cell, then convert one of its 8-neighbours to that type.

    Falls back to `_cell_change_move` if there is no existing seed of any
    cluster-loving land-use.
    """
    counts = Counter(c.land_use for c in grid.all_cells())
    short: List[Tuple[LandUse, int]] = []
    for lu in CLUSTER_ATTRACTED_LANDUSES:
        needed = requirements.required_cells_by_landuse.get(lu, 0)
        gap = needed - counts.get(lu, 0)
        if gap > 0 and counts.get(lu, 0) > 0:  # need an existing seed
            short.append((lu, gap))

    if not short:
        return _cell_change_move(grid, rng, requirements, cfg)

    target = rng.choices([lu for lu, _ in short],
                          weights=[g for _, g in short], k=1)[0]
    seed_cells = [c for c in grid.all_cells() if c.land_use == target]
    if not seed_cells:
        return _cell_change_move(grid, rng, requirements, cfg)

    # find a non-target neighbour of a seed; donor preferably from "abundant"
    rng.shuffle(seed_cells)
    candidates: List[Cell] = []
    abundant_donors = (LandUse.RESIDENTIAL_MID, LandUse.RESIDENTIAL_HIGH,
                        LandUse.OPEN_SPACE)
    for seed in seed_cells:
        for nb in grid.neighbours_8(seed.row, seed.col):
            if nb.land_use == target or nb.locked:
                continue
            # prefer abundant donors (don't destroy rare amenities)
            if nb.land_use in abundant_donors:
                candidates.append(nb)
        if candidates:
            break

    if not candidates:
        return _cell_change_move(grid, rng, requirements, cfg)

    cell = rng.choice(candidates)
    snap = _capture_cell(cell)
    cell.land_use = target
    _apply_land_use_defaults(cell, cfg, rng, n_rows=grid.n_rows)
    return "cluster_grow", lambda: _restore_cell(cell, snap)


# (Priority 2): rotate one built cell's long-facade axis to a
# different option in {0, 45, 90, 135} degrees. Pure local move -- changes
# only the axis, no land-use or height side-effect. SA fitness sees the
# new axis through `building_wind_alignment_score` + the energy-network
# facade-orientation cooling multiplier + BIPV per-facade multiplier.
# update: switched from diagonal-inclusive {0, 45, 90, 135} to
# cardinal-only {0, 90, 180, 270} per. Encodes
# the building's "facing" direction (where the principal facade points).
# Thermal effects depend on the LONG axis = facing mod 180, so 0/180 are
# thermally equivalent (long axis E-W) and 90/270 are equivalent (long
# axis N-S). The two pairs DO differ on which long facade is the "front"
# vs "back", which matters only for visualisation.
_AXIS_OPTIONS: Tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)


#: bias amenity placement toward
# under-served residential clusters. Pairs with the new
# `population_catchment_coverage_score` SOFT metric in layout/metrics.py.
# Strategy: pick one amenity category at random (healthcare / school /
# public_services / shopping_centre / religious), find the amenity cell
# of that category that serves the fewest households (= least useful in
# the current layout), find the residential cell with the WORST coverage
# of that category (= most under-served), and propose moving the amenity
# closer to that resident by relocating it onto an "abundant" donor cell
# in the under-served resident's 8-neighbourhood. Falls back to a normal
# cell_change move when no useful relocation exists. Deterministic
# tie-break by (row, col).
_CATCHMENT_MOVE_KINDS: Tuple[LandUse, ...] = (
    LandUse.HEALTHCARE, LandUse.SCHOOL, LandUse.PUBLIC_SERVICES,
    LandUse.SHOPPING_CENTRE, LandUse.RELIGIOUS,
)
# Abundant land-uses that can donate their cell to host the relocated
# amenity. Matches the donor list in `_targeted_swap_move` (ROAD
# excluded so the road grid isn't fragmented).
_CATCHMENT_DONOR_LANDUSES: Tuple[LandUse, ...] = (
    LandUse.OPEN_SPACE, LandUse.RESIDENTIAL_MID, LandUse.RESIDENTIAL_HIGH,
)


def _amenity_catchment_swap(grid: Grid,
                              rng: random.Random,
                              requirements: Requirements,
                              cfg: DistrictConfig,
                              ) -> Tuple[str, Callable[[], None]]:
    """Move one amenity cell closer to an under-served resident.

    Algorithm:
      1. Pick a random amenity kind from `_CATCHMENT_MOVE_KINDS`.
      2. Bail out if the kind has 0 amenity cells or 0 residential
         households in the layout.
      3. Find the residential cell with the LARGEST Manhattan distance
         to its nearest amenity of that kind (= most under-served).
      4. Pick an abundant 8-neighbour of that resident (OPEN_SPACE /
         RESIDENTIAL_MID / RESIDENTIAL_HIGH) as the relocation target.
         Fall back to a normal cell_change move if no donor is adjacent.
      5. Find the EXISTING amenity cell of that kind that's farthest
         from any resident (= least useful) -- demote it back to
         OPEN_SPACE on the swap so the layout's amenity COUNT is
         preserved (otherwise we'd silently shrink the amenity supply).

    The two-step swap (relocate + demote) keeps the requirements
    bookkeeping balanced: amenity_count unchanged, OPEN_SPACE/MID/HIGH
    donor count -1, demoted amenity becomes +1 of OPEN_SPACE.
    """
    kind = rng.choice(_CATCHMENT_MOVE_KINDS)
    amenities = [c for c in grid.all_cells() if c.land_use == kind]
    if not amenities:
        return _cell_change_move(grid, rng, requirements, cfg)
    residents = [c for c in grid.all_cells()
                 if c.is_residential and (
                     building_from_cell(c, cfg) is not None
                     and building_from_cell(c, cfg).households > 0
                 )]
    if not residents:
        return _cell_change_move(grid, rng, requirements, cfg)

    # Step 3: most under-served resident for THIS kind. Tie-break by (row, col).
    def _resident_dist(r: Cell) -> Tuple[float, int, int]:
        d = min(Grid.manhattan_distance(r, a) for a in amenities)
        return (d, r.row, r.col)

    residents_sorted = sorted(residents, key=_resident_dist, reverse=True)
    worst_resident = residents_sorted[0]
    worst_resident_dist = min(
        Grid.manhattan_distance(worst_resident, a) for a in amenities
    )

    # Step 4: pick an abundant 8-neighbour donor that HAS road frontage.
    # coupled to the placement, so the fix does not recreate the
    # amenity-no-road audit issue". A relocated amenity must sit on a cell
    # with a ROAD 4-neighbour, otherwise we trade a catchment gain for a
    # HARD `amenities_road_frontage` violation. Without this guard the
    # re-anneal pushed the road-frontage gap 0.189 -> 0.324.
    def _has_road_frontage(c: Cell) -> bool:
        return any(nb.land_use == LandUse.ROAD
                   for nb in grid.neighbours_4(c.row, c.col))

    #: donor must have road frontage but must NOT sit in a
    # road corridor (flanked by roads on opposite sides) or be locked — that
    # is what put the temple/hospital across the road links.
    candidates = [
        nb for nb in grid.neighbours_8(worst_resident.row, worst_resident.col)
        if nb.land_use in _CATCHMENT_DONOR_LANDUSES
        and not nb.locked
        and _has_road_frontage(nb)
        and not is_road_corridor_cell(grid, nb.row, nb.col)
    ]
    if not candidates:
        return _cell_change_move(grid, rng, requirements, cfg)
    candidates.sort(key=lambda c: (c.row, c.col))  # determinism
    donor = candidates[0]

    # Step 5: pick the least-useful existing amenity cell of the kind.
    def _amenity_min_resident_dist(a: Cell) -> Tuple[float, int, int]:
        d = min(Grid.manhattan_distance(a, r) for r in residents)
        return (d, a.row, a.col)

    amenities_sorted = sorted(amenities, key=_amenity_min_resident_dist,
                              reverse=True)
    least_useful = amenities_sorted[0]
    least_useful_dist = min(
        Grid.manhattan_distance(least_useful, r) for r in residents
    )

    # Only swap if it would improve coverage strictly. If the donor cell
    # is FURTHER from the worst resident than the cell we're demoting,
    # bail (the SA's cost function would reject this anyway, but we save
    # an evaluation cycle).
    if Grid.manhattan_distance(donor, worst_resident) >= worst_resident_dist:
        return _cell_change_move(grid, rng, requirements, cfg)
    if least_useful_dist <= worst_resident_dist:
        return _cell_change_move(grid, rng, requirements, cfg)

    donor_snap = _capture_cell(donor)
    least_snap = _capture_cell(least_useful)

    donor.land_use = kind
    _apply_land_use_defaults(donor, cfg, rng, n_rows=grid.n_rows)
    least_useful.land_use = LandUse.OPEN_SPACE
    _apply_land_use_defaults(least_useful, cfg, rng, n_rows=grid.n_rows)

    def _undo() -> None:
        _restore_cell(donor, donor_snap)
        _restore_cell(least_useful, least_snap)

    return "catchment_swap", _undo


def _building_axis_move(grid: Grid,
                          rng: random.Random,
                          ) -> Tuple[str, Callable[[], None]]:
    """Rotate one built cell's building_axis_deg to a new option.

    Returns ``("no_op", noop)`` if there are no built cells (e.g. empty
    grid early in SA).
    """
    built = [c for c in grid.all_cells() if c.has_building and not c.locked]
    if not built:
        return "no_op", lambda: None
    cell = rng.choice(built)
    snap = _capture_cell(cell)
    current = float(cell.building_axis_deg)
    options = [a for a in _AXIS_OPTIONS if abs(a - current) > 1e-6]
    cell.building_axis_deg = rng.choice(options)
    return "axis_rotate", lambda: _restore_cell(cell, snap)


def _make_move(grid: Grid,
                rng: random.Random,
                requirements: Requirements,
                cfg: DistrictConfig,
                ) -> Tuple[str, Callable[[], None]]:
    """Pick a move type with weighted probability and apply it.

    Weights ( update -- catchment_swap added at 8 % so the new
    `population_catchment_coverage_score` metric can actually move
    amenity placement during SA without dominating the existing
    land-use shuffling moves):
      * 26 % cluster_grow  (extends existing solar/open/industry clusters)
      * 26 % cell_change   (random under-supplied conversion)
      * 20 % targeted_swap (donor-from-abundance, target=under-supplied)
      * 12 % random_swap   (fine-tuning + diversity)
      *  8 % axis_rotate   (rotate a built cell's building axis)
      *  8 % catchment_swap (NEW: relocate amenity to under-served resident)
    """
    roll = rng.random()
    if roll < 0.26:
        return _cluster_grow_move(grid, rng, requirements, cfg)
    if roll < 0.52:
        return _cell_change_move(grid, rng, requirements, cfg)
    if roll < 0.72:
        return _targeted_swap_move(grid, rng, requirements, cfg)
    if roll < 0.84:
        return _random_swap_move(grid, rng)
    if roll < 0.92:
        return _building_axis_move(grid, rng)
    return _amenity_catchment_swap(grid, rng, requirements, cfg)


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------
def total_cost(grid: Grid,
               requirements: Requirements,
               cfg: DistrictConfig,
               weights: Dict[str, float],
               hard_penalty: float,
               soft_penalty: float,
               ) -> float:
    """Cost the SA minimises.

        cost = -weighted_metric_score
             + hard_penalty * sum(hard_constraint_gaps)
             + soft_penalty * sum(soft_constraint_gaps)

    Hard constraints (area targets, road connectivity, road proximity,
    industrial buffer, road frontage, solar/open clustering, etc.) get a
    much heavier penalty than soft (requirements_satisfied), which means
    moves that worsen feasibility are almost always rejected.

    Returns
    -------
    float
        Scalar objective value; lower is better.
    """
    score = score_layout(grid, requirements, cfg)
    objective = -weighted_score(score, weights)

    hard = check_hard_constraints(grid, cfg)
    hard_gap = sum(c.gap for c in hard)

    soft = check_soft_constraints(grid, requirements, cfg)
    soft_gap = sum(c.gap for c in soft)

    return objective + hard_penalty * hard_gap + soft_penalty * soft_gap


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def anneal(initial_grid: Grid,
           requirements: Requirements,
           cfg: Optional[DistrictConfig] = None,
           weights: Optional[Dict[str, float]] = None,
           n_iterations: Optional[int] = None,
           initial_temperature: Optional[float] = None,
           final_temperature: Optional[float] = None,
           hard_penalty: Optional[float] = None,
           soft_penalty: Optional[float] = None,
           rng_seed: Optional[int] = None,
           log_every: Optional[int] = None,
           verbose: bool = True,
           on_snapshot=None,
           ) -> Tuple[Grid, AnnealHistory]:
    """Run simulated annealing on a layout (Path A + hard-constraint
    enforcement).

    Hard constraints get a much heavier penalty than soft ones, which means
    the optimiser preferentially avoids violations even at high temperature.
    Strict rejection is NOT used because the seed (Chandigarh) typically
    starts with a few hard-constraint failures, so we want gradient-based
    progress rather than locking the search at start.

    Returns
    -------
    Tuple[Grid, AnnealHistory]
        Best grid found and the iteration history.
    """
    cfg = cfg or load_config()
    weights = weights or DEFAULT_WEIGHTS
    opt = cfg.optimisation or {}
    n_iterations = int(n_iterations or opt.get("n_iterations", 2500))
    T0 = float(initial_temperature or opt.get("initial_temperature", 0.10))
    Tf = float(final_temperature or opt.get("final_temperature", 0.001))
    hard_penalty = float(
        hard_penalty or opt.get("hard_penalty", 25.0)
    )
    soft_penalty = float(
        soft_penalty or opt.get("soft_penalty", 2.0)
    )
    seed = int(rng_seed or opt.get("rng_seed", 42))
    log_every = int(log_every or opt.get("log_every", 200))

    rng = random.Random(seed)
    grid = initial_grid.copy()
    current_cost = total_cost(grid, requirements, cfg, weights,
                                hard_penalty, soft_penalty)
    best_grid = grid.copy()
    best_cost = current_cost

    if T0 <= 0 or Tf <= 0 or Tf >= T0:
        raise ValueError(f"bad temperature schedule T0={T0}, Tf={Tf}")
    decay = (Tf / T0) ** (1.0 / max(1, n_iterations - 1))

    hist = AnnealHistory()
    T = T0
    t_start = time.time()

    if verbose:
        print(f"  SA: {n_iterations} iter, T0={T0}, Tf={Tf}, "
              f"hard_penalty={hard_penalty}, soft_penalty={soft_penalty}, "
              f"seed={seed}")
        print(f"  initial cost {current_cost:+.4f}")

    # OPTIONAL PROGRESSION CAPTURE.
    # `on_snapshot(iteration, cost, grid)` is called before the first move and
    # after selected ones, so the figure can show the SAME run that produced
    # the frozen layout rather than a separate illustrative anneal. It is a
    # pure addition: when the callback is None - which is every production
    # path - nothing below this line executes and the search is byte-identical
    # to before. The callback must not mutate the grid; it is handed the live
    # object for cheap copying, not for editing.
    if on_snapshot is not None:
        on_snapshot(0, current_cost, grid)

    for i in range(n_iterations):
        move_type, undo = _make_move(grid, rng, requirements, cfg)
        new_cost = total_cost(grid, requirements, cfg, weights,
                                hard_penalty, soft_penalty)
        delta = new_cost - current_cost

        accept = (delta < 0) or (rng.random() < math.exp(-delta / max(T, 1e-12)))
        if accept:
            current_cost = new_cost
            if current_cost < best_cost:
                best_cost = current_cost
                best_grid = grid.copy()
        else:
            undo()

        hist.iteration.append(i)
        hist.temperature.append(T)
        hist.current_cost.append(current_cost)
        hist.best_cost.append(best_cost)
        hist.accepted.append(accept)
        hist.move_type.append(move_type)

        T *= decay

        if on_snapshot is not None:
            on_snapshot(i + 1, current_cost, grid)

        if verbose and ((i + 1) % log_every == 0 or i == n_iterations - 1):
            elapsed = time.time() - t_start
            ar = (sum(hist.accepted[-log_every:]) /
                  max(1, min(log_every, len(hist.accepted))))
            print(f"  iter {i + 1:>5}/{n_iterations}   T={T:.4f}   "
                  f"cur={current_cost:+.4f}   best={best_cost:+.4f}   "
                  f"accept={ar:.0%}   {elapsed:.1f}s")

    if verbose:
        print(f"  final cost {best_cost:+.4f}   "
              f"(improvement {-(best_cost - hist.current_cost[0]):+.4f})")
        ab = hist.acceptance_by_move()
        print(f"  acceptance by move: " +
              ", ".join(f"{k}={v:.0%}" for k, v in ab.items()))

    #: post-SA spatial siting of Stage C utility plants
    # (biomass CHP, biogas, WTE). Deterministic greedy placement -- does
    # NOT enter the SA cost function. Populates `best_grid.plant_placements`
    # for downstream export + viewer rendering.
    try:
        from .plant_siting import (
            place_stage_c_plants,
            align_highstreet_axes,
            align_road_facing_axes,
        )
        placements = place_stage_c_plants(best_grid)
        if verbose and placements:
            for kind, p in placements.items():
                print(f"  plant_site[{kind}]: ({p.row},{p.col}) "
                      f"on {p.host_land_use} -- {p.reason}")
        # deterministic highstreet axis alignment (each cell
        # faces the ROAD it fronts; chain-perpendicular preferred).
        n_hs = align_highstreet_axes(best_grid)
        #: general road-facing alignment for ALL
        # built categories (school, hospital, residential, etc.).
        # Honours the SA-chosen axis if it already points at a road;
        # otherwise overrides to face the nearest ROAD 4-neighbour.
        n_road = align_road_facing_axes(best_grid)
        if verbose:
            print(f"  axis aligned: highstreet={n_hs}, road-facing={n_road}")
    except Exception as exc:  # pragma: no cover - non-blocking
        if verbose:
            print(f"  (post-SA hooks skipped: {exc})")

    return best_grid, hist


# ---------------------------------------------------------------------------
# Convenience reporting
# ---------------------------------------------------------------------------
def print_score_comparison(initial: Grid, optimised: Grid,
                            requirements: Requirements,
                            cfg: Optional[DistrictConfig] = None,
                            weights: Optional[Dict[str, float]] = None,
                            ) -> None:
    """Print before/after metric scores for an optimisation run.

    Returns
    -------
    None
    """
    cfg = cfg or load_config()
    weights = weights or DEFAULT_WEIGHTS
    s0 = score_layout(initial, requirements, cfg).as_dict()
    s1 = score_layout(optimised, requirements, cfg).as_dict()
    print(f"  {'metric':<22}{'before':>9}{'after':>9}{'delta':>9}")
    for k in s0:
        d = s1[k] - s0[k]
        sign = "+" if d >= 0 else ""
        print(f"  {k:<22}{s0[k]:>9.2f}{s1[k]:>9.2f}{sign}{d:>+8.2f}")
    o0 = weighted_score(score_layout(initial, requirements, cfg), weights)
    o1 = weighted_score(score_layout(optimised, requirements, cfg), weights)
    print(f"  {'overall':<22}{o0:>9.3f}{o1:>9.3f}{o1 - o0:>+9.3f}")
