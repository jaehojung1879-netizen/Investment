"""A deterministic, real-universe continuing-name pool for the KR dividend
cross-validation `kr-terminal-action-reconstruction-v2` needs.

WHY THIS EXISTS. `alpha-opportunity-model-v3`'s original repair plan's own
dividend cross-validation control sample was 5 names, hand-picked ("all
long-tenured KOSPI dividend payers, not chosen from the 22 under study").
That is defensible as a first probe but too small to characterize
`alotMatter.json`'s real-world agreement rate against Yahoo dividend data —
this module draws a larger, deterministic sample from the repository's own
REAL KR universe snapshots (`ledger/universe/kr/krx-universe-*.jsonl.gz` on
`signal-history`) rather than a second hand-picked list, so the selection is
reproducible from data already in the repository and never a second set of
guesses about which names are "long-tenured".

SELECTION RULE. Every code that was ranked inside the top `top_rank` by
market cap on at least one snapshot date, EXCLUDING the 22 terminated
securities under study, ranked by how many snapshot dates it held that
rank (most persistent first, ticker code as the deterministic tiebreak).
This is the same "how many days a code spent in the top-N" measure
`build_kr_termination_inventory.membership_windows` already reads from this
data — reused as a ranking key here, not a different rule invented for
this module.

PREFERRED SHARES ARE EXCLUDED BY A NAME-PATTERN HEURISTIC, PUBLISHED. Korean
preferred-share tickers carry a suffix on the ISSUER's common-share name
(e.g. "삼성전자우", "현대차2우B") rather than a separate stock-code
convention this repository could rely on, so `is_likely_common_share` is a
heuristic, not a confirmed classification -- the selected pool is printed by
the caller precisely so a human can review which codes were kept before the
sample is used for anything.
"""
from __future__ import annotations

import re

DEFAULT_TOP_RANK = 120
DEFAULT_SAMPLE_SIZE = 25

# A Korean preferred-share name ends in "우" (優先, preferred), optionally
# followed by a class letter/digit ("우B", "2우B") -- corroborated from
# general KRX/DART naming convention knowledge, not from a confirmed
# structured field (no field in the KR universe snapshot rows states
# common/preferred directly). This is why callers are expected to publish
# the selected pool for review rather than trust this filter silently.
_PREFERRED_NAME_PATTERN = re.compile(r"[0-9]?우[A-Z]?$")


def is_likely_common_share(name: str | None) -> bool:
    if not name:
        return True
    return not _PREFERRED_NAME_PATTERN.search(str(name).strip())


def rank_persistence(rows: list[dict], *, top_rank: int = DEFAULT_TOP_RANK) -> dict[str, dict]:
    """code -> {"days": N, "name": most-recently-seen name} for every code
    ever ranked inside `top_rank` on any snapshot date in `rows`.

    `rows` must be the full KR universe snapshot rows (every ticker, every
    date) -- exactly the same "whole cross-section, never pre-filtered"
    requirement `membership_windows` already documents, for the same
    reason: a day's rank depends on every other name that day too.
    """
    persistence: dict[str, dict] = {}
    for row in rows:
        rank = row.get("rank")
        if rank is None or int(rank) > top_rank:
            continue
        code = str(row.get("ticker") or "").removesuffix(".KS")
        if not code:
            continue
        entry = persistence.setdefault(code, {"days": 0, "name": None})
        entry["days"] += 1
        if row.get("name"):
            entry["name"] = row["name"]
    return persistence


def select_continuing_sample(rows: list[dict], *, terminated_codes: set[str],
                             top_rank: int = DEFAULT_TOP_RANK,
                             sample_size: int = DEFAULT_SAMPLE_SIZE) -> list[dict]:
    """The `sample_size` most rank-persistent continuing common-share codes,
    excluding `terminated_codes`, deterministically ordered.

    Returns `[{"code":..., "name":..., "topRankDays":...}, ...]`, sorted by
    `(-topRankDays, code)` -- the same tiebreak-by-code determinism this
    repository's other selection code (`kr_termination_inventory.
    build_inventory`, `_select_scored`) already uses.
    """
    persistence = rank_persistence(rows, top_rank=top_rank)
    candidates = [
        {"code": code, "name": entry["name"], "topRankDays": entry["days"]}
        for code, entry in persistence.items()
        if code not in terminated_codes and is_likely_common_share(entry["name"])
    ]
    candidates.sort(key=lambda r: (-r["topRankDays"], r["code"]))
    return candidates[:sample_size]
