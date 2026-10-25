"""industry-alpha-kr-next-v1: the frozen numbers of the prepared (NOT authorized) KR study.

Everything an execution would need to decide is a module constant here, so a future authorization can pin it by hash
(`spec_sha256`). Nothing in this module reads data. The 36 hypothesis slots are read from `design.json` so the slot
list has one source. Changes against `preregistration.md` are listed in PRE_OUTCOME_REVISIONS with their reasons;
no historical outcome had been computed by anyone for this study when they were made.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

STUDY_ID = "industry-alpha-kr-next-v1"
STATUS = "PREPARED_NOT_AUTHORIZED"
EVIDENCE_CLASS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY"
REGION = "KR"
BENCHMARK = "069500.KS"
HORIZONS = (126, 252)
PRIMARY_HORIZON = 126
DEVELOPMENT_CUTOFF = "2026-09-14"          # the replay-v16 `through`; no later price is read
SIGNAL_RULE = "LAST_V4_WEEKLY_GRID_DATE_OF_EACH_CALENDAR_MONTH"
LENSES = ("CAP_WEIGHTED", "EQUAL_WEIGHT")  # cap-weighted is primary; equal-weight is a registered diagnostic

# Inputs: every byte is reachable from git and pinned (see inputs.py). Caps are the strictly prior monthly KRX
# universe snapshot; liquidity is a replay Close x Volume proxy. Both are labelled, never called official values.
INPUT_POLICY = {
    "signalHistoryCommit": "4ea107ed0cde289f0a049a65ff13d2441a786710",
    "replayManifestSha256": "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2",
    "accountingPinsFrom": "research_specs/kr-model-overlay-portfolio-v1.json",
    "membership": "data/kr-industry-membership-foundation-v4/state/intervals.json.gz",
    "crosswalk": "research_specs/kr-industry-membership-foundation-v4/crosswalk.json",
    "top120Inputs": "data/kr-industry-membership-foundation-v1/top120-inputs.json",
    "terminalFoundation": "docs/results/kr-terminal-action-reconstruction-v2.json",
    "capBasis": "STRICTLY_PRIOR_MONTHLY_KRX_UNIVERSE_SNAPSHOT_ISSUE_CAP",
    "liquidityBasis": "REPLAY_CLOSE_X_VOLUME_PROXY_NOT_OFFICIAL_TRADING_VALUE",
    "returnBasis": "BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS",
}

# Feature blocks (industry-date columns). Each block is removed as a whole in its H1 contrast.
BLOCKS = {
    "MOM": ("REL_MOM_126",),
    "BREADTH": ("BREADTH_ABOVE_MA_126",),
    "PROFIT": ("MEDIAN_netIncomeToAssets", "MEDIAN_netIncomeImprovementToAssets"),
    "CASH": ("MEDIAN_ocfToAssets", "MEDIAN_ocfImprovementToAssets"),
    "VALUE": ("MEDIAN_bookToMarketProxy",),
    "CONCENTRATION": ("HHI", "TOP1_CAP_SHARE"),
}
NUISANCE = ("DOWNSIDE_VOL_126", "LOG_CONSTITUENT_COUNT", "MEDIAN_LOG_ADV60")
MARKET_CONTEXT = ("MKT_RET_126", "MKT_VOL_126", "MKT_ABOVE_SMA200", "MOM_X_MKT_TREND", "BREADTH_X_MKT_TREND")
DIFFUSION_BASE = ("LAGGARD_MOM_126", "LAGGARD_BREADTH_126", "EX_LEADER_MOM_126", "HHI", "MEDIAN_LOG_ADV60",
                  "LOG_INDUSTRY_CAP")
DIFFUSION_SIGNAL = ("LEADER_GAP_63",)

LEADER_SHARE = 0.20            # top 20% of signal-date cap, ceil, at least 1
MIN_LEADERS = MIN_LAGGARDS = 2
MIN_MEMBERS = 5                # inherited from the sealed anatomy (I.MIN_MEMBERS); asserted equal in tests
MIN_INDUSTRIES_PER_DATE = 8

RIDGE_LAMBDA = 10.0
EMBARGO_SESSIONS = 21
MIN_TRAINING_YEARS = 5
BOOTSTRAP = {"draws": 1999, "seed": 1879, "blockSignals": 12}   # 12 monthly signals ~ 252 sessions
MIN_NONOVERLAPPING_H252_BLOCKS = 8
HOLM_ALPHA = 0.05

COSTS = {"source": "pipeline.benchmark_alpha.REALISTIC_COSTS['KR']", "stress": (1, 2, 3)}

# Owner decisions an authorization must state explicitly; an absent or null value refuses execution.
OWNER_DECISIONS = (
    "krHistoryClosureException",      # Phase D closure kept; a bounded new question on exposed history is allowed
    "classifiedOnlyEstimand",         # accept the classification/survival-conditioned estimand measured by input_check
    "admissionRule",                  # "BLOCK_SCOPED" (contracts.py) or "STUDY_WIDE"
    "minimumCompleteBlocks",          # integer, fixed before outcomes
    "sequentialGate",                 # True = H2 opens only if an H1 non-concentration slot passes (preregistration)
    "supportRule",                    # how the structural support shortfall in input_check is handled
)

PRE_OUTCOME_REVISIONS = (
    {"id": "R-SIGNAL-MONTHLY", "change": "Signals are the last v4 weekly-grid date of each month",
     "reason": "the preregistration asks for month-end signals; the v4 reconstruction is defined on its weekly grid"},
    {"id": "R-PROFIT-CASH-CHANGE", "change": "PROFIT and CASH blocks each carry the level AND its 12-month change",
     "reason": "the owner's hypothesis 2 is about the CHANGE in earnings/cash flow and whether prices already anticipate it; "
               "the change uses the sealed improvement_to_assets definition (same visible-filing rule)"},
    {"id": "R-ANTICIPATION-DIAGNOSTIC", "change": "Fundamental-change contrasts are also reported within prior-MOM terciles",
     "reason": "anticipation means the change is already in the price; a descriptive split, never a slot"},
    {"id": "R-GIT-PINNED-INPUTS", "change": "Caps from the strictly prior monthly universe snapshot; liquidity is a Close x Volume proxy",
     "reason": "every input is then reproducible from pinned git objects; the daily KRX market-value files exist only in an expiring artifact"},
    {"id": "R-DOWNSIDE-VOL-NUISANCE", "change": "The volatility nuisance is the sealed anatomy's DOWNSIDE_VOL_126",
     "reason": "reuse the sealed definition instead of a second volatility formula"},
)


def slots():
    design = json.loads((HERE / "design.json").read_text())
    return tuple(design["primaryHypothesisSlots"])


def spec():
    keys = ("STUDY_ID", "STATUS", "EVIDENCE_CLASS", "REGION", "BENCHMARK", "HORIZONS", "PRIMARY_HORIZON",
            "DEVELOPMENT_CUTOFF", "SIGNAL_RULE", "LENSES", "INPUT_POLICY", "BLOCKS", "NUISANCE", "MARKET_CONTEXT",
            "DIFFUSION_BASE", "DIFFUSION_SIGNAL", "LEADER_SHARE", "MIN_LEADERS", "MIN_LAGGARDS", "MIN_MEMBERS",
            "MIN_INDUSTRIES_PER_DATE", "RIDGE_LAMBDA", "EMBARGO_SESSIONS", "MIN_TRAINING_YEARS", "BOOTSTRAP",
            "MIN_NONOVERLAPPING_H252_BLOCKS", "HOLM_ALPHA", "COSTS", "OWNER_DECISIONS", "PRE_OUTCOME_REVISIONS")
    g = globals()
    return {k: g[k] for k in keys} | {"slots": slots()}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=list).encode()


def spec_sha256():
    return hashlib.sha256(canonical(spec())).hexdigest()


CODE_FILES = ("study.py", "panel.py", "evaluate.py", "inputs.py", "input_check.py", "run_study.py", "contracts.py",
              "design.json")


def code_sha256():
    return {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in CODE_FILES}
