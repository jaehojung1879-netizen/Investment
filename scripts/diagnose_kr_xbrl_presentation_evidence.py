"""Outcome-free presentation-evidence diagnostic on a deterministic 12-fact subset.

Not a validation run: it reproduces the v2 reader's result, keeps the raw ZIPs
for inspection and decomposes where the presentation chain breaks. It repairs
nothing and changes no validation contract. Exit 0 = diagnostic completed,
4 = process/transport failure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_xbrl_presentation_diagnostic as D  # noqa: E402
from pipeline import kr_xbrl_value_validation as V  # noqa: E402
from pipeline import kr_xbrl_value_validation_v2 as V2  # noqa: E402
from scripts import validate_kr_original_xbrl_values as V1CLI  # noqa: E402

SPEC = "research_specs/" + D.STUDY + ".json"


def load_spec():
    spec = json.loads((ROOT / SPEC).read_text(encoding="utf-8"))
    protocol_v1, protocol_v2, sample = V2.load_frozen(ROOT)  # v1/v2 bytes, ancestry, sample SHA
    if spec["frozen"]["sampleSha256"] != V.SAMPLE_SHA256 or spec["frozen"]["v2ProtocolSha256"] != V2.PROTOCOL_SHA256:
        raise ValueError("DIAGNOSTIC_SPEC_DISAGREES_WITH_FROZEN_HASHES")
    subset = D.select_subset(sample["items"])
    if subset != spec["subset"]["identities"]:
        raise ValueError("SUBSET_NOT_REPRODUCED_FROM_FROZEN_METADATA")
    return spec, protocol_v1, sample, subset


def run(input_root, source_dir, raw_dir, download, materialize):
    spec, protocol_v1, sample, subset = load_spec()
    by = {i["identity"]: i for i in sample["items"]}
    items = [by[i] for i in subset]
    if materialize:
        V1CLI.materialize(input_root, protocol_v1)
    V.verify_frame(input_root, protocol_v1, sample)
    values = V1CLI.candidate_values(input_root, protocol_v1, sample)
    access = V1CLI.download_sources(source_dir, {"items": items}) if download else {"status": "LOCAL_SOURCE_ONLY"}
    raw_dir.mkdir(parents=True, exist_ok=True)
    diagnoses, retrieved = [], 0
    for item in items:
        try:
            path = V1CLI.source_path(source_dir, item, ".zip")
            if not path.exists():
                diagnoses.append({"identity": item["identity"], "error": "ZIP_NOT_RETRIEVED"})
                continue
            raw = path.read_bytes()
            retrieved += 1
            shutil.copyfile(path, raw_dir / path.name)
            diag = D.diagnose_item(item, raw)
            diag["zipMatchesFrozenSha256"] = diag["zipSha256"] == item["zipSha256"]
            index = V1CLI.source_path(source_dir, item, ".filing.json")
            rows = json.loads(index.read_text()) if index.exists() else None
            v2 = V2.validate_item(item, values[item["identity"]], raw, rows)
            diag["v2Reproduction"] = {"classification": v2["classification"], "reason": v2["reason"]}
            fact = diag["trace"]
            diag["identityEvidence"] = {
                "uniqueFactPointer": fact.get("instancePointerMatches") == 1,
                "entityIsFrozenCorpCode": fact.get("context", {}).get("entity") == item["corpCode"],
                "unitRefMatches": fact.get("unitRef") == item["unitRef"],
                "decimalsMatch": fact.get("decimals") == item["decimals"],
                "rawTextEqualsCandidateDescriptive": str(fact.get("rawText", "")).strip() ==
                    str(values[item["identity"]]).rstrip("0").rstrip(".") or
                    str(fact.get("rawText", "")).strip() == str(values[item["identity"]]).split(".")[0],
            }
            diagnoses.append(diag)
        except Exception as exc:  # keep diagnosing the others
            diagnoses.append({"identity": item["identity"], "error": type(exc).__name__})
    good = [d for d in diagnoses if "error" not in d]
    return {"study": D.STUDY, "startingMain": spec["startingMain"], "sampleSha256": V.SAMPLE_SHA256,
            "subset": subset, "sourceAccess": access, "zipsRetrieved": retrieved,
            "summary": D.summarize(good) if good else None, "hypotheses": D.HYPOTHESES,
            "diagnoses": diagnoses, "alphaOutcomesUsed": False, "candidateRepaired": False,
            "v1v2Modified": False}


def echo(report):
    """Compact per-item lines for the job log (secrets never appear in any field)."""
    print("summary", json.dumps(report["summary"], sort_keys=True))
    for d in report["diagnoses"]:
        if "error" in d:
            print("item", json.dumps(d))
            continue
        t = d["trace"]
        print("item", json.dumps({
            "identity": d["identity"], "basis": d["basis"], "files": [(f["name"], f["type"], f["size"]) for f in d["files"]],
            "readerEvidence": d["currentReaderPresentationEvidenceCount"], "firstBreak": t.get("firstBreak"),
            "v2": d["v2Reproduction"], "identity_evidence": d["identityEvidence"],
            "networks": d["presentationNetworks"][:25], "roleTypes": [(r["roleURI"], r["definition"][:100], r["usedOn"]) for r in d["roleTypes"][:40]],
            "references": [(r["kind"], r["href"][:160], r["scope"]) for r in d["references"][:30]],
            "matchedLocs": t.get("matchedLocs", [])[:6], "zipShaMatchesFrozen": d["zipMatchesFrozenSha256"],
            "concepts": d["localConceptIdCount"]}, ensure_ascii=False, sort_keys=True))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-root", required=True, type=Path)
    p.add_argument("--source-dir", required=True, type=Path)
    p.add_argument("--raw-dir", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--materialize-from-git", action="store_true")
    p.add_argument("--download", action="store_true")
    args = p.parse_args(argv)
    if args.output.exists():
        p.error("Output exists; use a new filename to preserve previous evidence")
    if "value-validation" in args.output.name:
        p.error("Refusing to write near closed validation results")
    try:
        report = run(args.input_root, args.source_dir, args.raw_dir, args.download, args.materialize_from_git)
        code = 0 if report["zipsRetrieved"] else 4
    except Exception as exc:
        report = {"study": D.STUDY, "status": "INFRASTRUCTURE_ERROR", "reason": type(exc).__name__}
        code = 4
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    if "diagnoses" in report:
        echo(report)
    else:
        print(json.dumps(report))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
