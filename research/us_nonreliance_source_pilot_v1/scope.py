"""Source-only audit of manually coded Item 4.02 disclosure scopes."""
import json
from datetime import datetime
from pathlib import Path


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("offset required")
    return result


def scope_history(rows, as_of):
    cutoff = stamp(as_of)
    observed = {}
    pending = {}
    ids = set()
    output = []
    for row in sorted(rows, key=lambda r: stamp(r["accepted_at"])):
        if stamp(row["accepted_at"]) > cutoff:
            continue
        cik, accession = row["cik"], row["accession"]
        if (cik, accession) in ids:
            raise ValueError("duplicate filing")
        ids.add((cik, accession))
        if row["form"] not in {"8-K", "8-K/A"} or "4.02" not in row["items"]:
            raise ValueError("not Item 4.02")
        confirmed = set(row["confirmed"])
        review = set(row["under_review"])
        if not confirmed or confirmed & review:
            raise ValueError("invalid scope")
        old = observed.setdefault(cik, set())
        prior_review = pending.setdefault(cik, set())
        output.append({"accession": accession, "new_scope": sorted(confirmed - old),
                       "repeated_scope": sorted(confirmed & old),
                       "prior_review_now_confirmed": sorted(confirmed & prior_review)})
        old.update(confirmed)
        prior_review.update(review)
        prior_review.difference_update(old)
    return output


if __name__ == "__main__":
    rows = json.loads(Path(__file__).with_name("observations.json").read_text(encoding="utf-8"))
    print(json.dumps(scope_history(rows, "2026-11-25T00:00:00+00:00"), indent=2))
