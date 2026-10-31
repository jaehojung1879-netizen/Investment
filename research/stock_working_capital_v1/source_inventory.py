"""Metadata-only intersection with the existing original-XBRL ledger.

Never read a price, label or a financial amount to decide source availability.
No record's extracted accounts or ZIP digest substitutes for the original bytes.
"""
from collections import Counter
import calendar
from datetime import date, timedelta
import gzip
import json
import os
from pathlib import Path
import re
import subprocess

from . import pit_filing_evidence as E
from . import portable_collection as P

SOURCE = "ledger/fundamentals/kr-xbrl-original/dart-xbrl-2015.jsonl.gz"


def filing_lags(targets):
    """Declared month-end diagnostic, never certification of a fiscal window."""
    rows = []
    for t in targets:
        year, month = map(int, t["periodEndMonth"].split("-"))
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        receipt_date = date.fromisoformat(t["availableFrom"])
        naive_due = month_end + timedelta(days=90)
        rows.append({"receipt": t["receipt"], "fiscalYear": t["fiscalYear"],
                     "declaredPeriodEndMonth": t["periodEndMonth"], "availableFrom": t["availableFrom"],
                     "monthEndToReceiptCalendarDaysDiagnostic": (receipt_date - month_end).days,
                     "naive90DayDateDiagnostic": naive_due.isoformat(),
                     "naive90DayDateWeekday": naive_due.strftime("%A"),
                     "fiscalWindowCertified": False, "legalDeadlineCertified": False})
    return {"basis": "Declared report month only; month-end assumption is a diagnostic, not source admission",
            "targetCount": len(rows), "rows": rows,
            "laterThanNaive90Days": sum(r["monthEndToReceiptCalendarDaysDiagnostic"] > 90 for r in rows),
            "minimumLag": min((r["monthEndToReceiptCalendarDaysDiagnostic"] for r in rows), default=None),
            "maximumLag": max((r["monthEndToReceiptCalendarDaysDiagnostic"] for r in rows), default=None),
            "selectedPolicy": None, "historicalOutcomesRead": 0,
            "officialGuide": {"url": "https://dart.fss.or.kr/introduction/content2.do",
                              "retrievedThisSession": False, "status": "HOST_NOT_ALLOWED"},
            "legalReviewStatus": "INCOMPLETE_NOT_READY_TO_PREREGISTER",
            "unresolvedLegalChecks": ["historically effective Article159 annual-report rule",
                                      "weekend/public-holiday deadline extension",
                                      "issuer-specific extensions, including applicable COVID-era measures",
                                      "changed fiscal year, short year and calendar-end validity"],
            "constraint": "A deadline never proves actual publication. Preserve original receipt visibility and pending F2 admission gate."}


def compare(rows, targets):
    wanted = {t["receipt"] for t in targets}
    supplied = {r for row in rows for r in row.get("receiptNos", [])}
    return {"existingOriginalRecords": len(rows),
            "existingFiscalYearCounts": dict(sorted(Counter(str(r["fiscalYear"]) for r in rows).items())),
            "existingReportCodeCounts": dict(sorted(Counter(r["reportCode"] for r in rows).items())),
            "fixedOriginalTargets": len(wanted),
            "sameReceiptMetadataCount": len(wanted & supplied),
            "sameReceiptNos": sorted(wanted & supplied),
            "originalZipBytesRecovered": 0, "originalFinancialFactsVerified": 0,
            "newHistoricalOutcomesRead": 0,
            "scope": "Existing original-XBRL ledger only; NOT proof that every external archive was searched",
            "verdict": "METADATA_INTERSECTION_NOT_ORIGINAL_BYTE_OR_NUMERIC_ADMISSION"}


def inspect(root, commit):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("EXACT_SOURCE_COMMIT_REQUIRED")
    raw = subprocess.run(["git", "cat-file", "blob", commit + ":" + SOURCE], cwd=root,
                         env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, capture_output=True, check=True).stdout
    # Parsing is structural; only identity/period fields are used or emitted.
    rows = [json.loads(r) for r in gzip.decompress(raw).splitlines() if r.strip()]
    report = compare(rows, P.reference_targets())
    report["source"] = {"commit": commit, "path": SOURCE, "sha256": E.sha(raw),
                        "codeSha256": E.sha(Path(__file__).read_bytes())}
    return report
