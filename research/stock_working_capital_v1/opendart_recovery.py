"""Read fixed-68 private OpenDART packages; never collect or approve a study.

The receipt, retained manifest and bytes must agree before the existing strict
financial comparator sees any package. Backslashes are canonicalized solely to
check ZIP member identity in memory; original bytes and SHA are never rewritten.
No key, price reader, outcome engine, extraction to disk or fiscal-policy choice.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
import gzip
import io
import json
from pathlib import Path
import re
import stat
import xml.etree.ElementTree as ET
import zipfile

from . import features as F
from . import pit_filing_evidence as E
from . import portable_collection as P

PLAN_SHA256 = '2c73067ced7c59a2b23a693b5db6aca37f45d69c478c2f789df877126f738766'
ROUTE = 'OPENDART_FNLTTXBRL_API'
RECEIPT_SCHEMA = 'KR_WC68_INDEPENDENT_ACQUISITION_RECEIPT_V1'
IDENTITY_KEYS = ('receipt', 'corpCode', 'ticker', 'fiscalYear', 'periodEndMonth', 'availableFrom')
ACQUIRED = 'ACQUIRED_IDENTITY_CHECKED_VALUES_UNVERIFIED'
MAX_BYTES = 32 << 20
PLAN = P.HERE / 'xbrl_recovery_v2/portable-plan.json.gz'


def _targets(plan_path):
    if E.sha(Path(plan_path).read_bytes()) != PLAN_SHA256:
        raise ValueError('FIXED_68_PLAN_CHANGED')
    return P.validate_plan(P.read_plan(plan_path))


def _partition(rows, targets):
    if not isinstance(rows, list) or len(rows) != len(targets):
        raise ValueError('FIXED_68_PARTITION_INCOMPLETE')
    seen = {}
    expected = {t['receipt'] for t in targets}
    for row in rows:
        if not isinstance(row, dict) or row.get('receipt') not in expected or row['receipt'] in seen:
            raise ValueError('FIXED_68_DUPLICATE_OR_FOREIGN_RECEIPT')
        seen[row['receipt']] = row
    return seen


def _member_name(info):
    original = info.orig_filename
    name = original.replace('\\', '/')
    parts = name.rstrip('/').split('/')
    if (not name or len(name) > 512 or '\x00' in original or name.startswith('/')
            or any(p in ('', '.', '..') or ':' in p for p in parts)
            or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1):
        raise ValueError('UNSAFE_ZIP_MEMBER')
    return '/'.join(parts)



class _NoDTD(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        # Parser callbacks handle UTF-16/BOM encodings that a byte substring
        # guard cannot recognize. No internal entity expansion is permitted.
        raise ValueError('ZIP_XML_DTD_REFUSED')


def inspect_package(raw, target):
    """Only package envelope identity, never numeric or original-vintage approval."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('ZIP_BYTE_BOUND')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            if not infos or len(infos) > 100 or sum(i.file_size for i in infos) > MAX_BYTES:
                raise ValueError('ZIP_EXPANSION_BOUND')
            canonical = [_member_name(i) for i in infos]
            if len(set(canonical)) != len(canonical):
                raise ValueError('ZIP_DUPLICATE_CANONICAL_MEMBER')
            roots = []
            for info, name in zip(infos, canonical):
                if info.file_size > MAX_BYTES or info.file_size > 200 * max(1, info.compress_size):
                    raise ValueError('ZIP_COMPRESSION_RATIO_BOUND')
                # Reading every member checks CRC even for files not interpreted.
                body = z.read(info)
                if info.is_dir():
                    continue
                if not name.lower().endswith(('.xml', '.xbrl', '.xsd')):
                    continue
                if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
                    raise ValueError('ZIP_XML_DTD_REFUSED')
                root = ET.fromstring(body, parser=ET.XMLParser(target=_NoDTD()))
                if root.tag == '{' + E.XI + '}xbrl':
                    roots.append((name, root))
            if len(roots) != 1:
                raise ValueError('ZIP_INSTANCE_AMBIGUOUS')
            name, root = roots[0]
            if not name.rsplit('/', 1)[-1].startswith(target['corpCode'] + '_'):
                raise ValueError('ZIP_INSTANCE_NAME_ISSUER_MISMATCH')
            identifiers = root.findall('.//{' + E.XI + '}entity/{' + E.XI + '}identifier')
            if (not identifiers or {x.text for x in identifiers} != {target['corpCode']}
                    or any(not re.fullmatch(r'https?://dart\.fss\.or\.kr/[^\s]*', x.get('scheme', ''))
                           for x in identifiers)):
                raise ValueError('ZIP_ENTITY_ISSUER_MISMATCH')
            ends = [x.text for x in root.findall('.//{' + E.XI + '}endDate')]
            ends += [x.text for x in root.findall('.//{' + E.XI + '}instant')]
            if not any(isinstance(s, str) and s.startswith(target['periodEndMonth'] + '-') for s in ends):
                raise ValueError('ZIP_FISCAL_PERIOD_END_NOT_PRESENT')
            # Namespace rebinding cannot silently change lexical unit/dimension QNames.
            E.package_namespaces(raw)
            return {'identityAndPeriodEndVerified': True,
                    'backslashMemberCount': sum('\\' in i.orig_filename for i in infos),
                    'memberCount': len(infos), 'originalFinancialValuesVerified': False}
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError, NotImplementedError) as exc:
        raise ValueError('ZIP_CONTENT_INVALID_OR_UNSUPPORTED') from exc


def load_acquisition(directory, receipt_path, *, plan_path=PLAN):
    """Re-read private files, ignoring the producer's claimed envelope checks.

    HTTPS route metadata is producer-recorded evidence, not an independent
    signature. A digest binds retained bytes and does not prove who served them.
    The existing original-list/main identity and strict numeric context/unit/
    amount comparator in pit_join remain necessary after this function.
    """
    directory, receipt_path = Path(directory), Path(receipt_path)
    if directory.is_symlink() or receipt_path.is_symlink():
        raise ValueError('PRIVATE_SOURCE_SYMLINK_REFUSED')
    targets = _targets(plan_path)
    receipt_raw = receipt_path.read_bytes()
    manifest_path = directory / 'manifest.json'
    if manifest_path.is_symlink():
        raise ValueError('PRIVATE_MANIFEST_SYMLINK_REFUSED')
    manifest_raw = manifest_path.read_bytes()
    doc, manifest = json.loads(receipt_raw), json.loads(manifest_raw)
    if not isinstance(doc, dict) or not isinstance(manifest, dict):
        raise ValueError('OPENDART_METADATA_OBJECT_REQUIRED')
    if (doc.get('schema') != RECEIPT_SCHEMA or doc.get('planSha256') != PLAN_SHA256
            or doc.get('forPr') != 'jaehojung1879-netizen/Investment#286'
            or doc.get('route') != ROUTE or manifest.get('route') != ROUTE
            or manifest.get('reprtCode') != '11011'
            or doc.get('rawBytesCommitted') is not False or doc.get('sourceAdmissionAuthorized') is not False
            or doc.get('originalFinancialValuesVerified') is not False
            or type(doc.get('historicalOutcomesRead')) is not int or doc['historicalOutcomesRead'] != 0):
        raise ValueError('OPENDART_RECEIPT_CONTRACT_MISMATCH')
    records = _partition(doc.get('rows'), targets)
    entries = _partition(manifest.get('entries'), targets)
    if doc.get('statusCounts') != dict(Counter(r.get('status') for r in records.values())):
        raise ValueError('RECEIPT_STATUS_COUNTS_MISMATCH')
    packages, diagnostics = {}, []
    for t in targets:
        r, e = records[t['receipt']], entries[t['receipt']]
        if any(r.get(k) != t[k] or type(r.get(k)) is not type(t[k]) for k in IDENTITY_KEYS):
            raise ValueError('FIXED_68_TARGET_METADATA_MISMATCH')
        if r.get('route') != ROUTE or r.get('status') != ACQUIRED:
            raise ValueError('FIXED_68_PACKAGE_NOT_ACQUIRED')
        keys = ('httpStatus', 'transportError', 'sha256', 'bytes', 'retrievedAt')
        if any(r.get(k) != e.get(k) or type(r.get(k)) is not type(e.get(k)) for k in keys):
            raise ValueError('ACQUISITION_RECEIPT_MANIFEST_MISMATCH')
        if (type(e.get('httpStatus')) is not int or e['httpStatus'] != 200 or e.get('transportError') is not None
                or type(e.get('bytes')) is not int or not 0 < e['bytes'] <= MAX_BYTES
                or not isinstance(e.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', e['sha256'])
                or e.get('file') != t['receipt'] + '.bin'):
            raise ValueError('ACQUISITION_OBJECT_METADATA_INVALID')
        stamp = datetime.fromisoformat(e['retrievedAt'])
        if stamp.tzinfo is None or stamp.date().isoformat() < t['availableFrom']:
            raise ValueError('ACQUISITION_RETRIEVAL_TIME_UNPROVEN')
        path = directory / e['file']
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('PRIVATE_PACKAGE_PATH_ESCAPE')
        raw = path.read_bytes()
        if len(raw) != e['bytes'] or E.sha(raw) != e['sha256']:
            raise ValueError('PRIVATE_PACKAGE_DIGEST_OR_SIZE_MISMATCH')
        diagnostics.append(inspect_package(raw, t))
        packages[t['receipt']] = {'raw': raw, 'sha256': E.sha(raw), 'route': ROUTE,
                                 'url': f"https://opendart.fss.or.kr/api/fnlttXbrl.xml?rcept_no={t['receipt']}&reprt_code=11011"}
    if receipt_path.read_bytes() != receipt_raw or manifest_path.read_bytes() != manifest_raw:
        raise ValueError('ACQUISITION_METADATA_CHANGED_DURING_READ')
    report = {'status': 'PRIVATE_PACKAGES_REHASHED_ENVELOPE_ONLY_NOT_RESEARCH_ADMISSION',
              'fixedOriginalTargets': len(targets), 'originalPackagesAcquiredUnverified': len(packages),
              'identityAndPeriodEndVerified': sum(d['identityAndPeriodEndVerified'] for d in diagnostics),
              'backslashMemberCount': sum(d['backslashMemberCount'] for d in diagnostics),
              'route': ROUTE, 'planSha256': PLAN_SHA256, 'receiptSha256': E.sha(receipt_raw),
              'acquisitionManifestSha256': E.sha(manifest_raw),
              'packageSha256': {r: p['sha256'] for r, p in packages.items()},
              'transportAuthenticity': 'PRODUCER_RECORDED_HTTPS_NOT_INDEPENDENT_SIGNATURE',
              'originalVintageLimitation': 'Receipt-addressed API contract; no byte-equivalence proof to unavailable public attachment or independent historical byte timestamp.',
              'originalFinancialValuesVerified': False, 'sourceAdmissionAuthorized': False,
              'historicalOutcomesRead': 0, 'historicalModelFits': 0}
    return packages, report



def verify_fact_candidates(records, packages, targets):
    """Validate raw API amounts against original facts, never infer absent facts.

    Counts are distinct receipt/basis/concept matches, not admitted signal rows.
    Source concepts, Decimal KRW amounts and annual windows are all decided by
    the existing pinned comparator. No new taxonomy equivalence is introduced.
    """
    targets = {t['receipt']: t for t in targets}
    matches, failures, seen = {}, [], set()
    for record in records:
        receipts = record.get('receiptNos', [])
        if not isinstance(receipts, list) or len(receipts) != 1 or receipts[0] not in targets:
            continue
        receipt = receipts[0]
        target = targets[receipt]
        if receipt not in packages:
            continue
        key = receipt, record.get('fsDiv')
        if key in seen:
            raise ValueError('DUPLICATE_RAW_RECEIPT_STATEMENT_BASIS')
        seen.add(key)
        visible_after = (F.day(target['availableFrom']) + timedelta(days=1)).isoformat()
        issues = F.record_issues(record, visible_after)
        if any(record.get(k) != target[k] for k in ('ticker', 'corpCode', 'fiscalYear', 'availableFrom')):
            issues.append('RAW_RECORD_ORIGINAL_METADATA_MISMATCH')
        for field in ('receivables', 'inventory'):
            try:
                if issues:
                    raise ValueError(','.join(issues))
                result = E.original_financial_facts(record, target, packages[receipt], field)
                if not result['ready']:
                    raise ValueError('ORIGINAL_FACTS_NOT_READY')
                for fact in ('sales', field):
                    amount, reason = F.amount(record, fact)
                    if reason:
                        raise ValueError(reason)
                    row = F.matching_rows(record, fact)[0]
                    fact_key = receipt, record['fsDiv'], fact
                    item = {'receipt': receipt, 'ticker': target['ticker'], 'corpCode': target['corpCode'],
                            'fiscalYear': target['fiscalYear'], 'availableFrom': target['availableFrom'],
                            'fsDiv': record['fsDiv'], 'field': fact, 'accountId': row['account_id'],
                            'amountKRW': str(amount), 'start': result['start'], 'end': result['end'],
                            'sourceSha256': result['sourceSha256'], 'rawRecordSha256': F.digest(record)}
                    if fact_key in matches and matches[fact_key] != item:
                        raise ValueError('CONFLICTING_VERIFIED_RAW_FACT')
                    matches[fact_key] = item
            except (ValueError, zipfile.BadZipFile, ET.ParseError, ArithmeticError, KeyError) as exc:
                failures.append({'receipt': receipt, 'fsDiv': record.get('fsDiv'), 'field': field,
                                 'reason': str(exc)})
    facts = [matches[k] for k in sorted(matches)]
    return {'status': 'ORIGINAL_RAW_AMOUNT_MATCHES_NOT_RESEARCH_ADMISSION',
            'verifiedFinancialFactCount': len(facts), 'facts': facts,
            'matchedReceiptCount': len({x['receipt'] for x in facts}), 'failures': failures,
            'originalTaxonomyEquivalenceInferred': False, 'fiscalAgePolicySelected': None,
            'historicalOutcomesRead': 0, 'sourceAdmissionAuthorized': False}


def inspect_to_directory(acquisition, receipt, output):
    """Feed actual rehashed packages to the unchanged fixed-cohort PIT comparator."""
    from . import pit_join as J
    output = Path(output)
    if output.exists():
        raise ValueError('PRESERVE_PREVIOUS_MEASUREMENT')
    packages, audit = load_acquisition(acquisition, receipt)
    source = J.PinnedInputs(J.ROOT)
    report, cohorts, rows = J.inspect(source, packages)
    records = (r for year in range(2015, 2025)
               for r in source.rows(f'ledger/fundamentals/kr-raw/raw-{year}.jsonl.gz')
               if r.get('reportCode') == '11011')
    report['originalSourceFactAudit'] = verify_fact_candidates(records, packages, _targets(PLAN))
    if report['coverage']['expectedMemberDates'] != 51360:
        raise ValueError('FIXED_51360_DENOMINATOR_CHANGED')
    if report['fiscalAgePolicy']['admissionEnabled']:
        raise ValueError('F2_POLICY_MUST_REMAIN_PENDING')
    report['originalRecoveryManifestSha256'] = audit['acquisitionManifestSha256']
    report['originalRecoveryReceiptSha256'] = audit['receiptSha256']
    report['originalRecoveryRoute'] = ROUTE
    report['privatePackageAudit'] = audit
    report['recoveryCodeSha256'] = E.sha(Path(__file__).read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    report['outputSha256'] = {}
    for name, values in (('cohorts.jsonl.gz', cohorts), ('rows.jsonl.gz', rows)):
        raw = gzip.compress(J.canonical_lines(values), mtime=0)
        (output / name).write_bytes(raw)
        report.setdefault('outputSha256', {})[name] = E.sha(raw)
    demand = (json.dumps(J.source_demand(cohorts, rows), ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    (output / 'source-demand.json').write_bytes(demand)
    report['outputSha256']['source-demand.json'] = E.sha(demand)
    (output / 'coverage.json').write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    J.verify_measurement(output)
    from .source_quality import write_report
    write_report(output, acquisition, output / 'source-quality.json', api_receipt=receipt)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquisition', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            report = inspect_to_directory(args.acquisition, args.receipt, args.output)
            summary = {'status': report['status'], 'coverage': report['coverage'],
                       'originalRecoveryReceiptSha256': report['originalRecoveryReceiptSha256']}
        else:
            _, summary = load_acquisition(args.acquisition, args.receipt)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'SOURCE_OR_INFRASTRUCTURE_ERROR', 'errorType': type(exc).__name__, 'error': str(exc),
                          'historicalOutcomesRead': 0}))
        return 4
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 3 if args.output else 0  # pending F2 is never a successful research admission


if __name__ == '__main__':
    raise SystemExit(main())
