"""DART statement responses kept whole: every row, every status, every attempt.

WHY A SECOND RAW STORE EXISTS. `dart_fundamentals.build_record` keeps only
the rows whose label EXACTLY matched `WANTED_ACCOUNTS` and drops the rest of
DART's response on the floor. The v4 coverage audit
(`docs/results/kr-accounting-coverage-audit.json`) then found `당기순이익`
absent from about half of all stored quarterly filings -- 5% of 2016 Q1-Q3
filings rising to over 70% by 2024-2025 -- while the same filings carry
revenue and operating income from the same income statement. Whatever label
those filers used for net income was discarded at collection, so no amount of
re-reading the sealed store can say what it was. This store keeps the whole
response, so an account-mapping decision can be made FROM DART's own rows, and
re-made, without spending the collection a second time.

AND WHY IT IS A NEW MODULE. `dart_fundamentals.py`, `dart_derive.py`,
`accounting_quality.py` and `alpha_opportunity_features.py` are hash-pinned by
the `alpha-opportunity-model-v1` and `-v2` seals, which the v4 execution
harness re-verifies on every load. Adding an alias to `WANTED_ACCOUNTS` in
place would raise `SEALED_DEPENDENCY_CHANGED` there. Nothing here edits them.

THE STATUS IS RECORDED AS DART SENT IT. `collect_dart_fundamentals.fetch_one`
returns the literal "013" once both CFS and OFS fail, whatever DART actually
answered, so every one of the 1,723 absences in the sealed `absent.json` reads
013 by construction. Here each attempt keeps its own status and message.

POINT IN TIME IS STILL THE RECEIPT NUMBER. `availableFrom` comes from the
served `rcept_no` and from nothing else, exactly as `dart_fundamentals.
receipt_date` defines it; a response mixing receipt numbers is kept but
flagged, and a response with no receipt date is refused. Collection date is
never a visibility date.

NOTHING HERE READS A PRICE, A RETURN OR A LABEL.
"""
from __future__ import annotations

from pathlib import Path

from . import dart_fundamentals as DF

CONTRACT = "DART_RAW_STATEMENT_ROWS_V1"
ENDPOINT = "fnlttSinglAcntAll"
FS_ORDER = (DF.FS_CONSOLIDATED, DF.FS_SEPARATE)
# 90 MB, under GitHub's 100 MB blob limit, the same margin the historical
# ledger keeps. A shard that outgrows it is split finer, never raised.
MAX_SHARD_BYTES = 90 * 1024 * 1024


def record_id(ticker: str, fiscal_year: int, report_code: str) -> str:
    return f"raw:{DF.record_id(ticker, fiscal_year, report_code)}"


def shard_path(root: str | Path, fiscal_year: int) -> Path:
    return Path(root) / f"raw-{int(fiscal_year)}.jsonl.gz"


def attempt(fs_div: str, payload: dict | None, error: str = "") -> dict:
    """One CFS or OFS call, as DART answered it."""
    if payload is None:
        return {"fsDiv": fs_div, "status": None, "message": error or "REQUEST_FAILED", "rows": 0}
    rows = payload.get("list") or []
    return {"fsDiv": fs_div, "status": str(payload.get("status")),
            "message": payload.get("message"), "rows": len(rows)}


def build_raw_record(*, ticker: str, stock_code: str, corp_code: str, fiscal_year: int,
                     report_code: str, fs_div: str, rows: list[dict], attempts: list[dict],
                     collected_at: str, identity_basis: str | None = None
                     ) -> tuple[dict | None, str]:
    """One stored filing from one served response, rows verbatim, or (None, reason)."""
    if not rows:
        return None, "EMPTY_RESPONSE"
    receipts = sorted({str(r.get("rcept_no")) for r in rows if r.get("rcept_no")})
    dates = sorted({DF.receipt_date(r) for r in receipts} - {None})
    if not dates:
        return None, "NO_RECEIPT_DATE"
    return {
        "id": record_id(ticker, fiscal_year, report_code),
        "contract": CONTRACT,
        "ticker": ticker, "stockCode": stock_code, "corpCode": corp_code,
        "identityBasis": identity_basis,
        "fiscalYear": int(fiscal_year), "reportCode": report_code,
        "reportName": DF.REPORT_CODES.get(report_code, report_code),
        "fsDiv": fs_div,
        # Earliest receipt, the same rule `dart_fundamentals.build_record`
        # uses; a mixed response is flagged so a reader never mistakes it for
        # one filing.
        "availableFrom": dates[0],
        "receiptNos": receipts,
        "mixedReceipts": len(receipts) > 1,
        "source": f"DART:{ENDPOINT}:{fs_div}",
        "attempts": attempts,
        "rows": [dict(r) for r in rows],
        "collectedAt": collected_at,
    }, ""


def absence_record(*, ticker: str, fiscal_year: int, report_code: str, attempts: list[dict],
                   checked_at: str) -> dict:
    """DART served no rows for this filing under any statement division."""
    return {"ticker": ticker, "fiscalYear": int(fiscal_year), "reportCode": report_code,
            "attempts": attempts, "checkedAt": checked_at,
            "dueBy": DF.filing_deadline(fiscal_year, report_code)}


def work_list(tickers, years, codes, done_ids: set[str], settled_absent: set[str]):
    """Filings still to fetch, in the given YEAR order (priority), then ticker, then code.

    Year order is the caller's: the gate years and the priors they need are
    worth more per call than a year the gate never reads.
    """
    pending = []
    for year in years:
        if year < DF.FIRST_SERVED_YEAR:
            continue
        for ticker in sorted(tickers):
            for code in codes:
                key = record_id(ticker, year, code)
                if key not in done_ids and key not in settled_absent:
                    pending.append((ticker, year, code))
    return pending


def settled(absent: dict, today: str) -> set[str]:
    """Absence ids whose filing deadline plus grace has passed (see `DF.absence_is_settled`)."""
    return {key for key, row in (absent or {}).items()
            if DF.absence_is_settled(int(row["fiscalYear"]), str(row["reportCode"]), today)}


def status_table(records: list[dict], absent: dict) -> list[dict]:
    """Served / absent counts by fiscal year, report code and each attempt's real status."""
    tally: dict[tuple, int] = {}
    for row in records:
        key = (row["fiscalYear"], row["reportCode"], "SERVED", row["fsDiv"])
        tally[key] = tally.get(key, 0) + 1
    for row in (absent or {}).values():
        statuses = "/".join(f"{a['fsDiv']}={a['status']}" for a in row.get("attempts") or [])
        key = (row["fiscalYear"], row["reportCode"], "ABSENT", statuses)
        tally[key] = tally.get(key, 0) + 1
    return [{"fiscalYear": y, "reportCode": c, "result": r, "detail": d, "filings": n}
            for (y, c, r, d), n in sorted(tally.items(), key=str)]
