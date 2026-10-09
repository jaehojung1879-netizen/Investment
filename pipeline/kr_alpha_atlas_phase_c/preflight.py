"""Exact preserved snapshot and Phase B-compatible proxy view, WITHOUT labels."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import zipfile
from pathlib import Path

import pandas as pd

from pipeline import kr_alpha_atlas_inputs as AI
from pipeline import kr_alpha_atlas_matrix as MX
from pipeline import kr_alpha_atlas_readiness as RD
from pipeline import kr_model_raw_snapshot as RAW
from .contract import digest, file_hash
from .labels import StudyData


def verify_runtime(spec):
    if platform.python_version() != spec["runtime"]["python"]:
        raise ValueError("PINNED_PYTHON_RUNTIME_REQUIRED")
    planned = {**spec["runtime"]["packages"], **spec["runtime"]["numericalExtras"]}
    versions = {p: importlib.metadata.version(p) for p in planned}
    if versions != planned:
        raise ValueError("PINNED_DEPENDENCY_VERSION_REQUIRED")
    if any(os.environ.get(k) != v for k, v in spec["runtime"]["environment"].items()):
        raise ValueError("SINGLE_THREAD_ENVIRONMENT_REQUIRED")
    return {
        "python": platform.python_version(),
        "packages": versions,
        "threadEnvironment": spec["runtime"]["environment"],
        "platform": platform.platform(),
        "processor": platform.processor(),
    }


def verify_git_inputs(root, spec):
    """Opaque Git object and schema metadata checks: no historical price decoding."""
    pin = spec["phaseBIdentity"]["inputs"]
    commit = pin["sourceCommit"]
    checks = {}
    paths = {**pin["barLedgerBlobSha1"], **pin["universeBlobSha1"], AI.SHARES_PATH: pin["dartSharesBlobSha1"]}
    accounting = RAW.frozen_spec()["inputs"]["accounting"]
    for name, sha in pin["accountingBlobSha1"].items():
        actual = (
            subprocess.check_output(
                ["git", "rev-parse", accounting["sourceCommit"] + ":ledger/fundamentals/kr-candidate-merged/" + name],
                cwd=root,
            )
            .decode()
            .strip()
        )
        if actual != sha:
            raise ValueError("ACCOUNTING_OBJECT_ID_CHANGED")
        checks[name] = actual
    for path, sha in paths.items():
        actual = subprocess.check_output(["git", "rev-parse", commit + ":" + path], cwd=root).decode().strip()
        if actual != sha:
            raise ValueError("PHASE_B_GIT_INPUT_CHANGED: " + path)
        checks[path] = actual
    raw = subprocess.check_output(["git", "show", commit + ":ledger/historical/replay-v16/inputs.json"], cwd=root)
    manifest = json.loads(raw)
    if manifest["sha256"] != pin["replayManifestSha256"] or not isinstance(manifest["components"], dict):
        raise ValueError("REPLAY_SCHEMA_OR_IDENTITY_CHANGED")
    if not any(k.startswith("price/") for k in manifest["components"]) or not any(
        k.startswith("benchmark/") for k in manifest["components"]
    ):
        raise ValueError("REPLAY_PRICE_BENCHMARK_SCHEMA_ABSENT")
    return {
        "gitObjects": checks,
        "replayManifestSha256": manifest["sha256"],
        "replaySchemaVerified": True,
        "realOutcomeReads": 0,
    }


def extract_exact(archive, root, wanted):
    archive = Path(archive)
    root = Path(root)
    if file_hash(archive) != wanted["archiveSha256"]:
        raise ValueError("ORIGINAL_ARCHIVE_CHECKSUM_REQUIRED")
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("FRESH_SNAPSHOT_DIRECTORY_REQUIRED")
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (root / info.filename).resolve()
            if not target.is_relative_to(root.resolve()) or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("UNSAFE_ARTIFACT_PATH")
            if not info.is_dir():
                RAW.immutable_bytes(target, z.read(info))
    identity = RAW.verify_snapshot(root)
    if identity["inputIdentity"]["sha256"] != wanted["inputIdentitySha256"]:
        raise ValueError("PINNED_ARTIFACT_IDENTITY_CHANGED")
    return identity


def prepare(root, spec, archive, work):
    """This is not invoked during PR authoring. Requires human-authorized preflight."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    opaque = verify_git_inputs(root, spec)
    preserved = None
    if archive is not None:
        preserved = extract_exact(archive, work / "preserved", spec["frozenArtifact"])
    # A separately identified proxy view uses the original Git-pinned sources.
    # Official market data stays preserved and verified, but is never selected as
    # feature trading value. This view is NOT relabelled as the original artifact.
    with RAW.outcome_firewall():
        inputs = AI.load_inputs(spec["phaseBIdentity"]["inputs"]["sourceCommit"], work / "proxy-view", root)
        if (
            inputs.identity != spec["phaseBIdentity"]["inputs"]
            or inputs.trading_value_basis != spec["tradingValueBasis"]
        ):
            raise ValueError("PROXY_VIEW_PHASE_B_IDENTITY_CHANGED")
        from pipeline.regional_alpha_features import weekly_grid

        matrix = MX.build_matrix(inputs, weekly_grid("2013-01-01", spec["developmentCutoff"], "KR"))
        if matrix.digest() != spec["phaseBIdentity"]["matrixDigest"]:
            raise ValueError("PHASE_B_MATRIX_DIGEST_CHANGED")
        pit = RD.pit_checks(matrix)
        reasons = RD.reason_checks(matrix)
        if not pit["pass"] or not reasons["pass"]:
            raise ValueError("PHASE_B_READINESS_AUDIT_FAILED")
    rows = matrix.rows.copy().reset_index(drop=True)
    caps = [
        (inputs.bars[r.ticker].quote(r.date) or {}).get("marketCap") if r.ticker in inputs.bars else None
        for r in rows.itertuples()
    ]
    rows["marketCap"] = caps
    days = inputs.calendar[inputs.calendar <= pd.Timestamp(spec["developmentCutoff"])]
    tickers = sorted(set(rows.ticker))
    prices = {t: inputs.prices[t].reindex(days) for t in tickers if t in inputs.prices}
    benchmark = inputs.prices[spec["benchmark"]].reindex(days)["Close"].to_numpy(float)
    foundation = json.loads((Path(root) / "docs/results/kr-terminal-action-reconstruction-v2.json").read_text())
    # Existing completeness policy structure is adapted explicitly, never guessed.
    completeness = {r["code"]: r["completeness"] for r in foundation["securities"]}
    terminal = {
        r["code"]: {"lastTradingDate": r["lastTradingDate"]}
        for r in foundation["securities"]
        if r.get("lastTradingDate")
    }
    data = StudyData(
        rows,
        matrix.values.reset_index(drop=True),
        matrix.available.reset_index(drop=True),
        days,
        {t: p["Close"].to_numpy(float) for t, p in prices.items()},
        {t: p["Volume"].to_numpy(float) for t, p in prices.items()},
        benchmark,
        inputs.identity["sha256"],
        completeness,
        terminal,
        matrix.reasons.reset_index(drop=True),
    )
    readiness = data.validate_features(spec)
    return data, {
        "originalArchiveSha256": spec["frozenArtifact"]["archiveSha256"] if preserved is not None else None,
        "formalInputBasis": "PHASE_B_GIT_PINNED_PROXY_SNAPSHOT",
        "originalArtifactUsed": False,
        "preservedSnapshotSha256": preserved["sha256"] if preserved is not None else None,
        "proxyViewIdentity": inputs.identity,
        "matrixDigest": spec["phaseBIdentity"]["matrixDigest"],
        "opaqueChecks": opaque,
        "readiness": readiness,
        "pit": pit,
        "reasonChecks": reasons,
        "derivedViewSha256": digest(inputs.identity),
        "outcomeReads": 0,
    }


def verify_source_schema_samples(root, spec):
    """Read only first-record keys/types, never prices/returns/targets into analysis."""
    import gzip
    import io
    from pipeline.kr_repaired_accounting_snapshot import git_blob_sha1

    pin = spec["phaseBIdentity"]["inputs"]
    accounting = RAW.frozen_spec()["inputs"]["accounting"]
    a = sorted(pin["accountingBlobSha1"])[0]
    u = sorted(pin["universeBlobSha1"])[0]
    b = sorted(pin["barLedgerBlobSha1"])[0]
    samples = [
        (
            accounting["sourceCommit"],
            "ledger/fundamentals/kr-candidate-merged/" + a,
            pin["accountingBlobSha1"][a],
            {"ticker", "fiscalYear", "reportCode", "availableFrom"},
        ),
        (pin["sourceCommit"], u, pin["universeBlobSha1"][u], {"ticker", "date", "rank", "marketCap"}),
        (pin["sourceCommit"], b, pin["barLedgerBlobSha1"][b], {"ticker", "date", "close", "volume", "listedShares"}),
        (
            pin["sourceCommit"],
            AI.SHARES_PATH,
            pin["dartSharesBlobSha1"],
            {"ticker", "fiscalYear", "reportCode", "sharesOutstanding"},
        ),
    ]
    checks = {}
    for commit, path, wanted, required in samples:
        raw = AI.git_blob(root, commit, path)
        if git_blob_sha1(raw) != wanted:
            raise ValueError("SCHEMA_SAMPLE_OBJECT_CHANGED")
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            first = stream.readline()
        record = json.loads(first)
        if not isinstance(record, dict) or not required <= set(record):
            raise ValueError("SELECTED_INPUT_SCHEMA_INCOMPATIBLE: " + path)
        checks[path] = {
            "gitBlobSha1": wanted,
            "fields": sorted(record),
            "requiredFields": sorted(required),
            "firstRecordSchema": "PASS",
            "valueTypes": {k: type(record[k]).__name__ for k in sorted(required)},
        }
    return {
        "selectedSourceSchemas": checks,
        "realLabels": 0,
        "realModelFits": 0,
        "realOutcomeReads": 0,
        "scope": "first-record schema only; no source values published or return paths analyzed",
    }
