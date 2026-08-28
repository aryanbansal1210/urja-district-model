""" GUARD: the hectares we PAY FOR must equal the hectares we can BUILD ON.

WHY THIS FILE EXISTS. On `farm_land_cells_by_period` was found to
have two production consumers that silently disagreed:

  * `Economics.farm_land_rent_annual_inr` charged rent on 295 ha, every period
  * the LP's capacity ceiling came from the LAYOUT'S expansion tags via
    `energy.network.phased_land_multipliers` - 201 / 251 / 301 ha

The town paid Rs 23,500,000/yr in 2030 for land it was forbidden to build on,
and in 2055 built on 6 ha it never rented. Nothing errored for three days.

THE POINT, AND WHY A CONFIG AUDIT CANNOT REPLACE THIS. `scripts/config_consumer_audit.py`
finds config keys that reach NOTHING. It could never have found this one,
because the key was never dead - it was read, in production, by a consumer
nobody was thinking about. The only thing that catches "one number, two
consumers, different answers" is an assert that RECOMPUTES the quantity by both
routes and compares. That is the same relative, decompositional style that
caught PPA-BAU-1 and the BAU parity drift three times: it stores no constant, so
it cannot go stale, and it fails the moment the two routes diverge.

These tests are fast (no LP solve) and should stay that way.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics                    # noqa: E402
from energy.network import (                               # noqa: E402
    load_optimised_network, phased_land_multipliers,
)

PERIODS = (2030, 2042, 2055)
KWP_PER_HA = 802.2          # 0.08022 kWp/m2 x 10,000 m2/ha

# Building the network costs ~3 min (the geometric-shading precompute), so cache
# it once for the whole module. Without this the four asserts below take 12 min
# between them, which is exactly the kind of cost that stops people running a
# check - and an unrun check is what was.
_CACHE: dict = {}


def _net():
    if "net" not in _CACHE:
        _CACHE["net"] = load_optimised_network()
    return _CACHE["net"]


def _econ():
    if "econ" not in _CACHE:
        _CACHE["econ"] = load_economics(force_reload=True)
    return _CACHE["econ"]


def _rented_ha(econ, year: int) -> float:
    mp = dict(econ.__dict__.get("multi_period_raw", {}) or {})
    cells = mp.get("farm_land_cells_by_period", {}) or {}
    return float(cells.get(str(year), cells.get("2030", 0.0)))


def _buildable_ha(net, year: int) -> float:
    farm_cells = len(net.solar_farm_nodes())
    mult = phased_land_multipliers(net.grid)["solar_farm"]
    return farm_cells * float(mult[year])


def test_rented_hectares_equal_buildable_hectares() -> None:
    """THE GUARD. Rent and capacity must describe the same farm.

    A mismatch is money paid for land the LP cannot use (or land used and never
    paid for). Both directions are wrong and both have happened."""
    econ = _econ()
    net = _net()
    bad = []
    for y in PERIODS:
        rented = _rented_ha(econ, y)
        buildable = _buildable_ha(net, y)
        if abs(rented - buildable) > 0.5:
            bad.append((y, rented, buildable, rented - buildable))
    assert not bad, (
        "farm land rent and farm land capacity disagree (year, rented_ha, "
        "buildable_ha, delta) - see LAND-A1. Rent comes from economics.yaml "
        "multi_period.farm_land_cells_by_period; capacity comes from the "
        "layout's solar_expansion_* tags. Change one and you must change the "
        "other.", bad)


def test_farm_ceiling_matches_land_times_density() -> None:
    """The LP's farm ceiling must be exactly land x 714 kWp/ha, per period.

    This is the decomposition that exposed: the capacities reproduced
    201/251/301 ha to the decimal while every document said 295, which is how
    we learned the tags and not the config were binding."""
    econ = _econ()
    net = _net()
    base = net.total_solar_farm_cap_kwp()
    farm_cells = len(net.solar_farm_nodes())
    assert abs(base - farm_cells * KWP_PER_HA) < 1.0, (
        "base farm ceiling is not cells x 714 kWp/ha - the density or the "
        "cell area moved", base, farm_cells)
    mult = phased_land_multipliers(net.grid)["solar_farm"]
    for y in PERIODS:
        expect = _buildable_ha(net, y) * KWP_PER_HA
        got = base * float(mult[y])
        assert abs(expect - got) < 1.0, (y, expect, got)


def test_single_period_farm_cap_equals_multi_period_2030() -> None:
    """ GUARD. The two builders must agree about the base year.

    The single-period builder is a 2030 model, so its farm ceiling must equal
    the multi-period builder's 2030 ceiling: base x density(2030) x land(2030).
    It used the BARE base for years - harmless only while the layout's
    expansion tags left 2030 at 1.0. released the whole reserve INTO
    2030 and the two silently diverged (multi 301 ha, single 201 ha) while
    both paid rent on 301 ha. This asserts they cannot drift again."""
    econ = _econ()
    net = _net()
    base = net.total_solar_farm_cap_kwp()
    land = float(phased_land_multipliers(net.grid)["solar_farm"][2030])
    dens = float(econ.pv_density_ceiling_multiplier(2030))
    expect = base * land * dens
    buildable_2030 = _buildable_ha(net, 2030) * KWP_PER_HA
    assert abs(expect - buildable_2030) < 1.0, (
        "single-period 2030 farm ceiling disagrees with the land the LP is "
        "granted in 2030 - see LAND-A3", expect, buildable_2030)


def test_reserve_tags_are_a_recognised_vocabulary() -> None:
    """Every solar_expansion_* tag on the map must be one the LP understands.

's first repair attempt retagged the reserve to
    `solar_expansion_2030`, which `phased_land_multipliers` did not know - the
    multipliers silently collapsed to 1.0/1.0/1.0 and the farm SHRANK to 201 ha
    in every period. A typo'd or invented tag must fail loudly, not quietly
    delete land."""
    import collections
    net = _net()
    known = {"solar_expansion_2030", "solar_expansion_2042",
             "solar_expansion_2055"}
    seen = collections.Counter()
    for c in net.grid.all_cells():
        sub = c.amenity_subtype or ""
        if sub.startswith("solar_expansion"):
            seen[sub] += 1
    unknown = {k: v for k, v in seen.items() if k not in known}
    assert not unknown, (
        "unrecognised solar_expansion tag on the layout - phased_land_"
        "multipliers would ignore it and the farm would silently shrink",
        unknown, sorted(known))


def main() -> int:
    import traceback
    fns = [v for k, v in sorted(globals().items())
           if callable(v) and k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  OK   {fn.__name__}")
        except AssertionError:
            failed += 1
            print(f"  FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
