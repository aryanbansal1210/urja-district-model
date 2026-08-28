"""B21 REGIONAL INTEGRATION tests.

Direct-runner style (NOT pytest): ``python tests/test_b21_regional.py``.
Covers the four B21 blocks (green_purchase / boundary_opex / interconnection
/ farm_land_rent - all default enabled: false) + the LP wiring in both
builders. Spec: _spec/next_sessions/B21_REGIONAL_INTEGRATION_SPEC.md.

Two tiers:
  FAST  - accessor arithmetic + gating (milliseconds; run anytime).
  SOLVE - (a) the byte-exact OFF gate: with every block at its YAML default
          the multi-period production pin must be BIT-IDENTICAL (proves the
          wiring is a true no-op); (b) a force-enabled green-purchase solve
          proving the mechanics (cost never worse than OFF + the standing
          admin; emissions never up; exports never up = no buy-to-export
          arbitrage; shared import ceiling respected).
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


# The forced-off provenance anchor: the multi-period headline with every
# B21 block disabled on the CURRENT layout.
# (born): 3_562_923_664.18 = the-patch production pin
#   (artifact f6_pin_discovery_20260710.txt).
# ANNEAL RUN 2 re-anchor): 3_562_923_664.18 ->
#   3_578_774_316.18 (the re-annealed layout + streetlight class weights;
#   artifact f6run2_off_anchor_20260711.txt). The B21 delta REPRODUCES on
#   the new town: ON - OFF = +79.46M cost / -16.84 Mt-kg CO2 (was +79.32M /
#   -16.83 on the old layout) - the boundary blocks are layout-robust.
# 3_578_774_316.18 -> 3_661_364_694.69. CONSISTENCY PROOF: the ON-OFF delta is
# +79,457,993 = the SAME +79.46M as at export 3.5 - the B21 boundary blocks are
# invariant to the export price line (they never touch export revenue), the
# third reproduction of the delta after layout and price-frame changes.
# 3_661_364_694.69 -> 3_781_547_812.45 (solver-true, suite
# solve; the crit2 discovery's 3_942_584_370.20 was a MISLABEL - that
# solve forced off ONLY green_purchase, i.e. the GP-option counterfactual
# the mechanics test measures, not the all-four-blocks pre-B21 world this
# anchor pins). The ON-OFF delta MOVES for the first time:
# +79,457,993.29 -> +72,451,225.82. Mechanism-consistent AND
# arithmetically PROVEN: the non-GP B21 blocks are period-constant lump
# sums, so delta_new = delta_old - (GP option value growth) =
# 79,457,993.29 - (88,585,331.93 - 81,578,564.46) = 72,451,225.82 to the
# paisa (GP values printed by test_green_purchase_on_mechanics in the
# rf2/crit2 suite logs). (tracked land ratio) cuts the farm's
# deliverable energy, the green-OA option is worth MORE on the thinner
# self-gen base (81.6M -> 88.6M), and the NET cost of the B21 boundary
# blocks falls by exactly that growth. Fourth reproduction of the
# B21 separation, now as a monotone response in both components.
# (infra_pin_discovery_20260811.txt). The B21 ON-OFF delta COLLAPSED
# +72,451,225.82 -> +12,858,282.32, an 82% fall. NOT a bug: the green
# option's value scales with the grid energy it displaces, and demand fell
# 43% while self-generation rose, so the town now imports 187 GWh. Cheaper
# batteries also substitute for it (the OFF run builds MORE battery,
# 607,099 vs 588,728 kWh). See FINDINGS/.
# CORRECTION (same day, before the value was ever quoted):
# 1,995,332,962.52 was WRONG for this test. That figure is the
# GREEN-PURCHASE-ONLY counterfactual from infra_pin_discovery, but
# `_force_b21_off` below disables FOUR blocks - green purchase,
# boundary opex, INTERCONNECTION and farm land rent. Two different
# counterfactuals; the discovery script only ever solved one of them.
# The correct all-B21-off anchor is this test's own measured value.
# B21's total worth on the new baseline = 1,982,474,680.20 -
# 1,903,322,632.01 = Rs 79,152,048.19/yr era: +72,451,225.82;
# it grew because the sized connection changed the interconnection
# component that this counterfactual removes).
# NOTE the internal-network parity charge is NOT a B21 block
# and is therefore paid on BOTH sides of this delta, by design.
# READ THE COUNTERFACTUAL DEFINITION BEFORE QUOTING ANY B21 DELTA. This
# test forces off FIVE things, not four: `set_ppa_enabled(False)` on the
# line above plus `_force_b21_off`'s four blocks. That mattered for the
# production - so the anchor sits on a PPA-OFF baseline and must be
# differenced against the PPA-OFF production run, NOT against production:
#     PPA off, B21 ON  = 2,121,528,359.54   (pin_probes_20260813.txt)
#     PPA off, B21 off = 2,014,941,615.59   <- _PIN_MULTI, this test
#     => B21's net cost = Rs 106,586,743.95/yr
# (era path +72.45M -> +79.15M -> +106.59M; it grows as the sized
# connection and the flat-295-ha Option A land rent both grow the charges
# this counterfactual removes.) A four-block-only probe gives
# 1,816,017,758.37 with the PPA left on - a DIFFERENT counterfactual, and
# the wrong-anchor lesson repeating in a new disguise: the
# number is only meaningful with its gate list attached.
# (+71,368.08). Layout only - the stub-connect road cell plus the
# car-park swap; the FIVE-GATE definition above is unchanged, so the delta
# against the PPA-off production run holds its meaning:
#     PPA off, B21 ON  = 2,121,599,445.68
#     PPA off, B21 off = 2,015,012,983.67   <- _PIN_MULTI, this test
#     => B21's net cost = Rs 106,586,462.01/yr  (was 106,586,743.95)
# Discovery prk6_pin_discovery_20260814.txt.
# (-124,526,526.27; the released 301-ha reserve makes even the five-gate-off
# counterfactual much cheaper). NOTE the delta differs from production's
# -153.9M because this counterfactual has NO farm land rent (it is one of the
# four forced-off blocks) - so it gains the capacity but never paid the rent:
#     PPA off, B21 ON  = 2,004,590,178.36
#     PPA off, B21 off = 1,890,486,457.40   <- _PIN_MULTI, this test
#     => B21's net cost = Rs 114,103,720.96/yr  (was 106,586,462.01)
# Discovery land_a1_pin_discovery_20260814.txt.
_PIN_MULTI = 1_882_777_547.49


# --------------------------------------------------------------------- FAST
def _force_b21_off(e) -> None:
    """Disable all four B21 blocks on ONE econ instance regardless of the
    YAML defaults (which are enabled: true since the flip) -
    the provenance lever for the pre-B21 pin."""
    e.set_green_purchase_enabled(False)
    for raw_key in ("boundary_opex_raw", "interconnection_raw",
                    "farm_land_rent_raw"):
        e.__dict__[raw_key] = {**(e.__dict__.get(raw_key) or {}),
                               "enabled": False}


def test_delivered_price_accessor_arithmetic() -> None:
    """EXACT compounding re-pin rider): gen x (1 + in-kind
    2%) / (1 - OA losses 4.00%) + CSS 0.85 + AS 0 = 2.97 x 1.0625 + 0.85
    = 4.005625 (PSPCL CC 10/2025 FY25-26 values; the additive 3.9982 era
    ended with the batch)."""
    e = load_economics(force_reload=True)
    got = e.green_purchase_delivered_price_inr_per_kwh()
    assert abs(got - 4.005625) < 1e-9, got


def test_disabled_blocks_are_zero() -> None:
    """With all four blocks forced OFF, every B21 accessor returns 0.0 ->
    the objective adders are exact no-ops (the pre-flip no-op claim,
    preserved as a provenance test after the flip)."""
    e = load_economics(force_reload=True)
    _force_b21_off(e)
    assert e.green_purchase_enabled() is False
    for y in (2030, 2042, 2055):
        assert e.boundary_opex_annual_inr(y) == 0.0, y
        assert e.farm_land_rent_annual_inr(y) == 0.0, y
    assert e.interconnection_annualised_inr() == 0.0


def test_boundary_opex_arithmetic() -> None:
    """residues_t x gate fee + canal kL x rate, per period (derivations in
    the economics.yaml boundary_opex block comments)."""
    e = load_economics(force_reload=True)
    e.__dict__["boundary_opex_raw"] = {
        **e.boundary_opex_config(), "enabled": True,
    }
    water = 4_312_969 * 5.0
    assert abs(e.boundary_opex_annual_inr(2030) - (2995 * 600 + water)) < 1.0
    assert abs(e.boundary_opex_annual_inr(2042) - (8470 * 600 + water)) < 1.0
    assert abs(e.boundary_opex_annual_inr(2055) - (14401 * 600 + water)) < 1.0


def test_land_rent_modes_arithmetic() -> None:
    """agricultural: granted ha x theka rate; market: ha x value x 5%.

 granted ha is now FLAT in every period (the author's OPTION A,
    `multi_period.farm_land_cells_by_period`), NOT the old B18 grant
    schedule 200/250/300. The whole belt is acquired and RENTED FROM THE
    START, because a land grant that arrives in tranches cannot be
    assembled later at agricultural prices - so the town pays for the
    whole belt from 2030 and the LP decides when to BUILD on it. The
    rates themselves are unchanged (theka Rs 250,000/ha/yr; market
    Rs 30,000,000/ha x 5%), so this test still checks the ARITHMETIC of
    both modes - only the hectare schedule moved.

 STALE-EXPECTATION FIX: the hectare count was hard-coded 295
    here and never updated when set the config to the layout's OWN
    301 solar-reserve cells (`farm_land_cells_by_period` 301/301/301, and
    the LP now actually reads it). The test was asserting a number the
    config had already left behind - the same seam itself was, one
    layer up. Probed agricultural returns 75,250,000 in all
    three periods and market returns 451,500,000 at 2030, both exactly 301
    ha. Read the count FROM the config rather than restating it, so this
    can never go stale again; the rates stay hard-coded because those are
    what the test is actually checking.
    """
    e = load_economics(force_reload=True)
    base = e.farm_land_rent_config()
    _mp = dict(e.__dict__.get("multi_period_raw", {}) or {})
    _ha = dict(_mp.get("farm_land_cells_by_period", {}) or {})
    assert _ha, "multi_period.farm_land_cells_by_period is missing"
    e.__dict__["farm_land_rent_raw"] = {**base, "enabled": True,
                                        "mode": "agricultural"}
    for _y in (2030, 2042, 2055):
        _n = float(_ha[str(_y)])
        assert abs(e.farm_land_rent_annual_inr(_y) - _n * 250_000) < 1.0, _y
    e.__dict__["farm_land_rent_raw"] = {**base, "enabled": True,
                                        "mode": "market"}
    assert abs(e.farm_land_rent_annual_inr(2030)
               - float(_ha["2030"]) * 30_000_000 * 0.05) < 1.0


def test_interconnection_crf_arithmetic() -> None:
    """capex x CRF(utility rate, 35 y) when force-enabled; sanity band
    Rs 7-14 cr/yr for the Rs 120 cr class."""
    e = load_economics(force_reload=True)
    e.__dict__["interconnection_raw"] = {
        **e.interconnection_config(), "enabled": True,
    }
    got = e.interconnection_annualised_inr()
    assert 7.0e7 < got < 1.4e8, got


def test_scenario_gating() -> None:
    """full_stack carries allow_green_purchase; the counterfactuals do not
    (BAU stays grid-only; pv_* stay dumb) - the/ comparison logic."""
    e = load_economics(force_reload=True)
    assert e.scenario("full_stack").allow_green_purchase is True
    assert e.scenario("bau").allow_green_purchase is False
    assert e.scenario("pv_only").allow_green_purchase is False


# -------------------------------------------------------------------- SOLVE
def test_off_is_byte_exact() -> None:
    """THE PROVENANCE ANCHOR: with every B21 block FORCED off, the
    multi-period headline is BIT-IDENTICAL to _PIN_MULTI (the no-B21
    counterfactual on the CURRENT layout; see the _PIN_MULTI comment for
    the anchor history) - proving the B21 blocks, and ONLY the B21
    blocks, separate the production baseline from its counterfactual."""
    if not has_pyomo():
        _skip("pyomo not installed - LP path not exercised")
    e = deepcopy(load_economics(force_reload=True))
    e.set_ppa_enabled(False)
    _force_b21_off(e)
    net = load_optimised_network()
    r = solve_dispatch_pyomo(net, e, scenario_name="full_stack", alpha=0.0)
    assert abs(r.annual_cost_inr - _PIN_MULTI) < 1.0, r.annual_cost_inr
    assert r.__dict__.get("green_purchase_kwh", 0.0) == 0.0


def test_green_purchase_on_mechanics() -> None:
    """Force-enable ONLY green_purchase (production config otherwise):
    (a) cost never rises beyond OFF + the standing OA admin;
    (b) emissions never rise (green EF 0 displaces grey import);
    (c) exports never rise vs OFF (delivered 4.00 > feed-in 3.5 makes
        buy-to-export strictly unprofitable - asserted, not constrained);
    (d) shared substation ceiling: (import + green)/h <= 600 MW everywhere;
    (e) the by_slice export carries green_purchase_kwh consistent with the
        headline total."""
    if not has_pyomo():
        _skip("pyomo not installed - LP path not exercised")
    net = load_optimised_network()
    # Isolate the PURCHASE mechanics: all four blocks forced off in the
    # baseline; ONLY green_purchase re-enabled in the treatment (the other
    # three are period-constants and would cancel anyway - forced off for
    # a clean A/B regardless of the YAML flip state).
    e_off = deepcopy(load_economics(force_reload=True))
    e_off.set_ppa_enabled(False)
    _force_b21_off(e_off)
    r_off = solve_dispatch_pyomo(net, e_off, scenario_name="full_stack",
                                 alpha=0.0)
    e_on = deepcopy(load_economics(force_reload=True))
    e_on.set_ppa_enabled(False)
    _force_b21_off(e_on)
    e_on.set_green_purchase_enabled(True)
    r_on = solve_dispatch_pyomo(net, e_on, scenario_name="full_stack",
                                alpha=0.0)
    admin = e_on.green_purchase_annual_admin_inr()
    # (a) CORRECTED - THE PRINCIPLE WAS RIGHT, THE QUANTITY WAS WRONG.
    # The reasoning "an LP given one MORE option can only improve, minus the
    # fixed fee" is sound and provable HERE: the model carries no integer or
    # binary variables (pure LP), `gp`/`gp_mw` are bounded (0, ub) so they can
    # sit at zero, and `gp_shared_import_cap` has the IDENTICAL right-hand side
    # to `imp_cap` (`_conn_kw(m) * hours`, both with the same RES-1 month
    # multiplier), so at gp = 0 the constraint set is unchanged and the feasible
    # region strictly EXPANDS. The optimum therefore cannot rise.
    # But the assert was applied to `annual_cost_inr`, which is NOT what the LP
    # minimises. The multi-period objective is `m.lifetime_cost_expr`
    # (dispatch.py m.cost, alpha=0 here); `annual_cost_inr` is the BASE-YEAR
    # slice, reported not optimised. A cheaper LIFETIME plan is free to cost
    # MORE in 2030 - build earlier, re-phase, spend now to save later - so
    # base-year monotonicity was never guaranteed by anything.
    # (chain step 5, and reproduced by a standalone probe):
    # annual ON 1,972,812,234.01 vs OFF 1,954,489,052.94 = +18,323,181.08,
    # i.e. the base year legitimately rises. THE MODEL WAS RIGHT AND THE TEST
    # WAS WRONG - the fourth instance of the seam pattern this month
    # (see also PPA-BAU-1, PPA-PRICE-1).
    # The guarantee is now asserted where it actually holds - on the objective.
    # `admin` is an ANNUAL fee, so over the lifetime it is charged once per
    # period-weighted year; bounding by the annual figure alone would be too
    # tight, hence the explicit period weighting.
    assert r_on.lifetime_cost_inr <= r_off.lifetime_cost_inr + admin * 30.0, (
        "adding the green-purchase option RAISED the LP's own objective, which "
        "is impossible for a pure LP whose feasible region only expands - "
        "check that enabling green_purchase has not tightened a constraint",
        r_on.lifetime_cost_inr, r_off.lifetime_cost_inr,
        r_on.lifetime_cost_inr - r_off.lifetime_cost_inr)
    #...and the base year is still REPORTED, so a silent blow-up is visible.
    # Band, not a bound: this is not an optimised quantity.
    _ann_delta = r_on.annual_cost_inr - r_off.annual_cost_inr
    assert abs(_ann_delta) < 0.05 * r_off.annual_cost_inr, (
        "base-year cost moved more than 5% when green purchase was enabled - "
        "not necessarily wrong (it is not the objective) but re-read the "
        "period phasing before accepting it", _ann_delta, r_off.annual_cost_inr)
    # (b)
    assert r_on.annual_emissions_kgco2 <= r_off.annual_emissions_kgco2 + 50.0, (
        r_on.annual_emissions_kgco2, r_off.annual_emissions_kgco2)
    # (c)
    assert r_on.grid_export_kwh <= r_off.grid_export_kwh + 1.0, (
        r_on.grid_export_kwh, r_off.grid_export_kwh)
    # (d) + (e)
    imp_cap = e_on.import_capacity_limit_kw()
    gp_total = 0.0
    for sid, b in r_on.by_slice.items():
        gp_total += b.get("green_purchase_kwh", 0.0)
    assert abs(gp_total - r_on.__dict__.get("green_purchase_kwh", 0.0)) < 1.0
    # slice-hours map via the exported slices is not on the result; the
    # shared-cap LP constraint enforced it - here we spot-check the
    # aggregate never exceeds cap x 8760 as a coarse guard.
    assert (r_on.grid_import_kwh + gp_total) <= imp_cap * 8760 * 1.0001
    # (units fix kWh/1e6 = GWh; the first run printed /1e9 and
    # briefly misled the mechanism story - see the b21_mechanism_diagnostic)
    print(f"    [b21] green purchase bought {gp_total/1e6:.1f} GWh "
          f"(2030 base year); cost delta "
          f"{r_on.annual_cost_inr - r_off.annual_cost_inr:+,.0f} INR/yr")


def main() -> None:
    import time
    fast = [test_delivered_price_accessor_arithmetic,
            test_disabled_blocks_are_zero,
            test_boundary_opex_arithmetic,
            test_land_rent_modes_arithmetic,
            test_interconnection_crf_arithmetic,
            test_scenario_gating]
    solve = [test_off_is_byte_exact, test_green_purchase_on_mechanics]
    only_fast = "--fast" in sys.argv
    n_pass = n_fail = n_skip = 0
    for fn in fast + ([] if only_fast else solve):
        t0 = time.time()
        try:
            fn()
            n_pass += 1
            print(f"PASS  {fn.__name__} ({time.time()-t0:.1f}s)", flush=True)
        except _Skipped as exc:
            # A test that could not run is reported as SKIP, never as PASS.
            n_skip += 1
            print(f"SKIP  {fn.__name__}: {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001
            n_fail += 1
            print(f"FAIL  {fn.__name__} ({time.time()-t0:.1f}s)\n"
                  f"      {type(exc).__name__}: {exc}", flush=True)
    print(f"\nTOTAL pass {n_pass} fail {n_fail} skip {n_skip}"
          + ("  [--fast: solve tests skipped]" if only_fast else ""))
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    _AS_SCRIPT = True          # route _skip through _Skipped, not pytest
    main()
