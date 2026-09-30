"""One-shot DEVELOPMENT harness. All historical outcome paths require a permit.

verify and gates-only never call a target, fit or portfolio evaluator. Inputs are
allowlisted raw sources; no historical signal/outcome ledger is a source. A later
committed authorization pins this seal, the full closure and an exact snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import historical_store as HS
from . import replay_inputs as RI
from . import replay_calendar as RC
from . import kr_repaired_accounting_snapshot as K
from . import kr_market_value as MV
from . import kr_value_quality_catalyst as F
from . import kr_model_overlay_portfolio as M
from . import kr_market_risk_overlay as O
from . import kr_concentrated_portfolio as P
from .alpha_opportunity_spec import digest, file_hash
from .alpha_opportunity_v3_spec import import_closure
from .regional_alpha_features import MembershipSnapshots

ROOT = Path(__file__).resolve().parents[1]
STUDY = "kr-model-overlay-portfolio-v1"
SPEC_PATH = "research_specs/" + STUDY + ".json"
AUTH_PATH = "research_specs/" + STUDY + "-execution-authorization.json"
RESULT_PATH = "docs/results/" + STUDY + "-result.json"


@dataclass
class Counters:
    targetCalls: int = 0
    labelCalls: int = 0
    fitCalls: int = 0
    predictionCalls: int = 0
    modelOutcomeCalls: int = 0
    portfolioOutcomeCalls: int = 0

    def zero(self):
        return all(v == 0 for v in asdict(self).values())


def load_spec(root=ROOT):
    root = Path(root)
    path = root / SPEC_PATH
    spec = json.loads(path.read_text())
    sha = path.with_suffix(".sha256").read_text().strip()
    if digest(spec) != sha or spec["studyId"] != STUDY:
        raise ValueError("SPEC_IDENTITY_CHANGED")
    expected = sorted(set(import_closure(spec["entryPoints"], root)) | set(spec["sealedDataInputs"]))
    if expected != sorted(spec["dependencyHashes"]):
        raise ValueError("IMPORT_CLOSURE_CHANGED")
    for rel, wanted in spec["dependencyHashes"].items():
        if file_hash(root / rel) != wanted:
            raise ValueError("HARNESS_OR_DEPENDENCY_CHANGED: " + rel)
    diagnostic = root / spec["diagnostics"]["path"]
    if digest(json.loads(diagnostic.read_text())) != spec["diagnostics"]["sha256"]:
        raise ValueError("DIAGNOSTIC_SPEC_CHANGED")
    for rel, wanted in spec["priorIdentity"].items():
        # Identity verification only, no parsing prior outcomes or diagnostics.
        if file_hash(root / rel) != wanted:
            raise ValueError("V5_PRIOR_CHANGED: " + rel)
    return spec, sha


def atomic_write(path, document, *, immutable=False):
    """fsync + atomic exclusive hard-link publication for one-shot immutable records."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode() + b"\n"
    temp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    try:
        with temp.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            os.link(temp, path)
        else:
            os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp.exists():
            temp.unlink()
    return hashlib.sha256(raw).hexdigest()


def source_files(input_root):
    """Only the paths this study reads; no generic recursive ledger discovery."""
    base = Path(input_root)
    paths = set()
    for pattern in ("ledger/universe/kr/krx-universe-*.jsonl.gz", "accounting/dart-*.jsonl.gz", "market/????-??-??.json"):
        paths.update(base.glob(pattern))
    manifest = base / "ledger/historical/replay-v16/inputs.json"
    if manifest.exists():
        paths.add(manifest)
        document = json.loads(manifest.read_text())
        for name, refs in document["components"].items():
            if name.startswith(("price/", "benchmark/")):
                paths.update(base / "ledger/replay-inputs/objects" / (ref + ".json.gz") for ref in refs)
    return sorted(paths)


def input_identity(input_root):
    root = Path(input_root)
    hashes = {str(p.relative_to(root)): file_hash(p) for p in source_files(root)}
    return {"files": hashes, "sha256": digest(hashes)}


def load_sources(input_root, spec):
    root = Path(input_root)
    market = MV.MarketValueStore.load(root / "market")
    # Verify accounting bytes AND decoded records against the accepted snapshot.
    files = K.shard_files(root / "accounting")
    blobs = {p.name: K.git_blob_sha1(p.read_bytes()) for p in files}
    pin = spec["inputs"]["accounting"]
    if blobs != pin["gitBlobSha1"]:
        raise ValueError("ACCOUNTING_SNAPSHOT_MISSING_OR_CHANGED")
    shards = {p.name: K.read_shard(p) for p in files}
    if K.content_sha256(shards) != pin["contentSha256"]:
        raise ValueError("ACCOUNTING_CONTENT_CHANGED")
    accounting = {}
    for rows in shards.values():
        for row in rows:
            accounting.setdefault(row["ticker"], []).append(row)
    grouped = {}
    for rel, sha in spec["inputs"]["universeBlobs"].items():
        path = root / rel
        if not path.is_file() or K.git_blob_sha1(path.read_bytes()) != sha:
            raise ValueError("PIT_UNIVERSE_MISSING_OR_CHANGED")
        for row in HS.read_jsonl(path):
            grouped.setdefault(row["date"], []).append(row)
    memberships = MembershipSnapshots([
        {"date": date, "members": sorted(r["ticker"] for r in sorted(rows, key=lambda r: (r["rank"], r["ticker"]))[:120])}
        for date, rows in sorted(grouped.items())])
    manifest_path = root / "ledger/historical/replay-v16/inputs.json"
    if not manifest_path.is_file():
        raise ValueError("REPLAY_MANIFEST_MISSING")
    manifest = json.loads(manifest_path.read_text())
    if (RI.digest({k: v for k, v in manifest.items() if k != "sha256"}) != manifest.get("sha256")
            or manifest.get("sha256") != spec["inputs"]["replayManifestSha256"]):
        raise ValueError("REPLAY_MANIFEST_CHANGED")
    store = RI.InputStore(root / "ledger", "replay-v16", manifest["dataVersion"])
    prices = {}
    for component in sorted(manifest["components"]):
        if not component.startswith(("price/", "benchmark/")):
            continue
        for row in store.load_component(component, manifest):
            ticker = row.get("ticker")
            if ticker and ticker.endswith(".KS"):
                prices.setdefault(ticker, []).append({k: v for k, v in row.items() if k != "ticker"})
    unique = {}
    for ticker, rows in prices.items():
        by_date = {}
        for row in rows:
            if row["date"] in by_date and by_date[row["date"]] != row:
                raise ValueError("CONFLICTING_REPLAY_PRICE_RECORD")
            by_date[row["date"]] = row
        unique[ticker] = RI.rows_frame(list(by_date.values()))
    prices = unique
    return accounting, memberships, market, prices


def prepare(input_root, spec):
    accounting, memberships, market, prices = load_sources(input_root, spec)
    benchmark = prices.get(spec["benchmark"])
    rows, overlay = [], {}
    schedule = M.weekly_dates(spec["walkForward"]["featureStart"], spec["developmentCutoff"])
    for date in schedule:
        membership = memberships.on(date)
        if membership is None:
            raise ValueError("PIT_MEMBERSHIP_MISSING: " + date)
        overlay[date] = O.state_at(benchmark, date)
        for ticker in membership["members"]:
            rows.append(F.feature_at(ticker, date, accounting.get(ticker, []), market, prices.get(ticker), benchmark))
    return {"features": pd.DataFrame(rows), "overlay": overlay, "prices": prices, "market": market, "accounting": accounting,
            "schedule": schedule}


def pre_label_gates(bundle, spec, counters):
    if not counters.zero():
        raise ValueError("GATES_ENTERED_AFTER_OUTCOME_ACCESS")
    frame = bundle["features"]
    reasons, coverage = [], {}
    if frame.empty:
        return {"status": "DATA_INSUFFICIENT", "reasons": ["NO_PIT_NAME_DATES"], "coverage": {}}
    if frame.duplicated(["date", "ticker"]).any():
        raise ValueError("DUPLICATE_PIT_NAME_DATE")
    if any(prov.get("availableFrom", "") >= date for date, prov in zip(frame.date, frame.accountingProvenance)):
        raise ValueError("ACCOUNTING_PUBLICATION_NOT_STRICTLY_PRIOR")
    if set(frame.date) != set(bundle["schedule"]):
        reasons.append("MISSING_SCHEDULED_SIGNAL_DATE")
    gate_rows = frame.loc[frame.date >= spec["gates"]["firstCoverageDate"]]
    for year, group in gate_rows.groupby(gate_rows.date.str[:4]):
        measured = {}
        for family, names in F.FAMILIES.items():
            for name in names:
                rate = float(pd.to_numeric(group[name], errors="coerce").replace([np.inf, -np.inf], np.nan).notna().mean())
                measured[name] = rate
                floor = spec["gates"]["featureOverrides"].get(name, spec["gates"]["featureFloors"][family])
                if rate < floor:
                    reasons.append("FEATURE_COVERAGE:" + year + ":" + name)
        for name in ("marketValuePresent", "tradable"):
            measured[name] = float(group[name].mean())
            if measured[name] < spec["gates"]["marketFloor"]:
                reasons.append("MARKET_OR_TRADABILITY_COVERAGE:" + year + ":" + name)
        measured["portfolioLiquidity"] = float(group.apply(lambda r: P.eligible(r, spec["portfolio"]), axis=1).mean())
        if measured["portfolioLiquidity"] < spec["gates"]["liquidityFloor"]:
            reasons.append("LIQUIDITY_COVERAGE:" + year)
        coverage[year] = {"denominator": len(group), "rates": measured}
    if not coverage:
        reasons.append("NO_COVERAGE_YEARS")
    if any(state["status"] != "READY" for date, state in bundle["overlay"].items()
           if date >= spec["gates"]["firstCoverageDate"]):
        reasons.append("OVERLAY_HISTORY_MISSING")
    # Calendar-only upper bounds; no label eligibility or endpoint price lookup.
    days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    depth = {}
    training_depth = {}
    for horizon in spec["horizons"]:
        matured = [d for d in bundle["schedule"] if str(days[days.searchsorted(pd.Timestamp(d), side="right") + horizon].date()) <= spec["developmentCutoff"]]
        depth[str(horizon)] = len(matured)
        if len(matured) < spec["gates"]["minimumMaturedSignalDates"]:
            reasons.append("CALENDAR_MATURITY_DEPTH:" + str(horizon))
        annual = {}
        for year in sorted({pd.Timestamp(d).year for d in bundle["schedule"]}):
            cutoff = min(d for d in bundle["schedule"] if pd.Timestamp(d).year == year)
            if pd.Timestamp(cutoff) < pd.Timestamp(spec["walkForward"]["featureStart"]) + pd.DateOffset(months=spec["walkForward"]["minimumHistoryMonths"]):
                continue
            annual[str(year)] = sum(str(days[days.searchsorted(pd.Timestamp(d), side="right") + horizon].date()) < cutoff
                                    for d in bundle["schedule"] if d < cutoff)
        training_depth[str(horizon)] = annual
        if not annual or max(annual.values()) < spec["walkForward"]["minimumMaturedDates"]:
            reasons.append("CALENDAR_TRAINING_DEPTH:" + str(horizon))
    return {"status": "READY" if not reasons else "DATA_INSUFFICIENT", "reasons": sorted(set(reasons)),
            "coverage": coverage, "calendarMaturityUpperBounds": depth, "annualTrainingDepthUpperBounds": training_depth,
            "counters": asdict(counters),
            "stoppedBeforeOutcomes": counters.zero()}


@dataclass(frozen=True)
class OutcomePermit:
    specSha256: str
    inputSha256: str
    token: object


_PERMIT_TOKEN = object()


def require_authorization(spec, spec_sha, identity, root=ROOT):
    path = Path(root) / AUTH_PATH
    if not path.is_file():
        raise ValueError("EXECUTE_UNAUTHORIZED")
    auth = json.loads(path.read_text())
    expected = {"studyId": STUDY, "specSha256": spec_sha, "inputSnapshotSha256": identity["sha256"],
                "harnessHashes": spec["dependencyHashes"], "diagnosticSpecSha256": spec["diagnostics"]["sha256"],
                "authorizedExecutions": 1}
    if any(auth.get(k) != v for k, v in expected.items()):
        raise ValueError("AUTHORIZATION_IDENTITY_MISMATCH")
    if not auth.get("authorizedBy") or not auth.get("mergeCommit"):
        raise ValueError("COMMITTED_OPERATOR_AUTHORIZATION_REQUIRED")
    return auth


def issue_permit(gates, spec, sha, identity, root=ROOT):
    if gates["status"] != "READY" or any(gates.get("counters", {}).values()):
        raise ValueError("OUTCOME_PERMIT_REQUIRES_CLEAN_PASSED_GATES")
    require_authorization(spec, sha, identity, root)
    return OutcomePermit(sha, identity["sha256"], _PERMIT_TOKEN)


def require_permit(permit):
    if not isinstance(permit, OutcomePermit) or permit.token is not _PERMIT_TOKEN:
        raise ValueError("OUTCOME_ACCESS_WITHOUT_PERMIT")


def build_labels(permit, bundle, spec, horizon, counters):
    require_permit(permit)
    from .alpha_opportunity_v2_evaluation import target_from_sessions
    from .alpha_opportunity_v4_execution import attach_eligibility
    frame = bundle["features"].copy()
    days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    rows = []
    for date, ticker in zip(frame.date, frame.ticker):
        counters.targetCalls += 1
        rows.append(target_from_sessions(days, bundle["prices"], spec["benchmark"], ticker, date,
                                         horizon, spec["developmentCutoff"]))
        counters.labelCalls += 1
    labelled = pd.concat([frame.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    # Audited evidence is evaluation-only; never selects securities ex ante.
    foundation = json.loads((ROOT / spec["inputs"]["terminalFoundationPath"]).read_text())
    complete = {row["code"] + ".KS": row.get("completeness") for row in foundation.get("securities", [])}
    labelled = attach_eligibility(labelled, bundle["prices"], complete)
    bad = ~labelled.eligibilityStatus.eq("ELIGIBLE") & labelled.labelStatus.eq("MATURED")
    labelled.loc[bad, "labelStatus"] = "UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE"
    return labelled


def model_predictions(permit, labelled, bundle, spec, horizon, counters):
    require_permit(permit)
    outputs, baselines, records = [], [], []
    started = False
    for fold in M.folds(labelled, bundle["schedule"], spec):
        if fold["status"] != "READY":
            if started:
                raise ValueError("MISSING_LATER_ANNUAL_FOLD")
            continue
        started = True
        train, valid = fold["train"], fold["valid"]
        counters.fitCalls += 1
        fitted = M.fit_predict(train, valid, spec)
        counters.predictionCalls += 1
        predictions = fitted["predictions"]
        # Limited descriptive challenger; cannot alter the primary decision.
        challenger_error = None
        try:
            counters.fitCalls += 1
            challenger = M.fit_predict(train, valid, spec, challenger=True)
            counters.predictionCalls += 1
            predictions["challengerPrediction"] = challenger["predictions"].prediction.to_numpy()
        except (ValueError, FloatingPointError) as exc:
            challenger_error = type(exc).__name__
            predictions["challengerPrediction"] = None
        from sklearn.linear_model import Ridge
        from .alpha_opportunity_model import TrainTransformer, date_weights
        ordered = valid.sort_values(["date", "ticker"])
        weights = date_weights(train.date)
        transform = TrainTransformer(["relative126"]).fit(train, weights)
        baseline = Ridge(**spec["model"]["ridge"])
        counters.fitCalls += 1
        baseline.fit(transform.transform(train), train.forwardRelativeReturn, sample_weight=weights)
        counters.predictionCalls += 1
        base = ordered[["date", "ticker"]].copy()
        base["momentumPrediction"] = baseline.predict(transform.transform(ordered))
        base["meanPrediction"] = np.average(train.forwardRelativeReturn, weights=weights)
        outputs.append(predictions)
        baselines.append(base)
        records.append({"horizon": horizon, "cutoff": fold["cutoff"], "trainingDates": train.date.nunique(),
                        "trainingRows": len(train), "omittedFeatures": fitted["omittedFeatures"],
                        "columns": fitted["columns"], "coefficients": fitted["estimator"].coef_.tolist(),
                        "intercept": float(fitted["estimator"].intercept_),
                        "challengerError": challenger_error,
                        "transformSnapshot": {"activeNames": fitted["transformer"].active_names,
                                              "rawCenter": fitted["transformer"].raw.center,
                                              "rawScale": fitted["transformer"].raw.scale,
                                              "interactionCenter": fitted["transformer"].center.tolist(),
                                              "interactionScale": fitted["transformer"].scale.tolist()}})
    if not outputs:
        raise ValueError("NO_READY_ANNUAL_FOLD")
    predictions = pd.concat(outputs).merge(pd.concat(baselines), on=["date", "ticker"], validate="one_to_one")
    return predictions, records


def development_state(model_evidence, portfolio_evidence):
    if not model_evidence.get("complete") or not portfolio_evidence.get("complete"):
        return "DATA_INSUFFICIENT"
    conditions = [model_evidence["mseImprovementVsMean"] > 0,
                  model_evidence["mseImprovementVsMomentum"] > 0,
                  model_evidence["rankWeightedSpread"] > 0,
                  portfolio_evidence["netExcess"] > 0,
                  all(v > 0 for v in portfolio_evidence["chronologicalHalfExcess"])]
    if all(conditions):
        return "DEVELOPMENT_CANDIDATE"
    if not any(conditions[:3]) or portfolio_evidence["netExcess"] <= 0:
        return "DEVELOPMENT_REJECT"
    return "DEVELOPMENT_INCONCLUSIVE"


def prediction_receipt(path, *, signal_date, merge_date, spec_sha, input_sha, model_snapshot_sha,
                       predictions, portfolio, overlay):
    if pd.Timestamp(signal_date) <= pd.Timestamp(merge_date):
        raise ValueError("PROSPECTIVE_SIGNAL_MUST_BE_STRICTLY_AFTER_SPEC_MERGE")
    if pd.Timestamp(signal_date) not in RC.sessions(signal_date, signal_date, "KR"):
        raise ValueError("PROSPECTIVE_SIGNAL_NOT_KR_SESSION")
    forbidden = ("forward", "realized", "outcome", "sharpe", "cagr", "label")
    def inspect(value):
        if isinstance(value, dict):
            if any(any(word in str(k).lower() for word in forbidden) for k in value):
                raise ValueError("OUTCOME_IN_PROSPECTIVE_RECEIPT")
            for v in value.values():
                inspect(v)
        elif isinstance(value, list):
            for v in value:
                inspect(v)
    document = {"studyId": STUDY, "scientificStatus": "PROSPECTIVE_PREDICTION_ONLY", "signalDate": signal_date,
                "specSha256": spec_sha, "inputSnapshotSha256": input_sha, "modelSnapshotSha256": model_snapshot_sha,
                "predictions": predictions, "portfolio": portfolio, "overlay": overlay}
    inspect(document)
    return atomic_write(path, document, immutable=True)


def evaluate_model(permit, predictions, labels, spec, counters):
    require_permit(permit)
    counters.modelOutcomeCalls += 1
    joined = predictions.merge(labels[["date", "ticker", "forwardRelativeReturn", "labelStatus"]],
                               on=["date", "ticker"], validate="one_to_one")
    matured = joined.loc[joined.labelStatus.eq("MATURED")]
    if len(matured) < len(joined.loc[~joined.labelStatus.eq("PENDING")]) or matured.date.nunique() < spec["gates"]["minimumEvaluationDates"]:
        return {"complete": False, "reason": "UNRESOLVED_ENDPOINT_OR_EVALUATION_DEPTH"}
    summaries = []
    from .alpha_opportunity_v5_evidence import rank_weighted_spread_design
    for _, group in matured.groupby("date", sort=True):
        y, prediction = group.forwardRelativeReturn.to_numpy(float), group.prediction.to_numpy(float)
        summaries.append({
            "mseImprovementVsMean": float(np.mean((group.meanPrediction.to_numpy() - y)**2 - (prediction - y)**2)),
            "mseImprovementVsMomentum": float(np.mean((group.momentumPrediction.to_numpy() - y)**2 - (prediction - y)**2)),
            "rankWeightedSpread": float(rank_weighted_spread_design(prediction, group.ticker).weights @ y)})
    return {"complete": True, "dates": len(summaries),
            **{key: float(np.mean([r[key] for r in summaries])) for key in summaries[0]}}


def _price(prices, market, ticker, day, previous=None):
    """An observed halt permits carry; missing/delisted economics do not."""
    frame = prices.get(ticker)
    stamp = pd.Timestamp(day)
    value = frame.loc[stamp, "Close"] if frame is not None and stamp in frame.index else None
    if value is not None and np.isfinite(value) and value > 0:
        return float(value)
    quote = market.at(ticker, day)
    if quote and quote["volume"] == 0 and previous is not None:
        return previous
    raise ValueError("PORTFOLIO_MARK_OR_TERMINAL_ECONOMICS_UNRESOLVED: " + ticker + ":" + day)


def replay_portfolio(permit, predictions, bundle, spec, counters, *, variant="primary", stress=1.0):
    """Daily continuous path; 21-KR-session origin-fixed rebalance, next-close fills.

No calendar anchor moves to a date with data. Zero-volume/missing execution
quotes defer that security's order. Liquidity-capped partial fills carry holdings;
unresolved held terminal economics block the complete path, never disappear.
"""
    require_permit(permit)
    counters.portfolioOutcomeCalls += 1
    cfg = spec["portfolio"]
    days = RC.sessions(spec["walkForward"]["featureStart"], spec["developmentCutoff"], "KR")
    if predictions.empty:
        return {"complete": False, "reason": "NO_PREDICTIONS"}
    by_date = {date: group for date, group in predictions.groupby("date")}
    schedule = bundle["schedule"]
    positions, previous_prices = {}, {}
    nav = benchmark_nav = gross_nav = 1.0
    previous_benchmark = None
    started = False
    records = []
    # First full prediction date, calendar-determined folds, precedes the entry.
    first_prediction = min(by_date) if by_date else None
    if not first_prediction:
        return {"complete": False, "reason": "NO_PREDICTIONS"}
    for index, stamp in enumerate(days):
        day = str(stamp.date())
        if day <= first_prediction:
            continue
        if started:
            stock_growth = {}
            for ticker in positions:
                mark = _price(bundle["prices"], bundle["market"], ticker, day, previous_prices.get(ticker))
                stock_growth[ticker] = mark / previous_prices[ticker]
                previous_prices[ticker] = mark
            growth = 1 - sum(positions.values()) + sum(w * stock_growth[t] for t, w in positions.items())
            positions = {t: w * stock_growth[t] / growth for t, w in positions.items()}
            nav *= growth
            gross_nav *= growth
            benchmark_price = _price(bundle["prices"], bundle["market"], spec["benchmark"], day)
            benchmark_nav *= benchmark_price / previous_benchmark
            previous_benchmark = benchmark_price
        cost, turnover, overlay, selected = 0.0, 0.0, None, []
        if index % spec["rebalance"]["strideKrSessions"] == 0:
            prior_signals = [d for d in schedule if d < day]
            signal = prior_signals[-1] if prior_signals else None
            if signal not in by_date:
                if started:
                    raise ValueError("MISSING_SCHEDULED_PREDICTION")
                continue
            inputs = bundle["features"].loc[bundle["features"].date.eq(signal)]
            group = by_date[signal].rename(columns={"prediction": "predictionH126"})
            merged = group.merge(inputs.drop(columns="region"), on=["date", "ticker"], validate="one_to_one")
            overlay = bundle["overlay"][signal]
            if overlay["status"] != "READY":
                raise ValueError("OVERLAY_UNAVAILABLE_AT_REBALANCE")
            rows = merged.to_dict("records")
            if variant == "momentum":
                rows = [{**r, "predictionH126": r["momentumPrediction"]} for r in rows]
            decision = P.construct(rows, overlay["riskMultiplier"], cfg)
            desired = decision["weights"]
            selected = decision["selected"]
            if variant == "equal":
                names = P.select(rows, cfg)
                equal_rows = [{**r, "downsideVol126": 1.0} for r in names]
                desired = {t: w * overlay["riskMultiplier"] for t, w in P.size(equal_rows, cfg).items()}
            after = dict(positions)
            adv = {}
            desired_buys = {}
            for ticker in sorted(set(positions) | set(desired)):
                quote = bundle["market"].at(ticker, day)
                history = bundle["market"].trailing(ticker, signal, 60)
                if not quote or quote["volume"] <= 0 or len(history) < 60 or any(r is None for r in history):
                    continue  # No fictitious suspension fill.
                adv[ticker] = float(np.mean([r["tradingValue"] for r in history]))
                limit = cfg["maximumAdvFraction"] * adv[ticker] / cfg["referenceNavKrw"]
                change = np.clip(desired.get(ticker, 0) - positions.get(ticker, 0), -limit, limit)
                if change <= 0:
                    after[ticker] = max(0.0, positions.get(ticker, 0) + change)
                else:
                    desired_buys[ticker] = change
            # Cash freed by executable sells only; deferred exits cannot finance buys.
            desired_buys = P.limit_new_positions(after, desired_buys, selected, cfg["maximumHoldings"])
            capacity = max(0.0, 1 - sum(after.values()))
            demand = sum(desired_buys.values())
            fraction = min(1.0, capacity / demand) if demand else 0.0
            for ticker, change in desired_buys.items():
                after[ticker] = after.get(ticker, 0) + fraction * change
            after = {t: float(w) for t, w in sorted(after.items()) if w > 1e-12}
            cost_info = P.trading_cost(positions, after, adv, cfg, stress=stress)
            cost, turnover = cost_info["costFraction"], cost_info["oneWayTurnover"]
            # Costs charged once at the close, the remaining NAV is the new
            # investable base. Frozen weight-based implementation approximation.
            nav *= 1 - cost
            positions = after
            for ticker in positions:
                previous_prices[ticker] = _price(bundle["prices"], bundle["market"], ticker, day, previous_prices.get(ticker))
            if not started:
                started = True
                previous_benchmark = _price(bundle["prices"], bundle["market"], spec["benchmark"], day)
            if len(positions) > cfg["maximumHoldings"]:
                raise ValueError("REPLAY_HOLDING_CAP")
            if sum(positions.values()) > 1 + 1e-10:
                raise ValueError("REPLAY_LEVERAGE")
        if started:
            records.append({"date": day, "nav": nav, "grossNav": gross_nav, "benchmarkNav": benchmark_nav,
                            "cost": cost, "turnover": turnover, "holdings": len(positions),
                            "cashWeight": 1 - sum(positions.values()), "weights": dict(positions),
                            "selected": selected, "overlay": overlay})
    if len(records) < spec["gates"]["minimumPortfolioSessions"]:
        return {"complete": False, "reason": "PORTFOLIO_DEPTH"}
    from .kr_portfolio_diagnostics import portfolio_metrics
    return {"complete": True, **portfolio_metrics(records), "path": records}


def run_historical(permit, bundle, spec, counters):
    require_permit(permit)
    models, predictions, records = {}, {}, []
    for horizon in spec["horizons"]:
        labels = build_labels(permit, bundle, spec, horizon, counters)
        try:
            scored, folds = model_predictions(permit, labels, bundle, spec, horizon, counters)
        except ValueError as exc:
            if str(exc) not in ("NO_READY_ANNUAL_FOLD", "MISSING_LATER_ANNUAL_FOLD", "MISSING_ENTIRE_TRAINING_FAMILY", "DATA_INSUFFICIENT_ALL_FEATURES_MISSING"):
                raise
            models[str(horizon)] = {"complete": False, "reason": str(exc)}
            predictions[str(horizon)] = pd.DataFrame()
            continue
        models[str(horizon)] = evaluate_model(permit, scored, labels, spec, counters)
        predictions[str(horizon)] = scored
        records.extend(folds)
    try:
        portfolio = replay_portfolio(permit, predictions["126"], bundle, spec, counters)
    except ValueError as exc:
        portfolio = {"complete": False, "reason": str(exc)}
    primary = {"studyId": STUDY, "scientificStatus": "DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY",
               "state": development_state(models["126"], portfolio), "model": models,
               "portfolio": {k: v for k, v in portfolio.items() if k != "path"},
               "counters": asdict(counters), "folds": records,
               "prospectiveEvidence": False, "executionAuthorizationConsumed": True}
    return primary, {"predictions": predictions, "portfolio": portfolio}
