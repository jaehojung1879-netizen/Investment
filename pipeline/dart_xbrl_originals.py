"""Which fiscal-2015 KR quarterly filing is the ORIGINAL, and what `fnlttXbrl.xml` said about it.

WHAT THE LIVE PROBE ESTABLISHED (GitHub Actions run 36300578100, 2026-09-27,
`data/kr-accounting-coverage-repair-v1` at `4965599c`, artifact
`dart-fiscal-2015-probe`, sha256 `af7e3b58…885c2e`). For all 8 sampled
tickers, `fnlttSinglAcntAll` answered 013 under both CFS and OFS for every
one of fiscal-2015 Q1/H1/Q3 (24 of 24 attempts) -- `dart_raw_statements
.SOURCE_ABSENCE_STATUSES` correctly calls that a genuine source absence for
THAT endpoint. `list.json`, over the SAME tickers and period, listed the
ORIGINAL 2015 quarterly and half-year reports with real receipt numbers
(e.g. `000030.KS`'s `분기보고서 (2015.03)`, receipt `20150515002248` -- an
amended re-filing of the same quarter, `[기재정정]분기보고서 (2015.03)`,
receipt `20150529001078`, is ALSO listed and is never substituted for the
original). One `fnlttXbrl.xml` package per issuer was then fetched for the
2015 Q3 report: 6 of 8 (`000080`, `000100`, `000120`, `000150`, `000210`,
`000240`) returned real ZIP payloads (153–170 KB, one at 85 KB); 2 of 8
(`000030`, `000060`) returned DART's own error envelope, `<result><status>
014</status><message>파일이 존재하지 않습니다.</message></result>` (147
bytes, confirmed non-ZIP). This is the exact evidence this module classifies
against -- nothing here is inferred beyond it.

THE CONSEQUENCE. `fnlttSinglAcntAll`'s historical depth and the original
filing archive's are DIFFERENT FACTS about DIFFERENT endpoints. Fiscal-2015
quarterlies are `PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY` for the
STATEMENT endpoint specifically, never a blanket claim about DART. Whether
the four gate accounts can actually be RECOVERED from a served ZIP is a
separate, still-open question this module does not answer -- see
`dart_xbrl_statements.py`'s own `CANDIDATE_UNCONFIRMED` discipline. Nothing
here has read the CONTENTS of a served ZIP; this session's only evidence for
"real ZIP payload" is that its first two bytes are `PK` (the standard ZIP
local-file-header signature) and DART's own error envelope is not.

ORIGINAL VS. AMENDMENT. `list.json`'s `report_nm` prefixes an amended
re-filing with `[기재정정]` (confirmed live: `000030.KS`'s Q1 2015 shows
both). The ORIGINAL is the earliest-receipt row matching a stage's report
name WITHOUT that marker; an amendment is never read as if it were the
original filing, and a stage with only an amended filing on record is its
own state (`ORIGINAL_NOT_LISTED_ONLY_AMENDMENT`), never silently upgraded to
"original available".
"""
from __future__ import annotations

CONTRACT = "DART_XBRL_ORIGINAL_DISCOVERY_V1"

# Q1/H1/Q3 only -- fiscal-2015 annual (11011) is already served by
# `fnlttSinglAcntAll` (81 of the sealed store's 2015 filings) and stays on
# that path; this module exists for exactly the codes that path cannot serve.
STAGE_REPORT_NAME = {
    "11013": ("분기보고서", "(2015.03)"),
    "11012": ("반기보고서", "(2015.06)"),
    "11014": ("분기보고서", "(2015.09)"),
}
AMENDMENT_MARKER = "[기재정정]"

# Classification codes. Exactly one applies to a (ticker, stage).
NO_ORIGINAL_FILING_INDEX = "NO_ORIGINAL_FILING_INDEX"
ORIGINAL_NOT_LISTED_ONLY_AMENDMENT = "ORIGINAL_NOT_LISTED_ONLY_AMENDMENT"
AMBIGUOUS_REPORT_MATCH = "AMBIGUOUS_REPORT_MATCH"
ORIGINAL_LISTED = "ORIGINAL_LISTED"
XBRL_ZIP_SERVED = "XBRL_ZIP_SERVED"
FILE_NOT_AVAILABLE_014 = "FILE_NOT_AVAILABLE_014"
REQUEST_ERROR = "REQUEST_ERROR"
CLASSIFICATIONS = (
    NO_ORIGINAL_FILING_INDEX, ORIGINAL_NOT_LISTED_ONLY_AMENDMENT, AMBIGUOUS_REPORT_MATCH,
    ORIGINAL_LISTED, XBRL_ZIP_SERVED, FILE_NOT_AVAILABLE_014, REQUEST_ERROR,
)

# DART's own error envelope for `fnlttXbrl.xml`, confirmed live (see module
# docstring). A tiny, deliberately permissive parser: it reads only the two
# fields the probe has actually observed, and never assumes a served ZIP's
# internal shape from this.
_STATUS_TAG, _MESSAGE_TAG = "<status>", "<message>"


def parse_error_envelope(body: bytes) -> dict | None:
    """DART's `<result><status>…</status><message>…</message></result>` error body, or None."""
    text = body.decode("utf-8", errors="replace")
    if _STATUS_TAG not in text or "<result>" not in text:
        return None
    status = text.split(_STATUS_TAG, 1)[1].split("</status>", 1)[0].strip()
    message = (text.split(_MESSAGE_TAG, 1)[1].split("</message>", 1)[0].strip()
              if _MESSAGE_TAG in text else None)
    return {"status": status, "message": message}


def select_original_filing(periodic_reports: list[dict], stage: str) -> tuple[dict | None, str]:
    """(row, classification) for one fiscal-2015 stage, from `list.json` rows.

    `periodic_reports` items carry `reportNm`/`rceptNo`/`rceptDt`, exactly the
    fields the live probe already reads. Matching is on the report's own
    stated words -- the type ("분기보고서"/"반기보고서") and stated period
    ("(2015.03)" etc.) -- never a computed date arithmetic.
    """
    label, period = STAGE_REPORT_NAME[stage]
    matches = [r for r in periodic_reports
              if label in str(r.get("reportNm")) and period in str(r.get("reportNm"))]
    originals = [r for r in matches if AMENDMENT_MARKER not in str(r.get("reportNm"))]
    if not matches:
        return None, NO_ORIGINAL_FILING_INDEX
    if not originals:
        return None, ORIGINAL_NOT_LISTED_ONLY_AMENDMENT
    if len({r.get("rceptNo") for r in originals}) > 1:
        # More than one non-amended row claims the same stage and period --
        # a real DART shape this sample never showed, so it is refused
        # rather than guessed at (e.g. picking the earliest).
        return None, AMBIGUOUS_REPORT_MATCH
    return min(originals, key=lambda r: str(r.get("rceptDt") or r.get("rceptNo"))), ORIGINAL_LISTED


def classify_xbrl_response(body: bytes) -> tuple[str, dict | None]:
    """(classification, errorEnvelope) for one `fnlttXbrl.xml` response body."""
    if body[:2] == b"PK":
        return XBRL_ZIP_SERVED, None
    envelope = parse_error_envelope(body)
    if envelope is not None and envelope.get("status") == "014":
        return FILE_NOT_AVAILABLE_014, envelope
    return REQUEST_ERROR, envelope
