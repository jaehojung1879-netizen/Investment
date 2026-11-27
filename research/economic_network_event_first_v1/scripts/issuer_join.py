"""Join FDA Class I manufacturer names to pre-incident EDGAR registrants/exhibits."""

import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, timedelta
from hashlib import file_digest
from pathlib import Path

from lxml import html

raw = Path("raw/edgar")
out = Path("build")


def normalized(value):
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    )
    words = re.findall(r"[a-z0-9]+", value)
    suffixes = {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "company",
        "co",
        "llc",
        "ltd",
        "limited",
        "ag",
        "lp",
        "plc",
    }
    while words and words[-1] in suffixes:
        words.pop()
    return " ".join(words)


def file_hash(path):
    with path.open("rb") as f:
        return file_digest(f, "sha256").hexdigest()


def write(name, rows):
    with (out / name).open("w", newline="", encoding="utf-8") as f:
        c = csv.DictWriter(f, fieldnames=list(rows[0]))
        c.writeheader()
        c.writerows(rows)


candidates = list(csv.DictReader((out / "fda_device_class_i.csv").open()))
referenced = {v for a in candidates for v in a["firm_keys"].split("|") if v}
filings = json.loads((raw / "manifest.json").read_text())
matched = defaultdict(list)
for tick, cik, form, filing_day, utc, period, acc, u, ex, registrant in filings:
    metadata = {
        "ticker": tick,
        "cik": cik,
        "form": form,
        "filing_date": filing_day,
        "sec_acceptance_utc": utc,
        "reporting_period": period,
        "accession": acc,
    }
    direct = normalized(registrant)
    if direct in referenced:
        path = raw / f"{tick}_{filing_day}_main.html"
        matched[direct].append(
            {
                **metadata,
                "name_in_filing": registrant,
                "match_basis": "EDGAR_REGISTRANT_EXACT",
                "filing_url": u,
                "source_sha256": file_hash(path),
            }
        )
    if not ex:
        continue
    path = raw / f"{tick}_{filing_day}_ex21.html"
    h = html.parse(str(path))
    heading = " ".join(h.xpath("//body//text()")[:80]).lower()
    if (
        "subsidiar" not in heading
        and "exhibit 21" not in heading
        and "exhibit 8" not in heading
    ):
        continue
    raw_names = []
    for element in h.xpath("//td|//li|//p[not(ancestor::td)]"):
        value = " ".join(element.text_content().split())
        if not 4 <= len(value) <= 140:
            continue
        key = normalized(value)
        if key in referenced:
            raw_names.append((key, value))
    if not raw_names:
        continue
    values = dict(raw_names)
    digest = file_hash(path)
    for key, value in values.items():
        matched[key].append(
            {
                **metadata,
                "name_in_filing": value,
                "match_basis": "EDGAR_SUBSIDIARY_EXACT",
                "filing_url": ex,
                "source_sha256": digest,
            }
        )

edges = []
for event in candidates:
    d = event["initiation_date"]
    end = (date.fromisoformat(d) - timedelta(days=550)).isoformat()
    for key in event["firm_keys"].split("|"):
        proposals = [
            r
            for r in matched.get(key, [])
            if end <= r["filing_date"] < d and r["sec_acceptance_utc"][:10] < d
        ]
        groups = {p["cik"] for p in proposals}
        if len(groups) != 1:
            continue
        best = max(
            proposals,
            key=lambda r: (
                r["filing_date"],
                r["match_basis"] == "EDGAR_REGISTRANT_EXACT",
            ),
        )
        edges.append(
            {
                "fda_event_id": event["fda_event_id"],
                "cluster_90d": event["cluster_90d"],
                "fda_initiation_date": d,
                "fda_first_observed": event["earliest_observed_fda_date"],
                "firm_key": key,
                "linked_510k_90d_before": event["linked_clearances_90d_before"],
                "linked_510k_same_name_90d_before": "|".join(
                    json.loads(event["same_firm_clearance_by_legal_name"]).get(key, [])
                ),
                "fda_device_record_url": event["fda_device_record_url"],
                **best,
            }
        )
assert edges
write("fda_issuer_exposure.csv", edges)
links = [e for e in edges if e["linked_510k_90d_before"]]
strict = [e for e in edges if e["linked_510k_same_name_90d_before"]]


def group(rows):
    return {
        "event_ids": len({x["fda_event_id"] for x in rows}),
        "clusters_90d": len({x["cluster_90d"] for x in rows}),
        "issuers": len({x["cik"] for x in rows}),
    }


summary = {
    "filing_targets": len(filings),
    "registrant_names_read": sum(bool(x[-1]) for x in filings),
    "exhibits_acquired": sum(bool(x[-2]) for x in filings),
    "distinct_name_keys_in_edgar": len(matched),
    "matched_event_corporate_rows": len(edges),
    "pre_event_public_issuer": group(edges),
    "public_issuer_and_linked_product_clearance": group(links),
    "public_issuer_and_same_legal_name_product_clearance": group(strict),
    "assurance_scope": "Documented registrant or subsidiary exposure. No FDA historical public capture, security eligibility or causal independence is assumed.",
}
(out / "issuer_metrics.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
