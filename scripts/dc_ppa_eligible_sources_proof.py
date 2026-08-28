"""Proof for the DC-PPA ELIGIBLE-SOURCE RULE.

THE RULE: no rooftop of any kind may supply the data centre. Only the solar
farm, the carports and the floating PV - ground-, water- and parking-mounted
public solar. Biomass CHP, waste-to-energy, biogas, battery and V2G are also
excluded.

WHAT MUST HOLD:
  1. PRODUCTION IS UNTOUCHED. The constraint lives inside `if _dc_ppa_on`
     and `ppa.enabled` is false in production, so full_stack must still be
     EXACTLY 1,982,474,680.20 / 117,401,973.84.
  2. The sale must FALL. Unconstrained it was 83.1 GWh, and 164 of the 354
     selling slices leant on the CHP fleet. Those slices must now sell less.
     A drop is the constraint working.
  3. In EVERY slice, offtake <= eligible generation. Checked directly against
     the farm/carport/FPV yields, not assumed from the solver's word.
  4. The PPA should still be worth signing. If the lifetime saving survives
     on public solar ALONE, the finding is far stronger than the version
     that quietly leant on private rooftops.

Run from district_v3:
    PYTHONPATH=. python -u scripts/dc_ppa_eligible_sources_proof.py
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics                    # noqa: E402
from energy.dispatch import solve_dispatch_pyomo           # noqa: E402
from energy.network import load_optimised_network          # noqa: E402

PROD = (1_982_474_680.20, 117_401_973.84)
UNCONSTRAINED_PPA = {"offtake_kwh": 83_055_076.28,
                     "annual_cost": 1_999_077_205.0,
                     "lifetime": 57_762_386_140.0}

net = load_optimised_network()
print("network built\n", flush=True)

# --- 1. production, PPA off: must be byte-exact -------------------------
e_off = deepcopy(load_economics(force_reload=True))
e_off.set_ppa_enabled(False)
r_off = solve_dispatch_pyomo(net, e_off, scenario_name="full_stack", alpha=0.0)
print("--- CHECK 1: production untouched (PPA off) ---")
dc = r_off.annual_cost_inr - PROD[0]
de = r_off.annual_emissions_kgco2 - PROD[1]
print(f"  cost {r_off.annual_cost_inr:>18,.2f}  vs {PROD[0]:>18,.2f}  ({dc:+.2f})")
print(f"  CO2  {r_off.annual_emissions_kgco2:>18,.2f}  vs {PROD[1]:>18,.2f}  ({de:+.2f})")
print("  " + ("OK - the constraint is structurally absent from production"
              if abs(dc) < 0.01 and abs(de) < 0.01
              else "*** PRODUCTION MOVED - the constraint leaked out of the "
                   "PPA branch. STOP. ***"))

# --- 2. PPA on, now with the eligible-source rule ----------------------
e_on = deepcopy(load_economics(force_reload=True))
e_on.set_ppa_enabled(True)
r_on = solve_dispatch_pyomo(net, e_on, scenario_name="full_stack", alpha=0.0)
off = r_on.__dict__.get("dc_ppa_offtake_kwh", 0.0)
print("\n--- CHECK 2: the sale falls to what public solar can back ---")
print(f"  offtake unconstrained  {UNCONSTRAINED_PPA['offtake_kwh'] / 1e6:>8,.2f} GWh")
print(f"  offtake ELIGIBLE-ONLY  {off / 1e6:>8,.2f} GWh"
      f"   ({100 * (off / UNCONSTRAINED_PPA['offtake_kwh'] - 1):+.1f}%)")

# --- 3. verify the ceiling slice by slice -------------------------------
print("\n--- CHECK 3: offtake <= eligible generation, every slice ---")
caps = r_on.capacities or {}
yf = net.pv_yield_per_kwp_kwh_solar_farm(e_on)
tr_mult = e_on.tracked_pv_yield_multiplier()
fpv_mult = e_on.floating_pv_yield_multiplier_vs_ground_mount()
worst = None
bad = 0
for sid, b in (r_on.by_slice or {}).items():
    sold = b.get("dc_ppa_kwh", 0.0)
    if sold <= 0:
        continue
    elig = yf[sid] * (caps.get("solar_farm_fixed_kwp", 0.0)
                      + tr_mult * caps.get("solar_farm_tracked_kwp", 0.0)
                      + caps.get("carport_kwp", 0.0)
                      + fpv_mult * caps.get("floating_pv_kwp", 0.0))
    slack = elig - sold
    if slack < -1.0:
        bad += 1
    if worst is None or slack < worst[1]:
        worst = (sid, slack, sold, elig)
print(f"  slices selling: {sum(1 for b in (r_on.by_slice or {}).values() if b.get('dc_ppa_kwh', 0) > 0)}")
print(f"  VIOLATIONS (sold > eligible): {bad}")
if worst:
    print(f"  tightest slice {worst[0]}: sold {worst[2]:,.0f} kWh, "
          f"eligible {worst[3]:,.0f} kWh, slack {worst[1]:,.0f}")
print("  NOTE: end-of-horizon capacities are used for the check, so the "
      "slack is a LOWER bound in early periods - a violation here is real, "
      "a pass is necessary but not sufficient. The binding proof is the LP "
      "constraint itself.")

# --- 4. is it still worth signing? -------------------------------------
print("\n--- CHECK 4: does the deal survive on public solar alone? ---")
print(f"  lifetime PPA OFF        {r_off.lifetime_cost_inr:>20,.2f}")
print(f"  lifetime PPA ON         {r_on.lifetime_cost_inr:>20,.2f}")
sav = r_off.lifetime_cost_inr - r_on.lifetime_cost_inr
print(f"  lifetime SAVING         {sav:>20,.2f}  ({sav / 1e9:,.2f} bn)")
print(f"  unconstrained saving    {UNCONSTRAINED_PPA['lifetime'] and (62_849_079_766.27 - UNCONSTRAINED_PPA['lifetime']):>20,.2f}")
print(f"  base-year cost ON       {r_on.annual_cost_inr:>20,.2f}")
print(f"  base-year CO2 ON        {r_on.annual_emissions_kgco2:>20,.2f}")
print("\n  If the saving survives, the thesis line is the strong one: the")
print("  district sells ONLY publicly-owned ground/water/parking solar, no")
print("  household's roof is monetised, and the deal still pays.")
