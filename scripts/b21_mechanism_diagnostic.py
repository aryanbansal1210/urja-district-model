"""B21 mechanism diagnostic - what EXACTLY does the green
purchase change in the single-period 2030 model?

Both discovery deltas (multi AND single) vs the pre-B21 pins came out at
+79,323,576.13 = the Rs 161.04M B21 constants MINUS Rs 81.71M - the same
gp-effect to the paisa in two different models. Before the FINDINGS entry
claims a mechanism, this script isolates it in the single-period model:
gp-ON vs gp-OFF (constants forced off in both), printing volumes and the
component-level deltas. ~6-8 min (two single solves).
"""
from __future__ import annotations

import sys
import time
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from energy.costs import load_economics
from energy.dispatch import solve_dispatch_pyomo
from energy.network import load_optimised_network


def _force_off(e) -> None:
    e.set_green_purchase_enabled(False)
    for k in ("boundary_opex_raw", "interconnection_raw", "farm_land_rent_raw"):
        e.__dict__[k] = {**(e.__dict__.get(k) or {}), "enabled": False}


def _single(e):
    e.__dict__["multi_period_raw"] = {
        **dict(e.__dict__.get("multi_period_raw", {}) or {}),
        "enabled": False,
    }
    net = load_optimised_network()
    return solve_dispatch_pyomo(net, e, scenario_name="full_stack", alpha=0.0)


def main() -> None:
    t0 = time.time()
    e_off = deepcopy(load_economics(force_reload=True))
    e_off.set_ppa_enabled(False)
    _force_off(e_off)
    print(f"[{time.time()-t0:.0f}s] solving single-period gp-OFF...", flush=True)
    r_off = _single(e_off)

    e_on = deepcopy(load_economics(force_reload=True))
    e_on.set_ppa_enabled(False)
    _force_off(e_on)
    e_on.set_green_purchase_enabled(True)
    print(f"[{time.time()-t0:.0f}s] solving single-period gp-ON...", flush=True)
    r_on = _single(e_on)

    price = e_on.green_purchase_delivered_price_inr_per_kwh()
    gp = r_on.__dict__.get("green_purchase_kwh", 0.0)
    print("\n=== SINGLE-PERIOD 2030: gp-ON vs gp-OFF (constants off both) ===")
    print(f"cost   OFF {r_off.annual_cost_inr:,.2f}  ON {r_on.annual_cost_inr:,.2f}"
          f"  delta {r_on.annual_cost_inr - r_off.annual_cost_inr:+,.2f}")
    print(f"emis   OFF {r_off.annual_emissions_kgco2:,.2f}  ON "
          f"{r_on.annual_emissions_kgco2:,.2f}  delta "
          f"{r_on.annual_emissions_kgco2 - r_off.annual_emissions_kgco2:+,.2f}")
    print(f"green purchased: {gp:,.0f} kWh ({gp/1e9*1000:.1f} GWh) at "
          f"Rs {price:.4f} -> gross spend {gp*price:,.0f}")
    print(f"grid import  OFF {r_off.grid_import_kwh/1e9*1000:,.1f}  ON "
          f"{r_on.grid_import_kwh/1e9*1000:,.1f} GWh "
          f"(delta {(r_on.grid_import_kwh-r_off.grid_import_kwh)/1e9*1000:+,.1f})")
    print(f"grid export  OFF {r_off.grid_export_kwh/1e9*1000:,.1f}  ON "
          f"{r_on.grid_export_kwh/1e9*1000:,.1f} GWh")
    print(f"PV gen       OFF {r_off.pv_generation_kwh/1e9*1000:,.1f}  ON "
          f"{r_on.pv_generation_kwh/1e9*1000:,.1f} GWh")
    for k in ("rooftop_pv_kwp", "solar_farm_kwp", "battery_kwh", "v2g_units",
              "thermal_storage_kwh", "carport_kwp", "floating_pv_kwp",
              "bipv_kwp"):
        a, b = r_off.capacities.get(k, 0.0), r_on.capacities.get(k, 0.0)
        if abs(a - b) > 0.5:
            print(f"cap {k}: OFF {a:,.1f} -> ON {b:,.1f}")
    # import-tariff-band split of the import delta
    from collections import defaultdict
    band_delta = defaultdict(float)
    for sid, b_on in r_on.by_slice.items():
        b_off = r_off.by_slice[sid]
        band_delta[e_on.import_tariff(sid)] += (
            b_on["grid_import_kwh"] - b_off["grid_import_kwh"])
    print("import delta by tariff band (Rs/kWh -> GWh):")
    for tariff in sorted(band_delta):
        print(f"  {tariff:5.2f}: {band_delta[tariff]/1e9*1000:+8.2f}")
    print(f"\nwall {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
