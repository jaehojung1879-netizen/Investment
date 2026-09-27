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
    absent = {RS.record_id("A.KS", 2016, "11012"): {"fiscalYear": 2016, "reportCode": "11012"}}
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
    absent = json.loads((tmp_path / "store/absent.json").read_text())
    q1 = absent[RS.record_id("000001.KS", 2025, "11013")]
    # DART said 100, not 013 -- and that is what is kept.
    assert [a["status"] for a in q1["attempts"]] == ["100", "100"]
    # Second run: nothing stored or settled is fetched again.
    calls.clear()
    COLLECT.collect(tmp_path / "store", "k", _universe(tmp_path), [2025],
                    COLLECT.Budget(1000, 10), directory_fn=lambda _: DIRECTORY)
    assert calls == []


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
    assert "git add ledger/fundamentals/kr-raw ledger/fundamentals/kr-canonical-v2" in job
    assert "git add ledger/fundamentals\n" not in job and "git add ledger/fundamentals/kr\n" not in job
    # Every step that tees a collector or audit keeps its exit status.
    for step in job.split("      - name: ")[1:]:
        if "| tee" in step:
            assert "set -o pipefail" in step, step.splitlines()[0]
