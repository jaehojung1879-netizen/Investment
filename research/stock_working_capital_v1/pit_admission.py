"""Outcome-free, date-keyed WC -> intended Top120 crosswalk.

Membership, readability, dated evidence and full admission are separate stages.
No security is removed for missing filings, industry, trading halt or eventual
termination. A missing source cannot turn into an empty successful cohort.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import timedelta
import re
import zipfile
import xml.etree.ElementTree as ET

from . import features as F
from . import pit_filing_evidence as E


class TopSnapshots:
    def __init__(self, rows, sessions, expected=120):
        if sessions != sorted(set(sessions)) or not sessions or expected < 1:
            raise ValueError("INVALID_CALENDAR_OR_EXPECTED_DENOMINATOR")
        self.expected, self.sessions = expected, set(sessions)
        self.by_date = defaultdict(list)
        seen, ranks = set(), set()
        for row in rows:
            stamp, ticker, rank = row["date"], row["ticker"], row["rank"]
            F.day(stamp)
            if (stamp not in self.sessions or not re.fullmatch(r"[0-9A-Z]{6}\.KS", ticker)
                    or type(rank) is not int or rank < 1):
                raise ValueError("INVALID_UNIVERSE_SOURCE_ROW")
            if (stamp, ticker) in seen or (stamp, rank) in ranks:
                raise ValueError("DUPLICATE_UNIVERSE_DATE_SECURITY_OR_RANK")
            seen.add((stamp, ticker))
            ranks.add((stamp, rank))
            if rank <= expected:
                self.by_date[stamp].append({k: row.get(k) for k in ("date", "ticker", "name", "rank")})
            else:
                self.by_date.setdefault(stamp, [])  # broken top ranks must not hide this snapshot
        self.dates = sorted(self.by_date)

    def on(self, signal):
        if signal not in self.sessions:
            raise ValueError("KRX_CLOSED_OR_UNKNOWN_SIGNAL_DATE")
        i = bisect_right(self.dates, signal) - 1  # signal close: same-day snapshot may be known
        if i < 0:
            payload = {"signal": signal, "snapshotDate": None, "members": [], "expectedCount": self.expected,
                       "missingRankSlots": list(range(1, self.expected + 1)), "reasons": ["NO_PRIOR_SNAPSHOT"],
                       "snapshotAgeDays": None, "basis": "NO_MEMBERSHIP_EVIDENCE"}
            return {**payload, "intendedSha256": F.digest(payload)}
        stamp = self.dates[i]
        members = sorted(self.by_date[stamp], key=lambda r: r["rank"])
        missing = sorted(set(range(1, self.expected + 1)) - {r["rank"] for r in members})
        reasons = []
        if missing:
            reasons.append("INCOMPLETE_TOP120_SNAPSHOT")
        if stamp[:7] != signal[:7]:
            reasons.append("STALE_MONTHLY_SNAPSHOT")
        payload = {"signal": signal, "snapshotDate": stamp, "members": members, "expectedCount": self.expected,
                   "missingRankSlots": missing, "reasons": reasons,
                   "snapshotAgeDays": (F.day(signal) - F.day(stamp)).days,
                   "basis": "SAME_SESSION_SNAPSHOT" if stamp == signal else "LAST_KNOWN_MONTHLY_TOP120_NOT_DAILY_RANK"}
        return {**payload, "intendedSha256": F.digest(payload)}


def first_friday_after(public_day, sessions):
    return next((s for s in sessions if s > public_day and F.day(s).weekday() == 4), None)


def choose_pair(records, signal):
    """Latest fiscal year of visible ANNUAL records; never latest delivery order."""
    visible = defaultdict(list)
    for row in records:
        if row.get("reportCode") != "11011":
            continue
        try:
            stamp = F.day(row.get("availableFrom"))
        except ValueError:
            return None, None, ["UNPLACEABLE_FILING_PUBLIC_DATE"]
        if stamp < F.day(signal):
            if type(row.get("fiscalYear")) is not int:
                return None, None, ["INVALID_FISCAL_YEAR"]
            visible[row["fiscalYear"]].append(row)
    if not visible:
        return None, None, ["NO_VISIBLE_ANNUAL"]
    year = max(visible)
    if len(visible[year]) != 1:
        return None, None, ["AMBIGUOUS_CURRENT_VINTAGE"]
    current = visible[year][0]
    previous = visible.get(year - 1, [])
    if len(previous) != 1:
        return current, None, ["MISSING_OR_AMBIGUOUS_CONSECUTIVE_PRIOR_ANNUAL"]
    return current, previous[0], []


def filing_metadata(record, originals, signal):
    if record is None:
        return None, ["MISSING_ANNUAL_LEG"]
    receipts = record.get("receiptNos", [])
    if not isinstance(receipts, list) or len(receipts) != 1:
        return None, ["RAW_RECEIPT_AMBIGUOUS"]
    candidates = originals.get((record["ticker"], record["fiscalYear"], receipts[0]), [])
    if len(candidates) != 1:
        if not candidates and any(k[:2] == (record["ticker"], record["fiscalYear"]) for k in originals):
            return None, ["RAW_RECEIPT_DIFFERS_FROM_PRESERVED_ORIGINAL"]
        return None, ["ORIGINAL_MAIN_MISSING_OR_AMBIGUOUS"]
    meta = candidates[0]
    if meta.get("evidenceError"):
        return None, ["ORIGINAL_MAIN_REJECTED:" + meta["evidenceError"]]
    issues = []
    if meta["corpCode"] != record.get("corpCode") or meta["ticker"] != record.get("ticker"):
        issues.append("DATED_ISSUER_SECURITY_MISMATCH")
    if meta["availableFrom"] != record.get("availableFrom") or meta["availableFrom"] >= signal:
        issues.append("ORIGINAL_VISIBILITY_MISMATCH")
    return (None, issues) if issues else (meta, [])


def industry_on(ticker, signal, intervals, events, crosswalk):
    """Use only already-published effective change notices; no future before-label.

    Last disclosed label is a dated observation, not proof of exhaustive event
    coverage. The old reconstruction is retained as a diagnostic, never used as
    historical PIT merely because its current anchor has no recorded changes.
    """
    candidates = [r for r in intervals.get(ticker, [])
                  if (not r.get("start") or r["start"] <= signal) and (not r.get("end") or signal < r["end"])]
    reconstructed = candidates[0].get("research_industry_id") if len(candidates) == 1 else None
    usable = [e for e in events.get(ticker, []) if e["notice_date"] < signal and e["effective_date"] <= signal]
    if not usable:
        return {"group": None, "reconstructedGroup": reconstructed, "reason": "NO_DATED_INDUSTRY_OBSERVATION",
                "sourceSha256": None, "tier": "RECONSTRUCTION_ONLY" if reconstructed else "UNKNOWN"}
    latest = max(e["effective_date"] for e in usable)
    current = [e for e in usable if e["effective_date"] == latest]
    if len(current) != 1:
        return {"group": None, "reconstructedGroup": reconstructed, "reason": "AMBIGUOUS_INDUSTRY_EVENT",
                "sourceSha256": None, "tier": "UNKNOWN"}
    e = current[0]
    group = crosswalk["mapping"].get("".join(e["after_label"].split()))
    return {"group": group, "reconstructedGroup": reconstructed,
            "reason": None if group else "UNMAPPED_DATED_INDUSTRY_LABEL", "sourceSha256": e["document_sha256"],
            "tier": "LAST_PUBLISHED_OFFICIAL_OBSERVATION_NOT_EXHAUSTIVE_HISTORY",
            "effectiveDate": e["effective_date"], "noticeDate": e["notice_date"],
            "issuerCorpCode": e.get("issuerCorpCode"), "issuerBridgeSourceSha256": e.get("issuerBridgeSourceSha256"),
            "issuerBridgeAvailableFrom": e.get("issuerBridgeAvailableFrom")}


class Crosswalk:
    def __init__(self, *, snapshots, filings, originals, intervals, events, crosswalk,
                 terminal, trading, sessions, packages=None):
        self.snapshots, self.originals, self.intervals = snapshots, originals, intervals
        self.events, self.crosswalk, self.terminal, self.trading = events, crosswalk, terminal, trading
        self.sessions, self.packages = sessions, packages or {}
        self.filings = defaultdict(list)
        for r in filings:
            self.filings[r["ticker"]].append(r)
        self.pair_cache, self.metadata_cache, self.financial_cache = {}, {}, {}

    def _metadata(self, record, signal):
        if record is None:
            return None, ["MISSING_ANNUAL_LEG"]
        key = (record["id"], record["availableFrom"], tuple(record.get("receiptNos", [])))
        if key not in self.metadata_cache:
            self.metadata_cache[key] = filing_metadata(record, self.originals, signal)
        return self.metadata_cache[key]

    def _financial(self, record, meta, field):
        if record is None or meta is None:
            return {"ready": False, "start": None, "end": None,
                    "reasons": ["ORIGINAL_VALUE_VINTAGE_UNVERIFIED", "FISCAL_DURATION_UNPROVEN"]}
        key = (record["id"], meta["receipt"], field)
        if key not in self.financial_cache:
            try:
                result = E.original_financial_facts(record, meta, self.packages.get(meta["receipt"]), field)
            except (ValueError, zipfile.BadZipFile, ET.ParseError, ArithmeticError) as exc:
                result = {"ready": False, "start": None, "end": None,
                          "reasons": ["ORIGINAL_VALUE_VINTAGE_UNVERIFIED", "FISCAL_DURATION_UNPROVEN", str(exc)]}
            self.financial_cache[key] = result
        return self.financial_cache[key]

    def on(self, signal):
        cohort = self.snapshots.on(signal)
        rows = []
        for member in cohort["members"]:
            ticker = member["ticker"]
            current, prior, pair_issues = choose_pair(self.filings.get(ticker, []), signal)
            pair = None
            if current is not None and prior is not None:
                key = (current["id"], current["availableFrom"], prior["id"], prior["availableFrom"])
                if key not in self.pair_cache:
                    self.pair_cache[key] = F.annual_pair(current, prior, signal)
                pair = self.pair_cache[key]
            cm, ci = self._metadata(current, signal)
            pm, pi = self._metadata(prior, signal)
            identity_issues = []
            if cm is None or pm is None:
                identity_issues.append("DATED_IDENTITY_EVIDENCE_INCOMPLETE")
            elif cm["corpCode"] != pm["corpCode"]:
                identity_issues.append("ISSUER_CHANGED_BETWEEN_ANNUALS")
            elif E.normal_name(cm["companyName"]) != E.normal_name(member.get("name")):
                identity_issues.append("SIGNAL_NAME_OR_DATED_NAME_CHANGE_UNRESOLVED")
            end = self.terminal.get(ticker)
            # The final trading date is still live. Future termination is audit
            # context only, never grounds to remove or block an earlier signal.
            ended = end is not None and signal > end
            if ended:
                identity_issues.append("IDENTITY_ENDED_BY_SIGNAL")
            industry = industry_on(ticker, signal, self.intervals, self.events, self.crosswalk)
            industry_issuer_matched = (cm is not None and industry.get("issuerCorpCode") == cm["corpCode"]
                and bool(re.fullmatch(r"[0-9a-f]{64}", industry.get("issuerBridgeSourceSha256") or ""))
                and isinstance(industry.get("issuerBridgeAvailableFrom"), str)
                and industry["issuerBridgeAvailableFrom"] < industry.get("noticeDate", ""))
            trade = self.trading.get((signal, ticker), "MISSING_SIGNAL_SESSION_BAR")
            base = set(cohort["reasons"] + pair_issues + identity_issues)
            base.update("CURRENT:" + x for x in ci)
            base.update("PREVIOUS:" + x for x in pi)
            if industry["reason"]:
                base.add(industry["reason"])
            elif not industry_issuer_matched:
                base.add("INDUSTRY_EVENT_ISSUER_BRIDGE_UNVERIFIED")
            if trade != "OBSERVED_TRADABLE_SIGNAL_BAR":
                base.add(trade)
            out = {"signal": signal, "ticker": ticker, "rankAtSnapshot": member["rank"],
                   "snapshotDate": cohort["snapshotDate"], "membershipBasis": cohort["basis"],
                   "intendedSha256": cohort["intendedSha256"], "industry": industry,
                   "industryIssuerMatched": industry_issuer_matched,
                   "datedIdentityMatched": not identity_issues,
                   "originalMainPairMatched": cm is not None and pm is not None,
                   "tradingStatus": trade,
                   "knownTerminalExPostAuditOnly": end is not None, "endedBySignal": ended,
                   "eventDue": current is not None and first_friday_after(current["availableFrom"], self.sessions) == signal,
                   "currentFiscalYear": current.get("fiscalYear") if current else None,
                   "filingReceipts": [r.get("receiptNos") if r else None for r in (prior, current)],
                   "filingAvailableFrom": [r.get("availableFrom") if r else None for r in (prior, current)],
                   "filingRecordDigests": pair["filingDigests"] if pair else None,
                   "originalMainDigests": [r["mainSha256"] if r else None for r in (pm, cm)], "signals": {}}
            for name, field in zip(F.SIGNALS, ("receivables", "inventory")):
                candidate = pair["signals"][name] if pair else {"value": None, "reasons": pair_issues}
                issues = base | set(candidate["reasons"])
                cf, pf = self._financial(current, cm, field), self._financial(prior, pm, field)
                issues.update("CURRENT:" + x for x in cf["reasons"])
                issues.update("PREVIOUS:" + x for x in pf["reasons"])
                comparable = cf["ready"] and pf["ready"]
                if comparable:
                    if (F.day(pf["end"]) + timedelta(days=1)).isoformat() != cf["start"]:
                        issues.add("FISCAL_WINDOWS_NOT_ADJACENT")
                        comparable = False
                    if (F.day(signal) - F.day(cf["end"])).days > 550:
                        issues.add("STALE_VERIFIED_FISCAL_WINDOW")
                        comparable = False
                ready = candidate["value"] is not None and not issues
                out["signals"][name] = {"inputReadable": candidate["value"] is not None,
                    "inputCandidateSha256": F.digest(candidate) if candidate["value"] is not None else None,
                    "originalFinancialFactsMatched": cf["ready"] and pf["ready"],
                    "fiscalWindowsComparable": comparable, "inputAdmitted": ready,
                    "value": candidate["value"] if ready else None, "reasons": sorted(issues)}
            rows.append(out)
        return cohort, rows


def coverage(cohorts, rows):
    """Every date/ticker remains in coverage; unknown rank slots stay explicit."""
    keys = [(r["signal"], r["ticker"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_SIGNAL_SECURITY_OUTPUT")
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["signal"]].append(r)
    if len({c["signal"] for c in cohorts}) != len(cohorts):
        raise ValueError("DUPLICATE_SIGNAL_COHORT")
    for c in cohorts:
        if {r["ticker"] for r in by_date[c["signal"]]} != {m["ticker"] for m in c["members"]}:
            raise ValueError("OUTPUT_LOST_OR_ADDED_INTENDED_SECURITY")
    denominator = sum(c["expectedCount"] for c in cohorts)
    return {"expectedMemberDates": denominator, "retainedMemberDates": len(rows),
            "distinctSecurities": len({r["ticker"] for r in rows}),
            "unidentifiedRankSlots": sum(len(c["missingRankSlots"]) for c in cohorts),
            "signalDates": len(cohorts), "knownTerminalMemberDatesAuditOnly": sum(r["knownTerminalExPostAuditOnly"] for r in rows),
            "knownTerminalSecuritiesAuditOnly": sorted({r["ticker"] for r in rows if r["knownTerminalExPostAuditOnly"]}),
            "endedBySignalMemberDates": sum(r["endedBySignal"] for r in rows),
            "originalMainPairMatched": sum(r["originalMainPairMatched"] for r in rows),
            "datedIdentityMatched": sum(r["datedIdentityMatched"] for r in rows),
            "datedIndustryObserved": sum(r["industry"]["group"] is not None for r in rows),
            "datedIndustryIssuerMatched": sum(r["industryIssuerMatched"] for r in rows),
            "tradingStatusCounts": dict(sorted(Counter(r["tradingStatus"] for r in rows).items())),
            "signals": {s: {"inputReadable": sum(r["signals"][s]["inputReadable"] for r in rows),
                            "readableWithOriginalMainPair": sum(r["signals"][s]["inputReadable"] and r["originalMainPairMatched"] for r in rows),
                            "readableWithDatedIdentityAndIndustry": sum(r["signals"][s]["inputReadable"] and r["datedIdentityMatched"] and r["industryIssuerMatched"] for r in rows),
                            "eventDueInputReadable": sum(r["eventDue"] and r["signals"][s]["inputReadable"] for r in rows),
                            "originalFinancialFactsMatched": sum(r["signals"][s]["originalFinancialFactsMatched"] for r in rows),
                            "fiscalWindowsComparable": sum(r["signals"][s]["fiscalWindowsComparable"] for r in rows),
                            "inputAdmitted": sum(r["signals"][s]["inputAdmitted"] for r in rows),
                            "inputReadableCoverage": sum(r["signals"][s]["inputReadable"] for r in rows) / denominator if denominator else None,
                            "missingByReasonNonexclusive": dict(sorted(Counter(reason for r in rows for reason in r["signals"][s]["reasons"]).items()))}
                        for s in F.SIGNALS}}
