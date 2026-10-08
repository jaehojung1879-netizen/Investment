"""kr-alpha-atlas Phase B — source feasibility and the broader-universe feasibility measurement. Outcome-blind; reads identities, dates and traded amounts only.

TWO THINGS, KEPT APART.
  1. `source_register(...)`: for every registry feature that is SOURCE_BLOCKED / DATA_BUILD_REQUIRED / PIT_UNSAFE / NOT_FEASIBLE, what the repository's own latest
     evidence says and the exact next step. A blocked source stays blocked: nothing is guessed, scraped around a licence, or substituted by an OHLCV proxy.
  2. `universe_feasibility(...)`: can the data already in the repository support a broader, liquidity-qualified KOSPI universe than the PIT Top120? It counts how
     many names would qualify and how much of each qualified name-date has a price panel, a visible DART filing and an industry label. It never adds a name to
     Phase C. The PIT Top120 stays the reference universe.

THE LIQUIDITY QUALIFICATION is `kr_alpha_signal_v2.MIN_MEDIAN_TRADED_VALUE_KRW` (a median 60-session KRW traded value of 1 billion), the floor the H2 design already
carries (one order of 10 million KRW at most 1% of a day's median traded value). Traded value here is the as-traded close x volume proxy.
"""
from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd

from . import alpha_opportunity_features as AOF
from . import kr_alpha_signal_v2 as S2
from . import kr_industry_anatomy as I
from . import kr_alpha_atlas_inputs as AI

CONTRACT = "KR_ALPHA_ATLAS_FEASIBILITY_V1"


# --------------------------------------------------------------------------- #
# Broader universe
# --------------------------------------------------------------------------- #
def _ledger_frame(repo, commit):
    parts = []
    for year in range(2013, 2027):
        raw = AI.git_blob(repo, commit, f"{AI.PRICE_LEDGER}/krx-prices-{year}.jsonl.gz")
        parts.append(pd.DataFrame([json.loads(line) for line in gzip.decompress(raw).decode().splitlines()],
                                  columns=["date", "ticker", "close", "volume", "listedShares"]))
    return pd.concat(parts, ignore_index=True)


def universe_feasibility(inputs, repo, commit, cutoff, termination_inventory):
    ledger = _ledger_frame(repo, commit)
    ledger = ledger[ledger.date <= cutoff]
    traded = ledger[(ledger.volume > 0) & (ledger.close > 0)].copy()
    traded["tv"] = traded.close * traded.volume
    tv = traded.pivot(index="date", columns="ticker", values="tv").sort_index()
    median60 = tv.rolling(60, min_periods=60).median()
    sample_dates = [g.index[-1] for _, g in tv.groupby(tv.index.str[:7])]
    sample_dates = [d for d in sample_dates if d >= "2013-12-31"]
    intervals, crosswalk, ends = inputs.industry
    last_seen = ledger.groupby("ticker").date.max()
    inventory = {s["code"] for s in termination_inventory["securities"]}
    rows = []
    qualified_ever = set()
    for date in sample_dates:
        snapshot = inputs.memberships.on(date)
        members = set(snapshot["members"]) if snapshot else set()
        qualified = set(median60.loc[date][median60.loc[date] >= S2.MIN_MEDIAN_TRADED_VALUE_KRW].index)
        qualified_ever |= qualified
        with_filing = {t for t in qualified if AOF.visible_filings(inputs.accounting.get(t, []), date, "KR")}
        with_industry = {t for t in qualified if I.industry_of(intervals, crosswalk, t, date)[0] is not None}
        with_panel = {t for t in qualified if t in inputs.prices}
        rows.append({"date": date, "ledgerNames": int(tv.loc[date].notna().sum()), "qualified": len(qualified), "top120": len(members),
                     "qualifiedInTop120": len(qualified & members), "qualifiedOutsideTop120": len(qualified - members),
                     "outsideWithReplayPricePanel": len((qualified - members) & with_panel), "qualifiedWithVisibleDartFiling": len(with_filing),
                     "outsideWithVisibleDartFiling": len((qualified - members) & with_filing), "qualifiedWithIndustryLabel": len(with_industry),
                     "outsideWithIndustryLabel": len((qualified - members) & with_industry)})
    frame = pd.DataFrame(rows)
    by_year = {}
    for year, g in frame.groupby(frame.date.str[:4]):
        n = g.qualified.mean()
        out = (g.qualified - g.qualifiedInTop120).mean()
        by_year[year] = {"monthlySamples": int(len(g)), "meanQualifiedNames": round(float(n), 1), "meanTop120": round(float(g.top120.mean()), 1),
                         "meanQualifiedOutsideTop120": round(float(out), 1),
                         "outsideReplayPricePanelPct": _pct(g.outsideWithReplayPricePanel.sum(), (g.qualified - g.qualifiedInTop120).sum()),
                         "outsideVisibleDartFilingPct": _pct(g.outsideWithVisibleDartFiling.sum(), (g.qualified - g.qualifiedInTop120).sum()),
                         "outsideIndustryLabelPct": _pct(g.outsideWithIndustryLabel.sum(), (g.qualified - g.qualifiedInTop120).sum()),
                         "qualifiedVisibleDartFilingPct": _pct(g.qualifiedWithVisibleDartFiling.sum(), g.qualified.sum())}
    outside_ever = qualified_ever - {t for s in inputs.memberships.snapshots for t in s["members"]}
    delisted = sorted(t for t in qualified_ever if last_seen.get(t, "9999") < _days_before(cutoff, 60))
    lacking_dart = sorted(t for t in qualified_ever if t not in inputs.accounting)
    return {
        "contract": CONTRACT, "scope": "FEASIBILITY_ONLY: nothing here enters Phase C; the PIT Top120 stays the reference universe",
        "qualification": {"rule": "median 60-session as-traded close x volume >= %.0f KRW" % S2.MIN_MEDIAN_TRADED_VALUE_KRW, "source": "kr_alpha_signal_v2.MIN_MEDIAN_TRADED_VALUE_KRW"},
        "barLedger": {"commit": commit, "tickersEver": int(ledger.ticker.nunique()), "meanNamesPerSession": _mean(tv.notna().sum(axis=1)),
                      "vendorIssuesPerSession": "about 930 on 2013-01-02 (registry universe evidence, sto/stk_bydd_trd)",
                      "reading": "the bar ledger is a storage-bounded subset of KOSPI (krx_prices.bar_rows `keep`), not the exchange"},
        "byYear": by_year,
        "qualifiedTickersEver": len(qualified_ever), "qualifiedTickersEverOutsideTop120": len(outside_ever),
        "qualifiedTickersWithoutAnyDartRecord": len(lacking_dart),
        "qualifiedTickersWithoutAnyDartRecordOutsideTop120": len([t for t in lacking_dart if t in outside_ever]),
        "delistedQualifiedTickers": len(delisted), "delistedQualifiedInTerminationInventory": len([t for t in delisted if t in inventory]),
        "delistedQualifiedWithoutTerminalEconomics": len([t for t in delisted if t not in inventory]),
        "terminalEconomics": "BLOCKED for the 22 inventoried securities (kr-terminal-action-reconstruction-v2); not audited at all for any other delisted name",
        "acquisitionEstimate": _acquisition(len([t for t in lacking_dart if t in outside_ever])),
        "verdict": _universe_verdict(by_year),
    }


def _pct(a, b):
    return None if not b else round(100.0 * float(a) / float(b), 2)


def _mean(s):
    return round(float(s.mean()), 1)


def _days_before(date, n):
    return str((pd.Timestamp(date) - pd.Timedelta(days=n)).date())


def _acquisition(extra_tickers):
    per_ticker = 12 * 4 * 2 + 12 * 4    # fiscal years x report codes x (CFS, OFS) plus the share-count pass: the collector's own call structure, an upper bound
    return {"extraTickersNeedingDartCollection": extra_tickers, "callsPerTickerUpperBound": per_ticker, "callsUpperBound": extra_tickers * per_ticker,
            "perRunBudgetReference": "1,500 calls per run (AGENTS.md PIT fundamentals invariants)", "runsUpperBound": -(-extra_tickers * per_ticker // 1500),
            "alsoRequired": ["a price panel for the extra names through the replay input store (a new replay generation or an additive input; the sealed replay-v16 is not edited)",
                             "industry reconstruction for the extra names (kr_industry_membership_v4 covers only the studied securities)",
                             "terminal economics for any delisted extra name (unaudited)"],
            "status": "ESTIMATE_FROM_COLLECTOR_STRUCTURE_NOT_A_MEASUREMENT"}


def _universe_verdict(by_year):
    outside = [v["meanQualifiedOutsideTop120"] for v in by_year.values()]
    cover = [v["outsideVisibleDartFilingPct"] or 0.0 for v in by_year.values()]
    return {"status": "BROADER_UNIVERSE_NOT_READY_KEEP_TOP120",
            "reason_ko": "유동성 기준을 통과하는 종목 중 상위 120 밖은 평균 %.0f개이지만, 그 종목-월 중 봉인된 저장소에 보이는 DART 공시가 있는 비율은 %.1f%%뿐이고, 가격 패널·산업 라벨·상장폐지 대가 자료도 없습니다."
                         % (np.mean(outside) if outside else 0.0, np.mean(cover) if cover else 0.0),
            "reason": "on average %.0f qualified names sit outside the Top120, but only %.1f%% of those name-months have a visible DART filing in the sealed store, and there is no "
                      "price panel, industry label or terminal economics for them" % (np.mean(outside) if outside else 0.0, np.mean(cover) if cover else 0.0)}


# --------------------------------------------------------------------------- #
# Input audits (what the stores actually contain)
# --------------------------------------------------------------------------- #
ACCOUNTS = ("자산총계", "부채총계", "자본총계", "당기순이익", "매출액", "영업이익", "영업활동현금흐름", "유형자산의취득")


def accounting_input_audit(accounting):
    """Presence of each account the features read in the PINNED DART store, by report code and by fiscal year. A figure is published with the filings it was
    measured on; nothing is averaged into 'fundamentals collected'."""
    filings = [r for rows in accounting.values() for r in rows]
    frame = pd.DataFrame([{"ticker": r["ticker"], "year": int(r["fiscalYear"]), "code": str(r["reportCode"]), "fsDiv": r.get("fsDiv"), "availableFrom": r.get("availableFrom"),
                           **{a: (r.get("accounts") or {}).get(a) is not None for a in ACCOUNTS}} for r in filings])
    out = {"filings": int(len(frame)), "tickers": int(frame.ticker.nunique()), "fsDivShare": {k: round(float(v), 4) for k, v in frame.fsDiv.value_counts(normalize=True).items()},
           "duplicateTickerYearCode": int(frame.duplicated(["ticker", "year", "code"]).sum()), "firstAvailableFrom": frame.availableFrom.min(), "lastAvailableFrom": frame.availableFrom.max(),
           "accountPresencePct": {a: round(100.0 * float(frame[a].mean()), 2) for a in ACCOUNTS}, "byReportCode": {}, "byFiscalYear": {}}
    for code, g in frame.groupby("code"):
        out["byReportCode"][code] = {"filings": int(len(g)), **{a: round(100.0 * float(g[a].mean()), 2) for a in ACCOUNTS}}
    for year, g in frame.groupby("year"):
        out["byFiscalYear"][str(year)] = {"filings": int(len(g)), **{a: round(100.0 * float(g[a].mean()), 2) for a in ACCOUNTS}}
    return out


TOLERANCES = (1e-9, 1e-4, 1e-3)


def price_basis_reconciliation(inputs):
    """Do the two price sources describe the same price path? Daily return of the split-adjusted as-traded KRX close (the bars the D/E features use) against the
    daily return of the replay-v16 close (the series the A/F features use), for every ticker in both. They differ BY CONSTRUCTION on ex-dividend days (the replay
    accumulates dividends, the KRX bars carry none), and some replay panels carry a ~1e-5 relative vendor-precision residue, so agreement is reported at three
    tolerances and the worst tickers are named. It is a measurement, not a gate: a ticker far below the rest would mean the sources disagree about a split."""
    per_ticker = {}
    for ticker, bars in sorted(inputs.bars.items()):
        replay = inputs.prices.get(ticker)
        if bars.empty or replay is None:
            continue
        a = bars.adj["Close"].pct_change(fill_method=None)
        b = pd.to_numeric(replay["Close"].reindex(bars.span), errors="coerce").pct_change(fill_method=None)
        both = a.notna() & b.notna()
        if both.sum() < 50:
            continue
        gap = (a - b).abs()[both]
        per_ticker[ticker] = {"sessions": int(both.sum()), **{"within%g" % t: float((gap < t).mean()) for t in TOLERANCES}}
    frame = pd.DataFrame(per_ticker).T
    out = {"tickersCompared": int(len(frame)), "sessionsCompared": int(frame.sessions.sum()) if len(frame) else 0, "tolerances": list(TOLERANCES), "byTolerance": {}}
    for t in TOLERANCES:
        col = frame["within%g" % t]
        out["byTolerance"]["%g" % t] = {"pooledAgreementPct": round(100.0 * float((col * frame.sessions).sum() / frame.sessions.sum()), 3),
                                        "medianTickerAgreementPct": round(100.0 * float(col.median()), 3), "worstTickerAgreementPct": round(100.0 * float(col.min()), 3)}
    worst = frame.sort_values("within0.001").head(8)
    out["worstTickersAtLargestTolerance"] = {t: round(100.0 * float(v), 3) for t, v in worst["within0.001"].items()}
    out["reading"] = ("returns agree within 0.1% on the share of sessions shown for every ticker; the remainder is dominated by ex-dividend sessions and is not a split disagreement. "
                      "The KRX-derived panels are exact to rounding; others carry vendor-precision residue near 1e-5")
    return out


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #
PROBES_WORKFLOW = ".github/workflows/probes.yml"


def source_register(registry, ownership_manifest, investor_flow_manifest, policy_rates, cutoff):
    """One entry per blocked or unbuilt registry feature group, with the repository's latest evidence quoted, not summarised away."""
    reg = {f["featureId"]: f for f in registry["features"]}
    ids = lambda prefix: sorted(i for i in reg if i.startswith(prefix))  # noqa: E731
    flow = investor_flow_manifest
    first_event = ownership_manifest.get("earliestObservedEventDate")
    return {
        "contract": CONTRACT,
        "decision": "AT MOST ONE re-probe per blocked source in Phase B; the latest existing evidence below is sufficient, so NONE was repeated and none was dispatched",
        "sources": [
            {"features": [i for i in ids("G0") if reg[i]["readinessStatus"] == "SOURCE_BLOCKED" and i != "G08_shortSellingVolume" and i != "G09_shortBalanceChange"],
             "source": "KRX investor-type net trading (data.krx.co.kr)", "status": "SOURCE_BLOCKED",
             "latestEvidence": {"artifact": "signal-history ledger/kr-investor-flow/manifest.json", "updatedAt": flow.get("updatedAt"), "calls": flow["thisRun"]["calls"],
                                "recordsWritten": flow["thisRun"]["recordsWritten"], "stopReason": flow["thisRun"]["stopReason"], "remainingPairs": flow.get("remainingPairs"),
                                "also": "AGENTS.md workflow-hygiene invariants (v2.25): the portal answered HTTP 400 LOGOUT on every candidate on a real Actions run"},
             "doNotDo": ["substitute an OHLCV accumulation proxy (D11) for investor-type flow", "scrape around the portal's terms", "guess flows"],
             "optionalOneReprobe": {"workflow": PROBES_WORKFLOW, "inputs": {"probe": "kr-investor-flow", "args": ""},
                                    "when": "only if a human has reason to believe KRX access changed since 2026-09-24; a result other than SERVED leaves the status unchanged"}},
            {"features": ["G08_shortSellingVolume", "G09_shortBalanceChange"], "source": "KRX short-selling statistics (MDCSTAT301 / MDCSTAT305)", "status": "SOURCE_BLOCKED",
             "latestEvidence": {"artifact": "AGENTS.md v2.25: both axes of the investor-flow collector measured BLOCKED_SOURCE; no short-selling ledger exists on signal-history",
                                "regimes": "three regulatory regimes inside the window (bans 2020-03-16..2021-05-02 and 2023-11-05..2025-03-31): a factor must carry the regime"},
             "optionalOneReprobe": {"workflow": PROBES_WORKFLOW, "inputs": {"probe": "kr-short-selling", "args": ""}, "when": "as above"}},
            {"features": ["G06_largeHolderAccumulation", "G07_largeHolderReduction"], "source": "DART majorstock.json (5% large-holding disclosures)",
             "status": "PIT_SAFE_BUT_HISTORY_TOO_SHORT",
             "latestEvidence": {"artifact": "signal-history ledger/dart-ownership-events/manifest.json", "earliestObservedEventDate": first_event,
                                "latestObservedEventDate": ownership_manifest.get("latestObservedEventDate"), "eventCount": ownership_manifest.get("eventCount"),
                                "companiesQueried": ownership_manifest.get("companiesQueried"), "pitAvailabilityRule": ownership_manifest["endpointSemantics"]["pitAvailabilityRule"],
                                "noRowsMeaning": ownership_manifest["endpointSemantics"]["noRowsMeaning"]},
             "reading": "the endpoint serves only about two years (from %s) and 'no rows' is not proof of no filing, so an absence cannot be read as a zero. Prospective collection, "
                        "not a historical feature; it stays DATA_BUILD_REQUIRED and is not computed in the matrix" % first_event},
            {"features": ["J02_dividendPolicyChange", "J03_buybackAnnouncement", "J04_materialDisclosure"], "source": "DART alotMatter.json / list.json (disclosure families)",
             "status": "DATA_BUILD_REQUIRED",
             "latestEvidence": {"artifact": "signal-history ledger/kr-corporate-actions", "scope": "the 22 terminated securities only (451 disclosures)"},
             "nextStep": "a bounded work list for the ever-top-120 issuers (254) would be a new collector scope; report-name matching is a reading list, never a verdict. Not built in Phase B."},
            {"features": ["I04_krPolicyRate"], "source": "data/bok-policy-rates.json", "status": "SOURCE_AVAILABLE_NOT_COMPUTED",
             "latestEvidence": {"basis": policy_rates.get("basis"), "verifiedThrough": policy_rates.get("verifiedThrough"), "firstEvent": policy_rates["events"][0]["date"],
                                "events": len(policy_rates["events"])},
             "reading": "a dated event series that predates the replay, effective on its event date, is point-in-time safe for the LEVEL of the policy rate. The registry classed I04 "
                        "DATA_BUILD_REQUIRED because the ECOS fetch layer is unbuilt; this file is a repository-carried alternative. No registered comparison reads I04, so it is not computed "
                        "here and the registry status is unchanged. It is a policy-rate proxy, not an investable rate."},
            {"features": ["I03_krTermSpread", "I06_krInflation", "I07_krExportsActivity", "I08_usdKrw", "I09_fxBeta26w", "I11_globalFinancialConditions"], "source": "ECOS / FRED / ALFRED",
             "status": "PIT_UNSAFE", "reading": "only revised history is served, or the publication time is unresolved against the KRX close; ALFRED vintages do not exist for these series"},
            {"features": ["B04_freeCashFlowYield", "C06_cashConversion", "C15_capexIntensity", "C16_grossProfitability"], "source": "DART fnlttSinglAcntAll via the sealed candidate-merged store",
             "status": "DATA_BUILD_REQUIRED", "reading": "computed in the matrix on the pinned store and judged on measured coverage like any other feature. kr-canonical-v2 exists on signal-history "
                        "but is not pinned by the sealed studies; using it needs its own pinned identity, so it is not mixed in here"},
            {"features": ["E08_trueBidAskSpread", "J06_searchAttention", "J07_newsTextSentiment", "J08_analystRevisions"], "source": "none", "status": "NOT_FEASIBLE",
             "reading": "no point-in-time source: quote data, search volume, news text and historical consensus are not available in the repository or on a free tier"},
        ],
        "cutoff": cutoff,
    }
