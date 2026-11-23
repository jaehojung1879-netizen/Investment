"""Stage 2 readiness: outcome-free facts the frozen P1 design depends on. NO credit value meets any label here.

Each block states which side it reads:

1. structure (label definedness + episode calendar + flag DEFINEDNESS via the presence proxy): evaluation start, rows,
   positives and episodes, per-year training/evaluation counts.
2. flag persistence (credit values only): rate, lag-1 autocorrelation, spell lengths.
3. opportunity-aware event null (credit values + FAST mask + calendar, NO label): for every hypothetical episode start
   s, the FAST-normal common-sample decisions in the 126 sessions before s and whether any was flagged -> P0(hit | n).
   Combined with each evaluation episode's opportunity count (label side, no credit) into the null hit distribution,
   and compared with the Stage 1 binomial that treated the monthly alarm rate as a per-episode hit probability.
4. basis checks (price and total return only, no credit): FAST on price vs total return at month-ends; episode
   starts on total return vs price.

    python -m research.market_risk_discovery_v1.stage2_readiness
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from . import baseline_census as B
from . import label_census as L
from . import panels as P
from . import stage2_design as D

HERE = Path(__file__).resolve().parent


def structure() -> dict:
    c = P.common_rows("presence")
    p = D.Panel(c["rows"])
    refits = D.refit_points(c["monthEnds"])
    gate = D.structure_gate(p, refits, c["flagSequence"])
    years = {}
    for y in sorted(refits):
        if y < 1998:
            continue
        tr = D.matured_mask(p, refits[y])
        ev = p.labelled & (p.year >= y)
        years[str(y)] = {"trainRows": int(tr.sum()), "trainPositives": int(np.nansum(p.y[tr])),
                         "trainEpisodes": len({e for e in p.episode[tr & (p.y == 1)]}),
                         "evalRowsIfStartHere": int(ev.sum()),
                         "evalEpisodesIfStartHere": len({e for e in p.episode[ev & (p.y == 1)]})}
    ev = D.evaluation_mask(p, gate["start"])
    opp = {e: int(np.sum(ev & (p.episode == e))) for e in gate["evaluationEpisodes"]}
    all_opp = {e: int(np.sum(p.labelled & (p.episode == e))) for e in sorted({e for e in p.episode if e})}
    return {"gate": gate, "commonSampleRows": len(p.rows), "labelledRows": int(p.labelled.sum()),
            "censoredRows": int((~p.labelled).sum()), "positives": int(np.nansum(p.y)),
            "definedFlagMonths": len(c["flagSequence"]), "firstDefinedFlagSession": c["flagSequence"][0][0],
            "byRefitYear": years, "evaluationOpportunities": opp, "allEpisodeOpportunities": all_opp,
            "lastSession": c["lastSession"]}


def flag_persistence() -> dict:
    v = np.array([x for _, x in P.credit_side()])
    spells, run = [], 0
    for x in v:
        if x:
            run += 1
        elif run:
            spells.append(run)
            run = 0
    if run:
        spells.append(run)
    return {"months": int(len(v)), "rate": float(v.mean()), "lag1Autocorrelation": float(np.corrcoef(v[1:], v[:-1])[0, 1]),
            "spells": len(spells), "meanSpell": float(np.mean(spells)), "maxSpell": int(max(spells))}


def opportunity_null(opportunities: dict[str, int]) -> dict:
    """P0(hit | n opportunities) from every hypothetical start session, using real flags on FAST-normal common-sample
    month-ends and the session calendar. Hypothetical starts within 126 sessions of a REAL episode start are skipped, so
    no window aligned with an actual episode is ever evaluated; risk-set membership is the PIT 'not in an episode'."""
    price = P.price_side()
    events = P.event_side()
    events_active = events["active"]
    real_starts = np.array(sorted(events["starts"].values()))
    dates = price["dates"]
    me = P.month_end_index(dates)
    flags = dict(P.credit_side())
    cand = sorted((k, flags[m]) for m, k in me.items()
                  if dates[k] >= P.FIRST_DECISION and not events_active[k] and price["fast"][k] == 0 and m in flags)
    idx = np.array([k for k, _ in cand])
    val = np.array([v for _, v in cand])
    by_n: dict[int, list[int]] = {}
    for s in range(int(idx.min()) + 1, len(dates)):
        if events_active[s] or np.any(np.abs(real_starts - s) <= D.HORIZON):
            continue   # never evaluate a window at (or overlapping) a real episode start
        m = (idx < s) & (idx >= s - D.HORIZON)
        n = int(m.sum())
        if n:
            by_n.setdefault(n, []).append(int(val[m].max() >= 0.5))
    p0 = {n: float(np.mean(h)) for n, h in sorted(by_n.items())}
    rate = float(val.mean())
    probs = [p0.get(n, 1 - (1 - rate) ** n) for n in opportunities.values()]
    dist = poisson_binomial(probs)
    k = len(probs)
    naive = [math.comb(k, h) * 0.1 ** h * 0.9 ** (k - h) for h in range(k + 1)]
    return {"flagRateOnFastNormalCommonSample": rate,
            "p0HitGivenOpportunities": {str(n): {"p0": p0[n], "startsObserved": len(by_n[n]),
                                                 "independentBernoulli": 1 - (1 - rate) ** n} for n in p0},
            "evaluationEpisodeNullHitProbability": dict(zip(opportunities, probs)),
            "nullHitDistribution": [float(x) for x in dist],
            "criticalHitsAt5pct": next((h for h in range(k + 1) if sum(dist[h:]) <= 0.05), None),
            "stage1BinomialP0_10Distribution": naive,
            "stage1BinomialCriticalHitsAt5pct": next((h for h in range(k + 1) if sum(naive[h:]) <= 0.05), None),
            "tailProbabilityOfStage1CriticalUnderOpportunityNull": (
                float(sum(dist[next(h for h in range(k + 1) if sum(naive[h:]) <= 0.05):])))}


def poisson_binomial(probs: list[float]) -> list[float]:
    dist = [1.0]
    for q in probs:
        nxt = [0.0] * (len(dist) + 1)
        for h, w in enumerate(dist):
            nxt[h] += w * (1 - q)
            nxt[h + 1] += w * q
        dist = nxt
    return dist


def basis_checks() -> dict:
    dates, tr = L.load_tr()
    _, close = B.raw_close()
    me = L.month_ends(dates)
    fast_px = B.fast_state(close)
    fast_tr = B.fast_state(tr)
    both = [k for k in me if fast_px[k] is not None and dates[k] >= P.FIRST_DECISION]
    flip = [dates[k] for k in both if (fast_px[k] == 0) != (fast_tr[k] == 0)]
    eps_tr, _ = L.episodes(dates, tr)
    eps_px, _ = L.episodes(dates, close)
    return {"fastPriceVsTotalReturn": {"monthEnds": len(both), "normalStateDisagreements": len(flip), "dates": flip},
            "episodesTotalReturn": [e["start"] for e in eps_tr], "episodesPrice": [e["start"] for e in eps_px]}


def main() -> int:
    s = structure()
    report = {"stage": "STAGE_2_READINESS", "creditLabelJoins": 0, "structure": s, "flagPersistence": flag_persistence(),
              "opportunityNull": opportunity_null(s["evaluationOpportunities"]), "basis": basis_checks()}
    (HERE / "evidence" / "stage2-readiness.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
