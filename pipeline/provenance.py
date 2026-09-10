"""Provenance & run-state stamps attached to every artifact.

The single most important honesty fix: README, the build, the validator and
the screen must all express the *same* safe state. This module is the one
source of truth for:

  * schemaVersion   — bumped when the payload shape changes (consumers gate on it)
  * modelVersion    — the engine/algorithm version (bumped on scoring changes)
  * buildCommitSha  — the exact code that produced the artifact
  * generatedAt     — when the build ran (UTC)
  * marketAsOf      — the last *price* observation date
  * sourceAsOf      — the last *fundamental / macro* source date
  * runMode         — researchOnly | paperTrading | liveValidated (default paperTrading)
  * dataMode        — live | seed | stale | synthetic  (what the numbers ACTUALLY are)

runMode is a claim about how the output may be used; dataMode is a claim about
what the numbers are. They are independent: a seed build is always dataMode=seed
regardless of runMode, and can never be liveValidated.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

SCHEMA_VERSION = "2.7.0"
MODEL_VERSION = "longterm-v2.2+regime-v2.1+entry-v1+probability-gated-regional-active-kelly-v3+daily-session-v2"

# Versions that identify a body of HISTORICAL evidence rather than the live
# engine. A replay is only comparable to another replay run with the same
# three, so every historical record carries them and evidence is never pooled
# across versions. Changing one does not invalidate the old records — it starts
# a new generation alongside them.
# v5: the replay stopped resolving its universe from today's constituent
# list. Against the 2012-12-27 S&P 500 the old universe saw 281 of 500
# names, and a cross-sectional rank taken over 281 survivors is not the
# same measurement as one taken over the real 500 — so v4's records are
# kept as their own generation rather than extended.
# v6: Korean value and quality stopped being empty. Every KR name in v5 was
# ranked on price alone — `FundamentalStore` held nothing, so earningsYield,
# bookYield, roe and the rest were None for all of them — and the DART
# collection now supplies 116 of the 119 KR names (the three absent are
# preferred shares, which have no corp_code of their own and never will).
# `alphaPercentile` is a rank inside the date's cross-section: a KR
# cross-section scored on two sleeves is not the same measurement as one
# scored on four, so v5's 379,873 signals and 372,883 outcomes are kept as
# their own generation rather than extended. MODEL_VERSION is deliberately
# unchanged — `longterm.score_cross_section` is byte-identical; what changed
# is which of its inputs are present, which is what DATA_VERSION records.
# v7: immutable acquired input prefixes, completed weekly signal calendar,
# fixed common-session evaluation windows, daily KRW NAV and risk-free cash.
# v6 cannot be reconstructed from its ledger: source prices/FX were not saved.
# Preserve all v6 shards; a full v7 run produces its own snapshot and signals.
# v8 corrects three source-confirmed 2026 KRX closures missing in the pinned
# library. The resulting anchors must not overwrite the committed v7 calendar.
# v9 changes historical valuation inputs: one official H.10 USD/KRW vintage
# replaces the incomplete Yahoo panel, independently observed FDR returns may
# repair only validated market-wide Korean holes, and a reviewed merger ledger
# values held securities through cash-and-stock actions. Those changes can alter
# past outcomes, so v8 stays immutable and v9 is a new full experiment.
# v10 repairs two defects observed on the first v9 production run.  Benchmark
# resolution now pins one vendor lineage per generation instead of selecting
# whichever source is one session fresher, and systemic Korean gaps compare
# FDR raw returns with Yahoo raw anchors before mapping them back to the
# adjusted basis.  Both can change historical inputs, so v9 remains sealed.
# v11 changes what the generation seals, because v10's seal could not hold.
# Yahoo's auto-adjusted close is a BACK-anchored total return: every value in it
# is rescaled by the dividends that come after it. Between v9's seal and v10's,
# one day apart, 17 of 567 names moved 3-86 bps in JANUARY 2011 for that reason
# and 550 more moved one float32 step, so `InputStore.commit`'s byte-exact
# prefix check refused every acquisition run after a generation's first. v7, v8,
# v9 and v10 each died that way rather than of anything to do with the evidence.
# v11 seals the as-traded close and the dividend/split events instead, and
# accumulates the total return FORWARD from the first session, so a dividend
# paid tomorrow appends and never rewrites a published value. The series stays
# proportional to Yahoo's adjusted close, so nothing that is measured changes —
# but v10's inputs cannot be reinterpreted on the new basis, so it stays sealed.
# v12 changes where Korean prices come from. v11 proved the point that made
# the change unavoidable: with the same-vendor retry finally narrowed to one
# window per gap cluster, it recovered NOTHING — targetedYahooRetries: 0 across
# all five market-wide holes — because Yahoo does not have those KRX sessions
# at all. It serves 3,782 KOSPI 200 sessions against FinanceDataReader's 3,855.
# The 42 names the bridge then refused on 2025-09-19 were refused against
# Yahoo's own anchors, which differ from FDR's by a median 55 bps with no
# relation to each name's volatility (r = -0.07). So the replay reads Korean
# sessions from the exchange-native vendor and keeps Yahoo for the
# distributions FDR does not publish, with Yahoo's closes recorded as a
# cross-check rather than silently preferred away.
REPLAY_VERSION = "replay-v12"
FEATURE_VERSION = "hfeat-v1"
DATA_VERSION = ("as-traded-close-forward-total-return-v1-regional-session-download"
                "+krx-fdr-sessions-with-yahoo-distributions-v1"
                "+pit-index-membership+dart-pit-fundamentals-kr"
                "+immutable-inputs-v1+common-calendar-v2-kr-2026-closures"
                "+fred-h10-usdkrw-fixing-v1+benchmark-vendor-lineage-v1"
                "+kr-systemic-gap-detect-only-v4"
                "+corporate-actions-v1+bok-rf-v1")

# MODEL_VERSION is a compound identity, and not every component of it is a
# statement about how names are scored. "daily-session-v2" was appended by a
# benchmark-download fix that left every scoring component byte-identical, and
# because the prospective ledger isolates generations on the whole string, it
# discarded 13,518 recorded signals and restarted a 252-business-day validation
# clock from four days. A change in how prices are downloaded is real, but it
# is what DATA_VERSION exists to record; it is not a new model.
#
# Components named here are plumbing: they stay in MODEL_VERSION so provenance
# is complete, and they are stripped before the prospective ledger decides
# which rows belong to the same generation.
PLUMBING_COMPONENTS = ("daily-session",)


def _component_name(component: str) -> str:
    """"longterm-v2.2" -> "longterm"; a component with no version is its name."""
    head, sep, tail = component.rpartition("-v")
    return head if sep and head and tail[:1].isdigit() else component


def scoring_identity(model_version: str | None) -> str | None:
    """The part of a model version that actually claims something about scoring.

    Order is preserved and unknown components are kept, so a new component is
    treated as scoring until someone deliberately declares it plumbing — the
    safe direction, since the cost of being wrong is pooling two generations
    rather than splitting one.
    """
    if model_version is None:
        return None
    kept = [component for component in str(model_version).split("+")
            if _component_name(component) not in PLUMBING_COMPONENTS]
    return "+".join(kept) if kept else str(model_version)


RUN_MODES = ("researchOnly", "paperTrading", "liveValidated")
DEFAULT_RUN_MODE = "paperTrading"


def build_commit_sha() -> str | None:
    """Short SHA of the code that produced this artifact.

    CI exposes it as GITHUB_SHA; locally we ask git. Never fabricate — return
    None if it genuinely can't be determined so the UI shows 'unknown' rather
    than a misleading value.
    """
    for env in ("GITHUB_SHA", "GIT_COMMIT", "BUILD_COMMIT_SHA"):
        val = os.environ.get(env)
        if val:
            return val[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


def resolve_run_mode(configured: str | None) -> str:
    """Clamp the configured run mode to a known value; default paperTrading.

    liveValidated is NEVER honored from config alone — it must be earned by the
    ledger/validation layer, which upgrades it explicitly. Config asking for
    liveValidated is downgraded here to paperTrading.
    """
    mode = (configured or DEFAULT_RUN_MODE).strip()
    if mode not in RUN_MODES:
        return DEFAULT_RUN_MODE
    if mode == "liveValidated":
        return DEFAULT_RUN_MODE
    return mode


def data_mode(payload: dict) -> str:
    """Classify what the numbers in this payload actually are."""
    meta = payload.get("meta", {}) or {}
    if payload.get("seed") or meta.get("syntheticData"):
        return "synthetic" if meta.get("syntheticData") else "seed"
    if payload.get("stale"):
        return "stale"
    return "live"


def stamp(payload: dict, run_mode: str) -> dict:
    """Attach the provenance block in-place and return it."""
    meta = payload.setdefault("meta", {})
    prov = {
        "schemaVersion": SCHEMA_VERSION,
        "modelVersion": MODEL_VERSION,
        "replayVersion": REPLAY_VERSION,
        "featureVersion": FEATURE_VERSION,
        "dataVersion": DATA_VERSION,
        "buildCommitSha": build_commit_sha(),
        "generatedAt": payload.get("generatedAt") or datetime.now(timezone.utc).isoformat(),
        "marketAsOf": meta.get("latestDataDate"),
        "sourceAsOf": meta.get("sourceAsOf"),
        "runMode": run_mode,
        "dataMode": data_mode(payload),
    }
    payload["provenance"] = prov
    payload["schemaVersion"] = SCHEMA_VERSION
    payload["modelVersion"] = MODEL_VERSION
    payload["runMode"] = run_mode
    payload["dataMode"] = prov["dataMode"]
    payload["generatedAt"] = prov["generatedAt"]
    return prov
