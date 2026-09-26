"""Read real DART XML/HTML tables without turning filing presence into economics.

Validated on the 92 retrieved documents at signal-history commit
71c5128a01a7528536a8ff24c4e82d896363fec0. Table rows retain cell boundaries,
row indices and correction-table status. DART's TE/TU cells, &cr; entities,
HTML BRs, Korean dates, common/preferred ratios and cash-instead-of-stock
wording are observed in that corpus. Extraction produces candidates, never
an automatic declaration of finality, subject identity or action completion.
Report names are not inputs. Later amendments keep their own receipt dates.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from datetime import date

PARSER_VALIDATION_STATUS = "REAL_DART_TABLE_PATTERNS_VALIDATED"

AMBIGUOUS_ZERO_MATCHES = "ZERO_MATCHES"
AMBIGUOUS_MULTIPLE_MATCHES = "MULTIPLE_CANDIDATE_MATCHES"

# Legacy text-only labels. Real XML/HTML extraction uses table boundaries
# below; neither path alone asserts subject identity or economic finality.
FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "mergerRatio": ("합병비율",),
    "mergerConsiderationValue": ("합병가액",),
    "mergerEffectiveDate": ("합병기일",),
    "mergerRegistrationDate": ("합병등기일",),
    "survivingCompany": ("존속회사",),
    "dissolvingCompany": ("소멸회사",),
    "newSharesPerOldShare": ("1주당 신주배정주식수", "1주당 배정주식수"),
    "cashPayoutPerShare": ("1주당 현금교부금액", "현금교부금액"),
    "tenderOfferPrice": ("공개매수가격",),
    "tenderOfferPeriod": ("공개매수기간",),
    "delistingEffectiveDate": ("상장폐지일",),
    "lastTradingDate": ("매매거래정지",),
}

# A value follows its label after an optional colon/space -- NEVER a
# newline, which `\s` alone would also match -- and runs until a newline, a
# closing table-cell-like boundary, or end of string. A label with nothing
# on its own line (the value only appears below it) is a ZERO match, never
# a guess at the next line's unrelated text.
_VALUE_PATTERN = re.compile(r"[ :]{1,4}([^\n\r]{1,80})")


def extract_labeled_value(text: str, labels: tuple[str, ...]) -> tuple[str | None, str | None]:
    """(value, reason). `value` is `None` unless EXACTLY ONE label (from any
    of its known synonyms) matches exactly once in `text` -- never a first-
    match pick among several, and never merged across synonyms that both
    matched. `reason` is one of `AMBIGUOUS_ZERO_MATCHES`/
    `AMBIGUOUS_MULTIPLE_MATCHES` when `value` is `None`, else `None`.
    """
    candidates: list[str] = []
    for label in labels:
        for match in re.finditer(re.escape(label), text):
            tail = text[match.end():match.end() + 100]
            value_match = _VALUE_PATTERN.match(tail)
            if value_match:
                candidates.append(value_match.group(1).strip())
    if not candidates:
        return None, AMBIGUOUS_ZERO_MATCHES
    unique_candidates = set(candidates)
    if len(unique_candidates) > 1:
        return None, AMBIGUOUS_MULTIPLE_MATCHES
    if len(candidates) > 1:
        # The same label matched more than once but every occurrence agreed
        # on the value (e.g. restated in a summary and a detail table) --
        # still exactly one candidate VALUE, not an ambiguity.
        return candidates[0], None
    return candidates[0], None


def parse_filing_document(text: str, *, receipt_no: str) -> dict:
    """Every `FIELD_LABELS` entry, conservatively extracted from `text`.

    Returns a dict with one entry per field: `{"value": ..., "reason":
    ...}` -- `value` is `None` whenever extraction was not unambiguous, and
    `reason` says why. The validation flag covers observed real table
    patterns only; it does not establish final economics or execution.
    """
    structure = document_structure(text)
    fields = {}
    for field_name, labels in FIELD_LABELS.items():
        value, reason = extract_labeled_value(text, labels)
        fields[field_name] = {"value": value, "reason": reason}
    return {
        "receiptNo": receipt_no,
        "structure": structure,
        "fields": fields,
        "parserValidationStatus": PARSER_VALIDATION_STATUS,
    }


class _Document(HTMLParser):
    """Small tolerant XML/HTML reader; no external entities or network access."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.tables = []
        self.next_table = 0
        self.row = None
        self.cell = None
        self.parts = []
        self.issuer = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "company-name":
            self.issuer = attrs.get("aregciK".lower())
        if tag == "table":
            self.tables.append(self.next_table)
            self.next_table += 1
        if tag == "tr":
            self.row = {"cells": [], "table": self.tables[-1] if self.tables else -1}
        if tag in {"td", "th", "te", "tu"} and self.row is not None:
            self.cell = []
        if tag in {"p", "br", "title", "tr"}:
            self.handle_data("\n")

    def handle_endtag(self, tag):
        if tag in {"td", "th", "te", "tu"} and self.cell is not None:
            if self.row is not None:
                self.row["cells"].append(" ".join("".join(self.cell).replace("&cr;", " ").split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.row["rowIndex"] = len(self.rows)
            self.rows.append(self.row)
            self.row = None
        if tag == "table" and self.tables:
            self.tables.pop()
        if tag in {"p", "br", "tr", "title"}:
            self.handle_data("\n")

    def handle_data(self, data):
        self.parts.append(data)
        if self.cell is not None:
            self.cell.append(data)


def document_structure(text: str) -> dict:
    parser = _Document()
    parser.feed(text)
    corrections = {row["table"] for row in parser.rows
                   if "정정전" in "".join(row["cells"]).replace(" ", "")
                   and "정정후" in "".join(row["cells"]).replace(" ", "")}
    for row in parser.rows:
        row["isCorrectionTable"] = row["table"] in corrections
    return {"rows": parser.rows, "text": "".join(parser.parts).replace("&cr;", " "),
            "issuerCorpCode": parser.issuer}


def labeled_rows(structure: dict, label: str) -> list[dict]:
    """Exact row-label matches, excluding before/after correction tables."""
    def normalized(value):
        return re.sub(r"^\d+\.", "", re.sub(r"\s+", "", value))
    return [row for row in structure["rows"] if row["cells"]
            and not row["isCorrectionTable"]
            and normalized(row["cells"][0]) == normalized(label)]


def korean_date(value: str) -> str | None:
    match = re.fullmatch(r"\s*(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})\s*일?\.?\s*", value)
    if not match:
        return None
    try:
        return date(*map(int, match.groups())).isoformat()
    except ValueError:
        return None


def cash_instead_of_stock(value: str) -> float | None:
    """Ignore a valuation ratio when the actual consideration is cash."""
    if "현금교부형" not in value or "신주 발행에 갈음" not in value:
        return None
    amounts = set(re.findall(r"(?:1주당|주당)\s*현금\s*([\d,]+)원", value))
    return float(amounts.pop().replace(",", "")) if len(amounts) == 1 else None
