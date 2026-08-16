"""Train and validate the Opportunity model against the historical OOS ledger.

Writes ``ledger/opportunity-model.json``: the *specification* that won
walk-forward selection, not a serialized model object. The daily build refits
that spec on the ledger and scores today's cross-section
(``opportunity.score_candidates``).

Persisting a spec rather than a pickle is deliberate. A pickle rots across
scikit-learn versions, fails in ways that are easy to swallow silently, and
makes it hard to prove that the model scoring today is the one that passed
validation. A spec — family, hyperparameters, feature list, target, calibration
method — plus a deterministic refit gives reproducibility and an auditable
paper trail, at the cost of a few seconds per build.

The file also carries the full search log, fold-by-fold results, the sealed
holdout score and the acceptance decision, so a reader can see how many things
were tried before this one was picked.

Usage:
    python scripts/train_opportunity.py <ledger-dir> [--warning] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS         # noqa: E402
from pipeline import opportunity as OP              # noqa: E402
from pipeline import provenance as prov_mod         # noqa: E402
from pipeline import walkforward as WF              # noqa: E402
from pipeline.config import load_config             # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--warning", action="store_true",
                        help="train the deterioration model instead")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    cfg, _ = load_config()
    opportunity_cfg = dict(cfg.opportunity or {})
    if not opportunity_cfg.get("enabled", True):
        print("opportunity model disabled in config")
        return 0

    ledger_dir = Path(args.ledger_dir)
    # Reading one generation only: a spec trained across replay generations
    # would be trained on two different definitions of the same feature.
    signals = HS.load(ledger_dir, HS.SIGNALS, generation=prov_mod.REPLAY_VERSION)
    outcomes = HS.load(ledger_dir, HS.OUTCOMES, generation=prov_mod.REPLAY_VERSION)
    if not signals or not outcomes:
        print("no historical ledger to train on — run scripts/run_replay.py first")
        return 0

    dataset = OP.build_dataset(signals, outcomes)
    if dataset.empty:
        print("historical signals have no matured outcomes yet")
        return 0
    print(f"dataset: {len(dataset)} rows, {dataset['date'].nunique()} dates, "
          f"{dataset['date'].min().date()} .. {dataset['date'].max().date()}")

    guard = WF.HoldoutGuard.from_config(opportunity_cfg)
    if guard.start >= pd.Timestamp(dataset["date"].max()):
        print(f"WARNING: configured final holdout ({guard.start.date()}) starts after the "
              f"ledger ends; no sealed evaluation is possible yet")
    targets = OP.WARNING_TARGET_SPECS if args.warning else OP.TARGET_SPECS

    started = time.time()
    result = OP.train(dataset, targets=targets, cfg=opportunity_cfg, guard=guard,
                      progress=not args.quiet)
    result["trainedAt"] = pd.Timestamp.utcnow().isoformat()
    result["kind"] = "warning" if args.warning else "opportunity"
    result["replayVersion"] = prov_mod.REPLAY_VERSION
    result["featureVersion"] = prov_mod.FEATURE_VERSION
    result["modelVersion"] = prov_mod.MODEL_VERSION
    print(f"training finished in {time.time() - started:.0f}s: status={result['status']}")

    if result.get("status") == "TRAINED":
        winner, test = result["winner"], result["winner"]["test"]
        top = test.get("topBucket") or {}
        print(f"  winner              {winner['name']} / {winner['target']}")
        print(f"  OOS ROC-AUC         {test.get('rocAuc')}  PR-AUC lift {test.get('prAucLift')}")
        print(f"  decile monotonicity {test.get('decileMonotonicity')}")
        print(f"  top-decile excess   {top.get('meanExcessPct')}% "
              f"(MDD {top.get('mddPct')}%, CVaR {top.get('cvar95Pct')}%, "
              f"{top.get('nonOverlappingDates')} non-overlapping dates)")
        print(f"  variants tested     {result['diagnostics']['searchLog']['variantsTested']}")
        print(f"  ACCEPTED            {result['accepted']}")
        for name, ok in (result.get("acceptance") or {}).get("checks", {}).items():
            print(f"      {'PASS' if ok else 'FAIL'}  {name}")
        if not result["accepted"]:
            print("  -> model NOT published; the rule-based change score stays in force.")

    name = "warning-model.json" if args.warning else "opportunity-model.json"
    out = ledger_dir / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
