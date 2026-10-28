"""Invented evidence/packages only; no historical label access or old study run."""
from copy import deepcopy
from datetime import date, timedelta
import io
import json
from pathlib import Path
import zipfile

import pytest

from . import features as F
from . import pit_admission as A
from . import pit_filing_evidence as E
from . import pit_join as J
from . import age_policy as AP
from .test_study import filing


def sessions():
    start = date(2023, 1, 1)
    return [(start + timedelta(days=i)).isoformat() for i in range(1200)
            if (start + timedelta(days=i)).weekday() < 5
            and (start + timedelta(days=i)).isoformat() != "2025-03-28"]


def target(year):
    r = filing(year)
    receipt = r["receiptNos"][0]
    return {**{k: r[k] for k in ("ticker", "corpCode", "fiscalYear", "identityBasis", "availableFrom", "receiptNos")},
            "originalStatus": "EARLIEST_NON_CORRECTION_ANNUAL_LIST_ROW", "reportPeriod": f"{year}-12",
            "listingMetadata": {"rcept_no": receipt, "rcept_dt": receipt[:8], "stock_code": "123456",
                                "corp_code": "12345678", "corp_name": "테스트기업", "report_nm": f"사업보고서 ({year}.12)"}}


def main_body(t):
    r = t["receiptNos"][0]
    return (f'<title>테스트기업/사업보고서/{r[:4]}.{r[4:6]}.{r[6:8]}</title>'
            f'<script>node1["rcpNo"] = "{r}";</script>').encode()


def meta(year):
    t = target(year)
    return E.original_main(t, main_body(t), "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + t["receiptNos"][0])


def package(record, *, start=None, end=None, currency="KRW", corp=None, member="ConsolidatedMember",
            unit_uri=E.ISO, unit_prefix="iso", extra="", value_delta=0):
    year = record["fiscalYear"]
    end, start = end or f"{year}-12-31", start or f"{year}-01-01"
    entity = (f'<xbrli:entity><xbrli:identifier scheme="http://dart.fss.or.kr/corpCode">'
              f'{corp or record["corpCode"]}</xbrli:identifier><xbrli:segment>'
              f'<xbrldi:explicitMember dimension="ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis">'
              f'ifrs-full:{member}</xbrldi:explicitMember></xbrli:segment></xbrli:entity>')
    contexts = (f'<xbrli:context id="F">{entity}<xbrli:period><xbrli:startDate>{start}</xbrli:startDate>'
                f'<xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>'
                f'<xbrli:context id="B">{entity}<xbrli:period><xbrli:instant>{end}</xbrli:instant>'
                f'</xbrli:period></xbrli:context>')
    facts = ""
    for field in ("sales", "inventory", "receivables"):
        r = F.matching_rows(record, field)[0]
        prefix, local = r["account_id"].split("_", 1)
        ctx = "F" if field == "sales" else "B"
        value = int(r["thstrm_amount"]) + value_delta
        facts += f'<{prefix}:{local} contextRef="{ctx}" unitRef="U" decimals="0">{value}</{prefix}:{local}>'
    xml = (f'<xbrli:xbrl xmlns:xbrli="{E.XI}" xmlns:xbrldi="{E.XD}" '
           'xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2024-03-27/ifrs-full" '
           'xmlns:dart="http://dart.fss.or.kr/taxonomy/2024/dart" '
           f'xmlns:{unit_prefix}="{unit_uri}">{contexts}<xbrli:unit id="U">'
           f'<xbrli:measure>{unit_prefix}:{currency}</xbrli:measure></xbrli:unit>{facts}{extra}</xbrli:xbrl>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        # A synthetic original's digest must not depend on a two-second ZIP
        # wall-clock boundary between the paired termination-control builds.
        info = zipfile.ZipInfo("instance.xbrl", date_time=(2024, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, xml)
    raw = b.getvalue()
    receipt = record["receiptNos"][0]
    return {"raw": raw, "sha256": E.sha(raw),
            "url": f"https://opendart.fss.or.kr/api/fnlttXbrl.xml?rcept_no={receipt}&reprt_code=11011"}


def universe(stamp="2025-03-04"):
    return [{"date": stamp, "ticker": ticker, "name": name, "rank": i + 1}
            for i, (ticker, name) in enumerate([("123456.KS", "테스트기업"), ("234567.KS", "없는공시"), ("345678.KS", "종결기업")])]


def worker(*, real_packages=True, terminal=None, records=None, originals=None, bars=None):
    records = records if records is not None else [filing(2023), filing(2024, inventory=15)]
    originals = originals if originals is not None else {(m["ticker"], m["fiscalYear"], m["receipt"]): [m] for m in (meta(2023), meta(2024))}
    packs = {r["receiptNos"][0]: package(r) for r in records} if real_packages else {}
    event = {"ticker": "123456.KS", "notice_date": "2023-01-02", "effective_date": "2023-01-03",
             "after_label": "실험산업", "document_sha256": "a" * 64, "issuerCorpCode": "12345678",
             "issuerBridgeSourceSha256": "b" * 64, "issuerBridgeAvailableFrom": "2022-03-20"}
    if bars is None:
        bars = {("2025-03-21", r["ticker"]): "OBSERVED_TRADABLE_SIGNAL_BAR" for r in universe()}
    return A.Crosswalk(snapshots=A.TopSnapshots(universe(), sessions(), expected=3), filings=records,
                       originals=originals, intervals={}, events={"123456.KS": [event]},
                       crosswalk={"mapping": {"실험산업": "SYN_INDUSTRY"}}, terminal=terminal or {},
                       trading=bars, sessions=sessions(), packages=packs, fiscal_age_policy=AP.synthetic_policy())


def test_monthly_asof_membership_is_not_called_exact_daily_ranking():
    index = A.TopSnapshots(universe() + universe("2025-04-01"), sessions(), expected=3)
    c = index.on("2025-03-21")
    assert c["snapshotDate"] == "2025-03-04" and c["snapshotAgeDays"] == 17
    assert c["basis"] == "LAST_KNOWN_MONTHLY_TOP120_NOT_DAILY_RANK"
    assert c["expectedCount"] == 3 and len(c["members"]) == 3


def test_no_prior_snapshot_never_uses_future_membership():
    c = A.TopSnapshots(universe(), sessions(), expected=3).on("2025-02-28")
    assert c["members"] == [] and c["expectedCount"] == 3 and len(c["missingRankSlots"]) == 3
    assert c["reasons"] == ["NO_PRIOR_SNAPSHOT"]


def test_stale_snapshot_keeps_names_but_blocks_admission():
    c = A.TopSnapshots(universe(), sessions(), expected=3).on("2025-04-04")
    assert len(c["members"]) == 3 and "STALE_MONTHLY_SNAPSHOT" in c["reasons"]


def test_missing_rank_never_promotes_rank_121_or_discards_denominator():
    rows = universe()
    rows[1]["rank"] = 4
    c = A.TopSnapshots(rows, sessions(), expected=3).on("2025-03-21")
    assert len(c["members"]) == 2 and c["expectedCount"] == 3 and c["missingRankSlots"] == [2]
    assert "INCOMPLETE_TOP120_SNAPSHOT" in c["reasons"]


def test_alphanumeric_krx_security_is_retained_without_numeric_identity_guess():
    rows = universe()
    rows[1]["ticker"] = "00680K.KS"
    c = A.TopSnapshots(rows, sessions(), expected=3).on("2025-03-21")
    assert "00680K.KS" in {m["ticker"] for m in c["members"]}


@pytest.mark.parametrize("mutation", ["duplicate_name", "duplicate_rank", "closed_source", "closed_signal"])
def test_bad_membership_or_closed_session_does_not_succeed(mutation):
    rows = universe()
    if mutation == "duplicate_name":
        rows[1]["ticker"] = rows[0]["ticker"]
    elif mutation == "duplicate_rank":
        rows[1]["rank"] = 1
    elif mutation == "closed_source":
        rows[0]["date"] = "2025-03-22"
    with pytest.raises(ValueError):
        index = A.TopSnapshots(rows, sessions(), expected=3)
        index.on("2025-03-22" if mutation == "closed_signal" else "2025-03-21")


def test_holiday_friday_skipped_without_backdating_or_filling_thursday():
    assert A.first_friday_after("2025-03-21", sessions()) == "2025-04-04"


def test_metadata_binds_original_receipt_identity_and_report_end_month_only():
    m = meta(2024)
    assert m["periodEndMonth"] == "2024-12" and m["receipt"] == filing(2024)["receiptNos"][0]
    assert not m["originalFinancialValuesVerified"] and not m["fiscalStartVerified"]


@pytest.mark.parametrize("kind", ["amendment", "stock", "corp", "date", "period", "receipt_node", "title"])
def test_original_metadata_rejects_wrong_vintage_identity_or_period(kind):
    t = target(2024)
    body = main_body(t)
    if kind == "amendment":
        t["listingMetadata"]["report_nm"] = "[기재정정]사업보고서 (2024.12)"
    elif kind == "stock":
        t["listingMetadata"]["stock_code"] = "999999"
    elif kind == "corp":
        t["listingMetadata"]["corp_code"] = "99999999"
    elif kind == "date":
        t["availableFrom"] = "2025-03-19"
    elif kind == "period":
        t["reportPeriod"] = "2023-12"
    elif kind == "receipt_node":
        body = body.replace(b'node1["rcpNo"]', b'bad["rcpNo"]')
    else:
        body = body.replace("테스트기업".encode(), "다른기업".encode())
    with pytest.raises(ValueError):
        E.original_main(t, body, "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + t["receiptNos"][0])


def test_original_package_verifies_amounts_fiscal_duration_and_basis():
    r = filing(2024)
    result = E.original_financial_facts(r, meta(2024), package(r), "inventory")
    assert result["ready"] and result["start"] == "2024-01-01" and result["end"] == "2024-12-31"


@pytest.mark.parametrize("kwargs", [{"currency": "USD"}, {"unit_uri": "https://evil.invalid/iso4217"},
                                  {"corp": "87654321"}, {"member": "SeparateMember"},
                                  {"start": "2023-07-01"}, {"end": "2024-12-30"},
                                  {"value_delta": 1}, {"extra": '<ifrs-full:Inventories contextRef="B" unitRef="U" decimals="0">30</ifrs-full:Inventories>'}])
def test_original_package_negative_controls(kwargs):
    r = filing(2024)
    with pytest.raises(ValueError):
        E.original_financial_facts(r, meta(2024), package(r, **kwargs), "inventory")


@pytest.mark.parametrize("kind", ["digest", "receipt", "untrusted_host"])
def test_original_package_identity_and_sha_are_required(kind):
    r = filing(2024)
    p = package(r)
    if kind == "digest":
        p["sha256"] = "0" * 64
    elif kind == "receipt":
        p["url"] = p["url"].replace("20250320", "20250321")
    else:
        p["url"] = p["url"].replace("opendart.fss.or.kr", "evil.invalid")
    with pytest.raises(ValueError):
        E.original_financial_facts(r, meta(2024), p, "inventory")


def test_missing_original_values_keep_readability_but_never_emit_admitted_signal():
    c, rows = worker(real_packages=False).on("2025-03-21")
    r = rows[0]
    assert r["originalMainPairMatched"] and r["datedIdentityMatched"]
    assert r["signals"]["inventory_discipline"]["inputReadable"]
    assert not r["signals"]["inventory_discipline"]["inputAdmitted"]
    assert r["signals"]["inventory_discipline"]["value"] is None
    assert "CURRENT:ORIGINAL_VALUE_VINTAGE_UNVERIFIED" in r["signals"]["inventory_discipline"]["reasons"]
    assert "CURRENT:FISCAL_DURATION_UNPROVEN" in r["signals"]["inventory_discipline"]["reasons"]
    report = A.coverage([c], rows)
    assert report["expectedMemberDates"] == report["retainedMemberDates"] == 3


def test_normal_fully_evidenced_synthetic_join_preserves_missing_names():
    c, rows = worker().on("2025-03-21")
    assert len(rows) == 3 and rows[0]["eventDue"]
    assert rows[0]["signals"]["inventory_discipline"]["inputAdmitted"]
    assert rows[0]["signals"]["inventory_discipline"]["value"] == .15
    assert rows[1]["signals"]["inventory_discipline"]["value"] is None
    report = A.coverage([c], rows)
    assert report["signals"]["inventory_discipline"]["inputAdmitted"] == 1
    assert report["signals"]["inventory_discipline"]["inputReadableCoverage"] == 1 / 3


def test_original_annual_fiscal_gap_is_not_treated_as_full_observation_window():
    w = worker()
    r = filing(2023)
    t = target(2023)
    t["reportPeriod"] = "2023-11"
    t["listingMetadata"]["report_nm"] = "사업보고서 (2023.11)"
    m = E.original_main(t, main_body(t), "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + t["receiptNos"][0])
    w.originals[(m["ticker"], m["fiscalYear"], m["receipt"])] = [m]
    w.packages[r["receiptNos"][0]] = package(r, start="2022-12-01", end="2023-11-30")
    _, rows = w.on("2025-03-21")
    assert "FISCAL_WINDOWS_NOT_ADJACENT" in rows[0]["signals"]["inventory_discipline"]["reasons"]


def test_eventual_termination_never_removes_or_blocks_a_pretermination_signal():
    _, control = worker().on("2025-03-21")
    c, rows = worker(terminal={"123456.KS": "2025-03-21", "345678.KS": "2025-03-20"}).on("2025-03-21")
    assert len(rows) == 3 and rows[0]["knownTerminalExPostAuditOnly"] and not rows[0]["endedBySignal"]
    assert rows[0]["signals"] == control[0]["signals"]
    assert rows[2]["endedBySignal"]
    assert "IDENTITY_ENDED_BY_SIGNAL" in rows[2]["signals"]["inventory_discipline"]["reasons"]
    assert A.coverage([c], rows)["knownTerminalMemberDatesAuditOnly"] == 2


def test_same_security_on_different_dates_is_retained_and_keyed_by_date():
    w = worker(real_packages=False)
    c1, r1 = w.on("2025-03-21")
    c2, r2 = w.on("2025-04-04")
    assert A.coverage([c1, c2], r1 + r2)["retainedMemberDates"] == 6
    assert c1["intendedSha256"] != c2["intendedSha256"]
    with pytest.raises(ValueError, match="DUPLICATE_SIGNAL_SECURITY"):
        A.coverage([c1], r1 + [r1[0]])
    with pytest.raises(ValueError, match="LOST_OR_ADDED"):
        A.coverage([c1], r1[:-1])


def test_halt_missing_bar_name_change_and_all_reasons_are_preserved():
    w = worker(bars={})
    w.snapshots.by_date["2025-03-04"][0]["name"] = "변경된회사"
    c, rows = w.on("2025-03-21")
    reasons = rows[0]["signals"]["inventory_discipline"]["reasons"]
    assert "MISSING_SIGNAL_SESSION_BAR" in reasons and "SIGNAL_NAME_OR_DATED_NAME_CHANGE_UNRESOLVED" in reasons
    report = A.coverage([c], rows)
    assert report["tradingStatusCounts"]["MISSING_SIGNAL_SESSION_BAR"] == 3
    w = worker(bars={("2025-03-21", "123456.KS"): "ZERO_VOLUME_NONTRADABLE_SIGNAL_BAR"})
    assert not w.on("2025-03-21")[1][0]["signals"]["inventory_discipline"]["inputAdmitted"]


def test_no_same_day_or_future_filings_and_no_previous_year_skip():
    w = worker(records=[filing(2023), filing(2024)], real_packages=False)
    _, rows = w.on("2025-03-20")
    assert rows[0]["currentFiscalYear"] == 2023
    assert "MISSING_OR_AMBIGUOUS_CONSECUTIVE_PRIOR_ANNUAL" in rows[0]["signals"]["inventory_discipline"]["reasons"]
    current, prior, reasons = A.choose_pair([filing(2021), filing(2024)], "2025-03-21")
    assert current["fiscalYear"] == 2024 and prior is None and reasons


def test_delayed_old_year_and_ambiguous_vintage_cannot_replace_latest_year():
    old = filing(2021)
    old["availableFrom"] = "2025-03-19"
    records = [old, filing(2023), filing(2024)]
    assert A.choose_pair(records, "2025-03-21")[0]["fiscalYear"] == 2024
    assert A.choose_pair(records + [deepcopy(records[-1])], "2025-03-21")[2] == ["AMBIGUOUS_CURRENT_VINTAGE"]


def test_different_original_receipt_is_not_spliced_onto_raw_api_values():
    r = filing(2024)
    m = meta(2024)
    m["receipt"] = "20250319000001"
    originals = {(m["ticker"], m["fiscalYear"], m["receipt"]): [m]}
    evidence, reasons = A.filing_metadata(r, originals, "2025-03-21")
    assert evidence is None and reasons == ["RAW_RECEIPT_DIFFERS_FROM_PRESERVED_ORIGINAL"]


def test_mutually_inconsistent_issuer_legs_never_join_by_ticker_alone():
    r = filing(2023)
    r["corpCode"] = "88888888"
    w = worker(real_packages=False, records=[r, filing(2024)])
    _, rows = w.on("2025-03-21")
    assert not rows[0]["datedIdentityMatched"]
    assert "ISSUER_CHANGED" in rows[0]["signals"]["inventory_discipline"]["reasons"]


def test_industry_never_uses_future_event_before_label_or_current_anchor():
    iv = {"123456.KS": [{"start": None, "end": None, "research_industry_id": "CURRENT_ONLY"}]}
    future = {"notice_date": "2026-01-01", "effective_date": "2026-01-02", "before_label": "過去推測",
              "after_label": "未來", "document_sha256": "a" * 64}
    r = A.industry_on("123456.KS", "2025-03-21", iv, {"123456.KS": [future]}, {"mapping": {"過去推測": "BAD"}})
    assert r["group"] is None and r["reconstructedGroup"] == "CURRENT_ONLY"
    assert r["reason"] == "NO_DATED_INDUSTRY_OBSERVATION"


def test_industry_publication_and_effective_dates_both_gate_change():
    e = {"notice_date": "2025-03-20", "effective_date": "2025-04-01", "after_label": "NEW", "document_sha256": "a" * 64}
    kwargs = ("123456.KS",)
    assert A.industry_on(*kwargs, "2025-03-21", {}, {"123456.KS": [e]}, {"mapping": {"NEW": "G"}})["group"] is None
    assert A.industry_on(*kwargs, "2025-04-01", {}, {"123456.KS": [e]}, {"mapping": {"NEW": "G"}})["group"] == "G"


def test_industry_event_issuer_bridge_cannot_use_future_annual_or_current_directory():
    m = meta(2024)  # public March 2025, after this old event
    originals = {(m["ticker"], m["fiscalYear"], m["receipt"]): [m]}
    event = {"ticker": m["ticker"], "notice_date": "2023-01-02", "identity": {"company": m["companyName"]}}
    assert J.bridge_event_issuer(event, originals)["issuerCorpCode"] is None
    event["notice_date"] = "2025-04-01"
    assert J.bridge_event_issuer(event, originals)["issuerCorpCode"] == m["corpCode"]
    event["identity"]["company"] = "다른기업"
    assert J.bridge_event_issuer(event, originals)["issuerCorpCode"] is None


def test_industry_notice_for_a_reused_code_cannot_follow_the_new_issuer():
    w = worker()
    w.events["123456.KS"][0]["issuerCorpCode"] = "99999999"
    _, rows = w.on("2025-03-21")
    r = rows[0]
    assert r["industry"]["group"] == "SYN_INDUSTRY" and not r["industryIssuerMatched"]
    assert "INDUSTRY_EVENT_ISSUER_BRIDGE_UNVERIFIED" in r["signals"]["inventory_discipline"]["reasons"]
    assert not r["signals"]["inventory_discipline"]["inputAdmitted"]


@pytest.mark.parametrize("path", ["ledger/historical/replay-v16/outcomes.jsonl.gz", "docs/results/kr-model-overlay-portfolio-v1-result.json",
                                   "data/site-data.json", "../ledger/universe/kr/krx-universe-2020.jsonl.gz"])
def test_input_reader_refuses_results_and_traversal_before_any_io(tmp_path, monkeypatch, path):
    def forbidden(*args, **kwargs):
        raise AssertionError("no subprocess")
    monkeypatch.setattr(J.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="REFUSED"):
        J.PinnedInputs(tmp_path).blob(J.RAW_COMMIT, path)


def test_missing_source_does_not_trigger_network_fetch_or_become_empty_success(tmp_path, monkeypatch):
    calls = []
    class Failure:
        returncode = 1
    def failure(command, **kwargs):
        calls.append(command)
        assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"
        return Failure()
    monkeypatch.setattr(J.subprocess, "run", failure)
    with pytest.raises(ValueError, match="SOURCE_UNAVAILABLE"):
        J.PinnedInputs(tmp_path).rows("ledger/universe/kr/krx-universe-2020.jsonl.gz")
    assert calls == [["git", "cat-file", "blob", J.RAW_COMMIT + ":ledger/universe/kr/krx-universe-2020.jsonl.gz"]]


def test_default_cli_opens_no_inputs_and_existing_evidence_cannot_be_overwritten(tmp_path, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no data read")
    monkeypatch.setattr(J, "inspect", forbidden)
    assert J.main([]) == 0
    assert json.loads(capsys.readouterr().out)["sourceReads"] == 0
    with pytest.raises(SystemExit):
        J.main(["--inspect", "--output", str(tmp_path)])


def test_source_demand_is_prelabel_worklist_and_does_not_shrink_intended_rows():
    c, rows = worker(real_packages=False).on("2025-03-21")
    demand = J.source_demand([c], rows)
    assert len(rows) == 3 and demand["bySignal"]["inventory_discipline"]["distinctSecurities"] == 1
    assert demand["distinctOriginalReceipts"] == 2
    assert all("rcept_no=" in r["originalPackageUrl"] for r in demand["requests"])
    assert A.coverage([c], rows)["expectedMemberDates"] == 3


def test_infrastructure_error_is_nonzero_and_does_not_write_success(tmp_path, capsys, monkeypatch):
    def unavailable(*args):
        raise ValueError("PINNED_LOCAL_SOURCE_UNAVAILABLE")
    monkeypatch.setattr(J, "inspect", unavailable)
    p = tmp_path / "new"
    assert J.main(["--inspect", "--output", str(p)]) == 4
    assert not p.exists() and json.loads(capsys.readouterr().out)["status"] == "SOURCE_OR_INFRASTRUCTURE_ERROR"


def saved_measurement(directory):
    import gzip
    c, rows = worker(real_packages=False).on("2025-03-21")
    report = {"coverage": A.coverage([c], rows), "historicalReturnLabelsRead": 0,
              "historicalReturnCalculations": 0, "modelFits": 0, "outputSha256": {}}
    for name, records in (("cohorts.jsonl.gz", [c]), ("rows.jsonl.gz", rows)):
        raw = gzip.compress(J.canonical_lines(records), mtime=0)
        (directory / name).write_bytes(raw)
        report["outputSha256"][name] = E.sha(raw)
    (directory / "coverage.json").write_text(json.dumps(report))
    return report, c, rows


def test_persisted_receipts_roundtrip_and_byte_tamper_rejected(tmp_path):
    saved_measurement(tmp_path)
    assert J.verify_measurement(tmp_path)["memberDates"] == 3
    with (tmp_path / "rows.jsonl.gz").open("ab") as f:
        f.write(b"tamper")
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        J.verify_measurement(tmp_path)


@pytest.mark.parametrize("kind", ["rank", "cohort_digest", "blocked_value"])
def test_rehashed_rows_still_require_intended_cohort_and_blocked_value_semantics(tmp_path, kind):
    import gzip
    report, c, rows = saved_measurement(tmp_path)
    if kind == "rank":
        rows[0]["rankAtSnapshot"] = 999
    elif kind == "cohort_digest":
        rows[0]["intendedSha256"] = "0" * 64
    else:
        rows[0]["signals"]["inventory_discipline"]["value"] = .99
    raw = gzip.compress(J.canonical_lines(rows), mtime=0)
    (tmp_path / "rows.jsonl.gz").write_bytes(raw)
    report["outputSha256"]["rows.jsonl.gz"] = E.sha(raw)
    (tmp_path / "coverage.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        J.verify_measurement(tmp_path)


def test_committed_input_receipts_preserve_all_intended_names_and_original_code_hashes():
    directory = Path(__file__).parent / "pit_measurement_v1"
    report = json.loads((directory / "coverage.json").read_text())
    checked = J.verify_measurement(directory)
    assert checked["memberDates"] == 51360
    assert report["coverage"]["expectedMemberDates"] == 428 * 120
    assert report["coverage"]["unidentifiedRankSlots"] == 0
    assert report["coverage"]["knownTerminalMemberDatesAuditOnly"] == 1725
    for name, expected in report["codeSha256"].items():
        # v1 remains an immutable receipt of8df; current revised code receives
        # a NEW v2 receipt, never rewrite v1 or weaken its old hash assertion.
        import os
        import subprocess
        old = subprocess.check_output(["git", "cat-file", "blob", "8df7f7965231e8e18310c821d3d4b7c5c3d8b04a:"
                                       + "research/stock_working_capital_v1/" + name],
                                      cwd=Path(__file__).resolve().parents[2], env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
        assert E.sha(old) == expected
    assert all(r["inputAdmitted"] == 0 for r in report["coverage"]["signals"].values())
