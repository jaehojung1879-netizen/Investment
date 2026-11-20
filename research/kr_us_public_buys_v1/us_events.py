"""Official SEC Form 4 source acquisition and outcome-free normalization.

The quarterly files are complete official as-filed extracts. P alone never
establishes an open-market purchase. Prices, returns and strategy code are not
read by this module.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from zoneinfo import ZoneInfo

import exchange_calendars as xc
import pandas as pd

HERE = Path(__file__).resolve().parent
CATALOG = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"
USER_AGENT = "InvestmentResearchDashboard/1.1 jaehojung1879-netizen@users.noreply.github.com"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate",
           "Accept": "application/zip, application/json, text/html, text/plain, */*"}
REQUIRED = ("SUBMISSION.tsv", "NONDERIV_TRANS.tsv", "REPORTINGOWNER.tsv", "FOOTNOTES.tsv")
OPEN = re.compile(r"\bopen[\s\-]+market\b", re.I)
PRIVATE = re.compile(r"\bprivat(?:e|ely)\b|\bnegotiated\b|\bsubscription (?:agreement|purchase)\b|"
                     r"\bdirect(?:ly)? from (?:the )?(?:issuer|company)\b|\bprivate placement\b", re.I)
PLAN = re.compile(r"employee stock purchase|dividend reinvestment|payroll deduction|employee purchase plan|"
                  r"stock purchase plan|pursuant to.{0,45}401\s*\(?k", re.I)
NEGATED_OPEN = re.compile(r"(?:not|other than|outside).{0,25}open[\s\-]+market", re.I)
NON_COMMON = re.compile(r"preferred|preference|warrant|option|restricted stock unit|\bRSU\b|phantom|"
                        r"depositary|depositary|\bADR\b|convertible|\bunits?\b", re.I)
COMMON = re.compile(r"common(?:\s+(?:stock|shares?))?|ordinary\s+shares?", re.I)
KNOWN_NON_PURCHASE = {"A", "C", "D", "E", "F", "G", "H", "M", "O", "S", "U", "W", "X", "Z"}
UTC, NY = timezone.utc, ZoneInfo("America/New_York")


def stamp():
    return datetime.now(UTC).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def normalized_cik(value):
    text = str(value or "").strip()
    return str(int(text)) if text.isdigit() and int(text) > 0 else None


def local_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("INVALID_SEC_DATE:" + text)


def decode(raw, encoding=""):
    if "gzip" in encoding.lower() or raw.startswith(b"\x1f\x8b"):
        return gzip.decompress(raw)
    if "deflate" in encoding.lower():
        import zlib
        return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def capture(url, dest, *, cap=32 * 1024 * 1024, pause=.35):
    """Retain decoded official bytes and the wire hash; no silent refusal retries."""
    receipt_path = dest.with_name(dest.name + ".receipt.json")
    if dest.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if sha(dest.read_bytes()) != receipt["sha256"]:
            raise ValueError("CAPTURE_HASH_MISMATCH:" + str(dest))
        return receipt
    observed = stamp()
    if receipt_path.exists() and not dest.exists():
        prior = json.loads(receipt_path.read_text())
        if prior.get("url") != url:
            save_json(receipt_path.with_name(receipt_path.name + ".prior-route.json"), prior)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as response:
            status, wire = response.status, response.read(cap + 1)
            encoding = response.headers.get("Content-Encoding", "")
            content_type = response.headers.get("Content-Type")
    except urllib.error.HTTPError as error:
        status, wire = error.code, error.read(128 * 1024)
        encoding = error.headers.get("Content-Encoding", "")
        content_type = error.headers.get("Content-Type")
    if len(wire) > cap:
        raise ValueError("OFFICIAL_SOURCE_BYTE_CAP:" + url)
    body = decode(wire, encoding)
    block = next((s for s in ("Undeclared Automated Tool", "Request Rate Threshold Exceeded",
                              "Your Request Originates from") if s.lower() in body[:10000].decode("utf-8", "replace").lower()), None)
    receipt = {"url": url, "observedAtUTC": observed, "status": status, "bytes": len(body),
               "sha256": sha(body), "wireSha256": sha(wire), "contentEncoding": encoding,
               "contentType": content_type, "bodyBlockMarker": block, "userAgentSource": "scripts/probe_us_pit_fundamentals.py:SEC_HEADERS"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    save_json(receipt_path, receipt)
    time.sleep(pause)
    if status != 200 or block:
        raise ValueError("OFFICIAL_SOURCE_REFUSED:" + json.dumps(receipt))
    return receipt


def acquire(private, inputs, first="2014q1", last="2026q3"):
    catalog_path = private / "catalog.html"
    receipt = capture(CATALOG, catalog_path, cap=2 * 1024 * 1024)
    html = catalog_path.read_text()
    links = re.findall(r'href=["\']([^"\']+?/(\d{4}q[1-4])_form345\.zip)["\']', html, re.I)
    sources = {quarter.lower(): urllib.parse.urljoin(CATALOG, url) for url, quarter in links}
    if not sources:
        raise ValueError("SEC_CATALOG_HAS_NO_QUARTER_LINKS")
    quarters = [f"{y}q{q}" for y in range(2006, 2027) for q in range(1, 5) if first <= f"{y}q{q}" <= last]
    rows, errors = [], []
    for quarter in quarters:
        if quarter not in sources:
            errors.append({"quarter": quarter, "reason": "OFFICIAL_CATALOG_LINK_ABSENT"})
            continue
        path = private / "bulk" / (quarter + "_form345.zip")
        try:
            got = capture(sources[quarter], path)
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if not set(REQUIRED).issubset(names):
                    raise ValueError("SEC_REQUIRED_TABLES_ABSENT")
                if quarter == "2024q1":
                    for name in ("FORM_345_metadata.json", "FORM_345_readme.htm"):
                        (inputs / name).parent.mkdir(parents=True, exist_ok=True)
                        (inputs / (name + ".gz")).write_bytes(gzip.compress(archive.read(name), mtime=0))
            rows.append({"quarter": quarter, "privatePath": str(path), **got})
            print("SEC quarter verified", quarter, got["bytes"], flush=True)
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            errors.append({"quarter": quarter, "reason": str(error)})
    manifest = {"source": "SEC_OFFICIAL_INSIDER_TRANSACTIONS_DATA_SETS", "catalog": receipt,
                "requestedFirstQuarter": first, "requestedLastQuarter": last,
                "quarters": rows, "errors": errors, "outcomesRead": 0,
                "sourceVintage": "CURRENT_OFFICIAL_REPROCESSING_OF_AS_FILED_SUBMISSIONS",
                "quarterBoundaryRule": "SEC filings after 17:30 ET on the last business day appear in the next quarterly posting. The final quarterly boundary day is conservatively outside complete coverage."}
    save_json(inputs / "source-manifest.json", manifest)
    return manifest


def tsv(archive, name):
    with io.TextIOWrapper(archive.open(name), encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream, delimiter="\t")


def positive_number(value):
    try:
        number = Decimal(str(value).strip())
        return number if number.is_finite() and number > 0 else None
    except InvalidOperation:
        return None


def classify(transaction, notes, owner_roles):
    code = str(transaction.get("TRANS_CODE", "")).strip().upper()
    acquired = str(transaction.get("TRANS_ACQUIRED_DISP_CD", "")).upper() == "A"
    title = transaction.get("SECURITY_TITLE", "")
    quantity = positive_number(transaction.get("TRANS_SHARES"))
    price = positive_number(transaction.get("TRANS_PRICEPERSHARE"))
    if not acquired:
        return "EXCLUDED_DISPOSITION", "NOT_ACQUISITION"
    if code != "P":
        if code in KNOWN_NON_PURCHASE:
            return "EXCLUDED_NON_PURCHASE_CODE", "KNOWN_AWARD_GIFT_EXERCISE_OR_OTHER_NON_PURCHASE"
        return "INDETERMINATE_ACQUISITION", "ACQUISITION_CODE_DOES_NOT_ESTABLISH_OPEN_MARKET_CASH_BUY"
    if not any(re.search(r"Director|Officer|TenPercentOwner", role, re.I) for role in owner_roles):
        return "INDETERMINATE_P", "ELIGIBLE_REPORTER_ROLE_NOT_ESTABLISHED"
    if NON_COMMON.search(title):
        return "EXCLUDED_NON_COMMON", "EXPLICIT_NON_COMMON_SECURITY"
    if not COMMON.search(title):
        return "INDETERMINATE_P", "COMMON_SHARE_CLASS_NOT_ESTABLISHED"
    if quantity is None or price is None:
        return "INDETERMINATE_P", "POSITIVE_CASH_QUANTITY_AND_PRICE_NOT_ESTABLISHED"
    opened, private, plan, negated = bool(OPEN.search(notes)), bool(PRIVATE.search(notes)), bool(PLAN.search(notes)), bool(NEGATED_OPEN.search(notes))
    if negated:
        return "INDETERMINATE_P", "OPEN_MARKET_PHRASE_NEGATED"
    if opened and (private or plan):
        return "INDETERMINATE_P", "CONFLICTING_OPEN_MARKET_AND_PRIVATE_OR_PLAN_EVIDENCE"
    if private:
        return "EXCLUDED_PRIVATE", "EXPLICIT_PRIVATE_OR_NEGOTIATED_PURCHASE"
    if plan:
        return "EXCLUDED_PLAN_PURCHASE", "EMPLOYEE_OR_REINVESTMENT_PLAN_PURCHASE"
    if not opened:
        return "INDETERMINATE_P", "P_IS_OPEN_MARKET_OR_PRIVATE_WITHOUT_EXPLICIT_ROW_EVIDENCE"
    return "CONFIRMED_OPEN_MARKET", "EXPLICIT_TRANSACTION_LINKED_OPEN_MARKET_FOOTNOTE"


def source_excerpt(notes):
    match = OPEN.search(notes) or PRIVATE.search(notes) or PLAN.search(notes)
    return notes[max(0, match.start()-100):match.end()+300] if match else notes[:400]


def normalize_quarter(path, quarter, calendar):
    archive_sha = sha(path.read_bytes())
    availability = {}
    with zipfile.ZipFile(path) as archive:
        submissions = {r["ACCESSION_NUMBER"]: r for r in tsv(archive, "SUBMISSION.tsv")}
        owners = defaultdict(list)
        for row in tsv(archive, "REPORTINGOWNER.tsv"):
            owners[row["ACCESSION_NUMBER"]].append(row)
        footnotes = {(r["ACCESSION_NUMBER"], r["FOOTNOTE_ID"]): r["FOOTNOTE_TXT"] for r in tsv(archive, "FOOTNOTES.tsv")}
        events, excluded, forms, codes = [], Counter(), Counter(), Counter()
        raw_rows = defaultdict(list)
        for transaction in tsv(archive, "NONDERIV_TRANS.tsv"):
            accession = transaction["ACCESSION_NUMBER"]
            submission = submissions.get(accession)
            if submission is None:
                raise ValueError("NONDERIV_ROW_WITHOUT_SUBMISSION:" + accession)
            document_type = submission["DOCUMENT_TYPE"].upper()
            forms[document_type] += 1
            code = transaction.get("TRANS_CODE", "").upper()
            codes[code] += 1
            if document_type not in ("4", "4/A"):
                excluded["NOT_FORM4_OR_4A"] += 1
                continue
            raw_refs = sorted(set(re.findall(r"\bF\d+\b", " ".join(v for k, v in transaction.items() if k.endswith("_FN")))))
            raw_rows[accession].append({"accession": accession, "rowId": transaction["NONDERIV_TRANS_SK"],
                "transDate": local_date(transaction["TRANS_DATE"]), "title": transaction.get("SECURITY_TITLE", ""),
                "qty": transaction.get("TRANS_SHARES", ""), "price": transaction.get("TRANS_PRICEPERSHARE", ""),
                "code": code, "acquired": transaction.get("TRANS_ACQUIRED_DISP_CD", ""),
                "notes": "\n".join(footnotes.get((accession, r), "") for r in raw_refs) if document_type == "4/A" else ""})
            if code != "P" and (code in KNOWN_NON_PURCHASE or transaction.get("TRANS_ACQUIRED_DISP_CD") != "A"):
                excluded["NON_P_KNOWN_NON_PURCHASE_OR_DISPOSITION"] += 1
                continue
            accession_owners = owners.get(accession, [])
            owner_roles = sorted({r["RPTOWNER_RELATIONSHIP"] for r in accession_owners})
            owner_ciks = sorted({c for r in accession_owners if (c := normalized_cik(r["RPTOWNERCIK"]))})
            refs = sorted(set(re.findall(r"\bF\d+\b", " ".join(v for k, v in transaction.items() if k.endswith("_FN")))))
            note = "\n".join(footnotes.get((accession, ref), "") for ref in refs)
            unresolved_refs = [ref for ref in refs if (accession, ref) not in footnotes]
            status, reason = classify(transaction, note, owner_roles)
            transaction_date = local_date(transaction["TRANS_DATE"])
            if transaction_date is None and status == "CONFIRMED_OPEN_MARKET":
                status, reason = "INDETERMINATE_P", "TRANSACTION_DATE_UNRESOLVED"
            if unresolved_refs and status == "CONFIRMED_OPEN_MARKET":
                status, reason = "INDETERMINATE_P", "TRANSACTION_FOOTNOTE_REFERENCE_MISSING"
            filed = local_date(submission["FILING_DATE"])
            if filed not in availability:
                session = calendar.date_to_session(filed, direction="next")
                if pd.Timestamp(session).date().isoformat() == filed:
                    session = calendar.next_session(session)
                availability[filed] = calendar.session_close(session).isoformat()
            available = availability[filed]
            qty, price = positive_number(transaction["TRANS_SHARES"]), positive_number(transaction["TRANS_PRICEPERSHARE"])
            issuer = normalized_cik(submission["ISSUERCIK"])
            source = f"https://www.sec.gov/Archives/edgar/data/{issuer}/{accession.replace('-', '')}/{accession}.txt"
            events.append({
                "eventId": accession + "|ND|" + transaction["NONDERIV_TRANS_SK"], "market": "US",
                "ticker": submission.get("ISSUERTRADINGSYMBOL", "").strip().upper().replace(".", "-"),
                "issuerCIK": issuer, "issuerName": submission.get("ISSUERNAME", ""),
                "accession": accession, "documentType": document_type,
                "transactionRowId": transaction["NONDERIV_TRANS_SK"],
                "transactionDate": transaction_date, "filingDate": filed,
                "availableAt": available, "timeBasis": "BULK_FILING_DATE_NEXT_SESSION_CLOSE",
                "acceptedAt": "", "acceptedAtBasis": "", "invalidatedAt": "",
                "status": status, "reason": reason, "transactionCode": code,
                "acquiredDisposed": transaction.get("TRANS_ACQUIRED_DISP_CD", ""),
                "securityTitle": transaction.get("SECURITY_TITLE", ""),
                "quantity": str(qty) if qty is not None else "", "price": str(price) if price is not None else "",
                "value": str(qty * price) if qty is not None and price is not None else "",
                "ownerCIKs": json.dumps(owner_ciks), "ownerRoles": json.dumps(owner_roles),
                "footnoteIds": json.dumps(refs), "unresolvedFootnoteIds": json.dumps(unresolved_refs),
                "sourceFootnotesSha256": sha(note.encode()), "sourceFootnoteExcerpt": source_excerpt(note),
                "classificationEvidence": "SEC_OFFICIAL_AS_FILED_TRANSACTION_LINKED_FOOTNOTE_EXTRACT",
                "sourceURL": source, "sourceQuarter": quarter, "sourceArchiveSha256": archive_sha,
                "isAmendment": document_type == "4/A", "originalSubmissionDate": local_date(submission.get("DATE_OF_ORIG_SUB")),
                "amendmentOf": "", "amendmentLinkStatus": "NOT_AMENDMENT" if document_type != "4/A" else "UNRESOLVED",
                "aff10b5one": submission.get("AFF10B5ONE", ""),
            })
        filing_metadata = []
        for accession, submission in submissions.items():
            if submission["DOCUMENT_TYPE"].upper() not in ("4", "4/A"):
                continue
            filing_metadata.append({"accession": accession, "issuerCIK": normalized_cik(submission["ISSUERCIK"]),
                "filingDate": local_date(submission["FILING_DATE"]),
                "documentType": submission["DOCUMENT_TYPE"].upper(),
                "originalSubmissionDate": local_date(submission.get("DATE_OF_ORIG_SUB")),
                "ownerCIKs": tuple(sorted({c for r in owners.get(accession, []) if (c := normalized_cik(r["RPTOWNERCIK"]))}))})
        interested = {r["accession"] for r in events} | {a for a,s in submissions.items() if s["DOCUMENT_TYPE"].upper() == "4/A"}
        retained_rows = [r for a,rr in raw_rows.items() if a in interested for r in rr]
        return events, filing_metadata, {"quarter": quarter, "formsByTransaction": dict(forms),
                "codesAllNonDerivativeTransactions": dict(codes), "excludedBeforePotentialBuyTable": dict(excluded),
                "potentialBuyRows": len(events), "statusCounts": dict(Counter(e["status"] for e in events))}, retained_rows


def apply_amendments(events, filings, calendar):
    """Link individual economic rows; an amendment never replaces a whole filing."""
    filings.row_factory = sqlite3.Row
    by_id = {e["eventId"]: e for e in events}
    receipt, audit = Counter(), []
    first_confirmed = {}
    for e in events:
        if not e["isAmendment"] and e["status"] == "CONFIRMED_OPEN_MARKET":
            first_confirmed[e["eventId"]] = e

    def number(value):
        try:
            v = Decimal(str(value))
            return v if v.is_finite() else None
        except InvalidOperation:
            return None

    def economic(row):
        return (row["transDate"], re.sub(r"\W+", "", row["title"]).lower(), number(row["qty"]), number(row["price"]))

    amendments = filings.execute("SELECT * FROM filings WHERE documentType='4/A' ORDER BY filingDate,accession")
    for filing in amendments:
        key = (filing["issuerCIK"], filing["ownerCIKs"], filing["originalSubmissionDate"])
        possible = filings.execute("SELECT * FROM filings WHERE issuerCIK=? AND ownerCIKs=? AND filingDate=? AND documentType='4'", key).fetchall()
        original_rows = [r for f in possible for r in filings.execute("SELECT * FROM transactions WHERE accession=?", (f["accession"],))]
        amended_rows = filings.execute("SELECT * FROM transactions WHERE accession=?", (filing["accession"],)).fetchall()
        session = calendar.date_to_session(filing["filingDate"], direction="next")
        if pd.Timestamp(session).date().isoformat() == filing["filingDate"]:
            session = calendar.next_session(session)
        when = calendar.session_close(session).isoformat()
        for row in amended_rows:
            amended = by_id.get(row["accession"] + "|ND|" + row["rowId"])
            full_key = economic(row)
            matches = [o for o in original_rows if economic(o) == full_key and all(v is not None and v != "" for v in full_key)]
            mode = "EXACT_ECONOMIC_ROW" if len(matches) == 1 else None
            if not matches:
                # Changed economic fields require row-linked explicit correction text.
                coarse = [o for o in original_rows if economic(o)[:2] == full_key[:2]]
                relevant = []
                if len(coarse) == 1:
                    previous_key = economic(coarse[0])
                    if previous_key[2] != full_key[2]:
                        relevant.append(r"shares?|quantity|number")
                    if previous_key[3] != full_key[3]:
                        relevant.append(r"price|consideration|amount")
                correction = any(re.search(r"correct|inadvertent|erroneous", sentence, re.I)
                                 and re.search("|".join(relevant), sentence, re.I)
                                 for sentence in re.split(r"[.!?;\n]", row["notes"])) if relevant else False
                if len(coarse) == 1 and correction:
                    matches, mode = coarse, "UNIQUE_ROW_AND_EXPLICIT_CORRECTION_FOOTNOTE"
            original = by_id.get(matches[0]["accession"] + "|ND|" + matches[0]["rowId"]) if len(matches) == 1 else None
            if original is None:
                if amended is not None:
                    amended["amendmentLinkStatus"] = "ECONOMIC_ROW_UNRESOLVED"
                    if amended["transactionCode"] == "P":
                        amended["status"], amended["reason"] = "INDETERMINATE_P", "AMENDMENT_ECONOMIC_ROW_LINK_UNRESOLVED"
                receipt["unresolvedEconomicRows"] += 1
                continue
            original_id = original["eventId"]
            if amended is not None:
                amended["amendmentOf"] = original["accession"]
                amended["amendmentLinkStatus"] = mode
                amended["originalEventId"] = original_id
            existing = first_confirmed.get(original_id)
            exact_same_purchase = (mode == "EXACT_ECONOMIC_ROW" and row["code"] == "P" and row["acquired"] == "A")
            if amended is not None and existing is not None and exact_same_purchase and amended["status"] == "CONFIRMED_OPEN_MARKET":
                amended["status"], amended["reason"] = "EXCLUDED_DUPLICATE_RESTATEMENT", "IDENTICAL_ECONOMIC_BUY_ALREADY_PUBLICLY_CONFIRMED"
                amended["duplicateOfEventId"] = existing["eventId"]
                amended["firstKnownAt"] = existing["availableAt"]
                receipt["duplicateConfirmedRestatements"] += 1
                audit.append({"amendment": row["accession"], "rowId": row["rowId"], "originalEventId": original_id,
                              "action": "PRESERVE_FIRST_CONFIRMATION", "availableAt": when, "mode": mode})
                continue
            # Invalidate exactly this row, including a proved P-to-gift correction.
            target = existing or original
            if not target["invalidatedAt"] or when < target["invalidatedAt"]:
                target["invalidatedAt"] = when
            if amended is not None and amended["status"] == "CONFIRMED_OPEN_MARKET":
                first_confirmed[original_id] = amended
                receipt["newlyConfirmedByAmendment"] += 1
            else:
                first_confirmed.pop(original_id, None)
                receipt["individualRowCorrections"] += 1
            audit.append({"amendment": row["accession"], "rowId": row["rowId"], "originalEventId": original_id,
                          "invalidatedEventId": target["eventId"], "action": "INDIVIDUAL_ROW_UPDATED",
                          "availableAt": when, "mode": mode})
    return {"counts": dict(receipt), "rowAudit": audit,
            "wholeFilingReplacement": False, "unrelatedOriginalRowsPreserved": True}


_WORKER_CALENDAR = None


def normalize_task(source):
    global _WORKER_CALENDAR
    if _WORKER_CALENDAR is None:
        _WORKER_CALENDAR = xc.get_calendar("XNYS", start="2013-01-01", end="2027-12-31")
    path = Path(source["privatePath"])
    if sha(path.read_bytes()) != source["sha256"]:
        raise ValueError("OFFICIAL_QUARTER_HASH_MISMATCH:" + source["quarter"])
    return normalize_quarter(path, source["quarter"], _WORKER_CALENDAR)


def normalize(private, inputs, out, workers=3):
    manifest = json.loads((inputs / "source-manifest.json").read_text())
    calendar = xc.get_calendar("XNYS", start="2013-01-01", end="2027-12-31")
    events, quarters, seen = [], [], set()
    filings = sqlite3.connect(private / "filing-metadata.sqlite")
    filings.execute("CREATE TABLE IF NOT EXISTS filings (accession TEXT PRIMARY KEY, issuerCIK TEXT, filingDate TEXT, documentType TEXT, originalSubmissionDate TEXT, ownerCIKs TEXT)")
    filings.execute("CREATE INDEX IF NOT EXISTS filing_family ON filings(issuerCIK,ownerCIKs,filingDate,documentType)")
    filings.execute("CREATE TABLE IF NOT EXISTS transactions (accession TEXT,rowId TEXT,transDate TEXT,title TEXT,qty TEXT,price TEXT,code TEXT,acquired TEXT,notes TEXT,PRIMARY KEY(accession,rowId))")
    filings.execute("CREATE INDEX IF NOT EXISTS transaction_accession ON transactions(accession)")
    # This database is derived from the selected archives. A narrower rerun
    # may not link amendments through an earlier run's unselected files.
    filings.execute("DELETE FROM transactions")
    filings.execute("DELETE FROM filings")
    duplicate = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for source, (rows, meta, stats, raw_rows) in zip(manifest["quarters"], pool.map(normalize_task, manifest["quarters"]), strict=True):
            for row in rows:
                if row["eventId"] in seen:
                    duplicate += 1
                    continue
                seen.add(row["eventId"])
                events.append(row)
            filings.executemany("INSERT OR REPLACE INTO filings VALUES (?,?,?,?,?,?)", [
                (f["accession"], f["issuerCIK"], f["filingDate"], f["documentType"], f["originalSubmissionDate"], json.dumps(f["ownerCIKs"])) for f in meta])
            filings.executemany("INSERT OR REPLACE INTO transactions VALUES (?,?,?,?,?,?,?,?,?)", [
                tuple(r[k] for k in ("accession","rowId","transDate","title","qty","price","code","acquired","notes")) for r in raw_rows])
            filings.commit()
            quarters.append(stats)
            print("SEC quarter normalized", source["quarter"], len(rows), flush=True)
    amendment_receipt = apply_amendments(events, filings, calendar)
    frame = pd.DataFrame(events).sort_values(["availableAt", "issuerCIK", "accession", "transactionRowId"])
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "events.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    spans = []
    for source in manifest["quarters"]:
        year, quarter = int(source["quarter"][:4]), int(source["quarter"][-1])
        first = date(year, 3*(quarter-1)+1, 1)
        last = (pd.Timestamp(first) + pd.offsets.QuarterEnd()).date()
        # The final business-day cutoff is not covered without the next release.
        through = last if f"{year + (quarter==4)}q{quarter%4+1}" in {q["quarter"] for q in manifest["quarters"]} else (pd.Timestamp(last) - pd.Timedelta(days=1)).date()
        spans.append({"from": first.isoformat(), "through": through.isoformat()})
    merged = []
    for span in sorted(spans, key=lambda s: s["from"]):
        if merged and pd.Timestamp(span["from"]) <= pd.Timestamp(merged[-1]["through"]) + pd.Timedelta(days=1):
            merged[-1]["through"] = max(merged[-1]["through"], span["through"])
        else:
            merged.append(span)
    coverage = {"schema": "US_FORM4_PUBLIC_BUYS_EVENTS_V1", "source": "SEC_OFFICIAL_QUARTERLY_FORM345",
        "coverageIntervals": merged, "quarterReceipts": manifest["quarters"], "sourceGaps": manifest["errors"],
        "quarterClassificationCounts": quarters, "statusCounts": frame["status"].value_counts().to_dict(),
        "events": len(frame), "issuerCIKs": int(frame["issuerCIK"].nunique()),
        "potentialBuyAccessions": int(frame["accession"].nunique()), "exactDuplicateSourceRowsRemoved": duplicate,
        "amendments": amendment_receipt, "timeBasis": "DATE_ONLY_NEXT_XNYS_SESSION_ACTUAL_CLOSE",
        "availabilityEqualityAtDecisionCloseAllowed": True,
        "filingDateNotTransactionDate": True, "individualRawDocumentsAllVerified": False,
        "bulkFootnotesAreOfficialAsFiledExtract": True,
        "noPCodeOnlyConfirmation": True, "jointOwnersDoNotMultiplyTransactions": True,
        "unknownPBlocksCleanControls": True, "outcomesRead": 0,
        "sourceVintageCaveat": "Current official extracts are not contemporaneously captured quarterly vintages; SEC reports historical reprocessing. Original filings, amendments and their own publication dates are preserved rather than latest-only backfilled.",
        "eventsFileSha256": sha((out / "events.csv.gz").read_bytes())}
    save_json(out / "events-coverage.json", coverage)
    filings.close()


def refresh_amendments(private, out):
    """Rebuild only amendment state from retained original rows; no new source fetch."""
    frame = pd.read_csv(out / "events.csv.gz", dtype=str, keep_default_na=False)
    events = frame.to_dict("records")
    connection = sqlite3.connect(private / "filing-metadata.sqlite")
    connection.row_factory = sqlite3.Row
    for e in events:
        e["invalidatedAt"] = ""
        e["isAmendment"] = str(e["isAmendment"]).lower() == "true"
        for key in ("duplicateOfEventId", "firstKnownAt", "originalEventId"):
            e.pop(key, None)
        if not e["isAmendment"]:
            continue
        row = connection.execute("SELECT * FROM transactions WHERE accession=? AND rowId=?", (e["accession"], e["transactionRowId"])).fetchone()
        if row is None:
            raise ValueError("AMENDMENT_RAW_ROW_NOT_RETAINED:" + e["eventId"])
        transaction = {"TRANS_CODE": row["code"], "TRANS_ACQUIRED_DISP_CD": row["acquired"],
                       "SECURITY_TITLE": row["title"], "TRANS_SHARES": row["qty"], "TRANS_PRICEPERSHARE": row["price"]}
        e["status"], e["reason"] = classify(transaction, row["notes"], json.loads(e["ownerRoles"]))
        if json.loads(e["unresolvedFootnoteIds"]) and e["status"] == "CONFIRMED_OPEN_MARKET":
            e["status"], e["reason"] = "INDETERMINATE_P", "TRANSACTION_FOOTNOTE_REFERENCE_MISSING"
        e["rawClassificationStatus"], e["rawClassificationReason"] = e["status"], e["reason"]
        e["amendmentOf"], e["amendmentLinkStatus"] = "", "UNRESOLVED"
    calendar = xc.get_calendar("XNYS", start="2013-01-01", end="2027-12-31")
    amendment = apply_amendments(events, connection, calendar)
    connection.close()
    frame = pd.DataFrame(events).sort_values(["availableAt", "issuerCIK", "accession", "transactionRowId"])
    frame.to_csv(out / "events.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    coverage = json.loads((out / "events-coverage.json").read_text())
    coverage.update(amendments=amendment, statusCounts=frame["status"].value_counts().to_dict(),
                    eventsFileSha256=sha((out / "events.csv.gz").read_bytes()),
                    amendmentFinalization="ECONOMIC_ROW_ONLY_WITH_FIRST_KNOWN_TIME_PRESERVED")
    save_json(out / "events-coverage.json", coverage)


def parse_original_sgml(body):
    text = body.decode("utf-8", "replace")
    acceptance = re.search(r"<ACCEPTANCE-DATETIME>(\d{14})", text)
    accepted = datetime.strptime(acceptance.group(1), "%Y%m%d%H%M%S").replace(tzinfo=NY).astimezone(UTC).isoformat() if acceptance else None
    xml = re.search(r"(<ownershipDocument\b.*?</ownershipDocument>)", text, re.S)
    if xml is None:
        raise ValueError("ORIGINAL_OWNERSHIP_XML_ABSENT")
    root = ET.fromstring(xml.group(1))
    notes = {n.attrib["id"]: " ".join(n.itertext()) for n in root.findall(".//footnotes/footnote")}
    transactions = []
    for n in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
        refs = sorted({f.attrib["id"] for f in n.findall(".//footnoteId")})
        transactions.append({"code": n.findtext("transactionCoding/transactionCode"),
            "transactionDate": n.findtext("transactionDate/value"),
            "securityTitle": n.findtext("securityTitle/value"),
            "quantity": n.findtext("transactionAmounts/transactionShares/value"),
            "price": n.findtext("transactionAmounts/transactionPricePerShare/value"),
            "acquiredDisposed": n.findtext("transactionAmounts/transactionAcquiredDisposedCode/value"),
            "footnoteIds": refs, "footnotes": "\n".join(notes.get(r, "") for r in refs)})
    return {"acceptedAt": accepted, "acceptedAtBasis": "EDGAR_SEC_HEADER_ACCEPTANCE_NOT_DISSEMINATION",
            "issuerCIK": normalized_cik(root.findtext("issuer/issuerCik")),
            "documentType": root.findtext("documentType"), "transactions": transactions}


def amounts_match(original, bulk, tolerance):
    left, right = positive_number(original), positive_number(bulk)
    return left is not None and right is not None and abs(left-right) <= tolerance


def crosscheck_originals(private, out, per_year=2):
    frame = pd.read_csv(out / "events.csv.gz", dtype=str, keep_default_na=False)
    frame["_year"] = frame["filingDate"].str[:4]
    selected = []
    for _, group in frame.groupby("_year", sort=True):
        for mask in (group["status"] == "CONFIRMED_OPEN_MARKET", group["isAmendment"] == "True"):
            selected.extend(group[mask].sort_values("accession").drop_duplicates("accession").head(per_year).to_dict("records"))
    receipts = []
    for row in selected:
        path = private / "originals" / (row["accession"] + ".txt")
        try:
            receipt = capture(row["sourceURL"], path, cap=4*1024*1024)
            original = parse_original_sgml(path.read_bytes())
            # Older SEC quarterly exports round some fields to two decimals
            # while the original XML retains greater precision.
            same_trade = [t for t in original["transactions"] if t["code"] == row["transactionCode"]
                          and t["transactionDate"] == row["transactionDate"]
                          and t["acquiredDisposed"] == row["acquiredDisposed"]]
            matches = [t for t in same_trade
                       if amounts_match(t["quantity"], row["quantity"], Decimal("0.005"))
                       and amounts_match(t["price"], row["price"], Decimal("0.005"))]
            exact = [t for t in matches if positive_number(t["quantity"]) == positive_number(row["quantity"])
                     and positive_number(t["price"]) == positive_number(row["price"])]
            original_open = (len(matches) == 1 and bool(OPEN.search(matches[0]["footnotes"]))
                             and not any(p.search(matches[0]["footnotes"]) for p in (PRIVATE, PLAN, NEGATED_OPEN)))
            receipts.append({"accession": row["accession"], "issuerCIK": row["issuerCIK"],
                "bulkStatus": row["status"], "source": receipt, "original": original,
                "uniqueEconomicRowMatch": len(matches) == 1,
                "uniqueExactAmountMatch": len(exact) == 1,
                "openMarketFootnoteConfirmedInOriginal": original_open,
                "bulkNormalizedAmounts": {"quantity": row["quantity"], "price": row["price"]},
                "matchedFootnoteSha256": sha(matches[0]["footnotes"].encode()) if len(matches) == 1 else None,
                "bulkFootnoteSha256": row["sourceFootnotesSha256"],
                "acceptanceNotUsedToAdvanceDefaultAvailability": True})
        except (ValueError, OSError, ET.ParseError) as error:
            receipts.append({"accession": row["accession"], "sourceURL": row["sourceURL"], "state": "ORIGINAL_CROSSCHECK_UNAVAILABLE", "reason": str(error)})
    save_json(out / "events-original-crosschecks.json", {
        "selection": "First accession(s) by filing year, separately confirmed open-market and amendments; source-only, not chosen by a return.",
        "amountToleranceForOfficialBulkRounding": "0.005 in price and quantity",
        "defaultAvailabilityUnchanged": True, "receipts": receipts, "outcomesRead": 0})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=HERE / "inputs/US")
    parser.add_argument("--out", type=Path, default=HERE / "results/US")
    parser.add_argument("--stage", choices=("all", "acquire", "normalize", "amend", "crosscheck"), default="all")
    parser.add_argument("--first-quarter", default="2014q1")
    parser.add_argument("--last-quarter", default="2026q3")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.stage in ("all", "acquire"):
        acquire(args.private, args.inputs, args.first_quarter, args.last_quarter)
    if args.stage in ("all", "normalize"):
        normalize(args.private, args.inputs, args.out, args.workers)
    if args.stage == "amend":
        refresh_amendments(args.private, args.out)
    if args.stage in ("all", "crosscheck"):
        crosscheck_originals(args.private, args.out)


if __name__ == "__main__":
    main()
