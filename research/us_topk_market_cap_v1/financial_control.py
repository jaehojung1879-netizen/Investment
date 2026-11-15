"""Rebuild the existing B2 score rule on corrected inputs; no old executor."""
from collections import defaultdict
from datetime import date
from pathlib import Path
import argparse
import hashlib
import math

import pandas as pd

from pipeline import replay_calendar as RC, us_decision_pilot as P
from scripts import run_us_decision_pilot as S
from research.us_historical_market_recovery_v1 import audit as A
from research.us_topk_market_cap_v1.inputs import read, write
from research.us_topk_market_cap_v1.performance import ASOF, Returns, net, summarize


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market-private", type=Path, required=True)
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    market = args.market_private
    original = read(market / "baseline-bars.json.gz")
    references = {t: original[t] for t in ("PSKY", "WBD", "KVUE", "KMB")}
    fixed = RC.sessions("2011-01-03", "2026-09-14", "US")
    close = pd.DataFrame({t: pd.Series({d: r["Close"] for d, r in rows.items()}, dtype=float)
                          for t, rows in original.items() if t not in A.QUARANTINED_BASELINE})
    close.index = pd.to_datetime(close.index)
    close = close.reindex(fixed)
    del original
    records = read(market / "new_charts.json")
    for old, (new, _, _) in A.ALIASES.items():
        rec = next(r for r in records if r["ticker"] == new and r.get("status") == 200)
        series, _, _ = A.chart_series(rec, market)
        close[old] = series.tr.reindex(fixed).where([str(d.date()) in series.good_days for d in fixed])
    auth = {(r["provider"], r["endpoint"], r["ticker"]): r for r in A.auth_rows(market)}
    for ticker in ("ATVI", "MRO", "TWTR", "VIAC", "WBA"):
        series, _, _ = A.fmp_series(ticker, auth)
        lower = "2019-12-05" if ticker == "VIAC" else "2014-12-31" if ticker == "WBA" else "1900-01-01"
        good = {d for d in series.good_days if d >= lower}
        close[ticker] = series.tr.reindex(fixed).where([str(d.date()) in good for d in fixed])
    calendar = [str(d.date()) for d in RC.sessions("2011-01-03", "2028-01-14", "US")]
    public, _ = A.load_public_prices(market, references, calendar)
    close["PARA"] = public["PARA"].tr.reindex(fixed)
    del references, auth
    filings, _ = S.load_filings()
    applied = A.apply_sec_overlay(filings, date(2026, 9, 14))
    for old, (new, _, _) in A.ALIASES.items():
        if old not in filings and new in filings:
            filings[old] = filings[new]
    frames, _, _ = S.build_signals(close, filings)
    native = {r["signal"]: set(r["tickers"]) for r in read(market / "repaired-input-eligible-cohorts.json")["cohorts"]}
    cap_ranks = read(args.private / "rankings.json.gz")
    dates = {r["signal"] for r in cap_ranks if r["pool"] == "CORRECTED_FINANCIAL_POOL" and r["status"].startswith("VERIFIED")}
    selections = []
    for day, frame in sorted(frames.items()):
        signal = str(day.date())
        if signal not in dates:
            continue
        corrected = P.scores(frame.loc[sorted(native[signal])])
        if set(corrected.index) != native[signal]:
            raise ValueError("FINANCIAL_CONTROL_COHORT_DRIFT")
        ordered = corrected.assign(_ticker=corrected.index).sort_values(["B2", "_ticker"], ascending=[False, True])
        count = max(1, math.ceil(len(ordered) / 5))
        selections.append({"signal": signal, "entry": calendar[calendar.index(signal) + 1],
                           "selected": list(ordered.index[:count]), "pool_size": len(corrected)})
    sha = write(args.private / "financial-control-ranks.json.gz", selections)
    write(args.output / "financial-control-freeze.json", {
        "rule": "Existing P.scores five equally weighted percentile families; reranked within corrected native single-CIK pool; B2 top ceil(N/5), equal weight",
        "sec_asset_filings_applied": applied, "input_frame_sha256": A.digest(pd.util.hash_pandas_object(close, index=True).values.tobytes()),
        "private_rank_sha256": sha, "dates": len(selections),
        "note": "Separate descriptive control on same dates; no original historical performance result or old evaluation executor read"})
    # Control ranks are persisted and checked before accessing their returns.
    if hashlib.sha256((args.private / "financial-control-ranks.json.gz").read_bytes()).hexdigest() != sha:
        raise ValueError("CONTROL_RANK_CHANGED")
    returns = Returns(market)
    rows = []
    for rank in selections:
        for h in (126, 252):
            end = calendar[calendar.index(rank["entry"]) + h]
            labels = {t: returns.get(t, rank["entry"], end, rank["signal"], h) for t in rank["selected"]}
            spy = returns.get("SPY", rank["entry"], end)
            failed = {t: r["status"] for t, r in labels.items() if r["status"] != "COMPLETE"}
            row = {"signal": rank["signal"], "entry": rank["entry"], "end": end, "horizon": h,
                   "selected_count": len(rank["selected"]), "status": "COMPLETE", "failed_names": failed}
            if end > ASOF:
                row["status"] = "HOLDING_NOT_MATURE"
            elif failed:
                row["status"] = "SELECTED_HOLDING_INCOMPLETE_NO_REPLACEMENT"
            elif spy["status"] != "COMPLETE":
                row["status"] = "SPY_" + spy["status"]
            else:
                row["net_return"] = net(sum(r["gross"] for r in labels.values()) / len(labels),
                    sum(1 + r["gross"] for r in labels.values() if r.get("cash_terminal")) / len(labels))
                row["spy_net_return"] = net(spy["gross"])
                row["excess"] = row["net_return"] - row["spy_net_return"]
            rows.append(row)
    write(args.private / "financial-control-cohorts.json.gz", rows)
    stats, grouped = [], defaultdict(list)
    for row in rows:
        grouped[row["horizon"], "ALL"].append(row)
        grouped[row["horizon"], row["signal"][:4]].append(row)
    for (h, year), group in sorted(grouped.items()):
        stats.append({"control": "CORRECTED_POOL_B2_TOP_QUINTILE_EQUAL_WEIGHT", "horizon": h,
                      "signal_year": year, **summarize(group, calendar)})
    write(args.output / "financial-control-summary.json", stats)
    print([r for r in stats if r["signal_year"] == "ALL"], flush=True)


if __name__ == "__main__":
    main()
