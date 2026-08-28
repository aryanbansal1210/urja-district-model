"""Reproduce the eMARC WINTER daily-consumption anchors.

WHY THIS EXISTS. `core/land_use.py` anchors all three residential base loads to
measured eMARC winter whole-house consumption:

    Basic                     3.44 kWh/day   (n=82)
    Water heaters, no AC      4.44           (n=27)
    With air conditioners     5.15           (n=23)
    North India subset, Basic 3.29

Those three numbers drive (base load, -24.4% district demand) and
(the water-heating double count, -6.25%), and the subtraction is the GAP
between the first two. But `scripts/emarc_load_shape.py` does NOT compute them -
it computes load SHAPES (kW by daypart) from a different file, and reports
different deployment counts (Basic n=90, not 82). So the levels had no script.

This closes that: the numbers now come from a re-runnable script, not a comment.

DELIBERATELY STDLIB ONLY. `emarc_load_shape.py` needs pandas, which is in
NEITHER environment on this machine (the canonical env has no pandas; base has a
broken numpy), so that script cannot currently be re-run at all. The daily file
is 111k rows, so csv + statistics is plenty and the anchors stay reproducible
with no new dependency.

Source: Prayas (Energy Group), eMARC processed data, Harvard Dataverse
doi:10.7910/DVN/YJ5SP1. 15-min IoT smart-meter data, 143 mainline deployments,
five Indian locations, Jan 2018 - Jun 2020. Tier 2, MEASURED not modelled.

Run:  python scripts/emarc_daily_anchors.py
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

SRC = r"C:\Users\aryan\Downloads\dataverse_files\eMAR daily consumption.csv"
OUT = os.path.join("outputs", "verification", "emarc_daily_anchors.txt")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
_log = open(OUT, "w", encoding="utf-8")


def emit(s=""):
    print(s, flush=True)
    _log.write(s + "\n")
    _log.flush()


# land_use.py describes the anchor as measured WINTER (Nov-Feb) whole-house
# load, chosen because no Indian region runs cooling in those months, so the
# figure is base + water heating with no cooling contamination.
WINTER = {11, 12, 1, 2}
NORTH = {"Kanpur rural", "Gonda"}          # UP, Indo-Gangetic, Punjab analogue
TYPES = ["Basic", "Water Heaters but no AC", "With Air Conditioners"]

# What the code comments claim, so the script can check itself.
CLAIMED = {"Basic": (3.44, 82),
           "Water Heaters but no AC": (4.44, 27),
           "With Air Conditioners": (5.15, 23)}

if not os.path.exists(SRC):
    emit("SOURCE NOT FOUND: %s" % SRC)
    emit("The eMARC download is not on this machine, so the anchors cannot be")
    emit("reproduced. Re-download from doi:10.7910/DVN/YJ5SP1.")
    _log.close()
    sys.exit(1)

emit("eMARC WINTER daily-consumption anchors")
emit("Prayas (Energy Group), Harvard Dataverse doi:10.7910/DVN/YJ5SP1")
emit("=" * 70)

# household_id -> daily kWh values, per scope
per_hh = {"all": defaultdict(list), "north": defaultdict(list)}
hh_type = {}
rows = kept = bad_date = 0

with open(SRC, "r", encoding="utf-8-sig", newline="") as fh:
    for r in csv.DictReader(fh):
        rows += 1
        if (r.get("Deployment type") or "").strip().lower() != "mainline":
            continue
        ht = (r.get("Household type") or "").strip()
        if ht not in CLAIMED:
            continue
        try:                                   # file is M/D/YYYY
            month = int((r["Date"] or "").split("/")[0])
        except (ValueError, IndexError, KeyError):
            bad_date += 1
            continue
        if month not in WINTER:
            continue
        try:
            kwh = float(r["Daily consumption (kWh)"])
        except (TypeError, ValueError):
            continue
        hid = r["household_id"]
        hh_type[hid] = ht
        per_hh["all"][hid].append(kwh)
        if (r.get("Region") or "").strip() in NORTH:
            per_hh["north"][hid].append(kwh)
        kept += 1

emit("rows read %s | winter mainline day-records kept %s | unparsed dates %d"
     % (f"{rows:,}", f"{kept:,}", bad_date))
emit("")
emit("Method: mean daily kWh PER HOUSEHOLD first, then the mean across")
emit("households. Averaging raw day-records instead would let a household with")
emit("a longer record dominate the mean - the same weighting trap that makes")
emit("emarc_load_shape.py's row-weighted shapes worth a second look.")
emit("")


def report(scope, label):
    emit("=" * 70)
    emit(label)
    emit("=" * 70)
    emit("  %-26s %10s %8s %10s %8s"
         % ("household type", "kWh/day", "n", "claimed", "n"))
    for ht in TYPES:
        vals = [sum(v) / len(v) for hid, v in per_hh[scope].items()
                if hh_type.get(hid) == ht and v]
        if not vals:
            emit("  %-26s %10s" % (ht, "no data"))
            continue
        mean = sum(vals) / len(vals)
        c_val, c_n = CLAIMED[ht]
        flag = "OK" if abs(mean - c_val) < 0.05 else "<-- DIFFERS"
        emit("  %-26s %10.2f %8d %10.2f %8d  %s"
             % (ht, mean, len(vals), c_val, c_n, flag))
    return {ht: [sum(v) / len(v) for hid, v in per_hh[scope].items()
                 if hh_type.get(hid) == ht and v] for ht in TYPES}


all_res = report("all", "1. ALL REGIONS, winter (Nov-Feb)")
emit("")
north_res = report("north", "2. NORTH INDIA ONLY (Kanpur rural + Gonda, UP)")

emit("")
emit("=" * 70)
emit("3. THE PA-B1c SUBTRACTION - the geyser component")
emit("=" * 70)
b = all_res.get("Basic") or []
w = all_res.get("Water Heaters but no AC") or []
if b and w:
    mb, mw = sum(b) / len(b), sum(w) / len(w)
    emit("  'water heaters, no AC' %.2f - 'basic' %.2f = %.2f kWh/day"
         % (mw, mb, mw - mb))
    emit("  PA-B1c used 1.00 (from the claimed 4.44 - 3.44).")
    emit("  %s" % ("CONFIRMED within 0.05." if abs((mw - mb) - 1.00) < 0.05
                   else "DIFFERS - PA-B1c's mid/high anchors need revisiting."))
    emit("")
    emit("  This gap is what PA-B1c subtracts from the MID and HIGH base")
    emit("  anchors (scaled x1.34 CEA x affluence). LOW is untouched because")
    emit("  'basic' is the no-water-heater tier.")
_log.close()
print("\nwrote %s" % OUT)
