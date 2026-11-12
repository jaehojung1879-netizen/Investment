"""Regression tests for the release gaps the independent preflight (#335) reported.

These are this branch's own tests, written against the behaviour each fix promises; they do not import or
edit the audit branch's tests. ledger.ACTIVATION_GATES names one test here for every RESOLVED gate.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import sys
import threading
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import availability as A  # noqa: E402
import desk as D  # noqa: E402
import evaluate as EV  # noqa: E402
import evidence as E  # noqa: E402
import judgment as J  # noqa: E402
import ledger as L  # noqa: E402
import packet as P  # noqa: E402
import validate_desk as V  # noqa: E402

LEDGER_ROWS = L.read(HERE / "dry-run" / "ledger.jsonl")
RECORDS = [r for r in LEDGER_ROWS if r.get("schema") in L.RECORD_SCHEMAS]


def _record(region="US", path="B2"):
    r = copy.deepcopy(next(x for x in RECORDS if x["region"] == region and x["path"] == path))
    return r


def _frame(region="US", n=260, close=100.0):
    idx = A.calendar(region).sessions_in_range("2026-11-11", "2028-06-30")[:n]
    return pd.DataFrame({"close": close, "volume": 1000.0, "dividend": 0.0, "split": 1.0}, index=idx)


def _with_record(tmp_path, monkeypatch, region="US", path="B2", weights=None):
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    led = tmp_path / "ledger.jsonl"
    r = _record(region, path)
    if weights:
        r["weights"] = weights
    rec = {k: v for k, v in r.items() if k not in ("digest", "prevDigest")}
    row = L.append(led, rec)
    return led, row


# ----------------------------------------------------------------------------- G1 / G2 / G9 information time
def test_revised_observation_is_dropped_not_substituted():
    cutoff = pd.Timestamp("2026-11-06T21:00:00Z")
    s = pd.Series([4.10, 4.20], index=pd.to_datetime(["2026-11-03", "2026-11-04"]))
    assert A.available_fred("DGS10", s, cutoff).tolist() == [4.10, 4.20]
    s.attrs["revisedAtUtc"] = {"2026-11-04": "2026-11-10T12:00:00Z"}
    out = A.available_fred("DGS10", s, cutoff)
    assert out.tolist() == [4.10]  # the revised value is NOT used and no other value is invented
    s.attrs["revisedAtUtc"] = "2026-11-06T20:00:00Z"  # revised before the cutoff: known at the cutoff
    assert A.available_fred("DGS10", s, cutoff).tolist() == [4.10, 4.20]


def test_fundamental_published_after_cutoff_fails_gates():
    row = {"coverage": {"dataCompleteness": 1.0, "sleevesPresent": 4}, "entryState": "ACCUMULATE",
           "priceMomentum": {"aboveMA200": True, "mom63Pct": 5}, "liquidityRisk": {"maxDD252Pct": -10, "vol252Pct": 20},
           "valuationProfitability": {"debtToEquity": 50}, "sector": "Industrials"}
    cutoff = pd.Timestamp("2026-11-06T21:00:00Z")
    assert E.gates(row, {"status": "FRESH"}, cutoff) == []
    late = copy.deepcopy(row)
    late["valuationProfitability"]["originalPublicationAtUtc"] = "2026-11-07T12:00:00Z"
    assert E.gates(late, {"status": "FRESH"}, cutoff) == ["G6_PUBLICATION"]
    same_day = copy.deepcopy(row)
    same_day["valuationProfitability"]["filingDate"] = "2026-11-06"  # date-only: visible from 11-07
    assert E.gates(same_day, {"status": "FRESH"}, cutoff) == ["G6_PUBLICATION"]
    assert E.gates(late, {"status": "FRESH"}) == []  # without a cutoff the legacy five gates are unchanged


def test_future_split_is_undone_at_the_cutoff(tmp_path):
    day = lambda d: int(pd.Timestamp(d + "T14:30:00Z").timestamp())  # noqa: E731
    payload = {"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York"},
                                     "timestamp": [day("2026-11-04"), day("2026-11-05")],
                                     "indicators": {"quote": [{"close": [40.0, 50.0]}]},
                                     "events": {"splits": {"a": {"date": day("2026-12-01"), "numerator": 4, "denominator": 1},
                                                           "b": {"date": day("2026-11-05"), "numerator": 2, "denominator": 1}}}}]}}
    (tmp_path / "yahoo_XYZ.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode()))
    s = A.available_closes("US", P.raw_close(tmp_path, "XYZ"), pd.Timestamp("2026-11-06T21:00:00Z"))
    # the December 4:1 split had not happened at the cutoff: both quotes are restored x4; the 11-05 split had
    assert s.tolist() == [160.0, 200.0]


# ----------------------------------------------------------------------------- G3 / G4 publication contract
def test_same_day_iso_cutoff_is_published():
    item = {"id": "x", "signalAsOf": "2026-11-06", "informationCutoff": "2026-11-06T21:00:00Z",
            "generatedAt": "2026-11-06T22:00:00Z", "executionAt": "2026-11-09"}
    V._alloc_ok(item)
    with pytest.raises(V.DeskError, match="CUTOFF_AFTER_GENERATION"):
        V._alloc_ok(dict(item, generatedAt="2026-11-06T20:00:00Z"))
    V._alloc_ok(dict(item, informationCutoff="2026-11-06", generatedAt="2026-11-07T00:00:01Z"))
    with pytest.raises(V.DeskError, match="CUTOFF_AFTER_GENERATION"):
        V._alloc_ok(dict(item, informationCutoff="2026-11-06", generatedAt="2026-11-06T12:00:00Z"))


def test_unsourced_number_in_prose_is_refused():
    pack = {"regions": {"US": {"market": {"vix": {"value": 16.61}}, "candidates": [{"ticker": "TRV", "price": 287.4}]}}}
    ok = {"regions": {"US": {"names": [{"ticker": "TRV", "reasons": ["VIX near 16.6 and price 287 in the packet; a 6 to 12 month view."]}]}}}
    J.check_prose_numbers(ok, pack)
    bad = copy.deepcopy(ok)
    bad["regions"]["US"]["names"][0]["reasons"] = ["Expected return 999% with 100% probability."]
    with pytest.raises(J.ReviewError, match="UNSOURCED_NUMBER_IN_PROSE"):
        J.check_prose_numbers(bad, pack)


# ----------------------------------------------------------------------------- G5 / G6 / G7 / G12 evaluation
def test_zero_or_negative_price_blocks():
    df = _frame()
    start, end = str(df.index[0].date()), str(df.index[126].date())
    zero = df.copy()
    zero["close"] = 0.0
    assert EV.window_block("US", "TRV", zero, start, end, {}).startswith("NON_POSITIVE_PRICE")
    assert EV.total_return(zero, start, end) is None
    neg = df.copy()
    neg.loc[neg.index[3], "close"] = -1.0
    assert EV.window_block("US", "TRV", neg, start, end, {}).startswith("NON_POSITIVE_PRICE")


def test_source_blocked_is_superseded_append_only(tmp_path, monkeypatch):
    led, rec = _with_record(tmp_path, monkeypatch, weights={"TRV": 0.1, "SPY": 0.9})
    observed = "2028-06-01T00:00:00Z"
    first = [o for o in EV.outcomes(L.read(led), {}, observed) if o["status"] != "PENDING"]
    assert {o["status"] for o in first} == {"SOURCE_BLOCKED"}
    for o in first:
        L.append(led, o)
    assert EV.outcomes(L.read(led), {}, observed) == []  # same answer: nothing new is written
    prices = {"TRV": _frame(), "SPY": _frame()}
    retry = [o for o in EV.outcomes(L.read(led), prices, observed) if o["status"] != "PENDING"]
    assert {o["status"] for o in retry} == {"SCORED"} and all(o["supersedes"] for o in retry)
    for o in retry:
        L.append(led, o)
    rows = L.read(led)
    assert sum(r.get("status") == "SOURCE_BLOCKED" for r in rows) == 2  # the blocked rows are kept
    with pytest.raises(L.LedgerError, match="OUTCOME_ALREADY_SCORED"):
        L.append(led, dict(retry[0], observedAt="2028-06-02T00:00:00Z"))
    # a second SOURCE_BLOCKED answer must cite the row it replaces
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr(L, "DRY_RUN_DIR", other)
    led2 = other / "ledger.jsonl"
    rec2 = L.append(led2, {k: v for k, v in rec.items() if k not in ("digest", "prevDigest")})
    b = dict(first[0], recordDigest=rec2["digest"])
    L.append(led2, b)
    with pytest.raises(L.LedgerError, match="RETRY_MUST_SUPERSEDE"):
        L.append(led2, dict(b, missingDataReason={"TRV": "OTHER"}))


def test_in_memory_blocked_rows_can_be_retried_without_a_ledger(tmp_path, monkeypatch):
    """A SOURCE_BLOCKED row that was never appended (no digest) must not crash a retry."""
    r = dict(_record("US", "B2"), weights={"TRV": 0.1, "SPY": 0.9})
    observed = "2028-06-01T00:00:00Z"
    blocked = [o for o in EV.outcomes([r], {}, observed) if o["status"] == "SOURCE_BLOCKED"]
    retry = [o for o in EV.outcomes([r, *blocked], {"TRV": _frame(), "SPY": _frame()}, observed) if o["status"] != "PENDING"]
    assert {o["status"] for o in retry} == {"SCORED"} and all(o["supersedes"] is None for o in retry)


def test_primary_comparison_excludes_contaminated_and_unobserved(tmp_path, monkeypatch):
    excl = L.primary_exclusions(LEDGER_ROWS)
    by = {(r["region"], r["path"]): excl[r["digest"]] for r in RECORDS}
    assert by[("KR", "B0")] == [] and by[("KR", "B1")] == []
    assert by[("KR", "B2")] == ["PIT_CONTAMINATED"]
    # the US records were confirmed public at 22:32Z, after the 21:00Z deadline: committer time only
    for p in ("B0", "B1"):
        assert by[("US", p)] == ["PUBLICATION_NOT_OBSERVED_BEFORE_DEADLINE"]
    assert by[("US", "B2")] == ["PIT_CONTAMINATED", "PUBLICATION_NOT_OBSERVED_BEFORE_DEADLINE"]
    # every scored outcome carries the flag, and the aggregate drops the excluded record
    led, rec = _with_record(tmp_path, monkeypatch, weights={"TRV": 0.1, "SPY": 0.9})
    L.append(led, {"schema": L.ANNOTATION_SCHEMA, "cohort": rec["cohort"], "category": "PIT_CONTAMINATED",
                   "recordDigests": [rec["digest"]], "createdAt": "2026-11-12T00:00:00Z", "detail": "test"})
    outs = [o for o in EV.outcomes(L.read(led), {"TRV": _frame(), "SPY": _frame()}, "2028-06-01T00:00:00Z") if o["status"] == "SCORED"]
    assert outs and all(o["primaryComparisonEligible"] is False for o in outs)
    for o in outs:
        L.append(led, o)
    assert L.primary_comparison(L.read(led)) == []
    bad = dict(outs[0], primaryComparisonEligible=True, costMultiplier=3.0)
    with pytest.raises(L.LedgerError, match="EXCLUDED_RECORD_MARKED_PRIMARY"):
        L.append(led, bad)


def test_evaluate_writes_base_and_double_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "LEDGER", tmp_path / "absent.jsonl")
    calls = []

    def fake(rows, prices, observed, cost_mult=1.0):
        calls.append(cost_mult)
        return []
    monkeypatch.setattr(EV, "outcomes", fake)
    D.cmd_evaluate("2028-01-01", fetch=False)
    assert calls == [1.0, 2.0]


# ----------------------------------------------------------------------------- G8 / G10 / G11 / G13 writer
def test_publication_checked_after_deadline_is_not_verified(tmp_path, monkeypatch):
    rec = _record("US", "B0")
    led = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    monkeypatch.setattr(D, "LEDGER", led)
    L.append(led, {k: v for k, v in rec.items() if k not in ("digest", "prevDigest")})
    deadline = rec["plannedExecutionCloseUtc"]
    monkeypatch.setattr(D, "commit_adding", lambda *a: ("a" * 40, "2026-11-11T12:30:49+00:00"))
    monkeypatch.setattr(D, "is_public", lambda sha: True)
    monkeypatch.setattr(D, "now_utc", lambda: "2026-11-11T22:32:59Z")  # after the 21:00Z deadline
    assert [a["category"] for a in D.cmd_verify_publication(rec["cohort"])] == ["PUBLICATION_NOT_OBSERVED"]
    led.unlink()
    L.append(led, {k: v for k, v in rec.items() if k not in ("digest", "prevDigest")})
    monkeypatch.setattr(D, "now_utc", lambda: "2026-11-11T20:00:00Z")
    assert deadline > "2026-11-11T20:00:00Z"
    assert [a["category"] for a in D.cmd_verify_publication(rec["cohort"])] == ["PUBLICATION_VERIFIED"]


def _packet(tmp_path, deadline="2099-12-08T14:30:00Z"):
    pk = {"schema": "DECISION_DESK_EVIDENCE_PACKET_V2", "cohort": "2099-12", "sealedAtUtc": "2099-12-04T22:00:00Z",
          "signalHistoryCommit": "synthetic", "receiptsBlob": "synthetic",
          "regions": {"US": {"schedule": {"registrationDeadlineUtc": deadline, "plannedExecution": "2099-12-08",
                                          "plannedExecutionCloseUtc": "2099-12-08T21:00:00Z"}}}}
    p = tmp_path / "packet.json"
    p.write_text(json.dumps(pk))
    return p, pk


def test_missed_deadline_records_no_path(tmp_path, monkeypatch):
    p, _ = _packet(tmp_path, deadline="2099-12-08T14:30:00Z")
    monkeypatch.setattr(D, "packet_path", lambda m: p)
    monkeypatch.setattr(D, "reviewers_at_seal", lambda m: [])
    with pytest.raises(D.StageError, match="REGISTRATION_CLOSED"):
        D.build_v2_records("2099-12", "2099-12-08T15:00:00Z")


def test_decide_refuses_review_before_packet_seal(tmp_path, monkeypatch):
    p, pk = _packet(tmp_path)
    rv = {"schema": "B2_AI_REVIEW_V2", "reviewer": "claude", "generatedAt": "2099-12-04T21:00:00Z", "regions": {}}
    rp = tmp_path / "review.json"
    rp.write_text(json.dumps(rv))
    monkeypatch.setattr(D, "packet_path", lambda m: p)
    monkeypatch.setattr(D, "review_path", lambda m, r: rp)
    monkeypatch.setattr(D, "reviewers_at_seal", lambda m: [{"id": "claude", "role": "PRIMARY_B2"}])
    monkeypatch.setattr(D, "committed_unchanged", lambda path: True)
    monkeypatch.setattr(D, "independence", lambda *a: {"claude": "INDEPENDENCE_NOT_VERIFIED"})
    with pytest.raises(D.StageError, match="REVIEW_BEFORE_PACKET"):
        D.build_v2_records("2099-12", "2099-12-05T10:00:00Z")


def test_concurrent_appends_keep_one_chain(tmp_path, monkeypatch):
    led, rec = _with_record(tmp_path, monkeypatch)
    start = threading.Barrier(8)
    errors = []

    def write(i):
        try:
            start.wait(timeout=10)
            L.append(led, {"schema": L.ANNOTATION_SCHEMA, "cohort": rec["cohort"], "category": "NOTE",
                           "recordDigests": [rec["digest"]], "createdAt": "2026-11-12T00:00:00Z", "detail": f"writer {i}"})
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    rows = L.read(led)
    L.verify_chain(rows)
    assert len(rows) == 9
    with pytest.raises(L.LedgerError, match="STALE_TIP"):
        L.append(led, {"schema": L.ANNOTATION_SCHEMA, "cohort": rec["cohort"], "category": "NOTE",
                       "recordDigests": [rec["digest"]], "createdAt": "2026-11-12T00:00:00Z", "detail": "late"},
                 expected_tip=rows[3]["digest"])


# ----------------------------------------------------------------------------- activation
def test_activation_is_refused_while_any_gate_is_open(tmp_path):
    assert any(g["status"] == "OPEN" for g in L.ACTIVATION_GATES)
    with pytest.raises(L.LedgerError, match="ACTIVATION_GATES_OPEN"):
        L.append(tmp_path / "live.jsonl", {"schema": "x", "path": "B0"}, owner_approved=True)
    names = set(globals())
    for g in L.ACTIVATION_GATES:
        if g["status"] == "RESOLVED":
            assert g["test"].split("::")[1] in names, g["id"]


def test_original_six_records_are_untouched():
    path = HERE / "dry-run" / "ledger.jsonl"
    prefix = b"".join(path.read_bytes().splitlines(keepends=True)[:6])
    assert hashlib.sha256(prefix).hexdigest() == "3854d94f07f6f91dc4d74372e3e59132ab3adbf613eec1b95c0f43aaa1c7b050"
