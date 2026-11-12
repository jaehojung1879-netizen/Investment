"""Content identities and immutable writes, independent of file existence."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import importlib.metadata

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment():
    names = ('numpy', 'pandas', 'scipy', 'scikit-learn', 'lightgbm', 'xgboost', 'exchange-calendars', 'threadpoolctl', 'joblib')
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {'python': platform.python_version(), 'machine': platform.machine(), 'packages': versions,
            'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'PYTHONHASHSEED')}}


def code_identity():
    from .vendor.input_pins_328 import repository_imports
    paths = [p for p in HERE.rglob('*.py') if '__pycache__' not in p.parts]
    paths += [ROOT / 'research/ml_strategy_tournament_v1/tournament.py',
              ROOT / 'research/ml_strategy_tournament_independent_audit_v1/check_cash.py',
              ROOT / 'research/ml_strategy_tournament_independent_audit_v1/recompute.py',
              ROOT / 'pipeline/replay_calendar.py']
    closure = repository_imports(ROOT, [str(p.relative_to(ROOT)) for p in paths])
    return {p: file_hash(ROOT / p) for p in closure}



def git_commit():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def identity(config, sources, model, fold):
    return {'code': code_identity(), 'config': config, 'sources': sources, 'model': model,
            'fold': fold, 'environment': environment()}


def write_once(path, value):
    path = Path(path)
    raw = canonical(value) + b'\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('IMMUTABLE_RESULT_IDENTITY_CONFLICT:' + str(path))
    else:
        with path.open('xb') as f:
            f.write(raw)
    return hashlib.sha256(raw).hexdigest()


def cache_write(path, key, payload):
    return write_once(path, {'identity': key, 'identitySha256': digest(key),
                             'payload': payload, 'payloadSha256': digest(payload)})


def cache_read(path, expected):
    doc = json.loads(Path(path).read_text())
    if doc['identity'] != expected or doc['identitySha256'] != digest(expected):
        raise ValueError('CACHE_IDENTITY_MISMATCH')
    if doc['payloadSha256'] != digest(doc['payload']):
        raise ValueError('CACHE_PAYLOAD_CORRUPT')
    return doc['payload']
