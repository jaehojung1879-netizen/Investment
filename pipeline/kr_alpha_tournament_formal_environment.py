"""kr-alpha-discovery-tournament-v1 post-outcome audit: the FORMAL EXECUTION ENVIRONMENT and a cheap parity gate.

POST_OUTCOME_FORENSIC_REPRODUCIBILITY_ENGINEERING. Not model rescue, not tuning, not Alpha Tournament v2. The first post-outcome reconstruction (run 37688582489)
read RECONSTRUCTION_MISMATCH at 1e-9, and ran in a different environment from the formal execution (run 37535814142). This module records the formal Python
environment from the formal job's own log and refuses to START the expensive reconstruction in a knowingly different one.

What it does and does not do:
  * It never changes a scientific rule. The 1e-9 reproduction gate lives in `kr_alpha_tournament_postoutcome_integrity_audit` and is untouched.
  * It reads the committed manifest (`docs/results/...-formal-environment-37535814142.json`) and the audit-only constraint file; neither is part of the sealed
    tournament's dependency closure, and the sealed workflow is not edited.
  * The PYTHON environment is pinned and checked: the exact CPython patch release, every package version pip installed in the formal execute job, the thread
    variables, and the constraint file itself. A mismatch is `PYTHON_ENVIRONMENT_MISMATCH` and the preflight exits non-zero BEFORE the raw snapshot is downloaded.
  * The HOST (runner image, CPU, the BLAS kernel set chosen at run time) cannot be pinned on GitHub-hosted runners and the formal log did not record the CPU, so it is
    RECORDED and CLASSIFIED but never blocks. `HOST_HARDWARE_IMAGE_MATCH` needs a recorded formal CPU and BLAS architecture to compare with; the formal log has
    neither, so it is unreachable today and the honest classifications are DIFFERS or UNVERIFIABLE.

Stdlib only at import time (numpy and threadpoolctl are read lazily and inside try blocks), no subprocess, no network.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
STUDY = "kr-alpha-discovery-tournament-v1"
FORMAL_RUN_ID = 37535814142
MANIFEST_PATH = "docs/results/" + STUDY + "-formal-environment-37535814142.json"
CONSTRAINTS_PATH = "constraints/" + STUDY + "-formal-env-37535814142.txt"
THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
PYTHON_EXACT = "PYTHON_ENVIRONMENT_EXACT_MATCH"
PYTHON_MISMATCH = "PYTHON_ENVIRONMENT_MISMATCH"
HOST_MATCH = "HOST_HARDWARE_IMAGE_MATCH"
HOST_DIFFERS = "HOST_HARDWARE_IMAGE_DIFFERS"
HOST_UNVERIFIABLE = "HOST_HARDWARE_IMAGE_UNVERIFIABLE"
PARITY_FAILURE = "FORMAL_ENVIRONMENT_PARITY_FAILED"


def canonical_name(name):
    """PEP 503 normalisation, so `charset_normalizer` and `charset-normalizer` are one name."""
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def _digest(manifest):
    body = {k: v for k, v in manifest.items() if k != "digest"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def constraints_text(manifest):
    """The constraint file a manifest implies. The committed file must equal this byte for byte (checked by the preflight and by a test)."""
    header = [
        "# AUDIT-ONLY constraints: the package versions pip installed in the execute job of formal run %d (commit %s)." % (
            manifest["formalRun"]["runId"], manifest["formalRun"]["executionSha"][:8]),
        "# Derived from the job log's 'Successfully installed' line; see %s." % MANIFEST_PATH,
        "# Used only by the post-outcome integrity-audit workflow, with:  pip install -r requirements.txt -r requirements-dev.txt -c <this file>",
        "# It is not read by the sealed tournament, its spec or its workflow, and it changes no scientific rule. Do not edit by hand: the preflight compares it with the manifest.",
    ]
    return "\n".join(header) + "\n" + "".join("%s==%s\n" % (k, v) for k, v in sorted(manifest["packages"].items()))


def load_manifest(root=ROOT):
    """Parse and validate the committed manifest. Raises ValueError (never returns a partially valid one)."""
    path = Path(root) / MANIFEST_PATH
    manifest = json.loads(path.read_text())
    if manifest.get("digest") != _digest(manifest):
        raise ValueError("FORMAL_ENVIRONMENT_MANIFEST_DIGEST_MISMATCH")
    if manifest["formalRun"]["runId"] != FORMAL_RUN_ID or manifest.get("manifestId") != STUDY + "-formal-environment-37535814142":
        raise ValueError("FORMAL_ENVIRONMENT_MANIFEST_IDENTITY_MISMATCH")
    if not re.fullmatch(r"\d+\.\d+\.\d+", manifest["python"]["version"]):
        raise ValueError("FORMAL_ENVIRONMENT_PYTHON_VERSION_NOT_A_PATCH_RELEASE")
    packages = manifest["packages"]
    if not packages or any(canonical_name(k) != k for k in packages) or any(not re.fullmatch(r"[0-9][0-9A-Za-z.!+_-]*", str(v)) for v in packages.values()):
        raise ValueError("FORMAL_ENVIRONMENT_PACKAGES_NOT_EXACT_PINS")
    if manifest["threadEnvironment"] != {k: "1" for k in THREAD_VARIABLES}:
        raise ValueError("FORMAL_ENVIRONMENT_THREAD_ENVIRONMENT_CHANGED")
    return manifest


# --------------------------------------------------------------------------- #
# Observation (what THIS interpreter and host look like)
# --------------------------------------------------------------------------- #
def _installed_packages():
    from importlib import metadata
    found = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            found[canonical_name(name)] = dist.version
    return found


def _cpu():
    model, flags = None, []
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if model is None and line.lower().startswith("model name"):
                model = line.split(":", 1)[1].strip()
            if not flags and line.lower().startswith("flags"):
                flags = sorted(line.split(":", 1)[1].split())
            if model is not None and flags:
                break
    except OSError:
        pass
    return {"cpuModel": model, "cpuFlags": flags or None}


def _blas():
    out = {"numpyShowConfig": None, "threadpool": None}
    try:
        import numpy
        config = numpy.show_config(mode="dicts")
        out["numpyShowConfig"] = json.loads(json.dumps(config, default=str))
    except Exception as exc:                                             # a config dump is a record, never a gate
        out["numpyShowConfig"] = "UNAVAILABLE: %s" % type(exc).__name__
    try:
        from threadpoolctl import threadpool_info
        out["threadpool"] = [{k: v for k, v in item.items() if k in ("internal_api", "num_threads", "threading_layer", "version", "architecture", "filepath")}
                             for item in threadpool_info()]
    except Exception as exc:
        out["threadpool"] = "UNAVAILABLE: %s" % type(exc).__name__
    return out


def observe_environment(environ=None, with_host_detail=True):
    """The environment of the running interpreter. `environ` is injectable so tests never depend on the machine they run on."""
    environ = os.environ if environ is None else environ
    uname = platform.uname()
    observed = {
        "python": {"version": platform.python_version(), "implementation": platform.python_implementation(), "executable": sys.executable},
        "packages": _installed_packages(),
        "threadEnvironment": {k: environ.get(k) for k in THREAD_VARIABLES},
        "host": {"imageOS": environ.get("ImageOS"), "imageVersion": environ.get("ImageVersion"), "runnerOS": environ.get("RUNNER_OS"),
                 "runnerArch": environ.get("RUNNER_ARCH"), "runnerEnvironment": environ.get("RUNNER_ENVIRONMENT"),
                 "uname": {"system": uname.system, "release": uname.release, "version": uname.version, "machine": uname.machine},
                 "locale": environ.get("LANG"), "tz": environ.get("TZ"), "pythonHashSeed": environ.get("PYTHONHASHSEED")},
    }
    if with_host_detail:
        observed["host"].update(_cpu())
        observed["blas"] = _blas()
    else:
        observed["host"].update({"cpuModel": None, "cpuFlags": None})
        observed["blas"] = {"numpyShowConfig": None, "threadpool": None}
    return observed


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
def compare_python_environment(manifest, observed, constraints_on_disk=None):
    """PYTHON_ENVIRONMENT_EXACT_MATCH only when every check passes. Each failure names exactly what differs."""
    failures = []
    py = manifest["python"]
    if observed["python"]["implementation"] != py["implementation"]:
        failures.append("implementation: formal %s, observed %s" % (py["implementation"], observed["python"]["implementation"]))
    if observed["python"]["version"] != py["version"]:
        failures.append("python: formal %s, observed %s" % (py["version"], observed["python"]["version"]))
    have = observed["packages"]
    for name, wanted in sorted(manifest["packages"].items()):
        got = have.get(name)
        if got is None:
            failures.append("package %s: formal %s, observed NOT INSTALLED" % (name, wanted))
        elif got != wanted:
            failures.append("package %s: formal %s, observed %s" % (name, wanted, got))
    for key in THREAD_VARIABLES:
        if observed["threadEnvironment"].get(key) != manifest["threadEnvironment"][key]:
            failures.append("%s: formal %s, observed %s" % (key, manifest["threadEnvironment"][key], observed["threadEnvironment"].get(key)))
    if constraints_on_disk is not None and constraints_on_disk != constraints_text(manifest):
        failures.append("constraint file differs from the manifest it was derived from")
    return {"classification": PYTHON_EXACT if not failures else PYTHON_MISMATCH, "failures": failures,
            "checked": {"pythonPatchRelease": py["version"], "packages": len(manifest["packages"]), "threadVariables": list(THREAD_VARIABLES)},
            "unrecordedInstalledPackages": sorted(set(have) - set(manifest["packages"]))}


def classify_host(manifest, observed):
    """Recorded, never gating. MATCH needs a formal CPU model AND BLAS architecture on record, which the formal log does not have."""
    formal, seen = manifest["host"], observed["host"]
    reasons = []
    image_equal = formal.get("imageVersion") is not None and formal.get("imageVersion") == seen.get("imageVersion")
    if not image_equal:
        reasons.append("runner image version: formal %s, observed %s" % (formal.get("imageVersion"), seen.get("imageVersion")))
    cpu_known = formal.get("cpuModel") is not None
    if not cpu_known:
        reasons.append("formal CPU model was not recorded in the formal log")
    elif formal["cpuModel"] != seen.get("cpuModel"):
        reasons.append("CPU model: formal %s, observed %s" % (formal["cpuModel"], seen.get("cpuModel")))
    arch_known = formal.get("openblasArchitecture") is not None
    if not arch_known:
        reasons.append("formal OpenBLAS dispatch architecture was not recorded in the formal log")
    if not image_equal or (cpu_known and formal["cpuModel"] != seen.get("cpuModel")):
        label = HOST_DIFFERS
    elif cpu_known and arch_known:
        label = HOST_MATCH
    else:
        label = HOST_UNVERIFIABLE
    return {"classification": label, "reasons": reasons, "blocksTheAudit": False,
            "formal": {k: formal.get(k) for k in ("imageName", "imageVersion", "provisionerVersion", "runnerVersion", "region", "cpuModel", "openblasArchitecture")},
            "observed": {k: seen.get(k) for k in ("imageOS", "imageVersion", "runnerArch", "cpuModel")}}


def parity_record(manifest, observed, constraints_on_disk=None):
    """Everything the audit artifact keeps about the environment, including pip freeze and the BLAS/CPU detail. `ok` is the Python gate only."""
    python = compare_python_environment(manifest, observed, constraints_on_disk)
    return {"manifestId": manifest["manifestId"], "manifestDigest": manifest["digest"], "formalRunId": manifest["formalRun"]["runId"],
            "ok": python["classification"] == PYTHON_EXACT, "pythonEnvironment": python, "host": classify_host(manifest, observed),
            "observed": {"python": observed["python"], "threadEnvironment": observed["threadEnvironment"], "hostDetail": observed["host"],
                         "pipFreeze": ["%s==%s" % (k, v) for k, v in sorted(observed["packages"].items())], "blas": observed["blas"]}}


def compact_comparison(manifest, observed):
    """The small comparison embedded in a failed reproduction's diagnostics (no pip freeze, no flags)."""
    python = compare_python_environment(manifest, observed)
    return {"manifestId": manifest["manifestId"], "manifestDigest": manifest["digest"], "pythonEnvironment": python["classification"],
            "pythonFailures": python["failures"], "host": classify_host(manifest, observed)["classification"],
            "formalPython": manifest["python"]["version"], "observedPython": observed["python"]["version"],
            "observedImageVersion": observed["host"].get("imageVersion"), "formalImageVersion": manifest["host"].get("imageVersion"),
            "observedOpenblasArchitectures": sorted({str(t.get("architecture")) for t in (observed["blas"].get("threadpool") or []) if isinstance(t, dict)}
                                                    if isinstance(observed["blas"].get("threadpool"), list) else [])}
