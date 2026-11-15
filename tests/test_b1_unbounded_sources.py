"""Offline checks for the cited B1 unbounded-event terms (no DART call, no price value)."""
import importlib.util
import json
from pathlib import Path

import pytest

from pipeline import kr_terminal_corporate_actions as T

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/corporate_event_outcome_v1/economic-readiness-v2"
spec = importlib.util.spec_from_file_location("b1_unbounded_sources", HERE / "b1_unbounded_sources.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
OUT = json.loads((HERE / "b1-unbounded-events-sources-v1.json").read_text(encoding="utf-8"))


def test_same_eight_events_as_the_admission_status_and_no_returns_read():
    status = json.loads((HERE / "b1-admission-status-v2.json").read_text(encoding="utf-8"))
    listed = {(e["ticker"], e["entry"]) for e in status["eventsWithUnboundedUpside_B1_H126"]}
    assert {(e["ticker"], e["entry"]) for e in OUT["events"]} == listed
    assert OUT["readsReturns"] is False and OUT["priceValuesRead"] == 0


def test_every_cited_term_carries_its_receipt_and_rebuilds_through_the_repository_builders():
    for e in OUT["events"]:
        if e["status"] == "NO_CONSIDERATION_FILED":
            assert not e.get("terms") and not e.get("record")
            continue
        assert e["sources"] and all(len(s["bodySha256"]) == 64 for s in e["sources"])
        if e.get("record"):
            r = e["record"]
            rebuilt = T.build_record(old_security=r["oldSecurity"], action_type=r["actionType"],
                                     effective_date=r["effectiveDate"], successor_security=r["successorSecurity"],
                                     successor_shares_per_old_share=r["successorSharesPerOldShare"],
                                     source_receipt_number=r["sourceReceiptNumber"],
                                     source_receipt_date=r["sourceReceiptDate"])
            assert rebuilt["evidenceStatus"] == T.EVIDENCE_SEALED
        for c in e.get("considerationComponents", []):
            assert c["sourceReceiptNumber"] == e["sources"][0]["rceptNo"]
            with pytest.raises(ValueError):
                T.build_consideration_component(component_type=c["type"], successor_security=c["successorSecurity"],
                                                shares_per_old_share=c["sharesPerOldShare"])


def test_spin_off_terms_are_internally_consistent():
    for e in OUT["events"]:
        if e["kind"] != "SPIN_OFF":
            continue
        t = e["terms"]
        assert t["retainedSharesPerOldShare"] + t["spinOffRatio"] == pytest.approx(1.0, abs=1e-7)
        assert t["capitalReductionPct"] == pytest.approx(100 * t["spinOffRatio"], abs=1e-5)
        assert t["newCompanySharesPerOldShare"] == pytest.approx(t["spinOffRatio"] * t["parRatio"], abs=1e-7)


def test_parsers_on_synthetic_rows():
    rows = ["1. 1주당 배당주식수 (주) | 보통주식 | 0.05", "4. 배당기준일 | 2019-12-31", "- 1주 미만의 단수주는 현금 지급"]
    assert M.parse_stock_dividend(rows) == {"newSharesPerOldShare": 0.05, "recordDate": "2019-12-31",
                                            "fractionalShares": "CASH_AT_PRIOR_DAY_CLOSE_STATED"}
    rows = ["4. 합병비율 | 보통주 1 : 0.2606772, 우선주 1 : 0.2534945", "합병기일 | 2017년 01월 01일",
            "신주의 상장예정일 | 2017년 01월 17일"]
    assert M.parse_merger(rows)["successorSharesPerOldShare"] == 0.2606772
    rows = ["4. 분할비율 | [분할비율]- 분할존속회사 : 0.6503913- 분할신설회사 : 0.3496087",
            "신주배정조건 | (b) 1주의 금액비율 : 분할회사 1주의 금액 2,500원을 분할신설회사의 1주의 금액 2,500원으로 나누어 산정함.",
            "8. 감자에 관한 사항- 신주배정기준일 | 정정 | 2025년 09월 30일 | 2025년 10월 31일",
            "8. 감자에 관한 사항 | 감자비율(%) | 34.96087", "신주배정기준일 | 2025년 10월 31일", "분할기일 | 2025년 11월 01일"]
    t = M.parse_spin_off(rows)
    assert (t["retainedSharesPerOldShare"], t["newCompanySharesPerOldShare"], t["recordDate"]) == (0.6503913, 0.3496087, "2025-10-31")
    with pytest.raises(ValueError, match="TERM_ROW_NOT_FOUND"):
        M.parse_bonus_issue(["4. 신주배정기준일 | 2017.04.10"])


def test_the_dps_missing_window_is_a_stated_zero_common_dividend():
    d = OUT["dpsMissingInWindowCashDividend"]
    assert (d["ticker"], d["commonDpsKrw"], d["status"]) == ("034020.KS", 0.0, "COMMON_ZERO_STATED_CLASS_SHARE_ONLY")
    assert M.parse_common_cash_dps(["3. 1주당 배당금(원) | 보통주식 | -", "종류주식 | 1,356"])["commonDpsKrw"] == 0.0
    assert M.parse_common_cash_dps(["3. 1주당 배당금(원) | 보통주식 | -"])["status"] == "UNRESOLVED"
    assert M.parse_common_cash_dps(["3. 1주당 배당금(원) | 보통주식 | 1,000"])["commonDpsKrw"] == 1000.0


def test_the_uncited_terminal_stays_unbounded():
    still = [e for e in OUT["events"] if e["status"] == "NO_CONSIDERATION_FILED"]
    assert [e["ticker"] for e in still] == ["051310.KS"] == [e["ticker"] for e in still if "terms" not in e]
    assert OUT["summary"] == {"events": 8, "termsCitedFromDart": 7, "stillUnbounded": ["포스코플랜텍"]}
