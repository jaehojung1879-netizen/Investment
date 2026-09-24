"""Collect per-stock KR investor-type net trading, one budgeted slice per run.

NOT YET RUN. `scripts/probe_kr_investor_flow.py` has not been executed against
the live portal from this sandbox (outbound network is blocked here; see
`AGENTS.md`'s vendor-refusal invariants for the general pattern). This
collector is built against the response shape that probe is designed to
confirm — `pipeline.kr_investor_flow`'s field aliases and bld codes, sourced
from researching `pykrx`'s own implementation (see that module's docstring) —
and it must not be scheduled until a `workflow_dispatch` run of the probe
confirms the portal answers as expected under session headers.

BUDGETED AND RESUMABLE, same discipline as `collect_dart_fundamentals.py` and
`collect_krx_universe_snapshots.py`: a call budget and a wall-clock budget, a
`done` file recording which trading dates are already collected, and a run
that stops on a refusal without marking that date done so the next run tries
it again rather than recording a refusal as an answer.

ONE CALL PER TICKER PER DATE, PER SCREEN. The general screen (MDCSTAT02302)
and the detailed screen (MDCSTAT02303) are two separate calls; a name's row
for one date needs both to get the institution sub-category breakdown, so the
budget is spent two calls at a time per ticker-date rather than one.

Usage:
    python scripts/collect_kr_investor_flow.py <store-dir>
        --universe-tickers 005930.KS,000660.KS,...
        [--start 2013-01-01] [--end today]
        [--max-calls 2000] [--max-minutes 240] [--pace 1.0]
        [--skip-detail]
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
from pipeline import kr_investor_flow as KIF  # noqa: E402
from pipeline import universe as universe_mod  # noqa: E402
from pipeline.config import load_config  # noqa: E402

BASE = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
SCREEN_URL = ("https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
              "?screenId=MDCSTAT023&locale=ko_KR")
HEADERS_BASE = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": SCREEN_URL,
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded",
}
DONE_NAME = "kr-investor-flow-done.json"


class Refused(RuntimeError):
    """The portal declined. Not a fact about the data, so nothing is marked done."""


def establish_session() -> dict:
    """One GET of the screen page, for whatever cookie precedes the AJAX call."""
    request = urllib.request.Request(SCREEN_URL, headers=dict(HEADERS_BASE))
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


def call(bld: str, params: dict, cookies: dict, timeout: int = 30) -> dict:
    body = dict(params)
    body["bld"] = bld
    encoded = urllib.parse.urlencode(body).encode("ascii")
    headers = dict(HEADERS_BASE)
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    request = urllib.request.Request(BASE, data=encoded, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise Refused(f"HTTP {exc.code}: {exc.read()[:200]!r}") from None
    except Exception as exc:  # pragma: no cover - network dependent
        raise Refused(f"{type(exc).__name__}: {exc}") from None
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise Refused("response was not JSON") from None
    if not isinstance(payload, dict):
        raise Refused(f"payload was {type(payload).__name__}, not an object")
    return payload


def row_for(payload: dict) -> dict | None:
    for key in ("OutBlock_1", "output", "block1", "list"):
        rows = payload.get(key)
        if isinstance(rows, list) and rows:
            return rows[0]
    return None


def trading_days(start: str, end: str) -> list[str]:
    first = dt.date.fromisoformat(start)
    last = dt.date.fromisoformat(end)
    out = []
    cursor = first
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


def save_done(store: Path, done: set[str]) -> None:
    (store / DONE_NAME).write_text(json.dumps(sorted(done), indent=0) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument("--universe-tickers", default=None,
                        help="comma-separated pipeline tickers, e.g. 005930.KS,000660.KS; "
                             "defaults to config.json's KR universe")
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-calls", type=int, default=2000)
    parser.add_argument("--max-minutes", type=float, default=240.0)
    parser.add_argument("--pace", type=float, default=1.0)
    parser.add_argument("--skip-detail", action="store_true",
                        help="collect only the general screen (no institution breakdown), "
                             "halving the call cost per ticker-date")
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

    pending = [(ticker, date) for date in dates for ticker in tickers
              if f"{ticker}:{date}" not in done]
    print(f"KR 투자자별 순매수 대상 {len(tickers)}종목 x {len(dates)}거래일 = "
          f"{len(tickers) * len(dates):,}쌍 · 이미 완료 {len(done):,} · 남은 {len(pending):,}")

    try:
        cookies = establish_session()
    except Refused as exc:
        print(f"ERROR: 세션을 만들지 못했습니다 — {exc}")
        return 1

    shards: dict[int, list[dict]] = {}
    for path in sorted(store.glob("kr-investor-flow-*.jsonl.gz")):
        try:
            year = int(path.stem.split("-")[-1].split(".")[0])
        except ValueError:
            continue
        shards[year] = HS.read_jsonl(path)

    deadline = time.time() + args.max_minutes * 60
    calls = 0
    fresh: dict[int, list[dict]] = {}
    refused_count = 0
    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stop_reason = "WORK_LIST_EXHAUSTED"

    for ticker, date in pending:
        if calls >= args.max_calls:
            stop_reason = "CALL_BUDGET_SPENT"
            break
        if time.time() >= deadline:
            stop_reason = "TIME_BUDGET_SPENT"
            break
        code = ticker.split(".")[0]
        params = {"isuCd": code, "strtDd": date.replace("-", ""),
                 "endDd": date.replace("-", ""), "trdVolVal": "2", "askBid": "3"}
        try:
            general_payload = call(KIF.BLD_GENERAL, params, cookies)
            calls += 1
            time.sleep(args.pace)
            detail_row = None
            if not args.skip_detail:
                detail_payload = call(KIF.BLD_DETAIL, params, cookies)
                calls += 1
                detail_row = row_for(detail_payload)
                time.sleep(args.pace)
        except Refused as exc:
            print(f"중단: {ticker} {date} — {exc}")
            stop_reason = f"REFUSED: {exc}"
            break

        general_row = row_for(general_payload)
        record, reason = KIF.build_record(
            ticker=ticker, date=date, row=general_row or {}, detail_row=detail_row,
            collected_at=collected_at)
        done.add(f"{ticker}:{date}")
        if record is None:
            refused_count += 1
            continue
        fresh.setdefault(int(date[:4]), []).append(record)

        if calls % 100 == 0:
            done_count = sum(len(v) for v in fresh.values())
            print(f"  {calls}콜 · 수집 {done_count} · 빈응답 {refused_count}")

    written = 0
    changed = 0
    for year, rows in sorted(fresh.items()):
        merged = shards.get(year, []) + rows
        path = KIF.shard_path(store, year)
        if HS.write_shard(path, merged):
            changed += 1
        written += len(rows)
    save_done(store, done)

    outcome = OUT.run_outcome(stop_reason=stop_reason, calls=calls, written=written)
    manifest = {
        "contract": "KR_INVESTOR_FLOW_RAW_V1",
        "updatedAt": collected_at,
        "universeSize": len(tickers),
        "dateRange": [args.start, end],
        "thisRun": {"calls": calls, "recordsWritten": written, "shardsChanged": changed,
                    "stopReason": stop_reason, "emptyResponses": refused_count,
                    "outcome": outcome},
        "remainingPairs": len(pending) - len(fresh),
    }
    (store / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n=== 이번 실행 ===\n  호출 {calls} · 수집 {written}건 · 샤드 {changed}개 변경 · "
          f"종료 사유 {stop_reason} · outcome {outcome}")

    if OUT.is_reportable_failure(outcome, written=written):
        print(f"거부: 소스가 이번 실행에서 아무 진행도 허용하지 않았습니다 (outcome={outcome}). "
              "success로 보고하지 않습니다.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
