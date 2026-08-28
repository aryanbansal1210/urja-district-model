"""Render the three battery sweeps as the markdown Appendix G assembles from.

WHY THIS EXISTS. `battery_capex_sweep_20260822.py`,
`battery_breakpoint_20260822.py` and `battery_lifetime_value_20260822.py` each
write a `.json` and nothing else, while the appendix generator builds Appendix G
by reading `.md` files out of `outputs/data/energy/`. So all three sweeps were
invisible to the appendix, and Appendix G still showed only "G.3.1 Battery entry
price, EARLIER RUN" from a superseded basis.

That mattered more than a missing table. Section 5.7.4 was about to be trimmed
against Appendix G on the assumption that G already carried the battery result.
It did not, and the trim would have deleted the only copy.

This is the SECOND instance of the same defect - `res1_black_swan_pack.py` had
it too, fixed on by `res1_black_swan_md.py`. **Any sweep script that
writes only JSON is invisible to the appendix.** Worth a sweep of `scripts/`
for others before the next appendix regeneration.

Reads the three JSONs, writes three markdown tables. No solving.

    python scripts/battery_sweeps_md.py
"""
from __future__ import annotations

import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "outputs", "data", "energy")

RS = "Rs "


def _load(name):
    with io.open(os.path.join(DATA, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def _kwh(v):
    v = float(v or 0)
    return "0" if v <= 0 else format(v, ",.0f")


def capex_sweep():
    d = _load("battery_capex_sweep_20260822")
    out = ["# Battery capital cost, published system prices", "",
           "Each row re-solves the whole system at that capital cost. The first "
           "row is the production value. **The base year builds no storage at "
           "any price tested**, which is what makes that claim structural "
           "rather than economic.", "",
           "| basis | %s/kWh | USD/kWh | 2030 | 2042 | 2055 |" % RS.strip(),
           "|---|---:|---:|---:|---:|---:|"]
    for c in d["cases"]:
        b = c["battery_by_period_kwh"]
        out.append("| %s | %s | %.0f | %s | %s | %s |" % (
            c["label"], format(c["capex_inr_per_kwh"], ","), c["usd_per_kwh"],
            _kwh(b.get("2030")), _kwh(b.get("2042")), _kwh(b.get("2055"))))
    out += ["", "Converted at %s%.0f per US dollar."
            % (RS, d.get("fx_inr_per_usd", 85.0)),
            "", "Source `battery_capex_sweep_20260822.json`."]
    return "battery_capex_sweep_20260822.md", "\n".join(out) + "\n"


def breakpoint():
    d = _load("battery_breakpoint_20260822")
    lo, hi = d["bracket_lo_inr_per_kwh"], d["bracket_hi_inr_per_kwh"]
    fx = d.get("fx_inr_per_usd", 85.0)
    out = ["# Battery capital cost, the price at which storage disappears", "",
           "A bisection on capital cost. **All storage vanishes between "
           "%s%s and %s%s per kWh**, which is USD %.0f to %.0f. The decline is "
           "gradual rather than a cliff, so the bracket rather than a single "
           "figure is the defensible statement."
           % (RS, format(lo, ",.0f"), RS, format(hi, ",.0f"), lo / fx, hi / fx),
           "",
           "| %s/kWh | USD/kWh | any battery built | 2055 kWh |" % RS.strip(),
           "|---:|---:|---|---:|"]
    for t in sorted(d["trace"], key=lambda r: r["capex_inr_per_kwh"]):
        b = t["battery_by_period_kwh"]
        out.append("| %s | %.0f | %s | %s |" % (
            format(t["capex_inr_per_kwh"], ",.0f"), t["usd_per_kwh"],
            "yes" if t["any_battery_built"] else "**no**", _kwh(b.get("2055"))))
    out += ["", "Source `battery_breakpoint_20260822.json`."]
    return "battery_breakpoint_20260822.md", "\n".join(out) + "\n"


def lifetime_value():
    d = _load("battery_lifetime_value_20260822")
    base = d["cases"][0]
    out = ["# What storage is worth over the horizon", "",
           "**The base year cannot answer this**: the battery is zero in every "
           "case there, so the value has to be read across the horizon with the "
           "period weights the objective uses (%s)."
           % ", ".join("%s x%.0f" % (k, v)
                       for k, v in sorted(d["period_weights"].items())),
           "",
           "| case | %s/kWh | lifetime cost | cumulative Mt | vs production |"
           % RS.strip(),
           "|---|---:|---:|---:|---:|"]
    for c in d["cases"]:
        dc = c["lifetime_cost_inr"] - base["lifetime_cost_inr"]
        out.append("| %s | %s | %s | %.4f | %s |" % (
            c["label"], format(c["capex_inr_per_kwh"], ","),
            format(c["lifetime_cost_inr"], ",.0f"), c["cumulative_mt"],
            "base" if dc == 0 else "+%s" % format(dc, ",.0f")))
    worst = d["cases"][-1]
    dc = (worst["lifetime_cost_inr"] / base["lifetime_cost_inr"] - 1) * 100
    dm = (worst["cumulative_mt"] / base["cumulative_mt"] - 1) * 100
    out += ["",
            "Removing storage entirely raises lifetime cost by **%.2f per "
            "cent** and cumulative emissions by **%.2f per cent**. The "
            "asymmetry is the result: storage costs this district a little and "
            "saves it a great deal of carbon, so an appraisal on cost alone "
            "understates what the asset is for." % (dc, dm),
            "", "Source `battery_lifetime_value_20260822.json`."]
    return "battery_lifetime_value_20260822.md", "\n".join(out) + "\n"


def main() -> int:
    for fn in (capex_sweep, breakpoint, lifetime_value):
        name, text = fn()
        path = os.path.join(DATA, name)
        io.open(path, "w", encoding="utf-8").write(text)
        print("wrote %s (%d chars)" % (name, len(text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
