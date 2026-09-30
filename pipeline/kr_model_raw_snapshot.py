"""Official raw acquisition and immutable pre-label inputs; frozen v1 untouched."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from unittest.mock import patch

import numpy as np
import pandas as pd

from . import kr_market_value as MV
from . import kr_model_portfolio_execution as X
from . import kr_value_quality_catalyst as F
from . import replay_calendar as RC
from . import replay_inputs as RI
from . import historical_store as HS
from .collector_outcomes import classify_refusal
from scripts.collect_krx_universe_snapshots import call, DEFAULT_BASE, ENDPOINT, Refused

canonical, digest, file_hash = RI.canonical, X.digest, X.file_hash

SPEC_SHA = "bda5ade60fab095d629dd542fac89c6fded3949c52b98e860e5f6ce677b1ad0c"
DIAGNOSTIC_SHA = "0fd3baf70d0fbe24e17a9ab2244ea6c3a4d8ac50c0af634a196fe3c3cb885f03"
SCHEMA = "KR_MODEL_RAW_SNAPSHOT_V1"
MANIFEST = "snapshot-manifest.json"


def frozen_spec(root=X.ROOT):
    spec, sha = X.load_spec(root)
    if sha != SPEC_SHA or spec["diagnostics"]["sha256"] != DIAGNOSTIC_SHA:
        raise ValueError("UNEXPECTED_FROZEN_SCIENTIFIC_SPEC_STOP")
    return spec


def immutable_bytes(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("IMMUTABLE_RAW_REWRITE_REFUSED: " + str(path))
        return
    temp = path.with_name(path.name + ".part")
    try:
        with temp.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def git_bytes(repo, commit, path):
    """Only caller-specified raw allowlist paths; no generic ledger discovery."""
    return subprocess.check_output(["git", "cat-file", "blob", commit + ":" + path], cwd=repo)


def materialize_universe(directory, spec, repo=X.ROOT):
    root = Path(directory)
    for rel, wanted in spec["inputs"]["universeBlobs"].items():
        raw = git_bytes(repo, spec["inputs"]["universeSourceCommit"], rel)
        if X.K.git_blob_sha1(raw) != wanted:
            raise ValueError("PINNED_UNIVERSE_BLOB_CHANGED: " + rel)
        immutable_bytes(root / rel, raw)
    members = set()
    for path in sorted((root / "ledger/universe/kr").glob("*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            if row["rank"] <= 120:
                members.add(row["ticker"])
    return sorted(members)


def materialize_inherited(directory, spec, repo=X.ROOT):
    root = Path(directory)
    pin = spec["inputs"]["accounting"]
    for name, wanted in pin["gitBlobSha1"].items():
        raw = git_bytes(repo, pin["sourceCommit"], "ledger/fundamentals/kr-candidate-merged/" + name)
        if X.K.git_blob_sha1(raw) != wanted:
            raise ValueError("PINNED_ACCOUNTING_BLOB_CHANGED: " + name)
        immutable_bytes(root / "accounting" / name, raw)
    rel = "ledger/historical/replay-v16/inputs.json"
    commit = spec["inputs"]["universeSourceCommit"]
    raw = git_bytes(repo, commit, rel)
    manifest = json.loads(raw)
    if manifest.get("sha256") != spec["inputs"]["replayManifestSha256"] or RI.digest({k:v for k,v in manifest.items() if k != "sha256"}) != manifest.get("sha256"):
        raise ValueError("PINNED_REPLAY_MANIFEST_CHANGED")
    immutable_bytes(root / rel, raw)
    refs = sorted({ref for name, values in manifest["components"].items() if name.startswith(("price/", "benchmark/")) for ref in values})
    def copy(ref):
        rel = "ledger/replay-inputs/objects/" + ref + ".json.gz"
        raw = git_bytes(repo, commit, rel)
        if hashlib.sha256(gzip.decompress(raw)).hexdigest() != ref:
            raise ValueError("PINNED_PRICE_OBJECT_CHANGED: " + ref)
        immutable_bytes(root / rel, raw)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(copy, refs))
    # Identity-only foundation bytes; no terminal/return interpretation here.
    rel = spec["inputs"]["terminalFoundationPath"]
    immutable_bytes(root / "foundation/terminal-evidence.json", (Path(repo) / rel).read_bytes())


def required_dates(spec):
    return [str(d.date()) for d in RC.sessions("2013-01-01", spec["developmentCutoff"], "KR")]


def normalize_official(payload, date):
    """Strict source envelope before the unchanged frozen normalization."""
    if not isinstance(payload, dict):
        raise ValueError("KRX_PAYLOAD_NOT_OBJECT")
    keys = [k for k in X.MV.KU.ROWS_KEYS if k in payload]
    if len(keys) != 1 or not isinstance(payload[keys[0]], list):
        raise ValueError("KRX_ROWS_SCHEMA_CHANGED")
    raw_rows = payload[keys[0]]
    seen, identifiers = set(), []
    explicit_dates = 0
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ValueError("KRX_NON_OBJECT_ROW")
        code = MV.KU._first(row, MV.KU.CODE_KEYS)
        if not code or not re.fullmatch(r"[0-9A-Z]{6}", code):
            raise ValueError("KRX_INVALID_RAW_IDENTIFIER")
        if code in seen:
            raise ValueError("DUPLICATE_KRX_SECURITY_DATE: " + code)
        seen.add(code)
        identifiers.append({k: row[k] for k in MV.KU.CODE_KEYS if k in row})
        stamp = MV.KU._first(row, MV.KU.DATE_KEYS)
        if stamp:
            if stamp != date.replace("-", ""):
                raise ValueError("KRX_ROW_DATE_IDENTITY_MISMATCH")
            explicit_dates += 1
    records = MV.parse_market_values(payload, date)
    if len(records) != len(raw_rows) or not records:
        raise ValueError("EXPECTED_KRX_SESSION_EMPTY_OR_ROW_LOSS")
    for row in records:
        MV.validate_record(row, date=date)
    discrepancies = [abs(r["close"] * r["listedShares"] / r["marketCap"] - 1) for r in records]
    return records, {"rawRows": len(raw_rows), "rawIdentifiers": sorted(identifiers, key=lambda r: canonical(r)),
                     "rowDateProvenance": "ALL_EXPLICIT" if explicit_dates == len(raw_rows) else "REQUEST_DATE_FALLBACK_AS_FROZEN_CONTRACT",
                     "duplicateHandling": "REJECT_ENTIRE_RESPONSE", "sourceValuesModified": False,
                     "capReconciliationTolerance": .01, "maximumCapDiscrepancy": max(discrepancies),
                     "nonzeroCapDiscrepancyRows": sum(d > 1e-12 for d in discrepancies)}


def cache_summary(directory):
    root = Path(directory)
    days, tickers, count = [], set(), 0
    hashes = {}
    for path in sorted(root.glob("????-??-??.json")):
        doc = json.loads(path.read_text())
        if doc != MV.day_document(path.stem, doc["records"]):
            raise ValueError("KRX_CACHE_HASH_OR_IDENTITY_CHANGED")
        days.append(path.stem); count += len(doc["records"])
        tickers.update(r["securityId"] for r in doc["records"])
        hashes[path.name] = file_hash(path)
    return {"rows": count, "dates": len(days), "securities": len(tickers), "start": min(days) if days else None,
            "end": max(days) if days else None, "fileHashes": hashes, "sha256": digest(hashes)}


def verify_cached_day(root, date, members):
    root = Path(root)
    raw = gzip.decompress((root / "sources/krx" / (date + ".json.gz")).read_bytes())
    provenance = json.loads((root / "sources/provenance" / (date + ".json")).read_text())
    payload = json.loads(raw)
    if raw != canonical(payload) + b"\n" or provenance["rawPayloadSha256"] != hashlib.sha256(raw).hexdigest():
        raise ValueError("KRX_RAW_SOURCE_HASH_CHANGED")
    records, validation = normalize_official(payload, date)
    selected = [r for r in records if r["securityId"] in set(members)]
    expected = MV.day_document(date, selected)
    if json.loads((root / "market" / (date + ".json")).read_text()) != expected:
        raise ValueError("KRX_NORMALIZED_SOURCE_LINEAGE_CHANGED")
    if (provenance.get("requestedDate") != date or provenance.get("source") != MV.SOURCE
            or provenance.get("endpoint") != DEFAULT_BASE + "/" + ENDPOINT
            or provenance.get("normalizedRows") != len(records)
            or provenance.get("storedMemberRows") != len(selected)
            or any(provenance.get(k) != v for k, v in validation.items())):
        raise ValueError("KRX_ACQUISITION_PROVENANCE_CHANGED")
    # Frozen serializer is deterministic and source values are never repaired.
    serialized = (json.dumps(expected, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()
    if (root / "market" / (date + ".json")).read_bytes() != serialized:
        raise ValueError("KRX_NONDETERMINISTIC_SERIALIZATION")


def collect_official(directory, dates, members, *, key, fetch=call, pace=.4, max_calls=None):
    """Preserve raw responses/provenance; resume only byte-verified first writes."""
    root = Path(directory)
    dates = sorted(set(dates))
    member_set = set(members)
    report = {"source": MV.SOURCE, "base": DEFAULT_BASE, "endpoint": ENDPOINT,
              "method": "OFFICIAL_KRX_GET_AUTH_KEY", "requestedStart": min(dates) if dates else None,
              "requestedEnd": max(dates) if dates else None, "requiredDates": len(dates),
              "identifierSelection": "UNION_OF_PINNED_HISTORICAL_TOP120_MEMBERS_FOR_RAW_STORAGE_ONLY",
              "requiredSecurityIds": sorted(members), "calls": 0, "status": "SERVED", "failure": None}
    if not key:
        report.update(status="AUTH_REQUIRED", failure="KRX_API_KEY_REQUIRED")
    else:
        for date in dates:
            if (root / "market" / (date + ".json")).exists():
                verify_cached_day(root, date, members)
                continue
            if max_calls is not None and report["calls"] >= max_calls:
                report.update(status="DATA_INSUFFICIENT", failure="CALL_BUDGET_SPENT_BEFORE_REQUIRED_COVERAGE")
                break
            acquired = datetime.now(timezone.utc).isoformat()
            try:
                report["calls"] += 1
                payload = fetch(DEFAULT_BASE, ENDPOINT, {"basDd": date.replace("-", "")}, key)
                raw = canonical(payload) + b"\n"
                immutable_bytes(root / "sources/krx" / (date + ".json.gz"), gzip.compress(raw, mtime=0))
                records, validation = normalize_official(payload, date)
                selected = [r for r in records if r["securityId"] in member_set]
                MV.write_day(root / "market", date, selected)
                X.atomic_write(root / "sources/provenance" / (date + ".json"), {
                    "schema": "KRX_DAILY_ACQUISITION_V1", "source": MV.SOURCE, "method": report["method"],
                    "endpoint": DEFAULT_BASE + "/" + ENDPOINT, "requestedDate": date,
                    "acquiredAtUtc": acquired, "rawPayloadSha256": hashlib.sha256(raw).hexdigest(),
                    "normalizedRows": len(records), "storedMemberRows": len(selected),
                    "parsing": "FROZEN_MV.parse_market_values; KRW unscaled; commas stripped; missing never zero",
                    **validation}, immutable=True)
            except Refused as exc:
                message = str(exc).replace(key, "[REDACTED]")
                report.update(status=classify_refusal(message), failure=message, failedDate=date)
                break
            except ValueError as exc:
                report.update(status="SCHEMA_CHANGED", failure=str(exc), failedDate=date)
                break
            if pace:
                time.sleep(pace)
    summary = cache_summary(root / "market")
    report["cache"] = summary
    present = set(summary["fileHashes"])
    report["missingDates"] = [d for d in dates if d + ".json" not in present]
    report["complete"] = report["status"] == "SERVED" and not report["missingDates"]
    X.atomic_write(root / "acquisition.json", report)
    return report


def _raw_files(root):
    files = set(X.source_files(root))
    files.update(p for pattern in ("sources/krx/*.json.gz", "sources/provenance/*.json", "foundation/*.json") for p in Path(root).glob(pattern))
    acquisition = Path(root) / "acquisition.json"
    if acquisition.is_file():
        files.add(acquisition)
    allowed = {str(p.relative_to(Path(root))) for p in files} | {MANIFEST, "snapshot-manifest.sha256"}
    for path in Path(root).rglob("*"):
        if path.is_file() and str(path.relative_to(Path(root))) not in allowed:
            raise ValueError("NON_ALLOWLIST_FILE_IN_RAW_SNAPSHOT: " + str(path.relative_to(Path(root))))
    return sorted(files)


def _component(path, root):
    rel = str(path.relative_to(root))
    raw = path.read_bytes()
    rows = []
    if path.name.endswith(".jsonl.gz"):
        rows = [json.loads(line) for line in gzip.decompress(raw).splitlines() if line.strip()]
    elif rel.startswith("ledger/replay-inputs/objects/"):
        rows = json.loads(gzip.decompress(raw))
    elif rel.startswith("market/"):
        rows = json.loads(raw)["records"]
    dates = [r["date"] for r in rows if r.get("date")]
    security = {r.get("securityId") or r.get("ticker") for r in rows if r.get("securityId") or r.get("ticker")}
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "rows": len(rows),
            "start": min(dates) if dates else None, "end": max(dates) if dates else None, "securities": len(security)}


def freeze_snapshot(directory, spec):
    root = Path(directory)
    acquisition = json.loads((root / "acquisition.json").read_text())
    if not acquisition.get("complete") or acquisition.get("missingDates"):
        raise ValueError("CANNOT_FREEZE_INCOMPLETE_KRX_ACQUISITION")
    summary = cache_summary(root / "market")
    if sorted(p[:-5] for p in summary["fileHashes"]) != required_dates(spec):
        raise ValueError("REQUIRED_KRX_DATE_COVERAGE_CHANGED")
    for date in required_dates(spec):
        verify_cached_day(root, date, acquisition["requiredSecurityIds"])
    if acquisition["cache"] != summary:
        raise ValueError("KRX_ACQUISITION_CACHE_CHANGED")
    # Reuse exact frozen accounting/universe/replay source validators before seal.
    X.load_sources(root, spec)
    files = {str(p.relative_to(root)): _component(p, root) for p in _raw_files(root)}
    document = {"schema": SCHEMA, "studyId": X.STUDY, "specSha256": SPEC_SHA, "diagnosticSpecSha256": DIAGNOSTIC_SHA,
                "sourceCommits": {"universeAndReplay": spec["inputs"]["universeSourceCommit"],
                                  "accounting": spec["inputs"]["accounting"]["sourceCommit"]},
                "inputIdentity": X.input_identity(root), "components": files,
                "scientificParametersChanged": False, "executionAuthorized": False}
    document["sha256"] = digest(document)
    immutable_bytes(root / MANIFEST, canonical(document) + b"\n")
    immutable_bytes(root / "snapshot-manifest.sha256", (document["sha256"] + "\n").encode())
    verify_snapshot(root)
    return document


def verify_snapshot(directory):
    root = Path(directory)
    document = json.loads((root / MANIFEST).read_text())
    if (document.get("schema") != SCHEMA or document.get("specSha256") != SPEC_SHA
            or document.get("diagnosticSpecSha256") != DIAGNOSTIC_SHA
            or digest({k:v for k,v in document.items() if k != "sha256"}) != document.get("sha256")
            or (root / "snapshot-manifest.sha256").read_text().strip() != document.get("sha256")):
        raise ValueError("RAW_SNAPSHOT_MANIFEST_CHANGED")
    actual = {str(p.relative_to(root)) for p in _raw_files(root)}
    if actual != set(document["components"]):
        raise ValueError("RAW_SNAPSHOT_COMPONENT_SET_CHANGED")
    for rel, metadata in document["components"].items():
        path = (root / rel).resolve()
        if not path.is_relative_to(root.resolve()) or (root / rel).is_symlink() or file_hash(path) != metadata["sha256"]:
            raise ValueError("RAW_SNAPSHOT_COMPONENT_CHANGED: " + rel)
    if X.input_identity(root) != document["inputIdentity"]:
        raise ValueError("RAW_SNAPSHOT_INPUT_IDENTITY_CHANGED")
    return document


@contextmanager
def outcome_firewall():
    """Runtime deny-list at all frozen outcome/authorization boundaries."""
    def forbidden(*args, **kwargs):
        raise RuntimeError("OUTCOME_OR_EXECUTION_ACCESS_FORBIDDEN_IN_DATA_READINESS")
    with ExitStack() as stack:
        for name in ("build_labels", "model_predictions", "evaluate_model", "replay_portfolio", "run_historical",
                     "issue_permit", "claim_execution_lock", "require_authorization"):
            stack.enter_context(patch.object(X, name, forbidden))
        stack.enter_context(patch.object(X.M, "fit_predict", forbidden))
        stack.enter_context(patch.object(X.M.Ridge, "fit", forbidden))
        stack.enter_context(patch.object(X.M.HistGradientBoostingRegressor, "fit", forbidden))
        stack.enter_context(patch.object(X.M.FamilyTransformer, "fit", forbidden))
        yield


def annual_coverage(bundle, spec):
    frame = bundle["features"].copy()
    if frame.empty:
        return {}
    flags = F.core_observability(frame)
    frame[flags.columns] = flags
    frame = frame.loc[frame.date >= spec["gates"]["firstCoverageDate"]]
    result = {}
    for year, group in frame.groupby(frame.date.str[:4]):
        result[year] = {"pitUniverseDenominator": len(group), "signalDates": group.date.nunique(),
                        "coreFamilyFloor": spec["gates"]["coreFamilyFloor"],
                        "families": {n: {"count": int(group[n].sum()), "share": float(group[n].mean())} for n in flags.columns},
                        "rawMissingCounts": {n: int((~np.isfinite(pd.to_numeric(group[n], errors="coerce"))).sum()) for n in F.RAW_FEATURES},
                        "accountingStatusCounts": dict(Counter(p.get("status", "UNKNOWN") for p in group.accountingProvenance)),
                        "marketValueMissing": int((~group.marketValuePresent).sum()),
                        "tradabilityMissing": int((~group.tradable).sum())}
    return result


def gates_only(directory, *, root=X.ROOT):
    from scripts.run_kr_model_overlay_portfolio_v1 import run
    frozen_spec(root)
    snapshot = verify_snapshot(directory)
    with outcome_firewall():
        # The unchanged formal runner owns the gate verdict. Extra counts only
        # describe its raw denominator; they can never override a failed gate.
        prepared = []
        original_prepare = X.prepare
        def prepare(*args):
            bundle = original_prepare(*args)
            prepared.append(bundle)
            return bundle
        with patch.object(X, "prepare", prepare):
            report = run("gates-only", input_root=directory, root=root)
        report["annualCoreFamilyCoverage"] = annual_coverage(prepared[0], frozen_spec(root)) if prepared else "NOT_MEASURED"
    if report["counters"] != asdict(X.Counters()):
        raise RuntimeError("NONZERO_OUTCOME_COUNTERS")
    if verify_snapshot(directory) != snapshot:
        raise ValueError("RAW_SNAPSHOT_CHANGED_DURING_GATES")
    report["rawSnapshotSha256"] = snapshot["sha256"]
    report["readiness"] = "READY_FOR_SEPARATE_EXECUTION_AUTHORIZATION" if report["status"] == "READY" else report["status"]
    report["executionAuthorizationCreated"] = False
    report["executionPermitIssued"] = False
    report["historicalExecutionPerformed"] = False
    return report
