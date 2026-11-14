"""Recreate private baseline inputs from pinned, read-only Git objects.

Uses original input helpers only; never runs a research evaluation. Git may
fetch absent promisor blobs using the caller's existing repository access.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

from pipeline import replay_inputs as RI
from pipeline.us_dual_benchmark_data import SealedReader, SOURCE_COMMIT
from research.us_historical_market_recovery_v1.collect import private_root, canonical

ROOT = Path(__file__).resolve().parents[2]


def save(path, value):
    raw = canonical(value)
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)


def verify_input_helpers(root=ROOT):
    """Pin reused inputs/helpers without invoking an old study's execution gate."""
    protocol = json.loads((root / "docs/us-decision-pilot-v1-protocol.json").read_bytes())
    pins = {**protocol["inputAndHelperHashes"],
            "pipeline/us_decision_pilot.py": protocol["coreCodeSha256"],
            "scripts/run_us_decision_pilot.py": protocol["orchestrationCodeSha256"]}
    for name, expected in pins.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("REUSED_INPUT_OR_HELPER_CHANGED:" + name)
    return pins


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    private = private_root(args.private_root)
    reader = SealedReader(args.repo)
    manifest = reader.manifest()
    if RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest["sha256"]:
        raise ValueError("SEALED_MANIFEST_CONTENT_MISMATCH")
    save(private / "sealed-inputs-manifest.json", manifest)
    bars, events, lineage, receipts = defaultdict(dict), defaultdict(dict), {}, []
    for name, refs in sorted(manifest["components"].items()):
        is_bar = name.startswith(("price/20", "benchmark/20"))
        is_event = name.startswith("corporate-events/20")
        is_lineage = name in ("price/source", "benchmark/source", "corporate-events/source")
        if not (is_bar or is_event or is_lineage):
            continue
        for ref in refs:
            blob = reader.blob("ledger/replay-inputs/objects/" + ref + ".json.gz")
            content = gzip.decompress(blob)
            if hashlib.sha256(content).hexdigest() != ref:
                raise ValueError("SEALED_COMPONENT_CONTENT_MISMATCH:" + ref)
            rows = json.loads(content)
            receipts.append({"component": name, "sha256": ref, "bytes": len(blob), "rows": len(rows)})
            if is_lineage:
                lineage[name] = rows
                continue
            for row in rows:
                ticker, day = row["ticker"], row["date"]
                if ticker.endswith((".KS", ".KQ")):
                    continue
                bucket = bars if is_bar else events
                if day in bucket[ticker] and bucket[ticker][day] != row:
                    raise ValueError("CONFLICTING_PINNED_SECURITY_DATE")
                bucket[ticker][day] = row
    save(private / "baseline-bars.json.gz", bars)
    save(private / "baseline-events.json.gz", events)
    save(private / "baseline-lineage.json.gz", lineage)
    save(private / "baseline-component-receipts.json", receipts)
    from scripts import run_us_decision_pilot as P
    verify_input_helpers(args.repo)
    filings, filings_receipts = P.load_filings(args.repo)
    close = pd.DataFrame({t: pd.Series({d: r["Close"] for d, r in rows.items()}, dtype=float)
                          for t, rows in bars.items()})
    close.index = pd.to_datetime(close.index)
    from pipeline import replay_calendar as RC
    close = close.reindex(RC.sessions("2011-01-03", manifest["through"], "US"))
    frames, annual, weeks = P.build_signals(close, filings, args.repo)
    result = {"cohorts": [{"signal": str(d.date()), "tickers": sorted(f.index.tolist())}
                           for d, f in sorted(frames.items())],
              "annual": annual, "weeks": weeks, "filings_receipts": filings_receipts}
    save(private / "original-input-eligible-cohorts.json", result)
    save(private / "preparation-receipt.json", {"commit": SOURCE_COMMIT, "manifest": manifest["sha256"],
         "price_rows": sum(len(v) for v in bars.values()), "component_count": len(receipts),
         "input_eligible_records": sum(len(r["tickers"]) for r in result["cohorts"])})
    print((private / "preparation-receipt.json").read_text())


if __name__ == "__main__":
    main()
