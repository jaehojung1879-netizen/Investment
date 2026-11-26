"""MCT-v1 monthly decision panel: signals (point-in-time) and, separately, outcomes.

`signals()` reads no return and no future value. Every signal at decision month-end M uses only values whose registered
effective date is on or before M:

* PE, HIGH_PE      Shiller P(M) / E(latest quarter-end q <= M-4), HIGH when above the mean of the 60 PRIOR recorded PE
                   (>= 54 valid) -- MVMA-v1's frozen rule, reused unchanged (features.valuation_cheap).
* CAPE, HIGH_CAPE  real P(M) [deflated by CPI(M-1)] over the mean real E of the 120 months ending at q; HIGH when above
                   the mean of the 120 PRIOR recorded CAPE values (>= 108 valid).
* EARN_DOWN        latest SPF survey usable at M (survey of quarter Q usable from the END of Q's last month) whose
                   fixed-target growth revision rev_s = log(CPROF5_s/CPROF2_s) - log(CPROF6_{s-1}/CPROF3_{s-1}) < 0,
                   i.e. expected profit growth from quarter s to s+3 was cut between consecutive surveys.
* CREDIT_STRESS    spread = BAA - GS10. 2007-01..2024-08: the ALFRED vintage in force the day before M (MVMA-v1
                   ledger; missing when the legs disagree on month). Before 2007: current vintage at M-1 (monthly
                   averages publish early in the next month; 207/208 months equal ALFRED where both exist, the
                   exception a 1bp revision). Stress when above
                   the type-7 P75 of the 60 PRIOR values and wider than 3 months earlier -- MVMA-v1's frozen rule.
* TREND_DOWN       market total-return index (Fama-French Mkt-RF + RF) below its 10-month mean at M (monthly analogue
                   of the SMA200 leg of the sealed KR FAST layer); VOL_HIGH: 6-month realised volatility above the
                   expanding median of its own history (>= 60 values). Past returns only.

`outcomes()` is the only place a future value is read, and only the execution script calls it.
"""
from __future__ import annotations

import csv
import gzip
import io
import math
import zipfile
from pathlib import Path

import numpy as np

from research.market_valuation_macro_overlay_v1 import features as F

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
MVMA = HERE.parent / "market_valuation_macro_overlay_v1"
FIRST, LAST = "1960-01", "2026-09"
CAPE_WINDOW, CAPE_HISTORY, CAPE_MIN_VALID = 120, 120, 108
TREND_MONTHS, VOL_MONTHS, VOL_MIN_HISTORY = 10, 6, 60


def months(first: str = FIRST, last: str = LAST) -> list[str]:
    a = int(first[:4]) * 12 + int(first[5:]) - 1
    b = int(last[:4]) * 12 + int(last[5:]) - 1
    return [f"{i // 12:04d}-{i % 12 + 1:02d}" for i in range(a, b + 1)]


def shift(month: str, k: int) -> str:
    i = int(month[:4]) * 12 + int(month[5:]) - 1 + k
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def _gz_text(name: str) -> str:
    return gzip.decompress((RAW / name).read_bytes()).decode("utf-8", "replace")


def load_shiller() -> dict[str, dict]:
    out = {}
    for row in csv.DictReader((MVMA / "data/shiller-monthly-20240904.csv").open()):
        if row["partialMonth"] == "1":
            continue
        out[row["month"]] = {k: (float(row[k]) if row[k] else None) for k in ("P", "E", "CPI")}
    return out


def load_fred_monthly(name: str) -> dict[str, float]:
    out = {}
    for line in _gz_text(name).strip().splitlines()[1:]:
        d, _, v = line.partition(",")
        if v not in ("", "."):
            out[d[:7]] = float(v)
    return out


def load_fred_daily_month_end(name: str) -> dict[str, float]:
    out = {}
    for line in _gz_text(name).strip().splitlines()[1:]:
        d, _, v = line.partition(",")
        if v not in ("", "."):
            out[d[:7]] = float(v)          # rows are ascending: the last valued day of the month wins
    return out


def load_alfred_spread() -> dict[str, float | None]:
    """MVMA-v1's ALFRED as-of ledgers (2007-01..2024-08): the spread actually visible the day before each decision;
    None when the two legs' latest observations are for different months (BAA stalled 2016-11..2017-02)."""
    base = MVMA / "data"
    baa = {r["decisionDate"][:7]: r for r in csv.DictReader((base / "alfred-BAA-asof-decisions.csv").open())}
    gs = {r["decisionDate"][:7]: r for r in csv.DictReader((base / "alfred-GS10-asof-decisions.csv").open())}
    out = {}
    for m, b in baa.items():
        g = gs[m]
        same = b["observationDate"][:7] == g["observationDate"][:7]
        out[m] = float(b["value"]) - float(g["value"]) if same else None
    return out


def load_spf() -> list[dict]:
    import openpyxl  # noqa: PLC0415
    raw = gzip.decompress((RAW / "spf-median-cprof-level.xlsx.gz").read_bytes())
    rows = list(openpyxl.load_workbook(io.BytesIO(raw), read_only=True)["Median_Level"].iter_rows(values_only=True))
    head = rows[0]
    out = []
    for r in rows[1:]:
        rec = dict(zip(head, r))
        vals = {k: (float(rec[k]) if isinstance(rec[k], (int, float)) else None) for k in ("CPROF2", "CPROF3", "CPROF5", "CPROF6")}
        out.append({"year": int(rec["YEAR"]), "quarter": int(rec["QUARTER"]), **vals})
    return out


def spf_revisions(spf: list[dict]) -> dict[str, dict]:
    """{effective month: {survey, rev}} with the survey of quarter Q effective at the end of Q's last month."""
    out = {}
    for prev, cur in zip(spf, spf[1:]):
        eff = f"{cur['year']:04d}-{cur['quarter'] * 3:02d}"
        ok = all(v is not None and v > 0 for v in (cur["CPROF5"], cur["CPROF2"], prev["CPROF6"], prev["CPROF3"]))
        rev = (math.log(cur["CPROF5"] / cur["CPROF2"]) - math.log(prev["CPROF6"] / prev["CPROF3"])) if ok else None
        out[eff] = {"survey": f"{cur['year']}Q{cur['quarter']}", "rev": rev}
    return out


def load_ff() -> dict[str, tuple[float, float]]:
    with zipfile.ZipFile(io.BytesIO(gzip.decompress((RAW / "ff-research-data-factors.zip.gz").read_bytes()))) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    out = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 5 and len(parts[0]) == 6 and parts[0].isdigit():
            key = f"{parts[0][:4]}-{parts[0][4:]}"
            if key in out:          # the annual block repeats 4-digit keys only, so this never fires on it
                break
            out[key] = (float(parts[1]) / 100.0, float(parts[4]) / 100.0)
    return out


def _prior_mean_high(values: list[float | None], i: int, window: int, min_valid: int) -> bool | None:
    if i < window or values[i] is None:
        return None
    sample = [v for v in values[i - window:i] if v is not None]
    if len(sample) < min_valid:
        return None
    return values[i] > sum(sample) / len(sample)


def signals(first: str = FIRST, last: str = "2024-08") -> list[dict]:
    """One row per decision month-end. Reads no future value (tested by truncation invariance)."""
    ms = months(first, last)
    sh = load_shiller()
    baa, gs10 = load_fred_monthly("fred-BAA.csv.gz"), load_fred_monthly("fred-GS10.csv.gz")
    spf = spf_revisions(load_spf())
    alfred = load_alfred_spread()
    ff = load_ff()

    pe, cape, spread = [], [], []
    rows = []
    for m in ms:
        y, mo = int(m[:4]), int(m[5:])
        q = F.shiller_earnings_effective_month(F.month_index(y, mo))
        qy, qm = F.month_from_index(q)
        qkey = f"{qy:04d}-{qm:02d}"
        p = (sh.get(m) or {}).get("P")
        pe.append(F.price_to_earnings(p, (sh.get(qkey) or {}).get("E")))
        cpi_prev = (sh.get(shift(m, -1)) or {}).get("CPI")
        real_e = []
        for k in range(CAPE_WINDOW):
            j = shift(qkey, -k)
            rec = sh.get(j) or {}
            if rec.get("E") is not None and rec.get("CPI"):
                real_e.append(rec["E"] / rec["CPI"])
        cape.append((p / cpi_prev) / (sum(real_e) / len(real_e))
                    if p and cpi_prev and len(real_e) == CAPE_WINDOW and sum(real_e) > 0 else None)
        prev = shift(m, -1)
        if m in alfred:                                    # 2007-01..2024-08: the exact real-time vintage
            spread.append(alfred[m])
        else:                                              # earlier: current vintage, verified unrevised, lag 1
            spread.append(baa[prev] - gs10[prev] if prev in baa and prev in gs10 else None)
        latest = max((k for k in spf if k <= m), default=None)
        rev = spf[latest]["rev"] if latest else None
        rows.append({"month": m, "pe": pe[-1], "cape": cape[-1], "spread": spread[-1],
                     "spfSurvey": spf[latest]["survey"] if latest else None, "spfRevision": rev})

    index, rets = [], []
    level = 1.0
    for m in ms:
        if m in ff:
            mkt = ff[m][0] + ff[m][1]
            level *= 1 + mkt
            rets.append(mkt)
        else:
            rets.append(None)
        index.append(level if m in ff else None)
    vols = []
    for i, row in enumerate(rows):
        row["highPe"] = (lambda c: None if c is None else not c)(F.valuation_cheap(pe, i))
        row["highCape"] = _prior_mean_high(cape, i, CAPE_HISTORY, CAPE_MIN_VALID)
        row["earnDown"] = None if row["spfRevision"] is None else row["spfRevision"] < 0
        row["creditStress"] = F.credit_stress(spread, i)
        window = index[i - TREND_MONTHS + 1:i + 1] if i >= TREND_MONTHS - 1 else []
        row["trendDown"] = (index[i] < sum(window) / len(window)) if window and all(v is not None for v in window) else None
        r6 = rets[i - VOL_MONTHS + 1:i + 1] if i >= VOL_MONTHS - 1 else []
        vol = float(np.std(r6, ddof=1)) if r6 and all(v is not None for v in r6) else None
        vols.append(vol)
        hist = [v for v in vols[:-1] if v is not None]
        row["volHigh"] = (vol > float(np.median(hist))) if vol is not None and len(hist) >= VOL_MIN_HISTORY else None
        parts = (row["highPe"], row["earnDown"], row["creditStress"])
        row["vulnTriple"] = None if None in parts else all(parts)
    return rows


def outcomes(rows: list[dict], horizons=(1, 3, 6, 12)) -> dict:
    """Forward market excess return from the end of month M over the next h months (compounded market minus
    compounded risk-free). The ONLY future read in this package; called by the execution script after the lock."""
    ff = load_ff()
    out = {}
    for h in horizons:
        vals = []
        for r in rows:
            fwd = [shift(r["month"], k) for k in range(1, h + 1)]
            if all(f in ff for f in fwd):
                mkt = np.prod([1 + ff[f][0] + ff[f][1] for f in fwd])
                rf = np.prod([1 + ff[f][1] for f in fwd])
                vals.append(float(mkt - rf))
            else:
                vals.append(None)
        out[h] = vals
    return out
