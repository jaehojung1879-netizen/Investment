"""SYNTHETIC: shadow ledger -> economic-path-readout-v1 envelope -> core.compare. No vendor, no real ledger."""
from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd
import pytest

from pipeline import entry_state_shadow_ledger as L
from research.economic_path_readout_v1.core import compare
from test_entry_state_shadow_ledger import SUNDAY, observation

KR_SESSIONS = L.region_sessions("KR", "2026-10-30", "2026-11-20")       # 2026-10-30 .. 2026-11-20 XKRX
AFTER = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)


def read(directory, name):
    p = directory / name
    return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []


def frames(stock_scale=1.0, *, through=None, drop=()):
    """Stock rises 1%/session, ETF 0.5%/session; `stock_scale` rescales the whole adjusted history (vendor vintage)."""
    days = [d for d in KR_SESSIONS if through is None or d <= through]
    out = {}
    for ticker, step, scale in (("000001.KS", 1.01, stock_scale), ("069500.KS", 1.005, 1.0)):
        values = [100.0 * step ** i * scale for i in range(len(days))]
        kept = [(d, v) for d, v in zip(days, values) if (ticker, d) not in drop]
        out[ticker] = pd.DataFrame({"Close": [v for _, v in kept]}, index=pd.to_datetime([d for d, _ in kept]))
    return out


def record(directory):
    return L.append_decisions(directory, L.decision_receipts(observation(), recorded_at=SUNDAY, code={"commit": "a"},
                                                             observation_sha256="x"))


def closes_from(directory, acquisition):
    origins = {"000001.KS": "2026-10-30", "069500.KS": "2026-10-30"}
    return L.anchored_closes(acquisition, origins, read(directory, "nav-daily.jsonl"))


def test_envelope_reads_through_the_readout_core_on_its_regional_calendar(tmp_path):
    record(tmp_path)
    L.advance(tmp_path, now=AFTER, close_of=closes_from(tmp_path, frames()), through="2026-11-20")
    pair = L.readout_input(tmp_path, "KR:N1:IN_RANK", "2026-11-21")
    assert pair["benchmark"]["instrument"] == "069500.KS" and pair["candidate"]["calendarPolicy"] == "XKRX"
    summary, _ = compare(pair["candidate"], pair["benchmark"], pair["asOfDate"])
    assert summary["pairedCalendar"]["verified"] is True          # regional sessions, not a KR+US common grid
    assert summary["costBasisMatches"] and summary["economicBasisMatches"]
    assert summary["excessLabel"] == "STORED_NET_NAV_DIFFERENCE_NOT_CERTIFIED_INVESTABLE_ALPHA"
    assert summary["scopes"]["FULL"]["windows"]["H126"]["measuredWindows"] == 0   # immature, never a zero return
    assert summary["investmentConclusion"] == "INSUFFICIENT_SOURCE_EVIDENCE_NO_PROMOTION"
    nav = dict((d, v) for d, v in pair["candidate"]["nav"])
    fill = next(f for f in read(tmp_path, "fills.jsonl") if f["strategyId"] == "KR:N1:IN_RANK")
    assert nav["2026-11-02"] == pytest.approx(fill["postTradeNav"])   # the readout sees the cost exactly once
    # the readout's cumulative return equals the ledger's own NAV ratio: no second deduction anywhere
    full = summary["scopes"]["FULL"]["candidate"]
    assert full["cumulativeReturnPct"] == pytest.approx((nav["2026-11-20"] / nav["2026-11-02"] - 1) * 100)


@pytest.mark.parametrize("scale", [0.5, 2.0, 0.97], ids=["split", "reverse-split", "dividend"])
def test_vendor_rescaling_between_runs_creates_no_profit_or_loss(tmp_path, scale):
    once, twice = tmp_path / "once", tmp_path / "twice"
    for d in (once, twice):
        record(d)
    L.advance(once, now=AFTER, close_of=closes_from(once, frames()), through="2026-11-20")
    L.advance(twice, now=AFTER, close_of=closes_from(twice, frames(through="2026-11-10")), through="2026-11-10")
    L.advance(twice, now=AFTER, close_of=closes_from(twice, frames(scale)), through="2026-11-20")
    a = {(n["strategyId"], n["date"]): n["nav"] for n in read(once, "nav-daily.jsonl")}
    b = {(n["strategyId"], n["date"]): n["nav"] for n in read(twice, "nav-daily.jsonl")}
    assert a.keys() == b.keys() and all(b[k] == pytest.approx(a[k], rel=1e-12) for k in a)


def test_rerun_appends_nothing_and_never_resets_nav(tmp_path):
    record(tmp_path)
    close = closes_from(tmp_path, frames())
    L.advance(tmp_path, now=AFTER, close_of=close, through="2026-11-20")
    before = {name: (tmp_path / name).read_bytes() for name in L.FILES}
    again = L.advance(tmp_path, now=AFTER, close_of=closes_from(tmp_path, frames()), through="2026-11-20")
    assert again["fillsAppended"] == 0 and again["navRowsAppended"] == 0
    assert {name: (tmp_path / name).read_bytes() for name in L.FILES} == before
    report = L.status_report(tmp_path, now=AFTER)["strategies"]["KR:N1:IN_RANK"]
    assert report["fills"] == 1 and report["fillState"] == "FILLED"
    assert report["chargedCostPctOfNav"] > 0 and report["nav"] > 1.0


def test_rereading_the_same_week_later_or_from_newer_code_is_not_a_conflict(tmp_path):
    record(tmp_path)
    monday_after_open = datetime(2026, 11, 2, 3, tzinfo=timezone.utc)      # 12:00 KST Monday
    later = L.decision_receipts(observation(), recorded_at=monday_after_open, code={"commit": "b"},
                                observation_sha256="x")
    assert later[0]["executionSession"] == "2026-11-03"
    report = L.append_decisions(tmp_path, later)
    assert report == {"appended": 0, "alreadyPresent": len(later), "conflictsRefused": []}
    assert all(d["executionSession"] == "2026-11-02" for d in read(tmp_path, "decisions.jsonl"))   # first write kept


def test_quote_not_yet_published_defers_instead_of_stopping(tmp_path):
    record(tmp_path)
    L.advance(tmp_path, now=AFTER, close_of=closes_from(tmp_path, frames(through="2026-11-04")), through="2026-11-20")
    states = L.status_report(tmp_path, now=AFTER)["strategies"]
    assert not [n for n in read(tmp_path, "nav-daily.jsonl") if n["status"] != "MARKED"]
    assert read(tmp_path, "nav-daily.jsonl")[-1]["date"] == "2026-11-04"
    assert states["KR:N1:IN_RANK"]["fillState"] == "FILLED"
    report = L.advance(tmp_path, now=AFTER, close_of=closes_from(tmp_path, frames()), through="2026-11-20")
    assert report["navRowsAppended"] > 0                                   # resumes once the vendor publishes


def test_genuine_gap_inside_published_history_stops_with_an_explicit_row(tmp_path):
    record(tmp_path)
    acquisition = frames(drop={("000001.KS", "2026-11-05")})
    L.advance(tmp_path, now=AFTER, close_of=closes_from(tmp_path, acquisition), through="2026-11-20")
    rank = [n for n in read(tmp_path, "nav-daily.jsonl") if n["strategyId"] == "KR:N1:IN_RANK"]
    assert rank[-1]["status"] == "UNRESOLVED_MISSING_PRICE" and rank[-1]["date"] == "2026-11-05"
    assert L.status_report(tmp_path, now=AFTER)["strategies"]["KR:N1:IN_RANK"]["fillState"].startswith("STOPPED_")
    envelope = L.nav_envelope(tmp_path, "KR:N1:IN_RANK")
    assert envelope["nav"][-1] == ["2026-11-05", None]                     # published as missing, never zero-filled
    etf = [n for n in read(tmp_path, "nav-daily.jsonl") if n["strategyId"] == "KR:ETF_ONLY"]
    assert etf[-1]["date"] == "2026-11-20"                                 # the ETF path does not hold that name


def test_zero_stock_policy_is_a_normal_result(tmp_path):
    record(tmp_path)
    L.advance(tmp_path, now=AFTER, close_of=closes_from(tmp_path, frames()), through="2026-11-20")
    policy = L.status_report(tmp_path, now=AFTER)["strategies"]["KR:CURRENT_POLICY"]
    assert policy["stockCount"] == 0 and policy["etfResidualWeight"] == 1.0 and policy["chargedCostPctOfNav"] == 0
    pair = L.readout_input(tmp_path, "KR:CURRENT_POLICY", "2026-11-21")
    summary, _ = compare(pair["candidate"], pair["benchmark"], pair["asOfDate"])
    assert summary["scopes"]["FULL"]["cagrGapPp"] == pytest.approx(0, abs=1e-9)
