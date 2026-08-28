"""Post-anneal FLOOR-CONSERVING spine gradient (Stage-.

Implements the ratified A2 spine class (register 0e / _spec/F0_FAR_TABLE.md):
residential cells adjacent to the locked arterial skeleton get the PUDA 1:3
GROUP-HOUSING envelope (net FAR 3.0 = TALL tier, 27 m G+9) - the Bertaud
"density gradient toward the transit spine" from
_spec/reference/far_fsi_analysis.md.

Why FLOOR-CONSERVING: the FX-3 demand reconciliation sizes the residential
cell count so that (cells x 20,000 m2 at MEDIUM) = the cited dwelling-stock
requirement (54,346 households at 250k). Simply promoting spine cells to
TALL would ADD ~50% floor on each and overshoot the household count, so
every promotion is compensated by demoting the residential cells FURTHEST
from the arterials to SHORT (net FAR 1.34 = an under-cap edge build, legal
inside the ratified 2.0 envelope). With the config multipliers (tall 1.5 /
short 0.67) the balance is +10,000 m2 per TALL vs -6,600 m2 per SHORT, i.e.
~2 TALL : 3 SHORT; the greedy pairing below keeps the district floor delta
below one cell's floor (reported, and checked in the FX-3 acceptance).

The result is the classic Bertaud profile INSIDE the ratified envelopes:
tall group housing on the spine, medium perimeter blocks in the body, short
blocks at the green-belt edge - with total floor (and therefore households
and demand) unchanged.

Deterministic: pools are sorted by (distance, row, col); no RNG. Runs
POST-anneal (the SA anneals at uniform MEDIUM so its floor accounting is
exact) and BEFORE the export / energy build so heights, shading and rooftop
areas all see the final built form.

Scope guards: only RESIDENTIAL_LOW / RESIDENTIAL_MID participate. The
plotted kothi colony (RESIDENTIAL_HIGH) is a fixed 12 m form and is never
touched; locked cells never appear in either pool (they are ROAD/SOLAR).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid, HeightTier
from core.land_use import LandUse

from .locked_zones import arterial_rows_cols

CellId = Tuple[int, int]

# eligible for the spine (group-housing) promotion / edge demotion.
_GRADIENT_LAND_USES = (LandUse.RESIDENTIAL_LOW, LandUse.RESIDENTIAL_MID)


def _arterial_cells(grid: Grid) -> List[Cell]:
    """The arterial skeleton: locked ROAD cells (fall back to the
    deterministic arterial rows/cols for grids that were built without
    locked-zone tagging, e.g. bare archetypes in tests)."""
    arts = [c for c in grid.all_cells()
            if c.land_use == LandUse.ROAD and c.locked]
    if arts:
        return arts
    art_rows, art_cols = arterial_rows_cols(grid)
    return [c for c in grid.all_cells()
            if c.land_use == LandUse.ROAD
            and (c.row in art_rows or c.col in art_cols)]


def _intersections(grid: Grid) -> List[CellId]:
    """Arterial x arterial crossing points (the TOD nodes)."""
    art_rows, art_cols = arterial_rows_cols(grid)
    return [(r, c) for r in art_rows for c in art_cols]


def apply_spine_gradient(grid: Grid,
                         cfg: Optional[DistrictConfig] = None) -> Dict[str, float]:
    """Promote spine-adjacent low/mid cells to TALL, floor-compensated by
    SHORT demotions at the edge. Mutates ``grid`` in place.

    Returns a summary dict (counts + floor delta) for the register/logbook
    and the FX-3 acceptance check.
    """
    if cfg is None:
        cfg = load_config()

    tall_mult = float(cfg.height_multiplier_for(HeightTier.TALL.value))
    short_mult = float(cfg.height_multiplier_for(HeightTier.SHORT.value))
    tall_h = cfg.height_for(HeightTier.TALL.value)
    short_h = cfg.height_for(HeightTier.SHORT.value)

    arterials = _arterial_cells(grid)
    if not arterials:
        return {"n_tall": 0, "n_short": 0, "floor_delta_m2": 0.0,
                "spine_eligible": 0, "uncompensated_spine": 0}
    art_set = {(c.row, c.col) for c in arterials}
    nodes = _intersections(grid)

    def _dist_to_arterial(cell: Cell) -> int:
        return min(abs(cell.row - r) + abs(cell.col - c) for (r, c) in art_set)

    def _dist_to_node(cell: Cell) -> int:
        return min(abs(cell.row - r) + abs(cell.col - c) for (r, c) in nodes)

    promote_pool: List[Cell] = []
    demote_pool: List[Cell] = []
    for cell in grid.all_cells():
        if cell.land_use not in _GRADIENT_LAND_USES or cell.locked:
            continue
        adjacent = any((n.row, n.col) in art_set
                       for n in grid.neighbours_4(cell.row, cell.col))
        if adjacent:
            promote_pool.append(cell)
        else:
            demote_pool.append(cell)

    # Deterministic ordering: spine promotions nearest the TOD crossings
    # first; edge demotions furthest from any arterial first.
    promote_pool.sort(key=lambda c: (_dist_to_node(c), c.row, c.col))
    demote_pool.sort(key=lambda c: (-_dist_to_arterial(c), c.row, c.col))

    def _base(cell: Cell) -> float:
        cat = {LandUse.RESIDENTIAL_LOW: "low_income_residential",
               LandUse.RESIDENTIAL_MID: "mid_income_residential"}[cell.land_use]
        return cfg.floor_area_for_category(cat)

    # Greedy floor-balanced pairing: promote while demotion budget allows,
    # pulling demotions until each promotion's floor gain is compensated.
    gain_total = 0.0
    loss_total = 0.0
    tall_cells: List[Cell] = []
    short_cells: List[Cell] = []
    di = 0
    for cell in promote_pool:
        gain = _base(cell) * (tall_mult - 1.0)
        # Extend demotions while under-compensated and supply remains.
        projected_loss = loss_total
        picked: List[Cell] = []
        while (di + len(picked)) < len(demote_pool) and \
                projected_loss < gain_total + gain:
            cand = demote_pool[di + len(picked)]
            projected_loss += _base(cand) * (1.0 - short_mult)
            picked.append(cand)
        if projected_loss < gain_total + gain:
            break  # demotion supply exhausted - stop promoting
        tall_cells.append(cell)
        gain_total += gain
        short_cells.extend(picked)
        loss_total = projected_loss
        di += len(picked)

    for cell in tall_cells:
        cell.height_tier = HeightTier.TALL
        cell.height_m = tall_h
    for cell in short_cells:
        cell.height_tier = HeightTier.SHORT
        cell.height_m = short_h

    delta = gain_total - loss_total
    return {
        "n_tall": len(tall_cells),
        "n_short": len(short_cells),
        "floor_delta_m2": delta,
        "spine_eligible": len(promote_pool),
        "uncompensated_spine": len(promote_pool) - len(tall_cells),
    }


if __name__ == "__main__":
    from layout.generator import generate
    from layout.locked_zones import apply_locked_zones

    g = generate("chandigarh_sector")
    apply_locked_zones(g, solar_cells=225)
    summary = apply_spine_gradient(g)
    print("spine gradient summary:")
    for k, v in summary.items():
        print(f"  {k:<22} {v}")
