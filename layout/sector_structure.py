"""Chandigarh-style SECTOR grid (Stage-, the author-ratified).

the author's direction: the town should adopt Chandigarh's sector structure -
self-contained neighbourhood sectors (school / park / shops inside), defined
by a COLLECTOR-road grid laid between the primary arterials. lays this
sector grid (pulling the sector-defining collectors forward from; then
adds the finer local access streets + per-class widths + the bike/foot layer.

The sector grid is laid + LOCKED before the anneal (exactly like the arterial
skeleton in locked_zones), so the SA arranges land use WITHIN each sector and
can never dissolve a sector boundary. A "sector" is one arterial/collector
super-cell block; at sector_size_cells = 8 on the 50 m... (100 m) 50x50 grid
that is ~0.64 km2, close to a real Chandigarh sector (0.8 x 1.2 km).

`sector_size_cells` is a PARAMETER (the sector-size sweep tries a few and
the model keeps the one with the best layout+energy score - the author: "the model
should choose what is optimal"). The single-bus energy LP is spatially blind,
so the responsive terms are the collector-road extent (streetlights + capex)
and mutual roof-shading; the layout metrics (walkability / compactness /
catchment) carry the rest.

Collectors are stamped at a regular stride BETWEEN the arterials, skipping:
  * arterial rows/cols (already primary roads),
  * the locked SOLAR reserve (a collector must not bisect the solar field),
so the result is a clean nested grid: arterials (primary) + collectors
(secondary) enclosing the sectors.
"""
from __future__ import annotations

from typing import Optional, Set, Tuple

from core.grid import Grid
from core.land_use import LandUse

from .locked_zones import arterial_rows_cols

CellId = Tuple[int, int]


def sector_collector_lines(grid: Grid, sector_size_cells: int
                           ) -> Tuple[Set[int], Set[int]]:
    """Return the (rows, cols) that carry a collector road for this sector size.

    STAGE- revision: collectors are placed EVENLY WITHIN each
    arterial-to-arterial band, not on a global stride from row 0. The global
    stride put a collector at 24 next to the arterial at 25 (and 48 next to
    49), creating unusable 100 m sliver "sectors". Per band: split the band
    into round(band/sector_size) equal sub-bands and lay a collector at each
    internal split, so every sector is ~sector_size_cells wide and no sector
    is thinner than ~sector_size/2. Excludes the arterial lines themselves.
    """
    art_rows, art_cols = arterial_rows_cols(grid)
    s = max(2, int(sector_size_cells))

    def _lines(n: int, art: Set[int]) -> Set[int]:
        bounds = sorted(art | {0, n - 1})
        out: Set[int] = set()
        for lo, hi in zip(bounds, bounds[1:]):
            band = hi - lo
            n_sub = max(1, round(band / s))
            for i in range(1, n_sub):
                k = lo + round(i * band / n_sub)
                if k not in art and lo < k < hi:
                    out.add(k)
        return out

    return _lines(grid.n_rows, art_rows), _lines(grid.n_cols, art_cols)


def apply_sector_grid(grid: Grid, sector_size_cells: int = 8,
                      lock: bool = True) -> Set[CellId]:
    """Stamp + (optionally) lock the collector-road sector grid. Mutates grid.

    A collector cell is set to ROAD and locked. Cells inside the locked SOLAR
    reserve are skipped (never bisect the solar field). Cells already ROAD
    (arterials) are left as-is. Returns the set of collector (row, col) ids.

    Returns
    -------
    Set[CellId]
        The collector-road cell ids added by this pass.
    """
    coll_rows, coll_cols = sector_collector_lines(grid, sector_size_cells)
    added: Set[CellId] = set()

    def _stamp(r: int, c: int) -> None:
        cell = grid.at(r, c)
        # never carve a collector through the locked solar reserve or the
        # locked canal corridor: the canal culverts under road crossings,
        # but a locked BLUE cell must not be overwritten if it exists already)
        if cell.locked and cell.land_use in (LandUse.SOLAR_FARM,
                                             LandUse.BLUE_SPACE):
            return
        if cell.land_use != LandUse.ROAD:
            cell.land_use = LandUse.ROAD
            cell.height_m = 0.0
            cell.height_tier = None
            cell.albedo = 0.18
            cell.vegetation_fraction = 0.10
        if lock:
            cell.locked = True
        added.add((r, c))

    for r in coll_rows:
        for c in range(grid.n_cols):
            _stamp(r, c)
    for c in coll_cols:
        for r in range(grid.n_rows):
            _stamp(r, c)
    return added


def sector_id_of(grid: Grid, row: int, col: int,
                 sector_size_cells: int = 8) -> Tuple[int, int]:
    """Return the (sector_row, sector_col) index a cell falls in, using the
    arterial + collector lines as sector boundaries. Cheap integer bucketing
    for the income-block / compactness metrics + viewer hover."""
    art_rows, art_cols = arterial_rows_cols(grid)
    coll_rows, coll_cols = sector_collector_lines(grid, sector_size_cells)
    row_bounds = sorted(art_rows | coll_rows | {0, grid.n_rows})
    col_bounds = sorted(art_cols | coll_cols | {0, grid.n_cols})

    def _bucket(v: int, bounds) -> int:
        b = 0
        for i, x in enumerate(bounds):
            if v >= x:
                b = i
        return b

    return _bucket(row, row_bounds), _bucket(col, col_bounds)


if __name__ == "__main__":
    from core.grid import make_thesis_grid
    from layout.locked_zones import apply_locked_zones

    for size in (5, 8, 10):
        g = make_thesis_grid()
        apply_locked_zones(g, solar_cells=350)
        coll = apply_sector_grid(g, sector_size_cells=size)
        roads = sum(1 for c in g.all_cells() if c.land_use == LandUse.ROAD)
        n_sec_r = len({sector_id_of(g, r, 0, size)[0] for r in range(g.n_rows)})
        n_sec_c = len({sector_id_of(g, 0, c, size)[1] for c in range(g.n_cols)})
        print(f"sector_size={size:2d} cells ({size/10:.1f} km): "
              f"+{len(coll)} collector cells, {roads} total road "
              f"({roads/g.total_cells:.1%}), ~{n_sec_r}x{n_sec_c} sectors")
