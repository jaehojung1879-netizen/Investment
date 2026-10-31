import ast
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import market_research_c1c_source_evidence as S


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


def test_timing_sensitivity_is_zero_on_a_flat_price_and_signed_on_a_trend():
    sessions = pd.bdate_range("2020-01-01", periods=60)
    chain = pd.DataFrame({"ex": [sessions[20]], "cash": [100.0]})
    flat = pd.Series(10_000.0, index=sessions)
    assert S.timing_sensitivity(flat, chain)["byLagSessionsAfterEx"]["3"]["signedPpPerYear"] == 0.0
    rising = pd.Series(10_000.0 * 1.001 ** np.arange(60), index=sessions)
    t = S.timing_sensitivity(rising, chain)["byLagSessionsAfterEx"]
    assert t["3"]["signedPpPerYear"] > 0 and t["10"]["signedPpPerYear"] > t["3"]["signedPpPerYear"]
    assert t["3"]["sumOfAbsolutePpPerYear"] == pytest.approx(t["3"]["signedPpPerYear"])


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


def test_reconstructed_price_equals_the_issuers_own_close_on_every_session():
    xlrd = pytest.importorskip("xlrd")
    quotes, chain, endpoint = S.load_chain()
    price = S.as_traded_prices(quotes, chain, endpoint)
    sheet = xlrd.open_workbook(S.AUDIT / "sources" / "issuer-standard.xls").sheet_by_index(0)
    issuer = pd.Series({pd.to_datetime(sheet.cell_value(r, 0)): sheet.cell_value(r, 1) for r in range(4, sheet.nrows)})
    joined = pd.concat({"rebuilt": price, "issuer": issuer}, axis=1).dropna()
    assert len(joined) == len(price) == 3612
    assert float(((joined.rebuilt / joined.issuer) - 1).abs().max()) < 1e-9


def test_module_imports_no_strategy_selection_or_replay_code():
    tree = ast.parse(Path(S.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert imported <= {"__future__", "hashlib", "json", "pathlib", "numpy", "pandas", ".kr_integrated_alpha_portfolio"}
