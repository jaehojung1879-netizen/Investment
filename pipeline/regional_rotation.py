"""Walk-forward regional weight rotation: blend two standalone, single-region
replays (US-only, KR-only) into one combined portfolio, re-deciding the split
every quarter from nothing but each region's own trailing record.

WHY A SEPARATE MODULE, NOT A THIRD SELECTOR. `champion`/`challenger` compare
two ways of RANKING candidates inside one already-fixed regional universe.
This compares two already-fixed selectors' OWN regions against each other and
asks how much of the book each should hold — a capital-allocation question
sitting a level above stock selection, not a third way of picking stocks.

WHY WALK-FORWARD, NOT "PICK THE BETTER REGION OVER THE FULL HISTORY". Scoring
each region's ENTIRE past and handing the winner 100% of the book is exactly
the look-ahead this project's `LookAheadError` exists to catch everywhere
else — it uses information (the full-sample winner) that was not available
on any of the dates being scored. Every weight decided here uses only
decisions whose outcome had already matured strictly before the decision
date; `apply_schedule` applies it from that decision date, never retroactively.

WHY SOFTMAX, NOT A RAW RETURN RATIO. A ratio of two trailing returns is
undefined or sign-flipped the moment either is zero or negative, which a
region's excess return over its own benchmark does routinely. Softmax is
smooth and well-defined on any sign, and `DEFAULT_TEMPERATURE` sets how many
points of trailing excess return roughly double one region's relative odds
against the other — a legible dial where a return ratio has none.

WHY A FLOOR. `DEFAULT_FLOOR` keeps every region holding at least that share
regardless of the score gap. Both regions are real, ongoing, currently-priced
markets the replay has already measured (not one of them being an artifact of
missing data) — a single quarter's trailing read is a tilt, not a mandate to
abandon a market entirely.

WHAT THIS DOES NOT DO. It does not invent a trailing score where none is
measurable yet (cold start reads as equal weight, not as an extrapolated
guess), and it does not change what `champion`/`challenger` are compared
against inside a region — the blended output is meant to be scored the same
way any other path is, through `portfolio_validation._path_metrics`.
"""
from __future__ import annotations

import math

import pandas as pd

DEFAULT_LOOKBACK_DAYS = 252     # CALENDAR days (frozen v1 semantics, not trading sessions)
DEFAULT_TEMPERATURE = 0.05      # 5pp of trailing excess return e-folds the odds ratio
DEFAULT_FLOOR = 0.15            # neither region ever falls below this share


def trailing_mean_excess(decisions: list[dict], as_of: str, *,
                         lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> float | None:
    """Mean `grossExcessReturn` over decisions matured strictly before `as_of`.

    `endDate < as_of`, never `<=`: a decision dated exactly `as_of` has not
    been observed as of `as_of` (it is the one about to be decided, not
    evidence for deciding it), so `<=` would let a date score itself. `None`
    when nothing has matured yet in the window — the caller's cold-start
    case, not a zero this function is entitled to invent.
    """
    cutoff = pd.Timestamp(as_of)
    window_start = cutoff - pd.Timedelta(days=lookback_days)
    matured = [row for row in decisions
              if window_start <= pd.Timestamp(row["endDate"]) < cutoff]
    if not matured:
        return None
    values = [float(row["grossExcessReturn"]) for row in matured]
    return sum(values) / len(values)


def softmax_weights(scores: dict[str, float], *, temperature: float = DEFAULT_TEMPERATURE,
                    floor: float = DEFAULT_FLOOR) -> dict[str, float]:
    """Trailing scores -> portfolio weights, bounded away from 0 and 1.

    Softmax the scores first (well-defined on any sign, unlike a raw return
    ratio), then water-fill: any region whose SHARE would land under `floor`
    is PINNED there and the remaining weight is split among the rest by their
    relative softmax shares, repeating until no free region sits under the
    floor. A single lift-then-globally-renormalize pass does not actually
    guarantee the floor — renormalizing after lifting one region back down can
    push it below `floor` again when another region's raw share dominates — so
    this pins each floored region at exactly `floor` and never revisits it.

    THE TEST IS THE REDISTRIBUTED SHARE, NEVER THE RAW ONE. Pinning a region at
    `floor` spends more than its raw share, so every surviving region is scaled
    DOWN by the pass that pinned it — and a region comfortably above `floor` on
    `raw` can land below it afterwards. Re-reading `raw` cannot see that, because
    `raw` does not change; such a loop runs one effective pass and calls it a
    water-fill. Measured on three regions at `floor=0.30` with raw shares
    (0.01, 0.31, 0.68): the 0.31 region is left free and receives
    0.70 x 0.31/0.99 = 0.219, under the floor the function exists to hold.
    Two regions — the only shape `regional-rotation-v1` runs — cannot reach that
    case, so this is a latent correctness fix and not a change to frozen v1
    weights: with one free region left the redistributed share is `1 - floor`,
    which is `>= floor` for every admissible floor.
    """
    regions = sorted(scores)
    if not regions:
        return {}
    if len(regions) == 1:
        return {regions[0]: 1.0}
    if floor * len(regions) > 1.0:
        raise ValueError(f"floor {floor} leaves no room for {len(regions)} regions")
    if not math.isfinite(temperature) or temperature <= 0 or not 0 <= floor <= 1 / len(regions):
        raise ValueError("invalid temperature or floor")
    if not all(math.isfinite(s) for s in scores.values()):
        raise ValueError("non-finite regional score")
    offset = max(scores.values())
    exps = {r: math.exp((scores[r] - offset) / temperature) for r in regions}
    total = sum(exps.values())
    raw = {r: exps[r] / total for r in regions}

    pinned: dict[str, float] = {}
    free = set(regions)
    while free:
        remaining = 1.0 - sum(pinned.values())
        free_raw_total = sum(raw[r] for r in free)
        if free_raw_total <= 0:
            break
        # Association kept exactly as the single-pass version had it, so the
        # two-region path this module actually runs is bit-identical.
        share = {r: remaining * (raw[r] / free_raw_total) for r in free}
        below = {r for r in free if share[r] <= floor}
        if not below:
            return {**pinned, **{r: share[r] for r in sorted(free)}}
        for r in below:
            pinned[r] = floor
        free -= below
    # Every region pinned — only when the floor exactly fills the simplex or
    # every raw share ties at it. Equal split is the only assignment left that
    # still sums to 1.
    return {r: 1.0 / len(regions) for r in regions}


def quarterly_decision_dates(all_dates: list[str]) -> list[str]:
    """The first ACTUAL replay date on or after each calendar quarter start.

    Picked from the dates the replay really has, never an invented calendar
    date the ledger might not hold (a holiday, a missing shard).
    """
    timestamps = sorted({pd.Timestamp(d) for d in all_dates})
    seen: set[tuple[int, int]] = set()
    picked = []
    for ts in timestamps:
        key = (ts.year, ts.quarter)
        if key not in seen:
            seen.add(key)
            picked.append(ts.strftime("%Y-%m-%d"))
    return picked


def regional_weight_schedule(decisions_by_region: dict[str, list[dict]], *,
                             lookback_days: int = DEFAULT_LOOKBACK_DAYS,
                             temperature: float = DEFAULT_TEMPERATURE,
                             floor: float = DEFAULT_FLOOR,
                             evaluation_dates: list[str] | None = None) -> list[dict]:
    """One row per quarterly re-decision date: each region's trailing score
    (`None` where unmeasurable) and the resulting weight.

    Cold start — any region without a measurable trailing score yet — reads
    as equal weight across every region, not a one-region default: an
    unmeasured region is not evidence against it.
    """
    if lookback_days <= 0:
        raise ValueError("lookback must be positive")
    all_dates = (evaluation_dates if evaluation_dates is not None else
                 [row["date"] for rows in decisions_by_region.values() for row in rows])
    regions = sorted(decisions_by_region)
    schedule = []
    for as_of in quarterly_decision_dates(all_dates):
        scores = {region: trailing_mean_excess(decisions_by_region[region], as_of,
                                                lookback_days=lookback_days)
                  for region in regions}
        measured = {r: s for r, s in scores.items() if s is not None}
        if len(measured) < len(regions):
            weights = {r: 1.0 / len(regions) for r in regions} if regions else {}
        else:
            weights = softmax_weights(measured, temperature=temperature, floor=floor)
        raw = (softmax_weights(measured, temperature=temperature, floor=0.0)
               if len(measured) == len(regions) else dict(weights))
        schedule.append({
            "date": as_of,
            "trailingExcessPct": {r: (None if s is None else round(s * 100, 4))
                                  for r, s in scores.items()},
            "rawWeights": {r: round(w, 6) for r, w in raw.items()},
            "weights": {r: round(w, 6) for r, w in weights.items()},
        })
    return schedule


def apply_schedule(decisions_by_region: dict[str, list[dict]],
                   schedule: list[dict]) -> list[dict]:
    """Blend every rebalance date's realized region returns using the most
    recently DECIDED weight — the weight a quarterly decision date sets
    governs every rebalance date from that date up to the next quarterly
    decision, never a date before it was decided.

    Rows are emitted in the shape `portfolio_validation._path_metrics`
    already reads (`date`, `endDate`, `grossReturn`, `benchmarkReturn`,
    `weights`, `regionByTicker`), so the blended path is scored by the same
    cost/CAGR/drawdown machinery any other path is — not a second copy of it.
    """
    for region, rows in decisions_by_region.items():
        if len({r["date"] for r in rows}) != len(rows):
            raise ValueError(f"duplicate block dates: {region}")
    by_date_region = {(row["date"], region): row
                      for region, rows in decisions_by_region.items() for row in rows}
    all_dates = sorted({row["date"] for rows in decisions_by_region.values() for row in rows})
    schedule_sorted = sorted(schedule, key=lambda s: s["date"])

    blended = []
    sched_idx = -1
    active_weights: dict[str, float] | None = None
    for date in all_dates:
        while (sched_idx + 1 < len(schedule_sorted)
              and schedule_sorted[sched_idx + 1]["date"] <= date):
            sched_idx += 1
            active_weights = schedule_sorted[sched_idx]["weights"]
        if active_weights is None:
            continue  # before the first quarterly decision: nothing to blend yet
        present = {region: by_date_region[(date, region)] for region in active_weights
                  if (date, region) in by_date_region}
        # A missing sleeve is unknown, never permission to invest 100% in the other.
        if set(present) != set(decisions_by_region) or set(active_weights) != set(present):
            continue
        if (any(not math.isfinite(v) or v < 0 for v in active_weights.values())
                or not math.isclose(sum(active_weights.values()), 1.0, abs_tol=1e-6)):
            raise ValueError("regional weights must sum to one")
        w = dict(active_weights)
        end_dates = {present[r]["endDate"] for r in present}
        # One blended block must mature on one date, or "excess return" would
        # mix returns measured over different horizons under one label.
        if len(end_dates) != 1:
            continue
        gross = sum(w[r] * present[r]["grossReturn"] for r in present)
        bench = sum(w[r] * present[r]["benchmarkReturn"] for r in present)
        weights_by_ticker: dict[str, float] = {}
        region_by_ticker: dict[str, str] = {}
        for region, row in present.items():
            for ticker, ticker_weight in row["weights"].items():
                weights_by_ticker[ticker] = ticker_weight * w[region]
                region_by_ticker[ticker] = region
        # Same concentration fields `portfolio_validation.portfolio_replay`
        # computes for every other path, so `_path_metrics` need not special-
        # case a blended row to report top1/top3/effectiveNames for it.
        values = list(weights_by_ticker.values())
        book = sum(values)
        result = {
            "date": date, "endDate": end_dates.pop(),
            "grossReturn": gross, "benchmarkReturn": bench,
            "grossExcessReturn": gross - bench,
            "cashWeight": 1 - book,
            "weights": weights_by_ticker, "regionByTicker": region_by_ticker,
            "regionalWeights": dict(w),
            "top1": max(values, default=0),
            "top3": sum(sorted(values, reverse=True)[:3]),
            "effectiveNames": (1 / sum((v / book) ** 2 for v in values)
                               if book > 0 else None),
        }
        daily = ["dailyDates" in row for row in present.values()]
        if any(daily):
            if not all(daily):
                raise ValueError("mixed daily and endpoint regional paths")
            first = next(iter(present.values()))
            dates = first["dailyDates"]
            if any(row["dailyDates"] != dates for row in present.values()):
                raise ValueError("regional daily dates do not align")
            if any(row["dailyRiskFreeNav"] != first["dailyRiskFreeNav"] for row in present.values()):
                raise ValueError("regional risk-free paths differ")
            result.update({
                "dailyDates": list(dates),
                "dailyGrossNav": [sum(w[r] * present[r]["dailyGrossNav"][i] for r in present)
                                  for i in range(len(dates))],
                "dailyBenchmarkNav": [sum(w[r] * present[r]["dailyBenchmarkNav"][i] for r in present)
                                      for i in range(len(dates))],
                "dailyRiskFreeNav": list(first["dailyRiskFreeNav"]),
                "terminalWeights": {}, "terminalRegionByTicker": {},
            })
            # Sleeve capital drifts inside a block. Use end-of-block VALUE shares,
            # not the entry split, when pricing the next rebalance's trades.
            for r, row in present.items():
                share = w[r] * (1 + row["grossReturn"]) / (1 + gross)
                for ticker, value in row["terminalWeights"].items():
                    result["terminalWeights"][ticker] = result["terminalWeights"].get(ticker, 0) + share * value
                result["terminalRegionByTicker"].update(row["terminalRegionByTicker"])
        blended.append(result)
    return blended


def static_blend(decisions_by_region: dict[str, list[dict]]) -> list[dict]:
    """Constant 50/50 capital targets at the same existing rebalance anchors."""
    if set(decisions_by_region) != {"US", "KR"}:
        raise ValueError("static control requires US and KR")
    dates = [r["date"] for rows in decisions_by_region.values() for r in rows]
    return apply_schedule(decisions_by_region, [
        {"date": min(dates), "weights": {"US": 0.5, "KR": 0.5}}]) if dates else []
