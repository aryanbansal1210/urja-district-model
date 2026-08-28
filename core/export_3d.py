"""Export district layouts as 3D-ready GeoJSON.

This module is deliberately separate from ``core.visualise``.  The SVG output
is a presentation drawing; this exporter uses the model objects as the source
of truth and writes georeferenced polygons that can be opened in Kepler,
Foursquare Spatial Desktop, deck.gl, or any GIS tool that understands GeoJSON.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.building import building_from_cell
from core.config import DistrictConfig, load_config
from core.demographics import DemandNorms, load_demand_norms, load_demographics
from core.grid import Cell, Grid
from core.land_use import DEFAULT_PV_ORIENTATION, LAND_USE_COLOURS, LandUse
from core.requirements import derive_requirements
from core.visualise import to_svg
from layout.generator import ARCHETYPES, generate
from layout.optimiser import anneal


DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "geojson3d"
# 2D SVG companions are written alongside so the 2D map and 3D viewer can
# never drift out of sync.
DEFAULT_SVG_DIR = Path(__file__).parent.parent / "outputs" / "geojson"
DEFAULT_LAYOUTS = tuple(ARCHETYPES.keys())
OPTIMISED_LAYOUT = "optimised_sa"
ALL_LAYOUTS = DEFAULT_LAYOUTS + (OPTIMISED_LAYOUT,)
METRES_PER_DEGREE_LAT = 111_320.0
GROUND_MOUNT_KWP_PER_M2_DEFAULT = 0.10

_DEFAULT_ECONOMICS_PATH = (
    Path(__file__).parent.parent / "config" / "economics.yaml"
)


def _load_pv_orientation_defaults() -> Dict[str, str]:
    """Read ``pv_orientation_defaults_by_category`` from ``config/economics.yaml``.

    Returns an empty dict if the file is missing or the block isn't set,
    in which case the viewer's client-side ``PV_ORIENTATION_BY_CATEGORY``
    fallback takes over.
    """
    if not _DEFAULT_ECONOMICS_PATH.exists():
        return {}
    try:
        import yaml  # local import keeps export_3d's hot path light
        with _DEFAULT_ECONOMICS_PATH.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception:
        return {}
    defaults = raw.get("pv_orientation_defaults_by_category") or {}
    return {str(k): str(v) for k, v in defaults.items()}


# (Claude 2 self-review follow-up): lazy single-shot cache. The
# YAML is read on first parcel-export call (not at module import), so an
# sessions is picked up on the next export without needing a process
# restart. Call ``_pv_orientation_defaults_cache.clear`` from tests if
# they need to force a re-read.
_PV_ORIENTATION_CACHE: Dict[str, Dict[str, str]] = {}


def _pv_orientation_defaults() -> Dict[str, str]:
    if "loaded" not in _PV_ORIENTATION_CACHE:
        _PV_ORIENTATION_CACHE["loaded"] = _load_pv_orientation_defaults()
    return _PV_ORIENTATION_CACHE["loaded"]


def _floating_pv_min_cluster_size() -> int:
    """Read `floating_pv.site_selection.min_cluster_size` from economics.yaml.

    Defaults to 2 (drops isolated BLUE_SPACE singletons from the floating-PV
    cap). Setting to 1 in YAML restores the legacy "every water cell hosts"
    behaviour without code changes.
    """
    from layout.floating_pv_siting import DEFAULT_MIN_CLUSTER_SIZE
    if not _DEFAULT_ECONOMICS_PATH.exists():
        return DEFAULT_MIN_CLUSTER_SIZE
    try:
        import yaml
        with _DEFAULT_ECONOMICS_PATH.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception:
        return DEFAULT_MIN_CLUSTER_SIZE
    block = (raw.get("floating_pv") or {}).get("site_selection") or {}
    try:
        return max(1, int(block.get("min_cluster_size", DEFAULT_MIN_CLUSTER_SIZE)))
    except (TypeError, ValueError):
        return DEFAULT_MIN_CLUSTER_SIZE


Rect = Tuple[float, float, float, float]


def _hex_to_rgb(hex_colour: str) -> List[int]:
    """Convert ``#RRGGBB`` to ``[r, g, b]``."""
    raw = hex_colour.strip().lstrip("#")
    return [int(raw[i:i + 2], 16) for i in (0, 2, 4)]


def _ground_mount_kwp_per_m2(norms: Optional[DemandNorms]) -> float:
    """Read ground-mount PV density (kWp/m²) from norms with a sane fallback."""
    if norms is None:
        return GROUND_MOUNT_KWP_PER_M2_DEFAULT
    return float(norms.solar.get(
        "ground_mount_kwp_per_m2", GROUND_MOUNT_KWP_PER_M2_DEFAULT,
    ))


_FLOATING_PV_PARAMS_CACHE: Dict[str, Dict[str, float]] = {}


def _floating_pv_params() -> Dict[str, float]:
    """Read `floating_pv.{kwp_per_cell_default, default_uptake_fraction}` from YAML.

    Cached for the lifetime of the process. Defaults mirror the YAML
    schema (1500 kWp/cell, 0.30 uptake) so test grids without the YAML
    still get a sensible non-zero per-cell number.
    """
    if "loaded" in _FLOATING_PV_PARAMS_CACHE:
        return _FLOATING_PV_PARAMS_CACHE["loaded"]
    defaults = {"kwp_per_cell_default": 1500.0, "default_uptake_fraction": 0.30,
                "canal_kwp_per_cell": 210.0}
    if _DEFAULT_ECONOMICS_PATH.exists():
        try:
            import yaml
            with _DEFAULT_ECONOMICS_PATH.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            block = raw.get("floating_pv") or {}
            defaults["kwp_per_cell_default"] = float(
                block.get("kwp_per_cell_default", defaults["kwp_per_cell_default"])
            )
            defaults["default_uptake_fraction"] = float(
                block.get("default_uptake_fraction", defaults["default_uptake_fraction"])
            )
            canal = block.get("canal") or {}
            defaults["canal_kwp_per_cell"] = float(
                canal.get("kwp_per_cell", defaults["canal_kwp_per_cell"])
            )
        except Exception:
            pass
    _FLOATING_PV_PARAMS_CACHE["loaded"] = defaults
    return defaults


def _carport_kwp_for_export(cell: Cell) -> float:
    """Per-cell carport PV nameplate (kWp) for the GeoJSON export.

    0 on cells not tagged as a carport site (most cells). Tagged cells
    return the category-specific kWp from `carport_kwp_for_cell` (e.g.
    SHOPPING_CENTRE 1500, OFFICE/HEALTHCARE/PUBLIC_SERVICES/HOTEL 1000,
    RESIDENTIAL_HIGH 600, WAREHOUSE/LIGHT_INDUSTRY 1200). ROAD is
    explicitly excluded by the eligibility list so this
    function never sees a ROAD-tagged carport.
    """
    if not bool(getattr(cell, "is_carport_site", False)):
        return 0.0
    from layout.carport_siting import carport_kwp_for_cell
    return carport_kwp_for_cell(cell)


def _floating_pv_deployable_kwp_for(cell: Cell) -> float:
    """Per-cell floating-PV deployable nameplate (kWp).

    Returns the YAML `kwp_per_cell_default × default_uptake_fraction`
    product when `cell.is_floating_pv_site` is True, else 0. The aggregate
    LP ceiling is the sum of this across cluster-tagged cells.

    STAGE- (Q23): CANAL cells (amenity_subtype "canal") return the
    canal-top density instead - 210 kWp per 100 m cell = 2.1 MW/km (PEDA
    Sidhwan/Ghaggar), matching
    ``EnergyNetwork.total_floating_pv_potential_kwp``.
    """
    if not bool(getattr(cell, "is_floating_pv_site", False)):
        return 0.0
    params = _floating_pv_params()
    if getattr(cell, "amenity_subtype", None) == "canal":
        return params["canal_kwp_per_cell"]
    return params["kwp_per_cell_default"] * params["default_uptake_fraction"]


def _deployable_pv_kwp_for(cell: Cell,
                             cfg: DistrictConfig,
                             norms: Optional[DemandNorms]) -> float:
    """Per-cell deployable PV nameplate (kWp).

    Built cells use their rooftop projection from ``building_from_cell``.
    ``SOLAR_FARM`` cells use the ground-mount density from
    ``config/demand_norms.yaml`` and their cell footprint, matching the
    formula already used by ``layout.metrics.solar_capacity_score``. Other
    non-built cells return 0.
    """
    if cell.land_use == LandUse.SOLAR_FARM:
        return cell.cell_size_m ** 2 * _ground_mount_kwp_per_m2(norms)
    building = building_from_cell(cell, cfg)
    return building.deployable_pv_kwp if building is not None else 0.0


def _cell_base_properties(
    layout_name: str,
    cell: Cell,
    cfg: DistrictConfig,
    norms: Optional[DemandNorms] = None,
    shading_lookup: Optional[Dict[Tuple[int, int], float]] = None,
    deployed_lookup: Optional[Dict[Tuple[int, int], float]] = None,
    shading_diagnostics: Optional[Dict[Tuple[int, int], Dict[str, object]]] = None,
    #: this parameter was MISSING while the body below
    # already read `solar_thermal_lookup` - an unconditional NameError on
    # every call, i.e. `export_3d` could not export ANYTHING. It landed with
    # the solar-thermal export work after the 03:16 suite
    # finished, so no green run ever covered it, and the geojson on disk
    # (dated) carries no `solar_thermal_m2` key at all. Caught by
    # the DENS batch suite. Default None keeps every caller that does not
    # allocate collectors (baseline archetypes, structures) byte-identical.
    solar_thermal_lookup: Optional[Dict[Tuple[int, int], float]] = None,
) -> Dict[str, object]:
    """Common properties attached to every exported feature."""
    building = building_from_cell(cell, cfg)
    colour = LAND_USE_COLOURS.get(cell.land_use, "#dddddd")
    # v2: surface the geometric shading multiplier so the
    # viewer can read it directly rather than recomputing a heuristic
    # client-side. Default 1.0 (no penalty) if not provided.
    pv_shade = 1.0
    if shading_lookup is not None:
        pv_shade = float(shading_lookup.get((cell.row, cell.col), 1.0))
    #: per-cell shading diagnostics so the viewer
    # can EXPLAIN red cells. Defaults: percentile 1.0 (unshaded), no
    # offenders, no reason string.
    shading_diag: Dict[str, object] = {
        "percentile": 1.0,
        "offender_dirs": [],
        "reason": "",
    }
    if shading_diagnostics is not None:
        shading_diag = shading_diagnostics.get((cell.row, cell.col), shading_diag)
    # (A17): LP-deployed rooftop PV (kWp) allocated to this
    # cell via greedy-by-yield from the aggregate scenario capacity.
    # Defaults to 0.0 when no dispatch result is on disk (baseline
    # archetypes; pre-dispatch first-run).
    pv_deployed = 0.0
    solar_thermal_m2 = float((solar_thermal_lookup or {}).get(
        (cell.row, cell.col), 0.0))
    if deployed_lookup is not None:
        pv_deployed = float(deployed_lookup.get((cell.row, cell.col), 0.0))
    # (Stage F #1 cleanup, Claude 2): write the per-cell PV
    # orientation default into the GeoJSON so the viewer no longer needs
    # the client-side `PV_ORIENTATION_BY_CATEGORY` mirror as the source
    # of truth. Resolved via `pv_orientation_defaults_by_category` in
    # `config/economics.yaml`. Defaults to "south_fixed" for unbuilt /
    # unknown categories (matches Economics.pv_orientation_default_for_category).
    pv_orientation = DEFAULT_PV_ORIENTATION
    if building is not None and building.category is not None:
        cat_name = building.category.name
        pv_orientation = _pv_orientation_defaults().get(cat_name, DEFAULT_PV_ORIENTATION)
    return {
        "layout": layout_name,
        "row": cell.row,
        "col": cell.col,
        "cell_id": f"{cell.row:02d}_{cell.col:02d}",
        "land_use": cell.land_use.value,
        "height_tier": cell.height_tier.value if cell.height_tier else None,
        "cell_height_m": round(cell.height_m, 3),
        "colour": colour,
        "colour_rgb": _hex_to_rgb(colour),
        "households": building.households if building else 0,
        "floor_area_m2": round(building.total_floor_area_m2, 3) if building else 0.0,
        "deployable_pv_kwp": round(
            _deployable_pv_kwp_for(cell, cfg, norms), 3,
        ),
        "albedo": round(cell.albedo, 3),
        "vegetation_fraction": round(cell.vegetation_fraction, 3),
        "is_built": cell.has_building,
        # (Priority 2 v2 cardinal): per-cell building facing
        # direction in degrees (0=N, 90=E, 180=S, 270=W). Chosen by SA.
        "building_axis_deg": round(cell.building_axis_deg, 1),
        # v2: geometric annual-average PV-yield shading
        # multiplier in [0, 1]. Computed via energy.solar_geometry
        # (sun-path x building footprints). Replaces the viewer's
        # client-side step-function heuristic. 1.0 = no penalty.
        "pv_shading_multiplier_geom": round(pv_shade, 3),
        #: rank of this cell within the layout's
        # actual shading distribution. 0.0 = most shaded in this layout,
        # 1.0 = least shaded. Matches the viewer's dynamic-ramp ordering,
        # so a viewer-red cell will have a low percentile here even if
        # the absolute multiplier is in the high 0.8s. Allows the viewer
        # to explain "red = relatively worst in this layout, not 40 %
        # physical loss".
        "pv_shading_percentile": shading_diag.get("percentile", 1.0),
        #: cardinal directions of 8-neighbour
        # cells with a roof at least 6 m above this cell's PV plane.
        # Cheap geometric scan -- the multiplier itself is the full
        # sun-path integration. Use this to tell the viewer "shaded by
        # 2 tall S/SW neighbours" without having to recompute the
        # integration client-side.
        "pv_shading_offender_dirs": list(shading_diag.get("offender_dirs", [])),
        #: short human-readable string combining
        # the multiplier, percentile, and offender directions. Suitable
        # for direct insertion into hover tooltips and the selected-cell
        # panel.
        "pv_shading_reason": shading_diag.get("reason", ""),
        # (A17): LP-realised rooftop PV in kWp on THIS cell
        # (greedy-by-yield allocation from the aggregate scenario
        # capacity). 0.0 means the LP did not deploy here even though
        # `deployable_pv_kwp` may be > 0 -- ceiling, not realised.
        "pv_deployed_kwp": round(pv_deployed, 2),
        #: LP-realised SOLAR THERMAL collector area in m2
        # on THIS cell. Allocated by `_allocate_roof_jointly` against the same
        # roof budget as `pv_deployed_kwp`, so the two can never cover the same
        # square metre - which is what the LP's `st_roof_share` constraint
        # enforces on district totals. 0.0 means no collector here: either the
        # category is not one of the eight that draw hot water, or the roof was
        # taken. WHICH roof carries a collector is an allocation convention,
        # not an LP output; the LP decides only the district total.
        "solar_thermal_m2": round(solar_thermal_m2, 2),
        # (Stage F #1): per-cell PV orientation default from
        # economics.yaml. Viewer prefers this prop; falls back to its
        # client-side category map only if absent.
        "pv_orientation": pv_orientation,
        # (Item 2): per-cell faith tag for RELIGIOUS cells
        # (Punjab Census 2011 shares: sikh ~57% / hindu ~38% / muslim
        # ~2% / christian ~1%, with min-1 floor for muslim+christian).
        # Empty string for non-RELIGIOUS cells so the GeoJSON schema
        # stays simple (single string field).
        "faith": cell.faith or "",
        # (Item 3): per-cell carport-site marker. True when
        # this cell was picked by `layout.carport_siting.place_carports`
        # as a discrete carport host (within ~800 m of an industry/
        # office/healthcare anchor, balanced across quadrants).
        "is_carport_site": bool(cell.is_carport_site),
        #: per-cell carport PV
        # nameplate (kWp) at south-facing fixed-tilt. Derived from
        # `layout.carport_siting.carport_kwp_for_cell` so the viewer
        # can size the panel-block visualisation directly without
        # re-hardcoding the per-category footprint map. 0 on non-
        # carport-site cells. ROAD cells deliberately return 0 (the
        # carport-off-road fix removed ROAD from eligibility).
        "carport_kwp": round(_carport_kwp_for_export(cell), 1),
        #: cardinal degrees where the
        # building entrance(s) face. Single-int list for most cells;
        # two-int list for RETAIL_HIGHSTREET cells that ALSO have a
        # ROAD 4-neighbour (front shop + back-shop opening to the
        # highstreet). Empty for non-built cells.
        "entrance_sides": list(cell.entrance_sides or []),
        #: BLUE_SPACE parcels flagged
        # by `layout.floating_pv_siting.assign_floating_pv_sites` as
        # part of a deployable cluster (default min_cluster_size = 2).
        # Singletons stay False; the viewer should treat False BLUE_SPACE
        # cells as panel-free ornamental water. `floating_pv_deployable_kwp`
        # carries the per-cell deployable nameplate (0 when not a site);
        # `floating_pv_cluster_id` (1-indexed) identifies the contiguous
        # cluster for grouping in the viewer.
        "is_floating_pv_site": bool(cell.is_floating_pv_site),
        "floating_pv_cluster_id": cell.floating_pv_cluster_id,
        "floating_pv_deployable_kwp": round(
            _floating_pv_deployable_kwp_for(cell), 3,
        ),
        # (Task 5): ROAD-cell street furniture tagged by
        # `layout.street_furniture.place_street_furniture`. `has_street_trees`:
        # avenue trees line this road (cools adjacent built cells).
        # `streetlight_type`: "solar" (off-grid, no grid load) or "grid" (mains,
        "has_street_trees": bool(cell.has_street_trees),
        "streetlight_type": cell.streetlight_type or "",
        # solar/grid lamps by segment_id + shows the reason on hover.
        "streetlight_segment_id": (cell.streetlight_segment_id
                                   if cell.streetlight_segment_id is not None
                                   else -1),
        "streetlight_reason": cell.streetlight_reason or "",
        # (batch-A): SCHOOL/HEALTHCARE hover sub-type (URDPFI/IPHS).
        # "primary"/"secondary" or "UPHC"/"UCHC"; "" elsewhere.
        "amenity_subtype": cell.amenity_subtype or "",
        # STAGE-: road hierarchy on ROAD
        # cells - "arterial"/"collector"/"local" + the right-of-way width in
        # metres (the honest road-area unit: only width_m x 100 m of the
        # cell is road; the remainder is verge + frontage). "" / 0 on
        # non-ROAD cells. The viewer renders carriageway width by class.
        "road_class": cell.road_class or "",
        "road_width_m": round(cell.road_width_m, 1),
    }


def _local_cell_rect(grid: Grid, cell: Cell, rect: Rect) -> List[Tuple[float, float]]:
    """Return a closed ring in local metres centred on the district.

    ``rect`` is expressed as fractions of the cell width:
    ``(-0.5, -0.5, 0.5, 0.5)`` is the full 200 m cell.
    """
    x0_frac, y0_frac, x1_frac, y1_frac = rect
    district_w = grid.n_cols * grid.cell_size_m
    district_h = grid.n_rows * grid.cell_size_m
    cx = cell.centre_x_m - district_w / 2.0
    cy = cell.centre_y_m - district_h / 2.0
    s = cell.cell_size_m
    x0, x1 = cx + x0_frac * s, cx + x1_frac * s
    y0, y1 = cy + y0_frac * s, cy + y1_frac * s
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def _metres_to_lonlat(east_m: float, north_m: float,
                      cfg: DistrictConfig) -> List[float]:
    """Convert local metres to WGS84 lon/lat around the configured site."""
    lat0 = float(cfg.site.get("latitude", 0.0))
    lon0 = float(cfg.site.get("longitude", 0.0))
    lon_scale = METRES_PER_DEGREE_LAT * math.cos(math.radians(lat0))
    if abs(lon_scale) < 1e-9:
        raise ValueError("site latitude is too close to the pole for this exporter")
    return [
        lon0 + east_m / lon_scale,
        lat0 + north_m / METRES_PER_DEGREE_LAT,
    ]


def _geojson_ring(grid: Grid, cell: Cell, rect: Rect,
                  cfg: DistrictConfig) -> List[List[float]]:
    return [
        _metres_to_lonlat(x, y, cfg)
        for x, y in _local_cell_rect(grid, cell, rect)
    ]


def _feature(
    grid: Grid,
    cell: Cell,
    rect: Rect,
    cfg: DistrictConfig,
    properties: Dict[str, object],
) -> Dict[str, object]:
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [_geojson_ring(grid, cell, rect, cfg)],
        },
        "properties": properties,
    }


def _parcel_feature(grid: Grid, cell: Cell, layout_name: str,
                    cfg: DistrictConfig,
                    norms: Optional[DemandNorms] = None,
                    shading_lookup: Optional[Dict[Tuple[int, int], float]] = None,
                    solar_thermal_lookup: Optional[Dict[Tuple[int, int], float]] = None,
                    deployed_lookup: Optional[Dict[Tuple[int, int], float]] = None,
                    shading_diagnostics: Optional[Dict[Tuple[int, int], Dict[str, object]]] = None,
                    lighting_lookup: Optional[Dict[Tuple[int, int], list]] = None,
                    ) -> Dict[str, object]:
    #: the parcel is the feature that carries the collector area, so it
    # is the one call site that forwards the lookup (structures sit on the
    # same roof and must not double-count it).
    props = _cell_base_properties(layout_name, cell, cfg, norms,
                                    shading_lookup, deployed_lookup,
                                    shading_diagnostics,
                                    solar_thermal_lookup)
    # (Part 4 / night-scene): weekday occupancy-by-daypart (12 vals,
    # 00_02..22_24) = building "brightness" at each 2-h slot for the viewer's
    # night glow. Empty list for non-built cells. Render-only; no energy effect.
    light_profile = (lighting_lookup or {}).get((cell.row, cell.col), [])
    props.update({
        "feature_id": f"{layout_name}_{cell.row:02d}_{cell.col:02d}_parcel",
        "role": "parcel",
        "part": "cell_base",
        "part_index": 0,
        "height_m": _surface_height(cell.land_use),
        "base_elevation_m": 0.0,
        "lighting_by_daypart": light_profile,
    })
    return _feature(grid, cell, (-0.5, -0.5, 0.5, 0.5), cfg, props)


def _structure_features(grid: Grid, cell: Cell, layout_name: str,
                        cfg: DistrictConfig,
                        norms: Optional[DemandNorms] = None,
                        shading_lookup: Optional[Dict[Tuple[int, int], float]] = None,
                        deployed_lookup: Optional[Dict[Tuple[int, int], float]] = None,
                        shading_diagnostics: Optional[Dict[Tuple[int, int], Dict[str, object]]] = None,
                        ) -> List[Dict[str, object]]:
    forms = _typology_forms(cell)
    out: List[Dict[str, object]] = []
    base = _cell_base_properties(layout_name, cell, cfg, norms,
                                   shading_lookup, deployed_lookup,
                                   shading_diagnostics)

    for i, (part, rect, height_m) in enumerate(forms, start=1):
        props = dict(base)
        props.update({
            "feature_id": f"{layout_name}_{cell.row:02d}_{cell.col:02d}_{part}_{i}",
            "role": "structure",
            "part": part,
            "part_index": i,
            "height_m": round(height_m, 3),
            "base_elevation_m": 0.0,
        })
        out.append(_feature(grid, cell, rect, cfg, props))
    return out


def _surface_height(land_use: LandUse) -> float:
    """Low extrusion for non-building surfaces in generic GIS viewers."""
    if land_use == LandUse.ROAD:
        return 0.15
    if land_use == LandUse.OPEN_SPACE:
        return 0.20
    if land_use == LandUse.BLUE_SPACE:
        # Slightly below ground plane so a transparent water polygon
        # reads as a pond surface, not an extruded building tile.
        return 0.05
    if land_use == LandUse.SOLAR_FARM:
        return 0.25
    if land_use == LandUse.PARKING_LOT:
        return 0.15   # flat asphalt surface (carport canopy rendered viewer-side)
    return 0.35


def _typology_forms(cell: Cell) -> List[Tuple[str, Rect, float]]:
    """Return simple typology-specific building footprints for a cell."""
    h = max(cell.height_m, 0.0)
    lu = cell.land_use

    if lu == LandUse.RESIDENTIAL_LOW:
        return [
            ("ews_slab", (-0.38, -0.34, -0.08, -0.22), h),
            ("ews_slab", (0.08, -0.34, 0.38, -0.22), h),
            ("ews_slab", (-0.38, 0.00, -0.08, 0.12), h),
            ("ews_slab", (0.08, 0.00, 0.38, 0.12), h),
            ("courtyard_edge", (-0.16, 0.26, 0.16, 0.36), max(3.0, h * 0.45)),
        ]
    if lu == LandUse.RESIDENTIAL_MID:
        return [
            ("mid_slab", (-0.35, -0.30, 0.35, -0.16), h),
            ("mid_slab", (-0.35, 0.02, 0.35, 0.16), h),
            ("mid_corner", (-0.28, 0.28, -0.06, 0.42), max(3.0, h * 0.65)),
            ("mid_corner", (0.06, 0.28, 0.28, 0.42), max(3.0, h * 0.65)),
        ]
    if lu == LandUse.RESIDENTIAL_HIGH:
        return [
            ("high_tower", (-0.30, -0.30, -0.08, -0.08), h),
            ("high_tower", (0.08, -0.30, 0.30, -0.08), h),
            ("high_tower", (-0.30, 0.08, -0.08, 0.30), h),
            ("high_tower", (0.08, 0.08, 0.30, 0.30), h),
        ]
    if lu == LandUse.SCHOOL:
        return [
            ("school_block", (-0.42, -0.24, 0.18, -0.08), h),
            ("school_block", (-0.42, 0.08, 0.18, 0.24), h),
            ("school_hall", (0.24, -0.20, 0.42, 0.20), max(4.0, h * 0.75)),
        ]
    if lu == LandUse.OFFICE:
        return [
            ("office_podium", (-0.36, -0.36, 0.36, 0.36), max(5.0, h * 0.35)),
            ("office_tower", (-0.18, -0.18, 0.18, 0.18), h),
        ]
    if lu == LandUse.SHOPPING_CENTRE:
        return [
            ("retail_podium", (-0.42, -0.34, 0.42, 0.28), h),
            ("atrium_cap", (-0.14, -0.06, 0.14, 0.20), max(3.0, h * 0.45)),
        ]
    if lu == LandUse.RETAIL_HIGHSTREET:
        # Linear ground-floor retail along a road frontage. Two narrow
        # parallel strips reading as a high-street block with a service
        # lane between them, plus a small marker for a ground-floor stair.
        return [
            ("highstreet_strip", (-0.42, -0.32, 0.42, -0.10), h),
            ("highstreet_strip", (-0.42, 0.10, 0.42, 0.32), h),
            ("highstreet_stair", (-0.06, -0.06, 0.06, 0.06),
             max(3.0, h * 0.5)),
        ]
    if lu == LandUse.RESTAURANT_FOOD:
        return [
            ("food_cluster", (-0.36, -0.30, -0.04, -0.02), h),
            ("food_cluster", (0.06, -0.28, 0.34, -0.02), max(3.0, h * 0.85)),
            ("food_cluster", (-0.18, 0.10, 0.24, 0.32), max(3.0, h * 0.75)),
        ]
    if lu == LandUse.HOTEL_GUESTHOUSE:
        return [
            ("hotel_podium", (-0.34, -0.34, 0.34, -0.04), max(5.0, h * 0.35)),
            ("hotel_bar", (-0.18, -0.02, 0.18, 0.38), h),
        ]
    if lu == LandUse.HEALTHCARE:
        return [
            ("healthcare_wing", (-0.40, -0.12, 0.40, 0.10), h),
            ("healthcare_wing", (-0.10, -0.38, 0.12, 0.38), max(5.0, h * 0.8)),
        ]
    if lu == LandUse.LIGHT_INDUSTRY:
        return [
            ("industry_shed", (-0.44, -0.34, 0.44, 0.08), h),
            ("industry_office", (-0.36, 0.18, -0.06, 0.36), max(4.0, h * 0.55)),
        ]
    if lu == LandUse.WAREHOUSE:
        return [
            ("warehouse_shed", (-0.44, -0.36, 0.44, 0.34), h),
        ]
    if lu == LandUse.PUBLIC_SERVICES:
        return [
            ("civic_block", (-0.30, -0.28, 0.30, 0.16), h),
            ("civic_marker", (-0.08, 0.24, 0.08, 0.36), max(4.0, h * 0.7)),
        ]
    if lu == LandUse.RELIGIOUS:
        # Walled precinct + central prayer hall + a slimmer marker for the
        # spire / dome / minaret / gurudwara nishan sahib.
        return [
            ("religious_precinct", (-0.36, -0.36, 0.36, 0.36),
             max(2.5, h * 0.35)),
            ("religious_hall", (-0.20, -0.18, 0.20, 0.18), h),
            ("religious_marker", (-0.06, -0.06, 0.06, 0.06),
             max(6.0, h * 1.6)),
        ]
    if lu == LandUse.SOLAR_FARM:
        return [
            ("solar_array", (-0.42, -0.36, 0.42, -0.30), 1.5),
            ("solar_array", (-0.42, -0.20, 0.42, -0.14), 1.5),
            ("solar_array", (-0.42, -0.04, 0.42, 0.02), 1.5),
            ("solar_array", (-0.42, 0.12, 0.42, 0.18), 1.5),
            ("solar_array", (-0.42, 0.28, 0.42, 0.34), 1.5),
        ]
    return []


def _bounds(features: Sequence[Dict[str, object]]) -> List[float]:
    lons: List[float] = []
    lats: List[float] = []
    for feature in features:
        geom = feature["geometry"]  # type: ignore[index]
        # Polygon coordinates = [ring,...] where ring = [[lon, lat],...];
        # STAGE-/ street_edge features are LineStrings whose
        # coordinates are ALREADY the [[lon, lat],...] list (no ring).
        if geom["type"] == "LineString":  # type: ignore[index]
            coords = geom["coordinates"]  # type: ignore[index]
        else:
            coords = geom["coordinates"][0]  # type: ignore[index]
        for lon, lat in coords:
            lons.append(float(lon))
            lats.append(float(lat))
    return [min(lons), min(lats), max(lons), max(lats)]


_PLANT_ELEVATION_OFFSET_M: float = 0.0


def _plant_features(grid: Grid, layout_name: str,
                     cfg: DistrictConfig) -> List[Dict[str, object]]:
    """Emit one GeoJSON feature per placed Stage C plant.

    Reads ``grid.plant_placements`` (populated by
    ``layout.plant_siting.place_stage_c_plants``). Each plant draws as a
    ~80 m square footprint at the centre of its host cell with role
    ``"plant"`` and ``plant_kind`` ∈ {biomass_chp, biogas, wte}. Returns
    an empty list when no placements are present.
    """
    placements = getattr(grid, "plant_placements", {}) or {}
    if not placements:
        return []
    out: List[Dict[str, object]] = []
    # viewer-visibility fix: plant markers were occluded by
    # the host LIGHT_INDUSTRY cell's industry_shed structure (12 m roof,
    # ~80 % cell footprint). Markers are now substantially taller than
    # any typical building (so the top pokes above) AND their footprint
    # is offset to a corner of the cell so they aren't perfectly inside
    # the industry_shed. Heights map to the real visual signature of
    # each plant: short stack for biogas digester (~25 m), tall stack
    # for WTE incinerator (~70 m), medium for biomass CHP (~50 m).
    rect = (0.05, 0.05, 0.45, 0.45)   # ~80 m square offset to NE quadrant of cell
    kind_colours = {
        "biomass_chp": "#E97A3C",   # orange (matches cockpit Live tab)
        "biogas":      "#84CC16",   # yellow-green
        "wte":         "#C0392B",   # dark red
    }
    kind_heights = {
        "biomass_chp": 50.0,   # boiler house + short stack
        "biogas":      25.0,   # digester + flare
        "wte":         70.0,   # tall stack signature
    }
    for kind, p in placements.items():
        cell = grid.at(p.row, p.col)
        props = {
            "feature_id": f"{layout_name}_plant_{kind}_{cell.row:02d}_{cell.col:02d}",
            "layout": layout_name,
            "row": cell.row,
            "col": cell.col,
            "cell_id": f"{cell.row:02d}_{cell.col:02d}",
            "role": "plant",
            "plant_kind": kind,
            "host_land_use": p.host_land_use,
            "min_residential_distance_cells": p.min_residential_distance_cells,
            "min_school_distance_cells": p.min_school_distance_cells,
            "siting_reason": p.reason,
            "colour": kind_colours.get(kind, "#999999"),
            "colour_rgb": _hex_to_rgb(kind_colours.get(kind, "#999999")),
            "height_m": kind_heights.get(kind, 12.0),
            "base_elevation_m": _PLANT_ELEVATION_OFFSET_M,
            "is_built": False,  # marker, not residential / commercial
        }
        out.append(_feature(grid, cell, rect, cfg, props))
    return out


def _solar_thermal_context(cfg: DistrictConfig):
    """(aggregate_m2, eligible_categories, module_efficiency) or None.

    Returns None whenever solar thermal is off, absent from the dispatch
    results, or the module efficiency is unusable - in which case the
    exporter ships 0.0 and the viewer draws nothing, which is the correct
    behaviour for a BAU or a pre-solar-thermal run.
    """
    try:
        from energy.costs import load_economics
        econ = load_economics()
        if not econ.solar_thermal_enabled():
            return None
        eligible = set(econ._solar_thermal().get("eligible_categories") or [])
        if not eligible:
            return None
        eff = float(getattr(cfg, "rooftop_module_efficiency", 0.1930))
        if eff <= 0:
            return None
        dispatch_path = (Path(__file__).resolve().parent.parent
                          / "outputs" / "data" / "energy"
                          / "dispatch_results.json")
        if not dispatch_path.exists():
            return None
        import json as _json
        with dispatch_path.open() as f:
            payload = _json.load(f)
        for scen in payload.get("scenarios", []):
            if (scen.get("name") == "full_stack"
                    and abs(scen.get("alpha", -1)) < 1e-6):
                total = float(scen.get("capacities", {})
                                  .get("solar_thermal_m2", 0.0))
                return (total, eligible, eff) if total > 0 else None
        return None
    except Exception:
        return None


def _cell_category_name(cell: Cell, cfg: DistrictConfig) -> str:
    """The economics category string for a cell, or '' if it has none.

    *** USE `category_for`, NOT `land_use.value`. *** They disagree, and the
    disagreement is silent and total for housing: economics calls the tiers
    `low_income_residential` / `mid_` / `high_`, while `LandUse.value` gives
    `residential_low` / `_mid` / `_high`. A first cut of this function
    returned `land_use.value` and would have excluded EVERY home from
    collector eligibility - the bulk of the district's hot-water demand -
    while still looking like it worked, because schools, healthcare, public
    services, hotels and restaurants do match by name.

    `energy/network.py` builds `EnergyNode.category_name` as
    `category_for(cell.land_use).name`, and the LP's roof cap tests
    eligibility against exactly that, so this mirrors it.
    """
    try:
        from core.land_use import category_for
        cat = category_for(cell.land_use)
        return str(cat.name) if cat is not None else ""
    except Exception:
        return ""


def _allocate_roof_jointly(grid: Grid,
                            shading_lookup: Dict[Tuple[int, int], float],
                            cfg: DistrictConfig,
                            norms: Optional[DemandNorms],
                            layout_name: str,
                            ) -> Tuple[Dict[Tuple[int, int], float],
                                       Dict[Tuple[int, int], float]]:
    """Allocate rooftop PV **and** solar-thermal collectors to roofs together.

    Returns ``(pv_kwp_by_cell, solar_thermal_m2_by_cell)``.

    WHY JOINTLY, AND WHY THIS ORDER. The LP already forbids the two from
    sharing a square metre::

        rooftop_installed[p] / eff + st_installed[p] <= st_roof_m2

    but it enforces that on DISTRICT TOTALS. Allocating the two aggregates to
    roofs independently would satisfy the district sum and still put a full
    panel array and a collector on the same roof, which is exactly the overlap
    the constraint exists to prevent. So both are placed against one shared
    per-cell roof budget.

    **Collectors are placed first, and that is a deliberate choice, not an
    accident of ordering.** A collector may only sit on one of eight eligible
    categories (the residential tiers, school, healthcare, public services,
    hotel, restaurant) because those are the buildings that draw hot water,
    and the LP's own roof cap is built from that same list. Panels may sit
    anywhere. Giving the constrained technology first refusal is the only
    ordering that can place both aggregates; the reverse can strand collectors
    with nowhere legal to go while panels sit on ineligible roofs that the
    collector was never allowed to use.

    **This is a VISUALISATION convention, not an LP result.** The LP chose two
    quantities, not a map. Any statement about *which* roof carries a collector
    is this function's assumption and must be described that way.
    """
    if layout_name != OPTIMISED_LAYOUT:
        return {}, {}

    st_ctx = _solar_thermal_context(cfg)
    pv_total = _lp_rooftop_pv_kwp()
    if pv_total <= 0 and st_ctx is None:
        return {}, {}

    eff = st_ctx[2] if st_ctx else float(
        getattr(cfg, "rooftop_module_efficiency", 0.1930))

    # One roof budget per cell, in m2, on exactly the basis the LP uses:
    # the deployable kWp ceiling inverted through the module efficiency.
    roof_m2: Dict[Tuple[int, int], float] = {}
    shade: Dict[Tuple[int, int], float] = {}
    category: Dict[Tuple[int, int], str] = {}
    for cell in grid.all_cells():
        if cell.land_use == LandUse.SOLAR_FARM:
            continue                      # has its own LP capacity variable
        ceiling_kwp = _deployable_pv_kwp_for(cell, cfg, norms)
        if ceiling_kwp <= 0:
            continue
        key = (cell.row, cell.col)
        roof_m2[key] = ceiling_kwp / eff
        shade[key] = shading_lookup.get(key, 1.0)
        category[key] = _cell_category_name(cell, cfg)

    st_out: Dict[Tuple[int, int], float] = {}
    if st_ctx is not None:
        st_total, eligible, _ = st_ctx
        cand = [k for k in roof_m2 if category.get(k) in eligible]
        # Best-lit eligible roof first, same yield logic A17 uses for panels.
        cand.sort(key=lambda k: -(roof_m2[k] * shade[k]))
        remaining = st_total
        for key in cand:
            if remaining <= 0:
                break
            take = min(remaining, roof_m2[key])
            if take > 0:
                st_out[key] = take
                remaining -= take
        if remaining > 1.0:
            # Not fatal - the viewer still draws what fits - but it means the
            # eligible roof in the LAYOUT is smaller than the one the LP
            # costed, which is a real inconsistency worth seeing.
            print(f"  [export_3d] WARNING: {remaining:,.0f} m2 of collector "
                  f"could not be placed on eligible roof "
                  f"({st_total:,.0f} m2 requested)")

    pv_out: Dict[Tuple[int, int], float] = {}
    if pv_total > 0:
        # Panels take what the collectors left, converted back to kWp.
        free_kwp = {k: max(0.0, (roof_m2[k] - st_out.get(k, 0.0))) * eff
                    for k in roof_m2}
        order = sorted(free_kwp, key=lambda k: -(free_kwp[k] * shade[k]))
        remaining = pv_total
        for key in order:
            if remaining <= 0:
                pv_out[key] = 0.0
                continue
            take = min(remaining, free_kwp[key])
            pv_out[key] = take
            remaining -= take
        if remaining > 1.0:
            print(f"  [export_3d] WARNING: {remaining:,.0f} kWp of rooftop PV "
                  f"could not be placed after collectors took their share")
    return pv_out, st_out


def _lp_rooftop_pv_kwp() -> float:
    """The LP's aggregate rooftop PV for full_stack at alpha=0, or 0.0."""
    try:
        dispatch_path = (Path(__file__).resolve().parent.parent
                          / "outputs" / "data" / "energy"
                          / "dispatch_results.json")
        if not dispatch_path.exists():
            return 0.0
        import json as _json
        with dispatch_path.open() as f:
            payload = _json.load(f)
        for scen in payload.get("scenarios", []):
            if (scen.get("name") == "full_stack"
                    and abs(scen.get("alpha", -1)) < 1e-6):
                return float(scen.get("capacities", {})
                                 .get("rooftop_pv_kwp", 0.0))
    except Exception:
        pass
    return 0.0


def _compute_deployed_pv_lookup(grid: Grid,
                                  shading_lookup: Dict[Tuple[int, int], float],
                                  cfg: DistrictConfig,
                                  norms: Optional[DemandNorms],
                                  layout_name: str
                                  ) -> Dict[Tuple[int, int], float]:
    """A17 -- distribute the LP's aggregate `rooftop_pv_kwp` across cells.

    Reads ``outputs/data/energy/dispatch_results.json`` if present and
    finds the deployed rooftop_pv_kwp for the `full_stack` scenario at
    alpha=0. Allocates this aggregate across PV-bearing cells greedy
    by descending (cell_ceiling x shading_multiplier): the LP would
    pick the highest-yield cells first within a uniform per-kWp CAPEX.
    Returns empty dict if dispatch results aren't on disk yet -- the
    field then ships as 0.0 in the GeoJSON.
    """
    if layout_name != OPTIMISED_LAYOUT:
        # Baselines don't have an LP-driven deployment; just zero.
        return {}
    try:
        dispatch_path = (Path(__file__).resolve().parent.parent
                          / "outputs" / "data" / "energy"
                          / "dispatch_results.json")
        if not dispatch_path.exists():
            return {}
        import json as _json
        with dispatch_path.open() as f:
            payload = _json.load(f)
        deployed_kwp = 0.0
        for scen in payload.get("scenarios", []):
            if (scen.get("name") == "full_stack"
                    and abs(scen.get("alpha", -1)) < 1e-6):
                deployed_kwp = float(scen.get("capacities", {})
                                       .get("rooftop_pv_kwp", 0.0))
                break
        if deployed_kwp <= 0:
            return {}
        # Per-cell ceiling x shading scores; sort descending.
        # (A17 fix): exclude SOLAR_FARM cells -- they have
        # their own LP capacity variable (`solar_farm_kwp`) and the
        # aggregate we're allocating is ROOFTOP only.
        scored: List[Tuple[Tuple[int, int], float, float]] = []
        for cell in grid.all_cells():
            if cell.land_use == LandUse.SOLAR_FARM:
                continue
            ceiling = _deployable_pv_kwp_for(cell, cfg, norms)
            if ceiling <= 0:
                continue
            shade = shading_lookup.get((cell.row, cell.col), 1.0)
            scored.append(((cell.row, cell.col), ceiling, shade))
        scored.sort(key=lambda t: -t[1] * t[2])
        out: Dict[Tuple[int, int], float] = {}
        remaining = deployed_kwp
        for key, ceiling, _shade in scored:
            if remaining <= 0:
                out[key] = 0.0
                continue
            allocated = min(remaining, ceiling)
            out[key] = allocated
            remaining -= allocated
        return out
    except Exception:
        return {}


def _compute_shading_lookup(grid: Grid, cfg: DistrictConfig) -> Dict[Tuple[int, int], float]:
    """Return ``{(row, col): pv_yield_multiplier in [0, 1]}`` for PV-bearing cells.

    Wraps ``energy.solar_geometry.compute_geometric_shading`` with a fresh
    Economics object so the viewer GeoJSON ships the physics-based
    multiplier rather than relying on a client-side heuristic. Returns an
    empty dict on any failure (legacy / tiny test grids).
    """
    try:
        # Local imports avoid a circular import via energy/network.py.
        from energy.costs import load_economics
        #: the cached wrapper, not the raw rasteriser -
        # same key discipline as energy/network.py (grid geometry + sun
        # samples + site + raster_res + solar_geometry.py sha256; any change
        # auto-misses). test_export_3d alone paid this uncached 341 min per
        # suite. Bit-exactness proven in shading_cache_proof.py.
        from energy.shading_cache import compute_cached as compute_geometric_shading
        econ = load_economics()
        site = getattr(cfg, "site", {}) or {}
        lat = float(site.get("latitude", 30.64))
        lon = float(site.get("longitude", 76.82))
        return compute_geometric_shading(grid, econ, lat, lon)
    except Exception:
        return {}


# (Part 4 / night-scene viewer): per-cell NIGHT-LIGHTING profile so
# the viewer can make buildings "glow" following a time-of-day slider. For each
# built cell we ship its WEEKDAY base-demand (occupancy) fractions by 2-h daypart
# — the same Tier-2 BESCOM-cited `base_demand_profile` the dispatch uses. The
# fraction (0..1) at the slider's daypart IS the building's relative brightness:
# homes peak in the evening (18-22), offices/schools in the daytime, religious at
# dawn+dusk. Streetlights are handled separately via `streetlight_type` + the
# dusk-dawn `street_lighting.daypart_shape` (lamps on ~18:00-06:00). This is a
# RENDER-DATA export only — it does NOT change any energy number.
def _compute_lighting_lookup(grid: Grid) -> Dict[Tuple[int, int], list]:
    """Return ``{(row, col): [12 weekday occupancy fractions, daypart-ordered]}``
    for built cells. Empty dict on any failure (tiny/legacy grids)."""
    try:
        from energy.costs import load_economics, DAYPARTS
        from core.land_use import category_for
        econ = load_economics()
        profiles = getattr(econ, "base_demand_profile", {}) or {}
        out: Dict[Tuple[int, int], list] = {}
        for cell in grid.all_cells():
            if not cell.land_use.has_buildings:
                continue
            cat = category_for(cell.land_use)
            cat_name = getattr(cat, "name", None)
            prof = profiles.get(cat_name, {}) if cat_name else {}
            wd = prof.get("weekday", {}) or {}
            if not wd:
                continue
            out[(cell.row, cell.col)] = [
                round(float(wd.get(dp, 0.0)), 3) for dp in DAYPARTS
            ]
        return out
    except Exception:
        return {}


#: per-PV-cell diagnostics so the viewer can
# explain why a cell is on the red end of the shading ramp.
# (1) `pv_shading_percentile` ranks the cell against the layout's actual
#     `pv_shading_multiplier_geom` distribution -- 0.0 = most shaded in
#     this layout, 1.0 = least shaded. This is the same percentile the
#     viewer's dynamic ramp uses, so red cells have low percentile and
#     unshaded cells have percentile 1.0.
# (2) `pv_shading_offender_dirs` lists the 8-neighbour cardinal directions
#     with at least one cell whose roof height exceeds the target's
#     rooftop level by `>= SHADING_OFFENDER_HEIGHT_THRESHOLD_M`. This is
#     a cheap geometric scan (NOT the full sun-path integration that
#     drives the multiplier) so it answers "who's tall around me?" rather
#     than "what's the integrated shaded fraction?". Combined with the
#     multiplier, this lets the viewer say "shaded by 2 tall S/SW
#     neighbours (~4 % annual yield loss)".
# (3) `pv_shading_reason` is a short human string for the tooltip and
#     selected-cell panel.
#: single source of truth, core/shading_constants.py
# The old comment here said "matches energy/solar_geometry constant" - a
# comment ASSERTING a match rather than enforcing one, which is how five
# copies of this number were free to drift.
from core.shading_constants import (
    PV_SHADING_DELTA_M, GROUND_PV_PANEL_TOP_M,
)

SHADING_OFFENDER_HEIGHT_THRESHOLD_M = PV_SHADING_DELTA_M
_CARDINAL_OFFSETS: Tuple[Tuple[int, int, str], ...] = (
    (-1, 0, "N"), (-1, 1, "NE"), (0, 1, "E"), (1, 1, "SE"),
    (1, 0, "S"), (1, -1, "SW"), (0, -1, "W"), (-1, -1, "NW"),
)


def _is_pv_bearing(cell: Cell) -> bool:
    return cell.has_building or cell.land_use == LandUse.SOLAR_FARM


def _offender_dirs(grid: Grid, cell: Cell) -> List[str]:
    """Return cardinal directions with at least one tall caster neighbour.

    "Tall" means `height_m >= target_z + SHADING_OFFENDER_HEIGHT_THRESHOLD_M`,
    where `target_z` is the cell's rooftop level (or 1.5 m for SOLAR_FARM
    racks). 6 m threshold matches the historical `_pv_shading_multiplier`
    heuristic from energy/network.py.
    """
    target_z = cell.height_m if cell.has_building else GROUND_PV_PANEL_TOP_M
    out: List[str] = []
    for dr, dc, label in _CARDINAL_OFFSETS:
        r, c = cell.row + dr, cell.col + dc
        if not (0 <= r < grid.n_rows and 0 <= c < grid.n_cols):
            continue
        nb = grid.at(r, c)
        if nb.height_m >= target_z + SHADING_OFFENDER_HEIGHT_THRESHOLD_M:
            out.append(label)
    return out


def _compute_shading_diagnostics(
    grid: Grid,
    shading_lookup: Dict[Tuple[int, int], float],
) -> Dict[Tuple[int, int], Dict[str, object]]:
    """Return ``{(row, col): {percentile, offender_dirs, reason}}``.

    Empty when no PV-bearing cells are present (legacy / tiny test grids).
    Percentile ranks the cell within the layout's actual multiplier
    distribution skipping the >= 0.999 unshaded tail (same convention the
    viewer uses for the dynamic ramp).
    """
    out: Dict[Tuple[int, int], Dict[str, object]] = {}
    if not shading_lookup:
        return out
    # Distribution rank (matches viewer dynamic-ramp convention).
    pv_cells_with_mults = [
        (key, mult) for key, mult in shading_lookup.items()
        if grid.at(*key) is not None and _is_pv_bearing(grid.at(*key))
    ]
    if not pv_cells_with_mults:
        return out
    # Sort ascending so rank-0 = most shaded.
    pv_cells_with_mults.sort(key=lambda kv: kv[1])
    n = len(pv_cells_with_mults)
    # Build percentile: tie-aware via average rank.
    sorted_values = [v for _, v in pv_cells_with_mults]
    for key, mult in pv_cells_with_mults:
        # Average-rank percentile so ties don't artificially split.
        # Find indices where value matches; midpoint is the rank.
        # Linear scan is fine for ~400 cells.
        first = next(i for i, v in enumerate(sorted_values) if v >= mult)
        last = n - 1 - next(
            i for i, v in enumerate(reversed(sorted_values)) if v <= mult
        )
        rank = (first + last) / 2.0
        percentile = rank / (n - 1) if n > 1 else 1.0
        cell = grid.at(*key)
        offender_dirs = _offender_dirs(grid, cell)
        out[key] = {
            "percentile": round(float(percentile), 3),
            "offender_dirs": offender_dirs,
            "reason": _build_shading_reason(mult, percentile, offender_dirs),
        }
    return out


def _build_shading_reason(mult: float, percentile: float,
                          offender_dirs: Sequence[str]) -> str:
    """Build a short human-readable shading reason string.

    The viewer reads this directly into the tooltip / selected-cell panel.
    Format aims to disambiguate "red on the dynamic ramp" (most shaded in
    THIS layout) from "severe physical loss" (multiplier far below 1).
    """
    drop_pct = (1.0 - float(mult)) * 100.0
    pct_int = max(0, int(round(percentile * 100)))
    if not offender_dirs:
        if drop_pct < 0.5:
            return (
                f"Unshaded ({drop_pct:.1f}% annual yield loss; "
                f"percentile {pct_int}/100 in this layout)"
            )
        return (
            f"Mild self/atmospheric shading ({drop_pct:.1f}% loss; "
            f"percentile {pct_int}/100)"
        )
    dirs_text = "/".join(offender_dirs)
    n_off = len(offender_dirs)
    if drop_pct < 2.0:
        severity = "Light"
    elif drop_pct < 6.0:
        severity = "Moderate"
    else:
        severity = "Heavy"
    return (
        f"{severity} shading from {n_off} tall {dirs_text} neighbour"
        f"{'s' if n_off > 1 else ''}; "
        f"{drop_pct:.1f}% annual yield loss "
        f"(percentile {pct_int}/100 in this layout)"
    )


def _street_edge_features(grid: Grid, layout_name: str,
                          cfg: DistrictConfig) -> List[Dict[str, object]]:
    """STAGE-/ street/path segments as LineString features.

    One feature per StreetEdge: a centerline from cell-centre a to
    cell-centre b in WGS84, with kind ("local_street" / "greenway_path"),
    ROW width and mode flags. role="street_edge" keeps them distinct from
    parcel features so `grid_from_geojson` cell loading skips them.
    """
    if not grid.street_edges:
        return []
    district_w = grid.n_cols * grid.cell_size_m
    district_h = grid.n_rows * grid.cell_size_m

    def _centre_lonlat(cell_id) -> List[float]:
        r, c = cell_id
        cell = grid.at(r, c)
        return _metres_to_lonlat(cell.centre_x_m - district_w / 2.0,
                                 cell.centre_y_m - district_h / 2.0, cfg)

    out: List[Dict[str, object]] = []
    for i, e in enumerate(grid.street_edges):
        out.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [_centre_lonlat(e.a), _centre_lonlat(e.b)],
            },
            "properties": {
                "role": "street_edge",
                "layout": layout_name,
                "edge_id": i,
                "kind": e.kind,
                "width_m": e.width_m,
                "modes": list(e.modes),
                "cell_a": list(e.a),
                "cell_b": list(e.b),
            },
        })
    return out


def grid_to_geojson(grid: Grid, layout_name: str,
                    cfg: Optional[DistrictConfig] = None,
                    norms: Optional[DemandNorms] = None,
                    ) -> Dict[str, object]:
    """Convert a populated ``Grid`` to a 3D-ready GeoJSON FeatureCollection.

    Returns
    -------
    Dict[str, object]
        GeoJSON FeatureCollection with metadata and exported features.
    """
    cfg = cfg or load_config()
    norms = norms or load_demand_norms()
    #: make sure deployable floating-PV
    # sites are tagged before we read the cell flags into the GeoJSON.
    # `_grid_for_layout` already calls this for grids it builds, but
    # callers that load a grid via `energy.network.grid_from_geojson`
    # and then re-export skip that path. Idempotent: only re-runs when
    # no cluster IDs are present.
    from layout.floating_pv_siting import assign_floating_pv_sites
    if not any(
        c.floating_pv_cluster_id is not None for c in grid.all_cells()
    ):
        assign_floating_pv_sites(
            grid, min_cluster_size=_floating_pv_min_cluster_size(),
        )
    # v2: precompute the geometric PV-shading multiplier per
    # PV-bearing cell so it ships in the GeoJSON. The viewer reads it
    # instead of recomputing a step-function heuristic client-side.
    shading_lookup = _compute_shading_lookup(grid, cfg)
    #: derive per-cell percentile + neighbour-offender
    # directions + short reason string from the multiplier lookup. The
    # viewer reads these directly so it can explain "why is this cell red?".
    shading_diagnostics = _compute_shading_diagnostics(grid, shading_lookup)
    #: rooftop PV and solar-thermal collectors are now
    # allocated TOGETHER against one shared per-cell roof budget, so a roof
    # can never show both covering the same square metre. The LP already
    # forbids that district-wide (`st_roof_share` in energy/dispatch.py);
    # allocating the two aggregates independently would have satisfied the
    # district sum and still drawn them on top of each other. Falls back to
    # the A17 PV-only path when solar thermal is off or absent.
    deployed_lookup, solar_thermal_lookup = _allocate_roof_jointly(
        grid, shading_lookup, cfg, norms, layout_name,
    )
    if not deployed_lookup:
        deployed_lookup = _compute_deployed_pv_lookup(
            grid, shading_lookup, cfg, norms, layout_name,
        )
    # (Part 4 / night-scene): per-cell weekday occupancy-by-daypart
    # so the viewer can glow buildings on a time-of-day slider (render-only).
    lighting_lookup = _compute_lighting_lookup(grid)
    features: List[Dict[str, object]] = []
    for cell in grid.all_cells():
        features.append(_parcel_feature(
            grid, cell, layout_name, cfg, norms,
            shading_lookup=shading_lookup,
            deployed_lookup=deployed_lookup,
            solar_thermal_lookup=solar_thermal_lookup,
            shading_diagnostics=shading_diagnostics,
            lighting_lookup=lighting_lookup,
        ))
        features.extend(_structure_features(
            grid, cell, layout_name, cfg, norms,
            shading_lookup=shading_lookup,
            deployed_lookup=deployed_lookup,
            shading_diagnostics=shading_diagnostics,
        ))
    #: Stage C plant markers (biomass CHP, biogas,
    # WTE). Spatial representation only -- the dispatch MILP remains
    # single-bus. Each placement renders as a small square footprint at
    # the centre of its host cell so the viewer can draw it.
    plant_features = _plant_features(grid, layout_name, cfg)
    features.extend(plant_features)
    # STAGE-/: sub-cell street/path segments as LineString
    # features (role "street_edge") - local access lanes + greenway paths.
    # Centerline geometry: cell centre to cell centre (see core.grid.
    # StreetEdge). The viewer draws lanes at width_m; the energy model
    # ignores them (no electrons).
    features.extend(_street_edge_features(grid, layout_name, cfg))

    land_use_counts = {
        lu.value: n for lu, n in sorted(
            grid.land_use_counts().items(), key=lambda item: item[0].value
        )
    }
    site_lon = float(cfg.site.get("longitude", 0.0))
    return {
        "type": "FeatureCollection",
        "name": layout_name,
        "metadata": {
            "layout": layout_name,
            "source": "district_v3 Python Grid",
            "site_name": cfg.site.get("name"),
            "center": {
                "latitude": float(cfg.site.get("latitude", 0.0)),
                "longitude": site_lon,
            },
            "solar_time": {
                # Date/time sliders in viewer3d are interpreted as
                # site-local solar time (apparent solar time at the site's
                # own meridian), not UTC and not the country's civil
                # standard time. To convert from civil clock time, an
                # external client would also need the equation of time
                # and the offset between site longitude and standard
                "convention": "site_local_solar",
                "standard_meridian_deg": site_lon,
            },
            "grid": {
                "rows": grid.n_rows,
                "cols": grid.n_cols,
                "cell_size_m": grid.cell_size_m,
                "area_km2": grid.total_area_m2 / 1e6,
            },
            "bounds": _bounds(features),
            "land_use_counts": land_use_counts,
            "feature_count": len(features),
            # STAGE-/: honest ROW-area road accounting
            # (register B6 - road is REPORTED in ROW area, decided ~20% of
            # developed) + the walkability composite over the street/path
            # edge network. Both are derived from the same grid object.
            "road_network": _road_network_metadata(grid, cfg),
            "walkability": _walkability_metadata(grid),
        },
        "features": features,
    }


def _road_network_metadata(grid: Grid, cfg: DistrictConfig) -> Dict[str, object]:
    from layout.road_network import road_row_report, tag_road_classes
    # tag idempotently so exports of loaded grids carry classes too
    counts = tag_road_classes(grid, cfg)
    rep = road_row_report(grid, cfg)
    rep["cells_by_class"] = counts
    #.11/.12,: per-class street
    # CROSS-SECTION so the viewer renders the carriageway as a centered
    # strip (not a 100 m slab) with foot+cycle paths on BOTH edges
    # (IRC:103-2012 pedestrian facilities + IRC:86 lane widths, Tier 1),
    # and furniture MULTIPLIERS so one rendered glyph is labelled as the
    # N real poles/trees a 100 m cell carries (IS:1944/SP:73 pole spacing
    # ~30 m staggered, Tier 2; MoHUA avenue-tree spacing ~10 m, Tier 2).
    # Energy already accounts for the full pole count (streetlight load is
    # per-capita-derived); this is presentation metadata only.
    # RE-ANCHORED to the adopted plan's own hierarchy (Revised
    # Master Plan Zirakpur p63: R2 50 m / R4 25 m / R5 20 m; Table 7-1
    # note ii 40-ft lanes) - see layout/road_network.py ROAD_CLASS_SPEC.
    # SEPARATE cycle track + footpath on every class;
    # each row sums exactly to row_total.
    rep["cross_section_m"] = {
        "arterial": {"row_total": 50.0, "carriageway": 18.0,
                     "median": 4.0, "cycle_each_side": 3.0,
                     "footpath_each_side": 2.5, "verge_each_side": 8.5},
        "collector": {"row_total": 25.0, "carriageway": 11.0,
                      "median": 0.0, "cycle_each_side": 2.5,
                      "footpath_each_side": 2.5, "verge_each_side": 2.0},
        "local": {"row_total": 20.0, "carriageway": 7.0,
                  "median": 0.0, "cycle_each_side": 2.25,
                  "footpath_each_side": 2.0, "verge_each_side": 2.25},
    }
    rep["furniture_per_road_cell"] = {
        "arterial": {"streetlight_poles": 7, "avenue_trees": 20},
        "collector": {"streetlight_poles": 5, "avenue_trees": 16},
        "local": {"streetlight_poles": 3, "avenue_trees": 10},
    }
    return rep


def _walkability_metadata(grid: Grid) -> Dict[str, float]:
    from layout.path_network import walkability_report
    return walkability_report(grid)


def _grid_for_layout(layout_name: str, cfg: DistrictConfig) -> Grid:
    """Generate a grid for a named exportable layout."""
    # (Item 2): tag RELIGIOUS cells with a faith for the
    # exporter so the GeoJSON carries the per-cell tag. Deterministic
    # (Punjab Census-2011 shares, sorted (row,col) walk; see
    # layout.faith_assignment for the algorithm).
    # (Item 3): place discrete carport sites near anchors,
    # balanced across quadrants. Both helpers are deterministic and
    # mutate the grid in place.
    from layout.faith_assignment import assign_faiths_to_religious_cells
    from layout.entrance_assignment import assign_entrances
    from layout.floating_pv_siting import assign_floating_pv_sites
    from layout.locked_zones import apply_locked_zones
    from layout.carport_siting import place_carports
    from layout.street_furniture import place_street_furniture
    from layout.amenity_subtype import assign_amenity_subtypes
    from layout.spine_gradient import apply_spine_gradient
    # carports re-enabled, now sited on dedicated PARKING_LOT cells
    # (place_carports tags every PARKING_LOT cell; see carport_siting.py). Street
    # furniture (avenue trees + solar/grid streetlights) tagged on ROAD cells.
    # School/health hover sub-types tagged from the URDPFI/IPHS facility mix.
    if layout_name in ARCHETYPES:
        g = generate(layout_name)
        assign_faiths_to_religious_cells(g)
        assign_entrances(g)
        assign_floating_pv_sites(g, min_cluster_size=_floating_pv_min_cluster_size())
        place_carports(g)
        place_street_furniture(g)
        assign_amenity_subtypes(g, derive_requirements(
            load_demographics(), load_demand_norms(), cfg))
        return g
    if layout_name == OPTIMISED_LAYOUT:
        seed_name = cfg.optimisation.get("initial_seed_archetype", "chandigarh_sector")
        demo = load_demographics()
        norms = load_demand_norms()
        requirements = derive_requirements(demo, norms, cfg)
        #: reserve + LOCK the arterial road skeleton and a
        # clean rectangular solar zone BEFORE annealing. The SA then arranges
        # all other land use around them (every move skips locked cells), so
        # roads can never be severed by an amenity and the solar field stays a
        # clean block with no buildings inside it.
        seed_grid = generate(seed_name)
        solar_req = int(requirements.required_cells_by_landuse.get(
            LandUse.SOLAR_FARM, 25))
        apply_locked_zones(seed_grid, solar_cells=solar_req)
        # STAGE-: lock the Chandigarh sector
        # COLLECTOR grid before the anneal (sector size = the config-pinned
        # sweep winner) so the SA arranges land use WITHIN sectors, then
        # the northern canal corridor (Q23 - culverts under road crossings,
        # canal-top PV ceiling prices via the floating-PV machinery).
        from layout.canal_corridor import apply_canal_corridor
        from layout.road_network import configured_sector_size
        from layout.sector_structure import apply_sector_grid
        apply_sector_grid(
            seed_grid, sector_size_cells=configured_sector_size(cfg))
        apply_canal_corridor(seed_grid, cfg)
        # STAGE-B18.4: the LOCKED Chandigarh green structure -
        # 3 x 12-ha community parks + the linear greenway spine (Leisure
        # Valley pattern) are PLANNED, not emergent; the SA arranges the
        # town around them like roads/farm/canal.
        from layout.park_structure import apply_locked_parks
        apply_locked_parks(seed_grid, cfg)
        # layout/f6_locks.py, tests/test_f6_locks.py): highstreet CHAIN on
        # the spine (the FULL requirements-derived count so no singleton
        # floaters remain - his 4-chain expectation), hospital 2x2 CAMPUS
        # fronting an arterial, the +50/+50 solar ring BRIDGED-contiguous
        # at the farm fence (impossible post-anneal - patch-A diagnostic),
        # and the agri perimeter band. Runs LAST in the lock sequence
        # (locks compose; never overwrites earlier locks).
        from core.land_use import LandUse as _LU
        from layout.f6_locks import apply_f6_locks
        _hs_req = int(requirements.required_cells_by_landuse.get(
            _LU.RETAIL_HIGHSTREET, 6))
        apply_f6_locks(seed_grid, highstreet_cells=max(_hs_req, 4))
        # verbose=True: a multi-hour anneal must stream
        # progress (house rule - "add progress prints to long solves");
        # one line per 200 moves, ~2.5 min apart at 100 m scale.
        best_grid, _ = anneal(
            seed_grid,
            requirements,
            cfg,
            verbose=True,
        )
        # STAGE-: requirements trim FIRST (demand-derived
        # counts are enforced by construction - the SA decides WHERE, the
        # URDPFI/IPHS norms decide HOW MANY; kills SA-grown commercial
        # over-supply + non-arterial road fragments, see
        # layout/requirements_trim.py), THEN the floor-conserving Bertaud
        # housing on arterial-adjacent low/mid cells, SHORT edge
        # compensation) - both BEFORE the export passes so heights,
        # shading and rooftop areas all see the final built form.
        from layout.requirements_trim import apply_requirements_trim
        apply_requirements_trim(best_grid, requirements, cfg)
        apply_spine_gradient(best_grid, cfg)
        #.2: rebalance the spine barbell to a TRUE
        # three-tier mix inside every residential class (floor-conserving;
        # Bertaud ordering survives) + kothi 9/12/15 m visual variants.
        from layout.height_variety import apply_height_variety
        apply_height_variety(best_grid, cfg)
        assign_faiths_to_religious_cells(best_grid)
        assign_entrances(best_grid)
        assign_floating_pv_sites(best_grid, min_cluster_size=_floating_pv_min_cluster_size())
        place_carports(best_grid)
        place_street_furniture(best_grid)
        assign_amenity_subtypes(best_grid, requirements)
        # STAGE-: campus grounds - ring big facility UNITS
        # (mall/UCHC/secondary/warehouse) with grounds cells claimed from open
        # space (tagged campus_grounds; land_use unchanged -> demand-invariant).
        # AFTER amenity_subtypes (needs secondary/UCHC sub-types), BEFORE the
        # open-space tagger (so grounds are claimed before parks are tagged).
        from layout.building_footprints import apply_campus_grounds
        apply_campus_grounds(best_grid, cfg)
        # STAGE- green structure: tag every
        # OPEN_SPACE cell with its structure subtype (parks / greenways /
        # phased reserves / belt). Skips campus_grounds cells (preserved).
        # The 350-cell solar reserve arrives via apply_locked_zones above.
        from layout.open_space_structure import tag_open_space_structure
        tag_open_space_structure(best_grid, cfg)
        # STAGE-/ road classes + the local access-lane
        # overlay. REORDER (, caught by the dress
        # rehearsal): lanes now come BEFORE the phased-expansion stamper -
        # the open-space tagger gives every road-fronting green to
        # `greenway`, so reserves/greenbelt live in sector INTERIORS and
        # the parking stamper's hard frontage filter starved (0/0 tags)
        # when it ran pre-lanes. Lanes only READ the built fabric, which
        # the tag-only passes below never change - order-safe.
        from layout.path_network import assign_path_network
        from layout.road_network import assign_local_streets, tag_road_classes
        tag_road_classes(best_grid, cfg)
        assign_local_streets(best_grid)
        # STAGE-B18: phased growth parcels - re-tag reserve
        # cells as solar_expansion_* (adjacent to the farm, per the phased
        # land grant;: pre-locked ring is kept via the skip-guard) and
        # parking_expansion_* (near the job-heavy cells, from the
        # demand-driven parking table, road/LANE frontage required).
        # Tags only; demand-safe.
        from layout.phased_expansion import apply_phased_expansion
        apply_phased_expansion(best_grid, requirements.parking_cells_by_period,
                               cfg)
        #.4: the agri/orchard belt is a CONTIGUOUS band on
        # the site edge (GMADA peri-urban form;: pre-locked band kept
        # via the skip-guard), stamped AFTER the growth parcels so it
        # never claims a solar/parking expansion cell.
        from layout.open_space_structure import apply_agri_perimeter_band
        apply_agri_perimeter_band(best_grid)
        # paths LAST (they read the final park/greenway/belt subtypes).
        assign_path_network(best_grid)
        return best_grid
    raise ValueError(
        f"Unknown layout {layout_name!r}. Choose from {sorted(ALL_LAYOUTS)}."
    )


def _layout_label(layout_name: str) -> str:
    """Human-readable layout label for the viewer manifest."""
    if layout_name == OPTIMISED_LAYOUT:
        return "Optimised SA"
    return layout_name.replace("_", " ").title()


def export_layouts(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    layout_names: Iterable[str] = DEFAULT_LAYOUTS,
    cfg: Optional[DistrictConfig] = None,
    svg_dir: Optional[Path] = DEFAULT_SVG_DIR,
) -> Dict[str, object]:
    """Generate and write GeoJSON (and a companion 2D SVG) for each layout.

    Writing both formats from the SAME grid object in the SAME process is
    what guarantees the 2D drawing and 3D viewer can never drift apart. If
    `svg_dir` is None, only the GeoJSON is written.

    Returns
    -------
    Dict[str, object]
        Viewer manifest describing exported layouts and bounds.
    """
    cfg = cfg or load_config()
    output_dir.mkdir(parents=True, exist_ok=True)
    if svg_dir is not None:
        svg_dir.mkdir(parents=True, exist_ok=True)

    manifest_layouts: List[Dict[str, object]] = []
    for layout_name in layout_names:
        print(f"generating {layout_name}...")
        grid = _grid_for_layout(layout_name, cfg)
        # 3D GeoJSON
        geojson = grid_to_geojson(grid, layout_name, cfg)
        path = output_dir / f"{layout_name}.geojson"
        path.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
        # 2D SVG companion - from the SAME grid object
        if svg_dir is not None:
            svg = to_svg(grid, title=layout_name.replace("_", " "))
            (svg_dir / f"{layout_name}.svg").write_text(svg, encoding="utf-8")
        metadata = geojson["metadata"]  # type: ignore[index]
        manifest_layouts.append({
            "name": layout_name,
            "label": _layout_label(layout_name),
            "path": f"{layout_name}.geojson",
            "svg_path": (str((svg_dir / f"{layout_name}.svg").relative_to(
                output_dir.parent)) if svg_dir is not None else None),
            "bounds": metadata["bounds"],  # type: ignore[index]
            "feature_count": metadata["feature_count"],  # type: ignore[index]
            "land_use_counts": metadata["land_use_counts"],  # type: ignore[index]
        })

    site_lon = float(cfg.site.get("longitude", 0.0))
    manifest: Dict[str, object] = {
        "type": "district_v3_3d_manifest",
        "source": "district_v3 Python Grid",
        "center": {
            "latitude": float(cfg.site.get("latitude", 0.0)),
            "longitude": site_lon,
        },
        # The viewer's sun-position sliders use site-local solar time, NOT
        # UTC and NOT civil standard time. standard_meridian_deg captures
        # the meridian against which solar time is measured; here it
        # equals site longitude, so the longitude correction is zero.
        "solar_time": {
            "convention": "site_local_solar",
            "standard_meridian_deg": site_lon,
        },
        "layouts": manifest_layouts,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Export district_v3 archetypes as 3D-ready GeoJSON."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for .geojson files and manifest.json.",
    )
    parser.add_argument(
        "--layouts",
        nargs="*",
        default=list(DEFAULT_LAYOUTS),
        choices=sorted(ALL_LAYOUTS),
        help="Archetype layouts to export.",
    )
    parser.add_argument(
        "--include-optimised",
        action="store_true",
        help="Also run simulated annealing and export optimised_sa.",
    )
    parser.add_argument(
        "--no-svg",
        action="store_true",
        help=("Skip writing the 2D SVG companions. By default the 2D SVG and "
              "3D GeoJSON are written from the same grid in lockstep so they "
              "can never drift apart."),
    )
    args = parser.parse_args(argv)

    layout_names = list(args.layouts)
    if args.include_optimised and OPTIMISED_LAYOUT not in layout_names:
        layout_names.append(OPTIMISED_LAYOUT)

    svg_dir = None if args.no_svg else DEFAULT_SVG_DIR
    manifest = export_layouts(Path(args.output_dir), layout_names, svg_dir=svg_dir)
    n = len(manifest["layouts"])  # type: ignore[arg-type]
    print(f"wrote {n} layouts to {args.output_dir}"
          + ("" if svg_dir is None else f" + 2D SVGs to {svg_dir}"))


if __name__ == "__main__":
    main()
