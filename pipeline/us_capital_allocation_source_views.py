"""Candidate source-repair VIEWS of a filing record. Analysis only; the frozen v1 feature meaning is never touched.

PR #220's `US_SHAREHOLDER_DISTRIBUTION_V1` admits exactly four concepts and treats a related-but-different concept as
`AMBIGUOUS_ACCOUNTING` (e.g. `PaymentsOfDividends` is not `PaymentsOfDividendsCommonStock`). That is the safe reading and it
stays. This module asks a different question, WITHOUT changing v1: if a NEW versioned definition accepted a documented, narrower
set of filing contexts, how many filings, and therefore how many weekly member-dates, would become measurable?

A view returns a COPY of a raw filing record in which the v1 concept is injected only when the filing's own statements document
that the broader concept has the v1 meaning. It never fills a missing value with zero and never infers a buyback or a dividend
from an ambiguous tag. Each decision carries a reason code so the accepted and rejected contexts are countable.

What a view CANNOT establish: Finnhub's flattened statements carry the face line item (concept, label, unit, value), not the XBRL
dimensional context of the fact. Whether a general tag excludes preferred or non-controlling holders is therefore inferred from the
filing's other face lines and from its labels, which is evidence, not verification. Every view is labelled
`STORE_EVIDENCE_NOT_CONTEXT_VERIFIED` until the SEC XBRL instance can be read (blocked in this environment).
"""
from __future__ import annotations

import copy
import re

from pipeline import finnhub_fundamentals as FF

EVIDENCE_LABEL = "STORE_EVIDENCE_NOT_CONTEXT_VERIFIED"
CANDIDATE_VERSION = "US_SHAREHOLDER_DISTRIBUTION_V2_CANDIDATE_VIEW"

EXACT_DIVIDEND = "PaymentsOfDividendsCommonStock"
GENERAL_DIVIDEND = "PaymentsOfDividends"
ORDINARY_DIVIDEND = "PaymentsOfOrdinaryDividends"
EXACT_OCF = "NetCashProvidedByUsedInOperatingActivities"
CONTINUING_OCF = "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"

_OTHER_HOLDER = re.compile(r"preferred|noncontrolling|non-controlling|minority|subsidiar|unitholder|partner|limited partner|redeemable", re.I)
_PREFERRED_CONCEPT = re.compile(r"preferred", re.I)
_DISCONTINUED = re.compile(r"discontinued", re.I)

DIVIDEND_ACCEPT = "ALIAS_ACCEPTED_NO_OTHER_HOLDER_EVIDENCE"
DIVIDEND_REASONS = (
    "EXACT_CONCEPT_PRESENT", DIVIDEND_ACCEPT, "REJECT_OTHER_HOLDER_DIVIDEND_LINE", "REJECT_OTHER_HOLDER_LABEL",
    "REJECT_PREFERRED_STOCK_OUTSTANDING", "REJECT_CONFLICTING_GENERAL_CONCEPTS", "REJECT_ORDINARY_ONLY_EXCLUDES_SPECIAL_DIVIDENDS",
    "NO_DIVIDEND_CONCEPT_IN_CASH_FLOW",
)
OCF_ACCEPT = "ALIAS_ACCEPTED_NO_DISCONTINUED_OPERATIONS_LINE"
OCF_REASONS = ("EXACT_CONCEPT_PRESENT", OCF_ACCEPT, "REJECT_DISCONTINUED_OPERATIONS_LINE", "NO_OPERATING_CASH_FLOW_CONCEPT")


def _rows(record, section):
    return list((record.get("statements") or {}).get(section) or [])


def _named(rows, name):
    return [r for r in rows if FF.strip_namespace(r.get("concept")) == name]


def _numeric(row):
    value = row.get("value")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _preferred_outstanding(record) -> bool:
    """A preferred-stock line with a non-zero value on ANY face statement."""
    for section in ("bs", "ic", "cf"):
        for row in _rows(record, section):
            if _PREFERRED_CONCEPT.search(FF.strip_namespace(row.get("concept")) or "") and "ividend" not in (row.get("concept") or "") \
                    and _numeric(row) not in (None, 0.0):
                return True
    return False


def dividend_decision(record) -> str:
    """Reason code for how a filing's cash dividends would be read under the candidate definition."""
    cf = _rows(record, "cf")
    if _named(cf, EXACT_DIVIDEND):
        return "EXACT_CONCEPT_PRESENT"
    general, ordinary = _named(cf, GENERAL_DIVIDEND), _named(cf, ORDINARY_DIVIDEND)
    if not general and not ordinary:
        return "NO_DIVIDEND_CONCEPT_IN_CASH_FLOW"
    if any("ividend" in (FF.strip_namespace(r.get("concept")) or "") and _OTHER_HOLDER.search(FF.strip_namespace(r.get("concept")) or "")
           for r in cf):
        return "REJECT_OTHER_HOLDER_DIVIDEND_LINE"
    if general and ordinary:
        values = {_numeric(r) for r in general + ordinary}
        if len(values) > 1:
            return "REJECT_CONFLICTING_GENERAL_CONCEPTS"
    if not general:
        # `PaymentsOfOrdinaryDividends` is the recurring dividend and leaves special dividends to another concept: it would
        # understate a company's total cash distribution, so it is not accepted as the common-stock total.
        return "REJECT_ORDINARY_ONLY_EXCLUDES_SPECIAL_DIVIDENDS"
    if any(_OTHER_HOLDER.search(str(r.get("label") or "")) for r in general):
        return "REJECT_OTHER_HOLDER_LABEL"
    if _preferred_outstanding(record):
        return "REJECT_PREFERRED_STOCK_OUTSTANDING"
    return DIVIDEND_ACCEPT


def ocf_decision(record) -> str:
    cf = _rows(record, "cf")
    if _named(cf, EXACT_OCF):
        return "EXACT_CONCEPT_PRESENT"
    if not _named(cf, CONTINUING_OCF):
        return "NO_OPERATING_CASH_FLOW_CONCEPT"
    if any(_DISCONTINUED.search(FF.strip_namespace(r.get("concept")) or "") and "OperatingActivities" in (r.get("concept") or "") for r in cf):
        return "REJECT_DISCONTINUED_OPERATIONS_LINE"
    return OCF_ACCEPT


def _inject(record, alias_name, target_name):
    out = copy.deepcopy(record)
    source = _named(_rows(out, "cf"), alias_name)[0]
    prefix = (source.get("concept") or "").rsplit("_", 1)[0] + "_" if "_" in (source.get("concept") or "") else ""
    out["statements"]["cf"].append({"concept": prefix + target_name, "label": "[view] " + str(source.get("label") or ""),
                                    "unit": source.get("unit"), "value": source.get("value"), "viewOf": alias_name})
    return out


def candidate_view(record, *, dividends: bool = True, ocf: bool = True):
    """(record copy, {'dividends': code, 'ocf': code}). The input is never mutated; nothing is injected unless accepted."""
    codes = {"dividends": dividend_decision(record), "ocf": ocf_decision(record)}
    out = record
    if dividends and codes["dividends"] == DIVIDEND_ACCEPT:
        out = _inject(out, GENERAL_DIVIDEND, EXACT_DIVIDEND)
    if ocf and codes["ocf"] == OCF_ACCEPT:
        out = _inject(out, CONTINUING_OCF, EXACT_OCF)
    return out, codes
