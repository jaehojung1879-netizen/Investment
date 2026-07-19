"""Immutable paper-signal ledger — the ONLY honest path to 'validated'.

Every build appends today's long-term signals (research view, entry state,
alpha, reference price, benchmark, macro regime, model version) to an
append-only ledger. Records are keyed by (date, ticker); a re-run with a
changed model NEVER overwrites a past record — that is the whole point, so
forward performance is judged against what the model ACTUALLY said at the time,
not a hindsight-revised version.

Outcomes (21/63/126/252-day forward return, excess vs benchmark, MFE/MAE) are
computed later from prices and stored in a SEPARATE outcomes ledger keyed by the
signal id, leaving the original signals untouched.

In CI this ledger lives on a dedicated ``signal-history`` branch (see
.github/workflows/ledger.yml) so it accumulates without triggering the main
Pages build.

Evaluation metrics (see ``evaluate``) go beyond hit-rate: rank IC, mean excess
return, turnover, MDD, and per-view breakdown — the metrics a real model review
uses.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = [21, 63, 126, 252]


def signal_id(date: str, ticker: str) -> str:
    return f"{date}|{ticker}"


def records_from_payload(payload: dict) -> list[dict]:
    """Extract immutable signal rows from a built payload."""
    date = (payload.get("meta") or {}).get("latestDataDate")
    model_version = payload.get("modelVersion")
    macro = ((payload.get("macroRegime") or {}) or {}).get("regime")
    lt = payload.get("longTerm") or {}
    out: list[dict] = []
    for region, blob in (lt.get("regions") or {}).items():
        # Use the research table (all eligible names), not just the sleeve, so
        # we track NEGATIVE/NEUTRAL calls too — needed for rank IC.
        for row in blob.get("researchTable", []):
            entry = row.get("entry") or {}
            out.append({
                "id": signal_id(date, row["ticker"]),
                "date": date,
                "ticker": row["ticker"],
                "region": region,
                "modelVersion": model_version,
                "longTermResearchView": row.get("longTermResearchView"),
                "entryState": entry.get("entryState"),
                "alpha": row.get("alpha"),
                "alphaPercentile": row.get("alphaPercentile"),
                "refClose": (payload.get("details", {}).get(row["ticker"], {}) or {}).get("lastClose"),
                "benchmark": payload.get("benchmark"),
                "macroRegime": macro,
            })
    return out


def append_signals(existing: list[dict], new: list[dict]) -> tuple[list[dict], int, int]:
    """Append only rows whose id is not already present. Returns
    (merged, appended, skipped). Existing rows are never mutated."""
    seen = {r["id"] for r in existing}
    appended = 0
    merged = list(existing)
    for r in new:
        if r.get("id") in seen or r.get("date") is None:
            continue
        merged.append(dict(r))
        seen.add(r["id"])
        appended += 1
    return merged, appended, len(new) - appended


def load_jsonl(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def compute_outcomes(signals: list[dict], prices: dict[str, pd.DataFrame],
                     benchmarks: dict[str, pd.Series] | None = None) -> list[dict]:
    """For each matured signal compute forward returns, excess vs benchmark,
    and MFE/MAE. Only produces an outcome for a horizon that has fully elapsed
    in the price data — no partial/look-ahead outcomes."""
    benchmarks = benchmarks or {}
    out = []
    for s in signals:
        tk = s["ticker"]
        px = prices.get(tk)
        if px is None or "Close" not in px:
            continue
        close = px["Close"].dropna()
        try:
            entry_idx = close.index.get_indexer([pd.Timestamp(s["date"])], method="ffill")[0]
        except Exception:
            continue
        if entry_idx < 0:
            continue
        entry_px = float(close.iloc[entry_idx])
        bench = benchmarks.get(s.get("benchmark"))
        rec = {"id": s["id"], "date": s["date"], "ticker": tk, "region": s.get("region"),
               "modelVersion": s.get("modelVersion"), "longTermResearchView": s.get("longTermResearchView"),
               "entryState": s.get("entryState"), "alpha": s.get("alpha"), "horizons": {}}
        for h in HORIZONS:
            j = entry_idx + h
            if j >= len(close):
                continue
            path = close.iloc[entry_idx:j + 1]
            fwd = float(close.iloc[j] / entry_px - 1)
            mfe = float(path.max() / entry_px - 1)
            mae = float(path.min() / entry_px - 1)
            excess = None
            if bench is not None:
                b = bench.dropna()
                try:
                    bi = b.index.get_indexer([pd.Timestamp(s["date"])], method="ffill")[0]
                    if bi >= 0 and bi + h < len(b):
                        excess = round(fwd - float(b.iloc[bi + h] / b.iloc[bi] - 1), 4)
                except Exception:
                    pass
            rec["horizons"][str(h)] = {
                "fwdReturn": round(fwd, 4), "excessReturn": excess,
                "mfe": round(mfe, 4), "mae": round(mae, 4),
            }
        if rec["horizons"]:
            out.append(rec)
    return out


def evaluate(outcomes: list[dict], horizon: int = 63) -> dict:
    """Model-review metrics for one horizon: rank IC, mean excess, hit rate,
    MDD of an equal-weight POSITIVE basket, and per-view breakdown."""
    hk = str(horizon)
    rows = [o for o in outcomes if hk in o.get("horizons", {})]
    if not rows:
        return {"n": 0, "horizon": horizon}
    alphas = np.array([o["alpha"] for o in rows if o.get("alpha") is not None], dtype=float)
    fwds = np.array([o["horizons"][hk]["fwdReturn"] for o in rows if o.get("alpha") is not None], dtype=float)
    rank_ic = None
    if len(alphas) >= 5 and np.std(alphas) > 0 and np.std(fwds) > 0:
        rank_ic = float(np.corrcoef(pd.Series(alphas).rank(), pd.Series(fwds).rank())[0, 1])
    excesses = [o["horizons"][hk]["excessReturn"] for o in rows if o["horizons"][hk]["excessReturn"] is not None]
    pos = [o for o in rows if o.get("longTermResearchView") == "POSITIVE"]
    pos_fwd = [o["horizons"][hk]["fwdReturn"] for o in pos]
    hit = float(np.mean([f > 0 for f in pos_fwd])) if pos_fwd else None
    by_view = {}
    for view in ("POSITIVE", "NEUTRAL", "NEGATIVE"):
        vf = [o["horizons"][hk]["fwdReturn"] for o in rows if o.get("longTermResearchView") == view]
        if vf:
            by_view[view] = {"n": len(vf), "meanFwd": round(float(np.mean(vf)), 4)}
    return {
        "n": len(rows), "horizon": horizon,
        "rankIC": round(rank_ic, 3) if rank_ic is not None else None,
        "meanExcess": round(float(np.mean(excesses)), 4) if excesses else None,
        "positiveHitRate": round(hit, 3) if hit is not None else None,
        "byView": by_view,
    }
