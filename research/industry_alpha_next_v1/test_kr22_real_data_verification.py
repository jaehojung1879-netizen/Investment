"""The committed real-data verification report and its row classifier. No network, price or outcome."""
import json

from . import kr22_real_data_verification as V

REPORT = json.loads(V.REPORT.read_text())


def test_report_reads_no_outcome_commits_no_raw_bytes_and_sets_no_gate():
    assert REPORT["historicalOutcomesRead"] == 0 and REPORT["pricesRead"] == 0 and REPORT["rawBytesCommitted"] is False
    s = REPORT["summary"]
    assert s["stage6Research"]["gatesBefore"] == s["stage6Research"]["gatesAfter"]
    assert s["stage6Research"]["totalReturnLabelEligible"] == {"before": 0, "after": 0}
    assert s["stage6Research"]["terminalEconomicsComplete"] == {"before": 5, "after": 5}


def test_stages_are_counted_on_their_own_denominators():
    t, d = REPORT["summary"]["terminal"], REPORT["summary"]["dividend"]
    assert t["planned"] == 35 and t["stage3Verified"] + t["stage3Refused"] + t["stage3NotServed"] == 35
    assert t["stage2Integrity"] == t["stage1Downloaded"] == t["stage3Verified"] + t["stage3Refused"]
    assert d["planned"] == d["stage1Downloaded"] == d["stage2Integrity"] == d["stage3Verified"] == 141
    # A record date is never promoted to an ex-date.
    assert d["stage4ExDateStated"] == 0 and all(r["stage4"]["exDateSource"] is None for r in REPORT["dividend"])


def test_every_refusal_and_non_service_keeps_its_reason():
    for r in REPORT["terminal"]:
        assert (r["stage3Identity"] == "VERIFIED") == (not r["stage3Reasons"])
        assert r["stage3Identity"] == "VERIFIED" or not r["stage4ChangedRows"]


def test_value_flag_needs_a_term_row_and_numbers_on_both_sides():
    assert V.stated_value_changed("4. 합병비율", "1: 1.33681318", "1: 1.3368131")
    assert V.stated_value_changed("3. 양도가액(원)", "37,000,000,000", "27,546,000,000")
    assert not V.stated_value_changed("1. 합병에 따라 배정되는 신주의 향후 상장 추진", "2015년 4월 20일", "2015년 4월 21일")
    assert not V.stated_value_changed("3. 주식이전비율 평가결과", "주 2-1)", "주 2-2)")
    assert not V.stated_value_changed("4. 합병비율", "1: 0.35", "1: 0.35")
    assert not V.stated_value_changed("4. 합병비율", "(정정 전 주1)", "(정정 후 주1)")


def test_changed_rows_skip_headers_and_unchanged_rows():
    rows = [{"cells": ["항 목", "정정전", "정정후"]}, {"cells": ["8. 매매거래정지예정기간", "2020-01-23", "2020-01-22"]},
            {"cells": ["10. 주식매수청구권", "a", "a"]}]
    [c] = V.changed_rows(rows)
    assert c["class"] == "EXECUTION_TIMELINE" and c["statedValueChanged"] is False
