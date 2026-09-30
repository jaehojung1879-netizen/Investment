"""Robust 0--5 stock construction, executable limits, explicit cash and costs."""
from __future__ import annotations

import math


def eligible(row, cfg):
    return (row.get("tradable") is True and row.get("adv60") is not None
            and math.isfinite(row["adv60"]) and row["adv60"] >= cfg["minimumAdvKrw"]
            and row.get("downsideVol126") is not None and math.isfinite(row["downsideVol126"])
            and row["downsideVol126"] >= cfg["minimumDownsideVol"])


def select(rows, cfg, *, score="predictionH126"):
    """Overlay is absent from selection, including positive-opportunity admission."""
    seen = [r["ticker"] for r in rows]
    if len(set(seen)) != len(seen):
        raise ValueError("DUPLICATE_SELECTION_SECURITY")
    candidates = [r for r in rows if eligible(r, cfg) and r.get(score) is not None
                  and math.isfinite(r[score]) and r[score] > cfg["roundTripFixedCost"]]
    return sorted(candidates, key=lambda r: (-r[score], r["ticker"]))[:cfg["maximumHoldings"]]


def size(selected, cfg):
    """Capped proportional water-fill BEFORE overlay; unallocatable funds stay cash."""
    raw = {r["ticker"]: 1 / r["downsideVol126"] for r in selected}
    caps = {r["ticker"]: min(cfg["singleNameCap"],
                            cfg["maximumAdvFraction"] * r["adv60"] / cfg["referenceNavKrw"])
            for r in selected}
    weights = dict.fromkeys(raw, 0.0)
    remaining, active = 1.0, set(raw)
    while active and remaining > 1e-12:
        total = sum(raw[t] for t in sorted(active))
        bound = sorted(t for t in active if remaining * raw[t] / total >= caps[t])
        if not bound:
            for t in sorted(active):
                weights[t] = remaining * raw[t] / total
            break
        for t in bound:
            weights[t] = caps[t]
            remaining -= caps[t]
            active.remove(t)
    return dict(sorted(weights.items()))


def construct(rows, multiplier, cfg):
    if not math.isfinite(multiplier) or not 0 <= multiplier <= 1:
        raise ValueError("NO_LEVERAGE_OVERLAY_REQUIRED")
    selected = select(rows, cfg)
    base = size(selected, cfg)
    weights = {t: w * multiplier for t, w in base.items()}
    if len(weights) > 5 or sum(weights.values()) > 1 + 1e-12:
        raise ValueError("PORTFOLIO_CONSTRAINT_VIOLATION")
    return {"selected": [r["ticker"] for r in selected], "baseWeights": base, "weights": weights,
            "cashWeight": 1 - sum(weights.values()), "riskMultiplier": multiplier,
            "sectorCapStatus": "DEFERRED_BY_PIT_SECTOR_HISTORY"}



def limit_new_positions(after_sells, desired_buys, selected, maximum=5):
    """Partial/deferred exits occupy slots; admit new names by unchanged model rank."""
    occupied = {ticker for ticker, weight in after_sells.items() if weight > 1e-12}
    allowed = {t: desired_buys[t] for t in sorted(occupied) if t in desired_buys}
    slots = max(0, maximum - len(occupied))
    for ticker in selected:
        if ticker not in occupied and ticker in desired_buys and slots:
            allowed[ticker] = desired_buys[ticker]
            slots -= 1
    return allowed

def trading_cost(before, after, adv, cfg, *, stress=1.0):
    """NAV fraction cost on actual buys/sells; levy buffer is an assumption, not law."""
    buys = sells = impact = 0.0
    for t in sorted(set(before) | set(after)):
        delta = after.get(t, 0) - before.get(t, 0)
        if abs(delta) <= 1e-12:
            continue
        value = adv.get(t)
        if value is None or not math.isfinite(value) or value <= 0:
            raise ValueError("MISSING_EXECUTABLE_LIQUIDITY")
        participation = abs(delta) * cfg["referenceNavKrw"] / value
        if participation > cfg["maximumAdvFraction"] + 1e-12:
            raise ValueError("ADV_TRADE_CAP_EXCEEDED")
        buys += max(delta, 0)
        sells += max(-delta, 0)
        impact += abs(delta) * cfg["impactAtOnePercent"] * math.sqrt(participation / .01)
    cost = stress * (buys * cfg["buyFixedCost"] + sells * cfg["sellFixedCost"] + impact)
    if not math.isfinite(cost) or not 0 <= cost < 1:
        raise ValueError("INVALID_COST")
    return {"costFraction": cost, "buyTurnover": buys, "sellTurnover": sells,
            "oneWayTurnover": (buys + sells) / 2, "impactFraction": stress * impact}
