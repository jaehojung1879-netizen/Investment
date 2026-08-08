"""Explainability contracts for the macro and expert-consensus panels."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import expert_consensus as EC
from pipeline import indices as IDX
from pipeline import regime as RG


ROOT = Path(__file__).resolve().parents[1]


def test_transition_distinguishes_mixed_signals_from_low_confidence():
    growth = {"value": 0.5, "direction": "positive", "confidence": 0.75,
              "labelKo": "가속"}
    inflation = {"value": 0.0, "direction": "flat", "confidence": 0.5,
                 "labelKo": "보합/상쇄"}

    decision = RG._regime_decision(growth, inflation)

    assert decision["label"] == "Transition/Low confidence"
    assert decision["displayLabelKo"] == "전환·신호 상쇄"
    assert decision["reasonCode"] == "INFLATION_MIXED"
    assert "물가" in decision["summaryKo"]
    assert decision["thresholds"] == {
        "minimumConfidence": 0.34,
        "directionAbsMin": 0.15,
    }


def test_indicator_read_carries_human_readable_method_and_signal():
    idx = pd.date_range("2020-01-31", periods=30, freq="ME")
    values = np.r_[100 * (1.015 ** np.arange(18)),
                   100 * (1.015 ** 17) * (1.002 ** np.arange(1, 13))]

    read = RG.indicator_read(
        "Core_CPI", pd.Series(values, index=idx),
        asof=idx[-1] + pd.Timedelta(days=30),
    )

    assert read["displayNameKo"] == "근원 소비자물가"
    assert "전년동월비" in read["transformationKo"]
    assert read["valueUnit"] == "%"
    assert "물가 둔화 기여" in read["signalSummaryKo"]
    assert read["observationDate"] and read["releaseLagBdays"] == 12
    assert len(read["history"]) >= 12
    assert {"meaningKo", "readKo", "useKo", "cautionKo"} <= set(read["guide"])


def test_cfnai_exposes_monthly_and_smoothed_trend_with_reference_lines():
    idx = pd.date_range("2022-01-31", periods=40, freq="ME")
    values = pd.Series(np.sin(np.arange(40) / 4), index=idx)

    read = RG.indicator_read("CFNAI", values, asof=idx[-1] + pd.Timedelta(days=30))

    assert read["history"] and read["trendHistory"]
    assert read["trendLabelKo"] == "3개월 이동평균"
    assert {x["value"] for x in read["referenceLines"]} == {0.0, -0.7}
    assert "85개" in read["guide"]["meaningKo"]


def test_index_summary_carries_dated_history_and_freshness():
    idx = pd.bdate_range("2025-01-02", periods=300)
    close = pd.Series(np.linspace(2500, 3100, len(idx)), index=idx)
    spec = next(x for x in IDX.SPEC if x["symbol"] == "^KS11")
    now = idx[-1].tz_localize("Asia/Seoul") + pd.Timedelta(hours=18)

    row = IDX.summarize_close(spec, close, "TEST", now=now)

    assert row["history"][-1] == {"date": idx[-1].strftime("%Y-%m-%d"), "value": 3100.0}
    assert len(row["history"]) == IDX.HISTORY_POINTS
    assert row["freshnessStatus"] == "CURRENT"
    assert row["critical"] is True
    assert row["sparkPeriod"] == "3M"
    assert row["sparkPoints"] == IDX.SPARK_POINTS == len(row["spark"])
    assert row["sparkStartDate"] == idx[-IDX.SPARK_POINTS].strftime("%Y-%m-%d")
    assert row["sparkEndDate"] == row["asOf"]
    expected_3m = round((close.iloc[-1] / close.iloc[-IDX.SPARK_POINTS] - 1) * 100, 2)
    assert row["chg3mPct"] == expected_3m


def test_index_return_windows_are_backend_calculated():
    idx = pd.bdate_range("2025-01-02", periods=300)
    close = pd.Series(100 + np.arange(len(idx), dtype=float), index=idx)
    spec = next(x for x in IDX.SPEC if x["symbol"] == "^GSPC")
    now = idx[-1].tz_localize("America/New_York") + pd.Timedelta(hours=19)

    row = IDX.summarize_close(spec, close, "TEST", now=now)

    assert row["chg1dPct"] == round((close.iloc[-1] / close.iloc[-2] - 1) * 100, 2)
    assert row["chg1mPct"] == round((close.iloc[-1] / close.iloc[-22] - 1) * 100, 2)
    assert row["chg3mPct"] == round((close.iloc[-1] / close.iloc[-63] - 1) * 100, 2)
    prior_year_last = close[close.index.year < close.index[-1].year].iloc[-1]
    assert row["ytdPct"] == round((close.iloc[-1] / prior_year_last - 1) * 100, 2)


def test_us_completed_session_is_required_by_breakfast_kst():
    # 07:10 KST is late enough that the just-completed US session must be the
    # expected date in both EST and EDT. A prior business-day row is delayed.
    now = pd.Timestamp("2026-01-06 07:10", tz="Asia/Seoul")
    expected = IDX._expected_market_date("US", now)
    assert expected.strftime("%Y-%m-%d") == "2026-01-05"
    lag, status, _ = IDX._freshness(pd.Timestamp("2026-01-02"), "US", now)
    assert lag == 1 and status == "DELAYED"


def test_expert_queue_explains_exactly_why_consensus_is_empty():
    sources = {"sources": [{
        "id": "alpha", "institution": "Alpha Research",
        "sourceType": "sellSideResearch", "weight": 1.0,
    }]}
    views = {"views": [{
        "id": "alpha-outlook", "sourceId": "alpha", "title": "2026 Outlook",
        "theme": "US Growth", "verified": False, "publishedAt": None,
        "verifiedAt": None, "stance": None, "summary": None,
        "url": "https://example.com/outlook", "staleAfterDays": 90,
        "risks": ["고용 둔화"], "signposts": ["고용"],
    }]}

    out = EC.build(
        sources=sources, views=views,
        now=datetime(2026, 7, 22, tzinfo=timezone.utc),
    )

    assert out["available"] is False and out["themes"] == []
    assert out["candidateCount"] == 1
    assert out["awaitingCount"] == 1
    assert out["verificationCoverage"] == 0.0
    queued = out["awaitingVerification"][0]
    assert queued["statusCode"] == "UNVERIFIED"
    assert queued["title"] == "2026 Outlook"
    assert set(queued["missingFields"]) == {
        "publishedAt", "verifiedAt", "stance", "summary", "verified",
    }


def test_frontend_surfaces_regime_rule_and_consensus_exclusion_details():
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "styles.css").read_text(encoding="utf-8")

    assert "왜 이 국면인가" in app
    assert "signalSummaryKo" in app
    assert "판정에 직접 사용" in app
    assert "검증된 컨센서스가 아직 없는 이유" in app
    assert "missingFields" in app
    assert "showIndexDialog" in app
    assert "이 지표는 무엇을 뜻하나?" in app
    assert "성장 × 물가 국면 지도" in app
    assert ".ax-detail" in styles
    assert ".cv-empty" in styles
    assert ".index-dialog" in styles
