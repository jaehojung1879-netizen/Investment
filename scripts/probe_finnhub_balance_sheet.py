"""Bounded owner-run probe: did Finnhub omit the balance sheet, move it, or complete it later? NOT RUN IN THE AUTHORING ENVIRONMENT.

    FINNHUB_API_KEY=... python scripts/probe_finnhub_balance_sheet.py --store <dir of finnhub-*.jsonl.gz> \\
        --output probe.json --raw-out probe-raw.jsonl.gz [--tickers NFLX,DAL,MU,AAPL] [--max-calls 12]

    --max-calls 0   PLAN ONLY: reads the store, prints and records the exact requests it WOULD make, needs no key and calls nothing.

In Actions it runs only through `fundamentals.yml` -> Run workflow -> region=finnhub-bs-probe (job `us-finnhub-bs-probe`: main only,
`contents: read`, the stored US fundamentals checked out read-only, the key present only in the probe step). See
docs/us-finnhub-balance-sheet-probe-ko.md.

WHY ONE REQUEST CAN DECIDE IT. A quarterly request for `from=2026-01-01` returns, in ONE response, the Q1 10-Q (stored in September WITH a
balance sheet) and the Q2 10-Q (stored in October WITHOUT one). So the same response is its own control:

  * Q1 has a balance sheet and Q2 does not                      -> the vendor omits it for the newly served filings only;
  * neither has one                                              -> the vendor stopped sending `bs` for the endpoint as a whole;
  * Q2 now has one                                               -> the vendor completed it after we stored the empty copy
                                                                    (the collector would have discarded that copy: first write wins);
  * Q2 has no `bs` but a balance-sheet-like key or `Assets` sits somewhere else in the filing
                                                                  -> the schema moved, and the parser, not the vendor, is behind it.

It spends at most `--max-calls` requests (hard ceiling 20), reads only the response, writes nothing into the store, and keeps the RAW
body of every response in `--raw-out` — the evidence the collector never retained. The API key is read from the environment, is never
printed or written, and is scrubbed from any error text.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
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

from pipeline import finnhub_fundamentals as FF  # noqa: E402
from pipeline import finnhub_response_health as FH  # noqa: E402

BASE = "https://finnhub.io/api/v1/stock/financials-reported"
DEFAULT_TICKERS = ("NFLX", "DAL", "MU", "AAPL", "MSFT", "JNJ", "MDT", "FLEX")
HARD_CEILING = 20
FROM = "2026-01-01"
ANNUAL_FROM = "2025-01-01"
LIKELY_BALANCE_WORDS = ("balance", "asset", "financialposition", "statementoffinancial")
EXACT_BALANCE_KEYS = ("bs", "balancesheet", "balance_sheet")

SERVED_NOW = "SERVED_NOW_COMPLETION_AVAILABLE"
KEY_MOVED = "BALANCE_SHEET_FOUND_UNDER_ANOTHER_KEY"
ENDPOINT_WIDE = "VENDOR_OMITS_BALANCE_SHEET_ENDPOINT_WIDE"
NEW_ONLY = "VENDOR_OMITS_BALANCE_SHEET_FOR_NEWLY_SERVED_FILINGS_ONLY"
INCONCLUSIVE = "INCONCLUSIVE"


def balance_like_keys(node, path: str = "", depth: int = 0, limit: int = 4) -> list[str]:
    """Paths whose key name looks like a balance sheet, outside the known `report.bs`. Bounded, deterministic."""
    found: list[str] = []
    if depth > limit:
        return found
    if isinstance(node, dict):
        for key in sorted(node):
            here = f"{path}.{key}" if path else str(key)
            name = str(key).lower()
            if here != "report.bs" and (name in EXACT_BALANCE_KEYS or any(w in name for w in LIKELY_BALANCE_WORDS)):
                found.append(here)
            found.extend(balance_like_keys(node[key], here, depth + 1, limit))
    elif isinstance(node, list) and node and isinstance(node[0], dict) and depth <= 1:
        for index, item in enumerate(node[:3]):
            found.extend(balance_like_keys(item, f"{path}[{index}]", depth + 1, limit))
    return found


def assets_outside_bs(filing: dict) -> list[str]:
    """Sections other than `bs` that nevertheless carry an `Assets` entry (a balance sheet filed under the wrong section)."""
    report = filing.get("report") if isinstance(filing.get("report"), dict) else {}
    hits = []
    for section, entries in sorted(report.items()):
        if section == "bs" or not isinstance(entries, list):
            continue
        if any(isinstance(e, dict) and FF.strip_namespace(e.get("concept")) == "Assets" for e in entries):
            hits.append(section)
    return hits


def describe_filing(ticker: str, filing: dict, stored: dict | None) -> dict:
    report = filing.get("report") if isinstance(filing.get("report"), dict) else {}
    status = FH.balance_sheet_status(filing)
    row = {
        "id": FF.filing_id(ticker, str(filing.get("accessNumber") or "")),
        "form": filing.get("form"), "year": filing.get("year"), "quarter": filing.get("quarter"),
        "endDate": filing.get("endDate"), "filedDate": filing.get("filedDate"),
        "filingKeys": sorted(filing), "reportKeys": sorted(report),
        "sectionEntries": {k: len(v) for k, v in sorted(report.items()) if isinstance(v, list)},
        "balanceSheetStatus": status,
        "balanceLikeKeysOutsideBs": balance_like_keys(filing),
        "assetsInOtherSections": assets_outside_bs(filing),
        "stored": None,
    }
    if stored is not None:
        row["stored"] = {"status": FH.stored_balance_sheet_status(stored), "collectedAt": stored.get("collectedAt"),
                         "balanceSheetEntries": len((stored.get("statements") or {}).get("bs") or [])}
    return row


def verdict(filings: list[dict]) -> dict:
    """Pure decision over `describe_filing` rows. Never guesses: no usable pair is INCONCLUSIVE."""
    lost_now_served = [f for f in filings if f["stored"] and f["stored"]["status"] == FH.STORED_BS_LOST
                       and f["balanceSheetStatus"] in (FH.BS_ASSETS_STATED, FH.BS_ASSETS_NOT_STATED)]
    moved = [f for f in filings if f["balanceSheetStatus"] in (FH.BS_EMPTY, FH.BS_KEY_ABSENT)
             and (f["balanceLikeKeysOutsideBs"] or f["assetsInOtherSections"])]
    still_lost = [f for f in filings if f["stored"] and f["stored"]["status"] == FH.STORED_BS_LOST
                  and f["balanceSheetStatus"] in (FH.BS_EMPTY, FH.BS_KEY_ABSENT)]
    had_now_lost = [f for f in filings if f["stored"] and f["stored"]["status"] in (FH.BS_ASSETS_STATED, FH.BS_ASSETS_NOT_STATED)
                    and f["balanceSheetStatus"] in (FH.BS_EMPTY, FH.BS_KEY_ABSENT)]
    had_still = [f for f in filings if f["stored"] and f["stored"]["status"] == FH.BS_ASSETS_STATED
                 and f["balanceSheetStatus"] == FH.BS_ASSETS_STATED]
    if moved:
        result = KEY_MOVED
    elif lost_now_served:
        result = SERVED_NOW
    elif still_lost and had_now_lost:
        result = ENDPOINT_WIDE
    elif still_lost and had_still:
        result = NEW_ONLY
    else:
        result = INCONCLUSIVE
    return {"verdict": result,
            "evidence": {"storedLostNowServed": len(lost_now_served), "storedLostStillLost": len(still_lost),
                         "storedCompleteNowLost": len(had_now_lost), "storedCompleteStillComplete": len(had_still),
                         "lostWithBalanceLikeKeyOrAssetsElsewhere": len(moved)}}


def scrub(text: str, key: str) -> str:
    return text.replace(key, "<key>") if key else text


def fetch_raw(key: str, ticker: str, freq: str, start: str, end: str, timeout: int = 45) -> tuple[str, str]:
    """(status, raw text). The URL carries the token and is never returned or logged."""
    url = BASE + "?" + urllib.parse.urlencode({"symbol": ticker, "freq": freq, "from": start, "to": end, "token": key})
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return f"HTTP_{response.getcode()}", response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(2000).decode("utf-8", "replace")
        except Exception:                                    # pragma: no cover - network
            body = ""
        return f"HTTP_{exc.code}", scrub(body, key)
    except Exception as exc:                                 # pragma: no cover - network
        return f"ERROR_{type(exc).__name__}", scrub(str(exc), key)


def load_stored(store: Path) -> dict[str, dict]:
    stored: dict[str, dict] = {}
    for path in sorted(Path(store).glob("finnhub-*.jsonl.gz")):
        for line in gzip.decompress(path.read_bytes()).decode("utf-8").split("\n"):
            if line.strip():
                row = json.loads(line)
                stored[str(row.get("id"))] = row
    return stored


# What each verdict means for the repair, in the words the recovery plan uses. The probe decides nothing beyond this table.
CATEGORY = {
    SERVED_NOW: "VENDOR_LATER_COMPLETED",
    KEY_MOVED: "VENDOR_MOVED_FIELD",
    NEW_ONLY: "VENDOR_OMITTED",
    ENDPOINT_WIDE: "VENDOR_OMITTED",
    INCONCLUSIVE: "INSUFFICIENT_EVIDENCE",
}
NEXT_REPAIR_PATH = {
    SERVED_NOW: "recovery plan S2_SUPPLEMENT: a reviewed supplement writer re-fetches the affected tickers into a NEW append-only family; "
                "stored shards are never rewritten and the supplement is visible only from the day the vendor served it",
    KEY_MOVED: "recovery plan S2_SUPPLEMENT after a SEPARATE reviewed parser change that reads the key named in `balanceLikeKeysOutsideBs` "
               "(build_record, with tests pinned to the raw bodies this probe retained); then the bounded supplement re-fetch",
    NEW_ONLY: "recovery plan S3_BLOCKED_SOURCE: ask Finnhub whether financials-reported omits the balance sheet for filings first served "
              "after 2026-10-07 and whether it will be back-filled; no value is repaired; the prospective signal stays unmeasurable",
    ENDPOINT_WIDE: "recovery plan S3_BLOCKED_SOURCE: the endpoint no longer states a balance sheet for any filing, including ones it stated "
                   "in September; vendor inquiry and a second balance-sheet source are the only paths; the nightly collector keeps "
                   "storing income and cash-flow statements unchanged",
    INCONCLUSIVE: "INSUFFICIENT_EVIDENCE: repeat once with a different sample (or more calls, up to the ceiling); do not start S2",
}


def _stable_rank(ticker: str, salt: str = "finnhub-bs-probe-v1") -> str:
    return hashlib.sha256((salt + ticker).encode()).hexdigest()


def select_plan(stored: dict[str, dict], quarterly: int = 10, annual: int = 2) -> list[dict]:
    """A deterministic call plan drawn from the STORED records, so each response can pair a healthy filing with an empty one.

    A quarterly ticker needs an empty 10-Q (period end 2026-03 or later) AND a healthy 10-Q of 2026 in the same request window; an annual
    ticker needs an empty 10-K. The order is by a salted hash of the ticker (a fixed pseudo-random spread, not a hand-picked sample) and
    the two annual calls are interleaved so a small budget still contains one.
    """
    by_ticker: dict[str, list[dict]] = {}
    for record in stored.values():
        by_ticker.setdefault(str(record.get("ticker")), []).append(record)
    q, a = [], []
    for ticker, records in by_ticker.items():
        lost = [r for r in records if FH.stored_balance_sheet_status(r) == FH.STORED_BS_LOST and str(r.get("periodEnd")) >= "2026-03-01"]
        healthy = [r for r in records if FH.stored_balance_sheet_status(r) == FH.BS_ASSETS_STATED and str(r.get("periodEnd")) >= FROM
                   and r.get("form") == "10-Q"]
        if any(r.get("form") == "10-Q" for r in lost) and healthy:
            q.append(ticker)
        if any(r.get("form") == "10-K" for r in lost):
            a.append(ticker)
    q = sorted(q, key=_stable_rank)[:quarterly]
    a = sorted(a, key=_stable_rank)[:annual]
    plan = [{"ticker": t, "freq": FF.QUARTERLY, "from": FROM} for t in q]
    for i, t in enumerate(a):
        plan.insert(min(len(plan), 5 * (i + 1) + i), {"ticker": t, "freq": FF.ANNUAL, "from": ANNUAL_FROM})
    return plan


def plan_from_tickers(tickers: list[str]) -> list[dict]:
    return [{"ticker": t, "freq": FF.QUARTERLY, "from": FROM} for t in tickers]


def leak_check(key: str, *texts: str) -> None:
    """Defence in depth: refuse to write any output that contains the key."""
    if key and any(key in t for t in texts):
        raise SystemExit("KEY_FOUND_IN_OUTPUT: refusing to write")


def run(key: str, store, plan: list[dict], max_calls: int, today: str, fetch=None, pace: float = FF.PACE_SECONDS,
        store_commit: str | None = None):
    """Execute at most `min(max_calls, HARD_CEILING)` requests of `plan`. `store` is a directory or an already loaded dict."""
    fetch = fetch or fetch_raw                              # resolved at call time, so a test can replace the network function
    stored = store if isinstance(store, dict) else load_stored(Path(store))
    plan = [{"ticker": p, "freq": FF.QUARTERLY, "from": FROM} if isinstance(p, str) else p for p in plan]
    budget = max(0, min(max_calls, HARD_CEILING))
    raw_rows, per_call, filings = [], [], []
    calls, stopped = 0, None
    for item in plan[:budget]:
        status, text = fetch(key, item["ticker"], item["freq"], item["from"], today)
        calls += 1
        raw_rows.append({"ticker": item["ticker"], "freq": item["freq"], "from": item["from"], "to": today, "status": status,
                         "bodySha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "body": text})
        entry = {"ticker": item["ticker"], "freq": item["freq"], "from": item["from"], "status": status}
        if status != "HTTP_200":
            per_call.append(entry)
            stopped = f"STOPPED_ON_{status}" + ("_RATE_LIMIT" if FF.is_rate_limited(int(status[5:]) if status[5:].isdigit() else None, text) else "")
            break
        try:
            payload = json.loads(text)
        except ValueError:
            per_call.append({**entry, "shape": "NON_JSON"})
            stopped = "STOPPED_ON_NON_JSON"
            break
        rows = payload.get("data") if isinstance(payload, dict) else payload
        per_call.append({**entry, "responseKeys": sorted(payload) if isinstance(payload, dict) else "LIST",
                         "filings": len(rows) if isinstance(rows, list) else None})
        for filing in rows if isinstance(rows, list) else []:
            if isinstance(filing, dict):
                fid = FF.filing_id(item["ticker"], str(filing.get("accessNumber") or ""))
                filings.append(describe_filing(item["ticker"], filing, stored.get(fid)))
        time.sleep(pace)
    decided = verdict(filings)
    report = {"contract": "FINNHUB_BALANCE_SHEET_PROBE_V1", "mode": "LIVE" if budget else "PLAN_ONLY", "storeCommit": store_commit,
              "today": today, "planned": plan, "callBudget": budget, "hardCeiling": HARD_CEILING, "calls": calls,
              "stopped": stopped, "perCall": per_call, "filings": filings, **decided}
    if not budget:
        report.update(verdict="PENDING_NO_CALLS_MADE", category="PENDING_OWNER_DISPATCH", nextRepairPath=None)
    else:
        report.update(category=CATEGORY[decided["verdict"]], nextRepairPath=NEXT_REPAIR_PATH[decided["verdict"]])
        if stopped and decided["verdict"] != INCONCLUSIVE:
            report["note"] = "the run stopped early (" + stopped + "); the verdict is drawn from the responses received before it"
    return report, raw_rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--store-commit", default=None, help="the signal-history commit the store was read from (recorded, not checked)")
    parser.add_argument("--tickers", default="", help="override the stored-record selection with an explicit quarterly sample")
    parser.add_argument("--max-calls", type=int, default=12, help="0 = plan only: no key needed, no request made")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-out", type=Path, required=True)
    parser.add_argument("--today", default=time.strftime("%Y-%m-%d", time.gmtime()))
    args = parser.parse_args(argv)
    if args.max_calls > HARD_CEILING or args.max_calls < 0:
        print(f"ERROR: --max-calls must be between 0 and the hard ceiling {HARD_CEILING}.")
        return 2
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if args.max_calls and not key:
        print("ERROR: FINNHUB_API_KEY not in the environment.")
        return 1
    stored = load_stored(args.store)
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    plan = plan_from_tickers(tickers) if tickers else select_plan(stored)
    if not plan:
        plan = plan_from_tickers(list(DEFAULT_TICKERS))
    report, raw_rows = run(key, stored, plan, args.max_calls, args.today, store_commit=args.store_commit)
    report_text = json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    raw_text = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in raw_rows)
    leak_check(key, report_text, raw_text)
    args.output.write_text(report_text, encoding="utf-8")
    with gzip.open(args.raw_out, "wt", encoding="utf-8") as handle:
        handle.write(raw_text)
    print(json.dumps({"mode": report["mode"], "calls": report["calls"], "verdict": report["verdict"], "category": report["category"],
                      "evidence": report["evidence"], "stopped": report["stopped"], "nextRepairPath": report["nextRepairPath"]},
                     indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
