"""A21 -- price + grid-EF trajectory scenario sweep.

Runs the full_stack scenario at alpha=0 under each of the 4 named price
trajectories defined in `config/price_trajectories.yaml`:

  * bau_continued         -- 2.0%/yr real, IEA STEPS EF curve
  * nep_policy_push       -- 1.0%/yr real, CEA NEP 2022-32 + TERI 2050
  * high_renewables       -- -0.5%/yr (declining), TERI No-Fossil + CEEW
  * stress_coal_lock_in   -- 3.5%/yr, CAT current-policies + IEA WEO CPS

Reports annual cost, emissions, lifetime cost, and the deltas vs the
currently-active scenario as `outputs/data/energy/price_scenario_sweep.csv`
and a markdown summary at `outputs/data/energy/price_scenario_sweep.md`.

Does NOT touch the saved `dispatch_results.json` (that one stays at the
yaml's `active_scenario`). The sweep mutates `Economics.price_trajectories_raw`
in-memory between solves and restores at the end.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List

from energy.costs import load_economics
from energy.dispatch import solve_dispatch
from energy.network import load_optimised_network


SCENARIOS = (
    "bau_continued",
    "nep_policy_push",
    "high_renewables",
    "stress_coal_lock_in",
)
OUT_CSV = (Path(__file__).resolve().parent.parent
            / "outputs" / "data" / "energy" / "price_scenario_sweep.csv")
OUT_MD = (Path(__file__).resolve().parent.parent
           / "outputs" / "data" / "energy" / "price_scenario_sweep.md")


def _solve_for_scenario(scenario_name: str) -> Dict[str, object]:
    """Reload Economics + network, override active scenario, solve, return row."""
    econ = load_economics()
    net = load_optimised_network()
    # Override the active scenario at the in-memory layer.
    traj = econ.__dict__.get("price_trajectories_raw") or {}
    if not traj or scenario_name not in (traj.get("scenarios") or {}):
        raise RuntimeError(
            f"price_trajectories.yaml has no scenario {scenario_name!r}"
        )
    traj["active_scenario"] = scenario_name
    econ.__dict__["price_trajectories_raw"] = traj

    esc = econ.tariff_escalation_real_annual_value()
    ef_avg = econ.emission_factor_trajectory_average()

    result = solve_dispatch(net, econ, "full_stack", alpha=0.0)

    return {
        "scenario": scenario_name,
        "tariff_esc_real_annual": esc,
        "ef_trajectory_avg_kgco2_per_kwh": round(ef_avg, 4),
        "annual_cost_inr": round(result.annual_cost_inr, 2),
        "annual_emissions_kgco2": round(result.annual_emissions_kgco2, 2),
        "lifetime_cost_inr": round(result.lifetime_cost_inr, 2),
        "rooftop_pv_kwp": round(
            result.capacities.get("rooftop_pv_kwp", 0.0), 1
        ),
        "solar_farm_kwp": round(
            result.capacities.get("solar_farm_kwp", 0.0), 1
        ),
        "biomass_kw_e": round(result.capacities.get("biomass_kw_e", 0.0), 1),
        "solver": result.solver,
    }


def main() -> None:
    rows: List[Dict[str, object]] = []
    for s in SCENARIOS:
        print(f"  solving {s} ...")
        rows.append(_solve_for_scenario(s))

    # Reference (anchor) scenario for deltas = nep_policy_push (the YAML default).
    anchor_name = "nep_policy_push"
    anchor = next(r for r in rows if r["scenario"] == anchor_name)
    for r in rows:
        for key, anchor_val in (
            ("annual_cost_inr", anchor["annual_cost_inr"]),
            ("annual_emissions_kgco2", anchor["annual_emissions_kgco2"]),
            ("lifetime_cost_inr", anchor["lifetime_cost_inr"]),
        ):
            delta_key = f"delta_{key}_pct_vs_{anchor_name}"
            r[delta_key] = round(
                ((r[key] - anchor_val) / anchor_val * 100.0)
                if anchor_val else 0.0, 3,
            )

    # CSV.
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Markdown.
    md_lines: List[str] = []
    md_lines.append("# A21 -- price + grid-EF trajectory sweep")
    md_lines.append("")
    md_lines.append("Scenario: full_stack at alpha=0. Sourced via Pyomo+HiGHS LP.")
    md_lines.append("")
    md_lines.append(
        "| scenario | tariff esc | EF avg | annual cost (M INR) | "
        "emissions (kt) | lifetime cost (B INR) | "
        f"deltacost vs {anchor_name} (%) | deltaemiss vs {anchor_name} (%) |"
    )
    md_lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        md_lines.append(
            f"| {r['scenario']} | "
            f"{r['tariff_esc_real_annual']:.3f} | "
            f"{r['ef_trajectory_avg_kgco2_per_kwh']:.3f} | "
            f"{r['annual_cost_inr']/1e6:.1f} | "
            f"{r['annual_emissions_kgco2']/1e6:.2f} | "
            f"{r['lifetime_cost_inr']/1e9:.2f} | "
            f"{r[f'delta_annual_cost_inr_pct_vs_{anchor_name}']:.2f} | "
            f"{r[f'delta_annual_emissions_kgco2_pct_vs_{anchor_name}']:.2f} |"
        )
    md_lines.append("")
    md_lines.append(
        "Anchor: `nep_policy_push` (the YAML default `active_scenario`)."
    )
    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"\nwrote {OUT_CSV}")
    print(f"wrote {OUT_MD}")
    print("\nSummary:")
    for r in rows:
        print(
            f"  {r['scenario']:22s}  "
            f"cost {r['annual_cost_inr']/1e6:8.1f} M  "
            f"emiss {r['annual_emissions_kgco2']/1e6:5.2f} kt  "
            f"lifetime {r['lifetime_cost_inr']/1e9:5.2f} B"
        )


if __name__ == "__main__":
    main()
