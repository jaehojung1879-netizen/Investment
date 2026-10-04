# KR market risk anatomy v1 — long-history preregistration

Status: `PROTOCOL_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED`. Scientific label: `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`.

This document is the **PRE-SOURCE FREEZE**. Its machine-readable twin is `research_specs/kr-market-risk-anatomy-v1-design.json` (SHA-256 sidecar). It was
committed together with the pure algorithms and their synthetic tests **before any source value was acquired or inspected**, and it is never edited afterwards.

## 1. Role and status

This is the MARKET layer of MARKET → INDUSTRY → STOCK: *how much equity risk should be taken?* It does not rank stocks or industries, does not try to predict a
crash date, does not search for a market-timing rule, and is not a portfolio study. The conceptual sequence it examines is

    SLOW VULNERABILITY -> TRANSITION / FINANCIAL STRESS -> FAST MARKET BREAK -> (a later, separate) risk-budget decision

The KR market history is already known to the researchers and to this repository. "Exploratory development on outcome-exposed history" therefore means: rules
frozen before this study's formal outcome execution; not prospective confirmation; not validated, predictive or production-ready. Preregistration and the
one-shot execution protect against post-outcome tuning inside this study; they do not make the sample independent.

## 2. Long history, two tiers

* `CORE_LONG_HISTORY` — the KR benchmark price index plus market-observed series (Treasury curve, policy rate, credit spreads, VIX, USD/KRW). It is **not**
  truncated to the start of the internals tier and must be able to include 2008. Every result states its real start, end and coverage.
* `EXTENDED_KR_INTERNALS` — breadth, cap-versus-equal-weight divergence, dispersion and concentration, only where a PIT universe exists (PIT Top120 from
  2015-01-02). Never reconstructed from today's constituents; not part of the readiness decision.

## 3. Primary KR market reference

Frozen identity rule (no splice, no silent substitution, never chosen on result quality): walk the KOSPI 200 price-index routes in priority order
`KRX_OPENAPI_KOSPI200` (documented blocker: the service history starts 2010-01-04 and the data portal refuses Actions), `YAHOO_KS200`, `FDR_KS200`; only if none
passes every identity/coverage/semantics test may the KOSPI composite price index (`YAHOO_KS11`, a different instrument, stated as such) be chosen. KODEX 200
(`YAHOO_069500`, as-traded close, dividends not reinvested) is a robustness reference only. The basis is a PRICE INDEX LEVEL and is never called total
shareholder return. Tests (dates only): first date <= 2005-12-31, >= 99% of XKRX sessions in 2007-2009 and 2019H2-2020, >= 98% over the whole range, no run of more
than 5 missing sessions, <= 0.5% invalid rows, fresh last date, no vendor conflict against another route to the same index.

## 4. Point-in-time discipline

Market-observed unrevised quotes (Treasury yields, effective fed funds, VIX, USD/KRW H.10, ICE spreads via FRED; Yahoo as the registered secondary for VIX and USD/KRW)
are usable with a conservative availability lag (observation date + 4 / 8 / 1 calendar days) and are labelled
`MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY` — never `PIT_EXACT`. A feature at KR session t sees the latest observation whose availability date is <= t; a carried
value older than 14 days is missing. `REVISED_HISTORY` (ECOS everything, OECD KR rates, NFCI/ANFCI) is never backdated and never a primary predictor; the Excess Bond Premium
and the Near-Term Forward Spread are not built (no defensible historical vintage / unverified construction); a KR term spread has no comparable validated legs.
Missing stays missing: no back-fill, no future interpolation, no current value stamped onto history. A secondary source replaces a primary only when the primary fails the
frozen 2007-2009 coverage gate, and never both.

## 5. Signal families (frozen; orientation always "higher = more downside risk")

* **Slow vulnerability (monthly, H126/H252):** 10y-3m and 10y-2y flatness, inversion duration, re-steepening after an earlier inversion, fed funds level and 126-session change.
* **Transition / financial stress (weekly, H63/H126):** HY and IG OAS level/change, VIX level/change, USD/KRW change and realised volatility, easing flags. A cut by itself is not
  declared bearish: `trans_benign_easing_flag` (easing, no inversion in 504 sessions, stress not worsening) is registered against `trans_post_vulnerability_stress_easing_{hy,vix}_flag`
  (easing after inversion with an expanding-percentile stress reading >= 0.75).
* **Fast market break (daily state, weekly snapshots, H21/H63):** SMA200 distance and slope, 63/126-session return, drawdown from the 252-session high, 21/63-session realised
  volatility, downside volatility, volatility acceleration; the existing overlay (price below SMA200, vol63 > 25%, multipliers 1.0/0.7/0.4) is preserved as a frozen BASELINE
  and reproduced by a literal replica proven equal to `kr_market_risk_overlay.state_at`, plus a trailing-drawdown trigger.
* **KR internals (EXTENDED only, weekly):** fraction above SMA200, positive-return breadth, breadth deterioration, cap-minus-equal-weight 63-session return, dispersion, top-five share.

Common H63/H126 tables compare families without pretending identical half-lives.

## 6. Future-path targets and downside labels

For horizon H at session p: forward return; forward worst loss from the signal = min(close[p+1..p+H])/close[p]-1; future max drawdown over close[p..p+H]; future realised volatility.
Event labels: worst loss <= -10%, <= -15%, <= -20% (cutoffs frozen). A window with a missing session is unresolved, never filled.

## 7. Drawdown episodes (algorithmic; nothing named by hand)

Deterministic underwater episodes on the primary benchmark: a close >= the running peak recovers any open episode and restarts the peak; a lower close opens an episode whose trough is the
first lowest close; an episode open at the end is right-censored. Reported at -10%, -15% (primary) and -20%. For every >= 15% episode: peak, trough, depth, recovery or censoring, and the
latest-known state of every family at the fixed landmarks (peak-252/126/63/21, peak, first -5/-10/-15%, trough) — the direct test of whether slow vulnerability came first, stress then
transitioned, and the market finally broke.

## 8. Early damage, false alarms and recovery cost

For each frozen binary trigger (existing-overlay legs, overlay any/both, trailing -10% drawdown): per episode the loss at trigger, damage fraction (continuous distribution plus the share
triggered before 20% and before 50% of the eventual drawdown), remaining drawdown after the trigger, trigger delay and missed episodes; slow warnings' pre-peak lead reported separately.
For false alarms: activations, time adverse, the share of ON and OFF sessions followed within H63/H126 by -10/-15/-20%, activation streaks with no -10% drawdown within H63, and after each
trough the sessions until the trigger's own off-state with the return missed meanwhile. No re-entry rule is optimised; risk-budget backtesting belongs to `kr-market-risk-model-v1`.

## 8b. Statistics

One time series, not a cross-sectional IC: time-series Spearman versus loss severity, max-drawdown severity and realised volatility; event rates (unconditional and when the past-only
percentile state is >= 0.80); AUROC when >= 10 events and non-events; a descriptive Newey-West standard error of the rank correlation; calendar-year tables; exact valid dates, event counts,
start and end. Percentiles are expanding and past-only (minimum 36 monthly / 156 weekly / 756 daily observations) and the state at t is identical whether the data end at t or in 2026. No
winner, no multiplicity correction, no "validated" or "predictive" language.

## 9. Hypotheses (registered, not truths)

H1 slow inversion carries more at H126/H252 than H21. H2 a cut alone is not adverse; easing after vulnerability with worsening stress may be. H3 widening credit/external stress carries
transition information. H4 fast trend/vol deterioration identifies the early part of a developing drawdown rather than predicting the crisis. H5 the existing overlay may cut remaining drawdown
at a measurable false-alarm and recovery-delay cost. H6 breadth adds information beyond the index in the shorter PIT-safe sample. H7 a slow -> transition -> fast sequence may beat any one
signal; this study does not optimise or select a combination. Literature (Estrella-Mishkin; Engstrom-Sharpe; Federal Reserve term-spread work; Gilchrist-Zakrajsek; Favara et al.) is motivation only.

## 10. Readiness and lifecycle

`READY_FOR_MARKET_RISK_ANATOMY_EXECUTION` only if, from observation dates alone, the primary reference, one slow family, one transition family (market stress: credit spread, VIX or USD/KRW; policy-only easing flags do not count) and one fast benchmark-derived family cover
2007-2009 and usable coverage exists around 2020; every missing candidate keeps its own coverage table. Otherwise `DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY` with exact blockers; the study is
never quietly redefined as 2015+. After this freeze, source work may only verify identity, bytes, hashes, dates, missingness, timestamps and units; it may not compute returns, drawdowns or episodes,
produce result tables, or tune anything. Formal execution is a manual dispatch from merged `main` with the committed spec, frozen input identities, no prior result or lock, label-free gates
first, then the durable git-tag lock, then the first outcome; failure after the lock consumes v1.

## 11. Limitations

One market series with few independent stress episodes; a historically known sample; approximate availability dates (no source is PIT_EXACT); a price index, not total return; no KR policy
rate, KR term spread, NTFS or EBP; extended internals start in 2015 and rely on the preserved raw artifact; no multiplicity correction.
