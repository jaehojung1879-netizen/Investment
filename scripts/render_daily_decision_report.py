"""Render committed sources only; output must be a new directory outside the repository."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import daily_decision_report as R  # noqa: E402


def safe_output(path, root=ROOT):
    output = path.resolve()
    listing = subprocess.check_output(["git", "worktree", "list", "--porcelain"], cwd=root, text=True)
    roots = [Path(line.removeprefix("worktree ")).resolve() for line in listing.splitlines() if line.startswith("worktree ")]
    common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=root, text=True).strip()
    roots.append((root / common).resolve())
    if output.exists() or any(output.is_relative_to(r) for r in roots):
        raise ValueError("OUTPUT_INSIDE_REPOSITORY_OR_ALREADY_EXISTS")
    parent = output.parent
    while not parent.exists():
        parent = parent.parent
    inside = subprocess.run(["git", "-C", str(parent), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    admin = subprocess.run(["git", "-C", str(parent), "rev-parse", "--is-inside-git-dir"], capture_output=True, text=True)
    if (inside.returncode == 0 and inside.stdout.strip() == "true"
            or admin.returncode == 0 and admin.stdout.strip() == "true"):
        raise ValueError("OUTPUT_INSIDE_REPOSITORY")
    return output


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-ref", required=True, help="full local immutable signal-history commit SHA")
    p.add_argument("--as-of", required=True, help="timezone-aware report timestamp; reproducible, not a research writer clock")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        output = safe_output(args.output)
    except ValueError as exc:
        p.error(str(exc))
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    code_paths = [Path(R.__file__), Path(__file__), Path(R.W.__file__)]
    identity = {"gitSha": sha, "files": {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in code_paths},
                "workingTreeDirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))}
    identity["registeredStudies"] = {}
    for study, module in R.STUDIES.items():
        raw = (ROOT / module.SPEC_PATH).read_bytes()
        spec = R._strict_json(raw)
        if spec.get("studyId") != study:
            raise ValueError("REGISTERED_STUDY_IDENTITY_MISMATCH")
        identity["registeredStudies"][study] = {"path": module.SPEC_PATH, "sha256": hashlib.sha256(raw).hexdigest(),
            "firstEligibleFloor": (spec.get("schedule") or {}).get("firstEligibleSignalSessionFloor"),
            "minimumEligibleNames": (spec.get("construction") or {}).get("minEligibleNames"),
            "primaryReceiptCohort": ((spec.get("assessment") or {}).get("primary") or {}).get("cohortReceipts"),
            "horizons": spec.get("horizonsSessions"), "outcomeEvaluationStatus": (spec.get("outcomeEvaluation") or {}).get("status")}
    snapshot = R.GitSnapshot(ROOT, args.source_ref)
    report = R.build(snapshot, as_of=args.as_of, code_identity=identity)
    markdown = R.render(report)
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")
    (output / "report.md").write_text(markdown)
    print(json.dumps({"report": str(output / "report.md"), "sourceCommitSha": snapshot.commit,
                      "sha256": hashlib.sha256(markdown.encode()).hexdigest(), "productionEffect": "NONE"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
