"""Does KRX serve DATED KOSPI 200 membership, or just today's list on any date?

WHY THIS EXISTS. `dataIntegrity` reports KR `membershipCoveragePct` 0.0 and
`survivorshipRisk` HIGH, because `build_universe_history.py` deliberately
writes no Korean rows: KRX-DELISTING is "every KRX name ever delisted", which
is not "was a member of the investable universe", and today's listed names
with no lower bound would admit a 2020 arrival into the 2013 cross-section.
Both were tried, both read as KNOWN membership, and the file reported 100%
coverage over a Korean cross-section it had invented. What would actually
close the gap is a dated KOSPI 200 constituent history. This measures whether
KRX's own public data portal is one.

WHAT THE ENDPOINT CLAIMS TO BE. `data.krx.co.kr`'s statistics loader serves
지수구성종목 (index constituents) under `MDCSTAT00601`, taking a trade date
(`trdDd`) and an index (KOSPI 200 is series 1, index 028). If it answers for
2013 with the names that were members in 2013, the Korean half of the
membership file follows directly and this is the whole fix.

THE TRAP, AND THE CHECK THAT CATCHES IT. A date-parameterised endpoint that
quietly ignores its date parameter — or falls back to the latest available
list for any date it does not hold — returns a plausible 200-name list for
2013 that is TODAY'S list. That is not a survivorship fix, it is survivorship
bias with a date stamped on it, and it would sail through every count-based
check: right size, right format, right tickers. It is the same failure the
KRX-DELISTING attempt made, and nothing caught that one either, because the
correctness was resting on a vendor's failure rather than on a measurement.

So the decisive measurement here is not "did a date return 200 names" but
"do two dates ten years apart return DIFFERENT names". `membership_evidence`
reports the pairwise overlap, and a source whose oldest and newest lists are
identical is REFUSED here rather than discovered later in a replay.

A second, positive check: names present in an old list and ABSENT from the
newest one. Those are precisely the departed members survivorship deletes —
if the source has none of them it is not describing history, whatever its
overlap says.

WHAT A YES WOULD AND WOULD NOT BUY. Not a green integrity gate. The KR
delisting-coverage measurement (2026-08-30, README) already settled the other
half: of the KOSPI names that left after the replay start, FinanceDataReader
prices 34.55% (19/55, 95% CI [23.36, 47.75]) and Yahoo 0.67%. A restored
former member the panel cannot price is `membership known - no price`, which
drops out of the cross-section exactly as before, so perfect membership takes
KR unvouched from 100% to roughly 40% and stops. `universe_ready` wants both
coverages at 100.0, so this does not open promotion and must not be reported
as if it might.

What it does buy is the OTHER thing the repo currently cannot say. Today the
Korean half is undescribed, so every KR observation carries
SURVIVORSHIP_BIAS_UNRESOLVED and the size of the bias is unknown. With dated
membership the gap becomes a counted set of named companies, which is what any
bias BOUND has to be built on. `build_universe_history.py` states the open
question as "what would close it is a dated KOSPI 200 constituent history;
until there is one, the honest state is a measured gap" — this answers whether
there is one.

Nothing is written to the membership file. This reports.

Usage:  python scripts/probe_krx_index_membership.py [--output krx-probe.json]
        [--dates 2013-01-02,2016-01-04,2020-01-02,2026-09-01]
        [--index-series 1 --index-code 028]
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
LOADER = ("http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"
          "?menuId=MDC0201020506")
BLD = "dbms/MDC/STAT/standard/MDCSTAT00601"
# A browser User-Agent is not a disguise here: the portal's loader sets the
# session this endpoint reads, and a bare urllib default is answered with the
# HTML shell instead of JSON. The probe records exactly what came back either
# way rather than pretending the shape was fine.
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# MEASURED, not guessed. The first run sent a Referer and no cookies, and every
# one of the five dates came back HTTP 400 with the body `LOGOUT` — the portal's
# answer to a request carrying no session, not a statement about the dates. The
# session is established by loading the statistics page the endpoint belongs to,
# which sets the cookies this then replays. A probe that reported that 400 as
# "KRX has no dated membership" would have retired a usable source on its own
# bug, so the session is opened first and the probe says whether it was.
LOGOUT_MARKERS = ("LOGOUT", "로그아웃")


def open_session(timeout: int = 30) -> tuple[urllib.request.OpenerDirector, dict]:
    """Load the portal page so the data endpoint sees a session.

    Returns the opener and what happened, because "the session could not be
    opened" and "the endpoint refused a session it had" are different findings
    and only the second says anything about the data.
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", USER_AGENT),
                         ("Accept-Language", "ko-KR,ko;q=0.9,en;q=0.8")]
    request = urllib.request.Request(LOADER)
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            response.read(2048)
    except Exception as exc:  # pragma: no cover - network dependent
        return opener, {"opened": False, "error": f"{type(exc).__name__}: {exc}"}
    names = sorted(cookie.name for cookie in jar)
    return opener, {"opened": bool(names), "status": status, "cookies": names}

# KRX serves codes without a suffix; the pipeline's KR tickers carry `.KS`
# because that is what the price vendor answers to. The membership file is
# keyed by the pipeline's ticker, so the conversion belongs with the source.
def to_pipeline_ticker(code: str) -> str:
    """`005930` -> `005930.KS`, the form `universe-history.json` is keyed by."""
    code = (code or "").strip()
    return f"{code}.KS" if code else ""


def fetch_constituents(date: str, *, index_series: str = "1",
                       index_code: str = "028", timeout: int = 30,
                       opener: urllib.request.OpenerDirector | None = None) -> dict:
    """One dated constituent list, or the reason there is none.

    Returns the raw shape as well as the parse, because "it answered with an
    HTML block page" and "it answered with an empty list" are different facts
    about the source and only one of them is fixable by asking differently.
    """
    trd = date.replace("-", "")
    body = urllib.parse.urlencode({
        "bld": BLD,
        "locale": "ko_KR",
        "indIdx": index_series,
        "indIdx2": index_code,
        "trdDd": trd,
        "money": "1",
        "csvxls_isNo": "false",
    }).encode("utf-8")
    request = urllib.request.Request(BASE, data=body, headers={
        "User-Agent": USER_AGENT,
        "Referer": LOADER,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    })
    send = (opener.open if opener is not None else urllib.request.urlopen)
    try:
        with send(request, timeout=timeout) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()[:400].decode("utf-8", "replace")
        # Name this one rather than leaving it as a bare 400. It is the portal
        # saying "no session", which is a fact about the request, not the date.
        no_session = any(marker in body for marker in LOGOUT_MARKERS)
        return {"date": date,
                "error": ("no session — the portal answered LOGOUT"
                          if no_session else f"HTTP {exc.code}"),
                "httpStatus": exc.code, "noSession": no_session,
                "bodyHead": body}
    except Exception as exc:  # pragma: no cover - network dependent
        return {"date": date, "error": f"{type(exc).__name__}: {exc}"}
    return parse_constituents(date, status, raw)


def parse_constituents(date: str, status: int, raw: bytes) -> dict:
    """Turn one response into codes, or into the reason it holds none."""
    text = raw.decode("utf-8", "replace")
    try:
        payload = json.loads(text)
    except ValueError:
        return {"date": date, "status": status,
                "error": "response was not JSON (block page or HTML shell?)",
                "bodyHead": text[:400]}
    key = next((k for k in ("output", "OutBlock_1") if k in payload), None)
    # A payload with no rows key at all is a DIFFERENT fact from one holding an
    # empty list: the first says the request was not understood, the second
    # that the index had no members on that date. Reading the first as zero
    # constituents would report a working endpoint as a market with no names.
    if key is None:
        return {"date": date, "status": status,
                "error": f"no constituent rows in payload keys {sorted(payload)[:8]}",
                "bodyHead": text[:400]}
    rows = payload.get(key)
    if not isinstance(rows, list):
        return {"date": date, "status": status,
                "error": f"payload key {key!r} was {type(rows).__name__}, not a list",
                "bodyHead": text[:400]}
    codes: list[str] = []
    names: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("ISU_SRT_CD") or row.get("ISU_CD") or "").strip()
        if not code or code in names:
            continue
        codes.append(code)
        names[code] = str(row.get("ISU_ABBRV") or row.get("ISU_NM") or "").strip()
    # `count` and `codes` must describe the same set, or every overlap the
    # verdict rests on is computed against a number that counted duplicates.
    codes = sorted(set(codes))
    return {"date": date, "status": status, "count": len(codes),
            "codes": codes, "names": names,
            "payloadKeys": sorted(payload)[:8]}


def membership_evidence(snapshots: list[dict]) -> dict:
    """Is this history, or one list wearing several dates?

    Two readings decide it and they fail differently:

    * ``oldestNewestOverlapPct`` — the share of the oldest list still in the
      newest. A date-parameterised endpoint that ignores its date returns
      100.0 here, with every count and format check passing.
    * ``departedMembers`` — names in an old list and absent from the newest.
      These are the names survivorship bias deletes, so a source that offers
      none of them describes no history whatever its overlap.

    A source is only usable when the overlap is BELOW 100 and there is at
    least one departed member; the verdict says which reading refused it, so
    a partial answer is not read as a failure of the other half.
    """
    usable = [s for s in snapshots if not s.get("error") and s.get("count")]
    if len(usable) < 2:
        # A run that never held a session measured the request, not the source.
        # Reporting it as INSUFFICIENT_SNAPSHOTS would read as "KRX could not
        # answer", and the next person would drop a usable source on our bug.
        failed = [s for s in snapshots if s.get("error")]
        if failed and all(s.get("noSession") for s in failed):
            return {"verdict": "NOT_MEASURED_NO_SESSION",
                    "reason": "every request was answered LOGOUT — the probe "
                              "held no portal session, so nothing here is a "
                              "finding about KRX's dated membership",
                    "snapshotsUsable": len(usable)}
        return {"verdict": "INSUFFICIENT_SNAPSHOTS",
                "reason": f"{len(usable)} dated lists answered; two are needed "
                          "to tell history from a repeated snapshot",
                "snapshotsUsable": len(usable)}
    usable.sort(key=lambda s: s["date"])
    oldest, newest = set(usable[0]["codes"]), set(usable[-1]["codes"])
    departed = sorted(oldest - newest)
    joined = sorted(newest - oldest)
    overlap = round(100.0 * len(oldest & newest) / len(oldest), 2) if oldest else None

    pairwise = []
    for earlier, later in zip(usable, usable[1:]):
        a, b = set(earlier["codes"]), set(later["codes"])
        pairwise.append({
            "from": earlier["date"], "to": later["date"],
            "overlapPct": round(100.0 * len(a & b) / len(a), 2) if a else None,
            "left": len(a - b), "joined": len(b - a),
        })

    if overlap == 100.0 and not departed:
        verdict, reason = "NOT_POINT_IN_TIME", (
            f"{usable[0]['date']} and {usable[-1]['date']} returned the same "
            "names — the date parameter is not changing the answer, so this is "
            "today's list with a date stamped on it")
    elif not departed:
        verdict, reason = "NOT_POINT_IN_TIME", (
            "no name in the oldest list is absent from the newest; a real "
            "membership history always loses members")
    else:
        verdict, reason = "POINT_IN_TIME", None
    return {
        "verdict": verdict,
        "reason": reason,
        "snapshotsUsable": len(usable),
        "oldest": usable[0]["date"], "newest": usable[-1]["date"],
        "oldestCount": len(oldest), "newestCount": len(newest),
        "oldestNewestOverlapPct": overlap,
        "departedMembers": len(departed),
        "departedSample": [to_pipeline_ticker(c) for c in departed[:10]],
        "joinedMembers": len(joined),
        "pairwise": pairwise,
    }


def universe_reach(snapshots: list[dict], universe: list[str]) -> dict:
    """How much of the replay's KR universe the oldest list can vouch for.

    Not a pass/fail — a name the oldest list does not hold may simply not have
    been a member then, which is the answer the replay wants. It is reported so
    the size of the KR membership fix is visible before it is attempted.
    """
    usable = sorted((s for s in snapshots if not s.get("error") and s.get("count")),
                    key=lambda s: s["date"])
    if not usable:
        return {"measured": False}
    wanted = set(universe)
    out = {"measured": True, "universeSize": len(wanted), "byDate": []}
    for snap in usable:
        held = {to_pipeline_ticker(c) for c in snap["codes"]} & wanted
        out["byDate"].append({
            "date": snap["date"], "constituents": snap["count"],
            "universeNamesHeld": len(held),
            "universeNamesHeldPct": (round(100.0 * len(held) / len(wanted), 2)
                                     if wanted else None),
        })
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="krx-probe.json")
    parser.add_argument("--dates",
                        default="2013-01-02,2016-01-04,2020-01-02,2024-01-02,2026-09-01")
    parser.add_argument("--index-series", default="1")
    parser.add_argument("--index-code", default="028")
    parser.add_argument("--sleep", type=float, default=1.5,
                        help="pause between calls; this is a public portal")
    args = parser.parse_args(argv)

    from pipeline import universe_lists

    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    print(f"KRX 지수구성종목 (series {args.index_series} / index "
          f"{args.index_code}) on {len(dates)} dates")
    opener, session = open_session()
    if session.get("opened"):
        print(f"  session cookies: {session['cookies']}")
    else:
        print(f"  WARNING: no session cookie ({session.get('error') or session}); "
              "the endpoint will answer LOGOUT and nothing below is about the data")
    snapshots = []
    for i, date in enumerate(dates):
        if i:
            time.sleep(args.sleep)
        snap = fetch_constituents(date, index_series=args.index_series,
                                  index_code=args.index_code, opener=opener)
        snapshots.append(snap)
        if snap.get("error"):
            print(f"  {date}  ERROR {snap['error']}")
            if snap.get("bodyHead"):
                print(f"    {snap['bodyHead'][:200]}")
        else:
            sample = ", ".join(snap["codes"][:5])
            print(f"  {date}  {snap['count']:>4} names  [{sample}]")

    evidence = membership_evidence(snapshots)
    reach = universe_reach(snapshots, universe_lists.KR)
    report = {
        "probe": "krx-index-membership",
        "endpoint": BASE, "bld": BLD,
        "indexSeries": args.index_series, "indexCode": args.index_code,
        "dates": dates,
        "session": session,
        # Names are large and not what the decision turns on; the codes are.
        "snapshots": [{k: v for k, v in s.items() if k != "names"} for s in snapshots],
        "evidence": evidence,
        "universeReach": reach,
    }
    Path(args.output).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

    print()
    print(f"verdict: {evidence['verdict']}")
    if evidence.get("reason"):
        print(f"  {evidence['reason']}")
    if evidence.get("oldestNewestOverlapPct") is not None:
        print(f"  {evidence['oldest']} vs {evidence['newest']}: "
              f"{evidence['oldestNewestOverlapPct']}% overlap, "
              f"{evidence['departedMembers']} departed, "
              f"{evidence['joinedMembers']} joined")
        if evidence.get("departedSample"):
            print(f"  departed sample: {evidence['departedSample']}")
    for row in reach.get("byDate") or []:
        print(f"  {row['date']}: {row['constituents']} constituents, "
              f"{row['universeNamesHeld']}/{reach['universeSize']} "
              f"({row['universeNamesHeldPct']}%) of the replay's KR universe")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
