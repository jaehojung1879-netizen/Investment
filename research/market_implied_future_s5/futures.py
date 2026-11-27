"""Bounded standard-month VX contract specimen. No continuous series or rolls."""
import csv
import io
import math
from datetime import date

from .foundation import MAX_BYTES, _utc

FUTURES_URL = "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/"
MONTHLY_CONTRACTS = {
    "2026-09-16": "U (Sep 2026)", "2026-10-21": "V (Oct 2026)",
    "2026-11-18": "X (Nov 2026)", "2026-12-16": "Z (Dec 2026)",
    "2027-01-20": "F (Jan 2027)", "2027-02-17": "G (Feb 2027)",
}
FIELDS = ("Trade Date", "Futures", "Settle", "Total Volume", "Open Interest")


def parse_contract(raw, expiration, retrieved_at):
    if expiration not in MONTHLY_CONTRACTS or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("UNREGISTERED_CONTRACT_OR_SIZE")
    end = date.fromisoformat(expiration)
    received = _utc(retrieved_at).date()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    names = reader.fieldnames or []
    if not set(FIELDS) <= set(names) or len(names) != len(set(names)):
        raise ValueError("FUTURES_SCHEMA")
    results = {}
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("FUTURES_BAD_ROW")
        day = date.fromisoformat(row["Trade Date"])
        if (
            day.isoformat() != row["Trade Date"] or day > min(end, received)
            or day in results or row["Futures"].strip() != MONTHLY_CONTRACTS[expiration]
        ):
            raise ValueError("FUTURES_DATE_OR_CONTRACT")
        settle = float(row["Settle"]) if row["Settle"].strip() not in ("", ".") else None
        volume = int(row["Total Volume"]) if row["Total Volume"].strip() not in ("", ".") else None
        oi = int(row["Open Interest"]) if row["Open Interest"].strip() not in ("", ".") else None
        if settle is not None and (not math.isfinite(settle) or settle < 0):
            raise ValueError("FUTURES_SETTLE")
        if any(value is not None and value < 0 for value in (volume, oi)):
            raise ValueError("FUTURES_COUNTS")
        results[day] = {"settlement_index_points": settle if settle else None,
                        "total_volume_contracts": volume, "open_interest_contracts": oi}
    if not results:
        raise ValueError("FUTURES_EMPTY")
    return results
