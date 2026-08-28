"""Build the MASTER CITATION REGISTER from the codebase itself.

the author, "MAKE SURE THERE IS A TRACK OF ALL DATASETS/CITATIONS WE
USE THROUGHOUT THE PROJECT".

The register is GENERATED, not hand-maintained, so it cannot drift from what
the model actually cites. Re-run it whenever citations change and commit the
output.

For every URL in the model-facing tree it records:
  - the source domain and full URL
  - every file:line that cites it
  - the Tier label found nearest to the citation, if any
  - the nearest YAML key or Python identifier, i.e. WHAT it is citing
  - a verification status, merged from a hand-maintained overrides table

THE THREE VERIFICATION LEVELS, which are not the same thing:
  LINK   the URL resolves (scripts/citation_link_audit.py proves this)
  DOC    a human has OPENED the document
  CLAIM  the specific number we attribute to it has been found IN it

A citation can be LINK-green and CLAIM-wrong. The LBNL room-AC reference is
exactly that: it resolves perfectly and says the opposite of what was
attributed to it. Only CLAIM protects the thesis.

Overrides live in _spec/CITATION_VERIFICATION.yaml so that verification work
is recorded once and survives regeneration.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)

SCAN = ["config", "energy", "core", "layout"]
OUT = os.path.join("_spec", "CITATION_REGISTER.md")
OVERRIDES = os.path.join("_spec", "CITATION_VERIFICATION.yaml")

URL_RE = re.compile(r"https?://[A-Za-z0-9./_%?=&#~+,:$!*'()@;-]+")
TIER_RE = re.compile(r"\bTier[- ]?([1-4])\b", re.I)
YAML_KEY_RE = re.compile(r"^\s{0,6}([a-z_][a-z0-9_]*)\s*:", re.I)
PY_DEF_RE = re.compile(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")


def nearest_context(lines, idx, path):
    """Walk backwards for the thing this citation is about."""
    rx = PY_DEF_RE if path.endswith(".py") else YAML_KEY_RE
    for j in range(idx, max(-1, idx - 60), -1):
        m = rx.match(lines[j])
        if m:
            return m.group(1)
    return ""


def nearest_tier(lines, idx):
    """Tier label within a few lines either side of the citation."""
    for j in range(max(0, idx - 6), min(len(lines), idx + 4)):
        m = TIER_RE.search(lines[j])
        if m:
            return m.group(1)
    return ""


def main():
    cites = defaultdict(list)          # url -> [(path, lineno, key, tier)]
    for d in SCAN:
        for dirpath, _dirs, files in os.walk(d):
            if "__pycache__" in dirpath:
                continue
            for fn in sorted(files):
                if not fn.endswith((".yaml", ".yml", ".py")):
                    continue
                path = os.path.join(dirpath, fn).replace("\\", "/")
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().splitlines()
                for i, line in enumerate(lines):
                    for m in URL_RE.findall(line):
                        if "w3.org/2000/svg" in m:
                            continue
                        url = m.rstrip(".,);:'\"")
                        cites[url].append(
                            (path, i + 1, nearest_context(lines, i, path),
                             nearest_tier(lines, i)))

    over = {}
    if os.path.exists(OVERRIDES):
        try:
            import yaml
            with open(OVERRIDES, "r", encoding="utf-8") as fh:
                over = (yaml.safe_load(fh) or {}).get("sources", {}) or {}
        except Exception:
            over = {}

    by_domain = defaultdict(list)
    for url, rows in cites.items():
        dom = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        by_domain[dom].append((url, rows))

    n_urls = len(cites)
    n_sites = sum(len(r) for r in cites.values())
    n_doc = sum(1 for u in cites if (over.get(u) or {}).get("doc_opened"))
    n_claim = sum(1 for u in cites if (over.get(u) or {}).get("claim_checked"))

    #. "not claim-verified" was one bucket and it hid the difference
    # that matters: a source someone investigated and found does NOT support the
    # claim looked identical to one nobody had opened. Both showed a dash.
    # These are not the same. The first has been dealt with - the number was
    # withdrawn, relabelled or re-sourced - and needs no further work. The
    # second is outstanding. Reporting them together overstates what is left and
    # understates what was found.
    # The classification reads the hand-written note, so it is a REPORTING aid,
    # not a truth claim. Only `claim_checked` certifies a citation.
    # The first version of these patterns was too narrow and undercounted badly:
    # it matched "NOT IN THIS ARTICLE" but not "NOT IN THIS PAGE", and had no
    # pattern at all for the commonest disposition of the lot, "this is a
    # landing page and the figures are not on it". Nine sources that carried
    # full investigation notes were reported as untouched. Widened
    # after checking them by hand.
    DISPOSED = [
        ("claim absent, withdrawn",
         r"NOT IN TH(IS|E) \w+|CITATION RETRACTED|IS NOT IN IT|ZERO HITS"
         r"|ZERO occurrences|DOES NOT CONTAIN|BOTH HALVES OF THE CLAIM ARE FALSE"
         r"|NONE OF THE FIGURES PRESENT|THE NUMBER IS RIGHT BUT"),
        ("landing or navigation page, figures not on it",
         r"LANDING PAGE|landing page|[Nn]avigation page|root domain"
         r"|Root domain|homepage|NO ARTICLE BODY|TOPIC LANDING"
         r"|WRONG ONE|wrong edition|EDITION SHOWN IS"),
        ("unreachable, disposition recorded",
         r"UNREACHABLE|HTTP 000|ECONNRESET|403|times out|paywall"
         r"|HTML error page|serves an HTML|DISPOSITION RECORDED|DISPOSITION:"),
        ("relabelled or re-sourced",
         r"relabel|declared Tier|now a \*\*declared"),
        ("superseded by a verified entry",
         r"[Ss]uperseded|Drop this one|should point at|Redundant"),
        ("data held locally", r"held (in|locally)|PROJECT/DATA|downloaded"),
        ("verified via a mirror", r"CLAIM-CHECKED VIA|working mirror"),
    ]
    triage, outstanding = {}, []
    for u in cites:
        o = over.get(u) or {}
        if o.get("claim_checked"):
            continue
        note = " ".join(str(o.get("note", "")).split())
        for label, pat in DISPOSED:
            if re.search(pat, note):
                triage[label] = triage.get(label, 0) + 1
                break
        else:
            outstanding.append((o.get("tier_b_priority"), u))
    outstanding.sort(key=lambda r: (r[0] is None, r[0] or 0, r[1]))

    L = []
    L.append("# Master citation register")
    L.append("")
    L.append("**GENERATED by `scripts/citation_register_build.py`. Do not edit "
             "by hand** - it is rebuilt from the code, so it cannot drift from "
             "what the model actually cites. Verification status is the one "
             "hand-maintained part and lives in "
             "`_spec/CITATION_VERIFICATION.yaml`.")
    L.append("")
    L.append("## Why three columns and not one")
    L.append("")
    L.append("| level | means | proven by |")
    L.append("|---|---|---|")
    L.append("| **LINK** | the URL resolves | `scripts/citation_link_audit.py`, automated |")
    L.append("| **DOC** | a human has opened the document | reading it |")
    L.append("| **CLAIM** | the number we attribute to it is IN it | reading the relevant page |")
    L.append("")
    L.append("These are not the same thing and the difference is not academic. "
             "The LBNL room-AC citation is LINK-green and CLAIM-wrong: it "
             "resolves perfectly and states the opposite of what was "
             "attributed to it. **Only CLAIM protects the thesis.**")
    L.append("")
    L.append("Three separate times a search tool reported that a source did "
             "not exist and it did - the time-series-aggregation literature, "
             "Keirstead's urban energy review, and PSPCL's own domestic H1/H2 "
             "sales split. Standing rule: **when a search reports a negative, "
             "open the document.**")
    L.append("")
    L.append("## Coverage")
    L.append("")
    L.append("| | count |")
    L.append("|---|---|")
    L.append("| unique sources cited in `config/ energy/ core/ layout/` | **%d** |" % n_urls)
    L.append("| individual citation sites | %d |" % n_sites)
    L.append("| document opened (DOC) | %d |" % n_doc)
    L.append("| claim verified in the document (CLAIM) | **%d** |" % n_claim)
    L.append("")
    L.append("### What the remaining %d actually are" % (n_urls - n_claim))
    L.append("")
    L.append("Not claim-verified is not the same as not looked at. A source "
             "that was opened and found NOT to support the number has been "
             "**dealt with** - the figure was withdrawn, relabelled or "
             "re-sourced - and needs no further work. Reporting it beside a "
             "source nobody has opened overstates what is outstanding and "
             "hides what was found.")
    L.append("")
    L.append("| state | count |")
    L.append("|---|---|")
    for label, cnt in sorted(triage.items(), key=lambda kv: -kv[1]):
        L.append("| %s | %d |" % (label, cnt))
    L.append("| **genuinely outstanding** | **%d** |" % len(outstanding))
    L.append("")
    L.append("The classification reads the hand-written note and is a "
             "reporting aid, not a certification. **Only `claim_checked` "
             "certifies a citation.**")
    L.append("")
    if outstanding:
        L.append("#### The outstanding ones, by priority")
        L.append("")
        L.append("| priority | source |")
        L.append("|---|---|")
        for pri, u in outstanding:
            L.append("| %s | %s |" % (pri if pri else "-", u))
        L.append("")
    L.append("`_spec/` documentation citations are deliberately out of scope "
             "here; they are checked when the chapter that cites them is "
             "written.")
    L.append("")
    L.append("---")
    L.append("")

    for dom in sorted(by_domain):
        L.append("## %s" % dom)
        L.append("")
        L.append("| source | cites | tier | what it supports | DOC | CLAIM | note |")
        L.append("|---|---|---|---|---|---|---|")
        for url, rows in sorted(by_domain[dom]):
            o = over.get(url) or {}
            tiers = sorted({t for _p, _l, _k, t in rows if t})
            keys = sorted({k for _p, _l, k, _t in rows if k})[:3]
            where = "<br>".join("`%s:%d`" % (p, l) for p, l, _k, _t in rows[:4])
            if len(rows) > 4:
                where += "<br>+%d more" % (len(rows) - 4)
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                url,
                where,
                "/".join(tiers) or "-",
                ", ".join("`%s`" % k for k in keys) or "-",
                "yes" if o.get("doc_opened") else "-",
                "**yes**" if o.get("claim_checked") else "-",
                (o.get("note") or "").replace("|", "/"),
            ))
        L.append("")

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")
    print("wrote %s" % OUT)
    print("  %d unique sources, %d citation sites" % (n_urls, n_sites))
    print("  DOC opened: %d   CLAIM verified: %d" % (n_doc, n_claim))
    print("  of the %d not claim-verified:" % (n_urls - n_claim))
    for label, cnt in sorted(triage.items(), key=lambda kv: -kv[1]):
        print("      %-36s %d" % (label, cnt))
    print("      %-36s %d" % ("GENUINELY OUTSTANDING", len(outstanding)))
    p1 = [u for pri, u in outstanding if pri == 1]
    print("      of which priority 1: %d" % len(p1))


if __name__ == "__main__":
    main()
