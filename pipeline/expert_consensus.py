"""Expert / house-view consensus — verified sources, weighted median, dispersion.

Deliberately NOT a headline scraper. It reads human-verified summaries of named
institutions' published outlooks (data/expert_views.json) and computes, per
theme:

  * a weighted MEDIAN stance (robust to one outlier vs a plain mean),
  * dispersion (do institutions agree or disagree?),
  * the number of distinct institutions behind it,
  * the freshest update, and per-view source links,
  * STALE flags past each view's staleAfterDays,
  * a standing 'counter-case' for every consensus.

Honesty guards:
  * Only ``verified=true`` views with a real ``stance`` are aggregated —
    unverified theme stubs are surfaced as "awaiting verification", never as a
    stance. Nothing is fabricated.
  * companyIR is never treated as an independent expert view (down-weighted and
    labelled).
  * One view per institution+team+theme (the freshest) — the same house can't
    be double-counted by publishing three reports.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import REPO_ROOT

SOURCES_PATH = REPO_ROOT / "data" / "expert_sources.json"
VIEWS_PATH = REPO_ROOT / "data" / "expert_views.json"

COMPANY_IR_WEIGHT = 0.25  # IR is not an independent expert view

# Standing counter-cases per theme so a consensus never ships without its risk.
COUNTER_CASE = {
    "AI/Semiconductors": "기대·CAPEX 집중 → 수익화 지연 시 급격한 디레이팅 위험",
    "US Growth": "정책·공급 충격, 고용 둔화 시 밸류에이션 부담",
    "Rates/Inflation": "실질금리 고착·재정 공급 확대 시 듀레이션 손실",
    "Credit Quality": "타이트한 스프레드 → 신용 사이클 반전 시 비대칭 손실",
    "Korea": "환율·에너지·지정학 및 반도체 사이클 의존도",
}


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _weighted_median(pairs: list[tuple[float, float]]) -> float | None:
    """pairs = [(value, weight)]. Returns the weighted median."""
    if not pairs:
        return None
    pairs = sorted(pairs, key=lambda x: x[0])
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return float(v)
    return float(pairs[-1][0])


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except Exception:
        return None


def build(sources: dict | None = None, views: dict | None = None, now: datetime | None = None) -> dict:
    src = (sources or _load(SOURCES_PATH)).get("sources", [])
    vlist = (views or _load(VIEWS_PATH)).get("views", [])
    src_by_id = {s["id"]: s for s in src}

    verified, unverified, stale = [], [], []
    for v in vlist:
        is_stale = False
        age = _days_since(v.get("verifiedAt") or v.get("publishedAt"))
        if v.get("verified") and v.get("stance") is not None:
            if age is not None and v.get("staleAfterDays") and age > v["staleAfterDays"]:
                is_stale = True
                stale.append(v)
            else:
                verified.append(v)
        else:
            unverified.append(v)
        v["_stale"] = is_stale
        v["_ageDays"] = age

    # Deduplicate to one view per (sourceId, theme): keep the freshest verified.
    dedup: dict[tuple, dict] = {}
    for v in verified:
        key = (v.get("sourceId"), v.get("theme"))
        cur = dedup.get(key)
        if cur is None or (v.get("_ageDays") or 1e9) < (cur.get("_ageDays") or 1e9):
            dedup[key] = v
    deduped = list(dedup.values())

    # Aggregate by theme.
    themes: dict[str, dict] = {}
    for v in deduped:
        theme = v.get("theme") or "Uncategorized"
        s = src_by_id.get(v.get("sourceId"), {})
        w = float(s.get("weight", 1.0))
        if v.get("sourceType") == "companyIR" or s.get("sourceType") == "companyIR":
            w *= COMPANY_IR_WEIGHT
        themes.setdefault(theme, {"stances": [], "institutions": set(), "views": []})
        themes[theme]["stances"].append((float(v["stance"]), w))
        themes[theme]["institutions"].add(s.get("institution", v.get("sourceId")))
        themes[theme]["views"].append({
            "institution": s.get("institution", v.get("sourceId")),
            "sourceType": v.get("sourceType") or s.get("sourceType"),
            "stance": v.get("stance"), "summary": v.get("summary"),
            "url": v.get("url"), "publishedAt": v.get("publishedAt"),
            "ageDays": v.get("_ageDays"),
        })

    theme_out = []
    for theme, agg in themes.items():
        stances = agg["stances"]
        wmed = _weighted_median(stances)
        vals = [s for s, _ in stances]
        dispersion = round(float(max(vals) - min(vals)), 2) if vals else None
        theme_out.append({
            "theme": theme,
            "weightedMedianStance": round(wmed, 2) if wmed is not None else None,
            "dispersion": dispersion,
            "agreement": ("high" if dispersion is not None and dispersion <= 1 else
                          "low" if dispersion is not None and dispersion >= 2.5 else "mixed"),
            "institutionCount": len(agg["institutions"]),
            "counterCase": COUNTER_CASE.get(theme),
            "views": agg["views"],
        })
    theme_out.sort(key=lambda t: (-t["institutionCount"], -(abs(t["weightedMedianStance"] or 0))))

    return {
        "available": bool(theme_out),
        "asOf": (now or datetime.now(timezone.utc)).isoformat(),
        "themes": theme_out,
        "consensusThemes": [t for t in theme_out if t["agreement"] == "high"],
        "contestedThemes": [t for t in theme_out if t["agreement"] == "low"],
        "awaitingVerification": [
            {"institution": src_by_id.get(v.get("sourceId"), {}).get("institution", v.get("sourceId")),
             "theme": v.get("theme"), "url": v.get("url"),
             "risks": v.get("risks"), "signposts": v.get("signposts")}
            for v in unverified
        ],
        "staleCount": len(stale),
        "verifiedCount": len(deduped),
        "note": None if theme_out else "검증된 전문가 의견 없음 — 원문 확인 후 verified=true로 갱신되면 컨센서스가 표시됩니다 (내용 날조 없음).",
    }
