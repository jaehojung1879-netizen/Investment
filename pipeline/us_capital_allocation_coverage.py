"""Weekly PIT coverage of the US shareholder-distribution features over S&P 500 members. Outcome-blind.

PR #220 measured how often the features are derivable on a company's own FILING EVENTS. That is not an investable
cross-section: a weekly observation date needs (a) a point-in-time index member, (b) a resolved security identity,
(c) a tradable price history, (d) a visible and fresh filing, and only then (e) a feature state. This module walks that
funnel for every PIT member on every weekly signal date and keeps each failure reason apart, so "missing", "reported
zero", "ambiguous" and "insufficient history" are never merged and no gap becomes a zero.

It imports no return, label, outcome or model module and reads no price beyond whether a session exists and is positive.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from . import us_capital_allocation_policy as POL
from . import us_shareholder_distribution as U

# Funnel stages, in the order a member-date is tested. A member-date is counted at the FIRST stage it fails.
IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
NO_PRICE_PANEL = "NO_PRICE_PANEL"
PRICE_HISTORY_INSUFFICIENT = "PRICE_HISTORY_INSUFFICIENT"
PRICE_STALE = "PRICE_STALE"
NO_FUNDAMENTAL_RECORD = "NO_FUNDAMENTAL_RECORD"
NO_VISIBLE_FILING = "NO_VISIBLE_FILING"
REPORT_STALE = "REPORT_STALE_OVER_180_DAYS"
FEATURES_NOT_MEASURED = "FEATURES_NOT_MEASURED"
JOINT_MEASURED = "JOINT_MEASURED"
FUNNEL = (IDENTITY_AMBIGUOUS, NO_PRICE_PANEL, PRICE_HISTORY_INSUFFICIENT, PRICE_STALE, NO_FUNDAMENTAL_RECORD,
          NO_VISIBLE_FILING, REPORT_STALE, FEATURES_NOT_MEASURED, JOINT_MEASURED)

# Inherited, not tuned: the existing feature matrix requires 272 prior sessions and a price at most 10 calendar days
# old; PR #220 flags a report period older than 180 days as stale.
MIN_PRIOR_SESSIONS = 272
MAX_PRICE_AGE_DAYS = 10
MAX_REPORT_AGE_DAYS = 180

# The four measurements a distribution-increase candidate cannot be formed without.
REQUIRED = ("totalCashDistributionTTM", "totalCashDistributionChangeYoY", "operatingCashFlowTTM", "distributionToOCF")
FAMILIES = {
    "dividends": ("cashDividendsPaidTTM", "cashDividendsPaidTTMChangeYoY"),
    "repurchases": ("commonStockRepurchasesTTM", "repurchasesTTMChangeYoY"),
    "totalDistribution": ("totalCashDistributionTTM", "totalCashDistributionChangeYoY"),
    "operatingCashFlow": ("operatingCashFlowTTM",),
    "support": ("distributionToOCF", "distributionCoverageByOCF"),
    "capexAndCash": ("capitalExpendituresTTM", "cashAndCashEquivalents"),
    "dilution": ("sharesOutstandingChangeYoY", "shareCountReductionIndicator"),
}
STATES = tuple(s.value for s in U.State)

CANONICAL_SECTORS = ("Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy", "Financials",
                     "Health Care", "Industrials", "Information Technology", "Materials", "Real Estate", "Utilities")
# Pre-2018 GICS name for what became Communication Services. A rename, not a mapping of different companies.
SECTOR_ALIASES = {"Telecommunication Services": "Communication Services", "Telecommunications Services": "Communication Services"}
UNCLASSIFIED = "UNCLASSIFIED"


def canonical_sector(label):
    """The label if it is one of the eleven sector names (or a pure rename of one); otherwise None. Never a guess."""
    if label in CANONICAL_SECTORS:
        return label
    return SECTOR_ALIASES.get(label)


class SectorBook:
    """Sector as the SOURCE published it at the membership snapshot used for the signal date.

    If that snapshot's own label is not a sector name (the upstream column drifted to sub-industries in a few
    commits), the latest EARLIER snapshot with a sector name for the ticker is used and marked as carried. A later
    snapshot is never read: that would be look-ahead.
    """

    def __init__(self, snapshots):
        self._order = sorted(snapshots, key=lambda s: (s["date"], s["sourceCommit"]))
        self._index = {(s["date"], s["sourceCommit"]): i for i, s in enumerate(self._order)}

    def lookup(self, snapshot, ticker):
        pos = self._index.get((snapshot["date"], snapshot["sourceCommit"]))
        if pos is None:
            return UNCLASSIFIED, "SNAPSHOT_HAS_NO_SECTOR_EVIDENCE"
        row = self._order[pos]["rows"].get(ticker)
        label = canonical_sector(row["sector"]) if row else None
        if label:
            return label, "SNAPSHOT"
        for earlier in range(pos - 1, -1, -1):
            row = self._order[earlier]["rows"].get(ticker)
            label = canonical_sector(row["sector"]) if row else None
            if label:
                return label, "CARRIED_FROM_EARLIER_SNAPSHOT"
        return UNCLASSIFIED, "NO_SECTOR_LABEL_IN_ANY_EARLIER_SNAPSHOT"

    def cik(self, snapshot, ticker):
        pos = self._index.get((snapshot["date"], snapshot["sourceCommit"]))
        if pos is None:
            return None
        row = self._order[pos]["rows"].get(ticker)
        return row.get("cik") if row else None


class PricePresence:
    """Per ticker: sorted session dates with a positive finite close. Nothing else about a price is retained."""

    def __init__(self):
        self._dates: dict[str, list[str]] = {}

    @classmethod
    def from_rows(cls, rows):
        book = cls()
        bucket = defaultdict(list)
        for row in rows:
            close = row.get("Close")
            if isinstance(close, (int, float)) and np.isfinite(close) and close > 0:
                bucket[row["ticker"]].append(row["date"])
        for ticker, dates in bucket.items():
            book._dates[ticker] = sorted(set(dates))
        return book

    def status(self, ticker, date):
        dates = self._dates.get(ticker)
        if not dates:
            return NO_PRICE_PANEL, None
        pos = bisect_right(dates, date) - 1
        if pos < MIN_PRIOR_SESSIONS:
            return PRICE_HISTORY_INSUFFICIENT, pos + 1
        age = (np.datetime64(date) - np.datetime64(dates[pos])).astype("timedelta64[D]").astype(int)
        if age > MAX_PRICE_AGE_DAYS:
            return PRICE_STALE, int(age)
        return "OK", pos + 1

    def tickers(self):
        return set(self._dates)


def report_age_days(snapshot_inputs_end, as_of):
    return (np.datetime64(as_of) - np.datetime64(snapshot_inputs_end)).astype("timedelta64[D]").astype(int)


def latest_period_end(snapshot):
    """Period end of the report the snapshot is anchored on, from the inputs of its own features."""
    ends = [i.period_end for f in snapshot.features.values() for i in f.inputs if i.period_end]
    return max(ends) if ends else None


def joint_status(snapshot):
    """(measured?, reason). The reason is the FIRST required feature that is not a usable measurement."""
    features = snapshot.features
    for name in REQUIRED:
        feature = features[name]
        if feature.value is None:
            return False, "%s:%s" % (name, feature.state.value)
    if features["operatingCashFlowTTM"].value <= 0:
        return False, "operatingCashFlowTTM:NONPOSITIVE_OCF"
    return True, None


class Tally:
    """Counters keyed by (group, status). Small, mergeable and order-independent."""

    def __init__(self):
        self.by_year = defaultdict(Counter)
        self.by_sector = defaultdict(Counter)
        self.by_company = defaultdict(Counter)
        self.states = defaultdict(lambda: defaultdict(Counter))       # family -> feature -> state
        self.states_by_year = defaultdict(lambda: defaultdict(Counter))
        self.states_by_sector = defaultdict(lambda: defaultdict(Counter))
        self.reasons = Counter()
        self.cross = Counter()
        self.weekly = []

    def add_member_date(self, year, sector, ticker, status):
        self.by_year[year][status] += 1
        self.by_sector[sector][status] += 1
        self.by_company[ticker][status] += 1

    def add_features(self, year, sector, snapshot):
        for family, names in FAMILIES.items():
            for name in names:
                state = snapshot.features[name].state.value
                self.states[family][name][state] += 1
                self.states_by_year[year][name][state] += 1
                self.states_by_sector[sector][name][state] += 1


def funnel_share(counter):
    total = sum(counter.values())
    return {stage: round(100.0 * counter.get(stage, 0) / total, 4) for stage in FUNNEL} if total else {}


# --------------------------------------------------------------------------- #
# One member on one signal date: the single classification the audit AND the weekly receipt both use
# --------------------------------------------------------------------------- #
@dataclass
class WeekContext:
    """Everything knowable about the universe, loaded once. Holds no return and no price level."""
    engines: dict                      # ticker -> U.FeatureEngine
    prices: "PricePresence"
    sectors: "SectorBook"
    ciks: dict                         # ticker -> [(visible_day, cik)]
    category: dict                     # v3 identity category by symbol
    malformed: dict                    # UPPER raw key -> resolved symbol
    renames: dict                      # verified rename: symbol -> price/fundamental ticker
    ambiguous: set                     # symbols whose panel or fundamentals belong to another issuer
    first_visible: dict = field(default_factory=dict)

    def __post_init__(self):
        self.first_visible = {t: min(f.visible_day for f in e._filings) for t, e in self.engines.items() if e._filings}


@dataclass
class MemberRow:
    symbol: str
    ticker: str
    sector: str
    sector_basis: str
    status: str
    reason: str = ""
    snapshot: object = None            # FeatureSnapshot when one was derived
    report_age_days: int | None = None
    report_end: str | None = None


def classify_member(ctx: WeekContext, membership_snapshot: dict, date: str, raw_symbol: str) -> MemberRow:
    """The first funnel stage this member-date fails, or JOINT_MEASURED. Deterministic and free of any return."""
    day = U.parse_day(date)
    symbol = ctx.malformed.get(raw_symbol.upper(), raw_symbol)
    sector, basis = ctx.sectors.lookup(membership_snapshot, raw_symbol)
    ticker = ctx.renames.get(symbol, symbol)
    row = MemberRow(symbol, ticker, sector, basis, "")
    if symbol in ctx.ambiguous:
        row.status, row.reason = IDENTITY_AMBIGUOUS, ctx.category.get(symbol, "PANEL_POSTDATES_MEMBERSHIP")
        return row
    member_cik = ctx.sectors.cik(membership_snapshot, raw_symbol)
    seen = {c for v, c in ctx.ciks.get(ticker, ()) if v < day}
    # A ticker can carry several CIKs (combined filings list subsidiaries; a holding company can replace its predecessor).
    # It is ambiguous only when the snapshot's CIK is none of those the visible filings carry.
    if member_cik and seen and member_cik not in seen:
        row.status, row.reason = IDENTITY_AMBIGUOUS, "CIK_MISMATCH"
        return row
    price_state, _ = ctx.prices.status(ticker, date)
    if price_state != "OK":
        row.status = price_state
    elif ticker not in ctx.engines:
        row.status = NO_FUNDAMENTAL_RECORD
    elif ctx.first_visible[ticker] >= day:
        row.status = NO_VISIBLE_FILING
    else:
        snapshot = ctx.engines[ticker].as_of(date)
        end = latest_period_end(snapshot)
        row.snapshot, row.report_end = snapshot, end
        row.report_age_days = report_age_days(end, date) if end else None
        measured, why = joint_status(snapshot)
        if row.report_age_days is None or row.report_age_days > MAX_REPORT_AGE_DAYS:
            row.status, row.reason = REPORT_STALE, "age=%s" % row.report_age_days
        elif not measured:
            row.status, row.reason = FEATURES_NOT_MEASURED, why
        else:
            row.status = JOINT_MEASURED
    return row


def member_evaluation(row: MemberRow) -> dict | None:
    """The registered rule's verdict on one member-date. Identity-ambiguous members are not candidates at all."""
    if row.status == IDENTITY_AMBIGUOUS:
        return None
    price_ok = row.status not in (NO_PRICE_PANEL, PRICE_HISTORY_INSUFFICIENT, PRICE_STALE)
    if row.snapshot is not None and price_ok:
        return POL.evaluate(POL.candidate_from_snapshot(row.snapshot, sector=row.sector, price_ok=True,
                                                         report_age_days=row.report_age_days, ticker=row.symbol))
    return POL.evaluate({"ticker": row.symbol, "sector": row.sector, "priceOk": price_ok, "reportAgeDays": None, "features": {}})
