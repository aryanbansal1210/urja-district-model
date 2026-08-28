"""Regression tests for the per-cell building-axis orientation feature
.

Three coupling points are exercised:
  1. ``layout.metrics.building_wind_alignment_score`` -- soft metric that
     rewards built cells whose cardinal facing gives an E-W long axis.
  2. ``energy.network`` facade-orientation cooling multiplier (E/W-facing
     cells raise cooling, N/S-facing cells reduce it).
  3. ``energy.network.total_bipv_potential_kwp`` is scaled by facade
     south-exposure (N/S-facing cells expose full south long facade;
     E/W-facing cells expose only the short south end).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.grid import Cell, Grid, HeightTier                      # noqa: E402
from core.land_use import LandUse                                  # noqa: E402
from energy.costs import load_economics                            # noqa: E402
from energy.network import (                                       # noqa: E402
    EnergyNetwork,
    _bipv_facade_orientation_multiplier,
    _facade_orientation_cooling_multiplier,
)
from layout.metrics import building_wind_alignment_score           # noqa: E402


def _populate_built_cell(grid: Grid, row: int, col: int,
                          axis_deg: float = 0.0,
                          height_m: float = 25.0) -> Cell:
    cell = grid.at(row, col)
    cell.land_use = LandUse.RESIDENTIAL_MID
    cell.height_m = height_m
    cell.height_tier = HeightTier.MEDIUM
    cell.building_axis_deg = axis_deg
    return cell


# ---------------------------------------------------------------------------
# 1. Wind-alignment metric.
# ---------------------------------------------------------------------------
def test_wind_alignment_score_zero_for_empty_grid() -> None:
    grid = Grid.empty(5, 5, 200.0)
    assert building_wind_alignment_score(grid) == 0.0


def test_wind_alignment_score_one_when_all_facing_n_or_s() -> None:
    """Long axis E-W (facing N or S) catches Punjab SW summer wind."""
    grid = Grid.empty(5, 5, 200.0)
    for r in range(5):
        for c in range(5):
            _populate_built_cell(grid, r, c, axis_deg=0.0)
    assert building_wind_alignment_score(grid) == 1.0
    grid2 = Grid.empty(5, 5, 200.0)
    for r in range(5):
        for c in range(5):
            _populate_built_cell(grid2, r, c, axis_deg=180.0)
    assert building_wind_alignment_score(grid2) == 1.0


def test_wind_alignment_score_zero_when_all_facing_e_or_w() -> None:
    """Long axis N-S (facing E or W) misses SW summer wind cross-vent."""
    grid = Grid.empty(5, 5, 200.0)
    for r in range(5):
        for c in range(5):
            _populate_built_cell(grid, r, c, axis_deg=90.0)
    assert building_wind_alignment_score(grid) == 0.0
    grid2 = Grid.empty(5, 5, 200.0)
    for r in range(5):
        for c in range(5):
            _populate_built_cell(grid2, r, c, axis_deg=270.0)
    assert building_wind_alignment_score(grid2) == 0.0


# ---------------------------------------------------------------------------
# 2. Facade-orientation cooling multiplier.
# ---------------------------------------------------------------------------
def test_facade_cooling_multiplier_facing_e_increases_cooling() -> None:
    """Long axis N-S (facing E) -> E + W long facades soak morning + afternoon sun."""
    grid = Grid.empty(3, 3, 200.0)
    cell = _populate_built_cell(grid, 1, 1, axis_deg=90.0)
    assert _facade_orientation_cooling_multiplier(cell) > 1.0


def test_facade_cooling_multiplier_facing_w_also_increases_cooling() -> None:
    """Facing 270 is the same long axis as facing 90 (both long axis N-S)."""
    grid = Grid.empty(3, 3, 200.0)
    cell = _populate_built_cell(grid, 1, 1, axis_deg=270.0)
    assert _facade_orientation_cooling_multiplier(cell) > 1.0


def test_facade_cooling_multiplier_facing_n_or_s_reduces_cooling() -> None:
    """Long axis E-W (facing N or S) -> easy to shade S facade + cross-vent."""
    grid = Grid.empty(3, 3, 200.0)
    cell = _populate_built_cell(grid, 1, 1, axis_deg=0.0)
    assert _facade_orientation_cooling_multiplier(cell) < 1.0
    cell2 = _populate_built_cell(grid, 1, 0, axis_deg=180.0)
    assert _facade_orientation_cooling_multiplier(cell2) < 1.0


def test_facade_cooling_multiplier_returns_unity_for_non_built() -> None:
    grid = Grid.empty(3, 3, 200.0)
    cell = grid.at(1, 1)  # OPEN_SPACE default
    cell.building_axis_deg = 90.0
    assert _facade_orientation_cooling_multiplier(cell) == 1.0


def test_facing_e_cooling_pushes_dispatched_peak_higher_than_facing_n() -> None:
    """Build two minimal networks, only difference is building facing, and
    confirm the long-axis-N-S cell carries higher peak_cooling_kw than the
    long-axis-E-W cell."""
    econ = load_economics()

    grid_facing_e = Grid.empty(3, 3, 200.0)
    _populate_built_cell(grid_facing_e, 1, 1, axis_deg=90.0, height_m=25.0)
    net_e = EnergyNetwork.from_grid(grid_facing_e, econ=econ,
                                       layout_name="test_e")

    grid_facing_n = Grid.empty(3, 3, 200.0)
    _populate_built_cell(grid_facing_n, 1, 1, axis_deg=0.0, height_m=25.0)
    net_n = EnergyNetwork.from_grid(grid_facing_n, econ=econ,
                                       layout_name="test_n")

    pc_e = next(n.peak_cooling_kw for n in net_e.nodes
                  if n.cell_id == (1, 1))
    pc_n = next(n.peak_cooling_kw for n in net_n.nodes
                  if n.cell_id == (1, 1))
    # facing E = 1.10x baseline, facing N = 0.95x. Ratio ~ 1.158.
    assert pc_e > pc_n, (
        f"facing-E cooling should exceed facing-N; got {pc_e=}, {pc_n=}"
    )


# ---------------------------------------------------------------------------
# 3. BIPV facade-orientation multiplier.
# ---------------------------------------------------------------------------
def test_bipv_multiplier_full_when_long_axis_e_w() -> None:
    """Long axis E-W (facing N or S) -> full south long facade for BIPV."""
    grid = Grid.empty(3, 3, 200.0)
    cell = _populate_built_cell(grid, 1, 1, axis_deg=0.0)
    assert _bipv_facade_orientation_multiplier(cell) == 1.0
    cell2 = _populate_built_cell(grid, 1, 0, axis_deg=180.0)
    assert _bipv_facade_orientation_multiplier(cell2) == 1.0


def test_bipv_multiplier_quarter_when_long_axis_n_s() -> None:
    """Long axis N-S (facing E or W) -> only short S end has south exposure."""
    grid = Grid.empty(3, 3, 200.0)
    for a in (90.0, 270.0):
        cell = _populate_built_cell(grid, 1, 1, axis_deg=a)
        assert _bipv_facade_orientation_multiplier(cell) == 0.25


# ---------------------------------------------------------------------------
# 4. Default for a non-built cell is 0 (no BIPV) and 1 (no cooling effect).
# ---------------------------------------------------------------------------
def test_defaults_for_non_built_cell() -> None:
    grid = Grid.empty(3, 3, 200.0)
    cell = grid.at(1, 1)  # OPEN_SPACE
    assert cell.building_axis_deg == 0.0
    assert _bipv_facade_orientation_multiplier(cell) == 0.0
    assert _facade_orientation_cooling_multiplier(cell) == 1.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    fails: List[str] = []
    for fn in fns:
        try:
            fn()
            print(f"  OK  {fn.__name__}")
        except Exception as e:
            print(f"  X   {fn.__name__}: {e}")
            fails.append(fn.__name__)
    if fails:
        print(f"\n{len(fails)} tests failed: {fails}")
        sys.exit(1)
    print(f"\nAll {len(fns)} building-axis tests passed.")
