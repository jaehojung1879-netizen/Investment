"""Static GICS-style sector map for the screening universe.

Sector membership drives three v2 features that a flat cross-sectional rank
cannot do honestly:

  * sector/industry-NEUTRAL factor z-scores (a bank's 0.8 P/B and an
    industrial's 3x P/B are not comparable raw; they are comparable *within*
    their sector),
  * sector exposure caps inside the model sleeve, and
  * portfolio/sector concentration warnings on entry.

Prices come from yfinance but the *sector* is bundled here so the map is
deterministic and offline-testable. yfinance's ``info['sector']`` is harvested
opportunistically in fundamentals.py and, when present, overrides this map.
Names we don't recognise resolve to ``None`` — which lowers that name's
factor coverage/confidence rather than silently bucketing it wrong.
"""
from __future__ import annotations

# GICS-ish sector keys (English, stable). Display translation lives in the UI.
_US = {
    "Technology": [
        "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "ACN",
        "CSCO", "IBM", "TXN", "QCOM", "NOW", "INTU", "KLAC", "MU", "SNPS",
        "PANW", "CDNS", "APH", "MSI", "NXPI", "ROP", "ADI",
    ],
    "Communication Services": ["GOOGL", "GOOG", "META", "NFLX", "VZ", "T"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "LOW", "BKNG", "TJX", "ORLY", "MAR"],
    "Consumer Staples": ["WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "CL"],
    "Financials": [
        "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "SPGI",
        "BLK", "C", "SCHW", "CB", "PGR", "ICE", "USB", "AON", "MMC", "FI",
    ],
    "Health Care": [
        "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "ISRG",
        "AMGN", "PFE", "SYK", "ELV", "VRTX", "MDT", "BSX", "GILD", "REGN",
        "ZTS", "CI", "MCK",
    ],
    "Energy": ["XOM", "CVX", "EOG"],
    "Industrials": [
        "GE", "CAT", "UNP", "HON", "RTX", "BA", "DE", "LMT", "NOC", "ITW",
        "EMR", "CSX", "GD", "ETN", "PH", "WM",
    ],
    "Materials": ["LIN", "SHW", "APD", "FCX"],
    "Utilities": ["NEE", "SO", "DUK"],
    "Real Estate": ["PLD"],
}

_KR = {
    "Technology": ["005930.KS", "000660.KS", "009150.KS", "011070.KS", "018260.KS"],
    "Materials": [
        "373220.KS", "006400.KS", "051910.KS", "003670.KS", "009830.KS",
        "011780.KS", "010130.KS", "004020.KS", "005490.KS",
    ],
    "Communication Services": [
        "035420.KS", "035720.KS", "036570.KS", "251270.KS", "352820.KS",
        "030200.KS", "017670.KS",
    ],
    "Consumer Discretionary": ["005380.KS", "000270.KS", "012330.KS", "066570.KS", "008770.KS", "139480.KS"],
    "Financials": [
        "105560.KS", "055550.KS", "086790.KS", "316140.KS", "024110.KS",
        "138040.KS", "032830.KS", "000810.KS",
    ],
    "Health Care": ["207940.KS", "068270.KS", "326030.KS", "302440.KS", "000100.KS"],
    "Industrials": [
        "009540.KS", "042660.KS", "010140.KS", "329180.KS", "012450.KS",
        "267260.KS", "010120.KS", "034020.KS", "047040.KS", "006260.KS",
        "064350.KS", "011200.KS", "028260.KS",
    ],
    "Consumer Staples": [
        "051900.KS", "090430.KS", "097950.KS", "271560.KS", "000080.KS",
        "282330.KS", "001040.KS", "033780.KS",
    ],
    "Energy": ["096770.KS", "010950.KS", "078930.KS"],
    "Utilities": ["015760.KS"],
    "Holding": ["003550.KS", "034730.KS"],
}

# Korean display names for the sector keys.
SECTOR_KO = {
    "Technology": "정보기술",
    "Communication Services": "커뮤니케이션",
    "Consumer Discretionary": "경기소비재",
    "Consumer Staples": "필수소비재",
    "Financials": "금융",
    "Health Care": "헬스케어",
    "Energy": "에너지",
    "Industrials": "산업재",
    "Materials": "소재",
    "Utilities": "유틸리티",
    "Real Estate": "리츠·부동산",
    "Holding": "지주",
    None: "미분류",
}

# Sectors where the standard value/quality yardsticks mislead and need special
# handling (financials carry structurally high leverage; utilities/real estate
# too). The long-term engine down-weights leverage penalties for these.
LEVERAGE_EXEMPT_SECTORS = {"Financials", "Utilities", "Real Estate", "Holding"}

_TICKER_TO_SECTOR: dict[str, str] = {}
for _sector, _tks in {**{k: v for k, v in _US.items()}}.items():
    for _t in _tks:
        _TICKER_TO_SECTOR[_t] = _sector
for _sector, _tks in _KR.items():
    for _t in _tks:
        _TICKER_TO_SECTOR[_t] = _sector


def sector_of(ticker: str, override: str | None = None) -> str | None:
    """Return the sector for ``ticker``.

    A non-empty ``override`` (e.g. yfinance ``info['sector']``) wins over the
    bundled map so live data can correct/extend it; otherwise fall back to the
    static map, else ``None``.
    """
    if override:
        return str(override)
    return _TICKER_TO_SECTOR.get(ticker)


def sector_ko(sector: str | None) -> str:
    return SECTOR_KO.get(sector, sector or "미분류")
