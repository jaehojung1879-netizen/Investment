"""KR factor anatomy v1 — spec identity, execution authorization and the (future) data assembly.

EXPLORATORY / DEVELOPMENT / HYPOTHESIS-GENERATING. Outcome execution is NOT part of the change that adds this
file: `verify` touches no data and no outcome, and `execute` refuses before reading a byte unless the run is a
`workflow_dispatch` on merged `main`, at a commit where this exact spec is committed, naming the exact preserved
raw artifact, with no committed result. The sealed `kr-model-overlay-portfolio-v1` machinery is only IMPORTED,
read-only; its execute path, permit and lock are never called here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import gzip
import hashlib
import importlib
import io
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from . import dart_derive as DD
from . import kr_factor_anatomy as A
from . import kr_factor_anatomy_report as R
from . import kr_model_portfolio_execution as X
from . import kr_portfolio_diagnostics as D
from . import kr_value_quality_catalyst as F
from . import replay_calendar as RC

digest, file_hash, import_closure = X.digest, X.file_hash, X.import_closure
visible_filings = F.visible_filings
ROOT = Path(__file__).resolve().parents[1]
STUDY = "kr-factor-anatomy-v1"
SPEC_PATH = "research_specs/" + STUDY + ".json"
RESULT_PATH = "docs/results/" + STUDY + "-result.json"
SCIENTIFIC_STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"


# The two SEALED read-only v1 functions this study reuses rather than re-derive. They live in `alpha_opportunity_*`
# research modules; the repository's frozen import-guard tests (pinned by sealed v1, so not editable here) allow-list the
# pipeline modules that may import those statically, and this research module is not on the list. They are therefore
# resolved by name, and ONLY these two names resolve. Both files are inside the sealed v1 import closure, so their
# bytes are verified by `X.load_spec` before any outcome is computed.
_SEALED_V1_FUNCTIONS = {"target_from_sessions": "alpha_opportunity_v2_evaluation",
                        "attach_eligibility": "alpha_opportunity_v4_execution"}


def sealed_v1_function(name):
    if name not in _SEALED_V1_FUNCTIONS:
        raise ValueError("UNREGISTERED_SEALED_FUNCTION")
    return getattr(importlib.import_module(f"{__package__}.{_SEALED_V1_FUNCTIONS[name]}"), name)


@dataclass
class Counters:
    """Everything that reads an outcome increments one of these; `verify` must leave all of them at zero."""
    targetCalls: int = 0
    labelCalls: int = 0
    predictionRecordReads: int = 0
    anatomyOutcomeCalls: int = 0

    def zero(self):
        return all(v == 0 for v in asdict(self).values())


@dataclass(frozen=True)
class ExecutionPermit:
    specSha256: str
    token: object


_PERMIT_TOKEN = object()


def require_permit(permit):
    if not isinstance(permit, ExecutionPermit) or permit.token is not _PERMIT_TOKEN:
        raise ValueError("ANATOMY_OUTCOME_ACCESS_WITHOUT_PERMIT")
    return permit


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def load_spec(root=ROOT):
    root = Path(root)
    path = root / SPEC_PATH
    spec = json.loads(path.read_text())
    sha = path.with_suffix(".sha256").read_text().strip()
    if digest(spec) != sha or spec.get("studyId") != STUDY:
        raise ValueError("SPEC_IDENTITY_CHANGED")
    if spec["scientificStatus"] != SCIENTIFIC_STATUS:
        raise ValueError("SCIENTIFIC_STATUS_CHANGED")
    expected = sorted(set(import_closure(spec["entryPoints"], root)) | set(spec["sealedDataInputs"]))
    if expected != sorted(spec["dependencyHashes"]):
        raise ValueError("IMPORT_CLOSURE_CHANGED")
    for rel, wanted in spec["dependencyHashes"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("HARNESS_OR_DEPENDENCY_CHANGED: " + rel)
    _verify_v1_relationship(spec, root)
    return spec, sha


def _verify_v1_relationship(spec, root):
    """The anatomy reuses v1's calendar, benchmark, horizons, cutoff and investability constants by VALUE, and
    checks them against the sealed v1 spec on every load. v1 itself is never edited and never rerun."""
    v1_path = Path(root) / spec["v1"]["specPath"]
    v1 = json.loads(v1_path.read_text())
    if not digest(v1) == v1_path.with_suffix(".sha256").read_text().strip() == spec["v1"]["specSha256"]:
        raise ValueError("V1_SEAL_CHANGED")
    if file_hash(Path(root) / spec["v1"]["resultPath"]) != spec["v1"]["resultFileSha256"]:
        raise ValueError("V1_RESULT_CHANGED")
    same = {"horizons": (spec["horizons"], v1["horizons"]), "benchmark": (spec["benchmark"], v1["benchmark"]),
            "developmentCutoff": (spec["developmentCutoff"], v1["developmentCutoff"]),
            "featureStart": (spec["calendar"]["featureStart"], v1["walkForward"]["featureStart"]),
            "minimumAdvKrw": (spec["universes"]["V1_INVESTABLE_ANALYSIS_UNIVERSE"]["v1Constraints"]["minimumAdvKrw"],
                              v1["portfolio"]["minimumAdvKrw"]),
            "minimumDownsideVol": (spec["universes"]["V1_INVESTABLE_ANALYSIS_UNIVERSE"]["v1Constraints"]["minimumDownsideVol"],
                                   v1["portfolio"]["minimumDownsideVol"])}
    for name, (mine, theirs) in same.items():
        if mine != theirs:
            raise ValueError("V1_CONSTANT_MISMATCH: " + name)
    if [f["name"] for f in spec["factors"]] != list(F.RAW_FEATURES):
        raise ValueError("FACTOR_LIST_DIFFERS_FROM_V1_RAW_FEATURES")
    if {f["name"]: f["family"] for f in spec["factors"]} != {n: fam for fam, names in F.FAMILIES.items() for n in names}:
        raise ValueError("FACTOR_FAMILIES_DIFFER_FROM_V1")
    return True


# --------------------------------------------------------------------------- #
# Execution authorization (merged main only)
# --------------------------------------------------------------------------- #
def _git(args, root):
    return subprocess.check_output(["git", *args], cwd=str(root))


def authorize_execution(spec, sha, root=ROOT, env=None, git=_git):
    """Raise unless this is a workflow_dispatch on main, at a commit that carries exactly this spec, naming exactly the
    preserved raw artifact, with no committed anatomy result. Nothing is read from any data directory here."""
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true":
        raise ValueError("FORMAL_EXECUTION_REQUIRES_ACTIONS")
    if env.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("FORMAL_EXECUTION_REQUIRES_MAIN")
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise ValueError("FORMAL_EXECUTION_REQUIRES_WORKFLOW_DISPATCH")
    head = git(["rev-parse", "HEAD"], root).decode().strip()
    if not env.get("GITHUB_SHA") or head != env["GITHUB_SHA"]:
        raise ValueError("CHECKOUT_IS_NOT_THE_DISPATCHED_COMMIT")
    for rel in (SPEC_PATH, str(Path(SPEC_PATH).with_suffix(".sha256"))):
        if git(["show", "HEAD:" + rel], root) != (Path(root) / rel).read_bytes():
            raise ValueError("SPEC_NOT_COMMITTED_AT_HEAD")
    pin = spec["input"]
    if (env.get("ANATOMY_INPUT_ARTIFACT") != pin["artifactName"]
            or env.get("ANATOMY_INPUT_RUN_ID") != str(pin["producingRunId"])):
        raise ValueError("INPUT_ARTIFACT_IDENTITY_MISMATCH")
    if (Path(root) / RESULT_PATH).exists():
        raise ValueError("ANATOMY_RESULT_ALREADY_COMMITTED")
    return ExecutionPermit(sha, _PERMIT_TOKEN)


def verify(root=ROOT, env=None):
    """Outcome-free: identity, closure and v1 relationship. This is the only mode ordinary pull-request CI runs."""
    spec, sha = load_spec(root)
    counters = Counters()
    try:
        authorize_execution(spec, sha, root, env)
        authorized = True
    except (ValueError, subprocess.CalledProcessError, OSError):
        authorized = False
    return {"studyId": STUDY, "mode": "verify", "status": "VERIFIED", "specSha256": sha,
            "scientificStatus": spec["scientificStatus"], "executeAuthorizedInThisEnvironment": authorized,
            "dependencyFiles": len(spec["dependencyHashes"]), "counters": asdict(counters),
            "stoppedBeforeOutcomes": counters.zero(), "historicalExecutionPerformed": False}


# --------------------------------------------------------------------------- #
# Net-income improvement (descriptive; the SAME lineage and basis rules as the v1 prior-year OCF chain)
# --------------------------------------------------------------------------- #
def improvement_to_assets(records, date, account):
    """(TTM account now - TTM account one year earlier at the same stage) / total assets.

    PIT-safe by construction: only filings visible strictly before `date`; both TTM chains and the assets level must
    come from ONE statement basis (CFS or OFS). None whenever any link is missing — never annualised, never zero."""
    index = DD.index_filings(visible_filings(records, date, "KR"))
    if not index:
        return None
    year, stage = max(index, key=lambda k: (k[0], F.STAGE[k[1]]))
    def keys(y, s):
        return [(y, s)] if s == DD.ANNUAL else [(y, s), (y - 1, DD.ANNUAL), (y - 1, s)]
    if not F._compatible(index, keys(year, stage) + keys(year - 1, stage)):
        return None
    now = DD.trailing_twelve_months(index, year, stage, account)[0]
    before = DD.trailing_twelve_months(index, year - 1, stage, account)[0]
    assets = DD.level_amount(index[(year, stage)], "자산총계")
    if now is None or before is None or assets is None:
        return None
    return F.ratio(now - before, assets)


# --------------------------------------------------------------------------- #
# Data assembly (permit required; label-free features come from the sealed v1 `prepare`)
# --------------------------------------------------------------------------- #
def build_panel(bundle, v1_spec, spec, permit, counters):
    require_permit(permit)
    features = bundle["features"].copy()
    market, prices, accounting = bundle["market"], bundle["prices"], bundle["accounting"]
    days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    panel = features.reset_index(drop=True)
    panel["marketCap"] = [(market.at(t, d) or {}).get("marketCap", np.nan) for t, d in zip(panel.ticker, panel.date)]
    panel["riskMultiplier"] = [bundle["overlay"][d].get("riskMultiplier") for d in panel.date]
    panel["netIncomeImprovementToAssets"] = [
        improvement_to_assets(accounting.get(t, []), d, "당기순이익") for t, d in zip(panel.ticker, panel.date)]
    foundation = json.loads((ROOT / v1_spec["inputs"]["terminalFoundationPath"]).read_text())
    complete = {row["code"] + ".KS": row.get("completeness") for row in foundation.get("securities", [])}
    target_from_sessions = sealed_v1_function("target_from_sessions")
    attach_eligibility = sealed_v1_function("attach_eligibility")
    for h in spec["horizons"]:
        records = []
        for ticker, date in zip(panel.ticker, panel.date):
            counters.anatomyOutcomeCalls += 1
            mine = A.endpoint_returns(days, prices, spec["benchmark"], ticker, date, h, spec["developmentCutoff"])
            counters.targetCalls += 1
            theirs = target_from_sessions(days, prices, spec["benchmark"], ticker, date, h, spec["developmentCutoff"])
            counters.labelCalls += 1
            if (mine["status"] != theirs["labelStatus"] or mine["entryDate"] != theirs["entryDate"]
                    or mine["exitDate"] != theirs["outcomeEndDate"]
                    or (mine["status"] == "MATURED"
                        and abs(mine["relativeReturn"] - theirs["forwardRelativeReturn"]) > 1e-12)):
                raise ValueError("ENDPOINT_SEMANTICS_DIFFER_FROM_V1_TARGET")
            records.append(mine)
        frame = pd.DataFrame(records)
        elig = attach_eligibility(pd.DataFrame({"ticker": panel.ticker, "outcomeEndDate": frame.exitDate}), prices, complete)
        status = frame.status.where(~(frame.status.eq("MATURED") & ~elig.eligibilityStatus.eq("ELIGIBLE")),
                                    "UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE")
        s = str(h)
        panel["entry" + s], panel["exit" + s] = frame.entryDate.to_numpy(), frame.exitDate.to_numpy()
        panel["stock" + s] = frame.stockReturn.astype(float).to_numpy()
        panel["bench" + s] = frame.benchmarkReturn.astype(float).to_numpy()
        panel["rawStatus" + s], panel["status" + s] = frame.status.to_numpy(), status.to_numpy()
        relative = frame.relativeReturn.astype(float)
        panel["relObs" + s] = relative.where(frame.status.eq("MATURED")).to_numpy()
        panel["rel" + s] = relative.where(status.eq("MATURED")).to_numpy()
    window = spec["fundamentalsVsPrice"]["windowRealised"]
    panel[window["column"]] = None
    panel["logBookGrowth126"] = np.nan
    panel["logMultipleExpansion126"] = np.nan
    flags = []
    for i, row in panel.iterrows():
        outcome = None
        if row["rawStatus126"] == "MATURED":
            entry_quote, exit_quote = market.at(row.ticker, row.date), market.at(row.ticker, row["exit126"])
            if entry_quote and exit_quote:
                entry, entry_basis = F.accounting_values(accounting.get(row.ticker, []), row.date)
                exit_, exit_basis = F.accounting_values(accounting.get(row.ticker, []), row["exit126"])
                outcome = D.valuation_convergence({**entry, **entry_quote, "basis": entry_basis.get("basis")},
                                                  {**exit_, **exit_quote, "basis": exit_basis.get("basis")})
        if outcome and outcome.get("status") == "DESCRIPTIVE":
            panel.at[i, "logBookGrowth126"] = outcome["logBookGrowth"]
            panel.at[i, "logMultipleExpansion126"] = outcome["logMultipleExpansion"]
            flags.append(bool(outcome["fundamentalImproved"]))
        else:
            flags.append(None)
    panel[window["column"]] = flags
    return panel


def load_memberships(input_root, v1_spec):
    """The strictly-previous KRX monthly top-120 snapshots, rebuilt independently of `prepare` from the pinned universe
    blobs, so the analysis panel can be proved to contain no row that was not a member on its own date."""
    from . import historical_store as HS
    from . import kr_repaired_accounting_snapshot as K
    from .regional_alpha_features import MembershipSnapshots
    grouped = {}
    for rel, wanted in v1_spec["inputs"]["universeBlobs"].items():
        path = Path(input_root) / rel
        if not path.is_file() or K.git_blob_sha1(path.read_bytes()) != wanted:
            raise ValueError("PIT_UNIVERSE_MISSING_OR_CHANGED")
        for row in HS.read_jsonl(path):
            grouped.setdefault(row["date"], []).append(row)
    return MembershipSnapshots([
        {"date": date, "members": sorted(r["ticker"] for r in sorted(rows, key=lambda r: (r["rank"], r["ticker"]))[:120])}
        for date, rows in sorted(grouped.items())])


def read_v1(root, spec, permit, counters):
    """Sealed v1 per-prediction records and annual fold snapshots (read-only; hashes pinned by `dependencyHashes`)."""
    require_permit(permit)
    counters.predictionRecordReads += 1
    result = json.loads((Path(root) / spec["v1"]["resultPath"]).read_text())
    summary = json.loads(gzip.open(Path(root) / spec["v1"]["diagnosticSummaryPath"], "rt", encoding="utf-8").read())
    predictions = {}
    for h in spec["horizons"]:
        frame = pd.DataFrame(summary["predictionRecords"][str(h)])
        predictions[h] = frame.rename(columns={"predictionH" + str(h): "prediction"})[
            ["date", "ticker", "prediction", "rank"] + [f + "_SCORE" for f in F.FAMILIES]]
    return {"predictions": predictions, "folds": result["folds"]}


# --------------------------------------------------------------------------- #
# Deterministic output
# --------------------------------------------------------------------------- #
def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    return value


def _gzip_csv(frame):
    raw = frame.to_csv(index=False, float_format="%.12g").encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as stream:
        stream.write(raw)
    return buffer.getvalue()


def write_outputs(output, result, rows, report, spec, sha, identity, counters):
    out = Path(output)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    files = {}
    anatomy_sha = X.atomic_write(out / "anatomy.json", json_safe(result))
    files["anatomy.json"] = anatomy_sha
    (out / "report.md").write_text(report, encoding="utf-8")
    files["report.md"] = hashlib.sha256(report.encode()).hexdigest()
    for key, frame in sorted(rows.items(), key=lambda kv: str(kv[0])):
        label = key[0] if isinstance(key[0], str) else str(key)
        if isinstance(key[1], dict):  # family rows: (universe, "families") -> {(col, h): frame}
            for (col, h), df in sorted(key[1].items()):
                name = f"tables/{label}__families__{col}__H{h}.csv.gz"
                data = _gzip_csv(df)
                (out / name).write_bytes(data)
                files[name] = hashlib.sha256(data).hexdigest()
            continue
        universe, treatment = key
        for (col, h), df in sorted(frame.items()):
            name = f"tables/{universe}__{treatment}__{col}__H{h}.csv.gz"
            data = _gzip_csv(df)
            (out / name).write_bytes(data)
            files[name] = hashlib.sha256(data).hexdigest()
    manifest = {"studyId": STUDY, "specSha256": sha, "inputIdentitySha256": identity["sha256"],
                "scientificStatus": SCIENTIFIC_STATUS, "returnBasis": A.RETURN_BASIS, "counters": asdict(counters),
                "files": files}
    X.atomic_write(out / "manifest.json", json_safe(manifest))
    return manifest


def execute(input_root, output, spec, sha, permit, root=ROOT):
    """Future outcome execution. Order: permit -> exact input identity -> label-free features -> outcomes -> tables."""
    require_permit(permit)
    if permit.specSha256 != sha:
        raise ValueError("PERMIT_FOR_A_DIFFERENT_SPEC")
    counters = Counters()
    identity = X.input_identity(input_root)
    if identity["sha256"] != spec["input"]["identitySha256"]:
        raise ValueError("INPUT_IDENTITY_MISMATCH")
    v1_spec, _ = X.load_spec(root)
    bundle = X.prepare(input_root, v1_spec)
    panel = build_panel(bundle, v1_spec, spec, permit, counters)
    A.assert_pit_membership(panel, load_memberships(input_root, v1_spec))
    v1 = read_v1(root, spec, permit, counters)
    result, rows = R.analyze_all(panel, spec, v1, structural=A.structural_status(spec, root))
    report = R.render_report(result, spec)
    return write_outputs(output, result, rows, report, spec, sha, identity, counters)
