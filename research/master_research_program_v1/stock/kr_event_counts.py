"""Outcome-blind DART report-name COUNTS for candidate KR stock-selection event axes.

Counts filings, issuers and receipt years; reads no price, return, label or model output.
Two inputs:

* ``I`` (KRX 거래소공시) lists already collected for all 254 DART-resolved ever-Top-120 issuers by
  alpha-mechanism-sprint-v1 (``research/alpha_mechanism_sprint_v1/data/dart-list/*-I.jsonl.gz``),
  re-read at zero DART cost;
* ``B`` (주요사항보고서) lists for the same deterministic 24-issuer sample the insider gate uses
  (``kr_insider_probe.issuer_sample(24)``), fetched here (buyback / issuance / CB decisions are B).

Matching a report name is a reading list for counting, never a classification of any filing.

CLI::

    DART_API_KEY=... python research/master_research_program_v1/stock/kr_event_counts.py --out <json>
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.alpha_evidence_sprint_v2 import kr_insider_probe as P  # noqa: E402

SPRINT1 = ROOT / "research/alpha_mechanism_sprint_v1/data/dart-list"
LIST = "https://opendart.fss.or.kr/api/list.json"
CACHE = Path("/tmp/claude-0/-home-user-Investment/3e1f344d-8435-50c1-8877-d6f38a230ceb/scratchpad/laneC/events")

# category -> report-name substrings (originals only; any name containing 정정 is excluded)
CATEGORIES = {
    "B": {
        "BUYBACK_DECISION": ("자기주식취득결정",),
        "BUYBACK_TRUST_DECISION": ("자기주식취득신탁계약체결결정",),
        "TREASURY_DISPOSAL_DECISION": ("자기주식처분결정",),
        "RIGHTS_OFFERING_DECISION": ("유상증자결정",),
        "CONVERTIBLE_BOND_DECISION": ("전환사채권발행결정",),
        "BOND_WITH_WARRANT_DECISION": ("신주인수권부사채권발행결정",),
        "EXCHANGEABLE_BOND_DECISION": ("교환사채권발행결정",),
        "MERGER_DECISION": ("회사합병결정",),
        "SPLIT_DECISION": ("회사분할결정", "회사분할합병결정"),
    },
    "I": {
        "CASH_DIVIDEND_DECISION": ("현금ㆍ현물배당결정",),
        "SHARE_CANCELLATION_DECISION": ("주식소각결정",),
        "TREASURY_STOCK_ANY_I": ("자기주식",),
        "MAJOR_HOLDER_CHANGE_FILING_KRX": ("최대주주등소유주식변동신고서",),
        "SUPPLY_CONTRACT": ("단일판매ㆍ공급계약체결",),
        "SUPPLY_CONTRACT_TERMINATION": ("단일판매ㆍ공급계약해지",),
        "NEW_FACILITY_INVESTMENT": ("신규시설투자",),
        "VALUE_UP_PLAN": ("기업가치제고계획",),
        "EARNINGS_GUIDANCE": ("영업실적등에대한전망",),
        "IR_EVENT": ("기업설명회",),
        "UNFAITHFUL_DISCLOSURE": ("불성실공시",),
        "EMBEZZLEMENT": ("횡령ㆍ배임",),
        "LARGEST_HOLDER_CHANGE": ("최대주주변경",),
        "INQUIRY_DISCLOSURE": ("조회공시",),
    },
}


def classify(report_nm: str, table: dict) -> list[str]:
    """Pure: the categories a report name falls under (an amendment never counts)."""
    name = report_nm or ""
    if "정정" in name:
        return []
    return [cat for cat, keys in table.items() if any(k in name for k in keys)]


def tally(rows_by_issuer: dict[str, list[dict]], table: dict) -> dict:
    count, issuers, years = Counter(), defaultdict(set), defaultdict(Counter)
    for corp, rows in rows_by_issuer.items():
        for r in rows:
            for cat in classify(r.get("report_nm"), table):
                count[cat] += 1
                issuers[cat].add(corp)
                years[cat][(r.get("rcept_dt") or "")[:4]] += 1
    return {cat: {"filings": count[cat], "issuers": len(issuers[cat]),
                  "byYear": dict(sorted(years[cat].items()))} for cat in table}


D_CATEGORIES = {
    "INSIDER_REPORT_SECTION173": ("임원ㆍ주요주주특정증권등소유상황보고서",),
    "LARGE_HOLDING_5PCT_REPORT": ("주식등의대량보유상황보고서",),
}


def anchor_density(rows_by_issuer: dict[str, list[dict]], keys: tuple, codes: dict[str, str],
                   members: dict[str, set[str]], anchors: list[str], sessions: list[str], window: int) -> dict:
    """Per anchor: PIT Top-120 member issuers (covered by the lists) with >= 1 original matching filing
    usable in the ``window`` sessions ending on the anchor (usable = first session strictly after receipt).
    Counts issuers, never outcomes."""
    import bisect
    usable = {}
    for corp, rows in rows_by_issuer.items():
        days = []
        for r in rows:
            name = r.get("report_nm") or ""
            if "정정" in name or not any(k in name for k in keys):
                continue
            rd = r["rcept_dt"]
            i = bisect.bisect_right(sessions, f"{rd[:4]}-{rd[4:6]}-{rd[6:]}")
            if i < len(sessions):
                days.append(sessions[i])
        usable[corp] = sorted(days)
    out = []
    for anchor in anchors:
        snap = [d for d in members if d <= anchor]
        mem = members[max(snap)] if snap else set()
        covered = [c for c, code in codes.items() if code in mem]
        j = bisect.bisect_right(sessions, anchor) - 1
        start = sessions[max(0, j - window + 1)]
        active = sum(1 for c in covered
                     if bisect.bisect_left(usable.get(c, []), start) < bisect.bisect_right(usable.get(c, []), anchor))
        out.append({"anchor": anchor, "membersCovered": len(covered), "membersInSnapshot": len(mem),
                    "issuersWithEvent": active})
    vals = sorted(a["issuersWithEvent"] for a in out)
    return {"windowSessions": window, "anchors": len(out),
            "issuersWithEventMedian": vals[len(vals) // 2] if vals else None,
            "issuersWithEventMin": vals[0] if vals else None, "issuersWithEventMax": vals[-1] if vals else None,
            "anchorsWithAtLeast5": sum(v >= 5 for v in vals), "anchorsWithAtLeast10": sum(v >= 10 for v in vals),
            "membersCoveredMedian": sorted(a["membersCovered"] for a in out)[len(out) // 2] if out else None,
            "perAnchor": out}


def read_sprint1(kind: str) -> dict[str, list[dict]]:
    out = {}
    for path in sorted(SPRINT1.glob(f"*-{kind}.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            out[path.name[:8]] = [json.loads(line) for line in fh if line.strip()]
    return out


def fetch_b(corp: str, key: str, counter: dict) -> list[dict]:
    path = CACHE / f"{corp}-B.json"
    if path.exists():
        return json.loads(path.read_text())
    rows, page, total = {}, 1, None
    while True:
        q = urllib.parse.urlencode({"crtfc_key": key, "corp_code": corp, "bgn_de": "20130101", "end_de": "20261031",
                                    "pblntf_ty": "B", "page_no": page, "page_count": 100})
        for attempt in range(3):
            counter["calls"] += 1
            time.sleep(0.15)
            try:
                with urllib.request.urlopen(f"{LIST}?{q}", timeout=60) as response:
                    payload = json.loads(response.read())
                break
            except Exception:  # noqa: BLE001
                if attempt == 2:
                    raise
                time.sleep(2)
        status = payload.get("status")
        if status == "013":
            break
        if status != "000":
            raise RuntimeError(f"LIST_STATUS_{status}")
        total = total or payload.get("total_count")
        for r in payload.get("list") or []:
            rows[r["rcept_no"]] = {"rcept_no": r["rcept_no"], "rcept_dt": r["rcept_dt"], "report_nm": r["report_nm"]}
        if page >= int(payload.get("total_page") or 1):
            break
        page += 1
    out = sorted(rows.values(), key=lambda r: r["rcept_no"])
    path.write_text(json.dumps(out, ensure_ascii=False))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--universe", help="dir of krx-universe-*.jsonl.gz (signal-history) for per-anchor density")
    ap.add_argument("--b-all", action="store_true", help="fetch B-type lists for all 254 sprint-1 issuers")
    ap.add_argument("--insider-cache", help="insider_density_gate cache dir (its D-type lists are re-read, 0 calls)")
    args = ap.parse_args(argv)
    key = os.environ.get("DART_API_KEY")
    if not key:
        raise SystemExit("DART_API_KEY_REQUIRED")
    CACHE.mkdir(parents=True, exist_ok=True)
    counter_path = CACHE / "calls.json"
    counter = json.loads(counter_path.read_text()) if counter_path.exists() else {"calls": 0}
    sample = P.issuer_sample(24)
    b_rows = {}
    try:
        for corp in sample:
            b_rows[corp] = fetch_b(corp, key, counter)
        b_all = {}
        if args.b_all:
            for corp in sorted({p.name[:8] for p in SPRINT1.glob("*-A.jsonl.gz")}):
                b_all[corp] = fetch_b(corp, key, counter)
    finally:
        counter_path.write_text(json.dumps(counter))
    i_rows = read_sprint1("I")
    result = {
        "probe": "kr-stock-event-report-name-counts-v1", "evidenceClass": "OUTCOME_BLIND_SOURCE_PROBE",
        "B_majorMatters_24IssuerSample": {"issuers": len(b_rows), "range": ["2013-01-01", "2026-10-31"],
                                          "filingsListed": sum(len(v) for v in b_rows.values()),
                                          "counts": tally(b_rows, CATEGORIES["B"])},
        "I_krxDisclosures_254Issuers": {"source": "research/alpha_mechanism_sprint_v1/data/dart-list/*-I.jsonl.gz "
                                                  "(collected 20121001-20261031, zero new calls)",
                                        "issuers": len(i_rows), "counts": tally(i_rows, CATEGORIES["I"])},
        "dartCalls": counter["calls"], "returnsRead": 0, "pricesRead": 0, "labelsBuilt": 0,
        "caveat": "report-name substring counts; a match is a reading list, not a verified event classification",
    }
    if args.insider_cache:
        d_rows = {p.stem: json.loads(p.read_text()) for p in sorted((Path(args.insider_cache) / "lists").glob("*.json"))}
        result["D_ownership_24IssuerSample"] = {"source": "insider_density_gate list cache (pblntf_ty=D, 0 new calls)",
                                                "issuers": len(d_rows), "counts": tally(d_rows, D_CATEGORIES)}
    if args.universe:
        from pipeline import replay_calendar as RC
        from research.master_research_program_v1.stock import insider_density_gate as G
        sessions = [d.strftime("%Y-%m-%d") for d in RC.sessions("2012-06-01", "2026-12-31", "KR")]
        members = G.top_members(G.load_snapshots(Path(args.universe)))
        anchors = G.load_anchors()
        codes = {}
        for corp, rows in i_rows.items():
            seen = sorted({r.get("stock_code") for r in rows if r.get("stock_code")})
            if seen:
                codes[corp] = seen[0]
        dens = {}
        for cat, window in (("SUPPLY_CONTRACT", 63), ("CASH_DIVIDEND_DECISION", 252),
                            ("SHARE_CANCELLATION_DECISION", 252), ("NEW_FACILITY_INVESTMENT", 252),
                            ("MAJOR_HOLDER_CHANGE_FILING_KRX", 63), ("EARNINGS_GUIDANCE", 252)):
            d = anchor_density(i_rows, CATEGORIES["I"][cat], codes, members, anchors, sessions, window)
            d.pop("perAnchor")
            dens[cat] = d
        if b_all:
            b_dens = {}
            for cat, keys in (("BUYBACK_DECISION_OR_TRUST", CATEGORIES["B"]["BUYBACK_DECISION"]
                               + CATEGORIES["B"]["BUYBACK_TRUST_DECISION"]),
                              ("RIGHTS_OFFERING_DECISION", CATEGORIES["B"]["RIGHTS_OFFERING_DECISION"]),
                              ("CONVERTIBLE_OR_EXCHANGEABLE_BOND", CATEGORIES["B"]["CONVERTIBLE_BOND_DECISION"]
                               + CATEGORIES["B"]["EXCHANGEABLE_BOND_DECISION"])):
                d = anchor_density(b_all, keys, codes, members, anchors, sessions, 252)
                d.pop("perAnchor")
                b_dens[cat] = d
            result["B_majorMatters_254Issuers"] = {
                "issuers": len(b_all), "filingsListed": sum(len(v) for v in b_all.values()),
                "counts": tally(b_all, CATEGORIES["B"]), "perAnchorTop120Density252": b_dens}
        result["I_perAnchorTop120Density"] = {
            "note": ("all 254 DART-resolved issuers (not a projection); PIT Top-120 = rank <= 120 in the latest "
                     "signal-history ledger/universe/kr snapshot on or before the anchor; issuers with >= 1 original "
                     "filing usable in the trailing window; counts filings only"),
            "anchorsSource": "docs/results/regional-standalone-paths.json.gz regional.KR[i].signalDate",
            "universeCommit": (Path(args.universe) / "COMMIT").read_text().strip()
            if (Path(args.universe) / "COMMIT").exists() else None,
            "categories": dens}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"calls": counter["calls"], "B": result["B_majorMatters_24IssuerSample"]["filingsListed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
