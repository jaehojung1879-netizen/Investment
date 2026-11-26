"""us-rank-independent-check-v1 — reference snapshots of S&P 500 company size from SPY's own SEC holdings filings.

This module does NOT rank, weight or value anything the way Codex's study does; it builds an independent yardstick to audit those outputs against.

SOURCE AND IDENTITY
  * The filings are exactly the SPY rows of docs/us-readiness/us-etf-sec-holdings-cross-check-v1.json (#342): the same URLs, and every downloaded
    byte string must hash to the SHA-256 recorded there or the run refuses (SOURCE_BYTES_CHANGED).
  * SPY's 2026 prospectus (485BPOS 0001193125-26-022316, sha256 695221f8...) states: "The Index is a float-adjusted capitalization weighted index of
    500 companies ... the aggregate market value of the available float shares outstanding in each of the component 500 Index Securities". A full-
    replication trust's holding value is therefore a security-line reading of float-adjusted market value on the holding date.

THREE DATES, NEVER ONE
  holdingAsOf      the date the positions describe (N-PORT repPdDate / the N-30D report date)
  publicFrom       the EDGAR filing date: the first day anyone outside the fund could read the positions
  indexEffective   official S&P index-change effective dates (#339 manually reviewed notices) are reported beside each snapshot; a change effective
                   between holdingAsOf and publicFrom means the filing describes a membership that was already stale when it became public.

SHARE CLASSES
  N-PORT lines are grouped into companies by LEI (one issuer, several CUSIPs: GOOGL/GOOG, FOXA/FOX, NWSA/NWS ...). N-30D (2018) has no LEI or CUSIP,
  so lines are grouped by the issuer name with a trailing class designation removed; every multi-line group is published for review. Ranking is
  done at COMPANY level and at LINE level and both are reported, because the S&P 500 holds lines while "the top-K companies" holds issuers.

TICKERS
  N-PORT CUSIPs are mapped with OpenFIGI (US composite). OpenFIGI answers with the CURRENT ticker of the CUSIP; a later rename (FB -> META) therefore
  shows the later symbol. The map is committed (inputs/openfigi-cusip-map.json) and labelled as such.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import subprocess
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UA = "Investment research audit admin@example.com"          # generic client name; no personal details
CROSS_CHECK = "docs/us-readiness/us-etf-sec-holdings-cross-check-v1.json"
DEPARTED = "research/us_historical_market_recovery_v1/inputs/departed-public-evidence.json"
PIN_COMMIT = "4f4497bcc9e7f9369bf5529225585ad39b0d7725"      # main after #342
REPLAY_COMMIT = "4ea107ed0cde289f0a049a65ff13d2441a786710"  # replay-v16 universe component (US PIT membership)
YEARS = ("2018", "2020", "2022")
BOUNDARIES = (5, 10, 100)
THIN_MARGIN = 0.02


def git_show(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def selected_filings():
    rows = [r for r in json.loads(git_show(PIN_COMMIT, CROSS_CHECK))["results"] if r["ticker"] == "SPY"]
    nport_dates = {r["as_of"] for r in rows if r["form"].startswith("NPORT")}
    # N-30D only where no N-PORT describes the same date (2018): N-PORT carries CUSIP and LEI, N-30D only names.
    pick = [r for r in rows if r["as_of"][:4] in YEARS and (r["form"].startswith("NPORT") or r["as_of"] not in nport_dates)]
    latest = max((r for r in rows if r["form"] == "NPORT-P"), key=lambda r: r["as_of"])
    pick.append(latest)
    return sorted({r["accession"]: r for r in pick}.values(), key=lambda r: (r["as_of"], r["form"]))


BOT_SCRIPT = re.compile(rb'<script type="text/javascript"\s+src="/[A-Za-z0-9/_+=-]+"></script>')


def fetch(row, cache):
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (row["accession"] + Path(row["url"]).suffix)
    if not path.exists():
        req = urllib.request.Request(row["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            path.write_bytes(r.read())
        time.sleep(0.3)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() == row["source_sha256"]:
        return raw, "EXACT_SHA256_MATCH_TO_342"
    if path.suffix.lower() in (".htm", ".html") and BOT_SCRIPT.search(raw):
        # SEC appends a bot-defence <script src="/<rotating path>"> to HTML documents; the path rotates over time, so raw bytes cannot reproduce
        # #342's hash once it has rotated. The holding count is checked against #342 after parsing instead.
        return BOT_SCRIPT.sub(b"", raw), "HTML_BOT_SCRIPT_STRIPPED_CONTENT_CHECKED_BY_HOLDING_COUNT"
    raise ValueError("SOURCE_BYTES_CHANGED: " + row["accession"])


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #
def _tag(block, tag):
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
    return html.unescape(m.group(1).strip()) if m else None


def parse_nport(raw):
    t = raw.decode("utf-8")
    meta = {k: _tag(t, k) for k in ("repPdDate", "repPdEnd", "totAssets", "netAssets")}
    lines = []
    for b in re.findall(r"<invstOrSec>(.*?)</invstOrSec>", t, re.S):
        isin = re.search(r'<isin value="([^"]+)"', b)
        lines.append({"name": _tag(b, "name"), "title": _tag(b, "title"), "lei": _tag(b, "lei"), "cusip": _tag(b, "cusip"),
                      "isin": isin.group(1) if isin else None, "shares": float(_tag(b, "balance") or "nan"), "units": _tag(b, "units"),
                      "valueUsd": float(_tag(b, "valUSD") or "nan"), "pctNav": float(_tag(b, "pctVal") or "nan"), "assetCat": _tag(b, "assetCat")})
    return meta, lines


NUM = re.compile(r"^\(?[\d,]+\)?$")
POS = re.compile(r"^[\d,]+$")


def parse_n30d(raw):
    """Schedule of investments: walk the document's text cells from the schedule heading (its second occurrence; the first is the table of
    contents) to the 'Total Common Stocks' row, taking every non-numeric cell followed by two numeric cells as `name, shares, value`.
    A cell walk, not a <TR> walk: one N-30D has an unbalanced <TR>, and a row parser silently dropped a holding there. The parsed values must sum
    to the filing's own 'Total Common Stocks' figure (checked by the caller)."""
    t = raw.decode("latin-1")
    first = t.find("Schedule of Investments")
    start = t.find("Schedule of Investments", first + 30)
    low = t.lower()
    end = low.find("total common stocks", start)
    if start < 0 or end < 0:
        return {"totalCommonStocksUsd": None, "parsedSumUsd": None}, []
    tail = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "|", t[end:end + 4000])))
    tcells = [c.strip() for c in tail.split("|") if c.strip() and c.strip() != "$"]
    total = next((float(c.replace(",", "")) for c in tcells[1:] if POS.match(c)), None)
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "|", t[start:end])))
    cells = [c.strip() for c in txt.split("|") if c.strip() and c.strip() != "$"]
    lines = []
    for i, c in enumerate(cells[:-2]):
        if NUM.match(c) or not re.search(r"[A-Za-z]", c):
            continue
        if POS.match(cells[i + 1]) and POS.match(cells[i + 2]):
            lines.append({"name": c, "shares": float(cells[i + 1].replace(",", "")), "valueUsd": float(cells[i + 2].replace(",", ""))})
    return {"totalCommonStocksUsd": total, "parsedSumUsd": sum(x["valueUsd"] for x in lines)}, lines


CLASS_SUFFIX = re.compile(r"[,\s]+(class|cl\.?)\s+[a-z](\s+reit)?$|\s+reit$", re.I)


FOOTNOTE = re.compile(r"(\s*\([a-z]\))+$", re.I)


def issuer_key_from_name(name):
    n = CLASS_SUFFIX.sub("", FOOTNOTE.sub("", name.strip()))
    return re.sub(r"[^a-z0-9]", "", n.lower())


# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #
def companies(lines, form):
    groups = defaultdict(list)
    for ln in lines:
        key = ("LEI:" + ln["lei"]) if form.startswith("NPORT") and ln.get("lei") and ln["lei"] != "N/A" else "NAME:" + issuer_key_from_name(ln["name"])
        groups[key].append(ln)
    out = []
    for key, g in groups.items():
        out.append({"issuerKey": key, "name": max(g, key=lambda x: x["valueUsd"])["name"], "valueUsd": sum(x["valueUsd"] for x in g),
                    "lines": [{k: x.get(k) for k in ("name", "title", "cusip", "shares", "valueUsd")} for x in sorted(g, key=lambda x: -x["valueUsd"])]})
    tot = sum(c["valueUsd"] for c in out)
    out.sort(key=lambda c: (-c["valueUsd"], c["issuerKey"]))
    for i, c in enumerate(out, 1):
        c["rank"], c["weight"] = i, c["valueUsd"] / tot
    return out, tot


def boundary(ranked, k):
    if len(ranked) <= k:
        return None
    a, b = ranked[k - 1]["valueUsd"], ranked[k]["valueUsd"]
    return {"k": k, "inside": ranked[k - 1]["name"], "outside": ranked[k]["name"], "relativeGap": (a - b) / a, "thin": (a - b) / a < THIN_MARGIN}


def build(cache, figi_map):
    filings = selected_filings()
    membership = us_membership()
    notices = official_notices()
    snaps = []
    for row in filings:
        raw, verification = fetch(row, cache)
        meta, lines = parse_nport(raw) if row["form"].startswith("NPORT") else parse_n30d(raw)
        eq = [ln for ln in lines if ln.get("assetCat") in (None, "EC")]
        if not row["form"].startswith("NPORT") and meta.get("totalCommonStocksUsd") is None:
            raise ValueError("SCHEDULE_TOTAL_NOT_FOUND: " + row["accession"])
        if meta.get("totalCommonStocksUsd") is not None and abs(meta["parsedSumUsd"] - meta["totalCommonStocksUsd"]) > 1.0:
            raise ValueError("SCHEDULE_DOES_NOT_SUM_TO_ITS_TOTAL: %s %.0f vs %.0f" % (row["accession"], meta["parsedSumUsd"], meta["totalCommonStocksUsd"]))
        if verification.startswith("HTML") and len(lines) != row["holding_count"]:
            raise ValueError("HOLDING_COUNT_DIFFERS_FROM_342: %s parsed %d recorded %d" % (row["accession"], len(lines), row["holding_count"]))
        comp, tot = companies(eq, row["form"])
        line_rank = sorted(eq, key=lambda x: -x["valueUsd"])
        for c in comp:
            for ln in c["lines"]:
                ln["ticker"] = figi_map.get(ln.get("cusip"))
        multi = [c for c in comp if len(c["lines"]) > 1]
        snap = {"form": row["form"], "accession": row["accession"], "url": row["url"], "sourceSha256": row["source_sha256"], "verification": verification, "holdingCountRecordedBy342": row["holding_count"],
                "parsedHoldingLines": len(lines),
                "holdingAsOf": row["as_of"], "publicFrom": row["filed"], "publicationLagDays": row["publication_lag_days"],
                "equityLines": len(eq), "companies": len(comp), "equityValueUsd": tot,
                "netAssetsUsd": float(meta["netAssets"]) if meta.get("netAssets") else None,
                "scheduleTotalCommonStocksUsd": meta.get("totalCommonStocksUsd"),
                "multiClassCompanies": [{"name": c["name"], "rank": c["rank"], "lines": [(ln["name"], ln.get("ticker"), round(ln["valueUsd"])) for ln in c["lines"]]}
                                        for c in multi],
                "boundaries": {str(k): boundary(comp, k) for k in BOUNDARIES},
                "lineVsCompanyTopK": {str(k): sorted(set(x["name"] for x in line_rank[:k]) ^ set(ln["name"] for c in comp[:k] for ln in c["lines"][:1]))
                                      for k in BOUNDARIES},
                "top100": [{"rank": c["rank"], "name": c["name"], "issuerKey": c["issuerKey"], "valueUsd": round(c["valueUsd"], 2), "weight": c["weight"],
                            "tickers": [ln.get("ticker") for ln in c["lines"]], "cusips": [ln.get("cusip") for ln in c["lines"]]} for c in comp[:100]],
                "officialIndexChangesBetweenHoldingAndPublic": [n for n in notices if row["as_of"] < n["effective"] <= row["filed"]],
                "officialIndexChangesWithin30DaysBeforeHolding": [n for n in notices if n["effective"] <= row["as_of"] and
                                                                  (pd_days(n["effective"], row["as_of"]) <= 30)]}
        if row["form"].startswith("NPORT"):
            snap["membershipComparison"] = compare_membership(comp, membership, row["as_of"])
        snaps.append(snap)
    return snaps


def pd_days(a, b):
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def us_membership():
    m = json.loads(git_show(REPLAY_COMMIT, "ledger/historical/replay-v16/inputs.json"))
    ref = m["components"]["universe"][0]
    raw = gzip.decompress(git_show(REPLAY_COMMIT, f"ledger/replay-inputs/objects/{ref}.json.gz"))
    if hashlib.sha256(raw).hexdigest() != ref:
        raise ValueError("REPLAY_OBJECT_HASH_MISMATCH")
    return {t: v for t, v in json.loads(raw)[0]["memberships"].items() if v.get("region") == "US"}


def official_notices():
    rows = json.loads(git_show(PIN_COMMIT, DEPARTED))["rows"]
    return sorted([{"ticker": r["audit_identifier"], "effective": x["date"], "timing": x.get("timing"), "url": x["sources"][0]["url"]}
                   for r in rows for x in r["index_removals"]], key=lambda n: n["effective"])


def norm_ticker(t):
    return None if t is None else t.replace("/", ".").replace("-", ".")


def compare_membership(comp, membership, day):
    held = {norm_ticker(ln["ticker"]) for c in comp for ln in c["lines"] if ln.get("ticker")}
    unmapped = [ln["name"] for c in comp for ln in c["lines"] if not ln.get("ticker")]
    members = {norm_ticker(t) for t, v in membership.items() if v["listed"] <= day and (v["delisted"] is None or v["delisted"] > day)}
    by_norm = {norm_ticker(t): v for t, v in membership.items()}
    why = {}
    for t in sorted(held - members):
        v = by_norm.get(t)
        if v is None:
            why[t] = "NOT_IN_REPO_UNDER_THIS_SYMBOL (later rename or OpenFIGI current symbol)"
        elif v["listed"] > day:
            why[t] = "REPO_LISTS_LATER:" + v["listed"]
        else:
            why[t] = "REPO_DELISTED_EARLIER:" + str(v["delisted"])
    return {"repoMembersOnHoldingDate": len(members), "spyLinesWithTicker": len(held), "spyLinesWithoutTicker": unmapped,
            "inRepoNotInSpy": sorted(members - held), "inSpyNotInRepo": sorted(held - members), "inSpyNotInRepoReason": why,
            "note": "SPY tickers are OpenFIGI CURRENT tickers of the filed CUSIPs; a later rename appears as a symmetric pair (old in repo, new in SPY)"}


def openfigi_map(cusips, cache_path):
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = sorted(c for c in set(cusips) if c and c not in cache)
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        req = urllib.request.Request("https://api.openfigi.com/v3/mapping", data=json.dumps([{"idType": "ID_CUSIP", "idValue": c} for c in batch]).encode(),
                                     headers={"Content-Type": "application/json"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    res = json.loads(r.read())
                break
            except Exception:  # noqa: BLE001 — rate limit; back off
                time.sleep(15 * (attempt + 1))
        else:
            raise RuntimeError("OPENFIGI_UNAVAILABLE")
        for c, x in zip(batch, res):
            d = x.get("data") or []
            us = [r for r in d if r.get("exchCode") == "US"] or [r for r in d if str(r.get("exchCode", "")).startswith("U")]
            if us:
                cache[c] = us[0]["ticker"]
            elif d:
                cache[c] = None                         # identifier known, but no US listing line today (e.g. a retired CUSIP)
            elif "No identifier found" in str(x.get("warning") or x.get("error") or ""):
                cache[c] = None                         # a definite answer; a rate-limit or transient error is never cached
        time.sleep(2.6)
    cache_path.write_text(json.dumps(dict(sorted(cache.items())), indent=0) + "\n")
    return cache


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True, help="directory for the downloaded SEC filings (verified by hash; not committed)")
    a = ap.parse_args(argv)
    cache = Path(a.cache)
    cusips = []
    for row in selected_filings():
        if row["form"].startswith("NPORT"):
            cusips += [ln["cusip"] for ln in parse_nport(fetch(row, cache)[0])[1]]
    figi = openfigi_map(cusips, HERE / "inputs/openfigi-cusip-map.json")
    snaps = build(cache, figi)
    out = {"studyId": "us-rank-independent-check-v1", "artifact": "SPY_SEC_HOLDINGS_REFERENCE_SNAPSHOTS",
           "sourceRecord": {"repoCommit": PIN_COMMIT, "file": CROSS_CHECK}, "membershipSource": {"commit": REPLAY_COMMIT, "component": "replay-v16 universe"},
           "methodologyEvidence": {"spyProspectus": "https://www.sec.gov/Archives/edgar/data/884394/000119312526022316/d77353d485bpos.htm",
                                   "sha256": "695221f82ac76899d7407472ad878f5477b58adccfd3ec9a3f9958f5a011ce32",
                                   "quote": "The Index is a float-adjusted capitalization weighted index of 500 companies ... the aggregate market value of the available float shares outstanding in each of the component 500 Index Securities"},
           "snapshots": snaps}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/spy-reference-snapshots.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    for s in snaps:
        b = s["boundaries"]
        print(s["form"], s["holdingAsOf"], s["publicFrom"], s["equityLines"], s["companies"], round(s["equityValueUsd"] / 1e9, 1),
              {k: (round(v["relativeGap"], 4), v["thin"]) if v else None for k, v in b.items()}, len(s["multiClassCompanies"]))


if __name__ == "__main__":
    main()
