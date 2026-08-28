"""Electrical-asset model (Stage D Phases B-E) — deterministic network layer.

 (Opus 4.8). On top of the Phase-2 per-edge KCL, this module adds the
explicit distribution NETWORK: cable route-km + voltage classes (Phase B/C),
the 33 kV backbone that makes the realistic per-cable cap FEASIBLE (Phase C),
the substation MVA cap (Phase C), and distribution-transformer siting (Phase D).
All of it is DETERMINISTIC (graph + arithmetic, no LP) — the dispatch LP only
reads the per-edge thermal caps + the annualised capex constants this produces.

OPT-IN: every consumer gates on ``econ.electrical_network_enabled``; when False
the production single-bus / Phase-1 path is byte-exact.

Key objects:
  * ``assign_voltage_classes(net, econ)`` -> {edge_key: "backbone_33kv"|"dist_11kv"}
    via a backbone heuristic (BFS trees from the substation along arterial roads
    to the N load-zone centroids).
  * ``network_capex_inr(net, econ)`` -> total cable CAPEX (route-km x ₹/km x
    OH/UG blend), and its annualised value.
  * ``substation_capex_inr(econ)`` + annualised.
  * ``per_edge_thermal_kw(net, econ)`` -> {edge_key: cap_kw} for the KCL.

Edge keys are the ordered ``(a, b)`` cell-id tuples from ``EnergyNetwork.edges``.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

from core.land_use import LandUse
from energy.network import EnergyNetwork

CellId = Tuple[int, int]
EdgeKey = Tuple[CellId, CellId]


# ---------------------------------------------------------------------------
# Capital recovery factor (mirror energy.costs.crf so this module is standalone)
# ---------------------------------------------------------------------------
def _crf(rate: float, years: int) -> float:
    """Capital recovery factor = annuity that pays off 1 unit over `years`."""
    if years <= 0:
        return 0.0
    if rate <= 0:
        return 1.0 / years
    return (rate * (1 + rate) ** years) / ((1 + rate) ** years - 1)


# ---------------------------------------------------------------------------
# Substation + road graph
# ---------------------------------------------------------------------------
def substation_cell(net: EnergyNetwork) -> CellId:
    """Most-central ROAD JUNCTION (grid-injection node). Mirrors the Phase-2
    ``_stage_d_pick_substation_cell`` so the electrical model agrees with KCL.
 (A4 re-time / register B15): junction preference (>= 3
    road-road edges, feeder-hub siting per CEA distribution planning) added
    in BOTH pickers - see the dispatch.py docstring for the full rationale."""
    road = [n for n in net.nodes if n.land_use == LandUse.ROAD]
    if not road:
        raise RuntimeError("electrical_assets needs at least one ROAD cell")
    built = [n for n in net.nodes if n.is_built]
    src = built or road
    cx = sum(b.centre_x_m for b in src) / len(src)
    cy = sum(b.centre_y_m for b in src) / len(src)
    degree: Dict[CellId, int] = {}
    for e in net.edges:
        degree[e.a] = degree.get(e.a, 0) + 1
        degree[e.b] = degree.get(e.b, 0) + 1
    junctions = [r for r in road if degree.get(r.cell_id, 0) >= 3]
    pool = junctions or road
    return min(pool, key=lambda r: ((r.centre_x_m - cx) ** 2
               + (r.centre_y_m - cy) ** 2,
               r.cell_id[0], r.cell_id[1])).cell_id


def _road_adjacency(net: EnergyNetwork) -> Dict[CellId, List[CellId]]:
    """Undirected ROAD-ROAD adjacency from the network's edges."""
    adj: Dict[CellId, List[CellId]] = {}
    for e in net.edges:
        adj.setdefault(e.a, []).append(e.b)
        adj.setdefault(e.b, []).append(e.a)
    return adj


def _edge_key(a: CellId, b: CellId) -> EdgeKey:
    """Canonical undirected edge key (matches EnergyNetwork.edges a<b order)."""
    return (a, b) if a <= b else (b, a)


# ---------------------------------------------------------------------------
# Load-zone centroids (for the backbone heuristic)
# ---------------------------------------------------------------------------
def _load_zone_road_targets(net: EnergyNetwork, n_zones: int) -> List[CellId]:
    """Pick ``n_zones`` ROAD cells nearest to the centroids of the N largest
    geographic clusters of built demand. Deterministic.

    Simple + stable approach: split the district into an approximately square
    grid of ``n_zones`` sectors, and for each sector with built demand take the
    ROAD cell nearest that sector's demand-weighted centroid. The substation's
    feeders will run out toward these targets, forming the 33 kV backbone.
    """
    road = [n for n in net.nodes if n.land_use == LandUse.ROAD]
    built = [n for n in net.nodes if n.is_built and n.peak_demand_kw > 0]
    if not road or not built:
        return []
    xs = [b.centre_x_m for b in built]
    ys = [b.centre_y_m for b in built]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    # near-square sector grid covering n_zones
    import math
    ncol = max(1, int(round(math.sqrt(n_zones))))
    nrow = max(1, int(math.ceil(n_zones / ncol)))
    targets: List[CellId] = []
    for ri in range(nrow):
        for ci in range(ncol):
            if len(targets) >= n_zones:
                break
            sx0 = x0 + (x1 - x0) * ci / ncol
            sx1 = x0 + (x1 - x0) * (ci + 1) / ncol
            sy0 = y0 + (y1 - y0) * ri / nrow
            sy1 = y0 + (y1 - y0) * (ri + 1) / nrow
            sect = [b for b in built
                    if sx0 <= b.centre_x_m <= sx1 and sy0 <= b.centre_y_m <= sy1]
            if not sect:
                continue
            w = sum(b.peak_demand_kw for b in sect) or 1.0
            mx = sum(b.centre_x_m * b.peak_demand_kw for b in sect) / w
            my = sum(b.centre_y_m * b.peak_demand_kw for b in sect) / w
            tgt = min(road, key=lambda r: (r.centre_x_m - mx) ** 2
                      + (r.centre_y_m - my) ** 2)
            if tgt.cell_id not in targets:
                targets.append(tgt.cell_id)
    return targets


def _bfs_path(adj: Dict[CellId, List[CellId]], src: CellId,
              dst: CellId) -> List[CellId]:
    """Shortest hop path src->dst over the ROAD graph (BFS). [] if unreachable.
    Neighbour iteration is sorted for determinism."""
    if src == dst:
        return [src]
    prev: Dict[CellId, Optional[CellId]] = {src: None}
    q = deque([src])
    while q:
        u = q.popleft()
        for v in sorted(adj.get(u, [])):
            if v not in prev:
                prev[v] = u
                if v == dst:
                    # reconstruct
                    path = [v]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])  # type: ignore[arg-type]
                    return list(reversed(path))
                q.append(v)
    return []


# ---------------------------------------------------------------------------
# Phase C: voltage-class assignment (the backbone heuristic)
# ---------------------------------------------------------------------------
def assign_voltage_classes(net: EnergyNetwork,
                           econ) -> Dict[EdgeKey, str]:
    """Assign each ROAD-ROAD edge a voltage class: 'backbone_33kv' or
    'dist_11kv'. Backbone = the union of shortest-path trees from the substation
    to the N load-zone targets (the arterial routes that must carry bulk power).
    Everything else is 11 kV distribution.

    Returns
    -------
    Dict[EdgeKey, str]
        Voltage class per edge (keyed by canonical (a,b) tuple).
    """
    classes: Dict[EdgeKey, str] = {
        _edge_key(e.a, e.b): "dist_11kv" for e in net.edges
    }
    if econ.en_backbone_assignment() != "heuristic":
        return classes  # all 11 kV (legacy Phase-2 behaviour)

    adj = _road_adjacency(net)
    src = substation_cell(net)
    targets = _load_zone_road_targets(net, econ.en_backbone_n_feeders())
    for dst in targets:
        path = _bfs_path(adj, src, dst)
        for u, v in zip(path, path[1:]):
            k = _edge_key(u, v)
            if k in classes:
                classes[k] = "backbone_33kv"
    return classes


def per_edge_thermal_kw(net: EnergyNetwork, econ) -> Dict[EdgeKey, float]:
    """Per-edge thermal cap (kW) by assigned voltage class. This is what makes
    the realistic-cap network feasible: backbone edges get ~40 MW, the rest
    6 MW. Used by the Phase-2 KCL flow bounds."""
    vc = assign_voltage_classes(net, econ)
    return {k: econ.en_voltage_tier_thermal_kw(cls) for k, cls in vc.items()}


# ---------------------------------------------------------------------------
# Phase B: network cable CAPEX
# ---------------------------------------------------------------------------
def network_capex_inr(net: EnergyNetwork, econ) -> Dict[str, float]:
    """Total cable CAPEX over all ROAD-ROAD edges, split by an OH/UG blend per
    voltage class. Returns a breakdown dict incl. 'total' and 'annualised'.

    capex_edge = length_km * [ (1-ug)*OH_₹/km + ug*UG_₹/km ]  for the edge's class.
    """
    vc = assign_voltage_classes(net, econ)
    by_class_km: Dict[str, float] = {"backbone_33kv": 0.0, "dist_11kv": 0.0}
    edge_len = {_edge_key(e.a, e.b): e.length_m for e in net.edges}
    for k, cls in vc.items():
        by_class_km[cls] += edge_len.get(k, 0.0) / 1000.0

    def blended_per_km(tier: str) -> float:
        ug = econ.en_underground_fraction(tier)
        oh_rate = econ.en_cable_capex_inr_per_km(f"{tier}_oh")
        ug_rate = econ.en_cable_capex_inr_per_km(f"{tier}_ug")
        return (1.0 - ug) * oh_rate + ug * ug_rate

    capex_backbone = by_class_km["backbone_33kv"] * blended_per_km("backbone_33kv")
    capex_dist = by_class_km["dist_11kv"] * blended_per_km("dist_11kv")
    total = capex_backbone + capex_dist
    # annualise over cable life at the utility discount rate
    rate = econ.actor_discount_rate("utility")
    crf = _crf(rate, econ.en_cable_lifetime_years())
    return {
        "backbone_33kv_km": by_class_km["backbone_33kv"],
        "dist_11kv_km": by_class_km["dist_11kv"],
        "total_route_km": by_class_km["backbone_33kv"] + by_class_km["dist_11kv"],
        "capex_backbone_inr": capex_backbone,
        "capex_dist_inr": capex_dist,
        "capex_total_inr": total,
        "annualised_inr": total * crf,
    }


# ---------------------------------------------------------------------------
# Phase C: substation CAPEX + throughput cap
# ---------------------------------------------------------------------------
def substation_capex_inr(econ) -> Dict[str, float]:
    """Primary 33/11 kV substation CAPEX (₹/MVA x MVA) + annualised."""
    capex = econ.en_substation_capex_inr_per_mva() * econ.en_substation_mva_installed()
    rate = econ.actor_discount_rate("utility")
    crf = _crf(rate, econ.en_substation_lifetime_years())
    return {
        "mva_installed": econ.en_substation_mva_installed(),
        "capex_total_inr": capex,
        "annualised_inr": capex * crf,
        "throughput_cap_kw": econ.en_substation_throughput_cap_kw(),
    }


def production_network_annualised_inr(net: EnergyNetwork,
                                      econ) -> Dict[str, float]:
    """Annualised internal-network CAPEX for the PRODUCTION dispatch paths.

    Same three components as ``electrical_network_annualised_capex_inr``
    (cables + substation + distribution transformers) but gated on
    ``en_cost_in_production_enabled`` instead of
    ``electrical_network_enabled`` - so the cost can be charged while
    Stage-D, and its unvalidated injection/loss layers, stay off.

. Before this, `electrical_network.enabled` was false AND its
    only consumer sat inside the Stage-D builder, which is also off: the
    district's internal grid was costed in no production number at all.

    PARITY: the caller adds this to every scenario including BAU. It is a
    constant of the LAYOUT, not of the dispatch, so it is a post-hoc
    overlay and the LP itself is unchanged (same convention as the Stage-D
    overlay at dispatch.py ~3963).
    """
    if not econ.en_cost_in_production_enabled():
        return {"annualised_total_inr": 0.0, "enabled": False}
    cab = network_capex_inr(net, econ)
    sub = substation_capex_inr(econ)
    txr = transformer_capex_inr(net, econ)
    return {
        "enabled": True,
        "cable_annualised_inr": cab["annualised_inr"],
        "cable_route_km": cab["total_route_km"],
        "cable_capex_total_inr": cab["capex_total_inr"],
        "substation_annualised_inr": sub["annualised_inr"],
        "substation_mva_installed": sub["mva_installed"],
        "substation_capex_total_inr": sub["capex_total_inr"],
        "transformer_annualised_inr": txr["annualised_inr"],
        "transformer_total_kva": txr["total_kva"],
        "annualised_total_inr": (cab["annualised_inr"] + sub["annualised_inr"]
                                 + txr["annualised_inr"]),
    }


def production_network_annualised_kgco2(net: EnergyNetwork,
                                        econ) -> Dict[str, float]:
    """Annualised EMBODIED carbon of the district's own internal network.

    Pairs with ``production_network_annualised_inr``: the same three asset
    groups, the same layout, the same parity rule, annualised over each
    group's OWN design life (cables 40 y, substation 35 y, distribution
    transformers 25 y) rather than a single blended figure.

    Gated on BOTH ``internal_network_embodied_enabled`` (factors present
    and global embodied carbon on) AND ``en_cost_in_production_enabled``
    - the carbon follows the cost, so a scenario that does not pay for the
    network does not carry its carbon either.

    Sources and the declared substitutions are in economics.yaml under
    ``embodied_carbon.internal_network``. Roughly 0.19% of the town's
    annual CO2, charged at parity, so it is here for completeness.
    """
    off = {"annualised_total_kgco2": 0.0, "enabled": False}
    if not (econ.en_cost_in_production_enabled()
            and econ.internal_network_embodied_enabled()):
        return off
    f = econ.internal_network_embodied()
    cab = network_capex_inr(net, econ)
    sub = substation_capex_inr(econ)
    txr = transformer_capex_inr(net, econ)

    cable_kg = (cab["dist_11kv_km"] * float(f.get("cable_11kv_kgco2_per_km", 0.0))
                + cab["backbone_33kv_km"]
                * float(f.get("cable_33kv_kgco2_per_km", 0.0)))
    sub_kg = (sub["mva_installed"]
              * float(f.get("substation_kgco2_per_mva", 0.0)))
    txr_kg = (txr["total_kva"] / 1000.0
              * float(f.get("transformer_kgco2_per_mva", 0.0)))

    cab_life = max(1, int(econ.en_cable_lifetime_years()))
    sub_life = max(1, int(econ.en_substation_lifetime_years()))
    txr_life = max(1, int(econ.en_transformer_lifetime_years()))
    ann = (cable_kg / cab_life + sub_kg / sub_life + txr_kg / txr_life)
    return {
        "enabled": True,
        "cable_kgco2_total": cable_kg,
        "cable_kgco2_annual": cable_kg / cab_life,
        "substation_kgco2_total": sub_kg,
        "substation_kgco2_annual": sub_kg / sub_life,
        "transformer_kgco2_total": txr_kg,
        "transformer_kgco2_annual": txr_kg / txr_life,
        "annualised_total_kgco2": ann,
    }


def electrical_network_annualised_capex_inr(net: EnergyNetwork,
                                            econ) -> Dict[str, float]:
    """Total annualised electrical-asset CAPEX (cables + substation +
    distribution transformers). Returns a breakdown; 'annualised_total_inr' is
    the line that enters lifetime cost."""
    if not econ.electrical_network_enabled():
        return {"annualised_total_inr": 0.0}
    cab = network_capex_inr(net, econ)
    sub = substation_capex_inr(econ)
    txr = transformer_capex_inr(net, econ)
    return {
        "cable_annualised_inr": cab["annualised_inr"],
        "cable_route_km": cab["total_route_km"],
        "cable_backbone_km": cab["backbone_33kv_km"],
        "cable_dist_km": cab["dist_11kv_km"],
        "cable_capex_total_inr": cab["capex_total_inr"],
        "substation_annualised_inr": sub["annualised_inr"],
        "substation_capex_total_inr": sub["capex_total_inr"],
        "substation_throughput_cap_kw": sub["throughput_cap_kw"],
        "transformer_annualised_inr": txr["annualised_inr"],
        "transformer_capex_total_inr": txr["capex_total_inr"],
        "transformer_total_kva": txr["total_kva"],
        "n_transformer_zones": txr["n_zones"],
        "annualised_total_inr": (cab["annualised_inr"] + sub["annualised_inr"]
                                 + txr["annualised_inr"]),
    }


# ---------------------------------------------------------------------------
# Phase D: distribution transformers (11 kV / 415 V), per zone
# ---------------------------------------------------------------------------
def transformer_zones(net: EnergyNetwork, econ,
                      n_zones: Optional[int] = None) -> List[Dict[str, object]]:
    """Split the built district into N transformer zones (NOT per cell) and size
    each zone's distribution transformer to its peak load. Deterministic
    sector-grid split (mirrors the backbone load-zone heuristic).

    Returns one dict per non-empty zone:
        {"centroid": (x,y), "peak_kw": float, "kva": float, "n_built": int}
    where kva = peak_kw / pf x sizing_headroom (rounded up to a standard rating).
    """
    import math
    built = [n for n in net.nodes if n.is_built and n.peak_demand_kw > 0]
    if not built:
        return []
    # default zone count: ~1 DTR per 8-12 built cells (urban DTR serves a cluster)
    if n_zones is None:
        n_zones = max(1, len(built) // 10)
    xs = [b.centre_x_m for b in built]
    ys = [b.centre_y_m for b in built]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    ncol = max(1, int(round(math.sqrt(n_zones))))
    nrow = max(1, int(math.ceil(n_zones / ncol)))
    pf = econ.en_substation_power_factor() or 0.95
    headroom = econ.en_transformer_sizing_headroom()
    # standard DTR ratings (kVA) to round up to (BEE/CEA common sizes)
    std = [63, 100, 160, 200, 250, 315, 400, 500, 630, 800, 1000]
    zones: List[Dict[str, object]] = []
    for ri in range(nrow):
        for ci in range(ncol):
            sx0 = x0 + (x1 - x0) * ci / ncol
            sx1 = x0 + (x1 - x0) * (ci + 1) / ncol
            sy0 = y0 + (y1 - y0) * ri / nrow
            sy1 = y0 + (y1 - y0) * (ri + 1) / nrow
            sect = [b for b in built
                    if sx0 <= b.centre_x_m <= sx1 and sy0 <= b.centre_y_m <= sy1]
            if not sect:
                continue
            peak_kw = sum(b.peak_demand_kw for b in sect)
            req_kva = peak_kw / pf * headroom
            kva = next((s for s in std if s >= req_kva), req_kva)
            w = peak_kw or 1.0
            cx = sum(b.centre_x_m * b.peak_demand_kw for b in sect) / w
            cy = sum(b.centre_y_m * b.peak_demand_kw for b in sect) / w
            zones.append({"centroid": (cx, cy), "peak_kw": peak_kw,
                          "kva": float(kva), "n_built": len(sect)})
    return zones


def transformer_capex_inr(net: EnergyNetwork, econ) -> Dict[str, float]:
    """Total distribution-transformer CAPEX (Σ kVA x ₹/kVA) + annualised."""
    zones = transformer_zones(net, econ)
    total_kva = sum(z["kva"] for z in zones)
    capex = total_kva * econ.en_transformer_capex_inr_per_kva()
    rate = econ.actor_discount_rate("utility")
    crf = _crf(rate, econ.en_transformer_lifetime_years())
    return {
        "n_zones": len(zones),
        "total_kva": total_kva,
        "capex_total_inr": capex,
        "annualised_inr": capex * crf,
    }


def transformer_loss_kwh(net: EnergyNetwork, econ,
                         annual_throughput_kwh: float) -> Dict[str, float]:
    """Explicit distribution-transformer losses (kWh/yr), split into:
      * no-load (core) loss: constant, ∝ installed kVA x 8760 h;
      * load (copper) loss: ∝ throughput (linear proxy for the I²R term at a
        representative loading; the full ∝loading² is linearised in Phase E).

    DOUBLE-COUNT NOTE: the aggregate ``ac_loss_fraction`` (0.02) already includes
    a transformer share (~``share_of_ac_loss_fraction``). When transformers are
    EXPLICIT, the caller must remove that share from the aggregate factor so the
    losses are not counted twice. This function returns the EXPLICIT transformer
    loss; the reconciliation (subtracting the share) is applied where
    ac_loss_fraction is consumed, gated on electrical_network.enabled.
    """
    zones = transformer_zones(net, econ)
    total_kva = sum(z["kva"] for z in zones)
    no_load_kw = total_kva * econ.en_transformer_no_load_loss_fraction()
    no_load_kwh = no_load_kw * 8760.0
    # load loss at a representative average loading: scale the rated copper loss
    # (∝loading²) by (avg_loading)². Approx avg loading from throughput vs kVA.
    pf = econ.en_substation_power_factor() or 0.95
    rated_kw = total_kva * pf
    avg_load_kw = annual_throughput_kwh / 8760.0 if annual_throughput_kwh else 0.0
    loading = (avg_load_kw / rated_kw) if rated_kw else 0.0
    load_loss_rated_kw = rated_kw * econ.en_transformer_load_loss_fraction_at_rated()
    load_loss_kwh = load_loss_rated_kw * (loading ** 2) * 8760.0
    return {
        "no_load_kwh": no_load_kwh,
        "load_kwh": load_loss_kwh,
        "total_kwh": no_load_kwh + load_loss_kwh,
        "avg_loading": loading,
    }
