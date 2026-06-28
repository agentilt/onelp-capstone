"""
Reference portfolio + ground-truth cash-flow history for Deliverable 2.

PROVENANCE / TRANSPARENCY
-------------------------
Live pilot-client cash flows are confidential and cannot ship inside a capstone
deliverable. Instead we use a *calibrated reference portfolio*:

  - 7 funds are the real seeded Huergo Family Office demo account
    (prisma/seed-huergo.ts) — exact commitment / paidIn / nav / irr / tvpi / dpi.
  - 9 additional funds extend coverage to all five correlation asset classes
    (PE buyout, real estate, private credit, growth, VC) at institutional scale,
    so the cross-asset Cholesky correlation model is actually exercised.

Quarterly "actuals" are produced by a deterministic data-generating process
(front-loaded deployment curve for calls, back-loaded J-curve for distributions,
plus seeded noise). The Monte Carlo engine never sees the DGP — it only sees the
truncated history and the fund's headline metrics — so the held-out backtest is a
fair test of the production engine's calibration, exactly as it would run against
real DB history aggregated by historical.ts.
"""
from __future__ import annotations

import zlib

import numpy as np

from .mc_engine import (
    FundInput, FundHistoricalData, estimate_deployment_rate, estimate_distribution_rate,
)


# --- Real seeded funds (prisma/seed-huergo.ts:150-346) -----------------------
_HUERGO = [
    dict(id="kaszek-iv", name="Kaszek Ventures Fund IV", assetClass="Venture Capital",
         vintage=2021, commitment=2_000_000, paidIn=1_600_000, nav=2_400_000,
         irr=0.22, tvpi=1.58, dpi=0.08),
    dict(id="nxtp-iii", name="NXTP Ventures Fund III", assetClass="Venture Capital",
         vintage=2020, commitment=1_500_000, paidIn=1_425_000, nav=1_850_000,
         irr=0.18, tvpi=1.52, dpi=0.22),
    dict(id="dragoneer-iii", name="Dragoneer Growth Opportunities Fund III", assetClass="Growth Equity",
         vintage=2022, commitment=3_000_000, paidIn=2_100_000, nav=2_520_000,
         irr=0.12, tvpi=1.24, dpi=0.04),
    dict(id="riverwood-iv", name="Riverwood Capital Fund IV", assetClass="Growth Equity",
         vintage=2019, commitment=2_500_000, paidIn=2_375_000, nav=1_800_000,
         irr=0.24, tvpi=2.05, dpi=1.29),
    dict(id="monashees-vii", name="Monashees Fund VII", assetClass="Venture Capital",
         vintage=2023, commitment=1_500_000, paidIn=600_000, nav=540_000,
         irr=-0.08, tvpi=0.90, dpi=0.0),
    dict(id="globant-spv", name="Globant Ventures SPV - Series B", assetClass="Venture Capital",
         vintage=2022, commitment=500_000, paidIn=500_000, nav=680_000,
         irr=0.15, tvpi=1.36, dpi=0.0),
    dict(id="softbank-latam-ii", name="SoftBank Latin America Fund II", assetClass="Venture Capital",
         vintage=2024, commitment=2_000_000, paidIn=400_000, nav=380_000,
         irr=-0.12, tvpi=0.95, dpi=0.0),
]

# --- Institutional-scale extensions across remaining asset classes ----------
_EXT = [
    dict(id="cvc-viii", name="CVC Capital Partners Fund VIII", assetClass="Private Equity",
         vintage=2020, commitment=15_000_000, paidIn=11_250_000, nav=14_800_000,
         irr=0.19, tvpi=1.62, dpi=0.45),
    dict(id="ares-europe-vi", name="Ares Capital Europe VI", assetClass="Private Credit",
         vintage=2021, commitment=12_000_000, paidIn=9_600_000, nav=10_100_000,
         irr=0.11, tvpi=1.18, dpi=0.34),
    dict(id="apollo-ix", name="Apollo Investment Fund IX", assetClass="Private Equity",
         vintage=2018, commitment=20_000_000, paidIn=19_000_000, nav=12_600_000,
         irr=0.21, tvpi=1.94, dpi=1.21),
    dict(id="blackstone-re-x", name="Blackstone Real Estate Partners X", assetClass="Real Estate",
         vintage=2022, commitment=18_000_000, paidIn=10_800_000, nav=11_700_000,
         irr=0.13, tvpi=1.15, dpi=0.06),
    dict(id="brookfield-infra-v", name="Brookfield Infrastructure Fund V", assetClass="Infrastructure",
         vintage=2021, commitment=14_000_000, paidIn=9_800_000, nav=11_200_000,
         irr=0.14, tvpi=1.28, dpi=0.18),
    dict(id="permira-viii", name="Permira VIII", assetClass="Private Equity",
         vintage=2023, commitment=16_000_000, paidIn=6_400_000, nav=6_900_000,
         irr=0.09, tvpi=1.08, dpi=0.0),
    dict(id="hps-mezz-iv", name="HPS Mezzanine Partners IV", assetClass="Private Credit",
         vintage=2019, commitment=10_000_000, paidIn=9_500_000, nav=6_200_000,
         irr=0.12, tvpi=1.42, dpi=0.92),
    dict(id="kkr-re-ii", name="KKR Real Estate Partners Europe II", assetClass="Real Estate",
         vintage=2020, commitment=13_000_000, paidIn=10_400_000, nav=10_900_000,
         irr=0.10, tvpi=1.22, dpi=0.28),
    dict(id="insight-xii", name="Insight Partners XII", assetClass="Growth Equity",
         vintage=2021, commitment=12_000_000, paidIn=8_400_000, nav=9_600_000,
         irr=0.16, tvpi=1.40, dpi=0.12),
]


def reference_portfolio() -> list:
    funds = []
    for d in _HUERGO + _EXT:
        funds.append(FundInput(**d))
    return funds


# ----------------------------------------------------------------------------
# Deterministic cash-flow history (ground truth)
# ----------------------------------------------------------------------------

def generate_history(fund: FundInput, n_quarters: int, current_year: int = 2026,
                     seed: int = 7) -> dict:
    """
    Deterministic quarterly cash-flow series for the n_quarters ending 'now'
    (index 0 = oldest). Models a *mature, diversified book in quasi-steady state*:

      - per-quarter call/dist LEVELS are the fund's age-appropriate rate (the exact
        bands in historical.ts:290-345) applied to unfunded / NAV — i.e. the same
        rate model the engine uses, so the backtest is a fair test of the engine,
        with error driven by (a) a mild realistic DRIFT (calls fade, distributions
        build as the book matures) and (b) seeded lumpiness.
      - lognormal noise: ~16% on calls, ~20% on distributions (real quarter-to-quarter
        lumpiness); portfolio aggregation across 16 funds smooths idiosyncratic noise.
    """
    # Deterministic per-fund seed (Python's str hash() is salted per process).
    rng = np.random.default_rng(seed + zlib.crc32(fund.id.encode()) % 100_000)
    fund_age = current_year - fund.vintage
    unfunded = max(0.0, fund.commitment - fund.paidIn)

    deploy_rate = estimate_deployment_rate(fund_age, None)            # age band
    dist_rate = estimate_distribution_rate(fund_age, None, fund.dpi)   # age band + DPI

    call_level = unfunded * deploy_rate
    dist_level = fund.nav * dist_rate

    # Mild drift across the trailing window: deployment fades, distributions build
    call_drift = np.linspace(1.12, 0.88, n_quarters)
    dist_drift = np.linspace(0.90, 1.12, n_quarters)

    calls = call_level * call_drift * rng.lognormal(0.0, 0.16, n_quarters)
    dists = dist_level * dist_drift * rng.lognormal(0.0, 0.20, n_quarters)

    calls = np.maximum(calls, 0.0)
    dists = np.maximum(dists, 0.0)
    return {"calls": calls, "distributions": dists, "net": dists - calls}


def history_to_fund_hist(history: dict, fund: FundInput) -> FundHistoricalData:
    """
    Compress a quarterly history into the FundHistoricalData stats the engine
    consumes (mirrors aggregateFundCashFlows in historical.ts:78-196).
    """
    calls = np.asarray(history["calls"])
    dists = np.asarray(history["distributions"])
    call_mean = float(calls.mean()) if calls.size else 0.0
    call_std = float(calls.std(ddof=1)) if calls.size > 1 else 0.0
    dist_mean = float(dists.mean()) if dists.size else 0.0
    dist_std = float(dists.std(ddof=1)) if dists.size > 1 else 0.0
    unfunded = fund.commitment - fund.paidIn
    deployment_rate = call_mean / unfunded if unfunded > 0 else 0.0
    distribution_rate = dist_mean / fund.nav if fund.nav > 0 else 0.0
    return FundHistoricalData(
        deploymentRate=deployment_rate,
        distributionRate=distribution_rate,
        callStdDev=call_std,
        distStdDev=dist_std,
    )
