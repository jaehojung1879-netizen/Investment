"""Render results/result.json into results/*.csv and the numeric tables used by REPORT-ko.md (tables only; prose is written by hand).

    python -m research.us_selection_value_v1.report
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
STRATS = ("PRICE", "SECTOR_MOMENTUM_BASKET", "WITHIN_SECTOR_VALUE", "CASH_PROFITABILITY", "VALUE_CONFIRMED", "PRICE_CONFIRMED", "B2_MULTIFACTOR")
KO = {"PRICE": "가격 신호(B1)", "SECTOR_MOMENTUM_BASKET": "업종 모멘텀 바스켓", "WITHIN_SECTOR_VALUE": "업종 내 가치", "CASH_PROFITABILITY": "현금수익성",
      "VALUE_CONFIRMED": "가치+사업 확인", "PRICE_CONFIRMED": "가격+사업 확인", "B2_MULTIFACTOR": "기존 다요인 B2"}
PERIODS = ("P1", "P2", "P3", "exclude2023Plus", "ALL")


def pct(v, d=2):
    return "—" if v is None else f"{v * 100:+.{d}f}"


def ci(v):
    return "—" if not v else f"[{v[0] * 100:+.1f}, {v[1] * 100:+.1f}]"


def main():
    r = json.loads((RES / "result.json").read_text())
    fh = r["fixedHolding"]
    rows = []
    for k, v in fh.items():
        s, b, H, p = k.split("|")
        rows.append({"strategy": s, "book": b, "H": H, "period": p, **{kk: (json.dumps(vv) if isinstance(vv, list) else vv) for kk, vv in v.items()}})
    keys = sorted({kk for x in rows for kk in x})
    with open(RES / "fixed-holding.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["strategy", "book", "H", "period"] + [k for k in keys if k not in ("strategy", "book", "H", "period")])
        w.writeheader()
        w.writerows(rows)
    nav_rows = []
    for k, v in r["nav"].items():
        s, b, p = k.split("|")
        nav_rows.append({"strategy": s, "book": b, "period": p, **{kk: vv for kk, vv in v.items() if kk != "yearly"}})
    with open(RES / "rebalancing-nav.csv", "w", newline="") as f:
        fields = sorted({kk for x in nav_rows for kk in x})
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(nav_rows)
    with open(RES / "year-sample.csv", "w", newline="") as f:
        fields = ["year"] + sorted({k for v in r["yearSample"].values() for k in v} | {"x_" + k for v in r["exclusionReasonsByYear"].values() for k in v})
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for y in sorted(set(r["yearSample"]) | set(r["exclusionReasonsByYear"])):
            w.writerow({"year": y, **r["yearSample"].get(y, {}), **{"x_" + k: v for k, v in r["exclusionReasonsByYear"].get(y, {}).items()}})
    out = []
    for b in ("TOP5", "TOP_QUINTILE"):
        for H in ("126", "252"):
            out.append(f"\n**{b} · H{H} — SPY 대비 순초과수익 평균(%p), 코호트 수**\n")
            out.append("| 전략 | 2013–19 | 2020–22 | 2023– | 2023 제외 | 전체 | 전체 구간(블록) | 승률 | QQQ 대비 |")
            out.append("|---|---:|---:|---:|---:|---:|---|---:|---:|")
            for s in STRATS:
                c = [fh.get(f"{s}|{b}|{H}|{p}", {}) for p in PERIODS]
                cells = [f"{pct(x.get('meanNetExcessSPY'))} ({x.get('cohorts', 0)})" for x in c]
                a = c[-1]
                out.append(f"| {KO[s]} | " + " | ".join(cells) + f" | {ci(a.get('ciMeanNetExcessSPY'))} | {pct(a.get('winRateSPY'), 0)} | {pct(a.get('meanNetExcessQQQ'))} |")
    out.append("\n**귀속(H126, 전체 기간, 평균 %p): SPY 대비 = 대형주·유니버스 + 업종 배분 + 업종 내 선택 + 비용 (+ 잔여 상호작용)**\n")
    out.append("| 전략 | 책 | 순초과 | 대형주·유니버스 | 업종 배분 | 업종 내 선택 | 비용 | 동업종·동규모 대비 선택 | 그 구간 |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for b in ("TOP5", "TOP_QUINTILE"):
        for s in STRATS:
            for p in ("ALL", "exclude2023Plus"):
                x = fh.get(f"{s}|{b}|126|{p}", {})
                if not x.get("cohorts"):
                    continue
                out.append(f"| {KO[s]}{' (2023 제외)' if p != 'ALL' else ''} | {b} | {pct(x['meanNetExcessSPY'])} | {pct(x['mean_largeCapAndUniverse'])} | "
                           f"{pct(x['mean_sectorAllocation'])} | {pct(x['mean_withinSectorSelection'])} | {pct(x['mean_costs'])} | "
                           f"{pct(x['mean_peerSelection'])} | {ci(x.get('ciMeanPeerSelection'))} |")
    # rebalancing NAV
    nav = r["nav"]
    out.append("\n**4계좌 리밸런싱 NAV (4주 보유, 계좌별 위상) — SPY 대비 CAGR 차이(%p) / IR / MDD(장부·SPY) / 편도 회전·연 비용**\n")
    out.append("| 전략 | 책 | 2013–19 | 2020–22 | 2023– | 2023 제외 | 전체 |")
    out.append("|---|---|---|---|---|---|---|")
    for b in ("TOP5", "TOP_QUINTILE"):
        for s in STRATS:
            if s == "SECTOR_MOMENTUM_BASKET" and b == "TOP_QUINTILE":
                continue
            cells = []
            for p in PERIODS:
                x = nav.get(f"{s}|{b}|{p}")
                if not x:
                    cells.append("—")
                elif "status" in x:
                    cells.append(x["status"])
                else:
                    cells.append(f"{pct(x['cagrMinusSpy'], 1)} / {x['infoRatio']:+.2f} / {x['mdd'] * 100:.0f}·{x['spyMdd'] * 100:.0f} / {x['oneWayTurnoverPerYear']:.1f}·{x['costPerYear'] * 100:.2f}")
            out.append(f"| {KO[s]} | {b} | " + " | ".join(cells) + " |")
    # paired price vs financial
    out.append("\n**가격 신호에 재무 정보를 더한 효과 — 양쪽 모두 계산된 같은 코호트의 짝 차이(SPY 대비 순초과, %p) [블록 95%] / 동업종·동규모 대비 선택 차이**\n")
    out.append("| 비교 | 책 | H | 2013–19 | 2020–22 | 2023– | 2023 제외 | 전체 |")
    out.append("|---|---|---|---|---|---|---|---|")
    pv = r["pairedPriceVsFinancial"]
    for lab in ("B2_MULTIFACTOR-PRICE", "PRICE_CONFIRMED-PRICE", "VALUE_CONFIRMED-WITHIN_SECTOR_VALUE"):
        for b in ("TOP5", "TOP_QUINTILE"):
            for H in ("126", "252"):
                cells = []
                for p in PERIODS:
                    x = pv.get(f"{lab}|{b}|{H}|{p}", {})
                    cells.append(f"{pct(x.get('meanDiffNetExcess'))} {ci(x.get('ci'))} / {pct(x.get('meanDiffPeerSelection'))}" if x.get("commonCohorts") else "—")
                out.append(f"| {lab} | {b} | {H} | " + " | ".join(cells) + " |")
    # Top-K control
    out.append("\n**대형주 집중 대조군 — 시총 대용 Top K (전체 가격 보유 구성원, 금융 포함), SPY 대비 순초과(%p), 코호트**\n")
    out.append("| H | 묶음 | 2013–19 | 2020–22 | 2023– | 2023 제외 | 전체 |")
    out.append("|---|---|---|---|---|---|---|")
    for H, d in r["topKControl"].items():
        for k in sorted(d, key=lambda z: (int(z.split("_")[0][3:]), z)):
            out.append(f"| {H} | {k} | " + " | ".join(f"{pct(d[k][p]['meanNetExcessSPY'])} ({d[k][p]['cohorts']})" if p in d[k] else "—" for p in PERIODS) + " |")
    # AI capex
    out.append("\n**AI CAPEX 조건부 가설 — 국면(지출 상위 10개사 capex 증가율 vs 과거 중앙값)별 SPY 대비 순초과(%p), 코호트**\n")
    out.append("| H | 바스켓 | 국면 | 2013–19 | 2020–22 | 2023– | 전체 |")
    out.append("|---|---|---|---|---|---|---|")
    for H, d in r["aiCapex"].items():
        for bk in ("spenders", "itProxy"):
            for reg in ("HIGH", "LOW"):
                cells = []
                for p in ("P1", "P2", "P3", "ALL"):
                    x = d.get(f"{bk}|{reg}|{p}")
                    cells.append(f"{pct(x['meanNetExcessSPY'])} ({x['cohorts']})" if x else "—")
                out.append(f"| {H} | {'투자 집행사 상위 10' if bk == 'spenders' else 'IT 업종(공급사 대용)'} | {reg} | " + " | ".join(cells) + " |")
    # dependence
    out.append("\n**의존도 — 상위 기여 5종목 제외 시 평균, 한 해 제외 시 부호가 뒤집히는 신호 연도, 결측 코호트를 관측 최악/최선으로 채운 범위 (H126, %p)**\n")
    out.append("| 전략 | 책 | 평균 | 상위5 제외 | 상위 기여 종목 | 부호 뒤집는 연도 | 결측 코호트 | 최악~최선 |")
    out.append("|---|---|---:|---:|---|---|---:|---|")
    for b in ("TOP5", "TOP_QUINTILE"):
        for s in STRATS:
            d = r["dependence"].get(f"{s}|{b}|126")
            m = r["missingCohortBounds"].get(f"{s}|{b}|126")
            if not d:
                continue
            out.append(f"| {KO[s]} | {b} | {pct(d['mean'])} | {pct(d['meanWithoutTopContributors'])} | {', '.join(d['topContributors'])} | "
                       f"{', '.join(d['yearsWhoseRemovalFlipsSign']) or '없음'} | {m['missingCohorts']} | {pct(m['worstFill'])} ~ {pct(m['bestFill'])} |")
    # year sample
    out.append("\n**연도별 표본 — 신호 주차, 30종목 이상 적격 주차, 공통 유니버스 평균 종목 수, 주당 주요 제외 사유**\n")
    out.append("| 연도 | 신호 주 | 적격 주 | 공통 유니버스 평균 | 가격 패널 없음(이탈 종목)/주 | CIK 모호/주 | 회계 불완전·기타 |")
    out.append("|---|---:|---:|---:|---:|---:|---|")
    for y, c in sorted(r["yearSample"].items()):
        x = r["exclusionReasonsByYear"].get(y, {})
        w = c.get("signalWeeks", 1)
        out.append(f"| {y} | {w} | {c.get('eligibleWeeks', 0)} | {c.get('commonUniverseRows', 0) / w:.0f} | {x.get('NO_PRICE_PANEL', 0) / w:.0f} | "
                   f"{x.get('CIK_AMBIGUOUS_EXCLUDED', 0) / w:.0f} | identity hold {x.get('IDENTITY_HOLD', 0) / w:.0f} |")
    (RES / "tables-ko.md").write_text("\n".join(out) + "\n")
    print("ok")


if __name__ == "__main__":
    main()
