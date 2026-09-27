"""KR accounting coverage repair: raw DART rows, element-id canonicalization, audit.

Every test here is network-free and outcome-free: fixtures are DART-shaped
statement rows and filing metadata, never a price after a signal date.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pipeline import accounting_quality as AQ
from pipeline import alpha_opportunity_features as AF
from pipeline import dart_canonical_accounts as C
from pipeline import dart_derive as DD
from pipeline import dart_fundamentals as DF
from pipeline import dart_raw_statements as RS
from pipeline import historical_store as HS
from pipeline import alpha_opportunity_kr_accounting_coverage_audit as A
from scripts import build_kr_canonical_filings as BUILD
from scripts import collect_dart_raw_statements as COLLECT

ROOT = Path(__file__).resolve().parent.parent


def row(sj, name, aid, amount, add=None, rcept="20250515000123", detail="-"):
    out = {"rcept_no": rcept, "sj_div": sj, "account_nm": name, "account_id": aid,
           "account_detail": detail, "thstrm_amount": str(amount)}
    if add is not None:
        out["thstrm_add_amount"] = str(add)
    return out


def raw_record(rows, *, ticker="000001.KS", year=2025, code="11013", fs="CFS"):
    record, reason = RS.build_raw_record(
        ticker=ticker, stock_code=ticker[:6], corp_code="00000001", fiscal_year=year,
        report_code=code, fs_div=fs, rows=rows,
        attempts=[{"fsDiv": fs, "status": "000", "message": "정상", "rows": len(rows)}],
        collected_at="2026-09-27T00:00:00Z")
    assert record is not None, reason
    return record


QUARTER_ROWS = [
    row("BS", "자산총계", "ifrs-full_Assets", 1000),
    row("BS", "부채총계", "ifrs-full_Liabilities", 400),
    row("CIS", "매출액", "ifrs-full_Revenue", 300, 300),
    row("CIS", "분기순이익(손실)", "ifrs-full_ProfitLoss", 50, 50),
    row("CF", "영업활동현금흐름", "ifrs-full_CashFlowsFromUsedInOperatingActivities", 70),
]


# --------------------------------------------------------------------------- #
# Canonicalization: which rows may become which account
# --------------------------------------------------------------------------- #
def test_quarterly_net_income_label_is_admitted_by_its_ifrs_element():
    record, _ = C.canonical_record(raw_record(QUARTER_ROWS))
    entry = record["accounts"]["당기순이익"]
    assert entry["amounts"] == {"thstrm_amount": 50.0, "thstrm_add_amount": 50.0}
    assert entry["statement"] == "CIS"
    how = record["canonicalization"]["accounts"]["당기순이익"]
    assert how["rule"] == C.IFRS_ELEMENT_ID and how["label"] == "분기순이익(손실)"
    # The legacy exact-label rule drops exactly this row.
    legacy, _ = DF.build_record(ticker="000001.KS", stock_code="000001", corp_code="1",
                                fiscal_year=2025, report_code="11013", rows=QUARTER_ROWS,
                                fs_div="CFS", collected_at="x")
    assert "당기순이익" not in legacy["accounts"]


@pytest.mark.parametrize("sj,name,aid,account", [
    ("CIS", "지배기업소유주지분순이익", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "당기순이익"),
    ("CIS", "분기순이익", "ifrs-full_ComprehensiveIncome", "당기순이익"),
    ("CF", "영업에서 창출된 현금", "ifrs-full_CashFlowsFromUsedInOperations", "영업활동현금흐름"),
    ("BS", "유동자산", "ifrs-full_CurrentAssets", "자산총계"),
    ("BS", "유동부채", "ifrs-full_CurrentLiabilities", "부채총계"),
])
def test_subtotals_and_attributable_profit_are_never_mapped(sj, name, aid, account):
    entry, how = C.resolve_account([row(sj, name, aid, 10, 10)], account)
    assert entry is None and how["rule"] is None


def test_net_income_is_never_taken_from_the_equity_statement():
    rows = [row("SCE", "당기순이익", "-표준계정코드 미사용-", 99),
            row("SCE", "분기순이익", "ifrs-full_ProfitLoss", 99)]
    entry, _ = C.resolve_account(rows, "당기순이익")
    assert entry is None


def test_cash_flow_profit_line_only_by_the_unchanged_exact_label_and_only_as_fallback():
    cf_label = row("CF", "당기순이익", "dart_ProfitLossForStatementOfCashFlows", 40)
    cf_element_only = row("CF", "분기순이익", "ifrs-full_ProfitLoss", 41)
    assert C.resolve_account([cf_element_only], "당기순이익")[0] is None
    entry, how = C.resolve_account([cf_label], "당기순이익")
    assert entry["statement"] == "CF" and how["rule"] == C.LEGACY_EXACT_LABEL
    income = row("IS", "분기순이익", "ifrs-full_ProfitLoss", 40, 40)
    entry, how = C.resolve_account([cf_label, income], "당기순이익")
    assert entry["statement"] == "IS"


def test_disagreeing_candidates_are_ambiguous_and_left_out():
    rows = [row("CIS", "분기순이익", "ifrs-full_ProfitLoss", 10, 10),
            row("CIS", "당기순이익", "ifrs-full_ProfitLoss", 11, 11)]
    entry, how = C.resolve_account(rows, "당기순이익")
    assert entry is None and how["rule"] == C.AMBIGUOUS
    record, _ = C.canonical_record(raw_record(rows + QUARTER_ROWS[:2]))
    assert "당기순이익" not in record["accounts"]
    assert record["canonicalization"]["accounts"]["당기순이익"]["rule"] == C.AMBIGUOUS


def test_component_rows_are_not_totals():
    entry, _ = C.resolve_account([row("BS", "자산총계", "ifrs-full_Assets", 5,
                                      detail="자본 [member]|이익잉여금")], "자산총계")
    assert entry is None


def test_legacy_label_matches_are_reproduced_exactly():
    rows = [row("BS", "자산 총계", "-표준계정코드 미사용-", 900),
            row("BS", "부채총계", "ifrs_Liabilities", 300),
            row("IS", "당기순이익(손실)", "ifrs_ProfitLoss", 12, 30),
            row("CF", "영업활동으로인한현금흐름", "ifrs_CashFlowsFromUsedInOperatingActivities", 44),
            row("IS", "영업이익", "dart_OperatingIncomeLoss", 20, 50)]
    legacy, _ = DF.build_record(ticker="000001.KS", stock_code="000001", corp_code="00000001",
                                fiscal_year=2025, report_code="11013", rows=rows, fs_div="CFS",
                                collected_at="2026-09-27T00:00:00Z")
    record, _ = C.canonical_record(raw_record(rows))
    assert record["accounts"] == legacy["accounts"]
    for key in ("id", "availableFrom", "receiptNos", "fsDiv", "fiscalYear", "reportCode", "source"):
        assert record[key] == legacy[key]


def test_canonical_records_are_read_unchanged_by_the_sealed_feature_path():
    prior_annual = raw_record([row("CIS", "당기순이익", "ifrs-full_ProfitLoss", 200, rcept="20250310000001"),
                               row("CF", "영업활동현금흐름",
                                   "ifrs-full_CashFlowsFromUsedInOperatingActivities", 260,
                                   rcept="20250310000001")], year=2024, code="11011")
    prior_q1 = raw_record([row("CIS", "분기순이익", "ifrs-full_ProfitLoss", 40, 40, rcept="20240514000001"),
                           row("CF", "영업활동현금흐름",
                               "ifrs-full_CashFlowsFromUsedInOperatingActivities", 55,
                               rcept="20240514000001")], year=2024, code="11013")
    current = raw_record(QUARTER_ROWS)
    records = [C.canonical_record(r)[0] for r in (prior_annual, prior_q1, current)]
    fields, provenance = AF.accounting_at(records, "2025-06-01", "KR")
    # TTM NI = 200 - 40 + 50 = 210; TTM OCF = 260 - 55 + 70 = 275.
    assert fields["ocfToNetIncomePct"] == pytest.approx(100.0 * 275 / 210)
    assert provenance["reportPeriod"] == "2025-11013"


# --------------------------------------------------------------------------- #
# Raw store: rows verbatim, receipt date from rcept_no only
# --------------------------------------------------------------------------- #
def test_raw_record_keeps_every_row_and_dates_from_the_receipt_number():
    rows = QUARTER_ROWS + [row("CIS", "기타포괄손익", "ifrs-full_OtherComprehensiveIncome", 1, 1)]
    record = raw_record(rows)
    assert record["rows"] == rows and record["availableFrom"] == "2025-05-15"
    assert record["mixedReceipts"] is False and record["contract"] == RS.CONTRACT


def test_raw_record_refuses_a_response_without_a_receipt_date():
    rows = [dict(r, rcept_no=None) for r in QUARTER_ROWS]
    record, reason = RS.build_raw_record(ticker="000001.KS", stock_code="000001", corp_code="1",
                                         fiscal_year=2025, report_code="11013", fs_div="CFS",
                                         rows=rows, attempts=[], collected_at="x")
    assert record is None and reason == "NO_RECEIPT_DATE"


def test_mixed_receipts_are_flagged_and_dated_by_the_earliest():
    rows = [row("BS", "자산총계", "ifrs-full_Assets", 1, rcept="20250601000001"),
            row("BS", "부채총계", "ifrs-full_Liabilities", 1, rcept="20250515000001")]
    record = raw_record(rows)
    assert record["mixedReceipts"] and record["availableFrom"] == "2025-05-15"


def test_work_list_follows_the_given_year_priority_and_skips_done_and_settled():
    done = {RS.record_id("A.KS", 2016, "11013")}
    absent = {RS.record_id("A.KS", 2016, "11012"): {
        "fiscalYear": 2016, "reportCode": "11012",
        "attempts": [{"fsDiv": "CFS", "status": "013"}, {"fsDiv": "OFS", "status": "013"}]}}
    pending = RS.work_list(["A.KS"], [2016, 2014, 2015], ["11013", "11012"], done,
                           RS.settled(absent, "2026-09-27"))
    assert pending == [("A.KS", 2015, "11013"), ("A.KS", 2015, "11012")]


# --------------------------------------------------------------------------- #
# Collector against a scripted DART
# --------------------------------------------------------------------------- #
DIRECTORY = [{"corpCode": "00000001", "corpName": "살아있는회사", "stockCode": "000001"},
             {"corpCode": "00000002", "corpName": "상장폐지회사", "stockCode": ""}]


def _universe(tmp_path):
    udir = tmp_path / "universe"
    HS.write_shard(udir / "krx-universe-2025.jsonl.gz", [
        {"id": "u1", "date": "2025-01-02", "ticker": "000001.KS", "name": "살아있는회사", "rank": 1},
        {"id": "u2", "date": "2025-01-02", "ticker": "000002.KS", "name": "상장폐지회사", "rank": 2},
    ])
    return COLLECT.pit_universe(udir)


def _scripted(monkeypatch, answers):
    calls = []

    def fake(path, params):
        calls.append((params["corp_code"], params["bsns_year"], params["reprt_code"], params["fs_div"]))
        return answers(params)
    monkeypatch.setattr(COLLECT, "call_json", fake)
    monkeypatch.setattr(COLLECT, "PACE_SECONDS", 0)
    return calls


def test_collector_records_real_statuses_resolves_delisted_issuers_and_keeps_rows(tmp_path, monkeypatch):
    def answers(p):
        if p["corp_code"] == "00000002" and p["fs_div"] == "OFS":
            return {"status": "000", "list": QUARTER_ROWS}
        if p["corp_code"] == "00000001" and p["reprt_code"] == "11011" and p["fs_div"] == "CFS":
            return {"status": "000", "list": QUARTER_ROWS}
        return {"status": "100" if p["corp_code"] == "00000001" else "013", "message": "m"}
    calls = _scripted(monkeypatch, answers)
    manifest = COLLECT.collect(tmp_path / "store", "k", _universe(tmp_path), [2025],
                               COLLECT.Budget(1000, 10), directory_fn=lambda _: DIRECTORY)
    assert manifest["resolvedIssuers"] == 2 and manifest["identityBasis"]["UNIQUE_NORMALIZED_NAME"] == 1
    stored = HS.read_jsonl(tmp_path / "store/raw-2025.jsonl.gz")
    delisted = [r for r in stored if r["ticker"] == "000002.KS"]
    assert len(delisted) == 4 and all(r["fsDiv"] == "OFS" for r in delisted)
    assert [a["status"] for a in delisted[0]["attempts"]] == ["013", "000"]
    assert delisted[0]["rows"] == QUARTER_ROWS
    # DART said 100 (invalid field), not 013: that is a request failure, not
    # evidence the filing does not exist. Kept with its statuses, never absent.
    absent = json.loads((tmp_path / "store/absent.json").read_text())
    unresolved = json.loads((tmp_path / "store/unresolved.json").read_text())
    q1 = RS.record_id("000001.KS", 2025, "11013")
    assert q1 not in absent and absent == {}
    assert [a["status"] for a in unresolved[q1]["attempts"]] == ["100", "100"]
    assert unresolved[q1]["evidence"] == RS.NOT_ESTABLISHED
    assert manifest["unresolvedFilings"] == 3 and not manifest["datasetComplete"]
    # Second run: stored filings are not fetched again; the 100s are retried.
    calls.clear()
    COLLECT.collect(tmp_path / "store", "k", _universe(tmp_path), [2025],
                    COLLECT.Budget(1000, 10), directory_fn=lambda _: DIRECTORY)
    assert sorted({(c[0], c[2]) for c in calls}) == [
        ("00000001", "11012"), ("00000001", "11013"), ("00000001", "11014")]


def _two_filers(tmp_path, monkeypatch, status, message="m"):
    """Every call answers `status`; returns (manifest, calls, store)."""
    calls = _scripted(monkeypatch, lambda p: {"status": status, "message": message})
    store = tmp_path / "store"
    manifest = COLLECT.collect(store, "k", _universe(tmp_path), [2025],
                               COLLECT.Budget(1000, 10), directory_fn=lambda _: DIRECTORY)
    return manifest, calls, store


def test_013_on_every_division_is_recorded_as_a_source_absence_and_settles(tmp_path, monkeypatch):
    manifest, calls, store = _two_filers(tmp_path, monkeypatch, "013", "조회된 데이타가 없습니다.")
    absent = json.loads((store / "absent.json").read_text())
    assert len(absent) == 8 and manifest["unresolvedFilings"] == 0
    row = absent[RS.record_id("000001.KS", 2025, "11013")]
    assert row["evidence"] == RS.SOURCE_ABSENCE
    assert [(a["fsDiv"], a["status"], a["message"]) for a in row["attempts"]] == [
        ("CFS", "013", "조회된 데이타가 없습니다."), ("OFS", "013", "조회된 데이타가 없습니다.")]
    # 2025 filings are past deadline + grace by 2026-09-27; a 2026 Q3 one is not.
    assert RS.settled(absent, "2026-09-27") == set(absent)
    assert RS.settled(absent, "2025-06-01") == set()
    calls.clear()
    COLLECT.collect(store, "k", _universe(tmp_path), [2025], COLLECT.Budget(1000, 10),
                    directory_fn=lambda _: DIRECTORY)
    assert calls == []


@pytest.mark.parametrize("status", ["100", "900", "014", "999", "None"])
def test_non_absence_statuses_are_never_settled_and_are_retried(tmp_path, monkeypatch, status):
    manifest, calls, store = _two_filers(tmp_path, monkeypatch, status)
    assert json.loads((store / "absent.json").read_text()) == {}
    unresolved = json.loads((store / "unresolved.json").read_text())
    assert len(unresolved) == 8 and manifest["unresolvedFilings"] == 8
    assert all([a["status"] for a in r["attempts"]] == [status, status] for r in unresolved.values())
    assert not manifest["datasetComplete"]
    calls.clear()
    COLLECT.collect(store, "k", _universe(tmp_path), [2025], COLLECT.Budget(1000, 10),
                    directory_fn=lambda _: DIRECTORY)
    assert len(calls) == 16  # every unresolved filing asked again, both divisions


@pytest.mark.parametrize("status", ["800", "021"])
def test_maintenance_and_company_limit_stop_the_run_without_settling(tmp_path, monkeypatch, status):
    manifest, calls, store = _two_filers(tmp_path, monkeypatch, status)
    assert len(calls) == 1 and manifest["thisRun"]["stopReason"].startswith("REFUSED:DART " + status)
    assert manifest["thisRun"]["outcome"] != "SERVED"
    assert json.loads((store / "absent.json").read_text()) == {}
    unresolved = json.loads((store / "unresolved.json").read_text())
    assert [a["status"] for r in unresolved.values() for a in r["attempts"]] == [status]


def test_mixed_013_and_a_request_error_is_not_absence():
    attempts = [{"fsDiv": "CFS", "status": "013"}, {"fsDiv": "OFS", "status": "100"}]
    assert RS.absence_evidence(attempts) == RS.NOT_ESTABLISHED
    assert RS.absence_evidence([{"fsDiv": "CFS", "status": "013"}]) == RS.NOT_ESTABLISHED
    assert RS.absence_evidence([{"fsDiv": "CFS", "status": "000"},
                                {"fsDiv": "OFS", "status": "000"}]) == RS.NOT_ESTABLISHED
    with pytest.raises(ValueError, match="ABSENCE_NOT_ESTABLISHED"):
        RS.absence_record(ticker="A.KS", fiscal_year=2016, report_code="11013",
                          attempts=attempts, checked_at="x")


def test_settled_rederives_evidence_and_ignores_a_stored_label():
    # A hand-edited or older row claiming absence with non-013 attempts never settles.
    forged = {"x": {"fiscalYear": 2016, "reportCode": "11013", "evidence": RS.SOURCE_ABSENCE,
                    "attempts": [{"fsDiv": "CFS", "status": "100"}, {"fsDiv": "OFS", "status": "100"}]},
              "legacy": {"fiscalYear": 2016, "reportCode": "11013", "status": "013"}}
    assert RS.settled(forged, "2026-09-27") == set()


def test_served_000_rows_are_stored_unchanged(tmp_path, monkeypatch):
    manifest, _, store = _two_filers(tmp_path, monkeypatch, "000")
    # 000 with no rows is not a filing and not an absence.
    assert json.loads((store / "absent.json").read_text()) == {}
    assert manifest["unresolvedFilings"] == 8
    calls = _scripted(monkeypatch, lambda p: {"status": "000", "list": QUARTER_ROWS})
    COLLECT.collect(store, "k", _universe(tmp_path), [2025], COLLECT.Budget(1000, 10),
                    directory_fn=lambda _: DIRECTORY)
    stored = HS.read_jsonl(store / "raw-2025.jsonl.gz")
    assert len(stored) == 8 and all(r["rows"] == QUARTER_ROWS and r["fsDiv"] == "CFS" for r in stored)
    assert json.loads((store / "unresolved.json").read_text()) == {}
    assert len(calls) == 8


def test_budget_is_checked_before_every_call_and_never_leaves_a_partial_filing(tmp_path, monkeypatch):
    calls = _scripted(monkeypatch, lambda p: {"status": "013"})
    manifest = COLLECT.collect(tmp_path / "store", "k", _universe(tmp_path), [2025],
                               COLLECT.Budget(3, 10), directory_fn=lambda _: DIRECTORY)
    assert len(calls) == 3 and manifest["thisRun"]["calls"] == 3
    assert manifest["thisRun"]["stopReason"] == "CALL_BUDGET_SPENT"
    absent = json.loads((tmp_path / "store/absent.json").read_text())
    # One filing finished both attempts; the second was cut after CFS and is not recorded.
    assert len(absent) == 1 and not manifest["datasetComplete"]


def test_a_fatal_key_status_stops_the_run_as_a_refusal(tmp_path, monkeypatch):
    _scripted(monkeypatch, lambda p: {"status": "010", "message": "등록되지 않은 키"})
    manifest = COLLECT.collect(tmp_path / "store", "k", _universe(tmp_path), [2025],
                               COLLECT.Budget(100, 10), directory_fn=lambda _: DIRECTORY)
    assert manifest["thisRun"]["stopReason"].startswith("REFUSED:")
    assert manifest["thisRun"]["outcome"] != "SERVED"


def test_pit_universe_is_every_ticker_ever_in_a_top_120_snapshot(tmp_path):
    udir = tmp_path / "u"
    udir.mkdir()
    rows = [{"id": f"{d}:{i}", "date": d, "ticker": f"{i:06d}.KS", "name": f"n{i}", "rank": i}
            for d, offset in (("2016-01-04", 0), ("2016-02-01", 5)) for i in range(1 + offset, 122 + offset)]
    HS.write_shard(udir / "krx-universe-2016.jsonl.gz", rows)
    universe = COLLECT.pit_universe(udir)
    assert len(universe) == 125 and "000126.KS" not in universe and "000121.KS" in universe


# --------------------------------------------------------------------------- #
# Audit: reason codes explain the sealed feature path, never disagree with it
# --------------------------------------------------------------------------- #
def _legacy(ticker, year, code, accounts, available):
    rows = []
    for name, (sj, amount, add) in accounts.items():
        rows.append(row(sj, name, "x", amount, add, rcept=available.replace("-", "") + "000001"))
    record, _ = DF.build_record(ticker=ticker, stock_code=ticker[:6], corp_code="1",
                                fiscal_year=year, report_code=code, rows=rows, fs_div="CFS",
                                collected_at="x")
    return record


def test_audit_names_the_2015_quarterly_gap_for_2016_growth():
    records = [_legacy("A.KS", 2016, "11013", {"자산총계": ("BS", 10, None), "부채총계": ("BS", 5, None)},
                       "2016-05-13")]
    absences = {("A.KS", 2015, "11013"): {"status": "013"}}
    out = A.diagnose_name_date("A.KS", records, [], "2016-06-03", absences)
    assert out["features"]["assetGrowthPct"]["blockers"] == [
        "자산총계:PRIOR_SAME_STAGE:" + A.PRIOR_2015_QUARTERLY_NOT_SERVED]


def test_audit_names_a_current_filing_that_lacks_net_income():
    records = [_legacy("A.KS", 2025, "11011", {"영업활동현금흐름": ("CF", 5, None),
                                               "매출액": ("IS", 9, None)}, "2026-03-10")]
    out = A.diagnose_name_date("A.KS", records, [], "2026-04-01", {})
    assert out["features"]["ocfToNetIncomePct"]["blockers"] == ["당기순이익:CURRENT:" + A.CURRENT_ACCOUNT_MISSING]


def test_audit_names_a_prior_served_only_as_a_later_amendment():
    records = [
        _legacy("A.KS", 2024, "11011", {"자산총계": ("BS", 10, None)}, "2025-11-20"),
        _legacy("A.KS", 2025, "11011", {"자산총계": ("BS", 12, None)}, "2026-03-10"),
    ]
    out = A.diagnose_name_date("A.KS", records, [], "2026-04-01", {})
    assert out["features"]["assetGrowthPct"]["available"]
    out = A.diagnose_name_date("A.KS", records[1:] + [
        _legacy("A.KS", 2024, "11011", {"자산총계": ("BS", 10, None)}, "2026-06-01")], [], "2026-04-01", {})
    assert out["features"]["assetGrowthPct"]["blockers"] == [
        "자산총계:PRIOR_SAME_STAGE:" + A.PRIOR_NOT_VISIBLE]


def test_uncollected_tickers_carry_calendar_blockers():
    out = A.diagnose_name_date("Z.KS", [], [], "2016-02-05", {})
    assert out["features"]["assetGrowthPct"]["blockers"] == [
        A.TICKER_NOT_IN_DART_COLLECTION, "CALENDAR:" + A.CALENDAR_2015_QUARTERLY,
        "CALENDAR:" + A.CALENDAR_BEFORE_DART_SERVICE]
    out = A.diagnose_name_date("Z.KS", [], [], "2025-06-05", {})
    assert out["features"]["ocfToNetIncomePct"]["blockers"] == [A.TICKER_NOT_IN_DART_COLLECTION]


def test_statutory_current_filing_uses_deadlines_strictly():
    assert A.statutory_current_filing("2016-03-31") == (2015, "11014")
    assert A.statutory_current_filing("2016-04-01") == (2015, "11011")
    assert A.statutory_current_filing("2016-05-16") == (2016, "11013")


def test_audit_raises_if_its_walk_ever_disagrees_with_the_feature_path(monkeypatch):
    monkeypatch.setattr(A.AF, "accounting_at", lambda *a, **k: ({"assetGrowthPct": 1.0}, {}))
    with pytest.raises(ValueError, match="AUDIT_DISAGREES_WITH_FEATURE_PATH"):
        A.diagnose_name_date("Z.KS", [], [], "2025-06-05", {})


def test_upper_bound_counts_only_rows_whose_every_reason_is_resolved():
    summary = {"2016": {"universeRows": 10, "features": {"assetGrowthPct": {
        "observed": 1, "rowsByReasonSet": {"A": 2, "A|B": 3, "C": 4}}}}}
    assert A.upper_bound_if_resolved(summary, ["A"])["2016"]["assetGrowthPct"] == pytest.approx(0.3)
    assert A.upper_bound_if_resolved(summary, ["A", "B"])["2016"]["assetGrowthPct"] == pytest.approx(0.6)


# --------------------------------------------------------------------------- #
# Boundaries: outcome-free, seals untouched, sealed store never written
# --------------------------------------------------------------------------- #
OUTCOME_NAMES = ("target_at", "target_from_sessions", "attach_labels", "net_label", "predict_cell",
                 "evaluate_cell", "fit_heads", "label_eligibility", "forwardRelativeReturn")


@pytest.mark.parametrize("path", [
    "pipeline/alpha_opportunity_kr_accounting_coverage_audit.py", "pipeline/dart_raw_statements.py",
    "pipeline/dart_canonical_accounts.py", "scripts/audit_kr_accounting_coverage.py",
    "scripts/collect_dart_raw_statements.py", "scripts/build_kr_canonical_filings.py"])
def test_repair_code_never_names_an_outcome_function(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert not [name for name in OUTCOME_NAMES if name in text]


SEALED = ("pipeline/dart_fundamentals.py", "pipeline/dart_derive.py", "pipeline/accounting_quality.py",
          "pipeline/alpha_opportunity_features.py", "pipeline/dart_ownership_universe.py",
          "research_specs/alpha-opportunity-model-v1.json", "research_specs/alpha-opportunity-model-v2.json",
          "research_specs/alpha-opportunity-model-v3.json", "research_specs/alpha-opportunity-model-v4.json")


def test_sealed_seals_still_load():
    from pipeline import alpha_opportunity_v2_spec as S2
    from pipeline import alpha_opportunity_v4_spec as S4
    S4.load_sealed(S4.DEFAULT_SPEC, expected_hash="4db0a96267a8b0de41c445ac600a8064a760191abdd29d97600153a78cbab8e6")
    S2.load_sealed(ROOT / "research_specs/alpha-opportunity-model-v2.json",
                   expected_hash="97c3727b37eeab71e31ffee17a2f81cac29f0333552ff04a5374ef48484b0e19")


def test_no_sealed_module_or_spec_differs_from_the_merge_base():
    base = subprocess.run(["git", "merge-base", "HEAD", "2c5b684949af82746dd2ba2ed810c255f4b84c2e"],
                          cwd=ROOT, capture_output=True, text=True)
    if base.returncode != 0:
        pytest.skip("merge commit not in this checkout's history")
    diff = subprocess.run(["git", "diff", "--name-only", base.stdout.strip(), "--", *SEALED],
                          cwd=ROOT, capture_output=True, text=True, check=True)
    assert diff.stdout.strip() == ""


def test_rebuild_refuses_to_write_into_the_sealed_store(tmp_path):
    target = tmp_path / "ledger/fundamentals/kr"
    with pytest.raises(ValueError, match="SEALED_LEGACY_STORE"):
        BUILD.main([str(tmp_path / "raw"), str(target)])


def test_rebuild_publishes_what_the_element_rule_admitted(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    HS.write_shard(RS.shard_path(raw_dir, 2025), [raw_record(QUARTER_ROWS)])
    report = BUILD.build(raw_dir, tmp_path / "out")
    assert report["records"] == 1
    assert report["admittedOnlyByElementId"]["당기순이익"] == [
        {"statement": "CIS", "label": "분기순이익(손실)", "accountId": "ifrs-full_ProfitLoss", "filings": 1}]
    rebuilt = HS.read_jsonl(DF.shard_path(tmp_path / "out", 2025))
    fields, _ = AQ.derive_kr_fields(DD.index_filings(rebuilt), 2025, "11013")
    assert "assetGrowthPct" not in fields  # no prior-year filing: coverage is not invented


def test_raw_collection_job_is_dispatch_only_and_never_writes_the_sealed_store():
    workflow = (ROOT / ".github/workflows/fundamentals.yml").read_text(encoding="utf-8")
    job = workflow.split("\n  kr-raw:\n", 1)[1]
    assert "if: github.event_name == 'workflow_dispatch' && startsWith(inputs.target, 'raw-')" in job
    assert "SEALED_SIGNAL_HISTORY_COMMIT: 4ea107ed0cde289f0a049a65ff13d2441a786710" in job
    assert "--universe-dir sealed-work/ledger/universe/kr" in job
    assert "for path in ledger/fundamentals/kr-raw ledger/fundamentals/kr-canonical-v2" in job
    assert "ledger/fundamentals/kr-xbrl-original ledger/fundamentals/kr-candidate-merged" in job
    assert 'if [ -e "$path" ]; then' in job and 'git add "$path"' in job
    assert "git add ledger/fundamentals\n" not in job and "git add ledger/fundamentals/kr\n" not in job
    assert "name: dart-fiscal-2015-probe" in job and "probe-2015.json" in job
    assert "raw-xbrl-2015" in job
    assert "collect_dart_xbrl_originals.py" in job and "merge_kr_candidate_snapshot.py" in job
    # Every step that tees a collector or audit keeps its exit status.
    for step in job.split("      - name: ")[1:]:
        if "| tee" in step:
            assert "set -o pipefail" in step, step.splitlines()[0]


def test_commit_step_never_crashes_when_one_candidate_path_is_missing(tmp_path):
    """Real defect, found by a real run (GitHub Actions 36313209561,
    `raw-xbrl-2015` alone, 2026-09-27): `raw-xbrl-2015` never creates
    kr-canonical-v2 (that is raw-statements' own rebuild step), and a bare
    `git add` on a path that does not exist at all is a hard git error, not a
    no-op -- it aborted the commit AFTER a real 525-record collection had
    already succeeded, discarding it. This test extracts the actual `git add`
    loop from the workflow file and runs it for real in a repo missing one of
    the four candidate paths, proving it no longer raises."""
    workflow = (ROOT / ".github/workflows/fundamentals.yml").read_text(encoding="utf-8")
    job = workflow.split("\n  kr-raw:\n", 1)[1]
    step = job.split("- name: Commit & push to signal-history\n", 1)[1].split("\n      - name:", 1)[0]
    loop = step.split("run: |\n", 1)[1]
    repo = tmp_path / "raw-work"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "ledger/fundamentals/kr-raw").mkdir(parents=True)
    (repo / "ledger/fundamentals/kr-raw/absent.json").write_text("{}")
    (repo / "ledger/fundamentals/kr-xbrl-original").mkdir(parents=True)
    (repo / "ledger/fundamentals/kr-xbrl-original/x.jsonl").write_text("{}")
    # kr-canonical-v2 and kr-candidate-merged deliberately absent, exactly the
    # real run's state after `raw-xbrl-2015` alone.
    add_only = loop.split('if git diff --cached --quiet', 1)[0]
    add_script = "\n".join(line[10:] if line.startswith(" " * 10) else line for line in add_only.splitlines())
    result = subprocess.run(["bash", "-c", add_script], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=repo,
                            capture_output=True, text=True, check=True).stdout
    assert "kr-raw/absent.json" in staged and "kr-xbrl-original/x.jsonl" in staged


# --------------------------------------------------------------------------- #
# Original-XBRL discovery/classification, pinned to the LIVE probe evidence
# (GitHub Actions run 36300578100, 2026-09-27, artifact dart-fiscal-2015-probe,
# sha256 af7e3b58086b1004af59bdbf978d4e19e9a150fd212d51a639f3512a9a885c2e).
# --------------------------------------------------------------------------- #
from pipeline import dart_xbrl_originals as XO
from pipeline import dart_xbrl_statements as XS
from scripts import collect_dart_xbrl_originals as XCOLLECT
from scripts import merge_kr_candidate_snapshot as MERGE

REAL_014_BODY = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<result><status>014</status><message>파일이 존재하지 않습니다.</message></result>'
                 ).encode("utf-8")
# 000030.KS's real periodicReports, exactly as the live probe recorded them.
REAL_PERIODIC_000030 = [
    {"rceptNo": "20160516002505", "rceptDt": "20160516", "reportNm": "분기보고서 (2016.03)"},
    {"rceptNo": "20160330004090", "rceptDt": "20160330", "reportNm": "사업보고서 (2015.12)"},
    {"rceptNo": "20151116001418", "rceptDt": "20151116", "reportNm": "분기보고서 (2015.09)"},
    {"rceptNo": "20150817001343", "rceptDt": "20150817", "reportNm": "반기보고서 (2015.06)"},
    {"rceptNo": "20150529001078", "rceptDt": "20150529", "reportNm": "[기재정정]분기보고서 (2015.03)"},
    {"rceptNo": "20150529001060", "rceptDt": "20150529", "reportNm": "[기재정정]사업보고서 (2014.12)"},
    {"rceptNo": "20150515002248", "rceptDt": "20150515", "reportNm": "분기보고서 (2015.03)"},
    {"rceptNo": "20150331004293", "rceptDt": "20150331", "reportNm": "사업보고서 (2014.12)"},
]


def test_real_014_error_envelope_is_parsed_and_classified():
    assert XO.parse_error_envelope(REAL_014_BODY) == {
        "status": "014", "message": "파일이 존재하지 않습니다."}
    classification, envelope = XO.classify_xbrl_response(REAL_014_BODY)
    assert classification == XO.FILE_NOT_AVAILABLE_014 and envelope["status"] == "014"


def test_real_zip_signature_is_classified_served():
    classification, envelope = XO.classify_xbrl_response(b"PK\x03\x04rest-of-a-real-zip")
    assert classification == XO.XBRL_ZIP_SERVED and envelope is None


def test_select_original_filing_reproduces_the_real_000030_case():
    row, selection = XO.select_original_filing(REAL_PERIODIC_000030, "11014")
    assert selection == XO.ORIGINAL_LISTED and row["rceptNo"] == "20151116001418"
    row, selection = XO.select_original_filing(REAL_PERIODIC_000030, "11012")
    assert selection == XO.ORIGINAL_LISTED and row["rceptNo"] == "20150817001343"
    # Q1 has BOTH an original and its amendment listed; the amendment is
    # never picked, even though it is the later, "more current" receipt.
    row, selection = XO.select_original_filing(REAL_PERIODIC_000030, "11013")
    assert selection == XO.ORIGINAL_LISTED and row["rceptNo"] == "20150515002248"


def test_a_stage_with_only_an_amended_filing_is_its_own_state():
    only_amended = [{"rceptNo": "1", "rceptDt": "20150529", "reportNm": "[기재정정]분기보고서 (2015.03)"}]
    row, selection = XO.select_original_filing(only_amended, "11013")
    assert row is None and selection == XO.ORIGINAL_NOT_LISTED_ONLY_AMENDMENT


def test_no_matching_stage_is_no_original_filing_index():
    row, selection = XO.select_original_filing([], "11013")
    assert row is None and selection == XO.NO_ORIGINAL_FILING_INDEX


def test_two_disagreeing_originals_for_one_stage_are_ambiguous():
    dup = [{"rceptNo": "1", "rceptDt": "20150515", "reportNm": "분기보고서 (2015.03)"},
           {"rceptNo": "2", "rceptDt": "20150516", "reportNm": "분기보고서 (2015.03)"}]
    row, selection = XO.select_original_filing(dup, "11013")
    assert row is None and selection == XO.AMBIGUOUS_REPORT_MATCH


# --------------------------------------------------------------------------- #
# XBRL parsing: exact local name, cumulative-window-only, never synthesised
# --------------------------------------------------------------------------- #
def _instance_zip(facts_and_contexts: str) -> bytes:
    import io
    import zipfile
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<xbrl xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2015-03-11/ifrs-full" '
           'xmlns:ifrs="http://xbrl.ifrs.org/taxonomy/2015-03-11/ifrs" '
           'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
           'xmlns:dart-gcd="http://dart.fss.or.kr/taxonomy/2013-03-31/ifrs/dart-gcd" '
           'xmlns:xbrli="http://www.xbrl.org/2003/instance">' + facts_and_contexts + '</xbrl>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("instance.xbrl", xml)
    return buf.getvalue()


STANDARD_CONTEXTS = (
    '<xbrli:context id="I"><xbrli:period><xbrli:instant>2015-09-30</xbrli:instant></xbrli:period></xbrli:context>'
    '<xbrli:context id="YTD"><xbrli:period><xbrli:startDate>2015-01-01</xbrli:startDate>'
    '<xbrli:endDate>2015-09-30</xbrli:endDate></xbrli:period></xbrli:context>'
    '<xbrli:context id="Qonly"><xbrli:period><xbrli:startDate>2015-07-01</xbrli:startDate>'
    '<xbrli:endDate>2015-09-30</xbrli:endDate></xbrli:period></xbrli:context>'
)


def test_target_local_names_derived_from_the_shared_element_rules():
    assert XS.TARGET_LOCAL_NAMES["당기순이익"] == frozenset({"ProfitLoss"})
    assert XS.TARGET_LOCAL_NAMES["영업활동현금흐름"] == frozenset(
        {"CashFlowsFromUsedInOperatingActivities"})
    assert "ProfitLossAttributableToOwnersOfParent" not in XS.ALL_TARGET_LOCAL_NAMES


def test_resolve_account_prefers_the_cumulative_window_over_a_standalone_quarter():
    zip_bytes = _instance_zip(
        STANDARD_CONTEXTS +
        '<ifrs-full:ProfitLoss contextRef="YTD" unitRef="KRW">50000</ifrs-full:ProfitLoss>'
        '<ifrs-full:ProfitLoss contextRef="Qonly" unitRef="KRW">15000</ifrs-full:ProfitLoss>')
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "당기순이익", fiscal_year_start="2015-01-01",
                                    period_end="2015-09-30")
    assert value == "50000" and how["status"] == XS.RESOLVED


def test_resolve_account_is_ambiguous_when_two_cumulative_facts_disagree():
    zip_bytes = _instance_zip(
        STANDARD_CONTEXTS +
        '<ifrs-full:ProfitLoss contextRef="YTD" unitRef="KRW">50000</ifrs-full:ProfitLoss>'
        '<ifrs:ProfitLoss contextRef="YTD" unitRef="KRW">51000</ifrs:ProfitLoss>')
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "당기순이익", fiscal_year_start="2015-01-01",
                                    period_end="2015-09-30")
    assert value is None and how["status"] == XS.AMBIGUOUS


def test_resolve_account_not_found_when_no_context_matches():
    zip_bytes = _instance_zip(STANDARD_CONTEXTS)
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "자산총계", fiscal_year_start="2015-01-01",
                                    period_end="2015-09-30")
    assert value is None and how["status"] == XS.NOT_FOUND


def test_attributable_to_parent_profit_is_never_matched_to_net_income():
    zip_bytes = _instance_zip(
        STANDARD_CONTEXTS +
        '<ifrs-full:ProfitLossAttributableToOwnersOfParent contextRef="YTD" unitRef="KRW">'
        '99999</ifrs-full:ProfitLossAttributableToOwnersOfParent>')
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "당기순이익", fiscal_year_start="2015-01-01",
                                    period_end="2015-09-30")
    assert value is None and how["status"] == XS.NOT_FOUND


def test_current_assets_is_never_matched_to_total_assets():
    zip_bytes = _instance_zip(
        STANDARD_CONTEXTS +
        '<ifrs-full:CurrentAssets contextRef="I" unitRef="KRW">1</ifrs-full:CurrentAssets>')
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "자산총계", fiscal_year_start="2015-01-01",
                                    period_end="2015-09-30")
    assert value is None and how["status"] == XS.NOT_FOUND


def test_unparseable_zip_entry_leaves_every_account_unavailable():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("instance.xbrl", b"not xml at all {{{")
    entries, _ = XS.unzip_entries(buf.getvalue())
    value, how = XS.resolve_account(entries, "자산총계", fiscal_year_start="2015-01-01",
                                    period_end="2015-09-30")
    assert value is None and how["status"] == XS.NO_PARSEABLE_XML_ENTRY


def test_a_bad_zip_is_reported_not_silently_empty():
    entries, error = XS.unzip_entries(b"not a zip")
    assert entries == [] and error


# --------------------------------------------------------------------------- #
# Dimensional-qualifier exclusion, pinned to REAL context definitions served
# by GitHub Actions run 36304452901 (`raw-probe-2015`, `--dump-entries`),
# copied byte-for-byte from that run's own `entryTextSnippets`. The 15 of 18
# served fiscal-2015 filings that read AMBIGUOUS under the first cut of this
# module all shared this shape: multiple contexts carrying the exact same
# literal dates, distinguished only by a `<scenario>` dimensional qualifier
# the context-window filter alone could not see. The FACT elements below are
# synthetic (the real snippet truncated before reaching any fact) -- added
# only to exercise `resolve_account` end to end against the real context
# shapes; the CONTEXT XML itself is exactly what DART served.
# --------------------------------------------------------------------------- #
REAL_000080_PERIODAXIS_CONTEXTS = (
    '<xbrli:context id="CFY2015dFQA_dart-gcd_PeriodAxis_dart-gcd_PeriodCoveredbyTheYearBeforeLastFiscalYearMember">'
    '<xbrli:entity><xbrli:identifier scheme="http://dart.fss.or.kr/ifrs/CIK">00150244</xbrli:identifier></xbrli:entity>'
    '<xbrli:period><xbrli:startDate>2015-01-01</xbrli:startDate><xbrli:endDate>2015-03-31</xbrli:endDate></xbrli:period>'
    '<xbrli:scenario><xbrldi:explicitMember dimension="dart-gcd:PeriodAxis">'
    'dart-gcd:PeriodCoveredbyTheYearBeforeLastFiscalYearMember</xbrldi:explicitMember></xbrli:scenario>'
    '</xbrli:context>'
    '<xbrli:context id="CFY2015dFQA_dart-gcd_PeriodAxis_dart-gcd_PeriodCoveredbyLastFiscalYearMember">'
    '<xbrli:entity><xbrli:identifier scheme="http://dart.fss.or.kr/ifrs/CIK">00150244</xbrli:identifier></xbrli:entity>'
    '<xbrli:period><xbrli:startDate>2015-01-01</xbrli:startDate><xbrli:endDate>2015-03-31</xbrli:endDate></xbrli:period>'
    '<xbrli:scenario><xbrldi:explicitMember dimension="dart-gcd:PeriodAxis">'
    'dart-gcd:PeriodCoveredbyLastFiscalYearMember</xbrldi:explicitMember></xbrli:scenario>'
    '</xbrli:context>'
)
# Real, from 000240.KS / 000100.KS: `ConsolidatedAndSeparateFinancialStatementsAxis`
# alone is the ONE qualifier this module admits.
REAL_SEPARATE_ONLY_CONTEXT = (
    '<xbrli:context id="PFY2014dFQ_ifrs_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs_SeparateMember">'
    '<xbrli:entity><xbrli:identifier scheme="http://dart.fss.or.kr/ifrs/CIK">00160047</xbrli:identifier></xbrli:entity>'
    '<xbrli:period><xbrli:startDate>2015-01-01</xbrli:startDate><xbrli:endDate>2015-03-31</xbrli:endDate></xbrli:period>'
    '<xbrli:scenario><xbrldi:explicitMember dimension="ifrs:ConsolidatedAndSeparateFinancialStatementsAxis">'
    'ifrs:SeparateMember</xbrldi:explicitMember></xbrli:scenario>'
    '</xbrli:context>'
)
# Real, from 000100.KS: TWO axes on the SAME context at once (Consolidated +
# an SCE component) -- confirms exclusion must check the axis SET, not just
# whether ComponentsOfEquityAxis is present alone.
REAL_CONSOLIDATED_PLUS_SCE_COMPONENT_CONTEXT = (
    '<xbrli:context id="CFY2015eFQA_ifrs_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs_ConsolidatedMember_'
    'ifrs_ComponentsOfEquityAxis_ifrs_EquityAttributableToOwnersOfParentMember">'
    '<xbrli:entity><xbrli:identifier scheme="http://dart.fss.or.kr/ifrs/CIK">00145109</xbrli:identifier></xbrli:entity>'
    '<xbrli:period><xbrli:startDate>2015-01-01</xbrli:startDate><xbrli:endDate>2015-03-31</xbrli:endDate></xbrli:period>'
    '<xbrli:scenario>'
    '<xbrldi:explicitMember dimension="ifrs:ConsolidatedAndSeparateFinancialStatementsAxis">'
    'ifrs:ConsolidatedMember</xbrldi:explicitMember>'
    '<xbrldi:explicitMember dimension="ifrs:ComponentsOfEquityAxis">'
    'ifrs:EquityAttributableToOwnersOfParentMember</xbrldi:explicitMember>'
    '</xbrli:scenario>'
    '</xbrli:context>'
)


def test_real_periodaxis_contexts_are_excluded_and_never_cause_ambiguity():
    """The exact 000080.KS shape: two PeriodAxis-tagged comparative contexts
    plus one unqualified current context, all sharing the window. Before this
    fix all three were candidates and disagreement made 당기순이익 AMBIGUOUS;
    now the two PeriodAxis ones are excluded and the unqualified one wins."""
    zip_bytes = _instance_zip(
        REAL_000080_PERIODAXIS_CONTEXTS +
        '<xbrli:context id="CurrentUnqualified"><xbrli:period><xbrli:startDate>2015-01-01</xbrli:startDate>'
        '<xbrli:endDate>2015-03-31</xbrli:endDate></xbrli:period></xbrli:context>'
        '<ifrs:ProfitLoss contextRef="CFY2015dFQA_dart-gcd_PeriodAxis_dart-gcd_PeriodCoveredbyTheYearBeforeLastFiscalYearMember" '
        'unitRef="KRW">11111</ifrs:ProfitLoss>'
        '<ifrs:ProfitLoss contextRef="CFY2015dFQA_dart-gcd_PeriodAxis_dart-gcd_PeriodCoveredbyLastFiscalYearMember" '
        'unitRef="KRW">22222</ifrs:ProfitLoss>'
        '<ifrs:ProfitLoss contextRef="CurrentUnqualified" unitRef="KRW">99999</ifrs:ProfitLoss>')
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "당기순이익", fiscal_year_start="2015-01-01",
                                    period_end="2015-03-31")
    assert value == "99999" and how["status"] == XS.RESOLVED
    assert how["candidates"] == 3 and how["eligibleCandidates"] == 1
    assert how["statementBasis"] is None


def test_periodaxis_only_candidates_are_axis_excluded_not_not_found():
    """No unqualified context at all -- only the two real PeriodAxis
    comparative contexts. This must read AXIS_EXCLUDED_ONLY, a different fact
    from NOT_FOUND (the element was never stated at all)."""
    zip_bytes = _instance_zip(
        REAL_000080_PERIODAXIS_CONTEXTS +
        '<ifrs:ProfitLoss contextRef="CFY2015dFQA_dart-gcd_PeriodAxis_dart-gcd_PeriodCoveredbyTheYearBeforeLastFiscalYearMember" '
        'unitRef="KRW">11111</ifrs:ProfitLoss>'
        '<ifrs:ProfitLoss contextRef="CFY2015dFQA_dart-gcd_PeriodAxis_dart-gcd_PeriodCoveredbyLastFiscalYearMember" '
        'unitRef="KRW">22222</ifrs:ProfitLoss>')
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "당기순이익", fiscal_year_start="2015-01-01",
                                    period_end="2015-03-31")
    assert value is None and how["status"] == XS.AXIS_EXCLUDED_ONLY
    assert how["candidates"] == 2 and how["eligibleCandidates"] == 0


def test_real_separate_only_context_is_eligible_and_recorded():
    """The exact 000240.KS/000100.KS shape: SeparateMember alone, no other
    axis, no unqualified rival -- this repository's own already-established
    Consolidated-preferred rule applies and the basis is recorded."""
    zip_bytes = _instance_zip(
        REAL_SEPARATE_ONLY_CONTEXT +
        '<ifrs:ProfitLoss contextRef="PFY2014dFQ_ifrs_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs_SeparateMember" '
        'unitRef="KRW">55555</ifrs:ProfitLoss>')
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "당기순이익", fiscal_year_start="2015-01-01",
                                    period_end="2015-03-31")
    assert value == "55555" and how["status"] == XS.RESOLVED
    assert how["statementBasis"] == DF.FS_SEPARATE


def test_consolidated_preferred_over_separate_when_both_present_and_no_unqualified():
    zip_bytes = _instance_zip(
        REAL_SEPARATE_ONLY_CONTEXT +
        '<xbrli:context id="ConsolidatedOnly">'
        '<xbrli:period><xbrli:startDate>2015-01-01</xbrli:startDate><xbrli:endDate>2015-03-31</xbrli:endDate></xbrli:period>'
        '<xbrli:scenario><xbrldi:explicitMember dimension="ifrs:ConsolidatedAndSeparateFinancialStatementsAxis">'
        'ifrs:ConsolidatedMember</xbrldi:explicitMember></xbrli:scenario></xbrli:context>'
        '<ifrs:ProfitLoss contextRef="PFY2014dFQ_ifrs_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs_SeparateMember" '
        'unitRef="KRW">55555</ifrs:ProfitLoss>'
        '<ifrs:ProfitLoss contextRef="ConsolidatedOnly" unitRef="KRW">77777</ifrs:ProfitLoss>')
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "당기순이익", fiscal_year_start="2015-01-01",
                                    period_end="2015-03-31")
    assert value == "77777" and how["status"] == XS.RESOLVED
    assert how["statementBasis"] == DF.FS_CONSOLIDATED


def test_real_consolidated_plus_sce_component_context_is_excluded():
    """The exact 000100.KS shape: a context tagged with BOTH the admitted
    Consolidated axis AND an SCE component axis at once -- confirms exclusion
    checks the axis SET, and reuses this repository's existing SCE-component
    refusal (dart_canonical_accounts) rather than deciding it a second way."""
    zip_bytes = _instance_zip(
        REAL_CONSOLIDATED_PLUS_SCE_COMPONENT_CONTEXT +
        '<ifrs:ProfitLoss contextRef="CFY2015eFQA_ifrs_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs_ConsolidatedMember_'
        'ifrs_ComponentsOfEquityAxis_ifrs_EquityAttributableToOwnersOfParentMember" unitRef="KRW">33333'
        '</ifrs:ProfitLoss>')
    entries, _ = XS.unzip_entries(zip_bytes)
    value, how = XS.resolve_account(entries, "당기순이익", fiscal_year_start="2015-01-01",
                                    period_end="2015-03-31")
    assert value is None and how["status"] == XS.AXIS_EXCLUDED_ONLY


def test_describe_candidates_reports_eligibility_per_candidate():
    zip_bytes = _instance_zip(
        REAL_000080_PERIODAXIS_CONTEXTS +
        '<xbrli:context id="CurrentUnqualified"><xbrli:period><xbrli:startDate>2015-01-01</xbrli:startDate>'
        '<xbrli:endDate>2015-03-31</xbrli:endDate></xbrli:period></xbrli:context>'
        '<ifrs:ProfitLoss contextRef="CFY2015dFQA_dart-gcd_PeriodAxis_dart-gcd_PeriodCoveredbyTheYearBeforeLastFiscalYearMember" '
        'unitRef="KRW">11111</ifrs:ProfitLoss>'
        '<ifrs:ProfitLoss contextRef="CurrentUnqualified" unitRef="KRW">99999</ifrs:ProfitLoss>')
    entries, _ = XS.unzip_entries(zip_bytes)
    detail = XS.describe_candidates(entries, "당기순이익", fiscal_year_start="2015-01-01",
                                    period_end="2015-03-31")
    by_context = {d["contextRef"]: d for d in detail}
    assert by_context["CurrentUnqualified"]["eligibleAxisShape"] is True
    assert by_context["CurrentUnqualified"]["dims"] == []
    excluded_id = "CFY2015dFQA_dart-gcd_PeriodAxis_dart-gcd_PeriodCoveredbyTheYearBeforeLastFiscalYearMember"
    assert by_context[excluded_id]["eligibleAxisShape"] is False
    assert by_context[excluded_id]["dims"] == [("PeriodAxis", "PeriodCoveredbyTheYearBeforeLastFiscalYearMember")]


FULL_XBRL_ZIP = _instance_zip(
    STANDARD_CONTEXTS +
    '<ifrs-full:Assets contextRef="I" unitRef="KRW">1000000</ifrs-full:Assets>'
    '<ifrs-full:Liabilities contextRef="I" unitRef="KRW">400000</ifrs-full:Liabilities>'
    '<ifrs-full:ProfitLoss contextRef="YTD" unitRef="KRW">50000</ifrs-full:ProfitLoss>'
    '<ifrs-full:CashFlowsFromUsedInOperatingActivities contextRef="YTD" unitRef="KRW">'
    '70000</ifrs-full:CashFlowsFromUsedInOperatingActivities>')


def test_canonical_record_from_xbrl_carries_candidate_unconfirmed_and_original_receipt():
    entries, _ = XS.unzip_entries(FULL_XBRL_ZIP)
    record, provenance = XS.canonical_record_from_xbrl(
        ticker="000080.KS", stock_code="000080", corp_code="00126380", fiscal_year=2015,
        report_code="11014", entries=entries, original_receipt_no="20151113000033",
        original_receipt_date="2015-11-13", zip_sha256="deadbeef", collected_at="x")
    assert record["id"] == "000080.KS:2015:11014"
    assert record["availableFrom"] == "2015-11-13" and record["receiptNos"] == ["20151113000033"]
    assert record["canonicalization"]["endpointConfidence"] == "CANDIDATE_UNCONFIRMED"
    assert all(v["status"] == XS.RESOLVED for v in provenance.values())


def test_xbrl_record_actually_serves_as_the_missing_prior_same_filing_for_2016_ttm():
    """The whole point: a 2016 Q3 net-income/OCF roll-forward needs a fiscal-2015
    Q3 prior filing on the SAME report code. Prove the XBRL-derived record
    supplies it, read by the unmodified sealed `dart_derive`."""
    entries, _ = XS.unzip_entries(FULL_XBRL_ZIP)
    record_2015, _ = XS.canonical_record_from_xbrl(
        ticker="000080.KS", stock_code="000080", corp_code="00126380", fiscal_year=2015,
        report_code="11014", entries=entries, original_receipt_no="20151113000033",
        original_receipt_date="2015-11-13", zip_sha256="x", collected_at="x")
    # trailing_twelve_months(2016, Q3) needs (2015, ANNUAL) and (2015, Q3) --
    # the latter is exactly the filing `record_2015` (from XBRL) supplies.
    prior_annual_2015 = _legacy("000080.KS", 2015, "11011", {"당기순이익": ("CIS", 100000, None),
                                                             "영업활동현금흐름": ("CF", 150000, None)},
                                "2016-03-20")
    current = _legacy("000080.KS", 2016, "11014", {"당기순이익": ("CIS", 20000, 60000),
                                                    "영업활동현금흐름": ("CF", 90000, None)},
                      "2016-11-13")
    by_key = DD.index_filings([prior_annual_2015, record_2015, current])
    ni, ni_basis = DD.trailing_twelve_months(by_key, 2016, "11014", "당기순이익")
    ocf, ocf_basis = DD.trailing_twelve_months(by_key, 2016, "11014", "영업활동현금흐름")
    # TTM = FY2015(100000) - cum2015Q3(50000, from record_2015) + cum2016Q3(60000)
    assert ni == pytest.approx(100000 - 50000 + 60000) and ni_basis == DD.BASIS_ROLLFORWARD
    # TTM = FY2015(150000) - cum2015Q3(70000, from record_2015) + cum2016Q3(90000)
    assert ocf == pytest.approx(150000 - 70000 + 90000) and ocf_basis == DD.BASIS_ROLLFORWARD


# --------------------------------------------------------------------------- #
# The real collector: append-only, budget-checked, every classification kept
# --------------------------------------------------------------------------- #
def _scripted_list_and_xbrl(monkeypatch, list_answer, xbrl_answer):
    calls = {"list": 0, "xbrl": 0}

    def fake_call_json(path, params):
        if path == "list.json":
            calls["list"] += 1
            return list_answer(params)
        raise AssertionError(path)
    def fake_http(path, params, timeout=40):
        if path == "fnlttXbrl.xml":
            calls["xbrl"] += 1
            return xbrl_answer(params)
        raise AssertionError(path)
    monkeypatch.setattr(COLLECT, "call_json", fake_call_json)
    monkeypatch.setattr(COLLECT, "http", fake_http)
    monkeypatch.setattr(COLLECT, "PACE_SECONDS", 0)
    return calls


ONE_TICKER_UNIVERSE_DIRECTORY = [{"corpCode": "00126380", "corpName": "회사", "stockCode": "000080"}]


def _one_ticker_universe(tmp_path):
    udir = tmp_path / "u"
    HS.write_shard(udir / "krx-universe-2025.jsonl.gz", [
        {"id": "u1", "date": "2025-01-02", "ticker": "000080.KS", "name": "회사", "rank": 1}])
    return COLLECT.pit_universe(udir)


def test_xbrl_collector_stores_served_zips_and_every_other_classification(tmp_path, monkeypatch):
    def list_answer(p):
        return {"status": "000", "list": [
            {"rcept_no": "Q3ORIG", "rcept_dt": "20151113", "report_nm": "분기보고서 (2015.09)"},
            {"rcept_no": "H1ORIG", "rcept_dt": "20150817", "report_nm": "반기보고서 (2015.06)"},
            {"rcept_no": "Q1AMEND", "rcept_dt": "20150515", "report_nm": "[기재정정]분기보고서 (2015.03)"}],
                "page_no": 1, "page_count": 100, "total_count": 3, "total_page": 1}
    def xbrl_answer(p):
        if p["reprt_code"] == "11014":
            return FULL_XBRL_ZIP
        return REAL_014_BODY
    calls = _scripted_list_and_xbrl(monkeypatch, list_answer, xbrl_answer)
    manifest = XCOLLECT.collect(tmp_path / "store", "k", _one_ticker_universe(tmp_path),
                               COLLECT.Budget(1000, 10), directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    assert manifest["classifications"] == {
        XO.XBRL_ZIP_SERVED: 1, XO.FILE_NOT_AVAILABLE_014: 1,
        XO.ORIGINAL_NOT_LISTED_ONLY_AMENDMENT: 1}
    assert manifest["recordsStored"] == 1 and manifest["datasetComplete"]
    stored = HS.read_jsonl(tmp_path / "store/dart-xbrl-2015.jsonl.gz")
    assert len(stored) == 1 and stored[0]["id"] == "000080.KS:2015:11014"
    assert stored[0]["canonicalization"]["endpointConfidence"] == "CANDIDATE_UNCONFIRMED"
    # Second run: every stage already checked, nothing re-fetched.
    calls["list"] = calls["xbrl"] = 0
    XCOLLECT.collect(tmp_path / "store", "k", _one_ticker_universe(tmp_path), COLLECT.Budget(1000, 10),
                     directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    assert calls == {"list": 0, "xbrl": 0}


def test_xbrl_collector_never_selects_an_amendment_as_original(tmp_path, monkeypatch):
    def list_answer(p):
        return {"status": "000", "list": [
            {"rcept_no": "ORIGINAL", "rcept_dt": "20150515", "report_nm": "분기보고서 (2015.03)"},
            {"rcept_no": "AMENDMENT", "rcept_dt": "20150529", "report_nm": "[기재정정]분기보고서 (2015.03)"}],
                "page_no": 1, "page_count": 100, "total_count": 2, "total_page": 1}
    seen_receipts = []
    def xbrl_answer(p):
        seen_receipts.append(p["rcept_no"])
        return REAL_014_BODY
    _scripted_list_and_xbrl(monkeypatch, list_answer, xbrl_answer)
    XCOLLECT.collect(tmp_path / "store", "k", _one_ticker_universe(tmp_path), COLLECT.Budget(1000, 10),
                     directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    # Only Q1 has any filing on record (H1/Q3 have none) -- one fetch, the
    # ORIGINAL receipt, never the amendment.
    assert seen_receipts == ["ORIGINAL"]


def test_xbrl_collector_call_budget_leaves_a_stage_unresolved_not_settled(tmp_path, monkeypatch):
    def list_answer(p):
        return {"status": "000", "list": [], "page_no": 1, "page_count": 100,
                "total_count": 0, "total_page": 0}
    _scripted_list_and_xbrl(monkeypatch, list_answer, lambda p: REAL_014_BODY)
    manifest = XCOLLECT.collect(tmp_path / "store", "k", _one_ticker_universe(tmp_path),
                               COLLECT.Budget(1, 10), directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    assert manifest["thisRun"]["stopReason"] == "CALL_BUDGET_SPENT"
    assert not manifest["datasetComplete"] and manifest["checked"] < 3


def test_xbrl_collector_dump_dir_writes_the_raw_zip_and_never_commits_it(tmp_path, monkeypatch):
    def list_answer(p):
        return {"status": "000", "list": [
            {"rcept_no": "R", "rcept_dt": "20151113", "report_nm": "분기보고서 (2015.09)"}],
                "page_no": 1, "page_count": 100, "total_count": 1, "total_page": 1}
    _scripted_list_and_xbrl(monkeypatch, list_answer, lambda p: FULL_XBRL_ZIP)
    dump = tmp_path / "dump"
    XCOLLECT.collect(tmp_path / "store", "k", _one_ticker_universe(tmp_path), COLLECT.Budget(1000, 10),
                     directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY, dump_dir=dump)
    written = list(dump.glob("*.zip"))
    assert len(written) == 1 and written[0].read_bytes() == FULL_XBRL_ZIP


# --------------------------------------------------------------------------- #
# Retryable vs. terminal fetch-state classifications. A request/network
# failure (LIST_JSON_ERROR, XO.REQUEST_ERROR) is never evidence the filing
# doesn't exist, so it must never settle a (ticker, stage) the way a genuine
# `list.json`/`fnlttXbrl.xml` answer does.
# --------------------------------------------------------------------------- #
def test_needs_fetch_treats_only_request_layer_errors_as_retryable():
    assert XCOLLECT._needs_fetch("r", {}) is True
    for terminal in (XO.XBRL_ZIP_SERVED, XO.FILE_NOT_AVAILABLE_014, XO.NO_ORIGINAL_FILING_INDEX,
                    XO.ORIGINAL_NOT_LISTED_ONLY_AMENDMENT, XO.AMBIGUOUS_REPORT_MATCH):
        assert XCOLLECT._needs_fetch("r", {"r": {"classification": terminal}}) is False
    for retryable in (XCOLLECT.LIST_JSON_ERROR, XO.REQUEST_ERROR):
        assert XCOLLECT._needs_fetch("r", {"r": {"classification": retryable}}) is True


def test_xbrl_collector_request_error_retries_next_run_and_is_not_settled(tmp_path, monkeypatch):
    def list_answer(p):
        return {"status": "000", "list": [
            {"rcept_no": "R", "rcept_dt": "20151113", "report_nm": "분기보고서 (2015.09)"}],
                "page_no": 1, "page_count": 100, "total_count": 1, "total_page": 1}
    attempts = {"n": 0}
    def xbrl_answer(p):
        attempts["n"] += 1
        # Neither a ZIP nor DART's confirmed 014 envelope -- an unclassifiable
        # response, exactly what a transient request-layer fault looks like.
        return b"<html>upstream error</html>" if attempts["n"] == 1 else FULL_XBRL_ZIP
    calls = _scripted_list_and_xbrl(monkeypatch, list_answer, xbrl_answer)
    store, universe = tmp_path / "store", _one_ticker_universe(tmp_path)
    manifest = XCOLLECT.collect(store, "k", universe, COLLECT.Budget(1000, 10),
                               directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    # The other two stages (no matching filing at all) settle immediately;
    # only the one with a real filing hits the request-layer fault.
    assert manifest["classifications"] == {XO.REQUEST_ERROR: 1, XO.NO_ORIGINAL_FILING_INDEX: 2}
    assert not manifest["datasetComplete"]
    assert calls["xbrl"] == 1
    # Second run: the REQUEST_ERROR stage is retried, never read as settled.
    manifest2 = XCOLLECT.collect(store, "k", universe, COLLECT.Budget(1000, 10),
                                directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    assert calls["xbrl"] == 2
    assert manifest2["classifications"] == {XO.XBRL_ZIP_SERVED: 1, XO.NO_ORIGINAL_FILING_INDEX: 2}
    assert manifest2["recordsStored"] == 1 and manifest2["datasetComplete"]


def test_xbrl_collector_list_json_error_retries_next_run_and_is_not_settled(tmp_path, monkeypatch):
    attempts = {"n": 0}
    def list_answer(p):
        attempts["n"] += 1
        if attempts["n"] <= 3:
            # Internally inconsistent pagination metadata (totalCount>0 but
            # totalPage 0) makes `KCA.fetch_all_pages` raise `PaginationError`
            # -- a request-layer fault, not DART stating "no filings".
            return {"status": "000", "list": [], "page_no": 1, "page_count": 100,
                    "total_count": 5, "total_page": 0}
        return {"status": "013"}
    calls = _scripted_list_and_xbrl(monkeypatch, list_answer, lambda p: REAL_014_BODY)
    store, universe = tmp_path / "store", _one_ticker_universe(tmp_path)
    manifest = XCOLLECT.collect(store, "k", universe, COLLECT.Budget(1000, 10),
                               directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    assert manifest["classifications"] == {XCOLLECT.LIST_JSON_ERROR: 3}
    assert not manifest["datasetComplete"]
    assert calls["xbrl"] == 0  # never reached fnlttXbrl.xml on a list.json fault
    # Second run: every stage retries list.json rather than being treated as
    # already checked -- this time DART genuinely states no filings exist.
    manifest2 = XCOLLECT.collect(store, "k", universe, COLLECT.Budget(1000, 10),
                                directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    assert attempts["n"] == 6
    assert manifest2["classifications"] == {XO.NO_ORIGINAL_FILING_INDEX: 3}
    assert manifest2["datasetComplete"]


def test_file_not_available_014_stays_terminal_and_is_never_refetched(tmp_path, monkeypatch):
    def list_answer(p):
        return {"status": "000", "list": [
            {"rcept_no": "R", "rcept_dt": "20151113", "report_nm": "분기보고서 (2015.09)"}],
                "page_no": 1, "page_count": 100, "total_count": 1, "total_page": 1}
    calls = _scripted_list_and_xbrl(monkeypatch, list_answer, lambda p: REAL_014_BODY)
    store, universe = tmp_path / "store", _one_ticker_universe(tmp_path)
    manifest = XCOLLECT.collect(store, "k", universe, COLLECT.Budget(1000, 10),
                               directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    assert manifest["classifications"] == {XO.FILE_NOT_AVAILABLE_014: 1, XO.NO_ORIGINAL_FILING_INDEX: 2}
    # 014 is DART's own confirmed "file does not exist" answer for the exact
    # original receipt -- terminal, unlike a bare request error. A second run
    # never re-asks it.
    calls["list"] = calls["xbrl"] = 0
    manifest2 = XCOLLECT.collect(store, "k", universe, COLLECT.Budget(1000, 10),
                                directory_fn=lambda _: ONE_TICKER_UNIVERSE_DIRECTORY)
    assert calls == {"list": 0, "xbrl": 0}
    assert manifest2["datasetComplete"]


# --------------------------------------------------------------------------- #
# Expanded (all-stage) probe -- read-only, two endpoints, uses the real evidence
# --------------------------------------------------------------------------- #
def test_expanded_probe_reports_all_three_stages_for_both_endpoints(monkeypatch):
    def answers(p):
        return {"status": "013", "message": "조회된 데이타가 없습니다."}
    _scripted(monkeypatch, answers)
    def fake_list_json(key, corp, budget):
        return REAL_PERIODIC_000030, ""
    monkeypatch.setattr(COLLECT, "periodic_reports_via_list_json", fake_list_json)
    def fake_fetch_xbrl(key, rcept_no, stage, budget):
        budget.spend()
        return (FULL_XBRL_ZIP if rcept_no == "20151116001418" else REAL_014_BODY), ""
    monkeypatch.setattr(COLLECT, "fetch_original_xbrl", fake_fetch_xbrl)
    result = COLLECT.probe_2015("k", {"000030.KS": "살아있는회사"}, COLLECT.Budget(1000, 10), 1,
                          directory_fn=lambda _: [{"corpCode": "00254045",
                                                    "corpName": "살아있는회사",
                                                    "stockCode": "000030"}])
    row = result["sample"][0]
    assert [(f["stage"], f["selection"]) for f in row["originalFilings"]] == [
        ("11013", XO.ORIGINAL_LISTED), ("11012", XO.ORIGINAL_LISTED), ("11014", XO.ORIGINAL_LISTED)]
    q3 = next(f for f in row["originalFilings"] if f["stage"] == "11014")
    assert q3["xbrl"]["classification"] == XO.XBRL_ZIP_SERVED
    assert q3["xbrl"]["candidateAccounts"]["자산총계"]["status"] == XS.RESOLVED
    q1 = next(f for f in row["originalFilings"] if f["stage"] == "11013")
    assert q1["xbrl"]["classification"] == XO.FILE_NOT_AVAILABLE_014


# --------------------------------------------------------------------------- #
# Bulk collection no longer wastes calls on a proven-013 endpoint for 2015
# --------------------------------------------------------------------------- #
def test_year_codes_limits_fiscal_2015_to_the_annual_report_only():
    assert COLLECT.year_codes(2015) == COLLECT.ANNUAL_ONLY
    assert COLLECT.year_codes(2016) == COLLECT.CODES


def test_bulk_collector_pending_list_never_asks_fnlttSinglAcntAll_for_2015_quarterlies(tmp_path, monkeypatch):
    _scripted(monkeypatch, lambda p: {"status": "013"})
    manifest = COLLECT.collect(tmp_path / "store", "k", _universe(tmp_path), [2015, 2025],
                        COLLECT.Budget(1000, 60), directory_fn=lambda _: DIRECTORY)
    absent = json.loads((tmp_path / "store/absent.json").read_text())
    codes_asked_for_2015 = {k.split(":")[2] for k in absent if k.split(":")[1] == "2015"}
    unresolved = json.loads((tmp_path / "store/unresolved.json").read_text())
    codes_asked_for_2015 |= {k.split(":")[2] for k in unresolved if k.split(":")[1] == "2015"}
    assert codes_asked_for_2015 <= {"11011"}
    assert manifest["thisRun"]["calls"] > 0


# --------------------------------------------------------------------------- #
# Merge: candidate snapshot combines both sources, collision refused
# --------------------------------------------------------------------------- #
def test_merge_combines_both_sources_by_year(tmp_path):
    canon = tmp_path / "canonical-v2"
    HS.write_shard(DF.shard_path(canon, 2025), [
        {"id": "A.KS:2025:11011", "fiscalYear": 2025, "ticker": "A.KS", "reportCode": "11011"}])
    xbrl = tmp_path / "xbrl-original"
    HS.write_shard(xbrl / "dart-xbrl-2015.jsonl.gz", [
        {"id": "A.KS:2015:11014", "fiscalYear": 2015, "ticker": "A.KS", "reportCode": "11014"}])
    out = tmp_path / "merged"
    report = MERGE.merge(out, canon, xbrl)
    assert report["records"] == 2 and report["bySource"] == {"canonical-v2": 1, "xbrl-original": 1}
    assert HS.read_jsonl(DF.shard_path(out, 2025))[0]["id"] == "A.KS:2025:11011"
    assert HS.read_jsonl(DF.shard_path(out, 2015))[0]["id"] == "A.KS:2015:11014"


def test_merge_refuses_to_pick_a_side_on_collision(tmp_path):
    canon = tmp_path / "canonical-v2"
    HS.write_shard(DF.shard_path(canon, 2015), [
        {"id": "A.KS:2015:11014", "fiscalYear": 2015, "ticker": "A.KS", "reportCode": "11014",
         "source": "legacy"}])
    xbrl = tmp_path / "xbrl-original"
    HS.write_shard(xbrl / "dart-xbrl-2015.jsonl.gz", [
        {"id": "A.KS:2015:11014", "fiscalYear": 2015, "ticker": "A.KS", "reportCode": "11014",
         "source": "xbrl"}])
    with pytest.raises(ValueError, match="CANDIDATE_SOURCE_COLLISION"):
        MERGE.merge(tmp_path / "merged", canon, xbrl)


def test_merge_works_with_no_xbrl_dir_at_all(tmp_path):
    canon = tmp_path / "canonical-v2"
    HS.write_shard(DF.shard_path(canon, 2025), [
        {"id": "A.KS:2025:11011", "fiscalYear": 2025, "ticker": "A.KS", "reportCode": "11011"}])
    report = MERGE.merge(tmp_path / "merged", canon, None)
    assert report["records"] == 1 and report["bySource"] == {"canonical-v2": 1}


# --------------------------------------------------------------------------- #
# New modules obey the same outcome-free / sealed-file boundaries
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", [
    "pipeline/dart_xbrl_originals.py", "pipeline/dart_xbrl_statements.py",
    "scripts/collect_dart_xbrl_originals.py", "scripts/merge_kr_candidate_snapshot.py"])
def test_xbrl_repair_code_never_names_an_outcome_function(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert not [name for name in OUTCOME_NAMES if name in text]
