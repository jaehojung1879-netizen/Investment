import csv
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from io import TextIOWrapper
from pathlib import Path
from statistics import median
from zipfile import ZipFile

raw = Path("raw")
out = Path("build")

fields = [
    "contract_transaction_unique_key",
    "contract_award_unique_key",
    "award_id_piid",
    "modification_number",
    "transaction_number",
    "action_date",
    "initial_report_date",
    "last_modified_date",
    "awarding_agency_name",
    "awarding_sub_agency_name",
    "recipient_uei",
    "recipient_name",
    "recipient_parent_uei",
    "recipient_parent_name",
    "action_type_code",
    "action_type",
    "product_or_service_code",
    "naics_code",
    "federal_action_obligation",
    "base_and_exercised_options_value",
    "base_and_all_options_value",
    "usaspending_permalink",
]

rows = []
for source in sorted(raw.glob("usa_*_bulk.zip")):
    agency = source.name.split("_")[1]
    with ZipFile(source) as z:
        for member in z.namelist():
            if not member.endswith(".csv"):
                continue
            with z.open(member) as f:
                r = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig", newline=""))
                assert all(k in r.fieldnames for k in fields), source
                for x in r:
                    assert "2024-10-01" <= x["action_date"] <= "2024-10-31", x[
                        "action_date"
                    ]
                    if (
                        x.get("organizational_type", "").strip()
                        in {"", "INDIVIDUAL", "SOLE PROPRIETORSHIP", "OTHER"}
                        or x.get("sole_proprietorship") == "t"
                    ):
                        x["recipient_name"] = ""
                        x["recipient_parent_name"] = ""
                        x["recipient_uei"] = ""
                        x["recipient_parent_uei"] = ""
                    rows.append({"agency_filter": agency, **{k: x[k] for k in fields}})

by = {}
for x in rows:
    k = x["contract_transaction_unique_key"]
    assert k
    if k in by and by[k] != x:
        raise ValueError(k)
    by[k] = x
rows.sort(
    key=lambda r: (
        r["agency_filter"],
        r["action_date"],
        r["contract_transaction_unique_key"],
    )
)


def emit(name, data):
    fields = list(data[0])
    with (out / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(data)


emit("usa_oct2024_transactions.csv", rows)
metrics = {}
for agency in sorted({r["agency_filter"] for r in rows}):
    c = [r for r in rows if r["agency_filter"] == agency]
    lag = []
    for x in c:
        date_string = x["initial_report_date"][:10]
        if date_string:
            lag.append(
                (
                    date.fromisoformat(date_string)
                    - date.fromisoformat(x["action_date"])
                ).days
            )
    metrics[agency] = {
        "transactions": len(c),
        "distinct_awards": len({x["contract_award_unique_key"] for x in c}),
        "distinct_nonblank_recipient_ueis": len(
            {x["recipient_uei"] for x in c if x["recipient_uei"]}
        ),
        "modified_or_nonzero_number": sum(
            x["modification_number"].strip()
            not in {"", "0", "00", "000", "0000", "00000", "000000"}
            for x in c
        ),
        "negative_obligation": sum(
            Decimal(x["federal_action_obligation"] or "0") < 0 for x in c
        ),
        "zero_obligation": sum(
            Decimal(x["federal_action_obligation"] or "0") == 0 for x in c
        ),
        "initial_report_present": len(lag),
        "initial_report_after_action": sum(v > 0 for v in lag),
        "initial_report_before_action": sum(v < 0 for v in lag),
        "initial_report_median_lag_days": median(lag) if lag else None,
        "action_types": dict(Counter(x["action_type"] for x in c)),
    }
terms = defaultdict(list)
for x in rows:
    value = x["action_type"].upper()
    if "TERMINAT" in value or "CANCEL" in value:
        terms[x["contract_award_unique_key"]].append(x)
cands = []
for award, c in sorted(terms.items()):
    cands.append(
        {
            "contract_award_unique_key": award,
            "first_action_date": min(x["action_date"] for x in c),
            "initial_report_date_candidates": "|".join(
                sorted(
                    {x["initial_report_date"] for x in c if x["initial_report_date"]}
                )
            ),
            "transaction_count": len(c),
            "agency_filter": c[0]["agency_filter"],
            "recipient_name": c[0]["recipient_name"],
            "action_types": "|".join(sorted({x["action_type"] for x in c})),
            "transaction_obligations_sum": str(
                sum(
                    (Decimal(x["federal_action_obligation"] or "0") for x in c),
                    Decimal(0),
                )
            ),
            "independent_shock_status": "NOT_REVIEWED_FOR_PROGRAM_OR_FIRST_PUBLICATION",
            "public_url": c[0]["usaspending_permalink"],
        }
    )
if cands:
    emit("usa_termination_candidates.csv", cands)
examples = json.loads((raw / "usa_example_tx.json").read_text())
exa = [
    {
        "transaction_id": r["id"],
        "action_date": r["action_date"],
        "modification_number": r["modification_number"],
        "action_type": r["action_type_description"],
        "federal_action_obligation": r["federal_action_obligation"],
    }
    for r in examples["results"]
]
assert not examples["page_metadata"]["hasNext"]
if len({e["transaction_id"] for e in exa}) != len(exa):
    raise ValueError("repeated example transaction ID")
emit("usa_example_award_history.csv", exa)
stats = {
    "by_awarding_agency": metrics,
    "gross_transactions": len(rows),
    "unique_transaction_keys": len(by),
    "unique_award_keys": len({x["contract_award_unique_key"] for x in rows}),
    "termination_or_cancellation_candidate_awards": len(cands),
    "example_award_transactions": len(exa),
    "example_award_monies": "obligation only, not contractor revenue",
}
(out / "usa_metrics.json").write_text(json.dumps(stats, indent=2) + "\n")
print(json.dumps(stats, indent=2))
