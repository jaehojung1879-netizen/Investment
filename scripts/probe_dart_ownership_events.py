"""Does DART's majorstock.json actually carry what dart_ownership_events reads?

WHY A PROBE AND NOT A STRAIGHT COLLECTOR. `pipeline/dart_ownership_events.py`
is built against a field set corroborated from RESEARCH — WebFetch of
OpenDART's own developer guide was blocked from this sandbox's egress, so the
field names (`rcept_no`, `rcept_dt`, `corp_code`, `corp_name`, `report_tp`,
`repror`, `stkqy`, `stkqy_irds`, `stkrt`, `stkrt_irds`) were corroborated
across two independent third-party libraries that wrap this same documented
endpoint instead. Corroborated is not confirmed: this probe calls the real
endpoint, in CI, with the real key, and reports which of those fields the
live response actually carries under those names, exactly as
`probe_dart_fundamentals.py` did for the statement endpoint before
`dart_fundamentals.py` was trusted.

WHAT DECIDES THE ANSWER, IN ORDER, mirroring `probe_dart_fundamentals.py`'s
own structure:

  1. DOES THE KEY REACH THIS ENDPOINT AT ALL. `majorstock.json` is API group
     DS004, a different group from the DS002 statement endpoint the existing
     collector already uses; a key subscribed to one group is not guaranteed
     subscribed to the other, and DART's own status codes distinguish "no
     data for this company" (013) from "key not recognised for this service"
     — `dart_fundamentals.describe_status` already carries both meanings, so
     this probe reads its answer through that same table rather than a new
     one.
  2. THE FIELD SET. Every field `build_event` reads is checked for presence
     on a real row, for at least one company with disclosed 5%+ holders.
  3. `report_tp`'S ACTUAL VALUES. This reports every distinct value a live
     sample actually returns, checked against
     `dart_ownership_events.KNOWN_REPORT_TYPE_RAW_VALUES` — a genuinely new
     value nobody has seen before is a different, more urgent fact than one
     already known and deliberately left untranslated (see that module's
     docstring for why `report_tp` is not translated into a normalized
     `reportType` even for known values).
  4. HOW FAR BACK. DART's statement coverage starts 2015
     (`dart_fundamentals.FIRST_SERVED_YEAR`); ownership disclosures are a
     different report family and may reach further back or not as far — this
     is asked for directly rather than assumed to match.

Nothing is written to the ledger and no artifact changes. This reports.

Usage:  python scripts/probe_dart_ownership_events.py [--output probe.json]
        [--samples 005930,000660,035420]
        DART_API_KEY must be in the environment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import dart_ownership_events as DOE  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
EXPECTED_FIELDS = ("rcept_no", "rcept_dt", "corp_code", "corp_name",
                   "report_tp", "repror", "stkqy", "stkqy_irds", "stkrt", "stkrt_irds")


def call(path: str, params: dict, timeout: int = 30) -> tuple[dict | None, str]:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}/{path}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # pragma: no cover - network dependent
        return None, f"{type(exc).__name__}: {exc}"
    try:
        return json.loads(raw.decode("utf-8")), ""
    except ValueError:
        return None, f"non-JSON response ({len(raw)} bytes)"


def corp_code_map(key: str) -> dict[str, str]:
    """Same mapping `collect_dart_fundamentals.py` builds — reused, not redone."""
    try:
        with urllib.request.urlopen(f"{BASE}/corpCode.xml?crtfc_key={key}",
                                    timeout=120) as response:
            blob = response.read()
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"ERROR: corp_code 목록을 받지 못했습니다 — {exc}")
        return {}
    if blob[:2] != b"PK":
        print("ERROR: corp_code 응답이 ZIP이 아닙니다")
        return {}
    import io
    import xml.etree.ElementTree as ET
    import zipfile
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        xml = archive.read(archive.namelist()[0])
    out: dict[str, str] = {}
    for item in ET.fromstring(xml).iter("list"):
        stock = (item.findtext("stock_code") or "").strip()
        corp = (item.findtext("corp_code") or "").strip()
        if stock and corp:
            out[stock] = corp
    return out


def probe_one(key: str, stock: str, corp: str) -> dict:
    payload, error = call("majorstock.json", {"crtfc_key": key, "corp_code": corp})
    entry: dict = {"stockCode": stock, "corpCode": corp}
    if payload is None:
        entry["error"] = error
        return entry
    status = str(payload.get("status"))
    entry["status"] = DF.describe_status(status)
    rows = payload.get("list") or []
    entry["rows"] = len(rows)
    if status != "000" or not rows:
        return entry

    fields_present = {field: sum(1 for r in rows if r.get(field) not in (None, ""))
                      for field in EXPECTED_FIELDS}
    entry["fieldsPresent"] = fields_present
    entry["fieldsPresentPct"] = {k: round(100.0 * v / len(rows), 1)
                                 for k, v in fields_present.items()}
    entry["reportTypesSeen"] = dict(Counter(str(r.get("report_tp")) for r in rows))

    sample = rows[0]
    events, refused = [], Counter()
    for row in rows:
        event, reason = DOE.build_event(row, ticker=f"{stock}.KS",
                                        collected_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"))
        if event is None:
            refused[reason] += 1
        else:
            events.append(event)
    entry["buildEventSucceeded"] = len(events)
    entry["buildEventRefused"] = dict(refused)
    entry["sampleRow"] = sample
    entry["sampleReceiptDates"] = sorted({DF.receipt_date(r.get("rcept_no")) for r in rows[:20]})
    entry["earliestReceiptDate"] = min(
        (DF.receipt_date(r.get("rcept_no")) for r in rows
         if DF.receipt_date(r.get("rcept_no"))), default=None)
    return entry


def classify_verdict(report: dict) -> str:
    """One of SERVED / AUTH_REQUIRED / NETWORK_ERROR / BLOCKED_SOURCE /
    SCHEMA_CHANGED / INCONCLUSIVE_NO_ROWS — the same exit-semantics vocabulary
    `pipeline/collector_outcomes.py` uses for the KRX collectors, so an
    operator (or an `auto` workflow gate) reads one consistent set of words
    across every source in this repository rather than a bespoke string per
    source.

    A genuinely new `report_tp` value never downgrades this verdict: raw
    passthrough handles any string, known or not, so a new categorical value
    is noted (`reportTypesNeverSeenBefore`) but is not a reason to block
    collection. Only a MISSING expected field — data this module actually
    reads — does that.
    """
    samples = report["samples"]
    served = [e for e in samples.values() if e.get("rows")]
    if served:
        all_fields_present = all(
            all(pct > 0 for pct in (e.get("fieldsPresentPct") or {}).values())
            for e in served)
        return "SERVED" if all_fields_present else "SCHEMA_CHANGED"
    statuses = [str(e.get("status", "")) for e in samples.values() if e.get("status")]
    if any(any(code in status for code in DF.FATAL_STATUSES) for status in statuses):
        return "AUTH_REQUIRED"
    errors = [str(e["error"]) for e in samples.values() if e.get("error")]
    if any("HTTP" not in err for err in errors):
        return "NETWORK_ERROR"
    if errors:
        return "BLOCKED_SOURCE"
    return "INCONCLUSIVE_NO_ROWS"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="dart-ownership-probe.json")
    parser.add_argument("--samples", default="005930,000660,035420",
                        help="stock codes: 삼성전자, SK하이닉스, NAVER")
    args = parser.parse_args(argv)

    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("ERROR: DART_API_KEY not in the environment; nothing probed.")
        return 1
    print(f"key present, {len(key)} chars\n")

    report: dict = {"probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "endpoint": "majorstock.json", "expectedFields": EXPECTED_FIELDS}

    codes = corp_code_map(key)
    if not codes:
        return 1
    print(f"corp_code 매핑 {len(codes):,}개\n")

    samples = [s.strip() for s in args.samples.split(",") if s.strip()]
    report["samples"] = {}
    all_report_types: Counter = Counter()
    for stock in samples:
        corp = codes.get(stock)
        if not corp:
            report["samples"][stock] = {"error": "corp_code 매핑 없음"}
            print(f"{stock}  corp_code 없음 — 건너뜀")
            continue
        entry = probe_one(key, stock, corp)
        report["samples"][stock] = entry
        all_report_types.update(entry.get("reportTypesSeen") or {})
        if entry.get("error"):
            print(f"{stock}  ERROR {entry['error']}")
        else:
            print(f"{stock}  status={entry.get('status')} rows={entry.get('rows')} "
                  f"earliest={entry.get('earliestReceiptDate')} "
                  f"report_tp={entry.get('reportTypesSeen')}")
        time.sleep(0.3)

    report["allReportTypesSeen"] = dict(all_report_types)
    unseen = sorted(set(all_report_types) - DOE.KNOWN_REPORT_TYPE_RAW_VALUES - {"None"})
    report["reportTypesNeverSeenBefore"] = unseen

    verdict = classify_verdict(report)
    report["verdict"] = verdict

    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

    served = [e for e in report["samples"].values() if e.get("rows")]
    all_fields_present = all(
        all(pct > 0 for pct in (e.get("fieldsPresentPct") or {}).values())
        for e in served)
    print("\n=== 판정 ===")
    print(f"  응답 샘플 {len(served)}/{len(samples)}")
    print(f"  모든 기대 필드 존재: {'예' if served and all_fields_present else '아니오'}")
    if unseen:
        print(f"  처음 보는 report_tp 값: {unseen} — "
              f"dart_ownership_events.KNOWN_REPORT_TYPE_RAW_VALUES에 없습니다. "
              f"reportTypeRaw로는 그대로 보존되지만, 확인 전에는 reportType으로 "
              f"번역하지 마세요")
    print(f"  verdict: {verdict}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"verdict={verdict}\n")

    print(f"\nwrote {args.output}")
    return 0 if verdict == "SERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
