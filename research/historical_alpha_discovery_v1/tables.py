"""Export review tables from this study's saved results; no new return computation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def build(directory):
    directory = Path(directory)
    summary = json.loads((directory / "summary.json").read_text())
    blocks = pd.read_json(directory / "blocks.json")
    rows, trades = [], []
    keys = ["analysisWindow", "sample", "horizon", "costMultiplier", "book"]
    for portfolio in summary["portfolios"]:
        mask = pd.Series(True, index=blocks.index)
        for key in keys:
            mask &= blocks[key].eq(portfolio[key])
        group = blocks[mask].sort_values("entry")
        rows.append(
            {
                **{k: portfolio[k] for k in keys + ["complete"]},
                "scheduledBlocks": len(group),
                "pricedBlocks": int(group.netReturn.notna().sum()),
                "meanStockCount": float(group.selected.map(len).mean()),
                "meanBlockEntryCostFraction": float(group.entryFraction.mean()),
                "meanBlockExitCostFraction": float(group.exitFraction.mean()),
                "meanBlockGrossNotionalTurnover": float(group.grossTurnover.mean()),
                **(portfolio["metrics"] or {}),
            }
        )
        previous = set()
        for i, (_, block) in enumerate(group.iterrows()):
            selected = set(block.selected)
            trades.append(
                {
                    **{k: portfolio[k] for k in keys},
                    "entry": block.entry,
                    "initialBuild": i == 0,
                    "initialNames": len(selected) if i == 0 else 0,
                    "newNamesAfterInitial": len(selected - previous) if i > 0 else 0,
                    "departingNames": len(previous - selected) if i > 0 else 0,
                    "sameNamesForcedLiquidationReentry": len(previous & selected) if i > 0 else 0,
                    "priceable": pd.notna(block.netReturn),
                    "note": "Counts are name-selection diagnostics. Unpriceable trades are not claimed executed. No-retarget band not tested.",
                }
            )
            previous = selected
    pd.DataFrame(rows).to_csv(directory / "portfolio-summary.csv", index=False, float_format="%.12g")
    pd.DataFrame(trades).to_csv(directory / "trade-decomposition.csv", index=False)


if __name__ == "__main__":
    build(Path(__file__).resolve().parent / "results")
