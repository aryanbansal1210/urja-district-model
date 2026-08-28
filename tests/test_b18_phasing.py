"""STAGE-B18 tests: demand-driven phased parking + the phased solar land
grant + the tag-driven per-period energy multipliers.

Direct-runner style: `python tests/test_b18_phasing.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config
from core.demographics import load_demand_norms, load_demographics
from core.land_use import LandUse
from core.parking_demand import (
    PERIODS, car_fleet_by_period, fleet_growth_index,
    on_plot_absorption_audit, parking_cells_by_period,
    public_parking_ecs_by_period,
)
from core.requirements import derive_requirements


def _req():
    return derive_requirements(load_demographics(), load_demand_norms(),
                               load_config())


def _floors(req):
    return {
        "high_income_residential": req.residential_floor_m2_by_income.get("high", 0.0),
        "mid_income_residential": req.residential_floor_m2_by_income.get("mid", 0.0),
        "low_income_residential": req.residential_floor_m2_by_income.get("low", 0.0),
        "office": req.office_m2_total,
        "shopping_centre": req.retail_m2_total,
        "light_industry": req.industry_m2_total,
        "warehouse_cold_storage": req.warehouse_m2,
        "public_services": req.public_services_m2,
        "hotel_guesthouse": req.hotel_m2,
    }


def test_car_fleet_positive_and_growing() -> None:
    fleet = car_fleet_by_period()
    prev = 0.0
    for p in PERIODS:
        assert fleet[p]["total"] > 0
        assert fleet[p]["total"] > prev          # everything grows with time
        prev = fleet[p]["total"]
    idx = fleet_growth_index()
    assert idx["2030"] == 1.0 and idx["2055"] > idx["2042"] > 1.0


def test_on_plot_audit_holds_every_period() -> None:
    audit = on_plot_absorption_audit()
    for p in PERIODS:
        assert audit[p]["fits_on_plot"], (
            f"{p}: resident cars no longer fit on-plot - the public-lot "
            f"model's core assumption broke: {audit[p]}")


def test_fleet_constraint_binds_and_counts_grow() -> None:
    req = _req()
    ecs = public_parking_ecs_by_period(_floors(req))
    for p in PERIODS:
        e = ecs[p]
        # the whole point of v2: stacked URDPFI rates exceed
        # the physical fleet, so the fleet constraint must be the binder
        assert e["binding"] == "fleet", e
        assert e["ecs"] <= e["fleet_peak_ecs"] + 1e-6
    cells = parking_cells_by_period(_floors(req))
    assert cells["2030"] < 74                    # the old over-supply is gone
    assert cells["2030"] <= cells["2042"] <= cells["2055"]


def test_requirements_wire_parking_and_solar() -> None:
    req = _req()
    assert req.required_cells_by_landuse[LandUse.PARKING_LOT] == \
        req.parking_cells_by_period["2030"]
    # B18.1 v2 (post-sweep ratification): the 2030 solar land grant is
    # 0.8 kWp/cap = 200,000 kWp, and the CELL COUNT that implies depends on
    # the land density, so it is DERIVED here rather than pinned. The literal
    # 200 that stood here corresponded to a density of 0.10 kWp/m2, which was
    # superseded on (-> 0.0714, 281 cells) and again on
    # -> 0.08022, 250 cells). It had therefore been RED for ten days
    # without anyone seeing it, because `f3_targeted_verify` does not include
    # this module - one of five that the nightly suite never runs. Deriving
    # the expectation from the same two config values the code uses means it
    # cannot go stale again on a density change.
    import math
    norms = load_demand_norms()
    cfg = load_config()
    dens = float(norms.solar["ground_mount_kwp_per_m2"])
    cell_m2 = float(cfg.site.get("cell_size_m", 100.0)) ** 2
    expected = math.ceil(req.solar_kwp_total / (cell_m2 * dens))
    assert req.required_cells_by_landuse[LandUse.SOLAR_FARM] == expected, (
        req.required_cells_by_landuse[LandUse.SOLAR_FARM], expected, dens)


def test_land_use_targets_sum_to_one() -> None:
    cfg = load_config()
    s = sum(cfg.land_use_targets.values())
    assert abs(s - 1.0) < 1e-6, s


def test_phased_expansion_tags_and_multipliers() -> None:
    from core.grid import make_thesis_grid
    from energy.network import phased_land_multipliers
    from layout.canal_corridor import apply_canal_corridor
    from layout.locked_zones import apply_locked_zones
    from layout.phased_expansion import apply_phased_expansion
    from layout.sector_structure import apply_sector_grid

    cfg = load_config()
    g = make_thesis_grid()
    apply_locked_zones(g, solar_cells=150)
    apply_sector_grid(g, sector_size_cells=8)
    apply_canal_corridor(g, cfg)
    # untagged: multipliers must be exactly 1.0 (byte-exact back-compat)
    mult0 = phased_land_multipliers(g)
    assert all(v == 1.0 for d in mult0.values() for v in d.values())

    # stamp jobs + a parking lot so the pass has anchors, then tag
    g.at(30, 30).land_use = LandUse.OFFICE
    g.at(30, 31).land_use = LandUse.PARKING_LOT
    counts = apply_phased_expansion(
        g, {"2030": 1, "2042": 3, "2055": 6}, cfg,
        farm_land_cells_by_period={"2030": 150, "2042": 200, "2055": 250})
    assert counts["solar_expansion_2042"] == 50
    assert counts["solar_expansion_2055"] == 50
    assert counts["parking_expansion_2042"] == 2
    assert counts["parking_expansion_2055"] == 3

    mult = phased_land_multipliers(g)
    n_farm = sum(1 for c in g.all_cells()
                 if c.land_use == LandUse.SOLAR_FARM)
    assert abs(mult["solar_farm"][2042] - (n_farm + 50) / n_farm) < 1e-9
    assert abs(mult["solar_farm"][2055] - (n_farm + 100) / n_farm) < 1e-9
    assert abs(mult["carport"][2042] - 3.0) < 1e-9     # 1 lot + 2 tags
    assert abs(mult["carport"][2055] - 6.0) < 1e-9     # + 3 more

    # solar growth parcels must hug the farm (adjacent expansion, not
    # confetti). 100 cells around a ~12x13 block necessarily reach a few
    # rings out (roads/locked cells interrupt the rings), so the bound is
    # Manhattan <= 6 for 90% - still "at the fence line", never scattered.
    farm_ids = {(c.row, c.col) for c in g.all_cells()
                if c.land_use == LandUse.SOLAR_FARM}
    tagged = [c for c in g.all_cells()
              if (c.amenity_subtype or "").startswith("solar_expansion")]
    near = sum(1 for c in tagged if any(
        abs(c.row - r) + abs(c.col - cc) <= 6 for (r, cc) in farm_ids))
    assert near >= len(tagged) * 0.9, f"solar growth scattered: {near}/{len(tagged)}"


def test_parking_lot_now_trimmable() -> None:
    from layout.requirements_trim import _TRIMMABLE
    assert LandUse.PARKING_LOT in _TRIMMABLE


def test_hourly_profiles_reported_and_fleet_still_binds() -> None:
    """B18.5 v3: the shared-parking hourly accumulation is computed and
    reported; the fleet constraint must STILL be the binder (the whole
    v2 insight survives the finer method)."""
    req = _req()
    ecs = public_parking_ecs_by_period(_floors(req))
    for p in PERIODS:
        e = ecs[p]
        assert e["profile_peak_ecs"] is not None
        # the accumulation peak must be BELOW the stacked all-uses total
        # (temporal sharing works: no hour has every use at 100%) - note it
        # MAY exceed the coarse day bucket (evening mall+restaurant+visitor
        # overlap), which is exactly what the hourly method exists to find
        assert e["profile_peak_ecs"] < (e["day_ecs"] + e["night_ecs"]), e
        assert e["profile_peak_ecs"] > 0
        #... but the physical fleet is still the binding ceiling
        assert e["binding"] == "fleet", e


def test_locked_parks_and_greenway_spine() -> None:
    """B18.4: 3 x 12-ha community parks + the linear greenway spine lock
    pre-anneal, survive the amenity-subtype wipe, and are preserved by the
    open-space tagger."""
    from core.grid import make_thesis_grid
    from layout.amenity_subtype import assign_amenity_subtypes
    from layout.canal_corridor import apply_canal_corridor
    from layout.locked_zones import apply_locked_zones
    from layout.park_structure import apply_locked_parks, locked_green_cells
    from layout.sector_structure import apply_sector_grid

    cfg = load_config()
    g = make_thesis_grid()
    apply_locked_zones(g, solar_cells=200)
    apply_sector_grid(g, sector_size_cells=8)
    apply_canal_corridor(g, cfg)
    out = apply_locked_parks(g, cfg)
    assert out["big_parks"] == 3, out
    assert out["park_cells"] == 36                    # 3 x 12 ha (~30 acres each)
    assert out["spine_cells"] >= 30                   # a real linear park (3+ km)
    before = locked_green_cells(g)
    assert len(before) == out["total_locked_green"]
    # the wipe pass must preserve the locked green tags (like the canal)
    req = _req()
    assign_amenity_subtypes(g, req)
    assert locked_green_cells(g) == before


def test_sector_greens_are_2_to_5_acres_and_spread() -> None:
    """B18.8 (the author: "smaller parks range ~2-5 acres... organised like
    Chandigarh"): every park_neighbourhood cluster is 1-2 cells (2.47 /
    4.94 acres on the 1-ha grid) and the greens are SPREAD across many
    sectors, not pooled in a corner."""
    from collections import deque
    from energy.network import grid_from_geojson
    from layout.open_space_structure import tag_open_space_structure
    from layout.road_network import configured_sector_size
    from layout.sector_structure import sector_id_of

    g, _ = grid_from_geojson()
    cfg = load_config()
    tag_open_space_structure(g, cfg)
    greens = {(c.row, c.col) for c in g.all_cells()
              if c.amenity_subtype == "park_neighbourhood"}
    assert greens, "no neighbourhood greens tagged"
    # 4-connected cluster sizes must be <= 2 cells (5 acres)
    seen: set = set()
    for start in sorted(greens):
        if start in seen:
            continue
        comp = 0
        dq = deque([start])
        seen.add(start)
        while dq:
            (r, c) = dq.popleft()
            comp += 1
            for nb in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if nb in greens and nb not in seen:
                    seen.add(nb)
                    dq.append(nb)
        assert comp <= 2, f"neighbourhood green cluster of {comp} cells (> 5 acres)"
    # spread: greens must reach a healthy majority of sectors
    size = configured_sector_size(cfg)
    sectors_with_green = {sector_id_of(g, r, c, size) for (r, c) in greens}
    assert len(sectors_with_green) >= 15, (
        f"greens pooled in only {len(sectors_with_green)} sectors")


if __name__ == "__main__":
    test_car_fleet_positive_and_growing()
    print("fleet ok")
    test_on_plot_audit_holds_every_period()
    print("on-plot audit ok")
    test_fleet_constraint_binds_and_counts_grow()
    print("fleet constraint ok")
    test_requirements_wire_parking_and_solar()
    print("requirements wiring ok")
    test_land_use_targets_sum_to_one()
    print("targets sum ok")
    test_phased_expansion_tags_and_multipliers()
    print("phased tags + multipliers ok")
    test_parking_lot_now_trimmable()
    print("trim coverage ok")
    test_hourly_profiles_reported_and_fleet_still_binds()
    print("hourly shared-parking profiles ok")
    test_locked_parks_and_greenway_spine()
    print("locked parks + greenway spine ok")
    test_sector_greens_are_2_to_5_acres_and_spread()
    print("sector greens 2-5 acres + spread ok")
    print("STAGE-B18 phasing tests passed.")
