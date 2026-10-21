"""Daily KOSPI bars from KRX, for the names FinanceDataReader cannot serve.

WHAT THIS CLOSES. `collect_krx_universe_snapshots.py` established that 139 of
the 260 names ever in the Korean top-120 universe have left it — 38 to 41% of
every cross-section from 2013 to 2017. Membership alone does not restore them:
`UniverseHistory.snapshot` keeps only what the price panel can serve, and
`unvouched` counts a described-but-unpriceable name exactly as it counts an
unknown one. FinanceDataReader was measured serving 34.55% of delisted Korean
names, so membership on its own would take KR unvouched from 100% to roughly
25% and stop there.

`sto/stk_bydd_trd` — the endpoint that answered the membership question, under
the same subscribed key — lists what TRADED on a date, so a name that delisted
in 2014 is in the 2013 responses like any other. Its rows carry
`TDD_OPNPRC/HGPRC/LWPRC/CLSPRC`, `ACC_TRDVOL` and `LIST_SHRS`.

WHAT IT COSTS. At most one call per candidate weekday per run; calendar-proven
closures consume no requests. Empty open sessions remain pending for a later
budgeted run. Closed dates are decided
by the pinned KR exchange calendar, never by an empty response or its age.
An empty open session remains pending on every run. Weekends are not requested.

WHAT IT WRITES, AND THE ONE POLICY IT APPLIES. Raw as-traded bars under
`<store>/krx-prices-YYYY.jsonl.gz`, one row per issue per session, carrying
what KRX printed. No adjustment is done here; `krx_prices.to_vendor_basis` and
the sealed `price_adjustment` path do that, so a change of method is a
re-derivation rather than 3,570 calls.

The single collector-side decision is WHICH TICKERS to keep, and it is a
storage bound rather than a judgement: the endpoint answers with the whole
exchange, about 930 issues, and a decade of that at daily grain would be
hundreds of megabytes in a branch that has to stay clonable. The membership
shards name the only tickers that can ever enter the cross-section, so those
are what is kept. `--all-issues` turns the filter off; the call count is
identical either way.

WHAT A RESPONSE MUST SATISFY BEFORE ANYTHING IS STORED. `bar_value_errors` is
the numeric contract of every field, not only the close: no NaN/Infinity, no
negative or fractional volume, no non-positive or fractional share count, and
on a traded row no zero or out-of-range price. A suspended issue (volume 0) may
print a zero range. An unstated field stays None. One violating issue in the
response refuses the whole day: nothing is written and `done` does not advance.

WHAT `done` DOES NOT PROVE. It means a valid response with kept rows was
stored, not that every listed name was in it. `completeness_receipts` compares
each date with the prior membership snapshot and reports missing members as
UNRESOLVED; `--diagnose` runs the same check over an existing store with no
API key, no call and no write.

Usage:
    KRX_API_KEY=... python scripts/collect_krx_daily_prices.py <store>
        --universe <membership shard dir>
        [--start 2013-01-01] [--end today]
        [--max-calls 4000] [--max-minutes 300] [--pace 0.4] [--all-issues]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
import time
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS  # noqa: E402
from pipeline import krx_prices as KP  # noqa: E402
from pipeline import krx_universe as KU  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402

from collect_krx_universe_snapshots import (AUTH_HEADER, DEFAULT_BASE,  # noqa: E402,F401
                                            ENDPOINT, Refused, call)

DONE_NAME = "krx-prices-done.json"


def universe_tickers(store: Path) -> set[str]:
    """Every ticker the membership shards ever describe.

    Read from the shards rather than from `universe-history.json`, so the price
    collection stays in step with the membership collection without depending
    on a build having run in between.
    """
    tickers: set[str] = set()
    for path in sorted(store.glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            ticker = row.get("ticker")
            if ticker:
                tickers.add(ticker)
    return tickers


def load_done(store: Path) -> set[str]:
    path = store / DONE_NAME
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValueError("INVALID_DONE_FILE: manual inspection required") from exc
    if not isinstance(raw, list) or any(not isinstance(d, str) for d in raw):
        raise ValueError("INVALID_DONE_FILE: expected ISO date list")
    for day in raw:
        if dt.date.fromisoformat(day).isoformat() != day:
            raise ValueError("INVALID_DONE_FILE: noncanonical date")
    if len(raw) != len(set(raw)):
        raise ValueError("INVALID_DONE_FILE: duplicate dates")
    return set(raw)


def save_done(store: Path, done: set[str]) -> None:
    # A failed/interrupted write must not destroy the prior retry checkpoint.
    with tempfile.TemporaryDirectory(dir=store, prefix=".krx-done-") as temp:
        path = Path(temp) / DONE_NAME
        path.write_text(json.dumps(sorted(done), indent=0) + "\n", encoding="utf-8")
        path.replace(store / DONE_NAME)


def daily_bars(payload: dict, requested: str) -> tuple[list[dict], str | None]:
    """Strict daily boundary around the unchanged, sealed general parser.

    Monthly universe collection can roll a holiday forward. Daily prices cannot:
    every returned row must explicitly describe the requested session.
    """
    bars, error = KP.parse_bars(payload)
    if error:
        return [], error
    key = next(k for k in KU.ROWS_KEYS if k in payload)
    raw = payload[key]
    if not raw:
        return [], None
    if len(bars) != len(raw):
        return [], "INVALID_DAILY_ROWS: partial, duplicate or unparseable rows"
    for row in raw:
        stamps = [str(row[k]).strip() for k in KU.DATE_KEYS if row.get(k) not in (None, "")]
        if not stamps or any(stamp != requested.replace("-", "") for stamp in stamps):
            return [], "SERVED_DATE_MISMATCH_OR_MISSING"
    if any(not math.isfinite(bar["close"]) or bar["close"] <= 0 for bar in bars):
        return [], "INVALID_DAILY_CLOSE"
    invalid = [(bar["code"], errors) for bar in bars if (errors := bar_value_errors(bar))]
    if invalid:
        code, errors = invalid[0]
        return [], (f"INVALID_DAILY_VALUE: {len(invalid)} issue(s), first {code}: "
                    + ",".join(errors))
    return bars, None


BAR_FIELDS = ("open", "high", "low", "close", "volume", "listedShares")


def bar_value_errors(bar: dict) -> list[str]:
    """The numeric contract of one parsed bar, checked at the collector boundary.

    `parse_number` (sealed, shared with the monthly universe) turns "NaN" and
    "Infinity" into floats, and `historical_store.encode` writes them as bare
    NaN/Infinity tokens, so the only place to refuse them is here.

    None means KRX printed nothing for the field and is kept as None: absence is
    not repaired into 0. A zero volume is a suspended issue, which KRX still
    lists with its last close, so on such a row a zero open/high/low is not an
    error and the range is not checked. On any other row these are an invalid
    response, not a value to store: a zero, negative or out-of-range price, a
    negative or fractional volume, or a non-positive or fractional share count.
    """
    errors = [f"NONFINITE:{field}" for field in BAR_FIELDS
              if bar.get(field) is not None
              and (not isinstance(bar[field], float) or not math.isfinite(bar[field]))]
    if errors:
        return errors
    volume, shares = bar.get("volume"), bar.get("listedShares")
    if volume is not None and volume < 0:
        errors.append("NEGATIVE:volume")
    elif volume is not None and not volume.is_integer():
        errors.append("NON_INTEGRAL:volume")
    if shares is not None and shares <= 0:
        errors.append("NOT_POSITIVE:listedShares")
    elif shares is not None and not shares.is_integer():
        errors.append("NON_INTEGRAL:listedShares")
    for field in ("open", "high", "low"):
        value = bar.get(field)
        if value is not None and value < 0:
            errors.append(f"NEGATIVE:{field}")
        elif value == 0 and volume != 0:
            errors.append(f"ZERO_PRICE_ON_ROW_NOT_KNOWN_SUSPENDED:{field}")
    if errors or volume == 0:
        return errors
    low, high = bar.get("low"), bar.get("high")
    if low is not None and high is not None and low > high:
        errors.append("OHLC_INCONSISTENT:low>high")
    for field in ("open", "close"):
        value = bar.get(field)
        if value is not None and ((low is not None and value < low)
                                  or (high is not None and value > high)):
            errors.append(f"OHLC_INCONSISTENT:{field}_outside_range")
    return errors


def assert_storable(rows: list[dict]) -> None:
    """Last guard before any shard is staged: standard JSON only, no NaN/Infinity."""
    for row in rows:
        try:
            json.dumps(row, ensure_ascii=False, default=str, allow_nan=False)
        except ValueError as exc:
            raise ValueError("NONFINITE_NUMERIC_IN_FRESH_ROW: " + str(row.get("id"))) from exc


def membership_snapshots(universe: Path) -> dict[str, set[str]]:
    """{snapshot date: tickers KRX listed in it}, from the membership shards."""
    snapshots: dict[str, set[str]] = {}
    for path in sorted(universe.glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            if row.get("date") and row.get("ticker"):
                snapshots.setdefault(str(row["date"]), set()).add(row["ticker"])
    return snapshots


def completeness_receipts(rows_by_date: dict[str, set[str]], dates: list[str],
                          snapshots: dict[str, set[str]]) -> list[dict]:
    """Stored tickers on each date against the latest membership snapshot before it.

    A completed date proves only that the response carried at least one kept
    row. This compares it with the names KRX itself listed on the most recent
    snapshot on or before that date. KRX keeps a suspended issue in the daily
    response, so a snapshot member missing from a day is either an exit between
    the snapshot and that day, or a gap in the response. The store holds no
    listing evidence that tells those apart, so any missing member makes the
    date UNRESOLVED. Members also listed in the next snapshot are reported
    separately, because they were listed on both sides of the date. No count
    threshold exists and nothing is filled. COMPLETE is relative to the prior
    snapshot only: a name that listed after it is not checked.
    """
    ordered = sorted(snapshots)
    receipts = []
    for day in sorted(dates):
        prior = [s for s in ordered if s <= day]
        later = [s for s in ordered if s > day]
        stored = rows_by_date.get(day, set())
        receipt = {"date": day, "storedTickers": len(stored),
                   "pitSnapshotDate": prior[-1] if prior else None,
                   "nextPitSnapshotDate": later[0] if later else None}
        if not prior:
            receipts.append({**receipt, "status": "UNRESOLVED_NO_PRIOR_PIT_SNAPSHOT"})
            continue
        missing = snapshots[prior[-1]] - stored
        both_sides = missing & snapshots[later[0]] if later else set()
        receipts.append({**receipt, "pitSnapshotTickers": len(snapshots[prior[-1]]),
                         "missingListedBeforeAndAfter": sorted(both_sides),
                         "missingExitUnknown": sorted(missing - both_sides),
                         "status": ("UNRESOLVED_PIT_MEMBERS_ABSENT" if missing
                                    else "COMPLETE_AGAINST_PRIOR_PIT_SNAPSHOT")})
    return receipts


def keep_digest(keep: set[str] | None) -> str | None:
    if keep is None:
        return None
    return hashlib.sha256("\n".join(sorted(keep)).encode("utf-8")).hexdigest()


def diagnose(store: Path, universe: Path | None) -> dict:
    """Read-only completeness diagnosis of an existing store. Calls nothing, writes nothing."""
    done = load_done(store)
    rows = [row for path in sorted(store.glob("krx-prices-*.jsonl.gz"))
            for row in HS.read_jsonl(path)]
    rows_by_date: dict[str, set[str]] = {}
    nonfinite: dict[str, int] = {}
    undated = 0
    for row in rows:
        try:
            day = dt.date.fromisoformat(str(row.get("date"))).isoformat()
        except ValueError:
            undated += 1
            continue
        rows_by_date.setdefault(day, set()).add(row.get("ticker"))
        for field in BAR_FIELDS:
            value = row.get(field)
            if isinstance(value, float) and not math.isfinite(value):
                nonfinite[field] = nonfinite.get(field, 0) + 1
    dates = sorted(done | set(rows_by_date))
    open_dates = (set(RC.sessions(dates[0], dates[-1], "KR").strftime("%Y-%m-%d"))
                  if dates else set())
    done_open = sorted(done & open_dates)
    snapshots = membership_snapshots(universe) if universe else {}
    receipts = completeness_receipts(rows_by_date, done_open, snapshots)
    by_status: dict[str, int] = {}
    for receipt in receipts:
        by_status[receipt["status"]] = by_status.get(receipt["status"], 0) + 1
    keep = set().union(*snapshots.values()) if snapshots else None
    anomalies = {
        "doneOpenSessionWithoutRows": sorted(set(done_open) - set(rows_by_date)),
        "rowsWithoutDone": sorted(set(rows_by_date) - done),
        "rowsOnClosedDates": sorted(set(rows_by_date) - open_dates),
        "storedNonfiniteValuesByField": dict(sorted(nonfinite.items())),
        "rowsWithoutValidDate": undated,
    }
    complete = (bool(receipts) and set(by_status) == {"COMPLETE_AGAINST_PRIOR_PIT_SNAPSHOT"}
                and not any(anomalies.values()))
    return {"status": "COMPLETE_AGAINST_PRIOR_PIT_SNAPSHOT" if complete else "UNRESOLVED",
            "doneDates": len(done), "doneOpenSessions": len(done_open),
            "membershipSnapshots": len(snapshots), "membershipKeepSha256": keep_digest(keep),
            "receiptsByStatus": dict(sorted(by_status.items())), "anomalies": anomalies,
            "receipts": receipts}


def today_kr() -> dt.date:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()


def collect(store: Path, targets: list[str], *, auth_key: str, base: str,
            keep: set[str] | None, max_calls: int, max_minutes: float,
            pace: float, log=print, as_of: dt.date | None = None,
            snapshots: dict[str, set[str]] | None = None) -> dict:
    as_of = as_of or today_kr()
    targets = list(dict.fromkeys(targets))
    for day in targets:
        if dt.date.fromisoformat(day).isoformat() != day:
            raise ValueError("NONCANONICAL_TARGET_DATE")
    # Unknown/out-of-range calendar evidence refuses before any call or write.
    open_dates = (set(RC.sessions(min(targets), max(targets), "KR").strftime("%Y-%m-%d"))
                  if targets else set())
    done = load_done(store)
    initial_done = set(done)
    pending = [d for d in targets if d not in done]

    shards: dict[int, list[dict]] = {}
    for path in sorted(store.glob("krx-prices-*.jsonl.gz")):
        try:
            year = int(path.stem.split("-")[-1].split(".")[0])
        except ValueError:
            continue
        shards[year] = HS.read_jsonl(path)

    stored_dates = {row.get("date") for rows in shards.values() for row in rows}
    unsupported = sorted((set(targets) & done & open_dates) - stored_dates)
    if unsupported:
        # Do not remove or repair legacy markers/data automatically.
        raise ValueError("DONE_WITHOUT_SESSION_ROWS: manual inspection required: " + ",".join(unsupported))
    store.mkdir(parents=True, exist_ok=True)

    log(f"수집 대상 {len(targets)}거래일(후보) · 이미 완료 "
        f"{len(targets) - len(pending)}일 · 남은 {len(pending)}일")
    log(f"이번 예산 {max_calls}콜 / {max_minutes}분 · 간격 {pace}s · "
        f"유지 종목 {'전체' if keep is None else len(keep)}\n")

    started = time.monotonic()
    calls = 0
    fresh: dict[int, list[dict]] = {}
    sessions: list[str] = []
    closed: list[str] = []
    provisional: list[str] = []
    bars_written = 0
    stopped: str | None = None

    for requested in pending:
        if requested > as_of.isoformat():
            provisional.append(requested)
            continue
        if requested not in open_dates:
            closed.append(requested)
            done.add(requested)
            continue
        if calls >= max_calls:
            stopped = f"콜 예산 {max_calls} 소진"
            break
        if (time.monotonic() - started) / 60.0 >= max_minutes:
            stopped = f"시간 예산 {max_minutes}분 소진"
            break
        if pace and calls:
            time.sleep(pace)
            if (time.monotonic() - started) / 60.0 >= max_minutes:
                stopped = f"시간 예산 {max_minutes}분 소진"
                break
        calls += 1
        try:
            payload = call(base, ENDPOINT,
                           {"basDd": requested.replace("-", "")}, auth_key)
        except Refused as exc:
            # The service, not the market. Nothing is marked done, so the next
            # run asks this day again instead of recording a refusal as a
            # holiday and never returning to it.
            log(f"  {requested}: 거절됨 — {exc}")
            stopped = f"{requested}에서 거절: {exc}"
            break
        bars, error = daily_bars(payload, requested)
        if error:
            log(f"  {requested}: 응답을 읽을 수 없음 — {error}")
            stopped = f"{requested}: {error}"
            break
        if not bars:
            # A normal session stays pending forever if the source stays empty.
            # Its age is never evidence that the exchange was closed.
            provisional.append(requested)
            continue

        served = requested  # every row's explicit served date was verified
        rows = KP.bar_rows(served, bars, keep)
        if not rows:
            provisional.append(requested)
            continue
        fresh.setdefault(KP.shard_year(served), []).extend(rows)
        bars_written += len(rows)
        done.add(requested)
        sessions.append(served)
        if len(sessions) % 250 == 0 or len(sessions) == 1:
            log(f"  {served}: {len(rows)}종목 "
                f"(누적 {len(sessions)}세션, {calls}콜, {bars_written}행)")

    for rows in fresh.values():
        assert_storable(rows)  # raises before any shard or checkpoint is touched
    written: list[str] = []
    for year, rows in sorted(fresh.items()):
        merged = shards.get(year, []) + rows
        path = store / f"krx-prices-{year}.jsonl.gz"
        # Stage through the unchanged canonical writer. Failure leaves the old
        # shard intact; no done checkpoint is committed until all shards land.
        with tempfile.TemporaryDirectory(dir=store, prefix=".krx-shard-") as temp:
            staged = Path(temp) / path.name
            HS.write_shard(staged, merged)
            if not path.exists() or path.read_bytes() != staged.read_bytes():
                staged.replace(path)
                written.append(path.name)
    if done != initial_done:
        save_done(store, done)

    remaining = len([d for d in targets if d not in done])
    # `done` still means "a valid response with kept rows was stored". Whether
    # that response held every snapshot member is reported, never assumed.
    by_date: dict[str, set[str]] = {}
    for rows in fresh.values():
        for row in rows:
            by_date.setdefault(row["date"], set()).add(row["ticker"])
    receipts = completeness_receipts(by_date, sessions, snapshots or {})
    unresolved = [r["date"] for r in receipts if r["status"] != "COMPLETE_AGAINST_PRIOR_PIT_SNAPSHOT"]
    log(f"\n{len(sessions)}세션 · {bars_written}행 · {calls}콜 · 휴장 "
        f"{len(closed)}일 · 샤드 {len(written)}개 기록 · 남은 {remaining}일 · "
        f"완전성 UNRESOLVED {len(unresolved)}일")
    if stopped:
        log(f"중단: {stopped}")
    return {"sessions": sessions, "bars": bars_written, "calls": calls,
            "closed": closed, "provisional": provisional, "written": written, "remaining": remaining,
            "stopped": stopped, "keepSha256": keep_digest(keep),
            "completeness": receipts, "completenessUnresolved": unresolved}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store")
    parser.add_argument("--universe", default=None,
                        help="멤버십 샤드 디렉터리 — 어떤 티커를 남길지 여기서 읽는다")
    parser.add_argument("--all-issues", action="store_true",
                        help="필터를 끄고 거래소 전체를 기록 (용량이 크게 늘어난다)")
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-calls", type=int, default=4000)
    parser.add_argument("--max-minutes", type=float, default=300.0)
    parser.add_argument("--pace", type=float, default=0.4)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--diagnose", action="store_true",
                        help="API 호출·쓰기 없이 기존 저장소의 완전성만 진단해 JSON으로 출력")
    args = parser.parse_args(argv)

    if args.diagnose:
        report = diagnose(Path(args.store), Path(args.universe) if args.universe else None)
        print(json.dumps(report, ensure_ascii=False, indent=1, allow_nan=False))
        return 0

    auth_key = (os.environ.get("KRX_API_KEY") or "").strip()
    if not auth_key:
        print("KRX_API_KEY가 없습니다. 키 없이 수집하면 서비스 거절을 "
              "'휴장'으로 기록하게 되므로 중단합니다.")
        return 2

    keep: set[str] | None = None
    if not args.all_issues:
        if not args.universe:
            print("--universe 또는 --all-issues 중 하나가 필요합니다. 필터 없이 "
                  "기본 실행하면 거래소 전체를 10년치 쌓게 됩니다.")
            return 2
        keep = universe_tickers(Path(args.universe))
        if not keep:
            print(f"{args.universe}에 멤버십 샤드가 없습니다. 멤버십을 먼저 "
                  f"수집하거나 --all-issues를 쓰십시오.")
            return 2

    end = args.end or today_kr().isoformat()
    targets = KP.calendar_days(args.start, end)
    snapshots = membership_snapshots(Path(args.universe)) if args.universe else None
    result = collect(Path(args.store), targets, auth_key=auth_key,
                     base=args.base, keep=keep, max_calls=args.max_calls,
                     max_minutes=args.max_minutes, pace=args.pace, snapshots=snapshots)
    # Preserve useful partial collection, but never report all-empty sessions
    # as a successful completed run. No immediate retry or workflow dispatch.
    return 1 if not result["sessions"] and (result["stopped"] or result["provisional"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
