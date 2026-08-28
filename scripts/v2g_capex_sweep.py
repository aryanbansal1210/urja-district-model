"""AUD-24 - V2G charger CAPEX sensitivity (the stress test).

WHY THIS EXISTS. `technologies.v2g_charger.capex_inr_per_unit: 42000` is the
only major capex in economics.yaml carrying NO source - just an inline comment
"2030 forecast (drop from 50k 2024-25)". Register row AUD-24 flags it as
"cheap vs $1.5-4k real bidirectional chargers - inflates a DEPLOYED tech", and
says the V2G one "matters most: re-source + sensitivity on V2G capex".

THE PROBLEM IN ONE LINE: at 7.0 kW nominal, Rs 42,000 is ~$500 - LESS than an
ordinary ONE-WAY 7.4 kW AC wallbox costs in India today.

EVIDENCE COLLECTED (all Tier 4 - no Tier 1/2 source publishes an
Indian bidirectional charger price, because the market barely exists; ISGF ran
a FOUR-vehicle pilot):
  - Indian branded 7.4 kW UNIdirectional AC wallbox: Rs 25,000-50,000
    (ev.care, https://ev.care/blog/best-home-ev-chargers-brands-india)
  - Same class, alternative trade estimate at 7.2 kW: Rs 40,000-75,000
    (meraev, https://www.meraev.com/blog/ev-home-charger-guide-2026-types-prices-and-which-one-your-car-actually-needs)
  - Bidirectional premium in India: "2-3x as much as a normal charger"
    (Bolt.Earth, https://bolt.earth/blog/what-is-bidirectional-charging-is-it-the-next-big-thing-for-ev-owners-in-india)
  - International hardware anchor: Wallbox Quasar 2 at $6,440 hardware-only
    (11.5 kW, not like-for-like on rating or market)
  - Feasibility (not price): ISGF 2024-25 pilot retrofitted four Tata Nexon EVs
    with AC bidirectional chargers - already cited in the literature review as
    South Asia's first V2G pilot (Tier 2)

WHY A SWEEP AND NOT A NEW NUMBER. Every price available is Tier 4. Replacing
one uncited point estimate with another uncited point estimate is not progress.
What IS defensible is bounding the finding: says "battery entry is deferred
because managed EV charging is the cheaper flexibility". V2G is the thing that
beats the battery, so a too-cheap V2G is a NON-CONSERVATIVE assumption FOR THAT
FINDING. This sweep answers the only question that matters: does survive a
realistic Indian bidirectional price, and if not, where is the threshold?

Production files are UNTOUCHED (clone-econ, same pattern as
discount_rate_sweep.py). No re-pin is required by running this.

Run: python scripts/v2g_capex_sweep.py    (~4 multi-period solves, ~30 min)
Writes: outputs/data/energy/v2g_capex_sweep.md
"""
from __future__ import annotations
import os, sys, time
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
from energy.costs import load_economics                       # noqa: E402
from energy.network import load_optimised_network             # noqa: E402
from energy.dispatch import solve_dispatch                    # noqa: E402

# (Rs/unit, label, basis)
CASES = [
    (42_000,  "as-is",   "current model value (UNCITED - the thing under test)"),
    (75_000,  "low",     "2x the low end of the Indian unidirectional band (Rs 37.5k)"),
    (110_000, "central", "mid of the Bolt.Earth 2-3x premium on a Rs 45k unidirectional base"),
    (150_000, "high",    "3x the upper unidirectional band (Rs 50k)"),
]

NET = load_optimised_network()


def _per_period(r, key):
    pb = getattr(r, "period_breakdown", {}) or {}
    return {int(y): float((d.get("installed_capacities", {}) or {}).get(key, 0) or 0)
            for y, d in pb.items()}


rows = []
for capex, label, basis in CASES:
    t0 = time.time()
    e = deepcopy(load_economics(force_reload=True))
    # `technologies` is a plain dataclass field on Economics (costs.py:469,690),
    # NOT a `*_raw` dict like multi_period - and every v2g accessor reads
    # self.technologies["v2g_charger"] directly (costs.py:2360, 4394, 4399,
    # 4413, 4418), so overriding here reaches all of them. deepcopy above makes
    # this instance independent; production files are untouched.
    if "v2g_charger" not in (e.technologies or {}):
        raise SystemExit("technologies.v2g_charger not found - check the key "
                         "name before trusting this sweep")
    e.technologies["v2g_charger"]["capex_inr_per_unit"] = float(capex)
    # prove the override reached the accessor rather than assuming it
    got = float(e.technologies["v2g_charger"]["capex_inr_per_unit"])
    assert abs(got - capex) < 1e-6, (got, capex)

    r = solve_dispatch(NET, e, "full_stack", alpha=0.0)
    batt = _per_period(r, "battery_kwh")
    v2gu = _per_period(r, "v2g_units")
    rows.append(dict(capex=capex, label=label, basis=basis,
                     cost=r.annual_cost_inr, life=r.lifetime_cost_inr,
                     co2=r.annual_emissions_kgco2,
                     b30=batt.get(2030, 0), b42=batt.get(2042, 0), b55=batt.get(2055, 0),
                     v30=v2gu.get(2030, 0), v42=v2gu.get(2042, 0), v55=v2gu.get(2055, 0),
                     secs=time.time() - t0))
    print(f"  Rs {capex:,}: cost {r.annual_cost_inr/1e6:,.1f} M | "
          f"batt 2030/42/55 = {batt.get(2030,0)/1e3:,.0f}/{batt.get(2042,0)/1e3:,.0f}/"
          f"{batt.get(2055,0)/1e3:,.0f} MWh | v2g {v2gu.get(2030,0):,.0f}/"
          f"{v2gu.get(2042,0):,.0f}/{v2gu.get(2055,0):,.0f} units "
          f"({time.time()-t0:.0f}s)", flush=True)

base = rows[0]
out = ["# AUD-24 - V2G charger capex sensitivity (F28 stress test)", "",
       "Generated by `scripts/v2g_capex_sweep.py`. Production config untouched.",
       "", "The model prices a 7.0 kW BIDIRECTIONAL unit at Rs 42,000 (~$500), which is",
       "less than an ordinary ONE-WAY 7.4 kW AC wallbox costs in India today",
       "(Rs 25,000-50,000, Tier 4). Indian bidirectional premium is quoted at 2-3x.",
       "", "| case | Rs/unit | annual cost (M) | vs as-is | lifetime (B) | CO2 (kt) |"
       " battery 2030/2042/2055 (MWh) | V2G units 2030/2042/2055 |",
       "|---|---:|---:|---:|---:|---:|---|---|"]
for r in rows:
    out.append(
        f"| {r['label']} | {r['capex']:,} | {r['cost']/1e6:,.1f} | "
        f"{(r['cost']-base['cost'])/1e6:+,.1f} | {r['life']/1e9:.2f} | "
        f"{r['co2']/1e6:,.1f} | "
        f"{r['b30']/1e3:,.0f} / {r['b42']/1e3:,.0f} / {r['b55']/1e3:,.0f} | "
        f"{r['v30']:,.0f} / {r['v42']:,.0f} / {r['v55']:,.0f} |")

out += ["", "## Basis for each case", ""]
for r in rows:
    out.append(f"- **{r['label']} (Rs {r['capex']:,})** - {r['basis']}")

out += ["", "## The question this answers", "",
        "F28 states that battery entry is deferred because managed EV charging is the",
        "cheaper flexibility. V2G is what beats the battery, so an under-priced V2G is a",
        "NON-CONSERVATIVE assumption *for that finding*. Read the battery columns:",
        "if the entry period and size hold across the range, F28 is robust to the",
        "uncited price and the thesis can say so. If entry moves earlier or the size",
        "jumps, report the threshold rather than the point estimate.", "",
        "## Sources (all Tier 4 unless noted)", "",
        "- Indian 7.4 kW unidirectional wallbox Rs 25,000-50,000 - ev.care",
        "  <https://ev.care/blog/best-home-ev-chargers-brands-india>",
        "- Indian 7.2 kW unit Rs 40,000-75,000 - meraev",
        "  <https://www.meraev.com/blog/ev-home-charger-guide-2026-types-prices-and-which-one-your-car-actually-needs>",
        "- Bidirectional premium 2-3x - Bolt.Earth",
        "  <https://bolt.earth/blog/what-is-bidirectional-charging-is-it-the-next-big-thing-for-ev-owners-in-india>",
        "- ISGF 2024-25 four-vehicle Tata Nexon V2G pilot (feasibility, no unit price;",
        "  Tier 2, already cited in the literature review)", ""]

dest = os.path.join("outputs", "data", "energy", "v2g_capex_sweep.md")
os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + "\n")
print("written:", dest)
