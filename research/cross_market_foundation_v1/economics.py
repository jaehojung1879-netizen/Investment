"""Outcome-free cash and shareholder-distribution admission adapters.

No price return, attribution, portfolio or NAV is computed here. Benchmark
quotes stay quotes; record/payment dates never become ex-dates by inference.
Existing ECOS, dividend-reconciliation and terminal-action readers remain the
authorities for their original contracts.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from pipeline import ecos_macro
from pipeline import kr_alpha_atlas_benchmark_audit as benchmark_audit
from pipeline import kr_dividend_reconciliation as dividend_reconciliation

CONTRACT = "CROSS_MARKET_ECONOMIC_INPUTS_V1"
QUOTE_KINDS = frozenset({"KOFR", "CD91", "BOK_POLICY_RATE"})
INVESTABLE_BASES = frozenset({"REALIZED_CASH_PAYOFF", "INVESTABLE_NAV_RETURN"})
RIGHTS = "VERIFIED_INTERNAL_RESEARCH"


class EconomicInputError(ValueError):
    """A stable failure code, never a substituted economic assumption."""


def _date(value: object) -> str:
    try:
        text = str(value)
        if len(text) == 8 and text.isdigit():
            text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
        return date.fromisoformat(text).isoformat()
    except (ValueError, TypeError) as exc:
        raise EconomicInputError("INVALID_ECONOMIC_DATE") from exc


def _number(value: object, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise EconomicInputError("INVALID_ECONOMIC_NUMBER")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise EconomicInputError("INVALID_ECONOMIC_NUMBER") from exc
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise EconomicInputError("INVALID_ECONOMIC_NUMBER")
    return result


def _digest(value: object) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in value)):
        raise EconomicInputError("SOURCE_DIGEST_REQUIRED")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise EconomicInputError("SOURCE_DIGEST_REQUIRED") from exc
    return value


def parse_ecos_benchmark_quotes(raw: bytes, *, spec: Mapping) -> dict:
    """Parse a verified exact ECOS selector without calling the network.

    This is deliberately an adapter to ``ecos_macro`` rather than another
    ECOS client. Its output is NEVER an investable cash-return input. Current
    revised history is not a point-in-time publication vintage.
    """
    kind = spec.get("kind")
    if kind not in QUOTE_KINDS:
        raise EconomicInputError("UNSUPPORTED_CASH_QUOTE")
    try:
        selected = ecos_macro.resolve_spec(kind, spec, ecos_series={kind: spec})
    except ecos_macro.AmbiguousSeries as exc:
        raise EconomicInputError("CASH_SERIES_IDENTITY_UNVERIFIED") from exc
    if selected["cycle"] != "D":
        raise EconomicInputError("DAILY_CASH_QUOTE_REQUIRED")
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise EconomicInputError("INVALID_SOURCE_PAYLOAD") from exc
    rows, error = ecos_macro.parse_response(payload)
    if error:
        raise EconomicInputError("ECOS_SOURCE_ROWS_UNAVAILABLE")
    out, seen = [], set()
    for row in rows:
        if (row.get("STAT_CODE") != selected["seriesId"]
                or row.get("ITEM_CODE1") != selected["itemCode"]):
            raise EconomicInputError("CASH_SELECTOR_MISMATCH")
        if row.get("UNIT_NAME") not in {"연%", "연 %"}:
            raise EconomicInputError("CASH_QUOTE_UNIT_UNVERIFIED")
        for number in (2, 3, 4):
            wanted = selected.get(f"itemCode{number}")
            actual = row.get(f"ITEM_CODE{number}")
            if (wanted and actual != wanted) or (not wanted and actual not in (None, "")):
                raise EconomicInputError("CASH_SELECTOR_MISMATCH")
        stamp, value = ecos_macro.row_to_observation(row)
        stamp = _date(stamp)
        if value is None:
            raise EconomicInputError("MISSING_CASH_QUOTE")
        if stamp in seen:
            raise EconomicInputError("DUPLICATE_CASH_QUOTE")
        seen.add(stamp)
        out.append({"date": stamp, "annualPercent": value})
    return {"contract": CONTRACT, "kind": kind, "basis": "REFERENCE_RATE_QUOTE",
            "currency": "KRW", "observations": sorted(out, key=lambda row: row["date"]),
            "sourcePayloadSha256": hashlib.sha256(raw).hexdigest(),
            "vintageStatus": ecos_macro.PIT_STATUS_FOR_ALL_SERIES,
            "publicationAvailability": "UNVERIFIED", "investable": False}


def build_cash_input_contract(rows: Sequence[Mapping], *, required_dates: Sequence[str],
                              as_of: str, currency: str = "KRW") -> dict:
    """Admit only documented investor cash outcomes on an exact daily grid.

    This validates supplied outcomes, not a permission to execute a study.
    There is no conversion of CD91/KOFR/base-rate quotations into returns,
    forward fill, maturity roll assumption, or pre-launch backfill.
    """
    dates = [_date(value) for value in required_dates]
    if not dates or len(set(dates)) != len(dates) or dates != sorted(dates):
        raise EconomicInputError("INVALID_REQUIRED_CASH_GRID")
    if any((date.fromisoformat(right) - date.fromisoformat(left)).days != 1
           for left, right in zip(dates, dates[1:])):
        raise EconomicInputError("CASH_CALENDAR_GRID_GAP")
    known = _date(as_of)
    if dates[-1] > known:
        raise EconomicInputError("FUTURE_CASH_PERIOD")
    selected = {}
    for row in rows:
        if row.get("basis") not in INVESTABLE_BASES:
            raise EconomicInputError("REFERENCE_RATE_NOT_INVESTABLE_CASH")
        if row.get("currency") != currency:
            raise EconomicInputError("CASH_CURRENCY_MISMATCH")
        if row.get("rights") != RIGHTS:
            raise EconomicInputError("CASH_RIGHTS_UNVERIFIED")
        if (not row.get("instrumentId") or not row.get("termsEvidence")
                or row.get("costBasis") != "NET_OF_INSTRUMENT_COSTS"):
            raise EconomicInputError("INVESTABLE_TERMS_UNVERIFIED")
        if row.get("investorTaxBasis") not in {"GROSS_PRE_INVESTOR_TAX", "NET_DOCUMENTED_INVESTOR_TAX"}:
            raise EconomicInputError("CASH_TAX_BASIS_UNVERIFIED")
        _digest(row.get("sourcePayloadSha256"))
        end, start, available = map(_date, (row.get("date"), row.get("periodStart"), row.get("availableOn")))
        # A daily payoff must identify its one-calendar-day accrual period;
        # weekend cash periods belong in the caller's explicitly supplied grid.
        if (date.fromisoformat(end) - date.fromisoformat(start)).days != 1:
            raise EconomicInputError("CASH_ACCRUAL_PERIOD_MISMATCH")
        if available < end or available > known:
            raise EconomicInputError("CASH_AVAILABILITY_MISMATCH")
        if end in selected:
            raise EconomicInputError("DUPLICATE_CASH_PERIOD")
        value = _number(row.get("netReturn"))
        if value <= -1:
            raise EconomicInputError("INVALID_CASH_PAYOFF")
        selected[end] = dict(row, date=end, periodStart=start, availableOn=available, netReturn=value)
    if set(selected) != set(dates):
        raise EconomicInputError("CASH_PERIOD_COVERAGE_GAP")
    if any(selected[right]["periodStart"] != left for left, right in zip(dates, dates[1:])):
        raise EconomicInputError("CASH_ACCRUAL_PERIOD_MISMATCH")
    return {"contract": CONTRACT, "basis": "INVESTABLE_CASH_INPUTS",
            "currency": currency, "asOf": known, "rows": [selected[stamp] for stamp in dates],
            "outcomeExecutionAuthorized": False}


def adapt_issuer_distributions(raw: bytes, *, security_id: str = "KR7069500007") -> dict:
    """Preserve Samsung's gross/taxable amounts and record/payment semantics.

    ``taxDividA`` is taxable income per unit, NOT cash net of withholding.
    Unlike the registered historical benchmark adapter, this generic interface
    does not infer an ex-date from a preceding calendar session.
    """
    if security_id != "KR7069500007":
        raise EconomicInputError("ISSUER_INSTRUMENT_MISMATCH")
    try:
        payload = json.loads(raw)
        source_rows = payload["dividList"]
    except (ValueError, TypeError, KeyError) as exc:
        raise EconomicInputError("INVALID_DISTRIBUTION_PAYLOAD") from exc
    if not isinstance(source_rows, list) or not source_rows:
        raise EconomicInputError("DISTRIBUTION_ROWS_ABSENT")
    digest = hashlib.sha256(raw).hexdigest()
    out, seen = [], set()
    for row in source_rows:
        record, payment = _date(row.get("basicD")), _date(row.get("payD"))
        if payment < record:
            raise EconomicInputError("PAYMENT_PRECEDES_RECORD_DATE")
        if record in seen:
            raise EconomicInputError("DUPLICATE_DISTRIBUTION_EVENT")
        seen.add(record)
        out.append({"eventId": f"{security_id}:{record}:CASH_DISTRIBUTION",
                    "securityId": security_id, "currency": "KRW", "shareBasis": "PER_ETF_UNIT",
                    "recordDate": record, "paymentDate": payment, "exDate": None,
                    "grossAmount": _number(row.get("dividA"), nonnegative=True),
                    "taxableAmount": _number(row.get("taxDividA"), nonnegative=True),
                    "investorNetCash": None, "availableOn": None,
                    "sourcePayloadSha256": digest})
    return {"contract": CONTRACT, "events": sorted(out, key=lambda row: row["recordDate"]),
            "coverage": "SOURCE_WINDOW_ONLY_NOT_FULL_HISTORY", "sourcePayloadSha256": digest,
            "exDateStatus": "UNRESOLVED", "rights": "UNVERIFIED"}


def verify_existing_benchmark_snapshot(directory: str | Path) -> dict:
    """Reuse the existing hash verifier; do not load or compute price returns."""
    return benchmark_audit.verified_sources(directory)


def reconcile_distribution_events(official: Sequence[Mapping], vendor: Sequence[Mapping]) -> dict:
    """Strict identity/basis/date gate around the existing reconciliation code."""
    sides = []
    for rows in (official, vendor):
        clean, used = [], set()
        for row in rows:
            key = (row.get("securityId"), row.get("eventId"))
            if not all(key) or key in used:
                raise EconomicInputError("DISTRIBUTION_IDENTITY_OR_DUPLICATE")
            used.add(key)
            if (row.get("amountBasis") != "GROSS_CASH" or not row.get("shareBasis")
                    or row.get("currency") not in {"KRW", "USD"}):
                raise EconomicInputError("DISTRIBUTION_BASIS_UNVERIFIED")
            stamp = _date(row.get("exDate"))
            if not row.get("exDateEvidence"):
                raise EconomicInputError("EX_DATE_EVIDENCE_REQUIRED")
            _digest(row.get("sourcePayloadSha256"))
            clean.append(dict(row, exDate=stamp, amountPerShare=_number(row.get("grossAmount"), nonnegative=True)))
        sides.append(clean)
    for left in sides[0]:
        for right in sides[1]:
            if left["eventId"] == right["eventId"] and any(
                left.get(key) != right.get(key) for key in ("securityId", "currency", "shareBasis")
            ):
                raise EconomicInputError("DISTRIBUTION_IDENTITY_OR_BASIS_MISMATCH")
    # Grouping prevents a same-date distribution on another security matching.
    keys = sorted({(row["securityId"], row["currency"], row["shareBasis"], row["eventId"]) for side in sides for row in side})
    results = []
    for security, currency, share_basis, event_id in keys:
        transformed = []
        for side in sides:
            transformed.append([dict(row, ticker=security, recordDate=row["exDate"], date=row["exDate"],
                                     isStockDividend=False) for row in side
                                if (row["securityId"], row["currency"], row["shareBasis"], row["eventId"])
                                == (security, currency, share_basis, event_id)])
        result = dividend_reconciliation.reconcile(*transformed, date_tolerance_days=0, amount_tolerance_pct=0)
        results.append({"securityId": security, "currency": currency, "shareBasis": share_basis, **result})
    pairs = sum(len(result["pairs"]) for result in results)
    disagreements = sum(result["disagreeingPairs"] for result in results)
    unmatched_official = sum(pair["dart"] is not None and pair["yahoo"] is None
                             for result in results for pair in result["pairs"])
    unmatched_vendor = sum(pair["dart"] is None and pair["yahoo"] is not None
                           for result in results for pair in result["pairs"])
    return {"contract": CONTRACT, "status": "MATCHED_EVENTS_ONLY" if pairs and not disagreements else "BLOCKED",
            "pairs": pairs, "disagreements": disagreements, "bySecurity": results,
            "unmatchedOfficialEvents": unmatched_official, "unmatchedVendorEvents": unmatched_vendor,
            "errors": (["NO_DISTRIBUTION_EVENTS"] if not pairs else [])
            + (["UNMATCHED_DISTRIBUTION_EVENTS"] if unmatched_official or unmatched_vendor else [])
            + (["DISTRIBUTION_DISAGREEMENTS"] if disagreements else []),
            "completenessCertified": False}


def total_return_input_gate(*, price_basis: str, distributions_complete: bool,
                           terminal_required: bool, terminal_evidence: str | None,
                           actions_complete: bool, investor_tax_basis: str,
                           raw_events_applied: bool = False) -> dict:
    """Prevent adjusted-price double counting and fabricated terminal values."""
    errors = []
    if price_basis not in {"AS_TRADED_CLOSE", "TOTAL_RETURN_INDEX"}:
        errors.append("PRICE_BASIS_UNVERIFIED")
    if price_basis == "TOTAL_RETURN_INDEX" and raw_events_applied:
        errors.append("DISTRIBUTION_DOUBLE_COUNTING")
    if distributions_complete is not True:
        errors.append("DISTRIBUTION_COVERAGE_UNVERIFIED")
    if actions_complete is not True:
        errors.append("CORPORATE_ACTION_COVERAGE_UNVERIFIED")
    if not isinstance(terminal_required, bool) or not isinstance(raw_events_applied, bool):
        errors.append("INVALID_ACTION_REQUIREMENT_FLAG")
    if terminal_required:
        try:
            _digest(terminal_evidence)
        except EconomicInputError:
            errors.append("TERMINAL_CONSIDERATION_UNRESOLVED")
    if investor_tax_basis not in {"GROSS_PRE_INVESTOR_TAX", "NET_DOCUMENTED_INVESTOR_TAX"}:
        errors.append("INVESTOR_TAX_BASIS_UNVERIFIED")
    return {"contract": CONTRACT, "status": "ADMISSIBLE_INPUT_CONTRACT" if not errors else "BLOCKED",
            "errors": errors, "evidenceLevel": "DECLARATION_AND_DIGEST_REFERENCE_ONLY",
            "sourcePayloadVerified": False, "outcomeExecutionAuthorized": False}
