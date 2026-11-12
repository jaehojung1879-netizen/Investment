"""Data-integrity audit of the 2026-11 census and the B1 profitability definition.

python research/evidence_first_v2/integrity.py   ->  results/data-integrity.json

Reads exactly the inputs census.py reads (signal-history 6398e94, the frozen US price store) and
first checks that census.census_region, run with a trace, reproduces the committed census.json.
It adds no outcome, return or forward price. Seven questions:

  1 profitability   ROE (B1) vs operating profit / book equity (closest PIT stand-in for Fama-French OP)
                    vs operating profit / total assets; gross profits / assets is not derivable
  2 dropSides       why each name left at stage 4: our collection or derivation gap, the company's own
                    state or reporting format, a rule added after inspection, or unresolved
  3 periods         report period vs publication date per field, mixed-period rows, same-day filings
  4 shareCounts     per-share fields built on a share count carried forward for more than 15 months
  5 opmRule         the |operating margin| > 1 rule: who it removed and what B1 would be without it
  6 usSnapshot      the US membership file's own date
  7 b1v2            the prospective B1 rule (same filing, next-day visibility) applied as a dry run
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import census as C  # noqa: E402

OUT = HERE / "results" / "data-integrity.json"
STALE_SHARES_DAYS = C.MAX_FILING_AGE_DAYS
STAGE4 = "4 PIT 재무 충족·팩터 계산 가능"


# ----------------------------------------------------------------------------- inputs
def load() -> dict:
    prod = C.production_names()
    uni = [r for r in C.jsonl_gz("ledger/universe/kr/krx-universe-2026.jsonl.gz") if r["date"] < C.AS_OF["KR"]]
    snap = max(r["date"] for r in uni)
    kr_members = {r["ticker"]: r for r in uni if r["date"] == snap}
    kr_rows = C.jsonl("ledger/fundamentals/pit-kr.jsonl")
    hist = json.loads((C.ROOT / "data" / "universe-history.json").read_text())
    us_members = {t: {"name": t} for t, v in hist.items() if v["delisted"] is None and v["region"] == "US"}
    us_rows, _ = C.us_fundamentals()
    return {"prod": prod,
            "KR": {"members": kr_members, "rows": kr_rows, "prices": C.kr_prices(set(kr_members)), "snapshot": snap},
            "US": {"members": us_members, "rows": us_rows, "prices": C.us_prices()}}


def run_region(region: str, d: dict, prod: dict) -> tuple[dict, dict, dict]:
    fund = C.latest_filings(d["rows"], C.AS_OF[region])
    trace: dict = {}
    out = C.census_region(region, d["members"], d["prices"], fund, prod, trace)
    return out, trace, fund


# ----------------------------------------------------------------------------- 1 profitability
def _same_filing(f: dict, keys: tuple[str, ...]) -> bool:
    src = f["fieldSources"]
    return all(k in src for k in keys) and len({src[k]["reportDate"] for k in keys}) == 1


def profitability_proxies(f: dict) -> dict:
    """OI/BE = operatingMargin x revenue/equity, and revenue/equity = ROE / profitMargin on one filing.
    OI/A  = OI/BE / (1 + liabilities/equity), since assets = equity + liabilities."""
    x = f["fields"]
    keys = ("roe", "operatingMargin", "profitMargin")
    if not _same_filing(f, keys) or any(x.get(k) is None for k in keys) or x["profitMargin"] <= 0:
        return {"oiToBookEquity": None, "oiToAssets": None,
                "reason": "INPUTS_FROM_DIFFERENT_FILINGS" if not _same_filing(f, keys) else "NET_MARGIN_NOT_POSITIVE_OR_MISSING"}
    oibe = x["operatingMargin"] * x["roe"] / x["profitMargin"]
    oia = None
    if x.get("debtToEquity") is not None and _same_filing(f, keys + ("debtToEquity",)):
        oia = oibe / (1 + x["debtToEquity"])
    return {"oiToBookEquity": oibe, "oiToAssets": oia, "reason": None}


def compare_rankings(rows: dict[str, dict]) -> dict:
    df = pd.DataFrame(rows).T
    out = {"n": int(len(df))}
    for col in ("oiToBookEquity", "oiToAssets"):
        sub = df.dropna(subset=["roe", col])
        sub = sub.astype({"roe": float, col: float})
        top_roe = list(sub.sort_values("roe", ascending=False).index)
        top_alt = list(sub.sort_values(col, ascending=False).index)
        q = max(1, len(sub) // 5)
        out[col] = {"n": int(len(sub)),
                    "spearmanWithRoe": round(float(sub["roe"].rank().corr(sub[col].rank())), 3) if len(sub) > 2 else None,
                    "top5Overlap": len(set(top_roe[:5]) & set(top_alt[:5])),
                    "topQuintileOverlap": f"{len(set(top_roe[:q]) & set(top_alt[:q]))}/{q}",
                    "top5ByThisMeasure": top_alt[:5]}
    return out


DEFINITIONS = [
    {"id": "FF_OP", "source": "Fama-French (2015) / Ken French Data Library",
     "definition": "(revenue - cost of goods sold - SG&A - interest expense) / book equity, fiscal year t-1, formed each June",
     "buildable": "PARTIAL", "closestPit": "oiToBookEquity = operating income (TTM) / book equity",
     "gap": "Operating income already deducts COGS and SG&A, but interest expense is not deducted (no interest-expense field in the PIT store); TTM rather than fiscal-year t-1; refreshed per filing rather than each June."},
    {"id": "NM_GPA", "source": "Novy-Marx (2013), NBER w15940",
     "definition": "(revenue - cost of goods sold) / total assets",
     "buildable": "NO", "closestPit": "oiToAssets = operating income (TTM) / total assets",
     "gap": "Neither store collects cost of goods sold or gross profit (US FLOWS and KR WANTED_ACCOUNTS list revenue, operating income, net income, equity, liabilities, assets, operating cash flow, capex). Operating income also deducts SG&A, which Novy-Marx deliberately does not; this is a different measure (closer to operating profitability / assets), not a weaker version of GP/A."},
    {"id": "B1_ROE", "source": "this repository, B1_PROFITABILITY_V1",
     "definition": "net income (TTM) / book equity among large caps with operating margin > 0 and liabilities/equity <= 2",
     "buildable": "YES", "closestPit": "roe",
     "gap": "Bottom-line and levered: includes interest, taxes, non-operating and one-off items, and rises with leverage (the <= 2 cap limits but does not remove that). It is an in-house proxy motivated by the profitability literature, NOT a reproduction of either academic strategy."},
]


# ----------------------------------------------------------------------------- 2 drop sides
SIDE = {"NOT_COLLECTED_BY_PIPELINE": "OUR_PIPELINE", "STORED_FILINGS_STALE": "OUR_PIPELINE_OR_FILER_UNRESOLVED",
        "NOT_YET_VISIBLE": "TIMING", "STORE_CHAIN_INCOMPLETE": "OUR_PIPELINE_OR_FILER_UNRESOLVED",
        "BALANCE_SHEET_NOT_EXTRACTED": "OUR_PIPELINE_OR_FILER_UNRESOLVED", "SHARE_COUNT_NOT_COLLECTED": "OUR_PIPELINE",
        "DENOMINATOR_NOT_POSITIVE": "COMPANY_STATE", "NO_OPERATING_SUBTOTAL_STATED": "COMPANY_REPORTING_FORMAT",
        "OPERATING_MARGIN_ABOVE_100PCT_RULE": "RULE_ADDED_AFTER_INSPECTION", "UNCLASSIFIED": "UNRESOLVED"}


def classify(code: str, t: str, all_rows: dict[str, list], fund: dict, as_of: str) -> str:
    rs = all_rows.get(t, [])
    if code == "OPERATING_MARGIN_ABOVE_100PCT_RULE":
        return code
    if code == "NO_PIT_FILING":
        return "NOT_YET_VISIBLE" if rs else "NOT_COLLECTED_BY_PIPELINE"
    if code == "FILING_OLDER_THAN_15M":
        return "STORED_FILINGS_STALE"
    vis = sorted((r for r in rs if r["availableFrom"] <= as_of), key=lambda r: (r["availableFrom"], r["reportDate"]))
    last = vis[-1] if vis else {"derivation": {}, "fields": {}}
    der = last.get("derivation", {})
    if code == "PROFITABILITY_MISSING":
        if der.get("netIncome") == "INCOMPLETE_CHAIN":
            return "STORE_CHAIN_INCOMPLETE"
        if last["fields"].get("bookValuePerShare") is None and last["fields"].get("debtToEquity") is None:
            return "BALANCE_SHEET_NOT_EXTRACTED"
        return "DENOMINATOR_NOT_POSITIVE"
    if code == "OPERATING_LINE_MISSING_ACCOUNTING_DEFINITION":
        if der.get("operating") == "INCOMPLETE_CHAIN":
            return "STORE_CHAIN_INCOMPLETE"
        return "NO_OPERATING_SUBTOTAL_STATED"
    if code == "BOOK_VALUE_OR_LEVERAGE_MISSING":
        if der.get("sharesAvailable") is False:
            return "SHARE_COUNT_NOT_COLLECTED"
        return "BALANCE_SHEET_NOT_EXTRACTED"
    return "UNCLASSIFIED"


def drop_sides(region: str, trace: dict, rows: list, fund: dict) -> dict:
    by_t: dict[str, list] = {}
    for r in rows:
        by_t.setdefault(r["ticker"], []).append(r)
    detail: dict[str, dict[str, int]] = {}
    sides: dict[str, int] = {}
    for t, tr in trace.items():
        if tr.get("stage") != STAGE4:
            continue
        sub = classify(tr["code"], t, by_t, fund, C.AS_OF[region])
        reason = "OPERATING_LINE_MISSING_ACCOUNTING_DEFINITION" if sub == "OPERATING_MARGIN_ABOVE_100PCT_RULE" else tr["code"]
        detail.setdefault(reason, {})[sub] = detail.setdefault(reason, {}).get(sub, 0) + 1
        sides[SIDE[sub]] = sides.get(SIDE[sub], 0) + 1
    return {"byReason": detail, "bySide": sides,
            "method": "Classified from the latest filing visible on the as-of date and its derivation flags; "
                      "a name absent from the store altogether was never collected. INCOMPLETE_CHAIN cannot tell an "
                      "account the filer omitted from one the collector's exact-label match dropped (AGENTS v2.33), so it stays unresolved."}


# ----------------------------------------------------------------------------- 3 periods / 4 shares
def periods(region: str, fund: dict, factor: dict) -> dict:
    as_of = pd.Timestamp(C.AS_OF[region])
    rows, mixed, same_day = {}, 0, 0
    for t in factor:
        src = fund[t]["fieldSources"]
        used = {k: src[k] for k in ("roe", "operatingMargin", "debtToEquity", "bookValuePerShare") if k in src}
        if len({v["reportDate"] for v in used.values()}) > 1:
            mixed += 1
        if any(v["availableFrom"] == C.AS_OF[region] for v in used.values()):
            same_day += 1
        rows[t] = {k: {"reportDate": v["reportDate"], "availableFrom": v["availableFrom"],
                       "ageDays": int((as_of - pd.Timestamp(v["reportDate"])).days),
                       "publicationLagDays": int((pd.Timestamp(v["availableFrom"]) - pd.Timestamp(v["reportDate"])).days)}
                   for k, v in used.items()}
    lag = [v["publicationLagDays"] for r in rows.values() for v in r.values()]
    age = [v["ageDays"] for r in rows.values() for v in r.values()]
    return {"freshnessRule": f"each field's report period must end within {C.MAX_FILING_AGE_DAYS} days of the as-of date; "
                             "the filing must be visible by its receipt date (availableFrom)",
            "factorRows": len(rows), "rowsMixingReportPeriods": mixed, "rowsUsingSameDayFiling": same_day,
            "publicationLagDays": {"median": float(np.median(lag)), "max": int(max(lag))} if lag else None,
            "ageDays": {"median": float(np.median(age)), "max": int(max(age))} if age else None,
            "byTicker": rows}


def share_counts(region: str, rows: list, factor: dict, fund: dict) -> dict:
    as_of = C.AS_OF[region]
    by_t: dict[str, list] = {}
    for r in rows:
        if r["availableFrom"] <= as_of:
            by_t.setdefault(r["ticker"], []).append(r)
    flagged = {}
    for t in factor:
        src = fund[t]["fieldSources"].get("bookValuePerShare")
        if not src:
            continue
        filed = [r["reportDate"] for r in by_t.get(t, []) if r.get("derivation", {}).get("sharesBasis") == "AS_FILED"
                 and r["reportDate"] <= src["reportDate"]]
        last = max(filed) if filed else None
        gap = None if last is None else (pd.Timestamp(src["reportDate"]) - pd.Timestamp(last)).days
        if last is None or gap > STALE_SHARES_DAYS:
            flagged[t] = {"bookValueFrom": src["reportDate"], "lastShareCountAsFiled": last, "carriedDays": gap,
                          "bookToPriceInCensus": round(factor[t]["bookToPrice"], 4)}
    return {"rule": f"a per-share field is invalid when its share count was carried forward more than {STALE_SHARES_DAYS} days",
            "flagged": flagged, "affects": "bookToPrice and every per-share figure; ROE, margins and liabilities/equity are ratios of totals and are unaffected",
            "pipelineNote": "Fixing the carry rule belongs to the shared pipeline (finnhub_derive.carried_shares), which this research branch does not modify."}


# ----------------------------------------------------------------------------- 5 opm rule
def opm_rule(region: str, trace: dict, members: dict, factor: dict) -> dict:
    hit = {t: tr for t, tr in trace.items() if tr.get("code") == "OPERATING_MARGIN_ABOVE_100PCT_RULE"}
    large = {t for t in factor if (region == "US" or members[t].get("rank", 999) <= C.KR_LARGE_CAP_RANK)}
    base = C.b1_screen(factor, large)
    out = {}
    for t, tr in hit.items():
        f = tr["fields"]
        would = (region == "US" or members[t].get("rank", 999) <= C.KR_LARGE_CAP_RANK) and f["operatingMargin"] > 0 \
            and f.get("debtToEquity") is not None and f["debtToEquity"] <= C.MAX_DEBT_TO_EQUITY and f.get("roe") is not None
        rank = None
        if would:
            rank = 1 + sum(1 for x in factor if x in large and factor[x]["operatingMargin"] > 0
                           and factor[x]["debtToEquity"] <= C.MAX_DEBT_TO_EQUITY and factor[x]["roe"] > f["roe"])
        out[t] = {"operatingMargin": round(f["operatingMargin"], 3), "roe": None if f.get("roe") is None else round(f["roe"], 4),
                  "wouldBeB1Eligible": bool(would), "roeRankIfKept": rank,
                  "wouldEnterDeepReview": bool(rank is not None and rank <= 5)}
    return {"addedAfterInspection": True, "removed": out,
            "b1DeepReviewWithRule": base["deepReview"],
            "verdict": "CHANGES_B1" if any(v["wouldEnterDeepReview"] for v in out.values()) else "NO_CHANGE_TO_B1_DEEP_REVIEW"}


# ----------------------------------------------------------------------------- 7 B1 v2 dry run
B1V2_KEYS = ("roe", "operatingMargin", "debtToEquity", "profitMargin")


def complete_filing(rows: list, as_of: str, keys=B1V2_KEYS) -> dict | None:
    """The latest single filing, visible strictly BEFORE the as-of date (a receipt date carries no time of
    day), that states every key, with a report period within the freshness limit. One filing, one period."""
    best = None
    for r in rows:
        if r["availableFrom"] >= as_of or any(r["fields"].get(k) is None for k in keys):
            continue
        if (pd.Timestamp(as_of) - pd.Timestamp(r["reportDate"])).days > C.MAX_FILING_AGE_DAYS:
            continue
        if best is None or (r["reportDate"], r["availableFrom"]) > (best["reportDate"], best["availableFrom"]):
            best = r
    return best


def b1v2(region: str, members: dict, rows: list, survivors: set) -> dict:
    """B1_PROFITABILITY_V2 (prospective): stage-3 survivors, inputs from ONE complete filing (complete_filing),
    large cap, operating margin > 0, liabilities/equity <= 2, ranked by ROE. OI/BE and OI/A are computed from
    the same filing and reported beside ROE, never used to rank."""
    as_of = C.AS_OF[region]
    by_t: dict[str, list] = {}
    for r in rows:
        if r["ticker"] in survivors:
            by_t.setdefault(r["ticker"], []).append(r)
    no_complete, elig = [], {}
    for t in sorted(survivors):
        f = complete_filing(by_t.get(t, []), as_of)
        if f is None:
            no_complete.append(t)
            continue
        x = f["fields"]
        large = region == "US" or members[t].get("rank", 999) <= C.KR_LARGE_CAP_RANK
        if not (large and 0 < x["operatingMargin"] <= 1 and x["debtToEquity"] <= C.MAX_DEBT_TO_EQUITY):
            continue
        oibe = x["operatingMargin"] * x["roe"] / x["profitMargin"] if x["profitMargin"] > 0 else None
        elig[t] = {"roe": x["roe"], "oiToBookEquity": oibe,
                   "oiToAssets": None if oibe is None else oibe / (1 + x["debtToEquity"]),
                   "reportDate": f["reportDate"], "availableFrom": f["availableFrom"],
                   "ageDays": int((pd.Timestamp(as_of) - pd.Timestamp(f["reportDate"])).days)}
    ranked = sorted(elig, key=lambda t: (-elig[t]["roe"], t))
    ages = [v["ageDays"] for v in elig.values()]
    return {"rule": b1v2.__doc__.strip(), "stage3Survivors": len(survivors), "noCompleteFiling": len(no_complete),
            "eligible": len(elig), "ageDays": {"median": float(np.median(ages)), "max": max(ages)} if ages else None,
            "top5": [{"ticker": t, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in elig[t].items()}} for t in ranked[:5]],
            "ranked": [{"ticker": t, "roe": round(elig[t]["roe"], 4), "reportDate": elig[t]["reportDate"],
                        "availableFrom": elig[t]["availableFrom"]} for t in ranked[:25]],
            "rankingComparison": compare_rankings({t: {k: elig[t][k] for k in ("roe", "oiToBookEquity", "oiToAssets")} for t in elig})}


# ----------------------------------------------------------------------------- run
def us_snapshot() -> dict:
    p = "data/universe-history.json"
    commit = subprocess.check_output(["git", "log", "-1", "--format=%H %cI", "--", p], cwd=C.ROOT, text=True).split()
    hist = json.loads((C.ROOT / p).read_text())
    us = {t: v for t, v in hist.items() if v["region"] == "US"}
    changes = [d for v in us.values() for d in (v.get("listed"), v.get("delisted")) if d]
    return {"file": p, "lastCommit": commit[0], "lastCommitAt": commit[1], "lastMembershipChange": max(changes),
            "currentMembers": sum(v["delisted"] is None for v in us.values()), "censusAsOf": C.AS_OF["US"],
            "gapDays": int((pd.Timestamp(C.AS_OF["US"]) - pd.Timestamp(max(changes))).days),
            "note": "Index changes after the last recorded change are not in the census; the file is a snapshot, not a live feed."}


def run(data: dict | None = None, census_path: Path = HERE / "results" / "census.json") -> dict:
    data = data or load()
    committed = json.loads(census_path.read_text())["regions"]
    out = {"schema": "DATA_INTEGRITY_V1", "signalHistoryCommit": C.SIGNAL_COMMIT, "definitions": DEFINITIONS, "regions": {}}
    for region in ("KR", "US"):
        d = data[region]
        res, trace, fund = run_region(region, d, data["prod"][region])
        fresh = json.loads(json.dumps(res, sort_keys=True, default=float))
        if fresh != {k: committed[region][k] for k in fresh}:
            raise RuntimeError(f"TRACE_RUN_DIFFERS_FROM_COMMITTED_CENSUS {region}")
        stage3 = set(d["members"]) - {t for t, tr in trace.items() if tr["stage"] != STAGE4}
        factor, large = {}, set()
        for t in sorted(set(d["members"]) - set(trace)):  # stage-4 survivors: never traced as dropped
            f = fund[t]
            fl = f["fields"]
            close = float((d["prices"][t]["close"] if region == "KR" else d["prices"][t]).loc[:C.AS_OF[region]].iloc[-1])
            factor[t] = {"roe": fl["roe"], "operatingMargin": fl["operatingMargin"], "debtToEquity": fl["debtToEquity"],
                         "bookToPrice": fl["bookValuePerShare"] / close}
            if region == "US" or d["members"][t].get("rank", 999) <= C.KR_LARGE_CAP_RANK:
                large.add(t)
        if len(factor) != res["funnel"][4]["remaining"]:
            raise RuntimeError(f"FACTOR_SET_MISMATCH {region}")
        b1_elig = {t: {**factor[t], **profitability_proxies(fund[t])} for t in factor
                   if t in large and factor[t]["operatingMargin"] > 0 and factor[t]["debtToEquity"] <= C.MAX_DEBT_TO_EQUITY}
        out["regions"][region] = {
            "asOf": C.AS_OF[region],
            "profitabilityOnV1View": {"b1Eligible": len(b1_elig),
                                      "proxyUndefined": {r: sum(1 for v in b1_elig.values() if v["reason"] == r)
                                                         for r in ("INPUTS_FROM_DIFFERENT_FILINGS", "NET_MARGIN_NOT_POSITIVE_OR_MISSING")}},
            "dropSides": drop_sides(region, trace, d["rows"], fund),
            "periods": periods(region, fund, factor),
            "shareCounts": share_counts(region, d["rows"], factor, fund),
            "opmRule": opm_rule(region, trace, d["members"], factor),
            "b1v2DryRun": b1v2(region, d["members"], d["rows"], stage3),
            "branches": {"main": "stages 0-4 drop names; stage 4 = factor-complete set",
                         "factorReference": "stage 5 is computed from stage 4 for information only and feeds nothing",
                         "b1": "stages 6-8 are computed from stage 4 independently of stage 5"},
        }
        if region == "KR":
            out["regions"][region]["membershipSnapshot"] = d["snapshot"]
    out["regions"]["US"]["membershipSnapshot"] = us_snapshot()
    return out


def _round(o):
    if isinstance(o, float):
        return round(o, 6)
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_round(v) for v in o]
    return o


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal-commit")
    ap.add_argument("--as-of-kr")
    ap.add_argument("--as-of-us")
    ap.add_argument("--us-prices", type=Path)
    ap.add_argument("--census", type=Path, default=HERE / "results" / "census.json")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    if a.signal_commit:
        C.configure(a.signal_commit, a.as_of_kr, a.as_of_us, a.us_prices or C.US_PRICES)
    OUT = a.out
    res = _round(run(census_path=a.census))
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    for g, v in res["regions"].items():
        print("==", g)
        print(" sides", v["dropSides"]["bySide"])
        print(" proxy undefined on v1 view", v["profitabilityOnV1View"])
        print(" periods mixed", v["periods"]["rowsMixingReportPeriods"], "same-day", v["periods"]["rowsUsingSameDayFiling"])
        print(" shares flagged", list(v["shareCounts"]["flagged"]))
        print(" opm rule", v["opmRule"]["verdict"], v["opmRule"]["removed"])
        b = v["b1v2DryRun"]
        print(" b1v2", b["stage3Survivors"], b["noCompleteFiling"], b["eligible"], b["ageDays"], [x["ticker"] for x in b["top5"]])
        print(" ranking", json.dumps(b["rankingComparison"], ensure_ascii=False))
