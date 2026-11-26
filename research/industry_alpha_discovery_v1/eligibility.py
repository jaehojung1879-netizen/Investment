"""Stage A data eligibility: coverage, missing months, publication timing, revisions and power. Reads no price.

    python -m research.industry_alpha_discovery_v1.eligibility
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
from scipy import stats

from research.industry_alpha_discovery_v1 import signals as SG

HERE = Path(__file__).resolve().parent
D = HERE / "data"


def months(a: str, b: str) -> list[str]:
    return [str(p) for p in pd.period_range(a, b, freq="M")]


def mde_sigma(n_eff: float, share_on: float = .5, alpha=.05, power=.8) -> float | None:
    """Minimum detectable ON-OFF mean difference in units of the outcome's standard deviation."""
    n1, n0 = n_eff * share_on, n_eff * (1 - share_on)
    if n1 < 2 or n0 < 2:
        return None
    return (stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)) * math.sqrt(1 / n1 + 1 / n0)


def main():
    log = pd.DataFrame(json.loads((D / "parse-log.json").read_text()))
    motie = pd.read_csv(D / "motie-items-by-release.csv")
    flash = pd.read_csv(D / "customs-flash-items.csv")
    iip = pd.read_csv(D / "iip-industry-yoy.csv")
    out = {}
    target = months("2013-02", "2026-10")
    out["targetWindow"] = {"first": "2013-02", "last": "2026-10", "months": len(target),
                           "note": "2013-02..2026-10 inclusive is 165 months (the 166 in the Codex note is an off-by-one)"}
    mlog = log[log.family == "MOTIE"]
    have = set(mlog["refMonth"])
    parsed = set(mlog.loc[mlog.status == "PARSED", "refMonth"])
    semi_first = set(motie.loc[(motie.item == "반도체") & (motie.vintage == "FIRST_RELEASE"), "releaseRefMonth"])
    out["MOTIE"] = {"releasesInArchive": len(have & set(target)), "parsed": len(parsed & set(target)),
                    "semiFirstRelease": len(semi_first & set(target)),
                    "missingFromArchive": sorted(set(target) - have),
                    "inArchiveNotParsed": sorted((have - parsed) & set(target)),
                    "formats": mlog["format"].value_counts().to_dict()}
    # months whose value is known as of SOME release (first or later), i.e. usable in G3
    semi = motie[motie.item == "반도체"]
    out["MOTIE"]["semiValueMonthsAnyVintage"] = int(semi["valueMonth"].isin(target).groupby(semi["valueMonth"]).any().sum())
    # publication lag (days after the reference month's end)
    pub = mlog.assign(published=pd.to_datetime(mlog["published"]),
                      end=pd.to_datetime(mlog["refMonth"]) + pd.offsets.MonthEnd(0))
    out["MOTIE"]["publicationLagDays"] = (pub["published"] - pub["end"]).dt.days.describe().to_dict()

    # revisions: first release vs every later statement of the same month
    s = semi.copy()
    s["published"] = pd.to_datetime(s["published"])
    first = s[s.vintage == "FIRST_RELEASE"].set_index("valueMonth")["valueMusd"]
    later = s[s.vintage == "LATER_RELEASE"].sort_values("published").groupby("valueMonth").tail(1).set_index("valueMonth")
    j = later.join(first.rename("first"), how="inner")
    j["revPct"] = (j["valueMusd"] / j["first"] - 1) * 100
    top = j.reindex(j["revPct"].abs().sort_values(ascending=False).index).head(5)
    out["semiRevisions"] = {"pairs": len(j), "medianAbsPct": float(j["revPct"].abs().median()),
                            "maxAbsPct": float(j["revPct"].abs().max()),
                            "largest": [{"valueMonth": m, "first": float(r["first"]), "latest": float(r["valueMusd"]),
                                         "latestPublished": str(r["published"].date()), "revPct": float(r["revPct"])}
                                        for m, r in top.iterrows()]}
    rv = SG.revision_flips(motie, "SEMI")
    out["semiRevisions"]["g3SignFlips"] = int(rv["g3SignFlip"].fillna(False).sum())
    out["semiRevisions"]["accelSignFlips"] = int(rv["accelSignFlip"].fillna(False).sum())
    out["semiRevisions"]["accelCompared"] = int(rv["accelSignFlip"].notna().sum())
    out["semiRevisions"]["flipMonths"] = rv.loc[rv["accelSignFlip"].fillna(False).astype(bool), "refMonth"].tolist()

    # cross-check against #356's independently parsed 2023-08.. table
    old = pd.read_csv(HERE.parent / "industry_first_release_v1" / "data" / "kr-export-items-by-release.csv")
    o = old[(old.item == "반도체")].set_index(["releaseRefMonth", "valueMonth"])["valueMusd"]
    n = semi.set_index(["releaseRefMonth", "valueMonth"])["valueMusd"]
    both = o.to_frame("pr356").join(n.rename("this"), how="inner").drop_duplicates()
    out["crossCheckWith356"] = {"overlapCells": len(both), "identical": int((both["pr356"] == both["this"]).sum())}

    sig = SG.monthly_signals(motie, "SEMI")
    out["H2signals"] = {"releases": len(sig), "g3Computable": int(sig["g3"].notna().sum()),
                        "accelComputable": int(sig["accel"].notna().sum()),
                        "first": str(sig.dropna(subset=["accel"])["published"].min().date()),
                        "shareAccelPositive": float((sig["accel"].dropna() > 0).mean())}
    for ind in ("AUTO", "PETRO", "SHIP"):
        si = SG.monthly_signals(motie, ind)
        out["H2signals"][ind] = int(si["accel"].notna().sum())

    fl = log[log.family.str.startswith("FLASH")]
    fs = flash[flash.item == "반도체"]
    out["FLASH"] = {"releasesInArchive": int(len(fl)), "byFamily": fl["family"].value_counts().to_dict(),
                    "parsedWithSemi": int(len(fs)), "first": str(fs["published"].min()), "last": str(fs["published"].max()),
                    "byYear": fs["published"].str[:4].value_counts().sort_index().to_dict(),
                    "statedReleaseTimes": fs["releaseTime"].fillna("not stated").value_counts().to_dict(),
                    "olderFlashes": "not on the KDI archive before 2021-05; korea.kr press-release search returned none"}
    il = log[log.family == "IIP"]
    out["IIP"] = {"releasesInArchive": int(len(il)), "statuses": il["status"].value_counts().to_dict(),
                  "formats": il["format"].value_counts().to_dict(),
                  "semiParsedMonths": int((iip.industry == "SEMI").sum()) if len(iip) else 0,
                  "first": str(iip["refMonth"].min()) if len(iip) else None,
                  "hwpNote": "HWP releases store their tables as embedded objects (body text is a single line); not readable"}
    # power, in units of the outcome SD, at the planned horizons (median spacing ~10 sessions for flashes, ~21 monthly)
    nf = len(fs)
    out["power"] = {
        "H1": {f"H{H}": {"n": nf, "independent": min(nf, nf * 10 / H), "mdeSigma": mde_sigma(min(nf, nf * 10 / H))}
               for H in (21, 126)},
        "H2": {f"H{H}": {"n": out["H2signals"]["accelComputable"],
                         "independent": out["H2signals"]["accelComputable"] * 21 / H,
                         "mdeSigma": mde_sigma(out["H2signals"]["accelComputable"] * 21 / H)} for H in (126, 252)},
        "note": "minimum detectable ON-OFF difference at 80% power, alpha .05 two-sided, equal split; multiply by the "
                "outcome's standard deviation (only known after Stage C) to read it in percentage points"}
    (D / "eligibility.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n")
    print(json.dumps({k: out[k] for k in ("MOTIE", "semiRevisions", "H2signals", "FLASH", "IIP", "power")},
                     ensure_ascii=False, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
