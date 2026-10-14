"""US factor reboot: what each of the 63 inventoried characteristics needs before research can resume on a repaired US panel.

    python scripts/audit_us_factor_integration_readiness.py --workspace <dir> [--extract]

Outcome-blind and read-only. It reads:
* the SANITIZED departed-security evidence of PR #241 (head 1e016bd9), from git objects pinned by commit and blob id: the recovery
  report `docs/us-readiness/us-departed-public-price-recovery-v1.json` and the redistribution audit. That head carries no third-party
  price payload, and neither does anything read here: no raw archive, no observation panel, no superseded commit. It never writes,
  merges or re-downloads anything of #241, and nothing here admits a candidate price;
* the pinned Finnhub filings (signal-history 704d7db6, blob-verified by the Phase 3 reader) to count, per departed identifier, whether a
  filing became visible inside its membership window and how many filing CIKs a ticker carries;
* the committed factor inventory (`docs/us-readiness/us-factor-inventory-v1.json`).
It reads no forward price, return, label, model or portfolio: price use is the EXISTENCE of a positive close on a date and which
publisher bases #241 counted for an identifier, both as recorded in its aggregate report.
Writes `docs/us-readiness/us-factor-integration-readiness-v1.json`.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/us-readiness/us-factor-integration-readiness-v1.json"
INVENTORY = ROOT / "docs/us-readiness/us-factor-inventory-v1.json"

PR241 = {
    "pullRequest": 241, "commit": "1e016bd9a4ff746a9b69958624182c6287301f51", "state": "OPEN_DRAFT_NOT_MERGED",
    "payload": "SANITIZED_NO_PRICE_PAYLOAD (raw archive and observation panel are not in this head)",
    "report": {"path": "docs/us-readiness/us-departed-public-price-recovery-v1.json", "gitBlob": "2b29aed4a80693365da7cfbb2537d6730c5d9f34"},
    "redistributionAudit": {"path": "docs/us-readiness/us-departed-price-redistribution-audit-v1.json", "gitBlob": "d8d7cc95f25b27a660df9e5836c185a4ad1fbbe3"},
}

REQUIREMENTS = {
    "HISTORICAL_SECURITY_IDENTITY": "the member's issuer and share class tied to every price and filing used, across renames and ticker reuse",
    "SPLIT_DIVIDEND_LINEAGE": "dated split and distribution events with a declared price basis; no splicing of differently adjusted series",
    "TERMINAL_CONSIDERATION": "what a holder received when trading ended (cash, stock, nothing), cited; never zero or last price by default",
    "DATED_MEMBERSHIP": "which names were S&P 500 members on the signal date, from the latest snapshot strictly before it",
    "PIT_FUNDAMENTALS": "filings visible strictly after max(availableFrom, acceptedDate), with the filing CIK matching the member issuer",
}

# Every forward-return reading (any factor, any horizon) needs these, whatever the feature needs.
LABEL_REQUIREMENTS = ["HISTORICAL_SECURITY_IDENTITY", "SPLIT_DIVIDEND_LINEAGE", "TERMINAL_CONSIDERATION", "DATED_MEMBERSHIP"]

# Feature-side requirement groups, fixed by what each computation reads (code paths in the inventory), not by any result.
GROUPS = {
    "RETURN_PATH_PRICE": {
        "needs": ["HISTORICAL_SECURITY_IDENTITY", "SPLIT_DIVIDEND_LINEAGE", "DATED_MEMBERSHIP"],
        "why": "momentum/risk read a continuous total-return-consistent close over >= 273 sessions; one basis per series, no splice",
        "ids": ["D01", "D02", "D03", "D04", "D05", "D06", "E01", "E02", "E03", "E04"]},
    "AS_TRADED_PRICE_OR_VOLUME": {
        "needs": ["HISTORICAL_SECURITY_IDENTITY", "SPLIT_DIVIDEND_LINEAGE", "DATED_MEMBERSHIP"],
        "why": "traded value, volume shock and dividend yield need the as-traded price/volume, rebuilt only from explicit events",
        "ids": ["E05", "H06", "F04"]},
    "AS_TRADED_PRICE_AND_FUNDAMENTALS": {
        "needs": ["HISTORICAL_SECURITY_IDENTITY", "SPLIT_DIVIDEND_LINEAGE", "DATED_MEMBERSHIP", "PIT_FUNDAMENTALS"],
        "why": "price-denominated value and size divide a filing figure by the as-traded close on the signal date",
        "ids": ["A01", "A02", "A03", "A06", "A07", "A08", "E06", "F06"]},
    "PIT_ACCOUNTING": {
        "needs": ["HISTORICAL_SECURITY_IDENTITY", "DATED_MEMBERSHIP", "PIT_FUNDAMENTALS"],
        "why": "dollar amounts from one filing chain; price only for eligibility (a panel must exist on the signal date)",
        "ids": ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09", "B12", "B13", "C01", "C02", "C03", "C04", "C05", "C06",
                "C07", "E07", "F01", "F02", "F03", "F07", "F08", "F09", "G05"]},
    "SHARE_COUNT_CHANGE": {
        "needs": ["HISTORICAL_SECURITY_IDENTITY", "SPLIT_DIVIDEND_LINEAGE", "DATED_MEMBERSHIP", "PIT_FUNDAMENTALS"],
        "why": "a share-count change is only meaningful after splits are neutralised, and needs period-end counts (SEC blocked)",
        "ids": ["F05"]},
    "MEMBERSHIP_EVENT": {
        "needs": ["HISTORICAL_SECURITY_IDENTITY", "DATED_MEMBERSHIP"],
        "why": "an index event needs its effective date, which snapshots cannot give",
        "ids": ["G06"]},
    "SOURCE_BLOCKED_OR_NOT_DERIVED": {
        "needs": [],
        "why": "no reachable source or derivation; the panel repair changes nothing for these",
        "ids": ["A04", "A05", "A09", "B10", "B11", "G01", "G02", "G03", "G04", "H01", "H02", "H03", "H04", "H05"]},
}


def git_bytes(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", "%s:%s" % (commit, path)], cwd=ROOT)


def blob_id(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load_pr241():
    out = {}
    for key in ("report", "redistributionAudit"):
        raw = git_bytes(PR241["commit"], PR241[key]["path"])
        if blob_id(raw) != PR241[key]["gitBlob"]:
            raise ValueError("PR241_%s_BLOB_MISMATCH" % key.upper())
        out[key] = json.loads(raw)
    return out["report"], out["redistributionAudit"]


def basis_classes(report: dict) -> dict:
    """Per identifier with qualified coverage, which publisher bases #241 counted. Aggregate report only; no price is read.

    Session-level basis counts need the observation panel, which is not public in the sanitized head, so they are UNMEASURED here."""
    classes = Counter()
    for item in report["inventory"]:
        if item["qualifiedPriceCoverage"] == "NONE":
            continue
        counted = {s["source"] for s in item["candidateSources"] if s["countedInQualifiedCoverage"]}
        if counted & {"D", "F"}:
            classes["HAS_ORIGINAL_OHLC_WITH_SEPARATE_ADJ_CLOSE_D_OR_F"] += 1
        elif "A" in counted:
            classes["BACK_ADJUSTED_ONLY_A_EVENTS_STRIPPED"] += 1
        else:
            classes["ROUNDED_CLOSE_ONLY_E_NO_VOLUME"] += 1
    total = sum(classes.values())
    return {"identifiers": total, "byBasis": {k: {"identifiers": v, "pct": round(100.0 * v / total, 2)} for k, v in sorted(classes.items())},
            "sessionLevelBasisCounts": "UNMEASURED: needs the observation panel, which the sanitized #241 head does not publish",
            "sourceBases": {"A": "BACK_ADJUSTED_OHLCV_WIKI_FIRST_YAHOO_FALLBACK", "D": "YAHOO_OHLC_WITH_SEPARATE_ADJ_CLOSE",
                            "E": "YFINANCE_CLOSE_ROUNDED_2DP_UNPINNED_ADJUSTMENT_DEFAULT", "F": "YAHOO_OHLC_WITH_SEPARATE_ADJ_CLOSE"},
            "meaning": ("an identifier is classed by the best basis #241 counted for it; a D/F identifier may still have A-only sessions, and D/F Close "
                        "is a vendor series whose split basis must still be verified")}


def fundamentals_link(inventory_rows: list[dict], workspace: Path) -> dict:
    spec = importlib.util.spec_from_file_location("phase3_audit", ROOT / "scripts/audit_us_alpha_phase3_readiness.py")
    p3 = importlib.util.module_from_spec(spec)
    sys.modules["phase3_audit"] = p3
    spec.loader.exec_module(p3)
    raw = p3.raw_records(workspace, p3.A.FUNDAMENTALS_COMMIT)          # blob-verified against the pinned extraction
    status, cik_counts, agreement = Counter(), Counter(), Counter()
    for item in inventory_rows:
        ticker = item["auditIdentifier"]
        filings = raw.get(ticker) or raw.get(ticker.replace("-", "."))
        if not filings:
            status["NO_FILINGS_IN_PINNED_STORE"] += 1
            continue
        window = item["expectedPricingWindow"]
        visible = [f for f in filings if window["first"] and window["first"] <= str(f.get("availableFrom") or "")[:10] <= window["last"]]
        status["FILING_VISIBLE_DURING_MEMBERSHIP" if visible else "FILINGS_ONLY_OUTSIDE_MEMBERSHIP"] += 1
        ciks = {str(f.get("cik") or "").lstrip("0") for f in filings} - {""}
        cik_counts["ONE_FILING_CIK" if len(ciks) == 1 else "MULTIPLE_FILING_CIKS"] += 1
        member = {c.lstrip("0") for c in item["historicalCiksWhereReported"]}
        agreement["NO_MEMBER_CIK_TO_COMPARE" if not member else "MEMBER_CIK_MATCHES_A_FILING_CIK" if member & ciks else "MEMBER_CIK_NOT_IN_FILINGS"] += 1
    return {"identifiers": len(inventory_rows), "filingVisibility": dict(sorted(status.items())),
            "filingCikMultiplicity": dict(sorted(cik_counts.items())), "memberCikAgreement": dict(sorted(agreement.items())),
            "source": "signal-history 704d7db6 ledger/fundamentals/us (Finnhub), blob-verified",
            "meaning": ("filings exist for most departed members because collection was keyed by ticker; they were unused only because no "
                        "price panel existed. Member CIK is known only from 2023-04-13 snapshots, so most links rest on ticker plus dates")}


def factor_matrix(inventory: dict) -> list[dict]:
    group_of = {fid: g for g, spec in GROUPS.items() for fid in spec["ids"]}
    ids = [f["id"] for f in inventory["factors"]]
    missing = sorted(set(ids) - set(group_of))
    extra = sorted(set(group_of) - set(ids))
    if missing or extra:
        raise ValueError("GROUP_MAP_DOES_NOT_COVER_INVENTORY: missing=%s extra=%s" % (missing, extra))
    out = []
    for f in inventory["factors"]:
        g = group_of[f["id"]]
        needs = GROUPS[g]["needs"]
        out.append({"id": f["id"], "name": f["name"], "family": f["family"], "group": g,
                    "featureRequires": needs, "labelRequires": LABEL_REQUIREMENTS if needs else [],
                    "historicalAvailabilityBeforeRepair": f["availability"]["historical"],
                    "researchResumable": "NO_UNTIL_DATASET_ADMISSION" if needs else "NO_SOURCE_OR_DERIVATION"})
    return out


def requirement_status(pr241: dict, basis: dict, fundamentals: dict) -> dict:
    rows = pr241["inventory"]
    covered = [r for r in rows if r["qualifiedPriceCoverage"] != "NONE"]
    return {
        "HISTORICAL_SECURITY_IDENTITY": {
            "state": "CANDIDATE_NAME_CORROBORATED_NOT_PERMANENT_ID",
            "measured": {"qualifiedCoverage": pr241["qualifiedPriceCoverageCounts"], "identityHolds": pr241["identityHoldIdentifiers"],
                         "recycledSymbolsStillWithoutCoverage": pr241["recycledSymbolIdentitiesStillWithoutQualifiedCoverage"],
                         "sealedCategoryCounts": dict(Counter(r["sealedIdentityCategory"] for r in rows))},
            "blocksAdmission": True},
        "SPLIT_DIVIDEND_LINEAGE": {
            "state": "UNRESOLVED_FOR_ALL_212",
            "measured": {"corporateActionUnresolvedIdentifiers": pr241["corporateActionUnresolvedIdentifiers"], "coveredIdentifiersByBasis": basis},
            "consequence": ("back-adjusted-only and rounded-close-only series cannot yield an as-traded price, so price-denominated value, traded "
                            "value and volume features stay missing for those identifiers even after identity is verified"),
            "blocksAdmission": True},
        "TERMINAL_CONSIDERATION": {
            "state": "UNRESOLVED_FOR_ALL_212",
            "measured": {"terminalConsiderationUnresolvedIdentifiers": pr241["terminalConsiderationUnresolvedIdentifiers"],
                         "identifiersWithQualifiedCoverage": len(covered),
                         "identifiersWithEveryMemberSessionObserved": sum(1 for r in rows if r["qualifiedPriceCoverage"] == "FULL"),
                         "observationsReachLastMembershipSession": "UNMEASURED_FROM_PUBLIC_EVIDENCE: needs per-session dates, which the sanitized head does not publish",
                         "qualifiedObservationWindow": [pr241["qualifiedMembershipFirstDate"], pr241["qualifiedMembershipLastDate"]],
                         "afterRepairImprovement2024to2026": "0 (no candidate observation after 2023-10-10)"},
            "consequence": "a forward window that runs past a name's last candidate observation has no resolved endpoint; it is UNRESOLVED, never zero",
            "blocksAdmission": True},
        "DATED_MEMBERSHIP": {
            "state": "SNAPSHOT_OBSERVED_NOT_EFFECTIVE_DATES",
            "measured": {"snapshots": pr241["membershipLimitation"],
                         "snapshotAgeOnWeeklyDates": json.loads((ROOT / "docs/us-readiness/us-factor-unique-variation-v1.json").read_text())["membershipSnapshotAge"]},
            "consequence": "usable for eligibility with a disclosed lag; never for index-event timing",
            "blocksAdmission": False},
        "PIT_FUNDAMENTALS": {
            "state": "PRESENT_FOR_MOST_DEPARTED_TICKERS_ISSUER_LINK_UNVERIFIED",
            "measured": fundamentals,
            "consequence": "accounting families become computable for departed names once a filing CIK is tied to the member issuer",
            "blocksAdmission": True},
    }


def build(workspace: Path) -> dict:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    pr241, redistribution = load_pr241()
    basis = basis_classes(pr241)
    fundamentals = fundamentals_link(pr241["inventory"], workspace)
    annual = {y: {"beforePct": v["beforeMissingPricePanelsPct"], "candidateAfterPct": v["afterCandidateMissingObservationsPct"]}
              for y, v in pr241["annualMissingness"].items()}
    return {
        "id": "us-factor-integration-readiness-v1", "evidenceClass": "OUTCOME_BLIND_INTEGRATION_READINESS",
        "readsReturns": False, "readsLabels": False, "forwardPricesRead": False, "fitsModels": False, "authorizes": "NOTHING",
        "candidatePricesAdmitted": False, "pr241FilesModified": False,
        "pr241Evidence": {**PR241, "coverageMeaning": pr241["coverageMeaning"],
                          "headline": {"recoveredMembershipSessions": pr241["qualifiedCoveredMembershipSessions"],
                                       "missingMembershipSessionsBefore": pr241["qualifiedCoveredMembershipSessions"] + sum(
                                           r["missingSessions"] for r in pr241["inventory"]),
                                       "readAs": ("72.90% = candidate positive-close OBSERVATIONS on missing member sessions. It is not validated total-return "
                                                  "coverage, not identity verification, not terminal economics, and not the end of survivorship bias")},
                          "annualWeeklyMemberDateMissingness": annual, "studyReady": pr241["studyReady"],
                          "licensing": pr241["licensing"], "redistributionAudit": {"reproducibility": redistribution["reproducibility"],
                                                                                   "aggregateFindings": redistribution["aggregateFindings"]}},
        "requirements": REQUIREMENTS, "labelRequirements": LABEL_REQUIREMENTS,
        "requirementStatus": requirement_status(pr241, basis, fundamentals),
        "groups": {g: {"needs": s["needs"], "why": s["why"], "factorIds": s["ids"]} for g, s in GROUPS.items()},
        "factorMatrix": factor_matrix(inventory),
        "inputs": {"inventory": {"path": str(INVENTORY.relative_to(ROOT)), "sha256": hashlib.sha256(INVENTORY.read_bytes()).hexdigest()},
                   "fundamentalsCommit": "704d7db6d5b00def771aba5d2665d0846d6bc776"},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--extract", action="store_true")
    args = parser.parse_args(argv)
    if args.extract:
        spec = importlib.util.spec_from_file_location("coverage_audit", ROOT / "scripts/audit_us_capital_allocation_coverage.py")
        cov = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cov)
        cov.extract(args.workspace, cov.FUNDAMENTALS_COMMIT)
    report = build(args.workspace)
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
