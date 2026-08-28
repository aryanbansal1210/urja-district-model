"""NAMED-BUT-UNLINKED SOURCE SWEEP.

The uncited sweep found 90 load-bearing values that NAME a source but give no
URL. That is the dangerous class, not the unsourced one: a named institution
LOOKS verified. It is exactly what produced all three retractions:

  AEEE/CEEW cooling-elasticity band  - the report contains no such band
  CGWB 0.49 m/yr water-table decline - retracted
  TERI-ETC rooftop PV CAPEX path     - no such publication exists

Each was a real organisation, a plausible number, and no document.

WHAT THIS DOES. For every organisation named next to a numeric value, ask the
one question that separates a citation from a memory:

    does this organisation appear ANYWHERE in the config with a URL?

  LINKED_ELSEWHERE - yes. The value inherits a real, checkable document; the
                     citation is merely not adjacent. Low risk, tidy later.
  PROSE_ONLY       - no. This organisation is named in this project and never
                     once linked. THAT IS THE RETRACTION SIGNATURE. Read it.

PROSE_ONLY is not proof of fabrication - plenty of real figures get typed from
a paper without pasting the link. It IS the population all three retractions
came from, and it is small enough to check by hand.

Run:  python -u scripts/named_source_sweep.py
"""
from __future__ import annotations

import os
import re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["config/economics.yaml", "config/demand_norms.yaml",
         "config/district_composition.yaml"]

ORGS = ["AEEE", "CEEW", "CGWB", "TERI", "BNEF", "MNRE", "CEA", "PSERC",
        "PSPCL", "PEDA", "SECI", "CERC", "IEX", "NREL", "IRENA", "IEA",
        "ITRPV", "Fraunhofer", "URDPFI", "IPHS", "CPHEEO", "BEE", "CPCB",
        "TGSPDCL", "LBNL", "Prayas", "Mercom", "CII", "NITI", "Census",
        "PVPS", "ecoinvent", "UCS", "Dubey", "PVGIS", "NASA", "GSA",
        "eMARC", "WEF", "Bain", "Petri", "Caldeira", "PNAS", "TPDDL"]

LINKISH = re.compile(r"https?://|doi:|doi\.org|10\.\d{4}/", re.I)
NUMERIC = re.compile(r"^\s*([a-z0-9_]+)\s*:\s*(-?\d+\.?\d*)\s*(#.*)?$", re.I)
LOADBEARING = re.compile(
    r"kwp|kw_e|kwh|efficiency|density|per_m2|per_capita|per_km|per_ha|"
    r"fraction|factor|multiplier|ratio|tariff|inr|cost|capex|opex|price|"
    r"emission|kgco2|lifetime_years|discount|rate|share|uptake|acceptance|"
    r"hours|lpcd|w_per_m2|elasticity|loss", re.I)


def main():
    # 1. which orgs ever appear ON a line that also carries a URL?
    linked = set()
    corpus = {}
    for f in FILES:
        txt = open(os.path.join(ROOT, f), encoding="utf-8").read()
        corpus[f] = txt.split("\n")
        for line in corpus[f]:
            # A DOI is a citation. Dubey 2017 carries
            # doi:10.1002/ese3.150 and no http, and v1 of this
            # script called it prose-only. It is not.
            if not LINKISH.search(line):
                continue
            for o in ORGS:
                if re.search(rf"\b{re.escape(o)}\b", line, re.I):
                    linked.add(o.upper())
    # an org is also "linked" if a URL sits within 3 lines of its mention
    for f, lines in corpus.items():
        for i, line in enumerate(lines):
            for o in ORGS:
                if o.upper() in linked:
                    continue
                if re.search(rf"\b{re.escape(o)}\b", line, re.I):
                    window = "\n".join(lines[max(0, i - 2):i + 4])
                    if LINKISH.search(window):
                        linked.add(o.upper())

    print("=" * 78)
    print("NAMED-SOURCE SWEEP - is each named organisation ever LINKED?")
    print("=" * 78)
    prose = [o for o in ORGS if o.upper() not in linked]
    print(f"\nLINKED at least once ({len(ORGS) - len(prose)}):")
    print("  " + ", ".join(sorted(o for o in ORGS if o.upper() in linked)))
    print(f"\n*** PROSE-ONLY - named in this project, NEVER linked "
          f"({len(prose)}) ***")
    print("  " + (", ".join(sorted(prose)) if prose else "(none)"))
    print("\n  This is the retraction signature. AEEE, CGWB and TERI were all")
    print("  in this class before they were checked and withdrawn.")

    # 2. which load-bearing values sit next to a prose-only org?
    if not prose:
        return
    hits = defaultdict(list)
    for f, lines in corpus.items():
        for i, line in enumerate(lines):
            m = NUMERIC.match(line)
            if not m or not LOADBEARING.search(m.group(1)):
                continue
            block = "\n".join(lines[max(0, i - 25):i + 4])
            if LINKISH.search(block):
                continue
            for o in prose:
                if re.search(rf"\b{re.escape(o)}\b", block, re.I):
                    hits[o].append((os.path.basename(f), i + 1,
                                    m.group(1), m.group(2)))
    print(f"\n{'=' * 78}")
    print("LOAD-BEARING VALUES RESTING ON A PROSE-ONLY SOURCE")
    print("=" * 78)
    if not hits:
        print("  none - the prose-only orgs are named in narrative only.")
    for o in sorted(hits, key=lambda k: -len(hits[k])):
        print(f"\n  {o}  ({len(hits[o])} value(s))")
        for fn, ln, key, val in hits[o][:12]:
            print(f"      {fn:<28}{ln:>6}  {key:<40}{val:>12}")


if __name__ == "__main__":
    main()
