---
title: "OneLP — Venture Capstone Deliverables Checklist"
subtitle: "Mapping to Dae-Jin Lee's requirements (June 2026)"
date: "June 2026"
---

# Venture Capstone — Deliverables Checklist

This maps every requirement in Prof. Dae-Jin Lee's guidance to a concrete artifact in
this repo, with status. **Legend:** ✅ built from repo · 🟠 drafted from repo data, team
to validate · 🔴 team to complete (needs external research or a strategic decision).

## Required deliverables

| Requirement | Artifact | Status |
|---|---|:--:|
| **Final presentation / pitch** (primary) | `slides/OneLP-Venture-Capstone-Pitch.pptx` (+ `.pdf`) — 19 slides, 7-section flow, presenter notes embedded | ✅ |
| Presentation slides | same file; technical-deep-dive backup: `slides/OneLP-Capstone-Deliverables.pptx` | ✅ |
| Working MVP / prototype | Live deployed platform + seeded demo accounts (Huergo FO, F3 Finance MFO, Atlas MFO). **Team:** confirm live + record fallback video | 🟠 |
| Code repository access | This repository (`OneLPMVP`) — pipeline `src/lib/documents/`, forecasting `src/lib/forecasting/`, evaluation `capstone/` | ✅ |
| Supporting: technical implementation | `capstone/` — 3 evaluation deliverables (reports, notebooks, figures, results) | ✅ |
| Supporting: customer validation | Traction slide + `vault/business/` (pilots, deals); **team:** confirm current pilot list / add LOIs | 🟠 |
| Supporting: market research | TAM/SAM/SOM + sourced market evidence | 🔴 |

## 7-section flow — coverage

| # | Section | Slides | Status | Notes |
|---|---|---|:--:|---|
| 1 | Team & problem statement | 2–3 | ✅ / 🟠 | Problem fully built; **team: add founder roles/bios** |
| 2 | Market opportunity & value proposition | 4–6 | 🟠 / 🔴 | Value prop + competitive landscape ✅; **TAM/SAM/SOM 🔴** |
| 3 | Product & MVP demonstration | 7–8 | ✅ | Live-demo script + extraction workflow |
| 4 | Technical implementation | 9–12 | ✅ | Architecture + ML/DS (extraction, forecasting, calibration), rationale, lessons |
| 5 | Business model & go-to-market | 13–16 | 🟠 / 🔴 | Pricing, unit econ, financials, traction drafted; **scale-up GTM 🔴** |
| 6 | Future roadmap | 17 | 🟠 | NOW shipped; **team: confirm NEXT/LATER sequencing & dates** |
| 7 | Funding requirements & use of funds | 18 | 🟠 | €300K pre-seed + €750K seed drafted; **team: confirm amount/valuation/instrument** |

## What the team still needs to complete (the 🔴 / 🟠 items)

1. **Founder roles & one-line bios** (slide 2) — replace placeholders.
2. **TAM / SAM / SOM** (slide 4) — insert figures with one cited source each (Preqin,
   Campden Wealth, Deloitte family-office reports). The funnel scaffold and methodology
   are already laid out.
3. **Scale-up GTM** (slide 16) — channels, sales-cycle length & conversion by tier (pull
   from pilot data), expansion sequence, CAC by channel.
4. **Funding ask confirmation** (slide 18) — confirm the current amount, valuation, and
   instrument (SAFE / equity). Draft uses the repo's €300K pre-seed + €750K seed scenario.
5. **Validate the 🟠 business numbers** (pricing, unit economics, financials, pilots)
   against the Notion sources of truth before presenting — they are drafted from
   `vault/business/` and may be dated.
6. **MVP demo** — confirm the deployed platform is live, rehearse the 5-step demo flow,
   and record a fallback screen capture.

## Technical contribution — already evaluated (the panel will probe this)

Built and measured against the proposal's quantitative targets:

| Metric | Target | Result | Where |
|---|---|---|---|
| Extraction F1 (hybrid) | ≥ 0.90 / crit ≥ 0.95 | **0.968 / 0.968** | Deliverable 1 |
| Forecast MAE | < 15% | **5.0%** | Deliverable 2 |
| End-to-end latency | P50 < 30s / P95 < 90s | **24s / 29s** | Deliverable 3 |

Full reports: `capstone/reports/OneLP-Capstone-POC-Deliverables.pdf`. Reproduce
everything with `cd capstone && ./build.sh`.
