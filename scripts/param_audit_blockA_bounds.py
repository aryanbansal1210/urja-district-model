"""Block A bounding run - READ ONLY, no solve, no production writes.

Replicates network.demand_by_slice_kw's arithmetic but keeps the four
demand COMPONENTS (base / cooling / heating / ev) separate per category,
so each block-A finding can be sized against district annual energy.
"""
from __future__ import annotations
import os, sys, json
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = r"C:\Users\aryan\OneDrive - Imperial College London\PROJECT\SESSIONS\district_v3"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics
from energy.network import load_optimised_network

econ = load_economics()
net = load_optimised_network()
S = econ.slices
print(f"slices={len(S)}  nodes={len(net.nodes)}")

cooling_by_month = econ.cooling_factors.get("cooling_factor_by_month", {})
cool_dp = econ.cooling_factors.get("cooling_daypart_shape", {})
cool_dp_mon = econ.cooling_factors.get("cooling_daypart_shape_monsoon", {})
monsoon = set(econ.cooling_factors.get("monsoon_months", []))
heat_dp = econ.heating_loads.get("heating_daypart_shape", {})

# comp[(category, component)] -> annual kWh; also keep (component, month, hour)
ann = defaultdict(float)
by_mh = defaultdict(float)        # (component, month, hour) -> kWh
heat_by_cat_hour = defaultdict(float)

for n in net.nodes:
    if n.category_name is None:
        continue
    cat = n.category_name
    bp = econ.base_demand_profile.get(cat)
    for s in S:
        h = s.hours_per_year
        if bp is not None:
            wd = float(bp.get("weekday", {}).get(s.daypart, 0.5))
            we = float(bp.get("weekend", {}).get(s.daypart, 0.5))
            ft = float(bp.get("festival", {}).get(s.daypart, 0.5))
            bm = s.weekday_share * wd + s.weekend_share * we + s.festival_share * ft
        else:
            bm = 0.5
        bm *= econ.behavioural_demand_multiplier(cat, s, faith=n.faith)
        base_kw = n.peak_base_kw * bm

        dp = float((cool_dp_mon if (s.month in monsoon and cool_dp_mon) else cool_dp)
                   .get(s.daypart, 0.0))
        cf = float(cooling_by_month.get(s.month, 0.0)) * dp
        cool_kw = (n.peak_cooling_kw * cf * n.microclimate_cooling_multiplier
                   * econ._cooling_effectiveness(cat, s.month)
                   * econ.heat_wave_cooling_multiplier(s.month))

        occ = econ.occupancy_monthly_modifier(cat, s.month)
        if occ != 1.0:
            base_kw *= occ
            cool_kw *= occ

        hf = econ.heating_factor_for_month(s.month) * float(heat_dp.get(s.daypart, 0.0))
        heat_kw = n.peak_heating_kw * hf
        ev_kw = n.peak_base_kw * econ.ev_demand_multiplier(cat, s.id, None)

        ann[(cat, "base")] += base_kw * h
        ann[(cat, "cool")] += cool_kw * h
        ann[(cat, "heat")] += heat_kw * h
        ann[(cat, "ev")] += ev_kw * h
        by_mh[("base", s.month, int(s.hour))] += base_kw * h
        by_mh[("cool", s.month, int(s.hour))] += cool_kw * h
        by_mh[("heat", s.month, int(s.hour))] += heat_kw * h
        by_mh[("ev", s.month, int(s.hour))] += ev_kw * h
        heat_by_cat_hour[(cat, int(s.hour))] += heat_kw * h

sl_kwh = getattr(net, "grid_streetlight_kwh_yr", 0.0)
GWH = 1e6
tot = sum(ann.values()) + sl_kwh
print("\n=== DISTRICT ANNUAL DEMAND BY COMPONENT (GWh) ===")
for comp in ("base", "cool", "heat", "ev"):
    v = sum(x for (c, k), x in ann.items() if k == comp)
    print(f"  {comp:6s} {v/GWH:9.2f}  ({100*v/tot:5.2f}%)")
print(f"  street {sl_kwh/GWH:9.2f}  ({100*sl_kwh/tot:5.2f}%)")
print(f"  TOTAL  {tot/GWH:9.2f} GWh")

print("\n=== HEATING BY CATEGORY (GWh/yr) ===")
hc = sorted(((c, v) for (c, k), v in ann.items() if k == "heat" and v > 0),
            key=lambda x: -x[1])
for c, v in hc:
    print(f"  {c:26s} {v/GWH:8.3f}  ({100*v/sum(x for _, x in hc):5.1f}% of heat)")

print("\n=== HEATING BY HOUR-OF-DAY (GWh/yr, all cats) ===")
hh = defaultdict(float)
for (c, hr), v in heat_by_cat_hour.items():
    hh[hr] += v
th = sum(hh.values())
for hr in range(24):
    bar = "#" * int(60 * hh[hr] / max(hh.values()))
    print(f"  {hr:02d}  {hh[hr]/GWH:7.3f} ({100*hh[hr]/th:4.1f}%) {bar}")
night = sum(hh[hr] for hr in (0, 1, 2, 3, 4, 5))
print(f"  --> 00:00-06:00 heating = {night/GWH:.3f} GWh = {100*night/th:.1f}% of heat"
      f" = {100*night/tot:.2f}% of district demand")

print("\n=== COOLING BY CATEGORY (GWh/yr) ===")
cc = sorted(((c, v) for (c, k), v in ann.items() if k == "cool" and v > 0),
            key=lambda x: -x[1])
for c, v in cc:
    print(f"  {c:26s} {v/GWH:8.3f}")

print("\n=== EV ANNUAL + evening share ===")
evtot = sum(v for (c, k), v in ann.items() if k == "ev")
ev_h = defaultdict(float)
for (comp, m, hr), v in by_mh.items():
    if comp == "ev":
        ev_h[hr] += v
print(f"  EV total {evtot/GWH:.2f} GWh")
for lbl, hrs in (("18-22 (system peak)", (18, 19, 20, 21)),
                 ("00-04 (deep night)", (0, 1, 2, 3)),
                 ("22-02", (22, 23, 0, 1))):
    s_ = sum(ev_h[h] for h in hrs)
    print(f"    {lbl:22s} {s_/GWH:7.3f} GWh = {100*s_/max(evtot,1e-9):5.1f}%")

print("\n=== dec vs jul, residential, by hour (kWh, normalised per day) ===")
# day-count normalise: divide by hours_per_year in that (month,hour) bucket
hrs_mh = defaultdict(float)
for s in S:
    hrs_mh[(s.month, int(s.hour))] += s.hours_per_year
for m in ("dec", "jul"):
    row = []
    for hr in (2, 3, 4, 18, 20, 22):
        tot_kwh = sum(by_mh[(c, m, hr)] for c in ("base", "cool", "heat", "ev"))
        row.append(f"{hr:02d}h={tot_kwh/max(hrs_mh[(m,hr)],1e-9)/1000:6.2f}MW")
    print(f"  {m}: " + "  ".join(row))

json.dump({f"{k[0]}|{k[1]}": v for k, v in ann.items()},
          open(os.path.join(HERE, "blockA_ann.json"), "w"), indent=1)
print("\nwrote blockA_ann.json")
