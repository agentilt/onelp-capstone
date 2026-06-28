#!/usr/bin/env python3
"""
Render the capstone reports to DOCX and PDF.

Pipeline:  Markdown --(pandoc)--> DOCX --(LibreOffice headless)--> PDF

Produces, per deliverable, REPORT.docx + REPORT.pdf in its own folder, and a single
combined `OneLP-Capstone-POC-Deliverables.{docx,pdf}` in reports/.

No LaTeX required (LibreOffice does the PDF step).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

PANDOC = shutil.which("pandoc")
SOFFICE = (shutil.which("soffice")
           or ("/Applications/LibreOffice.app/Contents/MacOS/soffice"
               if Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").exists() else None))

DELIVERABLES = [
    ("deliverable-1-extraction-accuracy", "REPORT.md", "Deliverable-1-Extraction-Accuracy"),
    ("deliverable-2-forecasting-backtest", "REPORT.md", "Deliverable-2-Forecasting-Backtest"),
    ("deliverable-3-pipeline-analysis", "REPORT.md", "Deliverable-3-Pipeline-Analysis"),
]


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def md_to_docx(md_path: Path, docx_path: Path, resource_dir: Path):
    # No --toc: LibreOffice's headless PDF export does not refresh the TOC field,
    # which leaves an empty "Table of Contents" in the PDF.
    run([PANDOC, str(md_path), "-o", str(docx_path), "--resource-path", str(resource_dir)])


def docx_to_pdf(docx_path: Path, out_dir: Path):
    if not SOFFICE:
        print("  [warn] LibreOffice not found — skipping PDF for", docx_path.name)
        return None
    run([SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)])
    return out_dir / (docx_path.stem + ".pdf")


def build_combined():
    """Concatenate the executive summary + 3 reports with absolute image paths."""
    parts = []
    summary = (HERE / "00-EXECUTIVE-SUMMARY.md").read_text()
    contents = (
        "\n\n## Contents\n\n"
        "1. Executive Summary & Synthesis\n"
        "2. Deliverable 1 — Document Extraction Accuracy\n"
        "3. Deliverable 2 — Cash-Flow Forecasting with Backtesting\n"
        "4. Deliverable 3 — Pipeline & Model Analysis\n"
    )
    # insert the manual contents right after the summary's front matter + H1
    parts.append(summary + contents)
    for d, fname, _ in DELIVERABLES:
        dd = ROOT / d
        text = (dd / fname).read_text()
        # strip the per-file YAML front matter (keep only the first one, from summary)
        text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
        # rewrite relative figure paths to absolute so the combined doc resolves them
        text = text.replace("](figures/", f"]({dd}/figures/")
        parts.append("\n\n\\newpage\n\n" + text)
    combined_md = HERE / "_combined.md"
    combined_md.write_text("\n\n".join(parts))
    docx = HERE / "OneLP-Capstone-POC-Deliverables.docx"
    run([PANDOC, str(combined_md), "-o", str(docx),
         "--metadata", "title=OneLP Capstone — Proof-of-Concept Deliverables"])
    pdf = docx_to_pdf(docx, HERE)
    combined_md.unlink(missing_ok=True)
    return docx, pdf


def main():
    if not PANDOC:
        sys.exit("pandoc not found — install pandoc to render reports.")
    print(f"pandoc: {PANDOC}")
    print(f"soffice: {SOFFICE or 'NOT FOUND (PDF will be skipped)'}")

    for d, fname, outname in DELIVERABLES:
        dd = ROOT / d
        md = dd / fname
        docx = dd / "REPORT.docx"
        md_to_docx(md, docx, dd)
        pdf = docx_to_pdf(docx, dd)
        print(f"  {d}: {docx.name}" + (f" + {pdf.name}" if pdf else ""))

    docx, pdf = build_combined()
    print(f"  combined: {docx.name}" + (f" + {pdf.name}" if pdf else ""))

    # Standalone deliverables checklist
    chk = HERE / "DELIVERABLES-CHECKLIST.md"
    if chk.exists():
        cdocx = HERE / "DELIVERABLES-CHECKLIST.docx"
        md_to_docx(chk, cdocx, HERE)
        cpdf = docx_to_pdf(cdocx, HERE)
        print(f"  checklist: {cdocx.name}" + (f" + {cpdf.name}" if cpdf else ""))
    print("Reports done.")


if __name__ == "__main__":
    main()
