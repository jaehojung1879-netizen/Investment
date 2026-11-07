"""Read only whitelisted issuer metadata and distribution events.

The issuer response also contains NAV and performance. These paths are never
selected here. A current webpage cannot prove historical publication vintage.
The registered economics adapters in PR #317 remain the eventual TR gates;
this module neither replaces those gates nor computes an economic outcome.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json


PRODUCT_FIELDS = (
    "stkTicker", "fId", "fNm", "fundFnm", "listD", "kodexinfoBmIdx",
    "bosuInfo", "taxation", "taxTpCd", "dividRemark", "minTradeUnit",
)
DISTRIBUTION_FIELDS = ("BASIC_D", "PAY_D", "DIVID_A", "TAX_DIVID_A")


def project_source(raw: bytes) -> bytes:
    """Deterministic projection, retaining no market prices, NAV or returns."""
    try:
        payload = json.loads(raw)
        product = payload["info"]["product"]
        records = payload["info"]["divideList"]
        if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
            raise ValueError("INVALID_ISSUER_PAYLOAD")
        selected = {
            "info": {
                "product": {key: product[key] for key in PRODUCT_FIELDS},
                "divideList": [{key: row.get(key) for key in DISTRIBUTION_FIELDS} for row in records],
            }
        }
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("INVALID_ISSUER_PAYLOAD") from exc
    return (json.dumps(selected, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _date(value: str) -> str:
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        raise ValueError("INVALID_ISSUER_DATE")
    return date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}").isoformat()


def _amount(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("INVALID_DISTRIBUTION_AMOUNT") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("INVALID_DISTRIBUTION_AMOUNT")
    return str(amount)


def inspect_source(raw: bytes) -> dict:
    """Verify instrument identity, preserve record/payment dates, quarantine errors."""
    projection = project_source(raw)
    payload = json.loads(projection)["info"]
    product = payload["product"]
    if product["stkTicker"] != "153130" or product["fId"] != "2ETF35":
        raise ValueError("ISSUER_INSTRUMENT_MISMATCH")
    if _date(product["listD"]) != "2012-02-22":
        raise ValueError("LISTING_DATE_MISMATCH")
    events, quarantine, seen = [], [], set()
    for index, row in enumerate(payload["divideList"]):
        try:
            record, payment = _date(row["BASIC_D"]), _date(row["PAY_D"])
            if record in seen:
                raise ValueError("DUPLICATE_RECORD_DATE")
            if payment < record:
                raise ValueError("PAYMENT_PRECEDES_RECORD")
            gross, taxable = _amount(row["DIVID_A"]), _amount(row["TAX_DIVID_A"])
            if Decimal(taxable) > Decimal(gross):
                raise ValueError("TAXABLE_AMOUNT_EXCEEDS_GROSS")
            seen.add(record)
            events.append({"recordDate": record, "paymentDate": payment, "exDate": None,
                           "grossAmount": gross, "taxableAmount": taxable,
                           "currency": "KRW", "investorNetCash": None})
        except ValueError as exc:
            quarantine.append({"sourceRow": index, "reason": str(exc)})
    events.sort(key=lambda row: row["recordDate"])
    return {
        "instrument": product, "events": events, "quarantine": quarantine,
        "inputSha256": hashlib.sha256(raw).hexdigest(),
        "projectionSha256": hashlib.sha256(projection).hexdigest(),
        "coverage": {
            "observedEvents": len(events),
            "firstRecordDate": events[0]["recordDate"] if events else None,
            "lastRecordDate": events[-1]["recordDate"] if events else None,
            "fullHistoryCertified": False,
        },
        "evidenceLevel": "INPUT_CONTENT_CHECKS_ONLY_NOT_SOURCE_AUTHENTICATION",
        "provenanceVerified": False,
        "dataEligibilityValidated": False, "economicEmpiricismReady": False,
        "outcomeExecutionAuthorized": False,
        "blockers": ["AS_TRADED_PRICE_CALENDAR_AND_TRADABILITY_UNVERIFIED", "FULL_DISTRIBUTION_HISTORY_UNVERIFIED",
                     "EX_DATE_EVIDENCE_ABSENT", "HISTORICAL_PUBLICATION_VINTAGE_UNVERIFIED",
                     "DATED_FEES_TAX_COST_LIQUIDITY_UNVERIFIED", "DATA_RIGHTS_UNVERIFIED"],
    }


def project_price_dates(raw: bytes) -> bytes:
    """Extract XLS date column and fixed headers only, never numeric price/NAV cells.

    xlrd 2.0.2 is already pinned in the repository's benchmark-audit requirements.
    The projection proves observed date labels, not valid executable prices.
    """
    import xlrd

    sheet = xlrd.open_workbook(file_contents=raw).sheet_by_index(0)
    title = sheet.cell_value(0, 0)
    headers = {"date": sheet.cell_value(2, 0), "tradePrice": sheet.cell_value(2, 1),
               "close": sheet.cell_value(3, 1), "volume": sheet.cell_value(3, 4),
               "fundNav": sheet.cell_value(2, 5), "taxNav": sheet.cell_value(2, 8)}
    if title != "KODEX 단기채권 기준가격" or headers != {
        "date": "일자", "tradePrice": "거래가격(원)", "close": "종가",
        "volume": "거래량", "fundNav": "펀드기준가격(원)", "taxNav": "과표기준가(원)",
    }:
        raise ValueError("PRICE_XLS_SCHEMA_MISMATCH")
    rows = [_date(sheet.cell_value(index, 0)) for index in range(4, sheet.nrows)]
    projection = {"title": title, "headers": headers, "dates": rows,
                  "originalSha256": hashlib.sha256(raw).hexdigest(),
                  "numericPriceNavOrVolumeSelected": False}
    return (json.dumps(projection, ensure_ascii=False, sort_keys=True) + "\n").encode()


def inspect_price_date_projection(raw: bytes) -> dict:
    """Count actual observed date labels without certifying calendar completeness."""
    payload = json.loads(raw)
    dates = payload["dates"]
    if any(date.fromisoformat(day).isoformat() != day for day in dates):
        raise ValueError("INVALID_PRICE_DATE")
    if len(dates) != len(set(dates)):
        raise ValueError("DUPLICATE_PRICE_DATE")
    if dates != sorted(dates, reverse=True):
        raise ValueError("PRICE_DATE_ORDER_MISMATCH")
    return {"observedDateRows": len(dates), "firstDate": min(dates) if dates else None,
            "lastDate": max(dates) if dates else None,
            "officialSessionCalendarReconciled": False, "priceValuesValidated": False,
            "tradabilityValidated": False, "historicalPublicationVintageVerified": False,
            "outcomeExecutionAuthorized": False,
            "missingSessions": None, "zeroVolumeSessions": None,
            "sourceSha256": payload["originalSha256"],
            "projectionSha256": hashlib.sha256(raw).hexdigest()}


def reconcile_price_sessions(raw: bytes, *, expected_sessions: list[str],
                             requested_through: str, calendar_id: str) -> dict:
    """Compare fixed labels to an independently supplied calendar, not to prices.

    Library/session agreement is not an official-exchange certification, a
    historical vintage, an execution price or an investable return series.
    Reject a supposedly dated endpoint that actually returns later observations.
    """
    checked = inspect_price_date_projection(raw)
    cutoff = date.fromisoformat(requested_through).isoformat()
    if (not expected_sessions or not calendar_id
            or expected_sessions != sorted(set(expected_sessions))
            or any(date.fromisoformat(d).isoformat() != d for d in expected_sessions)
            or expected_sessions[-1] > cutoff):
        raise ValueError("INDEPENDENT_ORDERED_CALENDAR_REQUIRED")
    observed = set(json.loads(raw)["dates"])
    expected = set(expected_sessions)
    missing, unexpected = sorted(expected - observed), sorted(observed - expected)
    after = sorted(d for d in observed if d > cutoff)
    blockers = []
    if after:
        blockers.append("OBSERVATIONS_AFTER_REQUESTED_CUTOFF")
    if missing:
        blockers.append("MISSING_EXPECTED_SESSIONS")
    if unexpected:
        blockers.append("UNEXPECTED_OBSERVATION_SESSIONS")
    return {
        "status": "BLOCKED" if blockers else "REPOSITORY_CALENDAR_LABELS_MATCH",
        "calendarId": calendar_id, "requestedThrough": cutoff,
        "calendarSha256": hashlib.sha256(json.dumps(expected_sessions, separators=(",", ":")).encode()).hexdigest(),
        "expectedSessionCount": len(expected_sessions), "observedDateCount": len(observed),
        "missingSessions": missing, "unexpectedSessions": unexpected,
        "observationsAfterRequestedCutoff": after, "blockers": blockers,
        "sourceSha256": checked["sourceSha256"], "projectionSha256": checked["projectionSha256"],
        "officialSessionCalendarCertified": False, "priceValuesValidated": False,
        "historicalPublicationVintageVerified": False,
        "economicEmpiricismReady": False, "outcomeExecutionAuthorized": False,
    }


def project_price_quality(raw: bytes) -> dict:
    """Inspect close/volume validity only; never retain values or compute returns.

    NAV, price change and the provider's published returns are never selected.
    Zero reported volume is an execution-data blocker, not a last-price fill.
    """
    import xlrd

    dates = json.loads(project_price_dates(raw))["dates"]
    sheet = xlrd.open_workbook(file_contents=raw).sheet_by_index(0)
    bad_price, bad_volume, zero_volume = [], [], []
    for index, day in enumerate(dates, start=4):
        values = []
        for column in (1, 4):  # already-verified close and volume headers only
            try:
                value = Decimal(str(sheet.cell_value(index, column)).replace(",", ""))
                values.append(value if value.is_finite() else None)
            except InvalidOperation:
                values.append(None)
        close, volume = values
        if close is None or close <= 0:
            bad_price.append(day)
        if volume is None or volume < 0 or volume != volume.to_integral_value():
            bad_volume.append(day)
        elif volume == 0:
            zero_volume.append(day)
    return {
        "sourceSha256": hashlib.sha256(raw).hexdigest(), "observedRows": len(dates),
        "firstDate": min(dates) if dates else None, "lastDate": max(dates) if dates else None,
        "invalidCloseDates": bad_price, "invalidVolumeDates": bad_volume,
        "zeroReportedVolumeDates": zero_volume,
        "numericPriceValuesRetained": False, "navSelected": False,
        "returnsComputed": 0, "tradabilityCertified": False,
        "historicalPublicationVintageVerified": False,
        "economicEmpiricismReady": False, "outcomeExecutionAuthorized": False,
    }
