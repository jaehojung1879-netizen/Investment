"""Independent synthetic checks; AUDIT_TARGET points to an isolated #334 checkout.

Known defects use strict xfail, never a relaxed assertion. --runxfail exposes failures.
No provider requests, historical fitting, production writes or original-file edits.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pandas as pd
import pytest

TARGET = Path(os.environ.get("AUDIT_TARGET", Path(__file__).resolve().parents[2])).resolve()
DESK = TARGET / "research/decision_desk_v1"
if not DESK.exists():
    pytest.skip("Set AUDIT_TARGET to a checkout containing #334", allow_module_level=True)
sys.path.insert(0, str(TARGET))
sys.path.insert(0, str(DESK))
import availability as A  # noqa: E402
import desk as D  # noqa: E402
import evaluate as E  # noqa: E402
import evidence as V  # noqa: E402
import judgment as J  # noqa: E402
import ledger as L  # noqa: E402
import packet as P  # noqa: E402
import validate_desk as C  # noqa: E402


def records():
    return [r for r in L.read(DESK / "dry-run/ledger.jsonl") if r.get("schema") in L.RECORD_SCHEMAS]


def frame(region="US", count=254):
    idx = A.calendar(region).sessions_in_range("2026-01-05", "2027-12-31")[:count]
    return pd.DataFrame({"close": 100.0, "volume": 1000.0, "dividend": 0.0, "split": 1.0}, index=idx)


def record(weights=None):
    r = copy.deepcopy(next(x for x in records() if x["region"] == "US" and x["path"] == "B2"))
    r["plannedExecution"] = "2026-01-05"
    r["weights"] = weights or {"TRV": 0.1, "SPY": 0.9}
    r["costs"] = {"stockRoundTripPct": 0.4, "benchmarkRoundTripPct": 0.1}
    return r


def test_receipt_to_population_and_gates():
    pack = json.loads((DESK / "inputs/2026-11/evidence-pack.json").read_text())
    rec = V.cohort_receipts(pack["signalHistoryCommit"], "2026-11")
    for region, expected_pass in (("KR", 1), ("US", 3)):
        receipt = rec["regions"][region]
        excluded = {"generatedAt", "digest", "previousWeekChange", "freshness", "publishedFrom", "laterRecomputationDigest"}
        payload = json.dumps({k: v for k, v in receipt.items() if k not in excluded},
                             sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        assert hashlib.sha256(payload).hexdigest() == receipt["digest"]
        rows = V.candidate_rows(receipt)
        assert len(rows) == 12
        assert len(receipt["candidates"]) == 12 and len(receipt["watchlist"]) == 5
        assert {x["ticker"] for x in rows} == {x["ticker"] for x in receipt["candidates"]}
        assert {x["ticker"] for x in receipt["watchlist"]} <= {x["ticker"] for x in rows}
        assert sum(x.get("coverage") is None for x in rows) == 7
        assert sum(not V.gates(x, receipt["freshness"]) for x in rows) == expected_pass
        assert {x["ticker"] for x in pack["regions"][region]["candidates"]} == {x["ticker"] for x in rows}


def test_original_six_records_preserved_and_annotations_target_only_b2():
    path = DESK / "dry-run/ledger.jsonl"
    assert hashlib.sha256(b"".join(path.read_bytes().splitlines(keepends=True)[:6])).hexdigest() == "3854d94f07f6f91dc4d74372e3e59132ab3adbf613eec1b95c0f43aaa1c7b050"
    rows = L.read(path)
    L.verify_chain(rows)
    contaminated = {d for a in rows if a.get("category") == "PIT_CONTAMINATED" for d in a["recordDigests"]}
    assert contaminated == {r["digest"] for r in records() if r["path"] == "B2"}
    for region in ("KR", "US"):
        rr = {r["path"]: r for r in records() if r["region"] == region}
        assert rr["B0"]["weights"] == rr["B1"]["weights"]
    assert J.PROTOCOL["portfolio"]["perNameWeight"] == 0.1


@pytest.mark.parametrize("series,obs,release", [
    ("DEXKOUS", "2026-11-05", "2026-11-09T21:15:00Z"),
    ("DEXKOUS", "2026-10-08", "2026-10-13T20:15:00Z"),
    ("DGS10", "2026-11-05", "2026-11-06T21:15:00Z"),
])
def test_injected_future_release_is_rejected_until_exact_boundary(series, obs, release):
    values = pd.Series([99999.0], index=pd.to_datetime([obs]))
    boundary = pd.Timestamp(release)
    assert A.available_fred(series, values, boundary - pd.Timedelta(seconds=1)).empty
    assert A.available_fred(series, values, boundary).iloc[0] == 99999


def test_same_day_us_bar_cannot_enter_korean_close():
    s = pd.Series([100.0, 99999.0], index=pd.to_datetime(["2026-11-05", "2026-11-06"]))
    cutoff = A.cutoff_utc("KR", "2026-11-06")
    assert cutoff == pd.Timestamp("2026-11-06T06:30:00Z")
    assert A.cutoff_utc("US", "2026-11-06") == pd.Timestamp("2026-11-06T21:00:00Z")
    assert A.available_closes("US", s, cutoff).tolist() == [100.0]
    assert A.available_closes("US", s, pd.Timestamp("2026-11-06T20:59:59Z")).tolist() == [100.0]


@pytest.mark.parametrize("region", ["KR", "US"])
def test_126_252_exchange_endpoints_and_costs(region):
    df = frame(region)
    sessions = [str(x.date()) for x in df.index]
    r = record()
    r.update(region=region, plannedExecution=sessions[0])
    calls = []

    def known(t, start, end):
        calls.append((t, start, end))
        return 0.2 if t == "TRV" else 0.1

    for h in (126, 252):
        o = L.evaluate(r, h, sessions, known, "2028-01-01T00:00:00Z")
        assert o["status"] == "SCORED"
        assert o["horizonEndSession"] == sessions[h]
        expected = 0.1 * (1.2 * 0.996 - 1) + 0.9 * (1.1 * 0.999 - 1)
        assert o["returnAfterCostPct"] == pytest.approx(expected * 100, abs=1e-6)
        assert o["excessAfterCostPct"] == pytest.approx((expected - (1.1 * 0.999 - 1)) * 100, abs=1e-6)
        assert all((s, e) == (sessions[0], sessions[h]) for _, s, e in calls[-3:])
        assert L.evaluate(r, h, sessions, known, sessions[h] + "T23:59:59Z")["status"] == "PENDING"


def test_first_entry_ignores_pre_execution_quotes_and_entry_dividend():
    df = frame(count=3)
    df["close"] = [1.0, 100.0, 110.0]
    df.loc[df.index[1], "dividend"] = 50.0  # entry close buyer has no ex-date entitlement
    assert E.total_return(df, str(df.index[1].date()), str(df.index[2].date())) == pytest.approx(0.1)
    assert J.execution_after("US", "2026-11-11T12:30:49Z") == ("2026-11-11", "2026-11-11T21:00:00Z")
    assert J.execution_after("KR", "2026-11-11T12:30:49Z") == ("2026-11-12", "2026-11-12T06:30:00Z")


def test_dividend_and_split_adjusted_units_no_double_count():
    df = frame(count=3)
    df["close"] = [50.0, 49.0, 55.0]  # all quotes in post-split units
    df["dividend"] = [0.0, 1.0, 0.0]
    df.loc[df.index[1], "split"] = 2.0
    start, end = str(df.index[0].date()), str(df.index[-1].date())
    assert E.total_return(df, start, end) == pytest.approx((50 / 50) * (55 / 49) - 1)
    scaled = df.copy()
    scaled[["close", "dividend"]] /= 10  # later split cancels only if BOTH share same units
    assert E.total_return(scaled, start, end) == pytest.approx(E.total_return(df, start, end))
    assert E.window_block("US", "TRV", df, start, end, {}).startswith("UNVERIFIED_SPLIT")


@pytest.mark.parametrize("defect,reason", [("missing", "MISSING_SESSION_CLOSE"), ("suspension", "ZERO_VOLUME_SESSION"),
                                          ("delisted", "NO_EXIT_CLOSE"), ("split", "UNVERIFIED_SPLIT"),
                                          ("move", "UNEXPLAINED_MOVE")])
def test_missing_and_unverified_quotes_never_zero(defect, reason):
    df = frame()
    start, end = str(df.index[0].date()), str(df.index[126].date())
    if defect == "missing":
        df = df.drop(df.index[10])
    elif defect == "suspension":
        df.loc[df.index[10], "volume"] = 0
    elif defect == "delisted":
        df = df.iloc[:100]
    elif defect == "split":
        df.loc[df.index[10], "split"] = 2
    else:
        df.loc[df.index[10], "close"] = 170
    assert E.window_block("US", "TRV", df, start, end, {}).startswith(reason)
    o = E.outcomes([record()], {"TRV": df, "SPY": frame()}, "2028-01-01T00:00:00Z")[0]
    assert o["status"] == "SOURCE_BLOCKED"
    assert o["returnAfterCostPct"] is None and o["excessAfterCostPct"] is None


def test_unavailable_price_and_double_cost():
    r = record()
    missing = E.outcomes([r], {}, "2028-01-01T00:00:00Z")[0]
    assert missing["status"] == "SOURCE_BLOCKED" and missing["returnAfterCostPct"] is None
    prices = {"SPY": frame(), "TRV": frame()}
    normal = E.outcomes([r], prices, "2028-01-01T00:00:00Z")[0]
    stress = E.outcomes([r], prices, "2028-01-01T00:00:00Z", cost_mult=2)[0]
    assert normal["returnAfterCostPct"] == pytest.approx(-0.13)
    assert stress["returnAfterCostPct"] == pytest.approx(-0.26)


def test_ledger_tamper_and_append_preserves_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    path = tmp_path / "ledger.jsonl"
    original = records()[0]
    L.append(path, original)
    prefix = path.read_bytes()
    L.append(path, {"schema": L.ANNOTATION_SCHEMA, "category": "NOTE", "cohort": "2026-11",
                    "recordDigests": [original["digest"]], "createdAt": "2026-11-12T00:00:00Z", "detail": "audit"})
    assert path.read_bytes().startswith(prefix)
    edited = L.read(path)
    edited[0]["investmentThesis"] = "rewritten"
    with pytest.raises(L.LedgerError, match="DIGEST_MISMATCH"):
        L.verify_chain(edited)


# Release gates below assert the required behavior and fail against exact #334.
# strict=True also makes a later fix (XPASS) fail until the audit is updated.
@pytest.mark.xfail(strict=True, reason="G1: revision/vintage time is discarded; observation date alone survives")
def test_future_revision_cannot_change_prior_information_set():
    idx = pd.to_datetime(["2026-11-04"])
    old = pd.Series([4.90], index=idx)
    revised = pd.Series([99.0], index=idx)
    revised.attrs["revisedAtUtc"] = "2026-11-10T12:00:00Z"
    cutoff = pd.Timestamp("2026-11-06T21:00:00Z")
    assert A.available_fred("DGS10", revised, cutoff).equals(A.available_fred("DGS10", old, cutoff))


@pytest.mark.xfail(strict=True, reason="G2: future fundamental publication timestamp is ignored by gates")
def test_future_fundamental_publication_fails_eligibility():
    pack = json.loads((DESK / "inputs/2026-11/evidence-pack.json").read_text())
    row = copy.deepcopy(next(c for c in pack["regions"]["US"]["candidates"] if c["ticker"] == "TRV"))
    row["valuationProfitability"].update(originalPublicationAtUtc="2099-01-01T00:00:00Z", vintageAtUtc="2099-01-01T00:00:00Z")
    assert V.gates(row, pack["regions"]["US"]["freshness"])


@pytest.mark.xfail(strict=True, reason="G3: valid same-day v2 cutoff compared to date-only generatedAt and rejected")
def test_v2_iso_cutoff_can_be_published():
    r = copy.deepcopy(json.loads((DESK / "desk.json").read_text())["regions"]["US"]["deskRecords"][0])
    r.update(informationCutoff="2026-11-06T21:00:00Z", generatedAt="2026-11-06T22:00:00Z")
    C._alloc_ok(r)


@pytest.mark.xfail(strict=True, reason="G4: free-text reasons can introduce any unobserved forecast number")
def test_unobserved_numeric_return_claim_in_prose_is_refused():
    review = json.loads((DESK / "ai-reviews/2026-11.json").read_text())
    pack = json.loads((DESK / "inputs/2026-11/evidence-pack.json").read_text())
    pack["_sha256"] = hashlib.sha256((DESK / "inputs/2026-11/evidence-pack.json").read_bytes()).hexdigest()
    next(n for n in review["regions"]["US"]["names"] if n["ticker"] == "TRV")["reasons"] = ["Expected return 999% with 100% probability."]
    with pytest.raises(J.ReviewError):
        J.check_review(review, pack)


@pytest.mark.xfail(strict=True, reason="G5: SOURCE_BLOCKED is terminal in done set; later verified quotes never retry")
def test_source_blocked_can_receive_later_append_only_correction():
    r = record()
    blocked = E.outcomes([r], {}, "2028-01-01T00:00:00Z")
    retry = E.outcomes([r, *blocked], {"TRV": frame(), "SPY": frame()}, "2028-01-02T00:00:00Z")
    assert retry and retry[0]["status"] == "SCORED"


@pytest.mark.xfail(strict=True, reason="G6: zero quotes pass and NaN gross factors collapse to a fabricated flat return")
def test_zero_price_is_source_blocked():
    df = frame()
    df["close"] = 0.0
    assert E.outcomes([record()], {"TRV": df, "SPY": frame()}, "2028-01-01T00:00:00Z")[0]["status"] == "SOURCE_BLOCKED"


@pytest.mark.xfail(strict=True, reason="G7: no primary-comparison eligibility field accompanies scored contaminated record")
def test_contaminated_outcomes_cannot_enter_primary_comparison():
    rows = L.read(DESK / "dry-run/ledger.jsonl")
    r = record()
    notes = [a for a in rows if a.get("category") == "PIT_CONTAMINATED"]
    scored = E.outcomes([r, *notes], {"TRV": frame(), "SPY": frame()}, "2028-01-01T00:00:00Z")[0]
    assert scored.get("primaryComparisonEligible") is False


@pytest.mark.xfail(strict=True, reason="G8: current remote reachability plus backdated committer time passes publication check")
def test_git_committer_time_is_not_first_publication_time(tmp_path, monkeypatch):
    r = records()[0]
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps(r) + "\n")
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    monkeypatch.setattr(D, "LEDGER", path)
    monkeypatch.setattr(D, "commit_adding", lambda *args: ("a" * 40, "2026-11-10T00:00:00+00:00"))
    monkeypatch.setattr(D, "is_public", lambda sha: True)  # first pushed after execution, reachable now
    assert not any(a["category"] == "PUBLICATION_VERIFIED" for a in D.cmd_verify_publication("2026-11"))


@pytest.mark.xfail(strict=True, reason="G9: Yahoo prior prices remain adjusted by a split after the information cutoff")
def test_future_split_cannot_rewrite_observed_historical_quote(tmp_path):
    payload = {"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York"},
        "timestamp": [int(pd.Timestamp("2026-11-05T14:30:00Z").timestamp())],
        "indicators": {"quote": [{"close": [50.0]}]},
        "events": {"splits": {"future": {"date": int(pd.Timestamp("2026-12-01T14:30:00Z").timestamp()),
                                         "numerator": 2, "denominator": 1}}}}]}}
    (tmp_path / "yahoo_SPY.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode()))
    s = A.available_closes("US", P.raw_close(tmp_path, "SPY"), pd.Timestamp("2026-11-06T21:00:00Z"))
    assert s.iloc[0] == 100.0  # as-traded price before the injected December split


@pytest.mark.xfail(strict=True, reason="G10: missed deadline refuses the entire cohort, including B0/B1")
def test_missed_review_deadline_still_records_b0_b1(tmp_path, monkeypatch):
    month = "2099-12"
    packet_path = tmp_path / "packet.json"
    pk = {"regions": {"US": {"schedule": {"registrationDeadlineUtc": "2026-11-09T14:30:00Z"}}}}
    packet_path.write_text(json.dumps(pk))
    monkeypatch.setattr(D, "packet_path", lambda m: packet_path)
    monkeypatch.setattr(D, "reviewers_at_seal", lambda m: [])
    written, notes = D.build_v2_records(month, "2026-11-09T15:00:00Z")
    assert {r["path"] for r in written} == {"B0", "B1"}


@pytest.mark.xfail(strict=True, reason="G11: new research ledger append has no lock or compare-and-swap; concurrent appends fork chain")
def test_two_research_ledger_writers_cannot_fork_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    path = tmp_path / "ledger.jsonl"
    r = L.append(path, records()[0])
    real_read = L.read
    barrier = threading.Barrier(2)

    def racing_read(p):
        rows = real_read(p)
        barrier.wait(timeout=10)
        return rows

    monkeypatch.setattr(L, "read", racing_read)
    note = {"schema": L.ANNOTATION_SCHEMA, "category": "NOTE", "cohort": "2026-11", "recordDigests": [r["digest"]],
            "createdAt": "2026-11-12T00:00:00Z", "detail": "concurrent"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda i: L.append(path, {**note, "detail": str(i)}), range(2)))
    L.verify_chain(real_read(path))


@pytest.mark.xfail(strict=True, reason="G12: official evaluate command calls base cost only; does not emit advertised 2x sensitivity")
def test_official_evaluation_reports_base_and_double_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "LEDGER", tmp_path / "absent.jsonl")
    calls = []

    def outcomes(rows, prices, observed, cost_mult=1.0):
        calls.append(cost_mult)
        return []

    monkeypatch.setattr(E, "outcomes", outcomes)
    D.cmd_evaluate("2028-01-01", fetch=False)
    assert calls == [1.0, 2.0]


def test_primary_exclusion_badge_is_present_in_both_views():
    code = """const a=require('./app.js'),d=require('./research/decision_desk_v1/desk.json');
for(const m of ['KR','US']) {let h=a.deskMarkup(d,m,Date.parse('2026-11-11T13:00:00Z'));
if(!h.includes('PIT 오염 — 주 비교 제외')) process.exit(1);}
"""
    subprocess.run(["node", "-e", code], cwd=TARGET, check=True)
