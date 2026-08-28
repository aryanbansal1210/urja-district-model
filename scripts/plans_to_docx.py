"""Render the two thesis-plan markdown documents to editable Word files.

Uses Word's BUILT-IN styles (Title, Heading 1/2/3, List Bullet) rather than
direct formatting, so the documents behave properly when edited: the
navigation pane works, headings collapse, and restyling the whole document
is a single style change. Word budgets are kept as normal text so they can
be edited or deleted freely.

Run:  python scripts/plans_to_docx.py
Out:  outputs/THESIS_PLAN_CONCISE.docx, outputs/THESIS_PLAN_DETAILED.docx
"""
from __future__ import annotations

import os
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "_spec")
OUT = os.path.join(ROOT, "outputs")

INK = RGBColor(0x18, 0x20, 0x2F)
MUTED = RGBColor(0x44, 0x4F, 0x66)
FAINT = RGBColor(0x8A, 0x93, 0xA6)
AMBER = RGBColor(0xA8, 0x68, 0x1C)


def add_runs(par, text: str, base_colour=MUTED, base_size=10.5):
    """Emit **bold**, *italic* and figure callouts as separate runs."""
    token = re.compile(r"(\*\*.+?\*\*|\*[^*]+?\*|Figures? D\d(?:, D\d)*)")
    for piece in token.split(text):
        if not piece:
            continue
        run = par.add_run()
        if piece.startswith("**") and piece.endswith("**"):
            run.text = piece[2:-2]
            run.bold = True
            run.font.color.rgb = INK
        elif piece.startswith("*") and piece.endswith("*"):
            run.text = piece[1:-1]
            run.italic = True
            run.font.color.rgb = FAINT
        elif piece.startswith("Figure"):
            run.text = piece
            run.italic = True
            run.font.color.rgb = AMBER
        else:
            run.text = piece
            run.font.color.rgb = base_colour
        run.font.size = Pt(base_size)


def build(md_path: str, docx_path: str) -> None:
    lines = open(md_path, encoding="utf-8").read().splitlines()
    doc = Document()

    # page setup + a readable body default
    for s in doc.sections:
        s.left_margin = s.right_margin = Pt(58)
        s.top_margin = s.bottom_margin = Pt(52)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(4)

    title_done = sub_done = False
    for raw in lines:
        t = raw.rstrip()
        if not t.strip() or t.startswith("---"):
            continue

        if t.startswith("# ") and not title_done:
            p = doc.add_paragraph(t[2:].strip(), style="Title")
            title_done = True
            continue
        if t.startswith("### ") and title_done and not sub_done:
            p = doc.add_paragraph(style="Subtitle")
            add_runs(p, t[4:].strip(), base_colour=MUTED, base_size=13)
            sub_done = True
            continue
        if t.startswith("**Target") or t.startswith("**20,000"):
            p = doc.add_paragraph()
            add_runs(p, t, base_colour=FAINT, base_size=9.5)
            continue
        if t.startswith("## "):
            doc.add_paragraph(re.sub(r"\*\*", "", t[3:]).strip(),
                              style="Heading 1")
            continue
        if t.startswith("### "):
            doc.add_paragraph(re.sub(r"\*\*|\*", "", t[4:]).strip(),
                              style="Heading 2")
            continue
        # bold-only line = a sub-subsection heading
        if t.startswith("**") and t.count("**") >= 2 and len(t) < 130 \
                and not t.lstrip().startswith("- "):
            p = doc.add_paragraph(style="Heading 3")
            add_runs(p, t, base_colour=INK, base_size=11)
            continue
        if t.startswith("*") and t.endswith("*"):
            p = doc.add_paragraph()
            add_runs(p, t, base_colour=FAINT, base_size=10)
            continue
        if t.lstrip().startswith("- "):
            depth = (len(t) - len(t.lstrip())) // 2
            style = "List Bullet" if depth == 0 else f"List Bullet {min(depth+1,3)}"
            try:
                p = doc.add_paragraph(style=style)
            except KeyError:
                p = doc.add_paragraph(style="List Bullet")
            add_runs(p, t.lstrip()[2:])
            continue
        p = doc.add_paragraph()
        add_runs(p, t)

    doc.core_properties.author = "Aryan Bansal"
    doc.core_properties.title = "Thesis plan"
    doc.save(docx_path)
    print(f"  -> {os.path.relpath(docx_path, ROOT)}")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    print("Rendering thesis plans to Word:")
    build(os.path.join(SPEC, "THESIS_PLAN_CONCISE.md"),
          os.path.join(OUT, "THESIS_PLAN_CONCISE.docx"))
    build(os.path.join(SPEC, "THESIS_PLAN_DETAILED.md"),
          os.path.join(OUT, "THESIS_PLAN_DETAILED.docx"))
