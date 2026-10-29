"""Versioned source-only rejoin of exact v2-selected originals retained in v1.

The fixed68 CODE8/plan and prior measurements are unchanged. Default PLAN_ONLY;
--inspect writes a new blocked measurement. No network, outcome/price loader,
original financial packages, policy choice or execution authorization.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import re

from . import features as F
from . import pit_admission as A
from . import pit_filing_evidence as E
from . import pit_join as J
from . import source_quality as Q

V1 = 'data/kr-industry-membership-foundation-v1/acquired-dart'
INVENTORY = 'data/kr-industry-membership-foundation-v2/inventory'
HERE = Path(__file__).parent
BASE = HERE / 'pit_measurement_v2'
BASE_HASHES = {
    'coverage.json': '50a2bc6fcd49dfdb1c3a7b758739af37ab107cacecbca9a273c03b2a28d740dc',
    'cohorts.jsonl.gz': '6b23451e56e28ce3225af47be38448bec0d635acf53a46d2361417e661490dfb',
    'rows.jsonl.gz': 'ac53b611e0df160e3846931530532b037e5f3ceef0589de93a8564ea1ca7a766',
}


class RetainedInputs(J.PinnedInputs):
    def blob(self, commit, path):
        extra = (re.fullmatch(re.escape(INVENTORY) + r'/batch-(?:0\d|1\d|2[0-5])/inventory\.json', path)
                 or re.fullmatch(re.escape(V1) + r'/(?:manifest|batch)-(?:00\d|01\d|020)\.json(?:\.gz)?', path))
        if commit != J.EVIDENCE_COMMIT or not extra:
            return super().blob(commit, path)
        # Exact manifests and archives only, never traversal or a caller URL.
        if not (re.fullmatch(re.escape(V1) + r'/manifest-(?:00\d|01\d|020)\.json', path)
                or re.fullmatch(re.escape(V1) + r'/batch-(?:00\d|01\d|020)\.json\.gz', path)
                or path.startswith(INVENTORY + '/')):
            raise ValueError('NON_INPUT_OR_UNPINNED_PATH_REFUSED:' + path)
        result = J.subprocess.run(['git', 'cat-file', 'blob', commit + ':' + path], cwd=self.root,
                                  env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'}, capture_output=True)
        if result.returncode:
            raise ValueError('PINNED_LOCAL_SOURCE_UNAVAILABLE:' + path)
        self.receipts[commit + ':' + path] = {'sha256': E.sha(result.stdout), 'bytes': len(result.stdout)}
        return result.stdout


def supplement_originals(source, originals, *, inventory_batches=26, archive_batches=21):
    """Only the original selected receipt; never a same-year or same-name substitute."""
    targets = {}
    for batch in range(inventory_batches):
        rows = json.loads(source.blob(J.EVIDENCE_COMMIT, f'{INVENTORY}/batch-{batch:02d}/inventory.json'))
        for row in rows:
            if row.get('paginationComplete') is not True:
                raise ValueError('ORIGINAL_SELECTION_PAGINATION_UNPROVEN')
            for target in row.get('selected', []):
                receipts = target.get('receiptNos')
                if not isinstance(receipts, list) or len(receipts) != 1:
                    raise ValueError('ORIGINAL_RECEIPT_UNRESOLVED')
                receipt = receipts[0]
                if receipt in targets and targets[receipt] != target:
                    raise ValueError('CONFLICTING_SELECTED_ORIGINAL_IDENTITY')
                targets[receipt] = target
    combined = deepcopy(originals)
    added, not_selected, not_served = [], 0, 0
    for batch in range(archive_batches):
        manifest = json.loads(source.blob(J.EVIDENCE_COMMIT, f'{V1}/manifest-{batch:03d}.json'))
        if manifest.get('archive') != f'batch-{batch:03d}.json.gz':
            raise ValueError('ORIGINAL_ARCHIVE_REFERENCE_CHANGED')
        archive = source.blob(J.EVIDENCE_COMMIT, V1 + '/' + manifest['archive'])
        if E.sha(archive) != manifest.get('archiveSha256'):
            raise ValueError('ORIGINAL_ARCHIVE_DIGEST_MISMATCH')
        bodies = json.loads(gzip.decompress(archive))
        for record in manifest['records']:
            mains = [r for r in record['responses'] if not r.get('section')]
            if len(mains) != 1:
                raise ValueError('ORIGINAL_MAIN_RESPONSE_AMBIGUOUS')
            main = mains[0]
            match = re.fullmatch(r'https://dart\.fss\.or\.kr/dsaf001/main\.do\?rcpNo=(\d{14})', main['url'])
            if not match:
                raise ValueError('ORIGINAL_MAIN_URL_MISMATCH')
            target = targets.get(match[1])
            if target is None:
                not_selected += 1
                continue
            if main.get('status') != 200 or main.get('sha256') not in bodies:
                not_served += 1
                continue
            raw = base64.b64decode(bodies[main['sha256']], validate=True)
            if E.sha(raw) != main['sha256']:
                raise ValueError('ORIGINAL_MAIN_BODY_DIGEST_MISMATCH')
            meta = E.original_main(target, raw, main['url'])
            issuers = set(re.findall(r"openCorpInfoNew\(['\"](\d{8})['\"]", raw.decode('utf-8')))
            if issuers != {target['corpCode']}:
                raise ValueError('ORIGINAL_ISSUER_LINK_MISMATCH')
            key = (meta['ticker'], meta['fiscalYear'], meta['receipt'])
            if key in combined:
                if combined[key] != [meta]:
                    raise ValueError('CONFLICTING_RETAINED_ORIGINAL')
            else:
                combined[key] = [meta]
                added.append(meta)
    return combined, {'addedExactSelectedOriginals': len(added),
                      'addedByFiscalYear': dict(sorted(Counter(str(m['fiscalYear']) for m in added).items())),
                      'addedIssuers': len({m['corpCode'] for m in added}),
                      'notSelectedReceipts': not_selected, 'selectedOriginalsNotServed': not_served,
                      'newFinancialFactsCertified': 0,
                      'addedEvidence': [{k: m[k] for k in ('ticker', 'corpCode', 'fiscalYear', 'receipt', 'availableFrom', 'mainSha256')}
                                        for m in sorted(added, key=lambda m: m['receipt'])]}


def _baseline():
    for name, expected in BASE_HASHES.items():
        if E.sha((BASE / name).read_bytes()) != expected:
            raise ValueError('BASE_MEASUREMENT_CHANGED:' + name)
    J.verify_measurement(BASE)
    report = json.loads((BASE / 'coverage.json').read_bytes())
    cohorts, rows = ([json.loads(r) for r in gzip.decompress((BASE / name).read_bytes()).splitlines() if r]
                     for name in ('cohorts.jsonl.gz', 'rows.jsonl.gz'))
    return report, cohorts, rows


def support(cohorts, rows):
    by_date, counts = {c['signal']: c for c in cohorts}, defaultdict(Counter)
    for row in rows:
        c = by_date[row['signal']]
        for signal, detail in row['signals'].items():
            valid = (not c['reasons'] and not row['endedBySignal']
                     and row['tradingStatus'] == 'OBSERVED_TRADABLE_SIGNAL_BAR' and detail['inputReadable']
                     and row['originalMainPairMatched'] and row['datedIdentityMatched'] and row['industryIssuerMatched'])
            counts[signal][row['signal']] += int(valid)
    return {signal: {'optimisticInputSupportRows': sum(counts[signal].values()),
                     'bestNamesOnOneDate': max(counts[signal].values(), default=0),
                     'datesAtLeast30': sum(v >= 30 for v in counts[signal].values()),
                     'byDate': {d: counts[signal][d] for d in sorted(by_date)}} for signal in F.SIGNALS}


def inspect(source):
    from . import portable_collection as P
    P.validate_plan(P.read_plan(HERE / 'xbrl_recovery_v2/portable-plan.json.gz'))
    base, cohorts, before = _baseline()
    originals, old_diagnostic = J.load_originals(source)
    originals, supplement = supplement_originals(source, originals)
    events, event_diagnostic = J.load_industry_events(source, originals)
    filings = [r for year in range(2015, 2025)
               for r in source.rows(f'ledger/fundamentals/kr-raw/raw-{year}.jsonl.gz') if r.get('reportCode') == '11011']
    sessions = [str(s.date()) for s in J.xc.get_calendar('XKRX', start='2015-01-01', end='2026-01-31').sessions]
    if F.digest(sessions) != base['calendar']['sha256']:
        raise ValueError('BASE_CALENDAR_CHANGED')

    class PreservedCohorts:
        def on(self, signal):
            return deepcopy(next(c for c in cohorts if c['signal'] == signal))

    terminal = {r['code']: r['lastTradingDate'] for r in source.json(J.TERMINAL)['securities']}
    worker = A.Crosswalk(snapshots=PreservedCohorts(), filings=filings, originals=originals,
                         intervals=source.json(J.INTERVALS), events=events, crosswalk=source.json(J.CROSSWALK),
                         terminal=terminal, trading={(r['signal'], r['ticker']): r['tradingStatus'] for r in before},
                         sessions=sessions)  # No original financial packages; pending F2 remains pending.
    after = []
    for c in cohorts:
        recovered, rr = worker.on(c['signal'])
        if recovered != c:
            raise ValueError('INTENDED_COHORT_CHANGED')
        after.extend(rr)
    cov = A.coverage(cohorts, after)
    if cov['retainedMemberDates'] != 51360 or cov['knownTerminalMemberDatesAuditOnly'] != 1725:
        raise ValueError('DENOMINATOR_OR_TERMINATED_MEMBERS_CHANGED')
    # The old failed acquisition remains its own immutable evidence, not the later producer's 68 ZIP claim.
    acquisition = json.loads((HERE / 'xbrl_recovery_v2/acquisition/manifest.json').read_bytes())
    first_failure = {'before': Q.decompose(cohorts, before, acquisition)['signals'],
                     'after': Q.decompose(cohorts, after, acquisition)['signals']}
    report = {**base, 'schema': 'STOCK_WC_RETAINED_ORIGINAL_JOIN_V3',
              'baseMeasurementSha256': BASE_HASHES, 'status': 'INPUT_JOIN_MEASURED_ADMISSION_BLOCKED',
              'sourceReadReceiptsThisRun': source.receipts,
              'sourceReceipts': {**base['sourceReceipts'], **source.receipts},
              'sourceReuse': 'Exact v2 selected originals already retained in v1; unchanged core Crosswalk and financial reader',
              'originalSourceEvidence': old_diagnostic, 'retainedOriginalSupplement': supplement,
              'industrySourceEvidence': event_diagnostic, 'coverage': cov,
              'beforeCoverage': base['coverage'], 'byYear': {},
              'support': {'before': support(cohorts, before), 'after': support(cohorts, after)},
              'exclusiveFirstFailure': first_failure,
              'sourceAdmission': {'financialEvidence': {s: cov['signals'][s]['originalFinancialFactsMatched'] for s in F.SIGNALS},
                  'rightsClearedMemberDates': None, 'completeStockReturnBasisMemberDates': None,
                  'fullyAdmissibleMemberDates': 0, 'datesMeeting30FullyAdmitted': 0,
                  'fullyAdmissibleMaturedCohorts': {'H126': 0, 'H252': 0},
                  'unknownIsNotZero': True, 'reason': 'No original financial packages or approved F2, rights or full shareholder-return binding'},
              'fixed68PlanChanged': False, 'legacyCode8Changed': False, 'sourceAdmissionAuthorized': False,
              'originalFinancialPackagesAvailable': 0, 'historicalReturnLabelsRead': 0,
              'historicalReturnCalculations': 0, 'modelFits': 0,
              'codeSha256': {**base['codeSha256'], Path(__file__).name: E.sha(Path(__file__).read_bytes())}}
    report.pop('outputSha256', None)
    report.pop('originalRecoveryManifestSha256', None)  # This source rejoin is not an XBRL reacquisition.
    report['sourceDemandSummary'] = {k: v for k, v in J.source_demand(cohorts, after).items() if k != 'requests'}
    return report, cohorts, after


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inspect', action='store_true')
    p.add_argument('--output', type=Path)
    args = p.parse_args(argv)
    if not args.inspect:
        print(json.dumps({'status': 'PLAN_ONLY', 'sourceReads': 0, 'historicalOutcomesRead': 0}))
        return 0
    if args.output is None or args.output.exists():
        p.error('--output must be a NEW directory')
    try:
        report, cohorts, rows = inspect(RetainedInputs(J.ROOT))
        args.output.mkdir(parents=True, exist_ok=False)
        for name, data in (('cohorts.jsonl.gz', cohorts), ('rows.jsonl.gz', rows)):
            raw = gzip.compress(J.canonical_lines(data), mtime=0)
            (args.output / name).write_bytes(raw)
            report.setdefault('outputSha256', {})[name] = E.sha(raw)
        (args.output / 'coverage.json').write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        J.verify_measurement(args.output)
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(json.dumps({'status': 'SOURCE_OR_INFRASTRUCTURE_ERROR', 'error': str(exc)}))
        return 4
    print(json.dumps({'status': report['status'], 'coverage': report['coverage']}, ensure_ascii=False))
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
