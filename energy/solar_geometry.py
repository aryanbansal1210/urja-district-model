"""Geometric shadow integration for PV-yield multipliers.

Replaces the previous step-function ``_pv_shading_multiplier`` heuristic
(10 % drop per tall S/SW/SE/E/W neighbour, floor 0.60) with a physics-based
annual-average yield multiplier computed from real building geometry.

For each PV-bearing cell:

  1. Sample sun positions at the midpoint of every (month, daypart) slice.
  2. For each above-horizon sample with non-zero PV capacity factor, project
     the footprint of every neighbour cell whose ``height_m`` exceeds the
     target's rooftop level onto the target's rooftop plane.
  3. Take the union of those shadow footprints intersected with the target
     cell's roof area --> shaded fraction at that sun sample.
  4. Average the shaded fraction weighted by ``slice_hours * pv_capacity_factor``
     (i.e. weighted by energy yield, not just sun-up hours).
  5. Multiplier = 1 - annual_average_shaded_fraction, clamped to [0, 1].

Same data the deck.gl viewer uses per-frame; this just integrates the
result offline once per network build. The output replaces the heuristic's
0.60 / 0.80 / 1.00 step-function bins with a continuous, physics-justified
multiplier in [0, 1].
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.grid import Cell, Grid
from core.land_use import LandUse

#: this used to be a local literal carrying the comment
# "matches the heuristic" - a comment ASSERTING agreement with the other four
# copies rather than enforcing it. The shared constant now enforces it. Value
# unchanged at 1.5, so this is byte-neutral.
from core.shading_constants import GROUND_PV_PANEL_TOP_M  # noqa: E402,F401

# Daypart id (from ``economics.yaml`` dayparts list) -> midpoint hour-of-day.
# All 12 dayparts are 2 hours wide; we pick the centre.
_DAYPART_MIDPOINT_HOUR: Dict[str, float] = {
    "00_02": 1.0, "02_04": 3.0, "04_06": 5.0, "06_08": 7.0,
    "08_10": 9.0, "10_12": 11.0, "12_14": 13.0, "14_16": 15.0,
    "16_18": 17.0, "18_20": 19.0, "20_22": 21.0, "22_24": 23.0,
}

# Month -> representative day-of-year (15th of the month).
_MONTH_DOY: Dict[str, int] = {
    "jan": 15,  "feb": 46,  "mar": 74,  "apr": 105,
    "may": 135, "jun": 166, "jul": 196, "aug": 227,
    "sep": 258, "oct": 288, "nov": 319, "dec": 349,
}

# Minimum sun altitude (degrees) below which the sun's PV-yield contribution
# is negligible and the shadow computation would explode to near-horizontal
# beams. Anything below this cutoff is dropped.
_MIN_SUN_ALTITUDE_DEG = 5.0

#: sub-sample each 2-hour slice at 4
# offsets (every 30 min) rather than evaluating only the slice midpoint.
# Rationale: a 2-hour slice like 18_20 has a midpoint at 19:00 which is
# below the 5 deg altitude threshold for much of the year, so the
# previous single-midpoint sampling effectively dropped every evening
# shadow contribution. Multi-sampling lets the 18:15 / 18:45 / 19:15 /
# 19:45 sub-samples each contribute to the integration when they are
# above the horizon, weighted by slice_hours / 4 * pv_capacity_factor.
# This does NOT artificially harshen shadows -- sub-samples below the
# horizon still contribute zero, so the only effect is that transitional
# / twilight slices are represented more accurately than by their
# midpoint alone.
_SUB_SAMPLE_OFFSETS_MIN: Tuple[float, ...] = (-45.0, -15.0, 15.0, 45.0)
_SUB_SAMPLES_PER_SLICE = len(_SUB_SAMPLE_OFFSETS_MIN)

# Default rooftop raster resolution (cells per side). 10 -> 20 m pixels at
# the standard 200 m cell, which gives a < 1 % discretisation error on
# shaded fraction for typical district geometry. Bump for higher fidelity.
DEFAULT_RASTER_RES = 10


# ---------------------------------------------------------------------------
# Sun position (copied from tests/test_sun_math.py for reuse in production).
# Convention here matches the test module: azimuth 0 = sun due south,
# increasing westward (Punjab / northern-hemisphere afternoon = positive
# azimuth).
# ---------------------------------------------------------------------------
def sun_position(day_of_year: int, hour_local: float,
                 latitude_deg: float, longitude_deg: float
                 ) -> Tuple[float, float]:
    """Return ``(altitude_rad, azimuth_rad)`` for site-local solar time.

    Convention matches ``tests/test_sun_math.py``: ``hour_local`` is
    apparent solar time at the site (i.e. solar noon == 12.00). No
    timezone / longitude correction is applied -- callers pass solar
    time directly. For Punjab (lon 76.82, IST meridian 82.5), this
    introduces a ~23 min skew vs. IST clock time which is well below
    the shading model's resolution.

    Below-horizon samples return a negative altitude; callers filter on
    altitude > 0 before using.

    ``longitude_deg`` is currently unused; kept in the signature so callers
    can swap to a UTC-based variant without changing call sites.
    """
    _ = longitude_deg  # reserved for future UTC-based convention
    lat_rad = math.radians(latitude_deg)
    n = day_of_year
    gamma = 2 * math.pi / 365 * (n - 1 + (hour_local - 12) / 24)
    declin = (
        0.006918
        - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma)
    )
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma)
    )
    solar_time_min = hour_local * 60 + eqtime
    hour_angle = math.radians(solar_time_min / 4 - 180)
    altitude = math.asin(
        math.sin(lat_rad) * math.sin(declin)
        + math.cos(lat_rad) * math.cos(declin) * math.cos(hour_angle)
    )
    azimuth = math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(lat_rad)
        - math.tan(declin) * math.cos(lat_rad),
    )
    return altitude, azimuth


# ---------------------------------------------------------------------------
# Sun-sample table (one entry per TimeSlice, filtered above-horizon).
# ---------------------------------------------------------------------------
def _sun_samples(econ, latitude_deg: float, longitude_deg: float
                  ) -> List[Tuple[float, float, float]]:
    """Yield ``(altitude_rad, azimuth_rad, weight)`` per usable sub-sample.

 upgrade: each 2-hour TimeSlice is sub-sampled at four
    30-minute offsets from the midpoint, instead of only the midpoint
    itself. Each sub-sample carries ``slice_hours_per_year *
    pv_capacity_factor / 4`` of the slice's annual energy weight; sub-
    samples below ``_MIN_SUN_ALTITUDE_DEG`` are dropped (no shadow
    geometry contribution, no integration weight). The total weight of a
    fully-daylight slice is therefore unchanged from the previous
    midpoint-only formulation, but twilight slices that previously had
    a single below-horizon midpoint sample are now correctly represented
    by the above-horizon minutes within them.
    """
    samples: List[Tuple[float, float, float]] = []
    min_alt = math.radians(_MIN_SUN_ALTITUDE_DEG)
    for s in econ.slices:
        if s.daypart not in _DAYPART_MIDPOINT_HOUR:
            continue
        if s.month not in _MONTH_DOY:
            continue
        doy = _MONTH_DOY[s.month]
        midpoint = _DAYPART_MIDPOINT_HOUR[s.daypart]
        cf = float(econ.pv_capacity_factor(s.id))
        if cf <= 0:
            continue
        slice_total_weight = float(s.hours_per_year) * cf
        if slice_total_weight <= 0:
            continue
        sub_weight = slice_total_weight / _SUB_SAMPLES_PER_SLICE
        for offset_min in _SUB_SAMPLE_OFFSETS_MIN:
            hour = midpoint + offset_min / 60.0
            alt, az = sun_position(doy, hour, latitude_deg, longitude_deg)
            if alt <= min_alt:
                continue
            samples.append((alt, az, sub_weight))
    return samples


# ---------------------------------------------------------------------------
# Geometric shading core.
# ---------------------------------------------------------------------------
def _candidate_casters(grid: Grid, target: Cell, target_z: float,
                         max_shadow_reach_m: float) -> List[Cell]:
    """Return cells that could conceivably shade the target.

    Filter rules:
      * caster height > target rooftop level (lower-or-equal can't shade);
      * caster centre within ``max_shadow_reach_m + cell diagonal`` of the
        target centre (anything further can't reach even at the lowest
        usable sun altitude).
    """
    reach = max_shadow_reach_m + grid.cell_size_m * math.sqrt(2.0)
    out: List[Cell] = []
    for c in grid.all_cells():
        if c.row == target.row and c.col == target.col:
            continue
        if c.height_m <= target_z:
            continue
        dx = c.centre_x_m - target.centre_x_m
        dy = c.centre_y_m - target.centre_y_m
        if dx * dx + dy * dy > reach * reach:
            continue
        out.append(c)
    return out


def _shaded_pixels_for_caster(pixel_u: np.ndarray, pixel_v: np.ndarray,
                                shadow_dx: float, shadow_dy: float,
                                half: float) -> np.ndarray:
    """Boolean mask of target pixels inside one caster's shadow polygon.

    A pixel ``P`` is inside the swept-rectangle shadow iff there exists
    ``t in [0, 1]`` such that ``P - t * shadow_vec`` lies inside the
    caster's footprint (a square of half-width ``half`` centred at the
    caster). Solving the constraints for t gives a 1-D interval that we
    intersect against ``[0, 1]``.

    Inputs ``pixel_u`` / ``pixel_v`` are the pixel offsets (metres) from
    the caster's centre. Returns a same-shape boolean mask.
    """
    eps = 1e-9

    if abs(shadow_dx) > eps:
        t_lo_x = np.where(shadow_dx > 0,
                          (pixel_u - half) / shadow_dx,
                          (pixel_u + half) / shadow_dx)
        t_hi_x = np.where(shadow_dx > 0,
                          (pixel_u + half) / shadow_dx,
                          (pixel_u - half) / shadow_dx)
    else:
        # Shadow vector is purely in y. Pixel must already lie inside the
        # caster's x-band; if so, any t in [0, 1] satisfies the x test.
        inside_x = (pixel_u >= -half) & (pixel_u <= half)
        t_lo_x = np.where(inside_x, 0.0, np.inf)
        t_hi_x = np.where(inside_x, 1.0, -np.inf)

    if abs(shadow_dy) > eps:
        t_lo_y = np.where(shadow_dy > 0,
                          (pixel_v - half) / shadow_dy,
                          (pixel_v + half) / shadow_dy)
        t_hi_y = np.where(shadow_dy > 0,
                          (pixel_v + half) / shadow_dy,
                          (pixel_v - half) / shadow_dy)
    else:
        inside_y = (pixel_v >= -half) & (pixel_v <= half)
        t_lo_y = np.where(inside_y, 0.0, np.inf)
        t_hi_y = np.where(inside_y, 1.0, -np.inf)

    t_lo = np.maximum(np.maximum(t_lo_x, t_lo_y), 0.0)
    t_hi = np.minimum(np.minimum(t_hi_x, t_hi_y), 1.0)
    return t_lo <= t_hi


def compute_geometric_shading(grid: Grid, econ, latitude_deg: float,
                                longitude_deg: float,
                                raster_res: int = DEFAULT_RASTER_RES,
                                ) -> Dict[Tuple[int, int], float]:
    """Return ``(row, col) -> pv_yield_multiplier in [0, 1]``.

    Multiplier = 1 - annual-average shaded fraction (weighted by
    capacity-factor x slice hours). Cells without PV (no building AND not
    SOLAR_FARM) are absent from the dict; the caller should default to 1.0
    for those.

    Parameters
    ----------
    grid
        Populated layout grid.
    econ
        Economics object (provides slices + capacity factors).
    latitude_deg, longitude_deg
        Site coordinates in degrees.
    raster_res
        Pixels per cell side. 10 -> 20 m pixels at 200 m cell. Larger
        gives higher fidelity at quadratic cost.
    """
    samples = _sun_samples(econ, latitude_deg, longitude_deg)
    total_weight = sum(w for _, _, w in samples)
    if total_weight <= 0 or not samples:
        return {}

    # Pre-compute per-sample shadow direction unit vector. Convention from
    # ``sun_position``: az = 0 -> sun south -> shadow points north (+y).
    # Sun horizontal vector points toward sun = (-sin(az), -cos(az)) under
    # this convention; shadow direction = (+sin(az), +cos(az)).
    sample_meta: List[Tuple[float, float, float, float]] = []  # alt, sdx_unit, sdy_unit, weight
    for alt, az, weight in samples:
        sdx = math.sin(az)
        sdy = math.cos(az)
        sample_meta.append((alt, sdx, sdy, weight))

    # Identify PV-bearing target cells.
    pv_targets: List[Tuple[Cell, float]] = []
    for c in grid.all_cells():
        is_built = bool(c.has_building)
        is_farm = c.land_use == LandUse.SOLAR_FARM
        if not (is_built or is_farm):
            continue
        target_z = c.height_m if is_built else GROUND_PV_PANEL_TOP_M
        pv_targets.append((c, target_z))

    if not pv_targets:
        return {}

    cell_size = float(grid.cell_size_m)
    half = cell_size / 2.0
    pixel_size = cell_size / raster_res
    # Pixel centres in cell-local coords [-half + pixel_size/2.. +half - pixel_size/2].
    offsets = (np.arange(raster_res) - raster_res / 2.0 + 0.5) * pixel_size
    PX, PY = np.meshgrid(offsets, offsets, indexing="xy")
    pixel_area_fraction = 1.0 / (raster_res * raster_res)

    # Maximum shadow reach for the candidate pre-filter: tallest building
    # in the grid at the lowest usable altitude.
    max_h = max(c.height_m for c in grid.all_cells()) or 0.0
    min_alt_rad = math.radians(_MIN_SUN_ALTITUDE_DEG)
    max_shadow_reach_m = max_h / math.tan(min_alt_rad) if max_h > 0 else 0.0

    multipliers: Dict[Tuple[int, int], float] = {}
    for target, target_z in pv_targets:
        candidates = _candidate_casters(grid, target, target_z,
                                          max_shadow_reach_m)
        if not candidates:
            multipliers[(target.row, target.col)] = 1.0
            continue

        # World-coordinate pixel positions for THIS target.
        tx_pixels = target.centre_x_m + PX
        ty_pixels = target.centre_y_m + PY

        weighted_shaded = 0.0
        for alt, sdx_unit, sdy_unit, weight in sample_meta:
            tan_alt = math.tan(alt)
            if tan_alt <= 0:
                continue
            shadow_mask = np.zeros((raster_res, raster_res), dtype=bool)
            for caster in candidates:
                eff_h = caster.height_m - target_z
                if eff_h <= 0:
                    continue
                shadow_len = eff_h / tan_alt
                if shadow_len < pixel_size * 0.5:
                    continue  # negligible at this resolution
                shadow_dx = sdx_unit * shadow_len
                shadow_dy = sdy_unit * shadow_len
                pixel_u = tx_pixels - caster.centre_x_m
                pixel_v = ty_pixels - caster.centre_y_m
                shadow_mask |= _shaded_pixels_for_caster(
                    pixel_u, pixel_v, shadow_dx, shadow_dy, half,
                )
            shaded_fraction = shadow_mask.sum() * pixel_area_fraction
            weighted_shaded += shaded_fraction * weight

        annual_shaded = weighted_shaded / total_weight
        multiplier = max(0.0, min(1.0, 1.0 - annual_shaded))
        multipliers[(target.row, target.col)] = multiplier

    return multipliers


# ---------------------------------------------------------------------------
# Diagnostics helper -- run as a module to dump the multipliers.
# ---------------------------------------------------------------------------
def _site_lat_lon_from_cfg(cfg) -> Tuple[float, float]:
    site = getattr(cfg, "site", {}) or {}
    return float(site.get("latitude", 30.64)), float(site.get("longitude", 76.82))


if __name__ == "__main__":  # pragma: no cover - diagnostic CLI
    from core.config import load_config
    from energy.costs import load_economics
    from energy.network import load_optimised_network
    cfg = load_config()
    econ = load_economics()
    net = load_optimised_network()
    lat, lon = _site_lat_lon_from_cfg(cfg)
    mults = compute_geometric_shading(net.grid, econ, lat, lon)
    pv_built = [m for (r, c), m in mults.items()
                if net.grid.at(r, c).has_building]
    pv_farm = [m for (r, c), m in mults.items()
               if net.grid.at(r, c).land_use == LandUse.SOLAR_FARM]
    print(f"geometric shading: {len(mults)} PV-bearing cells")
    if pv_built:
        print(f"  built rooftops   n={len(pv_built):3d}  "
              f"mean={np.mean(pv_built):.3f}  "
              f"min={np.min(pv_built):.3f}  max={np.max(pv_built):.3f}")
    if pv_farm:
        print(f"  solar farm cells n={len(pv_farm):3d}  "
              f"mean={np.mean(pv_farm):.3f}  "
              f"min={np.min(pv_farm):.3f}  max={np.max(pv_farm):.3f}")
