"""Block B: per-category norms. Do the intensities produce believable
per-household / per-capita energy? READ ONLY."""
from __future__ import annotations
import os, sys
from collections import defaultdict
ROOT = r"C:\Users\aryan\OneDrive - Imperial College London\PROJECT\SESSIONS\district_v3"
sys.path.insert(0, ROOT); os.chdir(ROOT)
from energy.costs import load_economics
from energy.network import load_optimised_network
from core.land_use import CATEGORY_CATALOGUE

econ = load_economics(); net = load_optimised_network(); S = econ.slices
GWH = 1e6
cool_by_m = econ.cooling_factors.get("cooling_factor_by_month", {})
cdp = econ.cooling_factors.get("cooling_daypart_shape", {})
cdpm = econ.cooling_factors.get("cooling_daypart_shape_monsoon", {})
mons = set(econ.cooling_factors.get("monsoon_months", []))
hdp = econ.heating_loads.get("heating_daypart_shape", {})

ann = defaultdict(lambda: defaultdict(float))   # cat -> comp -> kWh
meta = defaultdict(lambda: {"cells":0,"floor":0.0,"hh":0,"occ":0,
                            "pb":0.0,"pc":0.0,"ph":0.0,"kwp":0.0})
OCC = {c.name: c.occupants_per_cell for c in CATEGORY_CATALOGUE.values() if c}
BASEW = {c.name: c.base_load_w_per_m2 for c in CATEGORY_CATALOGUE.values() if c}

for n in net.nodes:
    if not n.category_name: continue
    c = n.category_name
    m = meta[c]; m["cells"] += 1; m["hh"] += n.households
    m["pb"] += n.peak_base_kw; m["pc"] += n.peak_cooling_kw; m["ph"] += n.peak_heating_kw
    m["kwp"] += getattr(n, "rooftop_pv_cap_kwp", 0.0) or 0.0
    m["occ"] += OCC.get(c, 0)
    bp = econ.base_demand_profile.get(c)
    for s in S:
        h = s.hours_per_year
        wd=float(bp["weekday"][s.daypart]); we=float(bp["weekend"][s.daypart])
        ft=float(bp["festival"][s.daypart])
        bm=(s.weekday_share*wd+s.weekend_share*we+s.festival_share*ft)
        bm*=econ.behavioural_demand_multiplier(c, s, faith=n.faith)
        occm = econ.occupancy_monthly_modifier(c, s.month)
        dp=float((cdpm if (s.month in mons and cdpm) else cdp).get(s.daypart,0.0))
        cf=float(cool_by_m.get(s.month,0.0))*dp
        ann[c]["base"] += n.peak_base_kw*bm*occm*h
        ann[c]["cool"] += (n.peak_cooling_kw*cf*n.microclimate_cooling_multiplier
                           * econ._cooling_effectiveness(c,s.month)
                           * econ.heat_wave_cooling_multiplier(s.month))*occm*h
        ann[c]["heat"] += n.peak_heating_kw*(econ.heating_factor_for_month(s.month)
                                             *float(hdp.get(s.daypart,0.0)))*h
        ann[c]["ev"]   += n.peak_base_kw*econ.ev_demand_multiplier(c,s.id,None)*h

# floor area from the authoritative config table
fa = {}
try:
    import yaml
    dc = yaml.safe_load(open("config/district_composition.yaml", encoding="utf-8"))
    fa = dc.get("floor_area_per_cell_m2", {}) or {}
except Exception as e:
    print("(district_composition read failed:", e, ")")

RES = ("low_income_residential","mid_income_residential","high_income_residential")
print("=== RESIDENTIAL: per-household and per-capita annual kWh ===")
print(f"{'tier':28s} {'cells':>5s} {'HH':>7s} {'pop':>7s} {'m2/HH':>6s}"
      f" {'base':>8s} {'cool':>8s} {'heat':>8s} {'TOTAL':>9s} {'kWh/HH':>9s} {'kWh/cap':>8s}")
tot_pop = 0; tot_kwh = 0.0
for c in RES:
    a = ann[c]; m = meta[c]
    pop = m["occ"]; hh = m["hh"]
    t = a["base"]+a["cool"]+a["heat"]+a["ev"]
    tot_pop += pop; tot_kwh += t
    f_hh = (fa.get(c,0)*m["cells"]/hh) if hh else 0
    print(f"{c:28s} {m['cells']:5d} {hh:7,d} {pop:7,d} {f_hh:6.0f}"
          f" {a['base']/GWH:8.1f} {a['cool']/GWH:8.1f} {a['heat']/GWH:8.1f}"
          f" {t/GWH:9.1f} {t/max(hh,1):9,.0f} {t/max(pop,1):8,.0f}")
print(f"{'RESIDENTIAL TOTAL':28s} {'':5s} {'':7s} {tot_pop:7,d} {'':6s}"
      f" {'':8s} {'':8s} {'':8s} {tot_kwh/GWH:9.1f} {'':9s} {tot_kwh/tot_pop:8,.0f}")

grand = sum(sum(a.values()) for a in ann.values())
print(f"\n  district total (excl. streetlight) {grand/GWH:.1f} GWh"
      f"   per-capita over residential pop {grand/tot_pop:,.0f} kWh/cap/yr")
print("  benchmarks: Punjab PSPCL domestic ~1,600-2,000 kWh/HH/yr (Tier 1 tariff order);"
      "\n              India urban all-sector per-capita ~1,300-1,600 kWh (CEA, Tier 1);"
      "\n              CLAUDE.md records the FX-3 landing at ~3,235 kWh/cap")

print("\n=== ALL CATEGORIES: intensity, floor, energy, implied kWh/m2/yr ===")
print(f"{'category':28s} {'W/m2':>5s} {'cells':>5s} {'floor m2':>10s}"
      f" {'GWh/yr':>8s} {'kWh/m2/yr':>9s} {'%dist':>6s}")
rows = sorted(ann, key=lambda c: -sum(ann[c].values()))
for c in rows:
    m = meta[c]; t = sum(ann[c].values())
    floor = fa.get(c, 0)*m["cells"]
    print(f"{c:28s} {BASEW.get(c,0):5.1f} {m['cells']:5d} {floor:10,.0f}"
          f" {t/GWH:8.2f} {t/max(floor,1):9.1f} {100*t/grand:6.2f}")

print("\n=== floor area per capita by tier (equity read) ===")
tf = sum(fa.get(c,0)*meta[c]["cells"] for c in RES)
for c in RES:
    m = meta[c]; f_ = fa.get(c,0)*m["cells"]
    print(f"  {c:28s} pop {m['occ']:7,d} ({100*m['occ']/tot_pop:4.1f}%)"
          f"  floor {f_:10,.0f} m2 ({100*f_/tf:4.1f}%)"
          f"  {f_/max(m['occ'],1):5.1f} m2/cap"
          f"  energy {100*sum(ann[c].values())/grand:4.1f}% of district")
