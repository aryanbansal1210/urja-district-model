"""HEAT-1 verification: water heating and space heating as two loads.

Checks the things that could silently be wrong:
  1. running hours land in the range a real appliance runs
  2. the day's delivered energy equals running_hours x peak EXACTLY, i.e.
     the daypart profile really does say only "when" and never "how much"
  3. hot water is non-zero in every month and for every category
     that uses it, including a hospital in July
  4. the 02:00 phantom geyser is gone but the room heater at 02:00 is NOT
 was half right, and only half)
  5. income runs through appliance, litres and hours, not just the peak
  6. totals against the measured pre-split baseline

Baselines below were measured on commit 80e114d in, HEAT-1 not).
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
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]
RES = ("low_income_residential", "mid_income_residential",
       "high_income_residential")
INC = {c: c.split("_")[0] for c in RES}

BASE = {"district": 880.173067, "heating": 79.36, "res": 72.24,
        "low": 5.76, "mid": 25.28, "high": 41.21, "non_res": 7.12,
        "night_share": 27.9}


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


hpd = defaultdict(float)
for s in S:
    hpd[s.daypart] += s.hours_per_year
for k in hpd:
    hpd[k] /= 365.0

# ---------------------------------------------------------------------------
hdr("1. running hours - is this an appliance or a smeared average?")
print(f"  {'category':<28}{'DHW h/day':>11}{'space h/day':>13}{'verdict':>10}")
bad = 0
for c in list(RES) + ["school", "office", "hotel_guesthouse", "healthcare",
                      "restaurant_food_service"]:
    d = econ.dhw_running_hours(c)
    sp = econ.space_heating_running_hours(c)
    ok = (0.5 <= d <= 5.0) if c in RES else (0.5 <= d <= 8.0)
    bad += 0 if ok else 1
    print(f"  {c:<28}{d:>11.2f}{sp:>13.2f}{'OK' if ok else 'CHECK':>10}")
print(f"  a thermostatic geyser runs 1-3 h/day. before the split the single"
      f"\n  daypart shape delivered 12.20 h/day per unit of peak.")
print(f"  {'PASS' if bad == 0 else 'FAIL'}")

# ---------------------------------------------------------------------------
hdr("2. identity - does the profile say ONLY 'when'?")
print("  For the peak month, sum(factor x hours) over the day must equal the")
print("  running hours exactly, for both loads and every class.")
worst = 0.0
for c in RES + ("healthcare",):
    for key, want in (("dhw", econ.dhw_running_hours(c)),
                      ("space_heating", econ.space_heating_running_hours(c))):
        got = sum(econ._heat_daypart(key, c, dp) * hpd[dp] for dp in hpd)
        worst = max(worst, abs(got - want))
        print(f"  {c:<28}{key:<16}want {want:6.3f}  got {got:6.3f}"
              f"  err {abs(got - want):.2e}")
print(f"  max error {worst:.2e}   {'PASS' if worst < 1e-9 else 'FAIL'}")

# ---------------------------------------------------------------------------
hdr("3. hot water is never zero (PA-C1), including a hospital in July (PA-A2)")
print(f"  {'month':<7}{'DHW factor':>12}{'space factor':>14}")
zero = 0
for m in MONTHS:
    d = econ.dhw_month_factor(m)
    sp = econ.space_heating_month_factor(m)
    if d <= 0:
        zero += 1
    print(f"  {m:<7}{d:>12.3f}{sp:>14.3f}")
jul = [s for s in S if s.month == "jul" and s.daypart == "08_10"][0]
hosp = econ.heating_split_factor("healthcare", jul.id)
print(f"\n  hospital heating factor, July 08:00-10:00: {hosp:.5f}"
      f"   (was exactly 0.00000)")
print(f"  months with zero DHW: {zero}   was 7   "
      f"{'PASS' if zero == 0 and hosp > 0 else 'FAIL'}")

# ---------------------------------------------------------------------------
hdr("4. the 02:00 test - phantom geyser gone, real heater kept")
jan2 = [s for s in S if s.month == "jan" and s.daypart == "02_04"][0]
jan7 = [s for s in S if s.month == "jan" and s.daypart == "06_08"][0]
print(f"  {'tier':<8}{'DHW @02':>10}{'space @02':>12}{'DHW @07':>10}"
      f"{'space @07':>12}")
ok4 = True
for c in RES:
    d2 = econ._heat_daypart("dhw", c, "02_04")
    s2 = econ._heat_daypart("space_heating", c, "02_04")
    d7 = econ._heat_daypart("dhw", c, "06_08")
    s7 = econ._heat_daypart("space_heating", c, "06_08")
    if d2 != 0.0 or d7 <= 0.0:
        ok4 = False
    print(f"  {INC[c]:<8}{d2:>10.4f}{s2:>12.4f}{d7:>10.4f}{s7:>12.4f}")
print("  nobody draws hot water at 02:00, so DHW @02 must be exactly 0.")
print("  a room heater at 02:00 is real, and richer households run it longer:")
print(f"  space @02  low {econ._heat_daypart('space_heating', RES[0], '02_04'):.4f}"
      f"   mid {econ._heat_daypart('space_heating', RES[1], '02_04'):.4f}"
      f"   high {econ._heat_daypart('space_heating', RES[2], '02_04'):.4f}")
print(f"  {'PASS' if ok4 else 'FAIL'}")

# ---------------------------------------------------------------------------
hdr("5. income runs through the whole chain, not just the peak")
b = (econ.heating_loads or {}).get("dhw", {})
print(f"  {'tier':<8}{'appliance':>11}{'L/person':>10}{'people/HH':>11}"
      f"{'DHW h':>8}{'heater h':>10}{'DHW share':>11}")
for c in RES:
    print(f"  {INC[c]:<8}"
          f"{b['appliance_kw_by_category'][c]:>10.1f}kW"
          f"{b['hot_water_lpcd_by_category'][c]:>10.0f}"
          f"{b['people_per_household_by_category'][c]:>11.2f}"
          f"{econ.dhw_running_hours(c):>8.2f}"
          f"{econ.space_heating_running_hours(c):>10.1f}"
          f"{econ.heating_loads['dhw_share_of_peak_by_category'][c]:>11.2f}")

# ---------------------------------------------------------------------------
hdr("6. totals against the pre-split baseline")
by_cat = defaultdict(float)
by_dp = defaultdict(float)
for n in net.nodes:
    if n.category_name is None or n.peak_heating_kw <= 0:
        continue
    for s in S:
        kwh = (n.peak_heating_kw
               * econ.heating_split_factor(n.category_name, s.id)
               * s.hours_per_year)
        by_cat[n.category_name] += kwh
        by_dp[s.daypart] += kwh
tot = sum(by_cat.values())
res = sum(v for k, v in by_cat.items() if k in RES)
district = sum(net.demand_by_slice_kwh(econ).values())
print(f"  {'':<10}{'before GWh':>12}{'after GWh':>12}{'change':>10}"
      f"{'kWh/HH/yr':>12}")
hh = {c: sum(n.households for n in net.nodes if n.category_name == c)
      for c in RES}
for c in RES:
    v = by_cat[c] / 1e6
    print(f"  {INC[c]:<10}{BASE[INC[c]]:>12.2f}{v:>12.2f}"
          f"{(v / BASE[INC[c]] - 1) * 100:>9.1f}%"
          f"{by_cat[c] / hh[c]:>12.0f}")
print(f"  {'res tot':<10}{BASE['res']:>12.2f}{res / 1e6:>12.2f}"
      f"{(res / 1e6 / BASE['res'] - 1) * 100:>9.1f}%")
print(f"  {'non-res':<10}{BASE['non_res']:>12.2f}{(tot - res) / 1e6:>12.2f}"
      f"{((tot - res) / 1e6 / BASE['non_res'] - 1) * 100:>9.1f}%")
print(f"  {'heating':<10}{BASE['heating']:>12.2f}{tot / 1e6:>12.2f}"
      f"{(tot / 1e6 / BASE['heating'] - 1) * 100:>9.1f}%")
print(f"  {'DISTRICT':<10}{BASE['district']:>12.2f}{district / 1e6:>12.2f}"
      f"{(district / 1e6 / BASE['district'] - 1) * 100:>9.2f}%")

night = sum(v for dp, v in by_dp.items() if dp in ("00_02", "02_04", "04_06"))
print(f"\n  heating energy in 00:00-06:00: {night / tot * 100:.1f}%"
      f"   was {BASE['night_share']:.1f}%")
print("  what leaves the night lands on 06-08 and 18-22 - no PV, top tariff.")
