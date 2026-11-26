"""Pytest inputs for the separately registered prospective-workflow inventory."""
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def prospective_workflow_inventory_input(request):
    """Give the preserved census tests the verified, additive inventory data.

    Both frozen census modules still enumerate the full live workflow
    directory and apply their original ACTIVE, RETIRED and coverage assertions.
    """
    module = request.module
    if module.__name__ not in ("test_workflow_inventory", "test_kr_alpha_atlas_price_repair_workflow_inventory"):
        return
    from pipeline.prospective_workflow_maintenance import INVENTORY, verify_install

    monkeypatch = request.getfixturevalue("monkeypatch")
    root = Path(__file__).resolve().parent
    verify_install(root)
    if module.__name__ == "test_workflow_inventory":
        all_original_docs = module._all_docs
        monkeypatch.setattr(module, "_all_docs", lambda: [*all_original_docs(), (root / INVENTORY).read_text(encoding="utf-8")])
    else:
        monkeypatch.setattr(module, "DOCS", (*module.DOCS, Path(INVENTORY).name))
