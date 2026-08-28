"""Disk cache for the geometric PV-shading precompute.

WHY (the author, "why do we run shading precompute and other things
that are not gonna change? they take so long to run can we just save the data
and not run it?").

`solar_geometry.compute_geometric_shading` rasterises building shadows over a
sun-path integration for every PV-bearing cell. It costs ~320 s and it runs on
EVERY `EnergyNetwork.from_grid`, which means every solve, every script and
every test pays it again for a layout that has been FROZEN since.
CLAUDE.md already logs the damage: of a 7 h 39 m suite, ~3.1 h was four
carbon-alpha-sweep tests "all paying the uncached 320 s shading precompute
repeatedly".

The function is pure - same grid, same sun samples, same result - so it caches
cleanly. The only real risk is a STALE cache silently returning shading for a
layout or a code version that has moved, and PV yield is the headline result,
so a wrong table would corrupt everything downstream without warning. The key
therefore covers every input that can change the answer:

  * grid geometry   - per cell (row, col, land_use, has_building, height_m,
                      centre_x_m, centre_y_m); these are exactly the
                      attributes `solar_geometry` reads off a Cell
  * sun samples     - per slice (id, month, daypart, hours_per_year) and the
                      slice's pv_capacity_factor, i.e. everything
                      `_sun_samples` consumes
  * site + fidelity - latitude, longitude, raster_res
  * THE CODE ITSELF - sha256 of solar_geometry.py, so editing the algorithm
                      invalidates every entry without anyone remembering to

Miss, read error, or corrupt payload all fall through to a live recompute:
the cache can make things fast, it can never make them wrong. Set
DISTRICT_V3_NO_SHADING_CACHE=1 to bypass it entirely.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Tuple

_CACHE_DIR = Path(__file__).resolve().parent.parent / "outputs" / "cache" / "shading"
_ENV_DISABLE = "DISTRICT_V3_NO_SHADING_CACHE"


def _source_digest() -> str:
    """sha256 of the shading algorithm's own source."""
    try:
        src = Path(__file__).resolve().parent / "solar_geometry.py"
        return hashlib.sha256(src.read_bytes()).hexdigest()
    except Exception:
        # Cannot read the source -> cannot prove the cache matches the code.
        # Return a unique-ish marker so nothing is ever served from cache.
        return "SOURCE-UNREADABLE"


def _grid_digest(grid) -> str:
    h = hashlib.sha256()
    try:
        cells = sorted(grid.all_cells(), key=lambda c: (c.row, c.col))
    except Exception:
        return "GRID-UNREADABLE"
    for c in cells:
        lu = getattr(c, "land_use", None)
        lu = getattr(lu, "name", None) or str(lu)
        h.update(
            "|".join(
                (
                    str(c.row),
                    str(c.col),
                    lu,
                    str(bool(getattr(c, "has_building", False))),
                    repr(float(getattr(c, "height_m", 0.0) or 0.0)),
                    repr(float(getattr(c, "centre_x_m", 0.0) or 0.0)),
                    repr(float(getattr(c, "centre_y_m", 0.0) or 0.0)),
                )
            ).encode("utf-8")
        )
    return h.hexdigest()


def _econ_digest(econ) -> str:
    h = hashlib.sha256()
    try:
        for s in econ.slices:
            try:
                cf = float(econ.pv_capacity_factor(s.id))
            except Exception:
                cf = float("nan")
            h.update(
                "|".join(
                    (
                        str(s.id),
                        str(s.month),
                        str(s.daypart),
                        repr(float(s.hours_per_year)),
                        repr(cf),
                    )
                ).encode("utf-8")
            )
    except Exception:
        return "ECON-UNREADABLE"
    return h.hexdigest()


def cache_key(grid, econ, latitude_deg: float, longitude_deg: float,
              raster_res: int) -> str:
    parts = (
        "v1",
        _source_digest(),
        _grid_digest(grid),
        _econ_digest(econ),
        repr(float(latitude_deg)),
        repr(float(longitude_deg)),
        str(int(raster_res)),
    )
    return hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()


def load(key: str):
    """Return the cached table, or None on any miss/failure."""
    path = _CACHE_DIR / (key + ".json")
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            doc = json.load(fh)
        if doc.get("key") != key:
            return None
        out: Dict[Tuple[int, int], float] = {}
        for k, v in doc["values"].items():
            r, c = k.split(",")
            out[(int(r), int(c))] = float(v)
        if len(out) != int(doc.get("n", -1)):
            return None
        return out
    except Exception:
        return None


def store(key: str, table: Dict[Tuple[int, int], float]) -> bool:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / (key + ".json")
        tmp = path.with_suffix(".json.tmp")
        # repr-based float round-trip: json.dump uses repr, which is
        # shortest-round-trip in py3, so reload is bit-identical.
        doc = {
            "key": key,
            "n": len(table),
            "values": {"%d,%d" % (r, c): v for (r, c), v in table.items()},
        }
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.replace(str(tmp), str(path))
        return True
    except Exception:
        return False


def compute_cached(grid, econ, latitude_deg: float, longitude_deg: float,
                   raster_res=None, verbose: bool = True):
    """`compute_geometric_shading` with a keyed disk cache in front of it."""
    from .solar_geometry import compute_geometric_shading, DEFAULT_RASTER_RES

    res = DEFAULT_RASTER_RES if raster_res is None else raster_res

    if os.environ.get(_ENV_DISABLE):
        return compute_geometric_shading(grid, econ, latitude_deg,
                                         longitude_deg, res)

    key = cache_key(grid, econ, latitude_deg, longitude_deg, res)
    hit = load(key)
    if hit is not None:
        if verbose:
            print("[shading] cache HIT %s (%d cells)" % (key[:12], len(hit)),
                  flush=True)
        return hit

    if verbose:
        print("[shading] cache MISS %s - computing..." % key[:12], flush=True)
    table = compute_geometric_shading(grid, econ, latitude_deg,
                                      longitude_deg, res)
    ok = store(key, table)
    if verbose:
        print("[shading] cached %d cells (%s)"
              % (len(table), "written" if ok else "WRITE FAILED"), flush=True)
    return table
