"""Street furniture on ROAD cells: avenue trees + streetlights (batch-A Task 5,
;).

Two road-cell attributes, tagged deterministically AFTER the SA converges (ROAD
cells are locked, so — like faith tags and carport sites — these are applied in
place on the frozen grid and round-trip through the GeoJSON):

  * ``has_street_trees`` — avenue/street trees line EVERY road segment (the author
 "put trees everywhere even on corners"). Trees cool the adjacent
    BUILT cells via shade + evapotranspiration; the cooling enters Stage B/C
    demand through ``EnergyNetwork._microclimate_cooling_multiplier``.

  * ``streetlight_type`` — "solar" (off-grid) or "grid" (mains), chosen by an
    ECONOMIC comparison per road cell (the author: "only solar street lamps if the
    optimising model allows it; if it's not worth it the model won't"):

      NPV_grid  = grid pole/LED capex
                  + trenching to reach the existing grid (Rs/m x distance)
                  + 25-yr discounted street-lighting ENERGY (grid-supplied)
      NPV_solar = solar pole capex (panel + LED + LFP BATTERY)
                  + battery replacements over 25 yr (the battery is the cost
                    driver, replaced every ~6 yr); no energy cost (off-grid)

    The cell takes whichever is cheaper. Grid wins where the road abuts the
    built area (≈0 trenching, cheap energy per pole); SOLAR wins where reaching
    the grid needs trenching (the periphery) — i.e. solar is selected ONLY when
    it is genuinely cheaper, not by a fixed rule. ``streetlight_type`` then
    drives the grid NIGHT load in ``EnergyNetwork`` (grid lamps add a
    night-shaped load; solar lamps add NOTHING).

Cost basis (Tier-3 engineering estimates; sized from MNRE/ANERT off-grid solar
streetlight specs + typical LT-cable trenching rates; the street-lighting energy
per pole = ~80 W LED x ~12 h x 365 ≈ 350 kWh/yr):
  - solar pole (75-100 Wp panel + 12.8 V LFP battery + LED + pole): ~Rs 22,000
    (ANERT/HAREDA off-grid streetlight tenders) + ~Rs 6,000 battery every ~6 yr.
  - grid pole + LED: ~Rs 10,000; LT-cable trenching ~Rs 500/m (cable + civil).
Idempotent: clears both attributes first, then re-tags ROAD cells.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

from core.grid import Grid
from core.land_use import LandUse


# --- streetlight cost parameters (Tier-3; see module docstring) -------------
SOLAR_POLE_CAPEX_INR = 22_000.0            # panel + LFP battery + LED + pole
SOLAR_BATTERY_REPLACE_INR = 6_000.0        # per replacement
SOLAR_BATTERY_LIFE_YR = 6.0                # LFP replaced ~every 6 yr
GRID_POLE_CAPEX_INR = 10_000.0             # pole + LED (no battery)
GRID_TRENCH_INR_PER_M = 500.0              # LT cable + civil trenching
POLES_PER_ROAD_CELL = 8.0                  # ~25 m spacing over a 200 m segment
STREETLIGHT_KWH_PER_POLE_YR = 350.0        # 80 W x 12 h x 365
# Street lighting is billed at the municipal "Public Lamps / Street Lighting"
# category, LOWER than domestic retail (~Rs 5 vs ~6). With this rate, grid is
# marginally cheaper than solar when the pole sits ON the built/grid edge (no
# trenching), so the choice is decided by TRENCHING distance: the built core
# stays grid, the periphery flips to solar. PSPCL Public Lamps tariff (Tier-3).
GRID_ENERGY_INR_PER_KWH = 5.0
HORIZON_YR = 25.0
DISCOUNT_REAL = 0.08                       # real discount rate (matches econ)


def _annuity_pv_factor(rate: float, years: float) -> float:
    """Present-value factor for a constant annual cashflow over `years`."""
    if rate <= 0:
        return years
    return (1.0 - (1.0 + rate) ** (-years)) / rate


def _battery_replacement_npv() -> float:
    """NPV of LFP battery replacements over the horizon (replaced every
    SOLAR_BATTERY_LIFE_YR; first battery is in the pole capex)."""
    npv = 0.0
    t = SOLAR_BATTERY_LIFE_YR
    while t < HORIZON_YR:
        npv += SOLAR_BATTERY_REPLACE_INR / ((1.0 + DISCOUNT_REAL) ** t)
        t += SOLAR_BATTERY_LIFE_YR
    return npv


def _dist_cells_to_nearest_built(grid: Grid) -> dict:
    """Multi-source BFS: for every cell, the 4-connected cell-distance to the
    nearest BUILT cell (0 if the cell itself is built)."""
    INF = 10 ** 9
    dist = [[INF] * grid.n_cols for _ in range(grid.n_rows)]
    q: deque = deque()
    for c in grid.all_cells():
        if c.has_building:
            dist[c.row][c.col] = 0
            q.append((c.row, c.col))
    while q:
        r, cc = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, cc + dc
            if 0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols:
                if dist[nr][nc] > dist[r][cc] + 1:
                    dist[nr][nc] = dist[r][cc] + 1
                    q.append((nr, nc))
    return dist


def place_street_furniture(grid: Grid) -> dict:
    """Tag avenue trees (all roads) + a SEGMENT-AWARE economic streetlight choice
    on ROAD cells. Mutates in place. Returns summary counts.

 (Part 4): segment-aware upgrade. The legacy model decided each
    road cell independently, with each cell paying its OWN full trench back to
    the grid. That double-counts trenching: grid lamps along a connected road run
    SHARE one cable trench (dug once, amortised over all the run's poles). So the
    decision is now made PER SEGMENT:

      * ROAD cells ADJACENT to built (4-neighbour distance-to-built <= 1) are
        "grid-edge": the mains is already there, ~0 trench -> always grid.
      * The remaining (peripheral) ROAD cells are grouped into SEGMENTS =
        connected runs (4-connectivity among peripheral road cells). Each segment
        chooses grid-vs-solar TOGETHER:
          NPV_grid(seg)  = poles_per_cell * |seg| * grid_pole_npv
                           + GRID_TRENCH_INR_PER_M * shared_trench_m(seg)   # ONE run
          NPV_solar(seg) = poles_per_cell * |seg| * solar_npv_per_pole
        where shared_trench_m = (the segment's minimum reach to the grid edge +
        its internal spine length) * cell_size — a single cable threading the run,
        NOT each cell's full independent distance. Solar wins on long peripheral
        runs where extending the shared cable costs more than the solar premium,
        and it now appears in COHERENT RUNS (a whole cul-de-sac goes solar), not
        scattered cells. Each cell gets streetlight_segment_id + streetlight_reason.
    """
    for c in grid.all_cells():
        c.has_street_trees = False
        c.streetlight_type = None
        c.streetlight_segment_id = None
        c.streetlight_reason = None

    dist = _dist_cells_to_nearest_built(grid)
    cell_m = grid.cell_size_m
    energy_pv = (POLES_PER_ROAD_CELL * STREETLIGHT_KWH_PER_POLE_YR
                 * GRID_ENERGY_INR_PER_KWH
                 * _annuity_pv_factor(DISCOUNT_REAL, HORIZON_YR))
    solar_npv = POLES_PER_ROAD_CELL * (SOLAR_POLE_CAPEX_INR + _battery_replacement_npv())
    grid_pole_npv = POLES_PER_ROAD_CELL * GRID_POLE_CAPEX_INR + energy_pv

    road_cells = [c for c in grid.all_cells() if c.land_use == LandUse.ROAD]
    treed = 0
    for cell in road_cells:
        cell.has_street_trees = True   # trees on every road (incl. corners)
        treed += 1

    # --- grid-edge road cells (mains already adjacent) -> always grid ---
    EDGE_DIST = 1   # distance-to-built (cells) at/below which trenching ~ 0
    peripheral = []
    grid_lights = solar_lights = 0
    for cell in road_cells:
        if dist[cell.row][cell.col] <= EDGE_DIST:
            cell.streetlight_type = "grid"
            cell.streetlight_segment_id = 0   # segment 0 = the grid-edge backbone
            cell.streetlight_reason = "grid: mains-adjacent (no trench)"
            grid_lights += 1
        else:
            peripheral.append(cell)

    # --- group peripheral road cells into connected segments (4-conn) ---
    periph_set = {(c.row, c.col) for c in peripheral}
    seen: set = set()
    segments: list = []
    for c in peripheral:
        key = (c.row, c.col)
        if key in seen:
            continue
        # BFS flood-fill this connected run
        comp = []
        stack = [key]
        seen.add(key)
        while stack:
            r, cc = stack.pop()
            comp.append((r, cc))
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nk = (r + dr, cc + dc)
                if nk in periph_set and nk not in seen:
                    seen.add(nk)
                    stack.append(nk)
        segments.append(comp)

    # --- per-segment grid-vs-solar decision ---
    next_seg_id = 1
    for comp in segments:
        n = len(comp)
        # NOTE: grid_pole_npv and solar_npv are PER-CELL (they already include
        # POLES_PER_ROAD_CELL). So scale by n (cells), NOT by total poles.
        # shared trench: ONE cable run = (min reach to the grid edge) + (internal
        # spine ~ the run's own length). min reach = min over the run of
        # (distance_to_built - EDGE_DIST), in cells; spine ~ (n - 1) cells.
        min_reach = min(max(0, dist[r][cc] - EDGE_DIST) for (r, cc) in comp)
        spine = max(0, n - 1)
        shared_trench_m = (min_reach + spine) * cell_m
        npv_grid = n * grid_pole_npv + GRID_TRENCH_INR_PER_M * shared_trench_m
        npv_solar = n * solar_npv
        seg_id = next_seg_id
        next_seg_id += 1
        if npv_solar < npv_grid:
            choice, reason = "solar", (
                f"solar: cable run {shared_trench_m/1000:.1f}km > premium "
                f"({n} cells)")
            solar_lights += n
        else:
            choice, reason = "grid", (
                f"grid: shared trench {shared_trench_m/1000:.1f}km amortised "
                f"over {n} cells")
            grid_lights += n
        for (r, cc) in comp:
            cell = grid.at(r, cc)
            cell.streetlight_type = choice
            cell.streetlight_segment_id = seg_id
            cell.streetlight_reason = reason

    return {
        "treed_roads": treed,
        "grid_lights": grid_lights,
        "solar_lights": solar_lights,
        "total_roads": len(road_cells),
        "n_segments": len(segments) + 1,   # +1 for the grid-edge backbone (id 0)
        "solar_npv_per_cell": round(solar_npv),
        "grid_npv_per_cell_no_trench": round(grid_pole_npv),
    }
