import ast
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import market_research_c1c_source_evidence as S
from pipeline import market_research_c1c_xls_cells as XLS


def _synthetic(n=60, ex_positions=(15, 35, 50), cash=(100.0, 120.0, 90.0), seed=1):
    rng = np.random.default_rng(seed)
    sessions = pd.bdate_range("2020-01-01", periods=n)
    raw = pd.Series(10_000 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=sessions)
    chain = pd.DataFrame({"ex": [sessions[i] for i in ex_positions], "record": [sessions[i + 1] for i in ex_positions],
                          "cash": cash})
    tr = raw.copy()
    level = 1.0
    out = []
    for i, p in enumerate(raw.values):
        if i > 0:
            ratio = p / raw.values[i - 1]
            hit = [c for e, c in zip(chain.ex, chain.cash) if e == sessions[i]]
            if hit:
                ratio = (p + hit[0]) / raw.values[i - 1]
            level *= ratio
        out.append(level)
    tr[:] = out
    return raw, tr, chain


def test_as_traded_price_inversion_recovers_the_raw_close_exactly():
    raw, tr, chain = _synthetic()
    price = S.as_traded_prices(tr, chain, float(raw.iloc[-1]))
    assert np.allclose(price.values, raw.values, rtol=1e-12)


def test_payment_dates_are_official_only_and_never_inferred():
    raw, tr, chain = _synthetic()
    official = pd.DataFrame({"record": [chain.record.iloc[2]], "pay": [tr.index[53]],
                             "cash": [90.0], "taxBase": [80.0]})
    facts = S.payment_facts(tr, chain, official)
    assert (facts["records"], facts["officialPaymentDate"], facts["paymentDateUnresolved"]) == (3, 1, 2)
    assert facts["paymentSessionsAfterRecord"] == [2]
    assert facts["firstUnresolved"]["exDate"] == str(chain.ex.iloc[0].date())


def test_official_cash_disagreeing_with_the_chain_is_flagged_not_merged():
    raw, tr, chain = _synthetic()
    official = pd.DataFrame({"record": [chain.record.iloc[2]], "pay": [tr.index[53]], "cash": [91.0], "taxBase": [80.0]})
    assert S.payment_facts(tr, chain, official)["officialCashEqualsChainCash"] is False


def _no_official():
    return pd.DataFrame({"record": pd.to_datetime([]), "pay": pd.to_datetime([]), "cash": [], "taxBase": []})


def test_timing_sensitivity_is_zero_on_a_flat_price_and_signed_on_a_trend():
    sessions = pd.bdate_range("2020-01-01", periods=60)
    chain = pd.DataFrame({"ex": [sessions[20]], "record": [sessions[21]], "cash": [100.0]})
    flat = pd.Series(10_000.0, index=sessions)
    t = S.timing_sensitivity(flat, chain, _no_official())
    assert t["mixedLagScenarioWith20Known"]["boundOnAbsoluteEffectPpPerYear"] == 0.0 and t["mixedLagScenarioWith20Known"]["unresolvedEvents"] == 1
    rising = pd.Series(10_000.0 * 1.001 ** np.arange(60), index=sessions)
    t = S.timing_sensitivity(rising, chain, _no_official())
    m = t["mixedLagScenarioWith20Known"]
    assert m["signedInterval"]["lowerPpPerYear"] > 0
    assert m["boundOnAbsoluteEffectPpPerYear"] == m["signedInterval"]["upperPpPerYear"]


def test_mixed_lag_bound_exceeds_the_common_lag_figure_when_events_peak_at_different_lags():
    """Event A is most affected at lag 2 and event B at lag 4: max_L sum|d| understates what mixed lags can reach."""
    sessions = pd.bdate_range("2020-01-01", periods=60)
    price = pd.Series(10_000.0, index=sessions)
    ex_a, ex_b = 10, 30
    price.iloc[ex_a + 2] = 10_500.0   # A: +5% two sessions after ex, flat otherwise
    price.iloc[ex_b + 4] = 10_500.0   # B: +5% four sessions after ex, flat otherwise
    chain = pd.DataFrame({"ex": [sessions[ex_a], sessions[ex_b]], "record": [sessions[ex_a + 1], sessions[ex_b + 1]],
                          "cash": [100.0, 100.0]})
    t = S.timing_sensitivity(price, chain, _no_official())
    common = max(v["sumOfAbsolutePpPerYear"] for v in t["commonLagScenario"]["byLagSessionsAfterEx"].values())
    m = t["mixedLagScenarioWith20Known"]
    assert m["perEventTriangleEnvelopePpPerYear"] == pytest.approx(2 * common, rel=1e-6)
    assert m["boundOnAbsoluteEffectPpPerYear"] == pytest.approx(2 * common, rel=1e-6)
    assert m["boundOnAbsoluteEffectPpPerYear"] > common
    assert t["commonLagScenario"]["status"] == "SCENARIO_NOT_A_BOUND"
    assert "NOT_A_UNIVERSAL_FUNDING_BOUND" in m["status"] and "NOT_SOURCE_ADMITTED" in m["status"]


def test_known_official_events_are_fixed_at_their_paid_date_and_only_the_rest_are_bounded():
    sessions = pd.bdate_range("2020-01-01", periods=60)
    price = pd.Series(10_000.0, index=sessions)
    price.iloc[10 + 3] = 10_300.0
    price.iloc[30 + 6] = 12_000.0
    chain = pd.DataFrame({"ex": [sessions[10], sessions[30]], "record": [sessions[11], sessions[31]], "cash": [100.0, 100.0]})
    official = pd.DataFrame({"record": [sessions[11]], "pay": [sessions[13]], "cash": [100.0], "taxBase": [100.0]})
    t = S.timing_sensitivity(price, chain, official)
    years = S.years_between(sessions[0], sessions[-1])
    m = t["mixedLagScenarioWith20Known"]
    assert (m["knownOfficialEvents"], m["unresolvedEvents"]) == (1, 1)
    assert m["knownEventsFixedAtObservedDatesPpPerYear"] == pytest.approx(100.0 / 10_000.0 * 0.03 / years * 100, rel=1e-3)
    assert m["boundOnAbsoluteEffectPpPerYear"] > m["knownEventsFixedAtObservedDatesPpPerYear"]


def test_exact_funded_comparison_validates_path_a_and_is_zero_on_a_flat_price():
    raw, tr, chain = _synthetic()
    official = pd.DataFrame({"record": chain.record, "pay": [tr.index[i + 3] for i in (15, 35, 50)],
                             "cash": chain.cash, "taxBase": chain.cash})
    out = S.exact_funded_comparison(raw, chain, official, tr)
    assert abs(out["pathAReproducesCorrectedIndexRelativeResidual"]) < 1e-12
    assert out["status"].startswith("SCENARIOS_NOT_A_BOUND")
    sessions = raw.index
    flat = pd.Series(10_000.0, index=sessions)
    flat_tr = pd.Series(np.nan, index=sessions)
    level, vals = 1.0, []
    for i in range(len(sessions)):
        if i:
            hit = [c for e, c in zip(chain.ex, chain.cash) if e == sessions[i]]
            level *= (10_000.0 + (hit[0] if hit else 0.0)) / 10_000.0
        vals.append(level)
    flat_tr[:] = vals
    zero = S.exact_funded_comparison(flat, chain, official, flat_tr)
    assert zero["exactPpPerYear"] == pytest.approx(0.0, abs=1e-9)


def test_tax_basis_full_taxable_base_has_share_one_and_scales_with_the_rate():
    raw, tr, chain = _synthetic()
    official = pd.DataFrame({"record": chain.record, "pay": [tr.index[i + 3] for i in (15, 35, 50)],
                             "cash": chain.cash, "taxBase": chain.cash})
    t = S.tax_basis(raw, chain, official)
    assert t["taxableShareOfCash"] == {"min": 1.0, "max": 1.0, "mean": 1.0}
    assert t["dragAtAssumedStatutoryRatePpPerYear"] == pytest.approx(t["taxableBaseYieldPpPerYear"] * 0.154, rel=1e-3)
    assert "UNVERIFIED" in t["rateStatus"]


def test_cash_sensitivity_brackets_zero_proxy_and_haircut_on_a_constant_rate():
    sessions = pd.bdate_range("2020-01-01", "2021-12-31")
    events = [{"date": "2019-01-01", "annualRatePct": 2.0}]
    c = S.cash_sensitivity(events, sessions)["meanRatePctPerYear"]
    assert c["ZERO"] == 0.0 and c["PROXY"] == pytest.approx(2.0) and c["PROXY_MINUS_HAIRCUT"] == pytest.approx(1.5)


def test_admission_is_fail_closed_and_cannot_be_ready_from_code_alone():
    base = {"confirmedSourceFacts": {"distributions": {"paymentDateUnresolved": 0, "records": 46,
                                                       "officialCashEqualsChainCash": True}},
            "ownerOnlyDecisions": list(S.OWNER_DECISIONS)}
    a = S.admission(base)
    assert a["etfDistributionFunding"] == "BLOCKED" and a["historicalExecution"] == "BLOCKED"
    assert not any(r.startswith("PAYMENT") for r in a["reasons"])
    base["confirmedSourceFacts"]["distributions"]["paymentDateUnresolved"] = 26
    assert "PAYMENT_DATE_UNRESOLVED:26_OF_46" in S.admission(base)["reasons"]
    base["confirmedSourceFacts"]["distributions"]["officialCashEqualsChainCash"] = False
    assert "OFFICIAL_CASH_DISAGREES_WITH_CHAIN" in S.admission(base)["reasons"]


def test_every_input_file_is_pinned_and_present():
    assert len(S.PINS) == 5
    for rel, digest in S.PINS.items():
        assert S.sha256(S.ROOT / rel) == digest, rel
    assert set(json.loads(S.OUTPUT.read_text())["inputs"]) == set(S.PINS)


def test_pinned_inputs_and_real_counts():
    S.verify_pins()
    quotes, chain, endpoint = S.load_chain()
    official = S.load_official_payments()
    facts = S.payment_facts(quotes, chain, official)
    assert (facts["records"], facts["officialPaymentDate"], facts["paymentDateUnresolved"]) == (46, 20, 26)
    assert facts["officialCashEqualsChainCash"] is True and facts["exDateIsSessionAndRecordIsNextSession"] is True
    assert facts["paymentSessionsAfterRecord"] == [2] and facts["paymentSessionsAfterEx"] == [3]
    assert facts["firstUnresolved"] == {"exDate": "2012-04-27", "recordDate": "2012-04-30"}


def test_pin_mismatch_raises(monkeypatch):
    first = next(iter(S.PINS))
    monkeypatch.setitem(S.PINS, first, "0" * 64)
    with pytest.raises(ValueError, match="SOURCE_EVIDENCE_INPUT_CHANGED"):
        S.verify_pins()


def _close(a, b):
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=2e-5)
    return a == b


def test_committed_evidence_matches_a_fresh_build():
    committed = json.loads(S.OUTPUT.read_text())
    fresh = S.evidence()
    fresh["admission"] = S.admission(fresh)
    assert _close(fresh, committed)
    assert committed["admission"]["historicalExecution"] == "BLOCKED"


def _rebuilt_price():
    quotes, chain, endpoint = S.load_chain()
    return S.as_traded_prices(quotes, chain, endpoint), endpoint


def test_issuer_close_cross_check_runs_without_xlrd_and_is_a_gate_not_a_skip():
    """The 3,612-session comparison must run in the required CI, which does not install xlrd."""
    price, _ = _rebuilt_price()
    out = S.issuer_close_cross_check(price)
    assert out["sessions"] == len(price) == 3612 and out["maxAbsRelativeDifference"] < S.ISSUER_CLOSE_TOLERANCE
    assert out["status"] == "GATING_ASSERTION_RUN_IN_REQUIRED_CI"
    assert json.loads(S.OUTPUT.read_text())["confirmedSourceFacts"]["asTradedPriceReconstruction"]["issuerAsTradedCloseCrossCheck"]["sessions"] == 3612


def test_issuer_close_cross_check_fails_loudly_on_one_wrong_session_or_a_missing_session():
    price, _ = _rebuilt_price()
    wrong = price.copy()
    wrong.iloc[1800] *= 1.0001
    with pytest.raises(ValueError, match="ISSUER_CLOSE_CROSS_CHECK_FAILED"):
        S.issuer_close_cross_check(wrong)
    extra = pd.concat([price, pd.Series([1.0], index=[price.index[-1] + pd.Timedelta(days=1)])])
    with pytest.raises(ValueError, match="ISSUER_CLOSE_CROSS_CHECK_FAILED"):
        S.issuer_close_cross_check(extra)


def test_xls_reader_anchors_on_the_real_file_including_an_independent_official_quote():
    price, endpoint = _rebuilt_price()
    cells = XLS.read_cells(S.AUDIT / "sources" / "issuer-standard.xls")
    assert len(cells) == 53275
    assert cells[(4, 0)] == "20261007" and cells[(4, 1)] == 108550.0
    assert cells[(max(r for r, c in cells), 0)] == "20021014"
    by_date = {v: cells[(r, 1)] for (r, c), v in cells.items() if c == 0 and r >= 4}
    assert by_date["20260914"] == endpoint == 105410.0   # the independent official raw endpoint quote in the audit report
    dividends = XLS.read_cells(S.AUDIT / "sources" / "issuer-dividends.xls")
    assert len(dividends) == 107 and dividends[(3, 0)] == "20260731" and dividends[(3, 1)] == "20260804"


def test_xls_reader_refuses_what_it_does_not_understand(tmp_path):
    bad = tmp_path / "bad.xls"
    bad.write_bytes(b"not an xls file")
    with pytest.raises(XLS.XlsReadError, match="NOT_AN_OLE2_FILE"):
        XLS.read_cells(bad)
    real = (S.AUDIT / "sources" / "issuer-standard.xls").read_bytes()
    cut = tmp_path / "cut.xls"
    cut.write_bytes(real[:100_000])
    with pytest.raises(XLS.XlsReadError):
        XLS.read_cells(cut)


def test_xls_reader_matches_xlrd_cell_by_cell_where_xlrd_is_installed():
    """Extra evidence only: the required gate above does not depend on this."""
    xlrd = pytest.importorskip("xlrd")
    for name in ("issuer-standard.xls", "issuer-dividends.xls"):
        path = S.AUDIT / "sources" / name
        sheet = xlrd.open_workbook(path).sheet_by_index(0)
        reference = {(r, c): sheet.cell_value(r, c) for r in range(sheet.nrows) for c in range(sheet.ncols)
                     if sheet.cell_type(r, c) not in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK)}
        assert XLS.read_cells(path) == reference


def test_module_imports_no_strategy_selection_or_replay_code():
    tree = ast.parse(Path(S.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert imported <= {"__future__", "hashlib", "json", "pathlib", "numpy", "pandas", ".kr_integrated_alpha_portfolio", "."}
    reader = ast.parse(Path(XLS.__file__).read_text())
    reader_imports = {n.module if isinstance(n, ast.ImportFrom) else a.name for n in ast.walk(reader)
                      if isinstance(n, (ast.Import, ast.ImportFrom)) for a in (n.names if isinstance(n, ast.Import) else [None])}
    assert reader_imports <= {"__future__", "struct", "pathlib"}   # no xlrd, no pandas: nothing a CI install could be missing
