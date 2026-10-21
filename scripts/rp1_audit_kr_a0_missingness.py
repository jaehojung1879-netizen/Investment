"""Independent, price-free decomposition of the KR A0 missingness (PR #262).

Reads ONLY pinned Git objects through the same allowlisted `Sources` reader as
the measurement: DART filing records (kr-candidate-merged), PIT KRX universe
membership (ticker/rank/name/date only), and the committed industry intervals,
crosswalk and identity inventory. It never opens a price, benchmark, replay
object, return, label or outcome, and it changes no hypothesis, gate or verdict.

The three price-based eligibility exclusions (signal-date price, 20 traded
sessions, liquidity floor) cannot be applied without prices, so the eligible
set here is a SUPERSET of the measurement's; both scales are published.
Counterfactual rows are COUNT-ONLY bounds and are never measurements.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import datetime as dt
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import kr_alpha_signal_v2 as H2  # noqa: E402
from pipeline import kr_continuing_dividend_sample as COMMON  # noqa: E402
from pipeline import rp1_a0 as A  # noqa: E402
from pipeline import rp1_kr_a0 as K  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402

RESULT = "docs/research-program/results/rp1-kr-a0-measurability-v1.json"
OUTPUT = "docs/research-program/results/rp1-kr-a0-missingness-audit-v1.json"
PRICE_FREE = re.compile(r"ledger/(fundamentals/kr-candidate-merged/dart|universe/kr/krx-universe)-20\d{2}\.jsonl\.gz")
DARK_YEARS = ("2013", "2014", "2015", "2016", "2017")
XBRL = "DART:fnlttXbrl.xml:ORIGINAL"


class PriceFreeSources(S.Sources):
    """The measurement's pinned reader with every price-bearing path refused."""
    def blob(self, commit, path):
        if commit == S.SOURCE_COMMIT and not PRICE_FREE.fullmatch(path):
            raise ValueError("PRICE_OR_OUTCOME_PATH_REFUSED:" + path)
        return super().blob(commit, path)


def deadline(year, code):
    end = dt.date.fromisoformat(DF.period_end(year, code))
    return end + dt.timedelta(days=90 if code == "11011" else 45)


def load(repo):
    source = PriceFreeSources(repo)
    filings, snapshots = defaultdict(list), defaultdict(list)
    for year in range(2015, 2027):
        for row in source.rows(f"ledger/fundamentals/kr-candidate-merged/dart-{year}.jsonl.gz"):
            filings[row["ticker"]].append(row)
    for year in range(2013, 2027):
        for row in source.rows(f"ledger/universe/kr/krx-universe-{year}.jsonl.gz"):
            snapshots[row["date"]].append({"ticker": row["ticker"], "rank": row["rank"], "name": row.get("name")})
    members = S.RAF.MembershipSnapshots([
        {"date": d, "members": [r["ticker"] for r in sorted(rs, key=lambda r: (r["rank"], r["ticker"]))[:120]],
         "rows": {r["ticker"]: r for r in rs}} for d, rs in sorted(snapshots.items())])
    inventory = source.json(S.IDENTITIES)
    identities = {r["ticker"]: i["issuerId"] for i in inventory["issuers"] for r in i["securities"]}
    return (source, filings, members, source.json(S.INTERVALS), source.json(S.CROSSWALK), identities,
            set(source.json(S.KR_PROVENANCE)["terminalSecurities"]))


def nonprice_eligibility(rows, day):
    """`rp1_kr_a0.eligibility` minus the three price-based H2 exclusions."""
    base = {}
    for r in rows:
        reasons = ["DEFINITIONALLY_EXCLUDED_FINANCIAL"] if r["industry"] == "FINANCIALS" else []
        if not r["issuerId"]:
            reasons.append("IDENTITY_UNRESOLVED")
        if r["isPreferredShare"] is not False:
            reasons.append("PREFERRED_SHARE")
        if not r["industry"]:
            reasons.append("INDUSTRY_UNCLASSIFIED")
        base[r["ticker"]] = reasons
    groups = Counter(r["industry"] for r in rows if not base[r["ticker"]])
    for r in rows:
        if not base[r["ticker"]] and groups[r["industry"]] < H2.MIN_INDUSTRY_MEMBERS:
            base[r["ticker"]].append("INDUSTRY_BELOW_MIN_MEMBERS")
    return base


def cross_sections(dates, members, intervals, crosswalk, identities):
    for day in dates:
        snap = members.on(day)  # strictly earlier snapshot
        rows = []
        for t in sorted(snap["members"]):
            industry, _ = S.KI.industry_of(intervals, crosswalk, t, day)
            name = snap.get("rows", {}).get(t, {}).get("name")
            rows.append({"ticker": t, "industry": industry, "issuerId": identities.get(t),
                         "isPreferredShare": None if not name else not COMMON.is_likely_common_share(name)})
        yield day, rows, nonprice_eligibility(rows, day)


def h1_pass(filings, sections, *, terminal=frozenset(), detail=False):
    histories = {t: A.FilingHistory(t, rs, adapter=K.Filings()) for t, rs in filings.items()}
    index = {t: {(r["fiscalYear"], r["reportCode"]): r for r in rs} for t, rs in filings.items()}
    by_year = defaultdict(lambda: {"eligible": 0, "measured": 0, "missing": Counter()})
    exclusions, terminal_reasons, vintage = Counter(), Counter(), Counter()
    for day, rows, eligibility in sections:
        year = by_year[day[:4]]
        for r in rows:
            t, reasons = r["ticker"], eligibility[r["ticker"]]
            if t in terminal:
                terminal_reasons[reasons[0] if reasons else "ELIGIBLE_WITHOUT_PRICE_RULES"] += 1
            if reasons:
                exclusions[reasons[0]] += 1
                continue
            year["eligible"] += 1
            state = histories[t].at(day) if t in histories else {"flag": None, "reason": "NO_FILING_STORE"}
            if state["flag"] is not None:
                year["measured"] += 1
                continue
            year["missing"][state["reason"]] += 1
            if detail and state["reason"] in ("NO_VISIBLE_FILING", "INCOMPLETE_TTM_CHAIN", "REPORT_STALE_OVER_180_DAYS"):
                d = dt.date.fromisoformat(day)
                # A filing whose statutory deadline has passed but whose ONLY
                # stored receipt is later: amendment vintage or a late original.
                late = any(deadline(*k) < d <= dt.date.fromisoformat(rec["availableFrom"])
                           for k, rec in index.get(t, {}).items())
                vintage[state["reason"] + (":STORED_ONLY_AS_LATER_VINTAGE" if late else ":NO_LATER_VINTAGE")] += 1
    eligible = sum(v["eligible"] for v in by_year.values())
    measured = sum(v["measured"] for v in by_year.values())
    out = {"eligible": eligible, "measured": measured, "rate": measured / eligible if eligible else None}
    if detail:
        out.update(byYear={y: {"eligible": v["eligible"], "measured": v["measured"],
                               "missing": dict(sorted(v["missing"].items()))} for y, v in sorted(by_year.items())},
                   nonPriceExclusions=dict(sorted(exclusions.items())),
                   terminalSecurityPrimaryReasons=dict(sorted(terminal_reasons.items())),
                   vintageAttribution=dict(sorted(vintage.items())))
    return out


def published_scale(result):
    by_year = defaultdict(Counter)
    for d in result["byDate"]:
        by_year[d["date"][:4]]["eligible"] += d["eligible"]
        for h in A.HYPOTHESES:
            by_year[d["date"][:4]][h] += d["hypotheses"][h]["measured"]
    total = sum(v["eligible"] for v in by_year.values())
    dark = sum(by_year[y]["eligible"] for y in DARK_YEARS)
    need = 0.60 * total
    peer = [p for p in result["peerCompletenessByDate"] if p["eligible"]]
    vetoed = [p for p in peer if p["eligibleMissingPastWindow"] or p["eligibleMissingMarketCap"]]
    single = [p for p in vetoed if p["eligibleMissingPastWindow"] + p["eligibleMissingMarketCap"] == 1]
    return {
        "byYear": {y: dict(sorted(v.items())) for y, v in sorted(by_year.items())},
        "historyDepth": {"darkYears": list(DARK_YEARS), "darkEligible": dark, "darkShare": dark / total,
                         "darkMeasuredH1H2": sum(by_year[y][h] for y in DARK_YEARS for h in ("A-H1", "A-H2")),
                         "fullPeriodCeilingIfEvery2018PlusCellMeasured": 1 - dark / total,
                         "required2018PlusRateFor60Pct": need / (total - dark)},
        "h3Propagation": {
            "datesWithEligible": len(peer), "datesWithheld": len(vetoed),
            "missingWindowCells": sum(p["eligibleMissingPastWindow"] for p in peer),
            "missingMarketCapCells": sum(p["eligibleMissingMarketCap"] for p in peer),
            "eligibleCellsOnWithheldDates": sum(p["eligible"] for p in vetoed),
            "measuredOnWithheldDates": sum(p["h3Measured"] for p in vetoed),
            "cleanDatesFullyMeasured": all(p["h3Measured"] == p["eligible"] for p in peer if p not in vetoed),
            "singleNameVetoDates": len(single), "eligibleCellsOnSingleNameVetoDates": sum(p["eligible"] for p in single),
            "missingPerWithheldDate": dict(sorted(Counter(p["eligibleMissingPastWindow"] + p["eligibleMissingMarketCap"]
                                                         for p in vetoed).items()))}}


def audit(repo=ROOT):
    result = json.loads((Path(repo) / RESULT).read_text())
    source, filings, members, intervals, crosswalk, identities, terminal = load(repo)
    dates = [d["date"] for d in result["byDate"]]
    sections = list(cross_sections(dates, members, intervals, crosswalk, identities))
    actual = h1_pass(filings, sections, terminal=terminal, detail=True)
    relabelled = deepcopy(filings)
    for rows in relabelled.values():
        for r in rows:
            if r["source"] == XBRL:
                r["fsDiv"] = "CFS"  # the per-account XBRL lineage says CFS
    early, moved, moved7 = deepcopy(filings), 0, 0
    for rows in early.values():
        for r in rows:
            due = deadline(r["fiscalYear"], r["reportCode"])
            late_days = (dt.date.fromisoformat(r["availableFrom"]) - due).days
            if late_days > 0:
                moved, moved7 = moved + 1, moved7 + (late_days > 7)
                r["availableFrom"], r["receiptNos"] = due.isoformat(), [due.strftime("%Y%m%d") + "999999"]
    records = [r for rs in filings.values() for r in rs]
    xbrl = [r for r in records if r["source"] == XBRL]
    report = {
        "id": "rp1-kr-a0-missingness-audit-v1",
        "role": "INDEPENDENT_POST_MEASUREMENT_AUDIT_NO_GATE_NO_VERDICT_CHANGE",
        "measurementResultSha256": __import__("hashlib").sha256((Path(repo) / RESULT).read_bytes()).hexdigest(),
        "inputs": "pinned DART filing records + PIT universe membership (ticker/rank/name) + committed industry/identity; no price",
        "sourceReceipts": source.receipts,
        "publishedScale": published_scale(result),
        "reconstructedH1NonPriceScale": actual,
        "storeFacts": {
            "records": len(records), "xbrlOriginalRecords": len(xbrl),
            "xbrlOriginalPeriods": dict(sorted(Counter(f"{r['fiscalYear']}:{r['reportCode']}" for r in xbrl).items())),
            "xbrlOriginalWithFsDiv": sum(r.get("fsDiv") in ("CFS", "OFS") for r in xbrl),
            "xbrlOriginalWithOperatingIncome": sum("영업이익" in (r.get("accounts") or {}) for r in xbrl),
            "unknownBasisRecords": sum(r.get("fsDiv") not in ("CFS", "OFS") for r in records),
            "oneReceiptPerRecord": all(len(r.get("receiptNos") or []) == 1 for r in records),
            "recordsAfterStatutoryDeadline": moved, "recordsMoreThan7DaysAfterDeadline": moved7,
            "invalidReceiptDateRecords": [{k: r[k] for k in ("id", "availableFrom", "receiptNos", "source")}
                                          for r in records if K.Filings.visible_day(r) is None]},
        "countOnlyBounds": {
            "note": "Bounds on what a data repair could recover. Never measurements, never gate inputs.",
            "basisRelabelXbrlAsCFS": h1_pass(relabelled, sections),
            "visibleAtStatutoryDeadlineLookAheadUpperBound": h1_pass(early, sections)},
        "accessCounters": {"priceReads": 0, "outcomeReads": 0, "forwardPriceReads": 0, "labelReads": 0, "modelFits": 0},
    }
    if any("prices/" in key or "replay-inputs/" in key or "historical/" in key for key in source.receipts):
        raise AssertionError("PRICE_PATH_OPENED")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    text = json.dumps(audit(args.repo), ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n"
    if args.write:
        (ROOT / OUTPUT).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
