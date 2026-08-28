"""Regression tests for the viewer sun-position approximation."""

from __future__ import annotations

import math
import sys
from datetime import date


LATITUDE_DEG = 30.64
LONGITUDE_DEG = 76.82
TOLERANCE_DEG = 2.0
VIEWER_HEIGHT_SCALE = 3.0
CELL_SIZE_M = 200.0
SHADOW_HIDE_ALTITUDE_DEG = 8.0


def day_of_year(value: date) -> int:
    return value.timetuple().tm_yday


def sun_position(day: int, hour: int, minute: int = 0) -> tuple[float, float]:
    """Return altitude and azimuth degrees for site-local solar time.

    Azimuth follows the viewer convention from the handoff: 0 is south and
    negative values are east of south.
    """
    decimal_hour = hour + minute / 60
    lat_rad = math.radians(LATITUDE_DEG)
    gamma = 2 * math.pi / 365 * (day - 1 + (decimal_hour - 12) / 24)
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )

    standard_meridian_deg = LONGITUDE_DEG
    solar_time_min = (
        decimal_hour * 60
        + equation_of_time
        + 4 * (LONGITUDE_DEG - standard_meridian_deg)
    )
    hour_angle = math.radians(solar_time_min / 4 - 180)
    altitude = math.asin(
        math.sin(lat_rad) * math.sin(declination)
        + math.cos(lat_rad) * math.cos(declination) * math.cos(hour_angle)
    )
    azimuth = math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(lat_rad)
        - math.tan(declination) * math.cos(lat_rad),
    )
    return math.degrees(altitude), math.degrees(azimuth)


def assert_close(actual: float, expected: float) -> None:
    assert abs(actual - expected) <= TOLERANCE_DEG, (
        f"expected {expected:.1f} deg +/- {TOLERANCE_DEG:.1f}, "
        f"got {actual:.2f} deg"
    )


def flat_shadow_vector(
    day: int,
    hour: int,
    height_m: float = 18.0,
) -> tuple[float, float, float] | None:
    """Viewer flat-shadow vector in metres.

    Azimuth convention matches the viewer: 0=south, negative=east of south.
    The visual shadow uses the same locked vertical scale as the deck.gl
    building extrusions, so the displayed shadow corresponds to displayed
    height rather than unscaled physical height.
    """
    altitude_deg, azimuth_deg = sun_position(day, hour)
    if altitude_deg <= SHADOW_HIDE_ALTITUDE_DEG:
        return None
    shadow_len_m = min(
        height_m * VIEWER_HEIGHT_SCALE / math.tan(math.radians(altitude_deg)),
        3 * CELL_SIZE_M,
    )
    east_m = math.sin(math.radians(azimuth_deg)) * shadow_len_m
    north_m = math.cos(math.radians(azimuth_deg)) * shadow_len_m
    return east_m, north_m, shadow_len_m


def test_summer_solstice_noon_is_near_zenith() -> None:
    altitude, _ = sun_position(day_of_year(date(2026, 6, 21)), 12)
    assert_close(altitude, 82.0)


def test_winter_solstice_noon_is_low_southern_sun() -> None:
    altitude, _ = sun_position(day_of_year(date(2026, 12, 21)), 12)
    assert_close(altitude, 36.0)


def test_summer_solstice_morning_sun_is_eastern() -> None:
    altitude, azimuth = sun_position(day_of_year(date(2026, 6, 21)), 6)
    assert_close(altitude, 11.0)
    assert_close(azimuth, -111.0)


def test_flat_shadow_hidden_below_usable_sun_band() -> None:
    assert flat_shadow_vector(day_of_year(date(2026, 6, 21)), 5) is None


def test_flat_shadow_morning_points_west() -> None:
    vector = flat_shadow_vector(day_of_year(date(2026, 6, 21)), 8)
    assert vector is not None
    east_m, north_m, length_m = vector
    assert east_m < -0.9 * length_m
    assert abs(north_m) < 0.25 * length_m


def test_flat_shadow_noon_points_north_and_shortens() -> None:
    vector = flat_shadow_vector(day_of_year(date(2026, 6, 21)), 12)
    assert vector is not None
    east_m, north_m, length_m = vector
    assert abs(east_m) < 0.15 * length_m
    assert north_m > 0.95 * length_m
    assert length_m < 10.0


def test_flat_shadow_evening_points_east() -> None:
    vector = flat_shadow_vector(day_of_year(date(2026, 6, 21)), 17)
    assert vector is not None
    east_m, north_m, length_m = vector
    assert east_m > 0.9 * length_m


def test_flat_shadow_low_winter_sun_is_clamped() -> None:
    vector = flat_shadow_vector(day_of_year(date(2026, 12, 21)), 8, height_m=70.0)
    assert vector is not None
    assert abs(vector[2] - 3 * CELL_SIZE_M) < 1e-6


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    failures = []
    for test in tests:
        try:
            test()
            print(f"  OK  {test.__name__}")
        except Exception as exc:
            print(f"  X   {test.__name__}: {exc}")
            failures.append(test.__name__)
    if failures:
        print(f"\n{len(failures)} tests failed: {failures}")
        sys.exit(1)
    print(f"\nAll {len(tests)} sun math tests passed.")
