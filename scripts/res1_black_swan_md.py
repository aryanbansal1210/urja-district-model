"""Render the priced-shock CSV as the markdown table the appendix expects.

WHY THIS EXISTS. `res1_black_swan_pack.py` writes `res1_black_swan.csv` and
nothing else, while every other resilience and sweep artefact in
`outputs/data/energy/` is a standalone markdown table. Appendix H therefore
reported the 72-hour autonomy simulation and nothing about the shock cases,
because the generator assembles the appendix from markdown files and there was
no markdown file to find. The numbers existed and were simply invisible.

Reads the CSV, writes the table. No solving, no re-running the pack.

    python scripts/res1_black_swan_md.py
"""
from __future__ import annotations

import collections
import csv
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "outputs", "data", "energy", "res1_black_swan.csv")
OUT = os.path.join(ROOT, "outputs", "data", "energy", "res1_black_swan.md")

# The CSV's case ids are terse. These are what the thesis calls them.
LABELS = {
    "a_blackout_jan": "Total import loss, January",
    "a_blackout_jul": "Total import loss, July",
    "b_heatwave": "Heatwave, raised cooling demand",
    "c_straw_lost": "Straw harvest lost",
    "d_canal_dec": "Canal supply interrupted",
    "e_n1_import": "Largest network element lost",
    "voll_20": "Total import loss at a lower value of lost load",
}


def main() -> int:
    rows = [r for r in csv.DictReader(io.open(SRC, encoding="utf-8"))
            if r["case"] != "null"]
    by = collections.OrderedDict()
    for r in rows:
        by.setdefault(r["case"], []).append(r)

    lines = ["# Priced shock cases", "",
             "Each shock is imposed on the frozen build and the system re-solved. "
             "**Critical load is the quantity that matters**: the district is "
             "designed to keep hospitals, water treatment and lit streets running, "
             "not to keep every load running.", "",
             "| case | total demand served | critical served | operating cost effect |",
             "|---|---|---|---|"]

    for case, rs in by.items():
        served = [float(r["served_pct_window"]) for r in rs]
        delta = [float(r["op_cost_delta_minr"]) for r in rs]
        crit = sorted({float(r["crit_served_pct_window"]) for r in rs})
        s = ("%.1f %%" % served[0] if max(served) - min(served) < 0.05
             else "%.1f to %.1f %%" % (min(served), max(served)))
        c = ("%.1f %%" % crit[0] if len(crit) == 1
             else "%.1f to %.1f %%" % (crit[0], crit[-1]))
        lo, hi = min(delta), max(delta)
        d = ("%+.1f M INR/yr" % lo if abs(hi - lo) < 0.05
             else "%+.1f to %+.1f M INR/yr" % (lo, hi))
        lines.append("| %s | %s | %s | %s |" % (LABELS.get(case, case), s, c, d))

    allcrit = {float(r["crit_served_pct_window"]) for r in rows}
    lines += ["",
              "Critical service is **%s** in every case and every period."
              % ("100 per cent" if allcrit == {100.0}
                 else "NOT uniform - read the table"),
              "",
              "A negative cost effect means the shock made the modelled year "
              "cheaper to operate, which happens when demand goes unserved: the "
              "saving is an artefact of the outage, not a benefit, and the "
              "value-of-lost-load column in the CSV is what prices it properly.",
              "",
              "Source `res1_black_swan.csv`, written by "
              "`scripts/res1_black_swan_pack.py`."]

    io.open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("wrote %s (%d cases)" % (OUT, len(by)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
