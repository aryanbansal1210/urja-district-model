""" pre-anneal lock tests.

Direct-runner style: ``python tests/test_f6_locks.py``. Exercises
layout/f6_locks.py on the REAL seed-grid sequence (locked zones -> sector
grid -> canal -> parks -> locks) - the exact order export_3d will run
at the anneal. No solves; seconds.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from core.grid import make_thesis_grid                      # noqa: E402
from core.land_use import LandUse                           # noqa: E402
from layout.locked_zones import apply_locked_zones          # noqa: E402
from layout.sector_structure import apply_sector_grid       # noqa: E402
from layout.canal_corridor import apply_canal_corridor      # noqa: E402
from layout.park_structure import apply_locked_parks        # noqa: E402
from layout.f6_locks import apply_f6_locks                  # noqa: E402


def _seed():
    g = make_thesis_grid()
    apply_locked_zones(g, solar_cells=200)
    apply_sector_grid(g, sector_size_cells=8)
    apply_canal_corridor(g)
    apply_locked_parks(g)
    return g


def _locked_before(g):
    return {(c.row, c.col): (c.land_use, c.amenity_subtype)
            for c in g.all_cells() if c.locked}


def test_counts_and_determinism() -> None:
    g1, g2 = _seed(), _seed()
    o1, o2 = apply_f6_locks(g1), apply_f6_locks(g2)
    assert o1 == o2, (o1, o2)
    assert o1["highstreet_locked"] == 6, o1
    assert o1["hospital_campus"] == 4, o1
    assert o1["ring_2042"] == 50 and o1["ring_2055"] == 50, o1
    assert o1["agri_band_locked"] == 14, o1


def test_never_overwrites_existing_locks() -> None:
    g = _seed()
    before = _locked_before(g)
    apply_f6_locks(g)
    for (rc, (lu, sub)) in before.items():
        cell = g.at(*rc)
        assert cell.land_use == lu, rc
        assert cell.amenity_subtype == sub, rc


def test_highstreet_is_one_bridged_chain_on_the_spine() -> None:
    g = _seed()
    apply_f6_locks(g)
    hs = sorted((c.row, c.col) for c in g.all_cells()
                if c.land_use == LandUse.RETAIL_HIGHSTREET and c.locked)
    rows = {r for r, _ in hs}
    assert rows == {g.n_rows // 2 - 1}, rows          # the spine row, south side
    cols = [c for _, c in hs]
    # contiguous up to single-road bridges: gaps of exactly the arterial col
    gaps = [b - a for a, b in zip(cols, cols[1:])]
    assert all(gap in (1, 2) for gap in gaps), cols   # 2 = one road bridged
    assert len(hs) == 6, hs


def test_hospital_campus_fronts_the_skeleton() -> None:
    from layout.locked_zones import arterial_rows_cols
    g = _seed()
    apply_f6_locks(g)
    campus = sorted((c.row, c.col) for c in g.all_cells()
                    if c.amenity_subtype == "hospital_campus")
    assert len(campus) == 4, campus
    rows = sorted({r for r, _ in campus})
    cols = sorted({c for _, c in campus})
    assert len(rows) == 2 and rows[1] == rows[0] + 1, campus   # 2x2 block
    assert len(cols) == 2 and cols[1] == cols[0] + 1, campus
    art_rows, art_cols = arterial_rows_cols(g)
    touches = (rows[0] - 1 in art_rows or rows[1] + 1 in art_rows
               or cols[0] - 1 in art_cols or cols[1] + 1 in art_cols)
    assert touches, (campus, art_rows, art_cols)
    for rc in campus:
        assert g.at(*rc).land_use == LandUse.HEALTHCARE, rc


def test_ring_is_bridged_contiguous_with_farm() -> None:
    g = _seed()
    apply_f6_locks(g)
    farm = {(c.row, c.col) for c in g.all_cells()
            if c.land_use == LandUse.SOLAR_FARM}
    ring = [(c.row, c.col) for c in g.all_cells()
            if (c.amenity_subtype or "").startswith("solar_expansion")]
    rset = set(ring)
    for (r, c) in ring:
        cell = g.at(r, c)
        assert cell.locked and cell.land_use == LandUse.OPEN_SPACE, (r, c)
        ok = False
        for (nr, nc) in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if (nr, nc) in farm or (nr, nc) in rset:
                ok = True
                break
            if (0 <= nr < g.n_rows and 0 <= nc < g.n_cols
                    and g.at(nr, nc).land_use == LandUse.ROAD):
                fr, fc = 2 * nr - r, 2 * nc - c     # the far side of the bridge
                if (fr, fc) in farm or (fr, fc) in rset:
                    ok = True
                    break
        assert ok, ("orphan ring cell", r, c)


def test_agri_band_single_run_inside_canal() -> None:
    g = _seed()
    apply_f6_locks(g)
    band = sorted((c.row, c.col) for c in g.all_cells()
                  if c.amenity_subtype == "agri_belt" and c.locked)
    assert len(band) == 14, band
    rows = {r for r, _ in band}
    assert rows <= {g.n_rows - 3, g.n_rows - 4, g.n_rows - 5}, rows
    cols = sorted(c for _, c in band)
    gaps = [b - a for a, b in zip(cols, cols[1:])]
    assert all(gap in (1, 2) for gap in gaps), cols   # bridged single run


def main() -> None:
    import time
    fns = [test_counts_and_determinism,
           test_never_overwrites_existing_locks,
           test_highstreet_is_one_bridged_chain_on_the_spine,
           test_hospital_campus_fronts_the_skeleton,
           test_ring_is_bridged_contiguous_with_farm,
           test_agri_band_single_run_inside_canal]
    n_pass = n_fail = 0
    for fn in fns:
        t0 = time.time()
        try:
            fn()
            n_pass += 1
            print(f"PASS  {fn.__name__} ({time.time()-t0:.1f}s)", flush=True)
        except Exception as exc:  # noqa: BLE001
            n_fail += 1
            print(f"FAIL  {fn.__name__} ({time.time()-t0:.1f}s)\n"
                  f"      {type(exc).__name__}: {exc}", flush=True)
    print(f"\nTOTAL pass {n_pass} fail {n_fail}")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
