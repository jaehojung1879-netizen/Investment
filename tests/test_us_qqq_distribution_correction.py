import json

import numpy as np
import pandas as pd
import pytest

from pipeline import us_dual_benchmark_data as data
from scripts import build_us_qqq_distribution_correction as correction


def test_verified_qqq_distribution_is_added_once_to_original_basis():
    source = data.read_snapshot(correction.foundation.SNAPSHOT)
    qqq = source[source.ticker == "QQQ"].set_index("date")
    revised = correction.corrected_qqq(qqq)
    before = qqq.index < correction.EX_DATE
    multiplier = 1 / (1 - correction.DIVIDEND / qqq.loc[before, "rawClose"].iloc[-1])
    np.testing.assert_allclose(revised[before], qqq.loc[before, "totalReturnClose"], rtol=1e-9)
    np.testing.assert_allclose(revised[~before], qqq.loc[~before, "totalReturnClose"] * multiplier, rtol=1e-9)

    qqq.loc[correction.EX_DATE, "dividend"] = correction.DIVIDEND
    with pytest.raises(ValueError, match="QQQ_DISTRIBUTION_ALREADY_PRESENT"):
        correction.corrected_qqq(qqq)

    qqq.loc[correction.EX_DATE, "dividend"] = 0
    qqq["rawClose"] = qqq["totalReturnClose"]
    with pytest.raises(ValueError, match="QQQ_ORIGINAL_TOTAL_RETURN_BASIS_MISMATCH"):
        correction.corrected_qqq(qqq)


def test_committed_correction_reproduces_and_preserves_spy_benchmark():
    report = correction.build_correction()
    assert report == json.loads(correction.OUTPUT.read_bytes())
    legacy = json.loads(correction.foundation.COMPARISON.read_bytes())
    assert report["officialUsBenchmark"] == "SPY"
    assert report["headline"]["usd"]["SPY"] == legacy["headline"]["usd"]["SPY"]
    assert report["headline"]["usd"]["QQQ"]["cagrPct"] == 19.851
    assert report["headline"]["window"] == legacy["headline"]["window"]
    assert pd.Timestamp(report["correction"]["payDate"]) > correction.EX_DATE
