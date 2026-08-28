"""Evidence pass for the author's visual review (read-only).

Answers, from the PRODUCTION geojson + dispatch_results.json:
  A. highstreet cluster sizes (was a 4-chain corridor kept?)
  B. building heights per income class (how many distinct sizes each?)
  C. solar_expansion tag adjacency to the farm (contiguous or scattered?)
  D. agri_belt contiguity (belt or confetti?)
  E. parking_expansion road/lane frontage (reserved lots reachable?)
  F. road network components (find the orphan road cell)
  G. amenity counts for 250k (hospitals/hotels/schools vs URDPFI)
  H. population capacity check (do 250k fit?)
  I. open-space cluster shape stats (rectangularity of emergent parks)
  J. who exports at noon in the dispatch by_cell data (houses green?)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def clusters_of(cells, all_set):
    """4-neighbour connected components of a set of (r, c)."""
    seen, out = set(), []
    for rc in cells:
        if rc in seen:
            continue
        comp, stack = [], [rc]
        seen.add(rc)
        while stack:
            r, c = stack.pop()
            comp.append((r, c))
            for nb in ((r+1, c), (r-1, c), (r, c+1), (r, c-1)):
                if nb in all_set and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        out.append(comp)
    return sorted(out, key=len, reverse=True)


def main() -> None:
    from core.land_use import LandUse
    from energy.network import grid_from_geojson
    from layout.road_network import cells_with_lane_frontage

    g, _ = grid_from_geojson()
    P = lambda *a: print(*a, flush=True)

    by_use = defaultdict(set)
    for c in g.all_cells():
        by_use[c.land_use.name].add((c.row, c.col))

    # ---- A. highstreet corridor -------------------------------------------
    hs = by_use.get("RETAIL_HIGHSTREET", set())
    hs_cl = clusters_of(hs, hs)
    P("A. HIGHSTREET: {} cells in {} clusters; sizes {}".format(
        len(hs), len(hs_cl), [len(x) for x in hs_cl]))

    # ---- B. heights per income class --------------------------------------
    P("\nB. HEIGHTS PER RESIDENTIAL CLASS (distinct storey/height values):")
    hclass = defaultdict(Counter)
    for c in g.all_cells():
        if c.land_use.name.startswith("RESIDENTIAL") and c.has_building:
            h = getattr(c, "building_height_m", None) or getattr(c, "height_m", 0)
            hclass[c.land_use.name][round(float(h), 1)] += 1
    for k in sorted(hclass):
        P("   {:<28} {}".format(k, dict(sorted(hclass[k].items()))))

    # ---- C. solar_expansion adjacency -------------------------------------
    farm = by_use.get("SOLAR_FARM", set())
    exp = {(c.row, c.col): c.amenity_subtype for c in g.all_cells()
           if (c.amenity_subtype or "").startswith("solar_expansion")}
    P("\nC. SOLAR EXPANSION TAGS: {} cells".format(len(exp)))
    exp_set = set(exp)
    touch_farm = sum(1 for (r, cc) in exp_set
                     if any(nb in farm for nb in ((r+1,cc),(r-1,cc),(r,cc+1),(r,cc-1))))
    touch_any = sum(1 for (r, cc) in exp_set
                    if any(nb in farm or nb in exp_set
                           for nb in ((r+1,cc),(r-1,cc),(r,cc+1),(r,cc-1))))
    exp_cl = clusters_of(exp_set, exp_set | farm)   # clusters allowed to run through farm
    pure_cl = clusters_of(exp_set, exp_set)
    P("   touching the farm itself: {}/{}".format(touch_farm, len(exp_set)))
    P("   touching farm OR another expansion cell: {}/{}".format(touch_any, len(exp_set)))
    P("   expansion-only clusters: {} (sizes {})".format(
        len(pure_cl), [len(x) for x in pure_cl][:12]))
    # farm cluster count for reference
    farm_cl = clusters_of(farm, farm)
    P("   (farm itself: {} cells in {} clusters, largest {})".format(
        len(farm), len(farm_cl), len(farm_cl[0]) if farm_cl else 0))

    # ---- D. agri belt ------------------------------------------------------
    agri = {(c.row, c.col) for c in g.all_cells()
            if c.amenity_subtype == "agri_belt"}
    agri_cl = clusters_of(agri, agri)
    n_rows = len(g.cells)
    n_cols = len(g.cells[0])
    edge = sum(1 for (r, cc) in agri
               if r in (0, n_rows - 1) or cc in (0, n_cols - 1))
    P("\nD. AGRI BELT: {} cells in {} clusters (sizes {}); {} on the site edge".format(
        len(agri), len(agri_cl), [len(x) for x in agri_cl][:12], edge))

    # ---- E. parking_expansion frontage ------------------------------------
    roads = by_use.get("ROAD", set())
    served = cells_with_lane_frontage(g)
    pexp = {(c.row, c.col): c.amenity_subtype for c in g.all_cells()
            if (c.amenity_subtype or "").startswith("parking_expansion")}
    bad = []
    for (r, cc) in pexp:
        has_road = any(nb in roads for nb in ((r+1,cc),(r-1,cc),(r,cc+1),(r,cc-1)))
        has_lane = (r, cc) in served
        if not (has_road or has_lane):
            bad.append((r, cc))
    P("\nE. PARKING EXPANSION: {} tagged; {} WITHOUT road or lane frontage: {}".format(
        len(pexp), len(bad), bad))

    # ---- F. road components ------------------------------------------------
    road_cl = clusters_of(roads, roads)
    P("\nF. ROAD COMPONENTS: {} components, sizes {}".format(
        len(road_cl), [len(x) for x in road_cl][:6]))
    if len(road_cl) > 1:
        for comp in road_cl[1:]:
            P("   ORPHAN road cells: {}".format(comp))
            for (r, cc) in comp:
                nbs = Counter(g.cells[nr][nc].land_use.name
                              for nr, nc in ((r+1,cc),(r-1,cc),(r,cc+1),(r,cc-1))
                              if 0 <= nr < n_rows and 0 <= nc < n_cols)
                P("     ({}, {}) neighbours: {}".format(r, cc, dict(nbs)))

    # ---- G. amenity counts --------------------------------------------------
    P("\nG. AMENITY COUNTS (cells; URDPFI-style norms for 250k in brackets):")
    for use, norm in [
        ("SCHOOL", "sr-sec ~1/7,500 -> ~33 schools of all tiers"),
        ("HEALTHCARE", "URDPFI: ~1 general hospital (500 beds)/250k + interm."),
        ("HOTEL", "no URDPFI norm; market-driven"),
        ("RESTAURANT", "market-driven"),
        ("SHOPPING_CENTRE", "community centre ~1/100k"),
        ("RETAIL_HIGHSTREET", "-"),
        ("PUBLIC_SERVICES", "police+fire+civic"),
        ("RELIGIOUS", "~1/10-15k"),
        ("OFFICE", "-"), ("LIGHT_INDUSTRY", "-"),
    ]:
        n = len(by_use.get(use, ()))
        P("   {:<18} {:>3}   [{}]".format(use, n, norm))

    # ---- H. population capacity --------------------------------------------
    P("\nH. POPULATION CAPACITY:")
    hh_by_class, pop = Counter(), 0.0
    occ = {"RESIDENTIAL_LOW": 5.0, "RESIDENTIAL_MID": 4.6,
           "RESIDENTIAL_HIGH": 4.3, "RESIDENTIAL_PLOTTED": 4.3}
    for c in g.all_cells():
        if c.land_use.name.startswith("RESIDENTIAL") and c.has_building:
            hh = float(getattr(c, "households", 0) or 0)
            hh_by_class[c.land_use.name] += hh
    tot_hh = sum(hh_by_class.values())
    for k, v in sorted(hh_by_class.items()):
        P("   {:<28} {:>10,.0f} HH".format(k, v))
    P("   TOTAL {:,.0f} HH x ~4.6 = ~{:,.0f} people (design 250,000)".format(
        tot_hh, tot_hh * 4.6))

    # ---- I. open-space cluster shapes --------------------------------------
    osp = by_use.get("OPEN_SPACE", set())
    osp_cl = clusters_of(osp, osp)
    P("\nI. OPEN-SPACE CLUSTERS: {} clusters; sizes top-12 {}".format(
        len(osp_cl), [len(x) for x in osp_cl][:12]))
    irregular = 0
    for comp in osp_cl:
        if len(comp) < 4:
            continue
        rs = [r for r, _ in comp]; cs = [cc for _, cc in comp]
        bbox = (max(rs)-min(rs)+1) * (max(cs)-min(cs)+1)
        if len(comp) / bbox < 0.6:
            irregular += 1
    P("   clusters >=4 cells with fill-ratio < 0.6 (raggedy): {}".format(irregular))
    singles = sum(1 for x in osp_cl if len(x) == 1)
    P("   singleton open-space cells: {}".format(singles))

    # ---- J. noon export attribution -----------------------------------------
    P("\nJ. NOON EXPORT (dispatch_results.json by_cell, if present):")
    d = json.load(open(ROOT / "outputs/data/energy/dispatch_results.json",
                       encoding="utf-8"))
    fs = None
    for sc in d.get("scenarios", []):
        if sc.get("name") == "full_stack" and abs(sc.get("alpha", -1)) < 1e-9:
            fs = sc
            break
    if fs is None:
        fs = d if "by_cell" in d else None
    bc = (fs or {}).get("by_cell") or (fs or {}).get("stage_d_by_cell")
    if not bc:
        keys = list((fs or d).keys())
        P("   no by_cell key found; scenario keys: {}...".format(keys[:14]))
    else:
        sample = next(iter(bc.values()))
        P("   by_cell entries: {}; fields per cell: {}".format(
            len(bc), list(sample.keys())[:12]))

if __name__ == "__main__":
    main()
