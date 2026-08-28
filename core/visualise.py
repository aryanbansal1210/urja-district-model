"""Render a Grid as an SVG image.

SVG is used (not matplotlib) because:
  * No installation needed — every browser opens it.
  * Vector format — scales without pixelation, prints cleanly.
  * Easy to embed in the thesis or a web 3D viewer later.

The output is a colour-coded top-down master plan with a legend on the right.
North is up. The grid origin (row 0, col 0) sits at the bottom-left to match
the convention in `core.grid`.

Usage:
    from core.visualise import to_svg
    svg_text = to_svg(grid, title="chandigarh_sector")
    with open("layout.svg", "w") as f:
        f.write(svg_text)
"""

from __future__ import annotations

from html import escape
from typing import Optional

from .grid import Grid
from .land_use import LAND_USE_COLOURS, LandUse


# ---------------------------------------------------------------------------
# Layout constants for the SVG
# ---------------------------------------------------------------------------
CELL_PX: int = 18                  # pixels per grid cell
MARGIN_PX: int = 32                # outer margin
LEGEND_WIDTH_PX: int = 220         # space for the legend
TITLE_HEIGHT_PX: int = 36
FOOTER_HEIGHT_PX: int = 28
GRID_STROKE: str = "#222"          # darker outline between cells
GRID_STROKE_WIDTH: float = 0.4
LEGEND_SWATCH_PX: int = 14
FONT_FAMILY: str = "Helvetica, Arial, sans-serif"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def to_svg(grid: Grid, title: Optional[str] = None) -> str:
    """Render the grid as a self-contained SVG string.

    Parameters
    ----------
    grid : Grid
        The populated grid to render.
    title : str, optional
        Heading shown above the grid.

    Returns
    -------
    str
        Full SVG document text. Write directly to a `.svg` file.
    """
    grid_w = grid.n_cols * CELL_PX
    grid_h = grid.n_rows * CELL_PX

    total_w = MARGIN_PX * 2 + grid_w + LEGEND_WIDTH_PX
    total_h = MARGIN_PX * 2 + grid_h + TITLE_HEIGHT_PX + FOOTER_HEIGHT_PX

    parts = []
    parts.append(_svg_header(total_w, total_h))
    parts.append(_title_block(title or "Master plan", total_w))
    parts.append(_grid_block(grid, x0=MARGIN_PX, y0=MARGIN_PX + TITLE_HEIGHT_PX))
    parts.append(_legend_block(
        x0=MARGIN_PX + grid_w + 24,
        y0=MARGIN_PX + TITLE_HEIGHT_PX,
        present_uses=_present_uses(grid),
    ))
    parts.append(_footer_block(grid, total_w, total_h))
    parts.append("</svg>\n")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------
def _svg_header(w: int, h: int) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'font-family="{FONT_FAMILY}">\n'
        f'<rect width="100%" height="100%" fill="#fafafa"/>\n'
    )


def _title_block(title: str, total_w: int) -> str:
    return (
        f'<text x="{total_w / 2}" y="{MARGIN_PX + 18}" '
        f'text-anchor="middle" font-size="18" font-weight="600" fill="#222">'
        f'{escape(title)}</text>\n'
    )


def _grid_block(grid: Grid, x0: int, y0: int) -> str:
    """Render the grid as coloured rectangles. Row 0 is at the BOTTOM."""
    out = ['<g shape-rendering="crispEdges">\n']
    for cell in grid.all_cells():
        # SVG y grows downward, so flip rows so row 0 is at the bottom.
        x = x0 + cell.col * CELL_PX
        y = y0 + (grid.n_rows - 1 - cell.row) * CELL_PX
        colour = LAND_USE_COLOURS.get(cell.land_use, "#dddddd")
        out.append(
            f'<rect x="{x}" y="{y}" width="{CELL_PX}" height="{CELL_PX}" '
            f'fill="{colour}" stroke="{GRID_STROKE}" '
            f'stroke-width="{GRID_STROKE_WIDTH}"/>\n'
        )
    # outer frame
    grid_w = grid.n_cols * CELL_PX
    grid_h = grid.n_rows * CELL_PX
    out.append(
        f'<rect x="{x0}" y="{y0}" width="{grid_w}" height="{grid_h}" '
        f'fill="none" stroke="#111" stroke-width="1"/>\n'
    )
    # north arrow + scale
    out.append(_compass(x0 - 12, y0 - 8))
    out.append(_scale_bar(grid, x0, y0 + grid_h + 6))
    out.append('</g>\n')
    return "".join(out)


def _compass(x: float, y: float) -> str:
    """A small N arrow above the grid."""
    return (
        f'<g font-size="11" fill="#444">'
        f'<text x="{x}" y="{y - 8}" text-anchor="middle">N</text>'
        f'<polygon points="{x - 4},{y} {x + 4},{y} {x},{y - 6}" '
        f'fill="#444"/></g>\n'
    )


def _scale_bar(grid: Grid, x0: float, y0: float) -> str:
    """1 km scale bar."""
    cells_per_km = int(round(1000.0 / grid.cell_size_m))   # 5 cells for 200 m grid
    bar_px = cells_per_km * CELL_PX
    return (
        f'<g font-size="10" fill="#444">'
        f'<rect x="{x0}" y="{y0}" width="{bar_px}" height="3" fill="#444"/>'
        f'<text x="{x0 + bar_px / 2}" y="{y0 + 14}" text-anchor="middle">'
        f'1 km</text></g>\n'
    )


def _present_uses(grid: Grid) -> list:
    """Return land-uses that actually appear in the grid, ordered by
    LAND_USE_COLOURS' definition order."""
    seen = set(c.land_use for c in grid.all_cells())
    return [lu for lu in LAND_USE_COLOURS if lu in seen]


def _legend_block(x0: float, y0: float, present_uses: list) -> str:
    """Right-side legend with one row per land-use that appears in the grid."""
    out = [f'<g font-size="11" fill="#222">\n']
    out.append(
        f'<text x="{x0}" y="{y0 - 4}" font-weight="600">Land use</text>\n'
    )
    row_height = LEGEND_SWATCH_PX + 6
    for i, lu in enumerate(present_uses):
        ry = y0 + 12 + i * row_height
        colour = LAND_USE_COLOURS[lu]
        out.append(
            f'<rect x="{x0}" y="{ry}" width="{LEGEND_SWATCH_PX}" '
            f'height="{LEGEND_SWATCH_PX}" fill="{colour}" '
            f'stroke="#222" stroke-width="0.5"/>\n'
        )
        out.append(
            f'<text x="{x0 + LEGEND_SWATCH_PX + 6}" '
            f'y="{ry + LEGEND_SWATCH_PX - 3}">'
            f'{escape(lu.value.replace("_", " "))}</text>\n'
        )
    out.append("</g>\n")
    return "".join(out)


def _footer_block(grid: Grid, total_w: int, total_h: int) -> str:
    """Footnote with grid spec + permeability reminder."""
    foot1 = (f"{grid.n_rows}x{grid.n_cols} cells of "
             f"{grid.cell_size_m:.0f} m  -  "
             f"district {grid.total_area_m2 / 1e6:.1f} km^2")
    foot2 = ("black cell borders are visualisation only; "
             "pedestrians can pass between any adjacent cells.")
    return (
        f'<text x="{MARGIN_PX}" y="{total_h - MARGIN_PX / 2 - 12}" '
        f'font-size="11" fill="#666">{escape(foot1)}</text>\n'
        f'<text x="{MARGIN_PX}" y="{total_h - MARGIN_PX / 2 + 4}" '
        f'font-size="10" fill="#888" font-style="italic">'
        f'{escape(foot2)}</text>\n'
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from .grid import make_thesis_grid

    g = make_thesis_grid()
    g.at(0, 0).land_use = LandUse.RESIDENTIAL_LOW
    g.at(12, 12).land_use = LandUse.SHOPPING_CENTRE
    g.at(24, 24).land_use = LandUse.LIGHT_INDUSTRY
    txt = to_svg(g, title="visualiser smoke test")
    out = "_visualise_smoke.svg"
    with open(out, "w") as f:
        f.write(txt)
    print(f"wrote {out} ({len(txt)} chars)")
