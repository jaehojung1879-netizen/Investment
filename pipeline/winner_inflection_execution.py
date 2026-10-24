"""WID execution over caller-admitted inputs; never opens sources itself.

Existing WID states/folds/learners and the US pilot's selector, self-financing
cost simulation and metrics do the work. Real input IO is permit-gated in CLI.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from bisect import bisect_left
from functools import lru_cache

import numpy as np
import pandas as pd

from . import experiment_workbench as W
from . import finnhub_derive as FD
from . import industry_foundation as IF
from . import prospective_receipt_core as PRC
from . import replay_calendar as RC
from . import us_cash_profitability as CP
from . import us_decision_pilot as P
from . import winner_inflection as I
from . import winner_inflection_exploration as E

BASE = ("financial.operatingMargin", "financial.ocfMargin", "price.momentum252", "risk.logSizeProxy")


@lru_cache(maxsize=8192)
def close_at(day, *, final=True):
    import exchange_calendars as xc
    value = xc.get_calendar("XNYS", start="1990-01-01", end="2035-12-31").session_close(pd.Timestamp(day))
    return (value + pd.Timedelta(hours=1) if final else value).isoformat()


def validate_spec(spec):
    if (spec["market"] != "US" or spec["horizon"] != 126 or spec["pattern"] not in ("A", "B", "C") or
            spec["benchmark"] != "SPY" or spec["maximumPositions"] != 5 or spec["seed"] != 19):
        raise ValueError("UNSUPPORTED_EXECUTION_SPEC")
    if spec["returnBasis"] != "RECONSTRUCTED_AS_TRADED_CASH_REINVEST_EX_CLOSE_V1":
        raise ValueError("EXPLICIT_COMMON_RETURN_BASIS_REQUIRED")
    if spec["cashPolicy"] != "UNREMUNERATED_USD_NOMINAL":
        raise ValueError("EXPLICIT_CASH_POLICY_REQUIRED")
    reference_end = str((pd.Timestamp(spec["signalEnd"]) + pd.Timedelta(days=800)).date())
    needed = RC.sessions(spec["signalEnd"], reference_end, "US")
    if len(needed) <= 127 or spec["sourceWindow"]["priceThrough"] < str(needed[127].date()):
        raise ValueError("SOURCE_WINDOW_CANNOT_COVER_H126_RUNOUT")
    prior = None
    for entry in spec["folds"]:
        fold = W.Fold(**entry)
        if prior and W._utc(fold.evaluation_start) <= W._utc(prior.evaluation_end):
            raise ValueError("EVALUATION_FOLDS_OVERLAP")
        prior = fold
        sessions = RC.sessions(fold.label_deadline[:10], fold.training_cutoff[:10], "US")
        if len(sessions) < 22:
            raise ValueError("AT_LEAST_21_SESSION_EMBARGO_REQUIRED")


def cash_reinvestment_close(raw_close, events):
    """Tiny return-basis adapter, not a new replay/feature engine.

    An old share becomes split shares; ex-date dividends per post-split share
    reinvest at that close: split * (P_t + D_t) / P_(t-1). A missing native quote
    is an explicit barrier. A later observed segment is rebased, never filled;
    all label/feature/daily-replay windows crossing the barrier abstain.
    """
    from . import price_adjustment as PA
    if raw_close.empty:
        return raw_close.copy()
    days = RC.sessions(str(raw_close.index.min().date()), str(raw_close.index.max().date()), "US")
    if not raw_close.index.is_unique or not raw_close.index.isin(days).all():
        raise ValueError("DUPLICATE_OR_OFF_CALENDAR_NATIVE_QUOTES")
    raw = raw_close.reindex(days).astype(float)
    records, seen = [], defaultdict(set)
    for day, dividend, split in events:
        if not PRC.finite(dividend) or not PRC.finite(split) or dividend < 0 or split <= 0:
            raise ValueError("INVALID_DIVIDEND_OR_SPLIT_BASIS")
        stamp = pd.Timestamp(day)
        kinds = ({"DIVIDEND"} if dividend else set()) | ({"SPLIT"} if split != 1 else set())
        # Replay stores a split and a dividend as TWO rows on the same day.
        # That is valid; repeating the same action kind is ambiguous.
        if seen[stamp] & kinds:
            raise ValueError("DUPLICATE_ACTION_DATE_REQUIRES_SOURCE_RECONCILIATION")
        seen[stamp].update(kinds)
        if raw.index.min() <= stamp <= raw.index.max() and stamp not in raw.index:
            raise ValueError("ACTION_ON_NONSESSION_DATE")
        records.append({"date": stamp, PA.DIVIDEND: dividend, PA.SPLIT: split})
    ev = pd.DataFrame(records).set_index("date") if records else None
    dividends, splits = PA._aligned_events(raw.index, ev)
    out = pd.Series(np.nan, index=days, dtype=float)
    for i, price in enumerate(raw):
        if not np.isfinite(price) or price <= 0:
            continue
        if i == 0 or not np.isfinite(out.iloc[i - 1]):
            out.iloc[i] = price
        else:
            out.iloc[i] = out.iloc[i - 1] * splits.iloc[i] * (price + dividends.iloc[i]) / raw.iloc[i - 1]
    return out


def reviewed_filings(records):
    """WID requires BOTH public/acceptance dates; missing evidence never falls back.

    The shared historical helpers retain their own contracts. Reject only this
    filing, preserving the security and every universe denominator.
    """
    accepted, rejected = [], []
    for record in records:
        dates = [CP._day(record.get(k)) for k in ("availableFrom", "acceptedDate")]
        if any(d is None for d in dates):
            rejected.append({"id": record.get("id"), "ticker": record.get("ticker"),
                             "reason": "BOTH_PUBLICATION_AND_ACCEPTANCE_DATES_REQUIRED"})
        else:
            accepted.append(record)
    return accepted, rejected


def observations(data, spec):
    """Full PIT universe first. No endpoint/maturity or target enters features."""
    source = data["source"]
    prices, as_traded = data["prices"], data["asTraded"]
    caches = {t: I.FilingStates(reviewed_filings(records)[0], "US") for t, records in data["filings"].items()}
    calendar_end = str((pd.Timestamp(spec["signalEnd"]) + pd.Timedelta(days=15)).date())
    calendar = RC.sessions(spec["inputStart"], calendar_end, "US")
    grid = calendar.to_series().groupby(calendar.to_period("W")).max()
    out, control_cache = [], {}
    for stamp in grid:
        day = str(stamp.date())
        if day > spec["signalEnd"]:
            continue
        membership = data["membership"].on(day)
        sector = data["industries"].on(day)
        if membership is None:
            continue
        cross, group_map = {}, {}
        for ticker in membership["members"]:
            group_map[ticker] = ((sector or {}).get("rows") or {}).get(ticker, {}).get("sector")
            if spec["pattern"] == "C" and ticker in prices:
                w = prices[ticker].reindex(calendar[calendar <= stamp][-127:])
                if len(w) == 127 and np.isfinite(w).all() and (w > 0).all():
                    cross[ticker] = (w.iloc[63] / w.iloc[0], w.iloc[-1] / w.iloc[63])
        relative = I.industry_relative_change(cross, group_map) if spec["pattern"] == "C" else {}
        for ticker in membership["members"]:
            meta = data["identity"].get(ticker, {})
            sector_row = ((sector or {}).get("rows") or {}).get(ticker, {})
            cik = str(sector_row.get("cik", "")).lstrip("0")
            cache = caches.get(ticker)
            n = bisect_left(cache.days, day) if cache else 0
            if (ticker, n) not in control_cache:
                # Reader-owned records; existing derivation functions are pure.
                # Same strict visible prefix without copying every old filing
                # again on each of the 52 weekly dates.
                visible = cache.records[:n] if cache else []
                index = FD.index_filings(visible)
                key = CP.current_key(index)
                shares, _, share_record = CP.carried_share_count(index, key) if key is not None else (None, None, None)
                control_cache[ticker, n] = ({str(r.get("cik", "")).lstrip("0") for r in visible}, shares,
                                           CP.visible_day(share_record).isoformat() if share_record else day)
            filing_ciks, shares, share_day = control_cache[ticker, n]
            category = meta.get("sp500IdentityCategory")
            identity_ok = bool(cik and filing_ciks == {cik} and str(meta.get("cik", "")).lstrip("0") == cik
                               and category in spec["acceptedIdentityCategories"])
            identity = "US:CIK:" + cik + ":" + ticker if identity_ok else "UNRESOLVED:" + ticker
            state = caches[ticker].at(day) if ticker in caches else {"fields": {}, "levels": {}, "availableFrom": None, "sourceIds": []}
            frame = prices[[ticker]].rename(columns={ticker: "Close"}) if ticker in prices else None
            pf = P.price_features(frame.Close, stamp) if frame is not None else {"momentum252": None}
            raw_quote = as_traded.at[stamp, ticker] if ticker in as_traded and stamp in as_traded.index else None
            splits = [e[0] for e in data["events"].get(ticker, ()) if e[2] and e[2] != 1]
            size, _ = CP.market_cap_proxy(shares, raw_quote, share_day, day, splits)
            fields = {"financial." + k: state["fields"].get(k) for k in I.PATTERNS[spec["pattern"]] if spec["pattern"] != "C"}
            if spec["pattern"] == "C":
                fields["industry.industryRelativeStrengthChange63"] = relative[ticker][0]
            fields.update({"financial." + k: state["levels"].get(k) for k in ("operatingMargin", "ocfMargin")})
            fields.update({"price.momentum252": pf["momentum252"], "risk.logSizeProxy": float(np.log(size)) if size and size > 0 else None})
            if not identity_ok:
                fields = dict.fromkeys(fields)
            group = group_map[ticker]
            group_ok = group in spec["allowedIndustries"] and group not in spec["excludedIndustries"]
            quote = prices.at[stamp, ticker] if ticker in prices and stamp in prices.index else np.nan
            traded = data["volumes"].at[stamp, ticker] if ticker in data["volumes"] and stamp in data["volumes"].index else np.nan
            tradable = bool(np.isfinite(quote) and quote > 0 and np.isfinite(traded) and traded > 0)
            complete = all(v is not None and np.isfinite(v) for v in fields.values())
            reason = ("CONDITIONAL_SCOPE_EXCLUDED:" + str(category) if category not in spec["acceptedIdentityCategories"] else
                      "CIK_IDENTITY_UNRESOLVED" if not identity_ok else "INDUSTRY_UNRESOLVED_OR_EXCLUDED" if not group_ok else
                      "NO_TRADE_AT_SIGNAL" if not tradable else "FEATURE_OR_SIZE_PROXY_UNRESOLVED" if not complete else None)
            at = close_at(day)
            cells = tuple(W.Cell(name, float(v) if v is not None and np.isfinite(v) else None, "ratio", at if v is not None else None,
                                 source, None if v is not None and np.isfinite(v) else "IDENTITY_UNRESOLVED" if not identity_ok else "INCOMPLETE_CHAIN") for name, v in sorted(fields.items()))
            available = (pd.Timestamp(membership["date"]) + pd.Timedelta(days=1)).tz_localize("America/New_York").isoformat()
            out.append(W.Observation(W.Key("US", day, identity), ticker, cik or None, "PROVISIONAL" if identity_ok else "UNRESOLVED",
                at, "PUBLIC_RECONSTRUCTION", source, available, reason is None, reason,
                group if group_ok else None, "RECONSTRUCTED" if group_ok else "UNRESOLVED", cells))
    E.validate_panel(out)
    return tuple(out)


def references(rows, data, spec):
    days = RC.sessions(spec["inputStart"], str((pd.Timestamp(spec["signalEnd"]) + pd.Timedelta(days=800)).date()), "US")
    out = {}
    for row in rows:
        pos = days.searchsorted(row.key.signal_date, side="right")
        entry, maturity = str(days[pos].date()), str(days[pos + spec["horizon"]].date())
        terminal = data.get("terminal", {}).get(row.ticker)
        status = "CONSIDERATION_VERIFIED" if terminal and terminal.get("verified") else "NOT_TERMINATED"
        out[row.key.sample_id] = W.LabelReference(row.key.sample_id, "US", spec["horizon"], close_at(entry, final=False),
            close_at(maturity), close_at(maturity), "VERIFIED", status, "wid:separate-labels/" + row.key.sample_id)
    return out


def outcome(row, reference, data):
    """Only called AFTER permit and, for training, after maturity admission.

    A certified CASH settlement may resolve endpoints; absent daily quotations
    still make a continuous portfolio MDD unresolved. Noncash deals need their
    own verified successor economics and are never ticker-substituted.
    """
    if W._utc(reference.available_at) > W._utc(data["asOf"]):
        return {"status": "UNRESOLVED", "reason": "OUTCOME_NOT_MATURE_OR_PUBLIC", "excess": None}
    entry, end = reference.execution_at[:10], reference.maturity_at[:10]
    days = RC.sessions(entry, end, "US")
    panel = data["prices"].reindex(days)
    if "SPY" not in panel or not np.isfinite(panel.SPY).all() or (panel.SPY <= 0).any():
        return {"status": "UNRESOLVED", "reason": "SPY_PATH_UNRESOLVED", "excess": None}
    if row.ticker not in panel or not np.isfinite(panel[row.ticker].iloc[0]) or panel[row.ticker].iloc[0] <= 0:
        return {"status": "UNRESOLVED", "reason": "ENTRY_PRICE_UNRESOLVED", "excess": None}
    volume = data["volumes"].reindex(days)[row.ticker] if row.ticker in data["volumes"] else pd.Series(np.nan, index=days)
    if not np.isfinite(volume.iloc[0]) or volume.iloc[0] <= 0:
        return {"status": "UNRESOLVED", "reason": "ENTRY_NOT_TRADABLE", "excess": None}
    stock = panel[row.ticker]
    terminal = data.get("terminal", {}).get(row.ticker)
    paid = None
    if terminal and terminal["date"] <= entry:
        return {"status": "UNRESOLVED", "reason": "ENTRY_AFTER_SECURITY_TERMINATION", "excess": None}
    if terminal and entry < terminal["date"] <= end:
        if (terminal.get("kind") != "CASH" or not terminal.get("verified") or not terminal.get("citation") or
                terminal.get("securityIdentity") != row.key.security_identity or terminal.get("currency") != "USD" or
                terminal.get("shareBasis") != "AS_TRADED_LAST_PRE_TERMINAL_SHARE" or
                not terminal["date"] <= terminal.get("settlementDate", "9999") <= end or
                not terminal.get("publicAt") or W._utc(terminal["publicAt"]) > W._utc(reference.available_at)):
            return {"status": "UNRESOLVED", "reason": "TERMINAL_CONSIDERATION_UNRESOLVED", "excess": None}
        prior = data["prices"].loc[data["prices"].index < pd.Timestamp(terminal["date"]), row.ticker].dropna()
        if prior.empty or row.ticker not in data["asTraded"]:
            return {"status": "UNRESOLVED", "reason": "TERMINAL_BASIS_UNRESOLVED", "excess": None}
        last = prior.index[-1]
        known_path, known_volume = stock.loc[:last], volume.loc[:last]
        if (not np.isfinite(known_path).all() or (known_path <= 0).any() or
                not np.isfinite(known_volume).all() or (known_volume <= 0).any() or
                any(str(last.date()) < day <= terminal["date"] and (dividend or split != 1)
                    for day, dividend, split in data["events"].get(row.ticker, ()))):
            return {"status": "UNRESOLVED", "reason": "TERMINAL_SHARE_CHAIN_UNRESOLVED", "excess": None}
        raw = data["asTraded"].at[prior.index[-1], row.ticker]
        cash = terminal.get("cashPerShare")
        if not PRC.finite(cash) or cash < 0 or not np.isfinite(raw) or raw <= 0:
            return {"status": "UNRESOLVED", "reason": "TERMINAL_CASH_OR_SHARE_BASIS_UNRESOLVED", "excess": None}
        paid = float(prior.iloc[-1] * cash / raw)
    if paid is None and (not np.isfinite(stock).all() or (stock <= 0).any() or not np.isfinite(volume).all() or (volume <= 0).any()):
        return {"status": "UNRESOLVED", "reason": "GAP_OR_TERMINAL_PRICE_UNRESOLVED", "excess": None}
    gross = (paid if paid is not None else stock.iloc[-1]) / stock.iloc[0] - 1
    spy = panel.SPY.iloc[-1] / panel.SPY.iloc[0] - 1
    return {"status": "RESOLVED", "reason": None, "gross": float(gross), "spy": float(spy),
            "excess": float(gross - spy), "terminalConsideration": paid is not None}


def label_cohorts(rows, refs, data, *, minimum):
    by_date = defaultdict(list)
    values = {}
    for row in rows:
        if row.investable:
            value = outcome(row, refs[row.key.sample_id], data)
            value["reference"] = asdict(refs[row.key.sample_id])
            values[row.key.sample_id] = value
            if value["status"] == "RESOLVED":
                by_date[row.key.signal_date].append(row.key.sample_id)
    for ids in by_date.values():
        if len(ids) < minimum:
            for sid in ids:
                values[sid].update(status="UNRESOLVED", reason="RESOLVED_COHORT_BELOW_MINIMUM", winner=None, big_loss=None)
            continue
        low, high = np.quantile([values[s]["excess"] for s in ids], [0.1, 0.9])
        for sid in ids:
            excess = values[sid]["excess"]
            values[sid].update(winner=bool(excess >= high and excess > 0), big_loss=bool(excess <= low and excess < 0))
    return values


def cells(row):
    return {c.name: c.value for c in row.cells}


def event(row):
    c = cells(row)
    if "industry.industryRelativeStrengthChange63" in c:
        return bool(c["industry.industryRelativeStrengthChange63"] > 0)
    if "financial.revenueGrowthAcceleration" in c:
        return bool(c["financial.revenueGrowthAcceleration"] > 0 and c["financial.operatingGrowthAcceleration"] > 0)
    return bool(c.get("financial.operatingPositiveCross", 0) > 0 and c.get("financial.ocfMarginChange", 0) > 0)


def probability_metrics(y, p):
    from sklearn.metrics import average_precision_score, brier_score_loss
    if not len(y) or not np.isfinite(p).all():
        return {"status": "UNRESOLVED", "reason": "NO_FINITE_PROBABILITY_SAMPLE"}
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    bins = []
    edges = np.linspace(0, 1, 11)
    for lo, hi in zip(edges[:-1], edges[1:]):
        use = (p >= lo) & ((p < hi) if hi < .999 else (p <= 1))
        if use.any():
            bins.append({"count": int(use.sum()), "predicted": float(p[use].mean()), "observed": float(y[use].mean())})
    return {"status": "MEASURED", "n": len(y), "baseRate": float(y.mean()), "brier": float(brier_score_loss(y, p)),
            "prAuc": float(average_precision_score(y, p)) if len(set(y)) == 2 else None,
            "prAucStatus": "MEASURED" if len(set(y)) == 2 else "UNRESOLVED_SINGLE_CLASS",
            "prAucDefinition": "average precision step integral",
            "reliability": bins, "ece": sum(b["count"] * abs(b["predicted"] - b["observed"]) for b in bins) / len(y)}


def model_predictions(rows, labels, plan, spec, refs):
    by_id = {r.key.sample_id: r for r in rows}
    training = [s for s in plan["training"] if labels.get(s, {}).get("status") == "RESOLVED"]
    evaluate = plan["evaluation"]
    dates = sorted({by_id[s].key.signal_date for s in training})
    if not dates or len(training) < spec["minimumTrainingRows"]:
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_MATURE_TRAINING_LABELS"}
    if (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days < spec["minimumTrainingSpanDays"]:
        return {"status": "BLOCKED", "reason": "MATURE_TRAINING_SPAN_TOO_SHORT"}
    if len({by_id[s].issuer_id for s in training}) < spec["minimumIssuers"]:
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_ISSUER_SUPPORT"}
    cal_start = dates[min(int(len(dates) * .8), len(dates) - 1)]
    calibration = [s for s in training if by_id[s].key.signal_date >= cal_start]
    proper = [s for s in training if by_id[s].key.signal_date < cal_start and refs[s].available_at[:10] < cal_start
              and refs[s].maturity_at[:10] < cal_start]
    if len(proper) < spec["minimumTrainingRows"] or not evaluate:
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_PURGED_PROPER_TRAINING"}
    proper_dates = sorted({by_id[s].key.signal_date for s in proper})
    if (len({by_id[s].issuer_id for s in proper}) < spec["minimumIssuers"] or
            (pd.Timestamp(proper_dates[-1]) - pd.Timestamp(proper_dates[0])).days < spec["minimumTrainingSpanDays"]):
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_PURGED_ISSUER_OR_TIME_SUPPORT"}
    if any(min(sum(labels[s][k] for s in proper), sum(not labels[s][k] for s in proper)) < spec["minimumClassRows"]
           for k in ("winner", "big_loss")):
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_BINARY_CLASS_SUPPORT"}
    pattern = tuple(c.name for c in rows[0].cells if c.name not in BASE)
    variants, fits = {}, 0
    for name, columns in (("levels_momentum", BASE), ("pattern_augmented", BASE + pattern)):
        matrix = lambda ids: np.array([[cells(by_id[s])[c] for c in columns] for s in ids], dtype=float)
        result = E.fit_prepared(matrix(proper), matrix(calibration + evaluate), list(columns), [labels[s]["excess"] for s in proper],
            {k: [labels[s][k] for s in proper] for k in ("winner", "big_loss")}, seed=spec["seed"], elastic_net=False,
            class_minimum=spec["minimumClassRows"])
        if result["status"] == "BLOCKED" or not all("logistic_" + k in result.get("scores", {}) for k in ("winner", "big_loss")):
            return {"status": "BLOCKED", "reason": "INSUFFICIENT_BINARY_CLASS_SUPPORT"}
        fits += result["modelFits"]
        score = result["scores"]
        prediction = {s: {k: float(v[len(calibration) + i]) for k, v in score.items()} for i, s in enumerate(evaluate)}
        calibration_status = {}
        for kind in ("winner", "big_loss"):
            from sklearn.linear_model import LogisticRegression
            y = [int(labels[s][kind]) for s in calibration]
            enough = len(y) >= spec["minimumCalibrationRows"] and min(sum(y), len(y) - sum(y)) >= spec["minimumCalibrationClassRows"]
            if enough:
                raw = np.clip(score["logistic_" + kind], 1e-6, 1 - 1e-6)
                logit = np.log(raw / (1 - raw)).reshape(-1, 1)
                calibrator = LogisticRegression(C=1e6, random_state=spec["seed"], max_iter=1000).fit(logit[:len(calibration)], y)
                calibrated = calibrator.predict_proba(logit[len(calibration):])[:, 1]
                for s, p in zip(evaluate, calibrated):
                    prediction[s]["calibrated_" + kind] = float(p)
                fits += 1
            calibration_status[kind] = "TRAIN_ONLY_TEMPORAL_PLATT" if enough else "UNRESOLVED_CALIBRATION_SUPPORT"
        variants[name] = {"predictions": prediction, "calibration": calibration_status}
    rule = {}
    for state in (False, True):
        group = [s for s in proper if event(by_id[s]) is state]
        rule[state] = {k: float(np.mean([labels[s][k] for s in group])) for k in ("winner", "big_loss")} if len(group) >= spec["minimumEventRows"] else None
    variants["event_rule"] = {"predictions": {s: {"logistic_" + k: v for k, v in rule[event(by_id[s])].items()}
                                               for s in evaluate if rule[event(by_id[s])] is not None}, "calibration": "TRAIN_EMPIRICAL_EVENT_RATES"}
    return {"status": "FITTED", "variants": variants, "modelFits": fits, "properTraining": proper,
            "calibrationSamples": calibration, "evaluation": evaluate, "planSha256": plan["sha256"],
            "properSamplesSha256": IF.digest(sorted(proper)), "calibrationSamplesSha256": IF.digest(sorted(calibration))}


def predictive_report(rows, labels, models):
    by_id = {r.key.sample_id: r for r in rows}
    out = {}
    common = [s for s in models["evaluation"] if labels.get(s, {}).get("status") == "RESOLVED" and
              all(s in v["predictions"] for v in models["variants"].values())]
    for name, variant in models["variants"].items():
        predicted = variant["predictions"]
        ids = common
        detail = {"sampleIdsSha256": IF.digest(ids), "n": len(ids), "eligibleEvaluationRows": len(models["evaluation"]),
                  "predictionRows": len(predicted), "calibration": variant["calibration"]}
        for kind in ("winner", "big_loss"):
            for prefix, key in (("raw", "logistic_" + kind), ("calibrated", "calibrated_" + kind)):
                detail[prefix + "_" + kind] = probability_metrics([labels[s][kind] for s in ids], [predicted[s].get(key, np.nan) for s in ids])
        for model in ("ridge",):
            detail[model] = {"status": "MEASURED", "mae": float(np.mean([abs(predicted[s][model] - labels[s]["excess"]) for s in ids]))} if ids and all(model in predicted[s] for s in ids) else {"status": "UNRESOLVED", "reason": "NOT_A_RETURN_MODEL"}
        out[name] = detail
    groups = {}
    for state in (False, True):
        all_ids = [s for s in models["evaluation"] if event(by_id[s]) is state]
        ids = [s for s in all_ids if labels.get(s, {}).get("status") == "RESOLVED"]
        n, known = len(all_ids), len(ids)
        groups[str(state)] = {"eligible": n, "resolved": known, "unresolved": n - known,
            "meanExcess": float(np.mean([labels[s]["excess"] for s in ids])) if ids else None,
            "medianExcess": float(np.median([labels[s]["excess"] for s in ids])) if ids else None,
            **{k + "Rate": float(np.mean([labels[s][k] for s in ids])) if ids else None for k in ("winner", "big_loss")},
            **{k + "RateAllEligibleBounds": [sum(labels[s][k] for s in ids) / n, (sum(labels[s][k] for s in ids) + n - known) / n] if n else None
               for k in ("winner", "big_loss")},
            "returnSensitivity": "UNRESOLVED_UNBOUNDED_MISSING_RETURN_SUPPORT" if n > known else "NO_OUTCOME_DROPOUT_IN_THIS_CONDITIONAL_COHORT"}
    increments = {}
    base, augmented = out.get("levels_momentum", {}), out.get("pattern_augmented", {})
    for key in ("raw_winner", "raw_big_loss", "calibrated_winner", "calibrated_big_loss"):
        a, b = base.get(key, {}), augmented.get(key, {})
        ready = a.get("status") == b.get("status") == "MEASURED"
        increments[key] = {"status": "MEASURED" if ready else "UNRESOLVED", "brierAugmentedMinusBaseline": b["brier"] - a["brier"] if ready else None,
            "prAucAugmentedMinusBaseline": b["prAuc"] - a["prAuc"] if ready and a["prAuc"] is not None and b["prAuc"] is not None else None}
    return {"models": out, "patternGroups": groups, "incrementalOnCommonSample": increments,
            "top5ForecastDiagnostics": top5_diagnostics(rows, labels, models)}


def top5_diagnostics(rows, labels, models):
    """Weekly forecast hit rates, explicitly not a compounded portfolio path."""
    by_id = {r.key.sample_id: r for r in rows}
    out = {}
    for variant, detail in models["variants"].items():
        for kind in (("event",) if variant == "event_rule" else ("logistic", "ridge")):
            selected = []
            for day in sorted({by_id[s].key.signal_date for s in models["evaluation"]}):
                candidates = []
                for sid in models["evaluation"]:
                    if by_id[sid].key.signal_date != day or sid not in detail["predictions"]:
                        continue
                    if variant == "event_rule" and not event(by_id[sid]):
                        continue
                    p = detail["predictions"][sid]
                    score = p["ridge"] if kind == "ridge" else p["logistic_winner"] - p["logistic_big_loss"]
                    candidates.append((sid, score))
                candidates.sort(key=lambda pair: (-pair[1], by_id[pair[0]].ticker))
                selected.extend(s for s, _ in candidates[:5])
            measured = [s for s in selected if labels.get(s, {}).get("status") == "RESOLVED"]
            loss = sorted((s for s in measured if labels[s]["big_loss"]), key=lambda s: labels[s]["excess"])
            out[variant + ":" + kind] = {"selected": len(selected), "resolved": len(measured), "unresolved": len(selected) - len(measured),
                "winnerHitRate": float(np.mean([labels[s]["winner"] for s in measured])) if measured else None,
                "bigLossRate": float(np.mean([labels[s]["big_loss"] for s in measured])) if measured else None,
                "largeLossCases": [{"sampleId": s, "ticker": by_id[s].ticker, "signalDate": by_id[s].key.signal_date,
                                    "excess": labels[s]["excess"]} for s in loss[:10]],
                "overlappingH126LabelsAreNotIndependent": True}
    return out


def matched_controls(rows, labels, ids):
    by_date = defaultdict(list)
    for row in rows:
        if row.key.sample_id in ids:
            by_date[row.key.signal_date].append(row)
    differences, unmatched, candidates_count, resolved_count = [], 0, 0, 0
    for group in by_date.values():
        ordered = sorted(group, key=lambda r: (cells(r)["risk.logSizeProxy"], r.key.security_identity))
        buckets = {r.key.sample_id: min(2, i * 3 // len(ordered)) for i, r in enumerate(ordered)}
        for row in group:
            if not event(row):
                continue
            peers = [r.key.sample_id for r in group if not event(r) and r.industry_id == row.industry_id
                     and buckets[r.key.sample_id] == buckets[row.key.sample_id]]
            resolved = [s for s in peers if labels.get(s, {}).get("status") == "RESOLVED"]
            candidates_count += len(peers)
            resolved_count += len(resolved)
            own = labels.get(row.key.sample_id, {})
            if not resolved or own.get("status") != "RESOLVED":
                unmatched += 1
            else:
                differences.append(own["excess"] - np.mean([labels[s]["excess"] for s in resolved]))
    return {"status": "MEASURED" if differences else "UNRESOLVED", "matchedCases": len(differences), "unmatchedCases": unmatched,
            "candidateControlPairs": candidates_count, "resolvedControlPairs": resolved_count,
            "meanExcessVsMatchedControl": float(np.mean(differences)) if differences else None,
            "matching": "same signal/industry/size tercile; outcome resolution never selects the initial controls"}


def cohort_endpoint(target, ids_by_ticker, rows_by_id, refs, data):
    """H126 endpoint settlement using the existing self-financing fee solver.

    This is not a replacement daily replay. It can resolve a legal cash payoff
    (including zero) while daily MDD remains unknown across missing marks.
    """
    values = {}
    for ticker in target:
        sid = ids_by_ticker[ticker]
        values[ticker] = outcome(rows_by_id[sid], refs[sid], data)
    if any(v["status"] != "RESOLVED" for v in values.values()):
        return {"status": "UNRESOLVED", "reason": "COHORT_PAYOFF_UNRESOLVED"}
    policy = P.REALISTIC_COSTS["US"]
    buy = (policy["commissionBps"] + policy["spreadBps"] / 2) / 1e4
    sell = buy + policy["sellTaxBps"] / 1e4
    entry_cost, entry_turn = P.rebalance({}, target, buy, sell)
    end_values = {t: target[t] * (1 + values[t]["gross"]) for t in target}
    growth = 1 - sum(target.values()) + sum(end_values.values())
    exit_weights = {t: value / growth for t, value in end_values.items() if not values[t]["terminalConsideration"]} if growth > 0 else {}
    exit_cost, exit_turn = P.rebalance(exit_weights, {}, buy, sell)
    return {"status": "MEASURED_ENDPOINT", "grossReturn": float(growth - 1),
            "netReturn": float((1 - entry_cost) * growth * (1 - exit_cost) - 1),
            "twoWayTurnover": float(entry_turn + exit_turn),
            "costInitialCapital": float(entry_cost + (1 - entry_cost) * growth * exit_cost),
            "cashSettlementBrokerFeeAssumption": "NO_DISCRETIONARY_TRADE_ON_CERTIFIED_CASH_REDEMPTION",
            "dailyMdd": -1.0 if growth == 0 else None,
            "dailyMddStatus": "DETERMINED_BY_TOTAL_LOSS_ENDPOINT" if growth == 0 else "USE_DAILY_REPLAY_WHEN_MARKS_COMPLETE"}


def economics(rows, models, prices, refs, *, data=None):
    """Sequential H126 books, next-session entry, then next completed week.

    Weekly overlapping forecast labels are never compounded as a NAV path.
    Existing pilot simulation handles drift, fees and turnover on daily quotes.
    """
    by_id = {r.key.sample_id: r for r in rows}
    dates = sorted({by_id[s].key.signal_date for s in models["evaluation"]})
    anchors, last_end = [], None
    for day in dates:
        if last_end is None or day >= last_end:
            ids = [s for s in models["evaluation"] if by_id[s].key.signal_date == day]
            ref = refs[ids[0]]
            anchors.append((ids, ref.execution_at[:10], ref.maturity_at[:10]))
            last_end = ref.maturity_at[:10]
    if not anchors:
        return {"status": "UNRESOLVED", "reason": "NO_ECONOMIC_ANCHORS"}
    days = RC.sessions(dates[0], anchors[-1][2], "US")
    panel = prices.reindex(days).copy()
    if data is not None:
        for ticker in panel:
            if ticker != "SPY":
                volume = data["volumes"].reindex(days)[ticker] if ticker in data["volumes"] else pd.Series(np.nan, index=days)
                panel[ticker] = panel[ticker].where(volume > 0)
    result = {}
    strategies = [(v, model) for v in models["variants"] for model in (("event",) if v == "event_rule" else ("logistic", "ridge"))]
    strategies.extend((("SPY", "matched_h126"), ("SPY", "buy_hold")))
    for variant, model in strategies:
        orders, unknown, endpoints = {}, None, []
        for ids, entry, end in anchors:
            ranks = []
            if variant == "SPY":
                target = {"SPY": 1.0}
            else:
                predicted = models["variants"][variant]["predictions"]
                for sid in ids:
                    p = predicted.get(sid)
                    if p is None:
                        continue
                    if variant == "event_rule" and not event(by_id[sid]):
                        continue
                    score = p.get("ridge") if model == "ridge" else p.get("logistic_winner", 0) - p.get("logistic_big_loss", 0)
                    if score is not None:
                        ranks.append((sid, score))
                if not ranks and variant != "event_rule":
                    unknown = "NO_MODEL_PREDICTION_AT_ANCHOR"
                    break
                # Reuse existing selector; one security identity per row,
                # ties stable and no new weighting/backtest framework.
                candidates = [{"ticker": by_id[s].ticker, "region": "US", "sector": by_id[s].industry_id} for s, _ in sorted(ranks)]
                score_by_ticker = {by_id[s].ticker: v for s, v in ranks}
                ranked = [{**r, "score": score_by_ticker[r["ticker"]], "eligible": True, "exclusionCodes": []} for r in candidates]
                selected, _ = P.KP.select_portfolio_by_scores(candidates, ranked,
                    {"maxNames": 5, "selection": {"targetNames": 5, "minNames": 0, "maxNamesPerSector": 5, "maxNamesPerRegion": 5}}, method="WID_H126_DIAGNOSTIC")
                target = {r["ticker"]: 1 / len(selected) for r in selected} if selected else {}
                if data is not None:
                    endpoints.append(cohort_endpoint(target, {by_id[s].ticker: s for s in ids}, by_id, refs, data))
            orders[pd.Timestamp(entry)], orders[pd.Timestamp(end)] = target, {}
        if variant == "SPY" and model == "buy_hold":
            orders = {pd.Timestamp(anchors[0][1]): {"SPY": 1.0}, pd.Timestamp(anchors[-1][2]): {}}
        endpoint_complete = bool(endpoints) and all(v["status"] == "MEASURED_ENDPOINT" for v in endpoints)
        endpoint_summary = {"status": "MEASURED" if endpoint_complete else "UNRESOLVED",
                            "cohorts": endpoints, "cumulativeNetReturn": float(np.prod([1 + v["netReturn"] for v in endpoints]) - 1) if endpoint_complete else None}
        if unknown:
            result[variant + ":" + model] = {"status": "UNRESOLVED", "reason": unknown, "endpointEconomics": endpoint_summary}
            continue
        try:
            gross, net = P.simulate(panel, orders, costed=False), P.simulate(panel, orders, costed=True)
            gm, nm = P.metrics(gross), P.metrics(net)
            result[variant + ":" + model] = {"status": "MEASURED", "gross": gm, "net": nm,
                "grossReturn": float(gross.nav.iloc[-1] / gross.nav.iloc[0] - 1), "netReturn": float(net.nav.iloc[-1] / net.nav.iloc[0] - 1),
                "returnVsSPY": None, "maximumPositions": 5, "cohorts": len(anchors)}
        except ValueError as error:
            result[variant + ":" + model] = {"status": "UNRESOLVED", "reason": str(error), "dailyMdd": None}
        result[variant + ":" + model]["endpointEconomics"] = endpoint_summary
    benchmark = result.get("SPY:buy_hold", {})
    matched = result.get("SPY:matched_h126", {})
    for name, detail in result.items():
        if detail["status"] == benchmark.get("status") == "MEASURED":
            detail["returnVsSPY"] = detail["netReturn"] - benchmark["netReturn"]
        if detail["status"] == matched.get("status") == "MEASURED":
            detail["returnVsMatchedH126SPY"] = detail["netReturn"] - matched["netReturn"]
        endpoint = detail["endpointEconomics"]
        if endpoint["status"] == "MEASURED" and benchmark.get("status") == "MEASURED":
            endpoint["returnVsSPY"] = endpoint["cumulativeNetReturn"] - benchmark["netReturn"]
    return {"status": "COMPUTED_DESCRIPTIVE", "holding": "nonoverlapping H126; cash gaps to next complete weekly signal; final 2020-origin cohort runs into 2021",
            "cashPolicy": "UNREMUNERATED_USD_NOMINAL", "strategies": result}


def execute(data, spec, *, checkpoint=None):
    """Pure orchestration. Real callers MUST authorize before constructing data."""
    validate_spec(spec)
    rows = observations(data, spec)
    refs = references(rows, data, spec)
    universe = [{"sampleId": r.key.sample_id, "date": r.key.signal_date, "securityIdentity": r.key.security_identity,
                 "ticker": r.ticker, "issuerId": r.issuer_id, "identityStatus": r.identity_status,
                 "industryId": r.industry_id, "industryStatus": r.industry_status,
                 "signalAt": r.signal_at, "universeAvailableAt": r.universe_available_at,
                 "provenance": asdict(r.universe_source), "eligible": r.investable, "reason": r.eligibility_reason} for r in rows]
    features = [{"sampleId": r.key.sample_id, "sourceSha256": r.universe_source.sha256,
                 "availableAt": {c.name: c.available_at for c in r.cells}, "features": cells(r)} for r in rows]
    if checkpoint:
        checkpoint("universe", "records", universe)
        checkpoint("features", "records", features)
    records, reports, all_predictions, fits = {}, [], {}, 0
    for fold_index, fold_data in enumerate(spec["folds"]):
        fold = W.Fold(**fold_data)
        plan = E.training_plan(rows, list(refs.values()), fold, identity_statuses=("VERIFIED_SECURITY", "PROVISIONAL"))
        if checkpoint:
            checkpoint("labels", f"fold-{fold_index}-admission", plan)
        training_ids, evaluation_ids = set(plan["training"]), set(plan["evaluation"])
        train_rows = [r for r in rows if r.key.sample_id in training_ids]
        training = label_cohorts(train_rows, refs, data, minimum=spec["minimumCohort"])
        if checkpoint:
            checkpoint("labels", f"fold-{fold_index}-training", training)
        models = model_predictions(rows, training, plan, spec, refs)
        if models["status"] == "BLOCKED":
            reports.append({"status": "BLOCKED", "reason": models["reason"], "planSha256": plan["sha256"]})
            continue
        # Predictions are frozen before evaluation outcomes are even derived.
        frozen = IF.digest(models)
        if checkpoint:
            checkpoint("decisions", f"fold-{fold_index}", models)
        evaluation_rows = [r for r in rows if r.key.sample_id in evaluation_ids]
        labels = label_cohorts(evaluation_rows, refs, data, minimum=spec["minimumCohort"])
        if checkpoint:
            checkpoint("labels", f"fold-{fold_index}-evaluation", labels)
        assert IF.digest(models) == frozen
        reports.append({"status": "EXPLORATORY_DESCRIPTIVE", "fold": fold_data, "forecastSha256": frozen,
            "training": {k: models[k] for k in ("properSamplesSha256", "calibrationSamplesSha256", "planSha256")},
            "predictive": predictive_report(rows, labels, models), "controls": matched_controls(rows, labels, set(plan["evaluation"])),
            "economic": economics(rows, models, data["prices"], refs, data=data),
            "trainingOutcomeReasons": dict(Counter(v.get("reason") or "RESOLVED" for v in training.values())),
            "foldExclusions": dict(Counter(plan["excluded"].values())),
            "outcomeReasons": dict(Counter(v.get("reason") or "RESOLVED" for v in labels.values()))})
        fits += models["modelFits"]
        records.update(training)
        records.update(labels)
        all_predictions[frozen] = models
    output = {"universe": universe, "features": features, "labels": records, "decisions": all_predictions,
            "evaluation": {"status": "EXPLORATION_COMPLETED" if any(r["status"] != "BLOCKED" for r in reports) else "BLOCKED",
                "evidenceClass": "SYNTHETIC_FIXTURE" if data["source"].vintage == "SYNTHETIC_FIXTURE" else "HISTORICAL_EXPLORATION",
                "studyId": spec["id"], "seed": spec["seed"], "returnBasis": spec["returnBasis"],
                "returnInterpretation": spec["returnInterpretation"],
                "fullUniverseReturnEffect": {"status": "UNRESOLVED", "reason": "conditional own-panel scope and excluded identities cannot identify the full market effect"},
                "inputBasisProblems": data.get("basisProblems", {}),
                "withheldFilingMetadata": [r for records in data["filings"].values() for r in reviewed_filings(records)[1]],
                "scope": "SURVIVOR_CONDITIONED_PUBLIC_RECONSTRUCTION", "folds": reports, "modelFits": fits,
                "universeReasons": dict(Counter(r.eligibility_reason or "ELIGIBLE" for r in rows)), "universeSha256": E.validate_panel(rows),
                "unbiasedFullUniverseEvidence": False, "independentOosEvidence": False, "productionPromotion": False}}
    if checkpoint:
        checkpoint("evaluation", "records", output["evaluation"])
    return output


def synthetic_fixture(spec):
    """Invented issuers, filings and paths; no Git, network or source readers."""
    from copy import deepcopy
    from .regional_alpha_features import MembershipSnapshots
    spec = deepcopy(spec)
    spec.update(inputStart="2015-01-01", minimumCohort=12, minimumTrainingRows=50, minimumTrainingSpanDays=365,
                minimumIssuers=20, minimumClassRows=5, minimumCalibrationRows=50, minimumCalibrationClassRows=3, minimumEventRows=3)
    rng = np.random.default_rng(spec["seed"])
    days = RC.sessions("2012-01-01", "2021-08-31", "US")
    tickers = ["SYN" + str(i).zfill(2) for i in range(36)]
    prices = pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(.0002, .015, len(days)))) for t in [*tickers, "SPY"]}, index=days)
    filings, identity, industries = {}, {}, {}
    for n, ticker in enumerate(tickers):
        cik = str(7000000 + n)
        identity[ticker] = {"sp500IdentityCategory": "CURRENT_MEMBER_OWN_PANEL", "cik": cik}
        industries[ticker] = {"cik": cik, "sector": "Industrials" if n % 2 else "Information Technology"}
        records = []
        for year in range(2012, 2021):
            revenue, operating, ocf = 0., 0., 0.
            for q, stage in enumerate(I.STAGES["US"]):
                revenue += 100 * (1 + .04 * (year - 2012))
                operating += (20 if (year * 4 + q + n) % 8 >= 4 else -10)
                ocf += (25 if (year * 4 + q + n) % 8 >= 3 else -5)
                end = (pd.Timestamp(year=year, month=(q + 1) * 3, day=1) + pd.offsets.MonthEnd(0)).date().isoformat()
                public = (pd.Timestamp(end) + pd.Timedelta(days=30)).date().isoformat()
                records.append({"id": f"SYN:{ticker}:{year}:{stage}", "ticker": ticker, "cik": cik, "fiscalYear": year,
                    "periodEnd": end, "availableFrom": public, "acceptedDate": public + " 17:00:00", "periodDays": (90, 181, 273, 365)[q],
                    "form": "10-K" if stage == "FY" else "10-Q", "statements": {"bs": [], "ic": [
                        {"concept": "Revenues", "unit": "usd", "value": revenue},
                        {"concept": "OperatingIncomeLoss", "unit": "usd", "value": operating},
                        {"concept": "WeightedAverageNumberOfDilutedSharesOutstanding", "unit": "shares", "value": 1e6}],
                        "cf": [{"concept": "NetCashProvidedByUsedInOperatingActivities", "unit": "usd", "value": ocf}]}})
        filings[ticker] = records
    return {"source": W.Source("synthetic:invented-execution-inputs", "a" * 64, "SYNTHETIC_FIXTURE", None, "NOT_RETAINED"), "asOf": "2026-10-17T00:00:00Z",
            "prices": prices, "volumes": prices * 0 + 1e6, "asTraded": prices.copy(), "events": {}, "filings": filings,
            "identity": identity, "membership": MembershipSnapshots([{"date": "2012-12-31", "members": tickers}]),
            "industries": MembershipSnapshots([{"date": "2012-12-31", "rows": industries}]), "terminal": {}}, spec
