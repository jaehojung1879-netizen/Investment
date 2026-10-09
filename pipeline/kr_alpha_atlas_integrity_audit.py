"""Isolated outcome-free audit of the unchanged, registered preparation path.

Never imported by the scientific executor. No authorization, lock or result writer.
The user-authorized audit may load prices for PIT features, never for targets.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
import resource
import shutil
import subprocess
import time
from unittest.mock import patch

from pipeline import kr_model_raw_snapshot as RAW
from pipeline.kr_alpha_atlas_phase_c import (
    contract, economics, executor, interactions, labels, lifecycle, models, preflight, statistics,
)


@dataclass
class AuditCounters:
    realHistoricalAlphaOutcomeReads: int = 0
    realForwardLabels: int = 0
    realHistoricalModelFits: int = 0
    realStockReturnOutcomeAnalyses: int = 0
    realPortfolioBacktests: int = 0
    formalExecutionDispatches: int = 0
    permanentExecutionLocksCreated: int = 0


@contextmanager
def outcome_free_firewall():
    """Fail before every registered outcome/fit/portfolio/lock entry point."""
    attempts = []

    def deny(*args, **kwargs):
        attempts.append("FORBIDDEN_OUTCOME_OR_EXECUTION_CALL")
        raise RuntimeError(attempts[-1])

    with ExitStack() as stack:
        stack.enter_context(RAW.outcome_firewall())
        for module, name in [
            (labels, "build_labels"), (labels, "formal_permit"),
            (labels, "synthetic_permit"),
            (executor, "execute"), (models, "predictions"),
            (models, "baseline_reading"), (models, "incremental"),
            (models, "residual_and_slopes"),
            (lifecycle, "formal"), (lifecycle.GitHub, "claim"),
            (economics, "evaluate"), (statistics, "factor_reading"),
        ]:
            stack.enter_context(patch.object(module, name, deny))
        # Guard any alternate direct model entry as well as the public executor.
        for name in ("fit", "ridge_fit", "fit_model", "analyze"):
            for module in (models, interactions):
                if hasattr(module, name):
                    stack.enter_context(patch.object(module, name, deny))
        yield attempts
        if attempts:
            raise RuntimeError("AUDIT_FIREWALL_WAS_TRIGGERED")


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root).decode().strip()


def resource_facts(work):
    disk = shutil.disk_usage(work)
    memory_limit = None
    current = None
    for path, key in [("/sys/fs/cgroup/memory.max", "limit"), ("/sys/fs/cgroup/memory.current", "current")]:
        p = Path(path)
        if p.exists() and p.read_text().strip().isdigit():
            if key == "limit":
                memory_limit = int(p.read_text())
            else:
                current = int(p.read_text())
    meminfo = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    physical = int(meminfo["MemTotal"].split()[0]) * 1024
    available = int(meminfo["MemAvailable"].split()[0]) * 1024
    if memory_limit is not None:
        available = min(available, max(0, memory_limit - (current or 0)))
    return {
        "diskFreeBytes": disk.free,
        "memoryCapacityBytes": min(physical, memory_limit) if memory_limit is not None else physical,
        "memoryAvailableBytes": available,
        "cgroupMemoryLimitBytes": memory_limit,
        "peakRssBytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }


def persistence_probe(work):
    """Use the formal immutable byte writer, only on an audit-specific probe."""
    p = Path(work) / "audit-persistence-probe.json"
    raw = contract.canonical({"scope": "AUDIT_PROBE_NO_SCIENTIFIC_RESULT"}) + b"\n"
    RAW.immutable_bytes(p, raw)
    RAW.immutable_bytes(p, raw)  # exact-byte recovery allowed
    try:
        RAW.immutable_bytes(p, raw + b" ")
    except ValueError:
        return {"status": "PASS", "exactByteRepeat": True, "differentBytesRefused": True}
    raise RuntimeError("IMMUTABLE_WRITER_ACCEPTED_MUTATION")


def audited_preflight(root, work, expected_main, *, github=None):
    """Execute the actual frozen prepare(), not a second matrix implementation.

    Audit branches are permitted only with an unchanged scientific closure and the
    verified main as ancestor. Formal authorization and lock phases are excluded.
    """
    root, work = Path(root), Path(work)
    if work.exists():
        raise ValueError("FRESH_AUDIT_DIRECTORY_REQUIRED")
    work.mkdir(parents=True)
    start = time.monotonic()
    spec = contract.load(root)
    github = github or lifecycle.GitHub()
    main = github.main()
    if main != expected_main:
        raise ValueError("ACTUAL_MAIN_CHANGED")
    subprocess.run(["git", "merge-base", "--is-ancestor", main, "HEAD"], cwd=root, check=True)
    if (root / spec["lifecycle"]["authorizationPath"]).exists():
        raise ValueError("AUDIT_REQUIRES_NO_PHASE_C_AUTHORIZATION")
    if (root / spec["lifecycle"]["resultPath"]).exists() or github.previous_results(spec["lifecycle"]["artifactPrefix"]):
        raise ValueError("FORMAL_RESULT_ALREADY_EXISTS")
    if github.locks(spec["lifecycle"]["lockPrefix"]):
        raise ValueError("STUDY_ALREADY_CONSUMED")
    runtime = preflight.verify_runtime(spec)  # fail cheaply, before preparation
    initial_resources = resource_facts(work)
    if initial_resources["memoryCapacityBytes"] < spec["compute"]["memoryBytes"]:
        raise ValueError("AUDIT_HOST_BELOW_REGISTERED_MEMORY_CAPACITY")
    if initial_resources["diskFreeBytes"] < 1024**3:
        raise ValueError("AUDIT_DISK_BELOW_ONE_GIB_PREREQUISITE")
    schemas = preflight.verify_source_schema_samples(root, spec)
    calendar = contract.calendar_facts(spec)
    counters = AuditCounters()
    with outcome_free_firewall() as attempts:
        data, identity = preflight.prepare(root, spec, None, work / "inputs")
        readiness = data.validate_features(spec)
        registered_b4 = contract.read(root, "docs/results/kr-alpha-atlas-phase-b-readiness.json")["baselines"]["B4_COMBINED_SIMPLE"]
        b4_range = registered_b4["commonUsableRange"]
        b4_rows = data.rows.date.between(*b4_range)
        b4_complete = data.values[spec["baselines"]["B4_COMBINED_SIMPLE"]].notna().all(axis=1)
        b4_comparable = {
            "commonUsableRange": b4_range, "observations": int(b4_rows.sum()),
            "measuredCompleteCasePct": float(b4_complete[b4_rows].mean() * 100),
            "registeredCompleteCasePct": registered_b4["completeCaseCoverageWithinCommonRangePct"],
            "wholePanelCompleteCasePct": readiness["b4CompleteCaseShare"] * 100,
            "policy": "different denominators; registered training-only imputation and matched masks unchanged",
        }
        # Only structural counts. Never read a forward price window or a label.
        securities = data.rows.ticker.nunique()
        price_cells = sum(len(x) for x in data.closes.values())
        benchmark_sessions = len(data.benchmark_close)
        probe = persistence_probe(work)
    elapsed = time.monotonic() - start
    resources = resource_facts(work)
    if elapsed > spec["compute"]["wallSeconds"] or resources["peakRssBytes"] > spec["compute"]["memoryBytes"]:
        raise ValueError("PRE_OUTCOME_AUDIT_RESOURCE_LIMIT")
    contract.load(root)
    if github.main() != main or github.locks(spec["lifecycle"]["lockPrefix"]):
        raise ValueError("MAIN_OR_LOCK_CHANGED_DURING_AUDIT")
    report = {
        "schema": "KR_ALPHA_ATLAS_PRE_EXECUTION_AUDIT_V1",
        "scope": "FULL_FROZEN_PREPARE_WITHOUT_TARGETS_AUTHORIZATION_LOCK_OR_EXECUTION",
        "status": "PASS",
        "actualMainSha": main,
        "auditCheckoutSha": git(root, "rev-parse", "HEAD"),
        "specFileSha256": contract.file_hash(root / contract.SPEC),
        "dependencyManifestSha256": contract.digest(spec["dependencyHashes"]),
        "dependencyFilesVerified": len(spec["dependencyHashes"]),
        "protectedFilesVerified": len(spec["protectedHashes"]),
        "auditCodeSha256": {p: contract.file_hash(root / p) for p in [
            "pipeline/kr_alpha_atlas_integrity_audit.py", "scripts/audit_kr_alpha_atlas_preflight.py"]},
        "runtime": runtime,
        "inputIdentity": identity,
        "expectedMatrixDigest": spec["phaseBIdentity"]["matrixDigest"],
        "actualMatrixDigest": identity["matrixDigest"],
        "matrixDigestMatches": identity["matrixDigest"] == spec["phaseBIdentity"]["matrixDigest"],
        "calendar": calendar,
        "sourceSchemas": schemas,
        "readiness": readiness,
        "b4ComparableCoverage": b4_comparable,
        "securities": int(securities),
        "eligibleCandidates": len(spec["eligibleFeatures"]),
        "priceCellsLoadedForPreparationOnly": price_cells,
        "benchmarkSessionArrayLength": benchmark_sessions,
        "tradingValueBasis": spec["tradingValueBasis"],
        "elapsedSeconds": round(elapsed, 3),
        "resourcesBefore": initial_resources,
        "resourcesAfter": resources,
        "persistenceProbe": probe,
        "firewallBlockedCalls": attempts,
        "counters": asdict(counters),
        "excludedLayers": ["human execution authorization", "permanent lock", "labels", "model fits", "statistics", "portfolios", "formal results"],
        "syntheticValidation": "RUN_SEPARATELY_IN_ORDINARY_CI_NOT_REAL_INPUT_FIT",
        "benchmarkIntegrity": spec["benchmarkIntegrity"],
    }
    RAW.immutable_bytes(work / "pre-execution-audit.json", contract.canonical(report) + b"\n")
    return report
