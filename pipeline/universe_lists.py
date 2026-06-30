"""Bundled constituent lists so the screening universe is large even when the
FinanceDataReader network fetch is blocked (e.g. a restrictive CI policy).

Ordered roughly by market cap (largest first) so capping at `universe_size`
keeps the most liquid, relevant names. Prices are still fetched via yfinance
(which works in CI); only the *list* is bundled here.
"""
from __future__ import annotations

# S&P 500 — top ~115 by market cap (yfinance symbols; class shares use '-').
US = [
    "QQQ", "SPY", "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "AVGO",
    "TSLA", "BRK-B", "LLY", "JPM", "WMT", "V", "UNH", "XOM", "MA", "ORCL",
    "COST", "HD", "PG", "JNJ", "ABBV", "NFLX", "BAC", "KO", "MRK", "CVX",
    "CRM", "AMD", "PEP", "TMO", "ADBE", "LIN", "ACN", "MCD", "CSCO", "WFC",
    "ABT", "GE", "DHR", "IBM", "TXN", "QCOM", "NOW", "INTU", "PM", "CAT",
    "VZ", "ISRG", "GS", "UNP", "AMGN", "SPGI", "MS", "HON", "BKNG", "AXP",
    "RTX", "PFE", "NEE", "LOW", "T", "BLK", "SYK", "ELV", "PLD", "TJX",
    "VRTX", "C", "SCHW", "MDT", "DE", "BSX", "ADP", "BA", "GILD", "MMC",
    "LMT", "ADI", "REGN", "CB", "MO", "FI", "CI", "SO", "BX", "PGR",
    "ZTS", "KLAC", "ETN", "MU", "SNPS", "PANW", "CDNS", "ICE", "SHW", "APH",
    "MCK", "USB", "DUK", "AON", "ITW", "NOC", "WM", "EOG", "CL", "EMR",
    "MSI", "ORLY", "CSX", "GD", "FCX", "APD", "MAR", "NXPI", "ROP", "PH",
]

# KOSPI / KOSDAQ majors (yfinance: 6-digit code + .KS / .KQ).
KR_NAMES = {
    "005930.KS": "삼성전자", "000660.KS": "SK하이닉스", "373220.KS": "LG에너지솔루션",
    "207940.KS": "삼성바이오로직스", "005380.KS": "현대차", "000270.KS": "기아",
    "068270.KS": "셀트리온", "105560.KS": "KB금융", "005935.KS": "삼성전자우",
    "035420.KS": "NAVER", "012330.KS": "현대모비스", "028260.KS": "삼성물산",
    "055550.KS": "신한지주", "035720.KS": "카카오", "051910.KS": "LG화학",
    "006400.KS": "삼성SDI", "000810.KS": "삼성화재", "015760.KS": "한국전력",
    "032830.KS": "삼성생명", "003670.KS": "포스코퓨처엠", "086790.KS": "하나금융지주",
    "138040.KS": "메리츠금융지주", "010130.KS": "고려아연", "009150.KS": "삼성전기",
    "011200.KS": "HMM", "034020.KS": "두산에너빌리티", "033780.KS": "KT&G",
    "066570.KS": "LG전자", "316140.KS": "우리금융지주", "024110.KS": "기업은행",
    "010120.KS": "LS ELECTRIC", "047040.KS": "대우건설", "018260.KS": "삼성에스디에스",
    "030200.KS": "KT", "009540.KS": "HD한국조선해양", "051900.KS": "LG생활건강",
    "097950.KS": "CJ제일제당", "271560.KS": "오리온", "004020.KS": "현대제철",
    "267260.KS": "HD현대일렉트릭", "042660.KS": "한화오션", "010140.KS": "삼성중공업",
    "329180.KS": "HD현대중공업", "012450.KS": "한화에어로스페이스", "064350.KS": "현대로템",
    "005490.KS": "POSCO홀딩스", "017670.KS": "SK텔레콤", "003550.KS": "LG",
    "011070.KS": "LG이노텍", "009830.KS": "한화솔루션", "010950.KS": "S-Oil",
    "078930.KS": "GS", "000100.KS": "유한양행", "090430.KS": "아모레퍼시픽",
    "036570.KS": "엔씨소프트", "251270.KS": "넷마블", "139480.KS": "이마트",
    "008770.KS": "호텔신라", "001040.KS": "CJ", "000080.KS": "하이트진로",
    "282330.KS": "BGF리테일", "006260.KS": "LS", "011780.KS": "금호석유",
    "096770.KS": "SK이노베이션", "034730.KS": "SK", "352820.KS": "하이브",
    "326030.KS": "SK바이오팜", "302440.KS": "SK바이오사이언스",
}
KR = list(KR_NAMES.keys())
