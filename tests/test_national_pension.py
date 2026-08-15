from pipeline import national_pension as NPS


def test_official_page_parser_keeps_scope_date_and_asset_weights():
    html = '''
    <h3>기금 포트폴리오 <span class="date">2026년 5월 말 기준</span></h3>
    <table><caption>기금 포트폴리오 구성별 규모</caption><tbody>
      <tr><th>금융부문</th><td><span>1,847.7</span> 조 원</td><td><span>99.9</span> %</td></tr>
      <tr><th>국내주식</th><td><span>543.6</span> 조 원</td><td><span>29.4</span> %</td></tr>
      <tr><th>국내채권</th><td><span>289.6</span> 조 원</td><td><span>15.7</span> %</td></tr>
      <tr><th>해외주식</th><td><span>650.7</span> 조 원</td><td><span>35.2</span> %</td></tr>
      <tr><th>해외채권</th><td><span>107.0</span> 조 원</td><td><span>5.8</span> %</td></tr>
      <tr><th>대체투자</th><td><span>254.5</span> 조 원</td><td><span>13.8</span> %</td></tr>
      <tr><th>단기자금</th><td><span>4.2</span> 조 원</td><td><span>0.2</span> %</td></tr>
      <tr><th>복지 ·기타 부문</th><td><span>1.0</span> 조 원</td><td><span>0.1</span> %</td></tr>
    </tbody></table><div class="pf-total"><em>1,848.7</em></div>
    '''
    got = NPS.parse_official_page(html)
    assert got["asOf"] == "2026-05-31"
    assert got["totalFundTrillionKrw"] == 1848.7
    assert got["equityWeightPct"] == 64.6
    assert got["overseasEquityWeightPct"] == 35.2
    assert len(got["allocations"]) == 6
