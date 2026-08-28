"""DIRECTIONAL (metamorphic) property tests -.

WHY THESE EXIST, AND WHY PINS ARE NOT ENOUGH.

The 334 headline pins answer "did the number change?" That is regression
detection, not correctness. This project's own history shows the gap: and
 were two errors of 2.3x and 2.5x in OPPOSITE directions, and the
top-down per-capita total check reconciled and RATIFIED both of them. What
caught them was a SHAPE - the PSPCL summer:winter ratio.

So these tests assert SHAPES and RELATIONSHIPS that must hold for ANY
parameterisation. They cannot be satisfied by tuning one number, and unlike a
pin they do not need updating when the model legitimately re-baselines.

The warming test is the one that would have caught on day one: under the
old flat multiplier, +2 C of global warming raised JANUARY demand by 3%.

Run fast subset only:   pytest tests/test_directional_properties.py -m "not slow"
Everything:             pytest tests/test_directional_properties.py

Measured reference values at the time of writing (/08, demand
559.33 GWh): cooling 184.21 GWh = 32.9% of demand; July warming uplift
+9.54% vs January +0.000%; load 22,001 -> 126,164 kW (peak/trough 5.73);
marginal cost 2.83 (midday) -> 7.70 (evening) INR/kWh; all four capacities
unique optima within 0.08%. Those are context, NOT assertions - the
assertions below are deliberately loose so only a real inversion trips them.
"""
from __future__ import annotations

import pytest

from energy.dispatch import has_pyomo

SUMMER = ("may", "jun", "jul", "aug")
WINTER = ("dec", "jan", "feb")


def _by_month(table, slices_by_id, months):
    return sum(v for sid, v in table.items()
               if slices_by_id[sid].month in months)


# ---------------------------------------------------------------- demand side
# These need the network but NOT a solve, so they are cheap once the
# session-scoped `net` fixture has been built.

def test_warming_raises_summer_cooling_not_winter_demand(net, econ):
    """: warming must raise COOLING, and must barely move January.

    Warming raises cooling and lowers heating. It does not raise winter
    demand. The pre- flat multiplier failed exactly here.
    """
    slices_by_id = {s.id: s for s in econ.slices}
    demand = net.demand_by_slice_kwh(econ)
    cooling = net.cooling_kwh_by_slice(econ)

    uplift = econ.cooling_warming_multiplier(2055) - 1.0
    assert uplift > 0, "no warming uplift configured; test is vacuous"

    jan_pct = 100.0 * uplift * _by_month(cooling, slices_by_id, ("jan",)) \
        / _by_month(demand, slices_by_id, ("jan",))
    jul_pct = 100.0 * uplift * _by_month(cooling, slices_by_id, ("jul",)) \
        / _by_month(demand, slices_by_id, ("jul",))

    assert jul_pct > jan_pct + 0.5, (
        f"warming must hit July harder than January: "
        f"Jul {jul_pct:+.3f}% vs Jan {jan_pct:+.3f}%"
    )
    assert abs(jan_pct) < 0.5, (
        f"warming moved January demand by {jan_pct:+.3f}% - it should be ~0. "
        "This is the PA-C6 defect returning (a flat multiplier on all demand)."
    )


def test_cooling_is_summer_weighted(net, econ):
    """Cooling must be concentrated in summer, not spread flat."""
    slices_by_id = {s.id: s for s in econ.slices}
    cooling = net.cooling_kwh_by_slice(econ)
    c_sum = _by_month(cooling, slices_by_id, SUMMER)
    c_win = _by_month(cooling, slices_by_id, WINTER)
    assert c_sum > 0, "no summer cooling at all"
    # Punjab winter has no AC load, so c_win is legitimately ~0. Assert the
    # direction without dividing by something that can be zero.
    assert c_sum > 20.0 * max(c_win, 1.0), (
        f"cooling not summer-weighted: summer {c_sum/1e6:.2f} GWh vs "
        f"winter {c_win/1e6:.2f} GWh"
    )


def test_removing_cooling_collapses_summer_not_winter(net, econ):
    """Zeroing the cooling peaks must gut summer and barely touch winter."""
    slices_by_id = {s.id: s for s in econ.slices}
    demand = net.demand_by_slice_kwh(econ)
    cooling = net.cooling_kwh_by_slice(econ)
    drop_sum = 100.0 * _by_month(cooling, slices_by_id, SUMMER) \
        / _by_month(demand, slices_by_id, SUMMER)
    drop_win = 100.0 * _by_month(cooling, slices_by_id, WINTER) \
        / _by_month(demand, slices_by_id, WINTER)
    assert drop_sum > 3.0 * max(drop_win, 0.1), (
        f"cooling share should be far larger in summer: "
        f"summer {drop_sum:.1f}% vs winter {drop_win:.1f}%"
    )


def test_demand_shape_is_not_flat(net, econ):
    """The guard as a property: the load curve must have real structure.

    Zero-hour slices are EXCLUDED. 48 of the 864 slices are festival
    day-types in months with no festival days, so `hours_per_year` is 0 and
    dividing by them produces a meaningless ratio (the first version of this
    test reported 1.26e14 and could not fail).
    """
    live = [s for s in econ.slices if s.hours_per_year > 0]
    assert len(live) > 0
    demand = net.demand_by_slice_kwh(econ)
    kw = sorted(demand[s.id] / s.hours_per_year for s in live)
    assert kw[0] > 1.0, (
        f"a live slice draws {kw[0]:.3f} kW - a district always has base load"
    )
    assert kw[-1] / kw[0] > 2.0, (
        f"load curve is nearly flat (peak/trough {kw[-1]/kw[0]:.2f}) - the F9 "
        "class of defect"
    )


def test_cooling_never_exceeds_total_demand(net, econ):
    """Sanity on the subtraction that isolates cooling: it cannot exceed the
    total, and cannot go negative, in any slice."""
    demand = net.demand_by_slice_kwh(econ)
    cooling = net.cooling_kwh_by_slice(econ)
    for sid, c in cooling.items():
        assert c >= -1e-6, f"negative cooling in {sid}: {c}"
        assert c <= demand[sid] + 1e-6, (
            f"cooling {c} exceeds total demand {demand[sid]} in {sid}"
        )


# ------------------------------------------------------------------ solve side
# Each of these costs a model build + solve (~2 min). Marked slow.

def _solve(net, econ, mutate=None):
    """Build + solve multi-period full_stack on a (optionally mutated) econ."""
    from copy import deepcopy
    import pyomo.environ as pyo
    from energy.costs import load_economics
    from energy.dispatch import (
        _build_pyomo_model_multi_period, _solve_pyomo,
    )
    e = deepcopy(load_economics(force_reload=True))
    if mutate is not None:
        mutate(e)
    model, periods, sids, _h, _w = _build_pyomo_model_multi_period(
        net, e, e.scenario("full_stack"), alpha=0.0)
    _solve_pyomo(model)
    obj = [o for o in model.component_objects(pyo.Objective, active=True)][0]
    base_year = int(e.multi_period_base_year())
    last = max(periods)
    return {
        "obj": float(pyo.value(obj)),
        "imp": sum(float(pyo.value(model.imp[base_year, s])) for s in sids),
        "pv": float(pyo.value(model.rooftop_installed[last])
                    + pyo.value(model.farm_fixed_installed[last])),
    }


@pytest.mark.slow
def test_dearer_power_does_not_raise_grid_import(net, econ):
    """Double the import tariff: grid import must not RISE, cost must."""
    if not has_pyomo():
        pytest.skip("pyomo not installed - LP path not exercised")
    base = _solve(net, econ)

    def double_tariff(e):
        for k in list(e.grid["import_tariff_inr_per_kwh"]):
            e.grid["import_tariff_inr_per_kwh"][k] *= 2.0

    dear = _solve(net, econ, double_tariff)
    assert dear["imp"] <= base["imp"] * 1.0001, (
        f"dearer power RAISED grid import: {base['imp']:,.0f} -> "
        f"{dear['imp']:,.0f} kWh"
    )
    assert dear["obj"] > base["obj"], "dearer power did not raise total cost"


@pytest.mark.slow
def test_expensive_pv_shrinks_the_pv_build(net, econ):
    """10x PV capex must SHRINK the build.

    Note the asymmetry: making PV *cheaper* cannot grow it, because both
    fleets already sit at their geometric caps (all usable roof, all granted
    land). So the informative direction is the expensive one. Rooftop capex
    must be moved via `module_types`, NOT the aggregate `capex_inr_per_kwp`,
    which is a derived summary the production path never reads.
    """
    if not has_pyomo():
        pytest.skip("pyomo not installed - LP path not exercised")
    base = _solve(net, econ)

    def dear_pv(e):
        for m in (e.technologies["rooftop_pv"].get("module_types") or {}).values():
            m["capex_inr_per_kwp"] = float(m["capex_inr_per_kwp"]) * 10.0
        e.technologies["rooftop_pv"]["capex_inr_per_kwp"] *= 10.0
        e.technologies["solar_farm"]["capex_inr_per_kwp"] *= 10.0

    dear = _solve(net, econ, dear_pv)
    assert dear["pv"] < base["pv"] * 0.999, (
        f"10x PV capex did not shrink the build: {base['pv']:,.0f} -> "
        f"{dear['pv']:,.0f} kWp"
    )
    assert dear["obj"] > base["obj"], "expensive PV did not raise total cost"


@pytest.mark.slow
def test_capacities_are_unique_optima_not_degenerate(net, econ):
    """Optimal-face check: fix the objective at its optimum, then minimise and
    maximise each capacity. A wide range at identical cost would mean the LP is
    indifferent and the reported build is an arbitrary vertex.

    This is the rigorous form of the battery question ("757 MWh
    built, 0 kWh cycled"), and it needs no second solver. Measured ranges at
    the time of writing: battery 0.08%, rooftop / farm / v2g 0.00%.
    """
    if not has_pyomo():
        pytest.skip("pyomo not installed - LP path not exercised")
    import pyomo.environ as pyo
    from energy.dispatch import (
        _build_pyomo_model_multi_period, _solve_pyomo,
    )
    model, periods, sids, _h, _w = _build_pyomo_model_multi_period(
        net, econ, econ.scenario("full_stack"), alpha=0.0)
    _solve_pyomo(model)
    obj = [o for o in model.component_objects(pyo.Objective, active=True)][0]
    obj_star = float(pyo.value(obj))
    last = max(periods)

    targets = {
        "battery_kwh": model.battery_installed[last],
        "rooftop_kwp": model.rooftop_installed[last],
        "farm_fixed_kwp": model.farm_fixed_installed[last],
    }
    baseline = {k: float(pyo.value(v)) for k, v in targets.items()}

    model._degen_bound = pyo.Constraint(
        expr=obj.expr <= obj_star + abs(obj_star) * 1e-7 + 1.0)
    obj.deactivate()
    try:
        for name, var in targets.items():
            span = {}
            for sense, tag in ((pyo.minimize, "lo"), (pyo.maximize, "hi")):
                model._degen_obj = pyo.Objective(expr=var, sense=sense)
                _solve_pyomo(model)
                span[tag] = float(pyo.value(var))
                model.del_component(model._degen_obj)
            base = baseline[name]
            if base <= 1e-9:
                continue
            rng = (span["hi"] - span["lo"]) / base * 100.0
            assert rng < 5.0, (
                f"{name} can range {rng:.2f}% of its value at identical cost "
                f"({span['lo']:,.1f} to {span['hi']:,.1f}) - the LP is "
                "indifferent, so the reported build is arbitrary"
            )
    finally:
        model.del_component(model._degen_bound)
        obj.activate()


@pytest.mark.slow
def test_shadow_prices_are_sane_and_peak_in_the_evening(net, econ):
    """The dual on each slice's energy balance is the marginal cost of one more
    delivered kWh. None may be negative, and the daily peak must sit in an
    evening band, not at midday when PV is abundant.

    Duals are scaled by the period weight (2030 represents 8 years, discount
    rate 0), so divide by that weight to read INR/kWh. Measured: 2.83 midday
    to 7.70 evening.
    """
    if not has_pyomo():
        pytest.skip("pyomo not installed - LP path not exercised")
    import pyomo.environ as pyo
    from energy.dispatch import (
        _build_pyomo_model_multi_period, _solve_pyomo,
    )
    model, periods, sids, _h, weights = _build_pyomo_model_multi_period(
        net, econ, econ.scenario("full_stack"), alpha=0.0)
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
    _solve_pyomo(model)

    bal = getattr(model, "balance", None)
    if bal is None:
        pytest.skip("energy-balance constraint not found by name")
    base_year = int(econ.multi_period_base_year())
    w = float(weights[base_year]) or 1.0
    slices_by_id = {s.id: s for s in econ.slices}

    duals = {}
    for s in sids:
        try:
            duals[s] = float(model.dual[bal[base_year, s]]) / w
        except (KeyError, AttributeError):
            pass
    if not duals:
        pytest.skip("solver returned no duals (integer vars make them undefined)")

    neg = {k: v for k, v in duals.items() if v < -1e-6}
    assert not neg, f"{len(neg)} slices have a NEGATIVE marginal cost, e.g. " \
                    f"{list(neg.items())[:3]}"

    by_dp = {}
    for sid, d in duals.items():
        by_dp.setdefault(slices_by_id[sid].daypart, []).append(d)
    means = {dp: sum(v) / len(v) for dp, v in by_dp.items()}
    peak_dp = max(means, key=means.get)
    assert peak_dp in ("16_18", "18_20", "20_22"), (
        f"marginal cost peaks at {peak_dp}, not in an evening band. "
        f"Means: {dict(sorted(means.items()))}"
    )
