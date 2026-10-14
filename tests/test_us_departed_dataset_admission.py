"""Synthetic admission fixtures only; no real prices, outcomes or authorizations."""
import ast
import copy
import gzip
import json
from pathlib import Path

import pytest

from pipeline import us_departed_dataset_admission as A
from scripts import audit_us_departed_dataset_admission as C

DAYS = ['2013-01-02', '2013-01-03', '2013-01-04', '2013-01-07', '2013-01-08', '2013-01-09']
CITE = {'citation': 'https://example.invalid/SYNTHETIC', 'sha256': 'a' * 64}


def fixture():
    expected = {'TEST': set(DAYS[:2])}
    candidates = {'TEST': {day: {'F'} for day in DAYS[:2]}}
    evidence = {'TEST': {'securityId': 'SYNTHETIC_SECURITY', 'identityHold': False,
        'identityDates': ['2013-01-01'], 'identityRecords': [{**CITE, 'kind': 'FILING_CIK', 'cik': '123',
            'issuerVerified': True, 'shareClassVerified': True}],
        'rawObservedDays': {'F': DAYS}, 'provenance': {'F': CITE},
        'basisEvidence': {'F': {**CITE, 'verified': True, 'classification': 'AS_TRADED'}},
        'lineage': {**CITE, 'verified': True, 'source': 'F', 'adjustedLevelCheck': 'PASS',
                    'from': '2013-01-01', 'through': DAYS[-1], 'completeEventSearch': True, 'events': []},
        'filings': [{'id': 'SYNTHETIC_FILING', 'cik': '123', 'availableFrom': '2012-12-31',
                    'acceptedDate': '2012-12-31 20:00:00'}]}}
    return expected, candidates, evidence


def run(values):
    return A.audit_sessions(*values, DAYS, horizon=2)


def test_explicit_synthetic_evidence_admits_and_reruns_identically():
    values = fixture();before = copy.deepcopy(values)
    report, table = run(values)
    assert report['finalAdmittedSessions'] == 2
    assert report['statusCounts']['ADMITTED'] == 2
    assert all(report['independentGatePass'][g] == 2 for g in A.GATES)
    assert report['accessCounters'] == {'forwardOutcomes': 0, 'labels': 0, 'models': 0, 'portfolios': 0}
    assert A.canonical(run(values)) == A.canonical((report, table))
    assert values == before
    assert not any(key in table[0] for key in ('close', 'volume', 'payoff', 'return'))


@pytest.mark.parametrize('defect,status', [('identity_hold', 'IDENTITY_HOLD'), ('name_only', 'NAME_ONLY'),
    ('basis_unknown', 'BASIS_UNRESOLVED'), ('lineage_missing', 'QUALITY_UNRESOLVED'),
    ('wrong_cik', 'QUALITY_UNRESOLVED'), ('share_class_unknown', 'NAME_ONLY'),
    ('uncited_identity', 'NAME_ONLY'), ('empty_cik', 'QUALITY_UNRESOLVED')])
def test_no_positive_observation_can_override_missing_evidence(defect, status):
    values = fixture();e = values[2]['TEST']
    if defect == 'identity_hold': e['identityHold'] = True
    if defect == 'name_only': e['identityRecords'][0]['kind'] = 'MEMBERSHIP_CIK_NOT_VERIFIED_PRICE_ISSUER_LINK'
    if defect == 'basis_unknown': e['basisEvidence'] = {}
    if defect == 'lineage_missing': e['lineage'] = {}
    if defect == 'wrong_cik': e['filings'][0]['cik'] = '456'
    if defect == 'share_class_unknown': e['identityRecords'][0]['shareClassVerified'] = False
    if defect == 'uncited_identity': e['identityRecords'][0].pop('citation')
    if defect == 'empty_cik': e['identityRecords'][0]['cik'] = None
    report, _ = run(values)
    assert report['statusCounts'][status] == 2
    assert report['finalAdmittedSessions'] == 0


def test_missing_observation_not_zero_or_fabricated():
    values = fixture();values[1]['TEST'].pop(DAYS[1])
    report, table = run(values)
    assert report['candidateRecoveredSessions'] == 1
    assert report['statusCounts']['NO_OBSERVATION'] == 1
    assert sum(report['statusCounts'].values()) == 2
    assert table[1]['endpointStatus'] == 'NO_START_OBSERVATION'


def test_strict_publication_and_acceptance_and_delayed_amendment():
    values = fixture();f = values[2]['TEST']['filings'][0]
    f['availableFrom'] = '2013-01-01';f['acceptedDate'] = '2013-01-02 09:00:00'
    report, table = run(values)
    assert report['finalAdmittedSessions'] == 1
    assert table[0]['filingId'] is None and table[1]['filingId'] == 'SYNTHETIC_FILING'
    values[2]['TEST']['filings'].append({**f, 'id': 'FUTURE_AMENDMENT', 'availableFrom': '2026-10-14', 'acceptedDate': '2026-10-14'})
    later_report, later_table = run(values)
    assert A.canonical(later_table) == A.canonical(table)
    assert later_report['independentGatePass'] == report['independentGatePass']
    assert later_report['finalAdmittedSessions'] == report['finalAdmittedSessions']
    assert A.filing_visible(f, DAYS[0], '000123') is False
    assert A.filing_visible(f, DAYS[1], '000123') is True
    assert A.filing_visible(f, DAYS[1], '456') is False


def test_future_member_cik_not_backfilled():
    values = fixture();values[2]['TEST']['identityDates'] = ['2023-04-13']
    report, _ = run(values)
    assert report['statusCounts']['NAME_ONLY'] == 2
    assert report['independentGatePass']['AD6_FUNDAMENTALS_LINK'] == 0


def test_one_publisher_fixed_across_gaps_no_splice():
    values = fixture();values[1]['TEST'][DAYS[1]] = {'A'}
    values[2]['TEST']['rawObservedDays']['F'] = [d for d in DAYS if d != DAYS[1]]
    report, table = run(values)
    assert table[1]['selectedPublisher'] == 'F' and table[1]['selectedPublisherPresent'] is False
    assert table[1]['status'] == 'BASIS_UNRESOLVED'
    assert report['incompatibleBasisSplices'] == 0
    values[2]['TEST']['seriesSources'] = ['F', 'A']
    with pytest.raises(ValueError, match='INCOMPATIBLE_PRICE_BASIS_SPLICE'): run(values)


@pytest.mark.parametrize('source', ['A', 'E'])
def test_back_adjusted_or_rounded_not_relabelled_as_traded(source):
    values = fixture();e = values[2]['TEST']
    values[1]['TEST'] = {d: {source} for d in DAYS[:2]}
    e['basisEvidence'][source] = e['basisEvidence']['F'];e['rawObservedDays'][source] = DAYS
    e['provenance'][source] = CITE
    report, _ = run(values)
    assert report['statusCounts']['BASIS_UNRESOLVED'] == 2


def test_terminal_last_quote_never_payoff_and_horizon_is_existence_only():
    observed = set(DAYS[:3])
    assert A.endpoint_status(DAYS[1], observed, DAYS, horizon=2) == 'UNRESOLVED_PAST_LAST_OBSERVATION'
    assert A.endpoint_status(DAYS[0], set(DAYS) - {DAYS[1]}, DAYS, horizon=2) == 'UNRESOLVED_OBSERVATION_GAP'
    assert A.endpoint_status(DAYS[-1], set(DAYS), DAYS, horizon=2) == 'UNRESOLVED_CALENDAR'
    terminal = {**CITE, 'verified': True, 'kind': 'CASH', 'lastTradingDate': DAYS[2], 'eventDate': DAYS[3]}
    assert A.endpoint_status(DAYS[1], observed, DAYS, terminal, 2) == 'TERMINAL_CITED'
    terminal['citation'] = ''
    assert A.endpoint_status(DAYS[1], observed, DAYS, terminal, 2).startswith('UNRESOLVED')
    assert A.endpoint_status(DAYS[1], set(), DAYS, terminal, 2).startswith('UNRESOLVED')


def test_uncited_or_wrong_issuer_split_event_blocks_lineage():
    values = fixture();values[2]['TEST']['lineage']['events'] = [{'kind': 'SPLIT', 'date': DAYS[0], 'cik': '123'}]
    assert run(values)[0]['independentGatePass']['AD4_LINEAGE'] == 0
    values[2]['TEST']['lineage']['events'] = [{**CITE, 'kind': 'SPLIT', 'date': DAYS[0], 'cik': '456'}]
    assert run(values)[0]['independentGatePass']['AD4_LINEAGE'] == 0


def test_data_unavailable_never_fetches_or_fabricates(monkeypatch, tmp_path):
    monkeypatch.setattr(C.subprocess, 'check_output', lambda *_args, **_kwargs: pytest.fail('no Git/outcome read permitted'))
    report, table = C.build(tmp_path)
    assert report['dataState'] == 'DATA_UNAVAILABLE'
    assert report['finalAdmittedSessions'] is None and report['measuredGateCounts'] is None and table is None
    assert report['historicalReportedBaselineNotRemeasured']['candidateRecoveredSessions'] == 186910


def test_local_checksum_failure_stops_before_filing_reads(tmp_path):
    manifest = {'raw': {'externalFilename': 'raw.gz', 'bytes': 1, 'sha256': 'a' * 64}}
    (tmp_path / 'raw.gz').write_bytes(b'x')
    with pytest.raises(ValueError, match='CHECKSUM_MISMATCH'): C.verify_local_artifacts(tmp_path, manifest)


def test_private_table_refuses_git_and_overwrite(tmp_path):
    checkout = tmp_path / 'repo';checkout.mkdir();(checkout / '.git').mkdir();(checkout / '.git/HEAD').write_text('ref: refs/heads/test')
    with pytest.raises(ValueError, match='OUTSIDE_GIT_CHECKOUT'): C.write_private_table(checkout / 'table.gz', [])
    path = tmp_path / 'table.gz';C.write_private_table(path, [])
    assert json.loads(gzip.decompress(path.read_bytes())) == []
    with pytest.raises(FileExistsError): C.write_private_table(path, [])


def test_outcome_spy_and_import_boundary(monkeypatch):
    monkeypatch.setattr(C, 'read_filing_metadata', lambda: pytest.fail('engine must not call adapter'))
    monkeypatch.setattr(C.subprocess, 'check_output', lambda *_args, **_kwargs: pytest.fail('no external/outcome API'))
    report, _ = run(fixture())
    assert all(v == 0 for v in report['accessCounters'].values())
    allowed = {'__future__', 'bisect', 'collections', 'datetime', 'hashlib', 'json'}
    imports = {node.module.split('.')[0] for node in ast.walk(ast.parse(Path(A.__file__).read_text()))
               if isinstance(node, ast.ImportFrom)}
    imports |= {n.name.split('.')[0] for node in ast.walk(ast.parse(Path(A.__file__).read_text()))
                if isinstance(node, ast.Import) for n in node.names}
    assert imports <= allowed
    cli = Path(C.__file__).read_text()
    assert 'git fetch' not in cli and 'git push' not in cli
    assert 'refs/tags/' not in cli and 'ledger/historical/' not in cli


def test_outside_membership_or_unsorted_identity_refused():
    values = fixture();values[1]['TEST'][DAYS[3]] = {'F'}
    with pytest.raises(ValueError, match='OUTSIDE_DATED_MEMBERSHIP'): run(values)
    values = fixture();values[2]['TEST']['identityDates'].append('2012-01-01')
    values[2]['TEST']['identityRecords'].append(values[2]['TEST']['identityRecords'][0])
    with pytest.raises(ValueError, match='INVALID_DATED_IDENTITY_TIMELINE'): run(values)


def test_missing_acceptance_and_invalid_hash_are_not_permission_to_admit():
    values = fixture();values[2]['TEST']['filings'][0]['acceptedDate'] = None
    assert run(values)[0]['finalAdmittedSessions'] == 0
    assert A.cited({'citation': 'SYNTHETIC', 'sha256': 'x' * 64}) is False


def test_conflicting_same_day_issuer_evidence_never_picks_a_cik():
    identity = {'rows': [['TEST', 'Old issuer', '123'], ['TEST', 'New issuer', '456']],
                'snapshots': [{'date': '2013-01-01', 'rows': [0], 'rawCsvSha256': 'a' * 64},
                              {'date': '2013-01-01', 'rows': [1], 'rawCsvSha256': 'b' * 64}]}
    dates, records = C.identity_evidence({'auditIdentifier': 'TEST'}, identity)
    assert dates == ['2013-01-01']
    assert records[0]['cik'] is None and records[0]['kind'] == 'AMBIGUOUS_SAME_DAY_MEMBER_IDENTITY'
    assert len(records[0]['coincidentSourceSha256s']) == 2


def test_filing_adapter_reads_only_fixed_metadata_objects(monkeypatch):
    import hashlib
    raw = gzip.compress(json.dumps({'ticker': 'TEST', 'id': 'MOCK', 'cik': '123',
        'availableFrom': '2013-01-01', 'acceptedDate': '2013-01-01', 'source': 'finnhub/financials-reported',
        'statements': {'mustNotEnterAdmission': 'SYNTHETIC'}}).encode(), mtime=0)
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    path = 'ledger/fundamentals/us/finnhub-2013.jsonl.gz'
    calls = []
    def read(command, **kwargs):
        calls.append(command)
        if command[:3] == ['git', 'ls-tree', '-r']:
            return ('100644 blob ' + blob + '\t' + path + '\n').encode()
        assert command == ['git', 'show', C.FUNDAMENTALS_COMMIT + ':' + path]
        return raw
    monkeypatch.setattr(C.subprocess, 'check_output', read)
    grouped, files, state = C.read_filing_metadata()
    assert state == 'VERIFIED_PINNED_METADATA_ONLY' and files[0]['gitBlob'] == blob
    assert 'statements' not in grouped['TEST'][0]
    assert len(calls) == 2 and calls[0][3] == C.FUNDAMENTALS_COMMIT


def test_fixed_publisher_start_gap_is_unresolved_even_if_endpoint_exists():
    values = fixture();values[1]['TEST'][DAYS[0]] = {'A'}
    report, table = run(values)
    assert table[0]['endpointStatus'] == 'UNRESOLVED_FIXED_PUBLISHER_START_GAP'
    assert table[0]['quoteWindowExistenceStatusIgnoringStartGap'] == 'OBSERVATION_EXISTS'
    assert report['independentGatePass']['AD5_TERMINAL'] == 1


def test_published_real_aggregate_is_not_a_synthetic_admission_claim():
    report = json.loads((C.ROOT / 'docs/us-readiness/us-departed-dataset-admission-audit-v1.json').read_bytes())
    assert report['dataState'] == 'EXACT_LOCAL_BYTES_VERIFIED'
    assert report['originalMissingSessions'] == 256402
    assert report['candidateRecoveredSessions'] == 186910
    assert report['finalAdmittedSessions'] == 0 and report['datasetGateVerdict'] == 'NOT_ADMITTED'
    assert sum(report['statusCounts'].values()) == 256402
    assert report['statusCounts']['NO_OBSERVATION'] == 69492
    assert report['basisIdentifierCounts'] == {'HAS_D_OR_F': 59, 'A_ONLY': 113, 'E_ONLY': 3}
    assert report['inputManifestSha256'] == A.digest(A.canonical(report['inputManifest']))
    assert len(report['identifiers']) == 212 and len(report['annual']) == 14
    assert sum(y['candidateRecovered'] for y in report['annual'].values()) == 186910
    assert all(y['ADMITTED'] == 0 and y['residualNoAdmittedWeeklyPct'] == y['beforeWeeklyPct']
               for y in report['annual'].values())
    assert all(report['annual'][str(y)]['candidateWindowUnresolvedPct'] is None for y in (2024, 2025, 2026))
    assert all(v == 0 for v in report['accessCounters'].values())
    assert all(not value['usableForMultifactorOutcomeTest'] for value in report['factorFamilyUse'].values())
    # Only provenance/counts: no per-session price values in the public output.
    forbidden = {'close', 'adjClose', 'open', 'high', 'low', 'volume', 'payoff', 'forwardReturn'}
    def inspect(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values(): inspect(child)
        elif isinstance(value, list):
            for child in value: inspect(child)
    inspect(report)
