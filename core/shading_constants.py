"""Shared inter-building shading thresholds -.

The parameter audit found the same shading threshold hand-written
in FIVE modules with two different values and no cross-reference:

    layout/constraints.py   SHADING_DELTA_M                     9.0
    layout/metrics.py       SHADOW_DELTA_M                      6.0
    layout/metrics.py       SHADING_DELTA_M_PROXY               6.0
    core/export_3d.py       SHADING_OFFENDER_HEIGHT_THRESHOLD_M 6.0
    energy/network.py       SHADING_DELTA_M                     6.0

plus ``GROUND_PV_PANEL_TOP_M = 1.5`` in three of them, one of which carried
the comment "matches energy/solar_geometry constant" - a comment ASSERTING a
match rather than enforcing one, which is exactly how the two drift apart.

THE 9.0 IS NOT A BUG. Reading the call sites, the model uses two distinct
thresholds for two distinct purposes, and collapsing them would have been the
wrong fix:

  - the LAYOUT HARD CONSTRAINT asks "is this so overshadowed that it fails
    planning?", and answers at three storeys;
  - everything PV-related asks "does this neighbour cost me generation?", and
    answers at two storeys.

So both survive, named for what they mean rather than for where they happen to
live. What is removed is the possibility of one being edited and the other
four silently disagreeing.

Storey height convention: 3.0 m, consistent with `core.grid.HeightTier` and the
typical_height_m figures in `core.land_use`.
"""
from __future__ import annotations

#: Storey height used to express the thresholds below in whole storeys.
STOREY_HEIGHT_M: float = 3.0

#: Height advantage at which a neighbour counts as MATERIAL DAYLIGHT
#: BLOCKAGE for the layout hard constraint (3 storeys). Deliberately looser
#: than the PV threshold: a planning failure is a stronger claim than a yield
#: penalty, so it takes more building to trigger it.
DAYLIGHT_BLOCKAGE_DELTA_M: float = 3.0 * STOREY_HEIGHT_M      # 9.0

#: Height advantage at which a neighbour counts as MATERIAL PV SHADING
#: (2 storeys). Used by the solar-access score, the PV shading proxy, the
#: energy model's yield penalty and the viewer's tooltip - all four must
#: agree, because they are describing the same physical effect to different
#: audiences.
PV_SHADING_DELTA_M: float = 2.0 * STOREY_HEIGHT_M             # 6.0

#: Top-of-panel height for ground-mounted / rooftop PV, i.e. the height a
#: shadow has to clear before it costs anything.
GROUND_PV_PANEL_TOP_M: float = 1.5
