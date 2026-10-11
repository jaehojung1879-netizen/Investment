"""One weekly observation of the US capital-allocation research program: universe -> decision -> receipt inputs.

This is the single path a future weekly job would run. It is the SAME classification the coverage audit used
(`us_capital_allocation_coverage.classify_member`), so the audited coverage and the prospective decision cannot drift apart.

It reads no return and no price level for selection. Prices enter only through `price_row`, which packages a signal-session close
for the receipt's observation-price block; they never feed the rule.
"""
from __future__ import annotations

from collections import Counter

from pipeline import price_adjustment as PA
from pipeline import us_capital_allocation_coverage as C
from pipeline import us_capital_allocation_policy as P
from pipeline import us_capital_allocation_receipts as R

PRICE_BASIS = "as-traded-forward-total-return-v1"


def membership_identity(snapshot: dict) -> dict:
    """The dated S&P 500 snapshot the decision used, named by its own source commit."""
    return {"snapshotDate": snapshot["date"], "sourceCommit": snapshot["sourceCommit"], "members": len(snapshot["members"])}


def observe_week(ctx: C.WeekContext, membership_snapshot: dict, signal_date: str) -> dict:
    """Decision plus every input the receipt records. `membership_snapshot` must already be the one strictly before `signal_date`."""
    if membership_snapshot is None or membership_snapshot["date"] >= signal_date:
        raise ValueError("MEMBERSHIP_SNAPSHOT_NOT_STRICTLY_BEFORE_THE_SIGNAL_DATE")
    rows = [C.classify_member(ctx, membership_snapshot, signal_date, raw) for raw in membership_snapshot["members"]]
    evaluations = [e for e in (C.member_evaluation(r) for r in rows) if e is not None]
    decision = P.select(evaluations)
    by_symbol = {r.symbol: r for r in rows}
    chosen = sorted(decision["weights"] or [])
    return {
        "decision": decision,
        "membership": membership_identity(membership_snapshot),
        "pit_evidence": {t: R.pit_evidence(by_symbol[t].snapshot) for t in chosen},
        "measured_tickers": sorted(r.symbol for r in rows if r.status == C.JOINT_MEASURED),
        "statusCounts": dict(sorted(Counter(r.status for r in rows).items())),
        "priceTickers": {t: by_symbol[t].ticker for t in chosen},      # symbol -> the ticker its price series is filed under
    }


def price_row(frame, session: str, vendor: str, retrieved_at_utc: str) -> dict:
    """The signal-session close of one name, on both the as-traded and the forward total-return basis.

    `frame` is a split-adjusted, dividend-unadjusted vendor frame (what `price_adjustment.to_total_return` takes). The row for
    `session` must exist: no earlier close is substituted for a missing one, because a stale price is not the observation price.
    """
    rebased, _ = PA.to_total_return(frame)
    if rebased is None or not len(rebased):
        raise ValueError("NO_CLOSE_ON_THE_SIGNAL_SESSION: " + session)
    labels = [str(i)[:10] for i in rebased.index]
    if session not in labels:
        raise ValueError("NO_CLOSE_ON_THE_SIGNAL_SESSION: " + session)
    position = labels.index(session)
    # As traded = the split-adjusted close undone by the splits that come AFTER the session (they have not happened yet at that time).
    clean = PA.normalize_daily_frame(frame)
    ratios = PA._series(clean, PA.SPLIT, 0.0)
    ratios = ratios.where(ratios > 0, 1.0)
    after = PA.future_split_factor(ratios)
    as_traded = float(PA._series(clean, "Close", float("nan")).iloc[position] * after[position])
    return {"session": session, "asTradedClose": as_traded, "totalReturnIndexClose": float(rebased["Close"].iloc[position]),
            "vendor": vendor, "retrievedAtUtc": retrieved_at_utc, "basis": PRICE_BASIS}
