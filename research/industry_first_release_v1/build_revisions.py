"""Turn the per-release table into a first-release vs later-release revision dataset.

    python -m research.industry_first_release_v1.build_revisions

Input: data/kr-export-items-by-release.csv (one row per release x item x stated month).
Output:
  data/kr-export-vintages.csv  one row per item x reference month: the value as first published (release of month m,
                               published on the 1st of m+1), and as restated one, two and twelve releases later, each
                               with its publication date. A vintage the archive does not contain is left empty.
  data/revision-summary.json   per item: how many months have each vintage, and the size of revisions in % of the
                               first release (median and max absolute), computed only where both values exist.
No return, price or model is read here.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
D = HERE / "data"


def month_add(m: str, k: int) -> str:
    return str(pd.Period(m, freq="M") + k)


def build() -> tuple[pd.DataFrame, dict]:
    r = pd.read_csv(D / "kr-export-items-by-release.csv", dtype={"releaseRefMonth": str, "valueMonth": str})
    r = r.drop_duplicates(["releaseRefMonth", "item", "valueMonth"])
    key = {(x.releaseRefMonth, x.item, x.valueMonth): (x.valueMusd, x.published) for x in r.itertuples()}
    rows = []
    for (item, m), _ in r.groupby(["item", "valueMonth"]):
        rec = {"item": item, "refMonth": m}
        for lab, k in (("first", 0), ("plus1", 1), ("plus2", 2), ("plus12", 12)):
            v = key.get((month_add(m, k), item, m))
            rec[f"{lab}Musd"], rec[f"{lab}Published"] = (v if v else (np.nan, None))
        rows.append(rec)
    v = pd.DataFrame(rows).sort_values(["item", "refMonth"])
    summary = {}
    for item, g in v.groupby("item"):
        s = {"months": int(len(g)), "withFirst": int(g["firstMusd"].notna().sum())}
        for lab in ("plus1", "plus2", "plus12"):
            both = g.dropna(subset=["firstMusd", f"{lab}Musd"])
            rev = (both[f"{lab}Musd"] / both["firstMusd"] - 1) * 100
            s[lab] = {"pairs": int(len(both)), "medianAbsRevisionPct": float(rev.abs().median()) if len(both) else None,
                      "maxAbsRevisionPct": float(rev.abs().max()) if len(both) else None,
                      "shareRevised": float((rev.abs() > 1e-9).mean()) if len(both) else None,
                      "meanRevisionPct": float(rev.mean()) if len(both) else None}
        summary[item] = s
    releases = sorted(r["releaseRefMonth"].unique())
    meta = {"releases": len(releases), "firstRelease": releases[0], "lastRelease": releases[-1],
            "missingReleases": [str(p) for p in pd.period_range(releases[0], releases[-1], freq="M") if str(p) not in releases],
            "unit": "USD million", "source": "MOTIE monthly export press releases via eiec.kdi.re.kr (original PDFs, sha256 in source-manifest.json)"}
    return v, {"meta": meta, "items": summary}


def main():
    v, s = build()
    v.to_csv(D / "kr-export-vintages.csv", index=False)
    (D / "revision-summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(json.dumps(s["meta"], ensure_ascii=False))
    print("반도체", json.dumps(s["items"].get("반도체"), ensure_ascii=False))


if __name__ == "__main__":
    main()
