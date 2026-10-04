"""Source acquisition and parsing: identity, bytes, dates and missingness only. Synthetic bytes; no network."""
import ast
import importlib.util
import json
from pathlib import Path

from pipeline import kr_market_risk_source_parse as P
from pipeline import kr_market_risk_sources as S

ROOT = Path(__file__).resolve().parents[1]
OUTCOME_NAMES = {"forward_targets", "underwater_episodes", "episodes_at_least", "first_trigger_damage", "trigger_profile", "damage_summary", "fast_features",
                 "baseline_trigger_states", "overlay_count_series", "feature_statistics", "episode_landmarks", "loss_labels", "pct_change", "cummax", "rolling",
                 "expanding_percentile", "slow_features", "transition_features", "ts_spearman", "rank_corr_hac", "auroc", "diff", "shift", "log"}


def load_script():
    spec = importlib.util.spec_from_file_location("acquire", ROOT / "scripts/acquire_kr_market_risk_sources.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def yahoo_bytes(symbol="^KS200", n=5, offset=32400, currency="KRW", nulls=()):
    stamps = [946857600 + 86400 * i for i in range(n)]  # 2000-01-03 00:00 UTC onwards
    closes = [None if i in nulls else 100.0 + i for i in range(n)]
    return json.dumps({"chart": {"result": [{"meta": {"symbol": symbol, "currency": currency, "instrumentType": "INDEX", "gmtoffset": offset, "exchangeTimezoneName": "Asia/Seoul"},
                                             "timestamp": stamps, "indicators": {"quote": [{"close": closes}]}}]}}).encode()


def fred_bytes(values):
    return json.dumps({"observations": [{"date": f"2000-01-{3 + i:02d}", "value": v} for i, v in enumerate(values)]}).encode()


def test_fred_parser_drops_and_counts_missing_values_never_fills():
    rows, dropped = P.parse_fred_observations(fred_bytes(["1.5", ".", "2.5", "", "x", "-0.5"]))
    assert rows == [("2000-01-03", 1.5), ("2000-01-05", 2.5), ("2000-01-08", -0.5)] and dropped == 3  # negative yields are legitimate
    rows, dropped = P.parse_fred_observations(fred_bytes(["10", "0", "-1"]), positive_required=True)
    assert rows == [("2000-01-03", 10.0)] and dropped == 2


def test_yahoo_parser_uses_exchange_local_date_and_counts_nulls():
    rows, dropped, identity = P.parse_yahoo_chart(yahoo_bytes(nulls=(1,)))
    assert rows[0][0] == "2000-01-03" and len(rows) == 4 and dropped == 1  # 00:00 UTC + 9h is still 2000-01-03 in Seoul
    assert identity["symbol"] == "^KS200" and identity["currency"] == "KRW" and identity["exchangeTimezoneName"] == "Asia/Seoul"
    ny, _, _ = P.parse_yahoo_chart(yahoo_bytes("^VIX", offset=-18000))
    assert ny[0][0] == "2000-01-02"  # the exchange-local date, not the UTC date
    rows, dropped, _ = P.parse_yahoo_chart(yahoo_bytes(), field="close", positive_required=True)
    assert dropped == 0 and rows[-1][1] == 104.0


def test_fdr_parser_and_duplicates_are_kept_and_counted():
    rows, dropped = P.parse_fdr_csv(b"Date,Open,Close\n2000-01-03,1,100\n2000-01-03,1,101\n2000-01-04,1,\n2000-01-05,1,0\n")
    assert rows == [("2000-01-03", 100.0), ("2000-01-03", 101.0)] and dropped == 2
    audit = P.metadata_audit(rows, dropped, 4)
    assert audit["duplicateDates"] == 1 and audit["validRows"] == 2 and audit["droppedRows"] == 2 and audit["firstDate"] == "2000-01-03"


def test_normalised_csv_is_deterministic_and_roundtrips():
    rows = [("2000-01-03", 100.5), ("2000-01-04", 101.25)]
    data = P.normalized_csv(rows)
    assert data == P.normalized_csv(rows) and P.read_normalized(data) == rows and P.sha256(data) == P.sha256(P.normalized_csv(list(rows)))
    assert data.startswith(b"date,value\n")


def test_metadata_audit_carries_dates_and_counts_but_no_value_statistics():
    audit = P.metadata_audit([("2000-01-03", 1.0), ("2001-01-03", 2.0), ("2001-01-04", 3.0)], 0, 3)
    assert audit["rowsByYear"] == {"2000": 1, "2001": 2} and audit["datesSorted"] is True
    assert not any(k in audit for k in ("min", "max", "mean", "median", "std", "last", "first"))  # no value is summarised


def test_parse_and_acquisition_code_never_reference_an_outcome_function():
    for module in ("pipeline/kr_market_risk_source_parse.py", "scripts/acquire_kr_market_risk_sources.py"):
        tree = ast.parse((ROOT / module).read_text())
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not (used & OUTCOME_NAMES), (module, used & OUTCOME_NAMES)
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert "kr_market_risk_anatomy" not in imported and "kr_market_risk_anatomy_execution" not in imported


def test_acquire_one_retains_raw_bytes_hashes_and_identity(tmp_path):
    acquire = load_script()
    acquire.fetch_yahoo = lambda entry, today: {"raw": {"chart.json": yahoo_bytes()}, "status": {"chart": 200}, "error": None, "host": "query1.finance.yahoo.com"}
    record = acquire.acquire_one("YAHOO_KS200", S.SOURCES["YAHOO_KS200"], "", "2026-10-02", tmp_path)
    assert record["status"] == "ACQUIRED" and record["identityOk"] is True and record["firstDate"] == "2000-01-03" and record["validRows"] == 5
    raw = (tmp_path / "YAHOO_KS200" / "raw_chart.json").read_bytes()
    assert raw == yahoo_bytes() and record["files"]["raw_chart.json"] == P.sha256(raw)
    assert record["files"]["normalized.csv"] == P.sha256((tmp_path / "YAHOO_KS200" / "normalized.csv").read_bytes())
    acquire.fetch_yahoo = lambda entry, today: {"raw": {"chart.json": yahoo_bytes(symbol="^OTHER")}, "status": {"chart": 200}, "error": None, "host": "x"}
    assert acquire.acquire_one("YAHOO_KS200", S.SOURCES["YAHOO_KS200"], "", "2026-10-02", tmp_path / "b")["identityOk"] is False  # another instrument is not the registered one
    acquire.fetch_yahoo = lambda entry, today: {"raw": {}, "status": {"chart": 429}, "error": "HTTP 429", "host": None}
    failed = acquire.acquire_one("YAHOO_KS200", S.SOURCES["YAHOO_KS200"], "", "2026-10-02", tmp_path / "c")
    assert failed["status"] == "FAILED" and failed["error"] == "HTTP 429" and "key" not in json.dumps(failed).lower()


def test_acquired_sources_are_immutable_and_failed_sources_retry_at_most_three_times(tmp_path):
    acquire = load_script()
    calls = []

    def fake(sid, entry, key, today, out):
        calls.append(sid)
        ok = sid != "FDR_KS200"
        return {"id": sid, "status": "ACQUIRED" if ok else "FAILED", "firstDate": "2000-01-03", "lastDate": "2026-10-01", "validRows": 1}
    acquire.acquire_one = fake
    acquire.time.sleep = lambda s: None
    for _ in range(5):
        acquire.main(["--output", str(tmp_path)])
    audit = json.loads((tmp_path / "audit.json").read_text())
    assert calls.count("YAHOO_KS200") == 1 and calls.count("FDR_KS200") == 3  # acquired once; the failing one stops after three attempts
    assert audit["sources"]["FDR_KS200"]["attempts"] == 3 and set(audit["sources"]) == set(S.ACQUIRED_IDS)
    assert "No return" in " ".join(audit["statements"])


def test_source_workflow_is_branch_scoped_has_no_schedule_or_dispatch_and_one_write_permission():
    workflow = (ROOT / ".github/workflows/kr-market-risk-anatomy-v1-sources.yml").read_text()
    for forbidden in ("schedule:", "cron", "workflow_dispatch", "kr_market_risk_anatomy_execution", "--mode execute", "KRX_API_KEY", "DART", "ECOS"):
        assert forbidden not in workflow
    assert workflow.count("contents: write") == 1 and "github.head_ref == 'claude/gifted-carson-g7rcbx'" in workflow and "head.repo.full_name == github.repository" in workflow
    assert "FRED_API_KEY" in workflow and workflow.count("secrets.") == 1
    assert "pull_request" in workflow and "refetch" in workflow
