"""Does KRX's short-selling screens actually answer, and under which bld codes?

WHY THIS PROBE EXISTS BEFORE ANY COLLECTOR CODE TRUSTS A FIELD. `pipeline/
kr_short_selling.py` is built from a WebSearch description of KRX's own
`MDCSTAT301` (daily short-sale trading) and `MDCSTAT305` (net short position)
screens — KRX's `data.krx.co.kr` domain itself is blocked from this sandbox's
WebFetch, so neither screen's actual `bld=` AJAX code nor its actual response
columns has been read directly. `BLD_TRADING`/`BLD_NET_POSITION` are `None` in
that module for exactly this reason: this probe is what would resolve them,
by trying documented-CONVENTION candidates against a live response and
reporting which one (if any) answers real short-sale figures.

THE CANDIDATES. `pykrx`'s own convention for a screen id like `MDCSTAT02302`
suggests the JSON `bld` for a page numbered `MDCSTAT301` sits in the
`dbms/MDC/STAT/srt/` family (the `srt` segment matches the page loader path
`comm/srt/srtLoader` this screen is served under, distinct from
`kr_investor_flow`'s `dbms/MDC/STAT/standard/` family). Several plausible
suffixes are tried rather than assumed, and every attempt's status and row
count is reported — a guessed bld that 404s or answers empty is a fact about
the guess, not about whether KRX serves this data at all.

SAME SESSION TREATMENT AS `probe_kr_investor_flow.py`, because the earlier
`data.krx.co.kr` LOGOUT finding applies to this loader too: a session cookie
plus Referer/X-Requested-With, established by first GETting the screen's own
page.

WHAT THIS ALSO CHECKS: THE BAN-WINDOW BOUNDARY. A request spanning
2023-11-04 to 2023-11-06 (the structural ban's start) should show real
short-sale volume on the 4th and none/a different regime marker on and after
the 5th — if the endpoint's own response distinguishes a banned day at all,
that is reported, because it would mean the source states more than this
module's own `regime_label` calendar does and the two could then be
cross-checked against each other.

Nothing is written to any collector store. This reports.

Usage:  python scripts/probe_kr_short_selling.py [--output probe.json]
        [--ticker 005930] [--recent-days 10]
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

from pipeline import kr_short_selling as KSS  # noqa: E402

BASE = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
TRADING_SCREEN_URL = ("https://data.krx.co.kr/comm/srt/srtLoader/index.cmd"
                      f"?screenId={KSS.SCREEN_TRADING}")
NET_POSITION_SCREEN_URL = ("https://data.krx.co.kr/comm/srt/srtLoader/index.cmd"
                          f"?screenId={KSS.SCREEN_NET_POSITION}")

HEADERS_BASE = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# Candidate bld codes, most-conventional first. Neither has been confirmed —
# see module docstring. Extending this list costs nothing; a wrong guess
# among several is just one more reported failure.
BLD_CANDIDATES_TRADING = (
    "dbms/MDC/STAT/srt/MDCSTAT30101", "dbms/MDC/STAT/srt/MDCSTAT301",
    "dbms/MDC/STAT/standard/MDCSTAT30101",
)
BLD_CANDIDATES_NET_POSITION = (
    "dbms/MDC/STAT/srt/MDCSTAT30501", "dbms/MDC/STAT/srt/MDCSTAT305",
    "dbms/MDC/STAT/standard/MDCSTAT30501",
)


def establish_session(screen_url: str) -> dict:
    request = urllib.request.Request(screen_url, headers=dict(HEADERS_BASE))
    cookies: dict[str, str] = {}
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            for header, value in response.getheaders():
                if header.lower() == "set-cookie":
                    crumb = value.split(";", 1)[0]
                    if "=" in crumb:
                        k, v = crumb.split("=", 1)
                        cookies[k.strip()] = v.strip()
            body_len = len(response.read())
        return cookies, {"status": response.status, "bytes": body_len}
    except Exception as exc:  # pragma: no cover - network dependent
        return {}, {"error": f"{type(exc).__name__}: {exc}"}


def call(bld: str, params: dict, cookies: dict, referer: str, timeout: int = 30) -> dict:
    body = dict(params)
    body["bld"] = bld
    encoded = urllib.parse.urlencode(body).encode("ascii")
    headers = dict(HEADERS_BASE)
    headers["Referer"] = referer
    headers["X-Requested-With"] = "XMLHttpRequest"
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    request = urllib.request.Request(BASE, data=encoded, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw, status = response.read(), response.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    except Exception as exc:  # pragma: no cover - network dependent
        return {"error": f"{type(exc).__name__}: {exc}"}
    text = raw.decode("utf-8", "replace")
    try:
        payload = json.loads(text)
    except ValueError:
        return {"status": status, "error": "non-JSON response", "bodyHead": text[:250]}
    return {"status": status, "payload": payload}


def parse_rows(payload) -> tuple[list[dict], str | None]:
    if not isinstance(payload, dict):
        return [], f"payload was {type(payload).__name__}, not an object"
    for key in ("OutBlock_1", "output", "block1", "list"):
        if key in payload and isinstance(payload[key], list):
            return payload[key], None
    if "message" in payload:
        return [], str(payload["message"])
    return [], f"no recognised rows key in {sorted(payload)[:8]}"


def try_candidates(candidates, params, cookies, referer) -> dict:
    attempts = {}
    for bld in candidates:
        time.sleep(0.6)
        answer = call(bld, params, cookies, referer)
        rows, error = ([], None)
        if "payload" in answer:
            rows, error = parse_rows(answer["payload"])
        attempts[bld] = {"status": answer.get("status"),
                         "error": answer.get("error") or error,
                         "rowCount": len(rows),
                         "sampleRow": rows[0] if rows else None}
        print(f"   {bld:<42} status={answer.get('status')} rows={len(rows)}"
              + ("" if rows else f" ({answer.get('error') or error})"))
        if rows:
            break
    return attempts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="kr-short-selling-probe.json")
    parser.add_argument("--ticker", default="005930")
    parser.add_argument("--recent-days", type=int, default=10)
    args = parser.parse_args(argv)

    import datetime as _dt
    end = _dt.date.today()
    start = end - _dt.timedelta(days=args.recent_days)
    params = {"isuCd": args.ticker, "strtDd": start.strftime("%Y%m%d"),
             "endDd": end.strftime("%Y%m%d")}

    report: dict = {"probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    print("1. trading screen session + candidates")
    cookies, session_result = establish_session(TRADING_SCREEN_URL)
    report["tradingSession"] = session_result
    trading_attempts = try_candidates(BLD_CANDIDATES_TRADING, params, cookies,
                                      TRADING_SCREEN_URL)
    report["tradingBldAttempts"] = trading_attempts

    print("\n2. net-position screen session + candidates")
    cookies2, session_result2 = establish_session(NET_POSITION_SCREEN_URL)
    report["netPositionSession"] = session_result2
    net_attempts = try_candidates(BLD_CANDIDATES_NET_POSITION, params, cookies2,
                                  NET_POSITION_SCREEN_URL)
    report["netPositionBldAttempts"] = net_attempts

    print(f"\n3. ban-window boundary — {KSS.regime_label('2023-11-04')} vs "
          f"{KSS.regime_label('2023-11-05')} (calendar only, no request)")
    report["banWindowCalendarCheck"] = {
        "2023-11-04": KSS.regime_label("2023-11-04"),
        "2023-11-05": KSS.regime_label("2023-11-05"),
        "2025-03-31": KSS.regime_label("2025-03-31"),
        "2025-04-01": KSS.regime_label("2025-04-01"),
    }

    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

    trading_served = any(a["rowCount"] for a in trading_attempts.values())
    net_served = any(a["rowCount"] for a in net_attempts.values())
    print("\n=== 판정 ===")
    print(f"  거래현황(MDCSTAT301) 서빙: {'예' if trading_served else '아니오'}")
    print(f"  순보유잔고(MDCSTAT305) 서빙: {'예' if net_served else '아니오'}")
    print(f"\nwrote {args.output}")
    return 0 if (trading_served or net_served) else 2


if __name__ == "__main__":
    raise SystemExit(main())
