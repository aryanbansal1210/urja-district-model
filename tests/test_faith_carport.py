"""Item 2 + Item 3 unit tests (faith assignment + carport siting).

Fast unit tests for the layout helpers. No LP solve;
no GeoJSON read. Just exercises the deterministic algorithms directly
on synthetic grids.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.grid import Grid  # noqa: E402
from core.land_use import LandUse  # noqa: E402
from layout.faith_assignment import (  # noqa: E402
    PUNJAB_CENSUS_2011_SHARES,
    assign_faiths_to_religious_cells,
    compute_faith_quotas,
)
from layout.carport_siting import (  # noqa: E402
    DEFAULT_ANCHOR_LAND_USES,
    carport_kwp_for_cell,
    place_carports,
)


# -------- compute_faith_quotas -------------------------------------------
def test_compute_faith_quotas_zero_cells_returns_zeros() -> None:
    q = compute_faith_quotas(0)
    assert q == {"sikh": 0, "hindu": 0, "muslim": 0, "christian": 0}


def test_compute_faith_quotas_one_cell_floors_minority() -> None:
    # Punjab Census shares are sikh ~58%, hindu ~38%, muslim ~2%, christian ~1%.
    # With a min-1 floor for muslim+christian and only 1 cell, the floor wins
    # (alphabetical tie-break would pick christian first).
    q = compute_faith_quotas(1)
    assert sum(q.values()) == 1
    # muslim or christian must claim the single cell (floor priority).
    assert q["muslim"] == 1 or q["christian"] == 1


def test_compute_faith_quotas_two_cells_one_each_minority() -> None:
    q = compute_faith_quotas(2)
    assert sum(q.values()) == 2
    assert q["muslim"] == 1 and q["christian"] == 1


def test_compute_faith_quotas_23_cells_matches_sa_layout() -> None:
    """optimised_sa has 23 RELIGIOUS cells; expected 13/8/1/1."""
    q = compute_faith_quotas(23)
    assert q["sikh"] == 13, q
    assert q["hindu"] == 8, q
    assert q["muslim"] == 1, q
    assert q["christian"] == 1, q
    assert sum(q.values()) == 23


def test_compute_faith_quotas_sum_invariant_across_sizes() -> None:
    for n in [3, 5, 10, 20, 50, 100, 500]:
        q = compute_faith_quotas(n)
        assert sum(q.values()) == n, (n, q)
        # Floors must hold.
        assert q["muslim"] >= 1
        assert q["christian"] >= 1


# -------- assign_faiths_to_religious_cells -------------------------------
def _make_grid_with_religious(n_religious: int) -> Grid:
    g = Grid.empty(n_rows=10, n_cols=10, cell_size_m=200.0)
    placed = 0
    for r in range(g.n_rows):
        for c in range(g.n_cols):
            if placed >= n_religious:
                break
            g.at(r, c).land_use = LandUse.RELIGIOUS
            placed += 1
    return g


def test_assign_faiths_deterministic_repeatable() -> None:
    g1 = _make_grid_with_religious(23)
    q1 = assign_faiths_to_religious_cells(g1)
    g2 = _make_grid_with_religious(23)
    q2 = assign_faiths_to_religious_cells(g2)
    assert q1 == q2
    faiths1 = [c.faith for c in g1.all_cells() if c.land_use == LandUse.RELIGIOUS]
    faiths2 = [c.faith for c in g2.all_cells() if c.land_use == LandUse.RELIGIOUS]
    assert faiths1 == faiths2


def test_assign_faiths_only_touches_religious_cells() -> None:
    g = _make_grid_with_religious(5)
    assign_faiths_to_religious_cells(g)
    for c in g.all_cells():
        if c.land_use == LandUse.RELIGIOUS:
            assert c.faith in {"sikh", "hindu", "muslim", "christian"}, c.faith
        else:
            assert c.faith is None, (c.row, c.col, c.faith)


def test_assign_faiths_quotas_match_compute_quotas() -> None:
    g = _make_grid_with_religious(23)
    q = assign_faiths_to_religious_cells(g)
    actual = {f: 0 for f in PUNJAB_CENSUS_2011_SHARES}
    for c in g.all_cells():
        if c.land_use == LandUse.RELIGIOUS and c.faith:
            actual[c.faith] += 1
    assert actual == q


# -------- carport siting --------------------------------------------------
def _make_grid_with_anchors_and_eligible() -> Grid:
    """10×10 grid with light_industry anchors in each quadrant +
    surrounding road/office cells (eligible carport hosts)."""
    g = Grid.empty(n_rows=10, n_cols=10, cell_size_m=200.0)
    # Drop one anchor per quadrant; surround with roads.
    anchor_positions = [(2, 2), (2, 7), (7, 2), (7, 7)]
    for (r, c) in anchor_positions:
        g.at(r, c).land_use = LandUse.LIGHT_INDUSTRY
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                rr, cc = r + dr, c + dc
                if 0 <= rr < g.n_rows and 0 <= cc < g.n_cols:
                    if g.at(rr, cc).land_use == LandUse.OPEN_SPACE:
                        g.at(rr, cc).land_use = LandUse.ROAD
    return g


def test_place_carports_balanced_across_quadrants() -> None:
    g = _make_grid_with_anchors_and_eligible()
    chosen = place_carports(g, target_per_quadrant=4, radius_cells=2)
    counts = {q: len(v) for q, v in chosen.items()}
    # Every quadrant has at least 1 site (we placed anchors in all 4).
    for q in range(4):
        assert counts.get(q, 0) >= 1, (q, counts)


def test_place_carports_no_anchors_returns_empty() -> None:
    g = Grid.empty(n_rows=10, n_cols=10, cell_size_m=200.0)
    # Make road cells but no anchors.
    for r in range(g.n_rows):
        for c in range(g.n_cols):
            g.at(r, c).land_use = LandUse.ROAD
    chosen = place_carports(g, target_per_quadrant=4, radius_cells=2)
    assert all(len(v) == 0 for v in chosen.values())


def test_place_carports_idempotent_when_re_run() -> None:
    g = _make_grid_with_anchors_and_eligible()
    c1 = place_carports(g, target_per_quadrant=4, radius_cells=2)
    sites1 = sorted((r, c) for cell in g.all_cells()
                     if cell.is_carport_site for (r, c) in [(cell.row, cell.col)])
    c2 = place_carports(g, target_per_quadrant=4, radius_cells=2)
    sites2 = sorted((r, c) for cell in g.all_cells()
                     if cell.is_carport_site for (r, c) in [(cell.row, cell.col)])
    assert c1 == c2 and sites1 == sites2


def test_carport_kwp_for_cell_by_land_use() -> None:
    g = Grid.empty(n_rows=2, n_cols=2, cell_size_m=200.0)
    for cell in g.all_cells():
        cell.land_use = LandUse.SHOPPING_CENTRE
    sample = next(iter(g.all_cells()))
    assert carport_kwp_for_cell(sample) == 1500.0
    sample.land_use = LandUse.WAREHOUSE
    assert carport_kwp_for_cell(sample) == 1200.0
    sample.land_use = LandUse.HEALTHCARE
    assert carport_kwp_for_cell(sample) == 1000.0
    sample.land_use = LandUse.RESIDENTIAL_HIGH
    assert carport_kwp_for_cell(sample) == 600.0
    # carports now live on dedicated PARKING_LOT cells (a full 4-ha
    # surface lot under PV canopy ~2,000 kWp). ROAD is no longer a carport host
    # (removed) so it falls through to the generic default (1000).
    sample.land_use = LandUse.PARKING_LOT
    assert carport_kwp_for_cell(sample) == 2000.0
    sample.land_use = LandUse.ROAD
    assert carport_kwp_for_cell(sample) == 1000.0


# -------- segment-aware streetlights (Part 4,) ----------------
def _grid_with_road_spur() -> Grid:
    """10x10 grid: a built block at rows 5-6 / cols 4-5, with a road SPUR on
    row 4 running from col 4 (abutting the block below it) out to col 9 (a long
    peripheral cul-de-sac). The road never overwrites the built block."""
    g = Grid.empty(n_rows=10, n_cols=10, cell_size_m=200.0)
    for c in g.all_cells():
        c.land_use = LandUse.OPEN_SPACE
    # central built block (rows 5-6, cols 4-5) — NOT on the road row
    for r in range(5, 7):
        for cc in range(4, 6):
            g.at(r, cc).land_use = LandUse.RESIDENTIAL_MID
    # road spur on row 4: (4,4) abuts the block at (5,4) below it (grid-edge);
    # the run extends out to (4,9) on the periphery.
    for cc in range(4, 10):
        g.at(4, cc).land_use = LandUse.ROAD
    return g


def test_streetlight_segments_coherent_and_tagged() -> None:
    """Each streetlight segment is single-type (decides together) + tagged."""
    from layout.street_furniture import place_street_furniture
    g = _grid_with_road_spur()
    s = place_street_furniture(g)
    assert s["total_roads"] == 6  # road spur (4,4)..(4,9)
    # every ROAD cell gets a type + segment id + reason
    roads = [c for c in g.all_cells() if c.land_use == LandUse.ROAD]
    assert all(c.streetlight_type in ("grid", "solar") for c in roads)
    assert all(c.streetlight_segment_id is not None for c in roads)
    assert all(c.streetlight_reason for c in roads)
    # no mixed-type segment
    seg_types: dict = {}
    for c in roads:
        seg_types.setdefault(c.streetlight_segment_id, set()).add(c.streetlight_type)
    assert all(len(t) == 1 for t in seg_types.values()), seg_types


def test_streetlight_grid_edge_is_grid() -> None:
    """Road cells adjacent to built (mains there) are grid (no trench)."""
    from layout.street_furniture import place_street_furniture
    g = _grid_with_road_spur()
    place_street_furniture(g)
    # (4,4) abuts the built block at (5,4) below it -> grid-edge -> grid
    assert g.at(4, 4).streetlight_type == "grid"
    assert g.at(4, 4).streetlight_segment_id == 0  # the grid-edge backbone


def test_streetlight_far_spur_goes_solar() -> None:
    """The far end of a long peripheral spur goes solar (cable run > premium)."""
    from layout.street_furniture import place_street_furniture
    g = _grid_with_road_spur()
    place_street_furniture(g)
    # the spur tip at (4,9) is far from built -> its segment should be solar
    assert g.at(4, 9).streetlight_type == "solar"


# -------- Self-test entry point ------------------------------------------
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
            if k.startswith("test_") and callable(v)]
    fails = []
    for fn in fns:
        try:
            fn()
            print(f"  OK  {fn.__name__}")
        except Exception as e:
            print(f"  X   {fn.__name__}: {e}")
            fails.append(fn.__name__)
    if fails:
        print(f"\n{len(fails)} tests failed: {fails}")
        sys.exit(1)
    print(f"\nAll {len(fns)} faith + carport tests passed.")
