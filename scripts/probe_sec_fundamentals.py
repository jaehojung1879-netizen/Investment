"""Does SEC EDGAR give us what point-in-time value and quality actually need
for the US half of the universe?

WHY A PROBE AND NOT A PIPELINE. The Korean half of this same problem was
closed by DART, but only after a probe measured DART's real response shapes
first — writing a parser against a guessed shape is how a week disappears.
US value and quality are currently dark for all ~500 US names: `historical_
replay.py` reads every ticker's fundamentals from ONE `FundamentalStore`, and
the only file wired into it today is `ledger/fundamentals/pit-kr.jsonl`. This
measures whether SEC EDGAR's XBRL API can close the US half the same way DART
closed the Korean one, before any collector is written against it.

WHAT DECIDES THE ANSWER, IN ORDER — the same four questions the DART probe
asked, because point-in-time correctness does not get to be assumed twice:

  1. FILING DATE. A 10-Q or 10-K describes a period that ended weeks before it
     was submitted. XBRL company facts carry `filed` on every fact; if that is
     absent or unreliable there is no point-in-time and nothing else matters.
  2. HOW FAR BACK. The replay starts 2013-01. SEC's XBRL frames API is known to
     start around 2009, but that is a claim about the API in general, not about
     what any specific company's own facts contain — measured here per sample.
  3. THE ACCOUNTS THEMSELVES, under whatever US-GAAP tag each filer actually
     used. Companies do not agree on tags the way DART filers mostly agree on
     Korean account labels — `Revenues` vs `RevenueFromContractWithCustomer
     ExcludingAssessedTax` is the least of it — so this checks a candidate list
     per concept and reports which one each sample actually carries.
  4. VOLUME AND SHAPE. `companyfacts` returns a company's ENTIRE filing history
     in one call, unlike DART's one-call-per-year-per-report — if that holds,
     roughly 500 US names is ~500 calls total, not the multi-day DART backfill.
     Duration facts also carry explicit `start`/`end` dates, which would answer
     directly the "is this a quarter or a year-to-date figure" question DART
     answered by measuring value ratios over 84 companies.

Nothing is written to the ledger and no artifact changes. This reports.

Usage:  python scripts/probe_sec_fundamentals.py [--output sec-probe.json]
        [--samples AAPL,JPM,XOM,KO,O]
        SEC_USER_AGENT should be a contact-identifying string (SEC fair-access
        policy); the 13F reader's default is reused if unset.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_SEC = "https://data.sec.gov"
WWW_SEC = "https://www.sec.gov"
DEFAULT_USER_AGENT = (
    "InvestmentResearchDashboard/1.1 "
    "jaehojung1879-netizen@users.noreply.github.com"
)
# SEC's fair-access policy asks for <=10 req/s; the 13F reader already paces at
# this rate against the same host, and disagreeing with it here would be two
# definitions of "polite" for one API.
PACE_SECONDS = 0.16

# What each production factor needs, and the US-GAAP tags (or `dei:` tags for
# share counts, which are cover-page facts rather than financial-statement
# ones) that might carry it. Filers do not agree on tags the way DART filers
# mostly agree on Korean labels, so several candidates are checked per concept
# and this reports which one each sample actually used — never assumed.
CANDIDATE_TAGS: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ],
    "netIncome": ["NetIncomeLoss", "ProfitLoss"],
    "operatingIncome": ["OperatingIncomeLoss"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "liabilities": ["Liabilities"],
    "assets": ["Assets"],
    "operatingCashFlow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForCapitalImprovements",
        "PaymentsToAcquireProductiveAssets",
    ],
}
# Share counts are cover-page facts (`dei:`), not financial-statement ones
# (`us-gaap:`) — a different namespace within the same companyfacts document.
DEI_SHARE_TAGS = ["EntityCommonStockSharesOutstanding"]

FACTOR_INPUTS = {
    "value · earningsYield":  ["netIncome", "sharesOutstanding"],
    "value · bookYield":      ["equity", "sharesOutstanding"],
    "value · fcfYield":       ["operatingCashFlow", "capex", "sharesOutstanding"],
    "quality · roe":          ["netIncome", "equity"],
    "quality · opMargin":     ["operatingIncome", "revenue"],
    "quality · profitMargin": ["netIncome", "revenue"],
    "quality · debtToEquity": ["liabilities", "equity"],
    "quality · earningsGrowth": ["netIncome (prior period)"],
}

# A fallback for the probe's default samples, in case `company_tickers.json`
# (served from www.sec.gov, not the data.sec.gov API host `companyfacts` lives
# on) stays blocked even after retries. This does not scale to the full ~500-
# name universe a real collector would need, but it lets the probe still
# measure the endpoint that actually matters — companyfacts — instead of
# failing before ever calling it. CIKs are public record, from SEC's own
# EDGAR full-text search.
KNOWN_CIKS = {
    "AAPL": "0000320193", "JPM": "0000019617", "XOM": "0000034088",
    "KO": "0000021344", "O": "0000726728",
}


def _request(url: str, timeout: int = 30) -> tuple[bytes | None, str]:
    """Fetch one SEC resource with bounded retries.

    The 13F reader (`pipeline.institutional_13f`) already established that SEC
    answers a live, working request with an occasional 403 and clears it on
    retry — its own `_request` retries {403, 429, 500, 502, 503, 504} three
    times. A probe that gives up on the first 403 would report "SEC blocks
    this" about a request that a retry would have served.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.8",
    })
    last_error = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read(), ""
        except urllib.error.HTTPError as exc:
            # The status code alone does not say WHO is refusing: SEC's own
            # bot policy, a CDN challenge page, and a network-level block all
            # answer 403, and only the body tells them apart. A 403 that
            # survives every retry is worth that extra read.
            body = ""
            try:
                body = exc.read(300).decode("utf-8", errors="replace").strip()
            except Exception:                          # pragma: no cover - network
                pass
            last_error = f"HTTP {exc.code}" + (f" — {body}" if body else "")
            if exc.code not in {403, 429, 500, 502, 503, 504} or attempt == 2:
                return None, last_error
        except Exception as exc:                      # pragma: no cover - network
            return None, f"{type(exc).__name__}: {exc}"
        time.sleep(1.5 * (2 ** attempt))
    return None, last_error


def _fetch_json(url: str, timeout: int = 30) -> tuple[dict | None, str]:
    raw, error = _request(url, timeout)
    if raw is None:
        return None, error
    try:
        return json.loads(raw.decode("utf-8")), ""
    except ValueError:
        return None, f"non-JSON response ({len(raw)} bytes)"


def ticker_to_cik(tickers: list[str]) -> tuple[dict[str, str], dict[str, str], str]:
    """Ticker -> zero-padded 10-digit CIK, and how each was resolved.

    Tries SEC's own published map first — the only source that would scale to
    a real collector's ~500 names. `KNOWN_CIKS` fills in only what the live
    fetch could not, so a `company_tickers.json` outage does not also block
    measuring the endpoint that actually matters (`companyfacts`), while still
    reporting honestly that the map itself did not resolve.
    """
    wanted = {t.upper() for t in tickers}
    out: dict[str, str] = {}
    source: dict[str, str] = {}
    payload, error = _fetch_json(f"{WWW_SEC}/files/company_tickers.json", timeout=60)
    if payload is not None:
        for row in payload.values():
            sym = str(row.get("ticker") or "").upper()
            if sym in wanted:
                out[sym] = f"{int(row['cik_str']):010d}"
                source[sym] = "company_tickers.json"
    for sym in wanted - out.keys():
        if sym in KNOWN_CIKS:
            out[sym] = KNOWN_CIKS[sym]
            source[sym] = "KNOWN_CIKS fallback"
    return out, source, ("" if payload is not None else error)


def parse_companyfacts(payload: dict) -> dict:
    """Everything the probe reports about one company, from its raw payload.

    Split out from the network call so the parsing — which tag a concept
    resolved to, whether filed dates are present, the quarterly duration
    shape — is the part pinned by a test, the same split the DART probe uses
    between `call()` and `receipt_date()`.
    """
    us_gaap = (payload.get("facts") or {}).get("us-gaap") or {}
    dei = (payload.get("facts") or {}).get("dei") or {}
    entry: dict = {"entityName": payload.get("entityName")}

    # --- which tag each concept actually resolves to, and how many facts --- #
    tags_found: dict[str, dict] = {}
    for concept, candidates in CANDIDATE_TAGS.items():
        hit = next((c for c in candidates if c in us_gaap), None)
        if hit is None:
            tags_found[concept] = {"tag": None, "candidatesChecked": candidates}
            continue
        units = (us_gaap[hit].get("units") or {})
        facts = units.get("USD") or next(iter(units.values()), [])
        tags_found[concept] = {"tag": hit, "factCount": len(facts)}
    entry["accounts"] = tags_found
    entry["accountsFound"] = sum(1 for v in tags_found.values() if v.get("tag"))
    entry["accountsWanted"] = len(CANDIDATE_TAGS)

    shares_tag = next((t for t in DEI_SHARE_TAGS if t in dei), None)
    entry["sharesTag"] = shares_tag
    if shares_tag:
        shares_units = (dei[shares_tag].get("units") or {})
        shares_facts = shares_units.get("shares") or next(iter(shares_units.values()), [])
        entry["sharesFactCount"] = len(shares_facts)

    # --- filed dates, form types, and duration shape — on net income, the --- #
    # account every sample should carry, so this is comparable across samples.
    reference = tags_found.get("netIncome", {})
    if reference.get("tag"):
        facts = ((us_gaap[reference["tag"]].get("units") or {}).get("USD") or [])
        entry["factCount"] = len(facts)
        entry["hasFiledDate"] = sum(1 for f in facts if f.get("filed"))
        forms = {}
        for f in facts:
            forms[f.get("form", "?")] = forms.get(f.get("form", "?"), 0) + 1
        entry["forms"] = forms
        years = sorted({f.get("fy") for f in facts if f.get("fy")})
        entry["fiscalYears"] = years[:3] + (["..."] if len(years) > 6 else []) + years[-3:] \
            if len(years) > 6 else years
        entry["earliestFiscalYear"] = min(years) if years else None
        # A 10-Q duration fact states its own start/end — the period length is
        # arithmetic, not a guess about which column DART-style vendors used.
        quarterly = [f for f in facts if f.get("form") == "10-Q" and f.get("start") and f.get("end")]
        if quarterly:
            sample = quarterly[-1]
            from datetime import date
            days = (date.fromisoformat(sample["end"]) - date.fromisoformat(sample["start"])).days
            entry["sampleQuarterlyFact"] = {
                "start": sample["start"], "end": sample["end"], "days": days,
                "filed": sample.get("filed"), "val": sample.get("val"),
            }
    return entry


def probe_company(cik: str) -> dict:
    payload, error = _fetch_json(f"{DATA_SEC}/api/xbrl/companyfacts/CIK{cik}.json",
                                 timeout=60)
    if payload is None:
        return {"error": error}
    return parse_companyfacts(payload)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="sec-probe.json")
    parser.add_argument("--samples", default="AAPL,JPM,XOM,KO,O",
                        help="mega-cap tech, bank, energy, staple, REIT — a "
                             "deliberately varied mix of tagging conventions")
    args = parser.parse_args(argv)

    samples = [s.strip().upper() for s in args.samples.split(",") if s.strip()]
    report: dict = {"probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "factorInputs": FACTOR_INPUTS, "samples": {}}

    print(f"User-Agent: {os.environ.get('SEC_USER_AGENT', DEFAULT_USER_AGENT)}\n")

    # --- 1. ticker -> CIK --------------------------------------------------- #
    cik_map, cik_source, error = ticker_to_cik(samples)
    report["cikMap"] = cik_map
    report["cikSource"] = cik_source
    if error:
        print(f"경고: company_tickers.json 실패 — {error} "
              f"(www.sec.gov, companyfacts가 사는 data.sec.gov와는 다른 호스트)")
    if not cik_map:
        print(f"ERROR: could not resolve any CIK — {error}")
        report["reachable"] = False
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
        return 1
    report["reachable"] = True
    print(f"1. CIK 매핑         {len(cik_map)}/{len(samples)}개 확보")
    for t in samples:
        print(f"   {t:<6} {cik_map.get(t, '없음')}  ({cik_source.get(t, '-')})")

    # --- 2. companyfacts per sample ------------------------------------------ #
    print("\n2. companyfacts — 계정, 접수일, 기간 형태")
    for t in samples:
        cik = cik_map.get(t)
        if not cik:
            report["samples"][t] = {"error": "CIK 없음"}
            continue
        entry = probe_company(cik)
        report["samples"][t] = entry
        time.sleep(PACE_SECONDS)
        if entry.get("error"):
            print(f"   {t:<6} 실패 — {entry['error']}")
            continue
        print(f"   {t:<6} 계정 {entry.get('accountsFound')}/{entry.get('accountsWanted')}"
              f"  주식수태그 {'있음' if entry.get('sharesTag') else '없음'}"
              f"  최초회계연도 {entry.get('earliestFiscalYear')}"
              f"  접수일보유 {entry.get('hasFiledDate')}/{entry.get('factCount')}")
        missing = [k for k, v in (entry.get("accounts") or {}).items() if not v.get("tag")]
        if missing:
            print(f"          누락: {', '.join(missing)}")
        sq = entry.get("sampleQuarterlyFact")
        if sq:
            print(f"          분기 기간 예시 {sq['start']}~{sq['end']} ({sq['days']}일)"
                  f"  filed={sq['filed']}")

    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --- verdict -------------------------------------------------------------- #
    ok = [e for e in report["samples"].values() if e.get("factCount")]
    has_dates = all(e.get("hasFiledDate") == e.get("factCount") for e in ok)
    earliest = min((e["earliestFiscalYear"] for e in ok if e.get("earliestFiscalYear")),
                   default=None)
    total_calls = 1 + len(samples)  # one ticker map + one companyfacts per name
    print("\n=== 판정 ===")
    print(f"  접수일자(filed) 전부 보유 : {'예' if has_dates and ok else '아니오'}")
    print(f"  가장 이른 회계연도        : {earliest}  (리플레이 시작 2013)")
    print(f"  이번 프로브 호출 수        : {total_calls} "
          f"(전체 유니버스라면 명당 1회 = 약 500회 안팎으로 추정)")
    if not has_dates or not ok:
        print("  → filed가 없으면 point-in-time이 성립하지 않습니다. 여기서 멈춥니다.")
    elif earliest and earliest > 2013:
        print(f"  → 2013~{earliest - 1}년 미국 밸류·퀄리티는 비어 있게 됩니다.")
    if error:
        print(f"  → company_tickers.json이 막혀 있었습니다({error}). companyfacts"
              f"(data.sec.gov)가 위에서 정상이었다면, 실제 컬렉터는 전체 500종목의 "
              f"CIK를 다른 방법으로 확보해야 합니다 — 이 프로브가 쓴 하드코딩은 "
              f"5종목까지만 통합니다.")
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
