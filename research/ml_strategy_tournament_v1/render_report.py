"""Render results/*.json into tables for the Korean report (results/tables-ko.md). Every number comes from a result file; nothing is recomputed.

    python research/ml_strategy_tournament_v1/render_report.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"


def pct(x, d=2):
    return "–" if x is None else f"{x * 100:.{d}f}%"


def num(x, d=2):
    return "–" if x is None else f"{x:.{d}f}"


def load(name):
    p = RES / name
    return json.loads(p.read_text()) if p.exists() else None


def table(rows, cols):
    head = "| " + " | ".join(c[0] for c in cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    return head + "".join("| " + " | ".join(c[1](r) for c in cols) + " |\n" for r in rows)


def ranking_section(view):
    rk = load(f"rankings-{view}.json")
    if rk is None:
        return ""
    cols = [("순위", lambda r: str(int(r["rankAbs"]))), ("전략", lambda r: f"`{r['strategy']}`"), ("CAGR", lambda r: pct(r["cagr"])),
            ("ETF 대비", lambda r: pct(r["excessCagr"])), ("Sharpe", lambda r: num(r["sharpe"])), ("IR", lambda r: num(r["informationRatio"])),
            ("변동성", lambda r: pct(r["vol"], 1)), ("TE", lambda r: pct(r["trackingError"], 1)), ("MDD", lambda r: pct(r["mdd"], 1)),
            ("연 회전율", lambda r: num(r["annualStockTurnover"])), ("평균 종목수", lambda r: num(r["meanNamesHeld"])),
            ("종결 상한 CAGR", lambda r: pct(r["cagrUpperBoundTerminalAtLastClose"]))]
    stab = [("안정성 순위", lambda r: str(int(r["rankStability"]))), ("전략", lambda r: f"`{r['strategy']}`"), ("CAGR", lambda r: pct(r["cagr"])),
            ("ETF 대비", lambda r: pct(r["excessCagr"])), ("초과>0 연도", lambda r: pct(r["positiveExcessYearShare"], 0)),
            ("전·후반 최소 초과", lambda r: pct(r["minHalfExcessCagr"])), ("252일 창 초과>0", lambda r: pct(r["rolling252PositiveShare"], 0)),
            ("상위5종목 제외 초과", lambda r: pct(r["excessCagrExTop5Names"])), ("상위5 기여 비중", lambda r: pct(r["top5ShareOfStockContribution"], 0))]
    out = f"### {view}: 절대수익 TOP 10\n\n" + table(rk["absoluteTop10"], cols)
    out += f"\n### {view}: 위험조정(Sharpe) TOP 10\n\n" + table(rk["riskAdjustedTop10"], [("Sharpe 순위", lambda r: str(int(r["rankRisk"])))] + cols[1:])
    out += f"\n### {view}: 안정성 TOP 10\n\n" + table(rk["stabilityTop10"], stab)
    out += f"\n### {view}: 규칙 기준선\n\n" + table(rk["ruleBaselines"], [("전략", lambda r: f"`{r['strategy']}`"), ("CAGR", lambda r: pct(r["cagr"])),
                                                                     ("ETF 대비", lambda r: pct(r["excessCagr"])), ("Sharpe", lambda r: num(r["sharpe"])),
                                                                     ("MDD", lambda r: pct(r["mdd"], 1)), ("절대순위", lambda r: str(int(r["rankAbs"])))])
    return out


def winner_section(view):
    w = load(f"winner-analysis-{view}.json")
    o = load(f"overfit-diagnostics-{view}.json")
    if w is None:
        return ""
    a = w["anatomy"]
    out = f"### {view}: 대상 `{a['winner']}` (절대순위 {w.get('subjectRankAbs')}) 연도별\n\n"
    out += table([{"y": y, **v} for y, v in a["yearly"].items()], [("연도", lambda r: r["y"]), ("전략", lambda r: pct(r["ret"])),
                                                                  ("ETF", lambda r: pct(r["etf"])), ("초과", lambda r: pct(r["excess"]))])
    c = a["contributions"]
    out += "\n상위 기여 종목(일별 비중×수익률 합, NAV 단위):\n\n" + table(c["byName"][:10], [("종목", lambda r: r["ticker"]), ("업종", lambda r: str(r["industry"])),
                                                                                  ("기여", lambda r: num(r["contribution"], 4))])
    out += "\n하위 기여 종목:\n\n" + table(c["byName"][-5:], [("종목", lambda r: r["ticker"]), ("업종", lambda r: str(r["industry"])),
                                                       ("기여", lambda r: num(r["contribution"], 4))])
    out += "\n종목 제외 재실행:\n\n" + table([{"k": k, **v} for k, v in a["leaveNamesOut"].items()],
                                         [("제외", lambda r: r["k"]), ("CAGR", lambda r: pct(r["cagr"])), ("ETF 대비", lambda r: pct(r["excessCagr"]))])
    out += "\n집중도·비용 민감도:\n\n" + table([{"k": k, **v} for k, v in a["concentrationAndCostSensitivity"].items()],
                                          [("구현", lambda r: r["k"]), ("CAGR", lambda r: pct(r["cagr"])), ("ETF 대비", lambda r: pct(r["excessCagr"]))])
    if "familyAblation" in a:
        out += "\n특성군 제거(전 fold 재학습):\n\n" + table([{"k": k, **v} for k, v in a["familyAblation"].items()],
                                                  [("제거", lambda r: r["k"]), ("제거 특성 수", lambda r: str(r["featuresDropped"])), ("CAGR", lambda r: pct(r["cagr"])),
                                                   ("ETF 대비", lambda r: pct(r["excessCagr"])), ("OOS IC", lambda r: num(r["oosRankIc"], 4))])
        lc = a["linearCounterpart"]
        out += (f"\n선형 대응 `{lc['strategy']}`: CAGR {pct(lc['cagr'])}, ETF 대비 {pct(lc['excessCagr'])}; 우승−선형 연환산 차이 "
                f"{pct(lc['winnerMinusLinear']['annualisedMeanDiff'])}, 95% 블록부트스트랩 [{pct(lc['winnerMinusLinear']['ci95'][0])}, {pct(lc['winnerMinusLinear']['ci95'][1])}]\n")
    if o:
        ds = o["deflatedSharpeWinnerAbsolute"]
        out += "\n과최적화 진단:\n\n"
        out += (f"- 전략 {o['trials']['strategies']}개, 실제 적합 {o['trials']['fitsPerformed']}회, ETF와 완전히 같은 경로 {o['trials']['strategiesIdenticalToEtf']}개; "
                f"ETF 대비 초과수익 기준 유효 전략 수: 고유값 참여비 {num(o['trials']['onExcessReturns']['participationRatio'], 1)}, "
                f"|ρ|≥0.9 군집 {o['trials']['onExcessReturns']['clustersAtCorr0.9']}\n")
        out += "- Deflated Sharpe(절대수익): " + ", ".join(f"{k} {num(v['deflatedSharpeProbability'], 3)} (기대최대 SR {num(v['expectedMaxSharpeUnderNullAnnual'])})"
                                                          for k, v in ds.items()) + "\n"
        dx = o["deflatedSharpeWinnerExcessVsEtf"]
        out += "- Deflated Sharpe(ETF 대비 초과): " + ", ".join(f"{k} {num(v['deflatedSharpeProbability'], 3)}" for k, v in dx.items()) + "\n"
        p = o["cscvPbo"]
        out += f"- CSCV PBO {num(p['pbo'], 3)} ({p['combinations']}조합, IS→OOS 기울기 {num(p['isToOosSlope'], 3)})\n"
        for k, v in o["blockBootstrap"].items():
            out += f"- {k}: 연환산 {pct(v['annualisedMeanDiff'])}, 95% CI [{pct(v['ci95'][0])}, {pct(v['ci95'][1])}], ≤0 비율 {num(v['shareBootstrapAtOrBelowZero'], 3)}\n"
        for k, v in o["nestedSelection"].items():
            out += (f"- 과거만 보고 매년 토너먼트 1위를 고른 전략({k}): CAGR {pct(v['metrics']['cagr'])}, ETF 대비 {pct(v['metrics']['excessCagr'])}, "
                    f"MDD {pct(v['metrics']['mdd'], 1)}, 서로 다른 선택 {v['distinctPicks']}개\n")
        f = o["factorRegressionWinner"]
        out += f"- 규칙 기준선 회귀 알파 연 {pct(f['annualisedAlpha'])} (t={num(f['alphaT'])}, R²={num(f['r2'], 3)})\n"
    return out


def main():
    parts = ["# ml-strategy-tournament-v1 결과 표 (자동 생성)\n\n증거 등급: EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY\n"]
    for view in ("gated", "forced"):
        parts.append(f"\n## 보기: {view}\n\n" + ranking_section(view) + "\n" + winner_section(view))
        for p in sorted(RES.glob(f"winner-analysis-{view}-*.json")):
            parts.append(f"\n## 보기: {view} — 최우수 ML 해부\n\n" + winner_section(p.stem.replace("winner-analysis-", "")))
    (RES / "tables-ko.md").write_text("\n".join(parts))


if __name__ == "__main__":
    main()
