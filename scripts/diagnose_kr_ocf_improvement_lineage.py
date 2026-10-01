"""Outcome-blind lineage diagnosis of `ocfImprovementToAssets` coverage on the pinned accounting snapshot.

Reads ONLY the pinned PIT universe blobs and the pinned accounting shards (by git blob, identity-checked) and the
frozen feature's own accounting functions. It never opens prices, KRX values, labels, targets or models, computes no
return, and reports presence/absence reason buckets and filing chronology only. It mirrors
`kr_value_quality_catalyst.accounting_values` step by step and reproduces the formal gate's observed count.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import dart_derive as DD  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import kr_model_portfolio_execution as X  # noqa: E402
from pipeline import kr_model_raw_snapshot as S  # noqa: E402
from pipeline import kr_value_quality_catalyst as F  # noqa: E402
from pipeline.alpha_opportunity_features import visible_filings  # noqa: E402
from pipeline.regional_alpha_features import MembershipSnapshots  # noqa: E402

OCF, ASSETS = "영업활동현금흐름", "자산총계"


def wildcard_basis(index, keys):
    """COUNTERFACTUAL ONLY: a record with no CFS/OFS label counts as compatible. Never used by the study."""
    rows = [index.get(k) for k in keys]
    return not any(r is None for r in rows) and len({r.get("fsDiv") for r in rows} - {None}) <= 1


def materialize(directory, spec):
    root = Path(directory)
    S.materialize_universe(root, spec)
    pin = spec["inputs"]["accounting"]
    for name, wanted in pin["gitBlobSha1"].items():
        raw = S.git_bytes(ROOT, pin["sourceCommit"], "ledger/fundamentals/kr-candidate-merged/" + name)
        if X.K.git_blob_sha1(raw) != wanted:
            raise ValueError("PINNED_ACCOUNTING_BLOB_CHANGED: " + name)
        S.immutable_bytes(root / "accounting" / name, raw)
    accounting = {}
    for path in X.K.shard_files(root / "accounting"):
        for row in X.K.read_shard(path):
            accounting.setdefault(row["ticker"], []).append(row)
    grouped = {}
    for rel in spec["inputs"]["universeBlobs"]:
        for row in HS.read_jsonl(root / rel):
            grouped.setdefault(row["date"], []).append(row)
    members = MembershipSnapshots([{"date": d, "members": sorted(r["ticker"] for r in sorted(rows, key=lambda r: (r["rank"], r["ticker"]))[:120])}
                                   for d, rows in sorted(grouped.items())])
    return accounting, members


def classify(records, date, compatible):
    """The first prerequisite of ocfImprovementToAssets that fails, in the feature's own order."""
    index = DD.index_filings(visible_filings(records, date, "KR"))
    if not index:
        return "NO_VISIBLE_FILING"
    year, stage = max(index, key=lambda k: (k[0], F.STAGE[k[1]]))
    if not compatible(index, [(year, stage)]):
        return "UNKNOWN_OR_MIXED_STATEMENT_BASIS"

    def ttm(y, s, label):
        keys = [(y, s)] if s == DD.ANNUAL else [(y, s), (y - 1, DD.ANNUAL), (y - 1, s)]
        missing = [k for k in keys if index.get(k) is None]
        if missing:
            where = "CURRENT_PERIOD" if (y, s) in missing else "PRIOR_ANNUAL" if (y - 1, DD.ANNUAL) in missing else "PRIOR_SAME_STAGE"
            return label + "_FILING_ABSENT:" + where
        if not compatible(index, keys):
            return label + "_MIXED_STATEMENT_BASIS"
        return None if DD.trailing_twelve_months(index, y, s, OCF)[0] is not None else label + "_OCF_ACCOUNT_UNAVAILABLE"

    reason = ttm(year, stage, "CURRENT_TTM") or ttm(year - 1, stage, "PRIOR_TTM")
    if reason:
        return reason
    assets = DD.level_amount(index[(year, stage)], ASSETS)
    return "OBSERVED" if assets is not None and np.isfinite(assets) and assets > 1 else "ASSETS_DENOMINATOR_UNAVAILABLE"


def diagnose(directory=None):
    spec = S.frozen_spec()
    with tempfile.TemporaryDirectory() as scratch:
        accounting, members = materialize(directory or scratch, spec)
        schedule = X.M.weekly_dates(spec["walkForward"]["featureStart"], spec["developmentCutoff"])
        buckets, observed_by_date, counterfactual = collections.defaultdict(collections.Counter), collections.Counter(), [0, 0]
        for date in schedule:
            snapshot = members.on(date)
            for ticker in (snapshot["members"] if snapshot else []):
                records = accounting.get(ticker)
                result = classify(records, date, F._compatible) if records else "NO_ACCOUNTING_RECORDS_FOR_TICKER"
                buckets[date[:4]][result] += 1
                observed_by_date[date] += result == "OBSERVED"
                if date[:4] == "2017":
                    counterfactual[1] += 1
                    counterfactual[0] += bool(records) and classify(records, date, wildcard_basis) == "OBSERVED"
        stages = collections.Counter((r["fiscalYear"], r["reportCode"], r["fsDiv"], r["source"]) for rows in accounting.values() for r in rows
                                     if r["fiscalYear"] in (2015, 2016))
    return {"studyId": X.STUDY, "specSha256": S.SPEC_SHA, "outcomeAccess": "NONE", "firstGateYear": spec["gates"]["firstCoverageDate"][:4],
            "floor": spec["gates"]["featureOverrides"]["ocfImprovementToAssets"],
            "bucketsByYear": {y: dict(c) for y, c in sorted(buckets.items())},
            "denominatorByYear": {y: sum(c.values()) for y, c in sorted(buckets.items())},
            "earliestWeeklyDateWithAnyObservation": min((d for d, n in observed_by_date.items() if n), default=None),
            "observedByMonth2017": {m: sum(n for d, n in observed_by_date.items() if d.startswith(m)) for m in sorted({d[:7] for d in observed_by_date if d[:4] == "2017"})},
            "fiscal2015And2016RecordBasis": {"|".join(map(str, k)): v for k, v in sorted(stages.items(), key=str)},
            "counterfactual2017IfUnlabelledBasisWereCompatible_NOT_A_PROPOSAL": {"observed": counterfactual[0], "denominator": counterfactual[1]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = diagnose()
    text = json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False)
    if args.output:
        args.output.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
