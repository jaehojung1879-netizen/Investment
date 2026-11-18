"""Korean narrative bound to the saved market results, without selecting new rules."""
from __future__ import annotations

import json

import pandas as pd

from research.kr_us_strategy_batch_v1 import report as R


def exposures(market, ids):
    path = R.OUT / market / ("exposures.csv.gz" if market == "KR" else "exposure.csv.gz")
    if not path.exists():
        return []
    f = pd.read_csv(path)
    key, names = ("id", "actual") if market == "KR" else ("config", "actualNames")
    group = "namedTwoWeight" if market == "KR" else "megaWeight"
    cap = "capTop5DirectWeight" if market == "KR" else "capTop5Weight"
    sector = "industryWeights" if market == "KR" else "sectorWeights"
    rows = []
    for config in ids:
        g = f.loc[f[key].eq(config)]
        if g.empty:
            continue
        by_sector = {}
        for raw in g[sector].dropna():
            for s, w in json.loads(raw).items():
                by_sector[s] = by_sector.get(s, 0) + w / len(g)
        largest = ", ".join(f"{s} {R.pct(w, False)}%" for s, w in sorted(by_sector.items(), key=lambda x: -x[1])[:3])
        rows.append([config, len(g), f"{g[names].mean():.2f}", R.pct(float(g.etfWeight.mean()), False),
                     R.pct(float(g[group].mean()), False), R.pct(float(g[cap].mean()), False), largest])
    return rows


def s2_shortfalls():
    path = R.OUT / "KR/exposures.csv.gz"
    if not path.exists():
        return []
    f = pd.read_csv(path)
    rows = []
    for k in range(1, 6):
        g = f.loc[f.id.eq(f"KR:S2:SLOT20:K{k}")]
        distribution = ", ".join(f"{int(n)}개:{int(count)}주" for n, count in sorted(g.actual.value_counts().items()))
        rows.append([k, len(g), int(g.shortfall.sum()), distribution])
    return R.table(["요청 이름수", "판단주", "적격 부족 주", "실제 보유 이름수 분포"], rows) + [""]


def periods(summaries, market, ids):
    rows = []
    for config in ids:
        for h in (126, 252):
            if market == "KR":
                s = summaries.get(market, {}).get("sensitivity", {}).get(str(h), {}).get(config, {})
                by = {k: s.get(k, R.empty()) for k in ("to2021", "from2022", "touchesSemiLedPostHoc", "exSemiLedKnownPostHoc")}
            else:
                by = summaries.get(market, {}).get("periods", {}).get(str(h), {}).get(config, {})
            for label, s in by.items():
                rows.append([config, "6" if h == 126 else "12", label, s.get("n", 0), R.effect(s)])
    return rows


def matched_subset_table():
    path = R.OUT / "matched-common-diagnostics.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    lines = ["### 매칭 가능한 신호 집합의 공통 날짜 — 사후 가용성 진단", "",
             "미국 산업 전체 바구니·칵테일·U1은 같은 업종 후보를 이미 보유해 대조군을 만들 수 없었다. 준비된10신호 전체 공통은0주다. 원 핵심 검정은 그대로 미측정으로 두고, 아래는 한국 complete4신호/미국 단일 종목7신호만의 공통 날짜 진단을 추가했다. 집합을 줄인 사후 보조 분석이며 명목 구간이다. 새로운 핵심 주장이나 Holm 통과로 해석하지 않는다.", ""]
    rows = []
    for market, by in data["markets"].items():
        for h, block in by.items():
            for selector in data["sets"][market]:
                s = block["selectors"][selector]["subsetCommon"]
                rows.append([market, selector, "6" if h == "126" else "12", s["selection"]["n"],
                             R.effect(s["total"]), R.effect(s["selection"]), R.effect(s["replacement"])])
    lines += R.table(["시장", "신호", "개월", "공통 n", "전체ETF 대체", "선택력", "ETF→peer"], rows)
    lines += ["", "동일 날짜 전체ETF 대체=선택력+ETF→peer를 검산했다. 최대 행별 오차와 정확한 날짜 마스크는 [원본](results/matched-common-diagnostics.json), [날짜별 3항](results/matched-decomposition-diagnostics.csv.gz)에 있다.", ""]
    return lines


def source_bridge_table():
    path = R.OUT / "us-source-bridge.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    rows = []
    for key, s in data["bridge"].items():
        rows.append([key, s["n"], R.pct(s["published"]), R.pct(s["archivedUncorrectedCapture"]),
                     R.pct(s["repairedCapture"]), R.pct(s["ctvaRepairEffect"])])
    return ["", "### 미국 원 집계 → 새 capture → CTVA 정정", "",
            "정정 전 새 capture의 native 고정보유 평균은 원 published와 최대1e-17 수준으로 일치했다. 정정 전후 달라진 수치형 feature는 CTVA 원종가328행·시총304행뿐이다. 칵테일112주·U1 143주의 비중이 달라졌다. 아래 차이는 새 후보 최적화가 아니라 원 입력 오류의 정정이다.", ""] + R.table(
        ["세션/구성", "n", "원 published", "정정 전 capture", "정정 후", "CTVA 정정 차이"], rows) + ["", "[원본/행별 재현](results/us-source-bridge.json) · `python -m research.kr_us_strategy_batch_v1.us_bridge --private /workspace/batch-inputs/us`. 정정 전 원종가 입력은 잘못된 기준이며 운용 후보로 취급하지 않는다.", ""]


def qqq_table():
    path = R.OUT / "US/qqq-secondary.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    rows = []
    for config in ["US:SPY", *R.US_REPORT_ROWS]:
        a, b = (data["fixed"][str(h)].get(config, R.empty()) for h in (126, 252))
        c, d = (data["ledgers"].get(i, {}).get(config, {}) for i in ("L26", "L52"))
        rows.append([config, f"{a.get('n', 0)}/{b.get('n', 0)}", R.effect(a), R.effect(b),
                     R.pct(c.get("cagrGap")), R.pct(d.get("cagrGap"))])
    return ["### 미국 QQQ 보조 비교", "", "주 검정과 운용 판단의 benchmark는 SPY다. QQQ는 기존 누락 분배 정정을 유지한 총수익이며 같은 체결·비용으로 비교했다. 이 보조 비교로 사전 SPY 가설 가족을 교체하지 않는다.", ""] + R.table(
        ["구성", "n6/12", "6개월 vsQQQ", "12개월 vsQQQ", "L26 CAGR차%p", "L52 CAGR차%p"], rows) + ["", "전체 후보 보조 결과: [qqq-secondary.json](results/US/qqq-secondary.json).", ""]


def conditional_headline(summaries):
    lines = []
    kr = summaries.get("KR", {})
    if kr:
        v = [kr["selection"][str(h)]["CONFIRM_NEUTRAL"]["own"] for h in (126, 252)]
        common = [kr["selection"][str(h)]["S2"]["common"]["n"] for h in (126, 252)]
        lines += [f"한국 사업확인 NEUTRAL의 신호별 own 매칭 표본은 {R.effect(v[0])}/{R.effect(v[1])}%p였다. 한국7신호 공통은 {common[0]}/{common[1]}주다. 날짜가 다른 own 결과로 신호 간 우열을 정하지 않는다.", ""]
    path = R.OUT / "matched-common-diagnostics.json"
    if path.exists():
        data = json.loads(path.read_text())
        for market, selector in (("KR", "CONFIRM_NEUTRAL"), ("US", "PRICE_CONFIRMED")):
            by = data["markets"].get(market)
            if by:
                cells = [by[str(h)]["selectors"][selector]["subsetCommon"] for h in (126, 252)]
                lines += [f"사후 보조 공통 표본 {market} {cells[0]['selection']['n']}/{cells[1]['selection']['n']}주에서 {selector} 선택력은 {R.effect(cells[0]['selection'])}/{R.effect(cells[1]['selection'])}%p, 같은 날짜 ETF 대비 전체 효과는 {R.pct(cells[0]['total']['mean'])}/{R.pct(cells[1]['total']['mean'])}%p였다. 가용성 진단이며 원 핵심 검정을 대체하지 않는다.", ""]
    examples = []
    for config in ("KR:K2", "KR:INDUSTRY_MOMENTUM:SLOT20:K5", "US:SECTOR_MOMENTUM:Q100", "US:U1:Q100"):
        a, b = (R.fixed_cell(summaries, h, config) for h in (126, 252))
        if a.get("mean") is not None and b.get("mean") is not None:
            examples.append(f"{config} {R.pct(a['mean'])}/{R.pct(b['mean'])}%p")
    if examples:
        lines += ["다른 ETF 대비 과거 점추정: " + "; ".join(examples) + ". 불확실성·위험은 아래의 전체 표와 함께 판단한다.", ""]
    sector = summaries.get("US", {}).get("sensitivity", {})
    if sector:
        a, b = [sector[str(h)]["US:SECTOR_MOMENTUM:Q100"] for h in (126, 252)]
        lines += [f"미국 산업 바구니 주식100%는 사후 최대 기여 진입년 {a['postHocMaximumEntryYear']}/{b['postHocMaximumEntryYear']}을 제외하면 {R.effect(a['excludeMaximumEntryYear'])}/{R.effect(b['excludeMaximumEntryYear'])}%p였다(n={a['excludeMaximumEntryYear']['n']}/{b['excludeMaximumEntryYear']['n']}). 이 구성은 업종 전체를 담으므로 이번 같은 업종 peer 대조로 업종 안 종목 선택력을 측정할 수 없다.", ""]
    return lines


def write(summaries, coverage, core, broad, evidence):
    passing = lambda rows: [r for r in rows if r["horizon"] == 126 and r["mean"] is not None and r["mean"] > 0 and r["pHolm"] < .05]
    cp, bp = passing(core), passing(broad)
    sp = [r for r in cp if r["kind"] == "selection"]
    core_missing = sum(r["horizon"] == 126 and r["pRawApprox"] is None for r in core)
    selection_missing = sum(r["horizon"] == 126 and r["kind"] == "selection" and r["pRawApprox"] is None for r in core)
    improved = [k for k, v in evidence.items() if v["bothCagrGapsPositive"] and v["bothMddStrictlyImproved"]]
    headline = []
    for market, selector, config in (("KR", "S2", "KR:S2:FIXED20:K5"), ("US", "PRICE_CONFIRMED", "US:U1:Q020")):
        s = [summaries.get(market, {}).get("selection", {}).get(str(h), {}).get(selector, {}) for h in (126, 252)]
        a, b = (R.fixed_cell(summaries, h, config) for h in (126, 252))
        sa, sb = (R.sensitivity_cell(summaries, market, h, config) for h in (126, 252))
        headline.append([market, f"{selector}: {R.effect(s[0].get('own'))} / {R.effect(s[1].get('own'))}",
                         f"{config}: {R.effect(a)} / {R.effect(b)}",
                         f"주도주 비중→ETF: {R.effect(sa['group'])} / {R.effect(sb['group'])}"])
    if "US" in summaries:
        a, b = (R.fixed_cell(summaries, h, "US:SECTOR_MOMENTUM:Q100") for h in (126, 252))
        sa, sb = (R.sensitivity_cell(summaries, "US", h, "US:SECTOR_MOMENTUM:Q100") for h in (126, 252))
        headline.append(["US 산업 바구니", "업종 전체 보유로 미보유 same-sector peer 없음",
                         f"주식100%: {R.effect(a)} / {R.effect(b)}",
                         f"주도주 직접 비중→ETF: {R.effect(sa['group'])} / {R.effect(sb['group'])}"])
    lines = ["# 한국·미국 투자전략 일괄 비교", "",
             "2026-11-18 KST · 한국 #349 `d9ac3ed5` · 기존 #348 `3a3e9d8e` · 성과 전 설계 `e6786ee` · 미국 입력 정정 `4710738`.", "",
             "**이미 반복해서 살펴본 과거 자료의 검증이며 전향 성과가 아니다.** 수익 차이는 %p/보유기간이다. 첫 표의 순서는 6개월 / 12개월, 대괄호는 명목 95% paired 이동 블록 구간이다.", "",
             "판단일은 한국2018-01-05~2026-09-11(454주), 미국2014-02-14~2026-08-21(654주), 가격 종료는2026-09-14다. 다음 세션 종가에 체결하고126/252세션을6/12개월로 부른다. 시장별 평가 기간이 다르다.", "",
             "원 판단일 가시성 규칙을 재사용했지만 구성·업종 스냅숏, 시총 대용치, 기업행위 및 빈티지 한계를 상속한다. 완전한 PIT 확인이나 실운용 검증을 마친 자료로 부르지 않는다.", "",
             "## 첫 장: 숫자로 보는 답", ""]
    lines += R.table(["시장", "동일 업종·시총 선택력 — 신호별 own 매칭 표본", "주요 구성의 ETF 대비 — 가격 공통 표본", "고정 주도주를 ETF로 돌리면 — 후보 own 표본"], headline)
    lines += ["", f"사전 고정 선택력19개 중 Holm 통과 **{len(sp)}개**이며 **{selection_missing}개는 공통 표본 부족/매칭 불가로 검정 자체가 미측정**이다. 이는 선택력 부재의 증거와 다르다. 전체 핵심41개 중 **{len(cp)}개** 통과({core_missing}개 미측정), 별도 broad ETF115개 중 **{len(bp)}개** 통과다(주 검정6개월). 미확보·표본 부족 가설도 p=1로 가족에 남겼다.", "",
              f"L26·L52 모두 CAGR이 높고 MDD도 엄격히 얕은 서술적 구성은 {len(improved)}개다: " + (", ".join(f"`{k}`" for k in improved) if improved else "없음") + ". 같은 신호의 다른 비중을 독립된 재현 증거로 세지 않는다. 이는 고정보유 검정 통과와 별개이며 운영 승격을 뜻하지 않는다.", "",
              "**한국에서 판단일에 0~5개를 정할 근거가 충분하다고 결론내리지 않는다.** 0개는 KODEX200 100%다. 만기가 끝난 자료만 쓰는 연간 선택 규칙의 실제 선택과 성과를 아래에 공개한다. 개수·가중치를 이 결과에 맞춰 고치지 않았다.", "",
              "## 1. 같은 업종·시총 종목보다 나았나", ""]
    insert = lines.index("## 1. 같은 업종·시총 종목보다 나았나")
    lines[insert:insert] = conditional_headline(summaries)
    pending = {m: x for m, x in R.market_progress(summaries).items() if x["status"] not in ("COMPLETE", "COMPLETE_WITH_NOT_ESTIMABLE_BOOKS")}
    if pending:
        lines[6:6] = ["**중간 산출 상태:** " + json.dumps(pending, ensure_ascii=False) + ". 미완료 운용 수치는 미측정으로 표시한다.", ""]
    top_nav = []
    for config in ("KR:S2:FIXED20:K5", "KR:K2", "US:U1:Q020", "US:U1:Q100",
                   "US:SECTOR_MOMENTUM:Q020", "US:SECTOR_MOMENTUM:Q050", "US:SECTOR_MOMENTUM:Q100"):
        market = config.split(":")[0]
        a, b = (R.ledger_cell(summaries, market, c, config) for c in ("L26", "L52"))
        top_nav.append([config, R.pct(a.get("cagrGap")), R.pct(a.get("mdd")),
                        R.pct(b.get("cagrGap")), R.pct(b.get("mdd")),
                        R.pct(a.get("annualArithmeticDailyGap")), R.pct(a.get("compoundingRemainder"))])
    insert = lines.index("## 1. 같은 업종·시총 종목보다 나았나")
    lines[insert:insert] = R.table(["운용 구성", "L26 CAGR차%p/년", "L26 MDD%", "L52 CAGR차%p/년", "L52 MDD%", "L26 산술차%p", "L26 복리잔여%p"], top_nav) + ["", "원 장부의 평균 수익과 복리 경로 차이를 분리했다. 예를 들어 S2 총20%·5이름의 양의 CAGR 차이에서 산술차는 음수다. 아래의 고정보유 검정·주도주 민감도와 함께 판단해야 한다.", ""]
    baselines = []
    for market, config in (("KR", "KR:ETF"), ("US", "US:SPY")):
        b = R.ledger_cell(summaries, market, "L26", config)
        if b:
            baselines.append(f"{market} ETF CAGR {R.pct(b.get('cagr'))}%/년·MDD {R.pct(b.get('mdd'))}%")
    if baselines:
        at = lines.index("## 1. 같은 업종·시총 종목보다 나았나")
        lines[at:at] = ["비교 기준: " + "; ".join(baselines) + ".", ""]
    for market in ("KR", "US"):
        lines += [f"### {market}", ""]
        lines += R.table(["신호", "own n6/12", "선택력6개월", "선택력12개월", "전체 매칭률%", "공통 n6/12", "공통6개월", "공통12개월"], R.selection_rows(summaries, coverage, market)) + [""]
    lines += ["주식20%·잔여ETF에서 동일 판단일·실제 이름 수·각 leg 비중을 고정했다. 원 품질/common 후보에서 같은 업종과 시총비[0.5,2]를 먼저 요구하고 |log 시총비| 최소, tie ticker로 고른다. 기존 보유·이미 사용한 peer는 제외한다. 한 leg라도 실패하면 책 전체 비교는 미측정이며 ETF/자기 자신으로 구제하지 않는다. 전체 매칭률 분모는 미만기 주도 포함한 비어 있지 않은 판단일이다. 실패 사유·가중 coverage는 [integrated.json](results/integrated.json)과 matching-audit에 있다.", "",
              "own끼리는 날짜가 달라 이 숫자만으로 신호 순위를 정할 수 없다. 공통은 준비된 모든 신호가 매칭된 날짜다. 6/12개월은 각각50/100주 미만이면 구간·p를 계산하지 않는다. N-PORT 미확보 둘은 교집합에서 제외하되 검정 가족의 p=1 슬롯은 유지한다.", ""]
    diagnostic = matched_subset_table()
    lines += diagnostic
    with (R.HERE / "TABLES-ko.md").open("a") as f:
        f.write("\n" + "\n".join(diagnostic) + "\n")
    lines += ["### 가치·사업 확인과 구성의 한 축 차이", ""]
    rows = []
    for claim in R.REG["coreClaims"]:
        if claim["kind"] not in ("factor", "construction"):
            continue
        a, b = (R.core_cell(summaries, h, claim) for h in (126, 252))
        p = next(r["pHolm"] for r in core if r["id"] == claim["id"] and r["horizon"] == 126)
        rows.append([claim["id"], f"{a.get('n', 0)}/{b.get('n', 0)}", R.effect(a), R.effect(b), R.number(p)])
    lines += R.table(["A−B 비교", "n6/12", "6개월", "12개월", "6개월 Holm41"], rows) + ["",
              "한국 complete pool은 B08·C01/C05/C14 모두 측정된 집합이며 확인 미측정을 실패로 보지 않는다. 두 NEUTRAL은 사전 고정 SHA256 순서로 만든 새 구성이다. 원래부터 있던 독립 사업 점수는 아니다. 필터 기여는 양쪽5이름인 날짜에 한정했다. 원 confirmation-only EW는5이름을 넘을 수 있어 원 정의/옛 결과만 참고로 보존한다.", "",
              "## 2. 0~5개와 ETF 대체 효과", ""]
    headers = ["구성", "공통 n6/12", "6개월 순초과", "12개월 순초과", "L26 CAGR%", "L26 CAGR차%p", "L26 MDD%", "L52 CAGR차%p", "L52 MDD%", "L26 회전/년"]
    lines += s2_shortfalls()
    lines += R.table(headers, R.configuration_rows(summaries, "KR", R.KR_REPORT_ROWS)) + [""]
    lines += R.table(headers, R.configuration_rows(summaries, "US", R.US_REPORT_ROWS)) + [""]
    lines += qqq_table()
    lines += ["",
              "한국 SLOT20은 이름당20%·잔여ETF, FIXED20은 실제 m개 이름에 총20%/m·ETF80%다. 적격0개는ETF100%다. 고정보유 FIXED20 순초과=SLOT20 순초과/m을 검산했다. 같은 이름의 노출을 축소하는 효과와 이름 수를 늘리는 분산 효과를 구분하고 NAV는 실제 계정으로 다시 계산했다. 미국은 기존 stock sleeve의 상대 비중을 보존해 주식20/50/100%·잔여SPY를 비교했다. 원 native 칵테일/U1도 별도 표기했다.", "",
              "미국 main 운용 benchmark는 같은 다음 종가·비용의 SPY 계정이다. 원 연구의 무비용 판단일 SPY와의 차이는 raw benchmark/nativePublishedBaselineDiff에 별도 기록했다. 고정보유는 원 EV.net 비용을 ETF와 종목 모두 적용한다. QQQ는 보조이며 모든 후보의 QQQ 순초과는 US summary에 있다. 연율은 원252세션 관례다.", "",
              "CAGR 차이는 [전체 운용 분해표](TABLES-ko.md)에서 일수익 차이 연율+복리 잔여로 나눴다. 양의 CAGR 차이만으로 선택력을 주장하지 않는다. 편도회전·비용·이름 교체와 유지자산 비중 재설정도 별도 기록했다.", "",
              "## 3. 주도주·특정 구간을 빼면", ""]
    sh = ["구성", "개월", "주도주/서명합%", "주도주 비중→ETF", "보유창 제외 n:초과", "사후 최대 이름", "그 이름→ETF", "사후 최대 진입년", "그 해 제외"]
    lines += R.table(sh, R.sensitivity_rows(summaries, "KR", ["KR:S2:SLOT20:K5", "KR:S2:FIXED20:K5", "KR:K2", "KR:INDUSTRY_MOMENTUM:SLOT20:K5"])) + [""]
    lines += R.table(sh, R.sensitivity_rows(summaries, "US", ["US:PRICE_CONFIRMED:Q100", "US:COCKTAIL:Q100", "US:U1:Q100", "US:SECTOR_MOMENTUM:Q100"])) + ["",
              "모두 사후 민감도다. 표본은 후보 own 가격 해결 날짜여서 앞의70/30구성 공통 표와 다르다. 고정 주도주는 한국 삼성전자·SK하이닉스, 미국 AAPL/MSFT/NVDA/AMZN/GOOGL/GOOG/META/AVGO/TSLA다. 이름별 w×(자산 순수익−ETF 순수익)의 합이 전체 순초과와 일치한다. 전체 서명합이 음수면 비율도 음수, 상쇄가 크면100%를 넘는다. 분모는 전체 책의 ETF 순초과 합이며, 이전 연구의5위 추가 슬롯 기여 중 약79%와는 분모가 다르다. 최대 구간은 해당 후보의 합산 순초과 기여가 가장 큰 진입 calendar-year다. 겹친 주간 창의 합이며 독립 사건 수가 아니다. 전체 이름·년 기여 원본과 모든 후보 민감도는 TABLES/results에 있다.", "",
              "### 업종·대형주 직접 비중", ""]
    eh = ["구성", "판단주", "평균 이름수", "평균ETF%", "주도주 직접%", "후보 cap top5 직접%", "평균 직접 업종 상위3"]
    lines += R.table(eh, exposures("KR", ["KR:S2:SLOT20:K5", "KR:S2:FIXED20:K5", "KR:INDUSTRY_MOMENTUM:SLOT20:K5", "KR:K2"])) + [""]
    lines += R.table(eh, exposures("US", ["US:PRICE_CONFIRMED:Q100", "US:COCKTAIL:Q100", "US:U1:Q100", "US:SECTOR_MOMENTUM:Q100"])) + ["",
              "직접 선택 주식만의 비중이다. ETF를 look-through한 전체 경제적 노출이 아니다. cap top5는 KR Top120/US common 후보 안의 판단일 시총 상위5 proxy다.", "",
              "### 고정 시기·원 반도체 주도기", ""]
    lines += R.table(["구성", "개월", "구간", "n", "순초과"], periods(summaries, "KR", ["KR:S2:SLOT20:K5", "KR:INDUSTRY_MOMENTUM:SLOT20:K5"]) + periods(summaries, "US", ["US:PRICE_CONFIRMED:Q100", "US:COCKTAIL:Q100", "US:U1:Q100", "US:SECTOR_MOMENTUM:Q100"])) + ["",
              "한국 to2021/from2022는 판단일, 미국 ENTRY_FROM_2023/EXIT_BY_2022는 진입/청산 기준이다. 한국 원 SEMI_LED 보유 창 라벨은 미래 수익으로 나눈 사후 진단이며 unknown은 나머지로 채우지 않는다. 주도기·최대 기여 이름·년을 선택 규칙의 입력으로 쓰지 않았다.", "",
              "## 4. 판단일에 만기가 끝난 자료로 고르면", ""]
    lines += R.table(["규칙", "post n6/12", "6개월", "12개월", "L26 post CAGR차", "L26 post MDD", "L52 post CAGR차", "L52 post MDD", "연도별 선택"], R.policies_rows(summaries)) + ["",
              "연간 첫 판단일에 exit<fit인6개월 공통 만기 자료104주 이상이 필요하다. paired 블록95% 하한>0, 과거 평균 costed 코호트 MDD가ETF보다 깊지 않은 후보 중 하한 최대를 고른다. tie는 낮은 주식 비중·개수·ID, 없으면ETF다. 모든 후보의 fit 점수·위험 가드·마지막 학습exit·실제 선택은 fits/trace에 있다. 고정 후보의 같은 post-fit 창도 공개한다. NAV post 창은 기존 계정·보유를 이어받은 재기준 창이며 fresh reset이 아니다. 이전 S2 expanding-mean 개수 규칙의 실패는 [원 보고서](../kr_s2_rank_ladder_v1/REPORT-ko.md)에 그대로 보존했다.", "",
              "## 5. 입력과 기준 재현", "",
              "한국 원 matrix/dataset/macro/vix_fx/SG1 캐시를 공유했다. 원 S2 SLOT0~5와 K2·고정 혼합의 고정보유·운용 수치를 검산했다. 새 S3(FOUR_FACTOR) K2~5에는000030.KS 종료가격6주(6/12개월),008560.KS 추가1주(12개월)가 미해결이다. 해당 책을0/ETF로 채우지 않았다. 전체70구성 공통은421/393주, 다른6신호 own은427/400주다. 원 frozen NAV의 terminal-zero가 발생한 새 책은 조건부 NAV를 남기되 위험 개선 주장에서 제외한다. OCI 후속 자산 재상장 시점 재투자 단순화, Top120·공시 가시성/빈티지 한계를 상속한다.", "",
              "미국 원 TR·재무는 봉인 커밋704d7db6에서 복구했다. 원 비공개 Yahoo/features 캐시가 없어 새 capture를 원 함수로 생성했다. 607 VERIFIED·CIK·연도별 common 통계 일치가 동일 빈티지를 뜻하지는 않는다. CTVA cutoff후6.665배 분할 누락을 원 응답으로 정정했다([근거/정정 범위](INPUT-REPAIR-ko.md)). admission·신호·구성은 불변이다. 원 published 기준과의 차이·가격/거래량 감사·정정 전 archive·새 feature SHA는 [미국 입력](US-INPUTS-ko.md), [감사 JSON](results/us-input-preparation.json), nativeBaselineDiff와 ledger nativePublishedBaselineDiff에 있다.", "",
              "미국 N-PORT OW/OW_RESID의 최소 미확보 파일은 `/workspace/batch-inputs/nport/round8/C2.pkl`이다. 기존 #348 OW_RESID는6개월 기존장부 대비+1.66[+0.70,+2.75]%p, 원 매칭 대비+1.49[+0.49,+2.77], SPY대비−2.16%p였다. 새2배 시총 범위·공통 날짜·20/50/100% 구성과 다른 참고 집계다. 날짜별 보유를 복원하지 못하므로 새 결과로 대체하지 않는다. 원파일·재생성 경로·7,402,820,315바이트 원ZIP은 US-INPUTS에 명시했다. 추가 구매하지 않았다.", ""]
    lines += source_bridge_table()
    lines += ["## 6. 전향 기록·재실행·원본", "",
              "기존 전향 경로6파일의 바이트를 보존·검증했다. preview7개는 전향 관측이 아니다. 최신 loader의 post-pin DART 미갱신·ETF 미검증·주식 분배 누락과 live recorder 등록값None이 남아 있다. 과거 연구를 전향 원장에 소급 쓰지 않았다. 병행 경로와 실제 blocker는 [prospective-status.json](results/prospective-status.json)에 있다.", "",
              "```bash", "export PYTHON=/workspace/s2-venv/bin/python", "export KR_INPUTS=/workspace/s2-inputs", "export US_INPUTS=/workspace/batch-inputs/us", "bash research/kr_us_strategy_batch_v1/reproduce.sh all", "# 기존 입력 재사용: compute / 표·검산: report / 검산만: verify", "```", "",
              "독립 시장별 재실행은 [reproduce.sh](reproduce.sh), [KR 명령](results/KR/REPRODUCE-ko.md), [US 입력](US-INPUTS-ko.md). 전체 실행 후보의 own/common 고정보유·실패·매칭·정책 fit/trace·이름/년 기여·daily NAV와 L26/L52 비용·회전율을 results/KR·US에 보존했다. paired 블록은4000회·seed20261118·25/50주이며 bootstrap-tail p는 근사다. [전체 표](TABLES-ko.md), [41개 핵심 검정](results/core-comparisons.csv), [115개 탐색 검정](results/broad-etf-comparisons.csv), [검산](results/verification.json), [파일 SHA](results/artifact-manifest.json), [검증 기록](VALIDATION.md)."]
    (R.HERE / "REPORT-ko.md").write_text("\n".join(lines) + "\n")
