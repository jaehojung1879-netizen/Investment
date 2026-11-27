# entry-state-role-etf-residual-v1: calendar and return-basis limitations (added after the run; no number changed)

Raised in an independent connection check on #304 (comment 6553261817). Re-measured here from the committed files.

1. **Daily NAV grid is KRX∪NYSE, not the regional calendar.** `replay_valuation.window` marks on `RC.sessions(..., "UNION")`.
   The KR `nav-daily.csv.gz` series has 3,547 dates, 186 of which are not XKRX sessions (e.g. 2013-02-11, 2013-03-01,
   2013-05-01); on those days the KR marks are carried flat. All 3,361 XKRX sessions in the span are present. The checker
   counted 184 against its own raw calendar; the difference is calendar-version detail and is not reconciled here.
   Consequence: `annualizedVolPct`, `trackingErrorPct`, `informationRatio` and `dailyCvar95Pct` annualize with sqrt(252) over
   about 259 observations a year, including flat days, so they slightly understate daily dispersion. Drawdown is unaffected by
   flat days. CAGR is unaffected.
2. **H126 / H252 are measured in common sessions.** A horizon window is 6 / 12 consecutive 21-session blocks of the
   KRX∩NYSE common schedule (`RC.schedule`), i.e. 126 / 252 COMMON sessions. That is not 126 / 252 KR sessions or 126 / 252
   US sessions, and the result keys `H126` / `H252` must be read with that meaning.
3. **Return basis is replay-v16's, not the Phase C corrected basis.** `returnBasis =
   REPLAY_V16_CLOSE_WITH_FORWARD_ACCUMULATED_DISTRIBUTIONS_PARTIAL`. The 069500.KS headline here (14.866% CAGR, 2013-01-07 to
   2026-09-14) must not be spliced with a corrected-basis ETF series, and it is not a corrected investable benchmark. Both the
   strategies and the ETF line use the same basis, so the within-study contrasts are internally consistent.
4. The `ETF_ONLY` line's `costBasis NO_TRADE_NO_COST` means zero trading cost already charged. It never trades.

None of these change the frozen contrast or its reading: both regions' primary intervals contain zero.
