"""Outcome-free audit of the KR accounting coverage that blocks v4 execution.

Reads the SAME sealed raw-input snapshot `alpha-opportunity-model-v4`'s
execution froze (signal-history `4ea107ed`, 28 git blobs, verified by the
harness's own `verify_input_identity`) and explains, per filing and per
tradable KR name-date, why `ocfToNetIncomePct`, `assetGrowthPct` and
`debtGrowthPct` are missing. It builds no label, reads no price after a
signal date (the tradability guard it calls looks backward only), fits
nothing, and writes no outcome field.

Its own coverage table is required to reproduce the #160 execution report's
coverage for these three features exactly; a mismatch raises rather than
publishing a second, different denominator.

Usage:
    python scripts/audit_kr_accounting_coverage.py --input-root <signal-history checkout>
        [--expected-signal-history-sha 4ea107ed...] [--output-dir docs/results]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_spec as S1  # noqa: E402
from pipeline import alpha_opportunity_v2_spec as S2  # noqa: E402
from pipeline import alpha_opportunity_v4_execution as X  # noqa: E402
from pipeline import alpha_opportunity_v4_spec as S4  # noqa: E402
from pipeline import dart_derive as DD  # noqa: E402
from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import alpha_opportunity_kr_accounting_coverage_audit as A  # noqa: E402
from scripts import execute_alpha_opportunity_model_v4 as E4  # noqa: E402
from scripts import run_alpha_opportunity_model_v2 as V2  # noqa: E402

V4_SEAL = "4db0a96267a8b0de41c445ac600a8064a760191abdd29d97600153a78cbab8e6"
SEALED_SIGNAL_HISTORY = "4ea107ed0cde289f0a049a65ff13d2441a786710"
EXECUTION_REPORT = ROOT / "docs/results/alpha-opportunity-model-v4-execution-report.json"
SUMMARY_NAME = "kr-accounting-coverage-audit.json"
INVENTORY_NAME = "kr-accounting-coverage-filings.jsonl.gz"
GATE_YEARS = ("2016", "2025")

# Reason codes whose resolution needs only a re-collection that retains DART's
# raw rows and covers the PIT universe (`pipeline.dart_raw_statements`).
COLLECTION_REASONS = (A.TICKER_NOT_IN_DART_COLLECTION, A.PRIOR_NOT_COLLECTED,
                      A.CURRENT_ACCOUNT_MISSING, A.PRIOR_ACCOUNT_MISSING)
# ...plus the fiscal-2015 quarterlies DART's statement endpoint did not serve.
FIFTEEN_REASONS = (A.PRIOR_2015_QUARTERLY_NOT_SERVED, A.CALENDAR_2015_QUARTERLY)


def _blob(path: Path) -> str | None:
    if not path.exists():
        return None
    return X.git_blob_sha1(path)


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def _directory_identity(directory: Path) -> dict:
    """Git blob of every shard in a candidate (unsealed) fundamentals directory."""
    blobs = {p.name: X.git_blob_sha1(p) for p in sorted(directory.glob("dart-*.jsonl.gz"))}
    return {"directory": str(directory), "gitBlobSha1": blobs,
            "sha256": S1.digest(blobs)}


def run(input_root: Path, expected_sha: str, kr_dir: Path | None = None,
        absent_json: Path | None = None) -> tuple[dict, list[dict]]:
    """Audit the sealed snapshot, or -- with `kr_dir` -- a CANDIDATE repaired KR store.

    A candidate keeps every other input of the sealed snapshot (membership,
    prices for the backward tradability guard, share records) and swaps only the
    KR DART filings, so a change in coverage is attributable to the filings.
    """
    v4_spec = S4.load_sealed(S4.DEFAULT_SPEC, expected_hash=V4_SEAL)
    v2_spec, _ = S2.load_sealed(ROOT / "research_specs/alpha-opportunity-model-v2.json",
                                expected_hash=E4.V2_SEAL)
    v3_spec = E4.load_v3_spec(v4_spec)
    identity = X.verify_input_identity(X.sealed_input_identity(v3_spec), input_root,
                                       expected_signal_history_sha=expected_sha)
    runtime = X.build_runtime_spec(v4_spec, v2_spec)

    from pipeline import regional_alpha_features as SOURCES
    import pandas as pd

    ledger = input_root / "ledger"
    _, prices, _, _ = SOURCES.load_inputs(ledger)
    raw, shares = X.load_kr_raw(ledger)
    candidate = None
    if kr_dir is not None:
        raw = {}
        for path in sorted(kr_dir.glob("dart-*.jsonl.gz")):
            for row in HS.read_jsonl(path):
                raw.setdefault(row["ticker"], []).append(row)
        candidate = _directory_identity(kr_dir)
    memberships = X.load_kr_memberships(ledger)
    absent_path = absent_json or ledger / "fundamentals/kr/absent.json"
    absent = json.loads(absent_path.read_text(encoding="utf-8")) if absent_path.exists() else {}
    absences = A.absence_index(absent)

    rows = []
    universe = set()
    for date in SOURCES.weekly_grid(runtime["walkForward"]["featureStart"], runtime["dataCutoff"], "KR"):
        snapshot = memberships.on(date)
        if snapshot is None:
            raise ValueError("PIT_MEMBERSHIP_MISSING: KR/" + date)
        for ticker in snapshot["members"]:
            universe.add(ticker)
            rows.append({"date": date, "region": "KR", "ticker": ticker})
    frame = pd.DataFrame(rows)
    guard = V2.tradability_frame(prices, frame, "KR", runtime["tradabilityGuard"]["windowSessions"])
    frame = frame.merge(guard, on=["date", "region", "ticker"], how="left", validate="one_to_one")
    tradable = frame.loc[frame.tradable.astype(bool)]

    diagnosed = []
    for row in tradable.itertuples():
        out = A.diagnose_name_date(row.ticker, raw.get(row.ticker, []), shares.get(row.ticker, []),
                                   row.date, absences)
        diagnosed.append({"date": row.date, "ticker": row.ticker, **out})
    summary = A.summarize_name_dates(diagnosed)

    # The denominator and numerator must be #160's, exactly. A blocked run
    # publishes only its failing cells and its frame counts, so those are what
    # is compared -- and the failing SET must match too, not only its members.
    executed = S1.read_json(EXECUTION_REPORT)
    if (len(frame), int(tradable.shape[0])) != (executed["preLabelFrame"]["memberDates"],
                                                executed["preLabelFrame"]["tradable"]):
        raise ValueError("AUDIT_DOES_NOT_REPRODUCE_EXECUTION_DENOMINATOR")
    expected_failures = None if candidate is not None else {
        (e["year"], e["feature"]): (e["observed"], e["universeRows"])
        for e in executed["detail"]["coverageFailures"]
        if e["region"] == "KR" and e["feature"] in A.FEATURES}

    floor = runtime["coverageGate"]["accounting"]
    first_year = runtime["coverageGate"]["firstEvaluationYear"]
    failures = [{"year": y, "feature": f, "observed": s["features"][f]["observed"],
                 "universeRows": s["universeRows"], "coverage": s["features"][f]["coverage"]}
                for y, s in summary.items() for f in A.FEATURES
                if int(y) >= first_year and s["features"][f]["coverage"] < floor]
    if expected_failures is not None and {
            (f["year"], f["feature"]): (f["observed"], f["universeRows"]) for f in failures} != expected_failures:
        raise ValueError("AUDIT_DOES_NOT_REPRODUCE_EXECUTION_COVERAGE_FAILURES")

    years = list(range(DF.FIRST_SERVED_YEAR - 1, 2027))
    records = [r for rs in raw.values() for r in rs]
    inventory = A.filing_inventory(records, absences, sorted(universe), years)
    for row in inventory:
        row["id"] = f"{row['ticker']}:{row['fiscalYear']}:{row['reportCode']}"

    collected_tickers = sorted(raw)
    member_dates = Counter()
    for row in tradable.itertuples():
        member_dates[(row.date[:4], row.ticker in raw)] += 1

    quarterly = Counter()
    for row in inventory:
        if row["filingStatus"] == "COLLECTED" and row["reportCode"] != "11011":
            missing_ni = "당기순이익" in row["requiredAccountsMissing"]
            quarterly[(row["fiscalYear"], missing_ni, bool(row["incomeStatementOtherAccountsPresent"]))] += 1
    ni_statement = Counter((r["reportCode"] == "11011", r.get("netIncomeStatement"))
                           for r in inventory if r["filingStatus"] == "COLLECTED")

    element_evidence = {}
    for account in ("당기순이익", "영업활동현금흐름", "자산총계", "부채총계"):
        seen = Counter()
        for r in records:
            entry = (r.get("accounts") or {}).get(account)
            if entry:
                seen[(entry.get("statement"), entry.get("accountId"))] += 1
        element_evidence[account] = [{"statement": st, "accountId": aid, "filings": n}
                                     for (st, aid), n in sorted(seen.items(), key=str)]
    late = Counter()
    for r in records:
        if r["availableFrom"] > DF.filing_deadline(r["fiscalYear"], r["reportCode"]):
            late[(r["fiscalYear"], r["reportCode"])] += 1

    signatures = Counter()
    for r in records:
        for account in ("당기순이익", "영업활동현금흐름", "자산총계", "부채총계"):
            entry = (r.get("accounts") or {}).get(account)
            if entry:
                signatures[(account, "ANNUAL" if r["reportCode"] == "11011" else "QUARTERLY",
                            entry.get("statement"), ",".join(sorted(entry.get("amounts") or {})))] += 1
    by_key = {(r["ticker"], r["fiscalYear"], r["reportCode"]): r for r in records}

    def q3_over_fy(account):
        ratios = []
        for (ticker, year, code), r in by_key.items():
            fy = by_key.get((ticker, year, "11011")) if code == "11014" else None
            if fy is None:
                continue
            a, b = DD.cumulative_amount(r, account), DD.cumulative_amount(fy, account)
            if a is not None and b and b > 0:
                ratios.append(a / b)
        ratios.sort()
        return {"median": ratios[len(ratios) // 2] if ratios else None, "pairs": len(ratios)}

    ids = Counter(r["id"] for r in records)
    derivation_check = {
        "amountFieldSignatures": [{"account": a, "report": k, "statement": st, "fields": f, "filings": n}
                                  for (a, k, st, f), n in sorted(signatures.items(), key=str)],
        "q3OverFiscalYearMedian": {"operatingCashFlow": q3_over_fy("영업활동현금흐름"),
                                   "netIncome": q3_over_fy("당기순이익"),
                                   "reading": "cumulative 9-month figures sit near 0.75, standalone "
                                              "quarters near 0.25"},
        "duplicateRecordIds": sum(1 for n in ids.values() if n > 1),
        "multiReceiptFilings": sum(1 for r in records if len(r.get("receiptNos") or []) != 1),
        "receiptDateDisagreesWithAvailableFrom": sum(
            1 for r in records
            if {x[:8] for x in r.get("receiptNos") or []} != {r["availableFrom"].replace("-", "")}),
    }

    blocked = {y: {f: Counter() for f in A.FEATURES} for y in GATE_YEARS}
    stale = Counter()
    for row in diagnosed:
        year = row["date"][:4]
        if year not in blocked:
            continue
        if row["currentFiling"] is not None:
            due = A.statutory_current_filing(row["date"])
            cy, cc = row["currentFiling"].split("-")
            later_served_late = any(
                (r["fiscalYear"], A.STAGE_ORDER[r["reportCode"]]) > (int(cy), A.STAGE_ORDER[cc])
                and (r["fiscalYear"], A.STAGE_ORDER[r["reportCode"]]) <= (due[0], A.STAGE_ORDER[due[1]])
                and r["availableFrom"] >= row["date"] for r in raw.get(row["ticker"], []))
            stale[(year, later_served_late)] += 1
        for name in A.FEATURES:
            info = row["features"][name]
            if not info["available"]:
                key = (row["ticker"], row["currentFiling"], row["fsDiv"], tuple(sorted(set(info["blockers"]))))
                blocked[year][name][key] += 1
    blocked_filings = {
        y: {f: [{"ticker": t, "currentFiling": cf, "fsDiv": fs, "blockers": list(b), "nameDates": n}
                for (t, cf, fs, b), n in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))]
            for f, c in feats.items()}
        for y, feats in blocked.items()}

    status_2015 = Counter((r["reportCode"], r["filingStatus"], r.get("absenceStatus"))
                          for r in inventory if r["fiscalYear"] == 2015)

    report = {
        "contract": A.CONTRACT,
        "outcomeFree": True,
        "reads": "filing metadata, stored account presence, receipt dates, PIT membership, "
                 "backward-looking tradability; no label, forward price, model, IC or return",
        "auditCodeCommitSha": _git("rev-parse", "HEAD"),
        "auditCodeDirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "snapshot": "SEALED_V4_EXECUTION_INPUT" if candidate is None else "REPAIRED_CANDIDATE_UNSEALED",
        "inputIdentity": identity,
        "candidateKrFundamentals": candidate,
        "unsealedBookkeepingRead": {
            "absent.json": _blob(absent_path),
            "ledger/fundamentals/kr/manifest.json": _blob(ledger / "fundamentals/kr/manifest.json"),
        },
        "gate": {"accountingFloor": floor, "firstEvaluationYear": first_year,
                 "failures": failures,
                 "reproducesExecutionReport": expected_failures is not None},
        "reasonCodes": list(A.REASON_CODES),
        "coverageByYear": summary,
        "upperBoundIfCollectionReasonsResolved": {
            "reasons": list(COLLECTION_REASONS),
            "meaning": "coverage if every name-date blocked ONLY by these reasons became available; "
                       "an upper bound, never a projection",
            "coverage": A.upper_bound_if_resolved(summary, COLLECTION_REASONS),
        },
        "upperBoundIfCollectionAnd2015QuarterliesResolved": {
            "reasons": list(COLLECTION_REASONS + FIFTEEN_REASONS),
            "coverage": A.upper_bound_if_resolved(summary, COLLECTION_REASONS + FIFTEEN_REASONS),
        },
        "collectionUniverse": {
            "pitUniverseTickers": len(universe),
            "tickersWithAnyDartFiling": len(collected_tickers),
            "pitTickersWithAnyDartFiling": len(universe & set(collected_tickers)),
            "tradableMemberDatesByYear": {
                y: {"withDartFilings": member_dates[(y, True)], "withoutDartFilings": member_dates[(y, False)]}
                for y in sorted({k[0] for k in member_dates})},
        },
        "accountIdsUnderExactLabelMatch": element_evidence,
        "derivationVerification": derivation_check,
        "blockedNameDatesByTickerAndFiling": blocked_filings,
        "currentFilingHeldBackByLaterServedFiling": {
            "meaning": "collected name-dates whose current filing is older than a filing already due "
                       "by statute, because that filing is stored only under a receipt dated on or "
                       "after the signal date (an amendment served in place of the original)",
            "byGateYear": {y: {"heldBack": stale[(y, True)], "notHeldBack": stale[(y, False)]}
                           for y in GATE_YEARS}},
        "receiptAfterStatutoryDeadline": {
            "meaning": "stored filings whose served receipt date is after the filing's legal "
                       "deadline; the statement endpoint serves the latest amendment's receipt, so "
                       "the original filing's visibility date is not in the store",
            "filings": sum(late.values()), "storedFilings": len(records),
            "byFiscalYearAndReportCode": [{"fiscalYear": y, "reportCode": c, "filings": n}
                                          for (y, c), n in sorted(late.items())],
        },
        "fiscal2015": {
            "byReportCodeStatus": [{"reportCode": c, "filingStatus": s, "absenceStatus": a, "filings": n}
                                   for (c, s, a), n in sorted(status_2015.items(), key=str)],
        },
        "quarterlyNetIncome": {
            "byFiscalYear": [{"fiscalYear": y, "netIncomeMissing": m,
                              "otherIncomeStatementAccountsPresent": o, "filings": n}
                             for (y, m, o), n in sorted(quarterly.items())],
            "netIncomeMatchedFromStatement": [{"annual": a, "statement": s, "filings": n}
                                              for (a, s), n in sorted(ni_statement.items(), key=str)],
        },
    }
    return report, inventory


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--expected-signal-history-sha", default=SEALED_SIGNAL_HISTORY)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/results")
    parser.add_argument("--kr-fundamentals-dir", type=Path,
                        help="audit a CANDIDATE repaired KR store instead of the sealed one")
    parser.add_argument("--absent-json", type=Path)
    args = parser.parse_args(argv)
    report, inventory = run(args.input_root.resolve(), args.expected_signal_history_sha,
                            args.kr_fundamentals_dir, args.absent_json)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / SUMMARY_NAME).write_bytes(S1.canonical(report) + b"\n")
    HS.write_shard(args.output_dir / INVENTORY_NAME, inventory)
    gate_years = {y: {f: round(100 * t["coverage"], 2) for f, t in report["coverageByYear"][y]["features"].items()}
                  for y in GATE_YEARS if y in report["coverageByYear"]}
    print(json.dumps({"snapshot": report["snapshot"], "gateFailures": report["gate"]["failures"],
                      "gateYearCoveragePct": gate_years}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
