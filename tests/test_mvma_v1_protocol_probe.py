"""MVMA-v1 protocol freeze, source-probe parsers and the outcome firewall (no network)."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from research.market_valuation_macro_overlay_v1 import protocol as P
from research.market_valuation_macro_overlay_v1 import source_probe as SP

PKG = Path(P.__file__).resolve().parent


@pytest.fixture()
def spec():
    return json.loads(P.PROTOCOL_PATH.read_text())


# ------------------------------------------------------------------ protocol

def test_committed_protocol_loads_and_matches_sidecar():
    loaded = P.load_protocol()
    assert loaded["status"] == "PREREGISTERED_NOT_AUTHORIZED"
    assert [h["id"] for h in loaded["hypotheses"] if h["holmFamily"] == "PRIMARY"] == ["H1-US-TRAILING", "H2-US-VM1T"]


def test_edited_protocol_bytes_are_refused(tmp_path):
    copy_path = tmp_path / "protocol.json"
    copy_path.write_bytes(P.PROTOCOL_PATH.read_bytes() + b" ")
    with pytest.raises(P.ProtocolError, match="PROTOCOL_DIGEST_MISMATCH"):
        P.load_protocol(copy_path, P.SIDECAR_PATH)


@pytest.mark.parametrize("mutate,code", [
    (lambda s: s["firewall"].__setitem__("outcomeExecutionAuthorized", True), "FIREWALL_FLAG_NOT_FALSE"),
    (lambda s: s["firewall"].__setitem__("executionAuthorizationFile", "x.json"), "EXECUTION_AUTHORIZATION_PRESENT"),
    (lambda s: s.__setitem__("evidenceClassification", "CONFIRMATORY"), "EVIDENCE_CLASSIFICATION_CHANGED"),
    (lambda s: s["signals"].__setitem__("CREDIT_PERCENTILE", 80.0), "SIGNAL_CONSTANT_MISMATCH"),
    (lambda s: s["signals"].__setitem__("PE_HISTORY_MONTHS", 36), "SIGNAL_CONSTANT_MISMATCH"),
    (lambda s: s["policies"]["B1"].__setitem__("weight", 0.7), "STATIC_WEIGHT_MISMATCH"),
    (lambda s: s["policies"].__setitem__("VM1", {"kind": "DYNAMIC", "inputs": ["cheap", "earningsStable",
                                                                              "creditStress"]}),
     "UNQUALIFIED_EARNINGS_VARIANT"),
    (lambda s: s["hypotheses"][2].__setitem__("holmFamily", "PRIMARY"), "INELIGIBLE_HYPOTHESIS_IN_FAMILY"),
    (lambda s: s["hypotheses"][4].__setitem__("holmFamily", "SECONDARY"), "UNAVAILABLE_HYPOTHESIS_IN_FAMILY"),
    (lambda s: s["calendar"]["evaluationWindowUS"].__setitem__("months", 160), "WINDOW_MONTH_COUNT_MISMATCH"),
    (lambda s: s["signalSources"]["US_TRAILING_PE"].__setitem__("earningsLagMonths", 2), "EARNINGS_LAG_MISMATCH"),
    (lambda s: s["markets"]["KR"].__setitem__("status", "ELIGIBLE"), "KR_STATUS_CHANGED_WITHOUT_EXCEPTION"),
    (lambda s: s.__setitem__("results", {"H1": 0.01}), "FORBIDDEN_RESULT_KEYS"),
    (lambda s: s["hypotheses"][0].__setitem__("pValue", 0.01), "FORBIDDEN_RESULT_KEYS"),
])
def test_validator_refuses_each_mutation(spec, mutate, code):
    bad = copy.deepcopy(spec)
    mutate(bad)
    with pytest.raises(P.ProtocolError, match=code):
        P.validate(bad)


def test_sidecar_is_the_sha256_of_the_protocol_bytes():
    assert P.SIDECAR_PATH.read_text().split()[0] == hashlib.sha256(P.PROTOCOL_PATH.read_bytes()).hexdigest()


# ------------------------------------------------------------------ probe parsers

def test_shiller_parser_never_touches_outcome_columns():
    requested = set()
    table = {0: [1871.01, 2023.1, "x"], 1: [4.44, 4000.0, None], 3: [0.4, 180.0, None], 12: [None, 30.0, None]}

    def cell(r, c):
        if r >= 3:
            raise IndexError
        requested.add(c)
        column = table.get(c)
        return column[r] if column else None

    rows = SP.shiller_rows(cell)
    assert set(rows) == {"1871-01", "2023-10"}
    assert rows["2023-10"]["P"] == 4000.0 and rows["2023-10"]["CAPE"] == 30.0
    assert requested <= {0, 1, 2, 3, 4, 12}
    assert not requested & SP.FORBIDDEN_SHILLER_COLUMNS


def test_shiller_summary_and_vintage_differences():
    old = {"2023-05": {"P": 1.0, "D": 1.0, "E": 179.17, "CPI": 1.0, "CAPE": 1.0},
           "2023-06": {"P": 1.0, "D": 1.0, "E": None, "CPI": 1.0, "CAPE": 1.0}}
    new = {"2023-05": {"P": 1.0, "D": 1.0, "E": 179.06, "CPI": 1.0, "CAPE": 1.0},
           "2023-06": {"P": 2.0, "D": 1.0, "E": 181.0, "CPI": 1.0, "CAPE": 1.0}}
    summary = SP.shiller_summary(new)
    assert summary["lastEarningsMonth"] == "2023-06" and summary["months"] == 2
    assert SP.shiller_summary(old)["lastEarningsMonth"] == "2023-05"
    diff = SP.vintage_differences(old, new)
    assert diff["columns"]["E"]["differingMonths"] == 1          # 2023-06 is missing in the old vintage
    assert diff["columns"]["P"]["differingMonths"] == 1
    assert diff["columns"]["D"]["differingMonths"] == 0


def test_alfred_fallback_to_current_vintage_is_detected():
    rows = [("2000-01-01", 1.0), ("2000-02-01", None)]
    served = SP.alfred_vintage_reading("BAA", "2005-01-03", "BAA_20050103", rows)
    assert served["status"] == "VINTAGE_SERVED" and served["lastObservation"] == "2000-01-01"
    fallback = SP.alfred_vintage_reading("DBAA", "2011-06-01", "DBAA_20261121", rows)
    assert fallback["status"] == "NO_VINTAGE_AT_DATE_CURRENT_SERVED"
    assert SP.alfred_vintage_reading("X", "2011-06-01", "X", [])["status"] == "NO_DATA"


def test_fred_csv_and_revision_count():
    header, rows = SP.parse_fred_csv("observation_date,BAA\n2000-01-01,7.5\n2000-02-01,.\n2000-03-01,7.7\n")
    assert header == "BAA" and rows[1] == ("2000-02-01", None)
    assert SP.fred_coverage(rows) == {"rows": 3, "valued": 2, "firstObservation": "2000-01-01",
                                      "lastObservation": "2000-03-01"}
    revisions = SP.revision_count(rows, [("2000-01-01", 7.5), ("2000-03-01", 7.8)])
    assert revisions["compared"] == 2 and revisions["differing"] == 1


def test_factset_slug_parsing_and_years():
    page = ('<a href="https://insight.factset.com/earningsinsight_02.17.17">x</a>'
            '<a href="https://insight.factset.com/2012/11/earningsinsight_11.9.12">x</a>'
            '<a href="https://insight.factset.com/sp-500-earnings-season-update-november-6-2026">x</a>'
            '<a href="https://insight.factset.com/topic/earnings/page/2">x</a>'
            '<a href="https://insight.factset.com/author/john-butters">x</a>')
    slugs = SP.factset_slugs(page)
    assert slugs == ["2012/11/earningsinsight_11.9.12", "earningsinsight_02.17.17",
                     "sp-500-earnings-season-update-november-6-2026"]
    assert [SP.factset_slug_year(s) for s in slugs] == [2012, 2017, 2026]


def test_months_between_quarter_end_and_vintage():
    from datetime import date
    assert SP.months_between("2024-06", date(2024, 9, 4)) == pytest.approx(2.17, abs=0.01)


# ------------------------------------------------------------------ outcome firewall

OUTCOME_NAMES = {"totalReturnClose", "forward_return", "forwardReturn", "excess_return", "nav", "cagr", "sharpe",
                 "max_drawdown", "decompose", "overlay_returns"}


@pytest.mark.parametrize("module", ["features.py", "signals.py", "protocol.py", "source_probe.py",
                                    "collect_inputs.py", "build_signals.py"])
def test_package_code_reads_no_outcome(module):
    tree = ast.parse((PKG / module).read_text())
    # protocol.py's own refusal list names the result keys it forbids; that one assignment is not a read.
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign)
                                             and any(getattr(t, "id", "") == "FORBIDDEN_KEYS" for t in n.targets))]
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
        elif isinstance(node, (ast.FunctionDef, ast.ImportFrom)):
            names.add(getattr(node, "name", None) or getattr(node, "module", "") or "")
    assert not names & OUTCOME_NAMES, module
