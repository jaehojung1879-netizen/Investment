"""Calendar-only upper bound. No source prices, states, returns, labels or lock."""
import json
from pathlib import Path
import sys

import engine


def calendar_bound(sessions, decisions):
    rows = [{"slot": i, "d": int(d), "e": int(d)+1, "end": int(d)+64,
             "final": int(d)+64, "stress": True} for i, d in enumerate(decisions)
            if int(d)+64 < len(sessions)]
    greedy = []
    for r in rows:
        if not greedy or r["e"] > greedy[-1]["end"]:
            greedy.append(r)
    training = greedy[:engine.MIN_TRAIN_SUPPORT]
    eligible = [r for r in rows if engine.support([rows[i] for i in engine.train_indices(rows, r)]) >= engine.MIN_TRAIN_SUPPORT]
    representatives = {}
    for r in eligible:
        representatives.setdefault(r["d"]//engine.BLOCK_SESSIONS, r)
    witness = sorted({r["slot"]: r for r in training + list(representatives.values())}.values(), key=lambda r: r["d"])
    def date(d):
        return str(sessions[d].date())
    return {"calendar_sessions": len(sessions), "weekly_decisions": len(decisions),
            "all_complete_mature_rows": len(rows), "upper_bound_blocks": len(representatives),
            "first_possible_test": date(eligible[0]["d"]) if eligible else None,
            "last_possible_test": date(eligible[-1]["d"]) if eligible else None,
            "first_bin": eligible[0]["d"]//126 if eligible else None,
            "last_bin": eligible[-1]["d"]//126 if eligible else None,
            "witness_stressed_rows": len(witness),
            "witness_support": engine.preflight_support(witness),
            "actual_stress_or_eligible_counts": None}


def main():
    # Import only the frozen calendar, never the historical market model.
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    import run
    manifest = run.read_json(Path(__file__).with_name("SOURCES.json"))
    path = "pipeline/replay_calendar.py"
    if run.sha(root/path) != manifest["repository_pins"][path]:
        raise ValueError("CALENDAR_CODE_CHANGED")
    from pipeline import replay_calendar as rc
    import pandas as pd
    from importlib.metadata import version
    if version("exchange-calendars") != "4.11.1" or version("korean-lunar-calendar") != "0.4.0":
        raise ValueError("PINNED_CALENDAR_REQUIRED")
    days = rc.sessions("1990-01-03", "2026-11-01", "KR")
    end = pd.Timestamp("2026-09-17")
    grid = days[days <= end]
    decisions = [i for i in range(len(grid)-1) if grid[i] >= pd.Timestamp("2007-01-01")
                 and grid[i].to_period("W") != days[i+1].to_period("W")]
    print(json.dumps(calendar_bound(grid, decisions), indent=2))


if __name__ == "__main__":
    main()
