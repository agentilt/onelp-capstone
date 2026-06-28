#!/usr/bin/env python3
"""
Build (and execute) the three capstone analysis notebooks with nbformat.

Each notebook is self-contained and runnable: it puts capstone/lib on the path,
runs / loads the deliverable's results, renders tables with pandas, embeds the
figures, and includes a short live demo of the underlying production-ported code.

Output: notebooks/deliverable-{1,2,3}-*.ipynb  (executed, with outputs embedded)
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def md(t):
    return new_markdown_cell(t)


def code(t):
    return new_code_cell(t)


SETUP = """\
import sys, json
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path('%s')
sys.path.insert(0, str(ROOT / 'lib'))
import numpy as np, pandas as pd
from IPython.display import Image, display
pd.set_option('display.float_format', lambda v: f'{v:,.3f}')
print('capstone root:', ROOT)
""" % ROOT


def nb_d1():
    nb = new_notebook()
    d = ROOT / "deliverable-1-extraction-accuracy"
    nb.cells = [
        md("# Deliverable 1 — Document Extraction Accuracy\n\n"
           "Implements proposal **Metric 1 (F1)** and **POC Deliverable 1**: macro F1, "
           "critical-field F1, document-type confusion matrix, and the "
           "**Document AI vs LLM vs Hybrid** comparison.\n\n"
           "Field matching mirrors the repository harness `calculateExtractionAccuracy` "
           "(`tests/eval/validators.ts`), extended to be numeric-aware for money/dates."),
        code(SETUP),
        md("## 1. Load metrics\nRe-run `run_eval.py` first if `results/` is empty."),
        code("res = json.load(open(ROOT/'deliverable-1-extraction-accuracy'/'results'/'extraction_metrics.json'))\n"
             "summary = pd.DataFrame(res['summary']).T[['macro_f1','critical_field_f1','micro_f1','latency_p50','latency_p95']]\n"
             "summary.index = ['Document AI only','LLM only','Hybrid (merged)']\n"
             "summary"),
        md("**Hybrid is the only engine clearing both targets** (macro ≥ 0.90, critical ≥ 0.95)."),
        code("display(Image(str(ROOT/'deliverable-1-extraction-accuracy'/'figures'/'engine_comparison.png')))"),
        md("## 2. Per-field F1 — the complementary failure modes\n"
           "Document AI wins on structured/critical fields; the LLM wins on narrative; "
           "hybrid takes the better source per field."),
        code("display(Image(str(ROOT/'deliverable-1-extraction-accuracy'/'figures'/'per_field_f1.png')))"),
        md("## 3. Document-type classification"),
        code("cl = res['classification']\n"
             "print('accuracy', round(cl['accuracy'],3), 'macro-F1', round(cl['macro_f1'],3))\n"
             "display(Image(str(ROOT/'deliverable-1-extraction-accuracy'/'figures'/'confusion_matrix.png')))"),
        md("## 4. F1 by document type"),
        code("bt = pd.DataFrame(res['by_document_type']).T.sort_values('macro_f1')\n"
             "display(bt)\n"
             "display(Image(str(ROOT/'deliverable-1-extraction-accuracy'/'figures'/'f1_by_document_type.png')))"),
        md("## 5. Live demo — score one document with the real matcher\n"
           "Showing the numeric-aware containment match on a single capital-call field."),
        code("from onelp_eval import extraction_eval as ee\n"
             "truth = ee.load_jsonl(ROOT/'data'/'extraction'/'ground_truth.jsonl')[0]\n"
             "pred  = ee.load_jsonl(ROOT/'data'/'extraction'/'predictions_hybrid.jsonl')[0]\n"
             "for f in ['fundName','totalAmount','dueDate']:\n"
             "    print(f'{f:14} truth={truth[f]!r:>28}  pred={pred[f]!r:>22}  match={ee.field_match(pred[f], truth[f])}')"),
        md("### Takeaway\nThe hybrid architecture is justified by the data: the two single "
           "engines fail in opposite directions, and merging them recovers the best of both."),
    ]
    return nb


def nb_d2():
    nb = new_notebook()
    nb.cells = [
        md("# Deliverable 2 — Cash-Flow Forecasting with Backtesting\n\n"
           "Implements proposal **Metric 2 (MAE)** and **POC Deliverable 2**: P10/P50/P90 "
           "bands, a rolling-origin **backtest**, **stress testing**, **sensitivity**, and "
           "the **Cholesky correlation** demonstration.\n\n"
           "The engine (`lib/onelp_eval/mc_engine.py`) is a **line-for-line port** of "
           "`src/lib/forecasting/monte-carlo.ts`."),
        code(SETUP),
        md("## 1. Load forecast metrics"),
        code("res = json.load(open(ROOT/'deliverable-2-forecasting-backtest'/'results'/'forecast_metrics.json'))\n"
             "print('Portfolio:', res['portfolio']['n_funds'], 'funds, $%.0fM committed' % (res['portfolio']['total_commitment']/1e6))\n"
             "print('Backtest MAE%%: %.1f%%  (target <15%%)  | 80%% band coverage %.0f%%' % (res['backtest']['mae_pct']*100, res['backtest']['coverage_80']*100))"),
        md("## 2. Probabilistic forecast (P10/P50/P90)"),
        code("display(Image(str(ROOT/'deliverable-2-forecasting-backtest'/'figures'/'forecast_fan_chart.png')))"),
        md("## 3. Backtest — forecast vs actual (Metric 2)\nMAE **6.3%** < 15% target."),
        code("display(Image(str(ROOT/'deliverable-2-forecasting-backtest'/'figures'/'backtest_vs_actual.png')))"),
        md("## 4. Stress testing & liquidity reserve"),
        code("st = pd.DataFrame(res['stress'])[['name','navShock','callMultiplier','distributionMultiplier','cumulative_net_p50','reserve_95']]\n"
             "st = st.sort_values('cumulative_net_p50'); display(st)\n"
             "display(Image(str(ROOT/'deliverable-2-forecasting-backtest'/'figures'/'stress_scenarios.png')))\n"
             "display(Image(str(ROOT/'deliverable-2-forecasting-backtest'/'figures'/'liquidity_reserve.png')))"),
        md("## 5. Sensitivity (±25% on key drivers)"),
        code("display(pd.DataFrame(res['sensitivity']['drivers']))\n"
             "display(Image(str(ROOT/'deliverable-2-forecasting-backtest'/'figures'/'sensitivity_tornado.png')))"),
        md("## 6. Cross-asset correlation effect (+45% tail σ)"),
        code("display(Image(str(ROOT/'deliverable-2-forecasting-backtest'/'figures'/'correlation_effect.png')))"),
        md("## 7. Live demo — run the ported engine on a 3-fund portfolio\n"
           "200 paths, same seeded LCG + Box-Muller as production."),
        code("from onelp_eval.mc_engine import FundInput, FundHistoricalData, MonteCarloOptions, run_monte_carlo, SCENARIOS_BY_ID\n"
             "funds = [FundInput('a','PE Fund','Private Equity',2020,20e6,14e6,18e6,0.18,1.6,0.4),\n"
             "         FundInput('b','VC Fund','Venture Capital',2021,10e6,6e6,8e6,0.2,1.4,0.05),\n"
             "         FundInput('c','RE Fund','Real Estate',2020,15e6,11e6,12e6,0.12,1.2,0.3)]\n"
             "hist = {f.id: FundHistoricalData() for f in funds}\n"
             "opts = MonteCarloOptions(simulations=200, quarters=8, seed=42, includeCorrelation=True)\n"
             "r = run_monte_carlo(funds, hist, SCENARIOS_BY_ID['base'], opts, 2026)\n"
             "pd.DataFrame({'P10':r.p10/1e6,'P50':r.p50/1e6,'P90':r.p90/1e6}).round(2)"),
        md("### Takeaway\nThe engine meets the MAE target; reserve sizing is stress-driven; "
           "the correlation model needs regularization to engage on realistic multi-fund books."),
    ]
    return nb


def nb_d3():
    nb = new_notebook()
    nb.cells = [
        md("# Deliverable 3 — Pipeline & Model Analysis\n\n"
           "Implements **POC Deliverable 3** and proposal **Metric 3 (latency)**: confidence "
           "**calibration** (reliability diagram, ECE), end-to-end **latency**, the auto-apply "
           "**threshold** trade-off, and **limitations**."),
        code(SETUP),
        md("## 1. Load analysis"),
        code("res = json.load(open(ROOT/'deliverable-3-pipeline-analysis'/'results'/'pipeline_analysis.json'))\n"
             "c, l = res['calibration'], res['latency']\n"
             "print('ECE %.3f | mean conf %.3f vs accuracy %.3f (%+.1f pts)' % (c['ece'],c['mean_confidence'],c['mean_accuracy'],(c['mean_confidence']-c['mean_accuracy'])*100))\n"
             "print('Latency P50 %.1fs (target<30) | P95 %.1fs (target<90)' % (l['p50'], l['p95']))"),
        md("## 2. Reliability diagram — conservative calibration"),
        code("display(Image(str(ROOT/'deliverable-3-pipeline-analysis'/'figures'/'reliability_diagram.png')))"),
        md("## 3. Calibration by field category"),
        code("cc = pd.DataFrame(res['calibration']['by_category']).T.sort_values('overconfidence')\n"
             "display(cc[['mean_conf','mean_acc','overconfidence','n']])\n"
             "display(Image(str(ROOT/'deliverable-3-pipeline-analysis'/'figures'/'calibration_by_category.png')))"),
        md("## 4. Auto-apply threshold operating curve"),
        code("th = pd.DataFrame(res['threshold_operating'])\n"
             "display(th[th['threshold'].isin([0.70,0.80,0.85,0.90,0.95])])\n"
             "display(Image(str(ROOT/'deliverable-3-pipeline-analysis'/'figures'/'threshold_operating_curve.png')))"),
        md("## 5. End-to-end latency (Metric 3)"),
        code("print('stage means (s):', {k:round(v,1) for k,v in l['stage_mean'].items()})\n"
             "display(Image(str(ROOT/'deliverable-3-pipeline-analysis'/'figures'/'latency_breakdown.png')))"),
        md("### Takeaway\nThe pipeline is conservatively calibrated (errs safe) and meets the "
           "latency targets; the opportunities are a calibration map (reclaim review capacity) "
           "and fixing the correlation-matrix fallback."),
    ]
    return nb


def main():
    notebooks = {
        "deliverable-1-extraction-accuracy.ipynb": nb_d1(),
        "deliverable-2-forecasting-backtest.ipynb": nb_d2(),
        "deliverable-3-pipeline-analysis.ipynb": nb_d3(),
    }
    try:
        from nbconvert.preprocessors import ExecutePreprocessor
        ep = ExecutePreprocessor(timeout=300, kernel_name="python3")
    except Exception as e:  # noqa: BLE001
        ep = None
        print("[warn] nbconvert execute unavailable, writing un-executed notebooks:", e)

    for name, nb in notebooks.items():
        if ep is not None:
            try:
                ep.preprocess(nb, {"metadata": {"path": str(HERE)}})
                status = "executed"
            except Exception as e:  # noqa: BLE001
                status = f"written un-executed ({type(e).__name__})"
        else:
            status = "written un-executed"
        with open(HERE / name, "w") as f:
            nbf.write(nb, f)
        print(f"  {name}: {status}")
    print("Notebooks done.")


if __name__ == "__main__":
    main()
