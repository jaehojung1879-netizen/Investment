"""kr-alpha-atlas Phase B — the smallest weekly dry run: can the future weekly process find its signal session, load point-in-time inputs, compute the
research-only features, check coverage, and say honestly what state it is in?

IT CAN ONLY SAY NOT_READY OR BLOCKED. No authorization is registered (`kr_alpha_signal_v2_receipts.REGISTERED_AUTHORIZATION is None`), so no state in this module
is a decision, a portfolio, a weight, an entry state or a radar tier, and the result carries no such key (a test scans it). It writes no receipt, appends to no ledger,
reads no label or forward price, and is scheduled nowhere. It reuses the existing prospective-receipt calendar rules (`prospective_receipt_core`: weekly decision
session, 18:00 KST final-close time) and the H2 contract's own readiness check (`kr_alpha_signal_v2.readiness`), and builds the same features with the same
`kr_alpha_atlas_matrix.build_matrix` the historical matrix uses — one definition, two uses.

THE CLOCK. The wall clock is read once, here, and only to choose which session is the latest FINAL one. A caller can replay a past instant by passing `now_utc`
(timezone-aware), which the result then labels as an explicit replay and not as a live run.
"""
from __future__ import annotations

import pandas as pd

from . import kr_alpha_atlas_matrix as M
from . import kr_alpha_signal_v2 as S2
from . import kr_alpha_signal_v2_receipts as R
from . import prospective_receipt_core as CORE
from . import regional_alpha_features as RAF

CONTRACT = "KR_ALPHA_ATLAS_WEEKLY_DRY_RUN_V1"
STATES = ("NOT_READY", "BLOCKED")
LOOKBACK_DAYS = 14
FORBIDDEN_KEY_FRAGMENTS = ("weight", "position", "holding", "entry", "tier", "radar", "portfolio", "order", "forecast", "expectedexcess")


def latest_signal_session(now_utc):
    """The most recent weekly decision session whose close was FINAL (18:00 KST) at `now_utc`, or None."""
    now = CORE.utc(now_utc)
    day = now.tz_localize(None).normalize()
    for back in range(0, LOOKBACK_DAYS + 1):
        candidate = day - pd.Timedelta(days=back)
        if CORE.is_weekly_decision_session(candidate) and (candidate + CORE.KR_CLOSE_FINAL_UTC).tz_localize("UTC") <= now:
            return candidate
    return None


def assert_not_actionable(result, path=""):
    """Refuse any key that names an actionable output. A dry run that grew one would no longer be a dry run."""
    if isinstance(result, dict):
        for key, value in result.items():
            if any(f in str(key).lower() for f in FORBIDDEN_KEY_FRAGMENTS):
                raise ValueError("ACTIONABLE_KEY_IN_DRY_RUN: " + path + "/" + str(key))
            assert_not_actionable(value, path + "/" + str(key))
    elif isinstance(result, list):
        for i, value in enumerate(result):
            assert_not_actionable(value, path + "/%d" % i)


def run(inputs, *, now_utc=None, signal_date=None, eligible_features=None, replay_of_instant=False, counters=None, history_weeks=0):
    """One dry run. `inputs` is a `kr_alpha_atlas_inputs.MatrixInputs`. Returns a plain dict; never raises on missing data (that is a BLOCKED state).

    `history_weeks` earlier weekly signal dates are built too, because three registered features read the name's own EARLIER rows (B06, B07, H07); with none they are
    reported INSUFFICIENT_OWN_HISTORY, which is what a first-ever weekly run would honestly say. Only the signal date's rows are evaluated."""
    counters = counters if counters is not None else {}
    clock = CORE.system_utc_now() if now_utc is None else CORE.utc(now_utc)
    result = {"contract": CONTRACT, "evidenceClass": "DRY_RUN_NOT_A_RECEIPT", "clockUtc": str(clock),
              "clock": "EXPLICIT_REPLAY_OF_A_PAST_INSTANT" if (replay_of_instant or now_utc is not None) else "WRITER_SYSTEM_CLOCK",
              "authorization": "NOT_REGISTERED" if R.REGISTERED_AUTHORIZATION is None else "REGISTERED_BUT_THIS_MODULE_NEVER_USES_IT",
              "inputIdentitySha256": inputs.identity.get("sha256"), "tradingValueBasis": inputs.trading_value_basis, "blockers": [], "notes": []}
    day = pd.Timestamp(signal_date) if signal_date is not None else latest_signal_session(clock)
    if day is None:
        result.update(state="BLOCKED", signalSession=None)
        result["blockers"].append("NO_FINAL_WEEKLY_DECISION_SESSION_WITHIN_%d_DAYS" % LOOKBACK_DAYS)
        return _finish(result)
    date = str(day.date())
    result["signalSession"] = date
    result["signalCloseFinalUtc"] = str((day + CORE.KR_CLOSE_FINAL_UTC).tz_localize("UTC"))
    if signal_date is not None and not CORE.is_weekly_decision_session(day):
        result["blockers"].append("SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")
    if (day + CORE.KR_CLOSE_FINAL_UTC).tz_localize("UTC") > clock:
        result["blockers"].append("SIGNAL_SESSION_CLOSE_NOT_FINAL_AT_THE_CLOCK")
    snapshot = inputs.memberships.on(date)
    if snapshot is None:
        result["blockers"].append("NO_PIT_MEMBERSHIP_SNAPSHOT_STRICTLY_OLDER_THAN_THE_SIGNAL_DATE")
    else:
        result["membershipSnapshotDate"] = snapshot["date"]
        result["universe"] = len(snapshot["members"])
    bench = inputs.prices.get(M.BENCHMARK)
    if bench is None or pd.Timestamp(date) not in bench.index:
        result["blockers"].append("NO_BENCHMARK_CLOSE_ON_THE_SIGNAL_SESSION_IN_THE_PINNED_PRICE_PANEL")
    if result["blockers"] or snapshot is None:
        result["state"] = "BLOCKED"
        return _finish(result)
    grid = RAF.weekly_grid("2013-01-01", date, "KR")
    matrix = M.build_matrix(inputs, grid[-(history_weeks + 1):], counters)
    result["historyWeeksBuilt"] = len(matrix.rows.date.unique()) - 1
    last = (matrix.rows.date == date).to_numpy()
    ids = list(eligible_features) if eligible_features else sorted(f for f in matrix.values.columns)
    measured = [{"feature": f, "measuredNames": int(matrix.values.loc[last, f].notna().sum())} for f in ids]
    thin = sorted(m["feature"] for m in measured if m["measuredNames"] < 30)
    result["featureRows"] = int(last.sum())
    result["measuredNamesPerFeature"] = measured
    result["featuresBelowThirtyMeasuredNames"] = thin
    result["matrixDigestOverTheBuiltWindow"] = matrix.digest()
    # The H2 contract's own readiness, fed the very rows the matrix produced: the weekly process and the study share one definition.
    v, rows = matrix.values[last], matrix.rows[last]
    records = S2.cross_section([_s2_row(rows.iloc[i], v.iloc[i], inputs, date) for i in range(len(rows))], date)
    result["h2Readiness"] = S2.readiness(records)
    result["h2Decision"] = {k: val for k, val in S2.decide(records, signal_date=date).items() if k in ("status", "reasons")}
    if thin:
        result["blockers"].append("%d_REGISTERED_FEATURES_HAVE_FEWER_THAN_30_MEASURED_NAMES_ON_THE_SIGNAL_DATE" % len(thin))
    result["state"] = "BLOCKED" if (not result["h2Readiness"]["ready"] and result["h2Readiness"]["coverage"]["eligible"] == 0) else "NOT_READY"
    result["notes"].append("NOT_READY because no authorization is registered; coverage above says what the data would support, not that a decision exists")
    return _finish(result)


def _s2_row(row, values, inputs, date):
    ticker = row["ticker"]
    pick = lambda f: (None if f not in values.index or pd.isna(values[f]) else float(values[f]))  # noqa: E731
    return {"ticker": ticker, "industry": row["industry"] if isinstance(row["industry"], str) else None, "isPreferredShare": None if pd.isna(row["isPreferredShare"]) else bool(row["isPreferredShare"]),
            "priceAsOf": date if row["tradableAtSignal"] else None, "positiveVolumeSessions20": None if pick("E04_tradabilityGuard20") is None else int(pick("E04_tradabilityGuard20")),
            "medianTradedValue60Krw": pick("E03_capacityMedianTradedValue60"), "fundamentalsAvailableFrom": row["filingAvailableFrom"],
            "bookToMarketProxy": pick("B01_bookToMarket"), "earningsYieldProxy": pick("B02_earningsYield"), "netIncomeToAssets": pick("C01_returnOnAssets"),
            "ocfToAssets": pick("C05_ocfToAssets"), "ocfImprovementToAssets": pick("C14_ocfImprovement"), "relative126": pick("A05_relative126"),
            "downsideVol126": pick("F02_downsideVol126"), "maxDrawdown252": pick("F05_maxDrawdown252")}


def _finish(result):
    if result["state"] not in STATES:
        raise ValueError("DRY_RUN_STATE_NOT_ALLOWED: " + str(result["state"]))
    assert_not_actionable(result)
    return result
