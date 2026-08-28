"""Solution TRUTH tests: verify the PUBLISHED production solution is
physically feasible - balance, caps, conservation - independent of the solver. Complements
the byte-exact pins (which prove reproducibility, NOT correctness). NO solve: reads
outputs/data/energy/dispatch_results.json in seconds.
Run: python tests/test_solution_feasibility.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics  # noqa: E402

_JSON = os.path.join(ROOT, "outputs", "data", "energy", "dispatch_results.json")


def _load():
    d = json.load(open(_JSON, encoding="utf-8"))
    sc = [s for s in d["scenarios"]
          if s["name"] == "full_stack" and abs(s.get("alpha", 1)) < 1e-9][0]
    sl = {s["id"]: s for s in d["slices"]}
    return d, sc, sl


def test_per_slice_energy_balance_holds():
    """The LP equality must hold in the EXPORTED solution for every active slice.

    FX-1-aware: if the export carries `curtailment_kwh`, the
    post-FX-1 balance applies (PV net of spill; ac_eff on biomass/WTE/biogas/
    thermal discharge per Q-1). Pre-FX-1 exports use the legacy formula.
    """
    _, sc, sl = _load()
    econ = load_economics(force_reload=True)
    ac_eff = 1.0 - econ.ac_loss_fraction()
    gi_eff = ac_eff * (1.0 - econ.pspcl_grid_loss_fraction())
    post_fx1 = any("curtailment_kwh" in b for b in sc["by_slice"].values())
    local_eff = ac_eff if post_fx1 else 1.0
    worst = 0.0
    for sid, b in sc["by_slice"].items():
        if sl[sid]["hours_per_year"] <= 0:
            continue
        # REV-2: managed-EV charge shift enters the balance
        # like DSR (out reduces the slice's load, in raises it)..get
        # keeps pre-REV-2 exports readable.
        # solar water heating reduces the ELECTRICAL load in the
        # same way DSR does - the heat is served from a collector, so those
        # kWh never have to be generated or imported. `demand_kwh` is GROSS,
        # so the served heat is subtracted here.
        # THIS TEST CAUGHT THE OMISSION. When solar thermal was first wired
        # into the LP the term was left out of the exported by_slice dict, and
        # kWh. The LP itself was correct; only the export was short. A test
        # that reconstructs the balance from the EXPORT rather than from the
        # model is the only thing that would have found that.
        lhs = (b["demand_kwh"] - b["dsr_reduce_kwh"] + b["dsr_add_kwh"]
               - b.get("solar_thermal_served_kwh", 0.0)
               - b.get("ev_shift_out_kwh", 0.0) + b.get("ev_shift_in_kwh", 0.0)
               + b["battery_charge_kwh"] + b["thermal_storage_charge_kwh"]
               + b["grid_export_kwh"] + b.get("dc_ppa_kwh", 0.0))
        # B21: buy-side green purchase enters DELIVERED (losses
        # + in-kind charges priced into the tariff, not the balance)..get
        # keeps pre-B21 exports readable.
        rhs = (b["pv_kwh"] - b.get("curtailment_kwh", 0.0)
               + ac_eff * (abs(b["battery_discharge_kwh"]) + abs(b["v2g_discharge_kwh"]))
               + local_eff * (abs(b["thermal_storage_discharge_kwh"]) + abs(b["biomass_kwh"])
                              + abs(b["wte_kwh"]) + abs(b["biogas_kwh"]))
               + gi_eff * b["grid_import_kwh"]
               + b.get("green_purchase_kwh", 0.0))
        worst = max(worst, abs(lhs - rhs))
    assert worst < 1.0, f"worst per-slice balance residual {worst:.3f} kWh (post_fx1={post_fx1})"


def test_grid_caps_respected():
    _, sc, sl = _load()
    econ = load_economics(force_reload=True)
    imp_cap = econ.import_capacity_limit_kw()
    exp_cap = econ.export_capacity_limit_kw()
    for sid, b in sc["by_slice"].items():
        h = sl[sid]["hours_per_year"]
        if h <= 0:
            continue
        assert b["grid_import_kwh"] / h <= imp_cap * 1.0001, sid
        # B21: grey import + wheeled green share the SAME
        # physical substation connection (.get = pre-B21 back-compat).
        assert ((b["grid_import_kwh"] + b.get("green_purchase_kwh", 0.0)) / h
                <= imp_cap * 1.0001), sid
        assert b["grid_export_kwh"] / h <= exp_cap * 1.0001, sid


def test_dsr_monthly_conservation():
    _, sc, sl = _load()
    from collections import defaultdict
    red, add = defaultdict(float), defaultdict(float)
    for sid, b in sc["by_slice"].items():
        red[sl[sid]["month"]] += b["dsr_reduce_kwh"]
        add[sl[sid]["month"]] += b["dsr_add_kwh"]
    for mm in red:
        assert abs(red[mm] - add[mm]) < 1.0, (mm, red[mm], add[mm])


def test_ev_shift_bucket_conservation():
    """REV-2: managed-EV charge shift must conserve energy per
    (month, day-type) bucket - the LP constraint is per (class, bucket); the
    export sums classes, and each class conserves per bucket, so the summed
    per-bucket totals must match too. No-op (0 == 0) on pre-REV-2 exports."""
    _, sc, sl = _load()
    from collections import defaultdict
    out, inn = defaultdict(float), defaultdict(float)
    for sid, b in sc["by_slice"].items():
        key = (sl[sid]["month"], sid.split("_")[1])
        out[key] += b.get("ev_shift_out_kwh", 0.0)
        inn[key] += b.get("ev_shift_in_kwh", 0.0)
    for key in out:
        assert abs(out[key] - inn[key]) < 1.0, (key, out[key], inn[key])


def test_dispatchables_within_annual_hour_caps():
    _, sc, _ = _load()
    econ = load_economics(force_reload=True)
    cap = sc["capacities"]
    checks = [
        ("biomass_kwh", cap["biomass_kw_e"], econ.biomass_operating_hours_per_year()),
        ("wte_kwh", cap["wte_kw_e"], econ.wte_operating_hours_per_year()),
        ("biogas_kwh", cap["biogas_kw_e"], econ.biogas_operating_hours_per_year()),
    ]
    for key, kw, hrs in checks:
        ann = sum(abs(b[key]) for b in sc["by_slice"].values())
        assert ann <= kw * hrs * 1.0001, (key, ann, kw * hrs)


def test_bau_cost_is_pure_tariffed_import():
    """BAU (the headline denominator) = sum(slice import x ToU tariff) + the
    B21 PARITY CONSTANTS.

    B21 deliberately charges the interconnection annuity +
    waste/canal boundary opex to EVERY scenario including BAU (fair-comparison
    parity, register B21), so the regenerated JSON stores BAU annual_cost WITH
    them. LATENT-RED HISTORY: the batch ran its suite
    BEFORE its regen, so the pure-import form of this assert validated the
    pre-B21 JSON and silently went stale when the B21 regen landed; the
    run-2 pin proof caught it. Kept RELATIVE (no pinned constant) so it holds
    across re-baselines; the parity terms are read live from economics."""
    d, _, _ = _load()
    econ = load_economics(force_reload=True)
    bau = [s for s in d["scenarios"] if s["name"] == "bau"][0]
    recomputed = sum(b["grid_import_kwh"] * econ.import_tariff(sid)
                     for sid, b in bau["by_slice"].items())
    parity = 0.0
    if econ.interconnection_enabled():
        #: the connection is SIZED, so the flat annuity is
        # REPLACED by per-MW x the MW this scenario actually sized (BAU 203.6
        # MW vs the town's 129.4 - that gap IS the decentralisation result).
        # Falls back to the flat charge when sizing is off, so this test
        # holds on both sides of the flag.
        _mw = bau.get("grid_connection_mw")
        if econ.interconnection_sizing_enabled() and _mw is not None:
            parity += econ.interconnection_annualised_inr_per_mw() * float(_mw)
        else:
            parity += econ.interconnection_annualised_inr()
    if econ.boundary_opex_enabled():
        parity += econ.boundary_opex_annual_inr(2030)
    #: the district's own cables, substation and
    # distribution transformers, charged to every scenario incl. BAU.
    if econ.en_cost_in_production_enabled():
        from energy.electrical_assets import production_network_annualised_inr
        from energy.network import load_optimised_network
        parity += float(
            production_network_annualised_inr(load_optimised_network(), econ)
            .get("annualised_total_inr", 0.0))
    #: BAU is now CHARGED for the diesel it burns during
    # uncovered outages. THIS TERM WAS INVISIBLE TO THIS TEST until the
    # batch published it - a parity test that cannot see a cost
    # term has silently stopped testing parity, which is exactly the
    # LATENT-RED failure mode described above happening a second time.
    parity += float(bau.get("diesel_backup_cost_inr", 0.0) or 0.0)
    assert abs(recomputed + parity - bau["annual_cost_inr"]) < 1.0, (
        recomputed, parity, bau["annual_cost_inr"])


def main():
    import time
    import traceback
    fns = [v for k, v in sorted(globals().items())
           if callable(v) and k.startswith("test_")]
    passed, failed = [], []
    for fn in fns:
        t = time.time()
        try:
            fn()
            print(f"  OK   {fn.__name__}  ({time.time()-t:.2f}s)")
            passed.append(fn.__name__)
        except Exception as e:  # noqa: BLE001
            print(f"  XX   {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed.append(fn.__name__)
    print(f"\nPASS {len(passed)}  FAIL {len(failed)}")
    if failed:
        sys.exit(1)
    print("all solution-feasibility tests passed")


if __name__ == "__main__":
    main()
