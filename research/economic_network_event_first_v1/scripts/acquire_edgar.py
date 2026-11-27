"""Fetch EDGAR annual filings and linked Exhibit 21 snapshots for source-only joins."""

import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

from lxml import html

RAW = Path("raw")
DEST = RAW / "edgar"
DEST.mkdir(exist_ok=True)
NAMES = {
    "BAX": 10456,
    "BDX": 10795,
    "MDT": 1613103,
    "SYK": 310764,
    "ZBH": 1136869,
    "BSX": 885725,
    "GEHC": 1932393,
    "TMO": 97745,
    "JNJ": 200406,
    "PODD": 1145197,
    "DXCM": 1093557,
    "RMD": 943819,
    "PHG": 313216,
    "FMS": 1333141,
    "ICUI": 883984,
    "TMDX": 1756262,
    "ABT": 1800,
    "TNDM": 1438133,
    "AVNS": 1606498,
    "EW": 1099800,
    "TFX": 96943,
    "IART": 917520,
    "HOLX": 859737,
    "PEN": 1321732,
    "OM": 1484612,
    "CAH": 721371,
    "ASAHI": 1065865,
    "OLYMPUS": 769893,
    "DHR": 313616,
    "RTX": 101829,
}


def pull(url, out):
    if out.is_file() and out.stat().st_size > 100:
        return True
    time.sleep(0.38)
    r = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--max-time",
            "18",
            "-A",
            "Investment public EDGAR research source audit",
            "-o",
            str(out),
            url,
        ],
        check=False,
        capture_output=True,
    )
    if r.returncode:
        out.unlink(missing_ok=True)
        return False
    return True


def filing_meta(pair):
    ticker, cik = pair
    src = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    meta = DEST / f"{ticker}.json"
    if not pull(src, meta):
        return []
    data = json.loads(meta.read_text())
    all_records = [data["filings"]["recent"]]
    supplement = data["filings"].get("files", [])
    for s in supplement:
        if s["filingTo"] < "2018" or s["filingFrom"] > "2021":
            continue
        name = s["name"]
        if pull("https://data.sec.gov/submissions/" + name, DEST / name):
            all_records.append(json.loads((DEST / name).read_text()))
    rows = []
    for rec in all_records:
        for i, form in enumerate(rec["form"]):
            day = rec["filingDate"][i]
            if (
                form not in {"10-K", "20-F", "40-F"}
                or not "2018-01-01" <= day <= "2025-12-31"
            ):
                continue
            a = rec["accessionNumber"][i]
            rows.append(
                (
                    ticker,
                    cik,
                    form,
                    day,
                    rec["acceptanceDateTime"][i],
                    rec["reportDate"][i],
                    a,
                    rec["primaryDocument"][i],
                )
            )
    return rows


def filing(row):
    tick, cik, form, day, utc, period, acc, name = row
    stem = tick + "_" + day
    root = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
    document = root + name
    main = DEST / (stem + "_main.html")
    if not pull(document, main):
        return [tick, cik, form, day, utc, period, acc, document, "", ""]
    parsed = html.parse(str(main))
    candidates = []
    for a in parsed.xpath("//a[@href]"):
        href = a.get("href")
        desc = " ".join(a.text_content().split())[:150]
        basename = urlparse(href).path.split("/")[-1].lower()
        ex21 = re.search(
            r"(?:ex(?:hibit)?[\-_. ]*21|subsidia)", basename, re.IGNORECASE
        ) or (desc.startswith("21") and "subsidiar" in desc.lower())
        if form in {"20-F", "40-F"}:
            ex21 = (
                ex21
                or re.search(
                    r"^ex(?:hibit)?[\-_. ]*0?8(?:[\-_. ]|\d)", basename, re.IGNORECASE
                )
                or (desc.startswith("8") and "subsidiar" in desc.lower())
            )
        if not ex21:
            continue
        if href.startswith("#"):
            continue
        url = urljoin(document, href)
        parts = urlparse(url)
        if (
            parts.hostname == "www.sec.gov"
            and "/Archives/edgar/data/" in parts.path
            and not parts.query
        ):
            candidates.append(url)
    exhibit = next(iter(dict.fromkeys(candidates)), "")
    if exhibit and not pull(exhibit, DEST / (stem + "_ex21.html")):
        exhibit = ""
    reg = " ".join(
        " ".join(x.text_content().split())
        for x in parsed.xpath(
            '//*[@name="dei:EntityRegistrantName" or @name="dei:entityregistrantname"]'
        )
    )
    return [tick, cik, form, day, utc, period, acc, document, exhibit, reg]


with ThreadPoolExecutor(3) as ex:
    target = list({r for v in ex.map(filing_meta, NAMES.items()) for r in v})
    target.sort()
    rows = list(ex.map(filing, target))
(DEST / "manifest.json").write_text(json.dumps(rows, indent=2))
print(
    len(rows),
    "annual targets",
    sum(bool(r[-1]) for r in rows),
    "registrant names",
    sum(bool(r[-2]) for r in rows),
    "exhibits",
    flush=True,
)
