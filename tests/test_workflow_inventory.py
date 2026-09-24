"""`docs/workflow-inventory.md` describes `.github/workflows/` accurately.

The whole point of that document is that an operator can trust it instead of
reading the Actions menu directly — a stale ACTIVE row (naming a workflow
that no longer exists) or a RETIRED row that quietly came back would defeat
that. This pins the two directions mechanically rather than by review.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
DOC = ROOT / "docs" / "workflow-inventory.md"

_YML_NAME = re.compile(r"[A-Za-z0-9][\w.-]*\.yml")


def _section(text: str, heading: str) -> str:
    """The text between one `## heading` and the next `## `, or end of file."""
    start = text.index(f"## {heading}")
    rest = text[start + len(f"## {heading}"):]
    m = re.search(r"\n## ", rest)
    return rest[:m.start()] if m else rest


def _actual_workflow_files() -> set[str]:
    return {p.name for p in WORKFLOWS_DIR.glob("*.yml")}


def test_the_inventory_doc_exists():
    assert DOC.is_file(), "docs/workflow-inventory.md is required by workflow-hygiene-live-data-fixes-v1"


def test_every_workflow_file_on_disk_is_mentioned_somewhere_in_the_doc():
    text = DOC.read_text(encoding="utf-8")
    mentioned = set(_YML_NAME.findall(text))
    on_disk = _actual_workflow_files()
    missing = on_disk - mentioned
    assert not missing, f"workflow file(s) not documented anywhere: {sorted(missing)}"


def test_every_active_row_names_a_workflow_that_actually_exists():
    text = DOC.read_text(encoding="utf-8")
    active = _section(text, "ACTIVE")
    named = set(_YML_NAME.findall(active))
    on_disk = _actual_workflow_files()
    missing = named - on_disk
    assert not missing, (
        f"docs/workflow-inventory.md's ACTIVE table names workflow(s) that do "
        f"not exist in .github/workflows/: {sorted(missing)}")


def test_no_active_workflow_file_is_missing_from_the_active_table():
    """The inverse direction: every file that actually runs unconditionally
    or on a schedule (not routed through Probes) should be listed as ACTIVE,
    not left implicit."""
    text = DOC.read_text(encoding="utf-8")
    active_named = set(_YML_NAME.findall(_section(text, "ACTIVE")))
    on_disk = _actual_workflow_files()
    # probes.yml is its own ACTIVE row (the dispatcher) even though the
    # sources it probes are documented in the ON-DEMAND PROBES table by
    # probe name, not by workflow filename.
    missing = on_disk - active_named
    assert not missing, (
        f"workflow file(s) present on disk but not listed in the ACTIVE "
        f"table: {sorted(missing)}")


def test_no_retired_workflow_filename_still_exists_on_disk():
    text = DOC.read_text(encoding="utf-8")
    retired = _section(text, "RETIRED RESEARCH")
    retired_names = set(_YML_NAME.findall(retired))
    on_disk = _actual_workflow_files()
    resurrected = retired_names & on_disk
    assert not resurrected, (
        f"workflow(s) documented as RETIRED but still present in "
        f".github/workflows/: {sorted(resurrected)}")


def test_retired_table_lists_no_currently_active_workflow():
    """Guards against a copy-paste naming an ACTIVE workflow in the RETIRED
    table by mistake."""
    text = DOC.read_text(encoding="utf-8")
    active_names = set(_YML_NAME.findall(_section(text, "ACTIVE")))
    retired_names = set(_YML_NAME.findall(_section(text, "RETIRED RESEARCH")))
    overlap = active_names & retired_names
    assert not overlap, f"listed as both ACTIVE and RETIRED: {sorted(overlap)}"
