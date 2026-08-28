"""Surgical injection of floating-PV site tags + shading diagnostics
into existing GeoJSON.

the author asks:
- BLUE_SPACE cells should only host floating PV when they sit in a
  contiguous water-body cluster of size >=
  `floating_pv.site_selection.min_cluster_size` (default 2).
  See `layout.floating_pv_siting.assign_floating_pv_sites`.
- The viewer needs per-PV-cell shading diagnostics so it can EXPLAIN
  red cells: percentile within the layout, neighbour-offender
  directions, and a short human-readable reason string.

This script loads each `outputs/geojson3d/*.geojson`, reconstructs a
minimal Grid (parcel land-use + height), runs the deterministic
cluster-tagging algorithm, then writes the new properties onto every
parcel-and-structure feature for cells where the (row, col) matches.

For shading diagnostics, we reuse the geometric `pv_shading_multiplier_geom`
already on the parcel features (no recomputation -- that's the slow
sun-path integration). We compute the percentile from the on-disk
distribution and the offender directions from neighbour heights.

DOES NOT re-anneal optimised_sa. Idempotent. Run after a model change
that updates the floating-PV siting algorithm or the shading-diagnostic
helpers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from core.grid import Grid  # noqa: E402
from core.land_use import LandUse  # noqa: E402
from layout.floating_pv_siting import assign_floating_pv_sites  # noqa: E402


GEOJSON_DIR = HERE / "outputs" / "geojson3d"
#: both were local literals. Same values, now sourced from
# the one module that owns them so an edit there cannot leave this script
# silently disagreeing with the model it feeds.
from core.shading_constants import (  # noqa: E402
    PV_SHADING_DELTA_M, GROUND_PV_PANEL_TOP_M,
)

SHADING_OFFENDER_HEIGHT_THRESHOLD_M = PV_SHADING_DELTA_M   # 6.0
_CARDINAL_OFFSETS = (
    (-1, 0, "N"), (-1, 1, "NE"), (0, 1, "E"), (1, 1, "SE"),
    (1, 0, "S"), (1, -1, "SW"), (0, -1, "W"), (-1, -1, "NW"),
)


def _grid_from_geojson_for_siting(features: List[dict]) -> Grid:
    """Lightweight Grid reconstruction (land_use + height) for the helpers."""
    max_r = max_c = -1
    cell_size_m = 200.0
    for f in features:
        p = f.get("properties", {}) or {}
        if p.get("role") not in (None, "parcel"):
            continue
        r = p.get("row")
        c = p.get("col")
        if r is None or c is None:
            continue
        if int(r) > max_r:
            max_r = int(r)
        if int(c) > max_c:
            max_c = int(c)
    n_rows = max_r + 1
    n_cols = max_c + 1
    grid = Grid.empty(n_rows=n_rows, n_cols=n_cols, cell_size_m=cell_size_m)
    for f in features:
        p = f.get("properties", {}) or {}
        if p.get("role") not in (None, "parcel"):
            continue
        r = p.get("row")
        c = p.get("col")
        if r is None or c is None:
            continue
        try:
            grid.at(int(r), int(c)).land_use = LandUse(p.get("land_use"))
        except (ValueError, TypeError):
            continue
        h = p.get("cell_height_m")
        if h is not None:
            grid.at(int(r), int(c)).height_m = float(h)
    return grid


def _read_min_cluster_size() -> int:
    """Read `floating_pv.site_selection.min_cluster_size` from economics.yaml.

    Default 2 (cluster filter on). Setting to 1 in the YAML restores
    legacy "every BLUE_SPACE cell hosts" behaviour.
    """
    import yaml
    p = HERE / "config" / "economics.yaml"
    try:
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        block = (raw.get("floating_pv") or {}).get("site_selection") or {}
        return max(1, int(block.get("min_cluster_size", 2)))
    except Exception:
        return 2


def _read_per_cell_kwp() -> float:
    """Read `floating_pv.kwp_per_cell_default × default_uptake_fraction`."""
    import yaml
    p = HERE / "config" / "economics.yaml"
    try:
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        block = raw.get("floating_pv") or {}
        return (
            float(block.get("kwp_per_cell_default", 1500.0))
            * float(block.get("default_uptake_fraction", 0.30))
        )
    except Exception:
        return 1500.0 * 0.30


def _offender_dirs(grid: Grid, row: int, col: int, target_z: float) -> List[str]:
    """8-neighbour list of cardinal dirs with a tall caster (>= +6 m)."""
    out: List[str] = []
    for dr, dc, label in _CARDINAL_OFFSETS:
        r, c = row + dr, col + dc
        if not (0 <= r < grid.n_rows and 0 <= c < grid.n_cols):
            continue
        nb = grid.at(r, c)
        if nb.height_m >= target_z + SHADING_OFFENDER_HEIGHT_THRESHOLD_M:
            out.append(label)
    return out


def _build_reason(mult: float, percentile: float,
                    offender_dirs: Sequence[str]) -> str:
    """Short human-readable shading reason. Mirrors core/export_3d.py."""
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


def _compute_diagnostics(
    grid: Grid,
    features: List[dict],
) -> Dict[Tuple[int, int], Dict[str, object]]:
    """Build per-PV-cell diagnostics from the parcel features.

    Reads `pv_shading_multiplier_geom` from each parcel (no recomputation
    of the slow sun-path integration), ranks within the PV-bearing
    distribution, and scans 8-neighbours for tall casters.
    """
    pv_cells: List[Tuple[Tuple[int, int], float]] = []
    for f in features:
        p = f.get("properties") or {}
        if p.get("role") != "parcel":
            continue
        is_built = bool(p.get("is_built", False))
        is_solar_farm = p.get("land_use") == "solar_farm"
        if not (is_built or is_solar_farm):
            continue
        mult = float(p.get("pv_shading_multiplier_geom", 1.0))
        pv_cells.append(((int(p["row"]), int(p["col"])), mult))
    if not pv_cells:
        return {}
    pv_cells.sort(key=lambda kv: kv[1])
    sorted_values = [v for _, v in pv_cells]
    n = len(pv_cells)
    out: Dict[Tuple[Tuple[int, int]], Dict[str, object]] = {}
    for key, mult in pv_cells:
        first = next(i for i, v in enumerate(sorted_values) if v >= mult)
        last = n - 1 - next(
            i for i, v in enumerate(reversed(sorted_values)) if v <= mult
        )
        rank = (first + last) / 2.0
        percentile = rank / (n - 1) if n > 1 else 1.0
        cell = grid.at(key[0], key[1])
        target_z = (
            cell.height_m if cell.land_use != LandUse.SOLAR_FARM
            else GROUND_PV_PANEL_TOP_M
        )
        offs = _offender_dirs(grid, key[0], key[1], target_z)
        out[key] = {
            "percentile": round(float(percentile), 3),
            "offender_dirs": offs,
            "reason": _build_reason(mult, percentile, offs),
        }
    return out


def _inject(
    features: List[dict],
    cell_sites: Dict[Tuple[int, int], Tuple[bool, Optional[int]]],
    diagnostics: Dict[Tuple[int, int], Dict[str, object]],
    per_cell_kwp: float,
) -> Tuple[int, int]:
    """Write the new properties onto every feature whose (row, col) matches.

    Returns (n_floating_sites, n_diag_cells)."""
    n_sites = 0
    n_diag = 0
    for f in features:
        p = f.get("properties")
        if p is None:
            continue
        r = p.get("row")
        c = p.get("col")
        if r is None or c is None:
            continue
        key = (int(r), int(c))
        is_site, cluster_id = cell_sites.get(key, (False, None))
        p["is_floating_pv_site"] = bool(is_site)
        p["floating_pv_cluster_id"] = cluster_id
        p["floating_pv_deployable_kwp"] = round(
            per_cell_kwp if is_site else 0.0, 3,
        )
        if is_site:
            n_sites += 1
        diag = diagnostics.get(key)
        if diag is not None:
            p["pv_shading_percentile"] = diag["percentile"]
            p["pv_shading_offender_dirs"] = list(diag["offender_dirs"])
            p["pv_shading_reason"] = diag["reason"]
            n_diag += 1
        else:
            # Non-PV cell: leave unshaded defaults so the viewer never
            # sees a missing key.
            p.setdefault("pv_shading_percentile", 1.0)
            p.setdefault("pv_shading_offender_dirs", [])
            p.setdefault("pv_shading_reason", "")
    return n_sites, n_diag


def main() -> None:
    print(f"Injecting floating-PV sites + shading diagnostics into "
          f"{GEOJSON_DIR}/*.geojson")
    files = sorted(GEOJSON_DIR.glob("*.geojson"))
    if not files:
        print("No GeoJSON files found.")
        return
    min_cluster_size = _read_min_cluster_size()
    per_cell_kwp = _read_per_cell_kwp()
    print(f"  min_cluster_size={min_cluster_size}; "
          f"per_cell_kwp={per_cell_kwp:.1f}")
    for path in files:
        if path.name == "manifest.json":
            continue
        with path.open("r", encoding="utf-8") as f:
            gj = json.load(f)
        features = gj.get("features", []) or []
        grid = _grid_from_geojson_for_siting(features)
        chosen = assign_floating_pv_sites(
            grid, min_cluster_size=min_cluster_size,
        )
        cell_sites: Dict[Tuple[int, int], Tuple[bool, Optional[int]]] = {
            (c.row, c.col): (bool(c.is_floating_pv_site), c.floating_pv_cluster_id)
            for c in grid.all_cells()
        }
        diagnostics = _compute_diagnostics(grid, features)
        n_sites, n_diag = _inject(features, cell_sites, diagnostics, per_cell_kwp)
        with path.open("w", encoding="utf-8") as f:
            json.dump(gj, f, indent=2)
        cluster_str = ", ".join(
            f"c{k}={len(v)}" for k, v in sorted(chosen.items())
        ) or "no clusters"
        cap_kwp = sum(per_cell_kwp for c in grid.all_cells()
                      if c.is_floating_pv_site)
        print(
            f"  {path.name:30s} clusters={len(chosen)} sites={n_sites:3d} "
            f"cap={cap_kwp:7.1f}kWp diag_cells={n_diag:4d} ({cluster_str})"
        )


if __name__ == "__main__":
    main()
