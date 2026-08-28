"""Solar water heating - config, accessors and guards..

NO LP SOLVE. Everything here runs off the session-scoped `econ` / `net`
fixtures, so the whole file is seconds rather than minutes.

WHAT THESE TESTS ARE FOR. The technology was added flag-gated and OFF, on the
back of a verification that found nine errors in its first draft
(`_spec/SOLAR_THERMAL_VERIFICATION_20260817.md`). Four of those nine were
INTERNAL INCONSISTENCIES that a test would have caught immediately - a slice
table that did not sum to its own declared annual, a tank temperature that
contradicted the source it was validated against, and so on. So the emphasis
here is deliberately on cross-checks between numbers that must agree, not on
pinning values that are free to change.

The one test that matters most is `test_off_by_default`. Everything else in
this file could pass while the model quietly changed, if that one failed.
"""
from __future__ import annotations

import math

import pytest

# MNRE "User's Handbook on Solar Water Heaters" (2010) Table 8, Chandigarh row.
# NOTE THE COLUMN ORDER - it is the error that started the whole re-derivation:
# 16 C is the DAY AMBIENT and 12 C is the COLD WATER INLET, not the reverse.
MNRE_GTI_KWH_M2_DAY = 5.79
MNRE_AMBIENT_C = 16.0
MNRE_INLET_C = 12.0
MNRE_LITRES_PER_DAY = 94.0
MNRE_SETPOINT_C = 60.0
MNRE_COLLECTOR_M2 = 2.0
MNRE_TOLERANCE = 0.10          # the handbook's own stated +/- 10%

MONTHS = ("jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec")
DAYS = {"jan": 31, "feb": 28.25, "mar": 31, "apr": 30, "may": 31, "jun": 30,
        "jul": 31, "aug": 31, "sep": 30, "oct": 31, "nov": 30, "dec": 31}


def _st(econ):
    return econ.technologies["solar_thermal"]


def _on(econ):
    """Turn the config flag on IN MEMORY. Never writes YAML."""
    econ.technologies["solar_thermal"] = {**_st(econ), "enabled": True}


def _off(econ):
    econ.technologies["solar_thermal"] = {**_st(econ), "enabled": False}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
def test_on_in_production(econ):
    """PRODUCTION NOW SHIPS THIS TECHNOLOGY, AND THIS TEST GUARDS THAT.

    INVERTED. This asserted the opposite - "PRODUCTION MUST NOT SEE
    THIS TECHNOLOGY" - which was correct while solar water heating was a
    flag-gated experiment. It was RATIFIED into the design case on
    (register and the pins since carry 63,226 m2 of collector serving
    28.47 GWh/yr. The test was never updated, and nothing noticed for two days
    because `test_solar_thermal` is one of five modules that
    `f3_targeted_verify` did not run; that gap is now closed and guarded.

    The gate is still worth having, only pointing the other way: if production
    stops building collectors, every pinned number moves and this says so
    first.
    """
    assert _st(econ)["enabled"] is True
    assert econ.solar_thermal_enabled() is True
    sc = econ.scenario("full_stack")
    assert getattr(sc, "allow_solar_thermal", False) is True
    # BAU must still never see it - the counterfactual has no collectors, and
    # the 0.0 m2 leak check at the pins depends on this staying true.
    bau = econ.scenario("bau")
    assert getattr(bau, "allow_solar_thermal", False) is False


def test_accessors_are_inert_when_off(econ):
    """Every accessor returns a falsy/neutral value with the flag off.

    A single accessor that leaked a non-zero would be enough to move a pinned
    total, because these feed the demand balance.
    """
    _off(econ)
    assert econ.solar_thermal_kw_per_m2("jun_wd_12") == 0.0
    total = sum(econ.solar_thermal_kw_per_m2(s.id) * s.hours_per_year
                for s in econ.slices)
    assert total == 0.0


def test_roof_cap_is_zero_when_off(econ, net):
    _off(econ)
    assert net.solar_thermal_roof_cap_m2(econ) == 0.0
    assert net.water_heating_kwh_by_slice(econ) == {}


# ---------------------------------------------------------------------------
# Internal consistency - the class of error this file exists to catch
# ---------------------------------------------------------------------------
def test_slice_table_reproduces_declared_annual(econ):
    """The per-slice table and `annual_kwh_per_m2` must agree.

    They are written by the same derivation script but into different config
    keys, so nothing but a test stops them drifting apart.
    """
    st = _st(econ)
    tab = st["kw_per_m2_by_month_daypart"]
    derived = sum(v * 2.0 * DAYS[m] for m, row in tab.items()
                  for v in row.values())
    assert derived == pytest.approx(st["annual_kwh_per_m2"], abs=1.0)


def test_annual_via_slices_matches_annual_via_table(econ):
    """Walking the model's own 864 slices must give the same annual.

    This is the stronger version of the test above: it goes through
    `slice_by_id` and `hours_per_year`, i.e. the exact path the LP uses, so a
    daypart-naming mismatch between config and the slice objects would show up
    here as a shortfall rather than silently zeroing hours.
    """
    _on(econ)
    total = sum(econ.solar_thermal_kw_per_m2(s.id) * s.hours_per_year
                for s in econ.slices)
    assert total == pytest.approx(_st(econ)["annual_kwh_per_m2"], rel=0.01)
    _off(econ)


def test_collector_day_is_shorter_than_pv_day(econ):
    """January must produce nothing at 06-08 while PV still does.

    Not a curiosity - it is the cutoff irradiance G* = a1(Ti-Ta)/eta0 doing its
    job. A table copied from the PV shape would pass every other test in this
    file and quietly invent winter-morning hot water.
    """
    _on(econ)
    tab = _st(econ)["kw_per_m2_by_month_daypart"]
    assert tab["jan"]["06_08"] == 0.0
    assert tab["jan"]["16_18"] == 0.0
    assert tab["jan"]["12_14"] > 0.0
    assert econ.pv_daypart_shape_by_month["jan"]["06_08"] > 0.0
    _off(econ)


def test_yield_peaks_in_spring_and_troughs_in_january(econ):
    """Seasonality must run the OPPOSITE way to hot water demand.

    If this ever inverts, the mismatch that drives the whole sizing result has
    gone, and the result would be wrong in the flattering direction.
    """
    tab = _st(econ)["kw_per_m2_by_month_daypart"]
    daily = {m: sum(tab[m].values()) * 2.0 for m in MONTHS}
    assert min(daily, key=daily.get) == "jan"
    assert daily[max(daily, key=daily.get)] / daily["jan"] > 2.0


# ---------------------------------------------------------------------------
# Validation against the source
# ---------------------------------------------------------------------------
def test_curve_reproduces_mnre_measured_output(econ):
    """The IS 12933 curve must reproduce MNRE's MEASURED Chandigarh row.

    This is the check that makes the collector parameters defensible rather
    than merely cited. It is run at MNRE's OWN stated conditions (clear
    December day, ambient 16 C, inlet 12 C) and at the derived collector inlet
    (inlet+setpoint)/2, NOT at the 45 C that the first draft guessed - that
    guess missed by -11.2%, outside the handbook's own tolerance.

    Soiling is deliberately excluded: MNRE's row is a CLEAN collector on a
    CLEAR test day, so charging it a year of dust would compare two different
    things.
    """
    st = _st(econ)
    eta0 = float(st["eta0"])
    a1 = float(st["a1_w_per_m2_k"])
    b0 = float(st["iam_b0"])
    t_in = (MNRE_INLET_C + MNRE_SETPOINT_C) / 2.0

    measured_kwh_m2 = (MNRE_LITRES_PER_DAY * 4.186
                       * (MNRE_SETPOINT_C - MNRE_INLET_C) / 3600.0
                       / MNRE_COLLECTOR_M2)

    # Spread the clear-day total over a symmetric 8-hour window and integrate
    # the curve hour by hour, clamped at the cutoff. Coarser than the
    # derivation script, which is the point: the agreement should not depend
    # on the fine detail of the intraday shape.
    hours = [8, 9, 10, 11, 12, 13, 14, 15]
    weights = [math.cos((h + 0.5 - 12.0) / 8.0 * math.pi) for h in hours]
    weights = [max(0.0, w) for w in weights]
    wsum = sum(weights)
    out = 0.0
    for h, wt in zip(hours, weights):
        g = MNRE_GTI_KWH_M2_DAY * 1000.0 * wt / wsum
        theta = math.radians(abs(h + 0.5 - 12.0) * 15.0)
        k = max(0.0, 1.0 - b0 * (1.0 / max(0.2, math.cos(theta)) - 1.0))
        q = eta0 * k * g - a1 * (t_in - MNRE_AMBIENT_C)
        out += max(0.0, q) / 1000.0

    rel = out / measured_kwh_m2 - 1.0
    assert abs(rel) < 0.20, (
        f"curve gives {out:.3f} vs MNRE {measured_kwh_m2:.3f} kWh/m2/day "
        f"({rel:+.1%}). The derivation script agrees to +3.9%; a coarse "
        f"8-hour integration is allowed 20%."
    )


def test_annual_sits_inside_mnre_system_band(econ):
    """MNRE: a single-collector system saves "1800 KWh at the maximum and 900
    KWh at the minimum per year". At 2 m2 the derived annual must land in it.
    """
    st = _st(econ)
    system = st["annual_kwh_per_m2"] * st["m2_per_100_lpd"]
    assert 900.0 <= system <= 1800.0, system


# ---------------------------------------------------------------------------
# The DHW leg
# ---------------------------------------------------------------------------
def test_dhw_leg_recomposes_to_heating_split(econ, net):
    """dhw_only + space must reproduce `heating_split_factor` exactly.

    THE DRIFT GUARD. Solar thermal can only displace the water leg, so that
    leg is recomputed beside the production accumulator rather than extracted
    from it (the accumulator's float addition order is pin-sensitive). This is
    what keeps the two honest.
    """
    hl = econ.heating_loads or {}
    shares = hl.get("dhw_share_of_peak_by_category") or {}
    cats = sorted({n.category_name for n in net.nodes if n.category_name})
    worst = 0.0
    for cat in cats:
        f = float(shares.get(cat, 0.0))
        for s in econ.slices:
            d = econ.dhw_only_split_factor(cat, s.id)
            sp = ((1.0 - f) * econ.space_heating_month_factor(s.month)
                  * econ._heat_daypart("space_heating", cat, s.daypart))
            worst = max(worst,
                        abs((d + sp) - econ.heating_split_factor(cat, s.id)))
    assert worst < 1e-12, worst


def test_dhw_never_exceeds_total_heating(econ, net):
    """A category's water leg cannot be larger than its whole heating load."""
    for cat in sorted({n.category_name for n in net.nodes if n.category_name}):
        for s in econ.slices:
            d = econ.dhw_only_split_factor(cat, s.id)
            t = econ.heating_split_factor(cat, s.id)
            assert d <= t + 1e-12, (cat, s.id, d, t)
            assert d >= -1e-12, (cat, s.id, d)


def test_summer_heating_is_all_water(econ, net):
    """In June there is no space heating, so the two must be equal.

    A physical check the arithmetic cannot fake: if the split ever leaks space
    heating into a Punjab June, this catches it.
    """
    for cat in ("high_income_residential", "mid_income_residential"):
        a = econ.dhw_only_split_factor(cat, "jun_wd_20")
        b = econ.heating_split_factor(cat, "jun_wd_20")
        assert a == pytest.approx(b, rel=1e-9), (cat, a, b)


# ---------------------------------------------------------------------------
# Costs and ownership
# ---------------------------------------------------------------------------
def test_geyser_credit_reduces_capex_but_not_below_zero(econ):
    st = _st(econ)
    net_capex = econ.solar_thermal_capex_inr_per_m2()
    assert 0.0 < net_capex < float(st["capex_inr_per_m2"])
    expected = (float(st["capex_inr_per_m2"])
                - float(st["avoided_geyser_capex_inr_per_system"])
                / float(st["m2_per_100_lpd"]))
    assert net_capex == pytest.approx(expected)


def test_blended_rate_lies_between_its_components(econ):
    """The blend must sit inside the range of the tiers it blends.

    Cheap, and it catches a mis-keyed actor name, which would otherwise fall
    back to a default rate and look plausible.
    """
    st = _st(econ)
    rates = [econ.solar_thermal_annualised_inr_per_m2(a)
             for a in st["owner_weights"]]
    blended = econ.solar_thermal_blended_annualised_inr_per_m2()
    assert min(rates) <= blended <= max(rates)


def test_owner_weights_sum_to_one(econ):
    w = _st(econ)["owner_weights"]
    assert sum(float(v) for v in w.values()) == pytest.approx(1.0, abs=1e-9)


def test_every_eligible_category_has_an_owner(econ):
    st = _st(econ)
    for cat in st["eligible_categories"]:
        assert cat in st["owner_actors"], cat
        assert econ.actor_discount_rate(st["owner_actors"][cat]) > 0.0


def test_mandated_categories_are_all_eligible(econ):
    """A building the state COMPELS to install must be one the model allows."""
    st = _st(econ)
    for cat in st["mandated_categories"]:
        assert cat in st["eligible_categories"], cat


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def test_tank_retention_is_a_fraction_and_decays(econ):
    r0 = econ.solar_thermal_tank_retention(0.0)
    r8 = econ.solar_thermal_tank_retention(8.0)
    r24 = econ.solar_thermal_tank_retention(24.0)
    assert r0 == 1.0
    assert 0.0 < r24 < r8 < r0


def test_bucket_hold_is_the_calibrated_value_not_the_centroid(econ):
    """12.5 h, not the 10.8 h the draw centroid implies.

    The centroid derivation is 3.7% optimistic against the hour-by-hour tank
    in scripts/solar_thermal_match_simulation.py. If someone "simplifies" this
    back to the tidy geometric value, the LP silently gains 3.7% of storage.
    """
    hold = float(_st(econ)["bucket_average_hold_hours"])
    assert hold == pytest.approx(12.5, abs=0.1)
    assert econ.solar_thermal_tank_retention(hold) == pytest.approx(0.7755,
                                                                    abs=0.005)


def test_tank_store_is_sized_off_the_dhw_setpoint(econ):
    """The tank's usable energy must track the DHW block's own setpoint.

    Hard-coding 60 C here would let the two drift if the setpoint ballot is
    ever revisited.
    """
    _on(econ)
    st = _st(econ)
    dhw = econ.heating_loads["dhw"]
    expected = (float(st["tank_litres_per_m2_collector"]) * 4.186
                * (float(dhw["setpoint_c"]) - float(st["reference_inlet_c"]))
                / 3600.0)
    assert econ.solar_thermal_tank_kwh_per_m2() == pytest.approx(expected)
    _off(econ)


# ---------------------------------------------------------------------------
# The fallback guard
# ---------------------------------------------------------------------------
def test_scenario_is_frozen_and_must_be_replaced_not_mutated(econ):
    """`Scenario` is a frozen dataclass, and this cost real time to find.

    A structural proof written earlier set the flag with
    `sc.allow_solar_thermal = True` inside `try/except Exception: pass`. The
    assignment raised FrozenInstanceError, the except swallowed it, the flag
    stayed False, and the script reported PASS on a comparison that had tested
    nothing. This test exists so the next person reaches for
    `dataclasses.replace` instead.
    """
    import dataclasses
    sc = econ.scenario("full_stack")
    with pytest.raises(dataclasses.FrozenInstanceError):
        sc.allow_solar_thermal = True
    off = dataclasses.replace(sc, allow_solar_thermal=False)
    assert off.allow_solar_thermal is False
    assert sc.allow_solar_thermal is True       # original untouched
    # ( direction flipped with's ratification - production is
    # now ON, so the replace-test builds the OFF variant.)


def test_merit_order_fallback_refuses_solar_thermal(econ, net, monkeypatch):
    """The heuristic has no collector, no tank and no DHW leg.

    Its own docstring says it is "NOT number-compatible" with the Pyomo
    builders. Returning a quietly-incomplete answer would be worse than
    failing, so it must raise.
    """
    import dataclasses
    from energy.dispatch import solve_dispatch_fallback
    _on(econ)
    on = dataclasses.replace(econ.scenario("full_stack"),
                             allow_solar_thermal=True)
    monkeypatch.setattr(econ, "scenario", lambda name: on)
    try:
        with pytest.raises(NotImplementedError, match="merit-order fallback"):
            solve_dispatch_fallback(net, econ, "full_stack", alpha=0.0)
    finally:
        _off(econ)


def test_fallback_guard_state_in_production(econ):
    """Production runs with the technology ON.

    The heuristic fallback has no collector, no tank and no hot-water leg, so
    what matters is that production does not USE the fallback - not that the
    technology is off. `test_merit_order_fallback_refuses_solar_thermal` above
    covers the fallback's own refusal.
    """
    # ORDER-INDEPENDENT ON PURPOSE. The `econ` fixture is session-scoped
    # (tests/conftest.py:38) and `_off` MUTATES it in place, so any earlier
    # test in this file leaves the flag off for every later one. Reading the
    # config fresh is the only way to assert what PRODUCTION ships rather than
    # what the previous test left behind.
    from energy.costs import load_economics
    fresh = load_economics(force_reload=True)
    sc = fresh.scenario("full_stack")
    assert getattr(sc, "allow_solar_thermal", False) is True
    assert fresh.solar_thermal_enabled() is True
