"""The KRX collector's budget, its resumption, and what it refuses to record.

The collector talks to a paid service with an unknown daily quota, over a
decade of dates, and writes into the sealed ledger. Three things must hold or
the shards are worse than nothing:

  * a REFUSAL is never recorded as a fact about the market. An unsubscribed
    key answering every call must not mark a decade of dates done and leave
    behind a store that looks like a finished backfill;
  * a HOLIDAY is resolved forward and dated by the session that happened, not
    by the closed day we asked about;
  * a re-run writes no bytes, so `signal-history` does not gain a commit for
    every scheduled run that found nothing new.

Nothing here touches the network: `call` is replaced, and what the fake
returns is what the real endpoint returned in Probes run #4.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import collect_krx_universe_snapshots as CC  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402


def _market(codes, date, caps=None):
    caps = caps or {}
    return {"OutBlock_1": [
        {"ISU_CD": code, "ISU_NM": f"이름{code}", "BAS_DD": date.replace("-", ""),
         "MKTCAP": str(caps.get(code, 1000 - n)), "LIST_SHRS": "100"}
        for n, code in enumerate(codes)]}


def _fake(responses, log=None):
    """A `call` that serves `responses` by requested date and records the asks."""
    asked = log if log is not None else []

    def call(base, path, params, auth_key, timeout=40):
        date = params["basDd"]
        asked.append(date)
        answer = responses.get(date, {"OutBlock_1": []})
        if isinstance(answer, Exception):
            raise answer
        return answer

    call.asked = asked
    return call


def _collect(tmp_path, targets, responses, monkeypatch, **kwargs):
    call = _fake(responses)
    monkeypatch.setattr(CC, "call", call)
    result = CC.collect(tmp_path, targets, auth_key="k", base="b",
                        top=kwargs.pop("top", 10),
                        max_calls=kwargs.pop("max_calls", 100),
                        max_minutes=kwargs.pop("max_minutes", 10),
                        pace=0.0, log=lambda *a: None, **kwargs)
    result["asked"] = call.asked
    return result


# ---------------------------------------------------------------- refusals

def test_a_refused_call_stops_the_run_and_marks_nothing_done(tmp_path, monkeypatch):
    """The failure this exists to prevent: an unsubscribed key "finishing".

    If a refusal marked its date done, a key that KRX declines would walk the
    whole calendar in seconds, write no shards, and leave a done-set saying
    every date was collected — after which no later run would ever ask again.
    """
    result = _collect(tmp_path, ["2013-01-01", "2013-02-01"],
                      {"20130101": CC.Refused("HTTP 401 — Unauthorized API Call")},
                      monkeypatch)
    assert result["collected"] == []
    assert result["stopped"] and "401" in result["stopped"]
    assert CC.load_done(tmp_path) == {}
    assert not list(tmp_path.glob("krx-universe-*.jsonl.gz"))


def test_a_refusal_after_real_work_keeps_what_was_collected(tmp_path, monkeypatch):
    result = _collect(tmp_path, ["2013-01-01", "2013-02-01"],
                      {"20130101": _market(["000001"], "2013-01-01"),
                       "20130201": CC.Refused("HTTP 429")},
                      monkeypatch)
    assert result["collected"] == ["2013-01-01"]
    assert result["stopped"]
    assert set(CC.load_done(tmp_path)) == {"2013-01-01"}


def test_an_unreadable_payload_stops_rather_than_reading_as_a_closed_market(
        tmp_path, monkeypatch):
    result = _collect(tmp_path, ["2013-01-01"],
                      {"20130101": {"respMsg": "Unauthorized API Call"}},
                      monkeypatch)
    assert result["collected"] == [] and result["stopped"]
    assert CC.load_done(tmp_path) == {}


# ---------------------------------------------------------------- holidays

def test_a_holiday_steps_forward_and_is_dated_by_the_session_that_happened(
        tmp_path, monkeypatch):
    """2013-01-01 is a Korean market holiday; the exchange opened on the 2nd."""
    result = _collect(tmp_path, ["2013-01-01"],
                      {"20130102": _market(["000001", "000002"], "2013-01-02")},
                      monkeypatch)
    assert result["collected"] == ["2013-01-02"]
    assert result["asked"] == ["20130101", "20130102"]
    rows = HS.read_jsonl(tmp_path / "krx-universe-2013.jsonl.gz")
    assert {row["date"] for row in rows} == {"2013-01-02"}


def test_the_holiday_probe_is_charged_to_the_budget(tmp_path, monkeypatch):
    """A closed day costs the quota exactly as a trading day does.

    Not charging it would let a run believe it had spent two calls while the
    service counted eight, which is how a quota is discovered by being hit.
    """
    result = _collect(tmp_path, ["2013-01-01"],
                      {"20130103": _market(["000001"], "2013-01-03")},
                      monkeypatch)
    assert result["calls"] == 3
    assert result["holidays"] == ["2013-01-01", "2013-01-02"]


def test_a_permanently_closed_window_is_marked_done_not_retried_forever(
        tmp_path, monkeypatch):
    result = _collect(tmp_path, ["2013-01-01"], {}, monkeypatch)
    assert result["collected"] == []
    assert CC.load_done(tmp_path) == {"2013-01-01": 10}
    assert result["stopped"] is None


# ---------------------------------------------------------------- budget

def test_the_call_budget_stops_the_run_and_leaves_the_rest_pending(
        tmp_path, monkeypatch):
    targets = ["2013-01-01", "2013-02-01", "2013-03-01"]
    responses = {"20130101": _market(["000001"], "2013-01-01"),
                 "20130201": _market(["000001"], "2013-02-01"),
                 "20130301": _market(["000001"], "2013-03-01")}
    result = _collect(tmp_path, targets, responses, monkeypatch, max_calls=2)
    assert result["collected"] == ["2013-01-01", "2013-02-01"]
    assert result["remaining"] == 1
    assert result["stopped"] and "예산" in result["stopped"]


def test_a_second_run_resumes_where_the_budget_stopped(tmp_path, monkeypatch):
    targets = ["2013-01-01", "2013-02-01"]
    responses = {"20130101": _market(["000001"], "2013-01-01"),
                 "20130201": _market(["000002"], "2013-02-01")}
    _collect(tmp_path, targets, responses, monkeypatch, max_calls=1)
    second = _collect(tmp_path, targets, responses, monkeypatch, max_calls=5)
    assert second["collected"] == ["2013-02-01"]
    assert second["asked"] == ["20130201"]
    assert second["remaining"] == 0


# ---------------------------------------------------------------- the store

def test_a_rerun_that_collects_nothing_new_writes_no_bytes(tmp_path, monkeypatch):
    """`signal-history` must not gain a commit for every scheduled no-op run."""
    targets = ["2013-01-01"]
    responses = {"20130101": _market(["000001", "000002"], "2013-01-01")}
    _collect(tmp_path, targets, responses, monkeypatch)
    shard = tmp_path / "krx-universe-2013.jsonl.gz"
    before = shard.read_bytes()
    second = _collect(tmp_path, targets, responses, monkeypatch)
    assert second["written"] == []
    assert shard.read_bytes() == before


def test_the_same_market_written_twice_produces_identical_bytes(
        tmp_path, monkeypatch):
    responses = {"20130101": _market(["000002", "000001"], "2013-01-01",
                                     caps={"000001": 500, "000002": 500})}
    _collect(tmp_path, ["2013-01-01"], responses, monkeypatch)
    first = (tmp_path / "krx-universe-2013.jsonl.gz").read_bytes()

    other = tmp_path / "again"
    other.mkdir()
    _collect(other, ["2013-01-01"],
             {"20130101": _market(["000001", "000002"], "2013-01-01",
                                  caps={"000001": 500, "000002": 500})},
             monkeypatch)
    assert (other / "krx-universe-2013.jsonl.gz").read_bytes() == first


def test_rows_are_sharded_by_the_year_they_describe(tmp_path, monkeypatch):
    _collect(tmp_path, ["2013-12-01", "2014-01-01"],
             {"20131201": _market(["000001"], "2013-12-01"),
              "20140101": _market(["000001"], "2014-01-01")}, monkeypatch)
    assert sorted(p.name for p in tmp_path.glob("krx-universe-*.jsonl.gz")) == [
        "krx-universe-2013.jsonl.gz", "krx-universe-2014.jsonl.gz"]


# ------------------------------------------------------------- the done-set

def test_raising_top_recollects_dates_taken_at_a_shallower_depth(
        tmp_path, monkeypatch):
    """A decade at two ranking depths spliced together is not one ranking.

    A date collected at top-2 holds no rank-3 issue, so widening the universe
    later would read "absent from the shard" as "did not trade".
    """
    responses = {"20130101": _market(["000001", "000002", "000003"], "2013-01-01")}
    _collect(tmp_path, ["2013-01-01"], responses, monkeypatch, top=2)
    assert CC.load_done(tmp_path) == {"2013-01-01": 2}

    again = _collect(tmp_path, ["2013-01-01"], responses, monkeypatch, top=3)
    assert again["collected"] == ["2013-01-01"]
    rows = HS.read_jsonl(tmp_path / "krx-universe-2013.jsonl.gz")
    assert len(rows) == 3


def test_lowering_top_does_not_recollect(tmp_path, monkeypatch):
    responses = {"20130101": _market(["000001", "000002"], "2013-01-01")}
    _collect(tmp_path, ["2013-01-01"], responses, monkeypatch, top=5)
    again = _collect(tmp_path, ["2013-01-01"], responses, monkeypatch, top=2)
    assert again["collected"] == [] and again["asked"] == []


def test_a_corrupt_done_file_is_read_as_nothing_done(tmp_path):
    (tmp_path / CC.DONE_NAME).write_text("{not json", encoding="utf-8")
    assert CC.load_done(tmp_path) == {}


def test_pending_skips_only_dates_taken_at_the_requested_depth_or_deeper():
    done = {"2013-01-01": 300, "2013-02-01": 100}
    assert CC.pending_dates(["2013-01-01", "2013-02-01", "2013-03-01"],
                            done, 300) == ["2013-02-01", "2013-03-01"]


# ---------------------------------------------------------------- the key

def test_no_key_refuses_to_run_at_all(tmp_path, monkeypatch, capsys):
    """Without a key every call is refused, and a refusal must not be data."""
    monkeypatch.setenv("KRX_API_KEY", "")
    assert CC.main([str(tmp_path)]) == 2
    assert "KRX_API_KEY" in capsys.readouterr().out


# --------------------------------------------------------- the workflow

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _text(name: str) -> str:
    # Read as text, not parsed. Every workflow-contract test here does, because
    # a test that needs `pyyaml` passes locally and fails CI with
    # ModuleNotFoundError — which is how that dependency was discovered missing.
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_the_workflow_collects_into_the_path_the_replay_would_read():
    run = _text("universe.yml")
    assert "scripts/collect_krx_universe_snapshots.py" in run
    assert "universe-work/ledger/universe/kr" in run
    assert "secrets.KRX_API_KEY" in run


def test_every_dispatch_input_defaults_to_empty():
    """A non-empty default is SENT on every dispatch and overrides the ceiling.

    The fundamentals workflow learned this the expensive way: a default in the
    box makes every hand-started run a small one, and the mobile app cannot
    pass inputs at all, so there is no way to override the override.
    """
    text = _text("universe.yml")
    inputs = text.split("workflow_dispatch:", 1)[1].split("permissions:", 1)[0]
    defaults = [line.split("default:", 1)[1].strip()
                for line in inputs.splitlines() if "default:" in line]
    assert defaults, "no dispatch inputs found — the parse is wrong, not the file"
    overridable = [d for d in defaults if d not in ('""', "''")]
    # `frequency` is a choice, not a ceiling: its default picks a shape rather
    # than capping a budget, and a choice input cannot be left empty.
    assert overridable == ['"monthly"'], overridable


def test_reading_the_korean_shards_and_keeping_replay_v15_cannot_both_be_true():
    """The seal, stated as an invariant instead of a snapshot.

    Korean membership rows redefine the Korean cross-section, and
    `universe_conflict` refuses to mix that into a generation that already
    holds Korean records ranked against the survivors-only one. So the commit
    that teaches `replay.yml` to pass `--krx-snapshots` is the commit that must
    bump `REPLAY_VERSION`, and this fails if either happens without the other.

    Today neither has: the collector writes shards nothing reads, which is why
    this branch leaves the v15 seal intact and costs no reacquisition.
    """
    from pipeline import provenance

    wired = "--krx-snapshots" in _text("replay.yml")
    assert wired == (provenance.REPLAY_VERSION != "replay-v15"), (
        f"replay.yml {'passes' if wired else 'does not pass'} --krx-snapshots "
        f"while REPLAY_VERSION is {provenance.REPLAY_VERSION!r}; Korean "
        f"membership needs a new generation, not an extension of v15")
