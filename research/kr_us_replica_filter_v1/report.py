"""Build the Korean first-page comparison from the saved market estimates."""
from __future__ import annotations

from research.kr_us_replica_filter_v1.tables import estimate, pct, read, table
from research.kr_us_replica_filter_v1.verify import HERE, OUT

HORIZONS = ("126", "252")
BRIDGE_ROWS = (
    ("proxyOutsideCommon", "복제의 공시 공통 집합 밖 종목 비중 효과"),
    ("sectorAndMegaWeight", "공통 종목의 업종·대형 기술주 비중 차이"),
    ("withinCellWeight", "같은 업종·대형주 구분 안의 종목 비중 차이"),
    ("reportNamesOutsideProxy", "복제에 빠진 관측 가능 공시 종목"),
    ("reportResidual", "부분 공시 바스켓과 SPY의 잔차"),
)
FENCE = chr(96) * 3


def display(stat):
    return f"{estimate(stat)} (n={stat['n']})"


def get(data, *keys):
    for key in keys:
        data = data[key]
    return data


def paired_rows(summaries, rows):
    return [[label, *[display(get(s, *keys)) for s in summaries]] for label, keys in rows]


def pair(summaries, *keys, render=display):
    return " / ".join(render(get(s, *keys)) for s in summaries)


def us_headline(result):
    horizons = [result["horizons"][h] for h in HORIZONS]
    bridge_path = ("bridge", "strict", "components")
    cols = ["미국 비용 차감 차이 (%p)", "6개월", "12개월"]
    rows = paired_rows(horizons, [
        ("#351 전체 원 복제 기준 − SPY", ("baseline", "netGross", "netExcess")),
        ("공시에서 비교 가능 종목의 종료가격까지 확인한 날짜의 복제 기준 − SPY",
         (*bridge_path, "proxyNetExcess")),
        *[(label, (*bridge_path, key)) for key, label in BRIDGE_ROWS],
    ])
    allocations = [h["bridge"]["strict"]["fullOriginalSampleAttribution"] for h in horizons]
    def precise(x):
        return f"{100*x:+.3f}"

    rows_full = [[label, *[precise(a["components"][key]) for a in allocations]] for key, label in BRIDGE_ROWS]
    four = [sum(v for k, v in a["components"].items() if k != "reportResidual") for a in allocations]
    rows_full += [
        ["공시 비교 밖 날짜의 미귀속분", *[precise(a["outsideBridgeContributionToFullMean"]) for a in allocations]],
        ["원 전체 평균 재현", *[precise(h["baseline"]["netGross"]["netExcess"]["mean"]) for h in horizons]],
        ["공시 비교 주 / 전체 원 주", *[f"{a['bridgeN']} / {a['n']}" for a in allocations]],
    ]
    nvda = pair(horizons, "sensitivity", "scenarios", "noMaxTickerContribution")
    price = pair(horizons, "baseline", "yahooPaths", "yahooPriceOnlyExcess", "mean", render=precise)
    dividend = pair(horizons, "baseline", "yahooPaths", "yahooDistributionGap", "mean", render=precise)
    vendor = pair(horizons, "baseline", "yahooPaths", "grossMinusYahooAdjusted", "mean", render=precise)
    cost = pair(horizons, "baseline", "netGross", "costNetMinusGross", "mean", render=lambda x: f"{100*x:+.4f}")
    missing_share = " / ".join(f"{100*a['outsideBridgeContributionToFullMean']/h['baseline']['netGross']['netExcess']['mean']:.0f}%"
                               for a, h in zip(allocations, horizons, strict=True))
    wat = result.get("watTailDiagnostic")
    tail_note = []
    if wat:
        pre_gap = " / ".join(pct(result["ledgers"][c]["prefixBeforeAbnormalWATFill"]["cagrGap"])
                             for c in ("L26", "L52"))
        tail_note = [
            f"원 일별 장부의 마지막 {wat['weeks']}주에 WAT 목표 비중이 "
            f"{100*wat['weightRange']['min']:.2f}%~{100*wat['weightRange']['max']:.2f}%였다. "
            f"이 판단일은 두 고정보유 만기 표본에 들어오지 않았다. 이상 비중 적용 직전까지의 L26/L52 CAGR 차이는 "
            f"SPY 대비 {pre_gap}%p였다. [원 주식 수 필드와 NAV 점검](US-ko.md#리밸런싱-장부와-wat-행-감사)", "",
        ]
    return [
        "## 미국 · 원 복제 기준이 SPY를 앞선 이유", "",
        *table(cols, rows),
        "부분 공시 분해를 원 전체 평균의 분모에 맞춰 환산했다. 공시 밖 날짜의 실현 차이는 미귀속에 넣었다.", "",
        *table(["전체 평균에 대한 기여 (%p)", "6개월", "12개월"], rows_full),
        "**시총 대용치의 노출 차이와 종목 집중이 일부를 설명한다.** "
        f"잔차를 제외한 네 부분을 합하면 원 전체 평균에 {precise(four[0])} / {precise(four[1])}%p 기여했다. "
        f"원 평균 차이의 {missing_share}는 "
        f"공시 비교 밖 날짜에서 발생했다. 전체 날짜의 동일 종목 Yahoo 비교에서 분할 조정 가격만의 차이는 {price}%p였고, "
        f"분배 조정은 {dividend}%p, 봉인 가격 경로 차이는 {vendor}%p, 공통 비용은 {cost}%p를 더했다. "
        f"최대 기여 종목 NVDA의 기여를 제외한 뒤의 차이(%p)는 {nvda}이며 두 구간에 0이 포함된다. "
        "시차가 있는 부분 공시로 실제 SPY 구성 전체의 성과를 귀속하거나 일관된 별도 전략 우위를 확인하기는 어렵다. "
        "[가격 경로·공시 비중·연도별 기여](US-ko.md)", "",
        *tail_note,
    ]


def kr_headline(result):
    horizons = [result["horizons"][h] for h in HORIZONS]
    rows = paired_rows(horizons, [
        ("① 전체 통과 후보를 매칭에 투입 — 통과−미통과, 주식만", ("whole", "matched100", "selection")),
        ("① 같은 전체풀 매칭 — 통과−미통과, 주식 20%", ("whole", "matched20", "selection")),
        ("② 최대 5개 원 해시 — 통과−미통과, 주식 20%", ("k5", "paired", "selection")),
        ("② 같은 날 최대 5개의 선택 효과 − 전체풀 선택 효과", ("k5", "deltaSelectionVsWholeOnCommonDates")),
        ("② 고정 해시 9개 가용 시드 날짜별 평균 — 선택", ("seedAvailable", "selection")),
        ("③ 전체풀 매칭 — 미통과 20%−ETF 100%", ("whole", "matched20", "replacement")),
        ("③ 전체풀 매칭 — 통과 20%−ETF 100%", ("whole", "matched20", "total")),
        ("③ 원 해시와 매칭된 날짜 — 미통과 20%−ETF 100%", ("k5", "paired", "replacement")),
        ("③ 같은 날짜 — 통과 20%−ETF 100%", ("k5", "paired", "total")),
        ("③ 원 해시의 모든 수익 관측 날짜 — 통과 20%−ETF 100%", ("k5", "own", "total")),
        ("③ 모든 통과 종목 균등배분 20%−ETF 100%", ("whole", "allPass20", "total")),
    ])
    ranges = pair(horizons, "seedRange", "selection",
                  render=lambda s: f"{pct(s['low'])}~{pct(s['high'])}")
    non_semi = pair(horizons, "whole", "nonSemiLed", "selection")
    no_leaders = pair(horizons, "whole", "exLeadersDates", "selection")
    p = " / ".join(f"{result['holm6'][k]:.3f}"
                   for k in ("wholePassVsFail", "originalK5PassVsFail", "originalK5PassVsETF"))
    return ["## 한국 · 사업 확인 조건, 최대 5개, ETF 비교", "",
            *table(["한국 비용 차감 차이 (%p)", "6개월", "12개월"], rows),
            f"**필터의 양의 점추정은 남았고 ETF 대비 우위는 확인되지 않았다.** 시드별 유효 날짜의 선택 효과 범위는 {ranges}%p다. "
            f"9개가 모두 매칭된 날짜는 0주다. 6개월 Holm 보정 p값은 전체풀 선택, 원 해시 선택, 원 해시 ETF 대비 순으로 {p}였다. "
            f"전체풀에서 삼성전자·SK하이닉스가 등장한 쌍이 있는 주를 제외한 선택 효과(%p)는 {no_leaders}다. "
            f"기존 반도체 주도기를 제외하고 구분이 확인된 기간의 효과(%p)는 {non_semi}다. "
            "원 해시 장부의 짝비교는 6개월 60주, 12개월 53주이며 12개월은 블록 수가 부족해 구간을 산출하지 못했다. "
            "[매칭 범위·공통 날짜·시드별 결과](KR-ko.md)", ""]


def details():
    return [
        "## 재실행과 검증", "",
        "새 결과를 보기 전에 설계 문서를 커밋 47548b1에 고정했다. 6개월이 주 평가다. "
        "두 시장 모두 기존에 연구한 과거 표본을 재사용했다. 95% 구간은 원 주간축의 짝지은 이동블록 구간이다. "
        "블록 길이는 25/50주, 반복 수는 4,000회다. 주도주·주도기·최대 기여 연도 제외는 사후 진단이다. [설계](DESIGN-ko.md)", "",
        FENCE + "bash",
        "PYTHON=/workspace/s2-venv/bin/python bash research/kr_us_replica_filter_v1/reproduce.sh",
        "PYTHON=/workspace/s2-venv/bin/python bash research/kr_us_replica_filter_v1/reproduce.sh report",
        FENCE, "",
        "첫 명령은 미국과 한국을 병렬로 계산한다. 두 번째 명령은 저장된 결과로 보고서와 검산표를 다시 만든다. "
        "시장 하나만 재실행하려면 마지막 인수에 US 또는 KR을 지정한다.", "",
        "기존 전향 기록 6개 파일의 해시를 대조했다. 최신 입력과 기록 승인이 확인되지 않아 새 실거래 영수증은 0건이다. "
        "기존 preview 7건은 별도 경로에 있다. "
        "[전향 상태](results/prospective-status.json)", "",
        "[미국 세부 결과와 입력 범위](US-ko.md) · [한국 세부 결과와 입력 범위](KR-ko.md) · "
        "[전체 결과표](TABLES-ko.md) · [결과 검산](results/verification.json) · [실행·검증 상태](VALIDATION.md)",
    ]


def main():
    lines = [
        "# 미국 복제 기준 수익과 한국 사업 확인 필터", "",
        "기준은 PR #351 0eceb6f135dd3bd08f35950997d36129bfe67f65다. "
        "수익 차이는 %p, 대괄호는 명목 95% 구간, n은 같은 판단일에서 양쪽 결과가 관측된 주 수다.", "",
    ]
    for market, headline in (("US", us_headline), ("KR", kr_headline)):
        result = read(OUT / market / "summary.json")
        if result:
            lines.extend(headline(result))
        else:
            lines.extend([f"## {market}", "", "이 시장의 원본 결과 파일을 확보하지 못해 이번 실행에서 미측정이다.", ""])
    lines.extend(details())
    (HERE / "REPORT-ko.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
