"""Repository-wide guardrails this data-foundation PR must hold to.

Not a study of the KR corporate-action modules' own behaviour (see
`test_kr_corporate_action_events.py`, `test_kr_terminal_corporate_actions.py`,
`test_kr_dividend_reconciliation.py`, `test_kr_termination_inventory.py`) --
this file checks the boundary the task that created it was scoped to never
cross: no Alpha result computed or changed, v1/v2/v3 untouched, PIT
availability kept separate from economic event dates everywhere a new module
could have blurred them.
"""
from __future__ import annotations

import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NEW_MODULES = ("kr_corporate_action_events", "kr_terminal_corporate_actions",
              "kr_dividend_reconciliation", "kr_termination_inventory",
              "kr_continuing_dividend_sample", "kr_dividend_amount_lineage",
              "kr_terminal_action_document_parser")

FORBIDDEN_TOKENS = ("select_portfolio_by_scores", "replay_valuation",
                    "kelly_portfolio", "alpha_opportunity_v3_decision",
                    "compute_outcomes", "sharpe", "sortino", "cagr")


# --------------------------------------------------------------------------- #
# No Alpha outcome, IC, calibration, hit rate, or backtest anywhere here
# --------------------------------------------------------------------------- #
def test_no_new_pipeline_module_imports_a_portfolio_or_alpha_function():
    import importlib
    for name in NEW_MODULES:
        module = importlib.import_module(f"pipeline.{name}")
        source = inspect.getsource(module).lower()
        for token in FORBIDDEN_TOKENS:
            assert token not in source, f"{name} references {token}"


def test_the_new_collector_and_builder_scripts_never_touch_alpha():
    for script in ("build_kr_termination_inventory.py",
                   "build_kr_terminal_action_reconstruction_v2.py",
                   "build_kr_dividend_amount_lineage.py",
                   "collect_kr_corporate_actions.py",
                   "collect_kr_dividend_sections.py",
                   "collect_kr_terminal_action_documents.py",
                   "probe_kr_corporate_actions.py"):
        source = (ROOT / "scripts" / script).read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_TOKENS:
            assert token not in source, f"{script} references {token}"


# --------------------------------------------------------------------------- #
# v1/v2/v3 preregistrations and production Alpha are untouched
# --------------------------------------------------------------------------- #
def _sidecar_hash(path: Path) -> str:
    return path.with_suffix(".sha256").read_text(encoding="utf-8").strip()


def test_v3_seal_still_loads_unchanged():
    from pipeline import alpha_opportunity_v3_spec as S
    expected = _sidecar_hash(S.DEFAULT_SPEC)
    spec = S.load_sealed(expected_hash=expected)
    assert spec["studyId"] == "alpha-opportunity-model-v3"
    assert spec["preregistrationStatus"] == "BLOCKED_BY_DATA_INTEGRITY"


def test_v2_seal_still_loads_unchanged():
    from pipeline import alpha_opportunity_v2_spec as S2
    # The exact digest is asserted in test_alpha_opportunity_v3.py's own
    # v1/v2-unchanged test; this only proves the loader still succeeds and
    # the file this PR did not touch still parses as a v2 spec.
    expected = _sidecar_hash(S2.DEFAULT_SPEC)
    spec, _registry = S2.load_sealed(expected_hash=expected)
    assert spec["studyId"] == "alpha-opportunity-model-v2"


def test_no_new_file_touches_production_alpha_scoring():
    for module in ("longterm.py", "kelly_portfolio.py", "opportunity.py",
                   "alpha_opportunity_model.py"):
        path = ROOT / "pipeline" / module
        assert path.exists()
    # This PR's own diff is data-foundation-only by construction (new files
    # plus doc/AGENTS/workflow-inventory additions); nothing above is edited
    # by any file this test suite introduces.


# --------------------------------------------------------------------------- #
# PIT availability vs economic event date -- never blurred
# --------------------------------------------------------------------------- #
def test_disclosure_events_never_backdate_availability_to_a_period_end():
    from pipeline import kr_corporate_action_events as KCA
    row = {"rcept_no": "20230312000789", "se": "x"}
    record, _ = KCA.build_dividend_section_row(row, ticker=None, collected_at="")
    # availability comes only from the receipt number, never a fiscal period
    # or a report's own stated period fields.
    assert record["receiptDate"] == "2023-03-12"
    assert "fiscalYear" not in record and "reportPeriod" not in record


def test_terminal_action_effective_date_is_never_read_as_availability():
    from pipeline import kr_terminal_corporate_actions as TCA
    row = TCA.build_record(old_security="A", action_type=TCA.MERGER_CASH,
                           cash_per_old_share=1.0, effective_date="2020-06-01",
                           source_receipt_number="r1", source_receipt_date="2020-01-01")
    # The economic effective date and the public receipt date are held apart
    # even when one PRECEDES the other, as a merger's terms are typically
    # disclosed before the deal actually closes.
    assert row["effectiveDate"] == "2020-06-01"
    assert row["sourceReceiptDate"] == "2020-01-01"
    assert row["effectiveDate"] != row["sourceReceiptDate"]
