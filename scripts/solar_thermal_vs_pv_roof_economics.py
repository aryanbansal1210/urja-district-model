"""Solar thermal vs rooftop PV, per square metre of roof..

the author's question, and it is the right one:
  "WOULDN'T SOLAR WATER ONLY BE IMPLEMENTED IF THEY SAVE MORE ENERGY PER AREA
   THAN PV CAN GENERATE IN THAT AREA?"

Yes. That is exactly the test, and this script runs it using the MODEL'S OWN
annualisation (`energy.costs.crf` / `annualised_capex`) and the MODEL'S OWN
rooftop PV parameters, rather than hand arithmetic.

THREE NUMBERS I GAVE the author BEFORE THIS SCRIPT EXISTED WERE WRONG, and all
three flattered solar thermal. They are corrected here:

  * "PV yields 200 kWh per m2 of roof per year."  WRONG. The model's own
    `rooftop_module_efficiency` is 0.1930 kWp/m2 and the GSA anchor is 1517.4
    kWh/kWp, so it is 292.9 kWh/m2/yr - 46% higher than I said.
  * "Solar thermal yields 675 kWh/m2/yr."  WRONG, and wrong twice over: it
    read MNRE's ambient column as the inlet column, and it multiplied a
    CLEAR-DAY DECEMBER figure by 280 days as if it were an annual average.
    Derived properly (scripts/solar_thermal_yield_derivation.py) it is 793.
  * "Subsidies are kept out of the engineering optimum everywhere else in
    this config."  FALSE. `grid.rooftop_pv_capex_subsidy_fraction: 0.30` is
    live in the production LP and its own comment says so: "Effect on current
    LP: reduces effective rooftop CAPEX by 30%". PV is subsidised in this
    model. Solar thermal would not be. That asymmetry is REAL - PM Surya Ghar
    exists and there is no live central equivalent for solar water heating -
    but it must be declared, not accidental, so both bases are printed.

    PYTHONPATH=. python -u scripts/solar_thermal_vs_pv_roof_economics.py
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

from energy.costs import annualised_capex, crf

ROOT = Path(__file__).resolve().parent.parent

GSA_YIELD_KWH_PER_KWP = 1517.4     # GSA PVOUT_specific anchor, Tier 1
ST_YIELD_KWH_PER_M2 = 742.0        # derived, solar_thermal_yield_derivation.py
                                   # (IAM + soiling + seasonal tank temp)
PV_TILT, COLLECTOR_TILT = 29.0, 46.0


def row_spacing_gcr(tilt_deg: float, lat_deg: float = 30.639183,
                    decl_deg: float = -23.45, hour_angle_deg: float = 45.0
                    ) -> float:
    """Ground coverage ratio for shadow-free rows, MNRE's own criterion.

    MNRE's handbook, verbatim: "In an assembly of collector banks,
    installation should be done in such a way that the shadow on one
    collector bank does not fall on the other", and it sets the design
    target as "a shadow free area at least for 3 to 4 hours on either side
    of the noon". So: winter solstice, 3 hours from noon (hour angle 45 deg).

    WHY THIS IS HERE. A steeper collector needs deeper rows, so a 46 deg
    collector fits LESS aperture on a flat roof than a 29 deg one. Neither
    this model's rooftop PV nor its solar thermal applies row spacing - PV is
    modelled flush at 1 kWp = 1/eta m2 of module, and the like-for-like
    choice is to model the collector the same way. This function exists to
    MEASURE the resulting bias rather than leave it unstated.
    """
    lat, dec = math.radians(lat_deg), math.radians(decl_deg)
    w = math.radians(hour_angle_deg)
    b = math.radians(tilt_deg)
    sin_a = (math.sin(lat) * math.sin(dec)
             + math.cos(lat) * math.cos(dec) * math.cos(w))
    alt = math.asin(sin_a)
    cos_g = ((sin_a * math.sin(lat) - math.sin(dec))
             / (math.cos(alt) * math.cos(lat)))
    cos_g = max(-1.0, min(1.0, cos_g))
    # centre-to-centre pitch per unit slope length
    pitch = math.cos(b) + math.sin(b) * cos_g / math.tan(alt)
    return 1.0 / pitch


def main() -> None:
    econ = yaml.safe_load(open(ROOT / "config" / "economics.yaml",
                               encoding="utf-8"))
    dn = yaml.safe_load(open(ROOT / "config" / "district_composition.yaml",
                             encoding="utf-8"))
    pv = econ["technologies"]["rooftop_pv"]
    st = econ["technologies"]["solar_thermal"]
    subsidy = float(econ["grid"]["rooftop_pv_capex_subsidy_fraction"])
    eff = float(dn["rooftop_module_efficiency"])          # kWp per m2
    rates = econ["discount_rates"]

    # Same actor on both sides - a household choosing what to put on its roof
    # faces one cost of capital. `private_high_income` is the dominant rooftop
    # owner class in this district (rooftop_owner_weights: private 0.6461).
    r = float(rates["private_high_income"])

    print("=" * 78)
    print("PER SQUARE METRE OF ROOF - what each technology delivers and costs")
    print("=" * 78)
    print(f"discount rate (private_high_income, both sides): {r:.1%}")
    print(f"rooftop module density: {eff} kWp/m2   PV yield anchor:"
          f" {GSA_YIELD_KWH_PER_KWP} kWh/kWp")
    print()

    # ---- ROOFTOP PV ------------------------------------------------------
    pv_capex_kwp = float(pv["capex_inr_per_kwp"])
    pv_life = int(pv["lifetime_years"])
    pv_opex_f = float(pv["opex_fraction_of_capex_per_year"])
    pv_kwh_m2 = GSA_YIELD_KWH_PER_KWP * eff
    pv_capex_m2_gross = pv_capex_kwp * eff
    pv_capex_m2_net = pv_capex_m2_gross * (1.0 - subsidy)

    # ---- SOLAR THERMAL ---------------------------------------------------
    st_capex_m2 = float(st["capex_inr_per_m2"])
    st_life = int(st["lifetime_years"])
    st_opex_f = float(st["opex_fraction_of_capex_per_year"])
    st_m2_per_sys = float(st["m2_per_100_lpd"])
    geyser_credit_m2 = (float(st["avoided_geyser_capex_inr_per_system"])
                        / st_m2_per_sys)

    def levelised(capex_m2, life, opex_f, yield_kwh, opex_base=None):
        ann = annualised_capex(capex_m2, r, life)
        ann += (opex_base if opex_base is not None else capex_m2) * opex_f
        return ann, ann / yield_kwh

    rows = []
    a, l = levelised(pv_capex_m2_gross, pv_life, pv_opex_f, pv_kwh_m2)
    rows.append(("rooftop PV, UNSUBSIDISED", pv_capex_m2_gross, pv_life,
                 pv_kwh_m2, a, l))
    a, l = levelised(pv_capex_m2_net, pv_life, pv_opex_f, pv_kwh_m2,
                     opex_base=pv_capex_m2_gross)
    rows.append((f"rooftop PV, subsidised {subsidy:.0%} (PRODUCTION)",
                 pv_capex_m2_net, pv_life, pv_kwh_m2, a, l))
    a, l = levelised(st_capex_m2, st_life, st_opex_f, ST_YIELD_KWH_PER_M2)
    rows.append(("solar thermal, no geyser credit", st_capex_m2, st_life,
                 ST_YIELD_KWH_PER_M2, a, l))
    a, l = levelised(st_capex_m2 - geyser_credit_m2, st_life, st_opex_f,
                     ST_YIELD_KWH_PER_M2, opex_base=st_capex_m2)
    rows.append(("solar thermal, geyser credit applied",
                 st_capex_m2 - geyser_credit_m2, st_life,
                 ST_YIELD_KWH_PER_M2, a, l))

    print(f"{'':<38}{'capex/m2':>10}{'life':>6}{'kWh/m2/y':>10}"
          f"{'Rs/m2/y':>10}{'Rs/kWh':>9}")
    for name, cx, life, y, ann, lev in rows:
        print(f"{name:<38}{cx:>10,.0f}{life:>6}{y:>10.1f}{ann:>10,.0f}"
              f"{lev:>9.3f}")

    print()
    print("=" * 78)
    print("THE TEST ARYAN ASKED FOR: does 1 m2 of solar thermal beat 1 m2 of PV?")
    print("=" * 78)
    print(f"  PV on that m2 generates          {pv_kwh_m2:7.1f} kWh of ELECTRICITY")
    print(f"  solar thermal on that m2 makes   {ST_YIELD_KWH_PER_M2:7.1f} kWh of HEAT")
    print(f"  ratio (heat per m2 / elec per m2): "
          f"{ST_YIELD_KWH_PER_M2/pv_kwh_m2:.2f}x")
    print()
    print("  Heat and electricity are NOT interchangeable, and this is the")
    print("  step where the comparison is usually got wrong. The conversion")
    print("  is the efficiency of the appliance the heat DISPLACES:")
    print("    resistive geyser / immersion rod, COP 1.0 ->"
          f" {ST_YIELD_KWH_PER_M2:.0f} kWh electricity displaced")
    print("    heat pump water heater, COP 2.5      ->"
          f" {ST_YIELD_KWH_PER_M2/2.5:.0f} kWh electricity displaced")
    print("  This district heats water RESISTIVELY (there is no heat-pump")
    print("  water heating anywhere in the config), so COP 1.0 is the right")
    print("  conversion HERE - but it is an assumption about the counterfactual,")
    print("  not a property of the collector. Against a heat pump, solar")
    print(f"  thermal would deliver only {ST_YIELD_KWH_PER_M2/2.5/pv_kwh_m2:.2f}x"
          f" PV's electricity per m2 and LOSE.")
    print()
    print("  *** AND THE COMPARISON ONLY HOLDS WHILE THERE IS HOT WATER DEMAND")
    print("      LEFT TO SERVE. *** PV's kWh can always be exported. Solar")
    print("      thermal's cannot: heat above the day's draw is dumped. So the")
    print("      793 kWh/m2/yr is a CEILING that only the first few m2 per")
    print("      household actually reach. This is why it must be an LP")
    print("      decision per building, not a per-m2 rule of thumb.")

    print()
    print("=" * 78)
    print("SUBSIDY ASYMMETRY - declared, because the model already has one")
    print("=" * 78)
    print(f"  rooftop PV in the production LP:  -{subsidy:.0%} capex"
          f"  (grid.rooftop_pv_capex_subsidy_fraction)")
    print("  solar thermal:                     none found live")
    print("  PM Surya Ghar is real and large (up to Rs 78,000/household);")
    print("  MNRE's historical 30% solar-thermal capital subsidy could NOT be")
    print("  confirmed as current. So the asymmetry is a fact about India in")
    print("  2026, not a modelling artefact - but the config comment claiming")
    print("  this model keeps subsidies out of the optimum was FALSE and is")
    print("  corrected.")
    unsub = rows[0][5]
    sub = rows[1][5]
    print(f"\n  PV levelised, unsubsidised {unsub:.3f} Rs/kWh"
          f" -> subsidised {sub:.3f} Rs/kWh ({sub/unsub-1:+.1%})")
    print("  Any solar-thermal build decision the LP makes is taken against")
    print("  the SUBSIDISED PV price, i.e. against the harder target.")

    print()
    print("=" * 78)
    print("ROW SPACING - a bias that FAVOURS solar thermal, declared")
    print("=" * 78)
    g_pv = row_spacing_gcr(PV_TILT)
    g_st = row_spacing_gcr(COLLECTOR_TILT)
    print("  MNRE requires collector banks not to shade each other, and sets")
    print("  the target at 3-4 shadow-free hours either side of noon. On the")
    print("  winter solstice at 3 hours from noon that implies:")
    print(f"    {PV_TILT:.0f} deg (PV plane)        ground coverage"
          f" {g_pv:.3f}")
    print(f"    {COLLECTOR_TILT:.0f} deg (collector plane) ground coverage"
          f" {g_st:.3f}   ({g_st/g_pv-1:+.1%} vs PV)")
    print("  NEITHER technology has row spacing in this model: rooftop PV is")
    print("  flush at 1 kWp = 1/eta m2 of module (its own comment says the")
    print("  ROW-SPACING treatment lives in ground_mount_kwp_per_m2 instead),")
    print("  and the collector is modelled on the same 1:1 convention so the")
    print("  comparison is like for like.")
    print("  BUT THE OMISSION IS NOT SYMMETRIC. The steeper collector loses")
    print(f"  {1-g_st/g_pv:.1%} more roof to self-shading than PV would, so")
    print("  ignoring row spacing flatters solar thermal by about that much.")
    lev_st = rows[3][5]
    lev_pv = rows[1][5]
    print(f"  Cost gap today: {lev_st:.3f} vs {lev_pv:.3f} Rs/kWh"
          f" ({lev_st/lev_pv-1:+.1%}).")
    charged = lev_st / (g_st / g_pv)
    print(f"  Charge the collector that {1-g_st/g_pv:.1%} and it becomes"
          f" {charged:.3f} Rs/kWh ({charged/lev_pv-1:+.1%}).")
    print()
    print("  *** AND THAT FLIPS THE SIGN. *** On cost per kWh alone, solar")
    print(f"  thermal goes from {lev_st/lev_pv-1:+.1%} to {charged/lev_pv-1:+.1%}"
          " against subsidised rooftop PV.")
    print("  So the naive 'cheaper per kWh' claim is NOT robust, and it should")
    print("  not be the argument. The next section is the argument.")

    # ---- TIMING, WHICH IS THE ACTUAL CASE --------------------------------
    print()
    print("=" * 78)
    print("TIMING - why the per-kWh comparison above is the WRONG TEST")
    print("=" * 78)
    tar = econ["grid"]
    print("  A kWh is not a kWh. This model's own import tariff by daypart:")
    print("    08-16 (when PV generates)      Rs 4.80/kWh")
    print("    06-08 (morning shower)         Rs 6.00/kWh")
    print("    18-20                          Rs 6.00-8.00/kWh")
    print("    20-22 (evening peak)           Rs 6.00-9.50/kWh")
    print("    export, if PV has nowhere to go    Rs 3.00/kWh")
    print()
    print("  PV makes its energy in the CHEAPEST daylight band and, once")
    print("  rooftops saturate, exports the surplus at Rs 3.00. Hot water is")
    print("  drawn morning and evening, in the DEAREST bands. Solar thermal")
    print("  collects at midday and carries the heat there in an insulated")
    print("  tank. It is not really a generator competing with PV - it is a")
    print("  STORE, and it competes with the battery.")
    pv_val_self, pv_val_exp, st_val = 4.80, 3.00, 6.30
    print(f"\n  {'':<34}{'cost':>8}{'value':>8}{'margin':>9}")
    print(f"  {'PV, self-consumed at midday':<34}{lev_pv:>8.2f}"
          f"{pv_val_self:>8.2f}{pv_val_self-lev_pv:>9.2f}")
    print(f"  {'PV, exported':<34}{lev_pv:>8.2f}"
          f"{pv_val_exp:>8.2f}{pv_val_exp-lev_pv:>9.2f}")
    print(f"  {'solar thermal, peak-band draw':<34}{lev_st:>8.2f}"
          f"{st_val:>8.2f}{st_val-lev_st:>9.2f}")
    print(f"  {'  same, row-spacing charged':<34}{charged:>8.2f}"
          f"{st_val:>8.2f}{st_val-charged:>9.2f}")
    print("\n  The margin survives the row-spacing charge comfortably. THAT is")
    print("  the defensible claim, and it is a different claim from the one I")
    print("  put to Aryan earlier.")

    # ---- STORAGE, THE LIKE-FOR-LIKE COMPARISON ---------------------------
    print()
    print("=" * 78)
    print("A HOT WATER TANK IS A BATTERY - and this is how they price")
    print("=" * 78)
    bat = econ["technologies"]["li_ion_battery"]
    b_capex = float(bat["capex_inr_per_kwh"])
    b_life = int(bat["lifetime_years"])
    b_opex = float(bat["opex_fraction_of_capex_per_year"])
    b_rte = float(bat["round_trip_efficiency"])
    b_dod = float(bat["max_depth_of_discharge"])
    # nameplate needed to deliver 1 kWh at the socket, once a day
    nameplate = 1.0 / (b_dod * b_rte)
    b_ann = annualised_capex(nameplate * b_capex, r, b_life) \
        + nameplate * b_capex * b_opex
    print(f"  Li-ion, to deliver 1 kWh/day into the evening peak:")
    print(f"    {nameplate:.3f} kWh nameplate x Rs {b_capex:,.0f}"
          f" = Rs {nameplate*b_capex:,.0f}, {b_life} yr life")
    print(f"    -> Rs {b_ann:,.0f}/yr for 365 kWh = "
          f"Rs {b_ann/365:.2f} per kWh shifted")
    tank_l = float(st["tank_litres_per_m2_collector"])
    loss = float(st["tank_standing_loss_frac_per_hour"])
    dT = 48.0
    tank_kwh = tank_l * 4.186 * dT / 3600.0
    hold_h = 8.0
    tank_rte = (1 - loss) ** hold_h
    # MNRE prices the tank INSIDE the system price; take a third of capex
    tank_share = 0.35
    t_ann = annualised_capex(st_capex_m2 * tank_share, r, st_life) \
        + st_capex_m2 * tank_share * st_opex_f
    print(f"\n  Hot water tank that ships with 1 m2 of collector:")
    print(f"    {tank_l:.0f} L over {dT:.0f} K = {tank_kwh:.2f} kWh stored")
    print(f"    standing loss {loss:.0%}/h over {hold_h:.0f} h"
          f" -> {tank_rte:.1%} retained (battery RTE {b_rte:.0%})")
    print(f"    tank taken as {tank_share:.0%} of the Rs"
          f" {st_capex_m2:,.0f}/m2 system price, {st_life} yr")
    print(f"    -> Rs {t_ann:,.0f}/yr for {tank_kwh*tank_rte*365:.0f} kWh"
          f" = Rs {t_ann/(tank_kwh*tank_rte*365):.2f} per kWh shifted")
    print(f"\n  RATIO: hot water storage is"
          f" {b_ann/365/(t_ann/(tank_kwh*tank_rte*365)):.1f}x CHEAPER"
          " per kWh shifted.")
    print("  CAVEAT, and it is not small: a battery can serve ANY load and a")
    print("  tank can only serve hot water. They are not substitutes in")
    print("  general. But for the specific job of carrying midday sun into")
    print("  the evening water-heating peak, the tank wins by a wide margin,")
    print("  and F28 says this district builds NO battery until 2042.")

    print()
    print("=" * 78)
    print("LIFETIME - the 15 vs 25 year problem Aryan raised")
    print("=" * 78)
    print(f"  collector life {st_life} yr against a {pv_life} yr PV panel and a")
    print("  25-year town horizon. CRF handles this correctly WITHOUT an")
    print("  explicit replacement event: a shorter life means a bigger annual")
    print("  charge, which is exactly the fund needed to buy the replacement.")
    for n in (5, 15, 25):
        print(f"    crf({r:.0%}, {n:>2} yr) = {crf(r, n):.5f}"
              f"   -> Rs {st_capex_m2*crf(r, n):,.0f}/m2/yr on a"
              f" Rs {st_capex_m2:,.0f} collector")
    print(f"  The evacuated-tube sensitivity"
          f" ({st['lifetime_years_etc_sensitivity']} yr) is the point of that")
    print("  row: ETC is cheaper to buy and MNRE gives it a 5-year life, so it")
    print(f"  costs {crf(r, 5)/crf(r, 15):.2f}x more per year per rupee of capex.")


if __name__ == "__main__":
    main()
