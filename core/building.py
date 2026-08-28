"""Building objects derived from a populated Grid.

A Cell + LandUse + height + albedo is enough to describe layout shape, but
energy and cost calculations want a `Building` view: total floor area,
roof area, peak demand, AC flag, and so on.

The relationship from cell + height tier to households and energy is:

    footprint_area_m2 = cell_size^2 * footprint_coverage     (config)
    floors            = height_m / floor_to_floor_m
    total_floor_area  = footprint_area * floors
    households        = total_floor_area / household_floor_area_m2[income]
    base_load_kw      = total_floor_area * base_load_w_per_m2 / 1000
    cooling_load_kw   = total_floor_area * cooling_load_w_per_m2_peak / 1000

So a TALL ews tower (low_income_residential x tall) has many more
households than a TALL high-income tower of the same height, but its
energy demand is calculated from floor area, not households.

`Building` is a lightweight read-only projection; rebuild from the Grid
whenever the layout changes. Don't cache it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .config import DistrictConfig, load_config
from .grid import Cell, Grid, HeightTier
from .land_use import BuildingCategory, LandUse, category_for


@dataclass(frozen=True)
class Building:
    """A built cell viewed from its energy parameters.

    Attributes
    ----------
    cell_id : tuple[int, int]
        (row, col) - unique identifier.
    centre_x_m, centre_y_m : float
        Geographic centre of the cell.
    land_use : LandUse
    category : BuildingCategory
    height_m : float
        From the Cell. Determines floor count.
    height_tier : HeightTier or None
        Which tier (short / medium / tall) this building is in. None if the
        cell hasn't been assigned a tier yet (defaults to medium).
    floors : int
    footprint_area_m2 : float
    total_floor_area_m2 : float
    households : int
        Computed only for residential cells.
    roof_area_m2 : float
        Footprint area times the category's PV-deployable coverage.
    pv_acceptance : float
        Fraction of roof area realistically deployable for PV given
        ownership / structural / behavioural constraints.
    """

    cell_id: tuple[int, int]
    centre_x_m: float
    centre_y_m: float
    land_use: LandUse
    category: BuildingCategory
    height_m: float
    height_tier: Optional[HeightTier]
    floors: int
    footprint_area_m2: float
    total_floor_area_m2: float
    households: int
    roof_area_m2: float
    pv_acceptance: float
    # Module efficiency (kWp per m^2 of panel area at STC, i.e. 1000 W/m^2).
    # refactor: replaces the previous hardcoded "/6.0" rule (which
    # implied ~16.7% efficiency).
    # Ortho to pv_acceptance (usable-roof fraction) and capacity-factor (yield).
    #: default realigned 0.20 -> 0.1930 to match the live
    # value in district_composition.yaml (the ITRPV-anchored figure). The old
    # 0.20 silently encoded the pre- number, so any Building built without
    # the config got PV capacity 3.6% high. Real value flows in via
    # `building_from_cell(cell, cfg)`; this default is the no-config fallback.
    rooftop_module_efficiency: float = 0.1930

    @property
    def has_ac(self) -> bool:
        return self.category.has_ac

    @property
    def occupants(self) -> int:
        # rough estimate from households if residential; otherwise from category
        if self.land_use.is_residential and self.households > 0:
            avg_hh_size = {
                "low_income_residential": 4.5,
                "mid_income_residential": 4.0,
                "high_income_residential": 3.5,
            }.get(self.category.name, 4.0)
            return int(self.households * avg_hh_size)
        return self.category.occupants_per_cell

    @property
    def base_load_kw(self) -> float:
        """Non-cooling electrical peak = an AREA term + a PER-HOUSEHOLD term.

: appliances scale with the number of
        households, not with floor area - a family owns one fridge whether it
        lives in 43 m2 or 300 m2. Charging them per square metre made a
        high-income household draw 15.3x a low-income one, against the 4-5x
        `core/land_use.py` itself states as the design intent.
        `appliance_kw_per_household` is 0.0 for every non-residential category,
        so those stay purely area-scaled (correct: an office plug load really
        does scale with the floor plate) and this term is a no-op for them.
        """
        return (self.total_floor_area_m2 * self.category.base_load_w_per_m2 / 1000.0
                + self.households * self.category.appliance_kw_per_household)

    @property
    def peak_cooling_load_kw(self) -> float:
        if not self.category.has_ac:
            return 0.0
        return (self.total_floor_area_m2
                * self.category.cooling_load_w_per_m2_peak / 1000.0)

    @property
    def deployable_pv_kwp(self) -> float:
        """Rooftop PV nameplate capacity from roof area, acceptance, efficiency.

        Formula:
            kWp = roof_area_m2 * pv_acceptance * rooftop_module_efficiency

        Why the formula reads this way: 1 kWp at Standard Test Conditions
        is defined as 1000 W of DC output under 1000 W/m^2 irradiance.
        At module efficiency eta, 1 m^2 of panel produces eta * 1000 W,
        so it takes 1/eta m^2 of panel per kWp. For eta = 0.20 (2030
        Tier-1 mono-Si default) that's 5 m^2/kWp. The previous hardcoded
        "/6.0" implied ~16.7% efficiency (2024-era commodity panels).

        roof_area_m2 is the geometric roof area; pv_acceptance multiplies
        it down to the realistically deployable share (ownership / HVAC /
        skylights / aesthetic constraints).

        Yield-side modifiers (capacity factor, biosolar cooling, dust,
        degradation, BIPV) are applied DOWNSTREAM in the Stage B/C dispatch
        and do NOT affect this installed-kWp number.

        Returns
        -------
        float
            Deployable rooftop PV nameplate capacity in kWp.
        """
        usable_m2 = self.roof_area_m2 * self.pv_acceptance
        return usable_m2 * self.rooftop_module_efficiency


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
def _income_class_for(category_name: str) -> Optional[str]:
    """Map a residential category name to its income class key."""
    return {
        "low_income_residential": "low",
        "mid_income_residential": "mid",
        "high_income_residential": "high",
    }.get(category_name)


def building_from_cell(cell: Cell,
                       cfg: Optional[DistrictConfig] = None) -> Optional[Building]:
    """Project a Cell to a Building. Returns None for non-built cells.

    Floor-area model:
        floor_area = floor_area_per_cell_m2[category] * height_multiplier[tier]
    Households (residential only):
        households = floor_area / household_floor_area[income_class]
    Footprint (used for roof area):
        footprint = floor_area / floors

    Returns
    -------
    Optional[Building]
        A building projection for built cells, otherwise None.
    """
    if not cell.has_building:
        return None
    cat = category_for(cell.land_use)
    if cat is None:
        return None
    if cfg is None:
        cfg = load_config()

    # tier defaults to MEDIUM if not assigned
    tier = cell.height_tier or HeightTier.MEDIUM
    height_m = (cfg.height_for(tier.value)
                if cell.height_m == 0 else cell.height_m)
    floors = max(1, int(round(height_m / cfg.floor_to_floor_m)))

    # floor area = config baseline * tier multiplier
    base_floor_area = cfg.floor_area_for_category(cat.name)
    if base_floor_area == 0:
        # fallback to category default to keep things working
        base_floor_area = cat.floor_area_per_cell_m2
    total_floor_area = base_floor_area * cfg.height_multiplier_for(tier.value)

    # households only meaningful for residential cells
    households = 0
    income_cls = _income_class_for(cat.name)
    if income_cls:
        hh_floor_area = cfg.household_floor_area_for(income_cls)
        if hh_floor_area > 0:
            households = int(round(total_floor_area / hh_floor_area))

    # footprint implicit from floor_area / floors -> drives roof area
    footprint = total_floor_area / floors if floors > 0 else 0.0
    roof_area = footprint * cat.roof_pv_coverage
    acceptance = cfg.acceptance_for(cat.name)

    return Building(
        cell_id=(cell.row, cell.col),
        centre_x_m=cell.centre_x_m,
        centre_y_m=cell.centre_y_m,
        land_use=cell.land_use,
        category=cat,
        height_m=height_m,
        height_tier=tier,
        floors=floors,
        footprint_area_m2=footprint,
        total_floor_area_m2=total_floor_area,
        households=households,
        roof_area_m2=roof_area,
        pv_acceptance=acceptance,
        rooftop_module_efficiency=cfg.rooftop_module_efficiency,
    )


def buildings_from_grid(grid: Grid,
                        cfg: Optional[DistrictConfig] = None
                        ) -> List[Building]:
    """Return Building views for every built cell in the grid.

    Returns
    -------
    List[Building]
        Building projections in grid traversal order.
    """
    if cfg is None:
        cfg = load_config()
    out: List[Building] = []
    for cell in grid.all_cells():
        b = building_from_cell(cell, cfg)
        if b is not None:
            out.append(b)
    return out


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from .grid import make_thesis_grid

    cfg = load_config()
    g = make_thesis_grid()
    g.at(0, 0).land_use = LandUse.RESIDENTIAL_LOW
    g.at(0, 0).height_tier = HeightTier.TALL
    g.at(12, 12).land_use = LandUse.RESIDENTIAL_HIGH
    g.at(12, 12).height_tier = HeightTier.TALL
    g.at(24, 24).land_use = LandUse.SCHOOL

    bs = buildings_from_grid(g, cfg)
    print(f"{len(bs)} buildings projected")
    for b in bs:
        print(f"  {b.cell_id} {b.land_use.value:<25} "
              f"tier={(b.height_tier.value if b.height_tier else 'na'):<6} "
              f"floors={b.floors:2d}  "
              f"floor_area={b.total_floor_area_m2:>7.0f} m^2  "
              f"hh={b.households:>4}  "
              f"roof_pv={b.roof_area_m2:>5.0f} m^2  "
              f"accept={b.pv_acceptance:.2f}  "
              f"PV_kWp={b.deployable_pv_kwp:>5.1f}")
