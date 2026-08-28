""": make "Option A" real - release the whole solar reserve in 2030.

THE BUG. `economics.yaml` set `farm_land_cells_by_period: {2030: 295,...}`
 but the LP
never saw it. Farm land reaches the LP through the LAYOUT'S EXPANSION TAGS -
`energy/network.phased_land_multipliers`, whose docstring calls the tags "single
source of truth with the map". The config key is consumed only by
`layout/phased_expansion.py`, the stamper that WRITES those tags, and the frozen
layout was never restamped. So the model kept building the old phased schedule:

    2030   201 ha x 714 kWp/ha x 1.00 = 143,514.0 kWp
    2042   251 ha x 714 kWp/ha x 1.10 = 197,135.4 kWp
    2055   301 ha x 714 kWp/ha x 1.15 = 247,151.1 kWp

(the arithmetic matching to the decimal in all three periods is what proves the
tags, not the config, are binding).

AND A SECOND, INDEPENDENT BUG THE SAME KEY CAUSED. `farm_land_cells_by_period`
IS read in production - by `Economics.farm_land_rent_annual_inr`, for RENT. So
rent was charged on 295 ha while the LP could build on 201/251/301:

    2030  +94 ha rented but unusable  = Rs 23,500,000/yr paid for nothing
    2042  +44 ha                      = Rs 11,000,000/yr
    2055   -6 ha BUILT ON BUT NEVER RENTED  (the reverse error)

One number, two consumers, silently disagreeing. A grep-based config audit
cannot see this class - only a consistency assert can, which is why one is being
added alongside.

WHAT THIS SCRIPT DOES. Retags all 100 `solar_expansion_2042` / `_2055` cells to
`solar_expansion_2030`, so the whole reserve is unlocked in the base year.

WHY 301 AND NOT 295. The config's 295 assumed the 100 m solar-to-building buffer
would cost 6 cells. MEASURED on this layout: **zero** farm or expansion cells
touch a built cell on any of 8 sides, so no cells are lost and the true reserve
is 301 ha. `farm_land_cells_by_period` is set to 301 in the same change so rent
and capacity finally agree.

WHAT DOES NOT CHANGE. No cell changes `land_use`; the 100 cells stay
`open_space` carrying a tag, exactly as before. Only the tag's PERIOD moves.
Land-use counts, households, roads and the solar estate are untouched by
construction - the gates re-run anyway.

Run from district_v3:
    PYTHONPATH=. python -u scripts/land_a1_release_reserve.py           # dry run
    PYTHONPATH=. python -u scripts/land_a1_release_reserve.py --apply
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

GEOJSON = os.path.join(ROOT, "outputs", "geojson3d", "optimised_sa.geojson")
BACKUP = GEOJSON + ".bak.pre-land-a1"
NEW_TAG = "solar_expansion_2030"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)
    feats = gj["features"]

    tags = collections.Counter()
    targets = []
    for i, ft in enumerate(feats):
        p = ft["properties"]
        sub = p.get("amenity_subtype") or ""
        if sub.startswith("solar_expansion_"):
            tags[sub] += 1
            if p.get("role") == "parcel":
                targets.append(i)
    farm = sum(1 for ft in feats
               if ft["properties"].get("role") == "parcel"
               and ft["properties"].get("land_use") == "solar_farm")

    print("LAND-A1: release the whole solar reserve in 2030")
    print(f"  farm cells (already available 2030) : {farm}")
    print(f"  expansion tags found                : {dict(tags)}")
    print(f"  parcel features to retag            : {len(targets)}")
    print(f"  => land available in 2030 after     : {farm + len(targets)} ha "
          f"(was {farm} ha)")
    print(f"  => 2030 farm ceiling after          : "
          f"{(farm + len(targets)) * 714:,.0f} kWp (was {farm * 714:,.0f})")
    if not args.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(GEOJSON, BACKUP)
    print(f"\n  backup -> {os.path.basename(BACKUP)}")
    for i in targets:
        feats[i]["properties"]["amenity_subtype"] = NEW_TAG
    with open(GEOJSON, "w", encoding="utf-8") as f:
        json.dump(gj, f)
    print(f"  retagged {len(targets)} cells -> {NEW_TAG}")

    from energy.network import load_optimised_network, phased_land_multipliers
    net = load_optimised_network()
    mult = phased_land_multipliers(net.grid)["solar_farm"]
    print("\n  VERIFY - phased_land_multipliers now:")
    for y in sorted(mult):
        print(f"    {y}: x{mult[y]:.6f}  -> {farm * mult[y]:,.0f} ha  "
              f"-> {farm * mult[y] * 714:,.0f} kWp base")
    print("\n  NEXT: set economics.yaml farm_land_cells_by_period to 301 for")
    print("  all three periods so RENT matches CAPACITY, then re-pin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
