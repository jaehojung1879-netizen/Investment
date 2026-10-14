"""Synthetic quality/acquisition tests; no forward-return/research execution."""
import json
from pathlib import Path
import tarfile

import pytest

from pipeline import us_departed_price_recovery as R
from scripts import audit_us_departed_public_prices as A

DAYS = {'2013-01-02', '2013-01-03', '2013-01-04', '2013-01-28'}
HEADER = 'date,open,high,low,close,volume\n'


def test_real_schema_missing_zero_invalid_and_duplicates():
    data = HEADER + '2013-01-02,10,12,9,11,0\n2013-01-03,10,8,9,11,2\n2013-01-04,10,12,9,11,2\n2013-01-04,10,12,9,11,2\n'
    rows, quality = R.parse_csv(data.encode(), DAYS)
    assert list(rows) == ['2013-01-02']
    assert rows['2013-01-02']['volume'] == 0
    assert quality['zeroVolumeRows'] == 1
    assert quality['duplicateDates'] == ['2013-01-04']
    assert quality['invalidRows'][0]['reason'] == 'OHLC_INCONSISTENT'
    rows, _ = R.parse_csv(b'Date,Close\n2013-01-02,10\n', DAYS)
    assert rows['2013-01-02']['volume'] is None


@pytest.mark.parametrize('value', ['NaN', 'inf', '-1', '0'])
def test_invalid_close_not_counted(value):
    rows, _ = R.parse_csv(('Date,Close\n2013-01-02,' + value + '\n').encode(), DAYS)
    assert rows == {}


def test_html_not_data_and_ambiguous_dates_blocked():
    with pytest.raises(ValueError, match='NOT_A_DAILY'):
        R.parse_csv(b'<html>login</html>', DAYS)
    rows, q = R.parse_csv(b'Date,Close\n1/2/2013,10\n', DAYS)
    assert not rows and q['invalidRows'][0]['reason'] == 'AMBIGUOUS_SLASH_DATE_FORMAT'
    rows, q = R.parse_csv(b'Date,Close\n1/2/2013,10\n1/28/2013,11\n', DAYS)
    assert set(rows) == {'2013-01-02', '2013-01-28'} and q['dateFormat'] == 'CONFIRMED_US_MDY'


def test_exact_session_coverage_no_span_tolerance_or_forward_requirement():
    assert R.coverage_state(DAYS, DAYS)[0] == 'FULL'
    assert R.coverage_state(DAYS, {'2013-01-02'})[0] == 'PARTIAL'
    assert R.coverage_state(DAYS, {'2020-01-02'})[0] == 'NONE'
    assert R.coverage_state([], [])[0] == 'NONE'


def test_main_window_same_day_membership_not_backfilled():
    snapshots = [{'date': '2013-01-01', 'members': ['OLD']}, {'date': '2013-01-03', 'members': ['NEW']}]
    expected, _ = A.expected_members(snapshots, sorted(DAYS), ['OLD', 'NEW'])
    assert '2013-01-03' in expected['OLD'] and '2013-01-03' not in expected['NEW']
    assert '2013-01-04' in expected['NEW']


def test_deterministic_bounded_acquisition_stops_on_rate_limit(tmp_path):
    base = 'https://raw.githubusercontent.com/owner/repo/' + 'a' * 40 + '/'
    urls = [{'url': base + str(i) + '.csv'} for i in range(4)]
    calls = []
    def fetch(url):
        calls.append(url)
        return (200, b'Date,Close\n2013-01-02,10\n') if len(calls) == 1 else (429, b'stop')
    records = R.acquire(urls, tmp_path, fetch=fetch, sleep=lambda _: None, now=lambda: 'SYNTHETIC')
    assert len(calls) == 2 and records[-1]['status'] == 429
    assert (tmp_path / records[0]['object']).read_bytes().startswith(b'Date,Close')
    with pytest.raises(ValueError, match='MANIFEST_ALREADY_EXISTS'):
        R.acquire(urls, tmp_path, fetch=fetch)
    assert R.digest(R.canonical(json.loads((tmp_path / 'acquisition.json').read_text())))


def test_unpinned_url_refused_before_fetch(tmp_path):
    with pytest.raises(ValueError, match='UNPINNED'):
        R.acquire([{'url': 'https://raw.githubusercontent.com/a/b/main/x.csv'}], tmp_path, fetch=lambda _: pytest.fail('network'))


def test_shapes_only_not_blind_adjustment_or_returns():
    result = R.compare_levels({'2013-01-02': 10, '2013-01-03': 20}, {'2013-01-02': 5, '2013-01-03': 10})
    assert result['p95RelativeRatioDeviation'] == 0
    assert result['spliceAuthorized'] is False and result['independentProviderConfirmed'] is False


def test_archive_is_deterministic_and_immutable(tmp_path):
    raw = tmp_path / 'raw';raw.mkdir();(raw / 'x.csv').write_bytes(b'raw fixture')
    first, second = tmp_path / 'first.gz', tmp_path / 'second.gz'
    A.archive(raw, first);A.archive(raw, second)
    assert first.read_bytes() == second.read_bytes()
    with pytest.raises(FileExistsError): A.archive(raw, first)
    with tarfile.open(first) as handle:
        assert handle.extractfile('x.csv').read() == b'raw fixture'


def test_no_sealed_input_change_or_research_engine_dependency():
    source = Path(R.__file__).read_text()
    assert 'run_us_cash_profitability' not in source
    _, _, _, identifiers = A.inputs()
    assert len(identifiers) == 212
    # Outcome APIs are absent, not merely mocked with a live escape hatch.
    for token in ('read_outcomes(', 'forward_return(', 'fit(', 'signal-history/'):
        assert token not in source
    assert {'AGN', 'IGT', 'BTU', 'CHK'} <= R.IDENTITY_HOLDS


def test_changed_pinned_observation_is_preserved_but_never_auto_accepted(tmp_path):
    url = 'https://raw.githubusercontent.com/o/r/' + 'a' * 40 + '/x.csv'
    calls = []
    def fetch(value):
        calls.append(value);return 200, b'new revision bytes'
    records = R.acquire([{'url': url, 'expectedSha256': R.digest(b'old bytes')}, {'url': url}],
                        tmp_path, fetch=fetch, sleep=lambda _: None)
    assert len(calls) == 1 and records[0]['revisionMismatch'] is True
    assert (tmp_path / records[0]['object']).read_bytes() == b'new revision bytes'



def test_public_store_is_metadata_only_and_measured_findings_unchanged():
    store = A.ROOT / 'candidate_data/us-departed-public-price-v1'
    manifest = json.loads((store / 'manifest.json').read_text())
    assert sorted(p.name for p in store.iterdir()) == ['manifest.json']
    assert manifest['p4Admission'] == 'BLOCKED_NEW_DATASET_PROTOCOL_AND_REVIEW_REQUIRED'
    for key in ('raw', 'panel'):
        assert manifest[key]['publicPayloadPresent'] is False
        assert manifest[key]['retention'] == 'LOCAL_NONPUBLIC_PENDING_OWNER_STORAGE'
        assert 'path' not in manifest[key]
    report = json.loads((A.ROOT / 'docs/us-readiness/us-departed-public-price-recovery-v1.json').read_text())
    assert len(report['inventory']) == 212
    assert report['distinctAuditIdentifiersWithDownloadedHistory'] == 193
    assert report['qualifiedPriceCoverageCounts'] == {'FULL': 5, 'PARTIAL': 170, 'NONE': 37}
    assert report['qualifiedCoveredMembershipSessions'] == 186910
    assert manifest['panel']['uniqueMembershipSessions'] == 186910


def synthetic_artifacts(tmp_path, rows):
    import gzip
    raw = b'synthetic raw archive bytes'
    expanded = json.dumps({'terminalConsiderationResolved': False, 'rows': rows}, allow_nan=True).encode()
    compressed = gzip.compress(expanded, mtime=0)
    (tmp_path / 'raw.gz').write_bytes(raw)
    (tmp_path / 'panel.gz').write_bytes(compressed)
    return {'raw': {'externalFilename': 'raw.gz', 'bytes': len(raw), 'sha256': R.digest(raw)},
            'panel': {'externalFilename': 'panel.gz', 'bytes': len(compressed), 'sha256': R.digest(compressed),
                      'decompressedSha256': R.digest(expanded), 'perSourceObservations': len(rows)}}


def test_external_artifact_integrity_retained_without_public_prices(tmp_path):
    rows = [['synthetic', 'TEST', 'E', '2013-01-02', None, None, None, 10, None, None]]
    manifest = synthetic_artifacts(tmp_path, rows)
    assert A.verify_candidate_artifacts(manifest, tmp_path)['perSourceObservations'] == 1
    (tmp_path / 'raw.gz').write_bytes(b'changed')
    with pytest.raises(ValueError, match='CHECKSUM_MISMATCH'):
        A.verify_candidate_artifacts(manifest, tmp_path)


@pytest.mark.parametrize('defect', ['duplicate', 'zero', 'invalid_source', 'invented_volume', 'nan'])
def test_external_panel_invalid_observations_rejected(tmp_path, defect):
    rows = [['synthetic', 'TEST', 'E', '2013-01-02', None, None, None, 10, None, None]]
    if defect == 'duplicate': rows.append(rows[0][:])
    if defect == 'zero': rows[0][7] = 0
    if defect == 'invalid_source': rows[0][2] = 'G'
    if defect == 'invented_volume': rows[0][8] = 0
    if defect == 'nan': rows[0][7] = float('nan')
    manifest = synthetic_artifacts(tmp_path, rows)
    with pytest.raises(ValueError, match='CANDIDATE_OBSERVATION_INTEGRITY'):
        A.verify_candidate_artifacts(manifest, tmp_path)


def test_git_payload_output_blocked_before_any_real_read(tmp_path, monkeypatch):
    checkout = tmp_path / 'checkout';checkout.mkdir();(checkout / '.git').mkdir();(checkout / '.git/HEAD').write_text('ref: refs/heads/test')
    monkeypatch.setattr(A, 'audit', lambda *_: pytest.fail('must not read inputs'))
    for option in ('--archive', '--candidate-panel'):
        with pytest.raises(ValueError, match='PRICE_PAYLOAD_MUST_BE_OUTSIDE_GIT_CHECKOUT'):
            A.main(['--raw-root', str(tmp_path / 'raw'), '--report', str(tmp_path / 'report'),
                    option, str(checkout / 'payload.gz')])


def test_all_acquired_sources_have_explicit_redistribution_hold():
    audit = json.loads((A.ROOT / 'docs/us-readiness/us-departed-price-redistribution-audit-v1.json').read_text())
    assert {'A', 'B_catalog', 'B_secondary', 'C', 'D', 'E', 'F', 'G', 'B_direct',
            'Stooq_probe', 'existing_sealed_Yahoo_controls'} == {item['source'] for item in audit['sources']}
    assert all(item['rawRedistribution'] == item['derivedRedistribution'] == 'UNVERIFIED'
               for item in audit['sources'])
