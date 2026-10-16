"""Read-only, outcome-free source census. Default: print the plan, open no data.

Opt-in --inspect reads only the fixed source allowlist from LOCAL Git objects.
It cannot fetch, collect, train, value a portfolio, read labels or write a file.
Redirect stdout to a new review artifact explicitly. No input price is emitted.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import experiment_workbench as W  # noqa: E402
from pipeline import kr_industry_anatomy as KI  # noqa: E402
from pipeline import kr_value_quality_catalyst as KQ  # noqa: E402
from pipeline import regional_alpha_features as RAF  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402
from pipeline import replay_inputs as RI  # noqa: E402
from pipeline import us_cash_profitability as CP  # noqa: E402

SOURCE_COMMIT = "1bf68f59cffa20239977e2cfaa0f35a07d0ec884"
CODE_BASE = "002b56434e3aa3e845798ec2ea7ca6d9267e3f7a"
MANIFEST = "ledger/historical/replay-v16/inputs.json"
MANIFEST_SHA = "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2"
MEMBERS = "research_specs/alpha-opportunity-model-v1-us-membership.json.gz"
SECTORS = "data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz"
IDENTITIES = "data/kr-industry-membership-foundation-v1/identity-inventory.json"
KR_PROVENANCE = "data/kr-industry-membership-foundation-v1/identity-provenance.json"
INTERVALS = "data/kr-industry-membership-foundation-v4/state/intervals.json.gz"
CROSSWALK = "research_specs/kr-industry-membership-foundation-v4/crosswalk.json"
US_IDENTITY = "data/research/us-dual-benchmark-v1/us-universe-coverage-manifest.csv.gz"
COARSE_LABELS = frozenset({"Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy",
    "Financials", "Health Care", "Industrials", "Information Technology", "Materials", "Real Estate", "Utilities",
    "Telecommunication Services"})  # old label retained; no retrospective remapping


def finalize_census(report):
    """Presence is weaker than taxonomy consistency. Keep both measurements."""
    us = report["markets"]["US"]
    groups = us["byIndustry"]
    unexpected = {k: v["memberDates"] for k, v in groups.items() if k not in COARSE_LABELS and k != "UNRESOLVED"}
    us["industryLabelCensus"] = {"unexpectedOrFinerLabelMemberDates": sum(unexpected.values()),
        "unexpectedOrFinerLabelPct": pct(sum(unexpected.values()), us["totals"]["memberDates"]),
        "rawLabels": unexpected, "taxonomyVersionVerified": False,
        "note": "industry flag measures a nonmissing source label, not a verified consistent GICS sector"}
    report["runtime"] = {"python": sys.version.split()[0], "packages": {
        name: importlib.metadata.version(name) for name in ("pandas", "numpy", "exchange-calendars")}}
    report["codeHashes"] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in (
        "scripts/inspect_experiment_sources.py", "pipeline/experiment_workbench.py", "pipeline/alpha_opportunity_features.py",
        "pipeline/kr_value_quality_catalyst.py", "pipeline/dart_derive.py", "pipeline/finnhub_derive.py",
        "pipeline/us_cash_profitability.py", "pipeline/regional_alpha_features.py", "pipeline/kr_industry_anatomy.py",
        "pipeline/replay_calendar.py")}
    return report


class Sources:
    """Pinned local Git reads, no implicit promisor network requests."""
    def __init__(self, repo):
        self.repo, self.receipts = Path(repo), {}
        self.allowed_objects = set()

    def blob(self, commit, path):
        main_paths = {MEMBERS, SECTORS, IDENTITIES, KR_PROVENANCE, INTERVALS, CROSSWALK, US_IDENTITY}
        raw_path = re.fullmatch(r"ledger/(?:fundamentals/(?:kr-candidate-merged/dart|us/finnhub)|universe/kr/krx-universe|prices/kr/krx-prices)-20\d{2}\.jsonl\.gz", path)
        object_ref = path.removeprefix("ledger/replay-inputs/objects/").removesuffix(".json.gz")
        object_allowed = (path == "ledger/replay-inputs/objects/" + object_ref + ".json.gz"
                          and object_ref in self.allowed_objects)
        permitted = ((commit == CODE_BASE and path in main_paths)
                     or (commit == SOURCE_COMMIT and (path == MANIFEST or raw_path
                         or object_allowed)))
        if not permitted:
            raise ValueError("PATH_OUTSIDE_RAW_INPUT_ALLOWLIST:" + path)
        raw = subprocess.check_output(["git", "cat-file", "blob", f"{commit}:{path}"],
                                      cwd=self.repo, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
        key = commit + ":" + path
        self.receipts[key] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        return raw

    def local(self, path):
        # Read committed main bytes, never a mutable worktree data substitute.
        return self.blob(CODE_BASE, path)

    def json(self, path):
        raw = self.local(path)
        return json.loads(gzip.decompress(raw) if path.endswith(".gz") else raw)

    def rows(self, path):
        return [
            json.loads(line) for line in gzip.decompress(self.blob(SOURCE_COMMIT, path)).splitlines() if line.strip()]

    def component(self, ref):
        if not re.fullmatch(r"[0-9a-f]{64}", ref):
            raise ValueError("INVALID_CONTENT_REFERENCE")
        raw = gzip.decompress(self.blob(SOURCE_COMMIT, "ledger/replay-inputs/objects/" + ref + ".json.gz"))
        if hashlib.sha256(raw).hexdigest() != ref:
            raise ValueError("SOURCE_CONTENT_CHANGED")
        return json.loads(raw)


def pct(n, d):
    return round(100 * n / d, 3) if d else None


def summary(rows, flags):
    return {"memberDates": len(rows), **{f: {"count": sum(r[f] for r in rows),
                                           "pct": pct(sum(r[f] for r in rows), len(rows))} for f in flags}}


class FilingAvailability:
    """Cache only a visible prefix's static arithmetic; recheck age on each date."""
    def __init__(self, records, market):
        self.market = market
        pairs = sorted(((CP.visible_day(r).isoformat() if market == "US" else r.get("availableFrom"), r)
                        for r in records if (CP.visible_day(r) if market == "US" else r.get("availableFrom"))),
                       key=lambda x: x[0])
        self.days, self.records = [d for d, _ in pairs], [r for _, r in pairs]
        self.cache = {}

    def at(self, date):
        n = bisect_left(self.days, date)  # source date itself is withheld
        if not n:
            return False, "NO_VISIBLE_FILING", None
        if n not in self.cache:
            # These existing builders are readers over this private in-memory
            # source copy. Avoid deep-copying entire cumulative filing histories
            # per prefix; they independently recheck public visibility below.
            visible = self.records[:n]
            if self.market == "KR":
                values, info = KQ.accounting_values(visible, date)
                ready = (values.get("assets") is not None and values["assets"] > 0
                         and all(values.get(k) is not None for k in ("netIncomeTtm", "ocfTtm")))
                self.cache[n] = ready, ("AVAILABLE" if ready else info["status"] + ":INCOMPLETE_CORE"), info.get("availableFrom")
            else:
                values = CP.features_as_of(list(visible), date)
                ready = all(values[k] is not None for k in (
                    "cashOperatingProfitability", "accrualsToAssets", "operatingProfitabilityToAssets"))
                reason = "AVAILABLE" if ready else "+".join(sorted(set(values["state"][k] for k in (
                    "cashOperatingProfitability", "accrualsToAssets", "operatingProfitabilityToAssets"))))
                self.cache[n] = ready, reason, values["reportEnd"]
        ready, reason, stamp = self.cache[n]
        if self.market == "US" and stamp and (pd.Timestamp(date) - pd.Timestamp(stamp)).days > CP.MAX_REPORT_AGE_DAYS:
            return False, CP.REPORT_STALE, self.days[n - 1]
        return ready, reason, self.days[n - 1]


def filing_inventory(rows, market):
    visible = [CP.visible_day(r).isoformat() if market == "US" else r.get("availableFrom") for r in rows]
    collected = [str(r.get("collectedAt")) for r in rows if r.get("collectedAt")]
    receipt_bad = sum(not r.get("receiptNos") or {n[:8] for n in r["receiptNos"]} !=
                      {str(r.get("availableFrom", "")).replace("-", "")} for r in rows) if market == "KR" else None
    cohorts = defaultdict(lambda: Counter())
    if market == "US":
        for r in rows:
            c = cohorts[str(r.get("collectedAt", "MISSING"))[:10]]
            c["filings"] += 1
            c["emptyBalanceSheet"] += not bool((r.get("statements") or {}).get("bs"))
    return {"rows": len(rows), "distinctIds": len({r["id"] for r in rows}),
            "tickers": len({r["ticker"] for r in rows}),
            "publicDateRange": [min(filter(None, visible)), max(filter(None, visible))],
            "publicDateMissing": sum(d is None for d in visible),
            "collectedAtRange": [min(collected), max(collected)] if collected else None,
            "collectedAtMissing": len(rows) - len(collected), "receiptDateMismatch": receipt_bad,
            "acceptedDateMissing": sum(not r.get("acceptedDate") for r in rows) if market == "US" else None,
            "collectionCohorts": dict(sorted(cohorts.items()))}


def inspect(repo):
    source = Sources(repo)
    manifest = json.loads(source.blob(SOURCE_COMMIT, MANIFEST))
    if manifest["sha256"] != MANIFEST_SHA or RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != MANIFEST_SHA:
        raise ValueError("REPLAY_MANIFEST_CHANGED")
    source.allowed_objects = {ref for name, refs in manifest["components"].items()
                              if name.startswith("price/20") or name == "macro" for ref in refs}
    # Only raw input components are allowed. Historical signals/results/labels
    # are never opened, even to estimate coverage.
    prices, duplicate_prices = defaultdict(set), 0
    for name, refs in sorted(manifest["components"].items()):
        if name.startswith("price/20"):
            for ref in refs:
                for r in source.component(ref):
                    if r.get("Close") is not None and r["Close"] > 0:
                        duplicate_prices += r["date"] in prices[r["ticker"]]
                        prices[r["ticker"]].add(r["date"])
    macro_rows = [r for ref in manifest["components"]["macro"] for r in source.component(ref)]
    macro_release_rows = sum(bool(r.get("availableFrom") or r.get("realtime_start")) for r in macro_rows)
    kr_universe, traded = defaultdict(list), defaultdict(set)
    for year in range(2013, 2027):
        for r in source.rows(f"ledger/universe/kr/krx-universe-{year}.jsonl.gz"):
            kr_universe[r["date"]].append(r)
        for r in source.rows(f"ledger/prices/kr/krx-prices-{year}.jsonl.gz"):
            if r.get("close", 0) > 0 and r.get("volume", 0) > 0:
                traded[r["ticker"]].add(r["date"])
    snapshots = [{"date": day, "members": [r["ticker"] for r in sorted(rows, key=lambda r: (r["rank"], r["ticker"]))[:120]]}
                 for day, rows in sorted(kr_universe.items())]
    us = source.json(MEMBERS)
    sectors = RAF.MembershipSnapshots(source.json(SECTORS)["snapshots"])
    memberships = {"KR": RAF.MembershipSnapshots(snapshots), "US": RAF.MembershipSnapshots(us["snapshots"])}
    intervals, crosswalk = source.json(INTERVALS), source.json(CROSSWALK)
    inventory, provenance = source.json(IDENTITIES), source.json(KR_PROVENANCE)
    kr_ids = {s["ticker"]: i["issuerId"] for i in inventory["issuers"] for s in i["securities"]}
    us_ids = list(csv.DictReader(io.StringIO(gzip.decompress(source.local(US_IDENTITY)).decode())))
    us_ids = {r["symbol"]: r for r in us_ids if r["inSp500"] == "True"}
    filings = {"KR": [], "US": []}
    for year in range(2015, 2027):
        filings["KR"].extend(source.rows(f"ledger/fundamentals/kr-candidate-merged/dart-{year}.jsonl.gz"))
    for year in range(2011, 2028):
        filings["US"].extend(source.rows(f"ledger/fundamentals/us/finnhub-{year}.jsonl.gz"))
    caches = {}
    for market, records in filings.items():
        grouped = defaultdict(list)
        for r in records:
            grouped[r["ticker"]].append(r)
        caches[market] = {t: FilingAvailability(v, market) for t, v in grouped.items()}
    print("Raw input census loaded; computing availability only", file=sys.stderr)
    flags = ("price", "history253", "financialCore", "industry", "issuerMapped", "joint", "jointWithPitMacro")
    markets = {}
    for market in ("KR", "US"):
        print("Availability census: " + market, file=sys.stderr)
        days = RC.sessions("2011-01-01", manifest["through"], market)
        weekly = days.to_series().groupby(days.to_period("W")).max()
        dates = [str(d.date()) for d in weekly if "2013-01-01" <= str(d.date()) <= manifest["through"]
                 and (str(d.date()) != manifest["through"] or d.weekday() == 4)]
        # Full calendar determines completed weeks; an incomplete final Monday
        # is not manufactured into a completed weekly signal.
        all_days = RC.sessions("2011-01-01", "2026-10-01", market)
        dates = [d for d in dates if all_days[all_days.searchsorted(d, side="right")].isocalendar()[:2]
                 != pd.Timestamp(d).isocalendar()[:2]]
        rows, by_date, reasons = [], [], Counter()
        for date in dates:
            snapshot = memberships[market].on(date)
            if snapshot is None:
                continue
            sector = sectors.on(date) if market == "US" else None
            members = snapshot["members"]
            start = days.searchsorted(date) - 252
            window = [str(d.date()) for d in days[max(0, start):days.searchsorted(date) + 1]]
            current = []
            for ticker in members:
                ready, reason, _ = caches[market][ticker].at(date) if ticker in caches[market] else (False, "NO_FILING_STORE", None)
                group, industry_status = (KI.industry_of(intervals, crosswalk, ticker, date) if market == "KR"
                                          else (((sector or {}).get("rows") or {}).get(ticker, {}).get("sector"), "DATED_SNAPSHOT"))
                observed_prices = traded[ticker] if market == "KR" else prices[ticker]
                row = {"date": date, "industryName": group or "UNRESOLVED", "price": date in observed_prices,
                       "history253": len(window) == 253 and all(d in observed_prices for d in window),
                       "financialCore": ready, "industry": group is not None,
                       "issuerMapped": ticker in kr_ids if market == "KR" else bool(us_ids.get(ticker, {}).get("cik"))}
                row["joint"] = row["price"] and row["history253"] and ready and row["industry"]
                row["jointWithPitMacro"] = row["joint"] and macro_release_rows > 0 and macro_release_rows == len(macro_rows)
                reasons[reason] += 1
                current.append(row)
            rows.extend(current)
            by_date.append({"date": date, **summary(current, flags)})
        years, groups = defaultdict(list), defaultdict(list)
        for r in rows:
            years[r["date"][:4]].append(r)
            groups[r["industryName"]].append(r)
        core_dates = [d["date"] for d in by_date if d["joint"]["count"] > 0]
        broad_dates = [d["date"] for d in by_date if d["joint"]["count"] >= 30]
        ever = set(t for s in memberships[market].snapshots for t in s["members"])
        markets[market] = {"weeklySignalRange": [by_date[0]["date"], by_date[-1]["date"]],
            "weeks": len(by_date), "everMembers": len(ever), "totals": summary(rows, flags),
            "firstJointInputDate": core_dates[0] if core_dates else None,
            "firstAtLeast30JointInputs": broad_dates[0] if broad_dates else None,
            "lastAtLeast30JointInputs": broad_dates[-1] if broad_dates else None,
            "latestCandidatesH126AndH252": by_date[-1],
            "byYear": {k: summary(v, flags) for k, v in sorted(years.items())},
            "byIndustry": {k: summary(v, flags) for k, v in sorted(groups.items())},
            "financialReasons": dict(sorted(reasons.items())),
            "weeklyAvailabilitySha256": RI.digest(by_date),
            "recentWeeklyAvailability": [{"date": d["date"], "memberDates": d["memberDates"],
                                           **{f: d[f]["count"] for f in flags}} for d in by_date[-52:]],
            "calendarOnlyMaturityCapacity": {str(h): sum(1 for d in dates if all_days.searchsorted(d, side="right") + h < len(all_days)
                and str(all_days[all_days.searchsorted(d, side="right") + h].date()) <= manifest["through"]) for h in W.HORIZONS},
            "filings": filing_inventory(filings[market], market),
            "priceTapeRange": [min(d for t in ever for d in prices[t]), max(d for t in ever for d in prices[t])],
            "membersWithoutAnyPricePanel": sum(not prices[t] for t in ever),
            "industryEvidence": "PARTIALLY_RECONSTRUCTED_V4" if market == "KR" else "DATED_COMMUNITY_SNAPSHOTS_NOT_OFFICIAL_SP_RECORD"}
    terminal = provenance["terminalSecurities"]
    markets["KR"]["identity"] = {"mappedSecurities": len(kr_ids), "issuers": inventory["issuerCount"],
        "terminalUnresolved": len(terminal), "terminalUnresolvedPctOfEverMembers": pct(len(terminal), markets["KR"]["everMembers"]),
        "retrospectiveIssuerBridge": provenance["retrospectiveIdentityBridgeIsNotDatedIssuerProof"]}
    cats = Counter(r["sp500IdentityCategory"] for r in us_ids.values())
    markets["US"]["identity"] = {"sourceCategories": dict(sorted(cats.items())),
        "metadataMissingForMemberSymbols": sorted(set(t for s in memberships["US"].snapshots for t in s["members"]) - set(us_ids)),
        "renameMappingsNotApplied": sum(bool(r["renameSuccessor"]) for r in us_ids.values()),
        "cikMissing": sum(not r["cik"] for r in us_ids.values()), "permanentShareClassIdVerified": False}
    return finalize_census({"contract": W.VERSION, "status": "INPUT_READINESS_ONLY", "sourceCommit": SOURCE_COMMIT,
            "mainBase": CODE_BASE, "through": manifest["through"], "manifestSha256": MANIFEST_SHA,
            "financialCoreDefinition": {"KR": "positive assets + nonmissing netIncomeTTM + OCF_TTM, existing KQ.accounting_values",
                "US": "three nonmissing CP cash/accrual/operating-to-assets ratios, 180d report freshness"},
            "jointDefinition": "same-session tradable price + 253-session history + financialCore + industry; identity audit separate",
            "macro": {"rows": len(macro_rows), "rowsWithReleaseOrVintage": macro_release_rows,
                      "pitJoinStatus": "BLOCKED_RELEASE_AND_VINTAGE_UNRESOLVED"},
            "duplicatePriceKeys": duplicate_prices, "markets": markets,
            "historicalExecutionAuthorized": False, "labelReads": 0, "modelFits": 0,
            "sources": dict(sorted(source.receipts.items()))})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = inspect(args.repo) if args.inspect else {
        "contract": W.VERSION, "status": "PREVIEW_ONLY", "sourceCommit": SOURCE_COMMIT,
        "historicalExecutionAuthorized": False, "sourceReads": 0,
        "scope": "fixed raw input census only; no outcomes, labels, training or collection"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
