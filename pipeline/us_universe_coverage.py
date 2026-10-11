"""Ticker-level data-gap manifest for historical S&P 500 and Nasdaq-100 members.

One row per historical symbol in either index inside the study window, with
what the repository already holds for it and the ONE status that names the
first thing a study would trip over:

  NEEDS_IDENTITY_REPAIR      the symbol's price panel belongs to another
                             security, or a rename is suspected but unproven
  BLOCKED_PAID_SOURCE        departed, already requested from the free vendor
                             and refused; only paid vendors quoted for it
  NEEDS_PRICE_HISTORY        no own price panel, never shown to be paid-only
  NEEDS_FUNDAMENTALS         priced, but no PIT filing in the Finnhub store
  NEEDS_MEMBERSHIP_EVIDENCE  priced and covered, but its only membership
                             evidence is the derived Nasdaq-100 record
  NOT_EVALUABLE              malformed or unresolvable key
  READY                      evidenced membership, own price panel, PIT filings

Every other gap is listed in ``gaps`` as well, so a READY-after-repair reading
is possible without re-running. Missing data is never read as a zero return,
and no symbol is dropped because it did not survive.
"""
from __future__ import annotations

import pandas as pd

READY = "READY"
NEEDS_FUNDAMENTALS = "NEEDS_FUNDAMENTALS"
NEEDS_PRICE_HISTORY = "NEEDS_PRICE_HISTORY"
NEEDS_IDENTITY_REPAIR = "NEEDS_IDENTITY_REPAIR"
NEEDS_MEMBERSHIP_EVIDENCE = "NEEDS_MEMBERSHIP_EVIDENCE"
BLOCKED_PAID_SOURCE = "BLOCKED_PAID_SOURCE"
NOT_EVALUABLE = "NOT_EVALUABLE"
PRECEDENCE = (NOT_EVALUABLE, NEEDS_IDENTITY_REPAIR, BLOCKED_PAID_SOURCE, NEEDS_PRICE_HISTORY,
              NEEDS_FUNDAMENTALS, NEEDS_MEMBERSHIP_EVIDENCE)
STATUSES = (READY, *PRECEDENCE)

# A price panel this many calendar days short of the needed span at either end
# is partial, not coverage (about one month of sessions).
SPAN_TOLERANCE_DAYS = 31
# v3 survivorship categories whose panel is NOT this security's own history.
NOT_OWN_PANEL = {"TICKER_REUSE_DIFFERENT_ISSUER"}
# v3 categories whose panel starts or stops inside the membership: the symbol
# may now belong to a different issuer (DELL, FOXA, DOW, SNDK ...).
IDENTITY_SUSPECT = {"CURRENT_MEMBER_PANEL_LATE_START", "PANEL_PARTIAL_OWN_HISTORY"}


def clip_spans(spans: list[list], start: str, end: str) -> list[list[str]]:
    out = []
    for a, b in spans:
        a = max(a, start)
        b = min(b or end, end)
        if a <= b:
            out.append([a, b])
    return out


def panel_starts_late(need: list[list[str]], panel: dict | None) -> bool:
    """A panel that begins after the membership began is not that member's history.

    Index membership cannot predate listing, so a later first session means
    the vendor history is truncated or the symbol now names another security.
    """
    if not panel or not need:
        return False
    first = pd.Timestamp(min(a for a, _ in need))
    return pd.Timestamp(panel["first"]) > first + pd.Timedelta(days=SPAN_TOLERANCE_DAYS)


def span_covered(need: list[list[str]], panel: dict | None) -> bool:
    if not panel or not need:
        return False
    first = pd.Timestamp(min(a for a, _ in need))
    last = pd.Timestamp(max(b for _, b in need))
    tol = pd.Timedelta(days=SPAN_TOLERANCE_DAYS)
    return (pd.Timestamp(panel["first"]) <= first + tol
            and pd.Timestamp(panel["last"]) >= last - tol)


def classify(row: dict) -> tuple[str, list[str]]:
    gaps = []
    if row.get("malformed"):
        gaps.append(NOT_EVALUABLE)
    if row.get("identityIssue"):
        gaps.append(NEEDS_IDENTITY_REPAIR)
    if not row.get("priceCovered"):
        gaps.append(BLOCKED_PAID_SOURCE if row.get("freeVendorRefused") else NEEDS_PRICE_HISTORY)
    if not row.get("fundamentalFilings"):
        gaps.append(NEEDS_FUNDAMENTALS)
    if not row.get("membershipEvidenced"):
        gaps.append(NEEDS_MEMBERSHIP_EVIDENCE)
    for status in PRECEDENCE:
        if status in gaps:
            return status, gaps
    return READY, gaps


def build_manifest(*, start: str, end: str, sp500: dict, sp500_identity: dict, sp500_unpriced: set,
                   n100_spans: dict, prices: dict, filings: dict, ciks: dict,
                   successors: dict) -> list[dict]:
    """Rows for the union of both memberships inside [start, end].

    ``sp500`` maps symbol -> {listed, delisted}; ``sp500_identity`` symbol ->
    v3 category; ``sp500_unpriced`` the departed symbols the free vendor was
    asked for and served nothing; ``n100_spans`` symbol -> [[from, to)];
    ``prices`` symbol -> {first, last}; ``filings`` symbol -> count;
    ``successors`` symbol -> verified rename successor (v3, CIK/name evidence).
    """
    rows = []
    sp_spans = {t: clip_spans([[v["listed"], v["delisted"]]], start, end) for t, v in sp500.items()}
    symbols = sorted({t for t, s in sp_spans.items() if s} | {t for t, s in n100_spans.items()
                                                             if clip_spans(s, start, end)})
    for symbol in symbols:
        in_sp = bool(sp_spans.get(symbol))
        n_spans = clip_spans(n100_spans.get(symbol, []), start, end)
        need = (sp_spans.get(symbol) or []) + n_spans
        priced_by = successors.get(symbol) or symbol
        category = sp500_identity.get(symbol)
        malformed = not symbol.replace("-", "").replace(".", "").isalnum() or " " in symbol
        reused = category in NOT_OWN_PANEL
        panel = None if reused else prices.get(priced_by)
        identity_issue = reused or category in IDENTITY_SUSPECT or panel_starts_late(need, panel)
        row = {
            "symbol": symbol,
            "inSp500": in_sp, "inNasdaq100": bool(n_spans),
            "sp500Span": sp_spans.get(symbol) or None, "nasdaq100Spans": n_spans or None,
            "sp500IdentityCategory": category,
            "renameSuccessor": successors.get(symbol),
            "pricePanel": prices.get(priced_by),
            "priceCovered": span_covered(need, panel),
            "freeVendorRefused": symbol in sp500_unpriced,
            "fundamentalFilings": filings.get(symbol, 0) + (filings.get(successors[symbol], 0)
                                                           if successors.get(symbol) else 0),
            "cik": ciks.get(symbol) or ciks.get(successors.get(symbol, "")),
            "membershipEvidenced": in_sp,
            "membershipEvidence": ("SEALED_SP500_SNAPSHOTS" if in_sp else "DERIVED_N100TICKERS_ONLY"),
            "identityIssue": identity_issue,
            "malformed": malformed,
        }
        row["status"], row["gaps"] = classify(row)
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    def count(subset):
        out = {s: 0 for s in STATUSES}
        for r in subset:
            out[r["status"]] += 1
        return {"symbols": len(subset), **out}
    return {"union": count(rows),
            "sp500": count([r for r in rows if r["inSp500"]]),
            "nasdaq100": count([r for r in rows if r["inNasdaq100"]]),
            "nasdaq100Only": count([r for r in rows if r["inNasdaq100"] and not r["inSp500"]]),
            "both": count([r for r in rows if r["inNasdaq100"] and r["inSp500"]]),
            "withFinnhubFilings": sum(1 for r in rows if r["fundamentalFilings"]),
            "withOwnPriceCoverage": sum(1 for r in rows if r["priceCovered"])}
