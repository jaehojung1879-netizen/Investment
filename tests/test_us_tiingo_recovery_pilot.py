"""us-tiingo-price-recovery-pilot-v1: plan, transport discipline, parsing, identity, comparison, report. Synthetic only, no socket."""
from __future__ import annotations

import ast
import copy
import gzip
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest

from pipeline import us_tiingo_recovery_pilot as P

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "tok3n-SYNTHETIC-0123456789abcdef"


def load_cli():
    spec = importlib.util.spec_from_file_location("run_tiingo_pilot", ROOT / "scripts/run_us_tiingo_recovery_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLI = load_cli()
PLAN = json.loads((ROOT / P.PLAN_PATH).read_text())
CALENDAR = PLAN["calendar"]["sessions"]


# ---- a synthetic provider world -------------------------------------------------------------------------------------------------
def rows_for(days, dividend_on=None):
    out = []
    for i, day in enumerate(sorted(days)):
        close = 50.0 + (i % 7)
        factor = 0.98 if dividend_on and day < dividend_on else 1.0
        out.append({"date": day + "T00:00:00.000Z", "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000,
                    "adjOpen": close * factor, "adjHigh": (close + 1) * factor, "adjLow": (close - 1) * factor, "adjClose": close * factor,
                    "adjVolume": 1000, "divCash": 0.5 if day == dividend_on else 0.0, "splitFactor": 1.0})
    return out


def supported_zip(rows):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("supported_tickers.csv", "ticker,exchange,assetType,priceCurrency,startDate,endDate\n" +
                         "".join(f"{t},NYSE,Stock,USD,{a},{b}\n" for t, a, b in rows))
    return buffer.getvalue()


def world(plan=PLAN, *, override=None):
    """url -> (status, headers, body). Every identity is answered by default: Tiingo's name and dates agree, NONE and FULL get every
    expected session, PARTIAL gets the first half, one dividend each."""
    responses, listings = {}, []
    for e in plan["identities"]:
        t, w = e["auditIdentifier"], e["expectedPricingWindow"]
        days = sorted(P.expected_sessions(e, CALENDAR))
        if e["stratum"] == "PARTIAL":
            days = days[: len(days) // 2]
        responses[P.tiingo_meta_url(t)] = (200, {}, json.dumps({"ticker": t.lower(), "name": e["historicalIssuerNames"][0],
                                                                "exchangeCode": "NYSE", "startDate": w["first"], "endDate": w["last"],
                                                                "description": "synthetic"}).encode())
        responses[P.tiingo_prices_url(t, w["first"], w["last"])] = (200, {"X-RateLimit-Remaining": "40"},
                                                                    json.dumps(rows_for(days, days[len(days) // 3])).encode())
        listings.append((t, w["first"], w["last"]))
    responses[P.TIINGO_SUPPORTED_TICKERS] = (200, {}, supported_zip(listings))
    responses[P.SEC_CIK_LOOKUP] = (200, {}, b"NORDSTROM INC:0000072333:\nDAYFORCE, INC.:0001725057:\n")
    responses[P.SEC_SUBMISSIONS.format(cik=72333)] = (200, {}, json.dumps({"name": "NORDSTROM INC", "formerNames": [], "tickers": ["JWN"]}).encode())
    responses[P.SEC_SUBMISSIONS.format(cik=1725057)] = (200, {}, json.dumps({"name": "Dayforce, Inc.", "formerNames": [{"name": "Ceridian HCM", "from": "2018-01-01", "to": "2024-02-01"}], "tickers": ["DAY"]}).encode())
    responses.update(override or {})
    return responses


class Fake:
    def __init__(self, responses, default=(404, {}, b'{"detail":"Not found."}')):
        self.responses, self.default, self.calls = responses, default, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        value = self.responses.get(url, self.default)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            return value(method, url, headers, body)
        if url == P.OPENFIGI:
            jobs = json.loads(body)
            return 200, {}, json.dumps([{"warning": "No identifier found."} for _ in jobs]).encode()
        return value


ENV = {"TIINGO_API_TOKEN": TOKEN, "SEC_USER_AGENT": "Synthetic test contact@example.invalid"}


def run(tmp_path, fake, *args, environ=None):
    """The real CLI path: memory only, writes the connection record and nothing else."""
    code = CLI.main(["--run", "--report-root", str(tmp_path / "repo"), *args], fetch=fake, environ=ENV if environ is None else environ,
                    prompt=lambda _: "", sleep=lambda s: None, clock=lambda: 1_790_000_000.0)
    return code, json.loads((tmp_path / "repo" / P.ACCESS_JSON).read_text())


def analyze_world(fake, *, sec_user_agent="Synthetic test contact@example.invalid"):
    """The derived analysis the CLI computes and discards, inspected in memory (it is never written)."""
    session = P.Session(fake, token=TOKEN, sec_user_agent=sec_user_agent, sleep=lambda s: None, clock=lambda: 1_790_000_000.0)
    answers = P.acquire(PLAN, session)
    return P.analyze(PLAN, answers, session.records, session.stopped, run_meta={})


def written_files(tmp_path):
    return sorted(p for p in tmp_path.rglob("*") if p.is_file())


# ---- licence: nothing from a Tiingo answer is ever persisted --------------------------------------------------------------------
def test_the_run_writes_only_connection_metadata(tmp_path, capsys):
    fake = Fake(world())
    code, access = run(tmp_path, fake)
    assert code == 0 and written_files(tmp_path) == [tmp_path / "repo" / P.ACCESS_JSON]
    text = (tmp_path / "repo" / P.ACCESS_JSON).read_text()
    for plan_ticker in (e["auditIdentifier"] for e in PLAN["identities"]):
        assert f'"{plan_ticker}"' not in text                            # no per-security outcome of any kind
    for word in ("identities", "sessions", "questions", "newlyRecoverable", "startDate", "endDate", "name"):
        assert f'"{word}"' not in text
    assert access["tiingo"] == {"calls": 41, "reachable": True, "authenticationAccepted": True, "rateLimited": False, "stopped": {},
                                "rateLimitHeaderNames": ["X-RateLimit-Remaining"]}
    assert access["licence"]["historicalPriceRetentionVerdict"] == "NO_GO_STARTER_PROHIBITS_PERSISTENT_STORAGE"
    assert access["licence"]["derivedResultRetention"] == "PROHIBITED_NO_PATH_IN_THIS_FREE_PILOT"
    out = json.loads(capsys.readouterr().out)
    assert out["derived"] == "DISCARDED_NOT_WRITTEN_STARTER_TOS_1_6" and "transient" not in out
    assert TOKEN not in text


def test_there_is_no_retention_option_and_a_permission_file_changes_nothing(tmp_path):
    fake = Fake(world())
    with pytest.raises(SystemExit) as exit_info:                         # argparse rejects the removed option
        CLI.main(["--run", "--report-root", str(tmp_path / "repo"), "--retention-authorization", "x.json"], fetch=fake, environ=ENV)
    assert exit_info.value.code == 2 and fake.calls == [] and written_files(tmp_path) == []
    permission = tmp_path / "repo" / "docs" / "tiingo-permission.json"   # an arbitrary file is never read as provider permission
    permission.parent.mkdir(parents=True)
    permission.write_text(json.dumps({"provider": "Tiingo", "scope": "EVERYTHING", "grantedBy": "anyone"}))
    run(tmp_path, Fake(world()))
    assert written_files(tmp_path) == sorted([permission, tmp_path / "repo" / P.ACCESS_JSON])
    source = (ROOT / "scripts/run_us_tiingo_recovery_pilot.py").read_text() + (ROOT / "pipeline/us_tiingo_recovery_pilot.py").read_text()
    for removed in ("retention_authorization", "retention-authorization", "REPORT_JSON", "REPORT_MD", "--private-dir", "--from-raw", "write_bytes"):
        assert removed not in source, removed


def test_no_provider_answer_byte_reaches_disk(tmp_path):
    run(tmp_path, Fake(world()))
    bodies = [v[2] for v in world().values() if isinstance(v, tuple) and len(v[2]) > 64]
    for path in written_files(tmp_path):
        content = path.read_bytes()
        for body in bodies:
            assert body not in content and body[:64] not in content, path
    assert "raw_dir" not in P.Session.__init__.__code__.co_varnames


def test_the_transient_summary_is_printed_and_never_written(tmp_path, capsys):
    run(tmp_path, Fake(world()), "--show-transient-summary")
    out = json.loads(capsys.readouterr().out)
    assert out["transient"]["retentionClass"] == "TRANSIENT_DISPLAY_ONLY_DO_NOT_SAVE"
    assert out["transient"]["decision"] == "EXPAND_TO_212_FREE_TIER_FEASIBILITY"
    assert written_files(tmp_path) == [tmp_path / "repo" / P.ACCESS_JSON]


def test_connectivity_check_uses_no_token_and_writes_nothing(tmp_path, capsys):
    fake = Fake({}, default=(403, {}, b"no token"))
    assert CLI.main(["--check-connectivity", "--report-root", str(tmp_path / "repo")], fetch=fake, environ={},
                    prompt=lambda _: pytest.fail("no token may be asked for")) == 0
    assert len(fake.calls) == 3 and all("Authorization" not in c["headers"] for c in fake.calls)
    assert json.loads(capsys.readouterr().out)["hosts"] == {"tiingo": "REACHABLE_HTTP_403", "sec": "REACHABLE_HTTP_403", "openfigi": "REACHABLE_HTTP_403"}
    assert written_files(tmp_path) == []

    def blocked(method, url, headers, body):
        raise P.NetworkBlocked("OSError: Tunnel connection failed: 403 Forbidden")
    CLI.main(["--check-connectivity"], fetch=Fake({}, default=blocked), environ={})
    assert set(json.loads(capsys.readouterr().out)["hosts"].values()) == {"BLOCKED_BEFORE_PROVIDER"}


# ---- preview and transport discipline ------------------------------------------------------------------------------------------
def test_preview_makes_no_request_and_writes_nothing(tmp_path, capsys):
    fake = Fake(world())
    assert CLI.main(["--report-root", str(tmp_path / "repo")], fetch=fake, environ={}) == 0
    assert fake.calls == [] and written_files(tmp_path) == []
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "PREVIEW_NO_REQUEST_MADE" and out["writes"] == {"always": P.ACCESS_JSON,
                                                                          "never": "any provider response or anything computed from one"}


def test_the_in_memory_analysis_answers_the_registered_questions_and_the_token_travels_only_in_a_header(tmp_path):
    fake = Fake(world())
    report = analyze_world(fake)
    assert report["liveProviderResponse"] == "TESTED" and report["admission"] == "NOT_ADMITTED"
    assert report["retentionClass"] == "DERIVED_TRANSIENT_ONLY_NEVER_WRITTEN"
    for call in fake.calls:
        assert TOKEN not in call["url"]
        if "api.tiingo.com" in call["url"]:
            assert call["headers"]["Authorization"] == "Token " + TOKEN
        else:
            assert "Authorization" not in call["headers"]
    q = report["questions"]
    assert q["1_identitiesWithTiingoPriceRows"] == 20 and q["7_decision"] == "EXPAND_TO_212_FREE_TIER_FEASIBILITY"
    by = {i["auditIdentifier"]: i for i in report["identities"]}
    assert by["ANDV"]["sessions"]["newlyRecoverableBounds"] == [530, 530] and by["JWN"]["sessions"]["newlyRecoverableBounds"] == [0, 0]
    assert by["AGN"]["identity"]["state"] == "HOLD_TICKER_REUSE_OR_IDENTITY_CONFLICT" and not by["AGN"]["identity"]["countsTowardRecovery"]
    assert by["JWN"]["identity"]["state"] == "INDEPENDENT_IDENTITY_CORROBORATED" and by["JWN"]["identity"]["secCiks"] == ["72333"]
    partial = by["TWX"]["sessions"]
    assert partial["newlyRecoverableBasis"] == "BOUNDS_PRIVATE_SESSION_TABLE_ABSENT" and partial["newlyRecoverableBounds"][0] <= partial["newlyRecoverableBounds"][1]
    assert by["DAY"]["sessions"]["sessionsFrom2024"] == 521
    assert by["ANDV"]["sessions"]["adjustmentStepsExplainedByEvent"] == 1 and by["ANDV"]["sessions"]["adjustmentStepsUnexplained"] == 0
    P.scan_report(report)
    code, _ = run(tmp_path, Fake(world()))
    assert code == 0 and all(TOKEN.encode() not in p.read_bytes() for p in written_files(tmp_path))


@pytest.mark.parametrize("status,outcome", [(401, "AUTH_REJECTED"), (403, "ACCESS_FORBIDDEN"), (429, "RATE_LIMITED"), (503, "PROVIDER_ERROR")])
def test_a_refusal_stops_the_source_without_retry(tmp_path, status, outcome):
    first = PLAN["identities"][0]
    override = {P.tiingo_meta_url(first["auditIdentifier"]): (status, {"Retry-After": "3600"}, b'{"detail":"refused"}')}
    fake = Fake(world(override=override))
    report = analyze_world(fake)
    assert len([c for c in fake.calls if c["url"].startswith(P.TIINGO)]) == 1 and report["stoppedSources"]["tiingo"] == outcome
    assert report["questions"]["7_decision"] == "STOP_SOURCE_NOT_REACHABLE_OR_REFUSED" and report["liveProviderResponse"] == "NOT_TESTED"
    code, access = run(tmp_path, Fake(world(override=override)))
    assert access["tiingo"]["rateLimited"] == (status == 429)
    assert access["tiingo"]["authenticationAccepted"] == (status not in (401, 403)) and access["liveProviderResponse"] == "NOT_TESTED"
    assert code == (2 if status in (401, 403) else 0)


def test_a_network_block_is_reported_and_never_bypassed(tmp_path):
    def blocked(method, url, headers, body):
        raise P.NetworkBlocked("OSError: Tunnel connection failed: 403 Forbidden")
    fake = Fake({}, default=blocked)
    report = analyze_world(fake)
    assert set(report["stoppedSources"].values()) == {"ACCESS_BLOCKED_BEFORE_PROVIDER"}
    assert all(n == 1 for n in report["calls"].values())          # one attempt per source, then stop
    assert report["questions"]["1_identitiesWithTiingoPriceRows"] == 0
    code, access = run(tmp_path, Fake({}, default=blocked))
    assert code == 2 and access["tiingo"]["reachable"] is False and access["liveProviderResponse"] == "NOT_TESTED"


def test_not_found_and_malformed_answers_are_recorded_per_identity():
    a, b = PLAN["identities"][0], PLAN["identities"][1]
    responses = world(override={P.tiingo_meta_url(a["auditIdentifier"]): (404, {}, b'{"detail":"Not found."}'),
                                P.tiingo_prices_url(a["auditIdentifier"], a["expectedPricingWindow"]["first"], a["expectedPricingWindow"]["last"]): (404, {}, b"{}"),
                                P.tiingo_prices_url(b["auditIdentifier"], b["expectedPricingWindow"]["first"], b["expectedPricingWindow"]["last"]): (200, {}, b"<html>oops")})
    report = analyze_world(Fake(responses))
    by = {i["auditIdentifier"]: i for i in report["identities"]}
    assert by[a["auditIdentifier"]]["identity"]["state"] == "NO_TIINGO_RESPONSE"
    assert by[b["auditIdentifier"]]["tiingoPriceResponse"] == "NOT_ANSWERED" and report["parseErrors"]
    assert report["stoppedSources"].get("tiingo") is None                # a per-ticker 404 is an answer, not a refusal


def test_budgets_and_pacing_are_respected():
    sleeps, fake = [], Fake(world())
    session = P.Session(fake, token=TOKEN, sec_user_agent="x@example.invalid", sleep=sleeps.append)
    for _ in range(P.BUDGET["openfigi"] + 3):
        session.request("openfigi", "T", P.OPENFIGI, method="POST", body=b"[]")
    assert session.calls["openfigi"] == P.BUDGET["openfigi"] and session.stopped["openfigi"] == "CALL_BUDGET_EXHAUSTED"
    assert sleeps == [P.PACING_SECONDS["openfigi"]] * (P.BUDGET["openfigi"] - 1)


def test_sec_is_skipped_without_a_contact_user_agent(tmp_path, monkeypatch):
    fake = Fake(world())
    report = analyze_world(fake, sec_user_agent=None)
    assert not any("sec.gov" in c["url"] for c in fake.calls) and report["stoppedSources"]["sec"] == "NOT_RUN_NO_CONTACT_USER_AGENT"
    monkeypatch.setattr(CLI, "sec_user_agent", lambda environ: None)
    _, access = run(tmp_path, Fake(world()), environ={"TIINGO_API_TOKEN": TOKEN})
    assert access["otherSources"]["sec"]["stopped"] == "NOT_RUN_NO_CONTACT_USER_AGENT"


def test_no_token_refuses_before_any_request(tmp_path):
    fake = Fake(world())
    with pytest.raises(P.Refused, match="NO_USABLE_TIINGO_TOKEN"):
        CLI.main(["--run", "--report-root", str(tmp_path / "r")], fetch=fake, environ={}, prompt=lambda _: "")
    assert fake.calls == [] and written_files(tmp_path) == []


def test_an_existing_connection_record_is_not_replaced_without_force_before_any_request(tmp_path):
    run(tmp_path, Fake(world()))
    again = Fake(world())
    with pytest.raises(P.Refused, match="OUTPUT_EXISTS"):
        run(tmp_path, again)
    assert again.calls == []
    assert run(tmp_path, Fake(world()), "--force")[0] == 0


# ---- parsing --------------------------------------------------------------------------------------------------------------------
def test_price_rows_are_validated_and_never_coerced():
    good = rows_for(["2014-01-02", "2014-01-03"])
    bad = [dict(good[0], date="2014-01-04T00:00:00.000Z"),                      # Saturday
           dict(good[0], date="2014-01-06T00:00:00.000Z", close=0),
           dict(good[0], date="2014-01-07T00:00:00.000Z", low=99.0),
           dict(good[0], date="2014-01-08T00:00:00.000Z", splitFactor=0),
           dict(good[0], date="2014-01-09T00:00:00.000Z", volume=None),
           dict(good[1])]                                                          # duplicate of 2014-01-03
    rows, quality = P.parse_prices(json.dumps(good + bad).encode(), set(CALENDAR))
    assert sorted(rows) == ["2014-01-02", "2014-01-09"] and rows["2014-01-09"]["volume"] is None
    assert quality["duplicateDates"] == 1 and quality["invalidRows"] == {"MISSING_OR_NONPOSITIVE_CLOSE": 1, "NONPOSITIVE_SPLIT_FACTOR": 1,
                                                                          "NON_SESSION_DATE": 1, "OHLC_INCONSISTENT": 1}
    with pytest.raises(ValueError, match="PRICES_SCHEMA_UNEXPECTED"):
        P.parse_prices(b'{"detail": "x"}', set(CALENDAR))


def test_an_adjustment_step_without_an_event_is_unexplained():
    rows, _ = P.parse_prices(json.dumps(rows_for(["2014-01-02", "2014-01-03", "2014-01-06"], "2014-01-03")).encode(), set(CALENDAR))
    assert P.adjustment_steps(rows) == (1, 0)
    rows["2014-01-03"]["divCash"] = 0.0
    assert P.adjustment_steps(rows) == (0, 1)


def test_identity_holds_and_disagreements_never_count():
    entry = copy.deepcopy(next(e for e in PLAN["identities"] if e["auditIdentifier"] == "ANDV"))
    w = entry["expectedPricingWindow"]
    no_sec = {"state": "NO_SEC_EVIDENCE", "ciks": []}
    meta = {"name": "Andeavor", "startDate": w["first"], "endDate": w["last"]}
    assert P.identity_verdict(entry, meta, True, no_sec, {}, {})["state"] == "TIINGO_NAME_AND_DATES_ONLY_UNRESOLVED"
    assert P.identity_verdict(entry, dict(meta, name="Another Company Holdings"), True, no_sec, {}, {})["state"] == "HOLD_TIINGO_NAME_OR_DATES_DISAGREE"
    later = dict(meta, startDate="2023-01-01", endDate="2026-01-01")
    assert P.identity_verdict(entry, later, True, no_sec, {}, {})["state"] == "HOLD_TIINGO_NAME_OR_DATES_DISAGREE"
    twice = {"ANDV": [{"assetType": "Stock", "startDate": "2010-01-01", "endDate": "2019-01-01"},
                      {"assetType": "Stock", "startDate": "2019-01-02", "endDate": "2021-01-01"}]}
    verdict = P.identity_verdict(entry, meta, True, no_sec, {}, twice)
    assert verdict["state"] == "HOLD_TICKER_REUSE_OR_IDENTITY_CONFLICT" and not verdict["countsTowardRecovery"]
    held = dict(entry, holdReasons=["SEALED_IDENTITY_HOLD"])
    assert P.identity_verdict(held, meta, True, {"state": "CORROBORATES", "ciks": ["1"]}, {}, {})["state"] == "HOLD_TICKER_REUSE_OR_IDENTITY_CONFLICT"


def test_sec_former_names_must_be_dated_inside_membership():
    entry = next(e for e in PLAN["identities"] if e["auditIdentifier"] == "ANDV")
    inside = {"1": {"name": "Marathon Petroleum", "formerNames": [{"name": "Andeavor", "from": "2017-08-01", "to": "2019-01-01"}], "tickers": []}}
    outside = {"1": {"name": "Marathon Petroleum", "formerNames": [{"name": "Andeavor", "from": "2001-01-01", "to": "2005-01-01"}], "tickers": []}}
    assert P.sec_evidence(entry, inside)["state"] == "CORROBORATES"
    assert P.sec_evidence(entry, outside)["state"] == "NO_NAME_MATCH"
    two = {"1": inside["1"], "2": {"name": "Andeavor", "formerNames": [], "tickers": []}}
    assert P.sec_evidence(entry, two)["state"] == "CONFLICTING_CIKS"


def test_the_existing_session_table_is_verified_by_its_published_digest(tmp_path):
    path = tmp_path / "table.json.gz"
    path.write_bytes(gzip.compress(P.canonical([{"ticker": "TWX", "date": "2014-01-02", "status": "NAME_ONLY"}])))
    with pytest.raises(P.Refused, match="DIGEST_MISMATCH"):
        P.load_existing_table(path)


def test_an_exact_table_turns_bounds_into_a_count():
    entry = next(e for e in PLAN["identities"] if e["auditIdentifier"] == "TWX")
    days = sorted(P.expected_sessions(entry, CALENDAR))
    rows, _ = P.parse_prices(json.dumps(rows_for(days[:100])).encode(), set(CALENDAR))
    out = P.session_comparison(entry, rows, CALENDAR, existing_rows=set(days[:60]))
    assert out["newlyRecoverableBounds"] == [40, 40] and out["newlyRecoverableBasis"] == "EXACT_FROM_PRIVATE_SESSION_TABLE"


def test_the_public_report_refuses_price_like_keys():
    with pytest.raises(ValueError, match="PRICE_LIKE_KEY"):
        P.scan_report({"identities": [{"sessions": {"adjClose": 1.0}}]})


def test_the_engine_and_cli_use_the_standard_library_only():
    allowed = {"__future__", "argparse", "collections", "csv", "datetime", "getpass", "gzip", "hashlib", "inspect", "io", "json", "math", "os", "pathlib",
               "re", "subprocess", "sys", "time", "urllib", "zipfile", "importlib", "pipeline"}
    for rel in ("pipeline/us_tiingo_recovery_pilot.py", "pipeline/us_departed_price_recovery.py", "scripts/run_us_tiingo_recovery_pilot.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        names = {(n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0] for n in top for a in n.names}
        assert names <= allowed, (rel, names - allowed)
