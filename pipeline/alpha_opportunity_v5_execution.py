"""KR-only execution harness for the SEALED `alpha-opportunity-model-v5` preregistration.

Research only; no production import; no promotion; no portfolio field.

This module is NOT part of the preregistration's dependency closure. PR #174 froze
`research_specs/alpha-opportunity-model-v5.json` and deliberately left the execution
harness out of `dependencyHashes`; `scripts/run_alpha_opportunity_model_v5.py` and
`pipeline/alpha_opportunity_v5_spec.py` stay byte-identical and this harness only
IMPORTS them. Nothing here changes a horizon, feature, model family, hyperparameter,
cost, transform, purge, calendar, statistic, interval, threshold or claim rule: every
one of those is read from the sealed spec, and where the sealed spec inherits from v4
the value is read from the spec's own digest-verified `inherited` copy.

ORDER, ENFORCED BY CONSTRUCTION (the lesson of the v4 executions, whose first harness
built ~170k forward labels before its coverage gate and then reported that it had not):

  1. `IdentityGuard.freeze`: sealed v5 digest and dependency closure, v1-v4 seals and
     inherited values, KR accounting snapshot identity, sealed raw-input blobs,
     calibrated-inference pins, terminal-action execution snapshot, harness code.
  2. PIT features (`build_kr_matrix`), then the tradability guard.
  3. `pre_label_gates`: feature coverage per cell and the calendar-depth upper bound.
     A failure raises `PreLabelStop`; NO label, fit, prediction or evaluation has run.
  4. `issue_label_permit`: only a `GatesPassed` object obtained from step 3 can be
     exchanged for a `LabelPermit`, and doing so re-verifies EVERY frozen identity.
  5. `build_labels` refuses to run without a `LabelPermit`. Labels, eligibility, folds,
     the B0-B5 fits, the statistics and the calibrated intervals exist only past here.
  6. identity is verified once more after evaluation, so the artifact can state that no
     protocol input moved during the run.

`Counters` are incremented AT THE CALL SITES of the outcome-reading functions, so a run
that stopped early reports the zeros it observed; `stoppedBeforeLabels` is DERIVED from
those counters and never asserted independently of them.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Callable
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

from . import alpha_opportunity_features as F
from . import alpha_opportunity_model as V1
from . import alpha_opportunity_v2_decision as D
from . import alpha_opportunity_v2_evaluation as E
from . import alpha_opportunity_v2_model as M
from . import alpha_opportunity_v4_eligibility as ELIG
from . import alpha_opportunity_v4_execution as X4
from . import alpha_opportunity_v5_evidence as EV
from . import alpha_opportunity_v5_spec as S5
from . import kr_repaired_accounting_snapshot as K
from . import replay_calendar as RC
from .alpha_opportunity_spec import canonical, digest, file_hash, read_json

CONTRACT = "ALPHA_OPPORTUNITY_V5_KR_EXECUTION_HARNESS_V1"
STUDY = S5.STUDY
KR_BENCHMARK = "069500.KS"
RESULT_NAME = "alpha-opportunity-model-v5-result.json"
REPLAY_MANIFEST = "ledger/historical/replay-v16/inputs.json"
RAW_READ_PATTERNS = (("ledger/universe/kr", "krx-universe-*.jsonl.gz"),
                     ("ledger/fundamentals/kr", "shares.jsonl.gz"))
ACCOUNTING_FIELDS = ("assetGrowthPct", "debtGrowthPct")
MATURED = E.MATURED
UNRESOLVED = E.UNRESOLVED
FORMAL = "FORMAL_EXECUTION"
GATES_ONLY = "GATES_ONLY_NO_LABELS"
HARNESS_FILES = ("pipeline/alpha_opportunity_v5_execution.py", "pipeline/alpha_opportunity_v5_evidence.py",
                 "scripts/execute_alpha_opportunity_model_v5.py")
# Registered non-success reasons. Each maps to a claim status; none is ever "fixed" by editing a threshold.
GATE_INTEGRITY = "BLOCKED_BY_DATA_INTEGRITY"
GATE_DEPTH = "BLOCKED_BY_SAMPLE_DEPTH"


class PreLabelStop(Exception):
    """A registered pre-label gate failed. No label has been constructed."""

    def __init__(self, status, detail):
        super().__init__(status)
        self.status, self.detail = status, detail


class InputIdentityChanged(ValueError):
    """A frozen execution input moved after it was frozen."""


class OrderingViolation(RuntimeError):
    """An outcome-reading step was requested before every pre-label gate passed."""


class ModelFitFailure(RuntimeError):
    """A PRIMARY model (B0/B2/B3/B4) could not be fitted: an execution failure, not a data result."""


# --------------------------------------------------------------------------- #
# Runtime spec: assembled from the sealed v5 file alone; no number is invented.
# --------------------------------------------------------------------------- #
def build_runtime_spec(spec: dict) -> dict:
    inherited = {name: entry["value"] for name, entry in spec["inherited"].items()}
    base = inherited["walkForwardBase"]
    return {
        "studyId": spec["studyId"], "horizons": list(inherited["horizons"]), "regions": list(spec["regions"]),
        "benchmarks": dict(inherited["benchmarks"]), "dataCutoff": inherited["dataCutoff"],
        "models": inherited["models"], "transforms": inherited["transforms"],
        "uncertainty": inherited["uncertainty"], "transactionCosts": inherited["transactionCosts"],
        "tradabilityGuard": inherited["tradabilityGuard"], "modelIds": dict(spec["modelIds"]),
        "walkForward": {key: base[key] for key in ("featureStart", "minimumHistoryMonths",
                                                   "minimumMaturedDates", "minimumNamesPerDate")},
        "allowedFeatures": {"KR": {str(h): list(names) for h, names in spec["modifiedFromV4"]["features"]["KR"].items()}},
        "coverageGate": dict(spec["modifiedFromV4"]["walkForward"]["coverageGate"]),
        "minimumConfirmatoryDepth": {h: int(v["signalWeeks"]) for h, v in spec["inference"]["minimumConfirmatoryDepth"].items()
                                     if h != "meaning"},
    }


class Counters:
    """Incremented at the call sites of every outcome-reading or model-consuming function."""
    NAMES = ("targetFromSessionsCalls", "labelEligibilityCalls", "fitCalls", "predictCalls", "evaluateCalls")

    def __init__(self):
        self.values = dict.fromkeys(self.NAMES, 0)

    def bump(self, name, n=1):
        self.values[name] += n

    def snapshot(self):
        return dict(self.values)

    def any_outcome_call(self) -> bool:
        return any(self.values.values())


# --------------------------------------------------------------------------- #
# Input identity. Every component is a zero-argument function returning a JSON
# value; `freeze` records them all, `assert_unchanged` recomputes ALL of them.
# --------------------------------------------------------------------------- #
class IdentityGuard:
    def __init__(self, components: dict[str, Callable[[], object]]):
        self.components = dict(components)
        self.frozen: dict | None = None
        self.checks: list[dict] = []

    def _measure(self) -> dict:
        return {name: fn() for name, fn in sorted(self.components.items())}

    def freeze(self) -> dict:
        if self.frozen is not None:
            raise OrderingViolation("IDENTITY_ALREADY_FROZEN")
        self.frozen = self._measure()
        self.checks.append({"at": "FROZEN", "identitySha256": digest(self.frozen)})
        return self.frozen

    @property
    def frozen_digest(self) -> str:
        if self.frozen is None:
            raise OrderingViolation("IDENTITY_NOT_FROZEN")
        return digest(self.frozen)

    def assert_unchanged(self, at: str) -> str:
        if self.frozen is None:
            raise OrderingViolation("IDENTITY_NOT_FROZEN")
        now = self._measure()
        moved = sorted(name for name in self.frozen if now.get(name) != self.frozen[name])
        if moved:
            self.checks.append({"at": at, "identitySha256": digest(now), "moved": moved})
            raise InputIdentityChanged(f"INPUT_IDENTITY_CHANGED at {at}: {', '.join(moved)}")
        self.checks.append({"at": at, "identitySha256": digest(now), "moved": []})
        return digest(now)


def git_blob_sha1(path) -> str:
    return X4.git_blob_sha1(path)


def verify_raw_inputs(spec: dict, input_root, *, expected_signal_history_sha=None) -> dict:
    """Byte-level proof the checkout is the sealed signal-history snapshot. Reads no row.

    `INPUT_SNAPSHOT_CHANGED` on any sealed blob missing or different, `UNSEALED_RAW_SHARD`
    on any file this harness WOULD read that the sealed list does not name,
    `REPLAY_MANIFEST_CHANGED` on a manifest digest mismatch and `SIGNAL_HISTORY_COMMIT_MISMATCH`
    when the freeze job's commit is given and the checkout is elsewhere.
    """
    sealed = spec["inputs"]["sealedRaw"]
    root = Path(input_root)
    commit = X4.signal_history_commit(root)
    if expected_signal_history_sha is not None and commit != expected_signal_history_sha:
        raise ValueError(f"SIGNAL_HISTORY_COMMIT_MISMATCH: expected {expected_signal_history_sha}, got {commit}")
    for rel, sha in sorted(sealed["gitBlobSha1"].items()):
        path = root / rel
        if not path.is_file() or git_blob_sha1(path) != sha:
            raise ValueError("INPUT_SNAPSHOT_CHANGED: " + rel)
    for folder, pattern in RAW_READ_PATTERNS:
        for path in sorted((root / folder).glob(pattern)):
            rel = str(path.relative_to(root))
            if rel not in sealed["gitBlobSha1"]:
                raise ValueError("UNSEALED_RAW_SHARD: " + rel)
    manifest = json.loads((root / REPLAY_MANIFEST).read_text())
    got = digest({k: v for k, v in manifest.items() if k != "sha256"})
    if not got == manifest.get("sha256") == sealed["replayManifestSha256"]:
        raise ValueError("REPLAY_MANIFEST_CHANGED: " + got)
    return {"sealedSignalHistoryCommit": sealed["signalHistoryCommit"], "signalHistoryCommit": commit,
            "replayManifestSha256": got, "blobsVerified": len(sealed["gitBlobSha1"]),
            "blobIdentitySha256": digest(dict(sorted(sealed["gitBlobSha1"].items())))}


def verify_snapshot_dir(pin: dict, merged_dir) -> dict:
    """The KR repaired accounting snapshot on disk is exactly the frozen one."""
    files = K.shard_files(Path(merged_dir))
    blobs = {p.name: K.git_blob_sha1(p.read_bytes()) for p in files}
    if blobs != pin["gitBlobSha1"]:
        raise ValueError("SNAPSHOT_SHARD_IDENTITY_CHANGED")
    if K.candidate_identity(blobs) != pin["candidateIdentitySha256"]:
        raise ValueError("SNAPSHOT_IDENTITY_CHANGED")
    shards = {p.name: K.read_shard(p) for p in files}
    content = K.content_sha256(shards)
    if content != pin["snapshotContentSha256"]:
        raise ValueError("SNAPSHOT_CONTENT_CHANGED")
    if sum(len(rows) for rows in shards.values()) != pin["recordCount"]:
        raise ValueError("SNAPSHOT_RECORD_COUNT_CHANGED")
    return {"snapshotContentSha256": content, "candidateIdentitySha256": pin["candidateIdentitySha256"],
            "recordCount": pin["recordCount"]}


def calibration_identity(spec: dict, root) -> dict:
    """Calibrated-inference pin re-verified (spec file, engine files, statistics, U1, coverage)."""
    S5.verify_calibration_pin(spec, root)
    pin = spec["inference"]["calibration"]
    return {"specFileSha256": pin["specFileSha256"], "engineFiles": dict(sorted(pin["engineFiles"].items())),
            "U1CriticalValue": pin["U1CriticalValue"]}


def spec_identity(spec_path, expected_sha256: str) -> dict:
    """The frozen preregistration file and its sidecar still agree with the digest the run was given."""
    path = Path(spec_path)
    spec = read_json(path)
    sidecar = path.with_suffix(".sha256").read_text().strip()
    if not digest(spec) == sidecar == expected_sha256:
        raise ValueError("SEALED_SPEC_CHANGED")
    return {"specSha256": expected_sha256, "specFileSha256": file_hash(path)}


# --------------------------------------------------------------------------- #
# Terminal-action execution snapshot (inherited v4 `executionDataVersioning`).
# --------------------------------------------------------------------------- #
def foundation_path(v4_spec: dict, root) -> Path:
    return Path(root) / v4_spec["sourceFoundationCitation"]["krTerminalActionReconstructionV2"]["path"]


def cited_foundation_snapshot(v4_spec: dict, root):
    """The reconstruction bytes AS CITED at v4 seal time: the current file if unchanged, else the
    exact blob found in this repository's own history."""
    citation = v4_spec["sourceFoundationCitation"]["krTerminalActionReconstructionV2"]
    path = Path(root) / citation["path"]
    if file_hash(path) == citation["shaAsOfThisSeal"]:
        return read_json(path), {"citedSnapshotSource": "CURRENT_FILE_UNCHANGED_SINCE_SEAL"}
    log = subprocess.check_output(["git", "log", "--follow", "--format=%H", "--", citation["path"]],
                                  cwd=root, text=True).splitlines()
    for rev in log:
        blob = subprocess.check_output(["git", "show", f"{rev}:{citation['path']}"], cwd=root)
        if hashlib.sha256(blob).hexdigest() == citation["shaAsOfThisSeal"]:
            return json.loads(blob), {"citedSnapshotSource": "GIT_HISTORY", "citedSnapshotCommit": rev}
    raise ValueError("CITED_FOUNDATION_SNAPSHOT_NOT_FOUND_IN_HISTORY")


def freeze_foundation(v4_spec: dict, root):
    """Regression check against the cited snapshot, then freeze the CURRENT one, exactly once."""
    cited, provenance = cited_foundation_snapshot(v4_spec, root)
    current = read_json(foundation_path(v4_spec, root))
    record = X4.verify_and_freeze_foundation(cited_snapshot=cited, current_snapshot=current)
    return {**record, **provenance}, current


def foundation_identity_fn(v4_spec: dict, root, frozen_hash: str) -> Callable[[], str]:
    """A guard component: the snapshot on disk still hashes to the frozen value (sealed function)."""
    def check():
        ELIG.assert_snapshot_matches_frozen_hash(
            reconstruction_snapshot=read_json(foundation_path(v4_spec, root)), frozen_hash=frozen_hash)
        return frozen_hash
    return check


# --------------------------------------------------------------------------- #
# PIT features and the tradability guard. No forward price is read here.
# --------------------------------------------------------------------------- #
def load_snapshot_raw(merged_dir) -> dict[str, list[dict]]:
    """Frozen KR accounting snapshot rows by ticker (the ONLY accounting input; v5 never reads
    `ledger/fundamentals/kr/dart-*.jsonl.gz`)."""
    raw: dict[str, list[dict]] = {}
    for path in K.shard_files(Path(merged_dir)):
        for row in K.read_shard(path):
            raw.setdefault(row["ticker"], []).append(row)
    return raw


def load_kr_shares(ledger) -> dict[str, list[dict]]:
    from . import historical_store as HS
    shares: dict[str, list[dict]] = {}
    path = Path(ledger) / "fundamentals/kr/shares.jsonl.gz"
    if path.exists():
        for row in HS.read_jsonl(path):
            shares.setdefault(row["ticker"], []).append(row)
    return shares


def canonical_order(frame: pd.DataFrame) -> pd.DataFrame:
    """Every downstream fit, sum and tie-break sees rows in (date, ticker) order, so the caller's
    row order cannot change a substantive number."""
    return frame.sort_values(["date", "ticker"], kind="stable").reset_index(drop=True)


def attach_tradability(frame, prices, runtime_spec):
    from scripts import run_alpha_opportunity_model_v2 as V2
    window = runtime_spec["tradabilityGuard"]["windowSessions"]
    guard = V2.tradability_frame(prices, frame, "KR", window)
    out = frame.merge(guard, on=["date", "region", "ticker"], how="left", validate="one_to_one")
    if out.tradable.isna().any():
        raise ValueError("TRADABILITY_UNRESOLVED")
    out["tradable"] = out.tradable.astype(bool)
    out["vouched"] = out.vouched.astype(bool)
    return canonical_order(out)


# --------------------------------------------------------------------------- #
# Pre-label gates.
# --------------------------------------------------------------------------- #
class GatesPassed:
    """Produced only by `pre_label_gates` on success; the sole input to `issue_label_permit`."""
    __slots__ = ("cells", "_sealed")

    def __init__(self, cells):
        self.cells = cells
        self._sealed = True


def _finite_share(values) -> float:
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return float(numeric.notna().mean()) if len(numeric) else 0.0


def coverage_table(observed: pd.DataFrame, names) -> dict:
    """{year: {feature: coverage}} over tradable KR name-dates (the frozen denominator)."""
    years = observed.date.str[:4]
    return {str(year): {name: _finite_share(group[name]) if name in group else 0.0 for name in names}
            for year, group in observed.groupby(years)}


def threshold_for(name: str, gate: dict) -> float:
    return gate["price"] if name in F.PRICE + F.ATTENTION else gate["accounting"]


def scheduled_exit(days: pd.DatetimeIndex, date: str, horizon: int):
    """Pure calendar fact: the H-th regional session after next-session entry, or None past the calendar."""
    entry = int(days.searchsorted(pd.Timestamp(date), side="right"))
    return days[entry + horizon] if entry + horizon < len(days) else None


def cell_gate(observed, horizon, runtime_spec, days) -> dict:
    """Coverage start-year rule and calendar-depth upper bound for one horizon cell, from features only."""
    gate, wf = runtime_spec["coverageGate"], runtime_spec["walkForward"]
    names = runtime_spec["allowedFeatures"]["KR"][str(horizon)]
    table = coverage_table(observed, names)
    years = sorted(y for y in table if int(y) >= gate["firstGateYear"])
    passing = {y: all(table[y][n] >= threshold_for(n, gate) for n in names) for y in years}
    start = next((y for y in years if passing[y]), None)
    failures = []
    if start is None:
        failures.append({"reason": "NO_YEAR_PASSES_THE_COVERAGE_GATE"})
    else:
        failures += [{"reason": "COVERAGE_BELOW_FLOOR_AFTER_START", "year": y,
                      "features": {n: table[y][n] for n in names if table[y][n] < threshold_for(n, gate)}}
                     for y in years if int(y) > int(start) and not passing[y]]
    depth = None
    if start is not None:
        per_date = observed.loc[observed.date.str[:4].astype(int) >= int(start)].groupby("date").size()
        cutoff = pd.Timestamp(runtime_spec["dataCutoff"])
        dates = [d for d, n in per_date.items()
                 if n >= wf["minimumNamesPerDate"] and (e := scheduled_exit(days, d, horizon)) is not None and e <= cutoff]
        depth = len(dates)
        floor = runtime_spec["minimumConfirmatoryDepth"][str(horizon)]
        if depth < floor:
            failures.append({"reason": "CALENDAR_DEPTH_UPPER_BOUND_BELOW_FLOOR", "signalWeeksUpperBound": depth,
                             "floor": floor})
    return {"horizon": horizon, "features": list(names), "startYear": None if start is None else int(start),
            "coverageByYear": table, "yearsPassing": passing, "signalWeeksUpperBound": depth, "failures": failures}


def pre_label_gates(frame: pd.DataFrame, runtime_spec: dict, days) -> GatesPassed:
    """FEATURE_COVERAGE then CALENDAR_SAMPLE_DEPTH for every registered cell, on tradable KR name-dates.

    Reads PIT features, the tradability flag and the session calendar only. Any failing cell raises
    `PreLabelStop` for the whole run: gates precede every label, so no cell's labels are built once
    another cell's gate has failed.
    """
    observed = frame.loc[frame.region.eq("KR") & frame.tradable]
    cells = {str(h): cell_gate(observed, h, runtime_spec, pd.DatetimeIndex(days)) for h in runtime_spec["horizons"]}
    failing = {h: c["failures"] for h, c in cells.items() if c["failures"]}
    if failing:
        integrity = any(f["reason"] != "CALENDAR_DEPTH_UPPER_BOUND_BELOW_FLOOR" for fs in failing.values() for f in fs)
        raise PreLabelStop(GATE_INTEGRITY if integrity else GATE_DEPTH, {"cells": cells, "failingCells": sorted(failing)})
    return GatesPassed(cells)


class LabelPermit:
    """Exchangeable only for label construction; issued only after the gates and an identity recheck."""
    __slots__ = ("identity_sha256", "cells")

    def __init__(self, identity_sha256, cells):
        self.identity_sha256, self.cells = identity_sha256, cells


def issue_label_permit(gates, guard: IdentityGuard, counters: Counters) -> LabelPermit:
    if not isinstance(gates, GatesPassed):
        raise OrderingViolation("LABELS_REQUIRE_PASSED_PRE_LABEL_GATES")
    if counters.any_outcome_call():
        raise OrderingViolation("OUTCOME_CALL_BEFORE_PERMIT")
    identity = guard.assert_unchanged("IMMEDIATELY_BEFORE_FIRST_LABEL")
    return LabelPermit(identity, gates.cells)


# --------------------------------------------------------------------------- #
# Labels (past the permit only) and the v4 label-eligibility policy.
# --------------------------------------------------------------------------- #
def build_labels(permit, regional, prices, sessions, runtime_spec, completeness_map, counters, horizon):
    """Forward labels, then per-observation `label_eligibility`. Refuses without a permit."""
    if not isinstance(permit, LabelPermit):
        raise OrderingViolation("LABELS_REQUIRE_A_LABEL_PERMIT")
    rows = []
    for ticker, date in zip(regional.ticker, regional.date):
        counters.bump("targetFromSessionsCalls")
        rows.append(E.target_from_sessions(sessions, prices, runtime_spec["benchmarks"]["KR"], ticker, date,
                                           horizon, runtime_spec["dataCutoff"]))
    data = E.attach_labels(regional, pd.DataFrame(rows))
    counters.bump("labelEligibilityCalls", len(data))
    annotated = X4.attach_eligibility(data, prices, completeness_map)
    modelling = annotated.assign(horizon=horizon)
    ineligible = modelling.labelStatus.eq(MATURED) & ~modelling.eligibilityStatus.eq(ELIG.ELIGIBLE)
    modelling.loc[ineligible, "labelStatus"] = UNRESOLVED
    modelling.loc[ineligible, ["forwardRelativeReturn", "beatBenchmarkNet"]] = None
    return annotated.assign(horizon=horizon), modelling


# --------------------------------------------------------------------------- #
# Fixed models. One code path per estimator; no search anywhere.
# --------------------------------------------------------------------------- #
def _fit_predict(kind, train, valid, names, spec):
    """Fit one registered estimator on the training frame; predict the validation frame.

    kind: 'ridge' (expected gross relative return), 'hgb' (the frozen shallow challenger, same target)
    or 'logistic' (P(net outperform), separate descriptive head). Same guards as `V1.fit_heads`.
    """
    if train.empty or valid.empty or train.region.nunique() != 1 or valid.region.nunique() != 1:
        raise ValueError("EMPTY_OR_MIXED_REGION")
    if set(train.region) != {"KR"} or set(valid.region) != {"KR"}:
        raise ValueError("REGION_MISMATCH")
    if pd.to_datetime(train.outcomeEndDate).max() >= pd.to_datetime(valid.date).min():
        raise ValueError("LABEL_NOT_MATURE_BEFORE_VALIDATION")
    weights = V1.date_weights(train.date)
    transformer = V1.TrainTransformer(list(names), tuple(spec["transforms"]["signedLog1p"])).fit(train, weights)
    x, v = transformer.transform(train), transformer.transform(valid)
    logistic, ridge = V1.estimator_pair("LINEAR", spec)
    _, hgb = V1.estimator_pair("SHALLOW_CHALLENGER", spec)
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        if kind == "logistic":
            logistic.fit(x, train.beatBenchmark.to_numpy(int), sample_weight=weights)
            out = logistic.predict_proba(v)[:, 1]
        else:
            model = {"ridge": ridge, "hgb": hgb}[kind]
            model.fit(x, train.forwardRelativeReturn.to_numpy(float), sample_weight=weights)
            out = model.predict(v)
    if not np.isfinite(out).all():
        raise FloatingPointError("MODEL_UNSTABLE_NONFINITE")
    return out, list(transformer.omitted)


def fitted_value_interval(train, valid, names, spec):
    """DESCRIPTIVE: training-only moving-block refits of the RIDGE head (v1/v2 statistic, same seed,
    blocks and quantiles). The probability refit of `M.prediction_uncertainty` consumes no random
    numbers, so the Ridge draws are identical; only the unused Logistic refit is skipped."""
    cfg = spec["uncertainty"]
    train = M.as_v1_target(train).reset_index(drop=True)
    dates = sorted(train.date.unique())
    if len(dates) < cfg["minimumTrainingBlocks"] * cfg["blockDates"]:
        return {"status": "DATA_INSUFFICIENT_UNCERTAINTY"}
    positions = train.groupby("date").indices
    by_date = [np.asarray(positions[d]) for d in dates]
    rng = np.random.default_rng(cfg["seed"])
    logs = tuple(spec["transforms"]["signedLog1p"])
    draws = []
    for _ in range(cfg["replicates"]):
        picked = V1.block_sample_indices(len(dates), cfg["blockDates"], rng)
        parts = [by_date[i] for i in picked]
        boot = train.iloc[np.concatenate(parts)].copy()
        boot["bootstrapDate"] = np.repeat(np.arange(len(parts)), [len(p) for p in parts])
        weights = V1.date_weights(boot.bootstrapDate)
        transformer = V1.TrainTransformer(list(names), logs).fit(boot, weights)
        _, ridge = V1.estimator_pair("LINEAR", spec)
        with threadpool_limits(limits=1), warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            ridge.fit(transformer.transform(boot), boot.forwardRelativeReturn.to_numpy(float), sample_weight=weights)
            draws.append(ridge.predict(transformer.transform(valid)))
    tail = cfg["lowerQuantile"]
    lower, upper = np.quantile(draws, tail, axis=0), np.quantile(draws, 1 - tail, axis=0)
    return {"status": "MEASURED", "meanWidth": float(np.mean(upper - lower))}


def rung_names(runtime_spec, horizon):
    """B4 = the full frozen registry of the cell; B3 = its non-accounting members; B2 = relative126."""
    full = runtime_spec["allowedFeatures"]["KR"][str(horizon)]
    non_accounting = [n for n in full if n not in ACCOUNTING_FIELDS]
    return {"B2": ["relative126"], "B3": non_accounting, "B4": list(full),
            "b3Applicable": non_accounting != list(full)}


# --------------------------------------------------------------------------- #
# Walk-forward ladder for one horizon cell.
# --------------------------------------------------------------------------- #
def run_cell(modelling, schedule, horizon, runtime_spec, counters, start_year):
    """Expanding annual folds anchored on the schedule (`V1.folds`); B0-B5 on identical rows.

    Only matured, eligible labels enter training and only labels whose exit is strictly before the
    fold cutoff (exact maturity purge); transforms are fitted on the training frame alone with equal
    influence per signal date. A fold before `start_year` (the coverage start rule) is not an
    evaluation fold. From the first READY fold at or after it, every scheduled fold must be READY.
    """
    names = rung_names(runtime_spec, horizon)
    frames, fold_records, descriptive_failures, history = [], [], [], []
    started = False
    for fold in V1.folds(M.as_v1_target(modelling), schedule, runtime_spec):
        record = {k: v for k, v in fold.items() if k not in ("train", "validation")}
        eligible_fold = fold["year"] >= start_year
        started = started or (eligible_fold and fold["status"] == "READY")
        fold_records.append({**record, "horizon": horizon, "evaluation": bool(started and eligible_fold)})
        if not (started and eligible_fold) or fold["status"] != "READY":
            continue
        train, valid = fold["train"], fold["validation"].copy()
        out = valid.copy()
        counters.bump("fitCalls")
        weights = V1.date_weights(train.date)
        out["pB0"] = float(np.average(train.forwardRelativeReturn, weights=weights))
        out["pB1"] = 0.0
        out["baseRate"] = float(np.average(train.beatBenchmark, weights=weights))
        try:
            for rung in (("B2", "ridge"), ("B4", "ridge")) + ((("B3", "ridge"),) if names["b3Applicable"] else ()):
                out["p" + rung[0]], omitted = _fit_predict(rung[1], train, valid, names[rung[0]], runtime_spec)
                if rung[0] == "B4":
                    fold_records[-1]["omittedFeatures"] = omitted
        except (ConvergenceWarning, FloatingPointError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith("DATA_INSUFFICIENT"):
                fold_records[-1]["status"] = str(exc)
                continue
            raise ModelFitFailure(f"PRIMARY_MODEL_FAILED year={fold['year']} {type(exc).__name__}: {exc}") from exc
        if not names["b3Applicable"]:
            out["pB3"] = np.nan
        for column, rung, kind in (("pB5", "B4", "hgb"), ("prob", "B4", "logistic")):
            try:
                out[column], _ = _fit_predict(kind, train, valid, names[rung], runtime_spec)
            except (ConvergenceWarning, FloatingPointError, ValueError) as exc:
                out[column] = np.nan
                descriptive_failures.append({"horizon": horizon, "year": fold["year"], "head": column,
                                             "reason": type(exc).__name__ + ": " + str(exc)[:120]})
        counters.bump("predictCalls")
        residual = V1.matured_residual_scale(pd.concat(history, ignore_index=True) if history else pd.DataFrame(),
                                             fold["cutoff"])
        try:
            uncertainty = fitted_value_interval(train, valid, names["B4"], runtime_spec)
        except (ConvergenceWarning, FloatingPointError, ValueError) as exc:
            uncertainty = {"status": "UNSTABLE_" + type(exc).__name__}
        fold_records[-1].update(predictiveResidualRms=residual, fittedValueUncertainty=uncertainty)
        out["horizon"], out["trainingCutoff"], out["foldYear"] = horizon, fold["cutoff"], fold["year"]
        history.append(out.assign(expectedRelativeReturn=out.pB4))
        frames.append(out)
    gap = [f for f in fold_records if f["evaluation"] and f["status"] != "READY"]
    return {"predictions": pd.concat(frames, ignore_index=True) if frames else None, "folds": fold_records,
            "descriptiveFailures": descriptive_failures, "unreadyEvaluationFolds": gap,
            "started": started, "rungs": {k: v for k, v in names.items()}}


def evaluation_table(predictions, runtime_spec):
    """Rows every rung was scored on: matured, eligible, exit at or before the cutoff, all primary rungs finite,
    on dates with at least `minimumNamesPerDate` such names. Pending dates are removed by calendar alone."""
    if predictions is None or predictions.empty:
        return None
    cutoff = pd.Timestamp(runtime_spec["dataCutoff"])
    keep = (predictions.labelStatus.eq(MATURED) & (pd.to_datetime(predictions.outcomeEndDate) <= cutoff)
            & np.isfinite(predictions[["pB0", "pB1", "pB2", "pB4", "forwardRelativeReturn"]].to_numpy(float)).all(axis=1))
    rows = predictions.loc[keep].copy()
    counts = rows.groupby("date").size()
    rows = rows.loc[rows.date.isin(counts[counts >= runtime_spec["walkForward"]["minimumNamesPerDate"]].index)]
    cost_by_date = {d: D.dated_round_trip_cost("KR", d, runtime_spec) for d in rows.date.unique()}
    rows["roundTripCost"] = rows.date.map(cost_by_date)
    return rows.sort_values(["date", "ticker"], kind="stable").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Evidence for one cell -> claim.
# --------------------------------------------------------------------------- #
def evaluate_cell(table, cell, horizon, runtime_spec, prices, days, calibration, counters):
    """Registered intervals, conjunct states, claim status and (conditionally) the economic tier."""
    floor = runtime_spec["minimumConfirmatoryDepth"][str(horizon)]
    base = {"horizon": horizon, "claim": "CREDIBLE_INCREMENTAL_EXPECTED_RETURN",
            "signalWeeksRequired": floor, "rungs": cell["rungs"], "folds": cell["folds"],
            "descriptiveModelFailures": cell["descriptiveFailures"]}
    reason = None
    if not cell["started"]:
        reason = "NO_READY_EVALUATION_FOLD"
    elif cell["unreadyEvaluationFolds"]:
        reason = "A_LATER_SCHEDULED_FOLD_IS_NOT_READY"
    elif table is None or table.empty:
        reason = "NO_EVALUABLE_SIGNAL_DATE"
    if reason is None and table.date.nunique() < floor:
        reason = "SIGNAL_WEEKS_BELOW_CONFIRMATORY_FLOOR"
    dates = [] if table is None else sorted(table.date.unique())
    base["signalWeeks"] = len(dates)
    if reason:
        return {**base, "status": EV.claim_status([], data_insufficient_reason=reason), "reason": reason,
                "conjuncts": {}, "economicTier": EV.economic_tier(EV.DATA_INSUFFICIENT, selected_minus_universe=None,
                                                                    selected_mean=None, selected_dates=0,
                                                                    half_estimates=[None, None])}, None
    counters.bump("evaluateCalls")
    closes = {t: EV.aligned_close(prices[t], days) for t in table.ticker.unique()}
    bench = EV.aligned_close(prices[KR_BENCHMARK], days)
    has_b3 = cell["rungs"]["b3Applicable"]
    has_b5 = bool(np.isfinite(table.pB5.to_numpy(float)).all())
    evidence = EV.horizon_evidence(table, days=days, closes_by_ticker=closes, bench_close=bench, horizon=horizon,
                                   critical=calibration["critical"], tolerance=calibration["tolerance"],
                                   has_b3=has_b3, has_b5=has_b5)
    intervals = evidence["intervals"]
    conjuncts = {name: {"interval": intervals[name], "state": EV.interval_state(intervals[name])}
                 for name in EV.CONJUNCTS}
    status = EV.claim_status([c["state"] for c in conjuncts.values()])
    selected = intervals["selectedMean"]
    tier = EV.economic_tier(
        status, selected_minus_universe=intervals["selectedMinusUniverse"], selected_mean=selected,
        selected_dates=selected.get("definedSignalDates", 0),
        half_estimates=EV.half_estimates(evidence["perDate"]["selectedMean"], dates))
    counts = pd.DataFrame(evidence["selection"])
    descriptive = {
        **EV.descriptive_summary(table, calibration["critical"]),
        "logisticHead": EV.logistic_descriptives(table, calibration["critical"]),
        "annualEstimates": EV.annual_estimates(evidence["perDate"], list(EV.CONJUNCTS)),
        "contrasts": {name: intervals[name] for name in intervals
                      if name.startswith("pairedMseImprovement") and name not in EV.CONJUNCTS},
        "costX2SelectedMean": intervals.get("selectedMeanCostX2"),
        "selectionByDate": [{"date": r.date, "names": int(r.names), "selectedCount": int(r.selectedCount)}
                            for r in counts.itertuples()],
        "selection": {"datesWithEmptySelectedSet": int((counts.selectedCount == 0).sum()),
                      "fractionEmpty": float((counts.selectedCount == 0).mean()),
                      "meanSelectedCount": float(counts.selectedCount.mean())},
    }
    if not has_b3:
        descriptive["contrasts"]["pairedMseImprovement_B4_vs_B3"] = {"status": "NOT_APPLICABLE",
                                                                    "reason": "B3 and B4 are one fitted predictor at H21"}
    return {**base, "status": status, "reason": None, "conjuncts": conjuncts, "economicTier": tier,
            "intervals": {n: v for n, v in intervals.items() if n not in EV.CONJUNCTS},
            "descriptive": descriptive,
            "namesPerDate": {"min": int(counts.names.min()), "median": float(counts.names.median()),
                             "max": int(counts.names.max())}}, evidence


# --------------------------------------------------------------------------- #
# Result artifact.
# --------------------------------------------------------------------------- #
def jsonable(value):
    """Plain JSON: numpy scalars and arrays to Python, non-finite floats to None, keys to strings."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    return value


ATTEMPT_KEYS = ("attempt",)


def substantive_digest(result: dict) -> str:
    """Digest of everything except the attempt identity and the digest fields themselves."""
    body = {k: v for k, v in result.items() if k not in ("resultDigests",)}
    body["provenance"] = {k: v for k, v in result["provenance"].items() if k not in ATTEMPT_KEYS}
    return digest(body)


def finalize(result: dict) -> bytes:
    result = jsonable(result)
    result["resultDigests"] = {"substantiveResultSha256": substantive_digest(result)}
    return canonical(result) + b"\n"


def code_identity(root, entry="scripts/execute_alpha_opportunity_model_v5.py") -> dict:
    """Harness file hashes (what an operator authorization pins) and the full import closure (audit)."""
    from .alpha_opportunity_v3_spec import import_closure
    root = Path(root)
    return {"harnessFiles": harness_file_hashes(root),
            "importClosure": {rel: file_hash(root / rel) for rel in sorted(import_closure([entry], root))}}


def harness_file_hashes(root) -> dict:
    """Cheap per-check identity of the reviewed harness bytes (no import-closure walk)."""
    return {rel: file_hash(Path(root) / rel) for rel in HARNESS_FILES}


def registered_claims(overall_cells: dict, *, status=None, reason=None) -> dict:
    return {h: {"status": status or cell["status"], "reason": reason or cell.get("reason")}
            for h, cell in overall_cells.items()}


def build_result(*, spec, spec_sha, mode, runtime_spec, counters, guard, phase, provenance, gates=None, cells=None,
                 stop=None, error=None, foundation=None, diagnostics=None, sample=None):
    horizons = [str(h) for h in runtime_spec["horizons"]]
    cells = dict(cells or {})
    if error is not None:
        claims = {h: {"status": EV.INFRASTRUCTURE_ERROR, "reason": error["code"]} for h in horizons}
    elif stop is not None:
        claims = {h: {"status": EV.DATA_INSUFFICIENT,
                      "reason": "PRE_LABEL_GATE_FAILED" if h in stop.detail["failingCells"]
                      else "RUN_STOPPED_BEFORE_LABELS_BY_ANOTHER_CELLS_GATE"} for h in horizons}
    elif mode == GATES_ONLY:
        claims = {h: {"status": EV.NOT_EVALUATED, "reason": "GATES_ONLY_NO_LABELS_BY_REQUEST"} for h in horizons}
    else:
        claims = {h: {"status": cells[h]["status"], "reason": cells[h].get("reason")} if h in cells
                  else {"status": EV.DATA_INSUFFICIENT, "reason": "CELL_NOT_EVALUATED"} for h in horizons}
    if mode == GATES_ONLY and error is None and stop is None:
        overall = EV.NOT_EVALUATED
    else:
        overall = EV.overall_status([c["status"] for c in claims.values()])
    values = counters.snapshot()
    labels_built = values["targetFromSessionsCalls"] > 0 or values["labelEligibilityCalls"] > 0
    substantive = (mode == FORMAL and overall in (EV.PASS, EV.FAIL, EV.INCONCLUSIVE, EV.DATA_INSUFFICIENT))
    return {
        "schemaVersion": 1, "harnessContract": CONTRACT, "studyId": STUDY, "specSha256": spec_sha,
        "evidenceClass": "HISTORICAL_OOS", "sampleStatus": spec["sampleStatus"], "promotionEligible": False,
        "executionMode": mode, "overallStatus": overall, "substantiveResult": bool(substantive),
        "closesPreregistration": bool(substantive),
        "overallMeaning": spec["claims"]["overall"]["PASS_means" if overall == EV.PASS else "FAIL_means"]
        if overall in (EV.PASS, EV.FAIL) else None,
        "claims": claims, "cells": cells, "phaseReached": phase,
        "ordering": {"counters": values, "labelsBuilt": labels_built, "stoppedBeforeLabels": not labels_built,
                     "note": "derived from call-site counters, never asserted independently"},
        "stop": None if stop is None else {"status": stop.status, "detail": stop.detail},
        "error": error, "preLabelGates": None if gates is None else gates.cells,
        "identity": {"frozen": guard.frozen, "frozenSha256": None if guard.frozen is None else guard.frozen_digest,
                     "checks": guard.checks,
                     "unchangedThroughout": bool(guard.frozen is not None
                                                 and not any(c.get("moved") for c in guard.checks))},
        "foundation": foundation, "sample": sample, "missingnessIntegrityDiagnostics": diagnostics,
        "noPortfolioFields": list(spec["outputSchema"]["noPortfolioFields"]),
        "blockedRegions": {"US": spec["blockedRegions"]["US"]["status"]},
        "provenance": provenance,
    }


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def run_execution(*, spec, spec_sha, runtime_spec, prepare, guard, calibration, mode, provenance,
                  foundation=None, counters=None, sessions=None):
    """Pre-label gates, permit, labels, ladder, evidence, claims. Returns the result dict; never raises on
    a registered stop, and reports any other failure as INFRASTRUCTURE_ERROR with the counters it observed.

    `prepare()` builds the PIT feature frame (tradability attached) and loads prices; it runs inside the
    guarded block so that a failure while reading inputs is an INFRASTRUCTURE_ERROR artifact, not a crash.
    It must read no forward price: `Counters` and the ordering tests are what prove it did not.
    """
    counters = counters or Counters()
    phase = "IDENTITY_FROZEN"
    gates, cells, diagnostics, sample = None, {}, None, None

    def result(**extra):
        return build_result(spec=spec, spec_sha=spec_sha, mode=mode, runtime_spec=runtime_spec, counters=counters,
                            guard=guard, phase=phase, provenance=provenance, gates=gates, cells=cells,
                            foundation=foundation, diagnostics=diagnostics, sample=sample, **extra)

    try:
        days = RC.sessions("2012-01-01", "2027-12-31", "KR") if sessions is None else pd.DatetimeIndex(sessions)
        phase = "PRE_LABEL_INPUTS"
        frame, prices, completeness_map, terminated_codes = prepare()
        phase = "PRE_LABEL_GATES"
        frame = canonical_order(frame)
        gates = pre_label_gates(frame, runtime_spec, days)
        if mode == GATES_ONLY:
            guard.assert_unchanged("END_OF_GATES_ONLY_RUN")
            return result()
        permit = issue_label_permit(gates, guard, counters)
        phase = "LABELS"
        regional = frame.loc[frame.tradable].copy()
        cost_by_date = {d: D.dated_round_trip_cost("KR", d, runtime_spec) for d in regional.date.unique()}
        regional["roundTripCost"] = regional.date.map(cost_by_date)
        schedule = sorted(regional.date.unique())
        annotated_frames, evaluation = [], {}
        for horizon in runtime_spec["horizons"]:
            phase = f"LABELS_H{horizon}"
            annotated, modelling = build_labels(permit, regional, prices, days, runtime_spec, completeness_map,
                                                counters, horizon)
            annotated_frames.append(annotated)
            phase = f"WALK_FORWARD_H{horizon}"
            start = gates.cells[str(horizon)]["startYear"]
            cell = run_cell(modelling, schedule, horizon, runtime_spec, counters, start)
            phase = f"EVALUATION_H{horizon}"
            table = evaluation_table(cell["predictions"], runtime_spec)
            cells[str(horizon)], evidence = evaluate_cell(table, cell, horizon, runtime_spec, prices, days,
                                                          calibration, counters)
            evaluation[str(horizon)] = {"signalWeeks": cells[str(horizon)]["signalWeeks"],
                                        "evaluationRows": 0 if table is None else int(len(table))}
        phase = "DIAGNOSTICS"
        allrows = pd.concat(annotated_frames, ignore_index=True)
        diagnostics = X4.missingness_integrity_report(allrows, regional, prices, terminated_codes)
        sample = {"tradableNameDates": int(len(regional)), "scheduledSignalDates": len(schedule),
                  "evaluation": evaluation}
        guard.assert_unchanged("END_OF_RUN")
        phase = "COMPLETE"
        return result()
    except PreLabelStop as stop:
        return result(stop=stop)
    except InputIdentityChanged as exc:
        return result(error={"code": "INPUT_IDENTITY_CHANGED", "message": str(exc)[:300]})
    except Exception as exc:  # noqa: BLE001 - any other failure is an execution failure, reported as such
        return result(error={"code": type(exc).__name__, "message": str(exc)[:300]})


def completeness_map_from(snapshot: dict) -> dict:
    return X4.completeness_by_code(snapshot)


def calibration_params(root) -> dict:
    """The sealed U1 critical value and near-zero tolerance, read from the pinned calibration spec."""
    construction = read_json(Path(root) / S5.CALIBRATION_V5)["intervalConstruction"]
    return {"critical": float(construction["U1CriticalValue"]),
            "tolerance": float(construction["nearZeroNormalizerRelativeTolerance"])}
