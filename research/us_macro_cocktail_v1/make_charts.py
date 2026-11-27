"""Dependency-free SVG charts from results/ and the frozen panel (no matplotlib in this environment)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cocktail as C  # noqa: E402

OUT = C.HERE / "results"
PALETTE = ["#1f5fbf", "#d1495b", "#2a9d8f", "#e9a03b", "#7b4fb3", "#6c757d", "#111111", "#c2185b"]
W, H, L, R, T, B = 960, 420, 60, 230, 30, 40


def svg_lines(series: dict, title: str, log: bool, ylabel: str, zero: bool = False) -> str:
    idx = sorted(set().union(*[s.index for s in series.values()]))
    t0, t1 = idx[0], idx[-1]
    vals = [v for s in series.values() for v in s.values]
    f = (lambda v: math.log10(v)) if log else (lambda v: v)
    lo, hi = min(f(v) for v in vals), max(f(v) for v in vals)
    pad = (hi - lo) * 0.05
    lo, hi = lo - pad, hi + pad

    def x(t):
        return L + (W - L - R) * (t - t0).days / (t1 - t0).days

    def y(v):
        return T + (H - T - B) * (1 - (f(v) - lo) / (hi - lo))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="sans-serif" font-size="11">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>', f'<text x="{L}" y="18" font-size="13" font-weight="bold">{title}</text>',
           f'<line x1="{L}" y1="{H - B}" x2="{W - R}" y2="{H - B}" stroke="#999"/>', f'<line x1="{L}" y1="{T}" x2="{L}" y2="{H - B}" stroke="#999"/>']
    for yr in range(t0.year + 1, t1.year + 1):
        t = pd.Timestamp(f"{yr}-01-01")
        if (yr - t0.year) % 2 == 0 or (t1.year - t0.year) < 12:
            out.append(f'<line x1="{x(t):.1f}" y1="{T}" x2="{x(t):.1f}" y2="{H - B}" stroke="#eee"/>'
                       f'<text x="{x(t):.1f}" y="{H - B + 14}" text-anchor="middle" fill="#555">{yr}</text>')
    ticks = [1, 1.5, 2, 3, 4, 5, 6, 8, 10] if log else [lo + (hi - lo) * k / 5 for k in range(6)]
    for v in ticks:
        if log and not (lo <= math.log10(v) <= hi):
            continue
        label = f"{v:g}x" if log else f"{v:.2f}"
        out.append(f'<line x1="{L}" y1="{y(v):.1f}" x2="{W - R}" y2="{y(v):.1f}" stroke="#f0f0f0"/>'
                   f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#555">{label}</text>')
    if zero:
        out.append(f'<line x1="{L}" y1="{y(0):.1f}" x2="{W - R}" y2="{y(0):.1f}" stroke="#444" stroke-dasharray="4 3"/>')
    out.append(f'<text x="14" y="{(H) / 2}" transform="rotate(-90 14 {H / 2})" fill="#555">{ylabel}</text>')
    for k, (name, s) in enumerate(series.items()):
        col = PALETTE[k % len(PALETTE)]
        pts = " ".join(f"{x(t):.1f},{y(v):.1f}" for t, v in s.items())
        out.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.6" points="{pts}"/>')
        out.append(f'<rect x="{W - R + 12}" y="{T + 16 * k}" width="12" height="3" fill="{col}"/>'
                   f'<text x="{W - R + 30}" y="{T + 16 * k + 5}">{name} ({s.iloc[-1]:.2f})</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    m = pd.read_csv(OUT / "primary-monthly-nav-usd.csv", index_col=0, parse_dates=True)
    assets = {a: m[f"ASSET_{a}"] for a in ["SPY", "QQQ", "IEF", "TLT", "GLD", "UUP", "BIL"]}
    (OUT / "chart-primary-asset-paths.svg").write_text(svg_lines(assets, "Asset total-return paths, USD, 2015-12-31 = 1 (month-end)", True, "growth of 1 (log)"))
    strat = {k: m[k] for k in ["S1_SPY", "S4_BALANCED", "S3_6040", "D1_TREND_SIGN", "D3_STATE_RULES", "D5_TREE_SIGN", "D6_FORECAST_VOL_SLEEVE"]}
    (OUT / "chart-primary-strategy-paths.svg").write_text(svg_lines(strat, "Strategy NAV net of cost, USD, primary window", True, "growth of 1 (log)"))
    p = C.build_panel()
    r = p.ret.loc["2007-06-01":"2026-10-30"]
    corr = {f"SPY-{b}": r["SPY"].rolling(126).corr(r[b]).dropna().resample("W-FRI").last().dropna() for b in ("IEF", "GLD", "UUP")}
    (OUT / "chart-rolling-126d-correlations.svg").write_text(svg_lines(corr, "126-session rolling correlation of daily TR returns", False, "correlation", zero=True))


if __name__ == "__main__":
    main()
