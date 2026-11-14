from datetime import date, datetime

import pytest

from research.us_sec_fundamentals_v1.assets import AssetFact, _asset_index, features_as_of, load_assets, with_sec_assets

ACCESSION = "0000000001-26-000001"
FACT = AssetFact(date(2026, 6, 30), date(2026, 7, 31), datetime.fromisoformat("2026-08-01T01:30:00Z"), 100, "fsds")
ASSETS = {("1", ACCESSION): FACT}
RECORD = {
    "cik": "0000000001", "accession": ACCESSION, "periodEnd": "2026-06-30",
    "availableFrom": "2026-07-31", "acceptedDate": "2026-07-31 21:30:00", "periodDays": 365,
    "fiscalYear": 2026, "statements": {
        "bs": [],
        "cf": [{"concept": "us-gaap_NetCashProvidedByUsedInOperatingActivities", "unit": "USD", "value": 12}],
    },
}


def test_sec_overlay_enters_existing_feature_only_after_both_sources_are_visible():
    assert features_as_of([RECORD], "2026-07-31", ASSETS, cik="1")["cashOperatingProfitability"] is None
    assert features_as_of([RECORD], "2026-08-01", ASSETS, cik="1")["cashOperatingProfitability"] == 0.12
    assert features_as_of([RECORD], "2026-08-01", ASSETS, cik="2")["cashOperatingProfitability"] is None
    assert RECORD["statements"]["bs"] == []


@pytest.mark.parametrize("changes", [
    {"cik": "2"}, {"accession": "0000000001-26-000002"}, {"periodEnd": "2026-06-29"},
    {"availableFrom": "2026-07-30"}, {"acceptedDate": None}, {"acceptedDate": "2026-08-02"},
    {"acceptedDate": "invalid"},
    {"statements": {"bs": [{"concept": "Assets", "unit": "USD", "value": 90}]}},
])
def test_sec_overlay_withholds_mismatches_and_existing_assets(changes):
    record = {**RECORD, **changes}
    assert with_sec_assets(record, ASSETS, date(2026, 8, 1)) is record


def test_committed_payload_and_duplicate_check():
    assets = load_assets()
    assert len(assets) == 619
    assert assets[("920760", "0001628280-26-064557")].usd == 33_378_225_000
    assert assets[("1604778", "0001628280-26-050166")].usd == 5_939_456_000
    line = b'["1","0000000001-26-000001","2026-06-30","2026-07-31","2026-08-01T01:30:00Z",100,"fsds"]\n'
    with pytest.raises(ValueError, match="Duplicate SEC asset fact"):
        _asset_index(line * 2)
