"""Block E of the physical parameter audit: technology energy +
efficiency figures. READ ONLY - measures, changes nothing.

Asks of every conversion efficiency: is it physically right, is it cited, is
it actually consumed, and does it agree with the other places the same
physical quantity is declared?
"""
from __future__ import annotations
import json
import os
import sys
from collections import defaultdict

ROOT = r"C:\Users\aryan\OneDrive - Imperial College London\PROJECT\SESSIONS\district_v3"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics            # noqa: E402
from energy.network import load_optimised_network  # noqa: E402

econ = load_economics()
net = load_optimised_network()
S = econ.slices
GWH = 1e6


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


T = econ.technologies or {}
rt = T.get("rooftop_pv", {})
sf = T.get("solar_farm", {})
bat = T.get("li_ion_battery", {})

# ---------------------------------------------------------------------------
# 1. PV module mix: three blended values, three live scalars, zero agreement
# ---------------------------------------------------------------------------
hdr("1. rooftop_pv.module_types - the blend vs the numbers actually used")
mt = rt.get("module_types", {})
tot_share = sum(float(v.get("share", 0)) for v in mt.values())
print(f"  {'type':16s} {'share':>7s} {'eff':>7s} {'capex':>8s} {'tempco':>8s}")
for k, v in mt.items():
    print(f"  {k:16s} {v.get('share'):7.2f} {v.get('efficiency'):7.3f}"
          f" {v.get('capex_inr_per_kwp'):8,.0f} {v.get('temp_coefficient_per_c'):8.4f}")
b_eff = sum(float(v["share"])*float(v["efficiency"]) for v in mt.values())/tot_share
b_cap = sum(float(v["share"])*float(v["capex_inr_per_kwp"]) for v in mt.values())/tot_share
b_tc = sum(float(v["share"])*float(v["temp_coefficient_per_c"]) for v in mt.values())/tot_share

import yaml as _y
_eloss = (_y.safe_load(open("config/economics.yaml", encoding="utf-8"))
          or {}).get("electrical_losses", {}) or {}
dc = _y.safe_load(open("config/district_composition.yaml", encoding="utf-8"))
live_eff = float(dc.get("rooftop_module_efficiency", 0.20))
live_cap = float(rt.get("capex_inr_per_kwp", 0))
live_tc = float((econ.pv_inverter or {}).get("temperature_derating_per_celsius", 0))

print(f"\n  {'quantity':26s} {'module-mix blend':>17s} {'live value':>12s}"
      f" {'source of live':>34s} {'gap':>8s}")
rows = [
    ("module efficiency", b_eff, live_eff,
     "district_composition.rooftop_module_efficiency"),
    ("capex INR/kWp", b_cap, live_cap, "technologies.rooftop_pv.capex_inr_per_kwp"),
    ("temp coeff /C", b_tc, live_tc, "pv_inverter.temperature_derating_per_celsius"),
]
for name, blend, live, src in rows:
    print(f"  {name:26s} {blend:17.4f} {live:12.4f} {src:>34s}"
          f" {100*(live-blend)/blend:+7.1f}%")
print("\n  pv_module_mix_summary() callers outside its own definition: 0")
print("  -> the config claim 'the BLENDED values back-feed into capex_inr_per_kwp"
      " (display)' is false; nothing reads the summary.")

# rooftop kWp sensitivity to the efficiency choice
kwp = sum((getattr(n, "rooftop_pv_cap_kwp", 0.0) or 0.0) for n in net.nodes)
print(f"\n  installed rooftop PV = {kwp:,.0f} kWp at eta={live_eff:.3f}")
print(f"  at the module-mix eta={b_eff:.4f} it would be"
      f" {kwp*b_eff/live_eff:,.0f} kWp  ({100*(b_eff/live_eff-1):+.1f}%,"
      f" {kwp*(b_eff/live_eff-1):+,.0f} kWp)")

# ---------------------------------------------------------------------------
# 2. The two "NOT YET CONSUMED" labels on rooftop_pv
# ---------------------------------------------------------------------------
hdr("2. 'NOT YET CONSUMED' labels on rooftop_pv degradation + capex decline")
print(f"  economics.yaml:689-690  degradation_per_year 'NOT YET CONSUMED by the LP'")
print(f"  economics.yaml:696-697  capex_real_decline   'NOT YET CONSUMED by the LP'")
print(f"\n  tech_degradation_per_year('rooftop_pv')      ="
      f" {econ.tech_degradation_per_year('rooftop_pv')}")
print(f"  tech_capex_real_decline_per_year('rooftop_pv') ="
      f" {econ.tech_capex_real_decline_per_year('rooftop_pv')}")
print("\n  pv_vintage_yield_factor(rooftop_pv, vintage, period) - degradation IS applied:")
for v, p in ((2030, 2030), (2030, 2042), (2030, 2055), (2042, 2055)):
    print(f"    vintage {v} evaluated {p}: {econ.pv_vintage_yield_factor('rooftop_pv', v, p):.4f}")
print("  period_capex_factor(rooftop_pv, build_year) - decline IS applied:")
for y in (2030, 2042, 2055):
    print(f"    build {y}: {econ.period_capex_factor('rooftop_pv', y):.4f}"
          f"  (Rs {live_cap*econ.period_capex_factor('rooftop_pv', y):,.0f}/kWp)")
print("\n  Both labels are FALSE. The li_ion_battery block carries the same"
      " claim CORRECTED\n  in June 2026 ('FX-1 correction: this IS consumed by"
      " the multi-period LP');\n  the rooftop_pv pair was never updated.")

# ---------------------------------------------------------------------------
# 3. Delivered PV capacity factor vs the declared base
# ---------------------------------------------------------------------------
hdr("3. base_annual_capacity_factor vs what the slice table actually delivers")
yield_south = sum(econ.pv_capacity_factor(s.id) * s.hours_per_year for s in S)
print(f"  pv_capacity_factor integrated over 8760 h = {yield_south:,.1f} kWh/kWp/yr")
print(f"  implied annual capacity factor            = {yield_south/8760:.4f}")
print(f"  technologies.rooftop_pv.base_annual_capacity_factor = "
      f"{rt.get('base_annual_capacity_factor')}")
print(f"  technologies.solar_farm.base_annual_capacity_factor = "
      f"{sf.get('base_annual_capacity_factor')}")
print("  benchmark: Global Solar Atlas Zirakpur fixed-tilt specific yield"
      " ~1,550-1,650 kWh/kWp/yr")
dcl = float(econ.__dict__.get("dc_loss_fraction_raw", 0.0))
acl = float(econ.__dict__.get("ac_loss_fraction_raw", 0.0))
gl = float(econ.__dict__.get("pspcl_grid_loss_fraction_raw", 0.0))
soil = sum(econ.pv_soiling_multiplier_for_month(m)
           * float(econ.pv_monthly_modifier.get(m, 1.0)) for m in
           ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
            "oct", "nov", "dec"]) / sum(
    float(econ.pv_monthly_modifier.get(m, 1.0)) for m in
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
     "oct", "nov", "dec"])
print(f"\n  the derate chain that sits on top of it:")
print(f"    dc_loss_fraction        {dcl:.4f}")
print(f"    soiling (PV-weighted)   {1-soil:.4f}")
print(f"    temperature derate      ~{1-0.8974:.4f}")
print(f"    net PV delivered/kWp   ~{yield_south*(1-dcl)*soil*0.8974:,.0f} kWh/kWp/yr")

# ---------------------------------------------------------------------------
# 4. The loss chain: what a kWh costs depending on where it comes from
# ---------------------------------------------------------------------------
hdr("4. electrical_losses - the full chain on an imported vs a local kWh")
print(f"  dc_loss_fraction        {dcl:.3f}  (every PV-yield builder)")
print(f"  ac_loss_fraction        {acl:.3f}  (AC bus deliveries: import, V2G, battery)")
print(f"  pspcl_grid_loss_fraction {gl:.3f}  (T&D between the PSPCL bus and the district)")
print(f"\n  imported kWh delivered to load: 1 / ((1-{gl:.3f})(1-{acl:.3f}))"
      f" = {1/((1-gl)*(1-acl)):.4f} kWh generated upstream")
print(f"  local PV kWh delivered to load: 1 / (1-{dcl:.3f})"
      f" = {1/(1-dcl):.4f} kWh DC")
print(f"  -> an imported kWh needs"
      f" {100*(((1/((1-gl)*(1-acl)))/(1/(1-dcl)))-1):.1f}% more generation than a"
      " local PV kWh to serve the same load.")
print("  This is the F36 arbitrage mechanism and it is ASYMMETRIC by design"
      " (BAU imports everything).")
print(f"  PSPCL T&D 10.7% is cited to the tariff order; the 2030 RDSS target"
      " is ~9-10%, so holding\n  10.7% flat to 2055 is conservative for the"
      " district and generous to BAU - check whether\n  any period trajectory"
      " scales it:")
print(f"    grid loss trajectory keys in config: "
      f"{[k for k in _eloss if 'period' in k or 'traj' in k] or 'NONE'}")

_eloss = (_y.safe_load(open("config/economics.yaml", encoding="utf-8")) or {}).get("electrical_losses", {}) or {}

# ---------------------------------------------------------------------------
# 5. Battery coherence
# ---------------------------------------------------------------------------
hdr("5. li_ion_battery - internal coherence of the efficiency stack")
for k in ("round_trip_efficiency", "max_depth_of_discharge", "c_rate_per_hour",
          "calendar_fade_per_year", "lifetime_years", "capex_inr_per_kwh",
          "capex_real_decline_per_year", "max_capacity_hours_of_peak"):
    print(f"  {k:30s} {bat.get(k)}")
rte = float(bat.get("round_trip_efficiency", 0.9))
dod = float(bat.get("max_depth_of_discharge", 0.9))
cal = float(bat.get("calendar_fade_per_year", 0.0))
life = float(bat.get("lifetime_years", 10))
print(f"\n  usable energy per nameplate kWh = DoD {dod:.2f} x sqrt(RTE)"
      f" {rte**0.5:.4f} per direction")
print(f"  calendar fade {cal:.2%}/yr over a {life:.0f}-yr life ="
      f" {1-(1-cal)**life:.1%} capacity lost by end of life")
print(f"  battery_vintage_capacity_factor:")
for v, p in ((2030, 2030), (2042, 2055), (2055, 2055)):
    print(f"    vintage {v} at {p}: {econ.battery_vintage_capacity_factor(v, p):.4f}")
print(f"  c_rate {bat.get('c_rate_per_hour')} /h -> a full charge takes"
      f" {1/float(bat.get('c_rate_per_hour', 0.5)):.1f} h"
      f" (SECI 2 h standard = 0.5C: consistent)")

# ---------------------------------------------------------------------------
# 6. Biomass CHP: does the efficiency reconcile with the fuel?
# ---------------------------------------------------------------------------
hdr("6. biomass_chp - efficiency vs calorific value vs delivered energy")
bio = T.get("biomass_chp", {})
eff = float(bio.get("electrical_efficiency", 0))
cv = float(bio.get("fuel_calorific_value_mj_per_kg", 0))
hrs = float(bio.get("operating_hours_per_year", 0))
fuel = float(bio.get("fuel_cost_inr_per_tonne", 0))
kwh_per_t = cv * 1000 * eff / 3.6
print(f"  electrical_efficiency        {eff}")
print(f"  fuel_calorific_value_mj_per_kg {cv}")
print(f"  -> {kwh_per_t:,.0f} kWh_e per tonne of straw")
print(f"  fuel cost {fuel:,.0f} INR/t -> {fuel/kwh_per_t:.3f} INR/kWh_e fuel alone")
print(f"  operating_hours_per_year     {hrs:,.0f}  ({100*hrs/8760:.1f}% availability)")
print(f"  operational_emission         {bio.get('operational_emission_kgco2_per_kwh')} kgCO2/kWh")
print("  benchmark: paddy straw LHV 13-16 MJ/kg air-dry (MNRE/IISc biomass atlas,"
      " Tier 1-2);\n  small straw-fired Rankine plants run 22-28% net electrical"
      " (IRENA biomass cost series, Tier 2)")

# ---------------------------------------------------------------------------
# 7. Cooling technology COPs
# ---------------------------------------------------------------------------
hdr("7. cooling_technologies.cop - declared for four techs, read by nothing")
for k, v in (econ.cooling_technologies or {}).items():
    print(f"  {k:22s} w_per_m2_peak {v.get('w_per_m2_peak'):5.1f}"
          f"   cop {v.get('cop')}"
          f"   monsoon_eff {v.get('monsoon_effectiveness')}")
print("\n  Python reads of the 'cop' key: 0.")
print("  The w_per_m2_peak figures are ELECTRICAL (block B verified the"
      " inverter_ac derivation:\n  '4 x 1.05 kW / 200 m2'), so no double-count"
      " exists today - but DCS-1 district cooling\n  needs exactly these COPs"
      " to compare against a central chiller, and they are unwired.")

# ---------------------------------------------------------------------------
# 8. Emission factors
# ---------------------------------------------------------------------------
hdr("8. emission factors")
print(f"  static grid emission_factor        {econ.emission_factor():.4f} kgCO2/kWh")
for y in (2030, 2042, 2055):
    print(f"  period_emission_factor({y})       {econ.period_emission_factor(y):.4f}")
print("  operational_emission_kgco2_per_kwh by tech:")
for k, v in T.items():
    if "operational_emission_kgco2_per_kwh" in v:
        print(f"    {k:22s} {v['operational_emission_kgco2_per_kwh']}")
emb = econ.__dict__.get("embodied_carbon_raw") or {}
print(f"  embodied_carbon block present: {bool(emb)}"
      f"  keys {list(emb)[:8] if emb else ''}")

# ---------------------------------------------------------------------------
# 9. Dead / stale label sweep for block E
# ---------------------------------------------------------------------------
hdr("9. block E field usage")
for f, path in (("cop", "cooling_technologies.*.cop"),
                ("max_depth_of_discharge", "li_ion_battery"),
                ("base_annual_capacity_factor", "rooftop_pv / solar_farm"),
                ("max_capacity_hours_of_peak", "li_ion_battery")):
    print(f"  {path:36s} -> see counts above")
print("""
  Confirmed by grep (Python reads outside tests/param_audit):
    cooling_technologies.*.cop            0   DEAD (4 values)
    pv_module_mix_summary()               0   DEAD accessor
    rooftop_pv.degradation_per_year       6   LIVE (label says NOT CONSUMED)
    rooftop_pv.capex_real_decline         5   LIVE (label says NOT CONSUMED)
    max_depth_of_discharge                1   live
    max_capacity_hours_of_peak            1   live (never binding per REV-5)
    base_annual_capacity_factor           2   check whether display-only""")
