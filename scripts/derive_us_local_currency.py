"""Re-express the committed US replay paths in USD (an accounting identity).

    python scripts/derive_us_local_currency.py <ledger_dir> --output <json>

The replay values every US path in KRW with USD/KRW included. For a path whose
every holding is a US asset (P0, P1 and C2 hold US stocks and SPY only),
USD value = KRW value x fx(start) / fx(t) exactly, so this reads no new price
and computes no new outcome. C1 holds KRW cash and has no exact USD form, so
it is not converted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import provenance                 # noqa: E402
from pipeline import replay_inputs as RI         # noqa: E402
from pipeline import replay_valuation as RV      # noqa: E402

RESULT = ROOT / "docs/weekly-decision/weekly-passive-first-v1-replay.json"
CONVERTIBLE = ("P0", "P1", "C2")


def convert(weekly_nav: list, fx: pd.Series, start: str, end: str) -> dict:
    fx0 = float(fx.loc[:start].iloc[-1])
    points = [[d, round(v * fx0 / float(fx.loc[:d].iloc[-1]), 6)] for d, v in weekly_nav]
    years = RV.span_years(start, end)
    final = points[-1][1]
    return {"cagrPct": round((final ** (1 / years) - 1) * 100, 3), "finalNav": final,
            "fxStart": fx0, "fxEnd": float(fx.loc[:end].iloc[-1])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = json.loads(RESULT.read_text())
    store = RI.InputStore(Path(args.ledger_dir), provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if manifest["sha256"] != result["inputManifestSha256"]:
        raise ValueError("frozen inputs differ from the replay's")
    fx = RV.normalize_daily_series(RI.unpack(store.load(manifest, valuation_only=True))["fx"]).dropna()
    us = result["regions"]["US"]
    out = {"id": "weekly-passive-first-v1-us-local-currency", "basis": "USD",
           "method": "KRW path x fx(start)/fx(t); exact only for all-US-asset paths",
           "evidenceClass": result["evidenceClass"], "status": us["status"],
           "replaySha256Source": "docs/weekly-decision/weekly-passive-first-v1-replay.json",
           "paths": {}}
    for key in CONVERTIBLE:
        summary = us["paths"].get(key) or {}
        if not summary.get("available"):
            continue
        out["paths"][key] = convert(us["weeklyNav"][key], fx, summary["startDate"], summary["endDate"])
    out["usdKrwChangePct"] = round((out["paths"]["P0"]["fxEnd"] / out["paths"]["P0"]["fxStart"] - 1) * 100, 3)
    Path(args.output).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out["paths"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
