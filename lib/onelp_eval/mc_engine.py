"""
Faithful Python port of OneLP's production Monte Carlo cash-flow engine.

Every function in this module is a line-for-line port of the TypeScript
production code so that capstone backtests exercise the *exact* algorithm that
runs in the product. Source of truth (paths relative to repo root):

  - src/lib/forecasting/monte-carlo.ts   (SeededRandom, Box-Muller, simulateFundPath,
                                           runSimulations, percentile extraction)
  - src/lib/forecasting/correlation.ts   (5x5 asset-class correlation matrix,
                                           Cholesky decomposition, correlated samples)
  - src/lib/forecasting/historical.ts    (estimateDeploymentRate / estimateDistributionRate)
  - src/lib/forecasting/scenarios.ts      (BASE + stress scenarios)

The seeded LCG and Box-Muller transform are reproduced exactly, so for a given
seed and call order the Python stream matches the TS stream. We deliberately do
NOT use numpy's RNG for the simulation core — only for post-hoc percentile math.

Citations in comments use the form  # ts: <file>:<line>
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ============================================================================
# Random Number Generation  (ts: monte-carlo.ts:37-70)
# ============================================================================

class SeededRandom:
    """Linear congruential generator. Port of monte-carlo.ts:37-49."""

    def __init__(self, seed: int):
        self.seed = int(seed) % 4294967296

    def next(self) -> float:
        # ts: monte-carlo.ts:46  this.seed = (this.seed * 1664525 + 1013904223) % 4294967296
        self.seed = (self.seed * 1664525 + 1013904223) % 4294967296
        return self.seed / 4294967296


def sample_normal(mean: float, std_dev: float, rng: SeededRandom) -> float:
    """Box-Muller normal sample. Port of monte-carlo.ts:54-59."""
    u1 = rng.next()
    u2 = rng.next()
    z0 = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    return mean + z0 * std_dev


def sample_standard_normal(rng: SeededRandom) -> float:
    """Port of monte-carlo.ts:66-70 (used for correlated shock generation)."""
    u1 = rng.next()
    u2 = rng.next()
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


# ============================================================================
# Asset-class volatility + NAV growth  (ts: monte-carlo.ts:95-131)
# ============================================================================

def get_asset_class_volatility(asset_class: str) -> dict:
    """Port of monte-carlo.ts:121-131 (getAssetClassVolatility)."""
    m = {
        "Venture Capital": {"callVol": 0.03, "distVol": 0.05},
        "Growth Equity": {"callVol": 0.025, "distVol": 0.04},
        "Private Equity": {"callVol": 0.02, "distVol": 0.03},
        "Real Estate": {"callVol": 0.015, "distVol": 0.025},
        "Infrastructure": {"callVol": 0.012, "distVol": 0.02},
        "Private Credit": {"callVol": 0.01, "distVol": 0.015},
    }
    return m.get(asset_class, {"callVol": 0.02, "distVol": 0.03})


def derive_quarterly_nav_growth(fund: "FundInput", fund_age: float) -> float:
    """Port of monte-carlo.ts:95-115 (deriveQuarterlyNavGrowth)."""
    if fund.irr and fund.irr != 0:
        annual_rate = fund.irr
        quarterly = (1 + annual_rate) ** 0.25
        return max(0.95, min(1.08, quarterly))
    if fund.tvpi and fund.tvpi > 0 and fund_age > 0:
        annual_return = fund.tvpi ** (1 / max(fund_age, 1)) - 1
        quarterly = (1 + annual_return) ** 0.25
        return max(0.95, min(1.08, quarterly))
    return 1.02


# ============================================================================
# Historical rate estimation  (ts: historical.ts:276-345)
# ============================================================================

def estimate_deployment_rate(fund_age: float, historical_rate: Optional[float]) -> float:
    """Port of historical.ts:276-299 (estimateDeploymentRate)."""
    if historical_rate is not None and historical_rate > 0:
        mean_rate = 0.05
        return historical_rate * 0.8 + mean_rate * 0.2
    if fund_age <= 2:
        return 0.08
    elif fund_age <= 4:
        return 0.05
    elif fund_age <= 6:
        return 0.03
    else:
        return 0.01


def estimate_distribution_rate(
    fund_age: float, historical_rate: Optional[float], dpi: Optional[float] = None
) -> float:
    """Port of historical.ts:305-345 (estimateDistributionRate)."""
    if historical_rate is not None and historical_rate > 0:
        mean_rate = 0.04
        base_rate = historical_rate * 0.8 + mean_rate * 0.2
    else:
        if fund_age <= 3:
            base_rate = 0.01
        elif fund_age <= 5:
            base_rate = 0.03
        elif fund_age <= 8:
            base_rate = 0.05
        else:
            base_rate = 0.07
    if dpi is not None and dpi >= 0:
        if dpi > 1.0:
            base_rate *= 1.3
        elif dpi < 0.1 and fund_age > 4:
            base_rate *= 0.5
    return base_rate


# ============================================================================
# Correlation  (ts: correlation.ts:26-257)
# ============================================================================

ASSET_CLASSES = ["PE_BUYOUT", "VC_EARLY", "VC_GROWTH", "REAL_ESTATE", "PRIVATE_CREDIT"]

# ts: correlation.ts:48-54  DEFAULT_CORRELATION_MATRIX
DEFAULT_CORRELATION_MATRIX = [
    [1.00, 0.55, 0.65, 0.35, 0.25],  # PE_BUYOUT
    [0.55, 1.00, 0.80, 0.20, 0.15],  # VC_EARLY
    [0.65, 0.80, 1.00, 0.25, 0.20],  # VC_GROWTH
    [0.35, 0.20, 0.25, 1.00, 0.40],  # REAL_ESTATE
    [0.25, 0.15, 0.20, 0.40, 1.00],  # PRIVATE_CREDIT
]


def normalize_asset_class(asset_class: str) -> str:
    """Port of correlation.ts:68-115 (normalizeAssetClass)."""
    lower = asset_class.lower().strip()
    if "buyout" in lower or lower == "pe_buyout":
        return "PE_BUYOUT"
    if "private equity" in lower and "venture" not in lower:
        return "PE_BUYOUT"
    if "early" in lower or "seed" in lower or lower == "vc_early":
        return "VC_EARLY"
    if "growth" in lower or "late" in lower or lower == "vc_growth":
        return "VC_GROWTH"
    if "venture" in lower or "vc" in lower:
        return "VC_GROWTH"
    if any(k in lower for k in ("real estate", "infrastructure", "property")) or lower == "real_estate":
        return "REAL_ESTATE"
    if any(k in lower for k in ("credit", "debt", "lending", "mezzanine")) or lower == "private_credit":
        return "PRIVATE_CREDIT"
    return "PE_BUYOUT"


def get_correlation(a: str, b: str) -> float:
    i = ASSET_CLASSES.index(normalize_asset_class(a))
    j = ASSET_CLASSES.index(normalize_asset_class(b))
    return DEFAULT_CORRELATION_MATRIX[i][j]


def build_correlation_matrix(asset_classes: list) -> list:
    """Port of correlation.ts:133-146."""
    n = len(asset_classes)
    m = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            m[i][j] = get_correlation(asset_classes[i], asset_classes[j])
    return m


def cholesky_decomposition(matrix: list) -> list:
    """Port of correlation.ts:160-191. Raises ValueError if not pos-def."""
    n = len(matrix)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = 0.0
            if i == j:
                for k in range(j):
                    s += L[j][k] * L[j][k]
                diag = matrix[j][j] - s
                if diag <= 0:
                    raise ValueError("Matrix is not positive-definite")
                L[i][j] = math.sqrt(diag)
            else:
                for k in range(j):
                    s += L[i][k] * L[j][k]
                L[i][j] = (matrix[i][j] - s) / L[j][j]
    return L


def generate_correlated_samples(cholesky_l: list, independent: list) -> list:
    """Port of correlation.ts:238-257 (L * z)."""
    n = len(cholesky_l)
    out = [0.0] * n
    for i in range(n):
        for j in range(i + 1):
            out[i] += cholesky_l[i][j] * independent[j]
    return out


# ============================================================================
# Scenarios  (ts: scenarios.ts:20-103)
# ============================================================================

@dataclass
class Scenario:
    id: str
    name: str
    severity: str
    category: str
    navShock: float
    callMultiplier: float
    distributionMultiplier: float
    reserveBufferPct: float


# ts: scenarios.ts:20-103  (BASE_SCENARIO + STRESS_SCENARIOS)
STRESS_SCENARIOS = [
    Scenario("base", "Base Case", "mild", "market", 0.0, 1.0, 1.0, 0.0),
    Scenario("mild_downturn", "Mild Downturn", "mild", "market", -0.10, 1.0, 0.85, 0.05),
    Scenario("market_correction", "Market Correction", "moderate", "market", -0.20, 1.1, 0.70, 0.10),
    Scenario("recession", "Recession", "severe", "market", -0.30, 1.25, 0.50, 0.20),
    Scenario("liquidity_crisis", "Liquidity Crisis", "severe", "liquidity", -0.25, 1.50, 0.30, 0.25),
    Scenario("credit_crunch", "Credit Crunch", "moderate", "credit", -0.15, 1.20, 0.60, 0.10),
    Scenario("rapid_recovery", "Rapid Recovery", "mild", "market", 0.15, 0.90, 1.30, 0.0),
]
SCENARIOS_BY_ID = {s.id: s for s in STRESS_SCENARIOS}


# ============================================================================
# Fund + options inputs  (ts: allocator/types + forecasting/types)
# ============================================================================

@dataclass
class FundInput:
    id: str
    name: str
    assetClass: str         # e.g. "Private Equity", "Venture Capital", ...
    vintage: int
    commitment: float
    paidIn: float
    nav: float
    irr: float = 0.0        # decimal (0.155 = 15.5%)
    tvpi: float = 0.0
    dpi: float = 0.0


@dataclass
class FundHistoricalData:
    deploymentRate: Optional[float] = None
    distributionRate: Optional[float] = None
    callStdDev: Optional[float] = None
    distStdDev: Optional[float] = None


@dataclass
class MonteCarloOptions:
    simulations: int = 1000          # proposal: 1,000 paths
    quarters: int = 8
    seed: int = 42
    includeCorrelation: bool = False   # ts default false (DEFAULT_MONTE_CARLO_OPTIONS)
    confidenceLevel: float = 0.80


# ============================================================================
# Fund simulation  (ts: monte-carlo.ts:154-225)
# ============================================================================

def simulate_fund_path(
    fund: FundInput,
    hist: Optional[FundHistoricalData],
    scenario: Scenario,
    quarters: int,
    rng: SeededRandom,
    current_year: int,
    call_shocks: Optional[list] = None,
    dist_shocks: Optional[list] = None,
):
    """Port of monte-carlo.ts:154-225 (simulateFundPath)."""
    fund_age = current_year - fund.vintage
    base_deploy = estimate_deployment_rate(fund_age, hist.deploymentRate if hist else None)
    base_dist = estimate_distribution_rate(fund_age, hist.distributionRate if hist else None, fund.dpi)

    adj_deploy = base_deploy * scenario.callMultiplier
    adj_dist = base_dist * scenario.distributionMultiplier

    vol = get_asset_class_volatility(fund.assetClass)
    call_vol = (hist.callStdDev if hist and hist.callStdDev else fund.commitment * vol["callVol"])
    dist_vol = (hist.distStdDev if hist and hist.distStdDev else fund.nav * vol["distVol"])

    calls, distributions, net = [], [], []
    remaining_unfunded = fund.commitment - fund.paidIn
    current_nav = fund.nav * (1 + scenario.navShock)

    for q in range(quarters):
        expected_call = remaining_unfunded * adj_deploy
        expected_dist = current_nav * adj_dist

        if call_shocks is not None and dist_shocks is not None:
            sampled_call = max(0.0, expected_call + call_shocks[q] * call_vol)
            sampled_call = min(sampled_call, remaining_unfunded)
            sampled_dist = max(0.0, expected_dist + dist_shocks[q] * dist_vol)
            sampled_dist = min(sampled_dist, current_nav)
        else:
            sampled_call = max(0.0, sample_normal(expected_call, call_vol, rng))
            sampled_call = min(sampled_call, remaining_unfunded)
            sampled_dist = max(0.0, sample_normal(expected_dist, dist_vol, rng))
            sampled_dist = min(sampled_dist, current_nav)

        calls.append(sampled_call)
        remaining_unfunded -= sampled_call
        distributions.append(sampled_dist)

        nav_growth = derive_quarterly_nav_growth(fund, fund_age + q / 4)
        current_nav = (current_nav - sampled_dist) * nav_growth

        net.append(sampled_dist - sampled_call)

    return {"calls": calls, "distributions": distributions, "netCashFlow": net}


def _simulate_portfolio_path(
    funds, hist_map, scenario, options, rng, cholesky_l, current_year
):
    """Port of monte-carlo.ts:242-310 (simulatePortfolioPath)."""
    quarters = options.quarters
    call_shocks_per_fund = None
    dist_shocks_per_fund = None
    if cholesky_l is not None:
        call_shocks_per_fund = [[] for _ in funds]
        dist_shocks_per_fund = [[] for _ in funds]
        for q in range(quarters):
            call_independent = [sample_standard_normal(rng) for _ in funds]
            call_correlated = generate_correlated_samples(cholesky_l, call_independent)
            dist_independent = [sample_standard_normal(rng) for _ in funds]
            dist_correlated = generate_correlated_samples(cholesky_l, dist_independent)
            for i in range(len(funds)):
                call_shocks_per_fund[i].append(call_correlated[i])
                dist_shocks_per_fund[i].append(dist_correlated[i])

    quarterly_net = [0.0] * quarters
    total_calls = 0.0
    total_dist = 0.0

    for i, fund in enumerate(funds):
        fh = hist_map.get(fund.id)
        res = simulate_fund_path(
            fund, fh, scenario, quarters, rng, current_year,
            call_shocks_per_fund[i] if call_shocks_per_fund else None,
            dist_shocks_per_fund[i] if dist_shocks_per_fund else None,
        )
        for q in range(quarters):
            quarterly_net[q] += res["netCashFlow"][q]
        total_calls += sum(res["calls"])
        total_dist += sum(res["distributions"])

    cumulative = []
    acc = 0.0
    for net in quarterly_net:
        acc += net
        cumulative.append(acc)

    return {
        "quarterlyNetCashFlows": quarterly_net,
        "cumulativeNetCashFlows": cumulative,
        "totalCalls": total_calls,
        "totalDistributions": total_dist,
    }


@dataclass
class MonteCarloResult:
    quarters: int
    p10: np.ndarray
    p25: np.ndarray
    p50: np.ndarray
    p75: np.ndarray
    p90: np.ndarray
    cum_p5: np.ndarray
    cum_p10: np.ndarray
    cum_p50: np.ndarray
    cum_p90: np.ndarray
    cum_p95: np.ndarray
    mean: np.ndarray
    paths_quarterly: np.ndarray   # (simulations, quarters) net cash flow
    paths_cumulative: np.ndarray
    total_calls: np.ndarray
    total_distributions: np.ndarray
    scenario_id: str
    used_correlation: bool


def run_monte_carlo(
    funds: list,
    hist_map: dict,
    scenario: Scenario,
    options: MonteCarloOptions,
    current_year: int = 2026,
) -> MonteCarloResult:
    """Port of runSimulations + extractPercentiles (monte-carlo.ts:316-447)."""
    rng = SeededRandom(options.seed if options.seed else 42)

    cholesky_l = None
    used_corr = False
    if options.includeCorrelation and len(funds) > 1:
        asset_classes = [f.assetClass for f in funds]
        corr = build_correlation_matrix(asset_classes)
        try:
            cholesky_l = cholesky_decomposition(corr)
            used_corr = True
        except ValueError:
            cholesky_l = None  # fall back to independent (ts: monte-carlo.ts:336-341)

    paths_q = np.empty((options.simulations, options.quarters))
    paths_c = np.empty((options.simulations, options.quarters))
    total_calls = np.empty(options.simulations)
    total_dist = np.empty(options.simulations)

    for i in range(options.simulations):
        p = _simulate_portfolio_path(
            funds, hist_map, scenario, options, rng, cholesky_l, current_year
        )
        paths_q[i] = p["quarterlyNetCashFlows"]
        paths_c[i] = p["cumulativeNetCashFlows"]
        total_calls[i] = p["totalCalls"]
        total_dist[i] = p["totalDistributions"]

    # extractPercentiles (ts: monte-carlo.ts:412-428) — per-quarter quantiles
    def q(arr, pct):
        return np.array([np.quantile(arr[:, t], pct) for t in range(options.quarters)])

    return MonteCarloResult(
        quarters=options.quarters,
        p10=q(paths_q, 0.10), p25=q(paths_q, 0.25), p50=q(paths_q, 0.50),
        p75=q(paths_q, 0.75), p90=q(paths_q, 0.90),
        cum_p5=q(paths_c, 0.05), cum_p10=q(paths_c, 0.10), cum_p50=q(paths_c, 0.50),
        cum_p90=q(paths_c, 0.90), cum_p95=q(paths_c, 0.95),
        mean=paths_q.mean(axis=0),
        paths_quarterly=paths_q, paths_cumulative=paths_c,
        total_calls=total_calls, total_distributions=total_dist,
        scenario_id=scenario.id, used_correlation=used_corr,
    )
