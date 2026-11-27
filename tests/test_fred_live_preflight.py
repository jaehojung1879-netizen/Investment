"""Synthetic regression cases; no provider requests, fits or ledger writes."""
import pandas as pd
import pytest

from operations.fred_live_v1.gate import assess, fetch_once


def inputs():
    days = pd.date_range("2026-01-01", periods=4)
    macro = pd.DataFrame({"Treasury_10Y": [3.0] * 4, "Yield_Curve": [0.5] * 4}, index=days)
    series = {"Treasury_10Y": "DGS10", "Yield_Curve": "T10Y2Y"}
    avail = {
        "status": "FULL", "dataDegraded": False, "requested": 2, "fetched": 2,
        "series": {k: {"status": "OK", "seriesId": v} for k, v in series.items()},
        "mlMacroSeries": {"missing": [], "overlapVerified": True,
                          "allPresentThrough": "2026-01-04", "fetched": list(series)},
    }
    spec = {"columns": ["x"], "target": "target",
            "coveragePolicy": {"maxStalenessDays": 7, "minOverlapObservations": 3,
                               "latestAllowedTrainingStart": "2026-01-02"}}
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "target": [1.0, 0.0, 1.0, None]}, index=days)
    return {"model_version": "registered", "as_of": "2026-01-04", "macro": macro,
            "availability": avail, "expected_series": series,
            "plan": {"US:A:20:screen": dict(spec), "KR:B:20:screen": dict(spec)},
            "observed": {"US:A:20:screen": (frame, ["x"]), "KR:B:20:screen": (frame.copy(), ["x"])}}


def test_complete_evidence_is_not_writer_authorization():
    result = assess(**inputs())
    assert result["decision"] == "REGISTERED_INPUTS_OBSERVED"
    assert result["writerAuthorized"] is False
    assert result["productionEffect"] == "NONE"
    assert len(result["identities"]) == 2


@pytest.mark.parametrize("case", ["missing_slot", "extra_slot", "no_training", "missing_policy",
                                  "missing_series", "wrong_series_id", "partial", "bad_date",
                                  "missing_macro_col", "bad_policy", "empty_plan", "wrong_features"])
def test_gate_holds_incomplete_or_unregistered_evidence(case):
    data = inputs()
    slot = "KR:B:20:screen"
    if case == "missing_slot":
        data["observed"].pop(slot)
    elif case == "extra_slot":
        data["observed"]["extra"] = data["observed"][slot]
    elif case == "no_training":
        data["observed"][slot][0]["target"] = None
    elif case == "missing_policy":
        data["plan"][slot]["coveragePolicy"] = None
    elif case == "missing_series":
        data["availability"]["series"].pop("Yield_Curve")
    elif case == "wrong_series_id":
        data["availability"]["series"]["Yield_Curve"]["seriesId"] = "OTHER"
    elif case == "partial":
        data["availability"]["status"] = "PARTIAL"
    elif case == "bad_date":
        data["as_of"] = None
    elif case == "missing_macro_col":
        data["macro"] = data["macro"].drop(columns=["Yield_Curve"])
    elif case == "bad_policy":
        data["plan"][slot]["coveragePolicy"] = {
            "maxStalenessDays": True, "minOverlapObservations": 0,
            "latestAllowedTrainingStart": "2026-01-02"}
    elif case == "empty_plan":
        data["plan"] = {}
        data["observed"] = {}
    elif case == "wrong_features":
        data["observed"][slot] = (data["observed"][slot][0].assign(z=1), ["z"])
    result = assess(**data)
    assert result["decision"] == "HOLD"
    assert result["reasons"]
    assert result["writerAuthorized"] is False


def test_fetch_passes_exact_config_once(monkeypatch):
    from types import SimpleNamespace

    from operations.fred_live_v1 import gate

    calls = []
    frame = object()

    def fake(series, key, start, **kwargs):
        calls.append((series, key, start, kwargs))
        return frame, {"status": "PARTIAL"}

    monkeypatch.setattr(gate.fr, "fetch_macro_with_availability", fake)
    cfg = SimpleNamespace(fred_series={"x": "X"}, fred_api_key="synthetic",
                          model=SimpleNamespace(history_start="2010-01-01"))
    result = fetch_once(cfg, timeout=10)
    assert result[0] is frame
    assert calls == [({"x": "X"}, "synthetic", "2010-01-01", {"timeout": 10})]
