"""Tests for the realism-focused constraints and metrics added to fix the
issues the 3D viewer surfaced (clustered solar farms, road frontage,
industrial buffers, ground-PV shading, etc.)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import load_config                         # noqa: E402
from core.grid import HeightTier, make_thesis_grid           # noqa: E402
from core.land_use import LandUse                            # noqa: E402

from layout.constraints import (                              # noqa: E402
    HARD_CONSTRAINT_NAMES,
    SOFT_CONSTRAINT_NAMES,
    check_amenities_road_frontage,
    check_hard_constraints,
    check_industrial_buffer,
    check_open_space_clustering,
    check_solar_farm_clustering,
)
from layout.metrics import (                                  # noqa: E402
    infrastructure_distance_score,
    open_space_cluster_score,
    solar_access_score,
    solar_cluster_score,
)


# ---------------------------------------------------------------------------
# Solar-farm clustering
# ---------------------------------------------------------------------------
def test_compact_solar_farm_passes_clustering() -> None:
    """A single 4x4 block of SOLAR_FARM cells must pass the cluster check."""
    grid = make_thesis_grid()
    for r in range(2, 6):
        for c in range(2, 6):
            grid.at(r, c).land_use = LandUse.SOLAR_FARM
    res = check_solar_farm_clustering(grid, min_cluster_size=4)
    assert res.passes, f"compact solar farm should pass: {res.message}"


def test_scattered_solar_singletons_fail_clustering() -> None:
    """16 single-cell solar farms (no neighbours) must fail the cluster check."""
    grid = make_thesis_grid()
    # 16 isolated cells, every other column / row
    for i in range(4):
        for j in range(4):
            grid.at(2 + 4 * i, 2 + 4 * j).land_use = LandUse.SOLAR_FARM
    res = check_solar_farm_clustering(grid, min_cluster_size=4)
    assert not res.passes
    assert res.gap > 0.5, (
        f"scattered singletons should have heavy gap, got {res.gap}"
    )


def test_solar_cluster_score_prefers_compact_over_scattered() -> None:
    compact = make_thesis_grid()
    for r in range(2, 6):
        for c in range(2, 6):
            compact.at(r, c).land_use = LandUse.SOLAR_FARM
    scattered = make_thesis_grid()
    for i in range(4):
        for j in range(4):
            scattered.at(2 + 4 * i, 2 + 4 * j).land_use = LandUse.SOLAR_FARM
    s_compact = solar_cluster_score(compact)
    s_scattered = solar_cluster_score(scattered)
    assert s_compact > s_scattered, (
        f"compact ({s_compact:.2f}) should beat scattered ({s_scattered:.2f})"
    )


# ---------------------------------------------------------------------------
# Solar-access shading (now also covers SOLAR_FARM cells)
# ---------------------------------------------------------------------------
def test_solar_farm_shadowed_by_tall_southern_building_is_penalised() -> None:
    """Place a SOLAR_FARM cell with a 27 m residential tower directly south.
    The old shading score didn't see this; the new one must.
    """
    cfg = load_config()
    grid = make_thesis_grid()
    # solar farm cell at row=10, col=10
    grid.at(10, 10).land_use = LandUse.SOLAR_FARM
    # tall tower directly south (row 9 is south of row 10 in our convention)
    grid.at(9, 10).land_use = LandUse.RESIDENTIAL_HIGH
    grid.at(9, 10).height_m = 27.0
    grid.at(9, 10).height_tier = HeightTier.TALL

    score = solar_access_score(grid)
    # exactly one shadowed cell out of two PV cells (the solar farm + tower
    # which has its own roof PV). Score should reflect this rather than 1.0.
    assert score < 1.0, (
        "solar farm beneath tall southern building should be scored "
        f"as shadowed, got {score:.3f}"
    )


def test_open_solar_farm_scores_full_access() -> None:
    """A SOLAR_FARM cell with no tall neighbours must score full credit."""
    grid = make_thesis_grid()
    # cluster of 4 cells with nothing around them
    for r, c in [(10, 10), (10, 11), (11, 10), (11, 11)]:
        grid.at(r, c).land_use = LandUse.SOLAR_FARM
    score = solar_access_score(grid)
    assert score == 1.0, f"unshadowed solar farm should score 1.0, got {score}"


# ---------------------------------------------------------------------------
# Amenity road-frontage
# ---------------------------------------------------------------------------
def test_school_with_no_adjacent_road_fails_frontage() -> None:
    grid = make_thesis_grid()
    grid.at(10, 10).land_use = LandUse.SCHOOL
    # leave 8-neighbours as OPEN_SPACE (default) — no road
    res = check_amenities_road_frontage(grid)
    assert not res.passes, "isolated school should fail road frontage"


def test_school_with_adjacent_road_passes_frontage() -> None:
    grid = make_thesis_grid()
    grid.at(10, 10).land_use = LandUse.SCHOOL
    grid.at(9, 10).land_use = LandUse.ROAD
    res = check_amenities_road_frontage(grid)
    assert res.passes, f"school next to road should pass: {res.message}"


def test_shopping_centre_requires_road_frontage() -> None:
    grid = make_thesis_grid()
    grid.at(5, 5).land_use = LandUse.SHOPPING_CENTRE
    # no road neighbour
    res = check_amenities_road_frontage(grid)
    assert not res.passes


def test_restaurant_and_public_services_required() -> None:
    grid = make_thesis_grid()
    grid.at(3, 3).land_use = LandUse.RESTAURANT_FOOD
    grid.at(20, 20).land_use = LandUse.PUBLIC_SERVICES
    res = check_amenities_road_frontage(grid)
    assert not res.passes
    assert res.gap >= 0.99, (
        f"both amenities lacking road should be near-full violation, "
        f"got {res.gap}"
    )


# ---------------------------------------------------------------------------
# Open-space clustering
# ---------------------------------------------------------------------------
def _blank_grid_residential():
    """make_thesis_grid defaults to OPEN_SPACE everywhere, which is wrong for
    open-space clustering tests. Reset to RESIDENTIAL_LOW so we control the
    OPEN_SPACE positions explicitly."""
    g = make_thesis_grid()
    for cell in g.all_cells():
        cell.land_use = LandUse.RESIDENTIAL_LOW
    return g


def test_open_space_singletons_fail_clustering_rule() -> None:
    grid = _blank_grid_residential()
    # 8 isolated singletons, well-spaced (>= 3 cells apart so no adjacency)
    for r, c in [(2, 2), (2, 7), (2, 12), (7, 2),
                  (12, 12), (17, 17), (22, 2), (22, 22)]:
        grid.at(r, c).land_use = LandUse.OPEN_SPACE
    res = check_open_space_clustering(grid, min_cluster_size=4,
                                        max_singleton_share=0.25)
    assert not res.passes, (
        f"all-singleton open space should fail; got {res.message}"
    )


def test_open_space_big_cluster_passes() -> None:
    grid = _blank_grid_residential()
    for r in range(5, 9):
        for c in range(5, 9):
            grid.at(r, c).land_use = LandUse.OPEN_SPACE
    res = check_open_space_clustering(grid, min_cluster_size=4)
    assert res.passes, f"4x4 park should pass: {res.message}"


def test_open_space_cluster_score_bigger_park_better() -> None:
    big = _blank_grid_residential()
    for r in range(5, 9):
        for c in range(5, 9):
            big.at(r, c).land_use = LandUse.OPEN_SPACE
    fragmented = _blank_grid_residential()
    # 16 singletons spread out
    coords = [(2 + 4 * i, 2 + 4 * j) for i in range(4) for j in range(4)]
    for r, c in coords:
        fragmented.at(r, c).land_use = LandUse.OPEN_SPACE
    s_big = open_space_cluster_score(big)
    s_frag = open_space_cluster_score(fragmented)
    assert s_big > s_frag, (
        f"compact park ({s_big:.2f}) should beat fragmented ({s_frag:.2f})"
    )


# ---------------------------------------------------------------------------
# Industrial buffer
# ---------------------------------------------------------------------------
def test_industry_directly_next_to_residential_fails_buffer() -> None:
    grid = make_thesis_grid()
    grid.at(0, 0).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(0, 1).land_use = LandUse.RESIDENTIAL_LOW
    res = check_industrial_buffer(grid)
    assert not res.passes


def test_industry_with_road_buffer_passes() -> None:
    grid = make_thesis_grid()
    grid.at(0, 0).land_use = LandUse.LIGHT_INDUSTRY
    # surround all 8 neighbours with non-residential
    grid.at(0, 1).land_use = LandUse.ROAD
    grid.at(1, 0).land_use = LandUse.ROAD
    grid.at(1, 1).land_use = LandUse.ROAD
    res = check_industrial_buffer(grid)
    assert res.passes, f"industry with full buffer should pass: {res.message}"


def test_industry_directly_next_to_religious_fails_buffer() -> None:
    """ (audit A26): RELIGIOUS is now a sensitive receptor for
    the industrial-buffer constraint. Cultural mismatch -- gurudwaras /
    temples should not share a boundary with industrial activity."""
    grid = make_thesis_grid()
    grid.at(0, 0).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(0, 1).land_use = LandUse.RELIGIOUS
    res = check_industrial_buffer(grid)
    assert not res.passes, (
        f"industry next to religious should fail buffer: {res.message}"
    )


# ---------------------------------------------------------------------------
# Hard / soft separation
# ---------------------------------------------------------------------------
def test_hard_constraint_set_includes_realism_rules() -> None:
    expected = {
        "area_targets",
        "road_connectivity",
        "road_proximity",
        "schools_vs_industry",
        "industry_on_edge",
        "hospital_near_road",
        "amenities_road_frontage",
        "industrial_buffer",
        "solar_farm_clustering",
        "open_space_clustering",
    }
    assert expected.issubset(HARD_CONSTRAINT_NAMES)


def test_soft_constraints_are_only_requirements() -> None:
    assert SOFT_CONSTRAINT_NAMES == {"requirements_satisfied"}


def test_check_hard_constraints_returns_only_hard() -> None:
    cfg = load_config()
    grid = make_thesis_grid()
    results = check_hard_constraints(grid, cfg)
    names = {r.name for r in results}
    assert names == HARD_CONSTRAINT_NAMES


# ---------------------------------------------------------------------------
# Infrastructure-distance proxy
# ---------------------------------------------------------------------------
def test_solar_far_from_roads_scores_lower_than_near_roads() -> None:
    far = make_thesis_grid()
    # solar in opposite corner from any roads, no roads at all
    for r in range(20, 24):
        for c in range(20, 24):
            far.at(r, c).land_use = LandUse.SOLAR_FARM
    # one isolated road in the other corner
    far.at(0, 0).land_use = LandUse.ROAD
    far.at(0, 1).land_use = LandUse.ROAD

    near = make_thesis_grid()
    for r in range(20, 24):
        for c in range(20, 24):
            near.at(r, c).land_use = LandUse.SOLAR_FARM
    # road right next to the solar
    for c in range(20, 24):
        near.at(19, c).land_use = LandUse.ROAD

    s_far = infrastructure_distance_score(far)
    s_near = infrastructure_distance_score(near)
    assert s_near > s_far, (
        f"near-road solar ({s_near:.2f}) should beat far-from-road "
        f"({s_far:.2f})"
    )


if __name__ == "__main__":
    # run by name so a failure is identifiable
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
    print(f"\nAll {len(fns)} realism tests passed.")
