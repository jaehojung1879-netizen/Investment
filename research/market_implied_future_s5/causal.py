"""Design-only expected variance reference. Inputs require independently proven clocks."""
import math
from itertools import pairwise

from .foundation import _utc

DECAY = .94


def ewma_expected_daily_variation(observations, *, decision_at):
    """Fixed EWMA over measured daily variance values available before decision.

    observations are ordered (measurement_end, first_available_at, daily decimal variance).
    A record at or after decision time is rejected, including a fresh outcome.
    """
    decision = _utc(decision_at)
    rows = [(_utc(end), _utc(available), variance) for end, available, variance in observations]
    if len(rows) < 22 or any(a[0] >= b[0] for a, b in pairwise(rows)):
        raise ValueError("NEED_22_OR_MORE_STRICTLY_ORDERED_DAILY_OBSERVATIONS")
    if any(end > available or available >= decision for end, available, _ in rows):
        raise ValueError("OBSERVATION_CLOCK_INELIGIBLE")
    if any(isinstance(value, bool) or not math.isfinite(value) or value < 0 for _, _, value in rows):
        raise ValueError("DAILY_VARIATION_INELIGIBLE")
    variance = sum(row[2] for row in rows[:22]) / 22
    for _, _, value in rows[22:]:
        variance = DECAY * variance + (1 - DECAY) * value
    return variance


def integrated_q_minus_expected_p(w30, w93, expected_daily_variation, scheduled_sessions):
    """30-to-93-day integrated decimal variance comparison, without clipping."""
    if (
        isinstance(scheduled_sessions, bool) or not isinstance(scheduled_sessions, int) or scheduled_sessions <= 0
        or any(isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in (w30, w93, expected_daily_variation))
    ):
        raise ValueError("INPUT_VARIATION_OR_HORIZON_INVALID")
    return w93 - w30 - expected_daily_variation * scheduled_sessions
