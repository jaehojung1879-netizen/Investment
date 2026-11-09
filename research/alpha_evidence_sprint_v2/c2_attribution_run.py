"""Runner for c2-fixed-exposure-attribution-v1.

    python research/alpha_evidence_sprint_v2/c2_attribution_run.py readiness --out <file>
    python research/alpha_evidence_sprint_v2/c2_attribution_run.py preflight <ledger_dir> --out <file>
    python research/alpha_evidence_sprint_v2/c2_attribution_run.py execute <ledger_dir>

``preflight`` is OUTCOME-FREE too: it verifies the replay-v16 manifest and every pinned file and
counts, per saved block, whether the registered beta window and the ETF block ends are present.
It computes no return and no beta.

``execute`` writes only ``c2-fixed-exposure-attribution-v1-result.json`` beside this file and
refuses when that result already exists on disk or in git history (one shot).

``readiness`` is OUTCOME-FREE: from the saved C2 ledger it reads only dates, tickers and
TARGET weights (never a NAV, a return or a terminal weight), plus file hashes and source
coverage dates. It may run at any time.

``execute`` reads realised C2 outcomes and pre-signal prices. It refuses unless
``research/alpha_evidence_sprint_v2/AUTHORIZATION-c2.json`` exists, was committed by the
owner, and states exactly::

    APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 <spec sha256>

together with the sha256 of this file and of ``c2_attribution.py``. The Phase D closure
(docs/kr-alpha-research-final-development-assessment.md §7) forbids new KR historical
outcome work without such an owner decision; this runner cannot bypass it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from research.alpha_evidence_sprint_v2 import c2_attribution as A  # noqa: E402

SPEC = HERE / "c2-fixed-exposure-attribution-v1.json"
AUTH = HERE / "AUTHORIZATION-c2.json"
STANDALONE = ROOT / "docs/results/regional-standalone-paths.json.gz"
REPLAY = ROOT / "docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json"
BASIS = ROOT / "docs/weekly-decision/weekly-passive-first-v1-benchmark-basis-protocol.json"
BOK = ROOT / "data/bok-policy-rates.json"
TERMINATED = ROOT / "docs/results/kr-termination-inventory.json"
ETF = "069500.KS"
# Only these keys of a saved block are read in readiness mode. Everything else in the
# row (NAVs, returns, terminal weights, costs) is an outcome and is not touched.
READINESS_KEYS = ("date", "endDate", "signalDate", "weights", "selectedTickers", "corporateActionsApplied")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(projection=None):
    data = json.loads(gzip.decompress(STANDALONE.read_bytes()))
    rows = data["regional"]["KR"]
    if projection:
        rows = [{k: r.get(k) for k in projection} for r in rows]
    return rows


# --------------------------------------------------------------------------- #
# readiness (outcome-free)
# --------------------------------------------------------------------------- #
def readiness() -> dict:
    rows = load_rows(READINESS_KEYS)
    replay = json.loads(REPLAY.read_text())
    basis = json.loads(BASIS.read_text())["correctedSeries"]
    corrected = ROOT / basis["file"]
    bok = json.loads(BOK.read_text())
    terminated = {s["code"]: s for s in json.loads(TERMINATED.read_text())["securities"]}
    calendar = replay["calendar"]
    held = {}
    stock_blocks = 0
    for r in rows:
        if r["weights"]:
            stock_blocks += 1
        for t in r["weights"]:
            held.setdefault(t, []).append(r["date"])
    held_terminated = {t: {"blocks": len(d), "firstHeld": d[0], "lastHeld": d[-1],
                           "lastTradingDate": terminated[t].get("lastTradingDate"),
                           "terminationType": terminated[t].get("terminationType"),
                           "terminalConsiderationResolved":
                               (terminated[t].get("completeness") or {}).get("terminalConsiderationResolved")}
                       for t, d in sorted(held.items()) if t in terminated}
    names_per_block = [len(r["weights"]) for r in rows]
    stock_weight = [round(sum(r["weights"].values()), 6) for r in rows]
    return {
        "study": "c2-fixed-exposure-attribution-v1",
        "mode": "READINESS_OUTCOME_FREE",
        "readKeysOnly": list(READINESS_KEYS),
        "inputs": {
            "regionalStandalonePaths": {"path": str(STANDALONE.relative_to(ROOT)), "sha256": sha256(STANDALONE)},
            "weeklyReplay": {"path": str(REPLAY.relative_to(ROOT)), "sha256": sha256(REPLAY),
                             "inputManifestSha256": replay["inputManifestSha256"],
                             "regionalPathsSha256": replay["regionalPathsSha256"]},
            "correctedEtfSeries": {"path": basis["file"], "pinnedSha256": basis["sha256"],
                                   "actualSha256": sha256(corrected) if corrected.exists() else None,
                                   "definition": basis["definition"]},
            "bokPolicyRate": {"path": str(BOK.relative_to(ROOT)), "sha256": sha256(BOK), "basis": bok["basis"],
                              "verifiedThrough": bok["verifiedThrough"], "events": len(bok["events"]),
                              "firstEvent": bok["events"][0]["date"]},
            "terminationInventory": {"path": str(TERMINATED.relative_to(ROOT)), "sha256": sha256(TERMINATED)},
        },
        "blocks": len(rows),
        "calendarBlocks": calendar["blocks"],
        "calendarFirst": calendar["first"], "calendarLast": calendar["last"],
        "blocksWithStocks": stock_blocks,
        "namesPerBlock": {str(n): names_per_block.count(n) for n in sorted(set(names_per_block))},
        "targetStockWeight": {"min": min(stock_weight), "max": max(stock_weight)},
        "distinctNamesHeld": len(held),
        "heldTickers": sorted(held),
        "heldTerminatedSecurities": held_terminated,
        "blocksWithCorporateActionsApplied": sum(1 for r in rows if r["corporateActionsApplied"]),
        # Honest counters (Codex F1): load_rows() decompresses and parses the WHOLE saved file,
        # outcome fields included, and only then projects to READINESS_KEYS. Outcome values are
        # therefore deserialized into memory but never used; this is not an I/O firewall.
        "fullSavedRowsDeserialized": True, "outcomeValuesUsed": 0, "returnsComputed": 0,
    }


# --------------------------------------------------------------------------- #
# execute (owner-gated)
# --------------------------------------------------------------------------- #
OWNER_AUTHOR_EMAIL = "jaeho.jung1879@gmail.com"   # the repository owner's commit identity (git log)
AGENT_AUTHOR_EMAILS = ("noreply@anthropic.com",)
RESULT = HERE / "c2-fixed-exposure-attribution-v1-result.json"
CLAIM = HERE / "c2-fixed-exposure-attribution-v1-execution-claim.json"
LOCK_REF_PREFIX = "refs/tags/c2-fixed-exposure-attribution-v1-execution"
LOCK_REF = LOCK_REF_PREFIX + "-claim"
REMOTE = "origin"
GATED_FILES = ("c2_attribution.py", "c2_attribution_run.py", "c2-fixed-exposure-attribution-v1.json",
               "AUTHORIZATION-c2.json")
# What the authorization can and cannot prove (Codex F1). Git author identity is self-asserted and
# in this project agents commit and comment through the owner's own GitHub account, so no check
# here can tell the Owner from an agent holding the Owner's credentials. The gate below is a
# PROCEDURAL binding of exact hashes to a committed, unmodified file; the Owner's approval itself
# must additionally be confirmed by the Owner in person (the conversation), and is reported so.
OWNER_AUTHENTICATION = ("NOT_CRYPTOGRAPHICALLY_VERIFIED: git author identity is self-asserted and agents act "
                        "through the owner's GitHub account; Owner approval needs the Owner's own manual "
                        "confirmation in addition to this procedural gate")


def _git(*args, cwd=None) -> str:
    import subprocess
    done = subprocess.run(["git", "-C", str(cwd or ROOT), *args], capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(done.stderr.strip() or "git failed")
    return done.stdout


def authorization_ok(spec_sha: str, *, check_git: bool = True) -> tuple[bool, str]:
    """The procedural exact-hash approval: bound to the spec, both code files and a commit.

    ``check_git`` is only switched off by synthetic tests. In the real gate the authorization
    file must be committed (not merely present), every commit touching it must carry the
    owner's author identity and no agent's, and the gated files must be unmodified relative to
    HEAD, so the hashes approved are the bytes that run. This does NOT authenticate the Owner
    (see OWNER_AUTHENTICATION)."""
    if not AUTH.exists():
        return False, "NO_OWNER_AUTHORIZATION_FILE"
    auth = json.loads(AUTH.read_text())
    phrase = f"APPROVE KR_PHASE_D_EXCEPTION c2-fixed-exposure-attribution-v1 {spec_sha}"
    if auth.get("phrase") != phrase:
        return False, "AUTHORIZATION_PHRASE_MISMATCH"
    want = {"c2_attribution.py": sha256(HERE / "c2_attribution.py"),
            "c2_attribution_run.py": sha256(HERE / "c2_attribution_run.py")}
    if auth.get("codeSha256") != want:
        return False, "AUTHORIZED_CODE_HASH_MISMATCH"
    if not check_git:
        return True, "AUTHORIZED_SYNTHETIC"
    rel = [str((HERE / f).relative_to(ROOT)) for f in GATED_FILES]
    try:
        tracked = _git("ls-files", "--", rel[-1]).strip()
    except RuntimeError as error:
        return False, f"GIT_UNAVAILABLE:{error}"
    if tracked != rel[-1]:
        return False, "AUTHORIZATION_NOT_COMMITTED"
    try:
        if _git("status", "--porcelain", "--", *rel).strip():
            return False, "GATED_FILES_MODIFIED_SINCE_COMMIT"
        authors = _git("log", "--format=%ae", "--", rel[-1]).split()
    except RuntimeError as error:
        return False, f"GIT_UNAVAILABLE:{error}"
    if not authors or any(a != OWNER_AUTHOR_EMAIL or a in AGENT_AUTHOR_EMAILS for a in authors):
        return False, "AUTHORIZATION_NOT_COMMITTED_BY_OWNER_IDENTITY"
    return True, "AUTHORIZED_PROCEDURAL_OWNER_NOT_AUTHENTICATED"


def remote_lock_refs(remote=REMOTE, cwd=None) -> list[str]:
    """Every ref under the study's lock prefix on the remote (any branch, any worktree, any spec)."""
    out = _git("ls-remote", remote, LOCK_REF_PREFIX + "*", cwd=cwd)
    # an annotated tag is listed twice (the tag and its peeled "^{}" commit): one ref, listed once
    return sorted({line.split()[1].removesuffix("^{}") for line in out.splitlines() if line.strip()})


def one_shot_ok(remote=REMOTE, cwd=None) -> tuple[bool, str]:
    """The study runs once: refuse when its result or claim exists locally, the result is in any
    local git history, or ANY lock ref exists on the remote (Codex F1)."""
    if RESULT.exists():
        return False, "RESULT_ALREADY_EXISTS"
    if CLAIM.exists():
        return False, "LOCAL_CLAIM_ALREADY_EXISTS"
    try:
        if _git("log", "--all", "--format=%H", "--", str(RESULT.relative_to(ROOT)), cwd=cwd).strip():
            return False, "RESULT_ALREADY_IN_GIT_HISTORY"
        if remote_lock_refs(remote, cwd):
            return False, "REMOTE_EXECUTION_LOCK_EXISTS"
    except RuntimeError as error:
        return False, f"GIT_UNAVAILABLE:{error}"
    return True, "NOT_YET_EXECUTED"


def _make_claim_tag(commit: str, body: str, nonce: str, cwd=None) -> str:
    """Create a UNIQUE annotated tag object (not a ref) naming ``commit`` and carrying a nonce.

    Two callers claiming the same commit used to push the same commit OID to the same ref, which
    Git treats as an up-to-date success for the second caller (Codex F1 re-audit). A tag object
    whose message carries a fresh nonce has a different OID for every attempt, so the second
    push is a real non-fast-forward update of an existing tag ref and is rejected."""
    # A fixed claim identity: the tag must not depend on any machine's git user.name/email (a CI
    # runner or a fresh checkout has none). Uniqueness comes from the nonce, not the tagger.
    import time
    ident = f"c2-execution-claim <c2-execution-claim@invalid> {int(time.time())} +0000"
    text = (f"object {commit}\ntype commit\ntag {LOCK_REF.rsplit('/', 1)[-1]}\ntagger {ident}\n\n"
            f"c2-fixed-exposure-attribution-v1 execution claim\nnonce: {nonce}\n{body}")
    import subprocess
    done = subprocess.run(["git", "-C", str(cwd or ROOT), "mktag"], input=text, capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"REFUSED: CLAIM_TAG_NOT_CREATED:{done.stderr.strip()}")
    return done.stdout.strip()


def claim_execution(commit: str, record: dict, remote=REMOTE, cwd=None) -> dict:
    """Atomically take the one execution right, BEFORE any outcome is read.

    1. a local claim file created with O_CREAT|O_EXCL (two processes in one worktree: one wins);
    2. a remote annotated tag whose OBJECT is unique to this attempt (random nonce), created by
       a non-forced push. Even for the same commit, the loser's tag object differs from the
       winner's, so Git rejects the push instead of reporting an identical ref as up to date.
    3. a read-back: the remote ref must now equal THIS attempt's tag object, otherwise the claim
       is refused (defence in depth against any server that accepts the push anyway).
    Once the remote ref exists the study is CONSUMED, whatever happens next; nothing deletes it.
    A study-specific ref; no Phase C lock is read, reused or moved."""
    import uuid
    nonce = uuid.uuid4().hex
    body = (json.dumps({**record, "commit": commit, "lockRef": LOCK_REF, "nonce": nonce},
                       sort_keys=True) + "\n")
    try:
        fd = os.open(CLAIM, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        raise SystemExit("REFUSED: LOCAL_CLAIM_ALREADY_EXISTS") from None
    with os.fdopen(fd, "wb") as handle:
        handle.write(body.encode())
        handle.flush()
        os.fsync(handle.fileno())
    tag = _make_claim_tag(commit, body, nonce, cwd)
    try:
        _git("push", remote, f"{tag}:{LOCK_REF}", cwd=cwd)
    except RuntimeError as error:
        raise SystemExit(f"REFUSED: REMOTE_EXECUTION_LOCK_NOT_ACQUIRED:{error}") from error
    held = _git("ls-remote", remote, LOCK_REF, cwd=cwd).split()
    if not held or held[0] != tag:
        raise SystemExit("REFUSED: REMOTE_EXECUTION_LOCK_HELD_BY_ANOTHER_CLAIM")
    return {"lockRef": LOCK_REF, "commit": commit, "claimTagObject": tag, "nonce": nonce,
            "claimFile": str(CLAIM.name)}


def write_result_once(payload: dict, path: Path | None = None) -> Path:
    """Write the single result file atomically and never over an existing one: temp file
    (O_EXCL) + fsync, then os.link to the final name, which fails if it exists."""
    path = Path(path or RESULT)
    data = (json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n").encode()
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(tmp, path)
    except FileExistsError:
        raise SystemExit("REFUSED: RESULT_ALREADY_EXISTS") from None
    finally:
        tmp.unlink(missing_ok=True)
    return path


def returns_from_closes(closes):
    out = []
    for a, b in zip(closes[:-1], closes[1:]):
        ok = a is not None and b is not None and math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0
        out.append(b / a - 1.0 if ok else None)
    return out


def cash_growth(row) -> dict:
    """Registered cash scenarios for one saved block. BOK_POLICY_PROXY is the replay's own
    ACT/365 daily policy-rate path (``dailyRiskFreeNav``); +100bp adds simple ACT/365 accrual."""
    from datetime import date as _d
    rf = float(row["dailyRiskFreeNav"][-1])
    days = (_d.fromisoformat(row["dailyDates"][-1]) - _d.fromisoformat(row["dailyDates"][0])).days
    return {"ZERO": 1.0, "BOK_POLICY_PROXY": rf, "BOK_POLICY_PLUS_100BP": rf * (1.0 + 0.01 * days / 365.0)}


def window_closes(series_by_ticker, sessions, ticker, signal_date):
    """253 KR-session closes ending at the last KR session <= signal date; None for a gap.

    ``series_by_ticker[t]`` is a ``{iso_date: close}`` mapping; ``sessions`` the sorted KR
    session list. Nothing after the signal date is ever indexed.
    """
    import bisect
    i = bisect.bisect_right(sessions, signal_date) - 1
    if i < A.BETA_WINDOW_RETURNS:
        return []
    window = sessions[i - A.BETA_WINDOW_RETURNS:i + 1]
    source = series_by_ticker.get(ticker) or {}
    return [source.get(d) for d in window]


def build_blocks(saved_rows, etf_close, pre_signal_closes, cash_growth_fn):
    """Assemble ``A.Block`` inputs from saved rows (outcome-reading; execute mode only).

    ``etf_close(date) -> float`` reads the pinned corrected ETF series.
    ``pre_signal_closes(ticker, signal_date) -> (stock_closes, etf_closes)`` returns the
    253 aligned KR-session closes ending ON the signal date (None where no quote).
    ``cash_growth_fn(row) -> {scenario: 1 + R_F}``.
    Returns ``(blocks, failures)``; a saved row that fails the buy-and-hold identity (e.g. a
    corporate-action successor) is a failure with its reason, never a renormalised block.
    """
    blocks, failures = [], []
    for row in saved_rows:
        weights = {t: float(w) for t, w in row["weights"].items()}
        cash_w = 1.0 - sum(weights.values())
        rf_growth = float(row["dailyRiskFreeNav"][-1])
        try:
            growth = A.growth_from_terminal(weights, row.get("terminalWeights") or {}, row["grossReturn"],
                                            cash_w, rf_growth) if weights else {}
        except A.AttributionError as error:
            failures.append({"date": row["date"], "reason": str(error)})
            blocks.append(None)
            continue
        betas = {}
        for t in weights:
            s_closes, e_closes = pre_signal_closes(t, row["signalDate"])
            if len(s_closes) != A.BETA_WINDOW_RETURNS + 1 or len(e_closes) != A.BETA_WINDOW_RETURNS + 1:
                betas[t] = None
                continue
            betas[t], _ = A.ols_beta(returns_from_closes(s_closes), returns_from_closes(e_closes))
        etf_growth = etf_close(row["endDate"]) / etf_close(row["date"])
        days = len(row["dailyDates"])
        blocks.append(A.Block(row["date"], row["endDate"], row["signalDate"], weights, growth, betas,
                              etf_growth, cash_growth_fn(row), days / 252.0))
    return blocks, failures


def attribute_all(blocks):
    results = []
    for b in blocks:
        results.append(A.BlockResult("?", "SAVED_ROW_IDENTITY_FAILED") if b is None else A.attribute_block(b))
    return results


def path_returns(blocks, results, cost_fn, multiplier=1.0, detail=None):
    """Net block returns for C2 (stocks + ETF residual) and each control, costs charged as the
    replay's ``account`` charges them: on the drifted prior book, before the block's growth.

    C2 needs no beta, so a BETA_UNAVAILABLE block keeps C2 valued and breaks only the control
    paths (their drifted book is unknown from there, so they are never restarted). ``detail``,
    when a dict, receives per-block costs and the one-way turnover split (AGENTS v2.11)."""
    c2_net, ctrl_net = [], {k: [] for k in A.CASH_SCENARIOS}
    prior_c2, prior_ctrl = {}, {k: {} for k in A.CASH_SCENARIOS}
    broken = {k: False for k in A.CASH_SCENARIOS}
    costs = {"c2": [], **{k: [] for k in A.CASH_SCENARIOS}}
    turnover = []
    for index, (b, r) in enumerate(zip(blocks, results)):
        if b is None or r.c2_gross is None:
            # an unvalued C2 block breaks every compounded path from here on
            c2_net.append(math.nan)
            costs["c2"].append(math.nan)
            turnover.append(None)
            for k in A.CASH_SCENARIOS:
                ctrl_net[k].append(math.nan)
                costs[k].append(math.nan)
                broken[k] = True
            prior_c2 = None
            continue
        s = sum(b.weights.values())
        target = {**b.weights, ETF: 1.0 - s} if 1.0 - s > 1e-12 else dict(b.weights)
        if prior_c2 is None:
            c2_net.append(math.nan)
            costs["c2"].append(math.nan)
            turnover.append(None)
        else:
            cost = A.trade_cost(prior_c2, target, ETF, cost_fn, b.date, multiplier)
            costs["c2"].append(cost)
            c2_net.append((1 - cost) * (1 + r.c2_gross) - 1)
            rep_, ret_ = A.turnover_split(prior_c2, target, ETF)
            turnover.append(None if index == 0 else {"replaced": rep_, "retargeted": ret_})
        end = {t: target[t] * (b.growth.get(t, b.etf_growth) if t != ETF else b.etf_growth) for t in target}
        total = sum(end.values())
        if prior_c2 is not None:
            prior_c2 = {t: v / total for t, v in end.items()} if total > 0 else {}
        for k in A.CASH_SCENARIOS:
            if broken[k] or k not in r.by_cash:
                ctrl_net[k].append(math.nan)
                costs[k].append(math.nan)
                broken[k] = True
                continue
            eq = r.control_equity
            tgt = {ETF: eq} if eq > 1e-12 else {}
            ccost = A.trade_cost(prior_ctrl[k], tgt, ETF, cost_fn, b.date, multiplier)   # cash leg free
            costs[k].append(ccost)
            ctrl_net[k].append((1 - ccost) * (1 + r.by_cash[k]["control"]) - 1)
            g = 1 + r.by_cash[k]["control"]
            prior_ctrl[k] = {ETF: eq * b.etf_growth / g} if g > 0 and eq > 1e-12 else {}
    if detail is not None:
        detail.update(costs=costs, turnover=turnover)
    return c2_net, ctrl_net


def etf_path(blocks, cost_fn, multiplier=1.0, costs=None):
    """The ETF-only alternative (the replay's P0): buys 100% 069500.KS once, at the first
    block, and pays that buy at the same dated schedule; later blocks hold, so cost 0.
    ``costs``, when a list, receives each block's cost fraction."""
    out = []
    for index, b in enumerate(blocks):
        if b is None:
            out.append(math.nan)
            if costs is not None:
                costs.append(math.nan)
            continue
        cost = A.trade_cost({}, {ETF: 1.0}, ETF, cost_fn, b.date, multiplier) if index == 0 else 0.0
        if costs is not None:
            costs.append(cost)
        out.append((1 - cost) * b.etf_growth - 1)
    return out


def _finite(x):
    return x is not None and math.isfinite(x)


def decomposition(blocks, results, c2_net, ctrl_net, etf_net, years, c2_costs=None, ctrl_costs=None,
                  etf_costs=None):
    """Exact per-block reconciliation with EXPLICIT cost terms (Codex: a cost difference is the
    drag on the funded growth, ``cost * (1 + gross)``, not a difference of fee rates):

        net C2 - net ETF     = SELECTION + EXPOSURE + COST_vs_ETF
                             = SELECTION_UNCLIPPED + CLIP_TRANSFER + EXPOSURE + COST_vs_ETF
        COST_vs_ETF          = -cost_C2 * (1 + C2 gross) + cost_ETF * (1 + ETF gross)
        net C2 - net CONTROL = SELECTION + COST_vs_CONTROL      (the investable-twin gap)
        COST_vs_CONTROL      = -cost_C2 * (1 + C2 gross) + cost_CTRL * (1 + CONTROL gross)

    Each cost term is computed from the recorded costs, and the largest residual of each
    identity is published, so a mismatch is visible rather than absorbed. Terms are summed and
    annualised by the span; Jensen is the log-minus-arithmetic gap. Unattributable blocks are
    counted and left out of a scenario's sums, never filled.
    """
    n_blocks = len(blocks)
    c2_costs = c2_costs or [0.0] * n_blocks
    etf_costs = etf_costs or [0.0] * n_blocks
    out = {}
    for k in A.CASH_SCENARIOS:
        kc = (ctrl_costs or {}).get(k) or [0.0] * n_blocks
        acc = dict.fromkeys(("sel", "unc", "clip", "exp", "costE", "costK", "gapK"), 0.0)
        n, worst_e, worst_k = 0, 0.0, 0.0
        for i, (b, r, c, e) in enumerate(zip(blocks, results, c2_net, etf_net)):
            if b is None or k not in r.by_cash or not (_finite(c) and _finite(e)):
                continue
            v = r.by_cash[k]
            cost_e = -c2_costs[i] * (1 + r.c2_gross) + etf_costs[i] * (1 + b.etf_growth - 1)
            worst_e = max(worst_e, abs((c - e) - (v["selection"] + v["exposure"] + cost_e)))
            if abs(v["selection"] - v["selectionUnclipped"] - v["clipTransfer"]) > A.TOL:
                raise A.AttributionError("CLIP_TRANSFER_IDENTITY_FAILED")
            ctrl = ctrl_net[k][i]
            if _finite(ctrl) and _finite(kc[i]):
                cost_k = -c2_costs[i] * (1 + r.c2_gross) + kc[i] * (1 + v["control"])
                worst_k = max(worst_k, abs((c - ctrl) - (v["selection"] + cost_k)))
                acc["costK"] += cost_k
                acc["gapK"] += c - ctrl
            acc["sel"] += v["selection"]
            acc["unc"] += v["selectionUnclipped"]
            acc["clip"] += v["clipTransfer"]
            acc["exp"] += v["exposure"]
            acc["costE"] += cost_e
            n += 1
        ok = all(_finite(x) for x in c2_net) and all(_finite(x) for x in etf_net)
        jensen = A.jensen_split(c2_net, etf_net, years) if ok else None
        pp = (lambda x: 100 * x / years)
        out[k] = {"blocks": n, "selectionPpPerYear": pp(acc["sel"]),
                  "selectionUnclippedPpPerYear": pp(acc["unc"]), "clipTransferPpPerYear": pp(acc["clip"]),
                  "exposurePpPerYear": pp(acc["exp"]), "costVsEtfPpPerYear": pp(acc["costE"]),
                  "arithmeticC2MinusEtfPpPerYear": pp(acc["sel"] + acc["exp"] + acc["costE"]),
                  "c2MinusControlNetPpPerYear": pp(acc["gapK"]), "costVsControlPpPerYear": pp(acc["costK"]),
                  "jensenPpPerYear": None if jensen is None else 100 * jensen["jensen"],
                  "logGrowthGapPpPerYear": None if jensen is None else 100 * jensen["logGrowthGap"],
                  "maxResidualVsEtf": worst_e, "maxResidualVsControl": worst_k}
    return out


def subperiod(rows, blocks, results, c2_net, ctrl_net, etf_net, first_date):
    """Descriptive slice from ``first_date`` (fixed before outcomes: 2024-01-01)."""
    idx = [i for i, row in enumerate(rows) if row["date"] >= first_date]
    if not idx:
        return None
    years = RV_span(rows[idx[0]]["date"], rows[idx[-1]]["endDate"])
    pick = (lambda xs: [xs[i] for i in idx])
    out = {"firstBlock": rows[idx[0]]["date"], "lastEnd": rows[idx[-1]]["endDate"], "blocks": len(idx),
           "years": years, "c2Cagr": None, "etfCagr": None, "scenarios": {}}
    c2s, etfs = pick(c2_net), pick(etf_net)
    if all(_finite(x) for x in c2s + etfs):
        out["c2Cagr"] = A.cagr(A.chain(c2s), years)
        out["etfCagr"] = A.cagr(A.chain(etfs), years)
    for k in A.CASH_SCENARIOS:
        sel = [results[i].by_cash[k]["selection"] if k in results[i].by_cash else None for i in idx]
        ctrl = pick(ctrl_net[k])
        out["scenarios"][k] = {
            "selectionAnnualized": A.newey_west([x * len(idx) / years if x is not None else None for x in sel],
                                                A.BLOCKS_H126 - 1),
            "controlCagr": A.cagr(A.chain(ctrl), years) if all(_finite(x) for x in ctrl) else None}
    return out


def RV_span(first, last):
    """``replay_valuation.span_years`` (calendar days / 365.2425), so CAGRs match the replay's."""
    from datetime import date as _d
    return (_d.fromisoformat(last) - _d.fromisoformat(first)).days / 365.2425


def horizon_gaps(c2_net, ctrl):
    """H126 / H252: compounded C2-minus-control over every 6 / 12 block run (overlapping,
    descriptive) and over the non-overlapping runs only (the independent count)."""
    out = {}
    for label, k in (("h126", A.BLOCKS_H126), ("h252", A.BLOCKS_H252)):
        if not (all(_finite(x) for x in c2_net) and all(_finite(x) for x in ctrl)):
            out[label] = None
            continue
        gaps = [c - b for c, b in zip(A.windows(c2_net, k), A.windows(ctrl, k))]
        non = gaps[::k]
        out[label] = {"windows": len(gaps), "positiveShare": sum(g > 0 for g in gaps) / len(gaps),
                      "meanGap": sum(gaps) / len(gaps), "nonOverlapping": len(non),
                      "nonOverlappingPositive": sum(g > 0 for g in non),
                      "nonOverlappingMeanGap": sum(non) / len(non)}
    return out


# Published replay figures the reconstruction must reproduce (pre-outcome revision R1).
# They are rounded by the replay to 3 decimals of a percent, hence the tolerance.
RECONSTRUCTION_TOLERANCE_PCT = 0.0005 + 1e-9


def reconstruction_check(c2_net, etf_net, years, published):
    """Compare the reconstructed C2 and ETF (P0) net paths with the replay's own published
    KR C2 / P0 metrics. ``published = {"C2": {...}, "P0": {...}}`` holds ``cagrPct`` and
    ``cumulativeNetReturnPct`` as the replay wrote them. A mismatch makes the verdict
    SOURCE_OR_SAMPLE_INSUFFICIENT: an attribution of a path that is not the saved C2 path is
    not an attribution of C2."""
    if published is None:
        return {"status": "NOT_CHECKED"}
    mine = {}
    for key, series in (("C2", c2_net), ("P0", etf_net)):
        if not all(_finite(x) for x in series):
            mine[key] = None
            continue
        nav = A.chain(series)[-1]
        mine[key] = {"cagrPct": 100 * (nav ** (1 / years) - 1), "cumulativeNetReturnPct": 100 * (nav - 1)}
    diffs, ok = {}, True
    for key in ("C2", "P0"):
        for field in ("cagrPct", "cumulativeNetReturnPct"):
            want = (published.get(key) or {}).get(field)
            got = None if mine.get(key) is None else mine[key][field]
            if want is None or got is None:
                ok = False
                diffs[f"{key}.{field}"] = None
                continue
            diffs[f"{key}.{field}"] = got - float(want)
            ok = ok and abs(got - float(want)) <= RECONSTRUCTION_TOLERANCE_PCT
    return {"status": "REPRODUCES_PUBLISHED_C2_AND_P0" if ok else "RECONSTRUCTION_MISMATCH",
            "tolerancePct": RECONSTRUCTION_TOLERANCE_PCT, "differencesPct": diffs, "reconstructed": mine}


def analyse(saved_rows, etf_close, pre_signal_closes, cost_fn, years_total, published=None,
            recent_from="2024-01-01", require_unclipped=True):
    """Pure core of ``execute`` (tested on synthetic rows): attribution at cost 1x/2x/3x."""
    blocks, failures = build_blocks(saved_rows, etf_close, pre_signal_closes, cash_growth)
    results = attribute_all(blocks)
    per_cost, verdict_input, extra = {}, {}, {}
    for m in A.COST_MULTIPLIERS:
        detail = {}
        c2_net, ctrl_net = path_returns(blocks, results, cost_fn, m, detail)
        etf_costs = []
        etf_net = etf_path(blocks, cost_fn, m, etf_costs)
        summary = A.summarize(results, c2_net, ctrl_net, etf_net, years_total,
                              len(saved_rows) / years_total)
        summary["decomposition"] = decomposition(
            blocks, results, c2_net, ctrl_net, etf_net, years_total, detail["costs"]["c2"],
            {k: detail["costs"][k] for k in A.CASH_SCENARIOS}, etf_costs)
        summary["horizonC2MinusControl"] = {k: horizon_gaps(c2_net, ctrl_net[k]) for k in A.CASH_SCENARIOS}
        summary["recent"] = subperiod(saved_rows, blocks, results, c2_net, ctrl_net, etf_net, recent_from)
        per_cost[f"{m:g}x"] = summary
        extra[m] = (c2_net, etf_net, detail)
    for k in A.CASH_SCENARIOS:
        one = per_cost["1x"]["scenarios"][k]
        verdict_input[k] = {"mean": one["selectionAnnualized"]["mean"], "ci95": one["selectionAnnualized"]["ci95"],
                            "netCi95": one["netSelectionAnnualized"]["ci95"],
                            "unclippedCi95": one["selectionUnclippedAnnualized"]["ci95"]}
    # SELECTION is gross of cost by construction; the 2x requirement reads the net c2-vs-control gap
    for k in A.CASH_SCENARIOS:
        gap = per_cost["2x"]["scenarios"][k]["c2VsControl"]
        verdict_input[k]["mean2x"] = None if gap is None else gap["arithmeticActive"]
    c2_1x, etf_1x, detail_1x = extra[1.0]
    recon = reconstruction_check(c2_1x, etf_1x, years_total, published)
    share = per_cost["1x"]["unattributableShare"]
    verdict = A.verdict(verdict_input, share, require_unclipped=require_unclipped)
    if recon["status"] == "RECONSTRUCTION_MISMATCH":
        verdict = "SOURCE_OR_SAMPLE_INSUFFICIENT"
    turns = [t for t in detail_1x["turnover"] if t]
    clipped = [r for r in results if r.clip]
    return {"failures": failures, "byCost": per_cost,
            "clipped": len(clipped),
            "clips": {"count": len(clipped), "byKind": {c: sum(1 for r in clipped if r.clip == c)
                                                         for c in sorted({r.clip for r in clipped})},
                      "dates": [r.date for r in clipped]},
            "betaUnavailable": [{"date": r.date, "status": r.status} for r in results
                                if r.status.startswith("BETA_UNAVAILABLE")],
            "turnoverOneWayPerYear": {
                "replaced": sum(t["replaced"] for t in turns) / years_total,
                "retargeted": sum(t["retargeted"] for t in turns) / years_total},
            "reconstruction": recon, "verdictInput": verdict_input, "unattributableShare": share,
            "requireUnclippedSelection": require_unclipped,
            "verdictWithoutR4": A.verdict(verdict_input, share, require_unclipped=False),
            "verdict": verdict}


CLOSURE_ENTRY_POINTS = ("research/alpha_evidence_sprint_v2/c2_attribution_run.py",
                        "pipeline/weekly_decision.py", "pipeline/replay_inputs.py", "pipeline/replay_calendar.py",
                        "pipeline/market_dates.py", "pipeline/provenance.py")


def dependency_closure(root=None) -> dict:
    """sha256 of every pipeline module execute can import (top-level and lazy), computed with the
    repository's own ``alpha_opportunity_v3_spec.import_closure``. The two research files are
    bound by the authorization itself and are excluded here."""
    from pipeline.alpha_opportunity_v3_spec import import_closure
    root = Path(root or ROOT)
    files = [f for f in import_closure(CLOSURE_ENTRY_POINTS, root) if f.startswith("pipeline/")]
    return {f: sha256(root / f) for f in files}


def verify_dependency_closure(spec, root=None) -> dict:
    """Cost schedule, calendar, input store and valuation code are part of the approved state
    (Codex F2): a new import or an edited sealed module refuses before any input is read."""
    pinned = spec["dependencyClosure"]["files"]
    actual = dependency_closure(root)
    if set(actual) != set(pinned):
        raise SystemExit("REFUSED: DEPENDENCY_CLOSURE_CHANGED " + ",".join(sorted(set(actual) ^ set(pinned))))
    changed = sorted(f for f in pinned if actual[f] != pinned[f])
    if changed:
        raise SystemExit("REFUSED: SEALED_DEPENDENCY_CHANGED " + ",".join(changed))
    return actual


def resolve_etf_series(spec, basis_path=None, root=None) -> dict:
    """The ONLY 069500.KS series execute may use (Codex F2).

    The first draft read the file and field named by the basis protocol and hash-checked a
    DIFFERENT, separately pinned file, so a protocol pointing at file B passed while file A was
    verified. Now: the protocol's own bytes are pinned; its file and field must equal the
    registered ones; that file's bytes must equal the registered sha256, which must also be the
    pinnedInputs entry for the same path. The series must be strictly dated and positive."""
    root = Path(root or ROOT)
    basis_path = Path(basis_path or BASIS)
    pin = spec["etfSeries"]
    if sha256(basis_path) != pin["protocolSha256"]:
        raise SystemExit("REFUSED: BASIS_PROTOCOL_CHANGED")
    basis = json.loads(basis_path.read_text())["correctedSeries"]
    if basis.get("file") != pin["file"] or basis.get("field") != pin["field"]:
        raise SystemExit("REFUSED: ETF_SOURCE_REDIRECTED")
    listed = {i["path"]: i["sha256"] for i in spec["pinnedInputs"]["files"]}
    if listed.get(pin["file"]) != pin["sha256"]:
        raise SystemExit("REFUSED: ETF_PIN_INCONSISTENT")
    if sha256(root / pin["file"]) != pin["sha256"]:
        raise SystemExit("REFUSED: ETF_SERIES_CHANGED")
    quotes = json.loads((root / pin["file"]).read_text())[pin["field"]]
    series = {}
    for q in quotes:
        d, c = q["date"][:10], float(q["Close"])
        if d in series or (series and d <= max(series)) or not (math.isfinite(c) and c > 0):
            raise SystemExit("REFUSED: ETF_SERIES_MALFORMED")
        series[d] = c
    return series


def load_inputs(ledger: Path) -> dict:
    """Verify every pinned identity and load the inputs ``execute`` needs. Loads the full price
    panel into memory; computes no return (``preflight`` only counts presence)."""
    from pipeline import provenance, replay_calendar as RC, replay_inputs as RI
    from pipeline.replay_valuation import normalize_daily_series   # the replay's own import path
    spec = json.loads(SPEC.read_text())
    closure = verify_dependency_closure(spec)
    for item in spec["pinnedInputs"]["files"]:
        if sha256(ROOT / item["path"]) != item["sha256"]:
            raise SystemExit("REFUSED: PINNED_FILE_CHANGED " + item["path"])
    etf = resolve_etf_series(spec)
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if manifest is None or manifest["sha256"] != spec["pinnedInputs"]["replayInputManifestSha256"]:
        raise SystemExit("REFUSED: REPLAY_INPUT_MANIFEST_MISMATCH")
    frozen = RI.unpack(store.load(manifest, valuation_only=True))
    prices = {t: {d.strftime("%Y-%m-%d"): float(v) for d, v in normalize_daily_series(p["Close"]).items()}
              for t, p in frozen["prices"].items() if p is not None and "Close" in p}
    sessions = [d.strftime("%Y-%m-%d") for d in RC.sessions("2011-01-01", manifest["through"], "KR")]
    return {"spec": spec, "manifest": manifest, "prices": prices, "etf": etf, "sessions": sessions,
            "closure": closure}


def preflight(ledger: Path) -> dict:
    """OUTCOME-FREE eligibility count on the real inputs: for every saved block, does each held
    name and the ETF have the closes the registered beta needs (presence only), and does the
    ETF quote both block ends. No return, NAV, terminal weight or beta is computed."""
    data = load_inputs(ledger)
    rows = load_rows(READINESS_KEYS)
    prices, etf, sessions = data["prices"], data["etf"], data["sessions"]

    def present(xs):
        return sum(1 for a, b in zip(xs[:-1], xs[1:]) if a is not None and b is not None)

    eligible, problems, min_pairs = 0, [], None
    for row in rows:
        reasons = []
        e = window_closes({ETF: etf}, sessions, ETF, row["signalDate"])
        for t in row["weights"]:
            s = window_closes(prices, sessions, t, row["signalDate"])
            if len(s) != A.BETA_WINDOW_RETURNS + 1:
                reasons.append(f"WINDOW_SHORT:{t}")
                continue
            pairs = sum(1 for i in range(A.BETA_WINDOW_RETURNS)
                        if None not in (s[i], s[i + 1], e[i] if e else None, e[i + 1] if e else None))
            min_pairs = pairs if min_pairs is None else min(min_pairs, pairs)
            if pairs < A.BETA_MIN_RETURNS:
                reasons.append(f"BETA_PAIRS_{pairs}:{t}")
        if row["date"] not in etf or row["endDate"] not in etf:
            reasons.append("ETF_BLOCK_END_UNQUOTED")
        if reasons:
            problems.append({"date": row["date"], "reasons": reasons})
        else:
            eligible += 1
    return {"mode": "PREFLIGHT_OUTCOME_FREE", "blocks": len(rows), "eligibleBlocks": eligible,
            "ineligible": problems, "minimumJointBetaPairs": min_pairs,
            "etfReturnsInFirstWindow": present(window_closes({ETF: etf}, sessions, ETF, rows[0]["signalDate"])),
            "replayInputManifestSha256": data["manifest"]["sha256"], "tickersPriced": len(prices),
            # Honest counters: the full replay-v16 price panel IS loaded into memory (prices after
            # each signal date included); only date presence is inspected, nothing is divided.
            "fullPricePanelLoaded": True, "returnsComputed": 0, "betasComputed": 0,
            "savedRowOutcomeFieldsLoaded": False}


def execute(ledger: Path) -> dict:  # pragma: no cover - owner-gated, never run in CI
    """Order: authorization -> one-shot -> every identity -> CLAIM (consumes the study) -> outcomes."""
    spec_sha = sha256(SPEC)
    ok, reason = authorization_ok(spec_sha)
    if not ok:
        raise SystemExit(f"REFUSED: {reason}")
    ok, reason = one_shot_ok()
    if not ok:
        raise SystemExit(f"REFUSED: {reason}")
    from pipeline import weekly_decision as W
    data = load_inputs(ledger)          # identities only; no outcome is computed here
    commit = _git("rev-parse", "HEAD").strip()
    claim = claim_execution(commit, {"specSha256": spec_sha, "authorization": reason,
                                     "replayInputManifestSha256": data["manifest"]["sha256"]})
    prices, etf, sessions = data["prices"], data["etf"], data["sessions"]
    rows = load_rows()

    def pre(ticker, signal):
        return (window_closes(prices, sessions, ticker, signal), window_closes({ETF: etf}, sessions, ETF, signal))

    def cost(as_of, side, is_etf):
        return W.trade_cost_fraction("KR", as_of, is_benchmark=is_etf, side=side)

    years = RV_span(rows[0]["date"], rows[-1]["endDate"])
    paths = json.loads(REPLAY.read_text())["regions"]["KR"]["paths"]
    published = {k: {f: paths[k].get(f) for f in ("cagrPct", "cumulativeNetReturnPct")} for k in ("C2", "P0")}
    out = analyse(rows, lambda d: etf[d], pre, cost, years, published=published,
                  require_unclipped=bool(data["spec"]["decisionRule"].get("requireUnclippedSelection")))
    import importlib.metadata as md
    import platform
    out.update(study="c2-fixed-exposure-attribution-v1", specSha256=spec_sha,
               codeSha256={"c2_attribution.py": sha256(HERE / "c2_attribution.py"),
                           "c2_attribution_run.py": sha256(HERE / "c2_attribution_run.py")},
               dependencyClosureSha256=data["closure"], executionClaim=claim,
               ownerAuthentication=OWNER_AUTHENTICATION,
               runtime={"python": platform.python_version(),
                        **{p_: md.version(p_) for p_ in ("numpy", "pandas", "exchange-calendars")}},
               replayInputManifestSha256=data["manifest"]["sha256"], years=years,
               evidenceClass="POST_OUTCOME_EXPOSED_DESCRIPTIVE_ATTRIBUTION_OF_FIXED_SAVED_PATH",
               promotionEligible=False)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("readiness")
    r.add_argument("--out", required=True)
    f = sub.add_parser("preflight")
    f.add_argument("ledger")
    f.add_argument("--out", required=True)
    e = sub.add_parser("execute")
    e.add_argument("ledger")
    args = ap.parse_args(argv)
    if args.mode == "readiness":
        out = readiness()
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        print(json.dumps({k: out[k] for k in ("blocks", "blocksWithStocks", "distinctNamesHeld")}))
        return 0
    if args.mode == "preflight":
        out = preflight(Path(args.ledger))
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        print(json.dumps({k: out[k] for k in ("blocks", "eligibleBlocks", "minimumJointBetaPairs")}))
        return 0
    out = execute(Path(args.ledger))   # writes only the canonical one-shot RESULT path
    write_result_once(out)
    print(json.dumps({"verdict": out["verdict"], "result": str(RESULT.relative_to(ROOT))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
