"""FX-1 comparison solve: production full_stack alpha=0 under the fixed
formulation vs the old pinned baseline. Diagnostic only - does NOT write production JSON.
Run: python scripts/fx1_compare_solve.py
"""
from __future__ import annotations
import os, sys, time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
from energy.costs import load_economics
from energy.network import load_optimised_network
from energy.dispatch import solve_dispatch

OLD_COST, OLD_EMIS = 1_402_369_939.69, 82_573_979.0
net = load_optimised_network(); econ = load_economics(force_reload=True)

t = time.time()
r = solve_dispatch(net, econ, "full_stack", alpha=0.0)
print(f"solved in {time.time()-t:.0f}s")
print(f"COST: {r.annual_cost_inr:,.2f}  (old {OLD_COST:,.2f}; delta {r.annual_cost_inr-OLD_COST:+,.0f} = {(r.annual_cost_inr/OLD_COST-1)*100:+.2f}%)")
print(f"EMIS: {r.annual_emissions_kgco2:,.0f}  (old {OLD_EMIS:,.0f}; delta {(r.annual_emissions_kgco2/OLD_EMIS-1)*100:+.2f}%)")
print(f"LIFETIME: {r.lifetime_cost_inr:,.0f}")
print(f"renewable_share {r.renewable_share():.4f} | pv_self {r.pv_self_consumption_share():.4f}")
print("capacities (end-of-horizon):", {k: round(v,1) for k,v in r.capacities.items() if abs(v)>0.5})

bs = r.by_slice
curt = sum(b.get("curtailment_kwh", 0.0) for b in bs.values())
print(f"CURTAILMENT (2030): {curt/1e6:.3f} GWh ({curt/max(1,r.pv_generation_kwh)*100:.2f}% of PV)")

# spike check: effective load vs daily mean per (month, day-type)
from energy.costs import load_economics as _le
sl = {s.id: s for s in econ.slices}
per = defaultdict(list)
for sid, b in bs.items():
    s = sl[sid]
    if s.hours_per_year <= 0: continue
    eff = (b["demand_kwh"] + b["dsr_add_kwh"] - b["dsr_reduce_kwh"]
           - b.get("solar_thermal_served_kwh", 0.0)) / s.hours_per_year
    per[(s.month, getattr(s, "day_type", "?"))].append((sid, eff))
spikes = []
for grp, vals in per.items():
    mean = sum(v for _, v in vals) / len(vals)
    for sid, v in vals:
        if mean > 0 and v / mean > 1.8:
            spikes.append((round(v/mean, 2), sid))
spikes.sort(reverse=True)
print(f"SPIKES >1.8x daily mean: {len(spikes)}  {spikes[:6]}")
imp_max = max(b["grid_import_kwh"]/sl[sid].hours_per_year for sid, b in bs.items() if sl[sid].hours_per_year > 0)
print(f"max import rate {imp_max:,.0f} kW (cap 200,000; pre-fix the artifact hour hit the cap)")
print("done - DIAGNOSTIC ONLY, no production files written")
