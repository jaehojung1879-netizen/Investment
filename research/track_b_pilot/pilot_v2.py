"""Track B pilot v2 -- corrections to v1 (`pilot.py`, `track-b-pilot.json`, both kept unchanged).

1. SPF timing: v1 approximated every release as the 15th of the survey quarter's second month. v2 reads the Philadelphia
   Fed's official deadline and news-release dates (data/spf-release-dates-20261124.txt, preserved with its SHA-256).
   A survey's DEADLINE is when its forecasts were formed (the information it can contain); its RELEASE is when the
   market could see it. Ex ante = released before the first market reaction; a post-shock survey reflects the shock
   only if its DEADLINE is on or after the anchor.
2. SPF columns: v1 read only CPROF2/3/5/6, so the survey two quarters after the pre-shock survey had no value; v2
   reads CPROF1..6 from the same preserved file.
3. Drawdown: v1's `maxDrawdownWithin12m` was the lowest total return relative to the pre-reaction close (a
   minimum return from the base). v2 reports that as `minReturnFromBase12m` and adds the true maximum drawdown inside
   the same 252-session window (largest peak-to-trough fall from a running peak that starts at the base).

    python -m research.track_b_pilot.pilot_v2
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

from research.market_risk_discovery_v1 import label_census as L

from . import pilot as V1

HERE = Path(__file__).resolve().parent
RELEASES = HERE / "data" / "spf-release-dates-20261124.txt"
SOURCE = "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/spf-release-dates.txt"


def official_dates() -> dict[tuple[int, int], dict]:
    out, year = {}, None
    for line in RELEASES.read_text().splitlines():
        m = re.match(r"^\s*(\d{4})?\s*Q([1-4])\s+(\d+/\d+/\d+)(\**)\s+(\d+/\d+/\d+)?(\**)", line)
        if not m:
            continue
        if m.group(1):
            year = int(m.group(1))
        def iso(s):
            mo, d, y = (int(x) for x in s.split("/"))
            return dt.date(2000 + y if y < 50 else 1900 + y, mo, d).isoformat()
        out[(year, int(m.group(2)))] = {"deadline": iso(m.group(3)), "release": iso(m.group(5)) if m.group(5) else None,
                                        "flag": m.group(4) or None}
    return out


def spf_levels() -> list[dict]:
    """All CPROF1..CPROF6 columns of the preserved #361 SPF file (v1's reader kept only 2, 3, 5 and 6, so the
    two-quarters-ahead forecast was missing). Read with #361's own stdlib xlsx reader; #361 files are not modified."""
    import gzip
    rows = V1.SPF.read_rows(gzip.decompress((V1.MCT_RAW / "spf-median-cprof-level.xlsx.gz").read_bytes()))
    head, out = rows[0], []
    for r in rows[1:]:
        if not r:
            continue
        rec = dict(zip(head, r + [None] * (len(head) - len(r))))
        out.append({"year": int(rec["YEAR"]), "quarter": int(rec["QUARTER"]),
                    **{f"CPROF{i}": (float(rec[f"CPROF{i}"]) if isinstance(rec.get(f"CPROF{i}"), (int, float)) else None)
                       for i in range(1, 7)}})
    return out


def spf_view_v2(react: str, anchor: str) -> dict:
    dates = official_dates()
    tab = [{**r, **dates[(r["year"], r["quarter"])]} for r in spf_levels() if (r["year"], r["quarter"]) in dates]
    tab.sort(key=lambda r: r["release"])
    pre = [r for r in tab if r["release"] < react][-1]
    tgt = V1.target(pre["year"], pre["quarter"], 4)
    col_by_ahead = {4: "CPROF6", 3: "CPROF5", 2: "CPROF4", 1: "CPROF3", 0: "CPROF2"}
    path = []
    for r in [x for x in tab if x["release"] >= react][:4]:
        k = (tgt[0] * 4 + tgt[1] - 1) - (r["year"] * 4 + r["quarter"] - 1)
        v = r.get(col_by_ahead.get(k, ""), None)
        path.append({"survey": f"{r['year']}Q{r['quarter']}", "deadline": r["deadline"], "release": r["release"],
                     "deadlineOnOrAfterAnchor": r["deadline"] >= anchor,
                     "daysAnchorToRelease": (dt.date.fromisoformat(r["release"]) - dt.date.fromisoformat(anchor)).days,
                     "aheadQuarters": k, "forecastOfTarget": v,
                     "revisionVsPre": (v / pre["CPROF6"] - 1) if v is not None else None})
    return {"preSurvey": f"{pre['year']}Q{pre['quarter']}", "preDeadline": pre["deadline"], "preRelease": pre["release"],
            "targetQuarter": f"{tgt[0]}Q{tgt[1]}", "preForecastOfTarget": pre["CPROF6"], "postSurveys": path}


def drawdowns(tr: np.ndarray, k0: int, n: int = 252) -> dict:
    w = tr[k0:min(len(tr), k0 + n + 1)]
    peak = np.maximum.accumulate(w)
    return {"minReturnFromBase12m": float(w.min() / w[0] - 1), "maxDrawdown12m": float((w / peak - 1).min())}


def build() -> dict:
    v1 = json.loads((HERE / "track-b-pilot.json").read_text())
    dates, tr = L.load_tr()
    pos = {d: k for k, d in enumerate(dates)}
    out = {"study": "track-b-pilot", "version": 2, "supersedes": "track-b-pilot.json (v1, kept unchanged)",
           "spfReleaseSource": {"url": SOURCE, "file": "data/spf-release-dates-20261124.txt",
                                "sha256": hashlib.sha256(RELEASES.read_bytes()).hexdigest()},
           "events": {}}
    for name, ev in V1.EVENTS.items():
        e1 = v1["events"][name]
        k0 = pos[e1["exAnte"]["priceDate"]]
        spf = spf_view_v2(ev["firstReaction"], ev["anchor"])
        out["events"][name] = {
            "anchor": ev["anchor"], "firstReaction": ev["firstReaction"],
            "spf": spf, "drawdown": drawdowns(tr, k0),
            "v1Values": {"spfPreSurvey": e1["exAnte"]["spf"]["preSurvey"],
                         "spfPostRevisions": [s["revisionVsPre"] for s in e1["exPost"]["spfSameTargetRevisions"]],
                         "maxDrawdownWithin12m_wasMinReturnFromBase": e1["exPost"]["maxDrawdownWithin12m"]}}
    return out


def main() -> int:
    out = build()
    (HERE / "track-b-pilot-v2.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=float) + "\n")
    for n, e in out["events"].items():
        print(n, e["spf"]["preSurvey"], e["spf"]["preRelease"], [(s["survey"], s["deadline"], s["release"],
              s["deadlineOnOrAfterAnchor"], s["daysAnchorToRelease"], None if s["revisionVsPre"] is None else round(s["revisionVsPre"], 3))
              for s in e["spf"]["postSurveys"]], {k: round(v, 3) for k, v in e["drawdown"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
