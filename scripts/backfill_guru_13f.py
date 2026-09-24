"""Backfill the Guru 13F historical store, resumably, for the known managers.

ROUTE SELECTION. Tries the SEC bulk Form 13F dataset first when a
``--bulk-url`` is given (per ``scripts/probe_guru_13f_access.py``'s
measurement of whether that route is SERVED); on any failure, or when no
bulk URL is given, falls back automatically to the per-manager EDGAR
submissions API for the managers in ``data/institutional_managers.json`` —
the same CIKs ``pipeline.institutional_13f`` already resolved, reused here
rather than re-resolved.

RESUMABLE BY CONSTRUCTION, NOT BY A SEPARATE MANIFEST. A filing already in
the store is never re-downloaded: its own rows are reconstructed from what
is already on disk (``guru_13f_store.reconstruct_infotable_rows``) and fed
back into ``build_manager_rows`` alongside any newly-fetched filings, so a
manager's FULL row set is always recomputed in memory but the network is
only asked for filings this store has never seen. Because
``build_manager_rows`` is a pure forward-looking function of report-date
order, recomputing old rows this way reproduces them byte-for-byte, and
``guru_13f_store.write_holdings``'s id-dedup then writes nothing for them —
the store's own contents ARE the "already processed" index; a second file
tracking the same fact would just be a second place for it to drift from
the first.

THE BULK-DATASET PARSER IS BUILT, NOT EXERCISED. Its TSV column names come
from WebSearch-surfaced documentation of SEC's Form 13F structured data
sets, not from a byte-verified response — the same SEC-block-imposed
epistemic limit ``docs/alpha-information-inventory-v1-data-map.md`` §13
already states for Form 4's schema. It is validated here only against a
synthetic fixture (``tests/test_backfill_guru_13f.py``); a real run is what
would confirm or correct the column names, and ``--bulk-url`` is not the
default backfill path for that reason — see this task's own final report
for the current SERVED/BLOCKED verdict.

Usage:  python scripts/backfill_guru_13f.py [--start-date 2013-01-01]
        [--end-date YYYY-MM-DD] [--bulk-url URL] [--output report.json]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import guru_13f_store as STORE  # noqa: E402
from pipeline import institutional_13f as F13  # noqa: E402

DEFAULT_MANAGERS_REGISTRY = ROOT / "data" / "institutional_managers.json"
WANTED_FORMS = {"13F-HR", "13F-HR/A"}


# --------------------------------------------------------------------------- #
# Per-manager EDGAR submissions route
# --------------------------------------------------------------------------- #
def _filings_from_block(block: dict) -> list[dict]:
    keys = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument")
    count = min((len(block.get(k) or []) for k in keys), default=0)
    out = []
    for i in range(count):
        form = block["form"][i]
        if form not in WANTED_FORMS:
            continue
        row = {k: block[k][i] for k in keys}
        row["filingForm"] = form
        out.append(row)
    return out


def list_13f_filings(cik: str, fetch_json) -> list[dict]:
    """Every 13F-HR/13F-HR/A filing a manager has ever submitted — never
    truncated, never deduplicated by report date (that is
    ``institutional_13f._recent_13f_filings``'s job for a two-filing
    dashboard, not this store's). Follows the submissions API's own
    pagination (``filings.files``) so a manager with more than ~1,000 total
    SEC filings of any type is not silently cut off at the most recent page.
    """
    submissions = fetch_json(f"{F13.SEC_DATA}/submissions/CIK{cik}.json")
    filings = _filings_from_block((submissions.get("filings") or {}).get("recent") or {})
    for file_ref in ((submissions.get("filings") or {}).get("files") or []):
        name = file_ref.get("name")
        if not name:
            continue
        extra = fetch_json(f"{F13.SEC_DATA}/submissions/{name}")
        filings.extend(_filings_from_block(extra))

    seen: set[str] = set()
    unique: list[dict] = []
    for filing in sorted(filings, key=lambda f: (f["reportDate"], f["filingDate"], f["accessionNumber"])):
        if filing["accessionNumber"] in seen:
            continue
        seen.add(filing["accessionNumber"])
        unique.append(filing)
    return unique


# --------------------------------------------------------------------------- #
# Bulk dataset route (built as if access existed; see module docstring)
# --------------------------------------------------------------------------- #
def _normalize_bulk_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _read_tsv(archive: zipfile.ZipFile, name: str) -> list[dict]:
    with archive.open(name) as handle:
        text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
        return list(csv.DictReader(text, delimiter="\t"))


def parse_bulk_zip(raw: bytes, wanted_ciks: set[str]) -> dict[str, list[dict]]:
    """One quarterly bulk ZIP -> ``{managerCIK (zero-padded): [filing dicts]}``.

    ``wanted_ciks`` are zero-padded 10-digit CIKs, matching this store's own
    ``managerCIK`` convention; ``SUBMISSION.tsv``'s ``CIK`` column is a plain
    integer, so both sides are compared as plain integers.
    """
    archive = zipfile.ZipFile(io.BytesIO(raw))
    names = {name.upper(): name for name in archive.namelist()}
    sub_name, info_name = names.get("SUBMISSION.TSV"), names.get("INFOTABLE.TSV")
    if not sub_name or not info_name:
        raise ValueError("bulk 13F zip is missing SUBMISSION.tsv or INFOTABLE.tsv")

    wanted_plain = {str(int(cik)) for cik in wanted_ciks}
    accession_meta: dict[str, dict] = {}
    for row in _read_tsv(archive, sub_name):
        cik_plain = str(int(row.get("CIK") or -1))
        if cik_plain not in wanted_plain:
            continue
        form = (row.get("SUBMISSIONTYPE") or row.get("FORM") or "").strip()
        if form not in WANTED_FORMS:
            continue
        accession_meta[row["ACCESSION_NUMBER"]] = {
            "cikPlain": cik_plain, "filingForm": form,
            "filingDate": _normalize_bulk_date(row.get("FILING_DATE")),
            "reportDate": _normalize_bulk_date(row.get("PERIODOFREPORT")),
        }

    by_accession: dict[str, list[dict]] = {}
    for row in _read_tsv(archive, info_name):
        accession = row.get("ACCESSION_NUMBER")
        if accession not in accession_meta:
            continue
        by_accession.setdefault(accession, []).append({
            "issuer": row.get("NAMEOFISSUER"), "titleClass": row.get("TITLEOFCLASS") or "—",
            "cusip": row.get("CUSIP"), "valueUsd": round(float(row.get("VALUE") or 0)),
            "shares": round(float(row.get("SSHPRNAMT") or 0)),
            "shareType": row.get("SSHPRNAMTTYPE") or "SH",
            "putCall": (row.get("PUTCALL") or "").upper() or None,
        })

    out: dict[str, list[dict]] = {}
    for accession, meta in accession_meta.items():
        if not meta["filingDate"] or not meta["reportDate"]:
            continue
        cik10 = meta["cikPlain"].zfill(10)
        out.setdefault(cik10, []).append({
            "accessionNumber": accession, "filingDate": meta["filingDate"],
            "reportDate": meta["reportDate"], "filingForm": meta["filingForm"],
            "infoTableRows": by_accession.get(accession, []),
        })
    return out


def fetch_bulk_dataset_rows(bulk_url: str, wanted_ciks: set[str], fetch_bytes) -> dict[str, list[dict]]:
    raw = fetch_bytes(bulk_url)
    return parse_bulk_zip(raw, wanted_ciks)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_backfill(*, managers: list[dict], store_root: Path, start_date: str, end_date: str,
                 fetch_json, fetch_bytes, bulk_url: str | None,
                 sleep=time.sleep) -> dict:
    report: dict = {"bulkUrlUsed": bulk_url, "managers": {}}

    bulk_by_cik: dict[str, list[dict]] = {}
    if bulk_url:
        wanted = {m["cik"].zfill(10) for m in managers}
        try:
            bulk_by_cik = fetch_bulk_dataset_rows(bulk_url, wanted, fetch_bytes)
            report["bulkDatasetFilingsFound"] = sum(len(v) for v in bulk_by_cik.values())
        except Exception as exc:
            report["bulkDatasetError"] = f"{type(exc).__name__}: {exc}"

    existing_all = STORE.load_holdings(store_root)
    existing_by_manager: dict[str, list[dict]] = {}
    for row in existing_all:
        existing_by_manager.setdefault(row["managerCIK"], []).append(row)

    for manager in managers:
        cik = manager["cik"].zfill(10)
        manager_row = {**manager, "cik": cik}
        existing_rows = existing_by_manager.get(cik, [])
        existing_by_accession: dict[str, list[dict]] = {}
        for row in existing_rows:
            existing_by_accession.setdefault(row["accessionNumber"], []).append(row)

        try:
            filings_meta = list_13f_filings(cik, fetch_json)
        except Exception as exc:
            report["managers"][manager["id"]] = {"status": "ERROR",
                                                  "error": f"{type(exc).__name__}: {exc}"}
            continue

        filings_meta = [f for f in filings_meta if start_date <= f["reportDate"] <= end_date]
        bulk_rows_by_accession = {f["accessionNumber"]: f["infoTableRows"]
                                  for f in bulk_by_cik.get(cik, [])}

        filings_with_tables: list[dict] = []
        downloaded = reconstructed = from_bulk = failures = 0
        for filing in filings_meta:
            accession = filing["accessionNumber"]
            if accession in existing_by_accession:
                rows = STORE.reconstruct_infotable_rows(existing_by_accession[accession])
                reconstructed += 1
            elif accession in bulk_rows_by_accession:
                rows = bulk_rows_by_accession[accession]
                from_bulk += 1
            else:
                try:
                    table_url = F13._information_table_url(cik, filing, fetch_json)
                    rows = F13.parse_information_table(fetch_bytes(table_url))
                    downloaded += 1
                    sleep(0.12)
                except Exception as exc:
                    failures += 1
                    report.setdefault("warnings", []).append(
                        f"{manager['id']} {accession}: {type(exc).__name__}: {exc}")
                    continue
            filings_with_tables.append({**filing, "infoTableRows": rows})

        rows = STORE.build_manager_rows(manager_row, filings_with_tables)
        appended, skipped = STORE.write_holdings(store_root, rows)
        report["managers"][manager["id"]] = {
            "status": "OK", "filingsInRange": len(filings_meta),
            "filingsDownloaded": downloaded, "filingsReconstructedFromStore": reconstructed,
            "filingsFromBulkDataset": from_bulk, "filingsFailed": failures,
            "rowsAppended": appended, "rowsAlreadyStored": skipped,
        }

    STORE.write_manifest(store_root)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--managers-registry", default=str(DEFAULT_MANAGERS_REGISTRY))
    parser.add_argument("--store-root", default=str(STORE.STORE_ROOT))
    parser.add_argument("--start-date", default="2013-01-01")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--bulk-url", default=None,
                        help="omit to go straight to the per-manager EDGAR route")
    parser.add_argument("--output", default="guru-13f-backfill-report.json")
    parser.add_argument("--user-agent", default=None)
    args = parser.parse_args(argv)

    managers = json.loads(Path(args.managers_registry).read_text(encoding="utf-8"))
    end_date = args.end_date or datetime.now(timezone.utc).date().isoformat()

    contact = args.user_agent or os.environ.get("SEC_USER_AGENT") or F13.DEFAULT_USER_AGENT
    os.environ.setdefault("SEC_USER_AGENT", contact)

    def fetch_json(url: str) -> dict:
        return json.loads(F13._request(url).decode("utf-8"))

    report = run_backfill(managers=managers, store_root=Path(args.store_root),
                          start_date=args.start_date, end_date=end_date,
                          fetch_json=fetch_json, fetch_bytes=F13._request,
                          bulk_url=args.bulk_url)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
