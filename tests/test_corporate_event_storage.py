"""Lossless preservation, bounded decompression and original Git-byte oracle."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from research.corporate_event_readiness_v1.filings import load_filing

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'research/corporate_event_readiness_v1/evidence'
SAMPLES = json.loads((EVIDENCE / 'filing-samples.json').read_text())['samples']
ORIGINAL = '9a81b61da4a0493142447920f8bd8269ab8a33a8'


@pytest.mark.parametrize('meta', SAMPLES, ids=lambda m: m['rcept_no'])
def test_preserved_original_git_bytes_and_parser_input(meta):
    raw = load_filing(EVIDENCE, meta)
    old = subprocess.check_output([
        'git', 'show', ORIGINAL + ':research/corporate_event_readiness_v1/evidence/'
        + meta['rcept_no'] + '.html',
    ], cwd=ROOT)
    assert raw == old
    assert len(raw) == meta['bytes']
    assert hashlib.sha256(raw).hexdigest() == meta['sha256']
    raw.decode('cp949')
    with pytest.raises(UnicodeDecodeError):
        raw.decode('utf-8')


def fixture(root, raw=b'SYN_ONLY', packed=True):
    no = '20260101000001'
    name = no + ('.html.gz' if packed else '.html')
    stored = gzip.compress(raw, mtime=0) if packed else raw
    (root / name).write_bytes(stored)
    return {'rcept_no': no, 'file': name, 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(),
            'storage': 'gzip' if packed else 'identity',
            'storedBytes': len(stored), 'storedSha256': hashlib.sha256(stored).hexdigest()}


def test_uncompressed_fixed_body_remains_supported(tmp_path):
    meta = fixture(tmp_path, packed=False)
    assert load_filing(tmp_path, meta) == b'SYN_ONLY'


def test_stored_byte_tamper_is_rejected(tmp_path):
    meta = fixture(tmp_path)
    (tmp_path / meta['file']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='STORED_BODY_IDENTITY_MISMATCH'):
        load_filing(tmp_path, meta)


def test_repacked_wrong_original_is_rejected(tmp_path):
    meta = fixture(tmp_path)
    stored = gzip.compress(b'OTHER_SYN', mtime=0)
    (tmp_path / meta['file']).write_bytes(stored)
    meta.update(storedBytes=len(stored), storedSha256=hashlib.sha256(stored).hexdigest())
    with pytest.raises(ValueError, match='ORIGINAL_BODY_IDENTITY_MISMATCH'):
        load_filing(tmp_path, meta)


def test_decompression_cannot_exceed_declared_original_size(tmp_path):
    meta = fixture(tmp_path, raw=b'x' * 100_000)
    meta['bytes'] = 8
    with pytest.raises(ValueError, match='ORIGINAL_BODY_IDENTITY_MISMATCH'):
        load_filing(tmp_path, meta)


@pytest.mark.parametrize('size', [True, -1, 0, 1_000_001, '8'])
def test_invalid_original_size_is_rejected(tmp_path, size):
    meta = fixture(tmp_path)
    meta['bytes'] = size
    with pytest.raises(ValueError, match='BOUNDED_ORIGINAL_BODY_SIZE_REQUIRED'):
        load_filing(tmp_path, meta)


def test_receipt_path_escape_and_symlink_are_rejected(tmp_path):
    meta = fixture(tmp_path)
    with pytest.raises(ValueError, match='FIXED_DART_BODY_PATH_REQUIRED'):
        load_filing(tmp_path, {**meta, 'file': '../' + meta['file']})
    target = tmp_path / meta['file']
    target.unlink()
    target.symlink_to(tmp_path / 'missing')
    with pytest.raises(ValueError, match='BODY_PATH_ESCAPE'):
        load_filing(tmp_path, meta)


def test_invalid_gzip_container_is_rejected(tmp_path):
    meta = fixture(tmp_path)
    raw = b'not gzip'
    (tmp_path / meta['file']).write_bytes(raw)
    meta.update(storedBytes=len(raw), storedSha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match='INVALID_BODY_GZIP'):
        load_filing(tmp_path, meta)
