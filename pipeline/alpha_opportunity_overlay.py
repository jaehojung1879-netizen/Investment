"""Bounded DART overlay eligibility. Never shorten the core KR history."""
from __future__ import annotations

import pandas as pd

from . import regional_alpha_features as sources
from . import replay_calendar as calendar
from .alpha_opportunity_evaluation import overlay_sample_gate


def calendar_gate(spec):
    """An outcome-free upper bound; reject impossible samples before labels.

    This v1 snapshot has fewer than 112 weekly dates even before maturity and
    lookback losses. Its sealed contract cannot reach overlay training. More
    history requires a NEW snapshot/version, not silently relaxed requirements.
    """
    cfg = spec["ownershipOverlay"]
    start, end = cfg["receiptWindow"]
    through = min(end, cfg["priceCutoff"])
    sessions = calendar.sessions(start, through, "KR")
    weekly = sources.weekly_grid(start, through, "KR")
    eligible = [d for d in weekly
                if sessions.searchsorted(pd.Timestamp(d)) >= cfg["lookbackSessions"]]
    # At most these dates could be evaluated. Do not open prices or outcomes.
    possible_eval = max(0, len(eligible)-cfg["minimumTrainingDates"])
    result = overlay_sample_gate(training_dates=min(len(eligible), cfg["minimumTrainingDates"]),
        evaluation_dates=possible_eval, events=0, issuers=0, spec=spec)
    for field in ("trainingDates", "evaluationDates", "events", "issuers"):
        result.pop(field)
    result.update(modelId=cfg["modelId"], weeklyDateUpperBound=len(eligible),
                  evaluationDateUpperBound=possible_eval,
                  eventCountsMeasured=False, historicalLabelsComputed=False,
                  reason="CALENDAR_TOO_SHORT_BEFORE_LABEL_MATURITY_OR_EVENT_FILTERS")
    if possible_eval >= cfg["minimumEvaluationDates"]:
        # The runner supports exactly the sealed short snapshot. Future extra
        # observations require a reviewed implementation/version, never an
        # automatic historical experiment on an expanded window.
        raise ValueError("NEW_OWNERSHIP_SNAPSHOT_REQUIRES_NEW_STUDY_VERSION")
    return result
