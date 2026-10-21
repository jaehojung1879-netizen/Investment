"""Independent audit of the KR A0 missingness mechanisms. Synthetic only.

Each test pins one mechanism the real decomposition attributes missing cells
to, and shows whether the engine's behaviour there is a defect or the honest
consequence of absent data. No real source, price, return or outcome is read,
and nothing here changes a sealed hypothesis, the 60% gate or a verdict.
"""
import json

import pytest

from pipeline import rp1_a0 as A, rp1_kr_a0 as K

OP, OCF = "영업이익", "영업활동현금흐름"
DEADLINE = {"11013": "05-15", "11012": "08-14", "11014": "11-14", "11011": "03-31"}


def record(year, code, op, *, ocf=10.0, public=None, basis="CFS", with_op=True, ticker="SYN.KS"):
    """One DART filing. Quarterly IS states the quarter and the year-to-date
    total; the cash-flow statement states only the cumulative figure."""
    public = public or (f"{year + 1}-{DEADLINE[code]}" if code == "11011" else f"{year}-{DEADLINE[code]}")
    flow = {"thstrm_amount": op} if code == "11011" else {"thstrm_amount": op, "thstrm_add_amount": op}
    accounts = {OCF: {"statement": "CF", "amounts": {"thstrm_amount": ocf}}}
    if with_op:
        accounts[OP] = {"statement": "CIS", "amounts": flow}
    # Real KR ids carry no receipt number: one id per (ticker, year, report).
    return {"id": f"{ticker}:{year}:{code}", "ticker": ticker, "fiscalYear": year, "reportCode": code,
            "availableFrom": public, "receiptNos": [public.replace("-", "") + "000001"], "fsDiv": basis,
            "accounts": accounts}


def full_history(first_year=2015, last_year=2019, *, q2015_like_xbrl=False):
    """DART structured statements start at fiscal 2015, as in the real store."""
    rows = []
    for year in range(first_year, last_year + 1):
        for code in ("11013", "11012", "11014", "11011"):
            # A falling then rising operating profit, so every growth reading is
            # known (no EVENT_HISTORY_UNRESOLVED ambiguity from a missing sign).
            op = 100.0 - 5 * (year - first_year) if year < 2018 else 120.0
            xbrl = q2015_like_xbrl and year == 2015 and code != "11011"
            rows.append(record(year, code, op, basis=None if xbrl else "CFS", with_op=not xbrl))
    return rows


def weekly(start, end):
    days, d = [], A.dt.date.fromisoformat(start)
    while d <= A.dt.date.fromisoformat(end):
        days.append(d.isoformat())
        d += A.dt.timedelta(days=7)
    return days


def first_measured(rows, start="2015-01-02", end="2019-12-31"):
    history = A.FilingHistory("SYN.KS", rows, adapter=K.Filings())
    return next((d for d in weekly(start, end) if history.at(d)["flag"] is not None), None)


# 1. Disclosure availability: history depth, not a defect --------------------

def test_dart_from_fiscal_2015_makes_every_signal_before_fy2016_annual_unmeasurable():
    # Complete, on-time filings from FY2015 with operating income everywhere:
    # a TTM growth needs the same stage one year earlier, and its TTM needs the
    # year before that. Nothing can be measured before the FY2016 annual.
    first = first_measured(full_history())
    assert first is not None and first > "2017-03-31"


def test_missing_2015_quarterly_operating_income_delays_first_measurement_by_a_year():
    complete = first_measured(full_history())
    xbrl_like = first_measured(full_history(q2015_like_xbrl=True))
    # The real store's first H1 measurement is 2018-04-06; this is the mechanism.
    # Without 2015 quarterly operating income the 2017 quarterly keys cannot
    # form a prior-year TTM, so nothing is measured before the FY2017 annual;
    # an unresolved 2017 state can then hold the cell for its own 26 weeks.
    assert complete < "2018-01-01" <= xbrl_like
    assert "2018-03-31" < xbrl_like < "2018-12-31"


# 2. Statement basis: the label is not the binding constraint ----------------

def test_unknown_basis_masks_absent_operating_income_and_relabelling_rescues_nothing():
    rows = full_history(q2015_like_xbrl=True)
    index = {(r["fiscalYear"], r["reportCode"]): r for r in rows}
    key = (2017, "11013")
    *_, reason = K.Filings.values(index, key)
    assert reason == "STATEMENT_BASIS_UNRESOLVED"
    for r in rows:
        if r["fsDiv"] is None:
            r["fsDiv"] = "CFS"  # the per-account XBRL lineage says CFS
    op, prior, cash, reason = K.Filings.values({(r["fiscalYear"], r["reportCode"]): r for r in rows}, key)
    # Same cell, still unmeasurable: the 2015 quarter has no operating income.
    assert prior is None and reason == "OPERATING_INCOME_NOT_STATED"


def test_cfs_ofs_switch_inside_a_chain_abstains_without_imputation():
    rows = full_history()
    for r in rows:
        if r["fiscalYear"] == 2016 and r["reportCode"] == "11011":
            r["fsDiv"] = "OFS"
    index = {(r["fiscalYear"], r["reportCode"]): r for r in rows}
    op, prior, cash, reason = K.Filings.values(index, (2017, "11013"))
    assert (op, prior, cash) == (None, None, None) and reason == "STATEMENT_BASIS_CONFLICT"


# 3. Correction vintage: only the stored receipt date counts ------------------

def test_period_stored_only_as_a_later_vintage_is_never_backdated():
    rows = full_history()
    late = "2019-01-10"  # e.g. the latest amendment's receipt replaced the original
    for r in rows:
        if r["fiscalYear"] == 2017 and r["reportCode"] == "11011":
            r["availableFrom"], r["receiptNos"] = late, [late.replace("-", "") + "000001"]
    history = A.FilingHistory("SYN.KS", rows, adapter=K.Filings())
    before = history.at("2018-04-06")
    after = history.at("2019-01-18")
    # Before the stored receipt the FY2017 annual does not exist for the engine.
    assert before["currentKey"] != (2017, "11011")
    assert after["publicDay"] >= late
    for d in weekly("2018-04-06", "2019-12-27"):
        state = history.at(d)
        if state["eventDate"]:
            assert state["eventDate"] > min(r["availableFrom"] for r in rows if (r["fiscalYear"], r["reportCode"]) == state["currentKey"])


def test_receipt_date_disagreeing_with_available_from_is_dropped_not_shifted():
    r = record(2015, "11012", 100.0, public="2015-08-17")
    r["receiptNos"] = ["20150814000051"]  # the two real cases: next-business-day availableFrom
    assert K.Filings.visible_day(r) is None


# 4/5. PIT universe and terminal securities: outside the denominator ---------

def test_unclassified_terminal_member_never_enters_the_h3_peer_set():
    def row(t, sector, rel, cap):
        return {"ticker": t, "sector": sector, "industry": sector, "issuerId": "I-" + t, "marketCap": cap,
                "relative126": rel, "isPreferredShare": False, "priceAsOf": "2020-01-03",
                "positiveVolumeSessions20": 20, "medianTradedValue60Krw": 5e9}
    rows = [row(f"{s}{i}", s, 0.01 * i, 100 - i) for s in "ABC" for i in range(5)]
    terminal = row("DELISTED", None, None, 1.0)  # no industry interval, no window
    reasons = K.eligibility(rows + [terminal], A.pd.Timestamp("2020-01-03"))
    assert reasons["DELISTED"] == ["INDUSTRY_UNCLASSIFIED"]
    eligible = [r for r in rows + [terminal] if not reasons[r["ticker"]]]
    with_terminal = A.h3(eligible, size_field="marketCap")
    assert with_terminal == A.h3(rows, size_field="marketCap")
    assert all(reason == "AVAILABLE" for _, reason in with_terminal.values())


# 6. Industry cross-section propagation: the registered completeness rule ----

def test_one_missing_past_window_withholds_the_whole_date_by_design():
    rows = [{"ticker": f"{s}{i}", "sector": s, "marketCap": 100.0 - i, "relative126": 0.01 * i}
            for s in "ABCD" for i in range(6)]
    assert sum(v is not None for v, _ in A.h3(rows, size_field="marketCap").values()) == len(rows)
    rows[7]["relative126"] = None  # one name in sector B
    out = A.h3(rows, size_field="marketCap")
    assert all(v is None for v, _ in out.values())  # 1 missing cell -> 24 missing cells
    assert {out[r["ticker"]][1] for r in rows if r["sector"] == "B"} == {"INDUSTRY_PEER_INPUT_UNRESOLVED"}
    assert {out[r["ticker"]][1] for r in rows if r["sector"] != "B"} == {"INDUSTRY_CROSS_SECTION_UNRESOLVED"}


@pytest.mark.parametrize("missing_sector", ["A", "D"])
def test_propagation_does_not_substitute_or_drop_the_missing_peer(missing_sector):
    rows = [{"ticker": f"{s}{i}", "sector": s, "marketCap": 100.0 - i, "relative126": 0.01 * i}
            for s in "ABCD" for i in range(6)]
    survivors = [r for r in rows if r["ticker"] != missing_sector + "0"]
    gap = [dict(r, relative126=None) if r["ticker"] == missing_sector + "0" else r for r in rows]
    # Dropping the gap would yield a different, fully measured leader set; the
    # engine refuses that and abstains instead.
    assert all(v is not None for v, _ in A.h3(survivors, size_field="marketCap").values())
    assert all(v is None for v, _ in A.h3(gap, size_field="marketCap").values())


# Committed audit artifact: reconciles with the committed measurement --------

def _committed():
    import hashlib
    import json
    from pathlib import Path
    from scripts import rp1_audit_kr_a0_missingness as AUD
    root = Path(__file__).resolve().parents[1]
    result_bytes = (root / AUD.RESULT).read_bytes()
    return AUD, json.loads(result_bytes), json.loads((root / AUD.OUTPUT).read_text()), hashlib.sha256(result_bytes).hexdigest()


def test_audit_published_scale_is_recomputed_from_the_committed_measurement():
    AUD, result, audit, sha = _committed()
    assert audit["measurementResultSha256"] == sha
    assert audit["publishedScale"] == json.loads(json.dumps(AUD.published_scale(result)))
    years = audit["publishedScale"]["byYear"]
    for h in A.HYPOTHESES:
        assert sum(v[h] for v in years.values()) == result["hypotheses"][h]["measured"]
    assert sum(v["eligible"] for v in years.values()) == result["hypotheses"]["A-H1"]["eligible"]


def test_audit_conclusions_follow_from_its_own_numbers_and_change_no_gate():
    _, result, audit, _ = _committed()
    depth = audit["publishedScale"]["historyDepth"]
    assert depth["darkMeasuredH1H2"] == 0
    assert depth["required2018PlusRateFor60Pct"] > 0.97  # the 60% gate is untouched, only located
    h3 = audit["publishedScale"]["h3Propagation"]
    assert h3["measuredOnWithheldDates"] == 0 and h3["cleanDatesFullyMeasured"] is True
    assert h3["eligibleCellsOnWithheldDates"] + result["hypotheses"]["A-H3"]["measured"] == result["hypotheses"]["A-H3"]["eligible"]
    bounds = audit["countOnlyBounds"]
    assert all(b["rate"] < 0.60 for b in (bounds["basisRelabelXbrlAsCFS"], bounds["visibleAtStatutoryDeadlineLookAheadUpperBound"]))
    for h in A.HYPOTHESES:
        assert result["hypotheses"][h]["gates"]["measurability"] is False
        assert result["hypotheses"][h]["verdict"] == "PROSPECTIVE_ONLY"
    assert audit["accessCounters"] == {"priceReads": 0, "outcomeReads": 0, "forwardPriceReads": 0, "labelReads": 0, "modelFits": 0}
    assert not [k for k in audit["sourceReceipts"] if "prices/" in k or "replay-inputs/" in k or "historical/" in k]


@pytest.mark.parametrize("path", ["ledger/prices/kr/krx-prices-2020.jsonl.gz", "ledger/historical/replay-v16/inputs.json",
                                  "ledger/replay-inputs/objects/" + "0" * 64 + ".json.gz"])
def test_audit_reader_refuses_every_price_bearing_path(path, tmp_path):
    from scripts import rp1_audit_kr_a0_missingness as AUD
    with pytest.raises(ValueError, match="PRICE_OR_OUTCOME_PATH_REFUSED"):
        AUD.PriceFreeSources(tmp_path).blob(AUD.S.SOURCE_COMMIT, path)
