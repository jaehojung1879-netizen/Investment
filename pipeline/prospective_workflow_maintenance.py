"""Validate the single bounded addition to the historical workflow inventory."""
from __future__ import annotations

import hashlib
from pathlib import Path

WORKFLOW = ".github/workflows/prospective-ops.yml"
INVENTORY = "docs/prospective-ops-workflow-inventory-ko.md"
INSTALL_BYTES = {
    WORKFLOW: "888ebca76c55fda7196b9326e8f550e210410a34e72267bf5c5a63a08683f6ae",
    INVENTORY: "4825faa520d502c864ee4cb0ee9ec4ee95ebef2abeba2aa5ba2cf2993a29b7ce",
}


def verify_install(root: Path) -> None:
    """Every operation that admits the added path checks both exact live inputs."""
    for relative, expected in INSTALL_BYTES.items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"PROSPECTIVE_WORKFLOW_INSTALL_BYTES_CHANGED: {relative}")
