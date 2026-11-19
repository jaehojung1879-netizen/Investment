"""Synthetic tests for industry-relative returns. No real return is read."""
import pytest

from research.master_research_program_v1.market_industry import industry_relative as R
from research.master_research_program_v1.market_industry import us_sector_membership as U

W = ("2026-01-05", "2026-07-06")


def _snaps(extra=None):
    snaps = [("2025-12-01", "2025-12-01T00:00:00Z", "c1", {"A": "Energy", "B": "Energy", "C": "Utilities"})] + (extra or [])
    members = {"snapshots": [{"date": d, "publishedAt": p, "sourceCommit": c, "members": list(rows)} for d, p, c, rows in snaps]}
    sectors = {"snapshots": [{"date": d, "sourceCommit": c, "sectorColumn": "GICS Sector", "hasCik": False,
                              "rows": {k: {"sector": v, "cik": None} for k, v in rows.items()}} for d, _, c, rows in snaps]}
    built = U.build_snapshots(members, sectors)
    return lambda as_of: {m: v["sector"] for m, v in U.membership_table(built, as_of).items()}


def _ret(v):
    return {"start": W[0], "end": W[1], "tr": v}


ETF = {"start": W[0], "end": W[1], "tr": 0.05}


def test_equal_and_cap_weighted_relative():
    out = R.industry_relative(_snaps(), "2026-01-02", W, "Energy", {"A": _ret(0.10), "B": _ret(0.20)}, ETF, caps={"A": 3.0, "B": 1.0})
    assert out["EQUAL"]["relative"] == pytest.approx(0.15 - 0.05)
    assert out["CAP"]["relative"] == pytest.approx((3 * 0.10 + 0.20) / 4 - 0.05)
    assert out["CAP"]["top1CapShare"] == pytest.approx(0.75)


def test_mismatched_dates_are_refused():
    bad = {"A": _ret(0.1), "B": {"start": W[0], "end": "2026-07-07", "tr": 0.2}}
    with pytest.raises(ValueError, match="DATE_MISMATCH"):
        R.industry_relative(_snaps(), "2026-01-02", W, "Energy", bad, ETF)
    with pytest.raises(ValueError, match="DATE_MISMATCH"):
        R.industry_relative(_snaps(), "2026-01-02", W, "Energy", {"A": _ret(0.1), "B": _ret(0.2)},
                            {"start": "2026-01-06", "end": W[1], "tr": 0.05})


def test_missing_constituent_return_gives_none_and_is_counted():
    out = R.industry_relative(_snaps(), "2026-01-02", W, "Energy", {"A": _ret(0.1)}, ETF, caps={"A": 1.0, "B": 1.0})
    assert out["EQUAL"]["value"] is None and out["EQUAL"]["missingReturn"] == 1
    assert out["CAP"]["value"] is None and out["CAP"]["relative"] is None
    nan = R.industry_relative(_snaps(), "2026-01-02", W, "Energy", {"A": _ret(0.1), "B": _ret(float("nan"))}, ETF)
    assert nan["EQUAL"]["value"] is None


def test_missing_cap_blocks_only_the_cap_basket():
    out = R.industry_relative(_snaps(), "2026-01-02", W, "Energy", {"A": _ret(0.1), "B": _ret(0.2)}, ETF, caps={"A": 1.0})
    assert out["EQUAL"]["value"] == pytest.approx(0.15)
    assert out["CAP"]["value"] is None and out["CAP"]["missingCap"] == 1


def test_future_snapshot_cannot_alter_past_membership():
    later = [("2026-03-01", "2026-03-01T00:00:00Z", "c2", {"A": "Energy", "B": "Energy", "D": "Energy", "C": "Utilities"})]
    rets = {"A": _ret(0.1), "B": _ret(0.2), "D": _ret(0.9)}
    before = R.industry_relative(_snaps(), "2026-01-02", W, "Energy", rets, ETF)
    after = R.industry_relative(_snaps(later), "2026-01-02", W, "Energy", rets, ETF)
    assert before == after and before["members"] == ["A", "B"]


def test_window_cannot_start_before_signal():
    with pytest.raises(ValueError, match="WINDOW_STARTS_BEFORE_SIGNAL"):
        R.industry_relative(_snaps(), "2026-01-06", W, "Energy", {"A": _ret(0.1), "B": _ret(0.2)}, ETF)


def test_cross_section_counts_refused_baskets():
    out = R.industry_cross_section(_snaps(), "2026-01-02", W, {"A": _ret(0.1), "B": _ret(0.2)}, ETF)
    assert out["industries"] == 2 and out["equalWeightRefused"] == 1     # Utilities member C has no return
