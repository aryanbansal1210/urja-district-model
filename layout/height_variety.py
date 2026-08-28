"""TRUE 3-TIER HEIGHT VARIETY within every residential class.2,
the author's visual-review ballot "small/medium/big in each income
level" - ratified over the spine-only barbell).

Why: the spine gradient alone produced a BARBELL (MID = 68 short / 11
medium / 46 tall - the medium middle nearly vanished paying for the spine
promotions), so each class read as one-or-two heights on the skyline.
This pass REBALANCES each class to a true three-tier mix while:

  * conserving the class FLOOR STOCK (and therefore households + demand)
    to well under one cell's floor - same discipline as spine_gradient;
  * KEEPING the Bertaud logic: TALL nearest the arterial spine, MEDIUM in
    the body, SHORT at the edge (cells are re-sorted by spine distance,
    so the gradient survives inside the richer mix);
  * giving the plotted kothi colony (RESIDENTIAL_HIGH, ratified fixed
    FAR 1.2) VISUAL variety only: height_m cycles 9/12/15 m (G+2/G+3/G+4
    at 3 m floor-to-floor) with the tier - and therefore the modelled
    floor area - left at MEDIUM. Roof areas shift with floors (taller =
    slimmer = less roof), which is honest physics and lands in the
    re-pin.

Deterministic (sorted pools, no RNG). Runs POST-anneal after
apply_spine_gradient and BEFORE export / energy build. NOT byte-exact:
heights feed shading + party-wall + roof areas, so this pass re-pins.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from core.config import DistrictConfig, load_config
from core.grid import Cell, Grid, HeightTier
from core.land_use import LandUse

from .locked_zones import arterial_rows_cols

# Kothi visual variants: G+2 / G+3 / G+4 at 3 m floor-to-floor.
_KOTHI_HEIGHTS_M = (9.0, 12.0, 15.0)


def apply_height_variety(grid: Grid,
                         cfg: Optional[DistrictConfig] = None,
                         target_medium_share: float = 0.40
                         ) -> Dict[str, object]:
    """Rebalance LOW/MID to a floor-conserving 3-tier mix; vary kothis.

    Mutates ``grid``. Returns a per-class summary for the register.
    """
    if cfg is None:
        cfg = load_config()

    mult = {t: float(cfg.height_multiplier_for(t.value))
            for t in (HeightTier.SHORT, HeightTier.MEDIUM, HeightTier.TALL)}
    height = {t: float(cfg.height_for(t.value))
              for t in (HeightTier.SHORT, HeightTier.MEDIUM, HeightTier.TALL)}

    art_rows, art_cols = arterial_rows_cols(grid)
    art_set = {(c.row, c.col) for c in grid.all_cells()
               if c.land_use == LandUse.ROAD
               and (c.locked or c.row in art_rows or c.col in art_cols)}

    def _dist_to_spine(cell: Cell) -> int:
        if not art_set:
            return 0
        return min(abs(cell.row - r) + abs(cell.col - c)
                   for (r, c) in art_set)

    summary: Dict[str, object] = {}

    for land_use, key in ((LandUse.RESIDENTIAL_LOW, "low"),
                          (LandUse.RESIDENTIAL_MID, "mid")):
        cells = [c for c in grid.all_cells()
                 if c.land_use == land_use and c.has_building
                 and not c.locked]
        n = len(cells)
        if n < 3:
            continue
        floor_units = sum(
            mult[c.height_tier or HeightTier.MEDIUM] for c in cells)

        # Solve S+M+T = n and mS*S + M + mT*T = floor_units for the mix
        # with M pinned near the target share, then nudge T by +-2 cells
        # to minimise the residual floor delta.
        mS, mT = mult[HeightTier.SHORT], mult[HeightTier.TALL]
        best: Optional[Tuple[float, int, int, int]] = None
        for m_try in range(int(n * target_medium_share) - 2,
                           int(n * target_medium_share) + 3):
            if not 0 <= m_try <= n:
                continue
            t_exact = ((floor_units - m_try - mS * (n - m_try))
                       / (mT - mS))
            for t_try in (int(t_exact), int(t_exact) + 1):
                s_try = n - m_try - t_try
                if t_try < 0 or s_try < 0:
                    continue
                delta = (mS * s_try + m_try + mT * t_try) - floor_units
                cand = (abs(delta), m_try, t_try, s_try)
                if best is None or cand < best:
                    best = cand
        assert best is not None
        _, n_med, n_tall, n_short = best

        # Bertaud ordering: nearest spine -> TALL, body -> MEDIUM,
        # edge -> SHORT. Deterministic tiebreak on (row, col).
        cells.sort(key=lambda c: (_dist_to_spine(c), c.row, c.col))
        new_counts = {HeightTier.SHORT: 0, HeightTier.MEDIUM: 0,
                      HeightTier.TALL: 0}
        for i, c in enumerate(cells):
            if i < n_tall:
                tier = HeightTier.TALL
            elif i < n_tall + n_med:
                tier = HeightTier.MEDIUM
            else:
                tier = HeightTier.SHORT
            c.height_tier = tier
            c.height_m = height[tier]
            new_counts[tier] += 1
        new_floor = sum(mult[c.height_tier] for c in cells)
        summary[key] = {
            "n": n,
            "mix_s_m_t": (new_counts[HeightTier.SHORT],
                          new_counts[HeightTier.MEDIUM],
                          new_counts[HeightTier.TALL]),
            "floor_delta_units": round(new_floor - floor_units, 3),
        }

    # ---- kothi colony: visual 9/12/15 m, floor model untouched -----------
    kothis = sorted((c for c in grid.all_cells()
                     if c.land_use == LandUse.RESIDENTIAL_HIGH
                     and c.has_building and not c.locked),
                    key=lambda c: (c.row, c.col))
    k_counts = [0, 0, 0]
    for c in kothis:
        idx = (c.row + c.col) % 3
        c.height_m = _KOTHI_HEIGHTS_M[idx]
        c.height_tier = HeightTier.MEDIUM
        k_counts[idx] += 1
    summary["high_kothi"] = {
        "n": len(kothis),
        "variants_9_12_15_m": tuple(k_counts),
        "floor_model": "unchanged (ratified FAR 1.2; visual variety only)",
    }
    return summary


if __name__ == "__main__":
    from energy.network import grid_from_geojson

    g, name = grid_from_geojson()
    out = apply_height_variety(g)
    print(name)
    for k, v in out.items():
        print(" ", k, v)
