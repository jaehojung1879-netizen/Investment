# Portfolio D evidence authority — official / paper / research

**Documentation-only classification.** Does not migrate, erase, publish,
trade, change an allocator, or upgrade scientific admission.

| Stored surface | Role | Authority |
|---|---|---|
| `signal-history:ledger/weekly-decisions/latest.json` | Current regional KR/US weekly-policy summary | Sole operating policy display, **not** broker execution or proven live alpha |
| `signal-history:ledger/weekly-decisions/receipts.jsonl` | Immutable historic dated FINAL weekly-policy receipts | Records what was published; PREVIEW is not FINAL |
| `signal-history:state/latest.json` | Previous Kelly model `modelPortfolioWeights`, `holdingsByRegion` and `entryStatesByTicker` | **Internal/research model only**; cannot override weekly ETF fallback |
| `signal-history:ledger/research-strategies/*` | Challenger/paper receipts, outcomes, assessments | Exploratory; skipped run is **not** 0 eligible, and missing results are UNKNOWN |
| `pipeline/market_research_c1c_*`, PR #289 | C0/C1 historical hypotheses and synthetic diagnostics | No approved source, economic evidence, authority or live promotion |
| `pipeline/daily_decision_report.py` and `pipeline/daily_decision_delta.py` | Read-only Portfolio D briefs and two-date comparisons | Report-only; no fresh selection, backtest, orders or ledger writes |

## Required display and reporting behavior

1. Show only **one** policy decision per region (KR `069500.KS`, US `SPY`
   until separately eligible stock evidence exists); display exact effective
   week, FINAL vs PREVIEW, verification and source-freshness caveats.
2. Keep older Kelly weights, experimental watchlists, Market B/C and stock
   challengers under clearly separate **RESEARCH / EXPERIMENTAL** headings.
3. A report-as-of date, actual observed session, pipeline generation time and
   source publication timestamp are different and may be missing. Do not
   display an old `FRESH` state as if current.
4. Absence of official ETF total-return quotation, exact source rights,
   final price, paper eligibility or matured outcome is **UNKNOWN**, not 0.
5. CI success, paper PASS, favorable risk sign or model weight is never
   investment-grade net alpha or a model-promotion decision.
6. Preserve original Kelly observations as research evidence. Never delete
   them merely to make operating and research views agree.
7. For any later user-interface change, preserve original weekly receipts,
   `state/latest.json` and production byte identities. Test and review the
   separate UI PR without changing the research/spec seals.

**Objective is unchanged:** historical exploration plus future prospective
validation of risk-adjusted net return opportunities. ETF-first is the
current default policy, not the end of alpha research.
