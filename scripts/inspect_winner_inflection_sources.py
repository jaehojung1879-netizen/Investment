"""Input-only pattern census over #247's pinned LOCAL source allowlist.

Default preview opens no data. --inspect reads raw inputs, never outcomes or
sealed results. No network, persistence, model fitting or label construction.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_alpha_atlas_bars as B  # noqa: E402
from pipeline import krx_prices as KP  # noqa: E402
from pipeline import replay_inputs as RI  # noqa: E402
from pipeline import winner_inflection as WI  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402


def inspect(repo):
    source = S.Sources(repo)
    manifest = json.loads(source.blob(S.SOURCE_COMMIT, S.MANIFEST))
    if RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != S.MANIFEST_SHA:
        raise ValueError("REPLAY_MANIFEST_CHANGED")
    source.allowed_objects = {ref for name, refs in manifest["components"].items() if name.startswith("price/20") for ref in refs}
    prices, duplicates = defaultdict(dict), 0
    for name, refs in sorted(manifest["components"].items()):
        if name.startswith("price/20"):
            for ref in refs:
                for row in source.component(ref):
                    ticker, day = sys.intern(row["ticker"]), sys.intern(row["date"])
                    value = (row.get("Close"), row.get("Volume"))
                    if day in prices[ticker]:
                        duplicates += 1
                        if prices[ticker][day] != value:
                            raise ValueError("CONFLICTING_PRICE_KEY")
                    prices[ticker][day] = value
    memberships = {"US": S.RAF.MembershipSnapshots(source.json(S.MEMBERS)["snapshots"])}
    sectors = S.RAF.MembershipSnapshots(source.json(S.SECTORS)["snapshots"])
    intervals, crosswalk = source.json(S.INTERVALS), source.json(S.CROSSWALK)
    print("Pinned replay prices loaded", file=sys.stderr)
    kr_universe, kr_raw = defaultdict(list), defaultdict(list)
    for year in range(2013, 2027):
        for r in source.rows(f"ledger/universe/kr/krx-universe-{year}.jsonl.gz"):
            kr_universe[r["date"]].append(r)
    memberships["KR"] = S.RAF.MembershipSnapshots([
        {"date": day, "members": [r["ticker"] for r in sorted(rows, key=lambda r: (r["rank"], r["ticker"]))[:120]]}
        for day, rows in sorted(kr_universe.items())])
    kr_ever = {t for s in memberships["KR"].snapshots for t in s["members"]}
    del kr_universe
    for year in range(2013, 2027):
        for r in source.rows(f"ledger/prices/kr/krx-prices-{year}.jsonl.gz"):
            if r["ticker"] in kr_ever:
                kr_raw[r["ticker"]].append(r)
    filings, caches = {}, {}
    for market, years, name in (("KR", range(2015, 2027), "kr-candidate-merged/dart"), ("US", range(2011, 2028), "us/finnhub")):
        filings[market] = [r for year in years for r in source.rows(f"ledger/fundamentals/{name}-{year}.jsonl.gz")]
        grouped = defaultdict(list)
        for r in filings[market]:
            grouped[r["ticker"]].append(r)
        caches[market] = {t: WI.FilingStates(rows, market) for t, rows in grouped.items()}
    calendar = S.RC.sessions("2011-01-01", "2026-10-31", "KR")
    bars = {t: B.TickerBars(t, KP.frame_from_rows(rows, traded_only=False), calendar) for t, rows in kr_raw.items()}
    del kr_raw
    markets = {}
    for market in ("KR", "US"):
        print("PIT pattern census: " + market, file=sys.stderr)
        days = S.RC.sessions("2011-01-01", "2026-10-31", market)
        grid = days.to_series().groupby(days.to_period("W")).max()
        dates = [str(d.date()) for d in grid if "2013-01-01" <= str(d.date()) <= manifest["through"]]
        rows, reasons, by_date = [], defaultdict(Counter), []
        for day in dates:
            snapshot = memberships[market].on(day)
            if snapshot is None:
                continue
            groups, paths, states, base = {}, {}, {}, {}
            sector = sectors.on(day) if market == "US" else None
            pos = days.searchsorted(day)
            window = [str(d.date()) for d in days[max(0, pos - 126):pos + 1]]
            for ticker in snapshot["members"]:
                state = caches[market][ticker].at(day) if ticker in caches[market] else {
                    "fields": dict.fromkeys(WI.FLOW_FIELDS), "reasons": dict.fromkeys(WI.FLOW_FIELDS, "NO_FILING_STORE")}
                states[ticker] = state
                group = (S.KI.industry_of(intervals, crosswalk, ticker, day)[0] if market == "KR" else
                         ((sector or {}).get("rows") or {}).get(ticker, {}).get("sector"))
                groups[ticker] = group if market == "KR" or group in S.COARSE_LABELS else None
                observed = [prices[ticker].get(d, (None, None)) for d in window]
                valid = len(window) == 127 and all(c is not None and np.isfinite(c) and c > 0 and
                    v is not None and v > 0 for c, v in observed)
                quote = observed[-1] if observed else (None, None)
                tradable = quote[0] is not None and quote[0] > 0 and quote[1] is not None and quote[1] > 0
                price_reason = "AVAILABLE" if valid else "NO_EXACT_TRADED_127_SESSION_WINDOW"
                if market == "KR":
                    guard = bars.get(ticker)
                    cause = guard.basis_cause(day, 127) if guard else "NO_OFFICIAL_PRICE_PANEL"
                    if guard and (pd.Timestamp(day) not in guard.traded_mask.index or not guard.traded_mask.loc[day]):
                        tradable = False
                    if cause:
                        valid, price_reason = False, cause
                    # Require official trading on every session, as well as
                    # replay close: suspended/fill-forward windows abstain.
                    if guard is None or not guard.traded_mask.reindex(pd.to_datetime(window), fill_value=False).all():
                        valid, price_reason = False, "OFFICIAL_TRADING_WINDOW_INCOMPLETE"
                if valid:
                    paths[ticker] = (observed[63][0] / observed[0][0], observed[126][0] / observed[63][0])
                base[ticker] = {"tradable": tradable, "path127": valid, "priceReason": price_reason}
            relative = WI.industry_relative_change(paths, groups)
            current = []
            for ticker in snapshot["members"]:
                fields = states[ticker]["fields"]
                a = all(fields[k] is not None for k in WI.PATTERNS["A"])
                b = all(fields[k] is not None for k in WI.PATTERNS["B"])
                c = relative[ticker][0] is not None
                row = {"date": day, "industry": groups[ticker] or "UNRESOLVED", **base[ticker], "A": a, "B": b, "C": c,
                       "B_cash": fields["ocfMarginChange"] is not None and fields["ocfPositiveCross"] is not None,
                       "D_dependencyCeiling": b and c, "E_dependencyCeiling": c,
                       "F_dependencyCeiling": a and b, "G_dependencyCeiling": fields["ocfMarginChange"] is not None and base[ticker]["path127"]}
                row["ABC_tradable"] = a and b and c and row["tradable"]
                for pattern in ("A", "B"):
                    missing = sorted({states[ticker]["reasons"][k] for k in WI.PATTERNS[pattern] if fields[k] is None})
                    reasons[pattern]["AVAILABLE" if not missing else "|".join(missing)] += 1
                reasons["C"][base[ticker]["priceReason"] if not base[ticker]["path127"] else relative[ticker][1]] += 1
                current.append(row)
            rows.extend(current)
            by_date.append({"date": day, **summarize(current)})
        years, industries = defaultdict(list), defaultdict(list)
        for r in rows:
            years[r["date"][:4]].append(r)
            industries[r["industry"]].append(r)
        latest_financial = Counter()
        for t in memberships[market].on("2026-10-16")["members"]:
            fields = caches[market][t].at("2026-10-16")["fields"] if t in caches[market] else {}
            for pattern in ("A", "B"):
                latest_financial[pattern] += all(fields.get(k) is not None for k in WI.PATTERNS[pattern])
        markets[market] = {"weeklySignalRange": [by_date[0]["date"], by_date[-1]["date"]], "weeks": len(by_date),
            "totals": summarize(rows), "latestPriceLinkedCandidatesH126AndH252": by_date[-1],
            "firstMeasurableDate": {p: next((r["date"] for r in rows if r[p]), None) for p in ("A", "B", "C")},
            "byYear": {k: summarize(v) for k, v in sorted(years.items())},
            "byIndustry": {k: summarize(v) for k, v in sorted(industries.items())},
            "missingReasons": {k: dict(sorted(v.items())) for k, v in reasons.items()},
            "financialOnlyAt2026_10_16": {"counts": dict(latest_financial), "priceLinked": False},
            "weeklyCoverageSha256": RI.digest(by_date), "recentWeeklyCoverage": by_date[-8:],
            "filingInventory": S.filing_inventory(filings[market], market)}
    base_report = json.loads((ROOT / "docs/experiment-workbench/readiness.json").read_bytes())
    return {"program": WI.VERSION, "status": "INPUT_READINESS_ONLY", "sourceCommit": S.SOURCE_COMMIT,
        "mainBase": "0131a0dfe770ca5ae4d5a977e2caa4b50331fa3b", "through": manifest["through"], "manifestSha256": S.MANIFEST_SHA,
        "candidateMeaning": "input measurable, not verified identity / finalized shareholder-return labels / licensed execution",
        "universe": {"KR": "strict-prior monthly PIT Top120; not all KRX", "US": "strict-prior historical S&P500 community snapshots; not all US"},
        "patternsDEFG": "dependency ceilings only; event timelines, lagged leader sets, valuation sequence and downside features not implemented",
        "strictExecutionReady": False, "historicalExecutionAuthorized": False, "labelReads": 0, "modelFits": 0,
        "duplicatePriceKeys": duplicates, "markets": markets,
        "inheritedIdentityAudit": {m: base_report["markets"][m]["identity"] for m in ("KR", "US")},
        "inheritedAuditSha256": hashlib.sha256((ROOT / "docs/experiment-workbench/readiness.json").read_bytes()).hexdigest(),
        "codeHashes": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
            "pipeline/winner_inflection.py", "scripts/inspect_winner_inflection_sources.py")},
        "sources": dict(sorted(source.receipts.items()))}


def summarize(rows):
    flags = ("tradable", "path127", "A", "B", "B_cash", "C", "ABC_tradable", "D_dependencyCeiling",
             "E_dependencyCeiling", "F_dependencyCeiling", "G_dependencyCeiling")
    return {"memberDates": len(rows), **{f: {"count": sum(r[f] for r in rows), "pct": S.pct(sum(r[f] for r in rows), len(rows))} for f in flags}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    report = inspect(args.repo) if args.inspect else {"program": WI.VERSION, "status": "PREVIEW_ONLY", "sourceReads": 0,
        "historicalExecutionAuthorized": False, "labelReads": 0, "modelFits": 0}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
