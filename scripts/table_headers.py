"""Turn machine column keys into readable table headers.

the author,, on Appendix H: "pct instead of %, inr instead of rupee sign,
per instead of /, no brackets... what is m inr, and why is g in gwh not
capitalised".

WHERE THIS COMES FROM. The sweep scripts write their artefacts by taking a
dictionary key and replacing underscores with spaces, so `voll_inr_per_kwh`
reaches the appendix as "voll inr per kwh". Every one of those is a variable
name shown to a reader. The appendix copies its artefacts verbatim, which is
the right default - it is why the numbers cannot drift - so the fix belongs
here, at the copy, and applies to every artefact at once rather than to each
sweep script separately.

TWO RULES DO ALL THE WORK.
  * A unit token becomes its symbol: inr to the rupee sign, gwh to GWh, pct
    to %, minr to "rupees million".
  * "X per Y" collapses to "X/Y" ONLY when both sides are units. "per
    household", "per capita" and "per hectare" are prose and stay as words -
    "households/hectare" would be worse, not better.

WHAT IT WILL NOT DO. It does not invent a unit. If a header says "cost" with
no unit anywhere, it stays "Cost"; guessing rupees there would be exactly the
silent inference this project keeps getting caught by.
"""
from __future__ import annotations

import re

RUPEE = chr(8377)
SUB2 = chr(8322)

# Unit tokens, lower-case key -> what a reader should see.
UNITS = {
    "inr": RUPEE, "rs": RUPEE,
    "kwh": "kWh", "gwh": "GWh", "mwh": "MWh", "twh": "TWh",
    "kwp": "kWp", "mwp": "MWp", "kw": "kW", "mw": "MW", "kva": "kVA",
    "mva": "MVA", "kt": "kt", "mt": "Mt", "co2": "CO" + SUB2,
    "pct": "%", "%": "%", "pp": "percentage points",
    "m2": "m" + chr(178), "mwh_e": "MWh electrical",
    "kw_e": "kW electrical", "h": "hours",
    "yr": "year", "ha": "hectare", "kl": "kL", "m3": "m" + chr(179),
}

# Words spelled out, because an abbreviation in a header is a private note.
WORDS = {
    "minr": RUPEE + " million", "binr": RUPEE + " billion",
    "voll": "value of lost load", "lcoe": "LCOE",
    "emis": "emissions", "crit": "critical", "op": "operating",
    "delta": "change", "avg": "mean", "cum": "cumulative",
    "capex": "capital cost", "opex": "operating cost",
    "res": "residential", "pv": "photovoltaic", "hh": "household",
    "gen": "generation", "dem": "demand", "cap": "capacity",
}


# EXPLICIT BEFORE CLEVER. There are only twenty-two machine headers in the whole
# appendix, and a rule general enough to get "shed gwh window" right on its own
# would also be general enough to mangle something it has not seen. Each is
# written out and can be checked by eye; the generic rules below still handle
# anything new, and anything neither covers is left alone rather than guessed.
OVERRIDE = {
    "total served %": "Total load served (%)",
    "critical served %": "Critical load served (%)",
    "straw burned mwh_e": "Straw burned (MWh electrical)",
    "straw burned mwh e": "Straw burned (MWh electrical)",
    "first critical gap (h)": "First critical gap (hours)",
    "critical 100% hours (of 72)": "Hours at 100% (of 72)",
    "vs bau": "Against business as usual",
    "vs-bau cost": "Cost against business as usual (%)",
    "vs-bau co2": "CO2 against business as usual (%)",
    "cost m/yr": "Cost (₹ million/year)",
    "cost rs m/yr (2030)": "2030 cost (₹ million/year)",
    "annual cost rs": "Annual cost (₹)",
    "district bill inr/yr": "District bill (₹/year)",
    "lifetime rs": "Lifetime cost (₹)",
    "annual co2 kg": "Annual CO2 (kg)",
    "kwh/cap": "Per capita (kWh)",
    "lcoe, inr/kwh": "Levelised cost (₹/kWh)",
    "rs/kwh": "Price (₹/kWh)",
    "usd/kwh": "Price (USD/kWh)",
    "2030 capex rs/kwh": "2030 capital cost (₹/kWh)",
    "real irr": "Real internal rate of return (%)",
    "cumulative mt": "Cumulative emissions (Mt)",
    "green-buy gwh": "Green purchase (GWh)",
    "self-consumed gwh": "Self-consumed (GWh)",
    "shed gwh year": "Energy shed (GWh/year)",
    "shed gwh window": "Energy shed in the window (GWh)",
    "served pct window": "Demand served in the window (%)",
    "crit served pct window": "Critical load served in the window (%)",
    "window demand gwh": "Demand in the window (GWh)",
    "window critical gwh": "Critical demand in the window (GWh)",
    "voll cost minr": "Value of lost load ({R} million)",
    "voll inr per kwh": "Value of lost load ({R}/kWh)",
    "op cost delta minr": "Operating cost change ({R} million)",
    "annual value inr": "Annual value ({R})",
    "lcoe inr per kwh": "Levelised cost ({R}/kWh)",
    "collector m2 per household": "Collector area per household (m{S2})",
    "2030 annual cost m": "2030 annual cost ({R} million)",
    "lifetime b": "Lifetime cost ({R} billion)",
    "export rs/kwh": "Export price ({R}/kWh)",
    "net rs/kwh": "Net price ({R}/kWh)",
    "rate rs/kl": "Rate ({R}/kL)",
    "r (real)": "Discount rate (real)",
    "delta": "Change",
    "delta pp": "Change (percentage points)",
    "emis kt": "Emissions (kt)",
    "battery 2030 mwh": "Battery 2030 (MWh)",
    "annual cost m": "Annual cost ({R} million)",
    "vs base": "Change against base",
    "share of headline": "Share of the headline",
}
OVERRIDE = {k: v.replace("{R}", chr(8377)).replace("{S2}", chr(178))
            for k, v in OVERRIDE.items()}

UNIT_KEYS = set(UNITS)


def _unit(tok: str) -> str | None:
    return UNITS.get(tok.lower())


def header(text: str) -> str:
    """One machine key or loose header to a readable label with its unit."""
    s = " ".join(str(text).split())
    if not s:
        return s
    hit = OVERRIDE.get(s.lower().replace("_", " "))
    if hit:
        return hit
    if not re.fullmatch(r"[A-Za-z0-9 _%/()" + chr(178) + chr(179) + r"-]+", s):
        return s[:1].upper() + s[1:]      # capitalise, restructure nothing
    # A header already carrying a bracketed unit has been written for a reader.
    if "(" in s and ")" in s:
        return s[:1].upper() + s[1:]
    # A HEADER ENDING IN A CORRECTLY-SPELLED UNIT STILL NEEDS ITS BRACKETS.
    # This early return treated "consumption GWh" as already reader-ready,
    # because GWh carries capitals, and left thirty-eight headers with the
    # unit inline instead of bracketed.
    last = s.split()[-1].lower().strip("()")
    ends_in_unit = (last in UNIT_KEYS or last in ("minr", "binr")
                    or re.fullmatch(r"[a-z]{1,4}/[a-z]{1,4}", last) is not None)
    if (any(c.isupper() for c in s) and "_" not in s and not ends_in_unit
            and not re.search(r"(?:M|B|Rs|INR)", s)):
        return s

    toks = s.replace("_", " ").split()
    if not toks:
        return s

    # "x per y" -> "x/y" only when both sides are units
    out, i = [], 0
    while i < len(toks):
        if (i + 2 < len(toks) + 0 and toks[i].lower() in UNIT_KEYS
                and i + 1 < len(toks) and toks[i + 1].lower() == "per"
                and i + 2 < len(toks) and toks[i + 2].lower() in UNIT_KEYS):
            out.append(_unit(toks[i]) + "/" + _unit(toks[i + 2]))
            i += 3
            continue
        out.append(toks[i])
        i += 1

    # split the trailing units off the quantity, so the label reads
    # "Value of lost load (INR/kWh)" rather than "Value of lost load INR kWh"
    units, k = [], len(out)
    while k > 0:
        t = out[k - 1]
        if t.lower() in UNIT_KEYS or t.lower() in ("minr", "binr") or "/" in t:
            units.insert(0, t)
            k -= 1
        else:
            break
    name_toks, unit_toks = out[:k], units

    name = " ".join(WORDS.get(t.lower(), t) for t in name_toks)
    unit = " ".join(WORDS.get(t.lower(), _unit(t) or t) for t in unit_toks)

    if not name:
        name, unit = unit, ""
    name = name[:1].upper() + name[1:] if name else name
    return "%s (%s)" % (name, unit) if unit else name


def fix_markdown(text: str) -> str:
    """Rewrite the header row of every pipe table in a markdown document."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        cells = [c.strip() for c in nxt.strip().strip("|").split("|")]
        if not cells or not all(re.fullmatch(r":?-{2,}:?", c or "-")
                                for c in cells):
            continue                    # the next row is not a separator
        head = [c.strip() for c in line.strip().strip("|").split("|")]
        lines[i] = "| " + " | ".join(header(h) for h in head) + " |"
    return "\n".join(lines)


if __name__ == "__main__":
    for probe in ("voll_inr_per_kwh", "shed gwh year", "served pct window",
                  "op cost delta minr", "window demand gwh", "r (real)",
                  "collector m2 per household", "2030 annual cost M"):
        print("%-30s -> %s" % (probe, header(probe)))
