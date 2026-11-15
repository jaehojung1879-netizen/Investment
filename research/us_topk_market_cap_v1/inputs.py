"""Backward-only capitalization inputs, separate from forward-label evaluation."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import math


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def write(path, value):
    path = Path(path)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False) + "\n").encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invert_forward(rows, events, through):
    """Exact algebraic inverse of the registered split/dividend forward recipe.

    Counts remain as-traded. No future return, EPS average shares, or TR price
    is used in a capitalization. The first close anchors the registered series.
    """
    cumulative, previous_tr = 1.0, None
    out = {}
    for day, row in sorted(rows.items()):
        if day > through:
            break
        tr = row.get("Close")
        if tr is None or not math.isfinite(tr) or tr <= 0:
            continue
        event = events.get(day, {})
        ratio = event.get("split") or 1.0
        dividend = event.get("dividend") or 0.0
        if dividend and previous_tr is not None:
            previous_raw = previous_tr / cumulative
            if not 0 < dividend < previous_raw:
                raise ValueError("REGISTERED_DIVIDEND_INVERSION_REFUSED")
            cumulative *= ratio / (1 - dividend / previous_raw)
        else:
            cumulative *= ratio
        out[day] = tr / cumulative
        previous_tr = tr
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market-private", type=Path, required=True)
    ap.add_argument("--private", type=Path, required=True)
    args = ap.parse_args()
    baseline = read(args.market_private / "baseline-bars.json.gz")
    events = read(args.market_private / "baseline-events.json.gz")
    prices = {t: invert_forward(rows, events.get(t, {}), "2026-09-11")
              for t, rows in baseline.items() if t != "PARA"}
    del baseline
    newer = read(args.market_private / "new-source-series.json.gz")
    deviation = {}
    for ticker, record in newer.items():
        raw = {d: v for d, v in record["raw_close"].items() if d <= "2026-09-11"}
        common = sorted(set(raw) & set(prices.get(ticker, {})))
        if common:
            delta = max(abs(raw[d] / prices[ticker][d] - 1) for d in common)
            deviation[ticker] = delta
        # Reuse already admitted raw quotes rather than a second acquisition.
        prices.setdefault(ticker, {}).update(raw)
    del newer
    # Frozen #340 packets are already independently verified in corrected run.
    packet = read(args.market_private / "public-para-price-packet.json")
    for ticker, rows in packet.items():
        after = 1.0
        raw = {}
        for row in reversed(rows):
            day = row["date"]
            if day <= "2026-09-11":
                raw[day] = row["Close"] * after
            after *= row.get("Stock Splits") or 1.0
        prices[ticker] = raw
    # Registered symbol-only changes, same CIK/class, retain source symbols too.
    aliases = {"ABC": "COR", "BLL": "BALL", "FB": "META", "ANTM": "ELV"}
    for old, new in aliases.items():
        if old in prices and new not in prices:
            prices[new] = prices[old]
    digest = write(args.private / "signal-raw-prices.json.gz", prices)
    shares = {}
    for receipt in read(args.private / "sec-companyfacts-receipts.json"):
        if receipt["status"] != 200:
            continue
        data = read(args.private / receipt["object"])
        entries = []
        for namespace, tag in (("dei", "EntityCommonStockSharesOutstanding"),
                               ("us-gaap", "CommonStockSharesOutstanding"),
                               ("ifrs-full", "NumberOfSharesOutstanding")):
            facts = data["facts"].get(namespace, {}).get(tag, {})
            for fact in facts.get("units", {}).get("shares", []):
                if not fact.get("start") and fact["val"] > 0 and fact["filed"] < "2026-09-11":
                    entries.append({**fact, "tag": namespace + ":" + tag,
                                    "receipt": receipt["sha256"]})
        # Earliest publication for each period/tag avoids later restatement
        # and split recasts of a past period. Later-period counts still supersede.
        first = {}
        for fact in sorted(entries, key=lambda r: (r["filed"], r["accn"])):
            first.setdefault((fact["end"], fact["tag"]), fact)
        shares[str(int(data["cik"]))] = {"name": data["entityName"], "facts": list(first.values())}
    write(args.private / "shares-standard.json.gz", shares)
    write(args.private / "raw-price-validation.json", {
        "signal_raw_prices_sha256": digest, "tickers": len(prices),
        "reconstructed_vs_reused_raw_max_relative_difference": deviation,
        "basis": "AS_TRADED_USD_CLOSE_NOT_TOTAL_RETURN",
        "through": "2026-09-11",
    })
    print({"raw_tickers": len(prices), "share_issuers": len(shares), "raw_sha256": digest})


if __name__ == "__main__":
    main()
