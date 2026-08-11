"""Long-horizon (6–12 month) cross-sectional multi-factor research — v2.

WHAT CHANGED FROM v1 (and why it was wrong)
--------------------------------------------
v1 published TOP_PICKS=5 names and capped each at MAX_WEIGHT=20%. Five names
under a 20% cap is a *mathematical identity*: every name lands at ~20%. That is
not portfolio construction, it is an equal-weight in disguise. v1 also:
  * printed a "추천 비중"(suggested weight) with no knowledge of the user's
    portfolio size, region split, or risk budget — a number that cannot be
    correct;
  * ranked ETFs/benchmarks (QQQ, SPY) alongside single stocks;
  * applied one P/B and debt yardstick to banks, industrials and semis alike;
  * compared KR and US z-scores as if one global ranking existed;
  * blended a hidden alpha score with risk into a single "composite".

v2 fixes all of the above:
  * region-first: KR and US are ranked in SEPARATELY z-scored universes and
    never compared directly. Regional allocation is a macro/risk-budget layer
    (build.py), not a merged global 1-2-3.
  * ETFs/benchmarks excluded from single-stock ranking (config.excludeFromRanking).
  * factor z-scores are SECTOR-NEUTRAL where a sector has enough names, so a
    bank's leverage isn't scored against an industrial's.
  * an alpha score (factor composite, evidence-quality-shrunk) is reported SEPARATELY
    from risk metrics (downside vol / max drawdown / CVaR / beta) and from the
    entry state (pipeline.entry). Nothing is blended into one hidden number.
  * a real sleeve: 8–12 names, per-name cap, per-sector cap, and a cash floor,
    with the weight explicitly named ``modelSleeveWeightPct`` — the weight
    inside a hypothetical fully-invested MODEL sleeve, NOT advice about the
    user's own book.
  * names with < 3 factor sleeves or thin financial coverage are classed
    DATA_INSUFFICIENT and never enter the sleeve.
  * a rank buffer (config.longterm.rankBuffer) reduces turnover: new names must
    reach the top enterPct; incumbents are held until they fall below exitPct.

HONESTY (unchanged and reinforced): value/quality use CURRENT-snapshot
fundamentals (no point-in-time history), so those sleeves rest on published
academic evidence, not an in-house backtest. dataMode/provenance ship in the
payload; walk-forward validation for the price-based sleeves lives in
pipeline.validation_lt.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import sectors as SECT

# Evidence-weighted sleeve blend. Weights renormalize over the sleeves a name
# actually has data for.
FACTOR_WEIGHTS = {"momentum": 0.30, "value": 0.25, "quality": 0.25, "lowvol": 0.20}
MIN_HISTORY = 273           # 252d momentum + 21d skip
MIN_SECTOR_FOR_NEUTRAL = 4  # need >= this many names in a sector to neutralize

# Source-quality weights: price sleeves are our own history (high); fundamental
# sleeves are current-snapshot only (medium, no point-in-time).
SLEEVE_SOURCE_QUALITY = {"momentum": 1.0, "lowvol": 1.0, "value": 0.6, "quality": 0.6}

CAVEATS = [
    "value/quality는 현재 스냅샷 재무 데이터 기반 — 시점별(point-in-time) 이력이 없어 자체 백테스트 불가, 학술 팩터 근거(Fama-French, Novy-Marx 등)에 의존",
    "유니버스는 현재 상장 종목 기준(생존편향) — 과거 성과 재현 검증에는 영향, 오늘의 상대 순위 산출에는 영향 제한적",
    "modelSleeveWeight는 '완전 투자된 가상 모델 슬리브' 내 비중이며 개인 포트폴리오 추천 비중이 아님 — 전체 규모·지역·위험예산은 사용자가 결정",
    "팩터 알파 점수와 위험지표·진입상태는 별도 표기 — 하나의 점수로 섞지 않음",
    "무효화 조건은 종목별 현재 수치와 지역 횡단면 분포에서 산출한 개별 기준선이며, 모든 종목에 같은 문구를 붙이지 않음",
    "투자 조언이 아닌 리서치 참고 자료",
]

FACTOR_KO = {"momentum": "모멘텀", "value": "밸류", "quality": "퀄리티", "lowvol": "저변동"}


# --------------------------------------------------------------------------- #
# Price-based inputs
# --------------------------------------------------------------------------- #
def momentum_12_1(close: pd.Series) -> float | None:
    s = close.dropna()
    if len(s) < MIN_HISTORY:
        return None
    return float(s.iloc[-21] / s.iloc[-252] - 1)


def momentum_6m(close: pd.Series) -> float | None:
    s = close.dropna()
    if len(s) < 126:
        return None
    return float(s.iloc[-1] / s.iloc[-126] - 1)


def realized_vol_252(close: pd.Series) -> float | None:
    r = close.dropna().pct_change().dropna()
    if len(r) < 60:
        return None
    return float(r.iloc[-252:].std() * np.sqrt(252))


def downside_vol_252(close: pd.Series) -> float | None:
    """Semi-deviation of negative daily returns (annualized) — a downside-only
    risk metric (Sortino family), less misleading than symmetric vol."""
    r = close.dropna().pct_change().dropna().iloc[-252:]
    neg = r[r < 0]
    if len(neg) < 20:
        return None
    return float(np.sqrt((neg ** 2).mean()) * np.sqrt(252))


def cvar_95(close: pd.Series) -> float | None:
    """Historical 95% CVaR (expected shortfall) of daily returns, as a positive
    percentage of capital."""
    r = close.dropna().pct_change().dropna().iloc[-252:]
    if len(r) < 60:
        return None
    var = np.quantile(r, 0.05)
    tail = r[r <= var]
    if tail.empty:
        return None
    return float(-tail.mean() * 100)


def max_drawdown_252(close: pd.Series) -> float | None:
    sample = close.dropna().iloc[-252:]
    if sample.empty:
        return None
    peak = sample.cummax()
    return float(((sample - peak) / peak).min() * 100)


def beta_to(close: pd.Series, bench_close: pd.Series | None) -> float | None:
    if bench_close is None:
        return None
    a = close.dropna().pct_change()
    b = bench_close.dropna().pct_change()
    df = pd.concat([a, b], axis=1, join="inner").dropna().iloc[-252:]
    if len(df) < 60:
        return None
    var_b = df.iloc[:, 1].var()
    if not var_b:
        return None
    return float(df.iloc[:, 0].cov(df.iloc[:, 1]) / var_b)


# --------------------------------------------------------------------------- #
# Cross-sectional scoring
# --------------------------------------------------------------------------- #
def zscore(values: pd.Series, winsor: float = 2.5) -> pd.Series:
    """Cross-sectional z-score, winsorized so one outlier can't own a sleeve."""
    v = values.astype(float)
    mask = v.notna()
    if mask.sum() < 3:
        return pd.Series(np.nan, index=v.index)
    z = (v - v[mask].mean()) / (v[mask].std(ddof=0) or 1.0)
    return z.clip(-winsor, winsor)


def sector_neutral_z(values: pd.Series, sector: pd.Series, winsor: float = 2.5) -> pd.Series:
    """Z-score WITHIN each sector that has enough names; small sectors and
    unclassified names fall back to the universe-wide z-score.

    This is the core fix for 'don't apply one P/B rule to banks and industrials
    alike' — value/quality are only comparable within an industry.
    """
    out = pd.Series(np.nan, index=values.index, dtype=float)
    global_z = zscore(values, winsor)
    handled = pd.Series(False, index=values.index)
    for sec, idx in values.groupby(sector).groups.items():
        idx = list(idx)
        if sec is None or len(idx) < MIN_SECTOR_FOR_NEUTRAL:
            continue
        sub = values.loc[idx]
        if sub.notna().sum() >= 3:
            out.loc[idx] = zscore(sub, winsor)
            handled.loc[idx] = True
    out[~handled] = global_z[~handled]
    return out


def _sleeve(frames: list[pd.Series]) -> pd.Series:
    df = pd.concat(frames, axis=1)
    return df.mean(axis=1, skipna=True)


def _percentile(s: pd.Series) -> pd.Series:
    return s.rank(method="average", pct=True).mul(100).round(0)


def _deterministic_rank(table: pd.DataFrame, alpha_pct: pd.Series | None = None) -> pd.DataFrame:
    """Investment criteria first, ticker only as the final deterministic tie-break."""
    ranked = table.copy()
    def numeric_series(primary: str, fallback: str | None = None, default: float = 0.0) -> pd.Series:
        if primary in ranked:
            return pd.to_numeric(ranked[primary], errors="coerce").fillna(default)
        if fallback and fallback in ranked:
            return pd.to_numeric(ranked[fallback], errors="coerce").fillna(default)
        return pd.Series(default, index=ranked.index, dtype=float)

    ranked["_alphaPct"] = (alpha_pct.reindex(ranked.index) if alpha_pct is not None
                           else ranked["alpha"].rank(method="average", pct=True).mul(100))
    ranked["_ticker"] = ranked.index.astype(str)
    ranked["_evidence"] = numeric_series("evidenceCoverage", "factorCoverage")
    ranked["_completeness"] = numeric_series("dataCompleteness", "financialCoverage")
    ranked["_downside"] = numeric_series("downsideVol", default=np.inf)
    return ranked.sort_values(
        ["alpha", "_alphaPct", "_evidence", "_completeness", "_downside", "_ticker"],
        ascending=[False, False, False, False, True, True], kind="mergesort",
    ).drop(columns=["_alphaPct", "_ticker", "_evidence", "_completeness", "_downside"])


# --------------------------------------------------------------------------- #
# Region table
# --------------------------------------------------------------------------- #
def _earnings_yield(trailing_pe, forward_pe, earnings_growth) -> tuple[float | None, float | None]:
    """Trailing & forward earnings yields, guarding negative/absurd P/Es.

    A negative trailing P/E means the company is loss-making; earnings yield is
    then meaningless, so we drop it (rather than let a huge negative number
    pollute the value z). forwardPE — collected but unused in v1 — is now a real
    input, which also captures a turnaround the trailing number misses.
    """
    ey_t = round(1.0 / trailing_pe, 4) if trailing_pe and 0 < trailing_pe < 1000 else None
    ey_f = round(1.0 / forward_pe, 4) if forward_pe and 0 < forward_pe < 1000 else None
    return ey_t, ey_f


def raw_inputs(ticker: str, close: pd.Series, fundamentals_row: dict | None,
               bench_close: pd.Series | None = None) -> dict:
    """The per-name raw factor inputs, before any cross-sectional scoring.

    Split out of ``build_region`` so the historical replay engine can assemble
    the identical input row from point-in-time data and hand it to the same
    scorer, instead of maintaining a second copy of the factor definitions that
    could quietly drift away from production.
    """
    f = fundamentals_row or {}
    ey_t, ey_f = _earnings_yield(f.get("trailingPE"), f.get("forwardPE"), f.get("earningsGrowth"))
    return {
        "sector": SECT.sector_of(ticker, f.get("sector")),
        # momentum
        "mom121": momentum_12_1(close),
        "mom6": momentum_6m(close),
        # value
        "earningsYield": ey_t if ey_t is not None else f.get("earningsYield"),
        "fwdEarningsYield": ey_f,
        "bookYield": f.get("bookYield"),
        "fcfYield": f.get("fcfYield"),
        # quality
        "roe": f.get("roe"),
        "opMargin": f.get("operatingMargin"),
        "profitMargin": f.get("profitMargin"),
        "debtToEquity": f.get("debtToEquity"),
        "earningsGrowth": f.get("earningsGrowth"),
        "marketCap": f.get("marketCap"),
        # risk (price-based)
        "vol252": realized_vol_252(close),
        "downsideVol": downside_vol_252(close),
        "cvar95": cvar_95(close),
        "maxDD252": max_drawdown_252(close),
        "beta": beta_to(close, bench_close),
    }


RAW_INPUT_COLUMNS = (
    "sector", "mom121", "mom6", "earningsYield", "fwdEarningsYield", "bookYield",
    "fcfYield", "roe", "opMargin", "profitMargin", "debtToEquity", "earningsGrowth",
    "marketCap", "vol252", "downsideVol", "cvar95", "maxDD252", "beta",
)


def score_cross_section(rows: dict[str, dict], cfg_lt: dict | None = None) -> pd.DataFrame | None:
    """Sector-neutral factor scoring for one region's cross-section.

    This is THE alpha definition. Production (``build_region``) and the
    historical replay engine both call it with the same shaped input, so a
    replayed 2019 alpha percentile is produced by the same code path as today's
    — the only difference being which data was visible.
    """
    cfg_lt = cfg_lt or {}
    if len(rows) < 5:
        return None
    # Canonicalize the cross-section before any ranking/group operation. The
    # source listing order must never become an investment input.
    df = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=list(RAW_INPUT_COLUMNS))
    df = df.sort_index(kind="mergesort")
    sector = df["sector"]
    num = df.drop(columns=["sector"]).astype(float)

    # Sector-neutral z per raw input, then blend into sleeves.
    def snz(col):
        return sector_neutral_z(num[col], sector)

    factors = pd.DataFrame(index=df.index)
    factors["momentum"] = _sleeve([snz("mom121"), snz("mom6")])
    factors["value"] = _sleeve([snz("earningsYield"), snz("fwdEarningsYield"), snz("bookYield"), snz("fcfYield")])
    # Leverage penalty is sector-exempt: financials/utilities/REITs carry
    # structurally high debt-to-equity and must not be punished for it.
    lev = -num["debtToEquity"]
    lev_exempt = sector.isin(SECT.LEVERAGE_EXEMPT_SECTORS)
    lev_z = sector_neutral_z(lev.where(~lev_exempt), sector)
    factors["quality"] = _sleeve([snz("roe"), snz("opMargin"), snz("profitMargin"), snz("earningsGrowth"), lev_z])
    factors["lowvol"] = sector_neutral_z(-num["vol252"], sector)

    # Evidence/data quality, computed per name. These are not prediction odds.
    value_inputs = ["earningsYield", "fwdEarningsYield", "bookYield", "fcfYield"]
    quality_inputs = ["roe", "opMargin", "profitMargin", "earningsGrowth", "debtToEquity"]
    fin_inputs = value_inputs + quality_inputs
    financial_cov = num[fin_inputs].notna().mean(axis=1)
    sleeves_present = factors.notna().sum(axis=1)
    factor_cov = sleeves_present / len(FACTOR_WEIGHTS)

    # Alpha = evidence-weighted sleeve blend, renormalized over present sleeves,
    # then CONFIDENCE-SHRUNK toward 0 (neutral). This is the ONLY alpha number;
    # risk metrics and entry state are reported separately.
    w = pd.Series(FACTOR_WEIGHTS)
    avail = factors.notna().astype(float)
    weight_sum = avail.mul(w, axis=1).sum(axis=1)
    raw_alpha = factors.fillna(0).mul(w, axis=1).sum(axis=1) / weight_sum.replace(0, np.nan)
    # Evidence coverage in [0,1]: factor coverage, financial completeness and
    # source quality. It shrinks weakly-supported alpha but is never rendered as
    # a statistical or investment-prediction confidence.
    src_q = (avail.mul(pd.Series(SLEEVE_SOURCE_QUALITY), axis=1).sum(axis=1)
             / avail.sum(axis=1).replace(0, np.nan)).fillna(0.0)
    evidence_coverage = (0.5 * factor_cov + 0.3 * financial_cov + 0.2 * src_q).clip(0, 1)
    alpha = raw_alpha * evidence_coverage

    # Value-trap guard: cheap (high value z) but weak quality AND non-positive
    # free cash flow / shrinking earnings -> not a bargain, a trap.
    value_trap = (
        (factors["value"] > 0.5)
        & (factors["quality"] < -0.3)
        & ((num["fcfYield"].fillna(0) <= 0) | (num["earningsGrowth"].fillna(0) < 0))
    )

    out = factors.copy()
    out["sector"] = sector
    out["alpha"] = alpha
    out["rawAlpha"] = raw_alpha
    out["evidenceCoverage"] = evidence_coverage.round(3)
    out["dataCompleteness"] = financial_cov.round(3)
    out["sourceQuality"] = src_q.round(3)
    # Internal compatibility columns used by eligibility logic below. They are
    # not emitted as prediction-confidence fields in the artifact.
    out["factorCoverage"] = factor_cov.round(3)
    out["financialCoverage"] = financial_cov.round(3)
    out["sleevesPresent"] = sleeves_present
    out["valueTrap"] = value_trap
    for c in ["vol252", "downsideVol", "cvar95", "maxDD252", "beta", "mom121"]:
        out[c] = num[c]
    out["marketCap"] = num["marketCap"]

    # Classify research view / data sufficiency.
    min_sleeves = int(cfg_lt.get("minFactorSleeves", 3))
    min_fin = float(cfg_lt.get("minFinancialCoverage", 0.4))
    out["dataInsufficient"] = (out["sleevesPresent"] < min_sleeves) | (out["financialCoverage"] < min_fin)
    out = out.dropna(subset=["alpha"])
    return out if len(out) >= 5 else None


def build_region(tickers: list[str], prices: dict, fundamentals: dict, diags: dict,
                 bench_close: pd.Series | None = None, cfg_lt: dict | None = None) -> pd.DataFrame | None:
    cfg_lt = cfg_lt or {}
    exclude = set(cfg_lt.get("excludeFromRanking", []))
    rows = {
        t: raw_inputs(t, prices[t]["Close"], fundamentals.get(t, {}), bench_close)
        for t in tickers if t not in exclude and t in prices
    }
    out = score_cross_section(rows, cfg_lt)
    if out is None:
        return None
    out["aboveMA200"] = [bool((diags.get(t) or {}).get("aboveMA200")) for t in out.index]
    out["regime"] = [(diags.get(t) or {}).get("regime") for t in out.index]
    return out


def region_risk_limits(table: pd.DataFrame) -> dict:
    """Cross-sectional risk limits used as per-name invalidation levels.

    A name's tail-risk / drawdown trigger is the *region's own* distribution,
    not a number typed into the source. A name already past the limit is
    reported as breached instead of being given a comfortable headroom story.
    """
    def q(column: str, quantile: float) -> float | None:
        if column not in table:
            return None
        values = pd.to_numeric(table[column], errors="coerce").dropna()
        if len(values) < 5:
            return None
        return float(np.quantile(values, quantile))
    return {
        "cvar95Pct": q("cvar95", 0.90),
        "maxDD252Pct": q("maxDD252", 0.10),
        "downsideVolPct": q("downsideVol", 0.90),
        "basisKo": "지역 횡단면 분포 (꼬리위험·하방변동 90퍼센타일, 최대낙폭 10퍼센타일)",
    }


def invalidation_conditions(row: pd.Series, pct_row: pd.Series, alpha_pct: float | None,
                            cfg_lt: dict, risk_limits: dict | None = None) -> list[dict]:
    """Per-name conditions that would break THIS name's research case.

    Every condition carries the name's own current reading and the level at
    which the case stops holding, so two names never get the same sentence.
    Sources of the level: the configured rank buffer, the factor median, the
    trend definition already used by the momentum sleeve, the region's risk
    cross-section, and the data-sufficiency floor.
    """
    risk_limits = risk_limits or {}
    buf = (cfg_lt or {}).get("rankBuffer", {}) or {}
    exit_pct = float(buf.get("exitPct", 28))
    hold_floor = round(100 - exit_pct)
    out: list[dict] = []

    def add(key, label, current, trigger, breached=False):
        out.append({"key": key, "labelKo": label, "currentKo": current,
                    "triggerKo": trigger, "state": "BREACHED" if breached else "OK"})

    # 1. Relative rank — the reason the name is in the candidate set at all.
    if alpha_pct is not None:
        add("RANK_EXIT", "상대 순위", f"알파 {int(alpha_pct)}p",
            f"{hold_floor}p 미만으로 하락", breached=alpha_pct < hold_floor)

    # 2. The sleeves actually carrying the case (its thesis), each with its own
    #    current percentile and the median it must not fall through.
    leaders = [(k, float(pct_row[k])) for k in ("momentum", "value", "quality", "lowvol")
               if k in pct_row and pd.notna(pct_row[k]) and float(pct_row[k]) >= 66]
    for key, value in sorted(leaders, key=lambda kv: -kv[1])[:2]:
        add(f"FACTOR_{key.upper()}", f"{FACTOR_KO[key]} 팩터", f"{int(value)}p",
            "50p(중앙값) 미만으로 하락")

    # 3. Trend — the momentum sleeve's own definition (12-1M and the 200d line).
    mom = row.get("mom121")
    above = bool(row.get("aboveMA200"))
    if pd.notna(mom):
        add("TREND", "추세", f"12-1M {round(float(mom) * 100, 1)}% · 200일선 {'위' if above else '아래'}",
            "12-1M 음전환 또는 200일선 하회 고착", breached=(float(mom) <= 0 and not above))
    elif not above:
        add("TREND", "추세", "200일선 아래", "200일선 회복 실패 지속", breached=True)

    # 4. Risk — measured against the region's own cross-section, not a fixed line.
    for column, key, label, unit, worse_is_lower in (
        ("cvar95", "cvar95Pct", "꼬리위험 CVaR", "%", False),
        ("maxDD252", "maxDD252Pct", "최대낙폭", "%", True),
    ):
        current, limit = row.get(column), risk_limits.get(key)
        if pd.isna(current) or limit is None:
            continue
        current, limit = float(current), float(limit)
        breached = current < limit if worse_is_lower else current > limit
        add(f"RISK_{key.upper()}", label, f"{round(current, 1)}{unit}",
            f"지역 기준 {round(limit, 1)}{unit} {'하회' if worse_is_lower else '초과'}", breached=breached)

    # 5. Value trap — a cheap-but-deteriorating name is already invalidated.
    if bool(row.get("valueTrap")):
        add("VALUE_TRAP", "가치함정", "싼 가격 + 약한 퀄리티·현금흐름", "이미 성립", breached=True)

    # 6. Data sufficiency — the floor that decides whether the name is rankable.
    min_sleeves = int((cfg_lt or {}).get("minFactorSleeves", 3))
    min_fin = float((cfg_lt or {}).get("minFinancialCoverage", 0.4))
    sleeves = int(row.get("sleevesPresent") or 0)
    coverage = float(row.get("financialCoverage") or 0.0)
    add("DATA_FLOOR", "데이터 기준",
        f"슬리브 {sleeves}/{len(FACTOR_WEIGHTS)} · 재무 {round(coverage * 100)}%",
        f"슬리브 {min_sleeves}개 미만 또는 재무 {round(min_fin * 100)}% 미만",
        breached=(sleeves < min_sleeves or coverage < min_fin))
    return out


ENTRY_STATE_KO = {
    "ACCUMULATE_GRADUALLY": "분할 매수 구간", "WATCH": "관찰",
    "WAIT_FOR_PULLBACK": "되돌림 대기", "EVENT_RISK": "이벤트 위험", "AVOID": "회피",
}


def entry_invalidation(entry_state: str | None) -> dict | None:
    """Timing-layer condition. Separate from the factor case on purpose."""
    if not entry_state:
        return None
    return {
        "key": "ENTRY_STATE", "labelKo": "진입 상태",
        "currentKo": ENTRY_STATE_KO.get(entry_state, entry_state),
        "triggerKo": "회피·이벤트 위험으로 전환",
        "state": "BREACHED" if entry_state in {"AVOID", "EVENT_RISK"} else "OK",
    }


def thesis_summary(row: pd.Series, pct_row: pd.Series, alpha_pct: float | None) -> str:
    """One line naming which sleeves carry the case for THIS name."""
    leaders = [(FACTOR_KO[k], float(pct_row[k])) for k in ("momentum", "value", "quality", "lowvol")
               if k in pct_row and pd.notna(pct_row[k]) and float(pct_row[k]) >= 66]
    leaders.sort(key=lambda kv: -kv[1])
    rank = f"섹터중립 알파 상위 {max(1, round(100 - alpha_pct))}%" if alpha_pct is not None else "알파 순위 미산출"
    if not leaders:
        return f"{rank} · 단일 팩터가 아닌 전 슬리브 평균으로 올라온 사례"
    driver = "·".join(name for name, _ in leaders[:2])
    return f"{driver} 주도 · {rank}"


def research_view(row: pd.Series, alpha_pct: float | None) -> str:
    if bool(row.get("dataInsufficient")):
        return "DATA_INSUFFICIENT"
    if alpha_pct is None:
        return "NEUTRAL"
    if alpha_pct >= 66:
        return "POSITIVE"
    if alpha_pct <= 33:
        return "NEGATIVE"
    return "NEUTRAL"


# --------------------------------------------------------------------------- #
# Sleeve construction (real portfolio math)
# --------------------------------------------------------------------------- #
def select_names(table: pd.DataFrame, cfg_lt: dict, prior_holdings: set[str] | None = None) -> list[str]:
    """Pick 8–12 eligible names with a rank buffer and a per-sector count guard.

    New names must clear the top ``enterPct`` of the region; incumbents survive
    until they drop below ``exitPct`` — cutting turnover (and trading costs)
    without letting a decayed name linger forever.
    """
    prior_holdings = prior_holdings or set()
    buf = cfg_lt.get("rankBuffer", {}) or {}
    enter_pct, exit_pct = float(buf.get("enterPct", 12)), float(buf.get("exitPct", 28))
    min_names, max_names = int(cfg_lt.get("minNames", 8)), int(cfg_lt.get("maxNames", 12))

    elig = table[~table["dataInsufficient"]].copy()
    if elig.empty:
        return []
    # Alpha percentile within the eligible set.
    elig["alphaPct"] = elig["alpha"].rank(method="average", pct=True) * 100
    elig = _deterministic_rank(elig, elig["alphaPct"])

    enter_floor = 100 - enter_pct
    hold_floor = 100 - exit_pct
    chosen: list[str] = []
    for t, r in elig.iterrows():
        is_incumbent = t in prior_holdings
        floor = hold_floor if is_incumbent else enter_floor
        if r["alphaPct"] >= floor:
            chosen.append(t)
    # Backfill toward min_names by alpha if the buffer was too strict.
    if len(chosen) < min_names:
        for t in elig.index:
            if t not in chosen:
                chosen.append(t)
            if len(chosen) >= min_names:
                break
    return chosen[:max_names]


def sleeve_weights(picks: pd.DataFrame, cfg_lt: dict) -> tuple[pd.Series, float]:
    """Inverse-vol weights with a per-name cap, a per-sector cap and a cash floor.

    Returns (weights summing to <= 1-cash, cashPct). Weight that can't be placed
    under the caps spills into cash rather than being force-fit.
    """
    name_cap = float(cfg_lt.get("maxNameWeight", 0.15))
    sector_cap = float(cfg_lt.get("maxSectorWeight", 0.30))
    cash_floor = float(cfg_lt.get("minCashPct", 5)) / 100.0
    budget = 1.0 - cash_floor

    vol = picks["downsideVol"].fillna(picks["vol252"])
    inv = 1.0 / vol.clip(lower=0.05)
    inv = inv.fillna(inv.mean() if inv.notna().any() else 1.0)
    prop = inv / inv.sum()
    sectors = picks["sector"].fillna("미분류")

    # Freeze-based water-filling: distribute the budget proportional to inverse
    # vol among ACTIVE names; whenever a name hits its cap or a sector hits its
    # cap, freeze it (never unfreeze) so caps can't ping-pong. Whatever can't be
    # placed under the caps spills to cash.
    w = pd.Series(0.0, index=picks.index)
    frozen = pd.Series(False, index=picks.index)
    for _ in range(100):
        remaining = budget - float(w.sum())
        active = ~frozen
        if remaining <= 1e-6 or not active.any():
            break
        ptot = float(prop[active].sum())
        if ptot <= 0:
            break
        w[active] = w[active] + prop[active] / ptot * remaining
        progressed = False
        # Name cap.
        over = active & (w > name_cap)
        if over.any():
            w[over] = name_cap
            frozen |= over
            progressed = True
        # Sector cap.
        for sec, idx in sectors.groupby(sectors).groups.items():
            idx = list(idx)
            ssum = float(w[idx].sum())
            if ssum > sector_cap + 1e-9:
                w[idx] = w[idx] * (sector_cap / ssum)
                frozen[idx] = True
                progressed = True
        if not progressed:
            break
    cash_pct = round((1.0 - float(w.sum())) * 100, 1)
    return w.round(4), cash_pct


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def _row(table: pd.DataFrame, pct: pd.DataFrame, alpha_pct: pd.Series, region: str, t: str,
         cfg_lt: dict | None = None, risk_limits: dict | None = None) -> dict:
    r = table.loc[t]
    ap = int(alpha_pct.loc[t]) if pd.notna(alpha_pct.loc[t]) else None
    evidence = r.get("evidenceCoverage", r.get("factorCoverage", r.get("confidence", 0.0)))
    completeness = r.get("dataCompleteness", r.get("financialCoverage", 0.0))
    source_quality = r.get("sourceQuality", 0.0)
    return {
        "ticker": t,
        "region": region,
        "sector": r["sector"],
        "sectorKo": SECT.sector_ko(r["sector"]),
        "alpha": round(float(r["alpha"]), 3),
        "rawAlpha": round(float(r["rawAlpha"]), 3),
        "alphaPercentile": ap,
        "longTermResearchView": research_view(r, ap),
        "evidenceCoverage": round(float(evidence), 3),
        "dataCompleteness": round(float(completeness), 3),
        "sourceQuality": round(float(source_quality), 3),
        "marketCap": round(float(r["marketCap"]), 2) if pd.notna(r.get("marketCap")) else None,
        "empiricalValidationStatus": "PENDING_PAPER_HISTORY",
        "sleevesPresent": int(r["sleevesPresent"]),
        "valueTrap": bool(r["valueTrap"]),
        "factorPercentiles": {
            k: (int(pct.loc[t, k]) if pd.notna(pct.loc[t, k]) else None)
            for k in ("momentum", "value", "quality", "lowvol")
        },
        "risk": {
            "vol252Pct": round(float(r["vol252"]) * 100, 1) if pd.notna(r["vol252"]) else None,
            "downsideVolPct": round(float(r["downsideVol"]) * 100, 1) if pd.notna(r["downsideVol"]) else None,
            "cvar95Pct": round(float(r["cvar95"]), 2) if pd.notna(r["cvar95"]) else None,
            "maxDD252Pct": round(float(r["maxDD252"]), 1) if pd.notna(r["maxDD252"]) else None,
            "beta": round(float(r["beta"]), 2) if pd.notna(r["beta"]) else None,
        },
        "mom12_1Pct": round(float(r["mom121"]) * 100, 1) if pd.notna(r["mom121"]) else None,
        "aboveMA200": bool(r["aboveMA200"]),
        "regime": r["regime"],
        "thesisKo": thesis_summary(r, pct.loc[t], ap),
        "invalidation": invalidation_conditions(r, pct.loc[t], ap, cfg_lt or {}, risk_limits),
        "invalidationBasisKo": (risk_limits or {}).get("basisKo"),
    }


def build(universe: dict[str, list[str]], prices: dict, fundamentals: dict, diags: dict,
          cfg_lt: dict | None = None, bench_by_region: dict | None = None,
          prior_holdings: dict | None = None, blocked: bool = False) -> dict | None:
    """Region-first long-term research. When ``blocked`` is True the sleeve
    weights and any actionable phrasing are withheld (the artifact stays a pure
    research view), satisfying the 'blocked also hides longTerm actions' rule."""
    cfg_lt = cfg_lt or {}
    bench_by_region = bench_by_region or {}
    prior_holdings = prior_holdings or {}
    regions = {}
    for region, tickers in universe.items():
        table = build_region(tickers, prices, fundamentals, diags,
                              bench_close=bench_by_region.get(region), cfg_lt=cfg_lt)
        if table is None:
            continue
        pct = table[["momentum", "value", "quality", "lowvol"]].apply(_percentile)
        alpha_pct = table["alpha"].rank(method="average", pct=True).mul(100).round(0)
        risk_limits = region_risk_limits(table)
        row_of = lambda t: _row(table, pct, alpha_pct, region, t, cfg_lt, risk_limits)

        chosen = [] if blocked else select_names(table, cfg_lt, set(prior_holdings.get(region, [])))
        picks_rows = []
        if chosen:
            picks_df = table.loc[chosen]
            weights, cash_pct = sleeve_weights(picks_df, cfg_lt)
            for t in chosen:
                row = row_of(t)
                row["modelSleeveWeightPct"] = round(float(weights[t]) * 100, 1)
                picks_rows.append(row)
        else:
            cash_pct = None

        # UI research table is intentionally compact. The immutable ledger uses
        # the separate full validation cross-section below.
        elig = _deterministic_rank(table[~table["dataInsufficient"]], alpha_pct)
        table_rows = [row_of(t) for t in elig.head(15).index]
        validation_rows = [row_of(t) for t in elig.index]
        insufficient = [
            {"ticker": t, "region": region, "sector": table.loc[t, "sector"],
             "sleevesPresent": int(table.loc[t, "sleevesPresent"]),
             "dataCompleteness": round(float(table.loc[t, "financialCoverage"]), 3)}
            for t in sorted(table[table["dataInsufficient"]].index.astype(str))
        ]

        # Sector exposure of the sleeve (concentration transparency).
        sector_exposure = {}
        if picks_rows:
            for row in picks_rows:
                sector_exposure[row["sector"] or "미분류"] = round(
                    sector_exposure.get(row["sector"] or "미분류", 0.0) + (row["modelSleeveWeightPct"] or 0), 1)

        regions[region] = {
            "picks": picks_rows,
            "cashPct": cash_pct,
            "sectorExposure": sector_exposure,
            "researchTable": table_rows,
            "validationCrossSection": validation_rows,
            "dataInsufficient": insufficient,
            "universeRanked": int(len(table)),
            "holdings": chosen,
            "riskLimits": risk_limits,
        }
    if not regions:
        return None
    requested_tickers = {ticker for tickers in universe.values() for ticker in tickers}
    covered = sum(1 for ticker in requested_tickers if fundamentals.get(ticker))
    requested = len(requested_tickers)
    return {
        "horizonMonths": [6, 12],
        "rebalance": "분기(3개월) 리밸런싱 · rank buffer로 회전율 축소",
        "factorWeights": FACTOR_WEIGHTS,
        "fundamentalsCoverage": round(100 * covered / requested, 1) if requested else 0.0,
        "weightsWithheld": bool(blocked),
        "regions": regions,
        "caveats": CAVEATS,
    }
