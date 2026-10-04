"""Offline v3 reconstruction and structural audit from retained bytes only (no network, no outcomes)."""
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
from pipeline import kr_industry_membership_v3 as V  # noqa: E402
from pipeline.kr_industry_membership import top120_schedule  # noqa: E402
from scripts.collect_kr_industry_v3_notices import frozen as frozen_notice_plan  # noqa: E402

D1 = 'data/kr-industry-membership-foundation-v1'
D3 = 'data/kr-industry-membership-foundation-v3'
ANCHOR_SHA = 'e67bc8d33c47c0013d6e31bfc62897d049ad6fadac9013261c8bc100a4380d58'
LISTING_WINDOWS = [('2013-01-01', '2015-12-31'), ('2016-01-01', '2018-12-31'), ('2019-01-01', '2021-12-31'), ('2022-01-01', '2024-12-31'), ('2025-01-01', '2026-10-02')]


def read(root, path):
    return json.loads((root / path).read_text())


def notice_events(root, candidates):
    state = read(root, D3 + '/notices/state.json')
    events, refused = [], Counter()
    for cand in candidates['candidates']:
        record = state.get(cand['receipt_no'])
        if not record or record['status'] != 'SERVED':
            refused['DOCUMENT_NOT_SERVED'] += 1
            continue
        viewer = record['responses'][0]
        doc = next(m for m in record['responses'] if m.get('stage') == 'document' and m.get('status') == 200)
        parsed = V.parse_notice(V.decode((root / D3 / 'notices' / (doc['sha256'] + '.bin')).read_bytes())[0],
                                V.decode((root / D3 / 'notices' / (viewer['sha256'] + '.bin')).read_bytes())[0])
        if parsed['status'] != 'PARSED':
            refused[parsed['reason']] += 1
            continue
        tickers = [t for t in cand['candidate_securities'] if t.split('.')[0] == parsed['identity']['stock_code']]
        if len(tickers) != 1:
            refused['STATED_STOCK_CODE_NOT_A_CANDIDATE'] += 1
            continue
        events.append(dict(parsed, ticker=tickers[0], receipt_no=cand['receipt_no'], notice_date=cand['listing_time'][:10],
                           viewer_sha256=viewer['sha256'], document_sha256=doc['sha256'], document_url=doc['url'],
                           requested_at=doc['requestedAt'], source_lineage='KIND disclsviewer header + searchContents + document'))
    return events, dict(refused)


def build(root=ROOT):
    root = Path(root)
    candidates, protocol = frozen_notice_plan()
    criteria = read(root, 'research_specs/kr-industry-membership-foundation-v2/criteria.json')
    anchor_raw = (root / D3 / 'probe/run-37170219625' / (ANCHOR_SHA + '.bin')).read_bytes()
    if V.digest(anchor_raw) != ANCHOR_SHA:
        raise ValueError('CURRENT_ANCHOR_CHANGED')
    anchor_rows = V.parse_current_state(anchor_raw, '2026-10-04')['rows']
    anchor_labels, anchor_conflicts = V.anchor_map(anchor_rows)
    anchor = {k: {'industry_label': v} for k, v in anchor_labels.items()}
    inputs = read(root, D1 + '/top120-inputs.json')
    schedule, _ = top120_schedule(inputs)
    identity = read(root, D1 + '/identity-inventory.json')
    terminal_ids = set(read(root, D1 + '/identity-provenance.json')['terminalSecurities'])
    ends = {s['securityId']: s['delisted'] for i in identity['issuers'] for s in i['securities'] if s['ticker'] in terminal_ids and s.get('delisted')}
    events, refused = notice_events(root, candidates)
    v2_obs = json.loads(gzip.decompress((root / 'data/kr-industry-membership-foundation-v2/state/observations.json.gz').read_bytes()))
    by_ticker = {}
    for e in events:
        by_ticker.setdefault(e['ticker'], []).append(e)
    securities = sorted(inputs['securities'])
    intervals, conflicts = {}, Counter()
    for ticker in securities:
        code = ticker.split('.')[0]
        label = anchor[code]['industry_label'] if code in anchor else None
        intervals[ticker] = V.reconstruct_intervals(label, by_ticker.get(ticker, []))
        conflicts.update(iv['reason'] for iv in intervals[ticker] if iv['status'] == 'CONFLICT')
    dates, annual, terminal, status_counts, groups_seen = [], {}, Counter(), Counter(), Counter()
    pit_known = 0
    for stamp, names in sorted(schedule.items()):
        if len(names) != 120 or len(set(names)) != 120:
            raise ValueError('EXACT_REUSED_TOP120_DENOMINATOR_REQUIRED')
        groups, unknown = Counter(), []
        for name in names:
            ticker = name[4:]
            end = ends.get(name)
            label = status = None
            if end and stamp >= end:
                status = 'UNKNOWN_IDENTITY_TERMINATED'
            else:
                iv = V.label_at(intervals[ticker], stamp)
                if iv and iv['label']:
                    label, status = 'KIND:' + ''.join(iv['label'].split()), iv['status']
                    if iv['status'] == 'VERIFIED_KRX_KIND_CHANGE_EVENT' and iv.get('start') and iv.get('notice_date') and iv['notice_date'] < stamp:
                        pit_known += 1
                elif ticker.split('.')[0] not in anchor:
                    fallback, _ = V2.state_at(v2_obs, name, stamp, end)
                    if fallback:
                        label, status = 'DART:' + fallback['group_id'], 'RETAINED_DART_FALLBACK'
                if label is None and status is None:
                    status = 'CONFLICT' if iv and iv['status'] == 'CONFLICT' else 'UNKNOWN'
            if label:
                groups[label] += 1
            else:
                unknown.append({'security_id': name, 'status': status})
            status_counts[status] += 1
            if name in ends:
                terminal['denominator'] += 1
                terminal['classified'] += label is not None
        n = sum(groups.values())
        adequate = {k: v for k, v in groups.items() if v >= criteria['minimumGroupSize']}
        groups_seen.update(groups.keys())
        dates.append({'date': stamp, 'classified': n, 'coveragePct': n / 120 * 100, 'groupCount': len(groups),
                      'sufficientGroupCount': len(adequate), 'fractionInSufficientGroups': sum(adequate.values()) / n if n else None,
                      'groupSizes': sorted(groups.values(), reverse=True)})
        y = annual.setdefault(stamp[:4], {'denominator': 0, 'classified': 0})
        y['denominator'] += 120
        y['classified'] += n
    for y in annual.values():
        y['coveragePct'] = y['classified'] / y['denominator'] * 100
    cov = [d['coveragePct'] for d in dates]
    sizes = [s for d in dates for s in d['groupSizes']]
    per_count = Counter(len(by_ticker.get(t, [])) if len(by_ticker.get(t, [])) < 2 else 2 for t in securities)
    gates = {
        'signalCoverage': all(c / 100 >= criteria['minimumSignalCoverage'] for c in cov),
        'annualCoverage': all(y['coveragePct'] / 100 >= criteria['minimumAnnualCoverage'] for y in annual.values()),
        'terminalCoverage': bool(terminal['denominator']) and terminal['classified'] / terminal['denominator'] >= criteria['minimumTerminalCoverage'],
        'minimumSufficientGroups': all(d['sufficientGroupCount'] >= criteria['minimumSufficientGroups'] for d in dates),
        'fractionInSufficientGroups': all((d['fractionInSufficientGroups'] or 0) >= criteria['minimumFractionInSufficientGroups'] for d in dates)}
    total = len(dates) * 120
    classified = sum(d['classified'] for d in dates)
    audit = {
        'contract': 'KR_INDUSTRY_MEMBERSHIP_FOUNDATION_V3_AUDIT', 'decision': 'READY_FOR_INDUSTRY_ANATOMY' if all(gates.values()) else 'DATA_FOUNDATION_INSUFFICIENT_V3',
        'gates': gates, 'thresholds': {k: criteria[k] for k in ('minimumSignalCoverage', 'minimumAnnualCoverage', 'minimumTerminalCoverage', 'minimumGroupSize', 'minimumSufficientGroups', 'minimumFractionInSufficientGroups')},
        'everTop120Securities': len(securities), 'signalDates': len(dates), 'nameDates': total,
        'currentAnchor': {'tableRows': len(anchor_rows), 'distinctCodes': len(anchor), 'duplicateCodeLabelConflicts': anchor_conflicts, 'securitiesWithAnchor': sum(1 for t in securities if t.split('.')[0] in anchor),
                          'securitiesAbsent': sum(1 for t in securities if t.split('.')[0] not in anchor)},
        'candidateNotices': len(candidates['candidates']), 'noticeDocumentsFetched': sum(1 for r in read(root, D3 + '/notices/state.json').values() if r['status'] == 'SERVED'),
        'verifiedChangeEvents': len(events), 'refusedNotices': refused,
        'securitiesByChangeCount': {'0': per_count[0], '1': per_count[1], '2+': per_count[2]},
        'classifiedNameDates': classified, 'unknownNameDates': total - classified, 'classifiedPct': classified / total * 100,
        'nameDateStatus': dict(status_counts), 'pitKnownEventNameDates': pit_known,
        'annual': annual, 'signalCoveragePct': {'min': min(cov), 'median': statistics.median(cov), 'max': max(cov)},
        'terminal': dict(terminal), 'terminalCoveragePct': terminal['classified'] / terminal['denominator'] * 100 if terminal['denominator'] else None,
        'conflictIntervals': dict(conflicts), 'distinctGroups': len(groups_seen),
        'groupSize': {'min': min(sizes) if sizes else None, 'median': statistics.median(sizes) if sizes else None, 'max': max(sizes) if sizes else None},
        'datesWithAtLeastThreeSufficientGroups': sum(d['sufficientGroupCount'] >= 3 for d in dates),
        'unresolvedEventChains': sum(1 for t in securities if any(iv['status'] in ('CONFLICT',) for iv in intervals[t])),
        'stableInferenceBasis': {'listingWindows': LISTING_WINDOWS, 'listingRequests': read(root, D3 + '/events-rev4/manifest.json')['requests'],
                                  'limits': ['keyword 업종변경 only', 'name-based candidate discovery can miss a notice filed under a name absent from the universe record', 'reconstruction, never PIT_EXACT']},
        'taxonomy': 'Raw KIND labels preserved; KSIC edition not verified; not required for reconstruction (reported, not gated).',
        'historicalOutcomeComputed': False, 'protocolSha256': V.digest((ROOT / 'research_specs/kr-industry-membership-foundation-v3/notice-document-protocol-rev6.json').read_bytes())}
    return events, intervals, dates, audit


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--verify', action='store_true')
    a = p.parse_args()
    events, intervals, dates, audit = build()
    a.output.mkdir(parents=True, exist_ok=True)
    for name, value in (('events.json.gz', events), ('intervals.json.gz', intervals), ('audit.json.gz', audit)):
        raw = gzip.compress((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode(), mtime=0)
        path = a.output / name
        if a.verify:
            if path.read_bytes() != raw:
                raise ValueError('OFFLINE_REPRODUCTION_CHANGED:' + name)
        else:
            path.write_bytes(raw)
    print(json.dumps({k: audit[k] for k in ('decision', 'gates', 'currentAnchor', 'candidateNotices', 'noticeDocumentsFetched', 'verifiedChangeEvents', 'refusedNotices', 'securitiesByChangeCount', 'classifiedNameDates', 'unknownNameDates', 'classifiedPct', 'nameDateStatus', 'signalCoveragePct', 'terminal', 'conflictIntervals', 'distinctGroups', 'groupSize', 'datesWithAtLeastThreeSufficientGroups', 'unresolvedEventChains')}, ensure_ascii=False, indent=1))
