"""Metadata-only admission and one owner-comment permit for WID exploration.

No price, label, model or sealed-result reader is imported here. A permit is
verified against GitHub and a durable NEW attempt ref is claimed before reads.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from . import industry_foundation as IF
from . import prospective_receipt_core as P
from .winner_inflection_exploration import RunLayout, trial_record
from .winner_inflection_local_git import local_view, object_type

REPOSITORY = "jaehojung1879-netizen/Investment"
OWNER = "jaehojung1879-netizen"
SPEC_PATH = "docs/winner-inflection-discovery/execution-us-b-h126-2020-v1.json"
REVIEW_PATH = "docs/winner-inflection-discovery/source-admission-v1.json"
CLOSURE = ("pipeline/winner_inflection_admission.py", "pipeline/winner_inflection_local_git.py", "pipeline/winner_inflection_execution.py",
           "scripts/run_winner_inflection.py", "pipeline/winner_inflection.py", "pipeline/winner_inflection_exploration.py",
           "pipeline/experiment_workbench.py", "pipeline/us_decision_pilot.py", "pipeline/us_multifactor_inputs.py",
           "pipeline/price_adjustment.py", "pipeline/benchmark_alpha.py", "pipeline/replay_calendar.py",
           "pipeline/us_cash_profitability.py", "pipeline/finnhub_derive.py", "pipeline/finnhub_fundamentals.py",
           "pipeline/regional_alpha_features.py", "scripts/inspect_experiment_sources.py")
CLAIMS = ("rights", "identity", "membershipIndustry", "returnBasis", "terminal", "size", "vintage")
EVIDENCE_ROOT = Path("/workspace/wid-inputs/evidence")
EXECUTION_ROOT = Path("/workspace/wid-executions")
_AUTHENTICATED = object()


@dataclass(frozen=True)
class VerifiedPermit:
    evidence: dict
    _proof: object


def require_permit(permit):
    if not isinstance(permit, VerifiedPermit) or permit._proof is not _AUTHENTICATED:
        raise ValueError("DURABLE_OWNER_PERMIT_REQUIRED_BEFORE_SOURCE_READ")
    return permit.evidence


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def citation_verified(citation):
    """Evidence is metadata in the dedicated input/evidence directory only.

    Original price/label payloads are not opened by admission, even for a hash.
    This checks the reviewed document's bytes, not a legal interpretation.
    """
    path = Path(citation.get("reference", "")).resolve()
    return (path.is_relative_to(EVIDENCE_ROOT.resolve()) and path.is_file()
            and path.suffix in (".json", ".md", ".txt") and file_sha(path) == citation.get("sha256"))


def admission(spec, review):
    """Validate reviewed evidence and scope, not the legal truth of an assertion.

    The owner authorizes this exact review digest; missing permission is never
    inferred from possession of a price or an old research approval.
    """
    reasons = []
    if review.get("specId") != spec["id"]:
        reasons.append("REVIEW_SPEC_MISMATCH")
    if review.get("scope") != "SURVIVOR_CONDITIONED_PUBLIC_RECONSTRUCTION":
        reasons.append("CONDITIONAL_SCOPE_NOT_EXPLICIT")
    for claim in CLAIMS:
        item = review.get("claims", {}).get(claim, {})
        if item.get("status") != "REVIEWED_ACCEPTED" or not item.get("reviewer") or not item.get("citations"):
            reasons.append("SOURCE_REVIEW_UNRESOLVED:" + claim)
        for citation in item.get("citations", []):
            if not citation.get("reference") or not re.fullmatch(r"[0-9a-f]{64}", citation.get("sha256", "")):
                reasons.append("EVIDENCE_PIN_MISSING:" + claim)
            elif not citation_verified(citation):
                reasons.append("REVIEWED_EVIDENCE_BYTES_UNVERIFIED:" + claim)
    if review.get("basis") != spec["returnBasis"]:
        reasons.append("STOCK_SPY_RETURN_BASIS_MISMATCH")
    if review.get("identityPolicy") != "OWN_PANEL_AND_DATED_CIK_NO_REPAIR":
        reasons.append("IDENTITY_POLICY_UNRESOLVED")
    if review.get("cashPolicy") != "UNREMUNERATED_USD_NOMINAL":
        reasons.append("CASH_POLICY_UNRESOLVED")
    if review.get("terminalPolicy") != "RETAIN_UNRESOLVED_NO_LAST_QUOTE_OR_ZERO_SUBSTITUTION":
        reasons.append("TERMINAL_POLICY_UNRESOLVED")
    if review.get("sizePolicy") != "FILED_WEIGHTED_AVERAGE_SHARES_X_AS_TRADED_PRICE_PROXY":
        reasons.append("SIZE_PROXY_NOT_EXPLICIT")
    allowed = {"CURRENT_MEMBER_OWN_PANEL", "REMOVED_FROM_INDEX_STILL_TRADING"}
    if not review.get("acceptedIdentityCategories") or not set(review["acceptedIdentityCategories"]) <= allowed:
        reasons.append("UNSAFE_OR_EMPTY_IDENTITY_CATEGORY_SCOPE")
    if set(review.get("acceptedIdentityCategories", ())) != set(spec["acceptedIdentityCategories"]):
        reasons.append("REVIEW_IDENTITY_SCOPE_MISMATCH")
    if review.get("allowRedistribution") is not False or review.get("productionPromotion") is not False:
        reasons.append("SCOPE_EXCEEDS_INTERNAL_RESEARCH")
    return {"status": "ADMITTED_CONDITIONALLY" if not reasons else "BLOCKED", "reasons": sorted(set(reasons)),
            "reviewSha256": IF.digest(review), "outcomeReads": 0, "modelFits": 0,
            "unbiasedFullUniverseEvidence": False, "productionPromotion": False}


def source_preflight(root, spec):
    """Inspect through a remote-free local view, including partial-clone inputs."""
    try:
        with local_view(root) as view:
            missing = [c for c in sorted({spec["sourceCommit"], spec["metadataCommit"]}) if object_type(view, c) != "commit"]
            if missing:
                return {"status": "BLOCKED", "reason": "PINNED_COMMIT_METADATA_MISSING",
                        "missingCommits": missing, "payloadReads": 0}
            return _source_preflight_local(view, spec)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        return {"status": "BLOCKED", "reason": "SOURCE_METADATA_UNAVAILABLE:" + type(error).__name__, "payloadReads": 0}


def _source_preflight_local(root, spec):
    """Git object TYPE/SIZE only; no price/action/filing payload is opened.

    Prevent consuming an owner permit on a known incomplete partial clone.
    Only the already-pinned input manifest (hash/path metadata) is read.
    """
    from scripts import inspect_experiment_sources as S
    try:
        if spec["sourceCommit"] != S.SOURCE_COMMIT or spec["metadataCommit"] != S.CODE_BASE:
            raise ValueError("SOURCE_COMMIT_OUTSIDE_FIXED_REUSE_SCOPE")
        manifest = json.loads(S.Sources(root).blob(S.SOURCE_COMMIT, S.MANIFEST))
        if IF.digest({k: v for k, v in manifest.items() if k != "sha256"}) != spec["sourceManifestSha256"]:
            raise ValueError("SOURCE_MANIFEST_CHANGED")
        lo, hi = spec["sourceWindow"]["priceStart"][:7], spec["sourceWindow"]["priceThrough"][:7]
        refs = {ref for name, parts in manifest["components"].items() if
                name in ("price/source", "benchmark/source", "corporate-events/source") or
                name.startswith(("price/20", "benchmark/20", "corporate-events/20")) and lo <= name.split("/")[1] <= hi for ref in parts}
        paths = {S.SOURCE_COMMIT + ":ledger/replay-inputs/objects/" + ref + ".json.gz" for ref in refs}
        paths.update(S.SOURCE_COMMIT + f":ledger/fundamentals/us/finnhub-{year}.jsonl.gz"
                     for year in range(2011, spec["sourceWindow"]["lastFilingFiscalYear"] + 1))
        paths.update(S.CODE_BASE + ":" + p for p in (S.MEMBERS, S.SECTORS, S.US_IDENTITY))
        ordered = sorted(paths)
        lines = subprocess.check_output(["git", "cat-file", "--batch-check=%(objecttype) %(objectsize)"], cwd=root,
            input="\n".join(ordered) + "\n", text=True, stderr=subprocess.DEVNULL,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}).splitlines()
        missing = [path for path, line in zip(ordered, lines) if not line.startswith("blob ")]
        if len(lines) != len(ordered):
            raise ValueError("INCOMPLETE_OBJECT_METADATA_RESPONSE")
        return {"status": "BLOCKED" if missing else "READY", "requiredObjects": len(ordered),
                "missingObjects": len(missing), "missingPathsSha256": IF.digest(missing),
                "missingExamples": missing[:3], "payloadReads": 0}
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        return {"status": "BLOCKED", "reason": "SOURCE_METADATA_UNAVAILABLE:" + type(error).__name__, "payloadReads": 0}


def preflight(root, spec, review):
    result, local = admission(spec, review), source_preflight(root, spec)
    if local["status"] != "READY":
        result["status"] = "BLOCKED"
        result["reasons"] = sorted([*result["reasons"], "LOCAL_SOURCE_OBJECTS_NOT_READY"])
    return {**result, "sourcePreflight": local}


def runtime_versions():
    return {"python": sys.version.split()[0], **{p: importlib.metadata.version(p) for p in
        ("pandas", "numpy", "scipy", "scikit-learn", "exchange-calendars")}}


def prior_attempts(api=None):
    # The default is resolved at call time so metadata-only offline tests can
    # inject the same tiny API surface as authorization.
    api = api or github
    return sorted(r["ref"] for r in api([f"repos/{REPOSITORY}/git/matching-refs/tags/wid-exploration-attempt-"]))


def request(root, spec, review, *, created_at, run_root, prior_claims=()):
    root, run_root = Path(root), Path(run_root)
    P.utc(created_at)
    # Resolve existing parent symlinks too; output never overlaps repository or
    # old sealed outputs. All five layers remain physically disjoint.
    run_root = run_root.resolve()
    if not run_root.is_relative_to(EXECUTION_ROOT.resolve()) or run_root == EXECUTION_ROOT.resolve():
        raise ValueError("DEDICATED_EXECUTION_DIRECTORY_REQUIRED")
    layout = RunLayout(**{k: str(run_root / k) for k in ("universe", "features", "labels", "decisions", "evaluation")})
    code = {p: file_sha(root / p) for p in CLOSURE}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    body = {"repository": REPOSITORY, "spec": spec, "specSha256": IF.digest(spec), "review": review,
            "admission": preflight(root, spec, review), "codeCommit": head, "codeHashes": code,
            "createdAt": created_at, "layout": asdict(layout), "runRoot": str(run_root),
            "runtime": runtime_versions(), "priorClaims": sorted(prior_claims),
            "actions": ["claim one new wid-exploration attempt tag", "read pinned source inputs including matured outcomes",
                        "fit the fixed exploratory models", "write disjoint append-only local research outputs"],
            "productionPromotion": False}
    return {**body, "sha256": IF.digest(body)}


def verify_request(value, root, *, now):
    body = {k: v for k, v in value.items() if k != "sha256"}
    if IF.digest(body) != value.get("sha256") or value.get("repository") != REPOSITORY:
        raise ValueError("REQUEST_DIGEST_OR_REPOSITORY_MISMATCH")
    if IF.digest(value["spec"]) != value["specSha256"] or admission(value["spec"], value["review"])["status"] != "ADMITTED_CONDITIONALLY":
        raise ValueError("SOURCE_ADMISSION_BLOCKED")
    local = source_preflight(root, value["spec"])
    if (local["status"] != "READY" or value["admission"]["status"] != "ADMITTED_CONDITIONALLY" or
            value["admission"].get("sourcePreflight") != local):
        raise ValueError("LOCAL_SOURCE_OBJECTS_NOT_READY_OR_CHANGED")
    age = P.utc(now) - P.utc(value["createdAt"])
    if not 0 <= age.total_seconds() <= 7 * 86400:
        raise ValueError("REQUEST_EXPIRED_OR_FUTURE_DATED")
    for path, sha in value["codeHashes"].items():
        if path not in CLOSURE or file_sha(Path(root) / path) != sha:
            raise ValueError("CODE_CHANGED_AFTER_REQUEST:" + path)
    if set(value["codeHashes"]) != set(CLOSURE):
        raise ValueError("CODE_CLOSURE_INCOMPLETE")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if head != value["codeCommit"]:
        raise ValueError("CODE_COMMIT_CHANGED")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise ValueError("CLEAN_APPROVED_CODE_WORKTREE_REQUIRED")
    if value.get("runtime") != runtime_versions():
        raise ValueError("RUNTIME_CHANGED_AFTER_REQUEST")
    expected = {k: str(Path(value["runRoot"]).resolve() / k) for k in value["layout"]}
    if expected != value["layout"] or not Path(value["runRoot"]).resolve().is_relative_to(EXECUTION_ROOT.resolve()):
        raise ValueError("OUTPUT_LAYOUT_CHANGED")
    RunLayout(**value["layout"])
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", value["spec"]["id"]):
        raise ValueError("SAFE_VERSIONED_STUDY_ID_REQUIRED")


def github(args):
    return json.loads(subprocess.check_output(["gh", "api", *args], text=True))


def authorize(value, root, *, comment_id, now, api=github):
    """No approval flag. Fetch a repository-owner comment, then claim once.

    `api` injection exists for synthetic regression tests, never a CLI option.
    """
    verify_request(value, root, now=now)
    if type(comment_id) is not int or comment_id <= 0:
        raise ValueError("OWNER_COMMENT_ID_REQUIRED")
    comment = api([f"repos/{REPOSITORY}/issues/comments/{comment_id}"])
    expected = "APPROVE WID_EXECUTION " + value["sha256"]
    if (comment.get("user", {}).get("login", "").lower() != OWNER or
            comment.get("author_association") != "OWNER" or comment.get("body", "").strip() != expected or
            not str(comment.get("html_url", "")).startswith("https://github.com/" + REPOSITORY + "/issues/") and
            not str(comment.get("html_url", "")).startswith("https://github.com/" + REPOSITORY + "/pull/")):
        raise ValueError("EXACT_OWNER_APPROVAL_REQUIRED")
    if not P.utc(value["createdAt"]) <= P.utc(comment["created_at"]) <= P.utc(now):
        raise ValueError("APPROVAL_TIME_INVALID")
    if value.get("priorClaims") != prior_attempts(api):
        raise ValueError("ATTEMPT_HISTORY_CHANGED_AFTER_REQUEST")
    if value["priorClaims"] and not value["spec"]["resultInformed"]:
        raise ValueError("PRIOR_OUTCOME_EXPOSURE_REQUIRES_NEW_RESULT_INFORMED_VERSION")
    tag = "refs/tags/wid-exploration-attempt-" + value["spec"]["id"]
    # GitHub's atomic create fails on an existing ref. No old seal, tag or
    # receipt can be overwritten; a failed attempt also consumes this permit.
    claim = api([f"repos/{REPOSITORY}/git/refs", "-X", "POST", "-f", "ref=" + tag, "-f", "sha=" + value["codeCommit"]])
    if claim.get("ref") != tag or claim.get("object", {}).get("sha") != value["codeCommit"]:
        raise ValueError("DURABLE_ATTEMPT_CLAIM_NOT_VERIFIED")
    return VerifiedPermit({"requestSha256": value["sha256"], "approvalComment": comment["html_url"], "claimRef": tag,
            "specSha256": IF.digest(value["spec"]), "reviewSha256": IF.digest(value["review"]),
            "authorizedAt": now, "codeCommit": value["codeCommit"]}, _AUTHENTICATED)


def append_record(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def journal_record(value, *, status, reason, result_informed, prior=()):
    return trial_record(prior, version=value["spec"]["id"] + ":" + value["sha256"], reason=reason,
                        result_informed=result_informed, specification={"requestSha256": value["sha256"], "status": status,
                            "codeCommit": value["codeCommit"], "seed": value["spec"]["seed"]})
