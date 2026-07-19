"""Entry-state engine — 'is this a good stock' vs 'is now a good time to add'.

The long-term research view (pipeline.longterm) answers the first question from
factors. This module answers the SECOND, deliberately separate, question from
price action and risk — so a name can be POSITIVE long-term yet
WAIT_FOR_PULLBACK to add today (the SK hynix pattern: excellent factors, but
semiconductor-concentrated and overheated).

States (worst → best entry timing):
  AVOID               broken trend (below 200d & 50d, negative momentum)
  EVENT_RISK          binary event near (earnings) or violent vol/gap regime
  WAIT_FOR_PULLBACK   extended/overheated — good name, poor entry
  WATCH               constructive but not a clean add point
  ACCUMULATE_GRADUALLY trend-confirmed, not overheated, risk manageable

Inputs come from the engineered feature frame (build.py assembles them) plus a
universe-relative overheat percentile and the sleeve's sector concentration, so
'overheated' is measured against peers, not a fixed RSI line.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ENTRY_STATES = ("ACCUMULATE_GRADUALLY", "WATCH", "WAIT_FOR_PULLBACK", "EVENT_RISK", "AVOID")


def _last(series):
    if series is None:
        return None
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) else None


def entry_features(feat: pd.DataFrame, volume_surge: float | None = None,
                   earnings_in_days: int | None = None) -> dict:
    """Extract entry-relevant price/vol features for one ticker."""
    close = feat["Close"].dropna()
    last = float(close.iloc[-1]) if len(close) else None
    ma20 = _last(feat["ma20"]) if "ma20" in feat else None
    ma50 = _last(feat["ma50"]) if "ma50" in feat else None
    ma200 = _last(feat["ma200"]) if "ma200" in feat else None
    rsi = _last(feat["rsi_14"]) if "rsi_14" in feat else None
    vol20 = _last(feat["volatility_20d"]) if "volatility_20d" in feat else None
    vol60 = _last(feat["volatility_60d"]) if "volatility_60d" in feat else None
    mom63 = _last(feat["momentum_60d"]) if "momentum_60d" in feat else None

    rets = close.pct_change().dropna()
    recent = rets.iloc[-20:]
    max_adverse = float(recent.min() * 100) if len(recent) else None  # worst single day, last 20d
    # Overnight gap: today's open vs yesterday's close (last 10 sessions min).
    gap = None
    if "Open" in feat:
        op = feat["Open"].dropna()
        pc = feat["Close"].shift(1)
        g = (op / pc - 1).dropna().iloc[-10:]
        if len(g):
            gap = float(g.min() * 100)

    dist200 = (last / ma200 - 1) * 100 if (last and ma200) else None
    vol_spike = (vol20 / vol60) if (vol20 and vol60 and vol60 > 0) else None
    return {
        "aboveMA20": bool(last and ma20 and last > ma20),
        "aboveMA50": bool(last and ma50 and last > ma50),
        "aboveMA200": bool(last and ma200 and last > ma200),
        "dist200Pct": round(dist200, 1) if dist200 is not None else None,
        "rsi14": round(rsi, 1) if rsi is not None else None,
        "vol20Pct": round(vol20 * 100, 1) if vol20 is not None else None,
        "volSpike": round(vol_spike, 2) if vol_spike is not None else None,
        "mom63Pct": round(mom63 * 100, 1) if mom63 is not None else None,
        "maxAdversePct": round(max_adverse, 1) if max_adverse is not None else None,
        "gapDownPct": round(gap, 1) if gap is not None else None,
        "volumeSurge": volume_surge,
        "earningsInDays": earnings_in_days,
    }


def overheat_score(f: dict) -> float | None:
    """A raw overheat score (higher = more stretched). Ranked across the region
    universe in build.py to yield an overheat *percentile* — 'hot vs peers',
    which the task asks for instead of an absolute RSI threshold."""
    parts = []
    if f.get("rsi14") is not None:
        parts.append((f["rsi14"] - 50) / 25.0)          # RSI centred
    if f.get("dist200Pct") is not None:
        parts.append(f["dist200Pct"] / 20.0)            # extension above 200d
    if f.get("volSpike") is not None:
        parts.append((f["volSpike"] - 1.0) * 1.5)       # vol acceleration
    if f.get("mom63Pct") is not None:
        parts.append(f["mom63Pct"] / 40.0)              # recent run
    if not parts:
        return None
    return float(np.mean(parts))


def classify(f: dict, overheat_pct: float | None = None,
             sector_concentration_pct: float | None = None,
             sector_cap_pct: float = 30.0) -> dict:
    """Return {'entryState', 'reasons', 'overheatPercentile'} for one name."""
    reasons: list[str] = []

    broken = (not f.get("aboveMA200")) and (not f.get("aboveMA50")) and ((f.get("mom63Pct") or 0) < 0)

    volatile_regime = (f.get("volSpike") or 0) >= 1.6 and ((f.get("gapDownPct") or 0) <= -4 or (f.get("maxAdversePct") or 0) <= -6)
    earnings_near = f.get("earningsInDays") is not None and 0 <= f["earningsInDays"] <= 7

    overheated = (
        (overheat_pct is not None and overheat_pct >= 85)
        or (f.get("rsi14") or 0) >= 78
        or (f.get("dist200Pct") or 0) >= 25
    )

    constructive = f.get("aboveMA50") and f.get("aboveMA200") and (f.get("mom63Pct") or 0) > -5

    if broken:
        state = "AVOID"
        reasons.append("추세 훼손: 50·200일선 하회 + 음의 60일 모멘텀")
    elif earnings_near:
        state = "EVENT_RISK"
        reasons.append(f"실적 발표 임박(D-{f['earningsInDays']}) — 결과 확인 후 진입")
    elif volatile_regime:
        state = "EVENT_RISK"
        reasons.append("변동성 급등 + 최근 갭하락/급락 — 안정 확인 필요")
    elif overheated:
        state = "WAIT_FOR_PULLBACK"
        if overheat_pct is not None:
            reasons.append(f"유니버스 내 과열 상위 {max(1, round(100 - overheat_pct))}%")
        if (f.get("dist200Pct") or 0) >= 25:
            reasons.append(f"200일선 대비 +{f['dist200Pct']}% 이격 (되돌림 대기)")
        if (f.get("rsi14") or 0) >= 78:
            reasons.append(f"RSI {f['rsi14']} 과열")
    elif constructive:
        state = "ACCUMULATE_GRADUALLY"
        reasons.append("50·200일선 위 · 과열 아님 — 분할 매수 구간")
    else:
        state = "WATCH"
        if not f.get("aboveMA50"):
            reasons.append("50일선 아래 — 단기 추세 미확인")
        else:
            reasons.append("추세 혼조 — 확인 후 진입")

    # Concentration overlay: a clean add point still gets demoted if the sleeve
    # is already sector-heavy (correlation/concentration guard).
    if sector_concentration_pct is not None and sector_concentration_pct >= sector_cap_pct and state == "ACCUMULATE_GRADUALLY":
        state = "WATCH"
        reasons.append(f"동일 섹터 집중 {round(sector_concentration_pct)}% (상한 {round(sector_cap_pct)}%) — 신규 비중 확대 자제")

    return {
        "entryState": state,
        "reasons": reasons,
        "overheatPercentile": round(overheat_pct) if overheat_pct is not None else None,
    }
