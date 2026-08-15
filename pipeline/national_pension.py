"""National Pension Service official fund-allocation snapshot.

The NPS-wide allocation and the SEC 13F are different disclosure scopes.  This
module reads the official NPS Investment Management homepage for the former;
``institutional_13f`` reads the SEC filing for the latter.  A checked official
cache is allowed only as an explicitly labelled fallback, never as live data.
"""
from __future__ import annotations

import json
import calendar
import re
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

from .config import REPO_ROOT


SOURCE_URL = "https://fund.nps.or.kr/main.do"
CACHE_PATH = REPO_ROOT / "data" / "national_pension_cache.json"
USER_AGENT = "InvestmentResearchDashboard/1.1 (official NPS disclosure reader)"
ASSET_LABELS = {"금융부문", "국내주식", "국내채권", "해외주식", "해외채권", "대체투자", "단기자금", "복지 ·기타 부문"}


def _fetch() -> str:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_official_page(html: str) -> dict:
    date_match = re.search(
        r"기금\s*포트폴리오\s*<span[^>]*class=[\"']date[\"'][^>]*>\s*(\d{4})년\s*(\d+)월\s*말\s*기준",
        html,
        flags=re.I,
    )
    if not date_match:
        raise ValueError("NPS portfolio disclosure date not found")
    year, month = map(int, date_match.groups())

    caption_at = html.find("기금 포트폴리오 구성별 규모")
    if caption_at < 0:
        raise ValueError("NPS allocation table not found")
    table_end = html.find("</table>", caption_at)
    table = html[caption_at:table_end]
    allocations = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.I | re.S):
        cells = [_text(cell) for cell in re.findall(r"<(?:th|td)[^>]*>(.*?)</(?:th|td)>", row_html, flags=re.I | re.S)]
        if len(cells) < 3:
            continue
        label = cells[0].replace("·기타", " ·기타")
        values = [float(x.replace(",", "")) for x in re.findall(r"-?\d+(?:,\d{3})*(?:\.\d+)?", " ".join(cells[1:3]))]
        if label not in ASSET_LABELS or len(values) < 2:
            continue
        allocations.append({"labelKo": label, "valueTrillionKrw": values[0], "weightPct": values[1]})
    investable = [x for x in allocations if x["labelKo"] not in {"금융부문", "복지 ·기타 부문"}]
    if len(investable) < 6:
        raise ValueError("NPS allocation rows incomplete")
    total_match = re.search(r'<div class="pf-total">\s*<em>([\d,.]+)</em>', html[caption_at:table_end + 2500], flags=re.I | re.S)
    total = float(total_match.group(1).replace(",", "")) if total_match else round(sum(x["valueTrillionKrw"] for x in allocations if x["labelKo"] != "금융부문"), 1)
    overseas_equity = next((x for x in investable if x["labelKo"] == "해외주식"), None)
    domestic_equity = next((x for x in investable if x["labelKo"] == "국내주식"), None)
    return {
        "status": "AVAILABLE",
        "sourceMode": "LIVE_NPS",
        "source": "국민연금기금운용본부",
        "sourceUrl": SOURCE_URL,
        "asOf": f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}",
        "asOfLabelKo": f"{year}년 {month}월 말",
        "totalFundTrillionKrw": total,
        "allocations": investable,
        "equityWeightPct": round((domestic_equity or {}).get("weightPct", 0) + (overseas_equity or {}).get("weightPct", 0), 1),
        "overseasEquityWeightPct": (overseas_equity or {}).get("weightPct"),
        "provisional": True,
        "scopeKo": "국민연금 전체 기금의 자산군별 잠정 운용 현황",
        "limitationKo": "SEC 13F의 미국 보고대상 주식 범위와 다르며, 두 자료의 기준일도 서로 다를 수 있습니다.",
    }


def _read_cache(path: Path) -> dict | None:
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        return cached if cached.get("asOf") and cached.get("allocations") else None
    except (OSError, ValueError, AttributeError):
        return None


def build(cache_path: str | Path = CACHE_PATH) -> dict:
    path = Path(cache_path)
    retrieved = datetime.now(timezone.utc).isoformat()
    try:
        result = parse_official_page(_fetch())
        result["retrievedAt"] = retrieved
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    except Exception as exc:
        cached = _read_cache(path)
        if cached:
            return {
                **cached,
                "status": "CACHED_OFFICIAL",
                "sourceMode": "CACHED_NPS",
                "liveFetchError": type(exc).__name__,
                "noteKo": "국민연금 홈페이지 실시간 호출이 실패해 마지막으로 검증한 공식 공시를 표시합니다.",
            }
        return {
            "status": "UNAVAILABLE",
            "source": "국민연금기금운용본부",
            "sourceUrl": SOURCE_URL,
            "allocations": [],
            "error": type(exc).__name__,
            "noteKo": "국민연금 공식 원문과 검증된 공식 캐시를 모두 불러오지 못했습니다.",
        }
