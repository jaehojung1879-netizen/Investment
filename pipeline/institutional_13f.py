"""SEC Form 13F snapshots for a small, explicit manager watchlist.

This is a disclosure reader, not an investment signal.  A 13F reports selected
US-listed long securities as of a quarter end and may be filed up to 45 days
later.  It does not reveal cash, shorts, most derivatives, private assets, or
trades made after the report date.  The output therefore always carries both
the report date and filing date and never calls a disclosed position "current".
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .config import REPO_ROOT
from .sec_access import BLOCK_MARKERS, decode_body


REGISTRY_PATH = REPO_ROOT / "data" / "institutional_managers.json"
CACHE_PATH = REPO_ROOT / "data" / "institutional_13f_cache.json"
SEC_DATA = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_USER_AGENT = (
    "Investment Research Dashboard "
    "jaehojung1879-netizen@users.noreply.github.com"
)
_LAST_REQUEST_AT = 0.0
_MIN_REQUEST_INTERVAL = 0.16


def _request(url: str) -> bytes:
    """Fetch one SEC resource with fair-access pacing and bounded retries."""
    global _LAST_REQUEST_AT
    wait = _MIN_REQUEST_INTERVAL - (time.monotonic() - _LAST_REQUEST_AT)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT),
            "Accept": "application/json, application/xml, text/xml, */*",
            "Accept-Language": "en-US,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = decode_body(response.read(), response.headers.get("Content-Encoding"))
            _LAST_REQUEST_AT = time.monotonic()
            prefix = body[:2000].decode("utf-8", "replace").lower()
            if any(marker.lower() in prefix for marker in BLOCK_MARKERS):
                raise ValueError("SEC refused request in response body")
            return body
        except urllib.error.HTTPError as exc:
            _LAST_REQUEST_AT = time.monotonic()
            # A policy refusal or rate limit is not an invitation to retry.
            # Wait for the next scheduled run; retry only transient server failures.
            if exc.code not in {500, 502, 503, 504} or attempt == 2:
                raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == 2:
                raise
        time.sleep(1.5 * (2 ** attempt))
    raise RuntimeError("SEC request retry loop exhausted")


def _fetch_json(url: str) -> dict:
    return json.loads(_request(url).decode("utf-8"))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, name: str) -> str | None:
    wanted = name.lower()
    for child in node.iter():
        if _local(child.tag) == wanted and child.text:
            return child.text.strip()
    return None


def _number(value: str | None) -> float:
    try:
        return float((value or "0").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def parse_information_table(raw: bytes) -> list[dict]:
    """Parse both modern namespaced and older namespace-free 13F XML."""
    root = ET.fromstring(raw)
    if _local(root.tag) != "informationtable":
        raise ValueError("not a 13F information table")
    rows: list[dict] = []
    for node in root.iter():
        if _local(node.tag) != "infotable":
            continue
        issuer = _child_text(node, "nameOfIssuer")
        cusip = _child_text(node, "cusip")
        if not issuer or not cusip:
            raise ValueError("incomplete 13F position")
        value = _child_text(node, "value")
        shares = _child_text(node, "sshPrnamt")
        if value is None or shares is None:
            raise ValueError("missing 13F position value or shares")
        try:
            value_usd, share_count = int(value.replace(",", "")), int(shares.replace(",", ""))
        except ValueError as exc:
            raise ValueError("invalid 13F position amount") from exc
        if value_usd < 0 or share_count < 0:
            raise ValueError("negative 13F position amount")
        rows.append({
            "issuer": issuer,
            "titleClass": _child_text(node, "titleOfClass") or "—",
            "cusip": cusip,
            "valueUsd": value_usd,
            "shares": share_count,
            "shareType": _child_text(node, "sshPrnamtType") or "SH",
            "putCall": (_child_text(node, "putCall") or "").upper() or None,
        })
    if not rows:
        raise ValueError("empty 13F information table")
    return rows


def _recent_13f_filings(submissions: dict) -> list[dict]:
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    keys = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument")
    count = min((len(recent.get(k) or []) for k in keys), default=0)
    candidates = []
    for i in range(count):
        form = recent["form"][i]
        if form not in {"13F-HR", "13F-HR/A"}:
            continue
        candidates.append({k: recent[k][i] for k in keys})

    # Preserve the filing chain, including NEW HOLDINGS amendments.
    for row in candidates:
        date.fromisoformat(row["reportDate"])
        date.fromisoformat(row["filingDate"])
        if row["filingDate"] < row["reportDate"]:
            raise ValueError("filing precedes report date")
    candidates.sort(key=lambda x: (x["reportDate"], x["filingDate"]), reverse=True)
    reports = sorted({row["reportDate"] for row in candidates}, reverse=True)[:2]
    return [row for row in candidates if row["reportDate"] in reports]


def _information_table_url(cik: str, filing: dict, fetch_json: Callable[[str], dict]) -> str:
    cik_plain = str(int(cik))
    accession_plain = filing["accessionNumber"].replace("-", "")
    base = f"{SEC_ARCHIVES}/{cik_plain}/{accession_plain}"
    index = fetch_json(f"{base}/index.json")
    items = ((index.get("directory") or {}).get("item") or [])
    xml = [
        item.get("name") for item in items
        if str(item.get("name") or "").lower().endswith(".xml")
        and str(item.get("name") or "").lower() != "primary_doc.xml"
        and ("information table" in str(item.get("type") or "").lower()
             or "info" in str(item.get("name") or "").lower()
             or "form13f" in str(item.get("name") or "").lower())
    ]
    # Some filers (notably Berkshire) use a numeric information-table file
    # name and SEC's index reports every attachment as text.gif.  A 13F-HR
    # filing has one cover XML plus one information-table XML, so the remaining
    # non-cover XML is the deterministic fallback.
    if not xml:
        xml = [
            item.get("name") for item in items
            if str(item.get("name") or "").lower().endswith(".xml")
            and str(item.get("name") or "").lower() != "primary_doc.xml"
        ]
    if not xml:
        raise ValueError("SEC filing has no information-table XML")
    return f"{base}/{xml[0]}"


def _position_key(row: dict) -> tuple[str, str, str, str]:
    return (row["cusip"], row.get("putCall") or "", row.get("titleClass") or "",
            row.get("shareType") or "")


def _aggregate(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str, str], dict] = {}
    for row in rows:
        key = _position_key(row)
        if key not in grouped:
            grouped[key] = dict(row)
        else:
            grouped[key]["valueUsd"] += row["valueUsd"]
            grouped[key]["shares"] += row["shares"]
    return sorted(grouped.values(), key=lambda x: x["valueUsd"], reverse=True)


def _changes(current: list[dict], previous: list[dict]) -> dict:
    now = {_position_key(x): x for x in current}
    before = {_position_key(x): x for x in previous}
    out = {"new": [], "increased": [], "decreased": [], "exited": []}
    for key in sorted(set(now) | set(before)):
        cur, prev = now.get(key), before.get(key)
        template = cur or prev
        item = {
            "issuer": template["issuer"], "titleClass": template["titleClass"],
            "cusip": template.get("cusip"),
            "putCall": template.get("putCall"),
            "currentShares": cur["shares"] if cur else 0,
            "previousShares": prev["shares"] if prev else 0,
            "currentValueUsd": cur["valueUsd"] if cur else 0,
            "previousValueUsd": prev["valueUsd"] if prev else 0,
        }
        if cur and not prev:
            bucket = "new"
        elif prev and not cur:
            bucket = "exited"
        elif item["currentShares"] > item["previousShares"] * 1.005:
            bucket = "increased"
        elif item["currentShares"] < item["previousShares"] * 0.995:
            bucket = "decreased"
        else:
            continue
        base = item["previousShares"]
        item["shareChangePct"] = None if base == 0 else round(
            (item["currentShares"] / base - 1) * 100, 1
        )
        out[bucket].append(item)
    for bucket in out:
        out[bucket] = sorted(
            out[bucket],
            key=lambda x: max(x["currentValueUsd"], x["previousValueUsd"]),
            reverse=True,
        )[:8]
    return out


def _build_manager(manager: dict, fetch_json=_fetch_json, fetch_bytes=_request) -> dict:
    cik = manager["cik"].zfill(10)
    submissions = fetch_json(f"{SEC_DATA}/submissions/CIK{cik}.json")
    filings = _recent_13f_filings(submissions)
    if not filings:
        raise ValueError("no recent 13F-HR filing")

    parsed = []
    for report in sorted({f["reportDate"] for f in filings}, reverse=True):
        chain = [f for f in filings if f["reportDate"] == report]
        # SEC submissions are newest-first, including same-day filings.
        # Reverse the stable descending order for chronological application.
        rows = None
        for filing in reversed(chain):
            table_url = _information_table_url(cik, filing, fetch_json)
            added = parse_information_table(fetch_bytes(table_url))
            if filing["form"] == "13F-HR":
                rows = added
            else:
                accession = filing["accessionNumber"].replace("-", "")
                cover_name = filing["primaryDocument"].rsplit("/", 1)[-1]
                cover = ET.fromstring(fetch_bytes(
                    f"{SEC_ARCHIVES}/{int(cik)}/{accession}/{cover_name}"
                ))
                amendment = (_child_text(cover, "amendmentType") or "").upper()
                if amendment == "RESTATEMENT":
                    rows = added
                elif amendment == "NEW HOLDINGS" and rows is not None:
                    rows = rows + added
                else:
                    raise ValueError("unresolved 13F amendment chain")
            time.sleep(0.12)
        if rows is None:
            raise ValueError("missing 13F original or restatement")
        parsed.append((chain[0], _aggregate(rows)))

    current_filing, current = parsed[0]
    previous_filing, previous = parsed[1] if len(parsed) > 1 else ({}, [])
    consecutive = previous_filing.get("reportDate") == prior_quarter(current_filing["reportDate"])
    total = sum(x["valueUsd"] for x in current)
    for row in current:
        row["portfolioWeightPct"] = round(row["valueUsd"] / total * 100, 2) if total else 0.0
    accession_plain = current_filing["accessionNumber"].replace("-", "")
    filing_url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_plain}/"
        f"{current_filing['primaryDocument']}"
    )
    return {
        **manager,
        "status": "AVAILABLE",
        "sourceMode": "LIVE_SEC",
        "reportDate": current_filing["reportDate"],
        "filingDate": current_filing["filingDate"],
        "previousReportDate": previous_filing.get("reportDate"),
        "filingUrl": filing_url,
        "accessionNumber": current_filing["accessionNumber"],
        "totalValueUsd": round(total),
        "positionCount": len(current),
        "top5WeightPct": round(sum(x["portfolioWeightPct"] for x in current[:5]), 1),
        "topHoldings": current[:10],
        "changes": _changes(current, previous) if previous and consecutive else None,
    }


def prior_quarter(report: str) -> str:
    d = date.fromisoformat(report)
    return (date(d.year, ((d.month - 1) // 3) * 3 + 1, 1) - timedelta(days=1)).isoformat()


def expected_report_date(today: date) -> str:
    """Most recent quarter whose normal filing deadline has passed (US date)."""
    report = prior_quarter(today.isoformat())
    while True:
        deadline = date.fromisoformat(report) + timedelta(days=45)
        # Washington's Birthday (third Monday in February) can extend Q4.
        while deadline.weekday() >= 5 or (
            deadline.month == 2 and deadline.weekday() == 0 and 15 <= deadline.day <= 21
        ):
            deadline += timedelta(days=1)
        if today > deadline:
            return report
        report = prior_quarter(report)


def snapshot_key(row: dict) -> tuple[str, str, str]:
    return (row.get("reportDate") or "", row.get("filingDate") or "",
            row.get("retrievedAt") or "")


def valid_snapshot(row: dict, manager: dict) -> bool:
    try:
        return (
            row["id"] == manager["id"] and row["cik"] == manager["cik"]
            and date.fromisoformat(row["reportDate"]) <= date.fromisoformat(row["filingDate"])
            and str(row["filingUrl"]).startswith("https://www.sec.gov/Archives/")
            and row["positionCount"] > 0 and row["totalValueUsd"] >= 0
            and bool(row["topHoldings"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def persisted_cache() -> dict:
    """Read the previous successful Pages publication, without touching the ledger."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return {}
    try:
        result = subprocess.run(
            ["git", "show", "origin/signal-history:state/institutional_13f_cache.json"],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=20,
        )
        payload = json.loads(result.stdout)
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def merge_snapshots(old: dict, new: dict, registry: list[dict]) -> dict:
    """Preserve each institution's latest valid disclosure independently."""
    merged = {}
    for manager in registry:
        key = manager["id"]
        candidates = [doc[key] for doc in (old, new)
                      if key in doc and valid_snapshot(doc[key], manager)]
        if candidates:
            merged[key] = max(candidates, key=snapshot_key)
    return merged


def _read_cache(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(path: Path, managers: dict[str, dict], fetched_at: str) -> None:
    payload = {
        "source": "SEC EDGAR Form 13F-HR",
        "fetchedAt": fetched_at,
        "managers": managers,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as tmp:
        tmp.write(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        temp_path = Path(tmp.name)
    try:
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def build(registry_path: str | Path = REGISTRY_PATH,
          cache_path: str | Path | None = CACHE_PATH) -> dict:
    managers = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    use_cache = Path(registry_path).resolve() == REGISTRY_PATH.resolve() and cache_path is not None
    cache_file = Path(cache_path) if cache_path is not None else CACHE_PATH
    cache_doc = _read_cache(cache_file) if use_cache else {}
    cached_managers = dict(cache_doc.get("managers") or {})
    if use_cache and cache_file.resolve() == CACHE_PATH.resolve():
        persisted = persisted_cache()
        cached_managers = merge_snapshots(cached_managers, persisted.get("managers") or {}, managers)
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()
    # At 00:00 UTC it may still be the SEC filing day in New York.
    expected = expected_report_date(now.astimezone(ZoneInfo("America/New_York")).date())
    output = []
    live_count = 0
    cache_changed = False
    for manager in managers:
        try:
            current = _build_manager(manager)
            current["retrievedAt"] = fetched_at
            cached = cached_managers.get(manager["id"])
            if cached and snapshot_key(current)[:2] < snapshot_key(cached)[:2]:
                raise ValueError("SEC snapshot would regress cached disclosure")
            output.append(current)
            if use_cache:
                # Do not rewrite the official snapshot on a no-change poll.
                comparable = {k: v for k, v in current.items() if k != "retrievedAt"}
                old_comparable = {k: v for k, v in (cached or {}).items() if k != "retrievedAt"}
                if comparable != old_comparable:
                    cached_managers[manager["id"]] = current
                    cache_changed = True
            live_count += 1
        except Exception as exc:
            print(f"  SEC 13F {manager.get('id')}: {type(exc).__name__}"
                  + (f" HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else ""))
            cached = cached_managers.get(manager.get("id")) if use_cache else None
            if cached and cached.get("reportDate") and cached.get("filingUrl"):
                output.append({
                    **cached,
                    **{k: v for k, v in manager.items() if k in {"id", "name", "managerKo", "cik", "featured"}},
                    "status": "CACHED_OFFICIAL",
                    "sourceMode": "CACHED_SEC",
                    "cacheFetchedAt": cached.get("retrievedAt") or cache_doc.get("fetchedAt"),
                    "liveFetchError": type(exc).__name__,
                    "noteKo": "SEC 실시간 호출이 실패해 마지막으로 검증된 공식 공시 스냅샷을 표시합니다.",
                })
            else:
                output.append({
                    **manager, "status": "UNAVAILABLE", "error": type(exc).__name__,
                    "noteKo": "SEC 원문과 검증된 공식 캐시를 모두 불러오지 못했습니다.",
                })
    if use_cache and (cache_changed or cached_managers != cache_doc.get("managers", {})):
        _write_cache(cache_file, cached_managers, fetched_at)
    available = [m for m in output if m.get("status") in {"AVAILABLE", "CACHED_OFFICIAL"}]
    latest_report = max((m["reportDate"] for m in available), default=None)
    for manager in available:
        manager["reportRecency"] = (
            "LATEST_TRACKED_QUARTER" if manager["reportDate"] == latest_report
            else "OLDER_LAST_AVAILABLE"
        )
    overdue = 0
    for manager in output:
        manager["expectedReportDate"] = expected
        manager["freshnessStatus"] = (
            "NO_DISCLOSURE" if not manager.get("reportDate")
            else "OVERDUE_OR_NOT_FILED" if manager["reportDate"] < expected
            else "CURRENT_DUE_QUARTER"
        )
        overdue += manager["freshnessStatus"] != "CURRENT_DUE_QUARTER"
    return {
        "expectedReportDate": expected,
        "overdueOrMissingCount": overdue,
        "refreshStatus": ("LIVE" if live_count == len(output) and output
                          else "PARTIAL" if live_count else "NO_LIVE_DATA"),
        "source": "SEC EDGAR Form 13F-HR",
        "sourceUrl": "https://www.sec.gov/edgar/search/",
        "fetchedAt": fetched_at,
        "status": "AVAILABLE" if available else "UNAVAILABLE",
        "availableCount": len(available),
        "liveCount": live_count,
        "cachedCount": sum(m.get("status") == "CACHED_OFFICIAL" for m in available),
        "managerCount": len(output),
        "latestReportDate": latest_report,
        "laggedManagerCount": sum(m.get("reportRecency") == "OLDER_LAST_AVAILABLE" for m in available),
        "managers": output,
        "methodKo": (
            "분기말 보유 주식 수를 직전 분기와 비교합니다. 금액 변화는 주가 영향이 섞이므로 "
            "매수·매도 판정에 쓰지 않습니다."
        ),
        "limitationKo": (
            "13F는 분기말 기준이며 통상 최대 45일 뒤 공개됩니다. 미국 보고대상 롱 포지션 중심이라 "
            "현금·공매도·비상장·일부 해외자산과 공개 후 거래는 보이지 않습니다."
        ),
    }


if __name__ == "__main__":
    result = build()
    print(json.dumps({k: v for k, v in result.items() if k != "managers"}, ensure_ascii=False))
    raise SystemExit(0 if result["liveCount"] else 1)
