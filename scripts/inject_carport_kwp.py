"""Surgical injection of `carport_kwp` into existing GeoJSON parcels.

the author flagged the viewer renders carport sites as small
canopy ticks only and asks for actual PV panels on the carports. The
viewer's `pvPanelFeatures` (Codex task #5) needs the per-cell carport
kWp to size the panel block. `is_carport_site` is already exported;
this script adds the per-cell `carport_kwp` derived from
`layout.carport_siting.carport_kwp_for_cell` so Codex can read it
without re-hardcoding the per-category footprint map.

DOES NOT re-anneal. Idempotent. Mirrors `inject_carport_sites.py` /
`inject_floating_pv_sites.py` patterns.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from core.grid import Cell, Grid  # noqa: E402
from core.land_use import LandUse  # noqa: E402
from layout.carport_siting import carport_kwp_for_cell  # noqa: E402


GEOJSON_DIR = HERE / "outputs" / "geojson3d"


def _grid_lookup_from_features(features: List[dict]) -> Dict[Tuple[int, int], Cell]:
    """Reconstruct minimal cells (row, col, land_use) for the kWp lookup."""
    out: Dict[Tuple[int, int], Cell] = {}
    for f in features:
        p = f.get("properties") or {}
        if p.get("role") != "parcel":
            continue
        r = p.get("row")
        c = p.get("col")
        if r is None or c is None:
            continue
        try:
            lu = LandUse(p.get("land_use"))
        except (ValueError, TypeError):
            continue
        cell = Cell(row=int(r), col=int(c),
                    centre_x_m=0.0, centre_y_m=0.0, cell_size_m=200.0)
        cell.land_use = lu
        cell.is_carport_site = bool(p.get("is_carport_site", False))
        out[(int(r), int(c))] = cell
    return out


def _inject(features: List[dict],
            cells: Dict[Tuple[int, int], Cell]) -> int:
    """Write `carport_kwp` onto every feature whose (row, col) matches."""
    n_with_kwp = 0
    for f in features:
        p = f.get("properties")
        if p is None:
            continue
        r = p.get("row")
        c = p.get("col")
        if r is None or c is None:
            continue
        cell = cells.get((int(r), int(c)))
        if cell is None:
            continue
        kwp = carport_kwp_for_cell(cell) if cell.is_carport_site else 0.0
        p["carport_kwp"] = round(kwp, 1)
        if kwp > 0:
            n_with_kwp += 1
    return n_with_kwp


def main() -> None:
    print(f"Injecting carport_kwp into {GEOJSON_DIR}/*.geojson")
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
        cells = _grid_lookup_from_features(features)
        touched = _inject(features, cells)
        total_kwp = sum(
            float(f.get("properties", {}).get("carport_kwp", 0))
            for f in features
            if f.get("properties", {}).get("role") == "parcel"
        )
        with path.open("w", encoding="utf-8") as f:
            json.dump(gj, f, indent=2)
        print(f"  {path.name:30s} sites_with_kwp={touched:4d} "
              f"total_carport_kwp={total_kwp:>9.1f}")


if __name__ == "__main__":
    main()
