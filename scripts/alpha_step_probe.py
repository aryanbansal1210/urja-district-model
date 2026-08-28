"""Complete the regular alpha grid, and locate the battery-timing step.

WHY. The alpha sweep in `dispatch_results.json` tests 0.65 and then 0.80 with
nothing between, and that is exactly where the cost-carbon frontier steps: at
0.65 the battery first appears in the 2042 vintage, at 0.80 it appears in 2030,
and 94 % of the 35.5 kt emissions difference lands in the 2030 period alone.
No technology is added across the step - generation is identical at both
weights - so the step is a TIMING decision, and a discrete one, which is why
the frontier has a cliff rather than a slope.

Two extra solves bracket the crossover to within 0.05 so the thesis can state
where it occurs instead of bracketing it across a 0.15 gap.

Clone-econ. Production config, pins and layout untouched.

    python scripts/alpha_step_probe.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics            # noqa: E402
from energy.network import load_optimised_network  # noqa: E402
from energy.dispatch import solve_dispatch         # noqa: E402

OUT = os.path.join(ROOT, "outputs", "data", "energy", "alpha_step_probe.json")
# The regular 0.1 grid (config carbon_objective.alphas, regularised
#) already holds 0.0-0.5, 0.8 and 1.0 on the current basis.
# These three complete it. 0.75 was dropped with the irregular ladder.
ALPHAS = [0.60, 0.70, 0.90]


def main() -> int:
    print("ALPHA STEP PROBE - where does the battery jump to 2030?", flush=True)
    rows = []
    for a in ALPHAS:
        e = deepcopy(load_economics(force_reload=True))
        t0 = time.time()
        r = solve_dispatch(load_optimised_network(), e, "full_stack", alpha=a)
        # period_breakdown is Dict[INT,...] on the result object and only
        # becomes string-keyed once it is serialised to JSON. Indexing it with
        # "2030" raised KeyError after the solve had already completed.
        pb = r.period_breakdown or {}
        p30 = pb.get(2030) or pb.get("2030") or {}
        b30 = float((p30.get("installed_capacities") or {}).get("battery_kwh", 0.0))
        rows.append({
            "alpha": a,
            "annual_cost_inr": float(r.annual_cost_inr),
            "annual_emissions_kgco2": float(r.annual_emissions_kgco2),
            "battery_2030_kwh": b30,
            "battery_enters_2030": b30 > 1.0,
            "emissions_2030_kg": float(p30.get("annual_emissions_kgco2", 0.0)),
        })
        print(f"  alpha {a:.2f}  solved in {(time.time()-t0)/60:5.1f} min  "
              f"cost {float(r.annual_cost_inr):>18,.2f}  "
              f"CO2 {float(r.annual_emissions_kgco2)/1e6:>7.2f} kt  "
              f"battery 2030 {b30:>10,.0f} kWh"
              f"{'  <-- ENTERS 2030' if b30 > 1 else ''}", flush=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "basis": "2026-08-19 solar-thermal pins",
                   "known": {"0.65": "battery enters 2042",
                             "0.80": "battery enters 2030"},
                   "probe": rows}, f, indent=1)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
