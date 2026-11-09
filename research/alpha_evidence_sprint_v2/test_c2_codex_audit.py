"""Codex audit (#292 comment 6731937377) counterexamples F1-F6, each re-run against the fixed code.

Every test here is synthetic: no real C2 row, price, NAV or return is read. The only real files
touched are the committed protocol / corrected-ETF file / pipeline modules, read for their hashes.
"""
import json
import math
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from research.alpha_evidence_sprint_v2 import c2_attribution as A
from research.alpha_evidence_sprint_v2 import c2_attribution_run as RUN

OWNER = "jaeho.jung1879@gmail.com"


def git(cwd, *args, email=OWNER, check=True):
    env = {"GIT_AUTHOR_NAME": "x", "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": "x",
           "GIT_COMMITTER_EMAIL": email, "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)}
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)
    if check and done.returncode:
        raise AssertionError(done.stderr)
    return done


# --------------------------------------------------------------------------- #
# F1 authorization and one-shot
# --------------------------------------------------------------------------- #
@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    here = root / "research/alpha_evidence_sprint_v2"
    here.mkdir(parents=True)
    for f in ("c2_attribution.py", "c2_attribution_run.py", "c2-fixed-exposure-attribution-v1.json"):
        shutil.copy(RUN.HERE / f, here / f)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-qm", "code", email="noreply@anthropic.com")
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(root, "remote", "add", "origin", str(remote))
    for name, value in (("ROOT", root), ("HERE", here), ("AUTH", here / "AUTHORIZATION-c2.json"),
                        ("SPEC", here / "c2-fixed-exposure-attribution-v1.json"),
                        ("RESULT", here / "c2-fixed-exposure-attribution-v1-result.json"),
                        ("CLAIM", here / "c2-fixed-exposure-attribution-v1-execution-claim.json")):
        monkeypatch.setattr(RUN, name, value)
    return root


def write_auth(root):
    here = root / "research/alpha_evidence_sprint_v2"
    spec = RUN.sha256(here / "c2-fixed-exposure-attribution-v1.json")
    (here / "AUTHORIZATION-c2.json").write_text(json.dumps({
        "phrase": f"APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 {spec}",
        "codeSha256": {f: RUN.sha256(here / f) for f in ("c2_attribution.py", "c2_attribution_run.py")}}))
    return spec


def test_F1_uncommitted_auditor_created_authorization_is_refused(repo):
    # Codex: an uncommitted JSON with the right phrase and code hashes returned (True, AUTHORIZED)
    spec = write_auth(repo)
    assert RUN.authorization_ok(spec) == (False, "AUTHORIZATION_NOT_COMMITTED")


def test_F1_agent_identity_refused_and_owner_identity_is_only_procedural(repo):
    spec = write_auth(repo)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "auth", email="noreply@anthropic.com")
    assert RUN.authorization_ok(spec)[1] == "AUTHORIZATION_NOT_COMMITTED_BY_OWNER_IDENTITY"


def test_F1_a_forged_owner_email_passes_which_is_why_it_is_not_called_authentication(repo):
    # Honest limit: anyone can set GIT_AUTHOR_EMAIL. The gate says so in its own status.
    spec = write_auth(repo)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "auth (forged identity)", email=OWNER)
    ok, status = RUN.authorization_ok(spec)
    assert ok and status == "AUTHORIZED_PROCEDURAL_OWNER_NOT_AUTHENTICATED"
    assert RUN.OWNER_AUTHENTICATION.startswith("NOT_CRYPTOGRAPHICALLY_VERIFIED")


def test_F1_editing_code_after_approval_is_refused(repo):
    spec = write_auth(repo)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "auth")
    path = repo / "research/alpha_evidence_sprint_v2/c2_attribution.py"
    path.write_text(path.read_text() + "\n# edit\n")
    assert RUN.authorization_ok(spec)[1] == "AUTHORIZED_CODE_HASH_MISMATCH"
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "edit")
    assert RUN.authorization_ok(spec)[1] == "AUTHORIZED_CODE_HASH_MISMATCH"


def test_F1_one_claim_wins_and_every_later_or_other_worktree_attempt_is_refused(repo, tmp_path, monkeypatch):
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert RUN.one_shot_ok(cwd=repo) == (True, "NOT_YET_EXECUTED")
    RUN.claim_execution(head, {"specSha256": "x"}, cwd=repo)
    assert RUN.one_shot_ok(cwd=repo)[1] == "LOCAL_CLAIM_ALREADY_EXISTS"
    with pytest.raises(SystemExit, match="LOCAL_CLAIM_ALREADY_EXISTS"):
        RUN.claim_execution(head, {}, cwd=repo)
    # a second clone (another branch / worktree / machine) sees the remote lock
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(other))
    monkeypatch.setattr(RUN, "ROOT", other)
    monkeypatch.setattr(RUN, "CLAIM", other / "claim.json")
    monkeypatch.setattr(RUN, "RESULT", other / "result.json")
    assert RUN.one_shot_ok(cwd=other)[1] == "REMOTE_EXECUTION_LOCK_EXISTS"
    git(repo, "commit", "-q", "--allow-empty", "-m", "different branch head")
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/elsewhere")
    git(other, "fetch", "-q", "origin", "elsewhere")
    elsewhere = git(other, "rev-parse", "FETCH_HEAD").stdout.strip()
    with pytest.raises(SystemExit, match="REMOTE_EXECUTION_LOCK_NOT_ACQUIRED"):
        RUN.claim_execution(elsewhere, {}, cwd=other)
    assert RUN.remote_lock_refs(cwd=other) == [RUN.LOCK_REF]


def test_F1_two_simultaneous_remote_claims_cannot_both_succeed(repo, tmp_path):
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    clones = []
    for i in range(2):
        c = tmp_path / f"c{i}"
        git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(c))
        git(c, "fetch", "-q", str(repo), head)
        clones.append(c)
    codes, barrier = [], threading.Barrier(2)

    def push(c):
        barrier.wait()
        codes.append(git(c, "push", "origin", f"{head}:{RUN.LOCK_REF}", check=False).returncode)
    threads = [threading.Thread(target=push, args=(c,)) for c in clones]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(codes)[0] == 0 and sorted(codes)[1] != 0


def test_F1_result_written_once_atomically_never_overwritten(tmp_path):
    path = tmp_path / "result.json"
    RUN.write_result_once({"verdict": "A"}, path)
    with pytest.raises(SystemExit, match="RESULT_ALREADY_EXISTS"):
        RUN.write_result_once({"verdict": "B"}, path)
    assert json.loads(path.read_text()) == {"verdict": "A"}
    assert [p.name for p in tmp_path.iterdir()] == ["result.json"]          # no temp left behind


def test_F1_a_crash_before_publication_leaves_no_partial_result(tmp_path, monkeypatch):
    def crash(*a):
        raise OSError("disk died between write and publish")
    monkeypatch.setattr(RUN.os, "link", crash)
    with pytest.raises(OSError):
        RUN.write_result_once({"verdict": "A"}, tmp_path / "result.json")
    assert list(tmp_path.iterdir()) == []                                  # neither result nor temp


def test_F1_readiness_counters_no_longer_claim_an_io_firewall():
    src = Path(RUN.__file__).read_text()
    assert '"returnsRead": 0' not in src and '"fullSavedRowsDeserialized": True' in src


# --------------------------------------------------------------------------- #
# F2 ETF source pinned through the protocol
# --------------------------------------------------------------------------- #
def legacy_c598f14e_check(root, basis_path):
    """The exact #325@c598f14e ETF check: a self-referential hash from the protocol itself."""
    basis = json.loads(basis_path.read_text())["correctedSeries"]
    return RUN.sha256(root / basis["file"]) == basis["sha256"], basis["file"]


def etf_world(tmp_path):
    a = {"correctedBenchmarkQuotes": [{"date": "2020-01-02", "Close": 100.0}, {"date": "2020-01-03", "Close": 101.0}]}
    b = {"correctedBenchmarkQuotes": [{"date": "2020-01-02", "Close": 100.0}, {"date": "2020-01-03", "Close": 150.0}]}
    (tmp_path / "pinned.json").write_text(json.dumps(a))
    (tmp_path / "other.json").write_text(json.dumps(b))
    good = tmp_path / "basis-good.json"
    good.write_text(json.dumps({"correctedSeries": {"file": "pinned.json", "field": "correctedBenchmarkQuotes",
                                                    "sha256": RUN.sha256(tmp_path / "pinned.json")}}))
    bad = tmp_path / "basis-bad.json"
    bad.write_text(json.dumps({"correctedSeries": {"file": "other.json", "field": "correctedBenchmarkQuotes",
                                                   "sha256": RUN.sha256(tmp_path / "other.json")}}))
    spec = {"pinnedInputs": {"files": [{"path": "pinned.json", "sha256": RUN.sha256(tmp_path / "pinned.json")}]},
            "etfSeries": {"protocolSha256": RUN.sha256(good), "file": "pinned.json",
                          "field": "correctedBenchmarkQuotes", "sha256": RUN.sha256(tmp_path / "pinned.json")}}
    return spec, good, bad


def test_F2_codex_redirect_counterexample_passed_before_and_is_refused_now(tmp_path):
    spec, good, bad = etf_world(tmp_path)
    # BEFORE: pinned file A unchanged, protocol picks B, the old check passes on B
    assert legacy_c598f14e_check(tmp_path, bad) == (True, "other.json")
    # AFTER
    assert RUN.resolve_etf_series(spec, good, tmp_path) == {"2020-01-02": 100.0, "2020-01-03": 101.0}
    with pytest.raises(SystemExit, match="BASIS_PROTOCOL_CHANGED"):
        RUN.resolve_etf_series(spec, bad, tmp_path)
    # even if someone also re-pins the protocol hash, the registered file/field still decide
    with pytest.raises(SystemExit, match="ETF_SOURCE_REDIRECTED"):
        RUN.resolve_etf_series({**spec, "etfSeries": {**spec["etfSeries"], "protocolSha256": RUN.sha256(bad)}},
                               bad, tmp_path)


def test_F2_edited_or_duplicated_etf_rows_are_refused(tmp_path):
    spec, good, _ = etf_world(tmp_path)
    data = json.loads((tmp_path / "pinned.json").read_text())
    data["correctedBenchmarkQuotes"].append({"date": "2020-01-03", "Close": 101.0})   # a doubled row
    (tmp_path / "pinned.json").write_text(json.dumps(data))
    with pytest.raises(SystemExit, match="ETF_SERIES_CHANGED"):
        RUN.resolve_etf_series(spec, good, tmp_path)
    spec["etfSeries"]["sha256"] = spec["pinnedInputs"]["files"][0]["sha256"] = RUN.sha256(tmp_path / "pinned.json")
    with pytest.raises(SystemExit, match="ETF_SERIES_MALFORMED"):
        RUN.resolve_etf_series(spec, good, tmp_path)


def test_F2_real_registered_series_resolves_and_matches_every_pin():
    spec = json.loads(RUN.SPEC.read_text())
    series = RUN.resolve_etf_series(spec)
    assert len(series) == 3612 and min(series) == "2012-01-02" and max(series) == "2026-09-14"
    basis_pin = {i["path"]: i["sha256"] for i in spec["pinnedInputs"]["files"]}
    assert basis_pin[str(RUN.BASIS.relative_to(RUN.ROOT))] == spec["etfSeries"]["protocolSha256"]


def test_F2_cost_calendar_and_valuation_code_are_bound(tmp_path):
    spec = json.loads(RUN.SPEC.read_text())
    assert RUN.verify_dependency_closure(spec) == spec["dependencyClosure"]["files"]
    assert "pipeline/weekly_decision.py" in spec["dependencyClosure"]["files"]
    assert "pipeline/portfolio_validation.py" in spec["dependencyClosure"]["files"]   # dated cost policy
    assert "pipeline/replay_calendar.py" in spec["dependencyClosure"]["files"]
    root = tmp_path / "r"
    shutil.copytree(RUN.ROOT / "pipeline", root / "pipeline")
    (root / "research/alpha_evidence_sprint_v2").mkdir(parents=True)
    shutil.copy(RUN.HERE / "c2_attribution_run.py", root / "research/alpha_evidence_sprint_v2/")
    assert RUN.verify_dependency_closure(spec, root)
    p = root / "pipeline/weekly_decision.py"
    p.write_text(p.read_text().replace("ETF_SELL_TAX_BPS", "ETF_SELL_TAX_BPS", 1) + "\n# cost edit\n")
    with pytest.raises(SystemExit, match="SEALED_DEPENDENCY_CHANGED pipeline/weekly_decision.py"):
        RUN.verify_dependency_closure(spec, root)


# --------------------------------------------------------------------------- #
# F3 missingness keeps the time axis
# --------------------------------------------------------------------------- #
def legacy_newey_west(series, lag):
    """#316 / c598f14e estimator: drops missing slots, so blocks k apart look adjacent."""
    return A.newey_west([x for x in series if x is not None], lag)


def test_F3_92_of_100_unattributable_blocks_is_insufficient_not_negative():
    from research.alpha_evidence_sprint_v2.test_c2_attribution_run import _world
    rows, etf_px, pre = _world(n=100, seed=4)
    for r in rows[:92]:
        r["grossReturn"] += 0.05                    # saved-row identity fails
    out = RUN.analyse(rows, lambda d: etf_px[d], pre, lambda *a: 0.001, 100 * 21 / 252)
    assert out["unattributableShare"] == pytest.approx(0.92)
    assert out["verdict"] == "SOURCE_OR_SAMPLE_INSUFFICIENT"


def test_F3_single_and_consecutive_beta_gaps_keep_slots_and_never_restart():
    from research.alpha_evidence_sprint_v2.test_c2_attribution_run import _world
    for gaps in ([20], [20, 21, 22]):
        rows, etf_px, pre0 = _world(n=40)

        def pre(t, signal, pre0=pre0, gaps=gaps):
            s, e = pre0(t, signal)
            return ([], e) if int(signal[1:]) in gaps else (s, e)
        out = RUN.analyse(rows, lambda d: etf_px[d], pre, lambda *a: 0.001, 40 * 21 / 252)
        one = out["byCost"]["1x"]
        nw = one["scenarios"]["ZERO"]["selectionAnnualized"]
        assert nw["slots"] == 40 and nw["missingSlots"] == len(gaps)
        assert one["c2"]["status"] == "COMPLETE"                       # C2 / ETF still valued
        assert one["scenarios"]["ZERO"]["controlCagr"] is None           # no restarted control


def test_F3_compressing_missing_slots_changes_the_hac_variance():
    rng = __import__("random").Random(2)
    series = []
    for t in range(60):
        series.append(None if t in (10, 11, 12, 30) else (0.02 if (t // 4) % 2 else -0.02) + rng.gauss(0, 0.005))
    kept = A.newey_west(series, 5)
    old = legacy_newey_west(series, 5)
    assert kept["mean"] == pytest.approx(old["mean"])
    assert abs(kept["se"] - old["se"]) > 1e-4                       # the lag structure mattered
    full = [x for x in series if x is not None]
    assert A.newey_west(full, 5)["se"] == pytest.approx(old["se"])   # identical when nothing is missing


def test_F3_unestimable_lag_refuses_inference():
    series = [0.01, None] * 30          # every odd lag has zero jointly observed pairs
    out = A.newey_west(series, 5)
    assert out["pairsByLag"][1] == 0 and out["ci95"] is None
    v = {"mean": None, "ci95": None, "mean2x": 0.01, "netCi95": None}
    assert A.verdict({k: v for k in A.CASH_SCENARIOS}) == "SOURCE_OR_SAMPLE_INSUFFICIENT"


# --------------------------------------------------------------------------- #
# F4 ETF cost basis
# --------------------------------------------------------------------------- #
def test_F4_identical_all_etf_books_have_zero_net_difference():
    blocks = [A.Block(f"2020-0{i + 1}-02", f"2020-0{i + 2}-02", "s", {}, {}, {}, 1.0, {k: 1.0 for k in A.CASH_SCENARIOS},
                      21 / 252) for i in range(3)]
    results = RUN.attribute_all(blocks)
    fee = (lambda as_of, side, is_etf: 0.01 if side == "buy" else 0.02)
    c2_net, ctrl = RUN.path_returns(blocks, results, fee)
    etf_net = RUN.etf_path(blocks, fee)
    assert c2_net[0] == pytest.approx(-0.01) == etf_net[0] == ctrl["ZERO"][0]
    assert [c - e for c, e in zip(c2_net, etf_net)] == pytest.approx([0, 0, 0], abs=1e-15)
    assert c2_net[1:] == pytest.approx([0, 0], abs=1e-15)               # no repeated cost while held


def test_net_cost_term_uses_funded_growth_not_fee_rates():
    # Codex: RC=.16, RE=.10, cC=.01, cE=.005 -> exact net gap .0539, not .055
    block = A.Block("2020-01-02", "2020-02-03", "s", {"A": 1.0}, {"A": 1.16}, {"A": 1.0}, 1.10,
                    {k: 1.0 for k in A.CASH_SCENARIOS}, 21 / 252)
    res = A.attribute_block(block)
    c2_net, etf_net = [0.99 * 1.16 - 1], [0.995 * 1.10 - 1]
    d = RUN.decomposition([block], [res], c2_net, {k: [math.nan] for k in A.CASH_SCENARIOS}, etf_net, 1.0,
                          [0.01], None, [0.005])["ZERO"]
    assert d["arithmeticC2MinusEtfPpPerYear"] == pytest.approx(5.39, abs=1e-9)
    assert d["costVsEtfPpPerYear"] == pytest.approx(-0.61, abs=1e-9) and d["maxResidualVsEtf"] < 1e-15


# --------------------------------------------------------------------------- #
# F5 clipping
# --------------------------------------------------------------------------- #
def test_F5_codex_clip_example_is_split_into_theoretical_selection_and_transfer():
    # s=.6, b=2, RE=.10, RF=.02, RS=.20
    block = A.Block("2020-01-02", "2020-02-03", "s", {"A": 0.6}, {"A": 1.20}, {"A": 2.0}, 1.10,
                    {"ZERO": 1.02}, 21 / 252)
    r = A.attribute_block(block)
    v = r.by_cash["ZERO"]
    assert r.target_equity == pytest.approx(1.6) and r.control_equity == 1.0
    assert r.c2_gross == pytest.approx(0.16)
    assert v["selection"] == pytest.approx(0.06)                    # registered, vs investable twin
    assert v["selectionUnclipped"] == pytest.approx(0.012)          # beta-matched, theoretical
    assert v["clipTransfer"] == pytest.approx(0.048)                # unmatched market exposure
    assert v["selectionUnclipped"] + v["clipTransfer"] + v["exposure"] == pytest.approx(r.c2_gross - 0.10)
    assert v["selectionUnclipped"] + v["exposureUnclipped"] == pytest.approx(r.c2_gross - 0.10)


def test_F5_r4_refuses_survival_carried_by_the_clip():
    clipped_only = {"mean": 0.02, "ci95": [0.001, 0.04], "mean2x": 0.01, "netCi95": [0.0005, 0.03],
                    "unclippedCi95": [-0.01, 0.02]}
    per = {k: clipped_only for k in A.CASH_SCENARIOS}
    assert A.verdict(per) == "SELECTION_SURVIVES_FIXED_EXPOSURE"                       # without R4
    assert A.verdict(per, require_unclipped=True) == "NO_SELECTION_EVIDENCE_CI_CONTAINS_ZERO"
    spec = json.loads(RUN.SPEC.read_text())
    assert spec["decisionRule"]["requireUnclippedSelection"] is True


# --------------------------------------------------------------------------- #
# F6 net-of-cost significance
# --------------------------------------------------------------------------- #
def test_F6_codex_24_block_example_no_longer_survives():
    bpy = 12.0
    gross = [0.0001 * bpy] * 24
    net = [0.0001 * bpy] * 23 + [-0.001076 * bpy]
    g, n = A.newey_west(gross, 5), A.newey_west(net, 5)
    assert g["ci95"][0] > 0 and n["ci95"][0] < 0 < n["ci95"][1]
    v = {"mean": g["mean"], "ci95": g["ci95"], "mean2x": 0.000024, "netCi95": n["ci95"], "unclippedCi95": g["ci95"]}
    per = {k: v for k in A.CASH_SCENARIOS}
    assert A.verdict(per, require_unclipped=True) == "NO_SELECTION_EVIDENCE_CI_CONTAINS_ZERO"
    # the conjunction: one cash scenario failing net is enough to refuse SURVIVES
    good = {**v, "netCi95": [0.0001, 0.002]}
    assert A.verdict({k: good for k in A.CASH_SCENARIOS}, require_unclipped=True) == "SELECTION_SURVIVES_FIXED_EXPOSURE"
    assert A.verdict({**{k: good for k in A.CASH_SCENARIOS}, "ZERO": v}, require_unclipped=True) \
        == "NO_SELECTION_EVIDENCE_CI_CONTAINS_ZERO"
    assert A.verdict({k: {**good, "mean2x": -1e-6} for k in A.CASH_SCENARIOS}, require_unclipped=True) \
        == "NO_SELECTION_EVIDENCE_CI_CONTAINS_ZERO"


# --------------------------------------------------------------------------- #
# F1 re-audit: same-OID remote claim race (Codex comment 6732427458)
# --------------------------------------------------------------------------- #
def two_clones(repo, tmp_path, monkeypatch):
    """A bare remote and clones a/b at the SAME commit, each with its own local claim file."""
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    clones = {}
    for name in ("a", "b"):
        c = tmp_path / name
        git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(c))
        git(c, "fetch", "-q", str(repo), head)
        clones[name] = c
    return head, clones


def claim_from(clone, head, monkeypatch):
    monkeypatch.setattr(RUN, "CLAIM", clone / "claim.json")
    monkeypatch.setattr(RUN, "RESULT", clone / "result.json")
    monkeypatch.setattr(RUN, "ROOT", clone)
    return RUN.claim_execution(head, {"specSha256": "x"}, cwd=clone)


def test_F1_same_head_two_clones_sequential_second_claim_is_rejected(repo, tmp_path, monkeypatch):
    head, c = two_clones(repo, tmp_path, monkeypatch)
    # Codex interleaving: both pre-check before either claims
    for clone in c.values():
        monkeypatch.setattr(RUN, "ROOT", clone)
        monkeypatch.setattr(RUN, "CLAIM", clone / "claim.json")
        monkeypatch.setattr(RUN, "RESULT", clone / "result.json")
        assert RUN.one_shot_ok(cwd=clone) == (True, "NOT_YET_EXECUTED")
    first = claim_from(c["a"], head, monkeypatch)
    with pytest.raises(SystemExit, match="REMOTE_EXECUTION_LOCK_NOT_ACQUIRED"):
        claim_from(c["b"], head, monkeypatch)            # same OID commit: must now fail
    remote = tmp_path / "remote.git"
    assert git(remote, "rev-parse", RUN.LOCK_REF).stdout.strip() == first["claimTagObject"]
    assert git(remote, "cat-file", "-t", RUN.LOCK_REF).stdout.strip() == "tag"


def test_F1_old_same_oid_push_succeeded_twice_which_is_the_codex_counterexample(repo, tmp_path):
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    ref = RUN.LOCK_REF
    clones = []
    for n in ("a", "b"):
        c = tmp_path / f"old{n}"
        git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(c))
        git(c, "fetch", "-q", str(repo), head)
        clones.append(c)
    # the c598f14e / 4b694611 primitive: push the commit itself
    assert git(clones[0], "push", "origin", f"{head}:{ref}", check=False).returncode == 0
    assert git(clones[1], "push", "origin", f"{head}:{ref}", check=False).returncode == 0   # also succeeds


def test_F1_different_commit_second_claim_is_rejected(repo, tmp_path, monkeypatch):
    head, c = two_clones(repo, tmp_path, monkeypatch)
    claim_from(c["a"], head, monkeypatch)
    git(c["b"], "commit", "-q", "--allow-empty", "-m", "other")
    other = git(c["b"], "rev-parse", "HEAD").stdout.strip()
    with pytest.raises(SystemExit, match="REMOTE_EXECUTION_LOCK_NOT_ACQUIRED"):
        claim_from(c["b"], other, monkeypatch)


def test_F1_each_attempt_makes_a_distinct_tag_object_for_the_same_commit(repo):
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    objects = {RUN._make_claim_tag(head, "body", f"n{i}", cwd=repo) for i in range(5)}
    assert len(objects) == 5
    assert RUN._make_claim_tag(head, "body", "n0", cwd=repo) in objects     # same nonce+second: same object
    assert all(git(repo, "cat-file", "-t", o).stdout.strip() == "tag" for o in objects)


def test_F1_simultaneous_same_head_claims_exactly_one_wins(repo, tmp_path, monkeypatch):
    head, c = two_clones(repo, tmp_path, monkeypatch)
    results, barrier = [], threading.Barrier(2)

    def attempt(name):
        clone = c[name]
        tag = RUN._make_claim_tag(head, f"body-{name}", f"nonce-{name}", cwd=clone)
        barrier.wait()
        results.append(git(clone, "push", "origin", f"{tag}:{RUN.LOCK_REF}", check=False).returncode)
    threads = [threading.Thread(target=attempt, args=(n,)) for n in c]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results)[0] == 0 and sorted(results)[1] != 0


def test_F1_readback_refuses_a_remote_that_accepted_another_claims_ref(repo, tmp_path, monkeypatch):
    head, c = two_clones(repo, tmp_path, monkeypatch)
    real = RUN._git

    def lying_remote(*args, cwd=None):
        if args and args[0] == "ls-remote" and RUN.LOCK_REF in args:
            return "0" * 40 + f"\t{RUN.LOCK_REF}\n"          # someone else's object holds the ref
        return real(*args, cwd=cwd)
    monkeypatch.setattr(RUN, "_git", lying_remote)
    with pytest.raises(SystemExit, match="REMOTE_EXECUTION_LOCK_HELD_BY_ANOTHER_CLAIM"):
        claim_from(c["a"], head, monkeypatch)


def test_F1_claim_leaves_no_phase_c_ref_and_uses_only_the_study_ref(repo, tmp_path, monkeypatch):
    head, c = two_clones(repo, tmp_path, monkeypatch)
    claim_from(c["a"], head, monkeypatch)
    refs = git(tmp_path / "remote.git", "for-each-ref", "--format=%(refname)").stdout.split()
    assert [r for r in refs if r.startswith("refs/tags/")] == [RUN.LOCK_REF]
    assert RUN.LOCK_REF_PREFIX.startswith("refs/tags/c2-fixed-exposure-attribution-v1")
