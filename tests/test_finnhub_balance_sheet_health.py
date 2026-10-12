"""US Finnhub balance-sheet coverage repair v1: what is pinned, and what is deliberately NOT repaired.

The loss: every filing that first reached the US store from 2026-10-07 has an empty `bs` while `ic`/`cf` look like September's. The store keeps
`report.bs` and nothing else, so "the vendor omitted it" and "the vendor moved it" are indistinguishable, and the collector drops every re-served
copy of a stored filing. The change adds EVIDENCE (response shape, re-served comparison, a read-side quarantine view, a bounded probe) and
changes no stored byte, no account, no visibility rule and no feature. Pinned here:

  * September-style filings parse exactly as before; October-style ones keep an empty `bs` and nothing is invented, borrowed or zeroed;
  * a missing total assets is a reason code, never zero, and never taken from the previous filing or another company;
  * TTM operating cash flow and the visibility day are identical whether or not the balance sheet exists;
  * the collector's shard bytes for stored filings are identical after a re-serve that is richer, poorer or changed, and the comparison is reported;
  * the committed audit is a deterministic reading of a pinned signal-history commit and computes no return, IC or portfolio;
  * the frozen feature and derivation modules are byte-identical to the ones the P4 preflight pinned.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_derive as US                    # noqa: E402
from pipeline import finnhub_fundamentals as FF              # noqa: E402
from pipeline import finnhub_response_health as FH           # noqa: E402
from pipeline import historical_store as HS                  # noqa: E402
from pipeline import us_cash_profitability as CP             # noqa: E402


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


COLLECT = _load("collect_finnhub_fundamentals_bs", "scripts/collect_finnhub_fundamentals.py")
AUDIT = _load("audit_finnhub_bs_coverage", "scripts/audit_finnhub_balance_sheet_coverage.py")
PROBE = _load("probe_finnhub_bs", "scripts/probe_finnhub_balance_sheet.py")

AUDIT_JSON = ROOT / "docs/us-readiness/us-finnhub-balance-sheet-coverage-audit-v1.json"
PLAN_JSON = ROOT / "docs/us-readiness/us-finnhub-balance-sheet-recovery-plan-v1.json"
PREFLIGHT_JSON = ROOT / "docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json"
SECRET = "SECRETKEY-do-not-print"


def usd(concept, value):
    return {"concept": "us-gaap_" + concept, "label": concept, "unit": "usd", "value": value}


def raw_filing(accession="0000000000-26-000001", form="10-Q", year=2026, quarter=1, start="2026-01-01", end="2026-03-31",
               filed="2026-05-01", assets=1000.0, bs=True, bs_key="bs", extra=None):
    report = {"ic": [usd("NetIncomeLoss", 30.0), usd("OperatingIncomeLoss", 35.0)],
              "cf": [usd("NetCashProvidedByUsedInOperatingActivities", 50.0)]}
    if bs:
        report[bs_key] = [usd("Assets", assets), usd("Liabilities", 400.0)]
    elif bs_key == "EMPTY":
        report["bs"] = []
    out = {"accessNumber": accession, "cik": "123", "form": form, "year": year, "quarter": quarter, "startDate": start,
           "endDate": end, "filedDate": filed, "acceptedDate": filed + " 06:00:00", "report": report}
    out.update(extra or {})
    return out


# ---------------------------------------------------------------- parsing and the three kinds of absence
def test_september_style_filing_is_stored_exactly_as_before():
    record, reason = FF.build_record("AAA", raw_filing(), "2026-09-13T10:00:00Z", FF.QUARTERLY)
    assert reason == ""
    assert record["id"] == "AAA|0000000000-26-000001" and record["availableFrom"] == "2026-05-01"
    assert record["acceptedDate"] == "2026-05-01 06:00:00" and record["periodEnd"] == "2026-03-31" and record["periodDays"] == 89
    assert [e["concept"] for e in record["statements"]["bs"]] == ["us-gaap_Assets", "us-gaap_Liabilities"]
    assert US.amount(record, "bs", US.ASSETS) == 1000.0 and FH.stored_balance_sheet_status(record) == FH.BS_ASSETS_STATED


def test_october_style_filing_keeps_an_empty_balance_sheet_and_nothing_is_invented():
    record, _ = FF.build_record("AAA", raw_filing(bs=False), "2026-10-08T10:00:00Z", FF.QUARTERLY)
    assert record["statements"]["bs"] == [] and record["statements"]["ic"] and record["statements"]["cf"]
    assert US.amount(record, "bs", US.ASSETS) is None
    assert FH.stored_balance_sheet_status(record) == FH.STORED_BS_LOST
    # The record is exactly the September one minus the section: no zero, no placeholder, no copied total.
    full, _ = FF.build_record("AAA", raw_filing(), "2026-10-08T10:00:00Z", FF.QUARTERLY)
    full["statements"]["bs"] = []
    assert record == full


def test_balance_sheet_status_separates_the_five_shapes_the_store_collapses():
    assert FH.balance_sheet_status(raw_filing()) == FH.BS_ASSETS_STATED
    no_assets = raw_filing()
    no_assets["report"]["bs"] = [usd("Liabilities", 1.0)]
    assert FH.balance_sheet_status(no_assets) == FH.BS_ASSETS_NOT_STATED
    assert FH.balance_sheet_status(raw_filing(bs=False, bs_key="EMPTY")) == FH.BS_EMPTY
    assert FH.balance_sheet_status(raw_filing(bs=False)) == FH.BS_KEY_ABSENT
    assert FH.balance_sheet_status({"report": {}}) == FH.NO_STATEMENTS
    renamed = raw_filing(bs=True, bs_key="balanceSheet")                       # the sheet exists, under a key we do not read
    assert FH.balance_sheet_status(renamed) == FH.BS_KEY_ABSENT
    assert FH.unknown_keys(renamed) == ([], ["balanceSheet"])


def _chain(q2_assets):
    def rec(year, stage, form, end, days, filed, ni, ocf, oi, assets):
        statements = {"ic": [usd("NetIncomeLoss", ni), usd("OperatingIncomeLoss", oi)],
                      "cf": [usd("NetCashProvidedByUsedInOperatingActivities", ocf)],
                      "bs": [] if assets is None else [usd("Assets", assets)]}
        return {"id": f"X-{year}-{stage}", "ticker": "X", "fiscalYear": year, "form": form, "periodDays": days,
                "periodEnd": end, "availableFrom": filed, "acceptedDate": None, "source": "finnhub/financials-reported",
                "statements": statements}
    return [rec(2025, FF.FY, "10-K", "2025-12-31", 365, "2026-02-20", 100.0, 150.0, 130.0, 1000.0),
            rec(2025, FF.Q2, "10-Q", "2025-06-30", 181, "2025-08-10", 40.0, 60.0, 50.0, 950.0),
            rec(2026, FF.Q2, "10-Q", "2026-06-30", 181, "2026-08-10", 55.0, 80.0, 70.0, q2_assets)]


def test_missing_assets_is_a_reason_never_a_zero_and_never_borrowed_from_another_filing():
    with_bs = CP.features_as_of(_chain(1200.0), "2026-09-11")
    without = CP.features_as_of(_chain(None), "2026-09-11")
    assert with_bs["cashOperatingProfitability"] == pytest.approx((150.0 - 60.0 + 80.0) / 1200.0)
    assert without["cashOperatingProfitability"] is None and without["state"]["cashOperatingProfitability"] == CP.ASSETS_NOT_STATED
    assert without["accrualsToAssets"] is None and without["operatingProfitabilityToAssets"] is None
    # Not 1000 (the annual filing's total) and not 0: the current filing states no total, so no ratio exists.
    assert without["cashOperatingProfitability"] != pytest.approx(170.0 / 1000.0)


def test_ttm_cash_flow_and_visibility_are_identical_with_or_without_the_balance_sheet():
    chains = {"with": _chain(1200.0), "without": _chain(None)}
    ttm = {}
    for name, records in chains.items():
        by_key = US.index_filings(CP.visible_records(records, "2026-09-11"))
        key = CP.current_key(by_key)
        ttm[name] = (key, US.trailing_twelve_months(by_key, key[0], key[1], "operatingCashFlow")[0],
                     CP.visible_day(by_key[key]))
    assert ttm["with"] == ttm["without"] and ttm["with"][1] == pytest.approx(150.0 - 60.0 + 80.0)
    for name, records in chains.items():
        assert CP.features_as_of(records, "2026-08-10")["filingVisibleDay"] == "2026-02-20"   # strictly after the available day
        assert CP.features_as_of(records, "2026-08-11")["filingVisibleDay"] == "2026-08-10"


# ---------------------------------------------------------------- health observation
def test_health_reports_new_and_reserved_copies_without_touching_anything():
    complete, _ = FF.build_record("AAA", raw_filing(), "t", FF.QUARTERLY)
    lost, _ = FF.build_record("BBB", raw_filing(accession="0000000000-26-000002", bs=False), "t", FF.QUARTERLY)
    changed_before, _ = FF.build_record("CCC", raw_filing(accession="0000000000-26-000003"), "t", FF.QUARTERLY)
    health = FH.ResponseHealth()
    frozen = copy.deepcopy([complete, lost, changed_before])
    health.observe("quarterly", raw_filing(accession="0000000000-26-000009", bs=False), None, "DDD|new")          # NEW and lost
    health.observe("quarterly", raw_filing(accession="0000000000-26-000002"), lost, "BBB|completed")              # stored lost, now served
    health.observe("quarterly", raw_filing(bs=False), complete, "AAA|regressed")                                  # stored had it, now not
    health.observe("quarterly", raw_filing(accession="0000000000-26-000003", assets=2000.0), changed_before, "CCC|changed")
    health.observe("annual", raw_filing(accession="0000000000-26-000010", bs_key="balanceSheet", extra={"unexpected": 1}),
                   None, "EEE|moved")
    summary = health.summary()
    assert [complete, lost, changed_before] == frozen
    assert summary["new"] == {"filings": 2, "balanceSheetMissing": 2}
    assert summary["seenAgain"]["filings"] == 3 and summary["seenAgain"]["storedLostButServedNow"] == 1
    assert summary["seenAgain"]["storedHadButNotServedNow"] == 1 and summary["seenAgain"]["bothHaveBalanceSheet"] == 1
    assert summary["seenAgain"]["sectionContentChangedSinceStored"] == {"bs": 1}
    assert summary["completionCandidates"] == ["BBB|completed"] and summary["storedHadButNotServedNow"] == ["AAA|regressed"]
    assert summary["unknownFilingKeys"] == {"unexpected": 1} and summary["unknownReportKeys"] == {"balanceSheet": 1}
    assert summary["degraded"] is True and "no record, shard or account" in summary["note"]


def test_a_normal_run_is_not_flagged_and_the_history_is_bounded():
    health = FH.ResponseHealth()
    for i in range(100):
        health.observe("quarterly", raw_filing(accession=f"0000000000-26-{i:06d}", bs=(i != 0)), None, f"A|{i}")
    assert health.summary()["new"] == {"filings": 100, "balanceSheetMissing": 1} and health.summary()["degraded"] is False
    history = None
    for i in range(FH.HISTORY_LIMIT + 7):
        history = FH.merge_history(history, health.summary(), f"2026-10-{i:02d}")
    assert len(history["runs"]) == FH.HISTORY_LIMIT and history["runs"][-1]["collectedAt"] == f"2026-10-{FH.HISTORY_LIMIT + 6:02d}"


def test_quarantine_is_a_read_side_view_that_edits_nothing():
    good, _ = FF.build_record("AAA", raw_filing(), "t", FF.QUARTERLY)
    lost, _ = FF.build_record("BBB", raw_filing(accession="0000000000-26-000002", bs=False), "t", FF.QUARTERLY)
    empty, _ = FF.build_record("CCC", {**raw_filing(accession="0000000000-26-000003"), "report": {}}, "t", FF.QUARTERLY)
    records = [good, lost, empty]
    before = copy.deepcopy(records)
    view = FH.balance_sheet_quarantine(records)
    assert [v["ticker"] for v in view] == ["BBB"] and records == before


# ---------------------------------------------------------------- the collector: append-only, and the comparison is reported
def _run_collect(tmp_path, monkeypatch, capsys, filings, through, store=None):
    store = store or tmp_path / "store"
    monkeypatch.setenv("FINNHUB_API_KEY", SECRET)
    monkeypatch.setattr(COLLECT, "fetch_window", lambda key, ticker, start, end, freq=FF.QUARTERLY, timeout=45: (copy.deepcopy(filings), "SERVED"))
    code = COLLECT.main([str(store), "--tickers", "AAA", "--from-year", "2026", "--through", through, "--max-calls", "20", "--pace", "0",
                         "--freq", "quarterly"])
    out = capsys.readouterr().out
    return code, store, out


def _shard_bytes(store):
    return {p.name: p.read_bytes() for p in sorted(store.glob("finnhub-*.jsonl.gz"))}


def test_collector_never_rewrites_a_stored_filing_whatever_the_vendor_now_sends(tmp_path, monkeypatch, capsys):
    code, store, _ = _run_collect(tmp_path, monkeypatch, capsys, [raw_filing(bs=False)], "2026-10-08")      # stored WITHOUT a balance sheet
    assert code == 0
    first = _shard_bytes(store)
    record = list(HS.read_jsonl(next(iter(store.glob("finnhub-*.jsonl.gz")))))[0]
    assert record["statements"]["bs"] == []

    code, _, out = _run_collect(tmp_path, monkeypatch, capsys, [raw_filing(assets=1500.0)], "2026-10-12", store)   # now served WITH one
    assert code == 0 and _shard_bytes(store) == first                                    # the stored copy is not replaced
    health = json.loads((store / "response-health.json").read_text())
    last = health["runs"][-1]
    assert last["seenAgain"]["storedLostButServedNow"] >= 1 and last["completionCandidates"] == ["AAA|0000000000-26-000001"]
    assert "저장본엔 없고 이번엔 있음" in out

    code, _, _ = _run_collect(tmp_path, monkeypatch, capsys, [raw_filing(bs=False)], "2026-10-13", store)        # and poorer again
    assert code == 0 and _shard_bytes(store) == first
    assert len(json.loads((store / "response-health.json").read_text())["runs"]) == 3


def test_collector_warns_but_does_not_fail_when_new_filings_lack_a_balance_sheet(tmp_path, monkeypatch, capsys):
    code, store, out = _run_collect(tmp_path, monkeypatch, capsys, [raw_filing(bs=False)], "2026-10-08")
    assert code == 0 and "::warning title=finnhub balance sheet missing::" in out
    assert json.loads((store / "response-health.json").read_text())["runs"][-1]["degraded"] is True
    assert SECRET not in out and SECRET not in (store / "response-health.json").read_text()
    assert not list(store.glob("finnhub-response-health*"))                              # the sidecar can never match the shard glob


def test_a_healthy_collection_writes_the_same_shard_as_the_record_builder(tmp_path, monkeypatch, capsys):
    code, store, out = _run_collect(tmp_path, monkeypatch, capsys, [raw_filing()], "2026-10-08")
    assert code == 0 and "::warning" not in out
    rows = list(HS.read_jsonl(next(iter(store.glob("finnhub-*.jsonl.gz")))))
    expected, _ = FF.build_record("AAA", raw_filing(), rows[0]["collectedAt"], FF.QUARTERLY)
    assert rows == [expected]


# ---------------------------------------------------------------- the probe
def _described(stored_status_bs, fresh_bs, *, moved=False, quarter=2):
    stored = None if stored_status_bs is None else {"status": stored_status_bs, "collectedAt": "x", "balanceSheetEntries": 0}
    return {"stored": stored, "balanceSheetStatus": fresh_bs, "balanceLikeKeysOutsideBs": ["report.balanceSheet"] if moved else [],
            "assetsInOtherSections": []}


def test_probe_verdict_distinguishes_the_four_explanations_and_never_guesses():
    stated, lost = FH.BS_ASSETS_STATED, FH.STORED_BS_LOST
    assert PROBE.verdict([_described(stated, stated), _described(lost, stated)])["verdict"] == PROBE.SERVED_NOW
    assert PROBE.verdict([_described(stated, stated), _described(lost, FH.BS_KEY_ABSENT)])["verdict"] == PROBE.NEW_ONLY
    assert PROBE.verdict([_described(stated, FH.BS_EMPTY), _described(lost, FH.BS_EMPTY)])["verdict"] == PROBE.ENDPOINT_WIDE
    assert PROBE.verdict([_described(stated, stated), _described(lost, FH.BS_KEY_ABSENT, moved=True)])["verdict"] == PROBE.KEY_MOVED
    assert PROBE.verdict([_described(None, FH.BS_EMPTY)])["verdict"] == PROBE.INCONCLUSIVE
    assert PROBE.verdict([])["verdict"] == PROBE.INCONCLUSIVE


def test_probe_run_is_bounded_keeps_raw_bodies_and_never_leaks_the_key(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    q1, _ = FF.build_record("AAA", raw_filing(), "2026-09-14T00:00:00Z", FF.QUARTERLY)
    q2, _ = FF.build_record("AAA", raw_filing(accession="0000000000-26-000002", quarter=2, start="2026-04-01", end="2026-06-30",
                                              filed="2026-07-30", bs=False), "2026-10-08T00:00:00Z", FF.QUARTERLY)
    HS.write_shard(store / "finnhub-2026.jsonl.gz", [q1, q2])
    served = json.dumps({"data": [raw_filing(), raw_filing(accession="0000000000-26-000002", quarter=2, start="2026-04-01",
                                                           end="2026-06-30", filed="2026-07-30", bs=False)], "symbol": "AAA"})
    calls = []

    def fake_fetch(key, ticker, freq, start, end, timeout=45):
        calls.append((ticker, freq, start, end))
        return "HTTP_200", served

    report, raw = PROBE.run(SECRET, store, ["AAA", "BBB", "CCC"], 2, "2026-10-12", fetch=fake_fetch, pace=0)
    assert len(calls) == 2 == report["calls"] and len(raw) == 2                          # max-calls is a hard stop
    assert report["verdict"] == PROBE.NEW_ONLY
    assert raw[0]["body"] == served and raw[0]["bodySha256"] == hashlib.sha256(served.encode()).hexdigest()
    assert SECRET not in json.dumps(report) and SECRET not in json.dumps(raw)
    paired = [row for row in report["filings"] if row["id"].startswith("AAA|")]
    assert paired and all(row["stored"]["status"] in (FH.BS_ASSETS_STATED, FH.STORED_BS_LOST) for row in paired)
    assert all(row["stored"] is None for row in report["filings"] if not row["id"].startswith("AAA|"))      # unknown ids are not paired
    assert PROBE.main(["--store", str(store), "--output", str(tmp_path / "o.json"), "--raw-out", str(tmp_path / "r.gz")]) == 1   # no key: stops
    assert PROBE.HARD_CEILING == 20


def test_probe_refuses_a_budget_above_the_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", SECRET)
    assert PROBE.main(["--store", str(tmp_path), "--max-calls", "21", "--output", str(tmp_path / "o"), "--raw-out", str(tmp_path / "r")]) == 2


def test_probe_finds_a_balance_sheet_filed_under_another_key():
    filing = raw_filing(bs=True, bs_key="balanceSheet")
    row = PROBE.describe_filing("AAA", filing, None)
    assert row["balanceSheetStatus"] == FH.BS_KEY_ABSENT and row["balanceLikeKeysOutsideBs"] == ["report.balanceSheet"]
    mis_sectioned = raw_filing(bs=False)
    mis_sectioned["report"]["cf"].append(usd("Assets", 5.0))
    assert PROBE.describe_filing("AAA", mis_sectioned, None)["assetsInOtherSections"] == ["cf"]
    assert PROBE.balance_like_keys({"report": {"bs": [], "ic": [], "subsidiaries": 1}}) == []


# ---------------------------------------------------------------- the audit
def _synthetic_store(tmp_path):
    store = tmp_path / "audit-store"
    store.mkdir()
    rows = []
    for ticker, filed_q1 in (("AAPL", "2026-05-01"), ("MSFT", "2026-04-29")):
        rows.append(FF.build_record(ticker, raw_filing(filed=filed_q1, assets=1000.0), "2026-09-14T00:00:00Z", FF.QUARTERLY)[0])
        rows.append(FF.build_record(ticker, raw_filing(accession="0000000000-26-000002", quarter=2, start="2026-04-01", end="2026-06-30",
                                                       filed="2026-07-30", bs=False), "2026-10-08T00:00:00Z", FF.QUARTERLY)[0])
    HS.write_shard(store / "finnhub-2026.jsonl.gz", rows)
    return store


def test_audit_reads_cohorts_without_touching_the_store_and_is_deterministic(tmp_path):
    store = _synthetic_store(tmp_path)
    before = _shard_bytes(store)
    rows, shards = AUDIT.read_store(store)
    one = AUDIT.build(rows, shards, {"store": "synthetic", "commit": None})
    two = AUDIT.build(*AUDIT.read_store(store), {"store": "synthetic", "commit": None})
    assert json.dumps(one, sort_keys=True) == json.dumps(two, sort_keys=True) and _shard_bytes(store) == before
    assert one["cohorts"]["september"]["balanceSheetAbsent"] == 0 and one["cohorts"]["october"]["balanceSheetAbsentPct"] == 100.0
    assert one["facts"]["everyLateFilingMissesBalanceSheet"] and one["facts"]["lateIdsAlreadyInEarlierStore"] == 0
    assert one["causeClassification"]["C_frequency_behaviour_changed"] == "REFUTED"
    assert one["quarantineView"]["records"] == 2 and one["evidenceGap"]["rawResponseRetained"] is False
    assert all(s["sha256"] == hashlib.sha256((store / s["shard"]).read_bytes()).hexdigest() for s in one["shards"])


def test_audit_refuses_to_write_into_a_sealed_results_directory(tmp_path):
    with pytest.raises(SystemExit):
        AUDIT.main(["--store", str(_synthetic_store(tmp_path)), "--output", str(ROOT / "docs/results/should-not-exist.json")])


# ---------------------------------------------------------------- the committed evidence
@pytest.fixture(scope="module")
def audit():
    return json.loads(AUDIT_JSON.read_text())


def test_committed_audit_pins_the_signal_history_commit_and_the_measured_gap(audit):
    assert audit["source"]["commit"] == "4ddeb87bac078f2681fa83b1225111896edb319b"
    cohorts = audit["cohorts"]
    assert cohorts["october"]["filings"] == 619 and cohorts["october"]["balanceSheetPresent"] == 0
    assert cohorts["october"]["incomeStatementPresent"] == 618 and cohorts["october"]["cashFlowPresent"] == 619
    assert cohorts["september"]["filings"] == 34327 and cohorts["september"]["balanceSheetAbsent"] == 142
    assert cohorts["byCollectionDay"]["2026-10-08"]["filings"] == 588
    assert sum(c["filings"] for c in cohorts["byCollectionDay"].values()) == audit["storeTotals"]["filings"] == 34946
    assert audit["facts"]["lateIdsAlreadyInEarlierStore"] == 0 and audit["facts"]["septemberCeilingOfFilingDate"] == "2026-06-26"
    assert audit["causeClassification"]["A_source_omitted_balance_sheet"].startswith("NOT_REFUTED_NOT_CONFIRMED")
    assert audit["causeClassification"]["B_schema_or_key_changed"].startswith("NOT_REFUTED_NOT_CONFIRMED")
    assert audit["causeClassification"]["C_frequency_behaviour_changed"] == "REFUTED"


def test_committed_audit_computes_no_return_ic_or_portfolio(audit):
    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for item in node:
                yield from keys(item)
    forbidden = ("rankic", "excess", "forward", "sharpe", "cagr", "drawdown", "weights", "portfolio", "alpha")
    assert not [k for k in keys(audit) if any(f in k.lower() for f in forbidden)]
    source = (ROOT / "scripts/audit_finnhub_balance_sheet_coverage.py").read_text()
    tree = ast.parse(source)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not {m for m in imported if any(w in m for w in ("replay", "outcome", "kelly", "portfolio", "label", "weekly_publish"))}


def test_feature_coverage_shows_the_signal_is_not_measurable_now(audit):
    last_known = audit["featureCoverage"]["knownByObservationDate"][-1]
    last_stored = audit["featureCoverage"]["asStoredAtThisCommit"][-1]
    assert last_known["asOf"] == last_stored["asOf"] == "2026-10-09" and last_known["tickers"] == 503
    assert last_stored["cashOperatingProfitability"].get("AVAILABLE", 0) <= 5 and last_stored["availablePct"] < 1.0
    assert last_known["cashOperatingProfitability"]["ASSETS_NOT_STATED"] > 400
    mid_july = next(x for x in audit["featureCoverage"]["asStoredAtThisCommit"] if x["asOf"] == "2026-07-17")
    assert mid_july["availablePct"] > 90.0                                                # before the Q2 filings the signal measured


# ---------------------------------------------------------------- frozen things did not move
def test_frozen_feature_and_derivation_modules_are_byte_identical_to_their_pins():
    pins = json.loads(PREFLIGHT_JSON.read_text())["identities"]
    sha = lambda rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()               # noqa: E731
    assert sha("pipeline/us_cash_profitability.py") == pins["code:pipeline/us_cash_profitability.py"]
    assert sha("pipeline/finnhub_fundamentals.py") == "95b5090f1a306df5bc6231d952c42dfc85097a3a1f9f90a82bb4fa8af4f3a20d"
    assert sha("pipeline/finnhub_derive.py") == "2ceaf6a081a5fbbd893398a68e58006254da06492629d9e8824e0e835b848b56"


def test_no_workflow_or_protected_path_is_edited_by_this_change():
    import subprocess
    try:
        diff = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"], capture_output=True, text=True, cwd=ROOT, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("no git history available")
    touched = set(diff.split())
    protected = {".github/workflows/fundamentals.yml", ".github/workflows/tests.yml", ".github/workflows/probes.yml",
                 "pipeline/us_real_source_preflight.py", "scripts/preflight_us_real_sources.py", "pipeline/datafeed.py",
                 "pipeline/us_cash_profitability.py", "pipeline/finnhub_fundamentals.py", "pipeline/finnhub_derive.py"}
    assert not touched & protected and not [p for p in touched if p.startswith("docs/results/")]


def test_new_modules_import_nothing_that_decides_or_publishes():
    for relative in ("pipeline/finnhub_response_health.py", "scripts/probe_finnhub_balance_sheet.py"):
        tree = ast.parse((ROOT / relative).read_text())
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not {m for m in imported if any(w in m for w in ("replay", "outcome", "kelly", "portfolio", "weekly_publish", "datafeed"))}, relative


def test_recovery_plan_authorizes_nothing_and_is_bounded():
    plan = json.loads(PLAN_JSON.read_text())
    assert plan["authorizes"] == "NOTHING" and plan["executed"] is False and plan["status"] == "PROPOSED_NOT_AUTHORIZED"
    assert all(step["ownerApproval"] in (True, False) for step in plan["steps"])
    probe = next(s for s in plan["steps"] if s["id"] == "S0_PROBE")
    assert probe["maxCalls"] <= PROBE.HARD_CEILING and probe["writesInto"] == "nothing in the repository or the store"
    for step in plan["steps"]:
        if step["id"].startswith("S2"):
            assert step["ownerApproval"] is True and step["maxCalls"] <= 700 and step["rewritesStoredShards"] is False
    assert plan["productionBackfillExecutedByThisChange"] is False
