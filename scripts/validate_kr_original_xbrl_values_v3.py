"""Audit the immutable v1 60-fact sample under the v3 rules.

Exit 0 PASS, 2 FAIL, 3 BLOCKED, 4 process error. Never repairs candidate data.
Transport and candidate joining are the v1 script's own helpers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_xbrl_validation_sample as S  # noqa: E402
from pipeline import kr_xbrl_value_validation as V  # noqa: E402
from pipeline import kr_xbrl_value_validation_v3 as V3  # noqa: E402
from scripts import validate_kr_original_xbrl_values as V1CLI  # noqa: E402


def run(input_root, source_dir, download=False, materialize_from_git=False):
    protocol_v1, protocol, sample = V3.load_frozen(ROOT)
    if materialize_from_git:
        V1CLI.materialize(input_root, protocol_v1)
    V.verify_frame(input_root, protocol_v1, sample)
    values = V1CLI.candidate_values(input_root, protocol_v1, sample)
    access = V1CLI.download_sources(source_dir, sample) if download else {"status": "LOCAL_SOURCE_ONLY"}
    results = []
    for item in sample["items"]:
        value = values[item["identity"]]
        try:
            path = V1CLI.source_path(source_dir, item, ".zip")
            index = V1CLI.source_path(source_dir, item, ".filing.json")
            raw = path.read_bytes() if path.exists() else None
            rows = json.loads(index.read_text()) if index.exists() else None
            row = V3.validate_item(item, value, raw, rows)
            if index.exists():
                row["filingIndexSha256"] = V.sha256(index.read_bytes())
            results.append(row)
        except Exception as exc:
            results.append(V.outcome(item, value, "INFRASTRUCTURE_ERROR",
                                     "independent reader process error: " + type(exc).__name__))
    summary = V.summarize(results)
    return {"study": V3.STUDY, "predecessorStudy": "kr-original-xbrl-value-validation-v2", "startingMain": "2e9e2baf7db245cc3ed30da33d7db6ba64452584",
            "candidateSha256": protocol_v1["candidate"]["sha256"], "sourceCommit": S.SOURCE_COMMIT,
            "protocolFreezeCommit": V3.PROTOCOL_FREEZE_COMMIT, "protocolSha256": V3.PROTOCOL_SHA256,
            "sampleSha256": V.SAMPLE_SHA256, "sampleSize": len(sample["items"]),
            "frameSize": protocol_v1["frame"]["size"], "admittedCorpCodeSchemes": sorted(V3.V2.V2_CORP_CODE_SCHEMES), "presentationGate": False,
            "sourceAccess": access, **summary, "results": results,
            "sourceConfidence": "CANDIDATE_UNCONFIRMED",
            "promotionRecommended": summary["verdict"] == "PASS",
            "alphaOutcomesUsed": False, "historicalAlphaExecuted": False, "candidateRepaired": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-root", required=True, type=Path)
    p.add_argument("--source-dir", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--materialize-from-git", action="store_true")
    p.add_argument("--download", action="store_true")
    args = p.parse_args(argv)
    if args.output.exists():
        p.error("Output exists; use a new audit filename to preserve previous evidence")
    if args.output.resolve().name.startswith(("kr-original-xbrl-value-validation-v1-report","kr-original-xbrl-value-validation-v2-report")):
        p.error("Refusing to write over a closed result path")
    try:
        report = run(args.input_root, args.source_dir, args.download, args.materialize_from_git)
    except Exception as exc:
        report = {"study": V3.STUDY, "verdict": "INFRASTRUCTURE_ERROR",
                  "reason": type(exc).__name__, "detail": "Preflight could not produce a complete audit"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({k: report[k] for k in ("verdict", "counts", "sourceAccess") if k in report}))
    return {"PASS": 0, "FAIL": 2, "BLOCKED": 3, "INFRASTRUCTURE_ERROR": 4}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
