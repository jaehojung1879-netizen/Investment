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
  assert.match(html, /TRV · AI 실험 기록 비중 10%/);
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

test("the page follows the evidence-first order: production, eligibility, funnel, literature, AI, grades, performance, current vs past", () => {
  const html = a.deskMarkup(desk(), "KR", NOW);
  const heads = [...html.matchAll(/<h3 class="desk-h">(.)/g)].map((m) => m[1]);
  assert.deepEqual(heads.slice(0, 8), ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧"]);
  assert.doesNotMatch(html, /현재 검증된 production/);
  assert.match(html, /이 규칙이 기준 ETF를 이긴다는 검증은 아닙니다/);
});

test("eligibility and grades: nothing below E4 is decision-eligible and blocks are shown", () => {
  const d = desk();
  for (const m of ["KR", "US"]) {
    const html = a.deskMarkup(d, m, NOW);
    for (const row of html.split("<tr").filter((r) => r.includes("data-desk-eligibility=") && !r.includes("ETF_BASELINES")))
      assert.match(row, /<td>아니오<\/td>/);
    assert.match(html, /data-desk-grade-row="DESK_B2_2026_11"[\s\S]*?PIT 오염/);
  }
  assert.match(a.deskMarkup(d, "KR", NOW), /연구 종결\(거버넌스\)/);
});

test("the funnel shows every stage with drop reasons and the production comparison", () => {
  const d = desk();
  const html = a.deskMarkup(d, "KR", NOW);
  const stages = html.split("<tr").filter((r) => r.includes("data-desk-funnel="));
  assert.equal(stages.length, d.evidenceFirst.funnel.KR.stages.length);
  assert.match(html, /NO_PIT_FILING 121/);
  assert.match(html, /production 관찰 목록과 B1 상위 20% 비교/);
  assert.match(a.deskMarkup(d, "US", NOW), /today&#39;s members only/);
});

test("literature and the academic translation test are shown with their verdict", () => {
  const html = a.deskMarkup(desk(), "US", NOW);
  for (const id of ["FF5", "JT1993", "QMJ", "NM2013", "NM2015"]) assert.match(html, new RegExp(`data-desk-study="${id}"`));
  assert.match(html, /data-desk-verdict="WEAK_OR_ABSENT_AFTER_PUBLICATION"/);
  assert.match(html, /Bonferroni 유의 없음/);
  assert.match(html, /선정·추천 아님/);
});

test("AI dossiers: only screen-nominated names, held for research, with counter-arguments and sourced facts", () => {
  const d = desk();
  for (const m of ["KR", "US"]) {
    const html = a.deskMarkup(d, m, NOW);
    const cards = html.split('class="desk-item desk-dossier"').slice(1);
    assert.equal(cards.length, 5);
    for (const c of cards) {
      assert.match(c, /연구 보류 \(HOLD_FOR_RESEARCH\)/);
      assert.match(c, /반대 논거/);
      assert.match(c, /공개일/);
    }
  }
  assert.match(a.deskMarkup(d, "US", NOW), /four of five names/);
  assert.doesNotMatch(JSON.stringify(d.evidenceFirst.dossiers), /009150|삼성전기/);
});

test("legacy ledger paths are shown with their v3 names and the past is separated from the present", () => {
  const html = a.deskMarkup(desk(), "US", NOW);
  assert.match(html, /data-desk-v3="v3.B3"/);
  assert.match(html, /v3.B2<br><span class="digest">기존 B1/);
  const past = html.split("⑧ 현재 선택과 과거 선택")[1];
  assert.match(past, /과거 기록 \(2026-11 사전 기록, 원본 보존\)/);
  assert.match(past, /data-desk-item="decision-desk-v1 B2 2026-11"/);
  assert.doesNotMatch(html.split("②")[0], /data-desk-item="decision-desk-v1 B2/);
});

test("evidence-first contract violations are refused", () => {
  const digit = desk();
  digit.evidenceFirst.dossiers.dossiers[0].interpretation = ["ROE 65%"];
  assert.equal(a.validDesk(digit), false);
  const status = desk();
  status.evidenceFirst.dossiers.dossiers[0].status = "PROSPECTIVE_CANDIDATE";
  assert.equal(a.validDesk(status), false);
  const elig = desk();
  elig.evidenceFirst.grades.find((g) => g.id === "PROD_FOUR_FACTOR_KR").decisionEligible = true;
  assert.equal(a.validDesk(elig), false);
  const missing = desk();
  delete missing.evidenceFirst;
  assert.equal(a.validDesk(missing), false);
});

test("the top panel separates production, unverified virtual strategy, AI candidates and verified strategies", () => {
  for (const m of ["KR", "US"]) {
    const html = a.deskMarkup(desk(), m, NOW);
    const top = html.split('class="desk-h desk-four-h"')[1].split('<h3 class="desk-h">')[0];
    for (const k of ["production", "virtual", "ai", "verified"]) assert.match(top, new RegExp(`data-desk-four="${k}"`));
    const virt = top.split('data-desk-four="virtual"')[1].split("</article>")[0];
    assert.match(virt, /가상·미검증/);
    assert.match(virt, /매수 적격 아님/);
    const ai = top.split('data-desk-four="ai"')[1].split("</article>")[0];
    assert.match(ai, /연구 보류/);
    assert.match(ai, /매수 적격이 아님/);
    assert.match(top.split('data-desk-four="verified"')[1], /없음 \(0개\)/);
  }
});

test("data integrity: drop sides, mixed report periods, stale share counts and the post-inspection rule are shown", () => {
  const us = a.deskMarkup(desk(), "US", NOW);
  assert.match(us, /data-desk-side="OUR_PIPELINE"/);
  assert.match(us, /GOOGL\(마지막 공시 주식수 2020-06-30\)/);
  assert.match(us, /data-desk-invalid="bookToPrice"/);  // WDC's B/P is shown struck, not silently used
  assert.match(us, /data-desk-mixed/);
  const kr = a.deskMarkup(desk(), "KR", NOW);
  assert.match(kr, /402340\.KS: 영업이익률 27\.02 · 규칙이 없었다면 B1 5위로 심층검토 대상/);
  assert.match(kr, /data-desk-branch="FACTOR_REFERENCE"/);
  assert.match(kr, /data-desk-branch="B1"/);
});

test("profitability definitions say the ROE screen is not a reproduction of the academic strategies", () => {
  const html = a.deskMarkup(desk(), "US", NOW);
  for (const id of ["FF_OP", "NM_GPA", "B1_ROE"]) assert.match(html, new RegExp(`data-desk-definition="${id}"`));
  assert.match(html, /재현한 것이 아닙니다/);
});

test("the next cohort shows four comparable arms with recording blocked", () => {
  for (const m of ["KR", "US"]) {
    const html = a.deskMarkup(desk(), m, NOW);
    for (const k of ["ETF100", "B1_ROE", "PRODUCTION", "B1_PLUS_AI"]) assert.match(html, new RegExp(`data-desk-arm="${k}"`));
    assert.match(html, /data-desk-activation>ACTIVATION_BLOCKED/);
    assert.match(html, /data-desk-gate="CI_GREEN"/);
  }
  assert.match(a.deskMarkup(desk(), "US", NOW), /LRCX 제외\(INDUSTRY_CAP UNCLASSIFIED\)/);
});

test("primary-comparison exclusions are computed and shown on every past record", () => {
  const html = a.deskLedgerMarkup(desk().regions.US, NOW);
  assert.equal((html.match(/data-desk-primary="excluded"/g) || []).length, 3);
  assert.match(html, /마감 전 공개 관측 없음\(커밋 시각 주장만 있음\)/);
  const kr = a.deskLedgerMarkup(desk().regions.KR, NOW);
  assert.equal((kr.match(/data-desk-primary="eligible"/g) || []).length, 2);
});

test("track and activation contract violations are refused", () => {
  const fake = desk();
  fake.evidenceFirst.grades.find((g) => g.id === "ACADEMIC_PROFITABILITY_US").track = "A_VERIFIED_STRATEGY";
  assert.equal(a.validDesk(fake), false);
  const active = desk();
  active.evidenceFirst.prospective.activation = "ALLOWED";
  assert.equal(a.validDesk(active), false);
  const unlabelled = desk();
  delete unlabelled.evidenceFirst.prospective.dryRun.KR.arms.B1_ROE.recordLabel;
  assert.equal(a.validDesk(unlabelled), false);
});
