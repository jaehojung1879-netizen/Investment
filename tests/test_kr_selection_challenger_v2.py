"""kr-selection-challenger-v2-accounting with invented inputs only: no market download, no real ledger, no outcome of any real signal."""
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_selection_challenger as V1
from pipeline import kr_selection_challenger_v2 as C
from pipeline import prospective_receipt_core as CORE
from pipeline import replay_calendar as RC

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / C.SPEC_PATH).read_text())
SESSION = "2026-10-30"
EVENING = "2026-10-30T09:30:00+00:00"
SATURDAY = "2026-10-31T04:35:00+00:00"
MERGED = "2026-10-26T03:00:00+00:00"
SECTORS = ["Tech", "Fin", "Energy", "Health", "Ind", "Mat", "Util", "Cons"]


def ticker(i, last="0"):
    return f"{100000 + i * 10:06d}"[:5] + last + ".KS"


def site(n=48, *, generated=EVENING, session=SESSION):
    rows, details = [], {}
    for i in range(n):
        t = ticker(i)
        rows.append({"ticker": t, "sector": SECTORS[i % len(SECTORS)], "alpha": 0.01 * i, "marketCap": 1e12,
                     "risk": {"downsideVolPct": 20.0}})
        details[t] = {"asOf": session, "lastClose": 10000.0, "ma200": 9000.0, "pct52wHigh": 90.0}
    return {"generatedAt": generated, "provenance": {"dataMode": "live", "buildCommitSha": "a" * 40, "modelVersion": "m"},
            "indices": [{"symbol": "^KS11", "asOf": session}], "details": details,
            "longTerm": {"regions": {"KR": {"validationCrossSection": rows, "picks": []}}}}


def filing(t, year, *, available, assets=2e12, liabilities=1e12, ni=5e10, ocf=8e10):
    accounts = {"자산총계": {"amounts": {"thstrm_amount": assets}, "statement": "BS"},
                "부채총계": {"amounts": {"thstrm_amount": liabilities}, "statement": "BS"},
                "당기순이익": {"amounts": {"thstrm_amount": ni}, "statement": "CIS"},
                "영업활동현금흐름": {"amounts": {"thstrm_amount": ocf}, "statement": "CF"}}
    return {"id": f"{t}:{year}:11011", "ticker": t, "fiscalYear": year, "reportCode": "11011", "availableFrom": available,
            "receiptNos": [available.replace("-", "") + "000001"], "fsDiv": "CFS", "accounts": accounts}


def accounting(n=48, **edit):
    """Two annual filings per name. Book equity rises with i (cheaper names), and every fourth name loses money: cheap but unconfirmed."""
    out = {}
    for i in range(n):
        t = ticker(i)
        ni = -5e10 if i % 4 == 0 else 5e10
        out[t] = [filing(t, 2024, available="2025-03-14", ocf=6e10),
                  filing(t, 2025, available="2026-03-16", liabilities=1.9e12 - i * 1.5e10, ni=ni, ocf=8e10)]
    out.update(edit)
    return out


def bars(days=None, *, volume=1e6, close=1e4):
    days = days if days is not None else RC.sessions("2026-05-01", SESSION, "KR")
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": volume}, index=pd.DatetimeIndex(days))


def frames(n=48):
    return {ticker(i): bars() for i in range(n)}


STORE = {"store": C.STORE, "files": {"dart-2026.jsonl.gz": "f" * 64}, "newestAvailableFrom": "2026-09-16"}


def receipt(s=None, acc=None, fr=None, *, created=EVENING, merged=MERGED):
    return C.build_receipt(s or site(), "b" * 64, pathway=C.SYNTHETIC, created_at_utc=created, now_utc=created, merged_at_utc=merged,
                           code_identity={"commitSha": "c" * 40, "files": {"x": "d" * 64}}, spec=SPEC, spec_digest="e" * 64,
                           accounting=acc if acc is not None else accounting(), store_identity=STORE, frames=fr if fr is not None else frames())


# --------------------------------------------------------------------------- #
# Frozen design
# --------------------------------------------------------------------------- #
def test_spec_pins_code_and_registers_the_mechanism_check():
    spec = C.load_spec()
    assert set(spec["codeFileHashes"]) == {"pipeline/kr_selection_challenger_v2.py", "scripts/record_kr_selection_challenger_v2.py"}
    assert spec["schedule"]["firstEligibleSignalSessionFloor"] == "2026-10-30" and spec["horizonsSessions"] == [126, 252]
    assert "CTRL_CHEAP_UNCONFIRMED" in spec["assessment"]["primary"]["rule"] and spec["assessment"]["primary"]["z"] == 1.96
    assert spec["productionEffect"] == "NONE"


def test_a_changed_code_file_refuses_the_spec(tmp_path):
    for rel in [C.SPEC_PATH, *SPEC["codeFileHashes"]]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    C.load_spec(tmp_path)
    (tmp_path / "pipeline/kr_selection_challenger_v2.py").write_text("# edited\n")
    with pytest.raises(ValueError, match="CODE_CHANGED_SINCE_REGISTRATION"):
        C.load_spec(tmp_path)


# --------------------------------------------------------------------------- #
# Books: H2's own rule on point-in-time accounting
# --------------------------------------------------------------------------- #
def test_confirmed_and_unconfirmed_books_follow_the_registered_states():
    r = receipt()
    assert r["readiness"]["ready"] and r["coverage"]["eligible"] == 48
    state = {x["ticker"]: x["state"] for x in r["signal"]}
    confirmed, unconfirmed = r["books"]["CH_VALUE_CONFIRMED"], r["books"]["CTRL_CHEAP_UNCONFIRMED"]
    assert confirmed["slots"] and all(state[s["ticker"]] == "CHEAP_CONFIRMED" for s in confirmed["slots"])
    assert unconfirmed["slots"] and all(state[s["ticker"]] == "CHEAP_UNCONFIRMED" for s in unconfirmed["slots"])
    for blob in r["books"].values():
        sectors = [s["sector"] for s in blob["slots"]]
        assert max(sectors.count(x) for x in sectors) <= 2 and len(blob["slots"]) + blob["fallbackSlots"] == 5
    assert [s["ticker"] for s in r["books"]["CTRL_MODEL5"]["slots"]][0] == ticker(47)
    assert r["accountingStore"]["newestAvailableFrom"] == "2026-09-16" and r["productionEffect"] == "NONE"


def test_a_filing_dated_on_the_signal_day_is_not_yet_visible():
    t = ticker(1)
    late = accounting(**{t: [filing(t, 2024, available="2025-03-14"), filing(t, 2025, available=SESSION)]})
    row = {x["ticker"]: x for x in receipt(acc=late)["signal"]}[t]
    # Only FY2024 is visible: no prior-year OCF, so the confirmation is unmeasured rather than taken from the future filing.
    assert row["state"] in ("CHEAP_CONFIRMATION_UNMEASURED", "NOT_CHEAP", "MISSING_VALUE_INPUT")
    assert row["confirmationFlags"] is None or not all(row["confirmationFlags"].values())


def test_preferred_shares_and_untraded_names_are_ineligible():
    s = site()
    pref = ticker(2, "5")
    s["longTerm"]["regions"]["KR"]["validationCrossSection"][2]["ticker"] = pref
    s["details"][pref] = s["details"].pop(ticker(2))
    fr = frames()
    fr[pref] = fr.pop(ticker(2))
    halted = bars()
    halted.iloc[-3, halted.columns.get_loc("Volume")] = 0.0
    fr[ticker(3)] = halted
    gap = bars().drop(bars().index[-30])
    fr[ticker(4)] = gap
    reasons = {x["ticker"]: x["ineligibility"] for x in receipt(s, fr=fr)["signal"]}
    assert "PREFERRED_SHARE" in reasons[pref]
    assert "NOT_TRADED_EVERY_SESSION_20" in reasons[ticker(3)]
    assert "BELOW_LIQUIDITY_FLOOR" in reasons[ticker(4)] and "NOT_TRADED_EVERY_SESSION_20" not in reasons[ticker(4)]


def test_liquidity_reads_the_calendar_not_the_rows():
    full = bars()
    assert C.liquidity(full, SESSION) == (20, 1e10)
    assert C.liquidity(full.drop(full.index[-1]), SESSION) == (19, None)              # no bar on the signal session: not traded
    assert C.liquidity(None, SESSION) == (None, None)


def test_liquidity_evidence_tells_a_holiday_row_a_missing_session_and_a_halt_apart():
    full = bars()
    holiday = pd.DataFrame({"Open": 1e4, "High": 1e4, "Low": 1e4, "Close": 1e4, "Volume": 1e6}, index=pd.DatetimeIndex(["2026-10-09"]))
    assert len(RC.sessions("2026-10-09", "2026-10-09", "KR")) == 0                      # Hangul Day: KRX closed
    e = C.liquidity_evidence(pd.concat([full, holiday]).sort_index(), SESSION)
    assert e["offCalendarRows"] == 1 and e["basis"] == "ALL_60_TRADED" and e["medianTradedValue60Krw"] == 1e10   # dropped, not a session
    gap = full.drop(full.index[-30])
    e = C.liquidity_evidence(gap, SESSION)
    assert e["states"]["SESSION_MISSING"] == 1 and e["basis"] == "NOT_ALL_60_TRADED" and e["medianTradedValue60Krw"] is None
    assert e["positiveVolumeSessions20"] == 20
    halted = full.copy()
    halted.loc[halted.index[-3], "Volume"] = 0
    e = C.liquidity_evidence(halted, SESSION)
    assert e["states"]["SUSPENDED"] == 1 and e["positiveVolumeSessions20"] == 19
    assert C.liquidity_evidence(None, SESSION)["basis"] == "NO_VENDOR_FRAME"
    assert C.liquidity_evidence(full.iloc[-10:], SESSION)["basis"] == "NOT_ALL_60_TRADED"           # 50 sessions with no row
    # The receipt carries every name's evidence and a cross-section summary.
    fr = frames()
    fr[ticker(1)], fr[ticker(2)] = gap, halted
    r = receipt(fr=fr)
    summary = r["liquidityDiagnostics"]["summary"]
    assert summary["names"] == len(r["signal"]) and summary["median60Measured"] == summary["names"] - 2 - summary["noVendorFrame"]
    assert summary["sessionStates60"]["SESSION_MISSING"] == 1 and summary["sessionStates60"]["SUSPENDED"] == 1
    assert r["liquidityDiagnostics"]["names"][ticker(2)]["positiveVolumeSessions20"] == 19


def test_missing_accounting_blocks_every_book_instead_of_ranking_on_what_is_left():
    acc = {t: rows[:1] for t, rows in accounting().items()}                           # FY2024 only: no prior OCF anywhere
    r = receipt(acc=acc)
    assert not r["readiness"]["ready"]
    assert all(b["status"] == "BLOCKED_COVERAGE" and not b["slots"] and b["fallbackSlots"] == 5 for b in r["books"].values())


def test_a_failed_download_writes_no_receipt():
    with pytest.raises(ValueError, match="PRICE_FETCH_INCOMPLETE"):
        receipt(fr={ticker(i): bars() for i in range(10)})


def test_artifact_and_timing_gates_are_v1s():
    with pytest.raises(ValueError, match="ARTIFACT_NOT_BUILT_ON_A_FINAL_SESSION"):
        receipt(site(generated="2026-10-30T05:00:00+00:00"))
    with pytest.raises(ValueError, match="SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY"):
        receipt(merged="2026-10-30T01:00:00+00:00")
    with pytest.raises(ValueError, match="RECEIPT_PATHWAY_MISMATCH"):
        C.validate_receipt(receipt(), pathway=C.LIVE)


def test_load_accounting_reads_only_the_canonical_store(tmp_path):
    with pytest.raises(ValueError, match="ACCOUNTING_STORE_MISSING"):
        C.load_accounting(tmp_path)
    for store, value in (("kr", 1.0), ("kr-canonical-v2", 2.0)):
        d = tmp_path / "fundamentals" / store
        d.mkdir(parents=True)
        with gzip.open(d / "dart-2025.jsonl.gz", "wt") as fh:
            fh.write(json.dumps({**filing("100000.KS", 2025, available="2026-03-16"), "marker": value}) + "\n")
    by_ticker, identity = C.load_accounting(tmp_path)
    assert by_ticker["100000.KS"][0]["marker"] == 2.0 and identity["newestAvailableFrom"] == "2026-03-16"
    assert identity["store"] == "fundamentals/kr-canonical-v2" and list(identity["files"]) == ["dart-2025.jsonl.gz"]


# --------------------------------------------------------------------------- #
# Outcomes and assessment
# --------------------------------------------------------------------------- #
def test_outcome_uses_v1_arithmetic_on_this_studys_books():
    r = receipt()
    maturity = str(CORE.maturity_session(r["executionDate"], 126).date())
    days = RC.sessions(r["executionDate"], maturity, "KR")
    fr = {}
    for t in {s["ticker"] for b in C.BOOKS for s in r["books"][b]["slots"]} | {C.BENCHMARK}:
        g = 0.10 if t == C.BENCHMARK else 0.0
        fr[t] = bars(days, close=1.0).assign(Close=np.exp(np.linspace(0, np.log(1 + g), len(days))))
    out = C.build_outcome(r, horizon=126, frames=fr, now_utc=pd.Timestamp(maturity).tz_localize("UTC") + pd.Timedelta(hours=10),
                          pathway=C.SYNTHETIC)
    C.validate_outcome(out, pathway=C.SYNTHETIC)
    book = out["books"]["CH_VALUE_CONFIRMED"]
    expected = V1.book_result(r["books"]["CH_VALUE_CONFIRMED"], out["names"], execution=r["executionDate"], maturity=maturity)
    assert book == expected and book["heldExcessReturn"] == pytest.approx(-0.10 * 0.2 * len(r["books"]["CH_VALUE_CONFIRMED"]["slots"]))


def _ledger(n, confirmed, unconfirmed, model=0.0):
    receipts, outcomes = [], []
    for i in range(n):
        sha = f"{i:064x}"
        books = {b: {"slots": [{"ticker": f"{i % 7:06d}.KS"}], "fallbackSlots": 4} for b in C.BOOKS}
        receipts.append({"receiptSha256": sha, "signalDate": str((pd.Timestamp(SESSION) + pd.Timedelta(weeks=i)).date()), "books": books})
        for h in (126, 252):
            outcomes.append({"receiptSha256": sha, "horizonSessions": h, "books": {
                "CH_VALUE_CONFIRMED": {"netExcessReturn": confirmed[i]}, "CTRL_CHEAP_UNCONFIRMED": {"netExcessReturn": unconfirmed},
                "CTRL_MODEL5": {"netExcessReturn": model}}})
    return receipts, outcomes


GOOD = {b: {"status": "COMPLETE", "sharpe": 1.0, "maxDrawdown": -0.2} for b in (*C.BOOKS, "CTRL_ETF")}


def test_the_confirmation_must_pay_for_a_supported_verdict():
    rng = np.random.default_rng(3)
    values = list(0.06 + 0.01 * rng.standard_normal(104))
    receipts, outcomes = _ledger(104, values, unconfirmed=0.0)
    out = C.assess(receipts, outcomes, SPEC, path_metrics=GOOD)["challengers"]["CH_VALUE_CONFIRMED"]
    assert out["verdict"] == "SUPPORTED" and out["primary"]["checks"]["beatsUnconfirmedCheapOnMean"]
    receipts, outcomes = _ledger(104, values, unconfirmed=0.10)                     # cheapness pays, confirmation does not
    out = C.assess(receipts, outcomes, SPEC, path_metrics=GOOD)["challengers"]["CH_VALUE_CONFIRMED"]
    assert out["verdict"] == "NOT_SUPPORTED" and not out["primary"]["checks"]["beatsUnconfirmedCheapOnMean"]
    receipts, outcomes = _ledger(51, values[:51], unconfirmed=0.0)
    assert C.assess(receipts, outcomes, SPEC)["challengers"]["CH_VALUE_CONFIRMED"]["verdict"] == "ACCUMULATING"


# --------------------------------------------------------------------------- #
# The recording path through the paper-ledger step
# --------------------------------------------------------------------------- #
def _ledger_dir(tmp_path):
    ledger = tmp_path / "ledger"
    d = ledger / "fundamentals" / "kr-canonical-v2"
    d.mkdir(parents=True)
    with gzip.open(d / "dart-2025.jsonl.gz", "wt", encoding="utf-8") as fh:
        for rows in accounting().values():
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return ledger


@pytest.mark.parametrize("clock,generated,session,expected", [
    (SATURDAY, "2026-10-31T04:30:00+00:00", SESSION, 1),
    ("2026-11-03T04:35:00+00:00", "2026-11-03T04:30:00+00:00", "2026-11-03", 0),   # weekday intraday artifact
])
def test_actual_recording_path_through_the_paper_ledger_step(tmp_path, monkeypatch, clock, generated, session, expected):
    import importlib
    update = importlib.import_module("scripts.update_ledger")
    v1_script = importlib.import_module("scripts.record_kr_selection_challenger")
    calls = []

    def fake_fetch(tickers, start, **kw):
        if str(start) >= "2026-01-01":                            # the challenger's liquidity download starts 150 days back
            calls.append(len(tickers))
            return frames()
        raise OSError("offline")                                  # the paper ledger's own outcome refresh starts in its history
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fake_fetch)
    monkeypatch.setattr(v1_script, "run_all", lambda *a: 0)
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp(clock))
    data = site(generated=generated, session=session)
    data["modelVersion"] = "m"
    path = tmp_path / "site.json"
    path.write_text(json.dumps(data))
    ledger = _ledger_dir(tmp_path)
    assert update.main([str(path), str(ledger)]) == 0
    study = ledger / "research-strategies" / C.STUDY
    rows = (study / "receipts.jsonl").read_text().splitlines() if (study / "receipts.jsonl").exists() else []
    assert len(rows) == expected
    status = json.loads((study / "publication-status.json").read_text())
    assert {k: v["status"] for k, v in status["steps"].items()} == {
        "record": "RECORDED" if expected else "SKIPPED", "outcomes": "NOTHING_MATURED", "assess": "ASSESSED"}
    assert status["failedSteps"] == [] and status["status"] == "OK"
    if expected:
        assert status["steps"]["record"]["liquidity"]["names"] == len(json.loads(rows[0])["signal"])
    if expected:
        row = json.loads(rows[0])
        C.validate_receipt(row, pathway=C.LIVE)
        assert (row["signalDate"], row["executionDate"]) == (SESSION, "2026-11-02") and row["readiness"]["ready"]
        before, downloads = (study / "receipts.jsonl").read_bytes(), len(calls)
        assert update.main([str(path), str(ledger)]) == 0                       # same window again: no download, no second row
        assert (study / "receipts.jsonl").read_bytes() == before
        assert len(calls) == downloads
    else:
        assert not calls                                                       # an intraday run downloads nothing for the challenger
    assert {p.name for p in (ledger / "research-strategies").iterdir()} == {C.STUDY}


def test_a_refused_record_stays_visible_after_assess_and_the_ledger_is_not_blocked(tmp_path, monkeypatch, capsys):
    """The accounting store is missing: record refuses (an exception inside the step), outcomes and assess still run, the one status file
    keeps the refusal, the paper-ledger step returns 0 and warns."""
    import importlib
    update = importlib.import_module("scripts.update_ledger")
    monkeypatch.setattr(importlib.import_module("scripts.record_kr_selection_challenger"), "run_all", lambda *a: 0)
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp(SATURDAY))
    data = site(generated="2026-10-31T04:30:00+00:00")
    data["modelVersion"] = "m"
    path = tmp_path / "site.json"
    path.write_text(json.dumps(data))
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    assert update.main([str(path), str(ledger)]) == 0
    status = json.loads((ledger / "research-strategies" / C.STUDY / "publication-status.json").read_text())
    assert status["failedSteps"] == ["record"] and status["status"] == "STEP_FAILED" and status["signalRecordState"] == "REFUSED"
    assert status["steps"]["record"]["reason"].startswith("ACCOUNTING_STORE_MISSING")
    assert status["steps"]["assess"]["status"] == "ASSESSED"
    assert "::warning::kr-selection-challenger-v2-accounting research steps exited 1" in capsys.readouterr().out


def test_a_step_exception_is_persisted_and_an_escaped_hook_exception_is_a_status(tmp_path, monkeypatch):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger_v2")
    update = importlib.import_module("scripts.update_ledger")
    monkeypatch.setattr(script, "outcomes", lambda *a: (_ for _ in ()).throw(OSError("vendor down")))
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp(SATURDAY))
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(generated="2026-11-03T04:30:00+00:00", session="2026-11-03")))
    ledger = tmp_path / "ledger"
    assert script.run_all(path, ledger) == 1
    status = json.loads((ledger / "research-strategies" / C.STUDY / "publication-status.json").read_text())
    assert status["failedSteps"] == ["outcomes"] and status["steps"]["outcomes"]["error"] == "OSError: vendor down"
    assert status["steps"]["assess"]["status"] == "ASSESSED"
    monkeypatch.setattr(importlib.import_module("scripts.record_kr_selection_challenger"), "run_all", lambda *a: 0)
    monkeypatch.setattr(script, "run_all", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    data = site()
    data["modelVersion"] = "m"
    path.write_text(json.dumps(data))
    assert update.main([str(path), str(ledger)]) == 0
    hook = json.loads((ledger / "research-strategies" / C.STUDY / "publication-status.json").read_text())
    assert hook["status"] == "STEP_FAILED" and hook["failedSteps"] == ["hook"] and hook["error"] == "RuntimeError: boom"
