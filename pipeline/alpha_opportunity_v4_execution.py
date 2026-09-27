"""KR-only execution harness for the SEALED `alpha-opportunity-model-v4`
preregistration. Research only; no production import.

This module is NOT part of the preregistration's own sealed dependency
closure (`research_specs/alpha-opportunity-model-v4.json`'s
`dependencyClosure`/`dependencyHashes`) and never touches it: the
preregistration was reviewed and merged before this harness existed, its own
entry points (`scripts/run_alpha_opportunity_model_v4.py`,
`scripts/audit_alpha_opportunity_v4_kr_eligibility.py`,
`pipeline/alpha_opportunity_v4_eligibility.py`) stay byte-identical, and this
module only ever IMPORTS `pipeline.alpha_opportunity_v4_eligibility`'s already
-sealed functions rather than editing them. `pipeline.alpha_opportunity_v4_spec
.load_sealed` is called by the execution SCRIPT (`scripts/execute_alpha_
opportunity_model_v4.py`) before anything here runs, as a read-only proof that
the design this harness executes is still exactly what was reviewed.

Every function below is either outcome-free (feature/eligibility/coverage
plumbing, computed the same way whether or not a label will ever be built) or
clearly marked as the point past which a label exists. Nothing here changes a
horizon, a feature, a model family, a hyperparameter, a cost, a transform, the
walk-forward schedule, the alpha decision rule, or an evaluation gate: every
one of those is read from the ALREADY-SEALED v2/v3/v4 spec JSON files and from
`pipeline.alpha_opportunity_v2_evaluation` / `alpha_opportunity_v2_model` /
`alpha_opportunity_v2_decision` / `alpha_opportunity_v3_decision`, called
unmodified.

WHY THE RUNTIME SPEC IS ASSEMBLED, NOT RE-DECLARED. v4's own JSON nests the
KR-only, already-corrected values it explicitly redeclares (`carriedFromV3`:
models, transforms, uncertainty, walkForward, transactionCosts,
tradabilityGuard, inference, targets, allowedFeatures) but never repeats the
runtime constants that do not change at all when a study narrows from four
region x horizon claims to two (`evidenceGates`, `costStress`, the
`WORST_PLAUSIBLE` survivorship-stress thresholds inside `survivorship`, and
`coverageGate`). Those live only in `research_specs/alpha-opportunity-model-v2
.json`, which is ALREADY one of v4's own hash-pinned `sealedDataInputs`.
`build_runtime_spec` reads them from that sealed file and overlays v4's own
explicit values on top -- assembly of two already-sealed documents, never an
invention of a new number.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from . import alpha_opportunity_v4_eligibility as ELIG
from . import historical_store as HS
from .alpha_opportunity_features import accounting_at, price_attention_at
from .alpha_opportunity_spec import digest
from .regional_alpha_features import BENCHMARKS, MembershipSnapshots, weekly_grid

# V2: pre-label gates now run before any label exists (the V1 harness built
# labels and called label_eligibility first -- see the execution report's
# correction section); raw inputs are verified against the sealed identity.
CONTRACT = "ALPHA_OPPORTUNITY_V4_KR_EXECUTION_HARNESS_V2"
KR_BENCHMARK = BENCHMARKS["KR"]


# --------------------------------------------------------------------------- #
# Inputs: KR-only membership, raw fundamentals and the KR feature matrix.
# Every function below mirrors the region-scoped slice of the already-sealed
# `regional_alpha_features`/`alpha_opportunity_features` logic; none of the
# per-name feature or accounting computations are reimplemented -- only the
# KR-only orchestration loop is new.
# --------------------------------------------------------------------------- #
def load_kr_memberships(ledger) -> MembershipSnapshots:
    """KR top-120-by-market-cap snapshots only -- the exact slice of
    `regional_alpha_features.load_memberships` that does not require a US
    membership file at all."""
    grouped: dict[str, list[dict]] = {}
    for path in sorted((Path(ledger) / "universe/kr").glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            grouped.setdefault(row["date"], []).append(row)
    snapshots = []
    for date, rows in sorted(grouped.items()):
        ranked = sorted((r for r in rows if r.get("rank") is not None),
                        key=lambda r: (r["rank"], r["ticker"]))[:120]
        snapshots.append({"date": date, "members": sorted(r["ticker"] for r in ranked),
                          "marketCaps": {r["ticker"]: r.get("marketCap") for r in ranked}})
    if not snapshots:
        raise ValueError("DATA_LINEAGE_UNRESOLVED: dated KR universe snapshots required")
    return MembershipSnapshots(snapshots)


def load_kr_raw(ledger):
    """KR DART raw fundamental shards and share-count records only."""
    raw: dict[str, list[dict]] = {}
    for path in sorted((Path(ledger) / "fundamentals/kr").glob("dart-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            raw.setdefault(row["ticker"], []).append(row)
    shares: dict[str, list[dict]] = {}
    shares_path = Path(ledger) / "fundamentals/kr/shares.jsonl.gz"
    if shares_path.exists():
        for row in HS.read_jsonl(shares_path):
            shares.setdefault(row["ticker"], []).append(row)
    return raw, shares


def build_kr_matrix(prices, kr_memberships, raw, shares, *, start, through):
    """KR-only feature frame. Calls the exact same per-name feature functions
    `alpha_opportunity_features.build_matrix` calls for KR (`price_attention_at`,
    `accounting_at`), scoped to one region so no US membership is required."""
    bench = prices.get(KR_BENCHMARK)
    if bench is None:
        raise ValueError("benchmark unavailable: KR")
    rows = []
    for date in weekly_grid(start, through, "KR"):
        snapshot = kr_memberships.on(date)
        if snapshot is None:
            raise ValueError("PIT_MEMBERSHIP_MISSING: KR/" + date)
        for ticker in snapshot["members"]:
            fields = price_attention_at(prices.get(ticker), bench, date, "KR")
            accounting, provenance = accounting_at(raw.get(ticker, []), date, "KR", shares.get(ticker, []))
            rows.append({"date": date, "region": "KR", "ticker": ticker, "benchmark": KR_BENCHMARK,
                        "membershipDate": snapshot["date"], "accountingProvenance": provenance,
                        **fields, **accounting})
    frame = pd.DataFrame(rows)
    if frame.duplicated(["date", "region", "ticker"]).any():
        raise ValueError("DUPLICATE_NAME_DATE")
    return frame.sort_values(["date", "ticker"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Raw input identity. The replay-v16 manifest content-addresses the price,
# benchmark and corporate-event objects (`InputStore._read` re-hashes every
# object against its manifest ref), but it does NOT cover the raw
# `ledger/fundamentals/kr` and `ledger/universe/kr` shards this harness reads
# directly -- those live beside the replay store, not inside it. Their sealed
# identity is the git-blob list `alpha-opportunity-model-v3`'s own
# `futureExecutionInputs` recorded at signal-history commit 4ea107ed (the same
# list, file for file, as v2's sealed `inputFiles`); v3's JSON is one of v4's
# own hash-pinned `sealedDataInputs`, so reading it here invents nothing.
# Collector bookkeeping v3 names as unread (`fundamentals/kr/manifest.json`,
# `absent.json`, `krx-universe-done.json`) is outside the read patterns and so
# outside the identity, exactly as v3's `excludedAdjacent` states.
# --------------------------------------------------------------------------- #
REPLAY_MANIFEST = "ledger/historical/replay-v16/inputs.json"
KR_READ_PATTERNS = (("ledger/fundamentals/kr", "dart-*.jsonl.gz"),
                    ("ledger/fundamentals/kr", "shares.jsonl.gz"),
                    ("ledger/universe/kr", "krx-universe-*.jsonl.gz"))


def _read_by_harness(rel: str) -> bool:
    return rel == REPLAY_MANIFEST or any(
        fnmatch.fnmatchcase(rel, f"{folder}/{pattern}") for folder, pattern in KR_READ_PATTERNS)


def sealed_input_identity(v3_spec: dict) -> dict:
    """The sealed identity of every raw file this harness reads."""
    future = v3_spec["futureExecutionInputs"]
    blobs = {rel: sha for rel, sha in future["gitBlobSha1"].items() if _read_by_harness(rel)}
    if REPLAY_MANIFEST not in blobs or not any("fundamentals/kr/dart-" in r for r in blobs):
        raise ValueError("SEALED_INPUT_IDENTITY_INCOMPLETE")
    return {"signalHistoryCommit": future["signalHistoryCommit"],
            "replayManifestSha256": future["replayManifestSha256"], "gitBlobSha1": blobs}


def git_blob_sha1(path) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def signal_history_commit(input_root) -> str | None:
    """The commit the input checkout is actually at, or None if it is not a
    git checkout (a synthetic fixture). Recorded, never trusted alone: the
    blob identity below is what proves the bytes."""
    try:
        out = subprocess.run(["git", "-C", str(input_root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def verify_input_identity(sealed: dict, input_root, *, expected_signal_history_sha=None) -> dict:
    """Byte-level proof the checkout is the sealed snapshot. Reads no row.

    Raises `INPUT_SNAPSHOT_CHANGED` on any sealed file missing or differing,
    `UNSEALED_RAW_SHARD` on any file the harness WOULD read that the sealed
    list does not name, `REPLAY_MANIFEST_CHANGED` on a manifest digest
    mismatch, and `SIGNAL_HISTORY_COMMIT_MISMATCH` when an expected commit
    (the freeze job's) is given and the checkout is elsewhere.
    """
    root = Path(input_root)
    commit = signal_history_commit(root)
    if expected_signal_history_sha is not None and commit != expected_signal_history_sha:
        raise ValueError(f"SIGNAL_HISTORY_COMMIT_MISMATCH: expected {expected_signal_history_sha}, got {commit}")
    for rel, sha in sorted(sealed["gitBlobSha1"].items()):
        path = root / rel
        if not path.is_file() or git_blob_sha1(path) != sha:
            raise ValueError("INPUT_SNAPSHOT_CHANGED: " + rel)
    for folder, pattern in KR_READ_PATTERNS:
        for path in sorted((root / folder).glob(pattern)):
            rel = str(path.relative_to(root))
            if rel not in sealed["gitBlobSha1"]:
                raise ValueError("UNSEALED_RAW_SHARD: " + rel)
    manifest = json.loads((root / REPLAY_MANIFEST).read_text())
    got = digest({k: v for k, v in manifest.items() if k != "sha256"})
    if not got == manifest.get("sha256") == sealed["replayManifestSha256"]:
        raise ValueError("REPLAY_MANIFEST_CHANGED: " + got)
    identity = {"sealedSignalHistoryCommit": sealed["signalHistoryCommit"],
                "signalHistoryCommit": commit, "replayManifestSha256": got,
                "gitBlobSha1": dict(sorted(sealed["gitBlobSha1"].items()))}
    identity["inputIdentitySha256"] = digest(identity["gitBlobSha1"] | {
        "__replayManifestSha256__": got})
    return identity


# --------------------------------------------------------------------------- #
# Foundation / execution-snapshot versioning -- thin call-throughs to the
# ALREADY-SEALED `alpha_opportunity_v4_eligibility` functions. Nothing here
# reimplements them.
# --------------------------------------------------------------------------- #
def completeness_by_code(reconstruction_snapshot: dict) -> dict:
    """{code: completeness row} read directly from the current KR
    terminal-action reconstruction snapshot's own `securities` list -- a data
    lookup of which securities this repository has audited, never a rule the
    eligibility function itself branches on (see `alpha_opportunity_v4_
    eligibility`'s module docstring)."""
    return {row["code"]: row["completeness"] for row in reconstruction_snapshot["securities"]}


def verify_and_freeze_foundation(*, cited_snapshot: dict, current_snapshot: dict) -> dict:
    """Proves the CURRENT foundation snapshot never regressed relative to the
    one cited at seal time (`assert_foundation_not_regressed`), then freezes
    the CURRENT snapshot for this run (`freeze_execution_snapshot`) -- both
    calls into the sealed module, unmodified. Must run exactly once, before
    the first label is constructed."""
    ELIG.assert_foundation_not_regressed(cited_snapshot=cited_snapshot, current_snapshot=current_snapshot)
    frozen_hash = ELIG.freeze_execution_snapshot(current_snapshot)
    return {"frozenExecutionSnapshotHash": frozen_hash,
            "foundationStatusAtExecution": current_snapshot.get("foundationStatus"),
            "citedFoundationStatusAtSeal": cited_snapshot.get("foundationStatus")}


def last_priced_session(frame) -> str | None:
    """Last date this ticker's own sealed panel carries a positive, finite
    Close -- the calendar fact `window_crosses_termination` is computed from.
    Reads no return; a Close level is not an outcome."""
    if frame is None or "Close" not in frame or not len(frame):
        return None
    close = pd.to_numeric(frame["Close"], errors="coerce")
    ok = close.notna() & (close > 0) & np.isfinite(close)
    if not ok.any():
        return None
    return str(frame.index[ok][-1].date())


def window_crosses_termination(exit_date: str, last_priced: str | None) -> bool:
    """Pure calendar fact: does this window's own scheduled exit session fall
    after the security's last priced session. `None` (never priced at all)
    counts as crossing -- there is no session for this window to NOT cross."""
    if last_priced is None:
        return True
    return pd.Timestamp(exit_date) > pd.Timestamp(last_priced)


def attach_eligibility(data: pd.DataFrame, prices: dict, completeness_map: dict) -> pd.DataFrame:
    """Attach `windowCrossesTermination`, `eligibilityStatus` and
    `eligibilityReasonCode` to every row of a labelled frame (post
    `alpha_opportunity_v2_evaluation.attach_labels`). Calls
    `alpha_opportunity_v4_eligibility.label_eligibility` once per observation
    with `total_return_series_available=False` -- this harness performs no
    total-return re-splicing engineering step, so every audited (completeness
    present) non-crossing observation is INELIGIBLE under today's evidence,
    exactly as the sealed spec's own `computedResultAsOfThisSeal` states.
    `successor_codes`/`priced_securities` are left at their empty defaults:
    building successor-price stitching is out of scope while every one of the
    22 audited securities reads `terminalActionChainResolved: BLOCKED` (0 of
    22), which makes the crossing-window branch's successor logic currently
    unreachable regardless.
    """
    last_priced = {t: last_priced_session(prices.get(t)) for t in data.ticker.unique()}
    crosses = [window_crosses_termination(exit_date, last_priced[t])
               for t, exit_date in zip(data.ticker, data.outcomeEndDate)]
    verdicts = [ELIG.label_eligibility(completeness=completeness_map.get(t),
                                       window_crosses_termination=c,
                                       total_return_series_available=False)
                for t, c in zip(data.ticker, crosses)]
    out = data.copy()
    out["windowCrossesTermination"] = crosses
    out["eligibilityStatus"] = [v["status"] for v in verdicts]
    out["eligibilityReasonCode"] = [v["reasonCode"] for v in verdicts]
    return out


# --------------------------------------------------------------------------- #
# Runtime spec assembly -- reads two already-sealed JSON documents; invents
# no number.
# --------------------------------------------------------------------------- #
def build_runtime_spec(v4_spec: dict, v2_spec: dict) -> dict:
    runtime = dict(v2_spec)
    runtime.update(v4_spec["carriedFromV3"])
    for key in ("horizons", "regions", "benchmarks", "dataCutoff", "studyId"):
        runtime[key] = v4_spec[key]
    runtime["modelIds"] = {"KR": f"{v4_spec['studyId']}@{v4_spec['immutableVersion']}"}
    return runtime


# --------------------------------------------------------------------------- #
# F -- missingness / survivorship integrity diagnostics. Every one of these
# is computed from the labelled-and-eligibility-annotated frame BEFORE
# filtering to what the model ever sees; none reads a realised outcome beyond
# whether a label matured, which reason it carries if it did not, and which
# security it is on -- no return magnitude enters any of them.
# --------------------------------------------------------------------------- #
def _year(dates) -> pd.Series:
    return pd.to_datetime(dates).dt.year.astype(str)


def unavailability_reason(row) -> str | None:
    """One reason code per row: None if usable (MATURED and ELIGIBLE), else
    the eligibility reason if MATURED-but-INELIGIBLE, else the labelStatus
    itself (PENDING / MISSING_FORWARD_PRICE_OR_DELISTING)."""
    if row["labelStatus"] == "MATURED" and row["eligibilityStatus"] == ELIG.ELIGIBLE:
        return None
    if row["labelStatus"] == "MATURED":
        return row["eligibilityReasonCode"]
    return row["labelStatus"]


def pit_universe_observations_by_year(frame: pd.DataFrame) -> dict:
    return {y: int(n) for y, n in _year(frame.date).value_counts().sort_index().items()}


def eligible_labels_by_year_and_horizon(annotated: pd.DataFrame) -> dict:
    usable = annotated.loc[annotated.labelStatus.eq("MATURED") & annotated.eligibilityStatus.eq(ELIG.ELIGIBLE)]
    out: dict[str, dict] = {}
    for (year, horizon), g in usable.assign(year=_year(usable.date)).groupby(["year", "horizon"]):
        out.setdefault(year, {})[str(int(horizon))] = int(len(g))
    return out


def unavailable_labels_by_reason_code(annotated: pd.DataFrame) -> dict:
    reasons = annotated.apply(unavailability_reason, axis=1)
    counts = reasons.dropna().value_counts()
    return {str(k): int(v) for k, v in counts.items()}


def terminated_vs_continuing_label_availability(annotated: pd.DataFrame, terminated_codes) -> dict:
    terminated = frozenset(terminated_codes)
    is_term = annotated.ticker.isin(terminated)

    def rate(mask):
        sub = annotated.loc[mask]
        if not len(sub):
            return {"observations": 0, "eligibleLabels": 0, "eligibleLabelRatePct": None}
        eligible = int((sub.labelStatus.eq("MATURED") & sub.eligibilityStatus.eq(ELIG.ELIGIBLE)).sum())
        return {"observations": int(len(sub)), "eligibleLabels": eligible,
                "eligibleLabelRatePct": round(100.0 * eligible / len(sub), 4)}
    return {"terminatedSecurities": rate(is_term), "continuingSecurities": rate(~is_term)}


def member_dates_removed_pct_by_reason_and_year(annotated: pd.DataFrame) -> dict:
    reasons = annotated.assign(reason=annotated.apply(unavailability_reason, axis=1), year=_year(annotated.date))
    out: dict[str, dict] = {}
    for year, g in reasons.groupby("year"):
        total = len(g)
        removed = g.reason.notna()
        by_reason = g.loc[removed].reason.value_counts()
        out[year] = {"totalObservations": int(total),
                     "removedPct": round(100.0 * removed.mean(), 4),
                     "byReasonPct": {str(k): round(100.0 * v / total, 4) for k, v in by_reason.items()}}
    return out


def temporal_concentration_of_missingness(annotated: pd.DataFrame) -> dict:
    reasons = annotated.assign(reason=annotated.apply(unavailability_reason, axis=1), year=_year(annotated.date))
    missing = reasons.loc[reasons.reason.notna()]
    if not len(missing):
        return {"totalUnavailable": 0, "byYearPct": {}, "maxYearSharePct": None, "maxYear": None}
    by_year = missing.year.value_counts()
    shares = (100.0 * by_year / len(missing)).round(4)
    return {"totalUnavailable": int(len(missing)), "byYearPct": {str(k): float(v) for k, v in shares.items()},
            "maxYearSharePct": float(shares.max()), "maxYear": str(shares.idxmax())}


def security_concentration_of_missingness(annotated: pd.DataFrame, top_k: int = 10) -> dict:
    reasons = annotated.assign(reason=annotated.apply(unavailability_reason, axis=1))
    missing = reasons.loc[reasons.reason.notna()]
    if not len(missing):
        return {"totalUnavailable": 0, "topSecurities": [], "topKSharePct": None}
    by_ticker = missing.ticker.value_counts()
    top = by_ticker.head(top_k)
    return {"totalUnavailable": int(len(missing)),
            "topSecurities": [{"ticker": t, "count": int(c)} for t, c in top.items()],
            "topKSharePct": round(100.0 * top.sum() / len(missing), 4)}


def exclusions_cluster_around_terminal_events_check(annotated: pd.DataFrame, terminated_codes) -> dict:
    """Whether the eligibility policy's own exclusions concentrate on the 22
    audited terminated names, contrasted with those names' share of the
    labelled universe overall -- the check the spec's `knownConsequence`
    field requires before any headline may be read as unconditional."""
    terminated = frozenset(terminated_codes)
    ineligible = annotated.loc[annotated.labelStatus.eq("MATURED") & ~annotated.eligibilityStatus.eq(ELIG.ELIGIBLE)]
    universe_terminated_share = (100.0 * annotated.ticker.isin(terminated).mean()
                                 if len(annotated) else None)
    if not len(ineligible):
        return {"ineligibleObservations": 0, "ineligibleOnTerminatedNamesPct": None,
                "universeTerminatedNameSharePct": universe_terminated_share}
    on_terminated = float(100.0 * ineligible.ticker.isin(terminated).mean())
    return {"ineligibleObservations": int(len(ineligible)),
            "ineligibleOnTerminatedNamesPct": round(on_terminated, 4),
            "universeTerminatedNameSharePct": (round(universe_terminated_share, 4)
                                               if universe_terminated_share is not None else None)}


def benchmark_coverage_pct(prices: dict, dates) -> float:
    bench = prices.get(KR_BENCHMARK)
    if bench is None or "Close" not in bench:
        return 0.0
    idx = pd.to_datetime(pd.Series(sorted(set(dates))))
    close = pd.to_numeric(bench["Close"], errors="coerce")
    present = idx.isin(close.index[close.notna() & (close > 0)])
    return round(100.0 * present.mean(), 4) if len(idx) else None


def total_return_comparability_coverage_pct(annotated: pd.DataFrame) -> float:
    """Share of MATURED-eligible-candidate observations (this security's
    non-crossing window, if audited, or deferred-to-production if not) whose
    total-return basis is NOT flagged by an unresolved-basis reason code --
    i.e. 1 minus the ineligibility rate attributable specifically to
    `EXDATE_LINEAGE_UNRESOLVED` / `TOTAL_RETURN_SERIES_NOT_BUILT` / any
    termination-crossing reason, among rows that reached MATURED at all."""
    matured = annotated.loc[annotated.labelStatus.eq("MATURED")]
    if not len(matured):
        return None
    basis_reasons = frozenset({
        ELIG.EXDATE_LINEAGE_UNRESOLVED, ELIG.TOTAL_RETURN_SERIES_NOT_BUILT,
        ELIG.NO_COMPLETENESS_EVIDENCE, ELIG.TERMINATION_TYPE_UNRESOLVED,
        ELIG.TERMINAL_CONSIDERATION_UNRESOLVED, ELIG.SUCCESSOR_IDENTITY_UNRESOLVED,
        ELIG.TERMINAL_ACTION_CHAIN_UNRESOLVED, ELIG.SUCCESSOR_HAS_NO_PRICE_PANEL,
    })
    flagged = matured.eligibilityReasonCode.isin(basis_reasons)
    return round(100.0 * (1 - flagged.mean()), 4)


def missingness_integrity_report(annotated: pd.DataFrame, universe_frame: pd.DataFrame,
                                 prices: dict, terminated_codes) -> dict:
    """All ten `requiredDiagnostics` named in the sealed spec's
    `evaluationPreregistration.F_missingnessIntegrity`, in the order listed
    there."""
    return {
        "pitUniverseObservationsByYear": pit_universe_observations_by_year(universe_frame),
        "eligibleLabelsByYearAndHorizon": eligible_labels_by_year_and_horizon(annotated),
        "unavailableLabelsByReasonCode": unavailable_labels_by_reason_code(annotated),
        "terminatedVsContinuingLabelAvailability":
            terminated_vs_continuing_label_availability(annotated, terminated_codes),
        "memberDatesRemovedPctByReasonAndYear": member_dates_removed_pct_by_reason_and_year(annotated),
        "temporalConcentrationOfMissingness": temporal_concentration_of_missingness(annotated),
        "securityConcentrationOfMissingness": security_concentration_of_missingness(annotated),
        "exclusionsClusterAroundTerminalEventsCheck":
            exclusions_cluster_around_terminal_events_check(annotated, terminated_codes),
        "benchmarkCoveragePct": benchmark_coverage_pct(prices, annotated.date.unique()),
        "totalReturnComparabilityCoveragePct": total_return_comparability_coverage_pct(annotated),
    }
