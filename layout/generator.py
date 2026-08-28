"""Rule-based layout generators.

Each generator returns a populated `Grid` representing one *archetype* of
master plan. Generators are deliberately simple and human-readable so that
the metric layer can be tested against layouts whose strengths and
weaknesses are easy to predict.

Archetypes implemented here:

  * `chandigarh_sector`  - Le-Corbusier-inspired sector grid: residential
                           sectors arranged around a commercial core, primary
                           road grid between sectors, schools in sector
                           centres, industry on the east edge, solar farm
                           on the west edge. Designed to score well overall.
  * `dispersed_low`      - sprawl baseline: residential evenly spread, few
                           amenities, weak structure. Deliberately bad
                           reference for the Pareto front.
  * `compact_centre`     - high-density mixed-use core, EWS pushed to the
                           outer ring. Strong on transport / accessibility
                           because everything is near the centre, but weak
                           on equity because EWS are far from amenities.
  * `radial`             - commercial core surrounded by concentric rings:
                           inner = high-income, middle = mid-income, outer =
                           EWS. Ring-roads + radial streets. Mid-equity, mid-
                           transport.

Coordinate convention:
  * Row 0 is south, row n_rows-1 is north.
  * Col 0 is west, col n_cols-1 is east.
  * Solar farm goes west (no morning shadow over residential).
  * Industry goes east (downwind of prevailing NW summer wind).
"""

from __future__ import annotations

import random
from math import sqrt

from core.config import load_config
from core.grid import Grid, HeightTier, make_thesis_grid
from core.land_use import DEFAULT_AREA_TARGETS, LandUse, category_for


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _set_default_height(grid: Grid, seed: int = 0) -> None:
    """Assign a height tier and matching height_m to every built cell.

    STAGE-: tiers are now DETERMINISTIC. The old row-biased
    random tier mix made the residential floor stock stochastic, which
    breaks the FX-3 bottom-up household reconciliation at the FAR-derived
    floor table (floor per cell IS the FAR class now, not a dice roll):

      * low/mid residential -> MEDIUM (net FAR 2.0 = the ratified A2 base
        class; 18 m G+5/6 perimeter-block form). The Bertaud TALL/SHORT
        gradient is applied post-anneal, floor-neutrally, by
        ``layout.spine_gradient.apply_spine_gradient`` (TALL FAR 3.0 on
        the arterial group-housing band, compensated by SHORT at the
        edge), so total floor still equals the FX-3 requirement.
      * high residential -> the FIXED plotted-colony form (the author
): MEDIUM tier multiplier (x1.0 -> floor = the config's
        12,000 m2 = net FAR 1.2 exactly) with height from the category's
        ``typical_height_m`` (12 m G+3 kothi) - the same mechanism as the
        facility categories, so the colony never scales with tiers.
      * non-residential -> MEDIUM + category typical height (unchanged).

    ``seed`` is kept for signature compatibility; no randomness remains.
    """
    cfg = load_config()

    for cell in grid.all_cells():
        cat = category_for(cell.land_use)
        if cat is None:
            continue
        cell.height_tier = HeightTier.MEDIUM
        if (cell.land_use.is_residential
                and cell.land_use != LandUse.RESIDENTIAL_HIGH):
            cell.height_m = cfg.height_for(HeightTier.MEDIUM.value)
        else:
            # fixed-form: plotted colony (12 m) + all non-residential
            cell.height_m = cat.typical_height_m


def _set_default_albedo_and_vegetation(grid: Grid) -> None:
    """Assign placeholder albedo and vegetation values per land-use.

    These will become layout decisions in their own right later (cool-roof
    treatment, street trees, etc.). For now they are rule-of-thumb defaults.
    """
    for cell in grid.all_cells():
        if cell.land_use == LandUse.OPEN_SPACE:
            cell.albedo = 0.25
            cell.vegetation_fraction = 0.85
        elif cell.land_use == LandUse.BLUE_SPACE:
            # Open water reflectance is low, but the cooling proxy comes from
            # the vegetation_fraction surface metric (treated as full-cover
            # evaporative-cooling surface).
            cell.albedo = 0.10
            cell.vegetation_fraction = 1.00
        elif cell.land_use == LandUse.SOLAR_FARM:
            cell.albedo = 0.30
            cell.vegetation_fraction = 0.10
        elif cell.land_use == LandUse.ROAD:
            cell.albedo = 0.18
            cell.vegetation_fraction = 0.10   # street trees, by default modest
        elif cell.land_use == LandUse.PARKING_LOT:
            cell.albedo = 0.18                 # asphalt surface lot
            cell.vegetation_fraction = 0.05
        elif cell.land_use.is_residential:
            cell.albedo = 0.30
            cell.vegetation_fraction = 0.20
        elif cell.land_use in (LandUse.SHOPPING_CENTRE, LandUse.OFFICE,
                                LandUse.WAREHOUSE, LandUse.LIGHT_INDUSTRY,
                                LandUse.RETAIL_HIGHSTREET):
            cell.albedo = 0.30
            cell.vegetation_fraction = 0.10
        elif cell.land_use == LandUse.RELIGIOUS:
            # temple complexes often have a courtyard / tree-lined precinct
            cell.albedo = 0.30
            cell.vegetation_fraction = 0.30
        else:
            cell.albedo = 0.25
            cell.vegetation_fraction = 0.15


def _stamp(grid: Grid, rows: range, cols: range, land_use: LandUse) -> None:
    """Paint a rectangle of cells with one land-use."""
    for r in rows:
        for c in cols:
            if 0 <= r < grid.n_rows and 0 <= c < grid.n_cols:
                grid.at(r, c).land_use = land_use


# ---------------------------------------------------------------------------
# Archetype 1: Chandigarh-inspired sector grid (TUNED)
# ---------------------------------------------------------------------------
def chandigarh_sector(seed: int = 0) -> Grid:
    """A 5 x 5 super-grid of sectors sized to the Stage- compact town.

    STAGE- REDESIGN. The pre- map filled ~56% of the grid
    with residential sectors - right for the old FAR-0.15 sprawl model,
    but ~1,000 cells away from the 250k compact-town targets (residential
    15.8%, open+belt 45.8%; see land_use_targets), which would strand the
    SA at 2,500 cells (spec risk R4). The sector mix now mirrors the
    derive_requirements cell budget at 250k:

      * a walkable TOWN CORE clustered on the central arterial cross:
        town-centre commercial at the crossing (TOD), civic campus and
        mid-income flats adjacent, EWS/LIG flats on the south spine,
        the plotted kothi colony (fixed 12 m form) on the SE quarter;
      * industry + warehouse on the east edge (downwind of the NW
        prevailing summer wind, unchanged rationale);
      * the locked solar reserve on the SW corner (apply_locked_zones
        stamps the exact 225-cell block over this seed);
      * two blue-space park sectors (~49 blue cells each ~= the 100-cell
        URDPFI water-body budget) inside the northern green belt;
      * everything else OPEN - the peri-urban green/agri belt that is the
        densification dividend of FAR 2.0 at 250k (open target 0.458).

    Under-seeded uses (parking lots, most religious cells) are grown by
    the SA's under-supply-biased cell-change move against requirements.

    Returns
    -------
    Grid
        Chandigarh-inspired compact-town sector archetype.
    """
    grid = make_thesis_grid()
    n = grid.n_rows                       # 50 at Stage-
    s = max(1, n // 5)                    # sector size in cells (10)

    # Sector grid layout (sector_row, sector_col) -> sector kind.
    # row 0 is the south edge (best solar exposure: no southern neighbours).
    sector_use = {
        # row 0 (south): solar reserve SW, EWS+mid spine, kothi colony, belt
        (0, 0): "solar",  (0, 1): "solar",    (0, 2): "resmix",     (0, 3): "high",     (0, 4): "open",
        # row 1: mid flats + civic campus flank the core; industry east
        (1, 0): "open",   (1, 1): "mid",      (1, 2): "civic",      (1, 3): "high",     (1, 4): "indwh",
        # row 2 (centre): town-centre commercial ON the arterial cross (TOD)
        (2, 0): "open",   (2, 1): "open",     (2, 2): "towncentre", (2, 3): "open",     (2, 4): "open",
        # rows 3-4 (north): the green belt with two blue-space parks
        (3, 0): "open",   (3, 1): "bluepark", (3, 2): "open",       (3, 3): "bluepark", (3, 4): "open",
        (4, 0): "open",   (4, 1): "open",     (4, 2): "open",       (4, 3): "open",     (4, 4): "open",
    }

    for (sr, sc), use in sector_use.items():
        r0 = sr * s
        c0 = sc * s
        rows = range(r0, r0 + s)
        cols = range(c0, c0 + s)
        rc = r0 + s // 2  # sector centre row
        cc = c0 + s // 2  # sector centre col

        if use == "resmix":
            # south half EWS/LIG flats, north half mid flats (spine-adjacent
            # halves of one residential sector; religious seed interior).
            _stamp(grid, range(r0, r0 + s // 2), cols, LandUse.RESIDENTIAL_LOW)
            _stamp(grid, range(r0 + s // 2, r0 + s), cols, LandUse.RESIDENTIAL_MID)
            grid.at(r0 + 1, c0 + 1).land_use = LandUse.RELIGIOUS
        elif use == "mid":
            _stamp(grid, rows, cols, LandUse.RESIDENTIAL_MID)
            grid.at(rc, cc).land_use = LandUse.SCHOOL
            grid.at(rc + 1, cc + 1).land_use = LandUse.RESTAURANT_FOOD
            grid.at(r0 + 1, c0 + 1).land_use = LandUse.RELIGIOUS
        elif use == "high":
            # plotted kothi colony (fixed 12 m G+3 form; see _set_default_height)
            _stamp(grid, rows, cols, LandUse.RESIDENTIAL_HIGH)
            grid.at(r0 + 1, c0 + 1).land_use = LandUse.RELIGIOUS
        elif use == "towncentre":
            # Commercial core on the arterial crossing: mall/office block at
            # the centre, high-street strip on its southern street-wall,
            # hotel + F&B inside, a few parking-lot seeds at the corners.
            _stamp(grid, rows, cols, LandUse.OPEN_SPACE)
            b = max(2, int(round(0.6 * s)))          # 6x6 core block at s=10
            br0, bc0 = rc - b // 2, cc - b // 2
            _stamp(grid, range(br0, br0 + b), range(bc0, bc0 + b),
                   LandUse.SHOPPING_CENTRE)
            for k in range(min(6, b)):               # office row inside the block
                grid.at(br0 + b - 1, bc0 + k).land_use = LandUse.OFFICE
            grid.at(br0, bc0).land_use = LandUse.HOTEL_GUESTHOUSE
            grid.at(br0, bc0 + 1).land_use = LandUse.RESTAURANT_FOOD
            grid.at(br0, bc0 + 2).land_use = LandUse.RESTAURANT_FOOD
            for k in range(min(7, b + 1)):           # bazaar street-wall south
                r_hs, c_hs = br0 - 1, bc0 + k
                if 0 <= r_hs < n and 0 <= c_hs < n:
                    grid.at(r_hs, c_hs).land_use = LandUse.RETAIL_HIGHSTREET
            for (pr, pc) in ((br0 - 1, bc0 - 1), (br0 + b, bc0 - 1),
                             (br0 + b, bc0 + b), (br0 - 1, bc0 + b)):
                if 0 <= pr < n and 0 <= pc < n:      # parking seeds at corners
                    grid.at(pr, pc).land_use = LandUse.PARKING_LOT
        elif use == "civic":
            # School-campus sector (85-cell URDPFI budget ~= one sector) with
            # the IPHS health cells + public-services block inside it.
            _stamp(grid, rows, cols, LandUse.SCHOOL)
            for k in range(6):                        # 6 IPHS facilities
                grid.at(rc - 1 + k // 3, cc - 1 + k % 3).land_use = LandUse.HEALTHCARE
            for k in range(9):                        # 3x3 civic block
                grid.at(r0 + 1 + k // 3, c0 + 1 + k % 3).land_use = LandUse.PUBLIC_SERVICES
        elif use == "indwh":
            # Industry block SW of the sector + warehouse block NE, rest open.
            _stamp(grid, rows, cols, LandUse.OPEN_SPACE)
            bi = max(2, int(round(0.6 * s)))          # 6x6 industry at s=10
            bw = max(2, int(round(0.4 * s)))          # 4x4 warehouse at s=10
            _stamp(grid, range(r0, r0 + bi), range(c0, c0 + bi),
                   LandUse.LIGHT_INDUSTRY)
            _stamp(grid, range(r0 + s - bw, r0 + s), range(c0 + s - bw, c0 + s),
                   LandUse.WAREHOUSE)
        elif use == "solar":
            _stamp(grid, rows, cols, LandUse.SOLAR_FARM)
        elif use == "open":
            _stamp(grid, rows, cols, LandUse.OPEN_SPACE)
        elif use == "bluepark":
            # Large pond/lake filling most of a green sector (two of these
            # ~= the 100-cell blue-space budget), framed by open space.
            _stamp(grid, rows, cols, LandUse.OPEN_SPACE)
            bb = max(2, int(round(0.7 * s)))          # 7x7 water at s=10
            wb0r, wb0c = rc - bb // 2, cc - bb // 2
            _stamp(grid, range(wb0r, wb0r + bb), range(wb0c, wb0c + bb),
                   LandUse.BLUE_SPACE)

    # Step 2: arterial road grid laid on top of the sector fill: perimeter
    # ring + central cross (matches layout.locked_zones.arterial_rows_cols).
    for c in range(n):
        grid.at(0, c).land_use = LandUse.ROAD
        grid.at(n // 2, c).land_use = LandUse.ROAD
        grid.at(n - 1, c).land_use = LandUse.ROAD
    for r in range(n):
        grid.at(r, 0).land_use = LandUse.ROAD
        grid.at(r, n // 2).land_use = LandUse.ROAD
        grid.at(r, n - 1).land_use = LandUse.ROAD

    _set_default_height(grid, seed=seed)
    _set_default_albedo_and_vegetation(grid)
    return grid


# ---------------------------------------------------------------------------
# Archetype 2: dispersed low-density sprawl
# ---------------------------------------------------------------------------
def dispersed_low(seed: int = 0) -> Grid:
    """Sprawl baseline: residential dominant, few amenities, weak structure.

    Intentionally not a good design. Anchors the Pareto front from below so
    the others have a benchmark to beat.

    Returns
    -------
    Grid
        Low-density dispersed baseline archetype.
    """
    rng = random.Random(seed)
    grid = make_thesis_grid()

    rare_lus = [
        LandUse.SCHOOL, LandUse.OFFICE, LandUse.SHOPPING_CENTRE,
        LandUse.RESTAURANT_FOOD, LandUse.HEALTHCARE, LandUse.PUBLIC_SERVICES,
        LandUse.HOTEL_GUESTHOUSE, LandUse.LIGHT_INDUSTRY, LandUse.WAREHOUSE,
    ]
    residential_lus = [
        LandUse.RESIDENTIAL_LOW, LandUse.RESIDENTIAL_MID, LandUse.RESIDENTIAL_HIGH,
    ]

    for cell in grid.all_cells():
        roll = rng.random()
        if roll < 0.15:
            cell.land_use = LandUse.ROAD
        elif roll < 0.25:
            cell.land_use = LandUse.OPEN_SPACE
        elif roll < 0.30:
            cell.land_use = rng.choice(rare_lus)
        else:
            cell.land_use = rng.choice(residential_lus)

    _set_default_height(grid, seed=seed)
    _set_default_albedo_and_vegetation(grid)
    return grid


# ---------------------------------------------------------------------------
# Archetype 3: compact mixed-use core, EWS at edge
# ---------------------------------------------------------------------------
def compact_centre(seed: int = 0) -> Grid:
    """High-density mixed-use centre. EWS pushed to the outer ring.

    Strong on transport / accessibility because amenities are central and
    everything is close. Weak on equity because EWS are far from the centre.
    Useful contrast to the chandigarh archetype.

    Returns
    -------
    Grid
        Compact mixed-use centre archetype.
    """
    grid = make_thesis_grid()
    n = grid.n_rows
    centre = (n // 2, n // 2)
    # STAGE-: distance bands and offsets scale with the grid
    # (f = 2.0 at 50x50) so the archetype keeps its SHAPE at any resolution.
    f = n / 25.0

    # Distance bands from centre (Euclidean in cell units)
    for r in range(n):
        for c in range(n):
            d = sqrt((r - centre[0]) ** 2 + (c - centre[1]) ** 2)
            cell = grid.at(r, c)
            if d < 2.5 * f:
                cell.land_use = LandUse.OFFICE
            elif d < 4.5 * f:
                cell.land_use = LandUse.SHOPPING_CENTRE
            elif d < 6.5 * f:
                cell.land_use = LandUse.RESIDENTIAL_HIGH
            elif d < 9.0 * f:
                cell.land_use = LandUse.RESIDENTIAL_MID
            elif d < 11.5 * f:
                cell.land_use = LandUse.RESIDENTIAL_LOW
            else:
                cell.land_use = LandUse.OPEN_SPACE

    # arterial cross + outer ring
    for i in range(n):
        grid.at(centre[0], i).land_use = LandUse.ROAD
        grid.at(i, centre[1]).land_use = LandUse.ROAD
        grid.at(0, i).land_use = LandUse.ROAD
        grid.at(n - 1, i).land_use = LandUse.ROAD
        grid.at(i, 0).land_use = LandUse.ROAD
        grid.at(i, n - 1).land_use = LandUse.ROAD

    # critical amenities + industry + solar (offsets scaled by f)
    def _o(k: float) -> int:
        return max(1, int(round(k * f)))

    grid.at(centre[0] - _o(1), centre[1] + _o(1)).land_use = LandUse.HEALTHCARE
    grid.at(centre[0] + _o(1), centre[1] - _o(1)).land_use = LandUse.HOTEL_GUESTHOUSE
    grid.at(centre[0] - _o(2), centre[1] - _o(2)).land_use = LandUse.PUBLIC_SERVICES
    # one school per quadrant, in the residential mid ring
    for (dr, dc) in [(-_o(7), -_o(3)), (-_o(7), _o(3)), (_o(7), -_o(3)), (_o(7), _o(3))]:
        r, c = centre[0] + dr, centre[1] + dc
        if 0 <= r < n and 0 <= c < n:
            grid.at(r, c).land_use = LandUse.SCHOOL
    # restaurants scattered in the commercial ring
    for (dr, dc) in [(-_o(3), 0), (_o(3), 0), (0, -_o(3)), (0, _o(3))]:
        r, c = centre[0] + dr, centre[1] + dc
        if 0 <= r < n and 0 <= c < n:
            grid.at(r, c).land_use = LandUse.RESTAURANT_FOOD
    # industry on east edge, warehouse below it
    for r in range(_o(2), _o(8)):
        grid.at(r, n - 2).land_use = LandUse.LIGHT_INDUSTRY
    for r in range(_o(8), _o(12)):
        grid.at(r, n - 2).land_use = LandUse.WAREHOUSE
    # solar farm on west edge
    for r in range(_o(8), _o(18)):
        grid.at(r, 1).land_use = LandUse.SOLAR_FARM

    _set_default_height(grid, seed=seed)
    _set_default_albedo_and_vegetation(grid)
    return grid


# ---------------------------------------------------------------------------
# Archetype 4: radial, with concentric income rings (more equitable)
# ---------------------------------------------------------------------------
def radial(seed: int = 0) -> Grid:
    """Commercial core, then high-income, mid-income, EWS in concentric rings.

    Ring road at each band boundary. Schools and amenities placed on the
    rings rather than the centre, so they are closer to mid- and low-income
    households than to the high-income inner ring. This is a deliberate
    counter-design to compact_centre.

    Returns
    -------
    Grid
        Radial income-ring archetype.
    """
    grid = make_thesis_grid()
    n = grid.n_rows
    centre = (n // 2, n // 2)
    # STAGE-: rings/offsets scale with the grid (f = 2 at 50x50).
    f = n / 25.0

    for r in range(n):
        for c in range(n):
            d = sqrt((r - centre[0]) ** 2 + (c - centre[1]) ** 2)
            cell = grid.at(r, c)
            # rings - reversed compared to compact_centre to get equity
            if d < 2.0 * f:
                cell.land_use = LandUse.OFFICE
            elif d < 3.5 * f:
                cell.land_use = LandUse.SHOPPING_CENTRE
            elif d < 5.5 * f:
                cell.land_use = LandUse.RESIDENTIAL_HIGH
            elif d < 8.5 * f:
                cell.land_use = LandUse.RESIDENTIAL_MID
            elif d < 11.5 * f:
                cell.land_use = LandUse.RESIDENTIAL_LOW
            else:
                cell.land_use = LandUse.OPEN_SPACE

    # ring roads at d ~3.5, 5.5, 8.5, 11.5 (x f), plus outer perimeter.
    # Tolerance scales with f so each ring stays one cell wide.
    for r in range(n):
        for c in range(n):
            d = sqrt((r - centre[0]) ** 2 + (c - centre[1]) ** 2)
            for ring in (3.5 * f, 5.5 * f, 8.5 * f, 11.5 * f):
                if abs(d - ring) < 0.25 * f:
                    grid.at(r, c).land_use = LandUse.ROAD
                    break

    # 4 radial spokes outward from the centre
    for i in range(n):
        if i != centre[0]:
            grid.at(i, centre[1]).land_use = LandUse.ROAD
        if i != centre[1]:
            grid.at(centre[0], i).land_use = LandUse.ROAD
    # outer perimeter
    for i in range(n):
        grid.at(0, i).land_use = LandUse.ROAD
        grid.at(n - 1, i).land_use = LandUse.ROAD
        grid.at(i, 0).land_use = LandUse.ROAD
        grid.at(i, n - 1).land_use = LandUse.ROAD

    def _o(k: float) -> int:
        return max(1, int(round(k * f)))

    # amenities on the mid-income / EWS ring boundaries
    for (dr, dc) in [(-_o(9), 0), (_o(9), 0), (0, -_o(9)), (0, _o(9))]:
        r, c = centre[0] + dr, centre[1] + dc
        if 0 <= r < n and 0 <= c < n:
            grid.at(r, c).land_use = LandUse.SCHOOL
    for (dr, dc) in [(-_o(7), -_o(7)), (-_o(7), _o(7)), (_o(7), -_o(7)), (_o(7), _o(7))]:
        r, c = centre[0] + dr, centre[1] + dc
        if 0 <= r < n and 0 <= c < n:
            grid.at(r, c).land_use = LandUse.PUBLIC_SERVICES
    grid.at(centre[0] - _o(2), centre[1] + _o(2)).land_use = LandUse.HEALTHCARE
    grid.at(centre[0] + _o(2), centre[1] - _o(2)).land_use = LandUse.HOTEL_GUESTHOUSE

    # industry / warehouse on east edge
    for r in range(_o(3), _o(10)):
        grid.at(r, n - 2).land_use = LandUse.LIGHT_INDUSTRY
    for r in range(_o(10), _o(14)):
        grid.at(r, n - 2).land_use = LandUse.WAREHOUSE
    # solar farm on west edge
    for r in range(_o(8), _o(18)):
        grid.at(r, 1).land_use = LandUse.SOLAR_FARM

    _set_default_height(grid, seed=seed)
    _set_default_albedo_and_vegetation(grid)
    return grid


# ---------------------------------------------------------------------------
# Archetype 5: BASELINE 2 - "plan as delivered" Zirakpur ribbon sprawl
# ---------------------------------------------------------------------------

# The designed town's BUILT programme, counted from optimised_sa.geojson
# parcels. Baseline 2 must reproduce these counts EXACTLY -
# If Baseline 2 under-provided schools/parks like real Zirakpur does, it
# would have less floor area, less demand, and would look CHEAPER - the
# comparison would degenerate into "fewer services cost less". Arrangement
# SPEC_20260812.md; under-provision is told in the discussion chapter with
# the GMADA plan's own quotes, not smuggled into the energy accounts.)
_B2_PROGRAMME = {
    LandUse.RESIDENTIAL_HIGH: 224,
    LandUse.RESIDENTIAL_MID: 125,
    LandUse.RESIDENTIAL_LOW: 44,
    LandUse.SCHOOL: 85,
    LandUse.LIGHT_INDUSTRY: 35,
    LandUse.RELIGIOUS: 25,
    LandUse.SHOPPING_CENTRE: 17,
    LandUse.PARKING_LOT: 17,
    LandUse.WAREHOUSE: 15,
    LandUse.HEALTHCARE: 9,
    LandUse.OFFICE: 9,
    LandUse.PUBLIC_SERVICES: 9,
    LandUse.RETAIL_HIGHSTREET: 7,
    LandUse.HOTEL_GUESTHOUSE: 4,
    LandUse.RESTAURANT_FOOD: 4,
}


def zirakpur_ribbon(seed: int = 0) -> Grid:
    """BASELINE 2 v4 - "Unplanned Conventional": Table 6-1's adopted land
    budget grown ORGANICALLY along the real highway skeleton.

    v4, (the author: "the baseline 2 still looks weird, it is too
    ordered and structured unlike the actual zirakpur... you dont see much
    agriculture or green land, only pockets of it"). v3 had the right
    BUDGET - Table 6-1, Proposed Land Use Distribution 2031, GMADA Revised
    Master Plan (extract in _spec/sources/), agriculture ABSENT from the
    table - but laid it out as a centred square with a uniform superblock
    lattice, i.e. a planned town that merely under-builds roads. v4 keeps
    EVERY v3 cell count and replaces only the GEOMETRY with a seeded
    growth process copying how Zirakpur actually assembled:

      * the crossroads skeleton: the NS highway (NH-7 Ambala-Chandigarh),
        the EW highway (Patiala / Dera Bassi road) and the Old Ambala Road
        diagonal, plus short colony stubs - the SAME ~190 road cells
        (7.60% of the site, the adopted share)
      * development ACCRETES from the corridors with seeded leapfrogging:
        ragged edges, detached pockets, and TRAPPED FIELDS left inside the
        fabric (the satellite's green pockets) instead of a farmland ring
        around a tidy square
      * commercial takes the corridor frontage ("20-25 banquet halls
        located along major roads"), industry sits in four UNBUFFERED
        pockets (the Morthikri / stone-crusher pattern), institutions are
        strung along roads wherever land was left, parks are leftover
        scraps - ~15 fragments totalling the 43-cell budget
      * housing fills each accreted pocket as an income-segregated colony
        (kothi pockets, builder-floor pockets, EWS pockets), which is how
        plotted colonies actually sell

    Same 54,794-household programme as the designed town, all LOW-RISE
    (SHORT-tier flats + plotted kothis), no TALL tier, no spine - the
    contrast stays a town WITH a vertical gradient against one WITHOUT.

    NOT RIGGED: every land-use total is the adopted Table 6-1 figure; only
    the arrangement follows the measured growth pattern. It scores badly
    because 29 institutional cells cannot serve 459 residential ones
    however they are strung, which is the plan's own admission:
    "Institutional & parks use needs enhancement as it can be seen very
    low in existing Land use distribution."

    Returns
    -------
    Grid
        Baseline 2 v4: adopted budget, organic corridor-growth geometry.
    """
    from collections import deque
    rng = random.Random(seed)
    grid = make_thesis_grid()
    n = grid.n_rows
    for cell in grid.all_cells():
        cell.land_use = LandUse.OPEN_SPACE

    # ---- water FIRST (exogenous, same site as every layout) so nothing
    # is ever placed on it - the v3 overwrite bug cannot recur ------------
    blue: set = set()
    try:
        import json
        from pathlib import Path
        _p = (Path(__file__).parent.parent / "outputs" / "geojson3d"
              / "optimised_sa.geojson")
        for _f in json.loads(_p.read_text(encoding="utf-8"))["features"]:
            _pr = _f.get("properties") or {}
            if (_pr.get("role") == "parcel"
                    and _pr.get("land_use") == "blue_space"):
                blue.add((int(_pr["row"]), int(_pr["col"])))
    except Exception:
        blue = {(n - 3, c) for c in range(2, 45)}
    for (r, c) in blue:
        grid.at(r, c).land_use = LandUse.BLUE_SPACE

    def open_cell(r, c):
        return (0 <= r < n and 0 <= c < n
                and grid.at(r, c).land_use == LandUse.OPEN_SPACE)

    # ---- roads: crossroads + diagonal + colony stubs = ~190 cells -------
    # Zirakpur exists because two highways cross. 7.60% of cells is the
    # Table 6-1 share, same as v3 - just no longer a uniform lattice.
    roads: set = set()

    def stamp(r, c):
        if open_cell(r, c):
            roads.add((r, c))

    HW_COL, HW_ROW = 24, 26
    for r in range(n):
        stamp(r, HW_COL)                      # NS highway (NH-7)
    for c in range(n):
        stamp(HW_ROW, c)                      # EW highway (Patiala road)
    r, c = 44, 4                              # Old Ambala Road diagonal
    while r > 9 and c < 42:
        stamp(r, c)
        if rng.random() < 0.85:
            r -= 1
        c += 1
    # v9: 250 road cells,
    # not 190. Justified by the plan's own measurement style: the EXISTING
    # land-use table books roads at 3.87% because colony-internal streets
    # hide inside the "Colonies" category (Table 3-1) - drawing colonies
    # at cell scale surfaces them, so 10% of cells as streets is the
    # honest cell-resolution total (Tier 3, derived).
    corridor = sorted(roads)                  # stubs bud off the corridors
    guard = 0
    while len(roads) < 250 and guard < 4000:
        guard += 1
        br, bc = corridor[rng.randrange(len(corridor))]
        dr, dc = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        for step in range(1, rng.randint(3, 6) + 1):
            rr, cc = br + dr * step, bc + dc * step
            if (rr, cc) in roads or not open_cell(rr, cc):
                break
            stamp(rr, cc)
            if len(roads) >= 250:
                break
    for (r, c) in roads:
        grid.at(r, c).land_use = LandUse.ROAD

    # ---- v5: TWO big green
    # VOIDS in the middle of town - the trapped fields/floodplain blocks
    # he traced at ~1.01 km2 and ~0.59 km2 - the only large green the
    # satellite shows. Tagged agri_belt (they are FIELDS, not parks; the
    # 43-cell Table 6-1 park budget stays separate as small scraps).
    # Development wraps around them; everything else unbuilt renders as
    # brown waste/vacant land in the viewer.
    voids: set = set()
    for (vr, vc), target in (((17, 30), 101), ((33, 16), 59)):
        qq, seen = deque([(vr, vc)]), {(vr, vc)}
        got = 0
        while qq and got < target:
            rc = qq.popleft()
            if open_cell(*rc) and rc not in roads and rc not in voids:
                voids.add(rc)
                grid.at(*rc).amenity_subtype = "agri_belt"
                got += 1
            nbs = [(rc[0] + dr, rc[1] + dc)
                   for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            rng.shuffle(nbs)
            for nb in nbs:
                if nb not in seen and 0 <= nb[0] < n and 0 <= nb[1] < n:
                    seen.add(nb)
                    qq.append(nb)

    # ---- distance-to-road field (multi-source BFS) ----------------------
    dist = {rc: 0 for rc in roads}
    q = deque(roads)
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < n and 0 <= cc < n and (rr, cc) not in dist:
                dist[(rr, cc)] = dist[(r, c)] + 1
                q.append((rr, cc))

    # ---- organic accretion: 863 developed (non-road) cells --------------
    # Acceptance decays with distance from a road; leapfrog seeds detach
    # pockets; every rejection can leave a TRAPPED FIELD inside the fabric.
    N_DEV = 944 + 43 + 145                    # v9: +145 commercial cells so
                                              # commercial TOTAL = 330 = 13.2%
                                              # of site = Table 6-1 mixed use
                                              # 7.40% + measured commercial
                                              # 5.93% (Table 3-1) EXACTLY.
                                              # Industry stays 135 = 5.4% =
                                              # the plan's 5.39%.
                                              # "we need to still
                                              # roughly follow the pdf /
                                              # zirakpur land distribution".
    grown: set = set()
    frontier: list = []

    def push(rc):
        if (rc not in grown and rc not in roads and rc not in voids
                and open_cell(*rc)):
            frontier.append(rc)

    for (rr, cc) in roads:
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            push((rr + dr, cc + dc))
    # v6
    # colonies/blocks... no empty barren land OUTSIDE the buildings,
    # just some empty space BETWEEN the colonies"): STRATIFIED seeds -
    # one jittered seed in every ~7x7 patch of the site - and a nearly
    # FLAT acceptance, so irregular colonies appear edge to edge and the
    # waste land is the interstitial gaps between them, never a barren
    # margin around a corridor town.
    # v8: 8x8 seed lattice reaching the boundary rows/cols + a flatter
    # acceptance, so colonies run to the site edge and the leftover
    # green/dirt sits INSIDE as gaps, not as an outer margin
    # "still a lot of green area outside").
    for gr in range(8):
        for gc in range(8):
            push((2 + gr * 6 + rng.randrange(-1, 3),
                  2 + gc * 6 + rng.randrange(-1, 3)))
    while len(grown) < N_DEV:
        if not frontier:
            push((rng.randrange(2, n - 2), rng.randrange(2, n - 2)))
            continue
        i = rng.randrange(len(frontier))
        frontier[i], frontier[-1] = frontier[-1], frontier[i]
        rc = frontier.pop()
        if rc in grown or rc in voids or not open_cell(*rc):
            continue
        d = dist.get(rc, 99)
        p = 0.48 if d <= 1 else 0.38
        if rng.random() > p:
            if rng.random() < 0.5:
                frontier.append(rc)           # may still develop later
            continue
        grown.add(rc)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            push((rc[0] + dr, rc[1] + dc))

    unassigned = set(grown)

    def road_adjacent(rc):
        return any((rc[0] + dr, rc[1] + dc) in roads
                   for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)))

    def take(want, pool):
        got = []
        for rc in pool:
            if len(got) >= want:
                break
            if rc in unassigned:
                got.append(rc)
                unassigned.discard(rc)
        return got

    # ---- commercial ribbon on the corridor frontage ---------------------
    front = [rc for rc in sorted(grown) if road_adjacent(rc)]
    rng.shuffle(front)
    pool = front + [rc for rc in sorted(grown) if not road_adjacent(rc)]
    for lu, want in ((LandUse.SHOPPING_CENTRE, 110),
                     (LandUse.RETAIL_HIGHSTREET, 40),
                     (LandUse.OFFICE, 20),
                     (LandUse.HOTEL_GUESTHOUSE, 8),
                     (LandUse.RESTAURANT_FOOD, 7),
                     (LandUse.PARKING_LOT, 12)):
        for rc in take(want, pool):
            grid.at(*rc).land_use = lu

    # ---- industry: four unbuffered pockets (the Morthikri pattern) ------
    for lu, want in ((LandUse.LIGHT_INDUSTRY, 34),
                     (LandUse.LIGHT_INDUSTRY, 33),
                     (LandUse.LIGHT_INDUSTRY, 33),
                     (LandUse.WAREHOUSE, 35)):
        placed = 0
        while placed < want and unassigned:
            cand = sorted(unassigned)
            s = cand[rng.randrange(len(cand))]
            qq, seen = deque([s]), {s}
            while qq and placed < want:
                rc = qq.popleft()
                if rc in unassigned:
                    unassigned.discard(rc)
                    grid.at(*rc).land_use = lu
                    placed += 1
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nb = (rc[0] + dr, rc[1] + dc)
                    if nb in unassigned and nb not in seen:
                        seen.add(nb)
                        qq.append(nb)

    # ---- 29 institutional cells strung along the roads ------------------
    inst_pool = ([rc for rc in sorted(unassigned) if road_adjacent(rc)]
                 + [rc for rc in sorted(unassigned) if not road_adjacent(rc)])
    rng.shuffle(inst_pool)
    for lu, want in ((LandUse.SCHOOL, 16), (LandUse.HEALTHCARE, 5),
                     (LandUse.PUBLIC_SERVICES, 4), (LandUse.RELIGIOUS, 4)):
        for rc in take(want, inst_pool):
            grid.at(*rc).land_use = lu

    # ---- parks: 43 cells of SMALL SCATTERED SCRAPS ("little green:
    # small parks",. The two BIG greens are the field
    # VOIDS above, which he measured on the satellite - they are not
    # parks and do not spend the Table 6-1 park budget.
    parks = 0
    guard = 0
    while parks < 43 and guard < 2000 and unassigned:
        guard += 1
        cand = sorted(unassigned)
        s = cand[rng.randrange(len(cand))]
        for rc in take(min(rng.randint(1, 2), 43 - parks), [s]):
            parks += 1                        # stays OPEN_SPACE
            grid.at(*rc).amenity_subtype = "park_neighbourhood"

    # ---- v9: MIXED-USE ribbon fabric - the Table 6-1 category the budget
    # never spent (Mixed Land Use 7.40% + measured commercial 5.93%): 145
    # more commercial cells, corridor-first, so total commercial = 330 =
    # 13.2% of site = the plan's mixed+commercial EXACTLY. Industry is NOT
    # added (135 = the plan's 5.39% already). NON-residential on purpose:
    # households stay the constant; institutional under-provision stays
    # the finding..)
    mixed_pool = ([rc for rc in sorted(unassigned) if road_adjacent(rc)]
                  + [rc for rc in sorted(unassigned) if not road_adjacent(rc)])
    rng.shuffle(mixed_pool)
    for lu, want in ((LandUse.SHOPPING_CENTRE, 50),
                     (LandUse.RETAIL_HIGHSTREET, 35),
                     (LandUse.RESTAURANT_FOOD, 20),
                     (LandUse.HOTEL_GUESTHOUSE, 10),
                     (LandUse.OFFICE, 30)):
        for rc in take(want, mixed_pool):
            grid.at(*rc).land_use = lu

    # ---- housing: each remaining pocket is an income-segregated colony --
    # v7... more smaller kothis
    # (accommodate less households per cell) so more cells need to have
    # housing"): LOW/MID move to the GROUND tier (G+1/G+2 solo houses and
    # builder floors on partially built-out plots, 0.45x floor area), so
    # the SAME 54,794 households need 583 residential cells, not 459:
    #   LOW  9,000/42.7 = 211 HH/cell -> 104 cells (was 70 at SHORT)
    #   MID  9,000/100  =  90 HH/cell -> 274 cells (was 184 at SHORT)
    #   HIGH kothi        40 HH/cell  -> 205 cells (unchanged)
    needs = ([LandUse.RESIDENTIAL_HIGH] * 205
             + [LandUse.RESIDENTIAL_MID] * 274
             + [LandUse.RESIDENTIAL_LOW] * 104)
    left = set(unassigned)
    comps = []
    while left:
        s = left.pop()
        comp, qq = [s], deque([s])
        while qq:
            rc = qq.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (rc[0] + dr, rc[1] + dc)
                if nb in left:
                    left.discard(nb)
                    comp.append(nb)
                    qq.append(nb)
        comps.append(sorted(comp))
    rng.shuffle(comps)
    k = 0
    for comp in comps:
        for rc in comp:
            grid.at(*rc).land_use = needs[k]
            k += 1

    # ---- GALLIS
    # small streets / gallis"): the deterministic 40-ft lane overlay, so
    # every colony pocket fills with the thin internal streets the
    # satellite shows. Same algorithm as the designed town - the
    # DIFFERENCE stays the road hierarchy above it (7.6% vs 25%), not
    # the existence of lanes, which every real colony has.
    from .road_network import assign_local_streets
    assign_local_streets(grid)

    # v8
    # need to be more gallis"): GRID-IRON gallis - a lane on EVERY shared
    # boundary between two BUILT cells (v9: all fabric, not just housing),
    # not just the dendritic access minimum. Real plotted colonies run a
    # galli along every plot row.
    from core.grid import StreetEdge
    have = {(e.a, e.b) if e.a <= e.b else (e.b, e.a)
            for e in grid.street_edges if e.kind == "local_street"}
    res_ids = {(c.row, c.col) for c in grid.all_cells()
               if c.has_building}
    for (rr, cc) in sorted(res_ids):
        for nb in ((rr + 1, cc), (rr, cc + 1)):
            if nb in res_ids:
                key = ((rr, cc), nb)
                if key not in have:
                    have.add(key)
                    grid.street_edges.append(StreetEdge(
                        a=(rr, cc), b=nb, kind="local_street",
                        width_m=12.0, modes=("motor", "cycle", "foot")))

    _set_default_height(grid, seed=seed)
    _set_default_albedo_and_vegetation(grid)

    # ---- GROUND TIER ONLY (v7): solo houses / builder floors - Baseline
    # 2 never gets the spine_gradient pass, and from v7 not even SHORT
    # flats: real Zirakpur is "all mostly solo houses" ------------
    cfg = load_config()
    for cell in grid.all_cells():
        if cell.land_use in (LandUse.RESIDENTIAL_LOW, LandUse.RESIDENTIAL_MID):
            cell.height_tier = HeightTier.GROUND
            cell.height_m = cfg.height_for(HeightTier.GROUND.value)
    return grid


# ---------------------------------------------------------------------------
# Available archetypes
# ---------------------------------------------------------------------------
ARCHETYPES = {
    "chandigarh_sector": chandigarh_sector,
    "dispersed_low": dispersed_low,
    "compact_centre": compact_centre,
    "radial": radial,
    # designed town's exact built programme arranged as Zirakpur ribbon
    # sprawl, no solar. NOT part of the SA seed set; a comparison town.
    "zirakpur_ribbon": zirakpur_ribbon,
}


def generate(name: str, seed: int = 0) -> Grid:
    """Public entry point: produce a layout by archetype name.

    Returns
    -------
    Grid
        Generated layout for the requested archetype.
    """
    if name not in ARCHETYPES:
        raise ValueError(f"Unknown archetype {name!r}. "
                         f"Choose from {sorted(ARCHETYPES)}.")
    return ARCHETYPES[name](seed=seed)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from collections import Counter

    for name in ARCHETYPES:
        grid = generate(name)
        counts = Counter(c.land_use for c in grid.all_cells())
        print(f"\n=== {name} ===")
        print(f"  {grid}")
        for lu, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            target = DEFAULT_AREA_TARGETS.get(lu, 0.0)
            actual = n / grid.total_cells
            mark = "OK " if abs(actual - target) < 0.06 else "*  "
            print(f"  {mark}{lu.value:<28} {n:4d} cells  "
                  f"({actual:5.1%}, target {target:5.1%})")
