"""CLI: verify (default), build the approval packet, or execute the ONE authorized run.

    python -m research.corporate_event_readiness_v1.cohort.outcome.run            # verify
    python -m research.corporate_event_readiness_v1.cohort.outcome.run --packet   # rebuild packet
    python -m research.corporate_event_readiness_v1.cohort.outcome.run --execute \
        --authorization AUTH.json --inputs MANIFEST.json --out RESULT.json

``--execute`` refuses, before reading any market file, unless: the registered
spec and every inherited value verify; the authorization pins the exact
registered-spec SHA256, the exact packet SHA256 and the exact phrase; every
harness file matches the packet; every required input is ADMITTED; and no
result exists. A refusal reads no outcome.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from pathlib import Path

from . import contract as C
from . import inputs as I

HERE = Path(__file__).resolve().parent
PACKET = HERE / 'historical-execution-packet-v1.json'
READINESS = HERE / 'execution-readiness-v1.json'
RESULT = C.COHORT_DIR / 'data' / 'historical-outcome-result-v1.json'
HARNESS_FILES = ('__init__.py', 'contract.py', 'engine.py', 'inference.py', 'decision.py', 'study.py',
                 'inputs.py', 'readiness.py', 'run.py')
PHRASE = 'APPROVE KR_PHASE_D_NEW_AXIS_EXCEPTION kr-corporate-information-events-v1 {spec} PACKET {packet}'


class Refused(SystemExit):
    pass


def harness_hashes() -> dict[str, str]:
    root = HERE.parents[3]
    return {str((HERE / f).relative_to(root)): C.sha256_file(HERE / f) for f in HARNESS_FILES}


def build_packet() -> dict:
    inherited = C.verify_registered()
    readiness = json.loads(READINESS.read_text(encoding='utf-8'))
    admission = I.admit(None)
    packet = {
        'studyId': C.STUDY_ID, 'contract': 'HISTORICAL_EXECUTION_APPROVAL_PACKET_V1',
        'status': 'PREPARED_BLOCKED_BY_SOURCE' if admission['blocked'] else 'PREPARED_READY_FOR_OWNER',
        'registeredSpec': {'path': str(C.REGISTERED_SPEC.relative_to(HERE.parents[3])),
                           'sha256': inherited['registeredSpecSha256']},
        'prospectiveAuthorizationSha256': C.sha256_file(C.COHORT_DIR / 'AUTHORIZATION-prospective-recording.json'),
        'harnessCodeSha256': harness_hashes(),
        'readinessSha256': C.sha256_file(READINESS),
        'pinnedLargestPitIndustryForRemovalCheck': readiness['pinnedLargestPitIndustryForRemovalCheck'],
        'frozenParameters': {
            'horizons': dict(C.HORIZONS), 'primaryHorizon': C.PRIMARY_HORIZON, 'meeDelta': dict(C.MEE),
            'familySlots': list(C.FAMILY_SLOTS), 'fwer': C.FWER, 'simultaneousLevel': C.SIMULTANEOUS_LEVEL,
            'bootstrap': {'draws': C.BOOTSTRAP['draws'], 'seed': C.BOOTSTRAP['seed'],
                          'block': dict(C.BOOTSTRAP['block']),
                          'sensitivityBlocks': {k: list(v) for k, v in C.BOOTSTRAP['sensitivityBlocks'].items()}},
            'hacLag': dict(C.HAC_LAG), 'beta': dict(C.BETA), 'costMultipliers': list(C.COST_MULTIPLIERS),
            'costs': {k: (list(map(list, v)) if k == 'sellTaxSchedule' else v) for k, v in C.COSTS.items()},
            'valueUp': C.VALUE_UP, 'recentConcentration': list(C.RECENT_CONCENTRATION),
            'benchmark': C.BENCHMARK,
        },
        'engineeringChoicesForOwnerReview': list(C.ENGINEERING_CHOICES),
        'inputAdmission': admission,
        'scope': ('ONE historical execution of A1 and B1 (H126 primary, H252 descriptive), A2 descriptive '
                  'contrast, over the frozen cohort-events-v1; no re-run, no threshold, window, cost or '
                  'universe change; result class EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY'),
        'preconditions': [
            'every inputAdmission component ADMITTED by a separate source PR with a non-author audit',
            'non-author independent review of this harness at these exact hashes',
            'formal run from merged main through a workflow holding a durable one-shot lock ref',
            'Owner authorization file pinning registeredSpec.sha256 and this packet SHA256 with the phrase',
        ],
        'outcomesReadToBuildThisPacket': 0,
    }
    return packet


def write_packet() -> str:
    packet = build_packet()
    raw = (json.dumps(packet, ensure_ascii=False, indent=1, sort_keys=True) + '\n').encode('utf-8')
    PACKET.write_bytes(raw)
    digest = C.sha256_file(PACKET)
    PACKET.with_suffix('.sha256').write_text(f'{digest}  {PACKET.name}\n', encoding='utf-8')
    return digest


def verify() -> dict:
    inherited = C.verify_registered()
    packet = json.loads(PACKET.read_text(encoding='utf-8'))
    problems = []
    if packet['registeredSpec']['sha256'] != inherited['registeredSpecSha256']:
        problems.append('REGISTERED_SPEC_CHANGED')
    if packet['harnessCodeSha256'] != harness_hashes():
        problems.append('HARNESS_CODE_CHANGED')
    if packet['readinessSha256'] != C.sha256_file(READINESS):
        problems.append('READINESS_CHANGED')
    return {'packetSha256': C.sha256_file(PACKET), 'problems': problems,
            'status': packet['status'], 'blocked': packet['inputAdmission']['blocked']}


def _refuse(code: str, **extra) -> None:
    print(json.dumps({'refused': code, 'outcomesRead': 0, **extra}, ensure_ascii=False, indent=1))
    raise Refused(2)


def execute(authorization: Path, manifest: Path, out: Path) -> dict:
    state = verify()
    if state['problems']:
        _refuse('PACKET_VERIFICATION_FAILED', problems=state['problems'])
    if out.exists() or RESULT.exists():
        _refuse('RESULT_ALREADY_EXISTS_ONE_SHOT_SPENT')
    if not authorization or not Path(authorization).is_file():
        _refuse('NO_OWNER_AUTHORIZATION')
    auth = json.loads(Path(authorization).read_text(encoding='utf-8'))
    spec_sha = json.loads(PACKET.read_text(encoding='utf-8'))['registeredSpec']['sha256']
    want = PHRASE.format(spec=spec_sha, packet=state['packetSha256'])
    if (auth.get('phrase') != want or auth.get('packetSha256') != state['packetSha256']
            or auth.get('registeredSpecSha256') != spec_sha):
        _refuse('AUTHORIZATION_DOES_NOT_PIN_THIS_PACKET', expectedPhrase=want)
    admission = I.admit(manifest)
    if admission['blocked']:
        _refuse('SOURCE_BLOCKED', blocked=admission['blocked'])
    if os.environ.get('GITHUB_REF') != 'refs/heads/main':
        _refuse('FORMAL_RUN_ONLY_FROM_MAIN_WORKFLOW')
    # ---- only past this line is any market value read
    from . import study
    market, events, chars, pinned = _load_admitted(Path(manifest))
    result = study.evaluate(events, market, pinned_industry=pinned, characteristics=chars)
    result['packetSha256'] = state['packetSha256']
    tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True, default=float) + '\n',
                   encoding='utf-8')
    os.replace(tmp, out)
    return result


def _load_admitted(manifest: Path):
    """Admitted component files are JSON (optionally gzip) in the schema the admission contract names."""
    doc = json.loads(manifest.read_text(encoding='utf-8'))
    base = manifest.parent

    def read(name):
        p = base / doc['components'][name]['path']
        raw = p.read_bytes()
        return json.loads(gzip.decompress(raw) if p.suffix == '.gz' else raw)
    market = {'sessions': read('tradability')['sessions'], 'levels': read('stockTotalReturn'),
              'etf': read('benchmarkTotalReturn069500'), 'cash': read('investableKrwCash'),
              'tradable': {k: set(v) for k, v in read('tradability')['tradable'].items()},
              'terminal': read('terminalConsideration')}
    from . import readiness as R
    intervals = read('pitIndustry')
    events = {}
    for e in R.load_events():
        h = e.get('hypothesis')
        if h in ('A1', 'B1', 'A2'):
            label, _ = R.industry_at(intervals, e['stock_code'], e['signalSession'])
            events.setdefault(h, []).append({**e, 'ticker': f"{e['stock_code']}.KS", 'industry': label})
    pinned = json.loads(PACKET.read_text(encoding='utf-8'))['pinnedLargestPitIndustryForRemovalCheck']
    return market, events, read('matchingCharacteristics'), pinned


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--packet', action='store_true')
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--authorization', type=Path)
    ap.add_argument('--inputs', type=Path)
    ap.add_argument('--out', type=Path, default=RESULT)
    args = ap.parse_args(argv)
    if args.packet:
        print(write_packet())
        return 0
    if args.execute:
        execute(args.authorization, args.inputs, args.out)
        return 0
    state = verify()
    print(json.dumps(state, ensure_ascii=False, indent=1))
    return 1 if state['problems'] else 0


if __name__ == '__main__':
    sys.exit(main())
