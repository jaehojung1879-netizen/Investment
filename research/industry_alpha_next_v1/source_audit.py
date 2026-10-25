"""Offline metadata audit of retained sources; no historical labels or fits built.

Read sealed result files only as bytes for SHA verification. Do not import any
pipeline module, execute a collector, or reconstruct an industry return.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

PINS = {
    "data/kr-industry-membership-foundation-v3/state/audit.json.gz":
        "8ad466de34144d7e9863798bd43cd42b192ec92e00fcfd80c0cbaf9b4ddd6104",
    "data/kr-industry-membership-foundation-v4/state/audit.json.gz":
        "4135846f16dcf59fe4ff89ab83b3b5aec288dea20fed36172b17abf768d44036",
    "data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz":
        "f49c15a0ebcd371c9a407118abb6ef350bba2060227ca40d61ba210fc4f81a74",
    "docs/results/kr-industry-opportunity-anatomy-v1-result.json":
        "71a960e3c19ce443d058508c4ec66576e3e5fcbd7a45dc851cf8b832bff62a08",
    "docs/results/kr-stock-within-industry-anatomy-v1-result.json":
        "3862c390a52f6f19abaa7849e41620858cd154735136647ee36c958624c2739f",
}
CANONICAL_TODAY = frozenset(("Communication Services", "Consumer Discretionary", "Consumer Staples",
                           "Energy", "Financials", "Health Care", "Industrials", "Information Technology",
                           "Materials", "Real Estate", "Utilities"))


def sector_schema_audit(data):
    """Today's vocabulary is a schema diagnostic, never a historical crosswalk."""
    summaries = []
    for snap in data["snapshots"]:
        labels = Counter(row.get("sector") for row in snap["rows"].values())
        summaries.append({"date": snap["date"], "sourceCommit": snap["sourceCommit"],
                          "sourceColumn": snap["sectorColumn"], "rows": len(snap["rows"]),
                          "distinctLabelsIncludingNull": len(labels), "blankRows": labels[None],
                          "outsideTodayVocabularyRows": sum(n for label, n in labels.items()
                                                             if label not in CANONICAL_TODAY),
                          "membersWithoutRow": snap["membersWithoutRow"],
                          "rawCsvSha256": snap["rawCsvSha256"]})
    return {"snapshots": len(summaries), "collectorFailures": data["failures"],
            "storedRows": sum(s["rows"] for s in summaries),
            "blankRows": sum(s["blankRows"] for s in summaries),
            "snapshotsWithMemberRowGaps": sum(bool(s["membersWithoutRow"]) for s in summaries),
            "snapshotsOutsideTodayVocabulary": sum(s["outsideTodayVocabularyRows"] > 0 for s in summaries),
            "outsideTodayVocabularyRows": sum(s["outsideTodayVocabularyRows"] for s in summaries),
            "vocabularyWarning": "Legacy names are not necessarily errors; no historical mapping inferred.",
            "bySnapshot": summaries}


def audit(root):
    verified = {}
    metadata = {}
    for path, expected in PINS.items():
        raw = (root / path).read_bytes()
        observed = hashlib.sha256(raw).hexdigest()
        if observed != expected:
            raise ValueError("SOURCE_HASH_MISMATCH: " + path)
        verified[path] = {"sha256": observed, "bytes": len(raw)}
        if path.endswith(".gz"):
            metadata[path] = json.loads(gzip.decompress(raw))
    v3, v4, us = (metadata[p] for p in list(PINS)[:3])
    return {
        "schema": "INDUSTRY_ALPHA_METADATA_AUDIT_V1",
        "auditedMain": "b589d658eedd3c47f555df20db86f37792ee3358",
        "evidenceClass": "SOURCE_METADATA_AND_EXISTING_SEAL_HASHES_ONLY",
        "verifiedInputs": verified,
        "kr": {"decision": v4["decision"], "nameDates": v4["nameDates"],
               "classified": v4["classifiedNameDates"], "unknown": v4["unknownNameDates"],
               "statusCounts": v4["nameDateStatus"], "terminal": v4["terminal"],
               "terminalUnknownSecurities": sorted(k for k, v in v4["absent28"]["perSecurity"].items()
                                                   if "terminalActionType" in v),
               "preferredUnknownSecurities": sorted(k for k, v in v4["absent28"]["perSecurity"].items()
                                                    if v["status"] == "UNKNOWN" and "terminalActionType" not in v),
               "demonstrablyPublicEventNameDatesV3": v3["pitKnownEventNameDates"],
               "taxonomySelected": v4["taxonomySelection"]["selected"],
               "fractionInSufficientGroups": v4["fractionInSufficientGroups"],
               "groupTotalsNameDates": v4["groupTotals"], "annual": v4["annual"]},
        "us": sector_schema_audit(us),
        "executionCapability": "NONE; this file does not construct or evaluate any historical target",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(audit(args.root), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
