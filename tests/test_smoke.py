"""Smoke tests for district_v3 stage 1 + foundation polish."""

from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import load_config                  # noqa: E402
from core.grid import HeightTier, make_thesis_grid    # noqa: E402
from core.land_use import (                          # noqa: E402
    DEFAULT_AREA_TARGETS, LandUse, validate_targets,
)
from core.building import buildings_from_grid        # noqa: E402
from layout.generator import ARCHETYPES, generate    # noqa: E402


def test_area_targets_sum_to_one() -> None:
    validate_targets()


def test_config_loads_and_validates() -> None:
    cfg = load_config(force_reload=True)
    assert abs(sum(cfg.land_use_targets.values()) - 1.0) < 0.01
    assert abs(sum(cfg.income_shares.values()) - 1.0) < 0.01
    # "ground" joined for Baseline 2 v7 (G+1/G+2 solo houses;
    # no designed-town cell uses it - see core.grid.HeightTier.GROUND).
    assert set(cfg.height_tiers) == {"ground", "short", "medium", "tall"}
    assert set(cfg.height_multipliers) == {"ground", "short", "medium", "tall"}
    assert cfg.height_multipliers["ground"] < cfg.height_multipliers["short"]
    # multipliers in expected order
    assert (cfg.height_multipliers["short"]
            < cfg.height_multipliers["medium"]
            < cfg.height_multipliers["tall"])


def test_thesis_grid_shape() -> None:
    # STAGE-: re-gridded 200 m -> 100 m (register 0f).
    g = make_thesis_grid()
    assert g.n_rows == 50 and g.n_cols == 50
    assert g.cell_size_m == 100.0
    assert g.total_cells == 2500
    assert abs(g.total_area_m2 - 25e6) < 1e-3


def test_each_archetype_runs() -> None:
    for name in ARCHETYPES:
        grid = generate(name)
        assert grid.total_cells == 2500
        residential = sum(
            1 for c in grid.all_cells() if c.land_use.is_residential
        )
        assert residential > 0, f"{name} produced no residential cells"


def test_chandigarh_has_industry_on_east_edge() -> None:
    # STAGE-: check the east THIRD parametrically (the
    # compact-town seed puts the indwh sector at sector-col 4 = the east
    # band; the old hardcoded cols 20-25 assumed the 25x25 grid).
    grid = generate("chandigarh_sector")
    east_start = grid.n_cols * 2 // 3
    east_industry = sum(
        1 for r in range(grid.n_rows)
        for c in range(east_start, grid.n_cols)
        if grid.at(r, c).land_use == LandUse.LIGHT_INDUSTRY
    )
    assert east_industry > 0, "expected industry on the east edge"


def test_residential_cells_have_height_tiers() -> None:
    grid = generate("chandigarh_sector")
    res_cells = [c for c in grid.all_cells() if c.is_residential]
    assert len(res_cells) > 0
    # all residential cells assigned a tier
    tiers_seen = {c.height_tier for c in res_cells}
    assert HeightTier.MEDIUM in tiers_seen, "expected at least medium tier"


def test_buildings_have_realistic_household_count() -> None:
    """Total district households near the top-down target.

    STAGE-: the design town is 250k people =
    54,346 households (4.6 p/HH NSS-78); the chandigarh SEED approximates
    the compact-town targets so its bottom-up count should land within
    ~25% of the target (the SA + requirements-trim close the residual).
    """
    cfg = load_config()
    grid = generate("chandigarh_sector")
    bs = buildings_from_grid(grid, cfg)
    total_hh = sum(b.households for b in bs)
    assert 40_000 < total_hh < 68_000, (
        f"chandigarh produced {total_hh} households; "
        f"expected ~54,346 (250k / 4.6 p/HH)"
    )


def test_buildings_have_pv_acceptance_and_roof_area() -> None:
    cfg = load_config()
    for name in ARCHETYPES:
        grid = generate(name)
        bs = buildings_from_grid(grid, cfg)
        assert len(bs) > 0
        assert any(b.roof_area_m2 > 0 for b in bs)
        assert any(b.deployable_pv_kwp > 0 for b in bs)
        # acceptance always in [0, 1]
        for b in bs:
            assert 0.0 <= b.pv_acceptance <= 1.0


def test_rooftop_pv_kwp_scales_with_module_efficiency() -> None:
    """deployable_pv_kwp should scale linearly with rooftop_module_efficiency.

 refactor: replaces the hardcoded "/6.0" rule (~16.7% eff)
    with an explicit module-efficiency parameter. This test pins that
    behaviour so a future regression that hard-codes the formula again
    will fail loudly.
    """
    from dataclasses import replace
    from core.building import Building

    cfg = load_config()
    grid = generate("chandigarh_sector")
    bs_default = buildings_from_grid(grid, cfg)
    # Pick a built cell with a non-trivial roof
    sample = next(b for b in bs_default if b.roof_area_m2 > 0)
    base_kwp = sample.deployable_pv_kwp

    # Re-derive at double and half the module efficiency.
    #: the doubled/halved values are now DERIVED from the
    # configured efficiency instead of hardcoded 0.40 / 0.10. Those literals
    # silently encoded a 0.20 default, so when moved the config to
    # 0.1930 (the ITRPV-anchored value) this test failed for a reason that
    # had nothing to do with the linearity it exists to protect. The property
    # under test is that kWp scales linearly with efficiency; pin the
    # property, not a pair of numbers.
    base_eff = sample.rooftop_module_efficiency
    assert base_eff > 0, "sample has no module efficiency to scale"
    high_eff = replace(sample, rooftop_module_efficiency=2.0 * base_eff)
    low_eff = replace(sample, rooftop_module_efficiency=0.5 * base_eff)
    assert abs(high_eff.deployable_pv_kwp - 2.0 * base_kwp) < 1e-6, (
        f"Expected kWp to double from {base_kwp:.2f} to "
        f"{high_eff.deployable_pv_kwp:.2f} when efficiency "
        f"{base_eff:.4f} -> {2.0 * base_eff:.4f}"
    )
    assert abs(low_eff.deployable_pv_kwp - 0.5 * base_kwp) < 1e-6


def test_rooftop_pv_kwp_no_longer_uses_hardcoded_6_m2() -> None:
    """Regression: with module efficiency 0.20, kWp = m^2 * 0.20, NOT m^2 / 6.

    Pins the refactor against a re-introduction of the previous
    hardcoded 6.0 m^2/kWp constant. The two formulas differ by ~20% at
    eta=0.20 so any sample with non-zero roof area shows the gap.
    """
    cfg = load_config()
    grid = generate("chandigarh_sector")
    bs = buildings_from_grid(grid, cfg)
    sample = next(b for b in bs if b.roof_area_m2 > 0)
    usable_m2 = sample.roof_area_m2 * sample.pv_acceptance
    # Old formula:
    old_kwp = usable_m2 / 6.0
    # New formula:
    new_kwp = usable_m2 * sample.rooftop_module_efficiency
    assert abs(sample.deployable_pv_kwp - new_kwp) < 1e-6
    # They MUST differ at the default eta=0.20 (1/6 ~= 0.1667 vs 0.20)
    assert abs(new_kwp - old_kwp) / old_kwp > 0.15, (
        f"New formula ({new_kwp:.2f}) too close to old ({old_kwp:.2f}); "
        f"refactor not actually applied or efficiency reverted to 1/6"
    )


def test_solar_farm_capacity_independent_of_rooftop_efficiency() -> None:
    """SOLAR_FARM kWp uses the demand_norms.solar.ground_mount_kwp_per_m2
    LAND-density parameter, NOT the rooftop module efficiency. Confirms
    the two PV-area conversion factors are independent after the refactor.
    """
    from energy.network import EnergyNetwork
    from core.demographics import load_demand_norms
    norms = load_demand_norms(force_reload=True)
    assert "ground_mount_kwp_per_m2" in norms.solar
    gm = float(norms.solar["ground_mount_kwp_per_m2"])
    # band widened downward for the HONEST density: 0.0714
    # kWp/m2 = 3.5 acres/MWdc GROSS (incl. internal roads/setbacks; the
    # ~50-line citation block in demand_norms.yaml). The old 0.08 floor
    # described NET array-area density, which is a different denominator.
    assert 0.06 <= gm <= 0.25, (
        f"ground_mount_kwp_per_m2 = {gm}; expected 0.06-0.25 (gross land-density)"
    )
    # And it should NOT equal the rooftop module efficiency by accident
    cfg = load_config()
    assert abs(gm - cfg.rooftop_module_efficiency) > 0.01, (
        "ground_mount_kwp_per_m2 should differ from rooftop_module_efficiency"
    )


def test_tall_low_income_has_more_households_than_tall_high() -> None:
    """Same height tier, low-income packs more HH than high-income."""
    cfg = load_config()
    grid = make_thesis_grid()
    grid.at(5, 5).land_use = LandUse.RESIDENTIAL_LOW
    grid.at(5, 5).height_tier = HeightTier.TALL
    grid.at(5, 5).height_m = cfg.height_for("tall")
    grid.at(10, 10).land_use = LandUse.RESIDENTIAL_HIGH
    grid.at(10, 10).height_tier = HeightTier.TALL
    grid.at(10, 10).height_m = cfg.height_for("tall")

    bs = buildings_from_grid(grid, cfg)
    low_hh = next(b.households for b in bs if b.cell_id == (5, 5))
    high_hh = next(b.households for b in bs if b.cell_id == (10, 10))
    assert low_hh > high_hh, (
        f"Tall low-income cell has {low_hh} HH; "
        f"tall high-income cell has {high_hh}. Expected low > high."
    )


if __name__ == "__main__":
    test_area_targets_sum_to_one()
    test_config_loads_and_validates()
    test_thesis_grid_shape()
    test_each_archetype_runs()
    test_chandigarh_has_industry_on_east_edge()
    test_residential_cells_have_height_tiers()
    test_buildings_have_realistic_household_count()
    test_buildings_have_pv_acceptance_and_roof_area()
    test_rooftop_pv_kwp_scales_with_module_efficiency()
    test_rooftop_pv_kwp_no_longer_uses_hardcoded_6_m2()
    test_solar_farm_capacity_independent_of_rooftop_efficiency()
    test_tall_low_income_has_more_households_than_tall_high()
    print("All smoke tests passed.")
