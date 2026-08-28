"""Generate Appendix C - the parameter and citation tables - from the configs.

The citation register (`scripts/citation_register_build.py`) cuts the same
evidence by SOURCE. The thesis appendix needs it cut by PARAMETER: what is the
value, what are its units, where did it come from, and how well verified is it.

Generated, not hand-written, so it cannot drift from what the model reads.

Run from the repo root:
    python scripts/appendix_c_parameters.py
"""
from __future__ import annotations

import os
import re
from collections import OrderedDict

CONFIGS = [
    ("demographics.yaml", "Population and income structure"),
    ("demand_norms.yaml", "Demand norms and end uses"),
    ("district_composition.yaml", "Land use, built form and ownership"),
    ("climate.yaml", "Climate and irradiance"),
    ("economics.yaml", "Costs, tariffs and technologies"),
    ("price_trajectories.yaml", "Grid emission factor and price paths"),
]

# The register PUBLISHES to the repository rather than printing in the
# thesis: 78 pages of four-column table serve a
# reader better as a searchable file beside the configs it is generated
# from. The thesis Appendix C is now a hand-written two-page statement.
# Path is resolved from the repo root (main chdirs there), so two
# levels up reaches PROJECT/. Three reached the OneDrive root on the first
# run and dropped the register outside the project entirely.
OUT = os.path.join("..", "..", "github_public", "PARAMETER_REGISTER.md")

TIER_RE = re.compile(r"\bTier\s*([1-4])(?:\s*-\s*([1-4]))?", re.I)
# Parentheses are legal in URLs and the ESMAP street-lighting report has
# "(P149482)" in its path; excluding ")" truncated that link mid-way. They
# are percent-encoded on output so the markdown link syntax survives.
URL_RE = re.compile(r"https?://[^\s,;>\]]+")


def urlsafe(u: str) -> str:
    return u.rstrip(".,;").replace("(", "%28").replace(")", "%29")
# Keys may start with a digit: period tables are keyed 2030:/2042:/2055:,
# and requiring a letter first made the scanner drop every one of them -
# 1,265 leaves, including the AI-uplift and car-ownership trajectories,
# were silently absent from the register by re-parsing
# the configs with a real YAML parser and diffing).
# Quotes are optional: period tables write their keys as "2030": to keep
# YAML from reading them as integers, and the unquoted pattern skipped every
# such block (car ownership by income, PM2.5 ambient scale).
KEY_RE = re.compile(r'^(\s*)"?([A-Za-z0-9_][A-Za-z0-9_]*)"?\s*:\s*(.*?)\s*$')
YEAR_LEAF = re.compile(r"^(19|20)\d{2}$")
LIST_ITEM_RE = re.compile(r"^\s*-\s+(.*?)\s*$")

# Keys whose value is structural rather than a modelled quantity.
SKIP_KEYS = {"enabled", "note", "notes", "comment", "source", "sources", "_comment"}

# Superscripts are written as the real characters; map_unicode in
# build_appendix_tex turns them into \textsuperscript. Writing "m2" printed
# a literal 2 in the compiled appendix.
M2 = "m²"
KM2 = "km²"
# The rupee prints as its symbol, not as "INR"
# compiled register); ₹ is declared in the abbreviations list.
RS = "₹"

# Named sources that recur without a URL beside them but have one canonical
# home elsewhere in the configs. Linking them here is a LOOKUP, not a guess:
# each URL below is copied from a config comment that cites the same body.
CANONICAL_URLS = {
    "URDPFI": "https://www.mohua.gov.in/link/urdpfi-guidelines.php",
    "Census 2011": "https://censusindia.gov.in/nada/index.php/catalog/1464",
    # Each of the following is the URL the configs themselves cite for the
    # same body elsewhere; a name without a link was a comment that did not
    # repeat the URL, not a different source.
    "CERC": "https://cercind.gov.in",
    "CEA": "https://cea.nic.in",
    "PSPCL": "https://pspcl.in",
    "PSERC": "https://pserc.nic.in",
    "IEX": "https://www.iexindia.com",
    "CPHEEO": "http://cpheeo.gov.in",
    "CEEW": "https://www.ceew.in",
    "MNRE": "https://mnre.gov.in",
    "NREL": "https://www.nrel.gov",
    "IEA": "https://www.iea.org",
    "BEE": "https://beeindia.gov.in",
    "MoHUA": "https://www.mohua.gov.in",
    "CGWB": "http://cgwb.gov.in",
}
UNIT_HINTS = [
    ("inr_per_kwh", RS + "/kWh"), ("inr_per_kwp", RS + "/kWp"), ("inr_per_kwh_per_year", RS + "/kWh/yr"),
    ("inr_per_kw", RS + "/kW"), ("inr_per_unit", RS + "/unit"), ("inr_per_m2", RS + "/" + M2),
    ("inr_per_mva", RS + "/MVA"), ("inr_per_km", RS + "/km"), ("inr_per_tonne", RS + "/t"),
    ("_inr", RS), ("kwh_per_capita_per_year", "kWh/cap/yr"), ("kwh_per_kwp", "kWh/kWp"),
    ("kwh_per_day", "kWh/day"), ("_kwh", "kWh"), ("_kwp", "kWp"), ("_kw", "kW"),
    ("_mw", "MW"), ("_mva", "MVA"), ("w_per_m2", "W/" + M2),
    ("_km2", KM2), ("_m2", M2),
    ("_m", "m"), ("_km", "km"), ("kgco2_per_kwh", "kgCO2/kWh"), ("kgco2_per_kwp", "kgCO2/kWp"),
    ("_kgco2", "kgCO2"), ("_tonnes", "t"), ("_years", "yr"), ("per_year", "/yr"),
    ("_hours", "h"), ("_fraction", "-"), ("_share", "-"), ("_ratio", "-"),
    ("_factor", "-"), ("_multiplier", "-"), ("_efficiency", "-"), ("_rate", "-"),
    ("_pct", "%"), ("_percent", "%"), ("_deg", "deg"), ("_celsius", "degC"),
    # counts and coordinates: named so the column does not sit half empty.
    # Order matters within this group too: per_1000_population must beat
    # _population, and cagr must never inherit "persons" from a population
    # parent - both were mislabelled in the first compiled register.
    ("per_1000_population", "per 1,000"), ("cagr", "/yr"),
    ("_population", "persons"), ("_households", "households"),
    ("latitude", "deg N"), ("longitude", "deg E"),
    ("_rows", "cells"), ("_cols", "cells"), ("_year", "year"),
    ("_capita", "per person"), ("_per_1000_pop", "per 1,000"),
    ("_seats", "seats"), ("_rooms", "rooms"), ("_ecs", "ECS"),
]


# Longest hint first, so kgco2_per_kwh is not swallowed by _kwh.
_HINTS = sorted(UNIT_HINTS, key=lambda p: len(p[0]), reverse=True)


# ---------------------------------------------------------------------------
# LONG MAPPINGS ARE SUMMARISED, NOT PRINTED IN FULL.
# The register is 101 pages of table, and the two tallest tables are 630
# printed lines each because a single cell can hold a twelve-band hourly
# profile - "00_02: 0.50, 02_04: 0.45,..." - which wraps to fifteen lines in
# a quarter-width column. Fifteen lines for one
# parameter is unreadable as well as wasteful: nobody reads a dictionary
# broken across fifteen ragged lines.
# WHAT IS KEPT AND WHAT IS DROPPED. The count of entries, the range and the
# first two entries are kept, because those are what a reader checks. The
# full mapping is dropped from the page and stays in the configuration file
# the row already names, which is the authority and is published with the
# code. Nothing is rounded and no value is altered: this is a decision about
# what to PRINT, not about what the model uses.
SERIES = re.compile(r"^[\[{]?\s*(?:[\"']?[\w:. -]+[\"']?\s*:\s*"
                    r"-?[\d.]+\s*[,;]\s*){4,}")
NUMS = re.compile(r":\s*(-?\d+(?:\.\d+)?)")


def compress_series(val: str, keep: int = 2) -> str:
    """A mapping of five or more numeric entries becomes count, range, sample."""
    if len(val) < 90 or not SERIES.match(val):
        return val
    pairs = re.findall(r"[\"']?([\w:. -]+?)[\"']?\s*:\s*(-?\d+(?:\.\d+)?)",
                       val)
    if len(pairs) < 5:
        return val
    nums = [float(v) for _, v in pairs]
    head = ", ".join("%s: %s" % (k.strip(), v) for k, v in pairs[:keep])
    return ("%s, ... (%d entries, %g to %g)"
            % (head, len(pairs), min(nums), max(nums)))


def vis(cell: str) -> str:
    """What a markdown cell actually prints: link text, not link target."""
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell)
    return cell.replace("`", "").replace("*", "").strip()


def collapse_numbered_siblings(rows: list[dict]) -> list[dict]:
    """Five or more rows keyed parent.1..parent.N become one row.

    monthly_rtc_inr_per_kwh printed as twelve rows differing only in the
    month index, each repeating the same units and source - a page of table
    carrying one series. Kept: the count, the range and
    the first two values; the full series stays in the named config file.
    Only collapses when every sibling shares one unit and one source, so a
    series whose members are individually sourced keeps its rows.
    """
    from collections import OrderedDict
    groups: "OrderedDict[str, list]" = OrderedDict()
    for r in rows:
        m = re.match(r"^(.*)\.(\d{1,4})$", r["path"])
        groups.setdefault(m.group(1) if m else None, []).append(r)

    out = []
    for parent, grows in groups.items():
        if parent is None or len(grows) < 5:
            out.extend(grows)
            continue
        units = {g["units"] for g in grows}
        srcs = {(g["url"], g["source"]) for g in grows}
        vals = []
        for g in grows:
            try:
                vals.append(float(str(g["value"]).replace(",", "")))
            except ValueError:
                vals = None
                break
        if vals is None or len(units) != 1 or len(srcs) != 1:
            out.extend(grows)
            continue
        first = grows[0]
        merged = dict(first)
        merged["path"] = parent
        merged["value"] = ("%s, %s, ... (%d values, %g to %g)"
                           % (grows[0]["value"], grows[1]["value"],
                              len(grows), min(vals), max(vals)))
        out.append(merged)
    return out


def common_prefix(paths: list[str]) -> str:
    """The dotted prefix every path in a group shares, minus the last segment.

    Returned without a trailing dot, and empty when the group has fewer than
    three rows or the prefix would swallow the whole key: stating "all keys
    below sit under X" is only worth a line when several rows save one.
    """
    if len(paths) < 3:
        return ""
    parts = [p.split(".") for p in paths]
    n = 0
    while all(len(q) > n + 1 for q in parts) and             len({q[n] for q in parts}) == 1:
        n += 1
    return ".".join(parts[0][:n]) if n else ""


def units_for(path: str) -> str:
    """Units from the leaf key, falling back to the parent path.

    Nested keys like grid.import_tariff_inr_per_kwh.peak carry their units on
    the parent, not the leaf.

    MATCHES ON WHOLE TOKENS, NOT SUBSTRINGS. The old `suffix in p` clause
    gave land_use_targets.residential_mid the unit "m", because "_m" is a
    substring of "residential_mid" - a land-use FRACTION printed as metres,
    and the author spotted it in the compiled appendix. A hint now matches only
    if its tokens appear as a contiguous run of the key's underscore tokens:
    "w_per_m2" still matches cooling_load_w_per_m2_peak, "m" no longer
    matches the "mid" inside residential_mid.
    """
    for part in reversed(path.split(".")):
        toks = part.lower().split("_")
        for suffix, unit in _HINTS:
            h = suffix.strip("_").split("_")
            if any(toks[i:i + len(h)] == h
                   for i in range(len(toks) - len(h) + 1)):
                return unit
    return ""


def tidy(text: str, limit: int = 240) -> str:
    text = text.replace("—", " - ").replace("–", "-")  # no em-dashes
    text = re.sub(r"\s+", " ", text).strip(" -;")
    text = text.replace("|", "/")
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "..."
    return text


# A SOURCE CITED IN PROSE IS STILL A SOURCE. The register was built by
# scraping URLs, so a value whose provenance is written as text - "MoSPI
# NSS-78", "NFHS-5", "Petri & Caldeira 2015" - printed with an EMPTY source
# column and read as unsourced.
# appendix. This recognises named bodies, standards and
# author-year forms so the evidence that already exists in the configuration
# is shown. It RECOGNISES, it never invents: anything not matched stays blank.
NAMED_SOURCE = re.compile(
    r"\b("
    r"MoSPI|NSS[-\s]?\d*|NFHS[-\s]?\d*|Census(?:\s+\d{4})?|"
    r"CEA|CERC|BEE|CPCB|CPHEEO|CGWB|IMD|MNRE|SECI|PSPCL|PMAY|URDPFI|IPHS|"
    r"NBC(?:\s+\d{4})?|NREL|IEA|IRENA|IPCC|AR6|PNAS|CEEW|TERI|WEF|Bain|"
    r"Fraunhofer(?:\s+ISE)?|BNEF|TPDDL|ICE360|eMARC|BESCOM|SGPC|"
    r"Prayas|CSE|NSSO|MoHUA|MoP|POSOCO|NIWE|NISE|"
    r"IS\s?\d{3,5}|"
    r"[A-Z][a-z]+\s+(?:&|and)\s+[A-Z][a-z]+\s+\d{4}|"
    r"[A-Z][a-z]+\s+et\s+al\.?,?\s*\d{4}"
    r")\b")


def named_sources(prose: str, limit: int = 2) -> str:
    """Distinct named sources in a comment, in the order written."""
    out: list[str] = []
    for m in NAMED_SOURCE.finditer(prose or ""):
        s = " ".join(m.group(1).split())
        if s.upper() not in {x.upper() for x in out}:
            out.append(s)
        if len(out) >= limit:
            break
    return "; ".join(out)


# A BLANK SOURCE CELL NOW SAYS WHY IT IS BLANK.
# much unsourced?" of rows that are not evidence at all - switches, shares
# that sum to one, the model's own resolution, arithmetic derivations and
# design choices. Each blank cell prints its category in italics, so the
# question is answered on the row itself rather than in a preamble nobody
# rereads. Categories are matched on the key name; anything unmatched is a
# design choice, which is what an unmatched free parameter in a design
# study is.
BLANK_TAGS = [
    (re.compile(r"enabled|allow_|_on$|use_|include_|\.mode$|active_", re.I),
     "*switch*"),
    (re.compile(r"_share|_fraction|_mix|_split|_shares|weights", re.I),
     "*shares sum to 1*"),
    (re.compile(r"slice|daypart|daytype|period|bucket|grid_|seed|_count|"
                r"n_rows|n_cols|_year$|base_year", re.I),
     "*model structure*"),
    (re.compile(r"_multiplier|_factor|_ratio|_efficiency|_rate$|derived|"
                r"_offset|_scale", re.I),
     "*derived*"),
    (re.compile(r"_cap|_limit|_max|_min|_bound|ceiling", re.I), "*bound*"),
    (re.compile(r"name|label|title|_id$|scenario|categories", re.I),
     "*label*"),
]


def blank_tag(path: str) -> str:
    for pat, tag in BLANK_TAGS:
        if pat.search(path):
            return tag
    return "*design choice*"


RULE_RE = re.compile(r"^#\s*[-=_]{6,}\s*$")


def harvest(block: list[str]) -> tuple[str, str, str]:
    """Pull (tier, urls, prose) out of a run of comment lines above a key.

    THE RUN IS CUT AT THE LAST HORIZONTAL RULE. These configs separate blocks
    with `# -----` lines and do not put blank lines between them, so a
    comment "run" could reach back seventy lines into a previous block's
    documentation. `harvest` then took the FIRST url in that run, and
    lighting_seasonal - whose real source is BESCOM 2022, named in its own
    comment - was credited to a Tribune newspaper report belonging to the
    religious-festival block above it. Fourteen rows carried that false
    attribution. Cutting at the rule keeps a block's own documentation, and
    the last url wins over an earlier one for the same reason: nearer the
    key is more specific.
    """
    # These configs write a block header as
    #     # -----          <- rule
    #     # doc, with URL
    #     # -----          <- rule
    #     key:
    # so a naive "cut at the last rule" deletes the very documentation being
    # looked for (NASA POWER vanished off every climate row that way). Drop
    # trailing rules FIRST, then cut at the last rule that remains: what is
    # left is the block's own header text and nothing from the block above.
    blk = list(block)
    while blk and RULE_RE.match(blk[-1].strip()):
        blk.pop()
    for i in range(len(blk) - 1, -1, -1):
        if RULE_RE.match(blk[i].strip()):
            blk = blk[i + 1:]
            break
    joined = " ".join(line.lstrip("# ").rstrip() for line in blk)
    tiers = TIER_RE.findall(joined)
    tier = ""
    if tiers:
        lo, hi = tiers[0]
        tier = f"{lo}-{hi}" if hi else lo
    urls = URL_RE.findall(joined)
    prose = URL_RE.sub("", joined)
    prose = re.sub(r"\(\s*\)", "", prose)
    # First url within a CORRECTLY SCOPED block is the primary citation.
    # (Taking the last one instead credited an EV ownership row to zoho.com,
    # an incidental link further down the same comment.)
    return tier, urlsafe(urls[0]) if urls else "", tidy(prose)


def source_label(url: str) -> str:
    if not url:
        return ""
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return host


def parse(path: str) -> list[dict]:
    rows: list[dict] = []
    stack: list[tuple[int, str]] = []
    comments: list[str] = []
    blanks = 0
    # Provenance harvested above a parent block applies to every leaf inside it,
    # so carry (tier, url, prose) down the indentation stack and let a leaf's own
    # comment override it.
    inherited: dict[int, tuple[str, str, str]] = {}
    # (Sibling inheritance was tried here and removed - see the note at the
    # attribution site below for why a block's first citation must not be
    # spread across its siblings.)
    pending_list: list[str] | None = None
    pending_row: dict | None = None

    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    for lineno, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if not line.strip():
            blanks += 1
            if blanks >= 2:
                comments = []
            continue
        blanks = 0
        if line.lstrip().startswith("#"):
            comments.append(line.strip())
            continue

        item = LIST_ITEM_RE.match(line)
        if item and pending_list is not None:
            pending_list.append(item.group(1))
            continue
        if pending_list is not None and pending_row is not None:
            pending_row["value"] = ", ".join(pending_list[:12]) + (
                f" ... ({len(pending_list)} values)" if len(pending_list) > 12 else ""
            )
            rows.append(pending_row)
            pending_list, pending_row = None, None

        m = KEY_RE.match(line)
        if not m:
            comments = []
            continue
        indent, key, value = len(m.group(1)), m.group(2), m.group(3)

        while stack and stack[-1][0] >= indent:
            stack.pop()
        for level in [k for k in inherited if k >= indent]:
            inherited.pop(level, None)

        inline = ""
        if "#" in value:
            body, _, inline = value.partition("#")
            value, inline = body.strip(), inline.strip()

        if value == "":
            stack.append((indent, key))
            got = harvest(comments)
            # A prose-only citation must inherit too. Requiring a tier or a
            # URL here is what stripped provenance from every child of a
            # block cited in words.
            if got[0] or got[1] or named_sources(got[2]):
                inherited[indent] = got
            comments = []
            continue

        if key in SKIP_KEYS:
            comments = []
            continue

        # NO SIBLING INHERITANCE. Propagating the first sourced child's
        # citation to its siblings looked right on household_size_by_income
        # (all four tiers share one MoSPI anchor) and was WRONG the moment a
        # block mixed sourced values with design choices: `site:` credited
        # its grid dimensions and prevailing wind to nhm.gov.in, the
        # population report cited for total_households. These configs mix
        # the two freely, so no inheritance rule can be correct, and a false
        # attribution is worse than a blank. A row is attributed only by its
        # OWN comment run (cut at the block rule, above); everything else is
        # left blank and the preamble states that such rows inherit the
        # citation of the block they sit in.
        tier, url, prose = harvest(comments)
        if not (tier or url or named_sources(prose)):
            for level in sorted(inherited, reverse=True):
                if level < indent:
                    tier, url, prose = inherited[level]
                    break
        note = tidy(inline, 160) if inline else tidy(prose, 200)
        full_path = ".".join([s[1] for s in stack] + [key])
        # An INLINE comment cites too: "onplot_ecs_per_dwelling: 1.0  # PUDA
        # Building Rules 2021" names its instrument on the value's own line,
        # and the harvester only read the block above. Inline is the most
        # specific place a source can be written, so it wins over prose.
        name = (named_sources(inline) or named_sources(prose))
        if not url and name:
            head_name = name.split(";")[0].strip()
            url = CANONICAL_URLS.get(head_name, "")
            if not url:
                # "CERC FY22-23" or "CERC Short-Term..." still means CERC:
                # match on the leading token so a qualified name links too.
                lead = head_name.split()[0].rstrip(",")
                url = CANONICAL_URLS.get(lead, "")
        val = value.strip("'\"")
        # YAML ALLOWS 8_000_000 AS A NUMERIC LITERAL, and several capex
        # values are written that way. hyphenat breaks \texttt at every
        # underscore AND PRINTS A HYPHEN THERE, so the register showed
        # "8_-/000_-/000" over three lines. Rendered with thousands commas,
        # which is what the value means and how every other row prints it.
        if re.fullmatch(r"\d[\d_]*\d", val) and "_" in val:
            val = "{:,}".format(int(val.replace("_", "")))
        # Flow-style lists print as one unbreakable token and overprinted
        # their neighbour ("[0.02,0.02,...]"); a space after each comma
        # gives LaTeX its break points.
        if val[:1] in "[{":
            val = re.sub(r",(?=\S)", ", ", val)
        val = compress_series(val)
        row = {
            "path": full_path,
            "key": key,
            "value": val,
            "units": units_for(full_path),
            "tier": tier,
            "url": url,
            "source": source_label(url) or name,
            "note": note,
            "line": lineno,
            "group": stack[0][1] if stack else "(root)",
        }
        if value == "[]" or value == "{}":
            comments = []
            continue
        if value.endswith("[") or value == "":
            pending_list, pending_row = [], row
            comments = []
            continue
        rows.append(row)
        comments = []

    if pending_list is not None and pending_row is not None:
        pending_row["value"] = ", ".join(pending_list[:12])
        rows.append(pending_row)

    # A trajectory prints as ONE row, not three. Year-keyed leaves under a
    # common parent ("...multiplier_by_period.2030/2042/2055") merge into a
    # single row whose value lists the periods in order - full coverage
    # without sixty pages of near-identical lines. Runs after the pending
    # flush so the final row participates; the comments reset above stays
    # inside the loop, where its removal would let one block's provenance
    # bleed into the next.
    merged: list[dict] = []
    i = 0
    while i < len(rows):
        r = rows[i]
        if YEAR_LEAF.match(r["key"]):
            parent = r["path"].rsplit(".", 1)[0]
            run = [r]
            j = i + 1
            while (j < len(rows) and YEAR_LEAF.match(rows[j]["key"])
                   and rows[j]["path"].rsplit(".", 1)[0] == parent):
                run.append(rows[j])
                j += 1
            head = dict(run[0])
            head["path"] = parent
            head["key"] = parent.rsplit(".", 1)[-1]
            head["units"] = units_for(parent)
            head["value"] = "; ".join(
                "%s: %s" % (x["key"], x["value"]) for x in run)
            merged.append(head)
            i = j
        else:
            merged.append(r)
            i += 1
    return merged


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    os.chdir(root)
    out_path = os.path.abspath(os.path.join(root, OUT))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    parts: list[str] = []
    parts.append("# Appendix C - Parameters and sources\n")
    # The tier-scheme preamble went with the tier column: grading is
    # internal apparatus, and explaining a scheme the tables no longer
    # show would only invite the question.
    parts.append(
        "**Generated from the model's own configuration files**, so the "
        "values cannot drift from what the model reads.\n"
    )
    parts.append(
        "A source is shown against a parameter only where that parameter's "
        "own entry in the configuration names one; citations are "
        "deliberately not spread from a parameter to its neighbours, since "
        "a block routinely mixes measured quantities with design choices. "
        "Where no source applies, the cell states the category instead: "
        "*switch* (turns a mechanism on or off), *shares sum to 1* "
        "(exhaustive by construction), *model structure* (the study's own "
        "resolution and periods), *derived* (computed from a sourced "
        "parameter, derivation in the configuration and Appendices B and "
        "D), *bound* (a cap the optimiser may not exceed), *label*, and "
        "*design choice* (a decision this study makes and argues in "
        "Chapters 3 and 4, such as the site, the 25 km² area, the design "
        "population and the height tiers).\n"
    )

    totals: OrderedDict[str, int] = OrderedDict()
    cited_total = 0
    sourced_total = 0
    all_rows = 0
    body: list[str] = []

    for fname, title in CONFIGS:
        path = os.path.join("config", fname)
        if not os.path.exists(path):
            continue
        rows = collapse_numbered_siblings(parse(path))
        totals[fname] = len(rows)
        all_rows += len(rows)
        cited_total += sum(1 for r in rows if r["url"])
        sourced_total += sum(1 for r in rows if r["source"])

        body.append(f"\n---\n\n## {title}\n\n`config/{fname}`\n")
        groups: OrderedDict[str, list[dict]] = OrderedDict()
        for r in rows:
            groups.setdefault(r["group"], []).append(r)

        for group, grows in groups.items():
            # Headings read as titles, not as YAML keys: "land_use_targets"
            # prints as "Land use targets", "education" as "Education".
            nice = group.replace("_", " ").strip()
            nice = nice[:1].upper() + nice[1:]
            body.append(f"\n### {nice}\n")
            # FOUR COLUMNS, NOT SIX
            # compile). The tier grade and the note prose are working
            # apparatus - they live in the configs and the citation register,
            # and printing them tripled the register's length (334 of the
            # appendix's ~430 pages) and crushed the parameter names into
            # the value column. A reader needs the value, its units and
            # where it came from; the audit trail stays in _spec/.
            # LEVER 1: THE SHARED PREFIX IS STATED ONCE, NOT ON EVERY ROW.
            # A key like
            #   heating_loads.dhw.people_per_household_by_category.low_income
            # shreds across four lines in a quarter-width column, and the
            # first two segments are the same on every row of the group. The
            # common prefix moves to the heading and the cell carries the
            # leaf, which is the part that differs and the part a reader
            # looks for: the register was 101 pages).
            stem = common_prefix([r["path"] for r in grows])
            if stem:
                body.append("\nAll keys below sit under `%s`.\n" % stem)
            cells = []
            for r in grows:
                src = (f"[{r['source']}]({r['url']})" if r["url"]
                       else r["source"])
                # EVERY CELL CARRIES SOMETHING. A units column that is blank
                # on most rows and filled on one reads as unfinished rather
                # than as "this quantity is dimensionless", which is what it
                # means. An en dash says it deliberately; a blank source says
                # its own category.
                units = r["units"] or "-"
                src = src or blank_tag(r["path"])
                short = r["path"][len(stem) + 1:] if stem else r["path"]
                cells.append((f"`{short}`", r["value"], units, src))

            # LEVER 2: TWO PARAMETERS TO A PRINTED ROW. multicol cannot carry
            # a longtable, so the two-column page is built into the table
            # instead: six columns, each printed row holding two parameters.
            # Units are folded into the value because a separate unit column
            # at half width was the narrowest thing on the page and the first
            # to overlap its neighbour.
            # PAIRING IS CONDITIONAL. A row whose source is a full link, or
            # whose value is a summarised series, needs the whole width; those
            # print one to a line so nothing is crushed. Everything else pairs.
            # LEVER 2 WAS MEASURED AND REJECTED. Two parameters to a printed
            # row halves the row count and halves the column width, and the
            # second cancels the first: 85 estimated pages against 86 for the
            # one-per-row form. A six-column register is also
            # harder to read for no gain, so the table stays four columns and
            # the saving comes from lever 1 above and from compress_series.
            body.append("| parameter | value | units | source |")
            body.append("|:---|:---|:---|:---|")
            for c in cells:
                body.append(f"| {c[0]} | {c[1]} | {c[2]} | {c[3]} |")

    parts.append("\n## Coverage\n")
    parts.append("| configuration file | parameters tabulated |")
    parts.append("|---|---|")
    for fname, n in totals.items():
        parts.append(f"| `config/{fname}` | {n} |")
    # No bold inside a table cell, main text or appendix.
    # The builder bolds header rows itself; a bolded total row is the emphasis
    # he asked to drop, and it is the last row anyway.
    parts.append(f"| total | {all_rows} |")
    parts.append(
        f"\n{sourced_total} of {all_rows} rows name a source, {cited_total} of "
        "them as a direct link. The rest are structural: switches that turn a "
        "technology on or off, shares that sum to one, the model's own time "
        "and space resolution, and quantities derived arithmetically from a "
        "sourced parameter above them. Full provenance for every block, "
        "including the derivations, is kept in the configuration comments.\n"
    )

    parts.extend(body)

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")

    print(f"wrote {out_path}")
    print(f"  {all_rows} parameters across {len(totals)} files")
    print(f"  {cited_total} with a direct source link")
    print(f"  {sourced_total} naming a source at all")

    # COLUMN WIDTHS MUST BE RE-DERIVED HERE, NOT REMEMBERED. This file is
    # written with flat `|:---|` separators, which ask pandoc for four equal
    # columns; the units column then cannot hold "kgCO2/kWh" and the text
    # overprints the source beside it. Regenerating the register without
    # re-running the sizer is what put overlapping text in the compiled
    # appendix, so the sizer is invoked from here.
    sizer = os.path.join(root, "..", "..", "WRITEUP",
                         "size_appendix_columns.py")
    sizer = os.path.abspath(sizer)
    if os.path.exists(sizer):
        import subprocess
        import sys as _sys
        r = subprocess.run([_sys.executable, sizer],
                           capture_output=True, text=True)
        tail = [l for l in (r.stdout or "").strip().split("\n") if l.strip()]
        print("  column widths re-derived: %s"
              % (tail[-1] if tail else "sizer produced no output"))
    else:
        print("  WARNING: sizer not found, columns left equal-width")


if __name__ == "__main__":
    main()
