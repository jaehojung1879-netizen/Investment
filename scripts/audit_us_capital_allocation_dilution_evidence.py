"""What the stored filings can and cannot say about share-count change (dilution). Outcome-blind, no acquisition.

    python scripts/audit_us_capital_allocation_dilution_evidence.py --workspace <dir>

PR #220 blocks `sharesOutstandingChangeYoY` because the flattened store lacks the XBRL context (period-end date, share class, split
basis) that a share-count change needs. This audit asks how much usable evidence exists anyway, and of what basis:

* PERIOD_END counts (`CommonStockSharesOutstanding`, `EntityCommonStockSharesOutstanding`);
* WEIGHTED counts (diluted, then basic) that `finnhub_derive.share_count` prefers for per-share numerators;
* whether a pair (a filing and its prior-year same-stage filing) uses the same basis and whether a sealed split event falls between.

A weighted-average count is NOT a period-end count and a change between two of them is NOT issuance or buyback. This audit
therefore never produces a dilution feature; it measures what a future NEW definition could build on, and what remains BLOCKED.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_derive as FD                         # noqa: E402
from pipeline import finnhub_fundamentals as FF                   # noqa: E402
from pipeline import us_dual_benchmark_data as D                  # noqa: E402
from pipeline import us_multifactor_inputs as M                   # noqa: E402
from pipeline import us_shareholder_distribution as U             # noqa: E402


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GAPS = _load("gaps_audit", "scripts/audit_us_capital_allocation_source_gaps.py")
MF = _load("mf_audit", "scripts/audit_us_multifactor_pit_readiness.py")
OUT = ROOT / "docs/us-readiness/us-capital-allocation-dilution-evidence-v1.json"
PERIOD_END = ("CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding")
BASIS_OF = {"WeightedAverageNumberOfDilutedSharesOutstanding": "WEIGHTED_DILUTED", "WeightedAverageNumberOfSharesOutstandingBasic": "WEIGHTED_BASIC",
            "WeightedAverageNumberOfBasicSharesOutstanding": "WEIGHTED_BASIC", "CommonStockSharesOutstanding": "PERIOD_END_FACE_STATEMENT",
            "EntityCommonStockSharesOutstanding": "PERIOD_END_COVER_PAGE"}
JUMP = 0.40            # |change| above this with no sealed split is reported as a possible unrecorded split/class artifact (descriptive)


def stated_share_count(record):
    """(value, concept) following finnhub_derive.share_count's priority and unit rule, or (None, None)."""
    resolved = FF.resolve_units(record)
    stated = {}
    for section in ("ic", "bs", "cf"):
        for entry in (record.get("statements") or {}).get(section) or []:
            concept = FF.strip_namespace(entry.get("concept"))
            if concept in FD.SHARE_COUNTS and concept not in stated and FF.value_class(record, entry, resolved) == FF.SHARES:
                value = entry.get("value")
                if isinstance(value, (int, float)) and value > 0:
                    stated[concept] = float(value)
    for concept in FD.SHARE_COUNTS:
        if concept in stated:
            return stated[concept], concept
    return None, None


def pct(n, d):
    return round(100.0 * n / d, 3) if d else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args(argv)
    cutoff = U.parse_day(GAPS.A.CUTOFF)
    by_ticker = defaultdict(list)
    for record in GAPS.iter_raw(args.workspace):
        available, accepted = U.parse_day(record.get("availableFrom")), U.parse_day(record.get("acceptedDate"))
        visible = max(available, accepted) if available and accepted else available
        if visible and visible < cutoff:
            by_ticker[record["ticker"]].append(record)
    reader = D.SealedReader(ROOT)
    events = MF.load_events(reader, reader.manifest())
    years = defaultdict(Counter)
    concept_counts, changes = Counter(), []
    for ticker, records in by_ticker.items():
        index = FD.index_filings(records)
        splits = M.split_dates(events.get(ticker, []))
        stated = {key: stated_share_count(filing) for key, filing in index.items()}
        for (year, stage), filing in index.items():
            value, concept = stated[(year, stage)]
            y = str(U.parse_day(filing["availableFrom"]).year)
            years[y]["filings"] += 1
            if value is None:
                continue
            years[y]["withShareCount"] += 1
            concept_counts[BASIS_OF[concept]] += 1
            years[y]["periodEndBasis"] += concept in PERIOD_END
            prior = index.get((year - 1, stage))
            prior_value, prior_concept = stated.get((year - 1, stage), (None, None))
            if prior is None or prior_value is None:
                continue
            years[y]["withPriorYearSameStageCount"] += 1
            same = BASIS_OF[concept] == BASIS_OF[prior_concept]
            years[y]["sameBasisPair"] += same
            a, b = np.datetime64(prior["availableFrom"][:10], "D"), np.datetime64(filing["availableFrom"][:10], "D")
            crossed = any(a < s <= b for s in splits)
            years[y]["splitBetweenPair"] += crossed
            if same and not crossed:
                years[y]["sameBasisNoSplitPair"] += 1
                years[y]["periodEndSameBasisNoSplitPair"] += concept in PERIOD_END and prior_concept in PERIOD_END
                change = value / prior_value - 1.0
                changes.append(change)
                years[y]["jumpOverThreshold"] += abs(change) > JUMP
    total = Counter()
    for c in years.values():
        total.update(c)
    q = lambda p: round(float(np.quantile(changes, p)), 4) if changes else None      # noqa: E731
    report = {
        "id": "us-capital-allocation-dilution-evidence-v1", "evidenceClass": "OUTCOME_BLIND_SOURCE_EVIDENCE", "readsReturns": False,
        "readsLabels": False, "fitsModels": False, "newAcquisition": False, "producesADilutionFeature": False,
        "inputs": {"fundamentalsCommit": GAPS.A.FUNDAMENTALS_COMMIT, "cutoff": GAPS.A.CUTOFF, "tickers": len(by_ticker), "filings": total["filings"]},
        "shareCountBasis": dict(concept_counts), "overall": {
            "filingsWithAnyShareCountPct": pct(total["withShareCount"], total["filings"]),
            "periodEndBasisPct": pct(total["periodEndBasis"], total["filings"]),
            "pairsWithPriorYearSameStagePct": pct(total["withPriorYearSameStageCount"], total["filings"]),
            "sameBasisPairsPct": pct(total["sameBasisPair"], total["filings"]),
            "sameBasisNoSplitPairsPct": pct(total["sameBasisNoSplitPair"], total["filings"]),
            "periodEndSameBasisNoSplitPairsPct": pct(total["periodEndSameBasisNoSplitPair"], total["filings"]),
            "splitBetweenPair": total["splitBetweenPair"], "jumpsOver40PctWithoutASealedSplit": total["jumpOverThreshold"]},
        "byFilingYearPct": {y: {"filings": c["filings"], "anyShareCount": pct(c["withShareCount"], c["filings"]),
                                "periodEndBasis": pct(c["periodEndBasis"], c["filings"]),
                                "sameBasisNoSplitPair": pct(c["sameBasisNoSplitPair"], c["filings"]),
                                "periodEndSameBasisNoSplitPair": pct(c["periodEndSameBasisNoSplitPair"], c["filings"])} for y, c in sorted(years.items())},
        "sameBasisNoSplitChangeDistribution": {"n": len(changes), "p01": q(.01), "p10": q(.1), "median": q(.5), "p90": q(.9), "p99": q(.99)},
        "reading": ["A same-basis, no-split pair is the most a NEW definition could build a dilution proxy on from this store.",
                    "Weighted-average counts move with issuance, buybacks, timing within the period and unit/class changes; none of that is separable here.",
                    "The period-end, share-class and split-adjusted count the registered hypothesis requires is the SEC XBRL instance fact, which is BLOCKED here."],
        "status": {"periodEndVerifiedDilution": "BLOCKED", "weightedAverageProxy": "UNVERIFIED_BASIS_NOT_A_DILUTION_MEASURE"},
    }
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["overall"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
