"""Score alternative alpha compositions against the selection null.

WHY THIS EXISTS. The per-sleeve attribution on the production ledger says the
two live price sleeves disagree sharply in the US over 2013-2026:

    US 126D   momentum  rank IC +0.018
              lowvol    rank IC -0.086
              composite rank IC -0.023      <- what the model actually ranks on

    KR 126D   momentum  +0.007   lowvol +0.014   composite +0.010

So the US composite is negative because a 40%-weighted sleeve runs backwards,
and the conviction score then divides by downside volatility as well — applying
the same anti-predictive quantity twice. That is a specific, falsifiable claim
about the model, and this script is how it gets tested rather than assumed.

DISCIPLINE. These variants were written AFTER looking at that attribution, so
they are in-sample by construction. Two rules keep that from becoming a lie:

  * Everything here runs on the VALIDATION period only — dates strictly before
    ``opportunity.finalHoldoutStart``. The holdout is not read, not counted, and
    not reported on.
  * A variant is judged by the selection null, not by its return. A composition
    that raises the headline while staying inside the null distribution has not
    been shown to pick better; it has been shown to be luckier in one sample.

Reusing the frozen point-in-time sleeve percentiles is what makes this cheap: no
replay is re-run, no new data is touched, and no look-ahead can enter that was
not already in the ledger.

Usage:
    python scripts/compare_alpha_variants.py <ledger-dir> [--draws 100] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS          # noqa: E402
from pipeline import portfolio_validation as PV      # noqa: E402
from pipeline import provenance as prov_mod          # noqa: E402
from pipeline import selection_null as SN            # noqa: E402
from pipeline.config import load_config              # noqa: E402

# Effective live weights once value/quality are withheld for want of PIT
# fundamentals: momentum 0.30 and lowvol 0.20, renormalized.
BASELINE_BLEND = {"momentum": 0.6, "lowvol": 0.4}

VARIANTS = {
    "V0_PRODUCTION": None,                       # stored alphaPercentile, untouched
    "V1_MOMENTUM_ONLY": {"momentum": 1.0},
    "V2_LOWVOL_ONLY": {"lowvol": 1.0},           # diagnostic: confirms the attribution
    "V3_BLEND_PROXY": dict(BASELINE_BLEND),      # sanity: should track V0 closely
    "V4_MOMENTUM_TILT": {"momentum": 0.85, "lowvol": 0.15},
}

# Region-specific rules are the most overfit-prone thing in this file: one
# sample, two regions, a rule chosen after seeing both. Kept for comparison and
# flagged in the output rather than treated as a candidate.
REGION_VARIANTS = {"V5_REGIONAL_SPLIT": {"US": {"momentum": 1.0},
                                         "KR": dict(BASELINE_BLEND)}}


def _blend_for(name: str, region: str) -> dict | None:
    if name in REGION_VARIANTS:
        return REGION_VARIANTS[name].get(region) or dict(BASELINE_BLEND)
    return VARIANTS.get(name)


ALPHA_FIELDS = ("alphaPercentile", "longTermAlphaPercentile", "alpha", "rawAlpha")


@contextmanager
def alpha_variant(signals: list[dict], variant: str):
    """Apply a variant's alpha in place for the duration of the block.

    In place, and not on a copy, because copying is not affordable here: the
    validation slice is ~295k signals whose nested feature blocks run to tens of
    kilobytes each, and ``[dict(row) for row in signals]`` took 9.4 GB of a 16 GB
    box and never finished. Only the four alpha fields change, so the originals
    fit in a small side list and are put back on the way out — including if the
    body raises, or the next variant would silently score the previous one's
    alpha.

    The percentile is taken within each date x region cross-section, the same
    scope the production composite is ranked in. ``alpha`` is a monotone
    transform of it because the research screen re-ranks on alpha, so only the
    ordering matters there. A signal whose sleeves are missing is left alone: a
    variant may not resurrect a name the replay could not score.
    """
    if variant == "V0_PRODUCTION":
        yield signals
        return

    original = [tuple(row.get(field) for field in ALPHA_FIELDS) for row in signals]
    by_cell: dict[tuple, list[int]] = defaultdict(list)
    for index, row in enumerate(signals):
        by_cell[(row.get("date"), row.get("region"))].append(index)
    try:
        for (_date, region), indices in by_cell.items():
            blend = _blend_for(variant, region or "US")
            scores, scored_idx = [], []
            for index in indices:
                sleeves = signals[index].get("factorPercentiles") or {}
                total = weight = 0.0
                for sleeve, share in blend.items():
                    value = sleeves.get(sleeve)
                    if value is None:
                        continue
                    total += float(value) * float(share)
                    weight += float(share)
                if weight <= 0:
                    continue
                scores.append(total / weight)
                scored_idx.append(index)
            if not scored_idx:
                continue
            pct = pd.Series(scores).rank(method="average", pct=True) * 100
            for slot, index in enumerate(scored_idx):
                value = round(float(pct.iloc[slot]), 4)
                alpha = round((value - 50.0) / 50.0, 6)
                signals[index]["alphaPercentile"] = value
                signals[index]["longTermAlphaPercentile"] = value
                signals[index]["alpha"] = alpha
                signals[index]["rawAlpha"] = alpha
        yield signals
    finally:
        for row, values in zip(signals, original):
            for field, value in zip(ALPHA_FIELDS, values):
                row[field] = value


def summarize(report: dict) -> dict:
    replay = report or {}
    champion = ((replay.get("selectors") or {}).get(PV.CHAMPION) or {}).get("summary") or {}
    null = replay.get("selectionNull") or {}
    modes = null.get("byMode") or {}

    def mode_row(mode: str) -> dict:
        blob = modes.get(mode) or {}
        stats = blob.get("statistics") or {}
        return {
            "verdict": (blob.get("overall") or {}).get("verdict") or blob.get("reason"),
            "turnoverPct": blob.get("nullMedianTurnoverPct"),
            **{key: (stats.get(key) or {}).get("pValueBeatsRandom")
               for key in ("annualizedExcessPct", "informationRatio", "sharpe")},
        }

    return {
        "periods": champion.get("periods"),
        "annualizedExcessPct": champion.get("annualizedExcessPct"),
        "informationRatio": champion.get("informationRatio"),
        "sharpe": champion.get("sharpe"),
        "mddPct": champion.get("mddPct"),
        "turnoverPct": champion.get("averageTurnoverPct"),
        "nullVerdict": (null.get("overall") or {}).get("verdict"),
        "byMode": {mode: mode_row(mode) for mode in SN.MODES},
    }


def rank_ic(report: dict) -> dict:
    regions = ((report or {}).get("alphaDiagnostics") or {}).get("regions") or {}
    return {key: (row.get("rankIC") or {}).get("mean")
            for key, row in regions.items() if key.endswith(":126")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--draws", type=int, default=100,
                        help="null draws per mode; screening needs fewer than publishing")
    parser.add_argument("--json", default=None)
    parser.add_argument("--only", default=None, help="comma-separated variant names")
    args = parser.parse_args(argv)

    cfg, _ = load_config()
    holdout = str((cfg.opportunity or {}).get("finalHoldoutStart") or "")
    if not holdout:
        print("ERROR: opportunity.finalHoldoutStart is not configured; refusing to "
              "run without a sealed holdout boundary.")
        return 1

    signals = HS.load(args.ledger_dir, HS.SIGNALS, prov_mod.REPLAY_VERSION)
    outcomes = HS.load(args.ledger_dir, HS.OUTCOMES, prov_mod.REPLAY_VERSION)
    diagnostics = json.loads(
        (Path(args.ledger_dir) / "historical-diagnostics.json").read_text(encoding="utf-8"))

    # The holdout is not merely unreported here — it is removed from the input,
    # so no variant can be selected on it even by accident.
    kept = [row for row in signals if str(row.get("date") or "") < holdout]
    keep_ids = {row.get("id") for row in kept}
    kept_outcomes = [row for row in outcomes if row.get("id") in keep_ids]
    print(f"ledger {len(signals)} signals -> validation {len(kept)} "
          f"(sealed from {holdout}); outcomes {len(kept_outcomes)}", flush=True)
    if not kept:
        print("ERROR: no validation signals before the holdout boundary.")
        return 1

    names = ([name.strip() for name in args.only.split(",")] if args.only
             else [*VARIANTS, *REGION_VARIANTS])
    cfg_pf = dict(cfg.kelly_portfolio)
    cfg_pf["selectionNullDraws"] = int(args.draws)

    results = {}
    for name in names:
        started = time.time()
        with alpha_variant(kept, name) as variant_signals:
            report = PV.portfolio_replay(variant_signals, kept_outcomes,
                                         cfg_lt=cfg.longterm, cfg_pf=cfg_pf,
                                         diagnostics=diagnostics)
        results[name] = {
            "summary": summarize(report.get("portfolioReplay") or report),
            "rankIC126": rank_ic(report),
            "regionSpecific": name in REGION_VARIANTS,
            "seconds": round(time.time() - started, 1),
        }
        row = results[name]["summary"]
        print(f"\n=== {name} ({results[name]['seconds']}s) ===", flush=True)
        print(f"  rank IC 126D  {results[name]['rankIC126']}")
        print(f"  champion      excess {row['annualizedExcessPct']}%/yr  IR {row['informationRatio']}"
              f"  Sharpe {row['sharpe']}  MDD {row['mddPct']}%  turnover {row['turnoverPct']}%"
              f"  ({row['periods']} blocks)")
        for mode, cell in row["byMode"].items():
            print(f"  null {mode:22s} {str(cell['verdict']):32s} "
                  f"p(excess/IR/Sharpe) {cell['annualizedExcessPct']}/"
                  f"{cell['informationRatio']}/{cell['sharpe']}"
                  f"  turnover {cell['turnoverPct']}%")
        print(f"  COMBINED VERDICT: {row['nullVerdict']}")

    print("\n" + "=" * 78)
    print("Validation period only. These variants were written after reading the")
    print("attribution they are testing, so a winner here is a CANDIDATE, not a")
    print("result: it has to be frozen and scored once on the sealed holdout")
    print(f"({holdout} onward) before it means anything out of sample.")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"holdoutStart": holdout, "draws": args.draws,
                        "validationSignals": len(kept), "results": results},
                       ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
