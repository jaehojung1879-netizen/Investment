"""WID-only source adapter. The C1-pinned execution module stays byte-identical."""
from __future__ import annotations

from copy import deepcopy
import datetime as dt
from zoneinfo import ZoneInfo

from . import prospective_receipt_core as PRC
from . import us_cash_profitability as CP
from . import winner_inflection_execution as X
from .regional_alpha_features import MembershipSnapshots

def reviewed_public_day(value):
    """Validate the entire source date/time, keeping a conservative US date.

    Naive source dates retain their declared calendar day. For an explicit
    offset, never expose earlier than either the declared or New York day.
    Downstream daily visibility still withholds the WHOLE resulting day.
    """
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return dt.date.fromisoformat(value)
        if len(value) < 16 or value[10] not in ("T", " "):
            return None
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        day = stamp.date()
        return max(day, stamp.astimezone(ZoneInfo("America/New_York")).date()) if stamp.tzinfo else day
    except ValueError:
        return None

def reviewed_filings(records):
    """WID requires BOTH public/acceptance dates; missing evidence never falls back.

    The shared historical helpers retain their own contracts. Reject only this
    filing, preserving the security and every universe denominator.
    """
    accepted, rejected = [], []
    for record in records:
        dates = [reviewed_public_day(record.get(k)) for k in ("availableFrom", "acceptedDate")]
        if any(d is None for d in dates):
            rejected.append({"id": record.get("id"), "ticker": record.get("ticker"),
                             "reason": "BOTH_PUBLICATION_AND_ACCEPTANCE_DATES_REQUIRED"})
        else:
            # Preserve raw source bytes and original timestamps. Only the
            # reader-owned copy gets a later offset-aware visibility date.
            changes = {key: day.isoformat() for key, day in zip(("availableFrom", "acceptedDate"), dates)
                       if day != CP._day(record[key])}
            accepted.append({**record, **changes, "_widOriginalAvailability": {
                key: record[key] for key in ("availableFrom", "acceptedDate")}} if changes else record)
    return accepted, rejected

def normalized_cik(value):
    """A missing/malformed identifier is never a shared issuer identity."""
    import re
    text = str(value) if value is not None and not isinstance(value, bool) else ""
    return text.lstrip("0") if re.fullmatch(r"[0-9]{1,10}", text) and int(text) > 0 else None

def require_spy_action_history(events, start, through):
    """Necessary condition for this fixed SPY cash-reinvestment reconstruction.

    The pinned multi-year SPY index has no preserved distributions. Inverting
    it with an empty event list returns the index unchanged, NOT native prices.
    One event is not proof of complete history, currency or share units; those
    remain independent source-admission requirements.
    """
    if not any(start <= day <= through and PRC.finite(dividend) and dividend > 0
               for day, dividend, _ in events):
        raise ValueError("SPY_NATIVE_RECONSTRUCTION_REQUIRES_DISTRIBUTION_HISTORY")


def prepare_inputs(data):
    """Detached input adaptation before the unchanged shared executor is called.

    Preserve every security/universe row and rejected filing ID. A bad issuer
    identifier becomes an empty identifier, never the common string 'None'.
    No quote, economic outcome or model is calculated here.
    """
    withheld = list(data.get("withheldFilingMetadata", []))
    filings = {}
    for ticker, records in data["filings"].items():
        accepted, rejected = reviewed_filings(records)
        withheld.extend(rejected)
        filings[ticker] = [{**r, "cik": normalized_cik(r.get("cik")) or ""} for r in accepted]
    identities = {ticker: {**row, "cik": normalized_cik(row.get("cik")) or ""}
                  for ticker, row in data["identity"].items()}
    snapshots = deepcopy(data["industries"].snapshots)
    for snapshot in snapshots:
        for row in snapshot.get("rows", {}).values():
            row["cik"] = normalized_cik(row.get("cik")) or ""
    unique = {(r.get("id"), r.get("ticker"), r["reason"]): r for r in withheld}
    return {**data, "filings": filings, "identity": identities,
            "industries": MembershipSnapshots(snapshots), "withheldFilingMetadata": list(unique.values())}


def observations(data, spec):
    return X.observations(prepare_inputs(data), spec)


def execute(data, spec, *, checkpoint=None):
    """Metadata wrapper; caller still needs the existing durable owner permit."""
    prepared = prepare_inputs(data)

    def record(layer, key, value):
        if layer == "evaluation":
            value = {**value, "withheldFilingMetadata": prepared["withheldFilingMetadata"]}
        if checkpoint:
            checkpoint(layer, key, value)

    result = X.execute(prepared, spec, checkpoint=record)
    result["evaluation"]["withheldFilingMetadata"] = prepared["withheldFilingMetadata"]
    return result
