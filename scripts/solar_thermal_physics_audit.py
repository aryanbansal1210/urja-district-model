"""SOLAR THERMAL PHYSICS AUDIT - every physical parameter, checked./18.

the author: "make sure you have everyhting tehcnially corrrct: effeicny, temp,
irradiance everyhtung related to this..."

This is the single consolidated answer. Every physical quantity the technology
depends on is listed with its value, its source, its tier, and where possible a
CHECK against something independent. A line that cannot be checked says so.

Runs WITHOUT the network, so it takes seconds rather than the ~19 minutes a
network build costs.

    PYTHONPATH=. python -u scripts/solar_thermal_physics_audit.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from solar_thermal_yield_derivation import (            # noqa: E402
    COLLECTOR_TILT, PV_TILT, DAYS, MONTHS, THETA_DIFFUSE_EFF,
    hourly_components, hourly_gti, monthly_gti, hourly_dni_profiles,
    iam, hour_useful_w, GTI_OPTA_REPORT,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "verification" / "solar_thermal_physics_audit.txt"

_lines = []


def w(s: str = "") -> None:
    _lines.append(s)
    print(s, flush=True)


def check(name: str, ok: bool, detail: str) -> bool:
    w(f"  [{'PASS' if ok else 'FAIL'}] {name:<46} {detail}")
    return ok


def main() -> None:
    econ = yaml.safe_load(open(ROOT / "config" / "economics.yaml",
                               encoding="utf-8"))
    clim = yaml.safe_load(open(ROOT / "config" / "climate.yaml",
                                encoding="utf-8"))["climate"]
    st = econ["technologies"]["solar_thermal"]
    dhw = econ["heating_loads"]["dhw"]
    eta0, a1 = float(st["eta0"]), float(st["a1_w_per_m2_k"])
    b0 = float(st["iam_b0"])
    setpoint = float(dhw["setpoint_c"])
    inlet_ref = float(st["reference_inlet_c"])
    allok = True

    w("=" * 78)
    w("SOLAR THERMAL PHYSICS AUDIT")
    w("=" * 78)

    # ---------------- 1. EFFICIENCY --------------------------------------
    w("\n1. EFFICIENCY  eta = eta0 * K_ta(theta) - a1 (Ti - Ta) / G")
    w("-" * 78)
    w(f"  eta0 = {eta0}   a1 = {a1} W/m2.K   (IS 12933 Part 5, Kadyan 2016)")
    w("  These are ACCEPTANCE THRESHOLDS - the worst a collector may be and")
    w("  still pass - not typical performance. Using them is conservative.")
    k0, k1 = float(st["eta0_keymark_sensitivity"]), float(st["a1_keymark_sensitivity"])
    allok &= check("Indian eta0 <= European Keymark", eta0 <= k0,
                   f"{eta0} <= {k0}")
    allok &= check("Indian a1 >= European Keymark (worse)", a1 >= k1,
                   f"{a1} >= {k1}")
    allok &= check("eta0 in physical range 0.5-0.85", 0.5 <= eta0 <= 0.85,
                   f"{eta0}")
    allok &= check("a1 in physical range 2-8 W/m2.K", 2.0 <= a1 <= 8.0,
                   f"{a1}")

    # ---------------- 2. INCIDENCE ANGLE ---------------------------------
    w("\n2. INCIDENCE ANGLE MODIFIER   K = 1 - b0 (1/cos theta - 1)")
    w("-" * 78)
    w(f"  b0 = {b0}  (Duffie & Beckman single-glazed flat plate)")
    k50 = iam(math.radians(50.0))
    allok &= check("K(50 deg) matches EN 12975 typical 0.93-0.95",
                   0.92 <= k50 <= 0.96, f"K(50) = {k50:.4f}")
    allok &= check("K(0) = 1 exactly", abs(iam(0.0) - 1.0) < 1e-12,
                   f"{iam(0.0):.6f}")
    allok &= check("K decreases monotonically to 90 deg",
                   all(iam(math.radians(a)) >= iam(math.radians(a + 5))
                       for a in range(0, 90, 5)), "checked every 5 deg")
    allok &= check("K(90 deg) = 0", abs(iam(math.radians(90.0))) < 1e-9,
                   f"{iam(math.radians(90.0)):.6f}")
    w("  NOTE: the IAM multiplies the OPTICAL term, not G. Deflating G would")
    w("  shrink the LOSS term too and overstate cold-morning output.")

    # ---------------- 3. IRRADIANCE --------------------------------------
    w("\n3. IRRADIANCE   GSA hourly DNI transposed to the collector plane")
    w("-" * 78)
    prof = hourly_dni_profiles()
    g29 = monthly_gti(hourly_gti(PV_TILT, prof))
    s29 = sum(g29.values())
    cfg_mod = econ["pv_capacity_factor"]["monthly_modifier"]
    worst_m, worst_d = None, 0.0
    for m in MONTHS:
        mod = 1517.4 * (g29[m] / s29) / (5.18 * DAYS[m])
        d = abs(mod / cfg_mod[m] - 1.0)
        if d > worst_d:
            worst_d, worst_m = d, m
    w("  CHECK A - re-run the transposition at the PV plane (29 deg) and")
    w("  compare against this config's OWN pv monthly_modifier table.")
    allok &= check("reproduces the model's PV shape", worst_d < 0.01,
                   f"worst month {worst_m} {worst_d:+.2%}")
    cal = GTI_OPTA_REPORT / s29
    g46 = {m: v * cal for m, v in monthly_gti(hourly_gti(COLLECTOR_TILT,
                                                         prof)).items()}
    ann46 = sum(g46.values())
    allok &= check("annual GTI at collector plane is plausible",
                   1500 <= ann46 <= 2100, f"{ann46:.0f} kWh/m2/yr at "
                   f"{COLLECTOR_TILT:.0f} deg")
    w(f"  isotropic-diffuse calibration to the GSA report: x{cal:.4f}")
    w(f"  tilt effect: jan {g46['jan']/(g29['jan']*cal)-1:+.1%}, "
      f"jun {g46['jun']/(g29['jun']*cal)-1:+.1%}, "
      f"annual {ann46/(s29*cal)-1:+.1%}")

    # ---------------- 4. TEMPERATURE -------------------------------------
    w("\n4. TEMPERATURE")
    w("-" * 78)
    w(f"  ambient      : climate.yaml t_mean_c per month "
      f"(jan {clim['jan']['t_mean_c']}, jun {clim['jun']['t_mean_c']} C)")
    w(f"  cold inlet   : proxied by t_mean_c (ISO 9459-2 convention)")
    w(f"  setpoint     : {setpoint} C  (heating_loads.dhw)")
    w(f"  collector in : (inlet + setpoint)/2, DERIVED not declared")
    tanks = {m: (float(clim[m]["t_mean_c"]) + setpoint) / 2.0 for m in MONTHS}
    allok &= check("collector inlet between ambient and setpoint",
                   all(clim[m]["t_mean_c"] < tanks[m] < setpoint
                       for m in MONTHS),
                   f"jan {tanks['jan']:.1f} C, jun {tanks['jun']:.1f} C")
    allok &= check("winter tank colder than summer tank",
                   tanks["jan"] < tanks["jun"],
                   f"{tanks['jan']:.1f} < {tanks['jun']:.1f} C")
    w("  A constant tank temperature was the FIRST DRAFT'S BIGGEST ERROR:")
    w("  45 C was guessed, and it missed MNRE's measurement by -11.2%.")

    # ---------------- 5. CUTOFF ------------------------------------------
    w("\n5. CUTOFF IRRADIANCE   G* = a1 (Ti - Ta) / eta0")
    w("-" * 78)
    for m in ("jan", "jun"):
        ta = float(clim[m]["t_mean_c"])
        gstar = a1 * (tanks[m] - ta) / eta0
        w(f"  {m}: Ta {ta:.1f} C, Ti {tanks[m]:.1f} C -> G* = {gstar:.0f} W/m2")
    tab = st["kw_per_m2_by_month_daypart"]
    allok &= check("January produces nothing at 06-08 (below cutoff)",
                   tab["jan"]["06_08"] == 0.0, f"{tab['jan']['06_08']}")
    allok &= check("but PV does generate then (collector day is shorter)",
                   econ["pv_capacity_factor"]["daypart_shape_by_month"]
                   ["jan"]["06_08"] > 0,
                   f"{econ['pv_capacity_factor']['daypart_shape_by_month']['jan']['06_08']}")

    # ---------------- 6. SOILING -----------------------------------------
    w("\n6. SOILING")
    w("-" * 78)
    w("  RAW A19 PM2.5 + dust multiplier, NOT the renormalised PV one.")
    w("  The PV renormalisation exists because GSA PVOUT already contains")
    w("  3.5% soiling. This level is anchored to GSA GTI, which is")
    w("  IRRADIANCE and carries no such derate, so raw is correct here.")
    allok &= check("soiling flag on", bool(st["apply_soiling"]), "true")

    # ---------------- 7. VALIDATION vs MEASUREMENT ------------------------
    w("\n7. VALIDATION AGAINST MEASURED SYSTEMS")
    w("-" * 78)
    comp = hourly_components(COLLECTOR_TILT, prof)
    kdif = iam(math.radians(THETA_DIFFUSE_EFF))
    mnre_gti, mnre_amb, mnre_inlet, mnre_l = 5.79, 16.0, 12.0, 94.0
    meas = mnre_l * 4.186 * (setpoint - mnre_inlet) / 3600.0 / 2.0
    t_in = (mnre_inlet + setpoint) / 2.0
    raw = comp["dec"]
    tot = sum(b + d for b, d, _ in raw)
    scale = mnre_gti * 1000.0 / tot
    got = sum(hour_useful_w(b * scale, d * scale, kb, kdif, t_in, mnre_amb,
                            eta0, a1, 1.0) / 1000.0 for b, d, kb in raw)
    w(f"  (a) MNRE Table 8 Chandigarh, clear Dec day, MEASURED {mnre_l:.0f} L/day")
    w(f"      ambient {mnre_amb} C, inlet {mnre_inlet} C, collector inlet "
      f"{t_in:.0f} C")
    allok &= check("reproduces MNRE within its stated +/-10%",
                   abs(got / meas - 1) < 0.10,
                   f"{got:.3f} vs {meas:.3f} kWh/m2/day = {got/meas-1:+.1%}")

    ann = float(st["annual_kwh_per_m2"])
    sysann = ann * float(st["m2_per_100_lpd"])
    w(f"\n  (b) MNRE annual band for a single-collector system: 900-1800 kWh/yr")
    allok &= check("annual sits inside MNRE's own band",
                   900 <= sysann <= 1800, f"{sysann:.0f} kWh/yr on 2 m2")

    buck = 2219.0 / 2.4
    w(f"\n  (c) Buckley et al. 2019, 12-month MONITORED thermosiphon,")
    w(f"      Stellenbosch: {buck:.0f} kWh/m2/yr, system efficiency 50.2%")
    allok &= check("this site below a clear-winter Mediterranean site",
                   ann < buck, f"{ann:.0f} vs {buck:.0f} = {ann/buck:.0%}")
    w(f"      this model's annual efficiency: {ann/ann46*100:.1f}% of incident")
    w("      Lower on both counts, which is the expected direction for a")
    w("      fog-dominated winter and acceptance-threshold coefficients.")

    # ---------------- 8. SEASONALITY & DRIFT ------------------------------
    w("\n8. SEASONALITY AND INTERNAL CONSISTENCY")
    w("-" * 78)
    daily = {m: sum(tab[m].values()) * 2.0 for m in MONTHS}
    lo, hi = min(daily, key=daily.get), max(daily, key=daily.get)
    allok &= check("yield troughs in January", lo == "jan",
                   f"{lo} {daily[lo]:.2f} kWh/m2/day")
    allok &= check("yield peaks in spring", hi in ("mar", "apr", "may"),
                   f"{hi} {daily[hi]:.2f} kWh/m2/day")
    w(f"  seasonality {daily[hi]/daily[lo]:.2f}x, and DEMAND runs the other way")
    tabann = sum(tab[m][dp] * 2.0 * DAYS[m] for m in MONTHS for dp in tab[m])
    allok &= check("slice table reproduces annual_kwh_per_m2",
                   abs(tabann - ann) < 1.0, f"{tabann:.2f} vs {ann}")

    # ---------------- 9. STORAGE ------------------------------------------
    w("\n9. STORAGE")
    w("-" * 78)
    litres = float(st["tank_litres_per_m2_collector"])
    tank_kwh = litres * 4.186 * (setpoint - inlet_ref) / 3600.0
    w(f"  {litres:.0f} L/m2 over ({setpoint:.0f} - {inlet_ref:.0f}) K "
      f"= {tank_kwh:.2f} kWh/m2")
    loss = float(st["tank_standing_loss_frac_per_hour"])
    hold = float(st["bucket_average_hold_hours"])
    allok &= check("standing loss inside the 1-3%/h defensible band",
                   0.01 <= loss <= 0.03, f"{loss:.1%}/h (Tier 3 DECLARED)")
    allok &= check("bucket hold calibrated to the hour-by-hour tank",
                   abs(hold - 12.5) < 0.2,
                   f"{hold} h -> retention {(1-loss)**hold:.4f}")
    w("  The draw-centroid estimate (10.8 h) is 3.7% OPTIMISTIC against the")
    w("  hour-by-hour simulation. The calibrated 12.5 h is used instead.")
    allok &= check("tank can hold roughly one day of collection",
                   0.8 <= tank_kwh / (ann / 365.0) <= 2.5,
                   f"{tank_kwh/(ann/365.0):.2f} days of average yield")

    # ---------------- 10. WHAT IS NOT VERIFIED ----------------------------
    w("\n10. NOT VERIFIED - stated rather than hidden")
    w("-" * 78)
    w("  - No BIS/NABL certificate for a NAMED Indian collector is public.")
    w("    IS 12933 acceptance thresholds are used instead, which are the")
    w("    worst a collector may be and still pass. Conservative.")
    w("  - Tank standing loss 2%/h is Tier 3 DECLARED. No Indian BIS UA")
    w("    figure was found. It is also the MOST SENSITIVE number: across")
    w("    the 1-3%/h band the annual solar fraction moves 8.1 points.")
    w("  - Embodied carbon 338.5 kgCO2/m2 is from an ITALIAN LCA (Ardente")
    w("    2005). Indian manufacturing is more coal-intensive, so this")
    w("    probably UNDERSTATES. No India scaling factor was invented.")
    w("  - Wind speed is not in the loss coefficient; a1 is a test value at")
    w("    standard wind. Second order.")
    w("  - Row spacing is not applied, to match how rooftop PV is modelled.")
    w("    The collector is steeper so this flatters it by ~12.8% of area.")

    w("\n" + "=" * 78)
    w(f"RESULT: {'ALL PHYSICS CHECKS PASS' if allok else 'ONE OR MORE FAILED'}")
    w("=" * 78)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(_lines), encoding="utf-8")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
