"""Invented observations only; no network, real price labels or production writes."""
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from pipeline import collector_outcomes as CO
from pipeline import historical_store as HS
from pipeline import us_daily_market_data as D
from pipeline import us_daily_market_sources as S

NOW = "2026-10-12T02:00:00Z"
LATER = "2026-10-13T02:00:00Z"
ROOT = Path(__file__).resolve().parents[1]


def membership(at=NOW, rows=None):
    rows = rows or [("SYN-A", "합성 A", "100"), ("SYN-B", "합성 B", "200")]
    raw = "Symbol,Security,CIK,Date added\n" + "".join(f"{t},{n},{c},2000-01-01\n" for t, n, c in rows)
    return D.MembershipResponse(raw.encode(), "SYNTHETIC_MEMBERSHIP_FIXTURE", "fixture-v1", at,
                                "2026-10-09T00:00:00Z", D.SYNTHETIC)


def reply(ticker="SYN-A", start="2026-10-09", through="2026-10-09", at=NOW, close=100):
    dates = D.sessions(start, through, "US").tz_localize("America/New_York")
    frame = pd.DataFrame({"Open": 100., "High": max(101., close), "Low": 99., "Close": float(close),
                          "Volume": 1000., "Dividends": 0., "Stock Splits": 0.}, index=dates)
    metadata = {"symbol": ticker, "currency": "USD", "exchangeTimezoneName": "America/New_York",
                "instrumentType": "ETF" if ticker in D.BENCHMARKS else "EQUITY",
                "acquisitionOptions": dict(D.PRICE_OPTIONS)}
    return D.PriceResponse(frame, metadata, at)


def fetch(ticker, start, through):
    return reply(ticker, start, through)


def file_bytes(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def member(snapshot, ticker="SYN-A"):
    return next(m for m in snapshot["members"] if m["ticker"] == ticker)


def test_as_traded_basis_split_volume_and_dividends_are_restored_once():
    snapshot = D.membership_snapshot(membership(), NOW)
    r = reply(start="2026-10-08")
    r.frame.loc[:, ["Open", "High", "Low", "Close"]] /= 2
    r.frame.loc[r.frame.index[0], "Dividends"] = 1
    r.frame.loc[r.frame.index[1], "Stock Splits"] = 2
    r.frame["Adj Close"] = 999999  # Never a daily observed close or an input.
    records = D.price_records(r, member(snapshot), snapshot, ["2026-10-08", "2026-10-09"], NOW)
    first, second = [x["core"] for x in records]
    assert first["Close"] == 100
    assert first["cashDividendAsTraded"] == 2
    assert first["Volume"] == 500
    assert second["Close"] == 50  # A split must not scale its own session.
    assert second["Volume"] == 1000
    assert second["splitRatio"] == 2
    assert "Adj Close" not in records[0]["sourcePanel"][0]
    assert all(r["totalReturnComputed"] is False for r in records)
    assert records[0]["core"]["adjustmentVersion"] == D.ADJUSTMENT_VERSION


@pytest.mark.parametrize("now,expected", [
    ("2026-10-09T20:59:59Z", "2026-10-08"),
    ("2026-10-09T21:00:00Z", "2026-10-09"),
    ("2026-10-12T02:00:00Z", "2026-10-09"),
    ("2026-11-27T18:59:59Z", "2026-11-25"),
    ("2026-11-27T19:00:00Z", "2026-11-27"),
    ("2026-11-30T21:59:59Z", "2026-11-27"),
    ("2026-11-30T22:00:00Z", "2026-11-30"),
])
def test_independent_us_calendar_holidays_dst_and_early_close(now, expected):
    assert D.completed_sessions(now)[-1] == expected


@pytest.mark.parametrize("change", [
    lambda r: r.frame.drop(columns="Dividends", inplace=True),
    lambda r: r.frame.__setitem__("Close", float("nan")),
    lambda r: r.frame.__setitem__("Close", 0),
    lambda r: r.frame.__setitem__("Volume", -1),
    lambda r: r.frame.__setitem__("Stock Splits", -1),
    lambda r: r.metadata.__setitem__("currency", "KRW"),
    lambda r: r.metadata.__setitem__("symbol", "OTHER"),
    lambda r: r.metadata["acquisitionOptions"].__setitem__("auto_adjust", True),
    lambda r: r.metadata["acquisitionOptions"].__setitem__("back_adjust", True),
    lambda r: r.metadata["acquisitionOptions"].__setitem__("repair", True),
])
def test_ambiguous_basis_invalid_units_and_missing_values_fail_closed(change):
    snapshot = D.membership_snapshot(membership(), NOW)
    r = reply()
    change(r)
    with pytest.raises(D.Refused):
        D.price_records(r, member(snapshot), snapshot, ["2026-10-09"], NOW)


def test_zero_actions_and_zero_reported_volume_are_not_missing():
    snapshot = D.membership_snapshot(membership(), NOW)
    r = reply()
    r.frame["Volume"] = 0.
    row = D.price_records(r, member(snapshot), snapshot, ["2026-10-09"], NOW)[0]
    assert row["core"]["Volume"] == row["core"]["cashDividendAsTraded"] == 0
    assert row["core"]["splitRatio"] == 1


@pytest.mark.parametrize("problem", ["empty", "stale", "future", "duplicate", "utc"])
def test_bad_daily_windows_never_become_zero_or_a_holiday(problem):
    snapshot = D.membership_snapshot(membership(), NOW)
    r = reply()
    if problem == "empty":
        r.frame.drop(r.frame.index, inplace=True)
    elif problem == "stale":
        r.frame.index = pd.to_datetime(["2026-10-08"]).tz_localize("America/New_York")
    elif problem == "future":
        r.frame.index = pd.to_datetime(["2026-10-12"]).tz_localize("America/New_York")
    elif problem == "duplicate":
        r = D.PriceResponse(pd.concat([r.frame, r.frame]), r.metadata, r.observed_at)
    else:
        r.frame.index = r.frame.index.tz_convert("UTC")
    with pytest.raises(D.Refused):
        D.price_records(r, member(snapshot), snapshot, ["2026-10-09"], NOW)


def test_membership_no_row_drops_no_effective_date_and_shared_aliases():
    snap = D.membership_snapshot(membership(rows=[("BRK.B", "合成 class B", "123"), ("BRK.A", "合成 class A", "123")]), NOW)
    assert {m["ticker"] for m in snap["members"]} == {"BRK-A", "BRK-B"}
    assert len({m["securityId"] for m in snap["members"]}) == 2
    assert snap["effectiveMembershipDate"] is None
    assert snap["pitCompleteHistoricalUniverse"] is False
    assert snap["officialCompletenessVerified"] is False
    with pytest.raises(D.Refused):
        D.membership_snapshot(membership(rows=[("BRK.B", "A", "123"), ("BRKB", "B", "123")]), NOW)
    with pytest.raises(D.Refused):
        D.membership_snapshot(membership(rows=[("SYN-A", "A", "")]), NOW)
    with pytest.raises(D.Refused):
        D.membership_snapshot(membership(rows=[("American Airlines Group", "A", "123")]), NOW)


def test_missing_stale_short_real_and_future_universe_are_blocked():
    response = membership()
    with pytest.raises(D.Refused, match="stale"):
        D.membership_snapshot(response, "2026-10-14T02:00:00Z")
    with pytest.raises(D.Refused, match="future"):
        D.membership_snapshot(response, "2026-10-11T02:00:00Z")
    with pytest.raises(D.Refused, match="Incomplete"):
        D.membership_snapshot(D.MembershipResponse(response.raw, response.source, response.source_identity,
                                                  NOW, response.source_last_changed_at, D.LIVE), NOW)
    with pytest.raises(D.Refused):
        D.membership_snapshot(D.MembershipResponse(b"", response.source, response.source_identity,
                                                  NOW, response.source_last_changed_at, D.SYNTHETIC), NOW)


def test_reused_ticker_changed_name_and_missing_member_are_explicit():
    old = D.membership_snapshot(membership(), NOW)
    new = D.membership_snapshot(membership(LATER, [("SYN-A", "合成 new issuer", "999")]), LATER)
    targets, issues = D.target_members(new, old)
    assert {i["code"] for i in issues} == {"TICKER_REUSED_DIFFERENT_CIK", "REMOVED_OR_MISSING_EFFECTIVE_DATE_UNVERIFIED"}
    assert all(i["blocksPrice"] for i in issues)
    assert {t["ticker"] for t in targets} == {"SYN-A", "SYN-B", "SPY", "QQQ"}
    assert member(old)["securityId"] != member(new)["securityId"]
    renamed = D.membership_snapshot(membership(LATER, [("SYN-A", "合成 rename", "100"), ("SYN-B", "합성 B", "200")]), LATER)
    _, warnings = D.target_members(renamed, old)
    assert warnings[0]["code"] == "NAME_CHANGE_IDENTITY_REVIEW_REQUIRED"


def test_complete_idempotent_deterministic_and_only_own_namespaces(tmp_path):
    root = tmp_path / "first"
    untouched = root / "weekly-decisions/receipts.jsonl"
    untouched.parent.mkdir(parents=True)
    untouched.write_bytes(b"existing unrelated bytes\n")
    result = D.collect(root, membership(), fetch, now=NOW)
    assert result["collectionComplete"] is True
    assert result["appended"] == 4
    before = file_bytes(root)
    replay = D.collect(root, membership(), lambda *a: pytest.fail("No source call on idempotent replay"), now=NOW)
    assert replay == result
    assert file_bytes(root) == before
    assert untouched.read_bytes() == b"existing unrelated bytes\n"
    other = tmp_path / "second"
    assert D.collect(other, membership(), fetch, now=NOW) == result
    assert {k: v for k, v in file_bytes(other).items()} == {k: v for k, v in before.items() if k.startswith(("prices/us/", "universe/us/"))}
    for p in root.rglob("*.jsonl.gz"):
        assert p.read_bytes()[4:8] == b"\0\0\0\0"
    assert not (root / "historical").exists()


def test_partial_budget_resumes_without_duplicate_prices(tmp_path):
    first = D.collect(tmp_path, membership(), fetch, now=NOW, max_calls=3)
    assert first["status"] == "PARTIAL"
    assert first["appended"] == 3
    assert first["missingBenchmarks"] == []
    store = D.ObservationStore(tmp_path, D.SYNTHETIC)
    old = {r["id"]: r["digest"] for r in store.observations().values()}
    second = D.collect(tmp_path, membership(), fetch, now=NOW)
    assert second["status"] == "COMPLETE"
    assert second["appended"] == 1
    assert all(store.observations()[key]["digest"] == value for key, value in old.items())
    assert len(store.observations()) == 4


def test_benchmark_refusal_stops_stock_fanout_and_reports_all_missing(tmp_path):
    calls = []
    def refused(ticker, *a):
        calls.append(ticker)
        raise D.Refused("SYNTHETIC_HTTP_REFUSAL", "SYNTHETIC HTTP 403", CO.BLOCKED_SOURCE)
    result = D.collect(tmp_path, membership(), refused, now=NOW)
    assert calls == ["QQQ", "SPY"]
    assert {r["ticker"] for r in result["missingBenchmarks"]} == {"SPY", "QQQ"}
    assert len(result["missing"]) == 4
    assert result["collectionComplete"] is False
    assert result["appended"] == 0
    assert all(r["sourceMessage"] == "SYNTHETIC HTTP 403" for r in result["sourceFailures"])


def test_partial_source_refusal_preserves_real_fixture_progress(tmp_path):
    def partial(ticker, start, through):
        if ticker == "SYN-B":
            raise D.Refused("SYNTHETIC_NETWORK_REFUSAL", "SYNTHETIC timeout", CO.NETWORK_ERROR)
        return fetch(ticker, start, through)
    result = D.collect(tmp_path, membership(), partial, now=NOW)
    assert result["appended"] == 3
    assert result["status"] == "PARTIAL"
    assert result["missing"] == [{"date": "2026-10-09", "ticker": "SYN-B"}]
    assert result["sourceFailures"][0]["outcome"] == CO.NETWORK_ERROR


def test_interruption_commits_buffer_and_resumes(tmp_path):
    def interrupted(ticker, start, through):
        if ticker == "SYN-A":
            raise KeyboardInterrupt()
        return fetch(ticker, start, through)
    with pytest.raises(KeyboardInterrupt):
        D.collect(tmp_path, membership(), interrupted, now=NOW)
    store = D.ObservationStore(tmp_path, D.SYNTHETIC)
    assert len(store.observations()) == 2
    manifests = store._rows(store.prices / "manifests", "run-*.jsonl.gz")
    assert manifests[0]["status"] == "INTERRUPTED"
    assert D.collect(tmp_path, membership(), fetch, now=NOW)["appended"] == 2


def test_later_correction_quarantined_and_never_rewrites_historical_asof(tmp_path):
    D.collect(tmp_path, membership(), fetch, now=NOW)
    store = D.ObservationStore(tmp_path, D.SYNTHETIC)
    history = deepcopy(store.prices_at(NOW))
    original_files = {str(p): p.read_bytes() for p in store.prices.glob("*/observations-*.jsonl.gz")}
    def changed(ticker, start, through):
        return reply(ticker, start, through, at=LATER, close=101 if ticker == "SYN-A" else 100)
    result = D.collect(tmp_path, membership(LATER), changed, now=LATER, target_dates=["2026-10-09"], recheck=True)
    assert result["status"] == "REVISION_CONFLICT"
    assert result["collectionComplete"] is False
    assert result["conflicts"] == 1
    assert store.prices_at(NOW) == history
    assert all(Path(p).read_bytes() == b for p, b in original_files.items())
    assert sum(x["status"] == "REVISION_CONFLICT" for x in store.prices_at(LATER).values()) == 1
    again = D.collect(tmp_path, membership(LATER), changed, now=LATER, target_dates=["2026-10-09"])
    assert again["collectionComplete"] is False
    assert again["activeRevisionConflicts"] == 1


def test_later_split_restores_same_core_and_retains_acquisition_evidence(tmp_path):
    D.collect(tmp_path, membership(), fetch, now=NOW)
    store = D.ObservationStore(tmp_path, D.SYNTHETIC)
    before = deepcopy(store.prices_at(NOW))
    def split(ticker, start, through):
        r = reply(ticker, start, through, at=LATER)
        if ticker == "SYN-A":
            r.frame.loc[:, ["Open", "High", "Low", "Close"]] /= 2
            r.frame.loc[r.frame.index[0], "Volume"] *= 2
            r.frame.loc[r.frame.index[-1], "Stock Splits"] = 2
        return r
    result = D.collect(tmp_path, membership(LATER), split, now=LATER, target_dates=["2026-10-09"], recheck=True)
    assert result["conflicts"] == 0
    assert result["repeated"] == 4
    assert store.prices_at(NOW) == before
    acquisitions = store._rows(store.prices / "source-acquisitions", "*/source-*.jsonl.gz")
    assert len(acquisitions) == 8


def test_no_lookahead_no_backdated_membership_no_survivor_retroassignment(tmp_path):
    D.collect(tmp_path, membership(), fetch, now=NOW)
    store = D.ObservationStore(tmp_path, D.SYNTHETIC)
    assert store.snapshot_at("2026-10-09T22:00:00Z") is None
    assert store.prices_at("2026-10-09T22:00:00Z") == {}
    snap = store.snapshot_at(NOW)
    assert snap["effectiveMembershipDate"] is None
    assert all(r["membershipApplicability"] == "OBSERVED_QUERY_SET_NOT_ASSERTED_SESSION_MEMBERSHIP" for r in store.observations().values())
    store.save_snapshot(D.membership_snapshot(membership(LATER), LATER), membership(LATER).raw)
    assert store.snapshot_at(NOW) == snap
    backwards = membership("2026-10-11T03:00:00Z", [("SYN-Z", "合成 Z", "900")])
    with pytest.raises(D.Refused, match="earlier"):
        store.save_snapshot(D.membership_snapshot(backwards, backwards.observed_at), backwards.raw)


def test_store_corruption_duplicate_ids_and_source_missing_are_visible(tmp_path):
    D.collect(tmp_path, membership(), fetch, now=NOW)
    store = D.ObservationStore(tmp_path, D.SYNTHETIC)
    path = next(store.prices.glob("*/observations-*.jsonl.gz"))
    before = path.read_bytes()
    path.write_bytes(before+b"corruption")
    with pytest.raises(D.Refused, match="Corrupt"):
        store.observations()
    path.write_bytes(before)
    next((store.universe/"sources").glob("*.csv")).unlink()
    with pytest.raises(D.Refused, match="Original source|Referenced original"):
        store.observations()


def test_unsafe_destinations_symlinks_and_unbounded_history_are_rejected(tmp_path):
    with pytest.raises(D.Refused, match="outside"):
        D.ObservationStore(ROOT/"ledger")
    root = tmp_path/"git"
    (root/".git").mkdir(parents=True)
    (root/".git/HEAD").write_text("ref: refs/heads/signal-history\n")
    with pytest.raises(D.Refused, match="production"):
        D.ObservationStore(root)
    unsafe = tmp_path/"unsafe"
    external = tmp_path/"external"
    external.mkdir()
    store = D.ObservationStore(unsafe, D.SYNTHETIC)
    store.prices.parent.mkdir(parents=True)
    store.prices.symlink_to(external, target_is_directory=True)
    with pytest.raises(D.Refused, match="symlink"):
        D.collect(unsafe, membership(), fetch, now=NOW)
    with pytest.raises(D.Refused, match="bounded"):
        D.collect(tmp_path/"old", membership(), fetch, now=NOW, target_dates=["2026-09-01"])


def test_collector_has_no_research_or_production_execution_interface():
    for name in ("pipeline/us_daily_market_data.py", "pipeline/us_daily_market_sources.py", "scripts/collect_us_daily_prices.py"):
        text = (ROOT/name).read_text()
        assert not any(x in text for x in ("fit(", "forward_return", "load_market_values", "append_signals", "weekly_publish", "workflow_dispatch", "git push"))


def test_provider_pins_current_csv_and_preserves_refusal_text(monkeypatch):
    response = membership()
    calls = []
    def get(url):
        calls.append(url)
        if "api.github.com" in url:
            return b'[{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","commit":{"committer":{"date":"2026-10-09T00:00:00Z"}}}]'
        return response.raw
    monkeypatch.setattr(S, "_get", get)
    monkeypatch.setattr(S, "now_utc", lambda: NOW)
    current = S.current_sp500()
    assert "/"+"a"*40+"/" in calls[1]
    assert current.raw == response.raw
    assert current.source_kind == D.LIVE
    assert len(calls) == 2


def test_shard_ceiling_is_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(HS, "MAX_SHARD_BYTES", 1)
    with pytest.raises(D.Refused, match="ceiling"):
        D.collect(tmp_path, membership(), fetch, now=NOW)


def test_timestamp_order_is_correct_with_fractional_seconds():
    assert D.stamp(NOW) < D.stamp("2026-10-12T02:00:00.000001Z")


def test_missing_committed_chunk_cannot_reuse_complete_manifest(tmp_path):
    D.collect(tmp_path, membership(), fetch, now=NOW)
    store = D.ObservationStore(tmp_path, D.SYNTHETIC)
    next(store.prices.glob("*/observations-*.jsonl.gz")).unlink()
    with pytest.raises(D.Refused, match="committed chunk"):
        D.collect(tmp_path, membership(), fetch, now=NOW)


def test_missing_acquisition_evidence_is_not_a_valid_price(tmp_path):
    D.collect(tmp_path, membership(), fetch, now=NOW)
    store = D.ObservationStore(tmp_path, D.SYNTHETIC)
    next(store.prices.glob("source-acquisitions/*/source-*.jsonl.gz")).unlink()
    with pytest.raises(D.Refused, match="acquisition evidence"):
        store.observations()


def test_identity_block_survives_repeated_new_universe_captures(tmp_path):
    D.collect(tmp_path, membership(), fetch, now=NOW)
    rows = [("SYN-A", "합성 A", "999")]
    for at in (LATER, "2026-10-14T02:00:00Z"):
        response = membership(at, rows)
        def current_fetch(ticker, start, through):
            return reply(ticker, start, through, at=at)
        result = D.collect(tmp_path, response, current_fetch, now=at)
        assert result["status"] == "IDENTITY_BLOCKED"
        assert {i["code"] for i in result["identityIssues"]} == {
            "TICKER_REUSED_DIFFERENT_CIK", "REMOVED_OR_MISSING_EFFECTIVE_DATE_UNVERIFIED"}
        assert {m["ticker"] for m in result["requestedInstruments"]} == {"SYN-A", "SYN-B", "SPY", "QQQ"}
        assert not result["collectionComplete"]


def test_duplicate_price_columns_are_refused():
    snapshot = D.membership_snapshot(membership(), NOW)
    r = reply()
    duplicated = pd.concat([r.frame, r.frame[["Close"]]], axis=1)
    r = D.PriceResponse(duplicated, r.metadata, r.observed_at)
    with pytest.raises(D.Refused, match="Missing prices/actions"):
        D.price_records(r, member(snapshot), snapshot, ["2026-10-09"], NOW)


def test_time_budget_stops_without_fabricating_missing_data(tmp_path, monkeypatch):
    clock = iter([0, 0, 2])
    monkeypatch.setattr(D.time, "monotonic", lambda: next(clock))
    result = D.collect(tmp_path, membership(), fetch, now=NOW, max_seconds=1)
    assert result["calls"] == result["appended"] == 1
    assert result["stopReason"] == "TIME_BUDGET_SPENT"
    assert len(result["missing"]) == 3


def test_cli_preserves_pre_universe_refusal_as_unknown_not_zero(tmp_path, monkeypatch, capsys):
    from scripts import collect_us_daily_prices as CLI
    def refusal():
        raise D.Refused("SOURCE_BLOCKED", "fixture: original 403 refusal", CO.BLOCKED_SOURCE)
    monkeypatch.setattr(S, "current_sp500", refusal)
    assert CLI.main([str(tmp_path)]) == 1
    import json
    result = json.loads(capsys.readouterr().out)
    assert result["expectedConstituentSecurityCount"] is None
    assert result["benchmarkStatus"] == "NOT_MEASURED"
    assert result["sourceMessage"] == "fixture: original 403 refusal"
    assert len(D.ObservationStore(tmp_path).manifests()) == 1


def test_optional_capital_gains_preserve_missing_versus_reported_zero():
    snapshot = D.membership_snapshot(membership(), NOW)
    r = reply()
    missing = D.price_records(r, member(snapshot), snapshot, ["2026-10-09"], NOW)[0]
    assert missing["core"]["capitalGainsAsTraded"] is None
    assert missing["core"]["capitalGainsStatus"] == "NOT_REPORTED"
    r.frame["Capital Gains"] = 0.
    zero = D.price_records(r, member(snapshot), snapshot, ["2026-10-09"], NOW)[0]
    assert zero["core"]["capitalGainsAsTraded"] == 0
    assert zero["core"]["capitalGainsStatus"] == "REPORTED"
    r.frame["Capital Gains"] = float("nan")
    with pytest.raises(D.Refused, match="capital gains"):
        D.price_records(r, member(snapshot), snapshot, ["2026-10-09"], NOW)


def test_source_adapter_requests_exact_basis_and_does_not_refetch_metadata(monkeypatch):
    import yfinance as yf
    calls = []
    class Security:
        _price_history = type("History", (), {"_history_metadata": reply().metadata})()
        def history(self, **kwargs):
            calls.append(kwargs)
            return reply().frame
    monkeypatch.setattr(yf, "Ticker", lambda ticker: Security())
    monkeypatch.setattr(S, "now_utc", lambda: NOW)
    result = S.yahoo_daily("SYN-A", "2026-10-09", "2026-10-09")
    assert len(calls) == 1
    assert all(calls[0][k] == v for k, v in D.PRICE_OPTIONS.items())
    assert calls[0]["raise_errors"] and calls[0]["keepna"]
    assert calls[0]["end"] == "2026-10-10"
    assert result.metadata["currency"] == "USD"


def test_price_observation_cannot_be_backdated_or_far_future():
    snapshot = D.membership_snapshot(membership(), NOW)
    r = reply(at="2026-10-15T02:00:00Z")
    with pytest.raises(D.Refused, match="bounded observation run"):
        D.price_records(r, member(snapshot), snapshot, ["2026-10-09"], NOW)
