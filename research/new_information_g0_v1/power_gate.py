"""Outcome-blind normalized power gate. Inputs are design assumptions, not returns."""
from __future__ import annotations

import argparse
import json
import math
from statistics import NormalDist


def normalized_mde(n_effective: float, alpha: float = 0.05,
                   power: float = 0.80, family_size: int = 1) -> float:
    """Approximate two-sided detectable paired mean in units of residual SD.

    A normal approximation only: correlated events, multiple tests and clustered
    standard errors can make actual power much worse. Never infer n_effective
    from raw count of overlapping event-days.
    """
    if not (n_effective > 1 and 0 < alpha < 1 and 0.5 < power < 1
            and isinstance(family_size, int) and family_size >= 1):
        raise ValueError("Invalid n_eff, alpha, power or family_size")
    z = NormalDist().inv_cdf(1 - alpha / (2 * family_size))
    zpower = NormalDist().inv_cdf(power)
    return (z + zpower) / math.sqrt(n_effective)


def scenarios() -> list[dict]:
    return [
        {"assumed_independent_events": n,
         "minimum_detectable_effect_in_residual_sd":
             round(normalized_mde(n), 4)}
        for n in (10, 20, 40, 80, 160, 320)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-effective", type=float)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--power", type=float, default=0.80)
    parser.add_argument("--family-size", type=int, default=1)
    a = parser.parse_args()
    out = {
        "status": "POWER_DESIGN_ONLY_NO_RETURNS",
        "independence_uncertainty": "n_eff must be independently reviewed",
        "conversion_to_percentage_points": "requires ex-ante residual SD not provided",
    }
    if a.n_effective is None:
        out["hypothetical_scenarios"] = scenarios()
    else:
        out["assumed_n_effective"] = a.n_effective
        out["normalized_mde"] = normalized_mde(
            a.n_effective, alpha=a.alpha,
            power=a.power, family_size=a.family_size)
    print(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
