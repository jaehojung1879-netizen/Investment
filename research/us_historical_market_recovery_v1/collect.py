"""Acquire existing pinned candidates and new Yahoo chart responses privately.

This is acquisition, not security admission. No raw vendor bytes belong in git.
Run with an uploaded request list and the existing repository recovery audit.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time
from urllib import error, parse, request

AS_OF = "2026-11-13"
ALIASES = {"ABC": "COR", "CTL": "LUMN", "FB": "META", "PKI": "RVTY",
           "RE": "EG", "BLL": "BALL", "WLTW": "WTW"}
FOLLOWUPS = ("AMD", "ABBV", "BMY", "CI", "FRCB", "SIVBQ", "SBNY", "BMY-RT", "SPY")
ROOT = Path(__file__).resolve().parents[2]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def private_root(path):
    path = Path(path).resolve()
    if path.is_relative_to(ROOT) or any((p / ".git").exists() for p in (path, *path.parents)):
        raise ValueError("RAW_DATA_MUST_STAY_OUTSIDE_GIT_CHECKOUTS")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    (path / "objects").mkdir(exist_ok=True, mode=0o700)
    return path


class Collector:
    def __init__(self, root, *, delay=.4):
        self.root = private_root(root)
        self.delay = delay
        self.lock = threading.Lock()
        self.stopped = {}
        self.next_request = {}

    def get(self, item):
        url = item["url"]
        host = parse.urlsplit(url).hostname
        if host not in {"raw.githubusercontent.com", "query1.finance.yahoo.com"}:
            raise ValueError("SOURCE_NOT_IN_ACQUISITION_CONTRACT")
        with self.lock:
            if host in self.stopped:
                return {**item, "status": "NOT_REQUESTED_PROVIDER_STOPPED", "reason": self.stopped[host]}
            wait = max(0, self.next_request.get(host, 0) - time.monotonic())
            self.next_request[host] = time.monotonic() + wait + self.delay
        time.sleep(wait)
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            with request.urlopen(request.Request(url, headers={"User-Agent": "InvestmentResearchData/1.0"}), timeout=25) as r:
                code, raw = r.status, r.read(8 * 1024 * 1024 + 1)
        except error.HTTPError as exc:
            code, raw = exc.code, exc.read(8192)
        except (error.URLError, TimeoutError, OSError) as exc:
            return {**item, "status": "TRANSPORT_ERROR", "error": type(exc).__name__, "acquired_at": stamp}
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("SOURCE_RESPONSE_TOO_LARGE")
        key = sha(raw)
        (self.root / "objects" / key).write_bytes(raw)
        result = {**item, "status": code, "bytes": len(raw), "sha256": key, "object": "objects/" + key, "acquired_at": stamp}
        if code in {401, 403, 429} or code >= 500:
            with self.lock:
                self.stopped[host] = "HTTP_" + str(code)
        if item.get("expected_sha256"):
            result["matches_existing_bytes"] = key == item["expected_sha256"]
        if code == 200 and item["source"] == "YAHOO_CHART":
            try:
                payload = json.loads(raw)
                chart = payload["chart"]["result"][0]
                dates = [datetime.fromtimestamp(t, timezone.utc).date().isoformat() for t in chart.get("timestamp", [])]
                meta = chart["meta"]
                result.update(rows=len(dates), first=min(dates) if dates else None, last=max(dates) if dates else None,
                              metadata={k: meta.get(k) for k in ("symbol", "currency", "exchangeName", "instrumentType", "firstTradeDate", "longName", "shortName")},
                              dividends=len(chart.get("events", {}).get("dividends", {})),
                              splits=len(chart.get("events", {}).get("splits", {})))
            except (ValueError, KeyError, TypeError, IndexError):
                result["schema_error"] = "NO_CHART_SERIES"
        return result

    def run(self, items, name, workers=2):
        destination = self.root / (name + ".json")
        prior = json.loads(destination.read_bytes()) if destination.exists() else []
        done = {r["url"] for r in prior}
        results = list(prior)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for row in pool.map(self.get, [r for r in items if r["url"] not in done]):
                results.append(row)
                destination.write_bytes(canonical(results))
                if len(results) % 25 == 0:
                    print(json.dumps({"collection": name, "requests_recorded": len(results)}, ensure_ascii=False), flush=True)
        return results


def chart_request(ticker, start, end, *, audit_identifier=None):
    def epoch(day):
        return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    # End is exclusive; midnight next day includes the requested final US close.
    from datetime import timedelta
    end_day = (datetime.fromisoformat(min(end, AS_OF)) + timedelta(days=1)).date().isoformat()
    query = parse.urlencode({"period1": epoch(start), "period2": epoch(end_day), "interval": "1d",
                            "events": "div,splits", "includeAdjustedClose": "true"})
    return {"ticker": ticker, "audit_identifier": audit_identifier or ticker, "source": "YAHOO_CHART",
            "requested_start": start, "requested_end": min(end, AS_OF),
            "url": "https://query1.finance.yahoo.com/v8/finance/chart/" + parse.quote(ticker) + "?" + query}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--existing-audit", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = json.loads(args.input.read_bytes())
    if len(rows) != 212 or len({r["audit_identifier"] for r in rows}) != 212:
        raise ValueError("REQUEST_COHORT_MUST_BE_EXACTLY_212")
    old = json.loads(args.existing_audit.read_bytes())
    cohort = {r["audit_identifier"] for r in rows}
    candidates = [{"source": r["source"], "ticker": r["ticker"], "url": r["url"], "expected_sha256": r["sha256"]}
                  for r in old["acquisition"] if r["ticker"] in cohort and r.get("status") == 200]
    collector = Collector(args.private_root)
    # Old candidates remain old baseline evidence, even when their bytes had to be reacquired.
    collector.run(candidates, "baseline_reacquisition", workers=3)
    charts = []
    for row in rows:
        symbol = row["audit_identifier"]
        start, end = row["requested_window_start_252_session_warmup"], row["requested_window_end_252_session_followup"]
        charts.append(chart_request(symbol, start, end))
        if symbol in ALIASES:
            charts.append(chart_request(ALIASES[symbol], start, end, audit_identifier=symbol))
    charts.extend(chart_request(t, "2011-12-29", AS_OF) for t in FOLLOWUPS)
    collector.run(charts, "new_charts", workers=2)


if __name__ == "__main__":
    main()
