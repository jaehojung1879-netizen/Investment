"""Invented benchmark paths and safe preparation/one-shot refusal checks."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_alpha_atlas_benchmark_audit as B
from pipeline import kr_alpha_atlas_integrity_audit as A
from pipeline.kr_alpha_atlas_phase_c import contract, labels, lifecycle, models, preflight

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_closure_and_protected_files_are_unchanged():
    spec = contract.load()
    assert contract.file_hash(ROOT / contract.SPEC) == "b57be30ce54abf1dd26388954053e99d4b1bf71fa06f3598787317e953988db0"
    assert contract.digest(spec["dependencyHashes"]) == "5e71455a3f01c1796ac99d5e7b66b30baa7c2982c62cb5ea1013201892f91820"
    assert len(spec["dependencyHashes"]) == 113
    assert len(spec["protectedHashes"]) == 235
    assert spec["benchmarkIntegrity"]["claimGate"] == "BLOCKED_UNVERIFIED"
    assert not any("integrity_audit" in p or "benchmark_audit" in p for p in spec["dependencyHashes"])


@pytest.mark.parametrize("target", [labels.build_labels, labels.formal_permit, models.predictions,
                                    models.ridge_fit, models.incremental, lifecycle.GitHub.claim])
def test_firewall_refuses_targets_fits_analysis_and_lock(target):
    # Resolve inside the guard: a saved callable would bypass monkeypatching.
    module = __import__(target.__module__, fromlist=[target.__name__])
    with pytest.raises(RuntimeError, match="AUDIT_FIREWALL_WAS_TRIGGERED"):
        with A.outcome_free_firewall() as attempts:
            function = getattr(lifecycle.GitHub, "claim") if target.__name__ == "claim" else getattr(module, target.__name__)
            with pytest.raises(RuntimeError, match="FORBIDDEN"):
                function()
            assert len(attempts) == 1
    assert all(v == 0 for v in vars(A.AuditCounters()).values())


def test_benchmark_recipe_does_not_double_count_and_has_distinct_cash_reinvestment():
    p = pd.Series([100.0, 90.0, 99.0], index=["2022-01-03", "2022-01-04", "2022-01-05"])
    cash = [{"exDate": "2022-01-04", "cashKrwPerUnit": 10.0}]
    q = B.adjusted_index(p, cash)
    assert q.tolist() == pytest.approx([1, 1, 1.1])
    # Price moves after the distribution distinguish the two economic recipes.
    p.iloc[1] = 99
    assert B.adjusted_index(p, cash).iloc[1] == pytest.approx(1.1)
    assert B.adjusted_index(p, cash, shareholder=True).iloc[1] == pytest.approx(1.09)
    with pytest.raises(ValueError, match="ONLY_REGISTERED"):
        B.adjusted_index(p, cash, ticker="000030.KS")


def test_missing_price_and_invalid_cash_are_never_zero_payoff():
    p = pd.Series([100.0, np.nan], index=["2022-01-03", "2022-01-04"])
    with pytest.raises(ValueError, match="MISSING_OR_INVALID"):
        B.adjusted_index(p, [])
    p.iloc[1] = 90
    with pytest.raises(ValueError, match="DISTRIBUTION_NOT_BELOW"):
        B.adjusted_index(p, [{"exDate": "2022-01-04", "cashKrwPerUnit": 100}])


@pytest.mark.parametrize("difference,status", [(0.0049, "PASS"), (0.0051, "FAIL")])
def test_existing_threshold_on_identical_sessions(difference, status):
    days = pd.to_datetime(["2021-12-30", "2022-01-03", "2022-01-04"])
    p = pd.Series([1, 1, 1.1 + difference], index=[str(d.date()) for d in days])
    q = pd.Series([1, 1, 1.1], index=p.index)
    result = B.annual_comparison(p, q, days, [2022], coverage_from="2021-01-01", cutoff="2022-01-04")[0]
    assert result["status"] == status
    assert result["matchingSessions"] == 2
    assert result["differencePercentagePoints"] == pytest.approx(difference * 100)


def test_unmatched_sessions_and_unknown_distributions_block_comparison():
    days = pd.to_datetime(["2021-12-30", "2022-01-03", "2022-01-04"])
    p = pd.Series([1, 1, 2], index=[str(d.date()) for d in days])
    for q, coverage in [(p.drop("2022-01-03"), "2021-01-01"), (p, "2022-01-03"), (p, None)]:
        r = B.annual_comparison(p, q, days, [2022], coverage_from=coverage, cutoff="2022-01-04")[0]
        assert r["status"] == "INSUFFICIENT_DATA"
        assert r["independentReturn"] is None and r["differencePercentagePoints"] is None


def test_distribution_uses_ex_session_not_payment_and_future_dates_do_not_snap_to_cutoff(tmp_path):
    p = tmp_path / "cash.json"
    p.write_text(json.dumps({"dividList": [{"basicD": "20220106", "payD": "20220110", "dividA": "10"}]}))
    rows = B.issuer_distributions(p, pd.bdate_range("2022-01-03", "2022-01-10"))
    assert rows[0]["exDate"] == "2022-01-05"
    assert rows[0]["paymentDate"] == "2022-01-10"
    assert [r for r in rows if r["exDate"] <= "2022-01-04"] == []


def test_snapshot_mutation_refused_before_returns(tmp_path):
    p = tmp_path / "prices.json"
    p.write_text("original")
    manifest = {"ticker": B.TICKER, "files": {"price": {"path": p.name, "sha256": contract.file_hash(p)}}}
    (tmp_path / "sources.json").write_text(json.dumps(manifest))
    B.verified_sources(tmp_path)
    p.write_text("mutated")
    with pytest.raises(ValueError, match="DIGEST_CHANGED"):
        B.verified_sources(tmp_path)


def test_audit_persistence_uses_exact_byte_writer(tmp_path):
    assert A.persistence_probe(tmp_path)["differentBytesRefused"]


@pytest.mark.parametrize("reason", ["MISSING_GIT", "ARTIFACT_DOWNLOAD", "CHECKSUM", "MATRIX_DIGEST",
                                    "PYTHON", "DEPENDENCY", "MEMORY", "WALL_TIME", "SYNTHETIC"])
def test_registered_order_preparation_failure_cannot_consume(reason):
    calls = []

    def preparation():
        calls.append("prepare")
        raise RuntimeError(reason)

    with pytest.raises(RuntimeError, match=reason):
        lifecycle.ordered_once(checks=lambda: calls.append("checks"), prepare=preparation,
                               claim=lambda: calls.append("lock"), run=lambda *_: calls.append("outcomes"),
                               on_failure=lambda *_: calls.append("failure"))
    assert calls == ["checks", "prepare"]


@pytest.mark.parametrize("failure", ["PARTIAL_LOCK_API", "PERSISTENCE", "AMBIGUOUS_LOCK"])
def test_registered_order_post_claim_failure_never_retries(failure):
    state = {"claims": 0, "failures": 0}

    def claim():
        state["claims"] += 1  # invented local receipt, no real GitHub write
        if failure != "PERSISTENCE":
            raise RuntimeError(failure)
        return SimpleNamespace(verified=True)

    def run(*args):
        raise RuntimeError(failure)

    def failed(*args):
        state["failures"] += 1

    with pytest.raises(RuntimeError, match=failure):
        lifecycle.ordered_once(checks=lambda: None, prepare=lambda: None,
                               claim=claim, run=run, on_failure=failed)
    assert state == {"claims": 1, "failures": 1}


def test_pages_provisions_pinned_history_before_tests():
    text = (ROOT / ".github/workflows/pages.yml").read_text()
    assert "fetch-depth: 0" in text
    for commit in ["fb6e83743fd8cdba647d1522a4645b662a9d5647", "4ea107ed0cde289f0a049a65ff13d2441a786710"]:
        assert text.index("origin " + commit) < text.index("run: pytest -q")
    assert "run: pytest -q" in text


def test_runtime_mismatch_refuses_before_input_preparation(tmp_path, monkeypatch):
    spec = contract.load()
    calls = []
    main = A.git(ROOT, "merge-base", "HEAD", "origin/main")
    github = SimpleNamespace(main=lambda: main, previous_results=lambda *_: False, locks=lambda *_: [])
    monkeypatch.setattr(A.contract, "load", lambda *_: spec)
    monkeypatch.setattr(preflight, "prepare", lambda *_: calls.append("prepare"))
    monkeypatch.setattr(preflight.platform, "python_version", lambda: "WRONG_VERSION")
    with pytest.raises(ValueError, match="PINNED_PYTHON"):
        A.audited_preflight(ROOT, tmp_path / "audit", main, github=github)
    assert calls == []


def test_real_source_snapshots_hashes_only_no_ci_return_analysis():
    source_dir = ROOT / "docs/audits/kr-alpha-atlas-phase-c-integrity/sources"
    assert B.verified_sources(source_dir)["issuerFundId"] == "2ETF01"
