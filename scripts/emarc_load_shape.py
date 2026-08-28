"""Build a MEASURED Indian residential load shape from Prayas eMARC.

Source: Prayas (Energy Group), eMARC processed data, Harvard Dataverse
doi:10.7910/DVN/YJ5SP1. 15-minute block loads from IoT smart meters in 143
mainline deployments across five Indian locations, Jan 2018 - Jun 2020.
Tier 2 (reputable research organisation, MEASURED not modelled).

Two audit questions this answers, both of which have been running on expert
judgement until now:

  the 504 hand-set numbers in `base_demand_profile` drive 58% of
         district demand and have no source. Do their SHAPES match measured
         Indian households?

  one cooling daypart curve serves a bedroom AC, an office AC and a
         cold store alike. Households classified "With Air Conditioners"
         minus households classified "Basic", in the same season and region,
         isolates the AC-attributable load shape by difference.

WHY THIS DATASET AND NOT THE HYDERABAD PAPER: Kanpur rural and Gonda are
Uttar Pradesh - north India, the same Indo-Gangetic plain as Zirakpur, with
real winters. Hyderabad is Deccan and has none. Both are used; the UP subset
is the closer analogue and is reported separately.

Writes outputs/verification/emarc_load_shape.txt
"""
from __future__ import annotations

import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

D = r"C:\Users\aryan\Downloads\dataverse_files"
OUT = os.path.join("outputs", "verification", "emarc_load_shape.txt")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
_log = open(OUT, "w", encoding="utf-8")


def emit(s=""):
    print(s, flush=True)
    _log.write(s + "\n")
    _log.flush()


# our model's 12 two-hour dayparts
DAYPARTS = ["00_02", "02_04", "04_06", "06_08", "08_10", "10_12",
            "12_14", "14_16", "16_18", "18_20", "20_22", "22_24"]

emit("eMARC measured residential load shape")
emit("Prayas (Energy Group), Harvard Dataverse doi:10.7910/DVN/YJ5SP1")
emit("=" * 74)

meta = pd.read_excel(os.path.join(D, "Household-Deployment basic info.xlsx"))
meta.columns = [c.strip() for c in meta.columns]
main = meta[meta["Deployment type"].str.lower() == "mainline"].copy()
emit("mainline deployments: %d" % len(main))
emit("by household type:")
for k, v in main["Household type"].value_counts().items():
    emit("    %-26s %d" % (k, v))
emit("by region:")
for k, v in main["Region"].value_counts().items():
    emit("    %-26s %d" % (k, v))

NORTH = {"Kanpur rural", "Gonda"}          # Uttar Pradesh, Indo-Gangetic
main["north"] = main["Region"].isin(NORTH)
emit("north India (UP) mainline deployments: %d" % int(main["north"].sum()))
emit("")

emit("reading 12.7M load blocks (this takes a minute) ...")
df = pd.read_csv(
    os.path.join(D, "eMARC load blocks.csv"),
    usecols=["deployment_id", "block", "date", "Load (kW)"],
    dtype={"deployment_id": "category", "block": "int16",
           "Load (kW)": "float32"},
)
df.columns = ["deployment_id", "block", "date", "kw"]
emit("  rows %s   blocks %d..%d" % (len(df), df["block"].min(), df["block"].max()))

# join metadata, keep mainline only
df = df.merge(main[["deployment_id", "Household type", "Region", "north"]],
              on="deployment_id", how="inner")
emit("  mainline rows %s" % len(df))

# date -> month. The file is M/D/YYYY (verified: max first field is 12,
# max second field is 31, and 13+ appears in the second field only).
dt = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")
bad = int(dt.isna().sum())
if bad:
    emit("  WARNING %d unparsed dates, dropped" % bad)
df["month"] = dt.dt.month
df = df[df["month"].notna()]
df["month"] = df["month"].astype("int8")

# 96 blocks of 15 min -> 12 dayparts of 2 h. Establish the base first.
b0 = int(df["block"].min())
nb = int(df["block"].max()) - b0 + 1
emit("  block base %d, count %d  (expect 96 blocks of 15 min)" % (b0, nb))
df["dp"] = ((df["block"] - b0) * 24 // nb // 2).clip(0, 11)

SUMMER = [4, 5, 6, 7, 8, 9]      # Apr-Sep, matches the PSERC H1 definition
df["season"] = df["month"].isin(SUMMER).map({True: "summer", False: "winter"})


def profile(sub):
    """mean kW per daypart, and the same normalised to its own mean."""
    g = sub.groupby("dp")["kw"].mean()
    g = g.reindex(range(12))
    return g, g / g.mean()


def show(title, sub):
    if len(sub) == 0:
        emit("  %s: no data" % title)
        return None
    g, n = profile(sub)
    emit("")
    emit(title + "   (n=%d deployments, %s rows)"
         % (sub["deployment_id"].nunique(), f"{len(sub):,}"))
    emit("    %-8s%10s%10s" % ("daypart", "mean kW", "norm"))
    for i, dpn in enumerate(DAYPARTS):
        emit("    %-8s%10.4f%10.3f" % (dpn, g.iloc[i], n.iloc[i]))
    night = g.iloc[[11, 0, 1, 2]].sum()          # 22-06
    aft = g.iloc[[6, 7, 8]].sum()                # 12-18
    emit("    22:00-06:00 share %.1f%%   12:00-18:00 share %.1f%%"
         % (night / g.sum() * 100, aft / g.sum() * 100))
    return g


emit("")
emit("=" * 74)
emit("1. WHOLE-HOUSE LOAD SHAPE BY HOUSEHOLD TYPE  (PA-A0)")
emit("=" * 74)
res = {}
for hh in ["Basic", "Water Heaters but no AC", "With Air Conditioners"]:
    for season in ["summer", "winter"]:
        key = (hh, season)
        res[key] = show("%s / %s" % (hh, season),
                        df[(df["Household type"] == hh)
                           & (df["season"] == season)])

emit("")
emit("=" * 74)
emit("2. THE AC-ATTRIBUTABLE SHAPE BY DIFFERENCE  (PA-A7)")
emit("=" * 74)
emit("AC homes minus Basic homes, same season. Not a perfect controlled")
emit("comparison - AC homes are richer and differ in other appliances too -")
emit("but the DIFFERENCE is dominated by cooling and its TIMING is the")
emit("question here, not its level.")
for season in ["summer", "winter"]:
    a = res.get(("With Air Conditioners", season))
    b = res.get(("Basic", season))
    if a is None or b is None:
        continue
    d = (a - b).clip(lower=0)
    if d.sum() <= 0:
        continue
    emit("")
    emit("  %s: AC-attributable load" % season)
    emit("    %-8s%12s%10s" % ("daypart", "delta kW", "share"))
    for i, dpn in enumerate(DAYPARTS):
        emit("    %-8s%12.4f%9.1f%%" % (dpn, d.iloc[i], d.iloc[i] / d.sum() * 100))
    night = d.iloc[[11, 0, 1, 2]].sum()
    aft = d.iloc[[6, 7, 8]].sum()
    emit("    22:00-06:00 %.1f%%    12:00-18:00 %.1f%%"
         % (night / d.sum() * 100, aft / d.sum() * 100))
    if season == "summer":
        emit("")
        emit("    OUR MODEL residential cooling: 22:00-06:00 25.0%%, "
             "12:00-18:00 33.7%%")
        emit("    Hyderabad paper (Ramapragada 2022): 84%% night / 16%% day")

emit("")
emit("=" * 74)
emit("2b. DOUBLE DIFFERENCE - controlling for wealth using winter  (PA-A7)")
emit("=" * 74)
emit("The single difference above is CONTAMINATED. AC-owning households are")
emit("richer in every season: more lighting, bigger fridges, more of")
emit("everything. The giveaway is the WINTER difference, which peaks at")
emit("08:00-10:00 - that is not air conditioning, that is water heating and")
emit("breakfast in a wealthier home.")
emit("")
emit("Winter is therefore a natural control: the ACs are off, so the winter")
emit("difference IS the wealth effect. Subtracting it from the summer")
emit("difference leaves the seasonal, cooling-driven part.")
emit("")
emit("    (AC homes - Basic homes) in summer")
emit("  - (AC homes - Basic homes) in winter")
emit("  = the load that appears in AC homes ONLY when it is hot")
a_s = res.get(("With Air Conditioners", "summer"))
b_s = res.get(("Basic", "summer"))
a_w = res.get(("With Air Conditioners", "winter"))
b_w = res.get(("Basic", "winter"))
if all(x is not None for x in (a_s, b_s, a_w, b_w)):
    dd = ((a_s - b_s) - (a_w - b_w)).clip(lower=0)
    tot = dd.sum()
    emit("")
    emit("    %-8s%12s%10s" % ("daypart", "delta kW", "share"))
    for i, dpn in enumerate(DAYPARTS):
        emit("    %-8s%12.4f%9.1f%%" % (dpn, dd.iloc[i], dd.iloc[i] / tot * 100))
    night = dd.iloc[[11, 0, 1, 2]].sum()
    aft = dd.iloc[[6, 7, 8]].sum()
    emit("")
    emit("    22:00-06:00  %.1f%%" % (night / tot * 100))
    emit("    12:00-18:00  %.1f%%" % (aft / tot * 100))
    emit("")
    emit("    CONVERGENCE - four independent estimates of the night share of")
    emit("    Indian residential cooling:")
    emit("      eMARC double difference (this)      %.0f%%" % (night / tot * 100))
    emit("      Ramapragada 2022, Hyderabad metered  84%")
    emit("      Hisham 2021, Malaysia, 20 dwellings  79%")
    emit("      OUR MODEL                            25%   <-- the outlier")

emit("")
emit("=" * 74)
emit("3. NORTH INDIA ONLY (Kanpur rural + Gonda, UP)")
emit("=" * 74)
emit("The closer analogue to Punjab - same Indo-Gangetic plain, real winters.")
for season in ["summer", "winter"]:
    show("UP / all household types / %s" % season,
         df[(df["north"]) & (df["season"] == season)])

_log.close()
print("\nwrote %s" % OUT)
