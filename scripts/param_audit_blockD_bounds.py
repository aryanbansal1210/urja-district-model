"""Block D of the physical parameter audit: EV / V2G / DSR
behavioural parameters. READ ONLY - measures, changes nothing.

Central question for EV: does the charging energy the model runs correspond
to a believable vehicle fleet? `charge_mult` is declared as "a fraction of
residential peak" and multiplied by a CELL's peak_base_kw, while the fleet it
is meant to represent is counted per HOUSEHOLD.
"""
from __future__ import annotations
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
RES = ("low_income_residential", "mid_income_residential",
       "high_income_residential")
INC = {"low_income_residential": "low", "mid_income_residential": "mid",
       "high_income_residential": "high"}


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


own = econ.ev_vehicle_ownership or {}
by_inc = own.get("by_income", {})
car_kwh = float(own.get("ev_car_kwh_per_day", 10.0))
e2w_kwh = float(own.get("e2w_kwh_per_day", 1.0))

# ---------------------------------------------------------------------------
# 1. Does the EV load match the fleet it claims to represent?
# ---------------------------------------------------------------------------
hdr("1. EV charging energy vs the vehicle fleet that is supposed to cause it")

agg = defaultdict(lambda: {"cells": 0, "hh": 0, "pkw": 0.0, "ev": 0.0})
for n in net.nodes:
    c = n.category_name
    if c not in RES:
        continue
    a = agg[c]
    a["cells"] += 1
    a["hh"] += n.households
    a["pkw"] += n.peak_base_kw
    for s in S:
        a["ev"] += n.peak_base_kw * econ.ev_demand_multiplier(c, s.id, None) \
            * s.hours_per_year

office_ev = 0.0
office_pkw = 0.0
for n in net.nodes:
    if n.category_name != "office":
        continue
    office_pkw += n.peak_base_kw
    for s in S:
        office_ev += n.peak_base_kw * econ.ev_demand_multiplier(
            "office", s.id, None) * s.hours_per_year

print(f"  {'tier':26s} {'HH':>7s} {'cars':>8s} {'e2w':>8s}"
      f" {'model kWh/d':>12s} {'fleet kWh/d':>12s} {'ratio':>7s}")
tot_cars = tot_e2w = 0.0
tot_model = tot_fleet = 0.0
for c in RES:
    a = agg[c]
    inc = INC[c]
    cars = a["hh"] * econ.ev_cars_per_household(inc)
    e2w = a["hh"] * econ.e2w_share(inc)
    fleet_kwh_d = cars * car_kwh + e2w * e2w_kwh
    model_kwh_d = a["ev"] / 365.0
    tot_cars += cars
    tot_e2w += e2w
    tot_model += model_kwh_d
    tot_fleet += fleet_kwh_d
    r = model_kwh_d / fleet_kwh_d if fleet_kwh_d > 0 else float("nan")
    print(f"  {c:26s} {a['hh']:7,d} {cars:8,.0f} {e2w:8,.0f}"
          f" {model_kwh_d:12,.0f} {fleet_kwh_d:12,.0f} {r:7.2f}x")
print(f"  {'TOTAL residential':26s} {sum(agg[c]['hh'] for c in RES):7,d}"
      f" {tot_cars:8,.0f} {tot_e2w:8,.0f}"
      f" {tot_model:12,.0f} {tot_fleet:12,.0f}"
      f" {tot_model/tot_fleet:7.2f}x")
print(f"\n  residential EV energy  {sum(agg[c]['ev'] for c in RES)/GWH:8.2f} GWh/yr")
print(f"  office EV energy       {office_ev/GWH:8.2f} GWh/yr")
print(f"  district EV energy     {(sum(agg[c]['ev'] for c in RES)+office_ev)/GWH:8.2f} GWh/yr")
print(f"\n  implied per-car charging: "
      f"{tot_model*365/max(tot_cars,1):,.0f} kWh/car/yr"
      f"  = {tot_model/max(tot_cars,1):,.1f} kWh/car/day"
      f"   (config says {car_kwh:.0f})")
print(f"  at 200 Wh/km that is {tot_model/max(tot_cars,1)/0.200:,.0f} km/car/day")

print("\n  WHY: charge_mult is applied to a CELL's peak_base_kw, not to its"
      " household count.")
print(f"  {'tier':26s} {'charge_mult':>11s} {'peak_base kW/cell':>18s}"
      f" {'HH/cell':>8s} {'kW/HH':>7s}")
for c in RES:
    a = agg[c]
    cm = by_inc.get(INC[c], {}).get("charge_mult", 0.0)
    print(f"  {c:26s} {cm:11.2f} {a['pkw']/a['cells']:18.1f}"
          f" {a['hh']/a['cells']:8.1f} {a['pkw']/a['hh']:7.2f}")

# ---------------------------------------------------------------------------
# 2. The EV scenario ladder: how much of it is live?
# ---------------------------------------------------------------------------
hdr("2. ev_adoption.scenarios - what actually moves between slow/default/fast")
print(f"  {'scenario':16s} {'res EV GWh':>11s} {'office EV GWh':>14s}"
      f" {'total GWh':>10s} {'v2g units':>10s}")
for name in ("2030_slow", "2030_default", "2030_fast"):
    r = o = 0.0
    for n in net.nodes:
        c = n.category_name
        if c in RES:
            for s in S:
                r += n.peak_base_kw * econ.ev_demand_multiplier(c, s.id, name) \
                    * s.hours_per_year
        elif c == "office":
            for s in S:
                o += n.peak_base_kw * econ.ev_demand_multiplier(c, s.id, name) \
                    * s.hours_per_year
    print(f"  {name:16s} {r/GWH:11.3f} {o/GWH:14.3f} {(r+o)/GWH:10.3f}"
          f" {net.v2g_units(econ):10,.0f}")
sc = econ.ev_adoption.get("scenarios", {})
print("\n  scenario fields and their Python read counts:")
print("    fleet_share            1 read   (office EV only)")
print("    household_adoption     3 reads  (FALLBACK ONLY - never fires,"
      " charge_mult is always present)")
print("    v2g_capable_fraction   0 reads  DEAD"
      f"   (declared {[sc[k].get('v2g_capable_fraction') for k in sc]})")

# ---------------------------------------------------------------------------
# 3. V2G fleet + throughput
# ---------------------------------------------------------------------------
hdr("3. V2G fleet")
for y in (None, 2030, 2042, 2055):
    u = net.v2g_units(econ, y)
    kwh = econ.v2g_kwh_per_unit_per_day_at(y) if y else econ.v2g_kwh_per_unit_per_day()
    print(f"  year {str(y):>5s}  units {u:9,.0f}  kWh/unit/day {kwh:6.2f}"
          f"  fleet throughput {u*kwh*365/GWH:7.2f} GWh/yr")
print()
for c in RES:
    inc = INC[c]
    hh = agg[c]["hh"]
    cars = hh * econ.ev_cars_per_household(inc)
    w = econ.v2g_willingness(inc)
    print(f"  {c:26s} HH {hh:7,d}  cars {cars:8,.0f}"
          f"  willingness {w:.2f}  -> V2G units {cars*w:8,.0f}")
print(f"  battery_kwh.ev_car = {own.get('battery_kwh',{}).get('ev_car')} kWh;"
      f"  v2g_kwh_per_unit_per_day = {econ.v2g_kwh_per_unit_per_day():.2f}"
      f"  ({100*econ.v2g_kwh_per_unit_per_day()/float(own.get('battery_kwh',{}).get('ev_car',30)):.0f}%"
      " of pack cycled per day, on top of driving)")

# ---------------------------------------------------------------------------
# 4. DSR: what is live, what is dead, and do the weights match the model?
# ---------------------------------------------------------------------------
hdr("4. demand_side_response - live vs dead, and the hardcoded pool weights")
p = econ.dsr_params()
print(f"  enabled                            {econ.dsr_enabled()}")
print(f"  aggregate_shiftable_fraction_in_peak {econ.dsr_aggregate_shiftable_fraction()}"
      "   <- the ONLY fraction the LP reads")
print(f"  shift_window_hours                 {econ.dsr_shift_window_hours()}"
      "   <- heuristic fallback only; the Pyomo path buckets per"
      " (month, day-type) = up to 24 h")
print(f"  comfort cost (weighted)            {econ.dsr_comfort_cost_inr_per_kwh():.4f} INR/kWh")
print("\n  categories: block - Python reads of dsr_category_params(): 0 (DEAD)")
for fam, cfg in (p.get("categories") or {}).items():
    keys = {k: v for k, v in cfg.items() if k != "applies_to"}
    print(f"    {fam:20s} {keys}")

# the hardcoded weights inside dsr_comfort_cost_inr_per_kwh
comp = defaultdict(float)
for n in net.nodes:
    c = n.category_name
    if not c:
        continue
    bp = econ.base_demand_profile.get(c)
    if bp is None:
        continue
    cbm = econ.cooling_factors.get("cooling_factor_by_month", {})
    cdp = econ.cooling_factors.get("cooling_daypart_shape", {})
    cdpm = econ.cooling_factors.get("cooling_daypart_shape_monsoon", {})
    mons = set(econ.cooling_factors.get("monsoon_months", []))
    hdp = econ.heating_loads.get("heating_daypart_shape", {})
    for s in S:
        h = s.hours_per_year
        wd = float(bp["weekday"][s.daypart]); we = float(bp["weekend"][s.daypart])
        ft = float(bp["festival"][s.daypart])
        bm = (s.weekday_share*wd + s.weekend_share*we + s.festival_share*ft)
        bm *= econ.behavioural_demand_multiplier(c, s, faith=n.faith)
        occm = econ.occupancy_monthly_modifier(c, s.month)
        dp = float((cdpm if (s.month in mons and cdpm) else cdp).get(s.daypart, 0.0))
        cf = float(cbm.get(s.month, 0.0)) * dp
        comp["base"] += n.peak_base_kw * bm * occm * h
        comp["cool"] += (n.peak_cooling_kw * cf * n.microclimate_cooling_multiplier
                         * econ._cooling_effectiveness(c, s.month)
                         * econ.heat_wave_cooling_multiplier(s.month) * occm) * h
        comp["heat"] += n.peak_heating_kw * (econ.heating_factor_for_month(s.month)
                                             * float(hdp.get(s.daypart, 0.0))) * h
        comp["ev"] += n.peak_base_kw * econ.ev_demand_multiplier(c, s.id, None) * h
TOT = sum(comp.values())
hard = {"ac_precool": 9.0, "geyser_thermal": 1.5, "ev_charging_window": 5.0}
real = {"ac_precool": 100*comp["cool"]/TOT * 0.30,
        "geyser_thermal": 100*comp["heat"]/TOT * 0.50,
        "ev_charging_window": 100*comp["ev"]/TOT * 1.00}
split = p.get("comfort_cost_by_category_inr_per_kwh") or {}
print("\n  pool weights are HARDCODED in energy/costs.py:3269-3273:")
print(f"  {'family':20s} {'hardcoded':>10s} {'docstring says':>16s}"
      f" {'model actual':>13s} {'x off':>7s} {'cost':>6s}")
docs = {"ac_precool": "cooling 30%", "geyser_thermal": "heating 3%",
        "ev_charging_window": "EV 5%"}
for k in hard:
    print(f"  {k:20s} {hard[k]:10.1f} {docs[k]:>16s} {real[k]:13.2f}"
          f" {real[k]/hard[k]:7.2f} {split.get(k,0):6.2f}")
cur = sum(hard[k]*split.get(k, 0) for k in hard) / sum(hard.values())
fix = sum(real[k]*split.get(k, 0) for k in hard) / sum(real.values())
print(f"  weighted comfort cost: current {cur:.4f} -> with the model's own"
      f" shares {fix:.4f} INR/kWh  ({100*(fix-cur)/cur:+.2f}%)")
print(f"  model composition: cooling {100*comp['cool']/TOT:.2f}%,"
      f" heating {100*comp['heat']/TOT:.2f}%, EV {100*comp['ev']/TOT:.2f}%")

# ---------------------------------------------------------------------------
# 5. The geyser_thermal conflation, and the two flexibility pools
# ---------------------------------------------------------------------------
hdr("5. flexibility pools: DSR 18% of peak, EV smart 60% of EV, geyser 50% of heating")
gy = 1.5 / (1.5 + 2.0)
print(f"  heating load {comp['heat']/GWH:.2f} GWh; config's own geyser share"
      f" {gy:.0%} -> geyser {comp['heat']*gy/GWH:.2f} GWh,"
      f" space heater {comp['heat']*(1-gy)/GWH:.2f} GWh")
print(f"  'geyser_thermal' credits 50% of the WHOLE heating load as shiftable"
      f" over a 12 h window = {0.50*comp['heat']/GWH:.2f} GWh")
print(f"  of which space heating (no tank, cannot be shifted 12 h) ="
      f" {0.50*comp['heat']*(1-gy)/GWH:.2f} GWh"
      f"  ({100*0.50*comp['heat']*(1-gy)/TOT:.2f}% of district)")
print("  (dead config today - dsr_category_params is unread - but this is the"
      " number the thesis methods section would quote)")

ev_tot = comp["ev"]
fr = econ.ev_shiftable_fraction("residential")
fw = econ.ev_shiftable_fraction("workplace")
print(f"\n  EV smart charging: residential f={fr}, workplace f={fw},"
      f" program cost {econ.ev_smart_charging_cost_inr_per_kwh()} INR/kWh")
print(f"  EV pool ~ {fr*ev_tot/GWH:.2f} GWh of {ev_tot/GWH:.2f} GWh EV energy")
peak_sl = defaultdict(float)
for n in net.nodes:
    c = n.category_name
    if not c:
        continue
    bp = econ.base_demand_profile.get(c)
    if bp is None:
        continue
    for s in S:
        wd = float(bp["weekday"][s.daypart]); we = float(bp["weekend"][s.daypart])
        ft = float(bp["festival"][s.daypart])
        bm = (s.weekday_share*wd + s.weekend_share*we + s.festival_share*ft)
        bm *= econ.behavioural_demand_multiplier(c, s, faith=n.faith)
        peak_sl[s.id] += n.peak_base_kw * bm
print(f"  DSR pool ~ 18% of peak-slice demand; EV energy is INSIDE that total,"
      f"\n  so the documented overlap is at most {min(fr*ev_tot, 0.18*TOT)/GWH:.2f} GWh"
      f" ({100*min(fr*ev_tot, 0.18*TOT)/TOT:.2f}% of district) - the config"
      " states 1-2%.")

# ---------------------------------------------------------------------------
# 6. Dead-field inventory
# ---------------------------------------------------------------------------
hdr("6. EV / V2G / DSR field usage (Python reads outside tests)")
print("""  ev_kwh_per_household_per_day      0  DEAD (10.0; the only place the
                                         '50 km/day at 200 Wh/km' basis is stated)
  ev_kwh_per_office_employee_per_day 0  DEAD (2.5)
  ev_charger_type_mix_office
      .share                         1  live
      .duty_cycle                    1  live
      .kwh_per_session               0  DEAD (5.0 / 12.0 / 2.5 - the numbers
                                         that make the mix look physical)
  ev_adoption.scenarios
      .fleet_share                   1  live (office EV only)
      .household_adoption            3  fallback only, never fires
      .v2g_capable_fraction          0  DEAD (0.20 / 0.35 / 0.55)
  demand_side_response.categories    0  DEAD (~35 lines: applies_to,
                                         shiftable_fraction_of_*, shift_window_hours)
  demand_side_response
      .comfort_cost_by_category      1  live, but with HARDCODED pool weights
      .aggregate_shiftable_fraction  1  live - the only DSR fraction in the LP
      .shift_window_hours            1  heuristic fallback only""")
