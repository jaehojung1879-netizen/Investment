"""Does the same replay, run twice, produce the same scorecard?

WHY THIS EXISTS. On 2026-09-05 the replay ran twice from the same commit
(38a4951) over the same 714 replay dates and published two different
scorecards: the challenger's CAGR moved 19.47% -> 16.77%, its max drawdown
-13.35% -> -9.85%, and the paired champion-minus-challenger difference
-0.702%p -> -0.530%p. The benchmark's own CAGR moved too (10.14% -> 9.57%),
which is what ruled out "the model changed" and pointed upstream.

THE CAUSE, MEASURED. Diffing the two ledger commits: 60 monthly signal files
from 2013-01 to 2018-03 were rewritten, not one existing row changed by a
single byte, and 250 rows were ADDED. Three tickers account for all of them --
HAR (215 rows), MHP (23), BMC (12) -- every one a delisted US name. So the
membership of a PAST cross-section depends on whether the price vendor served
those names during that particular run.

HOW 0.2% OF THE ROWS MOVED 84% OF THE SCORECARD. `block_dates` picks
non-overlapping evaluation blocks by scanning measurable dates forward
greedily. Add or drop one date and every block after it re-anchors. Measured
on the two runs: of 104 rolling evaluation points, 29 were shared -- an 84%
turnover in the dates the strategy was graded on, from a 250-row input change.

WHAT THIS MODULE ASSERTS. Not that the ledger never grows -- it must, daily.
The invariant is PREFIX STABILITY: every block already recorded must still be
there, with the same end date, and every past date's cross-section must still
hold the same names. New blocks may be appended after the last recorded one;
new dates may appear after the last recorded date. Anything else means the
past changed under us, and a scorecard computed on a past that changes is not
evidence about a strategy.

A divergence is a FAILURE, not a note. The two runs above both published, both
looked plausible, and nothing in either report said they disagreed.
"""
from __future__ import annotations

import hashlib

# Prefix intact, nothing appended.
STABLE = "SCHEDULE_STABLE"
# Prefix intact, new blocks/dates after the recorded end. The normal daily case.
EXTENDED = "SCHEDULE_EXTENDED"
# The recorded prefix changed. The past moved; the scorecard is not comparable.
DIVERGED = "SCHEDULE_DIVERGED"
# Nothing to compare against yet: first run, or the replay version was bumped.
NO_BASELINE = "NO_BASELINE_RECORDED"
# A new replay version is a new experiment, not a divergence in the old one.
VERSION_CHANGED = "REPLAY_VERSION_CHANGED"

FAILING = {DIVERGED}


def _digest(names) -> str:
    """A short, stable digest of one date's cross-section membership."""
    joined = "\x1f".join(sorted(str(name) for name in names))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def cross_section_fingerprint(signals: list[dict]) -> dict[str, dict]:
    """Per replay date: how many names, and which ones (as a digest).

    The names themselves are not stored -- 714 dates times ~180 names would
    dwarf the report it lives in. The digest is enough to prove a date's
    membership changed; the ledger's own history names the tickers, which is
    how HAR, MHP and BMC were identified.
    """
    by_date: dict[str, set] = {}
    for row in signals:
        date = row.get("date")
        ticker = row.get("ticker")
        if date is None or ticker is None:
            continue
        by_date.setdefault(str(date), set()).add(str(ticker))
    return {date: {"names": len(names), "digest": _digest(names)}
            for date, names in sorted(by_date.items())}


def schedule_fingerprint(blocks: list[dict]) -> list[dict]:
    """The evaluation calendar, as the pairs that must not move.

    Both halves matter. A block's entry date says when the strategy was
    graded; its end date says over what. `shared_block_dates` takes the LATER
    of the two selectors' end dates, so an end date can move even when the
    entry date does not -- and that alone shifts every later block.
    """
    out = []
    for block in blocks:
        date, end = block.get("date"), block.get("endDate")
        if date is None or end is None:
            continue
        out.append({"date": str(date), "endDate": str(end)})
    return sorted(out, key=lambda row: row["date"])


def compare_schedule(recorded: list[dict] | None,
                     current: list[dict]) -> dict:
    """Prefix stability for the evaluation calendar."""
    if not recorded:
        return {"verdict": NO_BASELINE, "recordedBlocks": 0,
                "currentBlocks": len(current)}
    recorded = schedule_fingerprint(recorded)
    current = schedule_fingerprint(current)
    last_recorded = recorded[-1]["date"]
    # Only the recorded span is under test. Blocks after it are new work, and
    # holding new work to a baseline that predates it would fail every day.
    prefix = [row for row in current if row["date"] <= last_recorded]
    for index, expected in enumerate(recorded):
        actual = prefix[index] if index < len(prefix) else None
        if actual != expected:
            return {"verdict": DIVERGED,
                    "recordedBlocks": len(recorded),
                    "currentBlocks": len(current),
                    "firstDivergenceIndex": index,
                    "expected": expected, "actual": actual,
                    "reason": ("a block that was already published moved; the "
                               "greedy schedule re-anchors from the first "
                               "change, so every later block is suspect too")}
    if len(prefix) != len(recorded):
        return {"verdict": DIVERGED,
                "recordedBlocks": len(recorded), "currentBlocks": len(current),
                "firstDivergenceIndex": len(recorded),
                "expected": None, "actual": prefix[len(recorded)],
                "reason": "a block appeared inside the already-published span"}
    return {"verdict": EXTENDED if len(current) > len(recorded) else STABLE,
            "recordedBlocks": len(recorded), "currentBlocks": len(current),
            "appendedBlocks": len(current) - len(recorded)}


def compare_cross_sections(recorded: dict | None, current: dict) -> dict:
    """Prefix stability for who was in the universe on each past date."""
    if not recorded:
        return {"verdict": NO_BASELINE, "recordedDates": 0,
                "currentDates": len(current)}
    last_recorded = max(recorded)
    drifted = []
    for date, row in sorted(recorded.items()):
        now = current.get(date)
        if now is None:
            drifted.append({"date": date, "was": row["names"], "now": None})
        elif now.get("digest") != row.get("digest"):
            drifted.append({"date": date, "was": row["names"],
                            "now": now.get("names")})
    # A date that never existed in the baseline but sits inside its span is the
    # same disease as a changed one: the past gained a row after publication.
    for date in sorted(current):
        if date <= last_recorded and date not in recorded:
            drifted.append({"date": date, "was": None,
                            "now": current[date]["names"]})
    if drifted:
        drifted.sort(key=lambda row: row["date"])
        net = sum((row["now"] or 0) - (row["was"] or 0) for row in drifted)
        return {"verdict": DIVERGED, "recordedDates": len(recorded),
                "currentDates": len(current), "driftedDates": len(drifted),
                "netNameChange": net, "firstDriftedDate": drifted[0]["date"],
                "driftedSample": drifted[:10],
                "reason": ("a past date's cross-section changed membership; "
                           "delisted names served intermittently by the price "
                           "vendor are the known cause")}
    added = sum(1 for date in current if date > last_recorded)
    return {"verdict": EXTENDED if added else STABLE,
            "recordedDates": len(recorded), "currentDates": len(current),
            "appendedDates": added}


def assess(previous: dict | None, *, schedule: list[dict],
           cross_section: dict, replay_version: str | None) -> dict:
    """The determinism block for this run's report.

    `previous` is the report the last run published. It is the only baseline
    that exists -- the ledger records outcomes, not the calendar they were
    graded on, which is why two runs could disagree without anything noticing.
    """
    block = {
        "checked": True,
        "replayVersion": replay_version,
        "schedule": schedule,
        "crossSection": cross_section,
    }
    prior = ((previous or {}).get("replayDeterminism") or {}) if previous else {}
    prior_version = prior.get("replayVersion")
    if not prior or not prior.get("schedule"):
        block["verdict"] = NO_BASELINE
        block["scheduleCheck"] = {"verdict": NO_BASELINE}
        block["crossSectionCheck"] = {"verdict": NO_BASELINE}
    elif prior_version != replay_version:
        block["verdict"] = VERSION_CHANGED
        block["previousReplayVersion"] = prior_version
        block["scheduleCheck"] = {"verdict": VERSION_CHANGED}
        block["crossSectionCheck"] = {"verdict": VERSION_CHANGED}
    else:
        sched = compare_schedule(prior.get("schedule"), schedule)
        cross = compare_cross_sections(prior.get("crossSection"), cross_section)
        block["scheduleCheck"] = sched
        block["crossSectionCheck"] = cross
        block["verdict"] = (DIVERGED if DIVERGED in (sched["verdict"],
                                                     cross["verdict"])
                            else EXTENDED if EXTENDED in (sched["verdict"],
                                                          cross["verdict"])
                            else STABLE)
    block["reproducible"] = block["verdict"] not in FAILING
    block["noteKo"] = (
        "같은 코드·같은 리플레이 버전으로 다시 돌렸을 때 이미 발표된 평가 블록과 "
        "과거 단면 구성이 그대로인지 봅니다. 원장이 자라는 것은 정상이므로 마지막 "
        "기록 이후에 붙는 것은 통과이고, 이미 발표된 구간이 바뀌면 실패입니다. "
        "2026-09-05에 같은 커밋의 두 실행이 서로 다른 성적표를 냈고 "
        "(challenger CAGR 19.47%→16.77%, MDD −13.35%→−9.85%), 원인은 상장폐지 "
        "종목 HAR·MHP·BMC가 과거 단면에 들쭉날쭉 들어온 것이었습니다.")
    return block
