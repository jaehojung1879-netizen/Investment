"""Render the requested Korean tables and one-paragraph conclusion from saved results."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def num(v):
    return '미측정' if v is None else f'{v*100:+.2f}'


def cell(s):
    return num(s['mean']) + (' [' + ', '.join(num(x) for x in s['ci']) + ']' if s['ci'] else ' [구간 미측정]')


def decomp_table(r, sample):
    lines = ['|기간|순위|주차|전체 추가 기여 S−B|S2 선택 효과 S−Q|ETF→대조 종목 Q−B|', '|---|---:|---:|---:|---:|---:|']
    for h, title in [('126', '6개월'), ('252', '12개월')]:
        for k in range(1, 6):
            a = r['decomposition'][h][str(k)][sample]
            lines.append(f"|{title}|{k}|{a['total']['n']}|{cell(a['total'])}|{cell(a['selection'])}|{cell(a['replacement'])}|")
    return lines


def main():
    r = json.loads((HERE/'results/summary.json').read_text())
    p = r['bookPerformance']
    main_sample = 'COMMON_ALL_RANKS_WITHIN_2X'
    whole = r['matchedWholeBookDecomposition']
    lines = ['# 한국 S2는 같은 업종·비슷한 시총의 다른 종목보다 잘 골랐나', '',
             '기준 `afb3ea3` · 계산 전 설계 `48e7f23` · 공개 과거 표본의 후속 검산, 전향 증거 아님 · 단위 %p/보유기간, 대괄호는 명목 95% 이동 블록 구간.', '',
             '## 1. 0~5종목 장부의 ETF 대비 전체 순초과', '',
             'N0는 KODEX 200 100%, Nk는 기존 S2 앞 k개를 각각 20%와 잔여 ETF로 보유한다. 모든 열은 비용 차감 순수익에서 같은 날짜 ETF 순수익을 뺀 평균이다. CAGR이나 순위 하나의 추가 기여가 아니다. 원 전체 표본은 기존 결과를 그대로 재사용했다. 원 최근접 매칭에는 시총 거리 상한이 없어, ½~2배 범위를 충족한 비교도 별도로 제시한다. 범위를 바꾸거나 다른 peer로 다시 매칭하지 않았다.', '',
             '|기간|종목 수|원 전체 표본(6개월 427 / 12개월 400)|최근접 매칭 5순위 공통(414 / 387)|시총 ½~2배 5순위 공통(317 / 291)|',
             '|---|---:|---:|---:|---:|']
    for h, title in [('126', '6개월'), ('252', '12개월')]:
        for k in range(6):
            a = p[h][str(k)]
            lines.append(f"|{title}|{k}|{cell(a['FULL_REUSED'])}|{cell(a['COMMON_ALL_RANKS'])}|{cell(a[main_sample])}|")
    lines += ['', '## 2. 1~5위별 단일 슬롯 기여 분해', '',
              '**아래 주 표는 모든 순위가 존재하고 각 쌍의 시총이 ½~2배인 공통 날짜**다. 6개월 317주, 12개월 291주로 각 순위를 같은 날짜에서 비교한다. B는 앞 k−1개 S2 종목+잔여 ETF, S는 B의 ETF 20%를 k위 S2로, Q는 같은 20%를 대조 종목으로 바꾼 장부다. S와 Q의 앞 순위 S2 종목·ETF 비중·날짜·거래비용 기준은 같다. 예를 들어 3위의 S/Q는 모두 1·2위 40%와 ETF 40%를 유지한다.', '']
    lines += decomp_table(r, main_sample)
    v6, v12 = r['validation']['126'], r['validation']['252']
    lines += ['', f"주 표 공통 신호일 범위는 6개월 {v6['commonWithin2xFirst']}~{v6['commonWithin2xLast']}, 12개월 {v12['commonWithin2xFirst']}~{v12['commonWithin2xLast']}다. 범위 안의 모든 주를 포함하는 것은 아니며 정확한 포함 날짜는 `common-dates-126/252.csv`에 남겼다.", '',
              f"각 날짜에서 **전체=선택+ETF→대조**를 검산했다(최대 오차 {r['validation']['maxPerDateDecompositionError']:.2g}). 표의 평균은 반올림으로 0.01%p 차이가 날 수 있다. 구간의 양 끝을 더하는 항등식은 아니다.", '', '## 결론', '']
    w6, w12 = (whole[h][main_sample] for h in ('126', '252'))
    exc6, exc12 = (r['rank5Sensitivity'][h]['LEGACY_FULL_EX_TWO'] for h in ('126', '252'))
    size6, size12 = (r['rank5Sensitivity'][h]['WITHIN_2X_EX_TWO'] for h in ('126', '252'))
    lines += [f"① **S2 상위 순위가 대조군보다 우월하다는 근거는 확인되지 않았다.** 시총 범위를 충족한 공통 날짜의 1~4위 선택 효과는 6개월 −1.01/−0.06/+0.05/+0.94, 12개월 −1.81/+0.07/+1.53/+0.76%p이며 전부 구간이 0을 포함한다. 5위 선택 효과도 {cell(r['decomposition']['126']['5'][main_sample]['selection'])} / {cell(r['decomposition']['252']['5'][main_sample]['selection'])}로 불확실하다. ② 같은 공통 날짜의 N5 전체 성과 {num(w6['total']['mean'])}/{num(w12['total']['mean'])}%p는 선택 부분 {num(w6['selection']['mean'])}/{num(w12['selection']['mean'])}와 ETF를 대조 종목으로 줄인 부분 {num(w6['replacement']['mean'])}/{num(w12['replacement']['mean'])}의 합이다. 원 최근접 공통 표본에서는 각각 전체 −1.63/+1.09, 선택 +2.01/+6.16, ETF→대조 −3.63/−5.07로, 표본에 민감하다. 대조 노출은 같은 업종·시총 종목의 효과이며 순수 시장 베타의 인과 효과는 아니다. ③ 기존 5위 기여의 약 79%를 만든 두 반도체 종목의 진입 날짜를 빼면 원 FULL 기준 전체 추가 기여는 6개월 {cell(exc6['total'])}, 12개월 {cell(exc12['total'])}로 줄고, 선택 효과는 {cell(exc6['selection'])}/{cell(exc12['selection'])}다. 시총 범위까지 충족한 제외 표본의 선택 효과도 {cell(size6['selection'])}/{cell(size12['selection'])}다. **남는 점추정은 양수지만 0과 구분되지 않는다.** 이는 사후 민감도이며, 공통 시총 표본의 독립 정보량은 약 12.7/5.8블록에 불과하고 여러 번 노출된 과거다. 종목 수 규칙이나 점수 가중치 변경 근거로 쓰지 않는다.", '',
              '## 부록 A. 재사용 여부와 후보·매칭 정의', '',
              '- 원 `incrementNetOfMatched = (Nk−Nprev)−(Mk−Mprev)`에서 Mk/Mprev는 같은 peer 집합의 prefix다. 고정보유 순수익은 비중에 선형이므로 이는 **원 S2 prefix를 유지한** `Nk−Qk`와 같다. 기존 비교는 수학적으로 재사용 가능하다. 실제 B/S/Q 장부와 원 주식·ETF 가격/날짜별 비용으로 직접 재구성하여 검산했다. 단순히 누적 `Nk−Mk`를 한 순위의 선택 효과로 보고하지 않았다.',
              '- 후보는 판단일 PIT Top120 중 원 품질 적격군이다: 거래 가능, 우선주 제외, E04≥20, E07≤0, 60세션 거래대금 중앙값≥50억원, WITHHELD 제외. 대조군에 B08 사업 확인·가치 점수를 추가로 요구하지 않는다. 따라서 원 S2의 가치·사업 확인 선택 전체를 검증한다.',
              '- 원 S2 다섯 이름 전부와 앞 순위에 이미 사용한 peer를 제외한다. 같은 업종에서 품질 적격군 내 시총 백분위 제곱 거리가 최소인 peer를 순위 순서로 선택한다. 동률은 티커 오름차순이다. 원 매칭을 재현해 `decisions.csv`의 저장 peer와 매일 일치함을 확인했다. 시총 스냅샷이 판단일보다 엄격히 이전인지 검사했고, 수익을 매칭에 넣지 않았다.',
              '- 기존 방식에는 크기 상한이 없다. 대칭 시총 배수 `max(peer/S2, S2/peer)`의 최대가 4위 24.27배, 5위 25.57배여서 전부를 비슷한 시총이라고 부를 수 없다. 계산 전 고정한 [0.5,2] 비율을 충족하는 기존 쌍만 별도 분석했다. 아래 표의 제외는 거리 조건 미충족이며 다른 종목으로 재매칭하거나 ETF로 채우지 않는다.',
              '- 다음 KR 세션 종가 진입, 126/252세션 보유, 원 편도 주식 수수료·스프레드와 날짜별 매도세, ETF 편도 2.5bp를 유지했다. replay-v16 주식의 최종 세션·OCI 정정과 공식 분배금 기반 ETF 총수익도 같다. ETF는 투자자 분배금 세전·배당락일 종가 재투자이며 주식 기업행위/vintage의 기존 한계는 이어받는다.',
              '- CI는 기존 `L.stats`: 4,000회, seed=20261117, 블록 25/50주. 원 만기 시간축 427/400주를 재표집한 뒤 같은 날짜의 마스크를 적용한다. 비연속 날짜를 먼저 붙이지 않는다. 최소 2블록 미만은 구간 미측정, 다중비교 보정한 새로운 승격 판정은 하지 않는다.', '',
              '### 대상 주차·매칭 성공률·실제 시총 거리', '',
              '|기간|순위|순위 존재 주차|최근접 매칭/대상|가격 유효|시총 범위 통과|범위 밖|대칭 시총 배수 중앙값 / p90 / 최대|',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for h, title in [('126', '6개월'), ('252', '12개월')]:
        for k in range(1, 6):
            a = r['coverage'][h][str(k)]; d = a['symmetricCapMultiple']
            lines.append(f"|{title}|{k}|{a['rankPresentWeeks']}|{a['matchedWeeks']}/{a['rankPresentWeeks']} (100%)|{a['validWeeks']}|{a['within2xWeeks']}|{a['outside2xWeeks']}|{d['median']:.2f} / {d['p90']:.2f} / {d['max']:.2f}|")
    lines += ['', '6개월 순위 1·2의 대상 기간은 2018-01-05~2026-03-06, 3위는 2018-03-30부터, 4·5위는 2018-04-06부터다. 12개월은 같은 시작일에서 2025-08-29까지다. 순위가 없는 주는 3위 12주, 4·5위 13주다. **동일 업종 후보 없음·시총 미측정·가격 미해결은 모두 0건**이다. 순위 부재는 매칭 성공률의 분모에 넣지 않았다. 미만기 27/54주는 기존처럼 제외했다. 모든 판단일의 이름·prefix·시총·스냅샷·매칭 거리·실패 사유는 [matching-audit.csv](results/matching-audit.csv)에 있다.', '',
              '### 각 순위 자체 표본: 시총 범위 통과, 공통 날짜 제한 전', '',
              '아래 순위끼리는 날짜가 다르므로 평균을 더해 장부 전체 성과로 해석하지 않는다. 본문의 공통 날짜 표는 이 문제를 제거한다.', '']
    lines += decomp_table(r, 'WITHIN_2X')
    lines += ['', '### 원 최근접 매칭 재사용: 5순위 공통 날짜(거리 상한 없음)', '']
    lines += decomp_table(r, 'COMMON_ALL_RANKS')
    lines += ['', '원 FULL의 순위 부재=0 재사용 수치는 `summary.json → decomposition → LEGACY_ZERO_FILL`에 있다. 5위 전체/선택 기여는 6개월 +1.18/+0.42, 12개월 +4.80/+2.17로 기존 수치와 일치한다. 실제 순위 존재 표본에서는 6개월 +1.22/+0.43, 12개월 +4.96/+2.25다. 표본 정의의 차이를 새 성과로 해석하지 않는다.', '',
              '## 부록 B. 5위의 두 반도체 종목 의존도 — 사후 민감도', '',
              '기존 79%는 `Σ(5위가 두 이름인 날짜의 delta5) / Σ(모든 날짜 delta5)`다. 두 이름이 5위로 들어간 날짜만 제외하고, 다른 순위에 있는 날짜는 유지했다. 분모는 **5번째가 ETF 20%를 대체한 순기여**이며 N5 장부 전체 성과나 대조군 대비 선택 효과가 아니다. 겹치는 주간 코호트의 기여 분해이지 독립 회귀 설명력이나 R²가 아니다.', '',
              '|보유기간|분모 적용 신호일|원 코호트|두 이름이 5위인 코호트|분자: 두 이름 기여/원 전체 N|분모: 전체 delta5 평균|비율|', '|---|---|---:|---:|---:|---:|---:|']
    for h, title in [('126', '6개월'), ('252', '12개월')]:
        a = r['old79PercentDenominator'][h]
        lines.append(f"|{title}|{a['firstSignal']}~{a['lastSignal']}|{a['fullCohorts']}|{a['twoAtRank5']}|{num(a['contributionMeanAcrossFullCohorts'])}|{num(a['fullMeanRank5Increment'])}|{a['share']*100:.2f}%|")
    lines += ['', '분자의 평균도 원 전체 N으로 나눈다(두 이름이 들어간 62/61주만의 평균이 아니다). 분자·분모의 합과 정확 비율은 `old79PercentDenominator`에 보존했다.', '',
              '|기간|표본(사후 이름 제외)|N|전체 추가 기여|선택 효과|ETF→대조|', '|---|---|---:|---:|---:|---:|']
    groups = [('LEGACY_FULL_ZERO_FILL', '원 FULL, 부재 주 0'), ('LEGACY_FULL_EX_TWO', '원 FULL에서 두 이름 날짜 제외'),
              ('BASE_PRESENT', '5위 존재·매칭'), ('EX_TWO_AT_RANK5', '위 표본에서 두 이름 날짜 제외'),
              ('WITHIN_2X', '5위 쌍 시총 ½~2배'), ('WITHIN_2X_EX_TWO', '위 표본에서 두 이름 날짜 제외'),
              ('COMMON_WITHIN_2X', '5순위 시총 범위 공통'), ('COMMON_WITHIN_2X_EX_TWO', '위 공통 표본에서 두 이름 날짜 제외')]
    for h, title in [('126', '6개월'), ('252', '12개월')]:
        for name, label in groups:
            a = r['rank5Sensitivity'][h][name]
            lines.append(f"|{title}|{label}|{a['total']['n']}|{cell(a['total'])}|{cell(a['selection'])}|{cell(a['replacement'])}|")
    lines += ['', '원 FULL의 제외 전후는 427→365, 400→339개다. 실제 5위 존재 표본은 414→352, 387→326개다. 이 제외는 순위·후보·비용·가중치를 바꾸지 않는 사후 민감도이며, 제외 후의 표본이 원 표본과 같은 시장 구성이라고 가정하지 않는다.', '',
              '### 기존 반도체 주도기 정의 유지', '',
              '기존 `SEMI_LED`는 126세션 전 PIT Top120 시총 비중의 시장 proxy가 양수이고 삼성전자·SK하이닉스가 그 수익의 절반 이상인 월이다. 보유 창이 해당 월에 닿는지는 미래 수익을 이용한 사후 라벨이다. 비주도기는 주도 월에 닿지 않고 라벨이 알려진 경우만 포함한다. 라벨이 일부 미정인 주를 비주도기로 임의 편입하지 않는다. 아래는 기존 최근접 비교의 실제 5위 존재 표본이다.', '',
              '|기간|5위 표본|N|전체 추가 기여|선택 효과|ETF→대조|', '|---|---|---:|---:|---:|---:|']
    for h, title in [('126', '6개월'), ('252', '12개월')]:
        for name, label in [('SEMI_LED', '주도 월 포함'), ('NON_SEMI_KNOWN', '알려진 비주도기'),
                            ('SEMI_LED_EX_TWO', '주도 월 포함·두 이름 제외'), ('NON_SEMI_KNOWN_EX_TWO', '비주도기·두 이름 제외')]:
            a = r['rank5Sensitivity'][h][name]
            lines.append(f"|{title}|{label}|{a['total']['n']}|{cell(a['total'])}|{cell(a['selection'])}|{cell(a['replacement'])}|")
    lines += ['', '라벨이 일부 미정인 실제 5위 주는 두 보유기간 모두 12개다(구간은 2블록 미만이라 미측정). 12개월에는 미정 주 일부가 뒤쪽 주도 월에도 닿아 포함/미정 수가 서로 배타적이지 않다. 상세 마스크 통계는 `rank5Sensitivity → LABEL_UNKNOWN`에 있다.', '',
              '## 부록 C. 재실행·검증·원본', '',
              '새 계산은 누락된 ETF→대조 분해·부분 표본·단일 슬롯 직접 검산만 수행했다. 원 v1 장부·무작위 경로·과거 종목 수 선택·가격 수집을 다시 돌리지 않았고 원 폴더의 읽은 파일 SHA256이 전후 동일했다. 기존 원 전체 장부 평균·구간과 매칭 추가분 평균·구간을 재사용했으며, 새 샘플의 구간만 같은 함수로 계산했다.', '',
              f"직접 장부 재구성 최대 차이 {r['validation']['maxDirectBookReconstructionError']:.2g}, 기존 차분과 단일 슬롯 차이 최대 {r['validation']['maxLegacyEquivalenceError']:.2g}, 날짜별 3항 분해 최대 오차 {r['validation']['maxPerDateDecompositionError']:.2g}다. 앞 두 차이는 기존 CSV 12자리 저장 정밀도 이내다.", '',
              '```bash',
              '# 이 저장소 루트, 기존 복구 입력 사용',
              'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \\',
              '  /workspace/s2-venv/bin/python -m research.kr_s2_single_slot_matched_v1.analyze \\',
              '  --scratch /workspace/s2-inputs',
              '/workspace/s2-venv/bin/python -m research.kr_s2_single_slot_matched_v1.report',
              '/workspace/s2-venv/bin/python -m research.kr_s2_single_slot_matched_v1.verify',
              '',
              '# 캐시가 없으면 고정 #329 입력 생성 경로만 복구(기존 v1 출력은 쓰지 않음)',
              '# pip install -c constraints/ci-registered-numerics-v1.txt -r requirements.txt -r requirements-dev.txt',
              'S=/absolute/scratch PYTHON=/absolute/python \\',
              'OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \\',
              'bash research/kr_s2_single_slot_matched_v1/reproduce.sh', '```', '',
              '입력의 의미상 identity·matrix digest·454개 날짜·원 매칭·모든 슬롯 순수익을 검증한다. pickle 직렬화 바이트는 Python 버전에 따라 달라질 수 있어 원/실제 SHA256을 따로 기록한다. 이번 캐시는 기준과 바이트까지 같았고 입력 digest도 같다.', '',
              '- [계산 전 설계](DESIGN-ko.md)',
              '- [결과 요약 원본](results/summary.json), [입력·코드·원 산출물 SHA256](results/provenance.json)',
              '- [6개월 날짜별 B/S/Q 및 3항 분해](results/single-slot-126.csv), [12개월 원본](results/single-slot-252.csv)',
              '- [6개월 공통 날짜·순위별 마스크](results/common-dates-126.csv), [12개월 마스크](results/common-dates-252.csv)',
              '- [판단일별 후보·매칭 감사](results/matching-audit.csv)',
              '- [기준 v1 보고서](../kr_s2_rank_ladder_v1/REPORT-ko.md), [기준 v1 입력 계보](../kr_s2_rank_ladder_v1/SOURCES-ko.md)',
              '- [검증 기록](VALIDATION.md), [저장 행·CI 재생 검증](results/verification.json)',
              '', '미국 추가 데이터 구매·종목 수 규칙·점수 가중치 조정·운영/전향 원장 변경은 이번 범위에서 수행하지 않았다.', '']
    text = '\n'.join(lines)
    (HERE/'REPORT-ko.md').write_text(text)
    # Keep the same tables in a compact file for exact lookup, without duplicating interpretation.
    start = text.index('## 1.')
    end = text.index('## 결론')
    (HERE/'TABLES-ko.md').write_text('# S2 0~5 장부 및 1~5위 단일 슬롯 분해\n\n' + text[start:end])


if __name__ == '__main__':
    main()
