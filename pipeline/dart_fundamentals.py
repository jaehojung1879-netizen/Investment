"""Korean point-in-time fundamentals from DART, stored raw.

WHAT THIS IS FOR. The replay has tested the production model on 0 of its 713
dates because value and quality need financial statements as they were VISIBLE
on the date. The probe (``scripts/probe_dart_fundamentals.py``) established that
DART can supply them: receipt dates are present on every response, all seven
statement accounts the factors are built from come back, and quarterly reports
are served, not just annual. It also established the two limits this module is
shaped around — coverage starts in 2015, and a call takes ~9 seconds, so a full
backfill is ~14 hours and cannot be one job.

RAW IN, DERIVED LATER. What is stored here is the filing as DART states it:
account names, the amounts under whatever fields DART actually returned, and the
receipt date. Deriving ROE or a per-share numerator is a separate step, because
a derivation found to be wrong must be fixable without re-fetching five thousand
calls that took fourteen hours to make.

THE RECEIPT DATE IS THE POINT. A filing describes a period that ended long
before it was submitted: on the 2023 samples the quarterlies landed 45 days
after period end and the annual report 71 days after. Reading the annual numbers
from January 1st, when nobody could see them until March 12th, is a 71-day
look-ahead — the exact error a point-in-time replay exists to prevent. So
``availableFrom`` comes from the receipt number and from nothing else.

APPEND-ONLY, LIKE THE LEDGER. A record's id is ticker x fiscal year x report
code. A filing already on disk is never re-fetched and never overwritten:
restatements arrive as their own filing with their own receipt date, which is
what makes the history honest rather than tidy.
"""
from __future__ import annotations

import re
from pathlib import Path

# DART's own labels for what the production factors are built from. Filers do
# not agree on wording, so each is probed under its aliases; a name matched
# loosely here is a wrong number carried for a decade.
WANTED_ACCOUNTS: dict[str, tuple[str, ...]] = {
    "매출액": ("매출액", "수익(매출액)", "영업수익"),
    "영업이익": ("영업이익", "영업이익(손실)"),
    "당기순이익": ("당기순이익", "당기순이익(손실)"),
    "자본총계": ("자본총계",),
    "부채총계": ("부채총계",),
    "자산총계": ("자산총계",),
    "영업활동현금흐름": ("영업활동현금흐름", "영업활동으로인한현금흐름"),
}

# The amount columns a statement row can carry. All that are present are kept,
# under DART's own names, because they mean different things and picking one
# here would decide a question this module is deliberately not deciding:
# `thstrm_amount` is the period, `thstrm_add_amount` the year-to-date running
# total. An income-statement figure from a Q3 report is nine months cumulative,
# not three, and a TTM built from the wrong column is wrong all the way down.
AMOUNT_FIELDS = ("thstrm_amount", "thstrm_add_amount",
                 "frmtrm_amount", "frmtrm_add_amount", "bfefrmtrm_amount")

# Quarterly report codes. Annual-only would give one observation a year against
# a 63-day rebalance, so all four are collected.
REPORT_CODES: dict[str, str] = {
    "11013": "1분기", "11012": "반기", "11014": "3분기", "11011": "사업",
}

# Consolidated first. Production reads group-level figures, but a company with
# no subsidiaries files no consolidated statement, and for those the separate
# one is the only statement that exists. Which was used is RECORDED on the
# record rather than resolved silently: a book that mixes the two without
# saying so is comparing companies on different definitions.
FS_CONSOLIDATED = "CFS"
FS_SEPARATE = "OFS"

# DART status codes, as diagnoses. "not 000" tells you neither whether to fix
# the key nor whether to come back tomorrow.
STATUS_MEANING = {
    "000": "정상",
    "010": "등록되지 않은 키",
    "011": "사용할 수 없는 키 (등록 대기/정지)",
    "012": "접근할 수 없는 IP",
    "013": "조회된 데이터 없음",
    "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과 (일일 한도)",
    "021": "조회 가능한 회사 개수 초과",
    "100": "필드의 부적절한 값",
    "800": "시스템 점검 중",
    "900": "정의되지 않은 오류",
    "901": "사용자 계정의 개인정보 보유기간 만료",
}
# Coming back later cannot help these, so a run that meets one stops rather
# than spending its budget on the same refusal several thousand times.
FATAL_STATUSES = {"010", "011", "012", "901"}
# The daily quota. Not an error in the data — the run simply ends and the next
# one resumes where it stopped.
QUOTA_STATUS = "020"

# DART serves financial statements from this year forward. The replay starts in
# 2013, so the first two years carry no Korean value or quality however complete
# the collection is. Recorded here rather than discovered by a caller wondering
# why 2013 came back empty.
FIRST_SERVED_YEAR = 2015


def describe_status(status: str | None) -> str:
    return f"{status} ({STATUS_MEANING.get(str(status), '알 수 없는 코드')})"


def receipt_date(receipt_no: str | None) -> str | None:
    """The date a filing became readable, from the receipt number's head.

    DART states the visibility date nowhere else. Without it a filing has a
    period and no date at which it may be used, and the whole point-in-time
    claim collapses — so this returns None rather than falling back to anything,
    and a record with no receipt date is refused upstream.
    """
    digits = str(receipt_no or "")[:8]
    if len(digits) != 8 or not digits.isdigit():
        return None
    month, day = digits[4:6], digits[6:8]
    if not ("01" <= month <= "12") or not ("01" <= day <= "31"):
        return None
    return f"{digits[:4]}-{month}-{day}"


_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def parse_amount(text) -> float | None:
    """DART's amount strings to a number, or None where there is no number.

    Amounts arrive as strings with thousands separators, and a negative can be
    written either with a minus sign or in accounting parentheses. A blank, a
    dash or an em-dash means the filer did not state the line — which is not
    zero, and returning 0.0 for it would put a fabricated figure into a ratio.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    raw = str(text).strip().replace(",", "").replace(" ", "")
    if raw in ("", "-", "—", "–", "N/A", "nan"):
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1].strip()
    if not _NUMBER.match(raw):
        return None
    value = float(raw)
    return -value if negative else value


def normalize_account(name) -> str:
    """Whitespace out of an account label, so ' 영업 이익 ' matches '영업이익'."""
    return re.sub(r"\s+", "", str(name or ""))


def match_account(name: str) -> str | None:
    """The canonical account a DART label belongs to, or None.

    Exact match against the alias list only. A substring rule would fold
    '영업이익' into '영업이익률' and quietly rank companies on a percentage
    against companies on a currency amount.
    """
    cleaned = normalize_account(name)
    for canonical, aliases in WANTED_ACCOUNTS.items():
        if cleaned in {normalize_account(a) for a in aliases}:
            return canonical
    return None


def record_id(ticker: str, fiscal_year: int, report_code: str) -> str:
    """One filing, identified by what makes it that filing.

    Same discipline as the signal ledger: the id carries the identity, so a
    re-run recognises what it already holds and a restatement — which arrives
    as a later filing with its own receipt date — is a new record rather than
    an overwrite of the number that was actually visible at the time.
    """
    return f"{ticker}:{int(fiscal_year)}:{report_code}"


def build_record(*, ticker: str, stock_code: str, corp_code: str,
                 fiscal_year: int, report_code: str, rows: list[dict],
                 fs_div: str, collected_at: str) -> tuple[dict | None, str]:
    """One stored record from one DART response, or (None, reason).

    Refused rather than stored when the receipt date is missing or no wanted
    account is present: a record that cannot say when it became visible is
    unusable in a point-in-time replay, and storing it would leave a row that
    looks like coverage and is not.
    """
    if not rows:
        return None, "EMPTY_RESPONSE"

    receipts = {receipt_date(row.get("rcept_no")) for row in rows}
    receipts.discard(None)
    if not receipts:
        return None, "NO_RECEIPT_DATE"
    # One filing carries one receipt number; several means the response mixed
    # filings and the earliest is the only one every row was certainly visible
    # under.
    available_from = min(receipts)

    accounts: dict[str, dict] = {}
    for row in rows:
        canonical = match_account(row.get("account_nm"))
        if canonical is None or canonical in accounts:
            continue
        amounts = {field: parse_amount(row.get(field))
                   for field in AMOUNT_FIELDS if row.get(field) is not None}
        amounts = {k: v for k, v in amounts.items() if v is not None}
        if not amounts:
            continue
        accounts[canonical] = {
            "amounts": amounts,
            "accountId": row.get("account_id"),
            "statement": row.get("sj_div"),
            "label": row.get("account_nm"),
        }
    if not accounts:
        return None, "NO_WANTED_ACCOUNTS"

    return {
        "id": record_id(ticker, fiscal_year, report_code),
        "ticker": ticker,
        "stockCode": stock_code,
        "corpCode": corp_code,
        "fiscalYear": int(fiscal_year),
        "reportCode": report_code,
        "reportName": REPORT_CODES.get(report_code, report_code),
        "availableFrom": available_from,
        "receiptNos": sorted({str(r.get("rcept_no")) for r in rows if r.get("rcept_no")}),
        "fsDiv": fs_div,
        "accounts": accounts,
        "accountsFound": len(accounts),
        "accountsWanted": len(WANTED_ACCOUNTS),
        "currency": "KRW",
        "source": f"DART:fnlttSinglAcntAll:{fs_div}",
        "collectedAt": collected_at,
    }, ""


def shard_path(root: str | Path, fiscal_year: int) -> Path:
    """One shard per fiscal year — ~480 rows at 120 names x 4 reports."""
    return Path(root) / f"dart-{int(fiscal_year)}.jsonl.gz"


def work_list(tickers: list[str], years: list[int], existing_ids: set[str],
              report_codes: list[str] | None = None) -> list[tuple[str, int, str]]:
    """What is still to fetch, oldest first and stable in order.

    Oldest first because the early years are the ones the replay is thinnest on
    and a run that dies halfway should have bought the scarcer end. Stable order
    because a resumed backfill that reshuffles its work list re-fetches what it
    already holds.
    """
    codes = report_codes or sorted(REPORT_CODES)
    pending: list[tuple[str, int, str]] = []
    for year in sorted(years):
        if year < FIRST_SERVED_YEAR:
            continue
        for ticker in sorted(tickers):
            for code in codes:
                if record_id(ticker, year, code) not in existing_ids:
                    pending.append((ticker, year, code))
    return pending


def progress(collected: int, pending: int) -> dict:
    total = collected + pending
    return {
        "collected": collected,
        "pending": pending,
        "total": total,
        "completePct": round(100.0 * collected / total, 2) if total else None,
    }
