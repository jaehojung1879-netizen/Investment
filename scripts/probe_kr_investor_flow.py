"""Does KRX's public statistics portal actually answer per-stock investor flow?

WHY A SECOND ATTEMPT AT A ROUTE ONE PROBE ALREADY TRIED. `probe_krx_index_
membership.py` tried `data.krx.co.kr/comm/bldAttendant/getJsonData.cmd` once,
bare, and every date came back `HTTP 400 LOGOUT` — read there as a dead end and
not pursued further, in favour of the KRX Open API (which then worked, for
price and membership data). But `LOGOUT` is a session-state answer, not a
data-does-not-exist answer, and a third-party survey of the Open API's own
catalogue (`seokhoonj/krx-openapi`, WebFetched 2026-09-24) states that the Open
API does not serve investor-type trading, foreign holdings, or short-selling at
all — so ruling out the portal on one bare attempt would leave this whole axis
unmeasured rather than measured-and-refused.

WHAT CHANGED. Researching `pykrx`'s own source (WebFetched 2026-09-24,
`pykrx/website/comm/webio.py`) shows the portal is a session-backed screen
target: a `requests.Session()`, a `Referer` header naming the screen the JSON
backs, and `X-Requested-With: XMLHttpRequest`. None of those were present in
the bare attempt. This probe sends all three and reports whether that alone
resolves the `LOGOUT` response — a single-variable isolation, in the style
`AGENTS.md`'s vendor-refusal invariants require: hold the endpoint and
parameters fixed, change only the session/header treatment, and report which
attempt was served.

WHAT IT ASKS, IN ORDER.

  1. SESSION ESTABLISHMENT. GET the screen page itself first (the URL the
     Referer header would name), to pick up whatever cookie the server sets
     before any getJsonData call — mirroring what a browser actually does
     before firing the AJAX request pykrx's `bld` classes wrap.
  2. THE GENERAL SCREEN (MDCSTAT02302) for one known-liquid ticker over a
     short recent window. If this returns rows with recognisable investor-type
     columns, per-stock flow exists at this route.
  3. THE DETAILED SCREEN (MDCSTAT02303) for the same ticker/window, to see
     whether the institution sub-category breakdown
     (금융투자/보험/투신/사모/은행/기타금융/연기금/기타법인) is actually
     served or whether that screen answers something else.
  4. HOW FAR BACK. A short window near today says nothing about 2013 — the
     portal may retain history differently from the Open API's own reach, so
     an old date is asked for separately and its answer (or refusal) is
     reported on its own.

Nothing is written to any collector store. This reports.

Usage:  python scripts/probe_kr_investor_flow.py [--output probe.json]
        [--ticker 005930] [--recent-days 10] [--old-date 2013-01-15]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import kr_investor_flow as KIF  # noqa: E402

BASE = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
# The screen the JSON call backs, for the Referer header. Any page under the
# statistics portal that hosts the 투자자별 거래실적(개별종목) widget will do;
# this is the one the search that found this axis linked directly.
SCREEN_URL = ("https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
              "?screenId=MDCSTAT023&locale=ko_KR")

HEADERS_BASE = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class Cookie:
    """The handful of Set-Cookie values a session needs, kept as a plain dict.

    Not `http.cookiejar`, because the portal's response headers are read once
    and replayed once; a jar's expiry and domain matching is machinery this
    probe does not need and would only hide what was actually received.
    """

    def __init__(self):
        self.pairs: dict[str, str] = {}

    def absorb(self, response) -> None:
        for header, value in response.getheaders():
            if header.lower() != "set-cookie":
                continue
            crumb = value.split(";", 1)[0]
            if "=" in crumb:
                key, val = crumb.split("=", 1)
                self.pairs[key.strip()] = val.strip()

    def header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.pairs.items())


def establish_session(cookie: Cookie) -> dict:
    """GET the screen page once, to pick up whatever cookie precedes the AJAX call."""
    request = urllib.request.Request(SCREEN_URL, headers=dict(HEADERS_BASE))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            cookie.absorb(response)
            body = response.read()
        return {"status": response.status, "bytes": len(body),
                "cookiesSet": sorted(cookie.pairs)}
    except Exception as exc:  # pragma: no cover - network dependent
        return {"error": f"{type(exc).__name__}: {exc}"}


def call(bld: str, params: dict, cookie: Cookie, with_session_headers: bool,
        timeout: int = 30) -> dict:
    """One POST to getJsonData.cmd, with or without the session treatment.

    ``with_session_headers`` is the single variable this probe isolates: on,
    it sends the Referer/X-Requested-With headers and the cookie collected by
    `establish_session`; off, it repeats exactly what the earlier bare attempt
    sent. Both are reported so the difference — if there is one — is visible
    rather than assumed.
    """
    body = dict(params)
    body["bld"] = bld
    encoded = urllib.parse.urlencode(body).encode("ascii")
    headers = dict(HEADERS_BASE)
    if with_session_headers:
        headers["Referer"] = SCREEN_URL
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        if cookie.pairs:
            headers["Cookie"] = cookie.header()
    request = urllib.request.Request(BASE, data=encoded, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:  # noqa: F821 - imported below
        raw = exc.read()
        status = exc.code
    except Exception as exc:  # pragma: no cover - network dependent
        return {"error": f"{type(exc).__name__}: {exc}"}
    text = raw.decode("utf-8", "replace")
    try:
        payload = json.loads(text)
    except ValueError:
        return {"status": status, "error": "non-JSON response",
                "bodyHead": text[:300]}
    return {"status": status, "payload": payload}


def parse_rows(payload: dict) -> tuple[list[dict], str | None]:
    """The portal's row list, under whichever key this screen answers with."""
    if not isinstance(payload, dict):
        return [], f"payload was {type(payload).__name__}, not an object"
    for key in ("OutBlock_1", "output", "block1", "list"):
        if key in payload and isinstance(payload[key], list):
            return payload[key], None
    if "message" in payload:
        return [], str(payload["message"])
    return [], f"no recognised rows key in {sorted(payload)[:8]}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="kr-investor-flow-probe.json")
    parser.add_argument("--ticker", default="005930", help="6-digit KRX code, no suffix")
    parser.add_argument("--recent-days", type=int, default=10)
    parser.add_argument("--old-date", default="2013-01-15")
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args(argv)

    report: dict = {"probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "base": BASE, "screenUrl": SCREEN_URL}

    cookie = Cookie()
    print("1. establishing a portal session")
    session_result = establish_session(cookie)
    report["sessionEstablishment"] = session_result
    print(f"   {session_result}")

    import datetime as _dt
    end = _dt.date.today()
    start = end - _dt.timedelta(days=args.recent_days)
    common_params = {"isuCd": args.ticker, "strtDd": start.strftime("%Y%m%d"),
                     "endDd": end.strftime("%Y%m%d"), "trdVolVal": "2", "askBid": "3"}

    print("\n2. isolating the session-header variable, one bare attempt and one dressed")
    isolation: dict = {}
    for label, dressed in (("bare_no_session_headers", False),
                           ("with_referer_and_cookie", True)):
        time.sleep(args.sleep)
        answer = call(KIF.BLD_GENERAL, common_params, cookie, dressed)
        rows, error = ([], None)
        if "payload" in answer:
            rows, error = parse_rows(answer["payload"])
        isolation[label] = {
            "status": answer.get("status"), "error": answer.get("error") or error,
            "rowCount": len(rows), "sampleRow": rows[0] if rows else None,
        }
        served = bool(rows) and not answer.get("error")
        print(f"   {label:<28} status={answer.get('status')} "
              f"rows={len(rows)} " + ("SERVED" if served else f"error={answer.get('error') or error}"))
    report["sessionIsolation"] = isolation
    session_headers_required = (
        isolation["bare_no_session_headers"]["rowCount"] == 0
        and isolation["with_referer_and_cookie"]["rowCount"] > 0)
    report["sessionHeadersRequired"] = session_headers_required

    # Whichever attempt was served decides the treatment for the rest of this run.
    dressed_worked = isolation["with_referer_and_cookie"]["rowCount"] > 0
    use_session_headers = dressed_worked or not isolation["bare_no_session_headers"]["rowCount"]

    print("\n3. detailed screen (MDCSTAT02303) — institution sub-category breakdown")
    time.sleep(args.sleep)
    detail_answer = call(KIF.BLD_DETAIL, common_params, cookie, use_session_headers)
    detail_rows, detail_error = ([], None)
    if "payload" in detail_answer:
        detail_rows, detail_error = parse_rows(detail_answer["payload"])
    detail_columns = sorted({k for row in detail_rows for k in row}) if detail_rows else []
    subcategories_present = [c for c in KIF.INSTITUTION_SUBCATEGORIES if c in detail_columns]
    report["detailScreen"] = {
        "status": detail_answer.get("status"),
        "error": detail_answer.get("error") or detail_error,
        "rowCount": len(detail_rows), "columns": detail_columns,
        "institutionSubcategoriesPresent": subcategories_present,
        "sampleRow": detail_rows[0] if detail_rows else None,
    }
    print(f"   rows={len(detail_rows)} sub-categories present: {subcategories_present}")

    print(f"\n4. reach into the past — a request for {args.old_date}")
    time.sleep(args.sleep)
    old_params = dict(common_params)
    old_params["strtDd"] = args.old_date.replace("-", "")
    old_params["endDd"] = args.old_date.replace("-", "")
    old_answer = call(KIF.BLD_GENERAL, old_params, cookie, use_session_headers)
    old_rows, old_error = ([], None)
    if "payload" in old_answer:
        old_rows, old_error = parse_rows(old_answer["payload"])
    report["historicalReach"] = {
        "requestedDate": args.old_date, "status": old_answer.get("status"),
        "error": old_answer.get("error") or old_error, "rowCount": len(old_rows),
        "sampleRow": old_rows[0] if old_rows else None,
    }
    print(f"   rows={len(old_rows)}"
          + (f" error={old_answer.get('error') or old_error}" if not old_rows else ""))

    general_sample = isolation["with_referer_and_cookie"]["sampleRow"] or {}
    general_columns = sorted(general_sample)
    matched = [canonical for canonical, aliases in KIF.GENERAL_FIELDS.items()
              if any(a in general_columns for a in aliases)]
    report["generalScreenFieldsMatched"] = matched

    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

    print("\n=== verdict ===")
    if session_headers_required:
        print("  the earlier bare LOGOUT was a transport problem, not a data absence — "
              "session headers resolve it")
    elif dressed_worked:
        print("  served with session headers; the bare attempt may also have been served "
              "this time (rate limiting or timing may explain the earlier LOGOUT)")
    else:
        print("  neither attempt was served — the portal refuses this run regardless of "
              "session treatment; the LOGOUT stands as a real refusal, not a fixed transport bug")
    print(f"\nwrote {args.output}")
    return 0 if (dressed_worked or isolation["bare_no_session_headers"]["rowCount"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
