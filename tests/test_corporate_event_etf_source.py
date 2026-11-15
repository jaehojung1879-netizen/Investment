"""Fixed issuer projection plus invented failure cases; no market outcomes."""
import hashlib
import json
from pathlib import Path

import pytest

from research.corporate_event_readiness_v1.etf.source import (
    inspect_price_date_projection,
    inspect_source,
    project_source,
)


ROOT = Path(__file__).resolve().parents[1] / "research/corporate_event_readiness_v1/etf"


def test_fixed_official_source_projection():
    raw = (ROOT / "issuer-projection.json").read_bytes()
    receipts = json.loads((ROOT / "source-receipts.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == receipts["projectionSha256"]
    result = inspect_source(raw)
    assert result["instrument"]["fundFnm"] == "삼성KODEX단기채권증권상장지수투자신탁[채권]"
    assert result["instrument"]["kodexinfoBmIdx"] == "KRW Cash Index Total Return"
    assert result["coverage"] == {
        "observedEvents": 15, "firstRecordDate": "2025-08-14",
        "lastRecordDate": "2026-10-15", "fullHistoryCertified": False,
    }
    assert not result["quarantine"]
    assert all(event["exDate"] is None for event in result["events"])
    assert not result["dataEligibilityValidated"]
    assert not result["economicEmpiricismReady"]
    assert not result["outcomeExecutionAuthorized"]
    assert not result["provenanceVerified"]


def test_projection_excludes_outcomes_and_is_idempotent():
    raw = (ROOT / "issuer-projection.json").read_bytes()
    payload = json.loads(raw)
    payload["suik"] = {"NAV": "SYNTHETIC_UNREAD", "earningRate": "SYNTHETIC_UNREAD"}
    payload["info"]["product"]["nav"] = "SYNTHETIC_UNREAD"
    assert project_source(json.dumps(payload).encode()) == raw
    assert project_source(raw) == raw


def test_different_instrument_rejected():
    payload = json.loads((ROOT / "issuer-projection.json").read_bytes())
    payload["info"]["product"]["stkTicker"] = "069500"
    with pytest.raises(ValueError, match="ISSUER_INSTRUMENT_MISMATCH"):
        inspect_source(json.dumps(payload).encode())


@pytest.mark.parametrize("field,value,reason", [
    ("BASIC_D", "20260230", "day is out of range"),
    ("PAY_D", "20120101", "PAYMENT_PRECEDES_RECORD"),
    ("DIVID_A", "NaN", "INVALID_DISTRIBUTION_AMOUNT"),
    ("DIVID_A", "-1", "INVALID_DISTRIBUTION_AMOUNT"),
])
def test_bad_event_is_quarantined(field, value, reason):
    payload = json.loads((ROOT / "issuer-projection.json").read_bytes())
    payload["info"]["divideList"][0][field] = value
    result = inspect_source(json.dumps(payload).encode())
    assert result["coverage"]["observedEvents"] == 14
    assert reason in result["quarantine"][0]["reason"]
    assert not result["coverage"]["fullHistoryCertified"]


def test_duplicate_keeps_first_event_and_quarantines_followup():
    payload = json.loads((ROOT / "issuer-projection.json").read_bytes())
    payload["info"]["divideList"].append(payload["info"]["divideList"][0].copy())
    result = inspect_source(json.dumps(payload).encode())
    assert len(result["events"]) == 15
    assert result["quarantine"][-1]["reason"] == "DUPLICATE_RECORD_DATE"


@pytest.mark.parametrize("raw", [b"not json", b"{}", b'{"info":null}'])
def test_malformed_document_rejected(raw):
    with pytest.raises(ValueError, match="INVALID_ISSUER_PAYLOAD"):
        inspect_source(raw)


def test_missing_event_date_is_quarantined():
    payload = json.loads((ROOT / "issuer-projection.json").read_bytes())
    del payload["info"]["divideList"][0]["BASIC_D"]
    result = inspect_source(json.dumps(payload).encode())
    assert result["quarantine"][0]["reason"] == "INVALID_ISSUER_DATE"


def test_official_price_date_projection_proves_dates_only():
    raw = (ROOT / "issuer-price-date-projection.json").read_bytes()
    receipts = json.loads((ROOT / "source-receipts.json").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == receipts["priceProjectionSha256"]
    result = inspect_price_date_projection(raw)
    assert result["observedDateRows"] == 3610
    assert result["firstDate"] == "2012-02-22"
    assert result["lastDate"] == "2026-11-04"
    assert result["missingSessions"] is None
    assert result["zeroVolumeSessions"] is None
    assert result["priceValuesValidated"] is False
    assert result["tradabilityValidated"] is False
    assert result["officialSessionCalendarReconciled"] is False
    assert result["outcomeExecutionAuthorized"] is False


def test_duplicate_price_date_rejected():
    payload = json.loads((ROOT / "issuer-price-date-projection.json").read_bytes())
    payload["dates"].append(payload["dates"][0])
    with pytest.raises(ValueError, match="DUPLICATE_PRICE_DATE"):
        inspect_price_date_projection(json.dumps(payload).encode())


def test_reordered_price_dates_rejected():
    payload = json.loads((ROOT / "issuer-price-date-projection.json").read_bytes())
    payload["dates"].reverse()
    with pytest.raises(ValueError, match="PRICE_DATE_ORDER_MISMATCH"):
        inspect_price_date_projection(json.dumps(payload).encode())
