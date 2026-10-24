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


@pytest.fixture(autouse=True)
def _accounting_challenger_isolated(monkeypatch):
    """The paper-ledger step also runs kr-selection-challenger-v2-accounting. It has its own tests; here it must never run git against this
    checkout or download anything."""
    from scripts import record_kr_selection_challenger_v2 as accounting
    monkeypatch.setattr(accounting, "run_all", lambda *a: 0)

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / C.SPEC_PATH).read_text())
SESSION = "2026-10-30"                      # Friday: a weekly decision session
EVENING = "2026-10-30T09:30:00+00:00"       # 18:30 KST, after finality
MERGED = "2026-10-26T03:00:00+00:00"
SECTORS = ["Tech", "Fin", "Energy", "Health", "Ind", "Mat", "Util", "Cons"]


_STEPS = np.abs(np.random.default_rng(7).normal(0, 1, 126)) + 0.1   # one multiset of daily moves shared by every invented name


def bars_for(ticker, session=SESSION, *, history=280, drop=(), holiday_rows=()):
    """An invented vendor frame ending at ``session``. The last 252 log moves are a fixed symmetric multiset scaled by the name's index,
    so downside volatility rises with the index; names with index % 3 == 0 rise then fall back (below their 200-day average), the
    others fall then recover (above it). ``drop`` removes KRX sessions (a vendor gap); ``holiday_rows`` adds rows on closed days."""
    i = int(ticker[:6]) - 100000
    days = RC.sessions(str((pd.Timestamp(session) - pd.Timedelta(days=1500)).date()), session, "KR")[-history:]
    steps = np.sort(np.concatenate([_STEPS, -_STEPS]))
    if i % 3 == 0:
        steps = steps[::-1]
    walk = np.concatenate([np.zeros(max(history - len(steps), 0)), 0.004 * (1 + 0.04 * i) * steps])[-history:]
    close = (1000.0 + i) * np.exp(np.cumsum(walk))
    frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1e5}, index=pd.DatetimeIndex(days))
    frame = frame.drop(index=[pd.Timestamp(d) for d in drop])
    for day in holiday_rows:
        frame.loc[pd.Timestamp(day)] = frame.iloc[-2]
    return frame.sort_index()


def production_features(frame):
    """The artifact's own values, computed exactly as the production build computes them on the vendor ROWS it was given."""
    from pipeline import features as F
    from pipeline import longterm as LT
    from pipeline import risk as RISK
    detail = RISK.diagnose("x", F.build_features(frame))
    dv = LT.downside_vol_252(frame["Close"])
    return {"downsideVolPct": round(dv * 100, 1) if dv is not None else None, "lastClose": detail["lastClose"],
            "ma200": detail["ma200"], "pct52wHigh": detail["pct52wHigh"]}


_FEATURES = {}


def _features(ticker, session):
    key = (ticker, session)
    if key not in _FEATURES:
        _FEATURES[key] = production_features(bars_for(ticker, session))
    return _FEATURES[key]


def fetch_for(session=SESSION, overrides=None):
    """A stand-in for the vendor download: fixture frames for every requested name (``overrides`` replaces some)."""
    def fetch(tickers, start, **_):
        out = {t: bars_for(t, session) for t in tickers}
        out.update({t: f for t, f in (overrides or {}).items() if t in out})
        return {t: f for t, f in out.items() if f is not None}
    return fetch


def site(n=50, *, generated=EVENING, session=SESSION, **edit):
    rows, details = [], {}
    for i in range(n):
        t = f"{100000 + i:06d}.KS"
        f = _features(t, session)
        rows.append({"ticker": t, "sector": SECTORS[i % len(SECTORS)], "alpha": 0.01 * i,
                     "risk": {"downsideVolPct": f["downsideVolPct"]}, "mom12_1Pct": 5.0})
        details[t] = {"asOf": session, "lastClose": f["lastClose"], "ma200": f["ma200"], "pct52wHigh": f["pct52wHigh"]}
    out = {"generatedAt": generated, "provenance": {"dataMode": "live", "buildCommitSha": "a" * 40, "modelVersion": "m"},
           "indices": [{"symbol": "^KS11", "asOf": session}], "details": details,
           "longTerm": {"regions": {"KR": {"validationCrossSection": rows, "picks": [{"ticker": rows[-1]["ticker"]}]}}}}
    out.update(edit)
    return out


def receipt(s=None, *, created=EVENING, merged=MERGED, overrides=None):
    s = s or site()
    session = s["indices"][0]["asOf"]
    return C.build_receipt(s, "b" * 64, pathway=C.SYNTHETIC, created_at_utc=created, now_utc=created, merged_at_utc=merged,
                           code_identity={"commitSha": "c" * 40, "files": {"pipeline/kr_selection_challenger.py": "d" * 64}},
                           spec=SPEC, spec_digest="e" * 64, fetch_bars=fetch_for(session, overrides))


def make_books(s, session=SESSION, overrides=None):
    rows, _ = C.universe_rows(s, session)
    return C.build_books(s, session, SPEC, bars=fetch_for(session, overrides)(C.verification_tickers(rows), None))


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
    for rel in [C.SPEC_PATH, *SPEC["codeFileHashes"], *C.SCIENTIFIC_FILES]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    C.load_spec(tmp_path)
    (tmp_path / "pipeline/kr_selection_challenger.py").write_text("# edited\n")
    with pytest.raises(ValueError, match="CODE_CHANGED_SINCE_REGISTRATION"):
        C.load_spec(tmp_path)


def _copy_study(tmp_path):
    for rel in [C.SPEC_PATH, *SPEC["codeFileHashes"], *C.SCIENTIFIC_FILES]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())


def test_the_spec_pins_its_scientific_dependencies_by_bytes_and_behaviour():
    deps = SPEC["scientificDependencies"]
    assert set(deps["fileHashes"]) == set(C.SCIENTIFIC_FILES)
    assert deps["conformanceDigest"] == C.conformance_digest()                      # the registered behaviour is today's
    assert C.conformance_digest() == C.conformance_digest()                         # deterministic


def test_an_edited_scientific_dependency_file_refuses_the_spec(tmp_path):
    _copy_study(tmp_path)
    C.load_spec(tmp_path)
    path = tmp_path / "pipeline/prospective_receipt_core.py"
    path.write_text(path.read_text() + "\n# edited\n")
    with pytest.raises(ValueError, match="SCIENTIFIC_DEPENDENCY_CHANGED: pipeline/prospective_receipt_core.py"):
        C.load_spec(tmp_path)


@pytest.mark.parametrize("target,patch", [
    ("trade_cost", lambda m: m.setattr(C.W, "trade_cost_fraction", lambda *a, _f=C.W.trade_cost_fraction, **k: _f(*a, **k) + 1e-4)),
    ("newey_west", lambda m: m.setattr(C.KP, "_newey_west_stats", lambda s, h, _f=C.KP._newey_west_stats: {**_f(s, h), "hacLag": 1})),
    ("downside_vol", lambda m: m.setattr(C.LT, "downside_vol_252", lambda c, _f=C.LT.downside_vol_252: (_f(c) or 0.0) * 1.01)),
    ("calendar", lambda m: m.setattr(C.RC, "sessions", lambda a, b, r="COMMON", _f=C.RC.sessions: _f(a, b, r)[1:])),
    ("finality", lambda m: m.setattr(C.W, "SESSION_EVIDENCE", {**C.W.SESSION_EVIDENCE, "KR": "^KS200"})),
])
def test_a_changed_production_helper_refuses_the_live_spec_without_touching_the_studys_files(monkeypatch, target, patch):
    """The study's own files and the pinned files are byte-identical; only a helper's behaviour moved."""
    C.load_spec()
    patch(monkeypatch)
    with pytest.raises(ValueError, match="SCIENTIFIC_DEPENDENCY_CHANGED: conformance"):
        C.load_spec()


def test_the_live_recorder_refuses_under_a_moved_dependency_and_synthetic_fixtures_stay_isolated(tmp_path, monkeypatch):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch_for())
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp("2026-10-31T04:35:00Z"))
    monkeypatch.setattr(C.W, "trade_cost_fraction", lambda *a, _f=C.W.trade_cost_fraction, **k: _f(*a, **k) * 2)
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(generated="2026-10-31T04:30:00+00:00")))
    study = tmp_path / "study"
    assert script.run_all(path, study) == 1
    status = json.loads((study / "publication-status.json").read_text())
    assert status["signalRecordState"] == "REFUSED" and status["signalRecordReason"] == "SCIENTIFIC_DEPENDENCY_CHANGED: conformance"
    assert {"record", "outcomes", "assess"} <= set(status["failedSteps"]) and not (study / "receipts.jsonl").exists()
    with pytest.raises(ValueError, match="SCIENTIFIC_DEPENDENCY_CHANGED"):        # LIVE receipts check whoever calls them
        C.build_receipt(site(), "b" * 64, pathway=C.LIVE, created_at_utc=EVENING, now_utc=EVENING, merged_at_utc=MERGED,
                        code_identity={"commitSha": "c" * 40, "files": {"x": "d" * 64}}, spec=SPEC, spec_digest="e" * 64,
                        fetch_bars=fetch_for())
    assert receipt()["pathway"] == C.SYNTHETIC                                      # fixtures never read the contract


# --------------------------------------------------------------------------- #
# Books from signal-time facts only
# --------------------------------------------------------------------------- #
def test_books_follow_the_registered_order_and_sector_cap():
    books, universe = make_books(site())
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
    low = make_books(s)[0]["CH_LOWVOL"]["slots"]
    assert [x["ticker"] for x in low] == ["100000.KS", "100001.KS", "100003.KS", "100004.KS", "100005.KS"]


def test_missing_values_exclude_a_name_from_its_book_only_and_are_counted():
    s = site()
    s["longTerm"]["regions"]["KR"]["validationCrossSection"][0]["risk"]["downsideVolPct"] = None
    s["details"]["100001.KS"]["asOf"] = "2026-10-29"                  # stale quote
    s["details"]["100002.KS"]["ma200"] = None                         # 200-day average undetermined
    s["longTerm"]["regions"]["KR"]["validationCrossSection"][3]["alpha"] = True   # a bool is not a number
    books, universe = make_books(s)
    assert universe["excluded"]["QUOTE_NOT_ON_SIGNAL_SESSION"] == 1
    assert books["CH_LOWVOL"]["excluded"]["FEATURE_MISSING"] == 1
    assert books["CH_HIGH52"]["excluded"]["MA200_UNDETERMINED"] == 1
    assert books["CTRL_MODEL5"]["excluded"]["FEATURE_MISSING"] == 1
    assert [x["ticker"] for x in books["CH_LOWVOL"]["slots"]][0] == "100002.KS"


def test_a_thin_cross_section_holds_the_benchmark_only():
    books, _ = make_books(site(n=29))
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
    ((100, 101, 99, 100, -1), "VOLUME_INVALID"),
    ((100, 101, 99, 100, None), "VOLUME_INVALID"),
    ((100, 101, 99, 100, float("nan")), "VOLUME_INVALID"),
    ((100, 101, 99, 100, float("inf")), "VOLUME_INVALID"),
    ((100, 101, 99, 100, float("-inf")), "VOLUME_INVALID"),
    ((100, 101, 99, 100, "n/a"), "VOLUME_INVALID"),
    ((100, float("inf"), 99, 100, 10), "RANGE_UNRESOLVED"),
])
def test_row_states(row, state):
    assert BI.classify_row(*row) == state


@pytest.mark.parametrize("volume,state", [
    (None, "VOLUME_INVALID"), (float("nan"), "VOLUME_INVALID"), (float("inf"), "VOLUME_INVALID"), (float("-inf"), "VOLUME_INVALID"),
    (-5.0, "VOLUME_INVALID"), (0.0, "SUSPENDED"),
])
def test_an_unknown_or_invalid_volume_is_never_a_traded_session(volume, state):
    """Plausible OHLC with a volume nobody stated is not evidence the name traded; a stated zero stays a suspension."""
    days = RC.sessions("2026-06-01", "2026-10-30", "KR")
    frame = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1e5}, index=pd.DatetimeIndex(days))
    frame["Volume"] = frame["Volume"].astype(object)
    hole = days[-3]
    frame.loc[hole, "Volume"] = volume
    aligned = BI.calendar_frame(frame)
    assert aligned.loc[hole, "state"] == state
    assert BI.traded_close(aligned, hole) is None and pd.isna(aligned.loc[hole, "Close"])
    assert not BI.window_complete(aligned, days[-1], 20) and BI.window_complete(aligned, days[-4], 20)
    assert BI.summary(aligned)["states"][state] == 1
    # The same row with no Volume column at all.
    if volume is None:
        assert BI.calendar_frame(frame.drop(columns="Volume")).loc[hole, "state"] == "VOLUME_INVALID"


def test_an_unknown_volume_is_a_provider_gap_in_outcomes_and_the_risk_path():
    """At maturity it is never TERMINAL_ECONOMICS_UNRESOLVED (that needs a stated zero) and never final; at a rebalance it is never
    the NOT_EXECUTABLE fallback (that needs a stated suspension) and stops the path."""
    r = receipt()
    a = r["books"]["CH_LOWVOL"]["slots"][0]["ticker"]
    frames, maturity = _frames(r, 126, growth={C.BENCHMARK: 0.10})
    frames[a] = frames[a].astype({"Volume": object})
    frames[a].iloc[-1, frames[a].columns.get_loc("Volume")] = float("nan")
    window_closed = pd.Timestamp(str(CORE.maturity_session(r["executionDate"], 126 + C.OUTCOME_RETRY_SESSIONS + 3).date())) \
        .tz_localize("UTC") + pd.Timedelta(hours=10)
    out = C.build_outcome(r, horizon=126, frames=frames, now_utc=window_closed, pathway=C.SYNTHETIC)
    assert out["names"][a]["integrityState"] == "VOLUME_INVALID" and out["names"][a]["state"] == "NAME_OUTCOME_MISSING"
    assert out["resolution"] == "DEFERRED" and out["unresolvedClasses"] == [C.PROVIDER]
    receipts = _path_receipts(9)
    days = RC.sessions(receipts[0]["executionDate"], receipts[8]["executionDate"], "KR")
    flat = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1.0}, index=pd.DatetimeIndex(days))
    unknown = flat.astype({"Volume": object})
    unknown.loc[pd.Timestamp(receipts[4]["executionDate"]), "Volume"] = None
    path = C.paper_path(receipts, {"000001.KS": flat, "000002.KS": unknown, C.BENCHMARK: flat}, "CH_LOWVOL", every=4, end_receipt=8)
    assert path["status"] == "INCOMPLETE" and path["ticker"] == "000002.KS"


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


def _flat(days, start=100.0, end=100.0):
    close = np.linspace(start, end, len(days))
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1.0}, index=pd.DatetimeIndex(days))


def test_the_opening_trade_cost_is_a_loss_in_the_risk_path_not_only_in_the_return():
    """One opening purchase with positive fees and no later turnover (every > end_receipt), on flat prices. The book starts at 1.0
    before that trade, so the fee is a drawdown and a negative first daily return, not a step hidden before the first observation."""
    receipts = _path_receipts(9)
    days = RC.sessions(receipts[0]["executionDate"], receipts[8]["executionDate"], "KR")
    entry = receipts[0]["executionDate"]
    frames = {"000001.KS": _flat(days), "000002.KS": _flat(days), C.BENCHMARK: _flat(days)}
    stock_cost = 0.2 * C._leg(entry, is_benchmark=False, side="buy") + 0.8 * C._leg(entry, is_benchmark=True, side="buy")
    etf_cost = C._leg(entry, is_benchmark=True, side="buy")
    assert stock_cost > 0 and etf_cost > 0
    for book, cost in (("CH_LOWVOL", stock_cost), ("CTRL_ETF", etf_cost)):     # each book against its own opening fee
        path = C.paper_path(receipts, frames, book, every=9, end_receipt=8)
        assert path["status"] == "COMPLETE" and path["rebalanceNameReplacement"] is None
        assert path["maxDrawdown"] == pytest.approx(-cost, rel=1e-12)
        assert path["annualReturn"] == pytest.approx((1 - cost) ** (252 / (len(days) - 1)) - 1, rel=1e-12)
        returns = [-cost] + [0.0] * (len(days) - 2)                             # the opening loss, then nothing moves
        assert path["annualVolatility"] == pytest.approx(float(np.std(returns, ddof=1) * np.sqrt(252)), rel=1e-9)
        assert path["annualVolatility"] > 0 and path["sharpe"] < 0


def test_the_opening_cost_enters_volatility_once_on_moving_prices():
    """An ETF-only book on a rising benchmark: the risk path must equal the hand-built net-of-cost path from a pre-trade 1.0, with the
    fee charged exactly once (the annual return and every daily return agree with that one NAV path)."""
    receipts = _path_receipts(9)
    days = RC.sessions(receipts[0]["executionDate"], receipts[8]["executionDate"], "KR")
    bench = _flat(days, 100.0, 112.0)
    frames = {"000001.KS": _flat(days), "000002.KS": _flat(days), C.BENCHMARK: bench}
    path = C.paper_path(receipts, frames, "CTRL_ETF", every=9, end_receipt=8)
    cost = C._leg(receipts[0]["executionDate"], is_benchmark=True, side="buy")
    price = bench["Close"].to_numpy()
    nav = np.concatenate([[1.0], (1 - cost) * price / price[0]])               # pre-trade 1.0, then the post-cost marked book
    daily = nav[2:] / np.concatenate([[1.0], nav[2:-1]]) - 1                   # first return from 1.0 to the first full day
    assert len(daily) == len(days) - 1
    assert path["annualReturn"] == pytest.approx(nav[-1] ** (252 / len(daily)) - 1, rel=1e-12)
    assert path["annualVolatility"] == pytest.approx(float(np.std(daily, ddof=1) * np.sqrt(252)), rel=1e-9)
    assert path["sharpe"] == pytest.approx(path["annualReturn"] / path["annualVolatility"], rel=1e-12)
    assert path["maxDrawdown"] == pytest.approx(-cost, rel=1e-12)              # the only fall below the pre-trade 1.0
    no_fee = (price[-1] / price[0]) ** (252 / len(daily)) - 1
    assert path["annualReturn"] < no_fee                                       # charged, and only once
    assert path["annualReturn"] == pytest.approx((1 + no_fee) * (1 - cost) ** (252 / len(daily)) - 1, rel=1e-12)


def test_a_name_suspended_on_a_rebalance_session_is_held_as_the_benchmark_in_the_risk_path():
    """The cohort outcome holds a name suspended at execution in 069500.KS (NOT_EXECUTABLE_HELD_AS_BENCHMARK). The risk path must do the
    same, or one halt on a rebalance date makes the whole primary risk check INCONCLUSIVE_DATA while the outcomes call it measured."""
    receipts = _path_receipts(9)
    days = RC.sessions(receipts[0]["executionDate"], receipts[8]["executionDate"], "KR")
    flat = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1.0}, index=pd.DatetimeIndex(days))
    bench = flat.copy()
    for col in ("Open", "High", "Low", "Close"):
        bench[col] = np.linspace(100.0, 110.0, len(days))
    entry = pd.Timestamp(receipts[4]["executionDate"])                      # 000002.KS is chosen for receipts 4-7
    halted = flat.copy()
    halted.loc[entry, "Volume"] = 0.0                                       # a served row: the name did not trade
    frames = {"000001.KS": flat, "000002.KS": halted, C.BENCHMARK: bench}
    path = C.paper_path(receipts, frames, "CH_LOWVOL", every=4, end_receipt=8)
    assert path["status"] == "COMPLETE"
    # Identical to a receipt that never chose the name: the slot sits in 069500.KS for the period, with the same legs charged.
    as_benchmark = [{**r, "books": {b: {"slots": [], "fallbackSlots": 5} for b in C.BOOKS}} if 4 <= i < 8 else r
                    for i, r in enumerate(receipts)]
    same = C.paper_path(as_benchmark, frames, "CH_LOWVOL", every=4, end_receipt=8)
    assert {k: path[k] for k in ("annualReturn", "maxDrawdown", "sharpe", "sessions")} == \
        {k: same[k] for k in ("annualReturn", "maxDrawdown", "sharpe", "sessions")}
    # And it is the cohort outcome's own reading of that session.
    span = BI.calendar_frame(halted, start=str(entry.date()), end=str(days[-1].date()))
    assert C.name_outcome(span, str(entry.date()), str(days[-1].date()), 0.0)["state"] == C.NOT_EXECUTABLE
    # Still fail closed: a missing row or an invalid close on the rebalance session, and a halt of a name already held.
    missing = flat.drop(entry)
    assert C.paper_path(receipts, {**frames, "000002.KS": missing}, "CH_LOWVOL", every=4, end_receipt=8)["status"] == "INCOMPLETE"
    invalid = flat.copy()
    invalid.loc[entry, "Close"] = 0.0
    assert C.paper_path(receipts, {**frames, "000002.KS": invalid}, "CH_LOWVOL", every=4, end_receipt=8)["status"] == "INCOMPLETE"
    held_halt = flat.copy()
    held_halt.loc[pd.Timestamp(receipts[2]["executionDate"]), "Volume"] = 0.0   # 000001.KS, bought at receipt 0, halted later
    assert C.paper_path(receipts, {**frames, "000001.KS": held_halt}, "CH_LOWVOL", every=4, end_receipt=8)["status"] == "INCOMPLETE"


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
    assert status["signalRecordState"] == "REFUSED" and status["status"] == "STEP_FAILED" and not (tmp_path / "study/receipts.jsonl").exists()
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp("2026-10-30T05:00:00Z"))
    assert script.main(["record", str(path), str(tmp_path / "study")]) == 0       # not this run's turn: quiet skip
    assert json.loads((tmp_path / "study/publication-status.json").read_text())["signalRecordState"] == "SKIPPED"


def test_paper_ledger_step_runs_the_challenger_and_a_failure_never_costs_it(tmp_path, monkeypatch):
    import importlib
    update = importlib.import_module("scripts.update_ledger")
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    accounting = importlib.import_module("scripts.record_kr_selection_challenger_v2")
    seen = []
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch_for())
    monkeypatch.setattr(script, "run_all", lambda site_path, directory: seen.append(directory) or 0)
    monkeypatch.setattr(accounting, "run_all", lambda *a: 0)       # its own test; the real one would run git against this repository
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


def _git_env(home, date=None):
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": "/usr/bin:/bin", "HOME": str(home)}
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return env


def test_merge_time_is_the_first_parent_commit_on_main_that_added_the_spec(tmp_path):
    """Read from origin/main, never from HEAD. A branch that adds the spec is not a registration until it is merged; a checkout that
    predates the merge cannot record under it."""
    import subprocess
    origin, clone = tmp_path / "origin", tmp_path / "clone"

    def git(cwd, *args, date=None):
        return subprocess.run(["git", *args], cwd=cwd, env=_git_env(tmp_path, date), check=True, capture_output=True,
                              text=True).stdout.strip()
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / "README").write_text("x")
    git(origin, "add", "README")
    git(origin, "commit", "-qm", "base", date="2026-10-20T00:00:00+00:00")
    git(origin, "checkout", "-qb", "study")
    (origin / C.SPEC_PATH).parent.mkdir(parents=True)
    (origin / C.SPEC_PATH).write_text("{}")
    git(origin, "add", C.SPEC_PATH)
    git(origin, "commit", "-qm", "spec", date="2026-10-21T00:00:00+00:00")      # authored on the branch, not merged
    git(tmp_path, "clone", "-q", "--no-local", str(origin), str(clone))
    git(clone, "checkout", "-q", "study")                                        # running the unmerged branch itself
    with pytest.raises(ValueError, match="SPEC_NOT_ON_MAIN"):
        C.merged_at_from_git(clone)
    git(origin, "checkout", "-q", "main")
    git(origin, "merge", "-q", "--no-ff", "study", "-m", "merge", date="2026-10-27T03:00:00+00:00")
    merge = git(origin, "rev-parse", "HEAD")
    # The clone's HEAD is still the branch tip, which does not contain the merge commit.
    with pytest.raises(ValueError, match="RUNNING_CODE_DOES_NOT_CONTAIN_REGISTRATION"):
        C.merged_at_from_git(clone)
    git(clone, "checkout", "-q", "-B", "main", "origin/main")
    found = C.registration_from_git(clone)
    # git renders a UTC commit time as "Z" or "+00:00" depending on its version; the instant is what is registered.
    assert found["commitSha"] == merge
    assert pd.Timestamp(found["mergedAtUtc"]) == pd.Timestamp("2026-10-27T03:00:00+00:00")
    # Without an origin/main at all the recorder refuses rather than guessing from HEAD.
    git(clone, "remote", "remove", "origin")
    git(clone, "update-ref", "-d", C.MAIN_REF)
    with pytest.raises(ValueError, match="SPEC_MERGE_TIME_UNKNOWN"):
        C.merged_at_from_git(clone)


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
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch_for())
    monkeypatch.setattr(importlib.import_module("scripts.record_kr_selection_challenger_v2"), "run_all", lambda *a: 0)  # its own tests
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
    assert status["steps"]["assess"]["status"] == "ASSESSED" and status["productionEffect"] == "NONE"
    assert status["signalRecordState"] == expected and status["status"] == "OK"
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
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch_for())
    monkeypatch.setattr(importlib.import_module("scripts.record_kr_selection_challenger_v2"), "run_all", lambda *a: 0)
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


# --------------------------------------------------------------------------- #
# Publication status: a later step never hides an earlier refusal
# --------------------------------------------------------------------------- #
def _run_all(tmp_path, monkeypatch, clock, **site_kwargs):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch_for())
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp(clock))
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(**site_kwargs)))
    study = tmp_path / "study"
    return script, script.run_all(path, study), study


def _status(study):
    return json.loads((study / "publication-status.json").read_text())


def test_a_refused_record_survives_the_later_steps(tmp_path, monkeypatch):
    # Signal 2026-10-30 is after the merge date but this clock is before the registered floor is irrelevant: use an unsafe artifact.
    script, code, study = _run_all(tmp_path, monkeypatch, "2026-10-31T04:35:00Z", generated="2026-10-31T04:30:00+00:00",
                                   provenance={"dataMode": "synthetic", "buildCommitSha": "a" * 40, "modelVersion": "m"})
    status = _status(study)
    assert code == 1 and status["status"] == "STEP_FAILED" and "record" in status["failedSteps"]
    assert status["signalRecordState"] == "REFUSED" and status["signalRecordReason"]
    assert status["steps"]["outcomes"]["status"] == "NOTHING_MATURED" and status["steps"]["assess"]["status"] == "ASSESSED"
    assert json.loads((study / "publication-status.record.json").read_text())["status"] == "REFUSED"
    assert not (study / "receipts.jsonl").exists()


def test_a_step_exception_is_persisted_not_only_printed(tmp_path, monkeypatch):
    script, _, study = _run_all(tmp_path, monkeypatch, "2026-10-31T04:35:00Z", generated="2026-10-31T04:30:00+00:00")
    monkeypatch.setattr(script, "outcomes", lambda directory: (_ for _ in ()).throw(OSError("vendor refused")))
    assert script.run_all(tmp_path / "site.json", study) == 1
    status = _status(study)
    assert status["failedSteps"] == ["outcomes"] and status["steps"]["outcomes"]["error"] == "OSError: vendor refused"
    assert status["signalRecordState"] == "SKIPPED"           # the earlier step's own answer is kept (already recorded)
    assert len((study / "receipts.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("clock,state,reason", [
    ("2026-10-30T09:30:00Z", "RECORDED", None),                                       # first signal session, 18:30 KST
    ("2026-10-30T08:59:00Z", "SKIPPED", "ARTIFACT_NOT_BUILT_ON_A_FINAL_SESSION"),     # before 18:00 KST
    ("2026-11-02T00:30:00Z", "SKIPPED", "RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED"),   # next day 09:30 KST: window closed
])
def test_timing_boundaries_write_a_machine_readable_state(tmp_path, monkeypatch, clock, state, reason):
    script, _, study = _run_all(tmp_path, monkeypatch, clock, generated=clock.replace("Z", "+00:00"))
    status = _status(study)
    assert status["signalRecordState"] == state and status["status"] == "OK"
    assert (status["signalRecordReason"] or "").startswith(reason or "")
    assert (study / "receipts.jsonl").exists() == (state == "RECORDED")


class _AdvancingClock:
    """The writer's clock for one record() run: ``start`` until the vendor download, ``after`` from then on."""

    def __init__(self, start, after):
        self.now, self.after, self.reads = pd.Timestamp(start), pd.Timestamp(after), []

    def __call__(self):
        self.reads.append(self.now)
        return self.now

    def fetch(self, tickers, start, **_):
        out = fetch_for()(tickers, start)
        self.now = self.after                          # the download took this long
        return out


OPEN = "2026-11-02T00:00:00Z"                           # 09:00 KST on the execution session of signal 2026-10-30


@pytest.mark.parametrize("finished,recorded", [
    ("2026-11-01T23:59:30Z", True),                     # (a) download done at 08:59:30 KST: inside the window
    (OPEN, False),                                      # (b) done exactly at the open: the window is closed
    ("2026-11-02T00:01:00Z", False),                    # (c) done at 09:01 KST
])
def test_the_receipt_window_is_decided_by_the_clock_at_the_write_not_at_the_start(tmp_path, monkeypatch, finished, recorded):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    clock = _AdvancingClock("2026-11-01T23:59:00Z", finished)          # every run starts at 08:59 KST, before the open
    monkeypatch.setattr(CORE, "system_utc_now", clock)
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", clock.fetch)
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(generated="2026-10-31T04:30:00+00:00")))
    study = tmp_path / "study"
    code = script.record(path, study)
    state = json.loads((study / "publication-status.record.json").read_text())
    if recorded:
        assert code == 0 and state["status"] == "RECORDED"
        (row,) = C.read_receipts(study / "receipts.jsonl", pathway=C.LIVE)
        assert pd.Timestamp(row["createdAtUtc"]) == pd.Timestamp(finished)           # the final clock, not the start
        assert row["receiptSha256"] == CORE.receipt_digest(row) == state["receiptSha256"]
    else:
        assert code == 1 and state["status"] == "REFUSED"
        assert state["reason"].startswith(C.WINDOW_CLOSED_DURING_RECORDING + ": RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED")
        assert not (study / "receipts.jsonl").exists()
    assert clock.reads[0] == pd.Timestamp("2026-11-01T23:59:00Z") and clock.reads[-1] == pd.Timestamp(finished)


def test_a_late_attempt_never_touches_an_existing_receipt(tmp_path, monkeypatch):
    """(d) A receipt written in the window; later attempts (finished late, or started late) leave its bytes as they are."""
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(generated="2026-10-31T04:30:00+00:00")))
    study = tmp_path / "study"
    first = _AdvancingClock("2026-10-31T04:35:00Z", "2026-10-31T04:40:00Z")
    monkeypatch.setattr(CORE, "system_utc_now", first)
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", first.fetch)
    assert script.record(path, study) == 0
    before = (study / "receipts.jsonl").read_bytes()
    for start, end in (("2026-11-01T23:59:00Z", "2026-11-02T00:01:00Z"), ("2026-11-02T00:05:00Z", "2026-11-02T00:06:00Z")):
        late = _AdvancingClock(start, end)
        monkeypatch.setattr(CORE, "system_utc_now", late)
        monkeypatch.setattr("pipeline.datafeed.fetch_prices", late.fetch)
        assert script.record(path, study) == 0                      # already recorded: quiet, and no download at all
        assert (study / "receipts.jsonl").read_bytes() == before and late.reads and late.now == pd.Timestamp(start)


def test_the_append_gate_rereads_the_clock_for_the_new_row_only():
    """Finalization and the write are adjacent; if the clock still moves past the open between them, the write is refused, and the
    rows already in the ledger are validated, never re-timed."""
    r = receipt(created="2026-11-01T23:59:00+00:00")
    times = iter([pd.Timestamp("2026-11-01T23:59:58Z"), pd.Timestamp(OPEN)])
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "receipts.jsonl"
        with pytest.raises(ValueError, match=C.WINDOW_CLOSED_DURING_RECORDING):
            C.append_live_receipt(path, r, merged_at_utc=MERGED, clock=lambda: next(times),
                                  validate=lambda x: C.validate_receipt(x, pathway=C.SYNTHETIC))
        assert not path.exists()
        ok = C.append_live_receipt(path, r, merged_at_utc=MERGED, clock=lambda: pd.Timestamp("2026-11-01T23:59:58Z"),
                                   validate=lambda x: C.validate_receipt(x, pathway=C.SYNTHETIC))
        assert pd.Timestamp(ok["createdAtUtc"]) == pd.Timestamp("2026-11-01T23:59:58Z") and ok["receiptSha256"] == CORE.receipt_digest(ok)


def test_a_merge_on_the_signal_date_makes_the_first_signal_ineligible(tmp_path, monkeypatch):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch_for())
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: "2026-10-30T01:00:00+00:00")     # 10:00 KST on the signal date
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp("2026-10-31T04:35:00Z"))
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(generated="2026-10-31T04:30:00+00:00")))
    script.run_all(path, tmp_path / "study")
    status = _status(tmp_path / "study")
    assert status["signalRecordState"] == "SKIPPED" and "SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY" in status["signalRecordReason"]


def test_a_hook_failure_in_the_paper_ledger_step_leaves_a_machine_readable_status(tmp_path, monkeypatch):
    import importlib
    update = importlib.import_module("scripts.update_ledger")
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch_for())
    monkeypatch.setattr(script, "run_all", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    data = site()
    data["modelVersion"] = "m"
    path = tmp_path / "site.json"
    path.write_text(json.dumps(data))
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    assert update.main([str(path), str(ledger)]) == 0                   # research failure is not a production failure
    status = json.loads((ledger / "research-strategies" / C.STUDY / "publication-status.json").read_text())
    assert status["status"] == "STEP_FAILED" and status["signalRecordState"] == "NOT_ATTEMPTED" and "boom" in status["error"]


def test_a_missing_price_collection_never_stops_the_signal_record(tmp_path, monkeypatch):
    script, _, study = _run_all(tmp_path, monkeypatch, "2026-10-31T04:35:00Z", generated="2026-10-31T04:30:00+00:00")
    first = (study / "receipts.jsonl").read_bytes()
    # Rerun later in the window with the vendor refusing: the receipt bytes are unchanged and nothing is added.
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp("2026-11-01T04:35:00Z"))
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    script.run_all(tmp_path / "site.json", study)
    assert (study / "receipts.jsonl").read_bytes() == first


def test_a_non_zero_research_exit_is_a_workflow_warning_and_never_the_ledgers_exit(tmp_path, monkeypatch, capsys):
    import importlib
    update = importlib.import_module("scripts.update_ledger")
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch_for())
    data = site()
    data["modelVersion"] = "m"
    path = tmp_path / "site.json"
    path.write_text(json.dumps(data))
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    for code, warned in ((0, False), (1, True)):
        monkeypatch.setattr(script, "run_all", lambda *a, _c=code: _c)
        assert update.main([str(path), str(ledger)]) == 0
        out = capsys.readouterr().out
        assert ("::warning::kr-selection-challenger-v1 research steps exited 1" in out) is warned


# --------------------------------------------------------------------------- #
# Regression tests for the independent-audit P1 findings
# --------------------------------------------------------------------------- #
def _with_vendor_frames(frames: dict, s=None):
    """The artifact the production build would publish if the vendor had returned ``frames`` for those names."""
    s = s or site()
    rows = {r["ticker"]: r for r in s["longTerm"]["regions"]["KR"]["validationCrossSection"]}
    for t, frame in frames.items():
        f = production_features(frame)
        rows[t]["risk"]["downsideVolPct"] = f["downsideVolPct"]
        s["details"][t].update({"lastClose": f["lastClose"], "ma200": f["ma200"], "pct52wHigh": f["pct52wHigh"]})
    return s


def test_a_feature_window_missing_one_or_two_krx_sessions_is_never_ranked():
    """The audit counterexample: 338 and 339 vendor rows (so mom12_1Pct exists and the old guard passed) with one or two KRX sessions
    absent inside the last year. Production computes all three features over the rows it got, so each 252-row window spans 253-254
    sessions. Both names would be ranked first in CH_LOWVOL and among the first in CH_HIGH52; neither is."""
    from pipeline import longterm as LT
    days = RC.sessions("2025-11-01", SESSION, "KR")
    gaps = {"100001.KS": [days[-120]], "100002.KS": [days[-60], days[-200]]}
    gapped = {t: bars_for(t, history=340, drop=d) for t, d in gaps.items()}
    for frame in gapped.values():
        assert len(frame) >= 330 and LT.momentum_12_1(frame["Close"]) is not None      # the mom12_1Pct guard reads it as full
    s = _with_vendor_frames(gapped)
    r = receipt(s, overrides=gapped)
    for book in C.CHALLENGERS:
        assert not set(gaps) & {x["ticker"] for x in r["books"][book]["slots"]}
        assert r["books"][book]["excluded"]["FEATURE_WINDOW_INCOMPLETE"] == 2
    # The same names with complete calendars are ranked: the exclusion is the gap, not the name.
    full = {t: bars_for(t, history=340) for t in gaps}
    r = receipt(_with_vendor_frames(full), overrides=full)
    assert set(gaps) <= {x["ticker"] for x in r["books"]["CH_LOWVOL"]["slots"]}
    assert set(gaps) <= {x["ticker"] for x in r["books"]["CH_HIGH52"]["slots"]}
    assert r["universe"]["featureVerification"]["basis"] == C.FEATURE_BARS_BASIS


def test_a_short_history_is_never_ranked():
    """longterm.downside_vol_252 answers from as few as 20 negative returns; 60 sessions are not a 252-session window."""
    short = {t: bars_for(t, history=60) for t in ("100000.KS", "100003.KS")}      # index % 3 == 0: the last 60 moves are falls
    s = _with_vendor_frames(short)
    assert all(s["longTerm"]["regions"]["KR"]["validationCrossSection"][i]["risk"]["downsideVolPct"] for i in (0, 3))
    r = receipt(s, overrides=short)
    assert not set(short) & {x["ticker"] for x in r["books"]["CH_LOWVOL"]["slots"]}
    assert r["books"]["CH_LOWVOL"]["excluded"]["FEATURE_WINDOW_INCOMPLETE"] == 2


def test_a_vendor_row_on_a_closed_day_inside_the_window_is_never_ranked():
    """2026-10-09 is a KRX holiday: a row dated on it was inside production's 252-row window and is not a session."""
    odd = {"100001.KS": bars_for("100001.KS", holiday_rows=["2026-10-09"])}
    r = receipt(_with_vendor_frames(odd), overrides=odd)
    for book in C.CHALLENGERS:
        assert "100001.KS" not in {x["ticker"] for x in r["books"][book]["slots"]}
        assert r["books"][book]["excluded"]["FEATURE_WINDOW_INCOMPLETE"] == 1


@pytest.mark.parametrize("field,delta,books", [
    ("downsideVolPct", 0.2, ["CH_LOWVOL"]), ("pct52wHigh", -0.3, ["CH_HIGH52"]), ("ma200", 5.0, ["CH_HIGH52"]),
    ("lastClose", 1.0, ["CH_LOWVOL", "CH_HIGH52"]),
])
def test_an_artifact_value_the_verified_frame_does_not_reproduce_is_never_ranked(field, delta, books):
    s = site()
    row = s["longTerm"]["regions"]["KR"]["validationCrossSection"][1]
    if field == "downsideVolPct":
        row["risk"][field] += delta
    else:
        s["details"]["100001.KS"][field] += delta
    r = receipt(s)
    for book in books:
        assert "100001.KS" not in {x["ticker"] for x in r["books"][book]["slots"]}
        assert r["books"][book]["excluded"]["FEATURE_VALUE_MISMATCH"] == 1
    # Inside the artifact's own rounding the same value is reproduced.
    assert C._close_enough(6.3, 6.349999, 0.05) and not C._close_enough(6.3, 6.36, 0.05)


def test_a_partial_verification_download_refuses_the_receipt_rather_than_shrinking_the_book():
    with pytest.raises(ValueError, match="PRICE_FETCH_INCOMPLETE: 1 of"):
        receipt(overrides={"100001.KS": None})


def test_a_vendor_refusal_at_record_time_is_refused_and_a_later_run_in_the_window_records(tmp_path, monkeypatch):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    monkeypatch.setattr(C, "merged_at_from_git", lambda *a: MERGED)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: pd.Timestamp("2026-10-31T04:35:00Z"))
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site(generated="2026-10-31T04:30:00+00:00")))
    study = tmp_path / "study"
    assert script.record(path, study) == 1
    state = json.loads((study / "publication-status.record.json").read_text())
    assert state["status"] == "REFUSED" and state["reason"].startswith("PRICE_FETCH_INCOMPLETE") and not (study / "receipts.jsonl").exists()
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", fetch_for())
    assert script.record(path, study) == 0 and len((study / "receipts.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("missing_in,expected_short", [
    ("h126", ["h126"]), ("model", ["versusExistingModel"]), ("both", ["h126", "versusExistingModel"]),
])
def test_supported_needs_every_series_within_the_none_budget_never_two_outcomes(missing_in, expected_short):
    """H252 complete on 104 receipts; the H126 series, the CTRL_MODEL5 pairs, or both, valid on only TWO receipts. The old gate read the
    H252 count alone and called this SUPPORTED."""
    rng = np.random.default_rng(1)
    values = list(0.06 + 0.01 * rng.standard_normal(104))
    receipts, outcomes = _ledger(104, values)
    for o in outcomes:
        i = int(o["receiptSha256"], 16)
        if i < 2:
            continue
        if missing_in in ("h126", "both") and o["horizonSessions"] == 126:
            o["books"]["CH_LOWVOL"]["netExcessReturn"] = None
        if missing_in in ("model", "both") and o["horizonSessions"] == 252:
            o["books"]["CTRL_MODEL5"]["netExcessReturn"] = None
    out = C.assess(receipts, outcomes, SPEC, path_metrics=GOOD_PATH)["challengers"]["CH_LOWVOL"]
    assert out["verdict"] == "INCONCLUSIVE_DATA" and out["primary"]["seriesShortOfCohort"] == expected_short
    assert out["primary"]["n"] == 104                                       # the H252 series alone would have passed
    # Exactly at the budget (10 None in each series) the verdict is still decided.
    receipts, outcomes = _ledger(104, values, missing=set(range(10)))
    assert C.assess(receipts, outcomes, SPEC, path_metrics=GOOD_PATH)["challengers"]["CH_LOWVOL"]["verdict"] == "SUPPORTED"


def test_an_undefined_risk_metric_is_inconclusive_not_a_crash():
    receipts, outcomes = _ledger(104, [0.06] * 52 + [0.07] * 52)
    for bad in ({"sharpe": None}, {"maxDrawdown": None}, {"sharpe": float("nan")}):
        paths = {**GOOD_PATH, "CH_LOWVOL": {**GOOD_PATH["CH_LOWVOL"], **bad}}
        assert C.assess(receipts, outcomes, SPEC, path_metrics=paths)["challengers"]["CH_LOWVOL"]["verdict"] == "INCONCLUSIVE_DATA"


def test_a_failed_vendor_download_is_deferred_and_regraded_never_a_permanent_none():
    r = receipt()
    a = r["books"]["CH_LOWVOL"]["slots"][0]["ticker"]
    frames, maturity = _frames(r, 126, growth={C.BENCHMARK: 0.10})
    at_maturity = _after(maturity)
    window_closed = pd.Timestamp(str(CORE.maturity_session(r["executionDate"], 126 + C.OUTCOME_RETRY_SESSIONS).date())) \
        .tz_localize("UTC") + pd.Timedelta(hours=10)
    # 1. An empty download (vendor outage): deferred, not BENCHMARK_UNPRICED for ever.
    out = C.build_outcome(r, horizon=126, frames={}, now_utc=at_maturity, pathway=C.SYNTHETIC)
    assert out["resolution"] == "DEFERRED" and out["unresolved"] == ["BENCHMARK_UNPRICED"]
    with pytest.raises(ValueError, match="OUTCOME_DEFERRED_IS_NEVER_A_RECORD"):
        C.validate_outcome(out, pathway=C.SYNTHETIC)
    # 2. A partial download (one held name missing): deferred too.
    partial = {t: f for t, f in frames.items() if t != a}
    out = C.build_outcome(r, horizon=126, frames=partial, now_utc=at_maturity, pathway=C.SYNTHETIC)
    assert out["resolution"] == "DEFERRED" and out["unresolved"] == [f"{a}:NAME_OUTCOME_MISSING:NO_VENDOR_FRAME"]
    # 3. The next run's full download resolves it.
    out = C.build_outcome(r, horizon=126, frames=frames, now_utc=at_maturity, pathway=C.SYNTHETIC)
    assert out["resolution"] == "FINAL" and out["books"]["CH_LOWVOL"]["netExcessReturn"] is not None
    # 4. Still missing after the retry window: an empty or partial Yahoo answer is not a delisting. It stays DEFERRED, never written.
    out = C.build_outcome(r, horizon=126, frames=partial, now_utc=window_closed, pathway=C.SYNTHETIC)
    assert out["resolution"] == "DEFERRED" and out["unresolvedClasses"] == [C.PROVIDER] and out["retryUntilSession"] is None
    forced = {**out, "resolution": "FINAL_UNRESOLVED_AFTER_RETRY"}
    forced["recordSha256"] = hashlib.sha256(CORE.canonical({k: v for k, v in forced.items() if k != "recordSha256"})).hexdigest()
    with pytest.raises(ValueError, match="OUTCOME_PROVIDER_GAP_IS_NEVER_FINAL"):
        C.validate_outcome(forced, pathway=C.SYNTHETIC)
    # 5. A halt at maturity is retried the same way, and becomes TERMINAL_ECONOMICS_UNRESOLVED only after the window.
    halted = {t: f.copy() for t, f in frames.items()}
    halted[a].iloc[-1, halted[a].columns.get_loc("Volume")] = 0.0
    assert C.build_outcome(r, horizon=126, frames=halted, now_utc=at_maturity, pathway=C.SYNTHETIC)["resolution"] == "DEFERRED"
    late = C.build_outcome(r, horizon=126, frames=halted, now_utc=window_closed, pathway=C.SYNTHETIC)
    assert late["names"][a]["state"] == "TERMINAL_ECONOMICS_UNRESOLVED" and late["resolution"] == "FINAL_UNRESOLVED_AFTER_RETRY"
    assert late["unresolvedClasses"] == [C.ECONOMIC] and late["books"]["CH_LOWVOL"]["netExcessReturn"] is None
    C.validate_outcome(late, pathway=C.SYNTHETIC)
    # 6. A halt plus a provider gap is still a provider gap: nothing is final until the provider answers.
    both = {t: f for t, f in halted.items() if t != r["books"]["CH_LOWVOL"]["slots"][1]["ticker"]}
    assert C.build_outcome(r, horizon=126, frames=both, now_utc=window_closed, pathway=C.SYNTHETIC)["resolution"] == "DEFERRED"


def _session_after(execution, sessions):
    return pd.Timestamp(str(CORE.maturity_session(execution, sessions).date())).tz_localize("UTC") + pd.Timedelta(hours=10)


@pytest.mark.parametrize("outage", ["empty", "benchmark_only", "truncated"])
def test_a_seven_session_provider_outage_is_regraded_on_recovery(outage):
    """D0 is the maturity session. The vendor fails from D0 to D6 (one session past the old +5 window), then serves on D7. Under the
    old rule D6 wrote a permanent None; now every attempt is DEFERRED and D7 grades it."""
    r = receipt()
    frames, maturity = _frames(r, 126, growth={C.BENCHMARK: 0.10})
    held = r["books"]["CH_LOWVOL"]["slots"][0]["ticker"]
    bad = {"empty": {}, "benchmark_only": {C.BENCHMARK: frames[C.BENCHMARK]},
           "truncated": {**frames, held: frames[held].iloc[:-10]}}[outage]     # Yahoo's partial answer: the series stops early
    for day in range(7):
        out = C.build_outcome(r, horizon=126, frames=bad, now_utc=_session_after(r["executionDate"], 126 + day), pathway=C.SYNTHETIC)
        assert out["resolution"] == "DEFERRED" and C.PROVIDER in out["unresolvedClasses"], day
    out = C.build_outcome(r, horizon=126, frames=frames, now_utc=_session_after(r["executionDate"], 126 + 7), pathway=C.SYNTHETIC)
    assert out["resolution"] == "FINAL" and out["books"]["CH_LOWVOL"]["netExcessReturn"] is not None


def test_the_outcome_step_keeps_a_retryable_pending_state_and_never_rewrites_a_written_outcome(tmp_path, monkeypatch):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    study = tmp_path / "study"
    live = C.build_receipt(site(), "b" * 64, pathway=C.LIVE, created_at_utc=EVENING, now_utc=EVENING, merged_at_utc=MERGED,
                           code_identity={"commitSha": "c" * 40, "files": {"x": "d" * 64}}, spec=SPEC, spec_digest="e" * 64,
                           fetch_bars=fetch_for())
    C.append_receipt(study / script.RECEIPTS, live, pathway=C.LIVE)
    frames, _ = _frames(live, 126, growth={C.BENCHMARK: 0.05})
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: {})
    for day in range(7):                                                     # D0..D6: the vendor serves nothing
        monkeypatch.setattr(CORE, "system_utc_now", lambda d=day: _session_after(live["executionDate"], 126 + d))
        assert script.outcomes(study) == 0
        pending = json.loads((study / script.PENDING).read_text())
        assert pending["evidence"] is False and [p["attempts"] for p in pending["pending"]] == [day + 1]
        assert pending["pending"][0]["unresolvedClasses"] == [C.PROVIDER]
        assert not (study / script.OUTCOMES).exists() or not (study / script.OUTCOMES).read_text().strip()
    first_seen = pending["pending"][0]["firstDeferredAtUtc"]
    assert first_seen.startswith(str(CORE.maturity_session(live["executionDate"], 126).date()))
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: frames)
    monkeypatch.setattr(CORE, "system_utc_now", lambda: _session_after(live["executionDate"], 133))   # D7: recovered
    assert script.outcomes(study) == 0
    rows = C.read_outcomes(study / script.OUTCOMES, pathway=C.LIVE)
    assert [(o["horizonSessions"], o["resolution"]) for o in rows] == [(126, "FINAL")]
    assert json.loads((study / script.PENDING).read_text())["pending"] == []
    written = (study / script.OUTCOMES).read_bytes()
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: {})        # a later outage never touches it
    assert script.outcomes(study) == 0 and (study / script.OUTCOMES).read_bytes() == written


def test_the_outcome_step_writes_nothing_on_an_outage_and_grades_on_the_next_run(tmp_path, monkeypatch):
    import importlib
    script = importlib.import_module("scripts.record_kr_selection_challenger")
    study = tmp_path / "study"
    live = C.build_receipt(site(), "b" * 64, pathway=C.LIVE, created_at_utc=EVENING, now_utc=EVENING, merged_at_utc=MERGED,
                           code_identity={"commitSha": "c" * 40, "files": {"x": "d" * 64}}, spec=SPEC, spec_digest="e" * 64,
                           fetch_bars=fetch_for())
    C.append_receipt(study / script.RECEIPTS, live, pathway=C.LIVE)
    frames, maturity = _frames(live, 126, growth={C.BENCHMARK: 0.05})
    monkeypatch.setattr(CORE, "system_utc_now", lambda: _after(maturity))
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: {})
    assert script.outcomes(study) == 0
    status = json.loads((study / "publication-status.outcomes.json").read_text())
    assert status["status"] == "DEFERRED" and status["written"] == [] and status["deferred"][0][2] == ["BENCHMARK_UNPRICED"]
    assert not (study / script.OUTCOMES).exists() or not (study / script.OUTCOMES).read_text().strip()
    monkeypatch.setattr("pipeline.datafeed.fetch_prices", lambda *a, **k: frames)
    assert script.outcomes(study) == 0
    rows = C.read_outcomes(study / script.OUTCOMES, pathway=C.LIVE)
    assert [(o["horizonSessions"], o["resolution"]) for o in rows] == [(126, "FINAL")]
    before = (study / script.OUTCOMES).read_bytes()
    assert script.outcomes(study) == 0 and (study / script.OUTCOMES).read_bytes() == before      # never graded twice
    assert (study / script.RECEIPTS).read_bytes() == CORE.canonical(live) + b"\n"               # the receipt never moves
