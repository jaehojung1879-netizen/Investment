"""v4: preferred-share identity, official-hierarchy proof and the frozen economic crosswalk (outcome-free)."""
from __future__ import annotations
import re

from pipeline import kr_industry_membership_v3 as V3

CONTRACT = 'KR_INDUSTRY_MEMBERSHIP_FOUNDATION_V4'
PREFERRED_SUFFIX = re.compile(r'^(?P<stem>.+?)(?:[0-9]?우[A-C]?)$')


def norm(text):
    return ''.join((text or '').split())


def preferred_parent(ticker, names, anchor_labels, anchor_names):
    """Frozen rule: stem code is anchored AND recorded name = common KIND name + preferred suffix."""
    code = ticker.split('.')[0]
    stem = code[:5] + '0'
    if stem == code or stem not in anchor_labels:
        return None
    common = norm(anchor_names.get(stem))
    for name in names:
        match = PREFERRED_SUFFIX.match(norm(name))
        if match and common and match['stem'] == common:
            return stem
    return None


def hierarchy_from_text(text):
    """Explicit (대분류)(중분류)(소분류) names and codes in a free-text 업종변경 notice, or None."""
    flat = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text or ''))
    out = []
    for block in (re.search(r'변경\s*전\s*업종\s*및\s*코드(.*?)변경\s*후\s*업종', flat), re.search(r'변경\s*후\s*업종\s*및\s*코드(.*?)4\.\s*변경일', flat)):
        if not block:
            continue
        m = re.search(r'\(대분류\)\s*(.+?)\s*\((\d+)\)\s*\(중분류\)\s*(.+?)\s*\((\d+)\)\s*\(소분류\)\s*(.+?)\s*\((\d+)\)', block[1])
        if m:
            out.append({'section_name': m[1], 'section_code': m[2], 'division_name': m[3], 'division_code': m[4], 'class_name': m[5].strip(), 'class_code': m[6]})
    return out


def prove_code_structure(structured, free_text):
    """structured: [(label, 6-digit code)], free_text: hierarchy dicts. Official prefix semantics are accepted only if
    every label seen in both forms has code == section+division+class and at least five labels overlap."""
    by_label = {norm(h['class_name']): h['section_code'] + h['division_code'] + h['class_code'] for h in free_text}
    overlap = {norm(l): c for l, c in structured if norm(l) in by_label}
    agree = {l: by_label[l] == c for l, c in overlap.items()}
    return {'overlappingLabels': len(overlap), 'agreeing': sum(agree.values()), 'disagreeing': sorted(l for l, ok in agree.items() if not ok),
            'accepted': len(overlap) >= 5 and all(agree.values())}


def research_group(raw_label, crosswalk):
    return crosswalk['mapping'].get(norm(raw_label))


def structure(per_date_groups, classified_total, criteria, dominance_limit):
    """per_date_groups: list of {group: size}. Pure structural gates, nothing else."""
    dates = []
    totals = {}
    for groups in per_date_groups:
        n = sum(groups.values())
        adequate = {k: v for k, v in groups.items() if v >= criteria['minimumGroupSize']}
        dates.append({'classified': n, 'groups': len(groups), 'sufficientGroupCount': len(adequate),
                      'fractionInSufficientGroups': (sum(adequate.values()) / n) if n else None})
        for k, v in groups.items():
            totals[k] = totals.get(k, 0) + v
    top_share = max(totals.values()) / classified_total if totals and classified_total else None
    return {'dates': dates, 'topGroupShare': top_share,
            'sufficientGroupsGate': all(d['sufficientGroupCount'] >= criteria['minimumSufficientGroups'] for d in dates),
            'fractionGate': all((d['fractionInSufficientGroups'] or 0) >= criteria['minimumFractionInSufficientGroups'] for d in dates),
            'dominanceGate': top_share is not None and top_share <= dominance_limit}


__all__ = ['V3']
