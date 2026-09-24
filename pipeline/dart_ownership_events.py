"""Raw DART large-shareholding disclosures with receipt-date PIT semantics.

The v2 contract preserves every economically relevant ``majorstock.json``
field confirmed by the live probe, including ``ctr_stkqy``, ``ctr_stkrt`` and
``report_resn``.  Raw labels remain raw; this module does not infer an alpha
classification.  Public availability is always the DART receipt date.  An
event/reference or transaction date is stored separately only when DART
actually supplies one and is never used to backdate availability.

Existing v1 shards remain readable.  Missing v2 fields stay ``None``: they are
not reconstructed, backfilled, or synthesized.  Receipt numbers are immutable
event identities.  A repeated receipt may enrich only fields newly observed
from the source; conflicting non-null source values are rejected.
"""
from __future__ import annotations

from . import dart_fundamentals as DF

# Reused directly. Recomputing "the first eight digits of the receipt number"
# a second time in this module is exactly the second-implementation risk
# `alpha-risk-separation-v1`'s invariants warn against one level up: a control
# that is called is safer than a control that is reproduced.
receipt_date = DF.receipt_date

# The two `report_tp` values a live probe run has actually observed (see
# module docstring for the run and counts). Listed so a probe or test can
# tell "a known raw value we chose not to translate" apart from "a value
# nobody has ever seen" — a materially different fact about the source.
KNOWN_REPORT_TYPE_RAW_VALUES = frozenset({"일반", "약식"})

# Deliberately empty. No raw value is mapped to a normalized `reportType`
# yet — see module docstring for why guessing one here would repeat the
# defect this correction fixes. Extending this dict is only correct once an
# authoritative source (OpenDART's own field guide, or DART support)
# confirms what a raw value means, at which point BOTH this map and
# `KNOWN_REPORT_TYPE_RAW_VALUES` should gain the new entry together.
_REPORT_TYPE_MAP: dict[str, str] = {}

# The 5% line the report family is named for. A holding percentage crossing
# below this on a CHANGE report is read as an exit signal — DERIVED, because
# no source consulted confirmed DART states "exited" as its own value.
DISCLOSURE_THRESHOLD_PCT = 5.0
RAW_CONTRACT = "DART_OWNERSHIP_EVENTS_RAW_V2"
SCHEMA_VERSION = 2


def parse_percent(text) -> float | None:
    """A DART percentage string to a float, or None where nothing was stated.

    Reuses the amount grammar `dart_fundamentals.parse_amount` already
    established (comma thousands, accounting parentheses, blank-means-none)
    rather than writing a second parser for the same grammar.
    """
    return DF.parse_amount(text)


def direction_of_change(stkrt_irds: float | None, stkrt: float | None) -> str | None:
    """INCREASE / DECREASE / EXIT_BELOW_THRESHOLD / None, derived and labelled as such.

    Never confused with a value DART stated: `report_tp` is DART's own word,
    and this is this module's own reading of `stkrt`/`stkrt_irds`, published
    under a different field name so the two are never mistaken for each other.
    """
    if stkrt_irds is None:
        return None
    if stkrt is not None and stkrt < DISCLOSURE_THRESHOLD_PCT and stkrt_irds < 0:
        return "EXIT_BELOW_THRESHOLD"
    if stkrt_irds > 0:
        return "INCREASE"
    if stkrt_irds < 0:
        return "DECREASE"
    return None


def _raw_text(row: dict, key: str) -> str | None:
    value = str(row.get(key) or "").strip()
    return value or None


def build_event(row: dict, *, ticker: str | None, collected_at: str,
                issuer_id: str | None = None) -> tuple[dict | None, str]:
    """One stored ownership-event row from one `majorstock.json` response row.

    Refused, never stored with a substitute, when the receipt date cannot be
    read — the same rule `dart_fundamentals.build_record` applies to a
    financial statement, for the same reason: a row that cannot say when it
    became visible is unusable in a point-in-time replay.
    """
    rcept_no = str(row.get("rcept_no") or "").strip()
    if not rcept_no:
        return None, "NO_RECEIPT_NO"
    available_from = receipt_date(rcept_no)
    if available_from is None:
        return None, "NO_RECEIPT_DATE"

    stkrt = parse_percent(row.get("stkrt"))
    stkrt_irds = parse_percent(row.get("stkrt_irds"))
    stkqy = parse_percent(row.get("stkqy"))
    stkqy_irds = parse_percent(row.get("stkqy_irds"))

    report_tp_raw = str(row.get("report_tp") or "").strip()
    report_type = _REPORT_TYPE_MAP.get(report_tp_raw)

    return {
        "id": f"dart-ownership:{rcept_no}",
        "schemaVersion": SCHEMA_VERSION,
        "issuerId": issuer_id or (f"DART:{row.get('corp_code')}" if row.get("corp_code") else None),
        "ticker": ticker,
        "corpCode": row.get("corp_code"),
        "corpName": row.get("corp_name"),
        "filerName": row.get("repror"),
        "reportType": report_type,
        "reportTypeRaw": report_tp_raw or None,
        "changeDirection": direction_of_change(stkrt_irds, stkrt),
        "holdingPctAfter": stkrt,
        "holdingPctChange": stkrt_irds,
        # "Before" is NOT computed as `stkrt - stkrt_irds` here — see module
        # docstring. A caller that wants it may derive it explicitly, with
        # this comment as the reason it is not done implicitly.
        "holdingPctBefore": None,
        "shareCountAfter": stkqy,
        "shareCountChange": stkqy_irds,
        "majorTransactionSharesRaw": _raw_text(row, "ctr_stkqy"),
        "majorTransactionOwnershipPctRaw": _raw_text(row, "ctr_stkrt"),
        "reportReasonRaw": _raw_text(row, "report_resn"),
        "eventDate": None,
        "reportDate": row.get("rcept_dt"),
        "availableFrom": available_from,
        "receiptNo": rcept_no,
        "currency": "KRW",
        "source": "DART:majorstock",
        "sourceEndpoint": "majorstock.json",
        "sourceFields": {
            "majorTransactionSharesRaw": "ctr_stkqy",
            "majorTransactionOwnershipPctRaw": "ctr_stkrt",
            "reportReasonRaw": "report_resn",
        },
        "collectedAt": collected_at,
    }, ""


def prior_filing_flags(events: list[dict]) -> list[dict]:
    """Mark only whether this issuer/reporter pair had an earlier filing."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for event in sorted(events, key=lambda e: (e.get("ticker"), e.get("filerName"),
                                               str(e.get("availableFrom")), e.get("receiptNo"))):
        key = (event.get("issuerId") or event.get("corpCode") or event.get("ticker"),
               event.get("filerName"))
        marked = dict(event)
        marked.pop("amendmentFlag", None)
        marked["priorFilingExists"] = key in seen
        seen.add(key)
        out.append(marked)
    return out


def read_compatible_event(event: dict) -> dict:
    """Read a v1/v2 event without inventing fields absent from the source."""
    out = dict(event)
    out.setdefault("schemaVersion", 1)
    out.setdefault("issuerId", f"DART:{out['corpCode']}" if out.get("corpCode") else None)
    out.setdefault("majorTransactionSharesRaw", None)
    out.setdefault("majorTransactionOwnershipPctRaw", None)
    out.setdefault("reportReasonRaw", None)
    out.setdefault("eventDate", None)
    if "amendmentFlag" in out and "priorFilingExists" not in out:
        out["priorFilingExists"] = bool(out["amendmentFlag"])
    return out


def merge_events(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """Deterministically deduplicate receipts and refuse source conflicts."""
    merged: dict[str, dict] = {}
    for raw in [*existing, *fresh]:
        event = dict(raw)
        key = str(event.get("id") or "")
        if not key:
            raise ValueError("ownership event has no immutable id")
        if key not in merged:
            merged[key] = event
            continue
        prior = merged[key]
        for field, value in event.items():
            old = prior.get(field)
            if value is None or value == "" or field == "collectedAt":
                continue
            if old in (None, ""):
                prior[field] = value
            elif old != value:
                raise ValueError(f"conflicting ownership event {key} field {field}")
    return sorted(merged.values(), key=lambda row: (str(row.get("availableFrom")), row["id"]))


# Kept as a source-compatible alias for callers; output uses the truthful name.
amendment_flags = prior_filing_flags


def shard_path(root, year: int):
    from pathlib import Path
    return Path(root) / f"dart-ownership-{int(year):04d}.jsonl.gz"


def record_year(event: dict) -> int | None:
    """The shard year, from the receipt date — never from the report period.

    Sharding by visibility date (not by the fiscal year the report might be
    read as describing) keeps this module's shard boundary meaningful for an
    append-only, receipt-ordered collection the way `dart_fundamentals`
    shards by the fiscal year its records ARE about — the two collections
    shard on different axes because they answer different questions about a
    filing.
    """
    stamp = str(event.get("availableFrom") or "")
    return int(stamp[:4]) if len(stamp) >= 4 and stamp[:4].isdigit() else None
