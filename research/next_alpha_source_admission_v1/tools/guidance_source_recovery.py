"""Recover public SEC exhibits for a pinned roster or the existing gold registry.

The archive segment is a new source object. Its bytes are never stored under a
different legacy exhibit hash. Use a separate output directory for a blind roster.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

SEC = "https://www.sec.gov/Archives/edgar/data"
USER_AGENT = (
    "Investment source research (https://github.com/jaehojung1879-netizen/Investment; "
    "project contact: https://github.com/jaehojung1879-netizen/Investment/issues)"
)
MAX_BYTES = 20 * 1024 * 1024
DOCUMENT = re.compile(rb"^<DOCUMENT>\r?\n.*?^</DOCUMENT>(?:\r?\n|$)", re.M | re.S)
PRESS = re.compile(r"earnings|financial results|press[ _-]*release|news[ _-]*release", re.I)
OTHER = re.compile(r"presentation|earnings slide|transcript|conference call", re.I)
ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
EX99 = re.compile(r"EX-99(?:\.[0-9]+)?\Z", re.I)
ROOT = Path(__file__).resolve().parents[1]


class SameSECArchive(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.netloc != "www.sec.gov" or not parsed.path.startswith("/Archives/"):
            raise HTTPError(req.full_url, code, "Off-archive redirect", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPEN = build_opener(SameSECArchive()).open


def field(section: bytes, tag: bytes) -> str:
    match = re.search(rb"^<" + tag + rb">([^\r\n]*)", section, re.M)
    return match[1].decode("ascii", "replace").strip() if match else ""


def sections(data: bytes):
    for match in DOCUMENT.finditer(data):
        section = match[0]
        filename = field(section, b"FILENAME")
        kind = field(section, b"TYPE")
        description = field(section, b"DESCRIPTION")
        if EX99.fullmatch(kind) and filename.lower().endswith((".htm", ".html", ".txt")):
            yield {"filename": filename, "type": kind, "description": description}, section


def select(candidates, known_filename):
    if known_filename:
        exact = [item for item in candidates if item[0]["filename"] == known_filename]
        if len(exact) == 1:
            return exact[0], "REGISTERED_EXHIBIT_FILENAME"
        return None, "REGISTERED_EXHIBIT_ABSENT_OR_DUPLICATED"
    likely = [(meta, item) for meta, item in candidates
              if PRESS.search(meta["filename"] + " " + meta["description"])
              and not OTHER.search(meta["filename"] + " " + meta["description"])]
    if len(likely) == 1:
        return likely[0], "UNIQUE_PRESS_RELEASE_DESCRIPTOR"
    if not likely and len(candidates) == 1 and not OTHER.search(candidates[0][0]["description"]):
        return candidates[0], "SOLE_EX99_REQUIRES_CONTENT_REVIEW"
    return None, "AMBIGUOUS_EX99" if candidates else "NO_EX99_SECTION"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def url_for(row):
    cik = int(row["cik"])
    accession = row["accession"]
    if not ACCESSION.fullmatch(accession) or not 1 <= cik <= 9_999_999_999:
        raise ValueError("INVALID_ACCESSION_OR_CIK")
    return f"{SEC}/{cik}/{accession.replace('-', '')}/{accession}.txt"


def save_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    local = path.with_suffix(".tmp")
    local.write_bytes(data)
    local.replace(path)


def recover(row, output, *, open_url=OPEN):
    url = url_for(row)
    provenance = {"split": row.get("split"), "issuer": row.get("ticker"), "cik": int(row["cik"]),
                  "accession": row["accession"], "registeredHttpSha256": row.get("sha256"),
                  "historyVerified": False, "url": url,
                  "retrievedAtUtc": datetime.now(timezone.utc).isoformat()}
    if row.get("exhibit"):
        provenance["registeredFilename"] = row["exhibit"]
    if row.get("bytes") is not None:
        provenance["registeredHttpBytes"] = row["bytes"]
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    try:
        with open_url(req, timeout=25) as reply:
            parsed = urlparse(reply.geturl())
            if reply.status != 200 or parsed.scheme != "https" or parsed.netloc != "www.sec.gov":
                return {**provenance, "status": "UNEXPECTED_RESPONSE", "httpStatus": reply.status}
            data = reply.read(MAX_BYTES + 1)
    except HTTPError as error:
        return {**provenance, "status": "HTTP_ERROR", "httpStatus": error.code}
    except (URLError, TimeoutError) as error:
        return {**provenance, "status": "TRANSPORT_ERROR", "reason": str(error)}
    if len(data) > MAX_BYTES:
        return {**provenance, "status": "ARCHIVE_TOO_LARGE"}
    provenance.update(httpStatus=200, archiveSha256=digest(data), archiveBytes=len(data))
    first_line = data.split(b"\n", 1)[0]
    if not first_line.startswith((b"<SEC-DOCUMENT>", b"<IMS-DOCUMENT>")):
        return {**provenance, "status": "UNRECOGNIZED_ARCHIVE_ENVELOPE"}
    if row["accession"].encode("ascii") + b".txt" not in first_line:
        return {**provenance, "status": "ARCHIVE_ACCESSION_MISMATCH"}
    save_bytes(output / "submissions" / provenance["archiveSha256"], data)
    candidates = list(sections(data))
    selected, reason = select(candidates, row.get("exhibit"))
    provenance["selection"] = reason
    provenance["candidates"] = [meta for meta, _ in candidates]
    if selected is None:
        return {**provenance, "status": "EXHIBIT_UNRESOLVED"}
    meta, section = selected
    section_hash = digest(section)
    save_bytes(output / "sections" / section_hash, section)
    expected_bytes = row.get("bytes")
    history_verified = section_hash == row.get("sha256") and (expected_bytes is None or len(section) == expected_bytes)
    return {**provenance, "status": "OFFICIAL_ARCHIVE_SECTION", "historyVerified": history_verified,
            "sectionSha256": section_hash, "sectionBytes": len(section), **meta}


def load_roster(roster: Path | None, expected_sha: str | None):
    if roster is not None:
        source = roster.read_bytes()
        if digest(source) != expected_sha:
            raise ValueError("ROSTER_SHA256_MISMATCH")
        raw = json.loads(source)
        rows = raw["documents"] if isinstance(raw, dict) else raw
        return rows, expected_sha
    if expected_sha is not None:
        raise ValueError("ROSTER_REQUIRED_WITH_SHA256")
    gold = (ROOT / "gold/gold-docs.json").read_bytes()
    sample = (ROOT / "results/guidance-stratified-sample.json").read_bytes()
    known = {(int(x["cik"]), x["accession"]): x for x in json.loads(sample) if x.get("status") == "FETCHED"}
    rows = json.loads(gold)
    for row in rows:
        ref = known.get((int(row["cik"]), row["accession"]))
        if ref and ref["sha256"] == row["sha256"]:
            row["exhibit"], row["bytes"] = ref["exhibit"], ref["bytes"]
    return rows, digest(gold + sample)


def provenance_sha(record):
    body = {key: value for key, value in record.items() if key != "recordSha256"}
    return digest(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, help="Pinned JSON list of documents with CIK and accession")
    parser.add_argument("--expected-roster-sha256")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", help="Restrict to a roster split such as dev or final")
    parser.add_argument("--max-requests", type=int, required=True)
    args = parser.parse_args(argv)
    if args.max_requests < 0:
        parser.error("--max-requests must be nonnegative")
    rows, roster_hash = load_roster(args.roster, args.expected_roster_sha256)
    keys = [(int(row["cik"]), row["accession"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_ROSTER_IDENTITY")
    for row in rows:
        url_for(row)  # Validate identities before making any requests.
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    journal = output / "manifest.jsonl"
    previous = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            record = json.loads(line)
            if record.get("rosterSha256") != roster_hash or provenance_sha(record) != record.get("recordSha256"):
                raise ValueError("MANIFEST_IDENTITY_MISMATCH")
            previous[(record["cik"], record["accession"])] = record
    requests = 0
    for row in rows:
        if args.split is not None and row.get("split") != args.split:
            continue
        kept = previous.get((int(row["cik"]), row["accession"]))
        if kept and kept.get("sectionSha256"):
            path = output / "sections" / kept["sectionSha256"]
            if path.exists() and digest(path.read_bytes()) == kept["sectionSha256"]:
                continue
        if requests >= args.max_requests:
            break
        requests += 1
        result = recover(row, output)
        result["rosterSha256"] = roster_hash
        result["recordSha256"] = provenance_sha(result)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(result["split"], result["issuer"], result["accession"], result["status"], result.get("sectionSha256", ""),
              result.get("selection", ""), flush=True)
        if result.get("httpStatus") in {403, 429}:
            return 2
        time.sleep(0.7)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
