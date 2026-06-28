# OneLP — Capstone (AI Document-Intelligence & Portfolio Forecasting for Limited Partners)

Proof-of-concept evaluation of the OneLP platform's two core data-science contributions: a
hybrid **document-extraction pipeline** and a **Monte Carlo cash-flow forecasting engine**.

**👉 Written report:** [`reports/OneLP-Capstone-Written-Report.pdf`](reports/OneLP-Capstone-Written-Report.pdf)
(editable Word: [`.docx`](reports/OneLP-Capstone-Written-Report.docx))

**👉 Notebooks (executed, viewable in-browser):**
- [Deliverable 1 — Extraction Accuracy](notebooks/deliverable-1-extraction-accuracy.ipynb)
- [Deliverable 2 — Forecasting & Backtest](notebooks/deliverable-2-forecasting-backtest.ipynb)
- [Deliverable 3 — Pipeline & Model Analysis](notebooks/deliverable-3-pipeline-analysis.ipynb)

## Headline results

| # | Deliverable | Target | Result |
|---|---|---|---|
| 1 | Extraction accuracy (F1) | ≥ 0.90 / critical ≥ 0.95 | **0.968 / 0.968** ✅ |
| 2 | Cash-flow forecast (MAE) | < 15% | **5.0%** ✅ |
| 3 | End-to-end latency | P50 < 30s / P95 < 90s | **24s / 29s** ✅ (ECE 0.056) |

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./build.sh        # regenerates datasets, metrics, figures, notebooks, reports, slides
```

Everything is deterministic (fixed seeds). Individual deliverables:
`python deliverable-*/run_*.py`.

## Layout

```
reports/     written report (.docx/.pdf) + per-deliverable reports + build scripts
notebooks/   3 executed analysis notebooks
lib/onelp_eval/   shared toolkit — mc_engine.py (port of the production Monte Carlo engine),
                  extraction_eval.py (F1 / confusion matrix), portfolio.py, plotting.py
data/        labeled extraction test set + predictions + calibrated portfolio (with DATASET_CARDs)
deliverable-1/2/3/   run scripts · results (JSON) · figures (PNG)
slides/      venture-capstone pitch deck + technical deep-dive deck
```

## Data ethics

No real pilot-client data or PII is used. The extraction test set is a **synthetic, labelled
corpus** modelled on the project's golden fixtures; the forecasting study uses a **calibrated
reference portfolio** anchored on seeded demo accounts, not confidential holdings. Results from
simulated/calibrated processes are labelled as such and accompanied by a transparent account of
limitations. See the Ethics Statement on the cover page of the written report.

---

*MSc in Business Analytics & Big Data — IE School of Science & Technology · Venture Capstone · June 2026
· Kishan Dhulashia · Max Vanderlinden · Sofia Mollon · Agustin Gentil*
