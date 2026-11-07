"""Reproduce source-only C2 qualification from retained, hashed payloads.

No network, price ratios, NAVs, beta fits or historical attribution are used.
Requires the exact referenced Git objects, local raw captures and optional
xlrd 2.0.2 for the issuer's original XLS. Never writes to a ledger or workflow.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys
from types import ModuleType

from pipeline import replay_calendar

from . import source_audit as S


def _module(repo, pin, name):
    module = ModuleType(name)
    raw = S.pinned_bytes(repo, pin)
    module.__file__ = f"<{pin['commit']}:{pin['path']}>"
    sys.modules[name] = module
    try:
        exec(compile(raw, module.__file__, "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


def qualify(repo: Path, raw_dir: Path) -> dict:
    here = Path(__file__).parent
    pins = json.loads((here / "reference-pins.json").read_text())
    sources = json.loads((here / "sources.json").read_text())
    for path, sha in sources["runtimeFiles"].items():
        S.verified_payload(repo / path, sha)
    # Authenticate every retained source before looking at economic fields.
    originals = {item["file"]: S.verified_payload(raw_dir / item["file"], item["sha256"])
                 for item in sources["payloads"]}
    spec = json.loads(S.pinned_bytes(repo, pins["contract"]))
    verified_fixed = []
    for item in spec["pinnedInputs"]["files"]:
        S.verified_payload(repo / item["path"], item["sha256"])
        verified_fixed.append(item)
    rows = json.loads(gzip.decompress((repo / "docs/results/regional-standalone-paths.json.gz")
                                     .read_bytes()))["regional"]["KR"]
    targets = S.fixed_input_projection(rows)
    if targets["blocks"] != 155 or targets["distinctNames"] != 72:
        raise S.SourceError("REGISTERED_FIXED_TARGET_COUNTS_CHANGED")
    sessions = [d.strftime("%Y-%m-%d") for d in replay_calendar.sessions(
        targets["from"], targets["through"], "KR")]
    session_index = {day: index for index, day in enumerate(sessions)}
    horizon_counts = {}
    for label, count in (("H126", 6), ("H252", 12)):
        lengths = [session_index[rows[i + count - 1]["endDate"]] - session_index[rows[i]["date"]]
                   for i in range(len(rows) - count + 1)]
        horizon_counts[label] = {"registeredConsecutiveBlocks": count,
                                 "actualKrReturnIntervalsMin": min(lengths),
                                 "actualKrReturnIntervalsMax": max(lengths),
                                 "datesOrThresholdsChanged": False}
    issuer = _module(repo, pins["etf_source"], "_c2_readonly_issuer_source")
    economics = _module(repo, pins["economics"], "_c2_readonly_economic_gate")
    market = S.audit_issuer_xls(originals["153130-price-cutoff.xls"], issuer_parser=issuer,
                                expected_sessions=sessions, through=targets["through"])
    history = issuer.inspect_distribution_history(
        [originals[f"153130-distributions-{n}.json"] for n in (1, 2)],
        product_source=originals["samsung-product-2ETF35.json"])
    events = []
    for n in (1, 2):
        page = json.loads(issuer.project_distribution_page(originals[f"153130-distributions-{n}.json"]))
        for row in page["dividList"]:
            events.append({"ticker": row["stkTicker"], "recordDate": row["basicD"],
                           "payDate": row["payD"], "grossCash": row["dividA"]})
    notices = sources["reviewedNoticeTranscriptions"]
    distributions = S.qualify_distributions(events, notices, through=targets["through"])
    gate = economics.total_return_input_gate(
        price_basis="AS_TRADED_CLOSE", distributions_complete=False,
        actions_complete=False, terminal_required=False, terminal_evidence=None,
        investor_tax_basis="GROSS_PRE_INVESTOR_TAX")
    # Reuse retained official fiscal-DPS evidence, not its date as an ex-date.
    stock_path = "docs/results/kr-terminal-action-reconstruction-v2.json"
    stock_raw = S.verified_payload(repo / stock_path, sources["stockLineageSha256"])
    stock_rows = json.loads(stock_raw)["securities"]
    lineage = []
    for record in stock_rows:
        ticker = record["code"]
        holding = [row for row in rows if ticker in row["weights"]]
        if not holding:
            continue
        last_exit = max(row["endDate"] for row in holding)
        last_trade = record.get("lastTradingDate")
        if not last_trade:
            continue
        lineage.append({
            "ticker": ticker, "fixedHoldingBlocks": len(holding),
            "lastFixedExit": last_exit, "lastTradingDate": last_trade,
            "terminalConsiderationNeededForTheseHoldings": last_exit >= last_trade,
            "yahooDividendEventCount": record["dividendEventsKnownFromYahoo"],
            "officialFiscalCashDpsEntriesBeforeLastTrade": [
                entry for entry in record["dividendAmountLineageEntries"]
                if entry["metric"] == "CASH_DPS" and entry["shareClass"] == "COMMON"
                and entry["sourceReceiptDate"] <= last_trade
                and entry["fiscalYear"] <= int(last_exit[:4])],
            "annualDpsConvertedToCashEvent": False,
            "identityContinuityCertified": False,
            "exDateStatus": record["completeness"]["exDateSemanticsResolved"]})
    boundaries = {row[key] for row in rows for key in ("date", "endDate")}
    gaps = set(market["missingSessions"] + market["invalidCloseDates"] +
               market["invalidVolumeDates"] + market["zeroVolumeDates"])
    return {
        "mode": "SOURCE_QUALIFICATION_ONLY", "verdict": "SOURCE_BLOCKED",
        "referencePins": pins, "fixedInputFilesVerified": verified_fixed,
        "fixedTargets": targets,
        "registeredHorizonDateAudit": horizon_counts,
        "retainedOriginalPayloadsVerified": len(originals),
        "payloadVerificationIsHistoricalVintageVerification": False,
        "calendarSource": "repository.replay_calendar.KR (not exchange-certified vintage)",
        "marketPriceCoverage": market,
        "fixedBoundaryDates": len(boundaries), "fixedBoundaryDataBlockers": sorted(boundaries & gaps),
        "distributionHistory": {
            "declaredCount": history["declaredCount"],
            "paginationCompleteAgainstDeclaredCount": history["paginationCompleteAgainstDeclaredCount"],
            "coverageGapYears": history["coverageGapYears"],
            "gapInterpretation": history["gapInterpretation"]},
        "noticeExDateQualification": distributions,
        "shareholderTotalReturnGateReusedFrom317": gate,
        "stockDividendLineage": {"sourcePath": stock_path, "sha256": S.digest(stock_raw), "heldTerminated": lineage},
        "cashEtfIsRegisteredCashScenario": False,
        "cashEtfRequiresProductRiskCostAndProtocolReview": True,
        "historicalOutcomesComputed": 0, "productionWrites": 0,
        "outcomeExecutionAuthorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = qualify(args.repo, args.raw_dir)
    with args.out.open("x") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
