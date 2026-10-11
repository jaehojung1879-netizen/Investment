"""Build the US dual-benchmark (SPY + QQQ) research foundation. Research only.

    python scripts/build_us_dual_benchmark_foundation.py            # all stages
    python scripts/build_us_dual_benchmark_foundation.py --stage compare

Stage ``sealed`` needs the pinned ``signal-history`` commit in the local object
store (``git fetch --depth 1 --filter=blob:none origin signal-history``) and
writes the SPY/QQQ snapshot, the rates file, the data audit, the Nasdaq-100
membership audit and the coverage manifest. Stage ``compare`` reads only the
committed snapshot and rates, so CI can recompute the comparison byte for byte.

It writes nothing to ``signal-history``, ``docs/results/`` (sealed by Phase C),
any weekly-decision artifact or any production path.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import nasdaq100_membership as N        # noqa: E402
from pipeline import us_dual_benchmark_data as D      # noqa: E402
from pipeline import us_spy_qqq_comparison as C       # noqa: E402
from pipeline import us_universe_coverage as U        # noqa: E402

DATA = ROOT / "data/research/us-dual-benchmark-v1"
OUT = ROOT / "docs/us-readiness"
SNAPSHOT = DATA / "spy-qqq-total-return.csv.gz"
RATES = DATA / "rates.json"
MANIFEST = DATA / "manifest.json"
N100_DIR = DATA / "nasdaq100-n100tickers"
COVERAGE_CSV = DATA / "us-universe-coverage-manifest.csv.gz"
DATA_AUDIT = OUT / "us-dual-benchmark-v1-data-audit.json"
COMPARISON = OUT / "us-spy-qqq-comparison-v1.json"
N100_AUDIT = OUT / "nasdaq100-pit-membership-v1.json"
COVERAGE = OUT / "us-universe-coverage-gap-v1.json"
CHART = OUT / "us-spy-qqq-comparison-v1.svg"

N100_SOURCE = {
    "id": "n100tickers@ec99dfb8",
    "project": "jmccarrell/n100tickers (PyPI name nasdaq-100-ticker-history, version 2026.11.0)",
    "commit": "ec99dfb8690820895d0a7546a7d9218336b96554",
    "urlPattern": ("https://raw.githubusercontent.com/jmccarrell/n100tickers/"
                   "ec99dfb8690820895d0a7546a7d9218336b96554/src/nasdaq_100_ticker_history/"
                   "n100-ticker-changes-{year}.yaml"),
    "fetchedAt": "2026-10-11",
    "license": "MIT (copy in nasdaq100-n100tickers/LICENSE)",
    "statedCoverage": "accurate from 2007-02-01 through at least 2026-09-26 (project README)",
    "upstream": "public Wikipedia change tables plus Nasdaq press releases cited in file comments",
    "authority": "DERIVED_NON_AUTHORITATIVE",
}
STUDY_START, STUDY_END = "2013-01-01", "2026-09-14"
COSTS_KEY = ("kellyPortfolio", "transactionCosts", "US")

# Official Nasdaq press releases whose titles and dates were surfaced by web
# search on 2026-10-11. The documents were NOT fetched (no route from this
# environment), so they are spot checks of the derived record, not sources.
SEARCH_SURFACED_SPOT_CHECKS = [
    {"effective": "2014-12-22", "added": ["AAL", "EA", "LRCX", "FOX", "LBTYK"], "removed": ["EXPE", "FFIV", "MXIM"],
     "alsoAddedNotCarried": ["CMCSK"],
     "reference": "https://mondovisione.com/media-and-resources/news/annual-changes-to-the-nasdaq-100-index-3-20141213/"},
    {"effective": "2020-04-20", "added": ["DXCM"], "removed": ["AAL"],
     "reference": "https://www.nasdaq.com/press-release/dexcom-inc.-to-join-the-nasdaq-100-index-beginning-april-20-2020-2020-04-10"},
    {"effective": "2020-06-22", "added": ["DOCU"], "removed": [],
     "reference": "https://www.nasdaq.com/press-release/docusign-inc.-to-join-the-nasdaq-100-index-beginning-june-22-2020-2020-06-12"},
    {"effective": "2020-07-20", "added": ["MRNA"], "removed": [],
     "reference": "https://www.nasdaq.com/press-release/moderna-inc.-to-join-the-nasdaq-100-index-beginning-july-20-2020-2020-07-13"},
    {"effective": "2024-07-22", "added": ["SMCI"], "removed": ["WBA"],
     "reference": "https://www.nasdaq.com/press-release/super-micro-computer-inc-join-nasdaq-100-indexr-beginning-july-22-2024-2024-07-12"},
    {"effective": "2026-05-18", "added": ["LITE"], "removed": ["CSGP"],
     "reference": "https://kdhnews.com/online_features/press_releases/lumentum-holdings-inc-to-join-the-nasdaq-100-index-beginning-may-18-2026/article_801688d6-ffb0-5bed-90e8-d09a5c100ef6.html"},
    {"effective": "2026-07-07", "added": ["SPCX"], "removed": [],
     "reference": "https://www.barchart.com/story/news/3008679/space-exploration-technologies-corporation-to-join-the-nasdaq-100-index-beginning-july-7-2026"},
]

SOURCE_CANDIDATES = [
    {"id": "nasdaq-official-press-releases", "kind": "official announcements (annual + replacements)",
     "depth": "years of releases exist (2014 and 2020-2026 examples surfaced)", "publicationDate": "yes",
     "effectiveDate": "yes", "completeness": "complete in principle but must be gathered release by release",
     "identity": "company name + ticker; no CUSIP", "license": "public press releases",
     "reproducibility": "per-URL documents", "cost": "free",
     "actionsReachable": "NOT_MEASURED (workflow dispatch refused to this agent; probe script prepared)",
     "thisEnvironment": "BLOCKED (egress proxy refuses nasdaq.com; WebFetch cannot resolve hosts)",
     "survivorship": "none if complete", "verdict": "BEST_AUTHORITATIVE_ROUTE_NOT_YET_COLLECTED"},
    {"id": "nasdaq-global-index-watch-history", "kind": "official historical constituent/weight files",
     "depth": "unknown", "publicationDate": "unknown", "effectiveDate": "yes",
     "completeness": "presumably complete", "identity": "unknown", "license": "subscription",
     "reproducibility": "vendor", "cost": "PAID (not priced, not purchased)",
     "actionsReachable": "NOT_MEASURED", "thisEnvironment": "BLOCKED",
     "survivorship": "none", "verdict": "BLOCKED_PAID_SOURCE"},
    {"id": "nasdaq-api-current-list", "kind": "current constituents only", "depth": "today",
     "publicationDate": "n/a", "effectiveDate": "n/a", "completeness": "current only",
     "identity": "ticker + name", "license": "website terms", "reproducibility": "changes daily",
     "cost": "free", "actionsReachable": "NOT_MEASURED", "thisEnvironment": "BLOCKED",
     "survivorship": "TOTAL (today's list)", "verdict": "UNUSABLE_FOR_HISTORY"},
    {"id": "invesco-qqq-holdings", "kind": "QQQ daily holdings file", "depth": "today",
     "publicationDate": "daily", "effectiveDate": "n/a", "completeness": "current only",
     "identity": "ticker + CUSIP", "license": "website terms", "reproducibility": "changes daily",
     "cost": "free", "actionsReachable": "NOT_MEASURED", "thisEnvironment": "BLOCKED",
     "survivorship": "TOTAL (today's list)", "verdict": "UNUSABLE_FOR_HISTORY"},
    {"id": "sec-qqq-nport-holdings", "kind": "QQQ quarterly portfolio holdings (N-PORT; N-Q before 2019)",
     "depth": "quarterly, years", "publicationDate": "SEC filing date", "effectiveDate": "quarter-end holdings",
     "completeness": "quarter-end snapshots only; intra-quarter changes invisible",
     "identity": "CUSIP per holding", "license": "public", "reproducibility": "accession-addressed",
     "cost": "free", "actionsReachable": "BLOCKED (SEC refused Actions egress on all hosts, AGENTS.md v2.9/v2.23)",
     "thisEnvironment": "BLOCKED", "survivorship": "none",
     "verdict": "BEST_IDENTITY_CROSS_CHECK_BLOCKED_BY_SEC_EGRESS"},
    {"id": "wikipedia-revision-history", "kind": "public article revisions (components + yearly changes)",
     "depth": "years", "publicationDate": "revision timestamp", "effectiveDate": "as edited",
     "completeness": "crowd-maintained; known omissions", "identity": "ticker + name",
     "license": "CC BY-SA 4.0", "reproducibility": "revision ids",
     "cost": "free", "actionsReachable": "NOT_MEASURED (probe script prepared)",
     "thisEnvironment": "BLOCKED (en.wikipedia.org refused)", "survivorship": "low",
     "verdict": "UPSTREAM_OF_N100TICKERS; NON_AUTHORITATIVE"},
    {"id": "n100tickers", "kind": "derived yearly membership + dated changes (2007-2026)",
     "depth": "2007-02-01 .. 2026-09-26", "publicationDate": "NOT RECORDED (announcement dates absent)",
     "effectiveDate": "yes", "completeness": "chain-consistent; maintainers note known omissions (e.g. CMCSK)",
     "identity": "contemporaneous ticker only; no CUSIP/CIK; renames shown as remove+add",
     "license": "MIT", "reproducibility": "pinned commit + per-file SHA-256", "cost": "free",
     "actionsReachable": "NOT_MEASURED", "thisEnvironment": "SERVED (raw.githubusercontent.com)",
     "survivorship": "low (departed tickers retained)", "verdict": "USED_AS_PARTIAL_DERIVED_EVIDENCE"},
    {"id": "commercial-apis (Norgate, EODHD, Eulerpool)", "kind": "vendor PIT constituents",
     "depth": "vendor-specific", "publicationDate": "vendor-specific", "effectiveDate": "yes",
     "completeness": "unknown", "identity": "vendor ids", "license": "paid", "reproducibility": "vendor",
     "cost": "PAID (not priced, not purchased)", "actionsReachable": "NOT_MEASURED",
     "thisEnvironment": "NOT_PROBED", "survivorship": "vendor-specific", "verdict": "BLOCKED_PAID_SOURCE"},
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, payload) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    path.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def config_costs() -> dict:
    cfg = json.loads((ROOT / "config.json").read_text())
    node = cfg
    for key in COSTS_KEY:
        node = node[key]
    return {k: node[k] for k in ("commissionBps", "spreadBps", "sellTaxBps")}


# --------------------------------------------------------------------------- #
# Stage: compare (committed files only)
# --------------------------------------------------------------------------- #
def load_inputs():
    frame = D.read_snapshot(SNAPSHOT)
    spy = frame[frame.ticker == "SPY"].set_index("date")["totalReturnClose"]
    qqq = frame[frame.ticker == "QQQ"].set_index("date")["totalReturnClose"]
    fx = frame[frame.ticker == "SPY"].set_index("date")["usdKrw"]
    rates = json.loads(RATES.read_text())
    return spy, qqq, fx, rates


def comparison_payload() -> dict:
    """The comparison, computed from committed files only. Writes nothing."""
    spy, qqq, fx, rates = load_inputs()
    costs = config_costs()
    common = dict(fx=fx, usd_rate=rates["usdFedFundsPct"], krw_rate=rates["krwPolicyRatePct"], costs=costs)
    headline = C.compare(spy, qqq, start=C.HEADLINE_WINDOW[0], end=C.HEADLINE_WINDOW[1], **common)
    first = max(spy.index[0], qqq.index[0]).strftime("%Y-%m-%d")
    last = min(spy.index[-1], qqq.index[-1]).strftime("%Y-%m-%d")
    full = C.compare(spy, qqq, start=first, end=last, **common)
    full.pop("weekly")
    payload = {
        "id": "us-spy-qqq-comparison-v1",
        "evidenceClass": "DESCRIPTIVE_ETF_COMPARISON_NOT_ALPHA",
        "officialUsBenchmark": D.OFFICIAL_US_BENCHMARK,
        "growthAlternative": D.US_GROWTH_BENCHMARK,
        "snapshot": {"path": str(SNAPSHOT.relative_to(ROOT)), "sha256": sha256(SNAPSHOT)},
        "rates": {"path": str(RATES.relative_to(ROOT)), "sha256": sha256(RATES)},
        "headlineWindowSource": C.HEADLINE_WINDOW_SOURCE,
        "headline": headline,
        "fullSealedOverlap": full,
        "doesNotSupport": [
            "choosing a future SPY/QQQ weight from this sample",
            "any statement about stock-picking alpha",
            "a forecast that QQQ will keep outperforming",
        ],
    }
    return json.loads(json.dumps(payload, sort_keys=True, allow_nan=False))


def stage_compare() -> dict:
    payload = comparison_payload()
    dump(COMPARISON, payload)
    CHART.write_text(render_chart(payload["headline"]))
    return payload


def render_chart(headline: dict) -> str:
    """Two panels from observed weekly closes: log growth of 1 USD, and QQQ/SPY.

    Deterministic text, no fitted line, no projection past the last session.
    """
    import math
    pts = headline["weekly"]
    w, h, pad = 760, 220, 46
    n = len(pts)

    def xs(i):
        return pad + (w - 2 * pad) * i / (n - 1)

    def path(values, lo, hi, top):
        coords = [f"{xs(i):.1f},{top + h - 20 - (h - 40) * (v - lo) / (hi - lo):.1f}" for i, v in enumerate(values)]
        return "M" + " L".join(coords)

    spy = [math.log(p["spyNavUsd"]) for p in pts]
    qqq = [math.log(p["qqqNavUsd"]) for p in pts]
    rel = [p["qqqOverSpy"] for p in pts]
    lo, hi = min(spy + qqq), max(spy + qqq)
    rlo, rhi = min(rel + [1.0]), max(rel + [1.0])
    years = sorted({p["date"][:4] for p in pts})
    ticks = []
    for y in years[::2]:
        i = next(k for k, p in enumerate(pts) if p["date"][:4] == y)
        ticks.append(f'<text x="{xs(i):.1f}" y="{2 * h + 16}" font-size="10" text-anchor="middle">{y}</text>')
    base_y = h + h - 20 - (h - 40) * (1.0 - rlo) / (rhi - rlo)
    window = headline["window"]
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{2 * h + 40}" viewBox="0 0 {w} {2 * h + 40}" '
        'font-family="sans-serif">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{pad}" y="16" font-size="12">Growth of 1 USD, total return, log scale '
        f'({window["start"]} to {window["end"]}, {window["matchedSessions"]} matched sessions)</text>',
        f'<path d="{path(spy, lo, hi, 0)}" fill="none" stroke="#1f5fa8" stroke-width="1.5"/>',
        f'<path d="{path(qqq, lo, hi, 0)}" fill="none" stroke="#c0571b" stroke-width="1.5"/>',
        f'<text x="{pad}" y="34" font-size="11" fill="#1f5fa8">SPY: 1 to {pts[-1]["spyNavUsd"]:.2f}</text>',
        f'<text x="{pad}" y="48" font-size="11" fill="#c0571b">QQQ: 1 to {pts[-1]["qqqNavUsd"]:.2f}</text>',
        f'<text x="{pad}" y="{h + 16}" font-size="12">QQQ wealth / SPY wealth (above 1 = QQQ ahead since start; ends at {rel[-1]:.2f})</text>',
        f'<line x1="{pad}" x2="{w - pad}" y1="{base_y:.1f}" y2="{base_y:.1f}" stroke="#999" stroke-dasharray="3,3"/>',
        f'<path d="{path(rel, rlo, rhi, h)}" fill="none" stroke="#444" stroke-width="1.5"/>',
        *ticks,
        f'<text x="{pad}" y="{2 * h + 34}" font-size="10" fill="#666">Observed history only. A past difference is not '
        'a forecast and sets no portfolio weight.</text>',
        "</svg>", ""])


# --------------------------------------------------------------------------- #
# Stage: sealed (needs signal-history objects)
# --------------------------------------------------------------------------- #
def xnys_sessions(start: str, end: str) -> list[str]:
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS")
    return [d.strftime("%Y-%m-%d") for d in cal.sessions_in_range(start, end)]


def stage_sealed() -> None:
    reader = D.SealedReader(ROOT)
    sealed = D.extract_sealed(reader)
    checks = {t: D.series_checks(t, sealed["bars"][t], sealed["events"][t]) for t in ("SPY", "QQQ")}
    spy, qqq = checks["SPY"]["_close"], checks["QQQ"]["_close"]
    sessions = spy.index.union(qqq.index)
    fx = D.fx_on_sessions(sealed["fx"], sessions)
    snap_sha = D.write_snapshot(D.snapshot_rows(checks, fx), SNAPSHOT)
    rates_sha = dump(RATES, {"usdFedFundsPct": dict(sorted(sealed["fedFunds"].items())),
                             "krwPolicyRatePct": dict(sorted(sealed["krwPolicyRate"].items())),
                             "usdSource": "FRED DFF via replay-v16 macro component",
                             "krwSource": sealed["lineage"]["riskFreeKrw"]})
    xnys = xnys_sessions(str(sessions[0].date()), str(sessions[-1].date()))
    weekly_digests = {p.name: sha256(p) for p in sorted((ROOT / "docs/weekly-decision").glob("*.json"))}
    receipts_blob = subprocess.check_output(
        ["git", "rev-parse", f"{D.SOURCE_COMMIT}:ledger/weekly-decisions/receipts.jsonl"], cwd=ROOT).decode().strip()
    spy_multiples = {"status": "NOT_VERIFIABLE_FROM_SEALED_STORE",
                     "reason": ("SPY entered replay-v16 through benchmark_source._yahoo_close, which keeps only the "
                                "rebased Close; its distributions were never written to corporate-events. The same "
                                "fetch_prices(total_return=True) -> price_adjustment.to_total_return path built QQQ, "
                                "whose 64 distributions each read multiple 1.000.")}
    audit = {
        "id": "us-dual-benchmark-v1-data-audit",
        "evidenceClass": "OUTCOME_BLIND_DATA_AUDIT",
        "source": {"signalHistoryCommit": D.SOURCE_COMMIT, "replayManifest": D.REPLAY_MANIFEST,
                   **sealed["manifest"], "componentsUsed": len(sealed["componentsUsed"]),
                   "componentContentHashesVerified": True, "lineage": sealed["lineage"]},
        "roles": {"US_MARKET_BENCHMARK": "SPY", "US_GROWTH_BENCHMARK": "QQQ",
                  "officialUsBenchmark": D.OFFICIAL_US_BENCHMARK},
        "series": {t: D.public_checks(c) for t, c in checks.items()},
        "spyDistributionApplication": spy_multiples,
        "calendar": {t: D.calendar_checks(checks[t]["_close"].index, xnys) for t in ("SPY", "QQQ")},
        "pair": D.ratio_checks(spy, qqq),
        "fx": {"sessions": int(len(fx)), "missingOrStale": [d.strftime("%Y-%m-%d") for d in fx[fx.isna()].index],
               "maxAgeDays": D.MAX_FX_AGE_DAYS, "series": "FRED H.10 DEXKOUS"},
        "spySnapshotCrossCheck": spy_snapshot_check(reader, sealed["bars"]["SPY"]),
        "officialReplayReconciliation": replay_reconciliation(spy),
        "externalCorroboration": {
            "status": "NOT_PERFORMED",
            "reason": ("no free independent price host is reachable from this environment (Yahoo, Nasdaq, Stooq, "
                       "SEC refused by the egress proxy) and the probe dispatch was refused (HTTP 403). "
                       "scripts/probe_nasdaq100_sources.py fetches Nasdaq raw closes and distributions for both "
                       "ETFs, but it is not wired into .github/workflows/probes.yml because that file is hash-pinned by "
                       "two sealed KR specs; running it is an owner decision.")},
        "snapshot": {"path": str(SNAPSHOT.relative_to(ROOT)), "sha256": snap_sha, "rows": 2 * len(spy)},
        "rates": {"path": str(RATES.relative_to(ROOT)), "sha256": rates_sha},
        "protected": {"weeklyDecisionDocsSha256": weekly_digests,
                      "signalHistoryReceiptsBlob": receipts_blob,
                      "configBenchmarksUS": json.loads((ROOT / "config.json").read_text())["benchmarks"]["US"]},
    }
    dump(DATA_AUDIT, audit)
    finnhub = _finnhub(reader)
    n100 = stage_n100(finnhub[1])
    coverage = stage_coverage(reader, n100["_spans"], finnhub)
    dump(MANIFEST, {
        "id": "us-dual-benchmark-v1", "kind": "RESEARCH_DATASET_NOT_A_SEALED_INPUT",
        "files": {str(p.relative_to(ROOT)): sha256(p)
                  for p in sorted([SNAPSHOT, RATES, COVERAGE_CSV, *N100_DIR.glob("*")])},
        "builtFrom": {"signalHistoryCommit": D.SOURCE_COMMIT, "replayManifestSha256": D.REPLAY_MANIFEST_SHA256,
                      "n100tickersCommit": N100_SOURCE["commit"]},
        "coverageSummary": coverage["summary"]["union"],
    })


def spy_snapshot_check(reader, bars) -> dict:
    rows = [json.loads(line) for line in
            gzip.decompress(reader.blob("ledger/benchmarks/SPY.jsonl.gz")).decode().split("\n") if line.strip()]
    snap = {r["date"]: r["close"] for r in rows}
    common = sorted(set(snap) & set(bars))
    worst = max(abs(bars[d]["Close"] / snap[d] - 1) for d in common)
    return {"ledgerBenchmarksSpySessions": len(snap), "commonSessions": len(common),
            "maxRelativeDifference": worst,
            "note": "same vendor lineage; a consistency check, not an independent corroboration"}


def replay_reconciliation(spy: pd.Series) -> dict:
    official = json.loads((ROOT / "docs/us-readiness/weekly-passive-first-v1-weekly-us-local-currency.json").read_text())
    start, end = C.HEADLINE_WINDOW
    years = C.span_years(pd.Timestamp(start), pd.Timestamp(end))
    ours = (spy.loc[pd.Timestamp(end)] / spy.loc[pd.Timestamp(start)]) ** (1 / years) - 1
    return {"officialP1SpyUsdCagrPct": official["paths"]["P1"]["cagrPct"],
            "thisSnapshotSpyUsdCagrPct": round(ours * 100, 3),
            "differencePctPt": round(ours * 100 - official["paths"]["P1"]["cagrPct"], 3),
            "officialSource": "docs/us-readiness/weekly-passive-first-v1-weekly-us-local-currency.json",
            "note": "official path includes its entry transaction cost and weekly block chaining; this is gross close-to-close"}


def swap_identity(removed: str, added: str, note: str, ciks: dict) -> str:
    a, b = ciks.get(removed), ciks.get(added)
    if a and b:
        return "SAME_CIK_RENAME" if a == b else "DIFFERENT_CIK_REPLACEMENT"
    if "ticker change" in note.lower() or " became " in note:
        return "RENAME_PER_SOURCE_NOTE_UNVERIFIED"
    return "UNRESOLVED_NO_IDENTIFIER"


def stage_n100(ciks: dict) -> dict:
    docs, shas = {}, {}
    for path in sorted(N100_DIR.glob("n100-ticker-changes-*.yaml")):
        doc = N.parse_yearly_yaml(path.read_text())
        docs[doc["year"]] = doc
        shas[doc["year"]] = sha256(path)
    chain = N.chain_consistency(docs)
    events = N.events_from_yearly(docs, N100_SOURCE["id"], shas)
    base = N.BaseSnapshot(sourceId=N100_SOURCE["id"], sourceSha256=shas[2013], asOfDate="2013-01-01",
                          publishedDate="2013-01-01",
                          members=tuple(N.Security(t, issuer="") for t in docs[2013]["tickers_on_Jan_1"]))
    in_window = [e for e in events if STUDY_START < e.effectiveDate <= STUDY_END]
    spans = N.membership_intervals(docs, STUDY_START, STUDY_END)
    counts = {}
    for year in range(2013, 2027):
        for md in ("01-01", "07-01"):
            date = f"{year}-{md}"
            if date <= STUDY_END:
                counts[date] = N.membership_knowable_on(date, base, events)["memberCount"]
    spot = []
    for check in SEARCH_SURFACED_SPOT_CHECKS:
        year = int(check["effective"][:4])
        ops = docs[year]["changes"].get(check["effective"], {})
        spot.append({**check, "derivedAdded": ops.get("union", []), "derivedRemoved": ops.get("difference", []),
                     "agrees": set(check["added"]) <= set(ops.get("union", []))
                     and set(check["removed"]) <= set(ops.get("difference", [])),
                     "referenceStatus": "SEARCH_SURFACED_TITLE_NOT_FETCHED"})
    renames = [{"date": e.effectiveDate, "removed": e.removed[0].tickerAtEvent,
                "added": e.added[0].tickerAtEvent, "note": e.note,
                "identity": swap_identity(e.removed[0].tickerAtEvent, e.added[0].tickerAtEvent, e.note, ciks)}
               for e in in_window if len(e.added) == 1 and len(e.removed) == 1]
    recon = N.classify_reconstruction(base, in_window, 2013, 2025)
    recon["status"] = N.PARTIAL                 # derived source, no announcement dates, no identifiers
    payload = {
        "id": "nasdaq100-pit-membership-v1",
        "evidenceClass": "OUTCOME_BLIND_SOURCE_AUDIT",
        "verdict": "PARTIAL",
        "verdictReasons": [
            "membership comes from one DERIVED, non-authoritative source (n100tickers, MIT), not from Nasdaq",
            "announcement dates are absent: changes are usable only from their effective date (conservative)",
            "no CUSIP/CIK: identity rests on contemporaneous tickers; 1-for-1 swaps may be renames or replacements",
            "the maintainers record known omissions (e.g. Comcast CMCSK, 2014-12-22)",
            "no authoritative cross-check could be fetched here (Nasdaq, SEC, Wikipedia refused by egress)",
        ],
        "source": N100_SOURCE, "fileSha256": {str(y): s for y, s in shas.items()},
        "candidates": SOURCE_CANDIDATES,
        "chainConsistency": {"years": len(chain), "inconsistentYears": [c for c in chain if not c["consistent"]]},
        "studyWindow": [STUDY_START, STUDY_END],
        "eventsInWindow": len(in_window),
        "annualReconstitutionsDetected": sorted(e.effectiveDate for e in in_window
                                                if e.kind == "ANNUAL_RECONSTITUTION"),
        "reconstruction": recon,
        "memberCounts": counts,
        "symbolsEverMember": len(spans),
        "oneForOneSwapsForIdentityReview": renames,
        "oneForOneSwapIdentityCounts": dict(Counter(r["identity"] for r in renames)),
        "spotChecks": spot,
        "informationAvailabilityRule": ("a change is used from knowableFrom = announcementDate if evidenced, "
                                        "else effectiveDate; today's list is never back-filled"),
        "spans": {t: s for t, s in sorted(spans.items())},
    }
    dump(N100_AUDIT, payload)
    payload["_spans"] = spans
    return payload


def _price_panels(reader) -> dict:
    manifest = reader.manifest()
    spans: dict[str, list[str]] = {}
    for name in sorted(manifest["components"]):
        if not (name.startswith("price/") and name[6:8] in ("19", "20")):
            continue
        for ref in manifest["components"][name]:
            for row in reader.component(ref):
                t, d = row["ticker"], row["date"]
                if t.endswith(".KS") or row.get("Close") is None:
                    continue
                cur = spans.setdefault(t, [d, d])
                cur[0], cur[1] = min(cur[0], d), max(cur[1], d)
    return {t: {"first": a, "last": b} for t, (a, b) in spans.items()}


def _universe(reader) -> dict:
    manifest = reader.manifest()
    rows = reader.component(manifest["components"]["universe"][0])
    return {t: v for t, v in rows[0]["memberships"].items() if v.get("region") == "US"}


def _finnhub(reader) -> tuple[dict, dict, int]:
    listing = subprocess.check_output(["git", "ls-tree", "--name-only", f"{D.SOURCE_COMMIT}:ledger/fundamentals/us"],
                                      cwd=ROOT).decode().split()
    counts, ciks, total = Counter(), {}, 0
    for name in sorted(listing):
        if not (name.startswith("finnhub-") and name.endswith(".jsonl.gz")):
            continue
        for line in gzip.decompress(reader.blob("ledger/fundamentals/us/" + name)).decode().split("\n"):
            if not line.strip():
                continue
            row = json.loads(line)
            counts[row["ticker"]] += 1
            ciks.setdefault(row["ticker"], row.get("cik"))
            total += 1
    return dict(counts), ciks, total


def stage_coverage(reader, n100_spans, finnhub) -> dict:
    v3 = json.loads((ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json").read_text())
    identity = v3["regions"]["US"]["identity"]
    category = {t: c for c, ts in identity["categories"].items() for t in ts}
    successors = {t: r["pricedBy"] for t, r in identity["renames"].items() if r.get("pricedBy")}
    unpriced = {m["ticker"] for m in json.loads((ROOT / "data/us-unpriced-members.json").read_text())["members"]}
    sp500 = _universe(reader)
    malformed = {k.upper(): v for k, v in identity["malformed"].items()}
    for key in [k for k in sp500 if k.upper() in malformed]:   # resolved upstream key errors
        info = malformed[key.upper()]
        sp500.pop(key)
        category.setdefault(info["resolvedTo"], category.get(info["resolvedTo"]))
    prices = _price_panels(reader)
    filings, ciks, total = finnhub
    rows = U.build_manifest(start=STUDY_START, end=STUDY_END, sp500=sp500, sp500_identity=category,
                            sp500_unpriced=unpriced, n100_spans=n100_spans, prices=prices,
                            filings=filings, ciks=ciks, successors=successors)
    buf = io.StringIO()
    fields = ["symbol", "status", "gaps", "inSp500", "inNasdaq100", "sp500Span", "nasdaq100Spans",
              "sp500IdentityCategory", "renameSuccessor", "pricePanel", "priceCovered", "freeVendorRefused",
              "fundamentalFilings", "cik", "membershipEvidence"]
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: (json.dumps(row[k], separators=(",", ":")) if isinstance(row[k], (list, dict))
                             else row[k]) for k in fields})
    COVERAGE_CSV.write_bytes(gzip.compress(buf.getvalue().encode(), compresslevel=9, mtime=0))
    n100_only_unpriced = [r["symbol"] for r in rows if r["inNasdaq100"] and not r["inSp500"] and not r["priceCovered"]]
    payload = {
        "id": "us-universe-coverage-gap-v1", "evidenceClass": "OUTCOME_BLIND_COVERAGE_AUDIT",
        "window": [STUDY_START, STUDY_END],
        "inputs": {"sp500Membership": "replay-v16 sealed universe component (US)",
                   "sp500Identity": "docs/results/alpha-opportunity-model-v3-survivorship-audit.json",
                   "freeVendorRefused": "data/us-unpriced-members.json",
                   "nasdaq100Membership": N100_SOURCE["id"],
                   "prices": "replay-v16 sealed price panels (Yahoo unadjusted with actions)",
                   "fundamentals": f"signal-history@{D.SOURCE_COMMIT[:8]} ledger/fundamentals/us (Finnhub)"},
        "finnhubStoreMeasured": {"tickers": len(filings), "filings": total,
                                 "readinessDocStated": {"tickers": 782, "filings": 34941,
                                                        "note": "us-source-readiness-v1 excluded 4 filings with abnormal fiscal years"}},
        "statusPrecedence": list(U.PRECEDENCE),
        "summary": U.summarize(rows),
        "nasdaq100OnlyWithoutPrices": n100_only_unpriced,
        "manifest": {"path": str(COVERAGE_CSV.relative_to(ROOT)), "sha256": sha256(COVERAGE_CSV), "rows": len(rows)},
    }
    dump(COVERAGE, payload)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "sealed", "compare"), default="all")
    args = parser.parse_args(argv)
    if args.stage in ("all", "sealed"):
        stage_sealed()
    if args.stage in ("all", "compare"):
        result = stage_compare()
        h = result["headline"]
        print(json.dumps({"window": h["window"], "SPY": h["usd"]["SPY"]["cagrPct"],
                          "QQQ": h["usd"]["QQQ"]["cagrPct"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
