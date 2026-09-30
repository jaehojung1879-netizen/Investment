"""Robust 0--5 stock construction, executable limits, explicit cash and costs."""
from __future__ import annotations

import math


def eligible(row, cfg):
    return (bool(row.get("coreFamilyObserved", False)) and row.get("tradable") is True and row.get("adv60") is not None
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
    occupied = {ticker for ticker, weight in after_sells.items() if weight > 0}
    allowed = {t: desired_buys[t] for t in sorted(occupied) if t in desired_buys}
    slots = max(0, maximum - len(occupied))
    for ticker in selected:
        if ticker not in occupied and ticker in desired_buys and slots:
            allowed[ticker] = desired_buys[ticker]
            slots -= 1
    return allowed

def trading_cost(before, after, adv, cfg, *, stress=1.0, nav_krw=None):
    """NAV fraction cost on actual buys/sells; levy buffer is an assumption, not law."""
    buys = sells = impact = 0.0
    for t in sorted(set(before) | set(after)):
        delta = after.get(t, 0) - before.get(t, 0)
        if delta == 0:
            continue
        value = adv.get(t)
        if value is None or not math.isfinite(value) or value <= 0:
            raise ValueError("MISSING_EXECUTABLE_LIQUIDITY")
        participation = abs(delta) * (cfg["referenceNavKrw"] if nav_krw is None else nav_krw) / value
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


def execute_rebalance(before, desired, adv, selected, multiplier, cfg, *, nav_krw, stress=1.0):
    """Exact cash-funded close ledger, amounts in units of PRE-trade NAV.

    Targets are fractions of post-cost NAV. Executable sells are solved first;
    deferred/partial exits occupy slots. A common buy fraction preserves rankings.
    Deterministic bisection funds costs and enforces the post-cost gross budget.
    ADV participation uses the actual executed notional in the KRW100m account.
    """
    if nav_krw <= 0 or not math.isfinite(nav_krw) or not 0 <= multiplier <= 1:
        raise ValueError("INVALID_EXECUTION_NAV_OR_OVERLAY")
    if any(not math.isfinite(w) or w < 0 for w in before.values()) or sum(before.values()) > 1 + 1e-12:
        raise ValueError("INVALID_PRETRADE_BOOK")
    limits = {t: cfg["maximumAdvFraction"] * value / nav_krw for t, value in adv.items()
              if value is not None and math.isfinite(value) and value > 0}

    def costs(after):
        return trading_cost(before, after, adv, cfg, stress=stress, nav_krw=nav_krw)

    def solve_nav(make_after):
        lo, hi = 0.0, 1.0
        for _ in range(64):
            mid = (lo + hi) / 2
            if mid + costs(make_after(mid))["costFraction"] > 1:
                hi = mid
            else:
                lo = mid
        return lo

    def sells(k):
        return {t: w - min(max(w - desired.get(t, 0) * k, 0), limits.get(t, 0))
                for t, w in before.items()}

    sell_nav = solve_nav(sells)
    after_sells = sells(sell_nav)
    actual_post_sell_gross = sum(after_sells.values()) / sell_nav
    available_new_buy_gross = max(0.0, multiplier - actual_post_sell_gross)
    allowed = limit_new_positions(after_sells, {t: 1.0 for t in desired if t in limits}, selected, cfg["maximumHoldings"])

    def bought(k, fraction):
        after = dict(after_sells)
        for t in allowed:
            buy = min(max(desired[t] * k - after_sells.get(t, 0), 0), limits[t]) * fraction
            after[t] = after.get(t, 0) + buy
        return after

    def attempt(fraction):
        k = solve_nav(lambda value: bought(value, fraction))
        after = bought(k, fraction)
        # Costs are paid from actual cash; never renormalize unfunded holdings.
        feasible = sum(after.values()) <= k and sum(after.values()) <= multiplier * k
        return k, after, feasible

    fraction = 0.0
    if available_new_buy_gross > 0 and allowed:
        if attempt(1.0)[2]:
            fraction = 1.0
        else:
            lo, hi = 0.0, 1.0
            for _ in range(64):
                mid = (lo + hi) / 2
                if attempt(mid)[2]:
                    lo = mid
                else:
                    hi = mid
            fraction = lo
    k, after, _ = attempt(fraction)
    cost_info = costs(after)
    cash = k - sum(after.values())
    if cash < -1e-12 or k <= 0:
        raise ValueError("UNFUNDED_TRANSACTION_COSTS")
    weights = {t: amount / k for t, amount in sorted(after.items()) if amount > 0}
    gross = sum(weights.values())
    excess = max(0.0, gross - multiplier)
    deferred = any(after_sells[t] > desired.get(t, 0) * sell_nav + 1e-12 for t in before)
    if excess > 1e-10 and not deferred:
        raise ValueError("UNEXPLAINED_OVERLAY_EXCESS")
    return {"weights": weights, "holdingAmounts": after, "cashAmount": max(0.0, cash),
            "cashWeight": max(0.0, cash) / k, "postCostNavFactor": k, **cost_info,
            "overlayTargetGross": multiplier, "actualPostSellGross": actual_post_sell_gross,
            "availableNewBuyGross": available_new_buy_gross, "realizedGross": gross,
            "overlayConstraintBinding": gross >= multiplier - 1e-10 or fraction < 1,
            "overlayExcessDueToDeferredExit": excess if deferred else 0.0}
