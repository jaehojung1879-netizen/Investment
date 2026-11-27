"""One bounded retrieval per candidate URL; no retry, proxy, or repository data writes.

Usage: python -m research.market_implied_future_s5.acquire --out /tmp/s5-originals
The output directory must be new and outside the repository. Public access
does not establish a redistribution right. Keep original bytes local.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .foundation import CBOE, FRED, MAX_BYTES, SOURCES, TERMS, admit
from .futures import FUTURES_URL, MONTHLY_CONTRACTS, parse_contract

ROOT = Path(__file__).resolve().parents[2]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def acquire(out, *, opener=None):
    out = Path(out).resolve()
    if out.is_relative_to(ROOT):
        raise ValueError("RAW_OUTPUT_OUTSIDE_REPOSITORY_REQUIRED")
    out.mkdir(parents=True, exist_ok=False)
    opener = opener or build_opener(NoRedirect())
    receipts, attempts, blocked_hosts = [], [], set()
    requests = [(symbol, url, "index") for symbol, urls in SOURCES.items() for url in urls]
    requests.extend((expiry, FUTURES_URL + f"VX_{expiry}.csv", "futures") for expiry in MONTHLY_CONTRACTS)
    for symbol, url, kind in requests:
        host = urlsplit(url).hostname
        row = {"symbol": symbol, "url": url, "kind": kind}
        if host in blocked_hosts:
            attempts.append({**row, "status": "NOT_REQUESTED_AFTER_HOST_RATE_LIMIT"})
            continue
        try:
            req = Request(url, headers={"User-Agent": "Investment research source validation/1.1",
                                        "Accept": "text/csv,application/csv,text/plain"})
            with opener.open(req, timeout=20) as response:
                if response.geturl() != url or response.status != 200:
                    raise ValueError("UNEXPECTED_RESPONSE")
                mime = response.headers.get_content_type()
                if mime not in ("text/csv", "text/plain", "application/csv",
                                "application/octet-stream", "application/vnd.ms-excel"):
                    raise ValueError("UNEXPECTED_CONTENT_TYPE")
                headers = {
                    "contentType": mime, "httpDate": response.headers.get("Date"),
                    "lastModified": response.headers.get("Last-Modified"), "etag": response.headers.get("ETag"),
                }
                raw = response.read(MAX_BYTES + 1)
            received = datetime.now(timezone.utc).isoformat()
            sha = hashlib.sha256(raw).hexdigest()
            if kind == "index":
                admit(raw, symbol=symbol, url=url, sha256=sha, retrieved_at=received, as_of=received)
                dest = out / (("FRED-" if url.startswith(FRED) else "CBOE-") + symbol + ".csv")
            else:
                parse_contract(raw, symbol, received)
                dest = out / f"CFE-VX-{symbol}.csv"
            with dest.open("xb") as f:
                f.write(raw)
            receipt = {**row, "sha256": sha, "retrievedAtUtc": received, "bytes": len(raw),
                       "path": str(dest), "responseHeaders": headers}
            receipts.append(receipt)
            attempts.append({**row, "status": "ADMITTED_CURRENT_HISTORY"})
        except HTTPError as exc:
            attempts.append({**row, "status": "HTTP_ERROR", "httpStatus": exc.code})
            if exc.code == 429 or (exc.headers and exc.headers.get("cf-mitigated") == "challenge"):
                blocked_hosts.add(host)
        except (URLError, OSError, ValueError, TypeError) as exc:
            attempts.append({**row, "status": "SOURCE_BLOCKED", "errorType": type(exc).__name__})
    (out / "manifest.json").write_text(json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
    terms = {row["symbol"] for row in receipts if row["kind"] == "index" and row["symbol"] in TERMS}
    result = {"status": "ALL_PLANNED_DOWNLOADS_ADMITTED" if len(receipts) == len(requests) else "PARTIAL_OR_BLOCKED",
              "admitted": len(receipts), "requested": len(requests),
              "termNodesAdmitted": len(terms), "cboeIndexReceipts": sum(row["url"].startswith(CBOE) for row in receipts),
              "attempts": attempts,
              "productionEffect": "NONE", "investmentEvaluationAuthorized": False}
    (out / "attempts.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = acquire(args.out)
    print(json.dumps(result, indent=2))
    return 0 if result["admitted"] == result["requested"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
