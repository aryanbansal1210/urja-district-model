"""Block C of the physical parameter audit: climate + seasonal
factors. READ ONLY - measures, changes nothing.

Bounds the candidate findings against real district energy so each one can
be triaged. Mirrors `demand_by_slice_kw` (energy/network.py ~540-670) but
keeps base / cooling / heating / EV separate, and re-computes the
microclimate multiplier term-by-term so each reduction can be priced.
"""
from __future__ import annotations
import math
import os
import sys
from collections import defaultdict

ROOT = r"C:\Users\aryan\OneDrive - Imperial College London\PROJECT\SESSIONS\district_v3"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from core.grid import LandUse                      # noqa: E402
from energy.costs import load_economics            # noqa: E402
from energy.network import load_optimised_network  # noqa: E402

econ = load_economics()
net = load_optimised_network()
S = econ.slices
GWH = 1e6
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]
DIM = {"jan": 31, "feb": 28, "mar": 31, "apr": 30, "may": 31, "jun": 30,
       "jul": 31, "aug": 31, "sep": 30, "oct": 31, "nov": 30, "dec": 31}

CLIM = econ.climate or {}
cool_by_m = econ.cooling_factors.get("cooling_factor_by_month", {})
cdp = econ.cooling_factors.get("cooling_daypart_shape", {})
cdpm = econ.cooling_factors.get("cooling_daypart_shape_monsoon", {})
mons = set(econ.cooling_factors.get("monsoon_months", []))
hdp = econ.heating_loads.get("heating_daypart_shape", {})


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


# ---------------------------------------------------------------------------
# 0. Denominators: annual energy by component, and by (component, month).
# ---------------------------------------------------------------------------
comp = defaultdict(float)                       # component -> kWh
by_m = defaultdict(lambda: defaultdict(float))  # component -> month -> kWh
peak_slice = defaultdict(float)                 # slice_id -> kW (district)
slice_month = {}
cool_peak_kw_tot = 0.0

for n in net.nodes:
    c = n.category_name
    if not c:
        continue
    bp = econ.base_demand_profile.get(c)
    if bp is None:
        continue
    cool_peak_kw_tot += n.peak_cooling_kw
    for s in S:
        h = s.hours_per_year
        slice_month[s.id] = s.month
        wd = float(bp["weekday"][s.daypart])
        we = float(bp["weekend"][s.daypart])
        ft = float(bp["festival"][s.daypart])
        bm = (s.weekday_share * wd + s.weekend_share * we + s.festival_share * ft)
        bm *= econ.behavioural_demand_multiplier(c, s, faith=n.faith)
        occm = econ.occupancy_monthly_modifier(c, s.month)
        dp = float((cdpm if (s.month in mons and cdpm) else cdp).get(s.daypart, 0.0))
        cf = float(cool_by_m.get(s.month, 0.0)) * dp
        b_kw = n.peak_base_kw * bm * occm
        c_kw = (n.peak_cooling_kw * cf * n.microclimate_cooling_multiplier
                * econ._cooling_effectiveness(c, s.month)
                * econ.heat_wave_cooling_multiplier(s.month) * occm)
        h_kw = n.peak_heating_kw * (econ.heating_factor_for_month(s.month)
                                    * float(hdp.get(s.daypart, 0.0)))
        e_kw = n.peak_base_kw * econ.ev_demand_multiplier(c, s.id, None)
        comp["base"] += b_kw * h
        comp["cool"] += c_kw * h
        comp["heat"] += h_kw * h
        comp["ev"] += e_kw * h
        by_m["base"][s.month] += b_kw * h
        by_m["cool"][s.month] += c_kw * h
        by_m["heat"][s.month] += h_kw * h
        by_m["ev"][s.month] += e_kw * h
        peak_slice[s.id] += b_kw + c_kw + h_kw + e_kw

TOT = sum(comp.values())
hdr("0. DENOMINATORS (read-only replica, no streetlight district term)")
for k in ("base", "cool", "heat", "ev"):
    print(f"  {k:5s} {comp[k]/GWH:9.2f} GWh  ({100*comp[k]/TOT:5.2f}%)")
print(f"  TOTAL {TOT/GWH:9.2f} GWh")
pk_id = max(peak_slice, key=peak_slice.get)
print(f"  district peak slice {pk_id} = {peak_slice[pk_id]/1000:.1f} MW")


# ---------------------------------------------------------------------------
# 1. HEATING MONTH FACTOR - HDD proxy on t_min, base 18. The third leg of
#    the HEAT-1 / / triangle.
# ---------------------------------------------------------------------------
hdr("1. heating_factor_for_month: HDD(base 18, t_min) - shape interrogation")


def norm(d):
    mx = max(d.values())
    return {m: (v / mx if mx > 0 else 0.0) for m, v in d.items()}


cur = {m: econ.heating_factor_for_month(m) for m in MONTHS}
tmin = {m: float(CLIM[m]["t_min_c"]) for m in MONTHS}
tmean = {m: float(CLIM[m]["t_mean_c"]) for m in MONTHS}
tmax = {m: float(CLIM[m]["t_max_c"]) for m in MONTHS}

hdd_mean18 = norm({m: max(0.0, 18.0 - tmean[m]) for m in MONTHS})
hdd_min15 = norm({m: max(0.0, 15.0 - tmin[m]) for m in MONTHS})
# DHW physics: energy to lift mains water to a 45 C set point.
# Inlet water tracks ambient; energy ~ (T_set - T_inlet).
dhw = norm({m: max(0.0, 45.0 - tmean[m]) for m in MONTHS})

print(f"  {'':22s}" + "".join(f"{m:>6s}" for m in MONTHS) + "   SUM")
for name, tbl in (("CURRENT HDD(18,t_min)", cur),
                  ("HDD(18,t_mean) std", hdd_mean18),
                  ("HDD(15,t_min) heater", hdd_min15),
                  ("DHW (45C - t_mean)", dhw)):
    print(f"  {name:22s}" + "".join(f"{tbl[m]:6.2f}" for m in MONTHS)
          + f"  {sum(tbl.values()):5.2f}")
print("\n  Weighted by days-in-month (what actually drives annual energy):")
for name, tbl in (("CURRENT", cur), ("HDD(18,t_mean)", hdd_mean18),
                  ("HDD(15,t_min)", hdd_min15), ("DHW", dhw)):
    w = sum(tbl[m] * DIM[m] for m in MONTHS)
    print(f"    {name:16s} {w:7.1f} degree-day-equivalents"
          f"   ratio vs current {w/sum(cur[m]*DIM[m] for m in MONTHS):5.2f}x")

zero_months = [m for m in MONTHS if cur[m] == 0.0]
heat_ann = comp["heat"]
print(f"\n  Heating annual = {heat_ann/GWH:.2f} GWh ({100*heat_ann/TOT:.2f}% of district)")
print(f"  EXACTLY ZERO in {len(zero_months)} months: {', '.join(zero_months)}")
print("  -> residential + hotel + healthcare hot water is exactly 0 kWh for"
      f" {len(zero_months)} months/yr.")
gy_share = 1.5 / (1.5 + 2.0)   # config's own '1.5 kW geyser + 2 kW heater'
dhw_energy_now = heat_ann * gy_share
w_cur = sum(cur[m] * DIM[m] for m in MONTHS)
w_dhw = sum(dhw[m] * DIM[m] for m in MONTHS)
dhw_energy_phys = dhw_energy_now * (w_dhw / w_cur)
print(f"  Config's own split: geyser = {gy_share:.0%} of the heating peak"
      f" -> {dhw_energy_now/GWH:.2f} GWh DHW today")
print(f"  Same peak on a (45C - t_mean) DHW season = {dhw_energy_phys/GWH:.2f} GWh"
      f"  ({(dhw_energy_phys-dhw_energy_now)/GWH:+.2f} GWh,"
      f" {100*(dhw_energy_phys-dhw_energy_now)/TOT:+.2f}% of district)")
heater_now = heat_ann * (1 - gy_share)
w_h15 = sum(hdd_min15[m] * DIM[m] for m in MONTHS)
heater_phys = heater_now * (w_h15 / w_cur)
print(f"  Space heater {1-gy_share:.0%} on HDD(15,t_min) = {heater_phys/GWH:.2f} GWh"
      f"  ({(heater_phys-heater_now)/GWH:+.2f} GWh,"
      f" {100*(heater_phys-heater_now)/TOT:+.2f}%)")
net_delta = (dhw_energy_phys + heater_phys) - heat_ann
print(f"  NET if both legs were split out: {net_delta/GWH:+.2f} GWh"
      f"  ({100*net_delta/TOT:+.2f}% of district)")


# ---------------------------------------------------------------------------
# 2. COOLING MONTH FACTOR - hand-typed, uncited, no CDD derivation.
# ---------------------------------------------------------------------------
hdr("2. cooling_factor_by_month: hand-typed vs a CDD proxy")
cur_c = {m: float(cool_by_m.get(m, 0.0)) for m in MONTHS}
print(f"  {'':22s}" + "".join(f"{m:>6s}" for m in MONTHS) + "   SUM")
print(f"  {'CURRENT (hand-typed)':22s}"
      + "".join(f"{cur_c[m]:6.2f}" for m in MONTHS)
      + f"  {sum(cur_c.values()):5.2f}")
cdd_tables = {}
for base in (22.0, 24.0, 26.0):
    t = norm({m: max(0.0, tmean[m] - base) for m in MONTHS})
    cdd_tables[base] = t
    print(f"  CDD({base:.0f}C, t_mean)      "
          + "".join(f"{t[m]:6.2f}" for m in MONTHS)
          + f"  {sum(t.values()):5.2f}")
# Simple CDD on t_max too - what people actually respond to.
t = norm({m: max(0.0, tmax[m] - 30.0) for m in MONTHS})
cdd_tables["tmax30"] = t
print(f"  {'CDD(30C, t_max)':22s}" + "".join(f"{t[m]:6.2f}" for m in MONTHS)
      + f"  {sum(t.values()):5.2f}")

print("\n  Annual cooling energy if the month table were CDD-derived"
      " (same daypart shape, same peaks):")
cool_m = by_m["cool"]
for label, tbl in (("CDD(22,t_mean)", cdd_tables[22.0]),
                   ("CDD(24,t_mean)", cdd_tables[24.0]),
                   ("CDD(26,t_mean)", cdd_tables[26.0]),
                   ("CDD(30,t_max)", cdd_tables["tmax30"])):
    scaled = sum(cool_m[m] * (tbl[m] / cur_c[m]) if cur_c[m] > 0 else 0.0
                 for m in MONTHS)
    # months where current is 0 but CDD is not: add at the cooling peak rate
    extra = 0.0
    for m in MONTHS:
        if cur_c[m] == 0.0 and tbl[m] > 0:
            ref = max((cool_m[x] / cur_c[x] for x in MONTHS if cur_c[x] > 0),
                      default=0.0)
            extra += ref * tbl[m] * (DIM[m] / 31.0)
    d = scaled + extra - comp["cool"]
    print(f"    {label:16s} {(scaled+extra)/GWH:8.2f} GWh"
          f"  ({d/GWH:+7.2f} GWh, {100*d/TOT:+5.2f}% of district)")
print(f"\n  jan and dec cooling factor are EXACTLY 0.00 -> "
      f"{by_m['cool']['jan']+by_m['cool']['dec']:.0f} kWh of cooling in"
      " Jan+Dec across all 14 categories, including warehouse_cold_storage.")


# ---------------------------------------------------------------------------
# 3. HEAT-WAVE MULTIPLIER - threshold applied to a MONTHLY MEAN of daily
#    maxima (Jensen's inequality).
# ---------------------------------------------------------------------------
hdr("3. heat_wave_cooling_multiplier: threshold on a monthly-mean t_max")


def hw_of(t):
    if t <= 35.0:
        return 1.0
    if t > 40.0:
        return 1.20
    return 1.0 + (t - 35.0) * 0.04


def hw_expected(mu, sigma, n=4001):
    """E[f(Tmax)] with Tmax ~ N(mu, sigma), f the config's own piecewise rule."""
    lo, hi = mu - 5 * sigma, mu + 5 * sigma
    step = (hi - lo) / (n - 1)
    num = den = 0.0
    for i in range(n):
        x = lo + i * step
        w = math.exp(-0.5 * ((x - mu) / sigma) ** 2)
        num += w * hw_of(x)
        den += w
    return num / den


SIGMA = 3.0   # IMD daily-max std dev, Punjab plains, pre-monsoon
print(f"  Daily-max spread assumed N(mean, sigma={SIGMA} C)")
print(f"  {'month':6s} {'t_max':>6s} {'current':>8s} {'E[f(T)]':>8s}"
      f" {'delta':>7s} {'P(T>35)':>8s} {'P(T>40)':>8s}  {'cool GWh':>9s} {'GWh delta':>9s}")
hw_tot = 0.0
for m in MONTHS:
    mu = tmax[m]
    cur_hw = hw_of(mu)
    exp_hw = hw_expected(mu, SIGMA)
    p35 = 0.5 * math.erfc((35.0 - mu) / (SIGMA * math.sqrt(2)))
    p40 = 0.5 * math.erfc((40.0 - mu) / (SIGMA * math.sqrt(2)))
    g = cool_m[m]
    d = g * (exp_hw / cur_hw - 1.0) if cur_hw > 0 else 0.0
    hw_tot += d
    print(f"  {m:6s} {mu:6.1f} {cur_hw:8.3f} {exp_hw:8.3f} {exp_hw-cur_hw:+7.3f}"
          f" {p35:8.2f} {p40:8.2f}  {g/GWH:9.2f} {d/GWH:+9.3f}")
print(f"  TOTAL cooling delta {hw_tot/GWH:+.2f} GWh"
      f"  ({100*hw_tot/TOT:+.2f}% of district,"
      f" {100*hw_tot/comp['cool']:+.2f}% of cooling)")


# ---------------------------------------------------------------------------
# 4. MICROCLIMATE - decompose the multiplier, price each term.
# ---------------------------------------------------------------------------
hdr("4. microclimate_cooling_multiplier: term-by-term decomposition")
mc = econ.microclimate or {}
veg_per = float(mc.get("vegetation_cooling_reduction_per_neighbour_fraction", 0.05))
blue_red = float(mc.get("blue_space_proximity_reduction", 0.05))
party_max = float(mc.get("party_wall_max_reduction", 0.06))
tree_per = float(mc.get("street_tree_cooling_reduction_per_treed_road_neighbour_fraction", 0.0))
tree_max = float(mc.get("street_tree_cooling_max", 0.12))
grid = net.grid

terms = defaultdict(float)     # term -> cooling-peak-kW * reduction
tot_cool_kw = 0.0
mult_hist = defaultdict(int)
n_floor = 0
for n in net.nodes:
    if not n.category_name or n.peak_cooling_kw <= 0:
        continue
    row, col = n.cell_id
    cell = grid.at(row, col)
    nbrs = grid.neighbours_4(row, col)
    green = sum(1 for b in nbrs
                if b.land_use in {LandUse.OPEN_SPACE, LandUse.BLUE_SPACE})
    veg = green * veg_per
    blue = blue_red if any(b.land_use == LandUse.BLUE_SPACE for b in nbrs) else 0.0
    treed = sum(1 for b in nbrs
                if b.land_use == LandUse.ROAD and getattr(b, "has_street_trees", False))
    tree = min(tree_max, treed * tree_per)
    my_h = float(cell.height_m)
    if my_h > 0:
        share = sum(min(my_h, float(b.height_m)) / (4.0 * my_h)
                    for b in nbrs if b.has_building and float(b.height_m) > 0)
        party = min(party_max, share * party_max)
    else:
        party = 0.0
    kw = n.peak_cooling_kw
    tot_cool_kw += kw
    terms["vegetation"] += kw * veg
    terms["blue_space"] += kw * blue
    terms["street_trees"] += kw * tree
    terms["party_wall"] += kw * party
    total_red = veg + blue + party + tree
    if 1.0 - total_red < 0.60:
        n_floor += 1
    mult_hist[round(max(0.60, 1.0 - total_red), 2)] += 1

print(f"  cooling-peak-weighted mean reduction by term"
      f"  (total cooling peak {tot_cool_kw/1000:.1f} MW):")
for k in ("street_trees", "vegetation", "party_wall", "blue_space"):
    frac = terms[k] / tot_cool_kw
    print(f"    {k:14s} -{100*frac:5.2f}%   = {frac*comp['cool']/GWH:6.2f} GWh/yr"
          f"  ({100*frac*comp['cool']/TOT:5.2f}% of district)")
allred = sum(terms.values()) / tot_cool_kw
print(f"    {'TOTAL':14s} -{100*allred:5.2f}%   = {allred*comp['cool']/GWH:6.2f} GWh/yr"
      f"  ({100*allred*comp['cool']/TOT:5.2f}% of district)")
print(f"  cells hitting the 0.60 floor: {n_floor}")
print("  multiplier distribution:",
      "  ".join(f"{k:.2f}:{v}" for k, v in sorted(mult_hist.items())))
print("\n  config economics.yaml:2994 says street trees are 'NOT YET READ BY CODE'"
      " - network.py:1158-1162 reads them.")
print("  vegetation_max_reduction (0.12) and wind_alignment_reduction_max (0.08)"
      " are in the YAML and read by nothing.")


# ---------------------------------------------------------------------------
# 5. CLIMATE-DRIFT WARMING - flat district multiplier vs a cooling-only one.
# ---------------------------------------------------------------------------
hdr("5. climate_drift_cooling: flat demand multiplier vs cooling-shaped")
dt55 = econ.climate_drift_delta_t_c(2055)
m30 = econ.lifetime_demand_multiplier(2030) if hasattr(econ, "lifetime_demand_multiplier") else None
print(f"  climate_drift_delta_t_c(2055) = {dt55:.2f} C")
print("  config lifetime_avg_multiplier = 1.015 -> 2055 endpoint 1.030 (flat, all slices)")
cool_share = comp["cool"] / TOT
print(f"  config cooling_share_of_demand = 0.25 (DEAD FIELD, never read)")
print(f"  model's ACTUAL cooling share  = {cool_share:.3f}")
print(f"  config cooling_elasticity_per_c = 0.10 (DEAD FIELD, never read)")
implied = 0.10 * dt55 * cool_share
print(f"  its own method: 0.10/C x {dt55:.1f} C x {cool_share:.3f} ="
      f" +{100*implied:.2f}% district at 2055  vs the coded +3.00%"
      f"  ({implied/0.03:.2f}x)")
# peak effect
flat_peak = peak_slice[pk_id] * 1.03
cool_only_uplift = 1.0 + 0.03 * TOT / comp["cool"]
print(f"\n  If the same +3% district energy were placed on COOLING ONLY,"
      f" cooling x{cool_only_uplift:.3f}")
# recompute peak under the two treatments
pk_cool = defaultdict(float)
pk_all = defaultdict(float)
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
        occm = econ.occupancy_monthly_modifier(c, s.month)
        dp = float((cdpm if (s.month in mons and cdpm) else cdp).get(s.daypart, 0.0))
        cf = float(cool_by_m.get(s.month, 0.0)) * dp
        ck = (n.peak_cooling_kw * cf * n.microclimate_cooling_multiplier
              * econ._cooling_effectiveness(c, s.month)
              * econ.heat_wave_cooling_multiplier(s.month) * occm)
        pk_cool[s.id] += ck
        pk_all[s.id] += (n.peak_base_kw*bm*occm + ck
                         + n.peak_heating_kw*(econ.heating_factor_for_month(s.month)
                                              * float(hdp.get(s.daypart, 0.0)))
                         + n.peak_base_kw*econ.ev_demand_multiplier(c, s.id, None))
flat = {k: v * 1.03 for k, v in pk_all.items()}
shaped = {k: pk_all[k] + pk_cool[k] * (cool_only_uplift - 1.0) for k in pk_all}
fp = max(flat.values()); sp = max(shaped.values())
print(f"  2055 district peak  flat +3%   = {fp/1000:8.1f} MW")
print(f"  2055 district peak  cooling-shaped = {sp/1000:8.1f} MW"
      f"   ({100*(sp-fp)/fp:+.2f}% vs flat, {(sp-fp)/1000:+.1f} MW)")
jan_flat = sum(v for k, v in flat.items() if slice_month[k] == "jan")
jan_shp = sum(v for k, v in shaped.items() if slice_month[k] == "jan")
print(f"  January demand:     flat +3.00%   vs cooling-shaped"
      f" {100*(jan_shp/jan_flat*1.03-1):+.2f}%"
      "   (warming should CUT January, not raise it)")


# ---------------------------------------------------------------------------
# 6. PV-side climate: the duplicate ambient table + soiling.
# ---------------------------------------------------------------------------
hdr("6. PV climate coupling: two temperature tables, one of them dead")
inv = econ.pv_inverter or {}
amb = inv.get("ambient_temperature_c_by_month", {})
coef = float(inv.get("temperature_derating_per_celsius", 0.0))
noct = float(inv.get("noct_temperature_uplift_c", 25.0))


def derate(a):
    d = a + noct - 25.0
    return 1.0 if d <= 0 else max(0.0, 1.0 - coef * d)


print(f"  {'month':6s} {'clim t_mean':>11s} {'pv ambient':>11s} {'diff':>6s}"
      f" {'derate(pv)':>11s} {'derate(clim)':>13s} {'soiling':>8s} {'pv wt':>7s}")
num_pv = den_pv = 0.0
wsum = 0.0
for m in MONTHS:
    a = float(amb.get(m, 25.0))
    w = float(econ.pv_monthly_modifier.get(m, 1.0)) * DIM[m]
    wsum += w
    num_pv += w * derate(a)
    den_pv += w * derate(tmean[m])
    print(f"  {m:6s} {tmean[m]:11.1f} {a:11.1f} {a-tmean[m]:+6.1f}"
          f" {derate(a):11.4f} {derate(tmean[m]):13.4f}"
          f" {econ.pv_soiling_multiplier_for_month(m):8.4f} {w/wsum if wsum else 0:7.3f}")
print(f"\n  PV-weighted derate using pv_inverter table  = {num_pv/wsum:.4f}")
print(f"  PV-weighted derate using climate.t_mean_c   = {den_pv/wsum:.4f}"
      f"   ({100*(den_pv-num_pv)/num_pv:+.2f}% yield)")
print("  climate.yaml header claims t_mean_c drives 'PV temperature derating'."
      " Python reads of t_mean_c: 0.")
sm = [econ.pv_soiling_multiplier_for_month(m) for m in MONTHS]
print(f"  soiling multiplier range {min(sm):.3f} - {max(sm):.3f};"
      f" PV-weighted mean "
      f"{sum(econ.pv_soiling_multiplier_for_month(m)*float(econ.pv_monthly_modifier.get(m,1.0))*DIM[m] for m in MONTHS)/wsum:.4f}")
print(f"  pv_fog_multiplier (retired 2026-07-06):"
      f" {set(round(econ.pv_fog_multiplier_for_month(m),4) for m in MONTHS)}")


# ---------------------------------------------------------------------------
# 7. Field-level provenance sweep of climate.yaml.
# ---------------------------------------------------------------------------
hdr("7. climate.yaml field usage (Python reads outside tests)")
print("""  t_mean_c                 0  DEAD - header claims it drives PV derating
  t_max_c                  1  heat_wave_cooling_multiplier
  t_min_c                  3  heating HDD proxy
  rh14_pct                 2  desert-cooler effectiveness curve
  rainfall_mm              0  DEAD (rain_days is what soiling uses)
  rain_days                5  PV soiling rain recovery
  cloud_cover_pct          0  DEAD - honestly labelled 'future Stage F'
  diffuse_fraction_pct     0  DEAD - honestly labelled 'future Stage F'
  wind10m_ms               0  DEAD - header claims 'microclimate B2'
  wind_direction_dominant  0  DEAD - header claims 'microclimate B2'
  pm25_ugm3                4  PV soiling
  dust_storm_days          4  PV soiling
  fog_days_observed_unused 0  deliberately retired 2026-07-06, documented""")
