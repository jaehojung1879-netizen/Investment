"""Stage 1 label census for P1 -- the first-passage event, fixed BEFORE it is counted. Reads no signal.

Candidate primary label (fixed in this file before the census was run, and not compared with any alternative):

* index      SPY total return: split-adjusted raw close plus SSGA issuer distributions, XNYS sessions.
* drawdown   DD_t = TR_t / max(TR_s, s <= t) - 1, using only the running peak known at t.
* episode    starts at the first session u with DD_u <= -15% while no episode is active; ends at the first later
             session whose TR regains the running peak recorded at the episode start (full recovery). A new episode
             can start only after that.
* risk set   sessions with no active episode (so DD_t > -15%); sessions inside an episode are excluded.
* label      Y_t = 1 if an episode starts in (t, t + 126 sessions]; right-censored (None) when fewer than 126
             sessions remain and no start was seen.

The census counts episodes, risk-set observations and labelled months. It relates no signal to any label: P1's power
depends on these counts, and they are a property of the market path alone. Thresholds other than -15% and horizons
other than 126 sessions are not computed here.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
THRESHOLD, HORIZON = -0.15, 126


def load_tr() -> tuple[list[str], np.ndarray]:
    chart = json.loads(gzip.decompress((HERE / "data/raw/yahoo-SPY-chart-20261110.json.gz").read_bytes()))
    r = chart["chart"]["result"][0]
    import datetime as dt
    day = lambda ts: dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()  # noqa: E731
    closes = {day(t): c for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c is not None}
    divs = {row["exDate"]: float(row["amount"]) for row in csv.DictReader((HERE / "data/ssga-SPY-distributions.csv").open())}
    dates = sorted(closes)
    level, out = 1.0, [1.0]
    for prev, cur in zip(dates, dates[1:]):
        level *= (closes[cur] + divs.get(cur, 0.0)) / closes[prev]
        out.append(level)
    return dates, np.array(out)


def episodes(dates: list[str], tr: np.ndarray, threshold: float = THRESHOLD) -> tuple[list[dict], np.ndarray]:
    """Episode list and an `active` mask (True on sessions inside an episode). Uses only the path up to each session
    for the start; the end is the later full recovery (a label-side fact, never a signal)."""
    peak = np.maximum.accumulate(tr)
    active = np.zeros(len(tr), dtype=bool)
    out, i = [], 0
    while i < len(tr):
        if tr[i] / peak[i] - 1 <= threshold:
            start_peak = peak[i]
            peak_idx = int(np.argmax(tr[: i + 1]))
            j = i
            while j < len(tr) and tr[j] < start_peak:
                j += 1
            trough = i + int(np.argmin(tr[i:j])) if j > i else i
            out.append({"start": dates[i], "priorPeak": dates[peak_idx], "trough": dates[trough],
                        "troughDrawdown": float(tr[trough] / start_peak - 1),
                        "recovered": dates[j] if j < len(tr) else None,
                        "sessionsPeakToStart": i - peak_idx})
            active[i:j] = True
            i = j
        else:
            i += 1
    return out, active


def labels(dates: list[str], active: np.ndarray, eps: list[dict], horizon: int = HORIZON) -> list[int | None]:
    starts = {e["start"] for e in eps}
    idx = [k for k, d in enumerate(dates) if d in starts]
    n = len(dates)
    out: list[int | None] = []
    for t in range(n):
        if active[t]:
            out.append(None)
            continue
        hit = any(t < k <= t + horizon for k in idx)
        out.append(1 if hit else (0 if t + horizon < n else None))
    return out


def month_ends(dates: list[str]) -> list[int]:
    last: dict[str, int] = {}
    for k, d in enumerate(dates):
        last[d[:7]] = k
    return [last[m] for m in sorted(last)]


def census(first: str | None = None) -> dict:
    dates, tr = load_tr()
    eps, active = episodes(dates, tr)
    y = labels(dates, active, eps)
    keep = [k for k, d in enumerate(dates) if first is None or d >= first]
    me = [k for k in month_ends(dates) if k in set(keep)]
    eps_in = [e for e in eps if first is None or e["start"] >= first]
    daily_risk = [k for k in keep if y[k] is not None or not active[k]]
    return {
        "window": [dates[keep[0]], dates[keep[-1]]],
        "episodes": eps_in, "independentEpisodes": len(eps_in),
        "dailyRiskSet": sum(1 for k in keep if not active[k]),
        "dailyLabelled": sum(1 for k in keep if y[k] is not None),
        "dailyPositive": sum(1 for k in keep if y[k] == 1),
        "monthEndRiskSet": sum(1 for k in me if not active[k]),
        "monthEndLabelled": sum(1 for k in me if y[k] is not None),
        "monthEndPositive": sum(1 for k in me if y[k] == 1),
        "monthEndCensored": sum(1 for k in me if not active[k] and y[k] is None),
        "unusedDailyRiskSessions": len(daily_risk) - sum(1 for k in keep if y[k] is not None),
    }


# ------------------------------------------------------------------ power (assumption-driven, no signal read)


def binom_tail(n: int, k: int, p: float) -> float:
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def episode_power(k_episodes: int, alarm_budget: float, hit_probs: tuple[float, ...], alpha: float = 0.05) -> dict:
    """Episode-level test: under H0 a warning is on before an episode onset with probability = its unconditional
    alarm share (budget); the critical count k* is the smallest with P(Bin(K, budget) >= k*) <= alpha."""
    k_star = next((k for k in range(k_episodes + 1) if binom_tail(k_episodes, k, alarm_budget) <= alpha), None)
    return {"episodes": k_episodes, "alarmBudget": alarm_budget, "criticalHits": k_star,
            "sizeAtCritical": None if k_star is None else binom_tail(k_episodes, k_star, alarm_budget),
            "power": {str(p): (None if k_star is None else binom_tail(k_episodes, k_star, p)) for p in hit_probs}}


def main() -> int:
    report = {"stage": "STAGE_1_LABEL_CENSUS", "label": {"threshold": THRESHOLD, "horizonSessions": HORIZON,
                                                         "episodeEnd": "full recovery of the start peak"},
              "signalReads": 0, "full": census(), "pitCreditWindow": census("1997-01-31")}
    k = report["pitCreditWindow"]["independentEpisodes"]
    report["power"] = {f"budget_{b}": episode_power(k, b, (0.5, 0.7, 0.9)) for b in (0.1, 0.2, 0.3)}
    out = HERE / "evidence" / "label-census.json"
    out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({key: {kk: vv for kk, vv in v.items() if kk != "episodes"} if isinstance(v, dict) and "episodes" in v else v
                      for key, v in report.items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
