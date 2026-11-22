"""BIL total return from the preserved raw close and ISSUER distributions (Phase 2 input build).

Basis, registered in `protocol.json` (`markets.US.cashAsset`): raw close plus issuer distributions (dividend + capital
gains) reinvested at the ex-date close. Vendor distribution events are never used.

The Yahoo chart's `close` is split-ADJUSTED (restated per current share) but not dividend-adjusted. BIL's 2017-11-30
1:2 consolidation therefore appears as no jump in `close`, and an issuer amount paid per OLD share before that date
must be restated per current share (x denominator / numerator = x2) to sit on the same basis as the close.

Gates (any failure raises; a gate is never relaxed to make a series pass):
* every required session has a positive close,
* every issuer ex-date with a non-zero amount inside the span is a session in the close series,
* no daily total return beyond `MAX_DAILY_ABS_RETURN` (a 1-3 month T-bill fund; an unadjusted split would read +-50%).
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
from pathlib import Path

MAX_DAILY_ABS_RETURN = 0.01


class BilInputError(ValueError):
    pass


def load_chart(path: Path) -> tuple[dict[str, float], list[dict]]:
    chart = json.loads(gzip.decompress(path.read_bytes()))["chart"]["result"][0]
    closes = chart["indicators"]["quote"][0]["close"]
    out = {}
    for ts, close in zip(chart["timestamp"], closes):
        if close is None:
            continue
        out[dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()] = float(close)
    splits = [{"date": dt.datetime.fromtimestamp(v["date"], dt.timezone.utc).date().isoformat(),
               "numerator": float(v["numerator"]), "denominator": float(v["denominator"])}
              for v in chart.get("events", {}).get("splits", {}).values()]
    return out, splits


def load_issuer(path: Path) -> list[dict]:
    events = []
    for row in csv.DictReader(path.open()):
        amount = float(row["dividend"]) + float(row["shortTermCapitalGain"]) + float(row["longTermCapitalGain"])
        events.append({"exDate": row["exDate"], "amount": amount})
    return events


def restate_per_current_share(events: list[dict], splits: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in events:
        amount = e["amount"]
        for s in splits:
            if e["exDate"] < s["date"]:
                amount = amount * s["denominator"] / s["numerator"]
        out[e["exDate"]] = out.get(e["exDate"], 0.0) + amount
    return out


def total_return_index(closes: dict[str, float], distributions: dict[str, float], sessions: list[str]) -> dict[str, float]:
    """TR index over `sessions` (ascending), 1.0 on the first: r_t = (close_t + D_t) / close_{t-1} - 1."""
    missing = [s for s in sessions if not closes.get(s, 0) > 0]
    if missing:
        raise BilInputError(f"BIL_CLOSE_MISSING: {len(missing)} sessions, first {missing[:3]}")
    span = set(sessions[1:])
    stray = [d for d, a in distributions.items() if a != 0 and sessions[0] < d <= sessions[-1] and d not in span]
    if stray:
        raise BilInputError(f"EX_DATE_NOT_A_SESSION: {stray[:3]}")
    index = {sessions[0]: 1.0}
    level = 1.0
    for prev, cur in zip(sessions, sessions[1:]):
        r = (closes[cur] + distributions.get(cur, 0.0)) / closes[prev] - 1.0
        if abs(r) > MAX_DAILY_ABS_RETURN:
            raise BilInputError(f"IMPLAUSIBLE_DAILY_RETURN: {cur} {r:.4%}")
        level *= 1.0 + r
        index[cur] = level
    return index


def build(chart_path: Path, issuer_path: Path, sessions: list[str]) -> dict:
    closes, splits = load_chart(chart_path)
    distributions = restate_per_current_share(load_issuer(issuer_path), splits)
    index = total_return_index(closes, distributions, sessions)
    paid = {d: a for d, a in distributions.items() if a != 0 and sessions[0] < d <= sessions[-1]}
    return {"index": index, "splits": splits, "distributionsInSpan": len(paid),
            "first": sessions[0], "last": sessions[-1], "sessions": len(sessions)}
