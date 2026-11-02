"""Append-only shadow decisions and paper accounting for the entry-state A/B (entry state in rank vs on weight).

PROSPECTIVE PAPER ONLY. No order, no allocation, no production effect. The decision producer is
`scripts/entry_state_shadow_observation.mjs` (unchanged selection rules, residual = regional ETF); this module turns one
observation into write-once decision receipts and advances each strategy's paper book through final sessions:

* a decision receipt is keyed by (policyVersion, region, strategyId, asOfDate) and is never rewritten; a second, different
  payload for the same key is refused and kept as a conflict count;
* every receipt carries the full candidate audit (selected and the reason every other name was not), the writer's own
  clock, the code / policy / input hashes, target weights, residual weight, and the EXECUTION session: the first regional
  session whose open is strictly after the receipt was recorded. A decision recorded after the next open is not filled at
  that open's close, it waits for the following one: no fill ever predates the receipt;
* a fill happens at the execution session's close once that session is final, from the book CARRIED from the previous fill
  (units marked to the new close), never from a reset principal. Each traded leg pays the dated cost schedule once
  (stock legs at the stock rate, ETF legs at the ETF rate, `weekly_decision.trade_cost_fraction`);
* first entry, retained, replaced and retargeted names are separated on every fill;
* a held name without a final close stops that strategy's NAV at the previous session with an explicit
  UNRESOLVED_MISSING_PRICE row. Nothing is filled with a zero return and no holding is dropped;
* H126 / H252 maturity is counted in the region's own sessions from the first fill; before that it is PENDING, never 0.

Every strategy starts at NAV 1.0 fully in its regional ETF at its first execution session (the default the policy keeps).
Live marks use fixed-origin vendor index levels with published-prefix checks, not raw adjusted-price levels across
acquisitions. Stored units are valuation-index units, never broker share counts; legacy price-coordinate books refuse
automatic continuation. Superseded receipt IDs remain consumed across restarts.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from . import replay_calendar as RC
from . import weekly_decision as W

STUDY = "entry-state-shadow-ledger-v1"
POLICY_VERSION = "ENTRY_STATE_SHADOW_CARDINALITY_V3"
EVIDENCE_CLASS = "PROSPECTIVE_PAPER"
REGIONAL_ETF = {"KR": "069500.KS", "US": "SPY"}
SEPARATE_COMPARISON = {"US": "QQQ"}
CURRENCY = {"KR": "KRW", "US": "USD"}
HORIZONS = {"H126": 126, "H252": 252}
OPEN = {"KR": ("Asia/Seoul", 9, 0), "US": ("America/New_York", 9, 30)}
# A session's close is FINAL (no later vendor revision of that day's print is expected) at: KR 18:00 KST (v2.53 rule),
# US 20:00 New York time.
FINAL = {"KR": ("Asia/Seoul", 18, 0), "US": ("America/New_York", 20, 0)}
RETURN_BASIS = "VENDOR_ADJUSTED_CLOSE_FIXED_ORIGIN_RATIO_V1_PREFIX_CHECKED"
NET_ALREADY_CHARGED = "NET_ALREADY_CHARGED"
FILES = ("decisions.jsonl", "fills.jsonl", "nav-daily.jsonl")
ZERO = 1e-10
DIGEST_EXCLUDED = ("recordedAtUtc", "digest", "code", "executionSession", "signalSessionFinalAtUtc", "timing")


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local(session: str, region: str, table) -> datetime:
    zone, hour, minute = table[region]
    day = pd.Timestamp(session)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)


def session_open_utc(session: str, region: str) -> datetime:
    return _local(session, region, OPEN)


def session_final_utc(session: str, region: str) -> datetime:
    return _local(session, region, FINAL)


def region_sessions(region: str, start: str, end: str) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in RC.sessions(start, end, region)]


def execution_session(region: str, as_of: str, recorded_at: datetime) -> str:
    """First regional session strictly after the signal session whose open is after the receipt was recorded."""
    end = (pd.Timestamp(recorded_at.date()) + pd.Timedelta(days=21)).strftime("%Y-%m-%d")
    for session in region_sessions(region, as_of, end):
        if session > as_of and session_open_utc(session, region) > recorded_at:
            return session
    raise ValueError("NO_EXECUTION_SESSION_WITHIN_21_DAYS")


# ------------------------------------------------------------------------------------------------------------------------------
# Decisions
# ------------------------------------------------------------------------------------------------------------------------------
def _book(stocks: dict | None, residual: float | None, etf: str) -> dict | None:
    if stocks is None or residual is None:
        return None
    book = {t: float(w) for t, w in stocks.items() if float(w) > ZERO}
    if residual > ZERO:
        book[etf] = book.get(etf, 0.0) + float(residual)
    total = sum(book.values())
    if abs(total - 1.0) > 1e-5:
        raise ValueError(f"TARGET_DOES_NOT_SUM_TO_ONE: {total}")
    return book


def strategies(observation: dict) -> list[dict]:
    """Every paper strategy one observation defines. A blocked scenario has target None and holds its previous book."""
    out = []
    for region, blob in sorted((observation.get("regions") or {}).items()):
        etf = REGIONAL_ETF[region]
        base = {"region": region, "asOfDate": blob.get("asOfDate"), "etf": etf}
        out.append({**base, "strategyId": f"{region}:ETF_ONLY", "kind": "PASSIVE_REFERENCE",
                    "target": {etf: 1.0}, "status": "PASSIVE"})
        if region in SEPARATE_COMPARISON:
            other = SEPARATE_COMPARISON[region]
            out.append({**base, "strategyId": f"{region}:SEPARATE_COMPARISON:{other}", "kind": "SEPARATE_COMPARISON",
                        "target": {other: 1.0}, "status": "PASSIVE"})
        if blob.get("status") != "RESEARCH_SNAPSHOT_ONLY_NOT_LIVE_VALIDATED":
            continue
        policy = blob.get("currentPolicy") or {}
        out.append({**base, "strategyId": f"{region}:CURRENT_POLICY", "kind": "CURRENT_RESEARCH_POLICY",
                    "status": policy.get("status"),
                    "target": {etf: 1.0} if policy.get("status") == "PASSIVE_NO_DEFENSIBLE_EDGE" else None})
        legacy = blob.get("legacyControlOnly") or {}
        out.append({**base, "strategyId": f"{region}:LEGACY_CONTROL_MAXREGION3", "kind": "LEGACY_COMPARATOR",
                    "status": "SAME_AS_PUBLISHED" if legacy.get("sameAsPublished") else "NOT_RECONSTRUCTED",
                    "selected": legacy.get("selected"),
                    "target": _book(legacy.get("stocks"), legacy.get("residual"), etf)})
        for scenario in blob.get("researchScenarios") or []:
            n = scenario["stockCount"]
            for arm, name in (("rankStateInSelection", "IN_RANK"), ("stateAtPositionWeight", "AT_WEIGHT")):
                book = scenario.get(arm)
                out.append({**base, "strategyId": f"{region}:N{n}:{name}", "kind": "RESEARCH_SCENARIO",
                            "stockCount": n, "status": scenario["status"],
                            "selected": None if book is None else book.get("selected"),
                            "candidateAudit": None if book is None else book.get("candidateAudit"),
                            "target": None if book is None else _book(book.get("stocks"), book.get("residual"), etf)})
    return out


def decision_receipts(observation: dict, *, recorded_at: datetime, code: dict, observation_sha256: str) -> list[dict]:
    """Receipts for one observation, stamped with the writer's clock. The 10/30-type reconstruction keeps its true time."""
    recorded_at = recorded_at.astimezone(timezone.utc)
    receipts = []
    for strategy in strategies(observation):
        as_of = strategy["asOfDate"]
        if not as_of:
            continue
        signal_final = session_final_utc(as_of, strategy["region"])
        if recorded_at < signal_final:
            raise ValueError(f"RECORDED_BEFORE_SIGNAL_SESSION_FINAL: {strategy['strategyId']} {as_of}")
        execution = execution_session(strategy["region"], as_of, recorded_at)
        key = {"policyVersion": POLICY_VERSION, "region": strategy["region"], "strategyId": strategy["strategyId"],
               "asOfDate": as_of}
        body = {**key, "schema": "ENTRY_STATE_SHADOW_DECISION_V1", "studyId": STUDY, "evidenceClass": EVIDENCE_CLASS,
                "kind": strategy["kind"], "status": strategy["status"], "stockCount": strategy.get("stockCount"),
                "selected": strategy.get("selected"), "candidateAudit": strategy.get("candidateAudit"),
                "targetWeights": strategy["target"],
                "residualAsset": strategy["etf"],
                "residualWeight": (None if strategy["target"] is None
                                   else round(strategy["target"].get(strategy["etf"], 0.0), 8)),
                "action": "TARGET" if strategy["target"] is not None else "HOLD_PREVIOUS_BOOK_NO_TRADE",
                "recordedAtUtc": recorded_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timing": ("RECORDED_BEFORE_EXECUTION_SESSION_OPEN"),
                "signalSessionFinalAtUtc": signal_final.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "executionSession": execution, "executionRule": "CLOSE_OF_FIRST_SESSION_OPENING_AFTER_RECORDING",
                "code": code, "observationSha256": observation_sha256,
                "sourceCommit": observation.get("sourceCommit"),
                "sourceHashes": observation.get("sourceHashes"),
                "sourceArtifactSha256": observation.get("sourceArtifactSha256"),
                "sourceGeneratedAt": observation.get("sourceGeneratedAt"),
                "productionEffect": "NONE", "liveValidated": False}
        body["receiptId"] = sha256(canonical(key))
        # The digest covers what was DECIDED. Who wrote it (code), when it was read (recordedAtUtc) and the execution
        # session that follows from that read time are provenance: a later re-read of the same published week is the
        # same decision, kept as first written, and must not be counted as a conflict.
        body["digest"] = sha256(canonical({k: v for k, v in body.items() if k not in DIGEST_EXCLUDED}))
        receipts.append(body)
    return receipts


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _append(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        for row in rows:
            stream.write(canonical(row) + b"\n")


# Where the bytes were read from, not what was decided. The scheduled hook stamps `sourceCommit` with the moving main commit and
# hashes the bytes of that run, so the same published week read on another day differs in these fields only.
PROVENANCE = ("sourceCommit", "sourceHashes", "observationSha256")


def decided_digest(receipt: dict) -> str:
    """Identity of what was decided, recomputed from the stored body so stored files and their `digest` stay untouched."""
    return sha256(canonical({k: v for k, v in receipt.items() if k not in DIGEST_EXCLUDED and k not in PROVENANCE}))


def append_decisions(directory: Path, receipts: list[dict]) -> dict:
    """Write-once by receiptId. Existing lines are never rewritten."""
    existing = {r["receiptId"]: r for r in _read(directory / "decisions.jsonl")}
    new, same, conflicts = [], 0, []
    for receipt in receipts:
        prior = existing.get(receipt["receiptId"])
        if prior is None:
            new.append(receipt)
            existing[receipt["receiptId"]] = receipt
        elif decided_digest(prior) == decided_digest(receipt):
            same += 1
        else:
            conflicts.append(receipt["receiptId"])
    _append(directory / "decisions.jsonl", new)
    return {"appended": len(new), "alreadyPresent": same, "conflictsRefused": conflicts}


# ------------------------------------------------------------------------------------------------------------------------------
# Accounting
# ------------------------------------------------------------------------------------------------------------------------------
def _weights(units: dict, closes: dict) -> tuple[float, dict]:
    values = {t: u * closes[t] for t, u in units.items()}
    nav = sum(values.values())
    return nav, {t: v / nav for t, v in values.items()}


def anchored_closes(frames: dict, origins: dict[str, str], prior_navs: list[dict]):
    """Put each acquisition in the SAME per-ticker valuation coordinates.

    A later split/dividend rescales Yahoo's adjusted prefix. Dividing both the
    mark and a fixed, explicitly dated origin by that acquisition's origin
    close cancels this common rescaling. Units are units of this vendor index,
    not brokerage shares. Non-uniform revisions of previously marked ratios
    are refused; this is not certification of vendor corporate-action coverage.
    """
    prices, source = {}, {}
    for ticker, origin in sorted(origins.items()):
        frame = frames.get(ticker)
        prices[ticker] = {}
        if frame is None or "Close" not in frame:
            continue
        dates = pd.to_datetime(frame.index).tz_localize(None).strftime("%Y-%m-%d")
        if dates.duplicated().any():
            raise ValueError(f"DUPLICATE_VENDOR_SESSION: {ticker}")
        raw = {d: (float(v) if pd.notna(v) and math.isfinite(float(v)) and float(v) > 0 else None)
               for d, v in zip(dates, frame["Close"])}
        source[ticker] = {"origin": origin, "quotes": sorted(raw.items())}
        anchor = raw.get(origin)
        if anchor is not None:
            prices[ticker] = {d: v / anchor if v is not None else None for d, v in raw.items()}
    for row in prior_navs:
        if row.get("status") != "MARKED":
            continue
        marks = row.get("valuationCloses")
        pinned = row.get("valuationOrigins")
        if row.get("returnBasis") != RETURN_BASIS or not marks or not pinned:
            raise ValueError("LEGACY_VALUATION_BASIS_REQUIRES_EXPLICIT_REVIEW")
        for ticker, previous in marks.items():
            if origins.get(ticker) != pinned.get(ticker):
                raise ValueError(f"VALUATION_ORIGIN_CHANGED: {ticker}")
            current = prices.get(ticker, {}).get(row["date"])
            if current is None:
                raise ValueError(f"PINNED_VENDOR_PREFIX_UNAVAILABLE: {ticker} {row['date']}")
            # Vendor float32 rounding, not an economic tolerance or a repair.
            if not math.isclose(current, previous, rel_tol=1e-6, abs_tol=1e-10):
                raise ValueError(f"VENDOR_RETURN_PREFIX_REVISED: {ticker} {row['date']}")

    def close_of(ticker, session):
        return prices.get(ticker, {}).get(session)
    close_of.valuation_origins = dict(origins)
    # Last session each ticker has a usable quote for IN THIS ACQUISITION. A session after it is not yet published
    # (or the fetch failed): that is a deferral, never evidence that the session's price is missing.
    close_of.quote_through = {t: max((d for d, v in p.items() if v is not None), default=None) for t, p in prices.items()}
    close_of.snapshot_sha256 = sha256(canonical(source))
    return close_of


def fill(units: dict, target: dict, closes: dict, region: str, session: str, etf_tickers: set[str]) -> dict:
    """Move a carried book to its target at one close. Cost is charged here and only here."""
    pre_nav, current = _weights(units, closes)
    legs, cost = [], 0.0
    for ticker in sorted(set(current) | set(target)):
        delta = float(target.get(ticker, 0.0)) - float(current.get(ticker, 0.0))
        if abs(delta) <= ZERO:
            continue
        side = "buy" if delta > 0 else "sell"
        rate = W.trade_cost_fraction(region, session, is_benchmark=ticker in etf_tickers, side=side)
        cost += abs(delta) * rate
        legs.append({"ticker": ticker, "side": side, "weight": round(abs(delta), 10),
                     "instrument": "ETF" if ticker in etf_tickers else "STOCK", "costRateBps": round(rate * 1e4, 4),
                     "costFraction": abs(delta) * rate, "price": closes[ticker],
                     "priceRole": "VENDOR_VALUATION_INDEX_NOT_BROKER_SHARE_QUOTE"})
    post_nav = pre_nav * (1 - cost)
    new_units = {t: w * post_nav / closes[t] for t, w in target.items() if w > ZERO}
    before = {t for t in current if t not in etf_tickers}
    after = {t for t in target if t not in etf_tickers and target[t] > ZERO}
    retargeted = sorted(t for t in before & after if abs(target[t] - current[t]) > ZERO)
    return {"preTradeNav": pre_nav, "postTradeNav": post_nav, "costFraction": cost, "legs": legs,
            "units": new_units, "weights": {t: round(w, 10) for t, w in target.items() if w > ZERO},
            "firstEntry": sorted(after - before), "retained": sorted(before & after), "replaced": sorted(before - after),
            "retargeted": retargeted, "oneWayTurnover": sum(l["weight"] for l in legs) / 2}


def advance(directory: Path, *, now: datetime, close_of, through: str | None = None) -> dict:
    """Advance every strategy's paper book through the final sessions it has not yet marked.

    `close_of(ticker, session) -> float | None` is the price source. Only sessions final at `now` are processed.
    """
    now = now.astimezone(timezone.utc)
    decisions = _read(directory / "decisions.jsonl")
    fills = _read(directory / "fills.jsonl")
    navs = _read(directory / "nav-daily.jsonl")
    by_strategy: dict[str, list[dict]] = {}
    for d in decisions:
        by_strategy.setdefault(d["strategyId"], []).append(d)
    new_fills, new_navs, report = [], [], {}
    for sid, items in sorted(by_strategy.items()):
        items.sort(key=lambda d: d["asOfDate"])
        region = items[0]["region"]
        etf = REGIONAL_ETF[region]
        etf_tickers = {etf, SEPARATE_COMPARISON.get(region, etf)}
        mine_navs = [n for n in navs if n["strategyId"] == sid]
        if mine_navs and mine_navs[-1]["status"] != "MARKED":
            report[sid] = "STOPPED_UNRESOLVED"
            continue
        mine_fills = [f for f in fills if f["strategyId"] == sid]
        filled_ids = {f["decisionReceiptId"] for f in mine_fills}
        # Superseded decisions were consumed too. Restarts must not trade them.
        for previous_fill in mine_fills:
            filled_ids.update(previous_fill.get("supersededReceiptIds") or [])
        if (any(f.get("returnBasis") != RETURN_BASIS for f in mine_fills)
                or (mine_navs and mine_navs[-1].get("returnBasis") != RETURN_BASIS)):
            raise ValueError("LEGACY_VALUATION_BASIS_REQUIRES_EXPLICIT_REVIEW")
        if mine_fills and (not mine_navs or mine_fills[-1]["session"] > mine_navs[-1]["date"]):
            raise ValueError("FILL_NAV_CHECKPOINT_INCOMPLETE")
        units = dict(mine_fills[-1]["units"]) if mine_fills else None
        start = mine_navs[-1]["date"] if mine_navs else items[0]["executionSession"]
        end = through or now.strftime("%Y-%m-%d")
        sessions = [s for s in region_sessions(region, start, end)
                    if (not mine_navs or s > mine_navs[-1]["date"]) and session_final_utc(s, region) <= now]
        first_fill = mine_fills[0]["session"] if mine_fills else None
        for session in sessions:
            pending = [d for d in items if d["receiptId"] not in filled_ids and d["executionSession"] <= session
                       and d["targetWeights"] is not None]
            need = set(units or {}) | (set(pending[-1]["targetWeights"]) if pending else set())
            if units is None and not pending:
                continue                                  # nothing to hold yet
            if units is None:
                need |= {etf}
            closes = {t: close_of(t, session) for t in need}
            missing = sorted(t for t, v in closes.items() if v is None or not math.isfinite(v) or not v > 0)
            published = getattr(close_of, "quote_through", None)
            if missing and published is not None and any(
                    (published.get(t) or "") < session for t in missing):
                # The vendor has not published through this session for a needed name, or the fetch failed. Write
                # nothing, so the next run can mark it; a later quote existing is what makes a gap a real gap.
                report[sid] = f"DEFERRED_QUOTE_NOT_PUBLISHED_THROUGH_{session}"
                break
            if missing:
                new_navs.append({"strategyId": sid, "region": region, "date": session, "status":
                                 "UNRESOLVED_MISSING_PRICE", "missing": missing, "nav": None})
                break
            if units is None:
                units = {etf: 1.0 / closes[etf]}          # NAV 1.0 already held in the regional ETF
            if pending:
                decision = pending[-1]
                result = fill(units, decision["targetWeights"], closes, region, session, etf_tickers)
                row = {"strategyId": sid, "region": region, "session": session,
                       "decisionReceiptId": decision["receiptId"], "decisionAsOfDate": decision["asOfDate"],
                       "supersededReceiptIds": [d["receiptId"] for d in pending[:-1]],
                       "costBasis": NET_ALREADY_CHARGED, "returnBasis": RETURN_BASIS, **result}
                new_fills.append(row)
                filled_ids |= {d["receiptId"] for d in pending}
                units = result["units"]
                first_fill = first_fill or session
            nav, _ = _weights(units, closes)
            new_navs.append({"strategyId": sid, "region": region, "date": session, "status": "MARKED",
                             "nav": nav, "currency": CURRENCY[region], "costBasis": NET_ALREADY_CHARGED,
                             "returnBasis": RETURN_BASIS, "evidenceClass": EVIDENCE_CLASS,
                             "valuationCloses": closes,
                             "valuationOrigins": {t: getattr(close_of, "valuation_origins", {}).get(t) for t in closes},
                             "priceSnapshotSha256": getattr(close_of, "snapshot_sha256", None)})
        report.setdefault(sid, "ADVANCED")
    _append(directory / "fills.jsonl", new_fills)
    _append(directory / "nav-daily.jsonl", new_navs)
    return {"fillsAppended": len(new_fills), "navRowsAppended": len(new_navs), "strategies": report}


def maturity(directory: Path, *, now: datetime) -> dict:
    """Sessions elapsed since each strategy's first fill and its H126/H252 state. Pending is not a zero return."""
    fills = _read(directory / "fills.jsonl")
    navs = _read(directory / "nav-daily.jsonl")
    out = {}
    for sid in sorted({f["strategyId"] for f in fills}):
        first = next(f for f in fills if f["strategyId"] == sid)
        marked = [n for n in navs if n["strategyId"] == sid and n["status"] == "MARKED" and n["date"] >= first["session"]]
        elapsed = max(0, len(marked) - 1)
        out[sid] = {"firstFillSession": first["session"], "sessionsElapsed": elapsed,
                    **{h: ("MATURED" if elapsed >= s else f"PENDING_{s - elapsed}_SESSIONS") for h, s in HORIZONS.items()}}
    return {"asOfUtc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "strategies": out}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------------------------------------------------------------
# Readout connection (economic-path-readout-v1 NAV envelope) and the status report
# ------------------------------------------------------------------------------------------------------------------------------
CALENDAR_POLICY = {"KR": "XKRX", "US": "XNYS"}


def _file_hashes(directory: Path) -> dict:
    return {name: sha256((directory / name).read_bytes()) for name in FILES if (directory / name).exists()}


def benchmark_id(strategy_id: str) -> str:
    region = strategy_id.split(":")[0]
    return f"{region}:ETF_ONLY"


def nav_envelope(directory: Path, strategy_id: str, *, source_commit: str = "UNKNOWN") -> dict:
    """One strategy's NAV in the readout's documented contract. Nothing is rebased, filled or charged here.

    Dates are the region's own sessions (KR: XKRX less the repository's dated closures, US: XNYS), so the readout may
    verify them against a single-exchange calendar. An UNRESOLVED_MISSING_PRICE row is published as null, never dropped.
    """
    rows = [n for n in _read(directory / "nav-daily.jsonl") if n["strategyId"] == strategy_id]
    if not rows:
        raise ValueError(f"NO_NAV_ROWS_YET: {strategy_id}")
    region = rows[0]["region"]
    etf = REGIONAL_ETF[region]
    instrument = (strategy_id.split(":")[-1] if ":SEPARATE_COMPARISON:" in strategy_id
                  else etf if strategy_id == benchmark_id(strategy_id) else None)
    return {"region": region, "strategyId": strategy_id, "studyId": STUDY, "currency": CURRENCY[region],
            "frequency": "DAILY", "returnBasis": RETURN_BASIS, "costBasis": NET_ALREADY_CHARGED,
            "evidenceClass": EVIDENCE_CLASS, "sourceCommit": source_commit, "hashes": _file_hashes(directory),
            "calendarPolicy": CALENDAR_POLICY[region], "fx": "NONE_LOCAL_CURRENCY_BOOK",
            "costNote": "every trade leg charged once at fill; ETF_ONLY never trades so its charged cost is zero",
            **({"instrument": instrument} if instrument else {}),
            "nav": [[n["date"], n["nav"] if n["status"] == "MARKED" else None] for n in rows]}


def readout_input(directory: Path, strategy_id: str, as_of: str, *, source_commit: str = "UNKNOWN",
                  benchmark: str | None = None) -> dict:
    """{asOfDate, candidate, benchmark} for `research.economic_path_readout_v1` (CLI --input or core.compare)."""
    return {"asOfDate": as_of, "candidate": nav_envelope(directory, strategy_id, source_commit=source_commit),
            "benchmark": nav_envelope(directory, benchmark or benchmark_id(strategy_id), source_commit=source_commit)}


def status_report(directory: Path, *, now: datetime) -> dict:
    """What a reader needs per strategy: decision, weights, fill state, cost, NAV, vs ETF, maturity. No new metric."""
    decisions = _read(directory / "decisions.jsonl")
    fills = _read(directory / "fills.jsonl")
    navs = _read(directory / "nav-daily.jsonl")
    matured = maturity(directory, now=now)["strategies"]
    latest_nav = {}
    for n in navs:
        latest_nav[n["strategyId"]] = n
    nav_by = {(n["strategyId"], n["date"]): n for n in navs if n["status"] == "MARKED"}
    out = {}
    for sid in sorted({d["strategyId"] for d in decisions}):
        mine = sorted((d for d in decisions if d["strategyId"] == sid), key=lambda d: d["asOfDate"])
        last = mine[-1]
        my_fills = [f for f in fills if f["strategyId"] == sid]
        consumed = {f["decisionReceiptId"] for f in my_fills} | {r for f in my_fills for r in f.get("supersededReceiptIds") or []}
        target = last["targetWeights"]
        if target is None:
            fill_state = "HOLD_PREVIOUS_BOOK_NO_TRADE"
        elif last["receiptId"] in consumed:
            fill_state = "FILLED"
        else:
            fill_state = "PENDING_EXECUTION_SESSION"
        tail = latest_nav.get(sid)
        if tail and tail["status"] != "MARKED":
            fill_state = "STOPPED_" + tail["status"]
        etf_row = nav_by.get((benchmark_id(sid), tail["date"])) if tail and tail["status"] == "MARKED" else None
        # Every strategy starts at NAV 1.0 on ITS OWN first marked session, which may be later than ETF_ONLY's (a blocked
        # week holds the previous book). The ETF is therefore rebased to that session; dividing by ETF_ONLY's NAV since
        # ITS start would charge the strategy with ETF returns earned before it existed.
        first_nav = next((n for n in navs if n["strategyId"] == sid and n["status"] == "MARKED"), None)
        etf_base = nav_by.get((benchmark_id(sid), first_nav["date"])) if first_nav else None
        excess = None
        if etf_row and etf_base and tail and tail["nav"] and etf_row["nav"] and etf_base["nav"]:
            excess = round(100 * (tail["nav"] / (etf_row["nav"] / etf_base["nav"]) - 1), 6)
        audit = {}
        for row in last.get("candidateAudit") or []:
            audit[row["status"]] = audit.get(row["status"], 0) + 1
        out[sid] = {
            "region": last["region"], "asOfDate": last["asOfDate"], "recordedAtUtc": last["recordedAtUtc"],
            "kind": last["kind"], "decisionStatus": last["status"], "action": last["action"],
            "selected": last.get("selected"), "stockCount": (None if target is None else
                                                             sum(1 for t in target if t not in (last["residualAsset"],))),
            "targetWeights": target, "etfResidualWeight": last.get("residualWeight"),
            "candidateAuditCounts": audit or None,
            "executionSession": last["executionSession"], "fillState": fill_state,
            "fills": len(my_fills), "lastFillSession": my_fills[-1]["session"] if my_fills else None,
            "chargedCostPctOfNav": round(100 * sum(f["costFraction"] for f in my_fills), 6) if my_fills else 0.0,
            "navDate": tail["date"] if tail else None, "nav": tail["nav"] if tail else None,
            "etfNavSameDate": etf_row["nav"] if etf_row else None,
            "excessVsEtfPct": excess,
            "etfBaseDate": first_nav["date"] if excess is not None else None,
            "maturity": matured.get(sid) or {"H126": "PENDING_NO_FILL_YET", "H252": "PENDING_NO_FILL_YET"},
        }
    return {"asOfUtc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "evidenceClass": EVIDENCE_CLASS,
            "returnBasis": RETURN_BASIS, "costBasis": NET_ALREADY_CHARGED,
            "limits": ["vendor adjusted-close ratios are not certified corporate-action or shareholder-return accounting",
                       "units are valuation-index units, not broker shares; no order was placed",
                       "excessVsEtfPct compares the strategy NAV (1.0 at its own first session) with the ETF_ONLY NAV rebased to that session (etfBaseDate); it is not a validated alpha"],
            "strategies": out}
