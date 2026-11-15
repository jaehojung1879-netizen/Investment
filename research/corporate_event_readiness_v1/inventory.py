"""Inspectable metadata inventory; filing density is never independent sample size."""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def fixed_sample_readiness(rows: list[dict]) -> dict:
    """Summarize actual parser fixtures without inventing independent events.

    Parsing, navigation-chain links and source admission are separate stages.
    Existing parser eligibility flags and blockers remain authoritative; an
    issuer/date/title match never merges different economic decisions here.
    """
    unique, owners, duplicates = {}, {}, 0
    for row in rows:
        key = (row['issuer_id'], row['receipt_no'])
        if owners.setdefault(row['receipt_no'], row['issuer_id']) != row['issuer_id']:
            raise ValueError('RECEIPT_ISSUER_CONFLICT')
        if key in unique:
            if unique[key] != row:
                raise ValueError('CONFLICTING_FIXED_RECEIPT')
            duplicates += 1
        unique[key] = row
    values = list(unique.values())
    reasons, years, families, industries = Counter(), {}, {}, {}
    for row in values:
        blockers = sorted(set(row.get('quarantine_reasons', []) + row.get('eligibility_blockers', [])))
        reasons.update(blockers)
        for buckets, label in ((years, row['receipt_date'][:4]),
                               (families, row.get('family') or 'UNCLASSIFIED'),
                               (industries, row.get('industry_pit') or 'UNRESOLVED')):
            group = buckets.setdefault(label, {'retainedVersions': 0, 'sourceQualified': 0})
            group['retainedVersions'] += 1
            # This packet has no source-admission authority. Even a forged status
            # cannot erase missing contemporaneous source/security evidence.
            if (not blockers and row.get('source_version_verified') is True
                    and row.get('pit_available_at') and row.get('tradable_security_at_event')
                    and row.get('industry_pit')):
                group['sourceQualified'] += 1
    complete = sum(v['sourceQualified'] for v in years.values())
    return {
        'scope': 'PURPOSIVE_FIXED_PARSER_FIXTURES_NOT_POPULATION_SAMPLE',
        'retainedVersions': len(values), 'duplicateReceiptRowsRemoved': duplicates,
        'issuerCandidates': len({r['issuer_id'] for r in values}),
        'sourceQualifiedReceiptCandidates': complete,
        'sourceBlockedReceipts': len(values) - complete,
        'byYear': dict(sorted(years.items())), 'byFamily': dict(sorted(families.items())),
        'byPitIndustry': dict(sorted(industries.items())),
        'blockerCounts': dict(sorted(reasons.items())),
        'uniqueEconomicEvents': None, 'independentN': None, 'mde': None,
        'mdeReason': 'VERIFIED_COHORT_INDEPENDENCE_AND_VARIANCE_ABSENT',
        'hypothesisReadiness': 'SOURCE_BLOCKED' if not complete else 'INDEPENDENT_SOURCE_REVIEW_REQUIRED',
        'returnsRead': 0, 'outcomeExecutionAuthorized': False,
    }


def sample_inventory(rows: list[dict], sessions: list[str] | None = None) -> dict:
    """Rows are disclosure versions, uniquely keyed by issuer and receipt.

    No amount/revenue/price/return values are read. A missing industry remains
    unclassified. Chains are counted only if explicitly resolved upstream;
    otherwise no unique-event or independent-N claim is made.
    """
    unique = {}
    duplicates = 0
    for row in rows:
        key = (row["issuer_id"], row["receipt_id"])
        if key in unique:
            if unique[key] != row:
                raise ValueError("CONFLICTING_RECEIPT_VERSION")
            duplicates += 1
        unique[key] = dict(row)
    values = list(unique.values())
    issuers = Counter(r["issuer_id"] for r in values)
    years, weeks, families, industries = Counter(), Counter(), Counter(), Counter()
    statuses, relations = Counter(), Counter()
    for row in values:
        day = date.fromisoformat(row["received_date"])
        years[str(day.year)] += 1
        week = day.isocalendar()
        weeks[f"{week.year}-W{week.week:02d}"] += 1
        families[row.get("family") or "UNCLASSIFIED"] += 1
        industries[row.get("industry_pit") or "UNRESOLVED"] += 1
        statuses[row.get("parse_status") or "NOT_PARSED"] += 1
        relations[row.get("relation_type") or "UNRESOLVED"] += 1
    chain_ids = {(r["issuer_id"], r["chain_id"]) for r in values if r.get("chain_id")}
    count = len(values)
    out = {
        "evidence_class": "DISCLOSURE_METADATA_INVENTORY_NOT_EMPIRICAL_ADMISSION",
        "filing_versions": count, "duplicate_rows_removed": duplicates,
        "by_issuer": dict(sorted(issuers.items())), "by_year": dict(sorted(years.items())),
        "by_iso_week": dict(sorted(weeks.items())), "by_family": dict(sorted(families.items())),
        "by_pit_industry": dict(sorted(industries.items())),
        "parse_status": dict(sorted(statuses.items())), "relation_type": dict(sorted(relations.items())),
        "repeat_issuer_filing_share": _ratio(sum(n for n in issuers.values() if n > 1), count),
        "max_same_week_filing_share": _ratio(max(weeks.values(), default=0), count),
        "correction_share": _ratio(relations["CORRECTION"], count),
        "termination_share": _ratio(relations["TERMINATION"], count),
        "quarantine_share": _ratio(statuses["QUARANTINED"], count - statuses["NOT_PARSED"]),
        "error_share": None,
        "unparsed_share": _ratio(statuses["NOT_PARSED"], count),
        "unresolved_chain_share": _ratio(sum(not r.get("chain_id") for r in values), count),
        "resolved_chain_count": len(chain_ids),
        "unique_events": len(chain_ids) if count and all(r.get("chain_id") for r in values) else None,
        "independent_observations": None, "mde": None, "returns_read": 0,
        "overlap": {"H126": None, "H252": None},
        "overlap_reason": "VERIFIED_TRADING_SESSION_CALENDAR_REQUIRED",
    }
    if sessions is None:
        return out
    for session in sessions:
        date.fromisoformat(session)
    if sessions != sorted(set(sessions)):
        raise ValueError("ORDERED_UNIQUE_SESSIONS_REQUIRED")
    # Only original decisions enter potential-window overlap. Follow-ups do not
    # become new independent events, and unresolved chains block event estimates.
    originals = [r for r in values if r.get("relation_type") == "ORIGINAL"]
    if not originals or not sessions:
        out["overlap_reason"] = "NO_MEASURABLE_ORIGINAL_WINDOWS"
        return out
    if any(not r.get("chain_id") for r in originals):
        out["overlap_reason"] = "UNRESOLVED_ORIGINAL_CHAINS"
        return out
    original_chains = [(r["issuer_id"], r["chain_id"]) for r in originals]
    if len(original_chains) != len(set(original_chains)):
        out["overlap_reason"] = "MULTIPLE_ORIGINALS_IN_SAME_CHAIN"
        return out
    if any(r["received_date"] < sessions[0] for r in originals):
        out["overlap_reason"] = "LEFT_CENSORED_CALENDAR_RANGE"
        return out
    starts = defaultdict(list)
    missing = 0
    for row in originals:
        index = bisect_right(sessions, row["received_date"])
        if index == len(sessions):
            missing += 1
        else:
            starts[row["issuer_id"]].append(index)
    if not starts:
        out["overlap_reason"] = "NO_SIGNAL_SESSIONS_IN_CALENDAR"
        return out
    for horizon in (126, 252):
        valid_starts = {k: sorted(v) for k, v in starts.items()}
        pairs = sum(sum(1 for j in range(i + 1, len(v)) if v[j] - v[i] < horizon)
                    for v in valid_starts.values() for i in range(len(v)))
        out["overlap"][f"H{horizon}"] = {
            "potential_same_issuer_overlapping_pairs": pairs,
            "originals_with_signal_session": sum(map(len, starts.values())),
            "originals_without_signal_session": missing,
            "right_censored_windows": sum(i + horizon >= len(sessions)
                                          for v in starts.values() for i in v),
        }
    out["overlap_reason"] = "POTENTIAL_WINDOWS_ONLY_NO_RETURN_VALIDITY_OR_EFFECTIVE_N"
    return out
