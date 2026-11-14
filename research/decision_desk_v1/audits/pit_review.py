"""PIT review of the 2026-11 cohort (protocol v1 evidence pack vs v2 release-time rules).

Reads the frozen 2026-11 market store and the committed v1 pack, recomputes the market and
macro layers with availability.py, and lists every v1 observation that was not public at
the region's information cutoff. Nothing in inputs/, ai-reviews/ or dry-run/ is modified.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DESK = HERE.parent
sys.path.insert(0, str(DESK))
import availability as A  # noqa: E402
import packet as P  # noqa: E402

STORE = DESK / "inputs" / "2026-11" / "market"
V1 = DESK / "inputs" / "2026-11" / "evidence-pack.json"


def v1_usage(region: str, v1_region: dict, cutoff: pd.Timestamp) -> list[dict]:
    """Observations the v1 pack actually read, with their release times."""
    used = []
    as_of = v1_region["asOfDate"]
    fred_last = pd.Timestamp(as_of) - pd.Timedelta(days=1)  # v1 rule: values dated before the cutoff date
    for k in ("DGS10", "DGS3MO", "VIXCLS", "T10YIE") + (("DEXKOUS",) if region == "KR" else ()):
        s = P.raw_fred(STORE, k).loc[:fred_last]
        d = s.index[-1]
        rel = A.release_utc(k, d)
        used.append({"input": f"FRED {k}", "obsDate": str(d.date()), "value": float(s.iloc[-1]),
                     "releasedUtc": P.iso(rel), "publicAtCutoff": bool(rel <= cutoff)})
    for sym in ("GLD", "UUP", "IEF") + (("SPY", "QQQ") if region == "US" else ()):
        s = P.raw_close(STORE, sym).loc[:as_of]
        d = s.index[-1]
        rel = A.exchange_close_utc("US", d)
        used.append({"input": f"Yahoo {sym} close", "obsDate": str(d.date()), "value": float(s.iloc[-1]),
                     "releasedUtc": P.iso(rel), "publicAtCutoff": bool(rel <= cutoff)})
    if region == "KR":
        s = P.raw_close(STORE, "KRW=X").loc[:as_of]
        used.append({"input": "Yahoo KRW=X daily bar", "obsDate": str(s.index[-1].date()), "value": float(s.iloc[-1]),
                     "releasedUtc": None, "publicAtCutoff": None, "note": "bar close time unverifiable; excluded in v2"})
        s = P.raw_close(STORE, "^KS11").loc[:as_of]
        rel = A.exchange_close_utc("KR", s.index[-1])
        used.append({"input": "Yahoo ^KS11 close", "obsDate": str(s.index[-1].date()), "value": float(s.iloc[-1]),
                     "releasedUtc": P.iso(rel), "publicAtCutoff": bool(rel <= cutoff)})
    return used


def review() -> dict:
    v1 = json.loads(V1.read_text())
    out = {"schema": "PIT_REVIEW_V1", "cohort": "2026-11",
           "inputsSha256": {"v1EvidencePack": hashlib.sha256(V1.read_bytes()).hexdigest(),
                            "marketManifest": hashlib.sha256((STORE / "manifest.json").read_bytes()).hexdigest(),
                            "availabilityModule": hashlib.sha256((DESK / "availability.py").read_bytes()).hexdigest()},
           "releaseRulesVerified": A.SOURCE_EVIDENCE, "regions": {}}
    for region, v in sorted(v1["regions"].items()):
        cutoff = A.cutoff_utc(region, v["asOfDate"])
        used = v1_usage(region, v, cutoff)
        after = {"market": P.market_layer(STORE, region, cutoff), "macro": P.macro_layer(STORE, region, cutoff)}
        out["regions"][region] = {
            "informationCutoffUtc": P.iso(cutoff),
            "v1Inputs": used,
            "notPublicAtCutoff": [u["input"] + " " + u["obsDate"] for u in used if u["publicAtCutoff"] is False],
            "unverifiable": [u["input"] for u in used if u["publicAtCutoff"] is None],
            "before": {"market": v["market"], "macro": v["macro"]},
            "after": after,
        }
    out["decisionImpact"] = {
        "deterministicPart": "Gates G1-G6 and the B1 production weights read only the production receipt (published 2026-11-07, before both cutoffs were reviewed); they are unchanged. Re-running the gates on the v2 packet gives the same gate passers.",
        "aiLabels": "The B2 market and macro layer labels and their interpretation text were written while reading v1 values, some of which were not public at the cutoff. Whether a blind review of the v2 values would have chosen different labels is unknowable now: any new review would be written after the outcome period began and would be post hoc.",
        "selectionSensitivity": "KR 021240.KS had 2 SUPPORTS; a macro label of SUPPORTS would have made it selectable, so the KR 0-name decision depended on an AI label formed on contaminated macro inputs. US TRV had 3 SUPPORTS without the macro layer; its selection did not depend on macro.",
        "contaminatedCitations": [
            "US market interpretation: 'VIX is 28, so implied risk is well above realised' — VIX 28.18 is the 2026-11-05 print, public 2026-11-06 21:15 UTC; at the US cutoff the latest public VIX was 16.61 (2026-11-04).",
            "TRV reason 2: 'diversifies the 90% SPY residual while VIX is 28' — same non-public VIX print.",
            "TRV thesis6m: 'stays choppy (VIX near 28)' — same.",
            "US/KR macro interpretation: '10y 4.84% (+15bp over 63 sessions)' — the 2026-11-05 H.15 print; the public value was 4.90% (+27bp).",
            "KR macro interpretation: 'dollar strong (UUP +6.5% over 126 sessions), VIX 28' — UUP 11-06 close and VIX 11-05 were not public at the KR cutoff (06:30 UTC); public values were UUP +5.5% and VIX 16.61.",
        ],
        "classification": "B2 2026-11 KR and US: PIT_CONTAMINATED. B0 and B1 2026-11: PIT_CLEAN (no market or macro input).",
        "effect": "The six 2026-11 records stay byte-identical. An annotation row marks the two B2 records PIT_CONTAMINATED; they will be scored but reported outside the primary comparison. No record is re-generated and no weight changes.",
    }
    return out


if __name__ == "__main__":
    res = review()
    (HERE / "2026-11-pit-review.json").write_text(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    for r, v in res["regions"].items():
        print(r, v["informationCutoffUtc"], "not public:", v["notPublicAtCutoff"], "unverifiable:", v["unverifiable"])
