"""Stage B energy network: turn a populated `Grid` into the data the
dispatch MILP needs.

Path-1 refactor: cells now carry separate base / cooling /
heating peak loads, plus a microclimate cooling adjustment that comes
from Stage A spatial context (proximity to OPEN_SPACE / BLUE_SPACE,
wind-aligned position, party-wall thermal coupling). Per-slice demand
is composed INLINE in `demand_by_slice_kw` from these peaks x the per-term
factors (`Economics.cooling_factor_for_month` / `cooling_daypart_factor` /
`heating_split_factor` / `lighting_seasonal_multiplier` + `ev_node_kw`).
NOTE: `Economics.daypart_multiplier` is NOT that path - it is a reduced
base+cooling+heating composite used only by one test and a __main__ demo.
This docstring claimed otherwise until.

Responsibilities:

  * `EnergyNode` per cell carrying decomposed peak loads + microclimate
    adjustment + rooftop / ground-mount PV ceiling.
  * `EnergyEdge` for every 4-neighbour ROAD-to-ROAD pair (HV cable
    permeability rule). Edges are placeholder topology for Stage D peer-
    to-peer flows; the Stage B MILP runs on a single bus aggregate.
  * Per-slice demand profile composed from the 144-slice economics.
  * Convenience loader `grid_from_geojson` for the on-disk SA layout.

All quantities use SI units: kW for power, kWh for energy, kWp for PV
nameplate, hours for time. Costs are not handled here; see
`energy.costs.Economics`.
"""

from __future__ import annotations

import copy
import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.building import building_from_cell
from core.config import DistrictConfig, load_config
from core.demographics import (
    DemandNorms,
    Demographics,
    load_demand_norms,
    load_demographics,
)
from core.grid import Cell, Grid, HeightTier
from core.land_use import LandUse, category_for

from .costs import Economics, load_economics


CellId = Tuple[int, int]

DEFAULT_OPTIMISED_GEOJSON = (
    Path(__file__).parent.parent / "outputs" / "geojson3d" / "optimised_sa.geojson"
)


# ---------------------------------------------------------------------------
# EnergyNode
# ---------------------------------------------------------------------------
@dataclass
class EnergyNode:
    """A single cell viewed from the energy-system perspective.

    Attributes
    ----------
    cell_id : (row, col)
        Identifier matching `Cell.row`, `Cell.col`.
    centre_x_m, centre_y_m : float
        Geographic centre (used for cable-length estimates).
    land_use : LandUse
    category_name : str or None
        BuildingCategory.name for built cells.
    peak_base_kw : float
        Base load (non-cooling, non-heating) at unity occupancy.
    peak_cooling_kw : float
        Cooling load at unity cooling factor (already adjusted by the
        cell's cooling-tech mix W/m² peak).
    peak_heating_kw : float
        Electric heating + geyser peak load (north India winter).
    microclimate_cooling_multiplier : float
        ∈ (0, 1]. Combines neighbour-vegetation cooling, blue-space
        proximity, wind alignment, party-wall coupling. Multiplies
        `peak_cooling_kw` before the per-slice cooling-factor mult.
    rooftop_pv_cap_kwp : float
    solar_farm_cap_kwp : float
    households : int
    is_residential : bool
    """

    cell_id: CellId
    centre_x_m: float
    centre_y_m: float
    land_use: LandUse
    category_name: Optional[str]
    peak_base_kw: float
    peak_cooling_kw: float
    peak_heating_kw: float
    microclimate_cooling_multiplier: float
    rooftop_pv_cap_kwp: float
    solar_farm_cap_kwp: float
    households: int
    is_residential: bool
    # per-cell PV-yield shading multiplier from neighbour heights.
    # 1.0 = unshaded; lower values penalise rooftop/ground PV yield when this
    # cell has S/SW/SE/E/W neighbours significantly taller than its own height
    # (built cells) or 1.5 m (SOLAR_FARM). Captures the Stage A geometric
    # outcome -> Stage B/C PV yield coupling that was previously missing.
    pv_shading_multiplier: float = 1.0
    # (Item 2): per-RELIGIOUS-cell faith tag from
    # `layout.faith_assignment` (Punjab Census 2011 shares). None for
    # non-RELIGIOUS nodes. Read by `Economics.behavioural_demand_multiplier`
    # to apply per-faith festival-day demand bumps on `fs` day-type slices.
    faith: Optional[str] = None

    @property
    def is_built(self) -> bool:
        return self.category_name is not None

    @property
    def is_solar_farm(self) -> bool:
        return self.land_use == LandUse.SOLAR_FARM

    @property
    def peak_demand_kw(self) -> float:
        """Approx aggregate peak (base + cooling + heating). For sizing only."""
        return (self.peak_base_kw
                + self.peak_cooling_kw * self.microclimate_cooling_multiplier
                + self.peak_heating_kw)


# ---------------------------------------------------------------------------
# EnergyEdge
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EnergyEdge:
    """A cable link between two ROAD cells (Stage D peer-to-peer placeholder)."""

    a: CellId
    b: CellId
    length_m: float


# ---------------------------------------------------------------------------
# EnergyNetwork
# ---------------------------------------------------------------------------
@dataclass
class EnergyNetwork:
    """The energy-side view of a populated Grid."""

    nodes: List[EnergyNode] = field(default_factory=list)
    edges: List[EnergyEdge] = field(default_factory=list)
    grid: Optional[Grid] = None
    layout_name: str = "unknown"
    # (Task 5): annual grid-powered street-lighting energy (kWh/yr)
    # from GRID-lit road cells only; SOLAR-lit roads are off-grid and contribute
    # 0. Added as a night-shaped district load in demand_by_slice_kw. 0 when the
    # grid carries no streetlight tags (back-compat).
    grid_streetlight_kwh_yr: float = 0.0
    # (solar thermal): the rooftop module efficiency the PV caps
    # were built with, carried through so the roof-competition constraint can
    # invert `kWp = roof_area x acceptance x eta` back to square metres. It
    # lives in district_composition.yaml and is applied inside
    # `building.deployable_pv_kwp`, so re-reading it anywhere else would be a
    # second source of truth for a number the caps already depend on.
    rooftop_module_efficiency: float = 0.1930
    # Caches keyed by economics object id (network is static during a Pareto
    # sweep; we just need any change in econ to invalidate). The dispatch
    # call chain hits demand_by_slice_kwh / pv_yield once per merit-order
    # evaluate; with ~1000 evaluates per coordinate-descent solve, caching
    # turns a 100s solve into a 5s solve.
    # REV-1: values are (econ, result) tuples - the pinned econ
    # reference guarantees the id-based key cannot be recycled while the
    # entry lives (see demand_by_slice_kwh).
    _demand_kwh_cache: dict = field(default_factory=dict)
    _yield_rooftop_cache: dict = field(default_factory=dict)
    _yield_farm_cache: dict = field(default_factory=dict)
    _yield_rooftop_oriented_cache: dict = field(
        default_factory=dict
    )

    # ---- factory -----------------------------------------------------
    @classmethod
    def from_grid(
        cls,
        grid: Grid,
        cfg: Optional[DistrictConfig] = None,
        norms: Optional[DemandNorms] = None,
        econ: Optional[Economics] = None,
        layout_name: str = "unknown",
        demographics: Optional[Demographics] = None,
    ) -> "EnergyNetwork":
        """Build the EnergyNetwork from a populated Grid + Economics.

        Decomposes each built cell's peak demand into base / cooling /
        heating and applies microclimate coupling based on Stage A
        spatial context (4-neighbour vegetation, blue-space proximity,
        wind alignment proxy, party-wall density).

        Caveat-8 fix: when ``norms.public_services`` carries a
        ``water_treatment_kwh_per_capita_per_year``, the district-total
        water-treatment + pumping load is split evenly across the
        PUBLIC_SERVICES cells and added to their ``peak_base_kw``.
        """
        if cfg is None:
            cfg = load_config()
        if norms is None:
            norms = load_demand_norms()
        if econ is None:
            econ = load_economics()
        if demographics is None:
            try:
                demographics = load_demographics()
            except Exception:
                demographics = None

        # (Item 2): tag RELIGIOUS cells with a faith if not
        # already tagged. Deterministic (sorted by row, col + Punjab
        # Census-2011 shares with min-1 floor for muslim/christian);
        # safe to re-run because faiths re-assign to the same cells
        # each time. Idempotent guard: only re-run if any RELIGIOUS
        # cell lacks a faith tag.
        from layout.faith_assignment import assign_faiths_to_religious_cells
        need_assign = any(
            c.faith is None
            for c in grid.all_cells()
            if c.land_use == LandUse.RELIGIOUS
        )
        if need_assign:
            assign_faiths_to_religious_cells(grid)

        # (Item 3): place discrete carport sites near
        # healthcare/office/industry, balanced across quadrants.
        # Idempotent: skipped if any cell already has is_carport_site
        # set (typical when grid was loaded from a GeoJSON that already
        # carries the tag). Deterministic (sorted by (dist, row, col)).
        from layout.carport_siting import place_carports
        if not any(c.is_carport_site for c in grid.all_cells()):
            place_carports(grid)

        #: per-cell entrance side(s).
        # Idempotent: re-runs only if no cell yet has entrance_sides
        # populated (older GeoJSONs without the property load empty).
        # Deterministic (road-adj / highstreet-two-door / nearest-road
        # fallback). See layout/entrance_assignment.py.
        from layout.entrance_assignment import assign_entrances
        if not any(c.entrance_sides for c in grid.all_cells()):
            assign_entrances(grid)

        #: tag deployable floating-PV
        # sites on BLUE_SPACE cells in clusters of >= min_cluster_size
        # (default 2). Idempotent: skipped when any cell already carries
        # `floating_pv_cluster_id` (typical when grid was loaded from a
        # GeoJSON that already ships the tag). Min cluster size is read
        # from `floating_pv.site_selection.min_cluster_size` via the
        # Economics object so the network honours the same YAML knob
        # the exporter uses.
        from layout.floating_pv_siting import assign_floating_pv_sites
        if not any(
            c.floating_pv_cluster_id is not None
            for c in grid.all_cells()
        ):
            assign_floating_pv_sites(
                grid,
                min_cluster_size=econ.floating_pv_min_cluster_size(),
            )

        gm_kwp_per_m2 = float(
            norms.solar.get("ground_mount_kwp_per_m2", 0.10)
        )

        # Caveat-8 (water-energy nexus): district baseload added to PUBLIC_SERVICES.
        water_kwh_cap_yr = float(
            norms.public_services.get("water_treatment_kwh_per_capita_per_year", 0.0)
        )
        population = demographics.total_population if demographics is not None else 0
        public_service_cells = [
            c for c in grid.all_cells() if c.land_use == LandUse.PUBLIC_SERVICES
        ]
        water_per_cell_kw = 0.0
        if (water_kwh_cap_yr > 0 and population > 0
                and len(public_service_cells) > 0):
            total_water_kwh_yr = population * water_kwh_cap_yr
            total_water_kw_continuous = total_water_kwh_yr / 8760.0
            water_per_cell_kw = total_water_kw_continuous / len(public_service_cells)

        # (Task 5): grid-powered street lighting. Total street-lighting
        # energy = per-capita norm x population, shared equally over ALL road
        # cells; only the GRID-lit ones draw from the grid (SOLAR-lit roads are
        # off-grid self-powered and add nothing). Added as a night-shaped
        # district load in demand_by_slice_kw. 0 when no road carries a
        # streetlight tag (untagged test grids / archetypes -> byte-exact).
        sl_kwh_cap_yr = float(
            norms.public_services.get("street_lighting_kwh_per_capita_per_year", 0.0)
        )
        road_cells = [c for c in grid.all_cells() if c.land_use == LandUse.ROAD]
        grid_lit_roads = sum(1 for c in road_cells if c.streetlight_type == "grid")
        grid_streetlight_kwh_yr = 0.0
        # Realism trio: per-ROAD-CLASS lighting weights
        # (IS 1944 illuminance grades - see demand_norms.yaml block). The
        # per-capita TOTAL is unchanged; weights change which cells carry it,
        # so the grid-lit share shifts toward the (mostly dense-core, grid-lit)
        # arterials. enabled:false reproduces the equal-share arithmetic
        # byte-exactly via the original expression below.
        _sl_cw = norms.public_services.get("street_lighting_class_weights") or {}
        if sl_kwh_cap_yr > 0 and population > 0 and road_cells:
            if bool(_sl_cw.get("enabled", False)):
                _w = _sl_cw.get("weights") or {}

                def _lamp_wt(c) -> float:
                    return float(_w.get(getattr(c, "road_class", None) or "local",
                                        1.0))

                _tot_w = sum(_lamp_wt(c) for c in road_cells)
                _grid_w = sum(_lamp_wt(c) for c in road_cells
                              if c.streetlight_type == "grid")
                if _tot_w > 0:
                    grid_streetlight_kwh_yr = (
                        sl_kwh_cap_yr * population * (_grid_w / _tot_w)
                    )
            else:
                grid_streetlight_kwh_yr = (
                    sl_kwh_cap_yr * population * (grid_lit_roads / len(road_cells))
                )

        # Precompute the geometric shading multiplier table once per network
        # build. Replaces the heuristic ``_pv_shading_multiplier`` step
        # function with a physics-based annual-average from sun-path +
        # building footprints. Falls back to the heuristic on per-cell
        # lookups for cells absent from the dict (tiny test grids, no
        # casters, geometric pass disabled).
        site = getattr(cfg, "site", {}) or {}
        lat_deg = float(site.get("latitude", 30.64))
        lon_deg = float(site.get("longitude", 76.82))
        try:
            #: keyed disk cache in front of the ~320 s
            # rasteriser. The key covers grid geometry, sun samples, site
            # coords, raster fidelity AND the sha256 of solar_geometry.py, so
            # any change to inputs or algorithm invalidates it. Every failure
            # path falls through to a live recompute - see shading_cache.py.
            from .shading_cache import compute_cached
            geometric_shading = compute_cached(
                grid, econ, lat_deg, lon_deg,
            )
        except Exception as exc:
            # this used to be a bare `geometric_shading = {}`,
            # which turned ANY failure here into a silently UNSHADED network.
            # PV yield is the headline result, so an unshaded build overstates
            # it with no warning of any kind - and the failure was easy to
            # hit: the only environment with pytest has a broken numpy, so
            # the import alone raised and every network built there had zero
            # PV shading while the suite reported green.
            # A legitimately EMPTY table stays fine (tiny test grids, no
            # casters, geometric pass disabled) - the per-cell lookup falls
            # back to the heuristic, as the note above describes. What must
            # never be silent is an ERROR. Byte-neutral on the success path.
            if os.environ.get("DISTRICT_V3_ALLOW_UNSHADED") == "1":
                warnings.warn(
                    "compute_geometric_shading FAILED (%s: %s). Building an "
                    "UNSHADED network because DISTRICT_V3_ALLOW_UNSHADED=1. "
                    "PV yield from this network is OVERSTATED - do not quote "
                    "any PV, cost or emissions figure derived from it."
                    % (type(exc).__name__, exc),
                    RuntimeWarning, stacklevel=2,
                )
                geometric_shading = {}
            else:
                raise RuntimeError(
                    "compute_geometric_shading failed (%s: %s). Refusing to "
                    "build an unshaded network, because that would overstate "
                    "PV yield silently. Fix the cause (a missing or broken "
                    "numpy is the usual one), or set "
                    "DISTRICT_V3_ALLOW_UNSHADED=1 to accept an explicitly "
                    "unshaded build for non-PV work."
                    % (type(exc).__name__, exc)
                ) from exc

        nodes: List[EnergyNode] = []
        for cell in grid.all_cells():
            cat = category_for(cell.land_use)
            building = building_from_cell(cell, cfg)
            peak_base = peak_cooling = peak_heating = 0.0
            rooftop_kwp = 0.0
            households = 0
            cat_name: Optional[str] = None
            if cat is not None and building is not None:
                cat_name = cat.name
                peak_base = building.base_load_kw
                # Caveat-8 (water-energy nexus): top up each PUBLIC_SERVICES
                # cell's base load with its share of district water-treatment
                # + groundwater-pumping baseload.
                if cell.land_use == LandUse.PUBLIC_SERVICES:
                    peak_base += water_per_cell_kw
                # Cooling: use tech-mix-weighted W/m² peak instead of legacy single value.
                cooling_w_per_m2 = _weighted_cooling_w_per_m2(econ, cat.name, cat)
                peak_cooling = cooling_w_per_m2 * building.total_floor_area_m2 / 1000.0
                # (Priority 2 v2): cardinal facade-facing effect
                # on cooling load. Facing E/W (long axis N-S) gets the
                # hotter E/W-facade penalty; facing N/S (long axis E-W)
                # gets the shading/cross-ventilation bonus.
                peak_cooling *= _facade_orientation_cooling_multiplier(cell)
                # Heating: read econ table; per-floor-area scalar.
                heating_w_per_m2 = float(
                    econ.heating_loads.get("per_category_peak_w_per_m2", {})
                    .get(cat.name, 0.0)
                )
                peak_heating = heating_w_per_m2 * building.total_floor_area_m2 / 1000.0
                rooftop_kwp = building.deployable_pv_kwp
                households = building.households

            solar_farm_kwp = 0.0
            if cell.land_use == LandUse.SOLAR_FARM:
                solar_farm_kwp = cell.cell_size_m ** 2 * gm_kwp_per_m2

            # Microclimate adjustment (Stage A → Stage B coupling).
            mc_mult = _microclimate_cooling_multiplier(grid, cell, econ)
            # PV-yield shading (Stage A geometry -> Stage B/C yield coupling).
            # geometric shadow integration replaces the
            # neighbour-counting heuristic when site lat/lon are available.
            # Falls back to the heuristic on tiny test grids (e.g. when
            # geometric_shading dict is empty for a cell because it has no
            # candidate casters or the grid lacks a usable building).
            pv_shade = geometric_shading.get(
                (cell.row, cell.col),
                _pv_shading_multiplier(grid, cell),
            )

            nodes.append(EnergyNode(
                cell_id=(cell.row, cell.col),
                centre_x_m=cell.centre_x_m,
                centre_y_m=cell.centre_y_m,
                land_use=cell.land_use,
                category_name=cat_name,
                peak_base_kw=peak_base,
                peak_cooling_kw=peak_cooling,
                peak_heating_kw=peak_heating,
                microclimate_cooling_multiplier=mc_mult,
                rooftop_pv_cap_kwp=rooftop_kwp,
                solar_farm_cap_kwp=solar_farm_kwp,
                households=households,
                is_residential=cell.land_use.is_residential,
                pv_shading_multiplier=pv_shade,
                faith=cell.faith,
            ))

        edges = cls._road_edges(grid)
        return cls(nodes=nodes, edges=edges, grid=grid, layout_name=layout_name,
                   grid_streetlight_kwh_yr=grid_streetlight_kwh_yr,
                   rooftop_module_efficiency=float(
                       getattr(cfg, "rooftop_module_efficiency", 0.1930)))

    @staticmethod
    def _road_edges(grid: Grid) -> List[EnergyEdge]:
        seen: set = set()
        out: List[EnergyEdge] = []
        for r in range(grid.n_rows):
            for c in range(grid.n_cols):
                cell = grid.at(r, c)
                if cell.land_use != LandUse.ROAD:
                    continue
                for dr, dc in ((1, 0), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols):
                        continue
                    other = grid.at(nr, nc)
                    if other.land_use != LandUse.ROAD:
                        continue
                    key = ((r, c), (nr, nc))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(EnergyEdge(
                        a=(r, c),
                        b=(nr, nc),
                        length_m=Grid.euclidean_distance(cell, other),
                    ))
        return out

    # ---- aggregate accessors -----------------------------------------
    def total_peak_demand_kw(self) -> float:
        return sum(n.peak_demand_kw for n in self.nodes)

    def total_rooftop_pv_cap_kwp(self) -> float:
        return sum(n.rooftop_pv_cap_kwp for n in self.nodes)

    def total_solar_farm_cap_kwp(self) -> float:
        return sum(n.solar_farm_cap_kwp for n in self.nodes)

    def total_households(self) -> int:
        return sum(n.households for n in self.nodes if n.is_residential)

    def v2g_units(self, econ, year: Optional[int] = None) -> float:
        """Income-aware V2G unit count: EV-CAR-owning households
        willing to do V2G. Replaces the legacy flat households/5. Only
        residential nodes contribute, weighted by per-income EV-car ownership x
        V2G willingness (cars only; low income owns ~no cars). Driven by
        economics.yaml `ev_vehicle_ownership`. Falls back to households/5 if the
        ownership table is absent (legacy).

        ``year``: when given, the EV-car ownership uses the
        per-period ``ev_car_share_by_period`` ramp so the V2G fleet grows
        across multi-period horizons (2030/2042/2055). ``year=None`` is the
        2030 baseline (single-period path stays byte-exact)."""
        if not getattr(econ, "ev_vehicle_ownership", None):
            return self.total_households() / 5.0
        total = 0.0
        for n in self.nodes:
            inc = econ.income_for_category(n.category_name or "")
            if inc is None:
                continue
            # ev_cars_per_household includes multi-car ownership
            # (affluent households with 2+ cars contribute 2+ V2G units).
            total += (n.households * econ.ev_cars_per_household(inc, year)
                      * econ.v2g_willingness(inc))
        return total

    def ev_node_kw(self, econ: Economics, n: "EnergyNode", s,
                    ev_scenario: Optional[str] = None,
                    year: Optional[int] = None) -> float:
        """EV-charging power (kW) this node draws in this slice.

: the two categories take different routes because
        they are physically different things.
          - RESIDENTIAL: households x per-household kW, built from the declared
            car / e-2W stock. A fraction-of-peak was the wrong dimension - it
            multiplied a per-household ownership figure by a per-CELL peak, and
            since cells carry a similar peak whatever their household count, a
            high-income household ended up drawing 15.7x a low-income one.
          - OFFICE: peak_base_kw x fleet-fraction, which IS the right dimension
            (a workplace charger bank scales with the building).

        Every EV term in this module goes through here, so the two routes
        cannot drift apart."""
        if n.category_name is None:
            return 0.0
        if econ.income_for_category(n.category_name) is not None:
            return n.households * econ.ev_kw_per_household(
                n.category_name, s.id, year)
        return n.peak_base_kw * econ.ev_demand_multiplier(
            n.category_name, s.id, ev_scenario, year)

    def ev_charging_kwh_by_slice(self, econ: Economics, year: Optional[int] = None,
                                  ev_scenario: Optional[str] = None) -> Dict[str, float]:
        """District EV-charging energy (kWh) per slice, isolated from the rest
        of demand. Mirrors the EV term added in ``demand_by_slice_kw``
        (both call ``ev_node_kw``) so the multi-period LP can ramp ONLY the EV
        portion of demand with ``year`` while the non-EV part scales by
        ``period_demand_multiplier``. ``year=None`` returns the 2030 EV load
        already embedded in ``demand_by_slice_kwh``."""
        out: Dict[str, float] = {s.id: 0.0 for s in econ.slices}
        for n in self.nodes:
            if n.category_name is None:   # mirror demand_by_slice_kw's filter
                continue
            for s in econ.slices:
                ev_kw = self.ev_node_kw(econ, n, s, ev_scenario, year)
                if ev_kw:
                    out[s.id] += ev_kw * s.hours_per_year
        return out

    def ev_charging_kwh_by_slice_by_class(
            self, econ: Economics, year: Optional[int] = None,
            ev_scenario: Optional[str] = None
    ) -> Dict[str, Dict[str, float]]:
        """REV-2: the EV-charging energy of
        ``ev_charging_kwh_by_slice`` split by CHARGING CLASS -
        ``residential`` (income-mapped categories, overnight plug-in
        window) vs ``workplace`` (office category, workday window). Used
        ONLY for the smart-charging shift-variable bounds in the Pyomo
        builders; the balance keeps consuming the unsplit total, so this
        method cannot perturb the demand path. A slice's class energy is
        zero outside that class's daypart-shape support - which is exactly
        the plug-in window the shift variables are confined to."""
        classes: Dict[str, Dict[str, float]] = {
            "residential": {s.id: 0.0 for s in econ.slices},
            "workplace": {s.id: 0.0 for s in econ.slices},
        }
        for n in self.nodes:
            if n.category_name is None:   # mirror demand_by_slice_kw's filter
                continue
            if econ.income_for_category(n.category_name) is not None:
                cls = "residential"
            elif n.category_name == "office":
                cls = "workplace"
            else:
                continue   # ev_node_kw is 0 for everything else
            bucket = classes[cls]
            for s in econ.slices:
                ev_kw = self.ev_node_kw(econ, n, s, ev_scenario, year)
                if ev_kw:
                    bucket[s.id] += ev_kw * s.hours_per_year
        return classes

    def built_nodes(self) -> List[EnergyNode]:
        return [n for n in self.nodes if n.is_built]

    def solar_farm_nodes(self) -> List[EnergyNode]:
        return [n for n in self.nodes if n.is_solar_farm]

    def residential_nodes(self) -> List[EnergyNode]:
        return [n for n in self.nodes if n.is_residential]

    def road_node_count(self) -> int:
        return sum(1 for n in self.nodes if n.land_use == LandUse.ROAD)

    # ---- per-slice profile builders ----------------------------------
    def demand_by_slice_kw(self, econ: Economics,
                            ev_scenario: Optional[str] = None) -> Dict[str, float]:
        """Per-slice district aggregate demand (kW).

        For each built node compose:
            base_kw  * base_occupancy_mult(slice)
          + cooling_kw * cooling_factor(slice) * microclimate_mult * cooling_eff
          + heating_kw * heating_factor(slice)
          + ev_kw_proxy(slice)        — added only via base × ev_multiplier

        Returns
        -------
        Dict[str, float]
            slice_id -> aggregate demand in kW.
        """
        out: Dict[str, float] = {s.id: 0.0 for s in econ.slices}
        #: climate-derived cooling degree days
        # (CIBSE TM41 max/min form, base 24 C = the MoP mandatory AC
        # default) replace twelve hand-typed numbers that scaled a
        # third of district demand with no source of any kind.
        cooling_by_month = {m: econ.cooling_factor_for_month(m)
                            for m in (econ.climate or
                                      econ.cooling_factors.get(
                                          "cooling_factor_by_month", {}))}
        # (Realism audit A1) put the monsoon-specific daypart shape
        # here; moved it, its month list and the dry-month
        # shape INTO Economics.cooling_daypart_factor, which now owns the
        # whole residential-vs-commercial split. The three locals left behind
        # were dead assignments; removed.
        # (Realism audit B3): heating month factor now comes
        # via econ.heating_factor_for_month -- HDD-derived from climate
        # if loaded, legacy table otherwise.

        # FX-8 / AUD-23: a missing base profile or daypart key used
        # to fall back SILENTLY to a flat 0.5 (the bug family). Validate once
        # up front and fail loudly - a YAML typo must not quietly flatten a
        # category's demand shape. (Zero categories trip this at the current
        # config; verified in the audit.)
        _dayparts_in_use = {s.daypart for s in econ.slices}
        for _cat in sorted({n.category_name for n in self.nodes if n.category_name}):
            _prof = econ.base_demand_profile.get(_cat)
            if _prof is None:
                raise ValueError(
                    f"base_demand_profile missing for category '{_cat}' "
                    "(economics.yaml) - refusing the silent flat-0.5 fallback (FX-8)"
                )
            for _dt in ("weekday", "weekend", "festival"):
                _missing = _dayparts_in_use - set((_prof.get(_dt) or {}).keys())
                if _missing:
                    raise ValueError(
                        f"base_demand_profile['{_cat}']['{_dt}'] missing dayparts "
                        f"{sorted(_missing)[:4]} - refusing the silent 0.5 fallback (FX-8)"
                    )

        # the SAME FX-8 discipline extended to the three
        # demand-shaping tables the/07 audit added. Each carried a
        # silent `.get(key, 0.0)` that would mis-shape a major load instead of
        # failing, which is the family all over again:
        #  residential cooling hours -> silently fell THROUGH to the
        #          non-residential afternoon curve (cooling is ~33% of demand)
        #  cooling month factor      -> silently 0.0, deleting a month
        #   HEAT-1 dhw share                 -> silently 100% space heating
        # Validate once here; the per-slice `.get` defaults below then cannot
        # mask a gap. Zero categories trip any of these at the current config.
        _months_in_use = {s.month for s in econ.slices}
        _cf = econ.cooling_factors or {}
        _rc = _cf.get("residential_cooling") or {}
        _hl = econ.heating_loads or {}
        _cats = sorted({n.category_name for n in self.nodes if n.category_name})

        if _rc:
            _hours_tbl = _rc.get("equivalent_full_load_hours") or {}
            for _cat in _cats:
                if econ.income_for_category(_cat) is None:
                    continue          # non-residential keeps the legacy curve
                if float(_hours_tbl.get(_cat, 0.0)) <= 0:
                    raise ValueError(
                        "residential_cooling.equivalent_full_load_hours "
                        f"missing '{_cat}' - refusing the silent fall-through "
                        "to the NON-residential afternoon cooling curve (PA-A7)"
                    )

        _month_src = (set(econ.climate or {})
                      | set(_cf.get("cooling_factor_by_month") or {}))
        _missing_m = _months_in_use - _month_src
        if _missing_m:
            raise ValueError(
                f"no cooling month factor resolvable for {sorted(_missing_m)} "
                "(climate.yaml or cooling_factor_by_month) - refusing the "
                "silent 0.0 that would delete that month's cooling (PA-C2)"
            )

        _dhw_share = _hl.get("dhw_share_of_peak_by_category") or {}
        if _dhw_share and _hl.get("dhw") and econ.climate:
            for _n in self.nodes:
                if (_n.category_name and _n.peak_heating_kw > 0
                        and _n.category_name not in _dhw_share):
                    raise ValueError(
                        "dhw_share_of_peak_by_category missing "
                        f"'{_n.category_name}', which has peak_heating_kw>0 - "
                        "refusing the silent 0.0 that would route ALL of its "
                        "heat through the space-heating season (HEAT-1)"
                    )

        for n in self.nodes:
            if n.category_name is None:
                continue
            base_prof = econ.base_demand_profile.get(n.category_name)
            for s in econ.slices:
                # Base / occupancy term — day-type weighted (coverage validated
                # above, so the.get defaults below can no longer mask a gap)
                if base_prof is not None:
                    wd = float(base_prof.get("weekday", {}).get(s.daypart, 0.5))
                    we = float(base_prof.get("weekend", {}).get(s.daypart, 0.5))
                    ft = float(base_prof.get("festival", {}).get(s.daypart, 0.5))
                    base_mult = (s.weekday_share * wd
                                 + s.weekend_share * we
                                 + s.festival_share * ft)
                else:
                    base_mult = 0.5
                # (864-slice refactor Phase 5, Claude 2):
                # apply hourly behavioural patches (lighting evening-peak,
                # WFH day-of-week split, festival Diwali evening). Returns
                # 1.0 in 144-slice mode by construction (day_type="mixed").
                base_mult *= econ.behavioural_demand_multiplier(
                    n.category_name, s, faith=n.faith,
                )
                base_kw = n.peak_base_kw * base_mult

                # Cooling term. Monsoon months get a different daypart
                # shape (cloud-dampened midday, humid-evening peak); fall
                # back to dry-month shape if monsoon table absent.
                #: residential cooling is night-weighted
                # and runs bottom-up hours; non-residential keeps the
                # afternoon-peaked shape and its monsoon variant. See
                # Economics.cooling_daypart_factor.
                dp_shape = econ.cooling_daypart_factor(
                    n.category_name, s.daypart, s.month)
                cf = float(cooling_by_month.get(s.month, 0.0)) * dp_shape
                cool_eff = econ._cooling_effectiveness(n.category_name, s.month)
                #: heat-wave
                # uplift when monthly t_max exceeds 40 C. Defaults to
                # 1.0 when climate data is unavailable.
                hw_mult = econ.heat_wave_cooling_multiplier(s.month)
                cool_kw = (n.peak_cooling_kw * cf
                           * n.microclimate_cooling_multiplier
                           * cool_eff
                           * hw_mult)

                # FX-4: per-(category, month) occupancy scaler -
                # school summer vacation closes the building, so plug loads
                # AND cooling collapse together. Returns 1.0 for categories/
                # months absent from the YAML table (byte-stable elsewhere).
                #: indoor lighting is seasonal. The 18-20
                # daypart is fully dark in December and half dark in July, so
                # its lighting share must move with daylength - the same
                # treatment street lighting already gets. Annual-neutral;
                # BASE term only.
                base_kw *= econ.lighting_seasonal_multiplier(
                    n.category_name, s.month, s.daypart)

                occ_m = econ.occupancy_monthly_modifier(n.category_name, s.month)
                if occ_m != 1.0:
                    base_kw *= occ_m
                    cool_kw *= occ_m

                # Heating term -- B3: HDD-derived month factor.
                # HEAT-1: water heating and space heating
                # are two loads with different seasons, different daily
                # curves and different running hours. See
                # Economics.heating_split_factor.
                heat_kw = n.peak_heating_kw * econ.heating_split_factor(
                    n.category_name, s.id)

                # EV charging uplift (residential per household, office per
                # peak - see ev_node_kw for why the two differ)
                ev_kw = self.ev_node_kw(econ, n, s, ev_scenario)

                out[s.id] += base_kw + cool_kw + heat_kw + ev_kw

        # (Task 5): grid street-lighting night load (off-grid solar
        # streetlights add nothing). Distributed across slices by a night-heavy
        # daypart shape; per-slice kW x hours_per_year sums back to the network's
        # grid_streetlight_kwh_yr. Road cells have no category so this can't be a
        # per-node base load; it enters here as a district term.
        sl_kwh = getattr(self, "grid_streetlight_kwh_yr", 0.0)
        if sl_kwh > 0:
            shape = econ.street_lighting_daypart_shape()
            if shape:
                # (Part 4): the daypart_shape gives the daily SHAPE
                # (dusk→dawn); a per-MONTH modifier scales each slice by how long
                # the streetlights actually burn that month (winter nights longer
                # than summer — Zirakpur daylength). To keep the ANNUAL total
                # EXACTLY sl_kwh regardless of the modifier's mean, we build a
                # per-slice ENERGY weight = daypart_frac × month_modifier × hours,
                # then normalise the weights to sum to sl_kwh before converting to
                # kW. (When no monthly_modifier is configured, modifier=1.0 →
                # byte-identical to the old daypart-only distribution.)
                hours_by_daypart: Dict[str, float] = {}
                for s in econ.slices:
                    hours_by_daypart[s.daypart] = (
                        hours_by_daypart.get(s.daypart, 0.0) + s.hours_per_year
                    )
                slice_weight: Dict[str, float] = {}
                total_weight = 0.0
                for s in econ.slices:
                    frac = float(shape.get(s.daypart, 0.0))
                    h = hours_by_daypart.get(s.daypart, 0.0)
                    if frac > 0 and h > 0:
                        mod = econ.street_lighting_monthly_modifier(s.month)
                        # energy share for this slice ∝ daypart-frac (per its
                        # hours) × month modifier × this slice's hours
                        w = (frac * s.hours_per_year / h) * mod
                        slice_weight[s.id] = w
                        total_weight += w
                if total_weight > 0:
                    for s in econ.slices:
                        w = slice_weight.get(s.id, 0.0)
                        if w > 0:
                            # energy to this slice = sl_kwh × (w / Σw); kW = /hours
                            slice_kwh = sl_kwh * (w / total_weight)
                            out[s.id] += slice_kwh / s.hours_per_year

        return out

    def demand_by_slice_kwh(self, econ: Economics,
                              ev_scenario: Optional[str] = None) -> Dict[str, float]:
        # REV-1: cache entries pin the econ OBJECT alongside the
        # value and verify identity on read. id alone can be recycled by
        # CPython after garbage collection, silently serving a previous
        # econ's demand to a new instance at the same address; holding the
        # strong reference makes recycling impossible while the entry lives.
        key = (id(econ), ev_scenario)
        cached = self._demand_kwh_cache.get(key) if ev_scenario is None else None
        if cached is not None and cached[0] is econ:
            return cached[1]
        kw = self.demand_by_slice_kw(econ, ev_scenario=ev_scenario)
        out = {sid: kw[sid] * econ.slice_by_id(sid).hours_per_year for sid in kw}
        if ev_scenario is None:
            self._demand_kwh_cache[key] = (econ, out)
        return out

    def annual_demand_kwh(self, econ: Economics,
                           ev_scenario: Optional[str] = None) -> float:
        return sum(self.demand_by_slice_kwh(econ, ev_scenario=ev_scenario).values())

    def cooling_kwh_by_slice(self, econ: Economics) -> Dict[str, float]:
        """District COOLING energy (kWh) per slice, isolated from the rest of
        demand.

: the climate-warming demand driver used to be a
        flat multiplier on everything, so +2 C of global warming raised
        JANUARY demand by 3%. Warming does not do that - it raises cooling and
        lowers heating. To apply the uplift to the right term, the LP needs
        the cooling term on its own.

        Isolated BY DIFFERENCE - total demand minus the same demand with every
        cooling peak zeroed - rather than by re-implementing the cooling
        formula. A parallel copy of that formula would silently drift from
        ``demand_by_slice_kw`` the first time either changed (monsoon shapes,
        cooling-tech effectiveness, heat-wave uplift, microclimate,
        school-holiday occupancy all feed it). Subtraction cannot drift."""
        full = self.demand_by_slice_kwh(econ)
        sub = copy.copy(self)
        sub.nodes = [copy.copy(n) for n in self.nodes]
        for n in sub.nodes:
            n.peak_cooling_kw = 0.0
        # copy.copy shares the cache dict with self, which would hand back the
        # parent's WITH-cooling answer. Give the clone its own.
        sub._demand_kwh_cache = {}
        no_cool = sub.demand_by_slice_kwh(econ)
        return {sid: full[sid] - no_cool.get(sid, 0.0) for sid in full}

    def demand_components_by_slice_kw(self, econ: Economics,
                                       ev_scenario: Optional[str] = None
                                       ) -> Dict[str, Dict[str, float]]:
        """RES-1: per-COMPONENT slice demand (kW).

        Returns ``{category_name: {slice_id: kw}}`` for every built node
        category, plus ``street_lighting`` for the grid-streetlight
        district term. Used by the resilience pack to compute the CRITICAL
        load (healthcare + public_services + street_lighting; water
        treatment is INSIDE public_services - baked into node base load at
        build, see the water_per_cell_kw comment in from_layout).

        DELIBERATELY replicates demand_by_slice_kw's arithmetic instead of
        refactoring it: the production accumulator's float ADDITION ORDER
        is pin-sensitive (byte-exact suite), so it must not change. The
        RES-1 runner asserts sum(components) == demand_by_slice_kw to 1e-6
        relative on every use - the drift guard that keeps the two loops
        honest.
        """
        comps: Dict[str, Dict[str, float]] = {}
        #: climate-derived cooling degree days
        # (CIBSE TM41 max/min form, base 24 C = the MoP mandatory AC
        # default) replace twelve hand-typed numbers that scaled a
        # third of district demand with no source of any kind.
        cooling_by_month = {m: econ.cooling_factor_for_month(m)
                            for m in (econ.climate or
                                      econ.cooling_factors.get(
                                          "cooling_factor_by_month", {}))}
        # moved the cooling daypart shape + its monsoon
        # variant + the monsoon month list INTO
        # Economics.cooling_daypart_factor. The three locals that used to be
        # read here were left behind as dead assignments; removed
        # so this file no longer reads as though it still applies the monsoon
        # shape itself (a later monsoon fix would have landed in the wrong
        # place and appeared to work).

        for n in self.nodes:
            if n.category_name is None:
                continue
            cat = comps.setdefault(n.category_name,
                                   {s.id: 0.0 for s in econ.slices})
            base_prof = econ.base_demand_profile.get(n.category_name)
            for s in econ.slices:
                if base_prof is not None:
                    wd = float(base_prof.get("weekday", {}).get(s.daypart, 0.5))
                    we = float(base_prof.get("weekend", {}).get(s.daypart, 0.5))
                    ft = float(base_prof.get("festival", {}).get(s.daypart, 0.5))
                    base_mult = (s.weekday_share * wd
                                 + s.weekend_share * we
                                 + s.festival_share * ft)
                else:
                    base_mult = 0.5
                base_mult *= econ.behavioural_demand_multiplier(
                    n.category_name, s, faith=n.faith,
                )
                base_kw = n.peak_base_kw * base_mult

                #: residential cooling is night-weighted
                # and runs bottom-up hours; non-residential keeps the
                # afternoon-peaked shape and its monsoon variant. See
                # Economics.cooling_daypart_factor.
                dp_shape = econ.cooling_daypart_factor(
                    n.category_name, s.daypart, s.month)
                cf = float(cooling_by_month.get(s.month, 0.0)) * dp_shape
                cool_eff = econ._cooling_effectiveness(n.category_name, s.month)
                hw_mult = econ.heat_wave_cooling_multiplier(s.month)
                cool_kw = (n.peak_cooling_kw * cf
                           * n.microclimate_cooling_multiplier
                           * cool_eff
                           * hw_mult)

                #: indoor lighting is seasonal. The 18-20
                # daypart is fully dark in December and half dark in July, so
                # its lighting share must move with daylength - the same
                # treatment street lighting already gets. Annual-neutral;
                # BASE term only.
                base_kw *= econ.lighting_seasonal_multiplier(
                    n.category_name, s.month, s.daypart)

                occ_m = econ.occupancy_monthly_modifier(n.category_name, s.month)
                if occ_m != 1.0:
                    base_kw *= occ_m
                    cool_kw *= occ_m

                # HEAT-1: water heating and space heating
                # are two loads with different seasons, different daily
                # curves and different running hours. See
                # Economics.heating_split_factor.
                heat_kw = n.peak_heating_kw * econ.heating_split_factor(
                    n.category_name, s.id)

                ev_kw = self.ev_node_kw(econ, n, s, ev_scenario)

                cat[s.id] += base_kw + cool_kw + heat_kw + ev_kw

        # Grid street-lighting district term (mirrors demand_by_slice_kw's
        # energy-weight normalisation exactly).
        sl_kwh = getattr(self, "grid_streetlight_kwh_yr", 0.0)
        if sl_kwh > 0:
            shape = econ.street_lighting_daypart_shape()
            if shape:
                sl = comps.setdefault("street_lighting",
                                      {s.id: 0.0 for s in econ.slices})
                hours_by_daypart: Dict[str, float] = {}
                for s in econ.slices:
                    hours_by_daypart[s.daypart] = (
                        hours_by_daypart.get(s.daypart, 0.0) + s.hours_per_year
                    )
                slice_weight: Dict[str, float] = {}
                total_weight = 0.0
                for s in econ.slices:
                    frac = float(shape.get(s.daypart, 0.0))
                    h = hours_by_daypart.get(s.daypart, 0.0)
                    if frac > 0 and h > 0:
                        mod = econ.street_lighting_monthly_modifier(s.month)
                        w = (frac * s.hours_per_year / h) * mod
                        slice_weight[s.id] = w
                        total_weight += w
                if total_weight > 0:
                    for s in econ.slices:
                        w = slice_weight.get(s.id, 0.0)
                        if w > 0:
                            slice_kwh = sl_kwh * (w / total_weight)
                            sl[s.id] += slice_kwh / s.hours_per_year
        return comps

    def water_heating_kwh_by_slice(self, econ: Economics) -> Dict[str, float]:
        """District WATER-heating energy per slice (kWh/yr), DHW leg only.

        This is the load solar thermal can displace - and only this one. A
        collector cannot heat a room, so the space-heating leg has to be left
        behind. `Economics.dhw_only_split_factor` isolates it.

        *** WRITTEN AS A SEPARATE LOOP, DELIBERATELY, NOT AS A REFACTOR OF
        `demand_by_slice_kw`. *** That accumulator's float ADDITION ORDER is
        pin-sensitive under the byte-exact suite - the sibling
        `demand_components_by_slice_kw` carries the same warning in its own
        docstring and replicates rather than refactors for exactly this
        reason. Touching the production loop to extract a component that can
        be recomputed beside it would move pinned totals for no gain.

        DRIFT GUARD. The DHW and space legs recomposed here must reproduce
        `heating_split_factor` on every (category, slice) pair, so the split
        cannot silently diverge from what the demand accumulator applied. The
        guard runs on the factor table (categories x slices), not per node,
        which keeps it cheap.

        Returns an empty dict when solar thermal is off, so no caller pays
        for a series nothing will read.
        """
        if not econ.solar_thermal_enabled():
            return {}
        hl = econ.heating_loads or {}
        shares = (hl.get("dhw_share_of_peak_by_category") or {})
        if not shares or "dhw" not in hl or not econ.climate:
            return {}

        cats = sorted({n.category_name for n in self.nodes if n.category_name})
        fac: Dict[tuple, float] = {}
        worst = 0.0
        for cat in cats:
            f = float(shares.get(cat, 0.0))
            for s in econ.slices:
                d = econ.dhw_only_split_factor(cat, s.id)
                sp = ((1.0 - f) * econ.space_heating_month_factor(s.month)
                      * econ._heat_daypart("space_heating", cat, s.daypart))
                worst = max(worst, abs((d + sp)
                                       - econ.heating_split_factor(cat, s.id)))
                fac[(cat, s.id)] = d
        if worst > 1e-9:
            raise ValueError(
                "water_heating_kwh_by_slice drift guard failed: the DHW and "
                "space legs do not recompose to heating_split_factor "
                f"(worst {worst:.3e}). The split changed under this function."
            )

        peak: Dict[str, float] = {}
        for n in self.nodes:
            if n.category_name and n.peak_heating_kw > 0:
                peak[n.category_name] = (peak.get(n.category_name, 0.0)
                                         + n.peak_heating_kw)
        out = {s.id: 0.0 for s in econ.slices}
        for cat, pk in peak.items():
            for s in econ.slices:
                out[s.id] += pk * fac[(cat, s.id)] * s.hours_per_year
        return out

    def solar_thermal_roof_cap_m2(self, econ: Economics) -> float:
        """Roof area (m2) a collector could compete for, district total.

        `rooftop_pv_cap_kwp` is already net of `pv_acceptance`, so dividing
        by the module efficiency recovers the roof the model treats as
        DEPLOYABLE - the right denominator, because solar thermal competes
        for that same accepted area rather than for raw slab.

        Restricted to categories that actually draw hot water: putting a
        collector on a warehouse roof would be free area the LP could use to
        dodge the competition constraint.
        """
        if not econ.solar_thermal_enabled():
            return 0.0
        eff = float(self.rooftop_module_efficiency)
        if eff <= 0:
            return 0.0
        total = 0.0
        for n in self.nodes:
            if (n.rooftop_pv_cap_kwp > 0 and n.category_name
                    and econ.solar_thermal_eligible(n.category_name)):
                total += n.rooftop_pv_cap_kwp / eff
        return total

    def pv_yield_per_kwp_kwh(self, econ: Economics) -> Dict[str, float]:
        """Rooftop PV yield per kWp installed (kWh) for each slice.

        Applies the capacity-weighted rooftop shading-yield multiplier so
        cells with tall S/SW/SE/E/W neighbours produce less per-kWp than
        their unshaded peers. The aggregate per-kWp yield = base yield
        * rooftop_pv_shading_yield_multiplier.
        """
        # REV-1: identity-pinned cache (see demand_by_slice_kwh).
        key = id(econ)
        cached = self._yield_rooftop_cache.get(key)
        if cached is not None and cached[0] is econ:
            return cached[1]
        shading_mult = self.rooftop_pv_shading_yield_multiplier()
        # (A12): DC-side electrical losses (inverter + string).
        dc_eff = max(0.0, 1.0 - econ.dc_loss_fraction())
        out: Dict[str, float] = {}
        for s in econ.slices:
            # (Realism audit A2): per-slice temperature derating.
            t_derate = econ.pv_temperature_derating(s.id)
            # (A19): per-month PM2.5 soiling + fog losses.
            # renormalised so the annual energy-weighted mean is
            # 1.0 - GSA PVOUT_specific already contains 3.5% soiling, so the
            # raw A19 multiplier double-charged the level. Seasonal shape is
            # preserved. See Economics.pv_soiling_yield_multiplier_for_month.
            soil_mult = econ.pv_soiling_yield_multiplier_for_month(s.month)
            fog_mult = econ.pv_fog_multiplier_for_month(s.month)
            out[s.id] = (econ.pv_capacity_factor(s.id) * s.hours_per_year
                          * shading_mult * t_derate * dc_eff
                          * soil_mult * fog_mult)
        self._yield_rooftop_cache[key] = (econ, out)
        return out

    def pv_yield_per_kwp_kwh_solar_farm(self, econ: Economics) -> Dict[str, float]:
        """Ground-mount PV yield per kWp installed (kWh) for each slice.

        Applies the capacity-weighted SOLAR_FARM shading-yield multiplier so
        ground arrays shadowed by tall neighbours produce less per-kWp.
        """
        # REV-1: identity-pinned cache (see demand_by_slice_kwh).
        key = id(econ)
        cached = self._yield_farm_cache.get(key)
        if cached is not None and cached[0] is econ:
            return cached[1]
        shading_mult = self.solar_farm_pv_shading_yield_multiplier()
        # (A12): DC-side electrical losses (inverter + string).
        dc_eff = max(0.0, 1.0 - econ.dc_loss_fraction())
        #: inter-row self-shading of the fixed-tilt rows,
        # derived rather than assumed (scripts/gcr_interrow_sweep.py; see
        # Economics.solar_farm_inter_row_derate). 1.0 while the config key
        # is unset. Carport canopies borrow this yield table; a single-row
        # borrow is a +0.021% understatement on an 19 GWh/yr technology -
        # documented as noise rather than split into a second table.
        inter_row = max(0.0, 1.0 - econ.solar_farm_inter_row_derate())
        out: Dict[str, float] = {}
        for s in econ.slices:
            # (Realism audit A2): per-slice temperature derating.
            t_derate = econ.pv_temperature_derating(s.id)
            # (A19): per-month PM2.5 soiling + fog losses.
            # renormalised so the annual energy-weighted mean is
            # 1.0 - GSA PVOUT_specific already contains 3.5% soiling, so the
            # raw A19 multiplier double-charged the level. Seasonal shape is
            # preserved. See Economics.pv_soiling_yield_multiplier_for_month.
            soil_mult = econ.pv_soiling_yield_multiplier_for_month(s.month)
            fog_mult = econ.pv_fog_multiplier_for_month(s.month)
            out[s.id] = (econ.pv_capacity_factor_solar_farm(s.id)
                          * s.hours_per_year * shading_mult * t_derate * dc_eff
                          * soil_mult * fog_mult * inter_row)
        self._yield_farm_cache[key] = (econ, out)
        return out

    # ---- Stage A -> B/C shading coupling --------------------------------
    def rooftop_pv_shading_yield_multiplier(self) -> float:
        """Capacity-weighted rooftop PV shading multiplier.

        Sums (rooftop_kwp x pv_shading_multiplier) / total rooftop_kwp
        across built nodes. Returns 1.0 when no rooftop capacity exists.
        """
        total_kwp = 0.0
        weighted = 0.0
        for n in self.nodes:
            if n.rooftop_pv_cap_kwp > 0:
                total_kwp += n.rooftop_pv_cap_kwp
                weighted += n.rooftop_pv_cap_kwp * n.pv_shading_multiplier
        if total_kwp <= 0:
            return 1.0
        return weighted / total_kwp

    def solar_farm_pv_shading_yield_multiplier(self) -> float:
        """Capacity-weighted SOLAR_FARM shading multiplier (parallel to rooftop)."""
        total_kwp = 0.0
        weighted = 0.0
        for n in self.nodes:
            if n.solar_farm_cap_kwp > 0:
                total_kwp += n.solar_farm_cap_kwp
                weighted += n.solar_farm_cap_kwp * n.pv_shading_multiplier
        if total_kwp <= 0:
            return 1.0
        return weighted / total_kwp

    # ---- Stage C round 3 (Claude 2) capacity surfaces ----------------
    def total_bipv_potential_kwp(self, econ: Economics) -> float:
        """Aggregate BIPV facade potential in the district.

        Sums ``kwp_per_meter_of_height x height_m x uptake_fraction`` over
        built nodes whose ``Cell.height_m >= applies_above_height_m``. Uses
        per-node height which is loaded from the GeoJSON (and equals
        ``cell.height_m`` in synthetic grids).
        """
        threshold = econ.bipv_applies_above_height_m()
        kwp_per_m = econ.bipv_kwp_per_meter_of_height()
        uptake = econ.bipv_uptake_fraction()
        total = 0.0
        grid = self.grid
        for n in self.built_nodes():
            cell = grid.at(*n.cell_id) if grid is not None else None
            h = getattr(cell, "height_m", 0.0) if cell is not None else 0.0
            if h >= threshold:
                # (Priority 2): scale per-cell BIPV potential by
                # the south-facing-facade exposure factor for this cell's
                # building axis. N-S axis -> 0 (no south facade); E-W -> 1
                # (full); diagonals -> 0.5 (partial south-east / south-west).
                facade_exp = (_bipv_facade_orientation_multiplier(cell)
                               if cell is not None else 0.5)
                total += kwp_per_m * h * uptake * facade_exp
        return total

    def total_carport_potential_kwp(self, econ: Economics) -> float:
        """Aggregate solar-carport potential.

        Two paths:
        - **Site-tagged** (Item 3,): when any cell on the
          underlying grid has ``is_carport_site == True``, sum the
          per-site kWp via `carport_siting.carport_kwp_for_cell`.
          This uses the discrete, anchor-proximate sites placed by
          `layout.carport_siting.place_carports` rather than the
          uniform "any eligible cell" cap.
        - **Legacy fallback**: when no sites are tagged, sums
          ``kwp_per_cell_default × uptake_fraction`` over nodes whose
          ``land_use`` is in the configured eligibility list
          (defaults: ROAD / OFFICE / SHOPPING_CENTRE / HEALTHCARE /
          PUBLIC_SERVICES / HIGH_INCOME_RES / HOTEL_GUESTHOUSE).
        """
        # Site-tagged path: read from the grid (the network does not
        # mirror is_carport_site onto EnergyNode — sites are a layout
        # attribute, not a per-bus electrical attribute).
        if self.grid is not None and any(
            c.is_carport_site for c in self.grid.all_cells()
        ):
            from layout.carport_siting import carport_kwp_for_cell
            return sum(
                carport_kwp_for_cell(c)
                for c in self.grid.all_cells()
                if c.is_carport_site
            )
        eligible = set(econ.carport_eligible_land_uses())
        kwp_per_cell = econ.carport_kwp_per_cell_default()
        uptake = econ.carport_uptake_fraction()
        n_eligible = sum(1 for n in self.nodes if n.land_use.value in eligible)
        return n_eligible * kwp_per_cell * uptake

    def total_floating_pv_potential_kwp(self, econ: Economics) -> float:
        """Aggregate floating-PV potential on BLUE_SPACE cells.

        Two paths:
        - **Site-tagged**: when any cell on the
          underlying grid has ``floating_pv_cluster_id`` populated (the
          deterministic siting helper has run), sum
          ``kwp_per_cell_default × uptake_fraction`` over cells where
          ``is_floating_pv_site == True``. Singleton BLUE_SPACE cells
          (cluster size < `min_cluster_size`) are excluded, matching the
          aesthetic + BOS-cost rationale. Eligibility is still gated by
          ``econ.floating_pv_eligible_land_uses`` for back-compat.
        - **Legacy fallback**: when no cluster tags exist, sums
          ``kwp_per_cell_default × uptake_fraction`` over every node
          whose ``land_use.value`` is in the configured eligibility
          list. Same number the model used pre-siting.
        """
        eligible = set(econ.floating_pv_eligible_land_uses())
        kwp_per_cell = econ.floating_pv_kwp_per_cell_default()
        uptake = econ.floating_pv_uptake_fraction()
        per_cell = kwp_per_cell * uptake
        # STAGE- (Q23,): CANAL corridor cells (BLUE_SPACE with
        # amenity_subtype "canal") price at the canal-top density - 210 kWp
        # per 100 m cell = 2.1 MW/km (PEDA Sidhwan/Ghaggar, Tier 1-2) -
        # instead of the pond per-cell x uptake product. The ceiling this
        # produces is the register-Q23 "canal length x density" cap; the
        # LP's floating-PV decision variable sizes the build within it.
        canal_per_cell = econ.canal_pv_kwp_per_cell()

        def _cell_kwp(c) -> float:
            if c.amenity_subtype == "canal":
                return canal_per_cell
            return per_cell
        # Site-tagged path: read from the grid (sites are a layout
        # attribute, not a per-bus electrical attribute).
        if self.grid is not None and any(
            c.floating_pv_cluster_id is not None for c in self.grid.all_cells()
        ):
            return sum(
                _cell_kwp(c)
                for c in self.grid.all_cells()
                if c.is_floating_pv_site and c.land_use.value in eligible
            )
        n_eligible = sum(1 for n in self.nodes if n.land_use.value in eligible)
        return n_eligible * per_cell

    def total_thermal_storage_potential_kwh(self, econ: Economics) -> float:
        """Aggregate thermal-cold-storage capacity ceiling in the district.

 targeting refinement: TES is only viable for buildings
        with central cooling (chiller + chilled-water distribution).
        Restricts deployment to ``econ.thermal_storage_eligible_categories``,
        sized by floor-area * ``thermal_storage_kwh_per_m2``. Residential
        and small retail return 0 even if they have non-zero cooling load.

        Returns 0 when no eligible cells exist or when the YAML omits the
        eligibility list (preserves legacy district-wide treatment).
        """
        eligible = set(econ.thermal_storage_eligible_categories())
        if not eligible:
            return 0.0
        kwh_per_m2 = econ.thermal_storage_kwh_per_m2()
        if kwh_per_m2 <= 0:
            return 0.0
        # Need floor area; recompute via building_from_cell for accuracy.
        from core.building import building_from_cell
        total = 0.0
        grid = self.grid
        if grid is None:
            return 0.0
        for c in grid.all_cells():
            b = building_from_cell(c)
            if b is None or b.category is None:
                continue
            if b.category.name in eligible:
                total += b.total_floor_area_m2 * kwh_per_m2
        return total

    def pv_yield_per_kwp_kwh_oriented(self, econ: Economics) -> Dict[str, float]:
        """Capacity-weighted average rooftop PV yield using per-cell
        orientation defaults from ``Economics.pv_orientation_default_for_category``.

        Returns a per-slice kWh-per-kWp-of-aggregate-rooftop dictionary
        comparable with :meth:`pv_yield_per_kwp_kwh`. Built nodes with
        non-zero rooftop_pv_cap_kwp are weighted by their capacity ceiling.
        Falls back to the south-only curve when no built rooftop is present.

        Stage C round 3 addition (Claude 2,). Cached per econ
        identity like the other yield builders.
        """
        # REV-1: identity-pinned cache (see demand_by_slice_kwh).
        key = id(econ)
        cached = self._yield_rooftop_oriented_cache.get(key)
        if cached is not None and cached[0] is econ:
            return cached[1]

        # Sum rooftop ceilings by orientation.
        cap_by_orientation: Dict[str, float] = {}
        for n in self.built_nodes():
            if n.rooftop_pv_cap_kwp <= 0:
                continue
            o = econ.pv_orientation_default_for_category(n.category_name)
            cap_by_orientation[o] = cap_by_orientation.get(o, 0.0) + n.rooftop_pv_cap_kwp
        total_cap = sum(cap_by_orientation.values())
        if total_cap <= 0:
            out = self.pv_yield_per_kwp_kwh(econ)
            self._yield_rooftop_oriented_cache[key] = (econ, out)
            return out

        shading_mult = self.rooftop_pv_shading_yield_multiplier()
        # (A12): DC-side electrical losses (inverter + string).
        dc_eff = max(0.0, 1.0 - econ.dc_loss_fraction())
        out: Dict[str, float] = {}
        for s in econ.slices:
            weighted = 0.0
            for orientation, cap in cap_by_orientation.items():
                cf = econ.pv_capacity_factor_by_orientation(s.id, orientation)
                weighted += cap * cf
            # (Realism audit A2): per-slice temperature derating.
            t_derate = econ.pv_temperature_derating(s.id)
            # (A19): per-month PM2.5 soiling + fog losses.
            # renormalised so the annual energy-weighted mean is
            # 1.0 - GSA PVOUT_specific already contains 3.5% soiling, so the
            # raw A19 multiplier double-charged the level. Seasonal shape is
            # preserved. See Economics.pv_soiling_yield_multiplier_for_month.
            soil_mult = econ.pv_soiling_yield_multiplier_for_month(s.month)
            fog_mult = econ.pv_fog_multiplier_for_month(s.month)
            out[s.id] = (weighted / total_cap * s.hours_per_year
                          * shading_mult * t_derate * dc_eff
                          * soil_mult * fog_mult)
        self._yield_rooftop_oriented_cache[key] = (econ, out)
        return out


# ---------------------------------------------------------------------------
# Helpers — cooling tech weighting + microclimate
# ---------------------------------------------------------------------------
def _weighted_cooling_w_per_m2(econ: Economics, category_name: str,
                                 cat) -> float:
    """Composite cooling W/m² for a category, using the cooling-tech mix.

    Falls back to the BuildingCategory's legacy `cooling_load_w_per_m2_peak`
    if no mix is configured for the category.
    """
    mix = econ.cooling_tech_mix_by_category.get(category_name)
    if mix is None:
        return getattr(cat, "cooling_load_w_per_m2_peak", 0.0)
    w = 0.0
    for tech_name, share in mix.items():
        tech = econ.cooling_technologies.get(tech_name, {})
        w += float(share) * float(tech.get("w_per_m2_peak", 0.0))
    #: the technology W/m2 values were derived
    # at a REFERENCE dwelling size. Where a category's actual dwelling differs,
    # a per-category correction re-states the AC count for the real dwelling
    # instead of inheriting a per-m2 intensity from a different one. Absent
    # from the table -> 1.0, so every other category is untouched. Derivation
    # and the honesty note live beside the table in economics.yaml.
    corr = float((econ.cooling_intensity_dwelling_correction or {})
                 .get(category_name, 1.0))
    return w * corr


def _microclimate_cooling_multiplier(grid: Grid, cell: Cell,
                                       econ: Economics) -> float:
    """Legacy four-neighbour cooling multiplier from Stage A context.

    the author requested the B2 distance-decay refactor be reverted:
    the four-neighbour heuristic remains for OPEN_SPACE / BLUE_SPACE
    contributions. ** (Realism audit B4)**: the party-wall
    term has been upgraded from a binary 4-neighbour count to a
    shared-wall-area-weighted reduction (continuous in heights). When
    `microclimate.party_wall_area_weighted` is true (default), the
    party-wall reduction scales with `min(my_height, neighbour_height) /
    (4 * my_height)` summed over built 4-neighbours, capped at
    `party_wall_max_reduction`. The 0.60 hard floor is retained.
    """
    if not cell.has_building:
        return 1.0

    mc = econ.microclimate or {}
    veg_per = float(mc.get("vegetation_cooling_reduction_per_neighbour_fraction", 0.05))
    blue_red = float(mc.get("blue_space_proximity_reduction", 0.05))
    party_per = float(mc.get("party_wall_reduction_per_built_neighbour", 0.015))
    party_max = float(mc.get("party_wall_max_reduction", 0.06))
    party_area_weighted = bool(mc.get("party_wall_area_weighted", True))
    tree_per = float(mc.get(
        "street_tree_cooling_reduction_per_treed_road_neighbour_fraction", 0.0))
    tree_max = float(mc.get("street_tree_cooling_max", 0.12))

    neighbours = grid.neighbours_4(cell.row, cell.col)
    green_neighbours = sum(
        1 for nb in neighbours
        if nb.land_use in {LandUse.OPEN_SPACE, LandUse.BLUE_SPACE}
    )

    veg_reduction = green_neighbours * veg_per
    blue_reduction = blue_red if any(
        nb.land_use == LandUse.BLUE_SPACE for nb in neighbours
    ) else 0.0

    # (Task 5): avenue/street trees on an adjacent ROAD cell shade +
    # transpire over this built cell, cutting its cooling load. Counts treed-road
    # 4-neighbours; capped. 0 when no road neighbour is treed (back-compat).
    treed_road_neighbours = sum(
        1 for nb in neighbours
        if nb.land_use == LandUse.ROAD and getattr(nb, "has_street_trees", False)
    )
    tree_reduction = min(tree_max, treed_road_neighbours * tree_per)

    # (audit B4): area-weighted party-wall coupling.
    if party_area_weighted and cell.height_m > 0:
        my_h = float(cell.height_m)
        total_envelope = 4.0 * my_h  # 4 facades; cell_size cancels in ratio
        party_share = 0.0
        for nb in neighbours:
            nb_h = float(nb.height_m)
            if nb.has_building and nb_h > 0:
                shared = min(my_h, nb_h)
                party_share += shared / total_envelope
        party_reduction = min(party_max, party_share * party_max)
    else:
        built_4nbr = sum(1 for nb in neighbours if nb.has_building)
        party_reduction = min(party_max, built_4nbr * party_per)

    total_reduction = veg_reduction + blue_reduction + party_reduction + tree_reduction
    return max(0.60, 1.0 - total_reduction)


# Yield-penalty constants for the building-height shading coupling.
# supervisor feedback: the SA optimiser already has a
# `solar_access_score` metric for shading-aware placement, but the Stage B/C
# dispatch ignored the shading effect on actual PV YIELD. These constants
# couple the geometric outcome into the per-cell yield multiplier.
#   SHADING_DELTA_M: a neighbour must be at least this much taller than the
#       PV-bearing cell's "panel-top" elevation to count as a shading offender
#       (matches the metric threshold).
#   GROUND_PV_PANEL_TOP_M: SOLAR_FARM rack height as seen from the south.
#   PER_OFFENDER_PENALTY: yield drop per shading offender (0.10 = 10%).
#   MAX_PENALTY: floor (cell never falls below 1 - MAX_PENALTY of its yield).
# NOTE a per-daypart directional refactor (eastern neighbours
# only shade morning slices, western only evening, etc.) was attempted
# and reverted;
# 100 m grid (where shadows actually reach across cells at higher sun
# altitudes) before adopting the directional model. At 200 m granularity
# the simpler annual-average scalar is the right fidelity.
#: single source of truth, core/shading_constants.py
from core.shading_constants import (
    PV_SHADING_DELTA_M, GROUND_PV_PANEL_TOP_M,
)

SHADING_DELTA_M = PV_SHADING_DELTA_M
PER_OFFENDER_PENALTY = 0.10
MAX_PENALTY = 0.40


# v2: cardinal-only facing options.
# SA picks `building_axis_deg` in {0, 90, 180, 270} representing the
# direction the principal facade points (0=N, 90=E, 180=S, 270=W).
# Thermal effects depend on the LONG AXIS (which two facades are large).
# The long axis is perpendicular to the principal-facing direction:
#   facing 0 (N)   or 180 (S) -> long axis E-W (large facades face N and S)
#   facing 90 (E)  or 270 (W) -> long axis N-S (large facades face E and W)
# Cooling-load multiplier (Punjab annual average):
#   Long axis E-W  (facing N or S) -> 0.95   -- S long facade catches winter
#                                              sun beneficially; SW summer
#                                              wind hits S long facade for
#                                              strong cross-ventilation;
#                                              easier to shade with eaves.
#   Long axis N-S  (facing E or W) -> 1.10   -- E facade soaks morning sun,
#                                              W facade soaks afternoon sun;
#                                              SW wind only hits short ends
#                                              so cross-vent is weaker.
# BIPV south-facade exposure (fraction of long facade that is south-facing):
#   facing 0 (N)   -> 1.00   long axis E-W, S long facade ("back") is full south
#   facing 180 (S) -> 1.00   long axis E-W, S long facade ("front") is full south
#   facing 90 (E)  -> 0.25   long axis N-S, only the short S end faces south
#   facing 270 (W) -> 0.25   long axis N-S, only the short S end faces south
# Wind alignment (Punjab SW prevailing wind, summer-dominant):
#   handled separately in `layout/metrics.py:building_wind_alignment_score`.
FACADE_COOLING_MULTIPLIER: Dict[float, float] = {
    0.0: 0.95,
    90.0: 1.10,
    180.0: 0.95,
    270.0: 1.10,
}
BIPV_FACADE_SOUTH_EXPOSURE: Dict[float, float] = {
    0.0: 1.00,
    90.0: 0.25,
    180.0: 1.00,
    270.0: 0.25,
}


def _facade_orientation_cooling_multiplier(cell: Cell) -> float:
    """Return the per-cell cooling-load multiplier from building axis."""
    if not cell.has_building:
        return 1.0
    axis_key = float(round(cell.building_axis_deg))
    return FACADE_COOLING_MULTIPLIER.get(axis_key, 1.0)


def _bipv_facade_orientation_multiplier(cell: Cell) -> float:
    """Return the per-cell BIPV-potential multiplier from building axis."""
    if not cell.has_building:
        return 0.0
    axis_key = float(round(cell.building_axis_deg))
    return BIPV_FACADE_SOUTH_EXPOSURE.get(axis_key, 0.50)


def _pv_shading_multiplier(grid: Grid, cell: Cell) -> float:
    """Per-cell PV-yield multiplier in [0.6, 1.0] from neighbour heights.

    For PV-bearing cells (built rooftops OR SOLAR_FARM), check the three
    southern directions (S, SW, SE) plus adjacent east + west. For each
    neighbour that exceeds the cell's panel-top elevation by more than
    SHADING_DELTA_M (default 6 m), apply a PER_OFFENDER_PENALTY (default
    10%) drop, capped at MAX_PENALTY (default 40%). Returns 1.0 (no
    penalty) for non-PV cells. The hard floor at 0.6 prevents the rule
    from zeroing out yield even in extreme geometry.

    This couples Stage A building-height decisions into Stage B/C PV
    yield, which was previously a known gap: the SA optimiser saw a
    `solar_access_score` penalty for placing PV near tall neighbours,
    but the dispatch ignored the effect on actual generation. With this
    coupling, the model now correctly reports lower PV yield AND lower
    cost benefit for shaded placements -- closing the feedback loop.

    Stage F (100 m grid) will refactor this to per-daypart directional
    shading (eastern offender -> morning only, western -> evening, etc.)
    when shadow geometry begins to matter inside cells.
    """
    if not (cell.has_building or cell.land_use == LandUse.SOLAR_FARM):
        return 1.0
    my_height = cell.height_m if cell.has_building else GROUND_PV_PANEL_TOP_M
    south_checks = [(-1, -1), (-1, 0), (-1, 1)]
    flank_checks = [(0, -1), (0, 1)]
    offenders = 0
    for dr, dc in south_checks + flank_checks:
        nr, nc = cell.row + dr, cell.col + dc
        if 0 <= nr < grid.n_rows and 0 <= nc < grid.n_cols:
            nb = grid.at(nr, nc)
            if nb.height_m - my_height > SHADING_DELTA_M:
                offenders += 1
    penalty = min(MAX_PENALTY, offenders * PER_OFFENDER_PENALTY)
    return 1.0 - penalty


# ---------------------------------------------------------------------------
# Load a Grid from a previously exported GeoJSON (no SA re-run).
# ---------------------------------------------------------------------------
def phased_land_multipliers(grid: Optional[Grid]) -> Dict[str, Dict[int, float]]:
    """STAGE-B18: per-period LAND growth multipliers for the
    area-phased techs, read from the layout's expansion tags (single source
    of truth with the map - layout/phased_expansion.py stamps them).

      solar_farm: (farm cells + solar_expansion tags unlocked by p) / farm
      carport   : (parking cells + parking_expansion tags by p) / parking

    Multiplies the multi-period farm/carport ceilings ALONGSIDE the TRJ-1
    density multiplier ("more land x better panels"). Returns 1.0 for every
    period when the grid is absent or carries no tags (pre-B18 layouts ->
    byte-exact back-compat).
    """
    out = {"solar_farm": {2030: 1.0, 2042: 1.0, 2055: 1.0},
           "carport": {2030: 1.0, 2042: 1.0, 2055: 1.0}}
    if grid is None:
        return out
    from core.land_use import LandUse
    n_farm = n_park = 0
    tags: Dict[str, int] = {}
    for c in grid.all_cells():
        if c.land_use == LandUse.SOLAR_FARM:
            n_farm += 1
        elif c.land_use == LandUse.PARKING_LOT:
            n_park += 1
        sub = c.amenity_subtype or ""
        if sub.startswith(("solar_expansion_", "parking_expansion_")):
            tags[sub] = tags.get(sub, 0) + 1
    if n_farm > 0 and any(k.startswith("solar_expansion") for k in tags):
        #: `solar_expansion_2030` added so the BASE YEAR can
        # carry released reserve.
        # the whole reserve up front - was written into economics.yaml
        # (`farm_land_cells_by_period`) but could not reach the LP, because this
        # function is the single source of truth for farm land and its tag
        # vocabulary had no 2030 term. The config key's only other production
        # consumer is the RENT accessor, so the town paid rent on 295 ha while
        # being allowed to build on 201. Releasing via land_use instead was
        # rejected: converting the 100 reserve cells to SOLAR_FARM would drop
        # open space 942 -> 842 (37.7% -> 33.7%) and breach the 38% target.
        # s30 defaults to 0, so every pre-existing layout is byte-exact.
        s30 = tags.get("solar_expansion_2030", 0)
        s42 = tags.get("solar_expansion_2042", 0)
        s55 = tags.get("solar_expansion_2055", 0)
        out["solar_farm"][2030] = (n_farm + s30) / n_farm
        out["solar_farm"][2042] = (n_farm + s30 + s42) / n_farm
        out["solar_farm"][2055] = (n_farm + s30 + s42 + s55) / n_farm
    if n_park > 0 and any(k.startswith("parking_expansion") for k in tags):
        p42 = tags.get("parking_expansion_2042", 0)
        p55 = tags.get("parking_expansion_2055", 0)
        out["carport"][2042] = (n_park + p42) / n_park
        out["carport"][2055] = (n_park + p42 + p55) / n_park
    return out


def grid_from_geojson(path: Optional[Path] = None) -> Tuple[Grid, str]:
    """Reconstruct a Grid from an exported geojson3d file."""
    path = Path(path) if path else DEFAULT_OPTIMISED_GEOJSON
    if not path.exists():
        raise FileNotFoundError(f"GeoJSON not found at {path}")
    with path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    meta = gj.get("metadata", {})
    inner_meta = meta.get("metadata", meta)
    grid_meta = inner_meta.get("grid", meta.get("grid", {}))
    n_rows = int(grid_meta.get("rows", 25))
    n_cols = int(grid_meta.get("cols", 25))
    cell_size_m = float(grid_meta.get("cell_size_m", 200.0))
    layout_name = inner_meta.get("layout", meta.get("layout", "optimised_sa"))

    grid = Grid.empty(n_rows=n_rows, n_cols=n_cols, cell_size_m=cell_size_m)
    seen_cells: set = set()
    for feature in gj.get("features", []):
        props = feature.get("properties", {})
        r = props.get("row")
        c = props.get("col")
        if r is None or c is None:
            continue
        key = (r, c)
        if key in seen_cells:
            continue
        if props.get("role") not in (None, "parcel"):
            continue
        try:
            lu = LandUse(props.get("land_use"))
        except (ValueError, TypeError):
            continue
        cell = grid.at(r, c)
        cell.land_use = lu
        tier_str = props.get("height_tier")
        if tier_str:
            try:
                cell.height_tier = HeightTier(tier_str)
            except ValueError:
                cell.height_tier = None
        else:
            cell.height_tier = None
        cell.height_m = float(props.get("cell_height_m", 0.0))
        cell.albedo = float(props.get("albedo", 0.20))
        cell.vegetation_fraction = float(props.get("vegetation_fraction", 0.0))
        # (Priority 2): per-cell building axis. Older GeoJSON
        # files without the field default to 0.0 (N-S long axis), matching
        # the pre-axis behaviour.
        cell.building_axis_deg = float(props.get("building_axis_deg", 0.0))
        # (Item 2): per-cell faith tag (RELIGIOUS only). Older
        # GeoJSON files without the field load with None; EnergyNetwork.
        # from_grid then re-runs the deterministic assignment.
        faith_val = props.get("faith")
        cell.faith = str(faith_val) if faith_val else None
        # (Item 3): per-cell carport-site marker. Older
        # GeoJSON files without the field load with False; EnergyNetwork.
        # from_grid then re-runs the deterministic carport siting.
        cell.is_carport_site = bool(props.get("is_carport_site", False))
        #: per-cell entrance side(s).
        # Older GeoJSON files load empty; EnergyNetwork.from_grid then
        # re-runs the deterministic assignment.
        es = props.get("entrance_sides")
        if isinstance(es, list):
            cell.entrance_sides = [int(x) for x in es]
        #: per-BLUE_SPACE-cell flag
        # marking the cell as a deployable floating-PV site (cluster
        # size >= min_cluster_size). Older GeoJSON files without the
        # field load False/None; EnergyNetwork.from_grid then re-runs
        # the deterministic clustering.
        cell.is_floating_pv_site = bool(props.get("is_floating_pv_site", False))
        cid = props.get("floating_pv_cluster_id")
        cell.floating_pv_cluster_id = (
            int(cid) if isinstance(cid, (int, float)) and cid is not None else None
        )
        # (Task 5): per-ROAD-cell street-furniture tags. Older
        # GeoJSON files without the fields load False/None; the values are
        # re-derivable by layout.street_furniture.place_street_furniture.
        cell.has_street_trees = bool(props.get("has_street_trees", False))
        sl_type = props.get("streetlight_type")
        cell.streetlight_type = str(sl_type) if sl_type else None
        # (Part 4): segment-aware streetlight tags. Older GeoJSON
        # without the fields loads None/-1; re-derivable by place_street_furniture.
        seg = props.get("streetlight_segment_id")
        cell.streetlight_segment_id = (
            int(seg) if isinstance(seg, (int, float)) and seg is not None
            and int(seg) >= 0 else None
        )
        reason = props.get("streetlight_reason")
        cell.streetlight_reason = str(reason) if reason else None
        sub = props.get("amenity_subtype")
        cell.amenity_subtype = str(sub) if sub else None
        # STAGE-: road hierarchy fields. Older GeoJSON files
        # load None/0; layout.road_network.tag_road_classes re-derives them
        # geometrically (locked flags do not round-trip - the classes do).
        rc = props.get("road_class")
        cell.road_class = str(rc) if rc else None
        cell.road_width_m = float(props.get("road_width_m", 0.0) or 0.0)
        seen_cells.add(key)
    # STAGE-/: sub-cell street/path segments (role
    # "street_edge") back onto the grid so ROW accounting, walkability and
    # re-exports survive the round-trip. Older files simply have none.
    from core.grid import StreetEdge
    edges = []
    for feature in gj.get("features", []):
        props = feature.get("properties", {})
        if props.get("role") != "street_edge":
            continue
        a = props.get("cell_a")
        b = props.get("cell_b")
        if not (isinstance(a, list) and isinstance(b, list)
                and len(a) == 2 and len(b) == 2):
            continue
        edges.append(StreetEdge(
            a=(int(a[0]), int(a[1])), b=(int(b[0]), int(b[1])),
            kind=str(props.get("kind", "local_street")),
            width_m=float(props.get("width_m", 0.0) or 0.0),
            modes=tuple(str(m) for m in props.get("modes", []) or ()),
        ))
    grid.street_edges = edges
    return grid, layout_name


def load_optimised_network(
    geojson_path: Optional[Path] = None,
    cfg: Optional[DistrictConfig] = None,
    norms: Optional[DemandNorms] = None,
    econ: Optional[Economics] = None,
) -> EnergyNetwork:
    grid, layout_name = grid_from_geojson(geojson_path)
    return EnergyNetwork.from_grid(grid, cfg=cfg, norms=norms, econ=econ,
                                    layout_name=layout_name)


if __name__ == "__main__":
    net = load_optimised_network()
    econ = load_economics()
    print(f"loaded network from {net.layout_name}")
    print(f"  {len(net.nodes)} nodes, {len(net.edges)} ROAD-ROAD edges")
    print(f"  built nodes: {len(net.built_nodes())}")
    print(f"  residential nodes: {len(net.residential_nodes())} "
          f"({net.total_households():,} households)")
    print(f"  solar-farm nodes: {len(net.solar_farm_nodes())} "
          f"({net.total_solar_farm_cap_kwp():,.0f} kWp ceiling)")
    print(f"  rooftop PV ceiling: {net.total_rooftop_pv_cap_kwp():,.0f} kWp")
    print(f"  total peak demand: {net.total_peak_demand_kw():,.0f} kW")
    annual = net.annual_demand_kwh(econ)
    print(f"  annual energy demand: {annual / 1e6:,.1f} GWh/yr")
    yields = net.pv_yield_per_kwp_kwh(econ)
    print(f"  PV yield/kWp range across {len(yields)} slices: "
          f"{min(yields.values()):.0f}-{max(yields.values()):.0f} kWh/kWp")
