"""Network-free tests on invented data for industry-information-transfer-v1."""
from __future__ import annotations

import ast
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import h2_contract as H  # noqa: E402
import transfer as T  # noqa: E402


def weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


SESSIONS = T.Sessions(weekdays(date(2014, 1, 2), 2000))


def test_next_session_availability_is_conservative():
    d = date(2014, 4, 10)  # Thursday
    assert not T.available(d, d, SESSIONS)                     # same day: never
    assert T.available(d, date(2014, 4, 11), SESSIONS)          # next session close
    assert not T.available(date(2014, 4, 11), date(2014, 4, 11), SESSIONS)


def test_quarter_arithmetic_round_trips():
    for q in (date(2014, 3, 31), date(2014, 6, 30), date(2014, 9, 30), date(2014, 12, 31)):
        assert T.quarter_from_index(T.quarter_index(q)) == q
    assert T.quarter_from_index(T.quarter_index(date(2015, 3, 31)) - 1) == date(2014, 12, 31)


def test_growth_definitions_refuse_undefined_denominators_and_clip():
    assert T.revenue_growth(110.0, 100.0) == pytest.approx(0.0953, abs=1e-4)
    assert T.revenue_growth(None, 100.0) is None and T.revenue_growth(100.0, 0.0) is None
    assert T.revenue_growth(1e9, 1.0) == T.CLIP_REVENUE
    assert T.op_change(10.0, 5.0, 100.0) == pytest.approx(0.05)
    assert T.op_change(10.0, 5.0, None) is None


def _obs(corp, q, day, y, industry, cap=1.0):
    return T.Obs(corp=corp, quarter=q, disclosed=day, y=y, y_op=None, industry=industry, market_cap=cap)


def test_build_rows_uses_only_peers_available_before_origin_and_never_the_target():
    q, prev = date(2014, 6, 30), date(2014, 3, 31)
    obs = [_obs(c, prev, date(2014, 4, 20), 0.0, "A" if c < "e" else "B") for c in "abcdefghij"]
    obs += [_obs("a", q, date(2014, 7, 1), 0.10, "A"), _obs("b", q, date(2014, 7, 2), 0.20, "A"),
            _obs("c", q, date(2014, 7, 3), 0.30, "A"),
            _obs("f", q, date(2014, 7, 1), -0.1, "B"), _obs("g", q, date(2014, 7, 1), -0.2, "B"),
            _obs("h", q, date(2014, 7, 2), -0.3, "B"), _obs("i", q, date(2014, 7, 2), -0.4, "B"),
            # target d reports on 7/10; origin is 7/9; peers usable if next session after them <= 7/9
            _obs("d", q, date(2014, 7, 10), 0.5, "A"),
            # a same-day / late peer that must not be used for d
            _obs("e", q, date(2014, 7, 9), 9.9 / 10, "A")]
    attrition = {}
    rows = T.build_rows(obs, SESSIONS, attrition=attrition)
    target = [r for r in rows if r.corp == "d"][0]
    assert target.origin == date(2014, 7, 9)
    assert target.n_ind == 3 and target.ind == pytest.approx(0.2)        # a, b, c only; e excluded (not usable yet)
    assert target.n_mkt == 7 and "e" not in [p[0] for p in target.peers]
    assert all(r.corp != p[0] for r in rows for p in r.peers)
    assert attrition["units"] == len(obs)


def test_missing_own_history_or_industry_drops_the_row_instead_of_filling_zero():
    q = date(2014, 6, 30)
    obs = [_obs(c, q, date(2014, 7, 1), 0.1, "A") for c in "abcdef"] + [_obs("z", q, date(2014, 7, 20), 0.2, None),
                                                                       _obs("z", date(2014, 3, 31), date(2014, 4, 20), 0.1, None)]
    attrition = {}
    rows = T.build_rows(obs, SESSIONS, attrition=attrition)
    assert rows == []
    assert attrition == {"units": 8, "noOwnHistory": 7, "noIndustry": 1}


def _synthetic_panel(seed: int, signal: float):
    """Industry common shock observed early by peers; target loads on it with weight ``signal``."""
    rng = random.Random(seed)
    obs = []
    industries = {c: "AB"[i % 2] for i, c in enumerate(f"f{k:02d}" for k in range(40))}
    for qi in range(T.quarter_index(date(2014, 3, 31)), T.quarter_index(date(2014, 3, 31)) + 24):
        q = T.quarter_from_index(qi)
        shock = {"A": rng.gauss(0, 0.2), "B": rng.gauss(0, 0.2)}
        base = SESSIONS.next_after(q + timedelta(days=5))
        for i, (corp, ind) in enumerate(sorted(industries.items())):
            day = base + timedelta(days=(i % 20))
            y = signal * shock[ind] + rng.gauss(0, 0.1)
            obs.append(T.Obs(corp=corp, quarter=q, disclosed=SESSIONS.next_after(day - timedelta(days=1)) or day,
                             y=y, y_op=None, industry=ind))
    return obs


def test_oos_comparison_detects_planted_transfer_and_not_its_absence():
    with_signal = T.oos_compare(T.build_rows(_synthetic_panel(1, 1.0), SESSIONS), ("own", "mkt"), ("own", "mkt", "ind"))
    without = T.oos_compare(T.build_rows(_synthetic_panel(1, 0.0), SESSIONS), ("own", "mkt"), ("own", "mkt", "ind"))
    assert with_signal["quartersEvaluated"] > 5
    assert with_signal["delta"]["mean"] > 0 and with_signal["delta"]["p"] < 0.05
    assert without["delta"]["mean"] < with_signal["delta"]["mean"]


def test_training_never_contains_the_test_quarter_or_the_one_before():
    rows = T.build_rows(_synthetic_panel(2, 1.0), SESSIONS)
    # poison every target in the last two quarters of the training gap: forecasts for later quarters must not change
    res1 = T.oos_compare(rows, ("own", "mkt"), ("own", "mkt", "ind"))
    last = max(r.quarter for r in rows)
    for r in rows:
        if r.quarter == last:
            r.y = 99.0
    res2 = T.oos_compare(rows, ("own", "mkt"), ("own", "mkt", "ind"))
    keep = [p for p in res1["perQuarter"] if p["quarter"] < T.quarter_from_index(T.quarter_index(last) - 1).isoformat()]
    keep2 = [p for p in res2["perQuarter"] if p["quarter"] in {k["quarter"] for k in keep}]
    assert [p["mseChallenger"] for p in keep] == [p["mseChallenger"] for p in keep2]


def test_permutation_preserves_group_sizes_per_quarter():
    obs = _synthetic_panel(3, 1.0)
    perm = T.permuted_industries(obs, random.Random(5))
    for q in {o.quarter for o in obs}:
        orig = sorted(o.industry for o in obs if o.quarter == q)
        new = sorted(perm[(o.corp, q)] for o in obs if o.quarter == q)
        assert orig == new


def test_nw_summary_and_holm_keep_unrun_slots_at_p_one():
    s = T.nw_summary([0.1, 0.2, 0.15, 0.12, 0.18, 0.11])
    assert s["mean"] == pytest.approx(0.1433, abs=1e-3) and s["p"] < 0.01
    h = T.holm({"a": 0.02, "b": None})
    assert h["a"]["threshold"] == 0.025 and h["a"]["rejectNull"] and h["b"]["p"] == 1.0
    assert not T.holm({"a": 0.03, "b": None})["a"]["rejectNull"]


def test_decide_h1_rules():
    good = {"quartersEvaluated": 40, "rowsEvaluated": 2000, "delta": {"mean": 0.001}}
    holm_ok = {"rejectNull": True}
    assert T.decide_h1(good, 0.01, 0.0001, holm_ok) == "KEEP"
    assert T.decide_h1(good, 0.20, 0.0001, holm_ok) == "INCONCLUSIVE"
    assert T.decide_h1({**good, "delta": {"mean": -0.001}}, 0.01, 0.0, holm_ok) == "REJECT"
    assert T.decide_h1({**good, "quartersEvaluated": 10}, 0.01, 0.0, holm_ok) == "DATA_BLOCKED"


# --------------------------------------------------------------------------- H2 contract
def test_h2_refuses_without_authorization(tmp_path):
    contract = tmp_path / "c.json"
    contract.write_text('{"x": 1}')
    with pytest.raises(H.NotAuthorized, match="AUTHORIZATION_ABSENT"):
        H.check_authorization(tmp_path / "missing.json", contract, require_git=False)
    auth = tmp_path / "a.json"
    digest = H.contract_sha256(contract)
    auth.write_text(json.dumps({"studyId": "industry-information-transfer-v1", "contractSha256": digest,
                                "approval": "APPROVE something else", "approvedBy": H.OWNER}))
    with pytest.raises(H.NotAuthorized, match="approval"):
        H.check_authorization(auth, contract, require_git=False)
    auth.write_text(json.dumps({"studyId": "industry-information-transfer-v1", "contractSha256": digest,
                                "approval": f"APPROVE KR_PHASE_D_EXCEPTION industry-information-transfer-v1-h2 {digest}",
                                "approvedBy": H.OWNER}))
    assert H.check_authorization(auth, contract, require_git=False) == digest
    contract.write_text('{"x": 2}')  # editing the contract voids the approval
    with pytest.raises(H.NotAuthorized, match="contractSha256"):
        H.check_authorization(auth, contract, require_git=False)


def test_the_committed_contract_is_not_authorized_in_this_change():
    assert not H.AUTHORIZATION.exists()
    with pytest.raises(H.NotAuthorized):
        H.check_authorization()
    with pytest.raises(H.NotAuthorized):
        H.main(["--execute", "--units", "x", "--panel", "y", "--out", "z"])


def test_paired_contrast_on_invented_prices_measures_only_the_entry_gap():
    sessions = [f"2020-01-{d:02d}" for d in range(1, 32)]
    bench = {s: 100.0 for s in sessions}
    # stock rises 1% per session; leg A enters 5 sessions earlier than leg B, both hold 10 sessions
    closes = {t: {s: 100.0 * (1.01 ** i) * (1 + 0.1 * k) for i, s in enumerate(sessions)} for k, t in enumerate("abcd")}
    units = [{"ticker": t, "quarter": "2019-12-31", "y": float(k), "prelimDate": "2020-01-02", "formalDate": "2020-01-07"}
             for k, t in enumerate("abcd")]
    res = H.paired_contrast(units, {"sessions": sessions, "closes": closes, "benchmark": bench}, 10, authorized_digest="x")
    q = res["perQuarter"]["2019-12-31"]
    assert q["n"] == 4 and q["D"] == pytest.approx(0.0, abs=1e-12)  # identical growth paths -> no timing difference
    with pytest.raises(H.NotAuthorized):
        H.paired_contrast(units, {"sessions": sessions, "closes": closes, "benchmark": bench}, 10, authorized_digest="")
    short = H.paired_contrast(units, {"sessions": sessions, "closes": closes, "benchmark": bench}, 40, authorized_digest="x")
    assert short["quarters"] == 0 and short["unitsDroppedFromBothLegs"] == 4


def test_no_module_reads_forward_returns_or_labels():
    forbidden = {"replay_valuation", "kelly_portfolio", "historical_outcomes", "attach_labels", "target_from_sessions"}
    for name in ("transfer.py", "run.py"):
        tree = ast.parse((HERE / name).read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
            a.name.split(".")[-1] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        assert not names & forbidden, (name, names & forbidden)
