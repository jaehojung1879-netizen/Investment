"""Market Risk Discovery Stage 2 v2 (independent audit remediation): the conditional randomization test on synthetic
worlds, the label-free generator gate, the exclusive one-shot claim across real OS processes, and the structured
authorization scope. No test joins a real credit value with a real label."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pytest

from research.market_risk_discovery_v1 import stage2_design as D
from research.market_risk_discovery_v1 import stage2v2_crt as G
from research.market_risk_discovery_v1 import stage2v2_synthetic as S
from research.market_risk_discovery_v1 import stage3_execute_v2 as X

HERE = Path(G.__file__).resolve().parent


# ------------------------------------------------------------------ CRT on synthetic worlds


def _accepted(env, seed, delta=0.0):
    rng = np.random.default_rng(seed)
    while True:
        w = S.world(env, rng, delta)
        if D.structure_gate(w["panel"], w["refits"], w["seq"])["pass"]:
            return w


def test_generator_simulation_keeps_initial_values_and_rates():
    rng = np.random.default_rng(0)
    n = 300
    gap, vol = rng.normal(0.05, 0.03, n), np.exp(rng.normal(np.log(0.15), 0.3, n))
    flags = (rng.random(n) < 1 / (1 + np.exp(-(-1.5 + 6 * (vol - 0.15))))).astype(float)
    g = G.Generator(gap, vol, flags)
    sims = g.simulate(400, np.random.default_rng(1))
    assert np.all(sims[:, :2] == flags[:2])
    assert abs(sims.mean() - flags.mean()) < 0.05
    assert np.corrcoef(sims.mean(axis=0), vol)[0, 1] > 0.5


def _band_world(seed):
    """The audit's counterexample type: C = 1[vol in its 40-70% band] (deterministic, non-monotone in X), the label
    hazard depends on X only, through that same band; the linear M1 cannot represent it and C can."""
    rng = np.random.default_rng(seed)
    n = 355
    s = S._ar(rng, n, 0.9)
    gap = 0.05 - 0.06 * s + 0.03 * S._ar(rng, n, 0.7)
    vol = np.exp(np.log(0.15) + 0.35 * s + 0.15 * S._ar(rng, n, 0.7))
    lo, hi = np.quantile(vol, [0.4, 0.7])
    flag = ((vol > lo) & (vol <= hi)).astype(float)
    return S._rows(np.random.default_rng(100 + seed), n, gap, vol, flag, np.ones(n, bool),
                   1 / (1 + np.exp(-(-4.6 + 2.6 * flag))))


def test_audit_counterexample_fools_rotation_and_an_approximate_generator_but_not_the_gate():
    """Y _|_ C | X holds. The v1 rotation rejects. A CRT whose generator only APPROXIMATES the deterministic band
    (quadratic in vol) also rejects: CRT validity is exactly as good as the generator, which is why v2 never reports
    a CRT p without the label-free adequacy gate. The production (linear) generator fails that gate here, so the v2
    verdict is GENERATOR_INADEQUATE_NO_INFERENCE, not support."""
    w = _band_world(1)
    assert D.structure_gate(w["panel"], w["refits"], w["seq"])["pass"]
    assert D.primary(w["panel"], w["refits"], w["seq"])["rotationP"] <= 0.05
    quad = lambda a, b: np.column_stack([a, b, a ** 2, b ** 2])  # noqa: E731
    assert G.crt(w["panel"], w["refits"], w["seq"], w["gap"], w["vol"], draws=99, design=quad)["p"]["dBrier"] <= 0.05
    flags = np.array([v for _, v in w["seq"]])
    assert not G.adequacy(w["gap"], w["vol"], flags, w["months"], w["common"], draws=199)["adequate"]


def test_crt_detects_a_planted_credit_specific_effect():
    w = _accepted("S6", 7, delta=3.0)
    out = G.crt(w["panel"], w["refits"], w["seq"], w["gap"], w["vol"], draws=99)
    assert out["observed"]["dBrier"] > 0 and out["p"]["dBrier"] <= 0.05


def test_adequacy_rejects_a_non_monotone_deterministic_flag():
    """S2: a band of vol that the linear generator cannot represent must fail the label-free gate."""
    fails = 0
    for seed in range(3):
        w = _accepted("S2", 100 + seed)
        a = G.adequacy(w["gap"], w["vol"], np.array([v for _, v in w["seq"]]), w["months"], w["common"], draws=199)
        fails += not a["adequate"]
    assert fails >= 2


def test_verdict_v2_truth_table():
    ok = {"A": 0.1}
    assert G.verdict_v2(False, 0.1, 0.001, ok) == "GENERATOR_INADEQUATE_NO_INFERENCE"
    assert G.verdict_v2(True, 0.1, 0.01, ok) == "EXPLORATORY_CONDITIONAL_INFORMATION_SUPPORT"
    assert G.verdict_v2(True, 0.1, 0.2, ok) == "DIRECTIONAL_NOT_SEPARATED"
    assert G.verdict_v2(True, 0.1, 0.01, {"A": -0.1}) == "DIRECTIONAL_NOT_SEPARATED"
    assert G.verdict_v2(True, -0.1, 0.01, ok) == "NOT_DETECTED_UNDERPOWERED"


def test_synthetic_module_reads_no_real_data():
    tree = ast.parse((HERE / "stage2v2_synthetic.py").read_text())
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "panels" not in names and "label_census" not in names and "baseline_census" not in names


def test_real_generator_adequacy_is_label_free_and_reproducible():
    rec = json.loads((HERE / "evidence" / "stage2v2-generator-selection.json").read_text())
    assert rec["labelReads"] == 0 and rec["chosen"]["adequacy"]["adequate"]
    again = X.label_free_adequacy()
    assert again["adequate"] and again["outside95"] == rec["chosen"]["adequacy"]["outside95"]
    assert again["coefficients"] == pytest.approx(rec["chosen"]["adequacy"]["coefficients"])


# ------------------------------------------------------------------ exclusive one-shot across OS processes


def _contender(tmp: str, barrier, queue):
    from research.market_risk_discovery_v1 import stage3_execute_v2 as H
    t = Path(tmp)
    H.RESULTS, H.MARKER, H.RESULT, H.FAILURE = t, t / "marker.json", t / "result.json", t / "failed.json"

    def compute():
        (t / f"computed-{mp.current_process().pid}").write_text("joined")
        return {"verdict": "SYNTHETIC"}

    barrier.wait()
    try:
        H.execute(compute=compute, verify_fn=lambda: {"protocolSha256": "synthetic"})
        queue.put("WON")
    except H.ExecutionRefused as exc:
        queue.put(str(exc))


def test_exactly_one_of_many_processes_claims_the_one_shot(tmp_path):
    ctx = mp.get_context("spawn")
    k = 6
    barrier, queue = ctx.Barrier(k), ctx.Queue()
    procs = [ctx.Process(target=_contender, args=(str(tmp_path), barrier, queue)) for _ in range(k)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    outcomes = sorted(queue.get(timeout=5) for _ in range(k))
    assert outcomes.count("WON") == 1
    assert outcomes.count("ONE_SHOT_ALREADY_SPENT") == k - 1
    assert len(list(tmp_path.glob("computed-*"))) == 1
    assert json.loads((tmp_path / "result.json").read_text())["verdict"] == "SYNTHETIC"
    assert not list(tmp_path.glob(".*.tmp"))


def _paths(monkeypatch, tmp_path):
    monkeypatch.setattr(X, "RESULTS", tmp_path)
    monkeypatch.setattr(X, "MARKER", tmp_path / "marker.json")
    monkeypatch.setattr(X, "RESULT", tmp_path / "result.json")
    monkeypatch.setattr(X, "FAILURE", tmp_path / "failed.json")


def test_failure_after_the_claim_spends_the_study(tmp_path, monkeypatch):
    _paths(monkeypatch, tmp_path)

    def boom():
        raise RuntimeError("synthetic crash")

    with pytest.raises(RuntimeError):
        X.execute(compute=boom, verify_fn=lambda: {"protocolSha256": "synthetic"})
    assert (tmp_path / "marker.json").exists() and (tmp_path / "failed.json").exists()
    assert not (tmp_path / "result.json").exists()
    ran = []
    with pytest.raises(X.ExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        X.execute(compute=lambda: ran.append(1) or {}, verify_fn=lambda: {"protocolSha256": "synthetic"})
    assert ran == []
    with pytest.raises(X.ExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        X.verify(require_authorization=False)


def test_publish_never_overwrites(tmp_path):
    target = tmp_path / "r.json"
    X.publish(target, "first")
    with pytest.raises(FileExistsError):
        X.publish(target, "second")
    assert target.read_text() == "first" and not list(tmp_path.glob(".*.tmp"))


# ------------------------------------------------------------------ authorization scope


def _auth(psha, pins, /, **over):
    a = {"protocolSha256": psha, "pins": pins, "scope": {**X.EXPECTED_SCOPE, "protocolSha256": psha},
         "approvedBy": "owner", "approvalQuote": "... " + X.REQUIRED_QUOTE.format(sha=psha) + " ...",
         "approvedAtUtc": "2026-11-20T09:00:00+00:00", "authenticity": X.AUTHENTICITY}
    a.update(over)
    return a


@pytest.mark.parametrize("override, code", [
    ({"scope": {}}, "AUTHORIZATION_SCOPE_DIFFERS"),
    ({"scope": {"action": "MERGE_AND_DEPLOY"}}, "AUTHORIZATION_SCOPE_DIFFERS"),
    ({"scope": {**X.EXPECTED_SCOPE, "protocolSha256": "0" * 64}}, "AUTHORIZATION_SCOPE_DIFFERS"),
    ({"scope": {**X.EXPECTED_SCOPE, "maxExecutions": 2, "protocolSha256": "P"}}, "AUTHORIZATION_SCOPE_DIFFERS"),
    ({"protocolSha256": "0" * 64}, "AUTHORIZATION_PINS_ANOTHER_PROTOCOL"),
    ({"pins": {}}, "AUTHORIZATION_PINS_DIFFER"),
    ({"approvalQuote": "approved"}, "APPROVAL_QUOTE_LACKS_REQUIRED_SENTENCE"),
    ({"approvedBy": "  "}, "APPROVED_BY_MISSING"),
    ({"approvedAtUtc": "yesterday"}, "APPROVED_AT_NOT_ISO8601"),
    ({"approvedAtUtc": "2999-01-01T00:00:00+00:00"}, "APPROVED_AT_INVALID"),
    ({"approvedAtUtc": "2026-11-23T09:00:00"}, "APPROVED_AT_INVALID"),
    ({"authenticity": "CRYPTOGRAPHICALLY_VERIFIED"}, "AUTHENTICITY_ACKNOWLEDGEMENT_MISSING"),
])
def test_authorization_scope_is_checked_exactly(override, code):
    pins = {"code": {"a": "b"}}
    with pytest.raises(X.ExecutionRefused, match=code):
        X.check_authorization(_auth("P", pins, **override), "P", pins)


def test_authorization_rejects_extra_or_missing_keys():
    pins = {"code": {}}
    with pytest.raises(X.ExecutionRefused, match="AUTHORIZATION_KEYS_DIFFER"):
        X.check_authorization({**_auth("P", pins), "mergeApproved": True}, "P", pins)
    a = _auth("P", pins)
    del a["scope"]
    with pytest.raises(X.ExecutionRefused, match="AUTHORIZATION_KEYS_DIFFER"):
        X.check_authorization(a, "P", pins)


def test_a_correct_authorization_passes():
    pins = {"code": {}}
    X.check_authorization(_auth("P", pins), "P", pins, now=dt.datetime(2026, 12, 1, tzinfo=dt.timezone.utc))


# ------------------------------------------------------------------ protocol lineage


def test_v2_protocol_verifies_and_records_its_lineage():
    out = X.verify(require_authorization=False)
    spec = json.loads(X.PROTOCOL.read_text())
    assert out["protocolSha256"] == X.PROTOCOL_SHA.read_text().split()[0]
    assert spec["supersedes"]["sha256"] == hashlib.sha256((HERE / "protocol-stage2.json").read_bytes()).hexdigest()
    assert spec["stage3Executed"] is False and spec["creditLabelJoinsWhileWritingThis"] == 0
    assert spec["decision"] in ("READY_FOR_STAGE_3", "NOT_READY_FOR_INFERENTIAL_STAGE_3")


def test_no_v2_authorization_marker_or_result_is_committed():
    for p in (X.AUTHORIZATION, X.MARKER, X.RESULT, X.FAILURE):
        assert not p.exists()
