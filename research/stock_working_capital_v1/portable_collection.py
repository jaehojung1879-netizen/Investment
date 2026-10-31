"""Transport the fixed68 public-source plan to an independently permitted machine.

No workflow, secret, Git history, outcome or source-admission change. Export is
offline; collection retains the selected machine's proxy, TLS and access policy.
The recipient needs this same checkout and dependencies, not historical objects.
Returned originals remain local evidence, never implicitly approved financials.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
from pathlib import Path

from . import pit_filing_evidence as E
from . import pit_join as J
from . import xbrl_recovery as R

HERE = Path(__file__).parent
ANCHOR = HERE / "xbrl_recovery_v1/manifest.json"
CODE = ("portable_collection.py", "xbrl_recovery.py", "pit_filing_evidence.py",
        "pit_join.py", "pit_admission.py", "features.py", "age_policy.py",
        "fiscal-age-decision-v1.json")


def code_hashes():
    return {name: E.sha((HERE / name).read_bytes()) for name in CODE}


def reference_targets():
    anchor = json.loads(ANCHOR.read_text())
    targets = [{k: v for k, v in r.items() if k != "status"} for r in anchor["rows"]]
    if len(targets) != 68 or len({t["receipt"] for t in targets}) != 68:
        raise ValueError("FIXED_68_REFERENCE_CHANGED")
    return targets


def build_plan(targets):
    return {"schema": "STOCK_WC_FIXED68_PORTABLE_SOURCE_PLAN_V1",
            "anchorSha256": E.sha(ANCHOR.read_bytes()), "codeSha256": code_hashes(),
            "demandSha256": E.sha(R.DEMAND.read_bytes()),
            "sourceAdmissionAuthorized": False, "historicalOutcomesRead": 0,
            "targets": [{**{k: v for k, v in t.items() if k != "mainRaw"},
                         "mainBase64": base64.b64encode(t["mainRaw"]).decode("ascii")}
                        for t in targets]}


def validate_plan(plan):
    if (plan.get("schema") != "STOCK_WC_FIXED68_PORTABLE_SOURCE_PLAN_V1"
            or plan.get("anchorSha256") != E.sha(ANCHOR.read_bytes())
            or plan.get("demandSha256") != E.sha(R.DEMAND.read_bytes())
            or plan.get("sourceAdmissionAuthorized") is not False
            or plan.get("historicalOutcomesRead") != 0):
        raise ValueError("PORTABLE_PLAN_IDENTITY_OR_PERMISSION_MISMATCH")
    if plan.get("codeSha256") != code_hashes():
        raise ValueError("PORTABLE_PLAN_CODE_HASH_MISMATCH")
    expected = reference_targets()
    targets = plan.get("targets", [])
    if (len(targets) != len(expected)
            or [{k: v for k, v in t.items() if k != "mainBase64"} for t in targets] != expected):
        raise ValueError("PORTABLE_PLAN_FIXED_RECEIPT_METADATA_MISMATCH")
    decoded = []
    for t in targets:
        raw = base64.b64decode(t["mainBase64"], validate=True)
        if E.sha(raw) != t["mainSha256"] or R.popup_url(raw, t["receipt"]) != t["downloadPageUrl"]:
            raise ValueError("PORTABLE_PLAN_ORIGINAL_MAIN_MISMATCH")
        decoded.append({**{k: v for k, v in t.items() if k != "mainBase64"}, "mainRaw": raw})
    return decoded


def export_plan(output):
    plan = build_plan(R.registry(J.PinnedInputs(J.ROOT)))
    validate_plan(plan)
    raw = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    if Path(output).suffix == ".gz":
        raw = gzip.compress(raw, mtime=0)
    with Path(output).open("xb") as f:
        f.write(raw)
    return {"status": "OFFLINE_PLAN_EXPORTED_NOT_SOURCE_ACQUIRED", "fixedReceipts": 68,
            "planSha256": E.sha(Path(output).read_bytes()), "publicRequestsAttempted": 0}


def read_plan(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def collect_plan(plan_path, output):
    # No Git reads or alternative network routes; unchanged collector validates
    # download-page/attachment provenance and uses normal inherited access.
    targets = validate_plan(read_plan(plan_path))
    return R.collect(targets, output, access=R.environment_access())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export-plan", action="store_true")
    mode.add_argument("--verify-plan", type=Path)
    mode.add_argument("--collect-plan", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    if args.verify_plan:
        if args.output:
            p.error("--verify-plan never writes an output")
        targets = validate_plan(read_plan(args.verify_plan))
        print(json.dumps({"status": "PLAN_VERIFIED_NOT_SOURCE_ACQUIRED", "fixedReceipts": len(targets),
                          "publicRequestsAttempted": 0}))
        return 0
    if args.output is None or args.output.exists():
        p.error("--output must be new; preserve previous plans and acquisitions")
    report = export_plan(args.output) if args.export_plan else collect_plan(args.collect_plan, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}))
    return 0 if args.export_plan or len(R.load_packages(args.output)) == 68 else 3


if __name__ == "__main__":
    raise SystemExit(main())
