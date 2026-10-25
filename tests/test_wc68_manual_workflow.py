"""Guardrails for the manual DART WC68 source-only workflow.

These tests never request a key, call DART, read a market outcome, or run the
workflow. They pin the manual-only and no-raw-artifact safety boundary.
"""
from pathlib import Path

WORKFLOW = (Path(__file__).parents[1] / ".github/workflows/fundamentals.yml").read_text(
    encoding="utf-8"
)


def _wc68_job():
    return WORKFLOW.split("\n  kr-wc68-original:\n", 1)[1].split(
        "\n  # READ-ONLY diagnostic:", 1
    )[0]


def test_wildcard_schedule_cannot_run_wc68():
    assert WORKFLOW.count("  kr-wc68-original:") == 1
    assert "github.event_name == 'workflow_dispatch'" in _wc68_job()
    assert "inputs.target == 'wc-originals-68'" in _wc68_job()
    assert "inputs.region == 'kr'" in _wc68_job()
    assert "github.ref == 'refs/heads/main'" in _wc68_job()


def test_daily_kr_collector_excludes_wc68_manual_target():
    assert "inputs.target != 'wc-originals-68'" in WORKFLOW
    assert '"wc-originals-68"' in WORKFLOW
    assert "kr-wc68-original:" in WORKFLOW


def test_collection_is_source_only_without_secret_or_public_bytes():
    job = _wc68_job()
    assert "contents: read" in job
    assert "persist-credentials: false" in job
    assert "secrets.DART" not in job
    assert "--collect --output \"$RUNNER_TEMP/wc68-originals\"" in job
    assert "newHistoricalLabelsRead" in job
    assert "sourceAdmissionAuthorized" in job
    assert "wc68-source-summary.json" in job
    assert "wc68-input-coverage.json" in job
    # ZIP objects and full source manifest must remain runner-ephemeral.
    artifact = job.split("      - name: Upload source-only diagnostics", 1)[1]
    assert "wc68-originals" not in artifact
    assert ".zip" not in artifact
    assert "signal-history" not in job.split(
        "      - name: Collect and inspect fixed original receipts", 1
    )[1]
    assert "workflow_dispatch" not in artifact  # no self-trigger
