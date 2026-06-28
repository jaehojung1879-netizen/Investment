"""Daily short-term trade-idea engine.

For each candidate it combines the calibrated UP-probability at the trade
horizon with the historical UP/DOWN move sizes to estimate an expected value,
then subtracts a round-trip cost hurdle. Only positive-edge, high-conviction,
non-bear ideas are proposed, each with an explicit hold-until date and an
invalidation rule. Ideas are ranked within each region (KR / US).

Why a cost hurdle and a conviction floor: short-horizon direction models sit
close to a coin flip, so a raw probability over 0.5 is not a tradeable edge.
The edge has to clear transaction costs (and, for short-term holds, tax) to be
worth acting on.
"""
from __future__ import annotations

import pandas as pd

# Round-trip cost hurdle as a fraction of price. Covers slippage on both legs
# plus a haircut for short-term tax/fees. KR short-term trading is taxed/fee'd
# more heavily, so its hurdle is higher.
COST_HURDLE = {"US": 0.004, "KR": 0.007}
CONVICTION_FLOOR = 0.55


def expected_value(prob_up: float, up_mean: float, down_mean: float) -> float:
    """Expected forward return (fraction) given UP probability and move sizes."""
    return prob_up * up_mean + (1 - prob_up) * down_mean


def build_idea(
    ticker: str,
    region: str,
    prob_up: float,
    stats: dict,
    horizon: int,
    last_date: str,
    regime: str,
) -> dict | None:
    ev = expected_value(prob_up, stats["upMean"], stats["downMean"])
    hurdle = COST_HURDLE.get(region, 0.004)
    ev_net = ev - hurdle

    qualifies = prob_up >= CONVICTION_FLOOR and ev_net > 0 and regime != "Bear"
    if not qualifies:
        return None

    hold_until = (pd.Timestamp(last_date) + pd.tseries.offsets.BDay(horizon)).strftime("%Y-%m-%d")
    return {
        "ticker": ticker,
        "region": region,
        "probUp": round(prob_up, 4),
        "expMovePct": round(ev * 100, 2),
        "edgeNetPct": round(ev_net * 100, 2),
        "horizon": horizon,
        "entry": last_date,
        "holdUntil": hold_until,
        "regime": regime,
        "invalidation": "종가가 MA20 하회하거나 다음 신호 확률이 0.5 미만이면 조기 청산",
    }


def rank_ideas(ideas: list[dict], per_region: int = 5) -> dict:
    """Group qualifying ideas by region, ranked by net edge (desc)."""
    out: dict[str, list[dict]] = {}
    for region in ("KR", "US"):
        regional = sorted(
            (i for i in ideas if i["region"] == region),
            key=lambda x: x["edgeNetPct"],
            reverse=True,
        )
        out[region] = regional[:per_region]
    return out
