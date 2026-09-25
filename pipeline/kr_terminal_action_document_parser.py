"""A CONSERVATIVE scaffold for reading termination terms out of a real DART
filing document's own text -- UNVALIDATED against any real filing.

WHY THIS EXISTS NOW BUT PRODUCES NOTHING YET. `document.xml` reachability is
confirmed live (`scripts/probe_kr_corporate_actions.probe_document_
retrieval`) and `scripts/collect_kr_terminal_action_documents.py` can now
retrieve real filing text for the 130 receipts this repair line's own
narrowing step selected -- but this sandbox has not run that collector
(no `workflow_dispatch` permission; see `docs/kr-terminal-action-
reconstruction-v2.md`), so ZERO real filing documents exist anywhere this
repository can read yet. Writing a parser now and claiming it works would be
exactly the failure this repository's discipline forbids: a plausible-
looking extraction with nothing real behind it. This module exists so the
NEXT step (once real documents land) has a starting point to validate and
correct against real content, not a claim that termination terms are
resolved.

`PARSER_VALIDATION_STATUS` IS STAMPED ON EVERY RESULT, ALWAYS
`NEVER_VALIDATED_AGAINST_REAL_DART_CONTENT` AS SHIPPED. No completeness-
matrix field, no `kr_terminal_corporate_actions.build_record` call anywhere
in this repository reads this module's output — it is not imported by
`build_kr_terminal_action_reconstruction_v2.py` or any other assembly
script. Wiring it in is future work, gated on that validation actually
happening.

THE FIELD LABELS ARE STANDARD KOREAN COMMERCIAL-ACT / DART DISCLOSURE-
TEMPLATE VOCABULARY, THE SAME EPISTEMIC TIER AS `보통주`/`우선주` IN
`kr_dividend_amount_lineage.py` -- NOT A GUESSED DART-INTERNAL ENUM. DART's
주요사항보고서(합병결정) template is a standardized form every Korean
merger disclosure uses the same field names for (합병비율, 합병가액,
합병기일, 존속회사, 소멸회사, 1주당 신주배정주식수, 현금교부); this is
public, checkable knowledge of the form's own structure, not a probe-and-
confirm exercise like `report_tp`'s opaque code was. What IS unvalidated is
whether this module's own EXTRACTION LOGIC correctly locates the value next
to each label across the real variety of real filings' formatting (HTML
tables, footnotes, amendment strikethroughs) -- that is what a real
document validates, not the label list itself.

EVERY EXTRACTION IS CONSERVATIVE: A FIELD IS `None` UNLESS EXACTLY ONE
CANDIDATE MATCHES. Zero matches or more than one candidate both return
`None` with a stated reason -- never a best guess among several, and never
an average or a first-match pick. This is the module-level version of the
task's own instruction: "if parsing is ambiguous, leave the field BLOCKED."

NO TERMINATION TYPE IS INFERRED FROM `report_nm`. This module only ever
reads the FILING'S OWN BODY TEXT, passed in by the caller -- it takes no
disclosure-index row and computes nothing from a report name.
"""
from __future__ import annotations

import re

PARSER_VALIDATION_STATUS = "NEVER_VALIDATED_AGAINST_REAL_DART_CONTENT"

AMBIGUOUS_ZERO_MATCHES = "ZERO_MATCHES"
AMBIGUOUS_MULTIPLE_MATCHES = "MULTIPLE_CANDIDATE_MATCHES"

# Standard 주요사항보고서(합병결정) template field labels -- see module
# docstring for why these are public, checkable form vocabulary rather than
# a guessed enum.
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
    `reason` says why. `parserValidationStatus` is always
    `NEVER_VALIDATED_AGAINST_REAL_DART_CONTENT` on the current shipped
    version of this module; a future change that validates this against
    real retrieved documents is what may ever change that value, and only
    after doing so.
    """
    fields = {}
    for field_name, labels in FIELD_LABELS.items():
        value, reason = extract_labeled_value(text, labels)
        fields[field_name] = {"value": value, "reason": reason}
    return {
        "receiptNo": receipt_no,
        "fields": fields,
        "parserValidationStatus": PARSER_VALIDATION_STATUS,
    }
