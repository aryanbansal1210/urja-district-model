"""Tests for Stage C plant spatial siting (biomass / biogas / WTE).

: plants are placed by a deterministic
post-SA greedy step. Tests pin: industrial preference, road-frontage
requirement, residential and school buffer behaviour, fallback when
no compliant cell exists, and the hard-constraint registration.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.grid import Grid                                       # noqa: E402
from core.land_use import LandUse                                 # noqa: E402

from layout.constraints import (                                  # noqa: E402
    HARD_CONSTRAINT_NAMES,
    check_stage_c_plant_buffer,
)
from layout.plant_siting import (                                 # noqa: E402
    PLANT_KINDS,
    PlantPlacement,
    find_plant_site,
    place_stage_c_plants,
)


def _empty_grid() -> Grid:
    return Grid.empty(n_rows=10, n_cols=10, cell_size_m=200.0)


def _place_road_corridor(grid: Grid, row: int) -> None:
    for c in range(grid.n_cols):
        grid.at(row, c).land_use = LandUse.ROAD


def test_no_candidates_returns_none() -> None:
    """An empty open-space-only grid has no industrial cells -> no site."""
    grid = _empty_grid()
    p = find_plant_site(grid, "biomass_chp")
    assert p is None


def test_industrial_cell_with_road_is_chosen() -> None:
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    # Single industrial cell adjacent to road on row 4, col 3
    grid.at(4, 3).land_use = LandUse.LIGHT_INDUSTRY
    p = find_plant_site(grid, "biomass_chp")
    assert p is not None
    assert (p.row, p.col) == (4, 3)
    assert p.host_land_use == LandUse.LIGHT_INDUSTRY.value


def test_isolated_industrial_without_road_is_skipped() -> None:
    grid = _empty_grid()
    grid.at(4, 3).land_use = LandUse.LIGHT_INDUSTRY
    # No road; should fail the candidate filter
    p = find_plant_site(grid, "biomass_chp")
    assert p is None


def test_residential_buffer_prefers_farther_cell() -> None:
    """Two industrial cells, both road-adjacent. The plant must pick the
    one farther from residential."""
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    # Two industrial cells equally road-adjacent but at different distances
    grid.at(4, 0).land_use = LandUse.LIGHT_INDUSTRY  # column 0
    grid.at(4, 9).land_use = LandUse.LIGHT_INDUSTRY  # column 9
    # Cluster of residential cells near column 0
    for c in range(0, 3):
        grid.at(2, c).land_use = LandUse.RESIDENTIAL_LOW
    p = find_plant_site(grid, "biomass_chp")
    assert p is not None
    assert p.col == 9, f"expected col 9 (far from residential), got {p}"


def test_school_buffer_fallback_when_all_too_close() -> None:
    """If every candidate violates the buffer, fallback returns best-of-worst
    with the buffer-violation reason recorded."""
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    # Industrial cell at (4, 3); school at (4, 5) -- Manhattan distance 2
    # (meets the default school buffer 2). Tighten school buffer to 3 to
    # force violation.
    grid.at(4, 3).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(4, 5).land_use = LandUse.SCHOOL
    p = find_plant_site(grid, "biomass_chp", school_buffer_cells=3)
    assert p is not None
    assert "buffer-violated fallback" in p.reason


def test_place_stage_c_plants_uses_distinct_cells() -> None:
    """The three plants must not share a cell."""
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    # Three industrial cells, all road-adjacent
    grid.at(4, 2).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(4, 5).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(4, 8).land_use = LandUse.PUBLIC_SERVICES
    placed = place_stage_c_plants(grid)
    assert len(placed) == 3, placed
    cells = {(p.row, p.col) for p in placed.values()}
    assert len(cells) == 3, "plants must occupy distinct cells"
    assert set(placed.keys()) == set(PLANT_KINDS)


def test_grid_plant_placements_field_mutated() -> None:
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    grid.at(4, 5).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(4, 7).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(4, 9).land_use = LandUse.PUBLIC_SERVICES
    place_stage_c_plants(grid)
    assert "biomass_chp" in grid.plant_placements
    assert all(isinstance(p, PlantPlacement)
               for p in grid.plant_placements.values())


def test_plant_buffer_constraint_passes_with_empty_placements() -> None:
    grid = _empty_grid()
    res = check_stage_c_plant_buffer(grid)
    assert res.passes, res.message


def test_plant_buffer_constraint_fails_with_close_residential() -> None:
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    grid.at(4, 3).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(3, 3).land_use = LandUse.RESIDENTIAL_LOW  # 1 cell away
    place_stage_c_plants(grid)
    res = check_stage_c_plant_buffer(grid)
    assert not res.passes, res.message


def test_stage_c_plant_buffer_is_hard_constraint() -> None:
    """Ensure the constraint is in the HARD set."""
    assert "stage_c_plant_buffer" in HARD_CONSTRAINT_NAMES


def test_grid_copy_preserves_plant_placements() -> None:
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    grid.at(4, 5).land_use = LandUse.LIGHT_INDUSTRY
    place_stage_c_plants(grid)
    copy = grid.copy()
    assert copy.plant_placements == grid.plant_placements


# ---------------------------------------------------------------------------
# (A15 logistics-aware siting) -- kind-specific objectives.
# ---------------------------------------------------------------------------
def test_biomass_prefers_edge_cell_for_truck_access() -> None:
    """Two equally-buffered LIGHT_INDUSTRY cells: biomass should pick the
    one nearer the district edge (truck-access proxy)."""
    grid = _empty_grid()
    _place_road_corridor(grid, row=8)
    # Two equally road-adjacent industrial cells, both far from residential
    # (none placed). One on the edge (col 0), one interior (col 5).
    grid.at(7, 0).land_use = LandUse.LIGHT_INDUSTRY   # at edge (d_edge = 0)
    grid.at(7, 5).land_use = LandUse.LIGHT_INDUSTRY   # interior (d_edge = 2)
    p = find_plant_site(grid, "biomass_chp")
    assert p is not None
    assert p.col == 0, (
        f"biomass should prefer the edge cell for truck access; got col={p.col}"
    )


def test_biogas_prefers_proximity_to_public_services() -> None:
    """Biogas should cluster with PUBLIC_SERVICES (waste / water-services)
    rather than just maximising buffer distance."""
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    # Two PUBLIC_SERVICES candidates equally road-adjacent; one near another
    # PUBLIC_SERVICES cell (waste / water-services proxy), one far from it.
    grid.at(4, 1).land_use = LandUse.PUBLIC_SERVICES   # close-cluster candidate
    grid.at(4, 8).land_use = LandUse.PUBLIC_SERVICES   # far candidate
    # Auxiliary water-services cell on row 0 column 0 -- not road-adjacent
    # so not a candidate itself, but pulls the biogas score toward col 1.
    grid.at(0, 0).land_use = LandUse.PUBLIC_SERVICES
    p = find_plant_site(grid, "biogas")
    assert p is not None
    assert p.col == 1, (
        f"biogas should prefer the cell nearer the PUBLIC_SERVICES cluster; got col={p.col}"
    )


def test_wte_maximises_sensitive_receptor_distance() -> None:
    """WTE should pick the cell with the largest sum of distances to
    residential + school + healthcare regardless of edge/cluster signals."""
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    grid.at(4, 0).land_use = LandUse.LIGHT_INDUSTRY   # near edge
    grid.at(4, 9).land_use = LandUse.LIGHT_INDUSTRY   # also near edge but far from receptors
    # Cluster of residential + school near column 0 so col 0 has the lower
    # receptor-distance score.
    for c in range(0, 3):
        grid.at(0, c).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(1, 0).land_use = LandUse.SCHOOL
    p = find_plant_site(grid, "wte")
    assert p is not None
    assert p.col == 9, (
        f"WTE should pick the cell with the largest receptor distance; got col={p.col}"
    )


def test_biomass_clustering_with_existing_light_industry() -> None:
    """When two edge cells tie on truck-access, biomass should pick the one
    clustered with another LIGHT_INDUSTRY cell."""
    grid = _empty_grid()
    _place_road_corridor(grid, row=5)
    # Two LIGHT_INDUSTRY candidates both at the edge.
    grid.at(4, 0).land_use = LandUse.LIGHT_INDUSTRY
    grid.at(0, 4).land_use = LandUse.LIGHT_INDUSTRY
    # Extra LIGHT_INDUSTRY cell adjacent to (4, 0) but not a candidate
    # itself (no road neighbour). Pulls the biomass score toward (4, 0).
    grid.at(3, 0).land_use = LandUse.LIGHT_INDUSTRY
    p = find_plant_site(grid, "biomass_chp")
    assert p is not None
    assert (p.row, p.col) == (4, 0), (
        f"biomass should cluster with existing light_industry; got ({p.row}, {p.col})"
    )


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    fails: List[str] = []
    for fn in fns:
        try:
            fn()
            print(f"  OK  {fn.__name__}")
        except Exception as exc:
            print(f"  X   {fn.__name__}: {exc}")
            fails.append(fn.__name__)
    if fails:
        print(f"\n{len(fails)} tests failed: {fails}")
        sys.exit(1)
    print(f"\nAll {len(fns)} plant-siting tests passed.")
