"""Inspect existing WID identity/action metadata; never read quotes or labels.

Default prints the plan. --inspect explicitly reads the fixed local Git source
allowlist and prints evidence, without admitting any claim or writing a permit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import winner_inflection_admission as A  # noqa: E402
from pipeline import winner_inflection_filing_review as F  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402


def inspect(root):
    source = S.Sources(root)
    spec = json.loads((Path(root) / A.SPEC_PATH).read_bytes())
    manifest = json.loads(source.blob(S.SOURCE_COMMIT, S.MANIFEST))
    if A.IF.digest({k: v for k, v in manifest.items() if k != "sha256"}) != spec["sourceManifestSha256"]:
        raise ValueError("SOURCE_MANIFEST_CHANGED")
    start, through = spec["sourceWindow"]["priceStart"], spec["sourceWindow"]["priceThrough"]
    selected = {name: refs for name, refs in manifest["components"].items()
                if name.startswith("corporate-events/20") and start[:7] <= name.split("/")[1] <= through[:7]}
    metadata_roles = ("price/source", "benchmark/source", "corporate-events/source")
    source.allowed_objects = {ref for refs in selected.values() for ref in refs}
    source.allowed_objects.update(ref for role in metadata_roles for ref in manifest["components"].get(role, []))
    lineage = {role: [source.component(ref) for ref in manifest["components"].get(role, [])] for role in metadata_roles}
    spy_events = []
    for refs in selected.values():
        for ref in refs:
            for row in source.component(ref):
                if row["ticker"] == "SPY" and start <= row["date"] <= through:
                    spy_events.append((row["date"], row.get("dividend", 0), row.get("split", 1)))
    try:
        F.require_spy_action_history(spy_events, start, through)
        necessary_gate = "PRESENT_NOT_COMPLETENESS_CERTIFIED"
    except ValueError as error:
        necessary_gate = str(error)
    identities = list(csv.DictReader(io.StringIO(gzip.decompress(source.local(S.US_IDENTITY)).decode())))
    sectors = source.json(S.SECTORS)["snapshots"]
    category_counts = Counter(row.get("sp500IdentityCategory", "") for row in identities)
    admitted = [r for r in identities if r.get("sp500IdentityCategory") in spec["acceptedIdentityCategories"]]
    bad_sectors = [{"date": snap["date"], "ticker": ticker, "value": row.get("cik")}
                   for snap in sectors for ticker, row in snap.get("rows", {}).items()
                   if row.get("cik") is not None and F.normalized_cik(row["cik"]) is None]
    return {
        "schema": "WID_UNRESOLVED_SOURCE_EVIDENCE_V3", "status": "BLOCKED",
        "sourceCommit": S.SOURCE_COMMIT, "metadataCommit": S.CODE_BASE,
        "specSha256": A.IF.digest(spec), "inspectorSha256": A.file_sha(Path(__file__)),
        "rights": {"status": "UNRESOLVED", "checkedLineageRoles": list(metadata_roles),
                   "finding": "Examined lineage names vendors and transformations, not an affirmative retention/reuse grant. Public access, existing Git bytes and code licenses do not resolve rights.",
                   "required": "Source-specific stock/SPY/actions, Finnhub and community metadata rights evidence covering this internal historical use; no Tiingo retention workaround."},
        "identity": {"status": "UNRESOLVED", "metadataRows": len(identities),
                     "categories": dict(sorted(category_counts.items())), "inScopeCategoryRows": len(admitted),
                     "inScopeMissingOrMalformedCik": sum(F.normalized_cik(r.get("cik")) is None for r in admitted),
                     "malformedDatedCik": bad_sectors,
                     "required": "Dated issuer AND share-class provenance of each admitted price panel. Matching issuer CIKs cannot certify which security produced the prices.",
                     "fix": "Missing, zero and malformed CIKs fail closed; no ticker or issuer substitution. The 2023 malformed source row is outside this fixed 2020 signal window."},
        "returnBasis": {"status": "UNRESOLVED", "monthlyActionComponents": len(selected),
                        "spyActionRows": len(spy_events), "spyDividendRows": sum(dividend > 0 for _, dividend, _ in spy_events),
                        "necessaryReconstructionGate": necessary_gate,
                        "required": "Native stock/SPY quote provenance, currency/share units, complete distributions and actions with independent evidence. Existing index plus missing SPY actions cannot be inverted into native prices.",
                        "fix": "Loader rejects missing SPY distribution history before native-price reconstruction. Presence of one event is necessary, never sufficient proof of completeness."},
        "lineage": lineage, "sourceReceipts": source.receipts,
        "outcomeReads": 0, "quotePayloadReads": 0, "modelFits": 0,
        "claimsAccepted": [], "executionAuthorization": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    result = inspect(ROOT) if args.inspect else {
        "status": "PLAN_ONLY", "sourceReads": 0, "outcomeReads": 0, "modelFits": 0,
        "plan": "Read only fixed local manifest, lineage, corporate-action and identity metadata; no quotes, labels, admission or execution."}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
