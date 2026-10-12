"""Bounded owner-run probe: did Finnhub omit the balance sheet, move it, or complete it later? NOT RUN IN THE AUTHORING ENVIRONMENT.

    FINNHUB_API_KEY=... python scripts/probe_finnhub_balance_sheet.py --store <dir of finnhub-*.jsonl.gz> \\
        --output probe.json --raw-out probe-raw.jsonl.gz [--tickers NFLX,DAL,MU,AAPL] [--max-calls 12]

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


def run(key: str, store: Path, tickers: list[str], max_calls: int, today: str, fetch=fetch_raw, pace: float = FF.PACE_SECONDS):
    stored = load_stored(store)
    raw_rows, per_call, filings = [], [], []
    calls = 0
    for ticker in tickers:
        for freq in (FF.QUARTERLY,):
            if calls >= min(max_calls, HARD_CEILING):
                break
            status, text = fetch(key, ticker, freq, FROM, today)
            calls += 1
            raw_rows.append({"ticker": ticker, "freq": freq, "from": FROM, "to": today, "status": status,
                             "bodySha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "body": text})
            try:
                payload = json.loads(text)
            except ValueError:
                per_call.append({"ticker": ticker, "freq": freq, "status": status, "shape": "NON_JSON"})
                continue
            rows = payload.get("data") if isinstance(payload, dict) else payload
            per_call.append({"ticker": ticker, "freq": freq, "status": status,
                             "responseKeys": sorted(payload) if isinstance(payload, dict) else "LIST",
                             "filings": len(rows) if isinstance(rows, list) else None})
            for filing in rows if isinstance(rows, list) else []:
                if isinstance(filing, dict):
                    fid = FF.filing_id(ticker, str(filing.get("accessNumber") or ""))
                    filings.append(describe_filing(ticker, filing, stored.get(fid)))
            time.sleep(pace)
    return {"contract": "FINNHUB_BALANCE_SHEET_PROBE_V1", "calls": calls, "perCall": per_call, "filings": filings,
            **verdict(filings)}, raw_rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--max-calls", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-out", type=Path, required=True)
    parser.add_argument("--today", default=time.strftime("%Y-%m-%d", time.gmtime()))
    args = parser.parse_args(argv)
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        print("ERROR: FINNHUB_API_KEY not in the environment.")
        return 1
    if args.max_calls > HARD_CEILING:
        print(f"ERROR: --max-calls above the hard ceiling {HARD_CEILING}.")
        return 2
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    report, raw_rows = run(key, args.store, tickers, args.max_calls, args.today)
    args.output.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    with gzip.open(args.raw_out, "wt", encoding="utf-8") as handle:
        for row in raw_rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"calls": report["calls"], "verdict": report["verdict"], "evidence": report["evidence"]}, indent=1))
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
