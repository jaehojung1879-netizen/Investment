"""Daily KRX prices for the industry baskets and the benchmark (Yahoo chart API, adjusted close incl. distributions).

    python -m research.industry_alpha_discovery_v1.fetch_prices --private <dir outside git>

Prices are kept outside git (vendor data); the committed manifest records ticker, first/last date, rows and SHA-256 of
the stored CSV so a later run can prove it used the same bytes. `adjclose` is Yahoo's split- and dividend-adjusted close,
so returns on it are total returns where Yahoo carries the distribution (KODEX 200 distributions are carried; the
benchmark is therefore a total-return series, as in the rest of this repository's 069500.KS work).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
TICKERS = {
    "069500.KS": "KODEX 200 (benchmark)",
    "005930.KS": "삼성전자", "000660.KS": "SK하이닉스", "091160.KS": "KODEX 반도체",
    "005380.KS": "현대차", "000270.KS": "기아", "012330.KS": "현대모비스", "091180.KS": "KODEX 자동차",
    "010950.KS": "S-Oil", "096770.KS": "SK이노베이션",
    "009540.KS": "HD한국조선해양", "010140.KS": "삼성중공업", "042660.KS": "한화오션",
    "^KS11": "KOSPI",
}
P1, P2 = 1325376000, 1795500000   # 2012-01-01 .. 2026-11


def fetch(t: str) -> pd.DataFrame:
    u = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}?period1={P1}&period2={P2}"
         "&interval=1d&events=div%7Csplit")
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                j = json.loads(r.read())
            break
        except Exception:  # noqa: BLE001
            time.sleep(5 * (k + 1))
    else:
        raise RuntimeError(t)
    res = j["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
    df = pd.DataFrame({"date": pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("Asia/Seoul").date,
                       "close": q["close"], "adjclose": adj, "volume": q["volume"]})
    return df.dropna(subset=["adjclose"]).drop_duplicates("date", keep="last")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    a = ap.parse_args(argv)
    out = Path(a.private) / "prices"
    out.mkdir(parents=True, exist_ok=True)
    man = {}
    for t, nm in TICKERS.items():
        df = fetch(t)
        p = out / f"{t.replace('^', '_')}.csv"
        df.to_csv(p, index=False)
        man[t] = {"name": nm, "rows": len(df), "first": str(df.date.iloc[0]), "last": str(df.date.iloc[-1]),
                  "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        print(t, man[t], flush=True)
        time.sleep(1.5)
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "price-manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
