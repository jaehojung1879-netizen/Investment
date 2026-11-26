"""Stage 2 v2 -- size and power of the P1 tests in synthetic worlds (independent audit A2).

No real value enters this module: prices, credit and drawdown episodes are all simulated. Each world has the shape of
the real sample (355 month-ends from 1997, 21 sessions a month, a 126-session = 6-month label window, FAST = 0 risk
set, yearly walk-forward refits, two early episodes used for training) and is accepted only if it passes the same
outcome-free structure gate as the real sample (>= 3 evaluation episodes, >= 100 evaluation rows).

    latent stress   s_t      AR(1), phi 0.9
    price features  gap_t = 0.05 - 0.06 s_t + 0.03 e1_t,   vol_t = exp(log 0.15 + 0.35 s_t + 0.15 e2_t)
    credit flag     environment-specific (below)
    episodes        start in a not-active month with probability sigmoid(a + h(X_t) [+ delta u_t]), last 3-30 months

Null environments (the label depends on the price features only; the flag adds nothing given X_t):

    S0  flag independent of everything (top 20% of a persistent AR(1)).
    S1  flag = top 20% of  1.2 vol_z - 0.8 gap_z + u_t  (u AR(1) 0.8, independent of s): strongly tied to X.
    S2  AUDIT COUNTEREXAMPLE TYPE: flag = 1[vol_t inside its 40-70% quantile band] (a deterministic non-monotone
        function of X) and the hazard is high exactly in that band; the linear M1 cannot represent it, the flag can.
    S3  S1 with a near-unit-root credit component (u AR 0.97).
    S4  regime change: S1 whose flag rate, X loading and hazard all change at mid-sample.
    S5  real-construction constraints: flag = 3-month change of the S1 latent above the expanding 80th percentile of
        all earlier changes (>= 12), a 7-month undefined block at the real 2016-11 position.

Alternatives:

    S6  S1 plus a credit-specific hazard term delta * u_t (information the price features do not have).

For each world: the v1 rotation p, the v2 CRT p (linear generator), the label-free generator adequacy gate, the
episode-exclusion sensitivity and the gated v2 verdict.

    python -m research.market_risk_discovery_v1.stage2v2_synthetic [--reps-null 1000 --reps-alt 300]
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import stage2_design as D
from . import stage2v2_crt as G

HERE = Path(__file__).resolve().parent
N_MONTHS = 355
SIM_CRT_DRAWS = 199
SIM_ADEQUACY_DRAWS = 199
SEED = 20261127
ENVIRONMENTS = ("S0", "S1", "S2", "S3", "S4", "S5")
DELTAS = (0.75, 1.5, 2.5)


def _ar(rng, n, phi):
    e = rng.normal(size=n)
    x = np.empty(n)
    x[0] = e[0]
    for t in range(1, n):
        x[t] = phi * x[t - 1] + np.sqrt(1 - phi ** 2) * e[t]
    return x


def _z(x):
    return (x - x.mean()) / x.std()


def _top(x, rate=0.2):
    return (x > np.quantile(x, 1 - rate)).astype(float)


def world(env: str, rng: np.random.Generator, delta: float = 0.0):
    n = N_MONTHS
    s = _ar(rng, n, 0.9)
    gap = 0.05 - 0.06 * s + 0.03 * _ar(rng, n, 0.7)
    vol = np.exp(np.log(0.15) + 0.35 * s + 0.15 * _ar(rng, n, 0.7))
    gz, vz = _z(gap), _z(vol)
    u = _ar(rng, n, 0.97 if env == "S3" else 0.8)
    defined = np.ones(n, dtype=bool)
    half = np.arange(n) >= n // 2
    hz = -4.4 + 0.9 * vz - 0.6 * gz
    if env == "S0":
        flag = _top(u)
    elif env in ("S1", "S3", "S6"):
        flag = _top(1.2 * vz - 0.8 * gz + u)
    elif env == "S2":
        lo, hi = np.quantile(vol, [0.40, 0.70])
        flag = ((vol > lo) & (vol <= hi)).astype(float)
        hz = -4.6 + 2.6 * flag
    elif env == "S4":
        lat = np.where(half, 0.5 * vz - 0.3 * gz, 1.6 * vz - 1.0 * gz) + u
        flag = np.where(half, lat > np.quantile(lat[half], 0.88), lat > np.quantile(lat[~half], 0.75)).astype(float)
        hz = np.where(half, -4.0 + 0.5 * vz - 0.3 * gz, -4.6 + 1.2 * vz - 0.8 * gz)
    elif env == "S5":
        lat = 1.2 * vz - 0.8 * gz + u
        ch = np.full(n, np.nan)
        ch[3:] = lat[3:] - lat[:-3]
        flag = np.zeros(n)
        for t in range(n):
            hist = ch[:t][~np.isnan(ch[:t])]
            if np.isnan(ch[t]) or len(hist) < 12:
                defined[t] = False
            else:
                flag[t] = float(ch[t] > np.quantile(hist, 0.8))
        block = slice(238, 245)
        defined[block] = False
    else:
        raise ValueError(env)
    if delta:
        hz = hz + delta * u
    return _rows(rng, n, gap, vol, flag, defined, 1.0 / (1.0 + np.exp(-hz)))


def _rows(rng, n, gap, vol, flag, defined, hazard):
    idx = 21 * np.arange(n)
    months = [f"{1997 + t // 12:04d}-{t % 12 + 1:02d}" for t in range(n)]
    active = np.zeros(n, dtype=bool)
    starts, t = {}, 0
    while t < n:
        if rng.random() < hazard[t]:
            sidx = int(idx[t] + 10)
            starts[f"E{months[t]}"] = sidx
            dur = int(rng.integers(3, 31))
            active[t + 1:t + 1 + dur] = True
            t = t + 1 + dur
        else:
            t += 1
    fast = (gap < 0).astype(int) + (vol > 0.25).astype(int)
    rows = []
    for t in range(n):
        if active[t] or fast[t] != 0 or not defined[t]:
            continue
        hit = [e for e, k in starts.items() if idx[t] < k <= idx[t] + D.HORIZON]
        y = 1 if hit else (0 if idx[t] + D.HORIZON <= idx[-1] else None)
        rows.append(D.Row(int(idx[t]), f"{months[t]}-28", float(gap[t]), float(vol[t]), float(flag[t]), y,
                          hit[0] if hit else None))
    seq = [(int(idx[t]), float(flag[t])) for t in range(n) if defined[t]]
    refits = D.refit_points([(f"{months[t]}-28", int(idx[t])) for t in range(n)])
    common = np.array([(not active[t]) and fast[t] == 0 for t in range(n) if defined[t]])
    keep = defined
    return {"panel": D.Panel(rows), "refits": refits, "seq": seq, "gap": gap[keep], "vol": vol[keep],
            "months": [m for m, d in zip(months, defined) if d], "common": common, "starts": starts}


def one(args) -> dict:
    env, delta, seed = args
    rng = np.random.default_rng(seed)
    for _ in range(200):                       # accept only worlds passing the outcome-free structure gate
        w = world(env, rng, delta)
        gate = D.structure_gate(w["panel"], w["refits"], w["seq"])
        if gate["pass"]:
            break
    else:
        return {"skipped": True}
    p = w["panel"]
    start = gate["start"]
    ev = D.evaluation_mask(p, start)
    y = p.y[ev]
    rot = D.primary(p, w["refits"], w["seq"])
    crt = G.crt(p, w["refits"], w["seq"], w["gap"], w["vol"], draws=SIM_CRT_DRAWS, seed=seed + 7)
    dser = D.brier(crt["preds"]["M1"], y) - D.brier(crt["preds"]["M2"], y)
    excl = D.leave_one_episode_out(dser, p.episode[ev], y)
    adq = G.adequacy(w["gap"], w["vol"], np.array([v for _, v in w["seq"]]), w["months"], w["common"],
                     draws=SIM_ADEQUACY_DRAWS, seed=seed + 11)
    d = float(dser.mean())
    excl_ok = all(v > 0 for v in excl.values())
    return {"skipped": False, "d": d, "rotP": rot["rotationP"], "crtP": crt["p"]["dBrier"], "adequate": adq["adequate"],
            "exclOk": excl_ok, "evalEpisodes": len(gate["evaluationEpisodes"]),
            "v1Support": d > 0 and rot["rotationP"] <= D.ALPHA and excl_ok,
            "v2Support": adq["adequate"] and d > 0 and crt["p"]["dBrier"] <= D.ALPHA and excl_ok}


def clopper_pearson(k: int, n: int, a: float = 0.05) -> list[float]:
    from scipy.stats import beta  # noqa: PLC0415
    lo = 0.0 if k == 0 else float(beta.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a / 2, k + 1, n - k))
    return [lo, hi]


def summarise(res: list[dict]) -> dict:
    res = [r for r in res if not r["skipped"]]
    n = len(res)

    def rate(key, sub=None):
        rr = res if sub is None else [r for r in res if sub(r)]
        k = sum(bool(r[key]) if key in ("adequate", "v1Support", "v2Support", "exclOk") else r[key] <= D.ALPHA
                for r in rr)
        return {"k": k, "n": len(rr), "rate": k / len(rr) if rr else None,
                "ci95": clopper_pearson(k, len(rr)) if rr else None}

    return {"reps": n, "rotationReject": rate("rotP"), "crtReject": rate("crtP"),
            "crtRejectGivenAdequate": rate("crtP", lambda r: r["adequate"]), "adequatePass": rate("adequate"),
            "v1SupportVerdict": rate("v1Support"), "v2SupportVerdict": rate("v2Support"),
            "meanEvaluationEpisodes": float(np.mean([r["evalEpisodes"] for r in res])),
            "positiveDBrierRate": float(np.mean([r["d"] > 0 for r in res]))}


def run(reps_null: int, reps_alt: int, workers: int = 4) -> dict:
    jobs = [(e, 0.0, SEED + 100000 * k + r) for k, e in enumerate(ENVIRONMENTS) for r in range(reps_null)]
    jobs += [("S6", d, SEED + 900000 + 10000 * k + r) for k, d in enumerate(DELTAS) for r in range(reps_alt)]
    with ProcessPoolExecutor(workers) as pool:
        res = list(pool.map(one, jobs, chunksize=2))
    out, i = {}, 0
    for e in ENVIRONMENTS:
        out[e] = summarise(res[i:i + reps_null])
        i += reps_null
    for d in DELTAS:
        out[f"S6_delta{d}"] = summarise(res[i:i + reps_alt])
        i += reps_alt
    return {"seed": SEED, "repsNull": reps_null, "repsAlt": reps_alt, "crtDraws": SIM_CRT_DRAWS,
            "adequacyDraws": SIM_ADEQUACY_DRAWS, "environments": out,
            "perReplication": [{"env": j[0], "delta": j[1], "seed": j[2], **r} for j, r in zip(jobs, res)]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps-null", type=int, default=1000)
    ap.add_argument("--reps-alt", type=int, default=300)
    ap.add_argument("--out", default=str(HERE / "evidence" / "stage2v2-null-validation.json"))
    a = ap.parse_args()
    out = run(a.reps_null, a.reps_alt)
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: {kk: (vv["rate"] if isinstance(vv, dict) and "rate" in vv else vv) for kk, vv in v.items()}
                      for k, v in out["environments"].items()}, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
