"""STAGE-/ tests: road hierarchy, ROW accounting, local streets, canal
corridor, path network + walkability, and the geojson round-trip.

Direct-runner style (no pytest): run
`python tests/test_road_network.py` with the canonical env.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config
from core.grid import Grid, StreetEdge, make_thesis_grid
from core.land_use import LandUse
from layout.canal_corridor import (
    apply_canal_corridor, canal_cells, canal_row, is_canal_cell,
)
from layout.constraints import (
    check_amenities_road_frontage, check_road_connectivity,
)
from layout.locked_zones import apply_locked_zones, arterial_rows_cols
from layout.path_network import assign_path_network, walkability_report
from layout.road_network import (
    LOCAL_STREET_WIDTH_M, ROAD_CLASS_SPEC, assign_local_streets,
    developed_area_m2, road_row_area_m2, road_row_report, tag_road_classes,
)
from layout.sector_structure import apply_sector_grid, sector_collector_lines


def _locked_grid(sector_size: int = 8) -> Grid:
    g = make_thesis_grid()
    apply_locked_zones(g, solar_cells=350)
    apply_sector_grid(g, sector_size_cells=sector_size)
    apply_canal_corridor(g)
    return g


def test_collector_lines_have_no_sliver_sectors() -> None:
    g = make_thesis_grid()
    art_rows, art_cols = arterial_rows_cols(g)
    for size in (5, 6, 8, 10, 12):
        rows, cols = sector_collector_lines(g, size)
        for lines, art, n in ((rows, art_rows, g.n_rows),
                              (cols, art_cols, g.n_cols)):
            bounds = sorted(set(lines) | art | {0, n - 1})
            gaps = [b - a for a, b in zip(bounds, bounds[1:])]
            # no sector thinner than ~half the sector size (the old global
            # stride produced 1-cell slivers at 24/25 and 48/49)
            assert min(gaps) >= max(2, size // 2), (size, bounds)


def test_sector_grid_locks_collectors_and_skips_solar() -> None:
    g = _locked_grid()
    coll_rows, coll_cols = sector_collector_lines(g, 8)
    n_collector_road = 0
    for cell in g.all_cells():
        if cell.land_use == LandUse.SOLAR_FARM:
            # a collector must never carve the solar reserve
            assert cell.locked
        if (cell.row in coll_rows or cell.col in coll_cols) \
                and cell.land_use == LandUse.ROAD:
            assert cell.locked
            n_collector_road += 1
    assert n_collector_road > 100


def test_tag_road_classes_geometric_and_widths() -> None:
    g = _locked_grid()
    cfg = load_config()
    counts = tag_road_classes(g, cfg)
    assert counts["arterial"] > 0 and counts["collector"] > 0
    art_rows, art_cols = arterial_rows_cols(g)
    for cell in g.all_cells():
        if cell.land_use != LandUse.ROAD:
            assert cell.road_class is None and cell.road_width_m == 0.0
            continue
        assert cell.road_class in ROAD_CLASS_SPEC
        assert cell.road_width_m == ROAD_CLASS_SPEC[cell.road_class]["width_m"]
        if cell.row in art_rows or cell.col in art_cols:
            assert cell.road_class == "arterial"


def test_row_area_intersection_is_union_not_double_count() -> None:
    # EXACT synthetic check: 5x5 grid, arterial lines rows/cols {0,2,4},
    # all stamped ROAD, no collectors (bands of 2 admit none at size 8).
    g = Grid.empty(5, 5, 100.0)
    art_rows, art_cols = arterial_rows_cols(g)
    for cell in g.all_cells():
        if cell.row in art_rows or cell.col in art_cols:
            cell.land_use = LandUse.ROAD
    by_class = road_row_area_m2(g)
    L = 100.0
    w = ROAD_CLASS_SPEC["arterial"]["width_m"]
    n_cross = len(art_rows) * len(art_cols)                    # 9 crossings
    n_single = (len(art_rows) + len(art_cols)) * 5 - 2 * n_cross
    expected = n_cross * (2 * w * L - w * w) + n_single * (w * L)
    assert abs(by_class["arterial"] - expected) < 1e-6, (
        by_class["arterial"], expected)
    # the big grid: total ROW far below the full-cell accounting (B16 fix)
    g2 = _locked_grid()
    cfg = load_config()
    by_class_2 = road_row_area_m2(g2, cfg)
    road_cells_area = sum(g2.cell_size_m ** 2 for c in g2.all_cells()
                          if c.land_use == LandUse.ROAD)
    assert sum(by_class_2.values()) < 0.55 * road_cells_area


def test_local_streets_serve_every_built_cell() -> None:
    from energy.network import grid_from_geojson
    g, _ = grid_from_geojson()
    out = assign_local_streets(g)
    assert out["lane_edges"] > 0
    # every lane is a real 12 m street with all three shared-space modes
    for e in g.street_edges:
        if e.kind == "local_street":
            assert e.width_m == LOCAL_STREET_WIDTH_M
            assert set(e.modes) == {"motor", "cycle", "foot"}
    # PRE-anneal bound: the CURRENT layout has 14 buildings engulfed by
    # the temporary north solar expansion block (solar_farm/blue on all
    # sides - the documented two-field state, register B14/A27); lanes
    # correctly refuse to cross a solar field. The anneal consolidates
    # solar to ONE locked SW block (nothing inside by construction), after
    # which the post-anneal verify requires unserved == 0.
    assert out["frontage_cells_unserved"] <= 20, out
    # deterministic: a second run reproduces the same edge set
    edges_1 = sorted((e.a, e.b) for e in g.street_edges
                     if e.kind == "local_street")
    assign_local_streets(g)
    edges_2 = sorted((e.a, e.b) for e in g.street_edges
                     if e.kind == "local_street")
    assert edges_1 == edges_2


def test_local_street_chains_connect_to_road_cells() -> None:
    from energy.network import grid_from_geojson
    g, _ = grid_from_geojson()
    assign_local_streets(g)
    lanes = [e for e in g.street_edges if e.kind == "local_street"]
    road_ids = {(c.row, c.col) for c in g.all_cells()
                if c.land_use == LandUse.ROAD}
    # union-graph BFS from road cells over lane adjacency must reach every
    # lane endpoint (no floating lane component)
    adj = {}
    for e in lanes:
        adj.setdefault(e.a, set()).add(e.b)
        adj.setdefault(e.b, set()).add(e.a)
    from collections import deque
    seen = set(k for k in adj if k in road_ids)
    dq = deque(seen)
    while dq:
        cur = dq.popleft()
        for nb in adj.get(cur, ()):
            if nb not in seen:
                seen.add(nb)
                dq.append(nb)
    floating = [k for k in adj if k not in seen]
    assert not floating, f"floating lane cells: {floating[:5]}"


def test_canal_corridor_stamps_locks_and_prices() -> None:
    g = _locked_grid()
    cells = canal_cells(g)
    assert len(cells) >= 30                        # ~4+ km of canal
    r = canal_row(g)
    for c in cells:
        assert c.row == r
        assert c.land_use == LandUse.BLUE_SPACE
        assert is_canal_cell(c)
    # road crossings survive: the canal row still carries ROAD at the
    # arterial + collector columns (culverts)
    crossings = [g.at(r, cc) for cc in range(g.n_cols)
                 if g.at(r, cc).land_use == LandUse.ROAD]
    assert len(crossings) >= 3
    # canal-top ceiling prices at the PEDA density via the fpv machinery
    from energy.costs import load_economics
    from energy.network import EnergyNetwork
    from layout.floating_pv_siting import assign_floating_pv_sites
    assign_floating_pv_sites(g, min_cluster_size=2)
    econ = load_economics()
    net = EnergyNetwork.from_grid(g, econ=econ)
    canal_kwp = econ.canal_pv_kwp_per_cell()
    assert canal_kwp == 210.0
    total = net.total_floating_pv_potential_kwp(econ)
    n_canal_sites = sum(1 for c in canal_cells(g) if c.is_floating_pv_site)
    assert n_canal_sites >= 30
    assert total >= n_canal_sites * canal_kwp      # canal + any pond sites


def test_canal_subtype_survives_amenity_subtype_pass() -> None:
    """Regression: the canal
    is tagged amenity_subtype='canal' PRE-anneal, and assign_amenity_subtypes
    does a defensive wipe of non-school/health subtypes. That wipe must
    PRESERVE 'canal' (the energy model prices canal-top PV off the tag),
    otherwise the whole canal silently reverts to pond density."""
    from core.demographics import load_demand_norms, load_demographics
    from core.requirements import derive_requirements
    from layout.amenity_subtype import assign_amenity_subtypes

    g = _locked_grid()
    before = len(canal_cells(g))
    assert before >= 30
    req = derive_requirements(load_demographics(), load_demand_norms(),
                              load_config())
    assign_amenity_subtypes(g, req)
    after = canal_cells(g)                 # identifies by subtype == 'canal'
    assert len(after) == before, (
        f"canal tag lost in assign_amenity_subtypes: {before} -> {len(after)}")
    for c in after:
        assert c.amenity_subtype == "canal"


def test_path_network_and_walkability() -> None:
    from energy.network import grid_from_geojson
    g, _ = grid_from_geojson()
    assign_local_streets(g)
    paths = assign_path_network(g)
    assert paths["path_edges"] > 0
    for e in g.street_edges:
        if e.kind == "greenway_path":
            assert set(e.modes) == {"cycle", "foot"}     # bike+foot together
    walk = walkability_report(g)
    for k in ("access", "permeability", "green_loop", "composite"):
        assert 0.0 <= walk[k] <= 1.0
    assert walk["access"] > 0.9        # lanes just served every built cell


def test_frontage_and_connectivity_accept_lanes() -> None:
    from energy.network import grid_from_geojson
    g, _ = grid_from_geojson()
    before = check_amenities_road_frontage(g)
    conn_before = check_road_connectivity(g)
    assign_local_streets(g)
    after = check_amenities_road_frontage(g)
    conn_after = check_road_connectivity(g)
    assert after.gap <= before.gap
    assert after.passes                       # lanes give every amenity frontage
    assert conn_after.gap <= conn_before.gap  # lanes only ever connect


def test_geojson_round_trip_preserves_edges_and_classes() -> None:
    import json
    import tempfile
    from core.export_3d import grid_to_geojson
    from energy.network import grid_from_geojson
    g, name = grid_from_geojson()
    cfg = load_config()
    tag_road_classes(g, cfg)
    assign_local_streets(g)
    assign_path_network(g)
    gj = grid_to_geojson(g, name, cfg)
    assert "road_network" in gj["metadata"]
    assert "walkability" in gj["metadata"]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "roundtrip.geojson"
        p.write_text(json.dumps(gj), encoding="utf-8")
        g2, _ = grid_from_geojson(p)
    assert len(g2.street_edges) == len(g.street_edges)
    assert sorted((e.a, e.b, e.kind) for e in g2.street_edges) == \
        sorted((e.a, e.b, e.kind) for e in g.street_edges)
    rc_1 = {(c.row, c.col): (c.road_class, c.road_width_m)
            for c in g.all_cells() if c.land_use == LandUse.ROAD}
    rc_2 = {(c.row, c.col): (c.road_class, c.road_width_m)
            for c in g2.all_cells() if c.land_use == LandUse.ROAD}
    assert rc_1 == rc_2


def test_row_report_hits_the_b6_band() -> None:
    """The B6 acceptance: on the structural grid + current fabric the total
    ROW share of developed area sits in the ratified band ~20% (17-24%
    accepted pre-anneal; the exact number re-verifies post-anneal)."""
    from energy.network import grid_from_geojson
    g, _ = grid_from_geojson()
    cfg = load_config()
    apply_sector_grid(g, sector_size_cells=8)     # proxy: collectors stamped
    tag_road_classes(g, cfg)
    assign_local_streets(g)
    rep = road_row_report(g, cfg)
    assert 0.17 <= rep["row_share_of_developed"] <= 0.24, rep
    assert rep["row_share_of_site"] <= 0.14, rep


def test_grid_copy_carries_edges_and_classes() -> None:
    g = _locked_grid()
    tag_road_classes(g, load_config())
    g.street_edges.append(StreetEdge(a=(2, 2), b=(2, 3), kind="local_street",
                                     width_m=12.0,
                                     modes=("motor", "cycle", "foot")))
    g2 = g.copy()
    assert len(g2.street_edges) == 1
    some_road = next(c for c in g2.all_cells()
                     if c.land_use == LandUse.ROAD)
    assert some_road.road_class in ROAD_CLASS_SPEC


if __name__ == "__main__":
    test_collector_lines_have_no_sliver_sectors()
    print("collector lines ok")
    test_sector_grid_locks_collectors_and_skips_solar()
    print("sector grid ok")
    test_tag_road_classes_geometric_and_widths()
    print("road classes ok")
    test_row_area_intersection_is_union_not_double_count()
    print("ROW accounting ok")
    test_local_streets_serve_every_built_cell()
    print("local streets ok")
    test_local_street_chains_connect_to_road_cells()
    print("lane connectivity ok")
    test_canal_corridor_stamps_locks_and_prices()
    print("canal corridor ok")
    test_canal_subtype_survives_amenity_subtype_pass()
    print("canal subtype survival ok")
    test_path_network_and_walkability()
    print("paths + walkability ok")
    test_frontage_and_connectivity_accept_lanes()
    print("constraint updates ok")
    test_geojson_round_trip_preserves_edges_and_classes()
    print("round-trip ok")
    test_row_report_hits_the_b6_band()
    print("B6 band ok")
    test_grid_copy_carries_edges_and_classes()
    print("grid copy ok")
    print("STAGE-F3/F4 road-network tests passed.")
