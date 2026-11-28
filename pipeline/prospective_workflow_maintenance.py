"""Validate the single bounded addition to the historical workflow inventory."""
from __future__ import annotations

import hashlib
from pathlib import Path

WORKFLOW = ".github/workflows/prospective-ops.yml"
INVENTORY = "docs/prospective-ops-workflow-inventory-ko.md"
INSTALL_BYTES = {
    WORKFLOW: "74efcd301b6f5c85c9f0e7541d431710dafc4c06a27377ed454e6e25e2f4371b",
    INVENTORY: "4825faa520d502c864ee4cb0ee9ec4ee95ebef2abeba2aa5ba2cf2993a29b7ce",
}


def verify_install(root: Path) -> None:
    """Every operation that admits the added path checks both exact live inputs."""
    for relative, expected in INSTALL_BYTES.items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"PROSPECTIVE_WORKFLOW_INSTALL_BYTES_CHANGED: {relative}")
