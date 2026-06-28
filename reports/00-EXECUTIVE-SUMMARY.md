---
title: "OneLP Capstone — Proof-of-Concept Deliverables"
subtitle: "Executive Summary & Synthesis"
author: "Kishan Dhulashia · Max Vanderlinden · Sofia Mollon · Agustin Gentil"
date: "June 2026"
---

# OneLP Capstone — Proof-of-Concept Deliverables

## Executive summary

The OneLP capstone builds a production-grade **document-intelligence pipeline** that
turns unstructured private-market documents into structured, validated, portfolio-ready
data, and an **analytics layer** that forecasts portfolio cash flow with calibrated
uncertainty. This document synthesizes the three Proof-of-Concept deliverables committed
to in §7 of the proposal, each evaluated against the quantitative target it was set.

| Deliverable | Proposal target | Result | Verdict |
|---|---|---|:--:|
| **1 — Extraction accuracy** | Macro F1 ≥ 0.90; critical fields ≥ 0.95 | Hybrid **0.968 / 0.968** | ✅ met |
| **2 — Forecast backtest** | MAE < 15% of quarterly cash flow | **5.0% MAE** (20-point rolling) | ✅ met |
| **3 — Latency (Metric 3)** | P50 < 30s; P95 < 90s | **23.9s / 29.4s** | ✅ met |

All three quantitative targets are met. Beyond the headline numbers, the deliverables
surface three findings that matter for production: the **hybrid extraction architecture
is empirically justified** (not just intuitive), the **forecast intervals are slightly
too tight**, and the **cross-asset correlation model silently no-ops on realistic
multi-fund books** — a concrete, fixable engineering gap.

---

## Deliverable 1 — Document Extraction Accuracy

A 54-document labeled test set across 8 GP document types is scored with the
repository's own field-matching logic (extended to be numeric-aware for money/dates).
The **hybrid** engine (Document AI + LLM, merged with precedence) is the **only**
configuration meeting both accuracy bars:

- Macro F1 **0.968** (≥ 0.90 target) · critical-field F1 **0.968** (≥ 0.95 target)
- Document AI alone: strong on financial fields (0.963) but weak on narrative → 0.889 macro
- LLM alone: strong overall (0.892) but weakest on the critical financial fields (0.887)
- Document-type classification: **88.9% accuracy**, confusions only between adjacent
  periodic-report types

**Takeaway:** the two single engines fail in opposite directions; merging them recovers
the best of both. The architecture bet pays off in the data.

## Deliverable 2 — Cash-Flow Forecasting with Backtesting

The production Monte Carlo engine (a faithful Python port of `monte-carlo.ts`) is run
over a 16-fund / $143M calibrated reference portfolio:

- **Backtest MAE 5.0%** of gross quarterly flow on a 20-point rolling-origin test — well
  inside the < 15% target. (80% predictive-interval coverage is 65% → bands are slightly
  too narrow.)
- **Stress testing** across 7 scenarios: cumulative net cash flow ranges from −$6.8M
  (Liquidity Crisis) to +$37.3M (Rapid Recovery); the implied 95% reserve scales with
  severity.
- **Liquidity reserve:** ~$8M (95% confidence) needed to survive a Liquidity Crisis; the
  mature book self-funds in the base case.
- **Sensitivity:** NAV level (±$16.8M) and distribution pacing (±$13.9M) dominate; call
  timing matters ~3× less.
- **Cross-asset correlation** widens the aggregate outcome distribution by +39% (σ) on a
  one-per-class demo — but **does not engage on the full 16-fund book** because the
  per-fund correlation matrix is singular and the engine falls back to independent
  simulation (a documented limitation, `monte-carlo.ts:336-341`).

**Takeaway:** the engine forecasts within target; the reserve sizing is the product's
real value; two calibration/engineering fixes are identified (widen bands, regularize
the correlation matrix).

## Deliverable 3 — Pipeline & Model Analysis

- **Confidence calibration:** ECE 0.056. The pipeline is **conservatively calibrated** —
  mean confidence 0.920 vs accuracy 0.965 (−4.5 pts) — it under-states its reliability,
  most in the structured categories (dates/tables/money) it handles near-perfectly. A
  small "confidently-wrong" tail is what the review queue must catch.
- **Threshold operating curve:** the per-type auto-apply thresholds (0.70–0.95) trade
  auto-apply rate against error leakage; at the 0.85 capital-call threshold, 90% of
  fields auto-apply at 1.9% leakage. Conservative calibration means thresholds could be
  relaxed after a calibration pass.
- **End-to-end latency (Metric 3):** P50 23.9s / P95 29.4s — both targets met; extraction
  dominates and is parallelized (cost = slower engine, not the sum).
- **Limitations:** data sparsity & cold-start (profile fallback until 8+ quarters of
  history), GP-format generalization (long tail of bespoke layouts), correlation-model
  fragility, and conservative calibration.

**Takeaway:** the pipeline's confidence is trustworthy and errs safe; the main
opportunities are a calibration map (to reclaim review capacity) and a correlation-matrix
fix.

---

## Cross-cutting conclusions

1. **The architecture choices are evidence-backed.** Hybrid extraction (D1) and Monte
   Carlo simulation (D2) each beat their simpler alternative on the metric that matters,
   and the parallel-extraction latency design (D3) meets target.
2. **The system is honest about uncertainty.** It is conservatively calibrated and its
   classification errors are "safe" — desirable properties for a financial system of
   record.
3. **Two concrete fixes carry forward:** widen forecast intervals (65% coverage of an 80%
   band) and regularize the correlation matrix so cross-asset co-movement is captured on
   real multi-fund books.
4. **The path to production numbers is wired.** Every metric recomputes unchanged against
   live extractions / real cash flows — only the input files change.

## Reproducibility

```bash
cd capstone && ./build.sh
```

Regenerates all datasets, metrics, figures, notebooks, reports and slides. Engine and
scoring code cite the production source (`src/lib/documents/`, `src/lib/forecasting/`)
throughout.
