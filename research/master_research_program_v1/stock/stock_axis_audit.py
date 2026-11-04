"""S1-S5 stock-selection information-axis audit (Lane C, outcome-blind).

Builds three files from the axis table below, the G2 insider density gate result and the
report-name counts (both produced in this folder):

* ``stock-axis-audit-v1.json``  - every axis with overlap ids, mechanism, PIT source/access, G0/G1
* ``register-entries.json``     - RESEARCH_OPPORTUNITY_REGISTER entries (REGISTER_SCHEMA.md v1)
* ``STOCK_AXES.md``             - the human-readable table

Gate definitions used here (operational, this lane):
* G0 NOVELTY: the axis reads information that no Atlas-106 feature, Phase C candidate, regional-31
  feature, US-inventory factor or registered study already reads. A rename, re-weighting or
  recombination of those features FAILS G0 (momentum variants, value x quality composites...).
* G1 SOURCE: a free, licensed, point-in-time source is reachable from this project for 2013-2026 at
  the list level (receipt-dated), with the access verdict cited. Content parsing that has never run
  is stated as such and does not by itself fail G1.
* G2 DENSITY: only the insider axis has a measured G2 here (insider_density_gate.py).

No return, price after a filing, label, NAV, IC or model output is read anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "86c5983f"
MAIN = "37f8cbf6"
WT = "WORKTREE(uncommitted; base 86c5983f)"
REG = f"research_specs/kr-alpha-atlas-registry-v1.json@{MAIN}"
PC = f"research_specs/kr-alpha-atlas-phase-c-v1.json@{MAIN}"
R31 = f"pipeline/regional_alpha_features.py@{MAIN}"
USINV = f"docs/us-readiness/us-factor-inventory-v1.json@{MAIN}"
USSRC = f"docs/us-readiness/us-source-readiness-v1.json@{MAIN}"
OVL = f"research/alpha_evidence_sprint_v2/evidence/feature-overlap.md@{BASE}"
INV = f"docs/alpha-information-inventory-v1.md@{MAIN}"
EVC = f"research/master_research_program_v1/stock/kr-event-report-counts-v1.json@{WT}"
GATE = f"research/master_research_program_v1/stock/insider-density-gate-v1.json@{WT}"
SPRINT1 = f"research/alpha_mechanism_sprint_v1/data/dart-list/*-I.jsonl.gz@{BASE}"

CRITERIA = ("netReturnRelevance", "mechanism", "independence", "sourceObtainable", "timeToDecision", "krUsExtensible")


def ax(axis_id, region, title, mechanism, overlap, source, access, g0, g1, horizon, counts, scores, refs,
       blockers, next_unit, cost="PARTIAL: dated KR cost schedule exists (weekly_decision.trade_cost_fraction); "
                                  "turnover of an event basket is unmeasured until events are built"):
    return {"axisId": axis_id, "family": axis_id.split("-")[0], "region": region, "title": title,
            "economicMechanism": mechanism, "overlap": overlap, "pitSource": source, "accessStatus": access,
            "g0": g0, "g1": g1, "h126h252Feasibility": horizon, "measuredCounts": counts,
            "scores": dict(zip(CRITERIA, scores)), "evidenceRefs": refs, "blockers": blockers,
            "nextExecutionUnit": next_unit, "transactionCostMeasurable": cost}


P, F, PART = "PASS", "FAIL", "PARTIAL"
NONE = {"atlas": [], "phaseC": [], "regional31": [], "usInventory": [], "studies": []}


def ov(atlas=(), phase_c=(), r31=(), us=(), studies=()):
    return {"atlas": list(atlas), "phaseC": list(phase_c), "regional31": list(r31), "usInventory": list(us),
            "studies": list(studies)}


AXES = [
    # ------------------------------------------------------------------ S1 valuation & quality
    ax("S1-KR-VALUE-QUALITY-RECOMBINATION", "KR", "Industry/own-history value x business-confirmation composites",
       "Cheap names with confirming fundamentals re-rate; the information is accounting level + price.",
       ov(["B01_bookToMarket", "B02_earningsYield", "B05_industryRelativeValue", "B06_ownHistoryValuation",
           "B07_valuationChange126", "B08_valueBusinessConfirmation", "C01_returnOnAssets", "C14_ocfImprovement"],
          ["B06", "B07", "B08", "X1"], ["roe", "profitMargin", "operatingMargin"], ["A01", "A02", "A07", "B01"],
          ["kr-alpha-signal-v2 H2 = Phase C B08/X1 (X1 p 0.9895)", "kr-model-overlay-portfolio-v1 DEVELOPMENT_REJECT"]),
       "DART fnlttSinglAcntAll (receipt-dated) x KRX market cap", "READY (Phase B MEASURED_READY for B06-B08)",
       {"verdict": F, "reason": "ATLAS_RECOMBINATION: every input is an Atlas/Phase C feature already measured"},
       {"verdict": P, "reason": "sources sealed"}, "FEASIBLE but closed on this history", None,
       (1, 1, 0, 3, 3, 2), [REG, PC, OVL], ["Phase C/D 0 nominations"], "none: closed (Phase D)"),
    ax("S1-KR-ACCRUAL-CASH-QUALITY", "KR", "Accruals / cash conversion / OCF quality",
       "Earnings backed by cash persist; accrual-heavy earnings mean-revert.",
       ov(["C05_ocfToAssets", "C06_cashConversion", "C07_negativeAccruals", "C08_netIncomeMinusOcf", "C14_ocfImprovement",
           "B03_ocfYield"], [], [], ["B05", "B06", "B07", "B08", "B09"],
          ["accounting_quality ACCOUNTING_QUALITY_V1 (AGENTS v2.24)"]),
       "DART accounts (receipt-dated)", "READY; C06 below the 60% floor (Phase B)",
       {"verdict": F, "reason": "ALREADY_TESTED: C07/C08 PRIOR_NEGATIVE_DEVELOPMENT, C05/C14 inconclusive"},
       {"verdict": P, "reason": "sources sealed"}, "FEASIBLE but closed", None,
       (1, 2, 0, 3, 3, 2), [REG, f"AGENTS.md@{MAIN} v2.24, v2.54"], [], "none: closed"),
    ax("S1-KR-DIVIDEND-POLICY-CHANGE", "KR", "Cash-dividend decision changes (initiation / increase / cut)",
       "A dividend change is a costly signal of management's view of persistent earnings; Korea's 2024+ "
       "value-up regime changes the base rate.",
       ov(["J02_dividendPolicyChange (DATA_BUILD_REQUIRED, UNTESTED, not in Phase C)"], [], [], ["F01", "F02", "F04"],
          ["us-capital-allocation-alpha-v1 (US analogue, registered, not executed)"]),
       "DART list.json I-type 현금ㆍ현물배당결정 (receipt date) + document/alotMatter.json for amounts",
       "LIST READY (254 issuers already collected, 0 new calls); amount fields CANDIDATE (alotMatter served live per "
       "AGENTS v2.29 probe, per fiscal year)",
       {"verdict": P, "reason": "never measured; reads corporate payout DECISIONS, not price or accounting levels"},
       {"verdict": P, "reason": "4,010 decision filings / 229 issuers 2012-10..2026-10; per-anchor median 99 of ~117 "
                               "covered Top-120 members with a decision in the trailing 252 sessions"},
       "FEASIBLE with caveat: KR distribution basis of the label is PARTIAL (Yahoo), worst exactly for payers",
       "see kr-event-report-counts-v1.json I counts CASH_DIVIDEND_DECISION", (1, 2, 2, 2, 2, 3), [EVC, SPRINT1, REG],
       ["amount parse not built", "label distribution basis PARTIAL for dividend payers (AGENTS v2.42)"],
       "parse the decision's per-share amount for the 24-issuer sample (outcome-blind) and measure change density"),
    ax("S1-US-CAPITAL-ALLOCATION", "US", "Distribution change / payout over OCF (US)",
       "Payout decisions signal management's private view of cash-flow durability.",
       ov([], [], [], ["F01", "F02", "F03", "F04", "F05", "F06"], ["us-capital-allocation-alpha-v1 (registered)"]),
       "Finnhub PIT store", "AVAILABLE_WITH_CAVEATS (F01-F03), F05/F06 NEEDS_VERIFICATION",
       {"verdict": F, "reason": "DUPLICATE_OF_REGISTERED_STUDY us-capital-allocation-alpha-v1"},
       {"verdict": P, "reason": "per us-factor-inventory-v1"}, "PROSPECTIVE_ONLY (registered prospective)", None,
       (1, 2, 1, 2, 1, 2), [USINV, f"docs/us-capital-allocation-alpha-v1.md@{MAIN}"], ["owner authorization None"],
       "none here: owned by us-capital-allocation-alpha-v1"),
    ax("S1-US-CASH-PROFITABILITY", "US", "Cash operating profitability (US)",
       "Cash-based profitability predicts returns beyond accrual earnings.",
       ov(["C05_ocfToAssets"], [], ["roe", "operatingMargin"], ["B04", "B05", "B07"],
          ["us-cash-profitability-study-protocol-v1"]),
       "Finnhub PIT store", "SURVIVOR_CONDITIONED (US panel)",
       {"verdict": F, "reason": "DUPLICATE_OF_REGISTERED_STUDY us-cash-profitability-study-protocol-v1"},
       {"verdict": PART, "reason": "212 unpriced departed identities (AGENTS v2.27)"}, "BLOCKED: survivorship", None,
       (1, 2, 1, 1, 1, 2), [USINV, f"docs/us-readiness/us-cash-profitability-study-protocol-v1.json@{MAIN}"], [],
       "none here"),
    # ------------------------------------------------------------------ S2 earnings & expectations
    ax("S2-KR-PRELIMINARY-EARNINGS", "KR", "Preliminary (잠정) earnings vs formal filing",
       "Under-reaction to early earnings news.",
       ov(["C-family levels/changes"], ["C02", "C09", "C12"], ["earningsGrowth", "delta_*"], [],
          ["alpha-mechanism-sprint-v1 (#308)"]),
       "DART I-type 영업(잠정)실적", "READY (collected)",
       {"verdict": F, "reason": "97.5% of revenue within 1% of the formal filing; only ~12 KRX-day timing gain (#308)"},
       {"verdict": P, "reason": "collected"}, "FEASIBLE", None, (1, 1, 0, 3, 2, 1),
       [f"research/alpha_mechanism_sprint_v1/REPORT.md@{BASE}", OVL], [], "none: closed as re-expression"),
    ax("S2-KR-MANAGEMENT-GUIDANCE", "KR", "Management forecasts (영업실적등에대한전망) and their revisions",
       "Management forecasts carry forward-looking private information; systematic optimism and revision "
       "drift are documented elsewhere; no Atlas feature reads a forecast.",
       ov(["J04_materialDisclosure (generic, DATA_BUILD_REQUIRED)"], [], [], ["G04 guidanceChanges (UNAVAILABLE)"], []),
       "DART list.json I-type (receipt date) + document.xml forecast table",
       "LIST READY (0 new calls); forecast-number parse NEVER RUN",
       {"verdict": P, "reason": "forward-looking management numbers are absent from every feature set"},
       {"verdict": PART, "reason": "714 filings / 111 issuers; per-anchor median 32 Top-120 issuers in 252 sessions; "
                                  "content parse unverified"},
       "FEASIBLE if parse works; issuer self-selection into guiding is itself a confound",
       "EARNINGS_GUIDANCE in kr-event-report-counts-v1.json", (2, 2, 2, 1, 1, 1), [EVC, SPRINT1],
       ["document parser for forecast tables does not exist", "self-selected issuers (111 of 254)"],
       "outcome-blind parse probe on 30 sampled guidance filings"),
    ax("S2-KR-ANALYST-REVISIONS", "KR", "Analyst estimate revisions (KR)",
       "Analysts under-react to news; revisions drift.",
       ov(["J08_analystRevisions (NOT_FEASIBLE)"], [], [], [], []),
       "FnGuide/FnSpace", "BLOCKED: terms of service (challenger-2-signal-source-feasibility-v1)",
       {"verdict": P, "reason": "never measured"}, {"verdict": F, "reason": "ToS-blocked"}, "BLOCKED", None,
       (2, 2, 3, 0, 0, 1), [REG, INV], ["licensed source required"], "none until a licensed source exists",
       cost="NO: no source"),
    ax("S2-US-ESTIMATE-REVISIONS", "US", "Consensus estimate revisions / surprise (US)",
       "As KR; the US literature is strongest here.",
       ov([], [], [], ["G01", "G02"], []), "Finnhub paid tier / I/B/E/S",
       "UNAVAILABLE (paid historical estimates; AGENTS v2.23)", {"verdict": P, "reason": "never measured"},
       {"verdict": F, "reason": "paid source"}, "BLOCKED", None, (2, 2, 3, 0, 0, 2), [USINV, INV],
       ["paid source", "US survivorship"], "none until purchased", cost="NO: no source"),
    ax("S2-US-SUE-WITHOUT-CONSENSUS", "US", "Seasonal-random-walk earnings surprise (US)",
       "Post-earnings drift; without consensus this is a scaled seasonal earnings change.",
       ov(["C13_fundamentalAcceleration"], [], ["earningsGrowth", "delta_earningsGrowth"], ["G05", "C01", "C06"],
          ["fundamental-acceleration-discovery-v1 CASE D"]),
       "Finnhub PIT store", "AVAILABLE_WITH_CAVEATS",
       {"verdict": F, "reason": "RE-EXPRESSION of the fundamental-change family already closed (regional-31 deltas, C13)"},
       {"verdict": PART, "reason": "survivor-conditioned US panel"}, "BLOCKED: survivorship", None,
       (1, 1, 0, 2, 1, 1), [USINV, f"AGENTS.md@{MAIN} v2.22, v2.24"], [], "none"),
    ax("S2-KR-ANNOUNCEMENT-TIMING", "KR", "Earnings-announcement timing / pre-announcement (결산실적공시예고)",
       "Firms with news to share report early; a periodic-filing event.",
       ov(["J01_periodicFilingEvent"], ["J01"], [], [], []), "DART I-type", "READY",
       {"verdict": F, "reason": "J01 is already a Phase C candidate"}, {"verdict": P, "reason": "collected"},
       "FEASIBLE", "3,868 filings / 160 issuers (I lists)", (1, 1, 0, 3, 2, 1), [PC, SPRINT1], [], "none: in Phase C"),
    # ------------------------------------------------------------------ S3 price & market behaviour
    ax("S3-KR-MOMENTUM-VARIANTS", "KR", "Momentum renames (12-1, 6M, residual, 52w high, persistence, intraday/overnight)",
       "Under-reaction / trend.",
       ov(["A05", "A07", "A08", "A10", "A11", "A12", "A13", "A14"], ["A08", "A10", "A11", "A12", "A13", "A14"],
          ["mom6", "mom121", "relative121", "high52Distance", "ma200Distance"], ["D01", "D02", "D03", "D05"],
          ["#286 intraday/overnight: NO STABLE ADDED ALPHA"]),
       "replay-v16 prices", "READY", {"verdict": F, "reason": "MOMENTUM_RENAME (rank-corr ~0.99, feature-overlap.md)"},
       {"verdict": P, "reason": "ready"}, "FEASIBLE but closed", None, (0, 1, 0, 3, 3, 3), [OVL, PC], [], "none"),
    ax("S3-KR-VOLUME-ATTENTION-VARIANTS", "KR", "Volume / attention / liquidity re-expressions",
       "Attention and liquidity premia.",
       ov(["D01-D11", "E01", "E02", "E06"], ["D01-D11", "E01", "E06"], ["volumeSurge5_60"], ["H06"],
          ["opportunity radar ML rejected twice"]),
       "KRX bars", "READY", {"verdict": F, "reason": "ATLAS_RECOMBINATION (D01/D03 rank-corr ~0.97)"},
       {"verdict": P, "reason": "ready"}, "FEASIBLE but closed", None, (0, 1, 0, 3, 3, 2), [OVL, PC], [], "none"),
    ax("S3-KR-SHORT-SELLING", "KR", "Short-selling volume / balance",
       "Short sellers are informed; high short interest predicts underperformance.",
       ov(["G08_shortSellingVolume", "G09_shortBalanceChange", "J05_shortSellingRegime"], [], [], [], []),
       "KRX data portal", "SOURCE_BLOCKED (probe_kr_short_selling.py; KRX LOGOUT, AGENTS v2.25)",
       {"verdict": P, "reason": "never measured"}, {"verdict": F, "reason": "KRX portal refuses; three regulatory regimes"},
       "BLOCKED", None, (2, 2, 3, 0, 0, 2), [REG, f"AGENTS.md@{MAIN} v2.23, v2.25"],
       ["KRX portal access", "2020-03..2021-05 and 2023-11..2025-03 bans"], "one permitted Probes re-run",
       cost="NO: no source"),
    ax("S3-US-SHORT-INTEREST", "US", "FINRA/Nasdaq short interest",
       "As KR.", ov([], [], [], ["H03"], []), "FINRA / Nasdaq", "UNAVAILABLE in this environment (us-factor-inventory-v1)",
       {"verdict": P, "reason": "never measured"}, {"verdict": F, "reason": "no reachable PIT source"}, "BLOCKED", None,
       (2, 2, 3, 0, 0, 2), [USINV, INV], ["egress", "US survivorship"], "source probe", cost="NO: no source"),
    ax("S3-KR-INDEX-RECONSTITUTION", "KR", "KOSPI 200 additions / deletions",
       "Index demand shocks; mostly a days-to-weeks price-pressure effect that reverses.",
       ov([], [], [], ["G06 indexMembershipChange"], []), "KRX index membership",
       "UNREACHABLE (scripts/probe_krx_index_membership.py; AGENTS v2.23)",
       {"verdict": P, "reason": "never measured; weak 6-12M mechanism"}, {"verdict": F, "reason": "portal unreachable"},
       "BLOCKED", None, (1, 1, 2, 0, 1, 2), [INV], ["KRX portal"], "none", cost="NO: no source"),
    ax("S3-US-INDEX-MEMBERSHIP-CHANGE", "US", "S&P 500 / Nasdaq-100 membership changes",
       "As KR.", ov([], [], [], ["G06"], []), "pinned membership files", "NEEDS_SOURCE_OR_IDENTITY_VERIFICATION",
       {"verdict": P, "reason": "never measured"}, {"verdict": PART, "reason": "identity limits pre-2023 (AGENTS v2.27)"},
       "BLOCKED: survivorship of departed names", None, (1, 1, 2, 1, 1, 2), [USINV, USSRC], ["US survivorship"], "none"),
    # ------------------------------------------------------------------ S4 ownership & capital flows
    ax("S4-KR-INSIDER", "KR", "Executive / major-shareholder open-market purchases (kr-insider-open-market-purchase-v1)",
       "Insiders trade on private long-horizon information; open-market purchases are discretionary and costly.",
       ov([], [], [], ["H02 insiderTransactions (US, UNAVAILABLE)"],
          ["G06/G07 (5%-rule) are different filers and a different report"]),
       "DART list.json pblntf_ty=D + document.xml original (s.173 report)", "SERVED (this lane's G2 run)",
       {"verdict": P, "reason": "absent from Atlas-106, Phase C-38, regional-31 and production"},
       {"verdict": P, "reason": "list + original documents served for 2013-2026"},
       "FEASIBLE (labels need owner exact-hash approval + KR Phase D exception)", "see insider-density-gate-v1.json",
       (3, 3, 3, 3, 2, 2), [GATE, f"research/alpha_evidence_sprint_v2/kr-insider-open-market-purchase-v1.json@{BASE}",
                            f"research/master_research_program_v1/stock/evidence-insider-filing-summaries-v1.json.gz@{WT}"],
       ["G2 UNCERTAIN: projected from ~10 sampled Top-120 members per anchor; the >=20 no-trade control is the binding "
        "bound", "labels need owner exact-hash approval and a KR Phase D exception",
        "7 PARSE_ERROR filings (line break inside a share-count cell); parser v2 frozen with the registration",
        "owner quarantine rule removes 128 filings (2.5%), 115 of them open-market rows dated 1-4 days after receipt"],
       "set by gate result", cost="PARTIAL: event-basket turnover measurable from filings; costs from the dated schedule"),
    ax("S4-US-FORM4", "US", "SEC Form 4 open-market purchases",
       "As KR; the original literature.",
       ov([], [], [], ["H02"], []), "SEC insider-transactions datasets (TRANS_CODE='P')",
       "ACCESS_CONDITIONAL: SEC refuses a client without a declared contact; Actions egress refused (AGENTS v2.9; "
       "evidence/us-insider-probe.json)",
       {"verdict": P, "reason": "never collected in this repository"},
       {"verdict": F, "reason": "SEC access + US panel survivorship (212 unpriced departed identities)"},
       "BLOCKED: historical outcomes BLOCKED_BY_DATA_INTEGRITY", "2013Q1: 261 S&P 500 purchase rows, 82 issuers",
       (3, 3, 3, 0, 1, 3), [f"research/alpha_evidence_sprint_v2/evidence/us-insider-probe.json@{BASE}", USSRC],
       ["owner decision on declaring an SEC contact", "US departed-price source (paid)"],
       "owner decision: permitted SEC contact + egress route", cost="NO: US historical panel blocked"),
    ax("S4-KR-INVESTOR-FLOW", "KR", "Foreign / institutional / retail net buying",
       "Informed and slow-moving institutional demand.",
       ov(["G01-G05", "X4"], [], [], ["H04 fundFlows"], []), "KRX data portal",
       "SOURCE_BLOCKED (HTTP 400 LOGOUT, 0 rows; AGENTS v2.25, v2.54)", {"verdict": P, "reason": "never measured"},
       {"verdict": F, "reason": "KRX portal refusal"}, "BLOCKED", None, (2, 2, 3, 0, 0, 1),
       [REG, f"AGENTS.md@{MAIN} v2.25"], ["KRX access"], "one permitted Probes re-run", cost="NO: no source"),
    ax("S4-KR-LARGE-HOLDER-5PCT", "KR", "5%-rule large-holding reports (purpose, accumulation / reduction)",
       "Blockholders with a control or activist purpose move prices over months; passive filers do not.",
       ov(["G06_largeHolderAccumulation", "G07_largeHolderReduction"], [], [], ["H01 13F (US analogue)"], []),
       "DART list.json pblntf_ty=D (주식등의대량보유상황보고서) + document.xml; majorstock.json serves only 2 years",
       "LIST HISTORY MEASURED here (0 new calls): 1,685 original 5% reports 2013-2026 in 23 of 24 sampled issuers, "
       ">=99 per year; registry's BLOCKED_HISTORICAL_DEPTH refers to majorstock.json, not to list.json",
       {"verdict": P, "reason": "never measured (registry BLOCKED)"},
       {"verdict": PART, "reason": "receipt-dated list exists for 2013+; document parser for the 5% table not built"},
       "FEASIBLE if parsed; shares filers with the insider axis", "LARGE_HOLDING_5PCT_REPORT in kr-event-report-counts-v1.json",
       (2, 2, 1, 2, 2, 2), [EVC, REG, f"docs/dart-ownership-history-replay-integrity-v1.md@{MAIN}"],
       ["5%-report table parser", "overlap with insider filers"], "parse probe on 30 sampled 5% originals"),
    ax("S4-KR-BUYBACK-CANCELLATION", "KR", "Treasury-share acquisition and cancellation decisions",
       "The firm is the best-informed insider; buybacks (and in Korea, cancellation - the only kind that cannot be "
       "re-issued) signal undervaluation and commit cash; documented 6-12M post-announcement drift elsewhere.",
       ov(["J03_buybackAnnouncement (DATA_BUILD_REQUIRED, UNTESTED, not in Phase C)",
           "C11_shareDilution (realised share count; Phase C) - partial"], ["C11 (partial)"], [],
          ["F05 netShareCountChange", "F06 netPayoutYield"], []),
       "DART list.json B-type 자기주식취득결정 / 자기주식취득신탁계약체결결정 and I-type 주식소각결정 (receipt date)",
       "LIST SERVED (B: this lane, 25 calls; I: already collected for 254 issuers)",
       {"verdict": P, "reason": "corporate repurchase decisions are read by no feature set; C11 reads realised share "
                               "counts months later from financial statements"},
       {"verdict": P, "reason": "receipt-dated decision events 2013-2026; event state needs no amount parse"},
       "FEASIBLE; acquisition decisions and trust contracts dense on 147/155 anchors; cancellations concentrated in 2024-26 (value-up regime)",
       "254-issuer B (this lane, 256 calls incl. the 24-issuer pass): 399 acquisition decisions / 111 issuers + 440 "
       "trust contracts / 83 issuers; per-anchor median 20 PIT Top-120 issuers with a decision or trust contract in "
       "the trailing 252 sessions, >=5 on 147/155 and >=10 on 143/155 anchors (2013 anchors left-censored: lists start "
       "2013-01-01). 254-issuer I: 542 cancellation decisions / 111 issuers, median 5, >=5 on 91/155 anchors",
       (2, 2, 2, 3, 2, 3), [EVC, SPRINT1, REG],
       ["trust contracts vs direct acquisitions are different commitments; amounts unparsed",
        "cancellation concentrated in 2024-26 (value-up)"],
       "outcome-blind parse of acquisition size (% of shares) and purpose on a 40-filing sample, then a "
       "pre-registration with its own density gate"),
    ax("S4-KR-EQUITY-ISSUANCE-CB", "KR", "Rights offerings, convertible / exchangeable bond decisions",
       "Managers issue when equity is expensive; CB/EB dilution overhang.",
       ov(["C11_shareDilution", "C10_liabilityGrowth"], ["C10", "C11"], [], ["F05"], []),
       "DART B-type + I-type list (receipt date)", "LIST SERVED",
       {"verdict": PART, "reason": "announcement precedes the realised dilution C11 measures; information partly shared"},
       {"verdict": P, "reason": "list served"}, "FEASIBLE but sparse in Top-120",
       "254-issuer B: 405 rights offerings / 126 issuers (per-anchor median 8 Top-120 issuers in 252 "
       "sessions), 125 CB / 40, 48 EB / 31 (CB+EB median 3, >=5 on 26/155 anchors)", (2, 2, 1, 3, 2, 2), [EVC, PC],
       ["sparse in large caps"], "fold into a net-issuance event study only after buyback density is measured"),
    ax("S4-KR-TREASURY-DISPOSAL", "KR", "Treasury-share disposal decisions",
       "Ambiguous: employee compensation, exchangeable-bond collateral, cross-holding swaps.",
       ov([], [], [], [], []), "DART B-type list", "LIST SERVED",
       {"verdict": P, "reason": "never measured"}, {"verdict": P, "reason": "served"}, "FEASIBLE",
       "254-issuer B: 696 / 142 issuers", (1, 0, 2, 3, 2, 1), [EVC], ["mechanism ambiguous"], "none (parked)"),
    ax("S4-KR-KRX-MAJOR-HOLDER-FILING", "KR", "KRX 최대주주등소유주식변동신고서",
       "The largest shareholder group's holding changes, KRX-side.",
       ov([], [], [], [], ["S4-KR-INSIDER (same holders, DART-side)"]), "DART I-type list", "LIST READY (0 calls)",
       {"verdict": F, "reason": "SAME_INFORMATION_AS S4-KR-INSIDER; usable only as a cross-check source"},
       {"verdict": P, "reason": "11,334 filings / 251 issuers"}, "FEASIBLE",
       "per-anchor median 50 Top-120 issuers in 63 sessions", (1, 2, 0, 3, 2, 0), [EVC, SPRINT1], [],
       "use to cross-check insider parse coverage"),
    ax("S4-US-13F", "US", "13F institutional holding changes",
       "Informed institutional accumulation.", ov([], [], [], ["H01"], []), "SEC 13F",
       "BLOCKED/route NONE (probe_guru_13f_access.py; AGENTS v2.25)", {"verdict": P, "reason": "never measured"},
       {"verdict": F, "reason": "SEC refusal"}, "BLOCKED", None, (1, 1, 2, 0, 0, 2), [USINV, f"AGENTS.md@{MAIN} v2.25"],
       ["SEC access", "45-day lag"], "none", cost="NO: no source"),
    # ------------------------------------------------------------------ S5 economic & industry linkages
    ax("S5-KR-SUPPLY-CONTRACT", "KR", "Single sales / supply contract announcements (단일판매ㆍ공급계약체결)",
       "Contract wins above a size threshold (stated as % of revenue) are hard, dated backlog news that analysts "
       "fold into earnings slowly; the counterparty name is an economic link.",
       ov(["J04_materialDisclosure (generic, DATA_BUILD_REQUIRED)"], [], [], ["G03 corporateEvents8K (US, UNAVAILABLE)"], []),
       "DART list.json I-type (receipt date) + document.xml (contract amount, % of revenue, counterparty, term)",
       "LIST READY for 254 issuers (0 new calls); amount parse never run",
       {"verdict": P, "reason": "no feature set reads order/backlog announcements"},
       {"verdict": P, "reason": "5,225 originals / 120 issuers 2012-2026; per-anchor median 18 Top-120 issuers with a "
                               "contract in 63 sessions, >=5 on 155/155 anchors"},
       "FEASIBLE; concentrated in industrials (120 of 254 issuers ever file) - industry confound",
       "SUPPLY_CONTRACT in kr-event-report-counts-v1.json", (2, 2, 3, 3, 2, 1), [EVC, SPRINT1],
       ["contract-size parse", "industry concentration", "219 termination filings must be netted"],
       "parse probe of contract size (% of revenue) on 40 sampled filings; then a pre-registration"),
    ax("S5-KR-NEW-FACILITY-INVESTMENT", "KR", "New facility investment announcements",
       "Investment anomaly: heavy investors underperform.",
       ov(["C09_assetGrowth", "C15_capexIntensity"], ["C09"], [], ["F07", "F08"], []), "DART I-type", "LIST READY",
       {"verdict": F, "reason": "SAME_ECONOMIC_INFORMATION as C09/C15; only the timing differs (cf. #308)"},
       {"verdict": P, "reason": "395 / 135 issuers"}, "FEASIBLE", "per-anchor median 13 in 252 sessions",
       (1, 1, 1, 3, 2, 1), [EVC, PC], [], "none"),
    ax("S5-KR-CUSTOMER-SUPPLIER-LINKS", "KR", "Customer-supplier return propagation",
       "Economic links: news about a customer reaches the supplier slowly.",
       ov([], [], [], [], []), "business-report text only", "NO structured PIT source",
       {"verdict": P, "reason": "never measured"}, {"verdict": F, "reason": "no PIT link table; counterparties appear only "
                                                                       "partially inside supply-contract filings"},
       "BLOCKED", None, (2, 2, 3, 0, 0, 1), [INV], ["link data"], "revisit after S5-KR-SUPPLY-CONTRACT parse",
       cost="NO: no source"),
    ax("S5-US-8K-EVENTS", "US", "8-K material events (contracts, guidance, departures)",
       "As KR supply contracts / guidance.", ov([], [], [], ["G03", "G04"], []), "SEC EDGAR",
       "UNAVAILABLE (SEC egress; AGENTS v2.23)", {"verdict": P, "reason": "never measured"},
       {"verdict": F, "reason": "SEC refusal"}, "BLOCKED", None, (2, 2, 3, 0, 0, 2), [USINV, INV], ["SEC access"], "none",
       cost="NO: no source"),
    ax("S5-KR-SEMICONDUCTOR-CYCLE", "KR", "SOX / semiconductor cycle exposure",
       "Industry-cycle linkage.", ov(["I10_semiconductorCycleSOX", "H01-H12"], [], [], [], ["industry lane"]),
       "external index", "DATA_BUILD_REQUIRED", {"verdict": F, "reason": "MACRO/INDUSTRY axis (lane B), not stock-specific"},
       {"verdict": PART, "reason": "not built"}, "n/a", None, (1, 1, 1, 1, 1, 1), [REG], [], "hand to industry lane"),
    ax("S5-KR-VALUE-UP-PLAN", "KR", "Corporate value-up plan disclosures (2024+)",
       "Commitment to payout / ROE targets under the 2024 programme.",
       ov([], [], [], [], []), "DART I-type 기업가치제고계획", "LIST READY",
       {"verdict": P, "reason": "never measured"}, {"verdict": P, "reason": "345 filings / 151 issuers, 2024-2026 only"},
       "PROSPECTIVE_ONLY: history starts 2024", None, (1, 1, 2, 3, 0, 0), [EVC], ["no history before 2024"],
       "prospective receipts only"),
]


def total(a):
    return sum(a["scores"].values())


def tier(a):
    g0, g1 = a["g0"]["verdict"], a["g1"]["verdict"]
    if g0 == F:
        return "P3"
    if g1 == P and total(a) >= 13:
        return "P1"
    if total(a) >= 10:
        return "P2"
    return "P3"


def build(gate: dict | None):
    for a in AXES:
        a["priorityTotal"] = total(a)
        a["tier"] = tier(a)
    order = {P: 0, PART: 1, F: 2}
    ranked = sorted(AXES, key=lambda a: (order[a["g0"]["verdict"]] == 2, order[a["g1"]["verdict"]], -a["priorityTotal"],
                                         a["axisId"]))
    for i, a in enumerate(ranked, 1):
        a["rank"] = i
    selected = [a["axisId"] for a in ranked if a["axisId"] != "S4-KR-INSIDER" and a["tier"] == "P1"][:2]
    return ranked, selected


def gate_summary(gate: dict | None) -> dict:
    if not gate:
        return {"verdict": "NOT_RUN"}
    g = gate["gate"]
    return {"verdict": g["verdict"], "anchorsIntervalPass": g["anchorsIntervalPass"],
            "anchorsIntervalUncertain": g["anchorsIntervalUncertain"], "anchorsIntervalFail": g["anchorsIntervalFail"],
            "anchorsRequired": g["anchorsRequired"], "anchorsPointEstimatePass": g["anchorsPointEstimatePass"],
            "parseRate": gate["source"]["parseRate"], "quarantined": gate["quarantine"]["quarantined"],
            "pooledBuyerShare": gate["summary"]["pooledBuyerShare"],
            "gateRuleOff": gate["quarantineRuleBound"]["gateRuleOff"]["verdict"]}


EVIDENCE = {"P1": "PREPARED_NOT_EXECUTED"}


def register_entry(a: dict, gate: dict | None) -> dict:
    g0, g1 = a["g0"]["verdict"], a["g1"]["verdict"]
    if g0 == F:
        highest, failed, ev, prog = "NONE", "G0", "NOT_STARTED", "CLOSED"
    elif g1 == F:
        highest, failed, ev, prog = "G0", "G1", "SOURCE_BLOCKED", "SOURCE_BACKLOG"
    elif g1 == PART:
        highest, failed, ev, prog = "G0", None, "NOT_STARTED", "PARKED" if a["tier"] == "P3" else "ACTIVE"
    else:
        highest, failed, ev, prog = "G1", None, "NOT_STARTED", "ACTIVE" if a["tier"] != "P3" else "PARKED"
    if "PROSPECTIVE_ONLY" in a["h126h252Feasibility"]:
        ev, prog = "PROSPECTIVE_PENDING", "PARKED"
    next_unit = a["nextExecutionUnit"]
    approval = False
    if a["axisId"] == "S4-KR-INSIDER":
        gs = gate_summary(gate)
        v = gs["verdict"]
        if v == "PROJECTED_PASS":
            highest, failed, ev, prog = "G2", None, "PREPARED_NOT_EXECUTED", "ACTIVE"
            next_unit = ("outcome-blind full collection of insider originals for all 254 issuers (~55,600 document "
                         "calls, ~3 DART days) to measure G2 on the full universe, then owner exact-hash decision")
        elif v == "PROJECTED_FAIL":
            highest, failed, ev, prog = "G1", "G2", "PREPARED_NOT_EXECUTED", "PARKED"
            next_unit = "none: preregistered density gate projected to fail; a different definition is a new registration"
        elif v == "SOURCE_BLOCKED":
            highest, failed, ev, prog = "G0", "G1", "SOURCE_BLOCKED", "SOURCE_BACKLOG"
            next_unit = "investigate parse failures"
        else:
            highest, failed, ev, prog = "G1", None, "PREPARED_NOT_EXECUTED", "ACTIVE"
            next_unit = ("outcome-blind collection of insider originals for the remaining 230 issuers (~49,000 "
                         "document calls, ~3 DART days) so G2 is measured on the PIT Top-120 itself instead of "
                         "projected from ~10 sampled members per anchor; owner to note that 115 of 128 quarantined "
                         "filings are open-market rows dated 1-4 days after receipt (settlement-date shape)")
        approval = True
    if a["axisId"] == "S4-US-FORM4":
        approval = True
    if a["axisId"] in ("S4-KR-BUYBACK-CANCELLATION", "S5-KR-SUPPLY-CONTRACT"):
        ev = "NOT_STARTED"
    s = a["scores"]
    importance = "HIGH" if s["netReturnRelevance"] >= 3 else ("MEDIUM" if s["netReturnRelevance"] == 2 else "LOW")
    return {
        "researchId": a["axisId"], "region": a["region"], "track": "STOCK", "title": a["title"],
        "economicMechanism": a["economicMechanism"],
        "overlapWithExisting": "; ".join(f"{k}: {', '.join(v)}" for k, v in a["overlap"].items() if v) or "none found",
        "pitSourceAndRights": f'{a["pitSource"]} | {a["accessStatus"]}',
        "h126h252Feasibility": _feas(a["h126h252Feasibility"]),
        "effectiveSampleAndMde": _sample(a, gate),
        "transactionCostMeasurable": a["transactionCostMeasurable"],
        "expectedEconomicImportance": f"{importance}: netReturnRelevance score {s['netReturnRelevance']}/3, "
                                      f"mechanism {s['mechanism']}/3",
        "prerequisitesAndBlockers": a["blockers"] or ["none recorded"],
        "evidenceClass": ev, "progressStatus": prog, "highestGatePassed": highest, "failedGate": failed,
        "nextExecutionUnit": next_unit, "ownerApprovalRequired": approval,
        "priority": {"tier": a["tier"], **s}, "evidenceRefs": a["evidenceRefs"],
    }


def _feas(text: str) -> str:
    if text.startswith("BLOCKED") or text == "n/a":
        return "BLOCKED: " + text
    if "PROSPECTIVE_ONLY" in text:
        return "PROSPECTIVE_ONLY: " + text
    if text.startswith("FEASIBLE"):
        return "FEASIBLE: " + text[len("FEASIBLE"):].lstrip(" :;,") if len(text) > 8 else "FEASIBLE"
    return "FEASIBLE: " + text


def _sample(a, gate):
    if a["axisId"] == "S4-KR-INSIDER" and gate:
        gs = gate_summary(gate)
        return (f"G2 projection from 24/254 issuers: pooled buyer share {gs['pooledBuyerShare']}, "
                f"{gs['anchorsIntervalPass']}/155 anchors interval-PASS, {gs['anchorsPointEstimatePass']}/155 "
                f"point-estimate PASS (need {gs['anchorsRequired']}); ~25 non-overlapping H126 / ~12 H252 windows; "
                f"MDE 0.62 / 0.89 sigma_S (preregistration); sigma_S UNKNOWN")
    return a["measuredCounts"] or "UNKNOWN"


def markdown(ranked, selected, gate):
    gs = gate_summary(gate)
    lines = ["# Lane C - Stock-selection information axes (S1-S5), outcome-blind", "",
             "Generated by `stock_axis_audit.py`; source of truth is `stock-axis-audit-v1.json`. No return, price after "
             "a filing, label, NAV, IC or model output was read.", "",
             "Gates: **G0** novelty (a rename/recombination of Atlas-106, Phase C-38, regional-31 or US-inventory "
             "features fails); **G1** free PIT source reachable at list level for 2013-2026 with a cited access verdict; "
             "**G2** density (insider only).", "",
             f"Insider G2: **{gs['verdict']}** (parse rate {gs.get('parseRate')}, quarantined {gs.get('quarantined')}, "
             f"interval-PASS anchors {gs.get('anchorsIntervalPass')}/155 vs {gs.get('anchorsRequired')} required; "
             f"rule-OFF bound {gs.get('gateRuleOff')}). Details: `insider-density-gate-v1.json`.", "",
             f"Selected for further preparation (non-insider, at most 2): **{', '.join(selected) or 'none'}**.", "",
             "| rank | axis | region | G0 | G1 | score | tier | main overlap |", "|---:|---|---|---|---|---:|---|---|"]
    for a in ranked:
        o = a["overlap"]
        main = ", ".join((o["atlas"] + o["phaseC"] + o["usInventory"] + o["studies"])[:3]) or "-"
        lines.append(f"| {a['rank']} | {a['axisId']} | {a['region']} | {a['g0']['verdict']} | {a['g1']['verdict']} | "
                     f"{a['priorityTotal']} | {a['tier']} | {main} |")
    lines += ["", "## Why these two", "",
              "* **S4-KR-BUYBACK-CANCELLATION** - the firm as the best-informed insider; Atlas J03 was registered but "
              "never built, Phase C has only the realised share count (C11) months later; the decision list is already "
              "served (B-type, 254 issuers) and receipt-dated; the US analogue (F05/F06) exists. Risk: 2024-26 value-up "
              "concentration of cancellations (median 5 issuers, >=5 on 91/155 anchors); acquisitions/trusts are dense "
              "(median 20, >=5 on 147/155 anchors, all 254 issuers measured).",
              "* **S5-KR-SUPPLY-CONTRACT** - hard, dated backlog news no feature set reads; dense (>=5 Top-120 issuers "
              "on every anchor, median 18 in 63 sessions) from lists already collected at zero cost. Risk: only 120 of 254 "
              "issuers ever file (industrials), so industry neutralisation is mandatory.",
              "* Not chosen: 5%-rule holders (shares filers with the insider axis - prepare after insider), dividend change "
              "(label distribution basis is weakest exactly for payers), management guidance (parser unknown, 111 "
              "self-selected issuers), issuance/CB (sparse in large caps, partly C11).", "",
              "Score = netReturnRelevance + mechanism + independence + sourceObtainable + timeToDecision + "
              "krUsExtensible (0-3 each). Tier: G0 FAIL -> P3; G1 PASS and score >= 13 -> P1; score >= 10 -> P2."]
    return "\n".join(lines) + "\n"


def main() -> int:
    gp = HERE / "insider-density-gate-v1.json"
    gate = json.loads(gp.read_text()) if gp.exists() else None
    ranked, selected = build(gate)
    audit = {"auditId": "stock-axis-audit-v1", "lane": "C", "evidenceClass": "OUTCOME_BLIND_SOURCE_INVENTORY",
             "baseCommit": BASE, "mainCommit": MAIN, "criteria": list(CRITERIA),
             "gateDefinitions": {"G0": "novelty vs Atlas-106 / Phase C-38 / regional-31 / US inventory / registered studies",
                                 "G1": "free PIT source reachable at list level 2013-2026, access verdict cited",
                                 "G2": "information density (insider only, insider_density_gate.py)"},
             "insiderGate": gate_summary(gate), "selectedForPreparation": selected,
             "axisCount": len(ranked), "axes": ranked,
             "outcomeAccess": {"returnsRead": 0, "pricesAfterFilingRead": 0, "labelsBuilt": 0, "icsComputed": 0}}
    (HERE / "stock-axis-audit-v1.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1) + "\n")
    entries = [register_entry(a, gate) for a in ranked]
    (HERE / "register-entries.json").write_text(json.dumps({"entries": entries}, ensure_ascii=False, indent=1) + "\n")
    (HERE / "STOCK_AXES.md").write_text(markdown(ranked, selected, gate))
    print(json.dumps({"axes": len(ranked), "selected": selected, "insider": gate_summary(gate)["verdict"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
