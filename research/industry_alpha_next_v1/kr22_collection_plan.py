"""Pinned DART request plan, fail-closed collector and offline verifier for the 16 in-window KR22 securities.

SOURCE-ONLY. No price, return, label or outcome is read. The plan is built from repository bytes alone
(`kr22-source-recovery.json` plus the `signal-history` disclosure index and fetch state at the pinned commit); the
collector is meant for an environment that may reach `opendart.fss.or.kr` with a DART key, and refuses to start
without one. This session's egress answers CONNECT 403 for every DART and KRX host, so nothing here has been run
against the live API, and nothing collected is admitted: industry and ex-date admission stay with the frozen
foundation rules (`kr_industry_membership_v2.admit`, DIRECT-only ex-dates).

What the plan asks for, and why each request can or cannot move a gate:

* LIST_A001 - `list.json` restricted to the periodic annual report (A001) over the fiscal years a security still
  needs an industry statement for (56 slots, 12 securities). The repository's own disclosure index kept only
  corporate-action families, so these receipts are not in `signal-history`.
* DOCUMENT_ANNUAL - `document.xml` for the 32 annual receipts already held in `kr-raw` and for every original
  A001 receipt LIST_A001 returns for a needed year. An annual report states an industry label in a minority of
  filings (12 explicit facts in the foundation's 112 reviewed), so the yield is measured, never assumed.
* DOCUMENT_DIVIDEND_DECISION - `document.xml` for the dividend-decision receipts the index already lists. The
  form states the record date (배당기준일) and the amount; it is not expected to state an ex-date, so this request
  can resolve record dates but cannot by itself satisfy the DIRECT-only ex-date gate.
* VIEWER_ROUTE_REQUIRED - the 35 failed terminal receipts. `document.xml` answered DART's 147-byte 014 envelope
  for every one of them on an exhausted retry, so asking it again is not a recovery attempt. They need the
  original-filing viewer route (`dart.fss.or.kr`), which #286's portable plan implements for XBRL attachments;
  this module does not reimplement or call it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path

from pipeline import kr_corporate_action_events as KCA

from . import inputs as IN
from . import kr22_source_recovery as R

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "kr22-collection-plan.json"
CONTRACT = "KR22_DART_COLLECTION_PLAN_V1"
MANIFEST_CONTRACT = "KR22_DART_COLLECTION_MANIFEST_V1"
SOURCE_COMMIT = R.DART_RAW_COMMIT
DISCLOSURES = "ledger/kr-corporate-actions/kr-corporate-actions-disclosures.jsonl.gz"
FETCH_STATE = R.FETCH_STATE
KINDS = ("LIST_A001", "DOCUMENT_ANNUAL", "DOCUMENT_DIVIDEND_DECISION", "VIEWER_ROUTE_REQUIRED")
# DART's own status codes that mean the request itself was refused, not that a filing does not exist.
REFUSAL_STATUSES = {"010", "011", "012", "020", "021", "100", "101", "800", "900", "901"}
DOCUMENT_ABSENT_STATUS = "014"   # document.xml: file not served
MAX_ZIP_MEMBERS = 64
MAX_MEMBER_BYTES = 64 << 20
MAX_TOTAL_BYTES = 256 << 20
# Served dividend decisions compress 4.5x-7.7x (141 real documents); a ratio past this is a bomb, not a filing.
MAX_COMPRESSION_RATIO = 100
UNSAFE_NAME_CHARS = re.compile(r"[\\\x00-\x1f:]")
ANNUAL_NAME = re.compile(r"^사업보고서\s*\((\d{4})\.(\d{2})\)$")


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


# --------------------------------------------------------------------------- #
# Plan (repository bytes only)
# --------------------------------------------------------------------------- #
def _ticker(code):
    return code if code.endswith(".KS") else code + ".KS"


def plan_requests(report, disclosures, fetch_state):
    """The request list for the in-window securities. Pure: inputs are the committed report and pinned bytes."""
    failed_state = {k for k, v in fetch_state["receipts"].items() if v.get("status") != "SUCCESS"}
    requests = []
    for q in report["requests"]:
        code, corp = q["code"], q["dartCorpCode"]
        if q.get("listJsonQuery"):
            requests.append({"kind": "LIST_A001", "code": code, "corpCode": corp, "params": dict(q["listJsonQuery"]),
                             "fiscalYears": sorted(q["fiscalYearsNeedingListJsonQuery"])})
        for year, receipt in sorted(q["annualReportReceiptsHeldInRepository"].items()):
            requests.append({"kind": "DOCUMENT_ANNUAL", "code": code, "corpCode": corp, "receiptNo": receipt,
                             "fiscalYear": int(year), "origin": "KR_RAW_HELD"})
        for row in sorted((r for r in disclosures if _ticker(r["ticker"]) == code
                           and "DIVIDEND_DECISION" in (r.get("disclosureFamilies") or [])), key=lambda r: r["receiptNo"]):
            if row["corpCode"] != corp:
                raise ValueError("DISCLOSURE_CORP_CODE_DIFFERS: " + row["receiptNo"])
            requests.append({"kind": "DOCUMENT_DIVIDEND_DECISION", "code": code, "corpCode": corp,
                             "receiptNo": row["receiptNo"], "receiptDate": row["receiptDate"],
                             "isAmendment": bool(row.get("isAmendment"))})
        for receipt in sorted(q["failedTerminalReceiptsToRetry"]):
            if receipt not in failed_state:
                raise ValueError("FAILED_RECEIPT_NOT_IN_FETCH_STATE: " + receipt)
            requests.append({"kind": "VIEWER_ROUTE_REQUIRED", "code": code, "corpCode": corp, "receiptNo": receipt,
                             "priorDocumentXml": "DART_014_FILE_NOT_SERVED_ON_EXHAUSTED_RETRY"})
    receipts = [r["receiptNo"] for r in requests if "receiptNo" in r]
    if len(receipts) != len(set(receipts)):
        raise ValueError("DUPLICATE_RECEIPT_IN_PLAN")
    return requests


def build_plan(root=IN.ROOT):
    report_path = HERE / "kr22-source-recovery.json"
    report = json.loads(report_path.read_text())
    blobs = IN.git_blobs(SOURCE_COMMIT, [DISCLOSURES, FETCH_STATE], root)
    disclosures = [json.loads(x) for x in gzip.decompress(blobs[DISCLOSURES]).decode().splitlines() if x.strip()]
    requests = plan_requests(report, disclosures, json.loads(blobs[FETCH_STATE]))
    counts = {k: sum(r["kind"] == k for r in requests) for k in KINDS}
    in_window = {q["code"] for q in report["requests"]}
    body = {"contract": CONTRACT, "evidenceClass": "SOURCE_REQUEST_PLAN_NOT_EVIDENCE",
            "historicalOutcomesRead": 0, "pricesRead": 0, "networkUsed": False,
            "denominator": report["summary"]["denominator"], "inWindowSecurities": sorted(in_window),
            "outOfWindowSecuritiesNotRequested": sorted(s["code"] for s in report["securities"] if s["code"] not in in_window),
            "inputs": {"kr22SourceRecoverySha256": IN.sha256(report_path.read_bytes()), "signalHistoryCommit": SOURCE_COMMIT,
                       "blobSha1": {p: IN.blob_sha1(blobs[p]) for p in sorted(blobs)}},
            "counts": counts, "fiscalYearSlots": sum(len(r["fiscalYears"]) for r in requests if r["kind"] == "LIST_A001"),
            "requests": requests}
    return {**body, "planSha256": digest(body)}


def load_plan(path=PLAN_PATH):
    plan = json.loads(Path(path).read_text())
    body = {k: v for k, v in plan.items() if k != "planSha256"}
    if digest(body) != plan.get("planSha256"):
        raise ValueError("PLAN_DIGEST_MISMATCH")
    return plan


# --------------------------------------------------------------------------- #
# Document parsing (shared by collector, verifier and extractors)
# --------------------------------------------------------------------------- #
def dart_status(raw):
    """DART's own <status> code in a non-ZIP response, or None."""
    m = re.search(rb"<status>\s*(\d{3})\s*</status>", raw[:4096])
    return m.group(1).decode() if m else None


def safe_member_name(name):
    """The member's name as a relative path, or ValueError. DART serves some document ZIPs with a single member named
    `/<receipt>.xml` (22 of 141 real dividend decisions). That one leading slash is read as relative ONLY when what
    follows is a single path component; every other absolute form, a backslash, a drive or stream colon, a control
    character, an empty, `.` or `..` component stays refused. Nothing is ever extracted to disk."""
    rest = name[1:] if name.startswith("/") and "/" not in name[1:] else name
    parts = rest.split("/")
    if (not rest or rest.startswith("/") or UNSAFE_NAME_CHARS.search(rest)
            or any(p in ("", ".", "..") for p in parts)):
        raise ValueError("UNSAFE_ZIP_MEMBER: " + name)
    return rest


def zip_members(raw):
    """Decoded members of a document.xml ZIP, read in memory. Refuses unsafe names, duplicates after normalisation,
    symlinks, encryption, too many members, oversized members, oversized totals and compression bombs."""
    if not raw.startswith(b"PK"):
        raise ValueError("NOT_A_ZIP")
    out, names, total = [], set(), 0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ValueError("TOO_MANY_ZIP_MEMBERS")
        for info in infos:
            name = safe_member_name(info.filename)
            if name in names:
                raise ValueError("DUPLICATE_ZIP_MEMBER: " + name)
            names.add(name)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("SYMLINK_ZIP_MEMBER: " + name)
            if info.flag_bits & 0x1:
                raise ValueError("ENCRYPTED_ZIP_MEMBER: " + name)
            total += info.file_size
            if info.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES:
                raise ValueError("UNSAFE_ZIP_MEMBER: " + info.filename)
            if info.file_size > MAX_COMPRESSION_RATIO * max(info.compress_size, 1):
                raise ValueError("ZIP_COMPRESSION_RATIO_EXCEEDED: " + name)
            data = z.read(info)
            if len(data) != info.file_size:
                raise ValueError("ZIP_MEMBER_SIZE_DIFFERS: " + name)
            for enc in ("utf-8", "cp949"):
                try:
                    text = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("UNDECODABLE_ZIP_MEMBER: " + name)
            out.append({"filename": name, "storedName": info.filename, "sha256": hashlib.sha256(data).hexdigest(),
                        "encoding": enc, "text": text})
    return out


# KRX exchange filings (receipts with an 8 in the 9th digit) are served as an HTML form with no DART header: no corp
# code, stock code or receipt number appears anywhere in the document (119 of 141 real dividend decisions).
XFORMS_HEADING = re.compile(r"^\s*([^/]{1,40}?)\s*/\s*([^/]{1,40}?)\s*/\s*\(\s*(\d{4})\.(\d{2})\.(\d{2})\s*\)")


def xforms_heading(text):
    """(filer name at filing, form title, heading date) of a KRX exchange-filing form, or None."""
    if 'class="xforms"' not in text:
        return None
    m = XFORMS_HEADING.match(flat(re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)))
    if not m:
        return None
    return m.group(1), m.group(2), "%s-%s-%s" % (m.group(3), m.group(4), m.group(5))


def listing_query(req):
    """The list.json query that must list a dividend-decision receipt: its issuer, on its receipt date."""
    day = req["receiptDate"].replace("-", "")
    return {"corp_code": req["corpCode"], "bgn_de": day, "end_de": day}


def header(text):
    """(corp code, document name) from the DART document header."""
    corp = re.search(r'<COMPANY-NAME[^>]*AREGCIK="(\d{8})"', text)
    name = re.search(r"<DOCUMENT-NAME[^>]*>([^<]*)<", text)
    return (corp.group(1) if corp else None), (name.group(1).strip() if name else None)


def flat(text):
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text.replace("&nbsp;", " ").replace("&cr;", " ")).strip()


DATE = r"(\d{4})\s*[-.년/]\s*(\d{1,2})\s*[-.월/]\s*(\d{1,2})"


def _date(m):
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()


def dividend_terms(text):
    """What a dividend-decision filing states directly: record date, common-share amount and, only if the
    filing itself states one, an ex-date. Nothing is derived; every absent field is None."""
    body = flat(text)
    record = re.search(r"배당\s*기준일\s*:?\s*" + DATE, body)
    ex = re.search(r"배당\s*락\s*일?\s*:?\s*" + DATE, body)
    amount = re.search(r"1\s*주\s*당\s*배당금\s*\(\s*원\s*\)\s*보통주식?\s*([\d,]+)", body)
    return {"recordDate": _date(record) if record else None,
            "exDate": _date(ex) if ex else None,
            "exDateSource": "DIRECT" if ex else None,
            "commonDividendPerShareKrw": int(amount.group(1).replace(",", "")) if amount else None}


# The anchor is the KSIC name itself. Patterns were developed against the foundation's 112 reviewed annual filings,
# whose 12 recorded explicit facts they all recover (with 1 candidate in the other 100): a DEVELOPMENT recall on the set
# the rules were written from, not an independent measurement.
ANCHOR = re.compile(r"표준\s*산업\s*분류")
LEAD = re.compile(r"^(?:[\]」』'‘\"“\s:：]|표|상의|상|의|에\s*의거하여|에\s*의거,?|에\s*의한|에\s*따른|에\s*따라|소분류에\s*의한"
                  r"|소분류인|소분류|동일한|코드|사업부문|[A-Z]?\d{2,6}|\(|\))+")
LABEL = re.compile(r"[가-힣][0-9가-힣 ,ㆍ·]*?업(?=\s*(?:\(|으로|로\s|을|를|이다|입니다|에\s*해당|이며|이고|,|\)|'|’|」|』|분류|$|\s))")
PARTICLE_END = re.compile(r"(?:를|을|는|은|이|가|의|에|로|며|고|여|서)$")


def industry_candidates(text):
    """Explicit KSIC statements in a periodic filing: code (if stated), label and the flattened context.

    A candidate is a reading-list entry. Admission stays `kr_industry_membership_v2.admit`'s decision on the hashed
    source, which also needs the locator to occur exactly once in it; `labelOccurrencesInSource` is reported for that."""
    body = flat(text)
    out = []
    for m in ANCHOR.finditer(body):
        after = body[m.end():m.end() + 140]
        rest = LEAD.sub("", after, count=1)
        lab = LABEL.match(rest)
        if lab:
            tail = re.match(r"\s*\(\s*(?:분류번호\s*[:：]\s*)?([A-Z]?\d{2,6})\s*\)", rest[lab.end():lab.end() + 30])
            head = re.search(r"([A-Z]?\d{3,6})\s*$", after[:len(after) - len(rest)])
            out.append(((tail or head).group(1) if (tail or head) else None, lab.group(0).strip(), "AFTER_ANCHOR"))
        before = body[max(0, m.start() - 60):m.start()]
        if re.search(r"업\s*\(\s*$", before):
            toks = re.sub(r"\s*\(\s*$", "", before).split()
            keep = [toks.pop()]
            while toks and len(keep) < 6 and (toks[-1] == "및" or not PARTICLE_END.search(toks[-1])):
                keep.insert(0, toks.pop())
            code = re.match(r"\s*[:：]?\s*([A-Z]?\d{2,6})", body[m.end():m.end() + 20])
            if re.match(r"[가-힣]", keep[0]):
                out.append((code.group(1) if code else None, " ".join(keep), "BEFORE_ANCHOR"))
    seen, unique = set(), []
    for code, label, where in out:
        key = (code, re.sub(r"\s+", "", label))
        if key not in seen:
            seen.add(key)
            unique.append({"reportedCode": code, "reportedLabel": key[1], "statedLabel": label, "position": where,
                           "labelOccurrencesInSource": text.count(label)})
    return unique


# --------------------------------------------------------------------------- #
# Collector (authorized environment only)
# --------------------------------------------------------------------------- #
class Refused(RuntimeError):
    pass


class BudgetExhausted(RuntimeError):
    pass


def _receipt_date(receipt):
    return dt.date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8]))


def annual_receipts_from_list(rows, corp, fiscal_years):
    """Original A001 receipts for the needed fiscal years from list.json rows. Amendments are kept separately."""
    picked, amendments = [], []
    for row in rows:
        if row.get("corp_code") != corp:
            raise ValueError("LIST_ROW_CORP_CODE_DIFFERS: " + str(row.get("rcept_no")))
        name = re.sub(r"\s+", " ", str(row.get("report_nm", ""))).strip()
        amend = name.startswith("[")
        m = ANNUAL_NAME.match(re.sub(r"^\[[^\]]*\]\s*", "", name))
        if not m or int(m.group(1)) not in fiscal_years:
            continue
        (amendments if amend else picked).append({"receiptNo": row["rcept_no"], "fiscalYear": int(m.group(1)),
                                                  "reportName": name})
    return sorted(picked, key=lambda r: r["receiptNo"]), sorted(amendments, key=lambda r: r["receiptNo"])


def collect(plan, out_dir, *, list_page, document, max_calls, now=None, pause=0.0):
    """Run the plan's LIST and DOCUMENT requests. `list_page(params, page_no) -> dict`, `document(receipt) -> bytes`.

    Every raw response is written once under `out_dir/raw/` and hashed into the manifest. A refusal status stops the
    run before any later call; a 013/014 answer is recorded as what DART said, never as proof a filing did not exist."""
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise ValueError("OUTPUT_DIRECTORY_NOT_EMPTY")
    (out / "raw").mkdir(parents=True)
    now = now or (lambda: dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat())
    calls, entries = 0, []

    def spend():
        nonlocal calls
        if calls >= max_calls:
            raise BudgetExhausted(f"{calls} calls")
        calls += 1
        time.sleep(pause)

    def keep(name, raw, meta):
        path = out / "raw" / name
        if path.exists():
            raise ValueError("DUPLICATE_RAW_NAME: " + name)
        path.write_bytes(raw)
        entries.append({**meta, "file": "raw/" + name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                        "retrievedAt": now()})

    def fetch_document(req, origin):
        spend()
        raw = document(req["receiptNo"])
        status = "ZIP" if raw.startswith(b"PK") else ("DART_" + (dart_status(raw) or "UNPARSED"))
        if status[5:] in REFUSAL_STATUSES:
            raise Refused(f"{req['receiptNo']}: {status}")
        keep(req["receiptNo"] + ".bin", raw, {"kind": req["kind"], "receiptNo": req["receiptNo"], "corpCode": req["corpCode"],
                                              "code": req["code"], "origin": origin, "status": status})

    try:
        for req in plan["requests"]:
            if req["kind"] == "LIST_A001":
                def fetch_page(page, req=req):
                    spend()
                    payload = list_page(req["params"], page)
                    status = str(payload.get("status"))
                    if status in REFUSAL_STATUSES:
                        raise Refused(f"list.json {req['code']}: {status}")
                    keep(f"list-{req['corpCode']}-p{page}.json", canonical(payload),
                         {"kind": "LIST_A001", "corpCode": req["corpCode"], "code": req["code"], "page": page,
                          "status": "DART_" + status})
                    return payload
                # The repository's own fail-closed walk: inconsistent or changing pagination raises, never truncates.
                rows, _ = KCA.fetch_all_pages(fetch_page)
                picked, _ = annual_receipts_from_list(rows, req["corpCode"], set(req["fiscalYears"]))
                for found in picked:
                    fetch_document({"kind": "DOCUMENT_ANNUAL", "code": req["code"], "corpCode": req["corpCode"],
                                    "receiptNo": found["receiptNo"]}, "LIST_A001_DISCOVERED")
            elif req["kind"] in ("DOCUMENT_ANNUAL", "DOCUMENT_DIVIDEND_DECISION"):
                fetch_document(req, req.get("origin", "INDEX_LISTED"))
        stop = "COMPLETE"
    except (Refused, BudgetExhausted, KCA.PaginationError) as exc:
        stop = f"{type(exc).__name__}: {exc}"
    manifest = {"contract": MANIFEST_CONTRACT, "planSha256": plan["planSha256"], "calls": calls, "stop": stop,
                "entries": entries}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    if stop == "COMPLETE":
        manifest = confirm_listings(plan, out, list_page=list_page, max_calls=max_calls - calls, now=now, pause=pause)
    return manifest


def confirm_listings(plan, out_dir, *, list_page, max_calls, now=None, pause=0.0):
    """Ask OpenDART's list.json, for every dividend-decision receipt the acquisition holds, whether that issuer filed
    that receipt on that day. This is the only issuer evidence a KRX exchange-filing form can have: the form names
    the filer as it was called on the day (LIG손해보험, 현대증권, 아이엔지생명) and carries no code at all. Raw pages
    are appended to the existing manifest; an already-confirmed receipt is not asked again."""
    out = Path(out_dir)
    manifest = json.loads((out / "manifest.json").read_text())
    if manifest.get("planSha256") != plan["planSha256"]:
        raise ValueError("MANIFEST_NOT_FOR_THIS_PLAN")
    now = now or (lambda: dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat())
    planned = {r["receiptNo"]: r for r in plan["requests"] if r["kind"] == "DOCUMENT_DIVIDEND_DECISION"}
    held = [e["receiptNo"] for e in manifest["entries"] if e.get("kind") == "DOCUMENT_DIVIDEND_DECISION"]
    done = {e["receiptNo"] for e in manifest["entries"] if e.get("kind") == "LISTING_CONFIRMATION"}
    calls, stop = 0, "COMPLETE"
    try:
        for receipt in held:
            if receipt in done:
                continue
            req = planned[receipt]

            def fetch_page(page, req=req, receipt=receipt):
                nonlocal calls
                if calls >= max_calls:
                    raise BudgetExhausted(f"{calls} listing calls")
                calls += 1
                time.sleep(pause)
                payload = list_page(listing_query(req), page)
                status = str(payload.get("status"))
                if status in REFUSAL_STATUSES:
                    raise Refused(f"list.json {receipt}: {status}")
                raw, name = canonical(payload), f"listing-{receipt}-p{page}.json"
                if (out / "raw" / name).exists():
                    raise ValueError("DUPLICATE_RAW_NAME: " + name)
                (out / "raw" / name).write_bytes(raw)
                manifest["entries"].append({"kind": "LISTING_CONFIRMATION", "receiptNo": receipt, "corpCode": req["corpCode"],
                                            "code": req["code"], "page": page, "query": listing_query(req),
                                            "status": "DART_" + status, "file": "raw/" + name,
                                            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "retrievedAt": now()})
                return payload
            KCA.fetch_all_pages(fetch_page)
    except (Refused, BudgetExhausted, KCA.PaginationError) as exc:
        stop = f"{type(exc).__name__}: {exc}"
    manifest["listingCalls"] = manifest.get("listingCalls", 0) + calls
    manifest["listingStop"] = stop
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return manifest


# --------------------------------------------------------------------------- #
# Offline verifier
# --------------------------------------------------------------------------- #
EXPECTED_DOCUMENT_NAME = {"DOCUMENT_ANNUAL": ("사업보고서",), "DOCUMENT_DIVIDEND_DECISION": ("배당",)}


def verify(plan, out_dir):
    """Re-check an acquisition against the pinned plan with no network. Returns problems; empty means consistent.

    It checks provenance and identity only. Passing does not admit any industry, ex-date or consideration."""
    out = Path(out_dir)
    problems = []
    try:
        manifest = json.loads((out / "manifest.json").read_text())
    except (OSError, ValueError):
        return ["MANIFEST_MISSING_OR_UNREADABLE"]
    if manifest.get("planSha256") != plan["planSha256"] or plan["planSha256"] != digest({k: v for k, v in plan.items() if k != "planSha256"}):
        problems.append("PLAN_DIGEST_MISMATCH")
    planned = {r["receiptNo"]: r for r in plan["requests"] if "receiptNo" in r and r["kind"] != "VIEWER_ROUTE_REQUIRED"}
    lists = {r["corpCode"]: r for r in plan["requests"] if r["kind"] == "LIST_A001"}
    listed_rows, seen_files, seen_receipts, confirmations = {}, set(), set(), {}
    documents = []
    for e in manifest.get("entries", []):
        path = out / e.get("file", "")
        if e.get("file") in seen_files:
            problems.append("DUPLICATE_FILE: " + str(e.get("file")))
            continue
        seen_files.add(e.get("file"))
        if path.is_symlink() or not path.is_file() or path.resolve().parent != (out / "raw").resolve():
            problems.append("FILE_MISSING_OR_OUTSIDE_RAW: " + str(e.get("file")))
            continue
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != e.get("sha256"):
            problems.append("SHA256_MISMATCH: " + e["file"])
            continue
        if e["kind"] == "LISTING_CONFIRMATION":
            req = planned.get(e.get("receiptNo"))
            payload = json.loads(raw)
            if req is None or req["kind"] != "DOCUMENT_DIVIDEND_DECISION" or e.get("query") != listing_query(req) \
                    or e.get("corpCode") != req["corpCode"]:
                problems.append("LISTING_NOT_IN_PLAN: " + e["file"])
                continue
            if e.get("status") != "DART_" + str(payload.get("status")):
                problems.append("STATUS_DOES_NOT_MATCH_BYTES: " + e["file"])
                continue
            for row in payload.get("list") or []:
                if row.get("corp_code") != req["corpCode"] or str(row.get("rcept_dt")) != req["receiptDate"].replace("-", ""):
                    problems.append("LISTING_ROW_OUTSIDE_QUERY: " + str(row.get("rcept_no")))
                    break
            else:
                confirmations.setdefault(e["receiptNo"], []).extend(payload.get("list") or [])
            continue
        if e["kind"] == "LIST_A001":
            req = lists.get(e.get("corpCode"))
            payload = json.loads(raw)
            if req is None:
                problems.append("LIST_NOT_IN_PLAN: " + e["file"])
                continue
            for row in payload.get("list") or []:
                if row.get("corp_code") != req["corpCode"]:
                    problems.append("LIST_ROW_CORP_CODE_DIFFERS: " + str(row.get("rcept_no")))
                elif not (req["params"]["bgn_de"] <= str(row.get("rcept_dt")) <= req["params"]["end_de"]):
                    problems.append("LIST_ROW_OUTSIDE_QUERY_WINDOW: " + str(row.get("rcept_no")))
            listed_rows.setdefault(req["corpCode"], []).extend(payload.get("list") or [])
            continue
        receipt = e.get("receiptNo")
        if receipt in seen_receipts:
            problems.append("DUPLICATE_RECEIPT: " + str(receipt))
            continue
        seen_receipts.add(receipt)
        if e.get("origin") == "LIST_A001_DISCOVERED":
            req = lists.get(e.get("corpCode"))
            rows = listed_rows.get(e.get("corpCode"), [])
            picked = {r["receiptNo"] for r in annual_receipts_from_list(rows, req["corpCode"], set(req["fiscalYears"]))[0]} if req else set()
            if receipt not in picked:
                problems.append("DISCOVERED_RECEIPT_NOT_IN_VERIFIED_LIST: " + str(receipt))
                continue
        elif receipt not in planned or planned[receipt]["corpCode"] != e.get("corpCode") or planned[receipt]["kind"] != e.get("kind"):
            problems.append("RECEIPT_NOT_IN_PLAN: " + str(receipt))
            continue
        if _receipt_date(receipt) > dt.date.fromisoformat(e["retrievedAt"][:10]):
            problems.append("RECEIPT_DATED_AFTER_RETRIEVAL: " + receipt)
        if e.get("status") != "ZIP":
            if raw.startswith(b"PK") or e.get("status") != "DART_" + str(dart_status(raw)):
                problems.append("STATUS_DOES_NOT_MATCH_BYTES: " + receipt)
            continue
        try:
            members = zip_members(raw)
        except (ValueError, zipfile.BadZipFile) as exc:
            problems.append(f"ZIP_REFUSED: {receipt}: {exc}")
            continue
        documents.append((e, members))
    # Issuer checks run after every listing page is read, whatever the manifest order.
    for e, members in documents:
        problems.extend(document_identity(e, members, planned.get(e["receiptNo"]), confirmations.get(e["receiptNo"])))
    return problems


def document_identity(entry, members, req, listing):
    """Issuer and form checks for one held document. A DART-header document must name the planned corp code in
    every XML member. A header-less KRX form is accepted only as the single member `<receipt>.xml`, with a heading
    dated on the receipt date, naming a form of the planned kind, and with list.json confirming that the planned
    issuer filed exactly this receipt, of that kind, on that day. The filer name in the heading is reported, never
    matched: it is the name on the day, and issuers rename."""
    receipt, problems = entry["receiptNo"], []
    xml = [m for m in members if m["filename"].lower().endswith(".xml")]
    heads = [header(m["text"]) for m in xml]
    if heads and all(c is not None for c, _ in heads):
        if any(c != entry["corpCode"] for c, _ in heads):
            problems.append("DOCUMENT_ISSUER_DIFFERS_FROM_PLAN: " + receipt)
        if not any(k in (heads[0][1] or "") for k in EXPECTED_DOCUMENT_NAME[entry["kind"]]):
            problems.append("DOCUMENT_NAME_DIFFERS_FROM_KIND: " + receipt)
        return problems
    form = xforms_heading(xml[0]["text"]) if len(xml) == 1 and len(members) == 1 else None
    if entry["kind"] != "DOCUMENT_DIVIDEND_DECISION" or form is None:
        return ["DOCUMENT_ISSUER_DIFFERS_FROM_PLAN: " + receipt]
    if members[0]["filename"] != receipt + ".xml":
        problems.append("DOCUMENT_MEMBER_NOT_THIS_RECEIPT: " + receipt)
    if req is None or form[2] != req.get("receiptDate"):
        problems.append("DOCUMENT_HEADING_DATE_DIFFERS_FROM_RECEIPT: " + receipt)
    if not any(k in form[1] for k in EXPECTED_DOCUMENT_NAME[entry["kind"]]):
        problems.append("DOCUMENT_NAME_DIFFERS_FROM_KIND: " + receipt)
    hits = [r for r in listing or [] if r.get("rcept_no") == receipt]
    if listing is None:
        problems.append("ISSUER_NOT_PROVEN_NO_HEADER_NO_LISTING: " + receipt)
    elif len(hits) != 1 or "배당결정" not in re.sub(r"[\sㆍ·]", "", str(hits[0].get("report_nm"))):
        problems.append("LISTING_DOES_NOT_CONFIRM_RECEIPT: " + receipt)
    return problems


def extract(plan, out_dir):
    """Candidates from a VERIFIED acquisition. Refuses an unverified directory."""
    problems = verify(plan, out_dir)
    if problems:
        raise ValueError("ACQUISITION_NOT_VERIFIED: " + "; ".join(problems[:5]))
    out = Path(out_dir)
    manifest = json.loads((out / "manifest.json").read_text())
    rows = []
    for e in manifest["entries"]:
        if e["kind"] == "LIST_A001" or e["status"] != "ZIP":
            continue
        members = zip_members((out / e["file"]).read_bytes())
        text = "\n".join(m["text"] for m in members)
        row = {"code": e["code"], "receiptNo": e["receiptNo"], "kind": e["kind"], "sourceSha256": e["sha256"]}
        if e["kind"] == "DOCUMENT_DIVIDEND_DECISION":
            row.update(dividend_terms(text))
        else:
            row["industryCandidates"] = industry_candidates(text)
        rows.append(row)
    return rows


def acquisition_effect(report, extracted=None):
    """Gate counts on the full 22 denominator, before and after an acquisition.

    A candidate never sets a gate: industry needs an admitted observation, ex-date a DIRECT ex-date on every in-window
    dividend event. Record dates resolved and industry candidates found are reported beside the gates."""
    extracted = extracted or []
    by_code = {}
    for row in extracted:
        by_code.setdefault(row["code"], []).append(row)
    gates = ("industryAdmitted", "terminalConsiderationResolved", "executionConfirmed", "exDateSemanticsResolved")
    after_rows = {}
    for s in report["securities"]:
        g = dict(s["gatesAfter"])
        decisions = [r for r in by_code.get(s["code"], []) if r["kind"] == "DOCUMENT_DIVIDEND_DECISION"]
        g["exDateSemanticsResolved"] = bool(g["exDateSemanticsResolved"] or (
            decisions and all(r.get("exDateSource") == "DIRECT" for r in decisions)))
        after_rows[s["code"]] = g
    before_rows = {s["code"]: s["gatesAfter"] for s in report["securities"]}
    count = lambda rows, g: sum(bool(r[g]) for r in rows.values())  # noqa: E731
    eligible = lambda rows: sum(all(r[g] for g in gates) for r in rows.values())  # noqa: E731
    return {"denominator": len(report["securities"]),
            "gatesBefore": {g: count(before_rows, g) for g in gates},
            "gatesAfter": {g: count(after_rows, g) for g in gates},
            "totalReturnLabelEligible": {"before": eligible(before_rows), "after": eligible(after_rows)},
            "recordDatesStated": sum(1 for r in extracted if r.get("recordDate")),
            "securitiesWithIndustryCandidates": len({r["code"] for r in extracted if r.get("industryCandidates")}),
            "documentsExtracted": len(extracted)}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _dart_callers(key):  # pragma: no cover - network
    import urllib.parse
    import urllib.request

    base = "https://opendart.fss.or.kr/api/"

    def get(path, params):
        url = base + path + "?" + urllib.parse.urlencode({"crtfc_key": key, **params})
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()

    def list_page(params, page):
        return json.loads(get("list.json", {**params, "page_no": page, "page_count": 100}))

    def document(receipt):
        return get("document.xml", {"rcept_no": receipt})

    return list_page, document


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-plan").add_argument("--output", default=str(PLAN_PATH))
    c = sub.add_parser("collect")
    c.add_argument("--output", required=True)
    c.add_argument("--max-calls", type=int, default=400)
    v = sub.add_parser("verify")
    v.add_argument("--input", required=True)
    x = sub.add_parser("extract")
    x.add_argument("--input", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "build-plan":
        Path(args.output).write_text(json.dumps(build_plan(), ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        return 0
    plan = load_plan()
    if args.cmd == "collect":  # pragma: no cover - network
        import os
        key = os.environ.get("DART_API_KEY")
        if not key:
            sys.stderr.write("DART_API_KEY is required; refusing to start.\n")
            return 2
        manifest = collect(plan, args.output, *_dart_callers(key), max_calls=args.max_calls, pause=0.3)
        problems = verify(plan, args.output)
        sys.stdout.write(json.dumps({"stop": manifest["stop"], "calls": manifest["calls"], "entries": len(manifest["entries"]),
                                     "verifyProblems": problems}, ensure_ascii=False) + "\n")
        return 0 if manifest["stop"] == "COMPLETE" and not problems else 3
    if args.cmd == "verify":
        problems = verify(plan, args.input)
        sys.stdout.write(json.dumps({"problems": problems}, ensure_ascii=False) + "\n")
        return 0 if not problems else 3
    rows = extract(plan, args.input)
    report = json.loads((HERE / "kr22-source-recovery.json").read_text())
    sys.stdout.write(json.dumps({"effect": acquisition_effect(report, rows), "rows": rows}, ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
