"""HEAT-1 cluster + + + + - sizing the options.

READ ONLY. Measures the current heating load and prices every candidate for
the four dials that have to move together:

  peak      how many watts of geyser + heater a household actually owns
  split     how those watts divide between water heating and space heating
  season    the per-month factor, one for each of the two loads
  daypart   the within-day shape, one for each of the two loads

The point of doing all four at once is that they push in opposite directions:
 takes energy OUT of the night, puts energy IN via the peak, and
 puts energy in for water heating and takes it out for space heating.
Any one of them alone moves the answer the wrong way.
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


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


hl = econ.heating_loads or {}
peak_w = hl.get("per_category_peak_w_per_m2", {}) or {}
dp_shape = hl.get("heating_daypart_shape", {}) or {}

# hours per day per daypart, from the slice table
hpd = defaultdict(float)
for s in S:
    hpd[s.daypart] += s.hours_per_year
for k in hpd:
    hpd[k] /= 365.0
# days per month per day-type, so a month factor can be energy-weighted
days_by_month = defaultdict(float)
for s in S:
    days_by_month[s.month] += s.hours_per_year
for m in days_by_month:
    days_by_month[m] /= 24.0

# ---------------------------------------------------------------------------
hdr("1. what the heating load is today")

cur_by_cat = defaultdict(float)
cur_by_month = defaultdict(float)
cur_by_dp = defaultdict(float)
for n in net.nodes:
    if n.category_name is None or n.peak_heating_kw <= 0:
        continue
    for s in S:
        kwh = (n.peak_heating_kw
               * econ.heating_factor_for_month(s.month)
               * float(dp_shape.get(s.daypart, 0.0))
               * s.hours_per_year)
        cur_by_cat[n.category_name] += kwh
        cur_by_month[s.month] += kwh
        cur_by_dp[s.daypart] += kwh
cur_total = sum(cur_by_cat.values())
district = sum(net.demand_by_slice_kwh(econ).values())
print(f"  district demand      {district / 1e6:9.2f} GWh")
print(f"  heating total        {cur_total / 1e6:9.2f} GWh"
      f"   = {cur_total / district * 100:.2f}% of demand")
res_tot = sum(v for k, v in cur_by_cat.items() if k in RES)
print(f"  of which residential {res_tot / 1e6:9.2f} GWh"
      f"   = {res_tot / cur_total * 100:.1f}% of heating")
for c, v in sorted(cur_by_cat.items(), key=lambda kv: -kv[1]):
    print(f"    {c:<28}{v / 1e6:8.2f} GWh")

night = sum(v for dp, v in cur_by_dp.items()
            if dp in ("00_02", "02_04", "04_06"))
print(f"\n  heating 00:00-06:00  {night / 1e6:9.2f} GWh"
      f"   = {night / cur_total * 100:.1f}% of heating,"
      f" {night / district * 100:.2f}% of district   <- PA-A1's mis-timed block")

# ---------------------------------------------------------------------------
cur_night_share = night / cur_total * 100   # before section 5 reuses `night`

hdr("2. per-household peaks: what the model gives vs what it says it gives")

# the config's own arithmetic, economics.yaml:2547-2549
GEYSER_KW = 1.5
HEATER_KW = 2.0
DHW_F = GEYSER_KW / (GEYSER_KW + HEATER_KW)
print(f"  config's own basis: {GEYSER_KW} kW geyser + {HEATER_KW} kW heater"
      f" per 250 m2 = {(GEYSER_KW + HEATER_KW) / 250 * 1000:.0f} W/m2")
print(f"  DHW share of that basis = {GEYSER_KW / (GEYSER_KW + HEATER_KW):.4f}"
      f"   space share = {HEATER_KW / (GEYSER_KW + HEATER_KW):.4f}\n")

print(f"  {'tier':<8}{'HH':>8}{'m2/HH':>9}{'W/m2':>7}{'kW/HH':>9}"
      f"{'geysers':>9}{'heaters':>9}")
area_per_hh, hh_by_tier, pk_by_tier = {}, {}, {}
for c in RES:
    nodes = [n for n in net.nodes if n.category_name == c]
    hh = sum(n.households for n in nodes)
    pk = sum(n.peak_heating_kw for n in nodes)
    # EnergyNode does not carry floor area; back it out of the peak it was
    # built from (network.py:360, heating_w_per_m2 x area / 1000)
    area = pk * 1000.0 / float(peak_w.get(c, 1.0))
    hh_by_tier[c], area_per_hh[c], pk_by_tier[c] = hh, area / hh, pk
    kw_hh = pk / hh
    dhw_hh = kw_hh * GEYSER_KW / (GEYSER_KW + HEATER_KW)
    sph_hh = kw_hh * HEATER_KW / (GEYSER_KW + HEATER_KW)
    print(f"  {INC[c]:<8}{hh:>8}{area / hh:>9.1f}"
          f"{float(peak_w.get(c, 0)):>7.1f}{kw_hh:>9.3f}"
          f"{dhw_hh / GEYSER_KW:>9.2f}{sph_hh / HEATER_KW:>9.2f}")
print("\n  'geysers'/'heaters' = how many appliances the model's peak implies")
print("  per household, at the config's own 1.5 kW / 2.0 kW ratings.")
print("  PA-B3: the config comment says mid = 'geyser + 2 room heaters'")
print(f"  = {GEYSER_KW + 2 * HEATER_KW} kW, and at 0.5 diversity"
      f" {(GEYSER_KW + 2 * HEATER_KW) * 0.5 * 1000:.0f} W/HH.")

# ---------------------------------------------------------------------------
hdr("3. SEASON candidates - normalised so the peak month = 1.00")

clim = econ.climate or {}
t_min = {m: float(clim.get(m, {}).get("t_min_c", 0.0)) for m in MONTHS}
t_mean = {m: float(clim.get(m, {}).get("t_mean_c", 0.0)) for m in MONTHS}


def normalise(raw):
    mx = max(raw.values())
    return {m: (v / mx if mx > 0 else 0.0) for m, v in raw.items()}


def hdd(base, temps):
    return normalise({m: max(0.0, base - temps[m]) for m in MONTHS})


def dhw(setpoint):
    """DHW energy is proportional to (T_set - T_inlet); inlet proxied by the
    monthly mean air temperature (ISO 9459-2 / ECBC convention)."""
    return normalise({m: max(0.0, setpoint - t_mean[m]) for m in MONTHS})


cands = {
    "CURRENT HDD(18,tmin)": hdd(18.0, t_min),
    "space HDD(18,tmean)": hdd(18.0, t_mean),
    "space HDD(15,tmin)": hdd(15.0, t_min),
    "DHW 45C on tmean": dhw(45.0),
    "DHW 60C on tmean": dhw(60.0),
    "DHW 72C on tmean": dhw(72.0),
}
print(f"  {'candidate':<22}" + "".join(f"{m:>6}" for m in MONTHS) + f"{'wtd':>8}")
for name, tab in cands.items():
    wtd = (sum(tab[m] * days_by_month[m] for m in MONTHS)
           / sum(days_by_month.values()))
    print(f"  {name:<22}" + "".join(f"{tab[m]:>6.2f}" for m in MONTHS)
          + f"{wtd:>8.3f}")
print("\n  'wtd' = day-count-weighted mean of the factor, i.e. how much annual")
print("  energy the season delivers per unit of peak. Ratios of this column")
print("  are exactly the energy ratios between candidates.")

# ---------------------------------------------------------------------------
hdr("4. DAYPART candidates")

# current single shape
cur_dp = {dp: float(dp_shape.get(dp, 0.0)) for dp in sorted(hpd)}
# DHW: bimodal, morning bath peak + evening. Zero overnight - nobody draws
# hot water at 02:00, which is the whole of.
dhw_dp = {"00_02": 0.00, "02_04": 0.00, "04_06": 0.10, "06_08": 1.00,
          "08_10": 0.70, "10_12": 0.25, "12_14": 0.15, "14_16": 0.15,
          "16_18": 0.25, "18_20": 0.60, "20_22": 0.70, "22_24": 0.30}
# space heating: occupied-evening + overnight, morning bump, daytime dip
sph_dp = {"00_02": 0.55, "02_04": 0.55, "04_06": 0.60, "06_08": 0.80,
          "08_10": 0.40, "10_12": 0.15, "12_14": 0.10, "14_16": 0.10,
          "16_18": 0.45, "18_20": 0.90, "20_22": 1.00, "22_24": 0.80}
print(f"  {'daypart':<9}{'CURRENT':>9}{'DHW':>8}{'space':>8}")
for dp in sorted(hpd):
    print(f"  {dp:<9}{cur_dp[dp]:>9.2f}{dhw_dp[dp]:>8.2f}{sph_dp[dp]:>8.2f}")
for nm, tab in (("CURRENT", cur_dp), ("DHW", dhw_dp), ("space", sph_dp)):
    day_kwh = sum(tab[dp] * hpd[dp] for dp in tab)
    night = sum(tab[dp] * hpd[dp] for dp in ("00_02", "02_04", "04_06"))
    print(f"  {nm:<9} kWh per kW of peak per day {day_kwh:6.3f}"
          f"   of which 00-06 {night / day_kwh * 100:5.1f}%")

# ---------------------------------------------------------------------------
hdr("5. THE MATRIX - district heating GWh for each combination")

# ---- option D: peaks from OWNERSHIP, not from nameplate ------------------
# BEE 2024 household survey (Tier 1, 4,321 HH, Punjab in the composite zone):
# 6% of households own a water heater, 97% of those are middle/upper class;
# 46 of 4,321 = 1.06% own a room heater. The national figures are a FLOOR for
# a cold-winter Punjab site, so the tier rates below are uplifted, and the
GEYSER_RATED, GEYSER_DIV = 2.0, 0.75      # 2 kW element x 0.75 -> the
#                                           config's own 1.5 kW, now derived
HEATER_RATED, HEATER_DIV, HEATERS_EACH = 2.0, 0.60, 1.5
OWN_GEYSER = {"low_income_residential": 0.10,
              "mid_income_residential": 0.55,
              "high_income_residential": 0.95}
OWN_HEATER = {"low_income_residential": 0.02,
              "mid_income_residential": 0.15,
              "high_income_residential": 0.50}
dhw_kw_hh = {c: GEYSER_RATED * GEYSER_DIV * OWN_GEYSER[c] for c in RES}
sph_kw_hh = {c: HEATER_RATED * HEATER_DIV * HEATERS_EACH * OWN_HEATER[c]
             for c in RES}

print("  option D per-household build (BEE-anchored ownership):")
print(f"  {'tier':<8}{'own gey':>9}{'own htr':>9}{'DHW kW':>9}{'space kW':>10}"
      f"{'tot kW':>9}{'today':>9}{'DHW %':>8}")
for c in RES:
    tot_hh = dhw_kw_hh[c] + sph_kw_hh[c]
    print(f"  {INC[c]:<8}{OWN_GEYSER[c]:>9.2f}{OWN_HEATER[c]:>9.2f}"
          f"{dhw_kw_hh[c]:>9.3f}{sph_kw_hh[c]:>10.3f}{tot_hh:>9.3f}"
          f"{pk_by_tier[c] / hh_by_tier[c]:>9.3f}"
          f"{dhw_kw_hh[c] / tot_hh * 100:>7.0f}%")
print("  note the DHW share: ownership-weighted it is 61-81%, the INVERSE of")
print("  the config's nameplate-weighted 43%. Geysers are ~6x commoner than")
print("  room heaters, so weighting by rating alone gets the split backwards.\n")

peak_opts = {
    "A keep today's peaks": {c: pk_by_tier[c] for c in RES},
    "B un-derate to 9/14/16 W/m2 (PA-B3 bound, NOW WITHDRAWN)":
        {c: area_per_hh[c] * hh_by_tier[c]
            * {"low_income_residential": 9.0,
               "mid_income_residential": 14.0,
               "high_income_residential": 16.0}[c] / 1000.0 for c in RES},
    "D per household from BEE ownership":
        {c: hh_by_tier[c] * (dhw_kw_hh[c] + sph_kw_hh[c]) for c in RES},
}
# per-tier DHW share: uniform nameplate 43% for A and B, ownership-weighted
# for D
dhw_frac = {
    "A keep today's peaks": {c: DHW_F for c in RES},
    "B un-derate to 9/14/16 W/m2 (PA-B3 bound, NOW WITHDRAWN)":
        {c: DHW_F for c in RES},
    "D per household from BEE ownership":
        {c: dhw_kw_hh[c] / (dhw_kw_hh[c] + sph_kw_hh[c]) for c in RES},
}
season_opts = {
    "current single season": (cands["CURRENT HDD(18,tmin)"],
                              cands["CURRENT HDD(18,tmin)"]),
    "DHW 60C + space HDD(18,tmean)": (cands["DHW 60C on tmean"],
                                      cands["space HDD(18,tmean)"]),
    "DHW 60C + space HDD(15,tmin)": (cands["DHW 60C on tmean"],
                                     cands["space HDD(15,tmin)"]),
    "DHW 45C + space HDD(18,tmean)": (cands["DHW 45C on tmean"],
                                      cands["space HDD(18,tmean)"]),
}
dhw_day = sum(dhw_dp[dp] * hpd[dp] for dp in dhw_dp)
sph_day = sum(sph_dp[dp] * hpd[dp] for dp in sph_dp)

# non-residential heating rides along unchanged in every option
non_res = cur_total - res_tot

print(f"  residential only; non-residential held at {non_res / 1e6:.2f} GWh")
print(f"  today's residential heating = {res_tot / 1e6:.2f} GWh\n")
print(f"  {'peaks':<56}{'season':<32}{'GWh':>8}{'vs now':>9}{'district':>10}")
for pname, pk in peak_opts.items():
    for sname, (ds, ss) in season_opts.items():
        tot = 0.0
        for c in RES:
            p = pk[c]
            f = dhw_frac[pname][c]
            tot += p * f * dhw_day * sum(
                ds[m] * days_by_month[m] for m in MONTHS)
            tot += p * (1 - f) * sph_day * sum(
                ss[m] * days_by_month[m] for m in MONTHS)
        d_new = district - res_tot + tot
        print(f"  {pname:<56}{sname:<32}{tot / 1e6:>8.2f}"
              f"{(tot / res_tot - 1) * 100:>8.1f}%"
              f"{(d_new / district - 1) * 100:>9.2f}%")

hdr("6. what moves the peak hour, not just the energy")
print("  today's heating 00-06 share of its own energy:"
      f" {cur_night_share:.1f}%")
new_night_share = (DHW_F * sum(dhw_dp[dp] * hpd[dp]
                               for dp in ("00_02", "02_04", "04_06"))
                   + (1 - DHW_F) * sum(sph_dp[dp] * hpd[dp]
                                       for dp in ("00_02", "02_04", "04_06")))
new_day = DHW_F * dhw_day + (1 - DHW_F) * sph_day
print(f"  split shapes give             {new_night_share / new_day * 100:.1f}%")
print("  The energy that leaves the night lands on 06-08 and 18-22, which are")
print("  the no-PV, high-tariff hours - so this is not a pure reshuffle and")
print("  it can move battery sizing.")
