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
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .foundation import MAX_BYTES, SOURCES, TERMS, admit

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
    receipts, attempts = [], []
    for symbol, urls in SOURCES.items():
        if not urls:
            attempts.append({"symbol": symbol, "status": "SOURCE_PATH_UNVERIFIED"})
        for url in urls:
            try:
                req = Request(url, headers={"User-Agent": "Investment research source validation/1.0",
                                            "Accept": "text/csv,text/plain"})
                with opener.open(req, timeout=20) as response:
                    if response.geturl() != url or response.status != 200:
                        raise ValueError("UNEXPECTED_RESPONSE")
                    mime = response.headers.get_content_type()
                    if mime not in ("text/csv", "text/plain", "application/csv",
                                    "application/octet-stream", "application/vnd.ms-excel"):
                        raise ValueError("UNEXPECTED_CONTENT_TYPE")
                    raw = response.read(MAX_BYTES + 1)
                received = datetime.now(timezone.utc).isoformat()
                sha = hashlib.sha256(raw).hexdigest()
                item = admit(raw, symbol=symbol, url=url, sha256=sha,
                             retrieved_at=received, as_of=received)
                dest = out / (symbol + ".csv")
                with dest.open("xb") as f:
                    f.write(raw)
                receipts.append({"symbol": symbol, "url": url, "sha256": sha,
                                 "retrievedAtUtc": received, "path": str(dest)})
                attempts.append({"symbol": symbol, "url": url, "status": "ADMITTED_CURRENT_HISTORY",
                                 "nonmissing": sum(x is not None for x in item["rows"].values())})
                break
            except HTTPError as exc:
                attempts.append({"symbol": symbol, "url": url, "status": "HTTP_ERROR", "httpStatus": exc.code})
                # Do not route around access controls or rate limits.
                if exc.code in (401, 403, 429):
                    break
            except (URLError, OSError, ValueError, TypeError) as exc:
                attempts.append({"symbol": symbol, "url": url, "status": "SOURCE_BLOCKED",
                                 "errorType": type(exc).__name__})
    (out / "manifest.json").write_text(json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
    result = {"status": "COMPLETE_SOURCE_CENSUS" if len(receipts) == len(TERMS) else "PARTIAL_OR_BLOCKED",
              "admitted": len(receipts), "requested": len(TERMS), "attempts": attempts,
              "productionEffect": "NONE", "investmentEvaluationAuthorized": False}
    (out / "attempts.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = acquire(args.out)
    print(json.dumps(result, indent=2))
    return 0 if result["admitted"] == len(TERMS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
