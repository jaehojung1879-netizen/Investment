"""Market Risk Discovery v1, Stage 1: fixed label, census reproducibility and source-ledger integrity."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from research.market_risk_discovery_v1 import baseline_census as B
from research.market_risk_discovery_v1 import label_census as L

HERE = Path(L.__file__).resolve().parent
EVID = HERE / "evidence"


def test_label_definition_is_fixed():
    assert L.THRESHOLD == -0.15 and L.HORIZON == 126


def _path():
    up = np.linspace(100, 120, 50)
    down = np.linspace(120, 95, 30)          # -20.8%: one episode
    back = np.linspace(95, 121, 40)          # recovers above 120
    again = np.linspace(121, 110, 20)        # -9%: no episode
    tr = np.concatenate([up, down, back, again])
    return [f"d{i:04d}" for i in range(len(tr))], tr


def test_episode_starts_at_first_passage_and_ends_at_full_recovery():
    dates, tr = _path()
    eps, active = L.episodes(dates, tr)
    assert len(eps) == 1
    start = dates.index(eps[0]["start"])
    assert tr[start] / tr[:start + 1].max() - 1 <= -0.15 < tr[start - 1] / tr[:start].max() - 1
    rec = dates.index(eps[0]["recovered"])
    assert tr[rec] >= 120 and all(active[start:rec]) and not active[rec]


def test_episode_start_does_not_depend_on_future_data():
    dates, tr = _path()
    full, _ = L.episodes(dates, tr)
    cut = dates.index(full[0]["start"]) + 1
    short, _ = L.episodes(dates[:cut], tr[:cut])
    assert short[0]["start"] == full[0]["start"]


def test_labels_exclude_active_sessions_and_censor_the_tail():
    dates, tr = _path()
    eps, active = L.episodes(dates, tr)
    y = L.labels(dates, active, eps, horizon=10)
    start = dates.index(eps[0]["start"])
    assert y[start - 1] == 1 and y[start - 10] == 1 and y[start - 11] == 0
    assert all(v is None for v, a in zip(y, active) if a)
    assert y[-1] is None and y[-11] == 0


def test_episode_power_matches_the_exact_binomial():
    p = L.episode_power(7, 0.2, (0.5, 0.7))
    assert p["criticalHits"] == 4 and p["sizeAtCritical"] <= 0.05
    assert p["power"]["0.5"] == pytest.approx(0.5)


def test_fast_state_counts_trend_and_volatility():
    close = np.concatenate([np.full(220, 100.0), np.full(10, 90.0)])
    s = B.fast_state(close)
    assert s[198] is None and s[219] == 0 and s[229] >= 1


def test_alfred_ledgers_are_complete_real_time_and_hash_pinned():
    audit = json.loads((EVID / "us-source-audit.json").read_text())
    for series in ("BAA", "GS10"):
        path = HERE / "data" / f"alfred-{series}-asof-month-ends.csv"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == audit["alfred"][series]["ledger"]["sha256"]
        rows = list(csv.DictReader(path.open()))
        assert len(rows) == 359 and rows[0]["decisionDate"] == "1996-12-31" and rows[-1]["decisionDate"] == "2026-10-30"
        for r in rows:
            assert r["value"] not in ("", "None")
            assert r["servedVintage"] <= r["vintageRequested"] < r["decisionDate"]
            assert r["observationDate"] < r["decisionDate"]
        assert audit["alfred"][series]["firstVintage"] == "1996-12-03"


def test_spy_issuer_distributions_and_reconciliation_recorded():
    audit = json.loads((EVID / "us-source-audit.json").read_text())["spy"]
    assert audit["sessions"]["missingXnysSessions"] == 0
    assert audit["distributions"]["matchedDates"] == 136 and not audit["distributions"]["issuerOnly"]
    rows = list(csv.DictReader((HERE / "data/ssga-SPY-distributions.csv").open()))
    assert len(rows) == 136
    assert abs(audit["trReconciliationWithRepositoryLedger"]["cumulativeRatio"] - 1) < 0.002


def test_label_census_reproduces_from_committed_data():
    committed = json.loads((EVID / "label-census.json").read_text())
    for key, first in (("full", None), ("pitCreditWindow", "1997-01-31")):
        again = L.census(first)
        assert again == committed[key]
    assert committed["full"]["independentEpisodes"] == 7 and committed["signalReads"] == 0


def test_baseline_census_reproduces_and_reads_no_credit_label():
    committed = json.loads((EVID / "baseline-census.json").read_text())
    again = B.build()
    again["candidateCreditFlags"] = B.candidate_credit_flags()
    assert json.loads(json.dumps(again, sort_keys=True)) == committed
    assert committed["creditLabelReads"] == 0 and committed["eligibleEpisodes"] == 7


def test_knowledge_ledger_uses_the_registered_vocabulary():
    ledger = json.loads((HERE / "knowledge-ledger.json").read_text())
    vocab = set(ledger["statusVocabulary"])
    for item in ledger["economicFacts"] + ledger["failedClaims"]:
        assert item["status"] in vocab
