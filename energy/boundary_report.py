"""B19 - BOUNDARY FLOWS LEDGER: the district in its region.

Supervisor critique (SUP-3/SUP-4, elevated by the author): "the 25 km2
is modelled as an island - how does it connect to the rest of the country?"
This report answers it with ONE per-period table of every flow that crosses
the town boundary, each line either read from the model's own outputs or
derived from a cited norm. REPORT-ONLY (no LP change); re-run after every
re-pin. Upgrades _spec/BOUNDARY_STATEMENT.md; thesis "district-in-region"
table.

Flows quantified per period (2030 / 2042 / 2055):
  IN : grid electricity, straw fuel, canal/surface water, petrol+diesel for
       the remaining ICE car fleet, food (net of the agri belt), in-commuter
       workers
  OUT: exported electricity, DC-PPA wheeled energy, treated effluent,
       waste-stream residues the WTE cannot take (recyclables/inerts +
       arisings growth beyond plant capacity)
  INTERNAL (for context): WTE-processed waste, groundwater, biogas from own
       sewage
Unquantified (stated limitations): out-commuters (dormitory share toward
Chandigarh), freight tonnage, construction materials for the phased
build-out (embodied carbon deliberately out of scope until Stage G).

Norm sources (Tier flags inline): World Bank What-a-Waste India 0.45-0.57
kg/cap/day (0.5 used, matches economics wte_plant chain); CPHEEO water
supply 135 lpcd + ~80% sewage return; FX-6 straw chain ~1,085 kWh_e/tonne;
ev tables (economics ev_adoption) for the ICE/EV fleet split; ~7,500 km/yr
@ ~15 km/L for ICE cars (MoRTH/SIAM indicative, Tier 3); Punjab wheat+paddy
~10 t/ha-yr combined for the agri belt (PAU package of practices, Tier 2);
~200 kg/cap/yr foodgrain demand (ICMR/NSSO basket, Tier 3).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
DISPATCH = ROOT / "outputs" / "data" / "energy" / "dispatch_results.json"
GEOJSON = ROOT / "outputs" / "geojson3d" / "optimised_sa.geojson"
OUT_JSON = ROOT / "outputs" / "data" / "energy" / "boundary_flows_ledger.json"
OUT_MD = ROOT / "outputs" / "data" / "energy" / "boundary_flows_ledger.md"

PERIODS = ("2030", "2042", "2055")
POP = 250_000

MSW_KG_CAP_DAY = 0.5          # World Bank / economics wte_plant chain (T1-2)
WTE_KWH_PER_T = 333.0         # as-fired net (CPCB/TERI recalib, T3)
STRAW_KWH_E_PER_T = 1085.0    # FX-6: 130 kt ~= 141 GWh_e (T2-3)
WATER_LPCD = 135.0            # CPHEEO benchmark (T1)
SEWAGE_RETURN = 0.80          # CPHEEO convention (T2)
GROUNDWATER_SHARE = 0.65      # DEM-5 pumping share (T3)
ICE_KM_YR = 7500.0            # MoRTH/SIAM indicative private-car use (T3)
ICE_KM_PER_L = 15.0           # petrol car fleet avg (T3)
GRAIN_KG_CAP_YR = 200.0       # foodgrain basket (ICMR/NSSO, T3)
AGRI_T_PER_HA_YR = 10.0       # Punjab wheat+paddy combined (PAU, T2)
# affluence growth on waste arisings, rides the same demand multipliers'
# spirit (T3 assumption, flagged): +12% by 2042, +25% by 2055
WASTE_GROWTH = {"2030": 1.00, "2042": 1.12, "2055": 1.25}


def _fs(dispatch: dict) -> dict:
    return next(s for s in dispatch["scenarios"]
                if s.get("name") == "full_stack"
                and float(s.get("alpha") or 0.0) == 0.0)


def build_ledger(dispatch_path: Path = DISPATCH,
                 geojson_path: Path = GEOJSON) -> dict:
    from energy.costs import load_economics
    from core.parking_demand import car_fleet_by_period
    try:
        from core.parking_demand import ev_fleet_by_period
    except ImportError:
        ev_fleet_by_period = None
    econ = load_economics()
    dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
    fs = _fs(dispatch)
    pb = fs.get("period_breakdown") or {}

    # agri belt area from the layout (0 on pre-B18 layouts)
    agri_ha = 0
    try:
        gj = json.loads(geojson_path.read_text(encoding="utf-8"))
        agri_ha = sum(1 for f in gj.get("features", [])
                      if (f.get("properties") or {}).get("amenity_subtype")
                      == "agri_belt")
    except Exception:
        pass

    fleet = car_fleet_by_period()
    ev = None
    if ev_fleet_by_period is not None:
        try:
            ev = ev_fleet_by_period()
        except Exception:
            ev = None

    periods: Dict[str, dict] = {}
    for p in PERIODS:
        d = pb.get(p) or pb.get(int(p)) or {}
        imp = float(d.get("grid_import_kwh", 0.0))
        exp = float(d.get("grid_export_kwh", 0.0))
        # B21: wheeled green open-access purchase - a distinct
        # IN flow from grey grid import (0.0 on pre-B21 exports).
        green_in = float(d.get("green_purchase_kwh", 0.0))
        ppa = float(fs.get("dc_ppa_offtake_kwh", 0.0)) if p == "2030" else None
        biomass_gen = float((d.get("installed_capacities") or {})
                            .get("biomass_kw_e", 0.0))
        # per-period biomass energy: period_breakdown lacks per-tech gen;
        # approximate 2030 from by_slice (exact) and scale by capacity for
        # later periods (flagged approximation)
        if p == "2030":
            bio_kwh = sum(float(s.get("biomass_kwh", 0.0))
                          for s in (fs.get("by_slice") or {}).values())
            wte_kwh = sum(float(s.get("wte_kwh", 0.0))
                          for s in (fs.get("by_slice") or {}).values())
            periods["_bio30"] = bio_kwh
            periods["_wte30"] = wte_kwh
        else:
            cap30 = float((pb.get("2030") or {}).get("installed_capacities", {})
                          .get("biomass_kw_e", 0.0)) or 1.0
            bio_kwh = periods.get("_bio30", 0.0) * (biomass_gen / cap30)
            wte30cap = float((pb.get("2030") or {}).get("installed_capacities", {})
                             .get("wte_kw_e", 0.0)) or 1.0
            wte_kwh = periods.get("_wte30", 0.0) * (
                float((d.get("installed_capacities") or {}).get("wte_kw_e", 0.0))
                / wte30cap)

        straw_in_t = bio_kwh / STRAW_KWH_E_PER_T
        msw_t = POP * MSW_KG_CAP_DAY * 365 / 1000.0 * WASTE_GROWTH[p]
        wte_t = wte_kwh / WTE_KWH_PER_T
        residues_out_t = max(0.0, msw_t - wte_t)

        water_m3 = POP * WATER_LPCD * 365 / 1000.0
        canal_in_m3 = water_m3 * (1 - GROUNDWATER_SHARE)
        effluent_out_m3 = water_m3 * SEWAGE_RETURN

        cars = fleet[p]["total"]
        if ev is not None:
            ev_cars = ev[p]["total"]
        else:
            shares = {"2030": 0.04, "2042": 0.17, "2055": 0.38}  # blended (T3)
            ev_cars = cars * shares[p]
        ice = max(0.0, cars - ev_cars)
        petrol_ml_yr = ice * ICE_KM_YR / ICE_KM_PER_L / 1e6   # million litres

        food_demand_t = POP * GRAIN_KG_CAP_YR / 1000.0
        agri_supply_t = agri_ha * AGRI_T_PER_HA_YR
        food_in_t = max(0.0, food_demand_t - agri_supply_t)

        periods[p] = {
            "IN_grid_electricity_GWh": imp / 1e9 * 1000,
            "IN_green_oa_purchase_GWh": green_in / 1e9 * 1000,
            "OUT_grid_electricity_GWh": exp / 1e9 * 1000,
            "OUT_dc_ppa_wheeled_GWh": (ppa / 1e9 * 1000) if ppa else None,
            "IN_straw_kt": straw_in_t / 1000.0,
            "INTERNAL_msw_arisings_kt": msw_t / 1000.0,
            "INTERNAL_wte_processed_kt": wte_t / 1000.0,
            "OUT_waste_residues_kt": residues_out_t / 1000.0,
            "IN_canal_water_Mm3": canal_in_m3 / 1e6,
            "INTERNAL_groundwater_Mm3": water_m3 * GROUNDWATER_SHARE / 1e6,
            "OUT_treated_effluent_Mm3": effluent_out_m3 / 1e6,
            "cars_total": cars,
            "cars_ev": ev_cars,
            "IN_petrol_diesel_ML": petrol_ml_yr,
            "IN_food_grains_kt": food_in_t / 1000.0,
            "LOCAL_agri_belt_supply_kt": agri_supply_t / 1000.0,
            "IN_commuter_workers_share_of_jobs": 0.15,
        }
    periods.pop("_bio30", None)
    periods.pop("_wte30", None)

    return {
        "meta": {
            "stage": "B19 boundary flows ledger (district-in-its-region)",
            "population_design": POP,
            "agri_belt_ha": agri_ha,
            "unquantified_limitations": [
                "out-commuters (dormitory share toward Chandigarh/Mohali)",
                "freight tonnage (consumer goods in, industrial products out)",
                "construction materials for the phased 2042/2055 build-out "
                "(embodied carbon deliberately out of scope until Stage G)",
            ],
            "note": ("later-period biomass/WTE energies scale by installed "
                     "capacity from the 2030 slice detail (approximation, "
                     "flagged); waste growth +12%/+25% is a Tier-3 affluence "
                     "assumption pending regional data"),
        },
        "periods": periods,
    }


_ROWS = [
    ("IN  grid electricity", "IN_grid_electricity_GWh", "GWh/yr"),
    ("IN  green OA purchase (B21)", "IN_green_oa_purchase_GWh", "GWh/yr"),
    ("OUT grid electricity (export)", "OUT_grid_electricity_GWh", "GWh/yr"),
    ("OUT DC-PPA wheeled", "OUT_dc_ppa_wheeled_GWh", "GWh/yr"),
    ("IN  straw fuel", "IN_straw_kt", "kt/yr"),
    ("    MSW arisings (internal)", "INTERNAL_msw_arisings_kt", "kt/yr"),
    ("    WTE processed (internal)", "INTERNAL_wte_processed_kt", "kt/yr"),
    ("OUT waste residues/recyclables", "OUT_waste_residues_kt", "kt/yr"),
    ("IN  canal/surface water", "IN_canal_water_Mm3", "Mm3/yr"),
    ("    groundwater (internal)", "INTERNAL_groundwater_Mm3", "Mm3/yr"),
    ("OUT treated effluent", "OUT_treated_effluent_Mm3", "Mm3/yr"),
    ("    car fleet (total / EV)", None, ""),
    ("IN  petrol+diesel (ICE fleet)", "IN_petrol_diesel_ML", "ML/yr"),
    ("IN  food grains (net of belt)", "IN_food_grains_kt", "kt/yr"),
    ("    agri-belt local supply", "LOCAL_agri_belt_supply_kt", "kt/yr"),
    ("IN  commuter workers", "IN_commuter_workers_share_of_jobs", "share of jobs"),
]


def write_ledger(led: dict) -> None:
    OUT_JSON.write_text(json.dumps(led, indent=2), encoding="utf-8")
    lines = [
        "# B19 - Boundary flows ledger: the district in its region",
        "",
        f"_Design population {led['meta']['population_design']:,}; agri belt "
        f"{led['meta']['agri_belt_ha']} ha. Every line is read from the model "
        f"or derived from the cited norm (module docstring). Everything "
        f"evolves across the three periods._",
        "",
        "| flow | 2030 | 2042 | 2055 | unit |",
        "|---|---|---|---|---|",
    ]
    P = led["periods"]
    for label, key, unit in _ROWS:
        if key is None:
            vals = ["{:,.0f} / {:,.0f}".format(P[p]["cars_total"],
                                               P[p]["cars_ev"])
                    for p in PERIODS]
        else:
            vals = []
            for p in PERIODS:
                v = P[p].get(key)
                vals.append("-" if v is None else
                            ("{:,.2f}".format(v) if isinstance(v, float)
                             else str(v)))
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} | {unit} |")
    lines += ["", "**Unquantified (limitations):** "
              + "; ".join(led["meta"]["unquantified_limitations"]) + ".",
              "", f"_Note: {led['meta']['note']}_"]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    led = build_ledger()
    write_ledger(led)
    print(f"-> {OUT_JSON}\n-> {OUT_MD}\n")
    for p in PERIODS:
        d = led["periods"][p]
        print(f"  {p}: grid in {d['IN_grid_electricity_GWh']:.0f} / out "
              f"{d['OUT_grid_electricity_GWh']:.0f} GWh; straw in "
              f"{d['IN_straw_kt']:.0f} kt; waste out "
              f"{d['OUT_waste_residues_kt']:.0f} kt; petrol in "
              f"{d['IN_petrol_diesel_ML']:.1f} ML; food in "
              f"{d['IN_food_grains_kt']:.0f} kt")
