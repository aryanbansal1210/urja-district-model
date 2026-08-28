"""Smoke tests for the 3D GeoJSON exporter."""

from __future__ import annotations

import sys
import math
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import load_config                         # noqa: E402
from core.export_3d import DEFAULT_LAYOUTS, grid_to_geojson  # noqa: E402
from layout.generator import generate                       # noqa: E402


def test_each_archetype_exports_feature_collection() -> None:
    cfg = load_config()
    for name in DEFAULT_LAYOUTS:
        grid = generate(name)
        geojson = grid_to_geojson(grid, name, cfg)
        assert geojson["type"] == "FeatureCollection"
        assert geojson["features"]
        assert geojson["metadata"]["layout"] == name


def test_export_preserves_cell_land_use_counts() -> None:
    cfg = load_config()
    for name in DEFAULT_LAYOUTS:
        grid = generate(name)
        geojson = grid_to_geojson(grid, name, cfg)
        parcel_counts = Counter(
            f["properties"]["land_use"]
            for f in geojson["features"]
            if f["properties"]["role"] == "parcel"
        )
        model_counts = Counter(c.land_use.value for c in grid.all_cells())
        assert parcel_counts == model_counts
        assert sum(parcel_counts.values()) == grid.total_cells


def test_coordinates_bound_configured_five_km_site() -> None:
    cfg = load_config()
    grid = generate("chandigarh_sector")
    geojson = grid_to_geojson(grid, "chandigarh_sector", cfg)
    min_lon, min_lat, max_lon, max_lat = geojson["metadata"]["bounds"]

    lat_span_m = (max_lat - min_lat) * 111_320.0
    lon_span_m = (
        (max_lon - min_lon)
        * 111_320.0
        * math.cos(math.radians(cfg.site["latitude"]))
    )
    assert 4_990.0 <= lat_span_m <= 5_010.0
    assert 4_990.0 <= lon_span_m <= 5_010.0


def test_built_structures_have_positive_height() -> None:
    cfg = load_config()
    grid = generate("chandigarh_sector")
    geojson = grid_to_geojson(grid, "chandigarh_sector", cfg)
    structures = [
        f for f in geojson["features"]
        if f["properties"]["role"] == "structure"
        and f["properties"]["is_built"]
    ]
    assert structures
    assert all(f["properties"]["height_m"] > 0 for f in structures)


if __name__ == "__main__":
    test_each_archetype_exports_feature_collection()
    test_export_preserves_cell_land_use_counts()
    test_coordinates_bound_configured_five_km_site()
    test_built_structures_have_positive_height()
    print("3D export tests passed.")
