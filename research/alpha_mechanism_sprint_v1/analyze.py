"""Build results.json for alpha-mechanism-sprint-v1 from the collected sources.

Outcome-blind: reads the monthly KRX market-cap snapshots (membership only),
DART disclosure metadata, a parsed document sample and DART-derived
fundamentals. It never reads a price series, a return, a label or a model
output.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import sprint  # noqa: E402

FIRST_QUARTER, LAST_QUARTER = date(2013, 3, 31), date(2026, 6, 30)
REPORT_CODE = {3: "11013", 6: "11012", 9: "11014", 12: "11011"}
SAMPLE_SEED, SAMPLE_PER_YEAR = 20261101, 18
PARSER_REVISIONS = [
    {"version": "v1", "measuredOn": "252-document seeded development sample",
     "allThreeCurrentAndPriorYearPct": 79.37,
     "defect": "decoded only one header-label style; first 400 characters were CSS so consolidation was never detected"},
    {"version": "v2", "measuredOn": "6,446 member-unit documents",
     "allThreeCurrentAndPriorYearPct": 88.15,
     "defect": "1,850 tables with no recognised period label, 1,580 of them stating numbers (date-range, 'N/4분기', 'FY', 'YYYY-NQ' labels)"},
    {"version": "v3", "measuredOn": "6,446 member-unit documents (holdout excludes the 252 development documents)",
     "allThreeCurrentAndPriorYearPct": 96.3,
     "defect": "fixed: ordered period-token scan; 2025+ seven-column layout with 흑자적자전환여부 (491 documents) read prior year from the fifth column",
     "disclosure": "v2->v3 revisions were made after reading population failure modes; no price, return or label was read. "
                   "Parsed values are cross-checked independently against the formal filing (contentConfirmed.prelimVsFormal)."},
]


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_jsonl_gz(path: str | Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def kr_sessions() -> list[date]:
    from pipeline import replay_calendar
    return [ts.date() for ts in replay_calendar.sessions("2012-10-01", "2026-10-31", "KR")]


def load_inputs(args) -> dict:
    universe_files = sorted(glob.glob(str(Path(args.universe_dir) / "krx-universe-*.jsonl.gz")))
    snapshots = [row for f in universe_files for row in read_jsonl_gz(f)]
    collection = json.loads(Path(args.collection_universe).read_text(encoding="utf-8"))
    code_to_corp = {sec["stockCode"]: issuer["corpCode"]
                    for issuer in collection["issuers"] for sec in issuer["securities"]}
    list_files = sorted(glob.glob(str(Path(args.dart_list) / "*.jsonl.gz")))
    rows_by_corp: dict[str, list[dict]] = defaultdict(list)
    for f in list_files:
        rows_by_corp[Path(f).name.split("-")[0]].extend(read_jsonl_gz(f))
    state_path = Path(args.dart_list) / "collect-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    hashes = {"universeShards": {Path(f).name: sha256_file(f) for f in universe_files},
              "collectionUniverse": sha256_file(args.collection_universe),
              "dartListFiles": len(list_files),
              "dartListCombinedSha256": hashlib.sha256(
                  b"".join(Path(f).name.encode() + sha256_file(f).encode() for f in list_files)).hexdigest()}
    return {"snapshots": snapshots, "collection": collection, "codeToCorp": code_to_corp,
            "listFileNames": [Path(f).name for f in list_files],
            "rowsByCorp": rows_by_corp, "collectState": state, "hashes": hashes}


def _complete_by_corp(data: dict) -> Counter:
    """Issuer complete only when both publication types were fully walked (a file exists per type)."""
    done = Counter()
    for name in data["listFileNames"]:
        done[name.split("-")[0]] += 1
    return done


def disclosure_inventory(rows_by_corp: dict) -> dict:
    families = Counter()
    amendments = Counter()
    for rows in rows_by_corp.values():
        for row in rows:
            family = sprint.classify(row["report_nm"])
            if family == sprint.OTHER:
                continue
            families[family] += 1
            if sprint.is_amendment(row["report_nm"]):
                amendments[family] += 1
    return {"rowsByFamily": dict(sorted(families.items())),
            "amendmentRowsByFamily": dict(sorted(amendments.items())),
            "amendmentSharePctByFamily": {k: round(100 * amendments[k] / v, 2) for k, v in sorted(families.items())}}


def sample_plan(units: list[dict], firsts_by_corp: dict) -> list[dict]:
    rng = random.Random(SAMPLE_SEED)
    by_year = defaultdict(list)
    for unit in units:
        if unit.get("prelimNotAfterFormal") is True:
            prelim = firsts_by_corp[unit["corp"]][(sprint.PRELIM, date.fromisoformat(unit["quarter"]))]
            by_year[unit["year"]].append({"corp": unit["corp"], "quarter": unit["quarter"],
                                          "rcept_no": prelim["rcept_no"], "rcept_dt": prelim["rcept_dt"],
                                          "report_nm": prelim["report_nm"]})
    sample = []
    for year in sorted(by_year):
        pool = sorted(by_year[year], key=lambda r: r["rcept_no"])
        sample.extend(rng.sample(pool, min(SAMPLE_PER_YEAR, len(pool))))
    return sorted(sample, key=lambda r: r["rcept_no"])


def merged_store(path: str | None) -> tuple[dict, dict]:
    if not path:
        return {}, {}
    files = sorted(glob.glob(str(Path(path) / "dart-*.jsonl.gz")))
    out = {}
    for f in files:
        for row in read_jsonl_gz(f):
            out[(row["corpCode"], int(row["fiscalYear"]), row["reportCode"])] = row
    return out, {Path(f).name: sha256_file(f) for f in files}


def formal_amount(record: dict, account: str) -> float | None:
    entry = (record.get("accounts") or {}).get(account)
    if not entry:
        return None
    return (entry.get("amounts") or {}).get("thstrm_amount")


def sample_checks(sample_rows: list[dict], merged: dict) -> dict:
    served = [r for r in sample_rows if r.get("served") == "ZIP"]
    fields = ("revenue", "operatingIncome", "netIncome")
    parse = {f: sum(1 for r in served if r.get(f) is not None and r.get(f + "PriorYear") is not None) for f in fields}
    all_three = sum(1 for r in served if all(r.get(f) is not None and r.get(f + "PriorYear") is not None for f in fields))
    mapped = [r for r in served if sprint.period_label_quarter(r.get("periodLabel"))]
    agree = 0
    for r in mapped:
        year, month = sprint.period_label_quarter(r["periodLabel"])
        agree += sprint.quarter_end(year, month).isoformat() == r["quarter"]
    revision = {f: [] for f in ("revenue", "operatingIncome")}
    revision_basis = Counter()
    for r in served:
        q = date.fromisoformat(r["quarter"])
        if q.month == 12:
            continue  # FY formal states the year, not Q4; not compared
        record = merged.get((r["corp"], q.year, REPORT_CODE[q.month]))
        if not record:
            revision_basis["NO_FORMAL_RECORD"] += 1
            continue
        consolidated_formal = record.get("fsDiv") == "CFS"
        if bool(r.get("consolidated")) != consolidated_formal:
            revision_basis["CONSOLIDATION_BASIS_DIFFERS"] += 1
            continue
        revision_basis["COMPARED"] += 1
        for field, account in (("revenue", "매출액"), ("operatingIncome", "영업이익")):
            formal = formal_amount(record, account)
            if r.get(field) is None or formal in (None, 0):
                continue
            revision[field].append(abs(r[field] - formal) / abs(formal))
    def dist(values):
        return {"n": len(values),
                "within1PctShare": round(100 * sum(v <= 0.01 for v in values) / len(values), 2) if values else None,
                "within5PctShare": round(100 * sum(v <= 0.05 for v in values) / len(values), 2) if values else None,
                "medianAbsRelDiff": sprint.percentile(values, 0.5)}
    return {
        "sampleSize": len(sample_rows),
        "servedZip": len(served),
        "parsedCurrentAndPriorYear": parse,
        "parsedAllThreeItems": all_three,
        "parseRateAllThreePct": round(100 * all_three / len(served), 2) if served else None,
        "periodLabelParsed": len(mapped),
        "quarterAssignmentAgreement": agree,
        "quarterAssignmentAgreementPct": round(100 * agree / len(mapped), 2) if mapped else None,
        "prelimVsFormalBasis": dict(sorted(revision_basis.items())),
        "prelimVsFormalAbsRelDiff": {f: dist(v) for f, v in revision.items()},
        "unitsSeen": dict(Counter(r.get("unit") for r in served)),
        "consolidatedShare": round(100 * sum(1 for r in served if r.get("consolidated")) / len(served), 2) if served else None,
    }


def phase_c_lag(units: list[dict], firsts_by_corp: dict, merged: dict, sessions: list[date]) -> dict:
    """Sessions between the prelim receipt and the date the sealed merged store made the
    same quarter visible (``availableFrom``; Phase C's accounting family used this store)."""
    leads, missing = [], 0
    for unit in units:
        if unit.get("prelimNotAfterFormal") is not True:
            continue
        q = date.fromisoformat(unit["quarter"])
        record = merged.get((unit["corp"], q.year, REPORT_CODE[q.month]))
        if not record:
            missing += 1
            continue
        prelim = firsts_by_corp[unit["corp"]][(sprint.PRELIM, q)]
        leads.append(sprint.session_count_between(sessions, sprint.parse_ymd(prelim["rcept_dt"]),
                                                  date.fromisoformat(record["availableFrom"])))
    return {"n": len(leads), "unitsWithoutStoreRecord": missing,
            "leadSessionsMedian": sprint.percentile(leads, 0.5),
            "leadSessionsP25": sprint.percentile(leads, 0.25),
            "leadSessionsP75": sprint.percentile(leads, 0.75),
            "leadSessionsP90": sprint.percentile(leads, 0.9)}


def ownership_maturity(paths: list[str], sessions_through: list[date]) -> dict:
    events = [row for p in paths for row in read_jsonl_gz(p)]
    dates = sorted(sprint.parse_ymd(str(e.get("availableFrom") or e.get("rcept_dt"))) for e in events
                   if e.get("availableFrom") or e.get("rcept_dt"))
    last = sessions_through[-1]
    def matured(h):
        cutoff = sessions_through[-1 - h] if len(sessions_through) > h else None
        return sum(1 for d in dates if cutoff and d < cutoff), cutoff
    m126, c126 = matured(126)
    m252, c252 = matured(252)
    return {"events": len(dates), "first": dates[0].isoformat() if dates else None,
            "last": dates[-1].isoformat() if dates else None, "lastSession": last.isoformat(),
            "maturedH126": m126, "h126EntryCutoff": c126.isoformat() if c126 else None,
            "maturedH252": m252, "h252EntryCutoff": c252.isoformat() if c252 else None,
            "distinctMonthsMaturedH252": len({(d.year, d.month) for d in dates if c252 and d < c252})}


def reparse(records: list[dict]) -> dict[str, dict]:
    """Parse every stored results table with the current parser (no refetch)."""
    out = {}
    for record in records:
        if record.get("served") != "ZIP":
            continue
        parsed = sprint.parse_prelim_text(record.get("tableText", ""))
        parsed["consolidated"] = "연결" in record.get("report_nm", "") or parsed["consolidated"]
        out[record["rcept_no"]] = parsed
    return out


def content_confirmed(args, data, member, collected, sessions, merged) -> dict:
    records = read_jsonl_gz(args.doc_parses)
    parses = reparse(records)
    sample_ids = set()
    if args.sample:
        sample_ids = {r["rcept_no"] for r in read_jsonl_gz(args.sample)}
    kinds = Counter((p["periodKind"] or "UNREAD") for p in parses.values())
    stated = [p for p in parses.values() if p["earningsStated"]]
    holdout = [p for rid, p in parses.items() if rid not in sample_ids and p["earningsStated"]]
    fields = ("revenue", "operatingIncome", "netIncome")
    def rate(rows, need_prior=True):
        ok = sum(1 for p in rows if all(p.get(f) is not None and (not need_prior or p.get(f + "PriorYear") is not None) for f in fields))
        return {"n": len(rows), "allThreeCurrentAndPriorYear": ok, "pct": round(100 * ok / len(rows), 2) if rows else None,
                "revenueOrOperatingCurrent": sum(1 for p in rows if p.get("revenue") is not None or p.get("operatingIncome") is not None)}
    by_rcept_plan_quarter = {r["rcept_no"]: r for corp_rows in data["rowsByCorp"].values() for r in corp_rows}
    agree = total = 0
    for rid, p in parses.items():
        q = sprint.stated_quarter(p)
        row = by_rcept_plan_quarter.get(rid)
        if q is None or row is None:
            continue
        total += 1
        agree += q == sprint.previous_quarter_end(sprint.parse_ymd(row["rcept_dt"]))
    firsts = {}
    for corp, rows in data["rowsByCorp"].items():
        base = dict(sprint.first_originals(rows))
        for key in [k for k in base if k[0] == sprint.PRELIM]:
            del base[key]
        for quarter, row in sprint.confirmed_prelims(rows, parses).items():
            base[(sprint.PRELIM, quarter)] = row
        firsts[corp] = base
    table = sprint.coverage_table(member, data["codeToCorp"], firsts, sessions, collected)
    revision = revision_vs_formal(table["units"], firsts, parses, merged)
    return {
        "documentsFetched": len(records), "documentsServedZip": len(parses),
        "periodKindCounts": dict(sorted(kinds.items())),
        "earningsStatedDocuments": len(stated),
        "parseRateAllDocuments": rate(stated),
        "parseRateHoldoutExcludingDevelopmentSample": rate(holdout),
        "receiptQuarterVsStatedQuarterAgreement": {"n": total, "agree": agree,
                                                   "pct": round(100 * agree / total, 2) if total else None},
        "coverage": sprint.summarize(table["units"]),
        "uncollectedIssuerQuartersByYear": table["uncollectedIssuerQuartersByYear"],
        "prelimVsFormal": revision,
        "phaseCAccountingVisibilityLag": phase_c_lag(table["units"], firsts, merged, sessions),
        "yoyChangeAvailability": yoy_availability(table["units"], firsts, parses),
        "redundancyWithVisibleFormalGrowth": redundancy(table["units"], firsts, parses, merged),
    }


def revision_vs_formal(units, firsts, parses, merged) -> dict:
    """Preliminary vs later formal figure for the same Q1-Q3 quarter on the same consolidation basis."""
    diffs = {"revenue": [], "operatingIncome": []}
    basis = Counter()
    for unit in units:
        if unit.get("prelimNotAfterFormal") is not True:
            continue
        q = date.fromisoformat(unit["quarter"])
        if q.month == 12:
            basis["Q4_NOT_COMPARED"] += 1
            continue
        record = merged.get((unit["corp"], q.year, REPORT_CODE[q.month]))
        if not record:
            basis["NO_FORMAL_RECORD"] += 1
            continue
        parsed = parses[firsts[unit["corp"]][(sprint.PRELIM, q)]["rcept_no"]]
        if parsed.get("periodKind") != "QUARTER":
            basis["PRELIM_NOT_STANDALONE_QUARTER"] += 1
            continue
        if bool(parsed.get("consolidated")) != (record.get("fsDiv") == "CFS"):
            basis["CONSOLIDATION_BASIS_DIFFERS"] += 1
            continue
        basis["COMPARED"] += 1
        for field, account in (("revenue", "매출액"), ("operatingIncome", "영업이익")):
            formal = formal_amount(record, account)
            if parsed.get(field) is None or formal in (None, 0):
                continue
            diffs[field].append(abs(parsed[field] - formal) / abs(formal))
    def dist(values):
        return {"n": len(values),
                "within0_5PctShare": round(100 * sum(v <= 0.005 for v in values) / len(values), 2) if values else None,
                "within1PctShare": round(100 * sum(v <= 0.01 for v in values) / len(values), 2) if values else None,
                "within5PctShare": round(100 * sum(v <= 0.05 for v in values) / len(values), 2) if values else None,
                "medianAbsRelDiff": sprint.percentile(values, 0.5),
                "p90AbsRelDiff": sprint.percentile(values, 0.9)}
    return {"basis": dict(sorted(basis.items())), "absRelDiff": {k: dist(v) for k, v in diffs.items()}}


def yoy_availability(units, firsts, parses) -> dict:
    """How often a confirmed preliminary filing states a usable year-over-year change."""
    n = with_rev = with_op = 0
    for unit in units:
        if unit.get("prelimNotAfterFormal") is not True:
            continue
        p = parses[firsts[unit["corp"]][(sprint.PRELIM, date.fromisoformat(unit["quarter"]))]["rcept_no"]]
        n += 1
        with_rev += p.get("revenue") is not None and bool(p.get("revenuePriorYear"))
        with_op += p.get("operatingIncome") is not None and p.get("operatingIncomePriorYear") is not None
    return {"confirmedUnits": n, "revenueYoYStated": with_rev, "operatingIncomeYoYStated": with_op,
            "revenueYoYPct": round(100 * with_rev / n, 2) if n else None,
            "operatingIncomeYoYPct": round(100 * with_op / n, 2) if n else None}


def redundancy(units, firsts, parses, merged) -> dict:
    """Cross-sectional rank correlation, per quarter, between the preliminary YoY change of quarter q
    and the YoY change of quarter q-1 that the formal filing had already made visible on the
    preliminary filing's receipt date. Signal-time information only."""
    previous_code = {6: ("11013", 0), 9: ("11012", 0), 12: ("11014", 0)}
    by_quarter: dict[str, dict[str, list]] = defaultdict(lambda: {"rev": [], "op": []})
    reasons = Counter()
    for unit in units:
        if unit.get("prelimNotAfterFormal") is not True:
            continue
        q = date.fromisoformat(unit["quarter"])
        if q.month not in previous_code:
            reasons["Q1_PREVIOUS_IS_FY_NOT_COMPARED"] += 1
            continue
        prelim_row = firsts[unit["corp"]][(sprint.PRELIM, q)]
        parsed = parses[prelim_row["rcept_no"]]
        if parsed.get("periodKind") != "QUARTER":
            reasons["PRELIM_NOT_STANDALONE_QUARTER"] += 1
            continue
        code, _ = previous_code[q.month]
        now, before = merged.get((unit["corp"], q.year, code)), merged.get((unit["corp"], q.year - 1, code))
        if not now or not before:
            reasons["NO_FORMAL_PAIR"] += 1
            continue
        if now["availableFrom"] > sprint.parse_ymd(prelim_row["rcept_dt"]).isoformat():
            reasons["FORMAL_NOT_YET_VISIBLE"] += 1
            continue
        reasons["USED"] += 1
        for key, field, account in (("rev", "revenue", "매출액"), ("op", "operatingIncome", "영업이익")):
            cur, prior = parsed.get(field), parsed.get(field + "PriorYear")
            f_now, f_before = formal_amount(now, account), formal_amount(before, account)
            if None in (cur, prior, f_now, f_before) or prior <= 0 or f_before <= 0:
                continue
            by_quarter[unit["quarter"]][key].append((cur / prior - 1, f_now / f_before - 1))
    summary = {}
    for key in ("rev", "op"):
        rhos = []
        for pairs in (v[key] for v in by_quarter.values()):
            if len(pairs) >= 20:
                rho = sprint.spearman([a for a, _ in pairs], [b for _, b in pairs])
                if rho is not None:
                    rhos.append(rho)
        summary[{"rev": "revenueYoY", "op": "operatingIncomeYoY"}[key]] = {
            "quartersWithAtLeast20Names": len(rhos),
            "meanSpearman": round(sum(rhos) / len(rhos), 4) if rhos else None,
            "medianSpearman": sprint.percentile(rhos, 0.5),
            "minSpearman": min(rhos) if rhos else None, "maxSpearman": max(rhos) if rhos else None,
            "redundancyCeiling": 0.70}
    return {"pairsByReason": dict(sorted(reasons.items())), **summary,
            "reading": "prelim YoY of quarter q against formal YoY of quarter q-1 visible at the prelim receipt date; positive-denominator pairs only"}


def minimum_effective_sample() -> dict:
    """Outcome-free power arithmetic; sigma is an already-published Phase C number."""
    out = {}
    for horizon, mse, per_year in (("H126", 0.093059, 2), ("H252", 0.346663, 1)):
        sigma = mse ** 0.5
        by_rho = {}
        for rho in (0.0, 0.05):
            rows = {}
            for target in (0.02, 0.04, 0.06):
                k = sprint.cohorts_needed(sigma, 40, rho, target)
                rows[f"{target:.2f}"] = {"independentCohortsNeeded": round(k, 1), "yearsNeeded": round(k / per_year, 1)}
            by_rho[f"{rho:.2f}"] = {"mdeOneCohort": round(sprint.mde(sigma, 40, rho, 1.0), 4),
                                    "mdeOverHistory13y": round(sprint.mde(sigma, 40, rho, 13 * per_year), 4),
                                    "byTargetSpread": rows}
        out[horizon] = {"sigma": round(sigma, 4),
                        "sigmaSource": f"Phase C B0 {horizon} MSE {mse} (docs/kr-alpha-research-final-development-assessment.md section 3)",
                        "nPerTercile": 40, "nonOverlappingCohortsPerYear": per_year,
                        "rhoIsAssumptionNotMeasured": True, "byRho": by_rho}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-dir", required=True)
    parser.add_argument("--collection-universe", required=True)
    parser.add_argument("--dart-list", required=True)
    parser.add_argument("--merged-dir")
    parser.add_argument("--sample")
    parser.add_argument("--ownership", nargs="*", default=[])
    parser.add_argument("--investor-flow-manifest")
    parser.add_argument("--write-sample-plan")
    parser.add_argument("--write-full-plan")
    parser.add_argument("--doc-parses", help="gz jsonl from sample_docs.py over the full plan")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    data = load_inputs(args)
    sessions = kr_sessions()
    firsts_by_corp = {corp: sprint.first_originals(rows) for corp, rows in data["rowsByCorp"].items()}
    quarters = sprint.quarters_between(FIRST_QUARTER, LAST_QUARTER)
    member = sprint.member_quarters(data["snapshots"], quarters)
    collected = {corp for corp, n in _complete_by_corp(data).items() if n == 2}
    table = sprint.coverage_table(member, data["codeToCorp"], firsts_by_corp, sessions, collected)
    units = table["units"]

    if args.write_sample_plan:
        plan = sample_plan(units, firsts_by_corp)
        Path(args.write_sample_plan).write_text(json.dumps({"seed": SAMPLE_SEED, "perYear": SAMPLE_PER_YEAR,
                                                            "sample": plan}, ensure_ascii=False, indent=1))
        print(json.dumps({"sample": len(plan)}))
        return 0

    if args.write_full_plan:
        member_units = {(u["corp"], u["quarter"]) for u in units}
        plan = []
        for corp, rows in sorted(data["rowsByCorp"].items()):
            for r in rows:
                if sprint.classify(r["report_nm"]) != sprint.PRELIM or sprint.is_amendment(r["report_nm"]):
                    continue
                quarter = sprint.previous_quarter_end(sprint.parse_ymd(r["rcept_dt"])).isoformat()
                if (corp, quarter) in member_units:
                    plan.append({"corp": corp, "rcept_no": r["rcept_no"], "rcept_dt": r["rcept_dt"],
                                 "report_nm": r["report_nm"], "quarter": quarter})
        Path(args.write_full_plan).write_text(json.dumps({"scope": "PRELIM originals in PIT member issuer-quarters",
                                                         "sample": sorted(plan, key=lambda r: r["rcept_no"])},
                                                        ensure_ascii=False, indent=0))
        print(json.dumps({"plan": len(plan), "units": len({(r["corp"], r["quarter"]) for r in plan})}))
        return 0

    merged, merged_hashes = merged_store(args.merged_dir)
    confirmed = None
    if args.doc_parses:
        confirmed = content_confirmed(args, data, member, collected, sessions, merged)
    summary = sprint.summarize(units)
    sample_rows = read_jsonl_gz(args.sample) if args.sample else []
    checks = sample_checks(sample_rows, merged) if sample_rows else None
    lag = phase_c_lag(units, firsts_by_corp, merged, sessions) if merged else None
    collected_corps = collected
    issuers = data["collection"]["issuers"]
    results = {
        "studyId": "alpha-mechanism-sprint-v1",
        "evidenceClass": "OUTCOME_BLIND_SOURCE_ELIGIBILITY",
        "returnsRead": 0, "labelsBuilt": 0, "modelsFit": 0,
        "population": {
            "everTop120Codes": len({r["code"] for r in data["snapshots"] if r.get("rank") and int(r["rank"]) <= 120}),
            "snapshotDates": len({r["date"] for r in data["snapshots"]}),
            "dartIssuers": len(issuers),
            "unresolvedSecurities": [u["ticker"] for u in data["collection"].get("unresolved", [])],
            "issuersCollected": len(collected_corps),
            "collectionErrors": data["collectState"].get("errors", {}),
            "collectLastRun": data["collectState"].get("lastRun"),
            "quarters": [quarters[0].isoformat(), quarters[-1].isoformat()],
            "unresolvedMemberSecurityQuartersByYear": table["unresolvedMemberSecuritiesByYear"],
            "uncollectedIssuerQuartersByYear": table["uncollectedIssuerQuartersByYear"],
        },
        "disclosureInventory": disclosure_inventory(data["rowsByCorp"]),
        "coverage": summary,
        "timingPrecision": {"source": "DART list.json rcept_dt (YYYYMMDD) and rcept_no (date + daily serial)",
                            "clockTimeAvailable": False,
                            "evidence": "list.json has no time field; document.xml body and dart.fss.or.kr viewer page carry no receipt time; KIND (kind.krx.co.kr) answered HTTP 403 from this environment"},
        "documentSample": checks,
        "contentConfirmed": confirmed,
        "phaseCAccountingVisibilityLag": lag,
        "ownershipEventsMaturity": ownership_maturity(args.ownership, sessions) if args.ownership else None,
        "investorFlowManifest": json.loads(Path(args.investor_flow_manifest).read_text()) if args.investor_flow_manifest else None,
        "minimumEffectiveSample": minimum_effective_sample(),
        "sourceHashes": {**data["hashes"], "mergedStore": merged_hashes,
                         "documentSample": sha256_file(args.sample) if args.sample else None,
                         "documentParses": sha256_file(args.doc_parses) if args.doc_parses else None,
                         "ownershipShards": {Path(p).name: sha256_file(p) for p in args.ownership},
                         "investorFlowManifest": sha256_file(args.investor_flow_manifest) if args.investor_flow_manifest else None},
    }
    results["provenance"] = {
        "mainCommit": "37f8cbf6b1c066f6b3c65235953648d17ebf2f69",
        "signalHistoryCommit": "5d187ec16dca29c68161060f4002227297ebd632",
        "signalHistoryPaths": ["ledger/universe/kr/krx-universe-*.jsonl.gz",
                               "ledger/dart-ownership-events/collection-universe.json",
                               "ledger/fundamentals/kr-candidate-merged/dart-*.jsonl.gz",
                               "ledger/dart-ownership-events/dart-ownership-*.jsonl.gz",
                               "ledger/kr-investor-flow/manifest.json"],
        "dartEndpoints": ["list.json (pblntf_ty I and A, 2012-10-01..2026-10-31)", "document.xml"],
        "collectedOn": "2026-11-01",
        "parserRevisions": PARSER_REVISIONS,
    }
    results["candidateScreen"] = json.loads((HERE / "candidate_screen.json").read_text(encoding="utf-8"))
    results["gates"] = gates(results)
    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(json.dumps(results["gates"], ensure_ascii=False, indent=1))
    return 0


def gates(results: dict) -> dict:
    """Protocol section 5 gates. Content-confirmed figures supersede the name-only ones when present."""
    confirmed = results.get("contentConfirmed")
    name_only = results["coverage"]["overall"]
    overall = confirmed["coverage"]["overall"] if confirmed else name_only
    g1, g3 = overall["coveragePct"], overall["leadSessionsMedian"]
    parse = (confirmed or {}).get("parseRateHoldoutExcludingDevelopmentSample", {}).get("pct")
    assign = (confirmed or {}).get("receiptQuarterVsStatedQuarterAgreement", {}).get("pct")
    revision = ((confirmed or {}).get("prelimVsFormal", {}).get("absRelDiff") or {}).get("revenue", {})
    within = revision.get("within1PctShare")

    def check(value, ok):
        return None if value is None else bool(ok(value))

    out = {
        "basis": "CONTENT_CONFIRMED" if confirmed else "REPORT_NAME_ONLY",
        "G1_coverage": {"value": g1, "nameOnlyValue": name_only["coveragePct"], "threshold": ">= 60", "pass": check(g1, lambda v: v >= 60)},
        "G2_clockTime": {"value": results["timingPrecision"]["clockTimeAvailable"], "pass": results["timingPrecision"]["clockTimeAvailable"]},
        "G3_leadSessionsMedian": {"value": g3, "threshold": "> 5", "pass": check(g3, lambda v: v > 5)},
        "G4_parseRate": {"value": parse, "threshold": ">= 90", "pass": check(parse, lambda v: v >= 90)},
        "G4_quarterAssignment": {"value": assign, "threshold": ">= 95", "pass": check(assign, lambda v: v >= 95)},
        "G5_identity": {"value": f"{results['population']['dartIssuers']} issuers collected {results['population']['issuersCollected']}, unresolved securities {len(results['population']['unresolvedSecurities'])}",
                        "pass": results["population"]["issuersCollected"] == results["population"]["dartIssuers"]},
        "G6_revenueWithin1PctShare": {"value": within, "pass": None, "reading": "report only"},
    }
    if out["G1_coverage"]["pass"] is False:
        verdict = "SOURCE_INSUFFICIENT"
    elif out["G3_leadSessionsMedian"]["pass"] is False and (within or 0) >= 50:
        verdict = "TIMING_ONLY_NOT_INDEPENDENT_FOR_H126_H252"
    elif all(out[k]["pass"] for k in ("G1_coverage", "G3_leadSessionsMedian", "G4_parseRate", "G4_quarterAssignment")):
        verdict = "ELIGIBLE_FOR_PROSPECTIVE_REGISTRATION_ONLY"
    else:
        verdict = "UNKNOWN_GATE_INCOMPLETE"
    out["verdict"] = verdict
    return out


if __name__ == "__main__":
    raise SystemExit(main())
