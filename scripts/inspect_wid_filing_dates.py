"""Outcome-free WID filing-date/evidence inventory; default opens no sources."""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import winner_inflection_admission as A  # noqa: E402
from pipeline import winner_inflection_filing_review as F  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402


def identity_census(spec, memberships, industries, identities, filings):
    """Enumerate the FULL weekly member denominator, without opening prices.

    These are provisional issuer metadata checks, never security/share-class
    proof, licensed source admission, total-return eligibility or outcomes.
    """
    identity = {r["symbol"]: r for r in identities}
    if len(identity) != len(identities):
        raise ValueError("DUPLICATE_SOURCE_IDENTITY_SYMBOL")
    grouped = defaultdict(list)
    for row in filings:
        day = max(F.reviewed_public_day(row[k]) for k in ("availableFrom", "acceptedDate")).isoformat()
        grouped[row["ticker"]].append((day, F.normalized_cik(row.get("cik"))))
    prefixes = {}
    for ticker, rows in grouped.items():
        rows.sort(key=lambda r: r[0])
        seen, sets = set(), [frozenset()]
        for _, cik in rows:
            seen.add(cik)
            sets.append(frozenset(seen))
        prefixes[ticker] = ([r[0] for r in rows], sets)
    end = (date.fromisoformat(spec["signalEnd"]) + timedelta(days=15)).isoformat()
    sessions = RC.sessions(spec["inputStart"], end, "US")
    grid = sessions.to_series().groupby(sessions.to_period("W")).max()
    counts, by_date, digest = Counter(), [], hashlib.sha256()
    unknown_dates = []
    for stamp in grid:
        day = str(stamp.date())
        if day > spec["signalEnd"]:
            continue
        member, sector = memberships.on(day), industries.on(day)
        if member is None:
            unknown_dates.append(day)
            by_date.append({"date": day, "memberDates": None, "reason": "NO_PRIOR_MEMBERSHIP"})
            continue
        members = member["members"]
        if len(members) != len(set(members)):
            raise ValueError("DUPLICATE_DATED_MEMBER")
        reasons = Counter()
        for ticker in sorted(members):
            meta = identity.get(ticker, {})
            category = meta.get("sp500IdentityCategory")
            row = ((sector or {}).get("rows") or {}).get(ticker, {})
            cik, own = F.normalized_cik(row.get("cik")), F.normalized_cik(meta.get("cik"))
            days, sets = prefixes.get(ticker, ([], [frozenset()]))
            visible = sets[bisect_left(days, day)]
            group = row.get("sector")
            reason = (
                "CONDITIONAL_SCOPE_EXCLUDED:" + str(category) if category not in spec["acceptedIdentityCategories"] else
                "DATED_ISSUER_CIK_UNRESOLVED" if cik is None else
                "OWN_PANEL_ISSUER_CIK_UNRESOLVED" if own is None else
                "NO_STRICTLY_VISIBLE_FILING" if not visible else
                "VISIBLE_FILING_CIK_UNRESOLVED" if None in visible else
                "ISSUER_CIK_DISAGREEMENT" if visible != {cik} or own != cik else
                "INDUSTRY_UNRESOLVED_OR_EXCLUDED" if group not in spec["allowedIndustries"] or group in spec["excludedIndustries"] else
                "PROVISIONAL_ISSUER_ONLY_NOT_SECURITY_ADMISSION")
            reasons[reason] += 1
            digest.update(json.dumps([day, ticker, reason], separators=(",", ":")).encode() + b"\n")
        counts.update(reasons)
        by_date.append({"date": day, "memberDates": len(members), "firstMetadataReason": dict(sorted(reasons.items()))})
    return {"enumeratedMemberDates": sum(counts.values()), "weeklyDates": len(by_date),
            "unknownUniverseDates": unknown_dates, "firstMetadataReason": dict(sorted(counts.items())),
            "enumeratedRowSha256": digest.hexdigest(), "byDate": by_date,
            "rights": "UNRESOLVED", "securityShareClassVerified": None,
            "comparableTotalReturnVerified": None, "admittedMemberDates": 0,
            "limitation": "Zero admitted is the closed review gate, not zero economically eligible names. Unverified source quantities are null. All scoped-out/terminal/reused names remain in the enumerated denominator."}


def inspect(root):
    root = Path(root)
    spec = json.loads((root / A.SPEC_PATH).read_bytes())
    if spec["sourceCommit"] != S.SOURCE_COMMIT or spec["metadataCommit"] != S.CODE_BASE:
        raise ValueError("SOURCE_COMMIT_OUTSIDE_FIXED_REUSE_SCOPE")
    source = S.Sources(root)
    rows, qualified, source_withheld = [], [], []
    for year in range(2011, spec["sourceWindow"]["lastFilingFiscalYear"] + 1):
        records = source.rows(f"ledger/fundamentals/us/finnhub-{year}.jsonl.gz")
        rows.extend(records)
        kept, refused = F.reviewed_filing_shard(records, year)
        qualified.extend(kept)
        source_withheld.extend(refused)
    accepted, withheld = F.reviewed_filings(rows)
    identities = list(csv.DictReader(io.StringIO(gzip.decompress(source.local(S.US_IDENTITY)).decode())))
    census = identity_census(spec, S.RAF.MembershipSnapshots(source.json(S.MEMBERS)["snapshots"]),
                             S.RAF.MembershipSnapshots(source.json(S.SECTORS)["snapshots"]), identities, qualified)
    review_dir = root / "docs/winner-inflection-discovery/admission-review-v2"
    review = json.loads((review_dir / "review.json").read_bytes())
    citations = [citation for claim in review["claims"].values() for citation in claim.get("citations", [])]
    report_sha = A.file_sha(review_dir / "source-audit.json")
    return {"schema": "WID_FULL_FILING_DATE_AND_EVIDENCE_AUDIT_V3",
        "status": "BLOCKED", "sourceCommit": S.SOURCE_COMMIT, "metadataCommit": S.CODE_BASE,
        "inspectorSha256": A.file_sha(Path(__file__)),
        "executionModuleSha256": A.file_sha(root / "pipeline/winner_inflection_execution.py"),
        "widAdapterSha256": A.file_sha(root / "pipeline/winner_inflection_filing_review.py"),
        "filings": {"records": len(rows), "tickers": len({r["ticker"] for r in rows}),
                    "bothDatesFullyValid": len(accepted), "withheld": withheld,
                    "differentReviewedDays": sum(F.reviewed_public_day(r["availableFrom"]) != F.reviewed_public_day(r["acceptedDate"]) for r in accepted)},
        "fiscalShardReview": {"retained": len(qualified), "retainedTickers": len({r["ticker"] for r in qualified}),
                              "withheld": source_withheld, "rawRecordsMutated": False,
                              "fiscalYearInferredOrRepaired": False},
        "admissionFunnel": census,
        "v2Evidence": {"committedReportSha256": report_sha,
                       "allCitationsPinCommittedReport": bool(citations) and all(c["sha256"] == report_sha for c in citations),
                       "locallyByteVerified": bool(citations) and all(A.citation_verified(c) for c in citations),
                       "portableFromGitAlone": False,
                       "limitation": "Absolute external evidence references need explicit authorized materialization. Local availability never implies clean-environment availability; admission remains BLOCKED without exact bytes."},
        "sourceReceipts": source.receipts, "quoteReads": 0, "outcomeReads": 0,
        "modelFits": 0, "sourceMaterialization": False, "executionAuthorization": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    report = inspect(ROOT) if args.inspect else {"status": "PLAN_ONLY", "sourceReads": 0}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
