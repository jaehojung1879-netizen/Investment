"""Offline admission of SEC 13F quarterly flat files (candidate only).

No network, Git writes, live cache publication, or market signals.
The caller supplies original SEC ZIPs with independently recorded SHA-256 and
official URLs. A hash verifies byte identity, not the authenticity of a URL.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from pipeline import institutional_13f as f13

URL = re.compile(
    r"https://www\.sec\.gov/files/datastandardsinnovation/data/form-13f-data-sets/"
    r"(\d{2}[a-z]{3}\d{4})-(\d{2}[a-z]{3}\d{4})_form13f\.zip"
)
ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
TABLES = {
    "SUBMISSION": {"ACCESSION_NUMBER", "CIK", "FILING_DATE", "SUBMISSIONTYPE", "PERIODOFREPORT"},
    "COVERPAGE": {"ACCESSION_NUMBER", "REPORTCALENDARORQUARTER", "AMENDMENTNO", "AMENDMENTTYPE", "REPORTTYPE"},
    "SUMMARYPAGE": {"ACCESSION_NUMBER", "TABLEENTRYTOTAL", "TABLEVALUETOTAL", "ISCONFIDENTIALOMITTED"},
    "INFOTABLE": {"ACCESSION_NUMBER", "INFOTABLE_SK", "NAMEOFISSUER", "TITLEOFCLASS",
                  "CUSIP", "VALUE", "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL"},
}
MAX_MEMBER_BYTES = 2_000_000_000


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _date(value):
    return datetime.strptime(value, "%d-%b-%Y").date()


def _num(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
        raise ValueError("INVALID_UNSIGNED_INTEGER")
    return int(value)


def _read_table(z, name):
    members = [m for m in z.infolist() if m.filename.upper() == name + ".TSV"]
    if len(members) != 1 or members[0].file_size > MAX_MEMBER_BYTES:
        raise ValueError("INVALID_TABLE_MEMBER:" + name)
    with z.open(members[0]) as binary, io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text:
        reader = csv.DictReader(text, delimiter="\t")
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("INVALID_HEADER:" + name)
        if not TABLES[name] <= set(reader.fieldnames):
            raise ValueError("MISSING_COLUMNS:" + name)
        for row in reader:
            if None in row or any(row[k] is None for k in TABLES[name]):
                raise ValueError("MALFORMED_ROW:" + name)
            yield row


def _unique(rows, wanted):
    out = {}
    for row in rows:
        key = row["ACCESSION_NUMBER"]
        if key in wanted:
            if key in out:
                raise ValueError("DUPLICATE_ACCESSION:" + key)
            out[key] = row
    return out


def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("OFFSET_AWARE_RECEIPT_TIME_REQUIRED")
    return value.astimezone(timezone.utc)


def _deadline(report):
    # The existing dashboard uses the same weekend and Washington's
    # Birthday adjustment for normal 13F filing deadlines.
    deadline = report + timedelta(days=45)
    while deadline.weekday() >= 5 or (
        deadline.month == 2 and deadline.weekday() == 0 and 15 <= deadline.day <= 21
    ):
        deadline += timedelta(days=1)
    return deadline


def load_archive(path, source_url, sha256, ciks, *, retrieved_at, as_of):
    match = URL.fullmatch(source_url)
    if not match or not re.fullmatch(r"[0-9a-f]{64}", sha256) or digest(path) != sha256:
        raise ValueError("ARCHIVE_PROVENANCE_MISMATCH")
    first, last = [datetime.strptime(x, "%d%b%Y").date() for x in match.groups()]
    if first < date(2023, 1, 3) or first > last:
        raise ValueError("UNSUPPORTED_ARCHIVE_PERIOD")
    received, clock = _utc(retrieved_at), _utc(as_of)
    # A URL window is not an SEC acceptance-time census. Reject future
    # receipts and windows that have not even ended in New York.
    if received > clock or received.astimezone(ZoneInfo("America/New_York")).date() <= last:
        raise ValueError("ARCHIVE_CLOCK_INVALID")
    filings = {}
    with ZipFile(path) as z:
        for row in _read_table(z, "SUBMISSION"):
            if not row["CIK"].isdigit() or int(row["CIK"]) not in ciks:
                continue
            accession = row["ACCESSION_NUMBER"]
            if not ACCESSION.fullmatch(accession) or accession in filings:
                raise ValueError("INVALID_ACCESSION")
            report, filed = _date(row["PERIODOFREPORT"]), _date(row["FILING_DATE"])
            if (
                not first <= filed <= last or report > filed
                or report.month not in (3, 6, 9, 12)
                or report.day != calendar.monthrange(report.year, report.month)[1]
            ):
                raise ValueError("INVALID_FILING_CLOCK")
            filings[accession] = {**row, "report": report, "filed": filed, "rows": []}
        wanted = set(filings)
        cover = _unique(_read_table(z, "COVERPAGE"), wanted)
        summary = _unique(_read_table(z, "SUMMARYPAGE"), wanted)
        seen = set()
        for row in _read_table(z, "INFOTABLE"):
            acc = row["ACCESSION_NUMBER"]
            if acc not in wanted:
                continue
            key = (acc, _num(row["INFOTABLE_SK"]))
            if key in seen:
                raise ValueError("DUPLICATE_POSITION_ROW")
            seen.add(key)
            if (
                not row["NAMEOFISSUER"].strip() or not row["TITLEOFCLASS"].strip()
                or not re.fullmatch(r"[A-Z0-9*@#]{9}", row["CUSIP"])
                or row["SSHPRNAMTTYPE"] not in ("SH", "PRN")
                or row["PUTCALL"].upper() not in ("", "PUT", "CALL")
            ):
                raise ValueError("INVALID_POSITION")
            filings[acc]["rows"].append({
                "issuer": row["NAMEOFISSUER"], "titleClass": row["TITLEOFCLASS"],
                "cusip": row["CUSIP"], "valueUsd": _num(row["VALUE"]),
                "shares": _num(row["SSHPRNAMT"]), "shareType": row["SSHPRNAMTTYPE"],
                "putCall": row["PUTCALL"].upper() or None,
            })
        for acc, filing in filings.items():
            if filing["SUBMISSIONTYPE"] not in ("13F-HR", "13F-HR/A"):
                continue  # notices are retained as such, not empty holdings
            if acc not in cover or acc not in summary:
                raise ValueError("MISSING_COVER_OR_SUMMARY:" + acc)
            c, s = cover[acc], summary[acc]
            if _date(c["REPORTCALENDARORQUARTER"]) != filing["report"]:
                raise ValueError("COVER_REPORT_MISMATCH")
            rows = filing["rows"]
            if not rows or len(rows) != _num(s["TABLEENTRYTOTAL"]):
                raise ValueError("ENTRY_TOTAL_MISMATCH")
            if sum(x["valueUsd"] for x in rows) != _num(s["TABLEVALUETOTAL"]):
                raise ValueError("VALUE_TOTAL_MISMATCH")
            filing["amendment"] = c["AMENDMENTTYPE"].upper()
            filing["number"] = _num(c["AMENDMENTNO"]) if c["AMENDMENTNO"] else 0
            filing["reportType"] = c["REPORTTYPE"].strip().upper()
            if filing["reportType"] not in ("13F HOLDINGS REPORT", "13F COMBINATION REPORT"):
                raise ValueError("HOLDINGS_REPORT_TYPE_MISMATCH")
            omitted = s["ISCONFIDENTIALOMITTED"].strip().upper()
            filing["confidentialOmitted"] = (
                True if omitted == "Y" else False if omitted == "N" else None
            )
    return first, last, filings


def resolve_chain(filings):
    if not filings:
        return None
    if any(f["SUBMISSIONTYPE"] not in ("13F-HR", "13F-HR/A") for f in filings):
        raise ValueError("NOTICE_OR_MIXED_REPORT")
    chain = sorted(filings, key=lambda f: f["number"])
    rows = []
    last_date = None
    for n, filing in enumerate(chain):
        if filing["number"] != n or (last_date and filing["filed"] < last_date):
            raise ValueError("INCOMPLETE_OR_UNORDERED_AMENDMENTS")
        if n == 0 and filing["SUBMISSIONTYPE"] == "13F-HR" and not filing["amendment"]:
            rows = list(filing["rows"])
        elif n > 0 and filing["SUBMISSIONTYPE"] == "13F-HR/A":
            if filing["amendment"] == "RESTATEMENT":
                rows = list(filing["rows"])
            elif filing["amendment"] == "NEW HOLDINGS":
                rows.extend(filing["rows"])
            else:
                raise ValueError("UNKNOWN_AMENDMENT")
        else:
            raise ValueError("INVALID_AMENDMENT_CHAIN")
        last_date = filing["filed"]
    scope = sorted({
        reason
        for filing in chain
        for reason, condition in (
            ("COMBINATION_REPORT", filing.get("reportType") != "13F HOLDINGS REPORT"),
            ("CONFIDENTIAL_SCOPE_NOT_CONFIRMED", filing.get("confidentialOmitted") is not False),
        )
        if condition
    })
    return chain[-1], f13._aggregate(rows), [f["ACCESSION_NUMBER"] for f in chain], scope


def candidate(manifest, registry, target, *, as_of):
    """Two consecutive reported quarters; no inference beyond ZIP coverage."""
    report = date.fromisoformat(target)
    previous = date.fromisoformat(f13.prior_quarter(target))
    if report != date.fromisoformat(f13.prior_quarter((report + timedelta(days=1)).isoformat())):
        raise ValueError("NOT_QUARTER_END")
    clock = _utc(as_of)
    if clock.astimezone(ZoneInfo("America/New_York")).date() <= _deadline(report):
        raise ValueError("TARGET_DEADLINE_NOT_PASSED")
    if len({m["id"] for m in registry}) != len(registry) or len({int(m["cik"]) for m in registry}) != len(registry):
        raise ValueError("DUPLICATE_MANAGER_REGISTRY")
    ciks = {int(m["cik"]) for m in registry}
    archives, seen = [], {}
    for item in manifest:
        first, last, filings = load_archive(
            item["path"], item["url"], item["sha256"], ciks,
            retrieved_at=item.get("retrievedAtUtc"), as_of=clock,
        )
        if set(seen) & set(filings):
            raise ValueError("DUPLICATE_ACCESSION_ACROSS_ARCHIVES")
        seen.update(filings)
        archives.append((first, last))
    archives.sort()
    if not archives or archives[0][0] > previous or archives[-1][1] < _deadline(report):
        raise ValueError("INSUFFICIENT_ARCHIVE_COVERAGE")
    if any(a[1] + timedelta(days=1) != b[0] for a, b in zip(archives, archives[1:])):
        raise ValueError("NONCONTIGUOUS_ARCHIVE_COVERAGE")
    managers, refused = {}, {}
    for manager in registry:
        key = manager["id"]
        filings = [f for f in seen.values() if int(f["CIK"]) == int(manager["cik"])]
        try:
            cur = resolve_chain([f for f in filings if f["report"] == report])
            if cur is None:
                raise ValueError("NO_TARGET_FILING_IN_ARCHIVES")
            prev = resolve_chain([f for f in filings if f["report"] == previous])
            latest, current, chain, scope = cur
            comparison_scope = sorted(set(scope) | set(prev[3] if prev else ["PREVIOUS_REPORT_MISSING"]))
            total = sum(row["valueUsd"] for row in current)
            for row in current:
                row["portfolioWeightPct"] = round(100 * row["valueUsd"] / total, 2) if total else 0.0
            acc = latest["ACCESSION_NUMBER"]
            managers[key] = {
                **manager, "status": "CANDIDATE_ONLY", "sourceMode": "SEC_BULK_AS_FILED",
                "reportDate": target, "filingDate": latest["filed"].isoformat(),
                "previousReportDate": previous.isoformat() if prev else None,
                "accessionNumber": acc,
                "filingUrl": f"{f13.SEC_ARCHIVES}/{int(manager['cik'])}/{acc.replace('-', '')}/{acc}.txt",
                "totalValueUsd": total, "positionCount": len(current),
                "top5WeightPct": round(sum(x["portfolioWeightPct"] for x in current[:5]), 1),
                "topHoldings": current[:10],
                "changes": f13._changes(current, prev[1]) if prev and not comparison_scope else None,
                "comparisonStatus": "DISCLOSED_QUANTITIES_ONLY" if not comparison_scope else "WITHHELD_SCOPE_UNCERTAIN",
                "scopeWarnings": comparison_scope,
                "sourceAccessions": chain, "previousSourceAccessions": prev[2] if prev else [],
                "archiveCoverageThrough": archives[-1][1].isoformat(),
            }
        except ValueError as exc:
            refused[key] = str(exc)
    return {
        "schema": "SEC_13F_BULK_CANDIDATE_V1", "productionEffect": "NONE",
        "source": "SEC EDGAR Form 13F Data Sets", "reportDate": target,
        "coverageThrough": archives[-1][1].isoformat(),
        "coverageBasis": "ARCHIVE_FILENAME_WINDOWS_NOT_ACCEPTANCE_CENSUS",
        "asOfUtc": clock.isoformat(),
        "sources": [{k: item[k] for k in ("url", "sha256", "retrievedAtUtc")} for item in manifest],
        "candidateManagers": managers, "refusedManagers": refused,
        "publicationAuthorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.is_relative_to(f13.REPO_ROOT.resolve()) or out.exists():
        raise ValueError("OUTPUT_MUST_BE_NEW_FILE_OUTSIDE_REPOSITORY")
    registry = json.loads(f13.REGISTRY_PATH.read_text(encoding="utf-8"))
    result = candidate(
        json.loads(args.manifest.read_text(encoding="utf-8")), registry, args.report,
        as_of=datetime.now(timezone.utc),
    )
    with out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    print("CANDIDATE_ONLY", len(result["candidateManagers"]), "refused", len(result["refusedManagers"]))
    return 0 if result["candidateManagers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
