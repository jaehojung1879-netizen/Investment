"""Bounded input-only audit of existing immutable Finnhub shards (never collects).

Company-dates are publication events + one calendar day, not index constituent
dates or investment observations. No return/label/model module is imported.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import finnhub_fundamentals as FF  # noqa: E402
from pipeline import us_shareholder_distribution as U  # noqa: E402

JOINT_FIELDS = ("cashDividendsPaidTTM", "commonStockRepurchasesTTM", "operatingCashFlowTTM",
                "totalCashDistributionChangeYoY", "distributionToOCF")
ALL_CONCEPTS = {c for family in U.CONCEPT_FAMILIES.values() for c in family}
ANCHORS = {c for concepts in FF.UNIT_ANCHORS.values() for c in concepts}


def _value(entry):
    value = entry.get("value")
    return float(value) if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) else None


def _family_tallies(record):
    entries = [e for s in ("cf", "bs", "ic") for e in record.get("statements", {}).get(s, [])]
    resolved = FF.resolve_units(record)
    tallies = {}
    for family, concepts in U.CONCEPT_FAMILIES.items():
        rows = [e for e in entries if FF.strip_namespace(e.get("concept")) in concepts]
        unit = FF.SHARES if family == "shares" else FF.PER_SHARE if family == "dividendPerShare" else FF.CURRENCY
        values = [_value(e) for e in rows if FF.value_class(record, e, resolved) == unit and _value(e) is not None]
        tallies[family] = Counter(filings=1, reported=bool(rows), notReported=not rows,
                                  hasPositive=any(v > 0 for v in values), hasReportedZero=any(v == 0 for v in values),
                                  hasNegative=any(v < 0 for v in values),
                                  hasInvalidValueOrUnit=len(values) < len(rows))
    return tallies


def _project(record):
    out = {k: record.get(k) for k in ("id", "ticker", "source", "fiscalYear", "fiscalQuarter", "form",
                                     "periodStart", "periodEnd", "periodDays", "availableFrom", "acceptedDate", "collectedAt")}
    out["statements"] = {s: [{k: e.get(k) for k in ("concept", "unit", "value")}
                              for e in record.get("statements", {}).get(s, [])
                              if FF.strip_namespace(e.get("concept")) in ALL_CONCEPTS | ANCHORS]
                         for s in ("cf", "bs", "ic")}
    return out


def _semantics(grouped):
    observations = {concept: defaultdict(dict) for concept in U.FLOW_CONCEPTS.values()}
    for ticker, rows in grouped.items():
        for row in sorted(rows, key=lambda r: (r.get("availableFrom") or "", str(r.get("id")))):
            stage = FF.quarter_stage(row)
            year = row.get("fiscalYear")
            if stage is None or isinstance(year, bool) or not isinstance(year, int) or not 1990 <= year <= 2100:
                continue
            resolved = FF.resolve_units(row)
            for concept in observations:
                candidates = [e for e in row["statements"]["cf"] if FF.strip_namespace(e.get("concept")) == concept
                              and FF.value_class(row, e, resolved) == FF.CURRENCY and _value(e) is not None]
                if len(candidates) == 1:
                    observations[concept][ticker, year].setdefault(stage, _value(candidates[0]))
    report = {}
    for concept, years in observations.items():
        ratios = {"Q2OverQ1": [], "Q3OverQ1": [], "Q3OverFY": []}
        for values in years.values():
            first = values.get("Q1")
            if first is not None and first > 0:
                for stage, key in (("Q2", "Q2OverQ1"), ("Q3", "Q3OverQ1")):
                    if values.get(stage) is not None:
                        ratios[key].append(values[stage] / first)
            if values.get("Q3") is not None and values.get("FY", 0) > 0:
                ratios["Q3OverFY"].append(values["Q3"] / values["FY"])
        mids = {k: median(v) if v else None for k, v in ratios.items()}
        counts = {k: len(v) for k, v in ratios.items()}
        cumulative = (counts["Q2OverQ1"] >= FF.MIN_RATIOS and counts["Q3OverQ1"] >= FF.MIN_RATIOS
                      and FF.CUMULATIVE_BAND[0][0] <= mids["Q2OverQ1"] <= FF.CUMULATIVE_BAND[0][1]
                      and FF.CUMULATIVE_BAND[1][0] <= mids["Q3OverQ1"] <= FF.CUMULATIVE_BAND[1][1])
        report[concept] = {"medians": mids, "counts": counts, "verdict": "CUMULATIVE_CORROBORATED" if cumulative else "INCONCLUSIVE",
                           "limitation": "Aggregate value ratios corroborate vendor convention; flattened rows lack their own XBRL contexts."}
    return report


def build_report(directory: Path, *, source_commit: str, cutoff: str, max_filings=40_000) -> dict:
    directory = directory.resolve()
    cutoff_day = U.parse_day(cutoff)
    if not cutoff_day or cutoff_day.isoformat() != cutoff:
        raise ValueError("cutoff must be an ISO calendar date")
    if len(source_commit) != 40 or any(c not in "0123456789abcdef" for c in source_commit):
        raise ValueError("source_commit must identify an immutable full Git SHA")
    paths = sorted(directory.glob("finnhub-*.jsonl.gz"))
    if not paths:
        raise ValueError("NOT_MEASURED: no Finnhub shards; an empty run is not readiness")
    if sum(p.stat().st_size for p in paths) > 128 * 1024 * 1024:
        raise ValueError("compressed input exceeds 128 MiB audit bound")
    source_files = []
    manifest = directory / "source-manifest.json"
    if not manifest.exists():
        raise ValueError("immutable source-manifest.json with commit and Git blob IDs is required")
    declared = json.loads(manifest.read_text())
    if declared["commit"] != source_commit:
        raise ValueError("SOURCE_COMMIT_MISMATCH")
    expected = {Path(item["path"]).name: item for item in declared["files"] if item["path"].endswith(".jsonl.gz")}
    if set(expected) != {p.name for p in paths}:
        raise ValueError("SOURCE_FILE_SET_MISMATCH")
    grouped, concepts = defaultdict(list), {}
    by_year = defaultdict(lambda: defaultdict(Counter))
    by_company = defaultdict(lambda: defaultdict(Counter))
    metadata = Counter()
    identities = defaultdict(set)
    identity_counts = Counter()
    n = 0
    for path in paths:
        blob = path.read_bytes()
        oid = hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()
        if expected[path.name]["gitBlob"] != oid:
            raise ValueError("SOURCE_BLOB_MISMATCH: " + path.name)
        source_files.append({"name": path.name, "gitBlob": oid, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)})
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                n += 1
                if n > max_filings:
                    raise ValueError("filing count exceeds bounded audit; no partial report emitted")
                record = json.loads(line)
                ticker = record.get("ticker")
                if not ticker or record.get("source") != U.SOURCE:
                    raise ValueError("SOURCE_OR_TICKER_IDENTITY_MISMATCH")
                available = U.parse_day(record.get("availableFrom"))
                accepted = U.parse_day(record.get("acceptedDate"))
                visible = max(available, accepted) if available and accepted else available
                metadata["missingAvailability"] += available is None
                metadata["missingAcceptanceTimestamp"] += not record.get("acceptedDate")
                if visible and visible >= cutoff_day:
                    metadata["notVisibleAtCutoff"] += 1
                    continue
                end = U.parse_day(record.get("periodEnd"))
                metadata["availabilityBeforePeriodEnd"] += bool(available and end and available < end)
                fiscal = record.get("fiscalYear")
                valid_year = not isinstance(fiscal, bool) and isinstance(fiscal, int) and 1990 <= fiscal <= 2100
                metadata["malformedFiscalYear"] += not valid_year
                year = str(fiscal) if valid_year else "INVALID"
                projection = _project(record)
                identity_counts[record.get("id")] += 1
                identities[record.get("id")].add(U.canonical_digest({k: v for k, v in projection.items() if k != "collectedAt"}))
                grouped[ticker].append(projection)
                tallies = _family_tallies(record)
                for family, counts in tallies.items():
                    by_year[year][family].update(counts)
                    by_company[ticker][family].update(counts)
                for section, entries in record.get("statements", {}).items():
                    for entry in entries:
                        c = FF.strip_namespace(entry.get("concept"))
                        if c not in ALL_CONCEPTS:
                            continue
                        item = concepts.setdefault(c, {"rawConceptNames": set(), "units": Counter(), "sections": Counter(),
                                                      "fiscalStages": Counter(), "fiscalYears": Counter(), "valueStates": Counter(),
                                                      "firstAvailableFrom": None, "lastAvailableFrom": None, "amendedRows": 0})
                        item["rawConceptNames"].add(entry["concept"])
                        item["units"][str(entry.get("unit"))] += 1
                        item["sections"][section] += 1
                        item["fiscalStages"][FF.quarter_stage(record) or "INVALID"] += 1
                        item["fiscalYears"][year] += 1
                        value = _value(entry)
                        item["valueStates"]["INVALID" if value is None else "POSITIVE" if value > 0 else "ZERO" if value == 0 else "NEGATIVE"] += 1
                        item["amendedRows"] += str(record.get("form")).endswith("/A")
                        if available:
                            stamp = available.isoformat()
                            item["firstAvailableFrom"] = min(item["firstAvailableFrom"] or stamp, stamp)
                            item["lastAvailableFrom"] = max(item["lastAvailableFrom"] or stamp, stamp)
    if not grouped:
        raise ValueError("NOT_MEASURED: no observable source filings at cutoff")
    semantics = _semantics(grouped)
    # One input-only audit defines the convention evidence; no outcome-based
    # field or formula selection is possible. Inconclusive fields are withheld.
    evidence = U.canonical_digest(semantics)
    source = U.SourceMetadata(U.SOURCE, source_commit, "input-only-family-semantics:" + evidence,
                              unverified_flow_concepts=tuple(c for c, s in semantics.items() if s["verdict"] != "CUMULATIVE_CORROBORATED"))
    feature_states, by_feature_year, companies = defaultdict(Counter), defaultdict(lambda: defaultdict(Counter)), {}
    feature_digest_stream = hashlib.sha256()
    company_dates = joint = 0
    for ticker, rows in sorted(grouped.items()):
        engine = U.FeatureEngine(ticker, rows, source)
        events = sorted({r.visible_day + timedelta(days=1) for r in engine._filings
                         if r.visible_day + timedelta(days=1) <= cutoff_day})
        own_states, own_joint = defaultdict(Counter), 0
        for event in events:
            snapshot = engine.as_of(event.isoformat())
            company_dates += 1
            feature_digest_stream.update((ticker + "|" + event.isoformat() + "|" + snapshot.feature_digest + "\n").encode())
            ready = all(snapshot.features[name].value is not None for name in JOINT_FIELDS)
            # Every selected cumulative family must also have measured support.
            ready = ready and all(semantics[U.FLOW_CONCEPTS[name]]["verdict"] == "CUMULATIVE_CORROBORATED"
                                  for name in ("cashDividendsPaidTTM", "commonStockRepurchasesTTM", "operatingCashFlowTTM"))
            joint += ready
            own_joint += ready
            for name, feature in snapshot.features.items():
                state = feature.state.value
                feature_states[name][state] += 1
                by_feature_year[str(event.year)][name][state] += 1
                own_states[name][state] += 1
        periods = sorted({r["periodEnd"] for r in rows if U.parse_day(r.get("periodEnd"))})
        companies[ticker] = {"filings": len(rows), "eventCompanyDates": len(events), "jointReadyCompanyDates": own_joint,
                             "firstObservableEvent": events[0].isoformat() if events else None,
                             "lastObservableEvent": events[-1].isoformat() if events else None,
                             "observableHistoryDays": (events[-1] - events[0]).days if events else None,
                             "firstReportPeriodEnd": periods[0] if periods else None, "lastReportPeriodEnd": periods[-1] if periods else None,
                             "distinctFiscalPeriods": len({(r.get("fiscalYear"), FF.quarter_stage(r)) for r in rows if FF.quarter_stage(r)}),
                             "featureStates": dict(own_states), "reportingFamilies": dict(by_company[ticker])}
    for concept, item in concepts.items():
        item["rawConceptNames"] = sorted(item["rawConceptNames"])
        family = next(f for f, names in U.CONCEPT_FAMILIES.items() if concept in names)
        item["family"] = family
        item["source"] = U.SOURCE
        item["accumulationConvention"] = ("FISCAL_YTD_CORROBORATED" if concept in semantics and semantics[concept]["verdict"] == "CUMULATIVE_CORROBORATED"
                                          else "CONTEXT_UNVERIFIED_STOCK_OR_WEIGHTED_AVERAGE" if family == "shares"
                                          else "PERIOD_END_LEVEL" if family == "cash" else "NOT_ACCEPTED_AS_FEATURE_INPUT")
        item["featureUse"] = "EXACT_CONCEPT_ONLY" if concept in U.FLOW_CONCEPTS.values() or concept == "CashAndCashEquivalentsAtCarryingValue" else "INVENTORY_ONLY"
        item["validityConstraints"] = ["finite numeric value", "filing-local compatible unit", "verified dates and fiscal stage",
                                        "strict publication before signal date", "no substitution with related concepts"]
        item["amendmentTreatment"] = "latest observable filing per fiscal slot; later amendments cannot rewrite an earlier as-of query"
    structural = []
    years = [y for y in sorted(by_year) if y != "INVALID"]
    for before, after in zip(years, years[1:]):
        for family in U.CONCEPT_FAMILIES:
            a, b = by_year[before][family], by_year[after][family]
            if min(a["filings"], b["filings"]) < 100:
                continue
            old, new = a["reported"] / a["filings"], b["reported"] / b["filings"]
            if abs(new - old) >= .15:
                structural.append({"family": family, "fromYear": before, "toYear": after,
                                   "fromReportingPct": round(old * 100, 4), "toReportingPct": round(new * 100, 4),
                                   "interpretation": "reporting-rate discontinuity, not proof of policy change; causal mechanism NOT_MEASURED"})
    return {
        "id": "us-shareholder-distribution-feature-audit-v1", "evidenceClass": "OUTCOME_BLIND_INPUT_QUALITY",
        "measurementStatus": "MEASURED", "featureVersion": U.FEATURE_VERSION, "sourceCommit": source_commit,
        "cutoff": cutoff, "files": source_files, "sourceMetadata": {"source": U.SOURCE, "currency": "USD", "cumulativeEvidence": source.cumulative_evidence},
        "rawFilingsRead": n, "observableFilings": sum(len(v) for v in grouped.values()), "companies": len(grouped),
        "metadataDiagnostics": dict(metadata), "duplicateSourceIDs": sum(v > 1 for v in identity_counts.values()),
        "conflictingSourceIDs": sum(len(v) > 1 for v in identities.values()),
        "fieldInventory": concepts, "cumulativeSemantics": semantics, "reportingByFiscalYear": {k: dict(v) for k, v in by_year.items()},
        "featuresByCalendarEventYear": {k: dict(v) for k, v in by_feature_year.items()}, "featureStates": dict(feature_states),
        "eventCompanyDates": company_dates, "jointReadyCompanyDates": joint, "jointReadyFields": list(JOINT_FIELDS),
        "eventGrid": "each company filing's effective publication date + 1 calendar day, capped at cutoff; no index-membership or trading-calendar claim",
        "eventFeatureDigest": feature_digest_stream.hexdigest(), "byCompany": companies, "structuralReportingBreaks": structural,
        "industrySectorCoverage": {"status": "NOT_MEASURED", "reason": "no trustworthy dated classification in the selected filing store; current labels are not backfilled"},
        "shareDilutionReadiness": {"status": "BLOCKED", "reason": "raw flattened rows do not verify period-end share context, share class or historical split basis"},
        "coverageMeaning": "reporting rates and point-in-time derivability on filing events, not an eligible investment universe; missing never becomes zero",
        "bounds": {"maxFilings": max_filings, "maxCompressedMiB": 128},
        "readsReturns": False, "readsLabels": False, "readsPrices": False, "fitsModels": False,
        "writesSignalHistory": False, "historicalResearchExecuted": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir", type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-filings", type=int, default=40_000)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if (output.suffix != ".json" or args.store_dir.resolve() in output.parents
            or any(p in output.parts for p in ("ledger", "results", "signal-history", ".git", ".github"))
            or (ROOT in output.parents and ROOT / "docs" / "us-readiness" not in output.parents)):
        raise ValueError("output must be separate from the immutable source and sealed research paths")
    report = build_report(args.store_dir, source_commit=args.source_commit, cutoff=args.cutoff, max_filings=args.max_filings)
    output.parent.mkdir(parents=True, exist_ok=True)
    # One compact line per company keeps the measured population inspectable
    # without adding 100,000 repetitive pretty-print lines to a feature PR.
    sections = []
    for key, value in sorted(report.items()):
        if key == "byCompany":
            encoded = "{\n" + ",\n".join("  " + json.dumps(ticker) + ": " + json.dumps(row, sort_keys=True, allow_nan=False)
                                         for ticker, row in sorted(value.items())) + "\n }"
        else:
            encoded = json.dumps(value, indent=1, sort_keys=True, allow_nan=False)
        sections.append(" " + json.dumps(key) + ": " + encoded)
    output.write_text("{\n" + ",\n".join(sections) + "\n}\n", encoding="utf-8")
    print(f"{report['companies']} companies, {report['rawFilingsRead']} filings, "
          f"{report['jointReadyCompanyDates']}/{report['eventCompanyDates']} joint-ready event company-dates -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
