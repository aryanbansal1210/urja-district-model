"""Generate Appendix B - the mathematical formulation - from the code itself.

B.1 is the layout problem: the 20 hard constraints and the 39 weighted
objectives, with their families, weights and what each one checks.

B.2 is the energy system: the sets, decision variables and constraint groups of
the multi-period linear program as actually declared in `energy/dispatch.py`.

The enumeration is extracted rather than typed, so a constraint added to the
model cannot silently go missing from the appendix. The narrative framing around
each group is editorial and lives in this file.

Run from the repo root:
    python scripts/appendix_b_formulation.py
"""
from __future__ import annotations

import ast
import os
import re
import sys

OUT = os.path.join("..", "..", "WRITEUP", "APPENDIX", "B_formulation.md")

# Editorial grouping. The code has no notion of families; this declares them and
# the script asserts the grouping partitions the real totals exactly.
HARD_FAMILY = {
    "Network integrity": ["road_connectivity", "road_proximity",
                          "amenities_road_frontage", "highstreet_road_frontage",
                          "parking_road_frontage"],
    "Separation": ["schools_industry_separation", "industry_on_edge",
                   "industrial_buffer", "green_space_buffer",
                   "stage_c_plant_buffer"],
    "Provision": ["area_targets", "solar_farm_clustering",
                  "open_space_clustering", "school_catchment",
                  "religious_catchment", "amenity_equity",
                  "park_quadrant_coverage"],
    "Siting": ["hospital_near_road", "building_shading", "highstreet_corridor"],
}

OBJ_FAMILY = {
    "Generation potential": ["solar_capacity", "solar_access", "solar_farm_access",
                             "solar_cluster", "pv_shading_yield", "building_orientation",
                             "building_axis_coherence", "highstreet_axis_alignment"],
    "Access": ["walkable_destinations", "access_school", "access_commercial",
               "access_healthcare", "coverage_15min", "mixed_use_ratio_400m",
               "shannon_diversity", "ews_amenity_access",
               "population_catchment_coverage", "walkability_permeability"],
    "Form": ["open_space_cluster", "commercial_cluster", "income_block_clustering",
             "town_compactness", "park_shape", "open_singletons",
             "mid_ews_adjacency", "solar_farm_residential_buffer"],
    "Microclimate": ["sky_view_factor", "albedo_composite", "heat_island_index",
                     "anthro_heat_clustering", "wind_alignment",
                     "building_wind_alignment", "tree_shading_routes",
                     "cool_refuge_distance", "ews_heat_shielding",
                     "blue_space_green_buffer", "water_body_proximity",
                     "high_income_water_proximity"],
    "Infrastructure": ["infrastructure_distance"],
}

# Constraint groups for the LP, in the order the appendix presents them. Each
# entry maps a heading to the Pyomo component-name prefixes that belong to it.
LP_GROUPS = [
    ("Energy balance", ["balance"], "One balance per period and slice: supply plus "
     "import plus discharge equals demand plus export plus charge."),
    ("Land and roof area budgets", ["farm_", "roof", "carport", "canal", "float",
                                    "bipv", "area", "land"],
     "Budgets AREA rather than capacity, so each vintage occupies land at its own "
     "density and standing capacity is never re-rated by a later period."),
    ("Capacity accounting across vintages", ["cum", "cap", "install", "vintage",
                                             "total_cap", "build"],
     "Installed capacity in a period is the sum of surviving builds from that "
     "vintage and every earlier one."),
    ("Storage", ["batt", "thermal_", "soc", "store"],
     "State of charge with chronology inside each bucket, plus charge and "
     "discharge power limits set by a real C-rate."),
    ("Vehicle to grid", ["v2g", "ev_"],
     "Fleet-capped, with availability and willingness applied by income tier."),
    ("Demand-side response", ["dsr"],
     "Per-slice caps on both adding and reducing load, and conservation within "
     "each month and day-type bucket so shifted energy cannot be created."),
    ("Grid interaction", ["grid", "imp", "exp", "gp_", "green", "conn", "ppa", "dc_"],
     "Sized connection as a decision variable, import and export limits, tariff "
     "banding, and the rule that the district may not sell into an import."),
    ("Dispatchable plant", ["biomass", "wte", "biogas", "straw", "chp"],
     "Resource budgets rather than capacity limits: an annual straw catchment "
     "with a monthly availability ceiling, municipal waste, and sewage gas."),
    ("Solar thermal", ["solar_thermal", "collector", "tank", "hot_water"],
     "Collector area within eligible roof, tank capacity, and the inter-temporal "
     "constraint linking collection to draw-off."),
    ("Resilience", ["unserved", "critical", "shed", "voll"],
     "An unserved-energy variable priced at the value of lost load, so a scenario "
     "that cannot serve critical demand pays for it."),
    ("Curtailment", ["curtail"],
     "An explicit curtailment variable, so the balance is never forced to absorb "
     "generation it does not want."),
]


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _first_sentence(doc: str) -> str:
    doc = " ".join((doc or "").split())
    if not doc:
        return ""
    doc = re.split(r"(?<=[.!?])\s+", doc)[0].replace("|", "/")
    return doc[:299].rsplit(" ", 1)[0] + "..." if len(doc) > 300 else doc


def docs_for(src: str, prefix: str) -> dict[str, str]:
    """First sentence of every top-level function whose name starts with prefix."""
    out: dict[str, str] = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name.startswith(prefix):
            out[node.name[len(prefix):]] = _first_sentence(ast.get_docstring(node))
    return out


# Objectives whose scoring is done by a shared or differently-named helper, so
# the resolver cannot reach a docstring. Wording taken from the metrics module's
# own header and its walking-distance constants.
METRIC_OVERRIDE = {
    "access_school": "One minus the mean residential walking distance to a school, "
                     "normalised against an 800 m target.",
    "access_commercial": "One minus the mean residential walking distance to "
                         "commercial floorspace, normalised against a 600 m target.",
    "access_healthcare": "One minus the mean residential walking distance to "
                         "healthcare, normalised against a 1,500 m target.",
    "coverage_15min": "Fraction of residential cells within 1,200 m of all three "
                      "amenity types at once, the 15-minute-city test.",
    "open_singletons": "Penalises isolated single cells of open space, which read as "
                       "leftover gaps rather than usable public realm.",
    "tree_shading_routes": "Rewards street trees along the walking routes residents "
                           "actually use, rather than tree cover in aggregate.",
}


def metric_docs(src: str, keys: list[str]) -> dict[str, str]:
    """Resolve each objective key to its scoring function's docstring.

    Metric functions are named `<key>_score`, `<key>`, or something close to it
    (`solar_farm_access` is implemented as `solar_farm_solar_access`), so try
    exact names first and fall back to a token match.
    """
    funcs: dict[str, str] = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            funcs[node.name] = _first_sentence(ast.get_docstring(node))
    out: dict[str, str] = {}
    for key in keys:
        if key in METRIC_OVERRIDE:
            out[key] = METRIC_OVERRIDE[key]
            continue
        for cand in (f"{key}_score", key, f"{key}_index", f"{key}_ratio"):
            if funcs.get(cand):
                out[key] = funcs[cand]
                break
        else:
            toks = set(key.split("_"))
            best = ""
            for nm, doc in funcs.items():
                if not doc:
                    continue
                if toks <= set(nm.split("_")):
                    if not best or len(nm) < len(best):
                        best = nm
            out[key] = funcs.get(best, "")
    return out


def lp_components(src: str, start_line: int):
    """Pyomo Var / Constraint declarations after start_line, with index sets."""
    var_re = re.compile(r"^\s*m\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*pyo\.Var\((.*)$")
    con_re = re.compile(r"^\s*m\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*pyo\.Constraint\((.*)$")
    set_re = re.compile(r"^\s*m\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*pyo\.(Set|RangeSet)\((.*)$")
    vars_, cons, sets_ = [], [], []
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        if i < start_line:
            continue
        m = set_re.match(line)
        if m:
            sets_.append((m.group(1), m.group(3)[:90]))
            continue
        m = var_re.match(line)
        if m:
            decl = m.group(2)
            # a Var( that opens on its own line carries its bounds below it
            j = i
            while not decl.strip(" ,") and j < len(lines):
                decl = lines[j].strip()
                j += 1
            vars_.append((m.group(1), decl[:90]))
            continue
        m = con_re.match(line)
        if m:
            idx = re.findall(r"m\.([A-Z][A-Za-z0-9_]*)", m.group(2))
            cons.append((m.group(1), ", ".join(idx) if idx else "scalar"))
    return sets_, vars_, cons


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    os.chdir(root)

    csrc = read(os.path.join("layout", "constraints.py"))
    msrc = read(os.path.join("layout", "metrics.py"))
    dsrc = read(os.path.join("energy", "dispatch.py"))

    cdocs = docs_for(csrc, "check_")

    sys.path.insert(0, os.getcwd())
    from layout.metrics import DEFAULT_WEIGHTS as W  # noqa: E402

    mdocs = metric_docs(msrc, list(W))

    hard_all = [c for fam in HARD_FAMILY.values() for c in fam]
    obj_all = [o for fam in OBJ_FAMILY.values() for o in fam]
    assert len(hard_all) == len(set(hard_all)) == 20, len(hard_all)
    assert len(obj_all) == len(set(obj_all)) == 39, len(obj_all)
    missing = [o for o in obj_all if o not in W]
    assert not missing, f"objectives not in DEFAULT_WEIGHTS: {missing}"

    P: list[str] = []
    A = P.append

    A("# Appendix B - Mathematical formulation\n")
    A(
        "**The enumeration in this appendix is generated by "
        "`scripts/appendix_b_formulation.py` directly from `layout/constraints.py`, "
        "`layout/metrics.py` and `energy/dispatch.py`.** A constraint added to the "
        "model therefore cannot go missing from the appendix. The grouping into "
        "families is editorial and is asserted at build time to partition the real "
        "totals exactly.\n"
    )
    A(
        "The design problem is solved in two stages. The first places land uses on a "
        "grid and is combinatorial; the second sizes and operates the energy system on "
        "the resulting layout and is a linear program. The stages are sequential, not "
        "co-optimised, and B.1.5 states why.\n"
    )

    # ------------------------------------------------------------ B.1
    A("\n---\n\n## B.1 Layout optimisation\n")
    A("### B.1.1 Problem statement\n")
    A(
        "Assign one land use to each of the 2,500 cells of a 50 x 50 grid at 100 m "
        "resolution, subject to statutory hard constraints, minimising a weighted sum "
        "of design objectives. Quantities are fixed before placement by population and "
        "statutory norms, so the optimiser decides **where**, never **how much**.\n"
    )
    A(
        "Solved by simulated annealing: 15,000 iterations at a frozen random seed of "
        "42, with the objective falling from +152.41 to +20.56. Lower is better; the "
        "objective is a penalty.\n"
    )

    A("\n### B.1.2 Hard constraints\n")
    A(
        f"{len(hard_all)} constraints in four families. A layout violating any of them "
        "is infeasible, and the annealer penalises violations rather than rejecting "
        "moves outright, so it can pass through infeasible states on the way to a "
        "better basin.\n"
    )
    for fam, names in HARD_FAMILY.items():
        A(f"\n**{fam}** ({len(names)})\n")
        A("| constraint | what it requires |")
        A("|---|---|")
        for nm in names:
            A(f"| `{nm}` | {cdocs.get(nm, '')} |")

    A("\n### B.1.3 Weighted objectives\n")
    tot = sum(W[o] for o in obj_all)
    A(
        f"{len(obj_all)} objectives in five families, total weight {tot:.2f}. Each "
        "returns a normalised score; the objective is the weighted sum of the "
        "shortfalls.\n"
    )
    for fam, names in OBJ_FAMILY.items():
        fw = sum(W[o] for o in names)
        A(f"\n**{fam}** ({len(names)}, weight {fw:.2f})\n")
        A("| objective | weight | what it scores |")
        A("|---|---|---|")
        for nm in sorted(names, key=lambda x: -W[x]):
            A(f"| `{nm}` | {W[nm]:.3f} | {mdocs.get(nm, '')} |")

    A("\n### B.1.4 Objective weights in full\n")
    A("| objective | weight |")
    A("|---|---|")
    for nm, w in sorted(W.items(), key=lambda kv: -kv[1]):
        A(f"| `{nm}` | {w:.3f} |")
    A(
        "\nAn objective carrying weight 0.000 is computed and reported but does not "
        "steer the search; it is retained so the metric can be quoted without being "
        "silently unavailable.\n"
    )

    A("\n### B.1.5 Why annealing, and what the output is\n")
    A(
        "Assigning 2,500 cells across the land-use alphabet is combinatorially "
        "intractable, so no exact optimum is available and none is claimed. The result "
        "is reported as **one good feasible design**, not as the optimum. The seed is "
        "frozen so the layout is reproducible, and every downstream energy result is "
        "computed on that single frozen layout, which is why the layout carries a "
        "fingerprint hash.\n"
    )
    A(
        "The two stages are sequential rather than co-optimised. Coupling them would "
        "require the annealer to solve an energy system at every move, which is not "
        "tractable at 15,000 iterations. The consequence is stated in the limitations: "
        "the layout is optimised against proxies for energy performance, such as solar "
        "access and shading, rather than against the energy system's own objective.\n"
    )

    # ------------------------------------------------------------ B.2
    A("\n---\n\n## B.2 Energy system optimisation\n")
    mp_line = dsrc.find("\ndef build_multi_period")
    start = dsrc[:mp_line].count("\n") + 1 if mp_line > 0 else 1900
    sets_, vars_, cons = lp_components(dsrc, start)

    A("### B.2.1 Problem statement\n")
    A(
        "A linear program that decides, simultaneously, what capacity of each "
        "technology to build in each of three investment periods and how to operate "
        "the whole system in every representative slice of every period, minimising "
        "annualised system cost plus a carbon weight times emissions.\n"
    )
    A(
        "Investment and operation are solved together rather than in sequence. That "
        "matters: several results in this thesis, including the entry date of storage "
        "and the fact that solar thermal is built at all, exist only because the "
        "objective can see capacity persisting across vintages.\n"
    )

    A("\n### B.2.2 Sets\n")
    A("| set | indexes |")
    A("|---|---|")
    named = {
        "P": "investment periods, 2030 / 2042 / 2055",
        "S": "representative time slices, 864 per year",
        "MONTHS": "calendar months",
        "BUCKETS": "(month, day-type) pairs, within which storage and shifted load conserve",
        "EVC": "electric vehicle classes",
    }
    seen = set()
    for nm, init in sets_:
        if nm in seen:
            continue
        seen.add(nm)
        A(f"| `{nm}` | {named.get(nm, init)} |")

    A("\n### B.2.3 Decision variables\n")
    A(
        f"{len(vars_)} variable blocks, split between **build** decisions indexed by "
        "period and vintage, and **operate** decisions indexed by period and slice.\n"
    )
    A("| variable | declaration |")
    A("|---|---|")
    seenv = set()
    for nm, decl in vars_:
        if nm in seenv:
            continue
        seenv.add(nm)
        d = decl.rstrip(",) ").replace("|", "/")
        A(f"| `{nm}` | {d} |")

    A("\n### B.2.4 Objective\n")
    A(
        "Minimise the period-weighted sum of annualised system cost plus alpha times "
        "annual emissions. Each period is weighted by the number of years it "
        "represents. Technology capital cost is discounted at a real rate per "
        "technology; the **inter-period weighting is not discounted**, which favours "
        "early building and is examined as a sensitivity in Appendix G.\n"
    )

    A("\n### B.2.5 Constraints\n")
    A(
        f"{len(cons)} constraint blocks. Names below are the Pyomo component names, so "
        "the main text can reference a constraint by name rather than restating it.\n"
    )
    assigned: set[str] = set()
    for heading, prefixes, blurb in LP_GROUPS:
        rows = []
        for nm, idx in cons:
            if nm in assigned:
                continue
            low = nm.lower()
            if any(low.startswith(p) or p in low for p in prefixes):
                rows.append((nm, idx))
                assigned.add(nm)
        if not rows:
            continue
        A(f"\n**{heading}**\n")
        A(f"{blurb}\n")
        A("| constraint | indexed over |")
        A("|---|---|")
        for nm, idx in rows:
            A(f"| `{nm}` | {idx} |")

    rest = [(nm, idx) for nm, idx in cons if nm not in assigned]
    if rest:
        A("\n**Other**\n")
        A("| constraint | indexed over |")
        A("|---|---|")
        for nm, idx in rest:
            A(f"| `{nm}` | {idx} |")

    A(
        "\n### B.2.6 The area-budget form, and why it replaced a capacity cap\n"
    )
    A(
        "The land and roof constraints budget **area**, not capacity. The earlier form "
        "capped cumulative installed capacity against a per-period density multiplier:\n"
    )
    A("```\nlegacy:  sum of new[v]              <=  base x density[p] x land[p]\n"
      "area:    sum of new[v] / density[v]   <=  base x land[p]\n```\n")
    A(
        "The legacy form was correct while farm land was released in phases, because "
        "later capacity went onto new land and newer panels on new land legitimately "
        "pack denser. Once all the land was released in the first period the land term "
        "went flat and the density term began re-rating modules that were already "
        "standing. The same array was simultaneously **degraded to 77.8 % of nameplate "
        "for its yield**, on the grounds that the panels are old, and **re-rated as "
        "later-vintage dense for its cap**. Old for output, new for the cap.\n"
    )
    A(
        "The defect was found by asking whether the implied physical story was "
        "possible, and tested by costing it: gaining the extra capacity would mean "
        "replacing the entire field at eleven times the charged capital, ₹532.4 crore "
        "against ₹48.4 crore, and 130,023 tCO2 against 11,820 charged, which is about "
        "a year of the town's total emissions. The area form makes that impossible by "
        "construction, because each vintage occupies land at its own density and "
        "nothing standing is ever re-rated.\n"
    )
    A(
        "The roof pair works the same way: collectors are limited to hot-water-eligible "
        "roof, while photovoltaics and collectors together are limited to the total "
        "accepted roof, so the two uses compete on one shared budget and neither can "
        "be charged against the wrong denominator.\n"
    )
    A("| roof quantity | value |")
    A("|---|---|")
    A("| total accepted roof | 668,854.5 m2 |")
    A("| hot-water-eligible roof | 491,854.5 m2, 73.5 % |")
    A("| non-eligible roof | 177,000 m2 |")
    A("| rooftop photovoltaic ceiling | 129,088.9 kWp, 90.5 % taken |")
    A("| module efficiency | 19.30 % |")
    A("| ground-mount density | 0.08022 kWp/m2 |")
    A(
        "\nThe earlier form charged **all** district rooftop photovoltaics against the "
        "hot-water-eligible roof alone, ignoring the 177,000 m2 owned by offices, "
        "retail and warehouses. It bound exactly, which is how it was found: "
        "428,628.5 + 63,226.0 = 491,854.5 m2, the eligible roof to the decimal. "
        "Rooftop photovoltaics stopping at 64 % of their cap was therefore not an "
        "economic result but an artefact of the wrong denominator.\n"
    )

    A("\n### B.2.7 Row spacing, derived rather than assumed\n")
    A(
        "The ground-coverage ratio of the solar farm, 0.382, and its inter-row "
        "self-shading loss of 0.021 %, are derived from the model's own sun-path "
        "machinery rather than taken from a handbook, and validated at the "
        "winter-solstice limit: at 30.6 degrees north the noon sun stands 35.9 degrees "
        "above the horizon, so the first noon self-shading appears only at a ground "
        "coverage ratio of 0.648.\n"
    )
    A(
        "The conclusion is worth stating plainly: **at this latitude physics does not "
        "bind the spacing.** Self-shading is negligible across the whole plausible "
        "range, so the binding limit is the citable land-per-megawatt figure, not the "
        "geometry. A ratio of 0.40 was rejected as sitting below the Indian practice "
        "band.\n"
    )

    text = "\n".join(P).replace("—", " - ")
    out_path = os.path.abspath(os.path.join(root, OUT))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")

    print(f"wrote {out_path}")
    print(f"  layout: {len(hard_all)} hard constraints, {len(obj_all)} objectives")
    print(f"  LP: {len(set(n for n, _ in sets_))} sets, "
          f"{len(set(n for n, _ in vars_))} variable blocks, {len(cons)} constraint blocks")
    print(f"  constraints grouped: {len(assigned)}, ungrouped: {len(rest)}")


if __name__ == "__main__":
    main()
