"""Outcome-blind source-eligibility probe for KR insider ownership filings (DART D002).

Question answered (and nothing else): can the information "an executive or major
shareholder of a PIT Top-120 issuer reported an OPEN-MARKET purchase" be built
point-in-time for 2013-2026 from free official sources, at what density, and with
what parse reliability?

It never reads a price after a filing, a return, a label or a model output.
Counts only. Two DART endpoints are used:

* ``list.json`` with ``pblntf_ty=D`` per issuer-year, walked to its last page, keeping
  rows whose ``report_nm`` contains 임원ㆍ주요주주특정증권등소유상황보고서. (A first run
  passed ``pblntf_detail_ty=D002`` with ``page_count=1``; the served rows included
  5%-rule 대량보유 reports, so the sub-filter was not honoured and that run's counts were
  discarded. Report-name filtering is applied here instead.)
* ``document.xml`` for a stratified subset of those receipts: is the per-transaction
  table (보고사유 / 변동일 / 증감 / 취득·처분 단가) present and parseable?

Usage::

    python research/alpha_evidence_sprint_v2/kr_insider_probe.py --out <dir> [--issuers 24] [--docs-per-year 2]

The sample of issuers is the first N corp codes ordered by sha256(corp_code), drawn
from the 254 ever-Top-120 DART issuers already collected by alpha-mechanism-sprint-v1.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

LIST = "https://opendart.fss.or.kr/api/list.json"
DOC = "https://opendart.fss.or.kr/api/document.xml"
YEARS = tuple(range(2013, 2027))
SPRINT1 = Path(__file__).resolve().parents[1] / "alpha_mechanism_sprint_v1" / "data" / "dart-list"

# Reason labels as they appear in the 세부변동내역 table of the filing. Matching is a
# reading list for counting, never a classification verdict about any filing.
INSIDER_REPORT = "임원ㆍ주요주주특정증권등소유상황보고서"
# Exact signed reason labels of the 세부변동내역 table. Generic words such as "기타" are not
# counted: they occur in boilerplate and would make every filing look like a match.
OPEN_MARKET_BUY = ("장내매수(+)",)
OPEN_MARKET_SELL = ("장내매도(-)",)
NON_MARKET = ("증여(+)", "증여(-)", "상속(+)", "신규선임(+)", "신규상장(+)", "유상신주취득(+)",
              "무상신주취득(+)", "주식매수선택권행사(+)", "장외매수(+)", "장외매도(-)", "신규보고(+)")
HEADER_TOKENS = ("보고사유", "변동일", "증감")
PRICE_TOKENS = ("취득/처분 단가", "취득·처분 단가", "단가")


def issuer_sample(n: int) -> list[str]:
    corps = sorted({p.name.split("-")[0] for p in SPRINT1.glob("*-A.jsonl.gz")})
    return sorted(corps, key=lambda c: hashlib.sha256(c.encode()).hexdigest())[:n]


def classify_reasons(text: str) -> dict:
    """Count reason tokens in decoded filing text. Pure; tested on synthetic text."""
    def count(tokens):
        return sum(len(re.findall(re.escape(t), text)) for t in tokens)
    return {
        "headerPresent": all(t in text for t in HEADER_TOKENS),
        "pricePresent": any(t in text for t in PRICE_TOKENS),
        "openMarketBuy": count(OPEN_MARKET_BUY),
        "openMarketSell": count(OPEN_MARKET_SELL),
        "nonMarket": count(NON_MARKET),
    }


def decode_zip(payload: bytes) -> str | None:
    if not payload.startswith(b"PK"):
        return None
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        parts = []
        for name in sorted(z.namelist()):
            raw = z.read(name)
            for enc in ("utf-8", "cp949", "euc-kr"):
                try:
                    parts.append(raw.decode(enc))
                    break
                except UnicodeDecodeError:
                    continue
        text = "\n".join(parts)
    return re.sub(r"<[^>]+>", " ", text)


def get(url: str, params: dict, timeout: int = 60) -> bytes:
    full = url + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(full, timeout=timeout) as response:
                return response.read()
        except Exception as error:  # noqa: BLE001 - recorded, never swallowed silently
            last = error
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{type(last).__name__}: {str(last)[:200]}")


def reparse(probe_path: Path, out: Path, key: str) -> dict:
    """Structured parse (kr_insider.parse_transactions) of the documents a density run sampled.

    Records, per original insider filing: parse success, detail-row count, every reason
    label/code pair seen, open-market net sign, and the lag from the latest transaction
    date to the DART receipt date. Reads no price after the filing and no return.
    """
    import collections
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from research.alpha_evidence_sprint_v2 import kr_insider as K
    probe = json.loads(gzip.open(probe_path, "rt", encoding="utf-8").read())
    docs = [d for d in probe["documents"] if K.INSIDER_REPORT in d["report_nm"] and "정정" not in d["report_nm"]]
    labels, results, calls = collections.Counter(), [], 0
    for d in docs:
        try:
            payload = get(DOC, {"crtfc_key": key, "rcept_no": d["rcept_no"]})
            calls += 1
        except RuntimeError as error:
            results.append({"rcept_no": d["rcept_no"], "status": "FETCH_ERROR", "error": str(error)})
            continue
        if not payload.startswith(b"PK"):
            results.append({"rcept_no": d["rcept_no"], "status": "NOT_A_ZIP"})
            continue
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            text = "\n".join(K.decode(z.read(n)) for n in sorted(z.namelist()))
        try:
            rows = K.parse_transactions(text)
        except K.ParseError as error:
            results.append({"rcept_no": d["rcept_no"], "year": d["year"], "status": "PARSE_ERROR", "error": str(error)})
            continue
        for r in rows:
            labels[f'{r["reasonLabel"]}|{r["reasonCode"]}|{r["securityLabel"]}'] += 1
        net = K.open_market_net(rows)
        latest = max((r["date"] for r in rows), default=None)
        lag = None
        if latest and d.get("rcept_dt"):
            from datetime import date as _d
            rd = d["rcept_dt"]
            lag = (_d(int(rd[:4]), int(rd[4:6]), int(rd[6:])) - _d.fromisoformat(latest)).days
        results.append({"rcept_no": d["rcept_no"], "year": d["year"], "status": "PARSED", "rows": len(rows),
                        "openMarketSign": (net["netShares"] > 0) - (net["netShares"] < 0),
                        "openMarketRows": sum(1 for r in rows if r["reasonLabel"] in (K.BUY_LABEL, K.SELL_LABEL)),
                        "receiptLagDaysFromLatestTransaction": lag})
    summary = {"probe": "kr-insider-structured-parse-v1", "evidenceClass": "OUTCOME_BLIND_SOURCE_PROBE",
               "documentCalls": calls, "originalsSampled": len(docs),
               "parsed": sum(1 for r in results if r["status"] == "PARSED"),
               "reasonLabelCodeSecurity": dict(labels.most_common()), "documents": results,
               "returnsRead": 0, "pricesAfterFilingRead": 0}
    (out / "kr-insider-structured-parse.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1,
                                                                     sort_keys=True) + "\n")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reparse", help="structured re-parse of a density run's sampled originals")
    ap.add_argument("--issuers", type=int, default=24)
    ap.add_argument("--docs-per-year", type=int, default=2)
    args = ap.parse_args(argv)
    key = os.environ.get("DART_API_KEY")
    if not key:
        raise SystemExit("DART_API_KEY_REQUIRED")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.reparse:
        summary = reparse(Path(args.reparse), out, key)
        print(json.dumps({k: summary[k] for k in ("documentCalls", "originalsSampled", "parsed")}))
        return 0
    calls = {"list": 0, "document": 0}
    density, receipts, errors = [], [], []
    for corp in issuer_sample(args.issuers):
        for year in YEARS:
            rows, page, total, status = [], 1, 0, None
            while True:
                params = {"crtfc_key": key, "corp_code": corp, "bgn_de": f"{year}0101", "end_de": f"{year}1231",
                          "pblntf_ty": "D", "page_no": page, "page_count": 100}
                try:
                    payload = json.loads(get(LIST, params))
                    calls["list"] += 1
                except RuntimeError as error:
                    errors.append({"corp": corp, "year": year, "page": page, "endpoint": "list.json",
                                   "error": str(error)})
                    status = "ERROR"
                    break
                status = payload.get("status")
                if status != "000":
                    break
                total = int(payload.get("total_count") or 0)
                rows.extend(payload.get("list") or [])
                if page >= int(payload.get("total_page") or 1):
                    break
                page += 1
            insider = [r for r in rows if INSIDER_REPORT in (r.get("report_nm") or "")]
            density.append({"corp": corp, "year": year, "status": status, "allEquityDisclosures": total,
                            "rowsServed": len(rows), "insiderReports": len(insider),
                            "insiderAmendments": sum(1 for r in insider if "정정" in r.get("report_nm", ""))})
            for row in insider:
                if "정정" in row.get("report_nm", ""):
                    continue
                receipts.append({"corp": corp, "year": year, "rcept_no": row.get("rcept_no"),
                                 "rcept_dt": row.get("rcept_dt"), "report_nm": row.get("report_nm")})
    # stratified document sample: per year, the first k receipts ordered by sha256(rcept_no)
    sample = []
    for year in YEARS:
        rows = sorted((r for r in receipts if r["year"] == year and r["rcept_no"]),
                      key=lambda r: hashlib.sha256(r["rcept_no"].encode()).hexdigest())
        sample.extend(rows[:args.docs_per_year])
    parsed = []
    for row in sample:
        try:
            payload = get(DOC, {"crtfc_key": key, "rcept_no": row["rcept_no"]})
            calls["document"] += 1
        except RuntimeError as error:
            errors.append({"rcept_no": row["rcept_no"], "endpoint": "document.xml", "error": str(error)})
            continue
        text = decode_zip(payload)
        entry = {**row, "zip": text is not None, "bytes": len(payload),
                 "sha256": hashlib.sha256(payload).hexdigest()}
        if text is not None:
            entry.update(classify_reasons(text))
        else:
            entry["sourceMessage"] = payload[:200].decode("utf-8", "replace")
        parsed.append(entry)
    result = {"probe": "kr-insider-d002-source-eligibility-v2", "evidenceClass": "OUTCOME_BLIND_SOURCE_PROBE",
              "calls": calls, "issuers": args.issuers, "years": [YEARS[0], YEARS[-1]],
              "density": density, "documents": parsed, "errors": errors,
              "returnsRead": 0, "labelsBuilt": 0, "pricesAfterFilingRead": 0}
    with gzip.open(out / "kr-insider-probe.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, sort_keys=True)
    print(json.dumps({"calls": calls, "density": len(density), "documents": len(parsed), "errors": len(errors)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
