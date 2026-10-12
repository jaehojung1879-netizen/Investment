"""Live terminal contracts; no replay execution or model fitting."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_node_presentation_contracts():
    assert shutil.which("node"), "Node is required to validate the deployed JavaScript"
    result = subprocess.run(
        ["node", "--test", "tests/research_terminal.test.cjs"], cwd=ROOT,
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_python_receipt_digest_matches_javascript_lexical_digest(tmp_path):
    """Independent oracle catches JS/Python float canonicalization drift."""
    from pipeline import weekly_decision as W
    receipt = {
        "name": "한국 \"회사\"", "weights": {"KR": 1.0}, "stockWeightPct": 0.0,
        "signedZero": -0.0, "nested": {"value": 1.5, "x": [True, None]},
        "generatedAt": "transport", "freshness": {"status": "FRESH"},
    }
    receipt["digest"] = W.receipt_digest(receipt)
    source = tmp_path / "receipt.jsonl"
    source.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
    result = subprocess.run([
        "node", "-e",
        "globalThis.crypto=require('node:crypto').webcrypto; const a=require('./app.js');"
        "a.parseReceipts(require('fs').readFileSync(process.argv[1],'utf8'))"
        ".then(r=>process.stdout.write(r[0].digest)).catch(e=>{console.error(e);process.exit(1)});",
        str(source),
    ], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == receipt["digest"]


@pytest.mark.parametrize("name", ["app.js", "index.html", "styles.css"])
def test_legacy_source_is_preserved_byte_for_byte(name):
    before = subprocess.check_output(["git", "show", f"8f45870cf8a0c41c5d32c3ec1296417de23c5db1:{name}"], cwd=ROOT)
    archived = (ROOT / "docs/archive/dashboard-v1" / name).read_bytes()
    assert hashlib.sha256(before).digest() == hashlib.sha256(archived).digest()


def test_pages_staging_requires_only_existing_deployed_frontend_files(tmp_path):
    workflow = (ROOT / ".github/workflows/pages.yml").read_text()
    assert "cp index.html styles.css app.js _site/" in workflow
    for name in ("index.html", "app.js", "styles.css"):
        shutil.copy(ROOT / name, tmp_path / name)
    html = (tmp_path / "index.html").read_text()
    assert 'src="app.js"' in html and 'href="styles.css"' in html
    assert "archive/dashboard-v1" not in html
    assert "<script src=\"https://" not in html


def test_sealed_build_publication_and_results_are_unchanged():
    paths = ["pipeline/build.py", "pipeline/weekly_decision.py", "pipeline/weekly_publish.py",
             "pipeline/weekly_history.py", "pipeline/validate.py", ".github/workflows/pages.yml",
             ".github/workflows/tests.yml", "config.json",
             "docs/weekly-decision/weekly-passive-first-v1-weekly-replay-corrected-benchmark.json",
             "docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json"]
    for path in paths:
        original = subprocess.check_output(["git", "show", f"8f45870cf8a0c41c5d32c3ec1296417de23c5db1:{path}"], cwd=ROOT)
        if path == "pipeline/weekly_publish.py":
            current = (ROOT / path).read_bytes()
            start = current.index(b"    # Additive research namespace.")
            end = current.index(b"    return 0\n", start)
            # v3 authorizes a separate append-only namespace only. Every
            # original P1 function/statement remains byte-identical outside it.
            assert current[:start] + current[end:] == original
            assert b"research-strategies" in current[start:end]
            continue
        if path == ".github/workflows/tests.yml":
            # The operational CI budget evolves independently of the terminal.
            # Permit exactly the owner-authorized timeout increase; all gates stay.
            original = original.replace(b"timeout-minutes: 30", b"timeout-minutes: 60", 1)
        assert (ROOT / path).read_bytes() == original, path
