"""What the same machine produces when the ranking carries no information.

The portfolio replay has always compared the final book against its benchmark.
That comparison cannot answer the question the product actually rests on,
because a benchmark comparison bundles three different things together:

  1. universe carry — the research pool beating the index for reasons the
     ranking did not produce,
  2. the construction rules — concentration, sector and region caps, the
     entry-state multipliers, the regime cash floor,
  3. the ranking itself — which five names, in which order.

Only (3) is the model's stock-picking claim, and on the production ledger (1)
alone earns +1.1% to +2.4% per 126 days. A number that clears an absolute bar
on carry looks exactly like skill.

So this module builds the counterfactual that isolates (3): the same dates, the
same research pool, the same constraints, the same weighting function, the same
turnover costs — with the conviction ranking replaced by noise. Everything the
model does *except* choose is held fixed, so the gap between the real book and
the null distribution is what choosing was worth.

SCOPE, precisely. The research pool itself is produced by ``LT.select_names``
from the alpha score, so this null measures the marginal value of the final
ranking and concentration step *within* an already model-selected pool. It does
NOT test the research screen. A null that also randomized the pool would test
both, and is not implemented here — a report must not claim it did.

The p-value is the permutation form with the customary +1 in both terms, which
keeps it valid (never zero) at finite draw counts.
"""
from __future__ import annotations

import math

import numpy as np

NULL_METHOD = "RANDOM_RANK_WITHIN_RESEARCH_POOL"

BEATS = "BEATS_RANDOM"
WORSE = "WORSE_THAN_RANDOM"
INDISTINGUISHABLE = "INDISTINGUISHABLE_FROM_RANDOM"
NOT_ASSESSED = "NOT_ASSESSED"

DEFAULT_DRAWS = 200
DEFAULT_ALPHA = 0.05
# Below this the percentile is too coarse for the threshold to mean anything:
# with 20 draws the smallest attainable p-value is 1/21.
MIN_USABLE_DRAWS = 40


# The alpha floor removes a name because the SCORE said so, which is part of
# what "choosing" means — a null forced to respect it would only ever pick from
# names the alpha score already approved, and would not test the score at all.
# Every other exclusion is a data or entry-state fact about the name, true
# whatever the ranking says, so the null stays subject to it.
SCORE_DRIVEN_EXCLUSIONS = frozenset({"ALPHA_BELOW_SELECTION_FLOOR"})


def permuted_scores(scored: list[dict], rng: np.random.Generator) -> list[dict]:
    """The real conviction scores, reassigned to different names.

    A permutation rather than fresh noise, for two reasons. It preserves the
    distribution of score magnitudes, so the null book carries the same
    conviction-tilt and concentration profile the real one does — draws from a
    normal would produce a differently shaped book and the comparison would
    confound tilt with ordering. And it is the exact randomization the null
    hypothesis describes: the scores are real, only their attachment to names
    is destroyed.

    Selection sorts on ``(-score, ticker)``, so ties break alphabetically and no
    part of the real ordering leaks back in through a tie-break.
    """
    rows = []
    for row in scored:
        item = dict(row)
        codes = [code for code in (item.get("exclusionCodes") or [])
                 if code not in SCORE_DRIVEN_EXCLUSIONS]
        item["exclusionCodes"] = codes
        item["eligible"] = not codes
        rows.append(item)

    pool = [index for index, row in enumerate(rows) if row["eligible"]]
    values = [float(rows[index].get("convictionScore")
                    or rows[index].get("score") or 0.0) for index in pool]
    order = rng.permutation(len(values))
    for index, slot in zip(pool, order):
        rows[index]["convictionScore"] = values[int(slot)]
        rows[index]["score"] = values[int(slot)]
    return rows


def _finite(values) -> list[float]:
    # `values or []` would raise on a NumPy array — its truth value is ambiguous
    # — and callers pass arrays as often as lists.
    if values is None:
        return []
    out = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            out.append(number)
    return out


def summarize(actual, null_values, *, higher_is_better: bool = True,
              alpha: float = DEFAULT_ALPHA, label: str | None = None) -> dict:
    """Where the real statistic sits inside the distribution luck produces."""
    values = _finite(null_values)
    try:
        observed = float(actual)
        observed = observed if math.isfinite(observed) else None
    except (TypeError, ValueError):
        observed = None

    if observed is None or len(values) < MIN_USABLE_DRAWS:
        return {
            "statistic": label,
            "actual": observed,
            "draws": len(values),
            "verdict": NOT_ASSESSED,
            "reason": ("statistic_unavailable" if observed is None
                       else f"insufficient_draws_{len(values)}/{MIN_USABLE_DRAWS}"),
        }

    array = np.asarray(values, dtype=float)
    n = int(array.size)
    # One-sided permutation p-values in both directions, +1 corrected.
    better = array >= observed if higher_is_better else array <= observed
    worse = array <= observed if higher_is_better else array >= observed
    p_beats = float((int(better.sum()) + 1) / (n + 1))
    p_worse = float((int(worse.sum()) + 1) / (n + 1))

    if p_beats <= alpha:
        verdict = BEATS
    elif p_worse <= alpha:
        verdict = WORSE
    else:
        verdict = INDISTINGUISHABLE

    percentile = float((array < observed).mean() * 100) if higher_is_better \
        else float((array > observed).mean() * 100)
    return {
        "statistic": label,
        "actual": round(observed, 4),
        "nullMean": round(float(array.mean()), 4),
        "nullSd": round(float(array.std(ddof=1)), 4) if n > 1 else None,
        "nullP05": round(float(np.percentile(array, 5)), 4),
        "nullP50": round(float(np.percentile(array, 50)), 4),
        "nullP95": round(float(np.percentile(array, 95)), 4),
        "percentileOfNull": round(percentile, 2),
        "pValueBeatsRandom": round(p_beats, 4),
        "pValueWorseThanRandom": round(p_worse, 4),
        "alpha": float(alpha),
        "draws": n,
        "higherIsBetter": bool(higher_is_better),
        "verdict": verdict,
    }


def overall_verdict(statistics: dict) -> dict:
    """One reading across the statistics tested.

    Deliberately conservative in both directions. A book has to clear the null
    on a RISK-ADJUSTED statistic to be called an edge — beating it on raw excess
    while sitting inside the null on information ratio means the extra return
    was bought with extra risk, which is not what a concentrated book is for.
    """
    assessed = {name: row for name, row in statistics.items()
                if row.get("verdict") != NOT_ASSESSED}
    if not assessed:
        return {"verdict": NOT_ASSESSED, "reason": "no_statistic_could_be_assessed",
                "assessed": [], "risk_adjusted_required": True}
    risk_adjusted = [name for name in ("informationRatio", "sharpe") if name in assessed]
    beats = [name for name, row in assessed.items() if row["verdict"] == BEATS]
    worse = [name for name, row in assessed.items() if row["verdict"] == WORSE]

    if risk_adjusted and all(assessed[name]["verdict"] == BEATS for name in risk_adjusted):
        verdict = BEATS
    elif worse and not beats:
        verdict = WORSE
    else:
        verdict = INDISTINGUISHABLE
    return {
        "verdict": verdict,
        "assessed": sorted(assessed),
        "beatsRandomOn": sorted(beats),
        "worseThanRandomOn": sorted(worse),
        "riskAdjustedStatistics": risk_adjusted,
        "riskAdjustedRequired": True,
        "scope": NULL_METHOD,
        "scopeNoteKo": ("이 검정은 연구 후보군 안에서의 '순위·집중' 단계만 검증합니다. "
                        "후보군 자체가 alpha 점수로 걸러지므로, 연구 스크리닝의 기여는 "
                        "여기서 측정되지 않습니다."),
    }
