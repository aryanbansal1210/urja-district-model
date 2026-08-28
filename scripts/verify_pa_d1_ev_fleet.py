""" verification: EV charging load vs the fleet that is meant to cause it.

Runs BEFORE and AFTER the fix in the same process:

  OLD  ev_kw(cell, slice) = cell.peak_base_kw x charge_mult[tier] x shape[dp]
  NEW  ev_kw(cell, slice) = cell.households x kwh_per_HH_per_day[tier]
                            x shape[dp] / hours_per_day[dp]

The OLD path is reconstructed here arithmetically from the config, so this
script keeps working after `charge_mult` leaves the code. The NEW path is read
from the model itself, so what is printed is what the model will solve.

READ ONLY - changes nothing.
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

RES = ("low_income_residential", "mid_income_residential",
       "high_income_residential")
INC = {"low_income_residential": "low", "mid_income_residential": "mid",
       "high_income_residential": "high"}

# the OLD per-tier charge_mult, kept here as literals because the fix removes
# them from the config (audit doc table,
OLD_CHARGE_MULT = {"low": 0.03, "mid": 0.15, "high": 0.40}
OLD_CAR_KWH = 10.0          # config value before the fix

own = econ.ev_vehicle_ownership or {}
car_kwh = float(own.get("ev_car_kwh_per_day", 10.0))
e2w_kwh = float(own.get("e2w_kwh_per_day", 1.0))
shape = econ.ev_adoption.get("ev_charging_daypart_shape_residential", {})


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


# hours per DAY covered by each daypart, from the slice table itself
hours_per_day = defaultdict(float)
for s in S:
    hours_per_day[s.daypart] += s.hours_per_year
for dp in hours_per_day:
    hours_per_day[dp] /= 365.0

hdr("0. mechanism check")
print(f"  dayparts                 {len(hours_per_day)}")
print(f"  hours/day per daypart    "
      f"{sorted(set(round(v, 6) for v in hours_per_day.values()))}")
print(f"  residential shape sums   {sum(shape.values()):.6f}")
print(f"  ev_car_kwh_per_day       {car_kwh}  (was {OLD_CAR_KWH})")
print(f"  e2w_kwh_per_day          {e2w_kwh}")

# ---------------------------------------------------------------------------
agg = defaultdict(lambda: {"cells": 0, "hh": 0, "pkw": 0.0,
                           "old": 0.0, "new": 0.0})
for n in net.nodes:
    c = n.category_name
    if c not in RES:
        continue
    a = agg[c]
    a["cells"] += 1
    a["hh"] += n.households
    a["pkw"] += n.peak_base_kw
    inc = INC[c]
    # OLD: reconstructed. daily kWh = 2 h/daypart x sum(shape) x peak x mult
    a["old"] += (n.peak_base_kw * OLD_CHARGE_MULT[inc]
                 * sum(float(shape.get(dp, 0.0)) * hours_per_day[dp]
                       for dp in hours_per_day))
    # NEW: straight from the model, summed over one day of slices
    for s in S:
        a["new"] += net.ev_node_kw(econ, n, s, None) * s.hours_per_year
for c in RES:
    agg[c]["new"] /= 365.0        # annual kWh -> kWh/day

hdr("1. EV charging per tier: model load vs its own declared fleet")
print(f"  {'tier':<8}{'HH':>8}{'cars':>8}{'e-2W':>8}"
      f"{'OLD kWh/d':>12}{'NEW kWh/d':>12}{'change':>10}")
tot = {"hh": 0, "cars": 0.0, "e2w": 0.0, "old": 0.0, "new": 0.0}
for c in RES:
    a = agg[c]
    inc = INC[c]
    cars = a["hh"] * econ.ev_cars_per_household(inc)
    e2w = a["hh"] * econ.e2w_share(inc)
    print(f"  {inc:<8}{a['hh']:>8}{cars:>8.0f}{e2w:>8.0f}"
          f"{a['old']:>12.0f}{a['new']:>12.0f}"
          f"{(a['new'] / a['old'] - 1) * 100:>9.1f}%")
    for k, v in (("hh", a["hh"]), ("cars", cars), ("e2w", e2w),
                 ("old", a["old"]), ("new", a["new"])):
        tot[k] += v
print(f"  {'total':<8}{tot['hh']:>8}{tot['cars']:>8.0f}{tot['e2w']:>8.0f}"
      f"{tot['old']:>12.0f}{tot['new']:>12.0f}"
      f"{(tot['new'] / tot['old'] - 1) * 100:>9.1f}%")

hdr("2. implied use per EV car (the finding)")
old_per_car = tot["old"] and (tot["old"] - tot["e2w"] * e2w_kwh) / tot["cars"]
new_per_car = (tot["new"] - tot["e2w"] * e2w_kwh) / tot["cars"]
print(f"  OLD  {old_per_car:6.1f} kWh/car/day = "
      f"{old_per_car / 0.200:6.0f} km/day at 200 Wh/km")
print(f"  NEW  {new_per_car:6.1f} kWh/car/day = "
      f"{new_per_car / 0.200:6.0f} km/day at 200 Wh/km")
print("  CEEW 'How Urban India Moves' anchor: 25-35 km/day (Tier 2 -> Tier 3)")

hdr("3. per-household equity check (this is what PA-D1 broke)")
print(f"  {'tier':<8}{'OLD kW/HH':>12}{'NEW kW/HH':>12}"
      f"{'OLD kWh/HH/d':>15}{'NEW kWh/HH/d':>15}")
old_hh, new_hh = {}, {}
for c in RES:
    a = agg[c]
    old_hh[c] = a["old"] / a["hh"]
    new_hh[c] = a["new"] / a["hh"]
    print(f"  {INC[c]:<8}{a['old'] / a['hh'] / 24:>12.4f}"
          f"{a['new'] / a['hh'] / 24:>12.4f}"
          f"{old_hh[c]:>15.3f}{new_hh[c]:>15.3f}")
print(f"  high:low ratio   OLD {old_hh[RES[2]] / old_hh[RES[0]]:6.1f}x"
      f"   NEW {new_hh[RES[2]] / new_hh[RES[0]]:6.1f}x")
print("  NEW ratio must equal the fleet ratio, because it IS the fleet ratio.")

hdr("4. district totals")
# compare like with like: the OLD reconstruction above is RESIDENTIAL only, so
# the office term has to be held out of both sides or the delta is overstated.
dem = net.demand_by_slice_kwh(econ)
dis = sum(dem.values())
ev_all = sum(net.ev_charging_kwh_by_slice(econ, year=None).values())
ev_res_new = sum(a["new"] for a in agg.values()) * 365.0
ev_office = ev_all - ev_res_new
print(f"  district demand           {dis / 1e6:10.2f} GWh")
print(f"  EV total (NEW)            {ev_all / 1e6:10.2f} GWh"
      f"   = {ev_all / dis * 100:.2f}% of demand")
print(f"    of which residential    {ev_res_new / 1e6:10.2f} GWh")
print(f"    of which office         {ev_office / 1e6:10.2f} GWh  (untouched)")
print(f"  residential EV OLD        {tot['old'] * 365 / 1e6:10.2f} GWh")
print(f"  delta on district         "
      f"{(ev_res_new - tot['old'] * 365) / 1e6:+10.2f} GWh"
      f"   = {(ev_res_new - tot['old'] * 365) / dis * 100:+.2f}% of demand")

hdr("5. the period ramp: identity holds, VALUES move (and should)")
# Careful with the claim here. Two different things:
#   (a) IDENTITY - ev_charge_ramp_factor must equal the ratio of the daily
#       energy function at two years. It now delegates to that function, so
#       this is exact by construction and this check guards the delegation.
#   (b) VALUES - the ramps DO change, because a smaller kWh/car/day means a
#       growing car fleet adds less. That is the fix working, not a defect.
print(f"  {'tier':<8}{'2042 now':>10}{'2042 @10':>10}"
      f"{'2055 now':>10}{'2055 @10':>10}")
for c in RES:
    inc = INC[c]
    row = [inc]
    for y in (2042, 2055):
        now = econ.ev_charge_ramp_factor(inc, y)
        # what the same ramp would have been at the old 10 kWh/car/day
        c30 = econ.ev_cars_per_household(inc)
        cy = econ.ev_cars_per_household(inc, y)
        e2 = econ.e2w_share(inc)
        old = ((cy * OLD_CAR_KWH + e2 * e2w_kwh)
               / (c30 * OLD_CAR_KWH + e2 * e2w_kwh))
        # (a) the identity, to machine precision
        ratio = (econ.ev_kwh_per_household_per_day(inc, y)
                 / econ.ev_kwh_per_household_per_day(inc, None))
        assert abs(ratio - now) < 1e-12, (inc, y, ratio, now)
        row += [f"{now:>10.4f}", f"{old:>10.4f}"]
    print(f"  {row[0]:<8}{''.join(row[1:])}")
print("  identity ev_charge_ramp_factor == energy ratio: OK (asserted)")

hdr("6. non-residential must be UNCHANGED (measured, not assumed)")
# measured at HEAD 17f6c83 in an isolated git worktree, i.e. with and
# applied but not: office 0.172955 GWh. It must not move, because
# ev_node_kw routes office through the untouched fraction-of-peak branch.
HEAD_OFFICE_GWH = 0.172955
office = 0.0
for n in net.nodes:
    if n.category_name != "office":
        continue
    for s in S:
        office += net.ev_node_kw(econ, n, s, None) * s.hours_per_year
delta = office / 1e6 - HEAD_OFFICE_GWH
print(f"  office EV  now {office / 1e6:.6f} GWh"
      f"   HEAD {HEAD_OFFICE_GWH:.6f} GWh   delta {delta:+.6f}")
print("  " + ("OK - byte-identical" if abs(delta) < 5e-7 else "*** MOVED ***"))

hdr("7. district totals against the measured HEAD baseline")
# HEAD 17f6c83, same worktree run
HEAD = {"low": 0.200286, "mid": 3.203746, "high": 5.073044,
        "res": 8.477077, "district": 883.393308}
now_res = {INC[c]: 0.0 for c in RES}
for n in net.nodes:
    c = n.category_name
    if c not in RES:
        continue
    for s in S:
        now_res[INC[c]] += net.ev_node_kw(econ, n, s, None) * s.hours_per_year
print(f"  {'tier':<10}{'HEAD GWh':>12}{'now GWh':>12}{'change':>10}")
for k in ("low", "mid", "high"):
    v = now_res[k] / 1e6
    print(f"  {k:<10}{HEAD[k]:>12.6f}{v:>12.6f}"
          f"{(v / HEAD[k] - 1) * 100:>9.1f}%")
res_now = sum(now_res.values()) / 1e6
print(f"  {'res total':<10}{HEAD['res']:>12.6f}{res_now:>12.6f}"
      f"{(res_now / HEAD['res'] - 1) * 100:>9.1f}%")
d_now = sum(net.demand_by_slice_kwh(econ).values()) / 1e6
print(f"  {'district':<10}{HEAD['district']:>12.6f}{d_now:>12.6f}"
      f"{(d_now / HEAD['district'] - 1) * 100:>9.2f}%")
print(f"  district falls by {HEAD['district'] - d_now:.6f} GWh, which must"
      f" equal the residential EV drop {HEAD['res'] - res_now:.6f} GWh")
