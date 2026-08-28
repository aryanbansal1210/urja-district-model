"""Reproduce the demand headline numbers and the PSPCL seasonality validation.

Written, after the parameter audit took district demand from
910.60 to 559.33 GWh/yr. Every number this prints was, until now, prose in
`_spec/FINDINGS.md`, `_spec/PARAM_AUDIT_2026_08_06.md` and
`_spec/LOGBOOK.md` with no script that regenerated it. A viva examiner asking
"show me" had nothing to be shown, and the next re-pin would have had no way to
tell a legitimate move from a regression.

WHAT IT CHECKS

1. District annual demand, per capita, and residential kWh per household.
2. The **PSPCL seasonality validation**, which is the model's one
   out-of-sample test against a state utility's published data:

       H1 (April-September) residential energy
       ---------------------------------------  vs  PSPCL domestic 1.708
       H2 (October-March)   residential energy

   Source: PSERC, Tariff Order FY 2023-24 for PSPCL, Table 69 p.84,
   "Category-wise metered energy sales projected by PSPCL for FY 2022-23"
   (MkWh). Domestic H1 10,561 / H2 6,184 = 1.708. The half definitions are on
   p.82: H1 is April to September, H2 is October to March. Tier 1.
   https://pspcl.in/pdfs/currenttariff/sesalesto2023052610211318601062023.pdf

WHY THE RATIO IS EVIDENCE AND NOT A FIT. No input in the chain was set from
this ratio. Cooling equivalent full-load hours came from the Prayas eMARC
double difference; the base load came from eMARC's measured WINTER whole-house
consumption, chosen because winter is the season least contaminated by
cooling. A single scale factor (0.544 on non-cooling residential) was available
that would have hit 1.708 exactly, and was deliberately not used. If a future
change makes this script's ratio drift, that is a real signal about the
seasonal decomposition, not a target to re-tune toward.

CAVEATS, which the print-out repeats so they travel with the number:
  - PSPCL domestic is all of Punjab including rural; our town is entirely
    urban with higher AC penetration, which pushes our ratio ABOVE PSPCL's.
    Landing below is the conservative side.
  - Punjab's 300 units/month domestic subsidy distorts measured consumption in
    ways this comparison cannot separate.
  - Ours is 2030 design demand; PSPCL's is FY2022-23 actual.
  - It validates the seasonal DECOMPOSITION, not the absolute LEVEL. The level
    rests on eMARC measured household consumption, a separate claim.

Run:  python scripts/demand_validation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config              # noqa: E402
from energy.costs import load_economics          # noqa: E402
from energy.network import load_optimised_network  # noqa: E402

# PSERC Tariff Order FY 2023-24, Table 69 p.84 (Tier 1) - see module docstring.
PSPCL_DOMESTIC_H1_MKWH = 10_561.0
PSPCL_DOMESTIC_H2_MKWH = 6_184.0
PSPCL_DOMESTIC_RATIO = PSPCL_DOMESTIC_H1_MKWH / PSPCL_DOMESTIC_H2_MKWH  # 1.708

# TimeSlice.month is a 3-letter lowercase name ("jan"), not an int - the first
# version of this script used ints, matched nothing, and reported a zero H2.
# The coverage assertion below now makes that class of mistake fail loudly
# instead of silently returning a wrong ratio.
H1_MONTHS = ("apr", "may", "jun", "jul", "aug", "sep")   # per the order p.82
H2_MONTHS = ("oct", "nov", "dec", "jan", "feb", "mar")


def main() -> int:
    cfg = load_config()
    econ = load_economics()
    net = load_optimised_network(cfg=cfg, econ=econ)

    slices_by_id = {s.id: s for s in econ.slices}

    # ---- 1. levels ---------------------------------------------------
    annual_kwh = net.annual_demand_kwh(econ)
    households = net.total_households()
    population = (cfg.site or {}).get("total_population")

    print("=" * 68)
    print("DEMAND LEVELS")
    print("=" * 68)
    print(f"  layout                    {net.layout_name}")
    print(f"  district annual demand    {annual_kwh / 1e6:,.2f} GWh/yr")
    print(f"  households                {households:,}")
    if population:
        print(f"  design population         {population:,}")
        print(f"  per capita                {annual_kwh / population:,.0f} kWh/cap/yr")

    # ---- 2. residential split ----------------------------------------
    # Category names are read off the network rather than hard-coded, so a
    # renamed or added residential tier cannot silently drop out of the check.
    residential_cats = sorted({n.category_name for n in net.residential_nodes()
                               if n.category_name})
    if not residential_cats:
        print("\nNO RESIDENTIAL NODES - cannot run the seasonality check.")
        return 1

    comps_kw = net.demand_components_by_slice_kw(econ)

    missing = [c for c in residential_cats if c not in comps_kw]
    if missing:
        raise SystemExit(f"residential categories absent from components: {missing}")

    res_kwh_by_slice = {}
    for cat in residential_cats:
        for sid, kw in comps_kw[cat].items():
            res_kwh_by_slice[sid] = (res_kwh_by_slice.get(sid, 0.0)
                                     + kw * slices_by_id[sid].hours_per_year)

    res_annual = sum(res_kwh_by_slice.values())
    print(f"  residential total         {res_annual / 1e6:,.2f} GWh/yr "
          f"({100.0 * res_annual / annual_kwh:.1f}% of district)")
    if households:
        print(f"  residential per household {res_annual / households:,.0f} kWh/HH/yr")

    # ---- 3. the PSPCL seasonality validation -------------------------
    # Fail loudly if the month labels stop matching the halves: a silent
    # mismatch would report a plausible-looking ratio computed from a subset.
    seen_months = {slices_by_id[sid].month for sid in res_kwh_by_slice}
    unclassified = seen_months - set(H1_MONTHS) - set(H2_MONTHS)
    if unclassified:
        raise SystemExit(
            f"slice months not in either half: {sorted(unclassified)} - the "
            "H1/H2 definitions no longer match TimeSlice.month")
    if len(seen_months) != 12:
        raise SystemExit(f"expected 12 months, saw {len(seen_months)}: "
                         f"{sorted(seen_months)}")

    h1 = sum(kwh for sid, kwh in res_kwh_by_slice.items()
             if slices_by_id[sid].month in H1_MONTHS)
    h2 = sum(kwh for sid, kwh in res_kwh_by_slice.items()
             if slices_by_id[sid].month in H2_MONTHS)

    if h2 <= 0:
        raise SystemExit("H2 residential energy is zero - check the slice months")

    ratio = h1 / h2
    miss_pct = 100.0 * (ratio - PSPCL_DOMESTIC_RATIO) / PSPCL_DOMESTIC_RATIO

    print()
    print("=" * 68)
    print("PSPCL SEASONALITY VALIDATION (F46)")
    print("=" * 68)
    print(f"  {'':24s} {'H1 Apr-Sep':>14s} {'H2 Oct-Mar':>14s} {'ratio':>9s}")
    print(f"  {'our model, residential':24s} "
          f"{h1 / 1e6:>11,.2f} GWh {h2 / 1e6:>11,.2f} GWh {ratio:>9.3f}")
    print(f"  {'PSPCL domestic, actual':24s} "
          f"{PSPCL_DOMESTIC_H1_MKWH:>10,.0f} MkWh {PSPCL_DOMESTIC_H2_MKWH:>10,.0f} MkWh "
          f"{PSPCL_DOMESTIC_RATIO:>9.3f}")
    print(f"  {'miss':24s} {'':14s} {'':14s} {miss_pct:>8.1f}%")
    print()
    print("  Source: PSERC Tariff Order FY 2023-24 for PSPCL, Table 69 p.84")
    print("  (halves defined p.82). Tier 1.")
    print("  https://pspcl.in/pdfs/currenttariff/"
          "sesalesto2023052610211318601062023.pdf")
    print()
    print("  Caveats that travel with this number:")
    # restatement): this caveat used to end "so landing below is
    # the conservative side", which was written when the model sat at 1.700,
    # BELOW PSPCL's 1.708. After/B1c-rev/B1d/B1f/C9 the model is at 1.773,
    # ABOVE it - so the old sentence asserted the opposite of what the line above
    # it now prints. The PREDICTION was always "we should sit above"; we now do.
    print("   - PSPCL domestic is all-Punjab incl. rural; our town is urban with")
    print("     higher AC penetration, which should push our ratio ABOVE theirs.")
    print("     It does. This caveat was written as a PREDICTION while the model")
    print("     still sat below 1.708, so landing above is the outcome it")
    print("     forecast, not an excuse constructed afterwards (F46).")
    print("   - Punjab's 300 units/month domestic subsidy distorts the measured")
    print("     side in ways this comparison cannot separate.")
    print("   - Ours is 2030 design demand; PSPCL's is FY2022-23 actual.")
    print("   - Validates the seasonal DECOMPOSITION, not the absolute LEVEL.")
    print()

    # Not a pass/fail gate: the ratio is emergent and must stay emergent. A
    # widening miss is a signal to investigate the decomposition, never a
    # licence to re-tune toward 1.708.
    if abs(miss_pct) > 10.0:
        print(f"  NOTE: the miss has widened past 10% ({miss_pct:+.1f}%).")
        print("  INVESTIGATE the seasonal decomposition. Do NOT scale demand to")
        print("  close the gap - that would convert a validation into a fit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
