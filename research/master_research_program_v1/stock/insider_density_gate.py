"""G2 information-density gate for kr-insider-open-market-purchase-v1 (OUTCOME-BLIND).

Question answered, and nothing else: on the preregistered 155 anchors, would the PIT Top-120
universe hold enough NET_BUYER and NO_OPEN_MARKET_TRADE issuers for the primary statistic to
exist? The preregistered gate (kr-insider-open-market-purchase-v1.json, powerAndEffectSize.
densityGate): at least 60% of anchors with >= 5 NET_BUYER and >= 20 NO_OPEN_MARKET_TRADE names,
from filings alone.

Reads: DART list.json + document.xml (filings only), the KRX session calendar, the 155 anchor
signal dates (ONLY ``regional.KR[i].signalDate`` of docs/results/regional-standalone-paths.json.gz),
and KRX universe snapshots (rank, for PIT Top-120 membership). It never reads a price after a
filing, a return, a NAV, a label, an IC or a model output.

This is a PROJECTION from the deterministic 24-issuer sample (kr_insider_probe.issuer_sample(24))
of the 254 DART-resolved ever-Top-120 issuers, never a measurement of the full universe.

CLI::

    DART_API_KEY=... python research/master_research_program_v1/stock/insider_density_gate.py collect \
        [--cache DIR] [--max-calls 7000]
    python research/master_research_program_v1/stock/insider_density_gate.py analyze \
        [--cache DIR] --universe DIR --out research/master_research_program_v1/stock/insider-density-gate-v1.json

``collect`` is resume-safe: completed issuer lists and per-filing summaries are cached in DIR and
never re-fetched; fetch errors are retried on the next run; the call counter persists.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.alpha_evidence_sprint_v2 import kr_insider as K  # noqa: E402
from research.alpha_evidence_sprint_v2 import kr_insider_probe as P  # noqa: E402

DEFAULT_CACHE = Path("/tmp/claude-0/-home-user-Investment/3e1f344d-8435-50c1-8877-d6f38a230ceb/scratchpad/laneC")
LIST = "https://opendart.fss.or.kr/api/list.json"
DOC = "https://opendart.fss.or.kr/api/document.xml"
BEGIN, END = "20130101", "20261031"
SAMPLE_SIZE = 24
POPULATION = 254
TOP_N = 120
GATE = {"anchorShare": 0.60, "minBuyers": 5, "minControls": 20}
STOP_STATUSES = {"010", "011", "012", "020", "021", "800", "901"}   # key / quota / maintenance
PARSE_FAILURE_LIMIT = 0.05


# ----------------------------------------------------------------------------- pure functions

def is_insider_original(report_nm: str) -> bool:
    return K.INSIDER_REPORT in (report_nm or "") and "정정" not in (report_nm or "")


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial share; (None, None) when n == 0."""
    if n <= 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def project(k: int, n: int, top_n: int = TOP_N) -> dict:
    """Projected count in a Top-N cross-section from k of n sampled members (Wilson 95%)."""
    lo, hi = wilson(k, n)
    if n <= 0:
        return {"share": None, "projected": None, "low": None, "high": None}
    return {"share": k / n, "projected": top_n * k / n, "low": top_n * lo, "high": top_n * hi}


def anchor_verdict(buy: dict, ctrl: dict, gate: dict = GATE) -> str:
    """PASS if both Wilson LOWER bounds clear the gate, FAIL if either UPPER bound misses it."""
    if buy["projected"] is None or ctrl["projected"] is None:
        return "UNMEASURED"
    if buy["low"] >= gate["minBuyers"] and ctrl["low"] >= gate["minControls"]:
        return "PASS"
    if buy["high"] < gate["minBuyers"] or ctrl["high"] < gate["minControls"]:
        return "FAIL"
    return "UNCERTAIN"


def gate_decision(verdicts: list[str], point_pass: list[bool], gate: dict = GATE) -> dict:
    """PROJECTED_PASS iff anchors whose interval clears the gate are >= the required share;
    PROJECTED_FAIL iff even counting every UNCERTAIN anchor as a pass stays below it."""
    n = len(verdicts)
    need = math.ceil(gate["anchorShare"] * n - 1e-12)
    passed = verdicts.count("PASS")
    possible = passed + verdicts.count("UNCERTAIN")
    if passed >= need:
        verdict = "PROJECTED_PASS"
    elif possible < need:
        verdict = "PROJECTED_FAIL"
    else:
        verdict = "UNCERTAIN"
    return {"verdict": verdict, "anchors": n, "anchorsRequired": need, "anchorsIntervalPass": passed,
            "anchorsIntervalUncertain": verdicts.count("UNCERTAIN"), "anchorsIntervalFail": verdicts.count("FAIL"),
            "anchorsUnmeasured": verdicts.count("UNMEASURED"), "anchorsPointEstimatePass": sum(point_pass)}


def top_members(snapshots: dict[str, list[dict]], top_n: int = TOP_N) -> dict[str, set[str]]:
    """Per snapshot date, the 6-digit codes ranked <= top_n."""
    return {d: {r["code"] for r in rows if r.get("rank") is not None and r["rank"] <= top_n}
            for d, rows in snapshots.items()}


def members_at(anchor: str, members: dict[str, set[str]]) -> set[str] | None:
    """Membership from the latest snapshot dated ON or BEFORE the anchor (never a later one)."""
    dates = [d for d in members if d <= anchor]
    return members[max(dates)] if dates else None


def condition(issuer_codes: dict[str, str], member_codes: set[str] | None) -> list[str]:
    """Sampled corp codes whose common stock code is a member; all of them when UNCONDITIONED."""
    if member_codes is None:
        return sorted(issuer_codes)
    return sorted(c for c, code in issuer_codes.items() if code in member_codes)


def anchor_counts(states: dict[str, str], unresolved: set[str]) -> dict:
    counts = {s: 0 for s in K.STATES}
    for corp, state in states.items():
        if corp not in unresolved:
            counts[state] += 1
    counts["UNRESOLVED_UNPARSED_FILING_IN_WINDOW"] = len(unresolved & set(states))
    return counts


def window_start(anchor: str, sessions: list[str], trailing: int = K.TRAILING_SESSIONS) -> str:
    import bisect
    i = bisect.bisect_right(sessions, anchor) - 1
    return sessions[max(0, i - trailing + 1)]


# ----------------------------------------------------------------------------- collection (network)

class Budget:
    def __init__(self, path: Path, limit: int):
        self.path, self.limit, self.lock = path, limit, threading.Lock()
        self.calls = json.loads(path.read_text())["calls"] if path.exists() else 0

    def take(self):
        with self.lock:
            if self.calls >= self.limit:
                raise RuntimeError("CALL_BUDGET_EXHAUSTED")
            self.calls += 1
            self.path.write_text(json.dumps({"calls": self.calls}))


class SourceStop(RuntimeError):
    pass


def _get(url: str, params: dict, budget: Budget) -> bytes:
    full = url + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(3):
        budget.take()
        time.sleep(0.12)
        try:
            with urllib.request.urlopen(full, timeout=60) as response:
                return response.read()
        except Exception as error:  # noqa: BLE001 - recorded by the caller
            last = error
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{type(last).__name__}: {str(last)[:160]}")


def list_issuer(corp: str, key: str, budget: Budget) -> list[dict]:
    rows, page = {}, 1
    first_total = None
    while True:
        payload = json.loads(_get(LIST, {"crtfc_key": key, "corp_code": corp, "bgn_de": BEGIN, "end_de": END,
                                         "pblntf_ty": "D", "page_no": page, "page_count": 100}, budget))
        status = payload.get("status")
        if status in STOP_STATUSES:
            raise SourceStop(f"list.json {status} {payload.get('message')}")
        if status == "013":
            return []
        if status != "000":
            raise RuntimeError(f"LIST_STATUS_{status}")
        total = (payload.get("total_count"), payload.get("total_page"))
        if first_total is None:
            first_total = total
        elif total != first_total:
            raise RuntimeError("RESULT_SET_CHANGED_MID_WALK")
        for r in payload.get("list") or []:
            rows[r["rcept_no"]] = {k: r.get(k) for k in ("rcept_no", "rcept_dt", "report_nm", "stock_code", "flr_nm")}
        if page >= int(payload.get("total_page") or 1):
            break
        page += 1
    if len(rows) != int(first_total[0] or 0):
        raise RuntimeError("ROW_COUNT_DISAGREES_WITH_TOTAL")
    return sorted(rows.values(), key=lambda r: r["rcept_no"])


def summarize_filing(corp: str, row: dict, payload: bytes, sessions: list[str]) -> dict:
    """Compact per-filing record. Raw bytes are hashed, never stored."""
    rd = row["rcept_dt"]
    receipt = f"{rd[:4]}-{rd[4:6]}-{rd[6:]}"
    base = {"rcept_no": row["rcept_no"], "corp": corp, "stock_code": row.get("stock_code"), "receiptDate": receipt,
            "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    if not payload.startswith(b"PK"):
        text = payload[:300].decode("utf-8", "replace")
        status = text.split("<status>")[1][:3] if "<status>" in text else None
        if status in STOP_STATUSES:
            raise SourceStop(f"document.xml {status}")
        return {**base, "status": "NOT_A_ZIP", "sourceStatus": status}
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        text = "\n".join(K.decode(z.read(n)) for n in sorted(z.namelist()))
    try:
        rows = K.parse_transactions(text)
    except K.ParseError as error:
        return {**base, "status": "PARSE_ERROR", "error": str(error)}
    net = K.open_market_net(rows)
    built = K.build_event(corp, row["rcept_no"], receipt, rows, sessions)   # the owner quarantine rule
    q = built if isinstance(built, K.Quarantine) else None
    return {**base, "status": "PARSED", "rows": len(rows),
            "openMarketRows": sum(1 for r in rows if r["reasonLabel"] in (K.BUY_LABEL, K.SELL_LABEL)
                                  and r["securityLabel"] == K.COMMON_LABEL),
            "openMarketNetShares": net["netShares"], "quarantined": q is not None,
            "rowsAfterReceipt": q.rows_after_receipt if q else 0,
            "maxDaysAfterReceipt": q.max_days_after_receipt if q else None,
            "latestTxDate": max(r["date"] for r in rows) if rows else None,
            "lateRowReasons": _late_reasons(rows, receipt)}


def _late_reasons(rows: list[dict], receipt: str) -> dict:
    """Reason label -> count over detail rows dated after the receipt date (diagnostic only)."""
    out: dict = {}
    for r in rows:
        if r["date"] > receipt:
            label = f'{r["reasonLabel"]}|{r["securityLabel"]}|+{K._days(r["date"], receipt)}d'
            out[label] = out.get(label, 0) + 1
    return out


def collect(key: str, cache: Path, max_calls: int, workers: int = 3, sessions: list[str] | None = None) -> dict:
    if sessions is None:
        sessions = kr_sessions()
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "lists").mkdir(exist_ok=True)
    budget = Budget(cache / "calls.json", max_calls)
    errors = []
    sample = P.issuer_sample(SAMPLE_SIZE)
    listed = {}
    for corp in sample:
        path = cache / "lists" / f"{corp}.json"
        if not path.exists():
            try:
                path.write_text(json.dumps(list_issuer(corp, key, budget), ensure_ascii=False))
            except SourceStop:
                raise
            except RuntimeError as error:
                errors.append({"corp": corp, "endpoint": "list.json", "error": str(error)})
                continue
        listed[corp] = json.loads(path.read_text())
    done_path = cache / "filings.jsonl"
    done = {}
    if done_path.exists():
        for line in done_path.read_text().splitlines():
            rec = json.loads(line)
            if rec.get("quarantined") and "lateRowReasons" not in rec:
                continue          # collected before the diagnostic field existed: re-fetch once
            done[rec["rcept_no"]] = rec
    todo = [(corp, r) for corp, rows in listed.items() for r in rows
            if is_insider_original(r["report_nm"]) and r["rcept_no"] not in done]
    lock = threading.Lock()
    stop = threading.Event()

    def work(item):
        if stop.is_set():
            return
        corp, row = item
        try:
            payload = _get(DOC, {"crtfc_key": key, "rcept_no": row["rcept_no"]}, budget)
            rec = summarize_filing(corp, row, payload, sessions)
        except SourceStop as error:
            stop.set()
            errors.append({"rcept_no": row["rcept_no"], "endpoint": "document.xml", "error": f"STOP {error}"})
            return
        except RuntimeError as error:
            if "BUDGET" in str(error):
                stop.set()
            errors.append({"rcept_no": row["rcept_no"], "endpoint": "document.xml", "error": str(error)})
            return
        with lock, done_path.open("a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(work, todo))
    (cache / "collect-errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=1))
    return {"calls": budget.calls, "issuersListed": len(listed), "todo": len(todo), "errors": len(errors),
            "stopped": stop.is_set()}


# ----------------------------------------------------------------------------- analysis (offline)

def load_anchors() -> list[str]:
    with gzip.open(ROOT / "docs/results/regional-standalone-paths.json.gz", "rt", encoding="utf-8") as fh:
        doc = json.load(fh)
    return [row["signalDate"] for row in doc["regional"]["KR"]]


def load_snapshots(universe: Path) -> dict[str, list[dict]]:
    out = {}
    for path in sorted(universe.glob("krx-universe-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                out.setdefault(r["date"], []).append({"code": r["code"], "rank": r.get("rank")})
    return out


def analyze(cache: Path, universe: Path | None, sessions: list[str], anchors: list[str],
            universe_commit: str | None = None) -> dict:
    listed = {p.stem: json.loads(p.read_text()) for p in sorted((cache / "lists").glob("*.json"))}
    filings = [json.loads(line) for line in (cache / "filings.jsonl").read_text().splitlines()]
    by_no = {f["rcept_no"]: f for f in filings}
    originals = [(corp, r) for corp, rows in listed.items() for r in rows if is_insider_original(r["report_nm"])]
    amendments = sum(1 for rows in listed.values() for r in rows
                     if K.INSIDER_REPORT in (r["report_nm"] or "") and "정정" in r["report_nm"])
    missing = [r["rcept_no"] for _, r in originals if r["rcept_no"] not in by_no]
    status = {}
    for _, r in originals:
        s = by_no.get(r["rcept_no"], {}).get("status", "NOT_FETCHED")
        status[s] = status.get(s, 0) + 1
    failures = len(originals) - status.get("PARSED", 0)
    failure_rate = failures / len(originals) if originals else None
    by_year = {}
    for _, r in originals:
        y = r["rcept_dt"][:4]
        e = by_year.setdefault(y, {"originals": 0, "parsed": 0, "quarantined": 0})
        e["originals"] += 1
        f = by_no.get(r["rcept_no"], {})
        e["parsed"] += f.get("status") == "PARSED"
        e["quarantined"] += bool(f.get("quarantined"))
    # issuer -> common stock code (from DART's own list rows)
    codes = {}
    for corp, rows in listed.items():
        seen = sorted({r["stock_code"] for r in rows if r.get("stock_code")})
        codes[corp] = seen[0] if len(seen) == 1 else (seen[0] if seen else None)
    # events through the owner quarantine rule
    built, unresolved_filings, raw_events = [], [], []
    for corp, r in originals:
        f = by_no.get(r["rcept_no"])
        if f is None or f["status"] != "PARSED":
            rd = r["rcept_dt"]
            unresolved_filings.append((corp, f"{rd[:4]}-{rd[4:6]}-{rd[6:]}"))
            continue
        # the quarantine verdict was taken by K.build_event on the parsed rows at collection time
        avail = K.available_session(f["receiptDate"], sessions)
        if avail is not None:
            raw_events.append(K.Event(corp, f["rcept_no"], f["receiptDate"], avail, f["openMarketNetShares"], None))
        if f["quarantined"]:
            built.append(K.Quarantine(corp, f["rcept_no"], f["receiptDate"], K.QUARANTINE_ROW_DATED_AFTER_RECEIPT,
                                      f["rowsAfterReceipt"], f["maxDaysAfterReceipt"]))
        elif avail is not None:
            built.append(raw_events[-1])
    events, qcount = K.split_events(built)
    quarantined_detail = sorted(({"rcept_no": q.receipt_no, "receiptDate": q.receipt_date,
                                  "rowsAfterReceipt": q.rows_after_receipt,
                                  "maxDaysAfterReceipt": q.max_days_after_receipt}
                                 for q in built if isinstance(q, K.Quarantine)), key=lambda x: x["rcept_no"])
    late = late_row_profile([by_no[q["rcept_no"]] for q in quarantined_detail])
    members = top_members(load_snapshots(universe)) if universe else None
    per_anchor, decision = gate_table(events, unresolved_filings, codes, members, anchors, sessions)
    _, decision_off = gate_table(raw_events, unresolved_filings, codes, members, anchors, sessions)
    decision["notIntervalPassBecause"] = binding_constraints(per_anchor)
    shares = [a["buyerShare"] for a in per_anchor if a["buyerShare"] is not None]
    pooled_k = sum(a["NET_BUYER"] for a in per_anchor)
    pooled_n = sum(a["measured"] for a in per_anchor)
    source_blocked = failure_rate is None or failure_rate > PARSE_FAILURE_LIMIT
    return {
        "gateId": "G2-INFORMATION-DENSITY", "studyId": "kr-insider-open-market-purchase-v1",
        "evidenceClass": "OUTCOME_BLIND_SOURCE_PROBE",
        "isProjection": True,
        "projectionStatement": (f"PROJECTION from a deterministic {SAMPLE_SIZE}-issuer sample (kr_insider_probe."
                                f"issuer_sample({SAMPLE_SIZE}), first {SAMPLE_SIZE} of {POPULATION} DART-resolved "
                                "ever-Top-120 issuers by sha256(corp_code)); per-anchor counts are the sampled members "
                                "only and the Top-120 figures are 120 x sample share with a Wilson 95% interval that "
                                "treats sampled members as a random draw. The same issuers recur across anchors, so "
                                "anchor verdicts are NOT independent."),
        "preregisteredGate": "at least 60% of anchors with >= 5 NET_BUYER and >= 20 NO_OPEN_MARKET_TRADE names, from filings alone",
        "decisionRule": ("anchor PASS iff both Wilson lower bounds clear (>=5 buyers, >=20 no-trade); FAIL iff either upper "
                         "bound misses; overall PROJECTED_PASS iff interval-PASS anchors >= 60%; PROJECTED_FAIL iff "
                         "PASS+UNCERTAIN < 60%; else UNCERTAIN"),
        "membership": ("PIT_TOP120_CONDITIONED: latest signal-history ledger/universe/kr snapshot on or before the anchor, "
                       "rank <= 120 (common and preferred share lines ranked together; the issuer is matched on its "
                       "DART common stock code)") if members is not None else "UNCONDITIONED",
        "membershipSourceCommit": universe_commit,
        "calendar": "pipeline.replay_calendar.sessions(..., 'KR') (offline exchange calendar)",
        "anchorsSource": "docs/results/regional-standalone-paths.json.gz regional.KR[i].signalDate (only key read)",
        "window": f"{K.TRAILING_SESSIONS} KRX sessions ending on the anchor; filing usable from the first session strictly after receipt",
        "quarantineRule": ("owner rule added 2026-11-04 before any outcome: a filing with ANY detail row dated after its DART "
                           "receipt date is QUARANTINED (kr_insider.build_event -> Quarantine) and never contributes to a "
                           "state; not part of the frozen registration's text, recorded here as a pre-outcome addition"),
        "source": {"issuersSampled": len(listed), "listedRange": [BEGIN, END],
                   "insiderOriginals": len(originals), "insiderAmendmentsExcluded": amendments,
                   "notFetched": len(missing), "statusCounts": status, "parseFailures": failures,
                   "parseFailureRate": _r(failure_rate, 6), "parseRate": _r(1 - failure_rate, 6) if failure_rate is not None else None,
                   "parseFailureLimit": PARSE_FAILURE_LIMIT,
                   "sourceVerdict": "SOURCE_BLOCKED" if source_blocked else "SOURCE_PARSE_GATE_PASSED",
                   "byReceiptYear": dict(sorted(by_year.items())),
                   "nonParsedFilings": sorted(({"rcept_no": f["rcept_no"], "status": f["status"],
                                                "error": f.get("error"), "sourceStatus": f.get("sourceStatus")}
                                               for f in by_no.values() if f["status"] != "PARSED"),
                                              key=lambda x: x["rcept_no"]),
                   "parserNote": ("parser kr_insider v2 left UNCHANGED (frozen with the registration): the observed "
                                  "PARSE_ERROR shape is a share-count cell whose digits are split by a line break "
                                  "(e.g. '-\\n2000', '-600\\n00'); fixing it would be a parser v3 = a new registration "
                                  "decision for the owner, and it is far below the 5% SOURCE_BLOCKED limit")},
        "quarantine": {**qcount, "shareOfParsedOriginals": _r(qcount["quarantined"] / max(1, status.get("PARSED", 0)), 4),
                       "lateRowProfile": late, "filings": quarantined_detail},
        "quarantineRuleBound": {
            "purpose": ("bound, not a substitute: the same gate with the owner quarantine rule switched OFF (every parsed "
                        "original contributes). The primary verdict is the rule-ON one; this only shows how much of it "
                        "the rule decides. No alternative rule is proposed or tuned here."),
            "gateRuleOff": decision_off},
        "eventsUsable": len(events),
        "sampleCommonStockCodes": dict(sorted(codes.items())),
        "summary": {"buyerShareMedian": _r(_median(shares), 4), "buyerShareMin": _r(min(shares), 4) if shares else None,
                    "buyerShareMax": _r(max(shares), 4) if shares else None,
                    "pooledBuyerShare": _r(pooled_k / pooled_n, 4) if pooled_n else None,
                    "pooledProjectedTop120Buyers": _r(TOP_N * pooled_k / pooled_n) if pooled_n else None,
                    "sampledMembersMedian": _median([a["sampledMembers"] for a in per_anchor]),
                    "pooledWilson95ProjectedTop120Buyers": [_r(TOP_N * x) if x is not None else None
                                                            for x in wilson(pooled_k, pooled_n)],
                    "pooledNote": ("pooled over all anchor x issuer cells; cells of the same issuer on consecutive "
                                   "anchors are strongly dependent, so this interval is too narrow and is NOT the gate")},
        "gate": decision if not source_blocked else {**decision, "verdict": "SOURCE_BLOCKED"},
        "perAnchor": per_anchor,
        "outcomeAccess": {"returnsRead": 0, "pricesAfterFilingRead": 0, "labelsBuilt": 0, "navsRead": 0,
                          "modelOutputsRead": 0},
    }


def late_row_profile(records: list[dict]) -> dict:
    """Diagnostic over quarantined filings: reason labels and calendar-day gaps of the late rows."""
    labels, gaps, open_market_only = {}, {}, 0
    for f in records:
        reasons = f.get("lateRowReasons") or {}
        only_om = bool(reasons)
        for key, n in reasons.items():
            label, security, gap = key.split("|")
            labels[f"{label}|{security}"] = labels.get(f"{label}|{security}", 0) + n
            d = int(gap.strip("+d"))
            bucket = "1-4d" if d <= 4 else ("5-30d" if d <= 30 else ">30d")
            gaps[bucket] = gaps.get(bucket, 0) + n
            only_om = only_om and label in (K.BUY_LABEL, K.SELL_LABEL)
        open_market_only += only_om
    return {"lateRowsByReasonAndSecurity": dict(sorted(labels.items(), key=lambda kv: -kv[1])),
            "lateRowsByCalendarDayGap": gaps, "filingsWhoseLateRowsAreAllOpenMarket": open_market_only,
            "filingsProfiled": len(records),
            "reading": ("descriptive: a 1-4 calendar-day gap on an open-market row is the shape a settlement-date "
                        "(T+2) 변동일 would leave on a promptly filed report; this is an observation about the filings, "
                        "not a verified explanation, and it does not change the owner rule")}


def binding_constraints(per_anchor: list[dict], gate: dict = GATE) -> dict:
    """Among anchors that are not interval-PASS: which Wilson lower bound missed (both can)."""
    out = {"buyerLowerBoundBelow5": 0, "noTradeLowerBoundBelow20": 0, "both": 0}
    for a in per_anchor:
        if a["anchorVerdict"] == "PASS" or a["buyersWilson95"][0] is None:
            continue
        b = a["buyersWilson95"][0] < gate["minBuyers"]
        c = a["noTradeWilson95"][0] < gate["minControls"]
        out["buyerLowerBoundBelow5"] += b
        out["noTradeLowerBoundBelow20"] += c
        out["both"] += b and c
    return out


def gate_table(events, unresolved_filings, codes, members, anchors, sessions):
    per_anchor, verdicts, point = [], [], []
    for anchor in anchors:
        mem = members_at(anchor, members) if members is not None else None
        sampled = condition(codes, mem)
        start = window_start(anchor, sessions)
        unresolved = set()
        for corp, rdate in unresolved_filings:
            avail = K.available_session(rdate, sessions) or "9999"
            if corp in sampled and start <= avail <= anchor:
                unresolved.add(corp)
        states = {corp: K.state_at(events, corp, anchor, sessions) for corp in sampled}
        counts = anchor_counts(states, unresolved)
        n = len(sampled) - counts["UNRESOLVED_UNPARSED_FILING_IN_WINDOW"]
        buy = project(counts["NET_BUYER"], n)
        ctrl = project(counts["NO_OPEN_MARKET_TRADE"], n)
        v = anchor_verdict(buy, ctrl)
        verdicts.append(v)
        point.append(buy["projected"] is not None and buy["projected"] >= GATE["minBuyers"]
                     and ctrl["projected"] >= GATE["minControls"])
        snap = max((d for d in members if d <= anchor), default=None) if members else None
        per_anchor.append({"anchor": anchor, "sampledMembers": len(sampled), "measured": n, **counts,
                           "membershipSnapshot": snap,
                           "buyerShare": _r(buy["share"], 4), "projectedTop120Buyers": _r(buy["projected"]),
                           "buyersWilson95": [_r(buy["low"]), _r(buy["high"])],
                           "projectedTop120NoTrade": _r(ctrl["projected"]),
                           "noTradeWilson95": [_r(ctrl["low"]), _r(ctrl["high"])], "anchorVerdict": v})
    return per_anchor, gate_decision(verdicts, point)


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def _r(x, nd=3):
    return None if x is None else round(x, nd)


def kr_sessions() -> list[str]:
    from pipeline import replay_calendar as RC
    return [d.strftime("%Y-%m-%d") for d in RC.sessions("2012-06-01", "2026-12-31", "KR")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--cache", default=str(DEFAULT_CACHE))
    c.add_argument("--max-calls", type=int, default=7000)
    c.add_argument("--workers", type=int, default=3)
    a = sub.add_parser("analyze")
    a.add_argument("--cache", default=str(DEFAULT_CACHE))
    a.add_argument("--universe", help="dir of krx-universe-*.jsonl.gz from signal-history; omit => UNCONDITIONED")
    a.add_argument("--out", required=True)
    a.add_argument("--summaries", help="optional gzip JSON of compact per-filing summaries")
    args = ap.parse_args(argv)
    cache = Path(args.cache)
    if args.cmd == "collect":
        key = os.environ.get("DART_API_KEY")
        if not key:
            raise SystemExit("DART_API_KEY_REQUIRED")
        print(json.dumps(collect(key, cache, args.max_calls, args.workers)))
        return 0
    sessions = kr_sessions()
    universe = Path(args.universe) if args.universe else None
    commit = (universe / "COMMIT").read_text().strip() if universe and (universe / "COMMIT").exists() else None
    result = analyze(cache, universe, sessions, load_anchors(), commit)
    calls = cache / "calls.json"
    result["dartCalls"] = json.loads(calls.read_text())["calls"] if calls.exists() else None
    ev = cache / "events" / "calls.json"
    result["dartCallsLaneTotal"] = {"insiderGate": result["dartCalls"],
                                    "eventCounts": json.loads(ev.read_text())["calls"] if ev.exists() else 0,
                                    "manualLatencyCheck": 1}
    result["dartCallsLaneTotal"]["total"] = sum(result["dartCallsLaneTotal"].values())
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    if args.summaries:
        keep = ("rcept_no", "corp", "receiptDate", "status", "openMarketNetShares", "quarantined", "maxDaysAfterReceipt",
                "sourceStatus", "error", "sha256")
        latest = {}
        for line in (cache / "filings.jsonl").read_text().splitlines():
            f = json.loads(line)
            latest[f["rcept_no"]] = f          # a re-fetched filing's last record wins
        rows = [{k: f[k] for k in keep if k in f} for f in latest.values()]
        with gzip.GzipFile(args.summaries, "wb", mtime=0) as fh:
            fh.write(json.dumps(sorted(rows, key=lambda r: r["rcept_no"]), ensure_ascii=False,
                                sort_keys=True, separators=(",", ":")).encode())
    print(json.dumps({"gate": result["gate"]["verdict"], "parseRate": result["source"]["parseRate"],
                      "quarantined": result["quarantine"]["quarantined"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
