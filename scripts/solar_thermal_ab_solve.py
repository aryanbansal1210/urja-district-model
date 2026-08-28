"""Does the LP actually build solar water heating, how much, and why?

. the author: "when are we going to know if it installs and how much and
why". This answers all three by solving the production multi-period model
twice on ONE network, with the technology off and then on, and differencing.

A PREDICTION IS ON RECORD AND THIS RUN CAN FALSIFY IT.
_spec/SOLAR_THERMAL_VERIFICATION_20260817.md predicts, from hand arithmetic
before any solve:

    45,000-50,000 m2 of collector, about 7% of deployable roof,
    serving 75-80% of district hot water.

The reasoning was that each m2 must clear Rs 2,126/yr (its own annualised cost,
minus the PV capex it displaces, plus the PV generation it gives up), that a
displaced hot-water kWh is worth Rs 5.924 weighted by the measured draw shape,
and that the marginal collector therefore has to return 359 kWh/m2/yr. That
crosses over near 50,000 m2.

If the LP disagrees, the difference is the interesting result, not an error to
be explained away. Likely reasons it could build MORE: the grid-connection
saving, which the hand arithmetic omitted; or interaction with the battery,
which says arrives only in 2042. Likely reasons it could build LESS: the
roof competition binding harder than assumed, or the bucket storage
formulation being stricter than the hour-by-hour simulation.

BOTH SOLVES USE THE SAME NETWORK OBJECT, so nothing but the technology flag
differs. The OFF case is also a check on itself: it must reproduce the
production numbers, because switching a flag off must leave the model where it
was.

    PYTHONPATH=. python -u scripts/solar_thermal_ab_solve.py
"""
from __future__ import annotations

import dataclasses
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "verification" / "solar_thermal_ab_solve.txt"
_t0 = time.time()
_lines = []


def w(s: str = "") -> None:
    _lines.append(s)
    print(s, flush=True)


def step(s: str) -> None:
    print(f"[{time.time()-_t0:7.1f}s] {s}", flush=True)


def main() -> None:
    from energy.costs import load_economics
    from energy.dispatch import solve_dispatch
    from energy.network import load_optimised_network

    step("loading economics")
    econ = load_economics(force_reload=True)
    step("building network (shading precompute, ~19 min, uncached - PERF-1)")
    net = load_optimised_network(econ=econ)
    step("network ready")

    roof = None
    results = {}
    for label, cfg_on in (("OFF", False), ("ON", True)):
        econ.technologies["solar_thermal"] = {
            **econ.technologies["solar_thermal"], "enabled": cfg_on}
        # `solve_dispatch` takes a scenario NAME and looks it up, and
        # `Scenario` is a frozen dataclass, so the flag is set by replacing
        # the entry in the registry rather than by mutating the object.
        # Mutating raises FrozenInstanceError, which an earlier script
        # swallowed in a bare except and thereby tested nothing.
        econ.scenarios["full_stack"] = dataclasses.replace(
            econ.scenarios["full_stack"], allow_solar_thermal=cfg_on)
        assert econ.scenario("full_stack").allow_solar_thermal is cfg_on
        if cfg_on:
            roof = net.solar_thermal_roof_cap_m2(econ)
            step(f"  eligible roof for collectors: {roof:,.0f} m2")
        step(f"  SOLVING solar thermal {label}")
        t = time.time()
        r = solve_dispatch(net, econ, "full_stack", alpha=0.0)
        step(f"  solved in {time.time()-t:.0f}s")
        results[label] = r

    off, on = results["OFF"], results["ON"]
    co, cn = off.capacities or {}, on.capacities or {}

    w("=" * 78)
    w("DOES THE LP BUILD SOLAR WATER HEATING?")
    w("=" * 78)
    m2 = float(cn.get("solar_thermal_m2", 0.0))
    served = float(cn.get("solar_thermal_served_kwh", 0.0))
    w("")
    if m2 <= 1.0:
        w("  ANSWER: NO. The LP builds none of it.")
    else:
        w(f"  ANSWER: YES. {m2:,.0f} m2 of collector.")
        if roof:
            w(f"          = {m2/roof:.1%} of eligible roof")
        w(f"          delivering {served/1e6:.2f} GWh/yr of hot water"
          f"  ({served/36.146e6:.1%} of the district's water heating)")

    w("")
    w("PREDICTION ON RECORD (made before this solve):")
    w("  45,000-50,000 m2, ~7% of roof, 75-80% of hot water")
    if m2 > 1.0:
        w(f"  ACTUAL: {m2:,.0f} m2"
          f"  -> prediction {'HELD' if 45000 <= m2 <= 50000 else 'MISSED'}")
        if m2 > 50000:
            w("  Built MORE than predicted. First place to look is the grid")
            w("  connection saving, which the hand arithmetic left out.")
        elif m2 < 45000:
            w("  Built LESS than predicted. First place to look is the roof")
            w("  competition, or the bucket storage being stricter than the")
            w("  hour-by-hour simulation it was calibrated against.")

    w("")
    w("=" * 78)
    w("WHAT IT COST AND WHAT IT SAVED")
    w("=" * 78)
    w(f"{'':<34}{'OFF':>18}{'ON':>18}{'delta':>14}")
    rows = [
        ("annual cost, Rs", off.annual_cost_inr, on.annual_cost_inr),
        ("annual CO2, kg", off.annual_emissions_kgco2,
         on.annual_emissions_kgco2),
        ("lifetime cost, Rs", off.lifetime_cost_inr, on.lifetime_cost_inr),
        ("demand met, kWh", off.annual_demand_kwh, on.annual_demand_kwh),
        ("grid import, kWh", off.grid_import_kwh, on.grid_import_kwh),
        ("grid export, kWh", off.grid_export_kwh, on.grid_export_kwh),
        ("PV generation, kWh", off.pv_generation_kwh, on.pv_generation_kwh),
    ]
    for name, a, b in rows:
        d = b - a
        w(f"{name:<34}{a:>18,.0f}{b:>18,.0f}{d:>+14,.0f}"
          + (f"  {d/a:+.3%}" if a else ""))

    w("")
    w("=" * 78)
    w("THE ROOF COMPETITION - what it displaced")
    w("=" * 78)
    for k, unit in (("rooftop_pv_kwp", "kWp"), ("solar_farm_kwp", "kWp"),
                    ("battery_kwh", "kWh"), ("carport_kwp", "kWp"),
                    ("bipv_kwp", "kWp"), ("floating_pv_kwp", "kWp"),
                    ("v2g_units", "units"), ("biomass_kw_e", "kW_e"),
                    ("thermal_storage_kwh", "kWh")):
        a, b = float(co.get(k, 0.0)), float(cn.get(k, 0.0))
        if a or b:
            w(f"  {k:<26}{a:>14,.0f}{b:>14,.0f}{b-a:>+13,.0f} {unit}"
              + ("   <- displaced" if b < a - 1 else ""))

    w("")
    w("=" * 78)
    w("BUILD PATH BY PERIOD - when does it arrive?")
    w("=" * 78)
    pb = on.period_breakdown or {}
    for p in sorted(pb):
        ic = (pb[p] or {}).get("installed_capacities") or {}
        nc = (pb[p] or {}).get("new_build") or {}
        w(f"  {p}: new {float(nc.get('solar_thermal_m2',0)):>10,.0f} m2"
          f"   installed {float(ic.get('solar_thermal_m2',0)):>10,.0f} m2"
          f"   rooftop PV {float(ic.get('rooftop_pv_kwp',0)):>10,.0f} kWp")

    w("")
    w("=" * 78)
    w("WHY - the economics the LP was choosing against")
    w("=" * 78)
    if m2 > 1.0:
        cost_delta = on.annual_cost_inr - off.annual_cost_inr
        w(f"  net annual cost change: Rs {cost_delta:+,.0f}")
        if cost_delta < 0:
            w(f"  The technology PAYS: it saves Rs {-cost_delta:,.0f}/yr net of")
            w(f"  its own cost and of the PV it displaces.")
            if served:
                w(f"  Effective value: Rs {-cost_delta/served:.3f} per kWh of")
                w(f"  hot water served, AFTER paying for the collector.")
        else:
            w("  *** IT BUILT DESPITE RAISING TOTAL COST, WHICH SHOULD BE")
            w("  IMPOSSIBLE IN A COST-MINIMISING LP. Investigate before")
            w("  reporting: most likely a constraint is forcing it. ***")
        w(f"  CO2 change: {on.annual_emissions_kgco2-off.annual_emissions_kgco2:+,.0f} kg/yr")
    else:
        w("  It did not build, so the marginal square metre never cleared its")
        w("  hurdle. Compare against the hand arithmetic in")
        w("  _spec/SOLAR_THERMAL_VERIFICATION_20260817.md, which put the")
        w("  break-even at 359 kWh/m2/yr of marginal yield.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(_lines), encoding="utf-8")
    step(f"written {OUT.name}")


if __name__ == "__main__":
    main()
