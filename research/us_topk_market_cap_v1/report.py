"""Aggregate-only Korean report, CSVs and research figures; no raw prices."""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import csv
import hashlib
import json

import numpy as np

from research.us_topk_market_cap_v1.inputs import read, write


def table(headers, rows):
    return "\n".join(["| " + " | ".join(map(str, headers)) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |",
                      *["| " + " | ".join(map(str, row)) + " |" for row in rows]])


def pct(value, signed=True):
    if value is None:
        return "미측정"
    return f"{value * 100:+.2f}" if signed else f"{value * 100:.1f}"


def csv_file(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()} for row in rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--market-private", type=Path, required=True)
    ap.add_argument("--corrected-results", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    private, out = args.private, args.output
    ranks = read(private / "rankings.json.gz")
    cohorts = read(private / "performance-cohorts.json.gz")
    summaries = read(out / "performance-summary.json")
    nav = read(out / "nav-segments.json")
    main_rows = [r for r in summaries if r["signal_year"] == "ALL"]
    control = read(private / "financial-control-cohorts.json.gz")
    controls = {(r["signal"], r["horizon"]): r for r in control if r["status"] == "COMPLETE"}
    paired = []
    for row in main_rows:
        observations = [r for r in cohorts if r["k"] == row["k"] and r["weighting"] == row["weighting"]
                        and r["horizon"] == row["horizon"] and r["status"] == "COMPLETE"
                        and (r["signal"], r["horizon"]) in controls]
        top = [r["excess"] for r in observations]
        b2 = [controls[r["signal"], r["horizon"]]["excess"] for r in observations]
        paired.append({"k": row["k"], "weighting": row["weighting"], "horizon": row["horizon"],
                       "same_date_complete_cohorts": len(top),
                       "topk_mean_excess": float(np.mean(top)) if top else None,
                       "b2_mean_excess": float(np.mean(b2)) if b2 else None,
                       "mean_topk_minus_b2": float(np.mean(np.array(top) - b2)) if top else None,
                       "note": "Corrected financial pool only; B2 is its own existing top-quintile rule, not a full-index selector"})
    write(out / "financial-control-paired.json", paired)
    concentrations = []
    all_concentrations = read(out / "concentration.json")
    for row in main_rows:
        valid_dates = {r["signal"] for r in cohorts if r["k"] == row["k"] and r["weighting"] == row["weighting"]
                       and r["horizon"] == row["horizon"] and r["status"] == "COMPLETE"}
        source = [r for r in all_concentrations if r["k"] == row["k"] and r["weighting"] == row["weighting"] and r["signal"] in valid_dates]
        unique = {s["cik"] for r in ranks if r["k"] == row["k"] and r["pool"] == row["pool"]
                  and r["signal"] in valid_dates for s in r["selected"]}
        numeric = ["company_top1", "company_top5", "company_hhi", "company_effective_n", "sector_top1", "sector_hhi", "sector_effective_n"]
        means = {"mean_" + k: float(np.mean([r[k] for r in source])) for k in numeric}
        sector_values = defaultdict(list)
        all_sectors = {s for r in source for s in r["sector_weights"]}
        for r in source:
            for s in all_sectors:
                sector_values[s].append(r["sector_weights"].get(s, 0.))
        sectors = {s: float(np.mean(v)) for s, v in sector_values.items()}
        concentrations.append({"k": row["k"], "weighting": row["weighting"], "horizon": row["horizon"],
                               "complete_cohorts": len(source), "distinct_companies": len(unique), **means,
                               "largest_mean_sector": max(sectors, key=sectors.get),
                               "mean_sector_weights": sectors})
    write(out / "concentration-summary.json", concentrations)
    years = sorted({r["signal"][:4] for r in ranks})
    annual = []
    for year in years:
        grid = {r["signal"] for r in ranks if r["signal"].startswith(year) and r["pool"] == "OBSERVED_SP500_SNAPSHOT"}
        for pool in ("OBSERVED_SP500_SNAPSHOT", "CORRECTED_FINANCIAL_POOL"):
            for k in (5, 10, 100):
                rows = [r for r in ranks if r["signal"].startswith(year) and r["pool"] == pool and r["k"] == k]
                for h in (126, 252):
                    observations = [r for r in cohorts if r["signal"].startswith(year) and r["pool"] == pool
                                    and r["k"] == k and r["horizon"] == h and r["weighting"] == "equal_company"]
                    annual.append({"year": year, "pool": pool, "k": k, "horizon": h,
                        "weekly_grid_denominator": len(grid), "pool_weeks": len(rows),
                        "official_float_rank_verified_weeks": 0,
                        "reported_total_cap_rank_verified_weeks": sum(r["status"].startswith("VERIFIED") for r in rows),
                        "rank_uncertain_weeks": sum(r["status"].startswith("BOUNDARY") for r in rows),
                        "pool_has_fewer_than_k_weeks": sum(r["status"].startswith("FEWER") for r in rows),
                        "mature_verified_rank_cohorts": sum(r["end"] <= "2026-11-13" for r in observations),
                        "complete_portfolio_cohorts": sum(r["status"] == "COMPLETE" for r in observations),
                        "mature_selected_path_failures": sum(r["end"] <= "2026-11-13" and r["status"] != "COMPLETE" for r in observations)})
    csv_file(out / "annual-rank-and-return-coverage.csv", annual)
    csv_file(out / "fixed-holding-performance.csv", summaries)
    csv_file(out / "financial-control-paired.csv", paired)
    csv_file(out / "concentration-summary.csv", concentrations)
    gap_groups = defaultdict(list)
    for r in read(private / "ranking-missingness.json.gz"):
        gap_groups[r["pool"], r["ticker"], r["reason"]].append(r["signal"])
    gap_ranges = [{"pool": p, "ticker": t, "missing_field_or_reason": reason, "from_signal": min(days),
                   "through_signal": max(days), "affected_signal_dates": len(set(days)),
                   "sources_checked": "Pinned membership/sector CIK; original as-traded reconstruction; corrected raw-close cache; SEC companyfacts and collected original class filings",
                   "scope": "Envelope; exact nonconsecutive signal dates retained in private ranking-missingness.json.gz"}
                  for (p, t, reason), days in sorted(gap_groups.items())]
    csv_file(out / "remaining-rank-gaps.csv", gap_ranges)
    effects = read(args.corrected_results / "sec-asset-input-effects.json")
    old_conflicts = {tuple(r) for r in read(args.market_private / "repaired-input-eligible-cohorts.json")["accounting_issuer_conflicts"]}
    rank_dates = {r["signal"] for r in cohorts if r["status"] == "COMPLETE"}
    selected_rows = [s for r in ranks if r["pool"] == "CORRECTED_FINANCIAL_POOL" and r["signal"] in rank_dates
                     and r["k"] == 100 for s in r["selected"]]
    correction = {
        "old_para_corrected_paths_per_horizon": 103,
        "para_in_complete_top100_security_signal_pairs": sum(s["ticker"] == "PARA" for s in selected_rows),
        "old_mixed_issuer_pairs_removed_from_corrected_financial_pool_per_horizon": len(old_conflicts),
        "mixed_issuer_pairs_in_selected_verified_topk": sum((r["signal"], s["ticker"]) in old_conflicts
            for r in ranks if r["status"].startswith("VERIFIED") for s in r["selected"]),
        "sec_asset_source_records_applied": effects["sec_same_accession_records_applied"],
        "sec_asset_eligible_added": len(effects["eligible_added_by_sec"]),
        "sec_asset_factor_vectors_changed": len(effects["existing_complete_factor_vectors_changed_by_sec"]),
        "cap_rank_uses_accounting_assets": False,
        "b2_control_para_security_signal_pairs": sum("PARA" in r["selected"] for r in read(private / "financial-control-ranks.json.gz")),
        "b2_mature_failure_names": {str(h): dict(Counter(t for r in control if r["horizon"] == h and r["end"] <= "2026-11-13"
                                                        for t in r["failed_names"])) for h in (126, 252)},
        "b2_mature_failure_reasons": {str(h): dict(Counter(reason for r in control if r["horizon"] == h and r["end"] <= "2026-11-13"
                                                          for reason in r["failed_names"].values())) for h in (126, 252)},
    }
    write(out / "correction-effects-on-topk.json", correction)
    weighting_pairs = []
    for h in (126, 252):
        for k in (5, 10, 100):
            ew = {(r["signal"]): r for r in cohorts if r["k"] == k and r["horizon"] == h and r["weighting"] == "equal_company" and r["status"] == "COMPLETE"}
            cw = {(r["signal"]): r for r in cohorts if r["k"] == k and r["horizon"] == h and r["weighting"] == "company_market_cap" and r["status"] == "COMPLETE"}
            assert ew.keys() == cw.keys()
            diffs = [ew[d]["excess"] - cw[d]["excess"] for d in sorted(ew)]
            weighting_pairs.append({"horizon": h, "k": k, "same_rank_same_dates": len(diffs),
                "mean_equal_minus_cap_excess": float(np.mean(diffs)), "median_equal_minus_cap_excess": float(np.median(diffs))})
    write(out / "weighting-paired-comparison.json", weighting_pairs)
    facts_receipts = read(private / "sec-companyfacts-receipts.json")
    additional = read(private / "extension-companyfacts-receipts.json")
    class_docs = read(private / "sec-class-filings.json")
    extension = read(out / "historical-extension-annual.json")
    samples = read(out / "historical-extension-sample-checks.json")
    verified_quotes = sum(r.get("quote_agrees_within_0_1pct", 0) for r in samples)
    checked_quotes = sum(r.get("quote_comparisons", 0) for r in samples)
    text = ["# 미국 Top 100·10·5 성과 및 과거 확장 점검", "",
        "**전체 S&P 500의 검증된 Top K 성과는 아직 0주다. 아래 수익은 기존 정정 재무 풀의 총시총 추정 Top K다.** 신호 2023-04-14~2025-03-07의 성숙 100주에서 계산했다. 금융·부동산과 네 재무 요인의 배제를 주 실험에 적용하지 않았으며, 주 실험은 미검증 순위 때문에 보류했다. 별도 재무 풀은 기존 입력의 제약을 그대로 표시했다.", "",
        "main 기준 `4f4497bcc9e7f9369bf5529225585ad39b0d7725`, 독립 worktree. 연구 결과는 이미 노출된 입력을 재사용한 탐색적 기술통계이며 새로운 표본외 검증 또는 투자 가능성 주장이 아니다. 원본·키·공용 원장·봉인 결과·main·화면·writer를 변경하지 않았다.", "",
        "## 첫 성과표", "", "SPY 달러 총수익 대비 비용 차감 초과수익. 평균·중앙값·하위 10%는 %p, 승률은 %. 연율화하지 않았다. 동일 K의 두 가중 방식은 같은 회사 순위·날짜·증권을 쓴다.", "",
        table(["K", "기간", "가중", "성숙/완전", "평균", "중앙값", "승률", "하위 10%"],
            [[r["k"], "H" + str(r["horizon"]), "시총" if r["weighting"] == "company_market_cap" else "동일",
              f"{r['mature_denominator']}/{r['complete_cohorts']}", pct(r["mean_excess"]), pct(r["median_excess"]),
              pct(r["win_rate"], False), pct(r["p10_excess"])] for r in sorted(main_rows, key=lambda r: (-r["k"], r["horizon"], r["weighting"]))]), "",
        "Top 100의 동일가중은 두 기간 모두 SPY를 밑돌았다. 이 표본에서는 집중한 Top 5·10과 시총가중의 평균이 더 높았다. 재무 풀에 조건부인 결과로 전체 지수 선정 효과를 입증하지 않는다.", "",
        "## 계산 전에 고정한 규칙", "",
        "회사 CIK로 합치고 복수 클래스 회사를 한 번만 순위에 넣는다. 보유 증권은 당시 지수 편입 클래스 중 사전순 첫 심볼이다. Alphabet은 A/B와 C의 가격을 구분하고 B를 A 1주로 환산한다. Berkshire A는 B 1,500주, Erie B는 A 150주의 경제적 권리 기준이다. 미상장 클래스의 경제적 동등 가격은 추정이며 실제 거래가격 또는 유동시총이 아니다. Up-C LLC 권리 연결이 불명확한 TKO·CVNA·IBKR은 순위 공백으로 남긴다.", "",
        "시총은 신호일보다 앞서 공개된 실제 보통주 발행주식 수와 신호일의 분할 전후가 일치하는 실제 종가를 사용한다. EPS 가중평균 주식 수를 쓰지 않는다. 주식 수는 최근 과거 측정을 이월하며 550일을 넘으면 공백이다. 차후 공시나 재작성으로 과거 숫자를 덮지 않고 최초 공개를 보존한다. 이 방법은 `보고 주식 수 기반 총시총 추정`으로, 지수 IWF를 반영한 유동시총과 다르다.", "",
        "완결 주의 마지막 미국 거래일이 신호일, 다음 거래일 종가가 체결일이다. H126/H252의 청산은 체결일 인덱스+126/+252 종가이며 성숙 기준일은 2026-11-13이다. 매수 8bp, 매도 8.3bp를 자기자본에서 지급한다. 계약상 현금으로 끝난 몫에 가상의 재매도 비용을 붙이지 않는다. 현금은 무이자이며 총수익 가격에 배당을 다시 더하지 않는다. 단주·권리·후속 주식 대가가 미확인이면 해당 보유를 실패로 남기고 대체하지 않는다.", "",
        "`rank-freeze-receipt.json`은 모든 후보 시총·선정 회사/증권의 비공개 파일 해시를 성과 접근 전에 기록했다. 원본 시세의 과거 구간을 짧은 후속 가격 창이 지우지 않도록 입력 로더를 바로잡고, 점/하이픈 클래스 표기를 연결한 뒤 최종 순위를 다시 봉인했다. 이 수정은 첫 성과 접근 전이었다. 성과 검산에서 마지막 검증 신호의 다음 리밸런싱 직전까지 NAV를 표시하고 계약상 현금의 불필요한 매도 비용을 제거했다. 순위·표본·비용률·가중 규칙은 바꾸지 않았다.", "",
        "## 연도별 유효 구간", "",
        table(["신호 연도", "전체 주차", "정정 풀 주차", "Top 5/10 검증 순위", "성숙 완전 H126/H252", "Top 100 성숙 완전"],
            [[year,
              next(r["weekly_grid_denominator"] for r in annual if r["year"] == year),
              next(r["pool_weeks"] for r in annual if r["year"] == year and r["pool"] == "CORRECTED_FINANCIAL_POOL"),
              next(r["reported_total_cap_rank_verified_weeks"] for r in annual if r["year"] == year and r["pool"] == "CORRECTED_FINANCIAL_POOL" and r["k"] == 5),
              "/".join(str(next(r["complete_portfolio_cohorts"] for r in annual if r["year"] == year and r["pool"] == "CORRECTED_FINANCIAL_POOL" and r["k"] == 5 and r["horizon"] == h)) for h in (126, 252)),
              "/".join(str(next(r["complete_portfolio_cohorts"] for r in annual if r["year"] == year and r["pool"] == "CORRECTED_FINANCIAL_POOL" and r["k"] == 100 and r["horizon"] == h)) for h in (126, 252))]
             for year in ["2023", "2024", "2025", "2026"]]), "",
        "2013~2022년은 모든 K에서 검증 성과 주차 0이다. 2025년은 1~3월의 10주만 비교할 수 있고, 2026년의 검증 순위는 아직 두 보유기간 모두 성숙하지 않았다. 연간 성과표의 2023·2025년은 연도 전체를 대표하지 않는다. 기존 재무 풀의 모든 보유가 완전한 133주(H126)·67주(H252)는 별도 검산값이며 이 Top K의 분모나 날짜 필터가 아니다.", "",
        "연도별 평균 초과수익(%p):", "",
        table(["신호 연도", "K", "기간", "시총 평균", "동일 평균", "각 완전 주차"],
          [[y, k, "H" + str(h),
            pct(next(r["mean_excess"] for r in summaries if r["signal_year"] == y and r["k"] == k and r["horizon"] == h and r["weighting"] == "company_market_cap")),
            pct(next(r["mean_excess"] for r in summaries if r["signal_year"] == y and r["k"] == k and r["horizon"] == h and r["weighting"] == "equal_company")),
            next(r["complete_cohorts"] for r in summaries if r["signal_year"] == y and r["k"] == k and r["horizon"] == h and r["weighting"] == "equal_company")]
           for y in ["2023", "2024", "2025"] for k in (100, 10, 5) for h in (126, 252)]), "",
        "## 보유 중복과 리밸런싱 NAV", "",
        "100개 주간 코호트는 서로 독립인 100번의 실험이 아니다. 보유 구간이 겹치지 않는 탐욕적 간격 수는 H126 4개, H252 2개다. 연속 구간 내 이동 블록 길이 26·51주, 2,000회·고정 시드로 평균의 탐색적 구간을 계산했다. 연도별 짧은 구간은 미측정이며 IID t 검정이나 표본외 우월성 주장을 하지 않는다. 블록 구간과 유효 연속 길이는 성과 CSV에 있다.", "",
        "주간 리밸런싱 NAV는 각 주에 새 목표 비중으로 거래하는 별도 전략이다. 위 H126/H252 표는 각 진입 주의 종목·비중을 고정한 보유 수익이다. NAV의 공백은 이어 붙이지 않으며 마지막 평가 시점은 데이터 검증 구간의 우측 절단이다.", "",
        table(["K", "가중", "시작~마지막 평가", "주간 구간", "NAV 수익 %", "SPY %", "일별 MDD %", "양방향 회전"],
          [[r["k"], "시총" if r["weighting"] == "company_market_cap" else "동일", s["first_entry"] + "~" + s["last_mark"],
            s["intervals"], pct(s["return_before_hypothetical_end_sell"]), pct(s["spy_return_before_end_sell"]),
            pct(s["daily_mdd"]), f"{s['turnover']:.3f}"]
           for r in nav if r["pool"] == "CORRECTED_FINANCIAL_POOL" for s in r["segments"]]), "",
        "NAV는 마지막 관측 종가로 표시한 평가금액이며 임의 청산을 실행하지 않았다. 매수·중간 거래 비용은 포함하고, 말일 가정 청산을 적용한 비교는 별도 JSON 필드에 있다. 2026년 8월의 2주짜리 구간은 긴 구간과 합산하지 않는다.", "",
        "![정정 재무 풀의 연속 검증 구간 NAV](nav-main-segment.png)", "",
        "## 종목·업종 집중도", "",
        table(["K", "가중", "서로 다른 회사", "평균 최대 회사 %", "상위5 회사 %", "회사 유효 수", "최대 업종", "업종 비중 %"],
          [[r["k"], "시총" if r["weighting"] == "company_market_cap" else "동일", r["distinct_companies"], pct(r["mean_company_top1"], False),
            pct(r["mean_company_top5"], False), f"{r['mean_company_effective_n']:.2f}", r["largest_mean_sector"],
            pct(r["mean_sector_weights"][r["largest_mean_sector"]], False)] for r in concentrations if r["horizon"] == 126]), "",
        "업종은 당시 구성 스냅숏의 분류를 사용했다. 세부 HHI·업종 유효 수·평균 업종 비중은 `concentration-summary.csv`에 있다. 금융·부동산이 없는 것은 이 보조 풀의 기존 정의이며, 주 실험의 제외 조건으로 사용하지 않았다.", "",
        "## 기존 재무 점수 대조", "",
        "기존 `P.scores`의 가격/현금/발생/투자/레버리지 다섯 계열을 같은 비중으로 합치는 B2 규칙과 상위 ceil(N/5) 동일가중 규칙을 정정 단일 CIK 풀에서 재현했다. 동일 날짜의 공통 완전 보유만 짝지었다. 이것은 기존 재무 점수 대조이며 Top K와 동일한 종목 수를 강요한 새 규칙이 아니다.", "",
        table(["K", "기간", "가중", "공통 주차", "Top K 평균 %p", "B2 평균 %p", "차이 %p"],
          [[r["k"], "H" + str(r["horizon"]), "시총" if r["weighting"] == "company_market_cap" else "동일",
            r["same_date_complete_cohorts"], pct(r["topk_mean_excess"]), pct(r["b2_mean_excess"]), pct(r["mean_topk_minus_b2"])] for r in paired]), "",
        f"B2의 성숙 100주 중 H126은 {sum(r['status']=='COMPLETE' for r in control if r['horizon']==126)}주, H252는 {sum(r['status']=='COMPLETE' for r in control if r['horizon']==252)}주가 완전했다. 실패 종목/사유: `{json.dumps(correction['b2_mature_failure_names'], ensure_ascii=False)}`, `{json.dumps(correction['b2_mature_failure_reasons'], ensure_ascii=False)}`. 실패 날짜에서 다른 종목으로 교체하지 않았다.", "",
        "## 정정 내용이 이번 집계에 준 영향", "",
        f"PARA의 기존 103개 보유 경로 정정은 보존했다. 이번 완전 Top 100의 PARA 증권·신호 쌍은 {correction['para_in_complete_top100_security_signal_pairs']}개이며 B2 대조에는 {correction['b2_control_para_security_signal_pairs']}개가 선택됐다. 원래 혼합 CIK 171개 쌍은 정정 재무 풀에서 순위 전에 제거됐고 이번 검증 Top K 선정에는 0개다. 주 실험의 SEC 시총 입력에는 기존 네 재무 요인 조건을 적용하지 않았다.", "",
        f"SEC 총자산 {correction['sec_asset_source_records_applied']}건의 동일 accession 보충을 재사용했다. 기존 검산에서 적격 쌍 추가 {correction['sec_asset_eligible_added']}개, 완전 재무 벡터 변화 {correction['sec_asset_factor_vectors_changed']}개였다. 시총 식에는 총자산이 없으므로 이번 Top K 순위·가중·성과에 직접 반영된 변화는 0개다. 이번 Top K의 성숙 보유에서는 가격·단주·WBA 권리로 실패한 날짜가 0개다. B2 대조의 실제 실패는 MRO 단주 H126 26주·H252 39주이며, WBA는 이번 대조 실패에 포함되지 않았다. 기존의 미해결 권리 공백은 보존하고 0 또는 마지막 종가로 채우지 않았다.", "",
        "## 2018·2020·2022년 확장: 실제 확보와 남은 경계", "",
        f"SEC companyfacts {sum(r['status']==200 for r in facts_receipts)}개 발행사와 클래스 원본 공시 {sum(r['status']==200 for r in class_docs)}건을 수집했다. 과거 후보 발행사 {sum(r['status']==200 for r in additional)}개를 추가했다. SPY 공식 공시 10건은 2018년 2건, 2020년 4건, 2022년 4건이다. 2020·2022 XML 8건은 기존 SHA-256과 일치했다. 2018 HTML 2건은 기존 해시와 다르므로 새 취득본으로 구분하고 각각 505·506개 보통주와 합계를 다시 읽었다. 이전 바이트와 같은 원본이라고 주장하지 않는다.", "",
        table(["연도", "신호 주차", "평균 구성 증권", "CIK 후보", "당시 종가", "후보+주식수+종가", "검증 Top5/10/100"],
          [[r["year"], r["signal_weeks"], f"{r['mean_member_count']:.1f}", f"{r['mean_candidate_cik_count']:.1f}",
            f"{r['mean_raw_quote_count']:.1f}", f"{r['mean_joint_candidate_share_quote_count']:.1f}", "0 / 0 / 0"] for r in extension if r["k"] == 5]), "",
        f"SPY 보유 가치/수량의 암묵 종가를 원 캐시의 실제 종가와 {checked_quotes}건 대조해 {verified_quotes}건이 0.1% 이내였다. 불일치는 `historical-extension-quote-discrepancies.json`에 남겼다. 이는 가격 기준의 독립 검산이며 해당 회사의 전체 발행주식 수나 IWF를 제공하지 않는다. XML의 CUSIP/LEI는 후속 증권 연결의 재사용 가능한 근거지만 현재 이름 후보를 당시 증권으로 자동 승인하지 않았다.", "",
        "ETF 보유가치 순서의 K 경계 ±2회사도 실제로 점검했다. 이 순서는 회사 시총 순위가 아니며, 전향 순위나 과거 성과에 넣지 않았다. 경계별 누락 필드와 확보 개수는 `historical-extension-boundaries.json`에 있다. 공시는 보유 기준일보다 50~62일 늦게 공개되므로 보유 기준일 신호에 소급하지 않았다.", "",
        "가장 큰 차단은 당시 증권/클래스 연결과 완전한 지수 편출입 원장, 그다음 상한이 없는 누락 회사 시총이다. 누락을 0으로 두지 않아 K마다 경계 불확실 상태를 남겼다. 현재 표본에서 종가만·주식수만·CIK 후보만 한 종류를 추가할 때 완전 순위로 열리는 주는 모두 0이다.", "",
        "다음 원천 하나는 기존 이용권에서 받을 수 있는 **주차별 S&P 구성·회사/증권 식별자·클래스·IWF와 회사 시총을 함께 담은 파일**이다. 2018/2020/2022의 52/53/52주가 순위 검증의 최대 후보 범위다. 실제 수익이 열리는 수는 이후 선택된 증권의 가격·총수익·청산 권리를 검사해야 하므로 보장하지 않는다. 필요한 날짜는 각 연도 첫 신호 이전 구성 기준일부터 마지막 주까지이며, 새 유료 구독은 하지 않았다.", "",
        "## 파일·재실행·제한", "",
        "`fixed-holding-performance.csv`: 평균·중앙값·승률·하위 10%·연도·분모·중복 블록. `annual-rank-and-return-coverage.csv`: 연도/K/기간별 전체 주차·풀 주차·순위·성숙·완전 분모. `remaining-rank-gaps.csv`: 종목/필드/날짜 범위/확인 원천. `nav-segments.json`: 연속 구간별 일별 NAV·주간 거래비용·회전. `financial-control-paired.csv`: 같은 날짜의 B2 대조.", "",
        "실행 순서와 비공개 경로 인수는 저장소 `research/us_topk_market_cap_v1/README-ko.md`를 참조한다. 재배포 권한은 부여하지 않는다. 시세·원 계정 응답·개별 미래수익·선정 파일·개인키를 PR에 포함하지 않았다. 순위가 막힌 전체 지수 실험을 성공으로 표시하거나 배포·writer를 활성화하지 않았다.", "",
        "## 원천", "",
        "- [고정 main의 분석 규칙·원천 코드](https://github.com/jaehojung1879-netizen/Investment/tree/4f4497bcc9e7f9369bf5529225585ad39b0d7725/research/us_historical_market_recovery_v1)",
        "- [SEC companyfacts API 예: Apple](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json) — 실제 주식 수의 공개일·측정일·accession 보존. 각 영수증은 비공개 수집 폴더에 있음.",
        "- [SPY 2018-03-31 공식 반기 보유 공시](https://www.sec.gov/Archives/edgar/data/884394/000119312518176552/d483307dn30d.htm) — 2018-05-29 공개, 새 취득 바이트 검산.",
        "- [SPY 2020-03-31 공식 NPORT](https://www.sec.gov/Archives/edgar/data/884394/000175272420111515/primary_doc.xml) — 2020-06-01 공개.",
        "- [SPY 2022-03-31 공식 NPORT](https://www.sec.gov/Archives/edgar/data/884394/000175272422127611/primary_doc.xml) — 2022-05-27 공개.",
        "- 모든 10개 ETF 공시의 정확한 URL·취득 해시는 `historical-extension-source-receipts.json`, 40개 회사의 클래스 원문 626건은 비공개 `sec-class-filings.json`에 보존했다.", ""]
    (out / "REPORT-ko.md").write_text("\n".join(text))
    # Record the exact code that produced this aggregate report.
    source_root = Path(__file__).resolve().parent
    write(out / "study-code-hashes.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in sorted(source_root.glob("*.py"))})
    print({"report": str(out / "REPORT-ko.md"), "main_full_index_verified_weeks": 0,
           "financial_pool_complete_cohorts_per_horizon": 100, "paired_control_rows": len(paired)})


if __name__ == "__main__":
    main()
