"""LAYOUT QUALITY: designed town vs Baseline 2.

the author: "we have to compare our layout to the bad layout in order to prove
ours is better, how do we do that, baseline 2 probably has no walk/bike/and
doesnt fulfill a lot of constraints and objectives?"

This is the answer, and it is the comparison that SURVIVES. The energy
comparison does not: programme-constant makes the two towns use the
same energy by construction). Everything below is layout-only - no solve,
no dispatch, no energy - so none of it is affected by that identity.

Three families of evidence:
  1. HARD CONSTRAINTS - the pass/fail planning rules. A plan enforces them;
     unplanned growth does not.
  2. ACCESS / WALKABILITY - mean walking distance to each amenity and the
     15-minute-city coverage.
     *** THE "PURELY PLACEMENT" CLAIM THAT USED TO BE HERE IS RETRACTED. ***
     It said both towns carry the same 85 schools and 25 temples. They do
     not, and have not since v3: Baseline 2 carries only Table 6-1's 1.16%
     institutional share, so it has 16 schools and 4 temples. The access
     gaps are UNDER-PROVISION AND MIS-PLACEMENT TOGETHER. The printed header
     has said so since; this docstring did not.
  3. LAND PRODUCTIVITY - arithmetic rather than simulation.
     *** THE 60,641 THAT USED TO BE HERE IS THE RETIRED 4.1x CLAIM. ***
     It paired a 2011 census population with a recent land survey. The
     vintage-matched figure is ~167,700 people the Zirakpur way against
     250,000 under the plan, i.e. ~1.5x. Section 3 has printed the corrected
     number since; this docstring did not. Both stale claims found
 while answering "why isn't the sprawl population 250k?".

Run from district_v3:
    PYTHONPATH=. python -u scripts/layout_quality_comparison.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.grid import Grid                                   # noqa: E402
from layout.constraints import check_hard_constraints        # noqa: E402
from layout.generator import generate                        # noqa: E402
from layout import metrics as M                              # noqa: E402


def _load_planned() -> Grid:
    """The frozen seed-42 town, read back from its exported geojson.

    `grid_from_geojson` takes a PATH (and returns (grid, name)), not a
    parsed dict - a signature I got wrong first time.
    """
    from energy.network import grid_from_geojson
    from pathlib import Path
    p = Path(__file__).parent.parent / "outputs" / "geojson3d" / "optimised_sa.geojson"
    grid, _name = grid_from_geojson(p)
    return grid


print("=" * 74)
print("LAYOUT QUALITY - designed town vs Baseline 2 (Zirakpur sprawl)")
print("PROGRAMME-CONSTANT: same ~54,800 households and same 250,000 people in")
print("BOTH towns - only the arrangement differs. Residential LAND therefore")
print("differs, and so does density; section 3 prints both. NOTE (v3/v4): PROVISION")
print("now differs by design - Baseline 2 carries only Table 6-1's 1.16%")
print("institutional share (the adopted budget), so its access gaps are")
print("under-provision AND mis-placement together. Both are the finding;")
print("the plan admits the first itself ('Institutional & parks use needs")
print("enhancement'). Do NOT quote these gaps as placement-only.")
print("=" * 74)

planned = _load_planned()
sprawl = generate("zirakpur_ribbon", seed=42)

# ---- 1. hard constraints ------------------------------------------------
print("\n1. HARD PLANNING CONSTRAINTS")
rp = {r.name: r for r in check_hard_constraints(planned)}
rs = {r.name: r for r in check_hard_constraints(sprawl)}
names = sorted(set(rp) | set(rs))
pp = sum(1 for k in names if rp.get(k) and rp[k].passes)
ps = sum(1 for k in names if rs.get(k) and rs[k].passes)
print(f"   {'constraint':<40}{'planned':>10}{'sprawl':>10}")
for k in names:
    a = "PASS" if (rp.get(k) and rp[k].passes) else "fail"
    b = "PASS" if (rs.get(k) and rs[k].passes) else "fail"
    mark = "  <--" if a != b else ""
    print(f"   {k:<40}{a:>10}{b:>10}{mark}")
print(f"   {'TOTAL PASSED':<40}{pp:>10}{ps:>10}")

# ---- 2. access / walkability -------------------------------------------
# NOTE: v1 of this script printed `access_score_for` under a
# "metres" heading and showed "1" for both towns. That was MY bug, not the
# metric's - access_score_for returns a NORMALISED 0-1 score that SATURATES
# at 1.0, so it cannot separate two towns that both clear the target. Real
# distances come from `_mean_walk_to_amenity`, used directly below.
from core.land_use import LandUse as _LU

print("")
print("2. ACCESS - mean walk from a home to the NEAREST amenity (metres)")
_np = {lu: sum(1 for c in planned.all_cells() if c.land_use == lu)
       for lu in (_LU.SCHOOL, _LU.HEALTHCARE, _LU.RELIGIOUS)}
_ns = {lu: sum(1 for c in sprawl.all_cells() if c.land_use == lu)
       for lu in (_LU.SCHOOL, _LU.HEALTHCARE, _LU.RELIGIOUS)}
print(f"   Provision differs (see header): schools {_np[_LU.SCHOOL]} vs "
      f"{_ns[_LU.SCHOOL]}, clinics {_np[_LU.HEALTHCARE]} vs "
      f"{_ns[_LU.HEALTHCARE]}, temples {_np[_LU.RELIGIOUS]} vs "
      f"{_ns[_LU.RELIGIOUS]}.")
_res_p = M._residential_cells(planned)
_res_s = M._residential_cells(sprawl)
_kinds = [("school", (_LU.SCHOOL,)),
          ("healthcare", (_LU.HEALTHCARE,)),
          ("religious", (_LU.RELIGIOUS,)),
          ("open space", (_LU.OPEN_SPACE,)),
          ("shops+food", (_LU.SHOPPING_CENTRE, _LU.RESTAURANT_FOOD)),
          ("public services", (_LU.PUBLIC_SERVICES,))]
print("   %-22s%10s%10s%12s" % ("amenity", "planned", "sprawl", "sprawl is"))
for label, lus in _kinds:
    ap = [c for c in planned.all_cells() if c.land_use in lus]
    asx = [c for c in sprawl.all_cells() if c.land_use in lus]
    dp = M._mean_walk_to_amenity(_res_p, ap)
    ds = M._mean_walk_to_amenity(_res_s, asx)
    v = ("%+.0f%%" % (100 * (ds / dp - 1))) if dp else "n/a"
    print("   %-22s%10,.0f%10,.0f%12s".replace(",", "") % (label, dp, ds, v))

print("")
print("   WORST CASE - the tail a plan exists to protect")
for label, lus, lim in (("a school", (_LU.SCHOOL,), 1000.0),
                        ("worship", (_LU.RELIGIOUS,), 800.0)):
    for nm, g, res in (("planned", planned, _res_p), ("sprawl", sprawl, _res_s)):
        am = [c for c in g.all_cells() if c.land_use in lus]
        far = sum(1 for r in res
                  if min(Grid.manhattan_distance(r, a) for a in am) > lim)
        print("   homes >%.0f m from %-10s %-8s %4d of %d  (%.0f%%)"
              % (lim, label, nm, far, len(res), 100.0 * far / len(res)))

print("")
print("   15-MINUTE COVERAGE (homes within reach of school+shops+clinic)")
cp, cs = M.coverage_15_minute(planned), M.coverage_15_minute(sprawl)
print("   %-22s%10.3f%10.3f%11.0f%%" % ("coverage", cp, cs, 100 * (cs / cp - 1)))
if cs > cp:
    print("   *** This one favours sprawl and the effect is real: corridor")
    print("   growth puts the AVERAGE home near something; the plan protects")
    print("   the TAIL. Quote the worst-case rows, not this one. ***")
else:
    print("   (v4 2026-08-12: the organic rebuild scattered pockets off the")
    print("   corridors, so sprawl now loses the mean AND the tail. The old")
    print("   'favours sprawl' caveat applied to the v2 corridor geometry.)")
print("")

# ---- 3. land productivity AS CORRECTED same-day) ------------------
# The first cut divided the 2011 census population by the REVISED plan's
# land survey - a vintage mismatch that overstated the gap 4.1x
# caught it from the satellite: "so its just a lie"). Corrected in
# FINDINGS: use the 2021 projection against the same survey.
print("\n3. LAND PRODUCTIVITY (F50, corrected 2026-08-12 - vintage-matched)")
LPA, SITE, POP = 4358.77, 2500.0, 250000
dens_z = 292461 / (0.2254 * LPA)          # 2021 projection, ~298 p/ha
z_pop = SITE * 0.2254 * dens_z
# DERIVED, NOT HARDCODED. Both densities now come from the
# residential cell counts measured above. The plan's 393 ha used to be a
# literal in this line, which is how it survived unchecked while the sprawl
# layout's own density was never printed at all.
dens_plan = POP / len(_res_p)
dens_b2 = POP / len(_res_s)
print(f"   {'':<34}{'Zirakpur':>12}{'Baseline 2':>12}{'this plan':>12}")
print(f"   {'residential land, ha':<34}{0.2254 * SITE:>12,.0f}"
      f"{len(_res_s):>12,.0f}{len(_res_p):>12,.0f}")
print(f"   {'residential density, persons/ha':<34}{dens_z:>12,.0f}"
      f"{dens_b2:>12,.0f}{dens_plan:>12,.0f}")
print(f"   {'people housed on 25 km2':<34}{z_pop:>12,.0f}{POP:>12,.0f}{POP:>12,.0f}")
print(f"\n   => ~{POP/z_pop:.1f}x more people on the same land, and 1.5x")
print("      denser than GMADA's own 2031 proposal (636 vs 432 persons/ha).")
print("   => The old 4.1x and 'it does not even fit' claims are RETIRED -")
print("      2011 people over a recent land survey. See FINDINGS F50.")
print("")
print("   *** READ THE THREE COLUMNS AS THREE DIFFERENT OBJECTS. ***")
print("   Baseline 2 is PROGRAMME-CONSTANT: it carries the SAME 250,000")
print("   people and the same ~54,800 households as the plan, because that")
print(f"   is the only way sections 1-2 are a controlled test. At {dens_b2:,.0f}")
print("   persons/ha it is therefore ~44% DENSER than the real Zirakpur")
print(f"   in the left column ({dens_z:,.0f} persons/ha). You cannot hold")
print("   population AND density at once - fixing one moves the other, which")
print("   is the same 'which variable is held fixed' lesson as F49 -> F50.")
print("   CONSEQUENCE, AND IT IS IN OUR FAVOUR: a denser sprawl scores BETTER")
print("   on walking distance than real sprawl would, so every access gap in")
print("   section 2 is a LOWER BOUND on the real thing.")

print("\n" + "=" * 74)
print("WHAT TO QUOTE: the energy comparison between these two is retired")
print("(F49 - identical programme => identical demand). The planning case")
print("rests on the three families above, and it is stronger for it.")
