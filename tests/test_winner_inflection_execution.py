"""Execution, admission and economic invariants on invented inputs ONLY."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import uuid

import numpy as np
import pandas as pd
import pytest

from pipeline import experiment_workbench as W
from pipeline import industry_foundation as IF
from pipeline import winner_inflection_admission as A
from pipeline import winner_inflection_execution as X
from pipeline import winner_inflection_exploration as E
from scripts import run_winner_inflection as CLI

ROOT = Path(__file__).resolve().parents[1]


def spec():
    return json.loads((ROOT / A.SPEC_PATH).read_bytes())


@pytest.fixture(scope="module")
def prepared():
    data, config = X.synthetic_fixture(spec())
    keep = sorted(data["identity"])[:12]
    for key in ("filings", "identity"):
        data[key] = {t: data[key][t] for t in keep}
    from pipeline.regional_alpha_features import MembershipSnapshots
    data["membership"] = MembershipSnapshots([{"date": "2012-12-31", "members": keep}])
    config.update(minimumIssuers=8, minimumCohort=8)
    rows = X.observations(data, config)
    refs = X.references(rows, data, config)
    fold = W.Fold(**config["folds"][0])
    plan = E.training_plan(rows, list(refs.values()), fold, identity_statuses=("VERIFIED_SECURITY", "PROVISIONAL"))
    train = set(plan["training"])
    labels = X.label_cohorts([r for r in rows if r.key.sample_id in train], refs, data, minimum=config["minimumCohort"])
    models = X.model_predictions(rows, labels, plan, config, refs)
    assert models["status"] == "FITTED"
    return data, config, rows, refs, plan, labels, models


def test_fixed_pilot_and_default_admission_read_no_outcomes(monkeypatch, capsys):
    monkeypatch.setattr(CLI, "load_permitted", lambda *_: pytest.fail("real source opened"))
    monkeypatch.setattr(A, "github", lambda *_: pytest.fail("approval/network called"))
    monkeypatch.setattr(A, "source_preflight", lambda *_: {"status": "READY", "payloadReads": 0})
    assert CLI.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED"
    assert result["outcomeReads"] == result["modelFits"] == 0
    assert len(result["reasons"]) == 7
    assert CLI.main(["admit"]) == 2
    config = spec()
    X.validate_spec(config)
    assert config["folds"][0]["evaluation_start"] == "2020-01-01T00:00:00Z"
    assert config["horizon"] == 126


def test_fake_permit_cannot_open_any_source(monkeypatch):
    monkeypatch.setattr(CLI.S, "Sources", lambda *_: pytest.fail("source constructed without permit"))
    with pytest.raises(ValueError, match="DURABLE_OWNER_PERMIT"):
        CLI.load_permitted(ROOT, spec(), {}, {"codeCommit": "a" * 40, "claimRef": "fake"})


@pytest.fixture
def approval(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "source_preflight", lambda *_: {"status": "READY", "payloadReads": 0})
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in A.CLOSURE:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic closure fixture\n")
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=repo, text=True, stderr=subprocess.DEVNULL)
    git("init")
    git("add", ".")
    git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid", "commit", "-m", "synthetic fixture")
    monkeypatch.setattr(A, "EVIDENCE_ROOT", tmp_path / "evidence")
    evidence = A.EVIDENCE_ROOT / ("synthetic-" + uuid.uuid4().hex + ".json")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text('{"evidenceClass":"SYNTHETIC_FIXTURE","meaning":"test metadata, no real permission"}')
    review = json.loads((ROOT / A.REVIEW_PATH).read_bytes())
    for claim in review["claims"].values():
        claim.update(status="REVIEWED_ACCEPTED", reviewer="SYNTHETIC_REVIEWER", citations=[{"reference": str(evidence), "sha256": A.file_sha(evidence)}])
    value = A.request(repo, spec(), review, created_at="2026-10-17T01:00:00Z", run_root="/workspace/wid-executions/synthetic-approval-test")
    calls, claims = [], set()
    def api(args):
        calls.append(args)
        if "matching-refs" in args[0]:
            return [{"ref": t} for t in claims]
        if "/issues/comments/" in args[0]:
            return {"user": {"login": A.OWNER}, "author_association": "OWNER", "body": "APPROVE WID_EXECUTION " + value["sha256"],
                    "created_at": "2026-10-17T01:01:00Z", "html_url": "https://github.com/" + A.REPOSITORY + "/pull/999999#issuecomment-synthetic"}
        assert args[1:3] == ["-X", "POST"]
        tag = args[args.index("ref=" + "refs/tags/wid-exploration-attempt-" + value["spec"]["id"])].removeprefix("ref=")
        if tag in claims:
            raise ValueError("REFERENCE_ALREADY_EXISTS")
        claims.add(tag)
        return {"ref": tag, "object": {"sha": value["codeCommit"]}}
    yield repo, review, value, api, calls, claims, evidence
    evidence.unlink()


def test_owner_comment_and_atomic_claim_are_required(approval):
    repo, _, value, api, calls, claims, _ = approval
    permit = A.authorize(value, repo, comment_id=1, now="2026-10-17T01:02:00Z", api=api)
    assert A.require_permit(permit)["requestSha256"] == value["sha256"]
    assert len(claims) == 1
    assert calls[-1][1:3] == ["-X", "POST"]
    with pytest.raises(ValueError, match="HISTORY_CHANGED"):
        A.authorize(value, repo, comment_id=1, now="2026-10-17T01:03:00Z", api=api)


@pytest.mark.parametrize("change", ["actor", "phrase", "time", "url"])
def test_bad_owner_evidence_stops_before_claim(approval, change):
    repo, _, value, api, calls, claims, _ = approval
    def bad(args):
        result = api(args)
        if "/issues/comments/" in args[0]:
            if change == "actor": result["user"]["login"] = "untrusted"
            if change == "phrase": result["body"] += " extra permission scope"
            if change == "time": result["created_at"] = "2026-10-16T00:00:00Z"
            if change == "url": result["html_url"] = "https://github.com/other/repo/pull/1"
        return result
    with pytest.raises(ValueError):
        A.authorize(value, repo, comment_id=1, now="2026-10-17T01:02:00Z", api=bad)
    assert not claims and not any("POST" in c for c in calls)


@pytest.mark.parametrize("change", ["code", "request", "review", "evidence", "runtime", "expired"])
def test_changed_contract_blocks_before_github(approval, change):
    repo, _, value, api, calls, claims, evidence = approval
    value = deepcopy(value)
    now = "2026-10-17T01:02:00Z"
    if change == "code": (repo / A.CLOSURE[0]).write_text("changed")
    if change == "request": value["spec"]["seed"] = 123
    if change == "review": value["review"]["claims"]["rights"]["status"] = "UNRESOLVED"
    if change == "evidence": evidence.write_text("changed metadata")
    if change == "runtime": value["runtime"]["numpy"] = "0.invalid"
    if change == "expired": now = "2026-10-25T00:00:00Z"
    if change in ("review", "runtime"):
        value["sha256"] = IF.digest({k: v for k, v in value.items() if k != "sha256"})
    with pytest.raises(ValueError):
        A.authorize(value, repo, comment_id=1, now=now, api=api)
    assert not calls and not claims


def test_admission_never_infers_rights_from_existing_prices(approval):
    _, review, _, _, _, _, _ = approval
    assert A.admission(spec(), review)["status"] == "ADMITTED_CONDITIONALLY"
    review["claims"]["rights"]["citations"] = []
    assert "SOURCE_REVIEW_UNRESOLVED:rights" in A.admission(spec(), review)["reasons"]
    review["basis"] = "PRICE_ONLY_SPY"
    assert "STOCK_SPY_RETURN_BASIS_MISMATCH" in A.admission(spec(), review)["reasons"]


def test_next_session_and_h126_are_exchange_correct(prepared):
    _, _, rows, refs, _, _, _ = prepared
    friday = next(r for r in rows if r.key.signal_date == "2020-01-17")
    ref = refs[friday.key.sample_id]
    assert ref.execution_at.startswith("2020-01-21")  # MLK holiday
    assert X.close_at("2020-11-27") == "2020-11-27T19:00:00+00:00"  # early close + buffer
    assert X.close_at("2020-07-06") == "2020-07-06T21:00:00+00:00"  # DST
    assert len(X.RC.sessions(ref.execution_at[:10], ref.maturity_at[:10], "US")) == 127


def test_shared_fold_purges_and_calibration_uses_no_2020_labels(prepared):
    _, _, rows, refs, plan, _, models = prepared
    by_id = {r.key.sample_id: r for r in rows}
    assert set(models["properTraining"]).isdisjoint(models["calibrationSamples"])
    first_cal = min(by_id[s].key.signal_date for s in models["calibrationSamples"])
    assert all(refs[s].maturity_at[:10] < first_cal and refs[s].available_at[:10] < first_cal for s in models["properTraining"])
    assert all(by_id[s].key.signal_date < "2020" for s in [*models["properTraining"], *models["calibrationSamples"]])
    assert all(refs[s].available_at < plan["fold"]["label_deadline"] for s in models["properTraining"])


def test_future_target_poison_cannot_change_forecasts(prepared):
    _, config, rows, refs, plan, labels, models = prepared
    altered = deepcopy(labels)
    for sid in plan["evaluation"]:
        altered[sid] = {"status": "RESOLVED", "excess": 1e9, "winner": True, "big_loss": False}
    assert X.model_predictions(rows, altered, plan, config, refs) == models


def test_future_prices_and_filings_do_not_change_an_earlier_feature_prefix(prepared):
    data, config, *_ = prepared
    small = {**config, "inputStart": "2015-01-01", "signalEnd": "2015-01-16"}
    first = X.observations(data, small)
    changed = dict(data)
    changed["prices"] = data["prices"].copy()
    changed["prices"].loc["2021":] *= 1000
    changed["filings"] = {t: [*v, {**v[-1], "availableFrom": "2021-01-01", "acceptedDate": "2021-01-01"}] for t, v in data["filings"].items()}
    assert first == X.observations(changed, small)


def test_identity_mismatch_and_reused_ticker_stay_in_universe(prepared):
    data, config, *_ = prepared
    changed = dict(data)
    changed["identity"] = deepcopy(data["identity"])
    changed["identity"]["SYN00"]["cik"] = "9999999"
    changed["identity"]["SYN01"]["sp500IdentityCategory"] = "TICKER_REUSE_DIFFERENT_ISSUER"
    rows = X.observations(changed, {**config, "inputStart": "2020-01-01", "signalEnd": "2020-01-10"})
    bad = [r for r in rows if r.ticker in ("SYN00", "SYN01")]
    assert bad and all(not r.investable and all(c.value is None for c in r.cells) for r in bad)
    assert {r.eligibility_reason for r in bad} == {"CIK_IDENTITY_UNRESOLVED", "CONDITIONAL_SCOPE_EXCLUDED:TICKER_REUSE_DIFFERENT_ISSUER"}


def test_common_deciles_unresolved_is_not_a_neutral_zero(prepared):
    data, config, rows, refs, *_ = prepared
    selected = [r for r in rows if r.key.signal_date == "2020-01-03"]
    damaged = dict(data)
    damaged["prices"] = data["prices"].copy()
    ref = refs[selected[0].key.sample_id]
    damaged["prices"].loc[ref.maturity_at[:10], selected[0].ticker] = np.nan
    labels = X.label_cohorts(selected, refs, damaged, minimum=8)
    bad = labels[selected[0].key.sample_id]
    assert bad["status"] == "UNRESOLVED" and bad["excess"] is None and "winner" not in bad
    resolved = [v for v in labels.values() if v["status"] == "RESOLVED"]
    assert resolved and all(not (v["winner"] and v["big_loss"]) for v in resolved)


@pytest.mark.parametrize("cash", [0.0, 50.0])
def test_verified_cash_terminal_is_an_economic_payoff_not_a_last_quote(prepared, cash):
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    ref = refs[row.key.sample_id]
    copied = dict(data)
    copied["prices"] = data["prices"].copy()
    day = "2020-03-02"
    copied["prices"].loc[day:, row.ticker] = np.nan
    copied["terminal"] = {row.ticker: {"date": day, "settlementDate": day, "publicAt": day + "T12:00:00Z",
        "kind": "CASH", "cashPerShare": cash, "verified": True, "citation": "synthetic:cash-contract",
        "securityIdentity": row.key.security_identity, "currency": "USD", "shareBasis": "AS_TRADED_LAST_PRE_TERMINAL_SHARE"}}
    value = X.outcome(row, ref, copied)
    entry = data["prices"].at[pd.Timestamp(ref.execution_at[:10]), row.ticker]
    assert value["status"] == "RESOLVED" and value["gross"] == pytest.approx(cash / entry - 1)
    copied["terminal"][row.ticker]["kind"] = "STOCK_SWAP_UNVERIFIED"
    assert X.outcome(row, ref, copied)["status"] == "UNRESOLVED"


def test_late_terminal_evidence_cannot_rewrite_a_training_label(prepared):
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    copied = dict(data)
    copied["terminal"] = {row.ticker: {"date": "2020-03-02", "settlementDate": "2020-03-02", "publicAt": "2025-01-01T00:00:00Z",
        "kind": "CASH", "cashPerShare": 50., "verified": True, "citation": "synthetic:late-evidence",
        "securityIdentity": row.key.security_identity, "currency": "USD", "shareBasis": "AS_TRADED_LAST_PRE_TERMINAL_SHARE"}}
    assert X.outcome(row, refs[row.key.sample_id], copied)["status"] == "UNRESOLVED"


def test_metrics_keep_real_zero_and_missing_separate():
    perfect = X.probability_metrics([0, 1], [0, 1])
    assert perfect["brier"] == 0 and perfect["prAuc"] == 1
    assert sum(b["count"] for b in perfect["reliability"]) == 2
    assert X.probability_metrics([], [])["status"] == "UNRESOLVED"
    assert X.probability_metrics([1], [1])["prAuc"] is None


def test_end_to_end_physical_checkpoints_and_economics(prepared, monkeypatch, tmp_path):
    data, config, rows, refs, *_ = prepared
    monkeypatch.setattr(X, "observations", lambda *_: rows)
    monkeypatch.setattr(X, "references", lambda *_: refs)
    order = []
    def checkpoint(layer, key, value):
        order.append((layer, key))
        A.append_record(tmp_path / layer / (key + ".json"), value)
    result = X.execute(data, config, checkpoint=checkpoint)
    assert result["evaluation"]["status"] == "EXPLORATION_COMPLETED"
    assert order.index(("decisions", "fold-0")) < order.index(("labels", "fold-0-evaluation"))
    assert (tmp_path / "features/records.json").exists() and (tmp_path / "labels/fold-0-evaluation.json").exists()
    report = result["evaluation"]["folds"][0]
    measured = report["predictive"]["models"]
    assert len({v["sampleIdsSha256"] for v in measured.values()}) == 1
    assert report["controls"]["matchedCases"] > 0
    assert report["economic"]["strategies"]["pattern_augmented:logistic"]["cohorts"] == 2
    for detail in report["economic"]["strategies"].values():
        assert detail["status"] == "MEASURED"
        assert detail["netReturn"] <= detail["grossReturn"]
    assert not {"winner", "big_loss", "excess"} & result["features"][0]["features"].keys()
    with pytest.raises(FileExistsError):
        A.append_record(tmp_path / "features/records.json", {})


def test_h126_label_and_spy_share_the_exact_same_basis(prepared):
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    equal = dict(data)
    equal["prices"] = data["prices"].copy()
    equal["prices"][row.ticker] = equal["prices"]["SPY"]
    value = X.outcome(row, refs[row.key.sample_id], equal)
    assert value["status"] == "RESOLVED" and value["excess"] == 0


def test_missing_held_price_never_forces_liquidation_or_zero_return(prepared):
    data, _, rows, refs, _, _, models = prepared
    copied = data["prices"].copy()
    copied.loc["2020-04-01", [c for c in copied if c != "SPY"]] = np.nan
    result = X.economics(rows, models, copied, refs)
    assert result["strategies"]["pattern_augmented:logistic"]["status"] == "UNRESOLVED"
    assert "netReturn" not in result["strategies"]["pattern_augmented:logistic"]


def test_flat_price_round_trip_costs_match_cash_account_arithmetic(prepared):
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    copied = dict(data)
    copied["prices"] = data["prices"] * 0 + 100.
    result = X.cohort_endpoint({row.ticker: 1.}, {row.ticker: row.key.sample_id}, {row.key.sample_id: row}, refs, copied)
    assert result["grossReturn"] == 0.
    assert result["netReturn"] == pytest.approx((1 - .00083) / (1 + .0008) - 1, abs=1e-12)
    assert result["costInitialCapital"] == pytest.approx(-result["netReturn"], abs=1e-12)


def test_total_loss_cash_settlement_resolves_end_wealth_without_inventing_a_price(prepared):
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    copied = dict(data)
    copied["prices"] = data["prices"].copy()
    copied["prices"].loc["2020-03-02":, row.ticker] = np.nan
    copied["terminal"] = {row.ticker: {"date": "2020-03-02", "settlementDate": "2020-03-02", "publicAt": "2020-03-02T12:00:00Z",
        "kind": "CASH", "cashPerShare": 0., "verified": True, "citation": "synthetic:legal-zero-consideration",
        "securityIdentity": row.key.security_identity, "currency": "USD", "shareBasis": "AS_TRADED_LAST_PRE_TERMINAL_SHARE"}}
    result = X.cohort_endpoint({row.ticker: 1.}, {row.ticker: row.key.sample_id}, {row.key.sample_id: row}, refs, copied)
    assert result["status"] == "MEASURED_ENDPOINT" and result["netReturn"] == -1
    assert result["dailyMdd"] == -1  # necessarily reaches zero, regardless of missing intermediate marks
    assert np.isnan(copied["prices"].loc["2020-03-02", row.ticker])  # never rewritten/zero-filled


def test_internal_vendor_basis_is_not_silently_called_exact_cash_reinvestment(prepared):
    from pipeline import price_adjustment as PA
    from pipeline import us_multifactor_inputs as MI
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    ref = refs[row.key.sample_id]
    days = X.RC.sessions(ref.execution_at[:10], ref.maturity_at[:10], "US")
    raw = pd.DataFrame({"Close": [100.] + [99.] * (len(days) - 1), "Dividends": [0., 2.] + [0.] * (len(days) - 2), "Stock Splits": 0.}, index=days)
    internal, _ = PA.to_total_return(raw)
    recovered = MI.as_traded_from_total_return(days, internal.Close, [(str(days[1].date()), 2., 1.)])
    assert recovered[-1] == pytest.approx(99.)
    proxy = internal.Close.iloc[-1] / internal.Close.iloc[0] - 1
    assert proxy == pytest.approx(99 / 98 - 1)
    assert proxy != pytest.approx((99 + 2) / 100 - 1)
    cash = X.cash_reinvestment_close(raw.Close, [(str(days[1].date()), 2., 1.)])
    assert cash.iloc[-1] / cash.iloc[0] - 1 == pytest.approx(.01)


def test_calendar_cache_keeps_prebuffer_and_final_timestamps_distinct():
    assert "2020-11-27" not in W._us_completed_at("2020-11-27 18:59:00+00:00")
    assert "2020-11-27" in W._us_completed_at("2020-11-27 19:00:00+00:00")


def test_role_layers_reject_overlapping_output_paths(approval):
    repo, review, *_ = approval
    with pytest.raises(ValueError, match="DEDICATED_EXECUTION_DIRECTORY"):
        A.request(repo, spec(), review, created_at="2026-10-17T01:00:00Z", run_root=repo / "docs/results")


def test_immature_label_stops_before_any_price_access(prepared):
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    immature = {"asOf": "2020-02-01T00:00:00Z"}  # deliberately NO prices key
    assert X.outcome(row, refs[row.key.sample_id], immature) == {"status": "UNRESOLVED", "reason": "OUTCOME_NOT_MATURE_OR_PUBLIC", "excess": None}


def test_calibration_labels_cannot_change_the_fitted_raw_models(prepared):
    _, config, rows, refs, plan, labels, models = prepared
    altered = deepcopy(labels)
    for sid in models["calibrationSamples"]:
        altered[sid]["winner"] = not altered[sid]["winner"]
        altered[sid]["big_loss"] = not altered[sid]["big_loss"]
    after = X.model_predictions(rows, altered, plan, config, refs)
    for variant in ("levels_momentum", "pattern_augmented"):
        for sid in models["evaluation"]:
            for key in ("ridge", "logistic_winner", "logistic_big_loss"):
                assert after["variants"][variant]["predictions"][sid][key] == models["variants"][variant]["predictions"][sid][key]


def test_source_scope_cannot_change_after_owner_permit(approval, monkeypatch):
    repo, review, value, api, _, _, _ = approval
    permit = A.authorize(value, repo, comment_id=1, now="2026-10-17T01:02:00Z", api=api)
    changed = deepcopy(spec())
    changed["seed"] = 1
    monkeypatch.setattr(CLI.S, "Sources", lambda *_: pytest.fail("source opened before scope binding"))
    with pytest.raises(ValueError, match="INPUT_SCOPE_CHANGED"):
        CLI.load_permitted(ROOT, changed, review, permit)


def test_generated_request_envelope_is_the_direct_execute_input(approval, tmp_path, monkeypatch, capsys):
    repo, _, value, *_ = approval
    path = tmp_path / "request.json"
    path.write_text(json.dumps({"request": value, "approvalText": "APPROVE WID_EXECUTION " + value["sha256"]}))
    def deny(actual, root, **kwargs):
        assert actual == value
        raise ValueError("SYNTHETIC_OWNER_DENIAL")
    monkeypatch.setattr(A, "authorize", deny)
    monkeypatch.setattr(CLI, "load_permitted", lambda *_: pytest.fail("unapproved real-value reader"))
    assert CLI.main(["execute", "--request", str(path), "--approval-comment", "1"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "SYNTHETIC_OWNER_DENIAL"


def test_source_lineage_is_checked_before_any_price_value(approval, monkeypatch):
    repo, review, _, api, *_ = approval
    manifest = {"components": {"price/source": ["price-meta"], "benchmark/source": ["spy-meta"],
                              "corporate-events/source": ["basis-meta"], "price/2020-01": ["prices"]}}
    config = spec()
    config["sourceManifestSha256"] = IF.digest(manifest)
    value = A.request(repo, config, review, created_at="2026-10-17T01:00:00Z", run_root="/workspace/wid-executions/synthetic-lineage")
    def owner(args):
        response = api(args)
        if "/issues/comments/" in args[0]: response["body"] = "APPROVE WID_EXECUTION " + value["sha256"]
        return response
    permit = A.authorize(value, repo, comment_id=1, now="2026-10-17T01:02:00Z", api=owner)
    calls = []
    class FakeSources:
        def __init__(self, root): self.allowed_objects = set()
        def blob(self, *_): return json.dumps(manifest).encode()
        def json(self, path): return {"snapshots": [{"date": "2012-12-31", "members": ["SYN00"]}]}
        def component(self, ref):
            calls.append(ref)
            if ref == "price-meta": return [{"region": "US", "vendor": "YAHOO_UNADJUSTED_WITH_ACTIONS"}]
            if ref == "spy-meta": return [{"region": "US", "ticker": "SPY", "symbol": "SPY", "source": "WRONG_VENDOR"}]
            if ref == "basis-meta": return []
            pytest.fail("opened outcome-bearing prices before lineage admission")
    monkeypatch.setattr(CLI.S, "Sources", FakeSources)
    with pytest.raises(ValueError, match="LINEAGE_MISMATCH"):
        CLI.load_permitted(repo, config, review, permit)
    assert "prices" not in calls


def test_cash_terminal_requires_exact_identity_currency_and_share_basis(prepared):
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    copied = dict(data)
    copied["terminal"] = {row.ticker: {"date": "2020-03-02", "settlementDate": "2020-03-02", "publicAt": "2020-03-02T12:00:00Z",
        "kind": "CASH", "cashPerShare": 50., "verified": True, "citation": "synthetic:unknown-share-context"}}
    assert X.outcome(row, refs[row.key.sample_id], copied)["status"] == "UNRESOLVED"


def test_split_and_cash_dividend_are_on_the_same_post_split_share_unit():
    days = pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08"])
    raw = pd.Series([100., 50., 50.], index=days)
    result = X.cash_reinvestment_close(raw, [("2020-01-07", 1., 2.)])
    assert result.iloc[-1] / result.iloc[0] - 1 == pytest.approx(.02)
    separate = X.cash_reinvestment_close(raw, [("2020-01-07", 0., 2.), ("2020-01-07", 1., 1.)])
    pd.testing.assert_series_equal(separate, result)


def test_missing_native_quote_is_a_barrier_not_a_fabricated_return():
    days = pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09"])
    raw = pd.Series([100., np.nan, 150., 165.], index=days)
    result = X.cash_reinvestment_close(raw, [])
    assert np.isnan(result.iloc[1])
    assert result.iloc[-1] / result.iloc[-2] - 1 == pytest.approx(.1)


def test_next_session_halt_is_not_an_executable_entry(prepared):
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    copied = dict(data)
    copied["volumes"] = data["volumes"].copy()
    copied["volumes"].loc[refs[row.key.sample_id].execution_at[:10], row.ticker] = 0.
    assert X.outcome(row, refs[row.key.sample_id], copied)["reason"] == "ENTRY_NOT_TRADABLE"


@pytest.mark.parametrize("change", ["interior_gap", "halted_split", "terminated_entry"])
def test_terminal_payoff_does_not_bridge_an_unknown_share_chain(prepared, change):
    data, _, rows, refs, *_ = prepared
    row = next(r for r in rows if r.key.signal_date == "2020-01-03")
    copied = dict(data)
    copied["prices"] = data["prices"].copy()
    copied["prices"].loc["2020-03-02":, row.ticker] = np.nan
    copied["terminal"] = {row.ticker: {"date": "2020-03-02", "settlementDate": "2020-03-02", "publicAt": "2020-03-02T12:00:00Z",
        "kind": "CASH", "cashPerShare": 50., "verified": True, "citation": "synthetic:share-chain",
        "securityIdentity": row.key.security_identity, "currency": "USD", "shareBasis": "AS_TRADED_LAST_PRE_TERMINAL_SHARE"}}
    if change == "interior_gap": copied["prices"].loc["2020-02-03", row.ticker] = np.nan
    if change == "halted_split": copied["events"] = {row.ticker: [("2020-03-02", 0., 2.)]}
    if change == "terminated_entry": copied["terminal"][row.ticker]["date"] = "2020-01-03"
    value = X.outcome(row, refs[row.key.sample_id], copied)
    assert value["status"] == "UNRESOLVED" and value["excess"] is None


def test_invalid_execution_spec_is_rejected_before_owner_claim(tmp_path, monkeypatch, capsys):
    config = spec()
    config["horizon"] = 252
    path = tmp_path / "request.json"
    path.write_text(json.dumps({"request": {"spec": config}}))
    monkeypatch.setattr(A, "authorize", lambda *_args, **_kwargs: pytest.fail("claimed unsupported execution"))
    assert CLI.main(["execute", "--request", str(path), "--approval-comment", "1"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "UNSUPPORTED_EXECUTION_SPEC"


def test_duplicate_corporate_action_requires_reconciliation():
    raw = pd.Series([100., 99.], index=pd.to_datetime(["2020-01-06", "2020-01-07"]))
    with pytest.raises(ValueError, match="DUPLICATE_ACTION_DATE"):
        X.cash_reinvestment_close(raw, [("2020-01-07", 1., 1.), ("2020-01-07", 1., 1.)])


def test_existing_output_directory_cannot_be_modified_even_on_failure(approval, tmp_path, monkeypatch, capsys):
    _, _, value, *_ = approval
    old = tmp_path / "existing"
    old.mkdir()
    (old / "marker.json").write_text('{"retained":true}')
    value = {**value, "runRoot": str(old)}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(value))
    monkeypatch.setattr(A, "authorize", lambda *_args, **_kwargs: A.VerifiedPermit({}, A._AUTHENTICATED))
    monkeypatch.setattr(CLI, "load_permitted", lambda *_: pytest.fail("read source into existing run"))
    assert CLI.main(["execute", "--request", str(path), "--approval-comment", "1"]) == 2
    assert sorted(p.name for p in old.iterdir()) == ["marker.json"]
    assert json.loads(capsys.readouterr().out)["attemptConsumed"]


def test_insufficient_class_support_blocks_before_any_numeric_fit(prepared, monkeypatch):
    _, config, rows, refs, plan, labels, _ = prepared
    changed = deepcopy(labels)
    for value in changed.values():
        if value["status"] == "RESOLVED": value["winner"] = False
    monkeypatch.setattr(E, "fit_prepared", lambda *_args, **_kwargs: pytest.fail("fit before class admission"))
    assert X.model_predictions(rows, changed, plan, config, refs)["reason"] == "INSUFFICIENT_BINARY_CLASS_SUPPORT"


@pytest.mark.parametrize("duplicate_identity", [False, True])
def test_approved_loader_reconstructs_shared_cash_basis_on_invented_archive(approval, monkeypatch, duplicate_identity):
    import gzip
    repo, review, _, api, *_ = approval
    manifest = {"components": {"price/source": ["price-meta"], "benchmark/source": ["spy-meta"],
        "corporate-events/source": ["basis-meta"], "price/2013-01": ["quotes"],
        "benchmark/2013-01": ["spy"], "corporate-events/2013-01": ["actions"]}}
    config = spec()
    config["sourceManifestSha256"] = IF.digest(manifest)
    value = A.request(repo, config, review, created_at="2026-10-17T01:00:00Z", run_root="/workspace/wid-executions/synthetic-loader")
    def owner(args):
        response = api(args)
        if "/issues/comments/" in args[0]: response["body"] = "APPROVE WID_EXECUTION " + value["sha256"]
        return response
    permit = A.authorize(value, repo, comment_id=1, now="2026-10-17T01:02:00Z", api=owner)
    class FakeSources:
        def __init__(self, root): self.allowed_objects, self.receipts = set(), {"synthetic:archive": {"fixture": True}}
        def blob(self, *_): return json.dumps(manifest).encode()
        def json(self, path):
            return {"snapshots": [{"date": "2012-12-31", "members": ["SYN00"],
                "rows": {"SYN00": {"cik": "7000000", "sector": "Industrials"}}}]}
        def component(self, ref):
            if ref == "price-meta": return [{"region": "US", "vendor": "YAHOO_UNADJUSTED_WITH_ACTIONS", "distributions": "YAHOO_ACTIONS"}]
            if ref == "spy-meta": return [{"region": "US", "ticker": "SPY", "symbol": "SPY", "source": "yahoo"}]
            if ref == "basis-meta": return [{"adjustment": "as-traded-forward-total-return-v1", "anchor": "FIRST_OBSERVED_SESSION",
                "basis": "AS_TRADED_CLOSE_WITH_FORWARD_ACCUMULATED_TOTAL_RETURN", "vendor": "YAHOO_UNADJUSTED_WITH_ACTIONS"}]
            if ref == "quotes": return [{"ticker": "SYN00", "date": d, "Close": p, "Volume": 1e6}
                for d, p in (("2013-01-07", 100.), ("2013-01-08", 100 * 99 / 98))]
            if ref == "spy": return [{"ticker": "SPY", "date": d, "Close": p} for d, p in (("2013-01-07", 200.), ("2013-01-08", 202.))]
            if ref == "actions": return [{"ticker": "SYN00", "date": "2013-01-08", "dividend": 2., "split": 1., "applied": True}]
            pytest.fail("unadmitted source object")
        def rows(self, path): return []
        def local(self, path):
            assert path == CLI.S.US_IDENTITY
            row = 'SYN00,7000000,CURRENT_MEMBER_OWN_PANEL\n'
            return gzip.compress(('symbol,cik,sp500IdentityCategory\n' + row * (2 if duplicate_identity else 1)).encode())
    monkeypatch.setattr(CLI.S, "Sources", FakeSources)
    if duplicate_identity:
        with pytest.raises(ValueError, match="DUPLICATE_SOURCE_IDENTITY_SYMBOL"):
            CLI.load_permitted(repo, config, review, permit)
    else:
        data = CLI.load_permitted(repo, config, review, permit)
        assert data["asTraded"].SYN00.iloc[-1] == pytest.approx(99.)
        assert data["prices"].SYN00.iloc[-1] == pytest.approx(101.)
        assert data["prices"].SPY.iloc[-1] == pytest.approx(202.)
        assert data["lineage"] and data["receipts"]


def test_missing_source_objects_are_detected_without_opening_payloads(tmp_path, monkeypatch):
    from scripts import inspect_experiment_sources as sources
    subprocess.check_call(["git", "init", "-q", str(tmp_path)])
    manifest = {"components": {"price/2020-01": ["a" * 64]}}
    config = spec()
    config["sourceManifestSha256"] = IF.digest(manifest)
    class MetadataOnly:
        def __init__(self, root): pass
        def blob(self, commit, path):
            assert path == sources.MANIFEST and commit == sources.SOURCE_COMMIT
            return json.dumps(manifest).encode()
        def component(self, *_): pytest.fail("outcome-bearing payload opened by preflight")
    monkeypatch.setattr(sources, "Sources", MetadataOnly)
    monkeypatch.setattr(A, "object_type", lambda *_: "commit")  # This test isolates missing payloads, not commit bindings.
    result = A.source_preflight(tmp_path, config)
    assert result["status"] == "BLOCKED" and result["payloadReads"] == 0
    assert result["missingObjects"] == result["requiredObjects"] == 15


def test_lost_local_source_objects_block_before_owner_and_durable_claim(approval, monkeypatch):
    repo, _, value, api, calls, claims, _ = approval
    monkeypatch.setattr(A, "source_preflight", lambda *_: {"status": "BLOCKED", "missingObjects": 1, "payloadReads": 0})
    with pytest.raises(ValueError, match="LOCAL_SOURCE_OBJECTS"):
        A.authorize(value, repo, comment_id=1, now="2026-10-17T01:02:00Z", api=api)
    assert not calls and not claims
