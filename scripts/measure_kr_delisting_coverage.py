"""Can any free vendor price the Korean names the replay is missing?

WHY THIS EXISTS. The Korean cross-section is survivors-only, and closing it
needs two separate things: a dated KOSPI 200 membership history (there is no
free one) and PRICE HISTORY FOR NAMES THAT HAVE SINCE BEEN DELISTED. The second
is the one that decides whether the first is worth building: with membership
alone the departed names are known-but-unpriceable, which `UniverseHistory.
snapshot` drops, so `affectedObservationsPct` for KR would fall from 100% to
roughly 40% and stop there. Only prices take it further.

WHAT IS ALREADY KNOWN. The replay's panel is Yahoo (`pipeline.datafeed`), and
Yahoo serves almost none of these: the first point-in-time run measured 17 of
3,010. FinanceDataReader exposes the same names under
`exchange='KRX-DELISTING'` and is already a dependency. Whether THAT route
serves usable history has never been measured, and this script measures it.

WHAT "USABLE" MEANS. Not "the vendor returned a frame". A name enters a
cross-section only if the panel can serve `longterm.MIN_HISTORY` (273) sessions
BEFORE the date it is needed — 252 days of momentum plus a 21-day skip. A
delisted name whose vendor history starts three months before it died is
useless to the replay however complete it looks. So the test is the replay's
own: rows strictly before the delisting date, counted against MIN_HISTORY.

THE DENOMINATOR IS NOT 3,010. That is every KRX delisting since 1960. A name
that stopped trading before the replay begins was never in any cross-section
the replay builds, so it cannot be missing from one. The relevant set is names
delisted ON OR AFTER the replay start, and the script reports both so the
shrinkage is visible rather than assumed.

SAMPLED, NOT ENUMERATED, AND SAID SO. Testing every name against two vendors is
thousands of sequential requests. A stratified random sample by delisting year
with a Wilson interval answers the question the decision needs — "is this route
worth building on" — and an interval is what makes it an answer rather than an
anecdote. `--all` enumerates when someone wants the exact figure.

This measures. It writes no membership and changes no artifact.

Usage:
    python scripts/measure_kr_delisting_coverage.py [--output out.json]
        [--sample 150] [--all] [--seed 11]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline.config import load_config  # noqa: E402
from pipeline.longterm import MIN_HISTORY  # noqa: E402

FDR_DELISTING_EXCHANGE = "KRX-DELISTING"
# The market the replay's Korean universe is drawn from — `universe.resolve`
# screens `fdr.StockListing("KOSPI")` and nothing else. Coverage on any other
# market is context, never the headline: the first run measured 53.33% pooled
# against 34.55% on KOSPI alone, because 95 of the 150 names sampled were
# KOSDAQ or KONEX and the replay never sees them. A pooled figure answered the
# decision question with the opposite sign to the real one.
REPLAY_MARKET = "KOSPI"


def wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float] | None:
    """Interval for a share, valid at the extremes a normal one is not.

    Coverage here is expected near 0 or near 1, where the textbook interval
    returns bounds outside [0, 1] and a width of zero when nothing succeeded.
    """
    if trials <= 0:
        return None
    p = successes / trials
    denom = 1 + z**2 / trials
    centre = (p + z**2 / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / denom
    return (round(max(0.0, centre - half) * 100, 2),
            round(min(1.0, centre + half) * 100, 2))


def delisting_listing() -> pd.DataFrame | None:
    try:
        import FinanceDataReader as fdr
    except ImportError as exc:                       # pragma: no cover - env
        print(f"FinanceDataReader unavailable: {exc}")
        return None
    try:
        return fdr.StockListing(FDR_DELISTING_EXCHANGE)
    except Exception as exc:                          # pragma: no cover - network
        print(f"KRX-DELISTING listing failed: {exc}")
        return None


def _column(frame: pd.DataFrame, *names: str):
    lookup = {str(c).lower().replace("_", ""): c for c in frame.columns}
    for name in names:
        hit = lookup.get(name.lower().replace("_", ""))
        if hit is not None:
            return hit
    return None


def candidates(frame: pd.DataFrame, replay_start: str) -> list[dict]:
    """Delisted KRX names, with the replay-relevant ones flagged.

    A name delisted before the replay starts is not a gap in any cross-section
    the replay builds; keeping it in the denominator would understate coverage
    against a need that does not exist.
    """
    symbol_col = _column(frame, "symbol", "code")
    date_col = _column(frame, "delistingdate", "delisting_date", "date")
    market_col = _column(frame, "market", "exchange")
    name_col = _column(frame, "name", "korname", "kor_name")
    if not symbol_col or not date_col:
        print(f"unexpected KRX-DELISTING columns: {list(frame.columns)}")
        return []
    cutoff = pd.Timestamp(replay_start)
    rows = []
    for _, row in frame.iterrows():
        symbol = str(row[symbol_col]).strip()
        if not symbol.isdigit():
            continue
        when = pd.to_datetime(str(row[date_col])[:10], errors="coerce")
        if pd.isna(when):
            continue
        rows.append({
            "symbol": symbol,
            "delisted": when.strftime("%Y-%m-%d"),
            "year": int(when.year),
            "market": (str(row[market_col]).strip() if market_col else None),
            "name": (str(row[name_col]).strip() if name_col else None),
            "inReplayWindow": bool(when >= cutoff),
        })
    return rows


def fdr_history(symbol: str, before: str) -> int:
    """Sessions FinanceDataReader can serve strictly before ``before``."""
    try:
        import FinanceDataReader as fdr
    except ImportError:                               # pragma: no cover - env
        return 0
    try:
        frame = fdr.DataReader(symbol, "1990-01-01", before,
                               exchange=FDR_DELISTING_EXCHANGE)
    except Exception:                                 # pragma: no cover - network
        return 0
    if frame is None or not len(frame):
        return 0
    close = frame.get("Close")
    if close is None:
        return 0
    close = close.dropna()
    return int((pd.to_datetime(close.index) < pd.Timestamp(before)).sum())


def yahoo_history(symbol: str, before: str) -> int:
    """The same question of the vendor the replay's panel actually uses."""
    from pipeline.datafeed import fetch_prices
    best = 0
    for suffix in (".KS", ".KQ"):
        frames = fetch_prices([f"{symbol}{suffix}"], "1990-01-01")
        frame = frames.get(f"{symbol}{suffix}")
        if frame is None or "Close" not in frame:
            continue
        close = frame["Close"].dropna()
        best = max(best, int((pd.to_datetime(close.index) < pd.Timestamp(before)).sum()))
    return best


def stratified(rows: list[dict], size: int, seed: int) -> list[dict]:
    """Proportional by delisting year, so no era can dominate the estimate.

    The need is front-loaded — the earliest cross-sections are missing the most
    names — so a sample that happened to draw recent delistings would report a
    coverage the early years never see.
    """
    if size >= len(rows):
        return list(rows)
    rng = random.Random(seed)
    by_year: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_year[row["year"]].append(row)
    picked: list[dict] = []
    for year in sorted(by_year):
        bucket = by_year[year]
        take = max(1, round(size * len(bucket) / len(rows)))
        picked.extend(rng.sample(bucket, min(take, len(bucket))))
    rng.shuffle(picked)
    return picked[:size]


def summarise(results: list[dict], key) -> dict:
    buckets: dict = defaultdict(lambda: {"tested": 0, "fdr": 0, "yahoo": 0})
    for row in results:
        bucket = buckets[key(row)]
        bucket["tested"] += 1
        bucket["fdr"] += int(row["fdrUsable"])
        bucket["yahoo"] += int(row["yahooUsable"])
    out = {}
    for name, bucket in sorted(buckets.items(), key=lambda kv: str(kv[0])):
        out[str(name)] = {
            "tested": bucket["tested"],
            "fdrUsablePct": round(100 * bucket["fdr"] / bucket["tested"], 2),
            "yahooUsablePct": round(100 * bucket["yahoo"] / bucket["tested"], 2),
            "fdrUsableCI": wilson(bucket["fdr"], bucket["tested"]),
        }
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="kr-delisting-coverage.json")
    parser.add_argument("--sample", type=int, default=150)
    parser.add_argument("--all", action="store_true",
                        help="test every replay-relevant name instead of a sample")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--market", default=REPLAY_MARKET,
                        help="market the headline is measured on; ALL to pool "
                             "(pooling answers a different question than the "
                             "replay asks)")
    args = parser.parse_args(argv)

    cfg, _ = load_config()
    replay_start = (cfg.historical_replay or {}).get("start", "2013-01-01")

    frame = delisting_listing()
    if frame is None:
        print("ERROR: could not read the KRX-DELISTING listing; nothing measured.")
        return 1
    rows = candidates(frame, replay_start)
    if not rows:
        return 1

    relevant = [row for row in rows if row["inReplayWindow"]]
    print(f"KRX-DELISTING listing: {len(rows):,} dated names since "
          f"{min(r['year'] for r in rows)}")
    print(f"  delisted on or after the replay start ({replay_start}): {len(relevant):,}")
    print(f"  irrelevant to the replay (already gone before it began): "
          f"{len(rows) - len(relevant):,}")
    # Second narrowing, and the one the first run got wrong. The replay screens
    # KOSPI; a KOSDAQ name it never ranks cannot be a hole in its cross-section,
    # and counting it answers a question nobody asked.
    market = args.market.upper()
    if market != "ALL":
        on_market = [row for row in relevant
                     if (row["market"] or "").upper() == market]
        print(f"  on {market}, the market the replay screens: {len(on_market):,} "
              f"(other markets: {len(relevant) - len(on_market):,}, sampled for "
              f"context only)")
        relevant = on_market
    if not relevant:
        print("nothing in the replay window; no coverage to measure.")
        return 0

    sample = relevant if args.all else stratified(relevant, args.sample, args.seed)
    print(f"\ntesting {len(sample):,} names against FinanceDataReader and Yahoo "
          f"(usable = {MIN_HISTORY} sessions before the delisting date) ...")

    results = []
    for index, row in enumerate(sample, 1):
        fdr_rows = fdr_history(row["symbol"], row["delisted"])
        yahoo_rows = yahoo_history(row["symbol"], row["delisted"])
        results.append({**row, "fdrRows": fdr_rows, "yahooRows": yahoo_rows,
                        "fdrUsable": fdr_rows >= MIN_HISTORY,
                        "yahooUsable": yahoo_rows >= MIN_HISTORY})
        if index % 25 == 0:
            done = sum(r["fdrUsable"] for r in results)
            print(f"  {index}/{len(sample)} — FinanceDataReader usable so far: {done}")

    tested = len(results)
    fdr_ok = sum(r["fdrUsable"] for r in results)
    yahoo_ok = sum(r["yahooUsable"] for r in results)
    either = sum(r["fdrUsable"] or r["yahooUsable"] for r in results)
    report = {
        "measuredAt": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "replayStart": replay_start,
        "market": market,
        "minHistorySessions": MIN_HISTORY,
        "listedNames": len(rows),
        "replayRelevantNames": len(relevant),
        "sampleSize": tested,
        "sampled": not args.all,
        "fdrUsablePct": round(100 * fdr_ok / tested, 2),
        "fdrUsableCI": wilson(fdr_ok, tested),
        "yahooUsablePct": round(100 * yahoo_ok / tested, 2),
        "yahooUsableCI": wilson(yahoo_ok, tested),
        "eitherUsablePct": round(100 * either / tested, 2),
        "byDelistingYear": summarise(results, lambda r: r["year"]),
        "byMarket": summarise(results, lambda r: r["market"] or "UNKNOWN"),
        "rows": results,
    }
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n=== usable price history, {market} delisted names in the replay window ===")
    print(f"  FinanceDataReader : {fdr_ok}/{tested} = {report['fdrUsablePct']}%  "
          f"95% CI {report['fdrUsableCI']}")
    print(f"  Yahoo (the panel) : {yahoo_ok}/{tested} = {report['yahooUsablePct']}%  "
          f"95% CI {report['yahooUsableCI']}")
    print(f"  either vendor     : {report['eitherUsablePct']}%")
    print("\n  by delisting year:")
    for year, bucket in report["byDelistingYear"].items():
        print(f"    {year}  fdr {bucket['fdrUsablePct']:6.2f}%  "
              f"yahoo {bucket['yahooUsablePct']:6.2f}%  ({bucket['tested']} tested)")
    if report["byMarket"]:
        print("\n  by market:")
        for market, bucket in report["byMarket"].items():
            print(f"    {market:<10} fdr {bucket['fdrUsablePct']:6.2f}%  "
                  f"yahoo {bucket['yahooUsablePct']:6.2f}%  ({bucket['tested']} tested)")
    print(f"\nwrote {args.output}")
    # The decision this measures for: with membership alone the KR sleeve stops
    # around 40% unvouched. Prices are what take it further, and only a vendor
    # that serves most of these can.
    print("\nreading: a dated KOSPI 200 membership history is worth building only "
          "if a vendor can price the names it restores. Below ~50% the Korean "
          "cross-section stays materially incomplete whatever the membership file "
          "says — and it is the UPPER bound of the interval that has to clear it, "
          "not the point estimate.")
    if market != "ALL":
        print(f"the figure above is {market} only, because that is the list "
              f"`universe.resolve` screens. Pooling markets the replay never "
              f"ranks reported 53.33% where {market} alone was 34.55%.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
