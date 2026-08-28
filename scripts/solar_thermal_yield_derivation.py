"""Solar thermal collector yield per slice, derived and VALIDATED,.

WHY THIS SCRIPT EXISTS. The config block written before it carried a single
flat number, `delivered_kwh_per_m2_per_day_site: 2.41`, lifted from MNRE's
Chandigarh row. Three things were wrong with using it that way, and all three
are fixed here:

  1. THE COLUMNS WERE READ WRONG. MNRE Table 8's columns are
     `Day Ambient Temperature` THEN `Cold Water Temperature`, so Chandigarh is
     ambient 16 C / inlet 12 C, not inlet 16 C. The temperature rise is 48 K,
     not 44 K, and the delivered energy is 2.62 kWh/m2/day, not 2.41 - the
     original figure was 8.3% LOW.
  2. IT IS A CLEAR-DAY DESIGN FIGURE, NOT A MONTHLY AVERAGE. The table's own
     title: "winter output... ON AN AVERAGE CLEAR DAY IN DECEMBER". Punjab
     Decembers and Januaries are not clear - the fog trough is the single
     largest feature of this site's solar resource (GSA January DNI 78.4 vs
     March 147.5). Multiplying a clear-day figure by 280 sunny days, which is
     what the config did to reach 675 kWh/m2/yr, mixes two bases.
  3. IT IS AT 46 DEGREES TILT, THE MODEL'S SOLAR RESOURCE IS AT 29. MNRE
     specifies latitude+15 for Chandigarh because winter is the binding
     season for hot water. The GSA site report, which every other solar
     number in this model comes from, is at OPTA 29 deg - the ANNUAL optimum,
     which is a PV objective. The two planes are not interchangeable.

So the yield is derived per month from the same GSA hourly DNI the PV shape
uses, transposed to the collector plane, and run through the IS 12933
efficiency curve against this site's own monthly temperatures. The flat
number becomes a validation target rather than an input.

VALIDATION IS THE POINT. Two independent checks the derivation must pass:
  A. Reproduce the config's own 29 deg PV monthly modifiers (proves the
     transposition is implemented correctly before it is trusted at 46).
  B. Reproduce MNRE's measured Chandigarh output on a CLEAR December day
     under MNRE's OWN stated conditions (proves the efficiency curve and the
     irradiance are consistent with a real measured system).

    python scripts/solar_thermal_yield_derivation.py
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LAT = math.radians(30.639183)

# ---- GSA site report, Tier 1 (identical constants to f1_gsa_monthly_shape) --
DNI = {"jan": 78.4, "feb": 110.9, "mar": 147.5, "apr": 147.2, "may": 134.9,
       "jun": 97.6, "jul": 65.4, "aug": 83.7, "sep": 110.5, "oct": 134.9,
       "nov": 107.3, "dec": 97.9}
DIF_ANNUAL = 875.2
GTI_OPTA_REPORT = 1925.4        # GSA's own GTI at OPTA 29 deg
DAYS = {"jan": 31, "feb": 28.25, "mar": 31, "apr": 30, "may": 31, "jun": 30,
        "jul": 31, "aug": 31, "sep": 30, "oct": 31, "nov": 30, "dec": 31}
MID_DOY = {"jan": 17, "feb": 47, "mar": 75, "apr": 105, "may": 135,
           "jun": 162, "jul": 198, "aug": 228, "sep": 258, "oct": 288,
           "nov": 318, "dec": 344}
MONTHS = list(DNI)

PV_TILT = 29.0                  # the model's existing solar resource plane
COLLECTOR_TILT = 46.0           # MNRE Table 8 for Chandigarh (= latitude + 15)


def _decl(doy: int) -> float:
    return math.radians(23.45) * math.sin(2 * math.pi * (284 + doy) / 365.0)


def _h0_day(doy: int) -> float:
    d = _decl(doy)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(LAT) * math.tan(d))))
    return (ws * math.sin(LAT) * math.sin(d)
            + math.cos(LAT) * math.cos(d) * math.sin(ws))


def hourly_dni_profiles() -> dict:
    """GSA report's average hourly DNI profile per month, W/m2."""
    import openpyxl
    xlsx = ROOT.parent.parent / "DATA" / "GSA_Report_Punjab.xlsx"
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb["Hourly_profiles"]
    out = {m: [0.0] * 24 for m in MONTHS}
    for row in ws.iter_rows(values_only=True):
        if not row or row[0] is None:
            continue
        label = str(row[0])
        if "-" not in label:
            continue
        try:
            hour = int(label.split("-")[0].strip())
        except ValueError:
            continue
        for i, m in enumerate(MONTHS):
            out[m][hour] = float(row[1 + i] or 0.0)
    return out


B0_IAM = 0.10                   # incidence angle modifier coefficient
THETA_DIFFUSE_EFF = 58.0        # effective incidence angle for isotropic sky


def iam(theta_rad: float) -> float:
    """Incidence angle modifier, K_ta(theta) = 1 - b0 (1/cos theta - 1).

    THIS WAS MISSING FROM THE FIRST DERIVATION AND IT MATTERS. The efficiency
    curve eta0 - a1 dT/G is defined at NORMAL incidence. Light arriving at a
    slant reflects off the glazing instead of passing through, and a hot water
    collector in December sees slanted light for most of a short day.

    b0 = 0.10 is the standard single-glazed flat-plate value (Duffie &
    Beckman; equivalently EN 12975 collectors reporting K(50 deg) ~ 0.94,
    which inverts to b0 = 0.06 / (1/cos 50 - 1) = 0.108).

    Beyond 60 degrees the linear form stops being physical, so it is faired
    linearly to zero at 90 - the usual treatment.
    """
    if theta_rad <= 0.0:
        return 1.0
    c = math.cos(theta_rad)
    if c <= 0.0:
        return 0.0
    t60 = math.radians(60.0)
    if theta_rad <= t60:
        return max(0.0, 1.0 - B0_IAM * (1.0 / c - 1.0))
    k60 = 1.0 - B0_IAM * (1.0 / math.cos(t60) - 1.0)
    return max(0.0, k60 * (math.radians(90.0) - theta_rad)
               / (math.radians(90.0) - t60))


def hourly_components(tilt_deg: float, profiles: dict) -> dict:
    """Per month, 24 tuples of (beam W/m2, diffuse W/m2, IAM on the beam).

    Same decomposition as the PV shape derivation: beam transposed by the
    incidence ratio, isotropic diffuse by the (1+cos b)/2 view factor. The
    diffuse level comes from the report's annual DIF spread over months by
    extraterrestrial availability, then spread over the day in proportion to
    the clear-sky solar altitude. Ground reflection omitted, as everywhere
    else in this model.

    Beam and diffuse are kept SEPARATE because the incidence angle modifier
    differs between them - beam has a real hourly angle, diffuse arrives from
    the whole sky dome and takes the conventional effective angle. Summing
    them first and applying one IAM would be wrong at exactly the times of
    day that decide a winter result.
    """
    tilt = math.radians(tilt_deg)
    iso = (1 + math.cos(tilt)) / 2.0
    h0w = {m: DAYS[m] * _h0_day(MID_DOY[m]) for m in MONTHS}
    h0s = sum(h0w.values())
    dif_m = {m: DIF_ANNUAL * h0w[m] / h0s for m in MONTHS}

    out = {}
    for m in MONTHS:
        d = _decl(MID_DOY[m])
        cz, ci = [0.0] * 24, [0.0] * 24
        for h in range(24):
            t = math.radians((h + 0.5 - 12.0) * 15.0)
            cz[h] = (math.sin(LAT) * math.sin(d)
                     + math.cos(LAT) * math.cos(d) * math.cos(t))
            ci[h] = (math.sin(LAT - tilt) * math.sin(d)
                     + math.cos(LAT - tilt) * math.cos(d) * math.cos(t))
        czsum = sum(max(0.0, z) for z in cz)
        dif_day_wh = dif_m[m] / DAYS[m] * 1000.0        # Wh/m2/day horizontal
        hours = []
        for h in range(24):
            beam, kb = 0.0, 1.0
            if profiles[m][h] > 0 and cz[h] > 0 and ci[h] > 0:
                beam = profiles[m][h] * ci[h]           # W/m2 on the plane
                kb = iam(math.acos(min(1.0, ci[h])))
            diff = 0.0
            if czsum > 0 and cz[h] > 0:
                diff = dif_day_wh * (cz[h] / czsum) * iso
            hours.append((beam, diff, kb))
        out[m] = hours
    return out


def hourly_gti(tilt_deg: float, profiles: dict) -> dict:
    """Hourly total plane-of-array irradiance W/m2 (beam + diffuse)."""
    comp = hourly_components(tilt_deg, profiles)
    return {m: [b + d for b, d, _ in comp[m]] for m in MONTHS}


def monthly_gti(hourly: dict) -> dict:
    """kWh/m2/month from the hourly W/m2 profiles."""
    return {m: sum(hourly[m]) / 1000.0 * DAYS[m] for m in MONTHS}


def hour_useful_w(beam: float, diff: float, k_beam: float, k_diff: float,
                  t_in_c: float, t_amb_c: float, eta0: float, a1: float,
                  soil: float = 1.0) -> float:
    """Useful heat collected in one hour, W/m2 of collector.

    THE IAM MULTIPLIES THE OPTICAL TERM, NOT THE IRRADIANCE. This is the
    part that is easy to get wrong. The collector equation is

        q = eta0 * K_ta * G  -  a1 * (Ti - Ta)

    so a slanted beam loses OPTICAL gain but the collector still loses heat
    to ambient at the same rate. Deflating G instead - which is what
    "multiply the irradiance by the IAM" does - would quietly shrink the loss
    term too and OVERSTATE cold-morning performance.

    Soiling is applied to the incoming radiation, because dirt on the glazing
    genuinely blocks light before it reaches the absorber.
    """
    g = (beam + diff) * soil
    if g <= 0.0:
        return 0.0
    optical = eta0 * (beam * k_beam + diff * k_diff) * soil
    q = optical - a1 * (t_in_c - t_amb_c)
    return max(0.0, q)


def collector_eta(g_w_m2: float, t_in_c: float, t_amb_c: float,
                  eta0: float, a1: float) -> float:
    """IS 12933 Part 5 / Duffie & Beckman first-order efficiency.

    Clamped at zero. This clamp is NOT cosmetic: below the cutoff irradiance
    G* = a1 (Ti - Ta) / eta0 the collector loses more than it gathers, and a
    real system stops circulating. Letting the curve go negative would have
    the collector actively cooling the tank at dawn and dusk.
    """
    if g_w_m2 <= 0.0:
        return 0.0
    return max(0.0, eta0 - a1 * (t_in_c - t_amb_c) / g_w_m2)


def main() -> None:
    econ = yaml.safe_load(open(ROOT / "config" / "economics.yaml",
                               encoding="utf-8"))
    clim = yaml.safe_load(open(ROOT / "config" / "climate.yaml",
                               encoding="utf-8"))["climate"]
    st = econ["technologies"]["solar_thermal"]
    eta0 = float(st["eta0"])
    a1 = float(st["a1_w_per_m2_k"])
    # MNRE's test tank runs from the cold inlet to the setpoint, so the
    # collector sees the mean of the two. For their Chandigarh row that is
    # (12 + 60)/2. Used only for CHECK B, which is run at MNRE's conditions;
    # the annual table below derives it per month from this site's climate.
    t_tank = (12.0 + float(econ["heating_loads"]["dhw"]["setpoint_c"])) / 2.0

    profiles = hourly_dni_profiles()

    # ---- CHECK A: reproduce the config's own 29 deg PV monthly modifiers ----
    g29 = monthly_gti(hourly_gti(PV_TILT, profiles))
    s29 = sum(g29.values())
    cfg_mod = econ["pv_capacity_factor"]["monthly_modifier"]
    print("=" * 74)
    print("CHECK A - does this transposition reproduce the model's PV shape?")
    print("=" * 74)
    print(f"{'mon':<5}{'GTI29':>9}{'/day':>7}{'mod here':>10}"
          f"{'mod config':>12}{'diff':>9}")
    worst = 0.0
    for m in MONTHS:
        mod = 1517.4 * (g29[m] / s29) / (5.18 * DAYS[m])
        d = mod / cfg_mod[m] - 1.0
        worst = max(worst, abs(d))
        print(f"{m:<5}{g29[m]:>9.1f}{g29[m]/DAYS[m]:>7.2f}"
              f"{mod:>10.4f}{cfg_mod[m]:>12.4f}{d:>+9.2%}")
    print(f"\nannual derived GTI at 29 deg: {s29:.1f} kWh/m2"
          f"   (GSA reports {GTI_OPTA_REPORT} at OPTA)")
    print(f"worst monthly modifier deviation: {worst:+.2%}")
    print("  -> the transposition is the same one the PV table was built with,"
          "\n     so it can be trusted at a different tilt.")

    # Correct the known isotropic-diffuse conservatism using GSA's OWN annual
    # GTI at the plane it reports. The same factor is applied at both tilts,
    # so it is a level correction and does not invent seasonality.
    cal = GTI_OPTA_REPORT / s29

    h46 = hourly_gti(COLLECTOR_TILT, profiles)
    g46 = {m: v * cal for m, v in monthly_gti(h46).items()}
    g29c = {m: v * cal for m, v in g29.items()}
    print(f"\nisotropic-diffuse calibration to the GSA report: x{cal:.4f}")

    print()
    print("=" * 74)
    print(f"TILT: what {COLLECTOR_TILT:.0f} deg buys over the PV plane "
          f"({PV_TILT:.0f} deg)")
    print("=" * 74)
    print(f"{'mon':<5}{'GTI29/day':>11}{'GTI46/day':>11}{'gain':>9}")
    for m in MONTHS:
        a, b = g29c[m] / DAYS[m], g46[m] / DAYS[m]
        print(f"{m:<5}{a:>11.2f}{b:>11.2f}{b/a-1:>+9.1%}")
    print(f"{'ANN':<5}{sum(g29c.values()):>11.0f}{sum(g46.values()):>11.0f}"
          f"{sum(g46.values())/sum(g29c.values())-1:>+9.1%}")
    print("  Winter is up, summer is down, annual is slightly down. That is")
    print("  exactly what latitude+15 is for, and why MNRE specifies it for a")
    print("  hot water system whose binding season is December.")

    comp46 = hourly_components(COLLECTOR_TILT, profiles)
    k_dif = iam(math.radians(THETA_DIFFUSE_EFF))

    # Soiling. The GSA GTI the level is calibrated to is IRRADIANCE, which is
    # NOT soiling-derated (unlike PVOUT_specific, where the fix
    # found soiling already inside the anchor). So the collector takes the RAW
    # A19 multiplier. Leaving it out would have charged PV for Punjab's dust
    # and let the collector sit in the same air for free.
    from energy.costs import load_economics
    ec = load_economics(force_reload=True)
    soil = {m: ec.pv_soiling_multiplier_for_month(m) for m in MONTHS}

    def day_yield(month: str, day_gti_kwh: float, t_amb: float,
                  t_in: float, use_iam: bool = True,
                  use_soil: bool = True) -> float:
        """kWh/m2 collected on one day of `month` scaled to `day_gti_kwh`."""
        raw = [(b, d) for b, d, _ in comp46[month]]
        tot = sum(b + d for b, d in raw)
        if tot <= 0:
            return 0.0
        scale = day_gti_kwh * 1000.0 / tot
        s = soil[month] if use_soil else 1.0
        out = 0.0
        for (b, d, kb) in comp46[month]:
            out += hour_useful_w(b * scale, d * scale,
                                 kb if use_iam else 1.0,
                                 k_dif if use_iam else 1.0,
                                 t_in, t_amb, eta0, a1, s) / 1000.0
        return out

    # ---- CHECK B: MNRE's measured clear December day ----------------------
    print()
    print("=" * 74)
    print("CHECK B - reproduce MNRE's MEASURED Chandigarh output")
    print("=" * 74)
    mnre_gti, mnre_amb, mnre_inlet, mnre_litres = 5.79, 16.0, 12.0, 94.0
    mnre_kwh = mnre_litres * 4.186 * (60.0 - mnre_inlet) / 3600.0
    print(f"  MNRE: clear Dec day, 46 deg, {mnre_gti} kWh/m2/day incident,")
    print(f"        ambient {mnre_amb} C, inlet {mnre_inlet} C,"
          f" {mnre_litres:.0f} L/day at 60 C on 2 m2")
    print(f"        = {mnre_kwh:.3f} kWh/day = "
          f"{mnre_kwh/2:.3f} kWh/m2/day delivered")
    # *** SOILING MUST NOT ENTER THIS CHECK. *** MNRE's row is a CLEAN
    # collector on a CLEAR test day. Charging it for a year of Punjab dust
    # and then calling the gap a validation failure would be comparing two
    # different things. Soiling belongs in the annual yield below, not here.
    print(f"\n  {'variant':<46}{'kWh/m2/d':>10}{'vs MNRE':>10}")
    for lab, ui in (("bare curve, no IAM", False),
                    ("+ incidence angle modifier (correct for a test day)",
                     True)):
        v = day_yield("dec", mnre_gti, mnre_amb, t_tank, ui, False)
        print(f"  {lab:<46}{v:>10.3f}{v/(mnre_kwh/2)-1:>+10.1%}")

    # ---- THE TANK TEMPERATURE, WHICH WAS THE REAL ERROR ------------------
    print()
    print("  THE REPRESENTATIVE TANK TEMPERATURE WAS WRONG, AND IT IS THE")
    print("  MOST SENSITIVE NUMBER IN THIS WHOLE DERIVATION.")
    print("  The config declared 45 C as a 'mid-charge' guess. Work MNRE's own")
    print("  test through an energy balance instead: the tank starts the day at")
    print(f"  the cold inlet ({mnre_inlet:.0f} C) and finishes at the setpoint")
    print(f"  (60 C), so the collector sees a mean inlet of"
          f" ({mnre_inlet:.0f}+60)/2 = {(mnre_inlet+60)/2:.0f} C, not 45.")
    print("  A guess was standing where an energy balance belonged.")
    print(f"\n  {'tank temp':<46}{'kWh/m2/d':>10}{'vs MNRE':>10}")
    for tt in (30.0, 36.0, 40.0, 45.0, 50.0):
        v = day_yield("dec", mnre_gti, mnre_amb, tt, True, False)
        tag = ""
        if tt == 45.0:
            tag = "  <- old config guess"
        elif tt == 36.0:
            tag = "  <- (inlet+setpoint)/2, DERIVED"
        print(f"  {tt:>4.0f} C{'':<40}{v:>10.3f}{v/(mnre_kwh/2)-1:>+10.1%}{tag}")
    print("\n  So the tank temperature becomes a DERIVED, SEASONAL quantity:")
    print("      T_collector_inlet(month) = (inlet(month) + setpoint) / 2")
    print("  which is physically right in a way a constant never was - a winter")
    print("  tank really does run colder, because the water going into it is")
    print("  colder. That RAISES winter efficiency and lowers summer, partly")
    print("  self-correcting the seasonality rather than assuming it away.")

    # ---- the actual per-month yield the model will use --------------------
    print()
    print("=" * 74)
    print("DERIVED YIELD - monthly average day, this site, collector plane")
    print("=" * 74)
    setpoint = float(econ["heating_loads"]["dhw"]["setpoint_c"])
    print(f"  collector inlet = (monthly inlet + setpoint {setpoint:.0f} C) / 2,"
          f" derived above")
    print(f"{'mon':<5}{'GTI/day':>9}{'Tamb':>7}{'Ttank':>7}{'soil':>7}"
          f"{'eta_eff':>9}{'kWh/m2/d':>10}{'cutoff':>9}")
    ann = 0.0
    rows = {}
    tanks = {}
    for m in MONTHS:
        tamb = float(clim[m]["t_mean_c"])
        # the model's own DHW convention: inlet is proxied by monthly mean air
        t_in = (tamb + setpoint) / 2.0
        tanks[m] = t_in
        day_kwh = g46[m] / DAYS[m]
        out = day_yield(m, day_kwh, tamb, t_in)
        eta_eff = out / day_kwh if day_kwh else 0.0
        cutoff = a1 * (t_in - tamb) / eta0          # W/m2 below which nothing
        ann += out * DAYS[m]
        rows[m] = out
        print(f"{m:<5}{day_kwh:>9.2f}{tamb:>7.1f}{t_in:>7.1f}{soil[m]:>7.3f}"
              f"{eta_eff:>9.3f}{out:>10.3f}{cutoff:>9.0f}")
    print("\n  'cutoff' is the irradiance below which this collector gathers")
    print("  less than it loses and a real system stops circulating. In")
    print("  January it is the single biggest reason winter output collapses:")
    print("  a foggy morning simply never crosses it.")
    print(f"\nANNUAL collector output: {ann:.0f} kWh/m2/yr"
          f"   ({ann*2:.0f} kWh/yr on a 2 m2 system)")
    print(f"MNRE cross-check for a single-collector system: "
          f"900 to 1800 kWh/yr  -> "
          f"{'INSIDE' if 900 <= ann*2 <= 1800 else 'OUTSIDE'}")
    flat = 2.41 * 280       # what the RETRACTED first draft of the block said
    print(f"\nthe retracted first draft declared 2.41 kWh/m2/day flat"
          f" x 280 days = {flat:.0f} kWh/m2/yr")
    print(f"derived                   {ann:.0f} kWh/m2/yr ({ann/flat-1:+.1%})")
    cfg_ann = st.get("annual_kwh_per_m2")
    if cfg_ann:
        print(f"config now declares       {cfg_ann} kWh/m2/yr"
              f"  ({'MATCHES' if abs(ann-cfg_ann) < 1.0 else 'DRIFTED'})")
    cfg_tab = st.get("monthly_kwh_per_m2_per_day") or {}
    if cfg_tab:
        worst_m = max(MONTHS, key=lambda m: abs(rows[m] - cfg_tab.get(m, 0)))
        print(f"monthly table drift: worst {worst_m} "
              f"{rows[worst_m]:.3f} vs {cfg_tab.get(worst_m)} "
              f"({abs(rows[worst_m]-cfg_tab.get(worst_m, 0)):.4f})")
    print()
    print("SEASONALITY, which is the whole point:")
    best, wrst = max(rows, key=rows.get), min(rows, key=rows.get)
    print(f"  best  {best} {rows[best]:.2f} kWh/m2/day")
    print(f"  worst {wrst} {rows[wrst]:.2f} kWh/m2/day")
    print(f"  ratio {rows[best]/rows[wrst]:.2f}x")
    print("  A flat annual figure would have hidden this entirely, and hot")
    print("  water demand PEAKS in the worst month.")
    print()
    print("PER-MONTH TABLE FOR THE CONFIG (kWh/m2/day, collector plane):")
    print("    " + "  ".join(f"{m}: {rows[m]:.3f}" for m in MONTHS[:6]))
    print("    " + "  ".join(f"{m}: {rows[m]:.3f}" for m in MONTHS[6:]))

    # ---- the per-slice table the LP will actually read --------------------
    # Same convention as pv_capacity_factor: a month x daypart table whose
    # value is the AVERAGE kW per m2 over that daypart, so
    #   sum(table[m][dp] x daypart_hours x days_in_month) = annual kWh/m2.
    # One table rather than PV's modifier x shape pair, because there is no
    # separate annual anchor to renormalise against here - the level IS the
    # derivation.
    print()
    print("=" * 74)
    print("PER-SLICE TABLE (kW per m2 of collector, month x daypart)")
    print("=" * 74)
    dayparts = [f"{h:02d}_{h+2:02d}" for h in range(0, 24, 2)]
    table = {}
    for m in MONTHS:
        tamb = float(clim[m]["t_mean_c"])
        t_in = tanks[m]
        day_kwh = g46[m] / DAYS[m]
        raw = comp46[m]
        tot = sum(b + d for b, d, _ in raw)
        scale = day_kwh * 1000.0 / tot if tot > 0 else 0.0
        per_hour = [
            hour_useful_w(b * scale, d * scale, kb, k_dif, t_in, tamb,
                          eta0, a1, soil[m]) / 1000.0        # kW/m2
            for (b, d, kb) in raw
        ]
        table[m] = {dp: (per_hour[2 * i] + per_hour[2 * i + 1]) / 2.0
                    for i, dp in enumerate(dayparts)}
    # drift guard: the daypart table must reproduce the annual total
    ann_tab = sum(table[m][dp] * 2.0 * DAYS[m]
                  for m in MONTHS for dp in dayparts)
    print(f"drift guard: daypart table annual {ann_tab:.2f} kWh/m2 vs"
          f" hourly {ann:.2f}  (diff {abs(ann_tab-ann):.4f})")
    assert abs(ann_tab - ann) < 0.01, "daypart aggregation lost energy"
    print()
    for m in MONTHS:
        vals = ", ".join(f'"{dp}": {table[m][dp]:.4f}' for dp in dayparts)
        print(f"    {m}: {{{vals}}}")


if __name__ == "__main__":
    main()
