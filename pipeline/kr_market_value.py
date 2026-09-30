"""Date-specific official KRX market values. Never reads a forward target.

Market observations at signal close are permitted; accounting must be strictly
older. No substitution of a monthly snapshot or a forward total-return index
for the price/market-cap denominator. Cache entries are first-write immutable.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import krx_universe as KU
from . import replay_calendar as RC
from .alpha_opportunity_spec import digest

SOURCE = "KRX:sto/stk_bydd_trd"
FIELDS = ("close", "marketCap", "listedShares", "volume", "tradingValue")


def parse_market_values(payload, requested):
    issues, error = KU.parse_issues(payload)
    if error:
        raise ValueError("KRX_RESPONSE_REFUSED: " + error)
    if not issues:
        return []
    date = KU.served_date(payload, requested)
    if date != requested:
        raise ValueError("KRX_DATE_IDENTITY_MISMATCH")
    key = next(k for k in KU.ROWS_KEYS if k in payload)
    raw = {KU._first(r, KU.CODE_KEYS): r for r in payload[key]}
    records = []
    for issue in issues:
        row = raw[issue["code"]]
        records.append({"date": date, "securityId": KU.to_pipeline_ticker(issue["code"]),
                        "source": SOURCE, "close": KU.parse_number(KU._first(row, ("TDD_CLSPRC", "CLSPRC"))),
                        "marketCap": issue["marketCap"], "listedShares": issue["listedShares"],
                        "volume": KU.parse_number(KU._first(row, ("ACC_TRDVOL", "TRDVOL"))),
                        "tradingValue": KU.parse_number(KU._first(row, ("ACC_TRDVAL", "TRDVAL")))})
    return sorted(records, key=lambda r: r["securityId"])


def validate_record(row, *, date=None, ticker=None):
    if row.get("source") != SOURCE or not str(row.get("securityId", "")).endswith(".KS"):
        raise ValueError("KRX_SOURCE_OR_SECURITY_IDENTITY")
    if date is not None and row.get("date") != date:
        raise ValueError("KRX_DATE_IDENTITY_MISMATCH")
    if ticker is not None and row.get("securityId") != ticker:
        raise ValueError("KRX_SECURITY_IDENTITY_MISMATCH")
    for name in FIELDS:
        value = row.get(name)
        if value is None or not math.isfinite(float(value)) or value < 0:
            raise ValueError("KRX_INVALID_" + name)
    if min(row["close"], row["marketCap"], row["listedShares"]) <= 0:
        raise ValueError("KRX_NONPOSITIVE_MARKET_VALUE")
    # Direct KRX capitalization must reconcile with its OWN quoted units.
    if abs(row["close"] * row["listedShares"] / row["marketCap"] - 1) > .01:
        raise ValueError("KRX_CAP_PRICE_SHARES_INCOHERENT")
    return True


def day_document(date, records):
    ordered = sorted(records, key=lambda r: r["securityId"])
    if len({r["securityId"] for r in ordered}) != len(ordered):
        raise ValueError("DUPLICATE_KRX_SECURITY_DATE")
    for row in ordered:
        validate_record(row, date=date)
    return {"date": date, "source": SOURCE, "records": ordered, "sha256": digest(ordered)}


def write_day(directory, date, records):
    """Exclusive first write; a different response never overwrites an old date."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (date + ".json")
    document = day_document(date, records)
    if path.exists():
        if json.loads(path.read_text()) != document:
            raise ValueError("KRX_CACHE_REWRITE_REFUSED")
        return path
    with path.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return path


class MarketValueStore:
    def __init__(self, records=()):
        self.rows = {}
        for row in records:
            validate_record(row)
            key = (row["date"], row["securityId"])
            if key in self.rows:
                raise ValueError("DUPLICATE_KRX_SECURITY_DATE")
            self.rows[key] = dict(row)

    @classmethod
    def load(cls, directory):
        records = []
        for path in sorted(Path(directory).glob("????-??-??.json")):
            document = json.loads(path.read_text())
            expected = day_document(path.stem, document["records"])
            if document != expected:
                raise ValueError("KRX_CACHE_HASH_OR_IDENTITY_CHANGED")
            records.extend(document["records"])
        return cls(records)

    def at(self, ticker, signal_date):
        row = self.rows.get((signal_date, ticker))
        return dict(row) if row else None

    def trailing(self, ticker, date, lookback=60):
        days = RC.sessions("2013-01-01", date, "KR")[-lookback:]
        return [self.rows.get((str(d.date()), ticker)) for d in days]

    def identity(self):
        return digest([self.rows[k] for k in sorted(self.rows)])
