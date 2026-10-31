"""Recover the fixed68 original DART attachments, without a new key or service.

Uses the public download popup exposed by the preserved original main page.
No authentication bypass, API key, search for alternative issuers/periods,
future price, outcome or model. Missing access is NOT missing source evidence.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse, parse_qs, urljoin

import requests

from . import pit_filing_evidence as E
from . import pit_join as J

HERE = Path(__file__).parent
DEMAND = HERE / "pit_measurement_v1/source-demand.json"


def popup_url(main_raw, receipt):
    text = main_raw.decode("utf-8")
    ids = set(re.findall(r"openPdfDownload\(\s*['\"]" + re.escape(receipt)
                         + r"['\"]\s*,\s*['\"](\d+)['\"]\s*\)", text))
    if len(ids) != 1:
        raise ValueError("ORIGINAL_DOCUMENT_ID_AMBIGUOUS")
    return f"https://dart.fss.or.kr/pdf/download/main.do?rcp_no={receipt}&dcm_no={next(iter(ids))}"


class AttachmentTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.cells, self.text, self.hrefs = [], [], [], []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cells, self.hrefs = [], []
        elif tag == "td":
            self.text = []
        elif tag == "a":
            self.hrefs.append(dict(attrs).get("href", ""))

    def handle_data(self, data):
        self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "td":
            self.cells.append("".join(self.text).strip())
        elif tag == "tr" and self.cells:
            self.rows.append((self.cells[0], list(self.hrefs)))


def select_attachment(body, page_url, receipt):
    page = urlparse(page_url)
    query = parse_qs(page.query)
    if (page.scheme != "https" or page.netloc != "dart.fss.or.kr" or page.path != "/pdf/download/main.do"
            or query.get("rcp_no") != [receipt] or not re.fullmatch(r"\d+", query.get("dcm_no", [""])[0])):
        raise ValueError("DOWNLOAD_PAGE_RECEIPT_OR_DOCUMENT_MISMATCH")
    parser = AttachmentTable()
    parser.feed(body.decode("utf-8"))
    candidates = []
    for name, links in parser.rows:
        if not re.search(r"(?:IFRS|XBRL).*\.zip\b", name, re.I):
            continue
        for link in links:
            url = urljoin(page_url, link)
            p, q = urlparse(url), parse_qs(urlparse(url).query)
            if (p.scheme == "https" and p.netloc == "dart.fss.or.kr" and p.path == "/pdf/download/ifrs.do"
                    and q.get("rcp_no") == [receipt] and q.get("dcm_no") == query.get("dcm_no")
                    and set(q) <= {"rcp_no", "dcm_no", "lang"}):
                candidates.append({"filename": name, "url": url})
    unique = {(c["filename"], c["url"]): c for c in candidates}
    if len(unique) != 1:
        raise ValueError("XBRL_ATTACHMENT_NOT_LISTED_OR_AMBIGUOUS")
    return next(iter(unique.values()))


def validate_public_provenance(metadata, package):
    if E.sha(package["mainRaw"]) != metadata["mainSha256"]:
        raise ValueError("PUBLIC_MAIN_SOURCE_DIGEST_MISMATCH")
    expected = popup_url(package["mainRaw"], metadata["receipt"])
    if package["downloadPageUrl"] != expected or E.sha(package["downloadPageRaw"]) != package["downloadPageSha256"]:
        raise ValueError("PUBLIC_DOWNLOAD_PAGE_SOURCE_MISMATCH")
    link = select_attachment(package["downloadPageRaw"], expected, metadata["receipt"])
    if link["url"] != package["url"] or link["filename"] != package["filename"]:
        raise ValueError("PUBLIC_ATTACHMENT_RECEIPT_OR_DOCUMENT_MISMATCH")


def registry(source):
    demand = json.loads(DEMAND.read_text())
    requested = {r["receipt"]: r for r in demand["requests"]}
    matches = defaultdict(list)
    for batch in range(26):
        prefix = f"{J.D2}/batch-{batch:02d}/"
        m = source.json(prefix + "manifest-originals.json")
        wanted = [r for r in m["records"] if any(x in requested for x in r["target"].get("receiptNos", []))]
        if not wanted:
            continue
        raw = source.blob(J.EVIDENCE_COMMIT, prefix + m["archive"])
        if E.sha(raw) != m["archiveSha256"]:
            raise ValueError("ORIGINAL_ARCHIVE_DIGEST_MISMATCH")
        bodies = json.loads(gzip.decompress(raw))
        for r in wanted:
            t = r["target"]
            response = r["responses"][0]
            if response.get("status") != 200 or len(t["receiptNos"]) != 1:
                raise ValueError("ORIGINAL_MAIN_EVIDENCE_NOT_SERVED")
            body = base64.b64decode(bodies[response["sha256"]], validate=True)
            if E.sha(body) != response["sha256"]:
                raise ValueError("ORIGINAL_MAIN_DIGEST_MISMATCH")
            meta = E.original_main(t, body, response["url"])
            receipt = meta["receipt"]
            if meta["ticker"] not in requested[receipt]["tickers"]:
                raise ValueError("PRIORITY_RECEIPT_ISSUER_MISMATCH")
            matches[receipt].append({**meta, "mainRaw": body, "downloadPageUrl": popup_url(body, receipt),
                                     "neededFor": requested[receipt]["neededFor"]})
    if len(requested) != 68 or any(len(matches[r]) != 1 for r in requested):
        raise ValueError("FIXED_68_RECEIPT_REGISTRY_INCOMPLETE_OR_AMBIGUOUS")
    return [matches[r][0] for r in sorted(requested)]


def environment_access():
    """Read desired host policy only as a negative prerequisite, not readiness."""
    path = Path("/etc/codex/network-policy.json")
    if not path.exists():
        return {"status": "UNOBSERVED_ATTEMPT_REQUIRED"}
    p = json.loads(path.read_text()).get("http_network_policy", {})
    hosts = {r.get("host") for r in p.get("egress_rules", [])}
    if p.get("type") == "restricted" and "dart.fss.or.kr" not in hosts and "*" not in hosts:
        return {"status": "ENVIRONMENT_NETWORK_HOST_NOT_ALLOWED", "requiredHost": "dart.fss.or.kr"}
    return {"status": "HOST_LISTED_ACTUAL_REQUEST_STILL_REQUIRED"}


def fetch_public(url):
    u = urlparse(url)
    if u.scheme != "https" or u.netloc != "dart.fss.or.kr":
        raise ValueError("NON_OFFICIAL_PUBLIC_DESTINATION_REFUSED")
    # Inherited proxy/TLS trust retained. No credentials are needed or printed.
    response = requests.get(url, timeout=(5, 20), allow_redirects=False)
    if response.status_code != 200:
        raise ValueError("PUBLIC_HTTP_STATUS:" + str(response.status_code))
    if len(response.content) > 32 * 1024 * 1024:
        raise ValueError("PUBLIC_RESPONSE_TOO_LARGE")
    return response.content


def collect(targets, destination, *, access, transport=fetch_public, throttle_seconds=1):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    objects = destination / "objects"
    objects.mkdir()
    rows, calls, circuit = [], 0, None
    for t in targets:
        row = {k: v for k, v in t.items() if k != "mainRaw"}
        if access["status"] == "ENVIRONMENT_NETWORK_HOST_NOT_ALLOWED":
            row["status"] = "NOT_ATTEMPTED_ENVIRONMENT_NETWORK_BLOCKED"
        elif circuit:
            row.update(status="NOT_ATTEMPTED_AFTER_TRANSPORT_FAILURE", reason=circuit)
        else:
            try:
                calls += 1
                page = transport(t["downloadPageUrl"])
                attachment = select_attachment(page, t["downloadPageUrl"], t["receipt"])
                if throttle_seconds:
                    time.sleep(throttle_seconds)
                calls += 1
                raw = transport(attachment["url"])
                if not raw.startswith(b"PK"):
                    raise ValueError("PUBLIC_ATTACHMENT_NOT_A_ZIP")
                for name, blob in (("main", t["mainRaw"]), ("page", page), ("package", raw)):
                    h = E.sha(blob)
                    path = objects / (h + (".zip" if name == "package" else ".bin"))
                    if not path.exists():
                        with path.open("xb") as f:
                            f.write(blob)
                    row[name + "Object"] = str(path.relative_to(destination))
                    row[name + "Sha256"] = h
                row.update(attachment, status="ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP", requestedAt=datetime.now(timezone.utc).isoformat())
            except requests.RequestException as exc:
                # Never print exception text that could contain request metadata.
                circuit = type(exc).__name__
                row.update(status="TRANSPORT_ACCESS_FAILURE_NOT_SOURCE_ABSENCE", reason=circuit)
            except ValueError as exc:
                row.update(status="SOURCE_ATTACHMENT_UNRESOLVED", reason=str(exc))
                if str(exc).startswith("PUBLIC_HTTP_STATUS:"):
                    circuit = str(exc)
        rows.append(row)
    report = {"status": "ACQUISITION_MEASURED_NOT_SOURCE_APPROVAL", "fixedReceipts": len(targets),
              "publicRequestsAttempted": calls, "statusCounts": dict(sorted(Counter(r["status"] for r in rows).items())),
              "access": access, "rows": rows, "newHistoricalLabelsRead": 0,
              "demandSha256": E.sha(DEMAND.read_bytes()), "apiKeyRequiredForThisPublicRoute": False}
    (destination / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return report


def load_packages(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    packages = {}
    for r in manifest["rows"]:
        if r["status"] != "ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP":
            continue
        blobs = {}
        for key in ("main", "page", "package"):
            p = directory / r[key + "Object"]
            if p.is_symlink() or not p.resolve().is_relative_to(directory.resolve()):
                raise ValueError("RECOVERED_OBJECT_PATH_ESCAPE")
            blobs[key] = p.read_bytes()
            if E.sha(blobs[key]) != r[key + "Sha256"]:
                raise ValueError("RECOVERED_OBJECT_DIGEST_MISMATCH")
        package = {"raw": blobs["package"], "sha256": r["packageSha256"], "url": r["url"], "filename": r["filename"],
                   "route": "DART_PUBLIC_ATTACHMENT", "mainRaw": blobs["main"], "downloadPageRaw": blobs["page"],
                   "downloadPageSha256": r["pageSha256"], "downloadPageUrl": r["downloadPageUrl"]}
        validate_public_provenance(r, package)
        if r["receipt"] in packages:
            raise ValueError("DUPLICATE_RECOVERED_RECEIPT")
        packages[r["receipt"]] = package
    return packages


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collect", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    if not args.collect:
        print(json.dumps({"status": "PLAN_ONLY", "fixedReceipts": 68, "publicRequestsAttempted": 0}))
        return 0
    if args.output is None or args.output.exists():
        p.error("--output must be a new directory; preserve earlier acquisition attempts")
    report = collect(registry(J.PinnedInputs(J.ROOT)), args.output, access=environment_access())
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}))
    return 3 if len(load_packages(args.output)) != 68 else 0


if __name__ == "__main__":
    raise SystemExit(main())
