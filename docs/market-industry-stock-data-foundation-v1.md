# Market / industry / stock data foundation v1

DATA FOUNDATION + RESEARCH ARCHITECTURE ONLY. Main inspected:
`9504f970a2895781eedcc3a6a1c94126fd4682f8` (PR #187 merged).
No historical Alpha outcome is calculated, no model is fitted, no prior sealed study
is rerun. The metadata runner has no execute mode and imports no outcome engine.

## Economic objective and scientific interpretation

The program asks: can we systematically earn FUTURE returns above the relevant
market benchmark, after realistic investability and costs? Each component retains
its own question, target, universe, identification, methodology and limitations.
An industry-cycle map can improve decomposition, a regime diagnostic can expose
non-stationarity, and anatomy can expose confounding without itself earning Alpha.
Scientific validity of such a component is different from economic success of the
investment program. At each phase transition state how the evidence could improve
future ranking/allocation and what evidence would contradict that use. Diagnostics
without a specified route to that decision do not authorize another historical sweep.

The three layers are:

| Layer | Question and eventual target | Information boundary |
|---|---|---|
| MARKET | Market state and risk budget, rather than stock choice | Past trend, volatility, breadth, credit/liquidity, concentration; retain each region's benchmark and vintage constraints |
| INDUSTRY | Which industries could beat their market? Industry return minus market return | Own-industry momentum, breadth, fundamentals, cycles, concentration; only after dated membership and sources exist |
| STOCK WITHIN INDUSTRY | Which companies could beat their signal-date industry? Stock return minus industry return | Value, quality/profitability, cash/earnings improvement, own-industry momentum, risk/liquidity; expectations only if historical estimates exist |

These are descriptive reference-return differences, NOT a causal market-beta / industry-beta
regression or orthogonal factor attribution. A diversified conglomerate has one sourced
primary assignment in this version; no invented segment-weighted industry assignment.
No feature is admitted merely because its economic story is plausible.

## Actual repository findings and reuse boundaries

`pipeline/sectors.py` is a static GICS-style map with a current Yahoo override; no
validity or release dates. `rotation.py` uses ETF baskets, not reconstructed historical
company membership. Neither can provide this framework's historical industry labels.

KR raw KRX snapshots carry rank, marketCap, listedShares and dated identity through
`krx_universe.py`; its legacy `members_on_date` unions today's configured names.
For new research, follow the reviewed raw-input convention: strictly prior KRX
snapshot, top 120 by dated rank, without today's-name additions. Monthly observations
are snapshot-observed membership, not exact exchange-effective membership. Prior
input-scope audit and protocols establish a 260-ever-top120 input scope; no broad KR
market or Top300 claim follows. A future adapter must retain the entire source universe
including names with missing classifications, prices, accounting, or termination terms.
This PR builds no price adapter and collects no new raw data.

Accounting reuse: `kr_repaired_accounting_snapshot.py` pins the candidate at
`fb6e83743fd8cdba647d1522a4645b662a9d5647`, 9,351 records, 250/260 securities,
FY2015 onward. Its four validated semantic families are assets, liabilities, net income,
OCF. `dart_canonical_accounts.py`, `dart_xbrl_statements.py`, `dart_derive.py` and
`merge_kr_candidate_snapshot.py` own concept, unit, cumulative/TTM and original receipt
semantics. Do not rederive them here. Read only filings with availableFrom < signal;
all TTM operands must come from that visible set, compatible currency / fiscal stage /
statement basis. Latest-amendment endpoint records cannot recreate overwritten originals.
Revenue, operating profit and capex exist in older DART account lists but are not proven
full-coverage extensions of the repaired four-family snapshot. A future collector/audit
must verify their actual concepts, units, period, basis and missingness before aggregation.
Never sum per-share ratios or compare sector-wide totals with changing constituent sets;
changes/breadth need the matched visible cohort and publish its denominator.

US: `finnhub_fundamentals.py` / `finnhub_derive.py` provide filedDate and separate account
chains/unit resolution. `accounting_quality.py` reuses regional TTM/level readers. US
historical issuer/security identity and departed-name coverage remain separate gates;
there is no US repair implied by a KR snapshot. The sources and classifications can differ.

Return reuse: `price_adjustment.to_total_return` makes a forward-anchored adjusted
index from served distributions. KRX bars alone supply no dividend events; Yahoo events
are missing for audited KR departed names and incomplete for continuing names.
The existing KR anatomy basis is `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS`,
NOT true total shareholder return. `kr_terminal_corporate_actions.py` owns cited economic
entitlements and successor identity, while `kr_termination_inventory.py` reports unresolved
fields: unknown termination is never NOT_APPLICABLE or zero entitlement. This framework
will require those economic chains for every frozen-cohort exit. No survivor-only repair.

Market reuse: `kr_market_risk_overlay.state_at` is a past-only benchmark rule (SMA200,
63-session volatility). It receives no stock ranking. `regime.py`, `macro_context.py`,
`pit_data.MacroVintageView` and `ecos_macro.py` distinguish publication lags from revision
vintages: lags alone cannot make revised FRED/ECOS history PIT_EXACT. No macro or risk
rule is modified or promoted here.

## Existing study lifecycle (provenance only, no outcome inspection)

* KR model overlay portfolio v1 has its committed seal and permanent execution lock;
  its documented closed state is retained. No raw results or diagnostic summary opened.
* KR factor anatomy v1: seal provenance names run 36960496371, execution commit
  cd82a5b7edb08f18ccdaa3f231415354aef9a41c, input identity
  233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7.
  Result/report payloads were not opened. The exploratory lifecycle stays closed.
* KR Top120 regime review v1 is NOT assumed unexecuted merely because main has only a
  protocol: GitHub metadata was checked on 2026-10-02 UTC / 2026-10-03 KST. Durable
  study-level and identity lock refs exist at the inspected main; completed dispatch
  run 37018055459 has a results artifact 11232463461, SHA-256
  93c0127cebddc7247057fa2e49e97ef58a593f0a375710c585b5e8c12610dcb4.
  The artifact was neither downloaded nor inspected. An earlier failed dispatch is not
  grounds to retry. No committed regime-review result exists at the inspected main.
* Regional alpha model v1's executed/closed status is recorded in the foundation errata;
  no prior model matrix is rerun or retrospectively rescued by adding industry labels.
* Material latest merges: #187 (regime protocol/lock), #186 (anatomy exact-byte seal),
  #185 (authorization test lifecycle). Their guards and pinned closures remain unchanged.

## PIT taxonomy and identity contract

`research_specs/market-industry-stock-membership-v1.schema.json` specifies immutable
rows: security_id, display ticker, region, taxonomy_id/version, industry_id,
valid_from/to, source_date, release_date, known_to, source URL/receipt, source_sha256,
evidence_kind and identity_provenance. Security IDs must follow instrument identity
(including preferred shares and successors), never a timeless ticker or issuer name.
Historical identity bridges must themselves have dated evidence; uncertain joins block.

Economic validity is [valid_from, valid_to). Knowledge uses release_date < signal_date;
a superseded record remains the known version through known_to (date-only changes
become usable the next day). Later retroactive corrections get new knowledge vintages,
never overwrite an old row. Same-date conflicting visible assignments raise; no first-wins
rule. An explicit taxonomy version is requested at every join. Definition changes cannot
be silently relabelled using today's code hierarchy. Current-only snapshots cannot
backfill and are never admitted as DATED_ASSIGNMENT, even on recent dates.

Classification announcements with a future effective date enter only when BOTH the
release and effective boundary pass. Source hashes are verified against retained raw
bytes by `verify_source`; row hashes alone do not prove a vendor's historical claim.
A future importer must establish historical release evidence, identity, codebook/version,
terms of use and terminal coverage before writing any admitted row. Simply stamping a
current classification with an old date does not satisfy the contract. No such importer
or historical membership file exists in this PR.

## Source and coverage matrix (checked 2026-10-03 KST)

| Source candidate | Verified fact / limitation | Current foundation decision |
|---|---|---|
| KR KRX historical KSIC-based classifications | Raw trade/membership snapshots in this repository contain no industry assignments. No acquired historical assignment/release/codebook file found | DATA_FOUNDATION_REQUIRED. Investigate dated KRX assignments or contemporaneous archived filings; do not infer from business names |
| KRICS | Official KRX homepage lists its 2026-09-22 introduction release. Article click yielded a generic dynamic list, not its detailed text; the earlier repository note's 9/24/60/129 counts and 2026-10-26 launch were NOT independently verified from primary release text here | Prospective lead only. Acquire official codebook, timestamped assignments/reclassification notices and terms; no 2015 backward projection or guaranteed historical archive claim |
| DART company.json induty_code | Official API guide exposes the code, but request keys are only API key and corp_code, with no as-of date | CURRENT_SNAPSHOT_ONLY, historical use refused. Archival receipt-specific business report extraction is an unbuilt lead, not a current API backfill |
| S&P GICS History (KR or US) | Official marketplace documents active/inactive company history and from/thru dates. Dataset existence is verified; actual licensed access, release-vintage semantics and instrument mapping are not | DATA_FOUNDATION_REQUIRED pending entitlement and point-in-time sample validation; request no purchase in this PR |
| US SEC filing SIC | SEC Financial Statement Data Sets SUB defines sic as assigned at filing date; raw EDGAR header also carries ASSIGNED-SIC. This is a dated official alternative, so “US PIT classification is paid-only” is too broad | DATA_FOUNDATION_REQUIRED: SEC bulk/header access historically refused in repository probes, CIK-to-security mapping/collection not built, acceptance time and first usable date need verification. SIC is not GICS |
| Current Yahoo sector/industry, static sectors.py | No historical assignment/releases | NOT_AVAILABLE for retrospective PIT membership; keep outside the research join |
| Analyst estimate/revision history | No immutable dated estimate store or collector found. Fundamentals are realised filings, not analyst expectations | NOT_AVAILABLE in current connected sources/repository; a licensed estimate-vintage panel would require separate foundation |

The analyst-source check distinguishes dataset existence from actual usable access:
Finnhub's official enterprise product page advertises historical EPS estimates, but
this repository's current statements endpoint/collector does not collect estimate
vintages, and no estimates entitlement was verified for its account in this task.
Historical forecast periods alone do not establish publication-time revision history.
S&P's official Capital IQ Estimates description explicitly offers point-in-time
history with effective/to timestamps; it is a viable licensed lead, not acquired data.
Neither vendor's advertised dataset upgrades the current ingredient state to READY.

Primary documentation checked (no numerical performance series retrieved):

* [KRX official release listing](https://global.krx.co.kr/contents/GLB/96/9600000000/GLB9600000000T2.jsp).
* [DART company API guide](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019002).
* [S&P GICS dataset](https://www.marketplace.spglobal.com/en/datasets/gics-(90)).
* [SEC financial statement dataset field definitions](https://www.sec.gov/files/financial-statement-data-sets.pdf), SUB sic and filed/accepted fields.
* [SEC sample raw filing header](https://www.sec.gov/edgar/searchedgar/sampleheader.htm).
* [Finnhub enterprise estimate product scope](https://api.finnhub.io/pricing-startups-and-enterprise).
* [S&P Capital IQ Estimates vintage description](https://www.spglobal.com/market-intelligence/en/solutions/capital-iq-estimates).

These are source leads, not proof this account can download usable full historical data.
NOT_AVAILABLE means no accessible supported input now, not that no vendor could ever supply it.

## Granularity: outcome-free comparison, no selected count

Do not freeze 15/20/30 groups. Compare original taxonomy levels using group-count
distributions per source-universe date, classified/full denominator, unclassified names,
continuity and reclassification/gap counts, codebook interpretability and sector concentration.
SIC, historical KSIC, GICS and prospective KRICS are separate candidates with different
coverage and meanings. Medium industry groups are a candidate, not a chosen level.
`coverage_audit` emits dates/group counts and observed adjacent-date changes without prices
or outcomes. No historical membership acquired means historical granularity metrics are
null, not zero or estimated. `minimum_constituents` must be explicit; >=2 is solely the
mechanical peer floor. A future anatomy protocol must preregister a statistical minimum
from coverage, effective sample and estimand before any outcomes. Sparse groups stay
DATA_INSUFFICIENT; no outcome-driven merges. No taxonomy is selected in this foundation.

## Deterministic industry return construction (future contract)

Both equal-weight and signal-date market-cap-weight are independent published definitions;
neither is chosen by Alpha results here. For a future preregistered rebalance calendar:

1. Select the whole dated regional universe and industry membership known at signal close.
   All unclassified names are listed; because their possible industry is unknown, any
   unclassified source-universe name blocks every industry block in this strict v1 primitive.
   A separately named classified-only research universe needs a new preregistration.
2. Execute at the next regional session close; freeze names and weights until the next
   rebalance. EW is 1/N. CW uses last publicly available dated capitalization, positive,
   same currency, observation <= signal and release < signal; no future cap or interpolation.
   Currency is native KRW or USD; cross-region pooling/FX conversion is outside scope.
   Full capitalization (not free float) must be labelled. Snapshot age is recorded in input;
   a future statistical protocol must set its allowable staleness before outcomes.
3. Entrants and reclassifications enter only the next rebalance. Existing members cannot
   be dropped mid-block based on future eligibility. A delisting/successor chain follows
   the old holding's entitlements under the frozen old-industry attribution; successor
   classification cannot move that return to another industry.
4. Missing exact entry/exit, unresolved action, missing capitalization (CW) or incompatible
   basis blocks the whole observation. Never renormalize surviving weights, zero-fill,
   skip a halted name or invent a last-price endpoint. Resolved -100% is allowed only with
   real economic evidence; unresolved is None. Proven cash proceeds remain cash with zero
   yield until the common exit; reinvestment conventions and costs need future specification.
5. Splits affect share counts/price consistently; distributions follow the chosen basis.
   PRICE_RETURN excludes distributions explicitly. ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS
   remains partial. TOTAL_SHAREHOLDER_RETURN needs complete distributions and terminal
   economic evidence on every name and a compatible benchmark. No aggregate promotes partial
   constituents into “total return.” Source/bar/action identities travel with outputs.

The scalar primitive represents a fixed-cohort buy-and-hold block: R_I=sum(w_i*R_i),
not a daily reset-weight index. Future series construction must chain consecutive ready
blocks via product(1+R_I)-1. A missing block makes the chain unavailable; no bridging.
No historical series constructor/price loader is shipped. Return primitives refuse scope
other than SYNTHETIC; enabling real history requires a separately reviewed execution
protocol, frozen inputs/definitions and explicit authorization, not changing a CLI flag.

## Exact decomposition, compounding and self-inclusion

For identical entry/exit dates, basis and currency, let R_S, R_I, R_M be simple
cumulative returns over the SAME interval. Then

    (R_I - R_M) + (R_S - R_I) = R_S - R_M
    R_M + (R_I - R_M) + (R_S - R_I) = R_S

This is exact arithmetic up to floating-point precision, not approximately additive.
The stock's reference industry is frozen at signal time even if it changes later.
The full industry includes the subject; the within-industry gap is mechanically diluted
by its own weight and is not an independent company-specific causal residual. A future
leave-one-out definition must be separately named/frozen, with its own size and coverage
rules. It is not silently substituted here.

Daily arithmetic gaps cannot be compounded separately and added: compounding introduces
cross-products. For multiplicative wealth-relative returns Q_SI=(1+R_S)/(1+R_I)-1
and Q_IM=(1+R_I)/(1+R_M)-1, Q_SM=Q_SI+Q_IM+Q_SI*Q_IM. Log wealth ratios add exactly
only when all gross wealth factors are positive; -100% makes logs undefined. Our API
reports simple gaps only. Synthetic tests show both identities and the cross term;
no historical H63/H126/H252 target is constructed.

## Candidate feature readiness (industry level is NOT ready)

READY applies to a verified contract/primitives, not to a complete historical industry
panel. PARTIAL means some constituent-level information exists but source semantics,
coverage, dated membership or denominator integrity is missing. The machine-readable
matrix lists each family and blocker. No new feature is computed on real data.

| Family | KR / US ingredient state | Industry-panel state and required gate |
|---|---|---|
| Relative momentum; breadth; dispersion; volatility | PARTIAL / PARTIAL: sealed price/index mechanisms; membership/terminal/distribution limits | DATA_FOUNDATION_REQUIRED: same PIT cohort, trailing-only prices, no synthetic/current classification |
| Liquidity / ADV; concentration | PARTIAL / PARTIAL: OHLCV, KR dated cap; US historical cap not universally verified | DATA_FOUNDATION_REQUIRED: as-traded price x volume, same cohort, dated cap and denominator/units; adjusted-index Close is not monetary ADV |
| Revenue; operating profit | PARTIAL / PARTIAL: legacy DART / Finnhub account chains, repaired KR four-family scope does not guarantee these | DATA_FOUNDATION_REQUIRED: independent concept/coverage check, currency/period/basis consistency |
| Net income; OCF; assets/leverage | PARTIAL / PARTIAL: repaired KR + filed US; original/amendment/TTM limitations | DATA_FOUNDATION_REQUIRED: matched visible cohorts, original release evidence, no missing zero or changing-population growth |
| Aggregate changes / improvement breadth | PARTIAL / PARTIAL | DATA_FOUNDATION_REQUIRED: same-name same-stage comparisons; report measured/full denominators; negative-base growth undefined |
| Analyst EPS revisions, estimate breadth, estimate dispersion | NOT_AVAILABLE / NOT_AVAILABLE in current inputs | NOT_AVAILABLE: require estimate publication timestamps, forecast fiscal/horizon alignment, broker coverage and vintage history |
| Capex; capex/sales; asset growth | PARTIAL / PARTIAL: accounting_quality ingredients; KR capex sparse and not repaired scope | DATA_FOUNDATION_REQUIRED: period/concept/coverage gate; no missing capex=0 |
| Exports, orders, shipments, product/commodity prices, spreads | DATA_FOUNDATION_REQUIRED / DATA_FOUNDATION_REQUIRED: ECOS/FRED/other official leads only | DATA_FOUNDATION_REQUIRED: economic-to-taxonomy crosswalk, units, release and revision vintages; no one-off feature built |

A future external-industry observation schema must carry region, taxonomy/version,
industry_id, metric_id, unit/currency, observation period, published_at, vintage_id,
source URL and raw hash, economic-to-taxonomy mapping validity/release dates. Vintage
selection is published_at < signal, never observation month alone. Revised annual
exports or current commodity histories are not automatically PIT. Industry-specific
signals can legitimately differ between KR and US, and are never pooled just to make
one feature matrix.

## Future roadmap and execution boundaries

1. This foundation: contracts, source gaps, synthetic mechanics. Next action is dated
   taxonomy acquisition/identity verification and an outcome-free coverage audit, then
   complete corporate-action/distribution basis. Do not request model execution yet.
2. `industry-opportunity-anatomy-v1`: new preregistration for associations between
   signal-time industry characteristics and later industry-minus-market returns.
   Freeze taxonomy/weights/horizons/sample/benchmarks/costs, source hashes and inference;
   exposed history stays exploratory. Findings can motivate an independent ranking study.
3. `within-industry-stock-anatomy-v1`: separately preregister company characteristics
   against own signal-date industry. Control cohort changes, self-inclusion and sparse
   groups; do not assume anatomy alone is profitable.
4. `hierarchical-alpha-model-v1`: possible additive predictions of industry-market gap
   and stock-industry gap on the same simple-return target. Separate training chronology,
   regional sources and methods; anatomy does not require this model stack. No model is
   selected, fitted or cross-validated now.
5. Portfolio/risk-budget study: connect to future benchmark-relative net returns with
   realistic participation, liquidity, entry prices, turnover/slippage, native taxes and
   concentrated-book risk. Market budget is separate from company selection. Predictive
   association and decomposition alone do not prove net Alpha or justify promotion.

Every execution requires its own reviewed preregistration and immutable inputs, and any
one-shot guard is claimed only AFTER input identity and readiness checks, BEFORE outcomes.
The foundation grants no execution permit and touches no previous study's lock/results.

## Deliverables and verification

New standalone membership/aggregation/decomposition module, machine-readable design spec
and SHA-256 sidecar, JSON row schema, source/feature matrix, metadata audit runner, read-only
metadata workflow, tests and synthetic fixture. Dependencies are pinned; editing a pinned
contract causes verification failure. No production imports, weights or generation bump.
`docs/workflow-inventory-addendum.md` records the new metadata-only workflow because the
original inventory is pinned by existing studies and cannot be changed.

Run targeted tests, full pytest, ruff, compileall, seed generation and seed artifact
validation. The audit output contains source readiness only, no historical return, model
prediction, portfolio or industry ranking. Unit return examples are explicitly synthetic.

NO HISTORICAL ALPHA OUTCOME WAS COMPUTED

NO INDUSTRY TAXONOMY WAS SELECTED USING FUTURE RETURNS

NO PRIOR SEALED STUDY WAS RERUN

THIS FOUNDATION SERVES THE BROADER OBJECTIVE OF FUTURE BENCHMARK-RELATIVE ALPHA,
BUT DOES NOT CLAIM ALPHA ITSELF.

## KR market-context implementation revision (PR #188)

The reusable KR context and safe ECOS validation path are detailed in
`docs/kr-market-context-foundation-v1.md`. They implement separate domestic
growth, inflation, rates, liquidity/credit, external financial conditions
and equity-market measurements. Revised ECOS history never becomes PIT_EXACT
through a publication lag. The manual source validation is still awaiting an
authorized dispatch path; the machine-readable matrix does not claim a live
run. Source/feature readiness and identity pins now include this layer.

The original alpha-opportunity-model-v1 seal pins shared config/ecos modules.
Repairing those modules intentionally makes its old closure fail closed; its
specification, hashes and runner are not resealed or changed. The hash-pinned legacy test file is byte-preserved. Three old open-closure
assertions are strict-xfailed through the existing conftest supersession pattern;
new context tests verify refusal before inputs or training. No study is reopened.
