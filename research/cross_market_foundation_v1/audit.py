"""Offline verification of the handoff packet; never a study execution entrypoint.

Run from the repository root:
  python -m research.cross_market_foundation_v1.audit
  python -m research.cross_market_foundation_v1.audit --source-bytes

The optional second command needs the exact referenced Git objects locally.
Neither command fetches data, evaluates outcomes, writes a ledger, or promotes
research readiness. Exit zero means a consistent packet, not source admission.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .provenance import verify_file_receipts, verify_receipt_inventory, verify_source_pin

STATUSES = {"READY", "PARTIAL", "SOURCE_BLOCKED", "RIGHTS_BLOCKED", "UNDERPOWERED"}
LAYERS = {"Market", "Industry", "Stock", "Portfolio"}
REGIONS = {"KR", "US"}


def validate_readiness(matrix: dict, package_root: Path) -> list[str]:
    """Require actionable recovery conditions with evidence, never empty green."""
    errors = []
    if matrix.get("historicalOutcomeExecuted") is not False or matrix.get("executionAuthorized") is not False:
        errors.append("SPRINT_OUTCOME_BOUNDARY_VIOLATED")
    rows = matrix.get("cells", [])
    keys = [(r.get("region"), r.get("layer")) for r in rows]
    if len(keys) != 8 or set(keys) != {(r, layer) for r in REGIONS for layer in LAYERS}:
        errors.append("EIGHT_UNIQUE_MARKET_LAYER_CELLS_REQUIRED")
    for row in rows:
        label = str(row.get("region")) + ":" + str(row.get("layer"))
        if row.get("status") not in STATUSES:
            errors.append("INVALID_READINESS_STATUS:" + label)
        if row.get("newOutcomeRunnable") is not False:
            errors.append("NO_SPRINT_OUTCOME_EXECUTION_PERMISSION:" + label)
        if not row.get("scope") or not row.get("availableWithoutOutcome"):
            errors.append("READINESS_SCOPE_AND_IMPLEMENTED_WORK_REQUIRED:" + label)
        blockers = row.get("blockers", [])
        if row.get("status") != "READY" and not blockers:
            errors.append("BLOCKER_REQUIRED:" + label)
        if row.get("status") == "READY" and blockers:
            errors.append("READY_WITH_UNRESOLVED_BLOCKER:" + label)
        for blocker in blockers:
            if (not blocker.get("code") or not blocker.get("recoveryCondition")
                    or not blocker.get("evidence") or blocker.get("priority") not in ("P0", "P1", "P2")):
                errors.append("UNVERIFIABLE_BLOCKER:" + label)
            for name in blocker.get("evidence", []):
                # Evidence references must be retained packet-relative files.
                path = (package_root / name).resolve()
                if not path.is_relative_to(package_root.resolve()) or not path.is_file():
                    errors.append("BLOCKER_EVIDENCE_UNAVAILABLE:" + label + ":" + name)
    return errors


def audit_packet(repo: Path, *, source_bytes: bool = False) -> dict:
    package = repo / "research/cross_market_foundation_v1"
    evidence = package / "evidence"
    receipt_manifest = json.loads((evidence / "evidence-receipts.json").read_text())
    receipts = verify_file_receipts(package, receipt_manifest["files"])
    matrix = json.loads((evidence / "readiness-matrix.json").read_text())
    errors = validate_readiness(matrix, package)
    errors.extend(verify_receipt_inventory(package, receipt_manifest["files"]))
    errors.extend(row["status"] + ":" + row["path"] for row in receipts if row["status"] != "VERIFIED_BYTES")
    source_results = []
    if source_bytes:
        pins = json.loads((evidence / "source-pins.json").read_text())["sources"]
        source_results = [verify_source_pin(repo, pin) for pin in pins]
        errors.extend(row["status"] + ":" + row["path"] for row in source_results if row["status"] != "VERIFIED_BYTES")
    return {"packetStatus": "CONSISTENT" if not errors else "PACKET_INVALID",
            "meaning": "packet integrity only; no research admission or execution permission",
            "historicalOutcomeExecuted": False, "executionAuthorized": False,
            "retainedReceiptsVerified": len(receipts), "gitSourcesVerified": len(source_results),
            "readinessCells": [{k: row[k] for k in ("region", "layer", "status")} for row in matrix["cells"]],
            "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-bytes", action="store_true", help="verify pinned Git bytes already present locally")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    try:
        result = audit_packet(repo, source_bytes=args.source_bytes)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"packetStatus": "PACKET_INVALID", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["packetStatus"] == "CONSISTENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
