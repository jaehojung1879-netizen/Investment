"""Reproduce alpha-opportunity-model-v3's input-only survivorship audit.

    python scripts/audit_alpha_opportunity_v3_survivorship.py \
        --input-root <checkout of signal-history 4ea107e with ledger/replay-inputs,
                      ledger/historical/replay-v16/inputs.json, ledger/universe/kr> \
        --output docs/results/alpha-opportunity-model-v3-survivorship-audit.json

Reads sealed identities, price EXISTENCE, membership and corporate-event
presence. Computes no return and constructs no label. Output is byte-stable.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v3_survivorship as A  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import replay_inputs as RI  # noqa: E402

REPLAY = "replay-v16"
US_MEMBERSHIP = ROOT / "research_specs/alpha-opportunity-model-v1-us-membership.json.gz"
START, THROUGH = "2013-01-01", "2026-09-14"
KR_TOP = 120


def blob_sha1(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def kr_snapshots(ledger):
    grouped = {}
    for path in sorted((Path(ledger) / "universe/kr").glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            grouped.setdefault(row["date"], []).append(row)
    return [{"date": d, "members": sorted(r["ticker"] for r in sorted(
                (r for r in rows if r.get("rank") is not None), key=lambda r: (r["rank"], r["ticker"]))[:KR_TOP])}
            for d, rows in sorted(grouped.items())]


def run(input_root):
    ledger = Path(input_root) / "ledger"
    manifest_raw = json.loads((ledger / f"historical/{REPLAY}/inputs.json").read_text())
    store = RI.InputStore(ledger, REPLAY, manifest_raw["dataVersion"])
    manifest = store.manifest()
    rows = []
    for name in sorted(c for c in manifest["components"] if RI.is_price_panel(c)):
        rows.extend(store.load_component(name, manifest))
    avail = A.availability_from_rows(rows)
    del rows
    dividends = {}
    for name in sorted(c for c in manifest["components"] if c.startswith("corporate-events/20")):
        for row in store.load_component(name, manifest):
            if row.get("dividend"):
                dividends[row["ticker"]] = dividends.get(row["ticker"], 0) + 1
    price_source = store.load_component("price/source", manifest)
    us = json.loads(gzip.decompress(US_MEMBERSHIP.read_bytes()))["snapshots"]
    kr = kr_snapshots(ledger)
    audits, verdicts, windows = {}, {}, {}
    for region, snaps in (("US", us), ("KR", kr)):
        audit = A.audit_region(region, snaps, avail, dividends, start=START, through=THROUGH)
        audits[region] = audit
        verdicts[region] = A.region_verdict(audit)
        windows[region] = A.restricted_window_exists(audit)
    kr_shards = {str(p.relative_to(input_root)): blob_sha1(p.read_bytes())
                 for p in sorted((ledger / "universe/kr").glob("krx-universe-*.jsonl.gz"))}
    return {
        "studyId": "alpha-opportunity-model-v3", "phase": "INPUT_ONLY_SURVIVORSHIP_AUDIT",
        "historicalOutcomesComputed": False, "returnsComputed": False, "labelsConstructed": False,
        "modelsTrained": False, "priceUse": "existence of a positive finite close/volume only",
        "inputs": {"signalHistoryCommit": "4ea107ed0cde289f0a049a65ff13d2441a786710",
                   "replayVersion": REPLAY, "replayManifestSha256": manifest["sha256"],
                   "through": manifest["through"],
                   "usMembership": {"path": str(US_MEMBERSHIP.relative_to(ROOT)),
                                    "sha256": hashlib.sha256(US_MEMBERSHIP.read_bytes()).hexdigest()},
                   "krUniverseShardBlobSha1": kr_shards,
                   "priceSource": [{k: s.get(k) for k in ("region", "vendor", "distributions", "source")}
                                   for s in price_source]},
        "window": {"start": START, "through": THROUGH, "krTopN": KR_TOP,
                   "membership": "strictly-earlier snapshot per last regional session of each week"},
        "regions": audits, "verdicts": verdicts, "restrictedWindow": windows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = run(args.input_root)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"verdicts": report["verdicts"], "restrictedWindow": report["restrictedWindow"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
