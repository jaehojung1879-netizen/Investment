"""Materialise the replay-v16 macro, vix and fx (DEXKOUS) components from git objects at the pinned signal-history commit.

    python research/adaptive_cocktail_v1/load_sources.py --scratch <dir>

Every object's decompressed SHA-256 must equal its manifest reference (content addressing), and the manifest's own digest must be the
one the sealed studies pinned. Writes <dir>/macro_panel.pkl and <dir>/vix_fx.pkl.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

COMMIT = "4ea107ed0cde289f0a049a65ff13d2441a786710"
MANIFEST_SHA = "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2"


def blob(path):
    return subprocess.check_output(["git", "cat-file", "blob", f"{COMMIT}:{path}"])


def objects(refs):
    rows = []
    for ref in refs:
        raw = gzip.decompress(blob(f"ledger/replay-inputs/objects/{ref}.json.gz"))
        if hashlib.sha256(raw).hexdigest() != ref:
            raise SystemExit("OBJECT_HASH_MISMATCH: " + ref)
        rows += json.loads(raw)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    m = json.loads(blob("ledger/historical/replay-v16/inputs.json"))
    if m.get("sha256") != MANIFEST_SHA:
        raise SystemExit("REPLAY_MANIFEST_CHANGED")
    c = m["components"]
    mac = pd.DataFrame(objects(c["macro"])).drop_duplicates("date", keep="last")
    mac.index = pd.to_datetime(mac.pop("date"))
    mac = mac.sort_index()
    vix = pd.DataFrame(objects(c["vix"]))
    fx = pd.DataFrame(objects(c["fx/USD_KRW"]))
    s = Path(a.scratch)
    mac.to_pickle(s / "macro_panel.pkl")
    pd.to_pickle({"vix": vix, "fx": fx}, s / "vix_fx.pkl")
    print(json.dumps({"macroRows": len(mac), "vixRows": len(vix), "fxRows": len(fx), "manifest": MANIFEST_SHA}))


if __name__ == "__main__":
    main()
