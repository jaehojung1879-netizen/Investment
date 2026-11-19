"""Collect DART ``list.json`` disclosure indexes for the ever-PIT-Top120 KR issuers.

Outcome-blind: only disclosure metadata (receipt number, receipt date, report
name) is read. No price, return, label or model output is touched.

Usage (needs ``DART_API_KEY`` in the environment; the key is never written)::

    python research/alpha_mechanism_sprint_v1/collect.py \
        --universe <collection-universe.json> --out <dir> [--max-calls N]

The output directory holds one gzipped JSON-lines file per issuer and
publication type plus ``collect-state.json``. An issuer/type is marked
complete only after every served page was read; a failure mid-walk leaves it
incomplete so the next run restarts it from page 1.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINT = "https://opendart.fss.or.kr/api/list.json"
BEGIN = "20121001"
END = "20261031"
TYPES = ("I", "A")
KEEP_FIELDS = ("corp_code", "corp_name", "stock_code", "corp_cls", "report_nm",
               "rcept_no", "flr_nm", "rcept_dt", "rm")


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class CallBudgetExhausted(RuntimeError):
    pass


class SourceError(RuntimeError):
    def __init__(self, message: str, status: str | None = None):
        super().__init__(message)
        self.status = status


STOP_STATUSES = {"010", "011", "012", "020", "021", "800", "901"}  # key, quota, maintenance


def fetch_page(key: str, corp_code: str, pblntf_ty: str, page: int, *, timeout: int = 30) -> dict:
    query = urllib.parse.urlencode({
        "crtfc_key": key, "corp_code": corp_code, "bgn_de": BEGIN, "end_de": END,
        "pblntf_ty": pblntf_ty, "page_no": page, "page_count": 100,
    })
    with urllib.request.urlopen(f"{ENDPOINT}?{query}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def walk(fetch, corp_code: str, pblntf_ty: str, budget: dict, lock=None) -> list[dict]:
    """Every page of one issuer/type. ``013`` (no data) is an empty answer."""
    rows: dict[str, dict] = {}
    page, total_page, total_count = 1, None, None
    while True:
        with lock or _NullLock():
            if budget["calls"] >= budget["max"]:
                raise CallBudgetExhausted(f"{corp_code}/{pblntf_ty} page {page}")
            budget["calls"] += 1
        payload = fetch(corp_code, pblntf_ty, page)
        status = payload.get("status")
        if status == "013":
            return []
        if status != "000":
            raise SourceError(f"{corp_code}/{pblntf_ty}: {status} {payload.get('message')}", status)
        try:
            served_pages, served_count = int(payload["total_page"]), int(payload["total_count"])
        except (KeyError, TypeError, ValueError) as error:
            raise SourceError(f"{corp_code}/{pblntf_ty}: bad pagination {error}") from error
        if total_page is None:
            total_page, total_count = served_pages, served_count
        elif (served_pages, served_count) != (total_page, total_count):
            raise SourceError(f"{corp_code}/{pblntf_ty}: result set changed mid-walk")
        for row in payload.get("list", []):
            rows[row["rcept_no"]] = {field: (row.get(field) or "").strip() for field in KEEP_FIELDS}
        if page >= total_page:
            break
        page += 1
    if len(rows) != total_count:
        raise SourceError(f"{corp_code}/{pblntf_ty}: {len(rows)} rows != total_count {total_count}")
    return sorted(rows.values(), key=lambda r: r["rcept_no"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-calls", type=int, default=4000)
    parser.add_argument("--sleep", type=float, default=0.12)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    key = os.environ.get("DART_API_KEY")
    if not key:
        print("DART_API_KEY missing", file=sys.stderr)
        return 2
    universe = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / "collect-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"complete": {}, "errors": {}}
    budget = {"calls": 0, "max": args.max_calls}

    def fetch(corp_code, pblntf_ty, page):
        time.sleep(args.sleep)
        for attempt in range(4):
            try:
                return fetch_page(key, corp_code, pblntf_ty, page)
            except (OSError, ValueError) as error:  # network / decode
                if attempt == 3:
                    raise SourceError(f"{corp_code}/{pblntf_ty}: network {type(error).__name__}") from error
                time.sleep(2 ** (attempt + 1))
        raise AssertionError("unreachable")

    stop = "WORK_LIST_EXHAUSTED"
    lock = threading.Lock()
    tasks = []
    for issuer in sorted(universe["issuers"], key=lambda i: i["corpCode"]):
        for pblntf_ty in TYPES:
            task = f"{issuer['corpCode']}:{pblntf_ty}"
            path = out / f"{issuer['corpCode']}-{pblntf_ty}.jsonl.gz"
            if task in state["complete"] or path.exists():  # a file is written only after a full walk
                state["complete"].setdefault(task, None)
                continue
            tasks.append((task, issuer["corpCode"], pblntf_ty, path))

    def run(item):
        task, corp_code, pblntf_ty, path = item
        try:
            rows = walk(fetch, corp_code, pblntf_ty, budget, lock)
        except SourceError as error:
            with lock:
                state["errors"][task] = str(error)
            if error.status in STOP_STATUSES:
                raise  # key / quota / maintenance refusal stops the run
            return
        tmp = path.with_suffix(".tmp")
        with gzip.GzipFile(tmp, "wb", mtime=0) as handle:
            for row in rows:
                handle.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        tmp.rename(path)
        with lock:
            state["complete"][task] = len(rows)
            state["errors"].pop(task, None)

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in [pool.submit(run, item) for item in tasks]:
                future.result()
    except CallBudgetExhausted as error:
        stop = f"CALL_BUDGET_EXHAUSTED at {error}"
    except SourceError as error:
        stop = f"REFUSED: {error}"
    finally:
        state["lastRun"] = {"calls": budget["calls"], "stopReason": stop,
                            "tasksComplete": len(state["complete"]),
                            "tasksTotal": len(universe["issuers"]) * len(TYPES)}
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True))
    print(json.dumps(state["lastRun"], ensure_ascii=False))
    return 0 if stop == "WORK_LIST_EXHAUSTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
