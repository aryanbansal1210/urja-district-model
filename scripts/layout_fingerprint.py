"""LAYOUT FINGERPRINT - the guard for.

On one cell of the frozen layout changed at 14:07, AFTER pin
discovery (02:53) and AFTER the chain's step-1 regen (09:00) but DURING the
step-4 suite. Nothing errored at edit time. It surfaced 3 h 37 m later as five
red byte-exact tests, and cost the whole chain run. Register row.

This script makes that failure loud and instant. It hashes ONLY the fields that
can move a solve, so a viewer-side re-save that changes nothing physical does
not trip it:

  * per-cell: land_use, height_tier, cell_height_m, albedo,
    vegetation_fraction, building_axis_deg, amenity_subtype, road_class,
    road_width_m, is_carport_site, is_floating_pv_site, streetlight_type,
    has_street_trees, faith
  * street edges: (cell_a, cell_b, kind, width_m)

These are exactly the properties `energy.network.grid_from_geojson` reads back.
Everything else in the file (colours, households, floor areas, deployable kWp,
shading percentiles) is DERIVED downstream from land_use + height_tier + config,
so it cannot move a solve on its own and is deliberately excluded.

USAGE

    # record, at the top of a chain (step 1, before the regen)
    PYTHONPATH=. python -u scripts/layout_fingerprint.py --write

    # verify, before any step that re-solves (step 4, the suite)
    PYTHONPATH=. python -u scripts/layout_fingerprint.py --check
    #   exit 0 = unchanged, exit 1 = CHANGED (halt the chain)

    # just look
    PYTHONPATH=. python -u scripts/layout_fingerprint.py

The stamp lives at outputs/verification/layout_fingerprint.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

GEOJSON = os.path.join(ROOT, "outputs", "geojson3d", "optimised_sa.geojson")
STAMP = os.path.join(ROOT, "outputs", "verification", "layout_fingerprint.json")

# The fields grid_from_geojson actually reads back onto the Grid.
SOLVE_RELEVANT = (
    "land_use", "height_tier", "cell_height_m", "albedo",
    "vegetation_fraction", "building_axis_deg", "amenity_subtype",
    "road_class", "road_width_m", "is_carport_site", "is_floating_pv_site",
    "floating_pv_cluster_id", "streetlight_type", "streetlight_segment_id",
    "has_street_trees", "faith", "entrance_sides",
)


def fingerprint(path: str = GEOJSON) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)

    cells, edges = [], []
    counts: dict = {}
    for feature in gj.get("features", []):
        p = feature.get("properties", {})
        if p.get("role") == "street_edge":
            edges.append((
                tuple(p.get("cell_a") or ()), tuple(p.get("cell_b") or ()),
                str(p.get("kind", "")), float(p.get("width_m", 0.0) or 0.0),
            ))
            continue
        r, c = p.get("row"), p.get("col")
        if r is None or c is None:
            continue
        cells.append(((r, c), tuple(
            # json round-trip so 15.0 and 15 hash identically
            json.dumps(p.get(k), sort_keys=True, default=str)
            for k in SOLVE_RELEVANT)))
        lu = p.get("land_use")
        counts[lu] = counts.get(lu, 0) + 1

    cells.sort(key=lambda x: x[0])
    edges.sort()
    h = hashlib.sha256()
    h.update(json.dumps(cells, sort_keys=True).encode())
    h.update(json.dumps(edges, sort_keys=True).encode())

    road_classes: dict = {}
    for feature in gj.get("features", []):
        p = feature.get("properties", {})
        if p.get("land_use") == "road" and p.get("role") != "street_edge":
            rc = p.get("road_class") or "untagged"
            road_classes[rc] = road_classes.get(rc, 0) + 1

    return {
        "sha256": h.hexdigest(),
        "n_cells": len(cells),
        "n_street_edges": len(edges),
        "land_use_counts": dict(sorted(counts.items(), key=lambda kv: str(kv[0]))),
        "road_classes": dict(sorted(road_classes.items())),
        "file_mtime": time.strftime("%F %H:%M:%S",
                                    time.localtime(os.path.getmtime(path))),
    }


def _report(fp: dict, prefix: str = "") -> None:
    print(f"{prefix}sha256        {fp['sha256']}")
    print(f"{prefix}cells         {fp['n_cells']}")
    print(f"{prefix}street edges  {fp['n_street_edges']}")
    print(f"{prefix}roads         {fp['land_use_counts'].get('road')} "
          f"{fp['road_classes']}")
    print(f"{prefix}file mtime    {fp['file_mtime']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="record the current fingerprint as the chain's baseline")
    ap.add_argument("--check", action="store_true",
                    help="compare against the recorded baseline; exit 1 if changed")
    args = ap.parse_args()

    fp = fingerprint()

    if args.write:
        fp["recorded_at"] = time.strftime("%F %H:%M:%S")
        with open(STAMP, "w", encoding="utf-8") as f:
            json.dump(fp, f, indent=2)
        print(f"LAYOUT FINGERPRINT RECORDED {fp['recorded_at']}")
        _report(fp, "  ")
        return 0

    if args.check:
        if not os.path.exists(STAMP):
            print("LAYOUT FINGERPRINT: no baseline recorded - run --write first")
            return 1
        with open(STAMP, "r", encoding="utf-8") as f:
            old = json.load(f)
        if old["sha256"] == fp["sha256"]:
            print(f"LAYOUT FINGERPRINT OK - unchanged since "
                  f"{old.get('recorded_at', '?')} ({fp['sha256'][:16]}...)")
            return 0
        print("*** LAYOUT FINGERPRINT CHANGED - THE FROZEN LAYOUT MOVED "
              "MID-CHAIN. HALT. ***")
        print("  This is REPIN-4 happening again. Every pin and every stored")
        print("  solve behind this point was made on a DIFFERENT town.")
        print("  recorded:")
        _report(old, "    ")
        print("  now:")
        _report(fp, "    ")
        for lu in sorted(set(old["land_use_counts"]) | set(fp["land_use_counts"]),
                         key=str):
            a = old["land_use_counts"].get(lu, 0)
            b = fp["land_use_counts"].get(lu, 0)
            if a != b:
                print(f"    land_use {lu}: {a} -> {b}")
        return 1

    _report(fp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
