"""Bugs from real runs that no other test caught, each pinned directly so it
cannot silently come back the same way: run #1's CLI rejected the exact
input shape GitHub Actions actually sends and its failure was invisible in
the workflow's own conclusion; run #2's `main()` crashed on its very first
line of real work, `load_config()`, because nothing had ever called it the
way `main()` does (`cfg, _ = load_config()` — it returns a
`(Config, warnings)` tuple, not a bare `Config`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pipeline import replay_inputs as RI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_regional_rotation_replay as RUNNER  # noqa: E402


def test_lookback_days_accepts_the_float_shaped_string_actions_sends():
    """workflow_dispatch's `type: number` inputs arrive as "252.0", not
    "252" — this is exactly what run #1's argparse call rejected."""
    parser = RUNNER.build_arg_parser()
    args = parser.parse_args(["some/ledger", "--lookback-days", "252.0"])
    assert args.lookback_days == 252
    assert isinstance(args.lookback_days, int)


def test_lookback_days_still_accepts_a_plain_integer_string():
    parser = RUNNER.build_arg_parser()
    args = parser.parse_args(["some/ledger", "--lookback-days", "126"])
    assert args.lookback_days == 126


def test_lookback_days_rejects_something_that_is_not_a_number_at_all():
    parser = RUNNER.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["some/ledger", "--lookback-days", "not-a-number"])


@pytest.mark.skipif(
    not (ROOT / ".github/workflows/regional-rotation.yml").exists(),
    reason="regional-rotation.yml was retired from Active Actions by "
           "workflow-hygiene-live-data-fixes-v1 (the study it ran, "
           "regional-rotation-v1, is closed and published — see "
           "docs/workflow-inventory.md); the file and this regression are "
           "still in git history if the workflow is ever restored.")
def test_the_workflow_sets_pipefail_before_piping_into_tee():
    """Without it, bash -e only sees tee's own exit code, so a script that
    fails before printing anything still reports the step (and the whole
    job) as successful — exactly what happened in run #1: a 4-second
    argparse failure came back green.

    Read as plain text, not parsed as YAML: PyYAML is not a listed
    dependency (`requirements.txt`), only incidentally present in some
    environments, and this check does not need a real parse — just that
    the one `run:` block that pipes into `tee` sets pipefail first.
    """
    text = (ROOT / ".github/workflows/regional-rotation.yml").read_text()
    marker = "Run the regional rotation analysis"
    assert marker in text
    block = text[text.index(marker):text.index(marker) + 1200]
    assert "| tee" in block, "this test is pinned to the piped-into-tee shape; update it if that changes"
    assert "set -o pipefail" in block
    # Order matters: pipefail has to take effect before the pipeline it protects.
    assert block.index("set -o pipefail") < block.index("| tee")


def test_main_gets_past_config_loading_on_a_real_config(tmp_path):
    """Run #2's actual crash, reproduced without needing real frozen replay
    data: point `main()` at an empty ledger dir so `_load_frozen` raises its
    own clean "no frozen inputs" error, and confirm `main()` reaches that
    error rather than dying on `cfg.historical_replay` first. This exercises
    `load_config()` for real (the repo's own `config.json`, not a stub), the
    same call `main()` makes, so an unpacking mistake in that specific line
    is caught here instead of only in a run against real data.
    """
    with pytest.raises(RI.InputVersionConflict, match="no frozen inputs"):
        RUNNER.main([str(tmp_path)])
