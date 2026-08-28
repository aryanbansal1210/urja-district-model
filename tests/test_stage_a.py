"""Regression tests for Stage A additions.

Covers:
  * the 3 new ``LandUse`` values (RETAIL_HIGHSTREET, BLUE_SPACE, RELIGIOUS)
    — enum, YAML target, palette, has_buildings, requirements derivation
  * all 5 new hard constraints with a positive + negative case each
  * the most behaviourally-important new Tier 1 metrics with a directional
    "compact > scattered" / "rich > poor" check

These tests are deliberately self-contained (no external fixtures) and use
the smallest grid mutation that exercises the rule. They should still pass
even if thresholds are recalibrated, because each test sets up a case that
is well clear of the threshold boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import load_config                                # noqa: E402
from core.demographics import load_demand_norms, load_demographics  # noqa: E402
from core.grid import HeightTier, make_thesis_grid                  # noqa: E402
from core.land_use import (                                         # noqa: E402
    DEFAULT_AREA_TARGETS, LAND_USE_COLOURS, LandUse, validate_targets,
)
from core.requirements import derive_requirements                   # noqa: E402

from layout.constraints import (                                    # noqa: E402
    HARD_CONSTRAINT_NAMES,
    check_amenity_equity,
    check_building_shading,
    check_green_space_buffer,
    check_hard_constraints,
    check_highstreet_road_frontage,
    check_religious_catchment,
    check_school_catchment,
)
from layout.metrics import (                                        # noqa: E402
    albedo_composite_score,
    anthro_heat_clustering_score,
    building_orientation_score,
    commercial_cluster_score,
    cool_refuge_distance_score,
    heat_island_index,
    mixed_use_ratio_400m,
    shannon_diversity_score,
    sky_view_factor_score,
    tree_shading_score,
    walkable_destinations_score,
    water_body_proximity_score,
    wind_alignment_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _blank_grid():
    """A grid where every cell is RESIDENTIAL_LOW (medium tier) so we can
    isolate the cell under test from the OPEN_SPACE defaults."""
    g = make_thesis_grid()
    cfg = load_config()
    for cell in g.all_cells():
        cell.land_use = LandUse.RESIDENTIAL_LOW
        cell.height_tier = HeightTier.MEDIUM
        cell.height_m = cfg.height_for("medium")
    return g


def _empty_grid():
    """A grid where every cell defaults to OPEN_SPACE (Grid.empty default)."""
    return make_thesis_grid()


# ---------------------------------------------------------------------------
# 1. New LandUse values exist and have all the expected metadata
# ---------------------------------------------------------------------------
def test_retail_highstreet_landuse_exists() -> None:
    assert LandUse.RETAIL_HIGHSTREET.value == "retail_highstreet"


def test_blue_space_landuse_exists() -> None:
    assert LandUse.BLUE_SPACE.value == "blue_space"


def test_religious_landuse_exists() -> None:
    assert LandUse.RELIGIOUS.value == "religious"


def test_new_landuses_have_area_targets() -> None:
    assert DEFAULT_AREA_TARGETS[LandUse.RETAIL_HIGHSTREET] > 0
    assert DEFAULT_AREA_TARGETS[LandUse.BLUE_SPACE] > 0
    assert DEFAULT_AREA_TARGETS[LandUse.RELIGIOUS] > 0
    # area targets across the whole catalogue must still sum to 1.0
    validate_targets()


def test_new_landuses_have_palette_colours() -> None:
    for lu in (LandUse.RETAIL_HIGHSTREET, LandUse.BLUE_SPACE, LandUse.RELIGIOUS):
        assert lu in LAND_USE_COLOURS
        assert LAND_USE_COLOURS[lu].startswith("#")
        assert len(LAND_USE_COLOURS[lu]) == 7


def test_blue_space_is_not_a_building_use() -> None:
    assert not LandUse.BLUE_SPACE.has_buildings
    assert not LandUse.BLUE_SPACE.is_residential


def test_retail_highstreet_and_religious_have_buildings() -> None:
    assert LandUse.RETAIL_HIGHSTREET.has_buildings
    assert LandUse.RELIGIOUS.has_buildings


def test_yaml_config_loads_new_landuses() -> None:
    cfg = load_config(force_reload=True)
    assert LandUse.RETAIL_HIGHSTREET in cfg.land_use_targets
    assert LandUse.BLUE_SPACE in cfg.land_use_targets
    assert LandUse.RELIGIOUS in cfg.land_use_targets


def test_requirements_assigns_cells_to_new_uses() -> None:
    """``derive_requirements`` must produce non-zero cell requirements for the
    three new land-uses given the placeholder demographics + norms."""
    cfg = load_config(force_reload=True)
    norms = load_demand_norms(force_reload=True)
    demo = load_demographics(force_reload=True)
    req = derive_requirements(demo, norms, cfg)
    assert req.required_cells_by_landuse.get(LandUse.RETAIL_HIGHSTREET, 0) > 0
    assert req.required_cells_by_landuse.get(LandUse.BLUE_SPACE, 0) > 0
    assert req.required_cells_by_landuse.get(LandUse.RELIGIOUS, 0) > 0


# ---------------------------------------------------------------------------
# 2. Hard constraints — positive + negative cases per new check
# ---------------------------------------------------------------------------
def test_hard_constraint_set_has_five_new_entries() -> None:
    expected = {
        "green_space_buffer",
        "building_shading",
        "highstreet_road_frontage",
        "school_catchment",
        "religious_catchment",
    }
    assert expected.issubset(HARD_CONSTRAINT_NAMES)


def test_check_hard_constraints_runs_new_checks() -> None:
    cfg = load_config(force_reload=True)
    grid = _empty_grid()
    results = check_hard_constraints(grid, cfg)
    names = {r.name for r in results}
    for new_name in ("green_space_buffer", "building_shading",
                      "highstreet_road_frontage", "school_catchment",
                      "religious_catchment"):
        assert new_name in names, f"missing constraint {new_name!r}"


# --- green_space_buffer ----------------------------------------------------
def test_green_space_buffer_passes_when_tall_cell_has_open_neighbour() -> None:
    grid = _empty_grid()
    cfg = load_config(force_reload=True)
    grid.at(10, 10).land_use = LandUse.RESIDENTIAL_HIGH
    grid.at(10, 10).height_m = cfg.height_for("tall")   # 27 m, clearly > 21
    grid.at(10, 10).height_tier = HeightTier.TALL
    # (10, 11) defaults to OPEN_SPACE so the buffer is satisfied
    res = check_green_space_buffer(grid)
    assert res.passes, res.message


def test_green_space_buffer_fails_when_tall_cell_has_no_open_buffer() -> None:
    grid = _blank_grid()
    cfg = load_config(force_reload=True)
    # surround a tall cell with other (built) cells — no OPEN_SPACE / BLUE_SPACE / ROAD
    for r in range(9, 12):
        for c in range(9, 12):
            grid.at(r, c).land_use = LandUse.RESIDENTIAL_HIGH
            grid.at(r, c).height_m = cfg.height_for("tall")
            grid.at(r, c).height_tier = HeightTier.TALL
    res = check_green_space_buffer(grid)
    assert not res.passes, res.message
    assert res.gap > 0


# --- building_shading ------------------------------------------------------
def test_building_shading_passes_when_neighbours_similar_height() -> None:
    grid = _blank_grid()
    cfg = load_config(force_reload=True)
    for r in range(8, 12):
        for c in range(8, 12):
            grid.at(r, c).height_m = cfg.height_for("medium")
            grid.at(r, c).height_tier = HeightTier.MEDIUM
    res = check_building_shading(grid)
    assert res.passes, res.message


def test_building_shading_fails_when_southern_neighbour_much_taller() -> None:
    grid = _empty_grid()
    cfg = load_config(force_reload=True)
    # candidate at (10, 10), short residential
    grid.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(10, 10).height_m = cfg.height_for("short")    # 12 m
    grid.at(10, 10).height_tier = HeightTier.SHORT
    # tall southern neighbour (row 9 is south of row 10)
    grid.at(9, 10).land_use = LandUse.RESIDENTIAL_HIGH
    grid.at(9, 10).height_m = cfg.height_for("tall")      # 27 m, diff = 15 > threshold
    grid.at(9, 10).height_tier = HeightTier.TALL
    res = check_building_shading(grid)
    assert not res.passes, res.message


# --- highstreet_road_frontage ---------------------------------------------
def test_highstreet_road_frontage_passes_with_road_on_4_neighbour() -> None:
    grid = _empty_grid()
    grid.at(10, 10).land_use = LandUse.RETAIL_HIGHSTREET
    grid.at(10, 11).land_use = LandUse.ROAD     # east 4-neighbour
    res = check_highstreet_road_frontage(grid)
    assert res.passes, res.message


def test_highstreet_road_frontage_fails_with_only_diagonal_road() -> None:
    grid = _empty_grid()
    grid.at(10, 10).land_use = LandUse.RETAIL_HIGHSTREET
    # diagonal — not a 4-neighbour
    grid.at(11, 11).land_use = LandUse.ROAD
    res = check_highstreet_road_frontage(grid)
    assert not res.passes, res.message


# --- highstreet_corridor (new) ----------------------------------
def test_highstreet_corridor_passes_with_4_chain() -> None:
    """4 RETAIL_HIGHSTREET cells in a row, each road-adjacent, 2 endpoints."""
    from layout.constraints import check_highstreet_corridor
    grid = _empty_grid()
    for c in range(10, 14):
        grid.at(10, c).land_use = LandUse.RETAIL_HIGHSTREET
        grid.at(11, c).land_use = LandUse.ROAD       # ROAD frontage south
    res = check_highstreet_corridor(grid)
    assert res.passes, res.message


def test_highstreet_corridor_fails_with_isolated_cell() -> None:
    """A standalone RETAIL_HIGHSTREET cell fails the >=4 chain length."""
    from layout.constraints import check_highstreet_corridor
    grid = _empty_grid()
    grid.at(10, 10).land_use = LandUse.RETAIL_HIGHSTREET
    grid.at(10, 11).land_use = LandUse.ROAD
    res = check_highstreet_corridor(grid)
    assert not res.passes, res.message


def test_highstreet_corridor_fails_with_3_chain() -> None:
    """A 3-cell chain still fails the minimum length 4 rule."""
    from layout.constraints import check_highstreet_corridor
    grid = _empty_grid()
    for c in range(10, 13):
        grid.at(10, c).land_use = LandUse.RETAIL_HIGHSTREET
        grid.at(11, c).land_use = LandUse.ROAD
    res = check_highstreet_corridor(grid)
    assert not res.passes, res.message


def test_highstreet_corridor_fails_with_t_branching() -> None:
    """A T-shaped component has 3 endpoints -> fails the <=2 endpoint rule."""
    from layout.constraints import check_highstreet_corridor
    grid = _empty_grid()
    # horizontal arm of length 4
    for c in range(10, 14):
        grid.at(10, c).land_use = LandUse.RETAIL_HIGHSTREET
        grid.at(11, c).land_use = LandUse.ROAD
    # vertical stub from middle (one extra cell to create the T)
    grid.at(9, 12).land_use = LandUse.RETAIL_HIGHSTREET
    grid.at(9, 11).land_use = LandUse.ROAD
    res = check_highstreet_corridor(grid)
    assert not res.passes, res.message


def test_highstreet_corridor_passes_with_no_highstreet_cells() -> None:
    from layout.constraints import check_highstreet_corridor
    grid = _empty_grid()
    res = check_highstreet_corridor(grid)
    assert res.passes


# --- school_catchment ------------------------------------------------------
def test_school_catchment_passes_with_nearby_school() -> None:
    grid = _empty_grid()
    grid.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(10, 12).land_use = LandUse.SCHOOL    # 2 cells east = 400 m Manhattan
    res = check_school_catchment(grid)
    assert res.passes, res.message


def test_school_catchment_fails_with_school_far_from_residents() -> None:
    grid = _empty_grid()
    grid.at(0, 0).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(24, 24).land_use = LandUse.SCHOOL    # 9600 m Manhattan — far > 1 km
    res = check_school_catchment(grid)
    assert not res.passes, res.message


# --- religious_catchment ---------------------------------------------------
def test_religious_catchment_passes_with_nearby_religious() -> None:
    grid = _empty_grid()
    grid.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(10, 12).land_use = LandUse.RELIGIOUS  # 400 m Manhattan, < 800 m
    res = check_religious_catchment(grid)
    assert res.passes, res.message


def test_religious_catchment_fails_with_religious_far_from_residents() -> None:
    grid = _empty_grid()
    grid.at(0, 0).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(24, 24).land_use = LandUse.RELIGIOUS  # 9600 m Manhattan
    res = check_religious_catchment(grid)
    assert not res.passes, res.message


# --- amenity_equity (option C hybrid hard constraint) ---------------------
def test_amenity_equity_passes_with_nearby_blue_and_healthcare() -> None:
    """A residential cell that has BLUE_SPACE AND HEALTHCARE within reach
    passes the equity constraint."""
    grid = _empty_grid()
    grid.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(10, 12).land_use = LandUse.BLUE_SPACE     # 400 m east
    grid.at(11, 11).land_use = LandUse.HEALTHCARE     # 400 m SE
    res = check_amenity_equity(grid)
    assert res.passes, res.message


def test_amenity_equity_fails_when_resident_far_from_cool_refuge() -> None:
    """Residents > 1000 m from any OPEN_SPACE / BLUE_SPACE -> fail.

    Note: empty grid defaults to OPEN_SPACE everywhere, so we explicitly
    REPLACE the OPEN_SPACE cells near (0,0) with non-refuge land-uses to
    force the failure condition.
    """
    grid = _empty_grid()
    grid.at(0, 0).land_use = LandUse.RESIDENTIAL_LOW
    # Strip OPEN_SPACE within 1000 m of (0, 0) to force a fail. STAGE-
    #: the strip radius derives from the grid's cell size
    # (was a hardcoded 5 cells that silently halved at the 100 m re-grid).
    strip = int(1000 // grid.cell_size_m) + 1
    for r in range(0, strip + 1):
        for c in range(0, strip + 1):
            if grid.at(r, c).land_use == LandUse.OPEN_SPACE:
                grid.at(r, c).land_use = LandUse.ROAD
    far = grid.n_rows - 1
    grid.at(far, far).land_use = LandUse.BLUE_SPACE   # far corner
    grid.at(0, 1).land_use = LandUse.HEALTHCARE       # close (passes health)
    res = check_amenity_equity(grid)
    assert not res.passes, res.message


def test_amenity_equity_fails_when_resident_far_from_healthcare() -> None:
    """Residents > 1200 m from HEALTHCARE -> fail."""
    grid = _empty_grid()
    grid.at(0, 0).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(0, 1).land_use = LandUse.BLUE_SPACE       # close (passes cool refuge)
    grid.at(24, 24).land_use = LandUse.HEALTHCARE     # 9600 m away
    res = check_amenity_equity(grid)
    assert not res.passes, res.message


def test_amenity_equity_open_space_counts_as_cool_refuge() -> None:
    """OPEN_SPACE alone (without BLUE_SPACE) satisfies cool-refuge equity."""
    grid = _empty_grid()
    grid.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(10, 12).land_use = LandUse.OPEN_SPACE     # OK in lieu of blue
    grid.at(11, 11).land_use = LandUse.HEALTHCARE
    res = check_amenity_equity(grid)
    assert res.passes, res.message


def test_amenity_equity_is_in_hard_constraint_set() -> None:
    """The new equity constraint must appear in the HARD constraint list."""
    assert "amenity_equity" in HARD_CONSTRAINT_NAMES


# --- park_quadrant_coverage ---------------------------------
def test_park_quadrant_coverage_passes_with_parks_in_each_quadrant() -> None:
    """Residents in each quadrant with 4+ OPEN_SPACE cells nearby pass."""
    grid = _empty_grid()
    grid.at(3, 3).land_use = LandUse.RESIDENTIAL_LOW   # NW
    grid.at(3, 20).land_use = LandUse.RESIDENTIAL_LOW  # NE
    grid.at(20, 3).land_use = LandUse.RESIDENTIAL_LOW  # SW
    grid.at(20, 20).land_use = LandUse.RESIDENTIAL_LOW # SE
    # Empty grid defaults to OPEN_SPACE; each quadrant has ~144 OPEN_SPACE
    # cells already. So the constraint passes by construction.
    from layout.constraints import check_park_quadrant_coverage
    res = check_park_quadrant_coverage(grid)
    assert res.passes, res.message


def test_park_quadrant_coverage_fails_when_quadrant_has_no_park() -> None:
    """An NE residential cluster with all OPEN_SPACE stripped should fail."""
    grid = _empty_grid()
    # Strip OPEN_SPACE from the NE quadrant. STAGE-: bounds
    # derive from the grid size (were hardcoded for the 25x25 grid).
    mid = grid.n_rows // 2
    for r in range(0, mid + 1):
        for c in range(mid, grid.n_cols):
            if grid.at(r, c).land_use == LandUse.OPEN_SPACE:
                grid.at(r, c).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(3, mid + 8).land_use = LandUse.RESIDENTIAL_LOW   # NE resident
    from layout.constraints import check_park_quadrant_coverage
    res = check_park_quadrant_coverage(grid)
    assert not res.passes, res.message
    assert "ne=0" in res.message, res.message


def test_park_quadrant_coverage_is_in_hard_constraint_set() -> None:
    assert "park_quadrant_coverage" in HARD_CONSTRAINT_NAMES


# ---------------------------------------------------------------------------
# 3. Metric directional tests — "compact > scattered", "near > far", etc.
# ---------------------------------------------------------------------------
def test_albedo_composite_rewards_higher_albedo() -> None:
    grid_low = _empty_grid()
    grid_high = _empty_grid()
    for c in grid_low.all_cells():
        c.albedo = 0.20
    for c in grid_high.all_cells():
        c.albedo = 0.50
    assert albedo_composite_score(grid_high) > albedo_composite_score(grid_low)


def test_heat_island_index_rewards_high_veg_low_load() -> None:
    cool = _empty_grid()
    hot = _empty_grid()
    for c in cool.all_cells():
        c.albedo = 0.40
        c.vegetation_fraction = 0.80
    for c in hot.all_cells():
        c.albedo = 0.10
        c.vegetation_fraction = 0.05
    assert heat_island_index(cool) > heat_island_index(hot)


def test_anthro_heat_clustering_rewards_dispersed_industry() -> None:
    # 4 industry cells in a tight cluster vs 4 industry cells spread out
    clustered = _empty_grid()
    for r in range(10, 12):
        for c in range(10, 12):
            clustered.at(r, c).land_use = LandUse.LIGHT_INDUSTRY
    dispersed = _empty_grid()
    for (r, c) in [(2, 2), (2, 22), (22, 2), (22, 22)]:
        dispersed.at(r, c).land_use = LandUse.LIGHT_INDUSTRY
    assert (anthro_heat_clustering_score(dispersed)
            > anthro_heat_clustering_score(clustered))


def test_wind_alignment_rewards_NW_SE_road_grid() -> None:
    # NW-SE diagonal: row 0 is south + col 24 is east, NW corner = (24, 0).
    # The wind-aligned diagonal therefore runs (24, 0) -> (0, 24), i.e. cells
    # where row + col = 24. NW neighbour of (r, c) is (r+1, c-1); summing to
    # the same constant means it stays on the same NW-SE diagonal.
    diagonal = _empty_grid()
    for i in range(25):
        diagonal.at(24 - i, i).land_use = LandUse.ROAD
    orthogonal = _empty_grid()
    for c in range(25):
        orthogonal.at(12, c).land_use = LandUse.ROAD
    assert wind_alignment_score(diagonal) > wind_alignment_score(orthogonal)


def test_tree_shading_rewards_vegetated_roads() -> None:
    leafy = _empty_grid()
    bare = _empty_grid()
    for r in range(25):
        leafy.at(r, 12).land_use = LandUse.ROAD
        leafy.at(r, 12).vegetation_fraction = 0.7
        bare.at(r, 12).land_use = LandUse.ROAD
        bare.at(r, 12).vegetation_fraction = 0.05
    assert tree_shading_score(leafy) > tree_shading_score(bare)


def test_cool_refuge_distance_rewards_residents_near_open_blue() -> None:
    near = _empty_grid()
    near.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    near.at(10, 11).land_use = LandUse.OPEN_SPACE
    far = _empty_grid()
    for c in far.all_cells():
        c.land_use = LandUse.RESIDENTIAL_LOW
    far.at(0, 0).land_use = LandUse.OPEN_SPACE
    far.at(24, 24).land_use = LandUse.RESIDENTIAL_LOW
    assert (cool_refuge_distance_score(near)
            > cool_refuge_distance_score(far))


def test_water_body_proximity_rewards_residents_near_blue_space() -> None:
    # Compact residential cluster + nearby vs far BLUE_SPACE. _blank_grid
    # paints the entire grid RESIDENTIAL_LOW so the proximity average is
    # dominated by the 600+ far cells; switch to a tight cluster so the
    # near/far signal is visible at the score level.
    near = _empty_grid()
    for r in range(10, 12):
        for c in range(10, 12):
            near.at(r, c).land_use = LandUse.RESIDENTIAL_LOW
    near.at(10, 12).land_use = LandUse.BLUE_SPACE   # 1 cell east of the cluster
    far = _empty_grid()
    for r in range(10, 12):
        for c in range(10, 12):
            far.at(r, c).land_use = LandUse.RESIDENTIAL_LOW
    far.at(0, 0).land_use = LandUse.BLUE_SPACE      # opposite-corner blue
    assert (water_body_proximity_score(near)
            > water_body_proximity_score(far))


def test_mixed_use_ratio_rewards_diverse_neighbourhood() -> None:
    diverse = _empty_grid()
    diverse.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    diverse.at(10, 11).land_use = LandUse.SCHOOL
    diverse.at(11, 10).land_use = LandUse.SHOPPING_CENTRE
    diverse.at(11, 11).land_use = LandUse.HEALTHCARE
    diverse.at(9, 10).land_use = LandUse.OPEN_SPACE
    diverse.at(9, 11).land_use = LandUse.ROAD
    monoculture = _blank_grid()    # all residential_low
    assert mixed_use_ratio_400m(diverse) > mixed_use_ratio_400m(monoculture)


def test_shannon_diversity_rewards_balanced_mix() -> None:
    mixed = _empty_grid()
    mixed.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    mixed.at(10, 11).land_use = LandUse.SCHOOL
    mixed.at(11, 10).land_use = LandUse.SHOPPING_CENTRE
    mixed.at(11, 11).land_use = LandUse.OPEN_SPACE
    monoculture = _blank_grid()
    assert shannon_diversity_score(mixed) > shannon_diversity_score(monoculture)


def test_walkable_destinations_rewards_more_distinct_amenity_types() -> None:
    diverse = _empty_grid()
    diverse.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    diverse.at(10, 11).land_use = LandUse.SCHOOL
    diverse.at(11, 10).land_use = LandUse.SHOPPING_CENTRE
    diverse.at(11, 11).land_use = LandUse.HEALTHCARE
    diverse.at(12, 10).land_use = LandUse.RELIGIOUS
    sparse = _empty_grid()
    sparse.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    # no amenity neighbours
    assert (walkable_destinations_score(diverse)
            > walkable_destinations_score(sparse))


def test_commercial_cluster_rewards_compact_shops() -> None:
    compact = _empty_grid()
    for r in range(10, 14):
        for c in range(10, 14):
            compact.at(r, c).land_use = LandUse.SHOPPING_CENTRE
    scattered = _empty_grid()
    for (r, c) in [(2, 2), (2, 22), (12, 12), (22, 2), (22, 22)]:
        scattered.at(r, c).land_use = LandUse.SHOPPING_CENTRE
    assert commercial_cluster_score(compact) > commercial_cluster_score(scattered)


def test_building_orientation_rewards_E_W_row_alignment() -> None:
    ew_row = _empty_grid()
    for c in range(5, 20):
        ew_row.at(10, c).land_use = LandUse.RESIDENTIAL_MID
    ns_column = _empty_grid()
    for r in range(5, 20):
        ns_column.at(r, 10).land_use = LandUse.RESIDENTIAL_MID
    assert building_orientation_score(ew_row) > building_orientation_score(ns_column)


def test_sky_view_factor_rewards_unobstructed_residential() -> None:
    cfg = load_config(force_reload=True)
    open_grid = _empty_grid()
    open_grid.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    open_grid.at(10, 10).height_m = cfg.height_for("short")
    # 4-neighbours default to OPEN_SPACE (height 0)

    obstructed = _empty_grid()
    obstructed.at(10, 10).land_use = LandUse.RESIDENTIAL_LOW
    obstructed.at(10, 10).height_m = cfg.height_for("short")
    for (dr, dc) in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        obstructed.at(10 + dr, 10 + dc).land_use = LandUse.RESIDENTIAL_HIGH
        obstructed.at(10 + dr, 10 + dc).height_m = cfg.height_for("tall")

    assert sky_view_factor_score(open_grid) > sky_view_factor_score(obstructed)


# ---------------------------------------------------------------------------
# Self-test entry point
# ---------------------------------------------------------------------------
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
    print(f"\nAll {len(fns)} Stage A regression tests passed.")
