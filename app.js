"use strict";

// Presentation only: committed observations and append-only paper receipts.
// No selection engine, model, price download, or portfolio return calculation.
const REPO = "jaehojung1879-netizen/Investment";
const SOURCE_COMMIT = "82b1aac4b2441f076064830b6af776f1cda1b0fe";
const POLICY = "weekly-passive-first-v1";
const BENCHMARKS = {
  KR: ["069500.KS", "KODEX 200"],
  US: ["SPY", "SPDR S&P 500 ETF"],
};
const SOURCES = Object.freeze({
  weekly: {
    path: "docs/weekly-decision/weekly-passive-first-v1-weekly-replay-corrected-benchmark.json",
    sha256: "598161a74cafb459daefbcdd8404b6ca02804098d7f22a51b2531f077012bbc5",
  },
  anchors: {
    path: "docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json",
    sha256: "901b3aee7d3bc06eed3fd2bd14b07a0d4ca4da23745b861a877203c48772b8d2",
  },
  usd: {
    path: "docs/us-readiness/weekly-passive-first-v1-weekly-us-local-currency.json",
    sha256: "047236cfc4f5669727917c4a2adf3b0c2870faf9f1a6d08973821cd7c254022c",
  },
  qqq: {
    path: "docs/us-readiness/us-spy-qqq-comparison-v1.json",
    sha256: "18a2e1b1038c1d1c094c6b58b4fffb6e7be60310d093a6d35a938e34718eb98d",
  },
  institutionalCache: {
    path: "data/institutional_13f_cache.json",
    sha256: "746e03ce9c7270b94b56b89ddd37541c4722cc42075a39f809b9d20375d417ca",
  },
  npsCache: {
    path: "data/national_pension_cache.json",
    sha256: "445e6e42f9484a3abf35aab749085210b39cd92a7067a3d7a0635ca0a426e728",
  },
});
const RAW = (sha, path) =>
  `https://raw.githubusercontent.com/${REPO}/${sha}/${path}`;
const LINK = (path, sha = SOURCE_COMMIT) =>
  `https://github.com/${REPO}/blob/${sha}/${path}`;
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const finite = (v) => typeof v === "number" && Number.isFinite(v);
const fmt = (v, digits = 2, suffix = "") =>
  finite(v) ? `${v.toFixed(digits)}${suffix}` : "—";
const signed = (v, digits = 3, suffix = "%p") =>
  finite(v) ? `${v > 0 ? "+" : ""}${fmt(v, digits, suffix)}` : "—";
const pct = (v, digits = 1) => fmt(v, digits, "%");
const day = (s) => {
  if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const stamp = Date.parse(`${s}T00:00:00Z`);
  return (
    Number.isFinite(stamp) && new Date(stamp).toISOString().slice(0, 10) === s
  );
};
const time = (s) => (typeof s === "string" ? Date.parse(s) : NaN);
const MAX_AGE_MS = 3 * 86400000; // Existing daily publication freshness bound.
const FINAL_STATUSES = new Set([
  "PASSIVE_NO_DEFENSIBLE_EDGE",
  "NO_CANDIDATES",
  "STOCKS_SELECTED",
]);
const REASONS = {
  ORDERING_NOT_ESTABLISHED:
    "종목 순위가 수익을 정렬했다는 통계적 근거가 확인되지 않았습니다.",
  NO_CANDIDATES: "규칙에 사용할 리서치 후보가 없었습니다.",
  NO_POSITIVE_NET_ADVANTAGE: "비용을 넘는 순우위를 확인한 후보가 없었습니다.",
};
const DIGEST_EXCLUDED = new Set([
  "generatedAt",
  "digest",
  "previousWeekChange",
  "freshness",
  "publishedFrom",
  "laterRecomputationDigest",
]);

// Python json canonical bytes preserve 100.0 versus 100. JSON.parse alone loses
// that distinction. Parse the ORIGINAL line, sort object keys and retain number
// tokens exactly as the Python publisher wrote them. Never digest JS re-encoding.
function canonicalReceiptLine(raw, excluded = DIGEST_EXCLUDED) {
  JSON.parse(raw); // Reject invalid JSON before the lexical canonicalizer.
  let i = 0;
  const ws = () => {
    while (/\s/.test(raw[i] || "") && i < raw.length) i++;
  };
  const string = () => {
    const start = i++;
    while (i < raw.length) {
      if (raw[i] === "\\") {
        i += 2;
        continue;
      }
      if (raw[i++] === '"') return raw.slice(start, i);
    }
    throw new Error("Incomplete JSON string");
  };
  const value = (root = false) => {
    ws();
    if (raw[i] === '"') return string();
    if (raw[i] === "{") {
      i++;
      ws();
      const pairs = [];
      const seen = new Set();
      while (raw[i] !== "}") {
        const token = string();
        const key = JSON.parse(token);
        if (seen.has(key)) throw new Error("Duplicate JSON key");
        seen.add(key);
        ws();
        i++;
        const v = value();
        if (!root || !excluded.has(key))
          pairs.push([key, `${token}:${v}`]);
        ws();
        if (raw[i] !== ",") break;
        i++;
        ws();
      }
      i++;
      return `{${pairs
        .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
        .map((p) => p[1])
        .join(",")}}`;
    }
    if (raw[i] === "[") {
      i++;
      ws();
      const items = [];
      while (raw[i] !== "]") {
        items.push(value());
        ws();
        if (raw[i] !== ",") break;
        i++;
      }
      i++;
      return `[${items.join(",")}]`;
    }
    const start = i;
    while (i < raw.length && !/[\s,\]}]/.test(raw[i])) i++;
    return raw.slice(start, i);
  };
  return value(true);
}
async function sha256(bytes) {
  const raw =
    typeof bytes === "string" ? new TextEncoder().encode(bytes) : bytes;
  return Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", raw)),
    (b) => b.toString(16).padStart(2, "0"),
  ).join("");
}
async function parseReceipts(text) {
  const out = [];
  const ids = new Map();
  for (const line of text.split(/\r?\n/).filter((x) => x.trim())) {
    const r = JSON.parse(line);
    if (
      !/^[a-f0-9]{64}$/.test(r.digest || "") ||
      (await sha256(canonicalReceiptLine(line))) !== r.digest
    )
      throw new Error("영수증 다이제스트 불일치");
    if (ids.has(r.receiptId)) throw new Error("중복 영수증 식별자");
    ids.set(r.receiptId, r.digest);
    out.push(r);
  }
  return out;
}
function validReceipt(r, market) {
  if (
    !r ||
    r.schema !== "WEEKLY_DECISION_RECEIPT_V1" ||
    r.region !== market ||
    r.policyVersion !== POLICY ||
    r.weekStatus !== "FINAL_WEEKLY" ||
    r.liveValidated !== false ||
    !day(r.asOfDate)
  )
    return false;
  if (
    r.receiptId !== `${POLICY}|${market}|${r.asOfDate}` ||
    !/^[a-f0-9]{64}$/.test(r.digest || "") ||
    !FINAL_STATUSES.has(r.status) ||
    r.benchmark !== BENCHMARKS[market][0]
  )
    return false;
  if (
    r.evidenceStatus?.verifiedLive !== "NOT_VERIFIED" ||
    !Array.isArray(r.holdings) ||
    !r.weights ||
    typeof r.weights !== "object" ||
    Array.isArray(r.weights)
  )
    return false;
  const holdings = r.holdings;
  const weights = Object.entries(r.weights);
  if (
    holdings.length > 5 ||
    r.stockCount !== holdings.length ||
    !weights.length ||
    weights.some(([, w]) => !finite(w) || w < 0 || w > 1)
  )
    return false;
  if (Math.abs(weights.reduce((s, [, w]) => s + w, 0) - 1) > 1e-6) return false;
  if (
    !finite(r.stockWeightPct) ||
    !finite(r.benchmarkWeightPct) ||
    Math.abs(r.stockWeightPct + r.benchmarkWeightPct - 100) > 1e-5
  )
    return false;
  if (
    !finite(r.weights[r.benchmark]) ||
    Math.abs(r.weights[r.benchmark] * 100 - r.benchmarkWeightPct) > 1e-5
  )
    return false;
  const ticks = holdings.map((h) => h.ticker);
  if (new Set(ticks).size !== ticks.length || ticks.includes(r.benchmark))
    return false;
  if (weights.filter(([t]) => t !== r.benchmark).length !== ticks.length)
    return false;
  if (
    holdings.some(
      (h) =>
        typeof h.ticker !== "string" ||
        !Object.hasOwn(r.weights, h.ticker) ||
        !finite(h.weightPct) ||
        h.weightPct <= 0 ||
        Math.abs(r.weights[h.ticker] * 100 - h.weightPct) > 1e-5,
    )
  )
    return false;
  if (
    Math.abs(holdings.reduce((s, h) => s + h.weightPct, 0) - r.stockWeightPct) >
    1e-5
  )
    return false;
  return holdings.length
    ? r.status === "STOCKS_SELECTED"
    : r.status !== "STOCKS_SELECTED" &&
        r.benchmarkWeightPct === 100 &&
        r.stockWeightPct === 0;
}
function decisionState(bundle, market, now = Date.now()) {
  const blocked = (reason, last = null) => ({
    state: "UNAVAILABLE_OR_BLOCKED",
    reason,
    last,
  });
  if (!bundle)
    return blocked(
      "게시된 판단을 확인하지 못했습니다. 현재 비중을 표시하지 않습니다.",
    );
  const { latest, publication, receipts } = bundle;
  const finals = receipts
    .filter((r) => validReceipt(r, market))
    .sort((a, b) => b.asOfDate.localeCompare(a.asOfDate));
  const last = finals[0] || null;
  if (
    latest?.schema !== "WEEKLY_DECISION_ARTIFACT_V1" ||
    publication?.schema !== "WEEKLY_PUBLICATION_STATUS_V1"
  )
    return blocked("게시 자료의 형식을 확인할 수 없습니다.", last);
  if (
    latest.blocked !== false ||
    latest.unsafeReason ||
    latest.liveValidated !== false
  )
    return blocked("게시 자료가 안전 기준에서 차단되었습니다.", last);
  if (
    publication.status !== "PUBLISHED" ||
    publication.siteGeneratedAt !== latest.generatedAt ||
    !finite(time(publication.attemptedAt)) ||
    time(publication.attemptedAt) < time(latest.generatedAt)
  )
    return blocked(
      "최신 게시가 거부되었거나 게시 상태가 일치하지 않습니다.",
      last,
    );
  const age = now - time(latest.generatedAt);
  if (!finite(age) || age > MAX_AGE_MS || age < -600000)
    return blocked(
      "게시 자료가 지연되었거나 생성 시각을 확인할 수 없습니다.",
      last,
    );
  const b = latest.regions?.[market];
  if (!b || !FINAL_STATUSES.has(b.status) || b.weekStatus !== "FINAL_WEEKLY")
    return blocked(
      "현재 확정 주간 판단이 없습니다. 미리보기와 과거 기록을 현재 비중으로 사용하지 않습니다.",
      last,
    );
  if (
    b.freshness?.status !== "FRESH" ||
    b.freshness.observedSession !== b.asOfDate ||
    b.freshness.expectedSession !== b.asOfDate
  )
    return blocked("지역 시세가 현재 게시 기준을 충족하지 못했습니다.", last);
  const r = finals.find(
    (x) => x.receiptId === b.receiptId && x.digest === b.digest,
  );
  if (!r || r.asOfDate > new Date(now).toISOString().slice(0, 10))
    return blocked("게시된 판단과 원장 영수증이 일치하지 않습니다.", last);
  return {
    state: r.stockCount === 0 ? "BENCHMARK_ONLY" : "STOCKS_PLUS_BENCHMARK",
    receipt: r,
    freshness: b.freshness,
    last,
  };
}

function studyData(report, market, kind) {
  if (
    !report ||
    report.benchmarkBasis !== "phase-c-corrected" ||
    report.liveValidated !== false ||
    report.promotionEligible !== false ||
    report.evidenceClass !== "POST_OUTCOME_EXPOSED_EXPLORATORY_PORTFOLIO_REPLAY"
  )
    return null;
  const cadence =
    kind === "weekly"
      ? "WEEKLY_SIGNAL_NEXT_COMMON_SESSION_EXECUTION"
      : "21_SESSION_ANCHORS_NOT_WEEKLY";
  if (
    report.calendar?.cadence !== cadence ||
    (market === "US" && kind !== "weekly")
  )
    return null;
  const b = report.regions?.[market];
  if (
    !b ||
    b.baseCurrency !== "KRW" ||
    b.benchmark !== BENCHMARKS[market][0] ||
    !Array.isArray(b.decisions)
  )
    return null;
  if (
    market === "KR" &&
    b.benchmarkDefinition !== "PHASE_C_RECONCILED_GROSS_ETF_TOTAL_RETURN"
  )
    return null;
  const keys = kind === "weekly" ? ["P0", "P1"] : ["P0", "P1", "C1", "C2"];
  const p0 = b.paths?.P0;
  if (!p0 || !day(p0.startDate) || !day(p0.endDate)) return null;
  for (const k of keys) {
    const p = b.paths?.[k];
    const nav = b.weeklyNav?.[k];
    if (
      p?.available !== true ||
      p.blocks !== b.decisions.length ||
      p.startDate !== p0.startDate ||
      p.endDate !== p0.endDate ||
      !finite(p.cagrPct) ||
      !Array.isArray(nav) ||
      nav.length < 2
    )
      return null;
    if (
      nav.some(
        (v, i) =>
          !Array.isArray(v) ||
          !day(v[0]) ||
          !finite(v[1]) ||
          v[1] <= 0 ||
          v[0] < p0.startDate ||
          v[0] > p0.endDate ||
          (i && nav[i - 1][0] >= v[0]),
      )
    )
      return null;
  }
  if (
    b.decisions.some(
      (d) =>
        !day(d.date) ||
        !day(d.signalDate) ||
        d.signalDate >= d.date ||
        !Array.isArray(d.holdings) ||
        d.stockCount !== d.holdings.length ||
        d.stockCount > 5 ||
        d.stockCount < 0,
    )
  )
    return null;
  if (
    market === "US" &&
    (b.decisions.some((d) => d.stockCount !== 0) ||
      JSON.stringify(b.weeklyNav.P0) !== JSON.stringify(b.weeklyNav.P1))
  )
    return null;
  return {
    ...b,
    kind,
    keys,
    source: SOURCES[kind].path,
    evidenceClass: report.evidenceClass,
    candidatePool: report.candidatePool,
    stockDecisions: b.decisions.filter((d) => d.stockCount > 0),
    period: `${p0.startDate} — ${p0.endDate}`,
  };
}

const LABELS = {
  P0: ["지수 단순 보유", "Passive ETF"],
  P1: ["규칙 + 잔여 지수", "Weekly stock selection + residual ETF"],
  C1: ["CHAMPION + 잔여 현금", "Legacy stock selection + residual cash"],
  C2: ["CHAMPION + 잔여 지수", "Legacy stock selection + residual ETF"],
};
const COLORS = { P0: "#8a9d96", P1: "#166d5e", C1: "#ad7756", C2: "#455a8c" };
const link = (path, label, sha = SOURCE_COMMIT) =>
  `<a class="source-link" href="${LINK(path, sha)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
const unavailableMarkup = (d) =>
  `<div class="unavailable" data-portfolio-state="UNAVAILABLE_OR_BLOCKED"><span class="pill warn">현재 판단 확인 불가</span><h2>확정 비중을 표시할 수 없습니다</h2><p>${esc(d.reason)}</p>${d.last ? `<small>마지막 확정 기록: ${esc(d.last.asOfDate)} · 과거 영수증으로만 보존</small>` : ""}</div>`;
function decisionMarkup(d, market, commit) {
  if (d.state === "UNAVAILABLE_OR_BLOCKED") return unavailableMarkup(d);
  const r = d.receipt;
  const zero = d.state === "BENCHMARK_ONLY";
  const reason =
    REASONS[r.noTradeReason] ||
    r.statusKo ||
    "자세한 판단 근거는 원문 영수증을 확인하세요.";
  return `<article class="decision-card" data-portfolio-state="${d.state}">
    <div class="card-meta"><span class="pill">공식 주간 가상 판단</span><span>${esc(r.asOfDate)} · ${market === "KR" ? "KRX" : "NYSE/Nasdaq"}</span></div>
    <h2>${zero ? `${esc(r.benchmarkName || BENCHMARKS[market][1])} ${pct(r.benchmarkWeightPct, 0)}` : `개별 종목 ${r.stockCount}개 + ${esc(r.benchmark)}`}</h2>
    <p class="reason">${zero ? esc(reason) : "영수증에 확정된 종목과 비중입니다. 남은 자금은 지역 지수 ETF에 배분했습니다."}</p>
    <div class="allocation-bar" aria-hidden="true"><span class="stocks" style="width:${r.stockWeightPct}%"></span><span class="benchmark" style="width:${r.benchmarkWeightPct}%"></span></div>
    <dl class="allocation-metrics"><div><dt>개별 종목</dt><dd>${r.stockCount}<small>개</small></dd></div><div><dt>종목 비중</dt><dd>${pct(r.stockWeightPct, 0)}</dd></div><div><dt>잔여 지수</dt><dd>${pct(r.benchmarkWeightPct, 0)}</dd></div></dl>
    ${zero ? "" : `<div class="holdings">${r.holdings.map((h) => `<div class="holding"><span>${esc(h.name || h.ticker)}<small>${esc(h.ticker)}</small></span><b>${pct(h.weightPct, 2)}</b></div>`).join("")}<div class="holding"><span>${esc(r.benchmarkName)}<small>${esc(r.benchmark)} · 잔여 지수</small></span><b>${pct(r.benchmarkWeightPct, 2)}</b></div></div>`}
    <div class="decision-foot"><span>시세 ${esc(d.freshness.observedSession)} · 게시 기준 충족</span><span>전향 기록 · 성과 관측 전</span>${link("ledger/weekly-decisions/receipts.jsonl", "원문 영수증", commit)}</div>
    <details><summary>판단 근거와 영수증</summary><p>${esc(r.statusKo || reason)}</p>${!zero ? r.holdings.map((h) => `<p><b>${esc(h.name || h.ticker)}</b> · ${esc(h.reasonKo || "추가 설명 미기록")}</p>`).join("") : `<p>미편입 사유: ${esc(r.noTradeReason || "미기록")}</p>`}
      <dl class="method-grid"><div><dt>규칙·주기</dt><dd>${esc(r.policyVersion)} · FINAL_WEEKLY</dd></div><div><dt>기준지수·통화</dt><dd>${esc(r.benchmark)} · ${market === "KR" ? "KRW" : "USD"}</dd></div><div><dt>전환 비용 문턱(기록값)</dt><dd>${pct(r.costs?.switchCostPct, 3)} · 126거래일 보정</dd></div><div><dt>증거</dt><dd>탐색적 정책 · 실전 검증 없음</dd></div><div><dt>영수증 ID</dt><dd>${esc(r.receiptId)}</dd></div><div><dt>SHA-256 · 원문 확인</dt><dd class="digest">${esc(r.digest)}</dd></div></dl></details></article>`;
}
function answerMarkup(study, market) {
  if (!study)
    return `<aside class="answer-card"><div><p class="eyebrow">종목 선택의 근거</p><h3>검증된 우위는 아직 확인되지 않았습니다</h3><p>과거 자료 조회 상태는 아래에서 확인하세요.</p></div><a href="#performance">연구 기록 확인 ↓</a></aside>`;
  const gap = study.paths.P1.excessCagrPp;
  return `<aside class="answer-card"><div><p class="eyebrow">지수 대신 종목을 고를 근거는?</p><h3>${market === "KR" ? "과거 주간 규칙은 지수에 뒤졌습니다" : "미국 규칙은 종목을 선택한 적이 없습니다"}</h3><p>종목 선택 ${study.stockDecisions.length} / ${study.decisions.length}회 · 과거 탐색</p></div><div><div class="answer-number ${gap < 0 ? "negative" : ""}">${signed(gap)}<small> / 년</small></div><p>${market === "KR" ? "P1 − P0 CAGR · 같은 KRW·주간 평가" : "개별 종목 선택 실적 없음 · SPY와 동일"}</p></div><a href="#performance">비교 근거 보기 ↓</a></aside>`;
}
function strategyCards(s) {
  return `<div class="metric-cards ${s.keys.length > 2 ? "four" : ""}">${s.keys
    .map((k) => {
      const p = s.paths[k];
      const title = k === "P0" ? `${s.benchmark} 단순 보유` : LABELS[k][0];
      const type =
        k === "P1" && s.kind === "anchors"
          ? "21-session stock selection + residual ETF"
          : LABELS[k][1];
      return `<article class="strategy-card" data-strategy="${k}"><div class="strategy-head"><span>${esc(title)}</span><span class="strategy-id">${k}</span></div><div class="strategy-type">${esc(type)}</div><div class="strategy-return">${pct(p.cagrPct, 3)}<small>CAGR · KRW · 비용 후</small></div><dl class="mini-metrics"><div><dt>최대 낙폭</dt><dd>${pct(p.maxDrawdownPct, 2)}</dd></div><div><dt>연 변동성</dt><dd>${pct(p.annualizedVolatilityPct, 2)}</dd></div><div><dt>연 비용 영향</dt><dd>${fmt(p.annualizedCostDragPct, 3, "%p")}</dd></div><div><dt>누적 거래 비용*</dt><dd>${pct(p.totalCostPctOfNav, 3)}</dd></div></dl></article>`;
    })
    .join("")}</div>`;
}
function chartMarkup(s, visible) {
  const keys = s.keys.filter((k) => visible[k]);
  if (!keys.length) return '<p class="empty">비교할 전략을 선택하세요.</p>';
  const all = keys.flatMap((k) => s.weeklyNav[k]);
  const W = 900,
    H = 300,
    L = 48,
    R = 18,
    T = 18,
    B = 35;
  const t0 = time(s.paths.P0.startDate),
    t1 = time(s.paths.P0.endDate);
  const low = Math.min(1, ...all.map((p) => p[1]));
  const high = Math.max(...all.map((p) => p[1])) * 1.06;
  const x = (date) => L + ((time(date) - t0) / (t1 - t0)) * (W - L - R);
  const y = (v) => T + ((high - v) / (high - low)) * (H - T - B);
  const grids = Array.from(
    { length: 5 },
    (_, i) => low + ((high - low) * i) / 4,
  )
    .map(
      (v) =>
        `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="chart-grid"/><text x="${L - 10}" y="${y(v) + 4}" text-anchor="end" class="chart-label">${v.toFixed(1)}×</text>`,
    )
    .join("");
  const years = [
    s.paths.P0.startDate,
    "2016-01-01",
    "2019-01-01",
    "2022-01-01",
    s.paths.P0.endDate,
  ].filter((d) => time(d) >= t0 && time(d) <= t1);
  const lines = keys
    .map(
      (k) =>
        `<polyline data-chart-line="${k}" points="${s.weeklyNav[k].map((p) => `${x(p[0]).toFixed(2)},${y(p[1]).toFixed(2)}`).join(" ")}" fill="none" stroke="${COLORS[k]}" stroke-width="2.4" ${k === "P1" ? 'stroke-dasharray="6 4"' : ""}><title>${k} ${esc(LABELS[k][0])}</title></polyline>`,
    )
    .join("");
  return `<svg class="wealth-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(s.benchmark)} 대비 ${s.kind === "weekly" ? "주간" : "21세션"} 전략의 기록된 누적 자산 경로 · KRW">${grids}${lines}${years.map((d, i) => `<text x="${x(d)}" y="${H - 8}" text-anchor="${i === 0 ? "start" : i === years.length - 1 ? "end" : "middle"}" class="chart-label">${d.slice(0, 4)}</text>`).join("")}</svg>`;
}
function timelineMarkup(s, market) {
  const n = s.decisions.length;
  const selected = s.stockDecisions;
  return `<div class="timeline"><h3>언제 실제로 종목을 골랐나</h3><p class="timeline-summary">${n}회 중 종목 선택 ${selected.length}회 · 지수만 보유 ${n - selected.length}회 (${pct(((n - selected.length) / n) * 100, 2)})</p>${market === "US" ? '<p class="study-reading">개별 종목 선택 실적 없음 — 미국 주간 규칙은 과거 재현에서 SPY만 보유</p>' : `<div class="timeline-weeks">${selected.map((d) => `<button class="week-button" type="button" data-week="${esc(d.date)}" aria-expanded="false" aria-controls="weekDetail">${esc(d.date)}<small>종목 ${d.stockCount}개 · 기록 보기</small></button>`).join("")}</div><div id="weekDetail" class="week-detail" hidden></div>`}<p class="chart-note">${s.kind === "weekly" ? "주간" : "21세션"} 과거 재현의 실행일입니다. 전향 영수증 이력과 별개입니다.</p></div>`;
}
function yearsMarkup(s) {
  const years = Object.keys(s.paths.P0.calendarYearReturnPct || {});
  if (!years.length) return "";
  return `<details><summary>연도별 수익률 비교</summary><div class="table-scroll" role="region" aria-label="연간 수익률" tabindex="0"><table><caption>KRW · 비용 후 · 첫해/마지막 해는 관측 구간만</caption><thead><tr><th>연도</th>${s.keys.map((k) => `<th scope="col">${k}</th>`).join("")}</tr></thead><tbody>${years.map((y) => `<tr><th scope="row">${esc(y)}</th>${s.keys.map((k) => `<td>${pct(s.paths[k].calendarYearReturnPct?.[y], 2)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
}
function methodMarkup(s, market) {
  return `<details><summary>방법론 · 비용 · 출처</summary><dl class="method-grid"><div><dt>기간·주기·판단 수</dt><dd>${s.period} · ${s.kind === "weekly" ? "주간 신호 / 다음 공통 세션 실행" : "21거래일 앵커 실행"} · ${s.decisions.length}회</dd></div><div><dt>평가 통화·기준지수</dt><dd>KRW · ${esc(s.benchmark)}${market === "US" ? " · 환율 포함" : " · 공식 분배금 단일 재투자"}</dd></div><div><dt>유니버스</dt><dd>replay-v16 당시 리서치 후보 풀 · 가격 팩터 대용(PRICE_SLEEVES_ONLY_AUDIT_PROXY). 현재 후보 목록을 과거로 소급하지 않음</dd></div><div><dt>비용</dt><dd>각 거래에 당시 수수료·스프레드·매도세 적용. KR 국내 주식형 ETF 거래세 면제. ETF 보수는 시세에 내재. 투자자 배당세 전</dd></div><div><dt>누적 비용* 정의</dt><dd>각 거래의 비용/NAV 비율을 합한 원문 totalCostPctOfNav. 초기자본 대비 총 지급액이 아님. 연 비용 영향은 gross − net CAGR</dd></div><div><dt>종목 선택 빈도</dt><dd>P1 ${s.stockDecisions.length}/${s.decisions.length}회${s.kind === "anchors" ? " · C1/C2는 원문 zeroNameBlockSharePct 기준 모두 종목 보유" : ""}</dd></div><div><dt>증거 분류</dt><dd>과거 탐색 · 결과 노출 · 독립 검증 미완료. 전향 가상 기록과 합산하지 않음</dd></div><div><dt>주요 한계</dt><dd>${market === "KR" ? "종목 가격은 6종목 표본 감사만 통과. 기대초과 보정 원장은 구형 지수 기준. 완전한 네 팩터 생산 전략 재현이 아님" : "생존편향·퇴출 종목 가격 결손. SPY 외부 가격/분배 대조 미완료. 개별 종목 전략 경로는 표시하지 않음"}</dd></div></dl><p>${link(s.source, "성과 지표·기록 NAV 원문")} · ${link("docs/weekly-decision/weekly-passive-first-v1.json", "규칙과 비용")} · ${link("docs/weekly-decision/kodex200-benchmark-audit.md", "KODEX 200 원천 감사")}</p><p class="digest">${esc(s.evidenceClass)} · 자료 commit ${SOURCE_COMMIT} · SHA-256 ${SOURCES[s.kind].sha256}</p></details>`;
}
function usdMarkup(local) {
  if (
    local?.basis !== "USD" ||
    local.cadence !== "WEEKLY_SIGNAL_NEXT_COMMON_SESSION_EXECUTION" ||
    local.replaySource !==
      "docs/weekly-decision/weekly-passive-first-v1-weekly-replay.json" ||
    !finite(local.paths?.P0?.cagrPct) ||
    JSON.stringify(local.paths.P0) !== JSON.stringify(local.paths.P1)
  )
    return "";
  return `<div class="usd-context"><div><span class="eyebrow">SPY · USD CAGR</span><br><b>${pct(local.paths.P0.cagrPct, 3)}</b></div><p>같은 주간 문맥의 달러 요약입니다. 아래 원화 경로의 수익률 차이는 환율 효과이며 종목 선택의 우위가 아닙니다.<br>${link(SOURCES.usd.path, "USD 요약 원문")}</p></div>`;
}
function performanceMarkup(s, market, visible, usd) {
  if (!s)
    return '<p class="empty">원본 연구 자료를 확인하지 못했습니다. 수익률과 그래프를 표시하지 않습니다.</p>';
  const weekly = s.kind === "weekly";
  return `<div class="study-basis" data-study-basis="${s.kind}"><span>${s.period} · ${s.decisions.length}회 · ${weekly ? "주간 신호" : "21거래일 앵커"}</span><span>KRW · 비용 후 · ${market === "KR" ? "KODEX 200 교정 기준" : "SPY 원화 평가 / 데이터 부분 확보"}</span></div>${market === "US" ? `<p class="notice">개별 종목 선택 실적 없음 — 미국 주간 규칙은 과거 재현에서 SPY만 보유. 생존편향·퇴출 시세 결손 때문에 개별 종목 전략 성과는 표시하지 않습니다.</p>${usdMarkup(usd)}` : ""}${strategyCards(s)}
    <div class="chart-card"><div class="chart-head"><h3>기록된 누적 자산 경로</h3><span>시작자본 1 · 주말 관측값 · KRW</span></div><div class="line-toggles" role="group" aria-label="차트 전략 표시">${s.keys.map((k) => `<label><input type="checkbox" data-line="${k}" ${visible[k] ? "checked" : ""}/><i class="line-dot" style="--line-color:${COLORS[k]}" aria-hidden="true"></i>${k} ${esc(LABELS[k][0])}</label>`).join("")}</div><div id="chartPlot">${chartMarkup(s, visible)}</div><p class="chart-note">커밋된 NAV만 표시합니다. 선은 기록값을 연결하며 새로운 수익률·초기점·개별 주 기여도를 생성하지 않습니다.</p></div>
    ${market === "KR" && weekly ? `<p class="study-reading">P1 − P0 CAGR <b class="negative">${signed(s.paths.P1.excessCagrPp)} / 년</b>. ${s.decisions.length - s.stockDecisions.length}회는 지수만 보유했습니다. 대부분의 성과는 종목 선택보다 지수 보유에서 나왔습니다.</p>` : ""}
    ${market === "KR" && !weekly ? `<div class="exploration-callout"><p class="eyebrow">C2 − P0 · 과거 관측</p><div class="answer-number">${signed(s.paths.C2.excessCagrPp)}<small> / 년</small></div><h3>과거 지수 초과수익 관측 · 사후 탐색 · 독립 검증 미완료</h3><p>동일한 종목을 선택했지만, 남은 자금을 현금으로 보유하는지 지수에 투자하는지에 따라 결과가 달라졌습니다. C2는 결과를 본 뒤 만든 조합입니다. 검증된 알파나 생산 전략 승격의 근거가 아닙니다.</p></div>` : ""}
    ${timelineMarkup(s, market)}${yearsMarkup(s)}${methodMarkup(s, market)}`;
}
function watchlistMarkup(d) {
  if (!d.receipt)
    return '<p class="empty">현재 확정 영수증의 관찰 후보를 확인할 수 없습니다.</p>';
  const rows = Array.isArray(d.receipt.watchlist)
    ? d.receipt.watchlist
        .slice(0, 5)
        .filter((w) => w.region === d.receipt.region)
    : [];
  if (!rows.length)
    return '<p class="empty">이 영수증에는 관찰 후보가 기록되지 않았습니다.</p>';
  return `<p class="watch-note">${esc(d.receipt.asOfDate)} 기준 관찰 후보입니다. 리서치 순위를 설명하며 매수 추천·보유 비중을 뜻하지 않습니다.</p><div class="watch-grid">${rows.map((w) => `<article class="watch-card"><span class="watch-rank">관찰 ${esc(w.rank)}</span><h3>${esc(w.name || w.ticker)}</h3><span class="ticker">${esc(w.ticker)} · ${esc(w.sectorKo || w.sector || "미분류")}</span><p>${esc(w.thesisKo || "추가 설명 미기록")}</p><details><summary>관찰 근거</summary><p>강점: ${esc((w.strengthsKo || []).join(" · ") || "미기록")}</p><p>주의: ${esc((w.weaknessesKo || []).join(" · ") || "추가 경고 미기록")}</p><p>편입 여부는 위 확정 판단에서 확인하세요. ${esc((w.exclusionReasonsKo || []).join(" · "))}</p><p>재무 기준: ${esc(w.valuationProfitability?.basisKo || "미기록")}</p></details></article>`).join("")}</div>`;
}

// No local preview override: a generated site-data/weekly-decision file cannot
// impersonate the immutable ledger. Browser tests intercept the actual URLs.
async function getBytes(url) {
  const response = await fetch(url, {
    cache: "no-store",
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return new Uint8Array(await response.arrayBuffer());
}
const decode = (bytes) =>
  new TextDecoder("utf-8", { fatal: true }).decode(bytes);
async function loadSource(key) {
  const source = SOURCES[key];
  const bytes = await getBytes(RAW(SOURCE_COMMIT, source.path));
  if ((await sha256(bytes)) !== source.sha256)
    throw new Error("원본 연구 자료 해시 불일치");
  return JSON.parse(decode(bytes));
}
async function loadPublication() {
  const ref = JSON.parse(
    decode(
      await getBytes(
        `https://api.github.com/repos/${REPO}/git/ref/heads/signal-history`,
      ),
    ),
  );
  const commit = ref.object?.sha;
  if (!/^[a-f0-9]{40}$/.test(commit || "") || ref.object.type !== "commit")
    throw new Error("원장 commit 확인 불가");
  const path = "ledger/weekly-decisions/";
  const files = await Promise.all([
    getBytes(RAW(commit, `${path}latest.json`)),
    getBytes(RAW(commit, `${path}publication-status.json`)),
    getBytes(RAW(commit, `${path}receipts.jsonl`)),
  ]);
  const receipts = await parseReceipts(decode(files[2]));
  return {
    commit,
    latest: JSON.parse(decode(files[0])),
    publication: JSON.parse(decode(files[1])),
    receipts,
  };
}

// Selectively restored v1 chart/indicator/disclosure logic. Each view consumes
// dated source observations; policies execute only in Python on the publisher.
const CHAMPION_VERSION = "current-champion-decisions-v1";
const CHAMPION_PATH = `ledger/research-strategies/${CHAMPION_VERSION}/`;
const CHAMPION_EVIDENCE = "PROSPECTIVE_RESEARCH_ONLY_CURRENT_CHAMPION_VARIANT";
const RESEARCH_EXCLUDED = new Set(["digest", "previousObservationChange"]);
const number = (v, digits = 0) => finite(v) ? v.toLocaleString("ko-KR", { maximumFractionDigits: digits }) : "—";
function safeSourceLink(url, label, hosts = []) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password ||
        (hosts.length && !hosts.includes(parsed.hostname))) return `<span>${esc(label)} · URL 확인 불가</span>`;
    return `<a class="source-link" href="${esc(parsed.href)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
  } catch (_) { return `<span>${esc(label)} · 원문 주소 없음</span>`; }
}
function sourceMode(site) {
  if (site?.seed || site?.synthetic || site?.meta?.syntheticData) return "SYNTHETIC_OR_SEED";
  return site?.provenance?.dataMode || site?.dataMode || "UNVERIFIED";
}
function siteIsCurrent(site, now = Date.now()) {
  const age = now - time(site?.generatedAt);
  return sourceMode(site) === "live" && !site.seed && !site.synthetic && !site.stale &&
    finite(age) && age >= -600000 && age <= MAX_AGE_MS;
}
async function parseChampionReceipts(text) {
  const records = [], ids = new Set();
  for (const line of text.split(/\r?\n/).filter(s => s.trim())) {
    const r = JSON.parse(line);
    if (r.schema !== "CURRENT_CHAMPION_RECEIPT_V1" || r.version !== CHAMPION_VERSION ||
        r.digest !== await sha256(new TextEncoder().encode(canonicalReceiptLine(line, RESEARCH_EXCLUDED))) ||
        ids.has(r.receiptId)) throw new Error("연구 영수증 식별자/다이제스트 확인 실패");
    ids.add(r.receiptId); records.push(r);
  }
  return records;
}
function validChampionPair(r, market) {
  if (!r || r.version !== CHAMPION_VERSION || r.schema !== "CURRENT_CHAMPION_RECEIPT_V1" ||
      r.region !== market || !day(r.asOfDate) || r.liveValidated !== false ||
      r.evidenceClass !== CHAMPION_EVIDENCE || r.receiptId !== `${CHAMPION_VERSION}|${market}|${r.asOfDate}` ||
      r.cadence !== "CURRENT_SESSION_OBSERVATION_NOT_21_SESSION_EXECUTION_SEQUENCE" ||
      ["regionalSha256","sourceArtifactSha256","configurationSha256","engineSha256"].some(k=>
        !/^[a-f0-9]{64}$/.test(r.inputs?.[k] || ""))) return false;
  const a = r.decisions?.C1, b = r.decisions?.C2;
  if (!a || !b || a.strategy !== "C1" || b.strategy !== "C2" || a.residualAsset !== "CASH" ||
      b.residualAsset !== BENCHMARKS[market][0] || !Array.isArray(a.holdings) ||
      JSON.stringify(a.holdings) !== JSON.stringify(b.holdings) ||
      JSON.stringify(a.stockWeights) !== JSON.stringify(b.stockWeights)) return false;
  for (const d of [a, b]) {
    if (!["STOCKS_SELECTED", "NO_ELIGIBLE_STOCKS"].includes(d.status) || d.stockCount !== d.holdings.length ||
        d.stockCount > 5 || !d.stockWeights || !d.weights || !finite(d.residualWeightPct) || !finite(d.stockWeightPct) ||
        Math.abs(d.stockWeightPct + d.residualWeightPct - 100) > 1e-5 || d.totalWeightPct !== 100) return false;
    const held = new Set(d.holdings.map(h => h.ticker));
    if (held.size !== d.stockCount || Object.keys(d.stockWeights).length !== held.size ||
        Object.keys(d.weights).length !== held.size + 1 || held.has(d.residualAsset)) return false;
    if (!Object.hasOwn(d.weights,d.residualAsset) || (d.stockCount>0 ? d.status!=="STOCKS_SELECTED" : d.status!=="NO_ELIGIBLE_STOCKS")) return false;
    if (Object.values(d.weights).some(w => !finite(w) || w < 0 || w > 1) ||
        Math.abs(Object.values(d.weights).reduce((s,w)=>s+w,0)-1) > 1e-6 ||
        Math.abs(d.weights[d.residualAsset]*100-d.residualWeightPct) > 1e-5 ||
        d.holdings.some(h => !finite(h.weightPct) || h.weightPct <= 0 || !finite(d.stockWeights[h.ticker]) ||
          Math.abs(d.weights[h.ticker]-d.stockWeights[h.ticker]) > 1e-10 ||
          Math.abs(d.stockWeights[h.ticker]*100-h.weightPct)>1e-5)) return false;
  }
  return a.residualWeightPct === b.residualWeightPct;
}
function championState(bundle, market, site, now = Date.now()) {
  const blocked = reason => ({state:"BLOCKED", reason});
  if (!bundle) return blocked("C1/C2 연구 영수증이 아직 게시되지 않았거나 조회할 수 없습니다.");
  if (!siteIsCurrent(site, now) || site.recommendationsBlocked || site.longTerm?.weightsWithheld !== false)
    return blocked("현재 production 입력의 신선도·안전 상태를 확인할 수 없습니다.");
  const {latest, publication, receipts} = bundle;
  if (latest?.schema !== "CURRENT_CHAMPION_ARTIFACT_V1" || latest.version !== CHAMPION_VERSION ||
      latest.liveValidated !== false || latest.evidenceClass !== CHAMPION_EVIDENCE ||
      publication?.schema !== "CURRENT_CHAMPION_PUBLICATION_V1" || publication.status !== "PUBLISHED" ||
      publication.generatedAt !== latest.generatedAt || !siteIsCurrent({...latest,dataMode:"live"}, now))
    return blocked("연구 게시 상태·생성 시각·버전을 확인할 수 없습니다.");
  const b = latest.regions?.[market];
  if (b?.status !== "READY") return blocked(`연구 계산 차단: ${(b?.reasonCodes || ["REGIONAL_RECORD_MISSING"]).join(" · ")}`);
  const symbol = market === "KR" ? "^KS11" : "^GSPC";
  const tape = site.indices?.find(x=>x.symbol===symbol);
  if (!tape || tape.freshnessStatus !== "CURRENT" || b.sourceObservedDate !== tape.asOf ||
      b.freshness?.status !== "FRESH" || b.freshness.expectedSession !== b.asOfDate ||
      b.freshness.observedSession !== b.asOfDate) return blocked("현재 지역 시장 세션과 연구 영수증이 일치하지 않습니다.");
  const candidates=site.longTerm?.regions?.[market]?.picks;
  if (!Array.isArray(candidates) || !candidates.length || candidates.some(c=>
    !c || c.region!==market || !c.ticker || !finite(c.alphaPercentile) || !finite(c.evidenceCoverage) ||
    !finite(c.risk?.downsideVolPct) || c.risk.downsideVolPct<=0 || site.details?.[c.ticker]?.asOf!==tape.asOf))
    return blocked("현재 지역 후보 풀·하방 위험·시세 기준일이 불완전합니다.");
  const r = receipts.find(r=>r.receiptId===b.receiptId && r.digest===b.digest);
  if (!validChampionPair(r, market) || r.asOfDate !== b.asOfDate ||
      r.asOfDate > new Date(now).toISOString().slice(0,10) || time(r.generatedAt)>now+600000)
    return blocked("C1/C2 원장·종목 비중·잔여 자산의 일치 검증에 실패했습니다.");
  return {state:"READY", receipt:r, freshness:b.freshness, commit:bundle.commit};
}
function championMarkup(state, strategy, market) {
  const description = strategy === "C1" ? "CHAMPION · 잔여 현금" : "C1의 동일 종목·비중 · 잔여 지수";
  if (state.state !== "READY") return `<article class="decision-card strategy-current blocked" data-current-strategy="${strategy}" data-current-state="BLOCKED"><div class="card-meta"><b>${strategy} · ${description}</b><span class="pill warn">UNAVAILABLE</span></div><h2>현재 비중 확인 불가</h2><p class="reason">${esc(state.reason)}</p><p class="notice">현재 종목·비중을 생성하거나 과거 포트폴리오로 대체하지 않습니다.</p><details><summary>계산·게시 조건</summary><p>지역별 최신 완료 세션, production 장기 후보·하방 위험·거시 위험예산, 별도 연구 영수증의 SHA-256과 C1/C2 동일성을 확인합니다.</p><p>원래 CHAMPION 함수로 계산하는 전향적 연구 변형이며, 과거 21세션 투자 순서의 검증된 재현은 아닙니다.</p></details></article>`;
  const r=state.receipt, d=r.decisions[strategy];
  return `<article class="decision-card strategy-current" data-current-strategy="${strategy}" data-current-state="READY"><div class="card-meta"><b>${strategy} · ${description}</b><span class="pill">연구 전용 PAPER</span></div><h2>개별 종목 ${d.stockCount}개</h2><p class="reason">신호 ${esc(r.asOfDate)} · 현재 관측 연구 변형<br>${strategy === "C2" ? "C1과 종목·종목 비중이 정확히 같습니다." : "원래 conviction·하방 변동성 배분과 현금/집중도 제약을 적용했습니다."}</p><dl class="allocation-metrics"><div><dt>종목 비중</dt><dd>${pct(d.stockWeightPct,1)}</dd></div><div><dt>${strategy === "C1" ? "잔여 현금" : esc(BENCHMARKS[market][0])}</dt><dd>${pct(d.residualWeightPct,1)}</dd></div><div><dt>총 비중</dt><dd>100<small>%</small></dd></div></dl><div class="holdings" aria-label="CURRENT SELECTED HOLDINGS">${d.holdings.map(h=>`<div class="holding"><span>${esc(h.name)}<small>${esc(h.ticker)} · ${esc(h.sector)}</small></span><b>${pct(h.weightPct,2)}</b></div>`).join("")}<div class="holding residual"><span>${strategy === "C1" ? "현금" : esc(BENCHMARKS[market][1])}<small>${esc(d.residualAsset)} · 잔여 자산</small></span><b>${pct(d.residualWeightPct,2)}</b></div></div><details><summary>선정 이유·점수·제외·출처</summary><p>${esc(d.scoreMeaningKo)}</p>${d.holdings.map(h=>`<p><b>${esc(h.name)}</b> · conviction ${fmt(h.convictionScore,4)} · 알파 백분위 ${fmt(h.alphaPercentile,0)} · 하방 변동성 ${pct(h.downsideVolPct)} · 근거 ${pct(h.evidenceCoverage*100)}<br>${esc(h.reasonKo)}</p>`).join("")}<p>현금 하한 ${pct(d.appliedMinCashPct)} · 원래 지역당 최대 ${esc(d.selection?.maxNamesPerRegion)}종목 · 섹터당 ${esc(d.selection?.maxNamesPerSector)}종목</p><p>제외 ${d.selection?.ranking?.filter(x=>!x.selected).map(x=>`${x.ticker}: ${x.exclusionCodes.join(", ")}`).map(esc).join(" · ") || "기록된 제외 없음"}</p><p>${esc(r.limitations?.join(" "))}</p>${r.previousObservationChange ? `<p>이전 관측 ${esc(r.previousObservationChange.priorAsOfDate)} · 추가 ${esc(r.previousObservationChange.added.join(", ") || "없음")} · 제외 ${esc(r.previousObservationChange.removed.join(", ") || "없음")}</p>` : "<p>이전 관측 차이: 최초 기록 또는 미기록</p>"}<p class="digest">입력 ${esc(r.inputs.regionalSha256)}<br>원천 artifact ${esc(r.inputs.sourceArtifactSha256)}<br>영수증 ${esc(r.digest)}<br>${esc(r.evidenceClass)}</p>${link(CHAMPION_PATH+"receipts.jsonl","별도 연구 영수증",state.commit)}</details></article>`;
}
function observations(points) {
  if (!Array.isArray(points)) return [];
  return points.filter(p=>p && day(p.date) && finite(p.value)).sort((a,b)=>a.date.localeCompare(b.date));
}
function cachedInstitutions(cache) {
  if (!cache?.managers) return null;
  return {managers:Object.values(cache.managers).map(m=>({...m,
    status:["AVAILABLE","CACHED_OFFICIAL"].includes(m.status) && day(m.reportDate) && day(m.filingDate) &&
      finite(m.totalValueUsd) && finite(m.positionCount) ? "CACHED_OFFICIAL" : "UNAVAILABLE",
    sourceMode:"CACHED_SEC",cacheFetchedAt:m.cacheFetchedAt || m.retrievedAt || cache.fetchedAt})),fetchedAt:cache.fetchedAt,
    sourceIdentity:SOURCES.institutionalCache};
}
function cachedNps(cache) {
  return cache?.asOf ? {...cache,status:["AVAILABLE","CACHED_OFFICIAL"].includes(cache.status) &&
    finite(cache.totalFundTrillionKrw) ? "CACHED_OFFICIAL" : "UNAVAILABLE",
    sourceMode:"CACHED_NPS",sourceIdentity:SOURCES.npsCache} : null;
}
function qqqMarkup(report) {
  if (report?.evidenceClass !== "DESCRIPTIVE_ETF_COMPARISON_NOT_ALPHA" || report.officialUsBenchmark !== "SPY" ||
      report.growthAlternative !== "QQQ" || !finite(report.headline?.usd?.QQQ?.cagrPct)) return "";
  const h=report.headline;
  return `<details class="etf-context"><summary>SPY / QQQ · 합병된 연구 소스의 수동 ETF 대안 비교</summary><p>공식 기준과 현재 잔여 ETF는 SPY입니다. 아래는 별도 원천 빈티지의 기술적 ETF 비교이며 종목 선택 알파·미래 비중·지속 우위를 뜻하지 않습니다. 외부 총수익 대조와 SPY 분배금 단일 반영 검증의 한계가 남습니다.</p><div class="metric-cards">${["SPY","QQQ"].map(k=>`<article class="strategy-card"><b>${k} · USD 원천 기록</b><div class="strategy-return">${pct(h.usd[k].cagrPct,3)}<small>기록된 CAGR</small></div><p>최대 낙폭 ${pct(h.usd[k].maxDrawdownPct,3)}</p></article>`).join("")}</div>${trendSvg([ {label:"SPY USD",points:(h.weekly || []).map(r=>({date:r.date,value:r.spyNavUsd}))},{label:"QQQ USD",points:(h.weekly || []).map(r=>({date:r.date,value:r.qqqNavUsd}))}],"기록된 SPY/QQQ 수동 ETF NAV")}<p class="chart-note">과거 원천에 기록된 주간 NAV만 표시합니다. 이 비교를 P1/C1/C2의 현재 정책에 적용하지 않습니다.</p>${link(SOURCES.qqq.path,"병합된 비교 원본")}<p class="digest">비교 SHA-256 ${esc(SOURCES.qqq.sha256)} · 입력 snapshot ${esc(report.snapshot?.sha256)}</p></details>`;
}
function rangePoints(points, range, macro = false) {
  const rows=observations(points);
  if (!rows.length) return rows;
  const months=macro ? {"1Y":12,"3Y":36,"5Y":60,"10Y":120}[range] : {"1M":1,"3M":3,"6M":6,"1Y":12}[range];
  if (!months) return rows;
  const end=new Date(rows.at(-1).date+"T00:00:00Z"), cut=new Date(end);
  cut.setUTCDate(1); cut.setUTCMonth(cut.getUTCMonth()-months);
  cut.setUTCDate(Math.min(end.getUTCDate(),new Date(Date.UTC(cut.getUTCFullYear(),cut.getUTCMonth()+1,0)).getUTCDate()));
  return rows.filter(p=>time(p.date+"T00:00:00Z")>=cut.getTime());
}
function trendSvg(lines, label, mini = false) {
  const clean=lines.map(l=>({...l,points:observations(l.points)})).filter(l=>l.points.length);
  if (!clean.length) return '<p class="chart-note">시계열 미보고 · 관측값을 생성하지 않습니다.</p>';
  const all=clean.flatMap(l=>l.points), times=all.map(p=>time(p.date+"T00:00:00Z")), values=all.map(p=>p.value);
  const width=mini?360:820, height=mini?100:300, left=mini?4:64, right=12, bottom=mini?4:34, top=12;
  const lo=Math.min(...values), hi=Math.max(...values), span=hi-lo || Math.max(Math.abs(lo)*.1,1);
  const min=lo-span*.1,max=hi+span*.1,t0=Math.min(...times),t1=Math.max(...times);
  const x=p=>left+(time(p.date+"T00:00:00Z")-t0)/(t1-t0||1)*(width-left-right);
  const y=p=>top+(max-p.value)/(max-min)*(height-top-bottom);
  const grid=mini?"" : [0,.5,1].map(f=>`<line class="chart-grid" x1="${left}" x2="${width-right}" y1="${top+f*(height-top-bottom)}" y2="${top+f*(height-top-bottom)}"/><text class="chart-label" x="${left-8}" y="${top+f*(height-top-bottom)+4}" text-anchor="end">${number(max-f*(max-min),2)}</text>`).join("");
  return `<svg class="observation-chart ${mini?"mini":""}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}" data-observations="${all.length}">${grid}${clean.map((l,i)=>`<polyline fill="none" stroke="${["#166d5e","#ad7756"][i%2]}" stroke-width="${mini?2:2.2}" vector-effect="non-scaling-stroke" points="${l.points.map(p=>`${x(p).toFixed(2)},${y(p).toFixed(2)}`).join(" ")}"><title>${esc(l.label)} · 원천 관측 ${l.points.length}개</title></polyline>${l.points.length===1?`<circle cx="${x(l.points[0])}" cy="${y(l.points[0])}" r="3"/>`:""}`).join("")}${mini?"":`<text class="chart-label" x="${left}" y="${height-7}">${esc(all.reduce((a,b)=>a.date<b.date?a:b).date)}</text><text class="chart-label" x="${width-right}" y="${height-7}" text-anchor="end">${esc(all.reduce((a,b)=>a.date>b.date?a:b).date)}</text>`}</svg>`;
}
function unit(x) {
  return x.unit || x.currency || (x.symbol === "KRW=X" ? "KRW/USD" : x.symbol?.startsWith("^") ? "지수 수준" : "원천 수준 · 단위 미기록");
}
function marketMarkup(site, market) {
  if (!site) return '<p class="empty">시장 원천을 불러오지 못했습니다. 현재 지표를 대체하지 않습니다.</p>';
  if (sourceMode(site)!=="live") return '<p class="empty">합성·시드·미검증 시장 자료는 실제 관측값으로 표시하지 않습니다.</p>';
  const rows=(site.indices || []).filter(x=>x.region===market || ["FX","CMDTY","CRYPTO"].includes(x.region));
  if (!rows.length) return '<p class="empty">이 시장의 지수·자산 관측이 미보고입니다.</p>';
  return `<div class="context-grid">${rows.map(x=>`<button type="button" class="asset-card" data-context-kind="index" data-context-id="${esc(x.symbol)}"><div class="asset-head"><b>${esc(x.name || x.symbol)}</b><small>${esc(x.symbol)}</small></div><div class="asset-quote">${number(x.last,x.digits ?? 2)}<small>${esc(unit(x))}</small></div><div class="asset-change">1일 ${signed(x.chg1dPct,2,"%")} · 3M 관측</div>${trendSvg([{label:x.name,points:rangePoints(x.history,"3M")}],x.name+" 원천 관측",true)}<div class="source-caption">${esc(x.asOf || "기준일 미기록")} · ${esc(x.freshnessStatus || "UNKNOWN")}<br>${esc(x.source || "원천 미기록")}</div><span class="open-detail">1M · 3M · 6M · 1Y 상세 →</span></button>`).join("")}</div><p class="chart-note">표시는 원천의 마지막 관측값입니다. 지연/누락된 현재 가격을 앞선 가격으로 채우지 않습니다. FX·금·가상자산은 시장 공통 참고 자산입니다.</p>`;
}
function macroIndicators(site) {
  const axes=site?.macroRegime?.axes || {};
  return Object.entries(axes).flatMap(([key,a])=>(a.indicators || []).map(i=>({...i,axisName:a.ko || key})));
}
function macroMarkup(site, market) {
  if (!site) return '<p class="empty">거시 원천을 확인할 수 없습니다.</p>';
  if (sourceMode(site)!=="live") return '<p class="empty">합성·시드·미검증 거시 시계열은 실제 관측값으로 표시하지 않습니다.</p>';
  const regime=site.macroRegime || {}, budget=regime.riskBudget?.equityRangePct;
  const groups=Object.entries(regime.axes || {});
  return `<div class="regime-card"><div><span class="pill">시장 연구 맥락</span><h3>${esc(regime.regime || "국면 미보고")}</h3><p>신뢰도 ${pct(finite(regime.confidence)?regime.confidence*100:null)} · 위험자산 예산 ${Array.isArray(budget)?budget.map(v=>pct(v,0)).join(" — "):"미보고"}</p></div><p>거시 국면은 검증된 종목 선택 알파가 아닙니다. 발표 시차와 개정 이력의 PIT/빈티지 한계가 남습니다.</p></div>${groups.map(([key,a])=>`<details class="macro-group" ${key==="growth" || key==="inflation"?"open":""}><summary>${esc(a.ko || key)} · ${esc(a.directionKo || a.direction || "관측 맥락")}</summary><div class="context-grid macro-grid">${(a.indicators || []).map(i=>`<button type="button" class="indicator-card" data-context-kind="macro" data-context-id="${esc(i.name)}"><div class="asset-head"><b>${esc(i.displayNameKo || i.name)}</b><span class="pill ${i.stale?"warn":""}">${i.stale?"STALE":"원천 관측"}</span></div><div class="asset-quote">${fmt(i.transformedValue,2)}<small>${esc(i.valueUnit || "단위 미기록")}</small></div><p>${esc(i.transformationKo || i.transformation || "변환 미기록")}</p>${trendSvg([{label:i.historyLabelKo || i.name,points:rangePoints(i.history,"3M")}],i.name+" 거시 관측",true)}<div class="source-caption">관측 ${esc(i.observationDate || "미기록")} · 발표시차 ${finite(i.releaseLagBdays)?i.releaseLagBdays:"미기록"}영업일<br>${esc(i.contextOnly?"판정 보조 · 점수 미반영":i.signalSummaryKo || "")}</div><span class="open-detail">1Y · 3Y · 5Y · 10Y 상세 →</span></button>`).join("") || '<p class="empty">지표 미보고</p>'}</div></details>`).join("")}<details class="macro-raw"><summary>${market} 원지표 값과 출처</summary><div class="raw-indicators">${(site.macro?.[market]?.indicators || []).map(r=>`<div><b>${esc(r[0])}</b><span>${esc(r[1])}</span><small>${esc(r[2])}</small></div>`).join("") || "원지표 미보고"}</div></details><p class="chart-note">세부 차트는 원천에 제공된 변환 시계열을 표시합니다. 빈 시계열은 현재값 카드로만 남기며, 관측 빈도는 원천에 기록된 경우에만 표기합니다.</p>`;
}
function chartDetail(x, kind, range) {
  const macro=kind==="macro", points=rangePoints(x.history,range,macro), trend=rangePoints(x.trendHistory,range,macro);
  const ranges=macro?["1Y","3Y","5Y","10Y"]:["1M","3M","6M","1Y"];
  return `<p class="eyebrow">${macro?"MACRO OBSERVATION":"MARKET OBSERVATION"} · ${esc(x.name || x.symbol)}</p><h2 id="contextDialogTitle">${esc(x.displayNameKo || x.name || x.symbol)} · ${range}</h2><p>${macro?esc(x.transformationKo || x.transformation || "변환 미기록"):esc(unit(x))} · 기준 ${esc(macro?x.observationDate:x.asOf)}</p><div class="range-controls" role="group" aria-label="차트 표시 기간">${ranges.map(r=>`<button type="button" data-context-range="${r}" aria-pressed="${r===range}">${r}</button>`).join("")}</div><div class="detail-chart">${trendSvg([{label:x.historyLabelKo || x.name,points},...(trend.length?[{label:x.trendLabelKo || "원천 추세",points:trend}]:[])],(x.displayNameKo || x.name)+" "+range)}</div><p class="chart-note">실제 제공 구간 ${esc(points[0]?.date || "미보고")} — ${esc(points.at(-1)?.date || "미보고")} · 원천 관측 ${points.length}개. 요청 기간보다 원천이 짧으면 가용 관측만 표시합니다.</p>${macro?`<p>${esc(x.guide?.meaningKo || "")}</p><p>${esc(x.guide?.readKo || x.signalSummaryKo || "")}</p><p class="notice">${esc(x.guide?.cautionKo || "개정된 과거 시계열은 최초 발표 빈티지와 다를 수 있습니다.")}</p><dl class="method-grid"><div><dt>단위·변환</dt><dd>${esc(x.valueUnit || "미기록")} · ${esc(x.transformation || "미기록")}</dd></div><div><dt>관측 빈도</dt><dd>${esc(x.frequency || "원천 미기록 · 제공 날짜를 그대로 표시")}</dd></div><div><dt>발표시차</dt><dd>${finite(x.releaseLagBdays)?x.releaseLagBdays:"미보고"}영업일</dd></div></dl>`:`<p>1일 변화 ${signed(x.chg1dPct,2,"%")} · ${esc(x.freshnessStatus || "UNKNOWN")} · 영업일 지연 ${esc(x.freshnessBdays ?? "미기록")}</p>`}<p>${safeSourceLink(macro?x.source:x.sourceUrl,"원자료",["fred.stlouisfed.org","ecos.bok.or.kr","www.bok.or.kr","finance.yahoo.com","stooq.com"])}${!macro?` · ${esc(x.source || "원천 미기록")}`:""}</p><details><summary>표시된 실제 관측값</summary><div class="table-scroll" tabindex="0" role="region" aria-label="시계열 관측 표"><table><thead><tr><th>관측일</th><th>${esc(macro?x.valueUnit || "원천 단위":unit(x))}</th></tr></thead><tbody>${points.map(p=>`<tr><th>${esc(p.date)}</th><td>${number(p.value,4)}</td></tr>`).join("")}</tbody></table></div></details>`;
}
function institutionalMarkup(block) {
  const managers=block?.managers || [];
  if (!managers.length) return '<p class="empty">기관별 공식 공시 자료가 미보고입니다. 기관 보유를 추정하지 않습니다.</p>';
  return `<p class="source-caption">표시 가능한 기관 ${managers.filter(m=>["AVAILABLE","CACHED_OFFICIAL"].includes(m.status)).length}/${managers.length} · 원천 확인 ${esc(block.fetchedAt || "미기록")}</p><div class="manager-grid">${managers.map(m=>{const available=["AVAILABLE","CACHED_OFFICIAL"].includes(m.status);return `<article class="manager-card"><div class="asset-head"><b>${esc(m.name)}</b><span class="pill ${m.status==="CACHED_OFFICIAL" || !available?"warn":""}">${esc(m.status || "UNAVAILABLE")}</span></div><small>${esc(m.managerKo)} · SEC CIK ${esc(m.cik || "미기록")}</small><p>공시 기준 ${esc(m.reportDate || "미보고")}<br>실제 제출 ${esc(m.filingDate || "미보고")}</p>${available?`<dl class="mini-metrics"><div><dt>보고대상 13F 평가액</dt><dd>USD ${number(m.totalValueUsd)}</dd></div><div><dt>공시 포지션 수</dt><dd>${number(m.positionCount)}</dd></div></dl><div class="manager-top">${(m.topHoldings || []).slice(0,3).map(h=>`<p>${esc(h.issuer)} <b>${pct(h.portfolioWeightPct,2)}</b></p>`).join("")}</div><button class="detail-button" type="button" data-context-kind="manager" data-context-id="${esc(m.id)}">보유·주식 수 변화 상세 →</button>`:`<p>${esc(m.noteKo || "공식 원문과 검증된 캐시를 확인할 수 없습니다.")}</p>`}<p class="source-caption">${m.status==="CACHED_OFFICIAL"?"CACHED_OFFICIAL · 캐시 수집 ":"원문 수집 "}${esc(m.cacheFetchedAt || m.retrievedAt || "원천 미기록")}</p></article>`;}).join("")}</div>`;
}
function managerDetail(m) {
  const changes=m.changes || {};
  return `<p class="eyebrow">SEC FORM 13F · ${esc(m.status)}</p><h2 id="contextDialogTitle">${esc(m.name)} 공시 보유</h2><p>SEC CIK ${esc(m.cik)} · 분기말 ${esc(m.reportDate)} · 실제 제출 ${esc(m.filingDate)}<br>${m.status==="CACHED_OFFICIAL"?"공식 캐시 수집":"원문 수집"} ${esc(m.cacheFetchedAt || m.retrievedAt || "미기록")}</p><p class="notice">지연 분기 공시이며 오늘의 보유내역이 아닙니다. 공시 평가액 증가는 매수 증거가 아니며, 주식 수 변화에도 실제 거래일은 알려져 있지 않습니다. 현금·숏·비보고 자산은 제외됩니다.</p><p>보고대상 총 평가액 USD ${number(m.totalValueUsd)} · ${number(m.positionCount)}포지션 · 표시는 저장된 상위 ${(m.topHoldings || []).length}개입니다.</p><div class="disclosed-holdings">${(m.topHoldings || []).map(h=>`<div class="holding"><span>${esc(h.issuer)}<small>${esc(h.titleClass)} · CUSIP ${esc(h.cusip)} · ${number(h.shares)} ${esc(h.shareType || "SH")}</small></span><div><b>${pct(h.portfolioWeightPct,2)}</b><small>USD ${number(h.valueUsd)}</small></div></div>`).join("")}</div><h3 class="macro-heading">직전 분기 ${esc(m.previousReportDate || "미기록")} 대비 주식 수 변화</h3>${Object.entries({new:"새로 공시된 보유",increased:"주식 수 증가",decreased:"주식 수 감소",exited:"보고 목록에서 제외"}).map(([key,label])=>`<details class="change-group"><summary>${label} · ${(changes[key] || []).length}건</summary>${(changes[key] || []).map(c=>`<div class="holding"><span>${esc(c.issuer)}<small>이전 ${number(c.previousShares)} → 현재 ${number(c.currentShares)}주</small></span><b>${signed(c.shareChangePct,1,"%")}</b></div>`).join("") || '<p>비교 가능한 공시 변화 미보고</p>'}</details>`).join("")}<p>${safeSourceLink(m.filingUrl,"원본 SEC filing",["www.sec.gov","sec.gov"])}</p>`;
}
function npsMarkup(nps) {
  if (!nps || !["AVAILABLE","CACHED_OFFICIAL"].includes(nps.status)) return '<p class="empty">국민연금 전체 기금 자산배분은 미보고입니다. NPS 13F로 대신하지 않습니다.</p>';
  return `<article class="nps-card"><div class="asset-head"><h3>국민연금 전체 기금 자산배분</h3><span class="pill ${nps.status==="CACHED_OFFICIAL"?"warn":""}">${esc(nps.status)}</span></div><p>${esc(nps.scopeKo)} · 기준 ${esc(nps.asOfLabelKo || nps.asOf)}<br>총 기금 ${number(nps.totalFundTrillionKrw,1)}조 원 · ${nps.provisional?"잠정치":"원천 공시값"}</p><div class="nps-allocations">${(nps.allocations || []).map(a=>`<div class="nps-allocation"><span>${esc(a.labelKo)}<small>${number(a.valueTrillionKrw,1)}조 원</small></span><div class="nps-track"><i style="width:${finite(a.weightPct)?Math.max(0,Math.min(100,a.weightPct)):0}%"></i></div><b>${pct(a.weightPct,1)}</b></div>`).join("")}</div><p class="notice">NPS의 미국 13F 보고대상 증권과 전체 연금 기금의 자산배분은 범위·기준일이 다릅니다. 원천의 반올림 비중을 재정규화하지 않습니다.</p><p class="source-caption">수집 ${esc(nps.retrievedAt || "미기록")} · ${esc(nps.sourceMode || "미기록")}</p><p>${safeSourceLink(nps.sourceUrl,"국민연금 공식 원문",["fund.nps.or.kr","www.nps.or.kr"])}</p></article>`;
}
async function loadResearchPublication(commit) {
  // A new namespace can legitimately be absent before the first ledger run.
  // Inspect metadata first, avoiding three predictable missing-file requests.
  const tree=JSON.parse(decode(await getBytes(`https://api.github.com/repos/jaehojung1879-netizen/Investment/git/trees/${commit}?recursive=1`)));
  if (tree.truncated || !["latest.json","publication-status.json","receipts.jsonl"].every(n=>
    tree.tree?.some(x=>x.type==="blob" && x.path===CHAMPION_PATH+n)))
    throw new Error("현재 C1/C2 연구 원장 미게시");
  const files=await Promise.all(["latest.json","publication-status.json","receipts.jsonl"].map(n=>getBytes(RAW(commit,CHAMPION_PATH+n))));
  return {commit,latest:JSON.parse(decode(files[0])),publication:JSON.parse(decode(files[1])),receipts:await parseChampionReceipts(decode(files[2]))};
}

function startTerminal() {
  const $ = (s) => document.querySelector(s);
  let market = "KR";
  try {
    if (sessionStorage.getItem("investment-market") === "US") market = "US";
  } catch (_) {
    /* Storage can be disabled. */
  }
  let kind = "weekly";
  let bundle = null;
  let researchBundle = null;
  let site = null;
  let siteLoading = true;
  let activeContext = null;
  let performanceOpened = false;
  let loading = true;
  let publicationError = false;
  let inFlight = false;
  const reports = {};
  const sourceLoading = new Set();
  const failures = {};
  const visible = { P0: true, P1: true, C1: true, C2: true };
  const currentStudy = () => studyData(reports[kind], market, kind);
  function renderEvidence(d) {
    const rows = (bundle?.receipts || [])
      .filter((r) => validReceipt(r, market))
      .sort((a, b) => a.asOfDate.localeCompare(b.asOfDate));
    $("#evidencePanel").innerHTML =
      `<div class="evidence-grid"><article class="evidence-box"><h3>전향 영수증과 과거 탐색을 구분합니다</h3><p>${rows.length ? `확정 영수증 ${rows.length}건 · 첫 기록 ${esc(rows[0].asOfDate)}. 이후 성과를 평가할 기간이 아직 부족합니다.` : "현재 조회에서 확정 영수증을 확인하지 못했습니다."} 2013–2026 시뮬레이션은 그 전향 실적이 아닙니다.</p><details><summary>확정 영수증 이력·출처</summary>${rows.map((r) => `<p>${esc(r.asOfDate)} · 종목 ${r.stockCount}개 · ${esc(r.status)}<br><span class="digest">${esc(r.digest)}</span></p>`).join("")}${bundle ? `<p>${link("ledger/weekly-decisions/receipts.jsonl", "추가 전용 원장", bundle.commit)}</p><p class="digest">조회 commit ${esc(bundle.commit)} · 숫자 토큰 보존 SHA-256 확인</p>` : "<p>네트워크나 게시 자료가 복구되면 다시 확인합니다.</p>"}</details></article>
      <article class="evidence-box"><h3>${market === "KR" ? "교정 지수와 종목 가격의 한계" : "미국 데이터의 범위"}</h3><p>${market === "KR" ? "KODEX 200 분배금 이중 반영 수치는 헤드라인에서 제외했습니다. 교정 지수는 공식 분배금 대조를 거쳤지만, 종목 시세는 6종목 표본 감사 범위입니다." : "SPY가 공식 기준지수입니다. 퇴출 종목 가격과 생존편향 때문에 과거 미국 종목선택 성과를 검증된 결과로 표시하지 않습니다."}</p><details><summary>원천 감사·연구 문서</summary><p>${link("docs/weekly-passive-first-v1.md", "주간 규칙과 평가")}<br>${link(market === "KR" ? "docs/weekly-decision/kodex200-benchmark-audit.md" : "docs/us-source-readiness-v1.md", "데이터 품질과 한계")}<br>${link("docs/alpha-research-philosophy-v2.md", "연구 원칙")}</p><p>${market === "KR" ? "과거 보정의 기대초과는 봉인된 구형 benchmark 원장을 읽습니다. 교정 성과를 보고 판단 문턱이나 파라미터를 바꾸지 않았습니다." : "SPY는 공식 기준이고, 병합된 QQQ 자료는 별도 수동 연구 대안입니다. 원천 빈티지·기간·통화·분배금 및 외부 대조 한계를 함께 확인해야 하며, 현재 정책의 잔여 자산은 SPY를 유지합니다."}</p></details></article></div>`;
  }
  function render() {
    document.documentElement.dataset.market = market;
    document
      .querySelectorAll("button[data-market]")
      .forEach((b) =>
        b.setAttribute("aria-pressed", String(b.dataset.market === market)),
      );
    document
      .querySelectorAll("[data-study]")
      .forEach((b) =>
        b.setAttribute("aria-pressed", String(b.dataset.study === kind)),
      );
    $("#marketContext").textContent =
      market === "KR"
        ? "KR / KRX · KRW · 독립 판단"
        : "US / NYSE·Nasdaq · USD · 독립 판단";
    $("#studySwitch").hidden = market === "US";
    const s = currentStudy();
    const d = decisionState(bundle, market);
    if (publicationError)
      d.reason =
        "영수증이나 게시 상태 조회에 실패했습니다. 현재 비중을 표시하지 않습니다.";
    $("#decisionPanel").setAttribute("aria-busy", String(loading));
    let p1 = decisionMarkup(d, market, bundle?.commit);
    if (d.state === "UNAVAILABLE_OR_BLOCKED") p1=`<article class="decision-card strategy-current" data-current-strategy="P1"><div class="card-meta"><b>P1 · 공식 주간 가상 판단</b><span class="pill warn">UNAVAILABLE</span></div>${p1}</article>`;
    else {
      p1=p1.replace('class="decision-card"','class="decision-card strategy-current" data-current-strategy="P1"')
        .replace("공식 주간 가상 판단","P1 · 공식 주간 가상 판단")
        .replace("</h2>",`</h2><p class="current-total">현재 확정 영수증 · ${esc(d.receipt.status)} · 합계 100%</p>`)
        .replace("</details></article>",`<p class="digest">원천 입력 SHA-256 ${esc(d.receipt.inputs?.siteDataSha256 || "영수증 원문 참조")}</p><p>제외: ${esc((d.receipt.excluded || []).map(x=>`${x.ticker}: ${(x.codes || []).join(", ")}`).join(" · ") || d.receipt.noTradeReason || "추가 제외 미기록")}</p><p>이전 관측 차이: ${esc(JSON.stringify(d.receipt.previousWeekChange || "미기록"))}</p></details></article>`);
    }
    const champion=championState(researchBundle,market,site);
    $("#decisionPanel").innerHTML = loading
      ? '<p class="loading">게시된 영수증을 확인하고 있습니다.</p>'
      : `<p class="watch-note">P1은 공식 주간 가상 영수증입니다. C1/C2는 독립된 현재 관측 연구 변형이며 실전 권고가 아닙니다. 선택된 보유 · 관찰 목록 · 과거 백테스트 보유를 구분합니다.</p><div class="current-strategies">${p1}${championMarkup(champion,"C1",market)}${championMarkup(champion,"C2",market)}</div>`;
    $("#performancePanel").setAttribute(
      "aria-busy",
      String(performanceOpened && !reports[kind] && !failures[kind]),
    );
    $("#performancePanel").innerHTML =
      !performanceOpened ? '<div class="empty"><p>과거 연구 자료는 요청할 때만 불러옵니다. 현재 전략 판단·시장·13F는 별도 원천을 사용합니다.</p><button type="button" class="detail-button" data-load-performance>전략별 과거 성과 불러오기</button></div>' : !reports[kind] && !failures[kind]
        ? '<p class="loading">교정된 원본 연구 자료를 확인하고 있습니다.</p>'
        : performanceMarkup(s, market, visible, reports.usd) + (market==="US"?`<p class="notice">미국의 과거 C1/C2는 생존편향·가격 이력 한계로 검증된 종목 선택 성과를 표시하지 않습니다.</p>${qqqMarkup(reports.qqq)}`:"");
    $("#watchlistPanel").innerHTML = loading
      ? '<p class="loading">영수증의 관찰 기록을 확인하고 있습니다.</p>'
      : watchlistMarkup(d);
    renderEvidence(d);
    $("#siteStatus").textContent=siteLoading?"production 시장 원천 확인 중":site ? `${sourceMode(site)} · 생성 ${site.generatedAt || "미기록"} · ${siteIsCurrent(site)?"게시 시각 기준 충족":"게시 지연/미확인 — 과거 관측으로만 표시"}${site.recommendationsBlocked?" · 전략 안전 차단":""}` : "production 시장 원천 조회 불가 · 공식 기관 캐시는 별도 표시 가능";
    $("#marketPanel").innerHTML=marketMarkup(site,market);
    if (sourceMode(site)==="live") {
      const h=site.marketDataHealth;
      $("#siteStatus").textContent += h ? ` · 테이프 ${h.status || "UNKNOWN"} · 수집 ${number(h.fetched)}/${number(h.requested)} · 최신 ${number(h.current)} / 지연 ${number(h.delayed)} / 오래됨 ${number(h.stale)} · 중요 누락 ${(h.missingCritical || []).join(", ") || "없음"} · 중요 지연 ${(h.staleCritical || []).join(", ") || "없음"}` : " · 테이프 품질 요약 미보고";
    }
    $("#macroPanel").innerHTML=macroMarkup(site,market);
    if (sourceMode(site)==="live" && site.macroRegime?.pointInTimeLimitations)
      $("#macroPanel").insertAdjacentHTML("beforeend",`<p class="notice">원천 PIT 한계: ${esc(site.macroRegime.pointInTimeLimitations)}</p>`);
    const institutions=(sourceMode(site)==="live"?site?.institutionalHoldings13F:null) || cachedInstitutions(reports.institutionalCache);
    const nps=(sourceMode(site)==="live"?site?.nationalPensionService:null) || cachedNps(reports.npsCache);
    $("#institutionalPanel").innerHTML=institutionalMarkup(institutions);
    $("#npsPanel").innerHTML=npsMarkup(nps);
    if (institutions?.sourceIdentity) $("#institutionalPanel").insertAdjacentHTML("beforeend",`<p class="source-caption">production 원천 조회 실패 시 사용하는 고정된 공식 캐시 · ${link(institutions.sourceIdentity.path,"캐시 바이트 원본")}<br><span class="digest">${esc(institutions.sourceIdentity.sha256)}</span></p>`);
    if (nps?.sourceIdentity) $("#npsPanel").insertAdjacentHTML("beforeend",`<p class="source-caption">고정된 공식 캐시 · ${link(nps.sourceIdentity.path,"기금 캐시 원본")}</p>`);
  }
  async function ensureSource(key) {
    if (reports[key] || sourceLoading.has(key)) return;
    sourceLoading.add(key);
    try {
      reports[key] = await loadSource(key);
      delete failures[key];
    } catch (_) {
      failures[key] = true;
    }
    sourceLoading.delete(key);
    render();
  }
  async function refresh() {
    if (inFlight) return;
    inFlight = true;
    loading = true;
    bundle = null;
    researchBundle = null;
    publicationError = false;
    $("#refresh").disabled = true;
    render();
    try {
      bundle = await loadPublication();
      try { researchBundle = await loadResearchPublication(bundle.commit); } catch (_) { researchBundle=null; }
    } catch (_) {
      publicationError = true;
    }
    loading = false;
    inFlight = false;
    $("#refresh").disabled = false;
    render();
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest('a[href="#performance"], [data-load-performance]')) openPerformance();
    const contextButton=event.target.closest("[data-context-kind]");
    if (contextButton) {
      const type=contextButton.dataset.contextKind, id=contextButton.dataset.contextId;
      const institutions=(sourceMode(site)==="live"?site?.institutionalHoldings13F:null) || cachedInstitutions(reports.institutionalCache);
      const x=type==="index" ? site?.indices?.find(r=>r.symbol===id) : type==="macro" ? macroIndicators(site).find(r=>r.name===id) : institutions?.managers.find(r=>r.id===id);
      if (!x) return;
      activeContext={type,x,range:type==="macro"?"1Y":"3M"};
      renderContext(); $("#contextDialog").showModal(); return;
    }
    const rangeButton=event.target.closest("[data-context-range]");
    if (rangeButton && activeContext) { activeContext.range=rangeButton.dataset.contextRange; renderContext(); return; }
    const marketButton = event.target.closest("button[data-market]");
    if (marketButton) {
      market = marketButton.dataset.market;
      kind = "weekly";
      try {
        sessionStorage.setItem("investment-market", market);
      } catch (_) {
        /* No persistence required when denied. */
      }
      render();
      if (performanceOpened) openPerformance();
      return;
    }
    const studyButton = event.target.closest("[data-study]");
    if (studyButton && market === "KR") {
      kind = studyButton.dataset.study;
      render();
      openPerformance();
      return;
    }
    const weekButton = event.target.closest("[data-week]");
    if (weekButton) {
      const d = currentStudy()?.stockDecisions.find(
        (r) => r.date === weekButton.dataset.week,
      );
      if (!d) return;
      const expanded = weekButton.getAttribute("aria-expanded") === "true";
      document
        .querySelectorAll("[data-week]")
        .forEach((b) => b.setAttribute("aria-expanded", "false"));
      const detail = $("#weekDetail");
      detail.hidden = expanded;
      if (!expanded) {
        weekButton.setAttribute("aria-expanded", "true");
        detail.innerHTML = `<b>실행 ${esc(d.date)} · 신호 ${esc(d.signalDate)}</b><div class="tickers">${d.holdings.map((t) => `<span>${esc(t)}</span>`).join("")}</div><p>이 과거 결정 자료에는 종목별 비중이 없습니다. 개별 주 초과수익이나 비중을 추정해 채우지 않습니다.</p>`;
      }
    }
  });
  document.addEventListener("change", (event) => {
    if (event.target.matches("[data-line]")) {
      visible[event.target.dataset.line] = event.target.checked;
      const s = currentStudy();
      if (s) $("#chartPlot").innerHTML = chartMarkup(s, visible);
    }
  });
  $("#refresh").addEventListener("click", () => {
    refresh();
    loadSite();
    if (performanceOpened) openPerformance();
  });
  function renderContext() {
    if (activeContext) $("#contextDialogBody").innerHTML=activeContext.type==="manager"?managerDetail(activeContext.x):chartDetail(activeContext.x,activeContext.type,activeContext.range);
  }
  $("#closeDialog").addEventListener("click",()=>$("#contextDialog").close());
  async function loadSite() {
    siteLoading=true; render();
    try { site=JSON.parse(decode(await getBytes("data/site-data.json"))); } catch (_) { site=null; }
    siteLoading=false; render();
    if (sourceMode(site)!=="live" || !site?.institutionalHoldings13F) ensureSource("institutionalCache");
    if (sourceMode(site)!=="live" || !site?.nationalPensionService) ensureSource("npsCache");
  }
  function openPerformance() {
    performanceOpened=true; ensureSource(kind);
    if (market==="US") { ensureSource("usd"); ensureSource("qqq"); }
  }
  render();
  refresh();
  loadSite();
  window.setInterval(()=>{refresh();loadSite();}, 15 * 60 * 1000);
}

// Pure adapter contracts are exercised in Node; the deployed file has no module
// dependency and works with the unchanged Pages staging list.
if (typeof module !== "undefined" && module.exports)
  module.exports = {
    SOURCES,
    SOURCE_COMMIT,
    canonicalReceiptLine,
    sha256,
    parseReceipts,
    validReceipt,
    decisionState,
    studyData,
    decisionMarkup,
    performanceMarkup,
    watchlistMarkup,
    chartMarkup,
    fmt,
    esc,
    CHAMPION_PATH, CHAMPION_VERSION, parseChampionReceipts, validChampionPair,
    championState, championMarkup, siteIsCurrent, observations, rangePoints, trendSvg,
    marketMarkup, macroIndicators, macroMarkup, chartDetail, institutionalMarkup,
    managerDetail, npsMarkup, safeSourceLink, cachedInstitutions, cachedNps, qqqMarkup,
  };
if (typeof document !== "undefined") startTerminal();
