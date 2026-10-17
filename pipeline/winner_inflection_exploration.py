"""Shared sample/fold planning and explicitly SYNTHETIC learner comparisons.

Historical label readers/executors are deliberately absent. This is independent
of rp1/C1: neither its completion nor its approval gates another study.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

import numpy as np

from . import experiment_workbench as W
from . import industry_foundation as IF
from . import prospective_receipt_core as PRC

MODELS = ("event_rule", "logistic_win_loss", "ridge", "elastic_net", "shallow_boosting")


@dataclass(frozen=True)
class RunLayout:
    """Disjoint physical output directories, declared before a future run.

    This validator creates nothing and grants no historical execution access.
    """
    universe: str
    features: str
    labels: str
    decisions: str
    evaluation: str

    def __post_init__(self):
        paths = [PurePosixPath(p) for p in asdict(self).values()]
        if any(not p.is_absolute() or ".." in p.parts for p in paths):
            raise ValueError("ABSOLUTE_RUN_DIRECTORIES_REQUIRED")
        if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(paths) for b in paths[i + 1:]):
            raise ValueError("FEATURE_LABEL_AND_OTHER_LAYERS_MUST_BE_PHYSICALLY_SEPARATE")


def validate_panel(observations):
    digest = W.sample_identity(observations)
    aliases = [(o.key.market, o.key.signal_date, o.ticker) for o in observations]
    if len(set(aliases)) != len(aliases):
        raise ValueError("TICKER_HAS_MULTIPLE_IDENTITIES_AT_SIGNAL")
    return digest


def training_plan(observations, references, fold, *, horizon=126, identity_statuses=("VERIFIED_SECURITY",)):
    """Join METADATA only after the full universe exists; preserve exclusions.

    All models receive this same plan. Unresolved/departed samples remain in
    the denominator; absence of a resolvable target is never a neutral outcome.
    """
    if horizon not in (126, 252):
        raise ValueError("HORIZON_NOT_ENABLED_IN_FIRST_EXPLORATION")
    if identity_statuses not in (("VERIFIED_SECURITY",), ("VERIFIED_SECURITY", "PROVISIONAL")):
        raise ValueError("EXPLICIT_IDENTITY_POLICY_REQUIRED")
    universe_sha = validate_panel(observations)
    ids = {o.key.sample_id for o in observations}
    if len({r.sample_id for r in references}) != len(references) or any(r.sample_id not in ids for r in references):
        raise ValueError("DUPLICATE_OR_FOREIGN_LABEL_REFERENCE")
    refs = {r.sample_id: r for r in references}
    train, evaluate, excluded = [], [], {}
    for o in observations:
        sid, at = o.key.sample_id, W._utc(o.signal_at)
        reference = refs.get(sid)
        if reference and (reference.market != o.key.market or reference.horizon_sessions != horizon
                          or W._utc(reference.execution_at).tz_convert("Asia/Seoul" if o.key.market == "KR" else "America/New_York").date().isoformat() <= o.key.signal_date):
            raise ValueError("LABEL_SIGNAL_OR_MARKET_MISMATCH")
        reason = ("IDENTITY_UNRESOLVED" if o.identity_status not in identity_statuses else
                  "NOT_TRADABLE" if o.investable is not True else None)
        if reason:
            excluded[sid] = reason
        elif W._utc(fold.evaluation_start) <= at <= W._utc(fold.evaluation_end):
            # Evaluation predictions require no outcome, including delisted
            # stocks whose future consideration remains unresolved.
            evaluate.append(sid)
        elif at <= W._utc(fold.training_cutoff):
            reason = "LABEL_REFERENCE_MISSING" if reference is None else fold.training_reason(reference)
            if reason:
                excluded[sid] = reason
            else:
                train.append(sid)
        else:
            excluded[sid] = "OUTSIDE_FOLD"
    body = {"universeSha256": universe_sha, "horizon": horizon, "fold": asdict(fold), "identityStatuses": list(identity_statuses),
            "training": sorted(train), "evaluation": sorted(evaluate), "excluded": dict(sorted(excluded.items()))}
    return {**body, "sha256": IF.digest(body)}


@dataclass(frozen=True)
class SyntheticTarget:
    reference: W.LabelReference
    excess: float
    winner: bool
    big_loss: bool

    def __post_init__(self):
        if not self.reference.reference.startswith("synthetic:") or not PRC.finite(self.excess):
            raise ValueError("SYNTHETIC_TARGET_REQUIRED")
        if type(self.winner) is not bool or type(self.big_loss) is not bool or self.winner and self.big_loss:
            raise ValueError("INVALID_SYNTHETIC_CLASSES")


def compare_synthetic(observations, targets, fold, *, seed, horizon=126):
    """Small deterministic rehearsal, never a route to historical fitting.

    Separate targets stay out of feature tables. The only values opened are
    mature training targets selected by the common fold plan.
    """
    if type(seed) is not int or seed < 0:
        raise ValueError("EXPLICIT_SEED_REQUIRED")
    for o in observations:
        if (not o.key.security_identity.startswith("SYNTHETIC:") or
                not all(s.reference.startswith("synthetic:") and s.vintage == "SYNTHETIC_FIXTURE"
                        for s in [o.universe_source, *(c.source for c in o.cells)])):
            raise ValueError("REAL_DATA_LEARNING_NOT_IMPLEMENTED")
    if not all(isinstance(t, SyntheticTarget) for t in targets):
        raise ValueError("SYNTHETIC_TARGET_REQUIRED")
    plan = training_plan(observations, [t.reference for t in targets], fold, horizon=horizon)
    rows, outcomes = {o.key.sample_id: o for o in observations}, {t.reference.sample_id: t for t in targets}
    names = sorted({c.name for o in observations for c in o.cells})

    def matrix(ids):
        return np.array([[{c.name: c.value for c in rows[sid].cells}.get(n) for n in names] for sid in ids], dtype=float)

    train, evaluate = plan["training"], plan["evaluation"]
    if len(train) < 50 or not evaluate or not names:
        return {"status": "BLOCKED", "reason": "INSUFFICIENT_SYNTHETIC_SAMPLE", "planSha256": plan["sha256"]}
    fitted = fit_prepared(matrix(train), matrix(evaluate), names,
                          [outcomes[s].excess for s in train],
                          {kind: [getattr(outcomes[s], kind) for s in train] for kind in ("winner", "big_loss")}, seed=seed)
    if fitted["status"] == "BLOCKED":
        return {**fitted, "planSha256": plan["sha256"]}
    predictions, statuses = fitted["scores"], fitted["modelStatus"]
    event = "financial.operatingPositiveCross"
    if event in fitted["trainingFeatureNames"]:
        predictions["event_rule"] = [None if v is None else float(v > 0) for sid in evaluate
                                     for v in [{c.name: c.value for c in rows[sid].cells}.get(event)]]
        statuses["event_rule"] = "SYNTHETIC_ONLY"
    else:
        statuses["event_rule"] = "BLOCKED_EVENT_NOT_MEASURED"
    statuses["shallow_boosting"] = "NOT_IMPLEMENTED_REQUIRES_2000_ROWS_100_ISSUERS_AND_SEPARATE_SPEC"
    return {"status": "SYNTHETIC_ONLY", "planSha256": plan["sha256"], "evaluationSampleIds": evaluate,
            "trainingRows": len(train), "trainingFeatureNames": fitted["trainingFeatureNames"],
            "scores": predictions, "modelStatus": statuses, "modelFits": fitted["modelFits"],
            "productionPromotion": False, "probabilityCalibrated": False}


def fit_prepared(x, test, names, excess, classes, *, seed, elastic_net=True, class_minimum=5):
    """Shared numeric learner, with no source reader or authorization side effect.

    The historical orchestrator must obtain its permit BEFORE loading values.
    Synthetic callers retain their separate source-marker checks above.
    """
    x, test = np.asarray(x, dtype=float), np.asarray(test, dtype=float)
    # Drop wholly unmeasured columns from TRAINING only. An all-missing feature
    # must not quietly become a fabricated zero column.
    measured = ~np.isnan(x).all(axis=0)
    x, test = x[:, measured], test[:, measured]
    if not measured.any():
        return {"status": "BLOCKED", "reason": "NO_MEASURABLE_TRAINING_FEATURE"}
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import ElasticNet, LogisticRegression, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def learner(model):
        # All preprocessing fits on the mature training prefix, never test.
        return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), model)

    predictions, statuses, fits = {}, {}, 0
    models = [("ridge", Ridge(alpha=1.0))]
    if elastic_net:
        models.append(("elastic_net", ElasticNet(alpha=0.01, l1_ratio=0.5, max_iter=5000, random_state=seed)))
    for model_name, model in models:
        fitted = learner(model).fit(x, excess)
        predictions[model_name] = fitted.predict(test).tolist()
        statuses[model_name] = "FITTED_UNCALIBRATED"
        fits += 1
    for kind in ("winner", "big_loss"):
        y = np.array(classes[kind], dtype=int)
        if min(np.count_nonzero(y), np.count_nonzero(1 - y)) < class_minimum:
            statuses["logistic_" + kind] = "BLOCKED_INSUFFICIENT_CLASS_SUPPORT"
            continue
        model = learner(LogisticRegression(C=1.0, random_state=seed, max_iter=1000)).fit(x, y)
        predictions["logistic_" + kind] = model.predict_proba(test)[:, 1].tolist()
        statuses["logistic_" + kind] = "FITTED_UNCALIBRATED"
        fits += 1
    return {"status": "FITTED_UNCALIBRATED", "trainingFeatureNames": [n for n, keep in zip(names, measured) if keep],
            "scores": predictions, "modelStatus": statuses, "modelFits": fits}


def evaluation_gate(economics, references, *, as_of, maximum_positions=5):
    """Economic evaluation prerequisites; BLOCKED returns no portfolio/score."""
    if type(maximum_positions) is not int or not 0 <= maximum_positions <= 5:
        raise ValueError("AT_MOST_FIVE_SECURITIES")
    reasons = set(economics.blockers())
    now = W._utc(as_of)
    if not references:
        reasons.add("NO_EVALUABLE_OUTCOME_REFERENCES")
    for reference in references:
        if reference.market != economics.market:
            reasons.add("OUTCOME_MARKET_MISMATCH")
        if reference.price_basis_status != "VERIFIED" or reference.terminal_status == "UNRESOLVED":
            reasons.add("BLOCKED_OUTCOME_ECONOMICS")
        if W._utc(reference.available_at) > now:
            reasons.add("OUTCOME_NOT_MATURE_OR_AVAILABLE")
    if len({r.horizon_sessions for r in references}) > 1:
        reasons.add("MIXED_EVALUATION_HORIZONS")
    return {"status": "BLOCKED" if reasons else "CONTRACT_READY_EXECUTOR_NOT_IMPLEMENTED", "reasons": sorted(reasons),
            "maximumPositions": maximum_positions, "historicalExecutionAuthorized": False, "productionPromotion": False}


def trial_record(prior, *, version, reason, result_informed, specification):
    """Append-only hash-chain VALUE, no filesystem writer or permission grant.

    Record failed/abandoned trials too. A post-result change can be legitimate
    exploration but cannot inherit a PRE_RESULT/OOS claim.
    """
    previous = None
    for record in prior:
        body = {k: v for k, v in record.items() if k != "sha256"}
        if body.get("parentSha256") != previous or IF.digest(body) != record.get("sha256"):
            raise ValueError("TRIAL_HISTORY_REWRITTEN")
        previous = record["sha256"]
    if not version or not reason or type(result_informed) is not bool or not specification:
        raise ValueError("EXPLICIT_TRIAL_CHANGE_REQUIRED")
    if any(r["version"] == version for r in prior):
        raise ValueError("TRIAL_VERSION_ALREADY_RECORDED")
    body = {"version": version, "reason": reason, "parentSha256": previous, "specification": specification,
            "hypothesisStatus": "RESULT_INFORMED_EXPLORATION" if result_informed else "PRE_RESULT_EXPLORATION",
            "independentOosEvidence": False, "trialNumber": len(prior) + 1}
    return {**body, "sha256": IF.digest(body)}
