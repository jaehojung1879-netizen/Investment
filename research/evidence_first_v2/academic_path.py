"""Run the pre-registered profitability translation test (academic-path-protocol.json).

python research/evidence_first_v2/academic_path.py [--fetch]
--fetch downloads the five Ken French CSV zips once into data/french/ with a SHA-256 manifest;
without it the frozen files are used. Output: results/academic-path.json.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "academic-path-protocol.json"
STORE = HERE / "data" / "french"
OUT = HERE / "results" / "academic-path.json"
UA = "Mozilla/5.0 (research fetch; evidence-first-v2)"


def fetch() -> None:
    proto = json.loads(PROTOCOL.read_text())
    STORE.mkdir(parents=True, exist_ok=True)
    man = {"fetchedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "files": {}}
    for key, url in proto["data"]["files"].items():
        for i in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90) as r:
                    body = r.read()
                break
            except Exception:
                time.sleep(5 * (i + 1))
        name = url.rsplit("/", 1)[1]
        (STORE / name).write_bytes(body)
        man["files"][key] = {"url": url, "file": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    (STORE / "manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")


def _read_zip(key: str) -> str:
    man = json.loads((STORE / "manifest.json").read_text())["files"][key]
    body = (STORE / man["file"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != man["sha256"]:
        raise RuntimeError(f"FRENCH_FILE_CHANGED {key}")
    z = zipfile.ZipFile(io.BytesIO(body))
    return z.read(z.namelist()[0]).decode("latin-1")


def first_monthly_table(text: str, title_hint: str | None = None) -> pd.DataFrame:
    """First block of YYYYMM rows after a header line (French files list value-weighted monthly first)."""
    lines = text.splitlines()
    start = 0
    if title_hint:
        start = next(i for i, ln in enumerate(lines) if title_hint.lower() in ln.lower())
    hdr = next(i for i in range(start, len(lines)) if lines[i].strip().startswith(",") or re.match(r"^\s*,", lines[i]))
    cols = [c.strip() for c in lines[hdr].split(",")[1:]]
    rows = []
    for ln in lines[hdr + 1:]:
        parts = [p.strip() for p in ln.split(",")]
        if not parts or not re.fullmatch(r"\d{6}", parts[0]):
            break
        rows.append([parts[0]] + [float(x) for x in parts[1:len(cols) + 1]])
    df = pd.DataFrame(rows, columns=["ym"] + cols).set_index("ym")
    df.index = pd.PeriodIndex([f"{s[:4]}-{s[4:]}" for s in df.index], freq="M")
    df = df.replace([-99.99, -999.0], np.nan) / 100.0
    return df


def series() -> dict[str, pd.Series]:
    ff3 = first_monthly_table(_read_zip("FF3"))
    mkt = ff3["Mkt-RF"] + ff3["RF"]
    op25 = first_monthly_table(_read_zip("ME_OP_25"))
    opq = first_monthly_table(_read_zip("OP_quantiles"))
    bm25 = first_monthly_table(_read_zip("ME_BM_25"))
    pr25 = first_monthly_table(_read_zip("ME_PRIOR_25"))

    def col(df, *names):
        for n in names:
            if n in df.columns:
                return df[n]
        raise KeyError(f"{names} not in {list(df.columns)}")
    return {"MKT": mkt, "BIG_HI_OP": col(op25, "BIG HiOP", "ME5 OP5"), "OP_HI_ALL_SIZES": col(opq, "Hi 20"),
            "BIG_VALUE": col(bm25, "BIG HiBM", "ME5 BM5"), "BIG_WINNERS": col(pr25, "BIG HiPRIOR", "ME5 PRIOR5")}


def nw_t(x: np.ndarray, lag: int = 12) -> float:
    x = x[~np.isnan(x)]
    n = len(x)
    e = x - x.mean()
    s = e @ e / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return float(x.mean() / np.sqrt(s / n))


def stats(port: pd.Series, mkt: pd.Series, drag_pp: float) -> dict:
    df = pd.concat([port, mkt], axis=1, keys=["p", "m"]).dropna()
    ex = (df["p"] - df["m"]).values
    out = {"months": int(len(df)), "first": str(df.index[0]), "last": str(df.index[-1]),
           "annualExcessPct": float(ex.mean() * 1200), "hacT": nw_t(ex), "trackingErrorPct": float(ex.std(ddof=1) * np.sqrt(12) * 100)}
    out["informationRatio"] = out["annualExcessPct"] / out["trackingErrorPct"] if out["trackingErrorPct"] else None
    out["annualExcessAfterDragPct"] = {f"{d}": out["annualExcessPct"] - d for d in drag_pp}
    rel = (1 + df["p"]).cumprod() / (1 + df["m"]).cumprod()
    out["maxRelativeDrawdownPct"] = float((rel / rel.cummax() - 1).min() * 100)
    for h in (6, 12):
        pw = (1 + df["p"]).rolling(h).apply(np.prod, raw=True) - 1
        mw = (1 + df["m"]).rolling(h).apply(np.prod, raw=True) - 1
        x = (pw - mw).dropna()
        out[f"excess{h}m"] = {"windows": int(len(x)), "sharePositive": float((x > 0).mean()),
                              "p5Pct": float(x.quantile(0.05) * 100), "worstPct": float(x.min() * 100),
                              "medianPct": float(x.median() * 100)}
    return out


def run() -> dict:
    proto = json.loads(PROTOCOL.read_text())
    s = series()
    mkt = s.pop("MKT")
    last = str(mkt.dropna().index[-1])
    windows = {"full": ("1963-07", last), "prePublication": ("1963-07", "2012-12"),
               "postPublication": ("2013-01", last), "ourEra": ("2016-01", last)}
    drags = {"BIG_HI_OP": (0.5, 1.0), "OP_HI_ALL_SIZES": (0.5, 1.0), "BIG_VALUE": (0.5, 1.0), "BIG_WINNERS": (2.0,)}
    res = {"protocolSha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
           "dataManifestSha256": hashlib.sha256((STORE / "manifest.json").read_bytes()).hexdigest(),
           "latestMonth": last, "portfolios": {}}
    for name, port in s.items():
        r = {}
        for w, (a, b) in windows.items():
            r[w] = stats(port.loc[a:b], mkt.loc[a:b], drags[name])
        post = port.loc["2013-01":last]
        post_no25 = post[post.index.year != 2025]
        r["postPublicationEx2025"] = stats(post_no25, mkt.loc[post_no25.index], drags[name])
        dec = {}
        for d0 in range(1960, 2030, 10):
            sl = port[(port.index.year >= d0) & (port.index.year < d0 + 10)]
            if len(sl) >= 12:
                ex = (sl - mkt.loc[sl.index]).dropna()
                dec[f"{d0}s"] = round(float(ex.mean() * 1200), 3)
        r["decadeAnnualExcessPct"] = dec
        res["portfolios"][name] = r
    p = res["portfolios"]["BIG_HI_OP"]["postPublication"]
    supported = p["hacT"] >= 2.0 and p["excess12m"]["sharePositive"] > 0.5 and p["annualExcessAfterDragPct"]["0.5"] > 0
    res["verdict"] = "TRANSFER_SUPPORTED" if supported else "WEAK_OR_ABSENT_AFTER_PUBLICATION"
    res["significantAtBonferroni"] = {k: abs(v["postPublication"]["hacT"]) >= 2.5 for k, v in res["portfolios"].items()}
    res["gradeEffect"] = proto["decisionRule"]["gradeEffect"]
    return res


def _round(o):
    if isinstance(o, float):
        return None if not np.isfinite(o) else round(o, 4)
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_round(v) for v in o]
    return o


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    out = run()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(_round(out), indent=1, sort_keys=True) + "\n")
    for k, v in out["portfolios"].items():
        for w in ("prePublication", "postPublication", "ourEra", "postPublicationEx2025"):
            x = v[w]
            print(f"{k:16s} {w:22s} ex {x['annualExcessPct']:6.2f}%/y t {x['hacT']:5.2f} TE {x['trackingErrorPct']:5.2f} 12m+ {x['excess12m']['sharePositive']:.2f} worst12 {x['excess12m']['worstPct']:6.1f} relDD {x['maxRelativeDrawdownPct']:6.1f}")
    print("verdict", out["verdict"], out["latestMonth"])
