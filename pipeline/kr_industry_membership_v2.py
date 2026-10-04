"""Outcome-free, bitemporal last-known-public issuer classification state.

Issuer observations and global taxonomy evidence are distinct objects. Unknown
rows remain in the original identity universe; a current map is not an input.
"""
from __future__ import annotations
from collections import Counter
from datetime import date
import hashlib

CONTRACT = 'KR_INDUSTRY_MEMBERSHIP_FOUNDATION_V2'
TIERS = ('KRX_DATED_NATIVE_CLASSIFICATION', 'DART_EXPLICIT_ISSUER_CLASSIFICATION',
         'DART_EXPLICIT_ISSUER_LABEL', 'CURRENT_ONLY_CROSSCHECK', 'UNKNOWN')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def admit(observation, sources, taxonomy):
    """Validate provenance without requiring a codebook in each issuer filing."""
    row = dict(observation)
    if row.get('evidence_tier') not in TIERS[:3]:
        return None, 'CURRENT_OR_UNKNOWN_NOT_HISTORICAL_EVIDENCE'
    if row.get('subject_scope') != 'ISSUER' or row.get('identity_status') != 'DATED_ISSUER_SECURITY':
        return None, 'ISSUER_IDENTITY_OR_SCOPE_UNPROVEN'
    for key in ('known_from',):
        try:
            date.fromisoformat(row[key])
        except (ValueError, KeyError, TypeError):
            return None, 'INVALID_BITEMPORAL_DATE'
    if row['security_id'] != 'KRX:' + row['ticker'] or not row.get('corpCode'):
        return None, 'INVALID_SECURITY_ISSUER_IDENTITY'
    for sha, locator in ((row.get('source_sha256'), row.get('source_locator')),
                         (row.get('identity_source_sha256'), row.get('identity_locator'))):
        raw = sources.get(sha)
        if not isinstance(raw, bytes) or digest(raw) != sha or not locator or raw.count(locator.encode('utf-8')) != 1:
            return None, 'SOURCE_LOCATOR_OR_HASH_UNPROVEN'
    if not row.get('reported_label'):
        return None, 'EXPLICIT_ISSUER_LABEL_REQUIRED'
    row['group_id'] = 'LITERAL:' + ''.join(row['reported_label'].split())
    row['standardized'] = False
    version = row.get('taxonomy_version')
    if version is not None:
        book = taxonomy.get(version)
        code = row.get('reported_code')
        if not book or book.get('status') != 'VERIFIED_OFFICIAL_CODEBOOK':
            return None, 'GLOBAL_TAXONOMY_EVIDENCE_UNPROVEN'
        for sha in (book.get('source_sha256'), book.get('effective_source_sha256')):
            if sha not in sources or digest(sources[sha]) != sha:
                return None, 'GLOBAL_TAXONOMY_SOURCE_MISSING'
        if not code or book['mapping'].get(code) != row['reported_label']:
            return None, 'AMBIGUOUS_TAXONOMY_MAPPING'
        row['group_id'] = version + ':' + code
        row['standardized'] = True
    # Versionless issuer codes are retained as reported, not guessed from prefix.
    return row, None


def state_at(observations, security_id, signal_date, terminated_at=None):
    stamp = date.fromisoformat(signal_date)
    if terminated_at and stamp >= date.fromisoformat(terminated_at):
        return None, 'IDENTITY_TERMINATED'
    visible = [r for r in observations if r['security_id'] == security_id
               and date.fromisoformat(r['known_from']) < stamp]
    if not visible:
        return None, 'UNKNOWN'
    # Evidence supersedes after release; choose hierarchy within the latest
    # public release cohort, never allow a stale higher tier to suppress change.
    latest = max(r['known_from'] for r in visible)
    cohort = [r for r in visible if r['known_from'] == latest]
    best = min(TIERS.index(r['evidence_tier']) for r in cohort)
    cohort = [r for r in cohort if TIERS.index(r['evidence_tier']) == best]
    if len({r['group_id'] for r in cohort}) != 1:
        return None, 'CONFLICTED_PUBLIC_STATE'
    row = min(cohort, key=lambda r: (r['receipt_no'], r['source_sha256']))
    return dict(row, classification_age_days=(stamp-date.fromisoformat(latest)).days), None


def audit(observations, schedule, criteria, terminations=None):
    terminations = terminations or {}
    dates, annual, terminal = [], {}, Counter()
    for stamp, names in sorted(schedule.items()):
        if len(names) != 120 or len(set(names)) != 120:
            raise ValueError('EXACT_REUSED_TOP120_DENOMINATOR_REQUIRED')
        tiers, groups, unknown, conflicts, ages, states = Counter(), Counter(), [], [], [], []
        for name in names:
            row, reason = state_at(observations, name, stamp, terminations.get(name))
            if row is None:
                unknown.append({'security_id': name, 'reason': reason})
                if reason == 'CONFLICTED_PUBLIC_STATE':
                    conflicts.append(name)
            else:
                tiers[row['evidence_tier']] += 1
                groups[row['group_id']] += 1
                ages.append(row['classification_age_days'])
                states.append({'security_id': name, 'receipt_no': row['receipt_no'], 'known_from': row['known_from'],
                               'source_sha256': row['source_sha256'], 'group_id': row['group_id'],
                               'evidence_tier': row['evidence_tier'], 'classification_age_days': row['classification_age_days'],
                               'standardized': row['standardized']})
            if name in terminations:
                terminal['denominator'] += 1
                terminal['classified'] += row is not None
        n = sum(tiers.values())
        adequate = {k:v for k,v in groups.items() if v >= criteria['minimumGroupSize']}
        entry = {'date': stamp, 'denominator':120, 'classified': n, 'UNKNOWN':unknown,
                 'coveragePct':n/120*100, 'tierCounts':dict(tiers), 'groupCounts':dict(groups),
                 'conflictedSecurityIds':conflicts, 'classificationAgeDays': sorted(ages),
                 'sufficientGroupCount':len(adequate), 'fractionInSufficientGroups':sum(adequate.values())/n if n else None,
                 'states': states}
        dates.append(entry)
        y=annual.setdefault(stamp[:4],{'denominator':0,'classified':0,'tierCounts':Counter()})
        y['denominator'] += 120
        y['classified'] += n
        y['tierCounts'].update(tiers)
    for y in annual.values():
        y['coveragePct']=y['classified']/y['denominator']*100
        y['tierCounts']=dict(y['tierCounts'])
    structural = all(d['coveragePct']/100 >= criteria['minimumSignalCoverage']
                     and d['sufficientGroupCount'] >= criteria['minimumSufficientGroups']
                     and (d['fractionInSufficientGroups'] or 0) >= criteria['minimumFractionInSufficientGroups'] for d in dates)
    standardized = bool(observations) and all(r['standardized'] for r in observations)
    terminal_fraction = terminal['classified']/terminal['denominator'] if terminal['denominator'] else None
    ready = structural and standardized and all(y['coveragePct']/100 >= criteria['minimumAnnualCoverage'] for y in annual.values()) and terminal_fraction is not None and terminal_fraction >= criteria['minimumTerminalCoverage']
    return {'contract': CONTRACT, 'object':'PIT_AVAILABLE_CLASSIFICATION_STATE', 'decision':'READY_FOR_INDUSTRY_ANATOMY' if ready else 'DATA_FOUNDATION_INSUFFICIENT_V2',
            'signalDates':len(dates),'nameDates':len(dates)*120,'dates':dates,'annual':annual,
            'terminalNameDates':dict(terminal),'terminalCoverageFraction':terminal_fraction,
            'admittedObservations':len(observations),'standardizedTaxonomyReady':standardized,
            'historicalOutcomeComputed':False}
