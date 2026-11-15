"""Export a standard research figure of the longest supported NAV segment."""
from pathlib import Path
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from research.us_topk_market_cap_v1.inputs import read


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    records = read(args.output / "nav-segments.json")
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
    colors = {"equal_company": "#147d92", "company_market_cap": "#c27320"}
    for ax, k in zip(axes, (100, 10, 5)):
        for mode in ("equal_company", "company_market_cap"):
            group = next(r for r in records if r["pool"] == "CORRECTED_FINANCIAL_POOL" and r["k"] == k and r["weighting"] == mode)
            # Longest by calendar support, never by realized performance.
            segment = max(group["segments"], key=lambda r: r["intervals"])
            days = pd.to_datetime([segment["first_entry"], *[r["date"] for r in segment["daily"]]])
            nav = [1., *[r["nav"] for r in segment["daily"]]]
            ax.plot(days, nav, color=colors[mode], label="Equal weight" if mode == "equal_company" else "Reported cap weight", lw=1.6)
            if mode == "equal_company":
                ax.plot(days, [1., *[r["spy_nav"] for r in segment["daily"]]], color="#526070", label="SPY total return", lw=1.4)
        ax.set_title(f"Pool Top {k}")
        ax.grid(alpha=.2)
        ax.spines[["right", "top"]].set_visible(False)
        ax.tick_params(axis="x", labelrotation=30, labelsize=8)
    axes[0].set_ylabel("NAV, initial capital = 1")
    axes[-1].legend(fontsize=8, loc="upper left")
    fig.suptitle("Corrected financial pool / reported common-cap estimate", fontsize=12)
    fig.text(.5, .005, "2023-04-17 to 2025-03-17 | weekly rebalance, daily marks, trading costs | separate 2026 segment omitted here; no gap stitching", ha="center", fontsize=7)
    fig.tight_layout(rect=[0, .04, 1, .92])
    fig.savefig(args.output / "nav-main-segment.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
