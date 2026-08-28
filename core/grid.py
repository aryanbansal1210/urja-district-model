"""The 2D grid of cells that holds a layout.

A `Grid` is a fixed-size N x M array of `Cell` objects, each at a known
(x, y) location in metres. A layout is just a particular assignment of
`LandUse` to every cell. Optimisation, scoring, and visualisation all read
the same `Grid` shape.

Coordinates: cell (row=0, col=0) sits at origin (0, 0). Row index increases
northwards (positive y), col index increases eastwards (positive x). This
matters for solar (south is negative y) and for prevailing-wind alignment.

A built cell carries a `height_tier` ("short" / "medium" / "tall") which is a
SECOND degree of freedom on top of land-use. Heights map to metres via the
config (e.g. short=12 m, medium=18 m, tall=27 m). Footprint stays the same
across tiers; floor count and households per cell scale with height.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, List, Optional

from .land_use import LandUse


class HeightTier(Enum):
    """Building height tiers per cell.

    GROUND (, Baseline 2 v7 only - no designed-town cell uses
    it): G+1/G+2 solo houses and builder floors on a PARTIALLY BUILT-OUT
    plotted colony - the real Zirakpur pattern (vacant plots interleaved;
    the Revised Master Plan's own Deviations chapter documents partially
    implemented colonies). Multiplier 0.45 = ~G+1.5 average against the
    6-storey reference (Tier 3, satellite-derived built-out share).
    """
    GROUND = "ground"
    SHORT = "short"
    MEDIUM = "medium"
    TALL = "tall"


# ---------------------------------------------------------------------------
# Cell
# ---------------------------------------------------------------------------
@dataclass
class Cell:
    """One cell of the master-plan grid.

    Attributes
    ----------
    row, col : int
        Discrete grid indices. (0, 0) is the south-west corner.
    centre_x_m, centre_y_m : float
        Centre point of the cell in metres relative to grid origin.
    cell_size_m : float
        Side length of the (square) cell in metres.
    land_use : LandUse
        What activity occupies this cell. Default is OPEN_SPACE so an empty
        grid is at least feasible.
    height_m : float
        Building height for this cell. 0 if there is no building. Used for
        solar-access scoring against southern neighbours.
    albedo : float
        Surface reflectance in [0, 1]. 0.2 for plain asphalt, 0.6 for high-
        albedo cool surfaces. Used by the heat-island score.
    vegetation_fraction : float
        Share of cell footprint covered by vegetation, in [0, 1]. Roads and
        most buildings have low values; parks have ~1.0.
    building_axis_deg : float
        Orientation of the cell's dominant building long-facade axis in
        degrees clockwise from north (0 = N-S long axis, 45 = NE-SW,
        90 = E-W, 135 = NW-SE). Decided by SA on built cells; ignored
        on non-built cells. Propagates into Stage A wind-alignment metric
        and Stage B/C facade-orientation cooling + BIPV multipliers.
 (Priority 2): added so facade orientation can be an
        SA decision rather than YAML-fixed in district_composition.yaml.
    """

    row: int
    col: int
    centre_x_m: float
    centre_y_m: float
    cell_size_m: float
    land_use: LandUse = LandUse.OPEN_SPACE
    height_m: float = 0.0
    height_tier: Optional[HeightTier] = None
    albedo: float = 0.20
    vegetation_fraction: float = 0.0
    building_axis_deg: float = 0.0  # default N-S long axis
    # (Item 2): per-RELIGIOUS-cell faith tag, populated by
    # `layout.faith_assignment.assign_faiths_to_religious_cells` from
    # Punjab Census 2011 shares. None for non-RELIGIOUS cells. Read by
    # `Economics.behavioural_demand_multiplier` to apply per-faith
    # festival-day demand bumps on the `fs` day-type.
    faith: Optional[str] = None
    # (Item 3): discrete carport-site marker. Populated by
    # `layout.carport_siting.place_carports` on a subset of eligible
    # cells (those near healthcare/office/industry, balanced across
    # quadrants). When True, this cell hosts a carport PV array.
    # `EnergyNetwork.total_carport_potential_kwp` uses the site-specific
    # per-cell kWp when any sites are tagged; falls back to the legacy
    # "all eligible × uptake" formula when no sites are marked
    # (back-compat for archetype layouts not yet sited).
    is_carport_site: bool = False
    #: cardinal degrees (clockwise from
    # north) where this cell's building entrance(s) face. Empty list
    # for non-built cells. Most cells have 1 entrance; RETAIL_HIGHSTREET
    # cells that ALSO have a road 4-neighbour get TWO entrances (one
    # road-side shop-front, one highstreet-side back-shop opening).
    # Computed by `layout.entrance_assignment.assign_entrances`.
    entrance_sides: List[int] = field(default_factory=list)
    #: BLUE_SPACE cells flagged as a
    # floating-PV deployment site by `layout.floating_pv_siting.assign_floating_pv_sites`.
    # Only cells in a 4-connected BLUE_SPACE cluster of >=
    # `floating_pv.site_selection.min_cluster_size` (default 2) get the
    # flag; isolated water bodies remain panel-free for aesthetic + BOS-
    # cost reasons. False / None on non-BLUE_SPACE cells.
    is_floating_pv_site: bool = False
    floating_pv_cluster_id: Optional[int] = None
    #: cells that the SA optimiser must NOT mutate.
    # Used to reserve deterministic structure the optimiser kept breaking
    # via soft metrics: the arterial road skeleton (so amenities can never
    # be placed on a road corridor / intersection) and a clean rectangular
    # solar-farm zone (so no buildings end up embedded in the solar field).
    # Set by `layout.locked_zones.apply_locked_zones`. All optimiser moves
    # skip locked cells as both donor and target.
    locked: bool = False
    # (batch-A Task 5): street-furniture attributes on ROAD cells,
    # tagged post-anneal by `layout.street_furniture.place_street_furniture`.
    #   has_street_trees: avenue/street trees line this road segment; cools the
    #     BUILT cells adjacent to it (shade + evapotranspiration) via
    #     `EnergyNetwork._microclimate_cooling_multiplier`.
    #   streetlight_type: "solar" (off-grid self-powered pole -> adds NO grid
    #     load) or "grid" (mains pole -> adds a night-shaped base load). None on
    #     non-ROAD cells.
    has_street_trees: bool = False
    streetlight_type: Optional[str] = None
    # (Part 4): segment-aware streetlight decision. Contiguous ROAD
    # cells form a "segment" (a connected run extending from the built/grid edge);
    # the whole segment chooses grid-vs-solar TOGETHER, because grid lamps along a
    # run share ONE amortised cable trench. streetlight_segment_id groups cells of
    # one run; streetlight_reason is a short human string for the viewer hover
    # (e.g. "grid: shared trench 0.6km amortised" / "solar: cable run > premium").
    streetlight_segment_id: Optional[int] = None
    streetlight_reason: Optional[str] = None
    # (batch-A): hover sub-type within a single land-use, tagged
    # post-anneal by `layout.amenity_subtype.assign_amenity_subtypes` (like the
    # RELIGIOUS faith tag). SCHOOL -> "primary"/"secondary" (URDPFI), HEALTHCARE
    # -> "UPHC"/"UCHC" (IPHS). None on other cells. Cosmetic (viewer hover); no
    # energy-model effect.
    amenity_subtype: Optional[str] = None
    # STAGE-: road HIERARCHY on ROAD cells.
    # road_class in {"arterial", "collector", "local"}; None on non-ROAD cells.
    # road_width_m is the right-of-way (ROW) width in metres - the honest
    # road-area accounting unit: a 24 m collector inside a 100 m cell counts
    # 24 x 100 m2 of ROW, the cell remainder is verge + building frontage.
    # Tagged GEOMETRICALLY by `layout.road_network.tag_road_classes` (the
    # geojson round-trip persists the values, but every pass re-derives from
    # geometry because locked flags do NOT survive the round-trip).
    road_class: Optional[str] = None
    road_width_m: float = 0.0

    @property
    def is_residential(self) -> bool:
        return self.land_use.is_residential

    @property
    def has_building(self) -> bool:
        return self.land_use.has_buildings


# ---------------------------------------------------------------------------
# Street / path EDGES (Stage-/
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StreetEdge:
    """A sub-cell street or path SEGMENT between two 4-adjacent cells (the
    register-B16 cell-EDGE road model).

    GEOMETRY: a CENTERLINE segment from the centre of cell `a` to the
    centre of cell `b`, crossing their shared boundary perpendicular - so a
    chain of edges is a physically CONNECTED street, and a segment whose
    far endpoint is a ROAD cell is the junction where the lane meets the
    road network. Local access streets (Stage and greenway paths
    (Stage are far narrower than a 100 m cell, so they live as these
    sub-cell segments instead of consuming whole cells - the fix for the
    ~30% road over-count the full-cell prototype produced (B16).

    ROW area = segment length (one cell side, centre-to-centre) x width_m,
    debited in REPORTING only (land_use is untouched, so demand and the
    energy LP are invariant by construction). Segments ending in a ROAD
    cell count HALF (the road-side half already lies inside the road ROW).

    kind: "local_street" access lane: shared-space motor+cycle+foot,
          IRC:103 shared street) or "greenway_path" foot+cycle path
          through parks/greenways/belt - inside park area, no ROW debit).
    modes: subset of ("motor", "cycle", "foot").
    """
    a: Tuple[int, int]
    b: Tuple[int, int]
    kind: str
    width_m: float
    modes: Tuple[str, ...]

    def touches(self, cell_id: Tuple[int, int]) -> bool:
        return cell_id == self.a or cell_id == self.b


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------
@dataclass
class Grid:
    """A 2D grid of cells covering the district.

    For the MSc thesis: 50 x 50 cells of 100 m x 100 m = 5 km x 5 km
    (Stage- re-grid,; previously 25 x 25 of 200 m).
    """

    n_rows: int
    n_cols: int
    cell_size_m: float
    cells: List[List[Cell]] = field(default_factory=list)
    #: spatial siting markers for Stage C utility
    # plants (biomass CHP, biogas, WTE). Populated by
    # ``layout.plant_siting.place_stage_c_plants`` after SA convergence
    # so the chosen cells are exported in GeoJSON and the viewer can
    # render them. Empty until placed.
    plant_placements: Dict[str, "PlantPlacement"] = field(default_factory=dict)
    # STAGE-/: sub-cell street/path edges (local access
    # lanes + greenway paths) on cell boundaries. Populated POST-anneal by
    # `layout.road_network.assign_local_streets` and
    # `layout.path_network.assign_path_network`; empty during the anneal.
    street_edges: List[StreetEdge] = field(default_factory=list)

    @classmethod
    def empty(cls, n_rows: int, n_cols: int, cell_size_m: float) -> "Grid":
        """Create a grid where every cell is OPEN_SPACE.

        Returns
        -------
        Grid
            New grid with generated cell coordinates and default land use.
        """
        cells: List[List[Cell]] = []
        for r in range(n_rows):
            row_cells: List[Cell] = []
            for c in range(n_cols):
                cx = (c + 0.5) * cell_size_m
                cy = (r + 0.5) * cell_size_m
                row_cells.append(
                    Cell(
                        row=r, col=c,
                        centre_x_m=cx, centre_y_m=cy,
                        cell_size_m=cell_size_m,
                    )
                )
            cells.append(row_cells)
        return cls(
            n_rows=n_rows, n_cols=n_cols,
            cell_size_m=cell_size_m, cells=cells,
        )

    def copy(self) -> "Grid":
        """Deep-copy the grid. Required by the simulated annealer to track
        the best-seen layout while the working state is mutated in place.

        Returns
        -------
        Grid
            Independent copy of this grid and its cells.
        """
        new_cells: List[List[Cell]] = []
        for row in self.cells:
            new_row: List[Cell] = []
            for c in row:
                new_row.append(Cell(
                    row=c.row, col=c.col,
                    centre_x_m=c.centre_x_m, centre_y_m=c.centre_y_m,
                    cell_size_m=c.cell_size_m,
                    land_use=c.land_use,
                    height_m=c.height_m,
                    height_tier=c.height_tier,
                    albedo=c.albedo,
                    vegetation_fraction=c.vegetation_fraction,
                    building_axis_deg=c.building_axis_deg,
                    faith=c.faith,
                    is_carport_site=c.is_carport_site,
                    entrance_sides=list(c.entrance_sides),
                    is_floating_pv_site=c.is_floating_pv_site,
                    floating_pv_cluster_id=c.floating_pv_cluster_id,
                    locked=c.locked,
                    has_street_trees=c.has_street_trees,
                    streetlight_type=c.streetlight_type,
                    streetlight_segment_id=c.streetlight_segment_id,
                    streetlight_reason=c.streetlight_reason,
                    amenity_subtype=c.amenity_subtype,
                    road_class=c.road_class,
                    road_width_m=c.road_width_m,
                ))
            new_cells.append(new_row)
        return Grid(
            n_rows=self.n_rows, n_cols=self.n_cols,
            cell_size_m=self.cell_size_m, cells=new_cells,
            plant_placements=dict(self.plant_placements),
            # StreetEdge is frozen (immutable) so sharing instances is safe.
            street_edges=list(self.street_edges),
        )

    # ----- access ------------------------------------------------------
    def at(self, row: int, col: int) -> Cell:
        """Return the cell at (row, col). Raises IndexError if out of bounds.

        Returns
        -------
        Cell
            Cell at the requested grid coordinates.
        """
        if not (0 <= row < self.n_rows and 0 <= col < self.n_cols):
            raise IndexError(f"({row}, {col}) outside {self.n_rows}x{self.n_cols}")
        return self.cells[row][col]

    def all_cells(self) -> Iterator[Cell]:
        """Iterate over every cell in row-major order.

        Returns
        -------
        Iterator[Cell]
            Generator over all cells from south-west toward north-east.
        """
        for row in self.cells:
            for cell in row:
                yield cell

    def cells_of(self, land_use: LandUse) -> List[Cell]:
        """Return all cells with the given LandUse.

        Returns
        -------
        List[Cell]
            Cells whose land use exactly matches `land_use`.
        """
        return [c for c in self.all_cells() if c.land_use == land_use]

    @property
    def total_cells(self) -> int:
        return self.n_rows * self.n_cols

    @property
    def total_area_m2(self) -> float:
        return self.total_cells * self.cell_size_m ** 2

    # ----- neighbour queries ------------------------------------------
    def neighbours_4(self, row: int, col: int) -> List[Cell]:
        """Return the up-to-4 von-Neumann neighbours (N, S, E, W).

        Returns
        -------
        List[Cell]
            Orthogonally adjacent in-bounds cells.
        """
        out: List[Cell] = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            r, c = row + dr, col + dc
            if 0 <= r < self.n_rows and 0 <= c < self.n_cols:
                out.append(self.at(r, c))
        return out

    def neighbours_8(self, row: int, col: int) -> List[Cell]:
        """Return the up-to-8 Moore neighbours.

        Returns
        -------
        List[Cell]
            Adjacent in-bounds cells, including diagonals.
        """
        out: List[Cell] = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r, c = row + dr, col + dc
                if 0 <= r < self.n_rows and 0 <= c < self.n_cols:
                    out.append(self.at(r, c))
        return out

    def cells_within_radius(self, row: int, col: int,
                             radius_m: float) -> List[Cell]:
        """Return cells whose centres fall within `radius_m` of (row, col).

        Useful for accessibility metrics (e.g. cells within 400 m for the
        15-minute-city walking-distance scoring).

        Returns
        -------
        List[Cell]
            Cells within the supplied radius, excluding the anchor cell.
        """
        anchor = self.at(row, col)
        out: List[Cell] = []
        r2 = radius_m ** 2
        for cell in self.all_cells():
            dx = cell.centre_x_m - anchor.centre_x_m
            dy = cell.centre_y_m - anchor.centre_y_m
            if dx * dx + dy * dy <= r2 and cell is not anchor:
                out.append(cell)
        return out

    # ----- distance helpers -------------------------------------------
    @staticmethod
    def manhattan_distance(a: Cell, b: Cell) -> float:
        """L1 distance in metres. Approximates walking via grid streets.

        Returns
        -------
        float
            Manhattan distance between the two cell centres, in metres.
        """
        return (abs(a.centre_x_m - b.centre_x_m)
                + abs(a.centre_y_m - b.centre_y_m))

    @staticmethod
    def euclidean_distance(a: Cell, b: Cell) -> float:
        """L2 distance in metres. Approximates straight cable run.

        Returns
        -------
        float
            Straight-line distance between the two cell centres, in metres.
        """
        dx = a.centre_x_m - b.centre_x_m
        dy = a.centre_y_m - b.centre_y_m
        return (dx * dx + dy * dy) ** 0.5

    # ----- summary ----------------------------------------------------
    def land_use_counts(self) -> dict[LandUse, int]:
        """Histogram of land-use across the grid.

        Returns
        -------
        dict[LandUse, int]
            Count of cells by land-use enum.
        """
        counts: dict[LandUse, int] = {}
        for cell in self.all_cells():
            counts[cell.land_use] = counts.get(cell.land_use, 0) + 1
        return counts

    def __repr__(self) -> str:
        return (f"Grid({self.n_rows}x{self.n_cols} of "
                f"{self.cell_size_m:.0f} m, {self.total_cells} cells, "
                f"{self.total_area_m2 / 1e6:.1f} km²)")


# ---------------------------------------------------------------------------
# Standard configurations
# ---------------------------------------------------------------------------
def make_thesis_grid() -> Grid:
    """The grid sized for the MSc thesis: 5 km x 5 km at 100 m resolution.

    STAGE-: re-gridded 200 m -> 100 m per
    ``_spec/STAGE_F_100M_MIGRATION_SPEC.md`` (25x25x200 -> 50x50x100; the
    frozen "final 200 m model" is the low-density comparison
    point). Dimensions come from ``config/district_composition.yaml``
    ``site.grid_n_rows / grid_n_cols / cell_size_m`` (single source of
    truth, shared with ``core/requirements.py`` cell-area arithmetic);
    the historical 50/50/100 fallback keeps config-less callers working.

    Returns
    -------
    Grid
        A 50 x 50 grid with 100 m (1 ha) cells.
    """
    # Local import: keeps core.grid import-light for the many unit tests
    # that build explicit Grid.empty(...) fixtures without a config.
    # Review fix: only a MISSING config
    # file falls back to the defaults (config-less environments); a broken
    # config (YAML/validation error) must surface loudly, not silently
    # produce a default grid.
    from .config import load_config
    try:
        site = load_config().site
    except FileNotFoundError:
        site = {}
    return Grid.empty(
        n_rows=int(site.get("grid_n_rows", 50)),
        n_cols=int(site.get("grid_n_cols", 50)),
        cell_size_m=float(site.get("cell_size_m", 100.0)),
    )


if __name__ == "__main__":
    g = make_thesis_grid()
    print(g)
    print(f"  {g.total_cells} cells, side {g.cell_size_m:.0f} m, "
          f"area {g.total_area_m2 / 1e6:.1f} km²")
    counts = g.land_use_counts()
    print(f"  initial land-use: {dict((k.value, v) for k, v in counts.items())}")

    centre = g.at(12, 12)
    n4 = g.neighbours_4(12, 12)
    n8 = g.neighbours_8(12, 12)
    near = g.cells_within_radius(12, 12, 400.0)
    print(f"\nCentre cell at ({centre.centre_x_m:.0f}, {centre.centre_y_m:.0f}) m")
    print(f"  4-neighbours: {len(n4)}, 8-neighbours: {len(n8)}, "
          f"within 400 m: {len(near)}")
