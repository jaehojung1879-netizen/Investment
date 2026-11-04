"""Build the outcome-free industry foundation inventories of Lane B.

    python -m research.master_research_program_v1.market_industry.build_industry_foundation

Writes, next to this file:
* ``us-sector-foundation-v1.json`` -- coverage, staleness and stability of the PIT US sector table (``us_sector_membership``).
* ``kr-industry-foundation-status-v1.json`` -- the KR industry membership foundation v4 status, copied from its own audit file.

Reads ONLY membership/sector snapshots, the survivorship audit's symbol lists and the KR v4 audit file. No price, return, label,
IC or model output is read or computed.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from research.master_research_program_v1.market_industry import us_sector_membership as U

HERE = Path(__file__).resolve().parent
ROOT = U.ROOT
IDENTITY_EVIDENCE = ROOT / "research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz"
SURVIVORSHIP_AUDIT = ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json"
KR_V4_AUDIT = ROOT / "data/kr-industry-membership-foundation-v4/state/audit.json.gz"
KR_V4_INTERVALS = ROOT / "data/kr-industry-membership-foundation-v4/state/intervals.json.gz"
KR_V4_DOC = ROOT / "docs/kr-industry-membership-foundation-v4.md"
BASE_COMMIT = "37f8cbf6"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path):
    return str(Path(path).resolve().relative_to(ROOT))


def ref(path):
    return rel(path) + "@" + BASE_COMMIT


def _git_unchanged_since_base(path):
    try:
        out = subprocess.run(["git", "diff", "--quiet", BASE_COMMIT, "--", rel(path)], cwd=ROOT, capture_output=True)
        return out.returncode == 0
    except OSError:
        return None


def raw_label_inventory(snapshots):
    first, last, rows = {}, {}, Counter()
    for s in snapshots:
        for r in s.rows.values():
            name = r.get("sector")
            key = "<blank>" if name is None else name
            first.setdefault(key, s.date)
            last[key] = s.date
            rows[key] += 1
    out = []
    for key in sorted(first):
        canonical, reason = U.normalise_sector(None if key == "<blank>" else key)
        out.append({"raw": key, "firstSnapshot": first[key], "lastSnapshot": last[key], "rows": rows[key], "canonical": canonical, "reason": reason})
    return out


def sector_level_raw(inventory):
    return [x for x in inventory if x["reason"] != "NOT_SECTOR_LEVEL_LABEL"]


def gaps(snapshots):
    days = sorted({date.fromisoformat(s.date) for s in snapshots})
    g = [(b - a).days for a, b in zip(days, days[1:])]
    worst = max(range(len(g)), key=lambda i: g[i])
    return {"distinctSnapshotDates": len(days), "snapshots": len(snapshots), "first": str(days[0]), "last": str(days[-1]),
            "gapDays": {"min": min(g), "median": statistics.median(g), "p90": sorted(g)[int(0.9 * (len(g) - 1))], "max": g[worst]},
            "maxGap": {"from": str(days[worst]), "to": str(days[worst + 1]), "days": g[worst]},
            "gapsOver90Days": [{"from": str(days[i]), "to": str(days[i + 1]), "days": g[i]} for i in range(len(g)) if g[i] > 90]}


def per_year(snapshots):
    by_year = defaultdict(list)
    for s in snapshots:
        by_year[s.date[:4]].append(s)
    out = {}
    for year, snaps in sorted(by_year.items()):
        member_dates = with_sector_pub = with_sector_carry = with_cik = 0
        joined = Counter()
        unique = set()
        sector_counts = defaultdict(list)
        for s in snaps:
            counts = Counter()
            for m in s.members:
                unique.add(m)
                member_dates += 1
                _, basis = s.row_for(m)
                joined[basis] += 1
                if s.cik_of(m):
                    with_cik += 1
                sec, b, _ = U.sector_on(snapshots, s.published_at, m, carry=True)
                if b == U.BASIS_PUBLISHED:
                    with_sector_pub += 1
                elif b == U.BASIS_CARRIED:
                    with_sector_carry += 1
                if sec is not None:
                    counts[sec] += 1
            for sec in U.GICS_SECTORS:
                if counts.get(sec):
                    sector_counts[sec].append(counts[sec])
        per_sector_median = {k: statistics.median(v) for k, v in sorted(sector_counts.items())}
        all_cells = [c for v in sector_counts.values() for c in v]
        out[year] = {
            "snapshots": len(snaps), "uniqueMembers": len(unique), "memberDates": member_dates,
            "membersPerSnapshot": {"min": min(len(s.members) for s in snaps), "max": max(len(s.members) for s in snaps)},
            "pctWithSectorAsPublished": round(100 * with_sector_pub / member_dates, 3),
            "pctWithSectorIncludingCarry": round(100 * (with_sector_pub + with_sector_carry) / member_dates, 3),
            "pctWithCik": round(100 * with_cik / member_dates, 3),
            "joinBasis": dict(sorted(joined.items())),
            "sectorsPresent": len(sector_counts),
            "namesPerSector": {"minAcrossSnapshotsAndSectors": min(all_cells) if all_cells else None,
                               "medianOfSectorMedians": statistics.median(per_sector_median.values()) if per_sector_median else None,
                               "perSectorMedian": per_sector_median},
        }
    return out


def pit_weekly(snapshots, start="2013-01-04", end="2026-09-11"):
    """The PIT view a weekly study would see: every Friday, the latest snapshot visible at 00:00 UTC that day."""
    from datetime import timedelta
    day, stop = date.fromisoformat(start), date.fromisoformat(end)
    by_year = defaultdict(lambda: {"dates": 0, "uniqueMembers": set(), "stalenessDays": [], "memberDates": 0, "withSector": 0,
                                   "carried": 0, "minNamesPerSector": None, "snapshotsUsed": set()})
    while day <= stop:
        snap = U.snapshot_on(snapshots, day)
        y = by_year[str(day.year)]
        y["dates"] += 1
        if snap is not None:
            y["snapshotsUsed"].add(snap.date)
            y["stalenessDays"].append((day - snap.published_at.date()).days)
            table = U.membership_table(snapshots, day, carry=True)
            counts = Counter(v["sector"] for v in table.values() if v["sector"])
            y["uniqueMembers"].update(table)
            y["memberDates"] += len(table)
            y["withSector"] += sum(1 for v in table.values() if v["sector"])
            y["carried"] += sum(1 for v in table.values() if v["basis"] == U.BASIS_CARRIED)
            low = min(counts.values()) if counts else None
            y["minNamesPerSector"] = low if y["minNamesPerSector"] is None else min(y["minNamesPerSector"], low)
        day += timedelta(days=7)
    out = {}
    for year, y in sorted(by_year.items()):
        st = y["stalenessDays"]
        out[year] = {"weeklyDates": y["dates"], "distinctSnapshotsUsed": len(y["snapshotsUsed"]), "uniqueMembers": len(y["uniqueMembers"]),
                     "pctMemberDatesWithSector": round(100 * y["withSector"] / y["memberDates"], 3) if y["memberDates"] else None,
                     "memberDatesSectorCarried": y["carried"],
                     "stalenessDays": {"median": statistics.median(st), "max": max(st)} if st else None,
                     "minNamesPerSectorOnAnyDate": y["minNamesPerSector"]}
    return out


def cik_anomalies(snapshots):
    return [{"snapshot": s.date, "hasCikColumn": s.has_cik, "rowsWithoutCik": sum(1 for r in s.rows.values() if not r.get("cik"))}
            for s in snapshots if s.date >= "2023-04-13" and any(not r.get("cik") for r in s.rows.values())]


def sector_changes(snapshots):
    """Consecutive-snapshot changes of a member's canonical sector, both labels usable as published (no carry)."""
    pairs, symbols, by_transition, by_snapshot = 0, set(), Counter(), Counter()
    for a, b in zip(snapshots, snapshots[1:]):
        for m in sorted(a.members & b.members):   # sorted: set order is hash-seeded
            sa, _ = a.sector_of(m)
            sb, _ = b.sector_of(m)
            if sa is not None and sb is not None and sa != sb:
                pairs += 1
                symbols.add(m)
                by_transition[sa + " -> " + sb] += 1
                by_snapshot[b.date] += 1
    return {"changeEvents": pairs, "distinctSymbols": len(symbols),
            "topTransitions": [{"transition": k, "events": v}
                               for k, v in sorted(by_transition.items(), key=lambda kv: (-kv[1], kv[0]))[:12]],
            "snapshotsWithMostChanges": [{"snapshot": k, "events": v}
                                         for k, v in sorted(by_snapshot.items(), key=lambda kv: (-kv[1], kv[0]))[:6]],
            "basis": "canonical sector as published in both consecutive snapshots; spelling variants normalised; unusable labels skipped"}


def hash_check(sector_payload):
    with gzip.open(IDENTITY_EVIDENCE) as fh:
        evidence = json.load(fh)
    pinned = {(s["date"], s["sourceCommit"]): s["rawCsvSha256"] for s in evidence["snapshots"]}
    match = sum(1 for s in sector_payload["snapshots"] if pinned.get((s["date"], s["sourceCommit"])) == s["rawCsvSha256"])
    return {"snapshotsMatchingPinnedRawCsvSha256": match, "snapshots": len(sector_payload["snapshots"])}


def departed_sectors(snapshots):
    audit = json.loads(SURVIVORSHIP_AUDIT.read_text())
    us = audit["regions"]["US"]
    no_panel = sorted(us["_sets"]["noPanel"])
    reused = set(us["identity"]["categories"].get("TICKER_REUSE_DIFFERENT_ISSUER", []))
    counts, basis, unresolved = Counter(), Counter(), []
    for sym in no_panel:
        spell_end = None
        started = False
        for s in snapshots:          # last snapshot of the symbol's FIRST membership spell (the departed issuer for a reused symbol)
            if sym in s.members:
                started = True
                spell_end = s
            elif started:
                break
        if spell_end is None:
            counts["NEVER_A_MEMBER_IN_SNAPSHOTS"] += 1
            unresolved.append(sym)
            continue
        sec, b, _ = U.sector_on(snapshots, spell_end.published_at, sym, carry=True)
        counts[sec or "UNAVAILABLE"] += 1
        basis[b] += 1
        if sec is None:
            unresolved.append(sym)
    return {"source": ref(SURVIVORSHIP_AUDIT), "set": "regions.US._sets.noPanel", "departedIdentitiesWithoutPanel": len(no_panel),
            "ofWhichReusedSymbols": len(reused & set(no_panel)),
            "sectorRule": "sector at the last snapshot of the symbol's first membership spell (carry from earlier snapshots only)",
            "bySector": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))), "sectorBasis": dict(sorted(basis.items())),
            "unresolved": unresolved,
            "caveat": "sector labels from the pre-2018 / pre-2020-05-10 taxonomy apply to names that departed before the restructure"}


def build_us():
    with gzip.open(U.SECTORS_PATH) as fh:
        sector_payload = json.load(fh)
    snapshots = U.load_snapshots()
    inventory = raw_label_inventory(snapshots)
    sub = [s.date for s in snapshots if s.sub_industry_column]
    years = per_year(snapshots)
    return {
        "schema": "US_SECTOR_FOUNDATION_V1",
        "lane": "master_research_program_v1/market_industry",
        "outcomeFree": True, "pricesRead": 0, "returnsRead": 0, "labelsRead": 0,
        "inputs": {rel(U.MEMBERSHIP_PATH): {"sha256": sha256(U.MEMBERSHIP_PATH), "ref": ref(U.MEMBERSHIP_PATH)},
                   rel(U.SECTORS_PATH): {"sha256": sha256(U.SECTORS_PATH), "ref": ref(U.SECTORS_PATH), "schema": sector_payload["schema"],
                                         "label": sector_payload["label"], "acquisitionFailures": len(sector_payload["failures"])},
                   rel(IDENTITY_EVIDENCE): {"sha256": sha256(IDENTITY_EVIDENCE)},
                   rel(SURVIVORSHIP_AUDIT): {"sha256": sha256(SURVIVORSHIP_AUDIT)}},
        "rawCsvHashCheck": hash_check(sector_payload),
        "pitRule": "latest snapshot whose publishedAt <= as-of; a date-only as-of is 00:00 UTC, so a same-day publication is visible next day; "
                   "a later snapshot is never consulted",
        "sectorColumnNames": dict(Counter(s.sector_column for s in snapshots)),
        "snapshotGaps": gaps(snapshots),
        "subIndustryColumnSnapshots": sub,
        "rawLabels": {"observedDistinct": len(inventory), "sectorLevelOrRecognised": sector_level_raw(inventory),
                      "notSectorLevelDistinct": sum(1 for x in inventory if x["reason"] == "NOT_SECTOR_LEVEL_LABEL")},
        "normalisationTable": {"spellingVariants": U.SPELLING_VARIANTS, "notGuessed": U.NOT_SECTOR_LEVEL,
                               "reclassificationsKeptDistinct": ["Telecommunication Services (last 2018-04-02) vs Communication Services (first 2020-05-10)",
                                                                 "Financials/Real Estate split visible from 2017-03-08",
                                                                 "IT -> Financials (V, MA, PYPL, FIS) and Consumer Discretionary -> Consumer Staples (DG, DLTR, TGT) visible from 2023-04-13"]},
        "perYear": years,
        "perYearNote": "perYear counts SNAPSHOTS dated in the year (2019 has none); pitWeekly is the as-of view a weekly study would read",
        "pitWeekly": pit_weekly(snapshots),
        "cikAnomaliesSince2023_04_13": cik_anomalies(snapshots),
        "sectorChanges": sector_changes(snapshots),
        "departedIdentities": departed_sectors(snapshots),
        "comparisonWithDocs": {
            "doc": "docs/research-program/07-market-industry-stock-portfolio-hierarchy-ko.md@" + BASE_COMMIT + " sec 2.2 (US 산업: 없음)",
            "nowReady": "SECTOR-level (11-12 GICS sector names as published by the dataset) PIT membership for S&P 500 members on every date from "
                        "2012-12-28, at dataset-snapshot granularity, research-only (dataset label, not an index-provider file)",
            "stillBlocked": ["sub-industry / industry-group history (only the malformed 2023-03-07 snapshot carries sub-industry names)",
                             "official GICS history (license unverified; not acquired)",
                             "prices for 212 departed identities without a panel (survivorship audit) -> historical US industry baskets are "
                             "survivor-conditioned; US industry evidence is PROSPECTIVE_ONLY",
                             "staleness: the dataset is updated irregularly; the 769-day gap 2018-04-02 -> 2020-05-10 means the 2018 Communication "
                             "Services restructure enters the PIT table only on 2020-05-10",
                             "dataset license/terms not verified for anything beyond internal research"]},
    }


def build_kr():
    with gzip.open(KR_V4_AUDIT) as fh:
        audit = json.load(fh)
    with gzip.open(KR_V4_INTERVALS) as fh:
        intervals = json.load(fh)
    absent = audit["absent28"]
    return {
        "schema": "KR_INDUSTRY_FOUNDATION_STATUS_V1", "outcomeFree": True, "recomputed": False,
        "source": {"audit": ref(KR_V4_AUDIT), "auditSha256": sha256(KR_V4_AUDIT), "intervals": ref(KR_V4_INTERVALS),
                   "intervalsSha256": sha256(KR_V4_INTERVALS), "doc": ref(KR_V4_DOC),
                   "unchangedSinceBase": _git_unchanged_since_base(KR_V4_AUDIT)},
        "files": sorted(rel(p) for p in (ROOT / "data/kr-industry-membership-foundation-v4").rglob("*") if p.is_file()),
        "copiedFromAudit": {k: audit[k] for k in ("contract", "decision", "gates", "thresholds", "everTop120Securities", "nameDates",
                                                  "classifiedNameDates", "classifiedPct", "signalDates", "signalCoveragePct", "terminal",
                                                  "terminalCoveragePct", "fractionInSufficientGroups", "sufficientGroupsPerDate",
                                                  "groupSize", "coarseIndustryCount", "rawIndustryCount", "topGroupShare",
                                                  "identityBreaksFromTerminalSet", "historicalOutcomeComputed")},
        "absent28Summary": {k: v for k, v in absent.items() if k != "perSecurity"},
        "intervalSecurities": len(intervals),
        "reading": {
            "historical": "DATA_FOUNDATION_INSUFFICIENT_V4: terminal coverage 0/2,345 name-dates and 398/610 dates below the 90% "
                          "groups-of-five gate; no taxonomy selected; the 22 terminated securities carry no industry",
            "prospective": "a classification observed AT the signal date is PIT by construction; the v4 frozen 14-group crosswalk could "
                           "label new receipts, but taxonomy selection failed the groups-of-five rule, so a prospective contract must "
                           "preregister how small groups are handled before the first receipt",
        },
    }


def main():
    us = build_us()
    kr = build_kr()
    for name, payload in (("us-sector-foundation-v1.json", us), ("kr-industry-foundation-status-v1.json", kr)):
        (HERE / name).write_text(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
        print(name, hashlib.sha256((HERE / name).read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
