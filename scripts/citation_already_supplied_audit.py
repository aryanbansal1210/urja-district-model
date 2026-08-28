"""CPHEEO-CLASS AUDIT: which unverified citations are already substantiated in place?

THE QUESTION, AND WHY IT IS THE RIGHT ONE (the author, "just like how
cpheeo is done, check if any of the others done too").

CPHEEO looked like an audit failure. Its URL is dead and it sat on the
not-claim-verified list for weeks. But the config does not merely LINK to the
manual - it names the edition ("Manual on Water Supply and Treatment, THIRD
EDITION, MAY 1999") and reproduces Chapter 13's pump relation
`P = Q.H / (367. eta)`. Nobody writes that from a search result. The document
had been opened; only the link had rotted.

So the register's CLAIM column measures the wrong thing for a whole class of
entries. It records "has someone written a verification entry", not "is the
claim substantiated". This script finds the gap: citations with NO claim
verification whose surrounding comment nevertheless carries hard evidence that
the document was in front of whoever wrote it.

WHAT COUNTS AS EVIDENCE. Only things you cannot produce from a search-engine
snippet:

  QUOTE      a verbatim quotation, or the word "verbatim"
  STRUCTURE  a pointer INTO the document - Table / Chapter / Section / Clause /
             Regulation / Annex / page number / figure number
  EDITION    a named edition, volume or revision
  LOCAL      a copy held in the repo, or the words extracted / parsed /
             downloaded / supplied
  DERIVED    the source's own relation reproduced, or an explicit statement
             that the value was rebuilt from first principles
  CHECKED    explicit verification language - VERIFIED / confirmed / reproduces

COUNTER-EVIDENCE is tracked too, because a comment saying "NOT FOUND" or
"unsourced" is the opposite of the CPHEEO case and must not be promoted.

WHAT THIS DOES NOT DO. It does not verify anything. It produces a RANKED
SHORTLIST of entries that are probably already defensible, so a human reads
those rather than re-chasing dead URLs. An entry scoring high here still needs
its verification note written before the register can be changed.

Run from district_v3 (seconds, read-only):
    PYTHONPATH=. python -u scripts/citation_already_supplied_audit.py
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "_spec" / "CITATION_REGISTER.md"
OUT = ROOT / "_spec" / "CITATION_ALREADY_SUPPLIED_20260817.md"

# Hard bounds on the comment block walk. The block itself is found by walking
# outward while the lines are still comments; these only stop a runaway.
# A FIXED WINDOW WAS TRIED FIRST AND WAS WRONG: config comment blocks run to
# dozens of lines, so a fixed 45-line reach bled into NEIGHBOURING citations and
# credited one block with the evidence of another. The walk stops at the first
# non-comment line, which is the real boundary between two cited values.
MAX_UP = 90
MAX_DOWN = 25

# CHECKED AND FAILED - AND THIS CLASS IS THE REASON THE SCRIPT EXISTS AT ALL.
# Some notes record that the document WAS opened and DOES NOT support the
# claim: "THE PER-CAPITA FIGURE IS NOT IN THIS DOCUMENT", "WRONG DOCUMENT FOR
# THE CLAIM", "COINCIDENTAL NUMBER MATCH - THE UNITS ARE DIFFERENT". Those read
# to the same regex as a successful verification, because both say "downloaded
# and parsed in full". The first draft of this script promoted three of them as
# already-verified, which is the exact error the CPHEEO exercise was meant to
# avoid, running backwards.
# THE REGISTER CANNOT DISTINGUISH THEM EITHER. A CLAIM column of "-" means
# "never checked" and "checked and DISPROVED" alike, and the second is an
# active defect while the first is only a gap. This class must be tested FIRST,
# before any promotion.
CHECKED_AND_FAILED = (
    r"IS NOT IN THIS DOCUMENT|is not in this document|WRONG DOCUMENT|"
    r"COINCIDENTAL NUMBER MATCH|ZERO hits|zero hits|does not contain|"
    r"NOT FOUND in|not present in the|found not to contain|"
    r"THE BAND DOES NOT EXIST|contains no|carries no"
)

# AND E MUST BE SPLIT IN TWO, BECAUSE THE TWO HALVES MEAN OPPOSITE THINGS.
# "zero hits" after parsing a 107-page PDF means the claim is not in the
# document. "zero hits" after a fetch returned 508 characters of site chrome
# from a JavaScript-rendered storefront means THE FETCH SAW NOTHING - the claim
# is unresolved, not disproved. Reporting the second as a disproof would be a
# false accusation against a source that may be perfectly good.
FETCH_FAILURE = (
    r"JavaScript|javascript|rendered text|site chrome|"
    r"rendering to \d|characters of rendered|HTML rendering|"
    r"login prompt|blocks or throttles"
)

# THE STRONGEST SIGNAL OF ALL, AND IT WAS FOUND BY ACCIDENT.
# Several register NOTES already record, in plain words, that the document was
# opened and the attributed figure found in it - "THE DOCUMENT IS REAL AND
# CONTAINS THE EXACT LINE ITEM CITED", "present verbatim", "VERIFIED EXACT
# against the gazette" - while the row's CLAIM column still reads "-". The
# verification WAS done; the column was never ticked. That is bookkeeping, not
# research, and it is the cheapest win in the whole audit.
NOTE_RECORDS_VERIFICATION = (
    r"CONTAINS THE EXACT|contains the exact|present verbatim|"
    r"VERIFIED EXACT|verified exact|confirmed verbatim|"
    r"opened and parsed|downloaded and parsed|parsed in full|"
    r"Verbatim from this (?:page|report|document)|"
    r"reproduces exactly|found in the document|verified directly from"
)

# A LOCAL COPY IS THE STRONGEST SIGNAL AND IT GETS ITS OWN CLASS.
# If the document or its data sits in the repo, the URL is an access path and
# nothing more - verification means opening the local file. This is the exact
# CPHEEO situation and it is not a matter of degree, so it is matched
# separately rather than scored.
# NOTE `outputs/` IS DELIBERATELY ABSENT. It was in the first draft and it
# produced false positives: `outputs/` holds MODEL RESULTS, not source
# documents, and any long comment mentioning an artifact scored as though the
# `PROJECT/DATA`, nowhere else.
HELD_LOCALLY = (
    r"_spec/sources/|PROJECT[/\\ ]DATA|\.\./DATA/|\.\.[/\\]DATA|"
    r"held (?:locally|in the repo)|retained as the workbook|workbook in|"
    r"data held locally|lives in the repo"
)

# The block itself says no model number depends on this source.
NOT_LOAD_BEARING = (
    r"Tier[- ]?3 declared|declared Tier[- ]?3|no longer load-bearing|"
    r"corroborat|cross-check only|not read by any code|ZERO reads|"
    r"NOT read by the model|recorded but NOT read|no parameter attached|"
    r"rebuilt from first principles|independently rebuilt|"
    r"Tier 3 adaptation|method(?:ological)? citation|enabled: false"
)

# Quotes in these comments are as often. A
# quotation only counts as document evidence if it is not attributed to him.
ARYAN_QUOTE = r"\(?Aryan[^)\n]{0,40}[:,]?\s*[\"“]"

# (name, weight, regex)
MARKERS: Tuple[Tuple[str, int, str], ...] = (
    ("QUOTE", 3, r"verbatim|\"[^\"]{25,}\"|“[^”]{25,}”"),
    ("STRUCTURE", 3, r"\b(Table|Chapter|Section|Clause|Annex|Appendix|Schedule|"
                     r"Regulation|Reg\.?|Para(?:graph)?|Figure|Fig\.)\s*[-–]?\s*"
                     r"[0-9IVXA-Z]"),
    ("EDITION", 2, r"\b(\d+(?:st|nd|rd|th)\s+edition|EDITION|\bed\.\s*\d|"
                   r"Vol(?:ume)?\.?\s*[IVX0-9]|Rev(?:ision)?\.?\s*[0-9])"),
    ("LOCAL", 3, r"_spec/sources/|extracted|parsed in full|parsed,|downloaded and|"
                 r"Aryan supplied|supplied by Aryan|held locally|data held locally"),
    ("DERIVED", 2, r"re-?derived|rebuilt from first principles|reproduces exactly|"
                   r"reproduce[sd]? (?:to|exactly)|derivation (?:below|above|beside)"),
    ("CHECKED", 2, r"\bVERIFIED\b|verified verbatim|confirmed verbatim|"
                   r"cross-check(?:ed)? against|checked against the (?:document|PDF|manual)"),
)
COUNTER: Tuple[Tuple[str, str], ...] = (
    ("NOT-FOUND", r"NOT FOUND|not found|could not (?:be )?(?:find|locate|verify)|"
                  r"does not exist|no accessible"),
    ("UNSOURCED", r"\bunsourced\b|\buncited\b|no source|admitted unsourced|"
                  r"UNCITED - the thing under test"),
    ("RETRACTED", r"RETRACT|retracted|withdrawn|FALSE CITATION|fabricated"),
)

ROW = re.compile(r"^\|\s*(?P<src>[^|]+?)\s*\|\s*(?P<cites>[^|]+?)\s*\|"
                 r"\s*(?P<tier>[^|]*?)\s*\|\s*(?P<what>[^|]*?)\s*\|"
                 r"\s*(?P<doc>[^|]*?)\s*\|\s*(?P<claim>[^|]*?)\s*\|"
                 r"\s*(?P<note>.*?)\s*\|\s*$")
CITE = re.compile(r"`([^`:]+):(\d+)`")


def _rows() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for line in REGISTER.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        d = m.groupdict()
        if d["src"].lower().startswith("source") or set(d["src"]) <= set("-: "):
            continue                                   # header / separator
        if not d["src"].startswith("http"):
            continue
        out.append(d)
    return out


def _is_comment(s: str) -> bool:
    """Strictly a comment line. BLANK LINES DO NOT COUNT, and that matters.

    The first draft treated a blank line as part of the block, which welded
    adjacent blocks together: the IEX citation absorbed the whole 60-line
    symmetric-diesel comment beneath it and scored on evidence belonging to a
    different value. In this repo comment blocks are contiguous `#` runs, so a
    blank line is exactly the boundary.
    """
    t = s.strip()
    return t.startswith("#") or t.startswith("//")


def _window(path: str, line: int, url: str = "") -> str:
    """The comment block the cite belongs to, not a fixed number of lines.

    Walks up while the lines are comments, then down the same way. The first
    non-comment line in each direction is the boundary, which is what separates
    one cited value's justification from the next one's.

    THE LINE NUMBER IS A HINT, NOT THE TRUTH. `CITATION_REGISTER.md` is
    generated, and its line numbers are only correct as of the last rebuild -
    every config comment edited since then has shifted them, including the six
    comment patches applied on. Reading line 1647 of economics.yaml
    for the CEA substation citation landed in the middle of the PEDA biomass
    fleet block, twenty entries away. So the URL is located by SEARCH and the
    recorded line is used only to disambiguate when it appears more than once.
    """
    p = ROOT / path
    if not p.exists():
        return ""
    L = p.read_text(encoding="utf-8", errors="replace").splitlines()
    i = min(max(0, line - 1), len(L) - 1)
    if url:
        hits = [n for n, s in enumerate(L) if url in s]
        if hits:
            i = min(hits, key=lambda n: abs(n - i))
    lo = i
    while lo > 0 and lo > i - MAX_UP and _is_comment(L[lo - 1]):
        lo -= 1
    hi = i + 1
    while hi < len(L) and hi < i + MAX_DOWN and _is_comment(L[hi]):
        hi += 1
    return "\n".join(L[lo:hi])


def main() -> None:
    rows = _rows()
    # The register writes a verified CLAIM as `**yes**`, not `yes`. Reading it
    # literally reported all 106 rows as unverified on the first run.
    def _yes(v: str) -> bool:
        return v.replace("*", "").strip().lower() in ("yes", "y")

    unverified = [r for r in rows if not _yes(r["claim"])]
    print("register rows: %d  |  CLAIM-verified: %d  |  not CLAIM-verified: %d"
          % (len(rows), len(rows) - len(unverified), len(unverified)))

    scored: List[Tuple[int, Dict[str, str], List[str], List[str], str, str]] = []
    for r in unverified:
        text = ""
        for path, line in CITE.findall(r["cites"]):
            text += _window(path, int(line), r["src"]) + "\n"
        text += " " + r["note"]

        # Strip
        # otherwise "...')" reads as
        # evidence that a document was opened. It is evidence of a design
        # instruction, which is a different thing entirely.
        clean = re.sub(ARYAN_QUOTE + r"[^\"”]{0,400}[\"”]", " ", text)

        hits: List[str] = []
        score = 0
        for name, weight, pat in MARKERS:
            if re.search(pat, clean, re.I):
                hits.append(name)
                score += weight
        anti: List[str] = []
        for name, pat in COUNTER:
            if re.search(pat, text, re.I):
                anti.append(name)
                score -= 2

        # Order matters. The register note beats everything else, because it is
        # a record of the verification having been DONE rather than evidence
        # that it could be.
        if re.search(CHECKED_AND_FAILED, r["note"], re.I):
            klass = ("E2_FETCH_BLIND"
                     if re.search(FETCH_FAILURE, r["note"], re.I)
                     else "E1_CLAIM_DISPROVED")
        elif re.search(NOTE_RECORDS_VERIFICATION, r["note"], re.I):
            klass = "A0_ALREADY_DONE"
        elif re.search(HELD_LOCALLY, text, re.I):
            klass = "A_LOCAL"
        elif re.search(NOT_LOAD_BEARING, text, re.I):
            klass = "C_NOT_LOAD_BEARING"
        elif score >= 6 and not anti:
            klass = "B_IN_PLACE"
        else:
            klass = "D_GAP"
        scored.append((score, r, hits, anti, text, klass))

    scored.sort(key=lambda x: (x[5], -x[0], x[1]["src"]))
    disproved = [x for x in scored if x[5] == "E1_CLAIM_DISPROVED"]
    blind = [x for x in scored if x[5] == "E2_FETCH_BLIND"]
    failed = disproved
    done = [x for x in scored if x[5] == "A0_ALREADY_DONE"]
    local = [x for x in scored if x[5] == "A_LOCAL"]
    inplace = [x for x in scored if x[5] == "B_IN_PLACE"]
    notlb = [x for x in scored if x[5] == "C_NOT_LOAD_BEARING"]
    gap = [x for x in scored if x[5] == "D_GAP"]
    strong, mixed, weak = failed, done, gap

    L: List[str] = []
    L.append("# CPHEEO-class audit - unverified citations that are already substantiated")
    L.append("")
    L.append("> ## READ THIS BEFORE THE TABLES. THE PREMISE WAS WRONG.")
    L.append(">")
    L.append("> This script was built to find citations whose evidence was sitting")
    L.append("> unrecorded in config comments. **It then turned out that every one of")
    L.append("> the %d already has a hand-written entry in `_spec/CITATION_VERIFICATION"
             ".yaml`.**" % len(unverified))
    L.append("> Not one is unexamined. That file carries `doc_opened`,")
    L.append("> `claim_checked` and a written reason per source, and it is the")
    L.append("> authority. **This script does not read it**, so where the two")
    L.append("> disagree, the YAML wins.")
    L.append(">")
    L.append("> **CPHEEO itself is the proof.** It was described in chat on")
    L.append("> 2026-08-17 as \"already supplied, only the URL is dead\". That was")
    L.append("> wrong. The YAML records `doc_opened: false`, four access routes")
    L.append("> tried and failed, and the manual being a SCANNED IMAGE with one")
    L.append("> extractable character. The water figure was rebuilt from first")
    L.append("> principles instead, and CPHEEO would only have corroborated a pump")
    L.append("> efficiency. So CPHEEO is **not load-bearing**, not **already")
    L.append("> verified** - and the register was right all along.")
    L.append(">")
    L.append("> The lesson is the same one this project keeps relearning: **read the")
    L.append("> record before building a tool to reconstruct it.** The tables below")
    L.append("> are still useful as a cross-check on the config comments, but the")
    L.append("> work list should be taken from the YAML.")
    L.append("")
    L.append("Generated by `scripts/citation_already_supplied_audit.py`, 2026-08-17.")
    L.append("**Read-only. It verifies nothing.** It ranks the not-CLAIM-verified")
    L.append("citations by how much evidence the surrounding comment carries that the")
    L.append("document was actually opened - the CPHEEO signature.")
    L.append("")
    L.append("CPHEEO is the worked example: dead URL, no verification entry, and yet the")
    L.append("config names the edition and reproduces Chapter 13's pump relation")
    L.append("`P = Q.H / (367 . eta)`. That is not something a search snippet gives you.")
    L.append("The register's CLAIM column was measuring whether a verification note had")
    L.append("been WRITTEN, not whether the claim was SUPPORTED.")
    L.append("")
    L.append("| marker | weight | what it proves |")
    L.append("|---|---:|---|")
    L.append("| QUOTE | 3 | verbatim quotation from the document |")
    L.append("| STRUCTURE | 3 | a pointer INTO it - table, chapter, clause, page |")
    L.append("| LOCAL | 3 | a copy in the repo, or extracted / parsed / supplied |")
    L.append("| EDITION | 2 | a named edition, volume or revision |")
    L.append("| DERIVED | 2 | the source's own relation reproduced |")
    L.append("| CHECKED | 2 | explicit verification language |")
    L.append("")
    L.append("Counter-markers (NOT-FOUND / UNSOURCED / RETRACTED) subtract 2 each and")
    L.append("move an entry out of the STRONG list however high it scores, because a")
    L.append("comment that says the source could not be found is the opposite case.")
    L.append("")
    L.append("| class | meaning | count |")
    L.append("|---|---|---:|")
    L.append("| **E1 - CLAIM DISPROVED** | the document WAS read and does NOT carry "
             "the claim. **An active defect, not a gap.** | **%d** |" % len(disproved))
    L.append("| **E2 - FETCH WENT BLIND** | the page is JavaScript-rendered or "
             "throttled, so the check saw nothing. **Unresolved, NOT disproved.** "
             "| **%d** |" % len(blind))
    L.append("| **A0 - ALREADY VERIFIED, NEVER TICKED** | the register's OWN note "
             "says the document was opened and the figure found. Pure bookkeeping. "
             "| **%d** |" % len(done))
    L.append("| **A - HELD LOCALLY** | the document or its data is IN THIS REPO. "
             "The URL is an access path, not the evidence. | **%d** |" % len(local))
    L.append("| **B - SUBSTANTIATED IN PLACE** | no local copy, but the comment "
             "quotes the source and points into it. | **%d** |" % len(inplace))
    L.append("| **C - NOT LOAD-BEARING** | the block itself says no model number "
             "depends on it. Needs a LABEL, not a citation. | **%d** |" % len(notlb))
    L.append("| D - GENUINE GAP | needs the document opened. | %d |" % len(gap))
    L.append("| total not CLAIM-verified | | %d |" % len(unverified))
    L.append("")
    L.append("**A0 + A + B + C = %d of %d need no library access at all.** Only the "
             "%d in class D require chasing a source."
             % (len(done) + len(local) + len(inplace) + len(notlb), len(unverified),
                len(gap)))
    L.append("")
    L.append("**The headline is class A0.** The register's CLAIM column was never a "
             "measure of whether a claim was verified - it is a measure of whether "
             "someone remembered to tick a box after verifying it. That is the same "
             "failure mode as CPHEEO, one layer up: CPHEEO's evidence sat unticked in "
             "a config comment, and these sit unticked in the register's own notes.")
    L.append("")

    def _table(title: str, items, note: str) -> None:
        L.append("## %s" % title)
        L.append("")
        L.append(note)
        L.append("")
        if not items:
            L.append("*(none)*")
            L.append("")
            return
        L.append("| score | evidence | source | supports | cited at |")
        L.append("|---:|---|---|---|---|")
        for score, r, hits, anti, _t, _k in items:
            ev = " ".join(hits) + ((" | !" + " !".join(anti)) if anti else "")
            src = r["src"]
            if len(src) > 62:
                src = src[:59] + "..."
            L.append("| %d | %s | %s | %s | %s |"
                     % (score, ev or "-", src, r["what"] or "-", r["cites"]))
        L.append("")

    _table("E1 - CLAIM DISPROVED (READ THESE FIRST - they are defects)", disproved,
           "The document was actually read - parsed in full, hundreds of thousands of "
           "characters in several cases - and **it does not carry the attributed "
           "claim**. These are not gaps in the audit; they are live citation errors, "
           "and the register shows them with the same `-` as a source nobody has "
           "looked at. Each needs the config comment corrected, a replacement source, "
           "or an explicit retraction. Check whether the 2026-08-10 audit that found "
           "them also FIXED them: finding is not fixing.")
    _table("E2 - FETCH WENT BLIND (unresolved, do NOT call these wrong)", blind,
           "Same 'zero hits' wording as E1 and a completely different meaning. The "
           "fetch returned site chrome from a JavaScript-rendered page, a login wall "
           "or a throttled host, so **nothing was read and nothing was disproved**. "
           "Treating these as errors would be a false accusation against sources that "
           "may be perfectly sound. They need a human browser, an archived snapshot, "
           "or a different URL for the same document.")
    _table("A0 - ALREADY VERIFIED, THE BOX WAS NEVER TICKED (do these next)", done,
           "For every row here the register's own NOTE column records that the "
           "document was opened and the attributed figure found in it, while the "
           "CLAIM column still reads `-`. Example: TGSPDCL Cost Data FY23-24 is noted "
           "as *107 pp, downloaded and parsed 2026-08-10. THE DOCUMENT IS REAL AND "
           "CONTAINS THE EXACT LINE ITEM CITED*. **There is nothing to research.** "
           "Read the note, set the CLAIM flag in `_spec/CITATION_VERIFICATION.yaml`, "
           "rebuild the register.")
    _table("A - HELD LOCALLY", local,
           "The comment block points at a file inside this project - a workbook in "
           "`PROJECT/DATA`, a PDF in `_spec/sources/`, an extracted text dump. **The "
           "evidence is already here.** Verification means opening the local file and "
           "writing the note; the dead URL is irrelevant to whether the number is "
           "right. This is the CPHEEO pattern exactly, and it is the cheapest "
           "verification work available.")
    _table("B - SUBSTANTIATED IN PLACE", inplace,
           "No local copy, but the comment quotes the source verbatim AND points into "
           "it by table, chapter or clause. Someone had the document open. Confirm by "
           "reading the block, then write the note from what is already there.")
    _table("C - NOT LOAD-BEARING", notlb,
           "The block says, in its own words, that no model value rests on this - "
           "corroboration only, declared Tier 3, method-only, not read by any code, or "
           "sitting behind `enabled: false`. **These should never have been on a "
           "verification list.** The right action is to relabel the citation as "
           "corroborative or method-only, not to verify it. Check each: `enabled: "
           "false` in particular can be stale, because INFRA-2 split cost from "
           "`enabled` on 2026-08-11.")
    _table("D - GENUINE GAP", gap,
           "No local copy, no in-place quotation, and the value is or may be "
           "load-bearing. These are the ones that need the document. The list being "
           "this short is the point of the exercise.")

    L.append("## What to do with this")
    L.append("")
    L.append("1. **Class A first.** The file is already here; open it and write the note.")
    L.append("2. **Class C is a labelling job, not a verification job.** Relabel and")
    L.append("   remove from the list. Re-check any `enabled: false` claim against the")
    L.append("   code, because INFRA-2 separated production cost from that flag.")
    L.append("3. **Class B**: read the block; if the quotation is real, promote it.")
    L.append("4. **Class D** is the honest remainder and belongs in the limitations.")
    L.append("5. **Do not treat a class or a score as a verification.** This script")
    L.append("   measures how much a comment LOOKS like someone read the document.")
    L.append("   Only reading the comment tells you whether they did.")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")

    print("STRONG %d | MIXED %d | WEAK %d" % (len(strong), len(mixed), len(weak)))
    print("wrote %s" % OUT)
    print()
    for score, r, hits, anti, _t, _k in strong[:30]:
        print("  %2d  %-14s %-58s %s" % (score, " ".join(hits)[:14], r["src"][:58],
                                         r["what"][:28]))


if __name__ == "__main__":
    main()
