"""Streetlights per road class (realism trio,).

The per-capita lighting TOTAL is unchanged; IS 1944-derived class weights
(arterial 2.0 / collector 1.0 / local 0.5) change which road cells carry the
stock, so the grid-lit share shifts. enabled:false must reproduce the legacy
equal-share arithmetic byte-exactly (it runs the original expression).
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.demographics import load_demand_norms
from core.grid import HeightTier
from core.land_use import LandUse
from energy.network import EnergyNetwork
from tests.test_energy_milp import _tiny_grid


def _lit_grid():
    """Tiny grid with 3 tagged roads: arterial(grid), collector(solar), local(grid)."""
    g = _tiny_grid()
    r_a, r_c, r_l = g.at(0, 0), g.at(0, 1), g.at(1, 0)
    r_a.road_class, r_a.streetlight_type = "arterial", "grid"
    r_c.road_class, r_c.streetlight_type = "collector", "solar"
    r_l.road_class, r_l.streetlight_type = "local", "grid"
    return g


def _norms(enabled: bool):
    n = copy.deepcopy(load_demand_norms(force_reload=True))
    n.public_services = dict(n.public_services)
    n.public_services["street_lighting_class_weights"] = {
        "enabled": enabled,
        "weights": {"arterial": 2.0, "collector": 1.0, "local": 0.5},
    }
    return n


def test_config_flip_is_the_baseline() -> None:
    # realism trio). enabled:true is now part of the pinned baseline - turning
    # it OFF un-pins the headline just as silently as turning it on did before.
    n = load_demand_norms(force_reload=True)
    cw = n.public_services.get("street_lighting_class_weights") or {}
    assert cw.get("enabled", False), (
        "street_lighting_class_weights.enabled was turned OFF - the current "
        "pins were discovered WITH class weights on (2026-07-11); flipping "
        "back re-pins the headline"
    )
    assert cw.get("weights") == {"arterial": 2.0, "collector": 1.0,
                                 "local": 0.5}, cw.get("weights")


def test_weighted_share_shifts_grid_energy() -> None:
    g = _lit_grid()
    off = EnergyNetwork.from_grid(g, norms=_norms(False))
    on = EnergyNetwork.from_grid(g, norms=_norms(True))
    assert off.grid_streetlight_kwh_yr > 0, "tiny grid must carry lighting load"
    # equal-share: grid-lit 2 of 3 cells -> 2/3.
    # weighted: tot 2+1+0.5 = 3.5, grid-lit 2+0.5 = 2.5 -> 5/7.
    expected_ratio = (2.5 / 3.5) / (2.0 / 3.0)
    got_ratio = on.grid_streetlight_kwh_yr / off.grid_streetlight_kwh_yr
    assert abs(got_ratio - expected_ratio) < 1e-9, (got_ratio, expected_ratio)


def test_untagged_road_class_defaults_to_local_weight() -> None:
    g = _lit_grid()
    g.at(1, 0).road_class = None          # untagged grid-lit road
    on = EnergyNetwork.from_grid(g, norms=_norms(True))
    off = EnergyNetwork.from_grid(g, norms=_norms(False))
    # falls back to the "local" weight (0.5): same arithmetic as the tagged case
    expected_ratio = (2.5 / 3.5) / (2.0 / 3.0)
    got_ratio = on.grid_streetlight_kwh_yr / off.grid_streetlight_kwh_yr
    assert abs(got_ratio - expected_ratio) < 1e-9, (got_ratio, expected_ratio)


def _run() -> int:
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"  FAIL {name}: {e}")
    return fails


if __name__ == "__main__":
    n = _run()
    print(f"{'OK' if n == 0 else 'FAILURES'} ({n} fail)")
    sys.exit(1 if n else 0)
