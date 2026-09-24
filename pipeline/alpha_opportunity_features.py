"""Outcome-free feature construction; PIT membership and public-date provenance."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import accounting_quality as AQ
from . import dart_derive as DD
from . import finnhub_derive as FD
from . import historical_store as HS
from . import liquidity_attention as LA
from . import regional_alpha_features as SOURCES
from . import replay_calendar as RC

BENCHMARKS = {"US": "SPY", "KR": "069500.KS"}
PRICE = ["relative126", "acceleration21", "vol63"]
ATTENTION = ["logVolumeShock60", "shockPersistence5d", "volumePriceAlignment"]


def visible_filings(records, as_of, region):
    """Strict previous-date availability avoids unknown intraday release timing.

    Never call a whole-history derive then filter its output: a late prior
    filing/restatement could already have contaminated a TTM rollforward.
    """
    visible = []
    for row in records:
        stamp = row.get("availableFrom")
        if not stamp or stamp >= as_of:
            continue
        if region == "KR":
            receipts = row.get("receiptNos") or []
            if {r[:8] for r in receipts} != {stamp.replace("-", "")}:
                continue
        visible.append(row)
    return sorted(visible, key=lambda r: (r["availableFrom"], str(r.get("id", ""))))


def accounting_at(records, as_of, region, share_records=()):
    visible = visible_filings(records, as_of, region)
    derive = DD if region == "KR" else FD
    index = derive.index_filings(visible)
    if not index:
        return {}, {"status": "NO_VISIBLE_FILING"}
    order = {"11013": 1, "11012": 2, "11014": 3, "11011": 4} if region == "KR" else FD.STAGE_ORDER
    year, stage = max(index, key=lambda k: (k[0], order[k[1]]))
    filing = index[(year, stage)]
    if region == "KR":
        # Raw share records must independently prove receipt availability.
        shares = {(int(r["fiscalYear"]), r["reportCode"]): r["sharesOutstanding"]
                  for r in sorted(share_records, key=lambda r: r.get("availableFrom", ""))
                  if r.get("availableFrom") and r["availableFrom"] < as_of
                  and r.get("sharesOutstanding") is not None}
    else:
        shares = {k: FD.share_count(r) for k, r in index.items()}
        shares = {k: v for k, v in shares.items() if v is not None}
    current, _ = derive.carried_shares(shares, year, stage)
    prior, _ = derive.carried_shares(shares, year - 1, stage)
    fn = AQ.derive_kr_fields if region == "KR" else AQ.derive_us_fields
    fields, basis = fn(index, year, stage, current, prior)
    return fields, {"availableFrom": max(r["availableFrom"] for r in visible),
                    "reportPeriod": f"{year}-{stage}", "source": filing.get("source"),
                    "derivation": basis, "visibleFilings": len(visible)}


def price_attention_at(frame, benchmark, date, region="US"):
    """Never interpret forward total-return Close * Volume as actual turnover."""
    values = {name: np.nan for name in PRICE + ATTENTION}
    if frame is None or benchmark is None:
        return values
    f = frame.loc[:date].copy()
    if not f.empty:
        f = f.reindex(RC.sessions(str(f.index[0].date()), date, region))
    b = benchmark.loc[:date]
    if f.empty or str(f.index[-1].date()) != date or "Close" not in f:
        return values
    c = pd.to_numeric(f.Close, errors="coerce")
    if len(c) >= 127 and c.iloc[-127] > 0:
        start = c.index[-127]
        if start in b.index and pd.Timestamp(date) in b.index and b.loc[start, "Close"] > 0:
            values["relative126"] = c.iloc[-1] / c.iloc[-127] - b.loc[date, "Close"] / b.loc[start, "Close"]
    if len(c) >= 43 and min(c.iloc[-1], c.iloc[-22], c.iloc[-43]) > 0:
        values["acceleration21"] = c.iloc[-1] / c.iloc[-22] - c.iloc[-22] / c.iloc[-43]
    returns = c.pct_change(fill_method=None)
    values["vol63"] = returns.tail(63).std(ddof=1) * math.sqrt(252) if returns.tail(63).count() == 63 else np.nan
    if "Volume" in f:
        volume = pd.to_numeric(f.Volume, errors="coerce")
        shock = LA.log_volume_shock(volume, 60)
        values["logVolumeShock60"] = shock.iloc[-1]
        # Foundation comparison turns NaN into False: require ALL five inputs.
        values["shockPersistence5d"] = (LA.shock_persistence(shock, 1.0, 5).iloc[-1]
                                              if shock.tail(5).count() == 5 else np.nan)
        values["volumePriceAlignment"] = LA.volume_price_alignment(shock, LA.price_direction(c)).iloc[-1]
    return values


def ownership_at(events, issuer_id, as_of, sessions, *, coverage_start="2024-09-24", coverage_end="2026-09-23"):
    """Issuer-grained 21-session count/direction; unknown history is not zero."""
    from .dart_ownership_events import receipt_date
    result = {"ownershipCount21": None, "ownershipNetDirection21": None}
    days = pd.DatetimeIndex(sessions)
    pos = days.searchsorted(pd.Timestamp(as_of))
    if not issuer_id or pos < 21 or as_of > coverage_end or str(days[pos - 21].date()) < coverage_start:
        return result
    lower = str(days[pos - 21].date())
    selected = {}
    for row in events:
        if row.get("issuerId") != issuer_id:
            continue
        receipt = receipt_date(row.get("receiptNo") or row.get("id", ""))
        if not receipt or receipt != row.get("availableFrom"):
            raise ValueError("PIT_INVALID_OWNERSHIP_RECEIPT")
        if lower <= receipt < as_of:
            selected[row["receiptNo"]] = row
    directions = [r.get("holdingPctChange") for r in selected.values()]
    result["ownershipCount21"] = len(selected)
    result["ownershipNetDirection21"] = (sum(np.sign(x) for x in directions)
        if all(x is not None for x in directions) else None)
    return result


def load_raw(ledger):
    raw, shares = {}, {}
    for region, pattern in (("US", "finnhub-*.jsonl.gz"), ("KR", "dart-*.jsonl.gz")):
        for path in sorted((Path(ledger) / "fundamentals" / region.lower()).glob(pattern)):
            for row in HS.read_jsonl(path):
                raw.setdefault(row["ticker"], []).append(row)
    for row in HS.read_jsonl(Path(ledger) / "fundamentals/kr/shares.jsonl.gz"):
        shares.setdefault(row["ticker"], []).append(row)
    return raw, shares


def build_matrix(prices, memberships, raw, shares, *, start, through):
    rows = []
    for region in ("US", "KR"):
        for date in SOURCES.weekly_grid(start, through, region):
            snapshot = memberships[region].on(date)
            if snapshot is None:
                raise ValueError("PIT_MEMBERSHIP_MISSING: " + region + "/" + date)
            for ticker in snapshot["members"]:
                fields = price_attention_at(prices.get(ticker), prices.get(BENCHMARKS[region]), date, region)
                accounting, provenance = accounting_at(raw.get(ticker, []), date, region, shares.get(ticker, []))
                # Keep absent-price names in the denominator and output.
                rows.append({"date": date, "region": region, "ticker": ticker,
                             "benchmark": BENCHMARKS[region], "informationTimestamp": pd.Timestamp(date + " 23:59:59", tz="America/New_York" if region == "US" else "Asia/Seoul").isoformat(),
                             "membershipDate": snapshot["date"], "accountingProvenance": provenance,
                             **fields, **accounting})
    frame = pd.DataFrame(rows)
    if frame.duplicated(["date", "region", "ticker"]).any():
        raise ValueError("DUPLICATE_NAME_DATE")
    return frame.sort_values(["region", "date", "ticker"]).reset_index(drop=True)


def coverage(frame, registry):
    result = []
    for (region, year), group in frame.assign(year=frame.date.str[:4]).groupby(["region", "year"]):
        for entry in registry["features"]:
            if entry["region"] != region or entry["status"] != "PRIMARY":
                continue
            name = entry["name"]
            measured = int(pd.to_numeric(group.get(name, pd.Series(index=group.index, dtype=float)), errors="coerce").replace([np.inf, -np.inf], np.nan).notna().sum())
            result.append({"region": region, "year": year, "feature": name,
                           "observed": measured, "universeRows": len(group),
                           "coverage": measured / len(group)})
    return result


def target_at(prices, region, ticker, date, horizon, through):
    """Gross label only, from the sealed replay's forward total-return series.

    Next regional session CLOSE is executable after the feature information
    cutoff. Exact session endpoints, no nearest-price or dead-name substitution.
    This function is called on synthetic fixtures in Phase 1 only.
    """
    sessions = RC.sessions(date, str((pd.Timestamp(date) + pd.Timedelta(days=400)).date()), region)
    sessions = sessions[sessions > pd.Timestamp(date)]
    if len(sessions) <= horizon:
        raise ValueError("CALENDAR_TOO_SHORT")
    entry, exit_ = sessions[0], sessions[horizon]
    out = {"entryDate": str(entry.date()), "outcomeEndDate": str(exit_.date()),
           "forwardRelativeReturn": None, "beatBenchmark": None, "labelStatus": "PENDING"}
    if exit_ > pd.Timestamp(through):
        return out
    out["labelStatus"] = "MISSING_FORWARD_PRICE_OR_DELISTING"
    values = []
    for name in (ticker, BENCHMARKS[region]):
        f = prices.get(name)
        if f is None or entry not in f.index or exit_ not in f.index:
            return out
        a, z = f.loc[entry, "Close"], f.loc[exit_, "Close"]
        if not np.isfinite([a, z]).all() or min(a, z) <= 0:
            return out
        values.append(z / a - 1.0)
    relative = float(values[0] - values[1])
    return {**out, "forwardRelativeReturn": relative, "beatBenchmark": int(relative > 0), "labelStatus": "MATURED"}
