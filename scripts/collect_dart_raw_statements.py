"""Collect DART statement responses WHOLE for the PIT KR universe; or probe fiscal 2015.

WHY THIS EXISTS. `collect_dart_fundamentals.py` has three limits the v4
coverage audit (`docs/results/kr-accounting-coverage-audit.json`) measured:

* its universe is `universe.resolve(cfg)` -- today's names, not the dated
  top-120 cross-sections v4 reads -- so 134 of the 260 PIT KR tickers have no
  DART filing at all (751 of 6,218 tradable 2025 name-dates);
* `dart_fundamentals.build_record` keeps only exact-label rows, so a net
  income stated as anything but 당기순이익 is dropped before it reaches disk;
* `fetch_one` reports "013" whenever both CFS and OFS fail, whatever DART
  actually said, so the 1,723 recorded absences cannot say why.

This collector fixes all three without touching either sealed module: the
work list is every ticker ever in a KR top-120 snapshot (`ledger/universe/kr`,
the file v4 reads), the issuer is resolved by the repository's historical
DART identity resolver (so a delisted issuer whose `corpCode.xml` stock code
is blank is still found by its unique exact name), every row DART returns is
stored verbatim under `DART_RAW_STATEMENT_ROWS_V1`, and every attempt keeps
DART's own status and message.

`--mode probe-2015` answers the fiscal-2015 question on a small sample and
writes nothing to the store: the statement endpoint's real status for each
2015 quarterly under CFS and OFS, whether `list.json` shows the original 2015
quarterly and half-year reports with their receipt numbers, and whether the
original XBRL package is served for such a receipt (`fnlttXbrl.xml`; only its
size and ZIP signature are recorded -- nothing is parsed).

POINT IN TIME. `availableFrom` is the served `rcept_no`'s date, never the
collection date. A filing already stored is never re-fetched or overwritten.

Usage:
    python scripts/collect_dart_raw_statements.py <store-dir> --universe-dir <ledger/universe/kr>
        [--mode collect|probe-2015] [--years 2015,2016,...] [--max-calls 1500]
        [--max-minutes 300] [--probe-tickers 8] [--probe-output probe.json]
    DART_API_KEY must be in the environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import collector_outcomes as CO  # noqa: E402
from pipeline import dart_fundamentals as DF  # noqa: E402
from pipeline import dart_ownership_universe as DOU  # noqa: E402
from pipeline import dart_raw_statements as RS  # noqa: E402
from pipeline import dart_xbrl_originals as XO  # noqa: E402
from pipeline import dart_xbrl_statements as XS  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402
from pipeline import kr_corporate_action_events as KCA  # noqa: E402

BASE = "https://opendart.fss.or.kr/api"
PACE_SECONDS = 0.2
# Gate years first (2016 and 2025) with the priors they need, then the rest.
DEFAULT_YEARS = (2015, 2016, 2024, 2025, 2023, 2017, 2018, 2019, 2020, 2021, 2022, 2026)
CODES = ("11013", "11012", "11014", "11011")
ANNUAL_ONLY = ("11011",)
# Fiscal-2015 Q1/H1/Q3 measured 013/013 on 24 of 24 real attempts (the live
# `raw-probe-2015` probe, GitHub Actions run 36300578100) -- a genuine source
# absence for THIS endpoint, not a coverage gap this collector can close.
# Spending calls asking `fnlttSinglAcntAll` for them again would only repeat
# a proven-wasteful request; the annual report (81 of the sealed store's
# 2015 filings) IS served here and stays on this path. The original-filing
# archive (`fnlttXbrl.xml`, via `scripts/collect_dart_xbrl_originals.py`) owns
# recovering the quarterlies, a different endpoint with different depth.
YEARS_LIMITED_TO_ANNUAL = frozenset({2015})


def year_codes(year: int) -> tuple[str, ...]:
    return ANNUAL_ONLY if year in YEARS_LIMITED_TO_ANNUAL else CODES


class Refused(RuntimeError):
    """The source did not answer in its own protocol (HTTP error, not JSON, network)."""


class CallBudgetExhausted(RuntimeError):
    """Raised BEFORE the call that would exceed `--max-calls`."""


def http(path: str, params: dict, timeout: int = 40) -> bytes:
    url = f"{BASE}/{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise Refused(f"HTTP {exc.code}") from exc
    except Exception as exc:  # pragma: no cover - network dependent
        raise Refused(f"{type(exc).__name__}: {exc}") from exc


def call_json(path: str, params: dict) -> dict:
    raw = http(path, params)
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise Refused(f"not JSON ({len(raw)} bytes)") from exc


def corp_directory(key: str) -> list[dict]:
    return DOU.parse_corp_code_zip(http("corpCode.xml", {"crtfc_key": key}, timeout=120))


def pit_universe(universe_dir: Path) -> dict[str, str | None]:
    """ticker -> latest KRX name, for every ticker ever inside a top-120 snapshot.

    The same ranking and cut `alpha_opportunity_v4_execution.load_kr_memberships`
    applies, so this is exactly the set of names v4's cross-sections contain.
    """
    by_date: dict[str, list[dict]] = {}
    for path in sorted(universe_dir.glob("krx-universe-*.jsonl.gz")):
        for row in HS.read_jsonl(path):
            by_date.setdefault(row["date"], []).append(row)
    names: dict[str, tuple[str, str | None]] = {}
    for date, rows in sorted(by_date.items()):
        ranked = sorted((r for r in rows if r.get("rank") is not None),
                        key=lambda r: (r["rank"], r["ticker"]))[:120]
        for r in ranked:
            names[r["ticker"]] = (date, r.get("name"))
    return {ticker: name for ticker, (_, name) in sorted(names.items())}


class Budget:
    def __init__(self, max_calls: int, max_minutes: int):
        self.calls, self.max_calls = 0, max_calls
        self.deadline = time.monotonic() + max_minutes * 60

    def spend(self):
        if self.calls >= self.max_calls:
            raise CallBudgetExhausted()
        if time.monotonic() >= self.deadline:
            raise TimeoutError()
        self.calls += 1


def fetch_statement(key, corp, year, code, budget) -> tuple[list[dict], str | None, list[dict], str | None]:
    """(rows, fsDiv, attempts, stop) for one filing; CFS first, OFS only if CFS served nothing."""
    attempts = []
    for fs_div in RS.FS_ORDER:
        budget.spend()
        payload = call_json("fnlttSinglAcntAll.json", {
            "crtfc_key": key, "corp_code": corp, "bsns_year": str(year),
            "reprt_code": code, "fs_div": fs_div})
        attempts.append(RS.attempt(fs_div, payload))
        status = str(payload.get("status"))
        if status in DF.FATAL_STATUSES:
            return [], None, attempts, f"REFUSED:DART {DF.describe_status(status)}"
        if status == DF.QUOTA_STATUS:
            return [], None, attempts, "DAILY_QUOTA"
        if status in RS.RUN_STOPPING_STATUSES:
            return [], None, attempts, f"REFUSED:DART {DF.describe_status(status)}"
        rows = payload.get("list") or []
        if status == "000" and rows:
            return rows, fs_div, attempts, None
        time.sleep(PACE_SECONDS)
    return [], None, attempts, None


def resolve_all(universe: dict, directory: list[dict]) -> dict[str, dict]:
    return {ticker: KCA.resolve_historical_dart_identity(ticker.split(".")[0], name, directory)
            for ticker, name in universe.items()}


def collect(store: Path, key: str, universe: dict, years, budget: Budget,
            directory_fn=corp_directory) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    identities = resolve_all(universe, directory_fn(key))
    shards = {int(p.stem.split("-")[1].split(".")[0]): HS.read_jsonl(p)
              for p in sorted(store.glob("raw-*.jsonl.gz"))}
    done = {r["id"] for rows in shards.values() for r in rows}
    absent_path = store / "absent.json"
    absent = json.loads(absent_path.read_text(encoding="utf-8")) if absent_path.exists() else {}
    unresolved_path = store / "unresolved.json"
    unresolved = (json.loads(unresolved_path.read_text(encoding="utf-8"))
                  if unresolved_path.exists() else {})
    today = time.strftime("%Y-%m-%d", time.gmtime())
    resolved = {t: i for t, i in identities.items() if i["status"] == KCA.RESOLVED}
    pending = []
    for year in years:
        pending += RS.work_list(resolved, [year], year_codes(year), done, RS.settled(absent, today))

    collected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fresh: dict[int, list[dict]] = {}
    statuses: Counter = Counter()
    stop_reason, written = "WORK_LIST_EXHAUSTED", 0
    for ticker, year, code in pending:
        identity = resolved[ticker]
        try:
            rows, fs_div, attempts, stop = fetch_statement(key, identity["corpCode"], year, code, budget)
        except CallBudgetExhausted:
            stop_reason = "CALL_BUDGET_SPENT"
            break
        except TimeoutError:
            stop_reason = "TIME_BUDGET_SPENT"
            break
        except Refused as exc:
            stop_reason = f"REFUSED:{exc}"
            break
        for a in attempts:
            statuses[f"{a['fsDiv']}={a['status']}"] += 1
        rid = RS.record_id(ticker, year, code)
        if stop:
            # The filing's answers are kept as UNRESOLVED so the log and the
            # store show exactly what DART said; nothing about it is settled.
            unresolved[rid] = RS.unresolved_record(ticker=ticker, fiscal_year=year, report_code=code,
                                                   attempts=attempts, checked_at=collected_at)
            stop_reason = stop if stop.startswith("REFUSED:") else "CALL_BUDGET_SPENT"
            break
        record, reason = RS.build_raw_record(
            ticker=ticker, stock_code=ticker.split(".")[0], corp_code=identity["corpCode"],
            fiscal_year=year, report_code=code, fs_div=fs_div or RS.FS_ORDER[-1], rows=rows,
            attempts=attempts, collected_at=collected_at, identity_basis=identity["basis"])
        if record is None:
            # Only DART's own "no data" on every statement division is evidence
            # that the filing does not exist. Anything else -- 100, 800, 900,
            # 021, 014, a 000 with no rows, an unknown code -- is kept with its
            # statuses and retried, never settled.
            if RS.absence_evidence(attempts) == RS.SOURCE_ABSENCE:
                absent[rid] = RS.absence_record(ticker=ticker, fiscal_year=year, report_code=code,
                                                attempts=attempts, checked_at=collected_at)
                unresolved.pop(rid, None)
            else:
                unresolved[rid] = RS.unresolved_record(ticker=ticker, fiscal_year=year,
                                                       report_code=code, attempts=attempts,
                                                       checked_at=collected_at)
            continue
        unresolved.pop(rid, None)
        fresh.setdefault(year, []).append(record)
        written += 1
        time.sleep(PACE_SECONDS)

    for year, rows in sorted(fresh.items()):
        path = RS.shard_path(store, year)
        HS.write_shard(path, shards.get(year, []) + rows)
        if path.stat().st_size > RS.MAX_SHARD_BYTES:
            raise RuntimeError(f"{path} exceeds {RS.MAX_SHARD_BYTES} bytes; shard finer")
    absent_path.write_text(json.dumps(absent, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                           encoding="utf-8")
    unresolved_path.write_text(json.dumps(unresolved, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                               encoding="utf-8")
    all_records = [r for rows in shards.values() for r in rows] + [r for rows in fresh.values() for r in rows]
    remaining = []
    for year in years:
        remaining += RS.work_list(resolved, [year], year_codes(year),
                                  {r["id"] for r in all_records}, RS.settled(absent, today))
    outcome = CO.run_outcome(stop_reason=stop_reason, calls=budget.calls, written=written)
    manifest = {
        "contract": RS.CONTRACT, "updatedAt": collected_at,
        "pitUniverseTickers": len(universe), "resolvedIssuers": len(resolved),
        "unresolvedIssuers": sorted(t for t, i in identities.items() if i["status"] != KCA.RESOLVED),
        "identityBasis": dict(Counter(i["basis"] for i in identities.values())),
        "years": list(years),
        "storedFilings": len(all_records), "recordedAbsences": len(absent),
        "unresolvedFilings": len(unresolved),
        "sourceAbsenceStatuses": sorted(RS.SOURCE_ABSENCE_STATUSES),
        "remaining": len(remaining), "datasetComplete": not remaining,
        "statusTable": RS.status_table(all_records, absent, unresolved),
        "thisRun": {"calls": budget.calls, "written": written, "stopReason": stop_reason,
                    "outcome": outcome, "attemptStatuses": dict(statuses)},
    }
    (store / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------- #
# list.json discovery + fnlttXbrl.xml fetch, shared by the probe (read-only)
# and the real original-XBRL collector (`collect_dart_xbrl_originals.py`).
# --------------------------------------------------------------------------- #
def periodic_reports_via_list_json(key: str, corp: str, budget: "Budget") -> tuple[list[dict], str]:
    """Every 사업/분기/반기보고서 `list.json` shows for one issuer, fully paginated.

    Never a single-page read: `KCA.fetch_all_pages` walks to the response's
    own `total_page`, exactly the discipline this repository already applies
    to `list.json` for corporate-action discovery.
    """
    def fetch_page(page_no):
        budget.spend()
        return call_json("list.json", {
            "crtfc_key": key, "corp_code": corp, "bgn_de": "20150101", "end_de": "20160630",
            "pblntf_ty": "A", "page_count": "100", "page_no": str(page_no),
            "sort": "date", "sort_mth": "asc"})
    try:
        rows, _ = KCA.fetch_all_pages(fetch_page)
    except KCA.PaginationError as exc:
        return [], f"PAGINATION_ERROR: {exc}"
    periodic = [{"rceptNo": r.get("rcept_no"), "rceptDt": r.get("rcept_dt"), "reportNm": r.get("report_nm")}
                for r in rows if any(k in str(r.get("report_nm")) for k in ("분기보고서", "반기보고서", "사업보고서"))]
    return periodic, ""


def fetch_original_xbrl(key: str, rcept_no: str, report_code: str, budget: "Budget") -> tuple[bytes | None, str]:
    budget.spend()
    try:
        return http("fnlttXbrl.xml", {"crtfc_key": key, "rcept_no": rcept_no, "reprt_code": report_code}), ""
    except Refused as exc:
        return None, str(exc)


def probe_original_stage(key: str, corp: str, periodic: list[dict], stage: str,
                         budget: "Budget", *, dump_entries: bool = False) -> dict:
    """One (issuer, fiscal-2015 stage)'s full original-XBRL evidence: which
    filing is the original, whether its XBRL package is served, and (only
    when served) a CANDIDATE_UNCONFIRMED best-effort read of the four gate
    accounts -- never a claim that the read is correct, only that it ran.
    """
    row, selection = XO.select_original_filing(periodic, stage)
    entry = {"stage": stage, "selection": selection,
            "originalReceiptNo": (row or {}).get("rceptNo"),
            "originalReceiptDate": (row or {}).get("rceptDt"), "xbrl": None}
    if row is None:
        return entry
    body, error = fetch_original_xbrl(key, row["rceptNo"], stage, budget)
    if body is None:
        entry["xbrl"] = {"classification": XO.REQUEST_ERROR, "error": error}
        return entry
    classification, envelope = XO.classify_xbrl_response(body)
    xbrl = {"classification": classification, "bytes": len(body), "errorEnvelope": envelope}
    if classification == XO.XBRL_ZIP_SERVED:
        entries, unzip_error = XS.unzip_entries(body)
        xbrl["zipSha256"] = hashlib.sha256(body).hexdigest()
        xbrl["entryNames"] = [name for name, _ in entries]
        xbrl["unzipError"] = unzip_error
        fiscal_year_start = "2015-01-01"
        period_end = DF.period_end(2015, stage)
        accounts = {}
        for account in XS.TARGET_LOCAL_NAMES:
            _, how = XS.resolve_account(entries, account, fiscal_year_start=fiscal_year_start,
                                        period_end=period_end)
            accounts[account] = how
        xbrl["candidateAccounts"] = accounts
        if dump_entries:
            xbrl["entryTextSnippets"] = {
                name: data.decode("utf-8", "replace")[:2000] for name, data in entries}
    entry["xbrl"] = xbrl
    return entry


def probe_2015(key: str, universe: dict, budget: Budget, sample: int, directory_fn=corp_directory,
               *, dump_entries: bool = False) -> dict:
    """Fiscal-2015 Q1/H1/Q3 availability on a small sample, all three stages,
    two independent endpoints: `fnlttSinglAcntAll` (the ordinary statement
    endpoint) and, via `list.json` discovery, the original-filing archive's
    own `fnlttXbrl.xml`. Writes nothing to the store."""
    identities = resolve_all(universe, directory_fn(key))
    tickers = [t for t, i in identities.items() if i["status"] == KCA.RESOLVED][:sample]
    out = []
    for ticker in tickers:
        corp = identities[ticker]["corpCode"]
        entry = {"ticker": ticker, "corpCode": corp, "statementEndpoint": {}, "originalFilings": []}
        for code in ("11013", "11012", "11014"):
            _, _, attempts, _ = fetch_statement(key, corp, 2015, code, budget)
            entry["statementEndpoint"][code] = attempts
        periodic, list_error = periodic_reports_via_list_json(key, corp, budget)
        entry["listJsonError"] = list_error or None
        for stage in ("11013", "11012", "11014"):
            entry["originalFilings"].append(
                probe_original_stage(key, corp, periodic, stage, budget, dump_entries=dump_entries))
        out.append(entry)
        time.sleep(PACE_SECONDS)
    return {"contract": "DART_FISCAL_2015_QUARTERLY_PROBE_V2", "calls": budget.calls, "sample": out}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store_dir", type=Path)
    parser.add_argument("--universe-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("collect", "probe-2015"), default="collect")
    parser.add_argument("--years", default=",".join(str(y) for y in DEFAULT_YEARS))
    parser.add_argument("--max-calls", type=int, default=1500)
    parser.add_argument("--max-minutes", type=int, default=300)
    parser.add_argument("--probe-tickers", type=int, default=8)
    parser.add_argument("--probe-output", type=Path)
    parser.add_argument("--dump-entries", action="store_true",
                        help="probe-2015 only: embed a bounded text snippet of each served "
                             "ZIP entry in the output, for a human to review real XBRL structure")
    args = parser.parse_args(argv)
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("ERROR: DART_API_KEY not in the environment.")
        return 1
    universe = pit_universe(args.universe_dir)
    if not universe:
        print("ERROR: no KR universe snapshots under", args.universe_dir)
        return 1
    budget = Budget(args.max_calls, args.max_minutes)
    try:
        directory = corp_directory(key)
    except (Refused, ValueError) as exc:
        print(f"ERROR: corpCode.xml not served -- {exc}")
        return 2
    if args.mode == "probe-2015":
        result = probe_2015(key, universe, budget, args.probe_tickers, directory_fn=lambda _: directory,
                            dump_entries=args.dump_entries)
        text = json.dumps(result, ensure_ascii=False, indent=1)
        print(text)
        if args.probe_output:
            args.probe_output.write_text(text + "\n", encoding="utf-8")
        return 0
    years = [int(y) for y in args.years.split(",") if y.strip()]
    manifest = collect(args.store_dir, key, universe, years, budget, directory_fn=lambda _: directory)
    print(json.dumps({k: manifest[k] for k in ("pitUniverseTickers", "resolvedIssuers", "storedFilings",
                                               "recordedAbsences", "unresolvedFilings", "remaining",
                                               "datasetComplete",
                                               "thisRun")}, ensure_ascii=False, indent=1))
    for row in manifest["statusTable"]:
        print(f"  {row['fiscalYear']} {row['reportCode']} {row['result']:6} {row['detail']:28} {row['filings']}")
    if CO.is_reportable_failure(manifest["thisRun"]["outcome"], written=manifest["thisRun"]["written"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
