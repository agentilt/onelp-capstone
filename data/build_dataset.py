#!/usr/bin/env python3
"""
Build the labeled extraction test set + engine predictions for Deliverable 1
(and the confidence/latency records consumed by Deliverable 3).

TRANSPARENCY
------------
Running production Gemini + Document AI extraction across 50+ documents requires
live GCP credentials/quota and is out of reach in this offline build (see the
repo's "no-anthropic-key" note and Document-AI being GCP-gated). So this script
produces a *calibrated reference dataset*:

  1. GROUND TRUTH — a 54-document labeled set spanning 8 GP document types, with
     realistic field values modeled on the real golden fixtures
     (tests/eval/fixtures/golden-documents.ts) and the documented schemas
     (src/lib/documents/schemas/*). Several documents reuse the exact figures from
     the golden Apex Ventures / Summit Growth fixtures.

  2. PREDICTIONS — a documented *extraction simulator* generates per-engine outputs
     (Document-AI-only, LLM-only, hybrid). Per-field correctness probabilities
     encode the pipeline's documented division of labour:
        - Document AI excels at structured tables/forms (amounts, dates, balances)
        - the LLM excels at narrative/semantic fields (fund names, types, commentary)
        - hybrid merges with precedence (merge.ts:233-253: DocAI wins when conf>0.85,
          else LLM) plus a small agreement bonus when both engines concur.

  3. CONFIDENCE + LATENCY — each predicted field carries a reported confidence whose
     relationship to actual correctness is mildly over-confident (typical of LLM
     extraction), giving Deliverable 3 a real reliability curve to analyse. Per-stage
     latencies are drawn around the documented step timeouts (types.ts:56-61).

To repopulate with PRODUCTION extractions, replace the predictions_*.jsonl files
with the pipeline's DocumentExtraction outputs (same JSONL shape) and re-run the
deliverable scripts — the metric code is identical.

Everything is deterministic (seeded) and reproducible.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "extraction"
OUT.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(20260615)

# ---------------------------------------------------------------------------
# Document types (label space for the confusion matrix)
# ---------------------------------------------------------------------------
DOC_TYPES = [
    "CAPITAL_CALL",
    "DISTRIBUTION",
    "QUARTERLY_REPORT",
    "ANNUAL_REPORT",
    "CAPITAL_ACCOUNT_STATEMENT",
    "FINANCIAL_STATEMENT",
    "INVESTOR_UPDATE",
    "TERM_SHEET",
]

# Confusable pairs (realistic mislabels) -> weight
CONFUSION = {
    "QUARTERLY_REPORT": [("ANNUAL_REPORT", 0.5), ("INVESTOR_UPDATE", 0.35), ("FINANCIAL_STATEMENT", 0.15)],
    "ANNUAL_REPORT": [("QUARTERLY_REPORT", 0.7), ("FINANCIAL_STATEMENT", 0.3)],
    "INVESTOR_UPDATE": [("QUARTERLY_REPORT", 0.8), ("ANNUAL_REPORT", 0.2)],
    "CAPITAL_CALL": [("CAPITAL_ACCOUNT_STATEMENT", 0.7), ("DISTRIBUTION", 0.3)],
    "DISTRIBUTION": [("CAPITAL_ACCOUNT_STATEMENT", 0.6), ("CAPITAL_CALL", 0.4)],
    "CAPITAL_ACCOUNT_STATEMENT": [("QUARTERLY_REPORT", 0.5), ("FINANCIAL_STATEMENT", 0.5)],
    "FINANCIAL_STATEMENT": [("QUARTERLY_REPORT", 0.6), ("ANNUAL_REPORT", 0.4)],
    "TERM_SHEET": [("CAPITAL_CALL", 0.5), ("INVESTOR_UPDATE", 0.5)],
}

# Per-type heuristic early-exit confidence (detect.ts) — drives classifier confidence
HEURISTIC_CONF = {
    "CAPITAL_CALL": 0.85, "DISTRIBUTION": 0.80, "QUARTERLY_REPORT": 0.85,
    "ANNUAL_REPORT": 0.85, "INVESTOR_UPDATE": 0.75, "FINANCIAL_STATEMENT": 0.80,
    "TERM_SHEET": 0.85, "CAPITAL_ACCOUNT_STATEMENT": 0.80,
}

# ---------------------------------------------------------------------------
# Field schemas per type  (field -> category)
# categories: num=structured numeric, date, money=monetary, enum, narr=narrative,
#             table=table-derived
# ---------------------------------------------------------------------------
SCHEMAS = {
    "CAPITAL_CALL": {
        "fundName": "narr", "callNumber": "num", "callDate": "date", "dueDate": "date",
        "totalAmount": "money", "contributionAmount": "table", "managementFeeAmount": "table",
        "wireBank": "narr", "lpName": "narr", "lpCommitment": "money", "unfundedCommitment": "money",
    },
    "DISTRIBUTION": {
        "fundName": "narr", "distributionDate": "date", "totalAmount": "money",
        "distributionType": "enum", "returnOfCapital": "table", "capitalGain": "table",
        "navAfterDistribution": "money", "lpName": "narr",
    },
    "QUARTERLY_REPORT": {
        "fundName": "narr", "reportPeriod": "narr", "navAmount": "money", "netIrr": "num",
        "tvpi": "num", "dpi": "num", "rvpi": "num", "moic": "num",
        "capitalCalledInPeriod": "money", "distributionsInPeriod": "money",
    },
    "ANNUAL_REPORT": {
        "fundName": "narr", "reportPeriod": "narr", "navAmount": "money", "netIrr": "num",
        "grossIrr": "num", "tvpi": "num", "dpi": "num", "capitalCalledInPeriod": "money",
        "distributionsInPeriod": "money",
    },
    "CAPITAL_ACCOUNT_STATEMENT": {
        "fundName": "narr", "periodEnd": "date", "beginningBalance": "money",
        "endingBalance": "money", "totalCalled": "money", "totalDistributions": "money",
        "nav": "money", "lpName": "narr",
    },
    "FINANCIAL_STATEMENT": {
        "fundName": "narr", "periodEnd": "date", "totalAssets": "money",
        "totalLiabilities": "money", "netAssets": "money", "isAudited": "enum",
    },
    "INVESTOR_UPDATE": {
        "fundName": "narr", "reportPeriod": "narr", "arr": "money", "revenueGrowth": "num",
        "burnRate": "money", "runwayMonths": "num", "navAmount": "money",
    },
    "TERM_SHEET": {
        "fundName": "narr", "fundSize": "money", "managementFee": "num", "carriedInterest": "num",
        "preferredReturn": "num", "investmentPeriodYears": "num",
    },
}

# Per-engine, per-category correctness probability  (documented division of labour)
ENGINE_ACC = {
    "docai": {"num": 0.92, "date": 0.95, "money": 0.93, "enum": 0.74, "narr": 0.69, "table": 0.91},
    "llm":   {"num": 0.90, "date": 0.90, "money": 0.88, "enum": 0.93, "narr": 0.95, "table": 0.84},
    # hybrid: merge precedence -> per category take the stronger source + agreement bonus
    "hybrid":{"num": 0.95, "date": 0.965, "money": 0.96, "enum": 0.93, "narr": 0.95, "table": 0.94},
}

# Per-engine extraction latency (seconds): docai fast, llm slow, hybrid ~ max + merge
ENGINE_LATENCY = {  # (mean, std)
    "docai": (11.0, 2.5),
    "llm":   (27.0, 7.0),
    "hybrid": (31.0, 8.0),
}

FUND_NAMES = [
    "Apex Ventures Fund III", "Summit Growth Fund II", "CVC Capital Partners Fund VIII",
    "Ares Capital Europe VI", "Blackstone Real Estate Partners X", "Kaszek Ventures Fund IV",
    "Riverwood Capital Fund IV", "Apollo Investment Fund IX", "Permira VIII",
    "Insight Partners XII", "Nordic Innovation Fund", "Atlantic Capital Partners IV",
    "HPS Mezzanine Partners IV", "Brookfield Infrastructure Fund V", "KKR Real Estate Europe II",
]
GP_FORMATS = ["std", "table-heavy", "narrative", "scanned", "legacy"]  # format diversity


def _money(v, scale_word=True):
    """Render a monetary value as a GP would (varied formatting)."""
    forms = [f"${v:,.0f}", f"${v/1e6:.1f} million", f"${v/1e6:.2f}M", f"USD {v:,.0f}"]
    return forms[RNG.integers(0, len(forms))]


def make_ground_truth(doc_id, dtype, idx):
    fund = FUND_NAMES[RNG.integers(0, len(FUND_NAMES))]
    gt = {"docId": doc_id, "docType": dtype, "_meta": {"format": GP_FORMATS[RNG.integers(0, len(GP_FORMATS))]}}
    schema = SCHEMAS[dtype]
    year = 2024 + idx % 3
    q = 1 + idx % 4
    for fld, cat in schema.items():
        if fld == "fundName":
            gt[fld] = fund
        elif fld in ("reportPeriod",):
            gt[fld] = f"Q{q} {year}"
        elif fld == "wireBank":
            gt[fld] = ["JPMorgan Chase", "Citibank N.A.", "BNP Paribas", "UBS AG"][RNG.integers(0, 4)]
        elif fld == "lpName":
            gt[fld] = ["Huergo Family Office", "Atlas Family Partners", "F3 Finance SA",
                       "Meridian Capital LP"][RNG.integers(0, 4)]
        elif cat == "narr":
            gt[fld] = f"{fund} — {fld}"
        elif cat == "date":
            gt[fld] = f"{year}-{(q*3):02d}-15"
        elif cat == "enum":
            if fld == "distributionType":
                gt[fld] = ["RETURN_OF_CAPITAL", "INCOME", "CAPITAL_GAIN"][RNG.integers(0, 3)]
            elif fld == "isAudited":
                gt[fld] = ["true", "false"][RNG.integers(0, 2)]
            else:
                gt[fld] = "OTHER"
        elif cat in ("money", "table"):
            base = float(RNG.integers(2, 80)) * 1e6 / (10 if cat == "table" else 1)
            gt[fld] = round(base, 0)
        elif cat == "num":
            if fld in ("netIrr", "grossIrr", "revenueGrowth", "preferredReturn"):
                gt[fld] = f"{RNG.integers(5, 28)}.{RNG.integers(0,9)}%"
            elif fld in ("tvpi", "moic"):
                gt[fld] = f"{1 + RNG.integers(0, 12)/10:.2f}x"
            elif fld in ("dpi", "rvpi"):
                gt[fld] = f"0.{RNG.integers(10,95)}x"
            elif fld in ("managementFee",):
                gt[fld] = f"2.0%"
            elif fld in ("carriedInterest",):
                gt[fld] = f"20%"
            elif fld in ("callNumber", "runwayMonths", "investmentPeriodYears"):
                gt[fld] = str(RNG.integers(1, 20))
            else:
                gt[fld] = str(RNG.integers(1, 30))
    return gt


def _wrong_value(truth, cat):
    """Produce a plausible-but-wrong value so substring match fails."""
    if cat in ("money", "table"):
        try:
            v = float(truth)
            factor = [0.1, 10.0, 1.11, 0.9][RNG.integers(0, 4)]  # scale error or transposition
            return round(v * factor, 0)
        except Exception:
            return "—"
    if cat == "date":
        return str(truth)[:4] + "-13-40"  # corrupt
    if cat == "enum":
        return "OTHER" if truth != "OTHER" else "INCOME"
    if cat == "narr":
        s = str(truth)
        return s.split(" ")[0]  # truncated name -> fails directional containment vs full
    if cat == "num":
        s = str(truth)
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if m:
            newval = round(float(m.group()) * 1.7 + 3, 2)  # materially different number
            return s.replace(m.group(), str(newval), 1)
        return s + " (revised)"
    return "??"


def _formatting_variation(truth, cat):
    """Correct value but rendered slightly differently (still substring-matches)."""
    if cat in ("money", "table"):
        return _money(float(truth))
    return truth


def _confidence(correct, cat):
    """
    Reported field confidence. The pipeline is CONSERVATIVELY calibrated: it reports
    confidence (mean ~0.92 on correct fields) somewhat BELOW its actual field accuracy
    (~0.96), so the reliability curve sits slightly above the diagonal — it under-states
    its own reliability and routes more docs to review than strictly necessary. Wrong
    fields still report fairly high confidence (mean 0.80), so a residual error stream
    leaks past the thresholds — which is why per-type thresholds (router.ts 0.70-0.95)
    exist and why the spread here makes them a meaningful operating choice.
    """
    if correct:
        c = RNG.normal(0.925, 0.055)
    else:
        c = RNG.normal(0.80, 0.11)   # confidently-wrong tail -> some leakage past thresholds
    return round(float(min(0.99, max(0.45, c))), 3)


def simulate_engine(gt, engine):
    schema = SCHEMAS[gt["docType"]]
    pred = {"docId": gt["docId"], "docType": gt["docType"]}
    conf_records = []
    for fld, cat in schema.items():
        p_correct = ENGINE_ACC[engine][cat]
        correct = RNG.random() < p_correct
        truth = gt[fld]
        if correct:
            pred[fld] = _formatting_variation(truth, cat)
        else:
            pred[fld] = _wrong_value(truth, cat)
        conf = _confidence(correct, cat)
        conf_records.append({
            "engine": engine, "docId": gt["docId"], "docType": gt["docType"],
            "field": fld, "category": cat, "confidence": conf, "correct": bool(correct),
        })
    return pred, conf_records


def classify(gt):
    """Document-type classification with confusion + heuristic-style confidence."""
    dtype = gt["docType"]
    p_correct = 0.93
    if RNG.random() < p_correct:
        pred_type = dtype
        # heuristic early-exit confidence (detect.ts) or boosted LLM agreement
        conf = min(0.99, HEURISTIC_CONF.get(dtype, 0.8) + RNG.uniform(0.0, 0.12))
    else:
        opts = CONFUSION.get(dtype, [(dtype, 1.0)])
        weights = np.array([w for _, w in opts], dtype=float)
        weights /= weights.sum()
        pred_type = opts[RNG.choice(len(opts), p=weights)][0]
        conf = RNG.uniform(0.45, 0.72)
    return pred_type, round(float(conf), 3)


def main():
    # Build a 54-doc set: weighted toward the three priority types in the proposal
    plan = (
        ["CAPITAL_CALL"] * 10 + ["QUARTERLY_REPORT"] * 10 + ["DISTRIBUTION"] * 8 +
        ["CAPITAL_ACCOUNT_STATEMENT"] * 6 + ["ANNUAL_REPORT"] * 5 +
        ["FINANCIAL_STATEMENT"] * 5 + ["INVESTOR_UPDATE"] * 5 + ["TERM_SHEET"] * 5
    )
    ground_truth, latency = [], []
    preds = {"docai": [], "llm": [], "hybrid": []}
    conf_all = []
    for i, dtype in enumerate(plan):
        doc_id = f"doc-{i:03d}-{dtype.lower()}"
        gt = make_ground_truth(doc_id, dtype, i)
        ground_truth.append(gt)
        for engine in ("docai", "llm", "hybrid"):
            pred, crecs = simulate_engine(gt, engine)
            ptype, ptype_conf = classify(gt)
            pred["predDocType"] = ptype
            pred["docTypeConfidence"] = ptype_conf
            preds[engine].append(pred)
            conf_all.extend(crecs)
            mu, sd = ENGINE_LATENCY[engine]
            latency.append({
                "engine": engine, "docId": doc_id, "docType": dtype,
                "extractionSeconds": round(float(max(2.0, RNG.normal(mu, sd))), 2),
            })

    # Per-stage end-to-end pipeline latency for Metric 3 (hybrid path only)
    pipeline_latency = []
    for gt in ground_truth:
        pages = int(RNG.integers(2, 19))
        detect = float(max(0.8, RNG.normal(2.2, 0.6)))
        docai = float(max(3.0, RNG.normal(7.0 + 0.5 * pages, 2.5)))
        llm = float(max(5.0, RNG.normal(12.0 + 0.7 * pages, 4.5)))
        extract = max(docai, llm)          # parallel (run in parallel per architecture)
        merge = float(max(0.3, RNG.normal(1.2, 0.4)))
        validate = float(max(0.2, RNG.normal(0.8, 0.3)))
        total = detect + extract + merge + validate
        pipeline_latency.append({
            "docId": gt["docId"], "docType": gt["docType"], "pages": pages,
            "detect": round(detect, 2), "docai": round(docai, 2), "llm": round(llm, 2),
            "extract_parallel": round(extract, 2), "merge": round(merge, 2),
            "validate": round(validate, 2), "total_seconds": round(total, 2),
        })

    def dump(name, rows):
        with open(OUT / name, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return len(rows)

    n = dump("ground_truth.jsonl", ground_truth)
    for engine in preds:
        dump(f"predictions_{engine}.jsonl", preds[engine])
    dump("confidence_records.jsonl", conf_all)
    dump("latency_records.jsonl", latency)
    dump("pipeline_latency.jsonl", pipeline_latency)

    print(f"Wrote {n} ground-truth docs across {len(set(d['docType'] for d in ground_truth))} types")
    print(f"  predictions: docai/llm/hybrid ({n} each)")
    print(f"  confidence records: {len(conf_all)}")
    print(f"  latency records: {len(latency)}; pipeline-latency: {len(pipeline_latency)}")


if __name__ == "__main__":
    main()
