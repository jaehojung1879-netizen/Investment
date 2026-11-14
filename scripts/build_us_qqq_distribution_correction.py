"""Rebuild the QQQ research benchmark with the verified September 2020 distribution."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_dual_benchmark_data as D  # noqa: E402
from pipeline import us_spy_qqq_comparison as C  # noqa: E402
from scripts import build_us_dual_benchmark_foundation as foundation  # noqa: E402

EX_DATE = pd.Timestamp("2020-09-21")
DIVIDEND = 0.38824
OUTPUT = ROOT / "docs/us-readiness/us-qqq-distribution-correction-v1.json"


def corrected_qqq(qqq: pd.DataFrame) -> pd.Series:
    """Validate the old adjustment basis, then apply the missing cash event once."""
    if not qqq.index.is_monotonic_increasing or qqq.index.has_duplicates:
        raise ValueError("UNSORTED_OR_DUPLICATE_QQQ_SESSIONS")
    if EX_DATE not in qqq.index:
        raise ValueError("QQQ_EX_DATE_MISSING")
    events = qqq[["dividend", "split"]].copy()
    if events.at[EX_DATE, "dividend"] != 0:
        raise ValueError("QQQ_DISTRIBUTION_ALREADY_PRESENT")
    raw = qqq["rawClose"]
    reconstructed = D.apply_distributions(raw, events, basis=D.BASIS_RAW)
    if not np.allclose(reconstructed, qqq["totalReturnClose"], rtol=1e-9, atol=0):
        raise ValueError("QQQ_ORIGINAL_TOTAL_RETURN_BASIS_MISMATCH")
    events.at[EX_DATE, "dividend"] = DIVIDEND
    return D.apply_distributions(raw, events, basis=D.BASIS_RAW)


def build_correction() -> dict:
    snapshot = D.read_snapshot(foundation.SNAPSHOT)
    spy = snapshot[snapshot.ticker == "SPY"].set_index("date")
    qqq = snapshot[snapshot.ticker == "QQQ"].set_index("date")
    revised = corrected_qqq(qqq)
    rates = json.loads(foundation.RATES.read_bytes())
    comparisons = {}
    for name, (start, end) in {
        "headline": C.HEADLINE_WINDOW,
        "full": (qqq.index[0].date().isoformat(), qqq.index[-1].date().isoformat()),
    }.items():
        comparisons[name] = C.compare(
            spy["totalReturnClose"], revised, start=start, end=end, fx=spy["usdKrw"],
            usd_rate=rates["usdFedFundsPct"], krw_rate=rates["krwPolicyRatePct"],
            costs=foundation.config_costs(),
        )
        if name == "full":
            comparisons[name].pop("weekly")
    return {
        "id": "us-qqq-distribution-correction-v1",
        "evidenceClass": "DESCRIPTIVE_ETF_COMPARISON_NOT_ALPHA",
        "officialUsBenchmark": "SPY",
        "growthAlternative": "QQQ",
        "snapshot": {"path": str(foundation.SNAPSHOT.relative_to(ROOT)),
                     "sha256": foundation.sha256(foundation.SNAPSHOT)},
        "rates": {"path": str(foundation.RATES.relative_to(ROOT)),
                  "sha256": foundation.sha256(foundation.RATES)},
        "correction": {
            "exDate": EX_DATE.date().isoformat(), "cashPerShareUsd": DIVIDEND, "payDate": "2020-10-30",
            "status": "VERIFIED_MISSING_CASH_DISTRIBUTION",
            "sources": [
                "https://www.sec.gov/Archives/edgar/data/831001/000095010320018722/dp137343_424b2-us2014449.htm",
                "https://chartexchange.com/symbol/nasdaq-qqq/historical/dividends/",
                "https://twelvedata.com/markets/958673/etf/nasdaq/qqq/historical-data/dividends",
            ],
        },
        "limits": ["Research comparison uses the pinned SPY series and the corrected QQQ dividend recipe.",
                   "The source snapshot's other distribution amounts retain vendor precision."],
        **comparisons,
    }


if __name__ == "__main__":
    foundation.dump(OUTPUT, build_correction())
