"""Scientific figure from retained estimates; no extra inference."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    res = json.loads((HERE / 'results/fixed.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True)
    for ax, horizon in zip(axes, ('126', '252')):
        for field, label, offset, color in [('increment', 'Added stock vs 20% ETF', -.12, '#17666e'),
                                            ('incrementNetOfRandom', 'After equal-exposure random control', .12, '#7855a0')]:
            cells = [res[horizon]['FULL'][str(k)][field] for k in range(1, 6)]
            means = np.array([c['mean'] for c in cells])*100
            bounds = np.array([c['ci'] or [np.nan, np.nan] for c in cells])*100
            y = np.arange(1, 6)+offset
            # Draw percentile endpoints directly; a percentile interval can exclude its point estimate.
            ax.hlines(y, bounds[:, 0], bounds[:, 1], color=color, linewidth=1.8)
            ax.scatter(means, y, color=color, s=32, label=label, zorder=3)
        ax.axvline(0, color='#53616e', linewidth=1)
        ax.set_title(f'{horizon} KR sessions', weight='bold')
        ax.set_xlabel('Incremental net contribution (percentage points)')
        ax.grid(axis='x', color='#e5e9eb')
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_yticks(range(1, 6), [f'Rank {k}' for k in range(1, 6)])
    axes[0].invert_yaxis()
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', ncol=2, frameon=False, fontsize=9)
    fig.suptitle('Korea S2: what did each additional rank contribute?', weight='bold')
    fig.text(.5, .085, 'Same decision dates; 20% per stock; residual KODEX 200. Dated transaction costs deducted.\n95% moving-block intervals. Outcome-exposed history; not prospective evidence.', ha='center', fontsize=8, color='#53616e')
    fig.tight_layout(rect=[0, .15, 1, .94])
    for ext in ('png', 'svg'):
        fig.savefig(HERE / f'rank-increments.{ext}', dpi=180, facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    main()
