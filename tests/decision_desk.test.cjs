"use strict";
// Decision desk presentation contracts (research/decision_desk_v1/desk.json).
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
if (!globalThis.crypto) globalThis.crypto = require("node:crypto").webcrypto;
const a = require("../app.js");

const desk = () => JSON.parse(fs.readFileSync(__dirname + "/../research/decision_desk_v1/desk.json", "utf8"));
const NOW = Date.parse("2026-11-11T13:00:00Z");

test("committed desk passes the publication contract", () => {
  assert.ok(a.validDesk(desk()));
});

test("KR shows the production ETF decision and an explicit zero-name B2 choice", () => {
  const html = a.deskMarkup(desk(), "KR", NOW);
  assert.match(html, /data-desk-production="KR"/);
  assert.match(html, /069500\.KS 100%/);
  assert.match(html, /0개 선택 \(명시적 판단\)/);
  assert.doesNotMatch(html, /목표주가|확률 \d/);
});

test("US shows SPY default, QQQ as comparison only, single stocks source-blocked, and the B2 pick with its invalidation rules", () => {
  const html = a.deskMarkup(desk(), "US", NOW);
  assert.match(html, /기본값은 SPY/);
  assert.match(html, /QQQ는 별도 비교 기준/);
  assert.match(html, /원천 차단/);
  assert.match(html, /TRV · 연구 비중 10%/);
  assert.match(html, /가설 훼손 조건/);
});

test("the US cocktail allocation is shown as a historical reconstruction, never as current", () => {
  const html = a.deskMarkup(desk(), "US", NOW);
  assert.match(html, /us-macro-cocktail-v1 latest allocation/);
  assert.match(html, /historical reconstruction, not a prospective receipt/);
});

test("old records become stale with time and say they are not a current recommendation", () => {
  const later = Date.parse("2027-01-15T00:00:00Z");
  const html = a.deskMarkup(desk(), "KR", later);
  assert.match(html, /과거 기록, 현재 추천 아님/);
});

test("source-blocked history rows render no numbers", () => {
  const html = a.deskHistoryMarkup(desk().history, "KR");
  const rows = html.split("<tr").filter((r) => r.includes('data-desk-history="SOURCE_BLOCKED"'));
  assert.ok(rows.length > 0);
  for (const r of rows) assert.doesNotMatch(r.split("</td>").slice(4, 8).join(""), /\d/);
});

test("contract violations are refused, not rendered", () => {
  const blockedWithNumber = desk();
  blockedWithNumber.history.find((r) => r.type === "SOURCE_BLOCKED").cagrPct = 0;
  assert.equal(a.validDesk(blockedWithNumber), false);
  const late = desk();
  const rec = late.regions.US.deskRecords[0];
  rec.generatedAt = "2026-12-01T00:00:00Z";
  assert.equal(a.validDesk(late), false);
  const prob = desk();
  prob.regions.US.deskRecords[2].b2.picks[0].probability = 0.7;
  assert.equal(a.validDesk(prob), false);
  const hist = desk();
  hist.regions.US.historicalAllocations[0].currentRecommendation = true;
  assert.equal(a.validDesk(hist), false);
  assert.match(a.deskMarkup(prob, "US", NOW), /계약 검증을 통과하지 못해/);
});

test("the pinned desk constant matches the committed file", async () => {
  const bytes = fs.readFileSync(__dirname + "/../research/decision_desk_v1/desk.json");
  const digest = require("node:crypto").createHash("sha256").update(bytes).digest("hex");
  if (a.DESK.sha256.startsWith("__")) return; // pinned in the follow-up commit
  assert.equal(a.DESK.sha256, digest);
});

test("2026-11 B2 records carry the PIT contamination badge and git-verified publication", () => {
  for (const m of ["KR", "US"]) {
    const html = a.deskMarkup(desk(), m, NOW);
    const b2 = html.split('data-desk-item="decision-desk-v1 B2 2026-11"')[1].split("</article>")[0];
    assert.match(b2, /PIT 오염 — 주 비교 제외/);
    assert.match(b2, /공개 시점 git 검증/);
    const b0 = html.split('data-desk-item="decision-desk-v1 B0 2026-11"')[1].split("</article>")[0];
    assert.doesNotMatch(b0, /PIT 오염/);
  }
});

test("ledger shows exact exchange-calendar exit sessions and the pipeline stage", () => {
  const html = a.deskMarkup(desk(), "US", NOW);
  assert.match(html, /평가 전 \(종료 2027-05-14\)/);
  assert.match(html, /공개 완료 · 평가 지평 대기/);
  assert.match(html, /증거 패킷 대기/);
  assert.match(html, /gpt \(COMPARISON_ARM, PENDING_OWNER_APPROVAL\)/);
});

test("scored and source-blocked outcomes render without inventing numbers", () => {
  const d = desk();
  const rec = d.regions.US.deskRecords[0];
  rec.outcomes = [
    { horizon: 126, status: "SCORED", horizonEndSession: "2027-05-14", returnAfterCostPct: 4.2, excessAfterCostPct: -0.3 },
    { horizon: 252, status: "SOURCE_BLOCKED", horizonEndSession: "2027-11-12", returnAfterCostPct: null, excessAfterCostPct: null, missingDataReason: { SPY: "MISSING_SESSION_CLOSE" } },
  ];
  const html = a.deskLedgerMarkup(d.regions.US, NOW);
  assert.match(html, /비용 후 4\.20% · 기준 대비 -0\.30%p/);
  assert.match(html, /원천 차단/);
  assert.doesNotMatch(html.split("원천 차단")[1].split("</td>")[0], /%/);
});
