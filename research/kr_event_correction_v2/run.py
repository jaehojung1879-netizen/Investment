"""Prepare/validate the four-cell correction. Execution requires NEW approval.

Default validation reads code/source metadata only. It never opens price shards,
calls the old screen/C2 executors, changes their locks, or writes LIVE receipts.
"""
from __future__ import annotations

import argparse
import gzip
import importlib.metadata
import json
import platform
import subprocess
import tempfile
from pathlib import Path

from research.corporate_event_outcome_v1 import b1_inputs as B
from research.corporate_event_outcome_v1.input_pins_v2 import code_hashes, file_hash, verify_public_owner_approval
from research.corporate_event_outcome_v1.shareholder_inputs_v2 import SourceBlocked
from . import cohort, evaluate, portfolio

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CONTRACT = HERE / 'execution-packet-v2.json'
ADMISSION = HERE / 'source-admission-v2.json'
AUTHORIZATION = HERE / 'OWNER-AUTHORIZATION-v2.json'
CLAIM = HERE / 'execution-claim-v2.json'
RESULT = HERE / 'result-v2.json'
ENTRY = ['research/kr_event_correction_v2/run.py']
STUDY = 'kr-event-four-cell-correction-v2'
REMOTE_LOCK = 'refs/tags/' + STUDY + '-execution-started'
SCOPE = 'POST_OUTCOME_P2_K7_FOUR_CELLS_AND_SOURCE_GATED_THREE_PORTFOLIO_PATHS_ONLY'
PACKAGES = ('numpy', 'pandas', 'scipy', 'exchange-calendars', 'xlrd', 'threadpoolctl', 'joblib')


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def jsonl(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return list(map(json.loads, stream))


def runtime():
    packages = {}
    for package in PACKAGES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None  # validation is metadata-only; execution still requires an exact match
    return {'python': platform.python_version(), 'packages': packages}


def prepare():
    if AUTHORIZATION.exists() or CLAIM.exists() or RESULT.exists():
        raise SourceBlocked('PREPARATION_CLOSED_AFTER_AUTHORIZATION_OR_EXECUTION')
    old = ROOT / 'research/broad_alpha_screen_v1'
    registered = read(old / 'contract-v1.json')
    source_files = ['research/corporate_event_readiness_v1/cohort/data/issuer-index-rows-v1.jsonl.gz',
                    'research/corporate_event_readiness_v1/cohort/data/dividend-decisions-v1.jsonl.gz',
                    'research/corporate_event_outcome_v1/economic-readiness-v2/benchmark/issuer-standard-20261107.xls',
                    'research/corporate_event_outcome_v1/economic-readiness-v2/benchmark/069500-official-distributions.json',
                    'data/bok-policy-rates.json', 'requirements.txt', 'requirements-dev.txt',
                    'research/kr_event_correction_v2/requirements-v2.txt']
    protected = {str(p.relative_to(ROOT)): file_hash(p) for p in old.iterdir()
                 if p.is_file() and p.name in ('contract-v1.json', 'events-v1.jsonl.gz', 'result-v1.json',
                                              'result-postoutcome-v1.json', 'AUTHORIZATION.json', 'execution-claim.json')}
    protected.update(registered['codeSha256'])
    protected['research/kr_capital_event_prospective_v1/spec-v1.json'] = file_hash(ROOT / 'research/kr_capital_event_prospective_v1/spec-v1.json')
    universe_blobs = {line.split('\t')[1]: line.split()[2] for line in
                      git('ls-tree', registered['inputs']['signalHistoryCommit'] + ':ledger/universe/kr').splitlines()
                      if line.split('\t')[1].startswith('krx-universe-20')}
    packet = {'studyId': STUDY, 'scope': SCOPE, 'status': 'PREPARED_SOURCE_BLOCKED_NOT_AUTHORIZED',
              'evidenceClass': 'EXPLORATORY_POST_OUTCOME_SOURCE_CORRECTION_NOT_CONFIRMATION',
              'promotionEligible': False, 'cells': [list(v) for v in evaluate.CELLS],
              'fixed': {'cutoff': '2026-10-30', 'dividendChange': .25, 'shareCountBand': [.9, 1.1],
                        'horizons': [126, 252], 'costMultipliers': [0, 1, 2, 3], 'cash': list(evaluate.CASH),
                        'bootstrapDraws': 9999, 'bootstrapSeed': 319320, 'bootstrapBlocks': {'H126': 252, 'H252': 504},
                        'multiplicity': 'Original primary family retained conceptually; K7 and H252 descriptive, no promotion',
                        'p2': 'Registered title-decision cohort; economic dilution annotations never optimize membership',
                        'missingEconomics': 'Blocks the paired cell, never terminal/survivor deletion',
                        'portfolio': ['ORIGINAL', 'AVOID_NEXT', 'AVOID_ETF'],
                        'avoidance': '252 sessions from F2 entry; new names only, no forced sale',
                        'replacement': 'Saved order and caps; removed slot capital inheritance; ETF remainder',
                        'baselineTolerance': 1e-9},
              'codeSha256': code_hashes(ROOT, ENTRY), 'sourceSha256': {p: file_hash(ROOT / p) for p in source_files},
              'protectedSha256': protected, 'signalHistoryCommit': registered['inputs']['signalHistoryCommit'],
              'priceSha256': registered['inputs']['priceShardSha256'], 'universeGitBlobs': universe_blobs,
              'admissionSha256': file_hash(ADMISSION), 'runtime': runtime(),
              'notAuthorized': ['old research rerun', 'C2 calculator or reconstruction', 'LIVE', 'scheduler',
                                'trades', 'new threshold, horizon, universe or hypothesis']}
    CONTRACT.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    CONTRACT.with_suffix('.sha256').write_text(file_hash(CONTRACT) + '\n')
    return validate()


def validate():
    packet = read(CONTRACT)
    if packet['studyId'] != STUDY or packet['scope'] != SCOPE or packet['cells'] != [list(v) for v in evaluate.CELLS]:
        raise SourceBlocked('PACKET_SCOPE_CHANGED')
    if CONTRACT.with_suffix('.sha256').read_text().strip() != file_hash(CONTRACT):
        raise SourceBlocked('PACKET_DIGEST_CHANGED')
    if packet['codeSha256'] != code_hashes(ROOT, ENTRY):
        raise SourceBlocked('CODE_OR_IMPORT_CLOSURE_CHANGED')
    for relative, expected in {**packet['sourceSha256'], **packet['protectedSha256']}.items():
        if file_hash(ROOT / relative) != expected:
            raise SourceBlocked('PINNED_SOURCE_OR_PROTECTED_FILE_CHANGED:' + relative)
    if file_hash(ADMISSION) != packet['admissionSha256']:
        raise SourceBlocked('ADMISSION_CHANGED_NEW_PACKET_AND_APPROVAL_REQUIRED')
    admission = read(ADMISSION)
    needed = ('securityIdentities', 'fiscalPeriods', 'amendmentLinks', 'actionsByTicker', 'coverageByTicker')
    ready = (admission.get('status') == 'ADMITTED_OFFICIAL_SHAREHOLDER_INPUTS'
             and all(k in admission for k in needed)
             and all(admission[k] for k in ('securityIdentities', 'fiscalPeriods', 'coverageByTicker')))
    return {'studyId': STUDY, 'packetSha256': file_hash(CONTRACT), 'codeFiles': len(packet['codeSha256']),
            'status': 'READY_FOR_EXACT_HASH_OWNER_REVIEW' if ready else 'SOURCE_BLOCKED',
            'missing': admission.get('missing', []), 'pricesOpened': 0, 'historicalExecutions': 0,
            'liveWrites': 0, 'protectedPinsMatch': True, 'runtimeMatchesExecution': runtime() == packet['runtime']}


def authorize():
    status = validate()
    if not AUTHORIZATION.is_file():
        raise SourceBlocked('NO_NEW_OWNER_AUTHORIZATION')
    auth = read(AUTHORIZATION)
    expected = 'APPROVE KR_EVENT_CORRECTION_V2 ' + file_hash(CONTRACT)
    if auth.get('scope') != SCOPE or auth.get('phrase') != expected:
        raise SourceBlocked('OWNER_AUTHORIZATION_DOES_NOT_PIN_THIS_SCOPE_AND_PACKET')
    try:
        committed = git('show', 'HEAD:' + str(AUTHORIZATION.relative_to(ROOT)))
    except subprocess.CalledProcessError:
        raise SourceBlocked('OWNER_AUTHORIZATION_NOT_COMMITTED') from None
    if committed != AUTHORIZATION.read_text().strip():
        raise SourceBlocked('OWNER_AUTHORIZATION_NOT_COMMITTED')
    verify_public_owner_approval(auth, expected)
    if not status['runtimeMatchesExecution']:
        raise SourceBlocked('EXACT_EXECUTION_RUNTIME_REQUIRED')
    if status['status'] != 'READY_FOR_EXACT_HASH_OWNER_REVIEW':
        raise SourceBlocked('SOURCE_ADMISSION_INCOMPLETE_NO_CLAIM_CONSUMED')
    if CLAIM.exists() or RESULT.exists() or git('ls-remote', 'origin', REMOTE_LOCK):
        raise SourceBlocked('CORRECTION_EXECUTION_ALREADY_CLAIMED')
    return read(CONTRACT)


def claim():
    with CLAIM.open('x', encoding='utf-8') as stream:
        json.dump({'studyId': STUDY, 'packetSha256': file_hash(CONTRACT), 'commit': git('rev-parse', 'HEAD')}, stream)
    # Non-force remote creation is the concurrency lock. Failure consumes local claim.
    git('push', 'origin', 'HEAD:' + REMOTE_LOCK)


def load_inputs(packet, prices, universe):
    """The only price reader; execute calls this after authorization and claim."""
    if not prices or not universe:
        raise SourceBlocked('PRICES_AND_UNIVERSE_DIRECTORIES_REQUIRED')
    rows, snapshots = [], {}
    for name, expected in packet['priceSha256'].items():
        path = Path(prices) / name
        if file_hash(path) != expected:
            raise SourceBlocked('PRICE_SHARD_CHANGED:' + name)
        rows.extend(jsonl(path))
    for name, expected in packet['universeGitBlobs'].items():
        path = Path(universe) / name
        if git('hash-object', str(path)) != expected:
            raise SourceBlocked('UNIVERSE_SHARD_CHANGED:' + name)
        for row in jsonl(path):
            snapshots.setdefault(row['date'], {})[row['code']] = row
    index = jsonl(ROOT / 'research/corporate_event_readiness_v1/cohort/data/issuer-index-rows-v1.jsonl.gz')
    dividends = jsonl(ROOT / 'research/corporate_event_readiness_v1/cohort/data/dividend-decisions-v1.jsonl.gz')
    sessions = [d.strftime('%Y-%m-%d') for d in B.RC.sessions('2012-01-02', '2026-10-30', 'KR')]
    return rows, snapshots, index, dividends, sessions


def verify_input_files(packet, prices, universe):
    """Byte/identity preflight only, before consuming the new execution lock."""
    for name, expected in packet['priceSha256'].items():
        path = Path(prices) / name
        if not path.is_file() or file_hash(path) != expected:
            raise SourceBlocked('PRICE_FILE_ABSENT_OR_CHANGED_BEFORE_CLAIM:' + name)
    for name, expected in packet['universeGitBlobs'].items():
        path = Path(universe) / name
        if not path.is_file() or git('hash-object', str(path)) != expected:
            raise SourceBlocked('UNIVERSE_FILE_ABSENT_OR_CHANGED_BEFORE_CLAIM:' + name)


def benchmark(sessions):
    market, _ = B.BA.issuer_prices(B.BENCH_DIR / 'issuer-standard-20261107.xls')
    raw = read(B.BENCH_DIR / '069500-official-distributions.json')
    with tempfile.TemporaryDirectory(prefix='kr-event-benchmark-') as work:
        source = Path(work) / 'distributions.json'
        source.write_text(json.dumps({'dividList': raw}))
        calendar = B.RC.sessions('2002-10-01', '2027-12-31', 'KR')
        distributions = B.BA.issuer_distributions(source, calendar)
    market = market[(market.index >= sessions[0]) & (market.index <= sessions[-1])]
    distributions = [d for d in distributions if sessions[0] < d['exDate'] <= sessions[-1]]
    return {str(d)[:10]: float(v) for d, v in B.BA.adjusted_index(market, distributions, shareholder=True).items()}


def execute(prices, universe):
    packet = authorize()
    # Require directory names before claiming; source gates never get bypassed.
    if not prices or not universe:
        raise SourceBlocked('PRICES_AND_UNIVERSE_DIRECTORIES_REQUIRED')
    verify_input_files(packet, prices, universe)
    claim()
    try:
        rows, snapshots, index, dividends, sessions = load_inputs(packet, prices, universe)
        admission = read(ADMISSION)
        events, drops = cohort.build(index, dividends, snapshots, admission, sessions)
        stock = evaluate.assemble_stocks(rows, events, dividends, admission, sessions)
        cash, cash_meta = B.cash_returns(sessions)
        market = {**stock, 'sessions': sessions, 'etf': benchmark(sessions), 'cash': cash}
        result = {'studyId': STUDY, 'packetSha256': file_hash(CONTRACT), 'promotionEligible': False,
                  'events': events, 'sourceDrops': drops, 'cashMeta': cash_meta,
                  'fourCells': evaluate.evaluate_four_cells(events, market),
                  'portfolioComparison': {'status': 'SOURCE_BLOCKED', 'reason': 'COMPLETE_FROZEN_C2_LEDGER_MISSING'}}
        result['comparisonToSavedV1'] = evaluate.compare_saved(
            result['fourCells'], read(ROOT / 'research/broad_alpha_screen_v1/result-postoutcome-v1.json'),
            read(ROOT / 'research/broad_alpha_screen_v1/result-v1.json'))
        if admission.get('portfolioBundle'):
            # This file is inline in the hashed admission, never a mutable path.
            bundle = admission['portfolioBundle']
            try:
                extra = {t for r in bundle['decisions'] for t in r['weights'] if t not in ('ETF', 'CASH', '069500.KS')}
                extra.update(c['ticker'] for r in bundle['decisions'] for c in r['rankedCandidates']
                             if c['ticker'] not in ('ETF', 'CASH', '069500.KS'))
                ps = evaluate.assemble_stocks(rows, [], dividends, admission, sessions, extra_tickers=extra)
                pm = {**market, **ps, 'sessions': bundle['calendar']}
                if pm['sessions'] != [d for d in sessions if pm['sessions'][0] <= d <= pm['sessions'][-1]]:
                    raise SourceBlocked('PORTFOLIO_CALENDAR_NOT_COMPLETE')
                result['portfolioComparison'] = portfolio.compare(bundle, events, pm)
            except (SourceBlocked, KeyError, IndexError) as exc:
                result['portfolioComparison'] = {'status': 'SOURCE_BLOCKED', 'reason': str(exc)}
    except Exception as exc:
        result = {'studyId': STUDY, 'status': 'SPENT_SOURCE_OR_EXECUTION_BLOCKED',
                  'failure': str(exc), 'packetSha256': file_hash(CONTRACT), 'promotionEligible': False}
        with RESULT.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        raise
    with RESULT.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    return {'status': 'SPENT', 'resultSha256': file_hash(RESULT)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--mode', choices=('validate', 'prepare', 'execute'), default='validate')
    parser.add_argument('--prices', type=Path)
    parser.add_argument('--universe', type=Path)
    args = parser.parse_args(argv)
    result = prepare() if args.mode == 'prepare' else execute(args.prices, args.universe) if args.mode == 'execute' else validate()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
