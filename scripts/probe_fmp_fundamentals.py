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

# FMP retired its `/api/v3/...` statement endpoints on 2025-08-31 — found
# live, not from documentation: the first real run got "Legacy Endpoint"
# on all three, HTTP 403, for an account created well after that date. The
# `/stable/...` endpoints are the replacement; `symbol` moves from the URL
# path to a query parameter.
BASE = "https://financialmodelingprep.com/stable"
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

# The filing date under BOTH spellings FMP has shipped. `/api/v3` carried a
# misspelt `fillingDate` for years; the `/stable` replacement spells it
# `filingDate`, and the first served response in this repo proved it — a
# probe that knew only the v3 spelling would have counted zero filing dates
# on a response that carried one in every row, and reported "no point-in-time"
# about a source that has it. Both are accepted; which one answered is
# reported rather than assumed.
FILING_DATE_FIELDS = ("filingDate", "fillingDate")


def filing_date_of(row: dict) -> tuple[str | None, str | None]:
    """(value, field name) for whichever filing-date spelling this row uses."""
    for field in FILING_DATE_FIELDS:
        value = row.get(field)
        if value:
            return str(value), field
    return None, None


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


def body_head(body: bytes | None, limit: int = 300) -> str:
    """What the vendor actually said, trimmed. Never dropped."""
    if not body:
        return ""
    return body[:limit].decode("utf-8", "replace").replace("\n", " ").strip()


# The same statement, asked for under both URL shapes. `/api/v3` was retired
# for statements on 2025-08-31 and `/stable` is the replacement, but a plan
# can expose them differently and "the path is wrong" and "the plan excludes
# it" are different problems with different fixes. Asked, not assumed.
BASES = {
    "stable": "https://financialmodelingprep.com/stable",
    "v3": "https://financialmodelingprep.com/api/v3",
}

# Endpoints a key on ANY live plan answers. Without one of these the probe
# cannot tell a dead key from a plan that excludes statements — and those
# point at completely different next moves.
LIVENESS = (
    ("profile", "stable", "profile", {"symbol": "AAPL"}),
    ("quote", "stable", "quote", {"symbol": "AAPL"}),
)


def check_liveness(key: str) -> dict:
    """Does this key work at all? Separates a dead key from a limited plan."""
    out = {}
    for name, base, path, params in LIVENESS:
        query = dict(params)
        query["apikey"] = key
        url = f"{BASES[base]}/{path}?{urllib.parse.urlencode(query)}"
        status, body, error = _request(url)
        time.sleep(PACE_SECONDS)
        served = status == 200 and bool(body) and body.lstrip()[:1] in (b"[", b"{")
        out[name] = {"httpStatus": status, "served": served,
                     "error": error or None, "bodyHead": body_head(body)}
    return out


def check_bases(key: str, ticker: str = "AAPL") -> dict:
    """One statement under each URL shape, so a path problem is ruled out."""
    out = {}
    for name, base in BASES.items():
        if name == "v3":
            url = (f"{base}/income-statement/{ticker}"
                   f"?{urllib.parse.urlencode({'period': 'quarter', 'limit': 4, 'apikey': key})}")
        else:
            url = (f"{base}/income-statement"
                   f"?{urllib.parse.urlencode({'symbol': ticker, 'period': 'quarter', 'limit': 4, 'apikey': key})}")
        status, body, error = _request(url)
        time.sleep(PACE_SECONDS)
        served = status == 200 and bool(body) and body.lstrip()[:1] in (b"[", b"{")
        out[name] = {"httpStatus": status, "served": served,
                     "error": error or None, "bodyHead": body_head(body)}
    return out


# How much history one call may ask for. The first run that got a 200 asked
# for 4 quarters and the run that got 402 on every ticker asked for 400 — the
# SAME endpoint, same key, same minute. That makes `limit` the variable, and
# a cap is a number to find, not a tier to infer from a status code.
LIMIT_LADDER = (4, 20, 50, 100, 200, 400)


def find_limit_cap(key: str, ticker: str = "AAPL",
                   ladder: tuple[int, ...] = LIMIT_LADDER) -> dict:
    """The largest `limit` this key is actually served, measured.

    Walks the ladder upward and stops at the first refusal: FMP's caps are
    monotonic (a plan that refuses 200 does not serve 400), so continuing
    past a refusal only spends quota. Reports the refusal's own body, because
    the vendor's sentence is the finding — the status code alone is what
    turned an unread 402 into "the free tier dropped statements".
    """
    rungs = []
    largest = None
    for limit in ladder:
        params = urllib.parse.urlencode(
            {"symbol": ticker, "period": "quarter", "limit": limit, "apikey": key})
        url = f"{BASE}/income-statement?{params}"
        status, body, error = _request(url)
        time.sleep(PACE_SECONDS)
        served = status == 200 and bool(body) and body.lstrip()[:1] in (b"[", b"{")
        periods = None
        if served:
            try:
                payload = json.loads(body.decode("utf-8"))
            except ValueError:
                payload = None
            if isinstance(payload, list):
                periods = len(payload)
            elif isinstance(payload, dict):
                served = False           # a 200 carrying an error body
        rungs.append({"limit": limit, "httpStatus": status, "served": served,
                      "periodsReturned": periods,
                      "error": error or None, "bodyHead": body_head(body)})
        if not served:
            break
        largest = limit
    return {"ladder": list(ladder), "rungs": rungs, "largestServed": largest,
            "refusedAt": next((r["limit"] for r in rungs if not r["served"]), None),
            "refusalBody": next((r["bodyHead"] for r in rungs if not r["served"]), None)}


def diagnose(liveness: dict, bases: dict) -> dict:
    """What the two checks together say the next move is.

    The distinction that matters: a key that works everywhere except the
    statement endpoints is a PLAN limit and the fix is a subscription; a key
    that works nowhere is a KEY problem and no subscription helps. A bare 402
    on statements alone cannot tell those apart, which is why the earlier run
    could only guess.
    """
    key_live = any(row.get("served") for row in liveness.values())
    statements_served = [name for name, row in bases.items() if row.get("served")]
    refused = {name: row.get("bodyHead") for name, row in bases.items()
               if not row.get("served")}
    if statements_served:
        return {"verdict": "STATEMENTS_AVAILABLE",
                "meaning": f"served under {statements_served}; the US route is open",
                "servedBases": statements_served}
    if key_live:
        return {"verdict": "KEY_LIVE_PLAN_EXCLUDES_STATEMENTS",
                "meaning": ("the key is answered on other endpoints and refused "
                            "on every statement URL shape, so this is the plan "
                            "rather than the key or the path — the refusal body "
                            "names what it wants"),
                "refusalBodies": refused}
    return {"verdict": "KEY_NOT_LIVE",
            "meaning": ("no endpoint answered, statement or otherwise, so the "
                        "key itself is the problem and no subscription changes "
                        "that"),
            "refusalBodies": refused}


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
    filing_hits = [filing_date_of(row) for row in payload]
    entry["fillingDateCoverage"] = sum(1 for value, _ in filing_hits if value)
    entry["fillingDateField"] = next((f for _, f in filing_hits if f), None)
    entry["acceptedDateCoverage"] = sum(1 for row in payload if row.get("acceptedDate"))

    fields_found: dict[str, dict] = {}
    for concept, candidates in CANDIDATE_FIELDS.get(kind, {}).items():
        hit = next((c for c in candidates if any(row.get(c) not in (None, "")
                                                   for row in payload)), None)
        fields_found[concept] = {"field": hit}
    entry["fieldsFound"] = fields_found
    entry["sampleRow"] = {k: payload[0].get(k) for k in
                          ("date", "period", "filingDate", "fillingDate",
                           "acceptedDate")
                          if k in payload[0]}
    return entry


def probe_ticker(key: str, ticker: str, limit: int) -> dict:
    entry: dict = {}
    calls = 0
    for kind, path in STATEMENT_PATHS.items():
        params = urllib.parse.urlencode(
            {"symbol": ticker, "period": "quarter", "limit": limit, "apikey": key})
        url = f"{BASE}/{path}?{params}"
        status, body, error = _request(url)
        calls += 1
        time.sleep(PACE_SECONDS)
        if body is None:
            entry[kind] = {"httpStatus": status, "error": error}
            continue
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            # The body was READ and then thrown away here, which is how a
            # bare "HTTP 402" became "FMP dropped statements from the free
            # tier" — an inference from a status code with the vendor's own
            # explanation discarded. FMP says which plan an endpoint needs;
            # that sentence is the finding, so it is kept.
            entry[kind] = {"httpStatus": status,
                           "error": f"non-JSON response (HTTP {status})",
                           "bodyHead": body_head(body)}
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

    # Before spending the sample: does the key work at all, and is the refusal
    # about the plan or about the path? A bare 402 on statements cannot say.
    liveness = check_liveness(key)
    print("=== 키 자체 확인 ===")
    for name, row in liveness.items():
        print(f"  {name:<9} {str(row['httpStatus']):<5} "
              f"{'SERVED' if row['served'] else 'refused'}  {row['bodyHead'][:120]}")
    bases = check_bases(key)
    print("\n=== URL 형태별 손익계산서 ===")
    for name, row in bases.items():
        print(f"  {name:<9} {str(row['httpStatus']):<5} "
              f"{'SERVED' if row['served'] else 'refused'}  {row['bodyHead'][:160]}")
    verdict = diagnose(liveness, bases)
    print(f"\n  판정: {verdict['verdict']}")
    print(f"  {verdict['meaning']}\n")

    # The 402s and the 200 in the previous run came from the same endpoint in
    # the same minute and differed only in `limit`. So the cap is measured
    # before the sample is spent, and the sample then asks for what the key is
    # actually served rather than re-buying the same refusal five times.
    limit = args.limit
    cap = None
    if verdict["verdict"] == "STATEMENTS_AVAILABLE":
        cap = find_limit_cap(key)
        print("=== limit 상한 ===")
        for rung in cap["rungs"]:
            mark = "SERVED" if rung["served"] else "refused"
            tail = (f"{rung['periodsReturned']}개 기간" if rung["served"]
                    else rung["bodyHead"][:160])
            print(f"  limit={rung['limit']:<4} {str(rung['httpStatus']):<5} "
                  f"{mark:<8} {tail}")
        if cap["largestServed"] is None:
            print("  → 어떤 limit 도 응답하지 않았습니다.\n")
        else:
            print(f"  → 서비스되는 최대 limit: {cap['largestServed']}"
                  + (f" (limit={cap['refusedAt']} 에서 거절)"
                     if cap["refusedAt"] else "") + "\n")
            if args.limit > cap["largestServed"]:
                print(f"  요청 limit {args.limit} → {cap['largestServed']} 로 낮춰서 "
                      f"샘플을 받습니다.\n")
                limit = cap["largestServed"]


    samples = [s.strip().upper() for s in args.samples.split(",") if s.strip()]
    report: dict = {"probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "factorInputs": FACTOR_INPUTS, "requestedLimit": args.limit,
                    "effectiveLimit": limit, "limitCap": cap, "samples": {}}

    total_calls = 0
    for ticker in samples:
        print(f"=== {ticker} ===")
        entry = probe_ticker(key, ticker, limit)
        report["samples"][ticker] = entry
        total_calls += entry["calls"]
        for kind in STATEMENT_PATHS:
            info = entry[kind]
            if info.get("error") or info.get("errorBody"):
                print(f"  {kind:<9} 실패 — {info.get('error') or info.get('errorBody')}"
                      f" (HTTP {info.get('httpStatus')})")
                # The body was already captured; printing it is what makes the
                # refusal readable from the run log instead of only from the
                # uploaded JSON, which is where the last one went unread.
                if info.get("bodyHead"):
                    print(f"            {info['bodyHead'][:200]}")
                continue
            print(f"  {kind:<9} {info.get('periodCount')}개 기간 · "
                  f"범위 {info.get('dateRange')} · "
                  f"filed일 {info.get('fillingDateCoverage')}/{info.get('periodCount')}"
                  f" ({info.get('fillingDateField')})")
            missing = [k for k, v in (info.get("fieldsFound") or {}).items() if not v.get("field")]
            if missing:
                print(f"            누락: {', '.join(missing)}")
        print()

    report["totalCalls"] = total_calls

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
    report["keyLiveness"] = liveness
    report["urlShapes"] = bases
    report["diagnosis"] = verdict
    report["limitCap"] = cap
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {args.output}")
    return 0 if ok_incomes else 1


if __name__ == "__main__":
    raise SystemExit(main())
