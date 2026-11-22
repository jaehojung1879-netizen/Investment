"""Build the US decision-date signal ledger and policy-target readiness from preserved inputs. Outcome-free.

Reads only: the pinned Shiller extract (P, E), the ALFRED as-of ledgers (BAA, GS10) and SPY's RAW close for the
drawdown signal. It never reads a total-return close, never computes a forward or realised return, and writes no
weight-to-return product. What it reports is what the frozen rules WOULD have said at each decision date and how
often each state occurs: the same outcome-free readiness the sealed market-risk model published before execution.

Usage::

    python -m research.market_valuation_macro_overlay_v1.build_signals --data-dir data/research/mvma-v1 \
        --out research/market_valuation_macro_overlay_v1/evidence/us-signal-readiness.json
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import sys
from collections import Counter
from pathlib import Path

from . import features as F
from . import signals as S

REPO = Path(__file__).resolve().parents[2]
SHILLER_FILE = "shiller-monthly-20240904.csv"
SPY_FILE = REPO / "data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz"
WINDOW_FIRST, WINDOW_LAST = "2012-01", "2024-08"


def load_shiller(path: Path) -> tuple[dict, dict]:
    prices, earnings = {}, {}
    for row in csv.DictReader(path.open()):
        if row["partialMonth"] == "1":
            continue
        if row["P"]:
            prices[row["month"]] = float(row["P"])
        if row["E"]:
            earnings[row["month"]] = float(row["E"])
    return prices, earnings


def load_asof(path: Path) -> dict[str, tuple[str | None, float | None]]:
    out = {}
    for row in csv.DictReader(path.open()):
        ok = row["status"] == "VINTAGE_SERVED" and row["value"] not in ("", "None")
        out[row["decisionDate"]] = (row["observationDate"] if ok else None, float(row["value"]) if ok else None)
    return out


def load_spy_raw_close(path: Path = SPY_FILE) -> tuple[list[str], list[float]]:
    """SPY raw close only: the column index is looked up and `totalReturn*` columns are never touched."""
    dates, closes = [], []
    with gzip.open(path, "rt") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        t, d, c = header.index("ticker"), header.index("date"), header.index("rawClose")
        for row in reader:
            if row[t] == "SPY":
                dates.append(row[d])
                closes.append(float(row[c]))
    return dates, closes


def month_key(iso: str) -> str:
    return iso[:7]


def build(data_dir: Path, spy_path: Path = SPY_FILE) -> dict:
    prices, earnings = load_shiller(data_dir / SHILLER_FILE)
    baa = load_asof(data_dir / "alfred-BAA-asof-decisions.csv")
    gs10 = load_asof(data_dir / "alfred-GS10-asof-decisions.csv")
    decisions = sorted(baa)
    spy_dates, spy_close = load_spy_raw_close(spy_path)
    spy_index = {d: i for i, d in enumerate(spy_dates)}

    pe, eps, spread, rows = [], [], [], []
    mismatched_months = 0
    for d in decisions:
        y, m = int(d[:4]), int(d[5:7])
        q = F.shiller_earnings_effective_month(F.month_index(y, m))
        qy, qm = F.month_from_index(q)
        e = earnings.get(f"{qy:04d}-{qm:02d}")
        p = prices.get(month_key(d))
        pe.append(F.price_to_earnings(p, e))
        eps.append(e)
        (b_obs, b_val), (g_obs, g_val) = baa[d], gs10[d]
        if b_val is not None and g_val is not None and b_obs == g_obs:
            spread.append(b_val - g_val)
        else:
            if b_val is not None and g_val is not None:
                mismatched_months += 1
            spread.append(None)
        rows.append({"decisionDate": d, "shillerPriceMonth": month_key(d), "shillerEarningsQuarter": f"{qy:04d}-{qm:02d}",
                     "baaObservation": b_obs, "gs10Observation": g_obs})

    for i, row in enumerate(rows):
        si = spy_index.get(row["decisionDate"])
        row.update({
            "pe": pe[i], "pe5": F.trailing_mean_prior(pe, i), "discount": F.valuation_discount(pe, i),
            "cheap": F.valuation_cheap(pe, i), "eps": eps[i], "earningsStable": F.earnings_stable(eps, i),
            "spread": spread[i], "creditStress": F.credit_stress(spread, i),
            "drawdown": None if si is None else F.drawdown_from_high(spy_close, si),
            "deepDrawdown": None if si is None else F.deep_drawdown(spy_close, si),
            "spySessionFound": si is not None,
        })

    window = [r for r in rows if WINDOW_FIRST <= month_key(r["decisionDate"]) <= WINDOW_LAST]
    policies = {}
    for name, rule in (("V1", "V1"), ("M1T", "M1"), ("VM1T", "VM1"), ("D1", "D1")):
        path = S.target_path(rule, window)
        for r, w in zip(window, path["targets"]):
            r["target" + name] = w
        policies[name] = {"holds": path["holds"], "firstDetermined": path["firstDetermined"],
                          "targetCounts": dict(sorted(Counter(path["targets"]).items())),
                          "meanTarget": round(sum(path["targets"]) / len(path["targets"]), 4)}

    def count(key):
        return dict(Counter("MISSING" if r[key] is None else str(r[key]) for r in window))

    two_by_two = Counter()
    for r in window:
        if r["cheap"] is None or r["earningsStable"] is None or r["creditStress"] is None:
            two_by_two["UNDETERMINED"] += 1
            continue
        good = r["earningsStable"] and not r["creditStress"]
        bad = (not r["earningsStable"]) and r["creditStress"]
        env = "GOOD" if good else "BAD" if bad else "MIXED"
        two_by_two[("CHEAP" if r["cheap"] else "NOT_CHEAP") + "_" + env] += 1

    return {
        "study": "market-valuation-macro-overlay-v1", "stage": "US_SIGNAL_READINESS_OUTCOME_FREE",
        "outcomeReads": 0,
        "note": "States and targets only. No return, NAV or performance was computed; a state frequency is not evidence.",
        "decisionDates": {"first": decisions[0], "last": decisions[-1], "count": len(decisions)},
        "window": {"first": window[0]["decisionDate"], "last": window[-1]["decisionDate"], "count": len(window)},
        "inputDeterminability": {k: count(k) for k in ("cheap", "earningsStable", "creditStress", "deepDrawdown")},
        "spreadObservationMonthMismatches": mismatched_months,
        "stateTable2x2": dict(sorted(two_by_two.items())),
        "policies": policies,
        "rows": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=str(REPO / "data/research/mvma-v1"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    report = build(Path(args.data_dir))
    rows = report.pop("rows")
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=list(rows[-1]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    Path(args.out).with_suffix(".csv").write_text(text.getvalue())
    Path(args.out).write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: report[k] for k in ("window", "inputDeterminability", "stateTable2x2", "policies")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
