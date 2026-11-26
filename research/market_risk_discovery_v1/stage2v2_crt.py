"""Market Risk Discovery v1 -- Stage 2 v2: conditional randomization test (CRT) for P1.

Why this replaces the v1 rotation null (independent audit A1). The v1 null rotated the credit flag against the
calendar. That keeps the flag's persistence but destroys its relation to the price features X (on the real signal
side, corr(C, gap200) = -0.39 and corr(C, vol63) = +0.50; the flag is on in 9.4% of FAST-normal months and 41-51% of
stressed months). Under the rotation, a flag that merely proxies a nonlinear function of X that M1 cannot represent
looks informative: the audit's synthetic counterexample (C a deterministic function of X, Y a nonlinear function of
X) gave dBrier = +0.026 and rotation p = 0.003 while Y is independent of C given X.

The CRT (Candes et al. 2018, model-X) keeps the statistic -- any statistic, including the walk-forward dBrier of a
misspecified M1/M2 -- and changes only how null copies of C are drawn: from a GENERATOR of the credit-flag path given
the price-feature path,

    C_t | X_t, C_{t-1}, C_{t-2}  ~  Bernoulli(G(X_t, C_{t-1}, C_{t-2}))

fitted on every defined month (all FAST states) WITHOUT any label. If (i) G is the true conditional law of the flag
path given the X path and (ii) under H0 the flag path carries no information about the labels beyond the X path,
then (C, C~_1, ..., C~_B) are exchangeable given (X, Y) and p = (1 + #{T~ >= T}) / (1 + B) is valid for ANY
statistic T. Misspecification of M1 no longer creates a false positive: a C that is a function of X is redrawn as
(nearly) the same function of X, so T~ ~= T.

What it does NOT give. Validity is exactly as good as G. G is checked against the real flag with label-free
posterior-predictive checks (`adequacy`), and the synthetic environments (stage2v2_synthetic) measure how much size
is lost when G is wrong in specified ways. Neither proves (i). The test also cannot separate "credit leads prices"
from "G misses a contemporaneous relation" -- a rejection is evidence against the conjunction (i) and (ii).
"""
from __future__ import annotations

import numpy as np

from . import stage2_design as D

GEN_LAMBDA = 1.0
CRT_DRAWS = 999
CRT_SEED = 20261125
ADEQUACY_DRAWS = 999
ADEQUACY_SEED = 20261126
ERAS = (("1998-01", "2006-12"), ("2007-01", "2016-12"), ("2017-01", "2026-12"))


# ------------------------------------------------------------------ generator


def x_design(gap: np.ndarray, vol: np.ndarray) -> np.ndarray:
    """Price-feature part of the generator: linear in gap200 and vol63.

    Chosen among five label-free candidates (evidence/stage2v2-generator-selection.json) because it is the only family
    that passed BOTH the in-sample and the out-of-time posterior-predictive checks; the quadratic/interaction/FAST-
    indicator design passed in sample and failed out of time (fit on 2012-2026, it predicted almost no relation to vol
    in 1998-2012). No label was read in that selection."""
    return np.column_stack([gap, vol])


class Generator:
    def __init__(self, gap, vol, flags, lam: float = GEN_LAMBDA, design=None):
        gap, vol, flags = (np.asarray(a, dtype=float) for a in (gap, vol, flags))
        self.design = design or x_design
        self.Xd = self.design(gap, vol)
        self.mean = self.Xd[2:].mean(axis=0)
        self.sd = np.where(self.Xd[2:].std(axis=0) > 0, self.Xd[2:].std(axis=0), 1.0)
        Z = (self.Xd - self.mean) / self.sd
        y = flags[2:]
        A = np.column_stack([np.ones(len(y)), flags[1:-1], flags[:-2], Z[2:]])
        self.beta = D.ridge_logit(A, y, lam)
        pr = 1.0 / (1.0 + np.exp(-(A @ self.beta)))
        pen = np.full(A.shape[1], lam)
        pen[0] = 1e-8
        self.cov = np.linalg.inv((A * (pr * (1 - pr))[:, None]).T @ A + np.diag(pen))
        self.base = self.beta[0] + Z @ self.beta[3:]          # X part of the linear predictor, every month
        self.b1, self.b2 = self.beta[1], self.beta[2]
        self.init = flags[:2].copy()
        self.n = len(flags)

    def transported(self, gap, vol, init) -> "Generator":
        """The same fitted coefficients applied to another X path (out-of-time checks)."""
        g = object.__new__(Generator)
        g.beta, g.mean, g.sd, g.b1, g.b2, g.cov = self.beta, self.mean, self.sd, self.b1, self.b2, self.cov
        g.design = self.design
        g.Xd = self.design(np.asarray(gap, float), np.asarray(vol, float))
        g.base = self.beta[0] + ((g.Xd - self.mean) / self.sd) @ self.beta[3:]
        g.init, g.n = np.asarray(init, float), len(gap)
        return g

    def prob(self, c1, c2, t):
        return 1.0 / (1.0 + np.exp(-(self.base[t] + self.b1 * c1 + self.b2 * c2)))

    def simulate(self, draws: int, rng: np.random.Generator, parameter_uncertainty: bool = False) -> np.ndarray:
        """`draws` flag paths given the X path; the first two months are held at their observed values.

        parameter_uncertainty=False (the CRT): every path uses the fitted coefficients.
        parameter_uncertainty=True (adequacy checks): each path first draws its coefficients from the Laplace
        approximation N(beta, H^-1), so a check's band reflects estimation error as well as sampling noise."""
        out = np.empty((draws, self.n))
        out[:, :2] = self.init
        if parameter_uncertainty:
            B = rng.multivariate_normal(self.beta, self.cov, size=draws)
            Z = (self.Xd - self.mean) / self.sd
            base = B[:, :1] + B[:, 3:] @ Z.T
            b1, b2 = B[:, 1], B[:, 2]
        else:
            base = np.broadcast_to(self.base, (draws, self.n))
            b1, b2 = self.b1, self.b2
        u = rng.random((draws, self.n))
        for t in range(2, self.n):
            pr = 1.0 / (1.0 + np.exp(-(base[:, t] + b1 * out[:, t - 1] + b2 * out[:, t - 2])))
            out[:, t] = (u[:, t] < pr).astype(float)
        return out


# ------------------------------------------------------------------ label-free adequacy checks


def _corr(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def path_stats(c: np.ndarray, gap, vol, months: list[str], common: np.ndarray) -> dict:
    """Signal-only statistics of one flag path (no label)."""
    spells, run = [], 0
    for x in c:
        if x:
            run += 1
        elif run:
            spells.append(run)
            run = 0
    if run:
        spells.append(run)
    out = {"rate": float(c.mean()), "lag1": _corr(c[1:], c[:-1]),
           "meanSpell": float(np.mean(spells)) if spells else 0.0,
           "corrGap": _corr(c, gap), "corrVol": _corr(c, vol),
           "rateCommonSample": float(c[common].mean())}
    for lo, hi in ERAS:
        m = np.array([lo <= x <= hi for x in months])
        if m.any():
            out[f"rate{lo[:4]}_{hi[:4]}"] = float(c[m].mean())
    vt = np.quantile(vol, [1 / 3, 2 / 3])
    for k, (a, b) in enumerate(((-np.inf, vt[0]), (vt[0], vt[1]), (vt[1], np.inf))):
        m = (vol > a) & (vol <= b)
        out[f"rateVolTercile{k + 1}"] = float(c[m].mean())
    return out


def adequacy(gap, vol, flags, months: list[str], common: np.ndarray, draws: int = ADEQUACY_DRAWS,
             seed: int = ADEQUACY_SEED, lam: float = GEN_LAMBDA, design=None) -> dict:
    """Posterior-predictive checks of the fitted generator against the observed flag path. Pre-specified rule:
    ADEQUATE iff no observed statistic lies outside its simulated 99.5% band and at most one lies outside its 95%
    band (12 statistics; under a correct generator about 0.6 fall outside a 95% band by chance), and at most one
    of the 10 out-of-time statistics lies outside its 95% band."""
    g = Generator(gap, vol, flags, lam, design)
    sims = g.simulate(draws, np.random.default_rng(seed), parameter_uncertainty=True)
    obs = path_stats(np.asarray(flags, float), gap, vol, months, common)
    sim = [path_stats(s, gap, vol, months, common) for s in sims]
    checks = {}
    for k, v in obs.items():
        dist = np.array([s[k] for s in sim])
        lo95, hi95 = np.quantile(dist, [0.025, 0.975])
        lo99, hi99 = np.quantile(dist, [0.0025, 0.9975])
        checks[k] = {"observed": v, "band95": [float(lo95), float(hi95)], "band995": [float(lo99), float(hi99)],
                     "outside95": bool(v < lo95 or v > hi95), "outside995": bool(v < lo99 or v > hi99)}
    n95 = sum(c["outside95"] for c in checks.values())
    n99 = sum(c["outside995"] for c in checks.values())
    oot = out_of_time(gap, vol, flags, months, common, draws, seed, lam, design)
    oot_bad = sum(c["outside95"] for half in oot.values() for c in half.values())
    return {"adequate": n99 == 0 and n95 <= 1 and oot_bad <= 1, "outside95": n95, "outside995": n99,
            "outOfTimeOutside95": oot_bad, "checks": checks, "outOfTime": oot,
            "coefficients": [float(b) for b in g.beta],
            "coefficientNames": ["intercept", "C_lag1", "C_lag2"] + [f"x{i}" for i in range(len(g.beta) - 3)],
            "draws": draws, "seed": seed}


OOT_KEYS = ("rate", "lag1", "corrGap", "corrVol", "rateCommonSample")


def out_of_time(gap, vol, flags, months, common, draws, seed, lam=GEN_LAMBDA, design=None) -> dict:
    """Fit on one half of the months, simulate the other half given its X path; observed half statistics must sit
    inside the simulated 95% band (5 statistics per half; at most one of the 10 may fall outside)."""
    gap, vol, flags = (np.asarray(a, float) for a in (gap, vol, flags))
    h = len(flags) // 2
    out = {}
    for name, fit, test in (("fitFirstTestSecond", slice(0, h), slice(h, None)),
                            ("fitSecondTestFirst", slice(h, None), slice(0, h))):
        g = Generator(gap[fit], vol[fit], flags[fit], lam, design).transported(gap[test], vol[test], flags[test][:2])
        sims = g.simulate(draws, np.random.default_rng(seed + 1), parameter_uncertainty=True)
        mt = [months[i] for i in range(len(months))][test]
        obs = path_stats(flags[test], gap[test], vol[test], mt, common[test])
        sim = [path_stats(x, gap[test], vol[test], mt, common[test]) for x in sims]
        out[name] = {}
        for k in OOT_KEYS:
            dist = np.array([x[k] for x in sim])
            lo, hi = np.quantile(dist, [0.025, 0.975])
            out[name][k] = {"observed": obs[k], "band95": [float(lo), float(hi)],
                            "outside95": bool(obs[k] < lo or obs[k] > hi)}
    return out


# ------------------------------------------------------------------ the test


def crt(p: D.Panel, refits, flag_sequence, seq_gap, seq_vol, draws: int = CRT_DRAWS, seed: int = CRT_SEED,
        stats: dict | None = None, design=None) -> dict:
    """CRT p-values for `stats` (name -> f(preds, y)); default the primary dBrier. The generator is fitted on the full
    defined flag sequence and its X path; every null copy is a whole simulated path, read at the panel's rows."""
    stats = stats or {"dBrier": D.d_brier}
    gate = D.structure_gate(p, refits, flag_sequence)
    if not gate["pass"]:
        return {"structure": gate, "p": None}
    start = gate["start"]
    pos, vals = D.sequence_positions(p, flag_sequence)
    g = Generator(seq_gap, seq_vol, vals, design=design)
    y = p.y[D.evaluation_mask(p, start)]
    base = D.walk_forward(p, refits, start, models=("M0", "M1"))
    obs_m2 = D.walk_forward(p, refits, start, vals[pos], models=("M2",))
    observed = {k: f({**base, **obs_m2}, y) for k, f in stats.items()}
    sims = g.simulate(draws, np.random.default_rng(seed))
    null = {k: np.empty(draws) for k in stats}
    for b in range(draws):
        m2 = D.walk_forward(p, refits, start, sims[b][pos], models=("M2",))
        for k, f in stats.items():
            null[k][b] = f({**base, **m2}, y)
    return {"structure": gate, "observed": observed,
            "p": {k: D.one_sided_p(null[k], observed[k]) for k in stats},
            "null": null, "preds": {**base, **obs_m2}, "y": y, "start": start}


# ------------------------------------------------------------------ the frozen v2 evaluation


VERDICTS_V2 = ("DATA_INSUFFICIENT", "GENERATOR_INADEQUATE_NO_INFERENCE", "EXPLORATORY_CONDITIONAL_INFORMATION_SUPPORT",
               "DIRECTIONAL_NOT_SEPARATED", "NOT_DETECTED_UNDERPOWERED")


def verdict_v2(adequate: bool, d: float, crt_p: float, exclusion: dict) -> str:
    if not adequate:
        return "GENERATOR_INADEQUATE_NO_INFERENCE"
    if d > 0 and crt_p <= D.ALPHA and all(v > 0 for v in exclusion.values()):
        return "EXPLORATORY_CONDITIONAL_INFORMATION_SUPPORT"
    if d > 0:
        return "DIRECTIONAL_NOT_SEPARATED"
    return "NOT_DETECTED_UNDERPOWERED"


def evaluate_v2(p: D.Panel, refits, flag_sequence, seq_gap, seq_vol, seq_months, seq_common, starts) -> dict:
    """The frozen v2 comparison. The generator-adequacy gate is label-free and is evaluated first."""
    vals = np.array([v for _, v in flag_sequence])
    adq = adequacy(seq_gap, seq_vol, vals, seq_months, seq_common)
    gate = D.structure_gate(p, refits, flag_sequence)
    if not gate["pass"]:
        return {"verdict": "DATA_INSUFFICIENT", "structure": gate, "generatorAdequacy": adq}
    if not adq["adequate"]:
        return {"verdict": "GENERATOR_INADEQUATE_NO_INFERENCE", "structure": gate, "generatorAdequacy": adq}
    res = crt(p, refits, flag_sequence, seq_gap, seq_vol, stats={"dBrier": D.d_brier, "dLogLoss": D.d_logloss})
    preds, y, start = res["preds"], res["y"], res["start"]
    ev = D.evaluation_mask(p, start)
    dser = D.brier(preds["M1"], y) - D.brier(preds["M2"], y)
    excl = D.leave_one_episode_out(dser, p.episode[ev], y)
    b = {m: float(D.brier(v, y).mean()) for m, v in preds.items()}
    ll = {m: float(D.logloss(v, y).mean()) for m, v in preds.items()}
    cv = D.purged_cv(p, starts)
    ycv = p.y[p.labelled]
    return {
        "structure": gate, "generatorAdequacy": adq,
        "primary": {"statistic": "dBrier = mean(Brier(M1) - Brier(M2)) over evaluation rows", "brier": b,
                    "dBrier": res["observed"]["dBrier"], "crtP": res["p"]["dBrier"], "crtDraws": CRT_DRAWS,
                    "crtNullQuantiles": {q: float(np.quantile(res["null"]["dBrier"], float(q))) for q in ("0.05", "0.5", "0.95")},
                    "episodeExclusionSensitivity": excl,
                    "episodeExclusionNote": "evaluation-side only: an episode's positive rows are removed and dBrier "
                                            "recomputed WITHOUT refitting; not an out-of-sample validation"},
        "verdict": verdict_v2(True, res["observed"]["dBrier"], res["p"]["dBrier"], excl),
        "reportedOnly": {
            "dLogLoss": res["observed"]["dLogLoss"], "dLogLossCrtP": res["p"]["dLogLoss"], "logloss": ll,
            "brierSkillVsM0": {m: 1 - b[m] / b["M0"] for m in ("M1", "M2")},
            "blockBootstrap": D.block_bootstrap_ci(dser),
            "events": D.event_metrics(p, start, p.X[:, 2], starts),
            "calibration": {m: D.calibration(preds[m], y) for m in D.MODELS},
            "positiveRowsAreNotIndependentCrises": "23 positive rows belong to 5 episodes",
            "purgedLeaveOneEpisodeOutCvNotRealTime": {m: float(D.brier(v, ycv).mean()) for m, v in cv.items()}},
    }
