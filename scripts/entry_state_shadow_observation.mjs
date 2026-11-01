/**
 * Source-pinned, read-only first paper A/B observation. No prices, fills or returns.
 *
 * Usage:
 * node scripts/entry_state_shadow_observation.mjs CHAMPION_LATEST WEEKLY_LATEST CONFIG SOURCE_COMMIT [OUTPUT]
 *
 * Inputs are two already-published SAME-ARTIFACT receipts from the repository's
 * signal-history branch, at an immutable SOURCE_COMMIT. This is a current-origin
 * projection, NOT reproduction of the historical replay-v16 study.
 */
import fs from "node:fs";
import crypto from "node:crypto";

const REGIONS = Object.freeze({KR: "069500.KS", US: "SPY"});
const VERSION = "ENTRY_STATE_SHADOW_PAIRED_FIRST_V1";
const round6 = n => Math.round((n + Number.EPSILON) * 1e6) / 1e6;
const isNum = n => typeof n === "number" && Number.isFinite(n);
const sum = o => Object.values(o).reduce((a, b) => a + b, 0);
const hash = data => crypto.createHash("sha256").update(data).digest("hex");

function choose(rows, selection, challenger) {
  const target = Math.min(selection.targetNames, selection.maxNamesPerRegion);
  const bySector = {};
  const ordered = rows.filter(x => x.eligible).map(x => ({
    ...x,
    comparisonScore: challenger ? x.convictionScore / x.entryStateMultiplier : x.convictionScore
  })).sort((a, b) => b.comparisonScore - a.comparisonScore ||
    String(a.ticker).localeCompare(String(b.ticker)));
  const chosen = [];
  for (const row of ordered) {
    if (chosen.length >= target) break;
    if ((bySector[row.sector] || 0) >= selection.maxNamesPerSector) continue;
    chosen.push(row);
    bySector[row.sector] = (bySector[row.sector] || 0) + 1;
  }
  return chosen;
}

function boundedMissingComplete(weeklyPool, ranked, chosen, selection) {
  // latest.json publishes selected names + only 8 near misses, not the full
  // candidate population. Even one omitted eligible 0.25x name could jump to
  // the challenger cut. A rigorous upper bound (coverage <=1) must exclude it.
  const seen = new Set(ranked.map(x => x.ticker));
  if (seen.size !== ranked.length || weeklyPool.length !== selection.consideredCount)
    return false;
  const cutoff = chosen.length ? chosen[chosen.length - 1].comparisonScore : -Infinity;
  if (chosen.length < Math.min(selection.targetNames, selection.maxNamesPerRegion))
    return weeklyPool.every(x => seen.has(x.ticker) ||
      ["AVOID", "EVENT_RISK"].includes(x.entryState));
  for (const missing of weeklyPool.filter(x => !seen.has(x.ticker))) {
    if (["AVOID", "EVENT_RISK"].includes(missing.entryState)) continue;
    const alpha = missing.alphaPercentile;
    const risk = missing.downsideVolPct;
    if (!isNum(alpha) || !isNum(risk) || risk <= 0) return false;
    if (alpha < selection.minAlphaPercentile) continue;
    // Published current production score = max(0,(alpha-50)/50)/risk
    // * evidenceCoverage * entryMultiplier. EvidenceCoverage <=1; the
    // challenger removes ONLY entryMultiplier.
    const maximum = Math.max(0, (alpha - 50) / 50) / Math.max(risk / 100, 0.05);
    if (maximum >= cutoff - 1e-8) return false;
  }
  return true;
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
    const originalChosen = choose(active, s, false);
    const alternateChosen = choose(active, s, true);
    if (!boundedMissingComplete(weeklyPool, ranking, alternateChosen, s)) {
      results[region] = blocked("TRUNCATED_RANKING_COULD_CHANGE_CHALLENGER");
      continue;
    }
    const control = weights(originalChosen, config, original.appliedMinCashPct, false);
    if (!sameAsPublishedControl(control, original.weights, benchmark)) {
      results[region] = blocked("ORIGINAL_CONTROL_RECONSTRUCTION_FAILED");
      continue;
    }
    const challenger = weights(alternateChosen, config, original.appliedMinCashPct, true);
    results[region] = {
      status: "RESEARCH_SNAPSHOT_ONLY_NOT_LIVE_VALIDATED",
      asOfDate: a.asOfDate,
      sourceReceiptId: a.receiptId,
      consideredCount: s.consideredCount, originallyEligibleCount: s.eligibleCount,
      rankedRowsRetained: ranking.length,
      omittedCandidateUpperBoundChecked: ranking.length < s.consideredCount,
      control: {selected: originalChosen.map(v => v.ticker), ...control,
        residualAsset: benchmark, sameAsPublished: true},
      challenger: {selected: alternateChosen.map(v => v.ticker), ...challenger,
        residualAsset: benchmark, note: "after pre-throttle caps; no redistribution"},
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
    regions: results
  };
}

if (process.argv[1]?.endsWith("entry_state_shadow_observation.mjs")) {
  const args = process.argv.slice(2);
  if (args.length < 4 || args.length > 5)
    throw Error("Usage: node scripts/entry_state_shadow_observation.mjs CHAMPION_LATEST WEEKLY_LATEST CONFIG SOURCE_COMMIT [OUTPUT]");
  const inputs = args.slice(0, 3).map(p => fs.readFileSync(p));
  const [champion, weekly, fullConfig] = inputs.map(x => JSON.parse(x.toString("utf8")));
  const output = observe(champion, weekly, fullConfig.kellyPortfolio, args[3], {
    championSha256: hash(inputs[0]), weeklySha256: hash(inputs[1]),
    configSha256: hash(inputs[2])
  });
  const serialized = JSON.stringify(output, null, 2) + "\n";
  if (args[4]) {
    const file = args[4];
    if (fs.existsSync(file)) throw Error("APPEND_ONLY_EXISTING_OBSERVATION_REFUSED");
    fs.writeFileSync(file, serialized, {flag: "wx"});
  } else process.stdout.write(serialized);
}
