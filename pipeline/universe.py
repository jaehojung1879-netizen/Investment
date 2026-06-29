"""Resolve the screening universe dynamically.

Primary source: FinanceDataReader (S&P 500 for US, KOSPI listing for KR),
ranked by market cap and capped at `universe_size` per region. Company names
come from the same listing, so KR tickers display as names automatically.

If the network fetch fails (e.g. a restrictive CI network policy), we fall
back to the static `universe` / `names` declared in config.json, so the
pipeline never hard-fails on universe resolution.
"""
from __future__ import annotations


def _us_sp500(size: int) -> tuple[list[str], dict[str, str]]:
    import FinanceDataReader as fdr

    df = fdr.StockListing("S&P500")
    # Columns vary by version; normalise.
    sym_col = next(c for c in df.columns if c.lower() in ("symbol", "ticker", "code"))
    name_col = next((c for c in df.columns if c.lower() in ("name", "company")), sym_col)
    df = df.dropna(subset=[sym_col])
    tickers, names = [], {}
    for _, row in df.head(size).iterrows():
        sym = str(row[sym_col]).replace(".", "-").strip()  # BRK.B -> BRK-B for yfinance
        if not sym:
            continue
        tickers.append(sym)
        names[sym] = str(row[name_col])
    return tickers, names


def _kr_kospi(size: int) -> tuple[list[str], dict[str, str]]:
    import FinanceDataReader as fdr

    df = fdr.StockListing("KOSPI")
    code_col = next(c for c in df.columns if c.lower() in ("code", "symbol"))
    name_col = next(c for c in df.columns if c.lower() in ("name", "company"))
    cap_col = next((c for c in df.columns if c.lower() in ("marcap", "marketcap", "market_cap")), None)
    df = df.dropna(subset=[code_col, name_col])
    if cap_col is not None:
        df = df.sort_values(cap_col, ascending=False)
    tickers, names = [], {}
    for _, row in df.head(size).iterrows():
        code = str(row[code_col]).zfill(6)
        if not code.isdigit():
            continue
        tk = f"{code}.KS"
        tickers.append(tk)
        names[tk] = str(row[name_col])
    return tickers, names


def resolve(cfg) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Return (universe {region: [tickers]}, names {ticker: name})."""
    size = cfg.universe_size
    universe: dict[str, list[str]] = {}
    names: dict[str, str] = {}

    fetchers = {"US": _us_sp500, "KR": _kr_kospi}
    for region, fetch in fetchers.items():
        try:
            tks, nm = fetch(size)
            if tks:
                universe[region] = tks
                names.update(nm)
                print(f"  universe {region}: {len(tks)} tickers (dynamic)")
                continue
            raise RuntimeError("empty listing")
        except Exception as exc:
            fallback = cfg.universe.get(region, [])[:size]
            universe[region] = fallback
            print(f"  universe {region}: fetch failed ({exc}); fallback {len(fallback)} tickers")

    # Always make sure core holdings are screened too.
    for tk in cfg.core:
        region = cfg.region_of(tk)
        universe.setdefault(region, [])
        if tk not in universe[region]:
            universe[region].insert(0, tk)

    # config names override fetched names (user-curated wins).
    names.update(cfg.names)
    return universe, names
