"""Extract the resident-app data snapshot (app/data.js) from the production model.

Re-run after every re-anneal / re-pin so the app tracks the current baseline:
    python scripts/app_data_extract.py

Everything the app shows is MODEL DATA (no mockups):
  - per-cell: households, floor area, deployed rooftop kWp, orientation, shading
  - per-archetype unit demand profiles (the model's own demand_by_slice_kw, so
    occupancy/cooling/heating/seasonality are exact)
  - per-slice rooftop PV yield per kWp (GSA monthly shape, temp derate, soiling)
  - per-slice ToU tariffs straight off the slice table (seasonal jun-sep bands)
  - district context from the production full_stack scenario (by_slice)
  - EV/V2G per-income parameters + smart-charging program config
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from energy import load_optimised_network            # noqa: E402
from energy.costs import load_economics              # noqa: E402

OUT = ROOT / "app" / "data.js"
DISPATCH_JSON = ROOT / "outputs" / "data" / "energy" / "dispatch_results.json"
GEOJSON = ROOT / "outputs" / "geojson3d" / "optimised_sa.geojson"

RES_CATS = ("low_income_residential", "mid_income_residential",
            "high_income_residential")
CAT_TO_TIER = {"low_income_residential": "residential_low",
               "mid_income_residential": "residential_mid",
               "high_income_residential": "residential_high"}
TIER_LABEL = {"residential_low": "EWS / LIG", "residential_mid": "Mid-income",
              "residential_high": "Kothi (HIG)"}


def r(x, nd=4):
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    econ = load_economics(force_reload=True)
    net = load_optimised_network()

    # slice metadata (incl. per-slice tariffs) comes from the dispatch export -
    # its ordering is the canonical one for every array in the payload
    d = json.loads(DISPATCH_JSON.read_text(encoding="utf-8"))
    slice_meta = [{
        "id": s["id"], "m": s["id"].split("_")[0], "dt": s["id"].split("_")[1],
        "dp": s["daypart"], "h": r(s["hours_per_year"], 2),
        "band": s.get("tariff_band", ""),
        "imp": r(s.get("import_tariff_inr_per_kwh", 0.0), 4),
        "exp": r(s.get("export_tariff_inr_per_kwh", 0.0), 4),
    } for s in d["slices"]]
    slice_ids = [s["id"] for s in slice_meta]

    # publish the boundary constants the app was hardcoding, so a
    # the green delivered price 4.01 as literals).
    grid_block = {
        "ef_kgco2_per_kwh": r(float(econ.period_emission_factor(2030)), 4),
        "green_price_inr_kwh": r(float(
            econ.green_purchase_delivered_price_inr_per_kwh()), 4),
    }

    # ---- per-archetype UNIT demand profiles (model-true) --------------------
    # Split into base / cooling / heating unit shapes (per kW of installed
    # peak), extracted by zeroing the other two components on a single node
    # and calling the model's own demand_by_slice_kw. The app then rebuilds
    # any cell exactly: base_kw*bp + cooling_kw*microclimate*cp + heating_kw*hp.
    cats = {}
    for cat_name in RES_CATS:
        nodes = [n for n in net.nodes if n.category_name == cat_name]
        if not nodes:
            continue
        proto = nodes[0]

        def raw_profile(component: str):
            node = copy.copy(proto)
            node.peak_base_kw = 1.0 if component == "base" else 0.0
            node.peak_cooling_kw = 1.0 if component == "cool" else 0.0
            node.peak_heating_kw = 1.0 if component == "heat" else 0.0
            node.microclimate_cooling_multiplier = 1.0
            sub = copy.copy(net)
            sub.nodes = [node]
            # district-wide terms (streetlights) don't belong to a household
            sub.grid_streetlight_kwh_yr = 0.0
            kw = sub.demand_by_slice_kw(econ)
            return [kw[sid] for sid in slice_ids]

        # zero-baseline: whatever demand_by_slice_kw adds regardless of the
        # node's peaks gets subtracted, so the unit profiles are pure.
        zero = raw_profile("none")

        def unit_profile(component: str):
            a = raw_profile(component)
            return [r(max(0.0, x - z), 6) for x, z in zip(a, zero)]

        tier = CAT_TO_TIER[cat_name]
        #: `ep` is now kW of EV charging PER HOUSEHOLD,
        # not a multiplier on peak_base_kw.
        # History. Until the model computed residential EV as
        # `peak_base_kw x ev_demand_multiplier`, so the unit base profile -
        # extracted with peak_base_kw = 1.0 - silently CONTAINED the average
        # EV uplift, and `ep` had to be exported so the app could subtract it
        # (the double-count fix). rebuilt residential EV as
        # households x per-household kW, which is independent of the node's
        # peaks, so it now lands entirely in the zero-baseline and
        # `unit_profile` subtracts it out: `bp` is EV-free by construction and
        # the subtraction the app used to do is no longer needed. The app adds
        # `ep` back on top instead. See app/app.js hhLoadKw.
        ev_prof = [r(float(econ.ev_kw_per_household(cat_name, sid)), 6)
                   for sid in slice_ids]
        cats[tier] = {
            "label": TIER_LABEL[tier],
            "bp": unit_profile("base"),
            "cp": unit_profile("cool"),
            "hp": unit_profile("heat"),
            "ep": ev_prof,
            # units marker for `ep`, read by app/app.js hhEvAvgKw:
            #   absent/1 = legacy multiplier on peak_base_kw, EV embedded in bp
            #   2        = kW per household, bp is EV-free
            "epv": 2,
        }

    # ---- rooftop PV yield per kWp per slice (south) + E-W multiplier -------
    y = net.pv_yield_per_kwp_kwh(econ)
    pv_yield = [r(y.get(sid, 0.0), 4) for sid in slice_ids]
    ew_mult = [r(econ.pv_orientation_yield_multiplier(sid, "east_west"), 4)
               for sid in slice_ids]

    # ---- residential cells --------------------------------------------------
    # geojson lookup for fields the node may not carry
    gj = json.loads(GEOJSON.read_text(encoding="utf-8"))
    props_by_cell = {}
    for f in gj.get("features", []):
        p = f.get("properties", {})
        cid = p.get("cell_id")
        if cid is None or p.get("part_index") not in (None, 0):
            continue
        if cid not in props_by_cell:
            props_by_cell[cid] = p

    # geojson lookup by (row, col) for deployed PV / orientation / floor area
    props_by_rc = {}
    for p in props_by_cell.values():
        if "row" in p and "col" in p:
            props_by_rc[(int(p["row"]), int(p["col"]))] = p

    cells = []
    for n in net.residential_nodes():
        tier = CAT_TO_TIER.get(n.category_name)
        if tier not in cats:
            continue
        row, col = n.cell_id
        p = props_by_rc.get((int(row), int(col)), {})
        hh = int(getattr(n, "households", 0) or p.get("households") or 0)
        if hh <= 0:
            continue
        mc = float(getattr(n, "microclimate_cooling_multiplier", 1.0) or 1.0)
        cells.append({
            "id": f"{int(row)}-{int(col)}",
            "r": int(row), "c": int(col), "cat": tier,
            "hh": hh,
            "b": r(n.peak_base_kw, 3),
            "co": r(float(n.peak_cooling_kw) * mc, 3),
            "he": r(n.peak_heating_kw, 3),
            "floor": r(p.get("floor_area_m2") or 0.0, 1),
            "kwp": r(p.get("pv_deployed_kwp") or 0.0, 2),
            "cap": r(getattr(n, "rooftop_pv_cap_kwp", 0.0) or 0.0, 2),
            "shade": r(getattr(n, "pv_shading_multiplier", 1.0)
                       or p.get("pv_shading_multiplier_geom") or 1.0, 4),
            "ori": p.get("pv_orientation") or "south_fixed",
            "trees": bool(p.get("has_street_trees")),
            # solar water heating collector area on THIS
            # roof, m2. Read from the GeoJSON so the app and the 3D
            # viewer can never disagree about which roof carries one -
            # that file is the single allocation authority. The LP
            # decides only the district total; the split across roofs is
            # pro-rata by roof area (scripts/patch_geojson_solar_thermal.py).
            "st": r(p.get("solar_thermal_m2") or 0.0, 2),
        })
    cells.sort(key=lambda x: (x["cat"], x["r"], x["c"]))

    # ---- town map (every base cell) -----------------------------------------
    lu_codes = {}
    map_cells = []
    for cid, p in props_by_cell.items():
        lu = p.get("land_use") or "?"
        #: the released generation ring carries
        # land_use=open_space with amenity_subtype=solar_expansion_2030 - a
        # deliberate tagging (network.py ~1624: retyping the land would breach
        # the open-space share). The LP builds on those 100 cells from 2030
        # (214,914 kWp base-year farm = all 301 ha), so a map that colours by
        # land_use alone paints a third of the operating farm as parkland.
        # The 2D svg had the same defect; both now retype FOR DISPLAY only.
        if str(p.get("amenity_subtype") or "").startswith("solar_expansion_"):
            lu = "solar_farm"
        if p.get("role") not in (None, "", "cell", "building"):
            # skip street_edge / path features etc.
            if "row" not in p or "col" not in p:
                continue
        if "row" not in p or "col" not in p:
            continue
        code = lu_codes.setdefault(lu, len(lu_codes))
        map_cells.append([int(p["row"]), int(p["col"]), code])

    # ---- district context (production full_stack) ---------------------------
    fs = next(s for s in d["scenarios"]
              if s["name"] == "full_stack" and abs(float(s.get("alpha", 0))) < 1e-9)
    # (RF-2 close-out catch): vs-BAU was HARDCODED -40.6/-56.0 (stale
    # since B21) against the app's zero-hardcoded-numbers contract - now derived
    # from the same regen JSON the rest of the snapshot reads.
    _bau = next(s for s in d["scenarios"] if s["name"] == "bau")
    _vs_cost = (float(fs["annual_cost_inr"]) / float(_bau["annual_cost_inr"]) - 1.0) * 100.0
    _vs_co2 = (float(fs["annual_emissions_kgco2"]) / float(_bau["annual_emissions_kgco2"]) - 1.0) * 100.0
    bs = fs["by_slice"]
    def arr(key):
        return [r(bs[sid].get(key, 0.0), 1) for sid in slice_ids]
    district = {
        "demand": arr("demand_kwh"), "pv": arr("pv_kwh"),
        "imp": arr("grid_import_kwh"), "exp": arr("grid_export_kwh"),
        "batt_d": arr("battery_discharge_kwh"), "v2g": arr("v2g_discharge_kwh"),
        "bio": arr("biomass_kwh"), "wte": arr("wte_kwh"), "biogas": arr("biogas_kwh"),
        "green": arr("green_purchase_kwh"),
        "st": arr("solar_thermal_served_kwh"),
    }
    pb = fs.get("period_breakdown", {}).get("2030", {})

    town = {
        "name": "Zirakpur New Town",
        "period": 2030,
        "population": 250000,
        "households": sum(c["hh"] for c in cells),
        "res_cells": len(cells),
        "renewable_share": r(fs.get("renewable_share", 0.0), 4),
        "annual_demand_gwh": r(float(fs.get("annual_demand_kwh", 0.0)) / 1e6, 1),
        "pv_gwh": r(float(fs.get("pv_generation_kwh", 0.0)) / 1e6, 1),
        "net_cost_inr_kwh": r(fs.get("lcoe_inr_per_kwh", 0.0), 2),
        "co2_kt": r(float(fs.get("annual_emissions_kgco2", 0.0)) / 1e6, 1),
        "vs_bau_cost_pct": r(_vs_cost, 1), "vs_bau_co2_pct": r(_vs_co2, 1),
    }

    # ---- solar water heating --------------------------------
    # Every figure derived from the regen JSON or counted off the GeoJSON, per
    # the app's zero-hardcoded-numbers contract. The Rs/yr and tCO2/yr SAVING
    # is deliberately NOT published here: it is a difference against the
    # pin, which is not in this file, so it cannot be derived and
    # would have to be transcribed. Section 5 of the thesis carries it.
    _caps = fs.get("capacities", {}) or {}
    _st_m2 = float(_caps.get("solar_thermal_m2", 0.0) or 0.0)
    _st_kwh = float(_caps.get("solar_thermal_served_kwh", 0.0) or 0.0)
    if _st_m2 > 0:
        _st_roofs = sum(1 for _f in gj.get("features", [])
                        if (_f.get("properties") or {}).get("role") == "parcel"
                        and float((_f.get("properties") or {})
                                  .get("solar_thermal_m2") or 0.0) > 0)
        _res_m2 = sum(float(c["st"]) for c in cells)
        _res_hh = sum(int(c["hh"]) for c in cells) or 1
        town["solar_thermal"] = {
            "total_m2": r(_st_m2, 1),
            "gwh_served": r(_st_kwh / 1e6, 2),
            "roofs": _st_roofs,
            "residential_m2": r(_res_m2, 1),
            "m2_per_household": r(_res_m2 / _res_hh, 2),
            # per-tier, because the split is STRONGLY unequal - collectors are
            # allocated by roof area and a high-income home has far more roof
            # per household. The app must show a household its own figure
            # rather than the average, and the inequality is a result, not a
            # presentation problem.
            "m2_per_household_by_tier": {
                _t: r(sum(c["st"] for c in cells if c["cat"] == _t)
                      / max(1, sum(c["hh"] for c in cells if c["cat"] == _t)), 2)
                for _t in sorted({c["cat"] for c in cells})
            },
        }

    # R-6: the p2p/ev blocks + generated date below were
    # hardcoded literals (the rule string still said "export 3.5" after the
    # 2030-labelled snapshot). All now derived from econ / the regen JSON,
    # per the app's zero-hardcoded-numbers contract.
    import datetime as _dt
    ev = d.get("ev_v2g_params", {})
    _p2p_price = float(econ.stage_d_p2p_tariff_inr_per_kwh())
    _exp_tariff = float(econ.export_tariff())
    _eq_cfg = econ.equity_report_config()
    _sc_on = bool(econ.ev_smart_charging_enabled())
    _own = getattr(econ, "ev_vehicle_ownership", {}) or {}
    payload = {
        "meta": {
            "generated": _dt.date.today().isoformat(),
            "source": "district_v3 production model (full_stack alpha=0, 2030 period)",
            "note": "One representative household per cell = cell energy / households in cell.",
        },
        "town": town,
        "slices": slice_meta,
        "cats": cats,
        "pv_yield_kwh_per_kwp": pv_yield,
        "pv_ew_mult": ew_mult,
        "cells": cells,
        "map": {"n": 50, "lu_codes": lu_codes, "cells": map_cells},
        "district": district,
        "p2p": {
            "price_inr_kwh": r(_p2p_price, 2),
            # publish the export tariff as a NUMBER. The app was
            # regex-scraping it out of the prose `rule` string for display
            # while its P2P-gain arithmetic used a hardcoded 3.5 - stale since
            # "feed-in 3" and priced the gain off 3.5 in the same view.
            "export_inr_kwh": r(_exp_tariff, 2),
            "rule": (f"a trade clears only when export {_exp_tariff:g} < "
                     f"{_p2p_price:g} < the slice import tariff"),
            "exclude_ews": bool(_eq_cfg.get("p2p_exclude_ews", True)),
        },
        "grid": grid_block,
        "ev": {
            "params": ev,
            "smart_charging": {
                "enabled": _sc_on,
                "shift_res": r(econ.ev_shiftable_fraction("residential"), 2),
                "shift_work": r(econ.ev_shiftable_fraction("workplace"), 2),
                "fee_inr_kwh": r(econ.ev_smart_charging_cost_inr_per_kwh(), 2),
            },
            # YAML keys are ev_car/e2w; the app reads.car/.e2w - map explicitly
            # (shape contract caught in the R-6 verification pass).
            "battery_kwh": {
                "car": r((_own.get("battery_kwh", {}) or {}).get(
                    "ev_car", (_own.get("battery_kwh", {}) or {}).get("car", 30.0)), 1),
                "e2w": r((_own.get("battery_kwh", {}) or {}).get("e2w", 3.0), 1),
            },
            # 2030-truthful pack (TRJ-3 table: 6.0 -> 8.0 -> 9.5); the old
            # literal 9.5 was the 2055 value on a 2030-labelled snapshot.
            "v2g_pack_kwh_day": r(econ.v2g_kwh_per_unit_per_day_at(2030), 2),
            # the app was using this same 2.0 as the household's
            # V2G *earnings* rate. It is the battery WEAR COST the dispatch
            # objective subtracts (dispatch.py:715), so the household panel was
            # paying out the cost as if it were revenue. Published explicitly
            # so the app can price V2G as (tariff avoided - wear).
            "v2g_degradation_inr_kwh": r(
                econ.v2g_cycle_degradation_inr_per_kwh(), 2),
        },
        "period_2030": {k: r(v, 1) for k, v in pb.items()
                        if isinstance(v, (int, float))},
    }

    OUT.write_text("window.APP_DATA = " + json.dumps(payload, separators=(",", ":"))
                   + ";\n", encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT}  ({kb:.0f} KB)")
    print(f"  cells: {len(cells)}  cats: {list(cats)}  map cells: {len(map_cells)}")
    print(f"  households total: {town['households']:,}")
    for tier, v in cats.items():
        print(f"  {tier}: bp max {max(v['bp']):.3f}  cp max {max(v['cp']):.3f}  "
              f"hp max {max(v['hp']):.3f}")


if __name__ == "__main__":
    main()
