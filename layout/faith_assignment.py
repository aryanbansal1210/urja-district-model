"""Faith-tag assignment for RELIGIOUS cells (Item 2,).

Tags each RELIGIOUS cell with a faith string ("sikh" / "hindu" /
"muslim" / "christian") by Punjab Census-2011 state-level religion
shares, with a >=1 minimum-cell floor for the smallest minorities
so the LP cannot dispatch a district that "has no mosque or church".

Punjab Census 2011 religion shares (Tier-1, primary):
- Sikh:      57.69% (16,004,754 / 27,743,338)
- Hindu:     38.49% (10,678,138 / 27,743,338)
- Muslim:     1.93%    (535,489 / 27,743,338)
- Christian:  1.26%    (348,230 / 27,743,338)
- Other:      0.65% (Jain + Buddhist + others)
Source: https://www.census2011.co.in/data/religion/state/03-punjab.html

Assignment algorithm (deterministic, no randomness):
1. Sort RELIGIOUS cells by (row, col) — stable, layout-independent.
2. Reserve 1 cell for Muslim + 1 for Christian (smallest minorities,
   floor-1 to guarantee diversity).
3. Distribute the remaining cells between Sikh and Hindu by their
   relative shares (Hare/largest-remainder rounding).
4. Walk the sorted cell list in order: first N_sikh get sikh, next
   N_hindu get hindu, next 1 muslim, last 1 christian.

This is a DEMAND-only attribute. Religious roof PV is 0 (HARD
constraint), so the dispatch only sees faith via the festival-day
demand multiplier (see Economics.behavioural_demand_multiplier).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from core.grid import Cell, Grid
from core.land_use import LandUse


# Punjab Census 2011 state-level religion shares (sum to 1.0).
PUNJAB_CENSUS_2011_SHARES: Dict[str, float] = {
    "sikh":      0.5769,
    "hindu":     0.3849,
    "muslim":    0.0193,
    "christian": 0.0126,
    # "other" 0.0063 absorbed into hindu for simplicity (Jain ~majority
    # of "other" in Punjab; SDA/Buddhist negligible — the religious-
    # tag is for festival-load tagging, not Census reproduction).
}

# Faiths that get a >=1 floor (so a district always has at least one
# mosque and one church). Sikh + Hindu always get the bulk.
MINIMUM_FAITH_FLOOR: Tuple[str, ...] = ("muslim", "christian")


def religious_cell_count(grid: Grid) -> int:
    """How many RELIGIOUS cells does this grid have?"""
    return sum(
        1 for c in grid.all_cells() if c.land_use == LandUse.RELIGIOUS
    )


def compute_faith_quotas(
    n_cells: int,
    shares: Optional[Dict[str, float]] = None,
) -> Dict[str, int]:
    """Compute per-faith cell counts that sum to `n_cells` and respect
    the minimum-floor for each of MINIMUM_FAITH_FLOOR.

    Largest-remainder allocation after reserving the floor; ties broken
    by faith name (alphabetical) for determinism.
    """
    if shares is None:
        shares = PUNJAB_CENSUS_2011_SHARES
    if n_cells <= 0:
        return {f: 0 for f in shares}
    floor_faiths = [f for f in MINIMUM_FAITH_FLOOR if f in shares]
    n_floor = min(len(floor_faiths), n_cells)
    # Reserve 1 cell per minority faith (up to what we can afford).
    quotas: Dict[str, int] = {f: 0 for f in shares}
    for f in floor_faiths[:n_floor]:
        quotas[f] = 1
    remaining = n_cells - n_floor
    if remaining <= 0:
        return quotas
    # Distribute the remaining among ALL faiths (including the floored
    # ones — they still claim their share above 1).
    target = {f: shares[f] * n_cells for f in shares}
    # Subtract what we've already given.
    fractional = {f: target[f] - quotas[f] for f in shares}
    # Floor for the non-floored faiths (sikh + hindu); zero out negatives.
    int_parts = {f: max(0, int(fractional[f])) for f in shares}
    given_int = sum(int_parts.values())
    leftover = remaining - given_int
    # Allocate leftover cells by largest remainder (with name-tiebreak).
    if leftover < 0:
        # Trim from largest int_parts first.
        order = sorted(
            shares,
            key=lambda f: (-int_parts[f], f),
        )
        i = 0
        while leftover < 0 and i < len(order):
            f = order[i]
            if int_parts[f] > 0:
                int_parts[f] -= 1
                leftover += 1
            i += 1
    else:
        # Distribute the remaining leftover by largest fractional
        # remainder; if leftover > num_faiths (large n with rounding
        # underage), do round-robin passes by remainder until exhausted.
        remainders = {f: fractional[f] - int_parts[f] for f in shares}
        while leftover > 0:
            order = sorted(
                shares,
                key=lambda f: (-remainders[f], f),
            )
            take = min(leftover, len(order))
            for f in order[:take]:
                int_parts[f] += 1
                remainders[f] -= 1.0  # demote so next round picks a different faith
            leftover -= take
    for f in shares:
        quotas[f] += int_parts[f]
    return quotas


def assign_faiths_to_religious_cells(
    grid: Grid,
    shares: Optional[Dict[str, float]] = None,
) -> Dict[str, int]:
    """Tag each RELIGIOUS cell of `grid` with a faith. Mutates in place.

    Walks RELIGIOUS cells in (row, col) order and assigns by quota.
    Order of faith blocks in the walk: sikh, hindu, muslim, christian.
    Non-RELIGIOUS cells are left with `faith=None`.

    Returns
    -------
    Dict[str, int]
        Per-faith allocation counts (for logging / tests).
    """
    rel_cells: List[Cell] = sorted(
        (c for c in grid.all_cells() if c.land_use == LandUse.RELIGIOUS),
        key=lambda c: (c.row, c.col),
    )
    quotas = compute_faith_quotas(len(rel_cells), shares=shares)
    # Walk order: sikh, hindu, muslim, christian (largest share first).
    walk_order = ("sikh", "hindu", "muslim", "christian")
    idx = 0
    for faith in walk_order:
        n = quotas.get(faith, 0)
        for _ in range(n):
            if idx >= len(rel_cells):
                break
            rel_cells[idx].faith = faith
            idx += 1
    # Sanity: clear faiths on non-RELIGIOUS cells (defensive).
    for c in grid.all_cells():
        if c.land_use != LandUse.RELIGIOUS:
            c.faith = None
    return quotas
