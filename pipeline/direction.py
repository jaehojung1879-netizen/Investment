"""Investment direction compass — the "which way should I lean" verdict.

Synthesizes four rules-based, widely-used allocation tools into one stance:

  * Dual-momentum VARIANT (inspired by Antonacci GEM, but not identical — the
    asset menu, lookbacks and defensive set differ, so we label it a variant,
    not "GEM"): 12-month absolute + relative momentum across global equities /
    bonds / gold vs cash (T-bills). Decides whether risk assets deserve capital.
  * Volatility targeting: size equity exposure so realized benchmark
    volatility lands near a target (the approach used by risk-parity and
    managed-vol funds). High vol -> mechanically smaller equity slice.
  * KR/US tilt: relative 3/6-month momentum of KOSPI vs S&P 500 decides which
    market deserves the marginal won/dollar.
  * Composite score: the above plus breadth (indices above 200d), the
    fear-greed sentiment, and the macro stances, mapped to 0..100.

Everything degrades gracefully: any series that fails to download simply
drops out of the verdict and is listed as unavailable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .datafeed import download_retry

# Dual-momentum menu. BIL is the cash yardstick (absolute-momentum hurdle).
ASSETS = [
    {"ticker": "SPY", "name": "미국 주식", "kind": "risk"},
    {"ticker": "EFA", "name": "선진국 주식(ex-US)", "kind": "risk"},
    {"ticker": "EEM", "name": "신흥국 주식", "kind": "risk"},
    {"ticker": "AGG", "name": "미국 채권", "kind": "defense"},
    {"ticker": "GLD", "name": "금", "kind": "defense"},
    {"ticker": "BIL", "name": "현금 (T-Bill)", "kind": "cash"},
]
TILT = {"US": "^GSPC", "KR": "^KS11"}

TARGET_VOL_PCT = 12.0  # annualized target for the vol-targeting sleeve
LOOKBACK_DAYS = 420    # enough history for 12M returns


def fetch_closes() -> dict[str, pd.Series]:
    """Download daily closes for every symbol the compass needs."""
    symbols = [a["ticker"] for a in ASSETS] + list(TILT.values())
    start = (pd.Timestamp.today() - pd.Timedelta(days=LOOKBACK_DAYS + 300)).strftime("%Y-%m-%d")
    df = download_retry(symbols, start=start, group_by="ticker")
    out: dict[str, pd.Series] = {}
    if df is None:
        return out
    for sym in symbols:
        try:
            if isinstance(df.columns, pd.MultiIndex):
                if sym in df.columns.get_level_values(0):
                    s = df[sym]["Close"].dropna()
                else:
                    continue
            else:
                s = df["Close"].dropna()
            if len(s) >= 63:
                out[sym] = s
        except Exception:
            continue
    return out


def _ret(close: pd.Series | None, days: int) -> float | None:
    if close is None:
        return None
    s = close.dropna()
    if len(s) <= days or s.iloc[-days - 1] == 0:
        return None
    return round(float((s.iloc[-1] / s.iloc[-days - 1] - 1) * 100), 2)


def _dual_momentum(closes: dict[str, pd.Series]) -> dict | None:
    rows = []
    for a in ASSETS:
        c = closes.get(a["ticker"])
        r12 = _ret(c, 252)
        if c is None:
            continue
        rows.append({
            "ticker": a["ticker"], "name": a["name"], "kind": a["kind"],
            "ret3mPct": _ret(c, 63), "ret6mPct": _ret(c, 126), "ret12mPct": r12,
        })
    if not rows:
        return None
    risk = [r for r in rows if r["kind"] == "risk" and r["ret12mPct"] is not None]
    cash12 = next((r["ret12mPct"] for r in rows if r["kind"] == "cash"), None)
    defense = [r for r in rows if r["kind"] == "defense" and r["ret12mPct"] is not None]
    best_risk = max(risk, key=lambda r: r["ret12mPct"]) if risk else None
    best_defense = max(defense, key=lambda r: r["ret12mPct"]) if defense else None

    equities_win = (
        best_risk is not None
        and (cash12 is None or best_risk["ret12mPct"] > cash12)
        and best_risk["ret12mPct"] > 0
    )
    winner = best_risk if equities_win else (best_defense or best_risk)
    return {
        "rows": rows,
        "equitiesWin": bool(equities_win),
        "winner": winner["ticker"] if winner else None,
        "winnerName": winner["name"] if winner else None,
        "cash12mPct": cash12,
    }


def _vol_target(bench_close: pd.Series | None) -> dict | None:
    if bench_close is None:
        return None
    rets = bench_close.dropna().pct_change().dropna()
    if len(rets) < 21:
        return None
    vol = float(rets.iloc[-21:].std() * np.sqrt(252) * 100)
    if vol <= 0:
        return None
    exposure = max(20.0, min(100.0, TARGET_VOL_PCT / vol * 100))
    return {
        "realizedVolPct": round(vol, 1),
        "targetVolPct": TARGET_VOL_PCT,
        "suggestedExposurePct": round(exposure),
    }


def _tilt(closes: dict[str, pd.Series]) -> dict | None:
    us, kr = closes.get(TILT["US"]), closes.get(TILT["KR"])
    r3 = (_ret(kr, 63), _ret(us, 63))
    r6 = (_ret(kr, 126), _ret(us, 126))
    if None in r3 or None in r6:
        return None
    d3 = round(r3[0] - r3[1], 1)
    d6 = round(r6[0] - r6[1], 1)
    if d3 > 2 and d6 > 0:
        label, cls = "한국 우위", "bull"
    elif d3 < -2 and d6 < 0:
        label, cls = "미국 우위", "bull"
    else:
        label, cls = "중립", "trans"
    return {"label": label, "cls": cls, "krMinusUs3mPct": d3, "krMinusUs6mPct": d6}


def _sig(name: str, state: str, cls: str, detail: str) -> dict:
    return {"name": name, "state": state, "cls": cls, "detail": detail}


def build(
    sentiment: dict | None = None,
    macro_summary: dict | None = None,
    indices: list[dict] | None = None,
    closes: dict[str, pd.Series] | None = None,
) -> dict | None:
    """Assemble the compass. `closes` is injectable for tests/seed data."""
    if closes is None:
        closes = fetch_closes()

    dm = _dual_momentum(closes)
    vt = _vol_target(closes.get("SPY"))
    tilt = _tilt(closes)

    score = 50.0
    signals: list[dict] = []

    if dm is not None:
        if dm["equitiesWin"]:
            score += 15
            signals.append(_sig("듀얼 모멘텀 변형 (12M)", "주식 우위", "bull",
                                f"12개월 수익률 1위 {dm['winnerName']} — 현금(T-Bill) 허들 통과"))
        else:
            score -= 15
            signals.append(_sig("듀얼 모멘텀 변형 (12M)", "방어자산 우위", "bear",
                                f"주식 12개월 모멘텀이 현금 허들 미달 — {dm['winnerName'] or '채권/금'} 선호"))

    eq_idx = [x for x in (indices or []) if x.get("region") in ("US", "KR") and x.get("above200d") is not None]
    if eq_idx:
        frac = sum(1 for x in eq_idx if x["above200d"]) / len(eq_idx)
        score += (frac - 0.5) * 30
        cls = "bull" if frac >= 0.6 else ("bear" if frac < 0.4 else "trans")
        signals.append(_sig("시장 추세 (200일선)", f"{frac * 100:.0f}% 상회", cls,
                            f"주요 주가지수 {len(eq_idx)}개 중 {sum(1 for x in eq_idx if x['above200d'])}개가 200일선 위"))

    sent_scores = [s["score"] for s in ((sentiment or {}).get("US"), (sentiment or {}).get("KR")) if s and s.get("score") is not None]
    if sent_scores:
        avg = sum(sent_scores) / len(sent_scores)
        score += (avg - 50) * 0.3
        cls = "bull" if avg >= 55 else ("bear" if avg < 45 else "trans")
        signals.append(_sig("공포·탐욕 지수", f"{avg:.0f}", cls,
                            "극단적 탐욕은 추격 과열, 극단적 공포는 역발상 기회일 수 있음"))

    if macro_summary and macro_summary.get("available"):
        stance_pts = {"Stable": 3, "Caution": -4, "Risk-off": -10}
        worst = "Stable"
        for r in ("US", "KR"):
            st = (macro_summary.get(r) or {}).get("stance")
            if st in stance_pts:
                score += stance_pts[st]
                if stance_pts[st] < stance_pts.get(worst, 3):
                    worst = st
        cls = {"Stable": "bull", "Caution": "trans", "Risk-off": "bear"}[worst]
        ko = {"Stable": "안정", "Caution": "주의", "Risk-off": "위험회피"}[worst]
        signals.append(_sig("매크로 환경", ko, cls, "금리·신용스프레드·환율 기반 스탠스 (US·KR 중 보수적인 쪽)"))

    if vt is not None:
        if vt["suggestedExposurePct"] < 50:
            score -= 8
            cls = "bear"
        elif vt["suggestedExposurePct"] > 90:
            score += 4
            cls = "bull"
        else:
            cls = "trans"
        signals.append(_sig("변동성 타게팅", f"주식 {vt['suggestedExposurePct']}%", cls,
                            f"벤치마크 실현변동성 {vt['realizedVolPct']}% vs 목표 {vt['targetVolPct']}% → 기계적 노출 상한"))

    if tilt is not None:
        signals.append(_sig("KR/US 틸트", tilt["label"], tilt["cls"],
                            f"코스피−S&P500 상대수익 3M {tilt['krMinusUs3mPct']:+.1f}%p · 6M {tilt['krMinusUs6mPct']:+.1f}%p"))

    if not signals:
        return None

    score = max(0.0, min(100.0, score))
    if score >= 60:
        stance, stance_cls, mult = "위험자산 확대", "bull", 1.0
    elif score >= 45:
        stance, stance_cls, mult = "중립 · 유지", "trans", 0.8
    else:
        stance, stance_cls, mult = "방어 · 축소", "bear", 0.5

    base_exposure = vt["suggestedExposurePct"] if vt else 70
    equity_pct = int(round(base_exposure * mult / 5) * 5)
    equity_pct = max(10, min(100, equity_pct))

    headline_bits = []
    if dm is not None:
        headline_bits.append("듀얼 모멘텀이 주식을 지지" if dm["equitiesWin"] else "듀얼 모멘텀이 방어자산을 지지")
    if tilt is not None and tilt["label"] != "중립":
        headline_bits.append(f"지역은 {tilt['label']}")
    headline_bits.append(f"모델 위험예산(주식) 약 {equity_pct}% (±10%p)")

    return {
        "score": round(score),
        "stance": stance,
        "stanceCls": stance_cls,
        "headline": " · ".join(headline_bits),
        "equityPct": equity_pct,
        "cashPct": 100 - equity_pct,
        "signals": signals,
        "dualMomentum": dm,
        "volTarget": vt,
        "tilt": tilt,
    }
