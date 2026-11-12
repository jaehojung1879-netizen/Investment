"""Local provenance receipts cannot activate writers or replace prior evidence."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cli(monkeypatch):
    spec = importlib.util.spec_from_file_location('closed_provenance_cli', ROOT / 'scripts/audit_closed_atlas_provenance.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, 'inspect', lambda *a, **k: {'status': 'SYN_CLOSED_PROVENANCE', 'formalExecutionAuthorized': False})
    return mod


def invoke(cli, path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['provenance', '--expected-main', '0' * 40, '--work', str(path)])
    return cli.main()


def test_duplicate_same_receipt_is_a_noop_and_failure_cannot_replace_success(cli, tmp_path, monkeypatch):
    invoke(cli, tmp_path, monkeypatch)
    target = tmp_path / 'closed-study-provenance.json'
    before = target.read_bytes()
    invoke(cli, tmp_path, monkeypatch)
    assert target.read_bytes() == before

    def failure(*a, **k):
        raise ValueError('SYN_API_REFUSED')

    monkeypatch.setattr(cli, 'inspect', failure)
    with pytest.raises(ValueError, match='PROVENANCE_RECEIPT_ALREADY_EXISTS_WITH_DIFFERENT_BYTES'):
        invoke(cli, tmp_path, monkeypatch)
    assert target.read_bytes() == before


def test_failed_receipt_stays_failed_and_does_not_become_a_new_execution_permit(cli, tmp_path, monkeypatch):
    def failure(*a, **k):
        raise ValueError('SYN_LOCK_UNAVAILABLE')
    monkeypatch.setattr(cli, 'inspect', failure)
    with pytest.raises(SystemExit) as e:
        invoke(cli, tmp_path, monkeypatch)
    assert e.value.code == 1
    raw = (tmp_path / 'closed-study-provenance.json').read_bytes()
    assert b'CLOSED_STUDY_PROVENANCE_REFUSED' in raw and b'NOT_RUN' in raw
    monkeypatch.setattr(cli, 'inspect', lambda *a, **k: {'status': 'SYN_DIFFERENT'})
    with pytest.raises(ValueError, match='PROVENANCE_RECEIPT_ALREADY_EXISTS_WITH_DIFFERENT_BYTES'):
        invoke(cli, tmp_path, monkeypatch)
    assert (tmp_path / 'closed-study-provenance.json').read_bytes() == raw


@pytest.mark.parametrize('path', [ROOT / 'data', Path('/tmp'), ROOT.parent / 'outside-repository'])
def test_repository_shared_temp_or_other_workspace_output_is_rejected_before_inspection(cli, path, monkeypatch):
    monkeypatch.setattr(cli, 'inspect', lambda *a, **k: pytest.fail('Must refuse before inspecting anything'))
    with pytest.raises(SystemExit) as e:
        invoke(cli, path, monkeypatch)
    assert e.value.code == 2


def test_receipt_symlink_never_writes_or_reuses_another_file(cli, tmp_path, monkeypatch):
    actual = tmp_path / 'unchanged.json'
    actual.write_bytes(b'unchanged')
    (tmp_path / 'closed-study-provenance.json').symlink_to(actual)
    with pytest.raises(ValueError, match='PROVENANCE_RECEIPT_SYMLINK_REFUSED'):
        invoke(cli, tmp_path, monkeypatch)
    assert actual.read_bytes() == b'unchanged'
