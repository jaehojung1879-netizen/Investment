#!/usr/bin/env python3
"""kr-integrated-alpha-portfolio-v1 post-outcome concentration audit runner (POST-OUTCOME DESCRIPTIVE DIAGNOSTIC ONLY).

Modes
-----
local   Computes everything that can be established from frozen, repository-resident inputs alone: the benchmark integrity and period arithmetic, the tracking
        cross-check, the Samsung Electronics / SK Hynix market-cap concentration proxy, the same-data reference portfolios and the facts carried forward from the two
        sealed anatomy reports. Reads the replay-v16 objects and the pinned universe snapshots from the ``signal-history`` branch (verified against their pinned
        hashes before use) and writes the committed JSON and Markdown. No network, no formal artifact, no lock.
full    The read-only reconstruction against the exact formal artifacts (see pipeline notes below). Run only through the audit workflow.

It never calls the formal ``execute`` path, never creates, moves or deletes an execution lock, never writes a formal result and never reruns a sealed study.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pipeline import kr_integrated_alpha_portfolio_postoutcome_audit as A  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402
from pipeline import replay_inputs as RI  # noqa: E402

JSON_OUT = "docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.json"
MD_OUT = "docs/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.md"
OVERLAY_SPEC = "research_specs/kr-model-overlay-portfolio-v1.json"
INTEGRATED_SPEC = "research_specs/kr-integrated-alpha-portfolio-v1.json"
KS200_CSV = "data/kr-market-risk-anatomy-v1/sources/FDR_KS200/normalized.csv"
INDUSTRY_REPORT = "docs/results/kr-industry-opportunity-anatomy-v1-report.md"
STOCK_REPORT = "docs/results/kr-stock-within-industry-anatomy-v1-report.md"
REPLAY_MANIFEST = "ledger/historical/replay-v16/inputs.json"
OBJECTS = "ledger/replay-inputs/objects/"
# What GitHub reported when this audit was written (recorded, not asserted for the future; the full mode re-verifies live).
OBSERVED_AT_AUTHORING = {
    "observedOn": "2026-10-05", "via": "GitHub REST API and git ls-remote",
    "resultArtifact": {"id": 11371812532, "name": "kr-integrated-alpha-portfolio-v1-results-37374530672", "sizeBytes": 19516, "expired": False,
                       "digest": "sha256:bb29676403068b8330b12808ff30f6a5766fee35d4e66e96594591eaae766722", "workflowRunId": 37374530672,
                       "headSha": "33237df6d69e31a396959529378a0f881af9a58e"},
    "jobs": {"frozen-machine": "success", "execute": "success", "seal": "failure (Commit and push the immutable seal branch)"},
    "executeLogManifest": {"integrated-alpha-portfolio.json": "a204148896de57207e3bf7b6335397ad181afbb0868c21b9e584aefe050707ab",
                           "execution-started.json": "2108f3ca01ea0d1d5f90ec9fc74bbfcad1ebdfcf687161879a60b44f8e789b5a",
                           "specSha256": "eea6128cd55260904c7f74ba78698f67e522626620fd11d757c27de89c758f77",
                           "inputIdentitySha256": "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7",
                           "counters": {"cashSensitivityCalls": 6, "decisionCalls": 1, "featureBuilds": 1, "markerWrites": 1, "marketStateComputations": 1, "marketValueReads": 4,
                                        "metricCalls": 18, "replayCalls": 18}},
    "lockRefsPresent": list(A.FORMAL["lockRefs"]), "lockRefsPointAt": "33237df6d69e31a396959529378a0f881af9a58e",
    "rawInputArtifact": {"id": 11157875265, "name": "kr-model-raw-inputs-36844599518", "sizeBytes": 335950804,
                         "digest": "sha256:42eeb18b7a5c88816629036f472a93057b6a9be4768ad47292ba0d2750b4cce7"},
    "limitation": "the result artifact's contents were not readable: GitHub redirects the download to Azure blob storage, which the authoring sandbox cannot reach"}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def git_show(ref, path):
    out = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, cwd=ROOT)
    if out.returncode:
        raise ValueError("GIT_OBJECT_MISSING: " + path)
    return out.stdout


def git_blob_sha1(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def materialize_replay(ref, destination):
    """Copy the replay-v16 manifest and the benchmark / price objects out of git, then let the repository's own InputStore verify every object against the manifest."""
    manifest_bytes = git_show(ref, REPLAY_MANIFEST)
    manifest = json.loads(manifest_bytes)
    overlay = json.loads((ROOT / OVERLAY_SPEC).read_text())
    if RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest["sha256"] or manifest["sha256"] != overlay["inputs"]["replayManifestSha256"]:
        raise ValueError("REPLAY_MANIFEST_DIFFERS_FROM_THE_PINNED_ONE")
    (destination / REPLAY_MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    (destination / REPLAY_MANIFEST).write_bytes(manifest_bytes)
    (destination / OBJECTS).mkdir(parents=True, exist_ok=True)
    needed = 0
    for component, refs in manifest["components"].items():
        if component.startswith(("price/", "benchmark/")):
            for r in refs:
                (destination / OBJECTS / (r + ".json.gz")).write_bytes(git_show(ref, OBJECTS + r + ".json.gz"))
                needed += 1
    store = RI.InputStore(destination / "ledger", "replay-v16", manifest["dataVersion"])
    return manifest, store, {"replayManifestSha256": manifest["sha256"], "replayManifestPinnedBy": OVERLAY_SPEC, "objectsCopied": needed,
                             "objectVerification": "RI.InputStore.load_component re-hashes every object against the manifest on read"}


def load_panels(manifest, store):
    bench_rows, price_rows = [], []
    for component in sorted(manifest["components"]):
        if not RI.is_price_panel(component):
            continue
        if component.startswith("benchmark/"):
            bench_rows += [r for r in store.load_component(component, manifest) if r["ticker"] == A.BENCHMARK]
        elif component.startswith("price/"):
            price_rows += [r for r in store.load_component(component, manifest) if r["ticker"].endswith(".KS")]
    bench = pd.DataFrame(bench_rows)
    duplicated = int(bench.date.duplicated().sum())
    if duplicated:
        raise ValueError("DUPLICATE_BENCHMARK_SESSIONS")
    prices = pd.DataFrame(price_rows)
    return bench.sort_values("date").set_index("date").Close, prices.pivot(index="date", columns="ticker", values="Close").sort_index(), duplicated


def load_universe(ref):
    """The 14 universe shards, each verified against the git blob SHA the sealed overlay study pinned for the formal run."""
    import gzip
    pins = json.loads((ROOT / OVERLAY_SPEC).read_text())["inputs"]["universeBlobs"]
    rows, verified = [], {}
    for rel, sha in sorted(pins.items()):
        blob = git_show(ref, rel)
        if git_blob_sha1(blob) != sha:
            raise ValueError("UNIVERSE_BLOB_DIFFERS_FROM_THE_PINNED_ONE: " + rel)
        verified[rel] = sha
        rows += [json.loads(line) for line in gzip.decompress(blob).decode().splitlines() if line.strip()]
    return pd.DataFrame(rows), verified


def load_ks200():
    spec = json.loads((ROOT / INTEGRATED_SPEC).read_text())
    data = (ROOT / KS200_CSV).read_bytes()
    pinned = spec["inputs"]["marketSourceFiles"][KS200_CSV]
    if sha256_bytes(data) != pinned:
        raise ValueError("KS200_CSV_DIFFERS_FROM_THE_PINNED_ONE")
    frame = pd.read_csv(KS200_CSV)
    series = frame.set_index("date").value
    series.index = series.index.astype(str)
    return series, {"path": KS200_CSV, "sha256": pinned, "pinnedBy": INTEGRATED_SPEC}


def run_local(ref, output_json=None, output_md=None):
    with tempfile.TemporaryDirectory() as tmp:
        manifest, store, replay_identity = materialize_replay(ref, Path(tmp))
        benchmark, close, duplicates = load_panels(manifest, store)
    universe, universe_pins = load_universe(ref)
    ks200, ks_identity = load_ks200()
    calendar = [str(d.date()) for d in RC.sessions("2011-01-03", A.CUTOFF, "KR")]
    sessions = [d for d in calendar if A.WINDOW_START <= d <= A.CUTOFF]
    report_hashes = {p: sha256_bytes((ROOT / p).read_bytes()) for p in (INDUSTRY_REPORT, STOCK_REPORT)}
    evidence = A.sealed_anatomy_evidence((ROOT / INDUSTRY_REPORT).read_text(), (ROOT / STOCK_REPORT).read_text(), report_hashes)
    identities = {"replay": replay_identity, "benchmarkDuplicateSessions": duplicates, "universeShardsVerifiedAgainstPinnedGitBlobs": len(universe_pins),
                  "universeBlobPins": universe_pins, "ks200PriceIndex": ks_identity, "priceTickers": int(close.shape[1]), "universeSnapshots": int(universe.date.nunique())}
    result = A.build_local_result(benchmark=benchmark, index_levels=ks200, close=close, universe=universe, sessions=sessions, calendar_sessions=calendar, identities=identities,
                                  sealed_evidence=evidence, observed_github_state=OBSERVED_AT_AUTHORING)
    result["notRunSections"] = A.not_run_sections()
    result["questionMatrix"] = A.question_matrix(result)
    A.assert_clean_language(result)
    text = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(text)
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(A.markdown_report(json.loads(text)))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("local", "full"), default="local")
    parser.add_argument("--signal-history-ref", default="origin/signal-history")
    parser.add_argument("--output-json", default=str(ROOT / JSON_OUT))
    parser.add_argument("--output-md", default=str(ROOT / MD_OUT))
    parser.add_argument("--inputs")
    parser.add_argument("--formal-result")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if args.mode == "local":
        run_local(args.signal_history_ref, args.output_json, args.output_md)
        print(json.dumps({"mode": "local", "json": args.output_json, "md": args.output_md}))
        return
    from pipeline import kr_integrated_alpha_portfolio_postoutcome_full as FULL
    print(json.dumps(FULL.run(args.inputs, args.formal_result, args.output), sort_keys=True, default=str))


if __name__ == "__main__":
    main()
