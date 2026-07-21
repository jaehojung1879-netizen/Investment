"""Explainability contracts for the macro and expert-consensus panels."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import expert_consensus as EC
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
    assert ".ax-detail" in styles
    assert ".cv-empty" in styles
