"""Independent synthetic checks; AUDIT_TARGET points to an isolated #334 checkout.

Known defects use strict xfail, never a relaxed assertion. --runxfail exposes failures.
No provider requests, historical fitting, production writes or original-file edits.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

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
    excluded = L.primary_exclusions(rows)
    for r in records():
        if r["region"] == "US":
            assert "PUBLICATION_NOT_OBSERVED_BEFORE_DEADLINE" in excluded[r["digest"]]
        elif r["path"] in ("B0", "B1"):
            assert excluded[r["digest"]] == []
        if r["path"] == "B2":
            assert "PIT_CONTAMINATED" in excluded[r["digest"]]
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


# Latest-HEAD regressions. Resolved gaps have ordinary assertions; only reproduced
# residual gaps retain typed strict xfail markers. Earlier outcomes remain in Git history.
def test_future_revision_cannot_change_prior_information_set():
    idx = pd.to_datetime(["2026-11-04"])
    old = pd.Series([4.90], index=idx)
    revised = pd.Series([99.0], index=idx)
    revised.attrs["revisedAtUtc"] = "2026-11-10T12:00:00Z"
    cutoff = pd.Timestamp("2026-11-06T21:00:00Z")
    assert not A.available_fred("DGS10", old, cutoff).empty
    assert A.available_fred("DGS10", revised, cutoff).empty


def test_future_fundamental_publication_fails_eligibility():
    pack = json.loads((DESK / "inputs/2026-11/evidence-pack.json").read_text())
    row = copy.deepcopy(next(c for c in pack["regions"]["US"]["candidates"] if c["ticker"] == "TRV"))
    row["valuationProfitability"].update(originalPublicationAtUtc="2099-01-01T00:00:00Z", vintageAtUtc="2099-01-01T00:00:00Z")
    assert "G6_PUBLICATION" in V.gates(row, pack["regions"]["US"]["freshness"], pd.Timestamp("2026-11-06T21:00:00Z"))


def test_v2_iso_cutoff_can_be_published():
    r = copy.deepcopy(json.loads((DESK / "desk.json").read_text())["regions"]["US"]["deskRecords"][0])
    r.update(informationCutoff="2026-11-06T21:00:00Z", generatedAt="2026-11-06T22:00:00Z")
    C._alloc_ok(r)


def test_unobserved_numeric_return_claim_in_prose_is_refused():
    review = json.loads((DESK / "ai-reviews/2026-11.json").read_text())
    pack = json.loads((DESK / "inputs/2026-11/evidence-pack.json").read_text())
    pack["_sha256"] = hashlib.sha256((DESK / "inputs/2026-11/evidence-pack.json").read_bytes()).hexdigest()
    next(n for n in review["regions"]["US"]["names"] if n["ticker"] == "TRV")["reasons"] = ["Expected return 999% with 100% probability."]
    with pytest.raises(J.ReviewError):
        J.check_prose_numbers(review, pack)


def test_source_blocked_can_receive_later_append_only_correction():
    r = record()
    blocked = [dict(o, digest=L.digest(o)) for o in E.outcomes([r], {}, "2028-01-01T00:00:00Z")]
    retry = E.outcomes([r, *blocked], {"TRV": frame(), "SPY": frame()}, "2028-01-02T00:00:00Z")
    assert retry and retry[0]["status"] == "SCORED"


def test_zero_price_is_source_blocked():
    df = frame()
    df["close"] = 0.0
    assert E.outcomes([record()], {"TRV": df, "SPY": frame()}, "2028-01-01T00:00:00Z")[0]["status"] == "SOURCE_BLOCKED"


def test_contaminated_outcomes_cannot_enter_primary_comparison():
    rows = L.read(DESK / "dry-run/ledger.jsonl")
    r = record()
    notes = [a for a in rows if a.get("category") == "PIT_CONTAMINATED"]
    scored = E.outcomes([r, *notes], {"TRV": frame(), "SPY": frame()}, "2028-01-01T00:00:00Z")[0]
    assert scored.get("primaryComparisonEligible") is False


def test_git_committer_time_is_not_first_publication_time(tmp_path, monkeypatch):
    r = records()[0]
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps(r) + "\n")
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    monkeypatch.setattr(D, "LEDGER", path)
    monkeypatch.setattr(D, "commit_adding", lambda *args: ("a" * 40, "2026-11-10T00:00:00+00:00"))
    monkeypatch.setattr(D, "is_public", lambda sha: True)  # first pushed after execution, reachable now
    assert not any(a["category"] == "PUBLICATION_VERIFIED" for a in D.cmd_verify_publication("2026-11"))


def test_future_split_cannot_rewrite_observed_historical_quote(tmp_path):
    payload = {"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York"},
        "timestamp": [int(pd.Timestamp("2026-11-05T14:30:00Z").timestamp())],
        "indicators": {"quote": [{"close": [50.0]}]},
        "events": {"splits": {"future": {"date": int(pd.Timestamp("2026-12-01T14:30:00Z").timestamp()),
                                         "numerator": 2, "denominator": 1}}}}]}}
    (tmp_path / "yahoo_SPY.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode()))
    s = A.available_closes("US", P.raw_close(tmp_path, "SPY"), pd.Timestamp("2026-11-06T21:00:00Z"))
    assert s.iloc[0] == 100.0  # as-traded price before the injected December split


def test_missed_deadline_refuses_backfilling_every_path(tmp_path, monkeypatch):
    month = "2099-12"
    packet_path = tmp_path / "packet.json"
    pk = {"signalHistoryCommit": "synthetic", "receiptsBlob": "synthetic",
          "regions": {"US": {"schedule": {"registrationDeadlineUtc": "2026-11-09T14:30:00Z"}}}}
    packet_path.write_text(json.dumps(pk))
    monkeypatch.setattr(D, "packet_path", lambda m: packet_path)
    monkeypatch.setattr(D, "reviewers_at_seal", lambda m: [])
    with pytest.raises(D.StageError, match="REGISTRATION_CLOSED"):
        D.build_v2_records(month, "2026-11-09T15:00:00Z")


def test_two_research_ledger_writers_cannot_fork_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    path = tmp_path / "ledger.jsonl"
    r = L.append(path, records()[0])
    note = {"schema": L.ANNOTATION_SCHEMA, "category": "NOTE", "cohort": "2026-11", "recordDigests": [r["digest"]],
            "createdAt": "2026-11-12T00:00:00Z", "detail": "concurrent"}
    prefix = path.read_bytes()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: L.append(path, {**note, "detail": str(i)}), range(32)))
    rows = L.read(path)
    L.verify_chain(rows)
    assert len(rows) == 33 and path.read_bytes().startswith(prefix)
    with pytest.raises(L.LedgerError, match="STALE_TIP"):
        L.append(path, note, expected_tip=r["digest"])


def test_official_evaluation_reports_base_and_double_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "LEDGER", tmp_path / "absent.jsonl")
    calls = []

    def outcomes(rows, prices, observed, cost_mult=1.0):
        calls.append(cost_mult)
        return []

    monkeypatch.setattr(E, "outcomes", outcomes)
    D.cmd_evaluate("2028-01-01", fetch=False)
    assert calls == [1.0, 2.0]


@pytest.mark.parametrize("injection", ["before_seal", "numeric_forecast"])
def test_decide_rejects_bad_review_on_actual_path(tmp_path, monkeypatch, injection):
    pk = json.loads((DESK / "inputs/2026-11/evidence-pack.json").read_text())
    pk.update(schema="DECISION_DESK_EVIDENCE_PACKET_V2", cohort="2099-12")
    pk["sealedAtUtc"] = "2026-11-11T12:30:00Z"
    for region, ev in pk["regions"].items():
        ev["informationCutoffUtc"] = "2026-11-06T06:30:00Z" if region == "KR" else "2026-11-06T21:00:00Z"
        ev["gatePassers"] = [c["ticker"] for c in ev["candidates"] if not c["gatesFailed"]]
        ev["schedule"] = {"plannedExecution": "2026-11-12",
                          "plannedExecutionCloseUtc": "2026-11-12T06:30:00Z" if region == "KR" else "2026-11-12T21:00:00Z",
                          "registrationDeadlineUtc": "2026-11-12T00:00:00Z" if region == "KR" else "2026-11-12T14:30:00Z"}
    pp = tmp_path / "packet.json"
    pp.write_text(json.dumps(pk))
    rv = json.loads((DESK / "ai-reviews/2026-11.json").read_text())
    rv.update(schema="B2_AI_REVIEW_V2", cohort="2099-12", reviewer="claude", readOnlyThePacket=True)
    rv["generatedAt"] = "2026-11-11T12:00:00Z" if injection == "before_seal" else "2026-11-11T12:45:00Z"
    if injection == "numeric_forecast":
        rv["regions"]["US"]["names"][0]["reasons"] = ["Expected return 999%"]
    rv["evidencePackSha256"] = hashlib.sha256(pp.read_bytes()).hexdigest()
    rv["packetSha256"] = rv["evidencePackSha256"]
    rp = tmp_path / "review.json"
    rp.write_text(json.dumps(rv))
    monkeypatch.setattr(D, "packet_path", lambda month: pp)
    monkeypatch.setattr(D, "review_path", lambda month, reviewer: rp)
    monkeypatch.setattr(D, "reviewers_at_seal", lambda month: [{"id": "claude", "role": "PRIMARY_B2"}])
    monkeypatch.setattr(D, "committed_unchanged", lambda p: True)
    monkeypatch.setattr(D, "independence", lambda *args: {"claude": "INDEPENDENCE_NOT_VERIFIED"})
    error, match = (D.StageError, "REVIEW_BEFORE_PACKET") if injection == "before_seal" else (J.ReviewError, "UNSOURCED_NUMBER")
    with pytest.raises(error, match=match):
        D.build_v2_records("2099-12", "2026-11-11T13:00:00Z")


def test_primary_exclusion_badge_is_present_in_both_views():
    code = """const a=require('./app.js'),d=require('./research/decision_desk_v1/desk.json');
for(const m of ['KR','US']) {let h=a.deskMarkup(d,m,Date.parse('2026-11-11T13:00:00Z'));
if(!h.includes('PIT 오염 — 주 비교 제외')) process.exit(1);}
"""
    subprocess.run(["node", "-e", code], cwd=TARGET, check=True)


@pytest.fixture
def evidence_first():
    folder = TARGET / "research/evidence_first_v2"
    if not folder.exists():
        pytest.skip("Evidence-First added after initial d876c6f0 audit")
    spec = importlib.util.spec_from_file_location("independent_evidence_contract", folder / "contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return folder, module


def test_latest_funnel_and_evidence_grades_do_not_promote(evidence_first):
    folder, contract = evidence_first
    census = json.loads((folder / "results/census.json").read_text())
    for region, expected in (("KR", (300, 78, 61, 5, 0)), ("US", (503, 356, 206, 5, 0))):
        f = census["regions"][region]["funnel"]
        assert tuple(f[i]["remaining"] for i in (0, 4, 6, 7, 8)) == expected
        for before, after in zip(f[:4], f[1:5]):
            assert before["remaining"] - sum(after["dropped"].values()) == after["remaining"]
    grades = contract.validate_grades(json.loads((folder / "evidence-grades.json").read_text()))
    assert not any(g["decisionEligible"] for g in grades.values() if g["grade"] != "BENCHMARK")


@pytest.mark.parametrize("injection", ["future_publication", "numeric_forecast"])
def test_latest_dossier_rejects_future_date_and_numeric_forecast(evidence_first, injection):
    folder, contract = evidence_first
    d = copy.deepcopy(json.loads((folder / "results/b3-dossiers.json").read_text())["dossiers"][0])
    region = json.loads((folder / "results/census.json").read_text())["regions"][d["region"]]
    rows = {r["ticker"]: r for r in region["b1"]["topQuintile"]}
    if injection == "future_publication":
        d["facts"][0]["source"]["availableFrom"] = "2099-01-01"
    else:
        d["interpretation"] = ["Expected return 999 percent"]
    with pytest.raises(ValueError):
        contract.validate_dossier(d, "E1", rows)


def test_latest_dossier_rejects_an_unobserved_fact_number(evidence_first):
    folder, contract = evidence_first
    d = copy.deepcopy(json.loads((folder / "results/b3-dossiers.json").read_text())["dossiers"][0])
    region = json.loads((folder / "results/census.json").read_text())["regions"][d["region"]]
    rows = {r["ticker"]: r for r in region["b1"]["topQuintile"]}
    d["facts"].append({"field": "unobservedFutureReturnPct", "label": "unverified forecast", "value": 999,
                       "source": {"availableFrom": "2000-01-01"}})
    with pytest.raises(ValueError):
        contract.validate_dossier(d, "E1", rows)


def test_latest_financial_facts_keep_their_own_publication_dates(evidence_first):
    _, contract = evidence_first
    roe_from = {"availableFrom": "2026-01-01", "reportDate": "2025-09-30"}
    op_from = {"availableFrom": "2026-10-30", "reportDate": "2026-09-30"}
    row = {"roe": .1, "operatingMargin": .2, "debtToEquity": .5, "bookToPrice": .3, "momentum12_2": .4,
           "roeFrom": roe_from, "fieldSources": {"roe": roe_from, "operatingMargin": op_from, "debtToEquity": op_from}}
    facts = contract.facts_from_census("US", row, "2026-11-10", "synthetic", row["fieldSources"])
    op_fact = next(f for f in facts if f["field"] == "operatingMargin")
    assert op_fact["source"]["availableFrom"] == op_from["availableFrom"]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="G1 residual: current FRED CSV has no vintage receipt, so a silent revision cannot be detected")
def test_macro_without_a_vintage_receipt_cannot_claim_pit_exact():
    silently_revised = pd.Series([99.0], index=pd.to_datetime(["2026-11-04"]))
    assert A.available_fred("DGS10", silently_revised, pd.Timestamp("2026-11-06T21:00:00Z")).empty


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="G2 residual: legacy fundamentals without publication metadata are flagged but not rejected by the eligibility helper")
def test_legacy_undated_fundamental_is_not_certified_public():
    pack = json.loads((DESK / "inputs/2026-11/evidence-pack.json").read_text())
    row = copy.deepcopy(next(c for c in pack["regions"]["US"]["candidates"] if c["ticker"] == "TRV"))
    for key in V.PUBLICATION_KEYS:
        row["valuationProfitability"].pop(key, None)
    assert "G6_PUBLICATION" in V.gates(row, pack["regions"]["US"]["freshness"], pd.Timestamp("2026-11-06T21:00:00Z"))


def test_activation_gates_are_scoped_and_owner_gate_stays_closed(evidence_first, tmp_path, monkeypatch):
    folder, _ = evidence_first
    assert {g["id"] for g in L.open_gates("DESK_V2_B2")} == {"G1_MACRO_VINTAGE", "G2_FUNDAMENTAL_PUBLICATION", "CI_GREEN"}
    assert {g["id"] for g in L.open_gates("PROSPECTIVE_V1")} == {"CI_GREEN"}
    assert {g["id"] for g in L.open_gates("DESK_WRITER")} == {"CI_GREEN"}
    with pytest.raises(L.LedgerError, match="ACTIVATION_GATES_OPEN"):
        L.append(tmp_path / "unactivated.jsonl", records()[0], owner_approved=True)
    assert not (tmp_path / "unactivated.jsonl").exists()
    spec = importlib.util.spec_from_file_location("independent_prospective", folder / "prospective.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "APPROVAL", tmp_path / "absent.json")
    with pytest.raises(module.ProtocolError, match="OWNER_APPROVAL_FILE_MISSING"):
        module.assert_activation_allowed(tmp_path / "absent.json")


@pytest.mark.parametrize("price", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
def test_nonfinite_and_nonpositive_prices_never_score(price):
    df = frame()
    df.loc[df.index[10], "close"] = price
    out = E.outcomes([record()], {"TRV": df, "SPY": frame()}, "2028-01-01T00:00:00Z")
    assert out and all(o["status"] == "SOURCE_BLOCKED" and o["returnAfterCostPct"] is None for o in out)


def test_retry_is_append_only_and_double_cost_rows_are_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    path = tmp_path / "ledger.jsonl"
    r = L.append(path, records()[0])
    # Shift the synthetic valuation calendar without changing the valid frozen receipt.
    monkeypatch.setattr(D, "LEDGER", path)
    monkeypatch.setattr(E, "load_store", lambda p: {r["benchmark"]: frame(r["region"])})
    synthetic = frame(r["region"])
    original_outcomes = E.outcomes
    def outcomes(rows, prices, observed_at, cost_mult=1.0):
        vals = [dict(x, plannedExecution=str(synthetic.index[0].date())) if x.get("schema") in L.RECORD_SCHEMAS else x for x in rows]
        return original_outcomes(vals, prices, observed_at, cost_mult)
    monkeypatch.setattr(E, "outcomes", outcomes)
    D.cmd_evaluate("2028-01-01", fetch=False)
    prefix = path.read_bytes()
    blocked = [x for x in L.read(path) if x.get("schema") == L.OUTCOME_SCHEMA]
    assert len(blocked) == 4 and {x["costMultiplier"] for x in blocked} == {1.0, 2.0}
    monkeypatch.setattr(E, "outcomes", lambda rows, prices, observed_at, cost_mult=1.0:
                        outcomes(rows, {r["benchmark"]: synthetic}, observed_at, cost_mult))
    D.cmd_evaluate("2028-01-02", fetch=False)
    assert path.read_bytes().startswith(prefix)
    rows = L.read(path)
    L.verify_chain(rows)
    scored = [x for x in rows if x.get("status") == "SCORED"]
    assert len(scored) == 4 and all(x.get("supersedes") for x in scored)
    assert {x["costMultiplier"] for x in scored} == {1.0, 2.0}


def test_actual_dossier_financial_dates_match_each_stored_field(evidence_first):
    folder, _ = evidence_first
    integrity = json.loads((folder / "results/data-integrity.json").read_text())["regions"]
    dossiers = json.loads((folder / "results/b3-dossiers.json").read_text())["dossiers"]
    fields = {"roe": "roe", "operatingMargin": "operatingMargin", "debtToEquity": "debtToEquity", "bookToPrice": "bookValuePerShare"}
    checked = 0
    for d in dossiers:
        sources = integrity[d["region"]]["periods"]["byTicker"][d["ticker"]]
        for fact in d["facts"]:
            if fact["field"] in fields:
                actual = sources[fields[fact["field"]]]
                assert {k: fact["source"][k] for k in ("reportDate", "availableFrom")} == {k: actual[k] for k in ("reportDate", "availableFrom")}
                checked += 1
    assert checked == 40


def test_new_prospective_inputs_refuse_same_day_and_future_filings(evidence_first, monkeypatch):
    folder, _ = evidence_first
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location("independent_integrity", folder / "integrity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = {"ticker": "SYN", "availableFrom": "2026-11-09", "reportDate": "2026-09-30",
           "fields": {"roe": .1, "operatingMargin": .2, "debtToEquity": .5, "profitMargin": .1, "bookValuePerShare": 10}}
    same = dict(old, availableFrom="2026-11-10", fields={k: 999 for k in old["fields"]})
    future = dict(same, availableFrom="2099-01-01")
    assert module.complete_filing([old, same, future], "2026-11-10") == old
    assert module.complete_filing([same, future], "2026-11-10") is None
    result = module.C.latest_filings([old, future], "2026-11-10")["SYN"]
    assert result["fields"] == old["fields"]
    assert all(src["availableFrom"] == old["availableFrom"] for src in result["fieldSources"].values())


def test_current_etf_policy_and_four_draft_arms_stay_separate(evidence_first):
    folder, _ = evidence_first
    desk = json.loads((DESK / "desk.json").read_text())
    draft = json.loads((folder / "results/prospective-dry-run.json").read_text())
    assert "NOT_A_COHORT" in draft["label"]
    assert "ACTIVATION_BLOCKED" in draft["activation"]
    for region, etf in (("KR", "069500.KS"), ("US", "SPY")):
        assert desk["regions"][region]["production"]["weights"] == {etf: 1.0}
        arms = draft["regions"][region]["arms"]
        assert set(arms) == {"ETF100", "B1_ROE", "PRODUCTION", "B1_PLUS_AI"}
        assert arms["PRODUCTION"]["weights"] == arms["ETF100"]["weights"] == {etf: 1.0}
        assert arms["B1_PLUS_AI"]["status"] == "NO_RECORD"
        assert arms["B1_ROE"]["recordLabel"] == "UNVERIFIED_PROSPECTIVE_VIRTUAL"


@pytest.mark.parametrize("scenario", ["preview", "stale"])
def test_top_production_summary_qualifies_preview_and_stale_inputs(scenario):
    code = r"""const a=require('./app.js'),d=require('./research/decision_desk_v1/desk.json');
const now=process.argv[1]==='stale'?'2027-01-15T12:00:00Z':'2026-11-12T10:00:00Z';
if(d.regions.US.production.weekStatus!=='INTRA_WEEK_PREVIEW') throw new Error('fixture changed: re-audit the new snapshot');
const market=process.argv[1]==='stale'?'KR':'US';
const html=a.deskMarkup(d,market,Date.parse(now));
const box=html.match(/<article[^>]*data-desk-four="production"[^>]*>[\s\S]*?<\/article>/);
if(!box) throw new Error('summary not found'); process.stdout.write(box[0]);"""
    box = subprocess.check_output(["node", "-e", code, scenario], cwd=TARGET, text=True)
    if scenario == "preview":
        assert any(token in box for token in ("미리보기", "INTRA_WEEK_PREVIEW", "현재 판단 확인 불가")), box
    else:
        assert any(token in box for token in ("과거 기록", "현재 판단 확인 불가", "STALE")), box
