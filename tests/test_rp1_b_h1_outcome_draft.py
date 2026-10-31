"""Invented prices only. Adversarial probes never fetch, write or evaluate LIVE."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import longterm as LT
from pipeline import prospective_receipt_core as C
from pipeline import replay_calendar as RC
from pipeline import rp1_b_h1_outcome_draft as D
from pipeline import rp1_b_h1_state as B

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    days = RC.sessions("2025-01-01", "2026-10-30", "KR")[-273:]
    rows, frames = [], {}
    for i in range(12):
        t = f"SYN{i:03}"
        rows.append({"ticker": t, "sector": "INDUSTRIALS", "issuerId": t, "industry": "SYN_INDUSTRY",
                     "isPreferredShare": False, "priceAsOf": "2026-10-30", "positiveVolumeSessions20": 20,
                     "medianTradedValue60Krw": 1_000_000_000})
        close = 100 * np.exp(np.arange(273) * i / 10000)
        frames[t] = pd.DataFrame({"Close": close, "Open": close, "High": close * 1.01,
                                  "Low": close * .99, "Volume": 10000}, index=days)
    return rows, frames


def select(rows, frames, **kw):
    return D.synthetic_selection(rows, frames, **{"signal": "2026-10-30", "snapshot_date": "2026-10-29",
                                                "available_at": "2026-10-29T09:00:00Z", **kw})


def test_draft_is_not_registration_even_when_forged():
    assert D.live_gate({"status": "REGISTERED", "ownerApproval": True})["computed"] is False
    proposal = json.loads((ROOT / "docs/research-program/proposals/rp1-b-h1-outcome-v1-owner-draft.json").read_text())
    assert proposal["status"] == D.STATUS
    assert all(d["ownerApproval"] is None for d in proposal["decisions"])
    spec = B.load_spec()
    assert [d["id"] for d in proposal["decisions"]] == [d["id"] for d in spec["outcomeEvaluation"]["openDecisions"]]
    assert B.outcome_gate(spec)["status"] == B.OUTCOME_BLOCKED
    forged = copy.deepcopy(spec)
    forged["outcomeEvaluation"]["status"] = "REGISTERED"
    with pytest.raises(ValueError, match="OUTCOME_CONTRACT_STATE_UNEXPECTED"):
        B.outcome_gate(forged)


def test_calendar_deadline_and_no_sliding_origin():
    rows = D.schedule()
    assert rows[0] == {"block": 1, "entrySession": "2026-11-02", "maturitySession": "2027-02-02", "stateSignalDate": "2026-10-30"}
    assert rows[11]["maturitySession"] == "2029-11-23"
    assert rows[-1]["maturitySession"] == "2031-12-16"
    assert all(a["maturitySession"] == b["entrySession"] for a, b in zip(rows, rows[1:]))
    assert not C.has_matured("2026-11-02", 63, "2027-02-02T08:59:59.999999Z")
    assert C.has_matured("2026-11-02", 63, "2027-02-02T09:00:00Z")


def test_original_momentum_literal_offsets_and_273_session_minimum():
    x = pd.Series(np.arange(1, 274, dtype=float))
    assert LT.momentum_12_1(x) == x.iloc[-21] / x.iloc[-252] - 1
    assert LT.momentum_12_1(x.iloc[1:]) is None
    rows, frames = fixture()
    before = copy.deepcopy(rows)
    selection = select(rows, frames)
    assert selection["long"] == ["SYN011", "SYN010", "SYN009", "SYN008"]
    assert selection["short"] == ["SYN003", "SYN002", "SYN001", "SYN000"]
    assert rows == before


@pytest.mark.parametrize("bad", ["snapshot", "availability", "kst_boundary", "future", "duplicate", "label"])
def test_lookahead_and_outcome_inputs_rejected(bad):
    rows, frames = fixture()
    kw = {}
    if bad == "snapshot":
        kw["snapshot_date"] = "2026-10-30"
    elif bad == "availability":
        kw["available_at"] = "2026-11-01T00:00:00Z"
    elif bad == "kst_boundary":
        kw["available_at"] = "2026-10-29T15:00:00Z"
    elif bad == "future":
        frames["SYN000"].loc[pd.Timestamp("2026-11-02")] = [100, 100, 101, 99, 100]
    elif bad == "duplicate":
        frames["SYN000"] = pd.concat([frames["SYN000"], frames["SYN000"].iloc[-1:]])
    else:
        rows[0]["realizedReturn"] = 100
    with pytest.raises(ValueError):
        select(rows, frames, **kw)


@pytest.mark.parametrize("bad", ["hole", "zero_volume", "invalid_volume", "close"])
def test_missing_session_never_compresses_window(bad):
    rows, frames = fixture()
    f = frames["SYN011"]
    if bad == "hole":
        frames["SYN011"] = f.drop(f.index[-100])
    else:
        f.loc[f.index[-100], "Close" if bad == "close" else "Volume"] = np.nan if bad in ("invalid_volume", "close") else 0
    s = select(rows, frames)
    assert "SYN011" not in s["long"] + s["short"]
    assert s["n"] == 11
    assert "MOMENTUM_WINDOW_INCOMPLETE" in s["excluded"]["SYN011"]


@pytest.mark.parametrize("count", [0, 5, 6])
def test_support_and_missing_state_are_not_inference(count):
    s = D.support(["adverse"] * 6 + ["notAdverse"] * count + ["unobserved", "undetermined"])
    assert s["enough"] == (count >= 6)
    assert s["p"] == 1


@pytest.mark.parametrize("bad", ["premature", "missing", "terminal", "wrong_session", "dividend_basis"])
def test_selected_missing_security_blocks_paired_spread(bad):
    rows, frames = fixture()
    s = select(rows, frames)
    before = copy.deepcopy(s)
    outcomes = {t: {"state": "PRICED_TOTAL_RETURN", "exitSession": "2027-02-02", "return": .1, "basisVerified": True}
                for t in s["long"] + s["short"]}
    t = s["long"][0]
    now = "2027-02-02T09:00:00Z"
    if bad == "premature":
        with pytest.raises(ValueError, match="NOT_MATURED"):
            D.synthetic_spread(s, outcomes, execution="2026-11-02", now="2027-02-02T08:59:59Z")
        return
    if bad == "missing":
        del outcomes[t]
    elif bad == "terminal":
        outcomes[t]["state"] = "TERMINAL_CONSIDERATION_UNRESOLVED"
    elif bad == "wrong_session":
        outcomes[t]["exitSession"] = "2027-02-03"
    else:
        outcomes[t]["basisVerified"] = False
    result = D.synthetic_spread(s, outcomes, execution="2026-11-02", now=now)
    assert result["spread"] is None and result["p"] == 1
    assert s == before


def test_attribution_identity_and_no_cross_state_pooling():
    daily = np.random.default_rng(123).normal(size=(12 * 63, 6))
    weights = np.tile([.5, .5, 0, 0, -.5, -.5], (12, 1))
    states = ["adverse", "notAdverse"] * 6
    d, x, ci = D.state_contrast_attribution(daily, weights, states)
    blocks = np.einsum("bsi,bi->b", daily.reshape(12, 63, 6), weights)
    assert d.sum() == pytest.approx(blocks[1::2].mean() - blocks[::2].mean())
    assert x.sum() == pytest.approx(1)
    assert ci["estimate"] == pytest.approx(d.sum())
    with pytest.raises(ValueError, match="INSUFFICIENT_STATE_BLOCKS"):
        D.state_contrast_attribution(daily, weights, ["adverse"] * 12)


def test_premature_probe_never_reads_outcomes():
    class Poison(dict):
        def get(self, *args, **kwargs):
            raise AssertionError("OUTCOME_READ_BEFORE_MATURITY")

    selection = {"status": "SYNTHETIC_FIXTURE", "long": ["SYNA"], "short": ["SYNB"]}
    with pytest.raises(ValueError, match="NOT_MATURED"):
        D.synthetic_spread(selection, Poison(), execution="2026-11-02", now="2027-02-02T08:59:59Z")


def test_invented_probe_cannot_be_used_as_a_live_arithmetic_entrypoint():
    selection = {"status": "SYNTHETIC_FIXTURE", "long": ["005930.KS"], "short": ["000660.KS"]}
    with pytest.raises(ValueError, match="SYNTHETIC_ONLY"):
        D.synthetic_spread(selection, {}, execution="2026-11-02", now="2027-02-02T09:00:00Z")
