"""Offline, exact-byte packet verification. This never fetches or admits a study."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MANIFEST = "packet-receipts.json"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def packet_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()
                  and "__pycache__" not in p.parts and p.name != MANIFEST)


def verify(root: Path = ROOT) -> dict:
    """Detect missing, added, tampered or escaping files; no implicit network."""
    receipts = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    expected, errors = set(), []
    for row in receipts["files"]:
        relative = row["path"]
        path = PurePosixPath(relative)
        if (path.is_absolute() or ".." in path.parts or "\\" in relative
                or path.as_posix() != relative or relative in expected):
            raise ValueError("INVALID_OR_DUPLICATE_PACKET_PATH")
        expected.add(relative)
        target = root / relative
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
            errors.append("PATH_ESCAPE:" + relative)
        elif not target.is_file():
            errors.append("MISSING:" + relative)
        else:
            raw = target.read_bytes()
            if len(raw) != row["bytes"] or digest(raw) != row["sha256"]:
                errors.append("DIGEST_MISMATCH:" + relative)
    actual = {p.relative_to(root).as_posix() for p in packet_files(root)}
    errors.extend("UNRECEIPTED:" + p for p in sorted(actual - expected))
    return {"status": "VERIFIED_BYTES" if not errors else "FAILED", "files": len(expected),
            "errors": errors, "researchAdmission": False, "economicReadiness": False}


def verify_fixed_filings(root: Path = ROOT) -> dict:
    """Replay actual retained filings, independently of stored parser output."""
    from .filings import load_filing, parse_filing

    evidence = root / "evidence"
    samples = json.loads((evidence / "filing-samples.json").read_text(encoding="utf-8"))["samples"]
    rows = []
    for sample in samples:
        row = parse_filing(load_filing(evidence, sample), sample)
        row.pop("raw_table_rows", None)
        rows.append(row)
    saved = json.loads((evidence / "parsed-filing-samples.json").read_text(encoding="utf-8"))
    if saved != rows:
        raise ValueError("PARSED_FIXED_SAMPLE_NOT_REPRODUCIBLE")
    return {"fixedFilingSamples": len(rows),
            "issuers": len({r["issuer_id"] for r in rows}),
            "parseStatuses": dict(sorted(Counter(r["parse_status"] for r in rows).items())),
            "eligibilityStatuses": dict(sorted(Counter(r["data_eligibility"] for r in rows).items())),
            "parsedSnapshotReproduced": True,
            "scope": "PURPOSIVE_PARSER_FIXTURE_NOT_EMPIRICAL_SAMPLE_OR_POWER_N"}


if __name__ == "__main__":
    result = verify()
    if not result["errors"]:
        result["filings"] = verify_fixed_filings()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["errors"]))
