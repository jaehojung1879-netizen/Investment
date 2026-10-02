#!/usr/bin/env python3
"""Outcome-free scope audit of the preserved KR inputs behind kr-factor-anatomy-v1.

Question answered: how broad can the analysis denominator honestly be, and what input facts support the frozen
case studies? It reads ONLY identity and coverage facts from the two pinned `signal-history` commits that the sealed
v1 spec already pins: the PIT universe snapshots (code, name, rank, market cap, shares), the ticker set of the
sealed replay price panels, the dividend-EVENT years of the sealed corporate-events components, and the ticker set of
the frozen accounting snapshot. It never computes, reads into a statistic or prints a price level, a return, a label
or any outcome; price objects are opened only to collect which tickers they contain.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_COMMIT = "4ea107ed0cde289f0a049a65ff13d2441a786710"
ACCOUNTING_COMMIT = "fb6e83743fd8cdba647d1522a4645b662a9d5647"
OUTPUT = "docs/results/kr-factor-anatomy-v1-input-scope-audit.json"


def git_show(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT, stderr=subprocess.DEVNULL)


def read_universe(commit=UNIVERSE_COMMIT):
    rows = []
    for year in range(2013, 2027):
        raw = git_show(commit, f"ledger/universe/kr/krx-universe-{year}.jsonl.gz")
        rows.extend(json.loads(line) for line in gzip.decompress(raw).decode().splitlines())
    return rows


def summarize_universe(rows):
    """Membership scope facts from the PIT snapshots alone."""
    by_date = collections.defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)
    ever120 = {r["ticker"] for r in rows if r["rank"] <= 120}
    ever300 = {r["ticker"] for r in rows if r["rank"] <= 300}
    band = [r for r in rows if 120 < r["rank"] <= 300]
    never = [r for r in band if r["ticker"] not in ever120]
    counts = [len(v) for v in by_date.values()]
    return {"snapshots": len(by_date), "firstSnapshot": min(by_date), "lastSnapshot": max(by_date),
            "rowsPerSnapshot": {"min": min(counts), "max": max(counts)},
            "maxRankPerSnapshot": {"min": min(max(r["rank"] for r in v) for v in by_date.values()),
                                   "max": max(max(r["rank"] for r in v) for v in by_date.values())},
            "fieldsPerRow": sorted(rows[0]), "distinctSecuritiesRank1To120": len(ever120),
            "distinctSecuritiesRank1To300": len(ever300), "securitiesOnlyEverRanked121To300": len(ever300 - ever120),
            "rank121To300NameDates": len(band), "rank121To300NameDatesOfSecuritiesNeverInTop120": len(never),
            "rank121To300NameDatesOfSecuritiesEverInTop120": len(band) - len(never)}


def read_accounting_tickers(commit=ACCOUNTING_COMMIT):
    tickers = set()
    for year in range(2015, 2027):
        raw = git_show(commit, f"ledger/fundamentals/kr-candidate-merged/dart-{year}.jsonl.gz")
        tickers.update(json.loads(line)["ticker"] for line in gzip.decompress(raw).decode().splitlines())
    return tickers


def read_replay_inventory(commit=UNIVERSE_COMMIT):
    """Tickers inside the sealed replay price components and the YEARS in which a dividend event exists per ticker.
    No price level is read into any value."""
    manifest = json.loads(git_show(commit, "ledger/historical/replay-v16/inputs.json"))
    components = manifest["components"]

    def objects(sha):
        return json.loads(gzip.decompress(git_show(commit, f"ledger/replay-inputs/objects/{sha}.json.gz")))

    price_tickers, dividend_years = set(), collections.defaultdict(set)
    for name, shas in sorted(components.items()):
        if name.startswith("price/") and name != "price/source":
            for sha in shas:
                price_tickers.update(r["ticker"] for r in objects(sha) if str(r.get("ticker", "")).endswith(".KS"))
        elif name.startswith("corporate-events/") and name != "corporate-events/source":
            for sha in shas:
                for r in objects(sha):
                    if str(r.get("ticker", "")).endswith(".KS") and (r.get("dividend") or 0) > 0:
                        dividend_years[r["ticker"]].add(name[len("corporate-events/"):][:4])
    lineage = objects(components["price/source"][0])
    kr = next(row for row in lineage if row.get("region") == "KR")
    return {"priceTickers": price_tickers, "dividendYears": {t: sorted(y) for t, y in dividend_years.items()},
            "krPriceLineage": {k: kr.get(k) for k in ("source", "vendor", "distributions", "routes")},
            "replayManifestSha256": manifest["sha256"]}


def per_security(rows, accounting, inventory):
    """One coverage row per security that was ever in the PIT top 120 (the only securities with priced histories)."""
    names = collections.defaultdict(set)
    top = collections.defaultdict(list)
    for r in rows:
        names[r["ticker"]].add(r["name"])
        if r["rank"] <= 120:
            top[r["ticker"]].append(r["date"])
    table = {}
    for ticker in sorted(top):
        dates = sorted(top[ticker])
        years = inventory["dividendYears"].get(ticker, [])
        table[ticker] = {"names": sorted(names[ticker]), "top120Snapshots": len(dates), "firstTop120": dates[0],
                         "lastTop120": dates[-1], "hasFrozenAccountingRecord": ticker in accounting,
                         "hasSealedPricePanel": ticker in inventory["priceTickers"],
                         "yearsWithServedDividendEvent": years, "servedDividendEventYearCount": len(years)}
    return table


def build(rows, accounting, inventory):
    universe = summarize_universe(rows)
    ever120 = {r["ticker"] for r in rows if r["rank"] <= 120}
    return {
        "study": "kr-factor-anatomy-v1", "kind": "OUTCOME_FREE_INPUT_SCOPE_AUDIT",
        "sources": {"universeCommit": UNIVERSE_COMMIT, "accountingCommit": ACCOUNTING_COMMIT,
                    "replayManifestSha256": inventory["replayManifestSha256"]},
        "readsNoPriceLevelReturnLabelOrOutcome": True,
        "universe": universe,
        "pricePanels": {"krTickers": len(inventory["priceTickers"]),
                        "equalsSecuritiesEverInTop120": inventory["priceTickers"] == ever120,
                        "lineage": inventory["krPriceLineage"]},
        "accounting": {"tickersWithAnyFrozenRecord": len(accounting),
                       "withinEverTop120": len(accounting & ever120), "outsideEverTop120": len(accounting - ever120),
                       "everTop120WithoutRecord": len(ever120 - accounting)},
        "dividendEvents": {"securitiesWithAnyServedEvent": len(inventory["dividendYears"]),
                           "note": "Counts of years in which the vendor served at least one distribution event. Not a "
                                   "completeness audit: absence does not prove a security paid nothing."},
        "securities": per_security(rows, accounting, inventory),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=OUTPUT)
    args = parser.parse_args()
    for commit in (UNIVERSE_COMMIT, ACCOUNTING_COMMIT):
        subprocess.check_call(["git", "fetch", "--no-tags", "--depth=1", "--filter=blob:none", "origin", commit],
                              cwd=ROOT, stderr=subprocess.DEVNULL)
    report = build(read_universe(), read_accounting_tickers(), read_replay_inventory())
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("universe", "pricePanels", "accounting")}, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
