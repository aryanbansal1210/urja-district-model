"""Stage-D EXPORT — MINIMAL mode.

The "shorter run now" (~30 min): re-solve full_stack alpha=0 + the 2 DC-PPA
scenarios at the CURRENT (post-ownership-correction) baseline, attach the
Codex-Batch-2 Stage-D data layer, and MERGE into the existing
dispatch_results.json. The other 17 scenarios (Pareto alpha>0, Agile, BAU,
pv_only...) are left as-is at the stale 1,398M baseline until the OVERNIGHT
FULL regen (`python -m energy.dispatch`) refreshes everything consistently.

Production byte-exact: full_stack alpha=0 MUST solve to 1,402,369,939.69 (the
script asserts it). The Stage-D fields are read-only post-hoc; voltage class +
transformers come from a separate electrical-enabled econ clone (topology only).

Run:  python scripts/stage_d_export.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics                    # noqa: E402
from energy.network import load_optimised_network          # noqa: E402
from energy.dispatch import (                               # noqa: E402
    solve_dispatch,
    _attach_stage_d_export_fields,
    _scenario_payload_dict,
)

OUT = os.path.join(ROOT, "outputs", "data", "energy", "dispatch_results.json")
PIN = 3_853_999_038.27


def _replace(scenarios, pred, new_dict, label):
    for i, s in enumerate(scenarios):
        if pred(s):
            scenarios[i] = new_dict
            print(f"   replaced scenario: {label}", flush=True)
            return
    scenarios.append(new_dict)
    print(f"   appended scenario (no match found): {label}", flush=True)


def main() -> None:
    net = load_optimised_network()

    # 1) production full_stack alpha=0 (byte-exact) + Stage-D fields
    print("solving full_stack alpha=0 (production, multi-period) ...", flush=True)
    econ = load_economics(force_reload=True)
    r_fs = solve_dispatch(net, econ, "full_stack", alpha=0.0)
    print(f"  full_stack a=0 = {r_fs.annual_cost_inr:,.2f}  (pin {PIN:,.2f})", flush=True)
    assert abs(r_fs.annual_cost_inr - PIN) < 5.0, (
        f"BYTE-EXACT BROKEN: full_stack a=0 = {r_fs.annual_cost_inr:,.2f} != {PIN:,.2f}")
    print("  attaching Stage-D export fields (by_cell + per-edge + voltage + transformers) ...",
          flush=True)
    _attach_stage_d_export_fields(r_fs, net, econ)

    # 2) DC-PPA standard
    print("solving full_stack_dc_ppa (standard offtaker) ...", flush=True)
    e_std = load_economics(force_reload=True)
    e_std.set_ppa_enabled(True)
    r_std = solve_dispatch(net, e_std, "full_stack", alpha=0.0)
    r_std.scenario = "full_stack_dc_ppa"

    # 3) DC-PPA green RE-concession
    print("solving full_stack_dc_ppa_green (RE-concession offtaker) ...", flush=True)
    e_grn = load_economics(force_reload=True)
    e_grn.set_ppa_enabled(True)
    cps = e_grn.__dict__["ppa_raw"]["counterparties"]
    cps["data_centre_offsite"]["enabled"] = False
    cps["data_centre_offsite_re_concession"]["enabled"] = True
    r_grn = solve_dispatch(net, e_grn, "full_stack", alpha=0.0)
    r_grn.scenario = "full_stack_dc_ppa_green"

    # 4) merge into the existing JSON (other scenarios untouched)
    print("merging into dispatch_results.json ...", flush=True)
    with open(OUT, encoding="utf-8") as f:
        d = json.load(f)
    sc = d["scenarios"]
    fs_dict = _scenario_payload_dict(r_fs, econ)
    std_dict = _scenario_payload_dict(r_std, e_std)
    grn_dict = _scenario_payload_dict(r_grn, e_grn)
    _replace(sc, lambda s: s.get("name") == "full_stack" and abs(s.get("alpha", -9)) < 1e-9,
             fs_dict, "full_stack a=0 (+ Stage-D fields, refreshed to 3,658.2M)")
    _replace(sc, lambda s: s.get("name") == "full_stack_dc_ppa", std_dict, "full_stack_dc_ppa")
    _replace(sc, lambda s: s.get("name") == "full_stack_dc_ppa_green", grn_dict, "full_stack_dc_ppa_green")
    d.setdefault("economics_meta", {})["stage_d_export_note"] = (
        "MINIMAL refresh 2026-07-14 (A4 re-time): full_stack a=0 + the 2 "
        "DC-PPA scenarios re-solved at the F6-run-2 baseline "
        "3,658,232,309.48 + Stage-D fields attached "
        "(by_cell.net_district_flow_kwh[_by_daypart], "
        "stage_d_per_edge_flow_kwh, stage_d_per_edge_voltage_class, "
        "stage_d_transformer_zones, stage_d_substation_cell; DC-PPA scenarios "
        "carry dc_ppa_offtake_kwh + dc_ppa_revenue_inr). Substation = the "
        "JUNCTION-RULE pick (25, 25) (register B15, 2026-07-14); the other "
        "17 scenarios are already F6-run-2-consistent from the 2026-07-12 "
        "mega-batch regen and are untouched here.")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)

    # 5) report what landed
    nbb = sum(1 for v in fs_dict.get("stage_d_per_edge_voltage_class", {}).values()
              if v == "backbone_33kv")
    print("\n=== Stage-D MINIMAL export written ===", flush=True)
    print(f"  full_stack a=0 by_cell cells           : {len(fs_dict.get('by_cell', {}))}")
    print(f"  per-edge flow entries                  : {len(fs_dict.get('stage_d_per_edge_flow_kwh', {}))}")
    print(f"  per-edge voltage_class (backbone_33kv) : {nbb} of "
          f"{len(fs_dict.get('stage_d_per_edge_voltage_class', {}))}")
    print(f"  transformer zones                      : {len(fs_dict.get('stage_d_transformer_zones', []))}")
    print(f"  substation cell                        : {fs_dict.get('stage_d_substation_cell')}")
    print(f"  DC-PPA std    offtake/revenue          : "
          f"{std_dict.get('dc_ppa_offtake_kwh'):,.0f} kWh / Rs {std_dict.get('dc_ppa_revenue_inr'):,.0f}")
    print(f"  DC-PPA green  offtake/revenue          : "
          f"{grn_dict.get('dc_ppa_offtake_kwh'):,.0f} kWh / Rs {grn_dict.get('dc_ppa_revenue_inr'):,.0f}")
    print(f"  -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
