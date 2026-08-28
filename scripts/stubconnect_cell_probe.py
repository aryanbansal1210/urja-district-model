""" PROBE: what did the one stub-connect cell cost?

The frozen geojson was edited at 14:07 on - AFTER pin discovery
(02:53) and AFTER the chain's step-1 regen (09:00), but DURING the step-4
suite. Cell (9,17) went open_space -> ROAD/collector (its
`solar_expansion_2042` tag re-homed to (24,6)), so the farm-side stub
reconnects to the row-8 road: 628 road cells, ONE component.

Two of the five suite failures already measured the effect on solves that
share no structure with each other, and they agree to SEVEN decimal places:

    single-period 2030 full_stack   +29,053.6720753
    multi-period  B21 five-gate     +29,053.6722980

That is the signature: a BUILD-INDEPENDENT CONSTANT passing through
to the paisa, i.e. no build decision moved. Its two components are measured
directly off the network builder, no LP required:

    internal network  93,494,881.1442 -> 93,531,344.6641  = +36,463.5199/yr
                      (cable route 65.700 -> 65.900 km)
    annual demand     520,351,397.44  -> 520,350,276.34   = -1,121.10 kWh/yr

    +36,463.5199 - 1,121.10 x 6.6094 = +29,053.672  (avoided import Rs/kWh)

This script solves the TWO cases the suite never re-measured - the
multi-period production headline and BAU - on the CURRENT 628-road town, and
checks them against the PREDICTION stated above before the solve runs. The
prediction is printed first on purpose: an advance prediction the run then
has to match is the standard this project holds its infrastructure results
to..4, FINDINGS.

BAU is predicted separately: it has no PV, so its avoided import is priced at
its own marginal, which need not equal the town's Rs 6.6094/kWh. The town
prediction is the falsifiable one.

Run from district_v3 (~10 min, 2 solves):
    PYTHONPATH=. python -u scripts/stubconnect_cell_probe.py
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics                    # noqa: E402
from energy.dispatch import solve_dispatch_pyomo           # noqa: E402
from energy.network import load_optimised_network          # noqa: E402

OUT = os.path.join(ROOT, "outputs", "verification",
                   "stubconnect_cell_probe_20260813.txt")

# Pins as discovered 02:53 on the PRE-edit 627-road town.
PRE = {
    "full_stack": (1_900_423_187.58, 116_118_904.66, 61_621_812_532.34),
    # BAU here is the POST-PPA-BAU-1 value (the discovery printed
    # 3,571,644,129.61 before that fix; -1,092,787.03 exactly).
    "bau": (3_570_551_342.58, 304_908_740.88, 107_924_060_597.66),
}
DELTA_TOWN = 29_053.672          # measured twice, 7 d.p. agreement
CABLE_DELTA = 36_463.5199        # measured off the network builder
DEMAND_DELTA_KWH = -1_121.10     # measured off the network builder


def main() -> None:
    t0 = time.time()
    log = open(OUT, "w", encoding="utf-8")

    def emit(s: str) -> None:
        print(s, flush=True)
        log.write(s + "\n")
        log.flush()

    emit(f"REPIN-4 stub-connect cell probe started {time.strftime('%F %H:%M')}")
    emit("")
    emit("== PREDICTION (stated BEFORE the solve) ==")
    emit(f"  cable cost delta      = {CABLE_DELTA:+,.4f} INR/yr  (65.700 -> 65.900 km)")
    emit(f"  demand delta          = {DEMAND_DELTA_KWH:+,.2f} kWh/yr")
    emit(f"  measured town constant= {DELTA_TOWN:+,.4f} INR/yr "
         f"(single-period AND B21 anchor, 7 d.p.)")
    emit(f"  => multi full_stack   = {PRE['full_stack'][0]:,.2f} "
         f"+ {DELTA_TOWN:,.4f} = {PRE['full_stack'][0] + DELTA_TOWN:,.2f}")
    emit(f"  => multi full_stack CO2 UNCHANGED at {PRE['full_stack'][1]:,.2f} "
         f"(cable cost has no operating emissions; the -1,121 kWh of avoided "
         f"import is the only CO2 term and is ~7 kgCO2/yr)")
    emit(f"  => BAU: between {PRE['bau'][0] + CABLE_DELTA - 1_121.10 * 9.0:,.2f} "
         f"and {PRE['bau'][0] + CABLE_DELTA:,.2f} "
         f"(cable constant less BAU's own avoided import, marginal unknown)")
    emit("")

    net = load_optimised_network()
    ind = None
    emit(f"[{time.strftime('%H:%M')}] network built on the CURRENT geojson")

    emit(f"[{time.strftime('%H:%M')}] 1/2 multi-period full_stack a=0 ...")
    e1 = load_economics(force_reload=True)
    r1 = solve_dispatch_pyomo(net, e1, "full_stack", alpha=0.0)
    ind = r1.__dict__.get("internal_network_breakdown") or {}

    emit(f"[{time.strftime('%H:%M')}] 2/2 multi BAU ...")
    e2 = load_economics(force_reload=True)
    r2 = solve_dispatch_pyomo(net, e2, "bau", alpha=0.0)

    emit("")
    emit("== RESULT on the CURRENT 628-road town ==")
    emit(f"  internal network       = Rs {ind.get('annualised_total_inr', 0):,.4f}/yr "
         f"({ind.get('cable_route_km', 0):,.3f} km)")
    for label, r, key in (("full_stack", r1, "full_stack"), ("bau", r2, "bau")):
        pc, pe, pl = PRE[key]
        emit(f"  -- {label}")
        emit(f"     annual_cost_inr   = {r.annual_cost_inr:,.4f}  "
             f"(was {pc:,.2f}, delta {r.annual_cost_inr - pc:+,.4f})")
        emit(f"     annual_emissions  = {r.annual_emissions_kgco2:,.4f}  "
             f"(was {pe:,.2f}, delta {r.annual_emissions_kgco2 - pe:+,.4f})")
        emit(f"     lifetime_cost_inr = {r.lifetime_cost_inr:,.2f}  "
             f"(was {pl:,.2f}, delta {r.lifetime_cost_inr - pl:+,.2f})")
        emit(f"     annual_demand_kwh = {r.annual_demand_kwh:,.2f}")
        conn = r.__dict__.get("grid_connection_mw")
        if conn is not None:
            emit(f"     sized connection  = {conn:,.1f} MW")
        caps = r.capacities or {}
        emit(f"     farm/rooftop/batt = {caps.get('solar_farm_kwp', 0):,.1f} / "
             f"{caps.get('rooftop_pv_kwp', 0):,.1f} / {caps.get('battery_kwh', 0):,.1f}")

    emit("")
    emit("== VERDICT ==")
    got = r1.annual_cost_inr - PRE["full_stack"][0]
    miss = got - DELTA_TOWN
    emit(f"  town delta predicted {DELTA_TOWN:+,.4f}, measured {got:+,.4f}, "
         f"miss {miss:+,.4f} INR/yr")
    emit("  PREDICTION HELD - build-independent constant confirmed on a THIRD "
         "solve." if abs(miss) < 1.0 else
         "  PREDICTION MISSED - the cell moved a build decision; do NOT treat "
         "it as a constant, re-run full pin discovery.")
    town, bau = r1.annual_cost_inr, r2.annual_cost_inr
    emit(f"  vs-BAU cost = {(1 - town / bau) * 100:.4f}%  "
         f"(was 46.7750% on the pre-edit town)")
    emit(f"  vs-BAU CO2  = "
         f"{(1 - r1.annual_emissions_kgco2 / r2.annual_emissions_kgco2) * 100:.4f}%  "
         f"(was 61.9170%)")
    emit("")
    emit(f"done in {(time.time() - t0) / 60:.1f} min")
    log.close()


if __name__ == "__main__":
    main()
