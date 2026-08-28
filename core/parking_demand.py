"""PER-BLOCK, DEMAND-DRIVEN, PHASED PARKING (register B18.3, the author-approved
 - "supply fills demand; no over-supply; parking grows like
everything else").

THE MODEL (plain English first):

  * WHO USES PUBLIC LOTS: offices, malls/highstreet, industry, warehouses,
    healthcare, public services, hotels - their workers (including
    OUT-OF-TOWN commuters, who must park at work) and visitors - plus a
    small residential VISITOR allowance. Resident cars do NOT hit public
    lots: Indian building bylaws make flats park on-plot (stilt/podium -
    PUDA Building Rules 2021 group-housing parking obligation) and the
    kothi colony self-parks on its plots (register 0f B2). The
    `on_plot_absorption_audit` PROVES that assumption against the actual
    car fleet each period - if resident cars ever exceeded on-plot
    capacity, the overflow would surface here loudly.

  * NO DOUBLE COUNTING: a commuter's car
    occupies a HOME space at night and a WORK space by day. Public-lot
    demand is therefore max(DAY, NIGHT), not the sum. With residents
    parking on-plot, DAY (work + visitor) dominates - but the max is
    computed, not assumed.

  * THE CAR FLEET (the audit + growth driver): per income tier,
    households x total-car ownership x cars-per-owning-household.
    TOTAL ownership (any fuel) sizes PARKING; the EV SUBSET (the existing
    cited `ev_adoption.ev_car_share_by_period`) drives charging/V2G in the
    energy model - consistent fleets, no double count. By 2055 the two
    tables CONVERGE.
    E-scooters (e2w) are audited for completeness; 2-wheelers park on-plot
    / on-street per URDPFI convention, and the commercial ECS rates already
    fold the 2W mix into Equivalent Car Spaces (1 car = ~4-5 2W).

  * GROWTH: lot
    demand scales with the car fleet per period. The 2030 count becomes
    real PARKING_LOT cells; the 2042/2055 INCREMENTS become expansion-
    reserve parcels tagged `parking_expansion_2042/2055` next to the
    job-heavy sectors (layout/phased_expansion.py), mirroring the
    residential land bank (register B12/B13).

  * SITING: the SA + hard constraints already enforce the author's siting rules
    - `parking_road_frontage` (every lot touches a road; hard,)
    and carport anchors (lots near offices/industry/healthcare, quadrant-
    balanced). `sector_parking_report` exposes the per-sector demand-vs-
    supply balance so a badly-served block is VISIBLE in the layout verify.

SOURCES (figures in config/demand_norms.yaml `parking`, each cited there):
  URDPFI 2015 Vol I ECS rates + 23 m2/ECS (Tier 1); Data For India vehicle
  ownership (~25% of the richest urban quintile own a car; Tier 2) + CEEW
  ownership-growth-to-2050 (Tier 2) for the total-car table (Tier 3
  derivation, affluent-new-town skew, converging to the cited
  ev_car_share_by_period by 2055); commuter share Tier 3 (10-20% band).
"""
from __future__ import annotations

from math import ceil
from typing import Dict, Optional, Tuple

from .config import DistrictConfig, load_config
from .demographics import DemandNorms, Demographics, load_demand_norms, load_demographics

PERIODS = ("2030", "2042", "2055")

# Residential income tiers used by the car tables (land-use classes).
TIERS = ("low", "mid", "high")


def _households_3class(demo: Demographics) -> Dict[str, int]:
    """Aggregate the 4 demographic tiers to the 3 land-use classes the car
    tables use (the established mapping: EWS+LIG -> low, MIG -> mid,
    HIG -> high; see config/district_composition.yaml income_shares)."""
    hh4 = demo.households_by_income()
    return {
        "low": int(hh4.get("ews", 0)) + int(hh4.get("lig", 0)),
        "mid": int(hh4.get("mig", 0)),
        "high": int(hh4.get("hig", 0)),
    }


# ---------------------------------------------------------------------------
# The car fleet (audit + growth driver)
# ---------------------------------------------------------------------------
def car_fleet_by_period(demo: Optional[Demographics] = None,
                        norms: Optional[DemandNorms] = None,
                        econ_raw: Optional[dict] = None
                        ) -> Dict[str, Dict[str, float]]:
    """TOTAL cars (any fuel) per income tier per period.

    cars(tier, p) = households(tier) x ownership_total(tier, p)
                    x cars_per_owning_household(tier)

    Households come from the same demographics the whole model uses; the
    cars-per-owning-household table is the existing cited one in
    economics.yaml `ev_adoption` (Data For India / CEEW). Returns
    {period: {tier: cars,..., "total": n}}.
    """
    demo = demo or load_demographics()
    norms = norms or load_demand_norms()
    hh = _households_3class(demo)             # {"low": n, "mid": n, "high": n}
    parking = norms.parking or {}
    own = parking.get("car_ownership_total_by_income", {})
    if econ_raw is None:
        from energy.costs import load_economics
        econ_raw = load_economics().ev_adoption or {}
    cpoh = (econ_raw.get("cars_per_owning_household")
            or {"low": 1.0, "mid": 1.05, "high": 1.25})

    out: Dict[str, Dict[str, float]] = {}
    for p in PERIODS:
        o = own.get(p) or own.get(int(p)) or {}
        row = {t: hh.get(t, 0) * float(o.get(t, 0.0)) * float(cpoh.get(t, 1.0))
               for t in TIERS}
        row["total"] = sum(row.values())
        out[p] = row
    return out


def fleet_growth_index(demo: Optional[Demographics] = None,
                       norms: Optional[DemandNorms] = None
                       ) -> Dict[str, float]:
    """Car-fleet growth relative to 2030 (the phased-parking scaler)."""
    fleet = car_fleet_by_period(demo, norms)
    base = max(1.0, fleet["2030"]["total"])
    return {p: fleet[p]["total"] / base for p in PERIODS}


def on_plot_absorption_audit(demo: Optional[Demographics] = None,
                             norms: Optional[DemandNorms] = None,
                             ) -> Dict[str, Dict[str, object]]:
    """PROVE that resident cars fit on-plot each period (the assumption that
    keeps them out of public lots). Flats: bylaw on-plot provision
    (`onplot_ecs_per_dwelling`, PUDA group-housing convention) vs cars per
    dwelling. Kothis: self-park on 300 m2 plots by construction (B2).
    Returns per period: cars/DU by tier, capacity/DU, fits (bool)."""
    demo = demo or load_demographics()
    norms = norms or load_demand_norms()
    parking = norms.parking or {}
    onplot = float(parking.get("onplot_ecs_per_dwelling", 1.0))
    own = parking.get("car_ownership_total_by_income", {})
    from energy.costs import load_economics
    cpoh = (load_economics().ev_adoption or {}).get(
        "cars_per_owning_household") or {"low": 1.0, "mid": 1.05, "high": 1.25}

    out: Dict[str, Dict[str, object]] = {}
    for p in PERIODS:
        o = own.get(p) or {}
        cars_per_du = {t: float(o.get(t, 0.0)) * float(cpoh.get(t, 1.0))
                       for t in TIERS}
        worst = max(cars_per_du.values())
        out[p] = {
            "cars_per_dwelling_by_tier": cars_per_du,
            "onplot_ecs_per_dwelling": onplot,
            "fits_on_plot": worst <= onplot,
            "headroom_ecs": onplot - worst,
        }
    return out


# ---------------------------------------------------------------------------
# Public-lot ECS demand (max of day / night) per period
# ---------------------------------------------------------------------------
def public_parking_ecs_by_period(req_floors: Dict[str, float],
                                 norms: Optional[DemandNorms] = None,
                                 demo: Optional[Demographics] = None,
                                 ) -> Dict[str, Dict[str, float]]:
    """District public-lot ECS per period.

    Parameters
    ----------
    req_floors : Dict[str, float]
        Built floor m2 by parking use (the same dict requirements.py
        assembles: office, shopping_centre, light_industry,... plus
        high_income_residential and mid/low visitor floors).

    DAY  = sum over uses of floor/100 x ECS rate, with the WORKER-heavy
           uses uplifted by (1 + external_commuter_share) - out-of-town
           workers park at work.
    NIGHT = residential VISITOR ECS only (residents park on-plot - audited).
    Both scale with the car-fleet growth index per period (more cars ->
    more driving visitors/commuters on the same floors; built form is
    2030-frozen per DEM-4).
    demand(p) = max(DAY(p), NIGHT(p)).
    """
    norms = norms or load_demand_norms()
    parking = norms.parking or {}
    rates = parking.get("ecs_per_100m2_by_use", {})
    commuter = float(parking.get("external_commuter_share", 0.15))
    worker_uses = set(parking.get("worker_ecs_uses",
                                  ["office", "light_industry",
                                   "warehouse_cold_storage",
                                   "public_services"]))
    visitor_uses = {"high_income_residential", "mid_income_residential",
                    "low_income_residential"}
    idx = fleet_growth_index(demo, norms)

    day_2030 = 0.0
    night_2030 = 0.0
    base_ecs_by_use: Dict[str, float] = {}
    for use, floor in req_floors.items():
        ecs = floor / 100.0 * float(rates.get(use, 0.0))
        if use in visitor_uses:
            night_2030 += ecs
        else:
            if use in worker_uses:
                ecs *= (1.0 + commuter)
            day_2030 += ecs
        base_ecs_by_use[use] = ecs

    # B18.5 v3
    # THAT many"): hourly shared-parking accumulation - each use occupies
    # its design ECS by its daypart profile; the requirement candidate is
    # the max-over-the-day of the SUM (ITE/ULI Shared Parking temporal
    # factors, Indian rhythms; norms `occupancy_profiles`). Falls back to
    # max(day, night) when profiles are absent.
    profiles = parking.get("occupancy_profiles") or {}
    profile_peak_2030 = None
    if profiles:
        n_dp = 12
        sums = [0.0] * n_dp
        for use, ecs in base_ecs_by_use.items():
            prof = profiles.get(use)
            if not prof or len(prof) != n_dp:
                prof = [1.0] * n_dp          # loud default: always-full
            for i in range(n_dp):
                sums[i] += ecs * float(prof[i])
        profile_peak_2030 = max(sums)

    # B18 v2: the stacked URDPFI rates are per-
    # building WORST-CASE standards - summed across the district they can
    # exceed the physical car fleet. Cap by the FLEET-CONSTRAINED peak: a
    # car cannot occupy two lots at once, and the whole town only owns
    # fleet(p) cars. peak = residents' cars away at midday + in-commuters'
    # cars + an outside-visitor allowance (norms keys, cited).
    fleet = car_fleet_by_period(demo, norms)
    away = float(parking.get("peak_away_share", 0.40))
    vis = float(parking.get("visitor_peak_share", 0.12))
    out: Dict[str, Dict[str, float]] = {}
    for p in PERIODS:
        day = day_2030 * idx[p]
        night = night_2030 * idx[p]
        # v3: the URDPFI-side candidate is the hourly accumulation peak
        # (max-over-day of the sum) when profiles exist, else max(day, night)
        if profile_peak_2030 is not None:
            urdpfi_peak = profile_peak_2030 * idx[p]
        else:
            urdpfi_peak = max(day, night)
        # residents' cars parked away from home at the midday peak
        resident_away = fleet[p]["total"] * away
        # in-commuters: outsiders hold `commuter` of the town's jobs, so
        # they add commuter/(1-commuter) of the resident driving workforce
        # (drive shares assumed comparable; Tier-3, demand_norms B18 v2)
        commuter_cars = resident_away * commuter / max(0.05, 1.0 - commuter)
        fleet_peak = (resident_away + commuter_cars) * (1.0 + vis)
        ecs = min(urdpfi_peak, fleet_peak)
        out[p] = {"day_ecs": day, "night_ecs": night,
                  "profile_peak_ecs": (profile_peak_2030 * idx[p]
                                       if profile_peak_2030 is not None
                                       else None),
                  "fleet_peak_ecs": fleet_peak, "ecs": ecs,
                  "fleet_index": idx[p],
                  "binding": "fleet" if fleet_peak < urdpfi_peak
                  else "shared_profile"}
    return out


def parking_cells_by_period(req_floors: Dict[str, float],
                            cfg: Optional[DistrictConfig] = None,
                            norms: Optional[DemandNorms] = None,
                            demo: Optional[Demographics] = None,
                            ) -> Dict[str, int]:
    """PARKING_LOT cell counts per period (the phased land take).

    cells(p) = ceil(ECS(p) x m2_per_ecs / (cell_area x lot_net_to_gross)).
    2030 becomes real cells in the layout; the 2042/2055 INCREMENTS become
    `parking_expansion_*` reserve tags (layout/phased_expansion.py).
    """
    cfg = cfg or load_config()
    norms = norms or load_demand_norms()
    parking = norms.parking or {}
    ecs = public_parking_ecs_by_period(req_floors, norms, demo)
    cell_area = float(cfg.site.get("cell_size_m", 100.0)) ** 2
    # B18 v2: EFFECTIVE capacity ~300 ECS per 1-ha cell -
    # real Indian surface lots run ~28-33 m2/car with landscaping/EVSE/
    # canopy columns (CSE/MoHUA), expressed as 0.70 net x URDPFI 23 m2.
    net = float(parking.get("lot_net_to_gross_effective",
                            parking.get("lot_net_to_gross", 0.85)))
    denom = cell_area * net
    m2_per_ecs = float(parking.get("m2_per_ecs", 23))
    return {p: int(ceil(ecs[p]["ecs"] * m2_per_ecs / denom)) for p in PERIODS}


# ---------------------------------------------------------------------------
# Per-sector demand report
# ---------------------------------------------------------------------------
def sector_parking_report(grid, cfg: Optional[DistrictConfig] = None,
                          norms: Optional[DemandNorms] = None) -> Dict:
    """Per-SECTOR day-ECS demand vs supplied lot capacity on a built layout.

    Reporting/verify only (the SA's catchment + frontage machinery does the
    siting; this makes block-level balance VISIBLE). Demand proxies each
    built cell's floor x its use's ECS rate into its sector; supply is the
    sector's PARKING_LOT capacity. Returns per-sector rows + a coverage
    summary (share of demand in sectors with supply within 1 sector reach).
    """
    cfg = cfg or load_config()
    norms = norms or load_demand_norms()
    from core.building import building_from_cell
    from core.land_use import LandUse
    from layout.road_network import configured_sector_size
    from layout.sector_structure import sector_id_of

    parking = norms.parking or {}
    rates = parking.get("ecs_per_100m2_by_use", {})
    m2_per_ecs = float(parking.get("m2_per_ecs", 23))
    net = float(parking.get("lot_net_to_gross_effective",
                            parking.get("lot_net_to_gross", 0.85)))
    size = configured_sector_size(cfg)
    use_of = {
        LandUse.OFFICE: "office", LandUse.SHOPPING_CENTRE: "shopping_centre",
        LandUse.RETAIL_HIGHSTREET: "shopping_centre",
        LandUse.LIGHT_INDUSTRY: "light_industry",
        LandUse.WAREHOUSE: "warehouse_cold_storage",
        LandUse.HEALTHCARE: "healthcare",
        LandUse.PUBLIC_SERVICES: "public_services",
        LandUse.HOTEL_GUESTHOUSE: "hotel_guesthouse",
    }
    demand: Dict[Tuple[int, int], float] = {}
    supply: Dict[Tuple[int, int], float] = {}
    cell_area = grid.cell_size_m ** 2
    for c in grid.all_cells():
        sid = sector_id_of(grid, c.row, c.col, size)
        if c.land_use in use_of:
            #: this
            # reporter had NEVER RUN - it called `.floor_area_m2`, which the
            # Building dataclass does not have (the field is
            # `total_floor_area_m2`), and `building_from_cell` returns None
            # for a non-built cell. Nothing outside this module calls it, so
            # the AttributeError sat here undetected. Reporting-only: no pin,
            # no LP, no layout effect.
            b = building_from_cell(c, cfg)
            floor = float(getattr(b, "total_floor_area_m2", 0.0) or 0.0) if b else 0.0
            demand[sid] = demand.get(sid, 0.0) + (
                floor / 100.0 * float(rates.get(use_of[c.land_use], 0.0)))
        elif c.land_use == LandUse.PARKING_LOT:
            supply[sid] = supply.get(sid, 0.0) + cell_area * net / m2_per_ecs

    sectors = sorted(set(demand) | set(supply))
    rows = [{"sector": s, "demand_ecs": round(demand.get(s, 0.0), 0),
             "supply_ecs": round(supply.get(s, 0.0), 0)} for s in sectors]
    # served if own or 8-neighbour sector has supply (one sector ~ 800 m)
    def _near_supply(s) -> bool:
        return any(supply.get((s[0] + dr, s[1] + dc), 0.0) > 0
                   for dr in (-1, 0, 1) for dc in (-1, 0, 1))
    served = sum(demand[s] for s in demand if _near_supply(s))
    total = max(1.0, sum(demand.values()))
    return {"rows": rows, "demand_served_within_1_sector": served / total,
            "total_demand_ecs": round(total, 0),
            "total_supply_ecs": round(sum(supply.values()), 0)}


if __name__ == "__main__":
    fleet = car_fleet_by_period()
    audit = on_plot_absorption_audit()
    print("CAR FLEET (total, any fuel):")
    for p, row in fleet.items():
        print(f"  {p}: " + ", ".join(
            f"{t} {row[t]:,.0f}" for t in TIERS) + f"  total {row['total']:,.0f}")
    print("\nON-PLOT AUDIT (residents park on-plot?):")
    for p, a in audit.items():
        print(f"  {p}: worst cars/DU "
              f"{max(a['cars_per_dwelling_by_tier'].values()):.2f} vs "
              f"on-plot {a['onplot_ecs_per_dwelling']:.2f} ECS/DU -> "
              f"{'FITS' if a['fits_on_plot'] else 'OVERFLOW'}")
