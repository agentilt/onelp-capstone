#!/usr/bin/env python3
"""
Deliverable 3 — Pipeline & Model Analysis.

  1. Confidence calibration: does the pipeline's reported confidence correspond to
     actual correctness? Reliability diagram + Expected Calibration Error (ECE) +
     per-category over/under-confidence. (proposal Deliverable 3)
  2. End-to-end processing latency (proposal Metric 3): per-stage breakdown and
     P50/P95 vs targets (P50 < 30s, P95 < 90s for <20-page docs).
  3. Confidence-threshold operating analysis: how the per-type auto-apply thresholds
     (router.ts) trade off auto-apply rate vs error leakage into fund records.

Writes results JSON to results/ and figures (PNG) to figures/.
Run:  python run_analysis.py
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

# Per-type auto-apply thresholds (src/lib/documents/pipeline/router.ts:82-106)
AUTO_APPLY_THRESHOLDS = {
    "CAPITAL_CALL": 0.85, "DISTRIBUTION": 0.85, "QUARTERLY_REPORT": 0.80,
    "ANNUAL_REPORT": 0.80, "FINANCIAL_STATEMENT": 0.85, "INVESTOR_UPDATE": 0.75,
    "TERM_SHEET": 0.80, "CAPITAL_ACCOUNT_STATEMENT": 0.80,
}


def ece(confs, corrects, n_bins=10):
    """Expected Calibration Error + per-bin stats."""
    confs = np.asarray(confs)
    corrects = np.asarray(corrects, dtype=float)
    bins = np.linspace(0, 1, n_bins + 1)
    total = len(confs)
    e = 0.0
    rows = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (confs > lo) & (confs <= hi) if i > 0 else (confs >= lo) & (confs <= hi)
        cnt = int(mask.sum())
        if cnt == 0:
            rows.append({"lo": lo, "hi": hi, "count": 0, "acc": None, "conf": None})
            continue
        acc = float(corrects[mask].mean())
        conf = float(confs[mask].mean())
        e += (cnt / total) * abs(acc - conf)
        rows.append({"lo": lo, "hi": hi, "count": cnt, "acc": acc, "conf": conf})
    return e, rows


def main():
    conf_records = ee.load_jsonl(DATA / "confidence_records.jsonl")
    pipe = ee.load_jsonl(DATA / "pipeline_latency.jsonl")

    # --- 1. Calibration (hybrid engine = production path) ---
    hy = [r for r in conf_records if r["engine"] == "hybrid"]
    confs = [r["confidence"] for r in hy]
    corrects = [r["correct"] for r in hy]
    overall_ece, bins = ece(confs, corrects)
    mean_conf = float(np.mean(confs))
    mean_acc = float(np.mean(corrects))
    overconf = mean_conf - mean_acc

    # per-category calibration
    cats = sorted({r["category"] for r in hy})
    cat_cal = {}
    for c in cats:
        sub = [r for r in hy if r["category"] == c]
        cc = np.mean([r["confidence"] for r in sub])
        ca = np.mean([r["correct"] for r in sub])
        cat_cal[c] = {"mean_conf": float(cc), "mean_acc": float(ca),
                      "overconfidence": float(cc - ca), "n": len(sub)}

    # --- 2. End-to-end latency (Metric 3) ---
    totals = np.array([r["total_seconds"] for r in pipe])
    stages = ["detect", "extract_parallel", "merge", "validate"]
    stage_mean = {s: float(np.mean([r[s] for r in pipe])) for s in stages}
    p50 = float(np.percentile(totals, 50))
    p95 = float(np.percentile(totals, 95))
    lat = {"p50": p50, "p95": p95, "mean": float(totals.mean()),
           "max": float(totals.max()), "stage_mean": stage_mean,
           "target_p50": 30.0, "target_p95": 90.0,
           "p50_pass": p50 < 30.0, "p95_pass": p95 < 90.0}

    # --- 3. Threshold operating analysis (auto-apply vs error leakage) ---
    # Use field-level correctness as a proxy for extraction reliability at a threshold.
    thr_sweep = []
    arr_conf = np.array(confs)
    arr_corr = np.array(corrects, dtype=float)
    for t in np.round(np.arange(0.50, 0.991, 0.05), 2):
        applied = arr_conf >= t
        auto_rate = float(applied.mean())
        # error leakage = fraction of auto-applied fields that are actually wrong
        leak = float((1 - arr_corr[applied]).mean()) if applied.any() else 0.0
        # review burden = fraction routed to human review
        thr_sweep.append({"threshold": float(t), "auto_apply_rate": auto_rate,
                          "error_leakage": leak, "review_rate": 1 - auto_rate})

    out = {
        "calibration": {
            "n_fields": len(hy), "ece": overall_ece, "mean_confidence": mean_conf,
            "mean_accuracy": mean_acc, "overconfidence": overconf, "bins": bins,
            "by_category": cat_cal,
        },
        "latency": lat,
        "threshold_operating": thr_sweep,
        "auto_apply_thresholds": AUTO_APPLY_THRESHOLDS,
    }
    with open(RES / "pipeline_analysis.json", "w") as f:
        json.dump(out, f, indent=2)

    _print(out)
    fig_reliability(bins, overall_ece, mean_conf, mean_acc)
    fig_confidence_hist(hy)
    fig_category_calibration(cat_cal)
    fig_latency(pipe, lat)
    fig_threshold(thr_sweep)
    print(f"\nFigures -> {FIG}\nResults -> {RES/'pipeline_analysis.json'}")


def _print(out):
    c = out["calibration"]
    l = out["latency"]
    print("=" * 64)
    print("DELIVERABLE 3 — PIPELINE & MODEL ANALYSIS")
    print("=" * 64)
    print(f"Calibration (hybrid, n={c['n_fields']} fields):")
    print(f"  ECE = {c['ece']:.3f}   mean confidence = {c['mean_confidence']:.3f}   "
          f"actual accuracy = {c['mean_accuracy']:.3f}")
    print(f"  Overconfidence (conf - acc) = {c['overconfidence']*100:+.1f} pts")
    print(f"\nEnd-to-end latency (Metric 3, <20-page docs):")
    print(f"  P50 = {l['p50']:.1f}s (target <30s: {'PASS' if l['p50_pass'] else 'MISS'})   "
          f"P95 = {l['p95']:.1f}s (target <90s: {'PASS' if l['p95_pass'] else 'MISS'})")
    print(f"  Stage means: " + "  ".join(f"{k}={v:.1f}s" for k, v in l["stage_mean"].items()))
    print(f"\nThreshold operating points (auto-apply rate / error leakage):")
    for r in out["threshold_operating"]:
        if r["threshold"] in (0.70, 0.80, 0.85, 0.90):
            print(f"  t={r['threshold']:.2f}: auto-apply {r['auto_apply_rate']*100:4.0f}%   "
                  f"leakage {r['error_leakage']*100:4.1f}%")


def fig_reliability(bins, ece_val, mean_conf, mean_acc):
    centers, accs, counts = [], [], []
    for b in bins:
        if b["count"] > 0:
            centers.append((b["lo"] + b["hi"]) / 2)
            accs.append(b["acc"])
            counts.append(b["count"])
    fig, ax = plt.subplots(figsize=(6.8, 6.0))
    ax.plot([0, 1], [0, 1], color=P.MUTED, ls="--", lw=1.2, label="Perfect calibration")
    sizes = 40 + 360 * np.array(counts) / max(counts)
    ax.scatter(centers, accs, s=sizes, color=P.TEAL, alpha=0.8, edgecolor="white",
               zorder=3, label="Observed (size ~ count)")
    ax.plot(centers, accs, color=P.TEAL, lw=1.5, zorder=2)
    # gap shading
    for cx, a in zip(centers, accs):
        ax.plot([cx, cx], [cx, a], color=P.AMBER, lw=1, alpha=0.6)
    ax.set_xlim(0.4, 1.02)
    ax.set_ylim(0.4, 1.02)
    ax.set_xlabel("Reported confidence")
    ax.set_ylabel("Empirical accuracy")
    gap = mean_conf - mean_acc
    direction = "over-confident" if gap > 0 else "conservative (under-confident)"
    ax.set_title(f"Confidence Calibration — Reliability Diagram\n"
                 f"ECE = {ece_val:.3f}   |   mean conf {mean_conf:.2f} vs accuracy "
                 f"{mean_acc:.2f}  ({gap*100:+.0f} pts, {direction})")
    ax.legend(loc="upper left")
    P.savefig(fig, FIG / "reliability_diagram.png")


def fig_confidence_hist(hy):
    right = [r["confidence"] for r in hy if r["correct"]]
    wrong = [r["confidence"] for r in hy if not r["correct"]]
    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    bins = np.linspace(0, 1, 26)
    ax.hist(right, bins=bins, color=P.TEAL, alpha=0.7, label=f"Correct (n={len(right)})")
    ax.hist(wrong, bins=bins, color=P.RED, alpha=0.6, label=f"Incorrect (n={len(wrong)})")
    ax.set_xlabel("Reported confidence")
    ax.set_ylabel("Field count")
    ax.set_title("Confidence Distribution by Correctness\n"
                 "(the confidently-wrong tail — errors with high confidence — is what the review queue must catch)")
    ax.legend()
    P.savefig(fig, FIG / "confidence_by_correctness.png")


def fig_category_calibration(cat_cal):
    cats = sorted(cat_cal.keys(), key=lambda c: cat_cal[c]["overconfidence"])
    label = {"money": "Monetary", "date": "Date", "num": "Numeric", "table": "Table-derived",
             "enum": "Enum", "narr": "Narrative"}
    y = np.arange(len(cats))
    conf = [cat_cal[c]["mean_conf"] for c in cats]
    acc = [cat_cal[c]["mean_acc"] for c in cats]
    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    ax.barh(y - 0.2, conf, height=0.4, color=P.SLATE, label="Mean confidence")
    ax.barh(y + 0.2, acc, height=0.4, color=P.TEAL, label="Actual accuracy")
    for yi, c in zip(y, cats):
        gap = cat_cal[c]["overconfidence"]
        ax.text(max(cat_cal[c]["mean_conf"], cat_cal[c]["mean_acc"]) + 0.01, yi,
                f"{gap*100:+.0f}pts", va="center", fontsize=8,
                color=P.RED if gap > 0 else P.GREEN)
    ax.set_yticks(y)
    ax.set_yticklabels([label.get(c, c) for c in cats])
    ax.set_xlim(0, 1.08)
    ax.set_xlabel("Score")
    ax.set_title("Calibration by Field Category (confidence vs accuracy)")
    ax.legend(loc="lower right")
    P.savefig(fig, FIG / "calibration_by_category.png")


def fig_latency(pipe, lat):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.6, 4.4),
                                   gridspec_kw={"width_ratios": [1.3, 1]})
    # Left: latency distribution with P50/P95
    totals = np.array([r["total_seconds"] for r in pipe])
    ax1.hist(totals, bins=18, color=P.TEAL, alpha=0.75)
    ax1.axvline(lat["p50"], color=P.INK, lw=1.6, ls="--", label=f"P50 = {lat['p50']:.0f}s")
    ax1.axvline(lat["p95"], color=P.AMBER, lw=1.6, ls="--", label=f"P95 = {lat['p95']:.0f}s")
    ax1.axvline(30, color=P.GREEN, lw=1.2, ls=":", label="P50 target 30s")
    ax1.axvline(90, color=P.RED, lw=1.2, ls=":", label="P95 target 90s")
    ax1.set_xlabel("End-to-end latency (seconds)")
    ax1.set_ylabel("Document count")
    ax1.set_title("End-to-End Processing Latency")
    ax1.legend(fontsize=8)
    # Right: per-stage mean breakdown
    stages = ["detect", "extract_parallel", "merge", "validate"]
    slabel = {"detect": "Detect", "extract_parallel": "Extract (parallel)",
              "merge": "Merge", "validate": "Validate"}
    vals = [lat["stage_mean"][s] for s in stages]
    colors = [P.MUTED, P.TEAL, P.SLATE, P.INK]
    bottom = 0
    for s, v, c in zip(stages, vals, colors):
        ax2.bar(0, v, bottom=bottom, color=c, width=0.5, label=f"{slabel[s]} ({v:.1f}s)")
        bottom += v
    ax2.set_xticks([])
    ax2.set_xlim(-0.6, 1.4)   # room so the legend doesn't overlap the bar
    ax2.set_ylabel("Mean stage time (s)")
    ax2.set_title("Mean Pipeline Stage Breakdown")
    ax2.legend(fontsize=10, loc="upper right")
    P.savefig(fig, FIG / "latency_breakdown.png")


def fig_threshold(sweep):
    t = [r["threshold"] for r in sweep]
    auto = [r["auto_apply_rate"] for r in sweep]
    leak = [r["error_leakage"] for r in sweep]
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    ax.plot(t, auto, color=P.TEAL, lw=2, marker="o", ms=4, label="Auto-apply rate")
    ax.plot(t, leak, color=P.RED, lw=2, marker="s", ms=4, label="Error leakage (wrong fields auto-applied)")
    for thr in (0.80, 0.85):
        ax.axvline(thr, color=P.AMBER, ls="--", lw=1, alpha=0.7)
    ax.annotate("capital-call / distribution\nthreshold 0.85", xy=(0.85, 0.90),
                xytext=(0.60, 0.78), fontsize=10, color=P.AMBER, ha="left", va="center",
                arrowprops=dict(arrowstyle="->", color=P.AMBER, lw=1))
    ax.set_xlabel("Confidence threshold")
    ax.set_ylabel("Rate")
    ax.set_title("Auto-Apply Threshold Operating Curve\n"
                 "(higher threshold = fewer errors reach fund records, more human review)")
    ax.legend(loc="center left")
    P.savefig(fig, FIG / "threshold_operating_curve.png")


if __name__ == "__main__":
    main()
