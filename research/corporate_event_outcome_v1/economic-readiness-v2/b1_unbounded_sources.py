"""Cited DART terms for the eight B1 H126 windows that had no upper bound (2026-11-09).

`b1-admission-status-v2.json` lists eight matured B1 H126 events whose as-traded / -100%
treatment is only a LOWER bound, which makes a REJECT_ECONOMIC_EFFECT unreachable
(README-ko.md section 5). This module fetches the issuer filings that state the
corporate-action terms, through #320's existing OpenDART client and document path,
and records each term with the receipt that states it.

* Terms only. No price level, return, NAV or label is read; the price ledger is read
  for (ticker, date) PRESENCE of the successor securities only.
* Records are built with the repository's own builders, which refuse a term without
  a citing receipt: `pipeline.kr_terminal_corporate_actions.build_record` for the
  terminal merger and `build_consideration_component` for each spin-off leg.
* The raw DART cache stays outside the repository (Owner rights decision, #320 README
  section 6); every body is pinned here by SHA256 so a re-fetch is byte-checked.
* An event with no filed consideration is recorded as such. Nothing is inferred.

    python research/corporate_event_outcome_v1/economic-readiness-v2/b1_unbounded_sources.py --cache <dir> [--offline]
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pipeline import kr_terminal_corporate_actions as T  # noqa: E402
from research.corporate_event_readiness_v1.cohort import bodies as B  # noqa: E402
from research.corporate_event_readiness_v1.cohort.dart_client import DartClient  # noqa: E402

OUT = Path(__file__).resolve().parent / "b1-unbounded-events-sources-v1.json"

# The eight events, exactly as listed in b1-admission-status-v2.json
# (eventsWithUnboundedUpside_B1_H126). Receipts were found from each issuer's list.json.
EVENTS = (
    {"ticker": "051310.KS", "name": "포스코플랜텍", "entry": "2015-11-25", "corp": "00181934",
     "kind": "TERMINAL", "listWindow": ("20150801", "20160630"), "receipts": ()},
    {"ticker": "068870.KS", "name": "LG생명과학", "entry": "2016-10-24", "corp": "00423609",
     "kind": "TERMINAL_MERGER", "listWindow": ("20160601", "20170131"),
     "receipts": ("20160912000005",), "amendmentNotServed": "20161214000402"},
    {"ticker": "210980.KS", "name": "SK디앤디", "entry": "2016-12-08", "corp": "00508344",
     "kind": "BONUS_ISSUE", "listWindow": ("20170301", "20170430"), "receipts": ("20170324000647",)},
    {"ticker": "210980.KS", "name": "SK디앤디", "entry": "2023-12-21", "corp": "00508344",
     "kind": "SPIN_OFF", "listWindow": ("20230901", "20240531"), "receipts": ("20240105000589",)},
    {"ticker": "207940.KS", "name": "삼성바이오로직스", "entry": "2025-09-11", "corp": "00877059",
     "kind": "SPIN_OFF", "listWindow": ("20250501", "20251130"), "receipts": ("20250822000109",)},
    {"ticker": "068270.KS", "name": "셀트리온", "entry": "2018-06-26", "corp": "00413046",
     "kind": "STOCK_DIVIDEND", "receipts": ("20181219800660",),
     "recordedBodySha256": "62fb033ebaf5e3b69b8b593a3b44da91b6081791da0d57102d6b6392c9b65392"},
    {"ticker": "068270.KS", "name": "셀트리온", "entry": "2019-09-27", "corp": "00413046",
     "kind": "STOCK_DIVIDEND", "receipts": ("20191218800434",),
     "recordedBodySha256": "ac7535444b78db7ac3524e0988147739f0e37a7741bd0aa9b4853100b630924a"},
    {"ticker": "068270.KS", "name": "셀트리온", "entry": "2022-10-04", "corp": "00413046",
     "kind": "STOCK_DIVIDEND", "receipts": ("20221216801362",),
     "recordedBodySha256": "4d9fc4b48d331cc99ca0ef5fd4cc89871f20b588eca1384666db28fc60502445"},
)
# Successor securities whose (ticker, date) presence is checked in the KRX bar ledger.
SUCCESSORS = {"051910.KS": "LG화학", "475150.KS": "SK이터닉스", "0126Z0.KS": "삼성에피스홀딩스"}
TERMINAL_KEYWORDS = ("상장폐지", "정리매매", "합병", "분할", "주식교환", "주식이전", "공개매수", "해산", "청산", "회생")


def _rows(raw: bytes) -> list[str]:
    cells, _ = B.as_table_cells(raw)
    return [" | ".join(r) for r in B.table_rows(cells) if r]


def _cell(rows: list[str], label: str) -> str:
    hits = [r for r in rows if r.startswith(label)]
    if not hits:
        raise ValueError("TERM_ROW_NOT_FOUND:" + label)
    return hits[0]


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _date(text: str) -> str:
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", text)
    if not m:
        raise ValueError("DATE_NOT_FOUND:" + text[:80])
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"


def parse_stock_dividend(rows: list[str]) -> dict:
    ratio = _num(_cell(rows, "1. 1주당 배당주식수").split("|")[-1].strip())
    return {"newSharesPerOldShare": ratio, "recordDate": _date(_cell(rows, "4. 배당기준일")),
            "fractionalShares": "CASH_AT_PRIOR_DAY_CLOSE_STATED" if any("단수주" in r for r in rows) else None}


def parse_bonus_issue(rows: list[str]) -> dict:
    return {"newSharesPerOldShare": _num(_cell(rows, "5. 1주당 신주배정 주식수").split("|")[-1].strip()),
            "recordDate": _date(_cell(rows, "4. 신주배정기준일")),
            "newShareListingDate": _date(_cell(rows, "8. 신주의 상장 예정일"))}


def parse_merger(rows: list[str]) -> dict:
    ratio = _cell(rows, "4. 합병비율")
    m = re.search(r"보통주\s*1\s*:\s*([0-9.]+)", ratio)
    if not m:
        raise ValueError("MERGER_RATIO_NOT_PARSED")
    return {"successorSharesPerOldShare": float(m[1]), "ratioText": ratio.split("|", 1)[1].strip(),
            "mergerDate": _date(_cell(rows, "합병기일")), "newShareListingDate": _date(_cell(rows, "신주의 상장예정일"))}


def parse_spin_off(rows: list[str]) -> dict:
    ratio = _cell(rows, "4. 분할비율")
    keep = re.search(r"(?:분할되는회사|분할존속회사)\s*:\s*([0-9.]+)", ratio)
    new = re.search(r"(?:신설회사|분할신설회사)\s*:\s*([0-9.]+)", ratio)
    alloc = next(r for r in rows if r.startswith("신주배정조건"))
    par = re.search(r"([\d,]+)원\s*\(분할 전 1주의 금액\)\s*/\s*([\d,]+)원|1주의 금액\s*([\d,]+)원을\s*분할신설회사의\s*1주의\s*금액\s*([\d,]+)원", alloc)
    if not (keep and new and par):
        raise ValueError("SPIN_OFF_TERMS_NOT_PARSED")
    old_par, new_par = (_num(par[1]), _num(par[2])) if par[1] else (_num(par[3]), _num(par[4]))
    split_new = float(new[1])
    return {"retainedSharesPerOldShare": float(keep[1]), "spinOffRatio": split_new, "parRatio": old_par / new_par,
            "newCompanySharesPerOldShare": round(split_new * old_par / new_par, 7),
            "capitalReductionPct": _num(_cell(rows, "8. 감자에 관한 사항 | 감자비율").split("|")[-1].strip()),
            "recordDate": _date(_cell(rows, "신주배정기준일")),
            "splitDate": _date(_cell(rows, "분할기일"))}


DPS_MISSING = {"ticker": "034020.KS", "eventEntry": "2018-07-27", "exDate": "2018-12-27",
               "rceptNo": "20190213800934",
               "recordedBodySha256": "c579a6c2b8806af40ee271daa9317afa9d0ac2810e458d089c9afb44b576ec37"}


def parse_common_cash_dps(rows: list[str]) -> dict:
    """A '-' common DPS next to a stated class-share DPS is a STATED zero for the listed common share, not a
    missing value. Anything else is left unresolved."""
    common = _cell(rows, "3. 1주당 배당금(원) | 보통주식").split("|")[-1].strip()
    other = next((r.split("|")[-1].strip() for r in rows if r.startswith("종류주식 |")), None)
    if common == "-" and other not in (None, "", "-"):
        return {"commonDpsKrw": 0.0, "classShareDpsKrw": _num(other), "status": "COMMON_ZERO_STATED_CLASS_SHARE_ONLY"}
    if common not in ("", "-"):
        return {"commonDpsKrw": _num(common), "status": "COMMON_DPS_STATED"}
    return {"commonDpsKrw": None, "status": "UNRESOLVED"}


def list_filings(client: DartClient, corp: str, start: str, end: str) -> list[dict]:
    rows, page = [], 1
    while True:
        raw, _ = client.get("list.json", {"corp_code": corp, "bgn_de": start, "end_de": end,
                                          "page_no": page, "page_count": 100})
        data = json.loads(raw)
        if data.get("status") == "013":
            return rows
        if data.get("status") != "000":
            raise RuntimeError(f"LIST_REFUSED:{data.get('status')}")
        rows += data["list"]
        if page >= int(data["total_page"]):
            return rows
        page += 1


def successor_presence(signal_history_ref: str) -> dict:
    """(ticker, date) presence only: first/last bar date and count per successor. No price is read."""
    found: dict[str, list[str]] = {}
    for year in range(2016, 2027):
        try:
            blob = subprocess.run(["git", "-C", str(ROOT), "show",
                                   f"{signal_history_ref}:ledger/prices/kr/krx-prices-{year}.jsonl.gz"],
                                  capture_output=True, check=True).stdout
        except subprocess.CalledProcessError:
            continue
        for line in gzip.decompress(blob).splitlines():
            row = json.loads(line)
            ticker = row["ticker"] if "." in row["ticker"] else row["ticker"] + ".KS"
            if ticker in SUCCESSORS:
                found.setdefault(ticker, []).append(row["date"])
    return {t: {"name": SUCCESSORS[t], "bars": len(found.get(t, [])),
                "first": min(found[t]) if found.get(t) else None, "last": max(found[t]) if found.get(t) else None}
            for t in SUCCESSORS}


def build(client: DartClient, signal_history_ref: str) -> dict:
    events = []
    for ev in EVENTS:
        rec = {k: ev[k] for k in ("ticker", "name", "entry", "kind")}
        bodies = []
        for receipt in ev["receipts"]:
            raw, info = B.document_body(client, receipt)
            bodies.append({"rceptNo": receipt, "receiptDate": f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}",
                           "zipSha256": info["zipSha256"], "bodySha256": info["bodySha256"]})
            rows = _rows(raw)
            if ev.get("recordedBodySha256") and info["bodySha256"] != ev["recordedBodySha256"]:
                raise ValueError("BODY_DIFFERS_FROM_#320_RECEIPT:" + receipt)
        rec["sources"] = bodies
        kind = ev["kind"]
        if kind == "STOCK_DIVIDEND":
            rec["terms"] = parse_stock_dividend(rows)
            rec["bodyMatchesPR320Receipt"] = True
            rec["status"] = "TERMS_CITED_EXACT_ADJUSTMENT"
        elif kind == "BONUS_ISSUE":
            rec["terms"] = parse_bonus_issue(rows)
            rec["status"] = "TERMS_CITED_EXACT_ADJUSTMENT"
        elif kind == "TERMINAL_MERGER":
            terms = parse_merger(rows)
            src = bodies[0]
            rec["terms"] = terms
            rec["record"] = T.build_record(
                old_security=ev["ticker"], action_type=T.MERGER_STOCK, old_issuer_corp_code=ev["corp"],
                decision_date="2016-09-12", effective_date=terms["mergerDate"],
                successor_security="051910.KS", successor_shares_per_old_share=terms["successorSharesPerOldShare"],
                source_receipt_number=src["rceptNo"], source_receipt_date=src["receiptDate"],
                sources=(src["rceptNo"],), unresolved_fields=("fractionalShareTreatment", "cashInLieuRule"))
            rec["amendment"] = {"rceptNo": ev["amendmentNotServed"],
                                "status": "DOCUMENT_XML_STATUS_014_FILE_NOT_SERVED",
                                "note": "the 2016-12-14 correction body is not served; the ratio is taken from the original decision and the correction's content is UNVERIFIED"}
            rec["status"] = "TERMINAL_CONSIDERATION_CITED"
        elif kind == "SPIN_OFF":
            terms = parse_spin_off(rows)
            src = bodies[0]
            successor = "475150.KS" if ev["ticker"] == "210980.KS" else "0126Z0.KS"
            rec["terms"] = terms
            rec["considerationComponents"] = [
                T.build_consideration_component(component_type=T.COMPONENT_SUCCESSOR_SHARES,
                                                successor_security=ev["ticker"],
                                                shares_per_old_share=terms["retainedSharesPerOldShare"],
                                                source_receipt_number=src["rceptNo"], source_receipt_date=src["receiptDate"]),
                T.build_consideration_component(component_type=T.COMPONENT_SUCCESSOR_SHARES,
                                                successor_security=successor,
                                                shares_per_old_share=terms["newCompanySharesPerOldShare"],
                                                source_receipt_number=src["rceptNo"], source_receipt_date=src["receiptDate"])]
            rec["status"] = "TERMS_CITED_EXACT_ADJUSTMENT"
        elif kind == "TERMINAL":
            filings = list_filings(client, ev["corp"], *ev["listWindow"])
            hits = [{"rceptNo": f["rcept_no"], "date": f["rcept_dt"], "title": f["report_nm"].strip()}
                    for f in filings if any(k in f["report_nm"] for k in TERMINAL_KEYWORDS)]
            rec["issuerFilingsListed"] = len(filings)
            rec["terminalKeywordFilings"] = hits
            rec["status"] = "NO_CONSIDERATION_FILED"
            rec["note"] = ("the issuer filed only impairment / delisting-risk notices; no merger, exchange, tender or "
                           "liquidation-distribution decision exists. Holders kept unlisted shares after the "
                           "liquidation-trading period. No term can be cited, so no upper bound exists from DART")
        events.append(rec)
    resolved = sum(1 for e in events if e["status"] != "NO_CONSIDERATION_FILED")
    # The single B1 H126 in-window cash dividend counted as `dpsMissing` (b1-input-assembly.json): located from
    # calendar + event dates + the #320 dividend records only (034020.KS, entry 2018-07-27, ex 2018-12-27).
    raw, info = B.document_body(client, DPS_MISSING["rceptNo"])
    if info["bodySha256"] != DPS_MISSING["recordedBodySha256"]:
        raise ValueError("BODY_DIFFERS_FROM_#320_RECEIPT:" + DPS_MISSING["rceptNo"])
    dps = {**DPS_MISSING, **parse_common_cash_dps(_rows(raw)), "zipSha256": info["zipSha256"]}
    return {
        "contract": "B1_UNBOUNDED_EVENT_SOURCES_V1",
        "population": "b1-admission-status-v2.json eventsWithUnboundedUpside_B1_H126 (8 matured B1 H126 events)",
        "readsReturns": False, "priceValuesRead": 0,
        "signalHistoryRef": signal_history_ref,
        "successorBarPresence": successor_presence(signal_history_ref),
        "events": events,
        "dpsMissingInWindowCashDividend": dps,
        "summary": {"events": len(events), "termsCitedFromDart": resolved,
                    "stillUnbounded": [e["name"] for e in events if e["status"] == "NO_CONSIDERATION_FILED"]},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--signal-history-ref", default="origin/signal-history")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args(argv)
    ref = subprocess.run(["git", "-C", str(ROOT), "rev-parse", args.signal_history_ref],
                         capture_output=True, text=True, check=True).stdout.strip()
    out_client = DartClient(args.cache, pause=0.3, offline=args.offline)
    out = build(out_client, ref)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**out["summary"], "dartCalls": out_client.calls}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
