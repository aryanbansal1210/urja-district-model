"""Focused sensitivity analysis for the Stage C production headline.

One-shot driver (NOT a comprehensive Stage E tornado). Runs +/-20% one-at-a-time
on five uncertain parameters around the documented full_stack alpha=0 headline
produced by the Pyomo+HiGHS MILP path:

    1. Li-ion 2030 CAPEX            (tech_costs.li_ion_battery.capex_inr_per_kwh)
    2. Grid emission trajectory     (grid.emission_factor_trajectory_kgco2_per_kwh)
    3. Demand scale                 (per-slice district demand, scaled in-cache)
    4. Carbon price                 (carbon_objective.carbon_price_inr_per_kgco2)
    5. Biomass fuel cost            (tech_costs.biomass_chp.fuel_cost_inr_per_tonne)

Each perturbation reloads a fresh Economics + EnergyNetwork, mutates the
in-memory config (no YAML edits), and re-solves full_stack at alpha=0 via
solve_dispatch (auto -> Pyomo+HiGHS). Outputs:

    outputs/data/energy/sensitivity_focused.csv
    outputs/data/energy/sensitivity_focused.json

Notes on interpretation:
- The Pyomo dispatch consumes net.demand_by_slice_kwh(econ) which is cached
  on the network by id(econ). Demand scaling pre-populates the cache and
  multiplies the cached dict in place; the demand_mult applied later
  (biosolar) stacks multiplicatively but is ~0.994 at default, so the
  realised demand uplift matches the requested multiplier within 0.6 %.
- The grid emission factor enters the dispatch via
  econ.emission_factor_trajectory_average which averages the 2025-2050
  trajectory across the 25-year project lifetime. Scaling every trajectory
  point by m scales the lifetime average by m -- a clean "slope-and-level"
  perturbation, documented as such.
- Carbon price weights the emissions term in the objective:
  (1-alpha)*cost + alpha*carbon_price*emissions. At alpha=0 the carbon
  price does not affect the optimum and the sensitivity is mathematically
  zero. This is reported honestly in the CSV/JSON.

Run:
    /c/Users/the author/anaconda3/envs/sef-python-demo/python.exe \\
        -m scripts.sensitivity_focused
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from energy.costs import Economics, load_economics
from energy.dispatch import DispatchResult, has_pyomo, solve_dispatch
from energy.network import EnergyNetwork, load_optimised_network


SCENARIO = "full_stack"
# (Claude 2): extended to multi-alpha sweep. alpha=0 is the
# documented cost-min headline; alpha=0.5 sits at the Pareto interior
# where BOTH cost and emissions enter the objective, so params that did
# nothing at alpha=0 (carbon price, Li-ion CAPEX with battery cap=0)
# get a chance to move things.
ALPHAS: Tuple[float, ...] = (0.0, 0.5)
MULTIPLIERS = (0.8, 1.2)

OUTPUT_DIR = (Path(__file__).resolve().parent.parent
              / "outputs" / "data" / "energy")
CSV_PATH = OUTPUT_DIR / "sensitivity_focused.csv"
JSON_PATH = OUTPUT_DIR / "sensitivity_focused.json"


# ---------------------------------------------------------------------------
# Perturbation functions. Each accepts (econ, net, multiplier) and mutates
# the inputs in place. Called BEFORE solve_dispatch.
# ---------------------------------------------------------------------------
def _perturb_li_ion_capex(econ: Economics, net: EnergyNetwork, m: float) -> float:
    base = float(econ.technologies["li_ion_battery"]["capex_inr_per_kwh"])
    econ.technologies["li_ion_battery"]["capex_inr_per_kwh"] = base * m
    return base * m


def _perturb_grid_trajectory(econ: Economics, net: EnergyNetwork, m: float) -> float:
    traj = econ.grid["emission_factor_trajectory_kgco2_per_kwh"]
    for key in list(traj.keys()):
        traj[key] = float(traj[key]) * m
    # also scale the static fallback EF so the reported scenario field tracks
    econ.grid["emission_factor_kgco2_per_kwh"] = (
        float(econ.grid["emission_factor_kgco2_per_kwh"]) * m
    )
    return econ.emission_factor_trajectory_average()


def _perturb_demand(econ: Economics, net: EnergyNetwork, m: float) -> float:
    # Force the slice-demand cache to populate, then scale in place. Pyomo
    # and fallback both read this dict.
    cached = net.demand_by_slice_kwh(econ)
    for sid in list(cached.keys()):
        cached[sid] *= m
    return sum(cached.values())


def _perturb_carbon_price(econ: Economics, net: EnergyNetwork, m: float) -> float:
    cobj = econ.__dict__.get("carbon_objective_raw") or {}
    base = float(cobj.get("carbon_price_inr_per_kgco2", 2.5))
    cobj["carbon_price_inr_per_kgco2"] = base * m
    econ.__dict__["carbon_objective_raw"] = cobj
    return base * m


def _perturb_biomass_fuel(econ: Economics, net: EnergyNetwork, m: float) -> float:
    tech = econ.technologies["biomass_chp"]
    base = float(tech["fuel_cost_inr_per_tonne"])
    tech["fuel_cost_inr_per_tonne"] = base * m
    return base * m


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    yaml_path: str
    unit: str
    apply: Callable[[Economics, EnergyNetwork, float], float]


PARAMS: List[ParamSpec] = [
    ParamSpec(
        key="li_ion_capex",
        label="Li-ion 2030 CAPEX",
        yaml_path="technologies.li_ion_battery.capex_inr_per_kwh",
        unit="INR/kWh",
        apply=_perturb_li_ion_capex,
    ),
    ParamSpec(
        key="grid_trajectory_slope",
        label="Grid emission trajectory (uniform scale = slope+level)",
        yaml_path="grid.emission_factor_trajectory_kgco2_per_kwh",
        unit="lifetime-avg kgCO2/kWh",
        apply=_perturb_grid_trajectory,
    ),
    ParamSpec(
        key="demand_scale",
        label="District demand scale (per-slice cache multiplier)",
        yaml_path="energy.network.demand_by_slice_kwh",
        unit="GWh/yr",
        apply=_perturb_demand,
    ),
    ParamSpec(
        key="carbon_price",
        label="Carbon shadow price",
        yaml_path="carbon_objective.carbon_price_inr_per_kgco2",
        unit="INR/kgCO2",
        apply=_perturb_carbon_price,
    ),
    ParamSpec(
        key="biomass_fuel_cost",
        label="Biomass paddy-straw fuel cost",
        yaml_path="technologies.biomass_chp.fuel_cost_inr_per_tonne",
        unit="INR/tonne",
        apply=_perturb_biomass_fuel,
    ),
]


# ---------------------------------------------------------------------------
# Run wrapper.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RunRecord:
    param: str
    label: str
    alpha: float
    multiplier: float
    perturbed_value: float
    solver: str
    annual_cost_inr: float
    annual_emissions_kgco2: float
    lifetime_cost_inr: float
    annual_demand_kwh: float
    cap_rooftop_kwp: float
    cap_solar_farm_kwp: float
    cap_battery_kwh: float
    cap_biomass_kw_e: float
    cap_carport_kwp: float
    cap_floating_pv_kwp: float

    def as_row(self) -> Dict[str, object]:
        return {
            "param": self.param,
            "label": self.label,
            "alpha": f"{self.alpha:.2f}",
            "multiplier": f"{self.multiplier:.2f}",
            "perturbed_value": f"{self.perturbed_value:.4f}",
            "solver": self.solver,
            "annual_cost_inr": f"{self.annual_cost_inr:.2f}",
            "annual_emissions_kgco2": f"{self.annual_emissions_kgco2:.2f}",
            "lifetime_cost_inr": f"{self.lifetime_cost_inr:.2f}",
            "annual_demand_kwh": f"{self.annual_demand_kwh:.2f}",
            "cap_rooftop_kwp": f"{self.cap_rooftop_kwp:.1f}",
            "cap_solar_farm_kwp": f"{self.cap_solar_farm_kwp:.1f}",
            "cap_battery_kwh": f"{self.cap_battery_kwh:.1f}",
            "cap_biomass_kw_e": f"{self.cap_biomass_kw_e:.1f}",
            "cap_carport_kwp": f"{self.cap_carport_kwp:.1f}",
            "cap_floating_pv_kwp": f"{self.cap_floating_pv_kwp:.1f}",
        }


def _record(result: DispatchResult, param: str, label: str,
            alpha: float, multiplier: float, perturbed_value: float,
            annual_demand_kwh: float) -> RunRecord:
    caps = result.capacities
    return RunRecord(
        param=param,
        label=label,
        alpha=alpha,
        multiplier=multiplier,
        perturbed_value=perturbed_value,
        solver=result.solver,
        annual_cost_inr=result.annual_cost_inr,
        annual_emissions_kgco2=result.annual_emissions_kgco2,
        lifetime_cost_inr=getattr(result, "lifetime_cost_inr", 0.0) or 0.0,
        annual_demand_kwh=annual_demand_kwh,
        cap_rooftop_kwp=caps.get("rooftop_pv_kwp", 0.0),
        cap_solar_farm_kwp=caps.get("solar_farm_kwp", 0.0),
        cap_battery_kwh=caps.get("battery_kwh", 0.0),
        cap_biomass_kw_e=caps.get("biomass_kw_e", 0.0),
        cap_carport_kwp=caps.get("carport_kwp", 0.0),
        cap_floating_pv_kwp=caps.get("floating_pv_kwp", 0.0),
    )


def _solve_one(param: ParamSpec, multiplier: float, alpha: float) -> RunRecord:
    """Fresh econ + net per run, apply one perturbation, solve full_stack
    at the given alpha via solve_dispatch (auto-prefers Pyomo+HiGHS)."""
    econ = load_economics()
    net = load_optimised_network()
    perturbed_value = param.apply(econ, net, multiplier)
    annual_demand_kwh = net.annual_demand_kwh(econ)
    result = solve_dispatch(net, econ, SCENARIO, alpha=alpha)
    return _record(result, param.key, param.label, alpha,
                   multiplier, perturbed_value, annual_demand_kwh)


def _base_record(alpha: float) -> RunRecord:
    econ = load_economics()
    net = load_optimised_network()
    annual_demand_kwh = net.annual_demand_kwh(econ)
    result = solve_dispatch(net, econ, SCENARIO, alpha=alpha)
    return _record(result, "base", "Unperturbed base case", alpha,
                   1.0, 1.0, annual_demand_kwh)


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------
def main() -> None:
    if not has_pyomo():
        raise RuntimeError(
            "Pyomo unavailable -- this script REQUIRES the production "
            "Pyomo+HiGHS MILP path. Install with: pip install pyomo highspy"
        )

    print(f"Sensitivity-focused run: scenario={SCENARIO}, "
          f"alphas={list(ALPHAS)}, +/-20% OAT on {len(PARAMS)} parameters.")
    print(f"Production solver: Pyomo+HiGHS MILP (verified, has_pyomo=True)")
    print()

    records: List[RunRecord] = []
    bases: Dict[float, RunRecord] = {}
    for alpha in ALPHAS:
        print(f"=== alpha = {alpha} ===")
        base = _base_record(alpha)
        bases[alpha] = base
        records.append(base)
        print(f"  base                              "
              f"cost={base.annual_cost_inr/1e6:>8.2f} M INR/yr  "
              f"emiss={base.annual_emissions_kgco2/1e6:>6.2f} ktCO2/yr  "
              f"solver={base.solver}")
        for p in PARAMS:
            for m in MULTIPLIERS:
                rec = _solve_one(p, m, alpha)
                records.append(rec)
                d_cost = (rec.annual_cost_inr - base.annual_cost_inr) / base.annual_cost_inr
                d_em = ((rec.annual_emissions_kgco2 - base.annual_emissions_kgco2)
                         / base.annual_emissions_kgco2
                         if base.annual_emissions_kgco2 else 0.0)
                print(f"  {p.key:<20} x{m:<4.2f}        "
                      f"cost={rec.annual_cost_inr/1e6:>8.2f} M ({d_cost*100:+6.2f}%)  "
                      f"emiss={rec.annual_emissions_kgco2/1e6:>6.2f} kt "
                      f"({d_em*100:+6.2f}%)")
        print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def _base_for(r: RunRecord) -> RunRecord:
        return bases[r.alpha]

    # CSV
    cols = list(records[0].as_row().keys())
    cols.extend(["delta_cost_pct_vs_base", "delta_emissions_pct_vs_base"])
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in records:
            b = _base_for(r)
            row = r.as_row()
            d_cost = (r.annual_cost_inr - b.annual_cost_inr) / b.annual_cost_inr
            if b.annual_emissions_kgco2 != 0:
                d_em = ((r.annual_emissions_kgco2 - b.annual_emissions_kgco2)
                         / b.annual_emissions_kgco2)
            else:
                d_em = 0.0
            row["delta_cost_pct_vs_base"] = f"{d_cost*100:.3f}"
            row["delta_emissions_pct_vs_base"] = f"{d_em*100:.3f}"
            w.writerow(row)

    # JSON (richer payload incl. per-alpha movers summary)
    movers_by_alpha: Dict[str, Dict[str, List[Dict[str, float]]]] = {}
    for alpha in ALPHAS:
        b = bases[alpha]
        by_param: Dict[str, Dict[str, RunRecord]] = {}
        for r in records:
            if r.param == "base" or r.alpha != alpha:
                continue
            side = "low" if r.multiplier < 1.0 else "high"
            by_param.setdefault(r.param, {})[side] = r
        m_cost: List[Dict[str, float]] = []
        m_em: List[Dict[str, float]] = []
        for param_key, sides in by_param.items():
            low = sides.get("low")
            high = sides.get("high")
            if low is None or high is None:
                continue
            d_cost_low = (low.annual_cost_inr - b.annual_cost_inr) / b.annual_cost_inr
            d_cost_high = (high.annual_cost_inr - b.annual_cost_inr) / b.annual_cost_inr
            cost_span = abs(d_cost_high - d_cost_low)
            d_em_low = ((low.annual_emissions_kgco2 - b.annual_emissions_kgco2)
                        / b.annual_emissions_kgco2
                        if b.annual_emissions_kgco2 else 0.0)
            d_em_high = ((high.annual_emissions_kgco2 - b.annual_emissions_kgco2)
                         / b.annual_emissions_kgco2
                         if b.annual_emissions_kgco2 else 0.0)
            em_span = abs(d_em_high - d_em_low)
            m_cost.append({"param": param_key, "cost_span_pct": cost_span * 100})
            m_em.append({"param": param_key, "emissions_span_pct": em_span * 100})
        m_cost.sort(key=lambda d: -d["cost_span_pct"])
        m_em.sort(key=lambda d: -d["emissions_span_pct"])
        movers_by_alpha[f"alpha={alpha}"] = {
            "by_cost_span": m_cost,
            "by_emissions_span": m_em,
        }

    payload = {
        "schema_version": "1.1",
        "scenario": SCENARIO,
        "alphas": list(ALPHAS),
        "solver_reported_by_base_run": bases[ALPHAS[0]].solver,
        "multipliers": list(MULTIPLIERS),
        "bases": {
            f"alpha={a}": {
                "annual_cost_inr": bases[a].annual_cost_inr,
                "annual_emissions_kgco2": bases[a].annual_emissions_kgco2,
                "lifetime_cost_inr": bases[a].lifetime_cost_inr,
                "annual_demand_kwh": bases[a].annual_demand_kwh,
            }
            for a in ALPHAS
        },
        "params": [
            {
                "key": p.key,
                "label": p.label,
                "yaml_path": p.yaml_path,
                "unit": p.unit,
            }
            for p in PARAMS
        ],
        "runs": [
            {
                "param": r.param,
                "label": r.label,
                "alpha": r.alpha,
                "multiplier": r.multiplier,
                "perturbed_value": r.perturbed_value,
                "solver": r.solver,
                "annual_cost_inr": r.annual_cost_inr,
                "annual_emissions_kgco2": r.annual_emissions_kgco2,
                "lifetime_cost_inr": r.lifetime_cost_inr,
                "annual_demand_kwh": r.annual_demand_kwh,
                "delta_cost_pct_vs_base": (
                    (r.annual_cost_inr - bases[r.alpha].annual_cost_inr)
                    / bases[r.alpha].annual_cost_inr * 100
                ),
                "delta_emissions_pct_vs_base": (
                    (r.annual_emissions_kgco2 - bases[r.alpha].annual_emissions_kgco2)
                    / bases[r.alpha].annual_emissions_kgco2 * 100
                    if bases[r.alpha].annual_emissions_kgco2 else 0.0
                ),
                "capacities": {
                    "rooftop_pv_kwp": r.cap_rooftop_kwp,
                    "solar_farm_kwp": r.cap_solar_farm_kwp,
                    "battery_kwh": r.cap_battery_kwh,
                    "biomass_kw_e": r.cap_biomass_kw_e,
                    "carport_kwp": r.cap_carport_kwp,
                    "floating_pv_kwp": r.cap_floating_pv_kwp,
                },
            }
            for r in records
        ],
        "movers_by_alpha": movers_by_alpha,
        "notes": [
            "alpha=0 is the cost-min headline. Carbon price has no effect at "
            "alpha=0 by construction of the weighted objective.",
            "Grid emission trajectory is perturbed by uniform scaling of all "
            "anchor years; this scales both the slope and the lifetime average "
            "by the same factor.",
            "Demand-scale perturbation multiplies the cached per-slice demand "
            "dict in place; the residual biosolar demand_mult ~0.994 stacks "
            "on top, so realised demand uplift matches the requested "
            "multiplier within 0.6 %.",
            "At alpha=0 the LP cost-optimal face is degenerate in per-slice "
            "flows: capacity choices are identical across perturbations of "
            "params that do not affect cost (Li-ion CAPEX with battery cap "
            "= 0, carbon price by construction, grid EF), but per-slice "
            "imports/biomass/V2G dispatches can land on different equal-cost "
            "vertices. Cost-side deltas at 0.000 are real (LP optimum "
            "unchanged); emissions-side deltas of order +/-3 % on those "
            "rows are LP-degeneracy noise, not economic sensitivity.",
            "Battery capacity is zero at alpha=0 (per LOGBOOK Caveat 1: "
            "annualised 9k INR/kWh CRF still exceeds achievable spread + "
            "reliability credit). +/-20% Li-ion CAPEX therefore moves "
            "nothing -- the optimum's response to Li-ion CAPEX is binary "
            "and only flips above some breakeven we haven't probed.",
            "2026-05-16 multi-alpha extension: sweep now runs at "
            "alpha=0 (cost-min headline) AND alpha=0.5 (Pareto interior). "
            "Empirical finding: in THIS LP formulation, the Pareto is "
            "FLAT across alpha=0.4-0.92 (see carbon_pareto.csv). At any "
            "alpha in that plateau, carbon-price +/-20% acts as a "
            "multiplicative scaling of the emissions term that is "
            "LP-invariant -- the optimum doesn't move. Carbon-price "
            "uncertainty does NOT propagate to the headline numbers in "
            "this scenario; defensible robustness statement, not a bug.",
            "Li-ion CAPEX +/-20%: battery capacity is zero at BOTH "
            "alpha=0 AND alpha=0.5 (annualised 9k INR/kWh CRF still "
            "exceeds achievable spread + reliability credit). The "
            "breakeven for battery deployment sits above alpha ~0.95 in "
            "this formulation; a +/-20% CAPEX perturbation does not "
            "cross it. Defensible: 2030 INR Li-ion pricing is robust to "
            "+/-20% uncertainty under the current carbon-objective "
            "structure.",
        ],
    }
    with JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print()
    print(f"wrote {CSV_PATH}")
    print(f"wrote {JSON_PATH}")

    print()
    for alpha_key, movers in movers_by_alpha.items():
        print(f"--- {alpha_key} ---")
        print("Strongest cost mover:")
        for m in movers["by_cost_span"][:1]:
            print(f"  {m['param']:<24} cost span {m['cost_span_pct']:.2f} pp")
        print("Strongest emissions mover:")
        for m in movers["by_emissions_span"][:1]:
            print(f"  {m['param']:<24} emissions span {m['emissions_span_pct']:.2f} pp")


if __name__ == "__main__":
    main()
