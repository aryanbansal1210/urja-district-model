"""Fill the regular 0.1 carbon-weight grid with HORIZON quantities.

WHY THIS EXISTS, AND WHY `alpha_step_probe.py` COULD NOT BE REUSED.
The probe recorded `annual_cost_inr` and `annual_emissions_kgco2`
only. established that those are the WRONG PAIR for a frontier: the
multi-period objective trades LIFETIME cost against CUMULATIVE carbon, and on
the annual pair the frontier is not even monotone (probe alpha=0.70 dominates
pinned alpha=0.65 on both axes, which is a reporting artefact of reading a
multi-period result through one year).

So the probe's three points cannot be plotted on the corrected Figure 5.7. This
re-solves the same three weights and records the horizon quantities, which
completes the regular grid the author asked for:

    pinned ladder supplies  0.0 0.1 0.2 0.3 0.4 0.5 0.8 1.0   (horizon data)
    this script supplies    0.6 0.7 0.9                       (horizon data)
    dropped as irregular    0.05 0.65 0.92

Cumulative carbon is integrated the same way `fig_5_4` and `fig_pareto` do it -
each period's annual rate times the years that period represents - so the three
cannot disagree.

Clone-econ. Production config, pins and layout untouched.

    python scripts/alpha_grid_horizon.py
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

OUT = os.path.join(ROOT, "outputs", "data", "energy", "alpha_grid_horizon.json")
ALPHAS = [0.60, 0.70, 0.90]


def main() -> int:
    print("ALPHA GRID - horizon quantities for the regular 0.1 ladder",
          flush=True)
    net = load_optimised_network()
    rows = []
    for a in ALPHAS:
        e = deepcopy(load_economics(force_reload=True))
        t0 = time.time()
        r = solve_dispatch(net, e, "full_stack", alpha=a)
        # period_breakdown is Dict[INT,...] on the object; it only becomes
        # string-keyed once serialised. Accept either so a future change to
        # the serialiser cannot silently break this.
        pb = r.period_breakdown or {}

        def per(year):
            return pb.get(year) or pb.get(str(year)) or {}

        cum = 0.0
        batt = {}
        for y in (2030, 2042, 2055):
            v = per(y)
            cum += (float(v.get("annual_emissions_kgco2", 0.0))
                    * float(v.get("weight", 0.0)))
            batt[y] = max(0.0, float((v.get("installed_capacities") or {})
                                     .get("battery_kwh", 0.0)))
        rows.append({
            "alpha": a,
            "annual_cost_inr": float(r.annual_cost_inr),
            "lifetime_cost_inr": float(r.lifetime_cost_inr),
            "annual_emissions_kgco2": float(r.annual_emissions_kgco2),
            "cumulative_emissions_kgco2": cum,
            "battery_kwh": {str(k): v for k, v in batt.items()},
        })
        print("  alpha {:.2f}  {:5.1f} min  lifetime {:>18,.0f}  "
              "cumulative {:6.4f} Mt  battery2030 {:>10,.0f} kWh".format(
                  a, (time.time() - t0) / 60.0, r.lifetime_cost_inr,
                  cum / 1e9, batt[2030]), flush=True)

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({
            "basis": "2026-08-19 solar-thermal pins",
            "why": ("horizon quantities for the regular 0.1 alpha grid; the "
                    "2026-08-19 alpha_step_probe recorded annual figures only "
                    "and F63 shows those are the wrong pair for a frontier"),
            "integration": "cumulative = sum over periods of annual rate x weight",
            "grid": rows,
        }, fh, indent=1)
    print("wrote", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
