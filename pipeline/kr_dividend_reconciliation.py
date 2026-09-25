"""Cross-validate DART-derived dividend rows against Yahoo's, on names both
vendors serve.

WHY THIS EXISTS. `docs/alpha-opportunity-v3-data-repair-plan.md`'s repair
plan is explicit: DART dividend data may not be applied to the 22 terminated
securities Yahoo cannot serve until it is validated on continuing names
where BOTH vendors answer. This module is that comparison. It never looks at
a stock return to decide whether a match is right — only identity, amount
and date agreement.

EVERY DISAGREEMENT IS EXPLAINED, NEVER AVERAGED AWAY. `reconcile` classifies
each unmatched or disagreeing pair into exactly one of the categories in
`MISMATCH_REASONS`; a pair this module cannot place stays `UNRESOLVED` rather
than being silently dropped from the count.
"""
from __future__ import annotations

import datetime as _dt

SOURCE_TIMING = "SOURCE_TIMING"
AMENDMENT = "AMENDMENT"
GROSS_NET_REPRESENTATION = "GROSS_NET_REPRESENTATION"
STOCK_VS_CASH_CLASSIFICATION = "STOCK_VS_CASH_CLASSIFICATION"
DATE_SEMANTICS = "DATE_SEMANTICS"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
UNRESOLVED = "UNRESOLVED"

MISMATCH_REASONS = frozenset({
    SOURCE_TIMING, AMENDMENT, GROSS_NET_REPRESENTATION,
    STOCK_VS_CASH_CLASSIFICATION, DATE_SEMANTICS, IDENTITY_MISMATCH, UNRESOLVED,
})

# A DART event and a Yahoo event on the same ticker are matched only if their
# dates fall within this window. Widened past a same-day match only for the
# defensible reason two sources can date the "same" distribution differently
# (decision vs. record vs. ex-date) — never to force a match that identity
# alone would not support.
DEFAULT_DATE_TOLERANCE_DAYS = 10
DEFAULT_AMOUNT_TOLERANCE_PCT = 1.0


def _parse_date(value) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _amount_close(a: float | None, b: float | None, tolerance_pct: float) -> bool:
    if a is None or b is None:
        return False
    if a == 0 and b == 0:
        return True
    denom = max(abs(a), abs(b))
    if denom == 0:
        return True
    return abs(a - b) / denom * 100.0 <= tolerance_pct


def match_events(dart_rows: list[dict], yahoo_rows: list[dict], *,
                 date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS
                 ) -> list[dict]:
    """Pair DART and Yahoo rows for one ticker by nearest date within the
    tolerance window. Each side is used at most once — the closest date wins,
    ties broken by input order — so agreement counts never double a row.
    """
    remaining_yahoo = list(enumerate(yahoo_rows))
    pairs = []
    for dart_row in dart_rows:
        dart_date = _parse_date(dart_row.get("recordDate") or dart_row.get("receiptDate"))
        best = None
        best_gap = None
        for position, (idx, yahoo_row) in enumerate(remaining_yahoo):
            yahoo_date = _parse_date(yahoo_row.get("date"))
            if dart_date is None or yahoo_date is None:
                continue
            gap = abs((dart_date - yahoo_date).days)
            if gap <= date_tolerance_days and (best_gap is None or gap < best_gap):
                best, best_gap, best_position = (idx, yahoo_row), gap, position
        if best is not None:
            remaining_yahoo.pop(best_position)
            pairs.append({"dart": dart_row, "yahoo": best[1], "dateGapDays": best_gap})
        else:
            pairs.append({"dart": dart_row, "yahoo": None, "dateGapDays": None})
    for _, yahoo_row in remaining_yahoo:
        pairs.append({"dart": None, "yahoo": yahoo_row, "dateGapDays": None})
    return pairs


def classify_mismatch(pair: dict, *, amount_tolerance_pct: float) -> str | None:
    """One `MISMATCH_REASONS` value, or `None` when the pair agrees.

    Never reads a stock return. Only the two sides' own stated fields.
    """
    dart_row, yahoo_row = pair.get("dart"), pair.get("yahoo")
    if dart_row is None or yahoo_row is None:
        return SOURCE_TIMING
    if dart_row.get("ticker") and yahoo_row.get("ticker") and \
            dart_row["ticker"] != yahoo_row["ticker"]:
        return IDENTITY_MISMATCH
    dart_amount = dart_row.get("amountPerShare")
    yahoo_amount = yahoo_row.get("amountPerShare")
    if dart_row.get("isStockDividend") != yahoo_row.get("isStockDividend"):
        return STOCK_VS_CASH_CLASSIFICATION
    if dart_row.get("isAmendment") or dart_row.get("supersedes"):
        return AMENDMENT
    if not _amount_close(dart_amount, yahoo_amount, amount_tolerance_pct):
        if dart_amount is not None and yahoo_amount not in (None, 0) and \
                _amount_close(dart_amount * 0.846, yahoo_amount, amount_tolerance_pct):
            # 15.4% Korean dividend withholding is a documented, dated rule
            # (not invented here); a DART decision amount close to Yahoo's
            # NET distribution at that ratio is a representation difference,
            # not a wrong number. Only flagged, never silently corrected.
            return GROSS_NET_REPRESENTATION
        return UNRESOLVED
    if pair.get("dateGapDays") not in (None, 0):
        return DATE_SEMANTICS
    return None


def reconcile(dart_rows: list[dict], yahoo_rows: list[dict], *,
             date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
             amount_tolerance_pct: float = DEFAULT_AMOUNT_TOLERANCE_PCT) -> dict:
    """Full reconciliation for one ticker: matched pairs, agreement count,
    and a mismatch reason for every disagreement. Publishes counts, never a
    pass/fail verdict — the repair plan decides what tolerance is acceptable
    before any DART dividend row is applied to a name Yahoo cannot check.
    """
    pairs = match_events(dart_rows, yahoo_rows, date_tolerance_days=date_tolerance_days)
    rows = []
    for pair in pairs:
        reason = classify_mismatch(pair, amount_tolerance_pct=amount_tolerance_pct)
        rows.append({**pair, "agrees": reason is None, "mismatchReason": reason})
    agree = sum(row["agrees"] for row in rows)
    return {
        "pairs": rows,
        "dartRows": len(dart_rows),
        "yahooRows": len(yahoo_rows),
        "matchedPairs": sum(row["dart"] is not None and row["yahoo"] is not None for row in rows),
        "agreeingPairs": agree,
        "disagreeingPairs": len(rows) - agree,
        "mismatchReasonCounts": {
            reason: sum(row["mismatchReason"] == reason for row in rows)
            for reason in sorted(MISMATCH_REASONS)
        },
    }


def reconcile_many(dart_by_ticker: dict[str, list[dict]],
                   yahoo_by_ticker: dict[str, list[dict]], **kwargs) -> dict:
    """`reconcile` over every ticker present on either side, plus a rollup."""
    tickers = sorted(set(dart_by_ticker) | set(yahoo_by_ticker))
    by_ticker = {ticker: reconcile(dart_by_ticker.get(ticker, []),
                                   yahoo_by_ticker.get(ticker, []), **kwargs)
                for ticker in tickers}
    total_pairs = sum(len(r["pairs"]) for r in by_ticker.values())
    total_agree = sum(r["agreeingPairs"] for r in by_ticker.values())
    rollup_reasons = {reason: sum(r["mismatchReasonCounts"][reason] for r in by_ticker.values())
                      for reason in sorted(MISMATCH_REASONS)}
    return {
        "tickers": len(tickers),
        "byTicker": by_ticker,
        "totalPairs": total_pairs,
        "totalAgreeingPairs": total_agree,
        "agreementRatePct": round(100.0 * total_agree / total_pairs, 2) if total_pairs else None,
        "mismatchReasonCounts": rollup_reasons,
    }
