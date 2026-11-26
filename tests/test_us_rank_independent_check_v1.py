"""us-rank-independent-check-v1: synthetic tests for the SPY filing parsers and the Codex cross-checks. No network access."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "us_rank_independent_check_v1"


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SN = _load("us_rank_snapshot", D / "snapshot.py")
X = _load("us_rank_crosscheck", D / "crosscheck.py")

NPORT = b"""<?xml version="1.0"?><edgarSubmission><repPdDate>2022-06-30</repPdDate><netAssets>1000</netAssets>
<invstOrSec><name>Alphabet Inc</name><lei>L1</lei><title>Alphabet Inc</title><cusip>02079K305</cusip><balance>10</balance><units>NS</units>
<valUSD>300</valUSD><pctVal>3</pctVal><assetCat>EC</assetCat></invstOrSec>
<invstOrSec><name>Alphabet Inc</name><lei>L1</lei><title>Alphabet Inc</title><cusip>02079K107</cusip><balance>9</balance><units>NS</units>
<valUSD>280</valUSD><pctVal>2.8</pctVal><assetCat>EC</assetCat></invstOrSec>
<invstOrSec><name>Apple Inc</name><lei>L2</lei><title>Apple Inc</title><cusip>037833100</cusip><balance>20</balance><units>NS</units>
<valUSD>500</valUSD><pctVal>5</pctVal><assetCat>EC</assetCat></invstOrSec>
<invstOrSec><name>Cash Fund</name><lei>L3</lei><title>MMF</title><cusip>000000000</cusip><balance>1</balance><units>NS</units>
<valUSD>20</valUSD><pctVal>0.2</pctVal><assetCat>STIV</assetCat></invstOrSec></edgarSubmission>"""

N30D = b"""<HTML><BODY><P>Schedule of Investments ... 1</P><P>Schedule of Investments</P><TABLE>
<TR><TD>Alphabet, Inc. Class A(a)</TD><TD>10</TD><TD>$</TD><TD>300</TD></TR>
<TR><TD>Alphabet, Inc. Class C(a)</TD><TD>9</TD><TD>280</TD>
<TR><TD>Apple, Inc.</TD><TD>20</TD><TD>500</TD></TR>
<TR><TD>TOTAL COMMON STOCKS (Cost $1)</TD><TD>1,080</TD></TR></TABLE></BODY></HTML>"""


def test_nport_lines_group_by_lei_and_rank_companies():
    meta, lines = SN.parse_nport(NPORT)
    assert meta["repPdDate"] == "2022-06-30" and len(lines) == 4
    eq = [x for x in lines if x["assetCat"] == "EC"]
    comp, tot = SN.companies(eq, "NPORT-P")
    assert tot == 1080 and [c["name"] for c in comp] == ["Alphabet Inc", "Apple Inc"] and comp[0]["valueUsd"] == 580
    assert SN.boundary(comp, 1) == {"k": 1, "inside": "Alphabet Inc", "outside": "Apple Inc", "relativeGap": 80 / 580, "thin": False}


def test_n30d_cell_walk_survives_an_unclosed_row_and_reconciles_to_the_filing_total():
    meta, lines = SN.parse_n30d(N30D)
    assert len(lines) == 3 and meta["parsedSumUsd"] == meta["totalCommonStocksUsd"] == 1080
    comp, _ = SN.companies(lines, "N-30D")
    assert len(comp) == 2 and comp[0]["valueUsd"] == 580          # footnote "(a)" and the class suffix are removed before grouping


def test_issuer_key_strips_class_and_footnote_only():
    assert SN.issuer_key_from_name("Alphabet, Inc. Class C(a)") == SN.issuer_key_from_name("Alphabet, Inc. Class A")
    assert SN.issuer_key_from_name("Apartment Investment & Management Co. Class A REIT") == SN.issuer_key_from_name("Apartment Investment & Management Co.")
    assert SN.issuer_key_from_name("Fox Corp") != SN.issuer_key_from_name("News Corp")


def test_bot_defence_script_is_the_only_thing_stripped():
    raw = b'<P>x</P><script type="text/javascript"  src="/88tB/Lib/MC/Zw/FMmAWE"></script></BODY>'
    assert SN.BOT_SCRIPT.sub(b"", raw) == b"<P>x</P></BODY>"
    assert SN.BOT_SCRIPT.sub(b"", b'<script type="text/javascript" src="https://x/y.js"></script>') != b""


def _snap():
    return {"holdingAsOf": "2022-06-30", "top100": [
        {"issuerKey": "LEI:A", "name": "Apple", "weight": 0.5, "tickers": ["AAPL"]},
        {"issuerKey": "LEI:G", "name": "Alphabet", "weight": 0.3, "tickers": ["GOOGL", "GOOG"]},
        {"issuerKey": "LEI:M", "name": "Microsoft", "weight": 0.2, "tickers": ["MSFT"]}]}


def test_rank_weight_check_merges_share_classes_and_names_disagreements():
    h = pd.DataFrame({"date": ["2022-06-30"] * 4, "ticker": ["AAPL", "GOOG", "GOOGL", "XYZ"], "rank": [1, 2, 3, 4], "weight": [0.5, 0.15, 0.15, 0.2]})
    r = X.rank_weight_check(h, [_snap()], ks=(2, 3))[0]
    assert r["byK"]["2"]["overlap"] == 2 and r["byK"]["3"]["codexTickersNotOnSpyTop100"] == ["XYZ"]
    assert r["weightsWithinCommonNames"]["maxAbsDiff"] < 1e-12            # 0.5 : 0.3 within the common names on both sides
    assert X.rank_weight_check(h.assign(date="2022-07-08"), [_snap()])[0]["status"].startswith("NO_CODEX_DATE")


def test_return_check_never_borrows_a_neighbouring_session():
    idx = pd.to_datetime(["2022-01-03", "2022-01-04", "2022-01-05"])
    fake = lambda t, a, b: pd.DataFrame({"Adj Close": [100.0, 101.0, 110.0]}, index=idx)  # noqa: E731
    assert abs(X.yahoo_total_return("AAPL", "2022-01-03", "2022-01-05", fake) - 0.10) < 1e-12
    assert X.yahoo_total_return("AAPL", "2022-01-03", "2022-01-06", fake) is None
    h = pd.DataFrame({"ticker": ["AAPL"], "periodStart": ["2022-01-03"], "periodEnd": ["2022-01-05"], "totalReturn": [0.1005]})
    r = X.return_check(h, downloader=fake)
    assert r["compared"] == 1 and r["withinTolerance"] == 1


def _weekly(n=104, seed=1, star=None):
    rng = np.random.default_rng(seed)
    w = pd.DataFrame({"week": pd.date_range("2021-01-08", periods=n, freq="W-FRI"), "benchmarkReturn": rng.normal(0.002, 0.02, n)})
    w["contrib:AAA"] = rng.normal(0.0002, 0.003, n)
    w["contrib:BBB"] = rng.normal(0.0002, 0.003, n)
    if star:
        w.loc[w["week"].dt.year == star, "contrib:AAA"] += 0.01
    w["portfolioReturn"] = w["benchmarkReturn"] + w["contrib:AAA"] + w["contrib:BBB"]
    return w


def test_concentration_finds_the_name_and_the_year_that_carry_the_result():
    w = _weekly(star=2022)
    c = X.concentration(w)
    assert c["topNames"][0]["ticker"] == "AAA" and c["topNames"][0]["annualisedExcessWithout"] < c["annualisedExcess"]
    assert 2022 in c["leaveOneYearOut"]


def test_missing_week_bounds_can_flip_a_thin_result():
    w = _weekly(n=60, seed=3)
    w["portfolioReturn"] = w["benchmarkReturn"] + 0.002                 # a thin positive edge ...
    w.loc[5, "portfolioReturn"] = w.loc[5, "benchmarkReturn"] - 0.03    # ... with one bad observed week
    expected = list(pd.date_range("2021-01-08", periods=80, freq="W-FRI"))
    r = X.missing_week_bounds(w, expected)
    assert r["missingWeeks"] == 20 and r["observedAnnualisedExcess"] > 0 and r["WORST_OBSERVED_WEEK"] < 0 < r["BEST_OBSERVED_WEEK"]
    assert r["signFlipsWithinBounds"]


def test_published_snapshots_record_three_distinct_dates_and_verification():
    p = D / "results" / "spy-reference-snapshots.json"
    if not p.exists():
        return
    d = json.loads(p.read_text())
    for s in d["snapshots"]:
        assert s["holdingAsOf"] < s["publicFrom"]
        assert s["verification"] in ("EXACT_SHA256_MATCH_TO_342", "HTML_BOT_SCRIPT_STRIPPED_CONTENT_CHECKED_BY_HOLDING_COUNT")
        assert "officialIndexChangesBetweenHoldingAndPublic" in s and set(s["boundaries"]) == {"5", "10", "100"}


def test_external_index_is_split_at_launch_and_never_chained():
    lv = pd.DataFrame({"date": ["2018-01-02", "2019-01-02", "2020-01-02", "2021-01-04"], "level": [100.0, 110.0, 121.0, 133.1]})
    r = X.external_index_segments(lv, "2019-06-01")
    assert r["BACKTESTED_BEFORE_LAUNCH"]["end"] == "2019-01-02" and r["LIVE_FROM_LAUNCH"]["start"] == "2020-01-02"
    assert abs(r["LIVE_FROM_LAUNCH"]["totalReturn"] - 0.1) < 1e-12
