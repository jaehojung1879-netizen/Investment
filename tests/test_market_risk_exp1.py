"""Market-risk experiment 1 (historical forecast comparison): leakage, maturity, common samples, data lag,
reproducibility and the one-shot harness. No test joins a real signal value with a real label."""
from __future__ import annotations

import ast
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pytest

from research.market_risk_discovery_v1 import baseline_census as B
from research.market_risk_discovery_v1 import exp1_design as E
from research.market_risk_discovery_v1 import exp1_execute as X
from research.market_risk_discovery_v1 import exp1_panels as EP
from research.market_risk_discovery_v1 import stage2_design as D

HERE = Path(E.__file__).resolve().parent
STARTS = (40, 80, 130, 170, 215, 255)


def synthetic(seed=0, effect=0.0, n=300, slope_from=0):
    """Fully synthetic month-ends; credit_z carries a planted lead of `effect` sd before each start."""
    rng = np.random.default_rng(seed)
    idx = 21 * np.arange(n)
    starts = {f"EP{k}": 21 * s + 10 for k, s in enumerate(STARTS)}
    pre = np.array([any(0 < s - i <= D.HORIZON for s in starts.values()) for i in idx])
    rows = []
    for t in range(n):
        hit = [e for e, s in starts.items() if idx[t] < s <= idx[t] + D.HORIZON]
        rows.append({"idx": int(idx[t]), "date": f"{1990 + t // 12:04d}-{t % 12 + 1:02d}-28",
                     "gap": float(rng.normal()), "vol": float(rng.normal()), "flag": float(rng.random() < 0.2),
                     "credit_z": float(rng.normal() + effect * pre[t]), "vix": float(rng.normal()),
                     "vix_slope": float(rng.normal()) if t >= slope_from else None,
                     "y": 1 if hit else (0 if idx[t] + D.HORIZON <= idx[-1] else None), "episode": hit[0] if hit else None})
    refits = D.refit_points([(r["date"], r["idx"]) for r in rows])
    return rows, refits, starts


def test_planted_credit_information_shows_up_only_in_m3():
    rows, refits, starts = synthetic(1, effect=2.5)
    out = E.evaluate(rows, refits, starts)["A"]
    assert out["status"] == "COMPUTED"
    assert out["models"]["M3"]["dBrierVsM1"] > 0 and out["models"]["M3"]["brier"] < out["models"]["M1"]["brier"]
    assert out["models"]["M3"]["brier"] < out["models"]["M4"]["brier"]


def test_unmatured_labels_never_reach_a_prediction():
    rows, refits, starts = synthetic(2, effect=1.0)
    p = E.Panel(E.sample_rows(rows, "A"))
    start = E.evaluation_start(p, refits)
    base = E.walk_forward(p, refits, start, E.SAMPLES["A"]["models"])
    year = start + 6
    poisoned = E.Panel(E.sample_rows(rows, "A"))
    bad = poisoned.labelled & (poisoned.idx + D.HORIZON > refits[year])
    poisoned.y = poisoned.y.copy()
    poisoned.y[bad] = 1 - poisoned.y[bad]
    again = E.walk_forward(poisoned, refits, start, E.SAMPLES["A"]["models"])
    keep = p.year[p.labelled & (p.year >= start)] <= year
    for m in base:
        assert np.allclose(base[m][keep], again[m][keep])


def test_common_sample_drops_rows_missing_any_required_input():
    rows, refits, starts = synthetic(3, slope_from=150)
    a, b = E.sample_rows(rows, "A"), E.sample_rows(rows, "B")
    assert len(a) == 300 and len(b) == 150 and all(r["vix_slope"] is not None for r in b)


def test_sample_b_reports_data_insufficient_instead_of_a_number():
    rows, refits, starts = synthetic(4, slope_from=260)
    out = E.evaluate(rows, refits, starts)["B"]
    assert out["status"] == "DATA_INSUFFICIENT" and "models" not in out


def test_reproducible():
    rows, refits, starts = synthetic(5, effect=1.0)
    assert json.dumps(E.evaluate(rows, refits, starts), sort_keys=True) == \
        json.dumps(E.evaluate(rows, refits, starts), sort_keys=True)


def test_warning_lead_and_misses_are_counted_per_episode():
    rows, refits, starts = synthetic(6, effect=3.0)
    out = E.evaluate(rows, refits, starts)["A"]["models"]["M3"]["warnings"]
    for e, rec in out["episodes"].items():
        assert rec["warned"] == (rec["firstWarning"] is not None)
        if rec["warned"]:
            assert 0 < rec["leadSessions"] <= D.HORIZON
    assert set(out["missedEpisodes"]) == {e for e, r in out["episodes"].items() if not r["warned"]}


def test_close_on_or_before_never_reads_a_later_close():
    s = {"2020-01-31": 10.0, "2020-02-03": 99.0}
    assert EP.close_on_or_before(s, "2020-02-01") == 10.0
    assert EP.close_on_or_before({"2020-02-10": 1.0}, "2020-02-01") is None


def test_credit_z_reads_no_later_month(monkeypatch):
    full = B.credit_series()
    keys = sorted(full)
    cut = {k: full[k] for k in keys[:200]}
    whole = EP.credit_z()
    monkeypatch.setattr(B, "credit_series", lambda: cut)
    part = EP.credit_z()
    assert part and all(whole[k] == pytest.approx(v) for k, v in part.items())


def test_real_structure_is_outcome_free_and_pinned():
    c = EP.rows("presence")
    assert all(r[f] in (None, 0.0) for r in c["rows"] for f in ("flag", "credit_z", "vix", "vix_slope"))
    a = E.structure(E.Panel(E.sample_rows(c["rows"], "A")), c["refits"])
    b = E.structure(E.Panel(E.sample_rows(c["rows"], "B")), c["refits"])
    assert a["pass"] and a["evaluationRows"] == 128 and a["independentEvaluationEpisodes"] == 5
    assert not b["pass"] and b["independentEvaluationEpisodes"] == 2


def test_signal_mode_carries_no_label():
    assert all(r["y"] is None and r["episode"] is None for r in EP.rows("signal")["rows"])


def test_only_the_harness_asks_for_real_rows():
    for path in HERE.glob("exp1_*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "rows" and node.args \
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value == "real":
                assert path.name == "exp1_execute.py", path


def test_the_one_authorized_run_happened_once_and_cannot_repeat():
    """State after the owner-approved run: the marker and result exist, the result carries the approved protocol
    hash, the authorization still matches the protocol, and any further run is refused before computing."""
    psha = X.PROTOCOL_SHA.read_text().split()[0]
    spec = json.loads(X.PROTOCOL.read_text())
    assert psha == X.sha(X.PROTOCOL) == "816e1644895bd86062226b5c58aaa52b7758569e51a368a43d9caede8314b04c"
    X.check_authorization(json.loads(X.AUTHORIZATION.read_text()), psha, spec["pins"])
    res = json.loads(X.RESULT.read_text())
    assert res["marker"]["protocolSha256"] == psha and res["inferentialClaim"] is None
    assert json.loads(X.MARKER.read_text())["protocolSha256"] == psha and not X.FAILURE.exists()
    with pytest.raises(X.ExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        X.verify(require_authorization=True)
    with pytest.raises(X.ExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        X.execute(compute=lambda: pytest.fail("recomputed"))


def _contender(tmp: str, barrier, queue):
    from research.market_risk_discovery_v1 import exp1_execute as H
    t = Path(tmp)
    H.RESULTS, H.MARKER, H.RESULT, H.FAILURE = t, t / "m.json", t / "r.json", t / "f.json"
    barrier.wait()
    try:
        H.execute(compute=lambda: (t / f"c-{mp.current_process().pid}").write_text("x") and {"ok": 1},
                  verify_fn=lambda: {"protocolSha256": "s"})
        queue.put("WON")
    except H.ExecutionRefused as exc:
        queue.put(str(exc))


def test_exactly_one_process_runs(tmp_path):
    ctx = mp.get_context("spawn")
    k = 5
    barrier, queue = ctx.Barrier(k), ctx.Queue()
    procs = [ctx.Process(target=_contender, args=(str(tmp_path), barrier, queue)) for _ in range(k)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    out = sorted(queue.get(timeout=5) for _ in range(k))
    assert out.count("WON") == 1 and out.count("ONE_SHOT_ALREADY_SPENT") == k - 1
    assert len(list(tmp_path.glob("c-*"))) == 1 and (tmp_path / "r.json").exists()


def _auth(psha, pins, /, **over):
    a = {"protocolSha256": psha, "pins": pins, "scope": {**X.EXPECTED_SCOPE, "protocolSha256": psha},
         "approvedBy": "owner", "approvalQuote": X.REQUIRED_QUOTE.format(sha=psha),
         "approvedAtUtc": "2026-11-20T00:00:00+00:00", "authenticity": "UNAUTHENTICATED_FILE_RECORD_OF_OWNER_APPROVAL"}
    a.update(over)
    return a


@pytest.mark.parametrize("over, code", [
    ({"scope": {**X.EXPECTED_SCOPE, "action": "EXECUTE_AND_DEPLOY", "protocolSha256": "P"}}, "AUTHORIZATION_SCOPE_DIFFERS"),
    ({"scope": {**X.EXPECTED_SCOPE, "excludes": [], "protocolSha256": "P"}}, "AUTHORIZATION_SCOPE_DIFFERS"),
    ({"protocolSha256": "Q"}, "AUTHORIZATION_PINS_ANOTHER_PROTOCOL"),
    ({"approvalQuote": "승인"}, "APPROVAL_QUOTE_LACKS_REQUIRED_SENTENCE"),
    ({"approvedAtUtc": "2999-01-01T00:00:00+00:00"}, "APPROVED_AT_INVALID"),
])
def test_authorization_scope_is_exact(over, code):
    with pytest.raises(X.ExecutionRefused, match=code):
        X.check_authorization(_auth("P", {"code": {}}, **over), "P", {"code": {}})
    X.check_authorization(_auth("P", {"code": {}}), "P", {"code": {}})
