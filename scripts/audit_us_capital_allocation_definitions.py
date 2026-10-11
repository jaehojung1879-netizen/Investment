"""Definition audit of the shareholder-distribution features: which XBRL concepts reach them, and what the rest would need.

    python scripts/audit_us_capital_allocation_definitions.py --workspace <dir> --output docs/us-readiness/us-capital-allocation-definition-audit-v1.json

Outcome-blind. It reads the pinned Finnhub shards PR #220 audited and answers four registration questions without a price:

1. DIVIDENDS / REPURCHASES / OCF. How many filings carry the exact concept the feature admits, how many carry only a
   related concept the feature REFUSES to treat as an alias, and, where both exist, whether the two even agree. The
   second number is the cost of the "exact concept only" rule; it is reported so the owner can see it, not adopted.
2. YEAR-OVER-YEAR. Which fiscal-stage chain a change needs, and how often the prior-year denominator is zero.
3. AMENDMENT CHRONOLOGY. For every fiscal slot with more than one filing, the engine must use the earlier filing before
   the later one is visible and the later filing afterwards, and never rewrite a past as-of. Checked on real slots.
4. DILUTION. Whether any share-count evidence exists in the store, and what would be needed to compute the change.

Nothing in this file proposes or adopts a different feature definition: that would be a new feature version and a
separate decision.
"""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_fundamentals as FF                   # noqa: E402
from pipeline import us_shareholder_distribution as U             # noqa: E402

_spec = importlib.util.spec_from_file_location("coverage_audit", ROOT / "scripts/audit_us_capital_allocation_coverage.py")
COV = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = COV
_spec.loader.exec_module(COV)

DIVIDEND_EXACT = "PaymentsOfDividendsCommonStock"
DIVIDEND_RELATED = {"PaymentsOfDividends": "GENERAL", "PaymentsOfOrdinaryDividends": "ORDINARY"}
PREFERRED = "PaymentsOfDividendsPreferredStockAndPreferenceStock"
REPURCHASE_EXACT = "PaymentsForRepurchaseOfCommonStock"
OCF_EXACT = "NetCashProvidedByUsedInOperatingActivities"
OCF_CONTINUING = "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"
SHARES_END = "CommonStockSharesOutstanding"
SHARES_WEIGHTED = ("WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic",
                   "WeightedAverageNumberOfBasicSharesOutstanding")
MAX_AMENDMENT_SLOTS_CHECKED = 300


def number(entry):
    value = entry.get("value")
    return float(value) if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) else None


def census(workspace: Path):
    """One pass over the raw shards: concept presence per filing, plus the slot index for the chronology check."""
    repurchase_names = Counter()
    filings = Counter()
    dividend_class, dividend_agreement, ocf_class, share_class = Counter(), Counter(), Counter(), Counter()
    forms = Counter()
    slots = defaultdict(list)
    for path in sorted(workspace.glob("finnhub-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                record = json.loads(line)
                filings["all"] += 1
                forms[str(record.get("form"))] += 1
                stage = FF.quarter_stage(record)
                resolved = FF.resolve_units(record)
                cf = {FF.strip_namespace(e.get("concept")): e for e in record.get("statements", {}).get("cf", [])}
                bs = {FF.strip_namespace(e.get("concept")): e for e in record.get("statements", {}).get("bs", [])}
                ic = {FF.strip_namespace(e.get("concept")): e for e in record.get("statements", {}).get("ic", [])}
                for concept in cf:
                    if "Repurchase" in concept or "TreasuryStock" in concept:
                        repurchase_names[concept] += 1

                def usable(entry, section_unit=FF.CURRENCY):
                    return entry is not None and number(entry) is not None and FF.value_class(record, entry, resolved) == section_unit

                has_exact = usable(cf.get(DIVIDEND_EXACT))
                related = [k for k in DIVIDEND_RELATED if usable(cf.get(k))]
                preferred = usable(cf.get(PREFERRED))
                label = ("EXACT_COMMON" if has_exact else "ONLY_" + "_".join(DIVIDEND_RELATED[k] for k in related) if related else "NONE")
                dividend_class[label + ("+PREFERRED_PRESENT" if preferred else "")] += 1
                if has_exact and related:
                    a, b = number(cf[DIVIDEND_EXACT]), number(cf[related[0]])
                    gap = abs(a - b) / max(abs(a), abs(b), 1.0)
                    dividend_agreement["EQUAL_WITHIN_0.1PCT" if gap <= 0.001 else "WITHIN_1PCT" if gap <= 0.01 else "DIFFER_OVER_1PCT"] += 1
                filings["repurchaseExact"] += usable(cf.get(REPURCHASE_EXACT))
                ocf_class["EXACT" if usable(cf.get(OCF_EXACT)) else "ONLY_CONTINUING_OPERATIONS" if usable(cf.get(OCF_CONTINUING)) else "NONE"] += 1
                share_class["bs:CommonStockSharesOutstanding"] += usable(bs.get(SHARES_END), FF.SHARES)
                share_class["ic:weightedAverage"] += any(usable(ic.get(c), FF.SHARES) for c in SHARES_WEIGHTED)
                year = record.get("fiscalYear")
                if stage and isinstance(year, int) and not isinstance(year, bool):
                    slots[(record["ticker"], year, stage)].append(
                        {"id": record["id"], "form": record.get("form"), "availableFrom": record.get("availableFrom"),
                         "acceptedDate": record.get("acceptedDate")})
    return {"filings": filings, "forms": forms, "dividendClass": dividend_class, "dividendAgreement": dividend_agreement,
            "repurchaseNames": repurchase_names, "ocfClass": ocf_class, "shareClass": share_class, "slots": slots}


def amendment_chronology(slots, engines):
    """For slots with two or more DIFFERENT filings, test the engine on the day before and the day after the later one."""
    multi = {k: v for k, v in slots.items() if len({r["id"] for r in v}) > 1}
    checked = Counter()
    failures = []
    ordered = sorted(multi)
    step = max(1, len(ordered) // MAX_AMENDMENT_SLOTS_CHECKED)
    for key in ordered[::step][:MAX_AMENDMENT_SLOTS_CHECKED]:
        ticker, year, stage = key
        engine = engines.get(ticker)
        if engine is None:
            checked["NO_ENGINE"] += 1
            continue
        filings = sorted(engine._filings, key=lambda f: (f.visible_day, f.acceptance))
        by_slot = [f for f in filings if (f.year, f.stage) == (year, stage)]
        days = sorted({f.visible_day for f in by_slot})
        if len(days) < 2:
            checked["SAME_DAY_PAIR_ORDER_BY_ACCEPTANCE"] += 1
            continue
        first_day, later_day = days[0], days[1]
        expected_before = max((f for f in by_slot if f.visible_day == first_day), key=lambda f: f.acceptance).raw["id"]
        expected_after = max((f for f in by_slot if f.visible_day <= later_day), key=lambda f: (f.visible_day, f.acceptance)).raw["id"]
        before = engine.as_of((later_day).isoformat())                       # later filing NOT yet visible on its own day
        after = engine.as_of((later_day + timedelta(days=1)).isoformat())
        used_before = {i.filing_id for f in before.features.values() for i in f.inputs if (i.fiscal_year, i.stage) == (year, stage)}
        used_after = {i.filing_id for f in after.features.values() for i in f.inputs if (i.fiscal_year, i.stage) == (year, stage)}
        if not used_before and not used_after:
            checked["SLOT_NOT_REFERENCED_BY_ANY_FEATURE"] += 1
            continue
        ok = used_before <= {expected_before} and used_after <= {expected_after}
        checked["CHRONOLOGY_RESPECTED" if ok else "CHRONOLOGY_VIOLATED"] += 1
        if not ok:
            failures.append({"slot": list(key), "usedBefore": sorted(used_before), "usedAfter": sorted(used_after)})
    return {"slotsWithMoreThanOneFiling": len(multi), "slotsChecked": sum(checked.values()), "results": dict(checked), "failures": failures[:10],
            "rule": "as_of(T) sees only filings with max(availableFrom, acceptedDate) < T; a later filing replaces its slot only after it is visible"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    grouped, ciks, shards, raw = COV.load_filings(args.workspace, COV.FUNDAMENTALS_COMMIT)
    source, semantics = COV.source_metadata(grouped)
    engines = {t: U.FeatureEngine(t, rows, source) for t, rows in grouped.items()}
    c = census(args.workspace)
    n = c["filings"]["all"]

    def pct(x):
        return round(100.0 * x / n, 4) if n else None

    dividends = {k: {"filings": v, "pct": pct(v)} for k, v in sorted(c["dividendClass"].items())}
    exact = sum(v for k, v in c["dividendClass"].items() if k.startswith("EXACT_COMMON"))
    only_related = sum(v for k, v in c["dividendClass"].items() if k.startswith("ONLY_"))
    report = {
        "id": "us-capital-allocation-definition-audit-v1", "evidenceClass": "OUTCOME_BLIND_DEFINITION_AUDIT",
        "readsReturns": False, "readsLabels": False, "readsPrices": False, "fitsModels": False, "proposesNoDefinitionChange": True,
        "featureVersion": U.FEATURE_VERSION, "sourceCommit": COV.FUNDAMENTALS_COMMIT, "shards": shards, "filings": n,
        "cumulativeSemantics": {k: {"verdict": v["verdict"], "medians": v["medians"], "counts": v["counts"]} for k, v in semantics.items()},
        "dividends": {
            "admittedConcept": DIVIDEND_EXACT, "filingsByConceptClass": dividends,
            "exactCommonPct": pct(exact), "onlyRelatedGeneralOrOrdinaryPct": pct(only_related),
            "agreementWhereBothExist": dict(c["dividendAgreement"]),
            "reading": ("A filing that carries only a general/ordinary dividend line is refused by the feature (AMBIGUOUS_ACCOUNTING), not "
                        "read as common dividends. That rule protects against preferred and noncontrolling payments but costs coverage; the "
                        "size of that cost is the 'onlyRelated' share. Adopting an alias is a new feature version and an owner decision."),
        },
        "repurchases": {"admittedConcept": REPURCHASE_EXACT, "filingsWithExact": c["filings"]["repurchaseExact"], "exactPct": pct(c["filings"]["repurchaseExact"]),
                        "repurchaseOrTreasuryConceptsSeenInCashFlow": dict(c["repurchaseNames"].most_common(15)),
                        "reading": "Other repurchase tags exist in the store and are not admitted; absence of the exact tag is NOT_REPORTED, never zero."},
        "operatingCashFlow": {"admittedConcept": OCF_EXACT, "filingsByClass": {k: {"filings": v, "pct": pct(v)} for k, v in c["ocfClass"].items()}},
        "yearOverYear": {
            "definition": "same fiscal stage, current TTM over prior-year TTM minus one; the prior value must be strictly positive",
            "chainRequired": "FY: current FY and prior FY for the TTM, plus the two years earlier for the prior-year TTM; "
                             "quarter: current cumulative, prior FY, prior same-stage cumulative, and the same three one year earlier",
            "zeroBase": "a prior-year TTM of zero is NOT_APPLICABLE (a payout that STARTED), never +100% and never 0%",
            "staleReportLimitDays": 180},
        "amendmentChronology": amendment_chronology(c["slots"], engines),
        "formCensus": dict(c["forms"].most_common(12)),
        "dilution": {"status": "BLOCKED", "periodEndShareCountFilings": {"count": c["shareClass"]["bs:CommonStockSharesOutstanding"],
                                                                         "pct": pct(c["shareClass"]["bs:CommonStockSharesOutstanding"])},
                     "weightedAverageShareFilings": {"count": c["shareClass"]["ic:weightedAverage"], "pct": pct(c["shareClass"]["ic:weightedAverage"])},
                     "whyBlocked": "the flattened rows lack the XBRL context (period-end date, share class, split basis) that a share-count change needs; "
                                   "SharesBasisEvidence is absent for every ticker pair",
                     "smallestRepair": "a per-filing source of period-end common shares with class and split-adjustment basis (for example the XBRL "
                                       "dei/us-gaap context facts), pinned by commit and hashed; weighted averages are not a substitute"},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n", encoding="utf-8")
    print("filings %d; exact common dividends %s%%; only related %s%%; amendments checked %s" % (
        n, report["dividends"]["exactCommonPct"], report["dividends"]["onlyRelatedGeneralOrOrdinaryPct"],
        report["amendmentChronology"]["results"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
