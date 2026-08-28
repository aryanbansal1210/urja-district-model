"""Block F of the physical parameter audit: costs, tariffs and
financial parameters. READ ONLY - measures, changes nothing.

The central question: the five import-tariff bands price 100% of BAU's cost
and most of the designed town's. Are they cited, do they reconcile to a real
PSPCL tariff, and is their SPREAD consistent with the regulation that governs
time-of-day pricing in India?
"""
from __future__ import annotations
import json
import os
import sys
from collections import defaultdict

ROOT = r"C:\Users\aryan\OneDrive - Imperial College London\PROJECT\SESSIONS\district_v3"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import yaml as _y                                 # noqa: E402
from energy.costs import load_economics           # noqa: E402
from energy.network import load_optimised_network # noqa: E402

econ = load_economics()
net = load_optimised_network()
S = econ.slices
GWH = 1e6
CR = 1e7   # 1 crore


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


RAW = _y.safe_load(open("config/economics.yaml", encoding="utf-8")) or {}
G = RAW.get("grid", {}) or {}
BANDS = G.get("import_tariff_inr_per_kwh", {}) or {}

# ---------------------------------------------------------------------------
# 1. The five bands: level, spread, and provenance
# ---------------------------------------------------------------------------
hdr("1. import_tariff_inr_per_kwh - level, spread, provenance")
#: the invented `super_off_peak` 02-04 sub-band was
# DELETED and the MoP rule 8A `solar` 08-16 band added, so 02-04 rejoined the
# night and the old 06-18 shoulder split into 06-08 + 16-18. This script still
# described the pre- world and crashed on BANDS.get("super_off_peak")
# returning None. Hours still sum to 24: 8 + 8 + 4 + 2 + 2.
HOURS = {"solar": 8, "off_peak": 8, "shoulder": 4,
         "peak": 2, "super_peak": 2}
print(f"  {'band':16s} {'Rs/kWh':>8s} {'hours/day':>10s} {'window':>22s}")
wins = {"solar": "08-16", "off_peak": "00-06,22-24",
        "shoulder": "06-08,16-18", "peak": "18-20", "super_peak": "20-22"}
for b in ("solar", "off_peak", "shoulder", "peak", "super_peak"):
    print(f"  {b:16s} {BANDS[b]:8.2f} {HOURS[b]:10d} {wins[b]:>22s}")
assert sum(HOURS.values()) == 24, HOURS
flat = sum(BANDS[b]*HOURS[b] for b in HOURS) / 24.0
print(f"\n  hours-weighted average (no seasonal_tod) = Rs {flat:.3f}/kWh")
st = RAW.get("seasonal_tod", {}) or {}
ov = st.get("overrides_by_month", {}) or {}
n_shoulder_months = sum(1 for m, d in ov.items()
                        if d.get("18_20") == "shoulder")
h2 = dict(HOURS)
h2["shoulder"] += 4; h2["peak"] -= 2; h2["super_peak"] -= 2
flat_off = sum(BANDS[b]*h2[b] for b in h2) / 24.0
print(f"  seasonal_tod moves 18-22 to shoulder for {n_shoulder_months} months"
      f" -> those months average Rs {flat_off:.3f}/kWh")
blend = (flat_off*n_shoulder_months + flat*(12-n_shoulder_months))/12.0
print(f"  12-month blended average                 = Rs {blend:.3f}/kWh")
print(f"\n  PSPCL domestic first-slab FY26-27 = Rs 5.40/kWh"
      "  (the config's OWN B2 note, economics.yaml:565)")
print(f"  -> the LEVEL reconciles ({blend:.2f} vs 5.40). That reconciliation"
      " is written NOWHERE.")
spread = BANDS["super_peak"] / BANDS["solar"]
sp2 = BANDS["peak"] / BANDS["shoulder"]
sol = BANDS["solar"] / flat
print(f"\n  SPREAD super_peak / solar          = {spread:.2f}x")
print(f"  peak / shoulder                    = {sp2:.2f}x")
print(f"  solar band (08-16) / daily average = {sol:.3f}x")
print("""
  MoP Electricity (Rights of Consumers) Amendment Rules 2023, 14.06.2023 (Tier 1):
    solar hours   <= 0.80 x normal   (at least 20% LESS)
    peak hours    >= 1.20 x normal   (C&I)
    peak hours    >= 1.10 x normal   (other consumers, incl. domestic)
  -> mandated minimum spread 1.50x (C&I) / 1.375x (domestic).
  -> the model runs 2.71x, and prices the SOLAR HOURS at 1.02x the daily
     average when the rule requires <= 0.80x.""")

# ---------------------------------------------------------------------------
# 2. What the solar-hours mispricing is worth
# ---------------------------------------------------------------------------
hdr("2. the solar-hours band: what self-consumed PV is credited at")
d = json.load(open("outputs/data/energy/dispatch_results.json", encoding="utf-8"))
fs = [x for x in d["scenarios"]
      if x.get("name") == "full_stack" and abs(x.get("alpha", 1)) < 1e-9][0]
bau = [x for x in d["scenarios"] if x.get("name") == "bau"][0]

SOLAR_DP = {"06_08", "08_10", "10_12", "12_14", "14_16", "16_18"}
pv_tot = exp_tot = 0.0
pv_solar = 0.0
imp_by_band = defaultdict(float)
for sid, v in fs["by_slice"].items():
    s = econ.slice_by_id(sid)
    pv = v.get("pv_kwh", 0.0) or 0.0
    ex = v.get("grid_export_kwh", 0.0) or 0.0
    pv_tot += pv
    exp_tot += ex
    if s.daypart in SOLAR_DP:
        pv_solar += pv
selfcon = pv_tot - exp_tot
print(f"  full_stack PV generation      {pv_tot/GWH:8.1f} GWh")
print(f"  of which exported             {exp_tot/GWH:8.1f} GWh")
print(f"  self-consumed on site         {selfcon/GWH:8.1f} GWh"
      f"  ({100*selfcon/pv_tot:.1f}%)")
print(f"  PV falling in the 06-18 solar window {100*pv_solar/pv_tot:.1f}%")
sh = BANDS["shoulder"]
for target in (0.80, 0.90):
    newp = flat * target
    delta = selfcon * (sh - newp)
    print(f"  self-consumed PV valued at Rs {sh:.2f} today;"
          f" at {target:.2f}x average = Rs {newp:.2f}"
          f"  -> avoided-cost falls Rs {delta/CR:,.1f} cr/yr")
print(f"\n  BAU annual cost {bau.get('annual_cost_inr', 0)/CR:,.1f} cr,"
      f" full_stack {fs.get('annual_cost_inr', 0)/CR:,.1f} cr")

# ---------------------------------------------------------------------------
# 3. How much of the answer rests on the ToU spread at all
# ---------------------------------------------------------------------------
hdr("3. arbitrage exposure: energy that only has value because of the spread")
keys = ("battery_discharge_kwh", "v2g_discharge_kwh", "dsr_reduce_kwh",
        "ev_shift_out_kwh")
tot = defaultdict(float)
for sid, v in fs["by_slice"].items():
    for k in keys:
        tot[k] += v.get(k, 0.0) or 0.0
print(f"  {'flexibility channel':24s} {'GWh/yr':>9s}"
      f" {'value at 2.71x spread':>22s} {'at 1.50x':>10s}")
band_hi = BANDS["super_peak"]; band_lo = BANDS["solar"]
sp_now = band_hi - band_lo                       # Rs/kWh headroom today
sp_mop = flat*1.20 - flat*0.80                   # C&I-compliant headroom
grand_now = grand_mop = 0.0
for k in keys:
    e = tot[k]
    grand_now += e*sp_now
    grand_mop += e*sp_mop
    print(f"  {k:24s} {e/GWH:9.3f} {e*sp_now/CR:20,.1f} cr"
          f" {e*sp_mop/CR:8,.1f} cr")
print(f"  {'TOTAL':24s} {sum(tot.values())/GWH:9.3f} {grand_now/CR:20,.1f} cr"
      f" {grand_mop/CR:8,.1f} cr")
print(f"  compressing the spread to the MoP C&I minimum removes"
      f" Rs {(grand_now-grand_mop)/CR:,.1f} cr/yr of headroom"
      f" ({100*(1-sp_mop/sp_now):.0f}% of it)")
print("  (upper bound on the arbitrage: real dispatch does not move every kWh"
      " from the cheapest\n   to the dearest band, but it bounds the exposure.)")

# ---------------------------------------------------------------------------
# 4. Financial parameters: real vs nominal discipline
# ---------------------------------------------------------------------------
hdr("4. discount rates, inflation, escalation - is the real/nominal split clean?")
dr = RAW.get("discount_rates", {}) or {}
for k, v in dr.items():
    print(f"  {k:22s} {v}")
print(f"  legacy flat discount_rate        {RAW.get('discount_rate')}")
print(f"  inflation_assumption_annual      {RAW.get('inflation_assumption_annual')}")
print(f"  tariff_escalation_real_annual    {RAW.get('tariff_escalation_real_annual')}")
print(f"  end_of_life_cost_fraction        {RAW.get('end_of_life_cost_fraction')}")
w = RAW.get("rooftop_owner_weights", {}) or {}
acts = RAW.get("rooftop_owner_actors", {}) or {}
blend_r = sum(float(w[k])*float(dr[acts[k]]) for k in w)
print(f"\n  rooftop blended discount rate = {blend_r:.4f}"
      f"  (weights sum {sum(w.values()):.4f})")
print(f"  legacy flat rate {RAW.get('discount_rate')} vs blended {blend_r:.4f}"
      f"  ({100*(RAW.get('discount_rate')/blend_r-1):+.1f}%)")

# ---------------------------------------------------------------------------
# 5. Carbon price + the objective
# ---------------------------------------------------------------------------
hdr("5. carbon price by period")
mp = RAW.get("multi_period", {}) or {}
cp = mp.get("price_inr_per_kgco2_by_period") or {}
print(f"  price_inr_per_kgco2_by_period: {cp}")
for y, v in (cp or {}).items():
    print(f"    {y}: Rs {v}/kgCO2 = Rs {float(v)*1000:,.0f}/tCO2"
          f" = ~USD {float(v)*1000/85:,.0f}/tCO2 at Rs 85/USD")
co = RAW.get("carbon_objective", {}) or {}
print(f"  carbon_objective keys: {list(co)[:8]}")

# ---------------------------------------------------------------------------
# 6. Field-usage sweep
# ---------------------------------------------------------------------------
hdr("6. block F field usage")
import subprocess
for f in ("inflation_assumption_annual", "discount_rate", "duty_fraction",
          "network_charge_inr_per_kwh", "cross_subsidy_inr_per_kwh",
          "retail_cap_inr_per_kwh", "level_calibration_multiplier",
          "end_of_life_cost_fraction", "industrial_cross_subsidy_inr_per_kwh"):
    r = subprocess.run(["grep", "-rl", f, "energy", "core", "layout", "scripts"],
                       capture_output=True, text=True)
    hits = [x for x in r.stdout.split() if "param_audit" not in x]
    print(f"  {f:38s} {len(hits):2d} file(s)  {', '.join(hits[:3])}")
