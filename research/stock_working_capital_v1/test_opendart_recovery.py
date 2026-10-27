"""Private source bytes are invented; no HTTP, prices, labels or model fits."""
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import zipfile

import pytest

from . import age_policy as AP
from . import opendart_recovery as O
from . import pit_filing_evidence as E
from . import portable_collection as P
from .test_pit_admission import filing, meta, package, worker


def archive(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in entries:
            z.writestr(name, content)
    return out.getvalue()


def target_and_raw():
    r = filing(2024)
    t = meta(2024)
    p = package(r)
    with zipfile.ZipFile(io.BytesIO(p['raw'])) as z:
        xml = z.read('instance.xbrl')
    raw = archive([(t['corpCode'] + '_2024.xbrl', xml), ('ifrs_for_2024\\dimensions\\meta.xml', b'<meta/>')])
    return r, t, raw


def fixture(tmp_path, monkeypatch):
    r, t, raw = target_and_raw()
    monkeypatch.setattr(O, '_targets', lambda plan_path: [t])
    directory = tmp_path / 'private'
    directory.mkdir()
    retrieved = datetime(2026, 10, 26, tzinfo=timezone.utc).isoformat()
    e = {'receipt': t['receipt'], 'httpStatus': 200, 'transportError': None,
         'file': t['receipt'] + '.bin', 'sha256': E.sha(raw), 'bytes': len(raw), 'retrievedAt': retrieved}
    manifest = {'route': O.ROUTE, 'reprtCode': '11011', 'entries': [e]}
    doc = {'schema': O.RECEIPT_SCHEMA, 'forPr': 'jaehojung1879-netizen/Investment#286',
           'planSha256': O.PLAN_SHA256, 'route': O.ROUTE, 'rawBytesCommitted': False,
           'historicalOutcomesRead': 0, 'sourceAdmissionAuthorized': False,
           'originalFinancialValuesVerified': False,
           'statusCounts': {'ACQUIRED_IDENTITY_CHECKED_VALUES_UNVERIFIED': 1},
           'rows': [{**{k: t[k] for k in O.IDENTITY_KEYS},
                     **{k: v for k, v in e.items() if k != 'file'}, 'route': O.ROUTE,
                     'status': 'ACQUIRED_IDENTITY_CHECKED_VALUES_UNVERIFIED',
                     'checks': {'entityIdentifierIsCorpCode': True}}]}
    (directory / e['file']).write_bytes(raw)
    receipt = tmp_path / 'receipt.json'
    def save():
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        receipt.write_text(json.dumps(doc))
    save()
    return r, t, directory, receipt, manifest, doc, save


def test_raw_backslash_members_are_read_only_and_existing_strict_fact_reader_is_used(tmp_path, monkeypatch):
    r, t, d, receipt, _, _, _ = fixture(tmp_path, monkeypatch)
    before = {p.name: p.read_bytes() for p in d.iterdir()}
    packages, audit = O.load_acquisition(d, receipt)
    assert audit['originalPackagesAcquiredUnverified'] == 1
    assert audit['identityAndPeriodEndVerified'] == 1
    assert not audit['originalFinancialValuesVerified'] and not audit['sourceAdmissionAuthorized']
    assert audit['backslashMemberCount'] == 1
    assert E.original_financial_facts(r, t, packages[t['receipt']], 'inventory')['ready']
    assert {p.name: p.read_bytes() for p in d.iterdir()} == before
    assert not (d / 'ifrs_for_2024').exists()
    w = worker()
    w.fiscal_age_policy = AP.pending_policy()
    _, rows = w.on('2025-03-21')
    assert not rows[0]['signals']['inventory_discipline']['inputAdmitted']


@pytest.mark.parametrize('names', [('../x.xml',), ('a\\..\\x.xml',), ('/x.xml',), ('C:\\x.xml',),
                                  ('a/x.xml', 'a\\x.xml'), ('a/./x.xml',), ('a//x.xml',)])
def test_unsafe_or_duplicate_canonical_paths_are_refused(names):
    with pytest.raises(ValueError, match='ZIP'):
        O.inspect_package(archive([(n, b'<meta/>') for n in names]), meta(2024))


def test_symlinks_and_compression_bombs_and_entities_are_refused():
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        link = zipfile.ZipInfo('link.xml')
        link.create_system = 3
        link.external_attr = (0o120777 << 16)
        z.writestr(link, b'../secret')
    for raw in (out.getvalue(), archive([('x.xml', b'x' * 200000)]),
                archive([('x.xml', b'<!DOCTYPE x [<!ENTITY e "bad">]><x/>')])):
        with pytest.raises(ValueError):
            O.inspect_package(raw, meta(2024))


@pytest.mark.parametrize('fault', ['hash', 'size', 'file', 'duplicate', 'foreign', 'corp', 'year', 'date',
                                   'counts', 'http', 'error', 'flags', 'retrieved', 'plan', 'missing'])
def test_recomputed_metadata_does_not_bypass_fixed_receipt_or_retained_bytes(tmp_path, monkeypatch, fault):
    _, _, d, receipt, manifest, doc, save = fixture(tmp_path, monkeypatch)
    e, row = manifest['entries'][0], doc['rows'][0]
    if fault == 'hash': e['sha256'] = row['sha256'] = 'f' * 64
    elif fault == 'size': e['bytes'] = row['bytes'] = 1
    elif fault == 'file': e['file'] = '../other.bin'
    elif fault == 'duplicate': manifest['entries'].append(deepcopy(e))
    elif fault == 'foreign': row['receipt'] = '20250321000001'
    elif fault == 'corp': row['corpCode'] = '99999999'
    elif fault == 'year': row['fiscalYear'] -= 1
    elif fault == 'date': row['availableFrom'] = '2025-01-01'
    elif fault == 'counts': doc['statusCounts'] = {}
    elif fault == 'http': e['httpStatus'] = row['httpStatus'] = True
    elif fault == 'error': e['transportError'] = row['transportError'] = 'TimeoutError'
    elif fault == 'flags': doc['sourceAdmissionAuthorized'] = True
    elif fault == 'retrieved': e['retrievedAt'] = row['retrievedAt'] = '2025-03-01T00:00:00'
    elif fault == 'plan': doc['planSha256'] = '0' * 64
    else: manifest['entries'] = []
    save()
    with pytest.raises(ValueError):
        O.load_acquisition(d, receipt)


def test_identity_envelope_cannot_admit_wrong_units_values_contexts_or_basis():
    r, t, _ = target_and_raw()
    for kw in ({'currency': 'USD'}, {'value_delta': 1}, {'member': 'SeparateMember'},
               {'start': '2024-04-01'}, {'corp': '99999999'}):
        p = package(r, **kw)
        with pytest.raises(ValueError):
            E.original_financial_facts(r, t, p, 'inventory')


def test_retrieval_evidence_never_backdates_the_financial_amount_vintage(tmp_path, monkeypatch):
    _, _, d, receipt, _, _, _ = fixture(tmp_path, monkeypatch)
    _, audit = O.load_acquisition(d, receipt)
    assert audit['historicalOutcomesRead'] == 0
    assert audit['transportAuthenticity'] == 'PRODUCER_RECORDED_HTTPS_NOT_INDEPENDENT_SIGNATURE'
    assert audit['originalVintageLimitation']
    assert audit['originalFinancialValuesVerified'] is False


def test_unchanged_portable_plan_and_codes_remain_valid():
    path = P.HERE / 'xbrl_recovery_v2/portable-plan.json.gz'
    assert E.sha(path.read_bytes()) == O.PLAN_SHA256
    assert len(P.validate_plan(P.read_plan(path))) == 68


def test_verified_fact_count_uses_original_amount_unit_context_and_pending_policy():
    r, t, raw = target_and_raw()
    p = package(r)
    p.update(raw=raw, sha256=E.sha(raw))
    facts = O.verify_fact_candidates([r], {t['receipt']: p}, [t])
    assert facts['verifiedFinancialFactCount'] == 3
    assert {x['field'] for x in facts['facts']} == {'sales', 'inventory', 'receivables'}
    assert facts['matchedReceiptCount'] == 1
    assert not facts['sourceAdmissionAuthorized']
    assert facts['fiscalAgePolicySelected'] is None
    wrong = deepcopy(r)
    wrong['rows'][2]['thstrm_amount'] = '9999999'
    failed = O.verify_fact_candidates([wrong], {t['receipt']: p}, [t])
    assert failed['verifiedFinancialFactCount'] == 0 and len(failed['failures']) == 2


def test_duplicate_raw_basis_or_different_receipt_metadata_cannot_create_facts():
    r, t, raw = target_and_raw()
    p = package(r)
    p.update(raw=raw, sha256=E.sha(raw))
    with pytest.raises(ValueError, match='DUPLICATE_RAW'):
        O.verify_fact_candidates([r, deepcopy(r)], {t['receipt']: p}, [t])
    wrong = deepcopy(r)
    wrong['availableFrom'] = '2025-03-19'
    failed = O.verify_fact_candidates([wrong], {t['receipt']: p}, [t])
    assert failed['verifiedFinancialFactCount'] == 0
    assert all('METADATA_MISMATCH' in x['reason'] for x in failed['failures'])


def test_real_measurement_wrapper_passes_packages_to_existing_join_and_keeps_fixed_population(tmp_path, monkeypatch):
    from . import pit_join as J
    from . import pit_admission as A
    w = worker()
    w.fiscal_age_policy = AP.pending_policy()
    cohort, rows = w.on('2025-03-21')
    packages = {'synthetic': object()}
    audit = {'acquisitionManifestSha256': 'a' * 64, 'receiptSha256': 'b' * 64}
    monkeypatch.setattr(O, 'load_acquisition', lambda *args: (packages, audit))
    class FakeSource:
        def rows(self, path):
            assert path.startswith('ledger/fundamentals/kr-raw/')
            return []
    monkeypatch.setattr(J, 'PinnedInputs', lambda path: FakeSource())
    called = []
    def inspect(source, given):
        assert given is packages
        called.append(True)
        return {'coverage': A.coverage([cohort], rows), 'fiscalAgePolicy': AP.pending_policy()}, [cohort], rows
    monkeypatch.setattr(J, 'inspect', inspect)
    monkeypatch.setattr(O, '_targets', lambda path: [])
    with pytest.raises(ValueError, match='FIXED_51360'):
        O.inspect_to_directory('unused', 'unused', tmp_path / 'no-output')
    assert called and not (tmp_path / 'no-output').exists()


def test_api_source_quality_rehashes_private_bytes_and_binds_receipt_then_refuses_rebound(tmp_path, monkeypatch):
    from . import source_quality as Q
    from . import pit_join as J
    from .test_source_quality_binding import measurement
    _, _, directory, receipt, _, _, _ = fixture(tmp_path, monkeypatch)
    _, audit = O.load_acquisition(directory, receipt)
    measured = measurement(tmp_path, audit['acquisitionManifestSha256'])
    coverage_file = measured / 'coverage.json'
    report = json.loads(coverage_file.read_text())
    report.update(originalRecoveryReceiptSha256=audit['receiptSha256'], originalRecoveryRoute=O.ROUTE)
    coverage_file.write_text(json.dumps(report))
    quality = Q.write_report(measured, directory, tmp_path / 'quality.json', api_receipt=receipt)
    assert quality['originalPackagesAcquiredUnverified'] == 1
    assert quality['apiRequestsRecorded'] == 1 and quality['publicReceiptRequestsAttempted'] == 0
    assert quality['independentAcquisitionReceiptSha256'] == audit['receiptSha256']
    assert J.verify_measurement(measured)['memberDates'] == 3
    for signal in quality['signals'].values():
        assert signal['researchEligibleObservations'] == 0
        assert sum(signal['exclusiveFirstUnresolvedStage'].values()) == 3
    changed = json.loads(receipt.read_text())
    changed['unusedButDifferent'] = True
    receipt.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='MEASUREMENT_API_ACQUISITION_BINDING'):
        Q.write_report(measured, directory, tmp_path / 'rebound.json', api_receipt=receipt)
    assert not (tmp_path / 'rebound.json').exists()


def test_wrapper_writes_new_bound_measurement_and_quality_without_touching_sources(tmp_path, monkeypatch):
    """Retained input-only cohorts exercise the real writer/validator, not outcomes."""
    import gzip
    from . import pit_join as J
    _, _, directory, receipt, _, _, _ = fixture(tmp_path, monkeypatch)
    retained = P.HERE / 'pit_measurement_v2'
    report = json.loads((retained / 'coverage.json').read_text())
    cohorts = [json.loads(x) for x in gzip.decompress((retained / 'cohorts.jsonl.gz').read_bytes()).splitlines()]
    rows = [json.loads(x) for x in gzip.decompress((retained / 'rows.jsonl.gz').read_bytes()).splitlines()]
    class FakeSource:
        def rows(self, path):
            return []
    monkeypatch.setattr(J, 'PinnedInputs', lambda path: FakeSource())
    def inspect(source, packages):
        assert len(packages) == 1 and next(iter(packages.values()))['raw'].startswith(b'PK')
        return report, cohorts, rows
    monkeypatch.setattr(J, 'inspect', inspect)
    output = tmp_path / 'new-measurement'
    result = O.inspect_to_directory(directory, receipt, output)
    assert J.verify_measurement(output)['memberDates'] == 51360
    assert result['originalSourceFactAudit']['verifiedFinancialFactCount'] == 0
    quality = json.loads((output / 'source-quality.json').read_text())
    assert quality['originalPackagesAcquiredUnverified'] == 1
    assert all(s['denominator'] == 51360 and s['researchEligibleObservations'] == 0 for s in quality['signals'].values())
    with pytest.raises(ValueError, match='PRESERVE_PREVIOUS'):
        O.inspect_to_directory(directory, receipt, output)


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'utf-16', 'utf-32'])
def test_encoded_internal_entities_cannot_bypass_xml_doctype_refusal(encoding):
    xml = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "expanded">]><x>&e;</x>'
    raw = archive([('instance.xbrl', xml.encode(encoding))])
    with pytest.raises(ValueError):
        O.inspect_package(raw, meta(2024))
