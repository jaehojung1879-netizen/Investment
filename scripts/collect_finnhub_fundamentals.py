"""Collect US point-in-time fundamentals from finnhub, one budgeted slice per run.

WHY FINNHUB, AND WHY THIS IS NOT A GUESS. SEC refuses the GitHub Actions
address range on all four of its hosts — measured across request shape, egress
address and traffic shape, and re-confirmed on every probe run since. Of the
vendors that are not sec.gov, finnhub is the one measured end to end: probe
run #2 returned filings inside 2012-01-01..2013-06-30 with `filedDate` for all
four living samples and for three of four names that have left the universe,
and every one of the seven production value and quality factors was computable
from the concepts that arrived. `docs/us-pit-fundamentals-source.md` carries
the run numbers.

WHY IN SLICES. About ten windows per ticker over 829 names that were ever US
members is roughly 8,290 calls. That is well inside a GitHub job at this
pacing, but the budget exists anyway: a collection that cannot resume is a
collection that starts over every time something upstream hiccups.

THE UNIVERSE IS EVERY NAME THAT WAS EVER A MEMBER, not the seventy in today's
config. 219 of the 829 US names were members before the replay starts and have
since left it. Collecting only what is listed today would rebuild, in the US
fundamentals, exactly the survivorship hole v12 and v13 spent two generations
closing in Korean prices.

WHAT IT WRITES. Raw filings under `<store>/finnhub-YYYY.jsonl.gz`, sharded by
the fiscal year they REPORT ON and byte-deterministic so an unchanged shard is
not re-committed. The concepts are kept under the filer's own US-GAAP tags.
Normalising at collection time cannot be revisited without re-fetching, and
probe run #2 — where a tag vocabulary assumed instead of measured reported
every production account as missing — is the standing reminder.

WHAT IT REFUSES. A filing with no `filedDate`. Point-in-time is the whole
reason this data is being collected, and a row that cannot say when it became
visible would sit in the store looking like coverage while being unusable.

WHAT IT REPORTS, AND WHY THE DERIVATION IS NOT WRITTEN YET. Per form type, the
distribution of period lengths the filings actually state. A US 10-Q is filed
with both a three-month and a year-to-date context, and which one the vendor
flattens into `report.ic` decides how a trailing-twelve-month figure has to be
built. The Korean derivation could only be written after the collector measured
the equivalent question over 2,927 filings; reading a cumulative cash flow as a
quarterly one would have inflated free cash flow fourfold with nothing raising
an error. So this run measures. The derivation is a separate change, written
against the answer.

Usage:
    python scripts/collect_finnhub_fundamentals.py <store-dir>
        [--from-year 2012] [--through 2026-09-13] [--tickers AAPL,JPM]
        [--max-calls 2000] [--max-minutes 240] [--pace 1.1]
    FINNHUB_API_KEY must be in the environment.
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
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_fundamentals as FF  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402

BASE = "https://finnhub.io/api/v1/stock/financials-reported"
UNIVERSE_HISTORY = ROOT / "data" / "universe-history.json"


def us_members(path: Path = UNIVERSE_HISTORY) -> list[str]:
    """Every US name the replay ever held, gone ones included."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return sorted(t for t, row in rows.items() if row.get("region") == "US")


def fetch_window(key: str, ticker: str, start: str, end: str,
                 freq: str = FF.QUARTERLY, timeout: int = 45) -> tuple[list[dict], str]:
    """One window for one ticker. Returns (filings, status).

    The status vocabulary is deliberately small and each value points at a
    different next move: RATE_LIMITED means ask again more slowly and is never
    an absence, HTTP_* and ERROR are ours to investigate, SERVED is data.
    """
    url = BASE + "?" + urllib.parse.urlencode(
        {"symbol": ticker, "freq": freq, "from": start, "to": end,
         "token": key})
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read(2000)
        except Exception:                              # pragma: no cover - network
            pass
        text = body.decode("utf-8", "replace")
        if FF.is_rate_limited(exc.code, text):
            return [], "RATE_LIMITED"
        return [], f"HTTP_{exc.code}"
    except Exception as exc:                           # pragma: no cover - network
        return [], f"ERROR_{type(exc).__name__}"

    text = body.decode("utf-8", "replace")
    if FF.is_rate_limited(status, text):
        return [], "RATE_LIMITED"
    try:
        payload = json.loads(text)
    except ValueError:
        return [], "NON_JSON"
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return [], "UNEXPECTED_SHAPE"
    return [r for r in rows if isinstance(r, dict)], "SERVED"


def load_existing(store: Path) -> tuple[set[str], dict[int, list[dict]]]:
    """Everything already collected, by shard. Filing ids drive the skip."""
    ids: set[str] = set()
    shards: dict[int, list[dict]] = {}
    for path in sorted(store.glob("finnhub-*.jsonl.gz")):
        try:
            year = int(path.stem.split("-")[1].split(".")[0])
        except (IndexError, ValueError):
            continue
        rows = list(HS.read_jsonl(path))
        shards[year] = rows
        ids.update(str(row.get("id")) for row in rows if row.get("id"))
    return ids, shards


def load_done_windows(store: Path) -> set[tuple[str, str, str]]:
    """Windows already asked for, so a resumed run does not re-buy them.

    Kept beside the shards rather than inferred from them: a window that
    legitimately held no filings is indistinguishable, from the shards alone,
    from one that was never asked — and re-buying an empty window every run is
    how a budget is spent on nothing.
    """
    path = store / "windows.json"
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return set()
    return FF.normalise_done(raw)


def save_done_windows(store: Path, done: set[tuple[str, str, str]]) -> None:
    (store / "windows.json").write_text(
        json.dumps(sorted(list(w) for w in done), indent=0, ensure_ascii=False),
        encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir")
    parser.add_argument("--from-year", type=int, default=FF.FIRST_YEAR)
    parser.add_argument("--through", default=None,
                        help="마지막 창의 끝 (기본: 오늘)")
    parser.add_argument("--tickers", default="",
                        help="쉼표 구분. 비우면 universe-history.json 의 미국 전체")
    parser.add_argument("--max-calls", type=int, default=2000)
    parser.add_argument("--max-minutes", type=int, default=240)
    parser.add_argument("--pace", type=float, default=FF.PACE_SECONDS)
    parser.add_argument("--freq", default=",".join(FF.FREQUENCIES),
                        help="쉼표 구분. 기본은 annual 먼저, 그 다음 quarterly")
    args = parser.parse_args(argv)

    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        print("ERROR: FINNHUB_API_KEY not in the environment.")
        return 1

    store = Path(args.store_dir)
    store.mkdir(parents=True, exist_ok=True)

    tickers = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
               if args.tickers else us_members())
    if not tickers:
        print("ERROR: 미국 유니버스를 확보하지 못했습니다.")
        return 1

    frequencies = tuple(f.strip() for f in args.freq.split(",") if f.strip())
    unknown = [f for f in frequencies if f not in FF.FREQUENCIES]
    if unknown:
        print(f"ERROR: 모르는 freq {unknown}; 가능한 값 {list(FF.FREQUENCIES)}")
        return 2

    spans = FF.windows(args.from_year, args.through)
    done_windows = load_done_windows(store)
    existing_ids, shards = load_existing(store)
    pending = FF.work_list(tickers, spans, done_windows, frequencies)

    state = FF.progress(len(done_windows), len(pending))
    print(f"미국 유니버스 {len(tickers)}종목 (한때 멤버였던 이름 전부) × 창 {len(spans)}개 "
          f"× 빈도 {list(frequencies)}")
    print(f"진행률 {state['collected']:,} / {state['total']:,} 창 "
          f"({state['completePct']}%) · 남음 {state['pending']:,}")
    print(f"이미 저장된 공시 {len(existing_ids):,}건")
    print(f"이번 예산 {args.max_calls}콜 / {args.max_minutes}분 · 간격 {args.pace}s\n")

    deadline = time.time() + args.max_minutes * 60
    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fresh: dict[int, list[dict]] = {}
    statuses: Counter = Counter()
    refused: Counter = Counter()
    seen_again: Counter = Counter()
    fresh_records: list[dict] = []
    calls = 0
    stop_reason = "WORK_LIST_EXHAUSTED"

    for ticker, start, end, freq in pending:
        if calls >= args.max_calls:
            stop_reason = "CALL_BUDGET_SPENT"
            break
        if time.time() >= deadline:
            stop_reason = "TIME_BUDGET_SPENT"
            break

        rows, status = fetch_window(key, ticker, start, end, freq)
        calls += 1
        statuses[status] += 1
        time.sleep(args.pace)

        # A rate limit is not an absence and must not close the window: the
        # next run has to ask again. polygon refused three of four samples this
        # way in probe run #2 and the verdict read it as missing coverage.
        if status == "RATE_LIMITED":
            print(f"중단: 속도 제한 — {calls}콜에서 멈춥니다. 다음 실행이 이어받습니다.")
            stop_reason = "RATE_LIMITED"
            break
        if status != "SERVED":
            refused[status] += 1
            continue

        for filing in rows:
            record, reason = FF.build_record(ticker, filing, collected_at, freq)
            if record is None:
                refused[reason] += 1
                continue
            if record["id"] in existing_ids:
                # The same 10-K can arrive from both passes. First write wins,
                # which keeps the store byte-stable across re-runs.
                seen_again[freq] += 1
                continue
            existing_ids.add(record["id"])
            fresh.setdefault(FF.shard_year(record), []).append(record)
            fresh_records.append(record)
        done_windows.add((ticker, start, end, freq))

    # Write before reporting. A run that spends its budget and then dies in the
    # summary must not lose what it paid for.
    written = []
    for year, records in sorted(fresh.items()):
        merged = shards.get(year, []) + records
        merged.sort(key=lambda row: (str(row.get("ticker")), str(row.get("periodEnd")),
                                     str(row.get("accession"))))
        path = store / f"finnhub-{year}.jsonl.gz"
        # `write_shard` is byte-deterministic and returns False when the bytes
        # are unchanged, so an untouched shard is not re-committed.
        if HS.write_shard(path, merged):
            written.append(f"{path.name}({len(merged):,})")
    save_done_windows(store, done_windows)

    print("\n=== 이번 실행 ===")
    print(f"  호출 {calls:,} · 중단 사유 {stop_reason}")
    for status, count in statuses.most_common():
        print(f"    {status:<20} {count:,}")
    if refused:
        print("  저장하지 않은 것")
        for reason, count in refused.most_common():
            print(f"    {reason:<20} {count:,}")
    if seen_again:
        print("  이미 갖고 있어 건너뛴 것 (두 빈도가 같은 공시를 줄 수 있습니다)")
        for freq, count in seen_again.most_common():
            print(f"    {freq:<20} {count:,}")
    print(f"  새 공시 {len(fresh_records):,}건 · 샤드 {', '.join(written) or '없음'}")

    after = FF.progress(len(done_windows), len(pending) - calls if pending else 0)
    print(f"  진행률 {after['collected']:,} 창 완료")

    if fresh_records:
        report = FF.inventory(fresh_records)
        print("\n=== 기간 인벤토리 (파생을 쓰기 전에 재야 하는 것) ===")
        print(f"  공시 {report['filings']:,}건 · 기간 길이 미기재 "
              f"{report['filingsWithNoPeriodLength']:,}건")
        for form, buckets in report["periodLengthByForm"].items():
            print(f"    {form:<10} " + " · ".join(f"{k} {v:,}" for k, v in buckets.items()))
        print(f"  빈도별 공시 수 {report['filingsByFreq']}")
        for freq, forms in report["formsByFreq"].items():
            print(f"    {freq:<10} {forms}")
        print("  계정과목 수 (원본 → 네임스페이스 통합)")
        for section, count in report["conceptsBySection"].items():
            merged = report["conceptsBySectionCollapsed"].get(section, count)
            print(f"    {section:<4} {count:,} → {merged:,}"
                  + (f"   (두 벌 철자 {count - merged:,}개)" if count > merged else ""))
        for section, names in report["topConceptsCollapsed"].items():
            if names:
                print(f"    {section} 상위: {names[:6]}")
        print(f"  단위 분류 {report['unitClasses']}")
        if report["unclassifiedUnits"]:
            print(f"  분류 못 한 단위 {report['unclassifiedUnits']} "
                  f"— 버리지 않고 남겨 두었습니다")
        (store / "inventory.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  → {store / 'inventory.json'} 에 기록했습니다. 10-Q 의 손익계산서가 "
              f"분기인지 누계인지가 여기서 정해지고, 파생은 그 답에 맞춰 씁니다.")
    return 0


if __name__ == "__main__":                              # pragma: no cover
    raise SystemExit(main())
