"""Render Korean result tables from the retained JSON (no source retrieval)."""
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent


def pct(x):
    return '미측정' if x is None else f'{x*100:+.2f}'


def ci(s):
    v = pct(s['mean'])
    return v + (' [' + ', '.join(pct(x) for x in s['ci']) + ']' if s['ci'] else ' [구간 미측정]')


def main():
    out = HERE / 'results'
    fixed = json.loads((out / 'fixed.json').read_text())
    led = json.loads((out / 'ledgers.json').read_text()) if (out / 'ledgers.json').exists() else None
    past = json.loads((out / 'past-only.json').read_text())
    lines = ['# 한국 S2 순위별 결과표', '', '단위: 수익·차이·낙폭은 % 또는 %p, 회전율은 편도/년. 고정보유는 126/252 세션. 95% 구간은 25/50주 블록. 공개된 과거 표본의 후속 검산이며 전향 성과가 아니다.', '']
    for h, title in [('126', '6개월'), ('252', '12개월')]:
        f = fixed[h]['FULL']
        lines += [f'## {title} 전체 날짜: 비용 차감 후', '', '|요청 종목 수|ETF 대비 순초과 [95%]|직전 수 대비 추가 기여 [95%]|실제 순위 존재 날짜의 기여|순위 기여 Holm p(근사)|', '|---|---:|---:|---:|---:|']
        for k in range(6):
            a = f[str(k)]
            lines += [f"|{k}|{ci(a['vsETF'])}|{ci(a['increment']) if k else '—'}|{ci(a['presentOnlyIncrement']) if k else '—'}|{a['increment']['holmPApproxFiveRanks']:.4f}|" if k else f"|0|{ci(a['vsETF'])}|—|—|—|"]
        lines += ['', f"공통 유효 코호트 {f['0']['vsETF']['n']}개, 근사 독립 블록 {f['0']['vsETF']['independentBlocksApprox']}개. 부족 순위는 추가 기여 0. 12개월 p는 보조 자료다.", '', '|종목 수|적격군 안 순위 효과: Nk−균등무작위|적격군 주식 노출: 무작위−ETF|업종·시총 매칭 대비 [95%]|매칭 코호트|', '|---|---:|---:|---:|---:|']
        for k in range(1, 6):
            a = f[str(k)]
            lines += [f"|{k}|{ci(a['randomSelection'])}|{ci(a['eligibleExposure'])}|{ci(a['matchedSelection'])}|{a['matchedSelection']['n']}|"]
        lines += ['', '|추가 순위|무작위 추가분을 차감한 순위 기여 [95%]|매칭 추가분을 차감한 순위 기여 [95%]|', '|---|---:|---:|']
        for k in range(1, 6):
            a = f[str(k)]
            lines += [f"|{k}|{ci(a['incrementNetOfRandom'])}|{ci(a['incrementNetOfMatched'])}|"]
        lines += ['', '무작위 대조군은 같은 날짜·실제 종목 수·종목당 20%·동일 ETF 잔여비중의 균등 무복원 추출 기대값이다. 노출 항에는 적격군의 업종·스타일도 포함된다. 매칭 비교는 성공 날짜만이며 해당 표의 다른 열과 표본이 다를 수 있다.', '', '|추가 순위|2022 이전|2022 이후|반도체 주도 월에 닿음|반도체 주도 월 제외|', '|---|---:|---:|---:|---:|']
        for k in range(1, 6):
            vals = [ci(fixed[h][s][str(k)]['increment']) for s in ['TO_2021', 'FROM_2022', 'TOUCHES_SEMI_LED', 'EX_SEMI_LED']]
            lines += [f"|{k}|" + '|'.join(vals) + '|']
        lines += ['', '반도체 월 포함 여부는 보유기간의 사후 구분이다. 판단일 예측에 사용하지 않았다.', '']
    if led:
        for every in (26, 52):
            lines += [f'## L{every} 동일 자본 분산 진입 장부', '', '|종목 수|CAGR|ETF 대비 CAGR 차이|MDD|편도 회전율/년|연 비용|직전 수 대비 CAGR 차이|일수익 차이 연율|복리 잔여|', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
            for k in range(6):
                a = led['metrics'][f'L{every}|N{k}']
                b = led['adjacent'].get(f'L{every}|rank{k}', {})
                lines += [f"|{k}|{pct(a['cagr'])}|{pct(a['excess'])}|{pct(a['mdd'])}|{a['oneWayTurnoverPerYear']:.2f}|{pct(a['costPerYear'])}|{pct(b.get('cagrGap')) if k else '—'}|{pct(b.get('annualArithmeticDailyGap')) if k else '—'}|{pct(b.get('compoundingRemainder')) if k else '—'}|"]
            lines += ['', '|종목 수|이전 보유 이름 중 교체 비율|유지 자산 비중 재설정 L1 평균(근사)|', '|---|---:|---:|']
            for k in range(6):
                a = led['metrics'][f'L{every}|N{k}']['turnoverDiagnostic']
                lines += [f"|{k}|{pct(a['nameReplacementShare'])}|{pct(a['meanRetainedAssetL1ResetApprox'])}|"]
            lines += ['', '이름 교체와 비중 재설정은 별도 진단이다. 재설정은 엔진의 6자리 반올림 보유비중으로 산출한 L1 거리로, 위 편도 회전율과 가산하는 항이 아니다. ETF도 유지 자산에 포함된다.', '', '|종목 수|동일노출 무작위 5경로 평균 ETF 대비 CAGR [경로 최솟값, 최댓값]|S2−무작위 평균 CAGR|', '|---|---:|---:|']
            for k in range(1, 6):
                a = led['adjacent'][f'L{every}|rank{k}']
                lines += [f"|{k}|{pct(a['randomExcessMean'])} [{', '.join(pct(x) for x in a['randomExcessRange'])}]|{pct(a['selectionVsRandomCagrMean'])}|"]
            lines += ['', '무작위 5경로 범위는 신뢰구간이 아니다. CAGR 차이는 그 자체로 선택 알파가 아니며, 일수익 차이와 복리 잔여를 함께 읽는다. ETF 100% 장부의 불필요한 거래는 없고, 고정보유 표는 ETF 진입·청산 비용도 차감한다.', '']
    lines += ['## 판단일 이전 만기 기록만 사용한 종목 수 선택', '', '|보유기간|과거평균 최대 k 규칙−ETF [95%]|동일 날짜 N5와 차이 [95%]|평가 코호트|', '|---|---:|---:|---:|']
    for h in ('126', '252'):
        a = past[h]
        lines += [f"|{h}세션|{ci(a['vsETF'])}|{ci(a['vsN5'])}|{a['vsETF']['n']}|"]
    if led:
        for every in (26, 52):
            a = led['metrics'][f'L{every}|PAST_ONLY']
            lines += ['', f"L{every} 과거만 사용: CAGR {pct(a['cagr'])}%, ETF 대비 {pct(a['excess'])}%p/년, MDD {pct(a['mdd'])}%, 회전율 {a['oneWayTurnoverPerYear']:.2f}/년. 초기 52개 만기 이전에는 ETF다."]
    lines += ['', '이 규칙은 관측된 과거 표본에서 한 번 정한 서술용 검산이다. 최적 k를 안다는 증거·새 전향 증거가 아니며 미래 성과를 보장하지 않는다.', '']
    (HERE / 'TABLES-ko.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
