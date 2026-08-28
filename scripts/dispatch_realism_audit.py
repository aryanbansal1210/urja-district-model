"""Dispatch realism audit.

Empirical anomaly scan of outputs/data/energy/dispatch_results.json - the method
generalised: eyeball every profile dimension programmatically and flag what looks
unphysical. Read-only; no solve. Run: python scripts/dispatch_realism_audit.py
"""
from __future__ import annotations
import json, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
os.chdir(ROOT)

d = json.load(open("outputs/data/energy/dispatch_results.json", encoding="utf-8"))
slices = d["slices"]
sc = [s for s in d["scenarios"] if s.get("name") == "full_stack" and abs(s.get("alpha", 1)) < 1e-9][0]
bs = sc["by_slice"]
MONTHS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
DTS = ["wd","we","fs"]
ZERO_W = [s["id"] for s in slices if s["hours_per_year"] <= 0]
sl_by_id = {s["id"]: s for s in slices}

def W(sid):  # hours weight
    return sl_by_id[sid]["hours_per_year"]

print("=" * 100)
print("1. SLICE-HOUR ACCOUNTING")
tot_h = sum(s["hours_per_year"] for s in slices)
print(f"   sum(hours_per_year) = {tot_h}  (expect 8760)  {'OK' if abs(tot_h-8760)<1e-6 else '*** ANOMALY ***'}")
by_m = defaultdict(float)
for s in slices: by_m[s["month"]] += s["hours_per_year"]
print("   hours by month:", {m: round(by_m[m]) for m in MONTHS})

print("=" * 100)
print("2. MONTHLY PV SHAPE (kWh/h by month, weekday) - F14 check")
pv_m = {}
for m in MONTHS:
    num = sum(bs[f"{m}_wd_{h:02d}"]["pv_kwh"] for h in range(24))
    hrs = sum(W(f"{m}_wd_{h:02d}") for h in range(24))
    pv_m[m] = num / hrs * 24  # per-day energy
print("   PV kWh/day (wd):", {m: round(pv_m[m]/1000) for m in MONTHS}, "(MWh/day)")
mx = max(pv_m, key=pv_m.get); mn = min(pv_m, key=pv_m.get)
print(f"   max month = {mx}, min month = {mn}")
# (FX-2, tightened FX-2b): checks anchored to the calibration
# sources (economics.yaml pv_capacity_factor, v3 = NASA/CERES satellite
# GTI shape). BOTH independent Tier-1 sources agree October/day runs
# ~10% above June at the 29-deg anchor tilt (NASA 1.098, PVGIS-ERA5
# 1.088 - clearest month + tilt geometry), so the old strict "Jun >= Oct"
# heuristic over-flagged. Flag only beyond the source-derived band:
# oct/jun > 1.15 (DNI proxy gave 1.32) or mar/may > 1.05 (sources ~0.96).
# FX-2b also expects a REAL winter dip now (jan/day ~ 0.60x May peak,
# satellite-observed fog) - jan HIGHER than ~0.75x May = fog-blind
# regression to the ERA5 shape.
oj = pv_m.get("oct", 0) / max(1e-9, pv_m.get("jun", 0))
mm_r = pv_m.get("mar", 0) / max(1e-9, pv_m.get("may", 0))
print(f"   oct/jun PV-per-day ratio = {oj:.3f} (PVGIS-GTI expectation ~1.09; flag > 1.15)")
if oj > 1.15: print("   *** ANOMALY (F14): oct/jun exceeds the PVGIS-GTI band ***")
if mm_r > 1.05: print(f"   *** mar/may = {mm_r:.3f} > 1.05 (DNI-proxy signature; PVGIS says 0.99) ***")

print("=" * 100)
print("3. DEMAND SHAPE: month x daytype daily energy + intraday spikes")
for dt in DTS:
    row = {}
    for m in MONTHS:
        ids = [f"{m}_{dt}_{h:02d}" for h in range(24) if f"{m}_{dt}_{h:02d}" in bs]
        if not ids: continue
        e = sum(bs[i]["demand_kwh"] for i in ids)
        hrs = sum(W(i) for i in ids)
        row[m] = e / hrs * 24 / 1000 if hrs else 0
    print(f"   {dt:>4} MWh/day:", {m: round(v) for m, v in row.items()})
print("   ratio dec/jun (wd, heating check):",
      round(sum(bs[f'dec_wd_{h:02d}']['demand_kwh'] for h in range(24)) /
            max(1, sum(bs[f'jun_wd_{h:02d}']['demand_kwh'] for h in range(24))), 3))

print("=" * 100)
print("4. EFFECTIVE LOAD SPIKES (demand + dsr_add - dsr_reduce + ev_in - ev_out): top-10 hours by ratio to daily mean")
spikes = []
for m in MONTHS:
    for dt in DTS:
        vals = []
        for h in range(24):
            b = bs.get(f"{m}_{dt}_{h:02d}")
            if not b: continue
            w = W(f"{m}_{dt}_{h:02d}")
            if w <= 0: continue
            # REV-2: managed-EV shift moves load like DSR.
            # solar water heating removes electrical load in
            # the same way DSR does; demand_kwh is GROSS.
            eff = (b["demand_kwh"] + b["dsr_add_kwh"] - b["dsr_reduce_kwh"]
                   - b.get("solar_thermal_served_kwh", 0.0)
                   + b.get("ev_shift_in_kwh", 0.0)
                   - b.get("ev_shift_out_kwh", 0.0)) / w
            vals.append((h, eff))
        if not vals: continue
        mean = sum(v for _, v in vals) / len(vals)
        for h, v in vals:
            if mean > 0 and v / mean > 1.8:
                spikes.append((v / mean, m, dt, h, v))
spikes.sort(reverse=True)
for r, m, dt, h, v in spikes[:10]:
    print(f"   {m}_{dt} h{h:02d}: eff load {v:,.0f} kW = {r:.2f}x daily mean  *** SPIKE ***")
if not spikes: print("   none > 1.8x daily mean")

print("=" * 100)
print("5. DSR ADD LOCATION (where does shifted load land?) - all months")
dsr_tot_add = defaultdict(float); dsr_tot_red = defaultdict(float)
for sid, b in bs.items():
    s = sl_by_id[sid]
    dsr_tot_add[(s["month"], s["id"].split("_")[1])] += b["dsr_add_kwh"]
    dsr_tot_red[(s["month"], s["id"].split("_")[1])] += b["dsr_reduce_kwh"]
add_by_dt = defaultdict(float); red_by_dt = defaultdict(float)
for (m, dt), v in dsr_tot_add.items(): add_by_dt[dt] += v
for (m, dt), v in dsr_tot_red.items(): red_by_dt[dt] += v
print("   annual dsr ADD by day-type:", {k: f"{v/1e6:.1f} GWh" for k, v in add_by_dt.items()})
print("   annual dsr REDUCE by day-type:", {k: f"{v/1e6:.1f} GWh" for k, v in red_by_dt.items()})
print("   (F18: reduce on wd but add on we = cross-day-type relocation)")

print("=" * 100)
print("5b. EV SMART CHARGING (REV-2): where does rescheduled EV energy come from / land?")
ev_out_h = defaultdict(float); ev_in_h = defaultdict(float)
ev_out_dt = defaultdict(float); ev_in_dt = defaultdict(float)
for sid, b in bs.items():
    h = int(sid.split("_")[-1]); dt = sid.split("_")[1]
    ev_out_h[h] += b.get("ev_shift_out_kwh", 0.0)
    ev_in_h[h] += b.get("ev_shift_in_kwh", 0.0)
    ev_out_dt[dt] += b.get("ev_shift_out_kwh", 0.0)
    ev_in_dt[dt] += b.get("ev_shift_in_kwh", 0.0)
tot_ev_out = sum(ev_out_dt.values())
if tot_ev_out < 1e-6:
    print("   no EV shift in export (pre-REV-2 or smart charging off)")
else:
    print(f"   annual shifted: {tot_ev_out/1e6:.2f} GWh")
    print("   OUT by hour (GWh):", {h: round(v/1e6, 2) for h, v in sorted(ev_out_h.items()) if v > 1e5})
    print("   IN  by hour (GWh):", {h: round(v/1e6, 2) for h, v in sorted(ev_in_h.items()) if v > 1e5})
    print("   by day-type OUT:", {k: f"{v/1e6:.2f} GWh" for k, v in ev_out_dt.items()},
          " IN:", {k: f"{v/1e6:.2f} GWh" for k, v in ev_in_dt.items()})
    print("   (conservation is per (class, month, day-type) - OUT and IN per day-type must match)")

print("=" * 100)
print("6. GRID IMPORT CAP BINDING (suspicious round numbers / hours at cap)")
print(f"   slices with hours_per_year == 0: {len(ZERO_W)} -> {ZERO_W[:10]}")
imp_rates = sorted(((b["grid_import_kwh"] / W(sid), sid) for sid, b in bs.items() if W(sid) > 0), reverse=True)
top = imp_rates[0][0]
at_cap = [sid for r, sid in imp_rates if r > 0.999 * top]
print(f"   max import rate = {top:,.0f} kW; slices within 0.1% of max: {len(at_cap)} -> {at_cap[:8]}")
# B21: the 600 MW substation ceiling now binds on grey import
# PLUS wheeled green purchase (they share the physical connection) - audit
# the COMBINED rate;.get keeps pre-B21 exports readable.
comb_rates = sorted(
    (((b["grid_import_kwh"] + b.get("green_purchase_kwh", 0.0)) / W(sid), sid)
     for sid, b in bs.items() if W(sid) > 0), reverse=True)
gp_total = sum(b.get("green_purchase_kwh", 0.0) for b in bs.values())
print(f"   B21 combined (import + green OA) max rate = {comb_rates[0][0]:,.0f} kW"
      f" (binding constraint post-B21; scaled cap 600,000);"
      f" green purchased total = {gp_total/1e6:,.1f} GWh")
exp_rates = sorted(((b["grid_export_kwh"] / W(sid), sid) for sid, b in bs.items() if W(sid) > 0), reverse=True)
print(f"   max export rate = {exp_rates[0][0]:,.0f} kW (label note: '60,000' was the"
      f" 100k-town cap - the scaled production cap is 180,000)")
at_ecap = [sid for r, sid in exp_rates if r > 0.999 * exp_rates[0][0]]
print(f"   slices at export max: {len(at_ecap)} -> {at_ecap[:8]}")

print("=" * 100)
print("7. DISPATCHABLES SEASONALITY (biomass straw should be seasonal in reality)")
for tech in ["biomass_kwh", "wte_kwh", "biogas_kwh"]:
    row = {}
    for m in MONTHS:
        e = sum(abs(b[tech]) for sid, b in bs.items() if sl_by_id[sid]["month"] == m)
        row[m] = e / 1e6
    tot = sum(row.values())
    if tot < 1e-6:
        print(f"   {tech:<12} ~0 everywhere")
        continue
    flat = max(row.values()) - min(row.values()) < 0.1 * max(row.values())
    print(f"   {tech:<12} GWh/mo:", {m: round(v, 2) for m, v in row.items()}, " FLAT" if flat else "")

print("=" * 100)
print("8. V2G + EV TIMING (V2G discharge by hour, July wd)")
v2g_h = {h: bs[f"jul_wd_{h:02d}"]["v2g_discharge_kwh"] / max(1e-9, W(f"jul_wd_{h:02d}")) for h in range(24)}
print("   V2G kW by hour:", {h: round(abs(v)) for h, v in v2g_h.items() if abs(v) > 1})
day_v2g = [h for h, v in v2g_h.items() if abs(v) > 1 and 9 <= h <= 17]
if day_v2g: print(f"   *** V2G discharging during work-day hours {day_v2g} - are commuter cars home? ***")

print("=" * 100)
print("9. THERMAL STORAGE + BATTERY CYCLING")
ts_c = sum(b["thermal_storage_charge_kwh"] for b in bs.values())
ts_d = sum(abs(b["thermal_storage_discharge_kwh"]) for b in bs.values())
bt_c = sum(b["battery_charge_kwh"] for b in bs.values())
print(f"   thermal charge {ts_c/1e6:.2f} GWh vs discharge {ts_d/1e6:.2f} GWh; battery charge {bt_c/1e6:.2f} GWh")

print("=" * 100)
print("10. PERIOD BREAKDOWN (SUP-1 battery learning + SUP-2 EF trajectory, empirically)")
pb = sc.get("period_breakdown")
if pb:
    print(json.dumps(pb, indent=2)[:2400])
else:
    print("   no period_breakdown in scenario!")

print("=" * 100)
print("11. TARIFF BANDS: seasonal TOD? (peak hours by month)")
peak_h = defaultdict(set)
for s in slices:
    if s["tariff_band"] in ("peak", "super_peak"):
        peak_h[s["month"]].add(int(s["id"].split("_")[-1]))
uniq = set(tuple(sorted(v)) for v in peak_h.values())
print(f"   months WITH an evening peak band: {sorted(peak_h.keys())}")
print(f"   distinct peak-hour sets across those months: {len(uniq)} -> {uniq}")
print("   (FX-4: PSPCL/PSERC ToD has its only evening premium 16 Jun-15 Oct (paddy");
print("    season) -> expect peak bands in jun-sep ONLY; peak in all 12 months = no")
print("    seasonality = pre-FX-4 regression)")

print("=" * 100)
print("12. FESTIVAL DAYS: month coverage + demand vs weekday")
fest_share = {m: sum(s["festival_share"] for s in slices if s["month"] == m and s["festival_share"] > 0) for m in MONTHS}
print("   months with festival slices:", [m for m, v in fest_share.items() if v > 0])
for m in MONTHS:
    ids_w = [f"{m}_wd_{h:02d}" for h in range(24) if f"{m}_wd_{h:02d}" in bs and W(f"{m}_wd_{h:02d}") > 0]
    ids_f = [f"{m}_fs_{h:02d}" for h in range(24) if f"{m}_fs_{h:02d}" in bs and W(f"{m}_fs_{h:02d}") > 0]
    if not ids_w or not ids_f: continue
    wd = sum(bs[i]["demand_kwh"] for i in ids_w) / sum(W(i) for i in ids_w)
    fe = sum(bs[i]["demand_kwh"] for i in ids_f) / sum(W(i) for i in ids_f)
    print(f"   {m}: fest/wd demand ratio = {fe/wd:.2f}")

print("=" * 100)
print("13. WEEKEND vs WEEKDAY demand ratio by month (office/school closure check)")
for m in ["jan", "jun", "jul"]:
    wd = sum(bs[f"{m}_wd_{h:02d}"]["demand_kwh"] for h in range(24)) / max(1, sum(W(f"{m}_wd_{h:02d}") for h in range(24)))
    we = sum(bs[f"{m}_we_{h:02d}"]["demand_kwh"] for h in range(24)) / max(1, sum(W(f"{m}_we_{h:02d}") for h in range(24)))
    print(f"   {m}: we/wd = {we/wd:.2f}")
print("done.")
