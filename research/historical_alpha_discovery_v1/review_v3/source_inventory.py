"""Hash-verify already stored demerger documents; no quote/label/strategy run.

Search is a document inventory, not automatic entitlement extraction. Even a
ratio in a subsidiary's unrelated 2019 transaction cannot value parent rights
in the selected 2023/2024 holding intervals.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
from html import unescape
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
BASE = Path("data/kr-industry-membership-foundation-v2/acquired-dart/annual")
TARGETS = ("009830.KS", "012450.KS")
TERMS = ("분할비율", "분할 비율", "신주배정", "신주 배정", "단수주", "0.898651", "0.90028")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect(root=ROOT):
    root = Path(root)
    sections, manifests = [], {}
    for path in sorted((root / BASE).glob("*/manifest-originals.json")):
        doc = json.loads(path.read_bytes())
        records = [r for r in doc["records"] if r.get("target", {}).get("ticker") in TARGETS]
        if not records:
            continue
        archive = path.parent / doc["archive"]
        raw = archive.read_bytes()
        if sha(raw) != doc["archiveSha256"]:
            raise ValueError("ARCHIVE_DIGEST_MISMATCH:" + str(archive))
        bodies = json.loads(gzip.decompress(raw))
        manifests[str(path.relative_to(root))] = {"sha256": sha(path.read_bytes()),
            "archive": str(archive.relative_to(root)), "archiveSha256": sha(raw)}
        for record in records:
            for section in record.get("sections", []):
                decoded = base64.b64decode(bodies[section["sha256"]], validate=True)
                if sha(decoded) != section["sha256"]:
                    raise ValueError("SECTION_DIGEST_MISMATCH:" + section["sha256"])
                text = re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", unescape(decoded.decode("utf8", errors="replace"))))
                hits = [{"term": term, "excerpt": text[max(0, hit.start() - 120):hit.end() + 350]}
                        for term in TERMS for hit in list(re.finditer(re.escape(term), text))[:10]]
                sections.append({"ticker": record["target"]["ticker"], "fiscalYear": record["target"]["fiscalYear"],
                    "receipts": record["target"]["receiptNos"], "sectionSha256": section["sha256"],
                    "urls": [r["url"] for r in record.get("responses", []) if r.get("sha256") == section["sha256"]],
                    "charactersSearched": len(text), "mentions": hits})
    if {row["ticker"] for row in sections} != set(TARGETS):
        raise ValueError("REQUIRED_STORED_ISSUER_SOURCES_MISSING")
    return {"schema": "KR_STORED_DEMERGER_SOURCE_INVENTORY_V3", "status": "BLOCKED",
        "codeSha256": sha(Path(__file__).read_bytes()), "sectionCount": len(sections),
        "sourceScope": "Only already stored annual company-summary/share sections, not all DART filings or complete corporate-action history.",
        "findings": [
            {"ticker": "009830.KS", "entry": "2022-10-19", "exit": "2023-04-19",
             "status": "BLOCKED_DISTRIBUTED_SECURITY_ECONOMICS",
             "finding": "The ratio mention located in FY2019 concerns subsidiary Hanwha Global Asset/Q CELLS, not this parent's 2023 Galleria entitlement. No substitution.",
             "required": ["parent-to-distributed-security entitlement and unit/record/delivery dates", "cash-in-lieu settlement", "452260 executable quotes and distributions for the required interval", "explicit valuation policy during suspensions"]},
            {"ticker": "012450.KS", "entry": "2024-04-30", "exit": "2024-11-07",
             "status": "BLOCKED_DISTRIBUTED_SECURITY_ECONOMICS",
             "finding": "Stored annual sections corroborate the demerger, but do not establish complete rights. Parent share-count contraction and vendor factor are not shareholder consideration.",
             "required": ["exact 489790 entitlement, parent cancellation and units", "record/delivery and cash-in-lieu settlement", "distributed-security marks and distributions", "explicit valuation policy during suspensions"]}],
        "manifests": manifests, "sections": sections,
        "entitlementCertified": False, "newReturnCalculations": 0, "quoteReads": 0,
        "formalStudyExecution": False, "originalResultsChanged": False,
        "strategyPathStatus": "UNCHANGED_INCOMPLETE_NO_CAGR_SHARPE_MDD"}


if __name__ == "__main__":
    print(json.dumps(inspect(), ensure_ascii=False, indent=2, allow_nan=False))
