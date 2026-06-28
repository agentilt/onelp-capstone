#!/usr/bin/env python3
"""
Deliverable 2 — Cash-Flow Forecasting with Backtesting.

Drives the faithfully-ported production Monte Carlo engine (onelp_eval.mc_engine,
a line-for-line port of src/lib/forecasting/monte-carlo.ts) over the calibrated
reference portfolio and produces:

  1. P10/P50/P90 confidence-band fan chart (proposal Deliverable 2)
  2. Backtest: hold out the most recent H quarters, forecast from prior history,
     compare P50 vs actuals -> MAE as % of quarterly cash flow (proposal Metric 2)
  3. 8-scenario stress test (base case -> liquidity crisis)               [code ships 7]
  4. Sensitivity analysis: +/-25% on three key drivers (proposal section 3B)
  5. Liquidity reserve at 90% / 95% confidence (cumulative percentiles)

Writes results JSON to results/ and figures (PNG) to figures/.
Run:  python run_backtest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "lib"))

from onelp_eval import plotting as P  # noqa: E402
from onelp_eval import portfolio as PF  # noqa: E402
from onelp_eval.mc_engine import (  # noqa: E402
    MonteCarloOptions, run_monte_carlo, SCENARIOS_BY_ID, STRESS_SCENARIOS,
    estimate_deployment_rate, estimate_distribution_rate,
)
import matplotlib.pyplot as plt  # noqa: E402

FIG = HERE / "figures"
RES = HERE / "results"
FIG.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)
P.apply_style()

CURRENT_YEAR = 2026
HIST_QUARTERS = 16          # history available per fund
HORIZON = 8                 # forecast horizon (quarters)
BACKTEST_HOLDOUT = 4        # most-recent quarters held out (proposal: 4-quarter holdout)
SIMS = 1000                 # proposal: 1,000 simulation paths
SEED = 42


def build_hist_map(funds, n_quarters):
    """Per-fund FundHistoricalData from generated cash-flow history."""
    hist_map, raw = {}, {}
    for f in funds:
        h = PF.generate_history(f, n_quarters, CURRENT_YEAR)
        raw[f.id] = h
        hist_map[f.id] = PF.history_to_fund_hist(h, f)
    return hist_map, raw


def quarter_labels(n, start_year=CURRENT_YEAR, start_q=1):
    out = []
    y, q = start_year, start_q
    for _ in range(n):
        out.append(f"{y}-Q{q}")
        q += 1
        if q > 4:
            q = 1
            y += 1
    return out


# ---------------------------------------------------------------------------
# 1 + 5. Forward forecast (fan chart) + liquidity reserve
# ---------------------------------------------------------------------------
def forward_forecast(funds, hist_map):
    opts = MonteCarloOptions(simulations=SIMS, quarters=HORIZON, seed=SEED,
                             includeCorrelation=True, confidenceLevel=0.80)
    res = run_monte_carlo(funds, hist_map, SCENARIOS_BY_ID["base"], opts, CURRENT_YEAR)
    # liquidity reserve = worst-case cumulative net outflow at confidence
    reserve_90 = float(max(0.0, -res.cum_p10.min()))   # 90% one-sided (P10 lower band)
    reserve_95 = float(max(0.0, -res.cum_p5.min()))    # 95% one-sided (P5 lower band)
    return res, reserve_90, reserve_95


# ---------------------------------------------------------------------------
# 2. Backtest
# ---------------------------------------------------------------------------
def _forecast_from_origin(funds, raw, train_q):
    """Forecast BACKTEST_HOLDOUT quarters from an expanding-window origin train_q."""
    train_hist = {}
    for f in funds:
        h = raw[f.id]
        trimmed = {"calls": h["calls"][:train_q], "distributions": h["distributions"][:train_q],
                   "net": h["net"][:train_q]}
        train_hist[f.id] = PF.history_to_fund_hist(trimmed, f)
    opts = MonteCarloOptions(simulations=SIMS, quarters=BACKTEST_HOLDOUT, seed=SEED,
                             includeCorrelation=True, confidenceLevel=0.80)
    res = run_monte_carlo(funds, train_hist, SCENARIOS_BY_ID["base"], opts, CURRENT_YEAR)
    actual_net = np.zeros(BACKTEST_HOLDOUT)
    actual_calls = np.zeros(BACKTEST_HOLDOUT)
    actual_dists = np.zeros(BACKTEST_HOLDOUT)
    for f in funds:
        h = raw[f.id]
        actual_calls += h["calls"][train_q:train_q + BACKTEST_HOLDOUT]
        actual_dists += h["distributions"][train_q:train_q + BACKTEST_HOLDOUT]
        actual_net += h["net"][train_q:train_q + BACKTEST_HOLDOUT]
    return res, actual_net, actual_calls, actual_dists


def backtest(funds):
    """
    Rolling-origin (expanding-window) backtest. For each origin train_q in
    {8..12}, train on the first train_q quarters, forecast the next
    BACKTEST_HOLDOUT quarters, and compare the P50 against held-out actuals at the
    portfolio level. Robust MAE%/coverage aggregate ~5 origins x 4 quarters; the
    plotted detail uses the most-recent origin (train_q = HIST - HOLDOUT).
    """
    hist_map, raw = build_hist_map(funds, HIST_QUARTERS)
    origins = list(range(8, HIST_QUARTERS - BACKTEST_HOLDOUT + 1))   # 8..12

    abs_err_all, gross_all, inside_all = [], [], []
    for train_q in origins:
        res, a_net, a_calls, a_dists = _forecast_from_origin(funds, raw, train_q)
        abs_err = np.abs(res.p50 - a_net)
        gross = np.abs(a_calls) + np.abs(a_dists)
        abs_err_all.extend(abs_err.tolist())
        gross_all.extend(gross.tolist())
        inside_all.extend(((a_net >= res.p10) & (a_net <= res.p90)).tolist())

    abs_err_all = np.array(abs_err_all)
    gross_all = np.array(gross_all)
    mae = float(abs_err_all.mean())
    mae_pct = float(np.mean(abs_err_all / np.where(gross_all > 0, gross_all, np.nan)))
    coverage = float(np.mean(inside_all))

    # Detail for the figure: most-recent origin
    last_train = HIST_QUARTERS - BACKTEST_HOLDOUT
    res, a_net, a_calls, a_dists = _forecast_from_origin(funds, raw, last_train)
    return {
        "labels": quarter_labels(BACKTEST_HOLDOUT, CURRENT_YEAR - 1, 1),
        "actual_net": a_net, "pred_p50": res.p50, "p10": res.p10, "p90": res.p90,
        "actual_calls": a_calls, "actual_dists": a_dists,
        "mae": mae, "mae_pct": mae_pct, "coverage_80": coverage,
        "n_origins": len(origins), "n_points": int(len(abs_err_all)),
        "train_quarters": last_train,
    }


def correlation_demo(funds):
    """
    Demonstrate the Cholesky cross-asset correlation path, which the full 16-fund
    book cannot exercise (duplicate asset-class rows -> singular matrix -> the engine
    correctly falls back to independent simulation, monte-carlo.ts:336-341).

    Build a 5-fund sub-portfolio with ONE fund per distinct correlation class so the
    5x5 matrix is positive-definite, then compare independent vs correlated runs.
    """
    from onelp_eval.mc_engine import FundInput
    demo = [
        FundInput("d_pe", "Buyout Fund", "Private Equity", 2020, 20e6, 14e6, 18e6, 0.18, 1.6, 0.4),
        FundInput("d_vce", "Seed VC Fund", "Venture Capital - Seed/Early", 2021, 10e6, 6e6, 8e6, 0.2, 1.4, 0.05),
        FundInput("d_vcg", "Growth VC Fund", "Venture Capital - Growth", 2021, 12e6, 8e6, 11e6, 0.16, 1.4, 0.1),
        FundInput("d_re", "Real Estate Fund", "Real Estate", 2020, 15e6, 11e6, 12e6, 0.12, 1.2, 0.3),
        FundInput("d_pc", "Private Credit Fund", "Private Credit", 2021, 14e6, 11e6, 11e6, 0.11, 1.2, 0.35),
    ]
    hist = {f.id: PF.history_to_fund_hist(PF.generate_history(f, HIST_QUARTERS, CURRENT_YEAR), f)
            for f in demo}
    out = {}
    for corr in (False, True):
        opts = MonteCarloOptions(simulations=SIMS, quarters=HORIZON, seed=SEED,
                                 includeCorrelation=corr, confidenceLevel=0.80)
        res = run_monte_carlo(demo, hist, SCENARIOS_BY_ID["base"], opts, CURRENT_YEAR)
        # cumulative-net distribution at the horizon
        cum_final = res.paths_cumulative[:, -1]
        out["correlated" if corr else "independent"] = {
            "p10": res.p10, "p90": res.p90, "p50": res.p50,
            "cum_final": cum_final, "used_correlation": res.used_correlation,
            "band_width": (res.p90 - res.p10),
            "cum_std": float(cum_final.std()),
        }
    return out


# ---------------------------------------------------------------------------
# 3. Stress test
# ---------------------------------------------------------------------------
def stress_test(funds, hist_map):
    rows = []
    for sc in STRESS_SCENARIOS:
        opts = MonteCarloOptions(simulations=SIMS, quarters=HORIZON, seed=SEED,
                                 includeCorrelation=True, confidenceLevel=0.80)
        res = run_monte_carlo(funds, hist_map, sc, opts, CURRENT_YEAR)
        cum_net_p50 = float(res.cum_p50[-1])
        worst_cum = float(res.cum_p5.min())
        reserve_95 = float(max(0.0, -worst_cum))
        rows.append({
            "id": sc.id, "name": sc.name, "severity": sc.severity, "category": sc.category,
            "navShock": sc.navShock, "callMultiplier": sc.callMultiplier,
            "distributionMultiplier": sc.distributionMultiplier,
            "cumulative_net_p50": cum_net_p50,
            "reserve_95": reserve_95,
            "total_calls_mean": float(res.total_calls.mean()),
            "total_dist_mean": float(res.total_distributions.mean()),
        })
    return rows


# ---------------------------------------------------------------------------
# 4. Sensitivity (+/-25% on three drivers)
# ---------------------------------------------------------------------------
def sensitivity(funds, hist_map):
    """
    Vary three key drivers by +/-25% and measure impact on cumulative net cash flow:
      - deployment (call) multiplier
      - distribution multiplier
      - NAV growth (applied as a NAV shock proxy on starting NAV)
    One-at-a-time around the base case.
    """
    base_opts = MonteCarloOptions(simulations=SIMS, quarters=HORIZON, seed=SEED,
                                  includeCorrelation=True, confidenceLevel=0.80)
    base = run_monte_carlo(funds, hist_map, SCENARIOS_BY_ID["base"], base_opts, CURRENT_YEAR)
    base_val = float(base.cum_p50[-1])

    from onelp_eval.mc_engine import Scenario
    drivers = []
    specs = [
        ("Distribution rate", "distributionMultiplier"),
        ("Capital-call rate", "callMultiplier"),
        ("NAV level", "navShock"),
    ]
    for label, attr in specs:
        lo_sc = Scenario("sens_lo", "lo", "mild", "custom", 0.0, 1.0, 1.0, 0.0)
        hi_sc = Scenario("sens_hi", "hi", "mild", "custom", 0.0, 1.0, 1.0, 0.0)
        if attr == "navShock":
            setattr(lo_sc, attr, -0.25)
            setattr(hi_sc, attr, 0.25)
        else:
            setattr(lo_sc, attr, 0.75)
            setattr(hi_sc, attr, 1.25)
        lo = run_monte_carlo(funds, hist_map, lo_sc, base_opts, CURRENT_YEAR)
        hi = run_monte_carlo(funds, hist_map, hi_sc, base_opts, CURRENT_YEAR)
        drivers.append({
            "driver": label,
            "low": float(lo.cum_p50[-1]),
            "high": float(hi.cum_p50[-1]),
            "base": base_val,
            "swing": float(hi.cum_p50[-1] - lo.cum_p50[-1]),
        })
    drivers.sort(key=lambda d: abs(d["swing"]), reverse=True)
    return base_val, drivers


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
M = 1e6


def fig_fan(res):
    labels = quarter_labels(HORIZON)
    x = np.arange(HORIZON)
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.fill_between(x, res.p10 / M, res.p90 / M, color=P.TEAL_LT, alpha=0.55, label="P10–P90")
    ax.fill_between(x, res.p25 / M, res.p75 / M, color=P.TEAL, alpha=0.35, label="P25–P75")
    ax.plot(x, res.p50 / M, color=P.INK, lw=2, marker="o", ms=4, label="P50 (median)")
    ax.axhline(0, color=P.MUTED, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Quarterly net cash flow ($M)")
    corr = "Cholesky-correlated" if res.used_correlation else "independent paths*"
    ax.set_title("Portfolio Net Cash-Flow Forecast — Monte Carlo Confidence Bands\n"
                 f"({SIMS:,} paths, {corr}, base case)")
    ax.legend(loc="upper left", ncol=3)
    P.savefig(fig, FIG / "forecast_fan_chart.png")


def fig_backtest(bt):
    x = np.arange(len(bt["labels"]))
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.fill_between(x, bt["p10"] / M, bt["p90"] / M, color=P.TEAL_LT, alpha=0.5,
                    label="Forecast P10–P90")
    ax.plot(x, bt["pred_p50"] / M, color=P.TEAL, lw=2, marker="o", ms=5, label="Forecast P50")
    ax.plot(x, bt["actual_net"] / M, color=P.RED, lw=2, marker="s", ms=5, ls="--", label="Actual")
    ax.set_xticks(x)
    ax.set_xticklabels(bt["labels"])
    ax.set_ylabel("Portfolio net cash flow ($M)")
    ax.set_title("Backtest — Forecast vs Actual (most-recent origin shown)\n"
                 f"Rolling MAE ${bt['mae']/M:.2f}M = {bt['mae_pct']*100:.1f}% of gross flow "
                 f"({bt['n_points']} pts);  80% band coverage {bt['coverage_80']*100:.0f}%")
    ax.legend(loc="best")
    P.savefig(fig, FIG / "backtest_vs_actual.png")


def fig_stress(rows):
    order = sorted(rows, key=lambda r: r["cumulative_net_p50"])
    names = [r["name"] for r in order]
    vals = [r["cumulative_net_p50"] / M for r in order]
    colors = [P.RED if r["severity"] == "severe" else P.AMBER if r["severity"] == "moderate"
              else P.TEAL for r in order]
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    y = np.arange(len(names))
    ax.barh(y, vals, color=colors)
    for yi, v in zip(y, vals):
        ax.text(v + (0.4 if v >= 0 else -0.4), yi, f"{v:,.0f}",
                va="center", ha="left" if v >= 0 else "right", fontsize=8, color=P.INK)
    ax.axvline(0, color=P.MUTED, lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("8-quarter cumulative net cash flow, P50 ($M)")
    ax.set_title("Stress-Test Scenarios — Cumulative Net Cash Flow (P50)")
    P.savefig(fig, FIG / "stress_scenarios.png")


def fig_sensitivity(base_val, drivers):
    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    y = np.arange(len(drivers))
    for yi, d in zip(y, drivers):
        lo = (d["low"] - base_val) / M
        hi = (d["high"] - base_val) / M
        ax.barh(yi, hi - lo, left=lo, color=P.TEAL, alpha=0.85, height=0.55)
        ax.text(lo, yi, f"{lo:+.0f}", va="center", ha="right", fontsize=8, color=P.RED)
        ax.text(hi, yi, f"{hi:+.0f}", va="center", ha="left", fontsize=8, color=P.GREEN)
    ax.axvline(0, color=P.INK, lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels([d["driver"] for d in drivers])
    ax.set_xlabel("Change in 8-quarter cumulative net cash flow vs base ($M)")
    ax.set_title("Sensitivity (Tornado) — ±25% on Key Drivers")
    P.savefig(fig, FIG / "sensitivity_tornado.png")


def fig_reserve(base_res, stress_res, stress_name, r90, r95):
    x = np.arange(HORIZON)
    labels = quarter_labels(HORIZON)
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    # Base case cumulative band
    ax.fill_between(x, base_res.cum_p5 / M, base_res.cum_p95 / M, color=P.TEAL_LT, alpha=0.40,
                    label="Base case P5–P95")
    ax.plot(x, base_res.cum_p50 / M, color=P.INK, lw=2, marker="o", ms=4, label="Base case P50")
    # Stressed scenario cumulative P50 + P5 (the funding-gap driver)
    ax.plot(x, stress_res.cum_p50 / M, color=P.AMBER, lw=1.8, marker="s", ms=4,
            label=f"{stress_name} P50")
    ax.plot(x, stress_res.cum_p5 / M, color=P.RED, lw=1.6, ls=":", label=f"{stress_name} P5 (95% conf)")
    gap_q = int(np.argmin(stress_res.cum_p5))
    ax.scatter([gap_q], [stress_res.cum_p5[gap_q] / M], color=P.RED, s=120, zorder=5)
    ax.annotate(f"max funding gap\n${-stress_res.cum_p5[gap_q]/M:,.1f}M",
                (gap_q, stress_res.cum_p5[gap_q] / M), textcoords="offset points",
                xytext=(8, -4), fontsize=8, color=P.RED)
    ax.axhline(0, color=P.MUTED, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Cumulative net cash flow ($M)")
    ax.set_title("Liquidity Reserve — Cumulative Net Cash Flow (Base vs Stress)\n"
                 f"Reserve under {stress_name}: ${r90/M:,.1f}M (90% conf) / ${r95/M:,.1f}M (95% conf)")
    ax.legend(loc="best", fontsize=8)
    P.savefig(fig, FIG / "liquidity_reserve.png")


def fig_correlation(demo):
    """Independent vs Cholesky-correlated aggregate distribution (5-fund demo)."""
    ind = demo["independent"]
    cor = demo["correlated"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.2, 4.4))
    # Left: distribution of horizon cumulative net cash flow
    ax1.hist(ind["cum_final"] / M, bins=40, color=P.MUTED, alpha=0.55,
             label=f"Independent (σ=${ind['cum_std']/M:.1f}M)", density=True)
    ax1.hist(cor["cum_final"] / M, bins=40, color=P.TEAL, alpha=0.55,
             label=f"Cholesky-correlated (σ=${cor['cum_std']/M:.1f}M)", density=True)
    ax1.set_xlabel("8-quarter cumulative net cash flow ($M)")
    ax1.set_ylabel("Density")
    ax1.set_title("Aggregate Outcome Distribution")
    ax1.legend(fontsize=8)
    # Right: per-quarter band width
    x = np.arange(HORIZON)
    ax2.plot(x, ind["band_width"] / M, color=P.MUTED, lw=2, marker="o", ms=4, label="Independent")
    ax2.plot(x, cor["band_width"] / M, color=P.TEAL, lw=2, marker="o", ms=4, label="Correlated")
    ax2.set_xticks(x)
    ax2.set_xticklabels(quarter_labels(HORIZON), rotation=45, ha="right")
    ax2.set_ylabel("P10–P90 band width ($M)")
    ax2.set_title("Forecast Uncertainty (band width)")
    ax2.legend(fontsize=8)
    fig.suptitle("Cross-Asset Correlation Effect (5-fund one-per-class demo) — "
                 "correlation reduces diversification, widening tails",
                 fontsize=13, fontweight="bold", y=1.03)
    P.savefig(fig, FIG / "correlation_effect.png")


def main():
    funds = PF.reference_portfolio()
    hist_map, _ = build_hist_map(funds, HIST_QUARTERS)

    res, _r90b, _r95b = forward_forecast(funds, hist_map)
    bt = backtest(funds)
    stress = stress_test(funds, hist_map)
    base_val, drivers = sensitivity(funds, hist_map)
    demo = correlation_demo(funds)

    # Reserve is meaningful under stress (a mature distributing book self-funds in base
    # case). Use the Liquidity Crisis scenario for the reserve figure + headline number.
    sc_name = "Liquidity Crisis"
    sc = SCENARIOS_BY_ID["liquidity_crisis"]
    sopts = MonteCarloOptions(simulations=SIMS, quarters=HORIZON, seed=SEED,
                              includeCorrelation=True, confidenceLevel=0.80)
    stress_res = run_monte_carlo(funds, hist_map, sc, sopts, CURRENT_YEAR)
    r90 = float(max(0.0, -stress_res.cum_p10.min()))
    r95 = float(max(0.0, -stress_res.cum_p5.min()))

    out = {
        "portfolio": {"n_funds": len(funds),
                      "total_commitment": sum(f.commitment for f in funds),
                      "total_nav": sum(f.nav for f in funds),
                      "total_unfunded": sum(f.commitment - f.paidIn for f in funds),
                      "asset_classes": sorted({f.assetClass for f in funds})},
        "config": {"simulations": SIMS, "horizon_quarters": HORIZON,
                   "history_quarters": HIST_QUARTERS, "backtest_holdout": BACKTEST_HOLDOUT,
                   "seed": SEED, "correlation_requested": True,
                   "correlation_engaged_full_portfolio": res.used_correlation},
        "forecast": {"labels": quarter_labels(HORIZON),
                     "p10": res.p10.tolist(), "p50": res.p50.tolist(), "p90": res.p90.tolist(),
                     "cum_p50": res.cum_p50.tolist(), "used_correlation": res.used_correlation},
        "reserve": {"scenario": sc_name, "reserve_90": r90, "reserve_95": r95},
        "backtest": {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in bt.items()},
        "stress": stress,
        "sensitivity": {"base_cum_p50": base_val, "drivers": drivers},
        "correlation_demo": {
            "independent_cum_std": demo["independent"]["cum_std"],
            "correlated_cum_std": demo["correlated"]["cum_std"],
            "independent_used_correlation": demo["independent"]["used_correlation"],
            "correlated_used_correlation": demo["correlated"]["used_correlation"],
            "tail_widening_pct": (demo["correlated"]["cum_std"] / demo["independent"]["cum_std"] - 1)
            if demo["independent"]["cum_std"] else 0.0,
        },
    }
    with open(RES / "forecast_metrics.json", "w") as f:
        json.dump(out, f, indent=2)

    fig_fan(res)
    fig_backtest(bt)
    fig_stress(stress)
    fig_sensitivity(base_val, drivers)
    fig_reserve(res, stress_res, sc_name, r90, r95)
    fig_correlation(demo)

    _print(out, res, demo)
    print(f"\nFigures -> {FIG}\nResults -> {RES/'forecast_metrics.json'}")


def _print(out, res, demo):
    print("=" * 64)
    print("DELIVERABLE 2 — FORECASTING + BACKTESTING")
    print("=" * 64)
    pf = out["portfolio"]
    print(f"Portfolio: {pf['n_funds']} funds, ${pf['total_commitment']/M:,.0f}M commitment, "
          f"${pf['total_unfunded']/M:,.0f}M unfunded, {len(pf['asset_classes'])} asset classes")
    print(f"Full-portfolio Cholesky correlation engaged: {res.used_correlation} "
          f"(falls back to independent — duplicate asset-class rows -> singular matrix)")
    bt = out["backtest"]
    print(f"\nRolling backtest ({bt['n_origins']} origins, {bt['n_points']} portfolio-quarter points):")
    print(f"  MAE = ${bt['mae']/M:.2f}M   MAE% (of gross flow) = {bt['mae_pct']*100:.1f}%   "
          f"target < 15%: {'PASS' if bt['mae_pct'] < 0.15 else 'MISS'}")
    print(f"  80% band empirical coverage = {bt['coverage_80']*100:.0f}%")
    rv = out["reserve"]
    print(f"\nLiquidity reserve ({rv['scenario']}): 90% conf ${rv['reserve_90']/M:,.1f}M | "
          f"95% conf ${rv['reserve_95']/M:,.1f}M")
    print("\nStress scenarios (8q cumulative net P50, $M):")
    for r in sorted(out["stress"], key=lambda r: r["cumulative_net_p50"]):
        print(f"  {r['name']:<20}{r['cumulative_net_p50']/M:>10,.1f}   reserve95 ${r['reserve_95']/M:>7,.1f}M")
    print("\nSensitivity swing ($M, ±25%):")
    for d in out["sensitivity"]["drivers"]:
        print(f"  {d['driver']:<20} swing {d['swing']/M:>8,.1f}")
    cd = out["correlation_demo"]
    print(f"\nCorrelation demo (5-fund one-per-class): engaged={cd['correlated_used_correlation']}, "
          f"tail σ widens {cd['tail_widening_pct']*100:+.1f}% vs independent")


if __name__ == "__main__":
    main()
