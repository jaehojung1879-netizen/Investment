"""Source-only inspection of manually transcribed guidance; no price access."""
import csv
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

KEY = ("cik", "target", "metric", "basis", "unit")
STATUSES = {"NUMERIC", "NO_UPDATE", "NOT_PROVIDED"}


def revisions(rows):
    """Compare consecutive observed statements, never bridge a missing numeric update."""
    ordered = sorted(rows, key=lambda row: datetime.fromisoformat(row["accepted_at"]))
    previous = {}
    seen = set()
    output = []
    for row in ordered:
        ts = datetime.fromisoformat(row["accepted_at"])
        if ts.tzinfo is None:
            raise ValueError("acceptance timestamp requires offset")
        key = tuple(row[k] for k in KEY)
        if not all(key):
            raise ValueError("missing comparison key")
        unique = (key, row["accession"])
        if unique in seen:
            raise ValueError("duplicate statement")
        seen.add(unique)
        prior = previous.get(key)
        if prior and datetime.fromisoformat(prior["accepted_at"]) >= ts:
            raise ValueError("ambiguous timestamp order")
        status = row["status"]
        if status not in STATUSES:
            raise ValueError("unknown status")
        if status == "NUMERIC":
            low, high = Decimal(row["low"]), Decimal(row["high"])
            if not low.is_finite() or not high.is_finite() or low > high:
                raise ValueError("invalid guidance bounds")
            midpoint = (low + high) / 2
        else:
            if row["low"] or row["high"]:
                raise ValueError("non-numeric status cannot contain values")
            midpoint = None
        change = None
        if midpoint is not None and prior and prior["status"] == "NUMERIC":
            old = (Decimal(prior["low"]) + Decimal(prior["high"])) / 2
            change = str(midpoint - old)
        output.append({
            "issuer": row["issuer"], "accession": row["accession"],
            "target": row["target"], "metric": row["metric"],
            "basis": row["basis"], "unit": row["unit"], "status": status,
            "midpoint_change": change,
            "prior_accession": prior["accession"] if prior else None,
        })
        previous[key] = row
    return output


def main():
    path = Path(__file__).with_name("observations.csv")
    with path.open(encoding="utf-8", newline="") as file:
        result = revisions(csv.DictReader(file))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
