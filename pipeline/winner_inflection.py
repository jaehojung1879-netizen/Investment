"""Input-only state changes for independent Winner & Inflection exploration.

Reuses the workbench's public-date prefix and the sealed DART/Finnhub arithmetic.
No labels, ranking, file writes, collection or historical execution live here.
"""
from __future__ import annotations

from bisect import bisect_left
from copy import deepcopy
import datetime as dt
import math

from . import dart_derive as DD
from . import dart_fundamentals as DF
from . import experiment_workbench as W
from . import finnhub_derive as FD
from . import kr_value_quality_catalyst as KQ
from . import us_cash_profitability as CP

VERSION = "WINNER_INFLECTION_EXPLORATORY_V1"
STAGES = {"KR": ("11013", "11012", "11014", "11011"), "US": ("Q1", "Q2", "Q3", "FY")}
ACCOUNTS = {"KR": {"revenue": "매출액", "operating": "영업이익", "ocf": "영업활동현금흐름"},
            "US": {"revenue": "revenue", "operating": "operatingIncome", "ocf": "operatingCashFlow"}}
PATTERNS = {
    "A": ("revenueGrowthAcceleration", "operatingGrowthAcceleration"),
    "B": ("operatingMarginChange", "ocfMarginChange", "operatingPositiveCross", "ocfPositiveCross"),
    "C": ("industryRelativeStrengthChange63",),
    "D": ("fundamentalEventAgeSessions", "postEventRelativePath"),
    "E": ("laggedLeaderRelativePath", "followerRelativePath"),
    "F": ("orderedGrowthValueImprovement",),
    "G": ("pastDownside126", "ocfMarginChange"),
}
FLOW_FIELDS = PATTERNS["A"] + PATTERNS["B"]


def previous_period(key, market):
    year, stage = key
    stages = STAGES[market]
    pos = stages.index(stage)
    return (year, stages[pos - 1]) if pos else (year - 1, stages[-1])


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def _state(records, market, as_of):
    visible = W.filing_prefix(records, market, as_of)
    index = (DD if market == "KR" else FD).index_filings(list(visible))
    key = (max(index, key=lambda k: (k[0], STAGES[market].index(k[1]))) if index else None) if market == "KR" else CP.current_key(index)
    out = {"period": None, "periodEnd": None, "availableFrom": None, "sourceIds": [],
           "fields": dict.fromkeys(FLOW_FIELDS), "reasons": dict.fromkeys(FLOW_FIELDS, "NO_VISIBLE_FILING")}
    if key is None:
        return out
    prev = previous_period(key, market)
    used = set()
    failures = set()

    def ttm(k, account):
        year, stage = k
        annual = STAGES[market][-1]
        dependencies = [k] if stage == annual else [k, (year - 1, annual), (year - 1, stage)]
        used.update(d for d in dependencies if d in index)
        if any(d not in index for d in dependencies):
            failures.add("INCOMPLETE_CHAIN")
            return None
        for d in dependencies:
            end = DF.period_end(*d) if market == "KR" else index[d].get("periodEnd")
            public = index[d]["availableFrom"] if market == "KR" else CP.visible_day(index[d]).isoformat()
            if not end or end > public:
                failures.add("REPORT_PERIOD_AFTER_PUBLICATION")
                return None
        if market == "KR" and not KQ._compatible(index, dependencies):
            failures.add("STATEMENT_BASIS_UNRESOLVED")
            return None
        if market == "US" and account == "operating":
            # FD's final fallback is pretax income, useful in its own contract
            # but economically different from operating profit in this study.
            if any(FD.amount(index[d], "ic", ("OperatingIncomeLoss",)) is None for d in dependencies):
                failures.add("OPERATING_SUBTOTAL_NOT_STATED")
                return None
        value = (DD if market == "KR" else FD).trailing_twelve_months(index, year, stage, ACCOUNTS[market][account])[0]
        if not _finite(value):
            failures.add("INCOMPLETE_CHAIN_OR_UNIT")
            return None
        return float(value)

    current = {a: ttm(key, a) for a in ACCOUNTS[market]}
    earlier = {a: ttm(prev, a) for a in ACCOUNTS[market]}
    # No changes across CFS/OFS, even when each TTM is separately compatible.
    basis_mixed = market == "KR" and not KQ._compatible(index, sorted(used))

    def put(name, value, reason):
        out["fields"][name] = value
        out["reasons"][name] = "AVAILABLE" if value is not None else reason

    for account in ("revenue", "operating"):
        prior = ttm((key[0] - 1, key[1]), account)
        prior_prev = ttm((prev[0] - 1, prev[1]), account)
        values = (current[account], earlier[account], prior, prior_prev)
        ready = all(v is not None for v in values)
        value = current[account] / prior - earlier[account] / prior_prev if ready and min(prior, prior_prev) > 0 else None
        put(account + "GrowthAcceleration", value,
            "NON_POSITIVE_GROWTH_BASE" if ready else "+".join(sorted(failures)))
    for account in ("operating", "ocf"):
        now, before = current[account], earlier[account]
        revenue, prior_revenue = current["revenue"], earlier["revenue"]
        complete = all(v is not None for v in (now, before, revenue, prior_revenue))
        margin = now / revenue - before / prior_revenue if complete and min(revenue, prior_revenue) > 0 else None
        put(account + "MarginChange", margin,
            "NON_POSITIVE_REVENUE" if complete else "+".join(sorted(failures)))
        cross = float(before <= 0 < now) if now is not None and before is not None else None
        put(account + "PositiveCross", cross, "+".join(sorted(failures)))
    # Growth reads additional prior-year dependencies: check the whole union.
    basis_mixed |= market == "KR" and not KQ._compatible(index, sorted(used))
    if basis_mixed:
        out["fields"] = dict.fromkeys(FLOW_FIELDS)
        out["reasons"] = dict.fromkeys(FLOW_FIELDS, "STATEMENT_BASIS_UNRESOLVED")
    current_record = index[key]
    out.update(period=list(key), periodEnd=(DF.period_end(*key) if market == "KR" else current_record["periodEnd"]),
               availableFrom=max((r["availableFrom"] if market == "KR" else CP.visible_day(r).isoformat()) for k, r in index.items() if k in used),
               sourceIds=sorted(str(index[k]["id"]) for k in used))
    return out


class FilingStates:
    """Reader-owned visible-prefix cache. Freshness is rechecked on EVERY date."""
    def __init__(self, records, market):
        if market not in STAGES:
            raise ValueError("UNKNOWN_MARKET")
        self.market = market
        pairs = sorted(((CP.visible_day(r).isoformat() if market == "US" else r.get("availableFrom"), r)
                        for r in records if (CP.visible_day(r) if market == "US" else r.get("availableFrom"))), key=lambda p: p[0])
        self.days, self.records = [p[0] for p in pairs], [p[1] for p in pairs]
        self.cache = {}

    def at(self, date):
        dt.date.fromisoformat(date)
        n = bisect_left(self.days, date)
        if n not in self.cache:
            # Invalid KR receipt dates are excluded by the existing visibility
            # adapter; they remain in the separate raw-source denominator.
            self.cache[n] = _state(self.records[:n], self.market, date)
        out = deepcopy(self.cache[n])
        if out["periodEnd"] and (dt.date.fromisoformat(date) - dt.date.fromisoformat(out["periodEnd"])).days > 180:
            out["fields"] = dict.fromkeys(FLOW_FIELDS)
            out["reasons"] = dict.fromkeys(FLOW_FIELDS, "REPORT_STALE_OVER_180_DAYS")
        return out


def industry_relative_change(paths, industries, *, minimum_peers=5):
    """Two consecutive 63-session paths, leave-self-out SAME-date peers.

    Paths are (earlier gross return, recent gross return), both entirely prior
    to/at the signal. No current survivors, missing peers or zero replacements.
    Caller supplies a PIT universe and validated exact-session price windows.
    """
    import numpy as np
    out = {}
    grouped = {}
    for security, path in paths.items():
        grouped.setdefault(industries.get(security), []).append((security, path))
    for security, group in industries.items():
        own = paths.get(security)
        peers = [p for s, p in grouped.get(group, ()) if s != security] if group is not None else []
        if own is None or group is None or len(peers) < minimum_peers:
            out[security] = (None, "NO_EXACT_PRICE_WINDOW" if own is None else
                             "INDUSTRY_UNRESOLVED" if group is None else "INSUFFICIENT_SAME_DATE_PEERS")
        else:
            old, recent = np.median(peers, axis=0)
            out[security] = (float((own[1] - recent) - (own[0] - old)), "AVAILABLE")
    return out
