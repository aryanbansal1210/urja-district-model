"""Render 2D plan views of layouts FROM THE FROZEN GEOJSON.

The 2D SVGs in outputs/geojson/ were written on by the same run
that produced the layout. Everything since - the car-park swap, the
 solar release, the solar-thermal re-pin - reached the geojson but
never the SVG, so the picture is five weeks behind the town.

This regenerates them by READING the frozen geojson and rendering it. It does
NOT rebuild the grid through `_grid_for_layout`, which would re-run the
generation chain: on today's config that chain starts from a different seed
cost and would produce a different town. Reading the artefact is the only safe
way to draw the town that the rest of the thesis reports.

    python scripts/render_2d_layouts.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import json                                       # noqa: E402

from core.land_use import LandUse                  # noqa: E402
from core.visualise import to_svg                 # noqa: E402
from energy.network import grid_from_geojson      # noqa: E402

OUT = os.path.join(ROOT, "outputs", "geojson")
WANT = [("optimised_sa", "Planned integrated district"),
        ("zirakpur_ribbon", "Baseline 2, unplanned conventional")]


def _show_released_reserve(grid, src):
    """Draw the released 2030 solar reserve AS generation land.

    THE PLAN VIEW WAS UNDERSTATING THE SOLAR FARM BY A THIRD, and it took a
    complaint that "the farm looks smaller than it is" to find it.

    The generation reserve is 301 cells. Only 201 of them carry
    `land_use = solar_farm`; the other 100 are `open_space` carrying
    `amenity_subtype = solar_expansion_2030` - the ring released into
    the first period. `core.visualise.to_svg` colours strictly by land use and
    knows nothing about the subtype, so it painted those 100 cells green, and
    the viewer's base colouring does the same (`ring_colour #7CC470`).

    The LP does not agree with that picture: it installs 214,914 kWp of
    ground-mounted capacity in 2030, which is the whole 301 ha in year one.
    Drawing a third of the operating solar farm as parkland is therefore wrong
    in the direction that matters, so the released cells are retyped for
    DISPLAY here.

    In memory only. The geojson on disk is never written by this script.
    """
    with open(src, encoding="utf-8") as fh:
        gj = json.load(fh)
    ring = set()
    for f in gj["features"]:
        pr = f["properties"]
        if str(pr.get("amenity_subtype") or "").startswith("solar_expansion_"):
            if pr.get("row") is not None:
                ring.add((pr["row"], pr["col"]))
    n = 0
    for cell in grid.all_cells():
        if (cell.row, cell.col) in ring and cell.land_use != LandUse.SOLAR_FARM:
            cell.land_use = LandUse.SOLAR_FARM
            n += 1
    return n


def main() -> int:
    for name, title in WANT:
        src = os.path.join(ROOT, "outputs", "geojson3d", name + ".geojson")
        if not os.path.exists(src):
            print("  %-18s MISSING (%s)" % (name, src))
            continue
        grid, _ = grid_from_geojson(src)
        moved = _show_released_reserve(grid, src)
        if moved:
            print("  %-18s +%d released reserve cells drawn as generation land"
                  % (name, moved))
        svg = to_svg(grid, title=title)
        dst = os.path.join(OUT, name + ".svg")
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(svg)
        cells = sum(1 for _ in grid.all_cells())
        print("  %-18s %d x %d, %d cells -> %s (%.0f KB)"
              % (name, grid.n_rows, grid.n_cols, cells,
                 os.path.basename(dst), len(svg) / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
