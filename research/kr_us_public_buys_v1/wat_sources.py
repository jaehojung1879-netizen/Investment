"""Normalize reviewed SEC documents for the US market-cap input audit."""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import exchange_calendars as xc
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = "https://www.sec.gov/Archives/edgar/data/1000697/"
NY = ZoneInfo("America/New_York")
USER_AGENT = "Investment Research audit data@openai.com"
WAT_PINS = {
    "2025cy-report": ("000119312526062604/d778470d10k.htm", "2aec8b929e6be5e3fe59db427910da24a8f0cd02c365eda5f5b5450a1cf8bf88"),
    "2025cy-index": ("000119312526062604/0001193125-26-062604-index.htm", "8d4a57af4825a4a636c0cd89c3b387101d12dd3e0a743f648f1cd069be644781"),
    "2026q1-report": ("000119312526219487/d435723d10q.htm", "003df08d0d7bbc6bb32d1a223bd9fedd73f122dad53e3c814dfd6552af107cec"),
    "2026q1-index": ("000119312526219487/0001193125-26-219487-index.htm", "b0cfc8dc2048539e680f13b68bfc286b0a6f633fe228f29706b8fab4cdedd14b"),
    "2026q2-report": ("000119312526344691/d170082d10q.htm", "9e86c6006c0a5c9e7b1cee2f55218e3037b4789e8a6ec090736293a1b03fb984"),
    "2026q2-index": ("000119312526344691/0001193125-26-344691-index.htm", "d22395d083f7797fa6932dddfec0355a32362e548b6eb37ed1d36aec7398d11d"),
    "bds-close-8k": ("000119312526042819/d23927d8k.htm", "889ccbc8f7f97486838e356a4aa42cd1f3b3a0c03885d867692551f7146d392e"),
    "bds-close-8k-index": ("000119312526042819/0001193125-26-042819-index.htm", "58e0467d40876e2cbbeae2dc993fd554d068a275389e92cbbb5ab71597e28db6"),
}
SHARES_TAG = "dei:EntityCommonStockSharesOutstanding"
SEC_COVER_KINDS = ("10-Q", "10-K")


@lru_cache(maxsize=1)
def calendar():
    return xc.get_calendar("XNYS", start="2013-01-01", end="2026-12-31")


def decision_close(day):
    return calendar().session_close(day)


class CoverFacts(HTMLParser):
    """Read inline-XBRL cover quantities and the associated XBRL contexts."""

    def __init__(self):
        super().__init__()
        self.current_context = None
        self.active_role = None
        self.contexts = {}
        self.facts = []
        self.active_fact = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        local = tag.split(":")[-1]
        if local == "context" and "id" in a:
            self.current_context = a["id"]
            self.contexts[self.current_context] = {"instant": "", "identifier": "", "dimensions": []}
        if self.current_context and local in ("instant", "identifier", "explicitmember", "typedmember"):
            self.active_role = local
            if local in ("explicitmember", "typedmember"):
                self.contexts[self.current_context]["dimensions"].append({"attribute": a.get("dimension"), "member": ""})
        is_cover = a.get("name", "").casefold() == SHARES_TAG.casefold()
        if local == SHARES_TAG.split(":")[-1].lower() or (local == "nonfraction" and is_cover):
            self.active_fact = {k: a.get(k) for k in ("contextref", "unitref", "scale", "decimals")}
            self.active_fact["text"] = ""

    def handle_endtag(self, tag):
        local = tag.split(":")[-1]
        if local == "context":
            self.current_context = None
        elif local == self.active_role:
            self.active_role = None
        elif local in ("nonfraction", SHARES_TAG.split(":")[-1].lower()) and self.active_fact is not None:
            self.facts.append(self.active_fact)
            self.active_fact = None

    def handle_data(self, content):
        if self.current_context and self.active_role:
            info = self.contexts[self.current_context]
            if self.active_role in ("explicitmember", "typedmember"):
                info["dimensions"][-1]["member"] += content.strip()
            else:
                info[self.active_role] += content.strip()
        if self.active_fact is not None:
            self.active_fact["text"] += content.strip()


def cover_shares(blob):
    reader = CoverFacts()
    reader.feed(blob.decode("utf-8", errors="replace"))
    rows = []
    for f in reader.facts:
        ctx = reader.contexts.get(f["contextref"], {})
        scale = int(f["scale"] or 0)
        n = int(f["text"].replace(",", "")) * 10 ** scale
        if n <= 0 or not ctx.get("instant") or not f["unitref"]:
            raise ValueError("Invalid inline-XBRL cover fact")
        rows.append({"shares": n, "shareAsOf": ctx["instant"], "shareCik": ctx["identifier"],
                     "scale": scale, "unitRef": f["unitref"], "contextRef": f["contextref"],
                     "contextDimensions": ctx["dimensions"], "decimals": f["decimals"],
                     "concept": SHARES_TAG})
    return rows


def acceptance(blob):
    result = re.search(rb">Accepted</div>\s*<div class=\"info\">([^<]+)</div>", blob)
    if result is None:
        raise ValueError("SEC acceptance field unavailable")
    return pd.Timestamp(result.group(1).decode(), tz=NY)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sec_get(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=25) as response:
                if response.status != 200:
                    raise ValueError(f"SEC HTTP {response.status}: {url}")
                return response.read()
        except HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(1.0+attempt)


def diluted_tag(blob, context):
    matches = []
    for attr, value in re.findall(rb"<ix:nonFraction\b([^>]*?)>([0-9,]+)</ix:nonFraction>", blob):
        fields = dict(re.findall(rb'([a-zA-Z]+)="([^"]+)"', attr))
        if (fields.get(b"name") == b"us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding"
                and fields.get(b"contextRef") == context.encode()):
            matches.append((int(value.replace(b",", b"")), int(fields[b"scale"]), fields[b"unitRef"].decode()))
    assert len(set(matches)) == 1
    text, tag_scale, unit = matches[0]
    return {"contextRef": context, "displayedDigits": text, "unitRef": unit,
            "machineScale": tag_scale, "machineShares": text*10**tag_scale,
            "sharesIfDisplayedInThousands": text*1000}


def normalized_wat(cache, fetch):
    bodies = {}
    receipts = {}
    for name, (suffix, expected) in WAT_PINS.items():
        url = BASE + suffix
        path = cache / (name + ".htm")
        if not path.is_file() and fetch:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(sec_get(url))
        data = path.read_bytes()
        observed = sha(data)
        if observed != expected:
            raise ValueError(f"Pinned WAT SEC body mismatch: {name} {observed}")
        bodies[name] = data
        receipts[name] = {"url": url, "sha256": expected, "bytes": len(data)}
    quantities = []
    for name, accession in (
        ("2025cy", "0001193125-26-062604"),
        ("2026q1", "0001193125-26-219487"),
        ("2026q2", "0001193125-26-344691"),
    ):
        stamp = acceptance(bodies[f"{name}-index"])
        rows = cover_shares(bodies[f"{name}-report"])
        assert len(rows) == 1
        row = rows[0]
        assert row["shareCik"] == "0001000697" and row["unitRef"] == "Unit_shares" and row["scale"] == 0
        assert not row["contextDimensions"] and pd.Timestamp(row["shareAsOf"]) < stamp.tz_localize(None)
        quantities.append({**row, "ticker": "WAT", "sourceId": accession, "acceptedET": stamp.isoformat(),
                           "document": receipts[f"{name}-report"], "index": receipts[f"{name}-index"],
                           "kind": "SEC_INLINE_10K_10Q_COVER_ENTITY_COMMON_SHARES"})
    assert [x["shares"] for x in quantities] == [98101871, 98185855, 98248111]
    assert b"38,541,852" in bodies["2025cy-report"] and b"0.135343148384084" in bodies["bds-close-8k"]
    wrong_tags = [diluted_tag(bodies[f"{name}-report"], ctx) for name, ctx in (
        ("2026q1", "P01_01_2026To04_04_2026"),
        ("2026q2", "P01_01_2026To07_04_2026"),
        ("2026q2", "P04_05_2026To07_04_2026"),
    )]
    assert [tag["machineShares"] for tag in wrong_tags] == [82_139_000_000, 90_041_000_000, 98_204_000_000]
    return {"ticker": "WAT", "cik": "0001000697", "shares": quantities,
            "dilutedWeightedAverageTagScaleAudit": wrong_tags,
            "issuance": {"effectiveDate": "2026-02-09", "acceptedET": acceptance(bodies["bds-close-8k-index"]).isoformat(),
                         "sharesIssued": 38541852, "type": "BDS_REVERSE_MORRIS_TRUST_NEW_COMMON_SHARES",
                         "totalOutstandingIn8K": None, "sourceId": "0001193125-26-042819",
                         "document": receipts["bds-close-8k"], "index": receipts["bds-close-8k-index"],
                         "exactIssueQuantitySource": quantities[0]["document"]},
            "sourceReceipts": receipts}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("/workspace/wat-sec-inputs"))
    ap.add_argument("--out", type=Path, default=HERE / "results/WAT/wat-sec-receipts.json")
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args(argv)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(normalized_wat(a.cache, a.fetch), ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
