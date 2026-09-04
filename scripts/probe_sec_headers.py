"""Was SEC refusing our IP, or refusing our HEADERS? One variable at a time.

WHAT WAS CONCLUDED BEFORE THIS, AND WHY IT WAS PREMATURE. Two probes against
sec.gov — the XBRL companyfacts API on data.sec.gov and the bulk Financial
Statement Data Sets on www.sec.gov — both came back with SEC block pages
("Your Request Originates from an Undeclared Automated Tool", "Request Rate
Threshold Exceeded"). That was written up as a site-wide policy against the
GitHub Actions IP pool, and the US half of the PIT fundamentals work was
parked on it.

That conclusion skipped a check. SEC's access policy asks for TWO things, not
one: a declaring `User-Agent` AND `Accept-Encoding: gzip, deflate`. Neither
probe sent the second, and neither does `pipeline.institutional_13f`, whose
same-day fallback to cache was cited as corroboration — so the corroborating
observation shares the suspect header set rather than being independent of it.
The User-Agent shape is a second candidate: SEC documents a plain
"Company Name contact@domain" and we send "AppName/1.1 contact@domain", where
the slash-version token is the classic scripted-client marker.

"Undeclared Automated Tool" is exactly what SEC serves when its check does not
see a compliant header set. It is ALSO what an IP-reputation refusal looks
like from the outside. The two were never separated, and this separates them.

HOW. One endpoint per host, several header sets, everything else held fixed —
same pacing, same retries, same process, same runner, same minute. If a
variant carrying Accept-Encoding gets through where the current one does not,
the block was ours to fix and the US fundamentals route was closed on a
mistake. If every variant is refused identically, the IP conclusion stands and
is now actually established rather than assumed.

WHAT IT DOES NOT DO. It does not fetch fundamentals, and a pass here is not a
backfill: it says which door opens. Nothing is written to the ledger.

`--user-agent` (or SEC_USER_AGENT) sets the contact string used by the
variants that need one. The default keeps the address already in the repo;
this probe never invents a contact of its own.

Usage:  python scripts/probe_sec_headers.py [--output sec-headers-probe.json]
        [--user-agent "Name contact@example.com"]
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

# One definition of "was this served", shared with the egress probe. Two
# copies of that judgement is how two probes end up disagreeing about the
# same response.
from pipeline.sec_access import (  # noqa: E402
    BLOCK_MARKERS, classify, decode_body)

# Same address the repo already uses. A probe does not invent a contact.
DEFAULT_CONTACT = "jaehojung1879-netizen@users.noreply.github.com"

# Both hosts, because both were refused and they run different front doors.
# AAPL's CIK is public record and zero-padded to 10 digits, which the earlier
# probe already got right — the identifier is not what is being tested here.
TARGETS = [
    ("data.sec.gov companyfacts",
     "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"),
    ("www.sec.gov company_tickers",
     "https://www.sec.gov/files/company_tickers.json"),
]

def header_variants(contact: str) -> list[tuple[str, dict, str]]:
    """(name, headers, what this variant is testing).

    Ordered so the first is EXACTLY what the failing probes sent. Without that
    baseline in the same run, a later variant succeeding would not be
    attributable to the header change rather than to the day.
    """
    app_ua = f"InvestmentResearchDashboard/1.1 {contact}"
    doc_ua = f"Investment Research Dashboard {contact}"
    return [
        ("baseline_as_shipped", {
            "User-Agent": app_ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.8",
        }, "exactly what the refused probes sent"),
        ("plus_accept_encoding", {
            "User-Agent": app_ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }, "the one header SEC's policy asks for that we never sent"),
        ("documented_ua_shape", {
            "User-Agent": doc_ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
        }, "SEC's documented 'Company Name contact' shape, no slash-version"),
        ("policy_minimum", {
            "User-Agent": doc_ua,
            "Accept-Encoding": "gzip, deflate",
        }, "only what the policy names, nothing else"),
    ]


def attempt(url: str, headers: dict, timeout: int = 30) -> dict:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            body = decode_body(raw, response.headers.get("Content-Encoding"))
            status = response.status
            content_encoding = response.headers.get("Content-Encoding")
    except urllib.error.HTTPError as exc:
        raw = b""
        try:
            raw = exc.read()
        except Exception:  # pragma: no cover - network dependent
            pass
        body = decode_body(raw, exc.headers.get("Content-Encoding") if exc.headers else None)
        status = exc.code
        content_encoding = exc.headers.get("Content-Encoding") if exc.headers else None
    except Exception as exc:  # pragma: no cover - network dependent
        return {"status": None, "outcome": "ERROR",
                "error": f"{type(exc).__name__}: {exc}"}
    outcome, marker = classify(status, body)
    return {
        "status": status,
        "outcome": outcome,
        "blockMarker": marker,
        "contentEncoding": content_encoding,
        "bytes": len(body),
        "bodyHead": body[:220].decode("utf-8", "replace").replace("\n", " ").strip(),
    }


def verdict(results: dict) -> dict:
    """Did any variant get through where the shipped one did not?

    This is the whole point. A variant succeeding while the baseline is
    refused, in the same run on the same runner, attributes the refusal to the
    headers. Everything refused identically attributes it to the address.
    """
    served, refused = [], []
    baseline_served = False
    for target, variants in results.items():
        for name, row in variants.items():
            key = f"{target}/{name}"
            if row.get("outcome") == "SERVED":
                served.append(key)
                if name == "baseline_as_shipped":
                    baseline_served = True
            else:
                refused.append(key)
    if not served:
        return {"verdict": "REFUSED_ON_EVERY_HEADER_SET",
                "meaning": ("no header set was served, so the refusal is not "
                            "about the headers; the earlier IP conclusion now "
                            "has evidence behind it rather than an assumption"),
                "served": [], "refused": refused}
    if baseline_served:
        return {"verdict": "BASELINE_SERVED_TOO",
                "meaning": ("the shipped headers worked this time, so the "
                            "earlier refusal was not permanent and nothing here "
                            "isolates a cause — re-run before concluding"),
                "served": served, "refused": refused}
    return {"verdict": "HEADERS_WERE_THE_BLOCKER",
            "meaning": ("a variant was served while the shipped headers were "
                        "refused in the same run, so the US fundamentals route "
                        "was closed on our own request shape"),
            "served": served, "refused": refused}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="sec-headers-probe.json")
    parser.add_argument("--user-agent", default=None,
                        help="contact string; default is the repo's existing address")
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="pause between calls; SEC asks for <=10 req/s")
    args = parser.parse_args(argv)

    contact = (args.user_agent or os.environ.get("SEC_USER_AGENT")
               or DEFAULT_CONTACT)
    variants = header_variants(contact)
    print(f"SEC header isolation — {len(variants)} header sets x {len(TARGETS)} hosts")
    print(f"contact: {contact}\n")

    results: dict[str, dict] = {}
    for label, url in TARGETS:
        results[label] = {}
        print(f"{label}")
        for name, headers, testing in variants:
            time.sleep(args.sleep)
            row = attempt(url, headers)
            row["testing"] = testing
            row["headersSent"] = sorted(headers)
            results[label][name] = row
            detail = row.get("blockMarker") or row.get("error") or ""
            print(f"  {name:<22} {str(row.get('status')):<5} "
                  f"{row['outcome']:<8} {row.get('bytes', 0):>8,}B  {detail}")
            if row.get("bodyHead") and row["outcome"] != "SERVED":
                print(f"      {row['bodyHead'][:150]}")
        print()

    report = {
        "probe": "sec-headers",
        "contact": contact,
        "targets": dict(TARGETS),
        "results": results,
        "verdict": verdict(results),
    }
    Path(args.output).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    final = report["verdict"]
    print(f"verdict: {final['verdict']}")
    print(f"  {final['meaning']}")
    if final["served"]:
        print(f"  served: {final['served']}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
