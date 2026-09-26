"""Assemble the `kr-terminal-action-reconstruction-v2` completeness matrix
from REAL collected evidence on `signal-history` -- never from this
prompt's own claims about what was collected (see the accompanying doc,
section 0).

WHAT THIS DOES. Reads (from a checkout of `signal-history`):
  - `ledger/kr-corporate-actions/fetch-state.json` -- which of the 22
    terminated securities' DART issuer identity actually resolved, and how
    (`kr_corporate_action_events.resolve_historical_dart_identity`'s own
    output, never re-derived here).
  - `ledger/kr-corporate-actions/kr-corporate-actions-disclosures.jsonl.gz`
    -- the real, paginated `list.json` disclosure index (451 rows across
    22/22 tickers as of 2026-09-25; this script never hardcodes that count,
    it reads whatever is actually on the shard).
  - `ledger/kr-corporate-actions/kr-dividend-sections.jsonl.gz` (if
    present) -- real `alotMatter.json` rows, once `collect_kr_dividend_
    sections.py` has been run.

The sealed survivorship audit supplies the 22 security identities. The
normalized book is now populated by `reconstruct_kr_terminal_documents.py`
from all 92 retained original filings plus explicit review selections.
Document access is live and verified; remaining blockers concern evidence
of final terms, exact successor identity, fractional treatment and execution.

DIVIDEND AMOUNT LINEAGE IS NOW REAL, DECODED FROM LIVE-OBSERVED VALUES ONLY
(`kr_dividend_amount_lineage.py`, commit
`dfeb098e26ff71d3b8149199677417a78eda42d6`: 47/47 tickers, 6,150 rows).
Dividend EVENT-DATE lineage stays BLOCKED regardless -- this endpoint has
never stated an ex-date/record date in any row collected, so
`exDateSemanticsResolved` cannot become `READY` from anything this script
reads.

WHAT THIS NEVER DOES. Assigns no `terminationType` from a report name (that
stays a human's job reading real filing content, per `kr_corporate_action_
events`'s own module docstring, or the reviewed real-document reconstruction in
`kr_terminal_action_document_parser.py`); computes no return, IC, or Alpha result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS  # noqa: E402
from pipeline import kr_corporate_action_events as KCA  # noqa: E402
from pipeline import kr_dividend_amount_lineage as DAL  # noqa: E402
from pipeline import kr_terminal_corporate_actions as TCA  # noqa: E402
from pipeline import kr_termination_inventory as INV  # noqa: E402

# reused directly from the v1 builder script, never a second implementation
sys.path.insert(0, str(ROOT / "scripts"))
import build_kr_termination_inventory as V1_BUILD  # noqa: E402


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fetch_state(store: Path) -> dict:
    path = store / "fetch-state.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("tickers", {})


def load_disclosures(store: Path) -> list[dict]:
    path = store / "kr-corporate-actions-disclosures.jsonl.gz"
    if not path.exists():
        return []
    return HS.read_jsonl(path)


def load_dividend_sections(store: Path) -> list[dict]:
    path = store / "kr-dividend-sections.jsonl.gz"
    if not path.exists():
        return []
    return HS.read_jsonl(path)


def build_dart_identity(fetch_state: dict) -> dict[str, dict]:
    """ticker -> {"corpCode", "status", "basis"} from the REAL fetch-state,
    never re-resolved -- the collector already ran the one true resolver."""
    out = {}
    for ticker, entry in fetch_state.items():
        if entry.get("status") == "SUCCESS":
            out[ticker] = {"corpCode": entry.get("corpCode"), "status": "RESOLVED",
                          "basis": entry.get("identityBasis")}
        elif entry.get("status") == "NO_DART_IDENTITY":
            out[ticker] = {"corpCode": None, "status": "UNRESOLVED",
                          "basis": entry.get("basis")}
    return out


def build_terminal_actions(disclosures: list[dict], dart_identity: dict[str, dict],
                           reviewed_book: dict) -> dict[str, dict]:
    """One record per ticker that has EITHER real disclosure evidence OR a
    human-reviewed book entry. A ticker with disclosure rows but no
    human-reviewed content-level classification stays
    `TERMINATION_TYPE_UNRESOLVED` with its raw evidence retained -- report
    NAMES are never promoted to a termination type here (see module
    docstring and `kr_corporate_action_events.classify_disclosure_family`'s
    own docstring for why).
    """
    reviewed_by_security = {row["oldSecurity"]: row for row in reviewed_book.get("actions", [])}
    by_ticker: dict[str, list[dict]] = {}
    for row in disclosures:
        by_ticker.setdefault(row["ticker"], []).append(row)

    out: dict[str, dict] = {}
    for ticker, rows in by_ticker.items():
        if ticker in reviewed_by_security:
            out[ticker] = reviewed_by_security[ticker]
            continue
        chained = KCA.amendment_chain(rows)
        receipts = sorted({r["receiptNo"] for r in rows if r.get("receiptNo")})
        amendment_entries = tuple(
            TCA.build_amendment_entry(
                receipt_number=r["receiptNo"], receipt_date=r["receiptDate"],
                report_name=r.get("reportName"),
                fields_changed=(), supersedes_receipt_number=None)
            for r in chained)
        identity = dart_identity.get(ticker) or {}
        out[ticker] = TCA.build_record(
            old_security=ticker, action_type=TCA.TERMINATION_TYPE_UNRESOLVED,
            old_issuer_corp_code=identity.get("corpCode"),
            sources=tuple(f"DART:{r}" for r in receipts),
            amendment_history=amendment_entries,
            unresolved_fields=("terminationType", "effectiveDate", "terminalConsideration",
                               "successorSecurity", "successorSharesPerOldShare",
                               "lastTradingDateFromFiling"))
    # Every reviewed-book entry not already covered by a disclosure (should
    # not happen once collection ran, but never silently dropped).
    for security, row in reviewed_by_security.items():
        out.setdefault(security, row)
    return out


def run(*, signal_history_root: Path, signal_history_commit: str | None,
       survivorship_audit: Path, reviewed_book_path: Path) -> dict:
    ledger = signal_history_root / "ledger"
    store = ledger / "kr-corporate-actions"

    audit = json.loads(survivorship_audit.read_text(encoding="utf-8"))
    kr_terminations = audit.get("krTerminations") or []
    if not kr_terminations:
        raise ValueError("survivorship audit has no krTerminations — nothing to build")
    codes = {row["code"].removesuffix(".KS") for row in kr_terminations}

    rows = V1_BUILD.kr_snapshot_rows(ledger)
    windows_by_bare_code = V1_BUILD.membership_windows(rows, codes)
    windows = {f"{code}.KS": window for code, window in windows_by_bare_code.items()}

    fetch_state = load_fetch_state(store)
    dart_identity = build_dart_identity(fetch_state)
    disclosures = load_disclosures(store)
    dividend_rows = load_dividend_sections(store)
    reviewed_book = TCA.load_book(reviewed_book_path)
    terminal_actions = build_terminal_actions(disclosures, dart_identity, reviewed_book)

    # Dividend AMOUNT lineage: real, decoded from live-observed `se`/
    # `stock_knd` values only (`kr_dividend_amount_lineage.KNOWN_SE_RAW_
    # VALUES`/`KNOWN_STOCK_KIND_RAW_VALUES`, both built from the real
    # `collect_kr_dividend_sections.py` run, commit
    # `dfeb098e26ff71d3b8149199677417a78eda42d6`). A ticker is
    # `DIVIDEND_RESOLVED` once it has at least one real CASH_DPS/STOCK_DPS
    # entry -- never from raw row presence alone (many raw rows are net
    # income, payout ratio or EPS figures, not a per-share amount).
    # `exDateSource` is never set here: this endpoint states no ex-date/
    # record date in any collected row, so dividend EVENT-DATE lineage
    # stays BLOCKED regardless (`kr_termination_inventory.completeness_
    # row`'s own unchanged rule).
    dividend_rows_by_ticker: dict[str, list[dict]] = {}
    for row in dividend_rows:
        dividend_rows_by_ticker.setdefault(row["ticker"], []).append(row)

    dividend_lineage: dict[str, dict] = {}
    dividend_lineage_detail: dict[str, dict] = {}
    for code in codes:
        ticker = f"{code}.KS"
        lineage = DAL.dividend_amount_lineage_for_ticker(
            dividend_rows_by_ticker.get(code, []))
        dividend_lineage_detail[ticker] = lineage
        if lineage["entries"]:
            dividend_lineage[ticker] = {"status": INV.DIVIDEND_RESOLVED}

    inventory = INV.build_inventory(
        kr_terminations=kr_terminations, kr_membership_windows=windows,
        dart_identity=dart_identity, terminal_actions=terminal_actions,
        dividend_lineage=dividend_lineage)

    disclosures_by_ticker = {}
    for row in disclosures:
        disclosures_by_ticker.setdefault(row["ticker"], 0)
        disclosures_by_ticker[row["ticker"]] += 1

    disclosures_by_full_ticker: dict[str, list[dict]] = {}
    for row in disclosures:
        disclosures_by_full_ticker.setdefault(row["ticker"], []).append(row)

    for security_row in inventory:
        ticker = security_row["code"]
        bare_code = ticker.removesuffix(".KS")
        security_row["rawDisclosureRowsCollected"] = disclosures_by_ticker.get(ticker, 0)
        security_row["rawDividendSectionRowsCollected"] = len(
            dividend_rows_by_ticker.get(bare_code, []))
        lineage = dividend_lineage_detail.get(ticker, {"entries": [], "selfConsistencyDisagreements": 0})
        security_row["dividendAmountLineageEntries"] = lineage["entries"]
        security_row["dividendAmountLineageSelfConsistencyDisagreements"] = (
            lineage["selfConsistencyDisagreements"])
        narrowed = KCA.plausibly_responsible_disclosures(
            disclosures_by_full_ticker.get(ticker, []),
            last_trading_date=security_row["lastTradingDate"])
        security_row["plausiblyResponsibleReceipts"] = [r["receiptNo"] for r in narrowed]

    actions_by_security = {row["oldSecurity"]: row for row in reviewed_book.get("actions", [])}
    for row in inventory:
        action = actions_by_security.get(row['code'], {})
        row['completeness']['amendmentChainResolved'] = (
            INV.READY if action.get('amendmentChainStatus') == 'READY' else INV.BLOCKED)
        row['economicEvidenceScope'] = 'FILED_CONTRACTUAL_TERMS_NOT_EXECUTION_CONFIRMATION'
        row['documentedTerms'] = action.get('documentedTerms')
        row['fieldEvidence'] = action.get('fieldEvidence', {})
        row['identityBridge'] = action.get('identityBridge')
        row['latestReviewedTermsReceiptNumber'] = action.get('latestReviewedTermsReceiptNumber')
        row['finalTermsReceiptNumber'] = action.get('finalTermsReceiptNumber')
        row['executionStatus'] = action.get('executionStatus', 'UNRESOLVED')
        row['reconstructionStatus'] = action.get('reconstructionStatus', 'BLOCKED')
        row['blockingReasons'] = action.get('blockingReasons', [])
        row['failedReceipts'] = action.get('failedReceipts', [])
        row['successorChain'] = reviewed_book.get('successorChains', {}).get(row['code'])
    summary = INV.summary(inventory)
    summary['byField']['amendmentChainResolved'] = sum(
        row['completeness']['amendmentChainResolved'] == INV.READY for row in inventory)
    counts = {
        'terminationTypesResolved': summary['byField']['terminationTypeResolved'],
        'terminalConsiderationResolved': summary['byField']['terminalConsiderationResolved'],
        'successorIdentityResolved': summary['byField']['successorResolvedWhereRequired'],
        'effectiveDateResolved': summary['byField']['effectiveDateResolved'],
        'fullyReconstructed': sum(r['reconstructionStatus'] == 'FULLY_RECONSTRUCTED' for r in inventory),
        'partiallyReconstructed': sum(r['reconstructionStatus'] == 'PARTIALLY_RECONSTRUCTED' for r in inventory),
        'unresolved': sum(r['reconstructionStatus'] == 'BLOCKED' for r in inventory),
        'securitiesBlockedByMaterialFailedReceipts': sum(any(
            f['category'] == 'MATERIALLY_BLOCKING' for f in r['failedReceipts']) for r in inventory),
    }

    return {
        "studyId": "kr-terminal-action-reconstruction-v2",
        "phase": "REAL_DOCUMENT_TERMS_RECONSTRUCTED_WITH_EXPLICIT_BLOCKERS",
        "historicalOutcomesComputed": False, "returnsComputed": False,
        "labelsConstructed": False, "modelsTrained": False,
        "inputs": {
            "signalHistoryCommit": signal_history_commit,
            "documentEvidenceCommit": reviewed_book.get('inputs', {}).get('documentEvidenceCommit'),
            "dividendEvidenceCommit": reviewed_book.get('inputs', {}).get('dividendEvidenceCommit'),
            "reviewedBookSha256": sha256_of(reviewed_book_path),
            "sourceHashes": reviewed_book.get('inputs', {}).get('sourceHashes', {}),
            "survivorshipAuditPath": str(survivorship_audit),
            "survivorshipAuditSha256": sha256_of(survivorship_audit),
            "krTerminationsCount": len(kr_terminations),
            "totalDisclosureRowsOnShard": len(disclosures),
            "totalDividendSectionRowsOnShard": len(dividend_rows),
            "fetchStatePresent": bool(fetch_state),
        },
        "securities": inventory,
        "summary": summary,
        "reconstructionCounts": counts,
        "foundationStatus": INV.foundation_status(inventory),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-history-root", required=True, type=Path,
                        help="A checkout of the signal-history branch (its ledger/ dir).")
    parser.add_argument("--signal-history-commit", required=True,
                        help="The exact commit hash of the signal-history checkout above, "
                            "recorded in the output for citation (never inferred from git "
                            "state inside this script, which may be a bare extraction).")
    parser.add_argument(
        "--survivorship-audit", type=Path,
        default=ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json")
    parser.add_argument(
        "--reviewed-book", type=Path,
        default=ROOT / "data/kr-terminal-corporate-actions.json")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    report = run(signal_history_root=args.signal_history_root,
                signal_history_commit=args.signal_history_commit,
                survivorship_audit=args.survivorship_audit,
                reviewed_book_path=args.reviewed_book)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    sidecar = args.output.with_suffix(args.output.suffix + ".sha256")
    sidecar.write_text(sha256_of(args.output) + "\n")
    print(json.dumps({"foundationStatus": report["foundationStatus"],
                      "securities": len(report["securities"]),
                      "totalDisclosureRowsOnShard": report["inputs"]["totalDisclosureRowsOnShard"],
                      "totalDividendSectionRowsOnShard":
                          report["inputs"]["totalDividendSectionRowsOnShard"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
