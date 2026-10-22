"""kr-selection-challenger-v2-accounting — the H2 accounting book, recorded prospectively (paper only).

v1 ranks KR names on price information only. This study adds the one information family the live production build does not use: point-in-
time DART accounting. Each weekly decision session it records the names that are cheap against their own sector AND whose business confirms
the price (positive net income, positive operating cash flow, improving operating cash flow), exactly the rule of `kr_alpha_signal_v2`
(no fitted parameter), against three controls: the same rule's cheap-but-UNCONFIRMED names (does the confirmation matter?), the production
alpha's own top five, and 069500.KS. Frozen design: ``docs/research-program/specs/kr-selection-challenger-v2-accounting.json``.

Nothing is new about the rule or the information: H2 / X1 were measured on the closed historical sample. What is new is the evidence, recorded
at the close it describes and graded after maturity, exactly as in v1, whose session gate, outcome arithmetic, statistics and risk path this
module calls rather than copies.

Inputs, all signal-time facts:
    accounting   ``<ledger>/fundamentals/kr-canonical-v2`` filings, visible strictly before the signal date (``visible_filings``) and derived by
                 ``kr_value_quality_catalyst.accounting_values``. The live ``kr`` store is not used: on 2026-10-16 it carries net income TTM
                 for 24 of 119 names, the canonical store for 115 (the label defect of v2.33).
    market       production ``marketCap`` and ``sector`` (the sector is a stated proxy for the registered KRX industry);
    liquidity    the last 60 KR sessions of vendor bars, aligned to the exchange calendar by ``kr_bar_integrity``.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import statistics
from pathlib import Path

import pandas as pd

from . import kr_alpha_signal_v2 as S2
from . import kr_bar_integrity as BI
from . import kr_selection_challenger as V1
from . import kr_value_quality_catalyst as VQ
from . import prospective_receipt_core as CORE
from . import weekly_publish as P

ROOT = V1.ROOT
STUDY = "kr-selection-challenger-v2-accounting"
SPEC_PATH = "docs/research-program/specs/kr-selection-challenger-v2-accounting.json"
SCHEMA_VERSION = 1
LIVE, SYNTHETIC = V1.LIVE, V1.SYNTHETIC
EVIDENCE_CLASS_BY_PATHWAY = V1.EVIDENCE_CLASS_BY_PATHWAY
BOOKS = ("CH_VALUE_CONFIRMED", "CTRL_CHEAP_UNCONFIRMED", "CTRL_MODEL5")
CHALLENGERS = ("CH_VALUE_CONFIRMED",)
BENCHMARK = V1.BENCHMARK
SLOTS = V1.SLOTS
STORE = "fundamentals/kr-canonical-v2"
LIQUIDITY_SESSIONS = 60
MIN_PRICED_SHARE = 0.5     # fewer names with a signal-session row than this means the download failed: no receipt, the next run retries
LIQUIDITY_FETCH = {"auto_adjust": False}   # as-traded close (split-consistent, not dividend-adjusted) x volume = KRW traded
TRADED_VALUE_BASIS = "AS_TRADED_CLOSE_X_VOLUME_SPLIT_CONSISTENT_NOT_DIVIDEND_ADJUSTED"
KEY_FIELDS = V1.KEY_FIELDS


# --------------------------------------------------------------------------- #
# Frozen design
# --------------------------------------------------------------------------- #
def load_spec(root=ROOT, *, verify_code=True) -> dict:
    spec = json.loads((Path(root) / SPEC_PATH).read_text(encoding="utf-8"))
    if spec.get("studyId") != STUDY or int(spec["construction"]["slots"]) != SLOTS:
        raise ValueError("SPEC_STUDY_MISMATCH")
    if verify_code:
        for rel, pinned in sorted(spec["codeFileHashes"].items()):
            if V1.file_sha256(Path(root) / rel) != pinned:
                raise ValueError("CODE_CHANGED_SINCE_REGISTRATION: " + rel)
    return spec


def spec_sha256(root=ROOT) -> str:
    return V1.file_sha256(Path(root) / SPEC_PATH)


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
def load_accounting(ledger_dir) -> tuple[dict, dict]:
    """Canonical filings by ticker, and the store's own identity (file digests and newest availability), from the signal-history ledger."""
    directory = Path(ledger_dir) / STORE
    files = sorted(directory.glob("dart-*.jsonl.gz"))
    if not files:
        raise ValueError("ACCOUNTING_STORE_MISSING: " + str(directory))
    by_ticker, newest, digests = {}, None, {}
    for path in files:
        digests[path.name] = V1.file_sha256(path)
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    row = json.loads(line)
                    by_ticker.setdefault(row.get("ticker"), []).append(row)
                    stamp = row.get("availableFrom")
                    newest = stamp if stamp and (newest is None or stamp > newest) else newest
    return by_ticker, {"store": STORE, "files": digests, "newestAvailableFrom": newest}


def is_common_share(ticker: str) -> bool:
    """KRX six-digit codes of common shares end in 0; preferred classes end in 5, 7 or 9. A stated heuristic, never a guess at 'common'."""
    return bool(V1.TICKER.match(ticker)) and ticker[5] == "0"


def liquidity_evidence(frame, session: str) -> dict:
    """The liquidity facts of one name on the exchange calendar ending at ``session``, with the session states behind them.

    ``positiveVolumeSessions20`` counts traded sessions among the last 20; ``medianTradedValue60Krw`` is the median close x volume over the last
    60 and exists only when all 60 traded. ``states`` tallies those 60 sessions (``SESSION_MISSING`` = an open session with no vendor row,
    ``SUSPENDED`` = a row with zero volume) and ``offCalendarRows`` the vendor rows dated on a closed day, which are dropped, not sessions.
    ``signalSessionRow`` says whether the vendor delivered a row for the signal session itself: a frame that stops earlier is a stale or
    truncated download, never a collected name.

    Traded value is the KRW actually traded: the close AS TRADED times the volume, both on the vendor's split-consistent basis, so a split
    cancels in the product. The frames must therefore come from ``fetch_prices(..., auto_adjust=False)``: a dividend-adjusted close would
    scale every earlier session's value down by the accumulated dividend factor while the volume stays as traded."""
    if frame is None:
        return {"positiveVolumeSessions20": None, "medianTradedValue60Krw": None, "basis": "NO_VENDOR_FRAME", "signalSessionRow": False}
    end = pd.Timestamp(session)
    aligned = BI.calendar_frame(frame, start=end - pd.Timedelta(days=130), end=end)
    if session not in {str(d.date()) for d in aligned.index} or len(aligned) < LIQUIDITY_SESSIONS:
        return {"positiveVolumeSessions20": None, "medianTradedValue60Krw": None, "basis": "CALENDAR_WINDOW_SHORT", "signalSessionRow": False}
    last = aligned.iloc[-LIQUIDITY_SESSIONS:]
    traded = last["state"].isin(["VALID", "RANGE_UNRESOLVED"]) & (last["Volume"] > 0)
    window = BI.summary(last)
    out = {"positiveVolumeSessions20": int(traded.iloc[-20:].sum()), "medianTradedValue60Krw": None,
           "states": {k: v for k, v in window["states"].items() if v}, "offCalendarRows": int(aligned.attrs.get("offCalendarRows") or 0),
           "basis": "ALL_60_TRADED" if traded.all() else "NOT_ALL_60_TRADED", "signalSessionRow": last["state"].iloc[-1] != "SESSION_MISSING"}
    if traded.all():
        out["medianTradedValue60Krw"] = float(statistics.median((last["Close"] * last["Volume"]).tolist()))
    return out


def liquidity(frame, session: str) -> tuple[int | None, float | None]:
    """(traded sessions among the last 20, median close x volume over the last 60) on the exchange calendar ending at ``session``.

    A missing, suspended or invalid session is not a traded one; the median exists only when all 60 sessions traded."""
    e = liquidity_evidence(frame, session)
    return e["positiveVolumeSessions20"], e["medianTradedValue60Krw"]


def liquidity_summary(evidence: dict) -> dict:
    """Counts over the cross-section: who had bars, who traded all 20, who has a 60-session median, who clears the floor, and the session
    states behind the misses. Missing data is counted, never filled."""
    rows = list(evidence.values())
    states, off = {}, 0
    for e in rows:
        for state, n in (e.get("states") or {}).items():
            states[state] = states.get(state, 0) + int(n)
        off += int(e.get("offCalendarRows") or 0)
    floor = S2.MIN_MEDIAN_TRADED_VALUE_KRW
    return {"names": len(rows), "tradedValueBasis": TRADED_VALUE_BASIS,
            "signalSessionRowPresent": sum(bool(e.get("signalSessionRow")) for e in rows),
            "noVendorFrame": sum(e["basis"] == "NO_VENDOR_FRAME" for e in rows),
            "calendarWindowShort": sum(e["basis"] == "CALENDAR_WINDOW_SHORT" for e in rows),
            "traded20of20": sum(e["positiveVolumeSessions20"] == 20 for e in rows),
            "median60Measured": sum(e["medianTradedValue60Krw"] is not None for e in rows),
            "aboveMedianFloor": sum((e["medianTradedValue60Krw"] or 0) >= floor for e in rows),
            "minMedianTradedValueKrw": floor, "sessionStates60": dict(sorted(states.items())), "offCalendarRowsDropped": off}


def signal_rows(site: dict, session: str, accounting: dict, frames: dict, liquidity_out: dict | None = None) -> tuple[list[dict], dict]:
    """``kr_alpha_signal_v2`` input rows for the production KR cross-section, and the production alpha by ticker for the control book.
    ``liquidity_out``, when given, receives each name's ``liquidity_evidence``."""
    blob = ((site.get("longTerm") or {}).get("regions") or {}).get("KR") or {}
    details = site.get("details") or {}
    rows, alpha, seen = [], {}, set()
    for item in blob.get("validationCrossSection") or []:
        ticker = item.get("ticker")
        if not isinstance(ticker, str) or not V1.TICKER.match(ticker) or ticker in seen:
            continue
        seen.add(ticker)
        detail = details.get(ticker) or {}
        values, provenance = VQ.accounting_values(accounting.get(ticker, []), session)
        cap = V1._number(item.get("marketCap"))
        ni, ocf, assets = values.get("netIncomeTtm"), values.get("ocfTtm"), values.get("assets")
        prior = values.get("priorOcfTtm")
        evidence = liquidity_evidence(frames.get(ticker), session)
        sessions20, traded = evidence["positiveVolumeSessions20"], evidence["medianTradedValue60Krw"]
        if liquidity_out is not None:
            liquidity_out[ticker] = evidence
        rows.append({
            "ticker": ticker, "industry": item.get("sector") or None, "isPreferredShare": not is_common_share(ticker),
            "priceAsOf": detail.get("asOf") if detail.get("asOf") == session else None,
            "positiveVolumeSessions20": sessions20, "medianTradedValue60Krw": traded,
            "fundamentalsAvailableFrom": provenance.get("availableFrom"),
            "bookToMarketProxy": VQ.ratio(values.get("totalBookEquity"), cap), "earningsYieldProxy": VQ.ratio(ni, cap),
            "netIncomeToAssets": VQ.ratio(ni, assets), "ocfToAssets": VQ.ratio(ocf, assets),
            "ocfImprovementToAssets": VQ.ratio(ocf - prior if ocf is not None and prior is not None else None, assets)})
        alpha[ticker] = V1._number(item.get("alpha"))
    return rows, alpha


# --------------------------------------------------------------------------- #
# Books
# --------------------------------------------------------------------------- #
def _fill(ranked, construction, industry):
    """Five equal slots in rank order, at most two per sector; the same rule as v1's books."""
    slots, per = [], {}
    for rank, (ticker, value, close) in enumerate(ranked, start=1):
        if len(slots) == int(construction["slots"]):
            break
        sector = industry.get(ticker) or "UNCLASSIFIED"
        if per.get(sector, 0) >= int(construction["maxNamesPerSector"]):
            continue
        per[sector] = per.get(sector, 0) + 1
        slots.append({"ticker": ticker, "sector": sector, "rank": rank, "featureValue": round(value, 6), "signalClose": close})
    return slots


def build_books(site: dict, session: str, records: list[dict], alpha: dict, spec: dict) -> tuple[dict, dict]:
    construction = spec["construction"]
    details = site.get("details") or {}
    close = {t: V1._number((details.get(t) or {}).get("lastClose")) for t in alpha}
    industry = {r["ticker"]: r["industry"] for r in records}
    readiness = S2.readiness(records)
    eligible = [r for r in records if r["state"] != "INELIGIBLE"]
    out = {}

    def book(state, ranked):
        base = {"slotFraction": float(construction["slotFraction"]), "eligibleNames": len(ranked)}
        if not readiness["ready"] or len(eligible) < int(construction["minEligibleNames"]):
            return {**base, "status": "THIN_CROSS_SECTION" if readiness["ready"] else "BLOCKED_COVERAGE",
                    "slots": [], "fallbackSlots": SLOTS}
        slots = _fill(ranked, construction, industry)
        return {**base, "status": state, "slots": slots, "fallbackSlots": SLOTS - len(slots)}
    for name, state in (("CH_VALUE_CONFIRMED", "CHEAP_CONFIRMED"), ("CTRL_CHEAP_UNCONFIRMED", "CHEAP_UNCONFIRMED")):
        ranked = sorted(((r["ticker"], r["valuePercentile"], close.get(r["ticker"])) for r in records if r["state"] == state),
                        key=lambda x: (-x[1], x[0]))
        out[name] = book("BOOK_FORMED", [x for x in ranked if x[2] is not None and x[2] > 0])
    model = sorted(((r["ticker"], alpha[r["ticker"]], close.get(r["ticker"])) for r in eligible
                    if alpha.get(r["ticker"]) is not None and close.get(r["ticker"])), key=lambda x: (-x[1], x[0]))
    out["CTRL_MODEL5"] = book("BOOK_FORMED", model)
    return out, readiness


# --------------------------------------------------------------------------- #
# Receipts
# --------------------------------------------------------------------------- #
REQUIRED = ("schemaVersion", "studyId", "pathway", "specSha256", "designDigest", "codeIdentity", "authorization", "signalDate",
            "executionDate", "createdAtUtc", "sourceArtifact", "accountingStore", "coverage", "readiness", "liquidityDiagnostics", "books", "benchmark",
            "horizonsSessions", "researchOnly", "productionEffect", "evidenceClass", "receiptSha256")


def validate_receipt(receipt: dict, *, pathway: str) -> None:
    missing = [k for k in REQUIRED if k not in receipt]
    if missing:
        raise ValueError("RECEIPT_FIELDS_MISSING: " + ",".join(missing))
    if receipt["studyId"] != STUDY or receipt["pathway"] != pathway or receipt["evidenceClass"] != EVIDENCE_CLASS_BY_PATHWAY[pathway]:
        raise ValueError("RECEIPT_PATHWAY_MISMATCH")
    if receipt["productionEffect"] != "NONE" or receipt["researchOnly"] is not True:
        raise ValueError("RECEIPT_CLAIMS_PRODUCTION_EFFECT")
    if CORE.receipt_digest(receipt) != receipt["receiptSha256"]:
        raise ValueError("RECEIPT_DIGEST_MISMATCH")
    CORE.scan_for_outcome_keys(receipt)
    for book in BOOKS:
        blob = receipt["books"][book]
        if len(blob["slots"]) + blob["fallbackSlots"] != SLOTS or len({s["ticker"] for s in blob["slots"]}) != len(blob["slots"]):
            raise ValueError("BOOK_SLOTS_INVALID: " + book)


def build_receipt(site: dict, site_sha256: str, *, pathway: str, created_at_utc, now_utc, merged_at_utc, code_identity: dict,
                  spec: dict, spec_digest: str, accounting: dict, store_identity: dict, frames: dict) -> dict:
    if pathway not in EVIDENCE_CLASS_BY_PATHWAY:
        raise ValueError("UNKNOWN_PATHWAY")
    if (reason := P.unsafe_reason(site)) is not None or (site.get("meta") or {}).get("syntheticData"):
        raise ValueError("UNSAFE_ARTIFACT: " + str(reason or "SEED_OR_SYNTHETIC_ARTIFACT"))
    if not CORE.is_sha256(site_sha256) or not CORE.is_sha256(spec_digest):
        raise ValueError("IDENTITY_REQUIRED")
    if not CORE.is_git_sha(code_identity.get("commitSha")) or not code_identity.get("files"):
        raise ValueError("CODE_IDENTITY_REQUIRED")
    session = V1.signal_session(site)
    floor = spec["schedule"]["firstEligibleSignalSessionFloor"]
    if session < floor:
        raise ValueError("SIGNAL_BEFORE_REGISTERED_FLOOR: " + floor)
    execution = CORE.check_timing(signal_date=session, created_at_utc=created_at_utc, now_utc=now_utc, merged_at_utc=merged_at_utc)
    evidence = {}
    rows, alpha = signal_rows(site, session, accounting, frames, evidence)
    universe = len(rows)
    # A name counts as collected only if the vendor delivered its signal-session row: a frame that exists but stops earlier is a stale
    # download, and counting it would let a run that never saw the signal session pass the download check.
    collected = sum(1 for e in evidence.values() if e.get("signalSessionRow"))
    if universe and collected / universe < MIN_PRICED_SHARE:
        raise ValueError("PRICE_FETCH_INCOMPLETE: %d of %d names have a vendor row on the signal session" % (collected, universe))
    records = S2.cross_section(rows, session)
    books, readiness = build_books(site, session, records, alpha, spec)
    provenance = site.get("provenance") or {}
    receipt = {
        "schemaVersion": SCHEMA_VERSION, "studyId": STUDY, "pathway": pathway, "specSha256": spec_digest,
        "designDigest": S2.design_digest(),
        "codeIdentity": {"commitSha": code_identity["commitSha"], "files": dict(sorted(code_identity["files"].items()))},
        "authorization": {"basis": "MERGE_OF_THE_REGISTERED_SPEC", "mergedAtUtc": str(CORE.utc(merged_at_utc).isoformat()),
                          "firstProspectiveSession": str(CORE.first_prospective_session(merged_at_utc).date()), "registeredFloor": floor},
        "signalDate": session, "executionDate": str(execution.date()), "createdAtUtc": str(CORE.utc(created_at_utc).isoformat()),
        "sourceArtifact": {"siteDataSha256": site_sha256, "siteGeneratedAt": site.get("generatedAt"),
                           "buildCommitSha": provenance.get("buildCommitSha"),
                           "modelVersion": provenance.get("modelVersion") or site.get("modelVersion")},
        "accountingStore": dict(store_identity), "coverage": S2.coverage(records), "readiness": readiness,
        "signal": [{k: r[k] for k in ("ticker", "industry", "state", "ineligibility", "valuePercentile", "confirmationFlags")}
                   for r in records],
        "liquidityDiagnostics": {"summary": liquidity_summary(evidence), "names": dict(sorted(evidence.items()))},
        "books": books, "benchmark": BENCHMARK, "horizonsSessions": list(spec["horizonsSessions"]),
        "researchOnly": True, "productionEffect": "NONE", "evidenceClass": EVIDENCE_CLASS_BY_PATHWAY[pathway],
    }
    receipt["receiptSha256"] = CORE.receipt_digest(receipt)
    validate_receipt(receipt, pathway=pathway)
    return receipt


def append_receipt(path, receipt, *, pathway: str) -> str:
    return CORE.append(path, receipt, validate=lambda r: validate_receipt(r, pathway=pathway), key_fields=KEY_FIELDS)


def read_receipts(path, *, pathway: str) -> list[dict]:
    return CORE.read_ledger(path, lambda r: validate_receipt(r, pathway=pathway))


# --------------------------------------------------------------------------- #
# Outcomes and assessment: v1's arithmetic and statistics, this study's books
# --------------------------------------------------------------------------- #
def build_outcome(receipt: dict, *, horizon: int, frames: dict, now_utc, pathway: str) -> dict:
    validate_receipt(receipt, pathway=pathway)
    execution = receipt["executionDate"]
    if horizon not in receipt["horizonsSessions"]:
        raise ValueError("HORIZON_NOT_REGISTERED")
    if not CORE.has_matured(execution, horizon, now_utc):
        raise ValueError("HORIZON_NOT_MATURED")
    maturity = str(CORE.maturity_session(execution, horizon).date())
    span = {t: BI.calendar_frame(f, start=execution, end=maturity) for t, f in frames.items() if f is not None}
    b_in, b_out = BI.traded_close(span.get(BENCHMARK), execution), BI.traded_close(span.get(BENCHMARK), maturity)
    record = {"evidenceClass": CORE.OUTCOME_EVIDENCE_CLASS if pathway == LIVE else "SYNTHETIC_FIXTURE", "studyId": STUDY,
              "receiptSha256": receipt["receiptSha256"], "signalDate": receipt["signalDate"], "executionDate": execution,
              "horizonSessions": int(horizon), "maturitySession": maturity, "createdAtUtc": str(CORE.utc(now_utc).isoformat()),
              "priceBasis": "VENDOR_ADJUSTED_CLOSE_BOTH_LEGS"}
    if b_in is None or b_out is None:
        record.update({"status": "BENCHMARK_UNPRICED", "books": None})
    else:
        bench = b_out / b_in - 1.0
        tickers = sorted({s["ticker"] for book in BOOKS for s in receipt["books"][book]["slots"]})
        names = {t: V1.name_outcome(span.get(t), execution, maturity, bench) for t in tickers}
        record.update({"status": "COMPLETE", "benchmarkReturn": bench, "names": names,
                       "books": {book: V1.book_result(receipt["books"][book], names, execution=execution, maturity=maturity)
                                 for book in BOOKS}})
    record.update(V1.resolution(record, now_utc))      # v1's retry rule: a transient vendor failure is DEFERRED, never a permanent None
    record["recordSha256"] = hashlib.sha256(CORE.canonical(record)).hexdigest()
    return record


def validate_outcome(record: dict, *, pathway: str) -> None:
    expected = CORE.OUTCOME_EVIDENCE_CLASS if pathway == LIVE else "SYNTHETIC_FIXTURE"
    if record.get("resolution") == "DEFERRED":
        raise ValueError("OUTCOME_DEFERRED_IS_NEVER_A_RECORD")
    if record.get("studyId") != STUDY or record.get("evidenceClass") != expected:
        raise ValueError("OUTCOME_PATHWAY_MISMATCH")
    if hashlib.sha256(CORE.canonical({k: v for k, v in record.items() if k != "recordSha256"})).hexdigest() != record.get("recordSha256"):
        raise ValueError("OUTCOME_DIGEST_MISMATCH")


def read_outcomes(path, *, pathway: str) -> list[dict]:
    return CORE.read_ledger(path, lambda r: validate_outcome(r, pathway=pathway))


def assess(receipts: list[dict], outcomes: list[dict], spec: dict, *, path_metrics: dict | None = None) -> dict:
    """v1's registered rule for one challenger, plus the mechanism check: confirmed must beat unconfirmed cheap names on mean."""
    rule = spec["assessment"]
    harm, primary = rule["harmCheck"], rule["primary"]
    receipts = sorted(receipts, key=lambda r: r["signalDate"])
    out = {"studyId": STUDY, "receipts": len(receipts), "outcomes": len(outcomes),
           "turnover": {b: V1.turnover(receipts, b) for b in BOOKS}, "challengers": {}}
    book = CHALLENGERS[0]
    verdict = {"verdict": "ACCUMULATING"}
    cohort = receipts[:harm["cohortReceipts"]]
    if len(cohort) == harm["cohortReceipts"] and V1._due(cohort, outcomes, harm["horizonSessions"]):
        ci = V1.interval(V1._series(cohort, outcomes, harm["horizonSessions"], book), harm["horizonSessions"], harm["z"])
        if len(cohort) - ci["n"] > harm["maxIncompleteReceipts"]:
            ci["result"] = "INCONCLUSIVE_DATA"
        elif ci["upper"] is not None and ci["upper"] < 0:
            ci["result"] = "HARM"
            verdict["verdict"] = "STOPPED_HARM"
        else:
            ci["result"] = "NO_HARM_ESTABLISHED"
        verdict["harmCheck"] = ci
    cohort = receipts[:primary["cohortReceipts"]]
    if verdict["verdict"] != "STOPPED_HARM" and len(cohort) == primary["cohortReceipts"] \
            and V1._due(cohort, outcomes, primary["horizonSessions"]) and V1._due(cohort, outcomes, harm["horizonSessions"]):
        h, s = primary["horizonSessions"], harm["horizonSessions"]
        ci = V1.interval(V1._series(cohort, outcomes, h, book), h, primary["z"])
        short = V1.interval(V1._series(cohort, outcomes, s, book), s, primary["z"])
        model = V1.interval(V1._series(cohort, outcomes, h, book, versus="CTRL_MODEL5"), h, primary["z"])
        mechanism = V1.interval(V1._series(cohort, outcomes, h, book, versus="CTRL_CHEAP_UNCONFIRMED"), h, primary["z"])
        checks = {"primaryLowerBoundAboveZero": ci["lower"] is not None and ci["lower"] > 0,
                  "h126MeanAboveZero": short["mean"] is not None and short["mean"] > 0,
                  "beatsExistingModelOnMean": model["mean"] is not None and model["mean"] > 0,
                  "beatsUnconfirmedCheapOnMean": mechanism["mean"] is not None and mechanism["mean"] > 0,
                  "riskNoWorseThanBenchmark": V1._risk_ok(path_metrics, book, primary)}
        short_of = V1._incomplete(len(cohort), {"h252": ci, "h126": short, "versusExistingModel": model,
                                                "versusUnconfirmedCheap": mechanism}, primary["maxIncompleteReceipts"])
        if short_of or checks["riskNoWorseThanBenchmark"] is None:
            result = "INCONCLUSIVE_DATA"
        else:
            result = "SUPPORTED" if all(checks.values()) else "NOT_SUPPORTED"
        verdict.update({"verdict": result, "primary": {**ci, "checks": checks, "h126": short, "versusExistingModel": model,
                                                       "versusUnconfirmedCheap": mechanism, "seriesShortOfCohort": short_of}})
    out["challengers"][book] = verdict
    return out


# --------------------------------------------------------------------------- #
# LIVE identity
# --------------------------------------------------------------------------- #
def merged_at_from_git(root=ROOT) -> str:
    """v1's main-only check for THIS study's spec: the first-parent commit on origin/main that added it, never a commit on HEAD's branch, and
    the running checkout must contain it (``kr_selection_challenger.registration_from_git``)."""
    return V1.registration_from_git(root, SPEC_PATH)["mergedAtUtc"]


def live_code_identity(spec: dict, root=ROOT) -> dict:
    return V1.live_code_identity(spec, root)
