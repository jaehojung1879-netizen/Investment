"""Render numerical, separated A/B outcomes; no result is recomputed here."""
import csv
import json
from pathlib import Path

from .identity import HERE


def pct(x):
    return 'SOURCE_BLOCKED' if x is None else f'{100*x:.6f}%'


def main(directory):
    p = Path(directory)
    r = json.loads((p / 'results.json').read_text())
    diag = json.loads((p / 'controlled-diagnostics.json').read_text())
    sources = json.loads((p / 'source-admission.json').read_text())
    rows = []
    for sid, result in r.items():
        rows.append({'strategy': sid, 'version': 'v1_REPORTED', 'status': 'ORIGINAL_DEVELOPMENT_PRESERVED',
                     **{k: result['v1'].get(k) for k in ('cagr', 'excessCagr', 'mdd', 'sharpe')}})
        for mode in ('A_VERIFIED_CASH', 'A_OBSERVED_PREFIX_INCOMPLETE_EVENT_COVERAGE'):
            x = result['v2A'][mode]
            rows.append({'strategy': sid, 'version': mode, 'status': x['status'],
                         **{k: x['metrics'].get(k) for k in ('cagr', 'excessCagr', 'mdd', 'sharpe')}})
        rows.append({'strategy': sid, 'version': 'B_REFIT', 'status': result['v2B']['status'],
                     **{k: result['v2B']['metrics'].get(k) for k in ('cagr', 'excessCagr', 'mdd', 'sharpe')}})
    with (HERE / 'comparison.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=['strategy', 'version', 'status', 'cagr', 'excessCagr', 'mdd', 'sharpe'])
        w.writeheader()
        w.writerows(rows)
    etf = r['RULE_ETF_ONLY']['v2A']['A_VERIFIED_CASH']
    nav = etf['metrics']['finalNavKrw']
    out = ['# ML Tournament v2 Integrity Repair — 정정 결과', '',
      '**네 후보만 고정해 정정했다. 새 대회·우승자 선정·모델 적합·Atlas 실행·잠금 해제·production 변경은 없다.**', '',
      'v1과 #330 증거는 원래 바이트로 보존했다. #330의 판정을 다시 검사해, 006800의 전 종목 일괄 거절과 config 해시 설명을 보완했다. 원시 주가·경제적 권리·현금 입금·주식 입고를 구분했다.', '',
      '## 1. v1 / v2 A / v2 B를 분리한 성과', '',
      '아래 CAGR은 v1과 비교 가능한 252거래일 연환산이며, 주식 전략의 빈 값은 0%가 아니다. **세 주식 전략의 완전한 정정 경제성은 아직 SOURCE_BLOCKED다.**', '',
      '|고정 전략|v1 보고 CAGR|v2 A 원시가격·현금 계정 CAGR|v2 B 같은 설정 재적합|',
      '|---|---:|---:|---|']
    for sid, x in r.items():
        out.append(f"|{sid}|{pct(x['v1']['cagr'])}|{pct(x['v2A']['A_VERIFIED_CASH']['metrics']['cagr'])}|" +
                   ('재적합 없음·동일 ETF 대조군' if sid == 'RULE_ETF_ONLY' else 'SOURCE_BLOCKED · NOT_RUN') + '|')
    out += ['', f"ETF는 1억원에서 **{nav:,.2f}원**, CAGR **{pct(etf['metrics']['cagr'])}**, MDD **{pct(etf['metrics']['mdd'])}**, Sharpe **{etf['metrics']['sharpe']:.6f}**로 계산됐다. 원래 ETF 총수익 지수 대비 CAGR 차이는 **{100*(etf['metrics']['cagr']-r['RULE_ETF_ONLY']['v1']['cagr']):+.6f}%p**다. 배당 지급일 뒤 실제 사용 가능한 현금으로 다음 고정 리밸런스에서 재투자하고 그 체결 비용을 차감한 영향이다.", '',
      '다른 세 전략은 세전 배당·주식배당·권리·분할·종결 조건의 전 기간 완전성이 입증되지 않았다. 실제 원시 가격이 있다는 사실과 완전한 주주수익 원천이 있다는 사실은 다르다. 따라서 전체 CAGR·ETF 대비 격차·MDD·Sharpe·연도별 확정 수익은 null이다. 결과를 좋게 만들기 위해 종목을 빼거나 차순위를 넣지 않았다.', '',
      '### 연도별 수익: 원래 네 전략과 정정 ETF 현금 계정', '',
      '|연도|v1 산업모멘텀|v1 XGB|v1 LGBM|v1 ETF|v2 A ETF|v2 A 주식 3개|', '|---|---:|---:|---:|---:|---:|---|']
    order = ['RULE_INDUSTRY_MOMENTUM', 'XGB_CI_RANK_h1', 'LGBM_CIM_RANK_h3', 'RULE_ETF_ONLY']
    for y in sorted(etf['metrics']['yearly']):
        old = [pct(r[s]['v1']['yearly'][y]['ret']) for s in order]
        out.append('|'+y+'|'+'|'.join(old)+'|'+pct(etf['metrics']['yearly'][y])+'|SOURCE_BLOCKED|')
    out += ['', '2026년은 9월 14일까지다. B 주식 세 후보의 각 연도도 NOT_RUN이며 새 성과로 v1을 대체하지 않는다. ETF는 학습 모델이 없어 B에서도 동일 대조군이다.', '',
      '## 2. 어디까지 관찰할 수 있었는가', '',
      '엄격한 전체 원천 admission은 주식 후보를 첫 진입부터 차단한다. 별도 관찰 진단은 원시 체결 가격으로 수량·현금을 계산하되 처음 미확정 사건에서 중단한다. 다음 초기 구간은 **당시까지 기업행동 누락이 전혀 없었다고 인증한 구간이 아니며**, 전체 성과의 추정치도 아니다.', '',
      '|전략|조건부 관찰 거래일|중단 전 최종 가치(1억원)|해당 초기 구간 누적 수익|처음 미확정 사건일|', '|---|---:|---:|---:|---|']
    for sid in order:
        x = r[sid]['v2A']['A_OBSERVED_PREFIX_INCOMPLETE_EVENT_COVERAGE']
        met = x['observedPrefixMetricsNotCertifiedFullPeriod']
        value = met.get('finalNavKrw')
        out.append(f"|{sid}|{x['valuedSessions']}|" + (f'{value:,.2f}' if value is not None else '불명') + '|' +
                   (pct(value/1e8-1) if value is not None else '불명') + '|' + (x['firstBlock']['date'] if x['firstBlock'] else '끝까지 계산') + '|')
    out += ['', '각 미확정 사건의 종목·vendor cash/split 값·공식 증거 부족 이유는 source-admission 및 account/events/orders 원장에 남겼다. 8거래일 같은 짧은 구간의 연환산 수치를 전체 기간 CAGR처럼 해석하지 않는다.', '',
      '## 3. 확인한 오류별 경제성 영향 — 통제 진단', '',
      '**다음 표는 v1의 총수익 지수에 한정된 오류 분해다. 실제 주식 수·배당 현금 계정의 확정 정정 성과가 아니다.** 2018 미상 권리를 연결하거나 모든 현금배당의 완전성을 인정하지 않는다. 원본 선택·20% 비중을 유지하며 새 종목을 선택하지 않았다.', '',
      '|전략|원래 보고|실제 거래대금 비용 방정식만|+최종일 가격 배율|+006800 2026 현금·주식 패키지만|', '|---|---:|---:|---:|---:|']
    for sid in order:
        x = diag['paths'][sid]
        out.append('|'+sid+'|'+pct(r[sid]['v1']['cagr'])+'|'+'|'.join(pct(x[k]['cagr']) for k in ('CASH_EQUATION_ONLY','PLUS_FINAL_QUOTES','PLUS_2026_MIRAE_PACKAGE'))+'|')
    probe = sources['finalSourceProbe']
    ev = diag['mirae2026Event']
    out += ['', f"최종일 원천 대조: **{probe['matchingSecurities']}종목**, 기존/원시 KRX 배율 차이 0.1% 초과 **{probe['scaleGapsAbove0p1pct']}종목**. 원시 종가를 사용하면 마지막 vendor 가격의 불일치 배율을 제거할 수 있다. 다만 당시 원본 vendor 응답이 없어 수집 시각 문제인지 vendor 정정인지 근본 원인은 확정할 수 없다.", '',
      f"006800 / 2026-03-16: 원시 KRX와 현금 300원·주당 주식 0.0073206주 패키지의 하루 경제적 배수는 **{ev['officialPackageGross']:.12f}**, 기존 replay는 **{ev['oldGross']:.12f}**다. #328의 `cited_levels` 재사용 결과와도 일치한다. 현금 중복 조정만 제거하면서 주식 권리를 무시하면 오히려 잘못된 수정이 된다. 두 요소를 함께 반영한 통제 pulse는 **{ev['correctionPulse']:.12f}**다.", '',
      '#330은 006800 전체를 미검증이라고 설명했지만 저장소에는 이미 공식 KRX의 연결된 구간별 복구가 있었다. v2는 이를 검증해 재사용한다. **2018-01-23 비상장 우선주 신주인수권의 가치 미확정 경계는 그대로 차단**한다. 2026 권리 인식과 실제 4월 주식 입고를 나눠 처리하는 회계 코드도 별도로 테스트했다. 그러나 전체 보유 기간의 완전한 지급·기업행동 이력이 없으므로 그 사실만으로 XGB 전체 성과를 인증하지 않는다.', '',
      '## 4. 회계와 PIT·재현성 수정', '',
      '- 원시 가격만 허용한다. 수정/총수익 가격에 배당을 또 더하는 입력을 거절한다. 현금배당은 권리일 채권으로 인식하고 공식 지급일까지 소비하지 않는다. 주식배당은 실제 입고일까지 비거래 주식채권이다. 분할·종결 현금·교환 주식은 인용된 패키지로만 처리한다.',
      '- 거래정지 수량은 다른 체결 수수료 때문에 줄어들지 않는다. 매도는 보류, 매수는 미체결로 기록한다. 실제 체결대금의 commission/spread/dated sell tax와 순자산 목표를 같이 풀어 음수 현금·숨은 레버리지를 막는다. 일별 수량·현금·채권·실제 비용·자금 잔차를 모두 저장한다.',
      '- 초기 1억원·시작 ETF 선보유·세전 배당·현금 금리 0%는 네 경로에 공통이다. 소수 수량 연구 계정이며 실제 거래소 lot 체결·개인 세후 실계좌를 재현한 것은 아니다. 현금은 같은 결제일 약정을 상계한 trade-date buying power다.',
      '- `refit.training_layers`는 해당 fold의 성숙한 과거 훈련 행만 사용한다. 선택 열·전체 열별 커버리지·평균·표준편차·중앙값·결측 규칙을 저장한다. 미래 행/미래 결측률을 추가해도 과거 입력과 통계가 바뀌지 않는 회귀가 있다. 실제 B 적합은 수행하지 않았으므로 실제 재학습 fold 기록이 있다고 주장하지 않는다.',
      '- 원래 두 ML 구조/HP, 산업모멘텀 규칙, gated/forced 구분, H126, 리밸런스 일정과 비용 규칙을 유지한다. B runner도 고정 네 후보만 받아 점수·선택·일별 원장을 저장하며 우승자/순위를 만들지 않는다.',
      '- 캐시는 code/config/source/model/fold/environment 및 실제 입력 내용과 payload 해시를 검사한다. 다른 identity나 깨진 payload는 재사용·덮어쓰기를 거절한다. NAV는 float64로 저장하며 동일 ETF 경로의 active return은 정확히 0이다.', '',
      '## 5. #330 판정 재확인과 메타데이터 정정', '',
      '[audit-reassessment.json](audit-reassessment.json)은 원시 PIT 스냅샷·저장 키·fold 성숙 조건을 다시 확인한다. 공개일·거시 발표 빈티지의 새 증거는 없으므로 INCONCLUSIVE를 유지한다. 연도별 모델 적합이 누출 전체를 증명하지도, 최종 모델 선택의 독립 외부 평가를 만들지도 않는다.', '',
      'v1 실제 config 바이트 SHA-256은 `982e116804a5ce35820201037a44e6fc4684ef9725f356e25fefdf1c84080a65`다. data-eligibility와 #330 서술에 인용된 `f9908805…`는 R2/b5ca5877 커밋의 config이며 최종 config와 **postOutcomeAdditions 문서 키만 다르다**. 원 모델 grid와 숫자 설정은 같다. 이를 수익률 조작이나 새 HP의 증거로 해석하지 않는다. 원본 metadata를 고치지 않고 v2 identity에 실제 값·이전 값과 [계보 검사](config-history-review.json)를 함께 보존했다.', '',
      '## 6. 원장·결과 재생성과 실행 권한', '',
      f"정식 A 실행 디렉터리: [`results/{p.name}/`](results/{p.name}/). `execution-identity.json`은 실행 커밋·전체 import closure·설정·원천·환경·선택 해시를 고정한다. `result-manifest.json`은 모든 결과/JSONL gzip의 해시를 고정한다. 동일 입력 재실행의 바이트 비교 결과와 실제 테스트 결과는 [verification.json](verification.json)에 있다.", '',
      'account/assets/trades/orders/events의 다섯 원장을 네 후보·두 admission 모드별로 보존한다. 미확정 기간도 모든 예정 선택·주문과 null 평가 행을 남긴다. 총수익 지수 통제 수치를 실제 주식 원장으로 위장하지 않는다.', '',
      'B는 `refit-execution-packet.json`·`refit-source-readiness.json`·`refit-approval-template.json`으로 정확히 분리돼 있다. 현재 원천은 SOURCE_BLOCKED, 올바른 정정 행렬도 없다. 공개 Owner의 정확 해시 승인 이전에도 이 원천 차단을 우회할 수 없다. 원천·코드·설정·환경이 바뀌면 패킷을 다시 생성해야 한다. 기존 Atlas·KR 연구 승인이나 소비된 lock을 재사용하지 않는다.', '',
      '## 7. PR·CI·판정', '',
      '#329 HEAD 17404f86 → #330 HEAD 8657acd5 위에 별도 v2를 쌓는다. #328 HEAD 3b3edb13의 순수 원천 검증 함수와 공식 ETF 내역을 버전 고정해 재사용한다. #321 HEAD cd2892eb의 threadpoolctl 3.7.0/joblib 1.6.0 제약으로 로컬 검증하되 보호된 Tests/Pages workflow는 수정하지 않는다. 인수 당시 #329/#330/#328 Tests는 FAILURE, #321 Tests/Pages는 SUCCESS였다. 기존 CI 의존성 문제가 해결됐다고 미리 주장하지 않는다.', '',
      '**정정 코드는 검증 가능한 부분을 계산하고, 세 주식 전략의 전체 경제성 인증은 차단한다.** 원래 23.27%·19.36%는 보존한다. 부정적인 초기 관찰 결과도 위에 그대로 공개했다. 세 전략의 수정 후 확정 CAGR을 제시하려면 보유 구간의 공식 cash/share/action/terminal coverage를 먼저 완성해야 한다. 새 역사 우승자 탐색은 다음 단계가 아니다.', '']
    (HERE / 'REPORT-ko.md').write_text('\n'.join(out))
    print(HERE / 'REPORT-ko.md')


if __name__ == '__main__':
    import sys
    main(sys.argv[1])
