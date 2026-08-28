"""Surgical injection of `is_carport_site` tags into existing GeoJSON.

Mirrors `inject_faith_tags.py`: loads each `outputs/geojson3d/*.geojson`,
reconstructs the grid (parcel-level cells only), runs the deterministic
`layout.carport_siting.place_carports` algorithm, and writes the
`is_carport_site` boolean back onto every feature whose (row, col)
matches a chosen site (parcel AND structure features for the cell).

DOES NOT re-anneal the frozen optimised_sa layout.
instruction: "add cells surgically and regenerate the GeoJSON via
export_3d without re-running SA".

Run after a model change that updates the carport-siting algorithm.
Idempotent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from core.grid import Grid  # noqa: E402
from core.land_use import LandUse  # noqa: E402
from layout.carport_siting import place_carports  # noqa: E402


GEOJSON_DIR = HERE / "outputs" / "geojson3d"


def _grid_from_geojson_for_siting(features: List[dict]) -> Grid:
    """Lightweight Grid reconstruction (land_use only) for the siting step.

    The carport-siting algorithm only needs row, col, and land_use to
    pick sites — we can rebuild a minimal Grid from the GeoJSON
    parcel features without instantiating the full Building / PV cost
    machinery.
    """
    # Sniff grid dims from features.
    max_r = max_c = -1
    cell_size_m = 200.0
    for f in features:
        p = f.get("properties", {}) or {}
        if p.get("role") not in (None, "parcel"):
            continue
        r = p.get("row")
        c = p.get("col")
        if r is None or c is None:
            continue
        if int(r) > max_r:
            max_r = int(r)
        if int(c) > max_c:
            max_c = int(c)
    n_rows = max_r + 1
    n_cols = max_c + 1
    grid = Grid.empty(n_rows=n_rows, n_cols=n_cols, cell_size_m=cell_size_m)
    for f in features:
        p = f.get("properties", {}) or {}
        if p.get("role") not in (None, "parcel"):
            continue
        r = p.get("row")
        c = p.get("col")
        if r is None or c is None:
            continue
        try:
            grid.at(int(r), int(c)).land_use = LandUse(p.get("land_use"))
        except (ValueError, TypeError):
            continue
    return grid


def _inject(features: List[dict],
            cell_is_site: Dict[Tuple[int, int], bool]) -> int:
    """Write `is_carport_site` onto every feature whose (row, col) matches.

    Returns the number of features touched (any is_carport_site=True write)."""
    touched = 0
    for f in features:
        p = f.get("properties")
        if p is None:
            continue
        r = p.get("row")
        c = p.get("col")
        if r is None or c is None:
            continue
        key = (int(r), int(c))
        flag = bool(cell_is_site.get(key, False))
        p["is_carport_site"] = flag
        if flag:
            touched += 1
    return touched


def main() -> None:
    print(f"Injecting carport-site tags into {GEOJSON_DIR}/*.geojson")
    files = sorted(GEOJSON_DIR.glob("*.geojson"))
    if not files:
        print("No GeoJSON files found.")
        return
    for path in files:
        if path.name == "manifest.json":
            continue
        with path.open("r", encoding="utf-8") as f:
            gj = json.load(f)
        features = gj.get("features", []) or []
        grid = _grid_from_geojson_for_siting(features)
        chosen = place_carports(grid)
        # Build per-cell flag dict from the grid (post-siting).
        cell_is_site: Dict[Tuple[int, int], bool] = {
            (c.row, c.col): bool(c.is_carport_site)
            for c in grid.all_cells()
        }
        per_quad = {q: len(v) for q, v in chosen.items()}
        n_sites = sum(per_quad.values())
        touched = _inject(features, cell_is_site)
        with path.open("w", encoding="utf-8") as f:
            json.dump(gj, f, indent=2)
        per_quad_str = ", ".join(f"q{q}={n}" for q, n in
                                    sorted(per_quad.items()))
        print(f"  {path.name:30s} sites={n_sites:3d} "
              f"features_tagged={touched:4d} ({per_quad_str})")


if __name__ == "__main__":
    main()
