"""Render the two thesis-plan markdown documents to PDF.

No LibreOffice or pandoc in this environment, so this lays the documents out
directly with reportlab: A4, serif headings, generous margins, word budgets
right-aligned, figure callouts picked out in the accent colour.

Run:  python scripts/plans_to_pdf.py
Out:  outputs/THESIS_PLAN_CONCISE.pdf, outputs/THESIS_PLAN_DETAILED.pdf
"""
from __future__ import annotations

import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                PageTemplate, Paragraph, Spacer)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "_spec")
OUT = os.path.join(ROOT, "outputs")

INK = colors.HexColor("#18202F")
MUTED = colors.HexColor("#54607A")
FAINT = colors.HexColor("#8A93A6")
AMBER = colors.HexColor("#B0701F")
RULE = colors.HexColor("#D9DEE7")

BODY = ParagraphStyle("body", fontName="Times-Roman", fontSize=9.6,
                      leading=13.4, textColor=MUTED, alignment=TA_LEFT,
                      spaceAfter=2.2)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=11, bulletIndent=2,
                        spaceAfter=2.6)
H1 = ParagraphStyle("h1", fontName="Times-Bold", fontSize=15, leading=19,
                    textColor=INK, spaceBefore=13, spaceAfter=5)
H2 = ParagraphStyle("h2", fontName="Times-Bold", fontSize=11, leading=15,
                    textColor=INK, spaceBefore=8, spaceAfter=3)
H3 = ParagraphStyle("h3", fontName="Times-Bold", fontSize=9.8, leading=13.6,
                    textColor=INK, spaceBefore=6, spaceAfter=2.4)
TITLE = ParagraphStyle("title", fontName="Times-Bold", fontSize=19, leading=23,
                       textColor=INK, spaceAfter=3)
SUB = ParagraphStyle("sub", fontName="Times-Italic", fontSize=11.2,
                     leading=15, textColor=MUTED, spaceAfter=3)
META = ParagraphStyle("meta", fontName="Helvetica", fontSize=8.6, leading=12,
                      textColor=FAINT, spaceAfter=12)
NOTE = ParagraphStyle("note", fontName="Times-Italic", fontSize=9.2,
                      leading=12.8, textColor=FAINT, spaceAfter=4)


def inline(s: str) -> str:
    """Markdown inline -> reportlab markup."""
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    # figure callouts in the accent colour
    s = re.sub(r"(Figures? D\d(?:, D\d)*)",
               r'<font color="#B0701F">\1</font>', s)
    # word budgets: keep them quiet
    s = re.sub(r"\((\d{3,4})\)$", r'<font color="#8A93A6">(\1 words)</font>', s)
    s = re.sub(r"— ([\d,]+)$", r'<font color="#B0701F">\1 words</font>', s)
    return s


def build(md_path: str, pdf_path: str, subtitle_note: str = "") -> None:
    raw = open(md_path, encoding="utf-8").read().splitlines()
    story = []
    title = sub = None
    for ln in raw:
        t = ln.rstrip()
        if not t.strip():
            continue
        if t.startswith("---"):
            continue
        if t.startswith("# ") and title is None:
            title = t[2:].strip()
            continue
        if t.startswith("### ") and sub is None and title and not story:
            sub = t[4:].strip()
            continue
        if t.startswith("**Target") or t.startswith("**20,000"):
            story.append(Paragraph(inline(t.strip("*")), META))
            continue
        if t.startswith("## "):
            story.append(Paragraph(inline(t[3:]), H1))
            continue
        if t.startswith("### "):
            story.append(Paragraph(inline(t[4:]), H2))
            continue
        if t.startswith("**") and t.endswith("**") and len(t) < 110:
            story.append(Paragraph(inline(t.strip("*")), H3))
            continue
        if t.startswith("**") and "**" in t[2:]:
            story.append(Paragraph(inline(t), H3))
            continue
        if t.startswith("*") and t.endswith("*") and not t.startswith("**"):
            story.append(Paragraph(inline(t.strip("*")), NOTE))
            continue
        if t.lstrip().startswith("- "):
            depth = (len(t) - len(t.lstrip())) // 2
            st = ParagraphStyle(f"b{depth}", parent=BULLET,
                                leftIndent=11 + depth * 12,
                                bulletIndent=2 + depth * 12)
            story.append(Paragraph(inline(t.lstrip()[2:]), st,
                                   bulletText="•"))
            continue
        story.append(Paragraph(inline(t), BODY))

    doc = BaseDocTemplate(pdf_path, pagesize=A4,
                          leftMargin=21 * mm, rightMargin=21 * mm,
                          topMargin=19 * mm, bottomMargin=17 * mm,
                          title=title or "Thesis plan", author="Aryan Bansal")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="f", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)

    def deco(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.6)
        canvas.setFillColor(FAINT)
        canvas.drawString(d.leftMargin, 11 * mm,
                          "Integrated Optimisation of Urban Form and Energy "
                          "- Aryan Bansal")
        canvas.drawRightString(d.pagesize[0] - d.rightMargin, 11 * mm,
                               str(canvas.getPageNumber()))
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(d.leftMargin, 14 * mm,
                    d.pagesize[0] - d.rightMargin, 14 * mm)
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=deco)])
    head = []
    if title:
        head.append(Paragraph(inline(title), TITLE))
    if sub:
        head.append(Paragraph(inline(sub), SUB))
    if subtitle_note:
        head.append(Paragraph(subtitle_note, META))
    head.append(Spacer(1, 3))
    doc.build(head + story)
    print(f"  -> {os.path.relpath(pdf_path, ROOT)}")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    print("Rendering thesis plans to PDF:")
    build(os.path.join(SPEC, "THESIS_PLAN_CONCISE.md"),
          os.path.join(OUT, "THESIS_PLAN_CONCISE.pdf"))
    build(os.path.join(SPEC, "THESIS_PLAN_DETAILED.md"),
          os.path.join(OUT, "THESIS_PLAN_DETAILED.pdf"))
