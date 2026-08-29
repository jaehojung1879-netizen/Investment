"""Score alternative alpha compositions against the selection null.

WHAT THIS FOUND. Six compositions were run on the validation period. None beat
the null, and the production blend was the best of them:

    variant              excess/yr   Sharpe      MDD   US IC    persistent p(IR)
    V0 production           +7.27%    1.094   -15.4%  -0.039               0.119
    V1 momentum only       +10.44%    0.930   -20.2%  -0.008               0.277
    V2 lowvol only          +1.54%    0.729   -13.1%  -0.068               0.416
    V3 blend 0.6/0.4        +4.01%    0.951   -12.5%  -0.035               0.386
    V4 blend 0.85/0.15      +5.95%    0.705   -22.0%  -0.016               0.545
    V5 regional split       +5.63%    0.822   -25.7%  -0.008               0.594

WHAT IT WAS BUILT TO TEST, AND WHY THAT PREMISE WAS WRONG. The starting claim was
that the US composite is dragged negative by a 40%-weighted lowvol sleeve whose
rank IC runs backwards, so removing it should help. Dropping lowvol does improve
the US rank IC (-0.039 -> -0.008), and the portfolio still got worse: return rose
3.2 points a year, drawdown widened by 4.8, Sharpe fell, and the p-value against
the null more than doubled. Lowvol was not predicting returns badly; it was
holding down risk, and the blend beats either sleeve alone on a risk-adjusted
basis.

The general lesson is worth more than the specific one: RANK IC IS THE WRONG
INSTRUMENT FOR THIS MODEL. It scores whether the whole cross-section is ordered
correctly on average; this book holds five names. V1 has the best US IC and a
worse Sharpe than V0; V2 has the worst US IC and the smallest drawdown. Judge a
concentrated book by its null-tested portfolio path, not by IC.

One more trap, recorded because it nearly set the direction: the attribution that
motivated all this was measured over 2013-2026, which INCLUDES the sealed
holdout. On the validation period alone the KR IC is -0.001, not the +0.019 that
made a region-specific rule look reasonable. V5 existed because of a number that
leaked from data no variant is allowed to be chosen on.

DISCIPLINE. Variants written after reading an attribution are in-sample by
construction. Two rules keep that from becoming a lie:

  * Everything runs on the VALIDATION period only — dates strictly before
    ``opportunity.finalHoldoutStart``. The holdout is removed from the input, not
    merely unreported, so nothing can be selected on it by accident.
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

import numpy as np
import pandas as pd
from scipy.stats import norm

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

# The ledger stores sleeve PERCENTILES; production blends sleeve Z-SCORES.
# Those are not interchangeable, and the V3 control proved it: blending the
# percentiles at production's own 0.6/0.4 weights returned Sharpe 0.325 against
# production's 1.094 on the same dates. A percentile throws away magnitude — the
# top name scores 100 whether it is one sigma or five above the mean — and with
# a fat-tailed momentum cross-section that reorders the book.
#
# The sleeves are sector-neutral z-scores, so their cross-section is roughly
# normal and the normal quantile of the percentile recovers the z up to a
# monotone rescaling. Single-sleeve variants are unaffected either way: probit
# is monotone, so momentum-only ranks identically before and after.
_Z_CLIP = 1e-4


def _to_z(percentile: float) -> float:
    """Percentile (0-100) back to an approximate sector-neutral z-score."""
    return float(norm.ppf(min(max(float(percentile) / 100.0, _Z_CLIP), 1 - _Z_CLIP)))


@contextmanager
def alpha_variant(signals: list[dict], variant: str,
                  outcomes: list[dict] | None = None):
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

    # Outcomes carry their own copy of alphaPercentile, and the diagnostics read
    # it from THERE, not from the signals — `_joined_frame` builds its table out
    # of `horizon_frame(outcomes)`. Rewriting only the signals left every
    # variant reporting production's rank IC under its own name, identical to
    # six decimal places, which is how the bug was spotted.
    outcomes = outcomes if outcomes is not None else []
    original = [tuple(row.get(field) for field in ALPHA_FIELDS) for row in signals]
    original_outcomes = [row.get("alphaPercentile") for row in outcomes]
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
                    total += _to_z(value) * float(share)
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
        if outcomes:
            by_id = {row.get("id"): row.get("alphaPercentile") for row in signals}
            for row in outcomes:
                if row.get("id") in by_id:
                    row["alphaPercentile"] = by_id[row["id"]]
        yield signals
    finally:
        for row, values in zip(signals, original):
            for field, value in zip(ALPHA_FIELDS, values):
                row[field] = value
        for row, value in zip(outcomes, original_outcomes):
            row["alphaPercentile"] = value


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


def rank_ic(signals: list[dict], outcomes: list[dict]) -> dict:
    """126-day rank IC per region for the alpha currently written on the signals.

    `portfolio_replay` does not compute this — `alpha_diagnostics` does, and it
    is a separate call. Reading it off the replay report returned an empty dict
    and quietly dropped the column that explains WHY a variant scored the way it
    did, which is most of the value of running variants at all.
    """
    diagnostics = PV.alpha_diagnostics(signals, outcomes)
    return {key: (row.get("rankIC") or {}).get("mean")
            for key, row in (diagnostics.get("regions") or {}).items()
            if key.endswith(":126")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--draws", type=int, default=100,
                        help="null draws per mode; screening needs fewer than publishing")
    parser.add_argument("--json", default=None)
    parser.add_argument("--only", default=None, help="comma-separated variant names")
    parser.add_argument("--ic-only", action="store_true",
                        help="rank IC per variant without the null; minutes rather than "
                             "an hour, and enough to see which sleeve moved the ordering")
    args = parser.parse_args(argv)

    cfg, _ = load_config()
    holdout = str((cfg.opportunity or {}).get("finalHoldoutStart") or "")
    if not holdout:
        print("ERROR: opportunity.finalHoldoutStart is not configured; refusing to "
              "run without a sealed holdout boundary.")
        return 1

    signals = HS.load(args.ledger_dir, HS.SIGNALS, prov_mod.REPLAY_VERSION,
                      project=HS.audit_projection)
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

    if args.ic_only:
        table = {}
        for name in names:
            started = time.time()
            with alpha_variant(kept, name, kept_outcomes) as variant_signals:
                table[name] = rank_ic(variant_signals, kept_outcomes)
            print(f"{name:20s} {table[name]}   ({time.time() - started:.0f}s)", flush=True)
        if args.json:
            Path(args.json).write_text(
                json.dumps({"holdoutStart": holdout, "rankIC126": table},
                           ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    results = {}
    for name in names:
        started = time.time()
        with alpha_variant(kept, name, kept_outcomes) as variant_signals:
            report = PV.portfolio_replay(variant_signals, kept_outcomes,
                                         cfg_lt=cfg.longterm, cfg_pf=cfg_pf,
                                         diagnostics=diagnostics)
            ic = rank_ic(variant_signals, kept_outcomes)
        results[name] = {
            "summary": summarize(report.get("portfolioReplay") or report),
            "rankIC126": ic,
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
