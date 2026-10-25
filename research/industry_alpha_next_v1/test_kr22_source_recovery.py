"""Share-count execution evidence and the 16-security request list. Synthetic inputs plus the committed report."""
import json

from . import inputs as IN
from . import kr22_source_recovery as R

REPORT = json.loads((R.K.ROOT / "research/industry_alpha_next_v1/kr22-source-recovery.json").read_text())


def snaps(rows):
    return IN.SnapshotCaps(rows)


def row(date, ticker, shares):
    return {"date": date, "ticker": ticker, "listedShares": shares, "marketCap": 1.0}


def test_share_jump_takes_the_first_moved_snapshot_after_the_effective_date():
    s = snaps([row("2023-01-02", "S", 100.0), row("2023-02-01", "S", 100.0), row("2023-03-02", "S", 150.0)])
    assert R.share_jump(s, "S", "2023-01-15") == ("2023-01-02", 100.0, "2023-03-02", 150.0)


def test_a_new_listing_starts_from_no_prior_snapshot():
    s = snaps([row("2014-12-01", "S", 676.0)])
    assert R.share_jump(s, "S", "2014-11-01") == (None, 0.0, "2014-12-01", 676.0)


def test_successor_is_resolved_only_when_unique():
    rows = [row("2026-01-02", "A", 10.0), row("2026-02-02", "A", 40.0),
            row("2026-01-02", "B", 10.0), row("2026-02-02", "B", 11.0)]
    assert R.resolve_successor(snaps(rows), "2026-01-15", 30) == "A"
    rows += [row("2026-01-02", "C", 5.0), row("2026-02-02", "C", 35.0)]
    assert R.resolve_successor(snaps(rows), "2026-01-15", 30) is None


def _src(text, code="OLD"):
    return {"retainedTerminalDocuments": [{"ticker": code, "members": [{"text": text}]}]}


def test_documented_count_is_read_from_the_securitys_own_filing_and_must_be_unique():
    t = "<td>5. 합병신주의 종류와 수(주)</td><td>보통주식</td><td>23,206,189</td>"
    assert R.documented_new_shares("OLD", _src(t)) == 23206189
    assert R.documented_new_shares("OTHER", _src(t)) is None
    two = t + "<td>신주의 종류와 수(주)</td><td>보통주식</td><td>1,000</td>"
    assert R.documented_new_shares("OLD", _src(two)) == [1000, 23206189]


def _case(count_text, before, after, *, successor="S", ratio=0.5):
    s = snaps([row("2014-06-02", "S", before), row("2014-08-01", "S", after)])
    r = {"code": "OLD", "terminal": {"actionType": "MERGER_STOCK"}}
    a = {"successorSharesPerOldShare": ratio, "effectiveDate": "2014-07-01", "successorSecurity": successor}
    return R.execution_evidence(r, a, _src(count_text), s)


def test_execution_classes():
    doc = "<td>신주의 종류와 수(주)</td><td>보통주식</td><td>{}</td>"
    assert _case(doc.format("100,000"), 1e6, 1.1e6)["status"] == R.EXACT
    assert _case(doc.format("100,000"), 1e6, 1.1e6 - 50)["status"] == R.ADJUSTED
    assert _case(doc.format("100,000"), 1e6, 1.05e6)["status"] == "CONTRADICTED_OR_UNRECONCILED"
    assert _case("", 1e6, 1.05e6)["status"] == R.PARTIAL
    assert _case("", 1e6, 1e6)["status"] == "CONTRADICTED_OR_UNRECONCILED"
    cash = R.execution_evidence({"code": "X", "terminal": {"actionType": "CASH_SHARE_EXCHANGE"}},
                                {"successorSharesPerOldShare": None}, _src(""), snaps([]))
    assert cash["status"] == "NOT_APPLICABLE_NO_DOCUMENTED_STOCK_RATIO"


def test_committed_report_reads_no_outcome_and_keeps_the_22_denominator():
    assert REPORT["historicalOutcomesRead"] == 0 and REPORT["pricesRead"] == 0 and REPORT["networkUsed"] is False
    assert REPORT["summary"]["denominator"] == len(REPORT["securities"]) == 22
    assert REPORT["summary"]["inWindowSecurities"] == len(REPORT["requests"]) == 16
    assert sum(REPORT["summary"]["executionEvidenceStatus"].values()) == 22


def test_committed_execution_evidence_is_internally_consistent():
    for r in REPORT["securities"]:
        e = r["executionEvidence"]
        if e["status"] == R.EXACT:
            assert e["observedIncrease"] == e["documentedNewShares"]
        if e["status"] == R.ADJUSTED:
            assert abs(e["relativeGap"]) <= R.ADJUSTMENT_TOLERANCE
        if e["status"] in (R.EXACT, R.ADJUSTED):
            assert r["gatesAfter"]["executionConfirmed"]
        # Recovery can only add evidence; it never removes a gate that was already met.
        assert all(r["gatesAfter"][k] or not v for k, v in r["gatesBefore"].items())


def test_no_label_becomes_eligible_without_an_admitted_industry_and_a_sealed_ex_date_rule():
    s = REPORT["summary"]
    assert s["industryAdmitted"]["after"] == 0 and s["exDateSemanticsResolved"]["after"] == 0
    assert s["eligibleForIndustryTotalReturnLabel"] == {"before": 0, "after": 0}


def test_request_list_names_the_corp_and_never_asks_for_a_year_after_the_window():
    for q in REPORT["requests"]:
        assert q["dartCorpCode"] and len(q["dartCorpCode"]) == 8
        held = {int(y) for y in q["annualReportReceiptsHeldInRepository"]}
        assert held.isdisjoint(q["fiscalYearsNeedingListJsonQuery"])
        assert set(q["industryFiscalYearsNeeded"]) == held | set(q["fiscalYearsNeedingListJsonQuery"])
        assert max(q["industryFiscalYearsNeeded"]) <= int(R.K.STUDY_WINDOW[1][:4]) - 1
