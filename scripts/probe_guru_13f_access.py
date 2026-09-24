"""Is the Guru 13F historical backfill route SERVED or BLOCKED, right now?

WHAT IS ALREADY KNOWN, GOING IN. AGENTS.md's Vendor refusal invariants
(v2.9) and this repository's own `scripts/probe_sec_bulk_datasets.py`
already measured `www.sec.gov` refusing a bulk DERA dataset ZIP
(`financial-statement-data-sets`) with a byte-identical
"Request Rate Threshold Exceeded" block page from GitHub Actions on
2026-09-04, on the same host the Form 13F bulk dataset also lives on. That is
evidence, not proof, for THIS endpoint — a domain-wide block does not need to
be uniform forever, and the only way to know today's answer is to ask today.
This probe asks two independent routes so a re-measurement, not a rerun of
an old assumption, is what decides the backfill's fallback.

TWO ROUTES, BOTH CLASSIFIED WITH `pipeline.sec_access`'s SERVED/BLOCKED/ERROR
vocabulary — never a second one:

  1. THE BULK DATASET. SEC's own structured Form 13F data sets
     (`sec.gov/data-research/sec-markets-data/form-13f-data-sets`), one ZIP
     per reporting window. `sec_access.classify` assumes a served response
     looks like JSON, which a ZIP never does; `classify_maybe_zip` below
     checks the ZIP magic bytes first (a block page cannot forge them) and
     defers to the shared classifier for everything else, so this is still
     the same three-value vocabulary, not a fourth shape invented here.
  2. THE PER-MANAGER FALLBACK. `data.sec.gov/submissions/CIK{cik}.json` for
     one of the seven already-known managers in
     `data/institutional_managers.json` — the same host and path shape
     `pipeline.institutional_13f` already uses, and the one
     `scripts/backfill_guru_13f.py` falls back to when the bulk route is
     BLOCKED.

Nothing is written to the ledger and no artifact changes. This reports.

Usage:  python scripts/probe_guru_13f_access.py [--output guru-13f-probe.json]
        [--bulk-url URL] [--manager-cik CIK]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.sec_access import SERVED, classify, decode_body, egress_ip  # noqa: E402

DEFAULT_USER_AGENT = (
    "InvestmentResearchDashboard/1.1 jaehojung1879-netizen@users.noreply.github.com"
)

# A recent three-month window in SEC's current naming scheme (effective
# March 2024: `<DDMon><YYYY>-<DDMon><YYYY>_form13f.zip`, windows ending
# Feb/May/Aug/Nov). This WILL go stale — pass --bulk-url for a fresher one.
# Staleness there reads as ERROR/404, a different, distinguishable outcome
# from BLOCKED, so a stale default cannot be misread as a vendor refusal.
DEFAULT_BULK_URL = (
    "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
    "01dec2025-28feb2026_form13f.zip"
)
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
DEFAULT_MANAGER_REGISTRY = ROOT / "data" / "institutional_managers.json"

ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def classify_maybe_zip(status: int | None, body: bytes) -> tuple[str, str | None]:
    """`sec_access.classify` assumes success looks like JSON; a bulk dataset
    ZIP never does. A ZIP's own magic bytes cannot be forged by a block
    page, so that check runs first; everything else defers to the shared
    SERVED/BLOCKED/ERROR classifier untouched."""
    if status == 200 and body[:4] in ZIP_MAGIC:
        return SERVED, None
    return classify(status, body)


def _fetch(url: str, *, user_agent: str, accept: str, timeout: int = 60) -> dict:
    request = urllib.request.Request(url, headers={
        "User-Agent": user_agent, "Accept": accept,
        "Accept-Encoding": "gzip, deflate", "Accept-Language": "en-US,en;q=0.8",
    })
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            body = decode_body(raw, response.headers.get("Content-Encoding"))
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
        return {"status": None, "outcome": "ERROR", "error": f"{type(exc).__name__}: {exc}",
                "elapsedSeconds": round(time.monotonic() - started, 3)}
    outcome, marker = classify_maybe_zip(status, body)
    return {
        "status": status, "outcome": outcome, "blockMarker": marker, "bytes": len(body),
        "bodyHead": (body[:160].decode("utf-8", "replace").replace("\n", " ").strip()
                    if outcome != SERVED or body[:4] not in ZIP_MAGIC else "(ZIP)"),
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }


def probe_bulk_dataset(url: str, user_agent: str) -> dict:
    return _fetch(url, user_agent=user_agent, accept="application/zip, */*")


def probe_per_manager(cik: str, user_agent: str) -> dict:
    url = SUBMISSIONS_URL_TEMPLATE.format(cik=str(cik).zfill(10))
    return {"url": url, **_fetch(url, user_agent=user_agent, accept="application/json, */*")}


def _pick_manager_cik(registry_path: Path, override: str | None) -> str:
    if override:
        return override
    managers = json.loads(registry_path.read_text(encoding="utf-8"))
    return managers[0]["cik"]


def judge(bulk: dict, submissions: dict) -> dict:
    bulk_ok = bulk.get("outcome") == SERVED
    submissions_ok = submissions.get("outcome") == SERVED
    if bulk_ok:
        route = "BULK_DATASET"
    elif submissions_ok:
        route = "PER_MANAGER_SUBMISSIONS"
    else:
        route = "NONE"
    overall = SERVED if route != "NONE" else (
        "BLOCKED" if bulk.get("outcome") == "BLOCKED" or submissions.get("outcome") == "BLOCKED"
        else "ERROR")
    return {
        "verdict": overall, "recommendedRoute": route,
        "bulkDatasetOutcome": bulk.get("outcome"),
        "perManagerSubmissionsOutcome": submissions.get("outcome"),
        "meaning": {
            "BULK_DATASET": "The SEC bulk Form 13F dataset ZIP is servable; the backfill can use it directly.",
            "PER_MANAGER_SUBMISSIONS": "The bulk dataset route is not servable, but the per-manager EDGAR submissions API is — the backfill falls back to it, quarter by quarter, for the seven known managers.",
            "NONE": "Neither route is servable from here right now. The backfill should not run; re-probe later or from a different network.",
        }[route],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="guru-13f-probe.json")
    parser.add_argument("--bulk-url", default=DEFAULT_BULK_URL)
    parser.add_argument("--manager-cik", default=None,
                        help="defaults to the first manager in data/institutional_managers.json")
    parser.add_argument("--managers-registry", default=str(DEFAULT_MANAGER_REGISTRY))
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    args = parser.parse_args(argv)

    ip = egress_ip()
    print(f"egress IP: {ip}")

    print(f"=== bulk dataset: {args.bulk_url} ===")
    bulk = probe_bulk_dataset(args.bulk_url, args.user_agent)
    print(f"  {bulk.get('status')} {bulk.get('outcome')} {bulk.get('bytes', 0):,}B "
         f"{bulk.get('blockMarker') or bulk.get('error') or ''}")

    manager_cik = _pick_manager_cik(Path(args.managers_registry), args.manager_cik)
    print(f"=== per-manager submissions: CIK {manager_cik} ===")
    submissions = probe_per_manager(manager_cik, args.user_agent)
    print(f"  {submissions.get('status')} {submissions.get('outcome')} "
         f"{submissions.get('bytes', 0):,}B "
         f"{submissions.get('blockMarker') or submissions.get('error') or ''}")

    verdict = judge(bulk, submissions)
    report = {
        "probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "egressIp": ip, "bulkUrlProbed": args.bulk_url, "managerCikProbed": manager_cik,
        "bulkDataset": bulk, "perManagerSubmissions": submissions,
        **verdict,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

    print("\n=== verdict ===")
    print(f"  {verdict['verdict']}  route={verdict['recommendedRoute']}")
    print(f"  {verdict['meaning']}")
    print(f"\nwrote {args.output}")
    return 0 if verdict["verdict"] == SERVED else 1


if __name__ == "__main__":
    raise SystemExit(main())
