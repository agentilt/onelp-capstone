#!/usr/bin/env python3
"""
OneLP — Venture Capstone Pitch Deck.

Follows the recommended Venture Capstone flow (Dae-Jin Lee, June 2026):
  1. Team & problem statement
  2. Market opportunity & value proposition (why it matters, market size, differentiation)
  3. Product & MVP demonstration (live demo + extraction workflow)
  4. Technical implementation (architecture, ML/DS, approach rationale, lessons)
  5. Business model & go-to-market (customers, revenue, TAM/SAM/SOM, validation)
  6. Future roadmap
  7. Funding requirements & use of funds

FILL POLICY (per team decision):
  * Technical / product / traction / architecture slides — FULLY BUILT from this repo
    (live numbers pulled from the deliverable results JSON + the vault).
  * Business slides grounded in vault data (pricing, unit economics, P&L, funding,
    competitors) — FILLED, tagged "DRAFT · from repo — validate" so the team confirms.
  * Slides needing external research / a strategic decision not in the repo
    (TAM/SAM/SOM numbers, detailed GTM channel plan) — TEMPLATED with a scaffold and a
    visible "TEAM TO COMPLETE" badge + presenter notes describing exactly what to add.

Output: slides/OneLP-Venture-Capstone-Pitch.pptx (+ .pdf via LibreOffice).
"""
from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image as PILImage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ---- palette ----
INK = RGBColor(0x0F, 0x17, 0x2A)
SLATE = RGBColor(0x33, 0x41, 0x55)
TEAL = RGBColor(0x0D, 0x94, 0x88)
TEAL_LT = RGBColor(0x5E, 0xEA, 0xD4)
AMBER = RGBColor(0xD9, 0x77, 0x06)
RED = RGBColor(0xDC, 0x26, 0x26)
GREEN = RGBColor(0x16, 0xA3, 0x4A)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
MUTED = RGBColor(0x64, 0x74, 0x8B)
LIGHT = RGBColor(0xF1, 0xF5, 0xF9)
CLOUD = RGBColor(0xCB, 0xD5, 0xE1)

F1 = ROOT / "deliverable-1-extraction-accuracy" / "figures"
F2 = ROOT / "deliverable-2-forecasting-backtest" / "figures"
F3 = ROOT / "deliverable-3-pipeline-analysis" / "figures"


# =============================================================================
# low-level helpers
# =============================================================================
def _slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _bg(slide, color):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def _box(slide, x, y, w, h, fill=None, line=None, rounded=False):
    shape = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.shadow.inherit = False
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid(); shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line; shp.line.width = Pt(1)
    return shp


def _text(slide, x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, space=5):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, para in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        for (txt, size, color, bold) in para:
            r = p.add_run(); r.text = txt
            r.font.size = Pt(size); r.font.color.rgb = color; r.font.bold = bold
            r.font.name = "Helvetica Neue"
    return tb


def _header(slide, title, kicker=None):
    _box(slide, 0, 0, 13.333, 1.25, fill=INK)
    _box(slide, 0, 1.25, 13.333, 0.045, fill=TEAL)
    runs = [[(title, 26, WHITE, True)]]
    if kicker:
        runs = [[(kicker, 12, TEAL_LT, True)], [(title, 24, WHITE, True)]]
    _text(slide, 0.7, 0.16, 10.6, 1.0, runs, anchor=MSO_ANCHOR.MIDDLE)


def _badge(slide, kind):
    """kind: 'built' (teal), 'draft' (amber-light), 'team' (amber)."""
    cfg = {
        "built": ("BUILT & VERIFIED", TEAL, WHITE),
        "draft": ("DRAFT · from repo — validate", AMBER, WHITE),
        "team": ("TEAM TO COMPLETE", RED, WHITE),
    }[kind]
    label, fill, fg = cfg
    w = 1.55 if kind == "built" else (2.85 if kind == "draft" else 2.0)
    shp = _box(slide, 13.333 - w - 0.35, 0.42, w, 0.42, fill=fill, rounded=True)
    tf = shp.text_frame; tf.word_wrap = False
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = label
    r.font.size = Pt(9); r.font.bold = True; r.font.color.rgb = fg; r.font.name = "Helvetica Neue"


def _notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def _caption(slide, text):
    _text(slide, 0.7, 6.98, 12, 0.4, [[(text, 11, MUTED, False)]])


def _place_fit(slide, path, bx, by, bw, bh):
    if not Path(path).exists():
        return
    with PILImage.open(path) as im:
        ar = im.width / im.height
    box_ar = bw / bh
    w, h = (bw, bw / ar) if ar >= box_ar else (bh * ar, bh)
    if ar >= box_ar:
        w, h = bw, bw / ar
    else:
        h, w = bh, bh * ar
    slide.shapes.add_picture(str(path), Inches(bx + (bw - w) / 2), Inches(by + (bh - h) / 2),
                             width=Inches(w))


def _bullets(slide, x, y, w, h, items, size=14, color=SLATE, gap=8):
    """items: list of (text, level) or (text, level, color, bold)."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    for i, it in enumerate(items):
        txt, lvl = it[0], it[1]
        c = it[2] if len(it) > 2 else color
        b = it[3] if len(it) > 3 else False
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        bullet = "" if lvl == 0 else ("•  " if lvl == 1 else "–  ")
        indent = "" if lvl <= 1 else "      "
        r = p.add_run(); r.text = indent + bullet + txt
        r.font.size = Pt(size if lvl <= 1 else size - 1)
        r.font.color.rgb = c; r.font.bold = b; r.font.name = "Helvetica Neue"
    return tb


def _stat_cards(slide, cards, y=5.55, x0=0.7, cw=2.85, gap=0.27):
    """cards: list of (big, label, foot)."""
    x = x0
    for big, label, foot in cards:
        _box(slide, x, y, cw, 1.5, fill=LIGHT, rounded=True)
        _box(slide, x, y, cw, 0.07, fill=TEAL)
        _text(slide, x + 0.22, y + 0.18, cw - 0.4, 1.2,
              [[(big, 26, INK, True)], [(label, 11, SLATE, True)], [(foot, 9.5, MUTED, False)]])
        x += cw + gap


def _table(slide, x, y, w, headers, rows, col_w=None, fsize=11, hfsize=11, row_h=0.34):
    nrows, ncols = len(rows) + 1, len(headers)
    h = row_h * nrows
    gtbl = slide.shapes.add_table(nrows, ncols, Inches(x), Inches(y), Inches(w), Inches(h)).table
    if col_w:
        for j, cw in enumerate(col_w):
            gtbl.columns[j].width = Inches(cw)
    # header
    for j, head in enumerate(headers):
        c = gtbl.cell(0, j)
        c.fill.solid(); c.fill.fore_color.rgb = INK
        c.margin_top = Pt(2); c.margin_bottom = Pt(2)
        p = c.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
        r = p.add_run(); r.text = head
        r.font.size = Pt(hfsize); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = "Helvetica Neue"
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            c = gtbl.cell(i, j)
            c.fill.solid(); c.fill.fore_color.rgb = WHITE if i % 2 else LIGHT
            c.margin_top = Pt(1); c.margin_bottom = Pt(1)
            p = c.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
            r = p.add_run(); r.text = str(val)
            r.font.size = Pt(fsize); r.font.color.rgb = INK
            r.font.bold = (j == 0); r.font.name = "Helvetica Neue"
    return gtbl


# =============================================================================
# load live technical numbers
# =============================================================================
def load_metrics():
    d1 = json.load(open(ROOT / "deliverable-1-extraction-accuracy" / "results" / "extraction_metrics.json"))
    d2 = json.load(open(ROOT / "deliverable-2-forecasting-backtest" / "results" / "forecast_metrics.json"))
    d3 = json.load(open(ROOT / "deliverable-3-pipeline-analysis" / "results" / "pipeline_analysis.json"))
    return d1, d2, d3


# =============================================================================
# SLIDES
# =============================================================================
def build(prs):
    d1, d2, d3 = load_metrics()
    hyb = d1["summary"]["hybrid"]

    # ---- 1. TITLE ----
    s = _slide(prs); _bg(s, INK)
    _box(s, 0, 3.15, 13.333, 0.05, fill=TEAL)
    _text(s, 0.9, 1.6, 11.5, 1.5,
          [[("OneLP", 52, WHITE, True)],
           [("The AI-native operating system for Limited Partners", 24, TEAL_LT, False)]])
    _text(s, 0.9, 3.45, 11.5, 0.7,
          [[("Turning fragmented private-market documents into structured intelligence, "
             "predictive insight, and automated workflows", 15, CLOUD, False)]])
    _text(s, 0.9, 5.7, 11.5, 1.1,
          [[("Kishan Dhulashia · Max Vanderlinden · Sofia Mollon · Agustin Gentil", 14, CLOUD, False)],
           [("Venture Capstone · IE School of Science & Technology · 2026", 12, MUTED, False)]])
    _notes(s, "30-second hook: LPs and family offices drown in PDFs and spreadsheets. OneLP "
              "is the AI-native system that turns that mess into real-time portfolio intelligence "
              "and automated workflows. We have a live product, 7 pilots and €5B+ AUM behind us.")

    # ---- 1b. TEAM ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "Team", kicker="WHO WE ARE")
    team = [
        ("Kishan Dhulashia", "Co-founder", "[role / background — TEAM]"),
        ("Max Vanderlinden", "Co-founder", "[role / background — TEAM]"),
        ("Sofia Mollon", "Co-founder", "[role / background — TEAM]"),
        ("Agustin Gentil", "Co-founder", "[role / background — TEAM]"),
    ]
    x = 0.7
    for name, role, bio in team:
        _box(s, x, 1.9, 2.85, 3.0, fill=LIGHT, rounded=True)
        _box(s, x, 1.9, 2.85, 0.07, fill=TEAL)
        _box(s, x + 1.02, 2.25, 0.8, 0.8, fill=TEAL, rounded=True)
        _text(s, x + 0.2, 3.25, 2.5, 1.5,
              [[(name, 15, INK, True)], [(role, 12, TEAL, True)], [(bio, 10.5, MUTED, False)]],
              align=PP_ALIGN.CENTER)
        x += 3.04
    _text(s, 0.7, 5.4, 12, 1.0,
          [[("IE School of Science & Technology — MSc in Business Analytics & Big Data. "
             "Combined background across data science, software engineering, and private markets.",
             13, SLATE, False)]])
    _badge(s, "team")
    _notes(s, "TEAM: replace the placeholder bios with each founder's specific role (CEO/CTO/etc.) "
              "and one credibility line (prior experience, relevant domain). Keep it to ~10 seconds.")

    # ---- 1c. PROBLEM ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "LPs run multi-million-euro portfolios on PDFs and email", kicker="PROBLEM")
    _bullets(s, 0.7, 1.75, 7.5, 4.6, [
        ("Private-market portfolios are managed across fragmented systems — GP portals, "
         "PDFs, emails, spreadsheets — with no standard data schema.", 1),
        ("Consequences for every LP and family office:", 0, INK, True),
        ("30–40 hours/month of manual reporting per family office", 2),
        ("Missed capital calls → late-payment penalties & compliance risk", 2),
        ("No real-time view of exposure, concentration, or liquidity", 2),
        ("5+ disconnected tools to assemble one portfolio picture", 2),
        ("The real problem is not aggregation — it is operationalizing unstructured, "
         "multi-source financial data into real-time, actionable intelligence.", 0, INK, True),
    ], size=14)
    _stat_cards(s, [("30–40h", "manual reporting / month", "per family office"),
                    ("5+", "fragmented tools", "to replace"),
                    ("16+", "GP document formats", "no standard schema")])
    _notes(s, "Anchor on the pain: a sophisticated LP with hundreds of millions committed still "
              "tracks capital calls in a spreadsheet. Quantify it: 30–40 hours/month. That is the wedge.")

    # ---- 2. MARKET OPPORTUNITY (TAM/SAM/SOM template) ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "Market opportunity", kicker="WHY THIS MATTERS · MARKET SIZE")
    # concentric scaffold
    for i, (lbl, val, note, fill) in enumerate([
        ("TAM", "[€ — TEAM]", "Global private-markets / LP software spend", INK),
        ("SAM", "[€ — TEAM]", "EU family offices, MFOs & LPs (target segments)", TEAL),
        ("SOM", "[€ — TEAM]", "Reachable in 3 yrs via pilot network & GTM", TEAL_LT),
    ]):
        _box(s, 0.9, 2.0 + i * 1.45, 5.4, 1.25, fill=fill, rounded=True)
        _text(s, 1.15, 2.18 + i * 1.45, 5.0, 1.0,
              [[(f"{lbl}   {val}", 18, WHITE if i < 2 else INK, True)],
               [(note, 11, WHITE if i < 2 else INK, False)]], anchor=MSO_ANCHOR.MIDDLE)
    _bullets(s, 6.8, 2.0, 5.9, 4.6, [
        ("Sizing methodology (TEAM to complete):", 0, INK, True),
        ("TAM = # LPs/family offices globally × annual software & data spend", 2),
        ("SAM = EU SFO + MFO + LP segments OneLP can serve today", 2),
        ("SOM = realistic 3-yr capture given pilot pipeline & GTM capacity", 2),
        ("Evidence of demand (have):", 0, INK, True),
        ("7 active pilots representing €5B+ aggregate AUM", 2),
        ("Family-office wealth growing; private-markets allocations rising", 2),
        ("Sources to cite: Preqin / Campden Wealth / Deloitte FO reports", 2, MUTED, False),
    ], size=12.5)
    _badge(s, "team")
    _notes(s, "TEAM: insert TAM/SAM/SOM figures with one cited source each (Preqin, Campden Wealth, "
              "Deloitte family-office reports). Keep the funnel logic explicit. The €5B+ pilot AUM is "
              "real evidence of demand — lead with it.")

    # ---- 2b. VALUE PROPOSITION ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "From fragmented documents to decisions", kicker="VALUE PROPOSITION")
    cols = [
        ("1 · INGEST", TEAL, ["AI document pipeline", "16+ doc types", "OCR + LLM hybrid extraction",
                              "Field-level evidence & audit trail"]),
        ("2 · UNDERSTAND", INK, ["Real-time NAV / IRR / TVPI / DPI", "Exposure & concentration",
                                 "Monte Carlo cash-flow forecasting", "Stress tests & liquidity reserves"]),
        ("3 · ACT", AMBER, ["Capital-call alerts & tracking", "AI daily briefing", "Scheduled reports",
                            "AI email drafting to GPs"]),
    ]
    x = 0.7
    for title, color, items in cols:
        _box(s, x, 1.85, 3.9, 3.6, fill=LIGHT, rounded=True)
        _box(s, x, 1.85, 3.9, 0.5, fill=color, rounded=False)
        _text(s, x + 0.25, 1.9, 3.4, 0.45, [[(title, 13, WHITE, True)]], anchor=MSO_ANCHOR.MIDDLE)
        _bullets(s, x + 0.25, 2.55, 3.45, 2.8, [(it, 1) for it in items], size=11.5, gap=6)
        x += 4.07
    _text(s, 0.7, 5.75, 12, 0.9,
          [[("The wedge: an ", 14, SLATE, False), ("LP interpretation & decision layer", 14, TEAL, True),
            (" above generic monitoring — not 'we store your data', but 'we turn reports, "
             "notices and LPAs into verified answers, alerts and decisions'.", 14, SLATE, False)]])
    _notes(s, "Three verbs: Ingest → Understand → Act. Stress the interpretation layer — that is what "
              "differentiates us from pure extraction (Canoe) and pure monitoring (Cobalt/Chronograph).")

    # ---- 2c. COMPETITIVE LANDSCAPE ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "Competitive landscape & differentiation", kicker="EXISTING SOLUTIONS")
    _table(s, 0.7, 1.75, 12.0,
           ["Player", "Category", "Strong at", "Gap OneLP exploits"],
           [["eFront / iLEVEL", "Enterprise platforms", "Breadth, institutional scale", "Heavy, not LP-opinionated"],
            ["Chronograph / Cobalt", "Monitoring + reporting", "Dashboards, doc-aware AI", "Monitoring, not decisions"],
            ["Canoe", "Doc extraction layer", "Collection & extraction", "Plumbing, not intelligence"],
            ["OneLP", "LP intelligence layer", "Interpret · forecast · automate", "EU-ready, explainable, fast"]],
           col_w=[2.4, 2.7, 3.5, 3.4], fsize=11.5, row_h=0.52)
    _bullets(s, 0.7, 5.2, 12, 1.6, [
        ("Our four defensible wedges:", 0, INK, True),
        ("(1) LP interpretation layer — fees, waterfall, valuation, 'what changed' in plain language", 2),
        ("(2) Decision workflows — pacing, liquidity, commitment recommendations (not just dashboards)", 2),
        ("(3) Europe-ready compliance — AIFMD / SFDR / DORA built in, not bolted on", 2),
        ("(4) Explainable, source-linked AI + faster time-to-value for lean LP teams", 2),
    ], size=11.5, gap=5)
    _notes(s, "Don't fight incumbents on their strong ground (breadth, extraction). Win on "
              "interpretation, decisions, EU compliance, and explainability. The last row is OneLP.")

    # ---- 3. PRODUCT / MVP — LIVE DEMO ----
    s = _slide(prs); _bg(s, INK); _header(s, "Live product demonstration", kicker="PRODUCT · MVP")
    _box(s, 0.9, 1.8, 11.5, 3.4, fill=SLATE, rounded=True)
    _text(s, 1.2, 2.1, 11.0, 2.9,
          [[("▶  LIVE DEMO", 26, TEAL_LT, True)],
           [("Demo flow (≈4 min):", 14, WHITE, True)],
           [("1.  Upload a real GP capital-call PDF → watch the pipeline classify & extract", 13, CLOUD, False)],
           [("2.  Review queue: click-to-highlight evidence on each extracted field", 13, CLOUD, False)],
           [("3.  Auto-apply to fund records → NAV / metrics / capital-call notice update live", 13, CLOUD, False)],
           [("4.  Dashboard: exposure, liquidity, concentration update in real time", 13, CLOUD, False)],
           [("5.  Forecasting tab: Monte Carlo bands, stress tests, daily AI briefing", 13, CLOUD, False)]])
    _text(s, 0.9, 5.5, 11.5, 1.0,
          [[("Live at the deployed platform · demo accounts seeded (Huergo FO, F3 Finance MFO, "
             "Atlas MFO). Fallback: recorded screen-capture if connectivity fails.", 12, CLOUD, False)]])
    _badge(s, "built")
    _notes(s, "DEMO is the centerpiece. Rehearse the 5-step flow on a seeded demo account. Always have "
              "a recorded fallback video. Keep narration tied to the LP's pain: 'this used to take an "
              "analyst an afternoon — now it's 30 seconds and fully auditable.'")

    # ---- 3b. EXTRACTION WORKFLOW ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "Document extraction workflow", kicker="PRODUCT · CORE ENGINE")
    steps = [
        ("1 · DETECT", "Two-stage classification: filename/context heuristic (early-exit ≥0.70) → Gemini LLM across 16+ doc types"),
        ("2 · EXTRACT", "Document AI (tables/forms, bounding boxes) + LLM (narrative) run in PARALLEL"),
        ("3 · MERGE", "Precedence-based conflict resolution (parser >0.85 wins, else LLM); conflicts logged"),
        ("4 · VALIDATE", "Schema + per-type confidence thresholds (0.70–0.95); low-confidence fields flagged"),
        ("5 · APPLY", "High-confidence → auto-apply to fund records; else → human review queue"),
    ]
    y = 1.8
    for tag, desc in steps:
        _box(s, 0.7, y, 2.5, 0.82, fill=TEAL, rounded=True)
        _text(s, 0.85, y + 0.08, 2.3, 0.66, [[(tag, 13, WHITE, True)]], anchor=MSO_ANCHOR.MIDDLE)
        _text(s, 3.45, y + 0.04, 9.2, 0.78, [[(desc, 12.5, SLATE, False)]], anchor=MSO_ANCHOR.MIDDLE)
        y += 0.95
    _text(s, 0.7, 6.6, 12, 0.5, [[("Every field carries raw text, confidence, page number and bounding "
                                   "box → full auditability and click-to-highlight verification.", 12, MUTED, False)]])
    _badge(s, "built")
    _notes(s, "This is the capstone's core technical contribution. Walk the 5 stages. Emphasise the "
              "parallel hybrid extraction and the evidence tracking — that is what makes it trustworthy "
              "for financial data.")

    # ---- 4. TECHNICAL — ARCHITECTURE ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "System architecture", kicker="TECHNICAL IMPLEMENTATION")
    layers = [
        ("APPLICATION", "Dashboard · review queue · daily briefing · workflow management", TEAL_LT),
        ("WORKFLOW AUTOMATION", "Async task queue · scheduled exports · alert engine · AI email drafting", TEAL),
        ("ANALYTICS", "Monte Carlo · stress testing · liquidity reserve · J-curve profiles · explainability", TEAL),
        ("PROCESSING / INGESTION", "Classification · hybrid extraction · merge · validation · auto-apply", INK),
        ("STORAGE", "PostgreSQL (structured) · Cloud Storage (documents) · cache (forecasts)", SLATE),
    ]
    y = 1.8
    for name, desc, fill in layers:
        _box(s, 1.6, y, 10.1, 0.86, fill=fill, rounded=True)
        fg = INK if fill == TEAL_LT else WHITE
        _text(s, 1.85, y + 0.06, 9.7, 0.76,
              [[(name + "   ", 13, fg, True), (desc, 11.5, fg, False)]], anchor=MSO_ANCHOR.MIDDLE)
        y += 0.96
    _text(s, 0.7, 6.55, 12, 0.5,
          [[("Cloud-native on Google Cloud · multi-tenant isolation (clientId) · field-level "
             "auditability · RBAC (LP read-only) · async processing · Sentry observability.", 11.5, MUTED, False)]])
    _badge(s, "built")
    _notes(s, "Five layers, ingestion at the core. Mention: Next.js/React/TypeScript, Prisma/Postgres, "
              "Google Document AI + Vertex Gemini, Cloud Run + Cloud Tasks. Accepted into Google Cloud "
              "for Startups (infra funded).")

    # ---- 4b. ML/DS #1: extraction accuracy ----
    s = _slide(prs); _bg(s, WHITE)
    _header(s, "ML/DS #1 — extraction accuracy (hybrid beats either engine)", kicker="TECHNICAL · DATA SCIENCE")
    _place_fit(s, F1 / "engine_comparison.png", 0.45, 1.6, 7.7, 4.95)
    _stat_cards_right(s, [(f"{hyb['macro_f1']:.3f}", "Hybrid macro F1", "target ≥ 0.90 ✓"),
                          (f"{hyb['critical_field_f1']:.3f}", "Critical-field F1", "target ≥ 0.95 ✓"),
                          (f"{d1['classification']['accuracy']:.3f}", "Doc-type accuracy", "8 types")])
    _caption(s, "54-doc labeled set · Document AI (tables/forms) + LLM (narrative) merged with precedence. "
                "Evaluation Metric 1 met.")
    _badge(s, "built")
    _notes(s, "Hybrid is the only engine clearing both F1 bars. The two single engines fail in opposite "
              "directions — that is WHY we merge. This is real evaluation, not a claim.")

    # ---- 4c. ML/DS #2: forecasting ----
    s = _slide(prs); _bg(s, WHITE)
    _header(s, f"ML/DS #2 — forecasting & backtest (MAE {d2['backtest']['mae_pct']*100:.1f}% < 15%)",
            kicker="TECHNICAL · DATA SCIENCE")
    _place_fit(s, F2 / "forecast_fan_chart.png", 0.4, 1.6, 6.15, 4.95)
    _place_fit(s, F2 / "backtest_vs_actual.png", 6.78, 1.6, 6.15, 4.95)
    _caption(s, "1,000-path Monte Carlo (Cholesky cross-asset correlation) · rolling-origin backtest, "
                "20 portfolio-quarter points · Evaluation Metric 2 met.")
    _badge(s, "built")
    _notes(s, "Monte Carlo with cross-asset correlation; backtested against held-out quarters at "
              f"{d2['backtest']['mae_pct']*100:.1f}% MAE. Also: 7 stress scenarios + liquidity-reserve sizing "
              "(~€8M reserve to survive a liquidity crisis).")

    # ---- 4d. ML/DS #3: calibration + approach rationale & lessons ----
    s = _slide(prs); _bg(s, WHITE)
    _header(s, "ML/DS #3 — calibration, approach rationale & lessons", kicker="TECHNICAL · DATA SCIENCE")
    _place_fit(s, F3 / "reliability_diagram.png", 0.4, 1.6, 5.5, 4.6)
    _bullets(s, 6.2, 1.7, 6.5, 4.9, [
        ("Why these choices:", 0, INK, True),
        ("Hybrid extraction — parser excels at tables, LLM at narrative; merge captures both", 2),
        ("Monte Carlo over closed-form — captures tail risk & cross-asset correlation", 2),
        ("Per-type confidence thresholds — capital calls need 0.85, reports tolerate 0.70", 2),
        ("Challenges & lessons learned:", 0, INK, True),
        (f"Pipeline is conservatively calibrated (ECE {d3['calibration']['ece']:.3f}) — under-states "
         "reliability → thresholds can be safely relaxed", 2),
        ("Correlation matrix goes singular on multi-fund books → engine falls back to independent "
         "simulation (documented; fix = regularize matrix)", 2),
        (f"End-to-end latency P50 {d3['latency']['p50']:.0f}s / P95 {d3['latency']['p95']:.0f}s — parallel "
         "extraction is the key design choice (Metric 3 met)", 2),
    ], size=12, gap=6)
    _badge(s, "built")
    _notes(s, "Show analytical maturity: we measured calibration (ECE), found the model is conservative, "
              "and we are honest about a real limitation (correlation fallback). Panels in a data-analytics "
              "program reward this kind of rigor.")

    # ---- 5. TRACTION & VALIDATION ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "Traction & market validation", kicker="EVIDENCE OF DEMAND")
    _stat_cards(s, [("7", "active pilots", "SFOs · MFOs · LPs"),
                    ("€5B+", "aggregate AUM", "across pilots"),
                    ("Top 3", "of 140+ startups", "IE Venture Day")], y=1.85)
    _bullets(s, 0.7, 3.7, 12, 3.0, [
        ("Live, deployed product with active users iterating in feedback loops", 1),
        ("Live pilot deals: F3 Finance (Belgian MFO) · BEMO Group (SFO) — signed pilot terms", 1),
        ("Institutional support:", 0, INK, True),
        ("Google Cloud for Startups — accepted & funded (infrastructure & architecture costs)", 2),
        ("LvlUp Labs Venture Accelerator — selected", 2),
        ("Best Startup — IE School of Science & Technology", 2),
        ("Demo accounts span real client archetypes (Huergo FO, Atlas MFO, F3 Finance)", 1),
    ], size=13, gap=6)
    _badge(s, "draft")
    _notes(s, "Lead with traction — it de-risks everything. 7 pilots / €5B+ AUM / Google Cloud / "
              "accelerator / award. TEAM: confirm pilot count is current and add any new logos or LOIs.")

    # ---- 5b. BUSINESS MODEL — pricing ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "Business model — six-tier SaaS pricing", kicker="REVENUE MODEL")
    _table(s, 0.7, 1.8, 8.0,
           ["Tier", "Annual (EUR)", "Users", "Funds"],
           [["UHNWI", "€5,000", "1", "15"],
            ["SFO Core", "€15,000", "5", "25"],
            ["SFO White Glove", "€30,000", "10", "75"],
            ["MFO Platform", "€50,000", "15+", "unlimited"],
            ["MFO White Glove", "€75–100K", "unlimited", "unlimited"],
            ["Enterprise", "€100–150K", "unlimited", "unlimited"]],
           col_w=[2.9, 2.1, 1.5, 1.5], fsize=11.5, row_h=0.42)
    _bullets(s, 9.0, 1.85, 3.8, 4.7, [
        ("Annual SaaS subscription by client type", 1),
        ("Add-ons: seats (€1.5–2K), funds (€200), family workspaces (€4–6K)", 1),
        ("Pilot program: 6 mo free + infra cost, converts to paid", 1),
        ("Selling now: UHNWI, SFO Core, MFO Platform", 1),
        ("White Glove / Enterprise open 2028+", 1),
    ], size=12, gap=8)
    _caption(s, "Source: vault/business/pricing-tiers.md (EUR). Gross margin 80% → 96% as base scales.")
    _badge(s, "draft")
    _notes(s, "Land-and-expand SaaS. Pilots convert to paid annual contracts. TEAM: confirm pricing is "
              "current vs the Notion source of truth before presenting.")

    # ---- 5c. UNIT ECONOMICS + P&L ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "Unit economics & 5-year financials", kicker="BUSINESS MODEL")
    _table(s, 0.7, 1.8, 12.0,
           ["", "2026", "2027", "2028", "2029", "2030"],
           [["Net revenue", "€8K", "€110K", "€556K", "€2.09M", "€4.94M"],
            ["Clients (EOY)", "7", "22", "50", "91", "141"],
            ["Gross margin", "80%", "91%", "94%", "95%", "96%"],
            ["EBIT", "-€73K", "-€239K", "-€330K", "-€89K", "+€1.23M"],
            ["LTV : CAC", "14.2x", "37.7x", "23.7x", "20.0x", "35.2x"],
            ["CAC payback", "4 mo", "4 mo", "5 mo", "7 mo", "5 mo"]],
           col_w=[3.0, 1.8, 1.8, 1.8, 1.8, 1.8], fsize=11.5, row_h=0.42)
    _stat_cards(s, [("€4.94M", "2030 net revenue", "from €8K in 2026"),
                    (">14x", "LTV:CAC every year", "capital-efficient"),
                    ("25%", "2030 EBIT margin", "profitable at scale")], y=5.3)
    _badge(s, "draft")
    _notes(s, "Pure-SaaS margins, LTV:CAC well above 3x every year, payback under a year. Path to "
              "profitability in 2030. TEAM: these are modeled projections — validate assumptions and note "
              "they update with actuals as pilots convert.")

    # ---- 5d. GO-TO-MARKET (template) ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "Go-to-market strategy", kicker="GTM · TARGET CUSTOMERS")
    _bullets(s, 0.7, 1.8, 6.0, 4.8, [
        ("Target customers (have):", 0, INK, True),
        ("Single & multi-family offices, LPs, advisory teams — EU-first", 2),
        ("Beachhead: lean MFO/SFO teams drowning in GP paperwork", 2),
        ("Motion so far (have):", 0, INK, True),
        ("Pilot partner program → warm intros to FO network", 2),
        ("Founder-led sales; bi-weekly pilot touchpoints", 2),
    ], size=12.5, gap=7)
    _bullets(s, 7.0, 1.8, 5.7, 4.8, [
        ("Scale-up GTM (TEAM to complete):", 0, RED, True),
        ("Channel strategy: outbound, partnerships, FO networks, events", 2),
        ("Sales cycle length & conversion by tier (fill from pilot data)", 2),
        ("Geographic expansion sequence beyond EU", 2),
        ("CAC by channel & payback targets", 2),
        ("Referral / network-effect loops", 2),
    ], size=12.5, gap=7)
    _badge(s, "team")
    _notes(s, "TEAM: the customer + current motion is real (pilot program, FO warm intros). Build out the "
              "scale-up GTM: channels, sales cycle, conversion rates from pilot data, expansion plan.")

    # ---- 6. ROADMAP ----
    s = _slide(prs); _bg(s, WHITE); _header(s, "Product roadmap", kicker="FUTURE DEVELOPMENT")
    phases = [
        ("NOW", TEAL, ["Ingestion pipeline (16+ types)", "Dashboard & analytics", "Monte Carlo forecasting",
                       "Daily briefing & alerts", "7 pilots live"]),
        ("NEXT (6–12 mo)", INK, ["Fee / waterfall / carry verification", "ILPA v2.0 performance logic",
                                 "Pacing & commitment engine", "EU compliance (AIFMD/SFDR/DORA)",
                                 "Convert pilots → paid"]),
        ("LATER (12–24 mo)", SLATE, ["Portfolio-company KPI pages", "Benchmarking & PME", "White-Glove & Enterprise tiers",
                                     "Geographic expansion", "[TEAM: prioritize]"]),
    ]
    x = 0.7
    for tag, color, items in phases:
        _box(s, x, 1.85, 3.9, 0.55, fill=color, rounded=True)
        _text(s, x + 0.2, 1.9, 3.5, 0.45, [[(tag, 14, WHITE, True)]], anchor=MSO_ANCHOR.MIDDLE)
        _bullets(s, x + 0.15, 2.6, 3.75, 3.8, [(it, 1) for it in items], size=11.5, gap=7)
        x += 4.07
    _badge(s, "draft")
    _notes(s, "NOW is real and shipped. NEXT maps to the competitor wedges (fee verification, ILPA, "
              "pacing, EU compliance). TEAM: confirm sequencing and dates.")

    # ---- 7. FUNDING ASK ----
    s = _slide(prs); _bg(s, INK); _header(s, "Funding requirements & use of funds", kicker="THE ASK")
    _box(s, 0.7, 1.75, 5.7, 3.1, fill=SLATE, rounded=True)
    _text(s, 1.0, 2.0, 5.1, 2.7,
          [[("Raising: €300K pre-seed", 22, WHITE, True)],
           [("23 months runway to prove product-market fit", 12.5, CLOUD, False)],
           [("", 6, CLOUD, False)],
           [("Then: €750K seed (mid-2027)", 18, TEAL_LT, True)],
           [("→ self-sustaining profitability by 2030 with €1.4M in the bank", 12.5, CLOUD, False)],
           [("Total dilutive capital to breakeven: ~€1M", 12.5, CLOUD, True)]])
    _bullets(s, 6.9, 1.85, 5.8, 3.2, [
        ("Use of pre-seed funds:", 0, TEAL_LT, True),
        ("Product development & engineering", 2, CLOUD, False),
        ("First 3 hires (eng + customer success)", 2, CLOUD, False),
        ("Pilot client onboarding & conversion", 2, CLOUD, False),
        ("Cloud infra (partly covered by Google Cloud credits)", 2, CLOUD, False),
    ], size=13, gap=8)
    _text(s, 0.7, 5.2, 12, 1.4,
          [[("Monthly burn: €3K (2026 H1) → €20K (2027) → cash-positive 2030. ", 12.5, CLOUD, False),
            ("TEAM: confirm the current ask amount, valuation, and instrument (SAFE / equity) before pitching.",
             12.5, AMBER, True)]])
    _badge(s, "draft")
    _notes(s, "The ask: €300K now (23 months), €750K seed mid-2027 to profitability. Use of funds = product, "
              "3 hires, pilot conversion. TEAM: confirm amount/valuation/instrument — these are the team's "
              "call and must be current.")

    # ---- CLOSING ----
    s = _slide(prs); _bg(s, INK)
    _box(s, 0, 3.0, 13.333, 0.05, fill=TEAL)
    _text(s, 0.9, 1.7, 11.5, 1.4,
          [[("OneLP", 40, WHITE, True)],
           [("The data-driven operating system for private markets", 20, TEAL_LT, False)]])
    _text(s, 0.9, 3.3, 11.5, 1.6,
          [[("Live product · 7 pilots · €5B+ AUM · evaluated to F1 0.968, forecast MAE "
             f"{d2['backtest']['mae_pct']*100:.1f}%, latency P50 {d3['latency']['p50']:.0f}s",
             15, CLOUD, False)],
           [("Built on real AI, validated with real clients, measured against real targets.", 14, CLOUD, False)]])
    _text(s, 0.9, 5.8, 11.5, 0.8,
          [[("Thank you  ·  Questions?", 18, WHITE, True)],
           [("Kishan · Max · Sofia · Agustin   |   info@onelp.capital", 12, MUTED, False)]])
    _notes(s, "Close on the trifecta: real AI + real clients + real measurement. Invite technical questions — "
              "the appendix deck (OneLP-Capstone-Deliverables) has the deep dive.")


def _stat_cards_right(slide, cards):
    """Three stat chips stacked on the right (for image+stats slides)."""
    x, w, y = 8.55, 4.35, 1.95
    for big, label, foot in cards:
        _box(slide, x, y, w, 1.2, fill=LIGHT, rounded=True)
        _box(slide, x, y, 0.07, 1.2, fill=TEAL)
        _text(slide, x + 0.28, y + 0.12, w - 0.5, 1.0,
              [[(big, 24, INK, True)], [(label, 12, SLATE, True), ("   " + foot, 10.5, MUTED, False)]],
              anchor=MSO_ANCHOR.MIDDLE)
        y += 1.32


def main():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    build(prs)
    out = HERE / "OneLP-Venture-Capstone-Pitch.pptx"
    prs.save(out)
    print(f"  {out.name}: {len(prs.slides._sldIdLst)} slides")

    import shutil, subprocess
    soffice = (shutil.which("soffice")
               or ("/Applications/LibreOffice.app/Contents/MacOS/soffice"
                   if Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").exists() else None))
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(HERE), str(out)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(f"  {out.stem}.pdf")
    print("Venture deck done.")


if __name__ == "__main__":
    main()
