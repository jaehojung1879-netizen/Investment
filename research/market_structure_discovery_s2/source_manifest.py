"""Write results/source-manifest.json: SHA-256 and size of every committed raw source file,
plus the access verdict measured on 2026-11-26 for each source family (KR and US)."""
from __future__ import annotations

import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

ACCESS = [
    # region, source, endpoint, verdict, evidence
    ("KR", "KRX 정보데이터시스템 투자자별·지수구성·공매도 (MDCSTAT02302/00601/30001)",
     "data.krx.co.kr/comm/bldAttendant/getJsonData.cmd", "BLOCKED_LOGIN_REQUIRED",
     "세션·Referer 포함 3건 모두 HTTP 400 'LOGOUT' (data/krx_portal_probe_2026-11-26.json). 로그인 우회 금지"),
    ("KR", "KRX 홈페이지·KIND 공지(지수 정기변경 보도자료)", "www.krx.co.kr, kind.krx.co.kr", "BLOCKED",
     "www.krx.co.kr main.jsp -> AccessDenied.jsp, kind.krx.co.kr 403"),
    ("KR", "KODEX 200 / KOSDAQ 150 PDF (삼성자산운용 공개 API)",
     "samsungfund.com/api/v1/kodex/product-pdf/{fId}.do?gijunYMD=", "PARTIAL_THEN_THROTTLED",
     "robots allow:/. 기준일별 과거 PDF 2010~ 응답. 약 550회 후 Cloudflare challenge(429, cf-mitigated) -> 수집 중단, 우회하지 않음"),
    ("KR", "TIGER ETF", "tigeretf.com", "BLOCKED", "403"),
    ("KR", "ACE ETF PDF API", "aceetf.co.kr /api/funds/{id}/pdf?std_dt=", "UNRESOLVED",
     "클라이언트 코드에 기준일 인자 존재, API 기본 호스트 미확인(빌드 설정 localhost)"),
    ("KR", "KOFIA FreeSIS 신용공여 잔고·증시자금(반대매매)", "freesis.kofia.or.kr/meta/getMetaDataList.do",
     "SERVED", "STATSCU0100000070BO 7,246행, STATSCU0100000060BO 7,245행(1998~2026-11-25). 시장 전체 수준만"),
    ("KR", "KOFIA 전자공시 펀드 보유종목", "dis.kofia.or.kr", "BLOCKED", "접속 실패(#347 선행 판단과 동일)"),
    ("KR", "국민연금 기금 포트폴리오", "fund.nps.or.kr/main.do", "INTERMITTENT_CURRENT_ONLY",
     "최초 200, 이후 터널 종료 2회. 현재 스냅샷만(data/national_pension_cache.json 2026-05 잠정). 월별 과거 비중은 연차보고서 필요"),
    ("KR", "DART OpenAPI", "opendart.fss.or.kr", "REACHABLE_NO_KEY_IN_SESSION",
     "200. 키 없음. 5% 대량보유는 #383 C에서 이미 수집·판정"),
    ("KR", "ECOS 한국은행", "ecos.bok.or.kr", "REACHABLE_NO_KEY_IN_SESSION", "200. 자금순환표 미수집"),
    ("KR", "signal-history KRX 일별 원장(KOSPI)", "signal-history@394fc9f6 ledger/prices/kr", "SERVED_READ_ONLY",
     "거래량·종가로 사건 20세션 이전 중앙 거래대금만 계산. KOSDAQ 미포함"),
    ("US", "SEC EDGAR (13F, N-PORT, Form 4)", "www.sec.gov, data.sec.gov", "BLOCKED", "403 (기존 v2.9 판정과 동일)"),
    ("US", "GCAP N-PORT 보유 릴리스", "Google Drive 1dGUfDF...(7.4GB, #347)", "NOT_FETCHED_THIS_SESSION",
     "#347이 이미 사용. 2019Q3~2026Q3. 재사용 가능하나 이 세션에서 내려받지 않음"),
    ("US", "S&P DJI 지수 변경 보도자료", "prnewswire.com/news/s%26p-dow-jones-indices/", "SERVED",
     "1,333건 2012-07~2026-11, ET 공개시각. 본문 S&P 500 관련 선택분 수집"),
    ("US", "Wikipedia S&P 500 구성종목(Date added)", "en.wikipedia.org (raw)", "SERVED",
     "현 구성종목 502개, 교차검증용. Historical components 페이지는 오류 응답"),
    ("US", "FINRA 공매도 잔고", "cdn.finra.org", "BLOCKED", "403"),
    ("US", "Federal Reserve Z.1 F.223(부문별 주식 순매수)", "federalreserve.gov/releases/z1/current/z1_csv_files.zip",
     "SERVED", "zip sha256 b63af975...; 분기, 개정 이력 미보존(빈티지 아님)"),
    ("US", "iShares / SSGA 보유·상장좌수", "ishares.com, ssga.com", "NOT_TESTED_DEPTH",
     "301 리다이렉트. 현재 보유만 공개로 알려짐 -> 과거 흐름은 전향 수집 대상"),
    ("US", "MSCI index review", "msci.com/index-review", "UNVERIFIED", "동적 페이지. 구성 변경 원장은 고객 자료"),
]


def main() -> None:
    files = []
    for root, _dirs, names in os.walk(os.path.join(HERE, "data")):
        for n in sorted(names):
            p = os.path.join(root, n)
            h = hashlib.sha256(open(p, "rb").read()).hexdigest()
            files.append({"path": os.path.relpath(p, HERE), "bytes": os.path.getsize(p), "sha256": h})
    out = {"measuredOn": "2026-11-26", "files": sorted(files, key=lambda f: f["path"]),
           "access": [dict(zip(("region", "source", "endpoint", "verdict", "evidence"), a)) for a in ACCESS]}
    json.dump(out, open(os.path.join(HERE, "results", "source-manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(len(files), "files")


if __name__ == "__main__":
    main()
