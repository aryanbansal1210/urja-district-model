"""Regression tests for the geometric shadow integration that replaces
the old neighbour-counting heuristic for PV-yield shading.

The annual-average multiplier is a continuous physics-based number rather
than the heuristic's 0.60 / 0.80 / 1.00 step bins, so these tests pin
qualitative geometry properties (north-vs-south asymmetry at northern-
hemisphere latitudes, isolation behaviour, ordering by distance / height)
rather than exact numeric values that would be fragile to small geometry
tweaks.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.grid import Cell, Grid, HeightTier                      # noqa: E402
from core.land_use import LandUse                                  # noqa: E402
from energy.costs import load_economics                            # noqa: E402
from energy.solar_geometry import (                                # noqa: E402
    GROUND_PV_PANEL_TOP_M,
    _MONTH_DOY,
    compute_geometric_shading,
    sun_position,
)


SITE_LAT = 30.64    # Punjab / Zirakpur
SITE_LON = 76.82


# ---------------------------------------------------------------------------
# Grid helpers (no SA dependency).
# ---------------------------------------------------------------------------
def _empty_grid(n_rows: int = 5, n_cols: int = 5,
                cell_size_m: float = 200.0) -> Grid:
    return Grid.empty(n_rows=n_rows, n_cols=n_cols, cell_size_m=cell_size_m)


def _set_cell(grid: Grid, row: int, col: int, *,
               land_use: LandUse = LandUse.RESIDENTIAL_MID,
               height_m: float = 0.0,
               height_tier: HeightTier = HeightTier.SHORT) -> Cell:
    cell = grid.at(row, col)
    cell.land_use = land_use
    cell.height_m = height_m
    cell.height_tier = height_tier
    return cell


# ---------------------------------------------------------------------------
# Sun-position sanity (matches tests/test_sun_math.py but in radians).
# ---------------------------------------------------------------------------
def test_summer_solstice_noon_altitude_near_zenith() -> None:
    alt, _ = sun_position(_MONTH_DOY["jun"], 12.0, SITE_LAT, SITE_LON)
    deg = math.degrees(alt)
    assert deg > 75, f"Punjab June noon should be near zenith, got {deg:.1f}°"


def test_winter_solstice_noon_altitude_low() -> None:
    alt, _ = sun_position(_MONTH_DOY["dec"], 12.0, SITE_LAT, SITE_LON)
    deg = math.degrees(alt)
    assert 25 < deg < 50, f"Punjab Dec noon altitude should be ~35°, got {deg:.1f}°"


def test_noon_azimuth_near_zero() -> None:
    # Convention here: azimuth 0 = sun due south. Punjab in March equinox.
    _, az = sun_position(_MONTH_DOY["mar"], 12.0, SITE_LAT, SITE_LON)
    assert abs(math.degrees(az)) < 10, (
        f"March noon azimuth should be near south (0°), got {math.degrees(az):.1f}°"
    )


# ---------------------------------------------------------------------------
# Geometric shading -- isolated cases.
# ---------------------------------------------------------------------------
def test_isolated_pv_cell_no_shading() -> None:
    """A solo built cell with no taller neighbours has multiplier == 1.0."""
    grid = _empty_grid()
    _set_cell(grid, 2, 2, land_use=LandUse.RESIDENTIAL_MID,
              height_m=10.0)
    econ = load_economics()
    mults = compute_geometric_shading(grid, econ, SITE_LAT, SITE_LON)
    assert (2, 2) in mults
    assert abs(mults[(2, 2)] - 1.0) < 1e-6, (
        f"isolated cell should have multiplier 1.0, got {mults[(2, 2)]}"
    )


def test_southern_neighbour_shades_more_than_northern() -> None:
    """At 30.64°N the sun crosses the southern sky; tall neighbours to the
    SOUTH must produce a larger yield loss than identical neighbours to the
    NORTH."""
    econ = load_economics()

    grid_south = _empty_grid(7, 7)
    _set_cell(grid_south, 3, 3, land_use=LandUse.RESIDENTIAL_MID,
              height_m=6.0)
    # In core.grid the row/col system has row growing in +y, so south of
    # row 3 is row 2 (smaller index). Verified by the heuristic which uses
    # row-1 = south.
    _set_cell(grid_south, 2, 3, land_use=LandUse.RESIDENTIAL_HIGH,
              height_m=30.0)
    mults_s = compute_geometric_shading(grid_south, econ, SITE_LAT, SITE_LON)

    grid_north = _empty_grid(7, 7)
    _set_cell(grid_north, 3, 3, land_use=LandUse.RESIDENTIAL_MID,
              height_m=6.0)
    _set_cell(grid_north, 4, 3, land_use=LandUse.RESIDENTIAL_HIGH,
              height_m=30.0)
    mults_n = compute_geometric_shading(grid_north, econ, SITE_LAT, SITE_LON)

    south_mult = mults_s[(3, 3)]
    north_mult = mults_n[(3, 3)]
    assert south_mult < north_mult, (
        f"South neighbour should shade more than north at lat {SITE_LAT}; "
        f"got south_mult={south_mult:.3f} >= north_mult={north_mult:.3f}"
    )
    # Sanity: north-side neighbour at 30°N should barely shade anything.
    assert north_mult > 0.97, (
        f"Northern neighbour at 30°N should produce negligible shading, "
        f"got {north_mult:.3f}"
    )


def test_taller_neighbour_shades_more_than_shorter() -> None:
    """Monotonicity in caster height: doubling the neighbour's height must
    not decrease the shading penalty on its southern target."""
    econ = load_economics()
    mults_per_height = []
    for h in (10.0, 20.0, 40.0, 60.0):
        grid = _empty_grid(7, 7)
        _set_cell(grid, 3, 3, land_use=LandUse.RESIDENTIAL_MID,
                  height_m=6.0)
        _set_cell(grid, 2, 3, land_use=LandUse.RESIDENTIAL_HIGH,
                  height_m=h)
        mults = compute_geometric_shading(grid, econ, SITE_LAT, SITE_LON)
        mults_per_height.append(mults[(3, 3)])
    for prev, curr in zip(mults_per_height, mults_per_height[1:]):
        assert curr <= prev + 1e-6, (
            f"taller neighbour should not REDUCE shading penalty; "
            f"got monotone-violation {mults_per_height}"
        )
    # Across the full height range we should see some real movement.
    assert mults_per_height[0] - mults_per_height[-1] > 0.005, (
        f"expected meaningful spread across heights 10-60 m, got "
        f"{mults_per_height}"
    )


def test_solar_farm_cell_uses_ground_level_target() -> None:
    """A SOLAR_FARM cell next to a tall building should see more shading
    than a same-position BUILT cell with high rooftop -- because the farm's
    PV reference height is 1.5 m, not the building's rooftop level."""
    econ = load_economics()
    grid_farm = _empty_grid(5, 5)
    _set_cell(grid_farm, 2, 2, land_use=LandUse.SOLAR_FARM, height_m=0.0)
    _set_cell(grid_farm, 1, 2, land_use=LandUse.RESIDENTIAL_HIGH,
              height_m=20.0)
    mults_farm = compute_geometric_shading(grid_farm, econ, SITE_LAT, SITE_LON)

    grid_high_roof = _empty_grid(5, 5)
    _set_cell(grid_high_roof, 2, 2, land_use=LandUse.RESIDENTIAL_MID,
              height_m=18.0)
    _set_cell(grid_high_roof, 1, 2, land_use=LandUse.RESIDENTIAL_HIGH,
              height_m=20.0)
    mults_high = compute_geometric_shading(grid_high_roof, econ, SITE_LAT,
                                            SITE_LON)
    assert mults_farm[(2, 2)] < mults_high[(2, 2)], (
        f"farm at 1.5m should be shaded more than a same-spot rooftop at "
        f"18m by an identical 20m neighbour; got farm={mults_farm[(2,2)]:.3f} "
        f">= rooftop={mults_high[(2,2)]:.3f}"
    )


def test_multiplier_within_unit_interval() -> None:
    """For a varied grid the multiplier must stay in [0, 1] for every cell."""
    econ = load_economics()
    grid = _empty_grid(10, 10)
    # Salt-and-pepper of tall and short buildings.
    for r in range(10):
        for c in range(10):
            h = 24.0 if (r + c) % 3 == 0 else 6.0
            _set_cell(grid, r, c,
                       land_use=LandUse.RESIDENTIAL_MID,
                       height_m=h)
    mults = compute_geometric_shading(grid, econ, SITE_LAT, SITE_LON)
    for cell_id, m in mults.items():
        assert 0.0 <= m <= 1.0, (
            f"multiplier out of [0, 1] for {cell_id}: {m}"
        )
    assert len(mults) == 100, f"expected 100 cells, got {len(mults)}"


def test_optimised_sa_aggregate_is_more_lenient_than_heuristic_floor() -> None:
    """Sanity check on the live SA layout: rooftop / solar-farm aggregate
    multipliers should sit above the old heuristic floor of 0.60.
    """
    from energy.network import load_optimised_network
    n = load_optimised_network()
    rooftop = n.rooftop_pv_shading_yield_multiplier()
    farm = n.solar_farm_pv_shading_yield_multiplier()
    assert rooftop > 0.60, f"rooftop aggregate {rooftop:.3f} <= heuristic floor"
    assert farm > 0.60, f"farm aggregate {farm:.3f} <= heuristic floor"
    # Aggregate should also be <= 1.0 (some cells are shaded).
    assert rooftop < 1.0, f"rooftop aggregate {rooftop:.3f} suspiciously equals 1.0"
    assert farm < 1.0, f"farm aggregate {farm:.3f} suspiciously equals 1.0"


# ---------------------------------------------------------------------------
# Runner.
# ---------------------------------------------------------------------------
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
    print(f"\nAll {len(fns)} geometric-shading tests passed.")
