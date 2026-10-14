"""Outcome-free US_MF1_DATASET_ADMISSION_V1: dates/evidence only, no price levels.

One publisher per security. Endpoint checks inspect observation EXISTENCE only.
Independent gate counts must not be confused with cumulative admission counts.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json

VERSION = 'US_DEPARTED_DATASET_ADMISSION_AUDIT_V1'
STATUSES = ('ADMITTED', 'IDENTITY_HOLD', 'NAME_ONLY', 'BASIS_UNRESOLVED', 'QUALITY_UNRESOLVED', 'NO_OBSERVATION')
SOURCE_PRIORITY = ('F', 'D', 'A', 'E')  # fixed accounting preference, never tuned on outcomes
BASIS_CLASSES = {'A': 'BACK_ADJUSTED', 'D': 'ORIGINAL_CLOSE_SEPARATE_ADJUSTED_CLOSE',
                 'F': 'ORIGINAL_CLOSE_SEPARATE_ADJUSTED_CLOSE', 'E': 'ROUNDED_ADJUSTMENT_UNKNOWN'}
GATES = ('AD2_IDENTITY', 'AD3_SINGLE_BASIS', 'AD4_LINEAGE', 'AD5_TERMINAL',
         'AD6_FUNDAMENTALS_LINK', 'DATED_MEMBERSHIP', 'SOURCE_PROVENANCE')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def cited(item):
    """An explicit evidence identity is necessary; a bare success boolean is not."""
    return isinstance(item, dict) and bool(item.get('citation')) and len(str(item.get('sha256', ''))) == 64 and all(
        c in '0123456789abcdef' for c in str(item.get('sha256', '')))


def cik(value):
    return str(value or '').lstrip('0')


def filing_visible(record, day, member_cik):
    """Conservative daily rule: strictly after BOTH publication and acceptance."""
    available, accepted = record.get('availableFrom'), record.get('acceptedDate')
    if not available or not accepted or not member_cik or cik(record.get('cik')) != cik(member_cik):
        return False
    try:
        parsed = [datetime.fromisoformat(str(value).replace('Z', '+00:00')).date().isoformat()
                  for value in (available, accepted)]
    except ValueError:
        return False
    return max(parsed) < day


def endpoint_status(day, observed_days, calendar, terminal=None, horizon=63, last_observation=None):
    """No quote/return/payoff reader; no last-quote or zero-value completion."""
    start = bisect_left(calendar, day)
    if start == len(calendar) or calendar[start] != day or start + horizon >= len(calendar):
        return 'UNRESOLVED_CALENDAR'
    window = calendar[start + 1:start + horizon + 1]
    last = last_observation or (max(observed_days) if observed_days else None)
    if last is None or window[-1] > last:
        if (last is not None and cited(terminal) and terminal.get('verified') is True
                and terminal.get('kind') in {'CASH', 'SHARE_EXCHANGE', 'ZERO_CONFIRMED'}
                and terminal.get('lastTradingDate') == last
                and last < str(terminal.get('eventDate', '')) <= window[-1]
                and all(d in observed_days for d in window if d <= last)):
            return 'TERMINAL_CITED'  # consideration verification metadata, never an invented payoff
        return 'UNRESOLVED_PAST_LAST_OBSERVATION'
    if any(d not in observed_days for d in window):
        return 'UNRESOLVED_OBSERVATION_GAP'
    return 'OBSERVATION_EXISTS'


def identity_on(evidence, day):
    dates = evidence.get('identityDates', [])
    pos = bisect_left(dates, day) - 1  # snapshots strictly earlier, no future CIK backfill
    if pos < 0:
        return {}
    item = evidence['identityRecords'][pos]
    if item.get('kind') not in {'FILING_CIK', 'PREVIOUSLY_ANNOTATION', 'IDENTICAL_NAME_AT_SWITCH'} or not cited(item):
        return {}
    if item.get('issuerVerified') is not True or item.get('shareClassVerified') is not True:
        return {}
    return item


def audit_sessions(expected, candidates, evidence, calendar, *, horizon=63):
    """Input: security->expected dates, date->separate publisher set, explicit evidence.

    Output tables contain identifiers/dates/statuses/provenance, NEVER prices or payoffs.
    Inputs must be checksum-verified by the acquisition adapter before this function.
    """
    if calendar != sorted(set(calendar)):
        raise ValueError('INVALID_SESSION_CALENDAR')
    statuses, independent, cumulative, annual = Counter(), Counter(), Counter(), defaultdict(Counter)
    basis_counts, per_identifier, tables, endpoints = Counter(), [], [], Counter()
    recovered = 0
    quote_windows = Counter()
    for ticker in sorted(expected):
        item = evidence[ticker]
        if item.get('seriesSources') and len(set(item['seriesSources'])) != 1:
            raise ValueError('INCOMPATIBLE_PRICE_BASIS_SPLICE')
        if any(day not in expected[ticker] for day in candidates.get(ticker, {})):
            raise ValueError('OBSERVATION_OUTSIDE_DATED_MEMBERSHIP')
        dates = item.get('identityDates', [])
        if dates != sorted(set(dates)) or len(dates) != len(item.get('identityRecords', [])):
            raise ValueError('INVALID_DATED_IDENTITY_TIMELINE')
        sources = {s for value in candidates.get(ticker, {}).values() for s in value}
        selected = next((s for s in SOURCE_PRIORITY if s in sources), None)
        if item.get('selectedSource') and item['selectedSource'] != selected:
            raise ValueError('DECLARED_PUBLISHER_MISMATCH')
        observed = set(item.get('rawObservedDays', {}).get(selected, []))
        last_observation = max(observed) if observed else None
        member_days = set(item.get('memberDays', expected[ticker]))
        matched_filings = defaultdict(list)
        for f in item.get('filings', []):
            if not f.get('availableFrom') or not f.get('acceptedDate'):
                continue
            try:
                visible = max(datetime.fromisoformat(str(f[k]).replace('Z', '+00:00')).date().isoformat()
                              for k in ('availableFrom', 'acceptedDate'))
            except ValueError:
                continue
            matched_filings[cik(f.get('cik'))].append((visible, f['id']))
        filing_dates = {key: sorted(values) for key, values in matched_filings.items()}
        local, local_gates, local_endpoints = Counter(), Counter(), Counter()
        for day in sorted(expected[ticker]):
            quotes = candidates.get(ticker, {}).get(day, set())
            candidate = bool(quotes)
            recovered += candidate
            year = day[:4]
            annual[year]['originalMissing'] += 1
            annual[year]['candidateRecovered'] += candidate
            identity = identity_on(item, day)
            member_cik = cik(identity.get('cik'))
            linked = filing_dates.get(member_cik, []) if member_cik else []
            filing_pos = bisect_left(linked, (day, '')) - 1  # visible day excluded
            filing_id = linked[filing_pos][1] if filing_pos >= 0 else None
            source_present = bool(selected in quotes) if selected else False
            lineage = item.get('lineage', {})
            basis_evidence = item.get('basisEvidence', {}).get(selected, {})
            lineage_pass = (cited(lineage) and lineage.get('verified') is True
                            and lineage.get('source') == selected and lineage.get('adjustedLevelCheck') == 'PASS'
                            and lineage.get('completeEventSearch') is True
                            and isinstance(lineage.get('events'), list)
                            and all(cited(e) and e.get('kind') in {'SPLIT', 'DISTRIBUTION'}
                                    and str(lineage.get('from', '~')) <= str(e.get('date', '')) <= str(lineage.get('through', ''))
                                    and cik(e.get('cik')) == member_cik for e in lineage['events'])
                            and str(lineage.get('from', '~')) <= day <= str(lineage.get('through', '')))
            terminal = item.get('terminal', {})
            if terminal and (cik(terminal.get('cik')) != member_cik or terminal.get('source') != selected):
                terminal = None
            quote_window = endpoint_status(day, observed, calendar, terminal, horizon, last_observation) if candidate else 'NO_START_OBSERVATION'
            endpoint = 'UNRESOLVED_FIXED_PUBLISHER_START_GAP' if candidate and not source_present else quote_window
            gates = {'AD2_IDENTITY': bool(identity) and not item.get('identityHold', False),
                     'AD3_SINGLE_BASIS': source_present and selected in {'D', 'F'}
                        and cited(basis_evidence) and basis_evidence.get('verified') is True
                        and basis_evidence.get('classification') in {'AS_TRADED', 'RECONSTRUCTED_AS_TRADED'},
                     'AD4_LINEAGE': bool(lineage_pass),
                     'AD5_TERMINAL': endpoint in {'OBSERVATION_EXISTS', 'TERMINAL_CITED'},
                     'AD6_FUNDAMENTALS_LINK': bool(member_cik and filing_id),
                     'DATED_MEMBERSHIP': day in member_days,
                     'SOURCE_PROVENANCE': source_present and cited(item.get('provenance', {}).get(selected))}
            if not candidate:
                status = 'NO_OBSERVATION'
            elif item.get('identityHold'):
                status = 'IDENTITY_HOLD'
            elif not gates['AD2_IDENTITY']:
                status = 'NAME_ONLY'
            elif not gates['AD3_SINGLE_BASIS']:
                status = 'BASIS_UNRESOLVED'
            elif not all(gates.values()):
                status = 'QUALITY_UNRESOLVED'
            else:
                status = 'ADMITTED'
            statuses[status] += 1;local[status] += 1;annual[year][status] += 1
            if candidate:
                endpoints[endpoint] += 1;local_endpoints[endpoint] += 1;annual[year][endpoint] += 1
                quote_windows[quote_window] += 1
                annual[year]['pastLastObservationWindows'] += quote_window == 'UNRESOLVED_PAST_LAST_OBSERVATION'
                basis = BASIS_CLASSES.get(selected, 'NONE') if source_present else 'FIXED_PUBLISHER_GAP_NO_SPLICE'
                basis_counts[basis] += 1
                passed = True
                for gate in GATES:
                    independent[gate] += bool(gates[gate]);local_gates[gate] += bool(gates[gate])
                    passed = passed and gates[gate]
                    cumulative[gate] += bool(passed)
            tables.append({'securityId': item['securityId'], 'ticker': ticker, 'date': day, 'status': status,
                           'selectedPublisher': selected, 'selectedPublisherPresent': source_present,
                           'basis': BASIS_CLASSES.get(selected, 'NONE'), 'endpointStatus': endpoint, 'quoteWindowExistenceStatusIgnoringStartGap': quote_window,
                           'issuerCik': member_cik or None, 'filingId': filing_id,
                           'failedGates': [g for g in GATES if not gates[g]],
                           'sourceSha256': item.get('provenance', {}).get(selected, {}).get('sha256')})
        per_identifier.append({'ticker': ticker, 'securityId': item['securityId'], 'selectedPublisher': selected,
                               'statusCounts': dict(sorted(local.items())), 'independentGatePass': dict(local_gates),
                               'endpointCounts': dict(local_endpoints), 'identityHold': bool(item.get('identityHold')),
                               'filingCiks': sorted(filing_dates), 'filingRecords': len(item.get('filings', []))})
    total = sum(len(days) for days in expected.values())
    if sum(statuses.values()) != total or recovered + statuses['NO_OBSERVATION'] != total:
        raise ValueError('SESSION_ACCOUNTING_MISMATCH')
    report = {'version': VERSION, 'originalMissingSessions': total, 'candidateRecoveredSessions': recovered,
              'statusCounts': {s: statuses[s] for s in STATUSES}, 'finalAdmittedSessions': statuses['ADMITTED'],
              'independentGatePass': {g: independent[g] for g in GATES},
              'cumulativeGatePass': {g: cumulative[g] for g in GATES},
              'basisCountsByCandidateSession': dict(sorted(basis_counts.items())),
              'candidateEndpointCounts': dict(sorted(endpoints.items())),
              'quoteWindowExistenceCountsIgnoringStartGap': dict(sorted(quote_windows.items())), 'horizonSessionsExistenceOnly': horizon,
              'annual': {str(y): {**dict(sorted(annual[str(y)].items())),
                        **{status: annual[str(y)][status] for status in STATUSES},
                        'pastLastObservationWindows': annual[str(y)]['pastLastObservationWindows']}
                         for y in range(2013, 2027)},
              'identifiers': per_identifier, 'incompatibleBasisSplices': 0,
              'accessCounters': {'forwardOutcomes': 0, 'labels': 0, 'models': 0, 'portfolios': 0},
              'sessionTableSha256': digest(canonical(tables)),
              'highestValueBlocker': 'Verified dated issuer/share-class and split/dividend lineage for D/F candidates; never more ticker-only prices'}
    return report, tables
