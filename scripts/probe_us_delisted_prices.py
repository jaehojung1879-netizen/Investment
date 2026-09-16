"""Who will sell us bars for the 194 US names Yahoo stopped answering for?

WHAT IS ALREADY MEASURED, AND WHAT IT LEAVES OPEN. `replay-v16` sealed a price
panel that serves 633 of the 829 US names that have ever been in the index.
The other 194 are in `data/us-unpriced-members.json`, measured against the
sealed snapshot rather than guessed: every one of them has a `delisted` date,
and not one still-listed member is missing. So the gap is exactly the
survivorship gap — `dataIntegrity` reports US at 82.90% constituent coverage
and `HIGH` risk because of these names, and 2013 is its worst year at 73.13%.

`fetch_prices` already asks for them. `run_replay` appends every former member
to the download list and prints how many it added, and `fetch_prices` retries
what a batch missed in small batches before giving up. There is no filter
between the vendor and the panel. So these 194 are not names the replay forgot
to request — they are names Yahoo returned nothing for, twice.

Korea had the same hole and it was closed by leaving the vendor, not by
retrying it: KRX's own endpoint lists what TRADED on a date, so a name that
delisted in 2014 is in the 2013 responses like any other, and Korean departed
coverage went 34.55% -> 100% served. This probe asks the same question for the
US: which vendor, of the ones whose hosts already answer from the Actions pool,
will serve a dead US ticker's daily history.

WHAT IT REFUSES TO CONCLUDE WITHOUT A CONTROL. A vendor that answers nothing
for `YHOO` may be refusing dead tickers or may be refusing us — a bad key, an
exhausted quota, a plan that never included history. Every vendor is therefore
asked the SAME questions about a control cohort of names that are alive today
and that the sealed panel already serves. A vendor that misses the control has
told us about our account, not about delisting, and its verdict says so:

  OPEN                served the departed cohort AND the control
  PLAN_LIMITED        has the names and quotes a price for them — a budget
                      question, not a vendor search
  DEPARTED_REFUSED    served the control, served nothing departed, and said
                      nothing about a plan — a real finding
  VENDOR_UNUSABLE     missed the control too; nothing is proven about delisting
  NO_KEY              no credential was passed, so it was never asked

PLAN_LIMITED is the distinction run #1 lacked, and lacking it produced a wrong
verdict: polygon answered every departed name with `NOT_AUTHORIZED — "Your plan
doesn't include this data timeframe"` and the probe filed all twelve as errors,
so the vendor read DEPARTED_REFUSED. Polygon had not refused the tickers; it had
quoted a price. "Find another vendor" and "pay this one" are opposite moves.

COVERAGE IS NOT "DID IT ANSWER". A vendor can answer with a two-year window and
look served. Each response is scored against the name's OWN membership span
(`listed`..`delisted`), because that is the only stretch the replay needs, and
a name is only `full` when the vendor covers essentially all of it. This is the
same distinction `coverage_shortfall` draws in the replay: a short history is
not a gap, but it is not coverage either.

RATE LIMITS ARE MEASURED, NOT ASSUMED. Probes run #2 lost the departed cohort
to Polygon's rate limiter and reported that as a vendor verdict; it was not
one. Every request here is spaced by `--delay`, a 429 is retried with backoff,
and a name that ends on 429 is recorded as `RATE_LIMITED` — never as empty.

Usage:
    python scripts/probe_us_delisted_prices.py --output probe.json
    python scripts/probe_us_delisted_prices.py --sample 24 --delay 13
    python scripts/probe_us_delisted_prices.py --vendors stooq,polygon
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COHORT = ROOT / "data" / "us-unpriced-members.json"

# Alive today, in the index across the whole replay, and served by the sealed
# panel. If a vendor cannot serve these, it cannot serve anything for us.
CONTROL = ("AAPL", "JPM", "XOM")

# A name counts as covered when the vendor spans essentially all of its
# membership. Not 100%: a vendor whose history starts the week after a name
# joined, or ends the week before it left, has the name — the replay would rank
# it on every date but a handful.
#
# That tolerance is DAYS AT EACH EDGE, not a share of the span, because a share
# means different things at different lengths: 98% of a decade is ten weeks and
# 98% of a one-year membership is a single week, so one ratio cannot express
# "the week after it joined" for both. The cohort runs from one-day memberships
# to fourteen-year ones.
EDGE_TOLERANCE_DAYS = 14
PARTIAL_COVERAGE = 0.10

SERVED_FULL = "FULL"
SERVED_PARTIAL = "PARTIAL"
SERVED_EMPTY = "EMPTY"
RATE_LIMITED = "RATE_LIMITED"
# The vendor has the name and will not serve it on this plan. Run #1 recorded
# every one of these as ERROR, which made polygon read DEPARTED_REFUSED when
# what it actually said was "Your plan doesn't include this data timeframe" —
# a sentence about our account, not about the ticker being dead. The two want
# opposite next moves (change vendor / pay the vendor), so they are separate.
PLAN_LIMITED = "PLAN_LIMITED"
ERROR = "ERROR"

TIMEOUT = 30

# urllib announces itself as `Python-urllib/3.11`, which a good many sites
# answer with 404 or 403 regardless of the path. Run #1 got a 404 HTML page
# from stooq for AAPL, JPM and XOM — names stooq certainly has — so the header
# is a candidate explanation that had not been ruled out. Asking as a browser
# does not make a refusal go away; it removes one reason for a false one.
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Payment-required and plan-scope refusals, as each vendor spells them.
PLAN_STATUSES = (402, 403)
PLAN_PHRASES = ("not_authorized", "doesn't include", "does not include",
                "upgrade", "payment required", "premium", "subscription",
                "your plan", "exclusive endpoint", "special endpoint")


def _get(url: str, *, headers: dict | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:2000]
    except Exception as exc:  # pragma: no cover - network dependent
        return 0, f"{type(exc).__name__}: {exc}".encode()


def _text(body: bytes, limit: int = 200) -> str:
    """What the vendor actually said, always — never 'unparseable body'.

    Run #1 printed `HTTP 402: unparseable body` twelve times because the error
    path only described bodies that were JSON. The status code alone cannot
    tell a paywall from an outage, and the sentence that can was thrown away.
    """
    text = body.decode("utf-8", "replace").strip().replace("\n", " ")
    return text[:limit] if text else "(empty body)"


def _is_plan_refusal(status: int, body_text: str) -> bool:
    """A refusal about our account rather than about the ticker."""
    if status not in PLAN_STATUSES:
        return False
    lowered = body_text.lower()
    # 402 is Payment Required and means it on its own; 403 is also used for
    # plain auth failures, so it has to say something about the plan.
    return status == 402 or any(phrase in lowered for phrase in PLAN_PHRASES)


def _dates_from_csv(body: bytes) -> list[str]:
    """Dates out of a header+rows CSV whose first column is the date."""
    lines = body.decode("utf-8", "replace").splitlines()
    if len(lines) < 2:
        return []
    header = [cell.strip().lower() for cell in lines[0].split(",")]
    if not header or not header[0].startswith("date"):
        return []
    out = []
    for line in lines[1:]:
        cell = line.split(",", 1)[0].strip()
        if len(cell) == 10 and cell[4] == "-" and cell[7] == "-":
            out.append(cell)
    return out


def _classify_http(status: int, body: bytes) -> tuple[str, str] | None:
    """The failure this response is, or None when it is a body worth parsing.

    Every vendor shares this: the shape of the payload differs, the meaning of
    429 / 402 / a plan-scoped 403 does not, and every one of them keeps the
    vendor's own sentence rather than a paraphrase of its status code.
    """
    text = _text(body)
    if status == 429:
        return RATE_LIMITED, f"HTTP 429: {text}"
    if _is_plan_refusal(status, text):
        return PLAN_LIMITED, f"HTTP {status}: {text}"
    if status != 200:
        return ERROR, f"HTTP {status}: {text}"
    return None


def stooq(ticker: str, start: str, end: str, key: str) -> tuple[str, list[str], str]:
    """Stooq's CSV export. No credential, which is the point of asking it first."""
    url = ("https://stooq.com/q/d/l/?s=" + urllib.parse.quote(ticker.lower() + ".us")
           + f"&d1={start.replace('-', '')}&d2={end.replace('-', '')}&i=d")
    status, body = _get(url)
    failure = _classify_http(status, body)
    if failure:
        return failure[0], [], failure[1]
    dates = _dates_from_csv(body)
    # Stooq answers 200 with a one-line body when it has nothing, so an empty
    # parse here is a real absence rather than a shape this parser missed.
    return "", dates, "" if dates else f"200 but no rows: {_text(body, 120)}"


def polygon(ticker: str, start: str, end: str, key: str) -> tuple[str, list[str], str]:
    """Aggregates. Polygon keeps delisted tickers addressable by symbol."""
    url = (f"https://api.polygon.io/v2/aggs/ticker/{urllib.parse.quote(ticker)}"
           f"/range/1/day/{start}/{end}?adjusted=true&sort=asc&limit=50000"
           f"&apiKey={urllib.parse.quote(key)}")
    status, body = _get(url)
    failure = _classify_http(status, body)
    if failure:
        return failure[0], [], failure[1]
    try:
        payload = json.loads(body)
    except ValueError:
        return ERROR, [], f"HTTP {status}: {_text(body)}"
    dates = [time.strftime("%Y-%m-%d", time.gmtime(row["t"] / 1000))
             for row in (payload.get("results") or []) if row.get("t")]
    return "", dates, ""


def finnhub(ticker: str, start: str, end: str, key: str) -> tuple[str, list[str], str]:
    """Candles. The same key the PIT fundamentals collector already uses."""
    frm = int(time.mktime(time.strptime(start, "%Y-%m-%d")))
    to = int(time.mktime(time.strptime(end, "%Y-%m-%d")))
    url = (f"https://finnhub.io/api/v1/stock/candle?symbol={urllib.parse.quote(ticker)}"
           f"&resolution=D&from={frm}&to={to}&token={urllib.parse.quote(key)}")
    status, body = _get(url)
    failure = _classify_http(status, body)
    if failure:
        return failure[0], [], failure[1]
    try:
        payload = json.loads(body)
    except ValueError:
        return ERROR, [], f"HTTP {status}: {_text(body)}"
    if payload.get("s") == "no_data":
        return "", [], ""
    stamps = payload.get("t") or []
    return "", [time.strftime("%Y-%m-%d", time.gmtime(s)) for s in stamps], ""


def fmp(ticker: str, start: str, end: str, key: str) -> tuple[str, list[str], str]:
    """FMP's EOD history. Its statements are capped at 4 periods; prices may not be."""
    url = ("https://financialmodelingprep.com/stable/historical-price-eod/full?symbol="
           + urllib.parse.quote(ticker)
           + f"&from={start}&to={end}&apikey={urllib.parse.quote(key)}")
    status, body = _get(url)
    failure = _classify_http(status, body)
    if failure:
        return failure[0], [], failure[1]
    try:
        payload = json.loads(body)
    except ValueError:
        return ERROR, [], f"HTTP {status}: {_text(body)}"
    rows = payload if isinstance(payload, list) else (payload.get("historical") or [])
    # FMP says some refusals in a 200 body, the way it does for statements.
    if isinstance(payload, dict) and not rows:
        message = str(payload.get("Error Message") or payload.get("message") or "")
        if message:
            plan = _is_plan_refusal(402, message) or any(
                phrase in message.lower() for phrase in PLAN_PHRASES)
            return (PLAN_LIMITED if plan else ERROR), [], f"200: {message[:200]}"
    return "", [row["date"] for row in rows if isinstance(row, dict) and row.get("date")], ""


def alphavantage(ticker: str, start: str, end: str, key: str) -> tuple[str, list[str], str]:
    """Full daily history. Answers HTTP 200 carrying an error body, so read the body."""
    url = ("https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&outputsize=full"
           f"&symbol={urllib.parse.quote(ticker)}&apikey={urllib.parse.quote(key)}")
    status, body = _get(url)
    failure = _classify_http(status, body)
    if failure:
        return failure[0], [], failure[1]
    try:
        payload = json.loads(body)
    except ValueError:
        return ERROR, [], f"HTTP {status}: {_text(body)}"
    for field in ("Error Message", "Information", "Note"):
        if field in payload:
            text = str(payload[field])[:200]
            lowered = text.lower()
            if "limit" in lowered or "frequency" in lowered:
                return RATE_LIMITED, [], text
            if any(phrase in lowered for phrase in PLAN_PHRASES):
                return PLAN_LIMITED, [], text
            return ERROR, [], text
    series = payload.get("Time Series (Daily)") or {}
    return "", [d for d in series if start <= d <= end], ""


VENDORS = {
    "stooq": (stooq, None),
    "polygon": (polygon, "POLYGON_API_KEY"),
    "finnhub": (finnhub, "FINNHUB_API_KEY"),
    "fmp": (fmp, "FMP_API_KEY"),
    "alphavantage": (alphavantage, "ALPHAVANTAGE_API_KEY"),
}


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def span_coverage(dates: list[str], listed: str, delisted: str) -> float:
    """Share of the name's membership span the vendor's history actually spans.

    Calendar span, not a session count: the probe must not need a trading
    calendar to say whether a decade of bars is there, and a vendor that serves
    the whole window with a gap in the middle is a question for the collector,
    not for "will they sell it to us at all".
    """
    if not dates or not listed or not delisted or delisted <= listed:
        return 0.0
    first, last = min(dates), max(dates)
    lo, hi = max(first, listed), min(last, delisted)
    if hi <= lo:
        return 0.0
    return _days(lo, hi) / _days(listed, delisted)


def _days(start: str, end: str) -> float:
    return max(
        (time.mktime(time.strptime(end, "%Y-%m-%d"))
         - time.mktime(time.strptime(start, "%Y-%m-%d"))) / 86400.0,
        1.0)


def classify_rows(dates: list[str], listed: str, delisted: str) -> tuple[str, float]:
    """FULL / PARTIAL / EMPTY, plus the share of the span for the record.

    FULL is decided at the edges and PARTIAL by the share: what makes a name
    usable is that the vendor's history reaches both ends of the membership,
    and what makes a shortfall worth reporting is how much of the middle is
    there.
    """
    if not dates:
        return SERVED_EMPTY, 0.0
    share = span_coverage(dates, listed, delisted)
    first, last = min(dates), max(dates)
    reaches_start = first <= listed or _days(listed, first) <= EDGE_TOLERANCE_DAYS
    reaches_end = last >= delisted or _days(last, delisted) <= EDGE_TOLERANCE_DAYS
    if reaches_start and reaches_end:
        return SERVED_FULL, share
    if share >= PARTIAL_COVERAGE:
        return SERVED_PARTIAL, share
    return SERVED_EMPTY, share


def vendor_verdict(departed: list[dict], control: list[dict]) -> str:
    """What the two cohorts together say about this vendor.

    The order matters and run #1 got it wrong by not having the middle case:
    polygon answered every departed name with "Your plan doesn't include this
    data timeframe" and was recorded as having REFUSED them. It had not. A
    vendor that names its price is a vendor that has the data, and that is a
    budget decision rather than a reason to go looking for another vendor.
    """
    control_served = [r for r in control if r["status"] in (SERVED_FULL, SERVED_PARTIAL)]
    control_plan_limited = [r for r in control if r["status"] == PLAN_LIMITED]
    if not control_served:
        # A control that is itself behind the paywall still says something: the
        # vendor is reachable and the plan is the obstacle, for live names too.
        return "PLAN_LIMITED" if control_plan_limited else "VENDOR_UNUSABLE"
    served = [r for r in departed if r["status"] in (SERVED_FULL, SERVED_PARTIAL)]
    if served:
        return "OPEN"
    if any(r["status"] == PLAN_LIMITED for r in departed):
        return "PLAN_LIMITED"
    return "DEPARTED_REFUSED"


# --------------------------------------------------------------------------- #
# Probe
# --------------------------------------------------------------------------- #
def pick_sample(members: list[dict], size: int) -> list[dict]:
    """A deterministic spread across the membership era, not the alphabet.

    Sorted by `delisted`, then evenly spaced: the 2013-2016 departures are the
    ones the coverage table says hurt most, and taking the first N tickers
    alphabetically would have sampled the 2020s almost exclusively.
    """
    ordered = sorted(members, key=lambda row: (row.get("delisted") or "", row["ticker"]))
    if size >= len(ordered):
        return ordered
    step = len(ordered) / size
    return [ordered[int(i * step)] for i in range(size)]


def ask(vendor: str, fetch, key: str, rows: list[dict], *, delay: float,
        retries: int = 2) -> list[dict]:
    out = []
    for index, row in enumerate(rows):
        ticker = row["ticker"]
        listed, delisted = row["listed"], row["delisted"]
        status, share, note, dates = ERROR, 0.0, "", []
        for attempt in range(retries + 1):
            if index or attempt:
                time.sleep(delay * (2 ** attempt if attempt else 1))
            failure, dates, note = fetch(ticker, listed, delisted, key)
            if failure == RATE_LIMITED and attempt < retries:
                continue
            if failure:
                status = failure
                break
            status, share = classify_rows(dates, listed, delisted)
            break
        out.append({
            "ticker": ticker, "listed": listed, "delisted": delisted,
            "status": status, "spanCoveredPct": round(100.0 * share, 2),
            "rows": len(dates),
            "firstDate": min(dates) if dates else None,
            "lastDate": max(dates) if dates else None,
            "note": note or None,
        })
        print(f"    {vendor:13} {ticker:8} {status:12} "
              f"span {round(100.0 * share, 1):5}%  rows {len(dates):5}"
              + (f"  {note}" if note else ""))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="us-delisted-prices.json")
    parser.add_argument("--cohort", default=str(COHORT))
    parser.add_argument("--sample", type=int, default=12,
                        help="departed names per vendor (0 = the whole cohort)")
    parser.add_argument("--delay", type=float, default=13.0,
                        help="seconds between requests; polygon's free tier is 5/min")
    parser.add_argument("--vendors", default=",".join(VENDORS))
    args = parser.parse_args(argv)

    cohort = json.loads(Path(args.cohort).read_text(encoding="utf-8"))
    members = cohort["members"]
    sample = pick_sample(members, args.sample or len(members))
    # The control names span the whole replay, so ask for the whole replay.
    control_rows = [{"ticker": t, "listed": "2013-01-02", "delisted": "2026-09-01"}
                    for t in CONTROL]
    print(f"cohort {len(members)} unpriced US members; asking about {len(sample)} "
          f"plus {len(control_rows)} controls")

    vendors = {}
    for name in [v.strip() for v in args.vendors.split(",") if v.strip()]:
        if name not in VENDORS:
            print(f"  unknown vendor: {name}")
            continue
        fetch, env = VENDORS[name]
        key = os.environ.get(env, "") if env else ""
        if env and not key:
            print(f"  {name}: NO_KEY ({env} unset)")
            vendors[name] = {"verdict": "NO_KEY", "keyEnv": env,
                             "departed": [], "control": []}
            continue
        print(f"  {name}: asking ...")
        control = ask(name, fetch, key, control_rows, delay=args.delay)
        departed = ask(name, fetch, key, sample, delay=args.delay)
        verdict = vendor_verdict(departed, control)
        served = [r for r in departed if r["status"] in (SERVED_FULL, SERVED_PARTIAL)]
        full = [r for r in departed if r["status"] == SERVED_FULL]
        priced = [r for r in departed if r["status"] == PLAN_LIMITED]
        vendors[name] = {
            "verdict": verdict, "keyEnv": env,
            "departedAsked": len(departed), "departedServed": len(served),
            "departedFullSpan": len(full), "departedPlanLimited": len(priced),
            "departedServedPct": round(100.0 * len(served) / len(departed), 2) if departed else None,
            # The sentence the vendor used to quote its price, kept verbatim:
            # it is the difference between a paywall and an outage.
            "planMessage": next((r["note"] for r in priced if r.get("note")), None),
            "control": control, "departed": departed,
        }
        print(f"  {name}: {verdict} — {len(served)}/{len(departed)} served, "
              f"{len(full)} with the full membership span"
              + (f", {len(priced)} behind the plan" if priced else ""))

    report = {
        "probe": "us-delisted-prices",
        "cohortSize": len(members),
        "sampled": len(sample),
        "coverageRule": {"fullEdgeToleranceDays": EDGE_TOLERANCE_DAYS,
                         "partialMinSpanShare": PARTIAL_COVERAGE},
        "controls": list(CONTROL),
        "vendors": vendors,
        "openVendors": sorted(n for n, v in vendors.items() if v["verdict"] == "OPEN"),
        # Vendors that have the data and want paying for it. Reported beside
        # the open ones because they are the answer to a different question,
        # and because a run with none of either means something else again.
        "payableVendors": sorted(n for n, v in vendors.items()
                                 if v["verdict"] == "PLAN_LIMITED"),
    }
    Path(args.output).write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {args.output}")
    print("open vendors:", ", ".join(report["openVendors"]) or "none")
    print("behind a plan:", ", ".join(report["payableVendors"]) or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
