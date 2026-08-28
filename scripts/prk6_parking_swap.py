""": swap the (12,28) car park with the (12,26) kothi cell.

the author-APPROVED (option A). Register row.

WHY. Both lane-served car parks are legally reachable - `check_parking_road_frontage`
passes because the author's ratified B8 rule counts a 12 m lane as drivable frontage, and
the lane chain from (12,28) does reach the arterial:

    (12,28) parking -> (12,27) school -> (12,26) residential -> (12,25) ROAD

But that lane threads 300 m between a school and a housing block to reach a car park,
so every car bound for the lot drives past a school. the author's design call: move the lot
onto the road instead.

WHY (12,26) AND NOT SOMETHING ELSE. The whole west edge of that block is a protected
greenway corridor - (9,26), (10,26), (11,26), (13,26), (14,26) all carry
amenity_subtype "greenway". (12,26) is the ONLY road-adjacent cell in the block that
can move. The alternative screened earlier, swapping with the (9,30) shopping centre,
was REJECTED on inspection: it would put the highest-traffic use in the ECS table
(3 ECS/100 sqm, 30,000 m2 of floor) onto the lane-only cell, which is worse than the
problem being fixed. Housing is the one use for which lane-only access is normal -
that is what a 12 m galli is for (RPT-1, plan Table 7-1 note ii, IRC:103).

(13,46) is deliberately LEFT ALONE: its lane crosses only open space inside the
industrial cluster it serves, so it carries none of the school-traffic objection.

WHY A SURGICAL JSON PATCH AND NOT A RE-EXPORT. Tested first: loading the grid and
re-exporting it with `core.export_3d.grid_to_geojson` drifts **815 of 2500 cells**,
almost all on `deployable_pv_kwp` / `pv_shading_percentile` / `pv_deployed_kwp` -
the geometric-shading precompute does not reproduce the stored values. Re-exporting
would silently rewrite the frozen layout. So this patches the two cells in place,
the same way the roadshift / orphanfix / stub-connect patches were done.

WHAT MOVES.
  * the two PARCEL features exchange every property except row / col / cell_id / layout
  * the 4 `structure` features (the kothi footprints) move from (12,26) to (12,28):
    row / col / cell_id rewritten and every coordinate translated +2 cells east
    (+0.00208815744631 deg lon, exactly the two-cell pitch measured off the parcels)
  * `entrance_sides` is RE-DERIVED for both cells from
    `layout.entrance_assignment.entrance_sides_for_cell`, which is deterministic and
    position-based - it does not travel with the cell

WHAT DELIBERATELY DOES NOT MOVE.
  * `building_axis_deg` keeps the kothi's 270 deg (west-facing). At (12,26) west was
    the arterial; at (12,28) west is the serving lane, so the building still faces its
    access. The axis is set by an SA random choice (layout/optimiser.py ~572), so
    there is no deterministic value to re-derive without re-annealing.
  * `pv_shading_*` and `deployable_pv_kwp` travel with the cell. They are VIEWER
    fields: `energy.network.grid_from_geojson` does not read them, it re-derives PV
    and shading from land_use + height_tier + config downstream. Verified by reading
    the loader.

COST. Land-use counts are exactly conserved, so demand, floor area and rooftop-PV
ceiling totals are unchanged; only position moves. Expect the ~Rs 29k/yr class of
shift measured for the stub-connect cell, and re-measure rather than
predict - the stub-connect prediction missed by Rs 47.60 when a 5 kWh battery moved.

Run from district_v3:
    PYTHONPATH=. python -u scripts/prk6_parking_swap.py          # dry run, prints the plan
    PYTHONPATH=. python -u scripts/prk6_parking_swap.py --apply  # writes (backs up first)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

GEOJSON = os.path.join(ROOT, "outputs", "geojson3d", "optimised_sa.geojson")
BACKUP = GEOJSON + ".bak.pre-prk6-swap"

LOT = (12, 28)          # the car park, lane-served
KOTHI = (12, 26)        # residential_high, on the arterial at (12,25)
KEEP = {"row", "col", "cell_id", "layout"}


def _parcel_index(features):
    """(row, col) -> index of its PARCEL feature, the loader's own selection."""
    out = {}
    for i, ft in enumerate(features):
        p = ft["properties"]
        if p.get("role") != "parcel":
            continue
        out[(p.get("row"), p.get("col"))] = i
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)
    feats = gj["features"]
    pidx = _parcel_index(feats)
    i_lot, i_kothi = pidx[LOT], pidx[KOTHI]
    p_lot = feats[i_lot]["properties"]
    p_kothi = feats[i_kothi]["properties"]

    assert p_lot["land_use"] == "parking_lot", p_lot["land_use"]
    assert p_kothi["land_use"] == "residential_high", p_kothi["land_use"]

    # two-cell pitch, measured off the parcels themselves
    x_lot = feats[i_lot]["geometry"]["coordinates"][0][0][0]
    x_kothi = feats[i_kothi]["geometry"]["coordinates"][0][0][0]
    dlon = x_lot - x_kothi

    structures = [i for i, ft in enumerate(feats)
                  if ft["properties"].get("role") == "structure"
                  and (ft["properties"].get("row"),
                       ft["properties"].get("col")) == KOTHI]

    print(f"PRK-6 SWAP  {LOT} parking_lot  <->  {KOTHI} residential_high")
    print(f"  parcel features      : idx {i_lot} and {i_kothi}")
    print(f"  structures to move   : {len(structures)} (from {KOTHI} to {LOT})")
    print(f"  longitude offset     : {dlon:+.14f} deg (two cells east)")
    print(f"  kothi households     : {p_kothi.get('households')}  "
          f"floor {p_kothi.get('floor_area_m2'):,.0f} m2  "
          f"pv {p_kothi.get('deployable_pv_kwp'):,.1f} kWp")
    print(f"  lot carport site     : {p_lot.get('is_carport_site')}")
    if not args.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(GEOJSON, BACKUP)
    print(f"\n  backup -> {os.path.basename(BACKUP)}")

    # 1. exchange parcel properties, keeping identity fields in place
    keep_lot = {k: p_lot[k] for k in KEEP if k in p_lot}
    keep_kothi = {k: p_kothi[k] for k in KEEP if k in p_kothi}
    new_lot = {k: v for k, v in p_kothi.items() if k not in KEEP}
    new_kothi = {k: v for k, v in p_lot.items() if k not in KEEP}
    feats[i_lot]["properties"] = {**new_lot, **keep_lot}
    feats[i_kothi]["properties"] = {**new_kothi, **keep_kothi}

    # 2. move the kothi footprints across, translating every coordinate
    def _shift(coords):
        if isinstance(coords[0], (int, float)):
            return [coords[0] + dlon] + list(coords[1:])
        return [_shift(c) for c in coords]

    for i in structures:
        sp = feats[i]["properties"]
        sp["row"], sp["col"] = LOT
        sp["cell_id"] = f"{LOT[0]:02d}_{LOT[1]:02d}"
        feats[i]["geometry"]["coordinates"] = _shift(
            feats[i]["geometry"]["coordinates"])
    print(f"  moved {len(structures)} structures and translated their geometry")

    with open(GEOJSON, "w", encoding="utf-8") as f:
        json.dump(gj, f)

    # 3. re-derive the position-dependent entrance sides for both cells
    from energy.network import grid_from_geojson
    from layout.entrance_assignment import entrance_sides_for_cell
    grid, _ = grid_from_geojson()
    with open(GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)
    feats = gj["features"]
    pidx = _parcel_index(feats)
    for rc in (LOT, KOTHI):
        cell = grid.at(*rc)
        sides = entrance_sides_for_cell(grid, cell)
        old = feats[pidx[rc]]["properties"].get("entrance_sides")
        feats[pidx[rc]]["properties"]["entrance_sides"] = sides
        for i, ft in enumerate(feats):
            sp = ft["properties"]
            if sp.get("role") == "structure" and (sp.get("row"), sp.get("col")) == rc:
                sp["entrance_sides"] = sides
        print(f"  entrance_sides {rc}: {old} -> {sides}")
    with open(GEOJSON, "w", encoding="utf-8") as f:
        json.dump(gj, f)

    print("\nWRITTEN. Now run the verification gates:")
    print("  PYTHONPATH=. python -u scripts/prk6_verify.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
