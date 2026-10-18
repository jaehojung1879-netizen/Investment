"""WP2 population census only: price PRESENCE, identity metadata, no outcomes.

The pilot CIK and sector definitions, v3 identity evidence and workbench keys
are reused. R-b is explicitly provisional; this does not repair replay-v16.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import math

from . import alpha_opportunity_v3_identity as ID
from . import experiment_workbench as W
from . import regional_alpha_features as RAF
from . import us_capital_allocation_coverage as C
from . import us_cash_profitability as CP

VERSION = "RP1_WP2_US_UNIVERSE_IDENTITY_V1"
RULES = ("R-a", "R-b")


@dataclass(frozen=True)
class PopulationMember:
    key: W.Key


def cik(value):
    text = str(value or "")
    return str(int(text)) if text.isdigit() and int(text) > 0 else None


def presence(rows, through, bucket=None):
    """Discard price magnitudes immediately; never retain a future-price path."""
    bucket = defaultdict(set) if bucket is None else bucket
    for row in rows:
        value = row.get("Close")
        if row["date"] <= through and not row["ticker"].endswith((".KS", ".KQ")):
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
                bucket[row["ticker"]].add(row["date"])
    return bucket


class VisibleCiks:
    """Only earliest public day for each ticker/CIK; census visibility policy."""
    def __init__(self, rows):
        self.first = defaultdict(dict)
        for row in rows:
            issuer, visible = cik(row.get("cik")), CP.visible_day(row)
            if issuer and visible:
                day = visible.isoformat()
                old = self.first[row["ticker"]].get(issuer)
                self.first[row["ticker"]][issuer] = min(day, old) if old else day

    def matches(self, ticker, issuer, day):
        first = self.first.get(ticker, {}).get(cik(issuer))
        return bool(first and first < day)

    def reason(self, ticker, issuer, day):
        if not cik(issuer):
            return "NO_SNAPSHOT_CIK"
        if self.matches(ticker, issuer, day):
            return None
        return ("CIK_MISMATCH" if any(first < day for first in self.first.get(ticker, {}).values())
                else "NO_VISIBLE_FILING_CIK")


def identity_maps(snapshots, evidence, prices, through):
    """Rebuild #245's identity-only audit join from source, not a result file.

    Full-history evidence is a retrospective identity audit, NOT a new PIT
    identifier source. Only snapshot CIKs enter the date-specific CIK gate.
    """
    by_commit = {s["sourceCommit"]: s for s in evidence["snapshots"]}
    index = []
    for snap in snapshots:
        ev = by_commit[snap["sourceCommit"]]
        table = {evidence["rows"][i][0].replace(".", "-"): tuple(evidence["rows"][i]) for i in ev["rows"]}
        if ev["date"] != snap["date"] or sorted(table) != sorted(snap["members"]):
            raise ValueError("IDENTITY_EVIDENCE_DOES_NOT_MATCH_SNAPSHOT")
        index.append(table)
    # classify uses ONLY the first and last presence dates, never magnitudes.
    avail = {t: {d: (True, False) for d in {min(days), max(days)}} for t, days in prices.items() if days}
    raw, malformed = ID.classify(snapshots, avail, index=index, through=through)
    normalized = ID.normalized_snapshots(snapshots, malformed)
    norm_index = [{malformed.get(t, t): row for t, row in table.items()} for table in index]
    records, _ = ID.classify(normalized, avail, index=norm_index, through=through)
    mappings = {t: ID.pricing_symbol(t, records) for t in records}
    ambiguous = {t for t, r in records.items() if r["category"] == ID.TICKER_REUSE_DIFFERENT_ISSUER
                 or "PANEL_POSTDATES_MEMBERSHIP" in r["flags"]}
    return raw, malformed, mappings, ambiguous


def select(years, summaries):
    """Exact integer 50% gate, every requested year; no missing-year pass."""
    passes = {}
    for rule in RULES:
        passes[rule] = all(str(year) in summaries and summaries[str(year)]["memberDays"] > 0
            and 2 * summaries[str(year)]["rules"][rule]["eligibleMemberDays"] >= summaries[str(year)]["memberDays"]
            for year in years)
    return {"passesEveryYear": passes, "selectedRule": next((r for r in RULES if passes[r]), None),
            "decision": next((r for r in RULES if passes[r]), "DATA_INSUFFICIENT")}


def percentage(n, d):
    return round(100 * n / d, 6) if d else None


def summarize(count, rules):
    total, nonfin = count["memberDays"], count["nonfinancialMemberDays"]
    out = {"memberDays": total, **dict(sorted(count.items()))}
    for key in ("financialRealEstateExcluded", "industryUnresolved", "nonfinancialMemberDays",
                "exitedMemberDays", "exitedNoPriceMemberDays", "knownConflictMemberDays", "snapshotOver90Days"):
        out[key] = count[key]
        out[key + "PctOfAll"] = percentage(count[key], total)
    out["exitedNoPricePctOfExited"] = percentage(count["exitedNoPriceMemberDays"], count["exitedMemberDays"])
    out["rules"] = {}
    for rule, values in rules.items():
        row = dict(sorted(values.items()))
        for field in ("eligibleMemberDays", "cikVerifiedMemberDays", "legacyRawJoinMemberDays"):
            row[field] = values[field]
            row[field + "PctOfAll"] = percentage(values[field], total)
        row["eligiblePctOfNonfinancial"] = percentage(values["eligibleMemberDays"], nonfin)
        row["cikVerifiedPctOfEligible"] = percentage(values["eligibleCikVerifiedMemberDays"], values["eligibleMemberDays"])
        row["firstFailureReasons"] = {k.removeprefix("failure:"): v for k, v in sorted(values.items()) if k.startswith("failure:")}
        row = {k: v for k, v in row.items() if not k.startswith("failure:")}
        if sum(row["firstFailureReasons"].values()) + row["eligibleMemberDays"] != total:
            raise ValueError("DENOMINATOR_NOT_RECONCILED")
        out["rules"][rule] = row
    return out


def measure(snapshots, sector_snapshots, evidence, prices, filing_metadata, dates, spec, *, through):
    """No outcome callback, IO, target window, financial arithmetic or model."""
    snapshots = sorted(snapshots, key=lambda s: s["date"])
    if len({(s["date"], s["sourceCommit"]) for s in snapshots}) != len(snapshots):
        raise ValueError("DUPLICATE_SNAPSHOT_OBSERVATION")
    if any(len(s["members"]) != len(set(s["members"])) for s in snapshots):
        raise ValueError("DUPLICATE_SNAPSHOT_MEMBER")
    if len(dates) != len(set(dates)):
        raise ValueError("DUPLICATE_SIGNAL_DATE")
    raw, malformed, mappings, ambiguous = identity_maps(snapshots, evidence, prices, through)
    members, sectors, visible = RAF.MembershipSnapshots(snapshots), C.SectorBook(sector_snapshots), VisibleCiks(filing_metadata)
    # Departure describes observed index exit, never delisting or zero proceeds.
    departed = {t for s in snapshots for t in s["members"] if t not in snapshots[-1]["members"]}
    known = set(spec["knownSuspectSymbols"])
    counts, rule_counts, sample_digests = {}, {}, {}
    eligibility_digests = {r: hashlib.sha256() for r in RULES}
    panel_counts, panel_years = defaultdict(Counter), defaultdict(Counter)
    sample_chain = hashlib.sha256()
    max_age, missing_snapshots = 0, []
    for day in sorted(dates):
        year = day[:4]
        count = counts.setdefault(year, Counter())
        rules = rule_counts.setdefault(year, {r: Counter() for r in RULES})
        snap = members.on(day)
        if snap is None:
            missing_snapshots.append(day)
            continue
        count["sessions"] += 1
        age = (CP._day(day) - CP._day(snap["date"])).days
        max_age = max(max_age, age)
        # Canonical key remains in replay-v16's symbol namespace; CIK is an
        # issuer attribute, not a share-class key. Alias merges cannot erase it.
        population = [PopulationMember(W.Key("US", day, "replay-v16:US:" + t)) for t in sorted(snap["members"])]
        sample_id = W.sample_identity(population)
        sample_chain.update((day + ":" + sample_id + "\n").encode())
        sample_digests.setdefault(year, hashlib.sha256()).update((day + ":" + sample_id + "\n").encode())
        targets = {t: mappings.get(malformed.get(t, t)) or malformed.get(t, t) for t in snap["members"]}
        duplicates = Counter(targets.values())
        eligibility = {r: [] for r in RULES}
        for symbol in sorted(snap["members"]):
            count["memberDays"] += 1
            count["snapshotOver90Days"] += age > 90
            sector, basis = sectors.lookup(snap, symbol)
            count["sectorBasis:" + basis] += 1
            industry_missing = sector == C.UNCLASSIFIED
            excluded = sector in ("Financials", "Real Estate")
            nonfin = not excluded and not industry_missing
            count["financialRealEstateExcluded"] += excluded
            count["industryUnresolved"] += industry_missing
            count["nonfinancialMemberDays"] += nonfin
            normalized = malformed.get(symbol, symbol)
            conflict = symbol in known or normalized in ambiguous or not ID.well_formed(normalized)
            count["knownConflictMemberDays"] += conflict
            no_price = day not in prices.get(symbol, ())
            if symbol in departed:
                count["exitedMemberDays"] += 1
                count["exitedNoPriceMemberDays"] += no_price
            panel_counts[symbol]["memberDays"] += 1
            panel_counts[symbol]["noExactPriceDays"] += no_price
            panel_years[symbol][year] += 1
            for rule in RULES:
                ticker = targets[symbol] if rule == "R-a" else symbol
                present = day in prices.get(ticker, ())
                matched = visible.matches(ticker, sectors.cik(snap, symbol), day)
                r = rules[rule]
                r["cikVerifiedMemberDays"] += matched
                r["cikStatus:" + (visible.reason(ticker, sectors.cik(snap, symbol), day) or "MATCHED")] += 1
                r["legacyRawJoinMemberDays"] += nonfin and present
                reason = ("FINANCIAL_REAL_ESTATE" if excluded else "INDUSTRY_UNRESOLVED" if industry_missing else
                          "KNOWN_IDENTITY_CONFLICT" if conflict else
                          "DUPLICATE_PRICING_IDENTITY" if rule == "R-a" and duplicates[ticker] > 1 else
                          "NO_EXACT_SESSION_PRICE" if not present else
                          visible.reason(ticker, sectors.cik(snap, symbol), day) if rule == "R-a" and not matched else None)
                r["eligibleMemberDays"] += reason is None
                r["eligibleCikVerifiedMemberDays"] += reason is None and matched
                if reason:
                    r["failure:" + reason] += 1
                eligibility[rule].append([symbol, ticker, reason])
        for rule in RULES:
            # Freeze all accept/hold decisions, not only the accepted survivors.
            mask_sha = hashlib.sha256(RAF.canonical(eligibility[rule])).hexdigest()
            eligibility_digests[rule].update((day + ":" + mask_sha + "\n").encode())
    annual = {year: summarize(count, rule_counts[year]) for year, count in sorted(counts.items())}
    decision = select(spec["years"], annual)
    if missing_snapshots:
        decision = {"passesEveryYear": dict.fromkeys(RULES, False), "selectedRule": None, "decision": "DATA_INSUFFICIENT"}
    suspect = []
    for symbol, rec in sorted(raw.items()):
        flags = list(rec["flags"])
        if symbol in known:
            flags.append(spec["knownSuspectSymbols"][symbol])
        if rec["category"] in (ID.TICKER_REUSE_DIFFERENT_ISSUER, ID.SAME_SECURITY_RENAME,
                               ID.IDENTIFIER_MALFORMED_RESOLVED, ID.IDENTIFIER_MALFORMED_UNRESOLVED):
            flags.append(rec["category"])
        if flags:
            suspect.append({"symbol": symbol, "reasons": sorted(set(flags)), "firstPanelDate": rec["panelFirstClose"],
                "lastPanelDate": rec["panelLastClose"], "firstSnapshotDate": rec["firstMember"],
                "lastSnapshotDate": rec["lastMember"], "diagnosticPricingSymbol": mappings.get(malformed.get(symbol, symbol)),
                "memberDays": panel_counts[symbol]["memberDays"], "noExactPriceDays": panel_counts[symbol]["noExactPriceDays"],
                "memberDaysByYear": dict(sorted(panel_years[symbol].items()))})
    return {"byYear": annual, "selection": decision,
        "sampleIdentity": {"namespace": "replay-v16:US:historical-symbol; PROVISIONAL, not issuer CIK",
            "orderedCrossSectionChainSha256": sample_chain.hexdigest(),
            "eligibilityMaskChainSha256": {r: h.hexdigest() for r, h in eligibility_digests.items()},
            "byYearSha256": {y: h.hexdigest() for y, h in sorted(sample_digests.items())}},
        "snapshotCoverage": {"maxAgeDays": max_age, "missingSnapshotDates": missing_snapshots,
            "multipleObservationDays": sum(n > 1 for n in Counter(s["date"] for s in snapshots).values()),
            "sameDayPolicy": "inherited MembershipSnapshots stable source order; same-day sources unavailable"},
        "departed": {"definition": "not in last preserved snapshot; not proof of delisting",
            "rawSymbols": len(departed), "withoutAnyDirectPricePanel": sum(not prices.get(t) for t in departed),
            "diagnosticCategoryCounts": dict(sorted(Counter(raw[t]["category"] for t in departed).items())),
            "notIdentitySafeDirectPanel": sum(not prices.get(t) or t in ambiguous or t in known or not ID.well_formed(t)
                                              for t in departed)},
        "suspectPanels": suspect}


def scan_output(value):
    """A schema guard: counters are allowed, actual outcome payload keys aren't."""
    blocked = ("return", "label", "winner", "cagr", "mdd", "nav", "close", "volume", "prediction", "holding", "weight")
    counters = {"outcomeReads", "forwardPriceReads", "labelReads", "modelFits", "locksCreated"}
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "sectorBasis:NO_SECTOR_LABEL_IN_ANY_EARLIER_SNAPSHOT" and isinstance(child, int):
                continue
            if key in counters:
                if child != 0:
                    raise ValueError("NONZERO_FORBIDDEN_ACCESS_COUNTER")
                continue
            if any(token in str(key).lower().replace("_", "") for token in blocked):
                raise ValueError("FORBIDDEN_OUTPUT_KEY:" + str(key))
            scan_output(child)
    elif isinstance(value, list):
        for child in value:
            scan_output(child)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NONFINITE_OUTPUT")
