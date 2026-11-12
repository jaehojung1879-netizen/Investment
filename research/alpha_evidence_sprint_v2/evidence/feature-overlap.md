# Feature-set overlap and failed hypothesis families (as of 2026-11-03, main `37f8cbf6`)

## 1. The five feature sets

| Set | Size | What it is | Source @ commit |
|---|---:|---|---|
| Atlas registry | 106 | Inventory, 10 families: C 16, A 14, H 12, I 12, D 11, G 9, B 8, E 8, F 8, J 8. Readiness: DERIVABLE 27 / READY 25 / ALREADY_TESTED 24 / DATA_BUILD_REQUIRED 13 / SOURCE_BLOCKED 7 (all 7 in G = investor flow / short selling) / PIT_UNSAFE 6 / NOT_FEASIBLE 4 | `research_specs/kr-alpha-atlas-registry-v1.json` @37f8cbf6 |
| Phase C candidates | 38 (→73 feature-horizon readings, 51 inferential at H21/H126) | Strict subset of the 106, chosen from the never-individually-measured ones (19 UNTESTED + 19 PRIOR_INCONCLUSIVE). By family: A 11, D 11, C 5, B 4, F 3, E 2, H 1, J 1. **Zero G (flow), zero I (macro)** | `research_specs/kr-alpha-atlas-phase-c-v1.json` @37f8cbf6; counts in `docs/kr-alpha-research-final-development-assessment.md` |
| Phase C baselines B0–B4 | 11 distinct features | 8 from the 24 `ALREADY_TESTED` registry features (A05, A07, B01, B02, C01, C05, E02, H01) + 3 that are also Phase C candidates (A11, D02, E01) | same spec `baselines`, `alreadyTested.sealedReferences` (24 ids) |
| regional-alpha-model-v1 | 31 | 21 price + 5 fundamental level + 4 fundamental-acceleration delta + 1 region-specific; research-only ML matrix | AGENTS.md v2.23 / v2.24 @37f8cbf6 |
| Production `FACTOR_WEIGHTS` | 4 sleeves / 13 raw sub-inputs | momentum 0.30, value 0.25, quality 0.25, lowvol 0.20; only `vol252` survives raw in the sealed ledger | `pipeline/longterm.py:50` @37f8cbf6; AGENTS v2.21, v2.23 |
| Opportunity radar | 28 | 19 level (incl. the 5 production percentiles alpha/momentum/value/quality/lowvol) + 9 change features | `pipeline/opportunity.py` LEVEL_FEATURES/CHANGE_FEATURES @37f8cbf6 |

**Relationships.** Phase C 38 ⊂ Atlas 106 (verified: all 38 ids are registry ids). The registry's 24 ALREADY_TESTED features cite the regional model, factor anatomy, overlay, v5 and industry anatomy as their sealed references, i.e. the 31-feature, 13-input and 28-feature sets are largely *already inside* the Atlas as baselines. Radar's 5 percentile inputs **are** the production 4-sleeve outputs. AGENTS v2.24: most of the 31 are "different representations of the same three information families (price/trend, fundamental level, fundamental change)".

## 2. Re-labels of the same information (do not count as independent tests)

| Re-label cluster | Measured redundancy / identity | Source |
|---|---|---|
| A05_relative126 / A08_momentum6 / A10_residualMomentum126 | rank-corr ≈ 0.99 | Phase D assessment §3 @37f8cbf6 |
| D01_volumeSurge5_60 / D03_tradingValueShock5_60 | ≈ 0.97 | same |
| Fundamental acceleration: regional-31's 4 deltas = C13 = fundamental-acceleration-discovery-v1 | C13 `PRIOR_NEGATIVE_DEVELOPMENT`, refs both studies | registry @37f8cbf6 |
| Value × business confirmation: kr-alpha-signal-v2 H2 = Phase C B08 / X1 = Challenger v2 | "same accounting fields kr-model-overlay-portfolio-v1 fitted and was rejected on" | AGENTS v2.52/v2.53; X1 p 0.9895 |
| KR preliminary earnings (#308) vs formal filings (Phase C C-family) | 97.5% of revenue within 1% of formal; only a 12-KRX-day timing gain | #308 @f48b6f29 REPORT |
| Industry info read 4 ways (industry anatomy, Phase C H, integrated v1 D, A-H3) | all on the same reconstructed v4 classification / same exposed history | hierarchy doc 07 §3.1 @37f8cbf6 |
| Price-based leader→laggard diffusion (#308 candidate B) | = X3, A09, A10, H01/H03/H07 ("시차를 둔 가격 수익은 같은 OHLCV 정보의 재표현") | #308 REPORT §2 |
| Radar ML blend (volume shock + momentum accel + fundamental pct) | rejected twice, negative top-decile ordering | AGENTS v2.23 |
| Intraday/overnight decomposition (#286) | "기존 OHLCV의 새로운 표현이며 독립적인 새 원천 정보라는 주장은 하지 않는다" | #286 @97aa2cfe README |

## 3. Failed / closed hypothesis families

| Family | Verdict | Source |
|---|---|---|
| Production 4 sleeves (mom/value/quality/lowvol) | pooled 126D IC −0.0015 / −0.0056 / −0.0223 / +0.0286, all Holm p > 0.32; all `D_UNSTABLE_REGIME_DEPENDENT` | `docs/results/four-factor-signal-attribution-audit-report.md` @37f8cbf6 |
| Regional 31-feature ML (US, KR) | `NO_MODEL_EVIDENCE` both | AGENTS v2.24 |
| Fundamental acceleration | CASE D `NO_DISCOVERY_EVIDENCE` (IC −0.0026) | AGENTS v2.22 |
| Opportunity radar ML | `accepted: false`, rejected twice | AGENTS v2.23 |
| Lowvol-sleeve removal / calibration resolution / region quota / dynamic breadth / entry separation / signal persistence | all `CONTAINS_ZERO` or unfavourable (e.g. calibration rescue CASE B) | AGENTS v2.12–v2.20 |
| Opportunity v5 (KR) | `overallStatus INCONCLUSIVE` | `docs/results/alpha-opportunity-model-v5-result.json` |
| Model overlay | `DEVELOPMENT_REJECT` | `docs/results/kr-model-overlay-portfolio-v1-result.json` |
| Tournament | `BLOCKED_BY_DATA_INTEGRITY` | `docs/results/kr-alpha-discovery-tournament-v1-result.json` |
| Atlas Phase C (38 cands, X1–X6) | BY/Holm pass 0, nominations [], Level 4 NOT_TRIGGERED | Phase D assessment |
| Integrated portfolio (industry + stock) | `NO_UNAMBIGUOUS_FINAL_ARCHITECTURE`; trails passive | AGENTS v2.47 |
| Market overlay C0–C3 (KR, US) | `NO_CANDIDATE_NOMINATED_CONTROL_RETAINED` | KR result json; US archive README |
| Intraday/overnight momentum (#286) | "NO STABLE ADDED ALPHA" | @97aa2cfe |
| Entry-state at weight (#304) | `CONTAINS_ZERO` KR and US | @38926172 |
| M3 backlog (US industry fundamentals) (#302) | `REJECTED` | @06d55d7f |
| Industry OCF-yield conditional (#300) | power `NO_GO` | @e580cde9 |
| Investor flow (G, X4) | `SOURCE_BLOCKED` (never measured) | registry; #308 |
