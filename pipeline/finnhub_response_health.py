"""What a finnhub `financials-reported` response looked like, kept as evidence, and what the stored copy was missing.

WHY THIS FILE EXISTS. Every filing that first reached the US store from 2026-10-07 carries an EMPTY balance sheet while its income
statement and cash-flow statement look exactly like September's (docs/us-finnhub-balance-sheet-coverage-ko.md). Two very different
things produce that row and the store cannot tell them apart:

  * the vendor sent `report.bs = []`, or sent no balance sheet at all (the source omitted it), and
  * the vendor sent the balance sheet under a key this collector does not read (the schema moved).

`build_record` keeps `report.get("bs")` and nothing else, so the raw response, the key that carried the sheet and the rest of the
filing's shape are gone the moment the record is written. The collector also throws away every re-fetched copy of a filing it
already holds (first write wins, which is right for byte-stability), so it cannot say whether the vendor has since completed the
sheet. This module changes neither behaviour. It OBSERVES, during the run that already has the response in hand:

  * which keys the filing and its `report` carried, and which were not the ones the collector knows;
  * how the balance sheet looked in each served filing (present with total assets, present without it, empty, key absent);
  * for a filing already stored: whether the stored copy lacked a section this copy has (a completion candidate), the reverse
    (the vendor now serves LESS than it did), and whether any section's content changed since it was stored.

Nothing here writes a record, imputes an account, relabels a missing value or touches a shard. A missing total assets stays missing.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from pipeline import finnhub_derive as US
from pipeline import finnhub_fundamentals as FF

CONTRACT = "FINNHUB_RESPONSE_HEALTH_V1"
SECTIONS = ("bs", "ic", "cf")

BS_ASSETS_STATED = "BS_PRESENT_ASSETS_STATED"
BS_ASSETS_NOT_STATED = "BS_PRESENT_ASSETS_NOT_STATED"
BS_EMPTY = "BS_EMPTY_WITH_IC_OR_CF"
BS_KEY_ABSENT = "BS_KEY_ABSENT_WITH_IC_OR_CF"
NO_STATEMENTS = "NO_STATEMENT_SECTIONS"
STATUSES = (BS_ASSETS_STATED, BS_ASSETS_NOT_STATED, BS_EMPTY, BS_KEY_ABSENT, NO_STATEMENTS)
# A stored record keeps `[]` for a section the vendor did not send, so "empty" and "key absent" are one stored state.
STORED_BS_LOST = "STORED_BS_EMPTY_WITH_IC_OR_CF"
# "Incomplete" here means: total assets is not stated, which is what the two features that divide by it need.
INCOMPLETE = (BS_ASSETS_NOT_STATED, BS_EMPTY, BS_KEY_ABSENT, STORED_BS_LOST)

# Keys the collector reads (`build_record`) plus the ones the vendor documents next to them. Anything else is reported, not guessed at.
KNOWN_FILING_KEYS = frozenset({"accessNumber", "symbol", "cik", "form", "year", "quarter", "startDate", "endDate",
                               "filedDate", "acceptedDate", "report"})
KNOWN_REPORT_KEYS = frozenset(SECTIONS)
MAX_LISTED_IDS = 200
HISTORY_LIMIT = 60


def _has_assets(entries) -> bool:
    return any(isinstance(e, dict) and FF.strip_namespace(e.get("concept")) in US.ASSETS
               and isinstance(e.get("value"), (int, float)) for e in entries or [])


def balance_sheet_status(filing: dict) -> str:
    """How the balance sheet looked in ONE raw vendor filing."""
    report = filing.get("report")
    report = report if isinstance(report, dict) else {}
    others = any(report.get(s) for s in ("ic", "cf"))
    bs = report.get("bs")
    if bs:
        return BS_ASSETS_STATED if _has_assets(bs) else BS_ASSETS_NOT_STATED
    if not others:
        return NO_STATEMENTS
    return BS_EMPTY if "bs" in report else BS_KEY_ABSENT


def stored_balance_sheet_status(record: dict) -> str:
    """How the balance sheet looks in a STORED record (the raw key/empty distinction no longer exists)."""
    statements = record.get("statements") or {}
    bs = statements.get("bs")
    if bs:
        return BS_ASSETS_STATED if _has_assets(bs) else BS_ASSETS_NOT_STATED
    if not (statements.get("ic") or statements.get("cf")):
        return NO_STATEMENTS
    return STORED_BS_LOST


def _signature(entries) -> tuple:
    return tuple((e.get("concept"), e.get("unit"), e.get("value")) for e in entries or [] if isinstance(e, dict))


def unknown_keys(filing: dict) -> tuple[list[str], list[str]]:
    """(filing keys, report keys) outside the set this collector knows. Sorted, so the output is deterministic."""
    report = filing.get("report")
    report_keys = sorted(set(report) - KNOWN_REPORT_KEYS) if isinstance(report, dict) else []
    return sorted(set(filing) - KNOWN_FILING_KEYS), report_keys


def balance_sheet_quarantine(records: list[dict]) -> list[dict]:
    """The stored records whose balance sheet is missing while the income or cash-flow statement is not.

    A READ-SIDE VIEW. It selects and describes; it never edits a record, adds an account, or decides that a filing is unusable for
    anything but the two features that divide by total assets.
    """
    out = []
    for r in records:
        if stored_balance_sheet_status(r) == STORED_BS_LOST:
            out.append({"id": r.get("id"), "ticker": r.get("ticker"), "form": r.get("form"), "periodEnd": r.get("periodEnd"),
                        "availableFrom": r.get("availableFrom"), "collectedAt": r.get("collectedAt")})
    return sorted(out, key=lambda row: (str(row["ticker"]), str(row["periodEnd"]), str(row["id"])))


class ResponseHealth:
    """Accumulates what one collection run saw. Pure bookkeeping: every method returns nothing the collector acts on."""

    def __init__(self) -> None:
        self.served = Counter()                 # (freq, class, status) -> filings
        self.by_form = Counter()                # (form, class, "complete"/"incomplete") -> filings
        self.filing_key_count = Counter()
        self.report_key_count = Counter()
        self.unknown_filing_keys = Counter()
        self.unknown_report_keys = Counter()
        self.completion_candidates: list[str] = []
        self.completion_total = 0
        self.regressions: list[str] = []
        self.regression_total = 0
        self.section_changes = Counter()        # section -> stored copies whose content differs from the re-served copy
        self.seen_again_total = 0
        self.seen_again_with_bs_both = 0
        self.filings = 0

    def observe(self, freq: str, filing: dict, stored: dict | None, filing_id: str | None = None) -> None:
        """One served filing; `stored` is the record already held for the same id, or None when it is new."""
        self.filings += 1
        klass = "SEEN_AGAIN" if stored is not None else "NEW"
        status = balance_sheet_status(filing)
        self.served[(freq, klass, status)] += 1
        form = str(filing.get("form") or "")
        self.by_form[(form, klass, "incomplete" if status in INCOMPLETE else "complete")] += 1
        self.filing_key_count.update(filing.keys())
        report = filing.get("report")
        if isinstance(report, dict):
            self.report_key_count.update(report.keys())
        extra_filing, extra_report = unknown_keys(filing)
        self.unknown_filing_keys.update(extra_filing)
        self.unknown_report_keys.update(extra_report)
        if stored is None:
            return
        self.seen_again_total += 1
        stored_status = stored_balance_sheet_status(stored)
        fresh_bs = bool((report or {}).get("bs")) if isinstance(report, dict) else False
        if stored_status == STORED_BS_LOST and fresh_bs:
            self.completion_total += 1
            if len(self.completion_candidates) < MAX_LISTED_IDS and filing_id:
                self.completion_candidates.append(filing_id)
        elif stored_status in (BS_ASSETS_STATED, BS_ASSETS_NOT_STATED) and not fresh_bs:
            self.regression_total += 1
            if len(self.regressions) < MAX_LISTED_IDS and filing_id:
                self.regressions.append(filing_id)
        if stored_status in (BS_ASSETS_STATED, BS_ASSETS_NOT_STATED) and fresh_bs:
            self.seen_again_with_bs_both += 1
        fresh_sections = report if isinstance(report, dict) else {}
        for section in SECTIONS:
            before, after = (stored.get("statements") or {}).get(section) or [], fresh_sections.get(section) or []
            if before and after and _signature(before) != _signature([e for e in after if isinstance(e, dict)]):
                self.section_changes[section] += 1

    def summary(self) -> dict[str, Any]:
        new_total = sum(v for (_, k, _), v in self.served.items() if k == "NEW")
        new_incomplete = sum(v for (_, k, s), v in self.served.items() if k == "NEW" and s in INCOMPLETE)
        seen_total = self.seen_again_total
        seen_incomplete = sum(v for (_, k, s), v in self.served.items() if k == "SEEN_AGAIN" and s in INCOMPLETE)
        return {
            "contract": CONTRACT,
            "filingsServed": self.filings,
            "new": {"filings": new_total, "balanceSheetMissing": new_incomplete},
            "seenAgain": {"filings": seen_total, "balanceSheetMissing": seen_incomplete,
                          "storedLostButServedNow": self.completion_total,
                          "storedHadButNotServedNow": self.regression_total,
                          "bothHaveBalanceSheet": self.seen_again_with_bs_both,
                          "sectionContentChangedSinceStored": dict(sorted(self.section_changes.items()))},
            "servedByFreqClassStatus": {f"{f}|{k}|{s}": v for (f, k, s), v in sorted(self.served.items())},
            "byFormClassCompleteness": {f"{f}|{k}|{c}": v for (f, k, c), v in sorted(self.by_form.items())},
            "filingKeys": dict(sorted(self.filing_key_count.items())),
            "reportKeys": dict(sorted(self.report_key_count.items())),
            "unknownFilingKeys": dict(sorted(self.unknown_filing_keys.items())),
            "unknownReportKeys": dict(sorted(self.unknown_report_keys.items())),
            "completionCandidates": sorted(self.completion_candidates),
            "storedHadButNotServedNow": sorted(self.regressions),
            "degraded": bool(new_total and new_incomplete / new_total > DEGRADED_SHARE),
            "note": "observation only: no record, shard or account was written, imputed or relabelled from this summary",
        }


# A normal run sees roughly 0.4% of new filings without a balance sheet; five per cent is an order of magnitude above that.
DEGRADED_SHARE = 0.05


def merge_history(existing: dict | None, run: dict, collected_at: str) -> dict:
    """Append this run to the sidecar's bounded history (newest last). Pure; the caller decides where it is written."""
    runs = list((existing or {}).get("runs") or [])
    runs.append({"collectedAt": collected_at, **run})
    return {"contract": CONTRACT, "runs": runs[-HISTORY_LIMIT:]}
