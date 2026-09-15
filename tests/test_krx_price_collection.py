"""The daily price collector: its budget, its filter, and what it will not record.

Same three properties the membership collector has to hold, for the same
reasons — a refusal is never a fact about the market, a shut day is marked done
because the calendar will not change on a retry, and a re-run writes no bytes.
What is new here is the ticker filter, which is the only decision this side
makes, and the scale: 3,570 sessions instead of 165 dates.

Nothing touches the network; `call` is replaced.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import collect_krx_daily_prices as CP  # noqa: E402
import collect_krx_universe_snapshots as CC  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import krx_universe as KU  # noqa: E402


def _session(codes, date, close="1000"):
    return {"OutBlock_1": [
        {"ISU_CD": code, "BAS_DD": date.replace("-", ""), "TDD_CLSPRC": close,
         "TDD_OPNPRC": close, "TDD_HGPRC": close, "TDD_LWPRC": close,
         "ACC_TRDVOL": "10", "LIST_SHRS": "1000"} for code in codes]}


def _fake(responses):
    asked = []

    def call(base, path, params, auth_key, timeout=40):
        asked.append(params["basDd"])
        answer = responses.get(params["basDd"], {"OutBlock_1": []})
        if isinstance(answer, Exception):
            raise answer
        return answer

    call.asked = asked
    return call


def _collect(tmp_path, targets, responses, monkeypatch, **kwargs):
    call = _fake(responses)
    monkeypatch.setattr(CP, "call", call)
    result = CP.collect(tmp_path, targets, auth_key="k", base="b",
                        keep=kwargs.pop("keep", None),
                        max_calls=kwargs.pop("max_calls", 100),
                        max_minutes=kwargs.pop("max_minutes", 10),
                        pace=0.0, log=lambda *a: None, **kwargs)
    result["asked"] = call.asked
    return result


# ---------------------------------------------------------------- refusals

def test_a_refusal_stops_the_run_and_marks_nothing_done(tmp_path, monkeypatch):
    result = _collect(tmp_path, ["2013-01-02", "2013-01-03"],
                      {"20130102": CP.Refused("HTTP 401 — Unauthorized API Call")},
                      monkeypatch)
    assert result["sessions"] == [] and result["stopped"]
    assert CP.load_done(tmp_path) == set()


def test_an_unreadable_payload_stops_rather_than_reading_as_a_holiday(
        tmp_path, monkeypatch):
    result = _collect(tmp_path, ["2013-01-02"],
                      {"20130102": {"respMsg": "Unauthorized API Call"}},
                      monkeypatch)
    assert result["sessions"] == [] and result["stopped"]
    assert CP.load_done(tmp_path) == set()


def test_a_closed_day_is_marked_done_and_never_asked_again(tmp_path, monkeypatch):
    """The calendar will not change on a retry; the quota would."""
    first = _collect(tmp_path, ["2013-01-01"], {}, monkeypatch)
    assert first["closed"] == ["2013-01-01"] and first["stopped"] is None
    second = _collect(tmp_path, ["2013-01-01"], {}, monkeypatch)
    assert second["asked"] == []


# ---------------------------------------------------------------- the filter

def test_only_the_universe_tickers_are_written(tmp_path, monkeypatch):
    result = _collect(tmp_path, ["2013-01-02"],
                      {"20130102": _session(["000001", "000002", "999999"],
                                            "2013-01-02")},
                      monkeypatch, keep={"000001.KS", "000002.KS"})
    rows = HS.read_jsonl(tmp_path / "krx-prices-2013.jsonl.gz")
    assert sorted(r["ticker"] for r in rows) == ["000001.KS", "000002.KS"]
    assert result["bars"] == 2


def test_the_filter_does_not_change_the_call_count(tmp_path, monkeypatch):
    """The endpoint answers with the whole exchange either way.

    Worth pinning because it is the argument for the filter being a storage
    bound rather than a measurement choice: narrowing it costs nothing and
    buys nothing but disk.
    """
    responses = {"20130102": _session(["000001", "999999"], "2013-01-02")}
    narrow = _collect(tmp_path, ["2013-01-02"], responses, monkeypatch,
                      keep={"000001.KS"})
    wide = _collect(tmp_path / "wide", ["2013-01-02"], responses, monkeypatch)
    assert narrow["calls"] == wide["calls"] == 1
    assert narrow["bars"] == 1 and wide["bars"] == 2


def test_the_keep_set_is_read_from_the_membership_shards(tmp_path):
    store = tmp_path / "universe"
    store.mkdir()
    ranked = KU.rank_issues([{"code": "000001", "name": "a", "marketCap": 2.0},
                             {"code": "000002", "name": "b", "marketCap": 1.0}])
    HS.write_shard(store / "krx-universe-2013.jsonl.gz",
                   KU.snapshot_rows("2013-01-02", ranked))
    assert CP.universe_tickers(store) == {"000001.KS", "000002.KS"}


def test_an_empty_membership_directory_refuses_rather_than_collecting_everything(
        tmp_path, monkeypatch, capsys):
    """A missing filter must not silently become a decade of the whole exchange."""
    monkeypatch.setenv("KRX_API_KEY", "k")
    (tmp_path / "universe").mkdir()
    assert CP.main([str(tmp_path / "out"), "--universe",
                    str(tmp_path / "universe")]) == 2
    assert "멤버십" in capsys.readouterr().out


def test_no_universe_and_no_all_issues_refuses(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KRX_API_KEY", "k")
    assert CP.main([str(tmp_path / "out")]) == 2
    assert "--all-issues" in capsys.readouterr().out


# ---------------------------------------------------------------- the store

def test_sessions_are_dated_by_what_krx_served(tmp_path, monkeypatch):
    _collect(tmp_path, ["2013-01-02"],
             {"20130102": _session(["000001"], "2013-01-03")}, monkeypatch)
    rows = HS.read_jsonl(tmp_path / "krx-prices-2013.jsonl.gz")
    assert {r["date"] for r in rows} == {"2013-01-03"}


def test_a_rerun_that_collects_nothing_new_writes_no_bytes(tmp_path, monkeypatch):
    responses = {"20130102": _session(["000001"], "2013-01-02")}
    _collect(tmp_path, ["2013-01-02"], responses, monkeypatch)
    shard = tmp_path / "krx-prices-2013.jsonl.gz"
    before = shard.read_bytes()
    second = _collect(tmp_path, ["2013-01-02"], responses, monkeypatch)
    assert second["written"] == [] and shard.read_bytes() == before


def test_rows_are_sharded_by_the_year_they_describe(tmp_path, monkeypatch):
    _collect(tmp_path, ["2013-12-31", "2014-01-02"],
             {"20131231": _session(["000001"], "2013-12-31"),
              "20140102": _session(["000001"], "2014-01-02")}, monkeypatch)
    assert sorted(p.name for p in tmp_path.glob("krx-prices-*.jsonl.gz")) == [
        "krx-prices-2013.jsonl.gz", "krx-prices-2014.jsonl.gz"]


# ---------------------------------------------------------------- the budget

def test_the_call_budget_leaves_the_rest_pending(tmp_path, monkeypatch):
    targets = ["2013-01-02", "2013-01-03", "2013-01-04"]
    responses = {d.replace("-", ""): _session(["000001"], d) for d in targets}
    result = _collect(tmp_path, targets, responses, monkeypatch, max_calls=2)
    assert len(result["sessions"]) == 2 and result["remaining"] == 1


def test_a_second_run_resumes_where_the_budget_stopped(tmp_path, monkeypatch):
    targets = ["2013-01-02", "2013-01-03"]
    responses = {d.replace("-", ""): _session(["000001"], d) for d in targets}
    _collect(tmp_path, targets, responses, monkeypatch, max_calls=1)
    second = _collect(tmp_path, targets, responses, monkeypatch)
    assert second["asked"] == ["20130103"] and second["remaining"] == 0


def test_a_corrupt_done_file_is_read_as_nothing_done(tmp_path):
    (tmp_path / CP.DONE_NAME).write_text("{not json", encoding="utf-8")
    assert CP.load_done(tmp_path) == set()


def test_no_key_refuses_to_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KRX_API_KEY", "")
    assert CP.main([str(tmp_path), "--all-issues"]) == 2
    assert "KRX_API_KEY" in capsys.readouterr().out


def test_the_price_collector_reuses_the_membership_collector_s_transport():
    """One endpoint, one auth header, proven once by Probes run #4.

    A second copy of the transport is a second thing that can drift from what
    was measured.
    """
    assert CP.ENDPOINT == CC.ENDPOINT == "sto/stk_bydd_trd"
    assert CP.AUTH_HEADER == CC.AUTH_HEADER == "AUTH_KEY"
    assert CP.call is CC.call


# ---------------------------------------------------------------- the audit

import audit_krx_prices as AP  # noqa: E402


def _write_bars(store: Path, ticker: str, sessions, volume=10.0):
    """sessions: [(date, close, listed shares)]"""
    by_year: dict[int, list[dict]] = {}
    for date, close, shares in sessions:
        by_year.setdefault(int(date[:4]), []).append({
            "id": f"krx-price:{date}:{ticker[:6]}", "date": date, "region": "KR",
            "ticker": ticker, "open": close, "high": close, "low": close,
            "close": close, "volume": volume, "listedShares": shares})
    store.mkdir(parents=True, exist_ok=True)
    for year, rows in by_year.items():
        HS.write_shard(store / f"krx-prices-{year}.jsonl.gz", rows)


def _quiet(start_date: str, close: float, shares: float, periods: int):
    import pandas as pd
    return [(d.strftime("%Y-%m-%d"), close, shares)
            for d in pd.bdate_range(start_date, periods=periods)]


def test_the_audit_reports_a_detected_split_and_refuses_nothing(tmp_path, capsys):
    _write_bars(tmp_path, "005930.KS",
                [("2018-04-30", 2650000.0, 128386494.0),
                 ("2018-05-02", 2678000.0, 128386494.0),
                 ("2018-05-04", 53000.0, 6419324700.0)]
                + _quiet("2018-05-08", 52900.0, 6419324700.0, 20))
    assert AP.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "액면분할 x50" in out
    assert "검출되지 않은 기업행위의 지문이 남아 있지 않습니다" in out


def test_a_suspended_stretch_is_counted_and_excluded(tmp_path, capsys):
    """The rows stay in the store; the audit says how many are not sessions."""
    _write_bars(tmp_path, "071970.KS",
                [("2017-03-27", 2765.0, 10.0), ("2017-03-28", 2765.0, 10.0)],
                volume=0.0)
    AP.main([str(tmp_path)])
    # Asserted on the whole line: "2행" also appears in the header, so a
    # substring check passes even when the count is never computed.
    line = next(l for l in capsys.readouterr().out.splitlines()
                if l.startswith("거래량 0"))
    assert "2행 (100.0%)" in line


def test_an_unexplained_collapse_refuses_the_ticker_by_name(tmp_path, capsys):
    """The fingerprint the audit exists to surface, and the cost of it.

    A capital reduction or a re-listing moves the printed price with no share
    movement to explain it. The ticker is left out of the panel and named, so
    the gap is measured rather than filled with a fabricated return.
    """
    import pandas as pd

    dates = list(pd.bdate_range("2013-01-02", periods=40))
    _write_bars(tmp_path, "001260.KS",
                [(d.strftime("%Y-%m-%d"), 900.0 if i < 20 else 30600.0,
                  18787617.0) for i, d in enumerate(dates)])
    assert AP.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "001260.KS" in out and "설명되지 않는 변동" in out
    assert "거부 1종목" in out


def test_the_audit_on_an_empty_store_is_not_a_failure(tmp_path, capsys):
    assert AP.main([str(tmp_path)]) == 0
    assert "시세 샤드가 없습니다" in capsys.readouterr().out


def test_the_audit_reports_departed_name_coverage_when_given_membership(
        tmp_path, capsys):
    """The number that decides whether the path was worth finishing."""
    universe = tmp_path / "universe"
    universe.mkdir()
    rows = []
    for date, issues in (("2013-01-02", [("000001", 300.0), ("000002", 200.0)]),
                         ("2016-01-04", [("000001", 300.0)])):
        ranked = KU.rank_issues([{"code": c, "name": c, "marketCap": m}
                                 for c, m in issues])
        rows += KU.snapshot_rows(date, ranked)
    HS.write_shard(universe / "krx-universe-2013.jsonl.gz", rows)

    prices = tmp_path / "prices"
    for ticker in ("000001.KS", "000002.KS"):
        _write_bars(prices, ticker, _quiet("2013-01-02", 1000.0, 10.0, 25))

    assert AP.main([str(prices), "--universe", str(universe)]) == 0
    out = capsys.readouterr().out
    assert "떠난 종목" in out and "FinanceDataReader" in out



# ---------------------------------------------------------- the workflow

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _wf(name: str) -> str:
    # Text, not parsed — a workflow-contract test that needs `pyyaml` passes
    # locally and fails CI with ModuleNotFoundError.
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_the_price_job_reads_the_filter_from_the_membership_job_s_output():
    """Its `--universe` must be the path `kr` writes, or the filter is empty.

    An empty filter is refused by the collector rather than silently collecting
    the exchange, so the failure would be loud — but it would also be a wasted
    run, and the two paths are three lines apart in one file.
    """
    run = _wf("universe.yml")
    assert "prices-work/ledger/universe/kr" in run
    assert "universe-work/ledger/universe/kr" in run
    assert "scripts/collect_krx_daily_prices.py" in run


def test_the_price_job_runs_after_membership_not_beside_it():
    run = _wf("universe.yml")
    job = run.split("  kr-prices:", 1)[1]
    assert job.lstrip().startswith("needs: kr"), job[:120]


def test_the_audit_runs_even_when_the_collection_stopped_early():
    """A budgeted run that stopped still committed bars; they still need looking at."""
    run = _wf("universe.yml")
    audit = run.split("What these bars say", 1)[1][:200]
    assert "if: always()" in audit


def test_no_kr_point_in_time_input_is_wired_while_replay_v15_stands():
    """The seal, covering both halves this time.

    Membership rows redefine the Korean cross-section; KRX bars change which
    Korean names can be priced into it, which redefines it again. Either wired
    into `replay.yml` makes the Korean records already in the generation
    incomparable with the ones that follow, and `universe_conflict` refuses
    exactly that. So both must land in the same commit as the version bump.

    Today neither is wired: the collectors write shards nothing reads, which is
    why this branch leaves v15 intact and costs no reacquisition.
    """
    from pipeline import provenance

    replay = _wf("replay.yml")
    wired = [flag for flag in ("--krx-snapshots", "--krx-prices",
                               "ledger/prices/kr", "ledger/universe/kr")
             if flag in replay]
    assert bool(wired) == (provenance.REPLAY_VERSION != "replay-v15"), (
        f"replay.yml wires {wired or 'nothing'} while REPLAY_VERSION is "
        f"{provenance.REPLAY_VERSION!r}; Korean point-in-time inputs need a new "
        f"generation, not an extension of v15")
