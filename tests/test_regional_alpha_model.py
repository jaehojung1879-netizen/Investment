"""Leakage, lineage, regional separation, and reproducibility invariants."""
import inspect

import numpy as np
import pandas as pd
import pytest

from pipeline import fundamental_acceleration as FA
from pipeline import historical_replay as HR
from pipeline import pit_data as PIT
from pipeline import regional_alpha_features as F
from pipeline import regional_alpha_model as M
from scripts import run_regional_alpha_model as RUN


def fixture_frame():
    rng = np.random.default_rng(714)
    rows = []
    for region in ("US", "KR"):
        for date in pd.date_range("2013-01-04", "2017-12-29", freq="W-FRI"):
            for i in range(12):
                feature = float(rng.random())
                outcome = float(feature + rng.normal(scale=.2))
                rows.append(dict(region=region, date=str(date.date()), ticker=f"T{i:02}",
                                 x=feature if i else np.nan, x__missing=int(i == 0),
                                 futureExcess126=outcome,
                                 outcomeEndDate=str((date+pd.offsets.BDay(126)).date()),
                                 target=0.0))
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def frame():
    return fixture_frame()


def test_weights_sum_to_one_per_date(frame):
    f = frame.loc[frame.region.eq("US")].iloc[3:]
    weights = M.date_weights(f)
    np.testing.assert_allclose(pd.Series(weights).groupby(f.date.to_numpy()).sum(), 1)


def test_pooled_weights_rejected(frame):
    with pytest.raises(ValueError, match="pooled"):
        M.date_weights(frame)


def test_label_maturity_strictly_before_validation(frame):
    sub = frame.loc[frame.region.eq("US")]
    train = M.training_frame(sub, "2016-01-01")
    M.assert_training_cutoff(train, "2016-01-01")
    assert train.outcomeEndDate.max() < "2016-01-01"
    train.loc[train.index[0], "outcomeEndDate"] = "2016-01-01"
    with pytest.raises(ValueError, match="VALIDATION_LABEL_LEAKAGE"):
        M.assert_training_cutoff(train, "2016-01-01")


def test_training_ranks_do_not_use_unmatured_peer_labels(frame):
    f = frame.loc[frame.region.eq("US")].copy()
    first_date = f.date.min()
    idx = f.index[f.date.eq(first_date)][0]
    f.loc[idx, "outcomeEndDate"] = "2099-01-01"
    before = M.training_frame(f, "2016-01-01")
    f.loc[idx, "futureExcess126"] = 1e9
    after = M.training_frame(f, "2016-01-01")
    pd.testing.assert_frame_equal(before, after)
    expected = before.groupby("date").futureExcess126.rank(pct=True) - .5
    np.testing.assert_allclose(before.target, expected)


def split(frame):
    sub = frame.loc[frame.region.eq("US")]
    return M.training_frame(sub, "2016-01-01"), sub.loc[sub.date.ge("2016-01-01")].head(100).copy()


def test_imputation_and_scaler_training_only(frame):
    train, validation = split(frame)
    _, d1 = M.fit_predict(train, validation, ["x"], "RIDGE")
    validation["x"] = 1e12
    _, d2 = M.fit_predict(train, validation, ["x"], "RIDGE")
    assert d1 == d2
    assert d1["imputationMedians"][0] == train.x.median()
    expected = train.x.fillna(train.x.median()).mean()
    assert d1["scalerMean"][0] == pytest.approx(expected)


def test_all_missing_training_field_not_zero_filled(frame):
    train, validation = split(frame)
    train = train.copy()
    for part in (train, validation):
        part["absent"], part["absent__missing"] = np.nan, 1
    _, diag = M.fit_predict(train, validation, ["x", "absent"], "RIDGE")
    assert diag["omittedAllMissingTraining"] == ["absent"]
    assert "absent" not in diag["predictiveColumns"]


@pytest.mark.parametrize("method", M.METHODS)
def test_deterministic_predictions(frame, method):
    train, validation = split(frame)
    p1, d1 = M.fit_predict(train, validation, ["x"], method)
    p2, d2 = M.fit_predict(train, validation, ["x"], method)
    assert p1.tobytes() == p2.tobytes()
    assert d1 == d2


def test_models_cannot_share_regions(frame):
    train, validation = split(frame)
    validation["region"] = "KR"
    with pytest.raises(ValueError, match="separate US/KR"):
        M.fit_predict(train, validation, ["x"], "HGBR")


def test_forbidden_and_unresolved_inputs_not_allowlisted():
    manifest = F.feature_manifest()
    for region in ("US", "KR"):
        names = F.allowed_features(manifest, region)
        assert not set(names) & {"ticker", "region", "date", "year", "outcomeEndDate", "sector", "alphaPercentile"}
        assert not set(names) & {r["feature"] for r in manifest if r["region"] == region and not r["eligible"]}
    assert "marketCap" not in F.allowed_features(manifest, "US")
    assert set(F.DELTAS).issubset(F.allowed_features(manifest, "KR"))


def test_no_random_split_or_early_stopping():
    text = inspect.getsource(M)
    assert "train_test_split" not in text and "GridSearch" not in text
    assert M.HGBR_PARAMS["early_stopping"] is False


def test_membership_reentry_does_not_erase_exit():
    snapshots = F.MembershipSnapshots([dict(date="2013-01-01", members=["A"]),
                                       dict(date="2014-01-01", members=["B"]),
                                       dict(date="2015-01-01", members=["A"])])
    assert snapshots.on("2013-01-01") is None
    assert snapshots.on("2014-02-01")["members"] == ["B"]
    assert snapshots.on("2015-02-01")["members"] == ["A"]


def test_future_price_cannot_change_features():
    dates = pd.bdate_range("2011-01-01", periods=800)
    close = 100 + np.arange(800, dtype=float)
    frame = pd.DataFrame({"Close": close, "Volume": np.ones(800)}, index=dates)
    h = HR.PricePanel({"T": frame}).get("T")
    asof = str(dates[400].date())
    before = F.price_features(h, 400, h, asof)
    altered = frame.copy()
    altered.loc[dates[401]:, "Close"] *= 100
    later = HR.PricePanel({"T": altered}).get("T")
    assert before == F.price_features(later, 400, later, asof)
    assert F.weekly_breadth(h, h, asof) == F.weekly_breadth(later, later, asof)
    with pytest.raises(PIT.LookAheadError):
        F.price_features(h, 401, h, asof)


def test_future_amendment_and_filing_excluded():
    records = [PIT.FundamentalRecord("T", "2019-Q1", "2019-05-01", {"roe": .1}),
               PIT.FundamentalRecord("T", "2019-Q2", "2019-08-01", {"roe": .2}),
               PIT.FundamentalRecord("T", "2019-Q2", "2020-01-01", {"roe": 9}),
               PIT.FundamentalRecord("T", "2019-Q3", "2019-11-01", {"roe": 8})]
    pair = FA.resolve_filing_pair(PIT.FundamentalStore({"T": records}), "T", "US", "2019-09-01")
    assert pair.current.fields["roe"] == .2
    assert FA.compute_deltas(pair.current, pair.previous)["roe"] == pytest.approx(.1)


def test_top10_selection_before_label_availability():
    f = pd.DataFrame(dict(date=["2020-01-01"]*12, ticker=[str(i) for i in range(12)],
                         predictionScore=np.arange(12), futureExcess126=np.ones(12)))
    f.loc[11, "futureExcess126"] = np.nan
    dates = M.per_date(f)
    assert dates.top10Excess.isna().all()


def test_constant_score_is_not_fake_ic():
    f = pd.DataFrame(dict(date=["2020-01-01"]*12, ticker=[str(i) for i in range(12)],
                         predictionScore=np.ones(12), futureExcess126=np.arange(12)))
    assert M.per_date(f).rankIC.isna().all()


def test_hac_missing_not_zero():
    assert M.hac(pd.Series(dtype=float))["mean"] is None


def test_no_evidence_is_not_missing_evidence():
    summary = dict(rankIC=dict(mean=None, ci95=None), q5MinusQ1=dict(mean=None),
                   monotonicity=None, positiveFoldFraction=None)
    assert M.classify(summary) == "NOT_EVALUABLE"


def test_same_seed_byte_identical_artifacts_and_no_ledger_writes(frame, tmp_path):
    manifest = [dict(region=r, feature="x", group="price", eligible=True) for r in ("US", "KR")]
    ledger = tmp_path/"ledger"
    ledger.mkdir()
    (ledger/"seal").write_bytes(b"unchanged")
    digest = F.digest_tree(ledger)
    output = []
    for name in ("a", "b"):
        p, f = M.walk_forward(frame, manifest)
        metrics, _ = M.evaluate(p.assign(mom6=p.x, mom121=p.x, relative126=p.x,
                                         relativeStrengthBreadth52w=p.x, marketCap=p.x), f)
        folder = tmp_path/name
        folder.mkdir()
        RUN.write_frame(folder/"predictions.csv.gz", p)
        RUN.write_json(folder/"manifest.json", manifest)
        RUN.write_json(folder/"metrics.json", metrics)
        output.append({x.name:x.read_bytes() for x in folder.iterdir()})
    assert output[0] == output[1]
    assert digest == F.digest_tree(ledger)


def test_output_guard_refuses_sealed_tree(tmp_path):
    with pytest.raises(ValueError, match="outside sealed"):
        RUN.main([str(tmp_path), "--output-dir", str(tmp_path/"outputs")])


def test_target_rejects_stock_quote_horizon_longer_than_benchmark():
    dates = pd.bdate_range("2020-01-01", periods=300)
    bench = pd.DataFrame({"Close": 100 + np.arange(300)}, index=dates)
    prices = {"SPY": bench, "069500.KS": bench, "T": bench.drop(dates[20])}
    frame = pd.DataFrame([dict(region="US", date=str(dates[0].date()), ticker="T", benchmark="SPY", outcomeJoinId="gap"),
                          dict(region="US", date=str(dates[30].date()), ticker="T", benchmark="SPY", outcomeJoinId="valid")])
    labels = M.join_outcomes(frame, prices).set_index("outcomeJoinId")
    assert pd.isna(labels.loc["gap", "futureExcess126"])
    assert pd.notna(labels.loc["valid", "futureExcess126"])


def test_raw_audit_withholds_late_prior_filing_derived_growth(tmp_path):
    import gzip
    import json

    def raw(year, visible, profit):
        return dict(ticker="T", fiscalYear=year, form="10-K", periodDays=365,
                    periodEnd=f"{year}-12-31", availableFrom=visible,
                    statements={"ic": [{"concept": "us-gaap_NetIncomeLoss", "unit": "usd", "value": profit},
                                       {"concept": "us-gaap_Revenues", "unit": "usd", "value": 100}],
                                "bs": [], "cf": []})

    # The global source index could derive 100% growth using a prior FY
    # filing that was not actually visible until AFTER the current filing.
    records = [raw(2018, "2020-06-01", 10), raw(2019, "2020-02-01", 20)]
    directory = tmp_path/"fundamentals/us"
    directory.mkdir(parents=True)
    (directory/"finnhub-2020.jsonl.gz").write_bytes(gzip.compress(
        "".join(json.dumps(r)+"\n" for r in records).encode(), mtime=0))
    store = PIT.FundamentalStore({"T": [PIT.FundamentalRecord(
        "T", "2019-FY", "2020-02-01", {"earningsGrowth": 1., "profitMargin": .2})]})
    vetted, audit = F.vetted_fundamentals(tmp_path, store)
    assert vetted._records["T"][0].fields == {"profitMargin": .2}
    assert audit["withheldFields"] == 1
