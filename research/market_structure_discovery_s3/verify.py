"""Validate the retained S3 packet and, optionally, replay its raw source checks."""

import argparse
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from statistics import mean
import subprocess

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def index(rows, field):
    indexed = {row[field]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"Duplicate {field}")
    return indexed


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def source_text(p):
    if p.suffix == ".pdf":
        return subprocess.check_output(["pdftotext", "-layout", str(p), "-"], text=True)
    from lxml import html

    tree = html.fromstring(p.read_bytes())
    for node in tree.xpath('//script|//style|//*[name()="ix:header"]'):
        node.drop_tree()
    return " ".join(tree.itertext())


def check_income(raw, cases, sources):
    comparisons = read("COMPARISON.json")["netIncomeComparison"]
    for row in comparisons:
        event = cases[row["eventId"]]
        ticker = row["ticker"]
        facts = json.loads((raw / f"{ticker}-facts.json").read_bytes())
        income = facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
        for i, year in enumerate((2023, 2024)):
            filing = sources[f"{ticker}-{year}-10K.htm"]
            matches = {
                record["val"]
                for record in income
                if record.get("accn") == filing["accession"] and record.get("form") == "10-K"
                and record["end"] == filing["fiscalEnd"] and record.get("start")
                and 350 <= (date.fromisoformat(record["end"]) - date.fromisoformat(record["start"])).days <= 380
            }
            state = event[("previousKnownState", "newlyObservedState")[i]]
            assert matches == {state["value"]} == {row["companyfacts"][i]}, (ticker, year)


def check_raw(raw, cases, sources):
    for item in sources.values():
        if item["status"] == "FETCHED":
            data = (raw / item["sourceId"]).read_bytes()
            assert len(data) == item["bytes"] and sha256(data).hexdigest() == item["sha256"], item["sourceId"]
    cached = {}
    n = 0
    for ev in cases.values():
        for ref in ev["sourceEvidence"]:
            tokens = list(ref.get("tokens", []))
            if "anchor" in ref:
                tokens.append(ref["anchor"])
            if not tokens:
                continue
            source_id = ref["sourceId"]
            if source_id not in cached:
                cached[source_id] = normalize(source_text(raw / source_id))
            for token in tokens:
                assert normalize(token) in cached[source_id], (source_id, token)
                n += 1
    assert n == read("COMPARISON.json")["evidenceChecks"]["correctedMatched"]
    check_income(raw, cases, sources)
    print(f"{n} source anchors and 10 accession-specific income values checked")


def main():
    from jsonschema import Draft202012Validator

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path)
    args = parser.parse_args()
    records = read("SOURCE-MANIFEST.json")
    sources = index(records, "sourceId")
    lines = (ROOT / "ECONOMIC-EVENTS.jsonl").read_text(encoding="utf-8").splitlines()
    cases = index([json.loads(line) for line in lines], "eventId")
    schema = Draft202012Validator(read("EVENT.schema.json"), format_checker=Draft202012Validator.FORMAT_CHECKER)
    for ev in cases.values():
        schema.validate(ev)
        receipt = sources[ev["sourceId"]]
        assert receipt["status"] == "FETCHED"
        assert ev["publishedAt"] == receipt["publishedAt"]
        assert datetime.fromisoformat(ev["observedAt"]) >= datetime.fromisoformat(receipt["observedAt"])
        assert all(sources[e["sourceId"]]["status"] == "FETCHED" for e in ev["sourceEvidence"])
        assert ev["outcome"] is None
        if ev["newlyObservedState"] is None:
            assert ev["direction"] is None
    experts = read("EXPERT-FORECASTS.json")
    scored = [row for row in experts["series"] if row["scored"]]
    assert all(row["probability"] is None and row["publishedTime"] is None for row in experts["series"])
    for name, field in [("EIA", "errorThousandBpd"), ("priorForecast", "priorErrorThousandBpd"),
                        ("reported2023Level", "priorYearErrorThousandBpd")]:
        assert round(mean(abs(row[field]) for row in scored), 3) == experts["maeThousandBpd"][name]
    print(f"{len(cases)} events, {len(records)} receipts, {len(scored)} scored forecast vintages")
    if args.raw_dir:
        check_raw(args.raw_dir, cases, sources)


if __name__ == "__main__":
    main()
