"""Phase 4 — equity + P2P trading report tests.

Direct-runner style (NOT pytest): ``python tests/test_equity_report.py``.
Mirrors the project convention (each ``test_*`` raises AssertionError on
failure; ``main`` runs them all and prints PASS/FAIL).

The report is a REPORT-ONLY transfer layer, so the headline assertions here
guard that NONE of the Phase-4 edits (the ``equity_report`` config block +
``Economics.equity_report_config`` accessor + the new module) perturbed the
cost-minimisation LP. A single-period solve is used (fast, ~70s) and CACHED so
every test reuses it.
"""

from __future__ import annotations

import os
import sys
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics                       # noqa: E402
from energy.network import load_optimised_network             # noqa: E402
from energy.dispatch import has_pyomo, solve_dispatch_pyomo   # noqa: E402
from energy.equity_report import (                            # noqa: E402

    build_equity_report,
    write_equity_report_json,
)

# --- skip plumbing ----------------------------------------------------
# These files run BOTH under pytest and directly as scripts (see the
# __main__ runner at the bottom), and the canonical pyomo env has no
# pytest -- so the import must not be load-bearing.
try:
    import pytest
except ModuleNotFoundError:          # direct-script run in the pyomo env
    pytest = None                    # type: ignore[assignment]

_AS_SCRIPT = False                   # set True by the __main__ runner


class _Skipped(Exception):
    """A test that could not run. Never reported as a pass."""


def _skip(reason: str):
    """Report an un-runnable test as SKIPPED rather than passed.

    Under pytest this defers to ``pytest.skip`` so the skip appears in the
    summary line. Run as a plain script it raises ``_Skipped``, which the
    runner reports as SKIP. A bare ``return`` here is exactly what let a
    70-test suite report green while exercising zero LP code, so the one
    thing this must never do is nothing.
    """
    if pytest is not None and not _AS_SCRIPT:
        pytest.skip(reason)
    raise _Skipped(reason)

# Single-period byte-exact pin (from test_energy_milp.test_d1b_multi_period_off,
# ownership correction). Guards that the Phase-4 edits left the LP
# untouched.
# 49_166_878.95 -> 41_487_917.60 (from the suite's discovered actuals).
# 41_487_917.60 -> 44_702_239.98 (single-period 2030: demand -9.4% cuts cost but
# the FX-5 EF premium + FX-4 cheaper winter evenings raise 2030 grid-import CO2).
# emissions 44_702_239.98 -> 44_524_263.22 (NASA satellite PV shape: less
# winter PV, more monsoon PV; E-W rooftop yield 0.86).
# (-3.2%: FX-14 tracked capex 1.12 + REV-2 EV smart charging + streetlight
# seasonal shape) and emissions 44_524_263.22 -> 44_505_346.84 (-0.04%).
# 2_989_689_891.05 and 44_505_346.84 -> 119_603_221.63. The town changed
# scale: 250k design population / 100 m grid / FAR floor stock / GSA
# single-source solar (v4 monthly + v5 per-month dayparts) / 350-cell
# solar land ceiling. Discovery artifact:
# "final 200 m model" pins remain on record as the low-density comparison.
# 3_465_486_624.72 and 119_603_221.63 -> 151_087_184.62. Production
# re-anneal (15k iters, seed 42) with B18 phased land: the 2030 solar
# grant halves 350 -> 201 cells so the 2030-only model swaps ~70 MWp of
# farm PV for grid import; parking 75 -> 17 lots (fleet-constrained).
# and 151_087_184.62 -> 151_004_299.16 (-0.16% / -0.05%).
# re-stamps (farm orphan absorbed, +0.025% alone from honest shading)
# + Patch B TRUE 3-tier heights (floor-conserving; roof area follows
# floors per -> rooftop ceiling +2.4% = the net saving; HH
# 54,420 -> 54,380, -0.074%). Discovery artifact:
# 3_459_998_489.52 -> 3_539_322_065.65 and 151_004_299.16 ->
# 141_145_251.59 (+2.29% cost / -6.5% CO2). Buy-side green OA purchase at
# Rs 4.00 delivered + interconnection 8.77 cr + boundary opex 2.34 cr +
# re-anneal (locked highstreet chain / hospital campus / solar ring /
# agri band, amenity re-targets, parking-stamper fix, park-shape +
# singleton SA terms) + streetlights-per-road-class flipped ON in the
# verify 12/12 + 22/22. Also this session (AUD-2/: the PMSGY rooftop
# attribution now uses the 2030 period build, not end-of-horizon.
# artifacts). 3_557_468_022.74 -> 3_640_029_350.64; 141_263_816.55 -> 137_171_818.75
# (less export value -> single-period re-optimises toward self-use; multi emis
# unchanged to the paisa).
# single now equals the multi 2030 value exactly (the old gap was the
# module-mix artifact); emissions +4.5% (all-fixed farm -> more
# 2030 import at the trajectory-average EF).
# SINGLE-period values - the equity report runs the single-bus path.
# PPA on in production + farm density 0.0714/Option A + the frozen-layout
# surgical patches (solar-estate road box + orphan road fix).
# two frozen-layout edits that both landed AFTER the pins and regen -
# the stub-connect cell (9,17) open_space -> ROAD and the
# car-park swap (12,28) <-> (12,26). Land-use counts and households (54,794) are
# exactly conserved, so this is a POSITION effect: +200 m of cable plus the moved
# building's facade/adjacency. Cost +70,148.25 (+0.0033%), CO2 +1,707.66.
# rent config moved 295 -> 301 ha). Emissions UNCHANGED: the single-period path
# reads the base 201-cell farm ceiling and never sees the released reserve
# (multipliers are multi-period-only; register, so rent is its only
# term and rent has no emissions.
# 1.00 flat + roof pair + farm density 0.08022; FINDINGS.
# Single-period moved too: it reads the 2030 land + density like multi does.
_PIN_ANNUAL = 2_059_143_602.74
_PIN_EMISSIONS = 72_658_646.64

_CACHE: dict = {}


def _solved():
    """Solve single-period full_stack a=0 ONCE; cache (net, econ, result, report)."""
    if "report" in _CACHE:
        return _CACHE
    econ = deepcopy(load_economics(force_reload=True))
    econ.__dict__["multi_period_raw"] = {
        **dict(econ.__dict__.get("multi_period_raw", {}) or {}),
        "enabled": False,
    }
    net = load_optimised_network()
    result = solve_dispatch_pyomo(net, econ, scenario_name="full_stack", alpha=0.0)
    report = build_equity_report(net, econ, result)
    _CACHE.update(net=net, econ=econ, result=result, report=report)
    return _CACHE


# --------------------------------------------------------------------------- #
def test_production_lp_unchanged_byte_exact() -> None:
    """The equity_report config + accessor must NOT touch the LP optimum."""
    if not has_pyomo():
        _skip("pyomo not installed - LP path not exercised")
    c = _solved()
    r = c["result"]
    # (FINDINGS / register PPA-PRICE-1): BOTH pins are checked
    # and BOTH are reported. Previously the cost assert fired first and the
    # EMISSIONS pin below was never evaluated - it sat stale and unseen
    # through three re-pins, and was only measured when the cost assert
    # happened to pass. An assert hidden behind a failing assert is not a
    # test. Collect, then fail once with everything that is wrong.
    bad = []
    if abs(r.annual_cost_inr - _PIN_ANNUAL) >= 5.0:
        bad.append(("annual_cost_inr", r.annual_cost_inr, _PIN_ANNUAL,
                    r.annual_cost_inr - _PIN_ANNUAL))
    if abs(r.annual_emissions_kgco2 - _PIN_EMISSIONS) >= 50.0:
        bad.append(("annual_emissions_kgco2", r.annual_emissions_kgco2,
                    _PIN_EMISSIONS, r.annual_emissions_kgco2 - _PIN_EMISSIONS))
    assert not bad, ("single-period pins moved (field, got, pinned, delta)", bad)


def test_equity_report_reconciles_to_demand() -> None:
    """Per-class consumption ties to the aggregate by_slice demand."""
    if not has_pyomo():
        _skip("pyomo not installed - LP path not exercised")
    rep = _solved()["report"]
    rel = rep["reconciliation"]["consumption_vs_aggregate_demand_rel_err"]
    assert rel < 0.02, rel  # within the Phase-1 attribution tolerance


def test_p2p_volume_and_value_bounded() -> None:
    """P2P volume in [0, consumption]; buyer saving + seller gain >= 0."""
    if not has_pyomo():
        _skip("pyomo not installed - LP path not exercised")
    rep = _solved()["report"]
    p = rep["p2p"]
    cons = rep["totals"]["consumption_kwh"]
    assert 0.0 <= p["annual_volume_kwh"] <= cons, p["annual_volume_kwh"]
    assert p["annual_buyer_saving_inr"] >= 0.0, p["annual_buyer_saving_inr"]
    assert p["annual_seller_gain_inr"] >= 0.0, p["annual_seller_gain_inr"]
    # a copper-plate town with daytime rooftop surplus should trade something
    assert p["annual_volume_kwh"] > 0.0, "expected some midday P2P trading"


def test_ews_social_discount_positive() -> None:
    """The EWS social tariff (Rs 3) must be a genuine discount vs the PSPCL
    first slab, and the gov absorbs the gap (the equity transfer)."""
    if not has_pyomo():
        _skip("pyomo not installed - LP path not exercised")
    rep = _solved()["report"]
    e = rep["ews_equity"]
    assert e["social_tariff_inr_per_kwh"] < e["pspcl_first_slab_comparator_inr_per_kwh"]
    assert e["annual_discount_vs_first_slab_inr"] > 0.0, e
    assert e["annual_bill_at_social_tariff_inr"] < e["annual_bill_at_first_slab_inr"]


def test_prosumer_savings_nonnegative() -> None:
    """Owning rooftop + trading P2P should never make a class worse off than
    BAU (buy everything from the grid at retail)."""
    if not has_pyomo():
        _skip("pyomo not installed - LP path not exercised")
    rep = _solved()["report"]
    for klass, c in rep["by_class"].items():
        assert c["savings_vs_bau_inr"] > -1.0, (klass, c["savings_vs_bau_inr"])


def test_pmsgy_attribution_is_progressive() -> None:
    """: the per-tier effective PMSGY subsidy fraction must be progressive
    (low >= mid >= high) — the Rs 78k cap covers more of a small system."""
    if not has_pyomo():
        _skip("pyomo not installed - LP path not exercised")
    rep = _solved()["report"]
    attr = rep["pmsgy_attribution"]["by_tier_f16"]
    low = attr.get("ews", {}).get("effective_capex_subsidy_fraction", 0.0)
    mid = attr.get("mid_residential", {}).get("effective_capex_subsidy_fraction", 0.0)
    high = attr.get("high_residential", {}).get("effective_capex_subsidy_fraction", 0.0)
    assert low >= mid >= high > 0.0, (low, mid, high)


def test_report_json_round_trips() -> None:
    """The report serialises to JSON and reloads with the headline sections."""
    if not has_pyomo():
        _skip("pyomo not installed - LP path not exercised")
    import json
    import tempfile

    rep = _solved()["report"]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "equity_report.json")
        write_equity_report_json(rep, path)
        with open(path, encoding="utf-8") as f:
            back = json.load(f)
    for key in ("meta", "totals", "p2p", "by_class", "ews_equity",
                "pmsgy_attribution", "n9_v2g_placement", "n10_diversity"):
        assert key in back, key


def main() -> None:
    import time
    import traceback

    fns = [v for k, v in sorted(globals().items())
           if callable(v) and k.startswith("test_")]
    passed, failed, skipped = [], [], []
    t0 = time.time()
    for fn in fns:
        t = time.time()
        try:
            fn()
            print(f"  OK   {fn.__name__}  ({time.time()-t:.1f}s)")
            passed.append(fn.__name__)
        except _Skipped as e:
            # A test that could not run is reported as SKIP, never as OK.
            print(f"  SKIP {fn.__name__}: {e}")
            skipped.append(fn.__name__)
        except Exception as e:  # noqa: BLE001
            print(f"  XX   {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed.append(fn.__name__)
    print(f"\nPASS {len(passed)}  FAIL {len(failed)}  "
          f"SKIP {len(skipped)}  ({time.time()-t0:.0f}s)")
    if skipped:
        print(f"  SKIPPED (did NOT run): {skipped}")
    if failed:
        sys.exit(1)
    print("all equity_report tests passed")


if __name__ == "__main__":
    _AS_SCRIPT = True          # route _skip through _Skipped, not pytest
    main()
