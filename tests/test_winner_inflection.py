"""Invented issuers and outcomes only; no historical label/results access."""
from copy import deepcopy
from dataclasses import replace
import json

import pandas as pd
import pytest

from pipeline import experiment_workbench as W
from pipeline import kr_alpha_atlas_bars as B
from pipeline import prospective_receipt_core as PRC
from pipeline import replay_calendar as RC
from pipeline import winner_inflection as I
from pipeline import winner_inflection_exploration as E
from pipeline.regional_alpha_features import MembershipSnapshots
from scripts import inspect_winner_inflection_sources as A


def filings(market):
    rows = []
    for year in (2017, 2018, 2019):
        for pos, stage in enumerate(I.STAGES[market]):
            end = pd.Timestamp(year=year, month=(pos + 1) * 3, day=1) + pd.offsets.MonthEnd(0)
            public = (end + pd.Timedelta(days=30)).date().isoformat()
            # Cumulative values: NOT individual quarterly flows.
            amounts = {"revenue": (100 + (year - 2017) * 20) * (pos + 1),
                       "operating": (10 + (year - 2017) * 5) * (pos + 1),
                       "ocf": (8 + (year - 2017) * 5) * (pos + 1)}
            row = {"id": f"SYN-{year}-{stage}", "ticker": "SYN", "fiscalYear": year,
                   "availableFrom": public, "periodEnd": str(end.date()), "collectedAt": "2026-10-01T01:00:00Z"}
            if market == "KR":
                row.update(reportCode=stage, fsDiv="CFS", receiptNos=[public.replace("-", "") + "000001"],
                    accounts={I.ACCOUNTS[market][a]: {"statement": "CF" if a == "ocf" else "IS", "amounts": {
                        "thstrm_amount": v if pos == 3 or a == "ocf" else v / (pos + 1), "thstrm_add_amount": v}} for a, v in amounts.items()})
            else:
                row.update(form="10-K" if pos == 3 else "10-Q", periodDays=(90, 181, 273, 365)[pos],
                    acceptedDate=public + " 17:00:00", statements={"bs": [],
                        "ic": [{"concept": c, "unit": "usd", "value": amounts[a]} for a, c in
                               (("revenue", "Revenues"), ("operating", "OperatingIncomeLoss"))],
                        "cf": [{"concept": "NetCashProvidedByUsedInOperatingActivities", "unit": "usd", "value": amounts["ocf"]}]})
            rows.append(row)
    return rows


@pytest.mark.parametrize("market", ["KR", "US"])
def test_ttm_acceleration_is_a_consecutive_state_change_not_four_cumulative_quarters(market):
    records = filings(market)
    snapshot = deepcopy(records)
    state = I.FilingStates(records, market).at("2019-08-02")
    # current revenue TTM = 480-240+280=520; preceding =480-120+140=500.
    # prior revenue TTM =400-200+240=440; preceding =400-100+120=420.
    assert state["fields"]["revenueGrowthAcceleration"] == pytest.approx(520 / 440 - 500 / 420)
    # Operating TTM 70 vs65 and revenue520 vs500.
    assert state["fields"]["operatingMarginChange"] == pytest.approx(70 / 520 - 65 / 500)
    assert all(v is not None for v in state["fields"].values())
    assert records == snapshot


@pytest.mark.parametrize("market", ["KR", "US"])
def test_future_and_same_day_filings_cannot_change_the_past(market):
    records = filings(market)
    before = [r for r in records if r["availableFrom"] < "2019-08-02"]
    future = deepcopy(records[-1])
    future.update(availableFrom="2019-08-02", acceptedDate="2019-08-02 17:00:00", receiptNos=["20190802000001"])
    assert I.FilingStates(before, market).at("2019-08-02") == I.FilingStates(before + [future], market).at("2019-08-02")
    assert I.FilingStates(records, market).at("2019-08-02") == I.FilingStates(before, market).at("2019-08-02")


def test_acceptance_date_and_late_fiscal_year_are_not_calendar_year_proxies():
    records = filings("US")
    records[-3]["acceptedDate"] = "2019-08-03 18:00:00"
    assert I.FilingStates(records, "US").at("2019-08-02")["period"] == [2019, "Q1"]
    records[-3]["acceptedDate"] = "2019-07-30 18:00:00"
    for r in records:
        r["fiscalYear"] += 1
    assert I.FilingStates(records, "US").at("2019-08-02")["period"] == [2020, "Q2"]


def test_empty_balance_sheet_does_not_invent_assets_or_block_flow_patterns():
    records = filings("US")
    a = I.FilingStates(records, "US").at("2019-08-02")
    assert all(v is not None for v in a["fields"].values())
    for r in records:
        r["statements"]["bs"] = [{"concept": "Assets", "unit": "usd", "value": 999}]
    assert a == I.FilingStates(records, "US").at("2019-08-02")


@pytest.mark.parametrize("market", ["KR", "US"])
def test_missing_quarter_stale_report_and_missing_denominator_remain_absent(market):
    records = filings(market)
    records = [r for r in records if not (r["fiscalYear"] == 2019 and r.get("periodEnd") == "2019-03-31")]
    state = I.FilingStates(records, market).at("2019-08-02")
    assert all(v is None for v in state["fields"].values())
    cache = I.FilingStates(filings(market), market)
    assert cache.at("2020-02-01")["fields"]["ocfMarginChange"] is not None
    assert set(cache.at("2021-01-01")["reasons"].values()) == {"REPORT_STALE_OVER_180_DAYS"}


def test_mixed_kr_statement_basis_and_bad_receipt_are_not_repaired():
    records = filings("KR")
    records[-3]["fsDiv"] = "OFS"
    assert set(I.FilingStates(records, "KR").at("2019-08-02")["reasons"].values()) == {"STATEMENT_BASIS_UNRESOLVED"}
    records = filings("KR")
    records[-3]["receiptNos"] = ["20990101000001"]
    assert I.FilingStates(records, "KR").at("2019-08-02")["period"] == [2019, "11013"]


def test_us_pretax_fallback_is_not_called_operating_profit():
    records = filings("US")
    for row in records:
        row["statements"]["ic"][1]["concept"] = I.FD.FLOWS["operatingIncome"][1][-1]
    state = I.FilingStates(records, "US").at("2019-08-02")
    assert state["fields"]["operatingMarginChange"] is None
    assert state["fields"]["ocfMarginChange"] is not None
    assert "OPERATING_SUBTOTAL_NOT_STATED" in state["reasons"]["operatingMarginChange"]


def test_nonpositive_growth_base_does_not_hide_real_profit_cross():
    records = filings("US")
    for r in records:
        if r["fiscalYear"] == 2018:
            r["statements"]["ic"][1]["value"] *= -1
    state = I.FilingStates(records, "US").at("2019-08-02")
    assert state["fields"]["operatingGrowthAcceleration"] is None
    assert state["reasons"]["operatingGrowthAcceleration"] == "NON_POSITIVE_GROWTH_BASE"
    assert state["fields"]["operatingPositiveCross"] in (0.0, 1.0)


def test_leave_self_out_industry_change_and_missing_peer_denominator():
    paths = {"ONE": (1.0, 1.3), **{str(n): (1.0, 1.1) for n in range(5)}}
    groups = dict.fromkeys(paths, "SYN_INDUSTRY")
    assert I.industry_relative_change(paths, groups)["ONE"][0] == pytest.approx(0.2)
    assert I.industry_relative_change({"ONE": (1, 2)}, {"ONE": "SYN"})["ONE"] == (None, "INSUFFICIENT_SAME_DATE_PEERS")
    assert I.industry_relative_change({}, {"ONE": "SYN"})["ONE"][0] is None


def synthetic_panel(market="US"):
    observations, targets = [], []
    source = W.Source("synthetic:invented", "a" * 64, "SYNTHETIC_FIXTURE", "2016-01-01T00:00:00Z", None)
    for n in range(72):
        date = "2017-01-06" if n < 60 else "2020-01-03"
        at = date + ("T09:00:00Z" if market == "KR" else "T22:00:00Z")
        obs = W.Observation(W.Key(market, date, "SYNTHETIC:" + str(n)), "SYN" + str(n), "SYN_ISSUER" + str(n),
            "VERIFIED_SECURITY", at, "PUBLIC_RECONSTRUCTION", source, "2016-01-01T00:00:00Z", True, None, "SYN_GROUP", "DATED",
            (W.Cell("financial.operatingPositiveCross", float(n % 3 == 0), "event", "2016-01-01T00:00:00Z", source),
             W.Cell("financial.ocfMarginChange", float(n % 7) / 10 if n % 4 else None, "ratio", "2016-01-01T00:00:00Z", source,
                    None if n % 4 else "NOT_STATED")))
        days = RC.sessions(date, "2022-01-01", market)
        entry, mature = str(days[1].date()), str(days[127].date())
        ref = W.LabelReference(obs.key.sample_id, market, 126, entry + ("T06:30:00Z" if market == "KR" else "T21:00:00Z"),
            mature + ("T09:00:00Z" if market == "KR" else "T22:00:00Z"),
            mature + ("T09:00:00Z" if market == "KR" else "T22:00:00Z"), "VERIFIED", "NOT_TERMINATED", "synthetic:separate-targets")
        observations.append(obs)
        targets.append(E.SyntheticTarget(ref, (n % 9 - 4) / 20, n % 5 == 0, n % 5 == 1))
    fold = W.Fold("2019-12-31T23:00:00Z", "2020-01-01T00:00:00Z", "2020-02-01T00:00:00Z", "2019-12-01T00:00:00Z", "VALIDATION")
    return observations, targets, fold


@pytest.mark.parametrize("market", ["KR", "US"])
def test_all_models_use_same_purged_samples_and_future_target_poison_has_no_effect(market):
    rows, targets, fold = synthetic_panel(market)
    result = E.compare_synthetic(rows, targets, fold, seed=19)
    poison = [replace(t, excess=1e8, winner=not t.winner, big_loss=False) if n >= 60 else t for n, t in enumerate(targets)]
    assert E.compare_synthetic(rows, poison, fold, seed=19) == result
    assert result["trainingRows"] == 60 and result["modelFits"] == 4
    assert all(len(values) == 12 for values in result["scores"].values())
    assert not result["probabilityCalibrated"]


def test_training_imputation_never_fits_on_evaluation_features():
    rows, targets, fold = synthetic_panel()
    before = E.compare_synthetic(rows, targets, fold, seed=19)
    rows[-1] = replace(rows[-1], cells=(rows[-1].cells[0], replace(rows[-1].cells[1], value=1e12, missing_reason=None)))
    after = E.compare_synthetic(rows, targets, fold, seed=19)
    changed = rows[-1].key.sample_id
    for name in ("ridge", "elastic_net", "logistic_winner", "logistic_big_loss"):
        assert [v for s, v in zip(before["evaluationSampleIds"], before["scores"][name]) if s != changed] == [
            v for s, v in zip(after["evaluationSampleIds"], after["scores"][name]) if s != changed]


def test_real_source_cannot_enter_synthetic_comparator():
    rows, targets, fold = synthetic_panel()
    rows[0] = replace(rows[0], universe_source=replace(rows[0].universe_source, reference="real:ledger"))
    with pytest.raises(ValueError, match="REAL_DATA_LEARNING"):
        E.compare_synthetic(rows, targets, fold, seed=19)


def test_survivors_are_not_the_universe_and_duplicate_aliases_are_rejected():
    rows, targets, fold = synthetic_panel()
    panel = MembershipSnapshots([{"date": "2016-01-01", "members": ["SYN_DEPARTED", "SYN_ALIVE"]},
                                 {"date": "2018-01-01", "members": ["SYN_ALIVE"]}])
    assert "SYN_DEPARTED" in panel.on("2017-01-06")["members"]
    rows[0] = replace(rows[0], investable=False, eligibility_reason="SUSPENDED")
    rows[1] = replace(rows[1], identity_status="UNRESOLVED")
    plan = E.training_plan(rows, [t.reference for t in targets], fold)
    assert len(plan["training"]) == 58 and len(plan["excluded"]) == 2
    with pytest.raises(ValueError, match="DUPLICATE"):
        E.validate_panel([rows[2], replace(rows[2], ticker="OLD_ALIAS")])
    with pytest.raises(ValueError, match="MULTIPLE_IDENTITIES"):
        E.validate_panel([rows[2], replace(rows[3], ticker=rows[2].ticker)])


@pytest.mark.parametrize("reason", ["terminal", "price", "overlap", "deadline", "missing"])
def test_unresolvable_and_unreleased_targets_are_excluded_with_reasons(reason):
    rows, targets, fold = synthetic_panel()
    ref = targets[0].reference
    if reason == "terminal":
        ref = replace(ref, terminal_status="UNRESOLVED")
    elif reason == "price":
        ref = replace(ref, price_basis_status="UNRESOLVED")
    elif reason in {"overlap", "deadline"}:
        at = ref.maturity_at
        fold = replace(fold, evaluation_start=at if reason == "overlap" else fold.evaluation_start,
                       training_cutoff="2017-06-01T00:00:00Z" if reason == "overlap" else fold.training_cutoff,
                       label_deadline="2017-05-01T00:00:00Z" if reason == "overlap" else at)
    refs = [ref, *(t.reference for t in targets[1:])] if reason != "missing" else [t.reference for t in targets[1:]]
    plan = E.training_plan(rows, refs, fold)
    assert rows[0].key.sample_id in plan["excluded"]


def test_terminal_consideration_and_cost_basis_gate_produce_no_zero_performance():
    rows, targets, _ = synthetic_panel()
    source = rows[0].universe_source
    economics = W.Economics("US", "SPY", "shareholder_return", "price_only", "UNRESOLVED", source, None)
    gate = E.evaluation_gate(economics, [replace(targets[0].reference, terminal_status="UNRESOLVED")], as_of="2020-01-01T00:00:00Z")
    assert gate["status"] == "BLOCKED" and "BLOCKED_OUTCOME_ECONOMICS" in gate["reasons"]
    assert not {"positions", "weights", "return", "scores"} & gate.keys()
    with pytest.raises(ValueError, match="FIVE"):
        E.evaluation_gate(economics, [], as_of="2020-01-01T00:00:00Z", maximum_positions=6)


def test_trial_chain_discloses_post_result_changes_and_detects_rewrites():
    a = E.trial_record([], version="v1", reason="initial exploratory protocol", result_informed=False, specification={"seed": 19})
    b = E.trial_record([a], version="v2", reason="after inspecting a failed trial", result_informed=True, specification={"seed": 19})
    assert b["hypothesisStatus"] == "RESULT_INFORMED_EXPLORATION" and b["trialNumber"] == 2
    assert not b["independentOosEvidence"]
    with pytest.raises(ValueError, match="REWRITTEN"):
        E.trial_record([{**a, "reason": "rewritten"}], version="v2", reason="x", result_informed=True, specification={"x": 1})


def test_default_cli_opens_no_source_and_does_not_authorize_execution(capsys, monkeypatch):
    monkeypatch.setattr(A, "inspect", lambda _: pytest.fail("opened data during preview"))
    assert A.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["sourceReads"] == report["labelReads"] == report["modelFits"] == 0
    assert not report["historicalExecutionAuthorized"]
    assert PRC.scan_for_outcome_keys({"financial.ocfMarginChange": 0.1}) is None


def test_all_missing_training_feature_does_not_become_a_zero_factor():
    rows, targets, fold = synthetic_panel()
    rows = [replace(o, cells=tuple(replace(c, value=None, missing_reason="NOT_STATED") for c in o.cells)) for o in rows]
    result = E.compare_synthetic(rows, targets, fold, seed=19)
    assert result["status"] == "BLOCKED" and result["reason"] == "NO_MEASURABLE_TRAINING_FEATURE"
    assert "scores" not in result


def test_signal_cannot_use_same_day_entry_or_foreign_duplicate_targets():
    rows, targets, fold = synthetic_panel()
    with pytest.raises(ValueError, match="DUPLICATE_OR_FOREIGN"):
        E.training_plan(rows, [targets[0].reference, targets[0].reference], fold)
    ref = replace(targets[0].reference, sample_id=rows[-1].key.sample_id)
    with pytest.raises(ValueError, match="LABEL_SIGNAL"):
        E.training_plan(rows, [ref], fold)


def test_existing_price_guard_never_backdates_a_late_split_confirmation():
    days = RC.sessions("2019-01-01", "2021-01-01", "KR")[:300]
    raw = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
                        "Volume": 1000.0, "ListedShares": 1e6}, index=days)
    raw.loc[days[150]:, ["Open", "High", "Low", "Close"]] /= 5
    raw.loc[days[175]:, "ListedShares"] *= 5
    early = days[160]
    whole = B.TickerBars("SYN", raw, days)
    prefix = B.TickerBars("SYN", raw.loc[:early], days)
    assert whole.basis_cause(early, 127) == prefix.basis_cause(early, 127) == "UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW"
    raw.loc[days[180]:, "Close"] = 99999.0
    assert B.TickerBars("SYN", raw, days).basis_cause(early, 127) == whole.basis_cause(early, 127)


def test_zero_volume_is_a_halt_even_when_a_close_is_carried_forward():
    days = RC.sessions("2019-01-01", "2020-01-01", "KR")[:150]
    raw = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
                        "Volume": 1000.0, "ListedShares": 1e6}, index=days)
    raw.loc[days[-2], "Volume"] = 0.0
    guard = B.TickerBars("SYN", raw, days)
    assert not guard.traded_mask.reindex(days[-127:]).all()
    assert guard.quote(days[-2]) is None


@pytest.mark.parametrize("market", ["KR", "US"])
def test_report_end_cannot_be_later_than_its_publication(market):
    rows = filings(market)
    bad = rows[-3]
    bad.update(availableFrom="2019-04-01", acceptedDate="2019-04-01", receiptNos=["20190401000001"])
    state = I.FilingStates(rows, market).at("2019-08-02")
    assert state["fields"]["ocfMarginChange"] is None
    assert "REPORT_PERIOD_AFTER_PUBLICATION" in state["reasons"]["ocfMarginChange"]


def test_features_and_labels_cannot_share_a_physical_output_directory():
    good = {k: "/tmp/synthetic-run/" + k for k in ("universe", "features", "labels", "decisions", "evaluation")}
    assert E.RunLayout(**good).labels.endswith("/labels")
    for path in (good["features"], good["features"] + "/nested-labels"):
        with pytest.raises(ValueError, match="PHYSICALLY_SEPARATE"):
            E.RunLayout(**{**good, "labels": path})


def test_immature_evaluation_is_blocked_even_with_verified_price_and_terminal_metadata():
    rows, targets, _ = synthetic_panel()
    source = rows[0].universe_source
    economics = W.Economics("US", "SPY", "shareholder_return", "shareholder_return", "VERIFIED", source, source)
    result = E.evaluation_gate(economics, [targets[0].reference], as_of="2017-01-09T00:00:00Z")
    assert result["status"] == "BLOCKED" and result["reasons"] == ["OUTCOME_NOT_MATURE_OR_AVAILABLE"]
