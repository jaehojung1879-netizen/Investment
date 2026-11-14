"""Exact current repair packet. A blocked packet cannot authorize a real refit."""
import json
from pathlib import Path

from .identity import HERE, code_identity, digest, environment, file_hash, git_commit, write_once
from .refit import CONFIG, MODELS


def build(source_admission):
    return {'studyId': CONFIG['studyId'], 'mode': 'B_FIXED_CANDIDATES_REFIT_ONLY',
            'codeCommit': git_commit(), 'code': code_identity(), 'configSha256': digest(CONFIG),
            'configFileSha256': file_hash(HERE / 'config.json'), 'sourceAdmissionSha256': digest(source_admission),
            'environment': environment(), 'requiredXgboostForRealRefit': '3.4.1',
            'candidates': CONFIG['candidates'], 'models': MODELS, 'allowNewWinner': False,
            'sourceReady': source_admission.get('status') == 'COMPLETE_VERIFIED_SHAREHOLDER_INPUTS',
            'formalAtlasExecutionAllowed': False, 'anyLockWriteAllowed': False, 'productionWriteAllowed': False,
            'status': 'BLOCKED_SOURCE_NOT_AUTHORIZED',
            'authorizationRule': 'Fresh public Owner exact-hash approval; current source block remains independently gating',
            'rebuildRequiredIfAnyCodeConfigSourceModelFoldEnvironmentChanges': True}


def main(run_directory):
    p = Path(run_directory)
    raw = json.loads((p / 'source-admission.json').read_text())
    admission = {'status': 'SOURCE_BLOCKED', 'sourceHashes': raw['sourceHashes'], 'stockAdmission': raw['admission'],
                 'correctedMatrixSha256': None, 'matrixTickers': None,
                 'reason': 'COMPLETE_STOCK_CASH_ACTION_TERMINAL_INPUTS_AND_CORRECTED_MATRIX_MISSING'}
    packet = build(admission)
    sha = digest(packet)
    write_once(HERE / 'refit-source-readiness.json', admission)
    write_once(HERE / 'refit-execution-packet.json', packet)
    write_once(HERE / 'refit-approval-template.json', {'authorized': False, 'packetSha256': sha,
               'approvalCommentId': None, 'approvalCommentSha256': None, 'authorizedAtUtc': None,
               'requiredLiteralLine': 'AUTHORIZE_ML_TOURNAMENT_V2_REFIT ' + sha,
               'sourceBlockCannotBeWaived': True})
    print(sha)


if __name__ == '__main__':
    import sys
    main(sys.argv[1])
