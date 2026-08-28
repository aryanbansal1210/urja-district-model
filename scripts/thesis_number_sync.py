"""THESIS NUMBER SYNC - find every stale figure in the drafts after a re-pin.

the author "run it all through and update the word doc numbers after."

A re-pin moves dozens of numbers that are hand-written into eight markdown
drafts. Hunting them by memory is how a thesis ends up quoting two different
headlines in two chapters (it has happened here before - CLAUDE.md's own pins
block went two re-pins stale and caused a wrong in-session comparison).

So this does not guess: it holds the OLD value of every quantity the DENS
batch moves, greps the drafts for each one, and prints file:line for every
occurrence beside the NEW value read live from dispatch_results.json. What it
prints is a checklist; what it cannot see (prose that must be REWRITTEN
rather than renumbered) is listed at the bottom by hand.

    PYTHONPATH=. python scripts/thesis_number_sync.py
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFTS = os.path.join(os.path.dirname(os.path.dirname(ROOT)),
                      "WRITEUP", "drafts")
RESULTS = os.path.join(ROOT, "outputs", "data", "energy",
                       "dispatch_results.json")

with io.open(RESULTS, encoding="utf-8") as fh:
    doc = json.load(fh)
fs = [s for s in doc["scenarios"] if s.get("name") == "full_stack"][0]
bau = [s for s in doc["scenarios"] if s.get("name") == "bau"][0]
pb = fs.get("period_breakdown", {})
P = sorted(pb, key=lambda k: int(k))


def ic(p, k):
    return float(pb[p]["installed_capacities"].get(k, 0.0))


def pv(p, k):
    return float(pb[p].get(k, 0.0))


caps = fs["capacities"]
vs_cost = 100 * (1 - fs["annual_cost_inr"] / bau["annual_cost_inr"])
vs_co2 = 100 * (1 - fs["annual_emissions_kgco2"] / bau["annual_emissions_kgco2"])

# label, OLD string(s) as written in the drafts, NEW value
CHECKS = [
    ("annual cost", ["1,841,569,555.79"], "{:,.2f}".format(fs["annual_cost_inr"])),
    ("annual CO2", ["116,638,892.44"], "{:,.2f}".format(fs["annual_emissions_kgco2"])),
    ("lifetime town", ["63,247,015,703.14"], "{:,.2f}".format(fs["lifetime_cost_inr"])),
    ("vs-BAU cost %", ["49.46", "49.4567"], "%.2f" % vs_cost),
    ("vs-BAU CO2 %", ["62.51", "62.5096"], "%.2f" % vs_co2),
    ("rooftop kWp", ["82,725.3"], "{:,.1f}".format(caps.get("rooftop_pv_kwp", 0))),
    ("farm 2030 kWp", ["214,914.0"], "{:,.1f}".format(ic(P[0], "solar_farm_kwp"))),
    ("farm 2042 kWp", ["236,405.4"], "{:,.1f}".format(ic(P[1], "solar_farm_kwp"))),
    ("farm 2055 kWp", ["247,151.1"], "{:,.1f}".format(ic(P[2], "solar_farm_kwp"))),
    ("carport kWp", ["18,975.0"], "{:,.1f}".format(caps.get("carport_kwp", 0))),
    ("canal-top kWp", ["18,664.5"], "{:,.1f}".format(caps.get("floating_pv_kwp", 0))),
    ("battery 2055 kWh", ["382,007.9"], "{:,.1f}".format(ic(P[2], "battery_kwh"))),
    ("battery 2042 kWh", ["130,858.7"], "{:,.1f}".format(ic(P[1], "battery_kwh"))),
    ("solar thermal m2", ["63,226"], "{:,.0f}".format(caps.get("solar_thermal_m2", 0))),
    ("rooftop ceiling", ["129,088.9"], "(recompute: roof cap)"),
    ("import 2030 GWh", ["187.85"], "%.2f" % (pv(P[0], "grid_import_kwh") / 1e6)),
    ("import 2055 GWh", ["203.67"], "%.2f" % (pv(P[2], "grid_import_kwh") / 1e6)),
    ("export 2030 GWh", ["149.59"], "%.2f" % (pv(P[0], "grid_export_kwh") / 1e6)),
    ("export 2055 GWh", ["6.03"], "%.2f" % (pv(P[2], "grid_export_kwh") / 1e6)),
    ("demand 2055 GWh", ["750.57"], "%.2f" % (pv(P[2], "annual_demand_kwh") / 1e6)),
    ("connection MW", ["145.1"], "(recompute from grid_connection)"),
]

files = sorted(f for f in os.listdir(DRAFTS) if f.endswith(".md"))
text = {}
for f in files:
    with io.open(os.path.join(DRAFTS, f), encoding="utf-8") as fh:
        text[f] = fh.read().splitlines()

print("=" * 100)
print("THESIS NUMBER SYNC - stale figures in %s" % DRAFTS)
print("=" * 100)
total = 0
for label, olds, new in CHECKS:
    hits = []
    for f in files:
        for i, line in enumerate(text[f], 1):
            for o in olds:
                if o in line:
                    hits.append((f, i, line.strip()[:88]))
                    break
    print("\n%-20s OLD %-22s -> NEW %s" % (label, "/".join(olds), new))
    if not hits:
        print("      (no occurrences)")
    for f, i, s in hits:
        total += 1
        print("      %-22s :%-5d %s" % (f, i, s))

print("\n" + "=" * 100)
print("%d occurrences to update" % total)
print("""
PROSE THAT MUST BE REWRITTEN, NOT RENUMBERED (this script cannot detect it):
  05_results.md ~199-206  "Ground-mounted generation behaves in the opposite
       way, rising ... as the reserved land is taken up in stages" and
       "exhausts its roofs immediately and its land gradually" - BOTH FALSE
       now. Farm and rooftop are each built once, in 2030. What grows across
       periods is carport (its parking land is genuinely released per period),
       battery and V2G. Figure 5.2's "one block flat, the block beneath keeps
       growing" description inverts with it.
  05_results.md ~517-522  battery narrative "as capital cost falls along the
       learning curve" - still true, but the farm half of that argument is
       gone; check it does not lean on farm deferral.
  06_discussion.md ~97    comment asserting 214,914 kWp built in 2030.
  Farm ledger paragraph (NEW, from F70): the merchant-plant -> town-power-
       station inversion, exports 230.4 -> 9.4 GWh, DC-PPA 95.8 -> 80.9 GWh,
       pro-rata income Rs 124.1 -> 42.6 crore. Not currently in any chapter.
  Methodology: the land-density derivation (GCR 0.34 -> 0.382, 4.0 ac/MWac)
       and the area-budget constraint form both belong in Ch3.
""")
