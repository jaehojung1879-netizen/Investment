"""Which source can serve US point-in-time fundamentals, now that SEC cannot?

WHY THIS PROBE EXISTS. The 13-year replay measures a model that is not the
production model. `alphaDiagnostics` reports `fullComposite` with ZERO
observations in the US and `claimEligible: false`, because the US half of the
`FundamentalStore` is empty: the only file wired into it is
`ledger/fundamentals/pit-kr.jsonl`. Half of the production weight — value 0.3
plus quality 0.2 — has therefore never been tested on a US name. Until that is
closed, no US backtest result, good or bad, is evidence about what we run.

WHY NOT SEC. Measured, across all three axes, and settled:

  * REQUEST SHAPE — `probe_sec_headers`: 4 header sets x 2 hosts = 8 refusals,
    byte-identical block pages (data.sec.gov 4,819B, www.sec.gov 1,925B).
    A refusal that does not change when the request changes is not reading the
    request. Verdict `REFUSED_ON_EVERY_HEADER_SET`.
  * EGRESS ADDRESS — `probe_sec_egress`, run #1 on 2026-09-04: 8 parallel
    runners took 8 DISTINCT Azure addresses, 16 requests, all 403. Verdict
    `REFUSED_ON_EVERY_ADDRESS`.
  * TRAFFIC SHAPE — `probe_sec_bulk_datasets`: the quarterly ZIP downloads are
    a different shape on a different path and are refused the same way.

So the US route needs a host that is not sec.gov. BUT the SEC verdict was
reached on TWO hosts, and "access granted per service is measured per service"
(the KRX lesson) cuts both ways: `efts.sec.gov` and the apex `sec.gov` were
never actually asked. They are asked here, with the two known-refused hosts
included IN THE SAME RUN as the baseline — without it a success would be
attributable to the day rather than to the host.

WHAT DECIDES A VENDOR, in order. The same four questions DART and the SEC
probe asked, plus one this project has never asked and needs:

  1. DOES THE HOST ANSWER US AT ALL, from the Actions IP pool. This is asked
     WITHOUT a credential, because it is a different question from whether a
     credential works, and it is the question run #49 skipped when it shipped
     an unproven KRX endpoint and got 119 of 119 tickers back as 400.
  2. THE PUBLICATION DATE. A 10-Q describes a quarter that ended weeks before
     it was filed. Without a filing date there is no point-in-time and nothing
     else matters — the same standard as DART's receipt date and SEC's `filed`.
  3. HOW FAR BACK, ASKED BY DATE. The replay starts 2013-01-01. v13 is the
     reason this is asked rather than inferred: Naver's `fchart` takes no date
     argument, returned ~3,000 trailing sessions, and the caller applied
     `start` to an already-truncated window — 46,356 Korean rows vanished and
     nothing failed. A vendor that cannot be asked by date gets that as its
     finding, not a depth number computed from a recent-window response.
  4. THE ACCOUNTS, under whatever field name the vendor actually uses. FMP
     shipped a misspelt `fillingDate` on `/api/v3` and `filingDate` on
     `/stable`; a probe that knew one spelling would have reported "no
     point-in-time" about a response carrying it in every row. Candidates per
     concept, and which one answered is recorded.
  5. THE NAMES THAT ARE GONE. 219 of the 829 US names in
     `data/universe-history.json` were members before 2013 and have since
     been delisted — SHLD, ANR, LXK, PCS. A vendor that serves only currently
     listed tickers reproduces, in the US fundamentals, exactly the
     survivorship hole this replay spent v12-v13 closing in Korean prices.
     Living and departed names are measured as SEPARATE cohorts and never
     pooled: pooled, a vendor that drops every dead name looks like a vendor
     with a coverage percentage.

WHAT THIS IS NOT. It is not a backfill and writes nothing to the ledger. It
reports. A vendor with no key in the environment is reported as exactly that
and nothing is claimed about its depth — a credential that was never sent is
not evidence about the vendor.

Usage:  python scripts/probe_us_pit_fundamentals.py [--output us-pit-probe.json]
        [--vendors finnhub,polygon,simfin,fmp,alphavantage] [--living AAPL,JPM]
        [--departed SHLD,ANR] [--skip-sec]
        Keys are read from the environment, one per vendor; all are optional.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import sec_access                                    # noqa: E402

# The replay's own first date. Copied rather than imported: the probe
# workflows install no requirements, and `pipeline.replay_calendar` pulls in
# pandas. `test_us_pit_fundamentals_probe` asserts the two are equal, so the
# copy cannot drift without a test failing.
REPLAY_START = "2013-01-01"

PACE_SECONDS = 0.35
TIMEOUT_SECONDS = 30

# The window is asked for around the replay's own first date rather than "a
# long time ago". A source that reaches 2013-01-01 closes the replay; one that
# reaches 2016 does not, and an answer in years cannot say which.
WINDOW_START = "2012-01-01"
WINDOW_END = "2013-06-30"

# Sample cohorts. The living names repeat the earlier probes' samples so the
# results are comparable across probes; the departed ones come from the
# replay's own membership file (see `departed_samples`).
DEFAULT_LIVING = ("AAPL", "JPM", "XOM", "KO")
DEFAULT_DEPARTED = ("SHLD", "ANR", "LXK", "PCS")

UNIVERSE_HISTORY = ROOT / "data" / "universe-history.json"

# ---------------------------------------------------------------------------
# Reachability, which is a different question from authorisation
# ---------------------------------------------------------------------------
# A vendor that refuses a missing key in its OWN protocol — structured JSON,
# whatever the status code — has answered us: the host is reachable, the base
# and path were read, and the only thing missing is the credential. KRX's
# `{"respMsg":"Unauthorized Key","respCode":"401"}` is the shape, and rolling
# it into "the source could not answer" would retire a source that was never
# actually asked. SEC's refusal is the opposite shape: an HTML interstitial
# that does not read the request at all.
ANSWERED = "ANSWERED"
BLOCK_PAGE = "BLOCK_PAGE"
NO_ANSWER = "NO_ANSWER"


def reach_outcome(status: int | None, body: bytes | None) -> str:
    """Did the HOST answer, whatever it said?

    Deliberately NOT `sec_access.classify`: that one answers "is this data",
    and treats every non-200 as ERROR. Here a 401 carrying the vendor's own
    JSON is the best possible news short of data — it proves the address is
    not blocked — so the body's SHAPE decides and the status does not.
    """
    if status is None and not body:
        return NO_ANSWER
    text = (body or b"")[:2000].decode("utf-8", "replace").lstrip()
    if not text:
        return NO_ANSWER
    for marker in sec_access.BLOCK_MARKERS:
        if marker.lower() in text.lower():
            return BLOCK_PAGE
    if text[:1] in ("{", "["):
        return ANSWERED
    return BLOCK_PAGE


def body_head(body: bytes | None, limit: int = 300) -> str:
    """What the host actually said, trimmed. Never dropped, never paraphrased.

    The FMP 402 was read and then replaced with "non-JSON response", and that
    empty status became "the free tier dropped statements" — a conclusion
    inferred from a bare status code with the vendor's own explanation thrown
    away. The sentence is the finding.
    """
    if not body:
        return ""
    return body[:limit].decode("utf-8", "replace").replace("\n", " ").strip()


def _request(url: str, headers: dict | None = None,
             timeout: int = TIMEOUT_SECONDS) -> tuple[int | None, bytes | None, str]:
    """One GET with bounded retries on transient failures.

    `status` is None only when no response was received at all — a network
    failure, which is a different finding from any HTTP status.
    """
    last_error = ""
    for attempt in range(3):
        request = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return (response.getcode(),
                        sec_access.decode_body(raw, response.headers.get("Content-Encoding")),
                        "")
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = sec_access.decode_body(exc.read(4000), exc.headers.get("Content-Encoding"))
            except Exception:                          # pragma: no cover - network
                pass
            last_error = f"HTTP {exc.code}"
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                return exc.code, body, last_error
        except Exception as exc:                      # pragma: no cover - network
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 2:
                return None, None, last_error
        time.sleep(1.5 * (2 ** attempt))
    return None, None, last_error


# ---------------------------------------------------------------------------
# What the production factors need
# ---------------------------------------------------------------------------
# The concepts, and the field or tag names each vendor might carry them under.
# Several candidates per concept for the same reason `probe_sec_fundamentals`
# keeps `CANDIDATE_TAGS` and the FMP probe keeps both spellings of the filing
# date: a vendor renaming a field is indistinguishable from the field being
# absent, and reads as the worse finding.
CONCEPTS = ("revenue", "netIncome", "operatingIncome", "equity", "liabilities",
            "assets", "operatingCashFlow", "capex", "sharesOutstanding")

# US-GAAP tags, for vendors that re-serve the filer's own XBRL rather than a
# normalised schema. Mirrors `probe_sec_fundamentals.CANDIDATE_TAGS`; which tag
# answered is reported per sample, so a divergence shows up as a named tag
# rather than as a silent miss.
GAAP_TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "netIncome": ["NetIncomeLoss", "ProfitLoss"],
    "operatingIncome": ["OperatingIncomeLoss"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "liabilities": ["Liabilities"],
    "assets": ["Assets"],
    "operatingCashFlow": ["NetCashProvidedByUsedInOperatingActivities",
                          "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForCapitalImprovements",
              "PaymentsToAcquireProductiveAssets"],
    "sharesOutstanding": ["WeightedAverageNumberOfSharesOutstandingBasic",
                          "WeightedAverageNumberOfDilutedSharesOutstanding",
                          "CommonStockSharesOutstanding"],
}

FACTOR_INPUTS = {
    "value · earningsYield":    ["netIncome", "sharesOutstanding"],
    "value · bookYield":        ["equity", "sharesOutstanding"],
    "value · fcfYield":         ["operatingCashFlow", "capex", "sharesOutstanding"],
    "quality · roe":            ["netIncome", "equity"],
    "quality · opMargin":       ["operatingIncome", "revenue"],
    "quality · profitMargin":   ["netIncome", "revenue"],
    "quality · debtToEquity":   ["liabilities", "equity"],
}


def _first_populated(rows: list[dict], candidates: list[str]) -> str | None:
    """The first candidate any row actually carries a non-null value for.

    Present-but-always-null is reported missing: a column of nulls is not a
    field the value sleeve can divide by.
    """
    for name in candidates:
        if any(row.get(name) not in (None, "") for row in rows):
            return name
    return None


def _first_date(row: dict, candidates: tuple[str, ...]) -> tuple[str | None, str | None]:
    """(value, field name) for whichever spelling of a date this row uses."""
    for field in candidates:
        value = row.get(field)
        if value:
            return str(value)[:10], field
    return None, None


def empty_reading() -> dict:
    return {"rowCount": 0, "periodEnds": [], "filingDates": [],
            "filingDateField": None, "fieldsFound": {}, "sampleRow": {}}


# ---------------------------------------------------------------------------
# Per-vendor response readers
# ---------------------------------------------------------------------------
# Each turns one decoded payload into the SAME reading, so `assess_window`
# below judges every vendor by one standard rather than five.

FINNHUB_FILING_FIELDS = ("filedDate", "acceptedDate")
FINNHUB_PERIOD_FIELDS = ("endDate", "periodOfReport")


def read_finnhub(payload) -> dict:
    """`/stock/financials-reported`: the filer's own XBRL, re-served.

    Rows carry `filedDate` (SEC's accepted-filing date) beside `startDate` /
    `endDate`, and the statements arrive as concept/value lists under
    `report.bs|ic|cf` rather than as named columns — so the concepts are
    looked up in those lists, under the same US-GAAP tags the SEC probe uses.
    """
    if isinstance(payload, dict) and "data" not in payload:
        message = payload.get("error") or json.dumps(payload, ensure_ascii=False)[:200]
        return {"errorBody": str(message)}
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {"errorBody": f"unexpected shape: {type(payload).__name__}"}
    if not rows:
        return empty_reading()

    out = empty_reading()
    out["rowCount"] = len(rows)
    for row in rows:
        period, _ = _first_date(row, FINNHUB_PERIOD_FIELDS)
        filed, field = _first_date(row, FINNHUB_FILING_FIELDS)
        out["periodEnds"].append(period)
        out["filingDates"].append(filed)
        if field and not out["filingDateField"]:
            out["filingDateField"] = field

    facts: list[dict] = []
    for row in rows:
        report = row.get("report") or {}
        for section in ("bs", "ic", "cf"):
            entries = report.get(section)
            if isinstance(entries, list):
                facts.extend(e for e in entries if isinstance(e, dict))
    tagged = [{f.get("concept"): f.get("value")} for f in facts]
    flat = {}
    for item in tagged:
        flat.update({k: v for k, v in item.items() if k})
    out["fieldsFound"] = {c: _first_populated([flat], GAAP_TAGS[c]) for c in CONCEPTS}
    first = rows[0]
    out["sampleRow"] = {k: first.get(k) for k in
                        ("symbol", "cik", "year", "quarter", "form", "startDate",
                         "endDate", "filedDate", "acceptedDate") if k in first}
    return out


POLYGON_FILING_FIELDS = ("filing_date", "acceptance_datetime")
POLYGON_PERIOD_FIELDS = ("end_date", "period_of_report_date")


def read_polygon(payload) -> dict:
    """`/vX/reference/financials`: SEC XBRL normalised, with `filing_date`."""
    if not isinstance(payload, dict):
        return {"errorBody": f"unexpected shape: {type(payload).__name__}"}
    if payload.get("status") == "ERROR" or "results" not in payload:
        message = payload.get("error") or payload.get("message") \
            or json.dumps(payload, ensure_ascii=False)[:200]
        return {"errorBody": str(message)}
    rows = payload.get("results") or []
    if not isinstance(rows, list):
        return {"errorBody": "results was not a list"}
    if not rows:
        return empty_reading()

    out = empty_reading()
    out["rowCount"] = len(rows)
    for row in rows:
        period, _ = _first_date(row, POLYGON_PERIOD_FIELDS)
        filed, field = _first_date(row, POLYGON_FILING_FIELDS)
        out["periodEnds"].append(period)
        out["filingDates"].append(filed)
        if field and not out["filingDateField"]:
            out["filingDateField"] = field

    # Polygon nests the statements under `financials.<statement>.<tag>.value`,
    # keyed by the filer's own XBRL tag.
    flat: dict = {}
    for row in rows:
        for statement in (row.get("financials") or {}).values():
            if isinstance(statement, dict):
                for tag, cell in statement.items():
                    if isinstance(cell, dict) and cell.get("value") not in (None, ""):
                        flat.setdefault(tag, cell.get("value"))
    out["fieldsFound"] = {c: _first_populated([flat], GAAP_TAGS[c]) for c in CONCEPTS}
    first = rows[0]
    out["sampleRow"] = {k: first.get(k) for k in
                        ("start_date", "end_date", "filing_date", "acceptance_datetime",
                         "fiscal_period", "fiscal_year", "cik") if k in first}
    return out


# SimFin answers v3 `compact` requests column-oriented: a `columns` list of
# names and a `data` list of rows positionally aligned to it. The column names
# carry spaces and capitals ("Publish Date"), so they are matched
# case-insensitively with the spaces removed rather than by exact spelling.
SIMFIN_FILING_COLUMNS = ("publishdate", "restateddate")
SIMFIN_PERIOD_COLUMNS = ("reportdate", "periodenddate", "fiscalperiodend")
SIMFIN_FIELD_COLUMNS = {
    "revenue": ["revenue", "sales"],
    "netIncome": ["netincome", "netincomecommon"],
    "operatingIncome": ["operatingincome(loss)", "operatingincome"],
    "equity": ["totalequity"],
    "liabilities": ["totalliabilities"],
    "assets": ["totalassets"],
    "operatingCashFlow": ["netcashfromoperatingactivities"],
    "capex": ["changeinfixedassets&intangibles", "capitalexpenditures"],
    "sharesOutstanding": ["sharesdiluted", "sharesbasic"],
}


def _simfin_key(name: str) -> str:
    return str(name).lower().replace(" ", "")


def read_simfin(payload) -> dict:
    """SimFin v3 compact: `columns` + positional `data`, carrying `Publish Date`."""
    if isinstance(payload, dict):
        message = payload.get("error") or payload.get("message") \
            or json.dumps(payload, ensure_ascii=False)[:200]
        return {"errorBody": str(message)}
    if not isinstance(payload, list):
        return {"errorBody": f"unexpected shape: {type(payload).__name__}"}
    statements = []
    for company in payload:
        if isinstance(company, dict):
            statements.extend(s for s in (company.get("statements") or [])
                              if isinstance(s, dict))
    if not statements:
        return empty_reading()

    rows: list[dict] = []
    for statement in statements:
        columns = [_simfin_key(c) for c in (statement.get("columns") or [])]
        for values in (statement.get("data") or []):
            rows.append(dict(zip(columns, values)))
    if not rows:
        return empty_reading()

    out = empty_reading()
    out["rowCount"] = len(rows)
    for row in rows:
        period, _ = _first_date(row, SIMFIN_PERIOD_COLUMNS)
        filed, field = _first_date(row, SIMFIN_FILING_COLUMNS)
        out["periodEnds"].append(period)
        out["filingDates"].append(filed)
        if field and not out["filingDateField"]:
            out["filingDateField"] = field
    out["fieldsFound"] = {c: _first_populated(rows, SIMFIN_FIELD_COLUMNS.get(c, []))
                          for c in CONCEPTS}
    out["sampleRow"] = {k: rows[0].get(k) for k in
                        list(SIMFIN_FILING_COLUMNS) + list(SIMFIN_PERIOD_COLUMNS)
                        if k in rows[0]}
    return out


FMP_FILING_FIELDS = ("filingDate", "fillingDate", "acceptedDate")
FMP_FIELD_NAMES = {
    "revenue": ["revenue"],
    "netIncome": ["netIncome"],
    "operatingIncome": ["operatingIncome"],
    "equity": ["totalStockholdersEquity", "totalEquity"],
    "liabilities": ["totalLiabilities"],
    "assets": ["totalAssets"],
    "operatingCashFlow": ["netCashProvidedByOperatingActivities", "operatingCashFlow"],
    "capex": ["capitalExpenditure"],
    "sharesOutstanding": ["weightedAverageShsOut", "weightedAverageShsOutDil"],
}


def read_fmp(payload) -> dict:
    """FMP `/stable`: both spellings of the filing date are accepted.

    `/api/v3` carried the misspelt `fillingDate` for years and `/stable`
    corrected it; the earlier probe knew only the old spelling and would have
    reported "no filing dates" about a response carrying one in every row.
    """
    if isinstance(payload, dict):
        for key in ("Error Message", "error", "message"):
            if payload.get(key):
                return {"errorBody": str(payload[key])}
        return {"errorBody": json.dumps(payload, ensure_ascii=False)[:200]}
    if not isinstance(payload, list):
        return {"errorBody": f"unexpected shape: {type(payload).__name__}"}
    if not payload:
        return empty_reading()

    out = empty_reading()
    out["rowCount"] = len(payload)
    for row in payload:
        out["periodEnds"].append(str(row.get("date"))[:10] if row.get("date") else None)
        filed, field = _first_date(row, FMP_FILING_FIELDS)
        out["filingDates"].append(filed)
        if field and not out["filingDateField"]:
            out["filingDateField"] = field
    out["fieldsFound"] = {c: _first_populated(payload, FMP_FIELD_NAMES.get(c, []))
                          for c in CONCEPTS}
    out["sampleRow"] = {k: payload[0].get(k) for k in
                        ("date", "period", "filingDate", "fillingDate", "acceptedDate")
                        if k in payload[0]}
    return out


ALPHAVANTAGE_FILING_FIELDS = ("filingDate", "reportedDate", "acceptedDate")


def read_alphavantage(payload) -> dict:
    """Alpha Vantage `INCOME_STATEMENT`: measured for the ABSENCE of a filing
    date rather than excluded on the strength of its documentation."""
    if not isinstance(payload, dict):
        return {"errorBody": f"unexpected shape: {type(payload).__name__}"}
    for key in ("Error Message", "Information", "Note"):
        if payload.get(key):
            return {"errorBody": str(payload[key])}
    rows = payload.get("quarterlyReports") or payload.get("annualReports") or []
    if not isinstance(rows, list):
        return {"errorBody": "quarterlyReports was not a list"}
    if not rows:
        return empty_reading()

    out = empty_reading()
    out["rowCount"] = len(rows)
    for row in rows:
        period = row.get("fiscalDateEnding")
        out["periodEnds"].append(str(period)[:10] if period else None)
        filed, field = _first_date(row, ALPHAVANTAGE_FILING_FIELDS)
        out["filingDates"].append(filed)
        if field and not out["filingDateField"]:
            out["filingDateField"] = field
    out["fieldsFound"] = {
        "revenue": _first_populated(rows, ["totalRevenue"]),
        "netIncome": _first_populated(rows, ["netIncome"]),
        "operatingIncome": _first_populated(rows, ["operatingIncome"]),
        "equity": None, "liabilities": None, "assets": None,
        "operatingCashFlow": None, "capex": None, "sharesOutstanding": None,
    }
    out["sampleRow"] = {k: rows[0].get(k) for k in
                        ("fiscalDateEnding", "reportedCurrency") if k in rows[0]}
    return out


# ---------------------------------------------------------------------------
# One standard, applied to every vendor's reading
# ---------------------------------------------------------------------------
REFUSED = "REFUSED"
NO_ROWS = "NO_ROWS"
NO_FILING_DATE = "NO_FILING_DATE"
WINDOW_NOT_HONOURED = "WINDOW_NOT_HONOURED"
NO_DATE_WINDOW_ENDPOINT = "NO_DATE_WINDOW_ENDPOINT"
PIT_DEPTH_CONFIRMED = "PIT_DEPTH_CONFIRMED"


def _in_window(value: str | None, start: str, end: str) -> bool:
    return bool(value) and start <= value <= end


def assess_window(reading: dict, takes_date_window: bool,
                  start: str = WINDOW_START, end: str = WINDOW_END) -> dict:
    """What one sample's response says about point-in-time depth.

    The order is deliberate. The filing date is decided FIRST, because depth
    without a publication date is depth in a series we may not use: a filing
    dated 2013-03-31 that we cannot show was published before 2013-05-14 is
    lookahead, not history.

    Then depth, and here the two failure shapes are kept apart. A vendor that
    ACCEPTS a date window and answers with rows outside it has not been asked
    what we think we asked — that is the Naver `fchart` shape, where `start`
    was applied to an already-truncated window and 46,356 Korean rows went
    missing without failing anything. A vendor that takes no date argument at
    all is a different finding with a different fix, and saying "too shallow"
    of it would blame the data for the endpoint.
    """
    if reading.get("errorBody"):
        return {"depth": REFUSED, "detail": reading["errorBody"]}
    if not reading.get("rowCount"):
        return {"depth": NO_ROWS, "detail": "응답은 왔지만 행이 없음"}

    periods = [p for p in reading.get("periodEnds") or [] if p]
    filings = [f for f in reading.get("filingDates") or [] if f]
    returned_range = [min(periods), max(periods)] if periods else None
    base = {"rowCount": reading["rowCount"], "returnedRange": returned_range,
            "filingDateField": reading.get("filingDateField"),
            "filingDateCoverage": len(filings),
            # Carried forward so `factor_readiness` can answer from the samples
            # that were actually SERVED rather than from the vendor's docs.
            "fieldsFound": reading.get("fieldsFound") or {}}

    if not filings:
        return {**base, "depth": NO_FILING_DATE,
                "detail": "행은 있으나 공시일이 한 건도 없음 — PIT 불가"}

    inside = [p for p in periods if _in_window(p, start, end)]
    base["rowsInsideWindow"] = len(inside)
    if inside:
        earliest = min(inside)
        return {**base, "depth": PIT_DEPTH_CONFIRMED, "earliestPeriodInWindow": earliest,
                "detail": f"{start}..{end} 창 안에서 {len(inside)}개 기간"}

    if takes_date_window:
        return {**base, "depth": WINDOW_NOT_HONOURED,
                "detail": (f"날짜 창을 받는 엔드포인트인데 {start}..{end} 안의 행이 0개. "
                           f"돌려준 범위: {returned_range}")}
    return {**base, "depth": NO_DATE_WINDOW_ENDPOINT,
            "detail": (f"날짜로 물을 수 없는 엔드포인트이고 가장 이른 기간이 "
                       f"{returned_range[0] if returned_range else '없음'} — "
                       f"리플레이 시작 {REPLAY_START} 에 닿지 않음")}


# ---------------------------------------------------------------------------
# Vendor-level verdicts
# ---------------------------------------------------------------------------
HOST_REFUSED = "HOST_REFUSED"
NO_ANSWER_FROM_HOST = "NO_ANSWER_FROM_HOST"
KEY_MISSING = "KEY_MISSING"
KEY_REFUSED = "KEY_REFUSED"
NO_POINT_IN_TIME = "NO_POINT_IN_TIME"
TOO_SHALLOW = "TOO_SHALLOW"
LIVING_ONLY = "LIVING_ONLY"
OPEN = "OPEN"


def vendor_verdict(reach: str, key_present: bool, living: dict, departed: dict) -> dict:
    """The one line this vendor earns, and what it means for the next move.

    `KEY_MISSING` exists so that a vendor nobody has a credential for is never
    written up as a vendor that failed. Nothing is claimed about its depth:
    a credential that was never sent is not evidence about the source.

    `LIVING_ONLY` exists because pooling the two cohorts hides the finding.
    219 of the 829 US names were members before 2013 and are gone now; a
    vendor that serves only what is listed today answers for 610 of 829 and
    reports as "73% coverage", when what it actually has is a survivorship
    hole in exactly the shape v12-v13 spent two generations closing in Korean
    prices.
    """
    if reach == BLOCK_PAGE:
        return {"verdict": HOST_REFUSED,
                "meaning": ("호스트가 자기 프로토콜이 아닌 차단 페이지로 답했습니다 "
                            "— SEC와 같은 모양이고, 키를 구해도 달라지지 않습니다")}
    if reach != ANSWERED:
        # "아무것도 오지 않았다"는 아직 벤더에 대한 사실이 아닙니다. 우리 쪽
        # (조직 egress 정책, DNS, TLS)을 먼저 배제해야 하고, 그 전에 벤더를
        # 탓하는 것이 바로 SEC 결론이 한동안 가정이었던 이유입니다.
        return {"verdict": NO_ANSWER_FROM_HOST,
                "meaning": ("응답 자체가 없었습니다. 이것은 아직 벤더의 거절이 "
                            "아니라 우리 쪽 송신 경로를 배제하지 못한 상태입니다 "
                            "— 같은 실행의 다른 호스트가 응답했는지 먼저 보십시오")}
    if not key_present:
        return {"verdict": KEY_MISSING,
                "meaning": ("호스트는 Actions 러너에 응답합니다. 키가 환경에 없어 "
                            "깊이는 측정하지 않았습니다 — 보내지 않은 자격증명은 "
                            "이 벤더에 대한 증거가 아닙니다")}

    depths = [row["depth"] for row in list(living.values()) + list(departed.values())]
    if depths and all(d == REFUSED for d in depths):
        return {"verdict": KEY_REFUSED,
                "meaning": ("호스트는 답하고 키는 전달됐지만 모든 표본이 거절됐습니다 "
                            "— 벤더의 거절 문장이 다음 수를 말해 줍니다"),
                "refusals": sorted({str(r.get("detail"))[:200]
                                    for r in living.values() if r.get("detail")})}
    if any(d == NO_FILING_DATE for d in depths) and \
            not any(d == PIT_DEPTH_CONFIRMED for d in depths):
        return {"verdict": NO_POINT_IN_TIME,
                "meaning": "데이터는 오지만 공시일이 없습니다 — 이 소스로는 PIT가 불가능합니다"}

    living_ok = [t for t, r in living.items() if r["depth"] == PIT_DEPTH_CONFIRMED]
    departed_ok = [t for t, r in departed.items() if r["depth"] == PIT_DEPTH_CONFIRMED]
    if not living_ok:
        return {"verdict": TOO_SHALLOW,
                "meaning": (f"살아 있는 표본 중 어느 것도 {WINDOW_START}..{WINDOW_END} "
                            f"창을 채우지 못했습니다 — 리플레이 시작 {REPLAY_START} 에 "
                            f"닿지 않습니다"),
                "depths": sorted({d for d in depths})}
    if departed and not departed_ok:
        return {"verdict": LIVING_ONLY,
                "meaning": ("상장 중인 이름은 2013년까지 닿지만 상장폐지된 이름은 "
                            "하나도 오지 않았습니다 — 생존 편향이 있는 미국 재무 "
                            "패널이 됩니다"),
                "livingServed": living_ok}
    return {"verdict": OPEN,
            "meaning": ("살아 있는 이름과 사라진 이름 모두 공시일이 붙은 2013년 "
                        "재무를 돌려줬습니다 — 미국 경로가 열립니다"),
            "livingServed": living_ok, "departedServed": departed_ok}


# ---------------------------------------------------------------------------
# The vendors, and how each one is asked
# ---------------------------------------------------------------------------
# `requests_for` returns CANDIDATE (label, url, headers) triples rather than
# one URL. Two variables live in that list and neither is safe to assume: the
# URL shape (FMP retired `/api/v3` for statements and `/stable` moved `symbol`
# from the path to a query parameter) and how the credential is PRESENTED
# (KRX's header-vs-query form was inferred from an error string and inferred
# wrong). Whichever candidate answered is recorded.

def _q(params: dict) -> str:
    return urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})


VENDORS: dict[str, dict] = {
    "finnhub": {
        "keyEnv": "FINNHUB_API_KEY",
        "signup": "https://finnhub.io/register",
        "takesDateWindow": True,
        "callsPerTickerWindow": 1,
        "note": "SEC XBRL as filed, re-served; rows carry filedDate and acceptedDate",
        "reachUrl": "https://finnhub.io/api/v1/stock/financials-reported?symbol=AAPL",
        "read": read_finnhub,
        "requests_for": lambda t, key, start, end: [
            ("query-token", "https://finnhub.io/api/v1/stock/financials-reported?"
             + _q({"symbol": t, "freq": "quarterly", "from": start, "to": end,
                   "token": key}), {}),
            ("header-token", "https://finnhub.io/api/v1/stock/financials-reported?"
             + _q({"symbol": t, "freq": "quarterly", "from": start, "to": end}),
             {"X-Finnhub-Token": key}),
        ],
    },
    "polygon": {
        "keyEnv": "POLYGON_API_KEY",
        "signup": "https://polygon.io/dashboard/signup",
        "takesDateWindow": True,
        "callsPerTickerWindow": 1,
        "note": "SEC XBRL normalised; rows carry filing_date and acceptance_datetime",
        "reachUrl": "https://api.polygon.io/vX/reference/financials?ticker=AAPL&limit=1",
        "read": read_polygon,
        "requests_for": lambda t, key, start, end: [
            ("vX-query-key", "https://api.polygon.io/vX/reference/financials?"
             + _q({"ticker": t, "timeframe": "quarterly",
                   "period_of_report_date.gte": start, "period_of_report_date.lte": end,
                   "limit": 50, "apiKey": key}), {}),
            ("vX-bearer", "https://api.polygon.io/vX/reference/financials?"
             + _q({"ticker": t, "timeframe": "quarterly",
                   "period_of_report_date.gte": start, "period_of_report_date.lte": end,
                   "limit": 50}), {"Authorization": f"Bearer {key}"}),
        ],
    },
    "simfin": {
        "keyEnv": "SIMFIN_API_KEY",
        "signup": "https://app.simfin.com/login",
        "takesDateWindow": True,
        "callsPerTickerWindow": 3,
        "note": "normalised statements carrying Publish Date and Restated Date",
        "reachUrl": "https://backend.simfin.com/api/v3/companies/general/compact?ticker=AAPL",
        "read": read_simfin,
        "requests_for": lambda t, key, start, end: [
            ("v3-header", "https://backend.simfin.com/api/v3/companies/statements/compact?"
             + _q({"ticker": t, "statements": "pl,bs,cf", "period": "q1,q2,q3,q4",
                   "start": start, "end": end}), {"Authorization": f"api-key {key}"}),
            ("v3-bare-header", "https://backend.simfin.com/api/v3/companies/statements/compact?"
             + _q({"ticker": t, "statements": "pl,bs,cf", "period": "q1,q2,q3,q4",
                   "start": start, "end": end}), {"Authorization": key}),
            ("v3-query", "https://backend.simfin.com/api/v3/companies/statements/compact?"
             + _q({"ticker": t, "statements": "pl,bs,cf", "period": "q1,q2,q3,q4",
                   "start": start, "end": end, "api-key": key}), {}),
        ],
    },
    "fmp": {
        # Already measured reachable and serving statements with `filingDate`
        # (run #4, 2026-09-05) — but with `limit` capped at 4 periods, and a
        # cap on PAGE SIZE is not an answer about DEPTH. It is asked again
        # here, by date, as the baseline every other vendor is read against.
        "keyEnv": "FMP_API_KEY",
        "signup": "https://site.financialmodelingprep.com/developer/docs",
        "takesDateWindow": False,
        "callsPerTickerWindow": 3,
        "note": "statements served with filingDate; no date window on the endpoint",
        "reachUrl": "https://financialmodelingprep.com/stable/income-statement?symbol=AAPL",
        "read": read_fmp,
        "requests_for": lambda t, key, start, end: [
            ("stable-limit5", "https://financialmodelingprep.com/stable/income-statement?"
             + _q({"symbol": t, "period": "quarter", "limit": 5, "apikey": key}), {}),
            ("stable-annual", "https://financialmodelingprep.com/stable/income-statement?"
             + _q({"symbol": t, "period": "annual", "limit": 5, "apikey": key}), {}),
        ],
    },
    "alphavantage": {
        "keyEnv": "ALPHAVANTAGE_API_KEY",
        "signup": "https://www.alphavantage.co/support/#api-key",
        "takesDateWindow": False,
        "callsPerTickerWindow": 3,
        "note": "probed to MEASURE whether a publication date exists, not to assume it",
        "reachUrl": "https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol=AAPL",
        "read": read_alphavantage,
        "requests_for": lambda t, key, start, end: [
            ("query-apikey", "https://www.alphavantage.co/query?"
             + _q({"function": "INCOME_STATEMENT", "symbol": t, "apikey": key}), {}),
        ],
    },
}


# ---------------------------------------------------------------------------
# SEC, completed per host
# ---------------------------------------------------------------------------
# The SEC verdict was reached on two hosts. "Access granted per service is
# measured per service" — the KRX approval opened one endpoint and left three
# refusing — so two more SEC hosts that were never actually asked are asked
# here. The two KNOWN-refused hosts are in the same list on purpose: without
# the baseline in the same run, a success on a new host would be attributable
# to the day rather than to the host.
SEC_HEADERS = {
    "User-Agent": ("InvestmentResearchDashboard/1.1 "
                   "jaehojung1879-netizen@users.noreply.github.com"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate",
}
SEC_TARGETS = (
    ("data.sec.gov", "https://data.sec.gov/submissions/CIK0000320193.json",
     "baseline — 2026-09-04 에 8개 주소에서 전부 403"),
    ("www.sec.gov", "https://www.sec.gov/files/company_tickers.json",
     "baseline — 2026-09-04 에 8개 주소에서 전부 403"),
    ("efts.sec.gov", "https://efts.sec.gov/LATEST/search-index?q=%22apple%22&forms=10-Q",
     "한 번도 물어본 적 없음 (전문검색 호스트)"),
    ("sec.gov", "https://sec.gov/files/company_tickers.json",
     "한 번도 물어본 적 없음 (www 없는 정점 도메인)"),
)


def probe_sec_hosts() -> dict:
    """Per host: what SEC answered, and how many bytes of it.

    Body SIZE is recorded because that is what settled the header question:
    four header sets returned the same 403 with the same body length every
    time, and a refusal that does not change when the request changes is not
    reading the request. A new host answering with a byte-identical block page
    is the same refusal, not a new one.
    """
    rows = []
    for host, url, note in SEC_TARGETS:
        status, body, error = _request(url, headers=dict(SEC_HEADERS))
        outcome, marker = sec_access.classify(status, body or b"")
        rows.append({"host": host, "url": url, "priorKnowledge": note,
                     "httpStatus": status, "outcome": outcome, "marker": marker,
                     "bodyBytes": len(body or b""), "error": error or None,
                     "bodyHead": body_head(body, 200)})
        time.sleep(PACE_SECONDS)
    served = [r["host"] for r in rows if r["outcome"] == sec_access.SERVED]
    fresh = [r["host"] for r in rows
             if r["outcome"] == sec_access.SERVED and "한 번도" in r["priorKnowledge"]]
    if fresh:
        verdict = {"verdict": "A_SEC_HOST_STILL_SERVES_US",
                   "meaning": (f"{fresh} 가 응답했고 baseline 두 호스트는 같은 실행에서 "
                               f"여전히 거절됐습니다 — 호스트별 차이이지 그날의 운이 "
                               f"아닙니다")}
    elif served:
        verdict = {"verdict": "BASELINE_MOVED",
                   "meaning": (f"이전에 거절되던 호스트가 응답했습니다({served}) — "
                               f"SEC 차단이 풀렸을 수 있으니 egress 프로브를 다시 "
                               f"돌리십시오")}
    else:
        verdict = {"verdict": "REFUSED_ON_EVERY_SEC_HOST",
                   "meaning": ("네 호스트 전부 거절 — 새로 물어본 두 곳도 포함이므로 "
                               "SEC는 호스트를 바꿔도 열리지 않습니다")}
    return {"targets": rows, **verdict}


# ---------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------
def departed_samples(path: Path = UNIVERSE_HISTORY, count: int = 4,
                     before: str = REPLAY_START) -> list[str]:
    """Names the replay HELD before it starts and that no longer exist.

    Read from the membership file rather than hardcoded, so the cohort cannot
    drift away from the universe it is supposed to represent. Sorted, so the
    same four names are asked every run and two runs are comparable.
    """
    try:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return list(DEFAULT_DEPARTED[:count])
    eligible = sorted(
        ticker for ticker, row in rows.items()
        if row.get("region") == "US" and row.get("delisted")
        and str(row.get("listed") or "9999") < before
    )
    return eligible[:count] or list(DEFAULT_DEPARTED[:count])


# ---------------------------------------------------------------------------
# Driving one vendor
# ---------------------------------------------------------------------------
def probe_sample(vendor: dict, ticker: str, key: str) -> dict:
    """One sample against one vendor, trying each candidate request in turn.

    Stops at the first candidate whose body reads as this vendor's data. Every
    attempt is recorded — including the refusals and their bodies — because
    "the path is wrong", "the credential is presented wrong" and "the plan
    excludes this" produce the same failure and have different fixes.
    """
    attempts = []
    for label, url, headers in vendor["requests_for"](
            ticker, key, WINDOW_START, WINDOW_END):
        status, body, error = _request(url, headers=headers)
        time.sleep(PACE_SECONDS)
        try:
            payload = json.loads((body or b"").decode("utf-8"))
        except ValueError:
            attempts.append({"candidate": label, "httpStatus": status,
                             "error": error or "non-JSON body",
                             "bodyHead": body_head(body)})
            continue
        reading = vendor["read"](payload)
        assessment = assess_window(reading, vendor["takesDateWindow"])
        attempts.append({"candidate": label, "httpStatus": status,
                         "error": error or None, "bodyHead": body_head(body, 160),
                         **assessment})
        if assessment["depth"] != REFUSED:
            return {"servedBy": label, "attempts": attempts, **assessment}
    last = attempts[-1] if attempts else {}
    return {"servedBy": None, "attempts": attempts, "depth": REFUSED,
            "detail": last.get("bodyHead") or last.get("error") or "응답 없음"}


def probe_vendor(name: str, vendor: dict, living: list[str],
                 departed: list[str]) -> dict:
    """Reachability first, credential second, depth only if both hold."""
    status, body, error = _request(vendor["reachUrl"])
    reach = reach_outcome(status, body)
    time.sleep(PACE_SECONDS)
    entry = {
        "keyEnv": vendor["keyEnv"], "signup": vendor["signup"],
        "note": vendor["note"], "takesDateWindow": vendor["takesDateWindow"],
        "reach": {"url": vendor["reachUrl"], "httpStatus": status, "outcome": reach,
                  "error": error or None, "bodyHead": body_head(body, 200)},
    }
    key = os.environ.get(vendor["keyEnv"], "").strip()
    entry["keyPresent"] = bool(key)
    entry["keyChars"] = len(key)

    living_rows: dict[str, dict] = {}
    departed_rows: dict[str, dict] = {}
    if reach == ANSWERED and key:
        for ticker in living:
            living_rows[ticker] = probe_sample(vendor, ticker, key)
        for ticker in departed:
            departed_rows[ticker] = probe_sample(vendor, ticker, key)
    entry["living"] = living_rows
    entry["departed"] = departed_rows
    entry.update(vendor_verdict(reach, bool(key), living_rows, departed_rows))

    served = [r for r in list(living_rows.values()) + list(departed_rows.values())
              if r.get("depth") == PIT_DEPTH_CONFIRMED]
    if served:
        entry["factorInputs"] = factor_readiness(served)
    return entry


def factor_readiness(served: list[dict]) -> dict:
    """Which production factors this vendor's fields can actually compute.

    Reported per factor rather than as a field count, because the value sleeve
    does not degrade gracefully: `bookYield` without a share count is not a
    weaker `bookYield`, it is an absent one.
    """
    found: dict[str, str | None] = {}
    for row in served:
        for concept, field in (row.get("fieldsFound") or {}).items():
            if field and not found.get(concept):
                found[concept] = field
    out = {}
    for factor, needs in FACTOR_INPUTS.items():
        missing = [c for c in needs if not found.get(c)]
        out[factor] = {"computable": not missing, "missing": missing}
    out["_fieldsFound"] = found
    return out


def us_universe_size(path: Path = UNIVERSE_HISTORY) -> int:
    """Every US name that was EVER a member, not the names that are members now.

    A point-in-time panel is built for the cross-sections the replay actually
    held. Sizing the backfill off today's 70-name list would under-order by an
    order of magnitude and rebuild the survivorship hole at the same time.
    """
    try:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return 0
    return sum(1 for row in rows.values() if row.get("region") == "US")


def backfill_cost(vendor: dict, entry: dict, universe: int) -> dict:
    """What a full 2012→today backfill would cost this vendor, in calls.

    Calls only. A duration needs a rate limit, and this probe has not measured
    one — reporting "about six days" from a documented quota would be exactly
    the inference from someone else's documentation that this file exists to
    avoid.
    """
    span_years = 15
    window_years = 1.5
    windows = max(1, round(span_years / window_years))
    per_ticker = windows * vendor["callsPerTickerWindow"]
    return {"universeNames": universe, "windowsPerTicker": windows,
            "callsPerWindow": vendor["callsPerTickerWindow"],
            "callsPerTicker": per_ticker,
            "callsForFullBackfill": per_ticker * universe,
            "rateLimit": "측정하지 않음 — 벤더 문서가 아니라 실측이 필요합니다"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="us-pit-probe.json")
    parser.add_argument("--vendors", default=",".join(VENDORS))
    parser.add_argument("--living", default=",".join(DEFAULT_LIVING))
    parser.add_argument("--departed", default="",
                        help="비우면 data/universe-history.json 에서 고릅니다")
    parser.add_argument("--skip-sec", action="store_true",
                        help="SEC 호스트 baseline 을 건너뜁니다")
    args = parser.parse_args(argv)

    living = [t.strip().upper() for t in args.living.split(",") if t.strip()]
    departed = ([t.strip().upper() for t in args.departed.split(",") if t.strip()]
                if args.departed else departed_samples())
    universe = us_universe_size()

    print(f"리플레이 시작 {REPLAY_START} · 창 {WINDOW_START}..{WINDOW_END}")
    print(f"살아 있는 표본 {living}")
    print(f"사라진 표본   {departed}   "
          f"(data/universe-history.json 의 미국 이름 {universe}개 중 상장폐지분)")
    print()

    report: dict = {"contract": "US_PIT_SOURCE_PROBE_V1", "replayStart": REPLAY_START,
                    "window": [WINDOW_START, WINDOW_END],
                    "livingSamples": living, "departedSamples": departed,
                    "usUniverseNames": universe}

    if not args.skip_sec:
        print("=== SEC 호스트 (두 곳은 baseline, 두 곳은 처음 묻는 것) ===")
        sec = probe_sec_hosts()
        for row in sec["targets"]:
            print(f"  {row['host']:<14} {str(row['httpStatus']):<5} "
                  f"{row['outcome']:<8} {row['bodyBytes']:>6}B  {row['priorKnowledge']}")
        print(f"  판정: {sec['verdict']}")
        print(f"  {sec['meaning']}\n")
        report["sec"] = sec

    requested = [v.strip() for v in args.vendors.split(",") if v.strip()]
    unknown = [v for v in requested if v not in VENDORS]
    if unknown:
        print(f"ERROR: 모르는 벤더 {unknown}; 가능한 값 {sorted(VENDORS)}")
        return 2

    vendors: dict[str, dict] = {}
    for name in requested:
        vendor = VENDORS[name]
        print(f"=== {name} ===")
        entry = probe_vendor(name, vendor, living, departed)
        reach = entry["reach"]
        print(f"  도달성(키 없이) {str(reach['httpStatus']):<5} {reach['outcome']:<11} "
              f"{reach['bodyHead'][:110]}")
        if entry["keyPresent"]:
            print(f"  키 {entry['keyChars']}자 · {vendor['keyEnv']}")
        else:
            print(f"  키 없음 · {vendor['keyEnv']} (발급: {vendor['signup']})")
        for cohort, rows in (("살아있음", entry["living"]), ("사라짐", entry["departed"])):
            for ticker, row in rows.items():
                served = f"[{row['servedBy']}]" if row.get("servedBy") else ""
                print(f"    {cohort:<8} {ticker:<6} {row['depth']:<24} "
                      f"{served} {str(row.get('detail'))[:120]}")
        print(f"  판정: {entry['verdict']}")
        print(f"  {entry['meaning']}")
        if entry["verdict"] in (OPEN, LIVING_ONLY):
            entry["backfill"] = backfill_cost(vendor, entry, universe)
            cost = entry["backfill"]
            print(f"  전체 백필: 종목당 {cost['callsPerTicker']}회 × "
                  f"{cost['universeNames']}종목 = {cost['callsForFullBackfill']:,}회")
            for factor, state in (entry.get("factorInputs") or {}).items():
                if factor.startswith("_"):
                    continue
                mark = "가능" if state["computable"] else f"불가 — 부족: {state['missing']}"
                print(f"    {factor:<26} {mark}")
        print()
        vendors[name] = entry

    report["vendors"] = vendors
    open_routes = [n for n, e in vendors.items() if e["verdict"] == OPEN]
    shallow = [n for n, e in vendors.items() if e["verdict"] == TOO_SHALLOW]
    needs_key = [n for n, e in vendors.items() if e["verdict"] == KEY_MISSING]
    living_only = [n for n, e in vendors.items() if e["verdict"] == LIVING_ONLY]
    silent = [n for n, e in vendors.items() if e["verdict"] == NO_ANSWER_FROM_HOST]
    report["summary"] = {"open": open_routes, "livingOnly": living_only,
                         "tooShallow": shallow, "needsKey": needs_key,
                         "noAnswer": silent}

    print("=== 판정 ===")
    if open_routes:
        print(f"  미국 PIT 재무를 2013년까지, 사라진 이름까지 돌려준 소스: {open_routes}")
    else:
        print("  2013년까지·사라진 이름까지 닿은 소스는 이번 실행에 없습니다.")
    if living_only:
        print(f"  상장 중인 이름만 돌려준 소스(생존 편향): {living_only}")
    if shallow:
        print(f"  도달은 하지만 2013년에 닿지 않는 소스: {shallow}")
    if silent:
        print(f"  응답 자체가 없었던 호스트: {silent} — 벤더의 거절로 읽지 "
              f"마십시오. 이 실행의 송신 경로부터 배제해야 합니다.")
    if needs_key:
        print(f"  호스트는 응답하지만 키가 없어 깊이를 재지 못한 소스: {needs_key}")
        for name in needs_key:
            print(f"    {name}: {VENDORS[name]['keyEnv']} ← {VENDORS[name]['signup']}")

    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
    print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":                              # pragma: no cover
    raise SystemExit(main())
