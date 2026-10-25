"""Invented statements and paths only. No old study or real outcome execution."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pytest

from . import census as C
from . import design_checks as D
from . import features as F


def filing(year, receivables=20, inventory=30, sales=100):
    receipt = f"{year + 1}0320000001"
    out = {"id": f"SYN-{year}", "ticker": "123456.KS", "stockCode": "123456", "corpCode": "12345678",
           "contract": "DART_RAW_STATEMENT_ROWS_V1", "identityBasis": "EXACT_STOCK_CODE",
           "fiscalYear": year, "reportCode": "11011", "fsDiv": "CFS", "mixedReceipts": False,
           "availableFrom": f"{year + 1}-03-20", "receiptNos": [receipt], "rows": []}
    for field, value in (("receivables", receivables), ("inventory", inventory), ("sales", sales)):
        if value is None:
            continue
        concepts, statement = F.CONCEPTS[field]
        out["rows"].append({"account_id": concepts[0], "sj_div": "IS" if statement == "FLOW" else statement,
                            "account_detail": "-", "currency": "KRW", "thstrm_amount": str(value),
                            "frmtrm_amount": "999999999", "rcept_no": receipt, "corp_code": out["corpCode"],
                            "bsns_year": str(year), "reprt_code": "11011"})
    return out


def signals(current=None, prior=None, stamp="2025-03-21"):
    return F.annual_pair(current or filing(2024), prior or filing(2023), stamp)["signals"]


def test_recovers_two_independent_inputs_not_a_factor_weight_mix():
    out = signals(filing(2024, 10, 15, 100))
    assert out["collection_discipline"]["value"] == pytest.approx(.1)
    assert out["inventory_discipline"]["value"] == pytest.approx(.15)


def test_worsening_working_capital_is_negative():
    out = signals(filing(2024, 40, 60))
    assert out["collection_discipline"]["value"] == pytest.approx(-.2)
    assert out["inventory_discipline"]["value"] == pytest.approx(-.3)


def test_zero_inventory_is_observed_not_missing():
    assert signals(filing(2024, inventory=0))["inventory_discipline"]["value"] == .3


def test_sales_growth_alone_can_explain_signal_and_must_be_a_control():
    assert signals(filing(2024, sales=200))["inventory_discipline"]["value"] == .15


@pytest.mark.parametrize("field", list(F.CONCEPTS))
def test_no_comparative_column_substitution(field):
    current = filing(2024)
    next(r for r in current["rows"] if r["account_id"] == F.CONCEPTS[field][0][0])["thstrm_amount"] = ""
    out = signals(current)
    affected = F.SIGNALS if field == "sales" else (F.SIGNALS[0 if field == "receivables" else 1],)
    assert all(out[s]["value"] is None for s in affected)


@pytest.mark.parametrize("stamp", ["2025-03-19", "2025-03-20"])
def test_same_day_and_future_publication_are_withheld(stamp):
    assert all(x["value"] is None for x in signals(stamp=stamp).values())


@pytest.mark.parametrize("key,value", [("currency", "USD"), ("account_detail", "segmentA"),
                                        ("corp_code", "00000001"), ("rcept_no", "20250321000001"),
                                        ("bsns_year", "2023"), ("reprt_code", "11014"),
                                        ("thstrm_amount", "NaN"), ("thstrm_amount", "1,000"),
                                        ("thstrm_amount", "-1")])
def test_bad_row_context_abstains(key, value):
    current = filing(2024)
    current["rows"][0][key] = value
    assert signals(current)["collection_discipline"]["value"] is None


@pytest.mark.parametrize("key,value", [("mixedReceipts", True), ("fsDiv", "UNKNOWN"),
                                        ("corpCode", "00000001"), ("reportCode", "11014"),
                                        ("identityBasis", "CURRENT_TICKER_GUESS"),
                                        ("availableFrom", "2025-02-30"), ("receiptNos", []),
                                        ("receiptNos", [20250320000001]), ("receiptNos", None)])
def test_bad_filing_context_blocks_both(key, value):
    current = filing(2024)
    current[key] = value
    assert all(x["value"] is None for x in signals(current).values())


def test_one_missing_field_preserves_other_signal_and_multi_reason_counts():
    out = signals(filing(2024, receivables=None))
    assert out["collection_discipline"]["value"] is None
    assert out["inventory_discipline"]["value"] == 0
    out = signals(filing(2024, None, None, None))
    assert len(out["collection_discipline"]["reasons"]) == 2


def test_combined_trade_other_receivables_cannot_replace_pure_trade():
    current = filing(2024)
    current["rows"][0]["account_id"] = "ifrs-full_TradeAndOtherCurrentReceivables"
    assert signals(current)["collection_discipline"]["value"] is None


def test_duplicate_concepts_even_agreeing_values_are_ambiguous():
    current = filing(2024)
    current["rows"].append(deepcopy(current["rows"][0]))
    assert signals(current)["collection_discipline"]["value"] is None


def test_taxonomy_migration_is_not_silently_equated():
    prior = filing(2023)
    prior["rows"][1]["account_id"] = "ifrs_Inventories"
    out = signals(prior=prior)
    assert out["inventory_discipline"]["value"] is None
    assert "CONCEPT_BASIS_CHANGED:inventory" in out["inventory_discipline"]["reasons"]


def test_prior_filing_and_same_basis_are_required():
    assert all(x["value"] is None for x in signals(prior=filing(2022)).values())
    prior = filing(2023)
    prior["fsDiv"] = "OFS"
    assert all(x["value"] is None for x in signals(prior=prior).values())


def test_latest_fiscal_year_not_latest_receipt_and_no_future_poisoning():
    records = [filing(2023), filing(2024), filing(2025)]
    old = filing(2021)
    old["availableFrom"] = "2025-03-19"
    out = F.visible_pair(records + [old], "123456.KS", "2025-03-21")
    assert out["fiscalYear"] == 2024
    assert out["signals"]["inventory_discipline"]["value"] == 0
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        F.visible_pair(records + [deepcopy(records[1])], "123456.KS", "2025-03-21")


def test_stale_fiscal_report_is_not_refreshed_by_a_new_receipt():
    old = filing(2021)
    old["availableFrom"] = "2025-03-19"
    with pytest.raises(ValueError, match="STALE_FISCAL"):
        F.visible_pair([filing(2020), old], "123456.KS", "2025-03-21")


@pytest.mark.parametrize("path", ["ledger/historical/replay-v16/2020.jsonl.gz", "ledger/prices/us/foo.json.gz",
                                   "../raw-2020.jsonl.gz", "ledger/fundamentals/kr-raw/raw-2020.jsonl.gz/../outcomes"])
def test_census_refuses_non_accounting_access_before_git(tmp_path, path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must not invoke git")
    monkeypatch.setattr(C.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="REFUSED"):
        C.AccountingSources(tmp_path).rows(path)


def test_census_default_opens_no_data(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("must not read")
    monkeypatch.setattr(C.AccountingSources, "rows", forbidden)
    C.main([])
    assert json.loads(capsys.readouterr().out)["mode"] == "PLAN_ONLY"


def calendar():
    # Invented exchange sessions; public holidays intentionally excluded.
    start = date(2017, 1, 2)
    return [(start + timedelta(days=i)).isoformat() for i in range(2200)
            if (start + timedelta(days=i)).weekday() < 5 and (start + timedelta(days=i)).isoformat() != "2017-01-30"]


def cohort(n=3):
    days = calendar()
    members = [{"security": f"SYN-{i}", "industry": "SYN-IND", "sizeBucket": "MID"} for i in range(n)]
    receipt = D.freeze_cohort(members, days[0], days)
    return days, receipt


def observations(n=3):
    return [{"domain": "SYNTHETIC_ONLY", "security": f"SYN-{i}", "targetNetExcess": .1,
             "baselinePrediction": .02, "augmentedPrediction": .05, "reasons": []} for i in range(n)]


def test_paired_comparison_and_json_receipt_roundtrip():
    days, receipt = cohort()
    receipt = json.loads(json.dumps(receipt))
    r = D.paired_rehearsal(observations(), receipt, receipt["sha256"], days, days[300], 126, 3)
    assert r["status"] == "SYNTHETIC_COMPLETE"
    assert r["mseImprovement"] > 0


@pytest.mark.parametrize("mutation", ["remove", "industry", "size", "signal", "calendar"])
def test_prelabel_cohort_digest_is_pinned(mutation):
    days, receipt = cohort()
    expected = receipt["sha256"]
    if mutation == "remove":
        receipt["members"].pop()
    elif mutation == "signal":
        receipt["signal"] = days[1]
    elif mutation == "calendar":
        days.pop(5)
    else:
        receipt["members"][0]["industry" if mutation == "industry" else "sizeBucket"] = "CHANGED"
    receipt["sha256"] = F.digest({k: v for k, v in receipt.items() if k != "sha256"})
    with pytest.raises(ValueError):
        D.paired_rehearsal(observations(), receipt, expected, days, days[300], 126, 3)


def test_two_of_104_valid_observations_never_supports_comparison():
    days, receipt = cohort(104)
    rows = observations(104)
    for row in rows[2:]:
        row["targetNetExcess"] = None
    r = D.paired_rehearsal(rows, receipt, receipt["sha256"], days, days[300], 126, 30)
    assert r["status"] == "BLOCKED" and r["pairs"] == 2
    assert r["mseImprovement"] is None


def test_all_missing_reasons_and_terminal_names_are_preserved():
    days, receipt = cohort()
    rows = observations()
    rows[0].update(targetNetExcess=None, baselinePrediction=None, augmentedPrediction=None,
                   reasons=["TERMINAL_UNRESOLVED", "TRADING_HALT"])
    r = D.paired_rehearsal(rows, receipt, receipt["sha256"], days, days[300], 126, 2)
    assert len(r["missingByReason"]) == 5 and r["intended"] == 3 and r["status"] == "BLOCKED"
    with pytest.raises(ValueError, match="INTENDED_MEMBER"):
        D.paired_rehearsal(rows[1:], receipt, receipt["sha256"], days, days[300], 126, 2)


@pytest.mark.parametrize("horizon", [126, 252])
def test_maturity_is_computed_from_frozen_sessions(horizon):
    days, receipt = cohort()
    r = D.paired_rehearsal(observations(), receipt, receipt["sha256"], days, days[horizon], horizon, 3)
    assert r["status"] == "NOT_MATURED"
    r = D.paired_rehearsal(observations(), receipt, receipt["sha256"], days, days[horizon + 1], horizon, 3)
    assert r["status"] == "SYNTHETIC_COMPLETE"


def test_purge_uses_label_end_not_signal_date():
    days = calendar()
    rows = [{"domain": "SYNTHETIC_ONLY", "security": "SYN-A", "signal": days[0], "labelEnd": days[100]},
            {"domain": "SYNTHETIC_ONLY", "security": "SYN-B", "signal": days[1], "labelEnd": days[179]}]
    assert D.purged_training(rows, days[200], days) == rows[:1]


def test_ridge_forecast_cannot_see_later_labels_or_evaluation_targets():
    days = calendar()
    train = [{"domain": "SYNTHETIC_ONLY", "security": f"SYN-{i}", "signal": days[i],
              "labelEnd": days[i + 126], "baseline": [i / 100, None if i == 0 else i / 200],
              "newSignal": (i % 3) / 10, "targetNetExcess": i / 200} for i in range(40)]
    evaluation = [{"domain": "SYNTHETIC_ONLY", "security": "SYN-EVAL", "signal": days[200],
                   "baseline": [None, .15], "newSignal": .1, "targetNetExcess": .1}]
    first = D.ridge_rehearsal(train, evaluation, days[200], days)
    evaluation[0]["targetNetExcess"] = -100
    late = deepcopy(train[0])
    late.update(security="SYN-LATE", labelEnd=days[180], targetNetExcess=999)
    assert D.ridge_rehearsal(train + [late], evaluation, days[200], days) == first
    with pytest.raises(ValueError, match="INSUFFICIENT_PURGED"):
        D.ridge_rehearsal(train[:2], evaluation, days[200], days)
    with pytest.raises(ValueError, match="DUPLICATE_DATED"):
        D.ridge_rehearsal(train + [train[0]], evaluation, days[200], days)


def test_sensitivities_are_pinned_to_signal_metadata_not_future_returns():
    members = [{"security": f"SYN-{i}", "industry": "CHIPS" if i == 2 else "OTHER", "marketCap": i + 1}
               for i in range(6)]
    r = D.sensitivity_members(members, "2025-02-01", {"CHIPS"})
    assert r["EXCLUDE_2025_2026"] == []
    assert r["EXCLUDE_SIGNAL_TOP2"] == [f"SYN-{i}" for i in range(4)]
    assert "SYN-2" not in r["EXCLUDE_FIXED_INDUSTRIES"]
    members[0]["marketCap"] = None
    with pytest.raises(ValueError, match="METADATA_UNRESOLVED"):
        D.sensitivity_members(members, "2024-02-01", {"CHIPS"})


def path(horizon=126):
    days = calendar()
    return days, [{"date": d, "entryOpen": 100., "wealth": 110., "tradable": True,
                   "economics": "SYNTHETIC_VERIFIED_SHAREHOLDER_WEALTH"} for d in days[1:horizon + 1]]


def test_economics_next_open_costs_and_no_dividend_double_counting():
    days, rows = path()
    r = D.holder_return(rows, days, days[0], 126, 11.5, 31.5, "SYNTHETIC_ONLY")
    assert r == pytest.approx(110 * (1 - .00315) / (100 * 1.00115) - 1)
    # A 2:1 split leaves total holder wealth unchanged; entry cost is not halved.
    split = deepcopy(rows)
    split[-1].update(rawClose=55, deliveredShares=2)
    assert D.holder_return(split, days, days[0], 126, 11.5, 31.5, "SYNTHETIC_ONLY") == r


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "rights", "negative", "exit_halt", "entry_halt", "index_only"])
def test_economic_path_abstains_instead_of_filling(mutation):
    days, rows = path()
    if mutation == "missing":
        rows.pop(60)
    elif mutation == "duplicate":
        rows[60] = deepcopy(rows[59])
    elif mutation == "rights":
        rows[60]["economics"] = "DEMERGER_UNRESOLVED"
    elif mutation == "negative":
        rows[60]["wealth"] = -1
    elif mutation == "index_only":
        rows[60]["economics"] = "PARTIAL_DISTRIBUTIONS_ADJUSTED_INDEX"
    else:
        rows[-1 if mutation == "exit_halt" else 0]["tradable"] = False
    with pytest.raises(ValueError):
        D.holder_return(rows, days, days[0], 126, 10, 30, "SYNTHETIC_ONLY")


def test_verified_halt_marks_may_be_held_without_inventing_trade():
    days, rows = path()
    rows[50]["tradable"] = False
    assert D.holder_return(rows, days, days[0], 126, 0, 0, "SYNTHETIC_ONLY") == pytest.approx(.1)


@pytest.mark.parametrize("stamp,bps", [("2019-06-02", 30), ("2019-06-03", 25), ("2025-01-01", 15), ("2026-01-01", 20)])
def test_tax_schedule_in_new_proposal_is_dated(stamp, bps):
    assert D.kr_sell_tax_bps(stamp) == bps


def test_minimum_sample_is_per_comparison_not_overall_cohorts():
    blocks = [{"block": str(i), "delta": .1 if i < 2 else None} for i in range(104)]
    r = D.synthetic_uncertainty(blocks, 10, 4, "SYNTHETIC_ONLY")
    assert r["validBlocks"] == 2 and r["ci95"] is None and not r["promotionEligible"]


def test_missing_blocks_cannot_be_stitched_to_positive_result():
    blocks = [{"block": str(i), "delta": .1 + .01 * i} for i in range(12)] + [{"block": "missing", "delta": None}]
    assert D.synthetic_uncertainty(blocks, 10, 4, "SYNTHETIC_ONLY")["status"] == "BLOCKED_INCOMPLETE_BLOCKS"


def test_synthetic_intervals_mde_and_family_correction():
    blocks = [{"block": str(i), "delta": .01 * (i - 7)} for i in range(12)]
    r = D.synthetic_uncertainty(blocks, 10, 4, "SYNTHETIC_ONLY")
    assert r["ci95"][0] < r["mean"] < r["ci95"][1] and r["mde80NormalApprox"] > 0
    assert not r["promotionEligible"]
    assert D.holm([.01, .02, .5, .9]) == pytest.approx([.04, .06, 1., 1.])


def test_every_real_execution_entry_is_absent_or_rejected():
    with pytest.raises(ValueError, match="NOT_IMPLEMENTED_OR_AUTHORIZED"):
        D.synthetic_uncertainty([], 10, 4, "HISTORICAL")
    with pytest.raises(ValueError, match="NOT_IMPLEMENTED_OR_AUTHORIZED"):
        D.purged_training([{"domain": "HISTORICAL", "security": "005930.KS"}], "2020-01-01", calendar())
    days, rows = path()
    with pytest.raises(ValueError, match="NOT_IMPLEMENTED_OR_AUTHORIZED"):
        D.holder_return(rows, days, days[0], 126, 10, 30, "LIVE")


def test_original_kr_artifact_bytes_and_c1_dependency_remain_unchanged():
    root = Path(__file__).resolve().parents[2]
    original = root / "research/historical_alpha_discovery_v1"
    manifest = json.loads((original / "results/manifest.json").read_text())
    assert len(manifest["filesSha256"]) == 50
    for name, expected in manifest["filesSha256"].items():
        assert hashlib.sha256((original / name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256((root / "pipeline/winner_inflection_execution.py").read_bytes()).hexdigest() == (
        "efbc6f7f61f83c4e8d4f2543bdf7ead42970e44ce140a64f2842f9e547e78b7d")


def test_new_study_has_no_execution_permission_or_production_promotion():
    proposal = json.loads((Path(__file__).parent / "proposal.json").read_text())
    assert proposal["studyId"] == "stock-working-capital-v1"
    assert not proposal["historicalExecutionEnabled"] and not proposal["promotionEligible"]
    assert len(proposal["hypotheses"]) == 2 and not proposal["productionChanges"]
