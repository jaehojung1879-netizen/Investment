import pytest

from research.us_nonreliance_source_pilot_v1.catalog_audit import audit, compare_index


def row(ticker="A", items="2.02,4.02", accession="x", cik="001"):
    return dict(ticker=ticker, cik=cik, form="8-K", items=items, filingDate="2025-01-01",
                acceptanceDateTime="2025-01-01T21:06:00Z", accession=accession, reportDate="2025-01-01")


def test_alias_dedup_and_exact_item():
    result = audit([row(), row(ticker="B", cik="1"), row(items="2.02,4.021", accession="y")])
    assert result["rawRows"] == 3
    assert result["uniqueIssuerAccessions"] == 2
    assert result["bothRawRows"] == 2
    assert result["bothUniqueIssuerAccessions"] == 1


def test_conflicting_alias_refused():
    with pytest.raises(ValueError, match="conflicting"):
        audit([row(), row(ticker="B", items="2.02")])


def test_summer_and_winter():
    assert compare_index("2026-05-27T20:06:04Z", "2026-05-27T16:06:04")["status"] == "MATCH"
    assert compare_index("2026-02-25T21:06:32Z", "2026-02-25T16:06:32")["status"] == "MATCH"


def test_false_z_moves_calendar_day():
    result = compare_index("2026-05-27T16:06:04Z", "2026-05-27T16:06:04")
    assert result["differenceSeconds"] == -14400
    assert result["existingEffectiveCalendarDay"] == "2026-05-27"
    assert result["indexEffectiveCalendarDay"] == "2026-05-28"


def test_missing_not_match():
    assert compare_index("2026-05-27T20:06:04Z", "")["status"] == "UNVERIFIED"
