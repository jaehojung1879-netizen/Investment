"""Does DART give us what point-in-time value and quality actually need?

WHY A PROBE AND NOT A PIPELINE. The replay has run 713 dates and tested the
production model on exactly ZERO of them: `fullProductionFidelityDates` is 0
because value and quality need financial statements as they were VISIBLE on the
date, and no such source is wired in. So the -4.24%/yr and
`INDISTINGUISHABLE_FROM_RANDOM` currently on record are verdicts on the
price-only half of the model, not on the model.

DART could close the Korean half. But the whole plan rests on assumptions about
an API this sandbox cannot reach, and writing a parser against guessed response
shapes is how a week disappears. So this measures first: it calls DART with the
real key, in CI, and reports what actually comes back.

WHAT DECIDES THE ANSWER, IN ORDER. Any one of these failing kills or reshapes
the plan, so each is checked separately and reported separately:

  1. PUBLICATION DATE. Point-in-time is not "the numbers for Q1 2015" — it is
     "the numbers a reader could see on 2015-06-30". A filing describes a period
     that ended months before it was submitted, and using it from the period end
     is a look-ahead of exactly that gap. `available_from` must come from the
     receipt date. If the response carries no receipt date, there is no PIT and
     the rest does not matter.

  2. HOW FAR BACK. The replay starts 2013-01. A source that begins in 2015
     leaves the first two years dark, which is not fatal but has to be known
     before anyone promises a decade of four-sleeve history.

  3. THE ACCOUNTS THEMSELVES. `longterm.score_cross_section` needs specific
     inputs: earnings/book/FCF per share for value, and ROE, margins, growth
     and leverage for quality. Financial statements state none of them directly
     — every one is derived from line items, and a line item the filing does
     not carry is a factor that stays dark.

  4. RATE LIMIT AND VOLUME. ~200 names x 13 years x 4 reports is ~10,000 calls.
     Whether that fits in a day's quota decides whether this is one job or a
     backfill campaign.

Nothing is written to the ledger and no artifact changes. This reports.

Usage:  python scripts/probe_dart_fundamentals.py [--output probe.json]
        [--samples 005930,000660,035420]
        DART_API_KEY must be in the environment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import urllib.request  # noqa: E402
import urllib.error  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
# Quarterly report codes: Q1, H1, Q3, annual.
REPORT_CODES = {"11013": "1분기", "11012": "반기", "11014": "3분기", "11011": "사업"}

# What each production factor needs, and the statement line items it is built
# from. Written out because "DART has financial statements" is not the same
# claim as "DART has what the model reads", and only the second one matters.
FACTOR_INPUTS = {
    "value · earningsYield":  ["당기순이익", "주식수"],
    "value · bookYield":      ["자본총계", "주식수"],
    "value · fcfYield":       ["영업활동현금흐름", "유형자산의취득", "주식수"],
    "quality · roe":          ["당기순이익", "자본총계"],
    "quality · opMargin":     ["영업이익", "매출액"],
    "quality · profitMargin": ["당기순이익", "매출액"],
    "quality · debtToEquity": ["부채총계", "자본총계"],
    "quality · earningsGrowth": ["당기순이익", "전기 당기순이익"],
}

# Account names as DART labels them, with the aliases seen across filers.
WANTED_ACCOUNTS = {
    "매출액": ("매출액", "수익(매출액)", "영업수익"),
    "영업이익": ("영업이익", "영업이익(손실)"),
    "당기순이익": ("당기순이익", "당기순이익(손실)", "당기순이익(손실)귀속"),
    "자본총계": ("자본총계",),
    "부채총계": ("부채총계",),
    "자산총계": ("자산총계",),
    "영업활동현금흐름": ("영업활동현금흐름", "영업활동으로인한현금흐름"),
}


def call(path: str, params: dict, timeout: int = 30) -> tuple[dict | None, str]:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}/{path}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:                          # pragma: no cover - network
        return None, f"{type(exc).__name__}: {exc}"
    try:
        return json.loads(raw.decode("utf-8")), ""
    except ValueError:
        return None, f"non-JSON response ({len(raw)} bytes)"


# DART status codes worth naming, because "000이 아님"은 진단이 아니다.
STATUS_MEANING = {
    "000": "정상",
    "010": "등록되지 않은 키",
    "011": "사용할 수 없는 키 (등록 대기/정지)",
    "012": "접근할 수 없는 IP",
    "013": "조회된 데이터 없음",
    "014": "파일이 존재하지 않음",
    "020": "요청 제한 초과 (일일 한도)",
    "021": "조회 가능한 회사 개수 초과",
    "100": "필드의 부적절한 값",
    "800": "시스템 점검 중",
    "900": "정의되지 않은 오류",
    "901": "사용자 계정의 개인정보 보유기간 만료",
}


def describe(status: str | None) -> str:
    return f"{status} ({STATUS_MEANING.get(str(status), '알 수 없는 코드')})"


def receipt_date(row: dict) -> str | None:
    """The date the filing was received — the only thing that licenses use.

    DART states it in `rcept_no`, whose first 8 digits are YYYYMMDD. That is
    the field the whole plan hangs on: without it a filing has a period but no
    visibility date, and the replay would be reading Q1 numbers in April that
    nobody could see until May.
    """
    number = str(row.get("rcept_no") or "")
    head = number[:8]
    return head if len(head) == 8 and head.isdigit() else None


def probe_statements(key: str, corp_code: str, year: int, code: str) -> dict:
    payload, error = call("fnlttSinglAcntAll.json", {
        "crtfc_key": key, "corp_code": corp_code,
        "bsns_year": str(year), "reprt_code": code, "fs_div": "CFS"})
    out = {"year": year, "reportCode": code, "reportName": REPORT_CODES.get(code, code)}
    if payload is None:
        out["error"] = error
        return out
    status = payload.get("status")
    out["status"] = describe(status)
    rows = payload.get("list") or []
    out["rows"] = len(rows)
    if status != "000" or not rows:
        return out

    dates = {receipt_date(row) for row in rows}
    dates.discard(None)
    out["receiptDates"] = sorted(dates)
    out["hasReceiptDate"] = bool(dates)

    names = {str(row.get("account_nm") or "").replace(" ", "") for row in rows}
    found = {}
    for label, aliases in WANTED_ACCOUNTS.items():
        hit = next((a for a in aliases if a.replace(" ", "") in names), None)
        found[label] = hit
    out["accounts"] = found
    out["accountsFound"] = sum(1 for v in found.values() if v)
    out["accountsWanted"] = len(WANTED_ACCOUNTS)
    # A period end alongside the receipt date is what makes the lag measurable.
    sample = rows[0]
    out["periodEnd"] = sample.get("thstrm_dt") or sample.get("bsns_de")
    out["sampleKeys"] = sorted(sample.keys())[:18]
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="dart-probe.json")
    parser.add_argument("--samples", default="005930,000660,035420",
                        help="stock codes: 삼성전자, SK하이닉스, NAVER")
    parser.add_argument("--from-year", type=int, default=2013)
    parser.add_argument("--to-year", type=int, default=2025)
    args = parser.parse_args(argv)

    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("ERROR: DART_API_KEY not in the environment; nothing probed.")
        return 1
    print(f"key present, {len(key)} chars\n")

    report: dict = {"probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "factorInputs": FACTOR_INPUTS}

    # --- 1. does the key work at all -------------------------------------- #
    payload, error = call("list.json", {"crtfc_key": key, "bgn_de": "20240101",
                                        "end_de": "20240107", "page_count": "10"})
    if payload is None:
        print(f"ERROR: could not reach DART — {error}")
        report["reachable"] = False
        report["error"] = error
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
        return 1
    status = payload.get("status")
    report["reachable"] = True
    report["keyStatus"] = describe(status)
    print(f"1. 키 확인          {describe(status)}")
    if status not in ("000", "013"):
        print("   키가 동작하지 않습니다. 나머지 항목은 의미가 없어 중단합니다.")
        report["message"] = payload.get("message")
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
        return 1

    # --- 2. corp_code mapping --------------------------------------------- #
    # Every statement call is keyed by corp_code, not the stock ticker, so the
    # mapping file is a hard dependency rather than a convenience.
    try:
        with urllib.request.urlopen(
                f"{BASE}/corpCode.xml?crtfc_key={key}", timeout=60) as response:
            blob = response.read()
        report["corpCodeBytes"] = len(blob)
        report["corpCodeLooksLikeZip"] = blob[:2] == b"PK"
        print(f"2. corp_code 목록   {len(blob):,} bytes, "
              f"{'ZIP 정상' if blob[:2] == b'PK' else 'ZIP 아님 — 확인 필요'}")
        codes = {}
        if blob[:2] == b"PK":
            import io, zipfile, xml.etree.ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                xml = archive.read(archive.namelist()[0])
            root = ET.fromstring(xml)
            for item in root.iter("list"):
                stock = (item.findtext("stock_code") or "").strip()
                if stock:
                    codes[stock] = (item.findtext("corp_code") or "").strip()
            report["listedCompaniesMapped"] = len(codes)
            print(f"   상장사 매핑        {len(codes):,}개")
    except Exception as exc:                          # pragma: no cover - network
        codes = {}
        report["corpCodeError"] = f"{type(exc).__name__}: {exc}"
        print(f"2. corp_code 목록   실패 — {exc}")

    # --- 3. statements, per sample name, across the replay window --------- #
    samples = [s.strip() for s in args.samples.split(",") if s.strip()]
    report["samples"] = {}
    print("\n3. 재무제표 — 리플레이 구간 전체에서")
    for stock in samples:
        corp = codes.get(stock)
        entry: dict = {"stockCode": stock, "corpCode": corp}
        if not corp:
            entry["error"] = "corp_code 매핑 없음"
            report["samples"][stock] = entry
            print(f"   {stock}  corp_code 없음 — 건너뜀")
            continue
        years: list[dict] = []
        for year in range(args.from_year, args.to_year + 1):
            row = probe_statements(key, corp, year, "11011")   # 사업보고서
            years.append(row)
            time.sleep(0.15)
        entry["byYear"] = years
        served = [r for r in years if r.get("rows")]
        entry["firstYearServed"] = served[0]["year"] if served else None
        entry["yearsServed"] = len(served)
        entry["withReceiptDate"] = sum(1 for r in served if r.get("hasReceiptDate"))
        report["samples"][stock] = entry
        first = entry["firstYearServed"]
        print(f"   {stock}  응답 연도 {len(served)}/{len(years)}  "
              f"최초 {first}  접수일자 보유 {entry['withReceiptDate']}/{len(served)}")
        if served:
            acc = served[-1].get("accounts") or {}
            missing = [k for k, v in acc.items() if not v]
            print(f"          계정 {served[-1]['accountsFound']}/{served[-1]['accountsWanted']}"
                  + (f"  누락: {', '.join(missing)}" if missing else "  전부 확보"))

    # --- 4. quarterly granularity ----------------------------------------- #
    print("\n4. 분기 보고서 (연간 말고 분기가 되는지)")
    quarterly = {}
    if samples and codes.get(samples[0]):
        for code, name in REPORT_CODES.items():
            row = probe_statements(key, codes[samples[0]], 2023, code)
            quarterly[name] = {"rows": row.get("rows"), "status": row.get("status"),
                               "receiptDates": row.get("receiptDates"),
                               "periodEnd": row.get("periodEnd")}
            print(f"   {name:<5} rows {row.get('rows')}  "
                  f"접수일 {(row.get('receiptDates') or ['—'])[0]}  "
                  f"기간말 {row.get('periodEnd')}")
            time.sleep(0.15)
    report["quarterly"] = quarterly

    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --- verdict ----------------------------------------------------------- #
    served_all = [e for e in report["samples"].values() if e.get("yearsServed")]
    has_dates = all(e.get("withReceiptDate") == e.get("yearsServed") for e in served_all)
    earliest = min((e["firstYearServed"] for e in served_all
                    if e.get("firstYearServed")), default=None)
    print("\n=== 판정 ===")
    print(f"  접수일자(=공시 시점) 확보 : {'예' if has_dates and served_all else '아니오'}")
    print(f"  가장 이른 응답 연도       : {earliest}  (리플레이 시작 {args.from_year})")
    if not has_dates or not served_all:
        print("  → 공시 시점이 없으면 point-in-time이 성립하지 않습니다. 여기서 멈춥니다.")
    elif earliest and earliest > args.from_year:
        print(f"  → {args.from_year}~{earliest - 1}년 한국 밸류·퀄리티는 비어 있게 됩니다.")
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
