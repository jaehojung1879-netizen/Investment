"""Build the 22 terminated + 25 continuing securities' DIVIDEND AMOUNT
lineage from the real `alotMatter.json` collection, and reconcile the
continuing names against the sealed replay-v16 ledger's own real Yahoo
distribution events.

INPUTS, BOTH REAL, NEITHER RE-DERIVED.
  - `ledger/kr-corporate-actions/kr-dividend-sections.jsonl.gz` on a
    `signal-history` checkout: `collect_kr_dividend_sections.py`'s real
    output (47/47 tickers, 6,150 rows, commit
    `dfeb098e26ff71d3b8149199677417a78eda42d6`).
  - `ledger/historical/replay-v16`'s own sealed `corporate-events/YYYY-MM`
    components, read through `replay_inputs.InputStore` -- the SAME reader
    `scripts/audit_alpha_opportunity_v3_survivorship.py` already uses for
    this exact component family, never a second implementation. These are
    real Yahoo dividend/split events already sealed into the historical
    replay ledger; nothing is fetched fresh.

WHAT THIS DOES NOT DO. Computes no forward return, no IC, no Alpha, no
backtest, and touches no portfolio selection or valuation function
anywhere in this repository. Produces no ex-date, record date, decision
date or payment date -- see `kr_dividend_amount_lineage.py`'s own
docstring for why that lineage stays separately BLOCKED regardless of what
this script resolves.
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
from pipeline import kr_dividend_amount_lineage as DAL  # noqa: E402
from pipeline import kr_dividend_reconciliation as REC  # noqa: E402
from pipeline import replay_inputs as RI  # noqa: E402

REPLAY_VERSION = "replay-v16"


def load_dividend_section_rows(store: Path) -> list[dict]:
    path = store / "kr-dividend-sections.jsonl.gz"
    if not path.exists():
        return []
    return HS.read_jsonl(path)


def load_yahoo_dividend_events(ledger: Path, tickers: set[str]) -> dict[str, list[dict]]:
    """ticker -> [{"date":..., "amountPerShare":...}, ...], read from the
    SEALED replay-v16 corporate-events components -- real Yahoo dividend
    events already committed to this repository, filtered to `tickers`
    (each carrying the ".KS" suffix) and to real (>0) dividend amounts.
    """
    manifest_path = ledger / f"historical/{REPLAY_VERSION}/inputs.json"
    manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    store = RI.InputStore(ledger, REPLAY_VERSION, manifest_raw["dataVersion"])
    manifest = store.manifest()
    by_ticker: dict[str, list[dict]] = {t: [] for t in tickers}
    for name in sorted(c for c in manifest["components"] if c.startswith("corporate-events/20")):
        for row in store.load_component(name, manifest):
            ticker = row.get("ticker")
            if ticker not in by_ticker:
                continue
            amount = float(row.get("dividend") or 0.0)
            if amount > 0:
                by_ticker[ticker].append({"date": row["date"], "amountPerShare": amount,
                                          "ticker": ticker})
    return by_ticker


def dart_rows_for_reconciliation(lineage_entries: list[dict], ticker: str) -> list[dict]:
    """Only COMMON-class CASH_DPS entries enter cross-validation: Yahoo's
    distribution events describe the single actively-traded (common)
    listing, so an UNSPECIFIED_CLASS or PREFERRED entry is not comparable
    to it without a further identity claim this script does not make.
    """
    out = []
    for entry in lineage_entries:
        if entry["metric"] != DAL.CASH_DPS or entry["shareClass"] != DAL.COMMON:
            continue
        out.append({
            "ticker": ticker, "receiptDate": entry["sourceReceiptDate"],
            "amountPerShare": entry["value"], "isStockDividend": False,
            "isAmendment": False,
        })
    return out


def run(*, signal_history_root: Path, signal_history_commit: str,
       terminated_codes: list[str], continuing_codes: list[str]) -> dict:
    ledger = signal_history_root / "ledger"
    store = ledger / "kr-corporate-actions"
    rows = load_dividend_section_rows(store)

    by_ticker: dict[str, list[dict]] = {}
    for row in rows:
        by_ticker.setdefault(row["ticker"], []).append(row)

    all_codes = sorted(set(terminated_codes) | set(continuing_codes))
    all_tickers = {f"{c}.KS" for c in all_codes}

    lineage_by_ticker = {}
    for code in all_codes:
        ticker = f"{code}.KS"
        lineage_by_ticker[ticker] = DAL.dividend_amount_lineage_for_ticker(
            by_ticker.get(code, []))

    yahoo_events = load_yahoo_dividend_events(ledger, all_tickers)

    continuing_tickers = {f"{c}.KS" for c in continuing_codes}
    dart_by_ticker = {
        t: dart_rows_for_reconciliation(lineage_by_ticker[t]["entries"], t)
        for t in continuing_tickers
    }
    yahoo_by_ticker = {t: yahoo_events.get(t, []) for t in continuing_tickers}
    # The point-date reconciler, reused unmodified -- see `kr_dividend_
    # amount_lineage.cross_validate_against_yahoo_by_fiscal_year`'s
    # docstring for why this alone reads near-zero agreement (a date-role
    # gap, not an amount defect) and is published alongside, never in
    # place of, the fiscal-year amount cross-validation below.
    reconciliation = REC.reconcile_many(dart_by_ticker, yahoo_by_ticker)

    fiscal_year_validation = {}
    fy_status_counts = {DAL.EXACT_MATCH: 0, DAL.AMOUNT_MISMATCH: 0,
                        DAL.NO_YAHOO_EVENT_IN_WINDOW: 0}
    for ticker in sorted(continuing_tickers):
        rows = DAL.cross_validate_against_yahoo_by_fiscal_year(
            lineage_by_ticker[ticker]["entries"], yahoo_events.get(ticker, []))
        fiscal_year_validation[ticker] = rows
        for row in rows:
            fy_status_counts[row["status"]] += 1
    fy_total = sum(fy_status_counts.values())

    securities = {}
    for code in all_codes:
        ticker = f"{code}.KS"
        lineage = lineage_by_ticker[ticker]
        securities[ticker] = {
            "rawDividendSectionRows": len(by_ticker.get(code, [])),
            "amountLineageEntries": lineage["entries"],
            "selfConsistencyDisagreements": lineage["selfConsistencyDisagreements"],
            "isTerminated": code in terminated_codes,
            "realYahooDividendEventsKnown": len(yahoo_events.get(ticker, [])),
        }

    return {
        "studyId": "kr-dividend-amount-lineage-v2",
        "historicalOutcomesComputed": False, "returnsComputed": False,
        "labelsConstructed": False, "modelsTrained": False,
        "inputs": {
            "signalHistoryCommit": signal_history_commit,
            "replayVersion": REPLAY_VERSION,
            "terminatedCodes": terminated_codes,
            "continuingCodes": continuing_codes,
            "totalDividendSectionRows": len(rows),
        },
        "securities": securities,
        "continuingNameReconciliation": {
            "pointDateReconciliation": reconciliation,
            "fiscalYearAmountCrossValidation": {
                "byTicker": fiscal_year_validation,
                "statusCounts": fy_status_counts,
                "exactMatchRatePct": (
                    round(100.0 * fy_status_counts[DAL.EXACT_MATCH] / fy_total, 2)
                    if fy_total else None),
            },
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-history-root", required=True, type=Path)
    parser.add_argument("--signal-history-commit", required=True)
    parser.add_argument(
        "--termination-inventory", type=Path,
        default=ROOT / "docs/results/kr-termination-inventory.json")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    inventory = json.loads(args.termination_inventory.read_text(encoding="utf-8"))
    terminated_codes = sorted(row["code"].removesuffix(".KS")
                              for row in inventory["securities"])

    from pipeline import kr_continuing_dividend_sample as SAMPLE
    universe_root = args.signal_history_root / "ledger" / "universe" / "kr"
    universe_rows = []
    for path in sorted(universe_root.glob("krx-universe-*.jsonl.gz")):
        universe_rows.extend(HS.read_jsonl(path))
    pool = SAMPLE.select_continuing_sample(
        universe_rows, terminated_codes=set(terminated_codes))
    continuing_codes = sorted(p["code"] for p in pool)

    report = run(signal_history_root=args.signal_history_root,
                signal_history_commit=args.signal_history_commit,
                terminated_codes=terminated_codes, continuing_codes=continuing_codes)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    sidecar = args.output.with_suffix(args.output.suffix + ".sha256")
    sidecar.write_text(hashlib.sha256(args.output.read_bytes()).hexdigest() + "\n")
    print(json.dumps({
        "securitiesWithAmountLineage": sum(
            1 for s in report["securities"].values() if s["amountLineageEntries"]),
        "totalTerminated": len(terminated_codes),
        "fiscalYearExactMatchRatePct":
            report["continuingNameReconciliation"]["fiscalYearAmountCrossValidation"][
                "exactMatchRatePct"],
        "pointDateAgreementRatePct":
            report["continuingNameReconciliation"]["pointDateReconciliation"][
                "agreementRatePct"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
