"""
Extraction-accuracy evaluation utilities for Deliverable 1.

The field-matching rule mirrors the repository's own eval harness
`calculateExtractionAccuracy()` (tests/eval/validators.ts:390-421): a predicted
field counts as correct when the normalized predicted string *contains* the
normalized ground-truth value (case-insensitive). We extend that harness with:

  - precision / recall / F1 per field and macro-averaged (proposal Metric 1)
  - a document-type confusion matrix (proposal Deliverable 1)
  - per-engine comparison: docai-only vs llm-only vs hybrid (proposal Deliverable 1)

This module is data-source agnostic: it consumes JSONL prediction + ground-truth
records, so the same code path scores production extractions (re-run with
`--live`) or the calibrated reference predictions shipped in capstone/data.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional


# Critical financial fields carry a higher accuracy bar in the proposal
# (>=95% vs >=90% overall). Metric 1, proposal section 5.
CRITICAL_FIELDS = {
    "totalAmount", "callAmount", "amount", "dueDate", "distributionDate",
    "callDate", "navAmount", "nav", "totalDistributions",
}


def _norm(v) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    # Normalize currency / punctuation noise so "$12.5 million" ~ "12.5 million"
    s = s.replace("$", "").replace("€", "").replace("£", "").replace(",", "")
    s = re.sub(r"\s+", " ", s)
    return s


_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6,
         "bn": 1e9, "b": 1e9, "billion": 1e9}


def _parse_number(v):
    """
    Parse a *scalar* financial value (money / percentage / multiple) to a float,
    honoring scale words so '$5.2 million', 'USD 5,200,000', '5200000.0', '18.2%',
    and '1.45x' all normalize to comparable magnitudes.

    Returns None (-> fall back to string matching) when the value is NOT a pure
    scalar: dates like '2024-03-15', period labels like 'Q3 2024', and free text
    must be compared as strings, not numbers.
    """
    if v is None:
        return None
    s = str(v).strip().lower()
    if re.search(r"\d{4}-\d{1,2}-\d{1,2}", s):   # ISO date -> not a scalar
        return None
    s = (s.replace(",", "").replace("$", "").replace("€", "").replace("£", "")
           .replace("usd", "").replace("eur", "").replace("gbp", "").strip())
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([a-z%]*)", s)
    if not m:
        return None  # embedded letters/spaces (e.g. 'Q3 2024') -> string compare
    num = float(m.group(1))
    suf = m.group(2)
    if suf in ("", "%", "x"):
        return num
    if suf in _MULT:
        return num * _MULT[suf]
    return None  # unrecognized trailing token


def field_match(pred, truth) -> bool:
    """
    Field equivalence. Numeric-aware for financial values (money / % / multiples)
    with a 1% tolerance; otherwise directional substring containment matching the
    repository harness `calculateExtractionAccuracy` (tests/eval/validators.ts:402-409),
    i.e. the ground-truth value must appear inside the predicted value.
    """
    tn, pn = _parse_number(truth), _parse_number(pred)
    if tn is not None and pn is not None:
        # both numeric -> compare magnitudes (catches scale/transposition errors)
        if tn == 0:
            return abs(pn) < 1e-6
        return abs(pn - tn) / abs(tn) <= 0.01
    t, p = _norm(truth), _norm(pred)
    if t == "":
        return p == ""
    return t in p  # directional: expected ⊆ predicted (validators.ts semantics)


@dataclass
class FieldTally:
    tp: int = 0   # predicted present & correct
    fp: int = 0   # predicted present but wrong (or hallucinated)
    fn: int = 0   # ground-truth present but missed / wrong-empty
    tn: int = 0   # both absent

    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 1.0

    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 1.0

    def f1(self) -> float:
        p, r = self.precision(), self.recall()
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def support(self) -> int:
        return self.tp + self.fn


def score_document(pred: dict, truth: dict, tallies: dict):
    """Update per-field tallies for one document's fields vs ground truth."""
    # Keys that are not extraction fields (ids, classifier metadata, provenance)
    NON_FIELD = {"docId", "docType", "_meta", "predDocType", "docTypeConfidence"}
    keys = (set(truth.keys()) | set(pred.keys())) - NON_FIELD
    for k in keys:
        t_present = k in truth and truth[k] not in (None, "", [])
        p_val = pred.get(k)
        p_present = p_val not in (None, "", [])
        tally = tallies.setdefault(k, FieldTally())
        if t_present and p_present:
            if field_match(p_val, truth[k]):
                tally.tp += 1
            else:
                tally.fp += 1  # wrong value present
                tally.fn += 1  # and the true value was missed
        elif t_present and not p_present:
            tally.fn += 1
        elif (not t_present) and p_present:
            tally.fp += 1  # hallucinated a field not in ground truth
        else:
            tally.tn += 1


def evaluate_predictions(pred_records: list, truth_records: list) -> dict:
    """
    Returns a dict with per-field tallies, macro F1, critical-field F1,
    and overall micro precision/recall/F1.
    """
    truth_by_id = {r["docId"]: r for r in truth_records}
    tallies: dict = {}
    matched_docs = 0
    for pr in pred_records:
        tr = truth_by_id.get(pr["docId"])
        if tr is None:
            continue
        matched_docs += 1
        score_document(pr, tr, tallies)

    # Macro F1 across fields
    field_f1 = {k: t.f1() for k, t in tallies.items()}
    macro_f1 = sum(field_f1.values()) / len(field_f1) if field_f1 else 0.0

    crit = [k for k in tallies if k in CRITICAL_FIELDS]
    crit_f1 = (sum(field_f1[k] for k in crit) / len(crit)) if crit else None

    # Micro (pooled) precision/recall/F1
    TP = sum(t.tp for t in tallies.values())
    FP = sum(t.fp for t in tallies.values())
    FN = sum(t.fn for t in tallies.values())
    micro_p = TP / (TP + FP) if (TP + FP) else 1.0
    micro_r = TP / (TP + FN) if (TP + FN) else 1.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) else 0.0

    return {
        "tallies": tallies,
        "field_f1": field_f1,
        "macro_f1": macro_f1,
        "critical_field_f1": crit_f1,
        "critical_fields": crit,
        "micro_precision": micro_p,
        "micro_recall": micro_r,
        "micro_f1": micro_f1,
        "n_docs": matched_docs,
        "n_fields": len(tallies),
    }


def confusion_matrix(pred_records: list, truth_records: list, labels: list):
    """Document-type classification confusion matrix (counts)."""
    idx = {l: i for i, l in enumerate(labels)}
    n = len(labels)
    cm = [[0] * n for _ in range(n)]
    truth_by_id = {r["docId"]: r for r in truth_records}
    for pr in pred_records:
        tr = truth_by_id.get(pr["docId"])
        if tr is None:
            continue
        t = tr.get("docType")
        p = pr.get("predDocType", pr.get("docType"))
        if t in idx and p in idx:
            cm[idx[t]][idx[p]] += 1
    return cm


def classification_report(cm, labels) -> dict:
    """Per-class precision/recall/F1 + accuracy from a confusion matrix."""
    n = len(labels)
    out = {}
    total = sum(sum(r) for r in cm)
    correct = sum(cm[i][i] for i in range(n))
    for i, lab in enumerate(labels):
        tp = cm[i][i]
        fp = sum(cm[r][i] for r in range(n)) - tp
        fn = sum(cm[i]) - tp
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        out[lab] = {"precision": p, "recall": r, "f1": f1, "support": sum(cm[i])}
    macro_f1 = sum(v["f1"] for v in out.values()) / n if n else 0.0
    return {"per_class": out, "accuracy": correct / total if total else 0.0,
            "macro_f1": macro_f1, "n": total}


def load_jsonl(path: str) -> list:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
