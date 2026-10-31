"""Outcome-free census of existing LOCAL raw statements; no remote requests.

Default prints a plan and opens no market data. --inspect opens only the pinned
accounting shards, never prices, outcomes, sealed results, or membership filters.
Output is aggregate metadata/coverage, not vendor payload redistribution.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import timedelta
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from . import features as F

SOURCE = "1bf68f59cffa20239977e2cfaa0f35a07d0ec884"
CUTOFF = "2026-08-31"
ROOT = Path(__file__).resolve().parents[2]


class AccountingSources:
    def __init__(self, root):
        self.root, self.receipts = Path(root), {}

    def rows(self, path):
        if not re.fullmatch(r"ledger/fundamentals/(?:kr-raw/raw|us/finnhub)-20\d{2}\.jsonl\.gz", path):
            raise ValueError("NON_ACCOUNTING_INPUT_REFUSED")
        result = subprocess.run(["git", "cat-file", "blob", SOURCE + ":" + path], cwd=self.root,
                                env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, capture_output=True)
        if result.returncode:
            raise ValueError("PINNED_LOCAL_ACCOUNTING_OBJECT_UNAVAILABLE:" + path)
        raw = result.stdout
        self.receipts[path] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        return [json.loads(line) for line in gzip.decompress(raw).splitlines() if line.strip()]


def kr_census(sources):
    by_year, previous, all_names, paired_names = [], {}, set(), {s: set() for s in F.SIGNALS}
    for year in range(2015, 2026):
        rows = sources.rows(f"ledger/fundamentals/kr-raw/raw-{year}.jsonl.gz")
        annuals = defaultdict(list)
        concepts = Counter()
        for r in rows:
            all_names.add(r["ticker"])
            if r.get("reportCode") == "11011":
                for field in F.CONCEPTS:
                    value, reason = F.amount(r, field)
                    concepts[field] += value is not None and reason is None
                annuals[r["ticker"]].append(r)
        pair_denominator = len(annuals)
        reasons = {s: Counter() for s in F.SIGNALS}
        measurable = Counter()
        earliest = {s: [] for s in F.SIGNALS}
        for ticker, current in annuals.items():
            prior = previous.get(ticker, [])
            if len(current) != 1 or len(prior) != 1:
                for signal in F.SIGNALS:
                    reasons[signal]["MISSING_OR_AMBIGUOUS_PRIOR_OR_CURRENT_ANNUAL"] += 1
                continue
            pair = F.annual_pair(current[0], prior[0], CUTOFF)
            for signal, observation in pair["signals"].items():
                if observation["value"] is None:
                    reasons[signal].update(observation["reasons"])
                else:
                    measurable[signal] += 1
                    paired_names[signal].add(ticker)
                    earliest[signal].append((max(F.day(r["availableFrom"]) for r in (current[0], prior[0]))
                                             + timedelta(days=1)).isoformat())
        by_year.append({"fiscalYear": year, "rawFilings": len(rows), "annualFilings": sum(map(len, annuals.values())),
                        "annualIssuers": pair_denominator, "exactConceptReadableAnnualFilings": dict(concepts),
                        "signals": {s: {"annualIssuerPairDenominator": pair_denominator,
                                        "inputMeasurablePairs": measurable[s],
                                        "coverage": measurable[s] / pair_denominator if pair_denominator else None,
                                        "earliestNextCalendarDayAvailability": min(earliest[s]) if earliest[s] else None,
                                        "missingByReasonNonexclusive": dict(sorted(reasons[s].items()))}
                                    for s in F.SIGNALS}})
        previous = annuals
    return {"years": by_year, "rawDistinctTickers": len(all_names),
            "distinctInputMeasurableTickers": {s: len(v) for s, v in paired_names.items()},
            "sourceAdmittedHistoricalPairs": 0,
            "limits": ["Raw issuer pairs are NOT signal-date PIT Top120 members or valid outcomes.",
                       "Missing reason counts overlap. Denominator includes unobservable annual issuers.",
                       "Rows absent from the raw annual store are outside this filing denominator, not assumed absent disclosures.",
                       "Annual fiscal duration/end dates, amendments, issuer transitions/M&A and actions still need qualification.",
                       "Retrospective September 2026 collection is not an original-vintage certificate."]}


def us_census(sources):
    by_year, names = [], set()
    for year in range(2011, 2026):
        rows = sources.rows(f"ledger/fundamentals/us/finnhub-{year}.jsonl.gz")
        counts = Counter()
        for r in rows:
            names.add(r["ticker"])
            bs = r.get("statements", {}).get("bs", [])
            for name, concept in (("receivables", "us-gaap_AccountsReceivableNetCurrent"),
                                  ("inventory", "us-gaap_InventoryNet")):
                matched = [x for x in bs if x.get("concept") == concept and x.get("unit") == "usd"]
                counts[name] += len(matched) == 1
        by_year.append({"fiscalShard": year, "rawFilings": len(rows), "formCounts": dict(Counter(r.get("form") for r in rows)),
                        "exactConceptPresenceNotQualified": dict(counts)})
    return {"years": by_year, "rawDistinctTickers": len(names), "sourceAdmittedHistoricalPairs": 0,
            "status": "BLOCKED_RIGHTS_IDENTITY_RETURN_BASIS",
            "limits": ["Presence is not permission, statement context validation or current/previous comparable-window coverage.",
                       "No US feature values, security prices, labels, models or WID execution.",
                       "The old inventory's not-collected claim applies to derived fields, not the complete preserved Finnhub response."]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inspect", action="store_true")
    args = p.parse_args(argv)
    if not args.inspect:
        print(json.dumps({"mode": "PLAN_ONLY", "sourceCommit": SOURCE, "historicalOutcomesRead": 0,
                          "permitted": ["KR raw 2015-2025", "US raw 2011-2025"], "status": "NOT_AUTHORIZED_TO_EXECUTE"}))
        return
    sources = AccountingSources(ROOT)
    result = {"study": "stock-working-capital-v1", "status": "INPUT_MEASUREMENT_ONLY",
              "sourceCommit": SOURCE, "inputAvailabilityCutoffExclusive": CUTOFF,
              "historicalOutcomesRead": 0, "modelFits": 0, "regions": {"KR": kr_census(sources), "US": us_census(sources)},
              "sourceReceipts": sources.receipts,
              "codeSha256": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                             for name in ("features.py", "census.py")}}
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
