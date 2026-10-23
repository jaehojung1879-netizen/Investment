"""kr-selection-challenger-v2-accounting with invented inputs only: no market download, no real ledger, no outcome of any real signal."""
import gzip
import hashlib
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
    for rel in [C.SPEC_PATH, *SPEC["codeFileHashes"], *C.SCIENTIFIC_FILES]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    C.load_spec(tmp_path)
    (tmp_path / "pipeline/kr_selection_challenger_v2.py").write_text("# edited\n")
    with pytest.raises(ValueError, match="CODE_CHANGED_SINCE_REGISTRATION"):
        C.load_spec(tmp_path)


def test_the_spec_pins_v2s_scientific_dependencies():
    deps = SPEC["scientificDependencies"]
    assert set(deps["fileHashes"]) == set(C.SCIENTIFIC_FILES)
    assert {"pipeline/kr_selection_challenger.py", "pipeline/kr_alpha_signal_v2.py", "pipeline/kr_value_quality_catalyst.py"} <= set(deps["fileHashes"])
    assert deps["conformanceDigest"] == V1.conformance_digest(C.conformance_values())


@pytest.mark.parametrize("rel", ["pipeline/kr_alpha_signal_v2.py", "pipeline/kr_value_quality_catalyst.py", "pipeline/kr_selection_challenger.py",
                                 "pipeline/dart_derive.py"])
def test_an_upstream_rule_file_edit_refuses_v2_while_v2s_own_files_are_unchanged(tmp_path, rel):
    """S2's design, the accounting derivation or v1's outcome code changing under the same v2 studyId is refused."""
    for f in [C.SPEC_PATH, *SPEC["codeFileHashes"], *C.SCIENTIFIC_FILES]:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_bytes((ROOT / f).read_bytes())
    C.load_spec(tmp_path)
    (tmp_path / rel).write_text((tmp_path / rel).read_text() + "\n# a changed rule\n")
    with pytest.raises(ValueError, match="SCIENTIFIC_DEPENDENCY_CHANGED: " + rel):
        C.load_spec(tmp_path)


@pytest.mark.parametrize("patch", [
    lambda m: m.setattr(C.VQ, "ratio", lambda n, d, _f=C.VQ.ratio: None if _f(n, d) is None else _f(n, d) * 1.1),
    lambda m: m.setattr(C.VQ, "accounting_values", lambda r, d, _f=C.VQ.accounting_values: ({}, {"status": "NO_VISIBLE_FILING"})),
    lambda m: m.setattr(C.S2, "MIN_MEDIAN_TRADED_VALUE_KRW", C.S2.MIN_MEDIAN_TRADED_VALUE_KRW * 2),
    lambda m: m.setattr(V1.W, "trade_cost_fraction", lambda *a, _f=V1.W.trade_cost_fraction, **k: _f(*a, **k) + 1e-4),
])
def test_a_changed_behaviour_upstream_refuses_the_live_v2_spec(monkeypatch, patch):
    C.load_spec()
    patch(monkeypatch)
    with pytest.raises(ValueError, match="SCIENTIFIC_DEPENDENCY_CHANGED: conformance"):
        C.load_spec()


def test_the_live_v2_recorder_refuses_under_a_moved_dependency_and_fixtures_stay_isolated(tmp_path, monkeypatch):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger_v2")
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: frames())
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp(SATURDAY))
    monkeypatch.setattr(C.VQ, "ratio", lambda n, d, _f=C.VQ.ratio: None if _f(n, d) is None else _f(n, d) * 2)
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(generated="2026-10-31T04:30:00+00:00")))
    ledger = _ledger_dir(tmp_path)
    assert script.record(path, ledger) == 1
    study = script.study_dir(ledger)
    state = json.loads((study / "publication-status.record.json").read_text())
    assert state["status"] == "REFUSED" and state["reason"] == "SCIENTIFIC_DEPENDENCY_CHANGED: conformance"
    assert not (study / script.RECEIPTS).exists()
    with pytest.raises(ValueError, match="SCIENTIFIC_DEPENDENCY_CHANGED"):
        script.outcomes(ledger)
    assert receipt()["pathway"] == C.SYNTHETIC                                  # fixtures never read the contract


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


# --------------------------------------------------------------------------- #
# Regression tests for the independent-audit P1 findings
# --------------------------------------------------------------------------- #
def test_registration_is_read_from_main_for_this_studys_spec(tmp_path):
    import subprocess

    def git(cwd, *args, date=None):
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
               "PATH": "/usr/bin:/bin", "HOME": str(tmp_path), **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {})}
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()
    origin, clone = tmp_path / "origin", tmp_path / "clone"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / "README").write_text("x")
    git(origin, "add", "README")
    git(origin, "commit", "-qm", "base", date="2026-10-20T00:00:00+00:00")
    (origin / V1.SPEC_PATH).parent.mkdir(parents=True, exist_ok=True)
    (origin / V1.SPEC_PATH).write_text("{}")
    git(origin, "add", ".")
    git(origin, "commit", "-qm", "v1 registered on main", date="2026-10-20T06:00:00+00:00")   # another study's spec IS on main
    git(origin, "checkout", "-qb", "study")
    (origin / C.SPEC_PATH).write_text("{}")
    git(origin, "add", ".")
    git(origin, "commit", "-qm", "v2 spec", date="2026-10-21T00:00:00+00:00")
    git(tmp_path, "clone", "-q", "--no-local", str(origin), str(clone))
    git(clone, "checkout", "-q", "study")
    with pytest.raises(ValueError, match="SPEC_NOT_ON_MAIN"):
        C.merged_at_from_git(clone)
    git(origin, "checkout", "-q", "main")
    git(origin, "merge", "-q", "--no-ff", "study", "-m", "merge", date="2026-10-28T03:00:00+00:00")
    git(clone, "fetch", "-q", "origin")
    git(clone, "checkout", "-q", "-B", "main", "origin/main")
    assert pd.Timestamp(C.merged_at_from_git(clone)) == pd.Timestamp("2026-10-28T03:00:00+00:00")   # git >= 2.55 spells UTC "Z"


def test_a_stale_download_is_not_a_collected_name_and_writes_no_receipt():
    """Frames that exist but stop before the signal session (the vendor has not served Friday yet) are not a collection."""
    stale = {ticker(i): bars(RC.sessions("2026-05-01", "2026-10-29", "KR")) for i in range(48)}
    e = C.liquidity_evidence(stale[ticker(0)], SESSION)
    assert e["signalSessionRow"] is False and e["states"]["SESSION_MISSING"] == 1 and e["medianTradedValue60Krw"] is None
    with pytest.raises(ValueError, match="PRICE_FETCH_INCOMPLETE: 0 of 48 names have a vendor row on the signal session"):
        receipt(fr=stale)
    half = {**stale, **{ticker(i): bars() for i in range(24)}}
    r = receipt(fr=half)                                                    # exactly half collected: recorded, the rest excluded
    assert r["liquidityDiagnostics"]["summary"]["signalSessionRowPresent"] == 24
    assert all("NOT_TRADED_EVERY_SESSION_20" in x["ineligibility"] or "BELOW_LIQUIDITY_FLOOR" in x["ineligibility"]
               for x in r["signal"] if x["ticker"] in {ticker(i) for i in range(24, 48)})


def test_traded_value_is_the_as_traded_close_times_volume_and_is_fetched_unadjusted(tmp_path, monkeypatch):
    """A split is consistent in close and volume and cancels; a dividend-adjusted close would scale earlier sessions down."""
    days = RC.sessions("2026-05-01", SESSION, "KR")
    traded = bars(days, volume=1e6, close=1e4)
    split = traded.copy()
    split.loc[split.index[:30], "Close"] *= 2.0
    split.loc[split.index[:30], "Volume"] /= 2.0                          # a 2:1 split mid-window, on the vendor's consistent basis
    assert C.liquidity_evidence(split, SESSION)["medianTradedValue60Krw"] == C.liquidity_evidence(traded, SESSION)["medianTradedValue60Krw"]
    adjusted = traded.copy()
    adjusted.loc[adjusted.index[:-10], "Close"] *= 0.97                     # what a dividend-adjusted close looks like before an ex-date
    assert C.liquidity_evidence(adjusted, SESSION)["medianTradedValue60Krw"] < 1e10
    assert C.LIQUIDITY_FETCH == {"auto_adjust": False} and receipt()["liquidityDiagnostics"]["summary"]["tradedValueBasis"] == \
        "AS_TRADED_CLOSE_X_VOLUME_SPLIT_CONSISTENT_NOT_DIVIDEND_ADJUSTED"
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger_v2")
    seen = []

    def fake_fetch(tickers, start, **kw):
        seen.append(kw)
        return frames()
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fake_fetch)
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp(SATURDAY))
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(generated="2026-10-31T04:30:00+00:00")))
    assert script.record(path, _ledger_dir(tmp_path)) == 0
    assert seen == [{"auto_adjust": False}]


def test_every_series_including_the_mechanism_control_must_be_within_the_none_budget():
    rng = np.random.default_rng(3)
    values = list(0.06 + 0.01 * rng.standard_normal(104))
    receipts, outcomes = _ledger(104, values, unconfirmed=0.0)
    for o in outcomes:
        if int(o["receiptSha256"], 16) >= 2 and o["horizonSessions"] == 252:
            o["books"]["CTRL_CHEAP_UNCONFIRMED"]["netExcessReturn"] = None     # the mechanism pairs valid on two receipts only
    out = C.assess(receipts, outcomes, SPEC, path_metrics=GOOD)["challengers"]["CH_VALUE_CONFIRMED"]
    assert out["verdict"] == "INCONCLUSIVE_DATA" and out["primary"]["seriesShortOfCohort"] == ["versusUnconfirmedCheap"]
    bad = {**GOOD, "CH_VALUE_CONFIRMED": {"status": "COMPLETE", "sharpe": None, "maxDrawdown": -0.2}}
    receipts, outcomes = _ledger(104, values, unconfirmed=0.0)
    assert C.assess(receipts, outcomes, SPEC, path_metrics=bad)["challengers"]["CH_VALUE_CONFIRMED"]["verdict"] == "INCONCLUSIVE_DATA"


def test_a_vendor_outage_defers_the_outcome_and_the_next_run_grades_it(tmp_path, monkeypatch):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger_v2")
    ledger = _ledger_dir(tmp_path)
    study = script.study_dir(ledger)
    live = C.build_receipt(site(), "b" * 64, pathway=C.LIVE, created_at_utc=EVENING, now_utc=EVENING, merged_at_utc=MERGED,
                           code_identity={"commitSha": "c" * 40, "files": {"x": "d" * 64}}, spec=SPEC, spec_digest="e" * 64,
                           accounting=accounting(), store_identity=STORE, frames=frames())
    C.append_receipt(study / script.RECEIPTS, live, pathway=C.LIVE)
    maturity = str(CORE.maturity_session(live["executionDate"], 126).date())
    days = RC.sessions(live["executionDate"], maturity, "KR")
    fr = {t: bars(days) for t in {s["ticker"] for b in C.BOOKS for s in live["books"][b]["slots"]} | {C.BENCHMARK}}
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp(maturity).tz_localize("UTC") + pd.Timedelta(hours=10))
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: {})
    assert script.outcomes(ledger) == 0
    assert json.loads((study / "publication-status.outcomes.json").read_text())["status"] == "DEFERRED"
    assert C.read_outcomes(study / script.OUTCOMES, pathway=C.LIVE) == []
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: fr)
    assert script.outcomes(ledger) == 0
    assert [o["resolution"] for o in C.read_outcomes(study / script.OUTCOMES, pathway=C.LIVE)] == ["FINAL"]
    out = C.build_outcome(live, horizon=126, frames={}, now_utc=pd.Timestamp(maturity).tz_localize("UTC") + pd.Timedelta(hours=10),
                          pathway=C.LIVE)
    with pytest.raises(ValueError, match="OUTCOME_DEFERRED_IS_NEVER_A_RECORD"):
        C.validate_outcome(out, pathway=C.LIVE)


def test_a_seven_session_provider_outage_stays_pending_and_is_graded_on_recovery(tmp_path, monkeypatch):
    """D0 is the maturity session; the vendor serves nothing from D0 to D6 (past the +5 window) and recovers on D7. The old rule wrote
    a permanent None on D6; v1's provider/economic split keeps it pending and grades it on D7."""
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger_v2")
    ledger = _ledger_dir(tmp_path)
    study = script.study_dir(ledger)
    live = C.build_receipt(site(), "b" * 64, pathway=C.LIVE, created_at_utc=EVENING, now_utc=EVENING, merged_at_utc=MERGED,
                           code_identity={"commitSha": "c" * 40, "files": {"x": "d" * 64}}, spec=SPEC, spec_digest="e" * 64,
                           accounting=accounting(), store_identity=STORE, frames=frames())
    C.append_receipt(study / script.RECEIPTS, live, pathway=C.LIVE)
    maturity = str(CORE.maturity_session(live["executionDate"], 126).date())
    fr = {t: bars(RC.sessions(live["executionDate"], maturity, "KR"))
          for t in {s["ticker"] for b in C.BOOKS for s in live["books"][b]["slots"]} | {C.BENCHMARK}}

    def at(day):
        return pd.Timestamp(str(CORE.maturity_session(live["executionDate"], 126 + day).date())).tz_localize("UTC") + pd.Timedelta(hours=10)
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: {})
    for day in range(7):
        monkeypatch.setattr(CORE, "system_utc_now", lambda d=day: at(d))
        assert script.outcomes(ledger) == 0
        pending = json.loads((study / "outcome-pending.json").read_text())["pending"]
        assert [p["attempts"] for p in pending] == [day + 1] and pending[0]["unresolvedClasses"] == ["PROVIDER_DATA_UNAVAILABLE"]
        assert C.read_outcomes(study / script.OUTCOMES, pathway=C.LIVE) == []
    late = C.build_outcome(live, horizon=126, frames={}, now_utc=at(6), pathway=C.LIVE)
    forced = {**late, "resolution": "FINAL_UNRESOLVED_AFTER_RETRY"}
    forced["recordSha256"] = hashlib.sha256(CORE.canonical({k: v for k, v in forced.items() if k != "recordSha256"})).hexdigest()
    with pytest.raises(ValueError, match="OUTCOME_PROVIDER_GAP_IS_NEVER_FINAL"):
        C.validate_outcome(forced, pathway=C.LIVE)
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: fr)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: at(7))
    assert script.outcomes(ledger) == 0
    assert [o["resolution"] for o in C.read_outcomes(study / script.OUTCOMES, pathway=C.LIVE)] == ["FINAL"]
    assert json.loads((study / "outcome-pending.json").read_text())["pending"] == []


def test_the_risk_path_holds_a_name_suspended_at_rebalance_in_the_benchmark_for_v2_books():
    """v2's assessment uses V1.paper_path: a chosen name with a served zero-volume row on a rebalance session is held as 069500.KS, the
    same reading as the cohort outcome; a missing row on that session still makes the path INCOMPLETE."""
    sessions = [d for d in RC.sessions("2026-10-30", "2027-03-31", "KR") if CORE.is_weekly_decision_session(d)][:9]
    receipts = [{"signalDate": str(d.date()), "executionDate": str(CORE.next_kr_session(d).date()),
                 "books": {b: {"slots": [{"ticker": ["000001.KS", "000002.KS"][i // 4 % 2]}], "fallbackSlots": 4} for b in C.BOOKS}}
                for i, d in enumerate(sessions)]
    days = RC.sessions(receipts[0]["executionDate"], receipts[8]["executionDate"], "KR")
    flat = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1.0}, index=pd.DatetimeIndex(days))
    entry = pd.Timestamp(receipts[4]["executionDate"])
    halted = flat.copy()
    halted.loc[entry, "Volume"] = 0.0
    frames = {"000001.KS": flat, "000002.KS": halted, C.BENCHMARK: flat}
    path = V1.paper_path(receipts, frames, "CH_VALUE_CONFIRMED", every=4, end_receipt=8)
    assert path["status"] == "COMPLETE"
    same = V1.paper_path([{**r, "books": {b: {"slots": [], "fallbackSlots": 5} for b in C.BOOKS}} if 4 <= i < 8 else r
                          for i, r in enumerate(receipts)], frames, "CH_VALUE_CONFIRMED", every=4, end_receipt=8)
    assert (path["annualReturn"], path["maxDrawdown"]) == (same["annualReturn"], same["maxDrawdown"])
    gap = {**frames, "000002.KS": flat.drop(entry)}
    assert V1.paper_path(receipts, gap, "CH_VALUE_CONFIRMED", every=4, end_receipt=8)["status"] == "INCOMPLETE"


def test_the_v2_risk_path_counts_the_opening_cost_in_drawdown_and_volatility():
    """v2's assessment reads V1.paper_path: one opening purchase with positive fees and no later turnover on flat prices is a real
    loss in Sharpe and max drawdown for each v2 book and for the ETF control, each against its own opening fee, charged once."""
    sessions = [d for d in RC.sessions("2026-10-30", "2027-03-31", "KR") if CORE.is_weekly_decision_session(d)][:9]
    receipts = [{"signalDate": str(d.date()), "executionDate": str(CORE.next_kr_session(d).date()),
                 "books": {b: {"slots": [{"ticker": "000001.KS"}], "fallbackSlots": 4} for b in C.BOOKS}} for d in sessions]
    days = RC.sessions(receipts[0]["executionDate"], receipts[8]["executionDate"], "KR")
    flat = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1.0}, index=pd.DatetimeIndex(days))
    frames = {"000001.KS": flat, C.BENCHMARK: flat}
    entry = receipts[0]["executionDate"]
    leg = lambda bench: V1._leg(entry, is_benchmark=bench, side="buy")   # noqa: E731
    for book in [b for b in C.BOOKS if b != "CTRL_ETF"] + ["CTRL_ETF"]:
        cost = leg(True) if book == "CTRL_ETF" else 0.2 * leg(False) + 0.8 * leg(True)
        path = V1.paper_path(receipts, frames, book, every=9, end_receipt=8)
        assert path["status"] == "COMPLETE" and cost > 0
        assert path["maxDrawdown"] == pytest.approx(-cost, rel=1e-12)
        assert path["annualReturn"] == pytest.approx((1 - cost) ** (252 / (len(days) - 1)) - 1, rel=1e-12)
        assert path["annualVolatility"] == pytest.approx(
            float(np.std([-cost] + [0.0] * (len(days) - 2), ddof=1) * np.sqrt(252)), rel=1e-9)
        assert path["sharpe"] < 0


def test_an_unknown_volume_is_never_a_traded_liquidity_session():
    """kr_bar_integrity's VOLUME_INVALID (missing / NaN / inf volume) is not a traded session: the 60-session median does not exist and
    the state is tallied, not hidden; a stated zero is still SUSPENDED."""
    days = RC.sessions("2026-05-01", SESSION, "KR")
    frame = bars(days).astype({"Volume": object})
    frame.loc[days[-5], "Volume"] = float("nan")
    frame.loc[days[-6], "Volume"] = None
    frame.loc[days[-7], "Volume"] = 0.0
    e = C.liquidity_evidence(frame, SESSION)
    assert e["states"]["VOLUME_INVALID"] == 2 and e["states"]["SUSPENDED"] == 1
    assert e["medianTradedValue60Krw"] is None and e["positiveVolumeSessions20"] == 17 and e["basis"] == "NOT_ALL_60_TRADED"


@pytest.mark.parametrize("finished,recorded", [
    ("2026-11-01T23:59:30Z", True), ("2026-11-02T00:00:00Z", False), ("2026-11-02T00:01:00Z", False),
])
def test_the_v2_receipt_window_is_decided_by_the_clock_at_the_write(tmp_path, monkeypatch, finished, recorded):
    """A run that starts at 08:59 KST on the execution session's morning and finishes its downloads at 08:59:30, exactly 09:00 or 09:01."""
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger_v2")
    state = {"now": pd.Timestamp("2026-11-01T23:59:00Z")}

    def fetch(tickers, start, **kw):
        state["now"] = pd.Timestamp(finished)
        return frames()
    monkeypatch.setattr(CORE, "system_utc_now", lambda: state["now"])
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch)
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(generated="2026-10-31T04:30:00+00:00")))
    ledger = _ledger_dir(tmp_path)
    study = script.study_dir(ledger)
    code = script.record(path, ledger)
    status = json.loads((study / "publication-status.record.json").read_text())
    if recorded:
        assert code == 0 and status["status"] == "RECORDED"
        (row,) = C.read_receipts(study / script.RECEIPTS, pathway=C.LIVE)
        assert pd.Timestamp(row["createdAtUtc"]) == pd.Timestamp(finished) and row["receiptSha256"] == CORE.receipt_digest(row)
        before = (study / script.RECEIPTS).read_bytes()
        state["now"] = pd.Timestamp("2026-11-01T23:59:50Z")            # a later attempt in or after the window changes nothing
        assert script.record(path, ledger) == 0 and (study / script.RECEIPTS).read_bytes() == before
    else:
        assert code == 1 and status["status"] == "REFUSED"
        assert status["reason"].startswith(V1.WINDOW_CLOSED_DURING_RECORDING) and not (study / script.RECEIPTS).exists()
