""" proof: the shading disk cache is BIT-EXACT, not merely close.

A shading table that is 1e-16 off would move PV yield, which moves the
headline, which moves every pin. So this does not test "approximately equal";
it tests that every one of the ~2,500 cell multipliers reloads with an
IDENTICAL float, and that the key set matches exactly.

Method: the cache-MISS path calls the real rasteriser, so comparing the value
returned on a MISS against the value read straight back off disk proves the
serialisation round-trip loses nothing. One compute, not two.

    PYTHONPATH=. python scripts/shading_cache_proof.py
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics
from energy.network import grid_from_geojson
from energy import shading_cache
from energy.solar_geometry import DEFAULT_RASTER_RES

LAT, LON = 30.64, 76.82

econ = load_economics(force_reload=True)
grid, layout = grid_from_geojson()
print("layout %s, raster_res %d" % (layout, DEFAULT_RASTER_RES), flush=True)

key = shading_cache.cache_key(grid, econ, LAT, LON, DEFAULT_RASTER_RES)
print("cache key %s" % key, flush=True)

# Force a clean MISS so the rasteriser really runs.
path = shading_cache._CACHE_DIR / (key + ".json")
if path.is_file():
    path.unlink()
    print("removed pre-existing entry to force a real compute", flush=True)

t0 = time.time()
live = shading_cache.compute_cached(grid, econ, LAT, LON)
t_miss = time.time() - t0
print("MISS path took %.1f s -> %d cells" % (t_miss, len(live)), flush=True)

t0 = time.time()
cached = shading_cache.compute_cached(grid, econ, LAT, LON)
t_hit = time.time() - t0
print("HIT  path took %.3f s -> %d cells" % (t_hit, len(cached)), flush=True)

print()
print("--- equality ---")
ok = True
if set(live) != set(cached):
    ok = False
    print("FAIL key sets differ: %d live vs %d cached"
          % (len(live), len(cached)))
else:
    print("key sets identical (%d cells)" % len(live))

worst = 0.0
nbad = 0
for k in live:
    a, b = live[k], cached[k]
    # bit-level comparison, not a tolerance
    if struct.pack("<d", a) != struct.pack("<d", b):
        nbad += 1
        worst = max(worst, abs(a - b))
if nbad:
    ok = False
    print("FAIL %d cells differ at the bit level, worst |delta| %.3e"
          % (nbad, worst))
else:
    print("all %d multipliers are BIT-IDENTICAL after the round trip" % len(live))

print()
print("speedup %.0fx (%.1f s -> %.3f s)"
      % ((t_miss / t_hit if t_hit > 0 else float("inf")), t_miss, t_hit))
print()
print("VERDICT:", "PASS - cache is safe to use" if ok else "FAIL - DO NOT USE")
sys.exit(0 if ok else 1)
