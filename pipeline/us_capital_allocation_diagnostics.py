"""Outcome-blind diagnostics of the registered US capital-allocation rule (and of its future receipts).

Everything here is a function of DECISIONS and FEATURE VALUES as of each signal date. No return, price level, label, NAV or
forward observation is read, and no threshold is varied: the registered v1 rule is described, never tuned. A count such as
"five names selected" says how the rule behaves; it says nothing about whether the names will outperform.

Two layers:

* `decision_diagnostics(decisions)` takes `[(signal_date, decision)]`, where `decision` is `us_capital_allocation_policy.select`'s
  output or a receipt's `decision` block, so the SAME measures describe the historical counterfactual weeks and the future
  prospective receipts (participation, turnover, persistence, concentration, sector exposure).
* `score_construction(weeks)` takes the per-week measured rows and shows how much of the rule's abundance is the score's
  construction (a payout-growth hurdle near the cross-sectional median, a common payout cycle, a small prior base) rather than
  anything that distinguishes a name's expected return.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from pipeline import us_capital_allocation_policy as P

NEAR_FIFTH = 0.10                 # "within 10% of the fifth score" is a descriptive closeness band, not a threshold of the rule
SMALL_BASE_OCF = 0.02             # prior-year distribution below 2% of OCF: a payout that barely existed (descriptive)
HIGH_PAYOUT = 0.80                # distribution above 80% of OCF: little cash cushion left (descriptive)
EARNINGS_MONTHS = {1: "Q4-10K", 2: "Q4-10K", 3: "Q4-10K", 4: "Q1-10Q", 5: "Q1-10Q", 6: "Q1-10Q", 7: "Q2-10Q", 8: "Q2-10Q",
                   9: "Q2-10Q", 10: "Q3-10Q", 11: "Q3-10Q", 12: "Q3-10Q"}


def _q(values, qs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    if not len(values):
        return None
    a = np.asarray(values, dtype=float)
    return {"n": int(len(a)), "min": round(float(a.min()), 6), **{"p%d" % round(q * 100): round(float(np.quantile(a, q)), 6) for q in qs},
            "max": round(float(a.max()), 6), "mean": round(float(a.mean()), 6)}


def _stats(values):
    if not len(values):
        return None
    a = np.asarray(values, dtype=float)
    return {"min": round(float(a.min()), 4), "median": round(float(np.median(a)), 4), "mean": round(float(a.mean()), 4), "max": round(float(a.max()), 4)}


def _spells(flags):
    """Run lengths of consecutive True values."""
    out, run = [], 0
    for f in flags:
        if f:
            run += 1
        elif run:
            out.append(run)
            run = 0
    if run:
        out.append(run)
    return out


def _hhi(counter):
    total = sum(counter.values())
    return round(sum((v / total) ** 2 for v in counter.values()), 6) if total else None


def _gini(values):
    a = np.sort(np.asarray(values, dtype=float))
    if not len(a) or a.sum() == 0:
        return None
    n = len(a)
    return round(float((2 * np.arange(1, n + 1) - n - 1).dot(a) / (n * a.sum())), 4)


# --------------------------------------------------------------------------- #
# Layer 1: decisions (historical counterfactual weeks and future receipts alike)
# --------------------------------------------------------------------------- #
def decision_diagnostics(decisions, *, include_names: bool = False) -> dict:
    """`decisions`: iterable of (signal_date 'YYYY-MM-DD', decision dict). Order is irrelevant; it is sorted by date.

    Names are omitted by default so that a published historical summary cannot be turned into a return backtest by a reader; the
    prospective receipts, which are not historical counterfactuals, can ask for them."""
    rows = sorted(decisions, key=lambda x: x[0])
    if not rows:
        return {"weeks": 0}
    status = Counter(d["status"] for _, d in rows)
    live = [(day, d) for day, d in rows if d["status"] != "BLOCKED"]
    sizes = Counter(len(d["selected"]) for _, d in live)
    selected = [(day, [s["ticker"] for s in d["selected"]]) for day, d in live]
    slot_weeks = Counter(t for _, names in selected for t in names)
    sector_slots = Counter(s["sector"] for _, d in live for s in d["selected"])
    total_slots = sum(slot_weeks.values())

    # Week-to-week change of the held set, over consecutive OBSERVED non-blocked weeks only (a blocked gap is not a "change").
    changes, unchanged, replaced = [], 0, []
    by_year_change = defaultdict(list)
    by_season = defaultdict(list)
    for (d0, a), (d1, b) in zip(selected, selected[1:]):
        if (np.datetime64(d1) - np.datetime64(d0)).astype(int) > 10:
            continue
        sa, sb = set(a), set(b)
        base = max(len(sa), len(sb), 1)
        frac = 1.0 - len(sa & sb) / base
        changes.append(frac)
        unchanged += frac == 0.0
        replaced.append(len(sb - sa))
        by_year_change[d1[:4]].append(frac)
        by_season[EARNINGS_MONTHS[int(d1[5:7])]].append(frac)

    # A name's consecutive-week holding spells.
    names = sorted(slot_weeks)
    held = {t: [t in set(n) for _, n in selected] for t in names}
    spell_lengths = [s for t in names for s in _spells(held[t])]
    skipped_weeks = sum(1 for _, d in live if d.get("skippedForSectorCap"))
    return {
        "weeks": len(rows), "status": dict(sorted(status.items())), "blockedShare": round(status.get("BLOCKED", 0) / len(rows), 4),
        "participation": {"nonBlockedWeeks": len(live), "weeksWithAtLeastOneName": sum(1 for _, d in live if d["selected"]),
                          "participationRate": round(sum(1 for _, d in live if d["selected"]) / len(live), 4) if live else None,
                          "weeksWithFullFiveNames": sum(1 for _, d in live if len(d["selected"]) == P.MAX_NAMES),
                          "namesPerWeek": {str(k): v for k, v in sorted(sizes.items())}},
        "distinctNames": {"everSelected": len(slot_weeks), "slotWeeks": total_slots,
                          "top10ShareOfSlotWeeks": round(sum(v for _, v in slot_weeks.most_common(10)) / total_slots, 4) if total_slots else None,
                          "largestSingleNameShare": round(slot_weeks.most_common(1)[0][1] / total_slots, 4) if total_slots else None,
                          "herfindahlOfSlotWeeks": _hhi(slot_weeks), "giniOfSlotWeeks": _gini(list(slot_weeks.values())),
                          "topTenShares": [round(v / total_slots, 4) for _, v in slot_weeks.most_common(10)] if total_slots else [],
                          **({"mostFrequent": [[t, v] for t, v in slot_weeks.most_common(10)]} if include_names else {})},
        "sectorExposure": {s: round(v / total_slots, 4) for s, v in sorted(sector_slots.items(), key=lambda kv: -kv[1])} if total_slots else {},
        "turnover": {"consecutiveWeekPairs": len(changes), "meanFractionReplaced": round(float(np.mean(changes)), 4) if changes else None,
                     "weeksWithUnchangedSet": int(unchanged), "shareUnchanged": round(unchanged / len(changes), 4) if changes else None,
                     "meanNamesReplaced": round(float(np.mean(replaced)), 4) if replaced else None,
                     "byYear": {y: round(float(np.mean(v)), 4) for y, v in sorted(by_year_change.items())},
                     "byFilingSeason": {s: {"pairs": len(v), "meanFractionReplaced": round(float(np.mean(v)), 4)} for s, v in sorted(by_season.items())}},
        "persistence": {"holdingSpellsWeeks": _q(spell_lengths), "spells": len(spell_lengths)},
        "sectorCap": {"weeksWhereCapSkippedAName": skipped_weeks, "share": round(skipped_weeks / len(live), 4) if live else None},
    }


def margins(decisions) -> dict:
    """How close the fifth selected score is to the first and to the first excluded passer. Descriptive only."""
    s1, s5, s6, ratio, gap, near, short = [], [], [], [], [], [], 0
    for _, d in decisions:
        if d["status"] == "BLOCKED":
            continue
        picked = [s["score"] for s in d["selected"]]
        if len(picked) < P.MAX_NAMES:
            short += 1
            continue
        fifth = picked[-1]
        s1.append(picked[0])
        s5.append(fifth)
        ratio.append(fifth / picked[0])
        excluded = [p["score"] for p in d["passers"] if p["ticker"] not in {s["ticker"] for s in d["selected"]}]
        if excluded:
            s6.append(max(excluded))
            gap.append((fifth - max(excluded)) / fifth)
        near.append(sum(1 for x in excluded if x >= fifth * (1 - NEAR_FIFTH)))
    return {"weeksWithFiveSelected": len(s5), "weeksWithFewerThanFive": short,
            "scoreOfFirst": _q(s1), "scoreOfFifth": _q(s5), "scoreOfBestExcludedPasser": _q(s6),
            "fifthOverFirst": _q(ratio), "relativeGapFifthToBestExcluded": _q(gap),
            "excludedPassersWithin10PctOfFifth": _stats(near),
            "reading": "a small gap between the fifth and the best excluded name means the cut-off is arbitrary: the fifth slot is filled by a coin-toss-sized difference in an accounting ratio"}


# --------------------------------------------------------------------------- #
# Layer 2: measured rows -> where the abundance comes from
# --------------------------------------------------------------------------- #
def _spearman(x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(x) < 5 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return round(float(np.corrcoef(rx, ry)[0, 1]), 4)


def score_construction(weeks) -> dict:
    """`weeks`: [{'date', 'decision', 'rows': [measured row dicts]}]. A measured row has
    ticker, sector, gate, score, growth, ratio, distribution, ocf, dividends, repurchases (the last two may be None)."""
    by_year = defaultdict(lambda: {"measured": 0, "growthGate": 0, "scoreGate": 0, "coverGate": 0, "passed": 0})
    growth_all, ratio_all, score_p, ratio_p, growth_p = [], [], [], [], []
    base_small, high_payout, buyback_led, dividend_led, mixed, comp_known = 0, 0, 0, 0, 0, 0
    passers_total = 0
    year_pass_rate = defaultdict(list)
    for w in weeks:
        rows = w["rows"]
        if not rows:
            continue
        year = w["date"][:4]
        passed_week = 0
        for r in rows:
            y = by_year[year]
            y["measured"] += 1
            growth_all.append(r["growth"])
            ratio_all.append(r["ratio"])
            if r["growth"] >= P.MIN_DISTRIBUTION_GROWTH:
                y["growthGate"] += 1
                if r["score"] is not None and r["score"] >= P.MIN_INCREMENTAL_OVER_OCF:
                    y["scoreGate"] += 1
                    if r["ratio"] <= P.MAX_DISTRIBUTION_TO_OCF:
                        y["coverGate"] += 1
            if r["gate"] is None:
                y["passed"] += 1
                passed_week += 1
                passers_total += 1
                score_p.append(r["score"])
                ratio_p.append(r["ratio"])
                growth_p.append(r["growth"])
                prior = r["distribution"] / (1.0 + r["growth"])
                base_small += prior / r["ocf"] < SMALL_BASE_OCF
                high_payout += r["ratio"] > HIGH_PAYOUT
                if r.get("dividends") is not None and r.get("repurchases") is not None and r.get("dividendYoY") is not None \
                        and r.get("repurchaseYoY") is not None:
                    comp_known += 1
                    d_div = r["dividends"] - r["dividends"] / (1.0 + r["dividendYoY"]) if r["dividendYoY"] > -1 else r["dividends"]
                    d_rep = r["repurchases"] - r["repurchases"] / (1.0 + r["repurchaseYoY"]) if r["repurchaseYoY"] > -1 else r["repurchases"]
                    if d_rep > 0 and d_rep > 2 * max(d_div, 0.0):
                        buyback_led += 1
                    elif d_div > 0 and d_div > 2 * max(d_rep, 0.0):
                        dividend_led += 1
                    else:
                        mixed += 1
        year_pass_rate[year].append(passed_week / len(rows))
    totals = {k: sum(v[k] for v in by_year.values()) for k in ("measured", "growthGate", "scoreGate", "coverGate", "passed")}
    yearly = {y: {**v, "passShareOfMeasured": round(v["passed"] / v["measured"], 4) if v["measured"] else None}
              for y, v in sorted(by_year.items())}
    shares = [v["passShareOfMeasured"] for v in yearly.values() if v["passShareOfMeasured"] is not None]
    within = [float(np.std(v)) for v in year_pass_rate.values() if len(v) > 5]
    return {
        "measuredNameWeeks": totals["measured"],
        "conditionalPass": {"growthAtLeastHurdle": round(totals["growthGate"] / totals["measured"], 4) if totals["measured"] else None,
                            "scoreAtLeastHurdleGivenGrowth": round(totals["scoreGate"] / totals["growthGate"], 4) if totals["growthGate"] else None,
                            "coverageGivenScore": round(totals["coverGate"] / totals["scoreGate"], 4) if totals["scoreGate"] else None,
                            "passedEveryGateOfMeasured": round(totals["passed"] / totals["measured"], 4) if totals["measured"] else None},
        "distributionGrowthAmongMeasured": _q(growth_all), "distributionToOCFAmongMeasured": _q(ratio_all),
        "hurdleVersusMedianGrowth": {
            "registeredHurdle": P.MIN_DISTRIBUTION_GROWTH,
            "medianGrowthAmongMeasured": round(float(np.median(growth_all)), 4) if growth_all else None,
            "shareOfMeasuredAtOrAboveHurdle": round(float(np.mean(np.asarray(growth_all) >= P.MIN_DISTRIBUTION_GROWTH)), 4) if growth_all else None,
            "reading": "a hurdle that a large minority of measured name-weeks clear is a coarse filter, not a rare event; the share is stated, not interpreted as selectivity"},
        "byYear": yearly,
        "commonFactor": {"yearlyPassShareRange": [min(shares), max(shares)] if shares else None,
                         "betweenYearSpread": round(float(np.std(shares)), 4) if shares else None,
                         "meanWithinYearWeeklySpread": round(float(np.mean(within)), 4) if within else None,
                         "betweenOverWithin": round(float(np.std(shares)) / float(np.mean(within)), 3) if shares and within and np.mean(within) > 0 else None,
                         "reading": "the share of measured names that pass moves by year (a payout cycle) about as much as it moves by week; the yearly range is stated so a reader can see how much of the rule's abundance is the aggregate payout cycle"},
        "passers": {"nameWeeks": passers_total, "scoreQuantiles": _q(score_p),
                    "spearmanScoreVsPayoutRatio": _spearman(score_p, ratio_p), "spearmanScoreVsGrowth": _spearman(score_p, growth_p),
                    "priorYearDistributionBelow2PctOfOCF": round(base_small / passers_total, 4) if passers_total else None,
                    "distributionAbove80PctOfOCF": round(high_payout / passers_total, 4) if passers_total else None,
                    "increaseComposition": {"nameWeeksWithBothComponents": comp_known,
                                            "repurchaseLed": round(buyback_led / comp_known, 4) if comp_known else None,
                                            "dividendLed": round(dividend_led / comp_known, 4) if comp_known else None,
                                            "mixed": round(mixed / comp_known, 4) if comp_known else None}},
    }


def selected_composition(weeks) -> dict:
    """Of the SELECTED slots specifically (not all passers): payout level, small prior base, buyback-led increases.
    Each week carries its own `decision`."""
    chosen = {(w["date"], s["ticker"]) for w in weeks for s in w["decision"]["selected"]}
    n = small = high = rep = div = known = 0
    for w in weeks:
        for r in w["rows"]:
            if (w["date"], r["ticker"]) not in chosen:
                continue
            n += 1
            small += r["distribution"] / (1.0 + r["growth"]) / r["ocf"] < SMALL_BASE_OCF
            high += r["ratio"] > HIGH_PAYOUT
            if None not in (r.get("dividends"), r.get("repurchases"), r.get("dividendYoY"), r.get("repurchaseYoY")):
                known += 1
                d_div = r["dividends"] - r["dividends"] / (1.0 + r["dividendYoY"]) if r["dividendYoY"] > -1 else r["dividends"]
                d_rep = r["repurchases"] - r["repurchases"] / (1.0 + r["repurchaseYoY"]) if r["repurchaseYoY"] > -1 else r["repurchases"]
                rep += d_rep > 2 * max(d_div, 0.0) and d_rep > 0
                div += d_div > 2 * max(d_rep, 0.0) and d_div > 0
    return {"selectedSlotWeeks": n,
            "priorYearDistributionBelow2PctOfOCF": round(small / n, 4) if n else None,
            "distributionAbove80PctOfOCF": round(high / n, 4) if n else None,
            "repurchaseLed": round(rep / known, 4) if known else None, "dividendLed": round(div / known, 4) if known else None,
            "compositionKnownSlotWeeks": known}


def passer_persistence(weeks) -> dict:
    """How long a name keeps passing the gates (not only being selected): the signal updates with filings, not with weeks."""
    names = sorted({r["ticker"] for w in weeks for r in w["rows"] if r["gate"] is None})
    index = [{r["ticker"] for r in w["rows"] if r["gate"] is None} for w in weeks]
    spells = [s for t in names for s in _spells([t in week for week in index])]
    return {"distinctPassingNames": len(names), "passingSpellsWeeks": _q(spells), "spells": len(spells),
            "reading": "median spell length near one filing cycle (about 13 weeks) means the weekly series is a quarterly signal repeated, so consecutive weeks are not independent evidence"}


def explainer() -> dict:
    return {
        "A_accountingCharacteristic": "A company's total cash distribution grew by at least 10% over the prior year, the increase is at least 2% of operating cash "
                                      "flow, and total distributions do not exceed operating cash flow. This is a statement about reported cash flows.",
        "B_expectedReturnAdvantage": "A demonstrably positive expected return advantage over SPY or QQQ after costs. It requires evidence that the characteristic "
                                     "is not already in the price, which only out-of-sample outcomes can supply. None exists for this rule.",
        "verdict": "The v1 rule selects on A. Nothing in its construction measures B. The score ranks companies by the size of a payout increase relative to cash flow; "
                   "it contains no forecast, no price, no valuation and no estimate of how much of the increase is already priced.",
    }
