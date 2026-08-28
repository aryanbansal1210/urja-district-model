"""Item 5 export-cap descending sweep.

In-memory descending-cap sweep on `econ.grid['export_capacity_limit_kw']`
under the production full_stack scenario (alpha=0). Finds the 2030 bite-
point: the cap value at which annual cost starts to deviate from the
non-binding 1e9-cap baseline.

NOTE: with `multi_period.enabled: true`, the Pyomo LP sizes capacities
in 2030 and solves all three periods (2030 / 2042 / 2055). Export peaks
in 2030 because demand grows 1.0 -> 1.75 across the horizon and absorbs
PV, so the 2030 max-slice export defines the binding limit.

Does NOT touch saved outputs. Mutates econ.grid in memory and restores.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the package import work whether invoked as `python scripts/...` or `python -m scripts.export_cap_sweep`.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from energy.costs import load_economics
from energy.dispatch import solve_dispatch
from energy.network import load_optimised_network


# Descending cap ladder in kW. 1e9 = effectively non-binding baseline.
CAPS_KW = [
    1_000_000_000,  # baseline non-binding
    200_000,
    150_000,
    120_000,
    100_000,
    80_000,
    60_000,
    50_000,
    45_000,
    40_000,
    35_000,
    30_000,
    25_000,
    20_000,
    15_000,
    10_000,
    5_000,
]


def _max_export_kw_for_period(result, period_year: int | None) -> float:
    """Max grid-export power (kW) across slices for the given period.

    If period_year is None, uses the legacy single-period `by_slice` (which
    Pyomo multi-period populates with the base-year/2030 snapshot)."""
    econ = load_economics()
    hours_by_id = {s.id: float(s.hours_per_year) for s in econ.slices}
    if period_year is None:
        slices = result.by_slice
        return max(
            (b.get("grid_export_kwh", 0.0) / hours_by_id[sid]) if hours_by_id.get(sid)
            else 0.0
            for sid, b in slices.items()
        )
    # Multi-period: read from period_breakdown grid_export_kwh aggregate only.
    pb = result.period_breakdown.get(period_year)
    if pb is None:
        return 0.0
    # If we want per-slice for non-2030 periods, we'd need to extend
    # period_breakdown. For now: 2030 max-slice = base-year by_slice.
    return 0.0


def main() -> None:
    print("Item 5 — export-cap descending sweep (full_stack alpha=0, multi_period on)")
    print("=" * 78)
    econ = load_economics()
    net = load_optimised_network()
    original_cap = econ.grid.get("export_capacity_limit_kw", 100_000)
    print(f"Original cap: {original_cap:,} kW")
    print(f"Solver: pyomo+highs; slices={len(econ.slices)}; "
          f"multi_period={econ.multi_period_enabled()}")
    print()
    print(f"{'cap_kw':>10} {'annual_cost':>16} {'em_kt':>8} "
          f"{'max_kw':>10} {'rooftop':>9} {'farm':>8} {'batt':>8} "
          f"{'v2g':>8} {'carport':>9} {'floatPV':>9} {'gridExp_GWh':>12}")
    print("-" * 132)
    results = []
    try:
        baseline_cost = None
        baseline_lifetime = None
        baseline_max_kw = None
        for cap in CAPS_KW:
            econ.grid["export_capacity_limit_kw"] = float(cap)
            r = solve_dispatch(net, econ, "full_stack", alpha=0.0)
            max_kw = _max_export_kw_for_period(r, None)
            if baseline_cost is None:
                baseline_cost = r.annual_cost_inr
                baseline_lifetime = r.lifetime_cost_inr
                baseline_max_kw = max_kw
            d_cost_pct = 100.0 * (r.annual_cost_inr - baseline_cost) / baseline_cost
            cap_kwh = r.capacities or {}
            roof = cap_kwh.get("rooftop_pv_kwp", 0.0)
            farm = cap_kwh.get("solar_farm_kwp", 0.0)
            batt = cap_kwh.get("battery_kwh", 0.0)
            v2g = cap_kwh.get("v2g_units", 0.0)
            carport = cap_kwh.get("carport_kwp", 0.0)
            float_pv = cap_kwh.get("floating_pv_kwp", 0.0)
            print(f"{cap:>10,d} {r.annual_cost_inr:>16,.0f} "
                  f"{r.annual_emissions_kgco2/1e6:>8.2f} "
                  f"{max_kw:>10,.0f} "
                  f"{roof:>9,.0f} {farm:>8,.0f} {batt:>8,.0f} "
                  f"{v2g:>8,.0f} {carport:>9,.0f} {float_pv:>9,.0f} "
                  f"{r.grid_export_kwh/1e6:>12,.1f}")
            results.append({
                "cap_kw": cap,
                "annual_cost_inr": r.annual_cost_inr,
                "lifetime_cost_inr": r.lifetime_cost_inr,
                "max_export_kw_2030": max_kw,
                "delta_cost_pct": d_cost_pct,
                "annual_emissions_kgco2": r.annual_emissions_kgco2,
                "grid_export_kwh_2030": r.grid_export_kwh,
                "battery_kwh": batt,
            })
        print()
        print(f"Non-binding baseline (cap=1e9): max-slice 2030 export = "
              f"{baseline_max_kw:,.0f} kW, annual cost {baseline_cost:,.0f} INR")
        print("Bite-point: the lowest cap >= max_export_kw_2030 (non-binding); "
              "below that the LP starts curtailing (cost rises).")
    finally:
        econ.grid["export_capacity_limit_kw"] = original_cap
        print(f"Restored econ.grid['export_capacity_limit_kw'] = {original_cap}")


if __name__ == "__main__":
    main()
