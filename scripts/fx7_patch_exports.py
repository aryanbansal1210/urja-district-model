"""FX-7: patch the existing exports with the honest metrics - NO solve.

1. dispatch_results.json (additive): recompute `renewable_share` to include biomass/WTE/biogas
, add `pv_self_consumption_share` (the old PV-only metric), `metric_notes`, and
   `capacities_base_year` from period_breakdown).
2. Rebuild outputs/data/energy/optimised_sa_pareto.json (the month-stale "Stage B preview"
   source, AUD-13/V1) from the CURRENT dispatch_results scenario ladder.
Backups: *.bak.20260610-fx7. Run: python scripts/fx7_patch_exports.py
"""
from __future__ import annotations
import json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
DR = "outputs/data/energy/dispatch_results.json"
PAR = "outputs/data/energy/optimised_sa_pareto.json"

shutil.copy2(DR, DR + ".bak.20260610-fx7")
shutil.copy2(PAR, PAR + ".bak.20260610-fx7")

d = json.load(open(DR, encoding="utf-8"))
NOTES = {
    "renewable_share": "includes biomass/WTE/biogas (F24 fix); the old PV-only metric is pv_self_consumption_share",
    "lcoe_inr_per_kwh": "NET system cost per kWh served (export + PPA revenue already netted) - not a conventional LCOE",
    "capacities": "END-OF-HORIZON (2055) installed; use capacities_base_year or period_breakdown for the 2030 design (F19)",
}
changed = 0
for sc in d.get("scenarios", []):
    dem = float(sc.get("annual_demand_kwh") or 0.0)
    if dem <= 0:
        continue
    pv = float(sc.get("pv_generation_kwh") or 0.0)
    exp = float(sc.get("grid_export_kwh") or 0.0)
    bio = (float(sc.get("biomass_generation_kwh") or 0.0)
           + float(sc.get("wte_generation_kwh") or 0.0)
           + float(sc.get("biogas_generation_kwh") or 0.0))
    sc["pv_self_consumption_share"] = max(0.0, min(1.0, (pv - exp) / dem))
    sc["renewable_share"] = max(0.0, min(1.0, (pv - exp + bio) / dem))
    sc["metric_notes"] = NOTES
    pb = sc.get("period_breakdown") or {}
    if pb:
        first = sorted(pb.keys())[0]
        inst = (pb[first] or {}).get("installed_capacities")
        if inst:
            sc["capacities_base_year"] = {"year": int(first), **inst}
    changed += 1
json.dump(d, open(DR, "w", encoding="utf-8"))
print(f"dispatch_results.json: patched {changed} scenarios")

# --- rebuild the pareto/Stage-B-preview file from the current ladder ---
old = json.load(open(PAR + ".bak.20260610-fx7", encoding="utf-8"))
ladder = ["bau", "pv_only", "pv_battery", "pv_battery_v2g"]
rows = []
for name in ladder:
    sc = next((s for s in d["scenarios"] if s["name"] == name
               and abs(float(s.get("alpha", 0))) < 1e-9), None)
    if sc is None:
        print(f"  WARNING: scenario {name} not found; skipped"); continue
    caps = sc.get("capacities") or {}
    dem = float(sc.get("annual_demand_kwh") or 1.0)
    rows.append({
        "scenario": name,
        "solver": sc.get("solver"),
        "capacities": caps,
        "annual_cost_inr": sc["annual_cost_inr"],
        "annual_emissions_kgco2": sc["annual_emissions_kgco2"],
        "annual_demand_kwh": sc["annual_demand_kwh"],
        "grid_import_kwh": sc["grid_import_kwh"],
        "grid_export_kwh": sc["grid_export_kwh"],
        "pv_generation_kwh": sc["pv_generation_kwh"],
        "battery_throughput_kwh": sc.get("battery_throughput_kwh", 0.0),
        "v2g_discharge_kwh": sc.get("v2g_discharge_kwh", 0.0),
        "by_slice": {},
        "total_pv_kwp": float(caps.get("rooftop_pv_kwp", 0.0)) + float(caps.get("solar_farm_kwp", 0.0)),
        "renewable_share": sc["renewable_share"],
        "lcoe_inr_per_kwh": sc["annual_cost_inr"] / dem,
        "metric_notes": NOTES,
    })
out = {
    "layout": old.get("layout", "optimised_sa"),
    "currency": old.get("currency", "INR"),
    "source": "regenerated 2026-06-10 (FX-7/AUD-13) from dispatch_results.json at the "
              "1,402.4M production baseline - replaces the stale 2026-05-13 file",
    "results": rows,
}
json.dump(out, open(PAR, "w", encoding="utf-8"), indent=2)
print(f"optimised_sa_pareto.json: rebuilt with {len(rows)} scenarios at the current baseline")
for r in rows:
    print(f"  {r['scenario']:<16} cost {r['annual_cost_inr']/1e6:8.1f}M  emis {r['annual_emissions_kgco2']/1e6:6.1f}kt  "
          f"renshare {r['renewable_share']:.3f}  net-cost {r['lcoe_inr_per_kwh']:.2f}")
