"""Synthetic tests for the C2 runner adapters and its owner gate. No real outcome is read."""
import json
import math
import random
from datetime import date, timedelta

import pytest

from research.alpha_evidence_sprint_v2 import c2_attribution as A
from research.alpha_evidence_sprint_v2 import c2_attribution_run as RUN


def saved_row(i, weights, growth, rf=1.002, cash=None):
    cash = 1 - sum(weights.values()) if cash is None else cash
    end = sum(weights[t] * growth[t] for t in weights) + cash * rf
    return {"date": f"2020-{i // 28 + 1:02d}-{i % 28 + 1:02d}", "endDate": f"2020-{i // 28 + 1:02d}-{i % 28 + 1:02d}",
            "signalDate": f"s{i}", "weights": weights, "terminalWeights": {t: weights[t] * growth[t] / end for t in weights},
            "grossReturn": end - 1, "dailyRiskFreeNav": [1.0, rf], "dailyDates": ["2020-01-02", "2020-01-31"]}


def iso(i):
    return (date(2013, 1, 7) + timedelta(days=30 * i)).isoformat()


def test_window_closes_never_reads_past_the_signal_date():
    sessions = [f"d{i:04d}" for i in range(400)]
    series = {"X": {d: float(i + 1) for i, d in enumerate(sessions)}}
    got = RUN.window_closes(series, sessions, "X", "d0300")
    assert len(got) == 253 and got[-1] == 301.0 and got[0] == 49.0
    assert RUN.window_closes(series, sessions, "X", "d0100") == []          # not enough history
    series["X"].pop("d0299")
    assert RUN.window_closes(series, sessions, "X", "d0300").count(None) == 1  # a gap is None, not filled


def test_readiness_reads_no_outcome_fields():
    assert set(RUN.READINESS_KEYS).isdisjoint({"dailyGrossNav", "grossReturn", "terminalWeights",
                                               "costAdjustedReturn", "benchmarkReturn", "dailyBenchmarkNav"})


def test_execute_refuses_without_owner_authorization(tmp_path, monkeypatch):
    monkeypatch.setattr(RUN, "AUTH", tmp_path / "missing.json")
    assert RUN.authorization_ok("x") == (False, "NO_OWNER_AUTHORIZATION_FILE")
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"phrase": "APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 abc",
                                "codeSha256": {"c2_attribution.py": "0", "c2_attribution_run.py": "0"}}))
    monkeypatch.setattr(RUN, "AUTH", auth)
    assert RUN.authorization_ok("def")[1] == "AUTHORIZATION_PHRASE_MISMATCH"
    assert RUN.authorization_ok("abc")[1] == "AUTHORIZED_CODE_HASH_MISMATCH"
    with pytest.raises(SystemExit, match="REFUSED"):
        monkeypatch.setattr(RUN, "AUTH", tmp_path / "missing.json")
        RUN.execute(tmp_path)


def test_analyse_end_to_end_recovers_planted_selection_and_rejects_identity_failures():
    rng = random.Random(5)
    rows, etf_px = [], {}
    level = 100.0
    for i in range(155):
        names = [f"N{(i + k) % 9}" for k in range(3)]
        weights = {t: 0.2 for t in names}
        r_e = rng.gauss(0.008, 0.05)
        growth = {t: 1 + 0.8 * r_e + 0.2 * 0.002 + 0.01 for t in names}   # +1% per block planted
        row = saved_row(i, weights, growth)
        row["date"], row["endDate"] = iso(i), iso(i + 1)
        etf_px[row["date"]] = level
        level *= 1 + r_e
        etf_px[row["endDate"]] = level
        rows.append(row)
    pre_rng = random.Random(9)
    etf_hist = [pre_rng.gauss(0, 0.01) for _ in range(252)]

    def pre(ticker, signal):
        e = [100.0]
        s = [100.0]
        for r in etf_hist:
            e.append(e[-1] * (1 + r))
            s.append(s[-1] * (1 + 0.8 * r))
        return s, e

    out = RUN.analyse(rows, lambda d: etf_px[d], pre, lambda *a: 0.0005, 155 * 21 / 252)
    assert out["verdict"] == "SELECTION_SURVIVES_FIXED_EXPOSURE"
    assert out["reconstruction"]["status"] == "NOT_CHECKED"
    for k, d in out["byCost"]["1x"]["decomposition"].items():
        assert d["blocks"] == 155 and d["maxIdentityResidual"] < 1e-12
    one = out["byCost"]["1x"]["scenarios"]["BOK_POLICY_PROXY"]["selectionAnnualized"]
    # selection per block = s * (0.01 + (0.2*0.002) - (1-b)*R_F) with b = 0.8, R_F = 0.002
    assert one["mean"] == pytest.approx(0.6 * 0.01 * (155 / (155 * 21 / 252)), rel=1e-6)
    assert out["failures"] == [] and out["clipped"] == 0
    bad = [dict(rows[0], grossReturn=rows[0]["grossReturn"] + 0.05)] + rows[1:]
    out_bad = RUN.analyse(bad, lambda d: etf_px[d], pre, lambda *a: 0.0005, 155 * 21 / 252)
    assert out_bad["failures"][0]["reason"].startswith("BUY_AND_HOLD_IDENTITY_FAILED")
    assert out_bad["byCost"]["1x"]["c2"]["status"] == "PATH_INCOMPLETE"


def test_cash_growth_band_is_ordered():
    g = RUN.cash_growth({"dailyRiskFreeNav": [1.0, 1.003], "dailyDates": ["2020-01-02", "2020-02-01"]})
    assert g["ZERO"] == 1.0 < g["BOK_POLICY_PROXY"] == 1.003 < g["BOK_POLICY_PLUS_100BP"]


def test_frozen_spec_matches_module_constants():
    spec = json.loads(RUN.SPEC.read_text())
    assert spec["cashScenarios"]["registeredBand"] == list(A.CASH_SCENARIOS)
    assert spec["promotionEligible"] is False
    for item in spec["pinnedInputs"]["files"]:
        assert RUN.sha256(RUN.ROOT / item["path"]) == item["sha256"], item["path"]


# --------------------------------------------------------------------------- #
# regression tests for the 2026-11-09 audit fixes
# --------------------------------------------------------------------------- #
def _world(n=40, seed=3, beta_gap_at=None):
    rng = random.Random(seed)
    rows, etf_px, level = [], {}, 100.0
    for i in range(n):
        names = [f"N{(i // 2 + k) % 7}" for k in range(3)]       # names persist two blocks
        weights = {t: 0.15 + 0.05 * k for k, t in enumerate(names)}
        r_e = rng.gauss(0.008, 0.05)
        growth = {t: 1 + 1.1 * r_e + rng.gauss(0, 0.03) for t in names}
        row = saved_row(i, weights, growth)
        row["date"], row["endDate"] = iso(i), iso(i + 1)
        etf_px[row["date"]] = level
        level *= 1 + r_e
        etf_px[row["endDate"]] = level
        rows.append(row)
    hist = [random.Random(9).gauss(0, 0.01) for _ in range(252)]

    def pre(ticker, signal):
        e, s_ = [100.0], [100.0]
        for r in hist:
            e.append(e[-1] * (1 + r))
            s_.append(s_[-1] * (1 + 1.1 * r))
        if beta_gap_at is not None and signal == f"s{beta_gap_at}":
            return [], e
        return s_, e
    return rows, etf_px, pre


def _cost(as_of, side, is_etf):
    return 0.0002 + (0.0 if is_etf or side == "buy" else 0.0023)


def test_c2_net_path_equals_the_replay_account_function():
    """C2 reconstruction must charge exactly what scripts/run_weekly_passive_first_replay.account
    charged the published C2 path: same drifted prior book, same dated legs."""
    from scripts import run_weekly_passive_first_replay as R
    rows, etf_px, pre = _world()
    blocks, failures = RUN.build_blocks(rows, lambda d: etf_px[d], pre, RUN.cash_growth)
    assert failures == []
    results = RUN.attribute_all(blocks)
    c2_net, _ = RUN.path_returns(blocks, results, _cost)
    replay_rows = []
    for b, r in zip(blocks, results):
        s = sum(b.weights.values())
        w = {**b.weights, RUN.ETF: 1 - s}
        end = {t: w[t] * (b.growth[t] if t != RUN.ETF else b.etf_growth) for t in w}
        tot = sum(end.values())
        replay_rows.append({"date": b.date, "weights": w, "grossReturn": tot - 1,
                            "terminalWeights": {t: v / tot for t, v in end.items()},
                            "dailyGrossNav": [1.0, tot], "dailyDates": [b.date, b.end_date],
                            "benchmarkReturn": b.etf_growth - 1, "regionByTicker": {t: "KR" for t in w}})
    real = R.W.trade_cost_fraction
    try:
        R.W.trade_cost_fraction = lambda region, as_of, *, is_benchmark, side: _cost(as_of, side, is_benchmark)
        acc = R.account(replay_rows, {RUN.ETF})
    finally:
        R.W.trade_cost_fraction = real
    mine = 1.0
    for x in c2_net:
        mine *= 1 + x
    assert mine == pytest.approx(acc["nav"][-1], rel=1e-12)
    assert [b for b, _ in acc["blockReturns"]] == pytest.approx(c2_net, abs=1e-12)


def test_etf_alternative_pays_its_initial_buy_like_the_replay_p0():
    rows, etf_px, pre = _world()
    blocks, _ = RUN.build_blocks(rows, lambda d: etf_px[d], pre, RUN.cash_growth)
    etf_net = RUN.etf_path(blocks, _cost)
    assert etf_net[0] == pytest.approx((1 - 0.0002) * blocks[0].etf_growth - 1, abs=1e-15)
    assert etf_net[1:] == pytest.approx([b.etf_growth - 1 for b in blocks[1:]], abs=1e-15)


def test_a_missing_beta_keeps_c2_valued_and_breaks_only_the_control_path():
    rows, etf_px, pre = _world(beta_gap_at=5)
    blocks, _ = RUN.build_blocks(rows, lambda d: etf_px[d], pre, RUN.cash_growth)
    results = RUN.attribute_all(blocks)
    assert results[5].status.startswith("BETA_UNAVAILABLE")
    c2_net, ctrl = RUN.path_returns(blocks, results, _cost)
    assert all(math.isfinite(x) for x in c2_net)                     # C2 is never restarted or lost
    assert all(math.isfinite(x) for x in ctrl["ZERO"][:5])
    assert all(math.isnan(x) for x in ctrl["ZERO"][5:])               # control never silently restarted
    out = RUN.analyse(rows, lambda d: etf_px[d], pre, _cost, 40 * 21 / 252)
    assert out["byCost"]["1x"]["c2"]["status"] == "COMPLETE"
    assert out["unattributableShare"] == pytest.approx(1 / 40)
    assert out["betaUnavailable"][0]["date"] == rows[5]["date"]


def test_reconstruction_mismatch_forces_insufficient():
    rows, etf_px, pre = _world()
    years = RUN.RV_span(rows[0]["date"], rows[-1]["endDate"])
    probe = RUN.analyse(rows, lambda d: etf_px[d], pre, _cost, years)
    mine = probe["reconstruction"]
    assert mine["status"] == "NOT_CHECKED"
    detail = {}
    blocks, _ = RUN.build_blocks(rows, lambda d: etf_px[d], pre, RUN.cash_growth)
    c2_net, _ = RUN.path_returns(blocks, RUN.attribute_all(blocks), _cost, 1.0, detail)
    etf_net = RUN.etf_path(blocks, _cost)
    nav_c2, nav_e = math.prod(1 + x for x in c2_net), math.prod(1 + x for x in etf_net)
    exact = {"C2": {"cagrPct": round(100 * (nav_c2 ** (1 / years) - 1), 3),
                    "cumulativeNetReturnPct": round(100 * (nav_c2 - 1), 3)},
             "P0": {"cagrPct": round(100 * (nav_e ** (1 / years) - 1), 3),
                    "cumulativeNetReturnPct": round(100 * (nav_e - 1), 3)}}
    good = RUN.analyse(rows, lambda d: etf_px[d], pre, _cost, years, published=exact)
    assert good["reconstruction"]["status"] == "REPRODUCES_PUBLISHED_C2_AND_P0"
    off = {**exact, "C2": {**exact["C2"], "cagrPct": exact["C2"]["cagrPct"] + 0.002}}
    bad = RUN.analyse(rows, lambda d: etf_px[d], pre, _cost, years, published=off)
    assert bad["reconstruction"]["status"] == "RECONSTRUCTION_MISMATCH"
    assert bad["verdict"] == "SOURCE_OR_SAMPLE_INSUFFICIENT"


def test_turnover_and_clip_reporting_and_recent_slice():
    rows, etf_px, pre = _world()
    years = RUN.RV_span(rows[0]["date"], rows[-1]["endDate"])
    out = RUN.analyse(rows, lambda d: etf_px[d], pre, _cost, years, recent_from=iso(30))
    t = out["turnoverOneWayPerYear"]
    assert t["replaced"] > 0 and t["retargeted"] >= 0
    assert out["clips"]["count"] == out["clipped"]
    recent = out["byCost"]["1x"]["recent"]
    assert recent["blocks"] == 10 and recent["firstBlock"] == iso(30)
    h = out["byCost"]["1x"]["horizonC2MinusControl"]["ZERO"]
    assert h["h126"]["windows"] == 35 and h["h126"]["nonOverlapping"] == 6
    assert h["h252"]["windows"] == 29 and h["h252"]["nonOverlapping"] == 3


def test_authorization_is_bound_to_an_owner_commit(tmp_path, monkeypatch):
    spec = "f" * 64
    auth = tmp_path / "AUTHORIZATION-c2.json"
    auth.write_text(json.dumps({
        "phrase": f"APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 {spec}",
        "codeSha256": {"c2_attribution.py": RUN.sha256(RUN.HERE / "c2_attribution.py"),
                       "c2_attribution_run.py": RUN.sha256(RUN.HERE / "c2_attribution_run.py")}}))
    monkeypatch.setattr(RUN, "AUTH", auth)
    assert RUN.authorization_ok(spec, check_git=False) == (True, "AUTHORIZED_SYNTHETIC")

    def fake_git(answers):
        def run(*args):
            return answers[args[0]](args)
        return run
    rel = str((RUN.HERE / "AUTHORIZATION-c2.json").relative_to(RUN.ROOT))
    base = {"ls-files": lambda a: rel + "\n", "status": lambda a: "", "log": lambda a: "jaeho.jung1879@gmail.com\n"}
    monkeypatch.setattr(RUN, "_git", fake_git(base))
    assert RUN.authorization_ok(spec) == (True, "AUTHORIZED")
    monkeypatch.setattr(RUN, "_git", fake_git({**base, "log": lambda a: "noreply@anthropic.com\n"}))
    assert RUN.authorization_ok(spec)[1] == "AUTHORIZATION_NOT_COMMITTED_BY_OWNER"
    monkeypatch.setattr(RUN, "_git", fake_git({**base, "log": lambda a: "jaeho.jung1879@gmail.com\nnoreply@anthropic.com\n"}))
    assert RUN.authorization_ok(spec)[1] == "AUTHORIZATION_NOT_COMMITTED_BY_OWNER"   # an agent edit after approval
    monkeypatch.setattr(RUN, "_git", fake_git({**base, "status": lambda a: " M c2_attribution.py\n"}))
    assert RUN.authorization_ok(spec)[1] == "GATED_FILES_MODIFIED_SINCE_COMMIT"

    def untracked(a):
        raise RuntimeError("error: pathspec did not match")
    monkeypatch.setattr(RUN, "_git", fake_git({**base, "ls-files": untracked}))
    assert RUN.authorization_ok(spec)[1].startswith("GIT_UNAVAILABLE")


def test_one_shot_refuses_an_existing_result(tmp_path, monkeypatch):
    monkeypatch.setattr(RUN, "_git", lambda *a: "")
    monkeypatch.setattr(RUN, "RESULT", RUN.HERE / "c2-fixed-exposure-attribution-v1-result.json")
    assert RUN.one_shot_ok() == (True, "NOT_YET_EXECUTED")
    monkeypatch.setattr(RUN, "_git", lambda *a: "abc123\n")
    assert RUN.one_shot_ok()[1] == "RESULT_ALREADY_IN_GIT_HISTORY"
    existing = tmp_path / "r.json"
    existing.write_text("{}")
    monkeypatch.setattr(RUN, "RESULT", existing)
    assert RUN.one_shot_ok()[1] == "RESULT_ALREADY_EXISTS"


def test_execute_path_names_resolve():
    """The owner-gated path was never run in CI; its first draft called a function that does not
    exist (replay_valuation.normalize_daily_series). Pin every name it resolves."""
    from pipeline import market_dates, provenance, replay_calendar, replay_inputs, weekly_decision
    assert callable(market_dates.normalize_daily_series) and callable(replay_calendar.sessions)
    assert callable(replay_inputs.unpack) and hasattr(replay_inputs.InputStore, "load")
    assert callable(weekly_decision.trade_cost_fraction) and provenance.REPLAY_VERSION == "replay-v16"
    assert weekly_decision.trade_cost_fraction("KR", "2020-01-02", is_benchmark=True, side="sell") > 0
    import inspect
    src = inspect.getsource(RUN.load_inputs)
    assert "RV.normalize_daily_series" not in src and "market_dates import normalize_daily_series" in src
