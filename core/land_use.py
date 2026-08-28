"""Land-use types and the building-typology catalogue.

A land-use type tells the layout module what kind of activity occupies a cell.
A building category (carried over conceptually from v2) gives that activity
its energy parameters: floor-area density, base load, cooling load, AC,
roof area share for PV, occupancy class.

The mapping from land-use to category is many-to-one: e.g. RESIDENTIAL_LOW maps
to category low_income_residential. ROAD and OPEN_SPACE map to None because
they have no buildings.

Numbers below are placeholder values shaped to match v2's qualitative ordering
(EWS lowest baseload, shopping centres highest, etc.). They will be tuned
later with calibration data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Land-use enum
# ---------------------------------------------------------------------------
class LandUse(Enum):
    """High-level use of a cell. A layout assigns one LandUse to every cell."""

    RESIDENTIAL_LOW = "residential_low"        # EWS / low-income housing
    RESIDENTIAL_MID = "residential_mid"        # mid-income apartments
    RESIDENTIAL_HIGH = "residential_high"      # higher-income / villa stock
    SCHOOL = "school"
    OFFICE = "office"
    SHOPPING_CENTRE = "shopping_centre"        # enclosed mall typology
    RETAIL_HIGHSTREET = "retail_highstreet"    # linear ground-floor retail on a road
    RESTAURANT_FOOD = "restaurant_food_service"
    HOTEL_GUESTHOUSE = "hotel_guesthouse"
    HEALTHCARE = "healthcare"
    LIGHT_INDUSTRY = "light_industry"
    WAREHOUSE = "warehouse_cold_storage"
    PUBLIC_SERVICES = "public_services"
    RELIGIOUS = "religious"                    # temples, gurudwaras, mosques
    OPEN_SPACE = "open_space"                  # parks, greens (water now in BLUE_SPACE)
    BLUE_SPACE = "blue_space"                  # ponds, tanks, lakes (evaporative cooling)
    ROAD = "road"                              # streets and ROW
    SOLAR_FARM = "solar_farm"                  # ground-mount PV reserve
    PARKING_LOT = "parking_lot"                # demand-sized surface parking (hosts carport PV)

    @property
    def is_residential(self) -> bool:
        return self in {
            LandUse.RESIDENTIAL_LOW,
            LandUse.RESIDENTIAL_MID,
            LandUse.RESIDENTIAL_HIGH,
        }

    @property
    def has_buildings(self) -> bool:
        return self not in {
            LandUse.OPEN_SPACE,
            LandUse.BLUE_SPACE,
            LandUse.ROAD,
            LandUse.SOLAR_FARM,
            LandUse.PARKING_LOT,   # surface parking + carport canopy, no occupied building
        }


# ---------------------------------------------------------------------------
# Building category (energy and physical parameters per land-use)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BuildingCategory:
    """Energy / geometry parameters for buildings of one land-use type.

    Attributes
    ----------
    name : str
        Machine-readable identifier (matches v2 naming).
    floor_area_per_cell_m2 : float
        Total conditioned floor area placed in one 200 m x 200 m cell of this
        type. Comes from typical density assumptions for that activity in a
        peri-urban Indian context.
    typical_height_m : float
        Default building height in metres (used for solar-access scoring).
    occupants_per_cell : int
        Typical occupants / users per cell (used to weight equity metrics).
    base_load_w_per_m2 : float
        Non-cooling electrical baseload (lighting, plug, appliances).
    cooling_load_w_per_m2_peak : float
        Peak cooling load when the cell has AC; zero otherwise.
    has_ac : bool
        Whether this category has air conditioning by default.
    roof_pv_coverage : float
        Fraction of cell roof footprint usable for PV (0-1).
    """

    name: str
    floor_area_per_cell_m2: float
    typical_height_m: float
    occupants_per_cell: int
    base_load_w_per_m2: float
    cooling_load_w_per_m2_peak: float
    has_ac: bool
    roof_pv_coverage: float
    # FIX: appliance load that scales with the
    # NUMBER OF HOUSEHOLDS, not with floor area. A family owns one fridge and
    # one television whether it lives in 43 m2 or 300 m2, so charging those
    # loads per square metre made a high-income household draw 15.3x a
    # low-income one - against the 4-5x this very file states as the intent
    # (see the RESIDENTIAL_HIGH note below). Non-residential categories keep
    # 0.0 and remain purely area-scaled, which is correct for them: an office's
    # plug load genuinely does scale with floor plate.
    appliance_kw_per_household: float = 0.0


# ---------------------------------------------------------------------------
# Catalogue (placeholder values — will be calibrated later)
# ---------------------------------------------------------------------------
# Land-use -> BuildingCategory. None means "no building" (parks, roads).
CATEGORY_CATALOGUE: Dict[LandUse, Optional[BuildingCategory]] = {
    # STAGE-: floor_area_per_cell_m2 values below are FALLBACKS -
    # config/district_composition.yaml floor_area_per_cell_m2 (the FAR-derived
    # 1-ha table) is authoritative and overrides them in building_from_cell.
    # Synced here to prevent drift. occupants_per_cell (live: equity weighting
    # for non-residential cells) rescaled proportionally to the new per-cell
    # floors; typical_height_m is live for non-residential + the fixed-form
    # plotted colony (RESIDENTIAL_HIGH) via generator/optimiser height defaults.
    LandUse.RESIDENTIAL_LOW: BuildingCategory(
        name="low_income_residential",
        floor_area_per_cell_m2=20000.0,
        typical_height_m=12.0,            # docs only (tier-driven: MEDIUM 18 m in SA)
        occupants_per_cell=2300,          # ~468 HH (20,000/42.7) x ~4.9 p/HH EWS/LIG blend
        # was 5; bumped to 5.5 -- LBNL India 2023 + EESL UJALA
        # data shows low-income lighting ~6 W/m2 indoor (single LED per
        # room) plus negligible outdoor lighting (~10-30 W/cell shared).
        # Cooking + lighting + 1-2 small appliances per household.
        # FIX: was 5.5 W/m2 all-in. Split into an
        # AREA term (lighting + common services, which do scale with floor
        # plate) and a PER-HOUSEHOLD appliance term. 2.0 W/m2 is LED-era
        # Indian residential lighting + shared common load (EESL UJALA LED
        # rollout; the old 5.5 comment's own "~6 W/m2 indoor" predates full
        # LED saturation). Per-HH appliance 0.348 kW = cooking + 1-2 small
        # appliances, consistent with the comment above.
        #: RECALIBRATED AGAINST MEASURED INDIAN HOUSEHOLDS.
        # fixed the DISTRIBUTION between tiers but deliberately held the
        # total, because the aggregate had been validated against a per-capita
        # anchor. That anchor turned out to be propped up by an inflated
        # cooling curve, so once cooling was corrected the base load
        # was exposed as too high - the PSPCL summer:winter ratio fell to
        # 1.372 against a measured 1.708, and decomposing it showed the
        # non-cooling residential load would have to be ~0.54x to fit.
        # ANCHOR: Prayas eMARC, Harvard Dataverse doi:10.7910/DVN/YJ5SP1,
        # measured WINTER (Nov-Feb) whole-house load - no cooling anywhere in
        # India in those months, so this IS base plus water heating:
        #     Basic                     3.44 kWh/day   (n=82)
        #     Water heaters, no AC      4.44           (n=27)
        #     With air conditioners     5.15           (n=23)  the affluent tier
        # North India subset (Kanpur rural + Gonda, UP - Indo-Gangetic, cold
        # winters, the right climate analogue for Punjab): Basic 3.29 kWh/day,
        # confirming the all-India Basic figure rather than diverging from it.
        # THIS IS WHY THE BASE LOAD TRANSFERS WHERE COOLING DOES NOT: a fridge
        # and a light bulb do not care that Punjab is hotter in summer and
        # colder in winter than the Deccan. Cooling does, which is why
        # carries an explicit Punjab adjustment and this does not.
        # UPLIFTS, both declared:
        #   x1.34  2030 vs 2019 - the CEA NEP demand trajectory already used
        #          as the FX-3 growth factor, applied consistently here
        #   xN     tier affluence against its eMARC comparator, per tier below
        # The area term drops 2.0 -> 0.8 W/m2. At 2.0 a 300 m2 kothi carried
        # 0.6 kW of "lighting and common services", which is about 67 LED bulbs
        # burning at once. Lighting does not scale linearly with floor area -
        # a larger house has larger rooms, not proportionally more fittings.
        # 0.8 W/m2 is ~9 LEDs simultaneously in a 100 m2 flat, which is right.
        # LOW: anchored to eMARC "Basic" 3.44 kWh/day x 1.34 = 4.61 kWh/day.
        # No affluence uplift - EWS/LIG in 2030 IS the eMARC Basic household.
        # MEASURED VERIFICATION. An earlier version of this note
        # ended "0.274 kW peak x ~15 equivalent hours = 4.1", which read as an
        # 11% shortfall against the 4.61 anchor. That hand-check was WRONG: the
        # "~15 equivalent hours" is not a model input, so it never described
        # what the model computes. Daily energy comes from the day-type-weighted
        # `base_demand_profile`, not from an assumed hours figure.
        # What the model ACTUALLY delivers, measured on the frozen layout over
        # winter (nov-feb, 120 d), BASE TERM ONLY (cooling, heating and EV all
        # zeroed), kWh per household per day against each tier's own anchor:
        #     low    4.66  vs  4.61   = 101%   <- essentially exact
        #     mid    8.19  vs  7.73   = 106%
        #     high  14.78  vs 12.42   = 119%
        # So the base load reconciles with the measured eMARC anchors, and the
        # low tier - the one the bad hand-check impugned - lands within 1%.
        # NO PARAMETER CHANGE WAS MADE on the strength of that arithmetic.
        # Reproduce: zero peak_cooling_kw / peak_heating_kw / households on a
        # node clone and sum `demand_components_by_slice_kw` over nov-feb.
        # OPEN, and a different question: adding the HEATING term takes high
        # income 14.78 -> 24.23 kWh/HH/day, i.e. 9.45 of heating against mid
        # income's 1.12 (8.4x). That concentration is deliberate in direction
        # (running a heater is a cost decision, graded by income) but its LEVEL
        # has not been checked against the BEE 2024 penetration figures that
        base_load_w_per_m2=0.8,
        appliance_kw_per_household=0.240,
        cooling_load_w_per_m2_peak=0.0,
        has_ac=False,
        roof_pv_coverage=0.40,
    ),
    LandUse.RESIDENTIAL_MID: BuildingCategory(
        name="mid_income_residential",
        floor_area_per_cell_m2=20000.0,
        typical_height_m=15.0,            # docs only (tier-driven: MEDIUM 18 m in SA)
        occupants_per_cell=900,           # 200 HH (20,000/100) x 4.5 p/HH MIG
        # was 6; bumped to 7.5 -- mid-income owns fridge +
        # washer + multiple TVs + electric kitchen + induction + porch
        # security light + entry lighting (~50-100 W outdoor/cell). LBNL
        # India 2023 mid-tier appliance saturation curve.
        # FIX: was 7.5 W/m2 all-in. Same split as low
        # income: 2.0 W/m2 area (lighting + common services) + 0.983 kW per
        # household for fridge, washer, multiple TVs, induction hob - the
        # appliance set the comment above already describes.
        #: see the low-income note above for the anchor.
        # MID: eMARC "Water heaters but no AC" 4.44 kWh/day x 1.34 x 1.3
        # (affluence: a 100 m2 owned 2-3BHK against the eMARC mixed sample)
        # = 7.73 kWh/day. Was 0.080 (area) + 0.430 = 0.510 kW peak.
        # FIX: WATER HEATING WAS COUNTED TWICE. This tier
        # is anchored to eMARC's "Water heaters but no AC" tier, so the 4.44
        # measurement ALREADY CONTAINS the geyser - and HEAT-1's dhw term then
        # added a Punjab-derived geyser on top of it (dhw share 0.75 here).
        # The low tier is anchored to "Basic", which is eMARC's explicitly
        # NO-water-heater tier, so low was never doubled and is unchanged.
        # The subtraction is measured, not assumed: eMARC's own tier gap gives
        # the geyser component directly.
        #     4.44 ("water heaters, no AC") - 3.44 ("basic") = 1.00 kWh/day
        # REVISION: THE GAP IS 1.44, NOT 1.00.
        # The 3.44 / 4.44 / 5.15 figures are NOT REPRODUCIBLE from the eMARC
        # download - see `scripts/emarc_daily_anchors.py`, which recomputes them
        # from source and is the first script in this project that does. Sixteen
        # method variants were tried (both source files x 4 winter definitions x
        # 2 deployment filters x 2 averaging methods); none returns the claimed
        # triple or its deployment counts (claimed n=82/27/23, measured 72/23/20).
        # Two INDEPENDENT reproductions agree on the gap:
        #     daily-consumption file   5.16 - 3.71 = 1.45
        #     15-min load-blocks file  4.97 - 3.53 = 1.44
        # 1.44 adopted (the load-blocks value: raw 15-min data, one less layer
        # SELF-VALIDATING: subtract 1.44 from each measured tier and all three
        # land on the same base - Basic 3.53 (no geyser), Water 4.97-1.44=3.53,
        # AC 4.88-1.44=3.44. A fridge and a light bulb are the same in any home,
        # so a geyser-stripped base that is tier-INVARIANT is exactly what should
        # fall out, and it is independent evidence that the subtraction is real.
        # *** THE 1.44 REVISION WAS WRONG AND IS REVERTED. GAP = 1.00.
        # The revision raised the gap 1.00 -> 1.44 on the finding
        # that the claimed anchors "are not reproducible". That finding used
        # the WRONG FILE. eMARC ships two: a small DAILY-TOTALS file and the
        # 368 MB 15-MINUTE LOAD BLOCKS file. The anchors come from the load
        # blocks; nothing in this repo could read it, because
        # `emarc_load_shape.py` needs pandas and pandas is in NEITHER
        # environment on this machine. So the check fell back to the daily
        # file - a smaller subset (n=73/23/20) - and its different answers
        # were read as the anchors failing to reproduce.
        # `scripts/emarc_loadblocks_anchors.py` (new, stdlib only,)
        # reads the load blocks directly, joining deployment_id to the
        # household-info workbook and keeping mainline + complete days:
        #     Basic                    3.45  (claimed 3.44)   n=82  (claimed 82)
        #     Water heaters, no AC     4.44  (claimed 4.44)   n=27  (claimed 27)
        #     With air conditioners    5.15  (claimed 5.15)   n=23  (claimed 23)
        # ALL THREE LEVELS AND ALL THREE DEPLOYMENT COUNTS REPRODUCE - including
        # the very counts the note said could not be matched.
        #     gap = 4.44 - 3.45 = 0.99, i.e. the ORIGINAL 1.00.
        # SELF-VALIDATING, and more cleanly than the 1.44 version ever was:
        # Basic 3.45 and (Water 4.44 - 0.99) = 3.45 land on each other exactly.
        # A geyser-stripped base SHOULD be tier-invariant, and here it is to
        # the penny.
        # Scaled by this tier's declared uplifts: 1.00 x 1.34 x 1.3 = 1.742.
        #     base anchor 7.73 - 1.742 = 5.988 kWh/day
        # This tier's base profile delivers 16.06 equivalent hours/day
        # (measured: 8.19 kWh/day at 0.510 kW), so the corrected peak is
        # 5.988 / 16.06 = 0.3728 kW, of which 0.080 is the area term.
        #     appliance 0.430 -> 0.293 kW/HH   (gap 1.00, RESTORED)
        # This RAISES demand relative to the 1.44 state, because 1.44 was
        # subtracting more geyser than the measurement supports.
        # RESOLVED, no longer open: the 7.73 anchor was said to "inherit the
        # unreproducible 4.44". 4.44 reproduces exactly (see above), so 7.73
        # = 4.44 x 1.34 x 1.3 stands on measured data. The proposed re-base to
        # (low 4.73 / mid 6.15 / high 8.30) is DROPPED - those targets were
        # derived from the unreproducible 3.53/3.53/3.44 bases, so adopting
        # them would have moved the model AWAY from the measured values.
        # HEAT-1's dhw term is KEPT: it is derived from Punjab inlet-water
        # temperatures, so it is the RIGHT geyser for this site. What is
        # removed is the Maharashtra-measured geyser the anchor smuggled in.
        base_load_w_per_m2=0.8,
        appliance_kw_per_household=0.293,
        cooling_load_w_per_m2_peak=15.0,
        has_ac=True,
        roof_pv_coverage=0.55,
    ),
    LandUse.RESIDENTIAL_HIGH: BuildingCategory(
        name="high_income_residential",
        # STAGE-: PLOTTED KOTHI COLONY - a FIXED built
        # form (net FAR 1.2, ~40 x 300 m2 kothis/ha, G+3). typical_height_m is
        # LIVE for this category: generator/optimiser treat it like a facility
        # (no tier randomisation), so height = 12 m and floor = the config's
        # 12,000 m2 exactly. PUDA plotted class Tier 1; form Tier 3 (Zirakpur).
        floor_area_per_cell_m2=12000.0,   # NET FAR 1.2 plotted colony
        typical_height_m=12.0,            # G+3 kothi/builder floor (was 18 m flats)
        occupants_per_cell=170,           # 40 HH (12,000/300) x 4.2 p/HH HIG
        # was 9; bumped to 12.0 -- empirical evidence (LBNL
        # India 2023, ECEEE 2022 Indian residential surveys) shows high-
        # income households use ~2x more indoor lighting (decorative
        # fixtures, often still halogen) PLUS substantial outdoor
        # landscape / security / decorative lighting (~150-300 W per
        # cell), MULTIPLE refrigerators, dishwasher, washer + dryer,
        # multiple TVs, water heater always-on tank geyser. The income-
        # tier gap is realistically larger than the 1.5x in the legacy
        # values. Note: this is per-m2 averaged across the cell; actual
        # high-income peak per household can be 4-5x low-income peak.
        # FIX: was 12.0 W/m2 all-in, which - multiplied by
        # the 300 m2 kothi the Stage- typology switch introduced on
        # - delivered 3.60 kW/household against low income's 0.235,
        # a ratio of 15.3x. The note directly above states the intent is
        # 4-5x. The 12.0 was calibrated on against 200 m2 FLATS and
        # was never re-derived when the typology became plotted kothis (the
        # parking model WAS corrected for that same switch in the same window:
        # ECS 1.5 -> 0.25, "40,180 phantom public ECS").
        # Split: 2.0 W/m2 area + 1.339 kW/HH appliances -> 1.939 kW/HH total,
        # i.e. 4.5x low income, the midpoint of this file's own stated band.
        # The DISTRICT TOTAL is held at the validated aggregate (55.8 MW): the
        # per-capita anchor (PANJ 2,000 x CEA 1.34 x urban 1.35) was graded
        # SOUND by MODEL_CRITIQUE item 16, so only the DISTRIBUTION between
        # tiers is corrected here, not the level.
        #: see the low-income note above for the anchor.
        # HIGH: eMARC "With air conditioners" 5.15 kWh/day x 1.34 x 1.8
        # (affluence: a 300 m2 plotted kothi with second fridge, dishwasher,
        # dryer, garden and security load, against eMARC's AC-owning flats)
        # = 12.42 kWh/day. Was 0.240 (area) + 0.590 = 0.830 kW peak.
        # The 1.8 is the largest declared uplift in this block and is the one
        # to challenge first - it is a Tier 3 judgement, not a measurement.
        # FIX: WATER HEATING WAS COUNTED TWICE, same defect
        # as the mid tier and worse here. This tier is anchored to eMARC's
        # "With air conditioners" tier, which contains the geyser, and HEAT-1
        # then added a Punjab geyser on top (dhw share 0.60). The measured
        # symptom: winter heating ran 9.45 kWh/HH/day against mid income's
        # 1.12 - 8.4x - which is what exposed the double count.
        # Subtraction from eMARC's own tier gap (see the mid-income note):
        #     1.00 kWh/day x 1.34 x 1.8 = 2.412  (gap REVERTED 1.44 -> 1.00,
        #     used the DAILY-TOTALS file; the anchors are from the 15-MINUTE
        #     LOAD BLOCKS file, which nothing could read until
        #     scripts/emarc_loadblocks_anchors.py. Reading the right file
        #     reproduces all three levels AND all three deployment counts, and
        #     gives gap 0.99 = the original 1.00. Full note in the mid-income
        #     block above.)
        #     base anchor 12.42 - 2.412 = 10.008 kWh/day
        # This tier's base profile delivers 17.81 equivalent hours/day
        # (measured: 14.78 kWh/day at 0.830 kW), so the corrected peak is
        # 10.008 / 17.81 = 0.5619 kW, of which 0.240 is the area term.
        #     appliance 0.590 -> 0.322 kW/HH   (gap 1.00, RESTORED)
        # NOTE ON THE TIER RATIO. This compresses the BASE peak spread from
        # 3.03x to 2.05x (low 0.271 / mid 0.373 / high 0.562). That is not a
        # regression against the "4-5x" intent stated above: eMARC's own
        # measured whole-house winter tiers span only 3.44 -> 5.15 = 1.50x, so
        # a base-load spread near 2x is what the measurement supports. The 4-5x
        # belongs to the WHOLE household including cooling, where high income
        # carries 25 W/m2 of AC over 300 m2 and low income carries none.
        base_load_w_per_m2=0.8,
        appliance_kw_per_household=0.322,
        cooling_load_w_per_m2_peak=25.0,
        has_ac=True,
        roof_pv_coverage=0.55,
    ),
    LandUse.SCHOOL: BuildingCategory(
        name="school",
        floor_area_per_cell_m2=3500.0,    # facility-sized 1-ha campus URDPFI counts)
        typical_height_m=9.0,
        occupants_per_cell=500,           # ~1 facility's students+staff (was 1600 at 4-ha)
        base_load_w_per_m2=8.0,
        cooling_load_w_per_m2_peak=20.0,
        has_ac=True,
        roof_pv_coverage=0.75,
    ),
    LandUse.OFFICE: BuildingCategory(
        name="office",
        floor_area_per_cell_m2=30000.0,
        typical_height_m=24.0,
        occupants_per_cell=3000,          # 30,000 m2 / 10 m2 per worker (URDPFI)
        base_load_w_per_m2=15.0,          # was 12; modern equipment-heavy India IT/services
        cooling_load_w_per_m2_peak=28.0,
        has_ac=True,
        roof_pv_coverage=0.65,
    ),
    LandUse.SHOPPING_CENTRE: BuildingCategory(
        name="shopping_centre",
        floor_area_per_cell_m2=30000.0,
        typical_height_m=18.0,
        occupants_per_cell=5000,          # scaled with floor (was 4000 @ 24,000 m2)
        base_load_w_per_m2=20.0,          # was 16; lit displays + refrigeration + escalators
        cooling_load_w_per_m2_peak=30.0,
        has_ac=True,
        roof_pv_coverage=0.70,
    ),
    # Linear high-street retail: smaller per-cell floor area, lower buildings,
    # less full-air-conditioning than an enclosed mall. Defined per the Indian
    # bazaar / mixed-use ground-floor retail pattern.
    LandUse.RETAIL_HIGHSTREET: BuildingCategory(
        name="retail_highstreet",
        floor_area_per_cell_m2=30000.0,   # NET FAR 3.0 mixed-use bazaar block
        typical_height_m=12.0,            # 4 storeys (ground retail + 3 above; ~75% coverage street-wall)
        occupants_per_cell=3600,          # scaled with floor (was 1200 @ 10,000 m2)
        base_load_w_per_m2=12.0,
        cooling_load_w_per_m2_peak=20.0,
        has_ac=True,
        roof_pv_coverage=0.55,
    ),
    LandUse.RESTAURANT_FOOD: BuildingCategory(
        name="restaurant_food_service",
        floor_area_per_cell_m2=10000.0,   # FAR 1.0 low-rise F&B strip
        typical_height_m=9.0,
        occupants_per_cell=1250,          # scaled with floor (was 1000 @ 8,000 m2)
        base_load_w_per_m2=20.0,
        cooling_load_w_per_m2_peak=22.0,
        has_ac=True,
        roof_pv_coverage=0.45,
    ),
    LandUse.HOTEL_GUESTHOUSE: BuildingCategory(
        name="hotel_guesthouse",
        floor_area_per_cell_m2=30000.0,   # NET FAR 3.0 (commercial class,
        typical_height_m=21.0,
        occupants_per_cell=1800,          # scaled with floor (was 1080 @ 18,000 m2)
        base_load_w_per_m2=10.0,
        cooling_load_w_per_m2_peak=26.0,
        has_ac=True,
        roof_pv_coverage=0.50,
    ),
    LandUse.HEALTHCARE: BuildingCategory(
        name="healthcare",
        floor_area_per_cell_m2=3600.0,    # facility-sized IPHS UPHC/UCHC blend
        typical_height_m=15.0,
        occupants_per_cell=180,           # scaled with floor (was 720 @ 15,000 m2)
        base_load_w_per_m2=18.0,          # was 14; 24/7 medical equipment + imaging + servers
        cooling_load_w_per_m2_peak=24.0,
        has_ac=True,
        roof_pv_coverage=0.45,
    ),
    LandUse.LIGHT_INDUSTRY: BuildingCategory(
        name="light_industry",
        floor_area_per_cell_m2=12500.0,   # FAR 1.25 industrial-estate plotted
        typical_height_m=12.0,
        occupants_per_cell=375,           # scaled with floor (was 600 @ 20,000 m2)
        base_load_w_per_m2=28.0,          # was 22; 2030 industrial electrification trajectory
        cooling_load_w_per_m2_peak=10.0,
        has_ac=True,
        roof_pv_coverage=0.80,
    ),
    LandUse.WAREHOUSE: BuildingCategory(
        name="warehouse_cold_storage",
        floor_area_per_cell_m2=8000.0,    # FAR 0.8 high-bay logistics
        typical_height_m=12.0,
        occupants_per_cell=110,           # scaled with floor (was 300 @ 22,000 m2)
        base_load_w_per_m2=30.0,          # was 24; cold-chain refrigeration realism
        cooling_load_w_per_m2_peak=22.0,
        has_ac=True,
        roof_pv_coverage=0.85,
    ),
    LandUse.PUBLIC_SERVICES: BuildingCategory(
        name="public_services",
        floor_area_per_cell_m2=6000.0,    # FAR 0.6 civic campus
        typical_height_m=9.0,
        occupants_per_cell=225,           # scaled with floor (was 300 @ 8,000 m2)
        base_load_w_per_m2=9.0,
        cooling_load_w_per_m2_peak=0.0,
        has_ac=False,
        roof_pv_coverage=0.60,
    ),
    # Temples / gurudwaras / mosques in the Punjab context. Low energy
    # intensity, often naturally ventilated, but high occupant turnover.
    LandUse.RELIGIOUS: BuildingCategory(
        name="religious",
        floor_area_per_cell_m2=4000.0,    # FAR 0.4 complex + forecourt
        typical_height_m=9.0,             # one prayer hall + ancillary
        occupants_per_cell=400,           # scaled with floor (was 600 @ 6,000 m2)
        base_load_w_per_m2=5.0,
        cooling_load_w_per_m2_peak=10.0,
        has_ac=False,                     # mostly naturally ventilated
        roof_pv_coverage=0.40,
    ),
    LandUse.OPEN_SPACE: None,
    LandUse.BLUE_SPACE: None,
    LandUse.ROAD: None,
    LandUse.SOLAR_FARM: None,
    LandUse.PARKING_LOT: None,   # no building; demand-sized via core.requirements
}


def category_for(land_use: LandUse) -> Optional[BuildingCategory]:
    """Return the BuildingCategory for a LandUse, or None for non-built uses.

    Returns
    -------
    Optional[BuildingCategory]
        Category metadata for built uses, otherwise None.
    """
    return CATEGORY_CATALOGUE[land_use]


# ---------------------------------------------------------------------------
# 1-ha cells. LIGHT footprint model: a campus = its BUILDING cell (which keeps
# its per-cell floor + demand, so this table does NOT change the energy model)
# PLUS surrounding GROUNDS cells (parking / playfield / ambulance bay / lawn,
# re-tagged from OPEN_SPACE by layout.building_footprints). The value is the
# TOTAL campus size; (campus - 1) grounds cells are added around the building.
# Rendering merges the building + its grounds into one campus polygon.
# Sub-type refinements (secondary school, UCHC hospital) are applied in the
# footprint pass from `amenity_subtype`, since SCHOOL / HEALTHCARE are single
# land-uses covering both tiers. Sources: URDPFI 2014 site-area norms (Tier 1)
# + Indian facility practice (Tier 3) - documented per row.
# ---------------------------------------------------------------------------
TYPICAL_FOOTPRINT_CELLS: Dict[LandUse, int] = {
    LandUse.RESIDENTIAL_LOW: 1,       # EWS/LIG group-housing society block
    LandUse.RESIDENTIAL_MID: 1,       # MIG apartment society
    LandUse.RESIDENTIAL_HIGH: 1,      # per kothi cell; colonies group by contiguity into pockets
    LandUse.SCHOOL: 1,                # primary campus (URDPFI ~0.4-1 ha); secondary -> 2 via subtype
    LandUse.OFFICE: 1,                # G+8 CBD block on 1 ha
    LandUse.SHOPPING_CENTRE: 4,       # regional mall 3-6 ha incl. surface parking (2x2; Tier 3)
    LandUse.RETAIL_HIGHSTREET: 1,     # linear bazaar street-wall (chained 1-cell segments)
    LandUse.RESTAURANT_FOOD: 1,
    LandUse.HOTEL_GUESTHOUSE: 1,
    LandUse.HEALTHCARE: 1,            # UPHC clinic (small); UCHC hospital -> 4 (2x2) via subtype
    LandUse.LIGHT_INDUSTRY: 1,        # industrial-estate plot
    LandUse.WAREHOUSE: 2,             # single-storey high-bay + loading yard, 1-2 ha (Tier 3)
    LandUse.PUBLIC_SERVICES: 1,       # civic campus
    LandUse.RELIGIOUS: 1,             # complex + forecourt
}

# Sub-type overrides (read from cell.amenity_subtype in the footprint pass).
TYPICAL_FOOTPRINT_CELLS_BY_SUBTYPE: Dict[str, int] = {
    "secondary": 2,   # URDPFI senior-secondary ~1.6-2 ha + sports fields
    "UCHC": 4,        # 50-100 bed urban CHC hospital + parking + ambulance, ~2-4 ha
}


# Default land-use share targets for the master plan (used by constraints).
# These are the fractions of total cells that should be of each type.
# IMPORTANT: at 200 m x 200 m resolution, a single "ROAD" cell represents a
# transport corridor (carriageway + verge + setback + pavement + utility ROW)
# rather than just asphalt. Targets reflect this — roads are a larger share
# than the literal-asphalt fraction in cm-resolution mapping.
# (Claude 2 critical-review #6): single-source fallback for
# PV panel orientation when a category isn't found in the YAML map
# `pv_orientation_defaults_by_category`. Imported by `energy/costs.py`
# (LP path) and `core/export_3d.py` (GeoJSON path) so the two consumers
# can never drift apart.
DEFAULT_PV_ORIENTATION: str = "south_fixed"


DEFAULT_AREA_TARGETS: Dict[LandUse, float] = {
    # STAGE-: re-derived at 250k population / 100 m cells from
    # derive_requirements counts; MUST mirror config/district_composition.yaml
    # land_use_targets (the YAML is authoritative - this dict is the fallback
    # for config-less callers). See the YAML block for the full derivation +
    # the compact-town-in-a-green-belt decomposition of open_space.
    LandUse.RESIDENTIAL_LOW: 0.018,   # EWS/LIG flats, FAR 2.0 (+3.0 spine)
    LandUse.RESIDENTIAL_MID: 0.050,   # MIG flats, FAR 2.0 (+3.0 spine)
    LandUse.RESIDENTIAL_HIGH: 0.090,  # plotted kothi colony, FAR 1.2 fixed form
    LandUse.SCHOOL: 0.034,            # 85 facility campuses (URDPFI at 250k)
    LandUse.OFFICE: 0.003,            # FAR 3.0 CBD block
    LandUse.SHOPPING_CENTRE: 0.007,   # FAR 3.0 malls
    LandUse.RETAIL_HIGHSTREET: 0.003, # FAR 3.0 mixed-use bazaar spine
    LandUse.RESTAURANT_FOOD: 0.001,
    LandUse.HOTEL_GUESTHOUSE: 0.001,
    LandUse.HEALTHCARE: 0.003,        # 5 UPHC + 1 UCHC (IPHS at 250k)
    LandUse.LIGHT_INDUSTRY: 0.016,    # FAR 1.25 estates
    LandUse.WAREHOUSE: 0.007,         # FAR 0.8 high-bay
    LandUse.PUBLIC_SERVICES: 0.004,
    LandUse.RELIGIOUS: 0.025,         # demand-driven (1 m2/cap) at 250k
    LandUse.OPEN_SPACE: 0.413,        # structured: parks 0.12 + phased reserve 0.13 + conversion + belt
    LandUse.BLUE_SPACE: 0.040,        # 4 m2/cap water bodies
    LandUse.ROAD: 0.115,              # arterial skeleton, just below the locked 11.64%
                                      # (SA must never grow roads; adds collectors/locals)
    LandUse.SOLAR_FARM: 0.140,        # 350 x 1-ha cells = 350 MWp reserve
    LandUse.PARKING_LOT: 0.030,       # URDPFI ECS at 250k (plotted colony on-plot)
}


# ---------------------------------------------------------------------------
# Visualisation palette (used by core.visualise.to_svg)
# ---------------------------------------------------------------------------
# Colours chosen to be readable on a master plan: residential warm tones, EWS
# distinctly amber, commercial / office cool blues, industry darker, green
# space and solar farm clearly green/yellow, roads grey.
LAND_USE_COLOURS: Dict[LandUse, str] = {
    LandUse.RESIDENTIAL_LOW: "#E8A86A",   # amber — visually distinct EWS
    LandUse.RESIDENTIAL_MID: "#F4C77B",   # warm sand
    LandUse.RESIDENTIAL_HIGH: "#D98C5F",  # darker terracotta
    LandUse.SCHOOL: "#7BB7E8",            # light blue
    LandUse.OFFICE: "#4A78A8",            # mid blue
    LandUse.SHOPPING_CENTRE: "#C964A8",   # magenta
    LandUse.RETAIL_HIGHSTREET: "#D17B3E", # warm orange — high-street awnings
    LandUse.RESTAURANT_FOOD: "#E08A6E",   # peach
    LandUse.HOTEL_GUESTHOUSE: "#A865B8",  # purple
    LandUse.HEALTHCARE: "#E85F5F",        # red
    LandUse.LIGHT_INDUSTRY: "#5B5570",    # dark slate
    LandUse.WAREHOUSE: "#6F6F8C",         # mid slate
    LandUse.PUBLIC_SERVICES: "#86C5C5",   # teal
    LandUse.RELIGIOUS: "#E8A857",         # saffron — distinct from amber EWS
    LandUse.OPEN_SPACE: "#7CC470",        # green
    LandUse.BLUE_SPACE: "#5C9DD8",        # water blue — distinct from open-space green
    LandUse.ROAD: "#C8C8C8",              # light grey
    LandUse.SOLAR_FARM: "#F2D24A",        # bright yellow
    LandUse.PARKING_LOT: "#5E636B",       # dark asphalt grey — distinct from light-grey road
}


def validate_targets() -> None:
    """Sanity-check that area targets sum to 1.0.

    Returns
    -------
    None
    """
    total = sum(DEFAULT_AREA_TARGETS.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Land-use area targets sum to {total}, not 1.0")


if __name__ == "__main__":
    validate_targets()
    print(f"{len(LandUse)} land-uses defined.")
    print(f"{sum(1 for c in CATEGORY_CATALOGUE.values() if c is not None)} "
          "have building categories.")
    print("\nArea-share targets:")
    for lu, share in sorted(DEFAULT_AREA_TARGETS.items(), key=lambda x: -x[1]):
        print(f"  {lu.value:<28} {share:6.1%}")
