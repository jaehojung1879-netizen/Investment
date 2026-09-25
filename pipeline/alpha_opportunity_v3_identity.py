"""Security-identity classification for alpha-opportunity-model-v3. Research only.

Identity is part of the survivorship problem. A symbol is not a security: a
row can carry a company name in its Symbol column, a company can change its
ticker, and a ticker can be reused by an unrelated issuer years later. Each of
those changes what "this member has / lacks a price history" means.

Nothing here maps a symbol on a guess. A historical symbol is joined to
another only on explicit, sealed evidence, and every join records its basis:

* SAME_CIK            both rows carry the same SEC CIK and the two symbols are
                      never listed in the same snapshot (share-class pairs such
                      as GOOG/GOOGL share a CIK and ARE co-listed, so they never
                      qualify);
* PREVIOUSLY_ANNOTATION  the successor's own upstream row says "(Previously X)";
* IDENTICAL_NAME      the successor enters in exactly the snapshot the
                      predecessor leaves, never co-listed, same security name.

An acquired or delisted company is never joined to its acquirer, and a panel
that starts after a member left is never read as that member's history.
Everything else stays UNRESOLVED and is counted, not dropped.
"""
from __future__ import annotations

import re

TICKER = re.compile(r"^[A-Z0-9][A-Z0-9\-]{0,7}(\.KS)?$")

SAME_SECURITY_RENAME = "SAME_SECURITY_RENAME"
IDENTIFIER_MALFORMED_RESOLVED = "IDENTIFIER_MALFORMED_RESOLVED"
IDENTIFIER_MALFORMED_UNRESOLVED = "IDENTIFIER_MALFORMED_UNRESOLVED"
TICKER_REUSE_DIFFERENT_ISSUER = "TICKER_REUSE_DIFFERENT_ISSUER"
ACQUIRED_OR_MERGED_TERMINATED = "ACQUIRED_OR_MERGED_TERMINATED"
TERMINATED_IN_PANEL = "TERMINATED_IN_PANEL"
REMOVED_FROM_INDEX_STILL_TRADING = "REMOVED_FROM_INDEX_STILL_TRADING"
PANEL_PARTIAL_OWN_HISTORY = "PANEL_PARTIAL_OWN_HISTORY"
DEPARTED_NO_PANEL_REASON_UNRESOLVED = "DEPARTED_NO_PANEL_REASON_UNRESOLVED"
CURRENT_OWN_PANEL = "CURRENT_MEMBER_OWN_PANEL"
CURRENT_PANEL_LATE_START = "CURRENT_MEMBER_PANEL_LATE_START"
CURRENT_NO_PANEL = "CURRENT_MEMBER_NO_PANEL"
CATEGORIES = (SAME_SECURITY_RENAME, IDENTIFIER_MALFORMED_RESOLVED, IDENTIFIER_MALFORMED_UNRESOLVED,
              TICKER_REUSE_DIFFERENT_ISSUER, ACQUIRED_OR_MERGED_TERMINATED, TERMINATED_IN_PANEL,
              REMOVED_FROM_INDEX_STILL_TRADING, PANEL_PARTIAL_OWN_HISTORY,
              DEPARTED_NO_PANEL_REASON_UNRESOLVED, CURRENT_OWN_PANEL, CURRENT_PANEL_LATE_START,
              CURRENT_NO_PANEL)
# Categories whose member-dates cannot be priced from the member's OWN history
# under any sealed evidence: the survivorship set proper.
UNPRICEABLE_DEPARTED = frozenset({TICKER_REUSE_DIFFERENT_ISSUER, ACQUIRED_OR_MERGED_TERMINATED,
                                  DEPARTED_NO_PANEL_REASON_UNRESOLVED})


def well_formed(symbol):
    return bool(TICKER.match(symbol))


def _norm_name(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def resolve_malformed(snapshots, index, key):
    """A malformed key resolves to T only if T is absent where the key sits and
    present in BOTH neighbouring snapshots, and the key names T explicitly
    (T is a token of the key) or equals T's own recorded name next door."""
    members = [set(s["members"]) for s in snapshots]
    where = [i for i, m in enumerate(members) if key in m]
    candidates = None
    for i in where:
        if i == 0 or i + 1 >= len(snapshots):
            return None
        options = (members[i - 1] & members[i + 1]) - members[i]
        options = {t for t in options if well_formed(t)}
        candidates = options if candidates is None else candidates & options
    if not candidates:
        return None
    tokens = set(re.findall(r"[A-Z0-9\-]+", key.replace(".", "-")))
    named = {t for t in candidates if t in tokens}
    if not named and index:
        for t in candidates:
            for i in where:
                for j in (i - 1, i + 1):
                    row = index[j].get(t)
                    if row and _norm_name(row[1]) and _norm_name(row[1]) == _norm_name(key):
                        named.add(t)
    return next(iter(named)) if len(named) == 1 else None


def find_renames(snapshots, index):
    """Predecessor -> (successor, basis). Evidence only; never a guess."""
    members = [set(s["members"]) for s in snapshots]
    present = {}
    for i, m in enumerate(members):
        for t in m:
            present.setdefault(t, []).append(i)
    out = {}
    for s, idx in present.items():
        last = max(idx)
        if last + 1 >= len(snapshots) or not well_formed(s) or not index:
            continue
        s_row = index[last].get(s)
        s_ciks = {index[i][s][2] for i in idx if index[i].get(s) and index[i][s][2]}
        found = []
        for t, tidx in present.items():
            # The successor must stand in the snapshot the predecessor first
            # misses, and the two may never be co-listed (share classes are).
            if t == s or not well_formed(t) or set(idx) & set(tidx) or (last + 1) not in tidx:
                continue
            t_first = index[last + 1].get(t)
            t_ciks = {index[i][t][2] for i in tidx if index[i].get(t) and index[i][t][2]}
            if s_ciks and t_ciks and s_ciks & t_ciks:
                found.append((t, "SAME_CIK"))
            elif t_first and re.search(r"previously\s+" + re.escape(s.lower()) + r"\b",
                                       (t_first[0] + " " + t_first[1]).lower().replace(".", "-")):
                found.append((t, "PREVIOUSLY_ANNOTATION"))
            elif (s_row and t_first and _norm_name(s_row[1])
                  and _norm_name(s_row[1]) == _norm_name(t_first[1])):
                found.append((t, "IDENTICAL_NAME"))
        if len(found) == 1:
            out[s] = {"successor": found[0][0], "basis": found[0][1]}
        elif len(found) > 1:
            out[s] = {"successor": None, "basis": "AMBIGUOUS", "candidates": sorted(found)}
    return out


def classify(snapshots, avail, *, index=None, corporate_actions=(), through, termination_gap_days=45):
    """{symbol: record} for every symbol in any snapshot, plus a resolution map.

    ``index`` is a per-snapshot {symbol: (rawSymbol, name, cik)} list aligned
    with ``snapshots`` (US); None where no identity columns exist (KR codes).
    """
    import pandas as pd
    snapshots = sorted(snapshots, key=lambda s: s["date"])
    members = [set(s["members"]) for s in snapshots]
    current = members[-1]
    first_member, last_member = {}, {}
    for s, m in zip(snapshots, members):
        for t in m:
            first_member.setdefault(t, s["date"])
            last_member[t] = s["date"]
    acquired = {a["ticker"]: a for a in corporate_actions}
    renames = find_renames(snapshots, index)
    cutoff = pd.Timestamp(through)

    def closes(t):
        a = avail.get(t) or {}
        c = [d for d, (ok, _) in a.items() if ok]
        return (min(c), max(c)) if c else (None, None)

    records, malformed_map = {}, {}
    for t in sorted(first_member):
        first, last = closes(t)
        rec = {"firstMember": first_member[t], "lastMember": last_member[t], "current": t in current,
               "panelFirstClose": first, "panelLastClose": last, "flags": []}
        if not well_formed(t):
            target = resolve_malformed(snapshots, index, t)
            rec["category"] = IDENTIFIER_MALFORMED_RESOLVED if target else IDENTIFIER_MALFORMED_UNRESOLVED
            rec["resolvedTo"] = target
            if target:
                malformed_map[t] = target
            records[t] = rec
            continue
        if first is not None and first > last_member[t]:
            rec["flags"].append("PANEL_POSTDATES_MEMBERSHIP")
        own = first is not None and first <= last_member[t]
        rename = renames.get(t)
        if rename and rename.get("successor"):
            rec["category"], rec["successor"], rec["basis"] = SAME_SECURITY_RENAME, rename["successor"], rename["basis"]
        elif t in current:
            rec["category"] = (CURRENT_NO_PANEL if first is None else
                               CURRENT_PANEL_LATE_START if first > first_member[t] else CURRENT_OWN_PANEL)
        elif t in acquired and not own:
            rec["category"], rec["evidence"] = ACQUIRED_OR_MERGED_TERMINATED, acquired[t].get("type")
        elif first is not None and not own:
            rec["category"] = TICKER_REUSE_DIFFERENT_ISSUER
        elif first is None:
            rec["category"] = DEPARTED_NO_PANEL_REASON_UNRESOLVED
        elif (cutoff - pd.Timestamp(last)).days > termination_gap_days:
            rec["category"] = TERMINATED_IN_PANEL
        elif first > first_member[t]:
            rec["category"] = PANEL_PARTIAL_OWN_HISTORY
        else:
            rec["category"] = REMOVED_FROM_INDEX_STILL_TRADING
        if rename and not rename.get("successor"):
            rec["flags"].append("RENAME_AMBIGUOUS")
            rec["renameCandidates"] = rename["candidates"]
        records[t] = rec
    return records, malformed_map


def pricing_symbol(symbol, records, *, depth=0):
    """The symbol whose sealed panel may price `symbol`, or None.

    A symbol's OWN panel qualifies when it starts no later than the symbol's
    last membership date. For a SAME_SECURITY_RENAME predecessor the successor
    chain is the same security, so among its qualifying panels the one with the
    earliest first close is used. A reused ticker's later panel never prices
    the old member, and an acquired or delisted company is never priced from an
    acquirer or any other issuer.
    """
    rec = records.get(symbol)
    if rec is None or depth > 5 or rec["category"] == IDENTIFIER_MALFORMED_UNRESOLVED:
        return None
    first = rec["panelFirstClose"]
    own = symbol if first is not None and first <= rec["lastMember"] else None
    if rec["category"] != SAME_SECURITY_RENAME:
        return own
    succ = pricing_symbol(rec["successor"], records, depth=depth + 1)
    options = [(records[x]["panelFirstClose"], x) for x in (own, succ) if x is not None]
    return min(options)[1] if options else None


def normalized_snapshots(snapshots, malformed_map):
    """Replace ONLY evidence-resolved malformed keys; unresolved ones stay as-is
    (and are counted as IDENTITY_UNRESOLVED member-dates, never as tickers)."""
    out = []
    for s in snapshots:
        members = sorted({malformed_map.get(t, t) for t in s["members"]})
        out.append({**s, "members": members})
    return out
