"""RP1 Track D v2 — endogenous stock count against the regional ETF (PREREGISTERED DESIGN, INACTIVE).

Spec: docs/research-program/specs/rp1-d-v2-endogenous-breadth-v1.json (issue #282). Design: docs/research-program/rp1-d-v2-endogenous-breadth-ko.md.

The question, per region and per decision session: how much of the equity sleeve should leave the regional ETF (KR 069500.KS, US SPY) for
individual stocks, and which ones? The number of names N is the OUTCOME of that decision. N = 0 (ETF 100%) is a normal answer, and so are
1, 2, 5, 10 and more than 10; nothing here fills a slot or caps the count. The legacy contract (`rp1_d_composition_contract`, at most 5) and
`weekly-passive-first-v1` (0-5 per region) are not modified and stay the active policy.

Objective (pp over the forecast horizon H): maximise  w'alpha_cons - C4'v - (lambda/100) (w'c_b + 1/2 w'S w)
  alpha_cons = G - z SE        G: gross excess over the regional ETF, SE: calibrated forecast error
  C4                           four-leg switching cost (ETF sell, stock buy, stock sell, ETF buy), charged once, only on ADDED fractions
  S, c_b                       past-only active covariance and active/ETF covariance (the second-order log-growth terms)
  lambda >= 1                  fractional-Kelly risk aversion; risk budget and caps are separate constraints, never folded into alpha

INACTIVE. Real inputs need (1) a forecast producer digest registered in REGISTERED_A_ADMISSIONS and (2) owner parameters in
OWNER_PARAMETERS. Both are empty: no admitted per-name forecast exists and every policy number belongs to the owner. Synthetic fixtures are
accepted only through `decide_region(..., synthetic_owner_parameters=...)` with evidenceClass SYNTHETIC_FIXTURE, and every such result is
stamped. No function here reads a realised return, writes a receipt, an order or a production artifact, and production does not import it.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

STUDY = "rp1-d-v2-endogenous-breadth-v1"
SPEC_PATH = "docs/research-program/specs/rp1-d-v2-endogenous-breadth-v1.json"
STATUS = "PREREGISTERED_DESIGN_INACTIVE_NO_ALLOCATION"
DEFAULT_POLICY = "EXISTING_PASSIVE_ETF_POLICY"
REGIONS = ("KR", "US")
REGIONAL_ETF = {"KR": "069500.KS", "US": "SPY"}
SEPARATE_COMPARISONS = {"US": ("QQQ",)}          # tracked separately; never a candidate, benchmark or residual
CURRENCY = {"KR": "KRW", "US": "USD"}
HORIZONS = (126, 252)
EXCESS_BASIS = "GROSS_VS_REGIONAL_ETF_TOTAL_RETURN"
COST_LEGS = ("etfSell", "stockBuy", "stockSell", "etfBuy")
COST_STRESS = (1, 2, 3)
SYNTHETIC = "SYNTHETIC_FIXTURE"
SYNTHETIC_STAMP = "SYNTHETIC_FIXTURE_NOT_A_DECISION"
TICKER_PATTERNS = {"KR": re.compile(r"[0-9]{6}\.KS"), "US": re.compile(r"[A-Z][A-Z0-9]{0,5}(?:[.-][A-Z]{1,2})?")}
OWNER_PARAMETER_KEYS = ("horizonSessions", "uncertaintyMultiplierZ", "edgeHurdlePct", "riskAversionLambda", "maxTrackingErrorPct",
                        "maxNameFraction", "maxSectorFraction", "maxActiveFraction", "minPositionFraction")
# SHA-256 digests of admitted per-name forecast producers. Empty: nothing qualifies (US A1 NO_GO, KR A2 not authorised, A0 PROSPECTIVE_ONLY).
REGISTERED_A_ADMISSIONS = frozenset()
# The owner's registered numbers (spec ownerDecisionsRequired). None: the engine is inactive for real inputs.
OWNER_PARAMETERS = None
# SHA-256 of owner-approved C interpretations usable on a v2 book. Empty, as in v1.
OWNER_APPROVED_C_ARTIFACTS = frozenset()
# SHA-256 digests of admitted risk-model producers. Empty: no real risk model is admitted. A digest proves a matrix was not edited after
# it was sealed; only a registered producer makes its stated dates trustworthy.
REGISTERED_RISK_MODEL_PRODUCERS = frozenset()
RISK_MODEL_ESTIMATOR = "LEDOIT_WOLF_DAILY_ACTIVE_PAST_ONLY"
RISK_PROVENANCE_KEYS = ("lastObservationSession", "computedAt", "sourceDigestSha256", "producerSha256", "contentSha256")
# A forecast input that carries any of these is mixing outcomes into a decision and is refused whole.
OUTCOME_FRAGMENTS = ("realized", "realised", "forward", "outcome", "matured", "futurereturn", "label")
ZERO = 1e-9
MAX_ABS_RISK_VALUE = 1e150
CHECK_TOLERANCE = 1e-7


class Refused(ValueError):
    """A region record that cannot be decided; the region holds its ETF."""


# ---------------------------------------------------------------------------------------------------------------------------------
# Small, explicit primitives
# ---------------------------------------------------------------------------------------------------------------------------------
def _finite(v):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:
        return False


def four_leg_cost_pct(legs):
    """C4 in pp of the switched principal, or None. Exactly the four legs; missing is never zero."""
    if not isinstance(legs, dict) or set(legs) != set(COST_LEGS):
        return None
    if not all(_finite(legs[k]) and 0 <= legs[k] < 100 for k in COST_LEGS):
        return None
    return float(sum(legs[k] for k in COST_LEGS))


def schedule_cost_legs(region, as_of):
    """The four legs from the repository's dated schedule (the same one weekly_decision.cost_breakdown sums), in pp."""
    from . import weekly_decision as W
    return {"etfSell": 100 * W.trade_cost_fraction(region, as_of, is_benchmark=True, side="sell"),
            "stockBuy": 100 * W.trade_cost_fraction(region, as_of, is_benchmark=False, side="buy"),
            "stockSell": 100 * W.trade_cost_fraction(region, as_of, is_benchmark=False, side="sell"),
            "etfBuy": 100 * W.trade_cost_fraction(region, as_of, is_benchmark=True, side="buy")}


def net_excess_pct(gross, legs, stress=1):
    """N_k = G - k C4. The only place a cost is deducted."""
    c4 = four_leg_cost_pct(legs)
    return None if c4 is None or not _finite(gross) else float(gross) - stress * c4


def liquidity_cap_fraction(median_traded_value, sleeve_capital, participation):
    """Largest sleeve fraction a name may take so the position is at most `participation` x its past median traded value.
    All three in the region's own currency / units; None when any is unmeasured."""
    if not all(_finite(x) for x in (median_traded_value, sleeve_capital, participation)):
        return None
    if median_traded_value <= 0 or sleeve_capital <= 0 or not 0 < participation <= 1:
        return None
    return min(1.0, participation * median_traded_value / sleeve_capital)


def _instant(value):
    """A timezone-aware ISO-8601 instant, or None. A date alone, a naive timestamp or a malformed string is never an instant."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})", value):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.utcoffset() is not None else None


def _session_text(value):
    return value if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else None


def decision_window_error(region, decision_session, cutoff):
    """The registered conservative cutoff rule. A decision about `decision_session` is fixed at `cutoff` only if that session's close
    has become final (weekly_decision.last_completed_session: close + settlement buffer, KR no earlier than 18:00 KST) and the next
    exchange session has not opened. Inside that window nothing after the decision session's close has traded. None when it holds."""
    import exchange_calendars as xc
    import pandas as pd
    from . import weekly_decision as W
    try:
        completed = W.last_completed_session(region, cutoff)
    except (ValueError, OverflowError):      # an instant the pinned calendar cannot place is refused, never raised
        return "DECISION_CUTOFF_OUTSIDE_THE_CALENDAR"
    if completed < decision_session:
        return "DECISION_CUTOFF_BEFORE_THE_SESSION_CLOSE_IS_FINAL"
    if completed > decision_session:
        return "DECISION_CUTOFF_AFTER_A_LATER_SESSION"
    calendar = xc.get_calendar("XKRX" if region == "KR" else "XNYS", start="1990-01-01", end="2035-12-31")
    following = calendar.sessions_in_range(pd.Timestamp(decision_session) + pd.Timedelta(days=1),
                                           pd.Timestamp(decision_session) + pd.Timedelta(days=21))
    if not len(following):
        return "DECISION_CUTOFF_OUTSIDE_THE_CALENDAR"
    if pd.Timestamp(cutoff) >= calendar.session_open(following[0]):
        return "DECISION_CUTOFF_AT_OR_AFTER_THE_NEXT_OPEN"
    return None


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def risk_model_content_sha256(model):
    """Digest of everything in a risk model except the digest itself: tickers, matrix, c_b, horizon, estimator and provenance."""
    return hashlib.sha256(_canonical({k: v for k, v in model.items() if k != "contentSha256"})).hexdigest()


def seal_risk_model(model):
    """Return a copy with `contentSha256` set; any later edit to a matrix entry or a provenance date breaks it."""
    out = {k: v for k, v in model.items() if k != "contentSha256"}
    out["contentSha256"] = risk_model_content_sha256(out)
    return out


def producer_sha256():
    """Digest of this module's bytes: the producer identity a real risk model built by `active_covariance` would carry."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def active_covariance(stock_returns, etf_returns, decision_session, horizon, *, region, computed_at):
    """Past-only risk model: Ledoit-Wolf shrinkage of daily ACTIVE returns (stock - ETF), and the active/ETF covariance, both scaled to
    H sessions and pp^2. Inputs are pandas objects indexed by session; any row after the decision session is refused, not dropped.
    The result is sealed with its provenance: the last session it read, the instant it was computed (which must be after that session
    closed), a digest of the exact return panel used, the producer digest and a content digest."""
    import pandas as pd
    from sklearn.covariance import LedoitWolf
    from . import weekly_decision as W
    if region not in REGIONS:
        raise ValueError("UNKNOWN_REGION")
    computed = _instant(computed_at)
    if computed is None:
        raise Refused("RISK_MODEL_COMPUTED_AT_NOT_A_TIMEZONE_AWARE_INSTANT")
    cut = pd.Timestamp(decision_session)
    if stock_returns.index.max() > cut or etf_returns.index.max() > cut:
        raise Refused("RISK_MODEL_INPUT_AFTER_DECISION_SESSION")
    frame = stock_returns.join(etf_returns.rename("__etf__"), how="inner").dropna()
    if len(frame) < 2 * frame.shape[1]:
        raise Refused("RISK_MODEL_HISTORY_TOO_SHORT")
    last = frame.index.max().strftime("%Y-%m-%d")
    if W.last_completed_session(region, computed) < last:
        raise Refused("RISK_MODEL_COMPUTED_BEFORE_ITS_LAST_OBSERVATION_WAS_FINAL")
    source = {"columns": [str(c) for c in frame.columns], "index": [d.strftime("%Y-%m-%d") for d in frame.index],
              "values": [[float(x) for x in r] for r in frame.to_numpy()]}
    etf = frame.pop("__etf__")
    active = frame.sub(etf, axis=0)
    tickers = sorted(active.columns)
    active = active[tickers]
    s = LedoitWolf().fit(active.to_numpy()).covariance_ * horizon * 1e4
    cb = np.array([np.cov(active[t].to_numpy(), etf.to_numpy())[0, 1] for t in tickers]) * horizon * 1e4
    return seal_risk_model({
        "tickers": tickers, "matrix": s.tolist(), "benchmarkCovariance": dict(zip(tickers, cb.tolist())),
        "estimator": RISK_MODEL_ESTIMATOR, "observations": int(len(active)), "horizonSessions": horizon,
        "lastObservationSession": last, "computedAt": computed_at,
        "sourceDigestSha256": hashlib.sha256(_canonical(source)).hexdigest(), "producerSha256": producer_sha256()})


def _hex64(v):
    return isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) is not None


def _risk_provenance(record, region, session, cutoff, synthetic):
    """Temporal provenance of a supplied risk model, checked in the decision path before any name is gated. A matrix that does not
    say what it read and when, says it read past the decision session, was computed after the cutoff, or was edited after sealing is
    refused whole. A real record additionally needs a registered producer: the digest proves integrity, not the truth of its dates."""
    from . import weekly_decision as W
    risk = record.get("riskModel")
    if not isinstance(risk, dict):
        raise Refused("RISK_MODEL_UNAVAILABLE")
    if any(k not in risk for k in RISK_PROVENANCE_KEYS):
        raise Refused("RISK_MODEL_PROVENANCE_MISSING")
    if not all(_hex64(risk[k]) for k in ("sourceDigestSha256", "producerSha256", "contentSha256")):
        raise Refused("RISK_MODEL_PROVENANCE_MALFORMED")
    try:
        digest = risk_model_content_sha256(risk)
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        # NaN/Inf, a non-string key or a non-JSON value cannot be canonicalised: a refusal, never an uncaught exception
        raise Refused("RISK_MODEL_NOT_CANONICAL_JSON") from error
    if risk["contentSha256"] != digest:
        raise Refused("RISK_MODEL_CONTENT_DIGEST_MISMATCH")
    if not synthetic and risk["producerSha256"] not in REGISTERED_RISK_MODEL_PRODUCERS:
        raise Refused("RISK_MODEL_PRODUCER_NOT_REGISTERED")
    last = _session_text(risk["lastObservationSession"])
    computed = _instant(risk["computedAt"])
    if last is None or computed is None:
        raise Refused("RISK_MODEL_UNDATED")
    if last > session:
        raise Refused("RISK_MODEL_OBSERVATIONS_AFTER_DECISION_SESSION")
    if computed > cutoff:
        raise Refused("RISK_MODEL_COMPUTED_AFTER_DECISION_CUTOFF")
    try:
        final = W.last_completed_session(region, computed)
    except (ValueError, OverflowError):
        final = None
    if final is None or final < last:
        raise Refused("RISK_MODEL_COMPUTED_BEFORE_ITS_LAST_OBSERVATION_WAS_FINAL")


def _outcome_key(k):
    norm = re.sub(r"[\s_\-.]", "", k).lower() if isinstance(k, str) else ""
    return any(f in norm for f in OUTCOME_FRAGMENTS)


def _refuse_outcome_fields(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _outcome_key(k):
                raise Refused("OUTCOME_FIELD_IN_FORECAST_INPUT:" + str(k))
            _refuse_outcome_fields(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _refuse_outcome_fields(v)


def check_owner_parameters(p):
    """The owner's numbers, validated for domain only. Their VALUES are never chosen here."""
    if not isinstance(p, dict) or set(p) != set(OWNER_PARAMETER_KEYS):
        raise Refused("OWNER_PARAMETERS_UNSET_OR_INCOMPLETE")
    if p["horizonSessions"] not in HORIZONS:
        raise Refused("OWNER_HORIZON_NOT_REGISTERED")
    checks = {"uncertaintyMultiplierZ": lambda x: _finite(x) and x >= 0, "edgeHurdlePct": lambda x: _finite(x) and x >= 0,
              "riskAversionLambda": lambda x: _finite(x) and x >= 1,
              "maxTrackingErrorPct": lambda x: x == "NOT_USED" or (_finite(x) and x > 0),
              "maxNameFraction": lambda x: _finite(x) and 0 < x <= 1, "maxSectorFraction": lambda x: _finite(x) and 0 < x <= 1,
              "maxActiveFraction": lambda x: _finite(x) and 0 <= x <= 1, "minPositionFraction": lambda x: _finite(x) and 0 <= x < 1}
    bad = [k for k, ok in checks.items() if not ok(p[k])]
    if bad:
        raise Refused("OWNER_PARAMETER_OUT_OF_DOMAIN:" + ",".join(bad))
    return p


# ---------------------------------------------------------------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------------------------------------------------------------
def _numeric(v):
    """A finite real number that float arithmetic on a covariance cannot overflow. The bound is numerical safety, not economics:
    |x| <= 1e150 keeps every quadratic form w'Sw (w in [0, 1]) and every eigenvalue far inside the float range."""
    return _finite(v) and abs(v) <= MAX_ABS_RISK_VALUE


def _risk_model(record, names):
    """The supplied covariance, validated element by element in plain Python BEFORE any float conversion, so a malformed payload
    (nested lists, unhashable tickers, integers beyond float range, NaN/Inf) is a refusal and never an exception."""
    risk = record.get("riskModel")
    if not isinstance(risk, dict) or not isinstance(risk.get("tickers"), list):
        raise Refused("RISK_MODEL_UNAVAILABLE")
    tickers = risk["tickers"]
    if not all(isinstance(t, str) for t in tickers):
        raise Refused("RISK_MODEL_MALFORMED")
    idx = {t: i for i, t in enumerate(tickers)}
    if len(idx) != len(tickers) or any(t not in idx for t in names):
        raise Refused("RISK_MODEL_DOES_NOT_COVER_GATED_NAMES")
    matrix, cb_map = risk.get("matrix"), risk.get("benchmarkCovariance")
    n = len(tickers)
    if (not isinstance(matrix, list) or len(matrix) != n
            or not all(isinstance(r, list) and len(r) == n and all(_numeric(x) for x in r) for r in matrix)
            or not isinstance(cb_map, dict) or not all(t in cb_map and _numeric(cb_map[t]) for t in names)):
        raise Refused("RISK_MODEL_MALFORMED")
    full = np.array([[float(x) for x in r] for r in matrix], dtype=float).reshape(n, n)
    cb = np.array([float(cb_map[t]) for t in names], dtype=float)
    sel = [idx[t] for t in names]
    s = full[np.ix_(sel, sel)]
    if not np.allclose(s, s.T, atol=1e-10):
        raise Refused("RISK_MODEL_NOT_SYMMETRIC_PSD")
    try:
        smallest = np.linalg.eigvalsh((s + s.T) / 2).min() if len(s) else 0.0
    except np.linalg.LinAlgError as error:
        raise Refused("RISK_MODEL_NOT_SYMMETRIC_PSD") from error
    if not np.isfinite(smallest) or smallest < -1e-9:
        raise Refused("RISK_MODEL_NOT_SYMMETRIC_PSD")
    if risk.get("horizonSessions") != record.get("horizonSessions"):
        raise Refused("RISK_MODEL_HORIZON_MISMATCH")
    return (s + s.T) / 2, cb


def _name_reasons(row, region, decision_session):
    reasons = []
    t = row.get("ticker")
    if not (isinstance(t, str) and TICKER_PATTERNS[region].fullmatch(t)):
        return ["IDENTIFIER_INVALID"]
    if t == REGIONAL_ETF[region] or t in SEPARATE_COMPARISONS.get(region, ()):
        return ["PASSIVE_INSTRUMENT_IS_NOT_AN_ACTIVE_NAME"]
    if row.get("signalSession") != decision_session:
        reasons.append("FORECAST_STALE_OR_UNDATED")
    if row.get("excessBasis") != EXCESS_BASIS:
        reasons.append("EXCESS_BASIS_NOT_GROSS_VS_REGIONAL_ETF")   # a NET value is refused, never charged again
    if not _finite(row.get("grossExcessPct")):
        reasons.append("GROSS_EXCESS_UNAVAILABLE")
    if not (_finite(row.get("standardErrorPct")) and row["standardErrorPct"] > 0):
        reasons.append("STANDARD_ERROR_UNAVAILABLE")
    if four_leg_cost_pct(row.get("costLegsPct")) is None:
        reasons.append("FOUR_LEG_COST_UNAVAILABLE")
    if not isinstance(row.get("sector"), str) or not row["sector"]:
        reasons.append("SECTOR_UNAVAILABLE")
    cap = row.get("liquidityCapFraction")
    if not (_finite(cap) and 0 < cap <= 1):
        reasons.append("LIQUIDITY_UNMEASURED")
    held = row.get("incumbentFraction", 0.0)
    if not (_finite(held) and 0 <= held <= 1):
        reasons.append("INCUMBENT_FRACTION_INVALID")
    return reasons


def _validate_record(record, region):
    if not isinstance(record, dict):
        raise Refused("FORECAST_RECORD_ABSENT")
    _refuse_outcome_fields(record)
    if record.get("region") != region:
        raise Refused("REGION_MISMATCH")
    if record.get("benchmark") != REGIONAL_ETF[region]:
        raise Refused("BENCHMARK_NOT_THE_REGIONAL_ETF")
    if record.get("horizonSessions") not in HORIZONS:
        raise Refused("HORIZON_NOT_REGISTERED")
    session = _session_text(record.get("decisionSession"))
    if session is None:
        raise Refused("DECISION_SESSION_UNDATED")
    cutoff = _instant(record.get("decisionCutoffAt"))
    if cutoff is None:
        raise Refused("DECISION_CUTOFF_NOT_A_TIMEZONE_AWARE_INSTANT")
    window = decision_window_error(region, session, cutoff)
    if window:
        raise Refused(window)
    names = record.get("names")
    if not isinstance(names, list):
        raise Refused("NAMES_NOT_A_LIST")
    for row in names:
        if not isinstance(row, dict):
            raise Refused("NAME_ROW_MALFORMED")
        available = _instant(row.get("availableAt"))
        if available is None:
            # a date alone cannot show the forecast existed before the decision instant; leakage in one row voids the record
            raise Refused("AVAILABILITY_NOT_A_TIMEZONE_AWARE_INSTANT")
        if available > cutoff:
            raise Refused("LOOK_AHEAD_AVAILABLE_AFTER_DECISION_CUTOFF")
    _risk_provenance(record, region, session, cutoff, record.get("evidenceClass") == SYNTHETIC)
    tickers = [r.get("ticker") for r in names]
    if len(tickers) != len(set(map(str, tickers))):
        raise Refused("DUPLICATE_NAME")
    return session


# ---------------------------------------------------------------------------------------------------------------------------------
# Optimizer (synthetic or registered inputs only)
# ---------------------------------------------------------------------------------------------------------------------------------
def _objective_terms(rows, p, stress):
    z, lam = p["uncertaintyMultiplierZ"], p["riskAversionLambda"]
    alpha = np.array([r["grossExcessPct"] - z * r["standardErrorPct"] for r in rows], dtype=float)
    c4 = np.array([stress * four_leg_cost_pct(r["costLegsPct"]) for r in rows], dtype=float)
    return alpha, c4, lam / 100.0


def _solve(rows, s, cb, p, stress):
    """The tracking-error budget, when registered, is met through its KKT form: the TE-constrained optimum equals the unconstrained one
    with an extra variance penalty mu >= 0, and TE is non-increasing in mu, so mu is bisected until TE <= budget (the feasible end is
    kept). The solver itself only ever sees linear constraints."""
    te = p["maxTrackingErrorPct"]

    def track(w):
        return math.sqrt(max(float(w @ s @ w), 0.0))

    w, v, value = _solve_linear(rows, s, cb, p, stress, 0.0)
    if te == "NOT_USED" or track(w) <= te:
        return w, v, value
    lo, hi = 0.0, 1.0
    while track(_solve_linear(rows, s, cb, p, stress, hi)[0]) > te:
        hi *= 2.0
        if hi > 1e12:
            raise Refused("TRACKING_ERROR_BUDGET_UNREACHABLE")
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if track(_solve_linear(rows, s, cb, p, stress, mid)[0]) > te:
            lo = mid
        else:
            hi = mid
    w, v, _ = _solve_linear(rows, s, cb, p, stress, hi)
    alpha, c4, k = _objective_terms(rows, p, stress)
    value = float(alpha @ w - c4 @ v - k * (cb @ w + 0.5 * w @ s @ w))      # reported on the registered objective, not the penalised one
    return w, v, value


def _solve_linear(rows, s, cb, p, stress, mu):
    """SLSQP over keep (u) and add (v) fractions with linear constraints only; `mu` is the TE multiplier (0 = none)."""
    from scipy.optimize import minimize
    n = len(rows)
    alpha, c4, k = _objective_terms(rows, p, stress)
    q = k + mu / 100.0
    h = p["edgeHurdlePct"]
    held = np.array([r.get("incumbentFraction", 0.0) for r in rows], dtype=float)
    cap = np.array([min(p["maxNameFraction"], r["liquidityCapFraction"]) for r in rows])
    keep_ok = alpha > h
    add_ok = alpha - c4 > h
    ub_u = np.where(keep_ok, np.minimum(held, cap), 0.0)
    ub_v = np.where(add_ok, cap, 0.0)

    def split(x):
        return x[:n], x[n:]

    def f(x):
        u, v = split(x)
        w = u + v
        return -(alpha @ w - c4 @ v - k * (cb @ w) - 0.5 * q * (w @ s @ w))

    def grad(x):
        u, v = split(x)
        w = u + v
        gw = alpha - k * cb - q * (s @ w)
        return -np.concatenate([gw, gw - c4])

    ones = np.concatenate([np.eye(n), np.eye(n)], axis=1)     # w = A x
    cons = [{"type": "ineq", "fun": lambda x: cap - ones @ x, "jac": lambda x: -ones},
            {"type": "ineq", "fun": lambda x: p["maxActiveFraction"] - ones.sum(axis=0) @ x,
             "jac": lambda x: -ones.sum(axis=0)[None, :]}]
    for sector in sorted({r["sector"] for r in rows}):
        m = np.array([r["sector"] == sector for r in rows], dtype=float) @ ones
        cons.append({"type": "ineq", "fun": lambda x, m=m: p["maxSectorFraction"] - m @ x, "jac": lambda x, m=m: -m[None, :]})
    x0 = np.concatenate([ub_u, np.zeros(n)])     # start from the retained book; deterministic
    res = minimize(f, x0, jac=grad, method="SLSQP", bounds=list(zip([0.0] * (2 * n), np.concatenate([ub_u, ub_v]))),
                   constraints=cons, options={"maxiter": 1000, "ftol": 1e-12})
    if not res.success:
        raise Refused("OPTIMIZER_DID_NOT_CONVERGE")
    u, v = split(np.clip(res.x, 0.0, None))
    w = u + v
    empty = w < ZERO
    u, v, w = np.where(empty, 0.0, u), np.where(empty, 0.0, v), np.where(empty, 0.0, w)
    if (w > cap + CHECK_TOLERANCE).any() or w.sum() > p["maxActiveFraction"] + CHECK_TOLERANCE:
        raise Refused("OPTIMUM_VIOLATES_A_CONSTRAINT")
    for sector in {r["sector"] for r in rows}:
        if sum(w[i] for i, r in enumerate(rows) if r["sector"] == sector) > p["maxSectorFraction"] + CHECK_TOLERANCE:
            raise Refused("OPTIMUM_VIOLATES_A_CONSTRAINT")
    value = -f(np.concatenate([u, v]))
    if value < -CHECK_TOLERANCE:
        raise Refused("OPTIMUM_WORSE_THAN_ETF_ONLY")
    return w, v, value


def _book(rows, s, cb, p, stress=1):
    """Solve, then remove sub-minimum positions one at a time (smallest, ticker tie-break) and re-solve."""
    live = list(range(len(rows)))
    while True:
        if not live:
            return {}, {}, 0.0
        sub = [rows[i] for i in live]
        w, v, value = _solve(sub, s[np.ix_(live, live)], cb[live], p, stress)
        small = [(w[j], sub[j]["ticker"], j) for j in range(len(sub)) if 0 < w[j] < p["minPositionFraction"]]
        if not small:
            held = {sub[j]["ticker"]: float(w[j]) for j in range(len(sub)) if w[j] > 0}
            added = {sub[j]["ticker"]: float(v[j]) for j in range(len(sub)) if w[j] > 0}
            return held, added, value
        live.pop(min(small)[2])


def _diagnostics(held, rows, s, region):
    tickers = [r["ticker"] for r in rows]
    w = np.array([held.get(t, 0.0) for t in tickers])
    total = float(w.sum())
    sectors = {}
    for r in rows:
        if held.get(r["ticker"]):
            sectors[r["sector"]] = sectors.get(r["sector"], 0.0) + held[r["ticker"]]
    return {"activeCount": len(held), "activeFraction": total, "etfFraction": 1.0 - total, "etf": REGIONAL_ETF[region],
            "effectiveNames": (total ** 2 / float((w ** 2).sum())) if total > 0 else 0.0,
            "largestNameFraction": float(w.max()) if len(w) else 0.0, "sectorFractions": dict(sorted(sectors.items())),
            "activeTrackingErrorPct": math.sqrt(max(float(w @ s @ w), 0.0)), "currency": CURRENCY[region]}


# ---------------------------------------------------------------------------------------------------------------------------------
# Public decision
# ---------------------------------------------------------------------------------------------------------------------------------
def _etf_default(region, reasons, status="ETF_DEFAULT_NO_ADMITTED_EDGE", **extra):
    out = {"studyId": STUDY, "region": region, "status": status, "defaultPolicy": DEFAULT_POLICY, "etf": REGIONAL_ETF[region],
           "activeCount": 0, "etfFraction": 1.0, "shadowFractions": {}, "reasons": reasons, "productionAffected": False}
    out.update(extra)
    return out


def decide_region(record, region, *, synthetic_owner_parameters=None):
    """One region's v2 decision. Real input: inactive until both registries exist. Synthetic input: requires evidenceClass
    SYNTHETIC_FIXTURE AND explicit parameters, and the result is stamped. Never touches production."""
    if region not in REGIONS:
        raise ValueError("UNKNOWN_REGION")
    synthetic = isinstance(record, dict) and record.get("evidenceClass") == SYNTHETIC
    if synthetic != (synthetic_owner_parameters is not None):
        return _etf_default(region, ["SYNTHETIC_MODE_REQUIRES_BOTH_FIXTURE_CLASS_AND_FIXTURE_PARAMETERS"], status="ETF_DEFAULT_REFUSED")
    stamp = {"stamp": SYNTHETIC_STAMP} if synthetic else {}
    try:
        if synthetic:
            params = check_owner_parameters(synthetic_owner_parameters)
        else:
            if not (isinstance(record, dict) and record.get("admissionSha256") in REGISTERED_A_ADMISSIONS):
                raise Refused("NO_ADMITTED_PER_NAME_FORECAST_PRODUCER")
            params = check_owner_parameters(OWNER_PARAMETERS)
        session = _validate_record(record, region)
        if record["horizonSessions"] != params["horizonSessions"]:
            raise Refused("FORECAST_HORIZON_DIFFERS_FROM_REGISTERED_HORIZON")
    except Refused as why:
        return _etf_default(region, [str(why)], **stamp)
    excluded, gated = {}, []
    for row in record["names"]:
        why = _name_reasons(row, region, session)
        if why:
            excluded[str(row.get("ticker"))] = why
        else:
            gated.append(row)
    z, h = params["uncertaintyMultiplierZ"], params["edgeHurdlePct"]
    passing = []
    for row in sorted(gated, key=lambda r: r["ticker"]):
        alpha = row["grossExcessPct"] - z * row["standardErrorPct"]
        new_ok = alpha - four_leg_cost_pct(row["costLegsPct"]) > h
        keep_ok = row.get("incumbentFraction", 0.0) > 0 and alpha > h
        if new_ok or keep_ok:
            passing.append(row)
        else:
            excluded[row["ticker"]] = ["EDGE_AFTER_UNCERTAINTY_AND_COST_NOT_ABOVE_HURDLE"]
    common = {"excluded": dict(sorted(excluded.items())), "screenedNames": len(record["names"]), "passingNames": len(passing),
              "decisionSession": session, "horizonSessions": record["horizonSessions"], **stamp,
              "b": {"used": False, "role": "CONTEXT_ONLY"}, "c": _c_overlay(record.get("cOverlay")),
              "separateComparisons": list(SEPARATE_COMPARISONS.get(region, ()))}
    if not passing:
        return _etf_default(region, ["NO_NAME_CLEARS_EDGE_AFTER_UNCERTAINTY_COST_AND_HURDLE"], **common)
    try:
        s, cb = _risk_model(record, [r["ticker"] for r in passing])
        held, added, value = _book(passing, s, cb, params)
    except Refused as why:
        return _etf_default(region, [str(why)], **common)
    stress = {}
    for k in COST_STRESS:
        try:
            stress[str(k)] = len(_book(passing, s, cb, params, stress=k)[0])
        except Refused as why:      # a diagnostic that cannot be computed is reported as such and never voids the decision
            stress[str(k)] = str(why)
    if not held:
        return _etf_default(region, ["OPTIMUM_HOLDS_ONLY_THE_ETF"], **common, costStressActiveCount=stress)
    status = "SYNTHETIC_SHADOW_BOOK" if synthetic else "PROSPECTIVE_SHADOW_BOOK"
    out = {"studyId": STUDY, "region": region, "status": status, "defaultPolicy": DEFAULT_POLICY,
           **_diagnostics(held, passing, s, region), "shadowFractions": dict(sorted(held.items())),
           "addedFractions": dict(sorted(added.items())), "objectivePp": value, "costStressActiveCount": stress,
           "reasons": [], "productionAffected": False, **common}
    assert_inactive(out)
    return out


def _c_overlay(c):
    """C is never applied here. A registered approval would apply once to the finished stock+ETF book; none is registered."""
    if c is None:
        return {"used": False, "approved": False}
    approved = isinstance(c, dict) and c.get("ownerApprovalArtifactSha256") in OWNER_APPROVED_C_ARTIFACTS
    return {"used": False, "approved": approved, "reasons": [] if approved else ["C_OWNER_APPROVAL_NOT_REGISTERED"]}


def decide(records, *, synthetic_owner_parameters=None):
    """Both regions, decided independently in their own currencies. A cross-region total is never formed without FX."""
    records = records if isinstance(records, dict) else {}
    regions = {r: decide_region(records.get(r), r, synthetic_owner_parameters=synthetic_owner_parameters) for r in REGIONS}
    out = {"studyId": STUDY, "status": STATUS, "regions": regions, "crossRegionTotal": "FX_AND_REGIONAL_CAPITAL_UNRESOLVED",
           "productionAffected": False}
    assert_inactive(out)
    return out


ORDER_FRAGMENTS = ("order", "notional", "quantity", "qty", "shares", "recommend")


def assert_inactive(obj):
    """No order, quantity or recommendation field, no production effect, finite JSON."""
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                norm = re.sub(r"[\s_\-.]", "", k).lower() if isinstance(k, str) else ""
                if any(f in norm for f in ORDER_FRAGMENTS):
                    raise ValueError("ORDER_FIELD_FORBIDDEN: " + str(k))
                if k == "productionAffected" and v is not False:
                    raise ValueError("PRODUCTION_EFFECT_FORBIDDEN")
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
    walk(obj)
    json.dumps(obj, allow_nan=False)
    return True


def load_spec(root=None):
    """The preregistration, checked against this module's constants."""
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    spec = json.loads((root / SPEC_PATH).read_text())
    owner = spec["ownerDecisionsRequired"]
    if spec["studyId"] != STUDY or spec["status"] != STATUS or spec["objective"]["competingAsset"] != REGIONAL_ETF:
        raise ValueError("SPEC_IDENTITY_MISMATCH")
    if {k: v for k, v in owner.items() if k in OWNER_PARAMETER_KEYS} != {k: None for k in OWNER_PARAMETER_KEYS}:
        raise ValueError("SPEC_OWNER_NUMBERS_MUST_STAY_UNSET_IN_THIS_VERSION")
    if spec["objective"]["separateComparisonsNotCandidates"] != {k: list(v) for k, v in SEPARATE_COMPARISONS.items()}:
        raise ValueError("SPEC_SEPARATE_COMPARISON_MISMATCH")
    return spec
