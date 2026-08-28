"""Generate Appendix G (sensitivity) and Appendix H (resilience).

Both are assembled from the sweep and resilience artefacts in
`outputs/data/energy/`, each of which is a standalone markdown table written by
the script that ran the solves.

The one thing this generator does that a copy-paste would not: it dates every
artefact against the current results file and says plainly which sweeps were run
on the current baseline and which predate it. A sensitivity quoted from an
earlier baseline is the exact failure the project has already been caught by
once, so the appendix states the provenance rather than hiding it.

Run from the repo root:
    python scripts/appendix_gh_sensitivity_resilience.py
"""
from __future__ import annotations

import os
import re
from datetime import datetime

ENERGY = os.path.join("outputs", "data", "energy")
BASELINE = os.path.join(ENERGY, "dispatch_results.json")
OUT_G = os.path.join("..", "..", "WRITEUP", "APPENDIX", "G_sensitivity.md")
OUT_H = os.path.join("..", "..", "WRITEUP", "APPENDIX", "H_resilience.md")

# file, heading, what the sweep tests, whether the conclusion is load-bearing
#. Four sweeps were written and run tonight and would not have
# appeared here, because this list is the registry: a sweep the generator does
# not know about is invisible to the appendix no matter how current its artefact
# is. Two of them REPLACE entries further down that predate the baseline - the
# battery entry price and the grid price scenario - so those older rows now
# carry a note pointing here rather than being silently duplicated.
SWEEPS = [
    # BATT-MD. The three battery sweeps of wrote JSON
    # and nothing else, so this generator could not see them and Appendix G
    # still showed only the SUPERSEDED "battery entry price, earlier run".
    # Caught while trimming Section 5.7.4 against Appendix G: the trim assumed
    # G already carried the battery result, and it did not, so the only copy
    # would have been deleted. Markdown now produced by
    # `scripts/battery_sweeps_md.py`. SECOND instance of this defect after
    # res1_black_swan - a sweep that writes only JSON is invisible here.
    ("battery_capex_sweep_20260822.md", "Battery capital cost, published prices",
     "Whether the base year builds no storage because of economics or because "
     "of structure. The answer separates two claims Section 5.2.1 makes about "
     "storage and must not be read from the base year alone."),
    ("battery_breakpoint_20260822.md", "Battery capital cost, the disappearance point",
     "A bisection for the price at which storage leaves the solution "
     "altogether, reported as a bracket because the decline is gradual."),
    ("battery_lifetime_value_20260822.md", "What storage is worth over the horizon",
     "The base year cannot answer this, since the battery is zero in every "
     "case there. Read across the horizon the answer is asymmetric: storage "
     "costs little and saves a great deal of carbon."),
    ("tariff_protection_sweep_20260822.md", "Grid tariff protection",
     "Whether a district that imports less is measurably less exposed to the "
     "price of imports. Both the district and the counterfactual are re-solved "
     "at every step, because a shock applied to one side alone proves nothing."),
    ("demand_sensitivity_20260822.md", "District demand, plus or minus 20 per cent",
     "Demand is derived bottom-up rather than measured, which Section 6.3.5 "
     "states as a limitation, so whether the saving survives a wide swing in it "
     "is the strongest available answer to that limitation."),
    ("discount_rate_sweep.md", "Inter-period discount rate",
     "Whether the build timing survives a non-zero social discount rate. The "
     "objective weights periods without discounting, which favours early building."),
    ("export_price_sweep_20260819.md", "Export tariff",
     "How much of the result rests on the price paid for exported generation."),
    ("cool_ac1_sweep.md", "Air-conditioning peak demand",
     "The cooling peak is the single parameter that moved the headline most in "
     "the August audit, at 0.78 percentage points."),
    ("dsr_band_sweep.md", "Demand-response depth",
     "How much the answer depends on the assumed share of peak load that can be "
     "shifted."),
    ("v2g_capex_sweep.md", "Vehicle-to-grid capital cost",
     "V2G carries one of the least well-sourced costs in the model, so its build "
     "order needs to survive a wide price range."),
    ("fx2_6_b1_sweep.md", "Battery entry price, earlier run",
     "SUPERSEDED 2026-08-22 by the battery capital-cost sweep reported in "
     "Section 5.7.4, which found the 2042 entry to be cost-contingent rather "
     "than structural. Retained for provenance; do not quote its levels."),
    ("fx2_6_demand_sensitivity.md", "District demand, earlier run",
     "SUPERSEDED 2026-08-22 by the demand sweep above, which is on the current "
     "baseline. Retained for provenance."),
    ("ai_price_sweep.md", "Data-centre and AI load",
     "Whether rising external demand is upside or risk for the district."),
    ("ppa_shape_sweep.md", "Contracted offtake shape",
     "How the data-centre contract behaves under different hourly profiles."),
    ("export_price_sweep.md", "Export tariff, earlier run",
     "Superseded by the August run above; retained for provenance."),
    ("green_cap_sweep.md", "Green open-access purchase cap",
     "How much the regional purchase option is worth at different volume caps."),
    ("f3_solar_land_sweep.md", "Solar land allocation",
     "How the headline responds to the share of the site reserved for the farm."),
    ("b21_dc_anchor_land_sweep.md", "Regional anchor land",
     "Land required by the regional integration blocks."),
    ("price_scenario_sweep.md", "Grid price scenario, earlier run",
     "SUPERSEDED 2026-08-22 by the tariff-protection sweep above, which "
     "re-solves BOTH sides rather than the district alone. Retained for "
     "provenance."),
]

#: the shock pack was re-run on the current pins and its
# artefact was not in this list at all, so Appendix H reported the autonomy
# simulation and nothing else.
RESILIENCE = [
    ("res1_autonomy_72h.md", "72-hour chronological autonomy simulation"),
    ("res1_black_swan.md", "Priced shock cases"),
]


# containing one of these is carrying prose or figures from an older baseline,
# EVEN IF the file itself was re-run recently - the numbers may be current while
# the commentary around them is not. Detected and flagged inline rather than
# silently reproduced.
SUPERSEDED = {
    "1,841,569,555": "previous town annual cost",
    "116,638,892": "previous town annual emissions",
    "49.4567": "previous vs-BAU cost saving",
    "62.5096": "previous vs-BAU emissions saving",
    "63,247,015,703": "previous lifetime cost",
    "82,725": "previous rooftop PV capacity",
    "148,452": "rooftop PV capacity from an earlier baseline still",
    "214,914": "previous solar farm capacity, 2030",
    "247,151": "previous solar farm capacity, 2055",
    "493,989": "previous battery capacity",
    "0.0714": "previous ground-mount density",
}


# A superseded value is a DEFECT when the prose still relies on it, and is
# PROVENANCE when the prose names it in order to retire it. This scanner
# originally could not tell the two apart, so once the export sweep was fixed to
# say "148,452.2 kWp against 116,886.3 kWp now" the caution box it emitted
# became false: it warned that current prose was stale. Same false-positive
# class as WRITEUP/sync_audit.py hit on with a provenance comment.
# The test is per SENTENCE, not per file, because a long artefact can carry both
# at once. A sentence that supersedes something says so - it names the
# replacement, or it uses supersession language.
SUPERSESSION_CUES = ("supersede", "Supersede", "previous", "earlier", "was ",
                     "retired", "no longer", "against", "do not quote",
                     "stale", "old ", "OLD ", "->")


def _is_provenance(sentence: str) -> bool:
    return any(cue in sentence for cue in SUPERSESSION_CUES)


def superseded_in(text: str) -> list[str]:
    """Superseded values the prose still RELIES on, ignoring ones it retires."""
    sentences = re.split(r"(?<=[.!?])\s+|\n", text)
    hits = []
    for k, why in SUPERSEDED.items():
        carrying = [s for s in sentences if k in s and not _is_provenance(s)]
        if carrying:
            hits.append(f"`{k}` ({why})")
    return hits


def stamp(path: str) -> datetime | None:
    return datetime.fromtimestamp(os.path.getmtime(path)) if os.path.exists(path) else None


def body(path: str) -> str:
    """The artefact's own table and commentary, minus its H1."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    out = [ln for ln in lines if not ln.startswith("# ")]
    while out and not out[0].strip():
        out.pop(0)
    # HEADERS ARE NORMALISED ON THE WAY IN. The artefacts write a dictionary
    # key with its underscores swapped for spaces, so `voll_inr_per_kwh`
    # arrives as "voll inr per kwh" - a variable name shown to a reader. The
    # body is otherwise copied VERBATIM, which is what stops the numbers
    # drifting, so this is the one place to fix it for every artefact at once.
    from table_headers import fix_markdown
    txt = fix_markdown(chr(10).join(out))
    return txt.replace(chr(8212), " - ").rstrip()


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    os.chdir(root)

    base = stamp(BASELINE)
    if base is None:
        raise SystemExit("dispatch_results.json not found")

    current, stale, missing = [], [], []
    for fname, heading, why in SWEEPS:
        path = os.path.join(ENERGY, fname)
        ts = stamp(path)
        if ts is None:
            missing.append((fname, heading))
        elif ts >= base:
            current.append((fname, heading, why, ts))
        else:
            stale.append((fname, heading, why, ts))

    # ---------------------------------------------------------------- G
    G = []
    A = G.append
    A("# Appendix G - Sensitivity and scenario analysis\n")
    A(
        "**Generated by `scripts/appendix_gh_sensitivity_resilience.py`.** Each "
        "section is the output of the script that ran the solves, reproduced without "
        "editing.\n"
    )
    A(
        f"**Provenance.** The production results were last regenerated on "
        f"{base:%d %B %Y at %H:%M}. Every sweep below is dated against that run. "
        "Sweeps re-run after it are on the current baseline. Sweeps predating it were "
        "run on an earlier formulation, and while their *direction* is informative "
        "their absolute figures are not comparable with the headline. They are listed "
        "separately rather than quietly mixed in.\n"
    )

    # FIGURE G.1,. The appendix held 2,364 table rows and one
    # figure. This is NOT a second frontier chart - Figure 5.7 already plots the
    # frontier in the main text and F.7 tabulates it. It shows the one thing
    # neither can: F.7 own note that the annual basis looks flat over much of
    # its range and is not monotone, while the horizon basis does not. The two
    # panels differ in exactly one variable, the basis, per the house rule.
    A("\n![Cost and carbon frontier, annual basis against horizon basis]"
      "(../figures/png/fig_g_1_frontier_basis.png)\n")
    A("**Figure G.1.** The eleven frontier solves read two ways. On the "
      "base-year annual basis the low-alpha solves collapse into one cluster "
      "and most of the frontier is invisible; the horizon basis separates them. The "
      "solves are identical and only the basis differs, which is why F.7 "
      "directs the reader to the horizon figures. Built by "
      "`WRITEUP/figures/build_appendix_figures.py` from `dispatch_results.json`.\n")

    A("\n## G.1 Coverage\n")
    A("| sweep | run | on current baseline |")
    A("|---|---|---|")
    for fname, heading, _why, ts in current:
        A(f"| {heading} | {ts:%d %b %Y} | yes |")
    for fname, heading, _why, ts in stale:
        A(f"| {heading} | {ts:%d %b %Y} | no, predates the re-pin |")
    for fname, heading in missing:
        A(f"| {heading} | not found | - |")

    # THE CLOSING SENTENCE WENT STALE THE MOMENT THE RE-SWEEP FINISHED. It said
    # re-running the remainder "is listed as outstanding work", true when nine
    # "earlier run" entries whose CURRENT counterpart is already in the table
    # so re-running them would destroy the comparison rather than improve it.
    # A generated sentence describing a backlog must be DERIVED from the
    # backlog, not written once beside it and left.
    earlier = [h for _f, h, _w, _t in stale if "earlier run" in h.lower()]
    tail = (
        f" All {len(earlier)} are *earlier run* entries whose current-basis "
        "counterpart appears above; they are retained as provenance, to show how "
        "each result moved across the re-pin, and re-running them would remove "
        "that comparison rather than add to it." + chr(10)
        if stale and len(earlier) == len(stale)
        else " Re-running them is outstanding work." + chr(10)
    )
    A(
        f"\n{len(current)} of {len(current) + len(stale)} sweeps sit on the current "
        "baseline. The remainder are reported in G.3 with their run date attached."
        + tail
    )

    A("\n---\n\n## G.2 Sweeps on the current baseline\n")
    flagged = []
    for i, (fname, heading, why, ts) in enumerate(current, 1):
        text = body(os.path.join(ENERGY, fname))
        A(f"\n### G.2.{i} {heading}\n")
        A(f"*{why}*\n")
        A(f"Run {ts:%d %B %Y}. Source `outputs/data/energy/{fname}`.\n")
        hits = superseded_in(text)
        if hits:
            flagged.append((heading, hits))
            A(
                "> **Caution.** This sweep was re-run on the current baseline, but its "
                "commentary still refers to " + ", ".join(hits) + ". The **sweep "
                "results** below are current; the **surrounding prose** was written "
                "against an earlier build and its comparison figures are stale. Quote "
                "the deltas, not the absolute reference values in the text.\n"
            )
        A(text)
        A("")

    A("\n---\n\n## G.3 Sweeps predating the current baseline\n")
    A(
        "Reported for completeness and for the mechanism each one demonstrates. **Do "
        "not read the absolute values against the headline in Appendix F**; they were "
        "produced on an earlier formulation. The relationships they show, such as the "
        "price at which storage enters, are the durable part.\n"
    )
    for i, (fname, heading, why, ts) in enumerate(stale, 1):
        text = body(os.path.join(ENERGY, fname))
        A(f"\n### G.3.{i} {heading}\n")
        A(f"*{why}*\n")
        A(f"Run {ts:%d %B %Y}, before the current re-pin. Source `outputs/data/energy/{fname}`.\n")
        hits = superseded_in(text)
        if hits:
            A(
                "> **Contains superseded values: " + ", ".join(hits) + ".** These are "
                "reproduced as run and must not be quoted as current. The relationship "
                "the sweep demonstrates is the durable part.\n"
            )
        A(text)
        A("")

    # ---------------------------------------------------------------- H
    H = []
    B = H.append
    B("# Appendix H - Resilience\n")
    B(
        "**Generated by `scripts/appendix_gh_sensitivity_resilience.py`** from the "
        "resilience artefacts. Method and citations are in "
        "`_spec/RES_1_RESILIENCE_PACK.md`.\n"
    )
    B("\n## H.1 What was tested\n")
    B(
        "Two things. First, a **total grid disconnection** lasting a month, solved in "
        "every investment period, to establish what the town can still serve on its "
        "own generation. Second, four **partial shocks** priced as annual cost: a "
        "heatwave, loss of the straw supply, closure of the canal, and loss of one "
        "transmission corridor.\n"
    )
    B(
        "Unserved energy enters the linear program as a variable priced at the value of "
        "lost load, so a scenario that cannot serve demand pays for it rather than "
        "simply being infeasible. That is what makes the shock cases comparable in "
        "money.\n"
    )
    B("\n## H.2 Critical load, and an honesty note\n")
    B(
        "Critical load is the hospital campus, water treatment and grid-fed street "
        "lighting, plus sewage and telecom lifeline proxies of about 1.22 MW combined. "
        "**Those last two are boundary loads that sit outside the LP's demand model**, "
        "so they are included in the chronological simulation's ledger but are not LP "
        "demand. The distinction is stated here rather than buried, because it changes "
        "what the percentage means.\n"
    )

    for i, (fname, heading) in enumerate(RESILIENCE, 1):
        path = os.path.join(ENERGY, fname)
        ts = stamp(path)
        if ts is None:
            continue
        B(f"\n---\n\n## H.{2 + i} {heading}\n")
        note = "on the current baseline" if ts >= base else (
            "**run before the current re-pin**, so absolute energies correspond to the "
            "previous build; the served-percentage result is structural and holds")
        B(f"Run {ts:%d %B %Y}, {note}. Source `outputs/data/energy/{fname}`.\n")
        B(body(path))
        # FIGURE H.1 sits with the 72-hour run and nothing else, because the
        # finding IS the gap between the two series and a six-row table makes
        # the reader compute it.
        if "autonomy" in fname:
            B("\n![Seventy-two hour autonomy, total against critical load]"
              "(../figures/png/fig_h_1_autonomy_72h.png)\n")
            B("**Figure H.1.** Six cases, two series. The critical series is "
              "pinned at 100 % in all six; the total series is not, and that "
              "gap is the result. Critical load is the hospital campus, water "
              "treatment and grid-fed street lighting, plus the sewage and "
              "telecom lifeline proxies described in H.2. Built by "
              "`WRITEUP/figures/build_appendix_figures.py` from "
              "`res1_autonomy_72h.md`.\n")
        B("")

    csv_path = os.path.join(ENERGY, "res1_black_swan.csv")
    if os.path.exists(csv_path):
        ts = stamp(csv_path)
        B(f"\n---\n\n## H.4 Black-swan solve pack\n")
        B(f"Run {ts:%d %B %Y}. Source `outputs/data/energy/res1_black_swan.csv`.\n")
        with open(csv_path, encoding="utf-8") as fh:
            rows = [r.rstrip("\n").split(",") for r in fh if r.strip()]
        if rows:
            head = rows[0]
            B("| " + " | ".join(h.replace("_", " ") for h in head) + " |")
            B("|" + "---|" * len(head))
            for r in rows[1:]:
                B("| " + " | ".join(r) + " |")

    B(
        "\n---\n\n## H.5 What is not solved\n"
    )
    B(
        "The **compound case** is the town's real worst case and it has not been "
        "solved: a straw supply ban during a grid blackout removes the fleet that "
        "carries the critical load in the single-shock cases. The single-shock results "
        "should not be read as implying the compound case is also covered.\n"
    )
    B(
        "The heatwave case lifts the whole demand profile rather than only the cooling "
        "dayparts, which overstates the shock slightly. The critical-load percentage in "
        "the LP leg is over modelled components only, per H.2.\n"
    )

    for path, parts in ((OUT_G, G), (OUT_H, H)):
        full = os.path.abspath(os.path.join(root, path))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write("\n".join(parts).replace("—", " - ") + "\n")
        print(f"wrote {full}")

    print(f"  baseline regenerated {base:%Y-%m-%d %H:%M}")
    print(f"  sweeps on current baseline: {len(current)}")
    print(f"  sweeps predating it: {len(stale)}")
    if flagged:
        print("  WARNING - re-run sweeps whose PROSE still cites superseded values:")
        for heading, hits in flagged:
            print(f"    {heading}: {', '.join(h.split(' (')[0] for h in hits)}")
    if missing:
        print(f"  not found: {[m[0] for m in missing]}")


if __name__ == "__main__":
    main()
