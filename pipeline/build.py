"""Orchestrate the pipeline and write the site data artifact.

Run from the repo root:  python3 -m pipeline.build
Outputs: data/site-data.json

Core holdings get the full treatment (purged walk-forward backtest + cards).
The whole dynamically-resolved KR/US universe is screened at the trade horizon
for daily trade ideas and for the market-sentiment panel.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import sys
import time
import traceback
import warnings
from datetime import datetime, timezone
from numbers import Integral, Real
from pathlib import Path

from . import direction as direction_mod
from . import entry as entry_mod
from . import evidence as evidence_mod
from . import expert_consensus as expert_mod
from . import features as F
from . import fundamentals as fundamentals_mod
from . import historical_calibration as histcal_mod
from . import historical_outcomes as histout_mod
from . import historical_replay as replay_mod
from . import indices as indices_mod
from . import ledger as ledger_mod
from . import longterm as longterm_mod
from . import kelly_portfolio as kelly_mod
from . import macro as macro_mod
from . import model as M
from . import opportunity as opportunity_mod
from . import pit_data
from . import provenance as prov_mod
from . import regime as regime_mod
from . import risk as risk_mod
from . import rotation as rotation_mod
from . import sentiment as sentiment_mod
from . import state as state_mod
from . import trade as trade_mod
from . import quality as quality_mod
from . import universe as universe_mod
from .config import REPO_ROOT, load_config
from .datafeed import fetch_macro, fetch_prices, fetch_vix

# These are expected for short calibration windows; they don't affect results.
warnings.filterwarnings("ignore", message="The least populated class")
warnings.filterwarnings("ignore", message="Number of classes in training fold")

OUT = REPO_ROOT / "data" / "site-data.json"
AUDIT_OUT = REPO_ROOT / "data" / "audit.json"


def _json_default(obj):
    """Last-resort encoder so a stray pandas/NumPy value can never break the
    build (and block the Pages deploy) the way a raw Timestamp once did.

    The pipeline should hand plain Python types to ``json.dumps``; anything that
    slips through — a ``Timestamp``, ``datetime``, NumPy scalar, or array — is
    coerced here to a JSON-safe form instead of raising ``TypeError``.
    """
    # pandas Timestamp / NaT and stdlib datetime/date all expose isoformat().
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    isoformat = getattr(obj, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except Exception:
            pass
    item = getattr(obj, "item", None)  # NumPy scalar -> native Python scalar
    if callable(item):
        try:
            return obj.item()
        except Exception:
            pass
    tolist = getattr(obj, "tolist", None)  # NumPy array / pandas Index/Series
    if callable(tolist):
        try:
            return obj.tolist()
        except Exception:
            pass
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def _json_sanitize(obj):
    """Recursively replace non-finite floats (NaN/±Inf) with ``None``.

    We serialize with ``allow_nan=False`` so the artifact is strictly valid
    JSON (the site's ``JSON.parse`` rejects the bare ``NaN`` token). A NaN metric
    means "not available", so ``null`` is the honest representation — and letting
    one slip through would otherwise abort the write and block the Pages deploy.
    Integers and booleans are left untouched; other objects fall through to
    ``_json_default`` at encode time.
    """
    if isinstance(obj, dict):
        return {k: _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(v) for v in obj]
    # Real, non-integer numbers (Python float, NumPy float32/64, ...).
    if isinstance(obj, Real) and not isinstance(obj, (bool, Integral)):
        try:
            f = float(obj)
        except (TypeError, ValueError):
            return obj
        return f if math.isfinite(f) else None
    return obj


def _dumps(payload) -> str:
    return json.dumps(_json_sanitize(payload), ensure_ascii=False, indent=2, allow_nan=False, default=_json_default)


def volume_surge(price) -> float | None:
    """Recent 5-day average volume vs the trailing 60-day average.

    A reading > 1 means money/attention is rushing in relative to normal — a
    crude but self-contained proxy for where liquidity is rotating.
    """
    if "Volume" not in price:
        return None
    vol = price["Volume"].dropna()
    if len(vol) < 60:
        return None
    recent = vol.iloc[-5:].mean()
    base = vol.iloc[-60:].mean()
    if not base or base <= 0:
        return None
    return round(float(recent / base), 2)


def _load_prior(path=None) -> tuple[dict, dict]:
    """Load only the last validated/deployed production state.

    ``data/site-data.json`` is never consulted because a committed preview may
    be synthetic.  CI supplies ``PRIOR_STATE_PATH`` from signal-history.
    """
    return state_mod.load_prior_state(
        path or os.environ.get("PRIOR_STATE_PATH"),
        expected_schema_version=prov_mod.SCHEMA_VERSION,
        expected_model_version=prov_mod.MODEL_VERSION,
    )


def _load_validation_status(path=None, min_paper_days: int = 126) -> dict:
    fallback = {
        "paperDays": 0, "maturedSignals": 0, "eligibleDates": 0,
        "firstSignalDate": None, "lastSignalDate": None,
        "regionIC": {}, "costAdjustedExcessReturn": None, "MDD": None,
        "CVaR": None, "liveValidationEligible": False, "liveValidated": False,
        "reasons": [f"paper_history_below_{min_paper_days}_business_days"],
    }
    summary_path = path or os.environ.get("PAPER_SUMMARY_PATH")
    if not summary_path:
        return fallback
    try:
        summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    except Exception:
        fallback["reasons"].append("paper_summary_unavailable")
        return fallback
    status = dict(summary.get("validationStatus") or fallback)
    status["liveValidated"] = False
    if int(status.get("paperDays") or 0) < min_paper_days:
        status["liveValidationEligible"] = False
    return status


def _load_jsonl(path: str | None) -> list[dict]:
    if not path:
        return []
    try:
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
                if line.strip()]
    except Exception:
        return []


def _load_historical_evidence(cfg) -> dict:
    """Read the HISTORICAL_OOS ledger, kept strictly apart from the paper ledger.

    CI supplies these from the ``signal-history`` branch, the same way the
    prospective ledger is supplied. Absence is normal on a fresh clone and is
    reported as a state, never as an error: the build still runs, Kelly simply
    has no historical prior and says so.
    """
    signals = _load_jsonl(os.environ.get("HISTORICAL_SIGNALS_PATH"))
    outcomes = _load_jsonl(os.environ.get("HISTORICAL_OUTCOMES_PATH"))
    diagnostics = kelly_mod.load_json(os.environ.get("HISTORICAL_DIAGNOSTICS_PATH"), {}) or {}
    model_spec = kelly_mod.load_json(os.environ.get("OPPORTUNITY_MODEL_PATH"), {}) or {}
    warning_spec = kelly_mod.load_json(os.environ.get("WARNING_MODEL_PATH"), {}) or {}

    # Records from an older replay generation describe a different model and
    # must not be pooled with the current one.
    expected = prov_mod.REPLAY_VERSION
    mismatched = sum(1 for s in signals if s.get("replayVersion") not in (None, expected))
    signals = [s for s in signals if s.get("replayVersion") in (None, expected)]
    keep_ids = {s.get("id") for s in signals}
    outcomes = [o for o in outcomes if o.get("id") in keep_ids] if keep_ids else []

    cfg_replay = cfg.historical_replay or {}
    horizon = int(cfg_replay.get("horizonDays", 126))
    calibration = histcal_mod.calibrate(
        outcomes, horizon=horizon,
        buckets=cfg_replay.get("alphaPercentileBuckets",
                               histcal_mod.DEFAULT_BUCKETS),
        cfg={"minEffectiveDates": int(cfg_replay.get("minEffectiveDates", 30)),
             "shrinkagePriorStrength": float(cfg_replay.get("shrinkagePriorStrength", 30))},
        diagnostics=diagnostics,
        cost_adjusted=bool(cfg_replay.get("costAdjusted", True)),
        require_pit=bool(cfg_replay.get("requirePitQuality", True)),
    ) if outcomes else {"available": False, "reason": "historical_ledger_unavailable",
                        "regions": {}, "horizonDays": horizon}
    coverage = (histout_mod.coverage_summary(signals, outcomes, horizon=horizon)
                if signals else {})
    dataset = opportunity_mod.build_dataset(signals, outcomes) if signals and outcomes else None
    return {
        "signals": signals, "outcomes": outcomes, "diagnostics": diagnostics,
        "calibration": calibration, "coverage": coverage, "dataset": dataset,
        "modelSpec": model_spec, "warningSpec": warning_spec,
        "replayVersionMismatchedRecords": mismatched,
    }


def _historical_validation_block(historical: dict, cfg) -> dict:
    """The Historical Validation panel — always visibly separate from paper."""
    diagnostics = historical.get("diagnostics") or {}
    coverage = historical.get("coverage") or {}
    calibration = historical.get("calibration") or {}
    spec = historical.get("modelSpec") or {}
    available = bool(historical.get("signals"))
    return {
        "evidenceClass": "HISTORICAL_OOS",
        "available": available,
        "reason": None if available else "historical_replay_ledger_not_supplied",
        "replayVersion": diagnostics.get("replayVersion") or prov_mod.REPLAY_VERSION,
        "featureVersion": diagnostics.get("featureVersion") or prov_mod.FEATURE_VERSION,
        "dataVersion": prov_mod.DATA_VERSION,
        "modelVersion": diagnostics.get("modelVersion"),
        "replayPeriod": [diagnostics.get("firstDate"), diagnostics.get("lastDate")],
        "replayFrequency": diagnostics.get("frequency"),
        "replayDates": diagnostics.get("replayDates"),
        "oosSignals": coverage.get("signalsRecorded"),
        "uniqueDates": coverage.get("uniqueDates"),
        "maturedSignals": coverage.get("maturedSignals"),
        "maturedByHorizon": coverage.get("maturedByHorizon"),
        "pitCoveragePct": (round(float(diagnostics.get("meanPitCoverage") or 0) * 100, 1)
                            if diagnostics.get("meanPitCoverage") is not None else None),
        "pitQuality": pit_data.quality_label(diagnostics.get("meanPitCoverage")),
        "survivorshipRisk": diagnostics.get("survivorshipRisk"),
        "survivorshipNote": diagnostics.get("survivorshipNote"),
        "fundamentalsPointInTime": diagnostics.get("fundamentalsPit"),
        "macroPitStatus": diagnostics.get("macroPitStatus"),
        "knownDeviationsFromProduction": diagnostics.get("knownDeviationsFromProduction") or [],
        "replayVersionMismatchedRecords": historical.get("replayVersionMismatchedRecords", 0),
        "alphaCalibration": calibration,
        "finalHoldoutStart": (cfg.opportunity or {}).get("finalHoldoutStart"),
        "walkForward": spec.get("walkForward"),
        "overfittingDiagnostics": spec.get("diagnostics"),
        "modelAcceptance": spec.get("acceptance"),
        "holdoutResult": spec.get("holdout"),
        "notLiveEvidenceKo": ("과거 재현 결과는 실시간 검증과 다른 종류의 증거입니다. "
                               "두 값을 합산하거나 같은 표로 섞지 않습니다."),
    }


def _prospective_validation_block(validation_status: dict) -> dict:
    """The paper-ledger panel, with tracking and maturity kept apart."""
    status = validation_status or {}
    return {
        "evidenceClass": "PROSPECTIVE_PAPER",
        "trackingSince": status.get("firstSignalDate"),
        "trackingDays": status.get("trackingDays", status.get("paperDays", 0)),
        "signalsRecorded": status.get("signalsRecorded"),
        "uniqueDates": status.get("uniqueDates"),
        "maturedObservationDays": status.get("maturedObservationDays", 0),
        "maturedSignals": status.get("maturedSignals", 0),
        "maturedByHorizon": status.get("maturedByHorizon") or {},
        "eligibleDates": status.get("eligibleDates", 0),
        "regionIC": status.get("regionIC") or {},
        "costAdjustedExcessReturn": status.get("costAdjustedExcessReturn"),
        "MDD": status.get("MDD"), "CVaR": status.get("CVaR"),
        "liveValidated": False,
        "reasons": status.get("reasons") or [],
        "roleKo": ("모델을 더 이상 손대지 않은 상태에서 실제 미래에도 재현되는지를 "
                    "확인하는 최종 증거입니다."),
    }


def _radar_candidates(live_rows: list[dict], holdings: set[str]) -> list[dict]:
    """Attach core-holding membership so warnings on held names sort first."""
    rows = []
    for row in live_rows:
        rows.append({**row, "isCoreHolding": row.get("ticker") in holdings})
    return rows


def _opportunity_transitions(current: dict | None, prior: dict,
                             prior_status: dict) -> dict:
    """What is NEW today, based on state transitions rather than levels.

    A name that has been HIGH since Tuesday is not news on Friday. Alerting on
    the level would re-fire the same alarm every day until the user stopped
    reading it, so the comparison is against the last validated production
    state and only transitions are surfaced.
    """
    if not prior_status.get("available"):
        return {"available": False, "reason": prior_status.get("reason"),
                "hasChanges": False,
                "summaryKo": "비교 가능한 이전 운영 상태가 없어 신규 여부를 판단하지 않습니다."}
    previous = prior.get("opportunityTiersByTicker") or {}
    previous_warn = prior.get("warningTiersByTicker") or {}
    current_tiers: dict[str, str] = {}
    current_warn: dict[str, str] = {}
    for region_rows in ((current or {}).get("opportunityRadar") or {}).get("regions", {}).values():
        for row in region_rows:
            current_tiers[row["ticker"]] = row["tier"]
    for region_rows in ((current or {}).get("warningRadar") or {}).get("regions", {}).values():
        for row in region_rows:
            current_warn[row["ticker"]] = row["tier"]

    def promoted(now: dict, before: dict, ladder: tuple) -> list[dict]:
        rank = {tier: i for i, tier in enumerate(ladder)}
        out = []
        for ticker, tier in sorted(now.items()):
            was = before.get(ticker)
            if was == tier:
                continue
            if rank.get(tier, 0) > rank.get(was, -1):
                out.append({"ticker": ticker, "before": was, "after": tier})
        return out

    new_opportunities = promoted(
        current_tiers, previous,
        ("WATCH", "EMERGING_OPPORTUNITY", "VALIDATED_OPPORTUNITY"))
    new_warnings = promoted(
        current_warn, previous_warn,
        ("WATCH", "ELEVATED_WARNING", "CRITICAL_WARNING"))
    resolved = [{"ticker": t, "before": previous[t]} for t in sorted(previous)
                if t not in current_tiers or current_tiers[t] == "WATCH"
                and previous[t] != "WATCH"]
    has_changes = bool(new_opportunities or new_warnings or resolved)
    return {
        "available": True, "hasChanges": has_changes,
        "newOpportunities": new_opportunities,
        "newWarnings": new_warnings,
        "resolvedOpportunities": resolved,
        "basisKo": "이전 운영 상태 대비 등급이 올라간 종목만 신규로 표시합니다.",
        "summaryKo": ("오늘 새로 발생한 변화가 있습니다." if has_changes
                      else "기회·경고 등급에 신규 변화 없음"),
    }


def _attach_entry_states(long_term: dict | None, entry_feats: dict, cfg_lt: dict) -> dict | None:
    """Compute universe-relative overheat percentiles per region and attach an
    entryState to every unblocked long-term row. Blocked rows are sanitized."""
    if not long_term:
        return long_term
    if long_term.get("weightsWithheld"):
        for blob in (long_term.get("regions") or {}).values():
            for group in ("picks", "researchTable", "validationCrossSection"):
                for row in (blob or {}).get(group, []):
                    row.pop("entry", None)
                    row.pop("entryState", None)
        return long_term
    import pandas as _pd
    sector_cap = float(cfg_lt.get("maxSectorWeight", 0.30)) * 100
    for region, blob in (long_term.get("regions") or {}).items():
        rows = (list(blob.get("picks", [])) + list(blob.get("researchTable", []))
                + list(blob.get("validationCrossSection", [])))
        tickers = {r["ticker"] for r in rows}
        scores = {t: entry_mod.overheat_score(entry_feats[t]) for t in tickers if t in entry_feats}
        scores = {t: v for t, v in scores.items() if v is not None}
        ranked = (_pd.Series(scores).rank(pct=True) * 100).to_dict() if scores else {}
        pick_tickers = {r["ticker"] for r in blob.get("picks", [])}
        sector_exposure = blob.get("sectorExposure", {})
        for row in rows:
            t = row["ticker"]
            f = entry_feats.get(t)
            if not f:
                row["entry"] = {"entryState": "WATCH", "reasons": ["진입 판단용 가격 데이터 부족"], "overheatPercentile": None}
            else:
                conc = sector_exposure.get(row.get("sector")) if t in pick_tickers else None
                row["entry"] = entry_mod.classify(f, ranked.get(t), conc, sector_cap)
            timing = longterm_mod.entry_invalidation(row["entry"].get("entryState"))
            if timing:
                conditions = [c for c in (row.get("invalidation") or []) if c.get("key") != "ENTRY_STATE"]
                row["invalidation"] = conditions + [timing]
    return long_term


def _changes_since_prior(long_term: dict | None, model_portfolio: dict | None,
                         macro_regime: dict | None, prior: dict,
                         prior_status: dict) -> dict:
    """Compact, deterministic diff against the last validated production state."""
    if not prior_status.get("available"):
        return {"available": False, "reason": prior_status.get("reason"), "hasChanges": False,
                "summaryKo": "비교 가능한 이전 운영 상태가 없습니다."}
    regions = (long_term or {}).get("regions") or {}
    current_holdings = {r: set((b or {}).get("holdings") or []) for r, b in regions.items()}
    previous_holdings = {r: set(v or []) for r, v in (prior.get("holdingsByRegion") or {}).items()}
    added, removed = [], []
    for region in sorted(set(current_holdings) | set(previous_holdings)):
        added.extend({"region": region, "ticker": t} for t in sorted(current_holdings.get(region, set()) - previous_holdings.get(region, set())))
        removed.extend({"region": region, "ticker": t} for t in sorted(previous_holdings.get(region, set()) - current_holdings.get(region, set())))
    current_weights = (model_portfolio or {}).get("finalWeights") or {}
    previous_weights = prior.get("modelPortfolioWeights") or {}
    increased, decreased = [], []
    for ticker in sorted(set(current_weights) | set(previous_weights)):
        before, after = float(previous_weights.get(ticker, 0.0)), float(current_weights.get(ticker, 0.0))
        delta = after - before
        if abs(delta) < 0.005:
            continue
        target = increased if delta > 0 else decreased
        target.append({"ticker": ticker, "beforePct": round(before * 100, 2),
                       "afterPct": round(after * 100, 2), "changePctPt": round(delta * 100, 2)})
    current_entries = {}
    for blob in regions.values():
        for row in (blob or {}).get("researchTable", []):
            state = ((row.get("entry") or {}).get("entryState"))
            if state:
                current_entries[row["ticker"]] = state
    previous_entries = prior.get("entryStatesByTicker") or {}
    entry_changes = [
        {"ticker": ticker, "before": previous_entries[ticker], "after": current_entries[ticker]}
        for ticker in sorted(set(previous_entries) & set(current_entries))
        if previous_entries[ticker] != current_entries[ticker]
    ]
    before_regime = prior.get("macroRegime")
    after_regime = (macro_regime or {}).get("regime")
    regime_change = ({"before": before_regime, "after": after_regime}
                     if before_regime and after_regime and before_regime != after_regime else None)
    has_changes = bool(added or removed or increased or decreased or entry_changes or regime_change)
    return {
        "available": True, "hasChanges": has_changes,
        "summaryKo": "주요 변화가 있습니다." if has_changes else "이전 실행 대비 주요 변화 없음",
        "added": added, "removed": removed, "weightIncreased": increased,
        "weightDecreased": decreased, "entryStateChanged": entry_changes,
        "regimeChanged": regime_change,
    }


def core_card(feat, fcols, ticker, cfg, diagnosis):
    """Full multi-horizon signal card + backtest for a held position."""
    signals = []
    fits = 0
    for h in cfg.horizons:
        tc = f"target_{h}d"
        current = M.current_signal(feat, fcols, tc, cfg.model)
        if current is None:
            continue
        fits += 1
        res = M.walk_forward(feat, fcols, tc, cfg.model, cfg.model.oos_start, h)
        fits += max(0, len(res) // cfg.model.step_size)
        threshold = M.dynamic_threshold(res, cfg.model)
        signals.append(
            {
                "horizon": h,
                "probUp": current["probUp"],
                "prediction": current["prediction"],
                "alert": "PAPER ONLY",
                "threshold": threshold,
                "oos": M.oos_metrics(res, threshold),
                "backtest": M.backtest(res, region=cfg.region_of(ticker)),
                "foldAudit": res[[c for c in res.columns if c.startswith("fold")]].drop_duplicates().to_dict("records") if not res.empty else [],
            }
        )
    card = {
        "ticker": ticker,
        "asOf": feat.dropna(subset=fcols).index[-1].strftime("%Y-%m-%d"),
        "lastClose": diagnosis["lastClose"],
        "signals": signals,
        "risk": diagnosis,
    }
    return card, fits


def run(cfg) -> dict:
    universe, names = universe_mod.resolve(cfg)
    universe_diagnostics = universe_mod.last_diagnostics()
    download = list(dict.fromkeys(
        [t for names_ in universe.values() for t in names_] + cfg.core + list(cfg.benchmarks.values())
    ))
    print(f"core={cfg.core} | universe={ {k: len(v) for k, v in universe.items()} } | "
          f"download={len(download)} | FRED={cfg.has_fred}")

    # Core + benchmark need full history (walk-forward back to 2020); the broad
    # screening universe only needs a few years, so fetch it on a shorter window
    # to keep downloads fast for a large list.
    core_set = list(dict.fromkeys(cfg.core + list(cfg.benchmarks.values())))
    universe_only = [t for t in download if t not in core_set]
    prices = fetch_prices(core_set, cfg.model.history_start)
    prices.update(fetch_prices(universe_only, cfg.model.screen_history_start))
    missing = [t for t in download if t not in prices]
    coverage = round(100 * len(prices) / len(download), 1) if download else 0.0
    missing_core = [t for t in cfg.core if t not in prices]
    if missing_core or coverage < 95:
        raise RuntimeError(f"critical price coverage failure: coverage={coverage}%, missing_core={missing_core[:10]}")
    vix = fetch_vix(cfg.model.history_start)
    macro = fetch_macro(cfg, cfg.model.history_start)

    # Market tape (S&P 500 / NASDAQ / KOSPI / ...). Never let it kill a build.
    try:
        market_indices = indices_mod.fetch()
    except Exception as exc:
        print(f"  warning: index tape failed: {exc}")
        market_indices = []
    market_data_health = indices_mod.health(market_indices)
    benchmark_closes = {
        region: prices[ticker]["Close"]
        for region, ticker in cfg.benchmarks.items() if ticker in prices
    }

    th = cfg.trade_horizon
    target_horizons = sorted(set(cfg.horizons) | {th})
    all_tickers = list(dict.fromkeys([t for names_ in universe.values() for t in names_] + cfg.core))

    core_cards, ideas, screened = [], [], []
    details = {}
    diags = {}
    entry_feats = {}
    audit = {"folds": {}, "oos": {}, "eligibility": {}, "warnings": ["survivorship_bias_unresolved", "macro_vintage_revision_bias_possible"]}
    fits = 0
    latest_date = None
    errors = []

    for ticker in all_tickers:
        if ticker not in prices:
            continue
        try:
            region = cfg.region_of(ticker)
            regional_benchmark = cfg.benchmarks.get(region)
            bench = benchmark_closes.get(region) if ticker != regional_benchmark else None
            feat = F.build_features(prices[ticker], benchmark_close=bench, vix=vix, macro=macro)
            feat = F.add_targets(feat, target_horizons)
            fcols = F.feature_columns(feat)
            clean = feat.dropna(subset=fcols)
            if clean.empty:
                continue
            latest_date = max(latest_date, clean.index[-1]) if latest_date else clean.index[-1]
            diagnosis = risk_mod.diagnose(ticker, feat)
            diags[ticker] = diagnosis
            vsurge = volume_surge(prices[ticker])
            try:
                entry_feats[ticker] = entry_mod.entry_features(feat, volume_surge=vsurge)
            except Exception:
                pass

            tsig = M.current_signal(feat, fcols, f"target_{th}d", cfg.model)
            details[ticker] = {
                "volSurge": vsurge,
                "region": region,
                "modelScore": tsig["probUp"] if tsig else None,
                "probUp": None,
                "regime": diagnosis["regime"],
                "lastClose": diagnosis["lastClose"],
                "asOf": clean.index[-1].strftime("%Y-%m-%d"),
                "ma50": diagnosis["ma50"], "ma200": diagnosis["ma200"],
                "rsi14": diagnosis["rsi14"], "realizedVol": diagnosis["realizedVol"],
                "maxDrawdown252d": diagnosis["maxDrawdown252d"],
                "relMomentum": diagnosis["relMomentum"], "pct52wHigh": diagnosis["pct52wHigh"],
                "mom63": round(diagnosis["mom63"] * 100, 1) if diagnosis["mom63"] is not None else None,
                "riskFlags": [f["message"] for f in diagnosis["riskFlags"]],
            }
            if tsig is not None:
                fits += 1
                stats = M.horizon_return_stats(feat, th)
                tres = M.walk_forward(feat, fcols, f"target_{th}d", cfg.model, cfg.model.oos_start, th)
                threshold = M.dynamic_threshold(tres, cfg.model)
                quality = M.oos_metrics(tres, threshold)
                audit["oos"][ticker] = quality
                if not tres.empty:
                    audit["folds"][ticker] = tres[[c for c in tres.columns if c.startswith("fold")]].drop_duplicates().to_dict("records")
                idea = trade_mod.build_idea(ticker, region, tsig["probUp"], stats, th, tsig["asOf"], diagnosis["regime"], diagnosis, quality)
                screened.append({
                    "ticker": ticker, "region": region, "modelScore": tsig["probUp"], "probUp": None,
                    "qualityGrade": quality.get("qualityGrade", "REJECT"), "eligible": quality.get("eligible", False),
                    "eligibilityReasons": quality.get("eligibilityReasons", []),
                    "regime": diagnosis["regime"], "qualifies": idea is not None,
                    "aboveMA50": diagnosis["aboveMA50"], "aboveMA200": diagnosis["aboveMA200"],
                    "mom63": diagnosis["mom63"], "volSurge": vsurge,
                })
                if idea is not None:
                    ideas.append(idea)

            if ticker in cfg.core:
                print(f"  core {ticker} ...")
                card, cfits = core_card(feat, fcols, ticker, cfg, diagnosis)
                core_cards.append(card)
                fits += cfits
        except Exception as exc:
            msg = f"{ticker}: {exc}"
            errors.append(msg)
            print(f"  error on {ticker}: {exc}")

    sentiment = sentiment_mod.summarize(screened, macro, vix)

    # Prior regime + prior long-term holdings (for regime-change detection and
    # the rank buffer) come from the last artifact, if any.
    prior, prior_status = _load_prior()
    prior_regime = prior.get("macroRegime")
    prior_holdings = {
        r: list((prior.get("holdingsByRegion") or {}).get(r, []))
        for r in ("KR", "US")
    }

    # Macro DIRECTION/REGIME engine (6 axes) — the risk-budget layer. Fixed
    # thresholds are gone; missing data lowers confidence, never fakes neutral.
    macro_regime = regime_mod.build(macro, vix, prior_regime=prior_regime)
    # Thin display wrapper (region indicator tables) kept for the market panel.
    macro_summary = macro_mod.summarize(macro, vix, macro_regime)

    # Long-horizon (6-12mo) multi-factor RESEARCH layer (not a buy list).
    fundamentals = {}
    try:
        fundamentals = fundamentals_mod.fetch_fundamentals(all_tickers)
        print(f"  fundamentals: {len(fundamentals)}/{len(all_tickers)} tickers")
    except Exception as exc:
        print(f"  warning: fundamentals fetch failed: {exc}")
    bench_by_region = benchmark_closes
    # A pre-pass data-safety block so long-term weights/actions are withheld too.
    pre_block, _ = quality_mod.recommendations_blocked({
        "seed": False, "stale": False,
        "meta": {"modelsTrained": fits, "coveragePct": coverage,
                 "universeScreened": len(screened), "pipelineErrors": errors}})
    withhold = pre_block or cfg.run_mode == "researchOnly"
    try:
        long_term = longterm_mod.build(universe, prices, fundamentals, diags,
                                       cfg_lt=cfg.longterm, bench_by_region=bench_by_region,
                                       prior_holdings=prior_holdings, blocked=withhold)
        long_term = _attach_entry_states(long_term, entry_feats, cfg.longterm)
    except Exception as exc:
        print(f"  warning: long-term engine failed: {exc}")
        traceback.print_exc()
        long_term = None

    # Portfolio Kelly is an additive SHADOW layer. Its expected returns come
    # only from matured immutable-ledger outcomes supplied by CI/local replay;
    # no outcome file means an explicit risk-weighted fallback, never a made-up
    # expected return derived from today's alpha score.
    portfolio_outcomes = kelly_mod.load_jsonl(os.environ.get("PAPER_OUTCOMES_PATH"))
    themes = kelly_mod.load_json(REPO_ROOT / "data" / "themes.json", {})
    prior_model_weights = (
        prior.get("modelPortfolioWeights")
        or ((prior.get("modelPortfolio") or {}).get("finalWeights"))
        or {}
    )
    validation_status = _load_validation_status(
        min_paper_days=int(cfg.validation.get("minPaperDays", 126)))

    # HISTORICAL_OOS evidence: the same model replayed against point-in-time
    # data. Loaded from its own ledger files and never merged into the paper
    # ledger above — the two answer different questions and are combined only
    # inside the expected-return posterior, with their weights published.
    historical = _load_historical_evidence(cfg)
    historical_calibration = historical["calibration"]
    try:
        model_portfolio = kelly_mod.build_model_portfolio(
            long_term, prices, portfolio_outcomes, cfg.kelly_portfolio,
            macro_regime=macro_regime, themes=themes,
            prior_weights=prior_model_weights,
            as_of=latest_date.strftime("%Y-%m-%d") if latest_date is not None else None,
            blocked=withhold,
            validation_status=validation_status,
            benchmarks=cfg.benchmarks,
            bench_by_region=benchmark_closes,
            historical_calibration=historical_calibration,
        )
    except Exception as exc:
        print(f"  warning: Kelly portfolio engine failed: {exc}")
        traceback.print_exc()
        model_portfolio = {
            "status": "OPTIMIZATION_FAILED",
            "method": "BLENDED_CONSTRAINED_FRACTIONAL_KELLY",
            "positions": [], "finalWeights": {}, "cashPct": 100.0,
            "fallbackReason": f"engine_error:{exc.__class__.__name__}",
            "warnings": ["EXPLICIT_ENGINE_FAILURE; NO_KELLY_WEIGHTS_PUBLISHED"],
        }

    # Opportunity / Warning radars. Feature vectors come from the REPLAY engine
    # (see historical_replay.live_features) so that today's inputs are built by
    # the identical code that built the training set — the production long-term
    # table would give subtly different numbers and silently break the model.
    opportunity_radar = warning_radar = None
    radar_diagnostics = {"status": "DISABLED"}
    if (cfg.opportunity or {}).get("enabled", True) and not withhold:
        try:
            holdings = {t for blob in ((long_term or {}).get("regions") or {}).values()
                        for t in ((blob or {}).get("holdings") or [])}
            live = replay_mod.live_features(
                prices, universe, benchmarks=cfg.benchmarks, cfg_lt=cfg.longterm,
                as_of=latest_date, frequency=(cfg.historical_replay or {}).get("frequency", "W"),
                macro=macro, vix=vix, model_version=prov_mod.MODEL_VERSION)
            candidates = _radar_candidates(live["rows"], holdings)
            if candidates:
                opportunity_radar = opportunity_mod.build_radar(
                    candidates, dataset=historical["dataset"],
                    spec=historical["modelSpec"], cfg=cfg.opportunity,
                    kind="opportunity",
                    limit=int((cfg.opportunity or {}).get("limitPerRegion", 8)))
                warning_radar = opportunity_mod.build_radar(
                    candidates, dataset=historical["dataset"],
                    spec=historical["warningSpec"], cfg=cfg.opportunity,
                    kind="warning",
                    limit=int((cfg.opportunity or {}).get("limitPerRegion", 8)))
                # Explainability only: the closest historical setups and what
                # followed. Never an input to sizing.
                for rows in (opportunity_radar.get("regions") or {}).values():
                    by_ticker = {c["ticker"]: c for c in candidates}
                    for row in rows:
                        row["historicalAnalogues"] = opportunity_mod.historical_analogues(
                            by_ticker.get(row["ticker"]) or {}, historical["dataset"])
                radar_diagnostics = {
                    "status": "READY", "asOf": live["asOf"],
                    "candidates": len(candidates),
                    "featureSource": "HISTORICAL_REPLAY_ENGINE",
                    "featureVersion": prov_mod.FEATURE_VERSION,
                    "trainServeFeatureParityKo": ("오늘의 피처는 과거 학습 데이터와 동일한 "
                                                   "replay 엔진으로 생성합니다."),
                }
            else:
                radar_diagnostics = {"status": "NO_CANDIDATES"}
        except Exception as exc:
            print(f"  warning: opportunity radar failed: {exc}")
            traceback.print_exc()
            radar_diagnostics = {"status": "FAILED",
                                 "reason": f"{exc.__class__.__name__}"}
    elif withhold:
        radar_diagnostics = {"status": "BLOCKED"}

    # Verified expert / house-view consensus (semi-automatic; nothing fabricated).
    try:
        expert_consensus = expert_mod.build()
    except Exception as exc:
        print(f"  warning: expert consensus failed: {exc}")
        expert_consensus = None

    # Direction compass + sector/factor rotation are additive tools; a failed
    # download must never take the whole build down with it.
    try:
        direction = direction_mod.build(sentiment=sentiment, macro_summary=macro_summary,
                                        indices=market_indices)
    except Exception as exc:
        print(f"  warning: direction compass failed: {exc}")
        direction = None
    try:
        rotation = rotation_mod.build()
    except Exception as exc:
        print(f"  warning: rotation failed: {exc}")
        rotation = None
    # Trim breadth helper fields out of the stored screen table.
    screen_table = [
        {k: r.get(k) for k in ("ticker", "region", "modelScore", "probUp", "regime", "qualifies", "eligible", "qualityGrade", "eligibilityReasons")}
        for r in sorted(screened, key=lambda x: x.get("modelScore") or -1, reverse=True)
    ]

    # Money-flow proxy: where is liquidity rotating? Volume surging into names
    # that are also rising (positive momentum), ranked per region.
    flows = {}
    for region in ("KR", "US"):
        cand = [
            {"ticker": r["ticker"], "region": region,
             "volSurge": r["volSurge"], "mom63": round((r["mom63"] or 0) * 100, 1),
             "regime": r["regime"]}
            for r in screened
            if r["region"] == region and r.get("volSurge") and (r.get("mom63") or 0) > 0
        ]
        flows[region] = sorted(cand, key=lambda x: x["volSurge"], reverse=True)[:6]

    eligible_count = sum(1 for r in screened if r.get("eligible"))
    for region, blob in ((long_term or {}).get("regions") or {}).items():
        diag = universe_diagnostics.setdefault("regions", {}).setdefault(region, {})
        diag["dataInsufficientExcluded"] = len((blob or {}).get("dataInsufficient") or [])
        diag["rankedCount"] = int((blob or {}).get("universeRanked") or 0)
    changes = _changes_since_prior(long_term, model_portfolio, macro_regime, prior, prior_status)
    radar_payload = {"opportunityRadar": opportunity_radar or {"regions": {}},
                     "warningRadar": warning_radar or {"regions": {}}}
    transitions = _opportunity_transitions(radar_payload, prior, prior_status)
    changes["opportunityTransitions"] = transitions

    kelly_evidence = (model_portfolio or {}).get("kellyEvidence") or {}
    spec = historical["modelSpec"] or {}
    model_comparison = {
        # Champion = what is actually deciding today's weights. Challengers are
        # measured in the same environment and are NOT allowed to change the
        # portfolio until they win on both evidence classes.
        "champion": {
            "name": "CONVICTION_RISK_WEIGHTED",
            "descriptionKo": "현재 운영 중인 컨빅션 위험가중 선정·비중",
            "inProduction": True,
            "allocationMethod": (model_portfolio or {}).get("method"),
            "kellyApplied": (model_portfolio or {}).get("kellyApplied", False),
        },
        "challengers": [
            {
                "name": "HISTORICAL_KELLY_ENHANCED",
                "descriptionKo": "과거 OOS calibration으로 기대수익 prior를 만든 Fractional Kelly",
                "inProduction": False,
                "evidenceClass": "HISTORICAL_OOS",
                "status": (kelly_evidence.get("activation") or {}).get("code", "NO_EVIDENCE"),
                "statusKo": (kelly_evidence.get("activation") or {}).get("labelKo"),
                "historicalCalibrationAvailable": bool(historical_calibration.get("available")),
                "promotionRuleKo": ("과거 OOS와 실시간 paper 양쪽에서 초과수익·rank IC·"
                                     "calibration·회전율·MDD·CVaR·안정성이 모두 우세할 때만 승격합니다."),
            },
            {
                "name": "ML_OPPORTUNITY_ENHANCED",
                "descriptionKo": "Historical OOS로 학습한 기회 확률 모델",
                "inProduction": False,
                "evidenceClass": "HISTORICAL_OOS",
                "status": spec.get("status", "NOT_TRAINED"),
                "accepted": bool(spec.get("accepted")),
                "acceptanceFailures": (spec.get("acceptance") or {}).get("failures") or [],
                "scope": "OPPORTUNITY_RADAR_ONLY_NOT_CORE_PORTFOLIO",
                "promotionRuleKo": ("Core Portfolio 선정기를 대체하지 않습니다. "
                                     "A/B 비교에서 명확히 우세할 때만 승격 검토 대상이 됩니다."),
            },
        ],
        "separationKo": ("Core Portfolio와 Opportunity는 하나의 점수로 합치지 않습니다. "
                          "서로 다른 질문에 답하는 별개의 층입니다."),
    }

    payload = {
        "portfolioName": cfg.portfolio_name,
        "primary": cfg.primary,
        "benchmark": cfg.benchmark,
        "benchmarks": cfg.benchmarks,
        "horizons": cfg.horizons,
        "tradeHorizon": th,
        "names": names,
        "dataSource": "Yahoo Finance + FinanceDataReader/Stooq fallback (market) + FRED (macro)" if cfg.has_fred else "Yahoo Finance + FinanceDataReader/Stooq fallback (market); FRED disabled",
        "indices": market_indices,
        "marketDataHealth": market_data_health,
        "universeDiagnostics": universe_diagnostics,
        "changesSincePrior": changes,
        "direction": direction,
        "rotation": rotation,
        "longTerm": long_term,
        "modelPortfolio": model_portfolio,
        "macroRegime": macro_regime,
        "expertConsensus": expert_consensus,
        "tradeIdeas": trade_mod.rank_ideas(ideas),
        "recommendationsBlocked": False,
        "priorState": prior_status,
        "validationStatus": validation_status,
        "historicalValidation": _historical_validation_block(historical, cfg),
        "prospectiveValidation": _prospective_validation_block(validation_status),
        "kellyEvidence": kelly_evidence,
        "opportunityRadar": opportunity_radar,
        "warningRadar": warning_radar,
        "radarDiagnostics": radar_diagnostics,
        "modelComparison": model_comparison,
        "runMode": cfg.run_mode,
        "screened": screen_table,
        "details": details,
        "flows": flows,
        "sentiment": sentiment,
        "core": core_cards,
        "macro": macro_summary,
        "meta": {
            "modelsTrained": fits,
            "universeScreened": len(screened),
            "latestDataDate": latest_date.strftime("%Y-%m-%d") if latest_date is not None else None,
            "sourceAsOf": datetime.now(timezone.utc).strftime("%Y-%m-%d") if fundamentals else None,
            "fredEnabled": cfg.has_fred,
            "ecosEnabled": cfg.has_ecos,
            "macroCoverage": macro_regime.get("coverage") if macro_regime else 0.0,
            "tickersRequested": len(download),
            "tickersFetched": len(prices),
            "coveragePct": coverage,
            "coverageFloor": cfg.coverage_floor,
            "missingSample": missing[:10],
            "indicesFetched": len(market_indices),
            "indicesCurrent": market_data_health["current"],
            "indicesDelayed": market_data_health["delayed"],
            "indicesStale": market_data_health["stale"],
            "eligibleSignals": eligible_count,
            "fundamentalsCovered": len(fundamentals),
            "runMode": cfg.run_mode,
            "survivorshipBias": "unresolved_current_constituents_only",
            "coreErrors": errors,
            "pipelineErrors": errors,
        },
    }
    blocked, reasons = quality_mod.recommendations_blocked(payload)
    payload["recommendationsBlocked"] = blocked
    payload["blockReasons"] = sorted(set(reasons))
    if blocked:
        # A blocked artifact must not carry ANY actionable output: short-term
        # ideas AND long-term sleeve weights/entry actions are all withheld.
        payload["tradeIdeas"] = {"KR": [], "US": []}
        if payload.get("longTerm") and not payload["longTerm"].get("weightsWithheld"):
            payload["longTerm"] = longterm_mod.build(
                universe, prices, fundamentals, diags, cfg_lt=cfg.longterm,
                bench_by_region=bench_by_region, prior_holdings=prior_holdings, blocked=True)
            payload["longTerm"] = _attach_entry_states(payload["longTerm"], entry_feats, cfg.longterm)
        # A blocked artifact must not expose portfolio positions, weights, or
        # allocation explanations even if the pre-pass had not caught it.
        portfolio = payload.get("modelPortfolio") or {}
        payload["modelPortfolio"] = {
            "status": "BLOCKED",
            "method": portfolio.get("method", "BLENDED_CONSTRAINED_FRACTIONAL_KELLY"),
            "positions": [], "finalWeights": {}, "riskWeightedWeights": {},
            "constrainedKellyWeights": {}, "cashPct": None,
            "kellyApplied": False, "kellyAllocationImpactPct": 0.0,
            "fallbackReason": "recommendations_blocked",
            "warnings": ["RECOMMENDATIONS_BLOCKED; WEIGHTS_WITHHELD"],
        }
        payload["changesSincePrior"] = {
            "available": False, "hasChanges": False,
            "reason": "recommendations_blocked",
            "summaryKo": "안전 차단 상태에서는 이전 실행 대비 행동성 변화를 표시하지 않습니다.",
        }
        # An opportunity or warning tier IS an actionable call, so the same rule
        # that hides positions and entry states hides the radars.
        for key in ("opportunityRadar", "warningRadar"):
            payload[key] = {"regions": {}, "blocked": True,
                            "reason": "recommendations_blocked"}
        payload["radarDiagnostics"] = {"status": "BLOCKED"}
    payload["audit"] = audit
    return payload


def main() -> int:
    cfg, _ = load_config()
    t0 = time.time()
    payload = run(cfg)
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat()
    payload["stale"] = False
    payload["seed"] = False
    payload["meta"]["elapsedSec"] = round(time.time() - t0, 1)
    prov_mod.stamp(payload, cfg.run_mode)
    payload["audit"]["todaySignals"] = ledger_mod.records_from_payload(payload)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_dumps(payload) + "\n", encoding="utf-8")
    AUDIT_OUT.write_text(_dumps({"generatedAt": payload["generatedAt"], "meta": payload["meta"], "audit": payload.get("audit", {}), "blockReasons": payload.get("blockReasons", [])}) + "\n", encoding="utf-8")
    m = payload["meta"]
    ti = payload.get("tradeIdeas") or {}
    lt = payload.get("longTerm") or {}
    lt_regions = lt.get("regions") or {}
    lt_counts = "/".join(f"{r}={len((v or {}).get('picks') or [])}" for r, v in lt_regions.items()) or "none"
    print(f"wrote {OUT}: {len(payload['core'])} core, universe {m['universeScreened']}, "
          f"coverage {m['coveragePct']}%, indices {m['indicesFetched']}, "
          f"{m['modelsTrained']} model fits, eligible {m['eligibleSignals']}, "
          f"ideas KR={len(ti.get('KR') or [])}/US={len(ti.get('US') or [])}, "
          f"longterm {lt_counts} (fund {m['fundamentalsCovered']}), "
          f"blocked={payload['recommendationsBlocked']}, {m['elapsedSec']}s, data as of {m['latestDataDate']}")
    return 0


def _mark_stale(reason: str) -> None:
    """On hard failure, flag the existing artifact as stale rather than passing
    it off as a fresh successful build."""
    if not OUT.exists():
        return
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        data["stale"] = True
        data.setdefault("meta", {})["buildError"] = reason[:300]
        data["staleCheckedAt"] = datetime.now(timezone.utc).isoformat()
        OUT.write_text(_dumps(data) + "\n", encoding="utf-8")
        print(f"marked existing {OUT} as STALE: {reason}", file=sys.stderr)
    except Exception as exc:
        print(f"could not mark stale: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"pipeline failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        _mark_stale(str(exc))
        # Hard failures must stop CI/Pages deployment.
        sys.exit(1)
