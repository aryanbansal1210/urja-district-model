"""Discrete floating-PV site selection on clustered BLUE_SPACE cells.

the author flag: "do not allocate floating PV across every BLUE_SPACE
cell. Prefer grouped/contiguous water bodies to reduce wiring/BOS cost and
preserve aesthetics. Leave isolated/aesthetic water bodies panel-free."

The aggregate LP variable `m.floating_pv_kwp` is bounded by
`EnergyNetwork.total_floating_pv_potential_kwp`. Without spatial siting, that
ceiling sums every BLUE_SPACE cell × `kwp_per_cell_default` × `uptake_fraction`,
which (a) lets the LP saturate isolated single ponds and (b) makes the viewer
spread the deployed kWp across every water tile, including ornamental ponds.

This module groups BLUE_SPACE cells by 4-adjacency and flags `is_floating_pv_site
= True` only on cells in clusters of size >= `min_cluster_size`. Each chosen
cell also gets `floating_pv_cluster_id` (1-indexed, deterministic by sorted
cluster anchor). Mirrors the carport / faith / entrance pattern (deterministic,
post-SA, idempotent).

Justification for `min_cluster_size >= 2` as the default:
- BOS cost: floating PV needs floats, anchors, inverter pad, MV combiner +
  outbound cable. SECI / NREL FPV reviews cite ~12-18% BOS-cost premium over
  ground-mount, dominated by single-site fixed costs. A 1-cell isolated pond
  cannot amortise the floats + combiner; a 2-cell cluster shares them.
- Aesthetic: solitary urban ponds (rain-harvesting tanks, ornamental basins)
  are a community amenity. Punjab IDP / URDPFI public-realm guidance treats
  them as cool-refuge / heritage features.
- Operational: contiguous clusters are easier to maintain (one boat trip
  cleans the whole array; one mooring assembly).

The threshold is YAML-tunable via `floating_pv.site_selection.min_cluster_size`
in `config/economics.yaml`. Setting it to 1 restores legacy behaviour.

References:
- SECI FPV Tender Documents 2022 — BOS premium structure.
- NREL "Floating Photovoltaic System Cost Benchmark Q1 2021" (Ramasamy et al.)
  https://www.nrel.gov/docs/fy22osti/80695.pdf — fixed BOS dominates < 5 MW.
- PEDA Sidhwan Kalan / Ghaggar canal-top 5 MW (2024) — Punjab precedent for
  contiguous canal-top vs scattered pond floats.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from core.grid import Cell, Grid
from core.land_use import LandUse


DEFAULT_MIN_CLUSTER_SIZE = 2


def _connected_components(
    cells: Sequence[Cell],
    grid: Grid,
) -> List[List[Cell]]:
    """Group `cells` into 4-connected components within `grid`.

    Returns components sorted by (smallest row, smallest col) of their
    anchor cell so cluster IDs are deterministic across runs.
    """
    cell_lookup: Dict[Tuple[int, int], Cell] = {
        (c.row, c.col): c for c in cells
    }
    visited: Set[Tuple[int, int]] = set()
    components: List[List[Cell]] = []
    for cell in cells:
        key = (cell.row, cell.col)
        if key in visited:
            continue
        # BFS over 4-neighbours.
        component: List[Cell] = []
        queue: List[Cell] = [cell]
        visited.add(key)
        while queue:
            current = queue.pop(0)
            component.append(current)
            for nb in grid.neighbours_4(current.row, current.col):
                nb_key = (nb.row, nb.col)
                if nb_key in visited:
                    continue
                if nb_key in cell_lookup:
                    visited.add(nb_key)
                    queue.append(nb)
        components.append(component)
    # Sort components for deterministic cluster IDs.
    components.sort(key=lambda comp: min((c.row, c.col) for c in comp))
    return components


def assign_floating_pv_sites(
    grid: Grid,
    *,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
    eligible_land_uses: Optional[Sequence[LandUse]] = None,
) -> Dict[int, List[Tuple[int, int]]]:
    """Tag floating-PV deployment sites on `grid`. Mutates in place.

    Algorithm:
      1. Clear `is_floating_pv_site` and `floating_pv_cluster_id` on every
         cell (so re-runs are stable).
      2. Collect all cells whose land use is in `eligible_land_uses`
         (defaults to BLUE_SPACE only).
      3. Group those cells into 4-connected components.
      4. For each component of size >= `min_cluster_size`, assign a
         1-indexed `floating_pv_cluster_id` (deterministic, smallest
         (row, col) first) and set `is_floating_pv_site = True` on
         every cell in the cluster.
      5. Components smaller than the threshold remain panel-free.

    Returns
    -------
    Dict[int, List[(row, col)]]
        Mapping cluster_id -> list of (row, col) cells in that cluster.
        Empty when no qualifying cluster exists.
    """
    eligible_set = set(eligible_land_uses or [LandUse.BLUE_SPACE])
    # Reset previous tags so the function is idempotent.
    for c in grid.all_cells():
        c.is_floating_pv_site = False
        c.floating_pv_cluster_id = None

    candidates = [c for c in grid.all_cells() if c.land_use in eligible_set]
    if not candidates:
        return {}

    components = _connected_components(candidates, grid)
    chosen: Dict[int, List[Tuple[int, int]]] = {}
    cluster_id = 0
    for comp in components:
        if len(comp) < max(1, int(min_cluster_size)):
            continue
        cluster_id += 1
        chosen[cluster_id] = []
        # Sort cells within a cluster for stable output.
        for cell in sorted(comp, key=lambda c: (c.row, c.col)):
            cell.is_floating_pv_site = True
            cell.floating_pv_cluster_id = cluster_id
            chosen[cluster_id].append((cell.row, cell.col))
    return chosen


def floating_pv_kwp_for_cell(
    cell: Cell, kwp_per_cell_default: float, uptake_fraction: float,
) -> float:
    """Per-cell floating-PV kWp (deployable on the water surface).

    Matches the legacy `kwp_per_cell_default × uptake_fraction` formula
    so the per-cell number stays comparable across configurations. The
    aggregate ceiling sums this over every cell with
    `is_floating_pv_site = True`.
    """
    return float(kwp_per_cell_default) * float(uptake_fraction)
