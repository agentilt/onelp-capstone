#!/usr/bin/env python3
"""
Build the capstone WRITTEN REPORT to the program spec:
  - 12-point Times New Roman, 1.0 (single) line spacing
  - Cover page WITH an ethics statement
  - 10-20 pages
  - Editable Word (.docx) + PDF

Pipeline: assemble markdown -> pandoc (styled reference.docx) -> .docx -> LibreOffice -> .pdf
Run:  python build_written_report.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # capstone/
PANDOC = shutil.which("pandoc")
SOFFICE = shutil.which("soffice") or "/Applications/LibreOffice.app/Contents/MacOS/soffice"

REPO_URL = "https://github.com/agentilt/onelp-capstone"
FIG_WIDTH = "4.0in"            # default embedded-figure width (tune to hit page budget)
# figures to omit from the written report to stay within 20 pages (kept in the repo/notebooks)
DROP_FIGURES = {
    "accuracy_latency.png", "per_field_f1.png",          # D1 (keep engine_comparison, confusion, by_type)
    "sensitivity_tornado.png", "liquidity_reserve.png",  # D2 (keep fan, backtest, stress, correlation)
    "calibration_by_category.png", "confidence_by_correctness.png",  # D3 (keep reliability, threshold, latency)
}

DELIVERABLES = [
    ("deliverable-1-extraction-accuracy", "REPORT.md"),
    ("deliverable-2-forecasting-backtest", "REPORT.md"),
    ("deliverable-3-pipeline-analysis", "REPORT.md"),
]

COVER = f"""\
# OneLP: AI Document-Intelligence and Portfolio-Forecasting for Limited Partners

**Capstone Written Report — Proof-of-Concept Evaluation**

**Authors:** Kishan Dhulashia · Max Vanderlinden · Sofia Mollon · Agustin Gentil

**Programme:** MSc in Business Analytics & Big Data — IE School of Science & Technology (Venture Capstone)

**Date:** June 2026

**Code & notebooks:** {REPO_URL}

---

### Ethics Statement

This capstone was conducted in accordance with responsible data-science and AI practices.
**No real pilot-client data or personally identifiable information was used in any evaluation.**
The document-extraction test set is a synthetic, labelled corpus modelled on the project's own
golden fixtures and schemas; the forecasting study uses a **calibrated reference portfolio**
anchored on seeded demo accounts rather than confidential client holdings. Results derived from
simulated or calibrated processes are explicitly labelled as such throughout, are distinguished
from production behaviour, and are accompanied by a transparent account of limitations
(calibration, cross-asset correlation fallback, cold-start, and generalisation across document
formats). The underlying system retains a **human-in-the-loop review queue** for low-confidence
extractions, so automated outputs never drive financial decisions without verification, and every
extracted field keeps source-linked evidence for auditability. All metrics are computed from first
principles with **deterministic, openly available code** to ensure reproducibility, and no claim is
made beyond what the evaluation measures. The authors affirm that this work is their own and that
all external sources and tools are duly acknowledged.
"""


def make_reference_docx(out: Path):
    """Generate pandoc's default reference.docx and restyle to TNR 12pt single-spaced."""
    subprocess.run([PANDOC, "--print-default-data-file", "reference.docx"],
                   stdout=open(out, "wb"), check=True)
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn
    doc = Document(str(out))
    BLACK = RGBColor(0, 0, 0)

    def set_font(style, size=None, bold=None):
        f = style.font
        f.name = "Times New Roman"
        f.color.rgb = BLACK   # black headings/body (override pandoc's blue heading default)
        # ensure the East-Asian/complex slots also use TNR
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = rpr.makeelement(qn("w:rFonts"), {})
            rpr.append(rfonts)
        for a in ("w:ascii", "w:hAnsi", "w:cs"):
            rfonts.set(qn(a), "Times New Roman")
        if size is not None:
            f.size = Pt(size)
        if bold is not None:
            f.bold = bold
        pf = style.paragraph_format
        pf.line_spacing = 1.0

    for st in doc.styles:
        try:
            if st.type is not None and st.name and st.font is not None:
                set_font(st, size=12)
        except Exception:
            pass
    # headings / title bigger
    for name, size in [("Title", 18), ("Heading 1", 15), ("Heading 2", 13),
                       ("Heading 3", 12), ("Normal", 12), ("Body Text", 12)]:
        try:
            set_font(doc.styles[name], size=size, bold=(name != "Normal" and name != "Body Text"))
        except Exception:
            pass
    doc.save(str(out))


def load_body(name, fname):
    d = ROOT / name
    text = (d / fname).read_text()
    text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)   # strip YAML
    # drop selected figures
    lines = []
    for ln in text.splitlines():
        m = re.match(r"!\[.*\]\(figures/([^)]+)\)", ln.strip())
        if m and m.group(1) in DROP_FIGURES:
            continue
        lines.append(ln)
    text = "\n".join(lines)
    # absolute figure paths + width
    text = re.sub(r"\]\(figures/([^)]+)\)", rf"]({d}/figures/\1){{width={FIG_WIDTH}}}", text)
    return text


def main():
    if not PANDOC:
        sys.exit("pandoc required")
    ref = HERE / "_reference.docx"
    make_reference_docx(ref)

    parts = [COVER, "\n\\newpage\n"]
    summary = (HERE / "00-EXECUTIVE-SUMMARY.md").read_text()
    summary = re.sub(r"^---\n.*?\n---\n", "", summary, count=1, flags=re.DOTALL)
    parts.append(summary)
    for name, fname in DELIVERABLES:
        parts.append("\n\\newpage\n")
        parts.append(load_body(name, fname))
    combined = HERE / "_written_report.md"
    combined.write_text("\n\n".join(parts))

    docx = HERE / "OneLP-Capstone-Written-Report.docx"
    subprocess.run([PANDOC, str(combined), "-o", str(docx),
                    "--reference-doc", str(ref), "--resource-path", str(HERE)],
                   check=True)
    # PDF via LibreOffice
    if Path(SOFFICE).exists() or shutil.which("soffice"):
        subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", str(HERE), str(docx)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    combined.unlink(missing_ok=True)
    ref.unlink(missing_ok=True)

    pdf = HERE / "OneLP-Capstone-Written-Report.pdf"
    pages = "?"
    try:
        out = subprocess.run(["mdls", "-name", "kMDItemNumberOfPages", str(pdf)],
                             capture_output=True, text=True).stdout
        pages = out.split("=")[-1].strip()
    except Exception:
        pass
    print(f"  {docx.name}  (editable Word)")
    print(f"  {pdf.name}  ({pages} pages)")
    print("Written report built.")


if __name__ == "__main__":
    main()
