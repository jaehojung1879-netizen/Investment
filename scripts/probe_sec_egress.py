"""Is the whole Actions pool refused, or is it an IP lottery we keep losing?

WHAT IS ALREADY KNOWN, AND WHAT IT LEAVES OPEN. SEC served this repository on
2026-08-15: `data/institutional_13f_cache.json` carries
`sourceMode: LIVE_SEC` and `fetchedAt: 2026-08-15T23:00:24Z`, fetched from
`data.sec.gov/submissions/CIK*.json` — the same host that now answers every
request with a block page. So SEC is not refusing this project by standing
policy. Something changed between then and now.

The header-isolation run then showed the refusal does not move when the
request moves: four header sets, two hosts, eight identical block pages down
to the byte. That ruled out the request shape — and it held the runner fixed
while doing so, which means it also held the EGRESS IP fixed. One IP, refused
eight times, is one observation repeated eight times.

That is the axis this varies. GitHub Actions runners come from a shared,
rotating address pool that thousands of other projects also point at SEC; SEC
throttles and blocks by address. If some runners' addresses are clean and
others are burned, "SEC blocks GitHub Actions" is the wrong description and a
backfill that retries across runners is viable. If every address is refused,
the pool reading is right and the US route needs a different vendor.

HOW. The workflow fans this out across parallel jobs — each gets its own
runner and, usually, its own address. Every job records the address it went
out from and what SEC answered, then `--summarize` reads them together.

THE CHECK THAT KEEPS THIS HONEST. If the runners happen to share one address,
the run varied nothing and must not be read as if it had. The summary reports
the number of DISTINCT addresses first and refuses a verdict below two — the
same discipline the header probe used in keeping its baseline: an experiment
that did not vary its variable proves nothing about it.

Usage:  python scripts/probe_sec_egress.py --output shard.json
        python scripts/probe_sec_egress.py --summarize dir/ --output summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.sec_access import SERVED, classify, decode_body  # noqa: E402

# Where the runner asks what address it is. Not SEC, deliberately: asking SEC
# would spend the very request being measured.
IP_SERVICES = ("https://checkip.amazonaws.com", "https://api.ipify.org")

# One per host, because the two answer with different block pages and a fix
# that reaches one may not reach the other. AAPL's CIK is public record.
TARGETS = [
    ("data.sec.gov", "https://data.sec.gov/submissions/CIK0000320193.json"),
    ("www.sec.gov", "https://www.sec.gov/files/company_tickers.json"),
]

# The headers the 13F reader used on 2026-08-15, when SEC served it. The point
# here is the address, so the request is held at the one known to have worked.
def headers(contact: str) -> dict:
    return {
        "User-Agent": f"InvestmentResearchDashboard/1.1 {contact}",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.8",
    }


DEFAULT_CONTACT = "jaehojung1879-netizen@users.noreply.github.com"


def egress_ip(timeout: int = 15) -> str | None:
    for url in IP_SERVICES:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                text = response.read(200).decode("utf-8", "replace").strip()
        except Exception:
            continue
        if text.startswith("{"):
            try:
                return str(json.loads(text).get("ip") or "").strip() or None
            except ValueError:
                continue
        if text:
            return text
    return None


def attempt(url: str, contact: str, timeout: int = 30) -> dict:
    request = urllib.request.Request(url, headers=headers(contact))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = decode_body(response.read(), response.headers.get("Content-Encoding"))
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = b""
        try:
            raw = exc.read()
        except Exception:  # pragma: no cover - network dependent
            pass
        body = decode_body(raw, exc.headers.get("Content-Encoding") if exc.headers else None)
        status = exc.code
    except Exception as exc:  # pragma: no cover - network dependent
        return {"status": None, "outcome": "ERROR",
                "error": f"{type(exc).__name__}: {exc}"}
    outcome, marker = classify(status, body)
    return {"status": status, "outcome": outcome, "blockMarker": marker,
            "bytes": len(body),
            "bodyHead": body[:160].decode("utf-8", "replace").replace("\n", " ").strip()}


def summarize(shards: list[dict]) -> dict:
    """Read the shards together. The address count comes first.

    A verdict is only available once at least two DISTINCT addresses were
    actually used. Below that the fan-out did not vary the thing it exists to
    vary, and saying "every address is refused" off one address would be the
    same error as concluding from one runner in the first place.
    """
    addresses = sorted({s["egressIp"] for s in shards if s.get("egressIp")})
    served, refused = [], []
    for shard in shards:
        for host, row in (shard.get("attempts") or {}).items():
            key = f"{shard.get('egressIp') or 'unknown-ip'}/{host}"
            (served if row.get("outcome") == SERVED else refused).append(key)

    if len(addresses) < 2:
        return {"verdict": "DID_NOT_VARY_THE_ADDRESS",
                "meaning": (f"{len(addresses)} distinct egress address(es) across "
                            f"{len(shards)} shards — the fan-out landed on the same "
                            "address, so this run says nothing about whether other "
                            "addresses are served"),
                "distinctAddresses": len(addresses), "addresses": addresses,
                "served": served, "refused": refused}
    if served and refused:
        return {"verdict": "SERVED_ON_SOME_ADDRESSES",
                "meaning": ("SEC served some egress addresses and refused others in "
                            "the same minute, so this is an address lottery rather "
                            "than a policy against the pool — a backfill that "
                            "retries across runners is viable"),
                "distinctAddresses": len(addresses), "addresses": addresses,
                "served": served, "refused": refused}
    if served:
        return {"verdict": "SERVED_ON_EVERY_ADDRESS",
                "meaning": ("every address was served — whatever refused the earlier "
                            "runs was not permanent, and the block should be "
                            "re-measured before anything is built on it"),
                "distinctAddresses": len(addresses), "addresses": addresses,
                "served": served, "refused": refused}
    return {"verdict": "REFUSED_ON_EVERY_ADDRESS",
            "meaning": (f"{len(addresses)} distinct addresses, all refused — the "
                        "pool reading holds and the US route needs a vendor that "
                        "is not SEC"),
            "distinctAddresses": len(addresses), "addresses": addresses,
            "served": served, "refused": refused}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="sec-egress-shard.json")
    parser.add_argument("--summarize", default=None,
                        help="directory of shard JSON files to read together")
    parser.add_argument("--shard", default=os.environ.get("SHARD_ID", "0"))
    parser.add_argument("--user-agent", default=None)
    args = parser.parse_args(argv)

    if args.summarize:
        shards = []
        for path in sorted(Path(args.summarize).rglob("*.json")):
            try:
                shards.append(json.loads(path.read_text(encoding="utf-8")))
            except ValueError:
                print(f"  skipped unreadable shard {path}")
        report = {"probe": "sec-egress", "shards": shards,
                  "verdict": summarize(shards)}
        Path(args.output).write_text(
            json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        for shard in shards:
            for host, row in (shard.get("attempts") or {}).items():
                print(f"  shard {shard.get('shard'):<3} "
                      f"{str(shard.get('egressIp')):<16} {host:<14} "
                      f"{str(row.get('status')):<5} {row.get('outcome')}")
        final = report["verdict"]
        print()
        print(f"verdict: {final['verdict']}")
        print(f"  {final['meaning']}")
        print(f"  distinct addresses: {final['distinctAddresses']} {final['addresses']}")
        print(f"wrote {args.output}")
        return 0

    contact = (args.user_agent or os.environ.get("SEC_USER_AGENT")
               or DEFAULT_CONTACT)
    ip = egress_ip()
    print(f"shard {args.shard} egress {ip}")
    attempts = {}
    for host, url in TARGETS:
        row = attempt(url, contact)
        attempts[host] = row
        print(f"  {host:<14} {str(row.get('status')):<5} {row['outcome']:<8} "
              f"{row.get('bytes', 0):>8,}B  {row.get('blockMarker') or row.get('error') or ''}")
    Path(args.output).write_text(json.dumps(
        {"shard": args.shard, "egressIp": ip, "attempts": attempts},
        indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
