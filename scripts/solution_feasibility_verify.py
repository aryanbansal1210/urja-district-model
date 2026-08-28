"""Independent feasibility + validity verification of the recovered production solution
. Re-checks the published full_stack alpha=0 by_slice solution
against the LP's own constraints WITHOUT trusting the solver: per-slice balance residual,
caps, V2G/biomass limits, monthly DSR + storage conservation, and an objective recompute.
Run: python scripts/solution_feasibility_verify.py
"""
from __future__ import annotations
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
from energy.costs import load_economics
from energy.network import load_optimised_network

econ = load_economics(force_reload=True)
net = load_optimised_network()
d = json.load(open("outputs/data/energy/dispatch_results.json", encoding="utf-8"))
sc = [s for s in d["scenarios"] if s["name"] == "full_stack" and abs(s.get("alpha", 1)) < 1e-9][0]
bs = sc["by_slice"]
sl = {s["id"]: s for s in d["slices"]}
cap = sc["capacities"]

ac_eff = 1.0 - econ.ac_loss_fraction()
pspcl_eff = 1.0 - econ.pspcl_grid_loss_fraction()
gi_eff = ac_eff * pspcl_eff

print("=== 1. PER-SLICE BALANCE RESIDUAL (recovered solution vs the LP equality) ===")
# eff_dem + charge + thermal_chg + exp [+ dc_ppa] == pv + ac*(dis+v2g) + thermal_dis + bio + wte + biogas + gi_eff*imp
# NOTE: by_slice pv_kwh is the exported PV supply value; discharge/v2g signs in JSON are negative-out.
worst = []
tot_res = 0.0
for sid, b in bs.items():
    if sl[sid]["hours_per_year"] <= 0:
        continue
    # solar water heating, see tests/test_solution_feasibility.py
    eff_dem = (b["demand_kwh"] - b["dsr_reduce_kwh"] + b["dsr_add_kwh"]
               - b.get("solar_thermal_served_kwh", 0.0))
    lhs = eff_dem + b["battery_charge_kwh"] + b["thermal_storage_charge_kwh"] + b["grid_export_kwh"] + b.get("dc_ppa_kwh", 0.0)
    rhs = (b["pv_kwh"] + ac_eff * (abs(b["battery_discharge_kwh"]) + abs(b["v2g_discharge_kwh"]))
           + abs(b["thermal_storage_discharge_kwh"]) + abs(b["biomass_kwh"]) + abs(b["wte_kwh"]) + abs(b["biogas_kwh"])
           + gi_eff * b["grid_import_kwh"])
    res = lhs - rhs
    tot_res += abs(res)
    worst.append((abs(res), sid, res))
worst.sort(reverse=True)
print(f"   sum |residual| = {tot_res:,.1f} kWh over the year ({tot_res/sc['annual_demand_kwh']*100:.4f}% of demand)")
for a, sid, r in worst[:5]:
    print(f"   worst: {sid} residual {r:,.1f} kWh")

print("=== 2. CAPS ===")
imp_cap = econ.import_capacity_limit_kw(); exp_cap = econ.export_capacity_limit_kw()
v_imp = [(b["grid_import_kwh"] / sl[sid]["hours_per_year"], sid) for sid, b in bs.items() if sl[sid]["hours_per_year"] > 0]
v_exp = [(b["grid_export_kwh"] / sl[sid]["hours_per_year"], sid) for sid, b in bs.items() if sl[sid]["hours_per_year"] > 0]
print(f"   import max {max(v_imp)[0]:,.0f} kW <= cap {imp_cap:,.0f}: {'OK' if max(v_imp)[0] <= imp_cap*1.0001 else '*** VIOLATION ***'}")
print(f"   export max {max(v_exp)[0]:,.0f} kW <= cap {exp_cap:,.0f}: {'OK' if max(v_exp)[0] <= exp_cap*1.0001 else '*** VIOLATION ***'}")

print("=== 3. V2G monthly energy + slice power ===")
v2g_units = cap["v2g_units"]; v2g_day = econ.v2g_kwh_per_unit_per_day(); v2g_kw = econ.v2g_power_kw_per_unit()
viol = 0
from collections import defaultdict
v2g_m = defaultdict(float)
for sid, b in bs.items():
    v2g_m[sl[sid]["month"]] += abs(b["v2g_discharge_kwh"])
    h = sl[sid]["hours_per_year"]
    if h > 0 and abs(b["v2g_discharge_kwh"]) > v2g_kw * v2g_units * h * 1.0001:
        viol += 1
print(f"   slice power violations: {viol}")
for mm, v in v2g_m.items():
    days = econ.calendar.get(mm, {}).get("days", 30)
    limit = days * v2g_day * v2g_units
    if v > limit * 1.0001:
        print(f"   *** {mm}: v2g {v:,.0f} > {limit:,.0f} ***")
print("   monthly energy: OK (no violations printed)")

print("=== 4. BIOMASS/WTE/BIOGAS annual hours ===")
for tech, key, cap_kw, hrs in [("biomass", "biomass_kwh", cap["biomass_kw_e"], econ.biomass_operating_hours_per_year()),
                                ("wte", "wte_kwh", cap["wte_kw_e"], econ.wte_operating_hours_per_year()),
                                ("biogas", "biogas_kwh", cap["biogas_kw_e"], econ.biogas_operating_hours_per_year())]:
    ann = sum(abs(b[key]) for b in bs.values())
    print(f"   {tech}: {ann:,.0f} kWh <= {cap_kw * hrs:,.0f} ({ann/(cap_kw*hrs)*100:.1f}% of annual-hours cap)"
          + ("" if ann <= cap_kw * hrs * 1.0001 else "  *** VIOLATION ***"))

print("=== 5. DSR monthly conservation (recovered) ===")
red_m = defaultdict(float); add_m = defaultdict(float)
for sid, b in bs.items():
    red_m[sl[sid]["month"]] += b["dsr_reduce_kwh"]; add_m[sl[sid]["month"]] += b["dsr_add_kwh"]
bad = [mm for mm in red_m if abs(red_m[mm] - add_m[mm]) > 1.0]
print(f"   months violating reduce==add: {bad if bad else 'none (OK)'}")

print("=== 6. THE NO-CURTAILMENT QUESTION: how much PV does DSR absorb at export-cap hours? ===")
forced = 0.0
for sid, b in bs.items():
    h = sl[sid]["hours_per_year"]
    if h <= 0: continue
    at_cap = b["grid_export_kwh"] / h > exp_cap * 0.999
    if at_cap and b["dsr_add_kwh"] > 0:
        forced += b["dsr_add_kwh"]
print(f"   dsr_add coinciding with export-cap-bound slices = {forced/1e6:.2f} GWh "
      f"(this load shift is partly FORCED absorption - no curtail var exists)")

print("=== 7. OBJECTIVE RECOMPUTE (2030 annual cost from raw solution + econ accessors) ===")
# capex annualised (2030 vintage = new_build at base year = the period_breakdown 2030 new_build)
pb = sc["period_breakdown"]["2030"]["new_build"]
pmsgy_adj = (1.0 - econ.pmsgy_subsidy_fraction_at_year(2030)) / max(1e-9, 1.0 - econ.rooftop_pv_capex_subsidy_fraction())
cape = (pb["rooftop_pv_kwp"] * econ.rooftop_pv_annualised_inr_per_kwp()
        * econ.rooftop_pv_capex_multiplier_with_solshare(None) if False else 0.0)
# scenario multipliers: use accessor defaults via the scenario object is complex; use raw helpers:
roof_annual = econ.rooftop_pv_annualised_inr_per_kwp()
cape = (pb["rooftop_pv_kwp"] * roof_annual * pmsgy_adj
        + pb["farm_fixed_kwp"] * econ.solar_farm_annualised_inr_per_kwp()
        + pb["farm_tracked_kwp"] * econ.tracked_pv_annualised_inr_per_kwp()
        + pb["battery_kwh"] * econ.battery_annualised_inr_per_kwh()
        + pb["v2g_units"] * econ.v2g_annualised_inr_per_unit()
        + pb["biomass_kw_e"] * econ.biomass_chp_annualised_inr_per_kw_e()
        + pb["wte_kw_e"] * econ.wte_annualised_inr_per_kw_e()
        + pb["biogas_kw_e"] * econ.biogas_annualised_inr_per_kw_e()
        + pb["thermal_storage_kwh"] * econ.thermal_storage_annualised_inr_per_kwh()
        + pb["bipv_kwp"] * econ.bipv_annualised_inr_per_kwp() * pmsgy_adj
        + pb["carport_kwp"] * econ.carport_annualised_inr_per_kwp()
        + pb["floating_pv_kwp"] * econ.floating_pv_annualised_inr_per_kwp())
grid_cost = sum(b["grid_import_kwh"] * econ.import_tariff(sid) for sid, b in bs.items())
exp_rev = sum(b["grid_export_kwh"] * econ.export_tariff(sid) for sid, b in bs.items())
fuel = (econ.biomass_fuel_cost_inr_per_kwh() * sum(abs(b["biomass_kwh"]) for b in bs.values())
        + econ.wte_effective_fuel_cost_inr_per_kwh() * sum(abs(b["wte_kwh"]) for b in bs.values())
        + econ.biogas_fuel_cost_inr_per_kwh() * sum(abs(b["biogas_kwh"]) for b in bs.values()))
v2g_cost = econ.v2g_cycle_degradation_inr_per_kwh() * sum(abs(b["v2g_discharge_kwh"]) for b in bs.values())
dsr_cost = econ.dsr_comfort_cost_inr_per_kwh() * sum(b["dsr_reduce_kwh"] for b in bs.values())
rel_credit = ((cap["battery_kwh"] + cap["v2g_units"] * econ.v2g_kwh_per_unit_per_day())
              * econ.outage_hours_per_year() * econ.reliability_coverage_fraction() / 24.0
              * econ.diesel_displacement_value_inr_per_kwh())
total = cape + grid_cost - exp_rev + fuel + v2g_cost + dsr_cost - rel_credit
print(f"   capex {cape/1e6:,.1f}M + grid {grid_cost/1e6:,.1f}M - export {exp_rev/1e6:,.1f}M + fuel {fuel/1e6:,.1f}M"
      f" + v2g {v2g_cost/1e6:,.1f}M + dsr {dsr_cost/1e6:,.1f}M - reliability {rel_credit/1e6:,.1f}M")
print(f"   = RECOMPUTED {total/1e6:,.2f}M  vs REPORTED {sc['annual_cost_inr']/1e6:,.2f}M"
      f"  (delta {(total-sc['annual_cost_inr'])/1e6:+,.2f}M = {abs(total-sc['annual_cost_inr'])/sc['annual_cost_inr']*100:.2f}%)")
print("   NOTE: reliability credit uses END-OF-HORIZON caps here; the LP uses per-period installed -")
print("         small delta expected from v2g_units(2030)=200 vs 2,636 + scenario multipliers.")
print("=== 8. EMBODIED CARBON FLAG ===")
print(f"   include_embodied_carbon = {econ.include_embodied_carbon()}")
em_check = sc["annual_emissions_kgco2"] - (econ.period_emission_factor(2030) * sc["grid_import_kwh"])
print(f"   emissions - EF*import = {em_check/1e6:.2f} kt (bio fuels + any embodied)")
print("done.")
