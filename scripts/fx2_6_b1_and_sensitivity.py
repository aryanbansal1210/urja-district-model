"""FX-2..6 follow-ups: B1 battery 2030 entry-price sweep + demand +/-20% sensitivity.

Two diagnostics on the FX-2..6 production baseline (clone-econ / clone-network,
production files NEVER written):

  (A) B1 SWEEP - sweep `technologies.li_ion_battery.capex_inr_per_kwh` DOWN from the
      base 9,000, re-solve full_stack alpha=0 multi-period at each, and report the
      battery installed per period (2030/2042/2055). At the FX-2..6 baseline the
      battery enters at 2055 ONLY evolution); this finds the 2030-entry capex
      ("storage economic in 2030 at Rs X/kWh"). The per-vintage real decline
      (capex_real_decline_per_year 0.030) still applies on top, so lowering the 2030
      base lowers every vintage proportionally.

  (B) DEMAND +/-20% SENSITIVITY (FX-3 deliverable) - scale every node's base/cooling/
      heating peak by 0.8 / 1.0 / 1.2 (PV roof + solar-farm capacity untouched), re-solve,
      and report cost/emissions so the absolute FX-3 figures carry an uncertainty band.
      This is a pure DEMAND shock (supply side held fixed).

Run: python scripts/fx2_6_b1_and_sensitivity.py
Writes: outputs/data/energy/fx2_6_b1_sweep.{csv,md} + fx2_6_demand_sensitivity.{csv,md}
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys, time
from copy import deepcopy

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); os.chdir(ROOT)
from core.demographics import load_demographics
from energy.costs import load_economics
from energy.network import load_optimised_network
from energy.dispatch import solve_dispatch

OUT = os.path.join(ROOT, "outputs", "data", "energy")
NET = load_optimised_network()
# (A4 session): per-capita divisor was hardcoded 100000 - the
# pre- town. Use the design demographics (250k at register 0f) so the
# kWh/cap column survives re-scales.
POP = load_demographics().total_population
BASE_CAPEX = 9000.0
CAPEX_POINTS = [9000, 7000, 6000, 5000, 4000, 3000, 2000]  # Rs/kWh 2030 base
DEMAND_FACTORS = [0.8, 1.0, 1.2]


def _battery_by_period(r):
    """Return {year: battery_kwh_installed} from the period breakdown."""
    pb = getattr(r, "period_breakdown", {}) or {}
    out = {}
    for y, d in pb.items():
        ic = d.get("installed_capacities", {}) or {}
        out[int(y)] = float(ic.get("battery_kwh", 0.0) or 0.0)
    return out


# ---------------------------------------------------------------------------
# (A) B1 battery 2030 entry-price sweep
# ---------------------------------------------------------------------------
def b1_sweep():
    print("=== B1 BATTERY 2030 ENTRY-PRICE SWEEP (full_stack a=0, multi-period) ===", flush=True)
    rows = []
    for capex in CAPEX_POINTS:
        t = time.time()
        e = deepcopy(load_economics(force_reload=True))
        e.technologies["li_ion_battery"]["capex_inr_per_kwh"] = float(capex)
        r = solve_dispatch(NET, e, "full_stack", alpha=0.0)
        bat = _battery_by_period(r)
        b2030 = bat.get(2030, 0.0); b2042 = bat.get(2042, 0.0); b2055 = bat.get(2055, 0.0)
        rows.append({
            "capex_2030_inr_per_kwh": capex,
            "battery_2030_kwh": round(b2030, 1),
            "battery_2042_kwh": round(b2042, 1),
            "battery_2055_kwh": round(b2055, 1),
            "annual_cost_inr": round(r.annual_cost_inr, 2),
            "annual_emissions_kgco2": round(r.annual_emissions_kgco2, 2),
            "lifetime_cost_inr": round(r.lifetime_cost_inr, 0),
        })
        print(f"  capex {capex:>5.0f}: 2030 {b2030/1e3:7.1f} MWh | 2042 {b2042/1e3:7.1f} | "
              f"2055 {b2055/1e3:7.1f} | cost {r.annual_cost_inr/1e6:,.1f} M ({time.time()-t:.0f}s)",
              flush=True)
    # find entry capex per period (highest capex at which that period's battery > 1 kWh)
    def entry(period_key):
        hits = [row["capex_2030_inr_per_kwh"] for row in rows if row[period_key] > 1.0]
        return max(hits) if hits else None
    e2030 = entry("battery_2030_kwh"); e2042 = entry("battery_2042_kwh"); e2055 = entry("battery_2055_kwh")
    with open(os.path.join(OUT, "fx2_6_b1_sweep.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, "fx2_6_b1_sweep.md"), "w", encoding="utf-8") as f:
        f.write("# B1 - battery 2030 entry-price sweep (production baseline, full_stack a=0)\n\n")
        f.write(f"Base 2030 capex Rs {BASE_CAPEX:,.0f}/kWh; per-vintage real decline 3.0%/yr applies on top.\n\n")
        f.write("| 2030 capex Rs/kWh | battery 2030 MWh | 2042 MWh | 2055 MWh | cost M/yr | emis kt |\n")
        f.write("|---:|---:|---:|---:|---:|---:|\n")
        for row in rows:
            f.write(f"| {row['capex_2030_inr_per_kwh']:,.0f} | {row['battery_2030_kwh']/1e3:.1f} | "
                    f"{row['battery_2042_kwh']/1e3:.1f} | {row['battery_2055_kwh']/1e3:.1f} | "
                    f"{row['annual_cost_inr']/1e6:,.1f} | {row['annual_emissions_kgco2']/1e6:.2f} |\n")
        f.write(f"\n**Entry capex (highest 2030-base Rs/kWh at which the period builds battery):**\n")
        f.write(f"- 2030 period: {('Rs %.0f/kWh' % e2030) if e2030 else 'none in sweep range'}\n")
        f.write(f"- 2042 period: {('Rs %.0f/kWh' % e2042) if e2042 else 'none in sweep range'}\n")
        f.write(f"- 2055 period: {('Rs %.0f/kWh' % e2055) if e2055 else 'none in sweep range'}\n")
    print(f"  -> 2030-entry capex: {e2030}; 2042-entry: {e2042}; 2055-entry: {e2055}", flush=True)
    print(f"  wrote fx2_6_b1_sweep.csv/.md", flush=True)
    return rows, (e2030, e2042, e2055)


# ---------------------------------------------------------------------------
# (B) demand +/-20% sensitivity
# ---------------------------------------------------------------------------
def _scaled_network(factor):
    """Deepcopy NET and scale every node's demand peaks by `factor` (supply held)."""
    net = deepcopy(NET)
    # clear any cached demand so the scaled peaks take effect
    for attr in ("_demand_kwh_cache", "_demand_kw_cache"):
        if hasattr(net, attr):
            getattr(net, attr).clear()
    new_nodes = []
    for n in net.nodes:
        n2 = dataclasses.replace(
            n,
            peak_base_kw=n.peak_base_kw * factor,
            peak_cooling_kw=n.peak_cooling_kw * factor,
            peak_heating_kw=n.peak_heating_kw * factor,
        )
        new_nodes.append(n2)
    net.nodes = new_nodes
    return net


def demand_sensitivity():
    print("\n=== DEMAND +/-20% SENSITIVITY (full_stack a=0, multi-period) ===", flush=True)
    rows = []
    for f in DEMAND_FACTORS:
        t = time.time()
        net = _scaled_network(f)
        e = deepcopy(load_economics(force_reload=True))
        r = solve_dispatch(net, e, "full_stack", alpha=0.0)
        dem = net.annual_demand_kwh(e)
        rows.append({
            "demand_factor": f,
            "annual_demand_gwh": round(dem / 1e6, 1),
            "kwh_per_cap": round(dem / POP, 0),
            "annual_cost_inr": round(r.annual_cost_inr, 2),
            "annual_emissions_kgco2": round(r.annual_emissions_kgco2, 2),
            "lifetime_cost_inr": round(r.lifetime_cost_inr, 0),
            "net_cost_inr_per_kwh": round(r.lcoe_inr_per_kwh(), 3),
            "renewable_share": round(r.renewable_share(), 4),
        })
        print(f"  x{f:.1f}: demand {dem/1e6:6.1f} GWh | cost {r.annual_cost_inr/1e6:,.1f} M | "
              f"emis {r.annual_emissions_kgco2/1e6:.2f} kt ({time.time()-t:.0f}s)", flush=True)
    with open(os.path.join(OUT, "fx2_6_demand_sensitivity.csv"), "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    base = next(r for r in rows if r["demand_factor"] == 1.0)
    with open(os.path.join(OUT, "fx2_6_demand_sensitivity.md"), "w", encoding="utf-8") as fo:
        fo.write("# Demand +/-20% sensitivity (FX-3 deliverable, full_stack a=0)\n\n")
        fo.write("Pure demand shock: node base/cooling/heating peaks scaled; PV/solar-farm capacity held.\n\n")
        fo.write("| demand factor | GWh | kWh/cap | cost M/yr | d cost | emis kt | d emis | net Rs/kWh | renew % |\n")
        fo.write("|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for r in rows:
            dc = (r["annual_cost_inr"] / base["annual_cost_inr"] - 1) * 100
            de = (r["annual_emissions_kgco2"] / base["annual_emissions_kgco2"] - 1) * 100
            fo.write(f"| {r['demand_factor']:.1f} | {r['annual_demand_gwh']:,.1f} | {r['kwh_per_cap']:,.0f} | "
                     f"{r['annual_cost_inr']/1e6:,.1f} | {dc:+.1f}% | {r['annual_emissions_kgco2']/1e6:.2f} | "
                     f"{de:+.1f}% | {r['net_cost_inr_per_kwh']:.3f} | {r['renewable_share']*100:.1f} |\n")
    print(f"  wrote fx2_6_demand_sensitivity.csv/.md", flush=True)
    return rows


if __name__ == "__main__":
    t0 = time.time()
    b1_sweep()
    demand_sensitivity()
    print(f"\nDONE in {time.time()-t0:.0f}s", flush=True)
