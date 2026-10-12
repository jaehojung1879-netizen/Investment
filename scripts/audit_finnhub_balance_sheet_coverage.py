"""Outcome-free audit of the US Finnhub balance-sheet coverage loss, read from the stored records only.

    python scripts/audit_finnhub_balance_sheet_coverage.py --from-git origin/signal-history~0 [--output PATH]
    python scripts/audit_finnhub_balance_sheet_coverage.py --store DIR      # DIR holds finnhub-*.jsonl.gz

It reads the immutable shards and measures; it writes nothing into them, calls no vendor, imputes no account and computes no return,
IC or portfolio. The output is deterministic for a given store (no wall-clock value is written), and names the shard digests and the
git commit it read, so the committed copy can be re-derived byte for byte.

What it can and cannot say is part of the output (`evidenceGap`): the collector stores `report.bs` and nothing else, so whether the
vendor omitted the balance sheet or moved it to a key the collector does not read is NOT answerable from the store.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_derive as US  # noqa: E402
from pipeline import finnhub_fundamentals as FF  # noqa: E402
from pipeline import finnhub_response_health as FH  # noqa: E402
from pipeline import us_cash_profitability as CP  # noqa: E402

OUTPUT = ROOT / "docs/us-readiness/us-finnhub-balance-sheet-coverage-audit-v1.json"
MEMBERSHIP = ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz"
STORE_PATH = "ledger/fundamentals/us"
CONTRACT = "US_FINNHUB_BALANCE_SHEET_COVERAGE_AUDIT_V1"
# The September collection is the one the P4 preflight (#232) called normal; October is everything collected on or after this day.
COHORT_SPLIT = "2026-10-01"
FIRST_AS_OF = dt.date(2026, 6, 5)
LAST_AS_OF = dt.date(2026, 10, 9)
REFERENCE_FROM = "2026-01-01"          # September-cohort filings of this period on form the recent-period comparison


def read_store(directory: Path) -> tuple[list[dict], list[dict]]:
    rows, shards = [], []
    for path in sorted(Path(directory).glob("finnhub-*.jsonl.gz")):
        raw = path.read_bytes()
        records = [json.loads(line) for line in gzip.decompress(raw).decode("utf-8").split("\n") if line.strip()]
        rows.extend(records)
        shards.append({"shard": path.name, "rows": len(records), "sha256": hashlib.sha256(raw).hexdigest()})
    return rows, shards


def extract_from_git(ref: str, target: Path) -> str:
    commit = subprocess.run(["git", "rev-parse", ref], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    archive = subprocess.run(["git", "archive", commit, STORE_PATH], capture_output=True, check=True, cwd=ROOT).stdout
    subprocess.run(["tar", "-x", "-C", str(target)], input=archive, check=True)
    return commit


def pct(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 3) if whole else None


def day(record: dict) -> str:
    return str(record.get("collectedAt") or "")[:10]


def has_section(record: dict, name: str) -> bool:
    return bool((record.get("statements") or {}).get(name))


def assets_entry(record: dict) -> dict | None:
    for entry in (record.get("statements") or {}).get("bs") or []:
        if FF.strip_namespace(entry.get("concept")) in US.ASSETS and isinstance(entry.get("value"), (int, float)):
            return entry
    return None


def cohort_row(rows: list[dict]) -> dict:
    n = len(rows)
    stated = [(r, assets_entry(r)) for r in rows]
    classes = Counter()
    accepted = 0
    for r, entry in stated:
        if entry is None:
            continue
        resolved = FF.resolve_units(r)
        classes[FF.value_class(r, entry, resolved)] += 1
        accepted += US.amount(r, "bs", US.ASSETS, resolved) is not None
    lag = sorted((dt.date.fromisoformat(day(r)) - dt.date.fromisoformat(str(r["availableFrom"])[:10])).days for r in rows
                 if r.get("collectedAt") and r.get("availableFrom"))
    absent = sum(not has_section(r, "bs") for r in rows)
    return {
        "filings": n,
        "balanceSheetPresent": n - absent,
        "balanceSheetAbsent": absent,
        "balanceSheetAbsentPct": pct(absent, n),
        "assetsTagStated": sum(e is not None for _, e in stated),
        "assetsAcceptedAsCurrencyByTheFeaturePath": accepted,
        "assetsStatedValueClass": dict(sorted(classes.items())),
        "incomeStatementPresent": sum(has_section(r, "ic") for r in rows),
        "cashFlowPresent": sum(has_section(r, "cf") for r in rows),
        "acceptedDatePresent": sum(bool(r.get("acceptedDate")) for r in rows),
        "collectedMinusFiledDaysMedian": statistics.median(lag) if lag else None,
        "collectedMinusFiledDaysMax": max(lag) if lag else None,
    }


def feature_coverage(by_ticker: dict[str, list[dict]], tickers: list[str], as_of: dt.date, observed_before: bool) -> dict:
    states, accrual = Counter(), Counter()
    for t in tickers:
        records = by_ticker.get(t, [])
        if observed_before:
            records = [r for r in records if day(r) < as_of.isoformat()]
        feat = CP.features_as_of(records, as_of.isoformat())
        states[feat["state"]["cashOperatingProfitability"]] += 1
        accrual[feat["state"]["accrualsToAssets"]] += 1
    n = len(tickers)
    return {"asOf": as_of.isoformat(), "tickers": n, "cashOperatingProfitability": dict(sorted(states.items())),
            "availablePct": pct(states.get(CP.AVAILABLE, 0), n), "accrualsToAssets": dict(sorted(accrual.items()))}


def build(rows: list[dict], shards: list[dict], source: dict) -> dict:
    early = [r for r in rows if day(r) < COHORT_SPLIT]
    late = [r for r in rows if day(r) >= COHORT_SPLIT]
    early_ids = {r["id"] for r in early}
    recent_september = [r for r in early if r["periodEnd"] >= REFERENCE_FROM]
    # The vocabulary / size comparison is against HEALTHY recent filings (those that do state a balance sheet), by design:
    # it asks whether the income and cash-flow sections of the October filings look like a healthy filing's. The unfiltered
    # recent September row is reported beside it so the healthy subset is never mistaken for the population.
    reference = [r for r in recent_september if has_section(r, "bs")]

    by_day = defaultdict(list)
    for r in rows:
        by_day[day(r)].append(r)
    cohorts = {"byCollectionDay": {d: cohort_row(v) for d, v in sorted(by_day.items())},
               "september": cohort_row(early), "october": cohort_row(late),
               "septemberFilingsOfRecentPeriods": cohort_row(recent_september),
               "referenceHealthyRecentSeptember": cohort_row(reference)}

    def concepts(r, s):
        return [e.get("concept") for e in (r.get("statements") or {}).get(s) or []]

    vocabulary = {}
    for s in ("ic", "cf"):
        late_v, ref_v = Counter(), Counter()
        for r in late:
            late_v.update(set(concepts(r, s)))
        for r in reference:
            ref_v.update(set(concepts(r, s)))
        vocabulary[s] = {"lateDistinct": len(late_v), "referenceDistinct": len(ref_v),
                         "referenceConceptsMissingFromLateAtLeast20Filings": sorted(k for k, v in ref_v.items() if v >= 20 and k not in late_v),
                         "lateMedianEntries": statistics.median(len(concepts(r, s)) for r in late) if late else None,
                         "referenceMedianEntries": statistics.median(len(concepts(r, s)) for r in reference) if reference else None}

    ceiling = max((r["availableFrom"] for r in early), default="")
    arrivals = [r for r in late if r["availableFrom"] <= ceiling]
    absent_breakdown = Counter((r["form"], r.get("requestedFreq"), r.get("fiscalQuarter")) for r in late if not has_section(r, "bs"))
    early_absent = [r for r in early if not has_section(r, "bs")]
    quarantine = FH.balance_sheet_quarantine(rows)
    by_ticker = defaultdict(list)
    for r in rows:
        by_ticker[r["ticker"]].append(r)
    late_tickers = sorted({r["ticker"] for r in late})
    prior_complete = [t for t in late_tickers if any(has_section(r, "bs") for r in by_ticker[t] if day(r) < COHORT_SPLIT)]

    members = json.loads(gzip.decompress(MEMBERSHIP.read_bytes()))["snapshots"][-1]
    universe = sorted(t for t in members["members"] if t in by_ticker)
    first_observed = min(day(r) for r in rows)
    as_of = []
    d = FIRST_AS_OF
    while d <= LAST_AS_OF:
        as_of.append(d)
        d += dt.timedelta(days=7)
    coverage = {
        "universe": {"basis": "tickers of the latest committed S&P 500 snapshot that have any stored filing; a measurement universe, "
                              "not a historical membership claim", "snapshotDate": members["date"], "tickers": len(universe)},
        "asStoredAtThisCommit": [feature_coverage(by_ticker, universe, a, False) for a in as_of],
        "knownByObservationDate": [feature_coverage(by_ticker, universe, a, True) for a in as_of if a.isoformat() > first_observed],
        "readingNote": "asStored lets every stored filing count from its filing date; knownByObservationDate lets a filing count only "
                       "from the day the collector first stored it, which is what a live signal on that date could have used; dates on or before the "
                       "first collection day are omitted there because the store did not exist yet",
    }

    both_freq = {f: cohort_row([r for r in late if r.get("requestedFreq") == f])["balanceSheetAbsentPct"] for f in ("quarterly", "annual")}
    size_ratio = {s: (vocabulary[s]["lateMedianEntries"] / vocabulary[s]["referenceMedianEntries"]
                      if vocabulary[s]["referenceMedianEntries"] else None) for s in ("ic", "cf")}
    facts = {
        "lateCohortFilings": len(late),
        "lateWithBalanceSheet": sum(has_section(r, "bs") for r in late),
        "everyLateFilingMissesBalanceSheet": bool(late) and all(not has_section(r, "bs") for r in late),
        "bothFrequenciesAffected": all(v == 100.0 for v in both_freq.values() if v is not None),
        "lateIdsAlreadyInEarlierStore": sum(r["id"] in early_ids for r in late),
        "icCfMedianSizeRatioLateToReference": {k: (round(v, 3) if v is not None else None) for k, v in size_ratio.items()},
        "referenceConceptsMissingFromLate": {s: vocabulary[s]["referenceConceptsMissingFromLateAtLeast20Filings"] for s in vocabulary},
        "septemberCeilingOfFilingDate": ceiling,
        "lateFilingsFiledOnOrBeforeSeptemberCeiling": len(arrivals),
        "lateFilingsFiledOnOrBeforeSeptemberCeilingWithoutBalanceSheet": sum(not has_section(r, "bs") for r in arrivals),
        "septemberCohortBalanceSheetAbsentPct": cohorts["september"]["balanceSheetAbsentPct"],
    }
    verdicts = {
        "A_source_omitted_balance_sheet": "NOT_REFUTED_NOT_CONFIRMED — the stored value is empty; whether the vendor sent `[]` is not retained",
        "B_schema_or_key_changed": "NOT_REFUTED_NOT_CONFIRMED — a balance sheet under a key the collector does not read is stored as `[]`, "
                                   "indistinguishable from A (the raw response is not kept)",
        "C_frequency_behaviour_changed": "REFUTED" if facts["bothFrequenciesAffected"] else "NOT_REFUTED",
        "D_collector_truncated_or_normalised": "REFUTED_FOR_WHOLE_RESPONSE_TRUNCATION" if all(
            v is not None and 0.9 <= v <= 1.1 for v in size_ratio.values()) else "NOT_REFUTED",
        "E_dedup_masked_a_valid_record": "REFUTED_AS_CAUSE_OF_THE_STORED_GAP" if facts["lateIdsAlreadyInEarlierStore"] == 0
        else "NOT_REFUTED",
        "E2_dedup_may_hide_a_later_completion": "UNTESTABLE_FROM_THE_STORE — a re-served copy is compared with nothing and dropped",
        "F_pit_or_classification_hides_a_valid_balance_sheet": "REFUTED_AS_CAUSE — the stored `bs` list is empty before any "
                                                                "feature code reads it",
    }
    return {
        "contract": CONTRACT, "source": source, "shards": shards,
        "storeTotals": {"filings": len(rows), "tickers": len(by_ticker), "cohortSplitCollectedOnOrAfter": COHORT_SPLIT},
        "cohorts": cohorts,
        "septemberAbsentSample": {"count": len(early_absent), "byForm": dict(Counter(r["form"] for r in early_absent).most_common()),
                                  "byPeriodYear": dict(sorted(Counter(r["periodEnd"][:4] for r in early_absent).items())),
                                  "withIncomeOrCashFlow": sum(has_section(r, "ic") or has_section(r, "cf") for r in early_absent)},
        "octoberAbsentBreakdown": {f"{k[0]}|{k[1]}|Q{k[2]}": v for k, v in sorted(absent_breakdown.items(), key=lambda kv: str(kv[0]))},
        "vendorServing": {
            "newFilingsPerCollectionDay": {d: len(v) for d, v in sorted(by_day.items())},
            "latestFilingDateInSeptemberCohort": ceiling,
            "octoberFilingsFiledOnOrBeforeThatDate": len(arrivals),
            "octoberFilingsFiledOnOrBeforeThatDateTickers": sorted({r["ticker"] for r in arrivals}),
            "octoberFilingDateRange": [min((r["availableFrom"] for r in late), default=None),
                                       max((r["availableFrom"] for r in late), default=None)],
            "octoberFilingsFiledInTheLastTwoDaysBeforeCollection": sum(
                (dt.date.fromisoformat(day(r)) - dt.date.fromisoformat(r["availableFrom"])).days <= 2 for r in late)},
        "quarantineView": {"definition": "stored records with income or cash-flow statement but no balance sheet; a read-side selection, "
                                         "no record is edited and no account is added",
                           "records": len(quarantine),
                           "byCollectionCohort": {"september": sum(q["collectedAt"][:10] < COHORT_SPLIT for q in quarantine),
                                                  "october": sum(q["collectedAt"][:10] >= COHORT_SPLIT for q in quarantine)}},
        "vocabulary": vocabulary,
        "tickerView": {"tickersWithAnOctoberFiling": len(late_tickers),
                       "ofWhichHadAnEarlierFilingWithBalanceSheet": len(prior_complete)},
        "featureCoverage": coverage,
        "facts": facts,
        "causeClassification": verdicts,
        "evidenceGap": {
            "rawResponseRetained": False,
            "whatIsStored": "per filing: id, form, period, availableFrom, acceptedDate and the entries of report.bs/ic/cf under the "
                            "filer's tags; the response's own keys, the key that would carry a renamed balance sheet, and the raw "
                            "bytes are not stored",
            "reDeliveredCopies": "a filing already stored is skipped on every later run without comparison, so the store cannot say "
                                 "whether the vendor completed the balance sheet after the first copy",
            "liveSourceCheck": "not performed in the authoring environment: no FINNHUB_API_KEY and no route to finnhub.io",
            "decidingMeasurement": "scripts/probe_finnhub_balance_sheet.py (bounded, owner-run) and the response-health sidecar the "
                                   "collector now writes"},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--store", type=Path)
    group.add_argument("--from-git", metavar="REF")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    if args.output.resolve() == (ROOT / "docs/results").resolve() or "docs/results" in str(args.output.resolve()):
        raise SystemExit("OUTPUT_MUST_NOT_BE_A_SEALED_RESULT_PATH")
    with tempfile.TemporaryDirectory() as tmp:
        if args.from_git:
            commit = extract_from_git(args.from_git, Path(tmp))
            directory, source = Path(tmp) / STORE_PATH, {"gitRef": args.from_git, "commit": commit}
        else:
            directory, source = args.store, {"store": "directory", "commit": None}
        rows, shards = read_store(directory)
    report = build(rows, shards, source)
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("storeTotals", "facts", "causeClassification")}, indent=1, ensure_ascii=False)[:3500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
