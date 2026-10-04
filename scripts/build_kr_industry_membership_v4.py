"""Offline v4 build: reuses the accepted v3 reconstruction unchanged, adds the frozen terminal rules and crosswalk."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_industry_membership_v2 as V2  # noqa: E402
from pipeline import kr_industry_membership_v3 as V3  # noqa: E402
from pipeline import kr_industry_membership_v4 as V4  # noqa: E402
from pipeline.kr_industry_membership import top120_schedule  # noqa: E402
from scripts import build_kr_industry_membership_v3 as B3  # noqa: E402

SPEC = ROOT / 'research_specs/kr-industry-membership-foundation-v4'
D1, D3 = B3.D1, B3.D3
DOMINANCE_LIMIT = 0.35


def frozen(name):
    raw = (SPEC / name).read_bytes()
    if V3.digest(raw) != (SPEC / (name + '.sha256')).read_text().strip():
        raise ValueError('UNFROZEN:' + name)
    return json.loads(raw)


def canonical(value):
    return gzip.compress((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode(), mtime=0)


def official_hierarchy(root):
    """Structured and free-text official codes from the retained, already-parsed notices."""
    state = json.loads((root / D3 / 'notices/state.json').read_text())
    structured, free_text, label_codes = [], [], {}
    for record in state.values():
        viewer = record['responses'][0]
        doc = next(m for m in record['responses'] if m.get('stage') == 'document')
        doc_html = V3.decode((root / D3 / 'notices' / (doc['sha256'] + '.bin')).read_bytes())[0]
        parsed = V3.parse_notice(doc_html, V3.decode((root / D3 / 'notices' / (viewer['sha256'] + '.bin')).read_bytes())[0])
        if parsed['status'] != 'PARSED':
            continue
        if parsed['format'] == 'STRUCTURED_FORM':
            for label, code in ((parsed['before_label'], parsed['before_code']), (parsed['after_label'], parsed['after_code'])):
                if label and code and len(code) == 6:
                    structured.append((label, code))
        else:
            free_text.extend(V4.hierarchy_from_text(doc_html))
    for label, code in structured:
        label_codes.setdefault(V4.norm(label), set()).add(code)
    for h in free_text:
        label_codes.setdefault(V4.norm(h['class_name']), set()).add(h['section_code'] + h['division_code'] + h['class_code'])
    return structured, free_text, label_codes


def build(root=ROOT):
    root = Path(root)
    protocol, crosswalk = frozen('protocol.json'), frozen('crosswalk.json')
    criteria = json.loads((root / 'research_specs/kr-industry-membership-foundation-v2/criteria.json').read_text())
    events3, intervals3, _, audit3 = B3.build(root)
    if canonical(audit3) != (root / D3 / 'state/audit.json.gz').read_bytes():
        raise ValueError('V3_RECONSTRUCTION_CHANGED')
    anchor_rows = V3.parse_current_state((root / D3 / 'probe/run-37170219625' / (B3.ANCHOR_SHA + '.bin')).read_bytes(), '2026-10-04')['rows']
    anchor_labels, _ = V3.anchor_map(anchor_rows)
    anchor_names = {r['ticker']: r['name'] for r in anchor_rows}
    inputs = json.loads((root / D1 / 'top120-inputs.json').read_text())
    schedule, _ = top120_schedule(inputs)
    identity = json.loads((root / D1 / 'identity-inventory.json').read_text())
    terminal_ids = set(json.loads((root / D1 / 'identity-provenance.json').read_text())['terminalSecurities'])
    ends = {s['securityId']: s['delisted'] for i in identity['issuers'] for s in i['securities'] if s['ticker'] in terminal_ids and s.get('delisted')}
    v2_obs = json.loads(gzip.decompress((root / 'data/kr-industry-membership-foundation-v2/state/observations.json.gz').read_bytes()))
    absent = protocol['absentSecurities']
    securities = sorted(inputs['securities'])
    # --- the 28 -------------------------------------------------------------
    parent, resolution = {}, {}
    for ticker in absent['nonTerminalPreferred6']:
        stem = V4.preferred_parent(ticker, inputs['securities'][ticker]['names'], anchor_labels, anchor_names)
        common = stem + '.KS' if stem else None
        if common and common in intervals3 and any(i['label'] for i in intervals3[common]):
            parent[ticker] = common
            resolution[ticker] = {'status': 'PREFERRED_SHARE_OF_ANCHORED_COMMON', 'common': common, 'common_name': anchor_names[stem]}
        else:
            resolution[ticker] = {'status': 'UNKNOWN', 'reason': 'PREFERRED_RULE_NOT_SATISFIED_OR_COMMON_NOT_RECONSTRUCTED'}
    retained_dart = {t: any(o['security_id'] == 'KRX:' + t for o in v2_obs) for t in absent['terminal22']}
    for ticker in absent['terminal22']:
        resolution[ticker] = ({'status': 'RETAINED_DART_FALLBACK'} if retained_dart[ticker] else
                              {'status': 'UNKNOWN', 'reason': 'NO_OFFICIAL_HISTORICAL_RECORD_AND_NO_ADMITTED_RETAINED_DART_OBSERVATION'})
    terminal_actions = json.loads((root / 'data/kr-terminal-corporate-actions.json').read_text())
    for action in terminal_actions['actions']:
        resolution.setdefault(action.get('oldSecurity') or action.get('security'), {})['terminalActionType'] = action['actionType'] if 'actionType' in action else None
    # --- official hierarchy proof ---------------------------------------------
    structured, free_text, label_codes = official_hierarchy(root)
    proof = V4.prove_code_structure(structured, free_text)
    raw_labels = sorted({V4.norm(i['label']) for v in intervals3.values() for i in v if i['label']})
    coded = [l for l in raw_labels if l in label_codes]
    official = {'codeStructureProof': proof, 'rawLabels': len(raw_labels), 'rawLabelsWithRetainedOfficialCode': len(coded),
                'rawLabelsWithoutCode': len(raw_labels) - len(coded),
                'divisionCandidate': 'FAILS_EVERY_RAW_LABEL_MUST_MAP' if len(coded) < len(raw_labels) else 'COMPLETE',
                'sectionCandidate': 'FAILS_EVERY_RAW_LABEL_MUST_MAP' if len(coded) < len(raw_labels) else 'COMPLETE'}
    unmapped = sorted(l for l in raw_labels if l not in crosswalk['mapping'])
    # --- name-date classification ---------------------------------------------
    dates, annual, terminal, status_counts, group_totals = [], {}, Counter(), Counter(), Counter()
    per_date, taxonomy_unknown, raw_seen = [], 0, set()
    classified_total = 0
    for stamp, names in sorted(schedule.items()):
        groups, n = Counter(), 0
        for name in names:
            ticker = name[4:]
            end = ends.get(name)
            label = status = None
            if end and stamp >= end:
                status = 'UNKNOWN_IDENTITY_TERMINATED'
            else:
                source = parent.get(ticker, ticker)
                iv = V3.label_at(intervals3[source], stamp)
                if iv and iv['label']:
                    label, status = iv['label'], ('PREFERRED_SHARE_OF_ANCHORED_COMMON' if ticker in parent else iv['status'])
                elif ticker.split('.')[0] not in anchor_labels and ticker not in parent:
                    fb, _ = V2.state_at(v2_obs, name, stamp, end)
                    if fb:
                        label, status = fb['group_id'].replace('LITERAL:', ''), 'RETAINED_DART_FALLBACK'
                if label is None and status is None:
                    status = 'CONFLICT' if iv and iv['status'] == 'CONFLICT' else 'UNKNOWN'
            group = V4.research_group(label, crosswalk) if label else None
            if label and group is None:
                taxonomy_unknown += 1
                status = 'UNKNOWN_TAXONOMY_UNMAPPED'
            if label:
                raw_seen.add(V4.norm(label))
            if group:
                groups[group] += 1
                n += 1
            status_counts[status] += 1
            if name in ends:
                terminal['denominator'] += 1
                terminal['classified'] += group is not None
        classified_total += n
        group_totals.update(groups)
        per_date.append(dict(groups))
        y = annual.setdefault(stamp[:4], {'denominator': 0, 'classified': 0})
        y['denominator'] += 120
        y['classified'] += n
        dates.append({'date': stamp, 'classified': n, 'coveragePct': n / 120 * 100})
    for y in annual.values():
        y['coveragePct'] = y['classified'] / y['denominator'] * 100
    total = len(dates) * 120
    struct = V4.structure(per_date, classified_total, criteria, DOMINANCE_LIMIT)
    cov = [d['coveragePct'] for d in dates]
    sizes = [s for g in per_date for s in g.values()]
    gates = {
        'signalCoverage': all(c / 100 >= criteria['minimumSignalCoverage'] for c in cov),
        'annualCoverage': all(y['coveragePct'] / 100 >= criteria['minimumAnnualCoverage'] for y in annual.values()),
        'terminalCoverage': bool(terminal['denominator']) and terminal['classified'] / terminal['denominator'] >= criteria['minimumTerminalCoverage'],
        'minimumSufficientGroups': struct['sufficientGroupsGate'], 'fractionInSufficientGroups': struct['fractionGate'],
        'taxonomyMappingComplete': not unmapped, 'taxonomyDominance': struct['dominanceGate']}
    resolved28 = sum(1 for r in resolution.values() if r.get('status') in ('PREFERRED_SHARE_OF_ANCHORED_COMMON', 'RETAINED_DART_FALLBACK', 'HISTORICAL_KRX_KIND_TERMINAL'))
    out_intervals = {}
    for ticker in securities:
        ivs = intervals3[parent.get(ticker, ticker)]
        out_intervals[ticker] = [dict(iv, raw_industry_name=iv['label'], raw_industry_code=(sorted(label_codes.get(V4.norm(iv['label']), [])) or None) if iv['label'] else None,
                                      research_industry_id=V4.research_group(iv['label'], crosswalk) if iv['label'] else None,
                                      research_industry_name=crosswalk['groups'].get(V4.research_group(iv['label'], crosswalk)) if iv['label'] else None,
                                      reconstruction_status='PREFERRED_SHARE_OF_ANCHORED_COMMON' if ticker in parent else iv['status']) for iv in ivs]
    audit = {
        'contract': V4.CONTRACT, 'decision': 'READY_FOR_INDUSTRY_ANATOMY' if all(gates.values()) else 'DATA_FOUNDATION_INSUFFICIENT_V4', 'gates': gates,
        'thresholds': dict(audit3['thresholds'], taxonomyDominanceLimit=DOMINANCE_LIMIT),
        'v3ReconstructionReusedUnchanged': True, 'everTop120Securities': len(securities), 'signalDates': len(dates), 'nameDates': total,
        'absent28': {'total': len(resolution) if False else 28, 'resolved': resolved28, 'unresolved': 28 - resolved28,
                     'preferredResolved': sum(1 for r in resolution.values() if r.get('status') == 'PREFERRED_SHARE_OF_ANCHORED_COMMON'),
                     'terminalResolved': sum(1 for t in absent['terminal22'] if resolution[t].get('status') != 'UNKNOWN'), 'perSecurity': resolution},
        'classifiedNameDates': classified_total, 'unknownNameDates': total - classified_total, 'classifiedPct': classified_total / total * 100,
        'nameDateStatus': dict(status_counts), 'taxonomyUnknownNameDates': taxonomy_unknown,
        'signalCoveragePct': {'min': min(cov), 'median': statistics.median(cov), 'max': max(cov)}, 'annual': annual,
        'terminal': dict(terminal), 'terminalCoveragePct': terminal['classified'] / terminal['denominator'] * 100,
        'rawIndustryCount': len(raw_seen), 'rawLabelsInTable': len(raw_labels), 'coarseIndustryCount': len(group_totals),
        'groupSize': {'min': min(sizes), 'median': statistics.median(sizes), 'max': max(sizes)},
        'fractionInSufficientGroups': {'min': min(d['fractionInSufficientGroups'] for d in struct['dates'] if d['fractionInSufficientGroups'] is not None),
                                       'datesBelowThreshold': sum(1 for d in struct['dates'] if (d['fractionInSufficientGroups'] or 0) < criteria['minimumFractionInSufficientGroups'])},
        'sufficientGroupsPerDate': {'min': min(d['sufficientGroupCount'] for d in struct['dates']), 'median': statistics.median(d['sufficientGroupCount'] for d in struct['dates']),
                                    'max': max(d['sufficientGroupCount'] for d in struct['dates'])},
        'topGroupShare': struct['topGroupShare'], 'groupTotals': dict(group_totals.most_common()),
        'conflictIntervals': audit3['conflictIntervals'], 'identityBreaksFromTerminalSet': len(ends), 'unmappedRawLabels': unmapped,
        'taxonomySelection': {'OFFICIAL_DIVISION': official['divisionCandidate'], 'OFFICIAL_SECTION': official['sectionCandidate'], 'officialEvidence': official,
                              'selected': 'ECONOMIC_CROSSWALK' if gates['taxonomyMappingComplete'] and gates['taxonomyDominance'] and gates['minimumSufficientGroups'] and gates['fractionInSufficientGroups'] else None},
        'taxonomyTemporalStability': 'Raw KSIC-edition renames map to the same group by frozen crosswalk (4 rename pairs).',
        'delistedRegisterProbe': 'search form only (시장구분, 회사명, 기간); no industry field observed; result columns not observed (single frozen request)',
        'historicalOutcomeComputed': False}
    return out_intervals, audit


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--verify', action='store_true')
    a = p.parse_args()
    intervals, audit = build()
    a.output.mkdir(parents=True, exist_ok=True)
    for name, value in (('intervals.json.gz', intervals), ('audit.json.gz', audit)):
        raw = canonical(value)
        path = a.output / name
        if a.verify:
            if path.read_bytes() != raw:
                raise ValueError('OFFLINE_REPRODUCTION_CHANGED:' + name)
        else:
            path.write_bytes(raw)
    print(json.dumps({k: audit[k] for k in audit if k not in ('annual', 'groupTotals', 'taxonomySelection')}, ensure_ascii=False, indent=1)[:6000])
    print(json.dumps(audit['taxonomySelection'], ensure_ascii=False, indent=1)[:2500]); print(audit['groupTotals'])
