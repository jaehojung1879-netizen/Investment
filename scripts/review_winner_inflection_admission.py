"""Outcome-free Codex technical source review, with explicit unresolved rights/basis.

Only pinned manifest, lineage, membership, identity metadata and filing records
are read. No quote panel, H126/H252 label, model or formal executor is called.
"""

from __future__ import annotations
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import winner_inflection_admission as A  # noqa: E402
from pipeline import winner_inflection_execution as X  # noqa: E402
from pipeline import us_cash_profitability as CP  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402

OUT = ROOT / "docs/winner-inflection-discovery/admission-review-v2"
ACCEPTED = ("membershipIndustry", "size", "vintage", "terminal")


def audit():
    source = S.Sources(ROOT)
    spec = json.loads((ROOT / A.SPEC_PATH).read_bytes())
    records = [r for y in range(2011, 2022) for r in source.rows(f"ledger/fundamentals/us/finnhub-{y}.jsonl.gz")]
    good, withheld = X.reviewed_filings(records)
    members = source.json(S.MEMBERS)
    sectors = source.json(S.SECTORS)
    identities = list(csv.DictReader(io.StringIO(gzip.decompress(source.local(S.US_IDENTITY)).decode())))
    assert len({r["symbol"] for r in identities}) == len(identities)
    dates = [r["date"] for r in members["snapshots"]]
    assert dates == sorted(dates)
    # Data contains retrospective community dates, not a contemporaneously captured universe.
    snapshots = S.RAF.MembershipSnapshots(members["snapshots"])
    for day in sorted(set(dates)):
        picked = snapshots.on(day)
        assert picked is None or picked["date"] < day
    taxonomy = Counter(
        row.get("sector") or "MISSING" for snap in sectors["snapshots"] for row in snap.get("rows", {}).values()
    )
    outside = {k: v for k, v in taxonomy.items() if k not in spec["allowedIndustries"]}
    # This audits the declared ranking proxy, not actual market capitalisation.
    shares = Counter()
    for r in good:
        value = X.FD.share_count(r)
        shares["positiveCountPresent" if value and value > 0 else "shareCountMissingOrInvalid"] += 1
    asserts = {
        "splitWithholdsSize": CP.market_cap_proxy(100, 10.0, "2020-01-01", "2020-02-01", ["2020-01-15"])[0] is None,
        "noSplitProxy": CP.market_cap_proxy(100, 10.0, "2020-01-01", "2020-02-01", [])[0] == 1000.0,
        "missingSharesAbstain": CP.market_cap_proxy(None, 10.0, "2020-01-01", "2020-02-01", [])[0] is None,
    }
    assert all(asserts.values())
    report = {
        "review": "WID_CONDITIONAL_TECHNICAL_SOURCE_REVIEW_V2",
        "sourceCommit": S.SOURCE_COMMIT,
        "metadataCommit": S.CODE_BASE,
        "reviewCodeSha256": A.file_sha(Path(__file__)),
        "specSha256": A.IF.digest(spec),
        "reviewer": "Codex technical review; not owner execution authorization",
        "filingInventory": {
            "records": len(records),
            "tickers": len({r["ticker"] for r in records}),
            "bothDatesValid": len(good),
            "withheld": withheld,
            "shares": dict(shares),
        },
        "membershipIndustry": {
            "snapshots": len(dates),
            "first": dates[0],
            "last": dates[-1],
            "duplicateDates": len(dates) - len(set(dates)),
            "strictPriorBoundaryVerified": True,
            "labelsOutsideAllowedTaxonomy": outside,
            "meaning": "Retrospective public reconstruction only. Unknown/finer labels are excluded by the fixed allowlist; no official historical index-membership or PIT sector certification.",
        },
        "identity": {
            "metadataRows": len(identities),
            "categories": dict(Counter(r["sp500IdentityCategory"] for r in identities)),
            "status": "UNRESOLVED_PRICE_ISSUER_AND_SHARE_CLASS_PROVENANCE",
        },
        "size": {
            "checks": asserts,
            "acceptedMeaning": "Filed weighted-average shares times recovered as-traded quote is a ranking PROXY only; split gaps abstain. Price/action truth remains blocked by returnBasis.",
        },
        "vintage": {
            "acceptedMeaning": "Retrospective 2026 collection; strict max(publication,acceptance)<signal and 180-day age gate. No claim of contemporaneous observations or unamended vintage."
        },
        "terminal": {
            "acceptedMeaning": "Accept only the fixed fail-closed policy: missing/late/stock-swap consideration remains unresolved; verified cash needs exact identity/currency/share basis. No terminal economic values certified by this review."
        },
        "rights": {
            "status": "UNRESOLVED",
            "reason": "Possession, code license or public access is not a vendor retention/reuse grant; no new vendor query or Tiingo retention workaround.",
        },
        "returnBasis": {
            "status": "UNRESOLVED",
            "reason": "Unit/action lineage and complete stock/SPY distribution reconciliation not certified by metadata or synthetic formula tests.",
        },
        "acceptedClaims": list(ACCEPTED),
        "remainingClaims": ["rights", "identity", "returnBasis"],
        "sourceReceipts": source.receipts,
        "codeHashes": {p: A.file_sha(ROOT / p) for p in A.CLOSURE},
        "newRealLabels": 0,
        "modelFits": 0,
        "executionAuthorization": False,
        "sourcePricesRead": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(report, ensure_ascii=False, indent=2).encode() + b"\n"
    (OUT / "source-audit.json").write_bytes(raw)
    review = json.loads((ROOT / A.REVIEW_PATH).read_bytes())
    citation = {
        "reference": str(
            A.EVIDENCE_ROOT / ("wid-codex-technical-review-v2-" + hashlib.sha256(raw).hexdigest() + ".json")
        ),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    for claim in ACCEPTED:
        review["claims"][claim].update(
            status="REVIEWED_ACCEPTED",
            reviewer=report["reviewer"],
            citations=[citation],
            reviewedScope=report[claim].get("acceptedMeaning", report[claim].get("meaning")),
            remaining="Full execution still requires owner approval and unresolved claims; no broad empirical certification.",
        )
    (OUT / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    return report, raw, review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--materialize-review",
        action="store_true",
        help="Copy only this technical evidence JSON to the existing admission evidence directory; no approval/attempt.",
    )
    args = parser.parse_args()
    report, raw, review = audit()
    if args.materialize_review:
        A.EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
        dest = A.EVIDENCE_ROOT / ("wid-codex-technical-review-v2-" + hashlib.sha256(raw).hexdigest() + ".json")
        if dest.exists() and dest.read_bytes() != raw:
            raise ValueError("REVIEW_EVIDENCE_ALREADY_EXISTS_WITH_DIFFERENT_BYTES")
        dest.write_bytes(raw)
    result = A.preflight(ROOT, json.loads((ROOT / A.SPEC_PATH).read_bytes()), review)
    (OUT / "preflight.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {"accepted": report["acceptedClaims"], "remaining": report["remainingClaims"], "preflight": result},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
