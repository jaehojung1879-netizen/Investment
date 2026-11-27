import json
from hashlib import file_digest
from pathlib import Path

RAW = Path("raw")
OUT = Path("build")
rows = []


def add(filename, url, **fields):
    name = Path(filename)
    p = RAW / name
    if "filing_role" in fields:
        record = {"url": url, **fields}
    else:
        record = {"archive_path": str(name), "url": url, **fields}
    if not p.is_file():
        record["acquired"] = False
    else:
        with p.open("rb") as f:
            digest = file_digest(f, "sha256").hexdigest()
        record.update(acquired=True, bytes=p.stat().st_size, sha256=digest)
    rows.append(record)


m = json.loads((RAW / "fda_download.json").read_text())
add(
    "fda_download.json",
    "https://api.fda.gov/download.json",
    index_last_updated=m["meta"]["last_updated"],
)
for name, url, *_ in json.loads((RAW / "fda_acquire_config.json").read_text()):
    _, dataset, kind, _ = name.split("_")
    r = m["results"][dataset][kind]
    add(
        name,
        url,
        export_date=r["export_date"],
        provider_dataset_record_count=r["total_records"],
    )
for k, u in {
    "fda_license.html": "https://open.fda.gov/license/",
    "fda_dates.html": "https://open.fda.gov/apis/device/enforcement/searchable-fields/",
    "fda_device_enf.json": "https://api.fda.gov/device/enforcement.json?limit=2",
    "fda_device_recall.json": "https://api.fda.gov/device/recall.json?limit=2",
    "fda_drug_short.json": "https://api.fda.gov/drug/shortages.json?limit=2",
    "fda_recalls.html": "https://www.fda.gov/medical-devices/medical-device-safety/medical-device-recalls-and-early-alerts",
    "fda_shortages.html": "https://www.fda.gov/medical-devices/medical-device-supply-chain-and-shortages/medical-device-shortages-list",
    "sec_master2024q4.idx": "https://www.sec.gov/Archives/edgar/full-index/2024/QTR4/master.idx",
    "oecd_terms.html": "https://www.oecd.org/en/about/terms-conditions.html",
    "bls_terms.html": "https://www.bls.gov/bls/linksite.htm",
}.items():
    add(k, u)
add(
    "sec_efts.json",
    "https://efts.sec.gov/LATEST/search-index?forms=8-K&startdt=2023-01-01&enddt=2025-12-31&q=%22production%20suspended%22",
    probe_status="HTTP_500_ERROR_BODY_NOT_SOURCE_DATA",
)
for config in ["official_urls.json", "extra_urls.json", "additional_case_sources.json"]:
    for k, u in json.loads((RAW / config).read_text()).items():
        ext = (
            ".json"
            if k.startswith("sec_submissions")
            else (".pdf" if u.endswith(".pdf") else ".html")
        )
        add(k + ext, u)
for tick, cik, form, day, utc, period, acc, u, ex, name in json.loads(
    (RAW / "edgar/manifest.json").read_text()
):
    add(
        f"edgar/{tick}_{day}_main.html",
        u,
        sec_acceptance_utc=utc,
        accession=acc,
        filing_role="primary",
    )
    if ex:
        add(
            f"edgar/{tick}_{day}_ex21.html",
            ex,
            sec_acceptance_utc=utc,
            accession=acc,
            filing_role="subsidiaries",
        )
for code in ("DOE", "HHS", "NASA"):
    response = json.loads((RAW / f"usa_{code}_bulk_response.json").read_text())
    kwargs = {
        "request_body": json.loads((RAW / f"usa_{code}_bulk_request.json").read_text())
    }
    add(
        f"usa_{code}_bulk_response.json",
        "https://api.usaspending.gov/api/v2/bulk_download/awards/",
        method="POST",
        **kwargs,
    )
    add(
        f"usa_{code}_bulk_status.json",
        response["status_url"],
        download_name=response["file_name"],
    )
    add(
        f"usa_{code}_bulk.zip",
        response["file_url"],
        download_name=response["file_name"],
        **kwargs,
    )
for path, url, req in [
    (
        "usa_example_tx.json",
        "https://api.usaspending.gov/api/v2/transactions/",
        "usa_tx_request.json",
    ),
    (
        "usa_search_nasa.json",
        "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        "usa_search_request.json",
    ),
]:
    add(path, url, method="POST", request_body=json.loads((RAW / req).read_text()))
add(
    "usa_award_example.json",
    "https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0001917C0015_9700_-NONE-_-NONE-/",
)
if len(
    {(r.get("archive_path"), r.get("accession"), r.get("filing_role")) for r in rows}
) != len(rows):
    raise ValueError("duplicate paths")
(OUT / "source_manifest.json").write_text(
    json.dumps(
        {
            "source_observation_date_kst": "2026-11-27",
            "raw_bundles_republished": False,
            "sources": rows,
        },
        indent=2,
    )
    + "\n"
)
print("Records", len(rows), "local responses", sum(r["acquired"] for r in rows))
