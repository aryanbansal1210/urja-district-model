"""Shared pytest fixtures for district_v3.

WHY THIS FILE EXISTS (register item. `compute_geometric_shading` costs
~200 s per network build and nothing cached it, so every test needing a network
paid the full cost. That is essentially the whole 1:07:17 suite runtime. Before
 there was no conftest.py in this project at all, so there was nowhere
for a shared network to live.

SCOPE, stated honestly rather than oversold: this only helps tests that ASK for
these fixtures. The existing call sites that call ``load_optimised_network``
directly are unchanged and still pay per build - retrofitting them is a separate
job, because each one has to be checked for whether it mutates the network.

WHAT IS DELIBERATELY *NOT* DONE HERE: nothing in production is memoised. A
shading cache keyed on the wrong signature would silently change PV yield, and
silent PV changes are the one class of bug this project can least afford (see
the fix to the swallowed shading failure in energy/network.py).
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: needs an LP solve (~2 min each). Deselect with -m 'not slow'.",
    )


@pytest.fixture(scope="session")
def econ():
    """Production ``Economics``, loaded once per session."""
    from energy.costs import load_economics
    return load_economics(force_reload=True)


@pytest.fixture(scope="session")
def net(econ):
    """The frozen seed-42 optimised network, built ONCE per session.

    ~200 s on first use, free for every later test. Session-scoped because the
    layout is frozen, so every test legitimately sees the same object.

    CONTRACT: treat it as READ-ONLY. A test that mutates node peaks must deep
    copy first (see ``EnergyNetwork.cooling_kwh_by_slice`` for the pattern,
    including giving the clone its own ``_demand_kwh_cache``).
    """
    from energy.network import load_optimised_network
    return load_optimised_network(econ=econ)


@pytest.fixture(scope="session")
def full_stack(econ):
    """The production ``full_stack`` scenario object."""
    return econ.scenario("full_stack")
