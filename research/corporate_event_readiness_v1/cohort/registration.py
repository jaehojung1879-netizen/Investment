"""Registration and owner authorization for PROSPECTIVE RECORDING only.

The spec (``kr-corporate-information-events-v1-candidate.json``) pins every code
file it depends on by SHA256. The authorization file pins the spec by SHA256
and records the repository owner's instruction. LIVE recording runs only if
both verify against the bytes on disk; any change to a pinned file stops it
(fail closed) until a new spec and a new authorization exist.

Scope is prospective recording. A historical outcome execution is NOT part of
this authorization and needs its own exact-hash approval.

Prospective boundary: ``prospective_receipt_core.first_prospective_session``
takes the instant from which recording was authorized and returns the first KR
session strictly after its KST date. That core names the instant
``merged_at_utc``; here it is the owner's authorization instant, because the
recorder runs from a scheduled task rather than a merged workflow (the
workflow inventories and ``ledger.yml`` are protected by sealed-study tests).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipeline import prospective_receipt_core as core

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = HERE / 'kr-corporate-information-events-v1-candidate.json'
AUTHORIZATION = HERE / 'AUTHORIZATION-prospective-recording.json'
SCOPE = 'PROSPECTIVE_RECORDING_ONLY'
LEDGER_RELATIVE = 'ledger/research-strategies/kr-corporate-information-events-v1/receipts.jsonl'


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(spec_path: Path = SPEC, authorization_path: Path = AUTHORIZATION, root: Path = ROOT) -> dict:
    """Return the verified authorization or raise; never a partial pass."""
    if not Path(authorization_path).is_file():
        raise ValueError('NO_REGISTERED_AUTHORIZATION')
    auth = json.loads(Path(authorization_path).read_text(encoding='utf-8'))
    spec = json.loads(Path(spec_path).read_text(encoding='utf-8'))
    if auth.get('scope') != SCOPE or auth.get('studyId') != spec.get('studyId'):
        raise ValueError('AUTHORIZATION_SCOPE_OR_STUDY_MISMATCH')
    if spec.get('status') != 'REGISTERED_PROSPECTIVE_RECORDING':
        raise ValueError('SPEC_NOT_REGISTERED')
    if auth.get('specSha256') != sha256(spec_path):
        raise ValueError('SPEC_CHANGED_AFTER_AUTHORIZATION')
    for relative, expected in spec['codeSha256'].items():
        target = Path(root) / relative
        if not target.is_file() or sha256(target) != expected:
            raise ValueError('PINNED_CODE_CHANGED:' + relative)
    authorized_at = auth.get('authorizedAtUtc')
    first = core.first_prospective_session(authorized_at)
    if auth.get('firstEligibleSignalSession') != first.strftime('%Y-%m-%d'):
        raise ValueError('FIRST_ELIGIBLE_SESSION_MISMATCH')
    return {**auth, 'authorizationSha256': sha256(authorization_path)}
