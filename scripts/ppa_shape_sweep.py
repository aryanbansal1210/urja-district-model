"""Switching-point #3 - what PPA SHAPE the district can actually commit to.

THE LAST OPEN ITEM of the sensitivity batch. The batch listed it as
"PPA shape 0.90/0.85/0.80", i.e. deliver 90/85/80 % of a fixed 25 MW contract.
That framing cannot be run and should not be: there is no partial-coverage knob
in the model, and inventing one would mean touching production dispatch code
that is currently under a green byte-exact pin.

The question behind it is answerable with a lever that already exists, and the
better-posed version is worth more. `bound_by_surplus_not_baseload` (wired
, register AUD-CFG-1) switches the contract between:

    true  (production) - offtake is an UPPER BOUND. The town sells whatever
                         surplus it has, up to the intake capacity. This is
                         what the headline PPA value is earned under.
    false              - the contract is FIRM. The Var must EQUAL
                         offtake_kw_constant x hours in EVERY slice, so the
                         town serves the load round the clock or the solve is
                         infeasible.

So rather than asking "can we hit 90 % of 25 MW", this sweeps the FIRM contract
SIZE downward and finds the largest round-the-clock commitment the district can
actually honour, and what that commitment costs against selling surplus.

WHY THAT IS THE MORE USEFUL RESULT. The production solve already reports the
shape it achieves: temporal match 1.0000 (every kWh sold is matched by
simultaneous own generation - no import-and-resell), coverage 0.4243 of the
219 GWh contract, and supply confined to hours 06-17. A data centre is a 24/7
load. The interesting number is therefore not a coverage percentage the town
was never able to offer, but the size of firm block it CAN offer, and the
premium a 24/7 counterparty would have to pay for it.

Clone-econ throughout. Production config, pins and the layout are untouched.

    python scripts/ppa_shape_sweep.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from energy.costs import load_economics            # noqa: E402
from energy.network import load_optimised_network  # noqa: E402
from energy.dispatch import solve_dispatch         # noqa: E402

GREEN = "data_centre_offsite_re_concession"
OUT = os.path.join(ROOT, "outputs", "data", "energy", "ppa_shape_sweep.json")
MD = os.path.join(ROOT, "outputs", "data", "energy", "ppa_shape_sweep.md")

# Firm-block sizes to try, kW. 25,000 is the production contract size; the
# ladder descends until one solves. Infeasible cases fail fast, so a long tail
# of small sizes is cheap insurance rather than wasted time.
FIRM_KW = [25000, 20000, 15000, 10000, 7500, 5000, 2500, 1000]


def _clone():
    return deepcopy(load_economics(force_reload=True))


def _solve(econ, label):
    t0 = time.time()
    try:
        r = solve_dispatch(load_optimised_network(), econ, "full_stack", alpha=0.0)
        dt = time.time() - t0
        print(f"  {label:<28} solved in {dt/60:5.1f} min  "
              f"cost {float(r.annual_cost_inr):>18,.2f}", flush=True)
        return r, None
    except Exception as exc:                       # infeasible is a RESULT here
        dt = time.time() - t0
        msg = str(exc).splitlines()[0][:120]
        print(f"  {label:<28} FAILED  in {dt/60:5.1f} min  {msg}", flush=True)
        return None, msg


def g(r, name, default=None):
    """Read a field off a DispatchResult.

    solve_dispatch returns an OBJECT, not a dict; the first version of this
    script subscripted it and every solve died after six minutes of work with
    "'DispatchResult' object is not subscriptable". Reading through one helper
    means that mistake can only be made once.
    """
    return default if r is None else getattr(r, name, default)


def main() -> int:
    print("PPA SHAPE SWEEP - largest firm round-the-clock block", flush=True)
    print(f"firm sizes to try (kW): {FIRM_KW}\n", flush=True)

    # (a) the production reference: surplus-following, PPA ON.
    e = _clone()
    e.set_ppa_enabled(True)
    ref, _ = _solve(e, "REFERENCE surplus-following")
    if ref is None:
        print("reference solve failed - aborting")
        return 1

    # (b) no PPA at all, for the value of the contract on this basis.
    e = _clone()
    e.set_ppa_enabled(False)
    noppa, _ = _solve(e, "no PPA")

    rows = []
    for kw in FIRM_KW:
        e = _clone()
        e.set_ppa_enabled(True)
        raw = e.__dict__["ppa_raw"]
        raw["enabled"] = True
        cp = raw["counterparties"][GREEN]
        cp["enabled"] = True
        cp["bound_by_surplus_not_baseload"] = False      # FIRM
        cp["offtake_kw_constant"] = float(kw)
        r, err = _solve(e, f"FIRM {kw:,} kW")
        rows.append({
            "firm_kw": kw,
            "feasible": r is not None,
            "error": err,
            "annual_cost_inr": g(r, "annual_cost_inr"),
            "annual_emissions_kgco2": g(r, "annual_emissions_kgco2"),
            "dc_ppa_offtake_kwh": g(r, "dc_ppa_offtake_kwh"),
            "dc_ppa_revenue_inr": g(r, "dc_ppa_revenue_inr"),
            "dc_ppa_coverage_fraction": g(r, "dc_ppa_coverage_fraction"),
            "capacities": g(r, "capacities"),
        })

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "basis": "2026-08-19 solar-thermal pins (post-chain)",
        "reference_surplus_following": {
            "annual_cost_inr": float(g(ref, "annual_cost_inr", 0.0)),
            "dc_ppa_offtake_kwh": g(ref, "dc_ppa_offtake_kwh"),
            "dc_ppa_revenue_inr": g(ref, "dc_ppa_revenue_inr"),
            "dc_ppa_coverage_fraction": g(ref, "dc_ppa_coverage_fraction"),
            "dc_ppa_temporal_match_fraction": g(ref, "dc_ppa_temporal_match_fraction"),
            "dc_ppa_hours_supplied": g(ref, "dc_ppa_hours_supplied"),
        },
        "no_ppa": {"annual_cost_inr": g(noppa, "annual_cost_inr")},
        "firm_sweep": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)

    feas = [r for r in rows if r["feasible"]]
    with open(MD, "w", encoding="utf-8") as f:
        f.write("# PPA shape - largest firm round-the-clock block\n\n")
        f.write(f"Basis: {payload['basis']}. Generated {payload['generated']}.\n\n")
        # Values pulled out BEFORE the f-string. The model env is Python 3.9,
        # where a nested same-type quote inside an f-string is a SyntaxError
        # (PEP 701 relaxed that only in 3.12). A py_compile under the system
        # 3.14 passed and this still died at run time, after the first solve
        # had already spent six minutes. Compile-check with the SAME
        # interpreter that runs the model, not whichever is first on PATH.
        _rc = float(g(ref, "annual_cost_inr", 0.0) or 0.0)
        _ro = float(g(ref, "dc_ppa_offtake_kwh", 0.0) or 0.0) / 1e6
        _rv = float(g(ref, "dc_ppa_coverage_fraction", 0.0) or 0.0)
        _rm = float(g(ref, "dc_ppa_temporal_match_fraction", 0.0) or 0.0)
        f.write("Surplus-following reference: cost "
                "{:,.2f}, offtake {:,.2f} GWh, coverage {:.4f}, "
                "temporal match {:.4f}.\n\n".format(_rc, _ro, _rv, _rm))
        f.write("| firm block kW | feasible | annual cost | offtake GWh | coverage |\n")
        f.write("|---:|:--:|---:|---:|---:|\n")
        for r in rows:
            if r["feasible"]:
                f.write(f"| {r['firm_kw']:,} | yes | {r['annual_cost_inr']:,.0f} | "
                        f"{(r['dc_ppa_offtake_kwh'] or 0)/1e6:,.2f} | "
                        f"{(r['dc_ppa_coverage_fraction'] or 0):.4f} |\n")
            else:
                f.write(f"| {r['firm_kw']:,} | **no** | - | - | - |\n")
        if feas:
            best = max(feas, key=lambda r: r["firm_kw"])
            f.write(f"\n**Largest firm block the district can honour: "
                    f"{best['firm_kw']:,} kW**, against a 25,000 kW "
                    f"surplus-following contract.\n")
        else:
            f.write("\n**No firm block is feasible at any tested size.** The "
                    "district cannot commit to round-the-clock delivery at "
                    "all: it generates nothing between 18:00 and 05:00 that "
                    "is not already serving its own evening peak.\n")
    print(f"\nwrote {OUT}\nwrote {MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
