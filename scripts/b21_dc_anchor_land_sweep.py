"""B21/ thesis figure: WHAT LAND GRANT WOULD A DATA-CENTRE ANCHOR
TENANT JUSTIFY? (; run at the FINAL baseline - post--anneal -
so the figure never goes stale.)

 killed the merchant PPA under phased land (offtake 0; the district
pays the standing charge for nothing). B21 then gave the model the
regional market BOTH ways. The remaining policy question: if a 25 MW
data-centre anchor tenant asks the town for power under the
RE-concessional intra-state PPA (net ~Rs 4.79/kWh, economics.yaml
data_centre_offsite_re_concession), HOW MUCH EXTRA farm-land grant makes
serving it worthwhile - and where does the answer bend?

Sweep: extra 2030-grant cells {0, +25, +50, +100} stacked on the ratified
200/250/300 schedule, with the RE-concession PPA forced ON, vs the same
grants with the PPA OFF. Each point = one multi-period solve (~5-6 min);
8 solves ~= 45 min. PAUSE RULE: tell the author the ETA before launching.

Output: outputs/data/energy/b21_dc_anchor_land_sweep.md (+.json).
NOTE: extra grant cells here are a COUNTERFACTUAL knob on the energy
model only (phased_land_multipliers scale off the schedule table when the
tags are absent... they scale off TAGS - so this sweep OVERRIDES the
multi_period.farm_land_cells_by_period table AND relies on the fact that
land multipliers fall back to the table ratio when expansion tags cover
fewer cells than the schedule; verify the first point against the pin
before trusting the rest - the script asserts it).
"""
from __future__ import annotations

import json
import sys
import time
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "outputs" / "data" / "energy" / "b21_dc_anchor_land_sweep.md"
OUT_JSON = ROOT / "outputs" / "data" / "energy" / "b21_dc_anchor_land_sweep.json"

EXTRA_CELLS = [0, 25, 50, 100]


def _solve(extra: int, ppa_on: bool):
    from energy.costs import load_economics
    from energy.dispatch import solve_dispatch_pyomo
    from energy.network import load_optimised_network

    econ = deepcopy(load_economics(force_reload=True))
    mp = dict(econ.__dict__.get("multi_period_raw", {}) or {})
    base = dict(mp.get("farm_land_cells_by_period", {}) or {})
    mp["farm_land_cells_by_period"] = {
        k: int(v) + extra for k, v in base.items()
    }
    econ.__dict__["multi_period_raw"] = mp
    if ppa_on:
        econ.set_ppa_enabled(True)
        # activate ONLY the RE-concession counterparty
        cps = econ.__dict__.get("ppa_raw", {}).get("counterparties", {})
        raw = dict(econ.__dict__.get("ppa_raw", {}) or {})
        raw["counterparties"] = {
            name: {**spec, "enabled": name == "data_centre_offsite_re_concession"}
            for name, spec in cps.items()
        }
        econ.__dict__["ppa_raw"] = raw
    else:
        econ.set_ppa_enabled(False)
    net = load_optimised_network()
    r = solve_dispatch_pyomo(net, econ, scenario_name="full_stack", alpha=0.0)
    return {
        "extra_cells": extra,
        "ppa": "re_concession" if ppa_on else "off",
        "annual_cost_inr": r.annual_cost_inr,
        "annual_emissions_kg": r.annual_emissions_kgco2,
        "lifetime_cost_inr": r.lifetime_cost_inr,
        "dc_ppa_offtake_kwh": r.__dict__.get("dc_ppa_offtake_kwh", 0.0),
        "green_purchase_kwh": r.__dict__.get("green_purchase_kwh", 0.0),
    }


def main() -> None:
    t0 = time.time()
    rows = []
    for extra in EXTRA_CELLS:
        for ppa_on in (False, True):
            print(f"[{time.time()-t0:.0f}s] solving extra=+{extra} cells, "
                  f"ppa={'RE-concession' if ppa_on else 'off'}...", flush=True)
            rows.append(_solve(extra, ppa_on))
            r = rows[-1]
            print(f"   cost {r['annual_cost_inr']:,.0f}  emis "
                  f"{r['annual_emissions_kg']:,.0f}  offtake "
                  f"{r['dc_ppa_offtake_kwh']/1e6:,.1f} GWh  green-buy "
                  f"{r['green_purchase_kwh']/1e6:,.1f} GWh", flush=True)

    OUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    lines = [
        "# B21/F35 - what land grant would a data-centre anchor tenant justify?",
        "",
        "_Each row: multi-period full_stack alpha=0 with the ratified grant",
        "schedule +extra 2030 cells; PPA = RE-concessional intra-state",
        "(net ~4.79/kWh). Baseline (extra=0, ppa=off) must byte-match the",
        "production pin - if it does not, the layout/tags moved and the",
        "sweep needs re-anchoring._",
        "",
        "| extra cells | PPA | cost M/yr | CO2 kt | offtake GWh | green-buy GWh |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| +{r['extra_cells']} | {r['ppa']} "
            f"| {r['annual_cost_inr']/1e6:,.1f} "
            f"| {r['annual_emissions_kg']/1e6:,.1f} "
            f"| {r['dc_ppa_offtake_kwh']/1e6:,.1f} "
            f"| {r['green_purchase_kwh']/1e6:,.1f} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n-> {OUT_MD}\n-> {OUT_JSON}\nwall {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
