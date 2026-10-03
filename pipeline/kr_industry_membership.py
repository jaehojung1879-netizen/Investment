"""KR dated industry source admission and coverage only; no outcome inputs."""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from .industry_foundation import Membership, day, membership_at, membership_identity, verify_source
from .regional_alpha_features import MembershipSnapshots, weekly_grid

CONTRACT = 'KR_INDUSTRY_MEMBERSHIP_FOUNDATION_V1'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def admit_assignment(candidate, raw, proof_sources):
    gates = {
        'OFFICIAL_DATED_ASSIGNMENT_REQUIRED': candidate.get('source_kind') in {'KRX_DATED_ASSIGNMENT', 'DART_CONTEMPORANEOUS_ASSIGNMENT'},
        'SUBJECT_SECURITY_ASSIGNMENT_REQUIRED': candidate.get('subject_scope') == 'SUBJECT_SECURITY',
        'EXACT_DATED_IDENTITY_REQUIRED': candidate.get('identity_status') == 'EXACT_DATED_SECURITY_ISSUER',
    }
    failures = [key for key, passed in gates.items() if not passed]
    if failures:
        return None, failures
    if candidate.get('industry_id') in {None, '', 'UNKNOWN', 'UNRESOLVED'}:
        return None, ['EXPLICIT_INDUSTRY_ASSIGNMENT_REQUIRED']
    for key in ('identity_provenance', 'taxonomy_version_evidence', 'economic_interval_evidence', 'release_date_evidence', 'codebook_evidence'):
        proof = candidate.get(key)
        if not isinstance(proof, dict) or not proof.get('source_sha256') or not proof.get('locator'):
            return None, ['RETAINED_EVIDENCE_REFERENCE_REQUIRED:' + key]
        source = proof_sources.get(proof['source_sha256'])
        if not isinstance(source, bytes) or sha256(source) != proof['source_sha256']:
            return None, ['EVIDENCE_SOURCE_MISSING_OR_CHANGED:' + key]
        encoding = proof.get('encoding', 'utf-8')
        if encoding not in {'utf-8', 'euc-kr', 'cp949'}:
            return None, ['UNSUPPORTED_EVIDENCE_ENCODING:' + key]
        try:
            locator = proof['locator'].encode(encoding)
        except (AttributeError, UnicodeError):
            return None, ['INVALID_EVIDENCE_LOCATOR:' + key]
        if source.count(locator) != 1:
            return None, ['EVIDENCE_LOCATOR_NOT_UNIQUE:' + key]
    try:
        values = {key: candidate[key] for key in Membership.__dataclass_fields__}
        values['identity_provenance'] = json.dumps(candidate['identity_provenance'], sort_keys=True)
        row = Membership(**values)
    except (KeyError, TypeError, ValueError) as exc:
        return None, ['INVALID_MEMBERSHIP_CONTRACT:' + type(exc).__name__]
    if row.region != 'KR' or row.security_id != 'KRX:' + row.ticker:
        return None, ['KR_SECURITY_IDENTITY_MISMATCH']
    if row.evidence_kind != 'DATED_ASSIGNMENT':
        return None, ['CURRENT_CLASSIFICATION_BACKFILL_REFUSED']
    verify_source(row, raw)
    return row, []


def resolve(rows, security_id, signal_date, taxonomy_id):
    matches = []
    for version in sorted({r.taxonomy_version for r in rows if r.taxonomy_id == taxonomy_id}):
        try:
            row = membership_at(rows, security_id, signal_date, region='KR', taxonomy_id=taxonomy_id, taxonomy_version=version)
        except ValueError:
            return None, 'AMBIGUOUS_PIT_MEMBERSHIP'
        if row is not None:
            matches.append(row)
    if len(matches) > 1:
        return None, 'CONFLICTING_TAXONOMY_VERSIONS'
    return (matches[0], None) if matches else (None, 'UNKNOWN')


def top120_schedule(inputs, start='2015-01-01', through='2026-09-14'):
    snapshots = inputs['snapshots']
    if not snapshots or len({s['date'] for s in snapshots}) != len(snapshots):
        raise ValueError('INVALID_TOP120_SNAPSHOTS')
    for snapshot in snapshots:
        day(snapshot['date'])
        if len(snapshot['members']) != 120 or len(set(snapshot['members'])) != 120:
            raise ValueError('FULL_TOP120_DENOMINATOR_REQUIRED')
    view, schedule, provenance = MembershipSnapshots(snapshots), {}, {}
    for stamp in weekly_grid(start, through, 'KR'):
        snapshot = view.on(stamp)
        if snapshot is None:
            raise ValueError('STRICTLY_PRIOR_UNIVERSE_MISSING')
        schedule[stamp] = ['KRX:' + ticker for ticker in sorted(snapshot['members'])]
        provenance[stamp] = snapshot['date']
    return schedule, provenance


def coverage(rows, schedule, taxonomy_id, criteria):
    rows = tuple(rows)
    dates, annual, previous, switches = [], {}, {}, []
    continuous = repeated = 0
    for stamp, names in sorted(schedule.items()):
        day(stamp)
        if not names or len(set(names)) != len(names):
            raise ValueError('INVALID_FULL_PIT_UNIVERSE')
        current, reasons, groups = {}, {}, Counter()
        for name in sorted(names):
            row, reason = resolve(rows, name, stamp, taxonomy_id)
            if row is None:
                reasons[name] = reason
            else:
                current[name] = (row.taxonomy_version, row.industry_id)
                groups[current[name]] += 1
        pairs = set(names) & set(previous)
        repeated += len(pairs)
        continuous += sum(previous[n] is not None and n in current for n in pairs)
        for n in sorted(pairs):
            if previous[n] is not None and n in current and previous[n] != current[n]:
                switches.append({'date': stamp, 'security_id': n, 'from': list(previous[n]), 'to': list(current[n])})
        sufficient = {k: v for k, v in groups.items() if v >= criteria['minimumConstituentsPerGroup']}
        classified = len(current)
        entry = {'date': stamp, 'universeCount': len(names), 'classifiedCount': classified,
                 'coverageFraction': classified / len(names), 'missingSecurityIds': sorted(reasons), 'missingReasons': reasons,
                 'groupCounts': [{'taxonomy_version': k[0], 'industry_id': k[1], 'count': v} for k, v in sorted(groups.items())],
                 'sufficientGroupCount': len(sufficient),
                 'classifiedFractionInSufficientGroups': sum(sufficient.values()) / classified if classified else None}
        dates.append(entry)
        record = annual.setdefault(stamp[:4], {'year': stamp[:4], 'signalDates': 0, 'universeNameDates': 0,
                                               'classifiedNameDates': 0, 'missingSecurityIds': set(), 'universeSecurityIds': set(),
                                               'minimumSignalDateCoverageFraction': 1.0})
        record['signalDates'] += 1
        record['universeNameDates'] += len(names)
        record['classifiedNameDates'] += classified
        record['missingSecurityIds'].update(reasons)
        record['universeSecurityIds'].update(names)
        record['minimumSignalDateCoverageFraction'] = min(record['minimumSignalDateCoverageFraction'], entry['coverageFraction'])
        previous = {n: current.get(n) for n in names}
    for record in annual.values():
        record['coverageFraction'] = record['classifiedNameDates'] / record['universeNameDates']
        record['uniqueUniverseSecurities'] = len(record.pop('universeSecurityIds'))
        record['missingSecurityIds'] = sorted(record['missingSecurityIds'])
    continuity = continuous / repeated if repeated else None
    failures = []
    if not dates:
        failures.append('EMPTY_SIGNAL_CALENDAR')
    if any(d['coverageFraction'] < criteria['minimumSignalDateCoverageFraction'] for d in dates):
        failures.append('SIGNAL_DATE_COVERAGE_BELOW_FLOOR')
    if any(r['coverageFraction'] < criteria['minimumAnnualNameDateCoverageFraction'] for r in annual.values()):
        failures.append('ANNUAL_COVERAGE_BELOW_FLOOR')
    if continuity is None or continuity < criteria['minimumAdjacentNameDateContinuityFraction']:
        failures.append('CONTINUITY_BELOW_FLOOR')
    if any(d['sufficientGroupCount'] < criteria['minimumSufficientGroupsPerSignalDate'] or
           d['classifiedFractionInSufficientGroups'] is None or
           d['classifiedFractionInSufficientGroups'] < criteria['minimumClassifiedFractionInSufficientGroupsPerSignalDate'] for d in dates):
        failures.append('GROUP_SIZE_OR_GROUP_COVERAGE_BELOW_FLOOR')
    return {'taxonomy_id': taxonomy_id, 'membershipSha256': membership_identity(rows), 'dates': dates,
            'annual': list(annual.values()), 'repeatedUniverseNameDatePairs': repeated,
            'classifiedAdjacentNameDatePairs': continuous, 'adjacentContinuityFraction': continuity,
            'observedAssignmentChanges': switches, 'failedCriteria': failures,
            'decision': 'DATA_FOUNDATION_INSUFFICIENT' if failures else 'READY_FOR_INDUSTRY_ANATOMY'}


def select_taxonomy(audits, criteria):
    by_id = {a['taxonomy_id']: a for a in audits}
    for taxonomy in criteria['candidateTaxonomiesInPriorityOrder']:
        if by_id[taxonomy]['decision'] == 'READY_FOR_INDUSTRY_ANATOMY':
            return taxonomy
    return None


def mapping_document(rows, criteria_sha256):
    return {'contract': CONTRACT, 'criteriaSha256': criteria_sha256, 'membershipSha256': membership_identity(rows),
            'memberships': sorted((asdict(r) for r in rows), key=lambda r: json.dumps(r, sort_keys=True)),
            'unknownPolicy': 'Absent mapping is UNKNOWN; never an inferred industry or removed denominator',
            'historicalOutcomeComputed': False, 'modelFitPerformed': False}
