"""kr-selection-challenger-v1 — a PRE-REGISTERED, PROSPECTIVE paper experiment for KR stock selection.

What is new is the evidence, not the information. The two challengers rank KR names on information families the closed historical
programme already measured with inconclusive readings (low downside volatility; proximity to the 52-week high). The historical sample is
spent and nothing here re-reads it: every number this study will ever use is recorded at the close it describes and graded only after its
horizon has matured. The frozen design is ``docs/research-program/specs/kr-selection-challenger-v1.json``; this module refuses to run if the code it
pins has changed.

Books, all built from ONE validated production artifact (``data/site-data.json``) on ONE weekly KR decision session:
    CH_LOWVOL    five lowest 252-day downside volatility;
    CH_HIGH52    five highest close / 52-week high among names above their 200-day average;
    CTRL_MODEL5  five highest production alpha (the existing model's own ranking, same universe, same caps);
    CTRL_ETF     069500.KS (the passive default).
Every book is five equal slots, at most two names per sector, unfilled slots in 069500.KS. A book is a PAPER composition for grading: it is
never an order, never a weight in the official weekly decision, and carries ``productionEffect: NONE``.

Two pathways that never meet: LIVE (writer clock, merge time read from git, code verified against the spec) and SYNTHETIC_FIXTURE (tests,
explicit clock and merge time). A receipt carries what was known; outcomes are separate records built after maturity.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import kelly_portfolio as KP
from . import kr_bar_integrity as BI
from . import longterm as LT
from . import prospective_receipt_core as CORE
from . import weekly_decision as W
from . import weekly_publish as P

ROOT = Path(__file__).resolve().parents[1]
STUDY = "kr-selection-challenger-v1"
SPEC_PATH = "docs/research-program/specs/kr-selection-challenger-v1.json"
SCHEMA_VERSION = 1
LIVE, SYNTHETIC = "LIVE", "SYNTHETIC_FIXTURE"
EVIDENCE_CLASS_BY_PATHWAY = {LIVE: CORE.EVIDENCE_CLASS, SYNTHETIC: "SYNTHETIC_FIXTURE"}
BOOKS = ("CH_LOWVOL", "CH_HIGH52", "CTRL_MODEL5")
CHALLENGERS = ("CH_LOWVOL", "CH_HIGH52")
BENCHMARK = "069500.KS"
SLOTS = 5
TICKER = re.compile(r"^\d{6}\.(KS|KQ)$")
KEY_FIELDS = ("studyId", "signalDate")
NOT_EXECUTABLE = "NOT_EXECUTABLE_HELD_AS_BENCHMARK"
EXCLUSION_CODES = ("TICKER_INVALID", "DUPLICATE_TICKER", "QUOTE_NOT_ON_SIGNAL_SESSION", "SIGNAL_CLOSE_MISSING", "FEATURE_MISSING",
                   "BELOW_200_DAY_AVERAGE", "MA200_UNDETERMINED")
BOOK_EXCLUSION_CODES = ("FEATURE_MISSING", "FEATURE_WINDOW_INCOMPLETE", "FEATURE_VALUE_MISMATCH", "BELOW_200_DAY_AVERAGE",
                        "MA200_UNDETERMINED")


# --------------------------------------------------------------------------- #
# Frozen design
# --------------------------------------------------------------------------- #
def file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_spec(root=ROOT, *, verify_code=True) -> dict:
    """The frozen spec. Refuses when any pinned code file differs from its registered hash: a changed rule is a new version."""
    path = Path(root) / SPEC_PATH
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("studyId") != STUDY or int(spec["construction"]["slots"]) != SLOTS:
        raise ValueError("SPEC_STUDY_MISMATCH")
    if verify_code:
        for rel, pinned in sorted(spec["codeFileHashes"].items()):
            if file_sha256(Path(root) / rel) != pinned:
                raise ValueError("CODE_CHANGED_SINCE_REGISTRATION: " + rel)
    return spec


def spec_sha256(root=ROOT) -> str:
    return file_sha256(Path(root) / SPEC_PATH)


# --------------------------------------------------------------------------- #
# Signal session and eligibility (signal-time facts only)
# --------------------------------------------------------------------------- #
def _number(value):
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def signal_session(site: dict) -> str:
    """The KR session this artifact can speak for, or raise.

    The index tape must equal the last session that was FINAL when the artifact was built (18:00 KST), so a build inside a session can never
    produce a receipt, and that session must be a weekly decision session."""
    observed = next((row.get("asOf") for row in site.get("indices") or [] if row.get("symbol") == W.SESSION_EVIDENCE["KR"]), None)
    if not observed:
        raise ValueError("KR_SESSION_EVIDENCE_MISSING")
    built = datetime.fromisoformat(str(site["generatedAt"]).replace("Z", "+00:00"))
    if observed != W.last_completed_session("KR", built):
        raise ValueError("ARTIFACT_NOT_BUILT_ON_A_FINAL_SESSION: observed %s" % observed)
    if not CORE.is_weekly_decision_session(observed):
        raise ValueError("NOT_A_WEEKLY_DECISION_SESSION: " + observed)
    return observed


# --------------------------------------------------------------------------- #
# Feature windows proven on the exchange calendar
# --------------------------------------------------------------------------- #
# The artifact's features are computed over vendor ROWS: longterm.downside_vol_252 takes the last 252 returns of close.dropna() and
# features.price_52w_high / ma200 are rolling(252) / rolling(200) over whatever rows the vendor returned. A history with 330 rows and one or
# two KRX sessions missing inside the last year therefore carries a "252-session" value spanning 253-254 sessions, and nothing in the
# artifact says so. A name enters a challenger book only if a fresh vendor download, aligned to the pinned KRX calendar by
# kr_bar_integrity, shows every session of the window traded with no off-calendar row inside it AND reproduces the artifact's own values
# (to the artifact's rounding). Anything that cannot be proven is excluded from that book, never repaired.
FEATURE_WINDOW_CLOSES = {"CH_LOWVOL": 253, "CH_HIGH52": 252}      # 252 returns; rolling(252) max (the 200-day mean sits inside it)
FEATURE_HALF_UNIT = {"downsideVolPct": 0.05, "pct52wHigh": 0.05, "ma200": 0.005, "lastClose": 0.005}  # longterm / risk.diagnose rounding
FEATURE_BARS_BASIS = "VENDOR_AUTO_ADJUSTED_BARS_ON_THE_KRX_CALENDAR"


def _feature_window(session: str) -> list:
    days = BI.sessions_between(pd.Timestamp(session) - pd.Timedelta(days=800), session)
    if len(days) == 0 or str(pd.Timestamp(days[-1]).date()) != session:
        raise ValueError("SIGNAL_SESSION_NOT_ON_CALENDAR: " + session)
    return list(days[-FEATURE_WINDOW_CLOSES["CH_LOWVOL"]:])


def feature_bars_start(session: str) -> str:
    """First calendar day the verification download must cover (with a margin so a vendor row before the window is visible)."""
    return str((pd.Timestamp(_feature_window(session)[0]) - pd.Timedelta(days=10)).date())


def _close_enough(artifact, computed, half_unit) -> bool:
    return artifact is not None and computed is not None and math.isfinite(computed) and \
        abs(float(artifact) - float(computed)) <= half_unit + 1e-9 * max(1.0, abs(float(computed)))


def verify_feature_window(row: dict, frame, session: str) -> dict:
    """``{book: None | exclusion code}`` for the two challenger books, from one vendor frame of this name."""
    window = _feature_window(session)
    out = {"CH_LOWVOL": "FEATURE_WINDOW_INCOMPLETE", "CH_HIGH52": "FEATURE_WINDOW_INCOMPLETE"}
    if frame is None or not len(frame):
        return out
    raw = frame.copy()
    index = pd.DatetimeIndex(pd.to_datetime(raw.index))
    raw.index = (index.tz_localize(None) if index.tz is not None else index).normalize()
    raw = raw[raw.index <= pd.Timestamp(session)]          # a row after the signal close is not what the artifact saw
    aligned = BI.calendar_frame(raw, start=window[0], end=session)
    if aligned.attrs.get("offCalendarRows"):              # a vendor row on a closed day sits inside the production window
        return out
    closes = aligned["Close"]
    identity = _close_enough(row["signalClose"], BI.traded_close(aligned, session), FEATURE_HALF_UNIT["lastClose"])
    for book, n in FEATURE_WINDOW_CLOSES.items():
        if not BI.window_complete(aligned, session, n):
            continue
        out[book] = "FEATURE_VALUE_MISMATCH"
        if not identity:
            continue
        last = closes.iloc[-n:]
        if book == "CH_LOWVOL":
            dv = LT.downside_vol_252(last)
            if dv is not None and _close_enough(row["downsideVolPct"], dv * 100.0, FEATURE_HALF_UNIT["downsideVolPct"]):
                out[book] = None
        else:
            pct = float(last.iloc[-1] / last.max() * 100.0)
            ma200 = float(last.iloc[-200:].mean())
            if _close_enough(row["pct52wHigh"], pct, FEATURE_HALF_UNIT["pct52wHigh"]) and \
                    _close_enough(row["ma200"], ma200, FEATURE_HALF_UNIT["ma200"]):
                out[book] = None
    return out


def verification_tickers(rows: list[dict]) -> list[str]:
    """Names a challenger book could rank (their feature is present): each needs a vendor frame."""
    need = []
    for row in rows:
        lowvol = row["downsideVolPct"] is not None and row["downsideVolPct"] > 0
        high52 = row["pct52wHigh"] is not None and 0 < row["pct52wHigh"] <= 100.5 and row["aboveMA200"]
        if lowvol or high52:
            need.append(row["ticker"])
    return need


def attach_feature_checks(rows: list[dict], bars: dict, session: str) -> dict:
    """Stamp ``featureCheck`` on every row; refuse (no receipt) if a name that needs proof has no vendor frame at all, because a book
    must never be formed on whichever names a partial download happened to return."""
    need = verification_tickers(rows)
    absent = sorted(t for t in need if bars.get(t) is None or not len(bars.get(t)))
    if absent:
        raise ValueError("PRICE_FETCH_INCOMPLETE: %d of %d names unserved (%s)" % (len(absent), len(need), ",".join(absent[:5])))
    for row in rows:
        row["featureCheck"] = verify_feature_window(row, bars.get(row["ticker"]), session) if row["ticker"] in need else \
            {"CH_LOWVOL": "FEATURE_MISSING", "CH_HIGH52": "FEATURE_MISSING"}
    return {"basis": FEATURE_BARS_BASIS, "windowCloses": dict(FEATURE_WINDOW_CLOSES), "framesChecked": len(need),
            "windowStart": str(pd.Timestamp(_feature_window(session)[0]).date())}


def universe_rows(site: dict, session: str) -> tuple[list[dict], dict]:
    """The production-eligible KR cross-section with the facts each book needs, and exclusion counts. Missing is never imputed."""
    blob = ((site.get("longTerm") or {}).get("regions") or {}).get("KR") or {}
    details = site.get("details") or {}
    rows, excluded, seen = [], {code: 0 for code in EXCLUSION_CODES}, set()
    for item in blob.get("validationCrossSection") or []:
        ticker = item.get("ticker")
        if not isinstance(ticker, str) or not TICKER.match(ticker):
            excluded["TICKER_INVALID"] += 1
            continue
        if ticker in seen:
            excluded["DUPLICATE_TICKER"] += 1
            continue
        seen.add(ticker)
        detail = details.get(ticker) or {}
        if detail.get("asOf") != session:
            excluded["QUOTE_NOT_ON_SIGNAL_SESSION"] += 1
            continue
        close = _number(detail.get("lastClose"))
        if close is None or close <= 0:
            excluded["SIGNAL_CLOSE_MISSING"] += 1
            continue
        ma200 = _number(detail.get("ma200"))
        rows.append({"ticker": ticker, "sector": str(item.get("sector") or "UNCLASSIFIED"), "signalClose": close,
                     "downsideVolPct": _number((item.get("risk") or {}).get("downsideVolPct")),
                     "pct52wHigh": _number(detail.get("pct52wHigh")), "ma200": ma200,
                     "aboveMA200": None if ma200 is None or ma200 <= 0 else close > ma200,
                     "alpha": _number(item.get("alpha"))})
    return sorted(rows, key=lambda r: r["ticker"]), excluded


def _book_candidates(book: str, rows: list[dict]) -> tuple[list[tuple], dict]:
    """(sort key, row) pairs for one book and its own exclusion counts."""
    out, excluded = [], {code: 0 for code in BOOK_EXCLUSION_CODES}
    for row in rows:
        check = (row.get("featureCheck") or {}).get(book, "FEATURE_WINDOW_INCOMPLETE") if book in CHALLENGERS else None
        if book == "CH_LOWVOL":
            value = row["downsideVolPct"]
            if value is None or value <= 0:
                excluded["FEATURE_MISSING"] += 1
                continue
            if check is not None:
                excluded[check] += 1
                continue
            out.append(((value, row["ticker"]), row, value))
        elif book == "CH_HIGH52":
            value = row["pct52wHigh"]
            if value is None or not 0 < value <= 100.5:
                excluded["FEATURE_MISSING"] += 1
                continue
            if row["aboveMA200"] is None:
                excluded["MA200_UNDETERMINED"] += 1
                continue
            if not row["aboveMA200"]:
                excluded["BELOW_200_DAY_AVERAGE"] += 1
                continue
            if check is not None:
                excluded[check] += 1
                continue
            out.append(((-value, row["ticker"]), row, value))
        elif book == "CTRL_MODEL5":
            value = row["alpha"]
            if value is None:
                excluded["FEATURE_MISSING"] += 1
                continue
            out.append(((-value, row["ticker"]), row, value))
        else:
            raise ValueError("UNKNOWN_BOOK: " + book)
    return sorted(out, key=lambda x: x[0]), excluded


def build_book(book: str, rows: list[dict], construction: dict) -> dict:
    ranked, excluded = _book_candidates(book, rows)
    slots_n, cap, floor = int(construction["slots"]), int(construction["maxNamesPerSector"]), int(construction["minEligibleNames"])
    base = {"eligibleNames": len(ranked), "excluded": excluded, "slotFraction": float(construction["slotFraction"])}
    if len(ranked) < floor:
        return {**base, "status": "THIN_CROSS_SECTION", "slots": [], "fallbackSlots": slots_n}
    slots, per_sector = [], {}
    for rank, (_, row, value) in enumerate(ranked, start=1):
        if len(slots) == slots_n:
            break
        if per_sector.get(row["sector"], 0) >= cap:
            continue
        per_sector[row["sector"]] = per_sector.get(row["sector"], 0) + 1
        slots.append({"ticker": row["ticker"], "sector": row["sector"], "rank": rank, "featureValue": round(value, 6),
                      "signalClose": row["signalClose"]})
    return {**base, "status": "BOOK_FORMED", "slots": slots, "fallbackSlots": slots_n - len(slots)}


def build_books(site: dict, session: str, spec: dict, *, bars: dict) -> tuple[dict, dict]:
    """``bars[ticker]`` is a vendor OHLCV frame covering ``feature_bars_start(session)`` to the signal session."""
    rows, excluded = universe_rows(site, session)
    verification = attach_feature_checks(rows, bars, session)
    books = {book: build_book(book, rows, spec["construction"]) for book in BOOKS}
    return books, {"crossSectionNames": len(rows), "excluded": excluded, "featureVerification": verification}


# --------------------------------------------------------------------------- #
# Receipts
# --------------------------------------------------------------------------- #
REQUIRED = ("schemaVersion", "studyId", "pathway", "specSha256", "codeIdentity", "authorization", "signalDate", "executionDate",
            "createdAtUtc", "sourceArtifact", "universe", "books", "productionResearchPicks", "benchmark", "horizonsSessions",
            "researchOnly", "productionEffect", "evidenceClass", "receiptSha256")


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
                  spec: dict, spec_digest: str, fetch_bars) -> dict:
    """``fetch_bars(tickers, start)`` returns vendor frames; it is called only once the timing checks have passed."""
    if pathway not in EVIDENCE_CLASS_BY_PATHWAY:
        raise ValueError("UNKNOWN_PATHWAY")
    if (reason := P.unsafe_reason(site)) is not None or (site.get("meta") or {}).get("syntheticData"):
        raise ValueError("UNSAFE_ARTIFACT: " + str(reason or "SEED_OR_SYNTHETIC_ARTIFACT"))
    if not CORE.is_sha256(site_sha256) or not CORE.is_sha256(spec_digest):
        raise ValueError("IDENTITY_REQUIRED")
    if not CORE.is_git_sha(code_identity.get("commitSha")) or not code_identity.get("files"):
        raise ValueError("CODE_IDENTITY_REQUIRED")
    session = signal_session(site)
    floor = spec["schedule"]["firstEligibleSignalSessionFloor"]
    if session < floor:
        raise ValueError("SIGNAL_BEFORE_REGISTERED_FLOOR: " + floor)
    execution = CORE.check_timing(signal_date=session, created_at_utc=created_at_utc, now_utc=now_utc, merged_at_utc=merged_at_utc)
    rows, _ = universe_rows(site, session)
    bars = fetch_bars(verification_tickers(rows), feature_bars_start(session))
    books, universe = build_books(site, session, spec, bars=bars)
    picks = ((site.get("longTerm") or {}).get("regions") or {}).get("KR", {}).get("picks") or []
    provenance = site.get("provenance") or {}
    receipt = {
        "schemaVersion": SCHEMA_VERSION, "studyId": STUDY, "pathway": pathway, "specSha256": spec_digest,
        "codeIdentity": {"commitSha": code_identity["commitSha"], "files": dict(sorted(code_identity["files"].items()))},
        "authorization": {"basis": "MERGE_OF_THE_REGISTERED_SPEC", "mergedAtUtc": str(CORE.utc(merged_at_utc).isoformat()),
                          "firstProspectiveSession": str(CORE.first_prospective_session(merged_at_utc).date()),
                          "registeredFloor": floor},
        "signalDate": session, "executionDate": str(execution.date()), "createdAtUtc": str(CORE.utc(created_at_utc).isoformat()),
        "sourceArtifact": {"siteDataSha256": site_sha256, "siteGeneratedAt": site.get("generatedAt"),
                           "buildCommitSha": provenance.get("buildCommitSha"),
                           "modelVersion": provenance.get("modelVersion") or site.get("modelVersion")},
        "universe": universe, "books": books,
        "productionResearchPicks": sorted(p.get("ticker") for p in picks if isinstance(p.get("ticker"), str)),
        "benchmark": BENCHMARK, "horizonsSessions": list(spec["horizonsSessions"]),
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
# Outcomes: separate records, built only after the maturity session closed
# --------------------------------------------------------------------------- #
def _leg(as_of: str, *, is_benchmark: bool, side: str) -> float:
    return W.trade_cost_fraction("KR", as_of, is_benchmark=is_benchmark, side=side)


def name_outcome(frame, execution: str, maturity: str, bench_return: float) -> dict:
    """One slot's state.

    A name SUSPENDED at the execution session cannot be bought, so its slot stays in the benchmark (a fact known at execution). Any other gap
    (no vendor frame, no row, an invalid close) is missing data and leaves the slot unresolved. A name that did not trade on the maturity
    session itself is unresolved too, never marked at an earlier close."""
    execution_ts, maturity_ts = pd.Timestamp(execution), pd.Timestamp(maturity)
    if frame is None or execution_ts not in frame.index:
        return {"state": "NAME_OUTCOME_MISSING", "excessReturn": None, "integrityState": "NO_VENDOR_FRAME"}
    entry = BI.traded_close(frame, execution)
    if entry is None:
        state = str(frame.loc[execution_ts, "state"])
        if state == "SUSPENDED":
            return {"state": NOT_EXECUTABLE, "excessReturn": 0.0, "entrySession": execution}
        return {"state": "NAME_OUTCOME_MISSING", "excessReturn": None, "integrityState": state, "entrySession": execution}
    exit_ = BI.traded_close(frame, maturity)
    if exit_ is None:
        state = str(frame.loc[maturity_ts, "state"]) if maturity_ts in frame.index else "SESSION_MISSING"
        return {"state": "TERMINAL_ECONOMICS_UNRESOLVED" if state == "SUSPENDED" else "NAME_OUTCOME_MISSING", "excessReturn": None,
                "entrySession": execution, "exitSession": maturity, "integrityState": state}
    return {"state": "PRICED", "excessReturn": exit_ / entry - 1.0 - bench_return, "nameReturn": exit_ / entry - 1.0,
            "entrySession": execution, "exitSession": maturity}


def book_result(blob: dict, names: dict, *, execution: str, maturity: str) -> dict:
    """Net excess return over 069500.KS of one book, every leg charged its dated cost, or None with the reason.

    Book return minus benchmark return is the slot-weighted excess of the names actually bought; slots held in the benchmark (unfilled or
    not executable) add zero excess and pay the ETF round trip, which the ETF control pays as well."""
    frac = float(blob["slotFraction"])
    bought = {s["ticker"]: frac for s in blob["slots"] if names[s["ticker"]]["state"] != NOT_EXECUTABLE}
    outcome = CORE.portfolio_outcome(bought, {t: names[t] for t in bought}) if bought else \
        {"status": "COMPLETE", "unresolvedTickers": [], "heldExcessReturn": 0.0}
    if outcome["status"] != "COMPLETE":
        return {**outcome, "netExcessReturn": None}
    stock_round = _leg(execution, is_benchmark=False, side="buy") + _leg(maturity, is_benchmark=False, side="sell")
    etf_round = _leg(execution, is_benchmark=True, side="buy") + _leg(maturity, is_benchmark=True, side="sell")
    held_as_benchmark = 1.0 - frac * len(bought)
    stock_cost, etf_cost = frac * len(bought) * stock_round, held_as_benchmark * etf_round
    net = outcome["heldExcessReturn"] - stock_cost - etf_cost + etf_round
    return {**outcome, "stockCost": stock_cost, "benchmarkCost": etf_cost, "netExcessReturn": net,
            "heldAsBenchmarkFraction": held_as_benchmark}


def build_outcome(receipt: dict, *, horizon: int, frames: dict, now_utc, pathway: str) -> dict:
    """A separate record keyed by the receipt digest. ``frames[ticker]`` are vendor OHLCV frames; ``frames[BENCHMARK]`` is required."""
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
        names = {t: name_outcome(span.get(t), execution, maturity, bench) for t in tickers}
        record.update({"status": "COMPLETE", "benchmarkReturn": bench, "names": names,
                       "books": {book: book_result(receipt["books"][book], names, execution=execution, maturity=maturity)
                                 for book in BOOKS}})
    record.update(resolution(record, now_utc))
    record["recordSha256"] = hashlib.sha256(CORE.canonical(record)).hexdigest()
    return record


# Two different things can leave an outcome unresolved, and they have opposite answers.
#
#   PROVIDER_DATA_UNAVAILABLE  the vendor did not serve what the record needs: an empty or partial download (no frame for the benchmark
#                              or a held name), a session with no row, an invalid close. An empty Yahoo answer is NOT evidence of a
#                              delisting and a frame that stops early is NOT evidence of a terminal event: these reasons are retried by
#                              every later run for as long as they persist and are NEVER written as an outcome. The pending state lives
#                              outside the append-only ledgers (``outcome-pending.json``) and is not evidence.
#   ECONOMIC_UNRESOLVED        the vendor served the maturity session and it says the name did not trade (zero volume): a halt or an
#                              unresolved terminal consideration. It is retried until the (horizon + OUTCOME_RETRY_SESSIONS)-th session
#                              after execution is final and then written (FINAL_UNRESOLVED_AFTER_RETRY) and counted as None.
#
# An outcome with ANY provider reason stays DEFERRED whatever the date. Closing a cohort that a provider never serves needs an independent
# source for the terminal event, which is an owner decision, not a recorder default.
OUTCOME_RETRY_SESSIONS = 5
RESOLVED_NAME_STATES = ("PRICED", NOT_EXECUTABLE)
PROVIDER, ECONOMIC = "PROVIDER_DATA_UNAVAILABLE", "ECONOMIC_UNRESOLVED"


def unresolved_reasons(record: dict) -> list[str]:
    if record.get("status") == "BENCHMARK_UNPRICED":
        return ["BENCHMARK_UNPRICED"]
    return sorted(f"{t}:{n['state']}:{n.get('integrityState', '')}".rstrip(":") for t, n in (record.get("names") or {}).items()
                  if n["state"] not in RESOLVED_NAME_STATES)


def reason_class(reason: str) -> str:
    """ECONOMIC only for a served maturity session that says the name did not trade; every other gap is the provider's."""
    return ECONOMIC if reason.split(":")[1:2] == ["TERMINAL_ECONOMICS_UNRESOLVED"] and reason.endswith(":SUSPENDED") else PROVIDER


def resolution(record: dict, now_utc) -> dict:
    """``FINAL`` (everything resolved), ``DEFERRED`` (do not write: a provider gap at any date, or an economic gap inside the retry
    window) or ``FINAL_UNRESOLVED_AFTER_RETRY`` (only economic gaps remain and the window has closed)."""
    reasons = unresolved_reasons(record)
    if not reasons:
        return {"resolution": "FINAL"}
    classes = sorted({reason_class(r) for r in reasons})
    closes = CORE.maturity_session(record["executionDate"], record["horizonSessions"] + OUTCOME_RETRY_SESSIONS)
    window_closed = CORE.has_matured(record["executionDate"], record["horizonSessions"] + OUTCOME_RETRY_SESSIONS, now_utc)
    if PROVIDER in classes or not window_closed:
        return {"resolution": "DEFERRED", "unresolved": reasons, "unresolvedClasses": classes,
                "retryUntilSession": None if PROVIDER in classes else str(closes.date())}
    return {"resolution": "FINAL_UNRESOLVED_AFTER_RETRY", "unresolved": reasons, "unresolvedClasses": classes,
            "retryUntilSession": str(closes.date())}


def validate_outcome(record: dict, *, pathway: str) -> None:
    expected = CORE.OUTCOME_EVIDENCE_CLASS if pathway == LIVE else "SYNTHETIC_FIXTURE"
    if record.get("resolution") == "DEFERRED":
        raise ValueError("OUTCOME_DEFERRED_IS_NEVER_A_RECORD")
    if record.get("resolution") == "FINAL_UNRESOLVED_AFTER_RETRY" and \
            any(reason_class(r) == PROVIDER for r in record.get("unresolved") or []):
        raise ValueError("OUTCOME_PROVIDER_GAP_IS_NEVER_FINAL")
    if record.get("studyId") != STUDY or record.get("evidenceClass") != expected:
        raise ValueError("OUTCOME_PATHWAY_MISMATCH")
    body = {k: v for k, v in record.items() if k != "recordSha256"}
    if hashlib.sha256(CORE.canonical(body)).hexdigest() != record.get("recordSha256"):
        raise ValueError("OUTCOME_DIGEST_MISMATCH")


def pending_entries(previous: list[dict], deferred: list[dict], now_utc) -> list[dict]:
    """The retryable state of every outcome not yet written, carrying ``firstDeferredAtUtc`` and the attempt count across runs. A
    status file, rewritten each run; never read as an outcome."""
    before = {(p["receiptSha256"], p["horizonSessions"]): p for p in previous}
    out = []
    for row in deferred:
        key = (row["receiptSha256"], row["horizonSessions"])
        old = before.get(key) or {}
        out.append({"receiptSha256": key[0], "horizonSessions": key[1], "signalDate": row["signalDate"],
                    "maturitySession": row["maturitySession"], "unresolved": row["unresolved"],
                    "unresolvedClasses": row["unresolvedClasses"], "retryUntilSession": row["retryUntilSession"],
                    "firstDeferredAtUtc": old.get("firstDeferredAtUtc") or str(CORE.utc(now_utc).isoformat()),
                    "lastAttemptAtUtc": str(CORE.utc(now_utc).isoformat()), "attempts": int(old.get("attempts") or 0) + 1})
    return sorted(out, key=lambda p: (p["signalDate"], p["horizonSessions"]))


def read_outcomes(path, *, pathway: str) -> list[dict]:
    return CORE.read_ledger(path, lambda r: validate_outcome(r, pathway=pathway))


# --------------------------------------------------------------------------- #
# Assessment: registered once, applied mechanically
# --------------------------------------------------------------------------- #
def _series(receipts, outcomes, horizon, book, *, versus=None):
    by = {(o["receiptSha256"], o["horizonSessions"]): o for o in outcomes}
    values = {}
    for r in receipts:
        o = by.get((r["receiptSha256"], horizon))
        blob = ((o or {}).get("books") or {})
        a = (blob.get(book) or {}).get("netExcessReturn")
        b = 0.0 if versus is None else (blob.get(versus) or {}).get("netExcessReturn")
        values[pd.Timestamp(r["signalDate"])] = a - b if a is not None and b is not None else None
    return pd.Series(values, dtype=object).sort_index()


def interval(series: pd.Series, horizon: int, z: float) -> dict:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 2:
        return {"n": int(len(clean)), "mean": None, "se": None, "lower": None, "upper": None}
    stats = KP._newey_west_stats(clean, horizon)
    mean, se = float(clean.mean()), stats.get("se")
    return {"n": int(len(clean)), "mean": mean, "se": se, "hacLag": stats.get("hacLag"),
            "lower": None if se is None else mean - z * se, "upper": None if se is None else mean + z * se}


def turnover(receipts: list[dict], book: str) -> dict:
    """Share of slots whose name changed between consecutive weekly receipts (names replaced, not weights retargeted)."""
    changes = []
    for prev, cur in zip(receipts, receipts[1:]):
        a = {s["ticker"] for s in prev["books"][book]["slots"]}
        b = {s["ticker"] for s in cur["books"][book]["slots"]}
        changes.append(len(b - a) / 5.0)
    return {"weeklyNameReplacement": sum(changes) / len(changes) if changes else None, "pairs": len(changes)}


def _due(cohort, outcomes, horizon) -> bool:
    graded = {o["receiptSha256"] for o in outcomes if o["horizonSessions"] == horizon}
    return all(r["receiptSha256"] in graded for r in cohort)


def assess(receipts: list[dict], outcomes: list[dict], spec: dict, *, path_metrics: dict | None = None) -> dict:
    """Mechanical verdict per challenger from the registered rule. Each check reads exactly its registered cohort (the first N receipts), so
    a verdict can never move once that cohort is graded; ACCUMULATING until then."""
    rule = spec["assessment"]
    harm, primary = rule["harmCheck"], rule["primary"]
    receipts = sorted(receipts, key=lambda r: r["signalDate"])
    out = {"studyId": STUDY, "receipts": len(receipts), "outcomes": len(outcomes),
           "turnover": {b: turnover(receipts, b) for b in BOOKS}, "challengers": {}}
    for book in CHALLENGERS:
        verdict = {"verdict": "ACCUMULATING"}
        cohort = receipts[:harm["cohortReceipts"]]
        if len(cohort) == harm["cohortReceipts"] and _due(cohort, outcomes, harm["horizonSessions"]):
            s = _series(cohort, outcomes, harm["horizonSessions"], book)
            ci = interval(s, harm["horizonSessions"], harm["z"])
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
                and _due(cohort, outcomes, primary["horizonSessions"]) and _due(cohort, outcomes, harm["horizonSessions"]):
            ci = interval(_series(cohort, outcomes, primary["horizonSessions"], book), primary["horizonSessions"], primary["z"])
            short = interval(_series(cohort, outcomes, harm["horizonSessions"], book), harm["horizonSessions"], primary["z"])
            versus = interval(_series(cohort, outcomes, primary["horizonSessions"], book, versus="CTRL_MODEL5"),
                              primary["horizonSessions"], primary["z"])
            checks = {"primaryLowerBoundAboveZero": ci["lower"] is not None and ci["lower"] > 0,
                      "h126MeanAboveZero": short["mean"] is not None and short["mean"] > 0,
                      "beatsExistingModelOnMean": versus["mean"] is not None and versus["mean"] > 0,
                      "riskNoWorseThanBenchmark": _risk_ok(path_metrics, book, primary)}
            short_of = _incomplete(len(cohort), {"h252": ci, "h126": short, "versusExistingModel": versus},
                                   primary["maxIncompleteReceipts"])
            if short_of or checks["riskNoWorseThanBenchmark"] is None:
                result = "INCONCLUSIVE_DATA"
            else:
                result = "SUPPORTED" if all(checks.values()) else "NOT_SUPPORTED"
            verdict.update({"verdict": result, "primary": {**ci, "checks": checks, "h126": short, "versusExistingModel": versus,
                                                           "seriesShortOfCohort": short_of}})
        out["challengers"][book] = verdict
    return out


def _incomplete(cohort: int, series: dict, max_incomplete: int) -> list[str]:
    """Names of the series whose valid (paired, where a comparison) observations fall more than ``max_incomplete`` short of the cohort.
    The registered None budget applies to EVERY series a check reads, not only the first: a mean or a comparison computed on two outcomes
    out of 104 is not the registered statistic."""
    return sorted(name for name, ci in series.items() if cohort - ci["n"] > max_incomplete)


def _risk_ok(path_metrics, book, primary):
    """True/False on the registered risk condition, None when it cannot be evaluated (an incomplete path or an undefined metric)."""
    if not path_metrics or (path_metrics.get(book) or {}).get("status") != "COMPLETE" or \
            (path_metrics.get("CTRL_ETF") or {}).get("status") != "COMPLETE":
        return None
    mine, etf = path_metrics[book], path_metrics["CTRL_ETF"]
    values = [mine.get("sharpe"), etf.get("sharpe"), mine.get("maxDrawdown"), etf.get("maxDrawdown")]
    if any(v is None or not math.isfinite(v) for v in values):
        return None
    return mine["sharpe"] >= etf["sharpe"] and abs(mine["maxDrawdown"]) <= primary["maxDrawdownMultiple"] * abs(etf["maxDrawdown"])


# --------------------------------------------------------------------------- #
# Risk path: rebalanced every k-th receipt, marked daily, costs on names traded
# --------------------------------------------------------------------------- #
def paper_path(receipts: list[dict], frames: dict, book: str, *, every: int, end_receipt: int) -> dict:
    """Daily NAV of one book rebalanced to equal slots at receipts 0, k, 2k, ... (< ``end_receipt``) and held, drifting, until the next,
    through the execution session of receipt ``end_receipt``. Any held name without a traded close on a day it must be marked makes the path
    INCOMPLETE: it is never carried at an earlier price. ``book="CTRL_ETF"`` is 069500.KS alone."""
    receipts = sorted(receipts, key=lambda r: r["signalDate"])
    if len(receipts) <= end_receipt:
        return {"status": "ACCUMULATING"}
    starts = [receipts[i]["executionDate"] for i in range(0, end_receipt, every)]
    stop = receipts[end_receipt]["executionDate"]
    days = BI.sessions_between(starts[0], stop)
    aligned = {t: BI.calendar_frame(f, start=starts[0], end=stop) for t, f in frames.items() if f is not None}
    nav, holdings, values, previous = 1.0, {}, [], set()
    rebalance = {pd.Timestamp(d): receipts[i] for d, i in zip(starts, range(0, end_receipt, every))}
    replaced = []
    for day in days:
        if holdings:
            marked = 0.0
            for ticker, (units, _) in holdings.items():
                close = BI.traded_close(aligned.get(ticker), day)
                if close is None:  # halted or missing: never carried at an earlier close
                    return {"status": "INCOMPLETE", "ticker": ticker, "day": str(day.date())}
                holdings[ticker] = (units, close)
                marked += units * close
            nav = marked
        if day in rebalance:
            receipt = rebalance[day]
            names = [BENCHMARK] if book == "CTRL_ETF" else [s["ticker"] for s in receipt["books"][book]["slots"]]
            fallback = 0 if book == "CTRL_ETF" else receipt["books"][book]["fallbackSlots"]
            target = {t: 0.2 for t in names} if book != "CTRL_ETF" else {BENCHMARK: 1.0}
            if fallback:
                target[BENCHMARK] = target.get(BENCHMARK, 0.0) + 0.2 * fallback
            current = {t: u * c / nav for t, (u, c) in holdings.items()} if holdings else {}
            date = str(day.date())
            cost = 0.0
            for t in set(target) | set(current):
                delta = target.get(t, 0.0) - current.get(t, 0.0)
                if abs(delta) > 1e-12:
                    cost += abs(delta) * _leg(date, is_benchmark=t == BENCHMARK, side="buy" if delta > 0 else "sell")
            nav *= 1.0 - cost
            new = {}
            for t, w in target.items():
                close = BI.traded_close(aligned.get(t), day)
                if close is None:
                    return {"status": "INCOMPLETE", "ticker": t, "day": date}
                new[t] = (nav * w / close, close)
            held = set(names) - {BENCHMARK}
            if previous:
                replaced.append(len(held - previous) / 5.0)
            previous, holdings = held, new
        values.append(nav)
    series = pd.Series(values, index=days)
    daily = series.pct_change().dropna()
    years = len(daily) / 252.0
    vol = float(daily.std(ddof=1) * math.sqrt(252)) if len(daily) > 1 else None
    annual = float(series.iloc[-1] ** (1 / years) - 1) if years > 0 else None
    return {"status": "COMPLETE", "sessions": len(series), "annualReturn": annual, "annualVolatility": vol,
            "sharpe": annual / vol if annual is not None and vol else None,
            "maxDrawdown": float((series / series.cummax() - 1).min()),
            "rebalanceNameReplacement": sum(replaced) / len(replaced) if replaced else None}


# --------------------------------------------------------------------------- #
# LIVE identity helpers
# --------------------------------------------------------------------------- #
def _git(*args, root=ROOT):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)


# Commits to deepen a shallow checkout of main by. ``--deepen`` counts from the current shallow boundary and can only ADD history;
# ``--shallow-since`` would also cut a full history back to its date in a repository that is shallow for another ref (CI fetches pinned
# commits at depth 1), silently removing commits other code proves ancestry against.
DEEPEN_COMMITS = 2000


MAIN_REF = "refs/remotes/origin/main"


def deepen_history(root=ROOT) -> None:
    """Refresh ``origin/main`` and give a shallow checkout enough of its history to find the spec's commit. ``--deepen`` never shortens
    anything; a failed fetch is ignored (the lookup below then refuses or, on a shallow root, can only answer LATER)."""
    args = ["fetch", "--no-tags", "--quiet"]
    if _git("rev-parse", "--is-shallow-repository", root=root).stdout.strip() == "true":
        args.append("--deepen=" + str(DEEPEN_COMMITS))
    _git(*args, "origin", "+refs/heads/main:" + MAIN_REF, root=root)


def registration_from_git(root=ROOT, spec_path=SPEC_PATH) -> dict:
    """The commit on main's first-parent history that added the registered spec (``spec_path``; another study passes its own), and its
    commit time.

    Read from ``origin/main``, never from HEAD: a branch that adds the spec without being merged has no such commit on main and is refused
    (``SPEC_NOT_ON_MAIN``). The running checkout must also contain that commit, so code from a branch cut before the registration cannot
    record under it (``RUNNING_CODE_DOES_NOT_CONTAIN_REGISTRATION``)."""
    deepen_history(root)
    if _git("rev-parse", "--verify", "--quiet", MAIN_REF, root=root).returncode != 0:
        raise ValueError("SPEC_MERGE_TIME_UNKNOWN: no " + MAIN_REF)
    found = _git("log", "--first-parent", "--diff-merges=first-parent", "--diff-filter=A", "--no-renames", "--name-only",
                 "--format=%H %cI", MAIN_REF, "--", spec_path, root=root)
    lines = [line.split(" ") for line in found.stdout.splitlines() if re.match(r"^[0-9a-f]{40} \d{4}-\d{2}-\d{2}T", line)]
    if found.returncode != 0:
        raise ValueError("SPEC_MERGE_TIME_UNKNOWN")
    if not lines:
        raise ValueError("SPEC_NOT_ON_MAIN")
    commit, merged = lines[-1]
    if _git("merge-base", "--is-ancestor", commit, "HEAD", root=root).returncode != 0:
        raise ValueError("RUNNING_CODE_DOES_NOT_CONTAIN_REGISTRATION: " + commit)
    return {"commitSha": commit, "mergedAtUtc": merged}


def merged_at_from_git(root=ROOT) -> str:
    """Commit time of the first-parent commit on ``origin/main`` that added the registered spec (``registration_from_git``). The LIVE
    recorder is the only caller; synthetic fixtures pass a merge time explicitly and never reach git."""
    return registration_from_git(root)["mergedAtUtc"]


def live_code_identity(spec: dict, root=ROOT) -> dict:
    head = _git("rev-parse", "HEAD", root=root).stdout.strip()
    if not CORE.is_git_sha(head):
        raise ValueError("CODE_COMMIT_UNKNOWN")
    return {"commitSha": head, "files": {rel: file_sha256(Path(root) / rel) for rel in sorted(spec["codeFileHashes"])}}
