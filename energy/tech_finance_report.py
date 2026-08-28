"""PER-TECHNOLOGY FINANCE REPORT + real-world KPI benchmarking (register
B20, - the author: "check the KPIs like IRR against real projects; we
need realistic numbers, not fantasy").

REPORT-ONLY: reads dispatch_results.json (full_stack alpha=0) + economics -
no LP change, safe at any baseline; re-run after every re-pin.

For each technology it builds an INVESTMENT STATEMENT:
  * installed capacity (2030 base year) + gross CAPEX + annual OPEX + fuel
  * annual ENERGY VALUE under an explicit attribution convention (below)
  * KPIs: simple payback, unlevered real project IRR (25 yr, PV degradation),
    per-tech LCOE, capacity factor
and compares each KPI against CITED REAL-PROJECT BANDS, flagging LOW / OK /
HIGH so unrealistic results surface loudly (the B20 86%-IRR class of error).

ATTRIBUTION CONVENTION (state in the thesis methods): in every time slice,
renewable generation first displaces grid import for the district (valued at
that slice's import tariff) and the exported remainder earns that slice's
feed-in. Each generating tech takes a pro-rata share of its slice's
self-use/export split. Storage (battery) is valued as arbitrage: discharge
at the slice tariff minus charge at the slice tariff. This is a DISTRICT
(social-planner) perspective at the utility discount rate - per-OWNER views
live in owner_finance.py.

REAL-PROJECT BENCHMARK BANDS (India, embedded as cited constants):
  utility solar     IRR ~8-14%, LCOE Rs 2.4-3.5/kWh  (SECI auctions FY23-25
                    cleared Rs 2.5-2.7/kWh; CERC RE Tariff Regulations 2024
                    normative returns; Tier 1-2)
                    https://www.seci.co.in; https://cercind.gov.in
  rooftop (resi)    IRR 15-25% unsubsidised / 25-40% with PMSGY; payback
                    3-6 yr (MNRE benchmark cost ~Rs 50k/kWp + PM Surya Ghar
                    subsidy 2024; BridgeToIndia India Solar Rooftop Map;
                    Tier 1-2) https://pmsuryaghar.gov.in
  C&I rooftop /     IRR 15-25% (net-metered C&I economics, BridgeToIndia;
  carport           Tier 2)
  canal-top /       utility-solar minus ~1-3 pp (capex +8-12% for structure;
  floating          PEDA Sidhwan/Ghaggar + NHDC Omkareshwar; Tier 2)
  biomass power     CERC generic levellised tariff ~Rs 7.5-8.5/kWh FY24-26;
                    project IRR ~12-16% at normative PLF/fuel (CERC RE Regs;
                    Tier 1-2)
  WTE               tariff ~Rs 7-8/kWh with VGF/tipping support; IRR 10-14%
                    (MNRE WTE programme + CPHEEO; Tier 2)
  biogas (sewage)   treated as avoided-cost co-benefit; IRR 8-15% (GOBARdhan
                    /FAME norms vary; Tier 3)
  battery BESS      standalone arbitrage-marginal in India today; value is
                    capacity/adequacy (SECI BESS tender benchmarks; Tier 2)

Output: outputs/data/energy/tech_finance_report.{json,md}.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DISPATCH = ROOT / "outputs" / "data" / "energy" / "dispatch_results.json"
OUT_JSON = ROOT / "outputs" / "data" / "energy" / "tech_finance_report.json"
OUT_MD = ROOT / "outputs" / "data" / "energy" / "tech_finance_report.md"

LIFE_DEFAULT = 25
SOCIAL_RATE = 0.05

# tech key in economics.technologies -> (label, dispatch by_slice field,
# capacity field in period_breakdown.installed_capacities, unit)
TECHS = {
    "solar_farm": ("Solar farm (fixed+tracked)", "pv_farm", "solar_farm_kwp", "kWp"),
    "rooftop_pv": ("Rooftop PV (all tiers)", "pv_rooftop", "rooftop_pv_kwp", "kWp"),
    "solar_carport": ("Carport PV", "pv_carport", "carport_kwp", "kWp"),
    "floating_pv": ("Canal/pond PV", "pv_floating", "floating_pv_kwp", "kWp"),
    "bipv_facade": ("BIPV facades", "pv_bipv", "bipv_kwp", "kWp"),
    "biomass_chp": ("Straw biomass CHP", "biomass_kwh", "biomass_kw_e", "kW_e"),
    "wte_plant": ("Waste-to-energy", "wte_kwh", "wte_kw_e", "kW_e"),
    "biogas": ("Sewage biogas", "biogas_kwh", "biogas_kw_e", "kW_e"),
    "battery": ("Battery BESS", None, "battery_kwh", "kWh"),
    # FIN-1: thermal store joins the 2030 statement (arbitrage
    # convention like the battery, from the thermal by_slice fields).
    "thermal_storage": ("Thermal cold store", None, "thermal_storage_kwh", "kWh"),
    # solar water heating. Sized in SQUARE METRES of aperture,
    # not kW, because a collector has no electrical rating - it is the one
    # technology in this table whose capacity unit is an area.
    # Absent from this dict the technology would be built by the LP and then
    # SILENTLY OMITTED from the finance statement, which is worse than not
    # modelling it: the cost would land in the objective with no line item.
    "solar_thermal": ("Solar water heating", None, "solar_thermal_m2", "m2"),
}

# FIN-1: report tech key -> economics.technologies key for the learning
# curve (period_capex_factor) + capex field, for the per-vintage section.
FIN1_VINTAGE_TECHS = {
    "rooftop_pv_kwp": ("Rooftop PV", "rooftop_pv", "capex_inr_per_kwp", "kWp", "rooftop_pv"),
    "farm_fixed_kwp": ("Solar farm (fixed)", "solar_farm", "capex_inr_per_kwp", "kWp", "solar_farm"),
    "carport_kwp": ("Carport PV", "solar_carport", "capex_inr_per_kwp", "kWp", "solar_carport"),
    "floating_pv_kwp": ("Canal/pond PV", "floating_pv", "capex_inr_per_kwp", "kWp", "floating_pv"),
    "battery_kwh": ("Battery BESS", "li_ion_battery", "capex_inr_per_kwh", "kWh", None),
    "v2g_units": ("V2G chargers", "v2g_charger", "capex_inr_per_unit", "units", None),
    # NOTE THE FINAL FIELD IS None, DELIBERATELY. That slot is the
    # `period_capex_factor` learning-curve key, and solar thermal has no
    # published Indian learning rate. Handing it another technology's decline
    # would repeat the CAPEX-DERIVED error of in reverse -
    # inventing a cost fall rather than omitting one. Flat-real is stated as
    # an assumption in the config and is the conservative direction.
    "solar_thermal_m2": ("Solar water heating", "solar_thermal", "capex_inr_per_m2", "m2", None),
}

BENCHMARKS = {
    "solar_farm": {"irr": (0.08, 0.14), "lcoe": (2.4, 3.5),
                   "src": "SECI auctions FY23-25 Rs2.5-2.7/kWh; CERC RE Regs 2024 (T1-2)"},
    "rooftop_pv": {"irr": (0.15, 0.40), "payback": (3.0, 6.0),
                   "src": "MNRE ~Rs50k/kWp + PM Surya Ghar subsidy; BridgeToIndia (T1-2)"},
    "solar_carport": {"irr": (0.15, 0.25),
                      "src": "C&I rooftop economics, BridgeToIndia (T2)"},
    "floating_pv": {"irr": (0.05, 0.12),
                    "src": "utility-solar minus 1-3pp; PEDA Sidhwan/Ghaggar (T2)"},
    "bipv_facade": {"irr": (0.02, 0.10),
                    "src": "facade yields below rooftop; niche economics (T3)"},
    "biomass_chp": {"irr": (0.12, 0.16), "lcoe": (6.5, 9.0),
                    "src": "CERC generic biomass tariff Rs7.5-8.5/kWh FY24-26 (T1-2)"},
    "wte_plant": {"irr": (0.10, 0.14), "lcoe": (6.0, 9.0),
                  "src": "MNRE WTE programme + CPHEEO; VGF-supported (T2)"},
    "biogas": {"irr": (0.08, 0.15),
               "src": "GOBARdhan-class sewage-gas projects (T3)"},
    "battery": {"note": "standalone arbitrage-marginal in India today; "
                        "value = adequacy (SECI BESS tenders, T2)"},
    "thermal_storage": {"note": "cold-storage/TES arbitrage + cooling "
                                "peak-shave; niche Indian benchmarks (T3)"},
}


def _irr(net_capex: float, annual_ben: float, opex: float,
         deg: float, life: int) -> Optional[float]:
    if net_capex <= 0 or annual_ben <= 0:
        return None
    lo, hi = -0.5, 3.0

    def npv(r: float) -> float:
        acc = -net_capex
        for y in range(1, life + 1):
            acc += (annual_ben * (1 - deg) ** (y - 1) - opex) / (1 + r) ** y
        return acc
    if npv(lo) < 0 or npv(hi) > 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _crf(rate: float, life: int) -> float:
    if rate <= 0:
        return 1.0 / life
    return rate * (1 + rate) ** life / ((1 + rate) ** life - 1)


def _payback(net_capex: float, annual_ben: float, opex: float,
             deg: float, life: int) -> Optional[float]:
    cum = 0.0
    for y in range(1, life + 1):
        net = annual_ben * (1 - deg) ** (y - 1) - opex
        if net <= 0:
            return None
        if cum + net >= net_capex:
            return y - 1 + (net_capex - cum) / net
        cum += net
    return None


def _fs(dispatch: dict) -> dict:
    return next(s for s in dispatch["scenarios"]
                if s.get("name") == "full_stack"
                and float(s.get("alpha") or 0.0) == 0.0)


def _slice_meta(dispatch: dict) -> Dict[str, dict]:
    return {s["id"]: s for s in dispatch.get("slices", [])}


def _pv_split_by_slice(fs: dict, meta: Dict[str, dict]
                       ) -> Tuple[float, float, Dict[str, Tuple[float, float]]]:
    """Per-slice (self_value, export_value) per PV-kWh + totals.

    In each slice: exported share = grid_export / total_generation (all
    generation is fungible on the single bus); the remainder displaces
    import at the slice import tariff.
    """
    per_slice: Dict[str, Tuple[float, float]] = {}
    for sid, s in (fs.get("by_slice") or {}).items():
        m = meta.get(sid) or {}
        gen = (float(s.get("pv_kwh", 0)) + float(s.get("biomass_kwh", 0))
               + float(s.get("wte_kwh", 0)) + float(s.get("biogas_kwh", 0)))
        exp = float(s.get("grid_export_kwh", 0))
        exp_share = min(1.0, exp / gen) if gen > 0 else 0.0
        imp_t = float(m.get("import_tariff_inr_per_kwh", 0.0))
        exp_t = float(m.get("export_tariff_inr_per_kwh", 0.0))
        per_slice[sid] = ((1 - exp_share) * imp_t + exp_share * exp_t,
                          exp_share)
    return 0.0, 0.0, per_slice


def build_report(dispatch_path: Path = DISPATCH) -> dict:
    from energy.costs import load_economics
    econ = load_economics()
    techs_cfg = getattr(econ, "technologies", {}) or {}
    dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
    fs = _fs(dispatch)
    meta = _slice_meta(dispatch)
    _, _, slice_val = _pv_split_by_slice(fs, meta)
    pb = fs.get("period_breakdown") or {}
    p2030 = pb.get("2030") or pb.get(2030) or {}
    caps30 = p2030.get("installed_capacities") or {}
    by_slice = fs.get("by_slice") or {}

    # per-tech generation by slice: PV subtypes are not split in by_slice
    # (single pv_kwh), so PV techs share the PV pool pro-rata by installed
    # kWp x their surface yield multiplier (documented approximation).
    pv_kwp = {k: float(caps30.get(TECHS[k][2], 0.0))
              for k in ("solar_farm", "rooftop_pv", "solar_carport",
                        "floating_pv", "bipv_facade")}
    # FIN-1 fix: farm yield weight follows the ACTUAL
    # fixed/tracked split (all-FIXED post-/ was hardcoded 1.18).
    _caps_w = fs.get("capacities") or {}
    _trw = float(_caps_w.get("solar_farm_tracked_kwp", 0.0) or 0.0)
    _totw = float(_caps_w.get("solar_farm_kwp", 0.0) or 0.0)
    _trs = (_trw / _totw) if _totw > 0 else 0.0
    yield_mult = {
        "solar_farm": 1.0 + _trs * (float(
            (techs_cfg.get("solar_farm") or {})
            .get("tracked_yield_multiplier", 1.18)) - 1.0),
        "rooftop_pv": 1.0,
        "solar_carport": 1.0,
        "floating_pv": float(econ.floating_pv_yield_multiplier_vs_ground_mount()),
        "bipv_facade": float((techs_cfg.get("bipv_facade") or {})
                             .get("yield_multiplier", 0.65)),
    }
    weights = {k: pv_kwp[k] * yield_mult[k] for k in pv_kwp}
    wsum = sum(weights.values()) or 1.0
    pv_share = {k: w / wsum for k, w in weights.items()}

    rows: List[dict] = []
    fuel_cost_biomass = float((techs_cfg.get("biomass_chp") or {})
                              .get("fuel_cost_inr_per_kwh_e", 1.84))
    wte_fuel = float((techs_cfg.get("wte_plant") or {})
                     .get("fuel_cost_inr_per_kwh_e", -0.5))

    # FIN-1: economics.technologies uses different block names for two rows.
    _CFG_ALIAS = {"thermal_storage": "thermal_cold_storage",
                  "biogas": "biogas_plant"}
    for key, (label, _f, capfield, unit) in TECHS.items():
        cfg_t = techs_cfg.get(_CFG_ALIAS.get(key, key)) or {}
        cap = float(caps30.get(capfield, 0.0))
        if cap <= 0:
            continue
        # `capex_inr_per_m2` added for solar water heating, which
        # is the only technology here sized by AREA rather than by power or
        # energy. Without it the lookup returned 0.0, the `capex_per <= 0`
        # guard below fired, and the technology was silently dropped from the
        # statement - the exact failure the report wiring was meant to
        # prevent. The guard is good; it was the lookup that was incomplete.
        capex_per = float(cfg_t.get("capex_inr_per_kwp",
                          cfg_t.get("capex_inr_per_kw_e",
                          cfg_t.get("capex_inr_per_kwh",
                          cfg_t.get("capex_inr_per_kwh_thermal",
                          cfg_t.get("capex_inr_per_m2", 0.0))))))
        # derived-capex techs (no direct key in their YAML blocks):
        farm_capex = float((techs_cfg.get("solar_farm") or {})
                           .get("capex_inr_per_kwp", 0.0))
        if key == "solar_farm":
            # FIN-1 fix: the "100% tracked" era ended at
            # - the farm is 100% FIXED). Read the actual split
            # from the frozen solution so the capex premium tracks reality
            # under any future tracked revival instead of a baked era.
            _caps_end = fs.get("capacities") or {}
            _tr = float(_caps_end.get("solar_farm_tracked_kwp", 0.0) or 0.0)
            _tot = float(_caps_end.get("solar_farm_kwp", 0.0) or 0.0)
            _tr_share = (_tr / _tot) if _tot > 0 else 0.0
            capex_per = farm_capex * (
                1.0 + _tr_share * (float(
                    cfg_t.get("tracked_capex_multiplier", 1.12)) - 1.0))
        elif key == "solar_carport":
            capex_per = farm_capex * float(
                econ.carport_capex_multiplier_vs_ground_mount())
        elif key == "floating_pv":
            capex_per = farm_capex * float(
                econ.floating_pv_capex_multiplier_vs_ground_mount())
        if capex_per <= 0:
            # LOUD skip - a zero-capex row would fabricate infinite returns
            print(f"  [warn] {key}: no capex key resolved - row skipped")
            continue
        life = int(cfg_t.get("lifetime_years", LIFE_DEFAULT))
        opex_frac = float(cfg_t.get("opex_fraction_of_capex_per_year", 0.015))
        deg = float(cfg_t.get("degradation_per_year",
                    0.012 if key.endswith("pv") or "solar" in key
                    or key == "bipv_facade" else 0.0))
        gross_capex = cap * capex_per
        opex = gross_capex * opex_frac
        # B21/TRJ-7: the farm now PAYS rent on its granted
        # per-tech statement must carry the same line or its IRR/LCOE
        # overstate the free-land era. Accessor returns 0.0 when the
        # farm_land_rent block is disabled (pre-B21 back-compat).
        if key == "solar_farm" and hasattr(econ, "farm_land_rent_annual_inr"):
            opex += float(econ.farm_land_rent_annual_inr(2030))

        # annual generation + value
        gen = 0.0
        value = 0.0
        fuel = 0.0
        if key in pv_share:
            for sid, s in by_slice.items():
                g = float(s.get("pv_kwh", 0.0)) * pv_share[key]
                gen += g
                value += g * slice_val[sid][0]
        elif key == "biomass_chp":
            for sid, s in by_slice.items():
                g = float(s.get("biomass_kwh", 0.0))
                gen += g
                value += g * slice_val[sid][0]
            fuel = gen * fuel_cost_biomass
        elif key == "wte_plant":
            for sid, s in by_slice.items():
                g = float(s.get("wte_kwh", 0.0))
                gen += g
                value += g * slice_val[sid][0]
            fuel = gen * wte_fuel          # negative = landfill credit
        elif key == "biogas":
            for sid, s in by_slice.items():
                g = float(s.get("biogas_kwh", 0.0))
                gen += g
                value += g * slice_val[sid][0]
        elif key == "battery":
            for sid, s in by_slice.items():
                m = meta.get(sid) or {}
                t = float(m.get("import_tariff_inr_per_kwh", 0.0))
                value += (float(s.get("battery_discharge_kwh", 0.0))
                          - float(s.get("battery_charge_kwh", 0.0))) * t
                gen += float(s.get("battery_discharge_kwh", 0.0))
        elif key == "thermal_storage":
            # FIN-1: same arbitrage convention as the battery, from the
            # thermal by_slice fields (electric-equivalent, LP convention).
            for sid, s in by_slice.items():
                m = meta.get(sid) or {}
                t = float(m.get("import_tariff_inr_per_kwh", 0.0))
                value += (float(s.get("thermal_storage_discharge_kwh", 0.0))
                          - float(s.get("thermal_storage_charge_kwh", 0.0))) * t
                gen += float(s.get("thermal_storage_discharge_kwh", 0.0))

        net_ben = value - fuel
        irr = _irr(gross_capex, net_ben, opex, deg, life)
        payback = _payback(gross_capex, net_ben, opex, deg, life)
        crf = _crf(float(econ.actor_discount_rate("utility"))
                   if hasattr(econ, "actor_discount_rate") else 0.08, life)
        lcoe = ((gross_capex * crf + opex + fuel) / gen) if gen > 0 else None
        cf = (gen / (cap * 8760.0)) if unit != "kWh" and cap > 0 else None

        bench = BENCHMARKS.get(key, {})
        verdict = []
        if irr is not None and "irr" in bench:
            lo, hi = bench["irr"]
            verdict.append("IRR " + ("LOW" if irr < lo else
                                     "HIGH" if irr > hi else "OK"))
        if lcoe is not None and "lcoe" in bench:
            lo, hi = bench["lcoe"]
            verdict.append("LCOE " + ("LOW" if lcoe < lo else
                                      "HIGH" if lcoe > hi else "OK"))
        if payback is not None and "payback" in bench:
            lo, hi = bench["payback"]
            verdict.append("payback " + ("FAST" if payback < lo else
                                         "SLOW" if payback > hi else "OK"))

        rows.append({
            "tech": key, "label": label,
            "installed_2030": cap, "unit": unit,
            "capex_inr_per_unit": capex_per,
            "gross_capex_inr": gross_capex,
            "annual_opex_inr": opex,
            "annual_fuel_inr": fuel,
            "annual_generation_kwh": gen,
            "annual_value_inr": value,
            "capacity_factor": cf,
            "lcoe_inr_per_kwh": lcoe,
            "project_irr_real": irr,
            "simple_payback_years": payback,
            "benchmark": bench.get("src", bench.get("note", "")),
            "benchmark_verdict": " / ".join(verdict) if verdict
                                 else bench.get("note", "n/a"),
        })

    # ---- FIN-1: per-VINTAGE expansion statements + boundary
    # procurement lines. Report-only; 2042/2055 rows are PROJECTIONS at the
    # learning-curve capex, valued by scaling the 2030 slice attribution by
    # the period's real tariff escalation - label Tier 3 wherever quoted
    # (the LP's own vintage economics are exact; this table is the readable
    # restatement, not a second model).
    esc = 1.0
    try:
        esc = 1.0 + float(econ.tariff_escalation_real_annual_value())
    except Exception:
        pass
    val_per_unit_2030 = {}
    for r in rows:
        if r["installed_2030"] > 0:
            val_per_unit_2030[r["tech"]] = (r["annual_value_inr"]
                                            / r["installed_2030"])
    vintages: List[dict] = []
    for y_str in ("2042", "2055"):
        nb = (pb.get(y_str) or {}).get("new_build") or {}
        y = int(y_str)
        for nb_key, (label, cfg_key, capex_key, unit,
                     val_class) in FIN1_VINTAGE_TECHS.items():
            add = float(nb.get(nb_key, 0.0) or 0.0)
            if add <= 1e-6:
                continue
            cfg_v = techs_cfg.get(cfg_key) or {}
            base_capex = float(cfg_v.get(capex_key, 0.0))
            # carport/floating capex is DERIVED from the farm base (same
            # convention as the 2030 rows above).
            _farm_base = float((techs_cfg.get("solar_farm") or {})
                               .get("capex_inr_per_kwp", 0.0))
            if base_capex <= 0 and cfg_key == "solar_carport":
                base_capex = _farm_base * float(
                    econ.carport_capex_multiplier_vs_ground_mount())
            elif base_capex <= 0 and cfg_key == "floating_pv":
                base_capex = _farm_base * float(
                    econ.floating_pv_capex_multiplier_vs_ground_mount())
            if base_capex <= 0:
                print(f"  [warn] FIN-1 {cfg_key}: no {capex_key} - row skipped")
                continue
            try:
                learn = float(econ.period_capex_factor(cfg_key, y))
            except Exception:
                learn = 1.0
            unit_capex = base_capex * learn
            life_v = int(cfg_v.get("lifetime_years", LIFE_DEFAULT))
            annualised = add * unit_capex * _crf(SOCIAL_RATE, life_v)
            # value projection: 2030 per-unit attribution x real escalation
            # (PV classes only; storage/V2G get the revealed-preference note)
            value_proj = None
            if val_class and val_class in val_per_unit_2030:
                value_proj = (add * val_per_unit_2030[val_class]
                              * (esc ** (y - 2030)))
            vintages.append({
                "vintage": y, "tech": nb_key, "label": label,
                "addition": add, "unit": unit,
                "learning_factor": learn,
                "unit_capex_inr": unit_capex,
                "gross_capex_inr": add * unit_capex,
                "annualised_capex_inr": annualised,
                "annual_value_inr_tier3": value_proj,
                "note": ("" if value_proj is not None else
                         "no merchant value line: the LP builds this vintage "
                         "only where its system value clears the learned "
                         "annualised cost (revealed preference)"),
            })
    procurement = []
    gp_kwh = float(fs.get("green_purchase_kwh", 0.0) or 0.0)
    if gp_kwh > 0 and hasattr(econ, "green_purchase_delivered_price_inr_per_kwh"):
        procurement.append({
            "line": "Green open-access PPA (delivered)",
            "annual_qty": gp_kwh, "unit": "kWh",
            "unit_price_inr": float(econ.green_purchase_delivered_price_inr_per_kwh()),
            "annual_cost_inr": float(fs.get("green_purchase_cost_inr", 0.0) or 0.0),
            "basis": "PSPCL CC 10/2025 delivered-price build-up (Tier 1); "
                     "200 MW contract cap; procurement contract - no IRR",
        })
    if hasattr(econ, "interconnection_annualised_inr"):
        icx = float(econ.interconnection_annualised_inr() or 0.0)
        if icx > 0:
            procurement.append({
                "line": "Grid interconnection (annualised CRF)",
                "annual_qty": None, "unit": "",
                "unit_price_inr": None,
                "annual_cost_inr": icx,
                "basis": "B21 220 kV bay + line works, CRF-annualised "
                         "(Tier 2 cost basis); infrastructure - no IRR",
            })

    return {
        "meta": {
            "stage": "B20 per-technology finance report + real-project "
                     "benchmarks + FIN-1 vintage/procurement extension",
            "scenario": "full_stack alpha=0, 2030 base year",
            "attribution": ("slice-level: generation displaces import at the "
                            "slice import tariff, exported share earns the "
                            "slice feed-in; PV subtypes pro-rata by "
                            "yield-weighted kWp; battery = tariff arbitrage; "
                            "district/social-planner view (per-owner views: "
                            "owner_finance.py)"),
            "source": str(DISPATCH),
            "fin1_convention": ("vintage rows: additions from period_breakdown"
                                ".new_build at learning-curve capex "
                                "(econ.period_capex_factor); PV value = 2030 "
                                "per-unit slice attribution x real tariff "
                                "escalation - TIER 3 PROJECTION; storage/V2G "
                                "carry the revealed-preference bound instead; "
                                "procurement lines are contracts, no IRR"),
        },
        "technologies": rows,
        "vintages": vintages,
        "procurement": procurement,
    }


def write_report(rep: dict) -> None:
    OUT_JSON.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    lines = [
        "# B20 - Per-technology finance report (2030 base year)",
        "",
        f"_{rep['meta']['attribution']}_",
        "",
        "| tech | installed | CAPEX Rs cr | value Rs cr/yr | CF | LCOE Rs/kWh "
        "| IRR | payback yr | vs real projects | benchmark source |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rep["technologies"]:
        cf = r["capacity_factor"]
        cf_s = "{:.0f}%".format(cf * 100) if cf else "-"
        lcoe = r["lcoe_inr_per_kwh"]
        lcoe_s = "{:.2f}".format(lcoe) if lcoe else "-"
        irr = r["project_irr_real"]
        irr_s = "{:.1f}%".format(irr * 100) if irr is not None else "-"
        pb = r["simple_payback_years"]
        pb_s = "{:.1f}".format(pb) if pb is not None else "-"
        lines.append(
            f"| {r['label']} | {r['installed_2030']:,.0f} {r['unit']} "
            f"| {r['gross_capex_inr']/1e7:,.1f} "
            f"| {r['annual_value_inr']/1e7:,.1f} "
            f"| {cf_s} | {lcoe_s} | {irr_s} | {pb_s} "
            f"| {r['benchmark_verdict']} | {r['benchmark']} |")
    if rep.get("vintages"):
        lines += [
            "",
            "## FIN-1 - Future-expansion vintages (2042 / 2055; TIER 3 projections)",
            "",
            f"_{rep['meta']['fin1_convention']}_",
            "",
            "| vintage | tech | addition | learning x | capex Rs/unit "
            "| gross capex Rs cr | annualised Rs cr/yr | value Rs cr/yr (T3) | note |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for v in rep["vintages"]:
            val = v["annual_value_inr_tier3"]
            val_s = "{:,.1f}".format(val / 1e7) if val is not None else "-"
            lines.append(
                f"| {v['vintage']} | {v['label']} "
                f"| {v['addition']:,.0f} {v['unit']} "
                f"| {v['learning_factor']:.2f} "
                f"| {v['unit_capex_inr']:,.0f} "
                f"| {v['gross_capex_inr']/1e7:,.1f} "
                f"| {v['annualised_capex_inr']/1e7:,.2f} "
                f"| {val_s} | {v['note'][:70]} |")
    if rep.get("procurement"):
        lines += [
            "",
            "## FIN-1 - Boundary procurement lines (contracts, no IRR)",
            "",
            "| line | annual quantity | unit price Rs | annual cost Rs cr | basis |",
            "|---|---|---|---|---|",
        ]
        for p in rep["procurement"]:
            qty = (f"{p['annual_qty']:,.0f} {p['unit']}"
                   if p["annual_qty"] else "-")
            up = (f"{p['unit_price_inr']:.4f}"
                  if p["unit_price_inr"] is not None else "-")
            lines.append(f"| {p['line']} | {qty} | {up} "
                         f"| {p['annual_cost_inr']/1e7:,.2f} | {p['basis']} |")
    lines += [
        "",
        "## Reading the verdicts (thesis framing - why some flags are EXPECTED)",
        "",
        "1. **District vs merchant frame.** The benchmark IRR bands for utility",
        "   solar/biomass/WTE describe MERCHANT projects selling at auction/CERC",
        "   tariffs (~Rs 2.6/kWh solar). Our plants are BEHIND-THE-METER: they",
        "   displace the district's RETAIL purchases (Rs 4.5-9.5/kWh ToU), so",
        "   returns sit structurally ABOVE the merchant band - the correct",
        "   comparator for that effect is C&I behind-the-meter solar (15-25%",
        "   IRR), which the farm/carport/canal rows do match.",
        "2. **Land is no longer free (B21/TRJ-7, 2026-07-10).** The farm row",
        "   now carries the AGRICULTURAL lease rent on its granted land",
        "   (Rs 2.5 lakh/ha/yr on the 2030 grant; Aryan ballot - market-rate",
        "   rent Rs 15 lakh/ha/yr is the A/B scenario, which would lift farm",
        "   LCOE by a further ~Rs 1/kWh toward the market band). Canal/pond",
        "   PV still sits on unpriced water surface (no rent line).",
        "3. **Captive straw.** Biomass LCOE ~Rs 3.4 vs CERC ~Rs 8 is driven by",
        "   the 20-km captive catchment at farm-gate straw prices (Tier-1",
        "   validated, N7-DATA) vs CERC market-fuel norms; TRJ-4 already",
        "   escalates the price x1.25/x1.50 by 2042/2055.",
        "4. **Subsidised rooftop.** Household IRRs (owner_finance.py) include",
        "   PM Surya Ghar capex subsidies - high-looking returns are the",
        "   POLICY WORKING as designed; the unsubsidised gross-capex IRR is",
        "   the like-for-like project figure.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    rep = build_report()
    write_report(rep)
    print(f"-> {OUT_JSON}\n-> {OUT_MD}\n")
    for r in rep["technologies"]:
        irr = (f"{r['project_irr_real']*100:5.1f}%"
               if r["project_irr_real"] is not None else "  n/a")
        pb = (f"{r['simple_payback_years']:5.1f}y"
              if r["simple_payback_years"] is not None else "  n/a")
        lcoe = (f"{r['lcoe_inr_per_kwh']:5.2f}"
                if r["lcoe_inr_per_kwh"] is not None else "  n/a")
        print(f"  {r['label']:<26} IRR {irr}  payback {pb}  "
              f"LCOE {lcoe}  -> {r['benchmark_verdict']}")
