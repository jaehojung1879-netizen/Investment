"""What can the KRX Open API key actually reach, and does it describe history?

WHY THIS EXISTS. `dataIntegrity` reports KR `membershipCoveragePct` 0.0 and
`survivorshipRisk` HIGH, because `build_universe_history.py` deliberately
writes no Korean rows: KRX-DELISTING is "every KRX name ever delisted", which
is not "was a member of the investable universe", and today's listed names
with no lower bound would admit a 2020 arrival into the 2013 cross-section.
Both were tried, both read as KNOWN membership, and the file reported 100%
coverage over a Korean cross-section it had invented.

WHAT WAS TRIED BEFORE THIS, AND WHY IT IS GONE. The public portal's statistics
loader (`data.krx.co.kr/comm/bldAttendant/getJsonData.cmd`, bld
`MDCSTAT00601`). Measured twice: every date answered HTTP 400 with the body
`LOGOUT`, first with no cookies and then with a real portal session
(`JSESSIONID` and `__smVisitorID` both set). The session was not the gate and
that route is not pursued further — it was scraping the screen when KRX
publishes an authenticated API for exactly this data.

WHAT THIS ASKS INSTEAD. The KRX Open API, with `KRX_API_KEY` in the
`AUTH_KEY` header. Two questions, in order of what they would buy:

  1. DATED INDEX MEMBERSHIP. Is there an endpoint giving KOSPI 200
     constituents as of a date? That is the literal thing
     `build_universe_history.py` says would close the Korean gap.

  2. DATED PER-ISSUE TRADING DATA — which may be worth MORE. The daily
     per-issue endpoints carry `MKTCAP` and `LIST_SHRS` for every issue that
     traded that day. The replay's KR universe is not literally the KOSPI 200;
     it is ~119 large names. A dated market-cap cross-section reconstructs
     that universe directly, by the rule the universe actually uses, instead
     of approximating it with an index's membership. And because it lists what
     TRADED that day, it carries issues that have since delisted — which is
     the pricing half of the gap (measured at 34.55% coverage from
     FinanceDataReader, 0.67% from Yahoo), not just the membership half.

THE ENDPOINT PATHS ARE A HYPOTHESIS, AND THAT IS THE POINT. This cannot be
tested from the dev container (`data.krx.co.kr` and `openapi.krx.co.kr` are
both outside the network allowlist), so rather than guess one path and report
its failure as the source's answer, it tries a CANDIDATE LIST and reports what
each one returned — status, shape, columns, sample. A 404 on a guessed path is
a fact about the guess; the run tells us which guesses were right.

THE TRAP, AND THE CHECK THAT CATCHES IT. A date-parameterised endpoint that
quietly ignores its date parameter returns a plausible list for 2013 that is
TODAY'S list. That is not a survivorship fix, it is survivorship bias with a
date stamped on it, and it sails through every count and format check. So the
decisive measurement is never "did a date return rows" but "do two dates ten
years apart return DIFFERENT issues, and does the older one hold issues the
newer one has lost". `membership_evidence` decides on exactly that.

WHAT A YES WOULD AND WOULD NOT BUY. Not a green integrity gate.
`universe_ready` wants both coverages at exactly 100.0 and neither reaches it
on free vendors, so this does not open promotion and must not be reported as
if it might. What it buys is that the Korean gap stops being unknown and
becomes a counted set of named companies — which is what any bias BOUND has to
be built on.

Nothing is written to the membership file. This reports.

Usage:  KRX_API_KEY=... python scripts/probe_krx_index_membership.py
        [--output krx-probe.json]
        [--dates 2013-01-02,2016-01-04,2020-01-02,2026-09-01]
        [--base https://data-dbg.krx.co.kr/svc/apis]
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
sys.path.insert(0, str(ROOT))

# The service root KRX publishes for the Open API. Overridable, because this
# is the one thing a wrong guess would make every endpoint look dead.
DEFAULT_BASE = "https://data-dbg.krx.co.kr/svc/apis"

# Candidates, most valuable first. `kind` says how the run should read a
# success: "issues" rows are a per-issue cross-section the membership check can
# be run on; "index" rows are index-level and only interesting if they carry
# constituents.
ENDPOINTS = [
    ("sto/stk_bydd_trd", "유가증권 일별매매정보 (종목별)", "issues"),
    ("sto/ksq_bydd_trd", "코스닥 일별매매정보 (종목별)", "issues"),
    ("sto/stk_isu_base_info", "유가증권 종목기본정보", "issues"),
    ("idx/kospi_dd_trd", "KOSPI 시리즈 지수 일별시세", "index"),
    ("idx/krx_dd_trd", "KRX 시리즈 지수 일별시세", "index"),
    ("idx/kosdaq_dd_trd", "KOSDAQ 시리즈 지수 일별시세", "index"),
]

# Columns that would carry the issue code, the name, and the two figures that
# make a dated market-cap universe possible. Checked by presence, not assumed.
CODE_KEYS = ("ISU_SRT_CD", "ISU_CD", "ISU_SRT_CD7")
NAME_KEYS = ("ISU_ABBRV", "ISU_NM", "ISU_KOR_NM")
MKTCAP_KEYS = ("MKTCAP", "MKT_CAP", "MKTCAP_AMT")
SHARES_KEYS = ("LIST_SHRS", "LIST_SHRS_CNT")


def to_pipeline_ticker(code: str) -> str:
    """`005930` -> `005930.KS`, the form `universe-history.json` is keyed by.

    KRX serves a bare six-digit code; the pipeline's KR tickers carry `.KS`
    because that is what the price vendor answers to, and the membership file
    is keyed by the pipeline's ticker. The conversion belongs with the source.
    """
    code = (code or "").strip()
    return f"{code}.KS" if code else ""


def _first(row: dict, keys) -> str | None:
    for key in keys:
        if row.get(key) not in (None, ""):
            return str(row[key]).strip()
    return None


# HOW THE KEY IS PRESENTED. Measured: every endpoint answered
# `{"respMsg":"Unauthorized Key","respCode":"401"}` with the key in an
# `AUTH_KEY` header. I read that as proof the header name was right — a
# service that never saw a key would say "missing", not "unauthorized" — but
# that is an inference about someone else's error strings, not a measurement,
# and it is exactly the kind of inference that cost two rounds on the portal.
# So the transport is a variable now: the same request goes out under each of
# these until one is served, and the run reports which. If they all fail
# identically the key really is unsubscribed and the answer is on the account
# side; if one differs, the transport was the bug.
AUTH_TRANSPORTS = (
    ("header:AUTH_KEY", "header", "AUTH_KEY"),
    ("header:authKey", "header", "authKey"),
    ("header:apiKey", "header", "apiKey"),
    ("query:AUTH_KEY", "query", "AUTH_KEY"),
    ("query:authKey", "query", "authKey"),
)


def resp_message(body: str) -> str | None:
    """KRX's own `respMsg`, or None when the body does not carry one.

    Reported as it came. The two messages seen so far mean different things
    and only the service can tell them apart for us.
    """
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    message = payload.get("respMsg")
    return str(message).strip() if message else None


def call(base: str, path: str, params: dict, auth_key: str,
         timeout: int = 40, transport: tuple = AUTH_TRANSPORTS[0]) -> dict:
    """One Open API call. What came back is recorded either way.

    A guessed path that 404s and a real path that refuses the key are
    different findings, and only the second says anything about the key.
    """
    _, kind, name = transport
    query = dict(params)
    headers = {"Accept": "application/json",
               "User-Agent": "InvestmentResearchDashboard/1.0"}
    if kind == "query":
        query[name] = auth_key
    else:
        headers[name] = auth_key
    url = f"{base.rstrip('/')}/{path}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"status": response.status, "raw": response.read()}
    except urllib.error.HTTPError as exc:
        body = exc.read()[:400].decode("utf-8", "replace")
        # CARRY WHAT THE SERVICE SAID, VERBATIM. The first run's label was
        # hardcoded to "Unauthorized Key" for any 401, and the second run's
        # bodies actually read `Unauthorized API Call` — a different statement
        # that the label was overwriting. The two are not the same finding:
        #
        #   respMsg "Unauthorized Key"        the key is not recognised
        #   respMsg "Unauthorized API Call"   the key IS recognised, and this
        #                                     call is not authorised for it
        #
        # Replacing a vendor's own words with our guess at them is how a
        # solved problem goes on looking unsolved, so the message is parsed
        # out of the body and reported as it came.
        message = resp_message(body)
        return {"status": exc.code,
                "error": (f"refused — {message}" if message
                          else f"HTTP {exc.code}"),
                "respMsg": message,
                "keyNotRecognised": bool(message and "key" in message.lower()),
                "serviceNotAuthorised": bool(
                    message and "api call" in message.lower()),
                "bodyHead": body}
    except Exception as exc:  # pragma: no cover - network dependent
        return {"status": None, "error": f"{type(exc).__name__}: {exc}"}


def parse_constituents(date: str, status: int, raw: bytes) -> dict:
    """Turn one response into issue codes, or into the reason it holds none."""
    text = raw.decode("utf-8", "replace")
    try:
        payload = json.loads(text)
    except ValueError:
        return {"date": date, "status": status,
                "error": "response was not JSON",
                "bodyHead": text[:400]}
    if not isinstance(payload, dict):
        return {"date": date, "status": status,
                "error": f"payload was {type(payload).__name__}, not an object",
                "bodyHead": text[:400]}
    key = next((k for k in ("OutBlock_1", "output", "OutBlock1") if k in payload), None)
    # A payload with no rows key at all is a DIFFERENT fact from one holding an
    # empty list: the first says the request was not understood, the second
    # that nothing traded that date. Reading the first as zero issues would
    # report a working endpoint as a market with no names.
    if key is None:
        return {"date": date, "status": status,
                "error": f"no rows key in payload keys {sorted(payload)[:8]}",
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
        code = _first(row, CODE_KEYS)
        if not code or code in names:
            continue
        codes.append(code)
        names[code] = _first(row, NAME_KEYS) or ""
    columns = sorted({k for row in rows if isinstance(row, dict) for k in row})
    # `count` and `codes` must describe the same set, or every overlap the
    # verdict rests on is computed against a number that counted duplicates.
    codes = sorted(set(codes))
    return {
        "date": date, "status": status, "count": len(codes),
        "codes": codes, "names": names,
        "rowsReturned": len(rows),
        "columns": columns,
        # The two that decide whether a dated market-cap universe is possible.
        "hasMarketCap": any(k in columns for k in MKTCAP_KEYS),
        "hasSharesOutstanding": any(k in columns for k in SHARES_KEYS),
        "payloadKeys": sorted(payload)[:8],
    }


def membership_evidence(snapshots: list[dict]) -> dict:
    """Is this history, or one cross-section wearing several dates?

    Two readings decide it and they fail differently:

    * ``oldestNewestOverlapPct`` — the share of the oldest list still in the
      newest. A date-parameterised endpoint that ignores its date returns
      100.0 here, with every count and format check passing.
    * ``departedMembers`` — issues in an old list and absent from the newest.
      These are the names survivorship bias deletes, so a source that offers
      none of them describes no history whatever its overlap.

    A source is only usable when the overlap is BELOW 100 and there is at
    least one departed name; the verdict says which reading refused it, so a
    partial answer is not read as a failure of the other half.
    """
    usable = [s for s in snapshots if not s.get("error") and s.get("count")]
    if len(usable) < 2:
        # A key the service refuses measured our credentials, not the data.
        # Reporting it as INSUFFICIENT_SNAPSHOTS would read as "KRX has no
        # dated cross-section" and retire a source that was never asked.
        failed = [s for s in snapshots if s.get("error")]
        if failed and all(s.get("keyNotRecognised") for s in failed):
            return {"verdict": "NOT_MEASURED_KEY_NOT_RECOGNISED",
                    "reason": "the service answered Unauthorized Key on every "
                              "request — it does not recognise the key, so "
                              "nothing here is a finding about KRX's dated data",
                    "respMsg": failed[0].get("respMsg"),
                    "snapshotsUsable": len(usable)}
        if failed and all(s.get("serviceNotAuthorised") for s in failed):
            return {"verdict": "NOT_MEASURED_SERVICE_NOT_AUTHORISED",
                    "reason": "the service answered Unauthorized API Call on "
                              "every request — the key is recognised and these "
                              "calls are not authorised for it, so the next "
                              "move is subscribing the key to these services, "
                              "not changing this code",
                    "respMsg": failed[0].get("respMsg"),
                    "snapshotsUsable": len(usable)}
        return {"verdict": "INSUFFICIENT_SNAPSHOTS",
                "reason": f"{len(usable)} dated cross-sections answered; two "
                          "are needed to tell history from a repeated snapshot",
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
            "issues — the date parameter is not changing the answer, so this is "
            "today's cross-section with a date stamped on it")
    elif not departed:
        verdict, reason = "NOT_POINT_IN_TIME", (
            "no issue in the oldest cross-section is absent from the newest; a "
            "real history always loses names")
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
    """How much of the replay's KR universe each dated cross-section holds.

    Not a pass/fail — a name the oldest cross-section does not hold may simply
    not have been listed then, which is the answer the replay wants. It is
    reported so the size of the KR fix is visible before it is attempted.
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
            "date": snap["date"], "issues": snap["count"],
            "universeNamesHeld": len(held),
            "universeNamesHeldPct": (round(100.0 * len(held) / len(wanted), 2)
                                     if wanted else None),
        })
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="krx-probe.json")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--dates",
                        default="2013-01-02,2016-01-04,2020-01-02,2026-09-01")
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args(argv)

    from pipeline import universe_lists

    auth_key = os.environ.get("KRX_API_KEY")
    if not auth_key:
        print("KRX_API_KEY is not set — the Open API cannot be reached. "
              "Nothing measured.")
        return 2

    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    print(f"KRX Open API at {args.base}")
    print(f"  {len(ENDPOINTS)} candidate endpoints x {len(dates)} dates")

    # Settle the transport on ONE endpoint and ONE date before spending the
    # whole matrix on it. Whichever is served wins; if none is, the first is
    # used so the run still reports the endpoints and their errors.
    probe_path = ENDPOINTS[0][0]
    probe_date = dates[-1].replace("-", "")
    transport = AUTH_TRANSPORTS[0]
    transport_results = {}
    print("  resolving how the key is presented:")
    for candidate in AUTH_TRANSPORTS:
        time.sleep(args.sleep)
        answer = call(args.base, probe_path, {"basDd": probe_date}, auth_key,
                      transport=candidate)
        served = not answer.get("error")
        transport_results[candidate[0]] = (
            {"served": True} if served else
            {"served": False, "error": answer.get("error"),
             "bodyHead": (answer.get("bodyHead") or "")[:120]})
        print(f"    {candidate[0]:<18} "
              + ("SERVED" if served
                 else f"{answer.get('error')}  {(answer.get('bodyHead') or '')[:80]}"))
        if served:
            transport = candidate
            break
    print(f"  using {transport[0]}\n")

    results: dict[str, dict] = {}
    for path, label, kind in ENDPOINTS:
        snapshots = []
        for i, date in enumerate(dates):
            if i or results:
                time.sleep(args.sleep)
            answer = call(args.base, path, {"basDd": date.replace("-", "")},
                          auth_key, transport=transport)
            if answer.get("error"):
                snap = {"date": date, "error": answer["error"],
                        "status": answer.get("status"),
                        "bodyHead": answer.get("bodyHead")}
            else:
                snap = parse_constituents(date, answer["status"], answer["raw"])
            snapshots.append(snap)
            if snap.get("error"):
                print(f"  {path:<24} {date}  ERROR {snap['error']}")
                if snap.get("bodyHead"):
                    print(f"      {snap['bodyHead'][:180]}")
            else:
                flags = []
                if snap.get("hasMarketCap"):
                    flags.append("MKTCAP")
                if snap.get("hasSharesOutstanding"):
                    flags.append("LIST_SHRS")
                print(f"  {path:<24} {date}  {snap['count']:>5} issues"
                      + (f"  [{' '.join(flags)}]" if flags else ""))
        answered = [s for s in snapshots if not s.get("error") and s.get("count")]
        results[path] = {
            "label": label, "kind": kind,
            "snapshots": [{k: v for k, v in s.items() if k != "names"}
                          for s in snapshots],
            "evidence": membership_evidence(snapshots) if kind == "issues" else None,
            "universeReach": (universe_reach(snapshots, universe_lists.KR)
                              if kind == "issues" else None),
            "columnsSeen": (answered[0].get("columns") if answered else []),
        }

    report = {
        "probe": "krx-open-api",
        "base": args.base,
        "dates": dates,
        "authTransport": transport[0],
        "authTransportsTried": transport_results,
        "endpoints": results,
    }
    Path(args.output).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

    print()
    for path, row in results.items():
        evidence = row.get("evidence") or {}
        verdict = evidence.get("verdict") or "—"
        print(f"  {path:<24} {verdict}")
        if evidence.get("reason"):
            print(f"      {evidence['reason']}")
        if evidence.get("oldestNewestOverlapPct") is not None:
            print(f"      {evidence['oldest']} vs {evidence['newest']}: "
                  f"{evidence['oldestNewestOverlapPct']}% overlap, "
                  f"{evidence['departedMembers']} departed, "
                  f"{evidence['joinedMembers']} joined")
            if evidence.get("departedSample"):
                print(f"      departed sample: {evidence['departedSample']}")
        for cell in (row.get("universeReach") or {}).get("byDate") or []:
            print(f"      {cell['date']}: {cell['issues']} issues, "
                  f"{cell['universeNamesHeld']}/"
                  f"{row['universeReach']['universeSize']} "
                  f"({cell['universeNamesHeldPct']}%) of the replay's KR universe")
        if row.get("columnsSeen"):
            print(f"      columns: {row['columnsSeen']}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
