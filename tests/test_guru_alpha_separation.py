"""Mechanical guardrail: Main Alpha never imports the Guru Decision Atlas.

This is not a promise in a docstring. `guru_13f_store` and
`security_identity` are DATA FOUNDATION for a future, separate research
line — no factor weight, selector, Kelly parameter, or scoring path may read
from either, ever, not even as an unused import. Parsed with `ast` rather
than grepped for text, so a multiline or aliased import cannot slip past a
line-oriented pattern.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_MODULES = {"guru_13f_store", "security_identity"}

# Main Alpha: production scoring and the daily build that assembles it.
GUARDED_FILES = (
    "pipeline/longterm.py",
    "pipeline/opportunity.py",
    "pipeline/kelly_portfolio.py",
    "pipeline/build.py",
)


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.rsplit(".", 1)[-1])
            # `from . import guru_13f_store` carries the name on the alias,
            # not on `module`, so both forms are checked.
            for alias in node.names:
                names.add(alias.name)
    return names


def test_no_guarded_main_alpha_file_imports_the_guru_atlas():
    violations = []
    for relative in GUARDED_FILES:
        path = ROOT / relative
        assert path.exists(), f"expected guarded file missing: {relative}"
        found = _imported_module_names(path) & FORBIDDEN_MODULES
        if found:
            violations.append((relative, sorted(found)))
    assert not violations, f"Main Alpha imports the Guru Decision Atlas: {violations}"


def test_the_forbidden_modules_themselves_still_exist_so_this_guard_is_not_vacuous():
    for module_name in FORBIDDEN_MODULES:
        assert (ROOT / "pipeline" / f"{module_name}.py").exists()


def test_guru_modules_never_import_a_main_alpha_scoring_module_either():
    """Belt and suspenders: the dependency arrow should not run the other
    way either — a data-foundation module has no reason to import the
    scorer it is deliberately kept out of."""
    scoring_modules = {"longterm", "opportunity", "kelly_portfolio"}
    for module_name in FORBIDDEN_MODULES:
        path = ROOT / "pipeline" / f"{module_name}.py"
        found = _imported_module_names(path) & scoring_modules
        assert not found, f"{module_name}.py imports a Main Alpha module: {found}"
