"""A20 — baseline-archetype hard-constraint audit.

: before thesis-comparison plots
compare optimised_sa against the 4 baseline archetypes, confirm each
baseline is a *fair* comparison rather than a strawman that fails
hard constraints by construction. This script:

  1. Reconstructs each archetype's grid (chandigarh_sector, dispersed_low,
     compact_centre, radial) from `core/seeds.py` via the same path that
     `core.export_3d` uses.
  2. Runs ALL hard constraints on each.
  3. Reports a pass / fail / gap table per archetype.

Write to stdout in a markdown-friendly table so it can be pasted into
the thesis discussion chapter or §13 entry.

Run:
    /c/Users/the author/anaconda3/envs/sef-python-demo/python.exe -m scripts.audit_baselines
"""
from __future__ import annotations

import sys
from typing import Dict, List

from core.config import load_config
from core.demographics import load_demographics, load_demand_norms
from layout.constraints import check_hard_constraints, HARD_CONSTRAINT_NAMES
from layout.generator import generate


BASELINE_NAMES = ("chandigarh_sector", "dispersed_low",
                   "compact_centre", "radial", "optimised_sa")


def _audit_one(layout_name: str, grid) -> Dict[str, Dict[str, float]]:
    results = check_hard_constraints(grid)
    out: Dict[str, Dict[str, float]] = {}
    for r in results:
        out[r.name] = {"passes": float(r.passes), "gap": r.gap,
                        "message": r.message}
    return out


def main() -> None:
    cfg = load_config()

    per_layout: Dict[str, Dict[str, Dict[str, float]]] = {}
    for name in BASELINE_NAMES:
        if name == "optimised_sa":
            # Read from disk; the optimiser run is too expensive for the audit.
            from energy.network import grid_from_geojson
            from pathlib import Path
            geo_path = Path(__file__).resolve().parent.parent / "outputs" / "geojson3d" / "optimised_sa.geojson"
            grid, _ = grid_from_geojson(geo_path)
        else:
            grid = generate(name)
        per_layout[name] = _audit_one(name, grid)

    # Build the table.
    constraint_names = sorted(HARD_CONSTRAINT_NAMES)
    print()
    print("# A20 baseline-archetype hard-constraint audit")
    print()
    print("Pass-rate per archetype:")
    print()
    header = "| constraint | " + " | ".join(BASELINE_NAMES) + " |"
    sep = "|" + "---|" * (1 + len(BASELINE_NAMES))
    print(header)
    print(sep)
    for c_name in constraint_names:
        row = f"| {c_name} |"
        for layout in BASELINE_NAMES:
            r = per_layout[layout].get(c_name)
            if r is None:
                row += " - |"
            else:
                passes = bool(r["passes"])
                gap = r["gap"]
                mark = "[OK]" if passes else f"[FAIL gap={gap:.2f}]"
                row += f" {mark} |"
        print(row)

    # Summary line per archetype.
    print()
    print("Summary:")
    for layout in BASELINE_NAMES:
        n_pass = sum(1 for c in constraint_names
                     if per_layout[layout].get(c, {}).get("passes", 0))
        total = len(constraint_names)
        print(f"  {layout:20s}  {n_pass:2d} / {total:2d} hard constraints pass")


if __name__ == "__main__":
    main()
