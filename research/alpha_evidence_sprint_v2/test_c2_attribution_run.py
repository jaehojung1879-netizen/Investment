"""Synthetic tests for the C2 runner adapters and its owner gate. No real outcome is read."""
import json
import random

import pytest

from research.alpha_evidence_sprint_v2 import c2_attribution as A
from research.alpha_evidence_sprint_v2 import c2_attribution_run as RUN


def saved_row(i, weights, growth, rf=1.002, cash=None):
    cash = 1 - sum(weights.values()) if cash is None else cash
    end = sum(weights[t] * growth[t] for t in weights) + cash * rf
    return {"date": f"2020-{i // 28 + 1:02d}-{i % 28 + 1:02d}", "endDate": f"2020-{i // 28 + 1:02d}-{i % 28 + 1:02d}",
            "signalDate": f"s{i}", "weights": weights, "terminalWeights": {t: weights[t] * growth[t] / end for t in weights},
            "grossReturn": end - 1, "dailyRiskFreeNav": [1.0, rf], "dailyDates": ["2020-01-02", "2020-01-31"]}


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
        row["date"], row["endDate"] = f"D{i:03d}", f"D{i + 1:03d}"
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
