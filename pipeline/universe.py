"""Resolve the screening universe dynamically.

Primary source: FinanceDataReader (S&P 500 for US, KOSPI listing for KR).
The US universe always contains the complete S&P 500 constituent set; the
configured `universe_size` cap applies only to the market-cap-ranked KR list.
Company names come from the same listing, so KR tickers display as names
automatically.

If a dynamic fetch fails (e.g. a restrictive CI network policy), the KR list
can fall back to the static configuration. US resolution deliberately fails
closed unless a complete S&P 500 list is available, preventing a partial list
from producing order-biased recommendations.
"""
from __future__ import annotations


_MIN_SP500_CONSTITUENTS = 450
_SP500_CSV = (
    "https://raw.githubusercontent.com/datasets/"
    "s-and-p-500-companies/main/data/constituents.csv"
)

# Class-share symbols appear as "BRK.B" (Wikipedia) or "BRKB" (some listings);
# yfinance wants "BRK-B". The generic dot->dash rule can't fix the dotless
# form, so map the S&P 500 cases explicitly.
_US_SYMBOL_FIXES = {"BRK.B": "BRK-B", "BRKB": "BRK-B", "BF.B": "BF-B", "BFB": "BF-B"}


def _us_symbol(raw: str) -> str:
    sym = str(raw).strip().upper()
    return _US_SYMBOL_FIXES.get(sym, sym.replace(".", "-"))


def _us_rows(df) -> tuple[list[str], dict[str, str]]:
    # Columns vary by version; normalise.
    sym_col = next(c for c in df.columns if c.lower() in ("symbol", "ticker", "code"))
    name_col = next(
        (c for c in df.columns if c.lower() in ("name", "company", "security")),
        sym_col,
    )
    df = df.dropna(subset=[sym_col])
    tickers, names = [], {}
    for _, row in df.iterrows():
        sym = _us_symbol(row[sym_col])
        if not sym or sym in names:
            continue
        tickers.append(sym)
        names[sym] = str(row[name_col])
    return tickers, names


def _complete_us_from(sources, errors=None) -> tuple[list[str], dict[str, str]]:
    errors = list(errors or [])
    for source, load in sources:
        try:
            tickers, names = _us_rows(load())
            if len(tickers) >= _MIN_SP500_CONSTITUENTS:
                return tickers, names
            errors.append(f"{source}: only {len(tickers)} constituents")
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    raise RuntimeError("full S&P 500 unavailable (" + "; ".join(errors) + ")")


def _us_sp500() -> tuple[list[str], dict[str, str]]:
    """Return the full S&P 500, never an order-dependent prefix.

    FinanceDataReader has occasionally been unavailable in GitHub Actions, so
    a separately maintained constituent CSV is used as a network fallback.
    Both sources must look like a complete index; accepting a short response
    would reintroduce the same alphabetical/partial-universe bias this module
    is intended to prevent.
    """
    errors = []
    try:
        import FinanceDataReader as fdr

        sources = [("FinanceDataReader", lambda: fdr.StockListing("S&P500"))]
    except Exception as exc:
        errors.append(f"FinanceDataReader import: {exc}")
        sources = []

    def csv_source():
        import pandas as pd

        return pd.read_csv(_SP500_CSV)

    sources.append(("constituent CSV", csv_source))
    return _complete_us_from(sources, errors)


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

    fetchers = {"US": lambda _size: _us_sp500(), "KR": _kr_kospi}
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
            from . import universe_lists as UL
            bundled = {"US": UL.US, "KR": UL.KR}.get(region, [])
            merged = list(dict.fromkeys(list(cfg.universe.get(region, [])) + bundled))
            fallback = merged[:size]
            if region == "US" and len(fallback) < _MIN_SP500_CONSTITUENTS:
                raise RuntimeError(
                    f"full S&P 500 unavailable; refusing partial fallback "
                    f"({len(fallback)} < {_MIN_SP500_CONSTITUENTS})"
                ) from exc
            universe[region] = fallback
            print(f"  universe {region}: fetch failed ({exc}); bundled fallback {len(fallback)} tickers")

    # Always make sure core holdings are screened too.
    for tk in cfg.core:
        region = cfg.region_of(tk)
        universe.setdefault(region, [])
        if tk not in universe[region]:
            universe[region].insert(0, tk)

    # Bundled KR names + fetched names, with user config overriding both.
    from . import universe_lists as UL
    merged_names = {**UL.KR_NAMES, **names, **cfg.names}
    return universe, merged_names

