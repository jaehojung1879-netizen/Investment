# Frozen machine handoff

Starting main `449508ad18ef6f4a7fce3678c0f593b3237dbab3`; branch `research/kr-model-overlay-portfolio-v1`. Draft only; no merge or ready transition. Historical execute remains unauthorized.

## Specification and hashes

Canonical preregistration SHA-256: `a11e63f0756c706774ef92da6fca632391b8f0a29b37d254df2163ffa02f3afe`.
Diagnostic canonical SHA-256: `0fd3baf70d0fbe24e17a9ab2244ea6c3a4d8ac50c0af634a196fe3c3cb885f03`.

Complete imported-code, workflow, dependency and frozen document hashes are in `research_specs/kr-model-overlay-portfolio-v1.json: dependencyHashes` (77 entries). Main new harness/module byte hashes:

| Path | SHA-256 |
|---|---|
| `pipeline/kr_concentrated_portfolio.py` | `245f00f321c890b2c70e2276b93313a6d1eb0e2185312aec38cefd9a1fb1687e` |
| `pipeline/kr_market_risk_overlay.py` | `983b3aab891a2af2f6d54b9b3d7ca29788651ba898b074da0506a40431ae4c07` |
| `pipeline/kr_market_value.py` | `49306b8d14c4e8d681ae5846802c2ae82fa5727bb7a8adf356fa313217103c5e` |
| `pipeline/kr_model_overlay_portfolio.py` | `04b006de9228a7b424d2be886a5d095f0f8250d75855940cb1dcd6e1a159f3c8` |
| `pipeline/kr_model_portfolio_execution.py` | `f9b613d979669b10ffffc6f7bc6c99cde99ab8c1504a25453e67fd9e78085af0` |
| `pipeline/kr_portfolio_diagnostics.py` | `9f28a5ddf49a58c95db36d3a573b19e56fe7c86f98ad2ed01d96e8c09e6b5c34` |
| `pipeline/kr_value_quality_catalyst.py` | `ee5dcfabc8bf5bd4d269c95fdb42ad3968535fab6971e535c7175b15b00369a8` |
| `scripts/collect_kr_model_market_values.py` | `2546c9afb7ef231c1599d59af4731a49ac05d7af6540c47e02bcc78ddc5e83fc` |
| `scripts/run_kr_model_overlay_portfolio_v1.py` | `3bf1e365dc9781a006067883bb3f33599f13b21b1e23fb3829496fc70e73b3dc` |

## Exact frozen registry

* VALUE: `bookToMarketProxy`, `earningsYieldProxy`, `ocfYieldProxy`.
* QUALITY: `netIncomeToAssets`, `ocfToAssets`, `negativeAccrualsToAssets`.
* CATALYST: `relative126`, `momentum121`, `ocfImprovementToAssets`.
* RISK: `negativeDownsideVol126`, `logAdv60`.

## Rules and limits

Separate H126-primary and H252-secondary Ridge regressions: alpha 10, intercept, SVD. Expanding annual refit, 36 months minimum history, 104 matured dates and 10 names/date. Endpoints strictly precede refit cutoff; equal-date training weights. Training-only median/IQR, median imputation plus flags, signed-log accounting ratios. Fixed descriptive HGB: 100 iterations, learning rate .05, depth 2, 7 leaves, 20 minimum leaf rows, L2 10, no early stopping, seed 42.
Interactions: positive-part VALUE×QUALITY, VALUE×CATALYST, QUALITY×CATALYST and VALUE×QUALITY×CATALYST. No unrestricted pairwise expansion.
Targets: next KR session close to H126/H252 further sessions; stock frozen adjusted-index ratio minus the same-endpoint 069500.KS ratio. Distribution coverage is partial, not a complete shareholder total return. No nearest-date endpoints or future filling.
Overlay: benchmark close below SMA200 and annualized trailing std63 >25% are two adverse flags; counts 0/1/2 map to 1.00/.70/.40. Missing history blocks. It never receives stock rankings.
Portfolio: top five eligible H126 forecasts strictly above .006 fixed roundtrip cost, ticker tie-break; zero names permitted. Inverse annual downside126 semideviation sizing, 30% target single-name cap, 1% ADV capacity and residual cash, then overlay. ADV60 floor KRW3bn; downside floor1%; reference NAV KRW100m. No sector cap or sector ranks. No leverage, no Kelly. Deferred/partial exits occupy slots so actual holdings remain <=5. Target caps can drift between rebalances; disclosed. Fixed 21-KR-session anchors, prior completed weekly signal; actual quote/volume required for fills.
Costs: buy .0015, sell .0045; sell includes .003 conservative assumed levy buffer, NOT an official historical tax schedule. Impact .0005 at 1% ADV, square-root participation; stress ×2/×3 descriptive. Actual executable turnover, suspended trades deferred, cash preserved; postcost weight approximation disclosed.
Prospective start: first eligible KR trading session strictly after actual final spec merge DATE. Immutable prediction receipts precede later maturity joins. No retroactive 2026-09-15 claim, schedule activation or authorization.

## Source exclusions and readiness

Added infrastructure: official KRX sto/stk_bydd_trd date-specific immutable marketCap/close/listedShares/volume/tradingValue cache and bounded collector. No real cache collected in this task; joined year coverage NOT_MEASURED. Real gates therefore remain pending. Four-family repaired DART accounting, prior-month KRX top120 universe and replay-v16 raw prices are pinned and reused.
Rejected: 3,721 legacy DART shares lack public-date/receipt provenance. Deferred: historical sectors; EV/EBITDA, sales/EV, net-debt, cash, gross/operating profit, ROIC/interest coverage and capex/FCF lacking validated concepts/applicability; dividend/buyback/share-count catalysts lacking complete PIT lineage; revisions/consensus without legitimate source; own-history/sector-relative valuation and macro series without separately frozen history/vintage contract. Attention features excluded by economic scope before outcomes. Detailed grain, annual source coverage, semantics, units and limitations are in the data audit; no performance-based exclusions.

## Verification and boundary proof

Full regression: **3021 passed, 1 skipped, 245 warnings**. New synthetic/adversarial tests: **78 passed**. Ruff, compileall, seed generation and --allow-seed validation passed. Three legacy research-isolation tests now explicitly recognize the seven new research modules; a new import-closure test proves none is reachable from production entrypoints. No v5 sealed source, spec, result, diagnostic or test was modified.
Actual verify: VERIFIED, executeAuthorized=false. Actual gates-only without snapshot: DATA_INSUFFICIENT / RAW_INPUT_SNAPSHOT_REQUIRED. Both have targetCalls=labelCalls=fitCalls=predictionCalls=modelOutcomeCalls=portfolioOutcomeCalls=0. A synthetic fully-ready gate fixture also passes with zero counters. No real new-study forward label, model outcome or portfolio outcome was accessed/computed. The hashed machine-audit artifact preserves these facts. Existing exposed prior narratives remain prior evidence, not a claim of untouched blindness.
CI and final PR head are reported in the Draft PR handoff. No formal workflow dispatch, execution authorization file, execution lock tag, historical result or prospective automation was created.

## Exact changed files

* `.github/workflows/kr-model-overlay-portfolio-v1.yml`
* `README.md`
* `docs/kr-model-overlay-portfolio-v1-data-audit.md`
* `docs/kr-model-overlay-portfolio-v1-design.md`
* `docs/kr-model-overlay-portfolio-v1-execution.md`
* `docs/kr-model-overlay-portfolio-v1-handoff.md`
* `docs/kr-model-overlay-portfolio-v1-preregistration.md`
* `docs/kr-model-overlay-portfolio-v1-prospective.md`
* `docs/kr-model-overlay-portfolio-v1-research-foundation.md`
* `docs/results/kr-model-overlay-portfolio-v1-machine-audit.json`
* `docs/results/kr-model-overlay-portfolio-v1-machine-audit.json.sha256`
* `docs/workflow-inventory.md`
* `pipeline/kr_concentrated_portfolio.py`
* `pipeline/kr_market_risk_overlay.py`
* `pipeline/kr_market_value.py`
* `pipeline/kr_model_overlay_portfolio.py`
* `pipeline/kr_model_portfolio_execution.py`
* `pipeline/kr_portfolio_diagnostics.py`
* `pipeline/kr_value_quality_catalyst.py`
* `research_specs/kr-model-overlay-portfolio-v1-diagnostics-v1.json`
* `research_specs/kr-model-overlay-portfolio-v1-diagnostics-v1.sha256`
* `research_specs/kr-model-overlay-portfolio-v1.json`
* `research_specs/kr-model-overlay-portfolio-v1.sha256`
* `scripts/collect_kr_model_market_values.py`
* `scripts/run_kr_model_overlay_portfolio_v1.py`
* `tests/test_alpha_opportunity.py`
* `tests/test_alpha_opportunity_v2.py`
* `tests/test_alpha_opportunity_v3.py`
* `tests/test_kr_model_overlay_portfolio_v1.py`
