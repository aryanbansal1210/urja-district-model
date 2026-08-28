"""Surgical injection of `entrance_sides` onto existing GeoJSONs
.

Mirrors `inject_faith_tags.py` / `inject_carport_sites.py`. Loads each
`outputs/geojson3d/*.geojson`, reconstructs a minimal grid from the
parcel features, runs `layout.entrance_assignment.assign_entrances`,
and writes `entrance_sides` (a list of cardinal degrees) onto every
feature whose (row, col) matches a built cell.

Does NOT re-anneal optimised_sa. Idempotent.
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
from layout.entrance_assignment import assign_entrances  # noqa: E402

GEOJSON_DIR = HERE / "outputs" / "geojson3d"


def _grid_from_geojson(features: List[dict]) -> Grid:
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
    grid = Grid.empty(n_rows=max_r + 1, n_cols=max_c + 1,
                       cell_size_m=cell_size_m)
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
            cell_entrances: Dict[Tuple[int, int], List[int]]) -> int:
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
        sides = cell_entrances.get(key) or []
        p["entrance_sides"] = list(sides)
        if sides:
            touched += 1
    return touched


def main() -> None:
    print(f"Injecting entrance_sides into {GEOJSON_DIR}/*.geojson")
    files = sorted(GEOJSON_DIR.glob("*.geojson"))
    for path in files:
        if path.name == "manifest.json":
            continue
        with path.open("r", encoding="utf-8") as f:
            gj = json.load(f)
        features = gj.get("features", []) or []
        grid = _grid_from_geojson(features)
        n_assigned = assign_entrances(grid)
        cell_entrances: Dict[Tuple[int, int], List[int]] = {
            (c.row, c.col): list(c.entrance_sides)
            for c in grid.all_cells()
        }
        # Count cells with 2-door (highstreet on road) for the log.
        two_door = sum(1 for v in cell_entrances.values() if len(v) == 2)
        touched = _inject(features, cell_entrances)
        with path.open("w", encoding="utf-8") as f:
            json.dump(gj, f, indent=2)
        print(f"  {path.name:30s} built={n_assigned:4d} two_door={two_door:3d} "
              f"features_tagged={touched:4d}")


if __name__ == "__main__":
    main()
