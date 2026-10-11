"""Weekly PIT coverage audit of the US shareholder-distribution features. Outcome-blind, research-only.

    python scripts/audit_us_capital_allocation_coverage.py --workspace <dir> --extract --output-dir <dir>

Reads, never collects: the pinned `signal-history` Finnhub shards (the same 17 blobs PR #220 audited), the sealed
`replay-v16` price panels (only to learn whether a positive close EXISTS on a date), the sealed S&P 500 membership
snapshots, the v3 identity audit and the dated sector labels. It computes no return, reads no label, fits nothing.

The unit is a (weekly signal date, PIT S&P 500 member) pair, not a filing event. Each pair is counted at the first
funnel stage it fails (identity, price panel, price history, price freshness, fundamental record, visible filing,
report freshness, feature measurement). The matrix of every pair is kept in the workspace; the committed outputs are
aggregates plus a digest of that matrix.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v3_survivorship as V3      # noqa: E402
from pipeline import regional_alpha_features as RAF               # noqa: E402
from pipeline import replay_calendar as RC                        # noqa: E402
from pipeline import us_capital_allocation_coverage as C          # noqa: E402
from pipeline import us_capital_allocation_policy as POL          # noqa: E402
from pipeline import us_dual_benchmark_data as D                  # noqa: E402
from pipeline import us_shareholder_distribution as U             # noqa: E402

_spec = importlib.util.spec_from_file_location("audit220", ROOT / "scripts/audit_us_shareholder_distribution.py")
A220 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = A220
_spec.loader.exec_module(A220)

FUNDAMENTALS_COMMIT = "704d7db6d5b00def771aba5d2665d0846d6bc776"
CUTOFF = "2026-10-11"                 # the cutoff PR #220's committed audit used
THROUGH = "2026-09-11"                # last COMPLETED US week inside the sealed price panels (through 2026-09-14)
MEMBERSHIP = ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz"
V3_AUDIT = ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json"
SECTORS = ROOT / "data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz"
COMMITTED_220 = ROOT / "docs/us-readiness/us-shareholder-distribution-feature-audit.json"
OUT_DIR = ROOT / "docs/us-readiness"
DATA_DIR = ROOT / "data/research/us-capital-allocation-alpha-v1"


def extract(workspace: Path, commit: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    listing = subprocess.check_output(["git", "ls-tree", "-r", commit, "ledger/fundamentals/us/"], cwd=ROOT).decode().splitlines()
    files = []
    for line in listing:
        meta, path = line.split("\t")
        if not path.endswith(".jsonl.gz"):
            continue
        oid = meta.split()[2]
        blob = subprocess.check_output(["git", "cat-file", "blob", oid], cwd=ROOT)
        (workspace / Path(path).name).write_bytes(blob)
        files.append({"path": path, "gitBlob": oid, "bytes": len(blob)})
    (workspace / "source-manifest.json").write_text(json.dumps({"commit": commit, "files": files}, indent=1))


def load_filings(workspace: Path, commit: str):
    """Group visible filings by ticker exactly as PR #220's audit does, and keep each ticker's CIK."""
    declared = json.loads((workspace / "source-manifest.json").read_text())
    if declared["commit"] != commit:
        raise ValueError("SOURCE_COMMIT_MISMATCH")
    expected = {Path(f["path"]).name: f for f in declared["files"]}
    cutoff = U.parse_day(CUTOFF)
    grouped, ciks, shard_ids, raw_count = defaultdict(list), defaultdict(list), [], 0
    for path in sorted(workspace.glob("finnhub-*.jsonl.gz")):
        blob = path.read_bytes()
        oid = hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()
        if expected[path.name]["gitBlob"] != oid:
            raise ValueError("SOURCE_BLOB_MISMATCH: " + path.name)
        shard_ids.append({"name": path.name, "gitBlob": oid, "sha256": hashlib.sha256(blob).hexdigest()})
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                raw_count += 1
                record = json.loads(line)
                available, accepted = U.parse_day(record.get("availableFrom")), U.parse_day(record.get("acceptedDate"))
                visible = max(available, accepted) if available and accepted else available
                if visible and visible >= cutoff:
                    continue
                grouped[record["ticker"]].append(A220._project(record))
                if record.get("cik") and visible:
                    ciks[record["ticker"]].append((visible, str(int(record["cik"]))))
    return grouped, ciks, shard_ids, raw_count


def source_metadata(grouped):
    semantics = A220._semantics(grouped)
    evidence = U.canonical_digest(semantics)
    meta = U.SourceMetadata(U.SOURCE, FUNDAMENTALS_COMMIT, "input-only-family-semantics:" + evidence,
                            unverified_flow_concepts=tuple(c for c, s in semantics.items() if s["verdict"] != "CUMULATIVE_CORROBORATED"))
    return meta, semantics


def load_price_presence():
    reader = D.SealedReader(ROOT)
    manifest = reader.manifest()
    rows = []
    for name in sorted(manifest["components"]):
        if name.startswith("price/20"):
            for ref in manifest["components"][name]:
                rows.extend({"ticker": r["ticker"], "date": r["date"], "Close": r.get("Close")}
                            for r in reader.component(ref) if not r["ticker"].endswith((".KS", ".KQ")))
    return C.PricePresence.from_rows(rows), {"manifestSha256": manifest["sha256"], "through": manifest["through"]}


def identity_tables():
    audit = json.loads(V3_AUDIT.read_text())["regions"]["US"]["identity"]
    category = {t: c for c, tickers in audit["categories"].items() for t in tickers}
    malformed = {k.upper(): v["resolvedTo"] for k, v in audit["malformed"].items() if v.get("resolvedTo")}
    renames = {t: r["pricedBy"] for t, r in audit["renames"].items() if r.get("pricedBy")}
    ambiguous = {t for t, c in category.items() if c == "TICKER_REUSE_DIFFERENT_ISSUER"} | set(audit["panelPostdatesMembership"])
    return category, malformed, renames, ambiguous


def run(workspace: Path, limit_dates=None):
    grouped, ciks, shard_ids, raw_count = load_filings(workspace, FUNDAMENTALS_COMMIT)
    source, semantics = source_metadata(grouped)
    committed = json.loads(COMMITTED_220.read_text())
    if source.cumulative_evidence != committed["sourceMetadata"]["cumulativeEvidence"]:
        raise ValueError("SOURCE_METADATA_DIFFERS_FROM_THE_COMMITTED_220_AUDIT")
    engines = {t: U.FeatureEngine(t, rows, source) for t, rows in grouped.items()}
    prices, price_identity = load_price_presence()
    membership = RAF.MembershipSnapshots(json.loads(gzip.decompress(MEMBERSHIP.read_bytes()))["snapshots"])
    sector_payload = json.loads(gzip.decompress(SECTORS.read_bytes()))
    if sector_payload["failures"] or len(sector_payload["snapshots"]) != len(membership.snapshots):
        raise ValueError("SECTOR_EVIDENCE_INCOMPLETE")
    sectors = C.SectorBook(sector_payload["snapshots"])
    category, malformed, renames, ambiguous = identity_tables()
    dates = V3.weekly_grid(RC.sessions(RC.ORIGIN, "2026-09-25", "US"), THROUGH)
    if limit_dates:
        dates = dates[::max(1, len(dates) // limit_dates)][:limit_dates]

    ctx = C.WeekContext(engines=engines, prices=prices, sectors=sectors, ciks=ciks, category=category,
                        malformed=malformed, renames=renames, ambiguous=ambiguous)
    tally, matrix = C.Tally(), io.StringIO()
    writer = csv.writer(matrix, lineterminator="\n")
    writer.writerow(["date", "symbol", "ticker", "sector", "sectorBasis", "status", "reason", "distribution", "yoy", "ocf",
                     "distributionToOCF", "dividends", "repurchases", "reportEnd", "dilution", "digest"])
    digest = hashlib.sha256()
    weekly, cik_mismatch, carried = [], Counter(), Counter()
    feasibility = {"decisions": Counter(), "selectedCount": Counter(), "byYear": defaultdict(lambda: defaultdict(Counter)),
                   "passers": [], "measured": [], "gateTotals": Counter(), "sectorOfSelected": Counter(), "skippedForSectorCap": 0}
    for date in dates:
        snapshot = membership.on(date)
        year = date[:4]
        per_date = Counter()
        evaluations = []
        for raw_symbol in snapshot["members"]:
            member = C.classify_member(ctx, snapshot, date, raw_symbol)
            symbol, ticker, sector, basis = member.symbol, member.ticker, member.sector, member.sector_basis
            status, reason, feature_snapshot, end = member.status, member.reason, member.snapshot, member.report_end
            carried[basis] += 1
            if reason == "CIK_MISMATCH":
                cik_mismatch[symbol] += 1
            extras = {}
            if feature_snapshot is not None:
                if status != C.REPORT_STALE:
                    tally.add_features(year, sector, feature_snapshot)      # fresh-report pairs only
                    tally.cross[(feature_snapshot.features["cashDividendsPaidTTM"].state.value,
                                 feature_snapshot.features["commonStockRepurchasesTTM"].state.value)] += 1
                f = feature_snapshot.features
                extras = dict(distribution=f["totalCashDistributionTTM"].value, yoy=f["totalCashDistributionChangeYoY"].value,
                              ocf=f["operatingCashFlowTTM"].value, ratio=f["distributionToOCF"].value,
                              dividends=f["cashDividendsPaidTTM"].state.value, repurchases=f["commonStockRepurchasesTTM"].state.value,
                              reportEnd=end, dilution=f["sharesOutstandingChangeYoY"].state.value,
                              digest=feature_snapshot.feature_digest[:12])
            per_date[status] += 1
            tally.add_member_date(year, sector, symbol, status)
            evaluation = C.member_evaluation(member)
            if evaluation is not None:
                evaluations.append(evaluation)
            if reason:
                tally.reasons[(status, reason.split(":")[0] if status == C.FEATURES_NOT_MEASURED else reason)] += 1
                if status == C.FEATURES_NOT_MEASURED:
                    tally.reasons[(status, reason)] += 1
            row = [date, symbol, ticker, sector, basis, status, reason, extras.get("distribution"), extras.get("yoy"), extras.get("ocf"),
                   extras.get("ratio"), extras.get("dividends"), extras.get("repurchases"), extras.get("reportEnd"), extras.get("dilution"),
                   extras.get("digest")]
            writer.writerow(row)
            digest.update(("|".join("" if v is None else str(v) for v in row) + "\n").encode())
        decision = POL.select(evaluations)
        feasibility["decisions"][decision["status"]] += 1
        feasibility["byYear"][year]["status"][decision["status"]] += 1
        feasibility["byYear"][year]["selected"][len(decision["selected"])] += 1
        feasibility["selectedCount"][len(decision["selected"])] += 1
        feasibility["passers"].append(len(decision["passers"]))
        feasibility["measured"].append(decision["funnel"]["measured"])
        feasibility["skippedForSectorCap"] += len(decision["skippedForSectorCap"])
        feasibility["gateTotals"].update(decision["funnel"]["failedAt"])
        feasibility["gateTotals"]["PASSED_EVERY_GATE"] += decision["funnel"]["passed"]
        feasibility["sectorOfSelected"].update(x["sector"] for x in decision["selected"])
        weekly.append({"date": date, "members": len(snapshot["members"]), **{s: per_date.get(s, 0) for s in C.FUNNEL},
                       "measuredNames": decision["funnel"]["measured"], "passers": len(decision["passers"]),
                       "selected": len(decision["selected"]), "decision": decision["status"]})
    return dict(dates=dates, tally=tally, weekly=weekly, matrix=matrix.getvalue(), matrixSha256=digest.hexdigest(),
                shards=shard_ids, rawCount=raw_count, source=source, semantics=semantics, price_identity=price_identity,
                carried=carried, cik_mismatch=cik_mismatch, companies=len(grouped), engines=engines, ciks=ciks, feasibility=feasibility)


def pct(n, d):
    return round(100.0 * n / d, 4) if d else None


def summarize(result):
    tally = result["tally"]
    total = Counter()
    for counter in tally.by_year.values():
        total.update(counter)
    n = sum(total.values())
    eligible_stage = (C.FEATURES_NOT_MEASURED, C.JOINT_MEASURED, C.REPORT_STALE)
    by_year = {y: {"memberDates": sum(c.values()), "funnelPct": C.funnel_share(c)} for y, c in sorted(tally.by_year.items())}
    by_sector = {s: {"memberDates": sum(c.values()), "funnelPct": C.funnel_share(c)} for s, c in sorted(tally.by_sector.items())}

    def state_table(book):
        return {name: {s: counter.get(s, 0) for s in C.STATES if counter.get(s, 0)} for name, counter in sorted(book.items())}

    families = {fam: {name: dict(sorted(states.items())) for name, states in sorted(names.items())} for fam, names in tally.states.items()}
    companies = {}
    for symbol, c in sorted(tally.by_company.items()):
        weeks = sum(c.values())
        companies[symbol] = {"memberWeeks": weeks, "jointMeasuredWeeks": c.get(C.JOINT_MEASURED, 0),
                             "firstFailureStage": next((s for s in C.FUNNEL[:-1] if c.get(s)), None),
                             "stages": {s: c[s] for s in C.FUNNEL if c.get(s)}}
    weekly = result["weekly"]
    measured_by_year = {}
    for y in sorted({w["date"][:4] for w in weekly}):
        vals = sorted(w["measuredNames"] for w in weekly if w["date"][:4] == y)
        measured_by_year[y] = {"weeks": len(vals), "min": vals[0], "median": vals[len(vals) // 2], "max": vals[-1],
                               "weeksBelowFloor": sum(v < POL.MIN_MEASURED_NAMES for v in vals)}
    f = result["feasibility"]
    passers = sorted(f["passers"])
    weeks = len(passers)
    feasibility = {
        "rule": POL.POLICY_VERSION, "designDigest": POL.design_digest(), "weeks": weeks,
        "weeklyDecisions": dict(f["decisions"]), "namesSelectedPerWeek": {str(k): v for k, v in sorted(f["selectedCount"].items())},
        "weeksWithAtLeastOnePasser": sum(1 for v in passers if v > 0), "passersPerWeek": {
            "median": passers[weeks // 2], "mean": round(sum(passers) / weeks, 3), "max": passers[-1]},
        "weeksWithAtLeastOneSelection": sum(v for k, v in f["selectedCount"].items() if k > 0),
        "gateFunnelTotalsAcrossWeeks": dict(f["gateTotals"]), "namesSkippedBecauseOfTheSectorCap": f["skippedForSectorCap"],
        "sectorOfSelectedNames": dict(f["sectorOfSelected"]),
        "byYear": {y: {"status": dict(v["status"]), "namesSelected": {str(k): c for k, c in sorted(v["selected"].items())}}
                   for y, v in sorted(f["byYear"].items())},
        "note": "counts only; the rule saw no return, and its thresholds were fixed before this run",
    }
    return {
        "memberDates": n,
        "dividendRepurchaseStateCrosstab": {"%s | %s" % k: v for k, v in sorted(tally.cross.items(), key=lambda kv: -kv[1])},
        "weeklyMeasuredNamesByYear": measured_by_year,
        "selectionFeasibility": feasibility,
        "weeklyDates": len(result["dates"]),
        "firstDate": result["dates"][0], "lastDate": result["dates"][-1],
        "funnelCounts": {s: total.get(s, 0) for s in C.FUNNEL},
        "funnelPct": C.funnel_share(total),
        "priceEligibleMemberDates": sum(total.get(s, 0) for s in (C.NO_FUNDAMENTAL_RECORD, C.NO_VISIBLE_FILING, *eligible_stage)),
        "filingEligibleMemberDates": sum(total.get(s, 0) for s in eligible_stage),
        "jointMeasuredOfFilingEligiblePct": pct(total.get(C.JOINT_MEASURED, 0), sum(total.get(s, 0) for s in eligible_stage)),
        "jointMeasuredOfAllMemberDatesPct": pct(total.get(C.JOINT_MEASURED, 0), n),
        "byYear": by_year, "bySector": by_sector,
        "featureStatesByFamily": families,
        "featureStatesByCalendarYear": {y: state_table(b) for y, b in sorted(tally.states_by_year.items())},
        "featureStatesBySector": {s: state_table(b) for s, b in sorted(tally.states_by_sector.items())},
        "notMeasuredReasons": {"%s|%s" % k: v for k, v in sorted(tally.reasons.items(), key=lambda kv: (-kv[1], kv[0]))[:60]},
        "sectorLabelBasis": dict(result["carried"]),
        "cikMismatchSymbols": dict(result["cik_mismatch"]),
        "companies": companies,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--extract", action="store_true", help="read the pinned Finnhub blobs from git into the workspace first")
    parser.add_argument("--matrix-out", type=Path, help="write the full member-date matrix (kept out of the repository)")
    parser.add_argument("--limit-dates", type=int, help="smoke run on an even subsample of weekly dates; writes nothing")
    args = parser.parse_args(argv)
    if args.extract:
        extract(args.workspace, FUNDAMENTALS_COMMIT)
    result = run(args.workspace, args.limit_dates)
    summary = summarize(result)
    if args.limit_dates:
        print(json.dumps({"funnelCounts": summary["funnelCounts"], "pct": summary["funnelPct"],
                          "reasons": dict(list(summary["notMeasuredReasons"].items())[:8]), "sectorBasis": summary["sectorLabelBasis"]}, indent=1))
        return 0
    committed = json.loads(COMMITTED_220.read_text())
    report = {
        "id": "us-capital-allocation-weekly-coverage-v1", "evidenceClass": "OUTCOME_BLIND_WEEKLY_PIT_COVERAGE",
        "readsReturns": False, "readsLabels": False, "fitsModels": False, "writesSignalHistory": False, "historicalResearchExecuted": False,
        "featureVersion": U.FEATURE_VERSION,
        "inputs": {"fundamentalsCommit": FUNDAMENTALS_COMMIT, "shards": result["shards"], "rawFilings": result["rawCount"],
                   "companiesWithFilings": result["companies"], "cutoff": CUTOFF,
                   "cumulativeEvidence": result["source"].cumulative_evidence,
                   "matchesCommitted220Evidence": True, "committed220EventDigest": committed["eventFeatureDigest"],
                   "pricePresence": {"source": "replay-v16 sealed price panels (existence of a positive close only)", **result["price_identity"]},
                   "membership": str(MEMBERSHIP.relative_to(ROOT)), "identity": str(V3_AUDIT.relative_to(ROOT)),
                   "sectors": str(SECTORS.relative_to(ROOT))},
        "grid": "last US session of each completed calendar week (alpha_opportunity_v3_survivorship.weekly_grid), membership = latest snapshot strictly earlier than the date",
        "matrixSha256": result["matrixSha256"],
        "summary": summary,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "us-capital-allocation-weekly-coverage-v1.json").write_text(
        json.dumps(report, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n", encoding="utf-8")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(DATA_DIR / "weekly-funnel-by-date.csv.gz", "wb", mtime=0) as stream:
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=["date", "members", *C.FUNNEL, "measuredNames", "passers", "selected", "decision"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["weekly"])
        stream.write(out.getvalue().encode())
    if args.matrix_out:
        args.matrix_out.parent.mkdir(parents=True, exist_ok=True)
        with gzip.GzipFile(args.matrix_out, "wb", mtime=0) as stream:
            stream.write(result["matrix"].encode())
    print("member-dates %d, joint measured %s%% of filing-eligible, matrix sha256 %s" % (
        summary["memberDates"], summary["jointMeasuredOfFilingEligiblePct"], result["matrixSha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
