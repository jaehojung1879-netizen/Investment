"""Small PIT accounting/market families; no labels, sector backfill or share repair."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import dart_derive as DD
from . import replay_calendar as RC
from .alpha_opportunity_features import visible_filings

FAMILIES = {
    "VALUE": ("bookToMarketProxy", "earningsYieldProxy", "ocfYieldProxy"),
    "QUALITY": ("netIncomeToAssets", "ocfToAssets", "negativeAccrualsToAssets"),
    "CATALYST": ("relative126", "momentum121", "ocfImprovementToAssets"),
    "RISK": ("negativeDownsideVol126", "logAdv60"),
}
RAW_FEATURES = tuple(name for family in FAMILIES.values() for name in family)
STAGE = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}


def ratio(numerator, denominator):
    if numerator is None or denominator is None:
        return None
    if not np.isfinite([numerator, denominator]).all() or denominator <= 1:
        return None
    return float(numerator / denominator)


def _compatible(index, keys):
    """No CFS/OFS mix; original-XBRL per-account mixed/unknown bases abstain.

The four repaired accounts have concept lineage. v1 derives total equity from
assets minus liabilities in the SAME statement; it never trusts legacy equity.
"""
    rows = [index.get(k) for k in keys]
    if any(r is None for r in rows):
        return False
    return len({r.get("fsDiv") for r in rows}) == 1 and rows[0].get("fsDiv") in ("CFS", "OFS")


def accounting_values(records, signal_date):
    visible = visible_filings(records, signal_date, "KR")
    index = DD.index_filings(visible)
    if not index:
        return {}, {"status": "NO_VISIBLE_FILING"}
    year, stage = max(index, key=lambda k: (k[0], STAGE[k[1]]))
    current = index[(year, stage)]
    if not _compatible(index, [(year, stage)]):
        return {}, {"status": "UNKNOWN_OR_MIXED_STATEMENT_BASIS"}

    def ttm(y, s, account):
        keys = [(y, s)] if s == DD.ANNUAL else [(y, s), (y - 1, DD.ANNUAL), (y - 1, s)]
        if not _compatible(index, keys):
            return None
        return DD.trailing_twelve_months(index, y, s, account)[0]

    assets = DD.level_amount(current, "자산총계")
    liabilities = DD.level_amount(current, "부채총계")
    book = assets - liabilities if assets is not None and liabilities is not None else None
    ni = ttm(year, stage, "당기순이익")
    ocf = ttm(year, stage, "영업활동현금흐름")
    prior_ocf = ttm(year - 1, stage, "영업활동현금흐름")
    return {"assets": assets, "totalBookEquity": book, "netIncomeTtm": ni, "ocfTtm": ocf,
            "priorOcfTtm": prior_ocf}, {
        "status": "VISIBLE", "availableFrom": current["availableFrom"],
        "receiptNos": current["receiptNos"], "basis": current["fsDiv"],
        "period": [year, stage], "visibleFilings": len(visible),
        "attribution": "TOTAL_ENTITY_NUMERATORS_INCLUDING_NCI; SECURITY_CAP_PROXY_NOT_COMMON_EQUITY_RATIO"}


def downside_vol(frame, date, lookback=126):
    if frame is None or frame.empty or "Close" not in frame:
        return None
    days = RC.sessions("2013-01-01", date, "KR")[-(lookback + 1):]
    close = pd.to_numeric(frame.Close.reindex(days), errors="coerce")
    if len(close) != lookback + 1 or not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        return None
    returns = close.pct_change(fill_method=None).iloc[1:].to_numpy(float)
    # Semideviation about zero, denominator ALL 126 sessions (not negative days).
    return float(np.sqrt(np.mean(np.minimum(returns, 0)**2)) * np.sqrt(252))


def feature_at(ticker, date, records, market, frame, benchmark):
    out = {n: None for n in RAW_FEATURES}
    values, provenance = accounting_values(records, date)
    quote = market.at(ticker, date)
    cap = quote["marketCap"] if quote else None
    assets, ni, ocf = (values.get(n) for n in ("assets", "netIncomeTtm", "ocfTtm"))
    out.update(bookToMarketProxy=ratio(values.get("totalBookEquity"), cap),
               earningsYieldProxy=ratio(ni, cap), ocfYieldProxy=ratio(ocf, cap),
               netIncomeToAssets=ratio(ni, assets), ocfToAssets=ratio(ocf, assets),
               negativeAccrualsToAssets=ratio(ocf - ni if ni is not None and ocf is not None else None, assets),
               ocfImprovementToAssets=ratio(ocf - values["priorOcfTtm"]
                                           if ocf is not None and values.get("priorOcfTtm") is not None else None, assets))
    days = RC.sessions("2013-01-01", date, "KR")
    if frame is not None and benchmark is not None:
        c = pd.to_numeric(frame.Close.reindex(days), errors="coerce")
        b = pd.to_numeric(benchmark.Close.reindex(days), errors="coerce")
        if len(days) >= 127 and np.isfinite([c.iloc[-1], c.iloc[-127], b.iloc[-1], b.iloc[-127]]).all():
            if min(c.iloc[-1], c.iloc[-127], b.iloc[-1], b.iloc[-127]) > 0:
                out["relative126"] = float(c.iloc[-1] / c.iloc[-127] - b.iloc[-1] / b.iloc[-127])
        if len(days) >= 253 and np.isfinite([c.iloc[-22], c.iloc[-253]]).all() and min(c.iloc[-22], c.iloc[-253]) > 0:
            out["momentum121"] = float(c.iloc[-22] / c.iloc[-253] - 1)
    dv = downside_vol(frame, date)
    if dv is not None:
        out["negativeDownsideVol126"] = -dv
    trailing = market.trailing(ticker, date, 60)
    adv = None
    if len(trailing) == 60 and all(r is not None and r["volume"] > 0 for r in trailing):
        adv = float(np.mean([r["tradingValue"] for r in trailing]))
        out["logAdv60"] = math.log1p(adv)
    return {"date": date, "ticker": ticker, "region": "KR", **out,
            "adv60": adv, "downsideVol126": dv,
            "marketValuePresent": quote is not None,
            "tradable": quote is not None and quote["volume"] > 0 and quote["tradingValue"] > 0,
            "accountingProvenance": provenance,
            "sourceFlags": [provenance["status"], "SECTOR_HISTORY_DEFERRED", "ISSUE_CAP_ACCOUNTING_PROXY"],
            "missingFeatures": [n for n in RAW_FEATURES if out[n] is None]}
