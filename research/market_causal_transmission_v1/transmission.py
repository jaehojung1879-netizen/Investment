"""MCT-v1 H1: FOMC shock origin and transmission, by local projection.

Shocks (month t): Jarocinski-Karadi MP_pm and CBI_pm, scaled by their own standard deviation over months with a
non-zero value (descriptive scaling; a coefficient is the response to a one-SD shock). Controls are pre-shock:
the market excess return of month t-1, the cumulative market excess return over t-12..t-1, and the change in GS10
in month t-1.

EXPLANATION vs PREDICTION are separate outputs, never pooled:
* explanation  -- the market excess return of the shock month t itself. JK classify shocks by the sign of the S&P 500
                  move inside the 30-minute window, so a same-month response is partly an identity, not a finding.
* prediction   -- outcomes measured strictly AFTER month t (t+1..t+h), the only part that could carry investment value.

Channels (proxies, not a Campbell-Shiller VAR decomposition):
* cash-flow expectations -- SPF fixed-target profit-growth revision at the first survey taken after month t (quarter
  starting after t), and the sum of the next four revisions;
* discount rate          -- change in the 10-year TIPS yield (DFII10) and breakeven (T10YIE), month-end t to t+h
                            (2003-02 onward);
* risk premium           -- change in the GZ excess bond premium, t to t+h (EBP is a full-sample residual: outcome only);
* realised earnings      -- log Shiller E(t+12) / E(t).
"""
from __future__ import annotations

import csv
import gzip
import io

import numpy as np

from . import models as M
from . import panel as P

FIRST, LAST = "1990-02", "2024-01"
HORIZONS = (1, 3, 6, 12)


def load_jk() -> dict[str, tuple[float, float]]:
    text = gzip.decompress((P.RAW / "jk-shocks-monthly.csv.gz").read_bytes()).decode()
    return {f"{int(r['year']):04d}-{int(r['month']):02d}": (float(r["MP_pm"]), float(r["CBI_pm"]))
            for r in csv.DictReader(io.StringIO(text))}


def load_bs() -> dict[str, tuple[float, float]]:
    import openpyxl  # noqa: PLC0415
    raw = gzip.decompress((P.RAW / "bauer-swanson-mps.xlsx.gz").read_bytes())
    rows = list(openpyxl.load_workbook(io.BytesIO(raw), read_only=True)["Monthly (update 2023)"].iter_rows(values_only=True))
    out = {}
    for r in rows[1:]:
        if isinstance(r[0], (int, float)) and isinstance(r[2], (int, float)) and isinstance(r[3], (int, float)):
            out[f"{int(r[0]):04d}-{int(r[1]):02d}"] = (float(r[2]), float(r[3]))
    return out


def load_ebp() -> dict[str, float]:
    text = gzip.decompress((P.RAW / "gz-ebp.csv.gz").read_bytes()).decode()
    return {r["date"][:7]: float(r["ebp"]) for r in csv.DictReader(io.StringIO(text))}


def shock_panel() -> list[dict]:
    """Pre-event information only: shocks and pre-shock controls. No outcome."""
    jk, bs, ff = load_jk(), load_bs(), P.load_ff()
    gs10 = P.load_fred_monthly("fred-GS10.csv.gz")
    rows = []
    for m in P.months(FIRST, LAST):
        mp, cbi = jk.get(m, (0.0, 0.0))
        prev = P.shift(m, -1)
        past = [P.shift(m, -k) for k in range(1, 13)]
        rows.append({
            "month": m, "MP": mp, "CBI": cbi, "MPS": bs.get(m, (None, None))[0], "MPS_ORTH": bs.get(m, (None, None))[1],
            "ctlRet1": ff[prev][0] if prev in ff else None,
            "ctlRet12": (float(np.prod([1 + ff[p][0] + ff[p][1] for p in past]) - np.prod([1 + ff[p][1] for p in past]))
                         if all(p in ff for p in past) else None),
            "ctlDgs10": (gs10[prev] - gs10[P.shift(prev, -1)]) if prev in gs10 and P.shift(prev, -1) in gs10 else None,
        })
    return rows


def outcome_panel(rows: list[dict]) -> dict:
    """Every future value H1 reads. Called only after the execution lock."""
    ff, ebp = P.load_ff(), load_ebp()
    dfii, bei = P.load_fred_daily_month_end("fred-DFII10.csv.gz"), P.load_fred_daily_month_end("fred-T10YIE.csv.gz")
    spf = P.spf_revisions(P.load_spf())
    sh = P.load_shiller()
    survey_after = {}
    effective = sorted(spf)
    for r in rows:
        m = r["month"]
        # the survey of quarter Q is effective at the end of Q's last month; "taken after t" = Q starts after t
        later = [e for e in effective if P.shift(e, -2) > m]
        survey_after[m] = later[:4]
    out = {"explain": [], "pred": {h: [] for h in HORIZONS}, "spfNext": [], "spfNext4": [],
           "dReal": {h: [] for h in HORIZONS}, "dBei": {h: [] for h in HORIZONS}, "dEbp": {h: [] for h in HORIZONS},
           "earn12": []}
    for r in rows:
        m = r["month"]
        out["explain"].append(ff[m][0] if m in ff else None)
        for h in HORIZONS:
            fwd = [P.shift(m, k) for k in range(1, h + 1)]
            out["pred"][h].append(float(np.prod([1 + ff[f][0] + ff[f][1] for f in fwd]) - np.prod([1 + ff[f][1] for f in fwd]))
                                  if all(f in ff for f in fwd) else None)
            end = P.shift(m, h)
            out["dReal"][h].append(dfii[end] - dfii[m] if m in dfii and end in dfii else None)
            out["dBei"][h].append(bei[end] - bei[m] if m in bei and end in bei else None)
            out["dEbp"][h].append(ebp[end] - ebp[m] if m in ebp and end in ebp else None)
        nxt = survey_after[m]
        revs = [spf[e]["rev"] for e in nxt]
        out["spfNext"].append(revs[0] if revs and revs[0] is not None else None)
        out["spfNext4"].append(float(sum(revs)) if len(revs) == 4 and all(v is not None for v in revs) else None)
        e0, e12 = (sh.get(m) or {}).get("E"), (sh.get(P.shift(m, 12)) or {}).get("E")
        out["earn12"].append(float(np.log(e12 / e0)) if e0 and e12 and e0 > 0 and e12 > 0 else None)
    return out


CONTROLS = ["ctlRet1", "ctlRet12", "ctlDgs10"]


def local_projection(rows: list[dict], y: list[float | None], shocks: list[str], lag: int, scale: dict) -> dict | None:
    keep = [i for i, r in enumerate(rows)
            if y[i] is not None and all(r[k] is not None for k in shocks + CONTROLS)]
    if len(keep) < 60:
        return None
    X = np.array([[rows[i][k] / scale.get(k, 1.0) for k in shocks] + [rows[i][k] for k in CONTROLS] for i in keep])
    fit = M.ols_hac(np.array([y[i] for i in keep]), X, lag, shocks + CONTROLS)
    out = {"n": fit["n"], "r2": fit["r2"], "lag": lag, "first": rows[keep[0]]["month"], "last": rows[keep[-1]]["month"],
           "coef": {k: fit["coef"][k] for k in shocks}}
    if "MP" in shocks and "CBI" in shocks:
        out["mpMinusCbi"] = M.linear_contrast(fit, shocks + CONTROLS, {"MP": 1.0, "CBI": -1.0})
    return out


def shock_scale(rows: list[dict], keys: list[str]) -> dict:
    return {k: float(np.std([r[k] for r in rows if r[k] not in (None, 0.0)], ddof=1)) for k in keys}
