"""Synthetic tests for the S2 institutional-trade ledgers (no network, no real data)."""
import datetime as dt

from research.market_structure_discovery_s2 import build_ledgers as bl
from research.market_structure_discovery_s2 import collect_kodex_pdf as ck
from research.market_structure_discovery_s2 import parse_spdji as ps
from research.market_structure_discovery_s2 import power_mde as pm


def _snap(d, codes, w=0.5):
    return {"date": d, "sha256": "x",
            "members": {c: {"name": c, "q": 10.0, "v": 1.0, "w": w} for c in codes}}


def _base(n):
    return [f"{i:06d}" for i in range(1, n + 1)]


def test_regular_review_adds_and_drops_are_detected_with_dates():
    base = _base(200)
    new = base[3:] + ["900001", "900002", "900003"]
    snaps = [_snap(dt.date(2025, 6, 11), base), _snap(dt.date(2025, 6, 16), new)]
    led = bl.index_ledger(snaps, "KOSPI200", 195)
    adds = [e for e in led["events"] if e["action"] == "ADD"]
    drops = [e for e in led["events"] if e["action"] == "DROP"]
    assert {e["code"] for e in adds} == {"900001", "900002", "900003"}
    assert len(drops) == 3
    assert all(e["regularReview"] for e in led["events"])
    assert adds[0]["firstSeen"] == "2025-06-16" and adds[0]["lastAbsent"] == "2025-06-11"


def test_temporary_pdf_exclusion_is_not_an_index_event():
    base = _base(200)
    snaps = [_snap(dt.date(2022, 1, 7), base),
             _snap(dt.date(2022, 1, 14), [c for c in base if c != "000005"]),
             _snap(dt.date(2022, 1, 28), base)]
    led = bl.index_ledger(snaps, "KOSPI200", 195)
    assert len(led["events"]) == 2
    assert all(e.get("pdfArtifact") == "PDF_TEMPORARY_EXCLUSION" for e in led["events"])
    summ = bl.summarize_index(led)
    assert summ["adds"] == 0 and summ["drops"] == 0
    assert summ["pdfTemporaryExclusionRowsExcluded"] == 2


def test_gaps_over_40_days_are_not_read_as_changes():
    base = _base(200)
    snaps = [_snap(dt.date(2018, 6, 1), base), _snap(dt.date(2022, 1, 7), base[10:] + _base(210)[200:])]
    led = bl.index_ledger(snaps, "KOSPI200", 195)
    assert led["events"] == []
    assert led["unobservedGaps"] == [["2018-06-01", "2022-01-07"]]


def test_partial_replication_period_is_skipped():
    snaps = [_snap(dt.date(2011, 6, 1), _base(137)), _snap(dt.date(2011, 7, 1), _base(136))]
    led = bl.index_ledger(snaps, "KOSPI200", 195)
    assert led["fullReplicationFrom"] is None and led["events"] == []


def test_pre_event_denominator_ends_before_the_event():
    series = [(f"2024-{m:02d}-{d:02d}", 100.0) for m in range(1, 7) for d in range(1, 21)]
    series.append(("2024-06-25", 1e12))  # a post-event value must never enter
    adv, n = bl.pre_event_adv(series, "2024-06-21")
    assert adv == 100.0 and n == 60


def test_spdji_summary_table_rows():
    body = "\n".join(["Effective Date", "Index Name", "Action", "Company Name", "Ticker", "GICS Sector",
                      "Dec 22, 2025", "S&P 500", "Addition", "Carvana", "CVNA", "Consumer Discretionary",
                      "Dec 22, 2025", "S&P 500", "Deletion", "LKQ", "LKQ", "Consumer Discretionary",
                      "Dec 22, 2025", "S&P MidCap 400", "Addition", "Pinterest", "PINS", "Communication"])
    rows = ps.table_rows(body)
    assert [(r["index"], r["action"], r["ticker"]) for r in rows] == [
        ("S&P 500", "Addition", "CVNA"), ("S&P 500", "Deletion", "LKQ"), ("S&P MidCap 400", "Addition", "PINS")]
    assert rows[0]["effectiveDate"] == "2025-12-22"


def test_review_schedule_uses_wednesday_and_following_monday():
    dates = ck.review_schedule(dt.date(2025, 1, 1), dt.date(2025, 12, 31))
    assert dates == [dt.date(2025, 6, 11), dt.date(2025, 6, 16), dt.date(2025, 12, 10), dt.date(2025, 12, 15)]


def test_mde_shrinks_with_effective_sample_and_clustering_inflates_it():
    independent = pm.mde(100, 100, 0.2, 0.0)
    clustered = pm.mde(100, 10, 0.2, 0.3)
    assert independent["nEffective"] == 100
    assert clustered["mdePctPoints"] > independent["mdePctPoints"]
