"""Title-level family reading list. Reuses #320's FAMILIES; adds three it lacks.

A title match only puts a filing on the reading list. Admission needs the
structured terms or the body (see ``events``), never the title alone.
"""
from __future__ import annotations

from ..filings import FAMILIES

EXTRA_FAMILIES = {
    'TRUST_TERMINATION': '자기주식취득신탁계약해지결정',
    'BW': '신주인수권부사채권발행결정',
    'CAPITAL_REDUCTION': '감자결정',
}

CAPITAL_ALLOCATION = ('BUYBACK', 'TRUST', 'TRUST_TERMINATION', 'CANCELLATION', 'DISPOSAL',
                      'RIGHTS', 'CB', 'EB', 'BW', 'CAPITAL_REDUCTION')
SUPPLY = ('SUPPLY', 'TERMINATION')


def compact(title: str) -> str:
    return (title or '').replace('ㆍ', '').replace('·', '').replace(' ', '')


def classify_title(title: str) -> str | None:
    text = compact(title)
    # Longest keyword first, so "신탁계약해지" never falls into a shorter family.
    words = {**FAMILIES, **EXTRA_FAMILIES}
    for family, word in sorted(words.items(), key=lambda kv: -len(kv[1])):
        if word in text:
            return family
    return None


def is_subsidiary_report(title: str) -> bool:
    text = compact(title)
    return '자회사의주요경영사항' in text or '종속회사의주요경영사항' in text or '(자회사' in text
