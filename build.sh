#!/usr/bin/env bash
# Build every capstone deliverable end-to-end: datasets -> metrics -> figures ->
# notebooks -> reports (PDF) -> combined report -> slide deck.
#
# Usage:  ./build.sh            (uses ../capstone_venv if present, else `python3`)
set -euo pipefail
cd "$(dirname "$0")"

PY="../capstone_venv/bin/python"
[ -x "$PY" ] || PY="python3"
echo "Using interpreter: $PY"

echo "==> 1/7  Build labeled extraction dataset + predictions"
$PY data/build_dataset.py

echo "==> 2/7  Deliverable 1 — extraction accuracy"
$PY deliverable-1-extraction-accuracy/run_eval.py

echo "==> 3/7  Deliverable 2 — forecasting + backtest"
$PY deliverable-2-forecasting-backtest/run_backtest.py

echo "==> 4/7  Deliverable 3 — pipeline & model analysis"
$PY deliverable-3-pipeline-analysis/run_analysis.py

echo "==> 5/7  Build Jupyter notebooks"
$PY notebooks/build_notebooks.py

echo "==> 6/7  Render reports to PDF + combined report (pandoc)"
$PY reports/build_reports.py

echo "==> 7/8  Build technical deep-dive deck (pptx)"
$PY slides/build_deck.py

echo "==> 8/8  Build Venture Capstone pitch deck (pptx)"
$PY slides/build_venture_deck.py

echo "Done. See reports/ and slides/ for final artifacts."
echo "  Primary pitch : slides/OneLP-Venture-Capstone-Pitch.pdf"
echo "  Tech deep-dive: slides/OneLP-Capstone-Deliverables.pdf"
echo "  Combined report: reports/OneLP-Capstone-POC-Deliverables.pdf"
