"""Analytic text-fit / overlap check for a generated.pptx.

LibreOffice is not installed here, so slides cannot be rendered for visual QA.
This does the same job arithmetically: it unpacks the deck, reads every shape's
position, size and text runs, estimates wrapped line count from font metrics,
and reports (a) text that overflows its box, (b) shapes that fall outside the
slide, (c) overlapping text boxes.

Conservative by design: character widths are over-estimated so a "fits" verdict
has margin. Same principle as scripts/thesis_diagram_check.py.

Run: python scripts/pptx_fit_check.py deck.pptx
"""
from __future__ import annotations

import sys
import zipfile
from xml.dom import minidom

EMU_IN = 914400.0
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
# width of an average glyph as a fraction of font size, per family
WFRAC = {"Cambria": 0.50, "Calibri": 0.478, "Arial": 0.525, None: 0.50}


def _txt(node) -> str:
    return "".join(n.data for n in node.childNodes if n.nodeType == n.TEXT_NODE)


def shapes(doc):
    """Yield dicts for every shape carrying text."""
    for sp in doc.getElementsByTagNameNS(
            "http://schemas.openxmlformats.org/presentationml/2006/main", "sp"):
        off = sp.getElementsByTagNameNS(A, "off")
        ext = sp.getElementsByTagNameNS(A, "ext")
        if not off or not ext:
            continue
        x = int(off[0].getAttribute("x")) / EMU_IN
        y = int(off[0].getAttribute("y")) / EMU_IN
        w = int(ext[0].getAttribute("cx")) / EMU_IN
        h = int(ext[0].getAttribute("cy")) / EMU_IN
        paras = []
        for p in sp.getElementsByTagNameNS(A, "p"):
            runs = []
            for r in p.getElementsByTagNameNS(A, "r"):
                rpr = r.getElementsByTagNameNS(A, "rPr")
                sz = None, None
                size = 18.0
                face = None
                if rpr:
                    s = rpr[0].getAttribute("sz")
                    if s:
                        size = int(s) / 100.0
                    lat = rpr[0].getElementsByTagNameNS(A, "latin")
                    if lat:
                        face = lat[0].getAttribute("typeface")
                ts = r.getElementsByTagNameNS(A, "t")
                text = "".join(_txt(t) for t in ts)
                if text:
                    runs.append((text, size, face))
            if runs:
                paras.append(runs)
        # explicit line breaks count as paragraph splits
        brs = len(sp.getElementsByTagNameNS(A, "br"))
        if paras:
            yield dict(x=x, y=y, w=w, h=h, paras=paras, brs=brs)


def est_height(shape) -> float:
    """Estimated rendered text height in inches (wrap-aware)."""
    total = 0.0
    inner_w = max(0.05, shape["w"] - 0.20)      # default text inset ~0.1" a side
    for runs in shape["paras"]:
        px = sum(len(t) * sz * WFRAC.get(f, 0.50) / 72.0 for t, sz, f in runs)
        big = max(sz for _, sz, _ in runs)
        lines = max(1, int(px / inner_w) + (1 if px % inner_w else 0))
        total += lines * (big * 1.22 / 72.0)
    total += shape["brs"] * 0.02
    return total


def main(path: str) -> int:
    z = zipfile.ZipFile(path)
    names = sorted((n for n in z.namelist()
                    if n.startswith("ppt/slides/slide") and n.endswith(".xml")),
                   key=lambda s: int("".join(c for c in s if c.isdigit())))
    SW, SH = 13.333, 7.5
    issues_total = 0
    for n in names:
        doc = minidom.parseString(z.read(n))
        sps = list(shapes(doc))
        issues = []
        for s in sps:
            need = est_height(s)
            if need > s["h"] + 0.06:
                first = s["paras"][0][0][0][:44]
                issues.append(f"OVERFLOW  '{first}'  needs {need:.2f}\" in "
                              f"{s['h']:.2f}\" box")
            if (s["x"] < -0.02 or s["y"] < -0.02
                    or s["x"] + s["w"] > SW + 0.02
                    or s["y"] + s["h"] > SH + 0.02):
                first = s["paras"][0][0][0][:40]
                issues.append(f"OFF-SLIDE '{first}'  box "
                              f"{s['x']:.2f},{s['y']:.2f} -> "
                              f"{s['x']+s['w']:.2f},{s['y']+s['h']:.2f}")
        for i in range(len(sps)):
            for j in range(i + 1, len(sps)):
                a, b = sps[i], sps[j]
                ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
                # compare against ESTIMATED text height, not box height, so a
                # tall empty box does not read as a collision
                ah, bh = min(a["h"], est_height(a)), min(b["h"], est_height(b))
                oy = min(a["y"] + ah, b["y"] + bh) - max(a["y"], b["y"])
                if ox > 0.05 and oy > 0.05:
                    issues.append(
                        f"OVERLAP   '{a['paras'][0][0][0][:26]}' x "
                        f"'{b['paras'][0][0][0][:26]}'  ({ox:.2f}x{oy:.2f}\")")
        issues_total += len(issues)
        num = "".join(c for c in n if c.isdigit())
        print(f"slide {num:>2}  {len(sps):>2} text shapes  "
              f"{'OK' if not issues else str(len(issues)) + ' ISSUES'}")
        for s in issues:
            print("      " + s)
    print(f"\nTOTAL ISSUES: {issues_total}")
    return 1 if issues_total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
