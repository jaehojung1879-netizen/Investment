// Pure presentation tests; actual historical paths are read, never replayed.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { webcrypto, createHash } = require("node:crypto");
globalThis.crypto = webcrypto;
const root = path.resolve(__dirname, "..");
const A = require(path.join(root, "app.js"));
const NOW = Date.parse("2026-10-11T12:00:00Z");
const clone = (x) => structuredClone(x);
function receipt(market = "KR", count = 0) {
  const benchmark = market === "KR" ? "069500.KS" : "SPY";
  const holdings = Array.from({ length: count }, (_, i) => ({
    ticker: `T${i}`,
    name: `종목 ${i}`,
    weightPct: 15,
    reasonKo: "기록된 설명",
  }));
  return {
    schema: "WEEKLY_DECISION_RECEIPT_V1",
    policyVersion: "weekly-passive-first-v1",
    region: market,
    benchmark,
    benchmarkName: benchmark,
    receiptId: `weekly-passive-first-v1|${market}|2026-10-09`,
    asOfDate: "2026-10-09",
    generatedAt: "2026-10-11T05:00:00Z",
    digest: "a".repeat(64),
    weekStatus: "FINAL_WEEKLY",
    liveValidated: false,
    evidenceStatus: { verifiedLive: "NOT_VERIFIED" },
    status: count ? "STOCKS_SELECTED" : "PASSIVE_NO_DEFENSIBLE_EDGE",
    stockCount: count,
    holdings,
    weights: {
      ...Object.fromEntries(holdings.map((h) => [h.ticker, 0.15])),
      [benchmark]: 1 - count * 0.15,
    },
    stockWeightPct: count * 15,
    benchmarkWeightPct: 100 - count * 15,
    noTradeReason: count ? null : "ORDERING_NOT_ESTABLISHED",
  };
}
function bundle(r = receipt()) {
  const generatedAt = "2026-10-11T05:00:00Z";
  return {
    receipts: [r],
    latest: {
      schema: "WEEKLY_DECISION_ARTIFACT_V1",
      generatedAt,
      blocked: false,
      liveValidated: false,
      regions: {
        [r.region]: {
          ...r,
          freshness: {
            status: "FRESH",
            observedSession: r.asOfDate,
            expectedSession: r.asOfDate,
          },
        },
      },
    },
    publication: {
      schema: "WEEKLY_PUBLICATION_STATUS_V1",
      status: "PUBLISHED",
      siteGeneratedAt: generatedAt,
      attemptedAt: "2026-10-11T05:01:00Z",
    },
  };
}
const read = (key) =>
  JSON.parse(fs.readFileSync(path.join(root, A.SOURCES[key].path), "utf8"));
test("all performance sources have exact committed byte hashes", () => {
  for (const source of Object.values(A.SOURCES))
    assert.equal(
      createHash("sha256")
        .update(fs.readFileSync(path.join(root, source.path)))
        .digest("hex"),
      source.sha256,
    );
});
test("corrected weekly and 21-session studies remain separate", () => {
  const weekly = A.studyData(read("weekly"), "KR", "weekly");
  const anchors = A.studyData(read("anchors"), "KR", "anchors");
  assert.equal(weekly.decisions.length, 713);
  assert.equal(weekly.stockDecisions.length, 4);
  assert.equal(weekly.paths.P0.cagrPct, 12.507);
  assert.equal(weekly.paths.P1.cagrPct, 12.043);
  assert.equal(weekly.paths.P1.excessCagrPp, -0.463);
  assert.equal(anchors.decisions.length, 155);
  assert.equal(anchors.paths.C2.excessCagrPp, 1.752);
  assert.deepEqual(weekly.keys, ["P0", "P1"]);
  assert.deepEqual(anchors.keys, ["P0", "P1", "C1", "C2"]);
  assert.equal(A.studyData(read("anchors"), "KR", "weekly"), null);
});
test("US contains no stock selections or unsupported stock strategy path", () => {
  const s = A.studyData(read("weekly"), "US", "weekly");
  assert.equal(s.stockDecisions.length, 0);
  assert.equal(s.decisions.length, 713);
  assert.deepEqual(s.weeklyNav.P0, s.weeklyNav.P1);
  assert.equal(s.paths.P1.excessCagrPp, 0);
  const html = A.performanceMarkup(
    s,
    "US",
    { P0: true, P1: true },
    read("usd"),
  );
  assert.match(html, /14\.734%/);
  assert.match(html, /16\.698%/);
  assert.match(html, /KRW/);
  assert.match(html, /개별 종목 선택 실적 없음/);
  assert.doesNotMatch(html, /data-week=/);
  assert.equal(A.studyData(read("anchors"), "US", "anchors"), null);
});
test("inflated benchmark, changed cadence, bad NAV and missing metrics fail closed", () => {
  for (const mutate of [
    (r) => (r.benchmarkBasis = "replay-v16"),
    (r) => (r.regions.KR.benchmarkDefinition = "NOT_RECONCILED"),
    (r) => (r.regions.KR.weeklyNav.P0[0][1] = 0),
    (r) => (r.regions.KR.paths.P1.cagrPct = null),
    (r) => (r.regions.KR.paths.P1.startDate = "2014-01-01"),
    (r) =>
      (r.regions.KR.decisions[0].signalDate = r.regions.KR.decisions[0].date),
  ]) {
    const r = read("weekly");
    mutate(r);
    assert.equal(A.studyData(r, "KR", "weekly"), null);
  }
});
test("C2 is visible with the exact observed excess and exploratory limitation", () => {
  const html = A.performanceMarkup(
    A.studyData(read("anchors"), "KR", "anchors"),
    "KR",
    { P0: true, P1: true, C1: true, C2: true },
  );
  assert.match(html, /\+1\.752%p/);
  assert.match(html, /사후 탐색 · 독립 검증 미완료/);
  assert.match(html, /동일한 종목을 선택했지만/);
  assert.match(html, /결과를 본 뒤 만든 조합/);
});
test("zero stocks requires an explicit full benchmark receipt", () => {
  const b = bundle();
  assert.equal(A.decisionState(b, "KR", NOW).state, "BENCHMARK_ONLY");
  const html = A.decisionMarkup(
    A.decisionState(b, "KR", NOW),
    "KR",
    "b".repeat(40),
  );
  assert.match(html, /100%/);
  assert.doesNotMatch(html, /class="holdings"|<table/);
  b.receipts[0].weights = {};
  assert.equal(A.decisionState(b, "KR", NOW).state, "UNAVAILABLE_OR_BLOCKED");
});
for (const count of [1, 2, 3, 4, 5])
  test(`${count} stocks uses exact receipt weights and residual`, () => {
    const b = bundle(receipt("KR", count));
    const d = A.decisionState(b, "KR", NOW);
    assert.equal(d.state, "STOCKS_PLUS_BENCHMARK");
    const html = A.decisionMarkup(d, "KR", "b".repeat(40));
    assert.match(html, /15\.00%/);
    assert.ok(html.includes(`${(100 - count * 15).toFixed(2)}%`));
  });
test("missing, refused, stale, future, blocked and preview sources do not carry prior weights", () => {
  assert.equal(
    A.decisionState(null, "KR", NOW).state,
    "UNAVAILABLE_OR_BLOCKED",
  );
  for (const mutate of [
    (b) => (b.publication.status = "REFUSED"),
    (b) => (b.latest.blocked = true),
    (b) => (b.latest.generatedAt = "2026-10-01T00:00:00Z"),
    (b) => (b.latest.generatedAt = "2026-11-01T00:00:00Z"),
    (b) => (b.latest.regions.KR.status = "SOURCE_INCOMPLETE"),
    (b) => (b.latest.regions.KR.weekStatus = "INTRA_WEEK_PREVIEW"),
    (b) => (b.latest.regions.KR.freshness.status = "STALE"),
    (b) => (b.latest.regions.KR.digest = "c".repeat(64)),
    (b) => (b.publication.siteGeneratedAt = "2026-10-10T00:00:00Z"),
  ]) {
    const b = bundle(receipt("KR", 3));
    mutate(b);
    const d = A.decisionState(b, "KR", NOW);
    assert.equal(d.state, "UNAVAILABLE_OR_BLOCKED");
    const html = A.decisionMarkup(d, "KR", "b".repeat(40));
    assert.doesNotMatch(html, /15\.00%|55\.00%|class="holdings"/);
    assert.equal(A.watchlistMarkup(d).includes("watch-card"), false);
  }
});
test("malformed, duplicate tickers, mismatched weights and six stocks are invalid", () => {
  for (const mutate of [
    (r) => (r.stockCount = null),
    (r) => (r.benchmark = "QQQ"),
    (r) => (r.asOfDate = "2026-99-99"),
    (r) => (r.holdings[1].ticker = r.holdings[0].ticker),
    (r) => (r.holdings[0].weightPct = null),
    (r) => (r.weights.T0 = 0.2),
    (r) => (r.liveValidated = true),
  ]) {
    const r = receipt("KR", 2);
    mutate(r);
    assert.equal(A.validReceipt(r, "KR"), false);
  }
  assert.equal(A.validReceipt(receipt("KR", 6), "KR"), false);
});
test("market isolation never uses the other market receipt", () => {
  const b = bundle(receipt("US"));
  assert.equal(A.decisionState(b, "KR", NOW).state, "UNAVAILABLE_OR_BLOCKED");
  assert.equal(A.decisionState(b, "US", NOW).state, "BENCHMARK_ONLY");
});
test("observations expose no sizing, probabilities or candidate scores", () => {
  const d = A.decisionState(bundle(), "KR", NOW);
  d.receipt.watchlist = [
    {
      region: "KR",
      rank: 1,
      ticker: "A",
      name: "관찰 회사",
      weightPct: 80,
      probUp: 0.99,
      expectedReturnPct: 100,
      researchScore: 999,
    },
  ];
  const html = A.watchlistMarkup(d);
  assert.match(html, /매수 추천·보유 비중을 뜻하지 않습니다/);
  assert.doesNotMatch(html, /80%|99%|100%|999/);
});
test("all external strings are escaped in decisions, observations and reasons", () => {
  const b = bundle(receipt("KR", 1));
  b.receipts[0].holdings[0].name = "<img src=x onerror=alert(1)>";
  const d = A.decisionState(b, "KR", NOW);
  assert.doesNotMatch(A.decisionMarkup(d, "KR", "b".repeat(40)), /<img/);
  d.receipt.watchlist = [
    {
      region: "KR",
      name: "<script>1</script>",
      rank: 1,
      ticker: "<svg/onload=alert(1)>",
    },
  ];
  assert.doesNotMatch(A.watchlistMarkup(d), /<script>|<svg/);
  assert.equal(A.fmt(null), "—");
  assert.equal(A.fmt(0), "0.00");
});
test("digest lexical parser preserves decimal tokens and excludes only transport fields", async () => {
  const raw =
    '{"stockWeightPct":0.0,"weights":{"X":1.0},"digest":"skip","generatedAt":"skip","name":"한국 \\"회사\\""}';
  assert.equal(
    A.canonicalReceiptLine(raw),
    '{"name":"한국 \\"회사\\"","stockWeightPct":0.0,"weights":{"X":1.0}}',
  );
  assert.throws(() => A.canonicalReceiptLine('{"x":1,"x":2}'), /Duplicate/);
  const r = receipt();
  const line = JSON.stringify(r);
  r.digest = await A.sha256(A.canonicalReceiptLine(line));
  assert.equal((await A.parseReceipts(JSON.stringify(r))).length, 1);
  await assert.rejects(
    A.parseReceipts(JSON.stringify({ ...r, stockCount: 1 })),
    /다이제스트/,
  );
  await assert.rejects(
    A.parseReceipts(`${JSON.stringify(r)}\n${JSON.stringify(r)}`),
    /중복/,
  );
});
test("every original chart point is preserved and no invented initial point exists", () => {
  const s = A.studyData(read("weekly"), "KR", "weekly");
  const html = A.chartMarkup(s, { P0: true, P1: false });
  assert.equal((html.match(/data-chart-line=/g) || []).length, 1);
  const points = html.match(/points="([^"]+)"/)[1].split(" ");
  assert.equal(points.length, s.weeklyNav.P0.length);
  assert.doesNotMatch(html, /data-chart-line="P1"/);
});
test("v3 has six sections with sourced context and no combined Kelly recommendation", () => {
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
  const app = fs.readFileSync(path.join(root, "app.js"), "utf8");
  assert.equal((html.match(/<section /g) || []).length, 6);
  for (const id of ["decision", "market", "performance", "institutional", "watchlist", "evidence"])
    assert.ok(html.includes(`id="${id}"`));
  assert.doesNotMatch(
    app,
    /renderModelPortfolio|loadData\(|kellyFraction/,
  );
  assert.ok(app.includes("/git/ref/heads/signal-history"));
  assert.ok(app.includes("raw.githubusercontent.com"));
  assert.ok(app.includes("data/site-data.json"));
  assert.ok(app.includes("current-champion-decisions-v1"));
  assert.ok(app.includes("performanceOpened"));
});
module.exports = { receipt, bundle, clone };
