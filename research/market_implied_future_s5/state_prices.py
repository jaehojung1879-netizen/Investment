"""One public Cboe sample and finite-support no-arbitrage state-price bounds."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener
from zipfile import ZipFile

import numpy as np
from scipy.optimize import linprog

from .acquire import ROOT, NoRedirect
from .foundation import MAX_BYTES, state_discount_witness
from .snapshot import bytes_from_receipt, encode

URL = "https://datashop.cboe.com/download/sample/217"
MEMBER = "UnderlyingOptionsEODCalcs_2023-08-25_cgi_or_historical.csv"
QUOTE_DATE, EXPIRY = "2023-08-25", "2023-09-25"
DISCOUNT_BOUNDS = (.994, .998)
WING = (3950.0, 4050.0)
REQUIRED = {"underlying_symbol", "quote_date", "root", "expiration", "strike", "option_type", "bid_1545", "ask_1545"}


def fetch(root):
    """Download the documented standalone product sample; never use delayed quote tables."""
    root = root.resolve()
    if root.is_relative_to(ROOT):
        raise ValueError("RAW_OUTPUT_OUTSIDE_REPOSITORY_REQUIRED")
    archive, receipt = root / "sample-217.zip", root / "sample-217.json"
    if archive.exists() or receipt.exists():
        raise FileExistsError("OPTION_SAMPLE_ALREADY_RECEIPTED")
    request = Request(URL, headers={"User-Agent": "Investment research source validation/1.1"})
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        if response.geturl() != URL or response.status != 200:
            raise ValueError("UNEXPECTED_SAMPLE_RESPONSE")
        headers = {name: response.headers.get(name) for name in ("Date", "Last-Modified", "ETag", "Content-Type")}
        raw = response.read(MAX_BYTES + 1)
    received = datetime.now(timezone.utc)
    parse_sample(raw)
    archive.write_bytes(raw)
    receipt.write_text(encode({"url": URL, "httpStatus": 200, "responseHeaders": headers, "path": archive.name,
                               "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                               "retrievedAtUtc": received}), encoding="utf-8")


def parse_sample(raw):
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("SAMPLE_SIZE")
    selected = {}
    with ZipFile(io.BytesIO(raw)) as archive:
        members = [m for m in archive.infolist() if m.filename == MEMBER]
        if len(members) != 1 or not 0 < members[0].file_size <= 64 * 1024 * 1024:
            raise ValueError("UNEXPECTED_OPTION_ARCHIVE")
        with archive.open(members[0]) as handle:
            reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"))
            header = reader.fieldnames or []
            if len(set(header)) != len(header) or not REQUIRED <= set(header):
                raise ValueError("OPTION_SAMPLE_SCHEMA")
            for row in reader:
                if None in row or any(x is None for x in row.values()):
                    raise ValueError("MALFORMED_OPTION_ROW")
                if (row["root"], row["underlying_symbol"], row["quote_date"], row["expiration"]) != (
                    "SPXW", "^SPX", QUOTE_DATE, EXPIRY
                ):
                    continue
                option_type = row["option_type"]
                strike, bid, ask = map(float, (row["strike"], row["bid_1545"], row["ask_1545"]))
                key = option_type, strike
                if (
                    key in selected or option_type not in {"C", "P"}
                    or not all(math.isfinite(v) for v in (strike, bid, ask))
                    or strike <= 0 or bid < 0 or ask <= 0 or bid > ask
                ):
                    raise ValueError("INVALID_OPTION_QUOTE")
                selected[key] = (bid, ask)
    if len(selected) < 8 or not {"C", "P"} <= {side for side, _ in selected}:
        raise ValueError("OPTION_SAMPLE_CHAIN_INCOMPLETE")
    return selected


def state_model(quotes, cap, discount_bounds, wing):
    d_min, d_max = discount_bounds
    low, high = wing
    if not 0 < d_min <= d_max or not 0 <= low < high < cap or any(k >= cap for _, k in quotes):
        raise ValueError("INVALID_SUPPORT_OR_DISCOUNT")
    # All option and put-spread payoffs interpolate linearly between these
    # knots. Any measure on this bounded support can be mapped onto the grid
    # preserving all its measured prices, mass and objective.
    points = np.array(sorted({0., float(cap), *wing, *(k for _, k in quotes)}))
    payoffs, bid, ask = [], [], []
    for (side, strike), (lo, hi) in quotes.items():
        payoffs.append(np.maximum(points - strike if side == "C" else strike - points, 0))
        bid.append(lo)
        ask.append(hi)
    payoffs = np.array(payoffs)
    a = np.concatenate([np.column_stack([payoffs, -np.array(ask)]),
                        np.column_stack([-payoffs, np.array(bid)])])
    lower_bounds = [(0, None)] * len(points) + [(1 / d_max, 1 / d_min)]
    mass = [*[1] * len(points), 0]

    def bound(values):
        a_objective = np.append(values, 0.)
        result = []
        for direction in (1, -1):
            fitted = linprog(a_objective * direction, A_ub=a, b_ub=np.zeros(len(a)),
                             A_eq=[mass], b_eq=[1], bounds=lower_bounds, method="highs")
            if fitted.status == 2:
                return None
            if not fitted.success:
                raise RuntimeError(f"LP_STATUS_{fitted.status}")
            result.append(float(direction * fitted.fun))
        return result

    # q sums to one and z=1/D. Linear inequalities enforce bid*z <= E_q[payoff] <= ask*z.
    q_put_spread = bound(np.clip((high - points) / (high - low), 0, 1))
    if q_put_spread is None:
        return {"status": "NO_FEASIBLE_SINGLE_EXPIRY_MODEL", "supportCapIndexPoints": cap}
    return {"status": "NONEMPTY_SINGLE_EXPIRY_STATE_PRICE_SET", "supportCapIndexPoints": cap,
            "piecewiseLinearKnots": len(points), "riskNeutralPutSpreadExpectation": q_put_spread,
            "riskNeutralTerminalForwardIndexPoints": bound(points)}


def synthetic_witnesses():
    q, p_a, p_b = [.2, .6, .2], [.1, .6, .3], [.35, .5, .15]
    return {
        "sameQDifferentPhysicalP": {"riskNeutralProbability": q, "discountFactor": .98,
                                   "physicalA": p_a, "physicalB": p_b,
                                   "sdfA": state_discount_witness(q, p_a, .98),
                                   "sdfB": state_discount_witness(q, p_b, .98)},
        "negativeButterfly": state_model({("C", 90.): (15., 15.), ("C", 100.): (12., 12.),
                                          ("C", 110.): (2., 2.)}, 300, (.98, 1.), (90., 110.)),
    }


def build(root):
    clock = datetime.now(timezone.utc)
    receipt = json.loads((root / "sample-217.json").read_text(encoding="utf-8"))
    if receipt["url"] != URL or receipt["httpStatus"] != 200:
        raise ValueError("UNREGISTERED_OPTION_SAMPLE")
    raw = bytes_from_receipt(root, receipt, clock)
    quotes = parse_sample(raw)
    return {
        "status": "AUTHOR_VALIDATION_ONLY", "classification": "ACTUAL_PUBLIC_HISTORICAL_SAMPLE_SUBSET",
        "sampleReceipt": {key: value for key, value in receipt.items() if key != "path"},
        "member": MEMBER, "quoteTime": "2023-08-25T15:45:00-04:00", "expiry": EXPIRY,
        "product": "SPXW European cash-settled PM", "quoteUnit": "SPX index points",
        "eligibleQuotes": len(quotes), "uniqueStrikes": len({k for _, k in quotes}),
        "zeroBidsRetained": sum(bid == 0 for bid, _ in quotes.values()),
        "discountBoundsAssumed": DISCOUNT_BOUNDS, "putSpreadStrikesIndexPoints": WING,
        "capacities": [state_model(quotes, cap, DISCOUNT_BOUNDS, WING) for cap in (6600, 8800)],
        "synthetic": synthetic_witnesses(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.fetch:
        fetch(args.raw_dir)
    result = build(args.raw_dir)
    args.report.write_text(encode(result), encoding="utf-8")


if __name__ == "__main__":
    main()
