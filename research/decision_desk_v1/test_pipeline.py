"""Protocol v2 pipeline tests: legacy preservation, release-time rules, staged decisions, evaluator."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
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

LEGACY_SHA = {
    "protocol.json": "15d46dfde547cd0650f060c4f36a06959ad827cc821f36da727de15f577647e2",
    "inputs/2026-11/evidence-pack.json": "305d906a95c14ffde96e66e855ac2dc29848c2b98926f6d385fdb2bae258bfe0",
    "ai-reviews/2026-11.json": "256d7f15a56caa0fc3d99268922a6994e996207e8db6f0308a13b053949ab62f",
}
LEGACY_LEDGER_PREFIX_SHA = "3854d94f07f6f91dc4d74372e3e59132ab3adbf613eec1b95c0f43aaa1c7b050"


# ----------------------------------------------------------------------------- legacy is untouched
@pytest.mark.parametrize("rel, sha", sorted(LEGACY_SHA.items()))
def test_legacy_2026_11_files_are_byte_identical(rel, sha):
    assert hashlib.sha256((HERE / rel).read_bytes()).hexdigest() == sha


def test_legacy_ledger_lines_are_an_unchanged_prefix():
    lines = (HERE / "dry-run" / "ledger.jsonl").read_bytes().splitlines(keepends=True)
    assert hashlib.sha256(b"".join(lines[:6])).hexdigest() == LEGACY_LEDGER_PREFIX_SHA
    L.verify_chain(L.read(HERE / "dry-run" / "ledger.jsonl"))


def test_v2_protocol_cites_the_v1_hash():
    v2 = json.loads((HERE / "protocol-v2.json").read_text())
    assert v2["amends"]["sha256"] == LEGACY_SHA["protocol.json"]


# ----------------------------------------------------------------------------- release-time rules
def test_h10_released_monday_1615_et_or_next_business_day():
    assert A.release_utc("DEXKOUS", "2026-11-05") == pd.Timestamp("2026-11-09 21:15", tz="UTC")
    assert A.release_utc("DEXKOUS", "2026-10-30") == pd.Timestamp("2026-11-02 21:15", tz="UTC")
    # Monday 2026-10-12 is Columbus Day: the 10-05..10-09 week releases Tuesday
    assert A.release_utc("DEXKOUS", "2026-10-08") == pd.Timestamp("2026-10-13 20:15", tz="UTC")
    assert A.release_utc("DEXKOUS", "2008-03-03") is None  # weekly H.10 suspended


def test_h15_and_vix_next_business_day_1615_et():
    assert A.release_utc("DGS10", "2026-11-05") == pd.Timestamp("2026-11-06 21:15", tz="UTC")
    assert A.release_utc("DGS10", "2026-11-06") == pd.Timestamp("2026-11-09 21:15", tz="UTC")  # Friday -> Monday
    assert A.release_utc("VIXCLS", "2026-11-10") == pd.Timestamp("2026-11-12 21:15", tz="UTC")  # 11-11 Veterans Day


def test_cutoffs_are_regional_closes():
    assert A.cutoff_utc("KR", "2026-11-06") == pd.Timestamp("2026-11-06 06:30", tz="UTC")
    assert A.cutoff_utc("US", "2026-11-06") == pd.Timestamp("2026-11-06 21:00", tz="UTC")


def test_pit_review_is_reproducible_and_finds_the_known_defects():
    sys.path.insert(0, str(HERE / "audits"))
    import pit_review as R
    committed = json.loads((HERE / "audits" / "2026-11-pit-review.json").read_text())
    fresh = R.review()
    # The audit is pinned by a ledger annotation and is never regenerated. availability.py later gained the
    # #335 G1/G9 rules, which do not change any 2026-11 value: the result must match without the module stamp,
    # and the stamp must be the module as committed with the audit.
    stamp = committed["inputsSha256"].pop("availabilityModule")
    fresh["inputsSha256"].pop("availabilityModule")
    assert fresh == committed
    added = subprocess.check_output(["git", "log", "--format=%H", "--diff-filter=A", "--",
                                     "research/decision_desk_v1/audits/2026-11-pit-review.json"], cwd=HERE.parents[1], text=True).split()[-1]
    old = subprocess.check_output(["git", "show", f"{added}:research/decision_desk_v1/availability.py"], cwd=HERE.parents[1])
    assert hashlib.sha256(old).hexdigest() == stamp
    kr = committed["regions"]["KR"]
    assert "FRED DEXKOUS 2026-11-05" in kr["notPublicAtCutoff"]
    assert "Yahoo UUP close 2026-11-06" in kr["notPublicAtCutoff"]
    assert kr["after"]["macro"]["usdkrwH10"]["obsDate"] == "2026-10-30"
    us = committed["regions"]["US"]
    assert us["after"]["macro"]["vix"] == {"value": 16.61, "obsDate": "2026-11-04", "availableAtUtc": "2026-11-05T21:15:00Z"}
    for region in ("KR", "US"):
        cutoff = committed["regions"][region]["informationCutoffUtc"]
        macro = committed["regions"][region]["after"]["macro"]
        stamps = [v["availableAtUtc"] for v in macro.values() if isinstance(v, dict) and "availableAtUtc" in v]
        assert stamps and all(s <= cutoff for s in stamps)


# ----------------------------------------------------------------------------- ledger v2 / annotations / backdating
def _v2(**over):
    r = {"schema": L.SCHEMA_V2, "protocolVersion": 2, "region": "KR", "path": "BX", "reviewer": "gpt", "cohort": "2099-01",
         "signalAsOf": "2099-01-02", "informationCutoff": "2099-01-02T06:30:00Z", "generatedAt": "2099-01-03T00:00:00Z",
         "publishedAt": "2099-01-03T01:00:00Z", "modelVersion": "t", "sourceHashes": {"x": "y"}, "packetSha256": "p",
         "selectedTickers": [], "weights": {"069500.KS": 1.0}, "benchmark": "069500.KS", "investmentThesis": "t",
         "invalidationConditions": {}, "plannedExecution": "2099-01-06", "plannedExecutionCloseUtc": "2099-01-06T06:30:00Z",
         "registrationDeadlineUtc": "2099-01-06T00:00:00Z", "costs": {"stockRoundTripPct": 0.3, "benchmarkRoundTripPct": 0.1},
         "horizon126": None, "horizon252": None, "subsequentReturns": None, "status": "DRY_RUN_NOT_ACTIVATED", "missingDataReason": None}
    r.update(over)
    return r


@pytest.fixture
def dry(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path)
    return tmp_path / "ledger.jsonl"


def test_v2_registration_closes_at_the_deadline(dry):
    with pytest.raises(L.LedgerError, match="REGISTRATION_CLOSED"):
        L.append(dry, _v2(publishedAt="2099-01-06T00:00:01Z"))
    L.append(dry, _v2())


@pytest.mark.parametrize("over, msg", [({"path": "B0"}, "RULE_PATH_HAS_NO_REVIEWER"), ({"reviewer": None}, "NEEDS_A_REVIEWER"),
                                       ({"path": "B9"}, "BAD_SCHEMA")])
def test_v2_path_and_reviewer_rules(dry, over, msg):
    with pytest.raises(L.LedgerError, match=msg):
        L.append(dry, _v2(**over))


def test_a_conversation_pick_cannot_be_backdated_into_the_2026_11_cohort(dry):
    """009150.KS (an idea raised outside the cohort window) cannot become a 2026-11 signal."""
    legacy = L.read(HERE / "dry-run" / "ledger.jsonl")
    kr_b0 = next(r for r in legacy if r.get("path") == "B0" and r["region"] == "KR")
    for row in legacy:
        L.append(dry, {k: v for k, v in row.items() if k not in ("prevDigest", "digest")})
    late = _v2(cohort="2026-11", signalAsOf="2026-11-06", informationCutoff="2026-11-06T06:30:00Z",
               generatedAt="2026-11-20T00:00:00Z", publishedAt="2026-11-20T00:00:00Z", reviewer="gpt",
               selectedTickers=["009150.KS"], weights={"009150.KS": 0.1, "069500.KS": 0.9},
               plannedExecution=kr_b0["plannedExecution"], plannedExecutionCloseUtc=kr_b0["plannedExecutionCloseUtc"],
               registrationDeadlineUtc="2026-11-12T00:00:00Z")
    with pytest.raises(L.LedgerError, match="REGISTRATION_CLOSED"):
        L.append(dry, late)
    # and the primary B2 slot of 2026-11 is already taken by the legacy claude record
    with pytest.raises(L.LedgerError):
        L.append(dry, {**late, "path": "B2", "reviewer": "claude", "publishedAt": "2026-11-11T00:00:00Z",
                       "generatedAt": "2026-11-11T00:00:00Z", "registrationDeadlineUtc": "2026-11-12T00:00:00Z"})
    assert not any("009150.KS" in json.dumps(r) for r in L.read(HERE / "dry-run" / "ledger.jsonl"))


def test_annotations_cannot_change_decisions(dry):
    rec = L.append(dry, _v2())
    base = {"schema": L.ANNOTATION_SCHEMA, "cohort": "2099-01", "category": "PIT_CONTAMINATED",
            "recordDigests": [rec["digest"]], "detail": "x", "createdAt": "2099-01-04T00:00:00Z"}
    with pytest.raises(L.LedgerError, match="CANNOT_CHANGE"):
        L.append(dry, {**base, "weights": {"069500.KS": 1.0}})
    with pytest.raises(L.LedgerError, match="UNKNOWN_RECORD"):
        L.append(dry, {**base, "recordDigests": ["f" * 64]})
    L.append(dry, base)
    L.verify_chain(L.read(dry))


def test_committed_ledger_marks_2026_11_b2_contaminated_and_publication_verified():
    rows = L.read(HERE / "dry-run" / "ledger.jsonl")
    b2 = {r["digest"] for r in rows if r.get("schema") == L.SCHEMA and r["path"] == "B2"}
    notes = [a for a in rows if a.get("schema") == L.ANNOTATION_SCHEMA]
    pit = [a for a in notes if a["category"] == "PIT_CONTAMINATED"]
    assert len(pit) == 1 and set(pit[0]["recordDigests"]) == b2
    assert pit[0]["evidence"]["path"].endswith("audits/2026-11-pit-review.json")
    pub = {d for a in notes if a["category"] == "PUBLICATION_VERIFIED" for d in a["recordDigests"]}
    assert pub == {r["digest"] for r in rows if r.get("schema") == L.SCHEMA}


# ----------------------------------------------------------------------------- packet -> review -> decide (synthetic cohort)
def _fake_receipts(month):
    v1 = json.loads((HERE / "inputs" / "2026-11" / "evidence-pack.json").read_text())
    regions = {}
    for region, v in v1["regions"].items():
        regions[region] = {"asOfDate": v["asOfDate"], "receiptId": v["receiptId"], "digest": v["receiptDigest"],
                           "generatedAt": v["receiptGeneratedAt"], "status": v["productionStatus"], "weights": v["productionWeights"],
                           "noTradeReason": v["noTradeReason"], "calibrationOrdering": v["calibrationOrdering"], "costs": v["costs"],
                           "freshness": v["freshness"], "inputs": {"modelVersion": v["modelVersion"], "siteDataSha256": v["siteDataSha256"]},
                           "watchlist": [{k: x for k, x in c.items() if k not in ("gatesFailed", "source")} for c in v["candidates"]],
                           "candidates": []}
    return {"signalHistoryCommit": "synthetic", "receiptsBlob": "synthetic", "receiptsSha256": "synthetic", "regions": regions}


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "cohort_receipts", lambda commit, month: _fake_receipts(month))
    monkeypatch.setattr(P, "COHORTS", tmp_path / "cohorts")
    monkeypatch.setattr(D, "LEDGER", tmp_path / "dry-run" / "ledger.jsonl")
    monkeypatch.setattr(L, "DRY_RUN_DIR", tmp_path / "dry-run")
    monkeypatch.setattr(D, "committed_unchanged", lambda p: True)
    monkeypatch.setattr(D, "first_commit", lambda p: None)
    month = "2099-12"
    store = tmp_path / "cohorts" / month / "market"
    store.mkdir(parents=True)
    for f in (HERE / "inputs" / "2026-11" / "market").iterdir():
        (store / f.name).write_bytes(f.read_bytes())
    sealed = pd.Timestamp("2026-11-07T08:00:00Z")
    _, pk = P.write_packet("synthetic", month, fetch=False, now=sealed)
    return month, pk


def test_packet_is_pit_filtered_and_fixes_one_schedule(synthetic):
    month, pk = synthetic
    kr = pk["regions"]["KR"]
    assert kr["macro"]["usdkrwH10"]["obsDate"] == "2026-10-30"
    assert kr["macro"]["uupReturn126"]["lastSession"] == "2026-11-05"
    assert kr["gatePassers"] == ["021240.KS"] and pk["regions"]["US"]["gatePassers"] == ["MPC", "SPG", "TRV"]
    # sealed Sat 08:00Z + 48h -> first session opening after Mon 08:00Z
    assert kr["schedule"]["plannedExecution"] == "2026-11-10"
    assert pk["regions"]["US"]["schedule"]["plannedExecution"] == "2026-11-09"
    req = json.loads((P.COHORTS / month / "review-request.json").read_text())
    assert req["status"] == "AI_REVIEW_REQUIRED" and req["requiredReviewers"] == ["claude"]
    assert "gpt" in req["pendingApprovalReviewers"]
    with pytest.raises(RuntimeError, match="PACKET_ALREADY_EXISTS"):
        P.write_packet("synthetic", month, fetch=False)


def _fill(tpl: dict, select: dict[str, list[str]]) -> dict:
    rv = copy.deepcopy(tpl)
    rv["generatedAt"] = "2026-11-08T00:00:00Z"
    rv["knowledgeLimit"] = "read only the packet"
    for region, reg in rv["regions"].items():
        reg.update(marketLabel="NEUTRAL", marketInterpretation="x", macroLabel="NEUTRAL", macroInterpretation="x")
        for n in reg["names"]:
            on = n["ticker"] in select.get(region, [])
            n["layers"] = {k: (["SUPPORTS", "x"] if on and k in ("company", "price", "risk") else ["NEUTRAL", "x"]) for k in J.LAYERS}
            n["decision"] = "SELECT" if on else "REJECT"
            if on:
                n.update(reasons=["x"], thesis6m="x", thesis12m="x", catalysts=["x"], risks=["x"], invalidationConditions=["x"],
                         notVerified=["x"], whyVersusBenchmark="x")
            else:
                n["rejectionReason"] = "x"
        reg["regionDecision"] = {"selected": select.get(region, []), "zeroSelectionReason": None if select.get(region) else "none"}
    return rv


def test_review_template_check_and_decide(synthetic):
    month, pk = synthetic
    path = D.cmd_review_template(month, "claude")
    with pytest.raises(D.StageError, match="TODO"):
        D.cmd_check_review(month, "claude")
    path.write_text(json.dumps(_fill(json.loads(path.read_text()), {"US": ["TRV"]})))
    assert D.cmd_check_review(month, "claude") == ["KR: 0 names", "US: ['TRV']"]
    with pytest.raises(D.StageError, match="REGISTRATION_CLOSED"):
        D.cmd_decide(month, now="2026-11-12T00:00:00Z")
    recs = D.cmd_decide(month, now="2026-11-08T12:00:00Z")
    got = {(r["region"], r["path"], r["reviewer"]): r["weights"] for r in recs}
    assert got[("US", "B2", "claude")] == {"TRV": 0.1, "SPY": 0.9}
    assert got[("KR", "B2", "claude")] == {"069500.KS": 1.0}
    assert all(r["plannedExecution"] == pk["regions"][r["region"]]["schedule"]["plannedExecution"] for r in recs)
    with pytest.raises(D.StageError, match="ALREADY_DECIDED"):
        D.cmd_decide(month, now="2026-11-08T12:00:00Z")
    assert D.cohort_status(month)["stage"] == "AWAITING_PUBLICATION_VERIFICATION"


def test_missing_primary_review_records_no_b2_and_says_so(synthetic):
    month, _ = synthetic
    recs = D.cmd_decide(month, now="2026-11-08T12:00:00Z")
    assert {r["path"] for r in recs} == {"B0", "B1"}
    notes = [a for a in L.read(D.LEDGER) if a.get("schema") == L.ANNOTATION_SCHEMA]
    assert {a["category"] for a in notes} == {"B2_NO_REVIEW"}


def test_independence_needs_commitments_before_the_first_reveal(synthetic, monkeypatch):
    month, _ = synthetic
    for rid in ("claude", "gpt"):
        p = D.cmd_review_template(month, rid)
        p.write_text(json.dumps(_fill(json.loads(p.read_text()), {})))
        D.cmd_commit_review(month, rid)
    times = {"commitments/claude": "2026-11-08T01:00:00Z", "commitments/gpt": "2026-11-08T02:00:00Z",
             "reviews/claude": "2026-11-08T03:00:00Z", "reviews/gpt": "2026-11-08T04:00:00Z"}
    monkeypatch.setattr(D, "first_commit", lambda p: ("sha", next(v for k, v in times.items() if k in str(p).replace(".sha256", "").replace(".json", ""))))
    assert D.independence(month, ["claude", "gpt"]) == {"claude": "INDEPENDENT_BY_COMMIT_ORDER", "gpt": "INDEPENDENT_BY_COMMIT_ORDER"}
    times["commitments/gpt"] = "2026-11-08T05:00:00Z"  # gpt committed after seeing claude's reveal
    assert D.independence(month, ["claude", "gpt"])["gpt"] == "INDEPENDENCE_NOT_VERIFIED"


# ----------------------------------------------------------------------------- evaluator
def _chart(rows, dividends=(), splits=(), tz="America/New_York"):
    ts = [int(pd.Timestamp(d + " 09:30", tz=tz).timestamp()) for d, _, _ in rows]
    ev = {"dividends": {str(i): {"date": int(pd.Timestamp(d + " 09:30", tz=tz).timestamp()), "amount": a} for i, (d, a) in enumerate(dividends)},
          "splits": {str(i): {"date": int(pd.Timestamp(d + " 09:30", tz=tz).timestamp()), "numerator": n, "denominator": m} for i, (d, n, m) in enumerate(splits)}}
    return {"chart": {"result": [{"meta": {"exchangeTimezoneName": tz}, "timestamp": ts, "events": ev,
                                  "indicators": {"quote": [{"close": [c for _, c, _ in rows], "volume": [v for _, _, v in rows]}]}}]}}


def _sessions(start, n):
    cal = A.calendar("US")
    s = cal.sessions_in_range(start, cal.last_session)
    return [str(pd.Timestamp(x).date()) for x in s[: n + 1]]


def test_total_return_reinvests_distributions_and_blocks_unverified_events():
    days = _sessions("2026-11-11", 5)
    rows = [(d, 100.0 + i, 1000) for i, d in enumerate(days)]
    df = EV.parse_chart(_chart(rows, dividends=[(days[2], 2.0)]))
    assert EV.total_return(df, days[0], days[5]) == pytest.approx((101 / 100) * ((102 + 2) / 101) * (103 / 102) * (104 / 103) * (105 / 104) - 1)
    assert EV.window_block("US", "X", df, days[0], days[5], {}) is None
    split = EV.parse_chart(_chart(rows, splits=[(days[3], 2, 1)]))
    assert EV.window_block("US", "X", split, days[0], days[5], {}).startswith("UNVERIFIED_SPLIT")
    assert EV.window_block("US", "X", split, days[0], days[5], {("X", days[3]): {}}) is None
    gap = EV.parse_chart(_chart([r for r in rows if r[0] != days[2]]))
    assert EV.window_block("US", "X", gap, days[0], days[5], {}).startswith("MISSING_SESSION_CLOSE")
    halted = EV.parse_chart(_chart([(d, c, 0 if d == days[1] else v) for d, c, v in rows]))
    assert EV.window_block("US", "X", halted, days[0], days[5], {}).startswith("ZERO_VOLUME")
    jump = EV.parse_chart(_chart([(d, c * (3 if d >= days[4] else 1), v) for d, c, v in rows]))
    assert EV.window_block("US", "X", jump, days[0], days[5], {}).startswith("UNEXPLAINED_MOVE")
    assert EV.window_block("US", "X", df, days[0], "2027-01-04", {}) == "NO_EXIT_CLOSE"


def test_outcomes_wait_then_score_with_costs_and_never_zero_fill(dry, monkeypatch):
    days = _sessions("2026-11-11", 130)
    rec = L.append(dry, _v2(region="US", path="B2", reviewer="claude", benchmark="SPY", selectedTickers=["TRV"],
                            weights={"TRV": 0.1, "SPY": 0.9}, plannedExecution=days[0],
                            informationCutoff="2026-11-06T21:00:00Z", generatedAt="2026-11-08T00:00:00Z",
                            publishedAt="2026-11-08T01:00:00Z", registrationDeadlineUtc="2026-11-11T14:30:00Z",
                            plannedExecutionCloseUtc="2026-11-11T21:00:00Z", cohort="2026-12"))
    trv = EV.parse_chart(_chart([(d, 100 * 1.001 ** i, 10) for i, d in enumerate(days)]))
    spy = EV.parse_chart(_chart([(d, 100 * 1.0005 ** i, 10) for i, d in enumerate(days)]))
    early = EV.outcomes([rec], {"TRV": trv, "SPY": spy}, "2027-01-15T00:00:00Z")
    assert {o["status"] for o in early} == {"PENDING"}
    after = days[126]
    late = EV.outcomes([rec], {"TRV": trv, "SPY": spy}, f"{days[127]}T23:00:00Z")
    o126 = next(o for o in late if o["horizon"] == 126)
    assert o126["status"] == "SCORED" and o126["horizonEndSession"] == after
    r_t, r_s = 1.001 ** 126 - 1, 1.0005 ** 126 - 1
    port = 0.1 * ((1 + r_t) * (1 - 0.003) - 1) + 0.9 * ((1 + r_s) * (1 - 0.001) - 1)
    assert o126["excessAfterCostPct"] == pytest.approx((port - ((1 + r_s) * 0.999 - 1)) * 100)
    blocked = EV.outcomes([rec], {"SPY": spy}, f"{days[127]}T23:00:00Z")
    b126 = next(o for o in blocked if o["horizon"] == 126)
    assert b126["status"] == "SOURCE_BLOCKED" and b126["excessAfterCostPct"] is None
    L.append(dry, o126)
    L.verify_chain(L.read(dry))
