/* Reproducible rendered-page verification. Install Playwright outside the repo,
 * set NODE_PATH to its node_modules and TERMINAL_RECEIPT_DIR to the three files
 * extracted read-only from the documented signal-history commit. No replay.
 * --live also checks actual HTTP sources through the managed proxy, with TLS
 * verification enabled by NODE_EXTRA_CA_CERTS; it never accepts invalid certs.
 */
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const http = require("node:http");
const assert = require("node:assert/strict");
const { webcrypto, createHash } = require("node:crypto");
const { chromium, request } = require("playwright");
globalThis.crypto = webcrypto;
const ROOT = path.resolve(__dirname, "..");
const A = require(path.join(ROOT, "app.js"));
const evidence = process.env.TERMINAL_RECEIPT_DIR;
const output =
  process.env.TERMINAL_VERIFICATION_DIR ||
  path.join(os.tmpdir(), "investment-terminal-verification");
const commit = "6a6b7e753814cc9adf56811ca78abdcaef0d69ea";
const fixtureNow = "2026-10-11T12:00:00Z";
const MIME = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "text/javascript",
  ".json": "application/json",
  ".md": "text/markdown",
};
const clone = (x) => structuredClone(x);
function syntheticReceipt(count) {
  return {
    schema: "WEEKLY_DECISION_RECEIPT_V1",
    policyVersion: "weekly-passive-first-v1",
    receiptId: "weekly-passive-first-v1|KR|2026-10-09",
    region: "KR",
    asOfDate: "2026-10-09",
    generatedAt: "2026-10-11T05:00:00Z",
    weekStatus: "FINAL_WEEKLY",
    liveValidated: false,
    evidenceStatus: { verifiedLive: "NOT_VERIFIED" },
    benchmark: "069500.KS",
    benchmarkName: "KODEX 200",
    status: "STOCKS_SELECTED",
    stockCount: count,
    holdings: Array.from({ length: count }, (_, i) => ({
      ticker: `TEST${i}`,
      name: `합성 검증 ${i}`,
      weightPct: 15,
    })),
    weights: {
      ...Object.fromEntries(
        Array.from({ length: count }, (_, i) => [`TEST${i}`, 0.15]),
      ),
      "069500.KS": 1 - count * 0.15,
    },
    stockWeightPct: count * 15,
    benchmarkWeightPct: 100 - count * 15,
  };
}
async function main() {
  assert.ok(
    evidence,
    "Set TERMINAL_RECEIPT_DIR; never substitute fabricated production data",
  );
  fs.mkdirSync(output, { recursive: true });
  const original = Object.fromEntries(
    ["latest.json", "publication-status.json", "receipts.jsonl"].map((n) => [
      n,
      fs.readFileSync(path.join(evidence, n), "utf8"),
    ]),
  );
  const realRows = await A.parseReceipts(original["receipts.jsonl"]);
  assert.equal(realRows.length, 2); // This pinned input has exactly two receipts.
  let fixture = clone(original);
  const stage = fs.mkdtempSync(path.join(os.tmpdir(), "terminal-pages-stage-"));
  // Same frontend copy list as the byte-pinned Pages workflow.
  for (const n of ["index.html", "styles.css", "app.js"])
    fs.copyFileSync(path.join(ROOT, n), path.join(stage, n));
  fs.mkdirSync(path.join(stage, "docs"));
  fs.copyFileSync(
    path.join(ROOT, "docs/investment-philosophy.md"),
    path.join(stage, "docs/investment-philosophy.md"),
  );
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, "http://localhost").pathname;
    const file = path.join(
      stage,
      pathname === "/" ? "index.html" : pathname.slice(1),
    );
    if (
      !file.startsWith(stage + path.sep) ||
      !fs.existsSync(file) ||
      !fs.statSync(file).isFile()
    ) {
      res.writeHead(404);
      res.end();
      return;
    }
    res.writeHead(200, {
      "Content-Type": MIME[path.extname(file)] || "text/plain",
    });
    res.end(fs.readFileSync(file));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
    args: ["--no-sandbox"],
  });
  const report = {
    version: "RESEARCH_TERMINAL_BROWSER_V2",
    sourceMain: A.SOURCE_COMMIT,
    receiptCommit: commit,
    fixtureObservationTime: fixtureNow,
    frontendSha256: Object.fromEntries(["index.html", "app.js", "styles.css"].map(name => [name, createHash("sha256").update(fs.readFileSync(path.join(stage, name))).digest("hex")])),
    screenshots: [],
    viewports: [],
    checks: [],
    live: { status: "NOT_RUN" },
  };
  const jsErrors = [];
  const normalConsoleErrors = [];
  let transport;
  try {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 1000 },
    });
    await context.route("**/*", async (route) => {
      const u = route.request().url();
      if (u.startsWith(url)) return route.continue();
      if (u.includes("/git/ref/heads/signal-history"))
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ object: { sha: commit, type: "commit" } }),
        });
      const last = u.split("/").pop();
      if (
        u.includes(`/ledger/weekly-decisions/`) &&
        Object.hasOwn(fixture, last)
      )
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: fixture[last],
        });
      const source = Object.values(A.SOURCES).find((s) =>
        u.endsWith(`/${A.SOURCE_COMMIT}/${s.path}`),
      );
      if (source)
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: fs.readFileSync(path.join(ROOT, source.path)),
        });
      throw new Error(`Unexpected dependency: ${u}`);
    });
    const p = await context.newPage();
    p.on("pageerror", (e) => jsErrors.push(e.message));
    p.on("console", (m) => {
      if (m.type() === "error") normalConsoleErrors.push(m.text());
    });
    await p.clock.setFixedTime(new Date(fixtureNow));
    const settled = async () => {
      await p.waitForFunction(
        () =>
          document.querySelector("#decisionPanel").getAttribute("aria-busy") ===
          "false",
      );
      await p.waitForFunction(
        () =>
          document
            .querySelector("#performancePanel")
            .getAttribute("aria-busy") === "false",
      );
    };
    await p.goto(url);
    await settled();
    const selectedMarket = async (m) => {
      await p.locator(`button[data-market="${m}"]`).click();
      await settled();
    };
    const screenshot = async (name) => {
      await p.evaluate(() => {
        document.activeElement?.blur();
        window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      });
      await p.screenshot({ path: path.join(output, name), fullPage: true });
      report.screenshots.push(name);
    };
    for (const width of [375, 390, 768, 1280]) {
      await p.setViewportSize({ width, height: width < 600 ? 844 : 1000 });
      for (const market of ["KR", "US"]) {
        await selectedMarket(market);
        const bounds = await p.evaluate(() => ({
          document: document.documentElement.scrollWidth,
          viewport: innerWidth,
        }));
        assert.ok(
          bounds.document <= bounds.viewport,
          `${market} ${width}: overflow ${JSON.stringify(bounds)}`,
        );
        assert.equal(
          await p
            .locator("[data-portfolio-state]")
            .getAttribute("data-portfolio-state"),
          "BENCHMARK_ONLY",
        );
        assert.ok(
          (await p.locator("#marketContext").innerText()).startsWith(market),
        );
        const current = realRows.find((r) => r.region === market);
        assert.ok(
          (await p.locator("#decisionPanel").innerText()).includes(
            current.asOfDate,
          ),
        );
        assert.equal(await p.locator("#watchlistPanel .watch-card").count(), 5);
        assert.ok(
          (await p.locator("#watchlistPanel").innerText()).includes(
            "매수 추천·보유 비중을 뜻하지 않습니다",
          ),
        );
        assert.equal(await p.locator("section").count(), 4);
        assert.equal(
          await p.locator('#performancePanel [data-strategy="C2"]').count(),
          0,
        );
        report.viewports.push({
          width,
          market,
          pageOverflowPx: bounds.document - bounds.viewport,
        });
        if (width === 1280 || (width === 390 && market === "KR"))
          await screenshot(`${market.toLowerCase()}-${width}.png`);
      }
    }
    assert.match(
      await p.locator("#performancePanel").innerText(),
      /개별 종목 선택 실적 없음/,
    );
    assert.match(await p.locator("#performancePanel").innerText(), /14\.734%/);
    assert.match(await p.locator("#performancePanel").innerText(), /16\.698%/);
    assert.equal(await p.locator("[data-week]").count(), 0);
    await p.reload();
    await settled();
    assert.equal(await p.locator("html").getAttribute("data-market"), "US");
    report.checks.push(
      "market switch and session retention; all four sections coherent; US no fake selection timeline",
    );
    await selectedMarket("KR");
    assert.equal(await p.locator("[data-week]").count(), 4);
    await p.locator('[data-week="2025-07-14"]').click();
    assert.match(await p.locator("#weekDetail").innerText(), /207940\.KS/);
    assert.match(await p.locator("#weekDetail").innerText(), /비중이 없습니다/);
    await p.locator('[data-line="P1"]').uncheck();
    assert.equal(await p.locator('[data-chart-line="P1"]').count(), 0);
    await p.locator('[data-line="P1"]').check();
    await p.locator('[data-study="anchors"]').click();
    await settled();
    assert.match(await p.locator("#performancePanel").innerText(), /155회/);
    assert.match(
      await p.locator("#performancePanel").innerText(),
      /\+1\.752%p/,
    );
    assert.match(
      await p.locator("#performancePanel").innerText(),
      /사후 탐색 · 독립 검증 미완료/,
    );
    assert.equal(await p.locator("[data-strategy]").count(), 4);
    await screenshot("kr-21-session-1280.png");
    for (const width of [375, 390, 768, 1280]) {
      await p.setViewportSize({ width, height: 1000 });
      const overflow = await p.evaluate(
        () => document.documentElement.scrollWidth - innerWidth,
      );
      assert.ok(overflow <= 0);
      report.viewports.push({
        width,
        market: "KR",
        study: "anchors",
        pageOverflowPx: overflow,
      });
    }
    report.checks.push(
      "713 weekly versus 155 anchors isolated; exact C2 evidence; holdings detail; chart toggle",
    );
    for (const summary of await p.locator("#performancePanel summary").all())
      await summary.click();
    for (const width of [375, 390, 768, 1280]) {
      await p.setViewportSize({ width, height: 1000 });
      const overflowExpanded = await p.evaluate(
        () => document.documentElement.scrollWidth - innerWidth,
      );
      assert.ok(overflowExpanded <= 0);
      report.viewports.push({ width, market: "KR", study: "anchors", expanded: true, pageOverflowPx: overflowExpanded });
    }
    await p.locator('[data-study="weekly"]').click();
    await settled();
    for (const count of [1, 2, 3, 4, 5]) {
      const r = syntheticReceipt(count);
      r.digest = await A.sha256(A.canonicalReceiptLine(JSON.stringify(r)));
      const latest = JSON.parse(original["latest.json"]);
      latest.regions.KR = {
        ...r,
        freshness: {
          status: "FRESH",
          observedSession: r.asOfDate,
          expectedSession: r.asOfDate,
        },
      };
      fixture = {
        ...original,
        "receipts.jsonl": JSON.stringify(r),
        "latest.json": JSON.stringify(latest),
      };
      await p.locator("#refresh").click();
      await settled();
      assert.equal(
        await p
          .locator("[data-portfolio-state]")
          .getAttribute("data-portfolio-state"),
        "STOCKS_PLUS_BENCHMARK",
      );
      assert.equal(await p.locator(".holding").count(), count + 1);
      assert.ok(
        (await p.locator("#decisionPanel").innerText()).includes(
          `${(100 - count * 15).toFixed(2)}%`,
        ),
      );
    }
    report.checks.push(
      "synthetic safety scenarios: 1–5 exact recorded stock weights and residual; no synthetic return path",
    );
    const scenarios = {
      refused: (f) => {
        const s = JSON.parse(f["publication-status.json"]);
        s.status = "REFUSED";
        f["publication-status.json"] = JSON.stringify(s);
      },
      stale: (f) => {
        const l = JSON.parse(f["latest.json"]);
        l.generatedAt = "2026-09-01T00:00:00Z";
        f["latest.json"] = JSON.stringify(l);
      },
      blocked: (f) => {
        const l = JSON.parse(f["latest.json"]);
        l.blocked = true;
        f["latest.json"] = JSON.stringify(l);
      },
      preview: (f) => {
        const l = JSON.parse(f["latest.json"]);
        l.regions.KR.weekStatus = "INTRA_WEEK_PREVIEW";
        f["latest.json"] = JSON.stringify(l);
      },
      missing: (f) => {
        f["receipts.jsonl"] = "";
      },
      digestMismatch: (f) => {
        f["receipts.jsonl"] = f["receipts.jsonl"].replace("100.0", "99.0");
      },
    };
    for (const [name, mutate] of Object.entries(scenarios)) {
      fixture = clone(original);
      mutate(fixture);
      await p.locator("#refresh").click();
      await settled();
      assert.equal(
        await p
          .locator("[data-portfolio-state]")
          .getAttribute("data-portfolio-state"),
        "UNAVAILABLE_OR_BLOCKED",
        name,
      );
      assert.equal(await p.locator(".holding").count(), 0);
      assert.equal(await p.locator("#watchlistPanel .watch-card").count(), 0);
      assert.doesNotMatch(
        await p.locator("#decisionPanel").innerText(),
        /KODEX 200 100%/,
      );
    }
    report.checks.push(
      "refused/stale/blocked/preview/missing/digest mismatch fail closed without invented positions",
    );
    assert.equal(jsErrors.length, 0);
    assert.equal(normalConsoleErrors.length, 0);
    report.browser = await browser.version();
    report.applicationErrors = jsErrors;
    report.consoleErrors = normalConsoleErrors;
    await context.close();
    if (process.argv.includes("--live")) {
      transport = await request.newContext({
        proxy: process.env.HTTPS_PROXY
          ? { server: process.env.HTTPS_PROXY }
          : undefined,
        timeout: 20000,
      });
      const live = await browser.newContext({
        viewport: { width: 1280, height: 1000 },
      });
      const liveErrors = [];
      const requests = [];
      await live.route("**/*", async (route) => {
        const u = route.request().url();
        if (u.startsWith(url)) return route.continue();
        const response = await transport.get(u);
        requests.push({ url: u, status: response.status() });
        await route.fulfill({ response });
      });
      const page = await live.newPage();
      page.on("pageerror", (e) => liveErrors.push(e.message));
      page.on("console", (m) => {
        if (m.type() === "error") liveErrors.push(m.text());
      });
      await page.goto(url);
      await page.waitForFunction(
        () =>
          document.querySelector("#decisionPanel").getAttribute("aria-busy") ===
          "false",
      );
      await page.waitForFunction(
        () =>
          document
            .querySelector("#performancePanel")
            .getAttribute("aria-busy") === "false",
      );
      assert.equal(
        await page
          .locator("[data-portfolio-state]")
          .getAttribute("data-portfolio-state"),
        "BENCHMARK_ONLY",
      );
      assert.equal(liveErrors.length, 0);
      assert.ok(requests.every((r) => r.status === 200));
      report.live = {
        status: "PASS",
        observedAt: new Date().toISOString(),
        tlsVerified: true,
        managedProxyTransport: true,
        requests,
        consoleErrors: liveErrors,
      };
      await live.close();
    }
    fs.writeFileSync(
      path.join(output, "browser-verification.json"),
      JSON.stringify(report, null, 2) + "\n",
    );
    process.stdout.write(
      JSON.stringify({
        browser: report.browser,
        viewports: report.viewports.length,
        checks: report.checks.length,
        live: report.live.status,
        output,
      }) + "\n",
    );
  } finally {
    if (transport) await transport.dispose();
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(stage, { recursive: true, force: true });
  }
}
main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
