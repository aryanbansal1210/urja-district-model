"""Discrete carport-site placement near demand anchors (Item 3,).

The aggregate carport PV is sized by `EnergyNetwork.total_carport_potential_kwp`
(sums per-cell kWp over eligible land uses). Without spatial siting, that
aggregate spreads carport PV uniformly across ALL eligible cells (road,
office, shopping_centre, healthcare, public_services, high-income
residential, hotel_guesthouse) — i.e. potentially anywhere in the
district, which is physically implausible. Carports follow parking
demand, which clusters around workplaces (light_industry, warehouse,
office), healthcare (hospital car parks), and high-occupancy public
services / shopping.

This module picks DISCRETE carport sites near those anchors, balanced
across the four geographic quadrants of the 25 × 25 grid. Selected
cells get `cell.is_carport_site = True`. `total_carport_potential_kwp`
falls back to "all eligible × uptake" when no sites are marked.

: DO NOT re-anneal the frozen optimised_sa layout
(seed 42). Sites are tagged on the loaded grid surgically; the GeoJSON
re-export round-trips the attribute.

Radius default: 4 cells = 800 m. Defensible: real urban parking
infrastructure typically serves trips < 1 km (Cervero 2009, Land
Use and Travel; CSE India 2019, "Parking policy for clean air").
Quadrant balance default: 14 sites per quadrant = 56 total (≈ what
the LP was already deploying at the geometric ceiling; sized to keep
the headline within a few % of the pre-siting baseline).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from core.grid import Cell, Grid
from core.land_use import LandUse


# Anchors: cells that GENERATE the parking demand the carport serves.
DEFAULT_ANCHOR_LAND_USES: Tuple[LandUse, ...] = (
    LandUse.LIGHT_INDUSTRY,
    LandUse.WAREHOUSE,
    LandUse.HEALTHCARE,
    LandUse.OFFICE,
    LandUse.PUBLIC_SERVICES,
    LandUse.SHOPPING_CENTRE,
)

# Carport-eligible: cells that CAN HOST a carport (have parking footprint).
#: ROAD removed. A 200 m ROAD cell carries moving
# traffic and at most a thin parallel-parking strip — it can't house a
# proper carport-with-PV canopy. Real carports go on dedicated parking
# lots adjacent to demand anchors (mall / office / hospital / industry /
# public-services / hotel / high-income RWA visitor parking). The site
# is meant to "fully substitute" the host cell with a parking-lot +
# canopy PV at the optimal fixed-tilt angle (Punjab south, ~25-30°);
# placing it on a ROAD cell makes neither the road nor the carport
# defensible. Carport PV orientation defaults to south_fixed (see
# `pv_orientation_defaults_by_category` in economics.yaml).
DEFAULT_CARPORT_ELIGIBLE_LAND_USES: Tuple[LandUse, ...] = (
    LandUse.OFFICE,
    LandUse.SHOPPING_CENTRE,
    LandUse.HEALTHCARE,
    LandUse.PUBLIC_SERVICES,
    LandUse.RESIDENTIAL_HIGH,
    LandUse.HOTEL_GUESTHOUSE,
    LandUse.LIGHT_INDUSTRY,
    LandUse.WAREHOUSE,
)


# carport canopy sizing on PARKING_LOT cells, by area (consistent
# with the solar-farm ground-mount density). CARPORT_KWP_PER_M2 mirrors
# demand_norms.yaml `solar.ground_mount_kwp_per_m2` (0.10 kWp/m^2 land density);
# CARPORT_CANOPY_COVERAGE is the fraction of the parking-lot cell under canopy
# (panels over bays; aisles / access / landscaping uncovered). Tier-3.
CARPORT_KWP_PER_M2: float = 0.10
CARPORT_CANOPY_COVERAGE: float = 0.50


def _quadrant(cell: Cell, n_rows: int, n_cols: int) -> int:
    """0 = SW, 1 = SE, 2 = NW, 3 = NE (grid (0,0) is SW corner)."""
    mid_r = n_rows / 2.0
    mid_c = n_cols / 2.0
    north = 1 if cell.row >= mid_r else 0
    east = 1 if cell.col >= mid_c else 0
    return north * 2 + east


def place_carports(
    grid: Grid,
    *,
    target_per_quadrant: int = 14,
    radius_cells: Optional[int] = None,
    anchor_land_uses: Optional[Sequence[LandUse]] = None,
    eligible_land_uses: Optional[Sequence[LandUse]] = None,
) -> Dict[int, List[Tuple[int, int]]]:
    """Tag discrete carport sites on `grid`. Mutates in place.

    Algorithm:
      1. Clear `is_carport_site` on all cells.
      2. Build the list of anchor cells (light_industry, warehouse,
         healthcare, office, public_services, shopping_centre).
      3. For each eligible cell: compute the minimum Manhattan distance
         (in cells) to any anchor. Drop if > `radius_cells`.
      4. Group remaining candidates by geographic quadrant.
      5. Within each quadrant, sort by ascending distance-to-anchor
         (ties broken by (row, col)), and pick the top
         `target_per_quadrant` cells. Quadrants with fewer eligible
         candidates than `target_per_quadrant` get as many as available
         (no padding with distant cells — physical realism > equal counts).
      6. Set `is_carport_site = True` on chosen cells.

    Returns
    -------
    Dict[int, List[(row, col)]]
        Mapping quadrant_id -> list of (row, col) chosen sites.
    """
    anchors_lu = set(anchor_land_uses or DEFAULT_ANCHOR_LAND_USES)
    eligible_lu = set(eligible_land_uses or DEFAULT_CARPORT_ELIGIBLE_LAND_USES)

    # STAGE-: the anchor radius is a WALKING distance (~800 m,
    # Cervero 2009 / CSE India 2019), so it is metre-anchored and derived from
    # the grid's cell size (4 cells at 200 m, 8 cells at 100 m) instead of a
    # fixed cell count that silently halved at the re-grid.
    if radius_cells is None:
        radius_cells = max(1, int(round(800.0 / grid.cell_size_m)))

    # Reset previous tags.
    for c in grid.all_cells():
        c.is_carport_site = False

    # carports now live on dedicated PARKING_LOT cells. Those cells
    # are themselves DEMAND-SIZED (URDPFI ECS, core.requirements) and placed by
    # the SA near the demand anchors / under-served residential (catchment), so
    # every parking lot is by construction next to the trips it serves. Each one
    # hosts a full PV canopy. We tag ALL parking lots and skip the legacy
    # anchor-radius siting. The anchor-based path below is kept as a FALLBACK for
    # archetype layouts (chandigarh_sector, etc.) that carry no PARKING_LOT cells.
    parking_cells = [
        c for c in grid.all_cells() if c.land_use == LandUse.PARKING_LOT
    ]
    if parking_cells:
        chosen: Dict[int, List[Tuple[int, int]]] = {q: [] for q in range(4)}
        for cell in parking_cells:
            cell.is_carport_site = True
            q = _quadrant(cell, grid.n_rows, grid.n_cols)
            chosen[q].append((cell.row, cell.col))
        return chosen

    anchor_cells: List[Cell] = [
        c for c in grid.all_cells() if c.land_use in anchors_lu
    ]
    if not anchor_cells:
        return {q: [] for q in range(4)}

    # Score each eligible cell by min Manhattan distance to any anchor.
    candidates_by_quad: Dict[int, List[Tuple[int, int, int, Cell]]] = {
        0: [], 1: [], 2: [], 3: [],
    }
    for cell in grid.all_cells():
        if cell.land_use not in eligible_lu:
            continue
        min_dist = min(
            abs(cell.row - a.row) + abs(cell.col - a.col)
            for a in anchor_cells
        )
        if min_dist > radius_cells:
            continue
        q = _quadrant(cell, grid.n_rows, grid.n_cols)
        candidates_by_quad[q].append((min_dist, cell.row, cell.col, cell))

    chosen: Dict[int, List[Tuple[int, int]]] = {q: [] for q in range(4)}
    for q, cands in candidates_by_quad.items():
        cands.sort(key=lambda t: (t[0], t[1], t[2]))
        for _, r, c, cell in cands[:target_per_quadrant]:
            cell.is_carport_site = True
            chosen[q].append((r, c))
    return chosen


def carport_kwp_for_cell(cell: Cell, default_kwp: Optional[float] = None) -> float:
    """Per-cell carport kWp by land-use parking footprint.

    STAGE-: every branch is now AREA-DERIVED so the values
    scale with cell size (the old constants were hand-sized to a 200 m /
    4-ha cell; at the 100 m re-grid they were 4x too big). Formula:

        kWp = cell_area x parking_coverage(land use) x CARPORT_KWP_PER_M2

    with coverage = the share of the cell under canopy-covered parking:

    - PARKING_LOT       : 0.50 (dedicated lot; aisles/landscaping uncovered)
    - shopping_centre   : 0.375 (large surface car park, e.g. Pacific Mall)
    - warehouse / industry : 0.30 (loading area + employee parking)
    - office / healthcare / public_services / hotel : 0.25 (mid)
    - high-income residential : 0.15 (visitor parking only - the plotted
      colony self-parks on-plot, see demand_norms.yaml parking note)

    At a 200 m cell these reproduce the pre- constants byte-for-byte
    (40,000 x 0.375 x 0.10 = 1,500; x0.30 = 1,200; x0.25 = 1,000;
    x0.15 = 600); at a 100 m cell they give 375 / 300 / 250 / 150 kWp.

: the ROAD branch was REMOVED (carport sites
    no longer land on ROAD cells; see `DEFAULT_CARPORT_ELIGIBLE_LAND_USES`
    rationale above). A ROAD cell is for moving traffic, not parking.

    Sources: Cochin Airport (CIAL) 50 MW carport plant 2022 (~0.1 kWp/m^2
    over parking footprint); CSE India parking-policy briefs; IEA PVPS
    Task 13 carport reference designs. Tier-3 coverages.
    """
    lu = cell.land_use
    area = cell.cell_size_m ** 2
    if lu == LandUse.PARKING_LOT:
        return area * CARPORT_CANOPY_COVERAGE * CARPORT_KWP_PER_M2
    if lu == LandUse.SHOPPING_CENTRE:
        return area * 0.375 * CARPORT_KWP_PER_M2
    if lu in (LandUse.WAREHOUSE, LandUse.LIGHT_INDUSTRY):
        return area * 0.30 * CARPORT_KWP_PER_M2
    if lu == LandUse.RESIDENTIAL_HIGH:
        return area * 0.15 * CARPORT_KWP_PER_M2
    if default_kwp is not None:
        return default_kwp
    # office / healthcare / public_services / hotel_guesthouse
    return area * 0.25 * CARPORT_KWP_PER_M2
