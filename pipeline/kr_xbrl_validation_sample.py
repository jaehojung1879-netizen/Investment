"""Metadata-only, deterministic sampling for original-XBRL source validation.

No production fact parser, amounts, market data or outcome artifacts are read
by the selector. File access is limited to explicit accounting shard paths.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re

STUDY = "kr-original-xbrl-value-validation-v1"
SEED = "KR_ORIGINAL_XBRL_VALUE_VALIDATION_V1"
FAMILIES = ("net_income", "operating_cash_flow", "assets", "liabilities")
ACCOUNTS = dict(zip(FAMILIES, ("당기순이익", "영업활동현금흐름", "자산총계", "부채총계")))
SOURCE_COMMIT = "fb6e83743fd8cdba647d1522a4645b662a9d5647"
MAIN_COMMIT = "d8e3caddb8a007cfd9842eedd5e751e054d267e4"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def permitted_path(root: Path, relative: str) -> Path:
    """Fail closed before opening; reject traversal, symlinks and outcome paths."""
    allowed = re.fullmatch(
        r"ledger/fundamentals/(?:kr-xbrl-original/dart-xbrl-2015|"
        r"kr-(?:canonical-v2|candidate-merged)/dart-[0-9]{4})\.jsonl\.gz", relative)
    if not allowed:
        raise ValueError("OUTCOME_OR_UNAPPROVED_PATH_REFUSED")
    root = root.resolve()
    path = root / relative
    if any(p.is_symlink() for p in [path, *path.parents] if p != root):
        raise ValueError("SYMLINK_REFUSED")
    if not path.resolve().is_relative_to(root):
        raise ValueError("PATH_ESCAPE_REFUSED")
    return path


def project_record(record):
    """Only explicit identity/provenance keys are accessed, never amounts.

    Account existence defines the stored-fact frame. Provenance status, numeric
    magnitude/sign and downstream coverage are NOT eligibility conditions.
    Missing provenance is retained and must later block, not shrink, the sample.
    """
    if record.get("source") != "DART:fnlttXbrl.xml:ORIGINAL":
        return []
    result = []
    for family, account in ACCOUNTS.items():
        if account not in record["accounts"]:
            continue
        entry = record["accounts"][account]
        provenance = record.get("canonicalization", {}).get("accounts", {}).get(account, {})
        result.append({
            "identity": record["id"] + ":" + family,
            "recordId": record["id"], "family": family, "account": account,
            "ticker": record["ticker"], "stockCode": record["stockCode"],
            "corpCode": record["corpCode"], "receiptNos": record["receiptNos"],
            "fiscalYear": record["fiscalYear"], "reportCode": record["reportCode"],
            "reportName": record.get("reportName"), "availableFrom": record.get("availableFrom"),
            "statement": entry.get("statement"), "element": entry.get("accountId"),
            "basis": provenance.get("statementBasis"), "contextRef": provenance.get("contextRef"),
            "unitRef": provenance.get("unitRef"), "decimals": provenance.get("decimals"),
            "currency": record.get("currency"),
            "zipSha256": record.get("canonicalization", {}).get("zipSha256"),
        })
    return result


def frame_from_file(root: Path):
    path = permitted_path(root, "ledger/fundamentals/kr-xbrl-original/dart-xbrl-2015.jsonl.gz")
    frame = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            frame.extend(project_record(json.loads(line)))
    frame.sort(key=lambda r: r["identity"])
    if len({r["identity"] for r in frame}) != len(frame):
        raise ValueError("DUPLICATE_FRAME_IDENTITY")
    return frame


def select(frame, per_family=15):
    """Round-robin families; balance actual report/basis/statement cells.

    Per family, choose a nonempty cell with fewest selections, tied by seeded
    SHA-256(cell). Within that cell minimize global issuer reuse, then seeded
    SHA-256(immutable fact identity). Neither frame order nor values matter.
    """
    if len({r["identity"] for r in frame}) != len(frame):
        raise ValueError("DUPLICATE_FRAME_IDENTITY")
    buckets = {}
    for row in frame:
        cell = (row["family"], row["reportCode"], row["basis"], row["statement"])
        buckets.setdefault(cell, []).append(row)
    totals = Counter(r["family"] for r in frame)
    if any(totals[f] < per_family for f in FAMILIES):
        raise ValueError("INSUFFICIENT_FRAME_REQUIRES_PRIOR_PROTOCOL_ADAPTATION")
    used, issuers, cells, sample = set(), Counter(), Counter(), []
    for _ in range(per_family):
        for family in FAMILIES:
            eligible = [c for c, rows in buckets.items() if c[0] == family
                        and any(r["identity"] not in used for r in rows)]
            cell = min(eligible, key=lambda c: (cells[c], digest([SEED, list(c)])))
            row = min((r for r in buckets[cell] if r["identity"] not in used),
                      key=lambda r: (issuers[r["corpCode"]], digest([SEED, r["identity"]])))
            sample.append(dict(row))
            used.add(row["identity"])
            issuers[row["corpCode"]] += 1
            cells[cell] += 1
    return sample


def sanitize_mixed_document(text):
    """Deliberately narrow instruction view: known operating commands only.

    Do not emit surrounding sentences/headings: keyword-based paragraph
    filtering can leak unlabelled performance narratives. All other mixed text
    is skipped; accounting-only files are inspected separately.
    """
    commands = ("ruff check .", "python -m compileall pipeline", "pytest -q", "git diff --check")
    result = ["Recognized repository checks:"]
    result.extend("- " + c for c in commands if c in text)
    if "Never merge directly to `main`" in text:
        result.append("- Never merge directly to main.")
    result.append("Other mixed text withheld; use narrower accounting sources.")
    return "\n".join(result) + "\n"
