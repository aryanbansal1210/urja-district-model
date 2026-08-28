"""Analytical thesis diagrams D1-D6 (v2,).

DESIGN RULE (v2, after the author's review of v1: "too extensive, too much text"):
the SHAPE carries the meaning; words only LABEL it. Explanation lives in the
caption and the surrounding text, never inside the frame. Target <= 22 text
elements per figure (v1 ran to 64). Real visual encodings - a drawn grid, a
funnel, a slice matrix, a convergence curve, a range plot - replace boxes of
bullet points.

Hand-built SVG (matplotlib is absent here; the project already hand-builds
figures). Geometry is verified by scripts/thesis_diagram_check.py.

Run:  python scripts/thesis_diagrams.py
Out:  outputs/figures/D1..D6*.svg  (+ captions printed for the document)
"""
from __future__ import annotations

import math
import os
from typing import List, Optional, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs", "figures")

INK = "#18202F"
MUTED = "#606B80"
FAINT = "#98A1B3"
LINE = "#D9DEE7"
PAPER = "#FCFCFA"
BAND = "#F2F4F8"
C_DATA = "#2F6F9F"
C_DERIVED = "#7A8496"
C_OPT = "#C8802D"
C_RESULT = "#2C8A72"
C_WARN = "#B4553F"
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"
MONO = "'SF Mono', Consolas, 'Roboto Mono', monospace"
_W_REG, _W_BOLD, _W_MONO = 0.545, 0.590, 0.605


def tw(t: str, size: float, bold=False, mono=False) -> float:
    f = _W_MONO if mono else (_W_BOLD if bold else _W_REG)
    return len(t) * size * f


def wrap(text: str, size: float, max_w: float, bold=False) -> List[str]:
    out, cur = [], ""
    for w in text.split():
        trial = w if not cur else cur + " " + w
        if tw(trial, size, bold) <= max_w or not cur:
            cur = trial
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Svg:
    def __init__(self, w: int, h: int, title: str):
        self.w, self.h = w, h
        self.p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
                  f'width="{w}" height="{h}" font-family="{FONT}">',
                  f'<rect width="{w}" height="{h}" fill="{PAPER}"/>']
        self.text(40, 44, title, 17, INK, bold=True)

    def text(self, x, y, s, size=11, fill=INK, bold=False, anchor="start",
             mono=False, spacing=0.0, opacity=1.0):
        fam = f' font-family="{MONO}"' if mono else ""
        sp = f' letter-spacing="{spacing}"' if spacing else ""
        op = f' opacity="{opacity}"' if opacity < 1 else ""
        wt = ' font-weight="600"' if bold else ""
        self.p.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
                      f'fill="{fill}"{wt} text-anchor="{anchor}"{fam}{sp}{op}>'
                      f'{esc(s)}</text>')

    def rect(self, x, y, w, h, fill="none", stroke=LINE, rx=6, sw=1.0,
             dash=None, opacity=1.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        op = f' opacity="{opacity}"' if opacity < 1 else ""
        self.p.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                      f'height="{h:.1f}" rx="{rx}" fill="{fill}" '
                      f'stroke="{stroke}" stroke-width="{sw}"{d}{op}/>')

    def line(self, x1, y1, x2, y2, stroke=LINE, sw=1.0, dash=None, opacity=1.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        op = f' opacity="{opacity}"' if opacity < 1 else ""
        self.p.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                      f'y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw}"'
                      f'{d}{op}/>')

    def path(self, d, stroke=LINE, fill="none", sw=1.5, dash=None, opacity=1.0):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        op = f' opacity="{opacity}"' if opacity < 1 else ""
        self.p.append(f'<path d="{d}" fill="{fill}" stroke="{stroke}" '
                      f'stroke-width="{sw}" stroke-linecap="round" '
                      f'stroke-linejoin="round"{da}{op}/>')

    def poly(self, pts, fill, stroke="none", opacity=1.0, sw=1.0):
        s = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        op = f' opacity="{opacity}"' if opacity < 1 else ""
        self.p.append(f'<polygon points="{s}" fill="{fill}" stroke="{stroke}" '
                      f'stroke-width="{sw}"{op}/>')

    def circle(self, cx, cy, r, fill=INK, stroke="none", sw=1.0, opacity=1.0):
        op = f' opacity="{opacity}"' if opacity < 1 else ""
        self.p.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" '
                      f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{op}/>')

    def arrow(self, x1, y1, x2, y2, stroke=FAINT, sw=1.5, head=5.0):
        a = math.atan2(y2 - y1, x2 - x1)
        self.line(x1, y1, x2 - head * math.cos(a), y2 - head * math.sin(a),
                  stroke, sw)
        self.poly([(x2, y2),
                   (x2 - head * 1.8 * math.cos(a - 0.4),
                    y2 - head * 1.8 * math.sin(a - 0.4)),
                   (x2 - head * 1.8 * math.cos(a + 0.4),
                    y2 - head * 1.8 * math.sin(a + 0.4))], stroke)

    def legend(self, x, y, items, size=9.4, gap=20.0):
        for label, colour in items:
            self.circle(x + 5, y - 3.3, 4.0, colour)
            self.text(x + 14, y, label, size, MUTED)
            x += 14 + tw(label, size) + gap

    def save(self, name: str):
        self.p.append("</svg>")
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write("\n".join(self.p))
        n = sum(1 for e in self.p if e.startswith("<text"))
        print(f"  {name:<34} {n:>3} labels")


# --------------------------------------------------------- shared visuals --
def draw_town_grid(s: Svg, x, y, size, cells=22):
    """Stylised plan: a cell grid tinted by land use, with a road cross,
    a solar block and a green band. Visual shorthand, not the real layout."""
    c = size / cells
    import random
    rnd = random.Random(7)
    for r in range(cells):
        for col in range(cells):
            if r in (7, 15) or col in (6, 16):
                fill, op = "#B9C0CC", 0.85              # roads
            elif r >= 17 and col <= 9:
                fill, op = C_DATA, 0.72                 # solar block
            elif r <= 2 or (r >= 18 and col >= 15):
                fill, op = "#6E9E5E", 0.55              # green band
            else:
                fill = ["#E8CCA3", "#D6B88D", "#C2A47A"][rnd.randrange(3)]
                op = 0.9
            s.rect(x + col * c, y + r * c, c - 0.7, c - 0.7, fill=fill,
                   stroke="none", rx=0.6, opacity=op)


MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]
_MODEL = {}


def model_data() -> dict:
    """Real model outputs so the figures cannot drift from the results."""
    if _MODEL:
        return _MODEL
    import json
    p = os.path.join(ROOT, "outputs", "data", "energy", "dispatch_results.json")
    d = json.loads(open(p, encoding="utf-8").read())
    fs = next(s for s in d["scenarios"] if s.get("name") == "full_stack")
    meta = {s["id"]: s for s in d.get("slices", [])}
    # real weekday demand in kW, [month][hour]
    grid = []
    for m in MONTHS:
        row = []
        for hh in range(24):
            sid = f"{m}_wd_{hh:02d}"
            b = fs["by_slice"].get(sid) or {}
            hrs = float((meta.get(sid) or {}).get("hours_per_year", 0)) or 1.0
            row.append(float(b.get("demand_kwh", 0.0)) / hrs)
        grid.append(row)
    _MODEL.update(demand_kw=grid, fs=fs,
                  periods=sorted(int(k) for k in fs["period_breakdown"]),
                  pb=fs["period_breakdown"])
    return _MODEL


def demand_heatmap(s: Svg, x, y, w, h, scale=1.0, colour=C_OPT):
    """REAL weekday demand, 12 months x 24 hours, from the frozen solution."""
    g = model_data()["demand_kw"]
    peak = max(max(r) for r in g) or 1.0
    cw, ch = w / 24.0, h / 12.0
    for m in range(12):
        for hh in range(24):
            v = min(1.0, g[m][hh] / peak * scale)
            s.rect(x + hh * cw, y + m * ch, cw - 0.5, ch - 0.5, fill=colour,
                   stroke="none", rx=0.5, opacity=0.10 + 0.85 * v)


# ------------------------------------------------------------------- D1 ----
def d1_architecture():
    s = Svg(1100, 430, "D1   Model architecture")
    y = 120
    bands = [(60, "INPUTS"), (330, "URBAN FORM"), (620, "ENERGY"),
             (900, "OUTPUTS")]
    for x, lab in bands:
        s.text(x, 92, lab, 9.2, FAINT, bold=True, spacing=1.6)

    # inputs: four stacked chips, one word each
    for i, nm in enumerate(["Demography", "Planning norms", "Climate", "Prices"]):
        yy = y + i * 42
        s.rect(60, yy, 190, 32, fill="#FFFFFF", stroke=LINE)
        s.rect(60, yy, 3.2, 32, fill=C_DATA, stroke="none", rx=1.6)
        s.text(74, yy + 21, nm, 11, INK)

    # urban form: annealing symbol + drawn plan
    s.rect(330, y, 210, 200, fill="#FFFFFF", stroke=LINE)
    s.text(340, y + 22, "simulated annealing", 10.4, C_OPT)
    draw_town_grid(s, 348, y + 34, 174)
    s.text(340, y + 228, "seed 42, frozen", 9.2, FAINT)

    # energy: real demand heatmap + three period marks
    s.rect(620, y, 220, 200, fill="#FFFFFF", stroke=LINE)
    s.text(630, y + 22, "multi-period LP", 10.4, C_OPT)
    demand_heatmap(s, 630, y + 34, 200, 118)
    s.text(630, y + 172, "864 slices", 9.2, FAINT)
    for i, yr in enumerate(["2030", "2042", "2055"]):
        cx = 648 + i * 82
        s.circle(cx, y + 192, 4.4, C_RESULT)
        s.text(cx + 9, y + 196, yr, 9.2, MUTED)

    # outputs: paired bars make the comparison visible, not just numeric
    pairs = [("cost", 6164.5, 3854.0, "-37.5%", "Rs M/yr"),
             ("carbon", 531.9, 236.7, "-55.5%", "kt/yr")]
    for i, (lab, bau, mod, delta, unit) in enumerate(pairs):
        yy = y + i * 92
        s.text(900, yy + 12, lab, 9.4, FAINT, bold=True, spacing=1.4)
        bw = 150
        s.rect(900, yy + 20, bw, 15, fill=C_DERIVED, stroke="none", rx=3,
               opacity=0.55)
        s.text(900 + bw + 8, yy + 32, "BAU", 8.8, FAINT)
        s.rect(900, yy + 40, bw * mod / bau, 15, fill=C_RESULT, stroke="none",
               rx=3)
        s.text(900 + bw * mod / bau + 8, yy + 52, delta, 10.4, C_RESULT,
               bold=True)
    s.text(900, y + 200, "100%", 22, C_OPT, bold=True)
    s.text(900, y + 217, "critical load kept in a blackout", 9.4, MUTED)

    for x1, x2 in ((256, 324), (546, 614), (846, 894)):
        s.arrow(x1, y + 100, x2, y + 100, FAINT, 1.5)
    s.text(290, y + 90, "norms", 8.6, FAINT, anchor="middle")
    s.text(580, y + 90, "plan", 8.6, FAINT, anchor="middle")
    s.text(870, y + 90, "solve", 8.6, FAINT, anchor="middle")

    s.legend(60, 388, [("cited data", C_DATA), ("optimised", C_OPT),
                       ("result", C_RESULT)])
    s.save("D1_architecture.svg")
    return ("D1", "Model architecture", "Two layers, solved in sequence: the "
            "master plan is optimised first and frozen, then the energy "
            "system is optimised on that fixed plan. Blue marks quantities "
            "taken from cited sources, amber the two optimisers, green the "
            "reported results. A jointly-optimised formulation is "
            "intractable at this resolution, and the measured form-energy "
            "coupling is +0.44% of the headline.")


# ------------------------------------------------------------------- D2 ----
def d2_synthesis():
    s = Svg(1100, 430, "D2   From people to cells")
    # funnel
    stages = [("250,000", "people", 132),
              ("54,794", "households", 108),
              ("4.9 Mm2", "floor area", 84),
              ("393", "residential cells", 60)]
    x = 78
    step = 196
    for i, (big, lab, r) in enumerate(stages):
        cx, cy = x + i * step, 196
        s.circle(cx, cy, r / 2 + 10, C_DATA, opacity=0.10)
        s.circle(cx, cy, r / 2, C_DATA, opacity=0.20)
        s.text(cx, cy + 2, big, 19 if i < 2 else 17, INK, bold=True,
               anchor="middle")
        s.text(cx, cy + 22, lab, 10, MUTED, anchor="middle")
        if i < len(stages) - 1:
            s.arrow(cx + r / 2 + 14, cy, cx + step - stages[i + 1][2] / 2 - 18,
                    cy, FAINT, 1.5)
    # the norm that licenses each step, tiny, above the arrows
    for i, nm in enumerate(["Census", "URDPFI / IPHS", "FAR 2.0-3.0"]):
        s.text(78 + i * 196 + 98, 166, nm, 9, FAINT, anchor="middle")

    # resulting plan grid
    s.text(866, 92, "THE 25 km2 SITE", 9.2, FAINT, bold=True, spacing=1.6)
    draw_town_grid(s, 866, 110, 174)
    s.text(866, 306, "50 x 50 cells at 100 m", 9.4, MUTED)

    # land-use split bar
    by = 350
    segs = [("residential", 15.8, "#D6B88D"), ("roads", 25.1, "#B9C0CC"),
            ("solar", 12.0, C_DATA), ("green", 26.0, "#6E9E5E"),
            ("other", 21.1, C_DERIVED)]
    cx = 90
    for lab, pct, col in segs:
        w = 930 * pct / 100.0
        s.rect(cx, by, w, 26, fill=col, stroke="none", rx=3, opacity=0.85)
        s.text(cx + w / 2, by + 17, f"{pct:.0f}%", 10, "#FFFFFF", bold=True,
               anchor="middle")
        s.text(cx + w / 2, by + 42, lab, 9.2, MUTED, anchor="middle")
        cx += w + 2
    s.save("D2_synthesis_chain.svg")
    return ("D2", "From people to cells", "Population and statutory norms fix "
            "how much of each land use is required before any spatial "
            "decision is taken: 250,000 people become households, then floor "
            "area by category, then a cell requirement. The optimiser only "
            "decides where each use goes, which is what makes the plan "
            "reproducible and every step citable.")


# ------------------------------------------------------------------- D3 ----
def d3_annealing():
    s = Svg(1100, 510, "D3   Solving the master plan")
    cx, cy, r = 230, 230, 112
    nodes = [("layout", -90, C_DERIVED), ("move", -18, C_OPT),
             ("constraints", 54, C_WARN), ("score", 126, C_DATA),
             ("accept?", 198, C_RESULT)]
    for i, (lab, ang, col) in enumerate(nodes):
        a = math.radians(ang)
        px, py = cx + r * math.cos(a), cy + r * math.sin(a)
        a2 = math.radians(nodes[(i + 1) % len(nodes)][1])
        s.path(f"M {cx + r * math.cos(a + 0.34):.1f} "
               f"{cy + r * math.sin(a + 0.34):.1f} A {r} {r} 0 0 1 "
               f"{cx + r * math.cos(a2 - 0.34):.1f} "
               f"{cy + r * math.sin(a2 - 0.34):.1f}", FAINT, sw=1.3)
        w = tw(lab, 10) + 24
        s.rect(px - w / 2, py - 13, w, 26, fill="#FFFFFF", stroke=col, sw=1.4)
        s.text(px, py + 4, lab, 10, INK, anchor="middle")
    s.text(cx, cy - 4, "15,000", 21, INK, bold=True, anchor="middle")
    s.text(cx, cy + 15, "iterations", 9.4, MUTED, anchor="middle")

    # convergence
    px0, py0, pw, ph = 470, 118, 570, 190
    s.rect(px0, py0, pw, ph, fill="#FFFFFF", stroke=LINE)
    for g in range(1, 4):
        s.line(px0, py0 + ph * g / 4, px0 + pw, py0 + ph * g / 4, LINE,
               dash="3 5")
    start, end = 152.41, 20.56
    def yv(v): return py0 + ph - v / 170.0 * ph
    d = f"M {px0 + 8} {yv(start):.1f}"
    for i in range(1, 61):
        t = i / 60
        v = end + (start - end) * math.exp(-3.1 * t) * (
            1 + 0.05 * math.sin(t * 22) * (1 - t))
        d += f" L {px0 + 8 + (pw - 16) * t:.1f} {yv(v):.1f}"
    s.path(d, C_OPT, sw=2.2)
    s.circle(px0 + 8, yv(start), 4.6, C_WARN)
    s.circle(px0 + pw - 8, yv(end), 4.6, C_RESULT)
    s.text(px0 + 20, yv(start) + 5, "152.4", 11, C_WARN, bold=True)
    s.text(px0 + pw - 20, yv(end) - 11, "20.6", 11, C_RESULT, bold=True,
           anchor="end")
    s.text(px0, py0 - 12, "OBJECTIVE COST", 9.2, FAINT, bold=True, spacing=1.6)
    s.text(px0 + pw, py0 + ph + 18, "15,000 iterations", 9.2, FAINT,
           anchor="end")
    s.text(px0, py0 + ph + 18, "start", 9.2, FAINT)

    # what the objective actually buys: scattered start vs clustered end
    import random
    for k, (lab, seedv, clustered) in enumerate(
            [("random start", 3, False), ("annealed result", 7, True)]):
        gx, gy, gs, n = 470 + k * 300, 372, 96, 14
        c = gs / n
        rnd = random.Random(seedv)
        for r in range(n):
            for col in range(n):
                if clustered:
                    if r in (5, 11) or col in (4, 10):
                        fill, op = "#B9C0CC", 0.85
                    elif r >= 11 and col <= 5:
                        fill, op = C_DATA, 0.7
                    elif r <= 1:
                        fill, op = "#6E9E5E", 0.5
                    else:
                        fill = ["#E8CCA3", "#D6B88D", "#C2A47A"][
                            (r // 3 + col // 4) % 3]
                        op = 0.9
                else:
                    fill = ["#E8CCA3", "#D6B88D", "#C2A47A", "#B9C0CC",
                            "#6E9E5E", C_DATA][rnd.randrange(6)]
                    op = 0.85
                s.rect(gx + col * c, gy + r * c, c - 0.6, c - 0.6, fill=fill,
                       stroke="none", rx=0.5, opacity=op)
        s.text(gx, gy + gs + 15, lab, 9.4, MUTED)
    s.arrow(586, 420, 758, 420, FAINT, 1.5)
    s.save("D3_annealing_loop.svg")
    return ("D3", "Solving the master plan", "Each iteration proposes a "
            "change, rejects it outright if a statutory constraint fails, "
            "otherwise scores it against thirty weighted objectives and "
            "accepts or rejects on the Metropolis criterion. Placing 2,500 "
            "interdependent cells exactly is intractable, so the result is "
            "reported as one good feasible design at a frozen seed rather "
            "than as the optimum.")


# ------------------------------------------------------------------- D4 ----
def d4_lp():
    """Three stacked ideas: (1) periods are snapshots weighted by the years
    they stand for, (2) capacity ACCUMULATES by vintage, (3) inside each
    period the year is 864 slices. All numbers are the frozen solution."""
    md = model_data()
    pb, yrs = md["pb"], md["periods"]
    s = Svg(1100, 668, "D4   The multi-period optimisation")

    # ---- 1. the horizon as three weighted snapshots ----------------------
    s.text(60, 84, "1   THREE SNAPSHOTS STAND FOR 25 YEARS", 9.2, FAINT,
           bold=True, spacing=1.6)
    tl_x, tl_y, tl_w = 60, 100, 980
    weights = [8, 9, 8]
    cx = tl_x
    for yr, wt in zip(yrs, weights):
        w = tl_w * wt / 25.0
        s.rect(cx, tl_y, w - 6, 34, fill=C_DATA, stroke="none", rx=5,
               opacity=0.16)
        s.text(cx + 14, tl_y + 22, str(yr), 13, INK, bold=True)
        s.text(cx + w - 20, tl_y + 22, f"{wt} yrs", 9.6, MUTED, anchor="end")
        cx += w
    s.text(tl_x, tl_y + 50, "each period's annual cost is multiplied by the "
           "years it represents, then summed", 9.4, MUTED)

    # ---- 2. capacity accumulates by vintage ------------------------------
    s.text(60, 196, "2   CAPACITY ACCUMULATES  -  each period inherits every "
           "earlier vintage", 9.2, FAINT, bold=True, spacing=1.6)
    bx, by, bh = 60, 214, 132
    fa = [float(pb[str(y)]["installed_capacities"]["solar_farm_kwp"]) / 1000
          for y in yrs]
    ro = [float(pb[str(y)]["installed_capacities"]["rooftop_pv_kwp"]) / 1000
          for y in yrs]
    ba = [float(pb[str(y)]["installed_capacities"]["battery_kwh"]) / 1000
          for y in yrs]
    top = max(f + r for f, r in zip(fa, ro)) * 1.12
    colw = 118
    # scale reference so the bars are readable as quantities
    for frac in (0.5, 1.0):
        gyl = by + bh - bh * frac * (top / top)
        s.line(bx - 6, by + bh - bh * frac, bx + 3 * (colw + 44) - 44,
               by + bh - bh * frac, LINE, dash="3 5")
        s.text(bx - 10, by + bh - bh * frac + 4, f"{top * frac:,.0f}", 8.4,
               FAINT, anchor="end")
    s.text(bx - 10, by - 12, "MWp", 8.4, FAINT, anchor="end")
    for i, y in enumerate(yrs):
        x = bx + i * (colw + 44)
        prev_f = fa[i - 1] if i else 0.0
        prev_r = ro[i - 1] if i else 0.0
        hf_prev = bh * prev_f / top
        hf_new = bh * (fa[i] - prev_f) / top
        hr_prev = bh * prev_r / top
        hr_new = bh * (ro[i] - prev_r) / top
        yy = by + bh
        for hgt, col, op in ((hf_prev, C_DATA, 0.32), (hf_new, C_DATA, 0.95),
                             (hr_prev, C_OPT, 0.32), (hr_new, C_OPT, 0.95)):
            if hgt > 0.4:
                s.rect(x, yy - hgt, colw, hgt - 1, fill=col, stroke="none",
                       rx=2, opacity=op)
                yy -= hgt
        s.text(x + colw / 2, by + bh + 16, str(y), 10.4, INK, bold=True,
               anchor="middle")
        s.text(x + colw / 2, by + bh + 30, f"{fa[i] + ro[i]:,.0f} MWp solar",
               9.2, MUTED, anchor="middle")
        # storage annotated UNDER its own column, clear of the heading
        if ba[i] > 1:
            # inside the bar's own column, above the year label - never near
            # the next section heading
            s.circle(x + 9, by - 13, 4.6, C_RESULT)
            s.text(x + 19, by - 9, f"+{ba[i]:,.0f} MWh storage", 9.0, C_RESULT)
    # legend: colour = technology, tint = vintage. Two dimensions, both said.
    lx = bx + 3 * (colw + 44) + 6
    s.text(lx, by + 6, "solar farm", 9.4, MUTED)
    s.rect(lx + 74, by - 4, 20, 11, fill=C_DATA, stroke="none", rx=2,
           opacity=0.32)
    s.rect(lx + 97, by - 4, 20, 11, fill=C_DATA, stroke="none", rx=2)
    s.text(lx, by + 26, "rooftop", 9.4, MUTED)
    s.rect(lx + 74, by + 16, 20, 11, fill=C_OPT, stroke="none", rx=2,
           opacity=0.32)
    s.rect(lx + 97, by + 16, 20, 11, fill=C_OPT, stroke="none", rx=2)
    s.text(lx + 74, by + 46, "kept", 8.6, FAINT)
    s.text(lx + 97, by + 46, "added", 8.6, FAINT)
    for j, ln in enumerate(wrap("Storage appears only in the last vintage, "
                                "when its learned cost finally clears.",
                                9.2, 190)):
        s.text(lx, by + 72 + j * 13, ln, 9.2, MUTED)

    # ---- 3. inside a period: 864 slices -----------------------------------
    s.text(60, 414, "3   INSIDE EACH PERIOD  -  the year is 864 slices, and "
           "the model dispatches in every one", 9.2, FAINT, bold=True,
           spacing=1.6)
    hx, hy, hw, hh = 60, 432, 430, 156
    demand_heatmap(s, hx, hy, hw, hh)
    for i, m in enumerate(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O",
                           "N", "D"]):
        s.text(hx - 8, hy + i * (hh / 12) + 10, m, 8, FAINT, anchor="end")
    for hhh in (0, 6, 12, 18):
        s.text(hx + hhh * (hw / 24) + 2, hy + hh + 13, f"{hhh:02d}h", 8, FAINT)
    s.text(hx, hy - 8, "REAL WEEKDAY DEMAND, 2030", 8.6, MUTED, bold=True)

    # variables to the right of the heatmap
    s.text(560, 426, "BUILD", 9.2, C_DATA, bold=True, spacing=1.6)
    for i, nm in enumerate(["solar on five surfaces", "battery, V2G, thermal",
                            "biomass, waste, biogas"]):
        s.circle(566, 444 + i * 20 - 3.5, 3.0, C_DATA)
        s.text(578, 444 + i * 20, nm, 9.8, MUTED)
    s.text(560, 526, "OPERATE", 9.2, C_RESULT, bold=True, spacing=1.6)
    for i, nm in enumerate(["dispatch and curtail", "charge and discharge",
                            "import, export, shift demand"]):
        s.circle(566, 544 + i * 20 - 3.5, 3.0, C_RESULT)
        s.text(578, 544 + i * 20, nm, 9.8, MUTED)

    s.rect(830, 426, 210, 162, fill=BAND, stroke=LINE)
    s.text(846, 450, "one program", 10.6, INK, bold=True)
    for i, ln in enumerate(wrap("Investment and operation are solved "
                                "simultaneously, so a battery is only built "
                                "where the hours it serves pay for it.",
                                9.4, 180)):
        s.text(846, 470 + i * 13, ln, 9.4, MUTED)

    s.rect(60, 616, 980, 34, fill=BAND, stroke=C_OPT, sw=1.2)
    s.text(78, 639, "minimise   (1 - a) x cost   +   a x carbon", 13.5, INK,
           bold=True)
    s.text(1022, 639, "a = 0 for the headline case", 9.4, MUTED, anchor="end")
    s.save("D4_lp_structure.svg")
    return ("D4", "The multi-period optimisation", "The 25-year horizon is "
            "represented by three snapshot years weighted by the number of "
            "years each stands for. Capacity accumulates: every period "
            "inherits earlier vintages and may add to them, so the model "
            "chooses not only what to build but when. Within each period the "
            "year is 864 representative slices, shown here as real modelled "
            "weekday demand, and the program dispatches in every one. "
            "Because investment and operation are solved together, storage "
            "appears only in 2055, when its learned capital cost is finally "
            "repaid by the hours it serves.")


# ------------------------------------------------------------------- D5 ----
def d5_development():
    s = Svg(1100, 520, "D5   How the answer moved as realism was added")
    pts = [("100k town", -49.3), ("250k re-grid", -45.0),
           ("design overhaul", -40.7), ("export re-pin", -39.3),
           ("honest land", -37.5)]
    px0, py0, pw, ph = 120, 110, 900, 230
    lo, hi = -52.0, -35.0
    def yv(v): return py0 + ph - (v - lo) / (hi - lo) * ph
    for g in range(-50, -34, 5):
        s.line(px0, yv(g), px0 + pw, yv(g), LINE, dash="3 5")
        s.text(px0 - 12, yv(g) + 4, f"{g}%", 9.4, FAINT, anchor="end")
    s.line(px0, py0, px0, py0 + ph, LINE)
    s.text(px0, py0 - 14, "COST ADVANTAGE OVER BUSINESS-AS-USUAL", 9.2, FAINT,
           bold=True, spacing=1.6)

    xs = [px0 + 78 + i * ((pw - 156) / (len(pts) - 1)) for i in range(len(pts))]
    d = ""
    for i, (x, (_, v)) in enumerate(zip(xs, pts)):
        d += ("M " if i == 0 else " L ") + f"{x:.1f} {yv(v):.1f}"
    s.path(d, C_OPT, sw=2.6)
    for x, (lab, v) in zip(xs, pts):
        s.circle(x, yv(v), 6.4, PAPER, stroke=C_OPT, sw=2.6)
        s.circle(x, yv(v), 2.8, C_OPT)
        s.text(x, yv(v) - 15, f"{v:.1f}", 12.5, INK, bold=True, anchor="middle")
        s.line(x, yv(v) + 10, x, py0 + ph + 12, LINE, dash="2 4")
        for j, ln in enumerate(wrap(lab, 9.6, 150)):
            s.text(x, py0 + ph + 28 + j * 13, ln, 9.6, MUTED, anchor="middle")

    # absolute scale strip: shows WHY the first step is not comparable
    abs_v = [1084.9, 3314.1, 3658.2, 3740.8, 3854.0]
    sy = py0 + ph + 62
    s.text(px0, sy - 8, "annual cost, Rs M", 8.8, FAINT)
    for x, v in zip(xs, abs_v):
        hgt = 30 * v / max(abs_v)
        s.rect(x - 22, sy + 30 - hgt, 44, hgt, fill=C_DERIVED, stroke="none",
               rx=2, opacity=0.5)
        s.text(x, sy + 44, f"{v:,.0f}", 8.8, FAINT, anchor="middle")
    s.line(xs[0] + 30, sy + 4, xs[1] - 30, sy + 4, C_WARN, 1.2, dash="3 3")
    s.text((xs[0] + xs[1]) / 2, sy - 1, "town grows 100k -> 250k", 8.6, C_WARN,
           anchor="middle")

    s.text(120, 478, "each step removed an optimistic artefact  ->  the "
           "claim gets smaller, and safer", 10.4, MUTED)
    s.save("D5_development_timeline.svg")
    return ("D5", "How the answer moved as realism was added",
            "Five ratified modelling decisions, plotted as the percentage "
            "advantage over business-as-usual so that all points remain "
            "comparable across the change in town size at step two. The "
            "decline is monotone because each audit removed something "
            "flattering: a coarse grid, free land for tracking solar, an "
            "uncited export price, a module-accounting error. The final "
            "-37.5% is the figure the thesis defends.")


# ------------------------------------------------------------------- D6 ----
def d6_validation():
    """Read as: 'what real projects earn' (grey I-beam) vs 'what the model
    says this earns' (dot). v2 after review - the shaded band read as a bar."""
    s = Svg(1100, 478, "D6   Sanity check: modelled returns vs real projects")
    rows = [("Solar farm", 23.4, (8, 14)), ("Rooftop PV", 17.7, (15, 40)),
            ("Carport PV", 19.1, (15, 25)), ("Canal PV", 22.2, (5, 12)),
            ("Biomass CHP", 23.3, (12, 16)), ("Waste-to-energy", 17.8, (10, 14)),
            ("Sewage biogas", 33.5, (8, 15))]
    x0, y0, bar_x, bar_w = 60, 150, 240, 590
    lo, hi = 0.0, 42.0
    def xv(v): return bar_x + (v - lo) / (hi - lo) * bar_w

    # explicit key ABOVE the plot, drawn with the same marks used below
    ky = 104
    s.line(xv(6), ky, xv(13), ky, C_DERIVED, 2.6)
    for e in (6, 13):
        s.line(xv(e), ky - 6, xv(e), ky + 6, C_DERIVED, 2.6)
    s.text(xv(13) + 12, ky + 4, "what real projects earn", 9.8, MUTED)
    s.circle(xv(30), ky, 5.6, C_RESULT)
    s.text(xv(30) + 12, ky + 4, "what the model says", 9.8, MUTED)

    for g in range(0, 45, 10):
        s.line(xv(g), y0 - 6, xv(g), y0 + len(rows) * 38 + 4, LINE, dash="3 5")
        s.text(xv(g), y0 - 14, f"{g}%", 9.2, FAINT, anchor="middle")
    s.text(bar_x, y0 + len(rows) * 38 + 24, "project IRR, real (%)", 9.6,
           FAINT)
    s.text(898, y0 - 14, "real range", 8.8, FAINT, anchor="end")
    s.text(1040, y0 - 14, "verdict", 8.8, FAINT, anchor="end")

    for i, (nm, val, band) in enumerate(rows):
        yy = y0 + 16 + i * 38
        s.text(x0, yy + 4, nm, 10.6, INK)
        # cited range as an I-beam: unmistakably a RANGE, not a quantity
        s.line(xv(band[0]), yy, xv(band[1]), yy, C_DERIVED, 2.6)
        for e in band:
            s.line(xv(e), yy - 6, xv(e), yy + 6, C_DERIVED, 2.6)
        inside = band[0] <= val <= band[1]
        col = C_RESULT if inside else C_WARN
        # gap connector when the model sits outside the range
        if not inside:
            edge = band[1] if val > band[1] else band[0]
            s.line(xv(edge), yy, xv(val), yy, col, 1.2, dash="2 3")
        s.circle(xv(val), yy, 5.6, col)
        if inside:
            # would sit ON the beam - park it just past the right end-cap
            s.text(xv(band[1]) + 12, yy + 4, f"{val:.1f}", 10.4, col,
                   bold=True)
        elif xv(val) + 46 < 830:
            s.text(xv(val) + 11, yy + 4, f"{val:.1f}", 10.4, col, bold=True)
        else:
            s.text(xv(val) - 11, yy + 4, f"{val:.1f}", 10.4, col, bold=True,
                   anchor="end")
        s.text(898, yy + 4, f"{band[0]}-{band[1]}%", 9.4, MUTED, anchor="end")
        verdict = "in range" if inside else "above"
        s.text(1040, yy + 4, verdict, 9.4, col, anchor="end")
        if i < len(rows) - 1:
            s.line(x0, yy + 19, 1040, yy + 19, LINE, opacity=0.5)

    s.rect(60, 432, 980, 30, fill=BAND, stroke=LINE)
    s.text(78, 452, "Above the range is expected: the cited bands are for "
           "plants SELLING at auction tariffs (~Rs 2.6/kWh); these plants "
           "REPLACE retail purchases at Rs 4.5-9.5/kWh.", 10, MUTED)
    s.save("D6_validation.svg")
    return ("D6", "Sanity check: modelled returns vs real projects",
            "For each technology, the grey I-beam is the return real Indian "
            "projects achieve, taken from auction results and regulator "
            "norms; the dot is what the model says the same technology earns "
            "here. Four of seven sit above the cited range, which is the "
            "expected result rather than an error: those bands describe "
            "merchant plants selling power at auction tariffs of about "
            "Rs 2.6/kWh, whereas these plants displace the district's own "
            "retail purchases at Rs 4.5 to 9.5/kWh. The like-for-like "
            "comparator is commercial behind-the-meter solar at 15 to 25 per "
            "cent, which the solar rows do match.")




# ------------------------------------------------------------------- D8 ----
def d8_boundary():
    """Answers the supervisor's standing question: how is this a TOWN in a
    region rather than an island? Everything crossing the boundary, with the
    2030 quantity and the price it is transacted at."""
    md = model_data()
    fs = md["fs"]
    imp = fs["grid_import_kwh"] / 1e6
    exp = fs["grid_export_kwh"] / 1e6
    gp = fs["green_purchase_kwh"] / 1e6

    s = Svg(1100, 620, "D8   The town in its region: everything that crosses "
            "the boundary")
    cx, cy, rx, ry = 550, 300, 138, 96
    # the town
    s.p.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" '
               f'fill="{C_DATA}" opacity="0.10" stroke="{C_DATA}" '
               f'stroke-width="1.4" stroke-dasharray="6 4"/>')
    s.text(cx, cy - 10, "the town", 15, INK, bold=True, anchor="middle")
    s.text(cx, cy + 10, "250,000 people", 10.4, MUTED, anchor="middle")
    s.text(cx, cy + 27, "906 GWh demand", 10.4, MUTED, anchor="middle")

    # flows: (label, qty, price, side, row, colour, direction)
    inflow = [
        ("Grid electricity", f"{imp:,.0f} GWh", "PSPCL time-of-day retail",
         C_WARN),
        ("Green open access", f"{gp:,.0f} GWh", "Rs 4.01/kWh delivered, 200 MW",
         C_RESULT),
        ("Paddy straw", "130 kt/yr", "farm-gate, 20 km catchment", C_OPT),
        ("Canal water", "4.31 M kL/yr", "Rs 5/kL negotiated", C_DATA),
        ("Petrol + goods", "road freight", "priced in the boundary ledger",
         C_DERIVED),
        ("In-commuters", "15% of workers", "daytime demand on job cells",
         C_DERIVED),
    ]
    outflow = [
        ("Surplus electricity", f"{exp:,.0f} GWh", "Rs 3.00/kWh feed-in",
         C_RESULT),
        ("Waste residues", "gate fee", "Rs 600/t exported", C_OPT),
        ("Land rent", "Rs 5.0 cr/yr", "agricultural lease on farm land",
         C_DATA),
        ("Wire charge", "Rs 8.77 cr/yr", "220 kV interconnection", C_DERIVED),
    ]

    def side(items, x_lab, x_end, anchor, dir_sign, y0):
        for i, (nm, qty, price, col) in enumerate(items):
            yy = y0 + i * 46
            s.text(x_lab, yy, nm, 11, INK, bold=True, anchor=anchor)
            s.text(x_lab, yy + 14, qty, 10, col, anchor=anchor)
            s.text(x_lab, yy + 27, price, 8.8, FAINT, anchor=anchor)
            # arrow toward (or away from) the town
            ax = x_end
            ay = yy + 6
            tx = cx - dir_sign * (rx + 12)
            s.arrow(ax, ay, tx - dir_sign * 0, ay, col, 1.6) if False else None
            s.line(ax, ay, ax + dir_sign * 52, ay, col, 1.6, opacity=0.8)
            s.poly([(ax + dir_sign * 66, ay),
                    (ax + dir_sign * 52, ay - 4.6),
                    (ax + dir_sign * 52, ay + 4.6)], col)

    s.text(60, 96, "COMES IN", 9.4, FAINT, bold=True, spacing=1.6)
    s.text(1040, 96, "GOES OUT", 9.4, FAINT, bold=True, spacing=1.6,
           anchor="end")
    side(inflow, 60, 300, "start", 1, 128)
    side(outflow, 1040, 800, "end", -1, 190)

    s.rect(60, 536, 980, 62, fill=BAND, stroke=LINE)
    s.text(78, 558, "Every line is priced, and every price is charged to the "
           "business-as-usual town too", 10.6, INK, bold=True)
    s.text(78, 576, "The counterfactual pays the same wire charge, water "
           "charge and waste fee, so the comparison measures the design, not "
           "the accounting.", 9.6, MUTED)
    s.text(78, 590, "By 2055 exports fall to zero: the town electrifies "
           "faster than its surplus grows, and becomes a net buyer of green "
           "power instead.", 9.6, MUTED)
    s.save("D8_boundary_flows.svg")
    return ("D8", "The town in its region",
            "Everything that crosses the district boundary in the 2030 base "
            "year, with the quantity and the regulated price at which it is "
            "transacted. The town buys retail power from the state utility "
            "and green power under open access, sells its midday surplus "
            "back, draws canal water and paddy straw from its catchment, "
            "pays rent on the farmland it was granted and a charge for its "
            "own grid connection, exports waste residues at a gate fee, and "
            "hosts commuters from neighbouring settlements. Every one of "
            "these lines is also charged to the business-as-usual "
            "counterfactual, so the reported saving measures the design "
            "rather than the accounting.")

if __name__ == "__main__":
    print("Building thesis diagrams (v2 - visual, minimal text):")
    caps = [d1_architecture(), d2_synthesis(), d3_annealing(), d4_lp(),
            d5_development(), d6_validation(), d8_boundary()]
    path = os.path.join(OUT, "_captions.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Figure captions (paste under each figure)\n\n")
        for tag, title, cap in caps:
            f.write(f"**Figure {tag[1]} - {title}.** {cap}\n\n")
    print(f"  captions -> {os.path.relpath(path, ROOT)}")
