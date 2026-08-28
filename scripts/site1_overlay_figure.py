"""SITE-1 overlay figure - the notional 5x5 km study square on the
Zirakpur-Banur corridor. DEPENDENCY-FREE (hand-written SVG + KML, house style).

Two outputs (register row SITE-1; spec _spec/SITE_1_GMADA_SITE_INTEGRATION.md):
  1. outputs/figures/site1_corridor_schematic.svg - self-drawn labelled schematic
     (no third-party imagery; interim thesis figure).
  2. outputs/figures/site1_model_square.kml - the EXACT geojson square + macro
     feature markers, for a Google Earth / QGIS satellite composite.

The square is read LIVE from optimised_sa.geojson metadata (single source of
truth); macro features are approximate public-map label positions (Tier 4,
labelling only - see the spec's source table).
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GEOJSON = os.path.join(ROOT, "outputs", "geojson3d", "optimised_sa.geojson")
OUTDIR = os.path.join(ROOT, "outputs", "figures")

# Approximate public-map label positions (lon, lat) - Tier 4, labels only.
FEATURES = {
    "Zirakpur (NH-5 x NH-7)": (76.817, 30.643),
    "Banur": (76.719, 30.554),
    "Chandigarh Intl Airport": (76.788, 30.673),
    "GMADA Aerocity (PR-7)": (76.783, 30.647),
    "Mohali / SAS Nagar": (76.718, 30.705),
    "Chandigarh": (76.782, 30.741),
}
# Stylised corridor polylines (lon, lat) - schematic alignment, labels only.
ROADS = [
    ("NH-7 (Zirakpur-Banur-Rajpura)", "#8a5a2b", 3.2,
     [(76.830, 30.660), (76.817, 30.643), (76.780, 30.610), (76.745, 30.575),
      (76.719, 30.554), (76.690, 30.520)]),
    ("NH-5", "#8a5a2b", 2.2,
     [(76.850, 30.630), (76.817, 30.643), (76.790, 30.680), (76.782, 30.720)]),
    ("PR-7 Airport Road", "#2b6a8a", 2.6,
     [(76.817, 30.643), (76.800, 30.648), (76.783, 30.652), (76.788, 30.668)]),
]

# View window (lon/lat) and canvas.
LON0, LON1 = 76.66, 76.88
LAT0, LAT1 = 30.48, 30.76
W = 900
# lat degrees are 1/0.860 "wider" than lon degrees at 30.64 N
ASPECT = 1.0 / 0.860
H = int(W * (LAT1 - LAT0) / (LON1 - LON0) * ASPECT)


def x(lon: float) -> float:
    return (lon - LON0) / (LON1 - LON0) * W


def y(lat: float) -> float:
    return H - (lat - LAT0) / (LAT1 - LAT0) * H


def main() -> None:
    os.makedirs(OUTDIR, exist_ok=True)
    with open(GEOJSON, encoding="utf-8") as f:
        md = json.load(f)["metadata"]
    w_, s_, e_, n_ = md["bounds"]  # lon_min, lat_min, lon_max, lat_max
    cx = md["center"]["longitude"]
    cy = md["center"]["latitude"]

    p = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H + 70}" '
             f'viewBox="0 0 {W} {H + 70}" font-family="Segoe UI, Arial, sans-serif">')
    p.append(f'<rect width="{W}" height="{H + 70}" fill="#fbfaf7"/>')
    # light graticule every 0.05 deg
    lon = 76.70
    while lon < LON1:
        p.append(f'<line x1="{x(lon):.1f}" y1="0" x2="{x(lon):.1f}" y2="{H}" '
                 f'stroke="#e3e0d8" stroke-width="1"/>')
        p.append(f'<text x="{x(lon):.1f}" y="{H + 14}" font-size="10" fill="#8a8778" '
                 f'text-anchor="middle">{lon:.2f}E</text>')
        lon += 0.05
    lat = 30.50
    while lat < LAT1:
        p.append(f'<line x1="0" y1="{y(lat):.1f}" x2="{W}" y2="{y(lat):.1f}" '
                 f'stroke="#e3e0d8" stroke-width="1"/>')
        p.append(f'<text x="4" y="{y(lat) - 3:.1f}" font-size="10" '
                 f'fill="#8a8778">{lat:.2f}N</text>')
        lat += 0.05
    # roads
    for label, colour, width, line in ROADS:
        pts = " ".join(f"{x(a):.1f},{y(b):.1f}" for a, b in line)
        p.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" '
                 f'stroke-width="{width}" stroke-linecap="round" opacity="0.85"/>')
        mx, my = line[len(line) // 2]
        p.append(f'<text x="{x(mx) + 6:.1f}" y="{y(my) - 6:.1f}" font-size="11" '
                 f'fill="{colour}">{label}</text>')
    # the model square (exact geojson bounds)
    p.append(f'<rect x="{x(w_):.1f}" y="{y(n_):.1f}" width="{x(e_) - x(w_):.1f}" '
             f'height="{y(s_) - y(n_):.1f}" fill="#d43a3a" fill-opacity="0.16" '
             f'stroke="#d43a3a" stroke-width="3"/>')
    p.append(f'<text x="{x(cx):.1f}" y="{y(cy) - 10:.1f}" font-size="12" fill="#7a1414" '
             f'text-anchor="middle" font-weight="bold">Study district (notional)</text>')
    p.append(f'<text x="{x(cx):.1f}" y="{y(cy) + 6:.1f}" font-size="10.5" fill="#7a1414" '
             f'text-anchor="middle">25 km2 - 50x50 x 100 m</text>')
    p.append(f'<text x="{x(cx):.1f}" y="{y(cy) + 21:.1f}" font-size="10.5" fill="#7a1414" '
             f'text-anchor="middle">centre 30.64 N 76.82 E</text>')
    # feature markers
    for name, (fx, fy) in FEATURES.items():
        p.append(f'<circle cx="{x(fx):.1f}" cy="{y(fy):.1f}" r="4.5" fill="#333"/>')
        p.append(f'<text x="{x(fx) + 8:.1f}" y="{y(fy) - 6:.1f}" font-size="11.5" '
                 f'fill="#222">{name}</text>')
    # 5 km scale bar (1 deg lon ~ 95.8 km at 30.64 N)
    km5 = 5.0 / 95.8
    bx0, bx1, by = x(76.70), x(76.70 + km5), y(30.505)
    p.append(f'<line x1="{bx0:.1f}" y1="{by:.1f}" x2="{bx1:.1f}" y2="{by:.1f}" '
             f'stroke="#111" stroke-width="4"/>')
    p.append(f'<text x="{(bx0 + bx1) / 2:.1f}" y="{by - 7:.1f}" font-size="11" '
             f'text-anchor="middle" fill="#111">5 km</text>')
    # title + caveat
    p.append(f'<text x="{W / 2:.0f}" y="{H + 34}" font-size="13" text-anchor="middle" '
             f'fill="#222" font-weight="bold">SITE-1: the notional study district on the '
             f'Zirakpur-Banur corridor (GMADA, SAS Nagar, Punjab)</text>')
    p.append(f'<text x="{W / 2:.0f}" y="{H + 52}" font-size="10.5" text-anchor="middle" '
             f'fill="#666">Schematic - macro features at approximate label positions '
             f'(Tier 4, labels only); red square = exact model geojson bounds. '
             f'Satellite composite: open site1_model_square.kml in Google Earth.</text>')
    p.append('</svg>')

    svg_path = os.path.join(OUTDIR, "site1_corridor_schematic.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(p))
    print(f"wrote {svg_path}")

    # ---- 2. KML ----
    kml_points = "".join(
        f"""
  <Placemark><name>{name}</name>
    <Point><coordinates>{fx},{fy},0</coordinates></Point></Placemark>"""
        for name, (fx, fy) in FEATURES.items())
    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <name>SITE-1 model square (district_v3)</name>
  <Style id="sq"><LineStyle><color>ff3a3ad4</color><width>3</width></LineStyle>
    <PolyStyle><color>2e3a3ad4</color></PolyStyle></Style>
  <Placemark><name>Study district (notional 25 km2)</name><styleUrl>#sq</styleUrl>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>
      {w_},{s_},0 {e_},{s_},0 {e_},{n_},0 {w_},{n_},0 {w_},{s_},0
    </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>{kml_points}
</Document></kml>
"""
    kml_path = os.path.join(OUTDIR, "site1_model_square.kml")
    with open(kml_path, "w", encoding="utf-8") as f:
        f.write(kml)
    print(f"wrote {kml_path}")


if __name__ == "__main__":
    main()
