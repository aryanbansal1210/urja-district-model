"""CONFIG-CONSUMER AUDIT - find settings that do nothing.

WHY THIS EXISTS. On `farm_land_cells_by_period: {2030: 295,...}`
("Option A", to release the whole solar reserve in 2030) was
found to have NO EFFECT. The LP reads farm land from the LAYOUT'S expansion
tags, and `farm_land_cells_by_period` is consumed only by the STAMPER that
writes those tags - which had not been re-run since the decision. The config
said 295 ha; the model built 201. Nothing errored. It was caught only because
the author happened to ask for land per period and the arithmetic did not add up.

IT IS THE FOURTH OF ITS KIND IN THIS PROJECT:
  * `diesel_genset_emission_kgco2_per_kwh` - dead config since Stage C, BAU's
    genset CO2 invisible
  * `electrical_network.enabled` false AND its only consumer also false, so
    cables/substation/transformers were costed nowhere
  * BIPV / carport / floating PV capex learning looked up under the CHILD's own
    name, silently returning 1.0 (CAPEX-DERIVED,)
  * `farm_land_cells_by_period` - this one

A config value with no live consumer is invisible: it does not raise, it does
not warn, it just quietly does nothing while every document quotes it.

WHAT THIS CHECKS. Three classes, in increasing subtlety:

  CLASS A - NEVER REFERENCED. The key appears in YAML and nowhere in the Python.
            Straightforward dead config.
  CLASS B - REFERENCED ONLY BY NON-PRODUCTION CODE. The only references live in
            scripts/ or tests/, never in the production packages, so the value
            cannot reach a solve.
  CLASS C - WRITE-TIME ONLY (the class, and the one a grep misses).
            The only production consumer is a STAMPER that writes a FROZEN
            artifact. The value is live in principle but stale in fact whenever
            the artifact predates the config edit. Reported with both mtimes so
            the staleness is visible rather than inferred.

This is a REPORT, not a gate. Some hits are legitimate - documented fallbacks,
A/B comparators, back-compat defaults. The output is a worklist to read, not a
list of bugs.

Run from district_v3:
    PYTHONPATH=. python -u scripts/config_consumer_audit.py
"""
from __future__ import annotations

import os
import re
import sys
from typing import Dict, List, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

CONFIG_DIR = os.path.join(ROOT, "config")
PROD_PKGS = ("energy", "core", "layout")
OTHER_PKGS = ("scripts", "tests")
OUT = os.path.join(ROOT, "outputs", "verification",
                   "config_consumer_audit.txt")

# Modules that WRITE a frozen artifact rather than feed a solve. A key whose
# only production consumer is one of these is CLASS C.
STAMPERS = {
    "layout/phased_expansion.py": "outputs/geojson3d/optimised_sa.geojson",
    "layout/generator.py": "outputs/geojson3d/optimised_sa.geojson",
    "layout/optimiser.py": "outputs/geojson3d/optimised_sa.geojson",
    "layout/road_network.py": "outputs/geojson3d/optimised_sa.geojson",
    "layout/carport_siting.py": "outputs/geojson3d/optimised_sa.geojson",
    "layout/street_furniture.py": "outputs/geojson3d/optimised_sa.geojson",
    "layout/entrance_assignment.py": "outputs/geojson3d/optimised_sa.geojson",
    "layout/canal_corridor.py": "outputs/geojson3d/optimised_sa.geojson",
    "core/export_3d.py": "outputs/geojson3d/optimised_sa.geojson",
}

# Keys that are structural noise rather than tunable settings.
SKIP_KEYS = {
    "source", "sources", "note", "notes", "enabled", "name", "description",
    "url", "tier", "comment", "citation", "units", "unit",
}


def yaml_keys() -> Dict[str, List[Tuple[str, int]]]:
    """key -> [(file, line)]. Plain text scan: we want the KEY TOKENS as
    written, including keys nested anywhere, without imposing a schema."""
    out: Dict[str, List[Tuple[str, int]]] = {}
    pat = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")
    for fn in sorted(os.listdir(CONFIG_DIR)):
        if not fn.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(CONFIG_DIR, fn)
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if line.lstrip().startswith("#"):
                    continue
                m = pat.match(line)
                if not m:
                    continue
                k = m.group(1)
                if k in SKIP_KEYS or len(k) < 4:
                    continue
                out.setdefault(k, []).append((fn, i))
    return out


def py_sources(pkgs) -> Dict[str, str]:
    out = {}
    for pkg in pkgs:
        base = os.path.join(ROOT, pkg)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            if "__pycache__" in dirpath:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, ROOT).replace("\\", "/")
                # SELF-POLLUTION GUARD: this file's own docstring
                # names the keys it was written about (bound_by_surplus_not_
                # baseload, farm_land_cells_by_period, diesel_genset_emission_
                # kgco2_per_kwh, electrical_network.enabled). Without this, the
                # audit "finds a consumer" for every example it cites and
                # silently downgrades exactly the keys it exists to surface.
                if rel == "scripts/config_consumer_audit.py":
                    continue
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        out[rel] = f.read()
                except Exception:
                    pass
    return out


def _strip_comments(src: str) -> str:
    """Drop full-line comments so a key merely NAMED in a comment does not
    count as a consumer. This is the whole point - is discussed at
    length in comments while being read by nobody live."""
    return "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))


def main() -> int:
    keys = yaml_keys()
    prod = {k: _strip_comments(v) for k, v in py_sources(PROD_PKGS).items()}
    other = {k: _strip_comments(v) for k, v in py_sources(OTHER_PKGS).items()}

    # Raw sources too, so we can tell "absent" from "mentioned only in a
    # comment" - after this tool filed
    # `bound_by_surplus_not_baseload` under CLASS A. That was technically
    # right (a comment is not a consumer) but it buried the sharper signal:
    # the key appears in dispatch.py inside a comment describing behaviour
    # the code does not implement. ABSENT is untidy; COMMENT-ONLY is a
    # documented lie, and the more dangerous of the two.
    prod_raw = py_sources(PROD_PKGS)
    other_raw = py_sources(OTHER_PKGS)

    class_a: List[str] = []
    class_a_comment: List[Tuple[str, List[str]]] = []
    class_b: List[Tuple[str, List[str]]] = []
    class_c: List[Tuple[str, List[str]]] = []

    for key, where in sorted(keys.items()):
        tok = re.compile(r"\b" + re.escape(key) + r"\b")
        prod_hits = [f for f, src in prod.items() if tok.search(src)]
        other_hits = [f for f, src in other.items() if tok.search(src)]
        if not prod_hits and not other_hits:
            # does it appear ANYWHERE, i.e. only inside comments?
            raw_hits = [f for f, src in {**prod_raw, **other_raw}.items()
                        if tok.search(src)]
            if raw_hits:
                class_a_comment.append((key, sorted(raw_hits)[:4]))
            else:
                class_a.append(key)
        elif not prod_hits:
            class_b.append((key, sorted(other_hits)[:4]))
        else:
            stamper_only = all(f in STAMPERS for f in prod_hits)
            if stamper_only:
                class_c.append((key, sorted(prod_hits)))

    lines: List[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    emit("CONFIG-CONSUMER AUDIT")
    emit("Finds settings that cannot reach a solve. See LAND-A1 for why.")
    emit("=" * 78)
    emit(f"scanned {len(keys)} distinct config keys across {CONFIG_DIR}")
    emit()

    emit(f"CLASS A - NEVER REFERENCED IN ANY PYTHON  ({len(class_a)})")
    emit("  Dead unless something reads the YAML generically.")
    for k in class_a:
        loc = ", ".join(f"{f}:{ln}" for f, ln in keys[k][:2])
        emit(f"    {k:44s} {loc}")
    emit()

    emit(f"CLASS A* - MENTIONED ONLY INSIDE COMMENTS  ({len(class_a_comment)})")
    emit("  *** READ THESE FIRST. *** No code reads the key, but a comment")
    emit("  DESCRIBES it - i.e. someone documented behaviour that does not")
    emit("  exist. `bound_by_surplus_not_baseload` was found this way: the")
    emit("  config offers a strict-baseload PPA mode that cannot be selected.")
    for k, hits in class_a_comment:
        loc = ", ".join(f"{f}:{ln}" for f, ln in keys[k][:2])
        emit(f"    {k:44s} {loc}")
        emit(f"        comment in: {', '.join(hits)}")
    emit()

    emit(f"CLASS B - REFERENCED ONLY OUTSIDE energy/core/layout  ({len(class_b)})")
    emit("  Cannot reach a production solve.")
    for k, hits in class_b:
        emit(f"    {k:44s} -> {', '.join(hits)}")
    emit()

    emit(f"CLASS C - ONLY CONSUMER IS A STAMPER (the LAND-A1 class)  ({len(class_c)})")
    emit("  Live in principle, STALE IN FACT if the frozen artifact predates")
    emit("  the config edit. Compare the mtimes below.")
    for k, hits in class_c:
        emit(f"    {k}")
        cfgs = sorted({f for f, _ in keys[k]})
        for f in cfgs:
            p = os.path.join(CONFIG_DIR, f)
            emit(f"        config  {f:34s} mtime "
                 f"{__import__('time').strftime('%F %H:%M', __import__('time').localtime(os.path.getmtime(p)))}")
        for h in hits:
            art = STAMPERS.get(h)
            if art and os.path.exists(os.path.join(ROOT, art)):
                p = os.path.join(ROOT, art)
                emit(f"        stamper {h:34s} -> {art}")
                emit(f"        artifact mtime "
                     f"{__import__('time').strftime('%F %H:%M', __import__('time').localtime(os.path.getmtime(p)))}")
    emit()
    emit("=" * 78)
    emit("*** HOW TO READ THIS, after the first full triage (2026-08-14). ***")
    emit("")
    emit("CLASS A IS DOMINATED BY FALSE POSITIVES and is the LEAST useful list.")
    emit("This tool matches a key as a literal token, so it CANNOT see a key")
    emit("that is looked up dynamically. Confirmed live-but-flagged examples:")
    emit("  backbone_33kv_ug / dist_11kv_oh -> read via")
    emit("      .get('cable_capex_inr_per_km', {}).get(f'{tier}_ug')")
    emit("      i.e. the key is BUILT at runtime. These feed the Rs 93.5M/yr")
    emit("      internal-network line and are entirely live.")
    emit("  gov_ews / gov_public / phev / bicycle -> dict keys ITERATED over,")
    emit("      never named in code.")
    emit("Also legitimately unread: documented fallbacks (data_centre_offsite),")
    emit("A/B comparators, back-compat defaults, and DERIVED-TABLE INPUTS -")
    emit("values that exist so a human can re-derive a table (water_energy's")
    emit("decline/head/harvest inputs feed multiplier_by_period by hand).")
    emit("")
    emit("THE TWO CLASSES THAT ACTUALLY FOUND BUGS:")
    emit("  CLASS A* comment-only -> bound_by_surplus_not_baseload: the config")
    emit("      advertises a strict-baseload PPA mode that no code implements.")
    emit("  CLASS C stamper-only  -> the LAND-A1 shape: config edited, frozen")
    emit("      artifact never restamped, so the setting silently did nothing.")
    emit("A THIRD class this tool CANNOT detect at all: one key, two consumers,")
    emit("disagreeing (LAND-A1's rent-vs-capacity) or a stale hand-derived")
    emit("table (WATER-D1). Those need consistency ASSERTS, not a scan - see")
    emit("tests/test_land_consistency.py for the pattern.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
