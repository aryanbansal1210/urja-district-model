"""Stage E one-page viva figure (SVG, no dependencies).

Reads LIVE outputs (dispatch_results.json, equity_report.json, owner_finance.json,
carbon_pareto.csv, fx2_6_b1_sweep.csv|md) and renders a single-page summary:
  A  who saves on BILLS (per-class % saving vs BAU)
  B  who earns as a PV INVESTOR (IRR bars + payback labels)
  C  the carbon-cost Pareto frontier (alpha = 0 -> 1)
  D  battery entry-price curve (B1 sweep: 2030 capex vs installed MWh per period)
  + a headline stats strip.
Re-run after any regen: python scripts/generate_stage_e_figure.py
Writes outputs/figures/stage_e_summary.svg
"""
from __future__ import annotations
import csv, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
OUT_DIR = os.path.join("outputs", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------- data ----------------
d = json.load(open("outputs/data/energy/dispatch_results.json", encoding="utf-8"))
sc = [s for s in d["scenarios"] if s.get("name") == "full_stack" and abs(s.get("alpha", 1)) < 1e-9][0]
bau = [s for s in d["scenarios"] if s.get("name") == "bau"][0]
eq = json.load(open("outputs/data/energy/equity_report.json", encoding="utf-8"))
ow = json.load(open("outputs/data/energy/owner_finance.json", encoding="utf-8"))

cost_m = sc["annual_cost_inr"] / 1e6
emis_kt = sc["annual_emissions_kgco2"] / 1e6
life_b = sc.get("lifetime_cost_inr", 0) / 1e9
ren = sc.get("renewable_share", 0) * 100
vs_cost = (sc["annual_cost_inr"] / bau["annual_cost_inr"] - 1) * 100
vs_emis = (sc["annual_emissions_kgco2"] / bau["annual_emissions_kgco2"] - 1) * 100
netkwh = sc.get("lcoe_inr_per_kwh", 0)

# A: bill savings by class. equity by_class: saving fraction = (bau_cost - eff_cost)/bau ~ use available fields
CLASS_LABELS = {"ews": "EWS (social tariff)", "mid_residential": "Mid-income res.",
                "high_residential": "High-income res.", "commercial_public": "Commercial/public",
                "industrial": "Industrial"}
bills = []
for cls, c in eq["by_class"].items():
    pct = c.get("savings_pct")
    if pct is not None:
        bills.append((CLASS_LABELS.get(cls, cls), float(pct) * (100 if abs(float(pct)) <= 1.5 else 1)))
bills.sort(key=lambda x: -x[1])

# B: investor IRR + payback
inv = []
for tier, t in ow["by_tier"].items():
    irr = t.get("irr"); pb = t.get("simple_payback_years")
    label = CLASS_LABELS.get(tier, tier)
    if irr is not None:
        inv.append((label, irr * 100, pb))
    else:
        inv.append((label + " (gov)", 0.0, None))
inv.sort(key=lambda x: -x[1])

# C: pareto
pareto = []
with open("outputs/data/energy/carbon_pareto.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            pareto.append((float(row["alpha"]), float(row["annual_cost_inr"]) / 1e6,
                           float(row["annual_emissions_kgco2"]) / 1e6))
        except (KeyError, ValueError):
            pass

# D: B1 sweep - CSV preferred, fall back to the md table
b1 = []
csv_p = "outputs/data/energy/fx2_6_b1_sweep.csv"
md_p = "outputs/data/energy/fx2_6_b1_sweep.md"
if os.path.exists(csv_p):
    for row in csv.DictReader(open(csv_p, encoding="utf-8")):
        b1.append((float(row["capex_2030_inr_per_kwh"]), float(row["battery_2030_kwh"]) / 1e3,
                   float(row["battery_2042_kwh"]) / 1e3, float(row["battery_2055_kwh"]) / 1e3))
elif os.path.exists(md_p):
    for line in open(md_p, encoding="utf-8"):
        m = re.match(r"\|\s*([\d,]+)(?:\s*\(base\))?\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", line)
        if m:
            b1.append((float(m.group(1).replace(",", "")), float(m.group(2)),
                       float(m.group(3)), float(m.group(4))))
b1.sort(key=lambda x: -x[0])

# ---------------- svg helpers ----------------
W, H = 1200, 850
parts = []
def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;")
def text(x, y, s, size=13, anchor="start", weight="normal", fill="#1a2733", opacity=1.0):
    parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
                 f'font-weight="{weight}" fill="{fill}" opacity="{opacity}" '
                 f'font-family="Segoe UI, Arial, sans-serif">{esc(s)}</text>')
def rect(x, y, w, h, fill, rx=2, opacity=1.0):
    parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" rx="{rx}" opacity="{opacity}"/>')
def line(x1, y1, x2, y2, stroke="#c9d4de", width=1, dash=""):
    dd = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{width}"{dd}/>')
def circle(x, y, r, fill):
    parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}"/>')
def polyline(pts, stroke, width=2.5, fill="none"):
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    parts.append(f'<polyline points="{p}" stroke="{stroke}" stroke-width="{width}" fill="{fill}" stroke-linejoin="round"/>')

parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
rect(0, 0, W, H, "#ffffff", rx=0)

# header
text(30, 40, "Stage E - who saves money, and how robust is the answer", 24, weight="bold")
text(30, 64, "district_v3 (Zirakpur-class 100k new town) - full_stack, cost-optimal dispatch", 13, fill="#5b6b7a")
stats = (f"Rs {cost_m:,.0f} M/yr   |   {emis_kt:.1f} kt CO2/yr   |   Rs {life_b:.1f} B lifetime   |   "
         f"{ren:.0f}% renewable   |   net Rs {netkwh:.2f}/kWh   |   vs BAU: {vs_cost:.0f}% cost, {vs_emis:.0f}% CO2")
rect(28, 76, W - 56, 34, "#f2f7fb", rx=6)
text(W / 2, 99, stats, 14, anchor="middle", weight="bold", fill="#0e4d92")

PAD_TOP = 140
PH = 320  # panel height
PW = 545  # panel width
GX1, GX2 = 30, 625

# ---- Panel A: bill savings ----
text(GX1, PAD_TOP - 8, "A. Bills: who saves vs business-as-usual", 15, weight="bold")
ax, ay, aw, ah = GX1 + 150, PAD_TOP + 10, PW - 190, PH - 60
maxv = max((v for _, v in bills), default=50) * 1.15
n = max(1, len(bills))
bh = min(34, ah / n - 10)
for i, (label, v) in enumerate(bills):
    y = ay + i * (ah / n) + (ah / n - bh) / 2
    text(ax - 8, y + bh / 2 + 4, label, 12, anchor="end")
    rect(ax, y, max(1, v / maxv * aw), bh, "#2E9E5B", rx=4)
    text(ax + v / maxv * aw + 6, y + bh / 2 + 4, f"{v:.0f}%", 12, weight="bold", fill="#2E9E5B")
line(ax, ay + ah, ax + aw, ay + ah)
text(ax + aw / 2, ay + ah + 22, "bill saving vs BAU (%)", 11, anchor="middle", fill="#5b6b7a")

# ---- Panel B: investor returns ----
text(GX2, PAD_TOP - 8, "B. Rooftop investment: who earns (IRR, payback)", 15, weight="bold")
bx, by, bw, bh2 = GX2 + 150, PAD_TOP + 10, PW - 190, PH - 60
maxirr = max((v for _, v, _ in inv), default=50) * 1.15 or 1
n2 = max(1, len(inv))
bbh = min(34, bh2 / n2 - 10)
for i, (label, irr, pb) in enumerate(inv):
    y = by + i * (bh2 / n2) + (bh2 / n2 - bbh) / 2
    text(bx - 8, y + bbh / 2 + 4, label, 12, anchor="end")
    if irr > 0:
        rect(bx, y, max(1, irr / maxirr * bw), bbh, "#0E7AC4", rx=4)
        lab = f"{irr:.0f}% IRR" + (f", {pb:.1f} yr payback" if pb else "")
        text(bx + irr / maxirr * bw + 6, y + bbh / 2 + 4, lab, 12, weight="bold", fill="#0E7AC4")
    else:
        rect(bx, y, 3, bbh, "#98a7b5", rx=1)
        text(bx + 10, y + bbh / 2 + 4, "gov-financed (social cost borne by state)", 11, fill="#5b6b7a")
line(bx, by + bh2, bx + bw, by + bh2)
text(bx + bw / 2, by + bh2 + 22, "internal rate of return (%)", 11, anchor="middle", fill="#5b6b7a")

# ---- Panel C: Pareto frontier ----
ROW2 = PAD_TOP + PH + 30
text(GX1, ROW2 - 8, "C. Carbon-cost frontier (alpha = carbon weight, 0 to 1)", 15, weight="bold")
cx, cy, cw, ch = GX1 + 70, ROW2 + 10, PW - 110, PH - 80
if pareto:
    e_lo = min(p[2] for p in pareto) * 0.95; e_hi = max(p[2] for p in pareto) * 1.05
    c_lo = min(p[1] for p in pareto) * 0.98; c_hi = max(p[1] for p in pareto) * 1.02
    def cxp(e): return cx + (e - e_lo) / (e_hi - e_lo) * cw
    def cyp(c): return cy + ch - (c - c_lo) / (c_hi - c_lo) * ch
    line(cx, cy + ch, cx + cw, cy + ch); line(cx, cy, cx, cy + ch)
    pts = sorted(((p[2], p[1], p[0]) for p in pareto))
    polyline([(cxp(e), cyp(c)) for e, c, _ in pts], "#C4472E")
    seen_alpha = set()
    for e, c, a in pts:
        circle(cxp(e), cyp(c), 4, "#C4472E")
        key = round(a, 2)
        if key in (0.0, 0.5, 0.8, 0.92, 1.0) and key not in seen_alpha:
            seen_alpha.add(key)
            text(cxp(e) + 6, cyp(c) - 8, f"a={a:g}", 11, fill="#C4472E")
    text(cx + cw / 2, cy + ch + 26, "annual emissions (kt CO2)", 11, anchor="middle", fill="#5b6b7a")
    text(cx - 46, cy + ch / 2, "cost (M Rs/yr)", 11, anchor="middle", fill="#5b6b7a")
    text(cx + cw / 2, cy + ch + 44,
         "flat to a~0.65: deep cuts are nearly free; the last third of CO2 costs +41% on bills",
         11, anchor="middle", fill="#8a5a00")

# ---- Panel D: battery entry ----
text(GX2, ROW2 - 8, "D. Battery entry vs 2030 capex (B1 switching point)", 15, weight="bold")
dx, dy, dw, dh = GX2 + 70, ROW2 + 10, PW - 110, PH - 80
if b1:
    x_lo = min(p[0] for p in b1) * 0.9; x_hi = max(p[0] for p in b1) * 1.05
    y_hi = max(max(p[1], p[2], p[3]) for p in b1) * 1.1 or 1
    def dxp(v): return dx + (x_hi - v) / (x_hi - x_lo) * dw   # capex decreasing to the right
    def dyp(v): return dy + dh - v / y_hi * dh
    line(dx, dy + dh, dx + dw, dy + dh); line(dx, dy, dx, dy + dh)
    series = [("2030", 1, "#0E7AC4"), ("2042", 2, "#7A4FC4"), ("2055", 3, "#C4472E")]
    for lab, idx, col in series:
        pts = [(dxp(p[0]), dyp(p[idx])) for p in sorted(b1, key=lambda r: -r[0])]
        polyline(pts, col)
        for p in b1: circle(dxp(p[0]), dyp(p[idx]), 3.5, col)
        text(pts[-1][0] + 6, pts[-1][1], lab, 12, weight="bold", fill=col)
    text(dx + dw / 2, dy + dh + 26, "2030 battery capex (Rs/kWh, decreasing ->)", 11, anchor="middle", fill="#5b6b7a")
    text(dx - 46, dy + dh / 2, "installed (MWh)", 11, anchor="middle", fill="#5b6b7a")
    text(dx + dw / 2, dy + dh + 44,
         "entry: 2055 at the base price; 2042 at ~Rs 7k; 2030 at ~Rs 4k/kWh - endogenous and price-steep",
         11, anchor="middle", fill="#8a5a00")

text(30, H - 14, "Generated by scripts/generate_stage_e_figure.py from live model outputs; re-run after any regen. Tier 3 (model results).",
     10, fill="#98a7b5")
parts.append("</svg>")

out = os.path.join(OUT_DIR, "stage_e_summary.svg")
open(out, "w", encoding="utf-8").write("\n".join(parts))
print(f"wrote {out}")
print(f"panels: bills={len(bills)} classes, investors={len(inv)} tiers, pareto={len(pareto)} pts, b1={len(b1)} pts")
