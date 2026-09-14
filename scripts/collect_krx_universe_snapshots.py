"""Collect dated KOSPI market-cap cross-sections, so Korea stops being survivors-only.

WHAT THIS BUYS. `dataIntegrity` reports KR `membershipCoveragePct` 0.0 —
not because the measurement failed but because `build_universe_history.py`
writes no Korean rows at all, having refused two earlier sources that both
described a cross-section they had invented. The consequence is not cosmetic:
with Korea undescribed, the survivorship stress test has to assume the whole
Korean sleeve could be wrong, and replay-v15's `survivorshipBound` came back
`REVERSES_UNDER_MEASURED_GAP` with KR stressed at 100%.

WHY A SOURCE EXISTS NOW. Probes run #4, under a subscribed key, measured
`sto/stk_bydd_trd` (유가증권 일별매매정보) as POINT_IN_TIME: 77.42% overlap
between 2013-01-02 and 2026-09-01, 210 issues departed, and it reached the
oldest date asked for. Below-100% overlap WITH departed names is the pair that
separates dated history from one cross-section wearing many date stamps.

WHAT IT WRITES, AND WHAT IT REFUSES TO DECIDE. Raw ranked issues under
`<store>/krx-universe-YYYY.jsonl.gz`, one row per issue per date, carrying what
KRX said — code, name, market cap, listed shares — and the rank market cap put
that issue at that day. No universe rule is applied here. A rule baked into a
collected artifact cannot be changed without re-collecting it, so the rule
lives in `krx_universe.members_on_date` where a different one is a
re-derivation rather than a re-fetch.

`--top` is the one number that bounds the artifact, and it is a ceiling on the
ranking, not a universe size: 300 against a Korean universe of 68 leaves room
for any plausible widening, while keeping a decade of monthly cross-sections
small enough to carry in the ledger. Raising it is a re-collection of the dates
already done, which is why the done-set records the `top` each date was
collected at and re-collects a date that was taken at a lower one.

BUDGETED AND RESUMABLE, like the two fundamentals collectors, because an
unknown daily quota should cost a resumed run and not a lost one. A call that
is refused does not mark its date done, so tomorrow starts where today stopped.

Usage:
    KRX_API_KEY=... python scripts/collect_krx_universe_snapshots.py <store>
        [--start 2013-01-01] [--end today] [--frequency monthly|weekly]
        [--top 300] [--max-calls 400] [--max-minutes 60] [--pace 0.4]
"""
from __future__ import annotations

import argparse
import datetime as dt
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

from pipeline import historical_store as HS  # noqa: E402
from pipeline import krx_universe as KU  # noqa: E402

# The service root and the one endpoint probes run #4 proved. Both overridable,
# because a wrong base is the single thing that would make a working endpoint
# look dead.
DEFAULT_BASE = "https://data-dbg.krx.co.kr/svc/apis"
ENDPOINT = "sto/stk_bydd_trd"

# The transport run #4 was served under. The probe varied this across five
# candidates precisely so the collector would not have to guess.
AUTH_HEADER = "AUTH_KEY"

DONE_NAME = "krx-universe-done.json"

# A requested date that falls on a market holiday is answered with no rows.
# Rather than dropping that month, step forward a few days to the next open
# session — and record the date KRX says it served, so the snapshot is dated by
# the session that happened and not by the holiday we asked about.
HOLIDAY_STEPS = 7


class Refused(RuntimeError):
    """The service declined. Not a fact about the data, so nothing is marked done."""


def call(base: str, path: str, params: dict, auth_key: str,
         timeout: int = 40) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{base.rstrip('/')}/{path}?{query}"
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        AUTH_HEADER: auth_key,
        "User-Agent": "InvestmentResearchDashboard/1.0",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read()[:400].decode("utf-8", "replace")
        message = None
        try:
            parsed = json.loads(body)
            message = parsed.get("respMsg") if isinstance(parsed, dict) else None
        except ValueError:
            pass
        # Carry KRX's own words. "Unauthorized Key" (the key is not recognised)
        # and "Unauthorized API Call" (the key is, this endpoint is not
        # subscribed) send whoever reads the log to different places, and a
        # label of our own would overwrite the distinction.
        raise Refused(f"HTTP {exc.code}"
                      + (f" — {message}" if message else f": {body[:160]}")) from None
    except ValueError as exc:
        raise Refused(f"response was not JSON: {exc}") from None
    except Exception as exc:  # pragma: no cover - network dependent
        raise Refused(f"{type(exc).__name__}: {exc}") from None


def load_done(store: Path) -> dict[str, int]:
    """Requested date -> the `--top` it was collected at.

    Kept beside the shards rather than inferred from them, for the same reason
    the fundamentals collectors keep one: a requested date that resolved
    forward to the next open session leaves no row under the date we asked
    about, and re-probing it every run would spend the budget on holidays.
    """
    path = store / DONE_NAME
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for date, top in raw.items():
        try:
            out[str(date)] = int(top)
        except (TypeError, ValueError):
            continue
    return out


def save_done(store: Path, done: dict[str, int]) -> None:
    (store / DONE_NAME).write_text(
        json.dumps(dict(sorted(done.items())), indent=0) + "\n", encoding="utf-8")


def pending_dates(targets: list[str], done: dict[str, int], top: int) -> list[str]:
    """Dates still owed, including ones taken at a shallower ranking than asked.

    A date collected at `--top 100` holds no rank-150 issue, so a later run at
    300 has to ask again or the ranking would be a decade of two different
    depths spliced together.
    """
    return [date for date in targets if done.get(date, 0) < top]


def collect(store: Path, targets: list[str], *, auth_key: str, base: str,
            top: int, max_calls: int, max_minutes: float, pace: float,
            log=print) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    done = load_done(store)
    pending = pending_dates(targets, done, top)

    shards: dict[int, list[dict]] = {}
    for path in sorted(store.glob("krx-universe-*.jsonl.gz")):
        try:
            year = int(path.stem.split("-")[-1].split(".")[0])
        except ValueError:
            continue
        shards[year] = HS.read_jsonl(path)

    log(f"수집 대상 {len(targets)}일 · 이미 완료 {len(targets) - len(pending)}일 "
        f"· 남은 {len(pending)}일")
    log(f"이번 예산 {max_calls}콜 / {max_minutes}분 · 간격 {pace}s · 상위 {top}종목\n")

    started = time.monotonic()
    calls = 0
    fresh: dict[int, list[dict]] = {}
    collected: list[str] = []
    holidays: list[str] = []
    stopped: str | None = None

    for requested in pending:
        if calls >= max_calls:
            stopped = f"콜 예산 {max_calls} 소진"
            break
        if (time.monotonic() - started) / 60.0 >= max_minutes:
            stopped = f"시간 예산 {max_minutes}분 소진"
            break

        rows: list[dict] = []
        served = requested
        # Walk forward over closed sessions. Each step is a call and is charged
        # to the budget, because a holiday costs the quota exactly as a trading
        # day does.
        for offset in range(HOLIDAY_STEPS + 1):
            if calls >= max_calls:
                break
            probe = (dt.date.fromisoformat(requested)
                     + dt.timedelta(days=offset)).isoformat()
            if pace and calls:
                time.sleep(pace)
            try:
                payload = call(base, ENDPOINT,
                               {"basDd": probe.replace("-", "")}, auth_key)
            except Refused as exc:
                # The service, not the data. Stop the run with nothing marked
                # done rather than recording a refusal as an empty exchange.
                log(f"  {probe}: 거절됨 — {exc}")
                stopped = f"{probe}에서 거절: {exc}"
                payload = None
                break
            calls += 1
            issues, error = KU.parse_issues(payload)
            if error:
                log(f"  {probe}: 응답을 읽을 수 없음 — {error}")
                stopped = f"{probe}: {error}"
                break
            if issues:
                served = KU.served_date(payload, probe)
                rows = KU.snapshot_rows(served, KU.rank_issues(issues, top))
                break
            holidays.append(probe)
        if stopped:
            break
        if not rows:
            log(f"  {requested}: {HOLIDAY_STEPS}일을 내다봐도 거래일이 없음 — 건너뜀")
            # Marked done: the exchange was shut, which is a fact about the
            # calendar and will not change on a retry.
            done[requested] = top
            continue

        fresh.setdefault(KU.shard_year(served), []).extend(rows)
        done[requested] = top
        collected.append(served)
        if len(collected) % 12 == 0 or len(collected) == 1:
            log(f"  {served}: {len(rows)}종목 (누적 {len(collected)}일, {calls}콜)")

    written: list[str] = []
    for year, rows in sorted(fresh.items()):
        merged = shards.get(year, []) + rows
        path = store / f"krx-universe-{year}.jsonl.gz"
        # Byte-deterministic: an unchanged shard returns False and is not
        # re-committed, so a re-run that collects nothing new is a no-op diff.
        if HS.write_shard(path, merged):
            written.append(path.name)
    save_done(store, done)

    remaining = len(pending_dates(targets, done, top))
    log(f"\n{len(collected)}일 수집 · {calls}콜 · 휴장 {len(holidays)}건 "
        f"· 샤드 {len(written)}개 기록 · 남은 {remaining}일")
    if stopped:
        log(f"중단: {stopped}")
    return {"collected": collected, "calls": calls, "holidays": holidays,
            "written": written, "remaining": remaining, "stopped": stopped}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store", help="어디에 샤드를 쓸지")
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default=None, help="기본값: 오늘")
    parser.add_argument("--frequency", default="monthly",
                        choices=sorted(KU.FREQUENCIES))
    parser.add_argument("--top", type=int, default=300)
    parser.add_argument("--max-calls", type=int, default=400)
    parser.add_argument("--max-minutes", type=float, default=60.0)
    parser.add_argument("--pace", type=float, default=0.4)
    parser.add_argument("--base", default=DEFAULT_BASE)
    args = parser.parse_args(argv)

    auth_key = (os.environ.get("KRX_API_KEY") or "").strip()
    if not auth_key:
        print("KRX_API_KEY가 없습니다. 키 없이 수집하면 서비스 거절을 "
              "'거래 없음'으로 기록하게 되므로 중단합니다.")
        return 2

    end = args.end or dt.date.today().isoformat()
    targets = KU.target_dates(args.start, end, args.frequency)
    result = collect(Path(args.store), targets, auth_key=auth_key,
                     base=args.base, top=args.top, max_calls=args.max_calls,
                     max_minutes=args.max_minutes, pace=args.pace)
    # A refusal is not a broken run — the store keeps everything collected
    # before it and the next run resumes — but it must not read as success
    # either, or an unsubscribed key would look like a finished backfill.
    return 1 if result["stopped"] and not result["collected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
