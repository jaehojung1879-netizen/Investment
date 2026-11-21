"""Outcome-free minimum-detectable-effect (MDE) arithmetic for the priority decisions.

Every input here is a DESIGN ASSUMPTION or an outcome-free count; nothing reads a
return. The numbers are planning gates, not results. A real study replaces the
assumed volatilities with pre-event residual volatility measured strictly before
each signal date and the assumed event counts with parsed, receipt-dated events.

Two estimands are kept apart on purpose:

* time-series: a single portfolio's mean excess over its ETF, one observation per
  year of history, SE = TE / sqrt(years);
* event-level: the mean abnormal return of N events, inflated by a calendar
  clustering design effect D (events in the same weeks share market shocks),
  SE = sigma * sqrt(D / N).
"""

from __future__ import annotations

import json
import math
from statistics import NormalDist

_N = NormalDist()


def critical_multiplier(alpha: float = 0.05, power: float = 0.80, family: int = 1) -> float:
    """Two-sided z for the first Holm step of a ``family``-sized family, plus z for power."""
    if not 0 < alpha < 1 or not 0 < power < 1 or family < 1:
        raise ValueError("alpha and power must lie in (0, 1) and family >= 1")
    return _N.inv_cdf(1 - alpha / family / 2) + _N.inv_cdf(power)


def mde_time_series(tracking_error_pct: float, years: float, **kw) -> float:
    """MDE in pp/yr of a portfolio's mean annual excess over its benchmark."""
    if tracking_error_pct <= 0 or years <= 0:
        raise ValueError("tracking error and years must be positive")
    return critical_multiplier(**kw) * tracking_error_pct / math.sqrt(years)


def years_needed(tracking_error_pct: float, alpha_pp: float, **kw) -> float:
    """Years of independent record needed before ``alpha_pp`` is detectable."""
    if alpha_pp <= 0:
        raise ValueError("alpha must be positive")
    return (critical_multiplier(**kw) * tracking_error_pct / alpha_pp) ** 2


def mde_event(sigma_pct: float, events: int, design_effect: float = 2.0, **kw) -> float:
    """MDE in pp of the mean per-event abnormal return over one horizon."""
    if sigma_pct <= 0 or events < 2 or design_effect < 1:
        raise ValueError("sigma > 0, events >= 2, design effect >= 1 required")
    return critical_multiplier(**kw) * sigma_pct * math.sqrt(design_effect / events)


def gate(mde_pp: float, minimum_economic_effect_pp: float) -> str:
    """Registered pre-outcome gate: run only if the design can see the effect that matters."""
    if mde_pp <= minimum_economic_effect_pp:
        return "POWER_PASS"
    if mde_pp <= 2 * minimum_economic_effect_pp:
        return "POWER_MARGINAL_PROSPECTIVE_OR_BROADER_UNIVERSE_FIRST"
    return "POWER_NO_GO"


def planning_table(assumptions: dict) -> dict:
    """Recompute every planning row in the decisions file from its stated assumptions."""
    kw = {"alpha": assumptions["alpha"], "power": assumptions["power"]}
    out = {"timeSeries": [], "events": []}
    for row in assumptions["timeSeries"]:
        m = mde_time_series(row["trackingErrorPct"], row["years"], **kw)
        out["timeSeries"].append({**row, "mdePpPerYear": round(m, 2),
                                  "yearsFor3ppAlpha": round(years_needed(row["trackingErrorPct"], 3.0, **kw), 1)})
    for row in assumptions["events"]:
        m = mde_event(row["sigmaPct"], row["events"], row["designEffect"],
                      family=row.get("family", 1), **kw)
        out["events"].append({**row, "mdePp": round(m, 2),
                              "gate": gate(m, row["minimumEconomicEffectPp"])})
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    from pathlib import Path

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("decisions", nargs="?", type=Path,
                   default=Path(__file__).with_name("priority-decisions-v1.json"))
    args = p.parse_args(argv)
    spec = json.loads(args.decisions.read_text(encoding="utf-8"))
    print(json.dumps(planning_table(spec["powerPlanning"]["assumptions"]), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
