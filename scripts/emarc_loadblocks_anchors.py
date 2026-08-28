"""Reproduce the eMARC WINTER anchors from the 15-MINUTE LOAD BLOCKS file.

WHY THIS EXISTS. `scripts/emarc_daily_anchors.py` reproduces the
anchors from the DAILY consumption file and gets 3.71 / 5.16 / 4.98 (gap 1.46).
But the values the model actually adopted - the 1.44 geyser gap, and the
geyser-stripped bases 3.53 / 3.53 / 3.44 behind the proposed re-base anchors
4.73 / 6.15 / 8.30 - come from the 15-MINUTE LOAD BLOCKS file instead, on the
argument that it is raw data with one less layer of upstream processing.

NOTHING IN THIS REPO COULD READ THAT FILE. `emarc_load_shape.py` needs pandas,
which is in NEITHER environment on this machine. So the numbers the model was
about to be re-based ONTO were themselves unreproducible - which is the exact
defect the re-base is meant to cure. This script closes that, stdlib only.

METHOD, deliberately identical to emarc_daily_anchors.py so the two are
comparable:
  * winter = Nov-Feb (no cooling anywhere in India, so whole-house load is
    base + water heating with no cooling contamination)
  * mainline deployments only
  * daily kWh = sum(Load kW) x 0.25 h over the day's 15-min blocks
  * mean per HOUSEHOLD first, then mean across households (averaging raw
    records would let a long-record household dominate)

The load-blocks file carries no household type or region, so deployment_id is
joined against "Household-Deployment basic info.xlsx".

Source: Prayas (Energy Group), eMARC processed data, Harvard Dataverse
doi:10.7910/DVN/YJ5SP1. Tier 2, MEASURED not modelled.

Run:  python scripts/emarc_loadblocks_anchors.py
"""
from __future__ import annotations

import csv
import os
import re
import sys
import zipfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

DL = r"C:\Users\aryan\Downloads\dataverse_files"
BLOCKS = os.path.join(DL, "eMARC load blocks.csv")
INFO = os.path.join(DL, "Household-Deployment basic info.xlsx")
OUT = os.path.join("outputs", "verification", "emarc_loadblocks_anchors.txt")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
_log = open(OUT, "w", encoding="utf-8")


def emit(s=""):
    print(s, flush=True)
    _log.write(s + "\n")


WINTER = {11, 12, 1, 2}
TYPES = ["Basic", "Water Heaters but no AC", "With Air Conditioners"]
# what the model adopted, so this script checks itself
ADOPTED = {"Basic": 3.53, "Water Heaters but no AC": 4.97,
           "With Air Conditioners": 4.88}

for p in (BLOCKS, INFO):
    if not os.path.exists(p):
        emit("SOURCE NOT FOUND: %s" % p)
        _log.close()
        sys.exit(1)


def read_xlsx(path):
    """Minimal stdlib xlsx reader -> list of row dicts."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
        shared = [re.sub(r"<[^>]+>", "", m)
                  for m in re.findall(r"<si>(.*?)</si>", ss, re.S)]
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8", "replace")
    rows = []
    for rm in re.finditer(r"<row[^>]*>(.*?)</row>", sheet, re.S):
        cells = {}
        for cm in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*)>(.*?)</c>',
                              rm.group(1), re.S):
            col, attr, body = cm.group(1), cm.group(2), cm.group(3)
            v = re.search(r"<v>(.*?)</v>", body, re.S)
            if not v:
                continue
            val = v.group(1)
            if 't="s"' in attr:
                try:
                    val = shared[int(val)]
                except (ValueError, IndexError):
                    pass
            cells[col] = val
        if cells:
            rows.append(cells)
    if not rows:
        return []
    hdr = rows[0]
    out = []
    for r in rows[1:]:
        out.append({hdr.get(c, c): v for c, v in r.items()})
    return out


info = read_xlsx(INFO)
emit("eMARC WINTER anchors from the 15-MINUTE LOAD BLOCKS file")
emit("Prayas (Energy Group), Harvard Dataverse doi:10.7910/DVN/YJ5SP1")
emit("=" * 70)
emit("household-info rows: %d | columns: %s"
     % (len(info), ", ".join(sorted(info[0].keys())) if info else "-"))


def pick(d, *names):
    for n in names:
        for k in d:
            if k and n.lower() in k.lower():
                return k
    return None


if not info:
    emit("could not parse the household info workbook")
    _log.close()
    sys.exit(1)

k_dep = pick(info[0], "deployment_id", "deployment id")
k_type = pick(info[0], "household type")
k_dtype = pick(info[0], "deployment type")
k_hh = pick(info[0], "household_id", "household id")
emit("keys -> dep=%s type=%s dtype=%s hh=%s" % (k_dep, k_type, k_dtype, k_hh))

dep_meta = {}
for r in info:
    dep = (r.get(k_dep) or "").strip()
    if not dep:
        continue
    dep_meta[dep] = {
        "type": (r.get(k_type) or "").strip(),
        "dtype": (r.get(k_dtype) or "").strip().lower(),
        "hh": (r.get(k_hh) or dep).strip(),
    }
emit("deployments mapped: %d" % len(dep_meta))
emit("")

# (household, date) -> kWh   built by streaming the 368 MB file
day_kwh = defaultdict(float)
day_blocks = defaultdict(int)
hh_type = {}
rows = kept = 0

with open(BLOCKS, "r", encoding="utf-8-sig", newline="") as fh:
    for r in csv.DictReader(fh):
        rows += 1
        dep = (r.get("deployment_id") or "").strip()
        meta = dep_meta.get(dep)
        if not meta or meta["dtype"] != "mainline":
            continue
        ht = meta["type"]
        if ht not in ADOPTED:
            continue
        d = (r.get("date") or "").strip()
        try:
            month = int(d.split("/")[0])
        except (ValueError, IndexError):
            continue
        if month not in WINTER:
            continue
        try:
            kw = float(r.get("Load (kW)") or "")
        except (TypeError, ValueError):
            continue
        hid = meta["hh"]
        hh_type[hid] = ht
        day_kwh[(hid, d)] += kw * 0.25          # 15-min block -> kWh
        day_blocks[(hid, d)] += 1
        kept += 1

emit("rows read %s | winter mainline block-records kept %s"
     % (f"{rows:,}", f"{kept:,}"))

# complete days only (96 x 15-min blocks); partial days would understate
complete = {k: v for k, v in day_kwh.items() if day_blocks[k] >= 96}
emit("household-days: %s total, %s complete (>=96 blocks)"
     % (f"{len(day_kwh):,}", f"{len(complete):,}"))
emit("")
emit("Method: daily kWh = sum(Load kW) x 0.25 h; mean per HOUSEHOLD first,")
emit("then mean across households. Complete days only.")
emit("")


def report(days, label):
    emit("=" * 70)
    emit(label)
    emit("=" * 70)
    per_hh = defaultdict(list)
    for (hid, _d), v in days.items():
        per_hh[hid].append(v)
    emit("  %-26s %10s %8s %10s" % ("household type", "kWh/day", "n", "adopted"))
    res = {}
    for ht in TYPES:
        vals = [sum(v) / len(v) for hid, v in per_hh.items()
                if hh_type.get(hid) == ht and v]
        if not vals:
            emit("  %-26s %10s" % (ht, "no data"))
            continue
        m = sum(vals) / len(vals)
        res[ht] = m
        flag = "" if abs(m - ADOPTED[ht]) < 0.05 else "  <-- DIFFERS"
        emit("  %-26s %10.2f %8d %10.2f%s"
             % (ht, m, len(vals), ADOPTED[ht], flag))
    emit("")
    if len(res) >= 2:
        gap = res.get("Water Heaters but no AC", 0) - res.get("Basic", 0)
        emit("  GEYSER GAP  'water heaters' - 'basic' = %.2f kWh/day" % gap)
        emit("  model adopted 1.44 (PA-B1c revised)")
        emit("")
        emit("  GEYSER-STRIPPED BASES (subtract the gap from each tier):")
        for ht in TYPES:
            if ht in res:
                sub = res[ht] - (gap if ht != "Basic" else 0.0)
                emit("    %-26s %6.2f" % (ht, sub))
        emit("  A geyser-stripped base should be tier-INVARIANT: a fridge and")
        emit("  a light bulb are the same in any home. Check that above.")
    return res


res = report(complete, "ALL REGIONS, winter (Nov-Feb), complete days")
emit("=" * 70)
emit("WHAT THIS IS FOR")
emit("=" * 70)
emit("The proposed re-base anchors (low 4.73 / mid 6.15 / high 8.30) are")
emit("derived as: geyser-stripped base x 1.34 (CEA) x tier uplift")
emit("(low 1.0 / mid 1.3 / high 1.8). Reproduce them from the bases above")
emit("before adopting them - if the bases here do not match 3.53/3.53/3.44,")
emit("the re-base targets need recomputing, not just copying.")
_log.close()
print("\nwrote %s" % OUT)
