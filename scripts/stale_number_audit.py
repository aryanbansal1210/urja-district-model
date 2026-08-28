"""Find any place still quoting a superseded headline as if it were live.

WHY. This project has been bitten repeatedly by three sources disagreeing
while every one of them looked confident: sw.js advertising one pin, data.js
another and app.js a hardcoded third; CLAUDE.md sitting two re-pins stale and
producing a wrong in-session conclusion about solar thermal. A stale number
that is LABELLED stale is fine and is often required for the audit trail. A
stale number presented as current is the failure.

So this does not just grep. It classifies each hit by whether its surrounding
text marks it as historical, and reports only the ones that do not.

    python scripts/stale_number_audit.py
"""
from __future__ import annotations

import io
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent          # district_v3
PROJECT = ROOT.parent.parent                                    # PROJECT

# The live set, for reference in the report.
LIVE = {
    "cost": "1,841,569,555.79",
    "co2": "116,638,892.44",
    "vs_cost": "49.4567 %",
    "vs_co2": "62.5096 %",
}

# Superseded values, with the pin they belong to.
STALE = {
    "1,810,574,389": "town cost, 2026-08-15",
    "1,865,075,502": "town cost, 2026-08-17",
    "122,008,650": "town CO2, 2026-08-15",
    "126,368,241": "town CO2, 2026-08-17",
    "50.3074": "vs-BAU cost, 2026-08-15",
    "60.7836": "vs-BAU CO2, 2026-08-15",
    "48.8115": "vs-BAU cost, 2026-08-17",
    "59.3823": "vs-BAU CO2, 2026-08-17",
    "-48.8": "vs-BAU cost, 2026-08-17 (1dp)",
    "-59.4": "vs-BAU CO2, 2026-08-17 (1dp)",
    "126.4": "CO2 kt, 2026-08-17",
}

# A hit is treated as PROPERLY LABELLED if its context says so.
HISTORICAL = re.compile(
    r"(?i)supersed|histor|\bwas\b|prior|previous|retired|dead|stale|lineage|"
    r"before|deprecat|old |former|no longer|do not quote|2026-08-1[57]")

SKIP_PARTS = (".bak", "geojson3d", "__pycache__", "node_modules", ".git",
              "outputs/verification", "outputs/data", "_litrev_extracted",
              "/png/", "stale_number_audit")
EXTS = {".md", ".js", ".tex", ".py", ".yaml", ".yml", ".html", ".json", ".svg"}


DATED_NAME = re.compile(r"20\d{6}")          # e.g. STATE_20260817.md
BANNER = re.compile(
    r"(?i)supersed|historical|do not quote|discharged|append-only|"
    r"dated history|previous|retired")


# Reviewed and accepted. Each needs a REASON, so that adding to
# this list is a decision rather than a way to silence the check.
ACCEPTED = {
    "D5_development_timeline.svg":
        "legacy D-series figure; its whole folder carries a SUPERSEDED "
        "README and _captions.md warns not to publish it. Replaced by "
        "WRITEUP/figures/.",
    "test_energy_milp.py":
        "dated code comment recording the F5-flip measurement of 2026-08-17. "
        "It documents when a past test ran, not a current headline.",
}


def _is_snapshot(p: pathlib.Path, text: str) -> str:
    """Reasons the WHOLE file may quote old numbers legitimately.

    Three of them, and without these the audit reports 66 hits of which about
    60 are correct-by-design, which is how a checker gets ignored.
    """
    if p.name in ACCEPTED:
        return f"accepted: {ACCEPTED[p.name]}"
    if DATED_NAME.search(p.name):
        return "dated snapshot filename"
    head = "\n".join(text.splitlines()[:40])
    if BANNER.search(head):
        return "carries a superseded/historical banner"
    if p.name in {"LOGBOOK.md", "notes.md", "CODEX_HANDOFF.md",
                  "FINDINGS.md", "open_questions.md"}:
        return "append-only dated record"
    return ""


def _in_svg_path(text: str, idx: int) -> bool:
    """True if the match sits inside an SVG path/points list.

    "126.4" appears constantly as a path coordinate. Those are not numbers
    about the model at all.
    """
    a = text.rfind("<", 0, idx)
    b = text.rfind(">", 0, idx)
    if a < 0 or b > a:
        return False                      # not inside a tag at all
    tag = text[a:idx]
    return ' d="' in tag or " points=" in tag


def scan(roots):
    hits = []
    for root in roots:
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in EXTS:
                continue
            s = str(p).replace("\\", "/")
            if any(k in s for k in SKIP_PARTS):
                continue
            try:
                t = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            snap = _is_snapshot(p, t)
            for pat, label in STALE.items():
                for m in re.finditer(re.escape(pat), t):
                    if _in_svg_path(t, m.start()):
                        continue
                    a = max(0, m.start() - 110)
                    ctx = " ".join(t[a:m.start() + 60].split())
                    ok = bool(snap) or bool(HISTORICAL.search(ctx))
                    hits.append((p, label + (f"  [{snap}]" if snap else ""),
                                 ok, ctx))
    return hits


if __name__ == "__main__":
    # the corpus contains subscripts and dashes cp1252 cannot encode
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    roots = [ROOT, PROJECT / "WRITEUP"]
    hits = scan(roots)
    bad = [h for h in hits if not h[2]]

    print("LIVE SET (2026-08-19, chain GREEN 188/0):")
    for k, v in LIVE.items():
        print(f"   {k:<10} {v}")
    print()
    print(f"stale-number occurrences: {len(hits)}")
    print(f"  properly labelled as historical: {len(hits) - len(bad)}")
    print(f"  NOT labelled                   : {len(bad)}")
    print()

    if not bad:
        print("PASS - every superseded figure is marked as historical.")
        sys.exit(0)

    print("*** THESE READ AS CURRENT AND SHOULD NOT ***")
    seen = set()
    for p, label, _, ctx in bad:
        try:
            rel = p.relative_to(PROJECT)
        except ValueError:
            rel = p
        key = (str(rel), label)
        if key in seen:
            continue
        seen.add(key)
        print(f"\n{rel}")
        print(f"   [{label}]")
        print(f"   ...{ctx[-140:]}")
    sys.exit(1)
