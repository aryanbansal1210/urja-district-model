"""Stage E - per-owner financial model (NPV / IRR / payback): "who actually saves money".

A PURE REPORT-LAYER. Reads the Phase-4 equity report
(`equity_report.json`, or a dict from `build_equity_report`) + the per-actor
discount rates, and computes the per-tier / per-owner ROOFTOP-INVESTMENT
economics. It runs NO LP and changes no production code, so the byte-exact
headline (1,402,369,939.69) is untouched. This is the Stage-E "financial model"
deliverable: does rooftop pay back, for whom, and how does the SOCIAL view
differ from the PRIVATE view (DEC-2)?

Per tier/owner:
  net_capex   = installed_kwp x rooftop_capex/kwp x (1 - PMSGY effective fraction)
  annual_ben  = savings_vs_bau (degraded by PV degradation/yr) - O&M
  NPV(r)      = -net_capex + sum_{t=1..life} annual_ben_t / (1+r)^t
  IRR         = r s.t. NPV(r) = 0   (bisection)
  payback     = first year cumulative (undiscounted) annual_ben >= net_capex

DEC-2: every tier is reported at BOTH the owner's discount rate AND the 5%
social-planner rate. EWS is gov-owned (council/RESCO), so it is reported from
TWO angles: the gov-investor cashflow (Rs 3/kWh revenue - grid cost - O&M) and
the tenant's pure benefit (bill saving, no CAPEX).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

# tier -> owner-financing actor (mirrors config rooftop_owner_actors; commercial
# /industrial -> private; public would be social_planner but is lumped in
# 'commercial_public' here -> use private as the conservative default).
_TIER_ACTOR = {
    "ews": "social_ews",
    "mid_residential": "rwa_pooled",
    "high_residential": "private_high_income",
    "industrial": "private_high_income",
    "commercial_public": "private_high_income",
}
_RESIDENTIAL = ("ews", "mid_residential", "high_residential")
SOCIAL_RATE = 0.05  # social-planner discount rate (DEC-2 social view)


def _npv(rate: float, net_capex: float, annual_ben: float, opex: float,
         degradation: float, years: int) -> float:
    total = -net_capex
    for t in range(1, years + 1):
        ben_t = annual_ben * (1.0 - degradation) ** (t - 1) - opex
        total += ben_t / (1.0 + rate) ** t
    return total


def _irr(net_capex: float, annual_ben: float, opex: float,
         degradation: float, years: int) -> Optional[float]:
    """Bisection IRR in [-0.9, 2.0]. None if it never crosses zero."""
    if net_capex <= 0:
        return None  # no investment (e.g. tenant) -> IRR undefined
    f = lambda r: _npv(r, net_capex, annual_ben, opex, degradation, years)
    lo, hi = -0.9, 2.0
    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        return None  # no sign change (always +ve -> IRR > 200%; always -ve -> none)
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        fmid = f(mid)
        if abs(fmid) < 1.0:
            return mid
        if flo * fmid < 0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return 0.5 * (lo + hi)


def _payback_years(net_capex: float, annual_ben: float, opex: float,
                   degradation: float, years: int) -> Optional[float]:
    if net_capex <= 0:
        return 0.0
    cum = 0.0
    for t in range(1, years + 1):
        cum += annual_ben * (1.0 - degradation) ** (t - 1) - opex
        if cum >= net_capex:
            # linear interpolation within the year
            prev = cum - (annual_ben * (1.0 - degradation) ** (t - 1) - opex)
            frac = (net_capex - prev) / max(1e-9, cum - prev)
            return (t - 1) + frac
    return None  # never pays back within `years`


def build_owner_finance(equity_report: Dict[str, object], econ) -> Dict[str, object]:
    """Compute per-tier / per-owner rooftop-investment NPV / IRR / payback."""
    by_class = equity_report["by_class"]
    pmsgy = (equity_report.get("pmsgy_attribution", {}) or {}).get("by_tier_f16", {}) or {}
    capex_kwp = float((equity_report.get("pmsgy_attribution", {}) or {})
                      .get("rooftop_capex_inr_per_kwp", 35000.0))
    rt = (getattr(econ, "technologies", {}) or {}).get("rooftop_pv", {}) or {}
    life = int(rt.get("lifetime_years", 25))
    deg = float(rt.get("degradation_per_year", 0.012))
    opex_frac = float(rt.get("opex_fraction_of_capex_per_year", 0.012))

    def _rate(actor: str) -> float:
        try:
            return float(econ.actor_discount_rate(actor))
        except Exception:
            return float((econ.discount_rates or {}).get(actor, 0.08))

    tiers: Dict[str, Dict[str, object]] = {}
    for cls, c in by_class.items():
        kwp = float(c.get("rooftop_installed_kwp", 0.0))
        if kwp <= 0:
            continue
        pmsgy_frac = float((pmsgy.get(cls, {}) or {}).get("effective_capex_subsidy_fraction", 0.0))
        gross_capex = kwp * capex_kwp
        net_capex = gross_capex * (1.0 - pmsgy_frac)
        opex = gross_capex * opex_frac
        actor = _TIER_ACTOR.get(cls, "private_high_income")
        owner_rate = _rate(actor)
        hh = float(c.get("households", 0.0))

        if cls == "ews":
            # Gov-investor cashflow: collects Rs 3/kWh from tenants, pays grid cost.
            annual_ben = float(c.get("social_tariff_bill", 0.0)) - float(c.get("gov_grid_cost", 0.0))
            resident_annual_saving = float(c.get("savings_vs_bau_inr", 0.0))
        else:
            # B20 FIX (,
            # must be wrong" - he was right): the investment benefit is the
            # ROOFTOP'S OWN CASHFLOW, not the tier's whole-district bill
            # savings. savings_vs_bau bundles the district system's benefits
            # (cheap farm/biomass supply, ToU design, cross-subsidies) and
            # crediting all of it against rooftop-only capex produced ~86%
            # IRR / 1.2-yr payback - ~3x any real Indian rooftop project.
            # Honest benefit = self-consumed kWh valued at the tier's AVOIDED
            # retail rate (their BAU rate: bau_bill / consumption) + the
            # tier's rooftop export + P2P sale revenue.
            cons = float(c.get("consumption_kwh", 0.0))
            bau_rate = (float(c.get("bau_bill_inr", 0.0)) / cons) if cons > 0 else 0.0
            annual_ben = (float(c.get("self_consumed_kwh", 0.0)) * bau_rate
                          + float(c.get("grid_export_revenue", 0.0))
                          + float(c.get("p2p_sell_revenue", 0.0)))
            resident_annual_saving = float(c.get("savings_vs_bau_inr", 0.0))

        npv_owner = _npv(owner_rate, net_capex, annual_ben, opex, deg, life)
        npv_social = _npv(SOCIAL_RATE, net_capex, annual_ben, opex, deg, life)
        irr = _irr(net_capex, annual_ben, opex, deg, life)
        payback = _payback_years(net_capex, annual_ben, opex, deg, life)

        tiers[cls] = {
            "owner_actor": actor,
            "owner_discount_rate": owner_rate,
            "installed_kwp": kwp,
            "pmsgy_subsidy_fraction": pmsgy_frac,
            "gross_capex_inr": gross_capex,
            "net_capex_inr": net_capex,
            "annual_benefit_inr": annual_ben,
            "annual_opex_inr": opex,
            "npv_owner_rate_inr": npv_owner,
            "npv_social_5pct_inr": npv_social,
            "irr": irr,
            "simple_payback_years": payback,
            "households": hh,
            "net_capex_per_household_inr": (net_capex / hh) if hh > 0 else None,
            "npv_owner_per_household_inr": (npv_owner / hh) if hh > 0 else None,
            "resident_annual_saving_inr": resident_annual_saving,
            "resident_lifetime_saving_inr": resident_annual_saving * life,
        }

    # district totals (owner-investment view)
    tot_net_capex = sum(t["net_capex_inr"] for t in tiers.values())
    tot_npv_owner = sum(t["npv_owner_rate_inr"] for t in tiers.values())
    tot_npv_social = sum(t["npv_social_5pct_inr"] for t in tiers.values())

    return {
        "meta": {
            "stage": "Stage E - per-owner financial model (NPV/IRR/payback)",
            "generated_by": "energy/owner_finance.py (Opus 4.8, 2026-06-03)",
            "method": "rooftop-investment NPV per owner; DEC-2 dual perspective (owner rate + 5% social)",
            "pv_lifetime_years": life,
            "pv_degradation_per_year": deg,
            "rooftop_capex_inr_per_kwp": capex_kwp,
            "tariff_escalation_real": 0.0,
            "byte_exact_note": "report-only; no LP; production headline unchanged",
            "caveats": ("commercial/industrial PMSGY = 0 (residential scheme; accel. depreciation not "
                        "modelled - conservative). 'commercial_public' financed at the private rate "
                        "(public-sub-split = refinement). EWS = gov-investor cashflow + tenant benefit."),
        },
        "by_tier": tiers,
        "district_totals": {
            "net_capex_inr": tot_net_capex,
            "npv_at_owner_rates_inr": tot_npv_owner,
            "npv_at_social_5pct_inr": tot_npv_social,
        },
    }


def _default_path() -> Path:
    return Path(__file__).parent.parent / "outputs" / "data" / "energy" / "owner_finance.json"


def write_owner_finance_json(report: Dict[str, object], path: Optional[Path] = None) -> Path:
    out = Path(path) if path is not None else _default_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return out


def _cr(x: float) -> str:
    return f"Rs {x/1e7:,.2f} cr"


def print_owner_finance_summary(rep: Dict[str, object]) -> None:
    print("\n" + "=" * 78)
    print("STAGE E - PER-OWNER ROOFTOP FINANCE (NPV / IRR / payback) - report-only")
    print("=" * 78)
    hdr = f"  {'tier':<18}{'rate':>6}{'netCAPEX':>12}{'NPV(owner)':>13}{'IRR':>7}{'payback':>9}"
    print(hdr)
    for cls, t in rep["by_tier"].items():
        irr = t["irr"]
        pb = t["simple_payback_years"]
        print(f"  {cls:<18}{t['owner_discount_rate']*100:>5.1f}%{_cr(t['net_capex_inr']):>12}"
              f"{_cr(t['npv_owner_rate_inr']):>13}"
              f"{(f'{irr*100:.0f}%' if irr is not None else 'n/a'):>7}"
              f"{(f'{pb:.1f}y' if pb is not None else '>life'):>9}")
    d = rep["district_totals"]
    print(f"\n  district net CAPEX {_cr(d['net_capex_inr'])} | NPV @ owner rates "
          f"{_cr(d['npv_at_owner_rates_inr'])} | NPV @ 5% social {_cr(d['npv_at_social_5pct_inr'])}")
    ews = rep["by_tier"].get("ews", {})
    if ews:
        print(f"\n  EWS (gov-owned): gov-investor NPV {_cr(ews['npv_owner_rate_inr'])} (gov bears the social cost); "
              f"tenant saving {_cr(ews['resident_annual_saving_inr'])}/yr, {_cr(ews['resident_lifetime_saving_inr'])} over {rep['meta']['pv_lifetime_years']}y (no CAPEX).")
    print("=" * 78)


def main() -> None:
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    sys.path.insert(0, root)
    os.chdir(root)
    from energy.costs import load_economics

    eq_path = Path(root) / "outputs" / "data" / "energy" / "equity_report.json"
    if not eq_path.exists():
        print(f"ERROR: {eq_path} not found - run energy/equity_report.py first.")
        sys.exit(1)
    equity_report = json.load(open(eq_path, encoding="utf-8"))
    econ = load_economics(force_reload=True)
    rep = build_owner_finance(equity_report, econ)
    out = write_owner_finance_json(rep)
    print_owner_finance_summary(rep)
    print(f"\n  -> wrote {out}")


if __name__ == "__main__":
    main()
