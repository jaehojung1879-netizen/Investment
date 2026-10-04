"""KR market risk anatomy v1 — the pure analysis assembly (panel -> tables). Used by the one-shot execution; never by pull-request CI on real data.

Everything here is a function of series passed in; no I/O. It turns the frozen registries and algorithms of `kr_market_risk_anatomy` into one result
document: per-feature time-series statistics on each family's own cadence, algorithmic drawdown episodes with the latest-known state at the fixed
landmarks, early-damage metrics and false-alarm / recovery cost for every frozen binary trigger, and slow-warning lead times kept separate from the fast
triggers. Nothing is selected, optimised or named; no feature or trigger is called best, validated or predictive.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import kr_market_risk_anatomy as M
from . import kr_market_risk_sources as S

SLOW_WARNING_STATES = {"W1_INVERSION_10Y3M": "spread_10y3m", "W2_INVERSION_10Y2Y": "spread_10y2y"}


def obs_series(rows):
    """[(date, value)] -> Series indexed by observation date (duplicates keep the last; non-finite dropped, never filled)."""
    s = pd.Series({pd.Timestamp(d): v for d, v in rows}, dtype=float).sort_index()
    return s[np.isfinite(s.to_numpy())]


def derived_spread(long_leg, short_leg):
    """Observation-level spread on dates where BOTH legs exist."""
    both = long_leg.index.intersection(short_leg.index)
    return long_leg.loc[both] - short_leg.loc[both]


def build_core_panel(reference, series, role_sources, lag_of):
    """reference: Series of the primary index close indexed by date. series: {source id: Series by observation date}. role_sources: {'VIX': id or None,
    'USDKRW': id or None}. lag_of(source id) -> calendar-day lag. Returns the daily-grid panel (all values known on each KR session).

    The session grid runs from the reference's first date to its last; a reference date that is not an XKRX session is reported (never used) and a
    session without a reference close stays NaN (never filled)."""
    ref = reference.copy()
    ref.index = pd.DatetimeIndex(ref.index)
    sessions = M.kr_sessions(str(ref.index.min().date()), str(ref.index.max().date()))
    close = ref.reindex(sessions)
    stale = M.FRED_DAILY_STALE_DAYS

    def known(obs, sid):
        return M.known_on_sessions(obs, sessions, lag_of(sid), stale)[0]
    kn = {}
    if {"FRED_DGS10", "FRED_DGS3MO"} <= set(series):
        kn["spread_10y3m"] = known(derived_spread(series["FRED_DGS10"], series["FRED_DGS3MO"]), "FRED_DGS10")
    if {"FRED_DGS10", "FRED_DGS2"} <= set(series):
        kn["spread_10y2y"] = known(derived_spread(series["FRED_DGS10"], series["FRED_DGS2"]), "FRED_DGS10")
    for key, sid in (("dff", "FRED_DFF"), ("hy", "FRED_BAMLH0A0HYM2"), ("ig", "FRED_BAMLC0A0CM")):
        if sid in series:
            kn[key] = known(series[sid], sid)
    for role, key in (("VIX", "vix"), ("USDKRW", "usdkrw")):
        sid = role_sources.get(role)
        if sid and sid in series:
            kn[key] = known(series[sid], sid)
    weekly = M.period_end_dates(sessions, "W")
    monthly = M.period_end_dates(sessions, "M")
    features = pd.concat([M.fast_features(close), M.slow_features(kn, sessions), M.transition_features(kn, sessions, weekly)], axis=1)
    if "spread_10y3m" in kn:
        duration = M.inversion_duration(kn["spread_10y3m"].reindex(monthly))
        features["slow_inversion_duration_10y3m"] = duration.reindex(sessions, method="ffill")
    krw_sid = role_sources.get("USDKRW")
    if krw_sid and krw_sid in series:
        features["trans_usdkrw_realized_vol_21"] = M.realized_vol_of_known_changes(series[krw_sid], sessions, lag_of(krw_sid))
    triggers = M.baseline_trigger_states(close)
    return {"sessions": sessions, "close": close, "known": kn, "features": features, "triggers": triggers, "weekly": weekly, "monthly": monthly,
            "referenceDatesOffCalendar": [str(d.date()) for d in ref.index.difference(sessions)]}


def sample_description(panel):
    """Actual start, end and valid counts of the reference and of every feature on its own cadence grid. No feature is dropped for starting late."""
    sessions, feats = panel["sessions"], panel["features"]
    out = {"reference": {"start": str(panel["close"].first_valid_index().date()), "end": str(panel["close"].last_valid_index().date()),
                         "sessions": int(len(sessions)), "validCloses": int(panel["close"].notna().sum()),
                         "missingSessions": int(panel["close"].isna().sum()), "datesOffCalendar": len(panel["referenceDatesOffCalendar"])},
           "features": {}}
    for name in feats.columns:
        grid = panel["monthly"] if M.CADENCE[M.feature_family(name)] == "M" else panel["weekly"]
        valid = feats[name].reindex(grid).dropna()
        out["features"][name] = {"family": M.feature_family(name), "tier": M.FEATURES[name][1], "cadence": M.CADENCE[M.feature_family(name)],
                                 "validDates": int(len(valid)), "start": str(valid.index[0].date()) if len(valid) else None,
                                 "end": str(valid.index[-1].date()) if len(valid) else None}
    return out


def feature_tables(panel, extra_features=None):
    """Registered per-feature statistics: each feature at its family's horizons and at the common H63/H126, on the family's own cadence rows.
    `extra_features` carries EXTENDED-tier columns (a daily-grid DataFrame, NaN outside their period)."""
    close, sessions = panel["close"], panel["sessions"]
    feats = panel["features"] if extra_features is None else extra_features
    targets = {h: M.forward_targets(close, h) for h in M.ALL_HORIZONS}
    out = {}
    for name in feats.columns:
        family = M.feature_family(name)
        frequency = M.CADENCE[family]
        grid = M.period_end_dates(sessions, frequency)
        M.assert_cadence(grid, frequency, sessions)
        x = feats[name].reindex(grid)
        horizons = sorted(set(M.HORIZONS[family]) | set(M.COMMON_HORIZONS))
        out[name] = {f"H{h}": M.feature_statistics(grid, x, targets[h].reindex(grid), frequency, h) for h in horizons}
    return out


def _state_at(panel, pos):
    """Latest-known values of every feature (and the raw known inputs) at one session position; NaN becomes None."""
    if pos is None:
        return None
    date = panel["sessions"][pos]
    row = {k: (None if not np.isfinite(v) else float(v)) for k, v in panel["features"].loc[date].items()}
    raw = {f"known_{k}": (None if not np.isfinite(v.loc[date]) else float(v.loc[date])) for k, v in panel["known"].items()}
    return {"date": str(date.date()), "features": row, "knownInputs": raw}


def episode_tables(panel, extra_features=None):
    """Algorithmic episodes at -10/-15/-20%, and for every >= 15% episode: the dates, depth, recovery or censoring, the landmark sequence with the
    latest-known state at each landmark, early-damage metrics of every frozen binary trigger, and the slow-warning lead times."""
    close, sessions = panel["close"], panel["sessions"]
    episodes = M.underwater_episodes(close)
    out = {"counts": {f"depth_ge_{int(t * 100)}pct": len(M.episodes_at_least(episodes, t)) for t in M.EPISODE_THRESHOLDS}, "episodes": [], "byTrigger": {}}
    major = M.episodes_at_least(episodes, M.PRIMARY_EPISODE_THRESHOLD)
    triggers = panel["triggers"]
    for ep in major:
        landmarks = M.episode_landmarks(close, ep)
        record = {"peak": str(sessions[ep["peakPos"]].date()), "trough": str(sessions[ep["troughPos"]].date()), "depth": float(ep["depth"]),
                  "recovery": (str(sessions[ep["recoveryPos"]].date()) if ep["recoveryPos"] is not None else None), "rightCensored": bool(ep["censored"]),
                  "landmarks": {k: _state_at(panel, v) for k, v in landmarks.items()}}
        if extra_features is not None:
            record["internalsAtLandmarks"] = {k: ({n: (None if not np.isfinite(extra_features[n].loc[sessions[v]]) else float(extra_features[n].loc[sessions[v]])) for n in extra_features.columns}
                                                  if v is not None else None) for k, v in landmarks.items()}
        record["slowWarnings"] = {w: M.slow_warning_lead((panel["known"][s] < 0).astype(float).where(panel["known"][s].notna()), ep)
                                  for w, s in SLOW_WARNING_STATES.items() if s in panel["known"]}
        out["episodes"].append(record)
    for name in M.BASELINE_TRIGGERS:
        on = triggers[name]
        per = {f"threshold_{int(t * 100)}": [M.first_trigger_damage(close, ep, on) for ep in M.episodes_at_least(episodes, t)] for t in M.EPISODE_THRESHOLDS}
        out["byTrigger"][name] = {"damage": {k: M.damage_summary(v) for k, v in per.items()}, "perEpisode": per[f"threshold_{int(M.PRIMARY_EPISODE_THRESHOLD * 100)}"],
                                  "profile": M.trigger_profile(on, close, major)}
    return out


def analyze(panel, extra_features=None):
    """The full registered result for one panel (CORE, optionally with the EXTENDED internals columns tabulated on their own period)."""
    result = {"sample": sample_description(panel), "features": feature_tables(panel), "episodes": episode_tables(panel, extra_features)}
    if extra_features is not None:
        result["extendedInternals"] = {"tier": "EXTENDED_KR_INTERNALS", "features": feature_tables(panel, extra_features),
                                       "sample": {n: {"start": str(extra_features[n].first_valid_index().date()) if extra_features[n].notna().any() else None,
                                                      "end": str(extra_features[n].last_valid_index().date()) if extra_features[n].notna().any() else None,
                                                      "validDays": int(extra_features[n].notna().sum())} for n in extra_features.columns}}
    result["statements"] = ["Descriptive only; no feature or trigger is validated, predictive or best.", "Every family is read on its own cadence rows.",
                            "The sample is historically known; this is exploratory development on outcome-exposed history."]
    M.assert_no_forbidden_keys(result)
    return result


def coverage_tables(audit_views, sessions, selected_roles):
    """Diagnostic coverage of every acquired source in the core windows from observation DATES only (not part of the decision)."""
    out = {}
    weekly, monthly = M.period_end_dates(sessions, "W"), M.period_end_dates(sessions, "M")
    for sid, view in audit_views.items():
        if view.get("status") != "ACQUIRED" or len(view["dates"]) == 0:
            out[sid] = {"status": view.get("status"), "windows": None}
            continue
        entry = S.SOURCES[sid]
        windows = {}
        for name, (a, b) in S.CORE_WINDOWS.items():
            windows[name] = {"sessionCoverage": M.session_coverage(view["dates"], sessions, a, b),
                             "weeklyKnownCoverage": S.known_coverage(view["dates"], sid, sessions, weekly, name) if not entry["role"].startswith("KR_") else None,
                             "monthlyKnownCoverage": S.known_coverage(view["dates"], sid, sessions, monthly, name) if not entry["role"].startswith("KR_") else None}
        out[sid] = {"status": "ACQUIRED", "first": str(pd.DatetimeIndex(view["dates"]).min().date()), "last": str(pd.DatetimeIndex(view["dates"]).max().date()),
                    "role": entry["role"], "windows": windows}
    return out
