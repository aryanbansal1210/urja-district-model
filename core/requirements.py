"""Translate demographics + demand norms into layout requirements.

This is a pure function:

    (Demographics + DemandNorms + DistrictConfig) -> Requirements

A `Requirements` object describes what the layout MUST contain to serve the
district's people: total floor area per land-use, count of facilities, and
the corresponding number of cells of each LandUse the optimiser must allocate.

The optimiser reads `Requirements` and either:
  * treats them as hard constraints (layout fails if it cannot satisfy them), or
  * treats them as soft objectives via a "feasibility gap" metric.

This module produces auditable numbers: every requirement traces back to
a demographic count and a norm. Print the report (`Requirements.summary`)
to defend the layout to a supervisor or planner.

Construction:
  required_residential_floor_per_class = households × hh_floor_area
  required_school_count                 = children × enrolment / students_per_school
  required_healthcare_beds              = pop × beds_per_1000 / 1000
  required_retail_m2                    = pop × retail_m2_per_capita
  required_office_m2                    = professionals × m2_per_worker
  required_industry_m2                  = industrial_workers × m2_per_worker
  required_hotel_rooms                  = pop × rooms_per_1000 / 1000
  required_open_space_m2                = pop × open_space_per_capita
  required_solar_kwp                    = pop × kwp_per_capita

Each requirement is then mapped to required CELL COUNTS per LandUse using the
floor-area-per-cell catalogue from DistrictConfig.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Dict, Optional

from .config import DistrictConfig, load_config
from .demographics import Demographics, DemandNorms, load_demand_norms, load_demographics
from .land_use import LandUse


# ---------------------------------------------------------------------------
# Income-tier aggregation (4 demographic tiers -> 3 residential land-uses)
# ---------------------------------------------------------------------------
# (Opus 4.8): the demographic layer (config/demographics.yaml) carries
# 4 PMAY-U income tiers EWS/LIG/MIG/HIG, but the layout + energy LP use 3
# residential LAND-USES. This map collapses the 4 tiers onto the 3 land-use keys.
# EWS + LIG share the low_income_residential land-use (both are affordable-housing
# typologies); MIG -> mid; HIG -> high.
_AGG_TIER_TO_LANDUSE = {
    "ews": "low", "lig": "low", "mig": "mid", "hig": "high",
    # identity for the legacy 3-key form (back-compat)
    "low": "low", "mid": "mid", "high": "high",
}


def _aggregate_income_tiers(by_tier: Dict[str, int]) -> Dict[str, int]:
    """Collapse a per-income-tier dict onto the 3 residential land-use keys.

    Accepts either the 4-tier form (ews/lig/mig/hig) or the legacy 3-tier form
    (low/mid/high); unknown keys are ignored. Returns a dict over low/mid/high.

    Returns
    -------
    Dict[str, int]
        Household counts keyed by residential land-use class (low/mid/high).
    """
    out = {"low": 0, "mid": 0, "high": 0}
    for tier, n in by_tier.items():
        lu = _AGG_TIER_TO_LANDUSE.get(tier)
        if lu is not None:
            out[lu] += int(n)
    return out


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------
@dataclass
class Requirements:
    """The layout MUST satisfy these to serve the district population."""

    # --- residential ---
    households_by_income: Dict[str, int] = field(default_factory=dict)
    residential_floor_m2_by_income: Dict[str, float] = field(default_factory=dict)

    # --- non-residential floor-area requirements ---
    school_students: int = 0
    primary_schools: int = 0
    secondary_schools: int = 0
    healthcare_beds_total: int = 0
    dispensaries: int = 0
    hospitals: int = 0
    retail_m2_total: float = 0.0                # enclosed shopping-centre share
    retail_highstreet_m2: float = 0.0           # NEW: linear ground-floor retail
    restaurant_seats: int = 0
    restaurant_m2: float = 0.0
    office_m2_total: float = 0.0
    public_services_m2: float = 0.0
    industry_m2_total: float = 0.0
    warehouse_m2: float = 0.0
    hotel_rooms: int = 0
    hotel_m2: float = 0.0
    religious_m2: float = 0.0                   # NEW: temples / gurudwaras / mosques
    open_space_m2: float = 0.0
    blue_space_m2: float = 0.0                  # NEW: ponds, tanks, lakes
    parking_ecs_total: float = 0.0              # NEW: URDPFI Equivalent Car Spaces
    parking_lot_m2: float = 0.0                 # NEW: consolidated surface-parking land
    # STAGE-B18: PHASED parking - lot cell counts per period
    # from the demand-driven car-fleet model (core/parking_demand.py).
    # ["2030"] becomes real PARKING_LOT cells; the 2042/2055 INCREMENTS
    # become parking_expansion_* reserve tags (layout/phased_expansion.py).
    parking_cells_by_period: Dict[str, int] = field(default_factory=dict)
    solar_kwp_total: float = 0.0

    # --- derived: minimum CELL COUNTS per LandUse the optimiser must place ---
    required_cells_by_landuse: Dict[LandUse, int] = field(default_factory=dict)

    def summary(self) -> str:
        """Return a human-readable, auditable summary.

        Returns
        -------
        str
            Multi-line report of derived floor area and cell requirements.
        """
        lines = []
        lines.append("Layout requirements derived from demographics x norms:")
        lines.append("-" * 60)
        lines.append("\nHouseholds and residential floor area:")
        for cls in ("low", "mid", "high"):
            n = self.households_by_income.get(cls, 0)
            f = self.residential_floor_m2_by_income.get(cls, 0.0)
            lines.append(f"  {cls:<6}: {n:>6,} hh   {f / 1e6:>5.2f} M m^2")

        lines.append("\nFacilities:")
        lines.append(f"  primary schools:       {self.primary_schools:>4} "
                     f"({self.school_students:,} students total)")
        lines.append(f"  secondary schools:     {self.secondary_schools:>4}")
        lines.append(f"  hospitals:             {self.hospitals:>4} "
                     f"({self.healthcare_beds_total} beds)")
        lines.append(f"  dispensaries:          {self.dispensaries:>4}")
        lines.append(f"  hotel rooms:           {self.hotel_rooms:>4}")

        lines.append("\nFloor area required (all m^2):")
        lines.append(f"  retail (mall):         {self.retail_m2_total:>10,.0f}")
        lines.append(f"  retail (high-street):  {self.retail_highstreet_m2:>10,.0f}")
        lines.append(f"  restaurant:            {self.restaurant_m2:>10,.0f}")
        lines.append(f"  office:                {self.office_m2_total:>10,.0f}")
        lines.append(f"  public services:       {self.public_services_m2:>10,.0f}")
        lines.append(f"  industry:              {self.industry_m2_total:>10,.0f}")
        lines.append(f"  warehouse:             {self.warehouse_m2:>10,.0f}")
        lines.append(f"  hotel:                 {self.hotel_m2:>10,.0f}")
        lines.append(f"  religious:             {self.religious_m2:>10,.0f}")
        lines.append(f"  open space:            {self.open_space_m2:>10,.0f}")
        lines.append(f"  blue space:            {self.blue_space_m2:>10,.0f}")
        lines.append(f"  parking ({self.parking_ecs_total:,.0f} ECS):  "
                     f"{self.parking_lot_m2:>10,.0f}")
        lines.append(f"\nSolar PV capacity target: {self.solar_kwp_total:>10,.0f} kWp")

        lines.append("\nMinimum required CELLS per land-use:")
        for lu, n in sorted(self.required_cells_by_landuse.items(),
                            key=lambda kv: -kv[1]):
            lines.append(f"  {lu.value:<28} {n:>4} cells")
        total = sum(self.required_cells_by_landuse.values())
        lines.append(f"  {'TOTAL':<28} {total:>4} cells")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
def derive_requirements(
    demographics: Optional[Demographics] = None,
    norms: Optional[DemandNorms] = None,
    cfg: Optional[DistrictConfig] = None,
) -> Requirements:
    """Compute layout requirements from demographics + norms + config.

    Pure function: same inputs always yield the same Requirements.

    Returns
    -------
    Requirements
        Derived layout demand object used by constraints and the optimiser.
    """
    demographics = demographics or load_demographics()
    norms = norms or load_demand_norms()
    cfg = cfg or load_config()

    req = Requirements()

    # ----- residential ------------------------------------------------
    # (Opus 4.8): demographics now has 4 income tiers (EWS/LIG/MIG/HIG)
    # but the layout + energy LP keep 3 residential LAND-USES. Aggregate the 4
    # demographic tiers -> 3 land-use keys (EWS+LIG->low, MIG->mid, HIG->high)
    # before computing residential floor area. Back-compatible: if demographics
    # still uses 3 keys (low/mid/high), the aggregation is an identity.
    hh = _aggregate_income_tiers(demographics.households_by_income())
    req.households_by_income = dict(hh)
    for cls in ("low", "mid", "high"):
        hh_n = hh.get(cls, 0)
        hh_floor = cfg.household_floor_area_for(cls)
        req.residential_floor_m2_by_income[cls] = hh_n * hh_floor

    pop = demographics.total_population

    # ----- education (URDPFI 2014 population-per-facility) -------------
    children = demographics.children_count()
    enrolled = int(round(children * demographics.school_enrolment_rate))
    req.school_students = enrolled
    edu = norms.education
    pop_per_primary = edu.get("population_per_primary_school", 5000)
    pop_per_secondary = edu.get("population_per_secondary_school", 7500)
    req.primary_schools = ceil(pop / pop_per_primary)
    req.secondary_schools = ceil(pop / pop_per_secondary)
    school_floor_m2 = (
        req.primary_schools * edu.get("floor_m2_per_primary_school", 2500)
        + req.secondary_schools * edu.get("floor_m2_per_secondary_school", 5000)
    )

    # ----- healthcare (IPHS 2022 facility-per-population) --------------
    hc = norms.healthcare
    total_beds = int(round(pop * hc.get("beds_per_1000_population", 3.0) / 1000))
    req.healthcare_beds_total = total_beds  # kept for the audit report
    n_uphc = ceil(pop / hc.get("population_per_uphc", 50000))
    n_uchc = ceil(pop / hc.get("population_per_uchc", 275000))
    req.dispensaries = n_uphc   # UPHC ~ primary-care facilities
    req.hospitals = n_uchc      # UCHC ~ hospitals
    healthcare_floor_m2 = (
        n_uphc * hc.get("floor_m2_per_uphc", 1500)
        + n_uchc * hc.get("floor_m2_per_uchc", 14000)
    )

    # ----- retail / restaurants --------------------------------------
    retail = norms.retail
    retail_m2 = pop * retail.get("m2_per_capita", 4.0)
    req.retail_m2_total = retail_m2 * retail.get("share_in_shopping_centre", 0.5)
    req.retail_highstreet_m2 = retail_m2 * retail.get("share_in_highstreet", 0.20)
    seats = pop * retail.get("restaurant_seats_per_1000_pop", 30) / 1000.0
    req.restaurant_seats = int(round(seats))
    req.restaurant_m2 = seats * retail.get("m2_per_restaurant_seat", 2.5)

    # ----- office / public services ----------------------------------
    workers = demographics.workers_by_sector()
    professional_n = workers.get("professional_office", 0)
    public_n = workers.get("public_services", 0)
    req.office_m2_total = (professional_n
                           * norms.office.get("m2_per_professional_worker", 10.0))
    req.public_services_m2 = (public_n
                              * norms.office.get("m2_per_public_services_worker", 12.0))

    # ----- industry / warehouse --------------------------------------
    industrial_n = workers.get("industry", 0)
    req.industry_m2_total = (industrial_n
                             * norms.industry.get("m2_per_industrial_worker", 30.0))
    req.warehouse_m2 = (industrial_n
                        * norms.industry.get("warehouse_m2_per_industrial_worker", 8.0))

    # ----- hospitality -----------------------------------------------
    hosp = norms.hospitality
    rooms = int(round(pop * hosp.get("hotel_rooms_per_1000_pop", 1.5) / 1000))
    req.hotel_rooms = rooms
    req.hotel_m2 = rooms * hosp.get("m2_per_hotel_room", 35.0)

    # ----- open / blue space -----------------------------------------
    req.open_space_m2 = pop * norms.open_space.get("m2_per_capita_total", 12.0)
    req.blue_space_m2 = pop * norms.blue_space.get("m2_per_capita_total", 4.0)

    # ----- religious facilities --------------------------------------
    req.religious_m2 = pop * norms.religious.get("m2_per_capita", 2.0)

    # ----- parking (STAGE-B18 demand-driven, phased) -------------------
    # (register B18.3,: public lots serve the
    # commercial/institutional uses' workers (incl. out-of-town commuters)
    # + visitors; RESIDENT cars park on-plot (flats stilt/podium, kothis on
    # their plots - audited per period against the car fleet by
    # core/parking_demand.on_plot_absorption_audit); demand = max(DAY,
    # NIGHT) so a commuter's car is never counted at home AND at work; lot
    # count scales with the car fleet per period (2030 -> real cells,
    # 2042/2055 increments -> parking_expansion reserve tags).
    parking = norms.parking or {}
    parking_floor_by_use = {
        "high_income_residential": req.residential_floor_m2_by_income.get("high", 0.0),
        "mid_income_residential": req.residential_floor_m2_by_income.get("mid", 0.0),
        "low_income_residential": req.residential_floor_m2_by_income.get("low", 0.0),
        "office": req.office_m2_total,
        "shopping_centre": req.retail_m2_total,
        #: these four have BUILT FLOOR AREA and were feeding
        # NOTHING, so they generated zero public-parking demand. Rates for them
        # now exist in demand_norms (URDPFI Table 8.11 local-shopping row for
        # highstreet; Table 8.12 public/semi-public for school + religious,
        # commercial for restaurants) - but a rate with no floor behind it is
        # just more dead config, which is the mistake repeated. Wired.
        # CHANGES NOTHING: the fleet cap binds ~10x below the stacked URDPFI
        # peak, so parking stays 17/23/33 cells (verified). See
        "school": school_floor_m2,
        "retail_highstreet": req.retail_highstreet_m2,
        "religious": req.religious_m2,
        "restaurant_food_service": req.restaurant_m2,
        "light_industry": req.industry_m2_total,
        "warehouse_cold_storage": req.warehouse_m2,
        "healthcare": healthcare_floor_m2,
        "public_services": req.public_services_m2,
        "hotel_guesthouse": req.hotel_m2,
    }
    from .parking_demand import (
        parking_cells_by_period, public_parking_ecs_by_period,
    )
    _ecs_by_period = public_parking_ecs_by_period(parking_floor_by_use,
                                                  norms, demographics)
    req.parking_ecs_total = _ecs_by_period["2030"]["ecs"]
    req.parking_lot_m2 = req.parking_ecs_total * parking.get("m2_per_ecs", 23)
    req.parking_cells_by_period = parking_cells_by_period(
        parking_floor_by_use, cfg, norms, demographics)

    # ----- solar capacity target -------------------------------------
    req.solar_kwp_total = pop * norms.solar.get("target_kwp_per_capita", 1.0)

    # ----- map floor-area requirements to required cell counts ------
    # uses cfg.floor_area_for_category at the MEDIUM tier as a divisor.
    # STAGE-: the area-divided land uses (open/blue/parking/
    # solar) previously hardcoded the 200 m cell area (200*200); they now
    # read site.cell_size_m so the 100 m re-grid flows through from config
    # (single source of truth with core/grid.py make_thesis_grid).
    cell_area_m2 = float(cfg.site.get("cell_size_m", 100.0)) ** 2

    def cells_for(land_use: LandUse, required_floor_m2: float) -> int:
        cat_name = {
            LandUse.RESIDENTIAL_LOW: "low_income_residential",
            LandUse.RESIDENTIAL_MID: "mid_income_residential",
            LandUse.RESIDENTIAL_HIGH: "high_income_residential",
            LandUse.SCHOOL: "school",
            LandUse.OFFICE: "office",
            LandUse.SHOPPING_CENTRE: "shopping_centre",
            LandUse.RETAIL_HIGHSTREET: "retail_highstreet",
            LandUse.RESTAURANT_FOOD: "restaurant_food_service",
            LandUse.HOTEL_GUESTHOUSE: "hotel_guesthouse",
            LandUse.HEALTHCARE: "healthcare",
            LandUse.LIGHT_INDUSTRY: "light_industry",
            LandUse.WAREHOUSE: "warehouse_cold_storage",
            LandUse.PUBLIC_SERVICES: "public_services",
            LandUse.RELIGIOUS: "religious",
        }.get(land_use)
        if cat_name is None:
            return 0
        per_cell = cfg.floor_area_for_category(cat_name)
        if per_cell <= 0:
            return 0
        return ceil(required_floor_m2 / per_cell)

    req.required_cells_by_landuse = {
        LandUse.RESIDENTIAL_LOW: cells_for(
            LandUse.RESIDENTIAL_LOW,
            req.residential_floor_m2_by_income.get("low", 0.0),
        ),
        LandUse.RESIDENTIAL_MID: cells_for(
            LandUse.RESIDENTIAL_MID,
            req.residential_floor_m2_by_income.get("mid", 0.0),
        ),
        LandUse.RESIDENTIAL_HIGH: cells_for(
            LandUse.RESIDENTIAL_HIGH,
            req.residential_floor_m2_by_income.get("high", 0.0),
        ),
        LandUse.SCHOOL: max(cells_for(LandUse.SCHOOL, school_floor_m2), 1),
        LandUse.OFFICE: cells_for(LandUse.OFFICE, req.office_m2_total),
        LandUse.SHOPPING_CENTRE: cells_for(
            LandUse.SHOPPING_CENTRE, req.retail_m2_total,
        ),
        LandUse.RETAIL_HIGHSTREET: cells_for(
            LandUse.RETAIL_HIGHSTREET, req.retail_highstreet_m2,
        ),
        LandUse.RESTAURANT_FOOD: cells_for(
            LandUse.RESTAURANT_FOOD, req.restaurant_m2,
        ),
        LandUse.HOTEL_GUESTHOUSE: cells_for(
            LandUse.HOTEL_GUESTHOUSE, req.hotel_m2,
        ),
        LandUse.HEALTHCARE: max(cells_for(LandUse.HEALTHCARE, healthcare_floor_m2), 1),
        LandUse.LIGHT_INDUSTRY: cells_for(
            LandUse.LIGHT_INDUSTRY, req.industry_m2_total,
        ),
        LandUse.WAREHOUSE: cells_for(LandUse.WAREHOUSE, req.warehouse_m2),
        LandUse.PUBLIC_SERVICES: cells_for(
            LandUse.PUBLIC_SERVICES, req.public_services_m2,
        ),
        LandUse.RELIGIOUS: cells_for(LandUse.RELIGIOUS, req.religious_m2),
        # open space, blue space, solar farm: divide by cell area
        LandUse.OPEN_SPACE: ceil(
            req.open_space_m2 / cell_area_m2
        ),
        LandUse.BLUE_SPACE: ceil(
            req.blue_space_m2 / cell_area_m2
        ),
        # parking lot: the B18 demand-driven 2030 count (single source of
        # truth with the phased table; 2042/2055 increments are reserve tags)
        LandUse.PARKING_LOT: req.parking_cells_by_period.get("2030", 0),
        LandUse.SOLAR_FARM: ceil(
            req.solar_kwp_total
            / (cell_area_m2 * norms.solar.get("ground_mount_kwp_per_m2", 0.10))
        ),
    }

    return req


if __name__ == "__main__":
    req = derive_requirements()
    print(req.summary())
    print("\n(grid is 2,500 cells of 100 m x 100 m = 25 km^2; Stage-F1 re-grid)")
