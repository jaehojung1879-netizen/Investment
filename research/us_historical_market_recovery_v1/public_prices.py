"""Load the verified public price windows from private, reproducible packets."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json

import pandas as pd

from pipeline import price_adjustment as PA
from research.us_historical_market_recovery_v1.engine import BASIS_TOLERANCE, Unresolved, frame_series

PACKETS = {
    "public-para-price-packet.json": (
        "e26f87d0c7a7d6a7043037ca36ef7543c5405abb80de91ef5d1d4605699baa7f",
        {"PARA": ("2022-02-17", "2025-08-06", "PSKY", "2025-08-06", 869),
         "PSKY": ("2025-08-07", "2026-10-05", "PSKY", "2026-09-14", 277)},
    ),
    "public-wbd-kvue-price-packet.json": (
        "9c96ba38062be7a8522c504e297215b3d40dc457d4b7c2b663886009957b32b7",
        {"WBD": ("2025-04-15", "2026-10-05", "WBD", "2026-09-14", 253),
         "KVUE": ("2025-05-13", "2026-10-30", "KVUE", "2026-09-14", 253),
         "KMB": ("2025-05-28", "2026-11-13", "KMB", "2026-09-14", 253)},
    ),
}
# The original Class B public float receives one share if no election is made.
# Actual cash electors instead received cash on their prorated allotment.
PARA_TERMINAL = {
    "date": "2025-08-07", "last_trading_date": "2025-08-06", "shares": 1.0,
    "successor": "PSKY", "verified": True, "effective_before_open": True,
    "citation": "https://www.sec.gov/Archives/edgar/data/2041610/000119312525175046/d841914d8k12b.htm",
    "election_basis": "CONTRACTUAL_NO_ELECTION_STOCK_DEFAULT",
}


def read_packet(path, expected_sha):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha:
        raise Unresolved("PUBLIC_PRICE_PACKET_CHECKSUM_MISMATCH:" + path.name)
    return json.loads(data)


def load_public_prices(private, baseline, calendar):
    """Return validated whole security windows; an absent packet is optional."""
    prices, receipts = {}, {}
    for name, (sha, coverage) in PACKETS.items():
        path = private / name
        if not path.exists():
            continue
        packet = read_packet(path, sha)
        if packet.keys() != coverage.keys():
            raise Unresolved("PUBLIC_PRICE_PACKET_WRONG_SECURITY_SET:" + name)
        for ticker, (first, last, reference, overlap_end, minimum) in coverage.items():
            frame = pd.DataFrame(packet[ticker]).set_index("date")
            frame.index = pd.to_datetime(frame.index)
            series, _ = frame_series(ticker, frame, source="PUBLIC_DATED_SECURITY_QUOTES", receipt=sha,
                                     basis="SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED")
            if series.good_days != {d for d in calendar if first <= d <= last}:
                raise Unresolved("PUBLIC_PRICE_CALENDAR_GAP:" + ticker)
            compare = series
            if ticker == "KVUE":
                # Match the original vendor's coarser adjustment only for the
                # comparison. The actual output uses official USD 0.2075.
                rounded = frame.copy()
                rounded[PA.DIVIDEND] = rounded[PA.DIVIDEND].map(
                    lambda n: float(Decimal(str(n)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)))
                compare, _ = frame_series(ticker, rounded, source=series.source, receipt=sha,
                                          basis="SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED")
            common = [d for d in sorted(series.good_days & baseline[reference].keys()) if d <= overlap_end][-minimum:]
            ratios = pd.Series([compare.tr.at[d] / baseline[reference][d]["Close"] for d in common], dtype=float)
            deviation = float((ratios / ratios.median() - 1).abs().max()) if len(ratios) else float("inf")
            if len(common) != minimum or not deviation <= BASIS_TOLERANCE:
                raise Unresolved("PUBLIC_PRICE_REFERENCE_BASIS_UNRECONCILED:" + ticker)
            series.identity_verified = series.actions_verified = True
            prices[ticker] = series
            receipts[ticker] = {
                "packet": name, "packet_sha256": sha, "first": first, "last": last,
                "reference_ticker": reference, "comparison_sessions": len(common),
                "comparison_maximum_deviation": deviation,
                "comparison_dividend_precision_only": ticker == "KVUE",
            }
    return prices, receipts
