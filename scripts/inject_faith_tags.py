"""Surgical injection of `faith` tags into existing GeoJSON layouts.

Loads each `outputs/geojson3d/*.geojson`, computes the deterministic
faith assignment for its RELIGIOUS cells (Punjab Census-2011 shares
with min-1 floor for muslim+christian), and writes the `faith`
property back onto every feature that belongs to a RELIGIOUS cell
(parcel AND all structure features for that cell).

DOES NOT re-anneal the frozen `optimised_sa` layout.
instruction: "add cells surgically and regenerate the GeoJSON via
export_3d without re-running SA". This script is the surgical edit.

Run after a model change that updates the faith assignment algorithm.
Idempotent: re-running produces the same output bytes.

Sources for shares: see `layout/faith_assignment.py` docstring.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from layout.faith_assignment import (  # noqa: E402
    MINIMUM_FAITH_FLOOR,
    PUNJAB_CENSUS_2011_SHARES,
    compute_faith_quotas,
)


GEOJSON_DIR = HERE / "outputs" / "geojson3d"


def _religious_cell_ids(features: List[dict]) -> List[Tuple[int, int]]:
    """Collect distinct (row, col) for cells whose parcel land_use=religious."""
    seen: set = set()
    out: List[Tuple[int, int]] = []
    for f in features:
        p = f.get("properties", {}) or {}
        # Top-level parcel features carry the cell-level land_use.
        if p.get("role") not in (None, "parcel"):
            continue
        if p.get("land_use") != "religious":
            continue
        r = p.get("row")
        c = p.get("col")
        if r is None or c is None:
            continue
        key = (int(r), int(c))
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def _allocate_faiths(cell_ids: List[Tuple[int, int]]) -> Dict[Tuple[int, int], str]:
    """Walk sorted cells, assign faith by quota (sikh, hindu, muslim, christian)."""
    quotas = compute_faith_quotas(len(cell_ids))
    walk_order = ("sikh", "hindu", "muslim", "christian")
    out: Dict[Tuple[int, int], str] = {}
    idx = 0
    for faith in walk_order:
        n = quotas.get(faith, 0)
        for _ in range(n):
            if idx >= len(cell_ids):
                break
            out[cell_ids[idx]] = faith
            idx += 1
    return out


def _inject(features: List[dict],
            cell_faith: Dict[Tuple[int, int], str]) -> int:
    """Write `faith` onto every feature whose (row, col) is in cell_faith.

    Returns the number of features touched."""
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
        faith = cell_faith.get(key)
        if faith is None:
            # Ensure non-RELIGIOUS / unmapped cells get an empty string
            # so the GeoJSON schema is stable across the file.
            if "faith" not in p:
                p["faith"] = ""
            continue
        p["faith"] = faith
        touched += 1
    return touched


def main() -> None:
    print(f"Injecting faith tags into {GEOJSON_DIR}/*.geojson")
    print(f"Punjab Census 2011 shares: {PUNJAB_CENSUS_2011_SHARES}")
    print(f"Min-1 floor for: {MINIMUM_FAITH_FLOOR}")
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
        rel_cells = _religious_cell_ids(features)
        if not rel_cells:
            print(f"  {path.name:30s} no RELIGIOUS cells; skip")
            continue
        cell_faith = _allocate_faiths(rel_cells)
        touched = _inject(features, cell_faith)
        # Count per-faith
        per_faith: Dict[str, int] = {}
        for f in cell_faith.values():
            per_faith[f] = per_faith.get(f, 0) + 1
        with path.open("w", encoding="utf-8") as f:
            json.dump(gj, f, indent=2)
        per_faith_str = ", ".join(f"{k}={v}" for k, v in
                                    sorted(per_faith.items()))
        print(f"  {path.name:30s} cells={len(rel_cells):3d} "
              f"features_touched={touched:4d} ({per_faith_str})")


if __name__ == "__main__":
    main()
