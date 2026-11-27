"""Validate public source-only files without external calls or outcome inputs."""

import csv
import gzip
import json
from collections import Counter
from decimal import Decimal
from hashlib import file_digest
from pathlib import Path
from zipfile import ZipFile

here = Path(__file__).resolve().parent.parent
data = here / "data"


def read_csv(name):
    path = data / name
    reader = gzip.open if path.suffix == ".gz" else open
    with reader(path, "rt", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def load_json(name):
    return json.loads((data / name).read_text())


archive = here / "s1" / "Investment-network-pilot.zip"
with archive.open("rb") as stream:
    assert (
        file_digest(stream, "sha256").hexdigest()
        == "1d1c725f7b70602333bbd73635d4ffe2e022f00d98ff6d16629344776898a7d8"
    )
with ZipFile(archive) as z:
    assert len(z.namelist()) == 36 and z.testzip() is None
    assert z.read("REPORT-ko.md") == (here / "s1" / "REPORT-ko.md").read_bytes()

events = read_csv("fda_event_census.csv.gz")
keys = {(r["domain"], r["fda_event_id"]) for r in events}
assert len(keys) == len(events) == 12056
assert Counter(r["domain"] for r in events) == {
    "device": 6464,
    "drug": 2251,
    "food": 3341,
}
assert all("2019-01-01" <= r["initiation_date"] <= "2025-12-31" for r in events)
products = read_csv("fda_product_crosswalk.csv.gz")
assert len(products) == 37641
assert len({(r["domain"], r["event_id"], r["recall_number"]) for r in products}) == len(
    products
)
assert {(r["domain"], r["event_id"]) for r in products} == keys

class_i = read_csv("fda_device_class_i.csv")
class_i_by_id = {e["fda_event_id"]: e for e in class_i}
assert len(class_i_by_id) == len(class_i) == 561
assert [len({r[f"cluster_{days}d"] for r in class_i}) for days in (30, 90, 180)] == [
    540,
    521,
    494,
]
links = read_csv("fda_issuer_exposure.csv")
assert len(links) == 115
assert all(
    r["filing_date"] < r["fda_initiation_date"]
    and r["sec_acceptance_utc"][:10] < r["fda_initiation_date"]
    for r in links
)
assert all(
    r["fda_event_id"] in class_i_by_id
    and r["cluster_90d"] == class_i_by_id[r["fda_event_id"]]["cluster_90d"]
    for r in links
)
both = [r for r in links if r["linked_510k_90d_before"]]
same = [r for r in links if r["linked_510k_same_name_90d_before"]]
assert len({r["cluster_90d"] for r in both}) == 66
assert len({r["cluster_90d"] for r in same}) == 45
assert all(
    r["linked_510k_same_name_90d_before"].split("|")
    == json.loads(
        class_i_by_id[r["fda_event_id"]]["same_firm_clearance_by_legal_name"]
    )[r["firm_key"]]
    for r in same
)
actions = read_csv("fda_action_cues.csv")
assert len(actions) == 561 and len({r["fda_event_id"] for r in actions}) == 561
focus = [r for r in actions if r["issuer_and_product_candidate"] == "True"]
assert {
    k: len({r["cluster_90d"] for r in focus if r[k] == "True"})
    for k in (
        "distribution_stop_wording",
        "return_or_quarantine_wording",
        "field_service_or_update_wording",
    )
} == {
    "distribution_stop_wording": 4,
    "return_or_quarantine_wording": 35,
    "field_service_or_update_wording": 12,
}

usa = read_csv("usa_oct2024_transactions.csv.gz")
assert len({r["contract_transaction_unique_key"] for r in usa}) == len(usa) == 4491
assert len({r["contract_award_unique_key"] for r in usa}) == 4115
assert all("2024-10-01" <= r["action_date"] <= "2024-10-31" for r in usa)
assert sum(Decimal(r["federal_action_obligation"]) < 0 for r in usa) == 616
assert sum(r["initial_report_date"][:10] < r["action_date"] for r in usa) == 2160
assert len(read_csv("usa_termination_candidates.csv")) == 6
assert len(read_csv("usa_example_award_history.csv")) == 207
assert "revenue" not in usa[0]
assert not (
    {"recipient_phone_number", "recipient_address_line_1", "transaction_description"}
    & usa[0].keys()
)

bls = read_csv("bls_event_first_91.csv")
assert len(bls) == len({r["campaign_id"] for r in bls}) == 91
assert sum(int(r["record_count"]) for r in bls) == 94
routes = read_csv("audited_shock_routes.csv")
assert len(routes) == len({r["common_root_id"] for r in routes}) == 8
assert (
    sum(
        r["path_grade"] == "VERIFIED_PRODUCT_CHANNEL" and r["novelty"] == "new"
        for r in routes
    )
    == 4
)
assert sum(r["novelty"] == "S1_overlap" for r in routes) == 1
assert len(read_csv("sec_event_sources.csv")) == 7
source = load_json("source_manifest.json")
assert len(source["sources"]) == len(
    {
        (r.get("archive_path"), r.get("accession"), r.get("filing_role"))
        for r in source["sources"]
    }
)
assert not source["raw_bundles_republished"]
assert all(
    len(r["sha256"]) == 64 and r["bytes"] > 0
    for r in source["sources"]
    if r["acquired"]
)
print(
    "S1 archive, 12,056 FDA IDs, 66 candidate clusters, 45 strict clusters, BLS, SEC, USAspending and action cues verified."
)
