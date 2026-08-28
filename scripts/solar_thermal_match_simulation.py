"""How much of the hot water can solar thermal ACTUALLY serve?.

THE QUESTION THIS ANSWERS. Every number so far has been a ceiling: 742 kWh
per m2 per year of collector capability against 36.146 GWh/yr of water
heating. Dividing one by the other gives 48,714 m2, or 7.28% of the
district's deployable roof, and that number is WRONG AS AN ANSWER because it
assumes every kWh collected lands on a kWh of demand. It cannot:

  * THE SEASONS FIGHT.   demand jan 4.065 GWh / jun 2.312 = 1.76x, peaking in
                         WINTER. yield apr 2.724 / jan 1.054 = 2.58x, peaking
                         in SPRING. The worst supply month is the best demand
                         month.
  * THE CLOCK FIGHTS.    79.05% of the draw is OUTSIDE the 08-16 window the
                         collector works in, and 41.58% of it is the 06-08
                         morning shower - which has to be heat collected
                         YESTERDAY, held overnight through a 2%/hour standing
                         loss.

So this script runs the day the LP will run: collect per daypart, store with
losses, draw against the real demand shape, dump what will not fit in the
tank. It reports the solar fraction that is actually reachable and the area
that reaches it.

*** IT IS A SIMULATION, NOT THE OPTIMISER. *** It dispatches greedily
(serve now, store the rest) which is what a thermosiphon system with a
thermostat physically does. The LP may do slightly better because it can see
the whole bucket at once. Treat the numbers here as a floor and a sanity
check on what the LP later reports.

    PYTHONPATH=. python -u scripts/solar_thermal_match_simulation.py
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec")
DAYS = {"jan": 31, "feb": 28.25, "mar": 31, "apr": 30, "may": 31, "jun": 30,
        "jul": 31, "aug": 31, "sep": 30, "oct": 31, "nov": 30, "dec": 31}
DAYPARTS = [f"{h:02d}_{h+2:02d}" for h in range(0, 24, 2)]

DHW_BY_MONTH_GWH = {"jan": 4.065, "feb": 3.376, "mar": 3.317, "apr": 2.703,
                    "may": 2.432, "jun": 2.312, "jul": 2.535, "aug": 2.604,
                    "sep": 2.603, "oct": 2.990, "nov": 3.351, "dec": 3.858}
DHW_DAYPART_SHARE = {"00_02": 0.0000, "02_04": 0.0000, "04_06": 0.0487,
                     "06_08": 0.4158, "08_10": 0.1540, "10_12": 0.0236,
                     "12_14": 0.0163, "14_16": 0.0156, "16_18": 0.0518,
                     "18_20": 0.1374, "20_22": 0.1101, "22_24": 0.0268}
DHW_TOTAL_GWH = 36.146
ROOF_TOTAL_M2 = 668_854


def simulate(area_m2: float, yield_tab: dict, tank_kwh_per_m2: float,
             loss_per_hour: float) -> dict:
    """One representative day per month, carried cyclically.

    The tank state is carried from the end of the day back to its start
    (steady-state daily cycle), which is what makes the 06-08 morning draw
    cost a full overnight hold rather than being free.
    """
    tank_cap = area_m2 * tank_kwh_per_m2
    out = {"served": 0.0, "collected": 0.0, "dumped": 0.0, "by_month": {}}
    for m in MONTHS:
        dem_day = DHW_BY_MONTH_GWH[m] * 1e6 / DAYS[m]        # kWh/day
        col = [yield_tab[m][dp] * area_m2 * 2.0 for dp in DAYPARTS]
        dem = [dem_day * DHW_DAYPART_SHARE[dp] for dp in DAYPARTS]
        # iterate the cyclic start-of-day state to a fixed point
        soc = 0.0
        served = collected = dumped = 0.0
        for _ in range(6):
            served = collected = dumped = 0.0
            s = soc
            for i in range(12):
                s *= (1.0 - loss_per_hour) ** 2.0     # standing loss, 2 h
                s += col[i]
                collected += col[i]
                if s > tank_cap:
                    dumped += s - tank_cap
                    s = tank_cap
                take = min(s, dem[i])
                served += take
                s -= take
            soc = s
        out["served"] += served * DAYS[m]
        out["collected"] += collected * DAYS[m]
        out["dumped"] += dumped * DAYS[m]
        out["by_month"][m] = {
            "served": served * DAYS[m], "demand": dem_day * DAYS[m],
            "collected": collected * DAYS[m], "dumped": dumped * DAYS[m]}
    return out


def main() -> None:
    econ = yaml.safe_load(open(ROOT / "config" / "economics.yaml",
                               encoding="utf-8"))
    st = econ["technologies"]["solar_thermal"]
    tab = st["kw_per_m2_by_month_daypart"]
    tank = float(st["tank_litres_per_m2_collector"]) * 4.186 \
        * (float(econ["heating_loads"]["dhw"]["setpoint_c"])
           - float(st["reference_inlet_c"])) / 3600.0
    loss = float(st["tank_standing_loss_frac_per_hour"])

    print("=" * 78)
    print("THE TWO MISMATCHES, MEASURED")
    print("=" * 78)
    print(f"{'mon':<5}{'demand GWh':>12}{'yield kWh/m2/d':>16}"
          f"{'demand rank':>13}{'yield rank':>12}")
    dr = sorted(MONTHS, key=lambda m: -DHW_BY_MONTH_GWH[m])
    yv = {m: sum(tab[m][dp] * 2.0 for dp in DAYPARTS) for m in MONTHS}
    yr = sorted(MONTHS, key=lambda m: -yv[m])
    for m in MONTHS:
        print(f"{m:<5}{DHW_BY_MONTH_GWH[m]:>12.3f}{yv[m]:>16.3f}"
              f"{dr.index(m)+1:>13}{yr.index(m)+1:>12}")
    print(f"\n  demand peaks {dr[0]}, yield peaks {yr[0]}."
          f"  demand's best month is yield's WORST ({yr[-1]}).")
    print(f"  {DHW_DAYPART_SHARE['06_08']:.1%} of the draw is 06-08 - heat")
    print(f"  collected YESTERDAY, held overnight at {loss:.0%}/h."
          f"  A 16 h hold retains {(1-loss)**16:.1%}.")

    print()
    print("=" * 78)
    print("SIZING SWEEP - what each area actually delivers")
    print("=" * 78)
    print(f"  tank {tank:.2f} kWh per m2 of collector,"
          f" standing loss {loss:.0%}/h")
    print(f"\n{'m2':>9}{'% roof':>8}{'collected':>11}{'SERVED':>10}"
          f"{'dumped':>9}{'solar frac':>12}{'util':>8}")
    best = None
    for area in (10_000, 20_000, 30_000, 48_714, 70_000, 100_000, 150_000):
        r = simulate(area, tab, tank, loss)
        frac = r["served"] / (DHW_TOTAL_GWH * 1e6)
        util = r["served"] / r["collected"] if r["collected"] else 0.0
        print(f"{area:>9,}{area/ROOF_TOTAL_M2:>8.1%}"
              f"{r['collected']/1e6:>11.2f}{r['served']/1e6:>10.2f}"
              f"{r['dumped']/1e6:>9.2f}{frac:>12.1%}{util:>8.1%}")
        if area == 48_714:
            best = r
    print("\n  'collected' is gross capability, 'SERVED' is what reaches a")
    print("  tap. 'util' is the fraction of collected heat that is not")
    print("  wasted. THE GAP BETWEEN THEM IS THE WHOLE STORY.")

    print()
    print("=" * 78)
    print("THE NAIVE AREA, MONTH BY MONTH")
    print("=" * 78)
    print("  48,714 m2 = demand / annual yield, i.e. the number you get by")
    print("  dividing. Here is what it actually does:")
    print(f"\n{'mon':<5}{'demand':>10}{'served':>10}{'frac':>9}"
          f"{'dumped':>10}")
    for m in MONTHS:
        d = best["by_month"][m]
        print(f"{m:<5}{d['demand']/1e6:>10.3f}{d['served']/1e6:>10.3f}"
              f"{d['served']/d['demand']:>9.1%}{d['dumped']/1e6:>10.3f}")
    print(f"\n  ANNUAL solar fraction at the naive area:"
          f" {best['served']/(DHW_TOTAL_GWH*1e6):.1%}")
    print(f"  JANUARY solar fraction:"
          f" {best['by_month']['jan']['served']/best['by_month']['jan']['demand']:.1%}")
    print("\n  So the number that came from dividing is not achievable, and")
    print("  the reason is the two mismatches at the top of this page. The")
    print("  LP will be choosing against exactly this, per building.")

    # ---- WHERE THE MISSING HEAT GOES -------------------------------------
    print()
    print("=" * 78)
    print("NOTHING IS DUMPED AT THAT AREA - SO WHERE DID 21% OF IT GO?")
    print("=" * 78)
    lost = best["collected"] - best["served"] - best["dumped"]
    print(f"  collected {best['collected']/1e6:6.2f} GWh")
    print(f"  served    {best['served']/1e6:6.2f} GWh")
    print(f"  dumped    {best['dumped']/1e6:6.2f} GWh  (tank never fills at"
          " this size)")
    print(f"  STANDING LOSS {lost/1e6:6.2f} GWh ="
          f" {lost/best['collected']:.1%} of everything collected")
    print("\n  That is the price of the 06-08 morning peak. The heat is")
    print("  collected at midday and has to sit in the tank until the next")
    print("  morning's shower, losing 2% of itself every hour it waits.")
    print("  THE BINDING CONSTRAINT IS NOT ROOF AREA AND IT IS NOT TANK SIZE.")
    print("  It is the clock.")

    # ---- and standing loss is a DECLARED number, so sweep it -------------
    print()
    print("=" * 78)
    print("SENSITIVITY: standing loss is Tier 3 DECLARED, and it costs 21%")
    print("=" * 78)
    print("  No published Indian BIS UA figure was found. 2%/h was declared")
    print("  inside the 1-3%/h band EN 12976 / ISO 9459 practice quotes. It")
    print("  is the single least-evidenced number in this technology and it")
    print("  moves the answer more than the collector coefficients do.")
    # compute the 2%/h baseline FIRST - reading it out of the loop left the
    # first two rows comparing against None and printing a false +0.0%.
    levels = (0.01, 0.015, 0.02, 0.025, 0.03)
    fracs = {lv: simulate(48_714, tab, tank, lv)["served"]
             / (DHW_TOTAL_GWH * 1e6) for lv in levels}
    base = fracs[0.02]
    print(f"\n{'loss/h':>8}{'solar frac':>12}{'vs 2%':>9}")
    for lv in levels:
        print(f"{lv:>8.1%}{fracs[lv]:>12.1%}{fracs[lv]/base-1:>+9.1%}"
              + ("   <- production" if lv == 0.02 else ""))
    span = fracs[0.01] - fracs[0.03]
    print(f"\n  Across the defensible 1-3%/h band the annual solar fraction")
    print(f"  moves {span*100:.1f} percentage points"
          f" ({fracs[0.03]:.1%} to {fracs[0.01]:.1%}).")
    print("  That is a bigger lever than sharpening eta0 or a1, and it is")
    print("  the number to chase if a BIS tank test can be obtained.")


if __name__ == "__main__":
    main()
