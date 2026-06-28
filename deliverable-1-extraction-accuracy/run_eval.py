#!/usr/bin/env python3
"""
Deliverable 1 — Extraction Accuracy Evaluation.

Computes, for the labeled test set in capstone/data/extraction:
  * macro-averaged field F1 + critical-field F1 (proposal Metric 1)
  * per-field precision/recall/F1
  * document-type classification confusion matrix + report
  * Document-AI-only vs LLM-only vs hybrid comparison (accuracy + latency trade-off)

Writes results JSON to results/ and figures (PNG) to figures/.
Run:  python run_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "lib"))

from onelp_eval import extraction_eval as ee  # noqa: E402
from onelp_eval import plotting as P  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

DATA = ROOT / "data" / "extraction"
FIG = HERE / "figures"
RES = HERE / "results"
FIG.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)
P.apply_style()

ENGINES = ["docai", "llm", "hybrid"]
ENGINE_LABEL = {"docai": "Document AI only", "llm": "LLM only", "hybrid": "Hybrid (merged)"}
ENGINE_COLOR = {"docai": P.MUTED, "llm": P.SLATE, "hybrid": P.TEAL}


def main():
    truth = ee.load_jsonl(DATA / "ground_truth.jsonl")
    preds = {e: ee.load_jsonl(DATA / f"predictions_{e}.jsonl") for e in ENGINES}
    latency = ee.load_jsonl(DATA / "latency_records.jsonl")

    # ---- 1. Per-engine accuracy ----
    results = {}
    for e in ENGINES:
        results[e] = ee.evaluate_predictions(preds[e], truth)

    lat_by_engine = {e: [r["extractionSeconds"] for r in latency if r["engine"] == e] for e in ENGINES}

    summary = {}
    for e in ENGINES:
        r = results[e]
        summary[e] = {
            "macro_f1": r["macro_f1"],
            "critical_field_f1": r["critical_field_f1"],
            "micro_precision": r["micro_precision"],
            "micro_recall": r["micro_recall"],
            "micro_f1": r["micro_f1"],
            "n_docs": r["n_docs"],
            "n_fields": r["n_fields"],
            "latency_p50": float(np.percentile(lat_by_engine[e], 50)),
            "latency_p95": float(np.percentile(lat_by_engine[e], 95)),
            "latency_mean": float(np.mean(lat_by_engine[e])),
        }

    # ---- 2. Document-type confusion matrix (hybrid classifier) ----
    labels = sorted({t["docType"] for t in truth})
    cm = ee.confusion_matrix(preds["hybrid"], truth, labels)
    clf = ee.classification_report(cm, labels)

    # ---- 3. F1 by document type (hybrid field extraction) ----
    by_type = {}
    for dt in labels:
        sub_truth = [t for t in truth if t["docType"] == dt]
        ids = {t["docId"] for t in sub_truth}
        sub_pred = [p for p in preds["hybrid"] if p["docId"] in ids]
        rr = ee.evaluate_predictions(sub_pred, sub_truth)
        by_type[dt] = {"macro_f1": rr["macro_f1"], "critical_f1": rr["critical_field_f1"], "n": len(sub_truth)}

    # ---- Persist results ----
    out = {
        "summary": summary,
        "classification": {"labels": labels, "confusion_matrix": cm,
                            "accuracy": clf["accuracy"], "macro_f1": clf["macro_f1"],
                            "per_class": clf["per_class"]},
        "field_f1_hybrid": results["hybrid"]["field_f1"],
        "field_f1_docai": results["docai"]["field_f1"],
        "field_f1_llm": results["llm"]["field_f1"],
        "by_document_type": by_type,
        "critical_fields": results["hybrid"]["critical_fields"],
        "targets": {"overall_f1": 0.90, "critical_field_f1": 0.95},
    }
    with open(RES / "extraction_metrics.json", "w") as f:
        json.dump(out, f, indent=2)

    _print_console(summary, clf, by_type, out)
    _fig_confusion(cm, labels)
    _fig_per_field(results)
    _fig_engine_comparison(summary)
    _fig_accuracy_latency(summary)
    _fig_f1_by_type(by_type)
    print(f"\nFigures -> {FIG}")
    print(f"Results -> {RES/'extraction_metrics.json'}")


def _print_console(summary, clf, by_type, out):
    print("=" * 64)
    print("DELIVERABLE 1 — EXTRACTION ACCURACY")
    print("=" * 64)
    print(f"{'engine':<18}{'macroF1':>9}{'critF1':>9}{'microF1':>9}{'P50 s':>8}{'P95 s':>8}")
    for e, s in summary.items():
        print(f"{ENGINE_LABEL[e]:<18}{s['macro_f1']:>9.3f}{s['critical_field_f1']:>9.3f}"
              f"{s['micro_f1']:>9.3f}{s['latency_p50']:>8.1f}{s['latency_p95']:>8.1f}")
    print(f"\nClassification accuracy (hybrid): {clf['accuracy']:.3f}  macro-F1: {clf['macro_f1']:.3f}")
    t = out["targets"]
    h = summary["hybrid"]
    print(f"Target overall F1 >= {t['overall_f1']:.2f}: "
          f"{'PASS' if h['macro_f1'] >= t['overall_f1'] else 'MISS'} ({h['macro_f1']:.3f})")
    print(f"Target critical-field F1 >= {t['critical_field_f1']:.2f}: "
          f"{'PASS' if h['critical_field_f1'] >= t['critical_field_f1'] else 'MISS'} ({h['critical_field_f1']:.3f})")


def _fig_confusion(cm, labels):
    cm = np.array(cm, dtype=float)
    row = cm.sum(axis=1, keepdims=True)
    norm = np.divide(cm, row, out=np.zeros_like(cm), where=row > 0)
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    ax.grid(False)
    im = ax.imshow(norm, cmap="BuGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    short = [l.replace("_", "\n") for l in labels]
    ax.set_xticklabels(short, rotation=45, ha="right", fontsize=9.5)
    ax.set_yticklabels(short, fontsize=9.5)
    ax.set_xlabel("Predicted type")
    ax.set_ylabel("True type")
    ax.set_title("Document-Type Classification — Confusion Matrix (row-normalized)")
    for i in range(len(labels)):
        for j in range(len(labels)):
            c = int(cm[i, j])
            if c:
                ax.text(j, i, str(c), ha="center", va="center",
                        color="white" if norm[i, j] > 0.5 else P.INK, fontsize=11, fontweight="bold")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="row fraction")
    P.savefig(fig, FIG / "confusion_matrix.png")


def _fig_per_field(results):
    flds = sorted(results["hybrid"]["field_f1"].keys(),
                  key=lambda k: results["hybrid"]["field_f1"][k])
    fig, ax = plt.subplots(figsize=(8.4, max(5, 0.26 * len(flds))))
    y = np.arange(len(flds))
    h = 0.26
    for off, e in zip((-h, 0, h), ENGINES):
        vals = [results[e]["field_f1"].get(f, 0) for f in flds]
        ax.barh(y + off, vals, height=h, color=ENGINE_COLOR[e], label=ENGINE_LABEL[e])
    crit = set(ee.CRITICAL_FIELDS)
    ax.set_yticks(y)
    ax.set_yticklabels([f + ("  *" if f in crit else "") for f in flds], fontsize=9)
    ax.axvline(0.90, color=P.AMBER, ls="--", lw=1, label="0.90 target")
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("F1 score")
    ax.set_title("Per-Field F1 by Extraction Engine  (* = critical financial field)")
    ax.legend(loc="lower left")
    P.savefig(fig, FIG / "per_field_f1.png")


def _fig_engine_comparison(summary):
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    metrics = [("macro_f1", "Macro F1"), ("critical_field_f1", "Critical-field F1"),
               ("micro_f1", "Micro F1")]
    x = np.arange(len(metrics))
    w = 0.26
    for off, e in zip((-w, 0, w), ENGINES):
        vals = [summary[e][m] for m, _ in metrics]
        bars = ax.bar(x + off, vals, width=w, color=ENGINE_COLOR[e], label=ENGINE_LABEL[e])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.008, f"{v:.2f}",
                    ha="center", va="bottom", fontsize=9.5, color=P.INK)
    ax.axhline(0.90, color=P.AMBER, ls="--", lw=1)
    ax.text(len(metrics) - 0.5, 0.905, "0.90 target", color=P.AMBER, fontsize=7.5, ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels([m[1] for m in metrics])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score")
    ax.set_title("Extraction Accuracy: Document AI vs LLM vs Hybrid")
    ax.legend(loc="lower right")
    P.savefig(fig, FIG / "engine_comparison.png")


def _fig_accuracy_latency(summary):
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    for e in ENGINES:
        s = summary[e]
        ax.scatter(s["latency_p50"], s["macro_f1"], s=220, color=ENGINE_COLOR[e],
                   zorder=3, edgecolor="white", linewidth=1.5)
        ax.annotate(ENGINE_LABEL[e], (s["latency_p50"], s["macro_f1"]),
                    textcoords="offset points", xytext=(10, 6), fontsize=9, color=P.INK)
    ax.axhline(0.90, color=P.AMBER, ls="--", lw=1)
    ax.text(ax.get_xlim()[1], 0.902, "0.90 F1 target", color=P.AMBER, fontsize=8, ha="right", va="bottom")
    ax.set_xlabel("Median extraction latency P50 (seconds)")
    ax.set_ylabel("Macro F1")
    ax.set_title("Accuracy vs Latency Trade-off")
    ax.margins(0.18)
    P.savefig(fig, FIG / "accuracy_latency.png")


def _fig_f1_by_type(by_type):
    types = sorted(by_type.keys(), key=lambda k: by_type[k]["macro_f1"])
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    y = np.arange(len(types))
    vals = [by_type[t]["macro_f1"] for t in types]
    ax.barh(y - 0.2, vals, height=0.4, color=P.TEAL, label="Macro F1 (all fields)")
    # Critical-field F1 only for types that actually carry critical financial fields
    cy = [yi for yi, t in zip(y, types) if by_type[t]["critical_f1"] is not None]
    cv = [by_type[t]["critical_f1"] for t in types if by_type[t]["critical_f1"] is not None]
    ax.barh(np.array(cy) + 0.2, cv, height=0.4, color=P.INK, label="Critical-field F1")
    ax.axvline(0.90, color=P.AMBER, ls="--", lw=1, label="0.90 target")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{t.replace('_',' ').title()}  (n={by_type[t]['n']})" for t in types], fontsize=10.5)
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("F1 score (hybrid engine)")
    ax.set_title("Hybrid Extraction F1 by Document Type")
    # Bars fill the full width, so place the legend below the axes (no overlap).
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, fontsize=9.5)
    P.savefig(fig, FIG / "f1_by_document_type.png")


if __name__ == "__main__":
    main()
