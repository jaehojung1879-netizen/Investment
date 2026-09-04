"""Does Financial Modeling Prep give the US half what DART gave the Korean
half — free (within a daily quota), and reachable from GitHub Actions where
SEC itself was not?

WHY THIS AND NOT SEC DIRECTLY. Two probes against sec.gov — the XBRL
companyfacts API and the bulk Financial Statement Data Sets, two different
hosts and two very different traffic shapes — both came back with live SEC
block pages ("Your Request Originates from an Undeclared Automated Tool",
"Request Rate Threshold Exceeded"), and a screenshot confirmed the already-
shipped 13F reader falling back to its cached snapshot the same day on the
same GitHub Actions IP pool. That reads as a site-wide policy, not a fixable
request pattern. FMP is not sec.gov: a different host, different
infrastructure, and — unlike SEC's per-IP fair-access policy — a per-key
daily quota, so whether IT is reachable from here is a clean, separate
question rather than a guess extended from SEC's answer.

WHAT DECIDES THE ANSWER, same standard as every probe before this one:

  1. FILING DATE. FMP's statement endpoints document `fillingDate` (SEC's own
     accepted-filing date, carried through) alongside `date` (the period
     end). Without it there is no point-in-time, same as DART's receipt date
     and SEC's `filed` — checked here, not assumed from the docs.
  2. CALLS PER TICKER. If one call with a high `limit` returns a company's
     full quarterly history, ~500 US names is a few thousand calls total —
     roughly a week at 250/day. If the free tier caps historical depth or
     needs one call per period, the same backfill could take months at this
     quota. This is the single number the "how long will this take" question
     from the plan turns on.
  3. THE ACCOUNTS THEMSELVES, under FMP's field names rather than DART's
     Korean labels or SEC's US-GAAP tags — including, if the income-statement
     response really does carry `weightedAverageShsOut`, whether the value
     sleeve needs a second endpoint at all the way DART needed a second SEC
     endpoint for shares outstanding.
  4. FREE-TIER LIMITS AS DATA. FMP is known to answer some free-tier
     restrictions with HTTP 200 and an error message in the response BODY
     rather than a non-200 status — so every response is inspected for that
     shape explicitly, not read as success just because the status was 200.

Nothing is written to the ledger. This reports.

Usage:  python scripts/probe_fmp_fundamentals.py [--output fmp-probe.json]
        [--samples AAPL,JPM,XOM,KO,O] [--limit 400]
        FMP_API_KEY must be in the environment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "https://financialmodelingprep.com/api/v3"
PACE_SECONDS = 0.3

STATEMENT_PATHS = {
    "income": "income-statement",
    "balance": "balance-sheet-statement",
    "cashflow": "cash-flow-statement",
}

# Several candidates per concept where the field name is not certain from
# documentation alone — the same discipline DART's WANTED_ACCOUNTS aliases
# and the SEC probe's CANDIDATE_TAGS used, because a vendor's schema is a
# claim to verify, not a fact to assume.
CANDIDATE_FIELDS = {
    "income": {
        "revenue": ["revenue"],
        "netIncome": ["netIncome"],
        "operatingIncome": ["operatingIncome"],
        "sharesOutstanding": ["weightedAverageShsOut", "weightedAverageShsOutDil"],
    },
    "balance": {
        "equity": ["totalStockholdersEquity", "totalEquity"],
        "liabilities": ["totalLiabilities"],
        "assets": ["totalAssets"],
    },
    "cashflow": {
        "operatingCashFlow": ["netCashProvidedByOperatingActivities", "operatingCashFlow"],
        "capex": ["capitalExpenditure"],
    },
}

FACTOR_INPUTS = {
    "value · earningsYield":  ["income.netIncome", "income.sharesOutstanding"],
    "value · bookYield":      ["balance.equity", "income.sharesOutstanding"],
    "value · fcfYield":       ["cashflow.operatingCashFlow", "cashflow.capex",
                               "income.sharesOutstanding"],
    "quality · roe":          ["income.netIncome", "balance.equity"],
    "quality · opMargin":     ["income.operatingIncome", "income.revenue"],
    "quality · profitMargin": ["income.netIncome", "income.revenue"],
    "quality · debtToEquity": ["balance.liabilities", "balance.equity"],
    "quality · earningsGrowth": ["income.netIncome (prior period)"],
}

# Common shapes FMP is known to use for a free-tier refusal delivered with a
# 200 status — a response that LOOKS like success until the body is read.
ERROR_BODY_KEYS = ("Error Message", "error", "message")


def _request(url: str, timeout: int = 30) -> tuple[int | None, bytes | None, str]:
    """One GET with bounded retries on transient failures. Returns
    (status_code, body, error) — status_code is None only when the request
    never got a response at all (network failure, not an HTTP error)."""
    last_error = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.getcode(), response.read(), ""
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read(2000)
            except Exception:                          # pragma: no cover - network
                pass
            last_error = f"HTTP {exc.code}"
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                return exc.code, body, last_error
        except Exception as exc:                      # pragma: no cover - network
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 2:
                return None, None, last_error
        time.sleep(1.5 * (2 ** attempt))
    return None, None, last_error


def parse_statement_response(kind: str, payload) -> dict:
    """Everything the probe reports about one statement's response, from the
    already-decoded JSON payload.

    Split from the network/decoding so this — the error-body shape, period
    count, filing-date coverage, which fields actually carry values — is the
    part pinned by a test.
    """
    if isinstance(payload, dict):
        message = next((str(payload[k]) for k in ERROR_BODY_KEYS if payload.get(k)), None)
        return {"errorBody": message or json.dumps(payload, ensure_ascii=False)[:200]}
    if not isinstance(payload, list):
        return {"errorBody": f"unexpected shape: {type(payload).__name__}"}
    if not payload:
        return {"periodCount": 0}

    entry: dict = {"periodCount": len(payload)}
    dates = sorted(str(row.get("date")) for row in payload if row.get("date"))
    if dates:
        entry["dateRange"] = [dates[0], dates[-1]]
    entry["fillingDateCoverage"] = sum(1 for row in payload if row.get("fillingDate"))

    fields_found: dict[str, dict] = {}
    for concept, candidates in CANDIDATE_FIELDS.get(kind, {}).items():
        hit = next((c for c in candidates if any(row.get(c) not in (None, "")
                                                   for row in payload)), None)
        fields_found[concept] = {"field": hit}
    entry["fieldsFound"] = fields_found
    entry["sampleRow"] = {k: payload[0].get(k) for k in
                          ("date", "period", "fillingDate", "acceptedDate")
                          if k in payload[0]}
    return entry


def probe_ticker(key: str, ticker: str, limit: int) -> dict:
    entry: dict = {}
    calls = 0
    for kind, path in STATEMENT_PATHS.items():
        params = urllib.parse.urlencode(
            {"period": "quarter", "limit": limit, "apikey": key})
        url = f"{BASE}/{path}/{ticker}?{params}"
        status, body, error = _request(url)
        calls += 1
        time.sleep(PACE_SECONDS)
        if body is None:
            entry[kind] = {"httpStatus": status, "error": error}
            continue
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            entry[kind] = {"httpStatus": status, "error": "non-JSON response"}
            continue
        parsed = parse_statement_response(kind, payload)
        parsed["httpStatus"] = status
        entry[kind] = parsed
    entry["calls"] = calls
    return entry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="fmp-probe.json")
    parser.add_argument("--samples", default="AAPL,JPM,XOM,KO,O")
    parser.add_argument("--limit", type=int, default=400,
                        help="quarters requested per call — high on purpose, "
                             "to measure how much history one call actually gives")
    args = parser.parse_args(argv)

    key = os.environ.get("FMP_API_KEY", "").strip()
    if not key:
        print("ERROR: FMP_API_KEY not in the environment; nothing probed.")
        return 1
    print(f"key present, {len(key)} chars\n")

    samples = [s.strip().upper() for s in args.samples.split(",") if s.strip()]
    report: dict = {"probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "factorInputs": FACTOR_INPUTS, "requestedLimit": args.limit,
                    "samples": {}}

    total_calls = 0
    for ticker in samples:
        print(f"=== {ticker} ===")
        entry = probe_ticker(key, ticker, args.limit)
        report["samples"][ticker] = entry
        total_calls += entry["calls"]
        for kind in STATEMENT_PATHS:
            info = entry[kind]
            if info.get("error") or info.get("errorBody"):
                print(f"  {kind:<9} 실패 — {info.get('error') or info.get('errorBody')}"
                      f" (HTTP {info.get('httpStatus')})")
                continue
            print(f"  {kind:<9} {info.get('periodCount')}개 기간 · "
                  f"범위 {info.get('dateRange')} · "
                  f"filed일 {info.get('fillingDateCoverage')}/{info.get('periodCount')}")
            missing = [k for k, v in (info.get("fieldsFound") or {}).items() if not v.get("field")]
            if missing:
                print(f"            누락: {', '.join(missing)}")
        print()

    report["totalCalls"] = total_calls
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== 판정 ===")
    print(f"  이번 프로브 호출 수 : {total_calls} (종목당 {total_calls // max(1, len(samples))})")
    ok_incomes = [e["income"] for e in report["samples"].values()
                 if not e["income"].get("error") and not e["income"].get("errorBody")]
    has_dates = ok_incomes and all(
        e.get("fillingDateCoverage") == e.get("periodCount") for e in ok_incomes)
    print(f"  filed일 전부 보유    : {'예' if has_dates else '아니오'}")
    if ok_incomes:
        earliest = min(e["dateRange"][0] for e in ok_incomes if e.get("dateRange"))
        print(f"  가장 이른 기간       : {earliest}  (리플레이 시작 2013-01)")
        per_ticker_calls = total_calls / max(1, len(samples))
        est_full_universe = int(per_ticker_calls * 500)
        est_days = -(-est_full_universe // 250)
        print(f"  전체 500종목 추정 호출: {est_full_universe:,} · "
              f"하루 250회면 약 {est_days}일")
    if not ok_incomes:
        print("  → 전부 실패했습니다. 키 또는 무료 티어 제한을 확인하십시오.")
    print(f"\nwrote {args.output}")
    return 0 if ok_incomes else 1


if __name__ == "__main__":
    raise SystemExit(main())
