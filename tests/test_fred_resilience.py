"""FRED resilience and short-term ML model identity (issue #279). Deterministic: a local HTTP fake of FRED, no external network, invented
values only. The fake speaks FRED's XML so the REAL fredapi parsing and the REAL `datafeed.fetch_macro` run against it."""
import ast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest

from pipeline import datafeed
from pipeline import entry as ENTRY
from pipeline import features as F
from pipeline import fred_resilience as R
from pipeline import risk as RISK

ROOT = Path(__file__).resolve().parents[1]
SERIES = {"Treasury_10Y": "DGS10", "Treasury_2Y": "DGS2", "HY_Spread": "BAMLH0A0HYM2", "IG_Spread": "BAMLC0A0CM",
          "Headline_CPI": "CPIAUCSL"}
# Invented coverage thresholds that exercise the gate. NOT a proposal for the owner's numbers (R.COVERAGE_POLICY stays None).
POLICY = {"maxStalenessDays": 7, "minOverlapObservations": 252, "latestAllowedTrainingStart": "2012-12-31"}


def _xml(series_id, start="2011-01-03", n=40, step=1):
    days = pd.bdate_range(start, periods=n)
    rows = "".join(f'<observation realtime_start="2026-10-01" realtime_end="2026-10-01" date="{d.date()}" value="'
                   f'{"." if i == 3 else f"{1.0 + 0.01 * i + 0.1 * len(series_id):.4f}"}"/>' for i, d in enumerate(days[::step]))
    return f'<?xml version="1.0" encoding="utf-8" ?><observations count="{n}">{rows}</observations>'.encode()


class FakeFred:
    """script[series_id] = list of responses consumed in order (the last repeats): ("ok", start) | (code, message) | ("hang", seconds)."""

    def __init__(self, script):
        self.script, self.hits, self.lock = script, [], threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                q = parse_qs(urlparse(self.path).query)
                sid = q["series_id"][0]
                with owner.lock:
                    owner.hits.append(sid)
                    queue = owner.script.get(sid, [("ok", "2011-01-03")])
                    action = queue.pop(0) if len(queue) > 1 else queue[0]
                kind, arg, n = (*action, 40)[:3]
                if kind == "hang":
                    time.sleep(arg)
                    kind, arg = "ok", "2011-01-03"
                if kind == "ok":
                    body, code = _xml(sid, arg, n), 200
                else:
                    body = (f'<error code="{kind}" message="{arg}"/>' if arg is not None else f'<error code="{kind}"/>').encode()
                    code = kind
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "text/xml")
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}/fred"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake(monkeypatch):
    # The fake is local: never route it through an environment proxy.
    for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    servers = []

    def make(script=None):
        servers.append(FakeFred(dict(script or {})))
        return servers[-1]
    yield make
    for s in servers:
        s.close()


def fetch(server, series=SERIES, **kw):
    kw.setdefault("sleep", lambda s: None)
    client = R.timeout_fred("k" * 32, kw.pop("timeout", 2.0), root_url=server.url)
    return R.fetch_macro_with_availability(series, "k" * 32, "2011-01-01", client=client, **kw)


# --- normal path: identical to production ------------------------------------------------------------------------------------------
def test_normal_response_is_exactly_the_frame_datafeed_builds(fake, monkeypatch):
    server = fake()
    import fredapi

    class LocalFred(fredapi.Fred):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.root_url = server.url
    monkeypatch.setattr(fredapi, "Fred", LocalFred)
    cfg = SimpleNamespace(has_fred=True, fred_series=SERIES, fred_api_key="k" * 32)
    production = datafeed.fetch_macro(cfg, "2011-01-01")
    ours, avail = fetch(server)
    pd.testing.assert_frame_equal(production, ours)
    assert "Yield_Curve" in ours.columns and ours["Treasury_10Y"].isna().sum() == 1          # FRED's "." stays NaN, as in fredapi
    assert avail["status"] == R.FULL and avail["dataDegraded"] is False and avail["fetched"] == avail["requested"] == len(SERIES)
    assert all(r["attempts"] == 1 and r["httpStatus"] == 200 for r in avail["series"].values())
    assert R.data_source_label(avail).endswith("+ FRED (macro)")


# --- outages ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("code,kind", [(500, R.SERVER_ERROR), (503, R.SERVER_ERROR), (429, R.RATE_LIMITED)])
def test_total_outage_is_bounded_and_stated(fake, code, kind):
    server = fake({sid: [(code, None)] for sid in SERIES.values()})       # body without a message: fredapi raised ValueError(None)
    macro, avail = fetch(server, attempts=3, provider_failures_before_stop=2)
    assert macro is None and avail["status"] == R.UNAVAILABLE and avail["dataDegraded"] is True and avail["fetched"] == 0
    assert len(server.hits) == 2 * 3                                     # circuit breaker: 2 series x 3 attempts, not 5 x 3
    statuses = [r["status"] for r in avail["series"].values()]
    assert statuses[:2] == [kind, kind] and set(statuses[2:]) == {R.NOT_ATTEMPTED}
    assert avail["series"]["Treasury_10Y"]["httpStatus"] == code
    assert "FRED unavailable (0 of 5" in R.data_source_label(avail) and "FRED (macro)" not in R.data_source_label(avail)


def test_partial_outage_retry_recovery_and_non_retryable_client_error(fake):
    server = fake({"DGS10": [(429, "Too Many Requests"), ("ok", "2011-01-03")], "DGS2": [(500, "boom")],
                   "CPIAUCSL": [(400, "Bad Request.  The series does not exist.")]})
    macro, avail = fetch(server, attempts=3, provider_failures_before_stop=99)
    s = avail["series"]
    assert s["Treasury_10Y"]["status"] == R.OK and s["Treasury_10Y"]["attempts"] == 2
    assert s["Treasury_2Y"]["status"] == R.SERVER_ERROR and s["Treasury_2Y"]["attempts"] == 3 and s["Treasury_2Y"]["message"] == "boom"
    assert s["Headline_CPI"]["status"] == R.CLIENT_ERROR and s["Headline_CPI"]["attempts"] == 1           # never retried
    assert avail["status"] == R.PARTIAL and avail["dataDegraded"] and set(avail["failedSeries"]) == {"Treasury_2Y", "Headline_CPI"}
    assert "Yield_Curve" not in macro.columns                          # derived only from both inputs, never half-filled
    assert "FRED partial (3 of 5" in R.data_source_label(avail)
    assert avail["mlMacroSeries"]["missing"] == ["Treasury_2Y"]


def test_a_hanging_request_times_out_within_its_budget(fake):
    server = fake({sid: [("hang", 1.5)] for sid in SERIES.values()})
    began = time.monotonic()
    macro, avail = fetch(server, timeout=0.2, attempts=2, provider_failures_before_stop=2)
    elapsed = time.monotonic() - began
    assert macro is None and {r["status"] for r in list(avail["series"].values())[:2]} == {R.TIMEOUT}
    assert elapsed < 2 * 2 * 0.2 + 1.0                                   # 2 series x 2 attempts x 0.2 s plus slack, not 5 x 1.5 s


def test_backoff_is_bounded_and_only_between_retries(fake):
    waits = []
    server = fake({"DGS10": [(500, None)]})
    _, avail = fetch(server, series={"Treasury_10Y": "DGS10"}, attempts=3, backoff=(2.0, 4.0), sleep=waits.append)
    assert waits == [2.0, 4.0] and avail["series"]["Treasury_10Y"]["attempts"] == 3


def test_disabled_is_not_degraded_and_never_claims_fred():
    macro, avail = R.fetch_macro_with_availability(SERIES, None, "2011-01-01")
    assert macro is None and avail["status"] == R.DISABLED and avail["requested"] == len(SERIES)
    assert R.data_source_label(avail).endswith("FRED disabled")


# --- short history / training window ------------------------------------------------------------------------------------------------
def test_short_history_series_is_named_as_the_training_start_limit(fake):
    long = ("ok", "2011-01-03", 4100)                                     # through 2026
    server = fake({"DGS10": [long], "DGS2": [long], "CPIAUCSL": [long],
                   "BAMLH0A0HYM2": [("ok", "2023-09-18", 700)], "BAMLC0A0CM": [("ok", "2023-09-18", 700)]})
    _, avail = fetch(server)
    ml = avail["mlMacroSeries"]
    assert ml["overlapVerified"] and ml["allPresentFrom"] == "2023-09-18" and ml["limitingSeries"] == ["HY_Spread", "IG_Spread"]


def test_non_overlapping_series_have_no_all_present_date(fake):
    server = fake({"BAMLH0A0HYM2": [("ok", "2023-09-18")], "BAMLC0A0CM": [("ok", "2023-09-18")]})   # others end 2011-02
    _, avail = fetch(server)
    ml = avail["mlMacroSeries"]
    assert avail["status"] == R.FULL and ml["overlapVerified"] is False and ml["allPresentFrom"] is None and ml["limitingSeries"] == []


def test_a_missing_ml_series_leaves_no_all_present_date(fake):
    server = fake({"DGS2": [(500, None)]})
    _, avail = fetch(server, provider_failures_before_stop=99)
    assert avail["mlMacroSeries"]["missing"] == ["Treasury_2Y"] and avail["mlMacroSeries"]["allPresentFrom"] is None


def test_a_one_observation_series_counts_as_fetched_but_never_as_usable(fake):
    server = fake({"BAMLC0A0CM": [("ok", "2026-09-14", 1)]})
    macro, avail = fetch(server)
    assert avail["status"] == R.FULL and avail["series"]["IG_Spread"]["validObservations"] == 1
    assert avail["mlMacroSeries"]["overlapVerified"] is False                     # other series end 2011: no common day
    ok, reasons = R.ml_input_coverage(avail, "2026-09-14", {"A": "2011-02-01"}, POLICY, macro)
    assert ok is False and "ML_MACRO_SERIES_DO_NOT_OVERLAP" in reasons


def _price(days, seed=1):
    rng = np.random.default_rng(seed)
    close = pd.Series(100 * np.exp(np.cumsum(0.0003 + 0.01 * rng.standard_normal(len(days)))), index=days)
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close,
                         "Volume": 1e6 + rng.integers(0, 1000, len(days))}, index=days)


def _macro(days, late_start=None):
    t = np.arange(len(days))
    m = pd.DataFrame({name: 2.0 + 0.1 * np.sin(t / (5 + i)) for i, name in enumerate(SERIES)}, index=days)
    if late_start:
        m.loc[m.index < pd.Timestamp(late_start), ["HY_Spread", "IG_Spread"]] = np.nan
    m["Yield_Curve"] = m["Treasury_10Y"] - m["Treasury_2Y"]
    return m


def test_production_dropna_truncates_training_to_the_latest_ml_series_start():
    days = pd.bdate_range("2011-01-03", "2026-09-14")
    price = _price(days)
    data = F.add_targets(F.build_features(price, benchmark_close=price["Close"] * 0.9, vix=pd.Series(20.0, index=days),
                                          macro=_macro(days, late_start="2023-09-18")), [21])
    start = R.training_start(data, F.feature_columns(data), "target_21d")
    assert start == "2023-09-19"                                      # one session after 2023-09-18: macro enters with shift(1)
    full = F.add_targets(F.build_features(price, benchmark_close=price["Close"] * 0.9, vix=pd.Series(20.0, index=days),
                                          macro=_macro(days)), [21])
    assert R.training_start(full, F.feature_columns(full), "target_21d") < "2012-01-01"


# --- model identity ----------------------------------------------------------------------------------------------------------------
def _build(macro):
    days = pd.bdate_range("2019-01-02", periods=600)
    price = _price(days)
    data = F.add_targets(F.build_features(price, benchmark_close=price["Close"] * 0.9, vix=pd.Series(20.0, index=days), macro=macro), [21])
    return data, F.feature_columns(data)


def _avail(macro):
    """The availability record a FULL fetch of `macro` would produce (spans read from the frame, every series OK)."""
    records = {}
    for name in SERIES:
        s = macro[name].dropna()
        records[name] = {"status": R.OK, "firstValidDate": str(s.index.min().date()), "lastValidDate": str(s.index.max().date()),
                         "validObservations": int(len(s))}
    return R.availability(records, SERIES)


def test_feature_change_is_detected_and_never_carries_the_registered_version():
    days = pd.bdate_range("2011-01-03", "2026-09-14")
    reference = R.reference_feature_columns(SERIES)
    full = _macro(days)
    _, full_cols = _build(full)
    none_data, none_cols = _build(None)
    normal = R.model_identity("mv", full_cols, reference, full, _avail(full), {"A": "2011-04-01"}, as_of="2026-09-14",
                              coverage_policy=POLICY)
    down = R.model_identity("mv", none_cols, reference, None, {"status": R.UNAVAILABLE, "dataDegraded": True}, {"A": "2011-02-01"},
                            as_of="2026-09-14", coverage_policy=POLICY)
    assert normal["variant"] == R.REGISTERED and normal["effectiveModelId"] == "mv" and normal["coverageVerified"] is True
    assert down["variant"] == R.DEGRADED and down["effectiveModelId"].startswith("mv#degraded-")
    assert down["featureSetSha256"] != normal["featureSetSha256"] == normal["registeredFeatureSetSha256"]
    assert down["constantPlaceholders"] == {"Treasury_10Y": 3.0, "Yield_Curve": 0.5}
    assert set(down["missingFeatures"]) == {"Treasury_2Y", "HY_Spread", "IG_Spread"}      # CPI is never an ML input
    assert (none_data["Treasury_10Y"] == 3.0).all() and (none_data["Yield_Curve"] == 0.5).all()   # what features.py inserts today


def test_matching_names_without_a_registered_coverage_policy_are_unverified_not_registered():
    days = pd.bdate_range("2011-01-03", "2026-09-14")
    full = _macro(days)
    _, cols = _build(full)
    assert R.COVERAGE_POLICY is None
    identity = R.model_identity("mv", cols, R.reference_feature_columns(SERIES), full, _avail(full), {"A": "2011-04-01"}, as_of="2026-09-14")
    assert identity["variant"] == R.UNVERIFIED and identity["effectiveModelId"].startswith("mv#unverified-")
    assert identity["coverageVerified"] is None and identity["coverageReasons"] == ["COVERAGE_POLICY_UNSET"]
    assert R.recording_decision(identity)["action"] == "HOLD"


@pytest.mark.parametrize("case,reason", [("truncated", "TRAINING_START_LATER_THAN_REGISTERED_WINDOW"), ("stale", "ML_MACRO_SERIES_STALE"),
                                         ("short_overlap", "ML_MACRO_OVERLAP_TOO_SHORT"), ("unmeasured", "TRAINING_START_UNMEASURED")])
def test_same_columns_but_unusable_coverage_is_degraded(case, reason):
    days = pd.bdate_range("2011-01-03", "2026-09-14")
    macro = _macro(days, late_start="2023-09-18" if case in ("truncated", "short_overlap") else None)
    _, cols = _build(macro)
    starts = {"truncated": {"A": "2023-09-19"}, "short_overlap": {"A": "2023-09-19"}, "unmeasured": {}}.get(case, {"A": "2011-04-01"})
    as_of = "2026-10-22" if case == "stale" else "2026-09-14"
    policy = {**POLICY, "minOverlapObservations": 5000} if case == "short_overlap" else POLICY
    identity = R.model_identity("mv", cols, R.reference_feature_columns(SERIES), macro, _avail(macro), starts, as_of=as_of,
                                coverage_policy=policy)
    assert identity["featureSetSha256"] == identity["registeredFeatureSetSha256"]          # identical column names ...
    assert identity["variant"] == R.DEGRADED and reason in identity["coverageReasons"]       # ... and still not the registered model
    assert identity["effectiveModelId"] != "mv" and R.recording_decision(identity)["action"] == "HOLD"


@pytest.mark.parametrize("bad_as_of,reason", [
    (None, "AS_OF_UNSET"), ("NaT", "AS_OF_INVALID"), (pd.NaT, "AS_OF_INVALID"),
    ("not-a-date", "AS_OF_INVALID"),
])
def test_unset_or_invalid_decision_date_cannot_reuse_registered_model(bad_as_of, reason):
    days = pd.bdate_range("2011-01-03", "2026-09-14")
    macro = _macro(days)
    _, cols = _build(macro)
    identity = R.model_identity("mv", cols, R.reference_feature_columns(SERIES), macro,
                                _avail(macro), {"A": "2011-04-01"}, as_of=bad_as_of,
                                coverage_policy=POLICY)
    assert identity["variant"] == R.DEGRADED
    assert reason in identity["coverageReasons"]
    assert identity["effectiveModelId"] != "mv"
    assert R.recording_decision(identity)["action"] == "HOLD"


def test_future_last_macro_observation_cannot_be_registered():
    days = pd.bdate_range("2011-01-03", "2026-09-14")
    macro = _macro(days)
    _, cols = _build(macro)
    identity = R.model_identity("mv", cols, R.reference_feature_columns(SERIES), macro,
                                _avail(macro), {"A": "2011-04-01"}, as_of="2026-09-11",
                                coverage_policy=POLICY)
    assert identity["variant"] == R.DEGRADED
    assert "ML_MACRO_SERIES_FUTURE" in identity["coverageReasons"]
    assert R.recording_decision(identity)["action"] == "HOLD"


@pytest.mark.parametrize("future_series", ["Treasury_10Y", "Treasury_2Y", "HY_Spread", "IG_Spread"])
def test_future_tail_in_only_one_series_cannot_hide_behind_the_common_end(future_series):
    days = pd.bdate_range("2011-01-03", "2026-09-14")
    macro = _macro(days)
    macro.loc[pd.Timestamp("2026-09-15"), future_series] = 2.0
    avail = _avail(macro)
    assert avail["mlMacroSeries"]["allPresentThrough"] == "2026-09-14"
    _, cols = _build(macro)
    identity = R.model_identity("mv", cols, R.reference_feature_columns(SERIES), macro,
                                avail, {"A": "2011-04-01"}, as_of="2026-09-14",
                                coverage_policy=POLICY)
    assert identity["variant"] == R.DEGRADED
    assert "ML_MACRO_SERIES_FUTURE" in identity["coverageReasons"]
    assert identity["effectiveModelId"] != "mv"
    assert R.recording_decision(identity)["action"] == "HOLD"


def test_an_empty_future_index_row_is_not_a_future_observation():
    days = pd.bdate_range("2011-01-03", "2026-09-14")
    macro = _macro(days)
    macro.loc[pd.Timestamp("2026-09-15")] = np.nan
    _, cols = _build(macro)
    identity = R.model_identity("mv", cols, R.reference_feature_columns(SERIES), macro,
                                _avail(macro), {"A": "2011-04-01"}, as_of="2026-09-14",
                                coverage_policy=POLICY)
    assert identity["variant"] == R.REGISTERED
    assert identity["coverageReasons"] == []


def test_coverage_policy_must_be_complete():
    with pytest.raises(ValueError):
        R.ml_input_coverage({"mlMacroSeries": {"missing": [], "overlapVerified": True}}, "2026-09-14", {}, {"maxStalenessDays": 7})


def test_reference_feature_set_matches_the_full_production_config():
    from pipeline.config import load_config
    cfg, _ = load_config()
    cols = R.reference_feature_columns(cfg.fred_series)
    _, no_macro = _build(None)
    assert len(cols) == 60 and len(no_macro) == 48                     # the 60 vs 48 columns of issue #279, from the code itself
    assert set(no_macro) < set(cols)


def test_same_feature_set_with_degraded_regime_inputs_is_still_not_recorded_as_normal():
    days = pd.bdate_range("2011-01-03", "2026-09-14")
    _, cols = _build(_macro(days))
    identity = R.model_identity("mv", cols, R.reference_feature_columns(SERIES), _macro(days),
                                {"status": R.PARTIAL, "dataDegraded": True}, {"A": "2011-04-01"}, as_of="2026-09-14",
                                coverage_policy=POLICY)
    assert identity["variant"] == R.DEGRADED and R.recording_decision(identity)["action"] == "HOLD"


def test_recording_decision_fails_closed_and_versions_are_separated():
    registered = {"variant": R.REGISTERED, "registeredModelVersion": "mv", "effectiveModelId": "mv", "regimeInputsDegraded": False}
    degraded = {"variant": R.DEGRADED, "registeredModelVersion": "mv", "effectiveModelId": "mv#degraded-abc", "regimeInputsDegraded": True}
    assert R.DEGRADED_POLICY is None
    assert R.recording_decision(registered) == {"action": "RECORD_UNDER_REGISTERED_MODEL_VERSION", "modelId": "mv"}
    assert R.recording_decision(degraded)["action"] == "HOLD" and R.recording_decision(degraded)["modelId"] is None
    assert R.recording_decision(degraded, "RECORD_AS_SEPARATE_VARIANT")["modelId"] == "mv#degraded-abc" != "mv"
    assert R.recording_decision(degraded, "REUSE_LAST_REGISTERED_MODEL")["action"] == "HOLD"
    with pytest.raises(ValueError):
        R.recording_decision(degraded, "SOMETHING_ELSE")


def test_provenance_rules_refuse_a_fred_claim_without_series_and_a_degraded_model_under_the_registered_version():
    avail = {"status": R.UNAVAILABLE, "fetched": 0, "dataDegraded": True}
    bad = {"macroAvailability": avail, "dataSource": "Yahoo Finance + FinanceDataReader/Stooq fallback (market) + FRED (macro)",
           "dataDegraded": False, "shortTermModelIdentity": {"variant": R.DEGRADED, "registeredModelVersion": "mv", "effectiveModelId": "mv"}}
    assert set(R.provenance_errors(bad)) == {"DATA_SOURCE_CLAIMS_FRED_BUT_FETCH_WAS_NOT_FULL", "DATA_SOURCE_CLAIMS_FRED_WITH_ZERO_SERIES",
                                            "DATA_DEGRADED_FLAG_INCONSISTENT", "DEGRADED_MODEL_RECORDED_UNDER_REGISTERED_VERSION"}
    claimed = {"macroAvailability": {"status": R.FULL, "fetched": 5, "dataDegraded": False,
                                     "mlMacroSeries": {"missing": ["IG_Spread"], "overlapVerified": False, "allPresentFrom": "2011-01-03"}},
               "dataSource": "x + FRED (macro)", "dataDegraded": False}
    assert R.provenance_errors(claimed) == ["ALL_PRESENT_FROM_WITHOUT_VERIFIED_OVERLAP"]
    good = {"macroAvailability": avail, "dataSource": R.data_source_label({**avail, "requested": 27}), "dataDegraded": True,
            "shortTermModelIdentity": {"variant": R.DEGRADED, "registeredModelVersion": "mv", "effectiveModelId": "mv#degraded-x"}}
    assert R.provenance_errors(good) == [] and R.provenance_errors({}) == ["MACRO_AVAILABILITY_MISSING"]


# --- isolation: the weekly decision and the sealed studies ---------------------------------------------------------------------------
def test_entry_state_and_risk_diagnosis_do_not_depend_on_macro():
    days = pd.bdate_range("2019-01-02", periods=600)
    with_macro, _ = _build(_macro(days))
    without, _ = _build(None)
    assert ENTRY.entry_features(with_macro) == ENTRY.entry_features(without)
    assert json.dumps(RISK.diagnose("X", with_macro), sort_keys=True, default=str) == \
        json.dumps(RISK.diagnose("X", without), sort_keys=True, default=str)


def _imports(rel):
    tree = ast.parse((ROOT / rel).read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out |= {node.module or ""} | {a.name for a in node.names}
        elif isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
    return out


@pytest.mark.parametrize("rel", ["pipeline/weekly_decision.py", "pipeline/weekly_publish.py", "pipeline/weekly_history.py"])
def test_weekly_decision_reads_no_macro_regime_or_short_term_model(rel):
    assert not _imports(rel) & {"datafeed", "macro", "regime", "features", "model", "fred_resilience", "build"}


def test_inactive_no_production_module_imports_it_and_sealed_bytes_are_untouched():
    users = [p for p in list((ROOT / "pipeline").glob("*.py")) + list((ROOT / "scripts").glob("*.py"))
             if p.name != "fred_resilience.py" and "fred_resilience" in p.read_text(encoding="utf-8")]
    assert users == []
    import hashlib
    for spec in ("research_specs/alpha-opportunity-model-v1.json", "research_specs/market-industry-stock-data-foundation-v1.json"):
        pins = json.loads((ROOT / spec).read_text())["dependencyHashes"]
        for rel in ("pipeline/datafeed.py", "pipeline/build.py", "pipeline/features.py", "pipeline/model.py", "pipeline/validate.py"):
            if rel in pins:
                assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == pins[rel], (spec, rel)
