"""US dividend-change events from a field already sitting in the PIT store.

WHY THIS NEEDS NO NEW COLLECTION. `finnhub_fundamentals.UNIT_ANCHORS[PER_SHARE]`
already lists `CommonStockDividendsPerShareDeclared` as a recognized
per-share concept (`finnhub_fundamentals.py:658`), so it is already present
in every US filing this repository has already backfilled — the raw field
`alpha-information-inventory-v1`'s data map (§11) found sitting unused.

THE REPORTING CONVENTION, MEASURED, NOT ASSUMED. Reading the real sealed
store rather than guessing: AAPL FY2013's four quarterly filings state this
concept as `2, 5, 8, 11` at 90/181/272/363 days into the fiscal year —
monotonically increasing WITHIN the year, the same cumulative-from-fiscal-
year-start pattern `finnhub_derive.py`'s own docstring already measured for
net income, revenue, operating income and operating cash flow (2.03/3.09
against the first quarter). So a quarter's OWN declared dividend is not
this field's raw value; it needs the identical TTM rollforward
`finnhub_derive.trailing_twelve_months` already implements for those other
flow accounts, applied here to a `PER_SHARE`-classified concept instead of
a `CURRENCY`-classified one. This module reuses `finnhub_derive`'s
`index_filings`, `carried_shares`-style stage ordering and
`BASIS_ANNUAL`/`BASIS_ROLLFORWARD`/`BASIS_INCOMPLETE` vocabulary rather than
redefining them, and adds only the one new reader (`_per_share_amount`) that
`finnhub_derive.amount` does not need because none of ITS accounts are
per-share.

A MEASURED DATA-QUALITY CAVEAT, PUBLISHED RATHER THAN HIDDEN. Every value
observed for this concept in a sample pull from the real store was a bare
integer (`2`, `5`, `8`, `11`, never a decimal) — AAPL's actual pre-split
quarterly dividend in 2013 was on the order of $2.65-$3.05, so this looks
like sub-dollar precision was lost somewhere upstream of this store (most
likely at ingestion). `dividendGrowthPct`'s classification is therefore
coarser than a cents-level dividend change would deserve, and this module's
own event thresholds are set wide enough (see `CLASSIFY_THRESHOLD_PCT`) to
not manufacture a false INCREASED/DECREASED read out of integer rounding
alone — but a study using this signal should know the ceiling on its own
precision, not just be told None where a filing states nothing.

NO FORWARD-RETURN RELATIONSHIP IS COMPUTED OR CONSUMED HERE.
"""
from __future__ import annotations

from . import finnhub_derive as US
from . import finnhub_fundamentals as FF

CONTRACT = "DIVIDEND_EVENTS_V1"
CONCEPT = "CommonStockDividendsPerShareDeclared"

BASIS_ANNUAL = US.BASIS_ANNUAL
BASIS_ROLLFORWARD = US.BASIS_ROLLFORWARD
BASIS_INCOMPLETE = US.BASIS_INCOMPLETE

DIVIDEND_INITIATED = "DIVIDEND_INITIATED"
DIVIDEND_INCREASED = "DIVIDEND_INCREASED"
DIVIDEND_UNCHANGED = "DIVIDEND_UNCHANGED"
DIVIDEND_DECREASED = "DIVIDEND_DECREASED"
DIVIDEND_SUSPENDED = "DIVIDEND_SUSPENDED"
DIVIDEND_NONE = "NO_DIVIDEND"

# A change smaller than this, in percent of the prior TTM dividend, is
# UNCHANGED rather than INCREASED/DECREASED — set wide relative to a typical
# per-share dividend given the integer-rounding ceiling measured above, so a
# rounding artifact is not read as a policy change.
CLASSIFY_THRESHOLD_PCT = 3.0


def _per_share_amount(record: dict, resolved: dict[str, str] | None = None) -> float | None:
    """The declared per-share dividend THIS FILING states, or `None`.

    Mirrors `finnhub_derive.amount`'s "first stated concept, currency-only"
    discipline exactly, except the accepted class is `PER_SHARE`, because
    this concept has no other meaning in any filing it appears in.
    """
    if resolved is None:
        resolved = FF.resolve_units(record)
    for section in ("ic", "bs", "cf"):
        for entry in (record.get("statements") or {}).get(section) or []:
            if FF.strip_namespace(entry.get("concept")) != CONCEPT:
                continue
            if FF.value_class(record, entry, resolved) != FF.PER_SHARE:
                continue
            value = entry.get("value")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def trailing_twelve_months_per_share(by_key: dict[tuple[int, str], dict],
                                     year: int, stage: str) -> tuple[float | None, str]:
    """TTM declared dividend per share ending at this filing.

    Identical rollforward arithmetic to `finnhub_derive.trailing_twelve_months`
    (`FY(Y-1) - cum(Y-1, stage) + cum(Y, stage)`), applied to the per-share
    reader above instead of a currency chain. A missing prior-year filing
    yields `None`, never an annualisation — the same discipline, not a
    relaxed copy of it.
    """
    current = by_key.get((year, stage))
    if current is None:
        return None, BASIS_INCOMPLETE
    this_period = _per_share_amount(current)
    if this_period is None:
        return None, BASIS_INCOMPLETE
    if stage == FF.FY:
        return this_period, BASIS_ANNUAL

    prior_annual = by_key.get((year - 1, FF.FY))
    prior_same = by_key.get((year - 1, stage))
    if prior_annual is None or prior_same is None:
        return None, BASIS_INCOMPLETE
    full_year = _per_share_amount(prior_annual)
    same_stage = _per_share_amount(prior_same)
    if full_year is None or same_stage is None:
        return None, BASIS_INCOMPLETE
    return full_year - same_stage + this_period, BASIS_ROLLFORWARD


def classify_change(current: float | None, prior: float | None) -> str | None:
    """One of the five event labels, or `None` when there is nothing to
    classify (either TTM reading unavailable).

    `DIVIDEND_SUSPENDED`/`DIVIDEND_INITIATED` are read off a genuine
    zero-vs-positive transition, never off a `None` standing in for zero —
    a company with no dividend concept in its filings at all classifies as
    `None` here (data absent), not `DIVIDEND_SUSPENDED` (a fact about the
    company).
    """
    if current is None or prior is None:
        return None
    if prior <= 0 and current <= 0:
        return DIVIDEND_NONE
    if prior <= 0 < current:
        return DIVIDEND_INITIATED
    if prior > 0 and current <= 0:
        return DIVIDEND_SUSPENDED
    change_pct = 100.0 * (current - prior) / prior
    if change_pct > CLASSIFY_THRESHOLD_PCT:
        return DIVIDEND_INCREASED
    if change_pct < -CLASSIFY_THRESHOLD_PCT:
        return DIVIDEND_DECREASED
    return DIVIDEND_UNCHANGED


def build_for_ticker(records: list[dict]) -> list[dict]:
    """Every classifiable dividend-change event for one US ticker.

    One row per filing that has a classifiable prior comparison — a
    company's first-ever filing in the store never gets a row here (there
    is nothing to compare it to), matching `finnhub_derive.build_for_ticker`'s
    own "no fields, no row" discipline.
    """
    by_key = US.index_filings(records)
    out: list[dict] = []
    for (year, stage), filing in sorted(by_key.items(),
                                        key=lambda kv: (kv[0][0], US.STAGE_ORDER[kv[0][1]])):
        current, current_basis = trailing_twelve_months_per_share(by_key, year, stage)
        prior, prior_basis = trailing_twelve_months_per_share(by_key, year - 1, stage)
        event = classify_change(current, prior)
        if event is None:
            continue
        out.append({
            "ticker": filing["ticker"],
            "reportPeriod": f"{year}-{stage}",
            "reportDate": filing["periodEnd"],
            "availableFrom": filing["availableFrom"],
            "event": event,
            "dividendPerShareTtm": current,
            "priorDividendPerShareTtm": prior,
            "changePct": (100.0 * (current - prior) / prior
                         if current is not None and prior not in (None, 0) else None),
            "derivation": {"currentBasis": current_basis, "priorBasis": prior_basis},
        })
    return sorted(out, key=lambda row: str(row["availableFrom"]))


def coverage(rows: list[dict]) -> dict:
    """Event counts by label — never averaged into a single "has dividend
    data" number, same discipline as every other `coverage()` in this line.
    """
    counts: dict[str, int] = {}
    for row in rows:
        event = row.get("event")
        if event:
            counts[event] = counts.get(event, 0) + 1
    return {"rows": len(rows), "eventCounts": counts}
