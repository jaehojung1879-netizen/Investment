"""Reproduce recovery inventory and H126/H252 coverage from private inputs.

Public outputs contain source receipts, dates, counts and failure codes only.
Prices and per-security numerical returns remain in the private input directory.
The fixed original input filters are reused; no old outcome or result is read.
"""
from __future__ import annotations

import argparse
import base64
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

from pipeline import price_adjustment as PA, replay_calendar as RC, us_decision_pilot as PILOT
from pipeline.us_departed_price_recovery import parse_csv
from research.us_historical_market_recovery_v1.collect import AS_OF, private_root
from research.us_historical_market_recovery_v1.engine import (
    Series, Unresolved, frame_series, holding, positive, ranges, required_old_quote_end, whole_window_source,
)

ROOT = Path(__file__).resolve().parents[2]
ALIASES = {"ABC": ("COR", "1140859", "2023-08-30"), "BLL": ("BALL", "9389", "2022-05-10"),
           "CTL": ("LUMN", "18926", "2020-09-18"), "FB": ("META", "1326801", "2022-06-09")}
IDENTITY_DOC = {"ABC": "ATTACHED_ABC", "BLL": "BLL_EFFECTIVE", "CTL": "CTL_EFFECTIVE", "FB": "FB_META"}
PARAMOUNT_CLASS_B_ISSUER_NAMES = {"Paramount Global", "ViacomCBS Inc.", "ViacomCBS Inc"}
# The pinned replay and the supplemental download both have unproven PARA
# lineage. Keep the original replay for the before comparison only.
QUARANTINED_BASELINE = {"PARA"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else raw)


def write_private(path, value):
    raw = canonical(value)
    Path(path).write_bytes(gzip.compress(raw, mtime=0) if str(path).endswith(".gz") else raw)


def check_paramount_class_b_chart(record, metadata):
    """Require explicit source identity for the reused PARA ticker."""
    if record.get("ticker") != "PARA":
        return
    names = {metadata[key].strip() for key in ("longName", "shortName")
             if isinstance(metadata.get(key), str) and metadata[key].strip()}
    if not names or not names <= PARAMOUNT_CLASS_B_ISSUER_NAMES:
        raise Unresolved("PARA_VENDOR_ISSUER_MISMATCH_OR_UNVERIFIED")
    if metadata.get("symbol") != "PARA" or metadata.get("instrumentType") != "EQUITY":
        raise Unresolved("PARA_VENDOR_SECURITY_TYPE_OR_SYMBOL_UNVERIFIED")


def accounting_conflicts(frames, filings, pilot, *, root=ROOT):
    """Find eligible rows whose inputs depend on another issuer's filings."""
    from pipeline import regional_alpha_features as RAF, us_capital_allocation_coverage as C

    membership = RAF.MembershipSnapshots(read(root / pilot.MEMBERSHIP)["snapshots"])
    sectors = C.SectorBook(read(root / pilot.SECTORS)["snapshots"])
    identity = read(root / pilot.IDENTITY)["regions"]["US"]["identity"]
    malformed = {t.upper(): v["resolvedTo"] for t, v in identity["malformed"].items() if v.get("resolvedTo")}
    renames = {t: row["pricedBy"] for t, row in identity["renames"].items() if row.get("pricedBy")}
    caches = {}
    for ticker, records in filings.items():
        by_cik = defaultdict(list)
        unidentified = False
        for row in records:
            cik = str(row.get("cik") or "")
            if cik.isdigit():
                by_cik[str(int(cik))].append(row)
            else:
                unidentified = True
        if len(by_cik) > 1 or unidentified:
            caches[ticker] = {cik: pilot.AccountingCache(rows) for cik, rows in by_cik.items()}

    conflicts = []
    for day, frame in sorted(frames.items()):
        date = day.date().isoformat()
        snap = membership.on(date)
        if snap is None:
            continue
        symbols = {}
        for symbol in snap["members"]:
            normalized = malformed.get(symbol.upper(), symbol)
            symbols.setdefault(renames.get(normalized, normalized), symbol)
        for ticker in frame.index.intersection(caches):
            symbol = symbols.get(ticker)
            cik = sectors.cik(snap, symbol) if symbol else None
            issuer_cache = caches[ticker].get(str(int(cik))) if cik else None
            if issuer_cache is None:
                conflicts.append([date, ticker])
                continue
            values, _ = issuer_cache.at(date)
            if any(values.get(f) != frame.at[ticker, f] for f in PILOT.ACCOUNTING):
                conflicts.append([date, ticker])
    return sorted(conflicts)


def chart_series(record, private, *, from_day=None):
    raw = (private / record["object"]).read_bytes()
    if digest(raw) != record["sha256"]:
        raise Unresolved("CHART_CHECKSUM_MISMATCH")
    chart = json.loads(raw)["chart"]["result"][0]
    check_paramount_class_b_chart(record, chart.get("meta", {}))
    if chart.get("meta", {}).get("currency") != "USD":
        raise Unresolved("QUOTE_CURRENCY_NOT_VERIFIED_USD")
    days = pd.to_datetime([datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d") for t in chart["timestamp"]])
    quotes = chart["indicators"]["quote"][0]
    frame = pd.DataFrame({k.capitalize(): v for k, v in quotes.items()}, index=days)
    if from_day is not None:
        # Ex-date adjustment needs the preceding close even if the requested
        # validation window itself begins on the ex-date.
        first = frame.index.searchsorted(pd.Timestamp(from_day))
        frame = frame.iloc[max(0, first - 1):]
    frame[PA.DIVIDEND], frame[PA.SPLIT] = 0., 0.
    for group, col in (("dividends", PA.DIVIDEND), ("splits", PA.SPLIT)):
        for event in chart.get("events", {}).get(group, {}).values():
            day = pd.Timestamp(datetime.fromtimestamp(event["date"], timezone.utc).date())
            if from_day is not None and day < frame.index[0]:
                continue
            if day not in frame.index:
                raise Unresolved("CORPORATE_ACTION_ON_ABSENT_PRICE_SESSION")
            frame.at[day, col] = event["amount"] if group == "dividends" else event["numerator"] / event["denominator"]
    adjusted = pd.Series(chart["indicators"]["adjclose"][0]["adjclose"], index=days, dtype=float).reindex(frame.index)
    series, deviation = frame_series(record["ticker"], frame, source="YAHOO_CHART", receipt=record["sha256"], basis="SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED", adjusted=adjusted)
    return series, frame, deviation


def auth_rows(private):
    rows = []
    for name in ("authenticated-responses.json.gz", "supplement-responses.json.gz"):
        for row in read(private / name):
            if row.get("body_b64"):
                raw = base64.b64decode(row["body_b64"])
                if digest(raw) != row["sha256"]:
                    raise Unresolved("ACCOUNT_RESPONSE_CHECKSUM_MISMATCH")
                try:
                    row = {**row, "body": json.loads(raw)}
                except ValueError:
                    row = {**row, "body": None}
            rows.append(row)
    return rows


def fmp_series(ticker, by_key):
    selected = [by_key.get(("FMP", endpoint, ticker)) for endpoint in ("historical-price-eod/full", "dividends", "splits")]
    if any(r is None or r["status"] != 200 or not isinstance(r.get("body"), list) for r in selected):
        raise Unresolved("FMP_PRICE_OR_ACTION_ENTITLEMENT_MISSING")
    price, div, split = selected
    rows = price["body"]
    if not rows:
        raise Unresolved("EMPTY_PRICE_RESPONSE")
    frame = pd.DataFrame(rows).set_index("date").sort_index()
    frame.index = pd.to_datetime(frame.index)
    frame = frame.rename(columns={k: k.capitalize() for k in ("open", "high", "low", "close", "volume")})
    frame[PA.DIVIDEND], frame[PA.SPLIT] = 0., 0.
    for row in div["body"]:
        day = pd.Timestamp(row["date"])
        if day in frame.index:
            # Both the full EOD price and adjDividend are split adjusted.
            frame.at[day, PA.DIVIDEND] += float(row["adjDividend"])
    for row in split["body"]:
        day = pd.Timestamp(row["date"])
        if day in frame.index:
            frame.at[day, PA.SPLIT] = float(row["numerator"]) / float(row["denominator"])
    series, _ = frame_series(ticker, frame, source="FMP_EOD_PLUS_ACTIONS", receipt=price["sha256"], basis="SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED")
    return series, frame, [r["sha256"] for r in selected]


def official_benchmark(series, frame, private):
    from openpyxl import load_workbook
    book = load_workbook(private / "identity-sources/spy-official-distributions.xlsx", read_only=True, data_only=True)
    official = {}
    for row in book["dividend"].iter_rows(min_row=2, values_only=True):
        if row[1] == "SPY" and row[2] == "78462F103":
            day = datetime.strptime(row[3], "%m/%d/%Y").strftime("%Y-%m-%d")
            official[day] = sum(float(str(v).replace(",", "")) for v in row[6:9] if v and str(v).strip() != "-")
    comparison, differences = [], []
    for day in frame.index.strftime("%Y-%m-%d"):
        vendor = float(frame.at[day, PA.DIVIDEND])
        actual = official.get(day, 0.)
        if vendor or actual:
            comparison.append(day)
            if abs(vendor - actual) > .0005:
                differences.append({"date": day, "vendor": vendor, "official": actual})
    corrected = frame.copy()
    corrected[PA.DIVIDEND] = [official.get(d, 0.) for d in corrected.index.strftime("%Y-%m-%d")]
    result, _ = frame_series("SPY", corrected, source="YAHOO_RAW_PLUS_SSGA_OFFICIAL_DISTRIBUTIONS", receipt=series.receipt, basis="SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED")
    result.identity_verified = result.actions_verified = True
    return result, {"official_source": "https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx",
                    "official_sha256": digest((private / "identity-sources/spy-official-distributions.xlsx").read_bytes()),
                    "events_compared": len(comparison), "disagreements": differences,
                    "correction_scope": "NEW_PRIVATE_BENCHMARK_ONLY_ORIGINAL_INPUT_UNCHANGED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uploaded-dir", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    private = private_root(args.private_root)
    inputs = args.uploaded_dir
    original = read(private / "baseline-bars.json.gz")
    requests = read(inputs / "us-212-market-data-request.json")
    manifest = read(inputs / "provenance.json")
    for name, expected in manifest.items():
        if name != "input_paths" and digest((inputs / name).read_bytes()) != expected:
            raise Unresolved("UPLOADED_INPUT_CHECKSUM_MISMATCH:" + name)
    if len(requests) != 212 or len({r["security_audit_id"] for r in requests}) != 212:
        raise Unresolved("COHORT_CHANGED")
    calendar = [str(d.date()) for d in RC.sessions("2011-01-03", "2028-01-14", "US")]
    calendar_set = set(calendar)
    latest = auth_rows(private)
    by_key = {(r["provider"], r["endpoint"], r["ticker"]): r for r in latest}
    chart_records = read(private / "new_charts.json")
    extra_charts = read(private / "last-gap-public-charts.json") if (private / "last-gap-public-charts.json").exists() else []
    chart_records += extra_charts
    charts, chart_frames, diagnostics = {}, {}, {}
    for rec in chart_records:
        if rec.get("status") == 200 and rec.get("rows", 0) > 1:
            try:
                series, frame, error = chart_series(rec, private)
                charts[rec["ticker"]], chart_frames[rec["ticker"]] = series, frame
                diagnostics[rec["ticker"]] = {"rows": len(frame), "valid_trading_rows": len(series.good_days),
                                              "maximum_adjusted_level_deviation": error, "sha256": series.receipt}
            except Unresolved as exc:
                diagnostics[rec["ticker"]] = {"blocked": str(exc)}
    spy, spy_report = official_benchmark(charts["SPY"], chart_frames["SPY"], private)
    public_docs = read(private / "identity-sources/public-receipts.json")
    docs = {r["id"]: r for r in public_docs if r["status"] == 200}
    supplied = read(inputs / "public-corporate-event-evidence.json")
    docs["ATTACHED_ABC"] = next(r for r in supplied if r["audit_identifier"] == "ABC")
    new_sources, source_frames, source_receipts = {}, {}, {}
    for old, (new, cik, effective) in ALIASES.items():
        if new in charts and IDENTITY_DOC[old] in docs:
            s = charts[new]
            s.identity_verified = s.actions_verified = True
            new_sources[old], source_frames[old] = s, chart_frames[new]
            source_receipts[old] = {"source": s.source, "price_sha256": s.receipt, "cik": cik,
                                    "class": "Class A common" if old == "FB" else "Common",
                                    "symbol_change_effective": effective, "successor_symbol": new,
                                    "identity_citation": docs[IDENTITY_DOC[old]]["url"],
                                    "identity_sha256": docs[IDENTITY_DOC[old]].get("sha256", docs[IDENTITY_DOC[old]].get("source_sha256"))}
    for ticker in ("ATVI", "MRO", "TWTR", "VIAC", "WBA"):
        try:
            s, f, receipts = fmp_series(ticker, by_key)
        except Unresolved as exc:
            diagnostics[ticker] = {"blocked": str(exc)}
            continue
        # Sources explicitly tie these names to registered common shares. VIAC
        # remains scoped to the post-2019 common class; old Viacom is not joined.
        s.identity_verified = s.actions_verified = True
        lower = "2019-12-05" if ticker == "VIAC" else "2014-12-31" if ticker == "WBA" else "1900-01-01"
        s.good_days = {d for d in s.good_days if d >= lower}
        new_sources[ticker], source_frames[ticker] = s, f
        source_receipts[ticker] = {"source": s.source, "source_sha256s": receipts, "identity_valid_from": lower,
                                    "cik": {"ATVI": "718877", "MRO": "101778", "TWTR": "1418091", "VIAC": "813828", "WBA": "1618921"}[ticker],
                                    "class": "Class B common" if ticker == "VIAC" else "Common",
                                    "identity_citation": next((r["url"] for r in supplied if r["audit_identifier"] == ticker),
                                                               docs.get({"MRO": "MRO_EXCHANGE", "WBA": "WBA_DAP", "VIAC": "VIAC_CLASS_B"}.get(ticker, ""), {}).get("url"))}
    alternate_series = {}
    if "PARA" in charts:
        successor = charts["PARA"]
        successor.identity_verified = successor.actions_verified = True
        successor.good_days = {d for d in successor.good_days if d >= "2019-12-05"}
        alternate_series["VIAC"] = successor
        source_receipts["VIAC"]["additional_whole_publisher_series"] = {
            "source": successor.source, "sha256": successor.receipt, "symbol": "PARA",
            "class": "Class B common", "cik": "813828", "symbol_effective": "2022-02-17",
            "identity_citation": docs["VIAC_CLASS_B"]["url"],
            "restriction": "Each entire holding uses one publisher series; no price-level splice"}
    terminals = {
        "ATVI": {"date": "2023-10-13", "cash": 95., "verified": True, "effective_before_open": True},
        "TWTR": {"date": "2022-10-27", "cash": 54.2, "verified": True},
        "MRO": {"date": "2024-11-22", "shares": .255, "successor": "COP", "verified": True,
                "cash_in_lieu_required": True, "effective_before_open": True},
        "WBA": {"date": "2025-08-28", "cash": 11.45, "cvr": True, "verified": True, "effective_before_open": True},
    }
    for ticker, terminal in terminals.items():
        if ticker in new_sources:
            s = new_sources[ticker]
            terminal["last_trading_date"] = max(d for d in s.good_days if d <= terminal["date"])
            terminal["citation"] = source_receipts[ticker]["identity_citation"]
    settlement = read(Path(__file__).with_name("inputs") / "terminal-followup.json")
    terminals["MRO"].update(settlement["MRO"])
    terminals.update({ticker: settlement[ticker] for ticker in ("KVUE", "WBD")})
    # A whole publisher series per security. No old/new level concatenation.
    baseline = {}
    for ticker, rows in original.items():
        tr = pd.Series({d: r["Close"] for d, r in rows.items()}, dtype=float)
        tr.index = pd.to_datetime(tr.index)
        tr = tr.sort_index()
        baseline[ticker] = Series(ticker, tr, tr.copy(), set(tr.index[tr.map(positive)].strftime("%Y-%m-%d")),
                                  "ORIGINAL_REPLAY_V16_TOTAL_RETURN", "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2", True, True)
    # These whole publisher series fill LABEL paths only. The signal input frame
    # and eligible universe remain fixed to the original cutoff and nine packets.
    label_followups, followup_diagnostics, historical_followup_refusals = {}, {}, {}
    # Calendar-only lower bound: earliest post-cutoff H252 entry minus a full
    # 253-session common-price check. It is unrelated to observed returns.
    followup_bound = calendar[bisect_left(calendar, "2026-09-14") - 252 - 253]
    followup_records = read(private / "label_followup_charts.json") if (private / "label_followup_charts.json").exists() else []
    for record in followup_records:
        ticker = record["audit_identifier"]
        reference = new_sources.get(ticker, baseline.get(ticker))
        if reference is None or record.get("status") != 200 or record.get("rows", 0) < 2:
            followup_diagnostics[ticker] = {"status": "NO_USABLE_FOLLOWUP_SERIES", "http_status": record.get("status")}
            continue
        try:
            scoped = False
            try:
                s, _, error = chart_series(record, private)
            except Unresolved as full_error:
                historical_followup_refusals[ticker] = str(full_error)
                s, _, error = chart_series(record, private, from_day=followup_bound)
                scoped = True
            common = s.tr.index.intersection(reference.tr.index)[-253:]
            ratio = (s.tr.loc[common] / reference.tr.loc[common]).replace([float("inf"), -float("inf")], float("nan")).dropna()
            deviation = float((ratio / ratio.median() - 1).abs().max()) if len(ratio) else float("inf")
            if len(ratio) < 126 or deviation > 1e-5:
                raise Unresolved("ORIGINAL_SECURITY_COMMON_WINDOW_BASIS_UNRECONCILED")
            s.identity_verified = s.actions_verified = True  # inherited original identity limitations, explicitly reported
            label_followups[ticker] = s
            followup_diagnostics[ticker] = {"status": "WHOLE_SERIES_LABEL_PATH_ONLY_ORIGINAL_IDENTITY_CONTRACT",
                "sha256": s.receipt, "rows": len(s.good_days), "first": min(s.good_days), "last": max(s.good_days),
                "original_common_sessions": len(ratio), "original_common_normalized_deviation": deviation,
                "vendor_adjusted_level_deviation": error,
                "validation_window_from": followup_bound if scoped else "2011-01-03",
                "older_full_history_refusal_preserved": historical_followup_refusals.get(ticker)}
        except Unresolved as exc:
            followup_diagnostics[ticker] = {"status": str(exc)}
    # Candidate input eligibility uses the original financial/time/sector gates.
    # This invokes no label reading, model fit, strategy evaluation or old result.
    from scripts import run_us_decision_pilot as P
    from research.us_historical_market_recovery_v1.prepare import verify_input_helpers
    helper_pins = verify_input_helpers()
    original_cohorts = read(private / "original-input-eligible-cohorts.json")
    repaired_file = private / "repaired-input-eligible-cohorts.json"
    frame = pd.DataFrame({t: s.tr for t, s in baseline.items() if t not in QUARANTINED_BASELINE})
    fixed_sessions = RC.sessions("2011-01-03", "2026-09-14", "US")
    frame = frame.reindex(fixed_sessions)
    for ticker, source in new_sources.items():
        frame[ticker] = source.tr.reindex(fixed_sessions).where(
            [d.strftime("%Y-%m-%d") in source.good_days for d in fixed_sessions])
    dependency_files = [private / n for n in ("baseline-bars.json.gz", "original-input-eligible-cohorts.json",
                        "authenticated-responses.json.gz", "supplement-responses.json.gz", "new_charts.json")]
    dependency_files += [ROOT / n for n in ("scripts/run_us_decision_pilot.py", "pipeline/us_decision_pilot.py",
                         "research/us_historical_market_recovery_v1/audit.py", "research/us_historical_market_recovery_v1/engine.py")]
    dependency_files.append(Path(__file__).with_name("inputs") / "terminal-followup.json")
    cache_key = digest(canonical([digest(p.read_bytes()) for p in dependency_files]))
    repaired = read(repaired_file) if repaired_file.exists() else {}
    if repaired.get("input_cache_key") != cache_key:
        filings, _ = P.load_filings()
        for old, (new, _, _) in ALIASES.items():
            if old in new_sources and old not in filings and new in filings:
                filings[old] = filings[new]  # immutable records; actual CIK checks remain in the original helper
        frames, annual, weeks = P.build_signals(frame, filings)
        conflicts = accounting_conflicts(frames, filings, P)
        blocked = defaultdict(set)
        for day, ticker in conflicts:
            blocked[day].add(ticker)
        cohorts = []
        for day, frame_at_day in sorted(frames.items()):
            text = day.date().isoformat()
            tickers = sorted(set(frame_at_day.index) - blocked[text])
            if len(tickers) >= PILOT.MIN_NAMES:
                cohorts.append({"signal": text, "tickers": tickers})
        repaired = {"cohorts": cohorts, "accounting_issuer_conflicts": conflicts,
                    "issuer_conflict_scope": "ORIGINAL_DATED_CIK_SINGLE_ISSUER_RECHECK",
                    "annual": annual, "weeks": weeks, "input_cache_key": cache_key}
        write_private(repaired_file, repaired)
    old_cohorts = {r["signal"]: set(r["tickers"]) for r in original_cohorts["cohorts"]}
    new_cohorts = {r["signal"]: set(r["tickers"]) for r in repaired["cohorts"]}
    issuer_conflicts = {tuple(row) for row in repaired["accounting_issuer_conflicts"]}
    cohort = {(day, ticker) for day in old_cohorts.keys() | new_cohorts.keys()
              for ticker in old_cohorts.get(day, set()) | new_cohorts.get(day, set())} | issuer_conflicts
    horizon_counts, private_labels = {}, []
    for horizon in (126, 252):
        counts, annual = {"before": Counter(), "after": Counter()}, defaultdict(lambda: {"before": Counter(), "after": Counter()})
        for day, ticker in sorted(cohort):
            entry_pos = bisect_left(calendar, day) + 1
            entry, end = calendar[entry_pos], calendar[entry_pos + horizon]
            for phase, members in (("before", old_cohorts), ("after", new_cohorts)):
                status, value, benchmark_value = None, None, None
                missing_security, missing_benchmark = [], []
                if phase == "after" and ticker in QUARANTINED_BASELINE:
                    status = "PRICE_SECURITY_IDENTITY_QUARANTINED" if end <= AS_OF else "NOT_MATURED"
                elif phase == "after" and (day, ticker) in issuer_conflicts:
                    status = "ACCOUNTING_ISSUER_CONFLICT" if end <= AS_OF else "NOT_MATURED"
                elif ticker not in members.get(day, set()):
                    status = "INPUT_NOT_ELIGIBLE"
                elif end > AS_OF:
                    status = "NOT_MATURED"
                else:
                    terminal = terminals.get(ticker) if phase == "after" else None
                    quote_end = required_old_quote_end(entry, end, terminal)
                    source = baseline.get(ticker)
                    if phase == "after":
                        source = whole_window_source(label_followups.get(ticker), new_sources.get(ticker, source),
                                                     entry, quote_end)
                        source = whole_window_source(alternate_series.get(ticker), source, entry, quote_end)
                    if source is None:
                        status = "PRICE_SOURCE_MISSING"
                    else:
                        try:
                            if terminal and entry <= terminal["date"] <= end and source is baseline.get(ticker):
                                raise Unresolved("TERMINAL_RAW_CLOSE_UNVERIFIED")
                            value = holding(source, entry, end, calendar, terminal=terminal,
                                            successors=label_followups if phase == "after" else None)
                            benchmark_value = holding(spy if phase == "after" else baseline["SPY"], entry, end, calendar)
                            status = "COMPLETE_ORIGINAL_RESEARCH_CONTRACT"
                        except Unresolved as exc:
                            status = str(exc)
                            window = calendar[entry_pos:entry_pos + horizon + 1]
                            missing_security = [d for d in window if d <= quote_end and d not in source.good_days]
                            benchmark = spy if phase == "after" else baseline["SPY"]
                            missing_benchmark = [d for d in window if d not in benchmark.good_days]
                counts[phase][status] += 1
                annual[day[:4]][phase][status] += 1
                private_labels.append({"horizon": horizon, "signal": day, "ticker": ticker, "entry": entry,
                                       "end": end, "phase": phase, "status": status,
                                       "gross_usd_total_return": value if status == "COMPLETE_ORIGINAL_RESEARCH_CONTRACT" else None,
                                       "spy_gross_usd_total_return": benchmark_value if status == "COMPLETE_ORIGINAL_RESEARCH_CONTRACT" else None,
                                       "difference_vs_spy": value - benchmark_value if status == "COMPLETE_ORIGINAL_RESEARCH_CONTRACT" else None})
                private_labels[-1].update(missing_security_sessions=missing_security, missing_benchmark_sessions=missing_benchmark)
        transitions = Counter()
        per_pair = defaultdict(dict)
        for row in private_labels:
            if row["horizon"] == horizon:
                per_pair[row["signal"], row["ticker"]][row["phase"]] = row["status"]
        for states in per_pair.values():
            before = states["before"] == "COMPLETE_ORIGINAL_RESEARCH_CONTRACT"
            after = states["after"] == "COMPLETE_ORIGINAL_RESEARCH_CONTRACT"
            transitions["already_complete_and_retained" if before and after else "newly_complete" if after else "previously_complete_withdrawn" if before else "still_unresolved_or_ineligible"] += 1
        horizon_counts[str(horizon)] = {"fixed_union_denominator": len(cohort), "before": dict(counts["before"]), "after": dict(counts["after"]), "transitions": dict(transitions),
                                         "annual": {y: {k: dict(v) for k, v in values.items()} for y, values in annual.items()}}
    write_private(private / "holding-returns.json.gz", private_labels)
    # The 212 inventory is independent of the label denominator and includes all
    # original source failures, not only names for which a fetch happened to work.
    existing_rows, baseline_dates = read(private / "baseline_reacquisition.json"), defaultdict(set)
    existing_plan = read(ROOT / "docs/us-readiness/us-departed-public-price-recovery-v1.json")
    allowed = {(s["source"], r["auditIdentifier"]) for r in existing_plan["inventory"]
               for s in r["candidateSources"] if s["countedInQualifiedCoverage"]}
    quote_reconciliation = []
    for r in existing_rows:
        if r.get("status") == 200 and r.get("matches_existing_bytes") and (r["source"], r["ticker"]) in allowed:
            parsed, _ = parse_csv((private / r["object"]).read_bytes(), calendar_set)
            baseline_dates[r["ticker"]].update(parsed)
            if r["source"] in {"D", "F"} and r["ticker"] in source_frames:
                frame = source_frames[r["ticker"]]
                common = [d for d in sorted(parsed) if pd.Timestamp(d) in frame.index and positive(frame.at[d, "Close"])]
                differences = [abs(float(frame.at[d, "Close"]) - parsed[d]["close"]) for d in common]
                quote_reconciliation.append({"ticker": r["ticker"], "old_source": r["source"], "old_sha256": r["sha256"],
                    "common_close_observations": len(common), "absolute_close_tolerance_usd": .011,
                    "close_observations_outside_rounding_tolerance": sum(v > .011 for v in differences),
                    "maximum_absolute_close_difference_usd": max(differences) if differences else None,
                    "restriction": "Price cross-check only; same-vendor mirror is not independent security identification"})
    events = {r["audit_identifier"]: r for r in supplied}
    for ticker, event in {"BLL": ("SAME_COMMON_STOCK_RENAME", "2022-05-10", "BLL_EFFECTIVE"),
                          "CTL": ("SAME_COMMON_STOCK_RENAME", "2020-09-18", "CTL_EFFECTIVE"),
                          "FB": ("SAME_COMMON_STOCK_RENAME", "2022-06-09", "FB_META"),
                          "VIAC": ("CLASS_B_SYMBOL_CHANGE", "2022-02-17", "VIAC_CLASS_B"),
                          "MRO": ("STOCK_MERGER", "2024-11-22", "MRO_EXCHANGE"),
                          "WBA": ("CASH_MERGER_WITH_DAP_RIGHT", "2025-08-28", "WBA_DAP"),
                          "BTU": ("OLD_COMMON_CANCELLATION", "2017-04-03", "BTU_CANCELLATION"),
                          "CHK": ("OLD_COMMON_CANCELLATION", "2021-02-09", "CHK_CANCELLATION"),
                          "SIVB": ("BANK_RECEIVERSHIP_PARENT_EQUITY_UNRESOLVED", "2023-03-10", "SIVB_RECEIVERSHIP"),
                          "SBNY": ("BANK_RECEIVERSHIP_EQUITY_UNRESOLVED", "2023-03-12", "SBNY_RECEIVERSHIP")}.items():
        kind, day, source = event
        if source in docs:
            events[ticker] = {"event": kind, "event_date": day, "url": docs[source]["url"], "sha256": docs[source]["sha256"]}
    inventory = []
    new_public_events = {"BLL", "CTL", "FB", "VIAC", "MRO", "WBA", "BTU", "CHK", "SIVB", "SBNY", "CELG"}
    for r in requests:
        ticker = r["audit_identifier"]
        first, last = r["requested_window_start_252_session_warmup"], min(r["requested_window_end_252_session_followup"], AS_OF)
        full_requested = {d for d in calendar if first <= d <= last}
        terminal = terminals.get(ticker)
        last_quote_required = terminal.get("last_trading_date", last) if terminal else last
        expected = {d for d in full_requested if d <= last_quote_required}
        observations = set(new_sources[ticker].good_days) if ticker in new_sources else set()
        if ticker in alternate_series:
            observations |= alternate_series[ticker].good_days
        direct = [x for x in chart_records if x.get("audit_identifier") == ticker]
        account = [x for x in latest if x["ticker"] == ticker]
        missing = expected - (observations | baseline_dates[ticker])
        blockers = []
        if ticker not in new_sources:
            blockers.append("DATED_PRICE_SECURITY_AND_SHARE_CLASS_UNVERIFIED")
        if missing:
            blockers.append("PRICE_DATES_MISSING")
        if ticker not in new_sources:
            blockers.append("DIVIDEND_SPLIT_BASIS_OR_LINEAGE_UNVERIFIED")
        cash_fully_attested = terminal and terminal.get("cash") is not None and not terminal.get("cvr") and not terminal.get("shares")
        if events.get(ticker, {}).get("event") not in {"SAME_COMMON_STOCK_RENAME", "CLASS_B_SYMBOL_CHANGE"} and not cash_fully_attested:
            blockers.append("TERMINAL_OR_SUCCESSOR_CONTRACT_NEEDS_WINDOW_REVIEW")
        inventory.append({"audit_identifier": ticker, "security_audit_id": r["security_audit_id"],
                          "requested_from": first, "requested_through": last,
                          "last_old_security_quote_required": last_quote_required,
                          "post_terminal_sessions_requiring_cash_or_successor_instead_of_old_quote": len(full_requested - expected),
                          "requested_followup_after_as_of": r["requested_window_end_252_session_followup"] if r["requested_window_end_252_session_followup"] > AS_OF else None,
                          "old_candidate_sessions_in_request": len(expected & baseline_dates[ticker]),
                          "new_source_sessions_in_request": len(expected & observations),
                          "new_observation_dates_beyond_old_candidates": len(expected & observations - baseline_dates[ticker]),
                          "source_acquired": ticker in new_sources, "source_admission": "AUTHOR_VALIDATED_DEVELOPMENT_CANDIDATE" if ticker in new_sources else "NOT_ADMITTED",
                          "new_public_event_material": ticker in new_public_events,
                          "event": events.get(ticker, {"event": "UNCLASSIFIED_NOT_ASSUMED_DELISTED"}),
                          "missing_candidate_price_sessions": len(missing), "missing_date_ranges": ranges(missing, calendar),
                          "blockers": blockers, "sec_cik_candidates_not_permanent_ids": r["sec_exact_name_cik_candidates"],
                          "provider_attempts": [{k: x.get(k) for k in ("source", "ticker", "status", "rows", "first", "last", "sha256", "url")} for x in direct]
                          + [{k: x.get(k) for k in ("provider", "endpoint", "ticker", "status", "sha256", "url")} for x in account]})
    result = {"schema": "US_HISTORICAL_MARKET_RECOVERY_V1", "as_of": AS_OF,
              "base_main": "be46343031c3ec77a19f79ae102eecf6c3695be7", "read_only_pr336_head": "148993572a625b914bbe6cd79610db7bf618f4b1",
              "original_price_cutoff_unchanged": "2026-09-14", "universe_and_entry_contract": "US_DECISION_PILOT_V1",
              "reused_input_helper_sha256": helper_pins,
              "denominator_grain": "input-eligible security x weekly signal x horizon; next-session close entry, entry_index+H exit",
              "collection_denominator": 212, "new_price_source_packets_validated": len(new_sources),
              "additional_price_or_public_event_identifiers": sum(r["source_acquired"] or r["new_public_event_material"] for r in inventory),
              "additional_price_or_public_event_ids": [r["audit_identifier"] for r in inventory if r["source_acquired"] or r["new_public_event_material"]],
              "baseline_reacquired_files": len(existing_rows), "baseline_bytes_match": all(r.get("matches_existing_bytes") for r in existing_rows),
              "original_input_eligible_records": sum(len(r["tickers"]) for r in original_cohorts["cohorts"]),
              "repaired_input_eligible_records": sum(len(r["tickers"]) for r in repaired["cohorts"]),
              "accounting_issuer_conflict_records": len(issuer_conflicts),
              "horizons": horizon_counts, "spy_official_reconciliation": spy_report,
              "source_receipts": source_receipts, "price_basis_diagnostics": diagnostics,
              "old_new_close_reconciliation": quote_reconciliation,
              "label_followup_scope": "MATURE_LABEL_GAPS_ONLY_NOT_SIGNAL_INPUTS_OR_UNIVERSE_CHANGE",
              "label_followup_downloads": len(followup_records), "label_followup_whole_series_validated": len(label_followups),
              "label_followup_diagnostics": followup_diagnostics,
              "additional_documented_class_price_series": len(alternate_series),
              "older_full_history_followup_refusals": historical_followup_refusals,
              "source_event_counts": dict(Counter(r["event"]["event"] for r in inventory)),
              "formal_dataset_admission": "NOT_GRANTED_INDEPENDENT_REVIEW_AND_RESIDUAL_GAPS_REMAIN",
              "inventory": inventory,
              "limitations": ["Development data reconstruction, not a new alpha test, investment nomination, or actual broker execution",
                              "Original surviving-stock labels retain the original replay-v16 vendor-basis and observed-membership limitations",
                              "The single-issuer guard blocks mismatched accounting rows; it does not establish a permanent traded security ID",
                              "SEC name candidates and current Finnhub profiles are never permanent historical security IDs",
                              "Mixed-consideration fractional settlement and unresolved CVRs/DAP rights are never filled with zero",
                              "Price/action payloads and numerical security-level returns are private; public output is metadata only"]}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_bytes(canonical(result))
    print(json.dumps({k: v for k, v in result.items() if k in ("additional_price_or_public_event_identifiers", "new_price_source_packets_validated", "original_input_eligible_records", "repaired_input_eligible_records", "horizons")}, ensure_ascii=False, indent=2))
    write_private(private / "new-source-series.json.gz", {t: {"source": s.source, "receipt": s.receipt,
                  "tr": {str(d.date()): None if pd.isna(v) else float(v) for d, v in s.tr.items()},
                  "raw_close": {str(d.date()): None if pd.isna(v) else float(v) for d, v in s.raw_close.items()},
                  "good_days": sorted(s.good_days)} for t, s in {**new_sources, **label_followups, "SPY": spy,
                  **{t + "@YAHOO_" + s.ticker: s for t, s in alternate_series.items()}}.items()})


if __name__ == "__main__":
    main()
