/**
 * Source-pinned, read-only first paper A/B observation. No prices, fills or returns.
 *
 * Usage:
 * node scripts/entry_state_shadow_observation.mjs CHAMPION_LATEST WEEKLY_LATEST CONFIG SOURCE_COMMIT CONFIG_COMMIT [OUTPUT]
 *
 * Inputs are two already-published SAME-ARTIFACT receipts from the repository's
 * signal-history branch, at an immutable SOURCE_COMMIT. This is a current-origin
 * projection, NOT reproduction of the historical replay-v16 study.
 */
import fs from "node:fs";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

const REGIONS = Object.freeze({KR: "069500.KS", US: "SPY"});
const VERSION = "ENTRY_STATE_SHADOW_CARDINALITY_V3";
// Scenario grid, not a cap: the same grid entry-state-role-etf-residual-v1 values historically.
export const SCENARIO_COUNTS = Object.freeze([0, 1, 2, 3, 4, 5, 10]);
const round6 = n => Math.round((n + Number.EPSILON) * 1e6) / 1e6;
const isNum = n => typeof n === "number" && Number.isFinite(n);
const sum = o => Object.values(o).reduce((a, b) => a + b, 0);
const hash = data => crypto.createHash("sha256").update(data).digest("hex");

export function choose(rows, selection, challenger, capacity = null, audit = null) {
  // The existing 3-name regional limit belongs ONLY to the legacy control.
  // Research scenarios take their count from SCENARIO_COUNTS; no count is a
  // permanent maximum and none is a mandatory minimum.
  const target = capacity === null ?
    Math.min(selection.targetNames, selection.maxNamesPerRegion) : capacity;
  if (!Number.isInteger(target) || target < 0)
    throw Error("INVALID_CARDINALITY");
  const bySector = {};
  const ordered = rows.filter(x => x.eligible).map(x => ({
    ...x,
    comparisonScore: challenger ? x.convictionScore / x.entryStateMultiplier : x.convictionScore
  })).sort((a, b) => b.comparisonScore - a.comparisonScore ||
    String(a.ticker).localeCompare(String(b.ticker)));
  const chosen = [];
  for (const row of ordered) {
    if (chosen.length >= target) {
      if (audit) audit[row.ticker] = "BELOW_TARGET_COUNT_CUTOFF";
      continue;
    }
    if ((bySector[row.sector] || 0) >= selection.maxNamesPerSector) {
      if (audit) audit[row.ticker] = "SECTOR_NAME_LIMIT";
      continue;
    }
    chosen.push(row);
    if (audit) audit[row.ticker] = "SELECTED";
    bySector[row.sector] = (bySector[row.sector] || 0) + 1;
  }
  return chosen;
}

function boundedMissingComplete(weeklyPool, ranked, chosen, selection, capacity, challenger, config) {
  if (capacity === 0) return true; // 100%-ETF needs no individual rank.
  const seen = new Set(ranked.map(x => x.ticker));
  if (seen.size !== ranked.length || weeklyPool.length !== selection.consideredCount)
    return false;
  if (chosen.length !== capacity) return false;
  const cutoff = chosen[chosen.length - 1].comparisonScore;
  for (const missing of weeklyPool.filter(x => !seen.has(x.ticker))) {
    const state = missing.entryState;
    const multiplier = state === "WAIT_FOR_PULLBACK" ? config.waitForPullbackWeightMultiplier :
      state === "WATCH" ? config.watchWeightMultiplier :
      state === "ACCUMULATE_GRADUALLY" ? 1 :
      state === "AVOID" || state === "EVENT_RISK" ? 0 : null;
    if (multiplier === null || !isNum(multiplier)) return false;
    if (multiplier === 0) continue;
    const alpha = missing.alphaPercentile;
    const risk = missing.downsideVolPct;
    if (!isNum(alpha) || !isNum(risk) || risk <= 0) return false;
    if (alpha < selection.minAlphaPercentile) continue;
    // Maximum unknown rank assumes evidenceCoverage=1; never fill in an
    // unobserved value or silently treat an omitted stock as ineligible.
    const maximum = Math.max(0, (alpha - 50) / 50) / Math.max(risk / 100, 0.05) *
      (challenger ? 1 : multiplier);
    if (maximum >= cutoff - 1e-8) return false;
  }
  return true;
}

function candidateAudit(pool, ranking, audit) {
  const ranked = new Map(ranking.map(r => [r.ticker, r]));
  return pool.map(c => {
    const r = ranked.get(c.ticker);
    const status = !r ? "NOT_IN_PUBLISHED_RANKING_BOUNDED_BELOW_CUTOFF" :
      !r.eligible ? "INELIGIBLE" : (audit[c.ticker] || "NOT_REACHED");
    return {ticker: c.ticker, sector: c.sector, entryState: c.entryState,
      eligible: r ? !!r.eligible : null, status};
  }).sort((a, b) => a.ticker.localeCompare(b.ticker));
}

function weights(chosen, config, minCashPct, throttled) {
  if (!chosen.length) return {stocks: {}, residual: 1};
  const target = 1 - minCashPct / 100;
  const ranks = Object.fromEntries(chosen.map((x, i) => [x.ticker, i]));
  const n = chosen.length;
  let raw = {};
  for (const row of chosen) {
    const tilt = n === 1 ? 1 :
      1 + config.selection.convictionTiltRange * (0.5 - ranks[row.ticker] / (n - 1));
    raw[row.ticker] = tilt / Math.max(row.downsideVolPct / 100, 0.05);
  }
  const total = sum(raw);
  for (const k in raw) raw[k] = Math.min(config.maxPositionWeight, raw[k] / total * target);
  for (let p = 0; p < 4; p++) {
    for (const axis of ["sector", "region"]) {
      const groups = {};
      for (const row of chosen) {
        const label = axis === "sector" ? row.sector : row.region;
        (groups[label] ||= []).push(row.ticker);
      }
      for (const [label, names] of Object.entries(groups)) {
        const cap = axis === "sector" ? config.maxSectorWeight :
          (config.regionCaps?.[label] ?? 1);
        const amount = names.reduce((a, k) => a + raw[k], 0);
        if (amount > cap + 1e-10) {
          for (const k of names) raw[k] *= cap / amount;
        }
      }
    }
  }
  if (sum(raw) > target) {
    const factor = target / sum(raw);
    for (const k in raw) raw[k] *= factor;
  }
  // The original baseline is capped before the alternative's entry-state
  // throttle. Withheld capital is NOT reallocated into another stock.
  for (const row of chosen) {
    raw[row.ticker] = round6(raw[row.ticker] *
      (throttled ? row.entryStateMultiplier : 1));
  }
  return {stocks: raw, residual: round6(1 - sum(raw))};
}

function sameAsPublishedControl(calculated, published, benchmark) {
  const expected = Object.fromEntries(Object.entries(published)
    .filter(([ticker]) => ticker !== benchmark));
  if (Object.keys(expected).length !== Object.keys(calculated.stocks).length) return false;
  if (!Object.entries(expected).every(([ticker, weight]) =>
      isNum(weight) && isNum(calculated.stocks[ticker]) &&
      Math.abs(weight - calculated.stocks[ticker]) < 0.0000011)) return false;
  return isNum(published[benchmark]) &&
    Math.abs(published[benchmark] - calculated.residual) < 0.0000011;
}

export function observe(champion, weekly, config, sourceCommit, sourceHashes = {}) {
  if (!/^[0-9a-f]{40}$/.test(sourceCommit))
    throw Error("IMMUTABLE_SOURCE_COMMIT_REQUIRED");
  if (champion.schema !== "CURRENT_CHAMPION_ARTIFACT_V1" ||
      champion.liveValidated !== false || champion.version !== "current-champion-decisions-v1" ||
      typeof champion.sourceArtifactSha256 !== "string" ||
      !/^[0-9a-f]{64}$/.test(champion.sourceArtifactSha256))
    throw Error("UNSUPPORTED_CHAMPION_SOURCE");
  if (champion.generatedAt !== weekly.generatedAt)
    throw Error("DIFFERENT_GENERATION_CANNOT_PAIR");
  const results = {};
  for (const [region, benchmark] of Object.entries(REGIONS)) {
    const a = champion.regions?.[region];
    const b = weekly.regions?.[region];
    const blocked = reason => ({status: "BLOCKED", reason,
      asOfDate: a?.asOfDate || null, control: null, challenger: null});
    if (!a || !b || a.status !== "READY" ||
        a.asOfDate !== b.asOfDate || a.sourceObservedDate !== a.asOfDate ||
        b.inputs?.siteDataSha256 !== champion.sourceArtifactSha256) {
      results[region] = blocked("DATED_SAME_SOURCE_RECEIPTS_NOT_READY");
      continue;
    }
    const original = a.decisions?.C2;
    const ranking = original?.selection?.ranking;
    const weeklyPool = b.candidates;
    const s = original?.selection;
    if (!Array.isArray(ranking) || !Array.isArray(weeklyPool) || !s ||
        !isNum(original.appliedMinCashPct) || !isNum(s.eligibleCount) ||
        !isNum(s.consideredCount) || !isNum(s.targetNames) ||
        !isNum(s.maxNamesPerRegion) || !isNum(s.maxNamesPerSector) ||
        !isNum(s.minAlphaPercentile) ||
        weeklyPool.length !== s.consideredCount ||
        !config?.selection || s.targetNames !== config.selection.targetNames ||
        s.maxNamesPerRegion !== config.selection.maxNamesPerRegion ||
        s.maxNamesPerSector !== config.selection.maxNamesPerSector ||
        s.minAlphaPercentile !== config.selection.minAlphaPercentile) {
      results[region] = blocked("SELECTION_CONTRACT_OR_SOURCE_INCOMPLETE");
      continue;
    }
    const byTicker = new Map(weeklyPool.map(v => [v.ticker, v]));
    if (byTicker.size !== weeklyPool.length) {
      results[region] = blocked("DUPLICATE_OR_MISSING_CANDIDATES");
      continue;
    }
    const valid = ranking.every(row => {
      const w = byTicker.get(row.ticker);
      if (!w || row.region !== region || row.sector !== w.sector ||
          row.alphaPercentile !== w.alphaPercentile ||
          row.downsideVolPct !== w.downsideVolPct) return false;
      if (!row.eligible) return true;
      const required = w.entryState === "WATCH" ? config.watchWeightMultiplier :
        w.entryState === "WAIT_FOR_PULLBACK" ? config.waitForPullbackWeightMultiplier :
        w.entryState === "ACCUMULATE_GRADUALLY" ? 1 : 0;
      return isNum(row.convictionScore) && isNum(row.entryStateMultiplier) &&
        row.entryStateMultiplier > 0 && required === row.entryStateMultiplier &&
        isNum(row.evidenceCoverage) && row.evidenceCoverage >= 0 &&
        row.evidenceCoverage <= 1 && row.riskUnitFallback === false;
    });
    if (!valid) {
      results[region] = blocked("REGIONAL_CANDIDATE_SOURCE_CONFLICT");
      continue;
    }
    const active = ranking.filter(row => row.eligible);
    if (active.length > s.eligibleCount) {
      results[region] = blocked("ELIGIBLE_COUNT_CONFLICT");
      continue;
    }
    const originalChosen = choose(active, s, false); // legacy 3-name control only
    if (!boundedMissingComplete(weeklyPool, ranking, originalChosen, s,
          originalChosen.length, false, config)) {
      results[region] = blocked("TRUNCATED_RANKING_COULD_CHANGE_CONTROL");
      continue;
    }
    const control = weights(originalChosen, config, original.appliedMinCashPct, false);
    if (!sameAsPublishedControl(control, original.weights, benchmark)) {
      results[region] = blocked("ORIGINAL_CONTROL_RECONSTRUCTION_FAILED");
      continue;
    }
    // No fixed three-name selection. Research ALL 0..5; neither three nor five
    // is inherently better. Separate cardinality and rank/weight mechanisms
    // using identically sized paired variants at each feasible count.
    const researchScenarios = [];
    for (const count of SCENARIO_COUNTS) {
      const audit0 = {}, audit1 = {};
      const arm0 = choose(active, s, false, count, audit0);
      const arm1 = choose(active, s, true, count, audit1);
      if (arm0.length !== count || arm1.length !== count) {
        researchScenarios.push({stockCount: count, status: "INSUFFICIENT_ELIGIBLE_NAMES",
          rankStateInSelection: null, stateAtPositionWeight: null});
        continue;
      }
      if (!boundedMissingComplete(weeklyPool, ranking, arm0, s, count, false, config) ||
          !boundedMissingComplete(weeklyPool, ranking, arm1, s, count, true, config)) {
        researchScenarios.push({stockCount: count,
          status: "TRUNCATED_RANKING_COULD_CHANGE_SELECTION",
          rankStateInSelection: null, stateAtPositionWeight: null});
        continue;
      }
      const base = weights(arm0, config, original.appliedMinCashPct, false);
      const alternative = weights(arm1, config, original.appliedMinCashPct, true);
      researchScenarios.push({stockCount: count, status: "SOURCE_PINNED_COUNTERFACTUAL",
        rankStateInSelection: {selected: arm0.map(x => x.ticker),
          ...base, residualAsset: benchmark,
          candidateAudit: candidateAudit(weeklyPool, ranking, audit0)},
        stateAtPositionWeight: {selected: arm1.map(x => x.ticker),
          ...alternative, residualAsset: benchmark,
          candidateAudit: candidateAudit(weeklyPool, ranking, audit1)}});
    }
    // Current P1 weekly decision is authoritative for whether a stock has
    // demonstrated a positive incremental advantage. A shortlist, raw
    // alpha-percentile or arbitrary count is NEVER evidence of that advantage.
    // If that gate is not explicitly PASSIVE, fail closed rather than infer
    // that any one of these six counterfactual choices is optimal.
    const passiveVerified = b.status === "PASSIVE_NO_DEFENSIBLE_EDGE" &&
      weeklyPool.every(x => x.edgeAvailable === false &&
        x.expectedNetAdvantagePct === null);
    results[region] = {
      status: "RESEARCH_SNAPSHOT_ONLY_NOT_LIVE_VALIDATED",
      asOfDate: a.asOfDate,
      sourceReceiptId: a.receiptId,
      consideredCount: s.consideredCount, originallyEligibleCount: s.eligibleCount,
      rankedRowsRetained: ranking.length,
      legacyControlOnly: {stockCount: originalChosen.length, selected: originalChosen.map(v => v.ticker),
        ...control, residualAsset: benchmark, sameAsPublished: true,
        note: "Existing maxNamesPerRegion=3 is NOT a research cardinality recommendation"},
      scenarioStockCounts: [...SCENARIO_COUNTS],
      researchScenarios,
      currentPolicy: passiveVerified ?
        {status: "PASSIVE_NO_DEFENSIBLE_EDGE", stockCount: 0,
          holdings: {}, benchmark, benchmarkWeight: 1,
          basis: "PUBLISHED_WEEKLY_POLICY_NOT_COUNTERFACTUAL_BACKTEST_WINNER"} :
        {status: "NO_VERIFIED_STOCK_SELECTION_AVAILABLE", stockCount: null,
          holdings: null, benchmark, benchmarkWeight: null},
      cardinalityWinner: null,
      selectionCriterion: "Future evidence-backed positive NET excess after costs, risk & multiplicity; no chosen count from exposed history",
      costs: null, realizedReturn: null, expectedAlpha: null,
      nextEligibleExecution: null
    };
  }
  return {
    schema: VERSION, sourceCommit, sourceHashes,
    sourceArtifactSha256: champion.sourceArtifactSha256,
    sourceGeneratedAt: champion.generatedAt,
    classification: "HISTORICAL_SESSION_OBSERVED_BEFORE_NEXT_SESSION; NOT_PROSPECTIVE_OUTCOME",
    status: "READ_ONLY_RESEARCH_NO_ORDERS_NO_VALIDATED_ALPHA",
    residualConvention: "ETF_NOT_CASH; DIFFERENT_FROM_OLD_REPLAY_V16",
    stockCountPolicy: "Scenario grid 0,1,2,3,4,5,10; no count is a permanent maximum or a mandatory minimum; 0 stocks + 100% ETF is valid",
    rankAndCountAreSeparateVariables: true,
    portfolioDPolicy: {
      permanentCombinedMaximum: null,
      regionalScenariosAreNotSimultaneousCombinedAllocations: true,
      allocationAcrossKRAndUS: null,
      note: "Each region is a separate book against its own ETF. No combined KR+US count is fixed here; a combined count is a later, evidence-backed decision, never a sum of two regional ladders."
    },
    regions: results
  };
}

if (process.argv[1]?.endsWith("entry_state_shadow_observation.mjs")) {
  const raw = process.argv.slice(2);
  const preCommit = raw.includes("--pre-commit-bytes");
  const args = raw.filter(a => a !== "--pre-commit-bytes");
  if (args.length < 5 || args.length > 6)
    throw Error("Usage: node scripts/entry_state_shadow_observation.mjs CHAMPION_LATEST WEEKLY_LATEST CONFIG SOURCE_COMMIT [OUTPUT]");
  const inputs = args.slice(0, 3).map(p => fs.readFileSync(p));
  if (!/^[0-9a-f]{40}$/.test(args[3])) throw Error("IMMUTABLE_SOURCE_COMMIT_REQUIRED");
  // A claimed SHA or file hash is not source verification. Authenticate the
  // bytes against the Git *objects* reachable from this exact source commit.
  const sourcePaths = [
    "ledger/research-strategies/current-champion-decisions-v1/latest.json",
    "ledger/weekly-decisions/latest.json"
  ];
  for (let i = 0; i < sourcePaths.length && !preCommit; i++) {
    const original = execFileSync("git", ["show", args[3] + ":" + sourcePaths[i]], {
      cwd: process.cwd(), maxBuffer: 4 * 1024 * 1024
    });
    if (!original.equals(inputs[i])) throw Error("IMMUTABLE_GIT_SOURCE_MISMATCH");
  }
  if (!/^[0-9a-f]{40}$/.test(args[4])) throw Error("IMMUTABLE_CONFIG_COMMIT_REQUIRED");
  if (!preCommit) {
    const trustedConfig = execFileSync("git", ["show", args[4] + ":config.json"], {
      cwd: process.cwd(), maxBuffer: 2 * 1024 * 1024
    });
    if (!trustedConfig.equals(inputs[2])) throw Error("IMMUTABLE_CONFIG_GIT_SOURCE_MISMATCH");
  }
  const [champion, weekly, fullConfig] = inputs.map(x => JSON.parse(x.toString("utf8")));
  const output = observe(champion, weekly, fullConfig.kellyPortfolio, args[3], {
    championSha256: hash(inputs[0]), weeklySha256: hash(inputs[1]),
    configSha256: hash(inputs[2]),
    sourceVerification: preCommit ? "SHA256_OF_BYTES_WRITTEN_IN_THIS_RUN_BEFORE_COMMIT" :
      "GIT_OBJECTS_AT_SOURCE_AND_CONFIG_COMMITS"
  });
  const serialized = JSON.stringify(output, null, 2) + "\n";
  if (args[5]) {
    const file = args[5];
    if (fs.existsSync(file)) throw Error("APPEND_ONLY_EXISTING_OBSERVATION_REFUSED");
    fs.writeFileSync(file, serialized, {flag: "wx"});
  } else process.stdout.write(serialized);
}
