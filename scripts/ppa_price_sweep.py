"""Switching-point analysis #2 - DC-PPA price crossover (supervisor ask,).

Sweeps the GREEN data-centre PPA net price and re-solves full_stack alpha=0 at each, to find:
  (a) the OFFTAKE switch-on price  - below it the model prefers the 3.5 grid feed-in, above it it
      sells surplus PV to the DC instead;
  (b) the EMISSIONS-flip price      - where selling clean PV to the DC + meeting own load from grid
      pushes annual emissions ABOVE the no-PPA baseline (the mechanism);
  (c) confirms there is NO import-to-resell arbitrage (the dc_ppa_no_import_resale constraint caps
      grid import at own-demand+storage, so offtake rising should NOT drag grid import up 1:1).

Net price is set cleanly by giving the green counterparty tariff=target, wheeling=CSS=loss=0
(=> net = tariff). Pure diagnostic - clones econ, production untouched.
Run: python scripts/ppa_price_sweep.py
"""
from __future__ import annotations
import json, os, sys, time
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
from energy.costs import load_economics
from energy.network import load_optimised_network
from energy.dispatch import solve_dispatch

net = load_optimised_network()
GREEN = "data_centre_offsite_re_concession"
# tariff 3.5 -> 3.0. It never drove the solve (that reads econ directly), but it
# was written into the artefact JSON and the printed conclusion, so the reported
# "switches on near the export floor" was measured against the wrong floor.
EXPORT_FLOOR = float(load_economics().export_tariff())  # grid feed-in tariff
PRICES = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0]  # net Rs/kWh to the district


def _solve_no_ppa():
    e = deepcopy(load_economics(force_reload=True))
    e.set_ppa_enabled(False)
    return solve_dispatch(net, e, "full_stack", alpha=0.0)


def _solve_at_price(net_price: float):
    e = deepcopy(load_economics(force_reload=True))
    e.set_ppa_enabled(True)
    raw = e.__dict__["ppa_raw"]
    raw["enabled"] = True
    cps = raw.get("counterparties", {}) or {}
    for sp in cps.values():
        sp["enabled"] = False
    g = cps[GREEN]
    g["enabled"] = True
    g["tariff_inr_per_kwh"] = float(net_price)
    g["wheeling_charge_inr_per_kwh"] = 0.0
    g["cross_subsidy_surcharge_inr_per_kwh"] = 0.0
    g["wheeling_loss_fraction"] = 0.0
    r = solve_dispatch(net, e, "full_stack", alpha=0.0)
    actual_net = e.ppa_counterparty_net_tariff_inr_per_kwh(GREEN)
    return r, actual_net


def main():
    print("=== DC-PPA PRICE CROSSOVER SWEEP (full_stack a=0) ===", flush=True)
    t = time.time()
    base = _solve_no_ppa()
    base_emis = base.annual_emissions_kgco2
    base_imp = base.grid_import_kwh
    print(f"  no-PPA baseline: cost {base.annual_cost_inr:,.0f}, emis {base_emis/1e6:.2f} kt, "
          f"grid_import {base_imp/1e6:.2f} GWh ({time.time()-t:.0f}s)", flush=True)

    rows = []
    for price in PRICES:
        t = time.time()
        r, net_price = _solve_at_price(price)
        off = getattr(r, "dc_ppa_offtake_kwh", 0.0)
        imp = r.grid_import_kwh
        rows.append({
            "net_price_inr_per_kwh": round(net_price, 3),
            "offtake_gwh": off / 1e6,
            "grid_import_gwh": imp / 1e6,
            "grid_import_delta_gwh": (imp - base_imp) / 1e6,
            "emissions_kt": r.annual_emissions_kgco2 / 1e6,
            "emissions_delta_vs_noppa_kt": (r.annual_emissions_kgco2 - base_emis) / 1e6,
            "cost_inr": r.annual_cost_inr,
            "ppa_revenue_inr": getattr(r, "dc_ppa_revenue_inr", 0.0),
            "solve_s": round(time.time() - t, 0),
        })
        print(f"  net Rs{net_price:>4.2f}/kWh: offtake {off/1e6:>6.2f} GWh | "
              f"grid_imp {imp/1e6:>6.2f} GWh (d{(imp-base_imp)/1e6:+.2f}) | "
              f"emis {r.annual_emissions_kgco2/1e6:>6.2f} kt (d{(r.annual_emissions_kgco2-base_emis)/1e6:+.2f}) "
              f"[{rows[-1]['solve_s']:.0f}s]", flush=True)

    # find the crossovers
    on = next((x["net_price_inr_per_kwh"] for x in rows if x["offtake_gwh"] > 0.5), None)
    flip = next((x["net_price_inr_per_kwh"] for x in rows if x["emissions_delta_vs_noppa_kt"] > 0.01), None)
    max_imp_drag = max((x["grid_import_delta_gwh"] for x in rows), default=0.0)
    out = {
        "baseline_no_ppa": {"cost_inr": base.annual_cost_inr, "emissions_kt": base_emis / 1e6,
                            "grid_import_gwh": base_imp / 1e6},
        "export_floor_inr_per_kwh": EXPORT_FLOOR,
        "sweep": rows,
        "crossovers": {
            "offtake_switch_on_price": on,
            "emissions_flip_price": flip,
            "max_grid_import_increase_gwh": max_imp_drag,
            "no_import_resale_constraint": "active (dispatch.py dc_ppa_no_import_resale)",
        },
        "note": ("Offtake switches on near the 3.5 export floor (below it the model prefers grid "
                 "feed-in). The emissions-flip price is where selling clean PV + grid-backfilling own "
                 "load raises emissions vs no-PPA (F5). Grid import does NOT track offtake 1:1 because "
                 "the no-import-resale constraint blocks pure arbitrage."),
    }
    p = os.path.join(ROOT, "outputs", "data", "energy", "ppa_price_sweep.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=2)
    print("\n=== CROSSOVERS ===")
    print(f"  offtake switches ON at net ~Rs {on}/kWh (export floor = Rs {EXPORT_FLOOR})")
    print(f"  emissions flip ABOVE no-PPA baseline at net ~Rs {flip}/kWh (F5 mechanism)")
    print(f"  max grid-import increase across sweep = {max_imp_drag:+.2f} GWh "
          f"(no-resale constraint blocks import-to-resell arbitrage)")
    print(f"  -> wrote {p}")


if __name__ == "__main__":
    main()
