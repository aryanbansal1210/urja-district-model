"""IS THE ANTI-ARBITRAGE CONSTRAINT SUPPRESSING THE 2030 SOLAR FARM?

THE SYMPTOM: turning the PPA on made the model build a
SMALLER 2030 farm - 92,514 kWp against 201,000 kWp with the PPA off. Less
solar when offered a BETTER price. That is backwards, so either the price
signal is not reaching the build decision or something is capping the outlet.

THE SUSPECT is the "strict" anti-arbitrage form:
    imp_eff + exp + dc_ppa <= eff_dem + charge + thermal_chg
With import at zero this still reads exp + dc_ppa <= eff_dem + charge, so
PPA sales DISPLACE export headroom rather than adding to it.

THE TEST: same model, same everything, only the constraint form switched.
    A  PPA off                       -> the 201,000 kWp reference
    B  PPA on,  form = strict        -> reproduces the 92,514 kWp symptom?
    C  PPA on,  form = import_cap    -> does the farm come back?

WHAT THE ANSWER MEANS:
  * If C restores ~201,000 kWp, the strict form is over-binding. It must be
    reformulated BEFORE any PPA number is re-pinned, because part of the
    Rs 4.98 bn "saving" would then be avoided 2030 capex, not earned
    revenue - a capex saving wearing a revenue costume.
  * If C also builds ~92,514 kWp, the constraint is exonerated and the
    smaller farm has a real economic cause worth finding.

Run from district_v3:
    PYTHONPATH=. python -u scripts/ppa_anti_arbitrage_probe.py
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics                    # noqa: E402
from energy.dispatch import solve_dispatch_pyomo           # noqa: E402
from energy.network import load_optimised_network          # noqa: E402


def econ_for(ppa_on: bool, form: str | None):
    e = deepcopy(load_economics(force_reload=True))
    e.set_ppa_enabled(ppa_on)
    if form is not None:
        e.__dict__["ppa_raw"] = {**(e.__dict__.get("ppa_raw") or {}),
                                 "anti_arbitrage_form": form}
    return e


def farm_2030(r):
    pb = r.period_breakdown or {}
    if not pb:
        return None
    y = sorted(pb.keys())[0]
    return float((pb[y].get("installed_capacities") or {})
                 .get("solar_farm_kwp", 0.0))


net = load_optimised_network()
print("network built\n", flush=True)

cases = [
    ("A  PPA off                ", False, None),
    ("B  PPA on,  strict        ", True, "strict"),
    ("C  PPA on,  import_cap    ", True, "import_cap"),
]
res = {}
for label, on, form in cases:
    r = solve_dispatch_pyomo(net, econ_for(on, form),
                             scenario_name="full_stack", alpha=0.0)
    res[label.strip()[0]] = r
    print(f"{label} farm2030 {farm_2030(r):>10,.0f} kWp  "
          f"cost {r.annual_cost_inr:>18,.2f}  "
          f"lifetime {r.lifetime_cost_inr:>20,.2f}  "
          f"export {r.grid_export_kwh / 1e6:>7,.1f} GWh  "
          f"ppa {r.__dict__.get('dc_ppa_offtake_kwh', 0.0) / 1e6:>6,.1f} GWh",
          flush=True)

a, b, c = res["A"], res["B"], res["C"]
fa, fb, fc = farm_2030(a), farm_2030(b), farm_2030(c)

print("\n--- VERDICT ---")
print(f"  2030 farm, PPA off        {fa:>10,.0f} kWp   (the reference)")
print(f"  2030 farm, strict         {fb:>10,.0f} kWp   ({100 * (fb / fa - 1):+.1f}%)")
print(f"  2030 farm, import_cap     {fc:>10,.0f} kWp   ({100 * (fc / fa - 1):+.1f}%)")
if fc > fb * 1.10:
    print("\n  *** THE STRICT FORM IS SUPPRESSING THE BUILD. Relaxing it")
    print("  restores the farm. The constraint must be reformulated before")
    print("  any PPA number is re-pinned - and the lifetime saving below")
    print("  tells you how much of the Rs 4.98 bn was avoided capex. ***")
else:
    print("\n  *** THE CONSTRAINT IS EXONERATED. The smaller 2030 farm has")
    print("  another cause; do NOT relax the guard. Find the real reason")
    print("  before re-pinning. ***")

print(f"\n  lifetime  off {a.lifetime_cost_inr:>20,.2f}")
print(f"  lifetime  strict     {b.lifetime_cost_inr:>20,.2f}"
      f"   saving {a.lifetime_cost_inr - b.lifetime_cost_inr:>18,.2f}")
print(f"  lifetime  import_cap {c.lifetime_cost_inr:>20,.2f}"
      f"   saving {a.lifetime_cost_inr - c.lifetime_cost_inr:>18,.2f}")
print("\n  The gap between the two savings is the part of the headline that")
print("  depended on the constraint form rather than on the deal itself.")
