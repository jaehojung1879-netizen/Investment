"""kr-selection-challenger-v1 with invented inputs only: no market download, no real ledger, no outcome of any real signal."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_bar_integrity as BI
from pipeline import kr_selection_challenger as C
from pipeline import prospective_receipt_core as CORE
from pipeline import replay_calendar as RC

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / C.SPEC_PATH).read_text())
SESSION = "2026-10-30"                      # Friday: a weekly decision session
EVENING = "2026-10-30T09:30:00+00:00"       # 18:30 KST, after finality
MERGED = "2026-10-26T03:00:00+00:00"
SECTORS = ["Tech", "Fin", "Energy", "Health", "Ind", "Mat", "Util", "Cons"]


def site(n=50, *, generated=EVENING, session=SESSION, **edit):
    rows, details = [], {}
    for i in range(n):
        t = f"{100000 + i:06d}.KS"
        rows.append({"ticker": t, "sector": SECTORS[i % len(SECTORS)], "alpha": 0.01 * i,
                     "risk": {"downsideVolPct": 10.0 + i}})
        details[t] = {"asOf": session, "lastClose": 1000.0 + i, "ma200": 900.0 if i % 3 else 1100.0, "pct52wHigh": 60.0 + i / 2}
    out = {"generatedAt": generated, "provenance": {"dataMode": "live", "buildCommitSha": "a" * 40, "modelVersion": "m"},
           "indices": [{"symbol": "^KS11", "asOf": session}], "details": details,
           "longTerm": {"regions": {"KR": {"validationCrossSection": rows, "picks": [{"ticker": rows[-1]["ticker"]}]}}}}
    out.update(edit)
    return out


def receipt(s=None, *, created=EVENING, merged=MERGED):
    s = s or site()
    return C.build_receipt(s, "b" * 64, pathway=C.SYNTHETIC, created_at_utc=created, now_utc=created, merged_at_utc=merged,
                           code_identity={"commitSha": "c" * 40, "files": {"pipeline/kr_selection_challenger.py": "d" * 64}},
                           spec=SPEC, spec_digest="e" * 64)


# --------------------------------------------------------------------------- #
# Frozen design
# --------------------------------------------------------------------------- #
def test_spec_pins_every_code_file_and_the_registered_rules():
    spec = C.load_spec()
    assert set(spec["codeFileHashes"]) == {"pipeline/kr_selection_challenger.py", "pipeline/kr_bar_integrity.py",
                                           "scripts/record_kr_selection_challenger.py"}
    assert spec["horizonsSessions"] == [126, 252] and spec["assessment"]["primary"]["horizonSessions"] == 252
    assert spec["construction"] == {**spec["construction"], "slots": 5, "slotFraction": 0.2, "maxNamesPerSector": 2,
                                    "minEligibleNames": 30}
    assert spec["productionEffect"] == "NONE" and spec["evidenceClass"] == "PROSPECTIVE_PAPER"
    assert abs(spec["assessment"]["primary"]["z"] - 2.2414) < 1e-4  # one-sided 0.025 / two challengers


def test_a_changed_code_file_refuses_the_spec(tmp_path):
    for rel in [C.SPEC_PATH, *SPEC["codeFileHashes"]]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    C.load_spec(tmp_path)
    (tmp_path / "pipeline/kr_selection_challenger.py").write_text("# edited\n")
    with pytest.raises(ValueError, match="CODE_CHANGED_SINCE_REGISTRATION"):
        C.load_spec(tmp_path)


# --------------------------------------------------------------------------- #
# Books from signal-time facts only
# --------------------------------------------------------------------------- #
def test_books_follow_the_registered_order_and_sector_cap():
    books, universe = C.build_books(site(), SESSION, SPEC)
    assert universe["crossSectionNames"] == 50
    low = [s["ticker"] for s in books["CH_LOWVOL"]["slots"]]
    assert low == ["100000.KS", "100001.KS", "100002.KS", "100003.KS", "100004.KS"]
    model = books["CTRL_MODEL5"]["slots"]
    assert [s["ticker"] for s in model] == ["100049.KS", "100048.KS", "100047.KS", "100046.KS", "100045.KS"]
    high = books["CH_HIGH52"]
    assert all(int(s["ticker"][-5:-3]) % 3 for s in high["slots"])  # below-MA200 names excluded
    assert high["excluded"]["BELOW_200_DAY_AVERAGE"] == 17 and high["status"] == "BOOK_FORMED"
    for blob in books.values():
        sectors = [s["sector"] for s in blob["slots"]]
        assert max(sectors.count(x) for x in sectors) <= 2 and len(blob["slots"]) + blob["fallbackSlots"] == 5


def test_sector_cap_skips_to_the_next_name_in_rank_order():
    s = site()
    for row in s["longTerm"]["regions"]["KR"]["validationCrossSection"][:3]:
        row["sector"] = "Same"
    low = C.build_books(s, SESSION, SPEC)[0]["CH_LOWVOL"]["slots"]
    assert [x["ticker"] for x in low] == ["100000.KS", "100001.KS", "100003.KS", "100004.KS", "100005.KS"]


def test_missing_values_exclude_a_name_from_its_book_only_and_are_counted():
    s = site()
    s["longTerm"]["regions"]["KR"]["validationCrossSection"][0]["risk"]["downsideVolPct"] = None
    s["details"]["100001.KS"]["asOf"] = "2026-10-29"                  # stale quote
    s["details"]["100002.KS"]["ma200"] = None                         # 200-day average undetermined
    s["longTerm"]["regions"]["KR"]["validationCrossSection"][3]["alpha"] = True   # a bool is not a number
    books, universe = C.build_books(s, SESSION, SPEC)
    assert universe["excluded"]["QUOTE_NOT_ON_SIGNAL_SESSION"] == 1
    assert books["CH_LOWVOL"]["excluded"]["FEATURE_MISSING"] == 1
    assert books["CH_HIGH52"]["excluded"]["MA200_UNDETERMINED"] == 1
    assert books["CTRL_MODEL5"]["excluded"]["FEATURE_MISSING"] == 1
    assert [x["ticker"] for x in books["CH_LOWVOL"]["slots"]][0] == "100002.KS"


def test_a_thin_cross_section_holds_the_benchmark_only():
    books, _ = C.build_books(site(n=29), SESSION, SPEC)
    assert all(b["status"] == "THIN_CROSS_SECTION" and not b["slots"] and b["fallbackSlots"] == 5 for b in books.values())


# --------------------------------------------------------------------------- #
# Timing and identity
# --------------------------------------------------------------------------- #
def test_receipt_is_sealed_and_says_it_has_no_production_effect():
    r = receipt()
    assert r["signalDate"] == SESSION and r["executionDate"] == "2026-11-02"
    assert r["receiptSha256"] == CORE.receipt_digest(r) and r["productionEffect"] == "NONE"
    assert r["evidenceClass"] == "SYNTHETIC_FIXTURE" and r["authorization"]["firstProspectiveSession"] == "2026-10-27"
    assert r["productionResearchPicks"] == ["100049.KS"]
    text = json.dumps(r).lower()
    assert "weight" not in text and "forward" not in text and "outcome" not in text


@pytest.mark.parametrize("generated,session,error", [
    ("2026-10-30T05:00:00+00:00", SESSION, "ARTIFACT_NOT_BUILT_ON_A_FINAL_SESSION"),   # built inside the session
    ("2026-10-29T09:30:00+00:00", "2026-10-29", "NOT_A_WEEKLY_DECISION_SESSION"),       # Thursday
])
def test_only_a_finished_weekly_session_can_be_recorded(generated, session, error):
    with pytest.raises(ValueError, match=error):
        receipt(site(generated=generated, session=session), created=EVENING)


@pytest.mark.parametrize("created,merged,error", [
    ("2026-10-30T08:59:00+00:00", MERGED, "RECEIPT_CREATED_BEFORE_SIGNAL_CLOSE"),
    ("2026-11-02T00:00:00+00:00", MERGED, "RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED"),
    (EVENING, "2026-10-30T01:00:00+00:00", "SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY"),     # merged the same KST day
])
def test_timing_and_eligibility_refusals(created, merged, error):
    with pytest.raises(ValueError, match=error):
        receipt(created=created, merged=merged)


def test_registered_floor_and_unsafe_artifacts_refuse():
    early = site(generated="2026-10-23T09:30:00+00:00", session="2026-10-23")
    with pytest.raises(ValueError, match="SIGNAL_BEFORE_REGISTERED_FLOOR"):
        receipt(early, created="2026-10-23T09:30:00+00:00", merged="2026-10-01T00:00:00+00:00")
    with pytest.raises(ValueError, match="UNSAFE_ARTIFACT"):
        receipt(site(seed=True))


def test_ledger_is_append_only_and_pathways_never_mix(tmp_path):
    r = receipt()
    path = tmp_path / "receipts.jsonl"
    C.append_receipt(path, r, pathway=C.SYNTHETIC)
    with pytest.raises(ValueError, match="RECEIPT_ALREADY_EXISTS"):
        C.append_receipt(path, r, pathway=C.SYNTHETIC)
    with pytest.raises(ValueError, match="RECEIPT_PATHWAY_MISMATCH"):
        C.append_receipt(tmp_path / "live.jsonl", r, pathway=C.LIVE)
    tampered = dict(r, books={**r["books"]})
    tampered["books"]["CH_LOWVOL"] = {**r["books"]["CH_LOWVOL"], "slots": r["books"]["CH_LOWVOL"]["slots"][:4]}
    with pytest.raises(ValueError, match="RECEIPT_DIGEST_MISMATCH"):
        C.validate_receipt(tampered, pathway=C.SYNTHETIC)


# --------------------------------------------------------------------------- #
# Outcomes
# --------------------------------------------------------------------------- #
def _frames(r, horizon, *, growth=None, edit=None):
    maturity = CORE.maturity_session(r["executionDate"], horizon)
    days = RC.sessions(r["executionDate"], str(maturity.date()), "KR")
    tickers = {s["ticker"] for b in C.BOOKS for s in r["books"][b]["slots"]} | {C.BENCHMARK}
    frames = {}
    for t in sorted(tickers):
        g = (growth or {}).get(t, 0.0)
        close = 100.0 * np.exp(np.linspace(0, np.log(1 + g), len(days)))
        frames[t] = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1000.0},
                                 index=pd.DatetimeIndex(days))
    for t, fn in (edit or {}).items():
        fn(frames, t)
    return frames, str(maturity.date())


def _after(maturity):
    return pd.Timestamp(maturity).tz_localize("UTC") + pd.Timedelta(hours=10)


def test_outcome_waits_for_the_maturity_session_and_charges_both_legs():
    r = receipt()
    low = [s["ticker"] for s in r["books"]["CH_LOWVOL"]["slots"]]
    frames, maturity = _frames(r, 126, growth={C.BENCHMARK: 0.10, **{t: 0.20 for t in low}})
    with pytest.raises(ValueError, match="HORIZON_NOT_MATURED"):
        C.build_outcome(r, horizon=126, frames=frames, now_utc=pd.Timestamp(maturity).tz_localize("UTC"), pathway=C.SYNTHETIC)
    out = C.build_outcome(r, horizon=126, frames=frames, now_utc=_after(maturity), pathway=C.SYNTHETIC)
    book = out["books"]["CH_LOWVOL"]
    leg = lambda bench, side, day: C.W.trade_cost_fraction("KR", day, is_benchmark=bench, side=side)
    stock = leg(False, "buy", r["executionDate"]) + leg(False, "sell", maturity)
    etf = leg(True, "buy", r["executionDate"]) + leg(True, "sell", maturity)   # the ETF control pays its own round trip
    assert stock > etf > 0
    assert book["status"] == "COMPLETE" and abs(book["heldExcessReturn"] - 0.10) < 1e-9
    assert abs(book["netExcessReturn"] - (0.10 - stock + etf)) < 1e-12
    assert out["books"]["CTRL_MODEL5"]["netExcessReturn"] == pytest.approx(-0.10 - stock + etf)
    assert out["recordSha256"] == hashlib.sha256(CORE.canonical({k: v for k, v in out.items() if k != "recordSha256"})).hexdigest()
    C.validate_outcome(out, pathway=C.SYNTHETIC)
    with pytest.raises(ValueError, match="OUTCOME_PATHWAY_MISMATCH"):
        C.validate_outcome(out, pathway=C.LIVE)
    with pytest.raises(ValueError, match="OUTCOME_DIGEST_MISMATCH"):
        C.validate_outcome({**out, "benchmarkReturn": 0.5}, pathway=C.SYNTHETIC)


def test_unpriceable_names_make_the_book_outcome_none_never_a_last_price():
    r = receipt()
    a, b, c = (s["ticker"] for s in r["books"]["CH_LOWVOL"]["slots"][:3])

    def halt_at_maturity(f, t):
        f[t].iloc[-1, f[t].columns.get_loc("Volume")] = 0.0

    def gone(f, t):
        del f[t]

    def suspended_at_entry(f, t):
        f[t].iloc[0, f[t].columns.get_loc("Volume")] = 0.0
    frames, maturity = _frames(r, 126, edit={a: halt_at_maturity})
    out = C.build_outcome(r, horizon=126, frames=frames, now_utc=_after(maturity), pathway=C.SYNTHETIC)
    assert out["names"][a]["state"] == "TERMINAL_ECONOMICS_UNRESOLVED" and out["books"]["CH_LOWVOL"]["netExcessReturn"] is None
    frames, _ = _frames(r, 126, edit={b: gone})
    out = C.build_outcome(r, horizon=126, frames=frames, now_utc=_after(maturity), pathway=C.SYNTHETIC)
    assert out["names"][b]["state"] == "NAME_OUTCOME_MISSING" and out["books"]["CH_LOWVOL"]["netExcessReturn"] is None
    frames, _ = _frames(r, 126, edit={c: suspended_at_entry})
    out = C.build_outcome(r, horizon=126, frames=frames, now_utc=_after(maturity), pathway=C.SYNTHETIC)
    book = out["books"]["CH_LOWVOL"]
    assert out["names"][c]["state"] == C.NOT_EXECUTABLE and book["heldAsBenchmarkFraction"] == pytest.approx(0.2)


def test_a_traded_row_with_a_zero_range_keeps_its_close_only():
    r = receipt()
    t = r["books"]["CH_LOWVOL"]["slots"][0]["ticker"]

    def zero_range(f, ticker):
        for col in ("Open", "High", "Low"):
            f[ticker].iloc[-1, f[ticker].columns.get_loc(col)] = 0.0
    frames, maturity = _frames(r, 126, edit={t: zero_range})
    out = C.build_outcome(r, horizon=126, frames=frames, now_utc=_after(maturity), pathway=C.SYNTHETIC)
    assert out["names"][t]["state"] == "PRICED"


# --------------------------------------------------------------------------- #
# Integrity reader (Task 3: audit defects of the KRX store, read side)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("row,state", [
    ((100, 101, 99, 100, 10), "VALID"),
    ((0, 0, 0, 100, 23370), "RANGE_UNRESOLVED"),      # the eight traded zero-OHL rows of the 2026-10-21 audit
    ((0, 0, 0, 100, 0), "SUSPENDED"),
    ((100, 99, 101, 100, 10), "RANGE_UNRESOLVED"),    # low above high
    ((100, 101, 99, float("nan"), 10), "CLOSE_INVALID"),
    ((100, 101, 99, 100, -1), "CLOSE_INVALID"),
    ((100, float("inf"), 99, 100, 10), "RANGE_UNRESOLVED"),
])
def test_row_states(row, state):
    assert BI.classify_row(*row) == state


def test_calendar_alignment_marks_missing_sessions_instead_of_stretching_windows():
    days = RC.sessions("2026-09-08", "2026-09-22", "KR")
    keep = [d for d in days if str(d.date()) not in ("2026-09-15", "2026-09-16")]
    frame = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0},
                         index=pd.DatetimeIndex(keep + [pd.Timestamp("2026-09-13")]))   # a Sunday row
    aligned = BI.calendar_frame(frame)
    assert list(aligned.loc[["2026-09-15", "2026-09-16"], "state"]) == ["SESSION_MISSING"] * 2
    assert aligned.attrs["offCalendarRows"] == 1
    assert not BI.window_complete(aligned, "2026-09-18", 5) and BI.window_complete(aligned, "2026-09-14", 5)
    assert BI.traded_close(aligned, "2026-09-16") is None
    assert BI.store_session_gaps(["2026-09-15", "2026-09-16", "2026-09-19"], [str(d.date()) for d in keep]) == \
        ["2026-09-15", "2026-09-16"]


# --------------------------------------------------------------------------- #
# Assessment
# --------------------------------------------------------------------------- #
def _ledger(n, values, *, model=0.0, missing=()):
    receipts, outcomes = [], []
    start = pd.Timestamp("2026-10-30")
    for i in range(n):
        sha = f"{i:064x}"
        books = {b: {"slots": [{"ticker": f"{i % 7:06d}.KS"}], "fallbackSlots": 4} for b in C.BOOKS}
        receipts.append({"receiptSha256": sha, "signalDate": str((start + pd.Timedelta(weeks=i)).date()), "books": books})
        for h in (126, 252):
            v = None if i in missing else values[i]
            outcomes.append({"receiptSha256": sha, "horizonSessions": h,
                             "books": {"CH_LOWVOL": {"netExcessReturn": v}, "CH_HIGH52": {"netExcessReturn": v},
                                       "CTRL_MODEL5": {"netExcessReturn": model}}})
    return receipts, outcomes


GOOD_PATH = {b: {"status": "COMPLETE", "sharpe": 1.0, "maxDrawdown": -0.2} for b in (*C.BOOKS, "CTRL_ETF")}


def test_assessment_accumulates_until_the_registered_cohort_is_graded():
    receipts, outcomes = _ledger(51, [0.05] * 51)
    assert all(v["verdict"] == "ACCUMULATING" for v in C.assess(receipts, outcomes, SPEC)["challengers"].values())


def test_harm_check_stops_a_clearly_losing_challenger():
    rng = np.random.default_rng(0)
    receipts, outcomes = _ledger(52, list(-0.05 + 0.01 * rng.standard_normal(52)))
    out = C.assess(receipts, outcomes, SPEC)["challengers"]["CH_LOWVOL"]
    assert out["verdict"] == "STOPPED_HARM" and out["harmCheck"]["result"] == "HARM"


def test_primary_needs_every_check_and_enough_complete_outcomes():
    rng = np.random.default_rng(1)
    values = list(0.06 + 0.01 * rng.standard_normal(104))
    receipts, outcomes = _ledger(104, values)
    out = C.assess(receipts, outcomes, SPEC, path_metrics=GOOD_PATH)["challengers"]["CH_LOWVOL"]
    assert out["verdict"] == "SUPPORTED" and all(out["primary"]["checks"].values())
    receipts, outcomes = _ledger(104, values, model=0.10)               # loses to the existing model
    assert C.assess(receipts, outcomes, SPEC, path_metrics=GOOD_PATH)["challengers"]["CH_LOWVOL"]["verdict"] == "NOT_SUPPORTED"
    worse = {**GOOD_PATH, "CH_LOWVOL": {"status": "COMPLETE", "sharpe": 1.0, "maxDrawdown": -0.26}}
    receipts, outcomes = _ledger(104, values)
    assert C.assess(receipts, outcomes, SPEC, path_metrics=worse)["challengers"]["CH_LOWVOL"]["verdict"] == "NOT_SUPPORTED"
    assert C.assess(receipts, outcomes, SPEC)["challengers"]["CH_LOWVOL"]["verdict"] == "INCONCLUSIVE_DATA"
    receipts, outcomes = _ledger(104, values, missing=set(range(11)))
    assert C.assess(receipts, outcomes, SPEC, path_metrics=GOOD_PATH)["challengers"]["CH_LOWVOL"]["verdict"] == "INCONCLUSIVE_DATA"


def test_turnover_counts_names_replaced():
    receipts, _ = _ledger(8, [0.0] * 8)
    assert C.turnover(receipts, "CH_LOWVOL") == {"weeklyNameReplacement": pytest.approx(0.2), "pairs": 7}


# --------------------------------------------------------------------------- #
# Risk path
# --------------------------------------------------------------------------- #
def _path_receipts(n):
    sessions = [d for d in RC.sessions("2026-10-30", "2027-03-31", "KR") if CORE.is_weekly_decision_session(d)][:n]
    out = []
    for i, d in enumerate(sessions):
        name = ["000001.KS", "000002.KS"][i // 4 % 2]
        out.append({"signalDate": str(d.date()), "executionDate": str(CORE.next_kr_session(d).date()),
                    "books": {b: {"slots": [{"ticker": name}], "fallbackSlots": 4} for b in C.BOOKS}})
    return out


def test_paper_path_marks_daily_and_charges_rebalances():
    receipts = _path_receipts(9)
    days = RC.sessions(receipts[0]["executionDate"], receipts[8]["executionDate"], "KR")
    flat = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1.0}, index=pd.DatetimeIndex(days))
    frames = {"000001.KS": flat, "000002.KS": flat, C.BENCHMARK: flat}
    path = C.paper_path(receipts, frames, "CH_LOWVOL", every=4, end_receipt=8)
    assert path["status"] == "COMPLETE" and path["maxDrawdown"] < 0 and path["rebalanceNameReplacement"] == pytest.approx(0.2)
    etf = C.paper_path(receipts, frames, "CTRL_ETF", every=4, end_receipt=8)
    assert etf["maxDrawdown"] > path["maxDrawdown"]                 # the switch cost is the only loss on flat prices
    gap = flat.drop(flat.index[10])
    assert C.paper_path(receipts, {**frames, "000001.KS": gap}, "CH_LOWVOL", every=4, end_receipt=8)["status"] == "INCOMPLETE"
    assert C.paper_path(receipts[:8], frames, "CH_LOWVOL", every=4, end_receipt=8)["status"] == "ACCUMULATING"


# --------------------------------------------------------------------------- #
# Recorder and workflow
# --------------------------------------------------------------------------- #
def test_live_recorder_fails_closed_without_a_registered_merge(tmp_path, monkeypatch):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site()))
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: (_ for _ in ()).throw(ValueError("SPEC_MERGE_TIME_UNKNOWN")))
    assert script.main(["record", str(path), str(tmp_path / "study")]) == 1
    status = json.loads((tmp_path / "study/publication-status.json").read_text())
    assert status["status"] == "REFUSED" and not (tmp_path / "study/receipts.jsonl").exists()
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp("2026-10-30T05:00:00Z"))
    assert script.main(["record", str(path), str(tmp_path / "study")]) == 0       # not this run's turn: quiet skip
    assert json.loads((tmp_path / "study/publication-status.json").read_text())["status"] == "SKIPPED"


def test_paper_ledger_step_runs_the_challenger_and_a_failure_never_costs_it(tmp_path, monkeypatch):
    import importlib
    update = importlib.import_module("scripts.update_ledger")
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    seen = []
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(script, "run_all", lambda site_path, directory: seen.append(directory) or 0)
    data = site()
    data["modelVersion"] = "m"
    path = tmp_path / "site.json"
    path.write_text(json.dumps(data))
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    assert update.main([str(path), str(ledger)]) == 0
    assert seen == [ledger / "research-strategies" / C.STUDY]
    monkeypatch.setattr(script, "run_all", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    assert update.main([str(path), str(ledger)]) == 0
    assert not list((ROOT / ".github/workflows").glob("*challenger*"))


def test_merge_time_is_the_first_parent_commit_that_added_the_spec(tmp_path):
    import subprocess

    def git(*args, date=None):
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
               "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    (tmp_path / "README").write_text("x")
    git("add", "README")
    git("commit", "-qm", "base", date="2026-10-20T00:00:00+00:00")
    with pytest.raises(ValueError, match="SPEC_MERGE_TIME_UNKNOWN"):
        C.merged_at_from_git(tmp_path)
    git("checkout", "-qb", "study")
    (tmp_path / C.SPEC_PATH).parent.mkdir(parents=True)
    (tmp_path / C.SPEC_PATH).write_text("{}")
    git("add", C.SPEC_PATH)
    git("commit", "-qm", "spec", date="2026-10-21T00:00:00+00:00")       # authored on the branch
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "study", "-m", "merge", date="2026-10-27T03:00:00+00:00")
    assert pd.Timestamp(C.merged_at_from_git(tmp_path)) == pd.Timestamp("2026-10-27T03:00:00+00:00")


@pytest.mark.parametrize("clock,site_kwargs,expected", [
    # Saturday run (the cron's real start, ~04:30 UTC): Friday's final session is recorded.
    ("2026-10-31T04:35:00Z", {"generated": "2026-10-31T04:30:00+00:00"}, "RECORDED"),
    # The same run when the build takes two hours (run 39722662150 on 2026-10-22: 04:29 start, 06:24 artifact): still inside the window.
    ("2026-10-31T06:27:00Z", {"generated": "2026-10-31T06:24:43+00:00"}, "RECORDED"),
    # Saturday wrote nothing (failed run): Sunday's run is the backup and records the same Friday.
    ("2026-11-01T04:35:00Z", {"generated": "2026-11-01T04:30:00+00:00"}, "RECORDED"),
    # A delayed weekday run inside the KRX session: the artifact speaks for an unfinished session, nothing is recorded.
    ("2026-11-03T04:35:00Z", {"generated": "2026-11-03T04:30:00+00:00", "session": "2026-11-03"}, "SKIPPED"),
])
def test_actual_recording_path_through_the_paper_ledger_step(tmp_path, monkeypatch, clock, site_kwargs, expected):
    """End to end through scripts/update_ledger.main, the LIVE pathway, the real spec and code-hash check; only the merge time,
    the writer's clock and the vendor download are replaced."""
    import importlib
    update = importlib.import_module("scripts.update_ledger")
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp(clock))
    data = site(**site_kwargs)
    data["modelVersion"] = "m"
    path = tmp_path / "site.json"
    path.write_text(json.dumps(data))
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    study = ledger / "research-strategies" / C.STUDY
    weekly_before = sorted(p.name for p in ledger.iterdir())
    assert update.main([str(path), str(ledger)]) == 0
    status = json.loads((study / "publication-status.json").read_text())
    assert status["status"] == "ASSESSED" and status["productionEffect"] == "NONE"
    receipts = (study / "receipts.jsonl").read_text().splitlines() if (study / "receipts.jsonl").exists() else []
    assert len(receipts) == (1 if expected == "RECORDED" else 0)
    if receipts:
        row = json.loads(receipts[0])
        C.validate_receipt(row, pathway=C.LIVE)
        assert (row["signalDate"], row["executionDate"], row["evidenceClass"]) == ("2026-10-30", "2026-11-02", "PROSPECTIVE_PAPER")
        # The same window again is idempotent: no second receipt, the first is unchanged.
        first = (study / "receipts.jsonl").read_bytes()
        assert update.main([str(path), str(ledger)]) == 0
        assert (study / "receipts.jsonl").read_bytes() == first
    # Nothing outside its own namespace is written by the challenger (the paper ledger writes its own files).
    assert {p.name for p in (ledger / "research-strategies").iterdir()} == {C.STUDY}
    assert "weekly-decisions" not in weekly_before + [p.name for p in ledger.iterdir()]


def test_research_namespace_leaves_the_paper_ledger_and_weekly_receipts_byte_identical(tmp_path, monkeypatch):
    """The same Saturday run with the challenger hook and with it stubbed out: every file outside the challenger's own directory is
    byte-identical, and pre-existing weekly-decisions receipts are never touched."""
    import importlib
    update = importlib.import_module("scripts.update_ledger")
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp("2026-10-31T04:35:00Z"))
    data = site(generated="2026-10-31T04:30:00+00:00")
    data["modelVersion"] = "m"
    path = tmp_path / "site.json"
    path.write_text(json.dumps(data))

    def run(name, hook):
        ledger = tmp_path / name / "ledger"
        (ledger / "weekly-decisions").mkdir(parents=True)
        (ledger / "weekly-decisions" / "receipts.jsonl").write_text('{"receiptId":"existing"}\n')
        with monkeypatch.context() as m:
            if not hook:
                m.setattr(script, "run_all", lambda *a: 0)
            assert update.main([str(path), str(ledger)]) == 0
        return {str(p.relative_to(ledger)): p.read_bytes() for p in ledger.rglob("*") if p.is_file()}
    with_hook, without = run("with", True), run("without", False)
    ours = {k for k in with_hook if k.startswith("research-strategies/" + C.STUDY + "/")}
    assert ours and "research-strategies/" + C.STUDY + "/receipts.jsonl" in ours
    outside = {k: v for k, v in with_hook.items() if k not in ours}
    assert outside == without
    assert outside["weekly-decisions/receipts.jsonl"] == b'{"receiptId":"existing"}\n'


def test_finding_the_merge_time_never_shortens_history(tmp_path):
    """CI checks out main in full and then fetches pinned commits at depth 1, so the repository reports shallow while main is complete.
    A ``--shallow-since`` deepen cut main back to its date there and removed a 2026-09 commit another test proves ancestry against."""
    import subprocess
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}

    def git(cwd, *args, date=None):
        e = dict(env, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}))
        return subprocess.run(["git", *args], cwd=cwd, env=e, check=True, capture_output=True, text=True).stdout.strip()
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / "a").write_text("a")
    git(origin, "add", "a")
    git(origin, "commit", "-qm", "old", date="2026-09-01T00:00:00+00:00")
    old = git(origin, "rev-parse", "HEAD")
    (origin / C.SPEC_PATH).parent.mkdir(parents=True)
    (origin / C.SPEC_PATH).write_text("{}")
    git(origin, "add", C.SPEC_PATH)
    git(origin, "commit", "-qm", "spec", date="2026-10-27T03:00:00+00:00")
    git(origin, "checkout", "-q", "--orphan", "other")
    (origin / "b").write_text("b")
    git(origin, "add", "b")
    git(origin, "commit", "-qm", "other", date="2026-10-28T00:00:00+00:00")
    git(origin, "commit", "-q", "--allow-empty", "-m", "other2", date="2026-10-29T00:00:00+00:00")
    git(origin, "checkout", "-q", "main")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--no-local", str(origin), str(clone))                       # full main
    git(clone, "fetch", "-q", "--depth=1", "origin", "other")                                 # ... and now "shallow"
    assert git(clone, "rev-parse", "--is-shallow-repository") == "true"
    assert pd.Timestamp(C.merged_at_from_git(clone)) == pd.Timestamp("2026-10-27T03:00:00+00:00")
    assert subprocess.run(["git", "cat-file", "-e", old + "^{commit}"], cwd=clone).returncode == 0      # the old commit is still there
    assert subprocess.run(["git", "merge-base", "--is-ancestor", old, "HEAD"], cwd=clone).returncode == 0
