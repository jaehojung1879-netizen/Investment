"""Build the kr-alpha-atlas Phase B outputs: the PIT feature matrix (in memory), the readiness report, the Phase C eligibility manifest, the source/universe feasibility
register, a weekly dry-run example and the Korean summary.

Outcome-blind: nothing here reads a label, a forward price or a return after a signal date, fits a model or values a portfolio. The matrix itself is NOT committed (it is
large and fully reproducible from the pinned inputs); its canonical digest is.

  python scripts/build_kr_alpha_atlas_phase_b.py --scratch <empty dir>            # build from the git-pinned inputs and write docs/
  python scripts/build_kr_alpha_atlas_phase_b.py --scratch <raw-input artifact>   # the authorised route: official KRX trading values are used when `market/` is present
  python scripts/build_kr_alpha_atlas_phase_b.py --check                          # re-render the Korean summary from the committed JSON and compare

Outputs never overwrite a sealed study file (the writer refuses any path under a sealed result name) and carry no wall-clock time, so a re-run on the same inputs is byte-identical.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import kr_alpha_atlas_dry_run as DR  # noqa: E402
from pipeline import kr_alpha_atlas_feasibility as FE  # noqa: E402
from pipeline import kr_alpha_atlas_inputs as AI  # noqa: E402
from pipeline import kr_alpha_atlas_matrix as M  # noqa: E402
from pipeline import kr_alpha_atlas_registry as AR  # noqa: E402
from pipeline import kr_alpha_atlas_report as RP  # noqa: E402
from pipeline import regional_alpha_features as RAF  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/results"
OUT = {"readiness": "kr-alpha-atlas-phase-b-readiness.json", "manifest": "kr-alpha-atlas-phase-b-phase-c-manifest.json",
       "sources": "kr-alpha-atlas-phase-b-source-feasibility.json", "dryRun": "kr-alpha-atlas-phase-b-weekly-dry-run-example.json"}
SUMMARY_KO = "docs/kr-alpha-atlas-phase-b-readiness-ko.md"
PINNED_COMMIT = "4ea107ed0cde289f0a049a65ff13d2441a786710"
CUTOFF = "2026-09-14"
FEATURE_START = "2013-01-01"
DRY_RUN_REPLAY_INSTANT = "2026-09-14T10:00:00Z"
DRY_RUN_HISTORY_WEEKS = 160     # B06 reads up to 156 earlier weekly rows of the same name


def dump(obj):
    return json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False, default=str) + "\n"


def facts():
    inventory = json.loads((RESULTS / "kr-termination-inventory.json").read_text())
    scan = json.loads((RESULTS / "kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit-model-free-scan.json").read_text())
    audit_path = "kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.json"
    audit = (RESULTS / audit_path).read_text()
    status = "BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED"
    if status not in audit:
        raise SystemExit("BENCHMARK_RECONCILIATION_STATUS_NOT_FOUND_IN_THE_COMMITTED_AUDIT")
    termination = {"inventoriedSecurities": inventory["summary"]["securities"], "terminationTypeBreakdown": inventory["summary"]["terminationTypeBreakdown"],
                   "completenessByField": inventory["summary"]["byField"], "foundationStatus": inventory["foundationStatus"],
                   "terminalEndsInTheReplayWindow": len(scan["terminalEnds"]), "namesInTop120AtAnOuterSignal": scan["namesInTop120AtAnOuterSignal"],
                   "reading": "every terminal consideration is unresolved; a held name that terminates cannot be valued, so the Phase C registration must declare how a label for such a name is "
                              "withheld (alpha-opportunity-model-v4's security-level eligibility policy is the precedent). Phase B corrects none of this.",
                   "sources": ["docs/results/kr-termination-inventory.json", "docs/results/kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit-model-free-scan.json"]}
    benchmark = {"symbol": "069500.KS", "reconciliationStatus": status, "source": "docs/results/" + audit_path,
                 "reading": "reproducible from the frozen series, with an unexplained accrual against the committed price index; no corrected benchmark is constructed and none is changed here"}
    return termination, benchmark


def build(args):
    registry = AR.load()
    AR.validate(registry)
    inputs = AI.load_inputs(args.commit, args.scratch)
    dates = RAF.weekly_grid(FEATURE_START, CUTOFF, "KR")
    counters = {}
    if args.matrix_cache and Path(args.matrix_cache).exists():
        matrix = pickle.loads(Path(args.matrix_cache).read_bytes())
    else:
        matrix = M.build_matrix(inputs, dates, counters)
        if args.matrix_cache:
            Path(args.matrix_cache).write_bytes(pickle.dumps(matrix))
    termination, benchmark = facts()
    universe = FE.universe_feasibility(inputs, ROOT, args.commit, CUTOFF, json.loads((RESULTS / "kr-termination-inventory.json").read_text()))
    universe["_tradingValueBasis"] = inputs.trading_value_basis
    ref = args.ledger_commit or "origin/signal-history"
    ref_sha = subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
    sources = FE.source_register(registry, json.loads(AI.git_blob(ROOT, ref_sha, "ledger/dart-ownership-events/manifest.json")),
                                 json.loads(AI.git_blob(ROOT, ref_sha, "ledger/kr-investor-flow/manifest.json")),
                                 json.loads((ROOT / "data/bok-policy-rates.json").read_text()), CUTOFF)
    sources["evidenceRef"] = {"ref": ref, "commit": ref_sha, "files": ["ledger/dart-ownership-events/manifest.json", "ledger/kr-investor-flow/manifest.json"],
                              "note": "small collector manifests read at this commit; they are evidence about source access, not inputs to the matrix"}
    audit = {"accounting": FE.accounting_input_audit(inputs.accounting), "priceBasisReconciliation": FE.price_basis_reconciliation(inputs),
             "tradingValueBasis": inputs.trading_value_basis, "marketValueStore": inputs.identity.get("marketValueStore")}
    report, manifest = RP.assemble(matrix, registry, cutoff=CUTOFF, universe=universe, sources=sources, termination=termination, benchmark=benchmark, input_audit=audit)
    if not report["pitChecks"]["pass"] or not report["reasonChecks"]["pass"]:
        raise SystemExit("MATRIX_AUDIT_FAILED: " + json.dumps({"pit": report["pitChecks"], "reasons": report["reasonChecks"]}, default=str))
    report["counters"] = {"featureRowsBuilt": counters.get("featureRowsBuilt"), "labelsBuilt": 0, "modelsFitted": 0, "forwardPriceReads": 0}
    dry = DR.run(inputs, now_utc=DRY_RUN_REPLAY_INSTANT, eligible_features=[e["featureId"] for e in manifest["eligibleFeatures"]] or None, replay_of_instant=True, history_weeks=DRY_RUN_HISTORY_WEEKS)
    universe.pop("_tradingValueBasis", None)
    return report, manifest, {"sources": sources, "universe": universe}, dry


def write(report, manifest, feasibility, dry):
    for key, doc in (("readiness", report), ("manifest", manifest), ("sources", feasibility), ("dryRun", dry)):
        target = RESULTS / OUT[key]
        if target.name.startswith("kr-alpha-discovery-tournament"):
            raise SystemExit("REFUSING_TO_WRITE_A_SEALED_STUDY_FILE")
        target.write_text(dump(doc), encoding="utf-8")
    (ROOT / SUMMARY_KO).write_text(RP.render_summary_ko(report, manifest, feasibility["universe"], feasibility["sources"]), encoding="utf-8")


def check():
    docs = {k: json.loads((RESULTS / v).read_text()) for k, v in OUT.items()}
    expected = RP.render_summary_ko(docs["readiness"], docs["manifest"], docs["sources"]["universe"], docs["sources"]["sources"])
    if (ROOT / SUMMARY_KO).read_text(encoding="utf-8") != expected:
        raise SystemExit("SUMMARY_OUT_OF_DATE: run scripts/build_kr_alpha_atlas_phase_b.py")
    for key in OUT:
        if (RESULTS / OUT[key]).read_text(encoding="utf-8") != dump(docs[key]):
            raise SystemExit("RESULT_FILE_NOT_CANONICAL: " + OUT[key])
    print(json.dumps({"ok": True, "recommendation": docs["readiness"]["recommendation"]["verdict"]}))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", default=PINNED_COMMIT, help="the pinned signal-history commit the sealed studies read")
    parser.add_argument("--ledger-commit", default=None, help="signal-history ref for the two small collector manifests (default origin/signal-history)")
    parser.add_argument("--scratch", help="empty directory (git route) or the extracted raw-input artifact (authorised route)")
    parser.add_argument("--matrix-cache", help="development only: pickle the matrix here and reuse it (never inside the repository)")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    if not args.scratch:
        raise SystemExit("--scratch is required")
    if args.matrix_cache and Path(args.matrix_cache).resolve().is_relative_to(ROOT):
        raise SystemExit("MATRIX_CACHE_MUST_BE_OUTSIDE_THE_REPOSITORY")
    write(*build(args))
    print(json.dumps({"written": list(OUT.values()) + [SUMMARY_KO]}))


if __name__ == "__main__":
    main()
