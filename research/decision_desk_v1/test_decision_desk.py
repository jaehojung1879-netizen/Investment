"""decision-desk-v1 tests (pytest -q research/decision_desk_v1). Synthetic fixtures plus the committed dry-run."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import evidence as E  # noqa: E402
import judgment as J  # noqa: E402
import ledger as L  # noqa: E402
import validate_desk as V  # noqa: E402


def _record(**over):
    r = {"schema": L.SCHEMA, "region": "US", "path": "B2", "cohort": "2099-01", "signalAsOf": "2099-01-02",
         "informationCutoff": "2099-01-02", "generatedAt": "2099-01-03T00:00:00Z", "publishedAt": "2099-01-03T01:00:00Z",
         "modelVersion": "t", "sourceHashes": {"x": "y"}, "selectedTickers": ["AAA"], "weights": {"AAA": 0.1, "SPY": 0.9},
         "benchmark": "SPY", "investmentThesis": "t", "invalidationConditions": {}, "plannedExecution": "2099-01-05",
         "plannedExecutionCloseUtc": "2099-01-05T21:00:00Z", "costs": {"stockRoundTripPct": 0.2, "benchmarkRoundTripPct": 0.1},
         "horizon126": None, "horizon252": None, "subsequentReturns": None, "status": "DRY_RUN_NOT_ACTIVATED",
         "missingDataReason": None}
    r.update(over)
    return r


@pytest.fixture
def dry(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    return tmp_path / "ledger.jsonl"


# ----------------------------------------------------------------------------- ledger
def test_append_chains_and_verifies(dry):
    a = L.append(dry, _record())
    b = L.append(dry, _record(path="B0", selectedTickers=[], weights={"SPY": 1.0}))
    assert b["prevDigest"] == a["digest"] and a["prevDigest"] == L.GENESIS
    L.verify_chain(L.read(dry))


def test_edit_or_delete_is_detected(dry):
    L.append(dry, _record())
    L.append(dry, _record(path="B0", selectedTickers=[], weights={"SPY": 1.0}))
    lines = dry.read_text().splitlines()
    edited = json.loads(lines[0])
    edited["weights"] = {"SPY": 1.0}
    edited["selectedTickers"] = []
    dry.write_text(json.dumps(edited) + "\n" + lines[1] + "\n")
    with pytest.raises(L.LedgerError):
        L.verify_chain(L.read(dry))
    dry.write_text(lines[1] + "\n")  # deleting the first record breaks the chain
    with pytest.raises(L.LedgerError):
        L.verify_chain(L.read(dry))


def test_duplicate_cohort_and_activation_are_refused(dry, tmp_path):
    L.append(dry, _record())
    with pytest.raises(L.LedgerError, match="DUPLICATE"):
        L.append(dry, _record())
    with pytest.raises(L.LedgerError, match="OWNER_APPROVAL"):
        L.append(tmp_path.parent / "elsewhere.jsonl", _record())


@pytest.mark.parametrize("over, msg", [
    ({"generatedAt": "2099-01-01T00:00:00Z"}, "TIME_ORDER"),
    ({"plannedExecutionCloseUtc": "2099-01-03T00:30:00Z"}, "EXECUTION_NOT_AFTER"),
    ({"weights": {"AAA": 0.5, "SPY": 0.4}}, "SUM_TO_ONE"),
    ({"horizon126": 1.0}, "FUTURE_FIELDS"),
    ({"investmentThesis": {"probability": 0.6}}, "FORBIDDEN"),
    ({"selectedTickers": ["A", "B", "C", "D", "E", "F"], "weights": {"A": .1, "B": .1, "C": .1, "D": .1, "E": .1, "F": .1, "SPY": .4}}, "EXCEED_5"),
])
def test_invalid_records_are_refused(dry, over, msg):
    with pytest.raises(L.LedgerError, match=msg):
        L.append(dry, _record(**over))


def test_evaluation_waits_for_the_horizon_and_never_zero_fills(dry):
    rec = L.append(dry, _record())
    sessions = [f"2099-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
    sessions = sessions[sessions.index("2099-01-05"):]
    tr = {"AAA": 0.20, "SPY": 0.10}
    pending = L.evaluate(rec, 126, sessions, lambda t, s, e: tr[t], observed_at="2099-02-01T00:00:00Z")
    assert pending["status"] == "PENDING" and pending["excessAfterCostPct"] is None
    done = L.evaluate(rec, 126, sessions, lambda t, s, e: tr[t], observed_at="2099-12-01T00:00:00Z")
    assert done["status"] == "SCORED"
    gross = 0.1 * (1.2 * (1 - 0.002) - 1) + 0.9 * (1.1 * (1 - 0.001) - 1)
    assert done["excessAfterCostPct"] == pytest.approx((gross - (1.1 * 0.999 - 1)) * 100)
    blocked = L.evaluate(rec, 126, sessions, lambda t, s, e: tr[t], observed_at="2099-12-01T00:00:00Z",
                         blocked={"AAA": "UNVERIFIED_SPLIT"})
    assert blocked["status"] == "SOURCE_BLOCKED" and blocked["excessAfterCostPct"] is None
    missing = L.evaluate(rec, 126, sessions, lambda t, s, e: None if t == "AAA" else 0.1, observed_at="2099-12-01T00:00:00Z")
    assert missing["status"] == "SOURCE_BLOCKED"
    L.append(dry, done)
    L.verify_chain(L.read(dry))


# ----------------------------------------------------------------------------- gates and judgment rules
def _cand(**over):
    c = {"ticker": "AAA", "sector": "Industrials", "entryState": "WATCH", "coverage": {"dataCompleteness": 0.9, "sleevesPresent": 4},
         "priceMomentum": {"aboveMA200": True, "mom63Pct": 2.0}, "liquidityRisk": {"maxDD252Pct": -20, "vol252Pct": 25},
         "valuationProfitability": {"debtToEquity": 50}}
    c.update(over)
    return c


@pytest.mark.parametrize("over, gate", [
    ({"coverage": {"dataCompleteness": 0.6, "sleevesPresent": 4}}, "G1_DATA"),
    ({"entryState": "AVOID"}, "G2_ENTRY"),
    ({"priceMomentum": {"aboveMA200": False, "mom63Pct": -3}}, "G3_FALLING_PRICE"),
    ({"liquidityRisk": {"maxDD252Pct": -55, "vol252Pct": 25}}, "G4_RISK"),
    ({"valuationProfitability": {"debtToEquity": 250}}, "G5_LEVERAGE"),
])
def test_each_gate_fires(over, gate):
    assert gate in E.gates(_cand(**over), {"status": "FRESH"})


def test_financials_are_exempt_from_the_leverage_gate_and_stale_data_fails():
    assert E.gates(_cand(sector="Financial Services", valuationProfitability={"debtToEquity": 900}), {"status": "FRESH"}) == []
    assert "G1_DATA" in E.gates(_cand(), {"status": "STALE"})


def _pack_and_review():
    pack = json.loads((HERE / "inputs" / "2026-11" / "evidence-pack.json").read_text())
    pack["_sha256"] = J.sha256_file(HERE / "inputs" / "2026-11" / "evidence-pack.json")
    review = json.loads((HERE / "ai-reviews" / "2026-11.json").read_text())
    return pack, review


def test_committed_review_satisfies_the_frozen_rules():
    pack, review = _pack_and_review()
    assert J.check_review(review, pack) == {"KR": [], "US": ["TRV"]}


def test_selecting_a_gated_name_is_refused():
    pack, review = _pack_and_review()
    r = copy.deepcopy(review)
    kr = r["regions"]["KR"]
    kr["names"].append({"ticker": "078930.KS", "layers": {k: ["SUPPORTS", "x"] for k in J.LAYERS}, "decision": "SELECT",
                        "reasons": ["x"], "thesis6m": "x", "thesis12m": "x", "catalysts": ["x"], "risks": ["x"],
                        "invalidationConditions": ["x"], "notVerified": ["x"], "whyVersusBenchmark": "x"})
    kr["regionDecision"]["selected"] = ["078930.KS"]
    with pytest.raises(J.ReviewError, match="GATED"):
        J.check_review(r, pack)


def test_too_few_supporting_layers_or_a_probability_is_refused():
    pack, review = _pack_and_review()
    r = copy.deepcopy(review)
    trv = next(n for n in r["regions"]["US"]["names"] if n["ticker"] == "TRV")
    trv["layers"]["company"] = ["NEUTRAL", "x"]
    with pytest.raises(J.ReviewError, match="SELECTION_RULE"):
        J.check_review(r, pack)
    r = copy.deepcopy(review)
    next(n for n in r["regions"]["US"]["names"] if n["ticker"] == "TRV")["targetPrice"] = 450
    with pytest.raises(J.ReviewError, match="FORBIDDEN"):
        J.check_review(r, pack)


def test_review_bound_to_its_evidence_pack():
    pack, review = _pack_and_review()
    pack["_sha256"] = "0" * 64
    with pytest.raises(J.ReviewError, match="DIFFERENT_EVIDENCE"):
        J.check_review(review, pack)


# ----------------------------------------------------------------------------- committed dry run
def test_committed_dry_run_is_valid_and_published_before_execution():
    rows = L.read(L.DRY_RUN_DIR / "ledger.jsonl")
    L.verify_chain(rows)
    recs = [r for r in rows if r["schema"] == L.SCHEMA]
    assert {(r["region"], r["path"]) for r in recs} == {(g, p) for g in ("KR", "US") for p in ("B0", "B1", "B2")}
    for r in recs:
        assert r["informationCutoff"] <= r["generatedAt"] <= r["publishedAt"] < r["plannedExecutionCloseUtc"]
        assert r["status"] == "DRY_RUN_NOT_ACTIVATED"
    us_b2 = next(r for r in recs if r["region"] == "US" and r["path"] == "B2")
    assert us_b2["weights"] == {"TRV": 0.1, "SPY": 0.9}
    # every observed number in a pick came from the evidence pack, not the review
    pack = json.loads((HERE / "inputs" / "2026-11" / "evidence-pack.json").read_text())
    trv = next(c for c in pack["regions"]["US"]["candidates"] if c["ticker"] == "TRV")
    assert us_b2["investmentThesis"]["picks"][0]["observed"]["valuationProfitability"] == trv["valuationProfitability"]


def test_dry_run_commit_precedes_execution():
    if shutil.which("git") is None:
        pytest.skip("git unavailable")
    out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%cI", "--", "research/decision_desk_v1/dry-run/ledger.jsonl"],
                         cwd=ROOT, capture_output=True, text=True)
    if not out.stdout.strip():
        pytest.skip("ledger not yet committed in this checkout")
    first_commit = out.stdout.strip().splitlines()[-1]
    rows = [r for r in L.read(L.DRY_RUN_DIR / "ledger.jsonl") if r["schema"] == L.SCHEMA]
    import pandas as pd
    assert all(pd.Timestamp(first_commit) < pd.Timestamp(r["plannedExecutionCloseUtc"]) for r in rows)


# ----------------------------------------------------------------------------- desk publication
def test_committed_desk_validates_and_blocked_rows_have_no_numbers():
    desk = json.loads((HERE / "desk.json").read_text())
    V.validate(desk)
    blocked = [r for r in desk["history"] if r["type"] == "SOURCE_BLOCKED"]
    assert blocked and all(r[m] is None for r in blocked for m in V.METRICS)


@pytest.mark.parametrize("mutate, msg", [
    (lambda d: d["history"].__setitem__(0, {**d["history"][0], "type": "CURRENT"}), "BAD_HISTORY_TYPE"),
    (lambda d: next(r for r in d["history"] if r["type"] == "SOURCE_BLOCKED").__setitem__("cagrPct", 0.0), "SOURCE_BLOCKED_WITH_NUMBER"),
    (lambda d: d["regions"]["US"]["historicalAllocations"][0].__setitem__("currentRecommendation", True), "NOT_CURRENT"),
    (lambda d: d["regions"]["KR"]["deskRecords"][0].__setitem__("generatedAt", "2026-12-31T00:00:00Z"), "AFTER_EXECUTION"),
])
def test_desk_contract_violations(mutate, msg):
    desk = json.loads((HERE / "desk.json").read_text())
    mutate(desk)
    with pytest.raises(V.DeskError, match=msg):
        V.validate(desk)


def test_node_presentation_contracts():
    if shutil.which("node") is None:
        pytest.skip("node unavailable")
    res = subprocess.run(["node", "--test", "tests/decision_desk.test.cjs"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr
