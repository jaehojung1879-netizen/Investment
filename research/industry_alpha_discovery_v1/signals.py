"""Point-in-time industry signals from first-release export data. Reads no price and no return.

Every quantity is computed AS OF a decision date d from the release rows published on or before d. A value month's
as-of value is the one stated by the latest release published on or before d (a MOTIE release states the reference
month, the two months before it and the same month a year earlier), so a later revision can never reach an earlier
decision.
"""
from __future__ import annotations

import math

import pandas as pd

# MOTIE appendix item labels used for each industry. The table's labels changed over 2013-2026; every alias was read
# from the parsed releases (see data/item-labels.json) before any signal was computed.
ITEM_ALIASES = {
    "SEMI": ("반도체",),
    "AUTO": ("자동차",),
    "PETRO": ("석유제품",),
    "SHIP": ("선박", "선박류"),
    "COMPUTER": ("컴퓨터",),
}


def item_rows(rows: pd.DataFrame, industry: str) -> pd.DataFrame:
    r = rows[rows["item"].isin(ITEM_ALIASES[industry])].copy()
    r["published"] = pd.to_datetime(r["published"])
    return r.sort_values(["published", "valueMonth"])


def asof_values(rows: pd.DataFrame, asof) -> dict[str, tuple[float, float | None]]:
    """value month -> (value, year-ago base) from the latest release published on or before `asof`.

    The base is the value divided by (1 + the YoY rate printed beside it in the same release), i.e. the year-ago value
    as that release stated it."""
    r = rows[rows["published"] <= pd.Timestamp(asof)]
    if r.empty:
        return {}
    last = r.sort_values(["published", "num"]).groupby("valueMonth").tail(1)
    out = {}
    for m, v, g in zip(last["valueMonth"], last["valueMusd"].astype(float), last["statedGrowthPct"]):
        g = None if g is None or (isinstance(g, float) and math.isnan(g)) else float(g)
        out[m] = (v, None if g is None or g <= -100 else v / (1 + g / 100))
    return out


def latest_values(rows: pd.DataFrame) -> dict[str, tuple[float, float | None]]:
    return asof_values(rows, rows["published"].max())


def month_add(m: str, k: int) -> str:
    y, mo = int(m[:4]), int(m[5:7])
    t = y * 12 + (mo - 1) + k
    return f"{t // 12}-{t % 12 + 1:02d}"


def g3(values: dict, m: str) -> float | None:
    """3-month sum over the year-ago bases of the same 3 months, minus 1. None when any is unknown."""
    got = [values.get(month_add(m, -k)) for k in range(3)]
    if any(x is None or x[1] is None for x in got):
        return None
    base = sum(x[1] for x in got)
    return None if base <= 0 else sum(x[0] for x in got) / base - 1.0


def yoy1(values: dict, m: str) -> float | None:
    x = values.get(m)
    return None if x is None or x[1] is None or x[1] <= 0 else x[0] / x[1] - 1.0


def monthly_signals(rows: pd.DataFrame, industry: str) -> pd.DataFrame:
    """One row per MOTIE first release: G3, its change over a quarter (acceleration) and 1-month YoY, all as of the
    release date. `refMonth` is the month the release first reports."""
    r = item_rows(rows, industry)
    rels = (r[r["vintage"] == "FIRST_RELEASE"][["releaseRefMonth", "published"]]
            .drop_duplicates().sort_values("published"))
    out = []
    for ref, pub in rels.itertuples(index=False):
        v = asof_values(r, pub)
        a, b = g3(v, ref), g3(v, month_add(ref, -3))
        out.append({"industry": industry, "refMonth": ref, "published": pub, "g3": a, "g3Prev3": b,
                    "accel": None if a is None or b is None else a - b, "yoy1": yoy1(v, ref)})
    return pd.DataFrame(out)


def revision_flips(rows: pd.DataFrame, industry: str) -> pd.DataFrame:
    """Each first release's G3 and acceleration recomputed on the LATEST values, beside the as-of reading."""
    r = item_rows(rows, industry)
    lat = latest_values(r)
    sig = monthly_signals(rows, industry)
    sig["g3Latest"] = [g3(lat, m) for m in sig["refMonth"]]
    prev = [g3(lat, month_add(m, -3)) for m in sig["refMonth"]]
    sig["accelLatest"] = [None if a is None or b is None else a - b for a, b in zip(sig["g3Latest"], prev)]
    sig["g3SignFlip"] = [None if a is None or b is None else (a > 0) != (b > 0) for a, b in zip(sig["g3"], sig["g3Latest"])]
    sig["accelSignFlip"] = [None if a is None or b is None else (a > 0) != (b > 0)
                            for a, b in zip(sig["accel"], sig["accelLatest"])]
    return sig


def flash_surprises(flash: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    """Customs flash semiconductor YoY minus the latest semiconductor YoY published BEFORE it.

    For a 10-day flash the prior reading is the latest monthly first-release YoY (MOTIE, 1st of the month) or an
    earlier flash, whichever was published last; for a 20-day flash it is normally the same month's 10-day flash. A
    proxy for expectations built from public data, not a market consensus.
    """
    f = flash[flash["item"] == "반도체"].copy()
    f["published"] = pd.to_datetime(f["published"])
    f["yoy"] = f["yoyPct"].astype(float) / 100.0
    readings = [(p, "FLASH", y) for p, y in zip(f["published"], f["yoy"])]
    m = monthly[monthly["industry"] == "SEMI"].dropna(subset=["yoy1"])
    readings += [(p, "MOTIE", y) for p, y in zip(pd.to_datetime(m["published"]), m["yoy1"])]
    # Only readings published strictly before the flash's day count, so a same-day reading can never be "prior".
    out = []
    for row in f.sort_values(["published", "family"]).itertuples(index=False):
        prior = [x for x in readings if x[0] < row.published]
        if not prior:
            continue
        p = max(prior, key=lambda x: x[0])
        out.append({"family": row.family, "refMonth": row.refMonth, "published": row.published, "yoy": row.yoy,
                    "priorSource": p[1], "priorPublished": p[0], "priorYoy": p[2], "surprise": row.yoy - p[2],
                    "workingDaysPrior": getattr(row, "workingDaysPrior", None),
                    "workingDaysCurrent": getattr(row, "workingDaysCurrent", None)})
    return pd.DataFrame(out)
