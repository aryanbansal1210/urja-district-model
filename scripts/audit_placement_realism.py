"""A27 -- per-cell placement-realism audit.

Reads `outputs/geojson3d/optimised_sa.geojson` and reports category-
adjacency issues that the existing hard constraints don't catch:

  * BLUE_SPACE directly 4-adjacent to ROAD without an OPEN_SPACE buffer
    (canal-realistic in Punjab but unrealistic for ponds / tanks).
  * RELIGIOUS 8-adjacent to LIGHT_INDUSTRY / WAREHOUSE (now caught by
    the industrial_buffer extension; report repeats the
    finding for diagnostic purposes).
  * Built cells with NO ROAD 4-neighbour (orphaned -- can't be reached).
  * Healthcare / school with NO road frontage (sanity check on existing
    constraints).
  * SOLAR_FARM cells next to RESIDENTIAL_* (urban-design awkwardness).

Outputs the table to stdout AND `outputs/data/placement_audit.md`.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


GEOJSON = (Path(__file__).resolve().parent.parent
            / "outputs" / "geojson3d" / "optimised_sa.geojson")
OUT_MD = (Path(__file__).resolve().parent.parent
           / "outputs" / "data" / "placement_audit.md")


def _load_parcels() -> Dict[Tuple[int, int], Dict[str, object]]:
    data = json.loads(GEOJSON.read_text())
    out: Dict[Tuple[int, int], Dict[str, object]] = {}
    for f in data.get("features", []):
        props = f.get("properties", {})
        if props.get("role") == "parcel":
            r = props.get("row")
            c = props.get("col")
            if isinstance(r, int) and isinstance(c, int):
                out[(r, c)] = props
    return out


def _adj4(cell: Tuple[int, int]) -> List[Tuple[int, int]]:
    r, c = cell
    return [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]


def _adj8(cell: Tuple[int, int]) -> List[Tuple[int, int]]:
    r, c = cell
    return [(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            if not (dr == 0 and dc == 0)]


def main() -> None:
    parcels = _load_parcels()

    findings: Dict[str, List[str]] = defaultdict(list)

    # 1) BLUE_SPACE-ROAD direct adjacency.
    for (r, c), p in parcels.items():
        if p.get("land_use") != "blue_space":
            continue
        for nr, nc in _adj4((r, c)):
            nb = parcels.get((nr, nc))
            if nb and nb.get("land_use") == "road":
                findings["blue_space_road_adjacency"].append(
                    f"BLUE_SPACE ({r:2d},{c:2d}) 4-adj to ROAD ({nr:2d},{nc:2d})"
                )

    # 2) RELIGIOUS 8-adj to industrial.
    for (r, c), p in parcels.items():
        if p.get("land_use") != "religious":
            continue
        for nr, nc in _adj8((r, c)):
            nb = parcels.get((nr, nc))
            if nb and nb.get("land_use") in ("light_industry",
                                             "warehouse_cold_storage"):
                findings["religious_industrial_adjacency"].append(
                    f"RELIGIOUS ({r:2d},{c:2d}) 8-adj to "
                    f"{nb['land_use'].upper()} ({nr:2d},{nc:2d})"
                )
                break

    # 3) Built AMENITY cells with no ROAD 8-neighbour (truly orphaned --
    # `amenities_road_frontage` constraint already enforces this for some
    # types, but we re-report for diagnostic clarity).
    AMENITY_LU = {
        "school", "healthcare", "shopping_centre",
        "retail_highstreet", "hotel_guesthouse", "public_services",
        "religious", "office",
    }
    for (r, c), p in parcels.items():
        if p.get("land_use") not in AMENITY_LU:
            continue
        has_road_8 = any(parcels.get(n, {}).get("land_use") == "road"
                          for n in _adj8((r, c)))
        if not has_road_8:
            findings["amenity_no_road_8nbr"].append(
                f"{p['land_use'].upper()} ({r:2d},{c:2d}) has no ROAD 8-neighbour"
            )

    # 4) SOLAR_FARM 4-adj to residential.
    for (r, c), p in parcels.items():
        if p.get("land_use") != "solar_farm":
            continue
        for nr, nc in _adj4((r, c)):
            nb = parcels.get((nr, nc))
            if nb and (nb.get("land_use") or "").startswith("residential_"):
                findings["solar_farm_residential_adjacency"].append(
                    f"SOLAR_FARM ({r:2d},{c:2d}) 4-adj to "
                    f"{nb['land_use'].upper()} ({nr:2d},{nc:2d})"
                )
                break

    # Render markdown.
    lines: List[str] = []
    lines.append("# A27 -- placement realism audit")
    lines.append("")
    lines.append(f"Source: `{GEOJSON.name}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Issue count |")
    lines.append("|---|---:|")
    keys = [
        ("blue_space_road_adjacency", "BLUE_SPACE 4-adj to ROAD"),
        ("religious_industrial_adjacency", "RELIGIOUS 8-adj to LIGHT_INDUSTRY/WAREHOUSE"),
        ("amenity_no_road_8nbr", "Amenity (school/clinic/etc.) with no ROAD 8-neighbour"),
        ("solar_farm_residential_adjacency", "SOLAR_FARM 4-adj to RESIDENTIAL"),
    ]
    for key, label in keys:
        lines.append(f"| {label} | {len(findings[key])} |")
    lines.append("")
    for key, label in keys:
        lines.append(f"## {label}")
        lines.append("")
        items = findings[key]
        if not items:
            lines.append("(none)")
        else:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines))
    print(f"wrote {OUT_MD}")
    print()
    print("\n".join(lines[:15]))
    print(f"... (full report at {OUT_MD})")


if __name__ == "__main__":
    main()
