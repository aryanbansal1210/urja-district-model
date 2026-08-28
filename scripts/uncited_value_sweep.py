"""FIND CONFIG VALUES WITH NO SOURCE AT ALL.

WHY THIS EXISTS. Three uncited numbers have been found WRONG in three days:
  cooling elasticity's "AEEE/CEEW 8-12 %/C band" - FABRICATED,
              the report contains zero occurrences of "elasticity".
  water-table decline "CGWB 0.49 m/yr" - RETRACTED.
  solar farm `ground_mount_kwp_per_m2: 0.10` - 2.47 acres/MWdc
              against an Indian norm of 4-5 acres/MW. NO citation at all.

The existing tooling cannot catch these:
  * citation_link_audit.py checks that URLs RESOLVE - it only sees values
    that already have a URL.
  * the 125-source register is built by SCRAPING LINKS out of comments, so a
    value with no link was never in the audited population in the first
    place.
That is a structural blind spot: THE AUDIT COULD ONLY EVER FIND PROBLEMS IN
THE THINGS THAT WERE ALREADY CITED.

WHAT THIS DOES. For every numeric scalar in the config YAMLs, read the
comment block attached to it (the run of comment lines immediately above,
plus any trailing inline comment) and classify:
    CITED       - a URL is present in the block
    NAMED_ONLY  - a source is named (Tier n / "per X" / "source:") but no URL
    UNSOURCED   - neither
UNSOURCED is the dangerous class and is what this prints first.

It is a TRIAGE tool, not a verdict: plenty of unsourced values are
structural (flags, counts, indices) and need no citation. The output is a
worklist to read, ranked so the load-bearing ones surface first.

Run:  python -u scripts/uncited_value_sweep.py [--all]
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["config/economics.yaml", "config/demand_norms.yaml",
         "config/district_composition.yaml"]

URL = re.compile(r"https?://")
NAMED = re.compile(r"\b(tier\s*[1-4]|source\s*:|per\s+[A-Z]|CEA|MNRE|PSERC|"
                   r"CGWB|BEE|CEEW|IEA|NREL|IRENA|BNEF|URDPFI|IPHS|CPHEEO|"
                   r"SECI|PSPCL|PEDA|ITRPV|Fraunhofer|census|IS\s?\d)",
                  re.IGNORECASE)
# Keys whose value materially drives capacity, demand, cost or emissions.
# Matched as substrings; deliberately broad, then hand-triaged.
LOADBEARING = re.compile(
    r"kwp|kw_e|kwh|efficiency|density|per_m2|per_capita|per_km|per_ha|"
    r"fraction|factor|multiplier|ratio|tariff|inr|cost|capex|opex|price|"
    r"emission|kgco2|lifetime_years|discount|rate|share|uptake|acceptance|"
    r"hours|lpcd|w_per_m2|elasticity|loss", re.IGNORECASE)
SKIP_KEY = re.compile(r"^(enabled|id|name|label|mode|colour|color|type|"
                      r"comment|note|source|url|status)$", re.IGNORECASE)
NUMERIC = re.compile(r"^\s*([a-z0-9_]+)\s*:\s*(-?\d+\.?\d*(?:e-?\d+)?)\s*(#.*)?$",
                     re.IGNORECASE)


def sweep(path):
    out = []
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    for i, line in enumerate(lines):
        m = NUMERIC.match(line)
        if not m:
            continue
        key, val, inline = m.group(1), m.group(2), (m.group(3) or "")
        if SKIP_KEY.match(key):
            continue
        # Walk backwards to the start of the ENCLOSING TOP-LEVEL SECTION,
        # collecting every comment line on the way. A citation in this
        # project is usually written once at the head of a section and the
        # values beneath inherit it - reading only the contiguous comment
        # block directly above a value reports those as unsourced when they
        # are not. (First version of this script did exactly that and
        # claimed 78.7% unsourced, which is wrong: `capex_inr_per_mva`, for
        # one, has its TGSPDCL URL at the head of `electrical_network`.)
        # v3 fix: the section HEADER comment block sits ABOVE the top-level
        # key, not below it. v2 stopped AT the key and so threw the header
        # away - which is where this project actually writes its citations
        # (the whole `dynamic_tariff` stack has IEX/CERC/PSERC URLs in the
        # header and v2 reported every value under it as UNSOURCED).
        # Walk to the section key, then KEEP GOING through the contiguous
        # comment header above it.
        # v4 fix: a citation is sometimes written on the lines BELOW the
        # value it justifies (`ews_social_tariff_inr_per_kwh: 3.0` is
        # followed by "Anchor: SECI RESCO model L1 ~Rs 2.97/kWh"). v3 only
        # looked upward and reported it as unsourced. Read the trailing
        # comment run too.
        block = [inline]
        k = i + 1
        while k < len(lines) and lines[k].strip().startswith("#"):
            block.append(lines[k])
            k += 1
        j = i - 1
        hit_key = False
        while j >= 0:
            prev = lines[j]
            stripped = prev.strip()
            if stripped.startswith("#"):
                block.append(prev)
            elif stripped and not prev.startswith((" ", "\t")):
                if hit_key:
                    break               # a second top-level key: stop
                block.append(prev)
                hit_key = True          #...then keep reading its header
            elif not stripped and hit_key:
                break                   # blank line above the header block
            j -= 1
        text = "\n".join(block)
        if URL.search(text):
            cls = "CITED"
        elif NAMED.search(text):
            cls = "NAMED_ONLY"
        else:
            cls = "UNSOURCED"
        out.append((cls, path, i + 1, key, val,
                    bool(LOADBEARING.search(key)), len(block) - 1))
    return out


def main():
    show_all = "--all" in sys.argv
    rows = []
    for f in FILES:
        rows.extend(sweep(f))
    tally = {}
    for c, *_ in rows:
        tally[c] = tally.get(c, 0) + 1
    print("=" * 78)
    print("UNCITED VALUE SWEEP")
    print("=" * 78)
    tot = len(rows)
    for c in ("CITED", "NAMED_ONLY", "UNSOURCED"):
        n = tally.get(c, 0)
        print(f"  {c:<12} {n:>5}   {100 * n / max(tot, 1):>5.1f}%")
    print(f"  {'TOTAL':<12} {tot:>5}")

    uns = [r for r in rows if r[0] == "UNSOURCED" and r[5]]
    print(f"\n{'=' * 78}")
    print(f"UNSOURCED **AND LOAD-BEARING**: {len(uns)}")
    print("  (no URL, no named source, and the key name says it drives a")
    print("   capacity / demand / cost / emissions number. READ THESE.)")
    print("=" * 78)
    print(f"{'file':<34}{'line':>6}  {'key':<44}{'value':>14}{'cmt':>5}")
    for _, path, ln, key, val, _, nc in sorted(uns, key=lambda r: (r[1], r[2])):
        print(f"{os.path.basename(path):<34}{ln:>6}  {key:<44}{val:>14}{nc:>5}")

    named = [r for r in rows if r[0] == "NAMED_ONLY" and r[5]]
    print(f"\nNAMED_ONLY and load-bearing: {len(named)}"
          f"   (a source is named but no URL - the class that hid the")
    print("   fabricated AEEE band and the retracted CGWB figure)")
    if show_all:
        for _, path, ln, key, val, _, nc in sorted(named,
                                                   key=lambda r: (r[1], r[2])):
            print(f"  {os.path.basename(path):<30}{ln:>6}  {key:<42}{val:>14}")
    else:
        print("   re-run with --all to list them")


if __name__ == "__main__":
    main()
