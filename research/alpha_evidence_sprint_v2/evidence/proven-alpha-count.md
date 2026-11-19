# Proven alpha count (as of 2026-11-03, main `37f8cbf6`)

**Bar:** passed a pre-registered, multiplicity-corrected, out-of-sample *or* prospective test, net of costs.

| Region | Count | Evidence |
|---|---:|---|
| **KR** | **0** | Phase C/D: "BY / Holm 보정 후 개발 증거 통과 **0**", `prospectiveNominations []`, Level 4 cost backtest `NOT_TRIGGERED` (`docs/kr-alpha-research-final-development-assessment.md` @37f8cbf6). All KR history is `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY` (no untouched OOS possible). Opportunity-v5 `INCONCLUSIVE`, overlay `DEVELOPMENT_REJECT`, tournament `BLOCKED_BY_DATA_INTEGRITY`, integrated portfolio trails passive (+15.01% vs +20.24%/yr, AGENTS v2.47), C1-KR `NO_CANDIDATE_NOMINATED_CONTROL_RETAINED`. No prospective KR ledger has matured (B-H1 first H63 = 2027-02-02, #301 @c9eaa036; challengers #277/#278 "결과 없음", hierarchy doc 07 §2.3). |
| **US** | **0** | regional-alpha-model-v1 `NO_MODEL_EVIDENCE` (AGENTS v2.24); Study A US A1 `NO_GO`, `MDE_UNRESOLVED` (`docs/research-program/results/rp1-a0-measurability-v1.json`); #287 rights/identity/returnBasis `BLOCKED`, `NOT APPROVED FOR EXECUTION` (@9a10baef); C1-US `REPLICATED_CONTROL_RETAINED` — a return-for-drawdown trade (passive 8.82% vs C0 7.77%), "알파가 아니다" (hierarchy doc 07 §0); US panel survivorship defect (AGENTS v2.27). |

Operating default stays 100% regional index ETF (`PASSIVE_NO_DEFENSIBLE_EDGE`, #304/#308).

## Closest but not proven

| Reading | Number (source @ commit) | Why it fails the bar |
|---|---|---|
| KR-only lowvol sleeve IC | +0.0511, 95% CI [+0.0047, +0.0974], raw p=0.031 (AGENTS v2.21) | Secondary regional reading; pooled IC +0.0286, Holm p 0.4392; US −0.0225 (sign flip); classified `D_UNSTABLE_REGIME_DEPENDENT` (`four-factor-signal-attribution-audit-report.md`); IC only, no costs |
| Industry median OCF-yield IC (CAP, H126) | +0.1364, HAC SE 0.0669, 337 dates, ~13.37 effective (`docs/results/kr-industry-opportunity-anatomy-v1-result.json` @37f8cbf6) | Descriptive, no multiplicity correction, exposed history; pre-2025 +0.1969 vs 2025+ −0.1485 (sign flip); conditional test power gate `NO_GO` (23.0% power, #300 @e580cde9); no portfolio/cost test |
| Industry net-income improvement IC | −0.185, ratio −3.0, all six cells negative (same report) | Opposite of hypothesised direction; never pre-registered as a test |
| #310 H1 peer-disclosure revenue forecast | MSE Δ +0.001328, p=0.0085, permutation p=0.005, Holm-passed (@50055560 REPORT) | Predicts **revenue**, not returns ("수익 주장은 아니다"); 89% from financials, ex financials+energy −0.000075; peer lead median 9 sessions; H2 return test `DATA_BLOCKED` |
| Phase C A01_return1d_H21 (short reversal) | raw p≈0.008536, corrected p≈0.693111 (Phase D assessment §2) | Fails BY; unstable |
| KR CHAMPION-C2 path vs ETF | +1.8181pp CAGR; regression intercept +6.1246pp/yr [+1.4215, +10.8276], β 0.6300 (#311 @e130c64f; #305 @e46024ca) | Post-outcome; top-3 years = 234.2% of log excess (#309); 3x-cost edge −1.470pp (#286 result-v2); verdict `INCONCLUSIVE` (#300, #309); last 2024–26 −64.8214pp |
| Integrated D industry layer | `INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED` (AGENTS v2.47) | 98.2% of gross after 2024, 59.5% one industry; D < passive full window |
| Entry-state at weight | v2.17 +2.069pp [−1.881, +6.061]; #304 KR +1.739pp [−2.779, +6.659] | Both `CONTAINS_ZERO`; US −1.142pp |
| #286 intraday vs momentum (H126) | +1.99pp, CI [−8.41, +16.69] | Contains zero; 19 valid pairs; halves −3.55/+11.23 |
| Switch-hurdle cost rung | lower bound clears zero by 0.122pp (AGENTS v2.12) | One sample, several rungs, no multiplicity correction; "none of which makes it a promotion" |
| KR preliminary earnings (#308) | 63.1% of variance unexplained by prior info (#310); lead 12 KRX days | No return ever read; content = formal filing; 4%p H126 needs 11.4–33.7 years prospective |
| Within-industry value | B/M +0.086, E/P +0.073 within-rank IC (hierarchy doc 07 §2.3) | Descriptive anatomy on exposed history; Phase C B-family 4/4 split, 0 BY passes |
