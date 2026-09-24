"""Collect per-stock KR short-sale trading and net-position rows, budgeted.

NOT YET RUN — see `pipeline/kr_short_selling.py`'s module docstring: the bld
codes this collector calls are RESEARCH CANDIDATES tried in the order
`scripts/probe_kr_short_selling.py` tries them, never assumed to be right.
`--bld-trading`/`--bld-net-position` let a confirmed code from that probe's
run be pinned here once one is known; until then this collector tries the
same candidate list the probe does and uses whichever one a ticker's first
call is served under, for the rest of that run.

Same budget-and-resume discipline as `collect_kr_investor_flow.py`: a call
budget, a wall-clock budget, a `done` file of (ticker, date) pairs already
collected, and a run that stops on a refusal without marking that pair done.

Usage:
    python scripts/collect_kr_short_selling.py <store-dir>
        --universe-tickers 005930.KS,000660.KS,...
        [--start 2013-01-01] [--end today]
        [--max-calls 2000] [--max-minutes 240] [--pace 1.0]
        [--bld-trading dbms/MDC/STAT/srt/MDCSTAT30101]
        [--bld-net-position dbms/MDC/STAT/srt/MDCSTAT30501]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import collector_outcomes as OUT  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import kr_short_selling as KSS  # noqa: E402
from pipeline import universe as universe_mod  # noqa: E402
from pipeline.config import load_config  # noqa: E402

BASE = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
TRADING_SCREEN_URL = (f"https://data.krx.co.kr/comm/srt/srtLoader/index.cmd"
                      f"?screenId={KSS.SCREEN_TRADING}")
NET_POSITION_SCREEN_URL = (f"https://data.krx.co.kr/comm/srt/srtLoader/index.cmd"
                          f"?screenId={KSS.SCREEN_NET_POSITION}")
HEADERS_BASE = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded",
    "X-Requested-With": "XMLHttpRequest",
}
BLD_CANDIDATES_TRADING = (
    "dbms/MDC/STAT/srt/MDCSTAT30101", "dbms/MDC/STAT/srt/MDCSTAT301",
)
BLD_CANDIDATES_NET_POSITION = (
    "dbms/MDC/STAT/srt/MDCSTAT30501", "dbms/MDC/STAT/srt/MDCSTAT305",
)
DONE_NAME = "kr-short-selling-done.json"


class Refused(RuntimeError):
    pass


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
    except Exception as exc:  # pragma: no cover - network dependent
        raise Refused(f"session establishment failed: {exc}") from None
    return cookies


def call(bld: str, params: dict, cookies: dict, referer: str, timeout: int = 30) -> dict:
    body = dict(params)
    body["bld"] = bld
    encoded = urllib.parse.urlencode(body).encode("ascii")
    headers = dict(HEADERS_BASE)
    headers["Referer"] = referer
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    request = urllib.request.Request(BASE, data=encoded, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise Refused(f"HTTP {exc.code}") from None
    except Exception as exc:  # pragma: no cover - network dependent
        raise Refused(f"{type(exc).__name__}: {exc}") from None
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise Refused("response was not JSON") from None
    return payload if isinstance(payload, dict) else {}


def first_row(payload: dict) -> dict | None:
    for key in ("OutBlock_1", "output", "block1", "list"):
        rows = payload.get(key)
        if isinstance(rows, list) and rows:
            return rows[0]
    return None


def find_working_bld(candidates, params, cookies, referer) -> str | None:
    for bld in candidates:
        try:
            payload = call(bld, params, cookies, referer)
        except Refused:
            continue
        if first_row(payload):
            return bld
    return None


def trading_days(start: str, end: str) -> list[str]:
    cursor, last = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    out = []
    while cursor <= last:
        if cursor.weekday() < 5:
            out.append(cursor.isoformat())
        cursor += dt.timedelta(days=1)
    return out


def load_done(store: Path) -> set[str]:
    path = store / DONE_NAME
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    return {str(d) for d in raw} if isinstance(raw, list) else set()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument("--universe-tickers", default=None)
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-calls", type=int, default=2000)
    parser.add_argument("--max-minutes", type=float, default=240.0)
    parser.add_argument("--pace", type=float, default=1.0)
    parser.add_argument("--bld-trading", default=None)
    parser.add_argument("--bld-net-position", default=None)
    args = parser.parse_args(argv)

    if args.universe_tickers:
        tickers = [t.strip() for t in args.universe_tickers.split(",") if t.strip()]
    else:
        cfg, _ = load_config()
        universe, _ = universe_mod.resolve(cfg)
        tickers = sorted(universe.get("KR") or [])
    if not tickers:
        print("ERROR: no KR tickers to collect.")
        return 1

    store = Path(args.store_dir)
    store.mkdir(parents=True, exist_ok=True)
    end = args.end or dt.date.today().isoformat()
    dates = trading_days(args.start, end)
    done = load_done(store)
    pending = [(t, d) for d in dates for t in tickers if f"{t}:{d}" not in done]
    print(f"KR 공매도 대상 {len(tickers)}종목 x {len(dates)}거래일 · "
          f"남은 {len(pending):,}")

    try:
        trading_cookies = establish_session(TRADING_SCREEN_URL)
        netpos_cookies = establish_session(NET_POSITION_SCREEN_URL)
    except Refused as exc:
        print(f"ERROR: 세션을 만들지 못했습니다 — {exc}")
        return 1

    probe_ticker = tickers[0].split(".")[0]
    probe_params = {"isuCd": probe_ticker, "strtDd": args.start.replace("-", ""),
                    "endDd": args.start.replace("-", "")}
    bld_trading = args.bld_trading or find_working_bld(
        BLD_CANDIDATES_TRADING, probe_params, trading_cookies, TRADING_SCREEN_URL)
    bld_netpos = args.bld_net_position or find_working_bld(
        BLD_CANDIDATES_NET_POSITION, probe_params, netpos_cookies, NET_POSITION_SCREEN_URL)
    if not bld_trading and not bld_netpos:
        print("ERROR: 어떤 후보 bld 코드도 서빙되지 않았습니다 — "
              "probe_kr_short_selling.py를 먼저 실행해 확인이 필요합니다.")
        return 1
    print(f"사용할 bld — trading={bld_trading} netPosition={bld_netpos}")

    trading_shards: dict[int, list[dict]] = {}
    netpos_shards: dict[int, list[dict]] = {}
    for path in sorted(store.glob("kr-short-trading-*.jsonl.gz")):
        trading_shards[int(path.stem.split("-")[-1].split(".")[0])] = HS.read_jsonl(path)
    for path in sorted(store.glob("kr-short-netpos-*.jsonl.gz")):
        netpos_shards[int(path.stem.split("-")[-1].split(".")[0])] = HS.read_jsonl(path)

    deadline = time.time() + args.max_minutes * 60
    calls = 0
    fresh_trading: dict[int, list[dict]] = {}
    fresh_netpos: dict[int, list[dict]] = {}
    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stop_reason = "WORK_LIST_EXHAUSTED"

    for ticker, date in pending:
        if calls >= args.max_calls:
            stop_reason = "CALL_BUDGET_SPENT"
            break
        if time.time() >= deadline:
            stop_reason = "TIME_BUDGET_SPENT"
            break
        params = {"isuCd": ticker.split(".")[0], "strtDd": date.replace("-", ""),
                 "endDd": date.replace("-", "")}
        try:
            if bld_trading:
                payload = call(bld_trading, params, trading_cookies, TRADING_SCREEN_URL)
                calls += 1
                record, _ = KSS.build_trading_record(
                    ticker=ticker, date=date, row=first_row(payload) or {},
                    collected_at=collected_at)
                if record:
                    fresh_trading.setdefault(int(date[:4]), []).append(record)
                time.sleep(args.pace)
            if bld_netpos:
                payload = call(bld_netpos, params, netpos_cookies, NET_POSITION_SCREEN_URL)
                calls += 1
                record, _ = KSS.build_net_position_record(
                    ticker=ticker, date=date, row=first_row(payload) or {},
                    collected_at=collected_at)
                if record:
                    fresh_netpos.setdefault(int(date[:4]), []).append(record)
                time.sleep(args.pace)
        except Refused as exc:
            print(f"중단: {ticker} {date} — {exc}")
            stop_reason = f"REFUSED: {exc}"
            break
        done.add(f"{ticker}:{date}")
        if calls % 100 == 0:
            print(f"  {calls}콜 · trading {sum(len(v) for v in fresh_trading.values())} · "
                  f"netpos {sum(len(v) for v in fresh_netpos.values())}")

    changed = 0
    written = 0
    for year, rows in sorted(fresh_trading.items()):
        merged = trading_shards.get(year, []) + rows
        if HS.write_shard(KSS.shard_path(store, year, "trading"), merged):
            changed += 1
        written += len(rows)
    for year, rows in sorted(fresh_netpos.items()):
        merged = netpos_shards.get(year, []) + rows
        if HS.write_shard(KSS.shard_path(store, year, "netpos"), merged):
            changed += 1
        written += len(rows)

    (store / DONE_NAME).write_text(json.dumps(sorted(done), indent=0) + "\n", encoding="utf-8")
    outcome = OUT.run_outcome(stop_reason=stop_reason, calls=calls, written=written)
    manifest = {
        "contract": "KR_SHORT_SELLING_RAW_V1", "updatedAt": collected_at,
        "bldUsed": {"trading": bld_trading, "netPosition": bld_netpos},
        "thisRun": {"calls": calls, "rowsWritten": written, "shardsChanged": changed,
                    "stopReason": stop_reason, "outcome": outcome},
    }
    (store / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n=== 이번 실행 ===\n  호출 {calls} · 기록 {written}건 · 종료 사유 {stop_reason} · "
          f"outcome {outcome}")

    if OUT.is_reportable_failure(outcome, written=written):
        print(f"거부: 소스가 이번 실행에서 아무 진행도 허용하지 않았습니다 (outcome={outcome}). "
              "success로 보고하지 않습니다.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
