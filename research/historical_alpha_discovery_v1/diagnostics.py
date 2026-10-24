"""Post-execution diagnostics, not new strategy selection or a new hypothesis test.

The original spec and first execution are preserved. All quantities use the fixed
signal schedule and mask. No thresholds, books or investment rules are changed.
"""

from __future__ import annotations

from collections import Counter
import json

import numpy as np
import pandas as pd

from . import run as R


def compute(output):
    source, universe, m, terminal, industries, _, local = R.load_inputs()
    days = m["close"].index
    first = days.get_loc(pd.Timestamp(R.SPEC["firstEntry"]))
    labels, readings, market_states, halted = [], [], {}, []
    for h in R.SPEC["horizons"]:
        for entry_i in range(first, len(days) - h, h):
            signal_i, end_i = entry_i - 1, entry_i + h
            signal, entry, end = [str(days[i].date()) for i in (signal_i, entry_i, end_i)]
            snap = universe.loc[universe.date < signal, "date"].max()
            members = universe.loc[(universe.date == snap) & (universe["rank"] <= 120)].to_dict("records")
            features, _ = R.features_at(m, signal_i, members, industries)
            bench = m["benchmark"].iloc[entry_i : end_i + 1].to_numpy(dtype=float)
            benchmark_net = (
                bench[-1]
                / bench[0]
                / (1 + R.cost(entry, stock=False, sell=False))
                * (1 - R.cost(end, stock=False, sell=True))
                - 1
            )
            before = m["benchmark"].iloc[signal_i - 199 : signal_i + 1]
            market_states[signal] = "ABOVE_PAST_MA200" if before.iloc[-1] >= before.mean() else "BELOW_PAST_MA200"
            for feature in features:
                ticker = feature["ticker"]
                path, reason = R.path_for(m, ticker, entry_i, end_i, terminal)
                net = (
                    None
                    if path is None
                    else float(
                        path[-1]
                        / (1 + R.cost(entry, stock=True, sell=False))
                        * (1 - R.cost(end, stock=True, sell=True))
                        - 1
                    )
                )
                labels.append(
                    {
                        "horizon": h,
                        "signal": signal,
                        "entry": entry,
                        "exit": end,
                        **feature,
                        "netStockReturn": net,
                        "netBenchmarkReturn": benchmark_net,
                        "netExcess": None if net is None else net - benchmark_net,
                        "missingReason": reason,
                        "marketTrendAtSignal": market_states[signal],
                    }
                )
            all_rows = pd.DataFrame([r for r in labels if r["signal"] == signal and r["horizon"] == h])
            valid = all_rows.dropna(subset=["netExcess"])
            # Each feature uses exactly the same common validity mask; actual n published.
            for feature in ("momentum", "intraday", "overnight"):
                ic = valid[feature].rank().corr(valid.netExcess.rank()) if len(valid) >= 30 else None
                readings.append(
                    {
                        "horizon": h,
                        "signal": signal,
                        "feature": feature,
                        "preMaskNames": len(all_rows),
                        "validNames": len(valid),
                        "spearmanIC": None if pd.isna(ic) else float(ic),
                    }
                )
    labels = pd.DataFrame(labels)
    output.mkdir(parents=True, exist_ok=True)
    labels.to_csv(output / "forward-labels.csv", index=False, float_format="%.12g")
    pd.DataFrame(readings).to_csv(output / "date-balanced-ic.csv", index=False, float_format="%.12g")
    ic_summary = []
    for (h, feature), group in pd.DataFrame(readings).groupby(["horizon", "feature"]):
        ok = group.spearmanIC.dropna()
        ic_summary.append(
            {
                "horizon": int(h),
                "feature": feature,
                "scheduledDates": len(group),
                "validDates": len(ok),
                "validNameDateCount": int(group.validNames.sum()),
                "meanDateIC": float(ok.mean()) if len(ok) else None,
                "inference": "NONE_EXPOSED_HISTORY_AND_FEW_NONOVERLAPPING_DATES",
            }
        )
    # Explicitly classify source halts of actually selected names; no marks or exits invented.
    blocks = json.loads((R.HERE / "results/blocks.json").read_text())
    strict = [
        r
        for r in blocks
        if r["analysisWindow"] == "FULL"
        and r["sample"] == R.SPEC["samples"][0]
        and r["costMultiplier"] == 1
        and r["horizon"] == 126
        and r["book"] == "INTRADAY"
    ]
    for block in strict:
        for failure in block["failures"]:
            ticker = failure["ticker"]
            volume = m["volume"][ticker].loc[block["entry"] : block["exit"]]
            dates = volume[volume <= 0].index
            halted.append(
                {
                    "entry": block["entry"],
                    "exit": block["exit"],
                    **failure,
                    "zeroVolumeSessions": len(dates),
                    "firstZeroVolume": str(dates[0].date()) if len(dates) else None,
                    "lastZeroVolume": str(dates[-1].date()) if len(dates) else None,
                    "stockBudgetFraction": 0.2,
                    "treatment": "WHOLE_BOOK_BLOCKED_NO_PAYOFF_SUBSTITUTION",
                }
            )
    # Price and financial availability profile; no additional financial hypothesis or fit.
    filing_coverage = []
    names = R.subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", source.commit], cwd=R.ROOT, text=True
    ).splitlines()
    for year in range(2014, 2027):
        path = f"ledger/fundamentals/kr-candidate-merged/dart-{year}.jsonl.gz"
        if path not in names:
            filing_coverage.append({"fiscalYear": year, "status": "SHARD_ABSENT_NOT_ZERO_FILINGS"})
            continue
        rows = source.rows(path)
        availability = [r["availableFrom"] for r in rows if r.get("availableFrom")]
        accounts = ("자본총계", "당기순이익", "영업활동현금흐름", "영업이익")
        filing_coverage.append(
            {
                "fiscalYear": year,
                "filings": len(rows),
                "tickers": len({r["ticker"] for r in rows}),
                "availableFromMin": min(availability) if availability else None,
                "availableFromMax": max(availability) if availability else None,
                "missingAvailableFrom": sum(not r.get("availableFrom") for r in rows),
                "accountPresent": {a: sum(a in r.get("accounts", {}) for r in rows) for a in accounts},
            }
        )
    # Do not silently invent a missing source. Detect its actual Git path from metadata only.
    flow_manifests = [p for p in names if "flow" in p.lower() and p.endswith("manifest.json")]
    flows = []
    for path in flow_manifests:
        obj = json.loads(source.blob(path))
        flows.append(
            {
                "path": path,
                "metadata": {
                    k: obj[k]
                    for k in (
                        "status",
                        "recordCount",
                        "records",
                        "lastUpdated",
                        "lastOutcome",
                        "refusal",
                        "updatedAt",
                        "thisRun",
                        "remainingPairs",
                    )
                    if k in obj
                },
            }
        )
    # Annual returns use actual daily continuous paths only; no joining over missing blocks.
    annual = []
    for path in sorted((R.HERE / "results").glob("nav-*.csv")):
        df = pd.read_csv(path, parse_dates=["date"])
        returns = df.nav.pct_change(fill_method=None)
        for year, group in pd.DataFrame({"year": df.date.dt.year, "return": returns}).groupby("year"):
            annual.append(
                {
                    "path": path.name,
                    "year": int(year),
                    "sessions": int(group["return"].notna().sum()),
                    "netReturn": float(np.prod(1 + group["return"].dropna()) - 1),
                    "note": "First/last year may be partial; costs stay on actual dates.",
                }
            )
    pd.DataFrame(annual).to_csv(output / "annual-path-returns.csv", index=False, float_format="%.12g")
    (output / "diagnostics.json").write_text(
        json.dumps(
            {
                "scope": "POST_EXECUTION_DESCRIPTIVE_ONLY_NO_RULE_CHANGE",
                "featureIC": ic_summary,
                "labelReasons": dict(Counter(labels.missingReason.fillna("VALID"))),
                "blockedPrimaryH126": halted,
                "filingCoverage": filing_coverage,
                "flowManifests": flows,
                "universeByYear": [
                    {
                        "year": int(y),
                        "snapshots": g.date.nunique(),
                        "top120EverTickers": g.loc[g["rank"] <= 120, "ticker"].nunique(),
                        "top120NameSnapshots": int((g["rank"] <= 120).sum()),
                    }
                    for y, g in universe.groupby(universe.date.str[:4].astype(int))
                ],
                "inputHashes": source.identities,
                "localSourceHashes": local,
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    print(json.dumps({"labels": len(labels), "valid": int(labels.netExcess.notna().sum()), "IC": ic_summary}))


if __name__ == "__main__":
    compute(R.HERE / "results/diagnostics")
